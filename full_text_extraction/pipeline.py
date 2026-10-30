"""Checkpointed orchestration reusing local PDF preparation and Responses API."""
from __future__ import annotations

from datetime import datetime, timezone
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from contextlib import nullcontext
from threading import Lock
from _thread import LockType
from enum import Enum
import json
from pathlib import Path
import shutil
from pydantic import BaseModel, Field, ValidationError
import api
import admission
import bibliography
import drive_links
import citation_keys
import experiment_design
import models
import pdf_text
import prompts
import progress
import reporting
import spreadsheet
import storage
import validation
import vocabulary as vocab


INTERNAL_SOURCE_ID_PREFIX = 'pdf-'
DIRECTORY_HASH_CHARACTERS = 24
EXPERIMENT_NUMBER_WIDTH = 3
RUN_NAME_FORMAT = '%Y%m%d_%H%M%S_%f_UTC'
RESPONSE_ARCHIVE_FORMAT = '%Y%m%dT%H%M%S%f'
DEFAULT_WORKERS = 1
MAXIMUM_WORKERS = 128
MAXIMUM_UNPACED_WORKERS = 16


class RunStatus(str, Enum):
    PENDING = 'pending'
    PREPARED = 'prepared'
    EXTRACTED = 'extracted'
    ERROR = 'error'


class PaperJob(BaseModel):
    source: str
    paper_id: str
    bibliography_id: str | None = None
    sha256: str
    directory: str
    status: RunStatus = RunStatus.PENDING
    error: str | None = None
    http_status: int | None = None
    sparse_pages: list[int] = Field(default_factory=list)


class Manifest(BaseModel):
    execute: bool
    settings: storage.Settings
    request_fingerprint: str
    papers: list[PaperJob]
    workers: int = DEFAULT_WORKERS
    bibliography_sources: list[str] = Field(default_factory=list)
    tokens_per_minute: int | None = None


@dataclass
class JobResult:
    index: int
    job: PaperJob
    folder: Path
    record: models.PaperRecord | None


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def request_fingerprint(settings: storage.Settings) -> str:
    return storage.fingerprint({'settings': settings.model_dump(), 'schema': models.ExtractionPaper.model_json_schema(),
                                'prompt': prompts.INSTRUCTIONS, 'schema_version': models.SCHEMA_VERSION,
                                'prompt_version': models.PROMPT_VERSION})


def plan_jobs(input_directory: Path, limit: int, associations: dict[str, str]) -> list[PaperJob]:
    files = sorted(path for path in input_directory.rglob('*') if path.is_file() and path.suffix.lower() == '.pdf')
    if not files:
        raise ValueError('No PDFs found in input directory')
    jobs = []
    for path in files[:limit]:
        source = path.relative_to(input_directory).as_posix()
        digest = storage.digest_bytes(path.read_bytes())
        bibliography_id = associations.get(source)
        internal_id = bibliography_id or f'{INTERNAL_SOURCE_ID_PREFIX}{digest}'
        paper_id = bibliography_id or citation_keys.from_filename(source, digest) or citation_keys.make_key(title=path.stem, year=None, source_sha256=digest)
        jobs.append(PaperJob(source=source, paper_id=paper_id, bibliography_id=bibliography_id, sha256=digest,
                             directory=storage.digest_bytes(internal_id.encode())[:DIRECTORY_HASH_CHARACTERS]))
    identities = {job.bibliography_id or job.sha256 for job in jobs}
    if len(identities) != len(jobs):
        raise ValueError('Multiple selected PDFs share a paper ID; select one document per study or fix the source map')
    return jobs


def initialize_run(run: Path, manifest: Manifest, resume: bool) -> None:
    if resume:
        previous = Manifest.model_validate_json((run / storage.MANIFEST_FILE).read_text())
        expected = [(p.source, p.directory, p.sha256) for p in manifest.papers]
        actual = [(p.source, p.directory, p.sha256) for p in previous.papers]
        if previous.execute != manifest.execute or previous.request_fingerprint != manifest.request_fingerprint or actual != expected:
            raise ValueError('Resume mode, settings, schema, prompt, source IDs or selected documents changed')
    else:
        run.mkdir(parents=True, exist_ok=False)
    storage.write_json(run / storage.SETTINGS_FILE, manifest.settings)
    storage.write_json(run / storage.SCHEMA_FILE, models.ExtractionPaper.model_json_schema())
    (run / storage.PROMPT_FILE).write_text(prompts.INSTRUCTIONS, encoding='utf-8')
    storage.write_json(run / storage.MANIFEST_FILE, manifest)


def cache_key(job: PaperJob, request_hash: str) -> str:
    return storage.fingerprint({'paper_id': job.bibliography_id or f'{INTERNAL_SOURCE_ID_PREFIX}{job.sha256}', 'source': job.source,
                                'sha256': job.sha256, 'request': request_hash})


def cached_record(folder: Path, job: PaperJob, request_hash: str,
                   entries: list[models.BibliographicMetadata] | None = None) -> models.PaperRecord | None:
    path = folder / storage.RECORD_FILE
    if not path.exists():
        return None
    record = models.PaperRecord.model_validate_json(path.read_text())
    validate_cached_record(record, job, request_hash)
    pages = json.loads((folder / storage.PAGES_FILE).read_text())
    if entries is not None:
        record.bibliography = bibliography.match_entry(entries, job.source, pages, job.bibliography_id)
    # Re-label cached records locally; preserve the paid response and provenance.
    record.paper_id = job.bibliography_id or (record.bibliography.citation_key if record.bibliography
        else citation_keys.from_paper(record.paper, job.source, job.sha256))
    record.experiment_ids = experiment_ids(record.paper_id, record.paper)
    record.review_issues = validation.review_issues(record.paper, pages)
    if record.experiment_design is not None:
        experiment_design.validate(record.experiment_design, len(record.paper.experiments))
        record.review_issues.extend(validation.design_issues(record.experiment_design, pages))
    record.review_issues.extend(validation.missing_assessment_issues(record.paper, record.missing_fields, pages))
    job.sparse_pages = [index for index, page in enumerate(pages, 1) if len(page.strip()) < storage.SPARSE_PAGE_CHARACTERS]
    storage.write_json(path, record)
    return record


def validate_cached_record(record: models.PaperRecord, job: PaperJob, request_hash: str) -> None:
    provenance = record.provenance
    if (provenance.source, provenance.source_sha256, provenance.request_fingerprint) != (job.source, job.sha256, request_hash):
        raise ValueError('Cached record provenance mismatch; inspect cache before proceeding')
    if job.bibliography_id and record.paper_id != job.bibliography_id:
        raise ValueError('Cached bibliography ID mismatch; inspect cache before proceeding')
    if record.experiment_ids != experiment_ids(record.paper_id, record.paper):
        raise ValueError('Cached experiment IDs do not match canonical record')


def experiment_ids(paper_id: str, paper: models.Paper | models.ExtractionPaper) -> list[str]:
    return [f'{paper_id}:E{index:0{EXPERIMENT_NUMBER_WIDTH}d}' for index in range(1, len(paper.experiments) + 1)]


def saved_paper(folder: Path, retry_failed: bool) -> models.ExtractionPaper | None:
    response_path = folder / storage.RESPONSE_FILE
    if not response_path.exists():
        return None
    response = json.loads(response_path.read_text())
    if response.get('status') == api.COMPLETED_STATUS:
        text = ''.join(part.get('text', '') for item in response.get('output', []) for part in item.get('content', []) if part.get('type') == 'output_text')
        try:
            return models.ExtractionPaper.model_validate_json(text)
        except ValueError:
            if not retry_failed:
                raise ValueError('Saved response cannot be parsed; inspect it or use --retry-failed') from None
    elif not retry_failed:
        raise ValueError('Saved response incomplete/refused; inspect it or use --retry-failed')
    archive = folder / f'response-{datetime.now(timezone.utc).strftime(RESPONSE_ARCHIVE_FORMAT)}.json'
    response_path.replace(archive)
    return None


def canonical_paper(paper: models.ExtractionPaper) -> models.Paper:
    # Legacy metadata slots stay empty; bibliography supplies metadata separately.
    missing_text = models.Extraction[str](value=None, other=[], raw_text=[], status=vocab.Status.NOT_REPORTED)
    missing_year = models.Extraction[int](value=None, other=[], raw_text=[], status=vocab.Status.NOT_REPORTED)
    return models.Paper(title=missing_text, doi=missing_text.model_copy(deep=True), publication_year=missing_year,
        method=paper.method, domain=paper.domain, limitations=paper.limitations, experiments=paper.experiments)


def make_record(job: PaperJob, paper: models.ExtractionPaper, pages: list[str], folder: Path,
                settings: storage.Settings, request_hash: str,
                metadata: models.BibliographicMetadata | None = None) -> models.PaperRecord:
    response = json.loads((folder / storage.RESPONSE_FILE).read_text())
    provenance = models.Provenance(model=response.get('model', settings.model), prompt_version=models.PROMPT_VERSION,
        schema_version=models.SCHEMA_VERSION, request_fingerprint=request_hash,
        extracted_at=utc_now(), source=job.source, source_sha256=job.sha256,
        page_numbering=models.PAGE_NUMBERING, response_id=response['id'])
    content = canonical_paper(paper)
    paper_id = job.bibliography_id or (metadata.citation_key if metadata
        else citation_keys.from_paper(content, job.source, job.sha256))
    design = paper.experiment_design
    if design is not None:
        experiment_design.validate(design, len(paper.experiments))
    issues = validation.review_issues(content, pages)
    if design is not None:
        issues.extend(validation.design_issues(design, pages))
    missing = paper.missing_fields
    issues.extend(validation.missing_assessment_issues(content, missing, pages))
    return models.PaperRecord(paper_id=paper_id, experiment_ids=experiment_ids(paper_id, paper),
                             provenance=provenance, paper=content,
                             review_issues=issues, experiment_design=design, missing_fields=missing, bibliography=metadata)


def extract_job(job: PaperJob, folder: Path, input_directory: Path, settings: storage.Settings,
                request_hash: str, execute: bool, retry_failed: bool,
                preparation_lock: LockType | None = None,
                entries: list[models.BibliographicMetadata] | None = None,
                pacer: admission.RequestPacer | None = None) -> models.PaperRecord | None:
    folder.mkdir(parents=True, exist_ok=True)
    if execute:
        record = cached_record(folder, job, request_hash, entries)
        if record:
            progress.log('Reusing completed extraction from cache; no API request needed.')
            return mark_extracted(job, record)
    # pypdf's process-wide warning logger requires serialized preparation.
    with preparation_lock if preparation_lock is not None else nullcontext():
        pages, text = prepare_job(job, folder, input_directory, settings)
    if not execute:
        return None
    metadata = bibliography.match_entry(entries or [], job.source, pages, job.bibliography_id)
    paper = recover_or_request_paper(folder, settings, text, retry_failed, source=job.source, pacer=pacer)
    record = make_record(job, paper, pages, folder, settings, request_hash, metadata)
    storage.write_json(folder / storage.RECORD_FILE, record)
    return mark_extracted(job, record)


def prepare_job(job: PaperJob, folder: Path, input_directory: Path,
                settings: storage.Settings) -> tuple[list[str], str]:
    progress.log('Preparing PDF text...')
    pages, text = pdf_text.prepare(input_directory / job.source, folder, settings.max_input_characters)
    job.sparse_pages = [i for i, page in enumerate(pages, 1) if len(page.strip()) < storage.SPARSE_PAGE_CHARACTERS]
    progress.log(f'Prepared {len(pages)} pages, {len(text):,} characters.')
    job.status = RunStatus.PREPARED
    return pages, text


def recover_or_request_paper(folder: Path, settings: storage.Settings, text: str,
                             retry_failed: bool, *, source: str | None = None,
                             pacer: admission.RequestPacer | None = None) -> models.ExtractionPaper:
    # Recover a completed paid response before considering a new request.
    paper = saved_paper(folder, retry_failed)
    if paper is None:
        return api.request_paper(settings, text, folder, source, pacer)
    progress.log('Recovering a saved API response; no new API request needed.')
    return paper


def mark_extracted(job: PaperJob, record: models.PaperRecord) -> models.PaperRecord:
    job.paper_id = record.paper_id
    job.status = RunStatus.EXTRACTED
    return record


def process_jobs(manifest: Manifest, run: Path, input_directory: Path,
                 cache: Path, retry_failed: bool,
                 entries: list[models.BibliographicMetadata] | None = None) -> int:
    """Keep requests bounded; only the coordinator writes shared run artifacts."""
    records: list[models.PaperRecord] = []
    preparation_lock = Lock()
    pacer = admission.RequestPacer(manifest.tokens_per_minute) if manifest.tokens_per_minute is not None else None
    initial_count = min(manifest.workers, len(manifest.papers))
    indices = iter(range(initial_count, len(manifest.papers)))
    with ThreadPoolExecutor(max_workers=manifest.workers) as executor:
        def submit(index: int) -> Future[JobResult]:
            return executor.submit(process_job, index, manifest, run, input_directory,
                                   cache, retry_failed, preparation_lock, entries, pacer)

        active = {submit(index) for index in range(initial_count)}
        while active:
            completed, active = wait(active, return_when=FIRST_COMPLETED)
            for future in completed:
                save_result(future.result(), manifest, run, records)
                index = next(indices, None)
                if index is not None:
                    active.add(submit(index))
    return int(any(job.status == RunStatus.ERROR for job in manifest.papers))


def process_job(index: int, manifest: Manifest, run: Path, input_directory: Path,
                cache: Path, retry_failed: bool, preparation_lock: LockType,
                entries: list[models.BibliographicMetadata] | None = None,
                pacer: admission.RequestPacer | None = None) -> JobResult:
    # Workers mutate private job copies and distinct cache folders only.
    job = manifest.papers[index].model_copy(deep=True)
    progress.log(f'[{index + 1}/{len(manifest.papers)}] {job.source}')
    folder = cache / cache_key(job, manifest.request_fingerprint)
    record = None
    try:
        record = recovered_run_record(run / job.directory, job, manifest.request_fingerprint)
        if record is not None:
            progress.log(f'Reusing reviewed recovery for {job.source}; no API request needed.')
            return JobResult(index, mark_recovered_job(job, record), run / job.directory, record)
        restore_checkpoint(run / job.directory, folder)
        record = extract_job(job, folder, input_directory, manifest.settings,
            manifest.request_fingerprint, manifest.execute, retry_failed, preparation_lock, entries, pacer)
    except Exception as exc:
        mark_failed(job, exc)
    return JobResult(index, job, folder, record)


def mark_recovered_job(job: PaperJob, record: models.PaperRecord) -> PaperJob:
    mark_extracted(job, record)
    job.error, job.http_status = None, None
    return job


def recovered_run_record(folder: Path, job: PaperJob, request_hash: str) -> models.PaperRecord | None:
    path = folder / storage.RECORD_FILE
    if not path.exists():
        return None
    record = models.PaperRecord.model_validate_json(path.read_text())
    if record.recovery is None:
        return None
    if record.recovery.run_request_fingerprint != request_hash:
        raise ValueError('Recovered record belongs to different run settings')
    # The audit explicitly permits a retry with its own, preserved fingerprint.
    validate_cached_record(record, job, record.provenance.request_fingerprint)
    return record


def save_result(result: JobResult, manifest: Manifest, run: Path,
                records: list[models.PaperRecord]) -> None:
    if result.record is not None:
        if any(existing.paper_id == result.record.paper_id for existing in records):
            mark_failed(result.job, ValueError('Citation key collision; supply distinct bibliography IDs with --source-map'))
        else:
            records.append(result.record)
    manifest.papers[result.index] = result.job
    progress.log('Saving checkpoint, workbook and coverage reports...')
    checkpoint(manifest, run, result.job, result.folder, records)
    progress.log(f'[{result.index + 1}/{len(manifest.papers)}] {result.job.status.value}: {result.job.paper_id}')


def mark_failed(job: PaperJob, error: Exception) -> None:
    job.status = RunStatus.ERROR
    # Avoid exception messages that may echo source text or credentials.
    job.error = str(error) if isinstance(error, ValueError) and not isinstance(error, ValidationError) else type(error).__name__
    job.http_status = getattr(error, 'status_code', None)
    progress.log(f'Failed: {job.error}; inspect manifest.json for details.')


def restore_checkpoint(previous: Path, folder: Path) -> None:
    if previous.exists() and not (folder / storage.RECORD_FILE).exists():
        if not (folder / storage.RESPONSE_FILE).exists():
            shutil.copytree(previous, folder, dirs_exist_ok=True)


def checkpoint(manifest: Manifest, run: Path, job: PaperJob, folder: Path,
               records: list[models.PaperRecord]) -> None:
    if folder.exists() and folder.resolve() != (run / job.directory).resolve():
        shutil.copytree(folder, run / job.directory, dirs_exist_ok=True)
    storage.write_json(run / storage.MANIFEST_FILE, manifest)
    spreadsheet.export_workbook(records, run / storage.WORKBOOK_FILE, pdf_drive_links=drive_links.load_links())
    reporting.write_coverage(run, records, len(manifest.papers),
                             sum(paper.status == RunStatus.ERROR for paper in manifest.papers))


def resolve_bibliography_paths(paths: list[Path] | None, resume: Path | None) -> list[Path]:
    if paths is not None:
        return paths
    if resume is None:
        return []
    saved = Manifest.model_validate_json((resume / storage.MANIFEST_FILE).read_text())
    return [Path(path) for path in saved.bibliography_sources]


def log_run(manifest: Manifest, run: Path) -> None:
    progress.log(f'Selected {len(manifest.papers)} PDFs; model: {manifest.settings.model}.')
    progress.log(f'Concurrent workers: {manifest.workers}; reasoning: {manifest.settings.reasoning_effort}.')
    if manifest.tokens_per_minute is not None:
        progress.log(f'Request pacing: {manifest.tokens_per_minute:,} tokens/minute '
                     f'with {1 - admission.RATE_LIMIT_UTILIZATION:.0%} reserve.')
    progress.log(f'Output: {run.resolve()}')
    progress.log('Mode: ' + ('API extraction with cache reuse' if manifest.execute else 'local preparation; no API calls'))


def resolve_token_rate(limit: int | None, resume: Path | None, workers: int) -> int | None:
    if limit is None and resume is not None:
        limit = Manifest.model_validate_json((resume / storage.MANIFEST_FILE).read_text()).tokens_per_minute
    if workers > MAXIMUM_UNPACED_WORKERS and limit is None:
        raise ValueError(f'More than {MAXIMUM_UNPACED_WORKERS} workers requires an explicit tokens_per_minute rate limit')
    if limit is not None and limit <= 0:
        raise ValueError('tokens_per_minute must be positive')
    return limit


def main(*, input_directory: Path, settings_path: Path, limit: int, execute: bool,
         resume: Path | None, output_directory: Path, source_map: Path | None,
         retry_failed: bool, model: str | None = None, workers: int = DEFAULT_WORKERS,
         bibliography_paths: list[Path] | None = None, tokens_per_minute: int | None = None) -> int:
    if not 1 <= workers <= MAXIMUM_WORKERS:
        raise ValueError(f'workers must be between 1 and {MAXIMUM_WORKERS}')
    tokens_per_minute = resolve_token_rate(tokens_per_minute, resume, workers)
    progress.log(f'Starting SLR extraction; discovering PDFs in {input_directory}...')
    settings = storage.load_settings(settings_path, model=model)
    bibliography_paths = resolve_bibliography_paths(bibliography_paths, resume)
    entries = bibliography.load_entries(bibliography_paths)
    jobs = plan_jobs(input_directory, limit, storage.load_associations(source_map))
    manifest = Manifest(execute=execute, settings=settings,
                        request_fingerprint=request_fingerprint(settings), papers=jobs, workers=workers,
                        bibliography_sources=[str(path.resolve()) for path in bibliography_paths or []],
                        tokens_per_minute=tokens_per_minute)
    run = resume or output_directory / datetime.now(timezone.utc).strftime(RUN_NAME_FORMAT)
    initialize_run(run, manifest, resume is not None)
    log_run(manifest, run)
    # A shared versioned cache also reuses completed work across new runs.
    result = process_jobs(manifest, run, input_directory, output_directory / storage.CACHE_DIRECTORY, retry_failed, entries)
    progress.log(f'Processed {len(jobs)} PDFs. Workbook: {(run / storage.WORKBOOK_FILE).resolve()}')
    if result:
        progress.log('Some papers failed; inspect manifest.json.')
    return result

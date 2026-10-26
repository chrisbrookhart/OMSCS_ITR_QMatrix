"""Checkpointed orchestration reusing local PDF preparation and Responses API."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
import json
from pathlib import Path
import shutil
from pydantic import BaseModel, Field, ValidationError
import api
import citation_keys
import models
import pdf_text
import prompts
import progress
import reporting
import spreadsheet
import storage
import validation


INTERNAL_SOURCE_ID_PREFIX = 'pdf-'
DIRECTORY_HASH_CHARACTERS = 24
EXPERIMENT_NUMBER_WIDTH = 3
RUN_NAME_FORMAT = '%Y%m%d_%H%M%S_%f_UTC'
RESPONSE_ARCHIVE_FORMAT = '%Y%m%dT%H%M%S%f'


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


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def request_fingerprint(settings: storage.Settings) -> str:
    return storage.fingerprint({'settings': settings.model_dump(), 'schema': models.Paper.model_json_schema(),
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
    storage.write_json(run / storage.SCHEMA_FILE, models.Paper.model_json_schema())
    (run / storage.PROMPT_FILE).write_text(prompts.INSTRUCTIONS, encoding='utf-8')
    storage.write_json(run / storage.MANIFEST_FILE, manifest)


def cache_key(job: PaperJob, request_hash: str) -> str:
    return storage.fingerprint({'paper_id': job.bibliography_id or f'{INTERNAL_SOURCE_ID_PREFIX}{job.sha256}', 'source': job.source,
                                'sha256': job.sha256, 'request': request_hash})


def cached_record(folder: Path, job: PaperJob, request_hash: str) -> models.PaperRecord | None:
    path = folder / storage.RECORD_FILE
    if not path.exists():
        return None
    record = models.PaperRecord.model_validate_json(path.read_text())
    validate_cached_record(record, job, request_hash)
    pages = json.loads((folder / storage.PAGES_FILE).read_text())
    # Re-label cached records locally; preserve the paid response and provenance.
    record.paper_id = job.bibliography_id or citation_keys.from_paper(record.paper, job.source, job.sha256)
    record.experiment_ids = experiment_ids(record.paper_id, record.paper)
    record.review_issues = validation.review_issues(record.paper, pages)
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


def experiment_ids(paper_id: str, paper: models.Paper) -> list[str]:
    return [f'{paper_id}:E{index:0{EXPERIMENT_NUMBER_WIDTH}d}' for index in range(1, len(paper.experiments) + 1)]


def saved_paper(folder: Path, retry_failed: bool) -> models.Paper | None:
    response_path = folder / storage.RESPONSE_FILE
    if not response_path.exists():
        return None
    response = json.loads(response_path.read_text())
    if response.get('status') == api.COMPLETED_STATUS:
        text = ''.join(part.get('text', '') for item in response.get('output', []) for part in item.get('content', []) if part.get('type') == 'output_text')
        try:
            return models.Paper.model_validate_json(text)
        except ValueError:
            if not retry_failed:
                raise ValueError('Saved response cannot be parsed; inspect it or use --retry-failed') from None
    elif not retry_failed:
        raise ValueError('Saved response incomplete/refused; inspect it or use --retry-failed')
    archive = folder / f'response-{datetime.now(timezone.utc).strftime(RESPONSE_ARCHIVE_FORMAT)}.json'
    response_path.replace(archive)
    return None


def make_record(job: PaperJob, paper: models.Paper, pages: list[str], folder: Path,
                settings: storage.Settings, request_hash: str) -> models.PaperRecord:
    response = json.loads((folder / storage.RESPONSE_FILE).read_text())
    provenance = models.Provenance(model=response.get('model', settings.model), prompt_version=models.PROMPT_VERSION,
        schema_version=models.SCHEMA_VERSION, request_fingerprint=request_hash,
        extracted_at=utc_now(), source=job.source, source_sha256=job.sha256,
        page_numbering=models.PAGE_NUMBERING, response_id=response['id'])
    paper_id = job.bibliography_id or citation_keys.from_paper(paper, job.source, job.sha256)
    return models.PaperRecord(paper_id=paper_id, experiment_ids=experiment_ids(paper_id, paper),
                             provenance=provenance, paper=paper,
                             review_issues=validation.review_issues(paper, pages))


def extract_job(job: PaperJob, folder: Path, input_directory: Path, settings: storage.Settings,
                request_hash: str, execute: bool, retry_failed: bool) -> models.PaperRecord | None:
    folder.mkdir(parents=True, exist_ok=True)
    if execute:
        record = cached_record(folder, job, request_hash)
        if record:
            progress.log('Reusing completed extraction from cache; no API request needed.')
            return mark_extracted(job, record)
    pages, text = prepare_job(job, folder, input_directory, settings)
    if not execute:
        return None
    paper = recover_or_request_paper(folder, settings, text, retry_failed)
    record = make_record(job, paper, pages, folder, settings, request_hash)
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
                             retry_failed: bool) -> models.Paper:
    # Recover a completed paid response before considering a new request.
    paper = saved_paper(folder, retry_failed)
    if paper is None:
        return api.request_paper(settings, text, folder)
    progress.log('Recovering a saved API response; no new API request needed.')
    return paper


def mark_extracted(job: PaperJob, record: models.PaperRecord) -> models.PaperRecord:
    job.paper_id = record.paper_id
    job.status = RunStatus.EXTRACTED
    return record


def process_jobs(manifest: Manifest, run: Path, input_directory: Path,
                 cache: Path, retry_failed: bool) -> int:
    records: list[models.PaperRecord] = []
    for index, job in enumerate(manifest.papers, 1):
        progress.log(f'[{index}/{len(manifest.papers)}] {job.source}')
        folder = cache / cache_key(job, manifest.request_fingerprint)
        try:
            restore_checkpoint(run / job.directory, folder)
            record = extract_job(job, folder, input_directory, manifest.settings,
                manifest.request_fingerprint, manifest.execute, retry_failed)
            if record:
                if any(existing.paper_id == record.paper_id for existing in records):
                    raise ValueError('Citation key collision; supply distinct bibliography IDs with --source-map')
                records.append(record)
        except Exception as exc:
            mark_failed(job, exc)
        finally:
            progress.log('Saving checkpoint, workbook and coverage reports...')
            checkpoint(manifest, run, job, folder, records)
            progress.log(f'[{index}/{len(manifest.papers)}] {job.status.value}: {job.paper_id}')
    return int(any(job.status == RunStatus.ERROR for job in manifest.papers))


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
    if folder.exists():
        shutil.copytree(folder, run / job.directory, dirs_exist_ok=True)
    storage.write_json(run / storage.MANIFEST_FILE, manifest)
    spreadsheet.export_workbook(records, run / storage.WORKBOOK_FILE)
    reporting.write_coverage(run, records, len(manifest.papers),
                             sum(paper.status == RunStatus.ERROR for paper in manifest.papers))


def main(*, input_directory: Path, settings_path: Path, limit: int, execute: bool,
         resume: Path | None, output_directory: Path, source_map: Path | None,
         retry_failed: bool, model: str | None = None) -> int:
    progress.log(f'Starting SLR extraction; discovering PDFs in {input_directory}...')
    settings = storage.load_settings(settings_path, model=model)
    jobs = plan_jobs(input_directory, limit, storage.load_associations(source_map))
    manifest = Manifest(execute=execute, settings=settings,
                        request_fingerprint=request_fingerprint(settings), papers=jobs)
    run = resume or output_directory / datetime.now(timezone.utc).strftime(RUN_NAME_FORMAT)
    initialize_run(run, manifest, resume is not None)
    progress.log(f'Selected {len(jobs)} PDFs; model: {settings.model}.')
    progress.log(f'Output: {run.resolve()}')
    progress.log('Mode: ' + ('API extraction with cache reuse' if execute else 'local preparation; no API calls'))
    # A shared versioned cache also reuses completed work across new runs.
    result = process_jobs(manifest, run, input_directory, output_directory / storage.CACHE_DIRECTORY, retry_failed)
    progress.log(f'Processed {len(jobs)} PDFs. Workbook: {(run / storage.WORKBOOK_FILE).resolve()}')
    if result:
        progress.log('Some papers failed; inspect manifest.json.')
    return result

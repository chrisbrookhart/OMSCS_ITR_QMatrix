"""Apply an explicit, audited local recovery or import a completed retry."""
import argparse
import json
from pathlib import Path

import bibliography
import models
import pipeline
import response_recovery as recovery
import storage

RECOVERY_REVIEW_NOTE = 'Saved extraction recovered locally; see the Recovery worksheet and recovery.json.'
UNRESOLVED_REVIEW_NOTE = 'Unavailable in the saved response; retained unknown during local recovery.'


def find_job(manifest: pipeline.Manifest, source: str) -> pipeline.PaperJob:
    matches = [job for job in manifest.papers if job.source == source]
    if len(matches) != 1:
        raise ValueError('Source must identify exactly one paper in the run')
    return matches[0]


def recovery_audit(manifest: pipeline.Manifest, response_path: Path,
                    actions: list[str], unresolved: list[str]) -> models.ResponseRecovery:
    response = recovery.load_response(response_path)
    return models.ResponseRecovery(recovered_at=pipeline.utc_now(),
        run_request_fingerprint=manifest.request_fingerprint, source_response_path=str(response_path.resolve()),
        source_response_sha256=storage.digest_bytes(response_path.read_bytes()), source_response_status=response.status,
        actions=actions, unresolved_fields=unresolved)


def add_recovery_notes(record: models.PaperRecord, audit: models.ResponseRecovery) -> None:
    record.recovery = audit
    record.review_issues.append(models.ReviewIssue(field='recovery', reason=RECOVERY_REVIEW_NOTE))
    record.review_issues.extend(models.ReviewIssue(field=path, reason=UNRESOLVED_REVIEW_NOTE)
                                for path in audit.unresolved_fields)


def save_recovery(run: Path, manifest: pipeline.Manifest, job: pipeline.PaperJob,
                   record: models.PaperRecord) -> None:
    if record.recovery is None:
        raise ValueError('Recovered records require an explicit audit')
    # Save the original manifest once; raw responses and shared caches stay intact.
    backup = run / recovery.BACKUP_DIRECTORY
    backup.mkdir(exist_ok=True)
    original = backup / storage.MANIFEST_FILE
    if not original.exists():
        original.write_bytes((run / storage.MANIFEST_FILE).read_bytes())
    folder = run / job.directory
    storage.write_json(folder / storage.RECORD_FILE, record)
    storage.write_json(folder / recovery.RECOVERY_FILE, record.recovery)
    pipeline.mark_recovered_job(job, record)
    storage.write_json(run / storage.MANIFEST_FILE, manifest)


def local_recovery(*, run: Path, source: str, mode: recovery.RecoveryMode) -> models.PaperRecord:
    manifest = pipeline.Manifest.model_validate_json((run / storage.MANIFEST_FILE).read_text())
    job = find_job(manifest, source)
    if job.status == pipeline.RunStatus.EXTRACTED:
        raise ValueError('Paper is already extracted; no recovery was applied')
    folder = run / job.directory
    response_path = folder / storage.RESPONSE_FILE
    recovered = recovery.recover_paper(recovery.output_text(recovery.load_response(response_path)), mode)
    entries = bibliography.load_entries([Path(path) for path in manifest.bibliography_sources])
    pages = json.loads((folder / storage.PAGES_FILE).read_text())
    metadata = bibliography.match_entry(entries, job.source, pages, job.bibliography_id)
    record = pipeline.make_record(job, recovered.paper, pages, folder, manifest.settings, manifest.request_fingerprint, metadata)
    audit = recovery_audit(manifest, response_path, recovered.actions, recovered.unresolved_fields)
    add_recovery_notes(record, audit)
    storage.write_json(folder / recovery.RECOVERED_PAYLOAD_FILE, recovered.paper)
    save_recovery(run, manifest, job, record)
    return record


def import_retry(*, run: Path, source: str, retry_run: Path) -> models.PaperRecord:
    manifest = pipeline.Manifest.model_validate_json((run / storage.MANIFEST_FILE).read_text())
    job = find_job(manifest, source)
    if job.status == pipeline.RunStatus.EXTRACTED:
        raise ValueError('Paper is already extracted; no retry was imported')
    retry_manifest = pipeline.Manifest.model_validate_json((retry_run / storage.MANIFEST_FILE).read_text())
    retry_job = find_job(retry_manifest, source)
    if retry_job.status != pipeline.RunStatus.EXTRACTED or retry_job.sha256 != job.sha256:
        raise ValueError('Retry must be complete and refer to the same source PDF')
    folder = retry_run / retry_job.directory
    record = models.PaperRecord.model_validate_json((folder / storage.RECORD_FILE).read_text())
    pipeline.validate_cached_record(record, job, retry_manifest.request_fingerprint)
    previous = record.recovery
    actions = previous.actions.copy() if previous else []
    unresolved = previous.unresolved_fields.copy() if previous else []
    actions.append(f'Imported completed retry from {retry_run}; retained the retry model/settings fingerprint.')
    audit = recovery_audit(manifest, folder / storage.RESPONSE_FILE, actions, unresolved)
    add_recovery_notes(record, audit)
    save_recovery(run, manifest, job, record)
    return record


def get_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('--source', required=True)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument('--mode', type=recovery.RecoveryMode,
                           choices=[mode.value for mode in recovery.RecoveryMode])
    selection.add_argument('--retry-run', type=Path)
    return parser


def main() -> None:
    arguments = get_parser().parse_args()
    if arguments.retry_run is not None:
        record = import_retry(run=arguments.run, source=arguments.source, retry_run=arguments.retry_run)
    else:
        record = local_recovery(run=arguments.run, source=arguments.source, mode=arguments.mode)
    print(f'Recovered {record.provenance.source}; {len(record.review_issues)} review notes retained.')


if __name__ == '__main__':
    main()

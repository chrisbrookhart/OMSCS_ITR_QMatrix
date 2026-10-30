"""Rebuild an extraction workbook from saved canonical JSON without API calls."""
import argparse
import json
from pathlib import Path
import bibliography
import drive_links
import models
import pipeline
import reporting
import spreadsheet
import storage


def get_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('--bibliography', nargs='+', type=Path)
    parser.add_argument('--output', type=Path, help='Write a separate workbook instead of replacing extraction.xlsx.')
    parser.add_argument('--pdf-drive-links', type=Path,
                        help=f'Filename-to-Drive URL JSON (default when present: {drive_links.DEFAULT_LINKS_PATH}).')
    return parser


def attach_bibliography(run: Path, manifest: pipeline.Manifest, records: list[models.PaperRecord],
                         paths: list[Path]) -> None:
    if paths:
        entries = bibliography.load_entries(paths)
        jobs = {job.source: job for job in manifest.papers}
        for record in records:
            job = jobs[record.provenance.source]
            pages = json.loads((run / job.directory / storage.PAGES_FILE).read_text())
            record.bibliography = bibliography.match_entry(entries, job.source, pages, job.bibliography_id)
        storage.write_json(run / bibliography.METADATA_FILE,
                           [record.bibliography.model_dump(mode='json') if record.bibliography else None for record in records])
        manifest.bibliography_sources = [str(path.resolve()) for path in paths]
        storage.write_json(run / storage.MANIFEST_FILE, manifest)


def main(*, run: Path, bibliography_paths: list[Path] | None = None, output: Path | None = None,
          pdf_drive_links_path: Path | None = None) -> None:
    manifest = pipeline.Manifest.model_validate_json((run / storage.MANIFEST_FILE).read_text())
    records = [models.PaperRecord.model_validate_json((run / paper.directory / storage.RECORD_FILE).read_text())
               for paper in manifest.papers if paper.status == pipeline.RunStatus.EXTRACTED]
    paths = bibliography_paths if bibliography_paths is not None else [Path(path) for path in manifest.bibliography_sources]
    attach_bibliography(run, manifest, records, paths)
    spreadsheet.export_workbook(records, output or run / storage.WORKBOOK_FILE,
                                pdf_drive_links=drive_links.load_links(pdf_drive_links_path))
    reporting.write_coverage(run, records, len(manifest.papers),
                             sum(paper.status == pipeline.RunStatus.ERROR for paper in manifest.papers))


if __name__ == '__main__':
    arguments = get_parser().parse_args()
    main(run=arguments.run, bibliography_paths=arguments.bibliography, output=arguments.output,
         pdf_drive_links_path=arguments.pdf_drive_links)

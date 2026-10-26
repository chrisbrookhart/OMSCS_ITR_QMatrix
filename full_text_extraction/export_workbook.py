"""Rebuild an extraction workbook from saved canonical JSON without API calls."""
import argparse
from pathlib import Path
import models
import pipeline
import reporting
import spreadsheet
import storage


def get_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    return parser


def main(*, run: Path) -> None:
    manifest = pipeline.Manifest.model_validate_json((run / storage.MANIFEST_FILE).read_text())
    records = [models.PaperRecord.model_validate_json((run / paper.directory / storage.RECORD_FILE).read_text())
               for paper in manifest.papers if paper.status == pipeline.RunStatus.EXTRACTED]
    spreadsheet.export_workbook(records, run / storage.WORKBOOK_FILE)
    reporting.write_coverage(run, records, len(manifest.papers),
                             sum(paper.status == pipeline.RunStatus.ERROR for paper in manifest.papers))


if __name__ == '__main__':
    main(run=get_parser().parse_args().run)

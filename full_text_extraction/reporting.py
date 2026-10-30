"""Coverage counts for review, without interpreting missing data as findings."""
from collections import Counter
import csv
from pathlib import Path
import re
from pydantic import BaseModel
import models
import bibliography
import storage
import validation
import vocabulary as vocab

COVERAGE_JSON = 'coverage.json'
COVERAGE_CSV = 'coverage.csv'


class FieldCoverage(BaseModel):
    field: str
    observations: int
    extracted: int
    not_reported: int
    not_applicable: int
    ambiguous: int
    flagged: int


def field_coverage(records: list[models.PaperRecord]) -> list[FieldCoverage]:
    counts: dict[str, Counter[str]] = {}
    for record in records:
        flagged = {issue.field for issue in record.review_issues}
        for path, field in validation.fields_in(record.paper):
            if path in bibliography.METADATA_PATHS:
                continue
            # Array indexes are grouped; counts describe field observations, not papers.
            name = re.sub(r'\[\d+\]', '[]', path)
            count = counts.setdefault(name, Counter())
            count[field.status.value] += 1
            count['flagged'] += int(path in flagged)
    return [coverage_row(name, count) for name, count in sorted(counts.items())]


def coverage_row(name: str, count: Counter[str]) -> FieldCoverage:
    return FieldCoverage(field=name, observations=sum(count[status.value] for status in vocab.Status),
        extracted=count[vocab.Status.EXTRACTED.value], not_reported=count[vocab.Status.NOT_REPORTED.value],
        not_applicable=count[vocab.Status.NOT_APPLICABLE.value], ambiguous=count[vocab.Status.AMBIGUOUS.value],
        flagged=count['flagged'])


def write_coverage(run: Path, records: list[models.PaperRecord], selected: int, failed: int) -> None:
    rows = field_coverage(records)
    storage.write_json(run / COVERAGE_JSON, {
        'selected_papers': selected, 'extracted_papers': len(records), 'failed_papers': failed,
        'experiments': sum(len(record.paper.experiments) for record in records),
        'fields': [row.model_dump() for row in rows],
        'interpretation': 'Field-observation counts, not study prevalence or validated accuracy; empty arrays contribute no observations.'})
    path = run / COVERAGE_CSV
    temporary = path.with_suffix('.tmp')
    with temporary.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(FieldCoverage.model_fields))
        writer.writeheader()
        writer.writerows(row.model_dump() for row in rows)
    temporary.replace(path)

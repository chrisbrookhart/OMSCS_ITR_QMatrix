"""Non-destructive field and quote checks; issues remain attached for review."""
from __future__ import annotations

import re
from typing import Iterator
from pydantic import BaseModel
import models
import vocabulary as vocab

COUNT_FIELDS = ('sample_size', 'number_of_items', 'number_of_attributes')
SINGLE_CATEGORY_FIELDS = ('data_type', 'response_type')


def normalize(text: str) -> str:
    return re.sub(r'\s+', ' ', text).strip()


def fields_in(record: BaseModel, prefix: str = '') -> Iterator[tuple[str, models.Extraction[object]]]:
    for name in type(record).model_fields:
        value = getattr(record, name)
        path = f'{prefix}.{name}' if prefix else name
        if isinstance(value, models.Extraction):
            yield path, value
        elif isinstance(value, BaseModel):
            yield from fields_in(value, path)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                if isinstance(child, BaseModel):
                    yield from fields_in(child, f'{path}[{index}]')


def quote_issues(field: models.Extraction[object], pages: list[str]) -> list[str]:
    issues = []
    for evidence in field.raw_text:
        quote = normalize(evidence.text)
        if evidence.page is None or not 1 <= evidence.page <= len(pages):
            issues.append('Evidence page unknown or outside PDF; manual review required')
        elif not quote or quote not in normalize(pages[evidence.page - 1]):
            issues.append(f'Quotation not verified on physical PDF page {evidence.page}')
        if not evidence.location:
            issues.append('Evidence location missing; manual review required')
    return issues


def numeric_issues(name: str, setting: models.NumericSetting) -> list[str]:
    values = list(setting.values)
    issues = []
    bounds = setting.range
    if bounds:
        values.extend(value for value in (bounds.minimum, bounds.maximum) if value is not None)
        if bounds.minimum is not None and bounds.maximum is not None and bounds.minimum > bounds.maximum:
            issues.append('Numeric range reversed')
    if not values:
        issues.append('Numeric condition has no values or range bounds')
    if name in COUNT_FIELDS and any(value < 0 or int(value) != value for value in values):
        issues.append('Counts must be nonnegative integers')
    if name == 'misspecification':
        limit = 100 if setting.unit in ('percent', 'percentage', '%') else 1
        if setting.unit not in ('percent', 'percentage', '%', 'proportion'):
            issues.append('Misspecification unit needs review')
        elif any(not 0 <= value <= limit for value in values):
            issues.append('Misspecification outside reported unit bounds')
    return issues


def field_issues(path: str, field: models.Extraction[object], pages: list[str]) -> list[str]:
    issues = quote_issues(field, pages)
    present = field.value is not None or bool(field.other)
    if present and not field.raw_text:
        issues.append('Value without source evidence')
    if field.status == vocab.Status.EXTRACTED and field.value is None:
        issues.append('Extracted status without primary value')
    if field.status in (vocab.Status.NOT_REPORTED, vocab.Status.NOT_APPLICABLE) and present:
        issues.append('Missing/inapplicable status conflicts with supplied values')
    if field.status == vocab.Status.AMBIGUOUS:
        issues.append('Reported but ambiguous; manual review required')
    name = path.rsplit('.', 1)[-1]
    if name in SINGLE_CATEGORY_FIELDS and field.other:
        issues.append('Mutually exclusive category has secondary values')
    for value in [field.value, *field.other]:
        if isinstance(value, models.NumericSetting):
            issues.extend(numeric_issues(name, value))
    return issues


def review_issues(paper: models.Paper, pages: list[str]) -> list[models.ReviewIssue]:
    return [models.ReviewIssue(field=path, reason=reason)
            for path, field in fields_in(paper)
            for reason in field_issues(path, field, pages)]

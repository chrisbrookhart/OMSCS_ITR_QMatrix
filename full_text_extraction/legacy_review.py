"""Historical flat-pilot review compatibility; never makes API requests."""
from __future__ import annotations

import json
from typing import TypedDict, cast
from validation import normalize
import storage

REPORTED = 'reported'
MISSING_STATUSES = ('not_reported', 'not_applicable')
COUNT_FIELDS = ('sample_size', 'number_of_items', 'number_of_attributes')
SIMULATION_FIELDS = ('simulation_misspecification_proportion', 'simulation_item_quality')


class LegacyEvidence(TypedDict):
    page: int
    quote: str


class LegacyObservation(TypedDict):
    condition: str
    measure: str
    unit: str
    values: list[int | float]
    minimum: int | float | None
    maximum: int | float | None


class LegacyField(TypedDict, total=False):
    status: str
    value: str | None
    evidence: list[LegacyEvidence]
    codes: list[str]
    typed_value: str | int | list[str] | list[LegacyObservation] | None


class LegacyDefinition(TypedDict, total=False):
    value_type: str
    codes: list[str]
    description: str


def status_warnings(name: str, field: LegacyField) -> list[str]:
    warnings = []
    status, typed = field['status'], field.get('typed_value')
    if status == REPORTED and (not field['value'] or not field['evidence']):
        warnings.append(f'{name}: reported without value/evidence')
    if status in MISSING_STATUSES and (field['value'] is not None or field['evidence'] or field.get('codes')):
        warnings.append(f'{name}: inconsistent {status} status')
    if 'codes' in field and status == REPORTED and not field['codes']:
        warnings.append(f'{name}: reported categorical field without a code')
    if status != REPORTED and typed is not None:
        warnings.append(f'{name}: typed value supplied for nonreported status')
    if 'typed_value' in field and status == REPORTED and typed is None:
        warnings.append(f'{name}: reported without typed value')
    if status == 'unclear':
        warnings.append(f'{name}: unclear; review required')
    return warnings


def observation_warnings(name: str, observation: LegacyObservation) -> list[str]:
    warnings = []
    low, high = observation['minimum'], observation['maximum']
    if low is not None and high is not None and low > high:
        warnings.append(f'{name}: numeric range reversed')
    values = observation['values'] + [value for value in (low, high) if value is not None]
    if name in COUNT_FIELDS and any(value < 0 for value in values):
        warnings.append(f'{name}: negative count')
    if name == SIMULATION_FIELDS[0] and (observation['unit'] != 'proportion' or any(not 0 <= value <= 1 for value in values)):
        warnings.append(f'{name}: invalid normalized proportion')
    return warnings


def definition_warnings(name: str, field: LegacyField, definition: str | LegacyDefinition,
                        result: dict[str, LegacyField]) -> list[str]:
    warnings = []
    if isinstance(definition, dict) and definition.get('value_type') == 'enum_list' and field['status'] == REPORTED and not field.get('typed_value'):
        warnings.append(f'{name}: reported categorical field without enum values')
    if field['status'] == MISSING_STATUSES[1]:
        data = result.get('data_type', {}).get('typed_value') or []
        if name not in SIMULATION_FIELDS:
            warnings.append(f'{name}: applicability requires human review; not treated as structural missingness')
        elif 'simulated' in data:
            warnings.append(f'{name}: marked not_applicable despite simulated data')
    return warnings


def quote_warnings(name: str, evidence: list[LegacyEvidence], pages: list[str]) -> list[str]:
    warnings = []
    for passage in evidence:
        page, quote = passage['page'], normalize(passage['quote'])
        if not 1 <= page <= len(pages) or not quote or quote not in pages[page - 1]:
            located = [index for index, text in enumerate(pages, 1) if quote and quote in text]
            suffix = f'; exact quote found on pages {located}' if located else '; no exact match on any page'
            warnings.append(f'{name}: evidence quote not found on PDF page {page}' + suffix)
    return warnings


def evidence_warnings(result: dict[str, LegacyField], pages: list[str],
                      definitions: dict[str, str | LegacyDefinition] | None = None) -> list[str]:
    warnings = []
    normalized_pages = [normalize(page) for page in pages]
    for name, field in result.items():
        warnings.extend(status_warnings(name, field))
        typed = field.get('typed_value')
        if isinstance(typed, list) and typed and isinstance(typed[0], dict):
            for observation in cast(list[LegacyObservation], typed):
                warnings.extend(observation_warnings(name, observation))
        if definitions:
            warnings.extend(definition_warnings(name, field, definitions.get(name, {}), result))
        warnings.extend(quote_warnings(name, field['evidence'], normalized_pages))
    return warnings


def append_review_rows(rows: list[dict[str, storage.JsonValue]], entry: dict[str, storage.JsonValue],
                       result: dict[str, LegacyField]) -> None:
    for name, field in result.items():
        warnings = cast(list[str], entry.get('review_warnings', []))
        rows.append({'source': entry['source'], 'field': name, 'status': field['status'],
                     'value': field['value'], 'typed_value': json.dumps(field.get('typed_value', field.get('codes')), ensure_ascii=False),
                     'evidence': json.dumps(field['evidence'], ensure_ascii=False),
                     'review_warnings': '; '.join(warnings)})

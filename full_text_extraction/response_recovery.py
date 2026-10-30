"""Recover complete saved JSON fields without guessing truncated scientific data."""
from dataclasses import dataclass
from enum import Enum
import json
from pathlib import Path
from pydantic import BaseModel, Field

import experiment_design
import models
import storage
import vocabulary as vocab

EXPERIMENTS_KEY = 'experiments'
DESIGN_KEY = 'experiment_design'
MISSING_FIELDS_KEY = 'missing_fields'
WHITESPACE = ' \t\r\n'
RECOVERY_FILE = 'recovery.json'
RECOVERED_PAYLOAD_FILE = 'recovered_payload.json'
BACKUP_DIRECTORY = 'recovery_original'


class RecoveryMode(str, Enum):
    DEDUPLICATE_ROLES = 'deduplicate_roles'
    COMPLETE_ROLES = 'complete_roles'
    RECOVER_NOTES = 'recover_notes'
    RECOVER_DESIGN = 'recover_design'


class TextPart(BaseModel):
    type: str
    text: str | None = None


class OutputItem(BaseModel):
    content: list[TextPart] | None = None


class SavedResponse(BaseModel):
    id: str
    status: str
    output: list[OutputItem] = Field(default_factory=list)


@dataclass
class JsonPrefix:
    fields: dict[str, storage.JsonValue]
    incomplete_field: str | None = None
    array_items: list[storage.JsonValue] | None = None


@dataclass
class RecoveredPaper:
    paper: models.ExtractionPaper
    actions: list[str]
    unresolved_fields: list[str]


def output_text(response: SavedResponse) -> str:
    return ''.join(part.text or '' for item in response.output for part in item.content or []
                   if part.type == 'output_text')


def skip_space(text: str, position: int) -> int:
    while position < len(text) and text[position] in WHITESPACE:
        position += 1
    return position


def read_key(text: str, position: int) -> tuple[str, int]:
    key, end = json.JSONDecoder().raw_decode(text, skip_space(text, position))
    if not isinstance(key, str):
        raise ValueError('JSON property name is not a string')
    colon = skip_space(text, end)
    if colon >= len(text) or text[colon] != ':':
        raise ValueError('JSON property has no colon')
    return key, skip_space(text, colon + 1)


def complete_array_items(text: str, position: int) -> list[storage.JsonValue]:
    items: list[storage.JsonValue] = []
    if position >= len(text) or text[position] != '[':
        return items
    position = skip_space(text, position + 1)
    while position < len(text) and text[position] != ']':
        try:
            value, end = json.JSONDecoder().raw_decode(text, position)
        except json.JSONDecodeError:
            break
        items.append(value)
        position = skip_space(text, end)
        if position >= len(text) or text[position] != ',':
            break
        position = skip_space(text, position + 1)
    return items


def complete_properties(text: str) -> JsonPrefix:
    position = skip_space(text, 0)
    if position >= len(text) or text[position] != '{':
        raise ValueError('Saved output does not start with a JSON object')
    result = JsonPrefix({})
    position = skip_space(text, position + 1)
    while position < len(text) and text[position] != '}':
        key, start = read_key(text, position)
        if key in result.fields:
            raise ValueError('Duplicate JSON property; automatic recovery refused')
        try:
            value, end = json.JSONDecoder().raw_decode(text, start)
        except json.JSONDecodeError:
            return JsonPrefix(result.fields, key, complete_array_items(text, start))
        result.fields[key] = value
        position = skip_space(text, end)
        if position >= len(text) or text[position] != ',':
            break
        position = skip_space(text, position + 1)
    return result


def unknown_assignment(number: int) -> models.ExperimentAssignment:
    return models.ExperimentAssignment(experiment_number=number, role=models.ExperimentRole.UNCLEAR,
        rationale=models.Extraction[str](value=None, other=[], raw_text=[], status=vocab.Status.NOT_REPORTED))


def unique_assignments(design: models.ExperimentDesign, actions: list[str]) -> None:
    unique: dict[int, models.ExperimentAssignment] = {}
    for assignment in design.assignments:
        number = assignment.experiment_number
        previous = unique.get(number)
        if previous is not None and previous != assignment:
            raise ValueError('Conflicting experiment roles require manual review')
        if previous is not None:
            actions.append(f'Removed an exactly duplicated role assignment for experiment {number}.')
        unique[number] = assignment
    design.assignments = list(unique.values())


def complete_roles(paper: models.ExtractionPaper, actions: list[str], unresolved: list[str]) -> None:
    present = {item.experiment_number for item in paper.experiment_design.assignments}
    for number in range(1, len(paper.experiments) + 1):
        if number not in present:
            paper.experiment_design.assignments.append(unknown_assignment(number))
            actions.append(f'Role for experiment {number} was absent; retained as unclear without invented rationale.')
            unresolved.append(f'experiment_design.assignments[{number - 1}].role')
    paper.experiment_design.assignments.sort(key=lambda item: item.experiment_number)


def complete_payload(prefix: JsonPrefix, mode: RecoveryMode) -> tuple[dict[str, storage.JsonValue], list[str]]:
    fields = dict(prefix.fields)
    actions = []
    if EXPERIMENTS_KEY not in fields:
        raise ValueError('Experimental content is incomplete; a new extraction is required')
    if mode in (RecoveryMode.RECOVER_NOTES, RecoveryMode.RECOVER_DESIGN):
        if prefix.incomplete_field == MISSING_FIELDS_KEY:
            fields[MISSING_FIELDS_KEY] = prefix.array_items or []
            actions.append('Preserved complete missing-field assessments; discarded the unfinished assessment tail.')
        elif MISSING_FIELDS_KEY not in fields:
            fields[MISSING_FIELDS_KEY] = []
            actions.append('Missing-field explanations were not completed; reasons remain unknown.')
    if mode == RecoveryMode.RECOVER_DESIGN and DESIGN_KEY not in fields:
        fields[DESIGN_KEY] = {'primary_experiment_number': None, 'assignments': []}
        actions.append('Experiment design was unfinished; no main experiment was inferred.')
    return fields, actions


def recover_paper(text: str, mode: RecoveryMode) -> RecoveredPaper:
    prefix = complete_properties(text)
    payload, actions = complete_payload(prefix, mode)
    paper = models.ExtractionPaper.model_validate_json(json.dumps(payload))
    unresolved: list[str] = []
    unique_assignments(paper.experiment_design, actions)
    if mode in (RecoveryMode.COMPLETE_ROLES, RecoveryMode.RECOVER_DESIGN):
        complete_roles(paper, actions, unresolved)
    if prefix.incomplete_field == MISSING_FIELDS_KEY or mode == RecoveryMode.RECOVER_DESIGN:
        unresolved.append(MISSING_FIELDS_KEY)
    if mode == RecoveryMode.RECOVER_DESIGN:
        unresolved.append(DESIGN_KEY)
    experiment_design.validate(paper.experiment_design, len(paper.experiments))
    return RecoveredPaper(paper, actions, unresolved)


def load_response(path: Path) -> SavedResponse:
    return SavedResponse.model_validate_json(path.read_text(encoding='utf-8'))

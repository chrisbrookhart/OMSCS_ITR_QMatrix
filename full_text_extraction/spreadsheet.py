"""Review and analysis worksheets derived from the same canonical records."""
from __future__ import annotations

import json
from pathlib import Path
from openpyxl import Workbook
from openpyxl.cell.cell import Cell, ILLEGAL_CHARACTERS_RE
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet
from pydantic import BaseModel
import models
import vocabulary as vocab

COMPONENTS = ('Value', 'Other', 'Raw Text')
IDENTIFIERS = ('Paper ID', 'Experiment ID', 'Source')
EXCEL_CELL_LIMIT = 32767
FIELD_COLUMN_WIDTH = 44
IDENTIFIER_COLUMN_WIDTH = 25
REVIEW_HEADER_ROWS = 3
FLAT_HEADER_ROWS = 1
HEADER_COLOR = '24476A'
PAPER_COLORS = ('FFFFFF', 'EAF0F6')
# The registry drives both layouts; models remain the source of field types.
COLUMNS = (
    ('Paper metadata', 'Paper title', 'title'),
    ('Paper metadata', 'DOI', 'doi'),
    ('Paper metadata', 'Publication year', 'publication_year'),
    ('Paper metadata', 'Experiment description', 'description'),
    ('Method Family', 'Primary Family', 'method.family'),
    ('Method Family', 'Method name', 'method.name'),
    ('Method Family', 'Q-Matrix Task', 'method.task'),
    ('Domain', 'Application Domain', 'domain'),
    ('Testing Conditions', 'Data Type', 'conditions.data_type'),
    ('Testing Conditions', 'Sample Size', 'conditions.sample_size'),
    ('Testing Conditions', 'Number of Items', 'conditions.number_of_items'),
    ('Testing Conditions', 'Number of Attributes', 'conditions.number_of_attributes'),
    ('Testing Conditions', 'Response Type', 'conditions.response_type'),
    ('Testing Conditions', 'Attribute Structure', 'conditions.attribute_structure'),
    ('Testing Conditions', 'Diagnostic Model', 'conditions.diagnostic_model'),
    ('Testing Conditions', 'Misspecification', 'conditions.misspecification'),
    ('Testing Conditions', 'Item Quality', 'conditions.item_quality'),
    ('Testing Conditions', 'Benchmark Datasets', 'conditions.benchmark_datasets'),
    ('Evaluation Criteria', 'Criteria Used', 'evaluations.criterion'),
    ('Evaluation Criteria', 'Metrics', 'evaluations.metrics'),
    ('Author-Reported Limitations', 'Limitation Themes', 'limitations.theme'),
    ('Author-Reported Limitations', 'Limitation Descriptions', 'limitations.description'),
)
PAPER_FIELDS = ('title', 'doi', 'publication_year')


def compact(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), default=str)


def evidence_text(field: models.Extraction[object]) -> str:
    return '\n'.join(f'PDF p. {e.page if e.page is not None else "?"}; {e.location or "location unknown"}: “{e.text}”'
                     for e in field.raw_text)


def resolve_fields(value: BaseModel | list[BaseModel], path: str) -> list[models.Extraction[object]]:
    if isinstance(value, list):
        return [field for item in value for field in resolve_fields(item, path)]
    name, _, rest = path.partition('.')
    child = getattr(value, name)
    return resolve_fields(child, rest) if rest else [child]


def effective_experiment(paper: models.Paper, experiment: models.Experiment) -> models.Experiment:
    result = experiment.model_copy(deep=True)
    # Only absent overrides inherit; ambiguity and inapplicability remain explicit.
    for name in type(result.method).model_fields:
        if getattr(result.method, name).status == vocab.Status.NOT_REPORTED:
            setattr(result.method, name, getattr(paper.method, name))
    if result.domain.status == vocab.Status.NOT_REPORTED:
        result.domain = paper.domain
    result.limitations = [*paper.limitations, *experiment.limitations]
    return result


def field_cells(fields: list[models.Extraction[object]], array: bool) -> list[object]:
    values = [field.model_dump(mode='json')['value'] for field in fields]
    others = [field.model_dump(mode='json')['other'] for field in fields]
    if array:
        evidence = '\n'.join(f'[{index}] {evidence_text(field)}' for index, field in enumerate(fields, 1))
        return [compact(values), compact(others), evidence]
    value = values[0]
    rendered = compact(value) if isinstance(value, (dict, list)) else value
    return [rendered, compact(others[0]), evidence_text(fields[0])]


def experiment_row(record: models.PaperRecord, index: int) -> list[object]:
    paper = record.paper
    experiment = effective_experiment(paper, paper.experiments[index])
    row: list[object] = [record.paper_id, record.experiment_ids[index], record.provenance.source]
    for _, _, path in COLUMNS:
        owner = paper if path in PAPER_FIELDS else experiment
        row.extend(field_cells(resolve_fields(owner, path), path.startswith(('evaluations.', 'limitations.'))))
    return row


def safe_cell(cell: Cell, value: object, overflow: Worksheet) -> None:
    # Escape XML-invalid controls before testing Excel's limit; never truncate data.
    if isinstance(value, str):
        value = ILLEGAL_CHARACTERS_RE.sub(lambda match: f'\\u{ord(match.group()):04x}', value)
    if isinstance(value, str) and len(value) > EXCEL_CELL_LIMIT:
        reference = f'{cell.parent.title}!{cell.coordinate}'
        for index, start in enumerate(range(0, len(value), EXCEL_CELL_LIMIT), 1):
            overflow.append([reference, index, value[start:start + EXCEL_CELL_LIMIT]])
            overflow.cell(overflow.max_row, 3).data_type = 's'
        value = f'Full content in Overflow: {reference}'
    cell.value = value
    if isinstance(value, str):
        cell.data_type = 's'
    cell.alignment = Alignment(vertical='top', wrap_text=True)


def append_row(sheet: Worksheet, values: list[object], overflow: Worksheet) -> None:
    row = sheet.max_row + 1
    for column, value in enumerate(values, 1):
        safe_cell(sheet.cell(row, column), value, overflow)


def headers(sheet: Worksheet, formatted: bool) -> int:
    if not formatted:
        sheet.append([*IDENTIFIERS, *[f'{group}.{label}.{part}' for group, label, _ in COLUMNS for part in COMPONENTS]])
        return FLAT_HEADER_ROWS
    sheet.append([*IDENTIFIERS, *[group for group, _, _ in COLUMNS for _ in COMPONENTS]])
    sheet.append([''] * len(IDENTIFIERS) + [label for _, label, _ in COLUMNS for _ in COMPONENTS])
    sheet.append([''] * len(IDENTIFIERS) + list(COMPONENTS) * len(COLUMNS))
    for column in range(1, len(IDENTIFIERS) + 1):
        sheet.merge_cells(start_row=1, end_row=REVIEW_HEADER_ROWS, start_column=column, end_column=column)
    merge_groups(sheet)
    return REVIEW_HEADER_ROWS


def merge_groups(sheet: Worksheet) -> None:
    start = len(IDENTIFIERS) + 1
    for index, (group, _, _) in enumerate(COLUMNS):
        column = len(IDENTIFIERS) + 1 + index * len(COMPONENTS)
        sheet.merge_cells(start_row=2, end_row=2, start_column=column, end_column=column + 2)
        if index == len(COLUMNS) - 1 or COLUMNS[index + 1][0] != group:
            sheet.merge_cells(start_row=1, end_row=1, start_column=start, end_column=column + 2)
            start = column + 3


def style_sheet(sheet: Worksheet, header_rows: int, frozen_columns: int = 3) -> None:
    sheet.freeze_panes = f'{get_column_letter(frozen_columns + 1)}{header_rows + 1}'
    sheet.auto_filter.ref = f'A{header_rows}:{get_column_letter(sheet.max_column)}{sheet.max_row}'
    for row in sheet.iter_rows(max_row=header_rows):
        for cell in row:
            cell.font = Font(bold=True, color='FFFFFF')
            cell.fill = PatternFill('solid', fgColor=HEADER_COLOR)
            cell.alignment = Alignment(wrap_text=True, vertical='top')
    for column in range(1, sheet.max_column + 1):
        sheet.column_dimensions[get_column_letter(column)].width = FIELD_COLUMN_WIDTH if column > frozen_columns else IDENTIFIER_COLUMN_WIDTH


def export_workbook(records: list[models.PaperRecord], path: Path) -> None:
    workbook = Workbook()
    workbook.remove(workbook.active)
    overflow = workbook.create_sheet('Overflow')
    overflow.append(['Cell', 'Chunk', 'Full content'])
    ordered = sorted(records, key=lambda record: record.paper_id)
    # Both review layouts consume exactly the same ordered canonical records.
    for name, formatted in (('Review', True), ('Flat', False)):
        sheet = workbook.create_sheet(name)
        header_rows = headers(sheet, formatted)
        write_experiments(sheet, ordered, overflow)
        style_sheet(sheet, header_rows)
    write_papers(workbook, ordered, overflow)
    write_statuses(workbook, ordered, overflow)
    write_issues(workbook, ordered, overflow)
    style_sheet(overflow, 1)
    workbook.active = workbook.sheetnames.index('Review')
    temporary = path.with_suffix('.tmp.xlsx')
    workbook.save(temporary)
    temporary.replace(path)


def write_experiments(sheet: Worksheet, records: list[models.PaperRecord], overflow: Worksheet) -> None:
    for paper_index, record in enumerate(records):
        for index in range(len(record.paper.experiments)):
            append_row(sheet, experiment_row(record, index), overflow)
            for cell in sheet[sheet.max_row]:
                cell.fill = PatternFill('solid', fgColor=PAPER_COLORS[paper_index % len(PAPER_COLORS)])


def write_papers(workbook: Workbook, records: list[models.PaperRecord], overflow: Worksheet) -> None:
    sheet = workbook.create_sheet('Papers')
    sheet.append(['Paper ID', 'Source', 'Experiments', 'Paper JSON', 'Provenance JSON'])
    for record in records:
        append_row(sheet, [record.paper_id, record.provenance.source, len(record.paper.experiments),
                           record.paper.model_dump_json(), record.provenance.model_dump_json()], overflow)
    style_sheet(sheet, 1)


def write_statuses(workbook: Workbook, records: list[models.PaperRecord], overflow: Worksheet) -> None:
    from validation import fields_in
    sheet = workbook.create_sheet('Field Status')
    sheet.append(['Paper ID', 'Field path', 'Status', 'Export inheritance'])
    for record in records:
        for path, field in fields_in(record.paper):
            inherited = 'paper' if path.startswith('experiments[') and field.status == vocab.Status.NOT_REPORTED and ('.method.' in path or path.endswith('.domain')) else ''
            append_row(sheet, [record.paper_id, path, field.status.value, inherited], overflow)
    style_sheet(sheet, 1, 1)


def write_issues(workbook: Workbook, records: list[models.PaperRecord], overflow: Worksheet) -> None:
    sheet = workbook.create_sheet('Manual Review')
    sheet.append(['Paper ID', 'Field path', 'Issue'])
    for record in records:
        for issue in record.review_issues:
            append_row(sheet, [record.paper_id, issue.field, issue.reason], overflow)
    style_sheet(sheet, 1, 1)

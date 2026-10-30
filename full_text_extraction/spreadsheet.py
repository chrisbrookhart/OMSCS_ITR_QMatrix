"""Review and analysis worksheets derived from the same canonical records."""
from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from openpyxl import Workbook
from openpyxl.cell.cell import Cell, ILLEGAL_CHARACTERS_RE
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet
from pydantic import BaseModel
import models
import bibliography
import drive_links
import experiment_design
import validation
import vocabulary as vocab

COMPONENTS = ('Value', 'Other', 'Raw Text')
IDENTIFIERS = ('Paper index', 'Experiment index', 'Citation', 'Filename', 'Abstract', 'Title', 'Authors',
               'Publication year', 'Venue', 'DOI', 'URL', 'BibTeX key',
               'Experiment role', 'Study structure', 'Paper ID', 'Experiment ID', 'Source')
FROZEN_COLUMNS = 3
FILENAME_COLUMN = 4
ABSTRACT_COLUMN = 5
EXCEL_CELL_LIMIT = 32767
FIELD_COLUMN_WIDTH = 44
OTHER_COLUMN_WIDTH = 12
PAPER_NAME_COLUMN_WIDTH = 54
PAPER_INDEX_COLUMN_WIDTH = 10
EXPERIMENT_INDEX_COLUMN_WIDTH = 12
CITATION_COLUMN_WIDTH = 60
ABSTRACT_COLUMN_WIDTH = 70
FILENAME_COLUMN_WIDTH = 20
HYPERLINK_COLOR = '0563C1'
IDENTIFIER_COLUMN_WIDTH = 25
REVIEW_HEADER_ROWS = 3
FLAT_HEADER_ROWS = 1
HEADER_COLOR = '24476A'
PAPER_COLORS = ('E8F0F8', 'EAF3E5')
PRIMARY_COLORS = ('ADC8E3', 'B8D3A8')
FIELD_BORDER_COLOR = '94A3B8'
SAME_VALUE = '(same)'
REVIEW_SHEET = 'Review'
FLAT_SHEET = 'Flat'
SUMMARY_SHEET = 'Paper Summary'
NOTE_AUTHOR = 'Extraction notes'
NOTE_WIDTH = 380
NOTE_HEIGHT = 160
ARRAY_INDEX_PATTERN = r'\[\d+\]'
MISSING_STATUS_NOTES = {
    vocab.Status.NOT_REPORTED: 'Not reported in the supplied text; reason not established.',
    vocab.Status.NOT_APPLICABLE: 'Marked not applicable to this paper or design; no value expected.',
    vocab.Status.AMBIGUOUS: 'The supplied text does not support an unambiguous taxonomy value.',
    vocab.Status.EXTRACTED: 'Primary value is missing; check this extraction.',
}
# The registry drives both layouts; models remain the source of field types.
COLUMNS = (
    ('Experiment', 'Description', 'description'),
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
        return [compact(values), compact(others) if any(others) else None, evidence]
    value = values[0]
    rendered = compact(value) if isinstance(value, (dict, list)) else value
    return [rendered, compact(others[0]) if others[0] else None, evidence_text(fields[0])]


def paper_name(record: models.PaperRecord) -> str:
    return record.bibliography.fields.get(bibliography.TITLE_FIELD, record.paper_id) if record.bibliography else record.paper_id


def metadata_cells(record: models.PaperRecord) -> list[object]:
    metadata = record.bibliography
    fields = metadata.fields if metadata else {}
    return [bibliography.citation(metadata), Path(record.provenance.source).name, fields.get(bibliography.ABSTRACT_FIELD),
        fields.get(bibliography.TITLE_FIELD), fields.get(bibliography.AUTHORS_FIELD),
        fields.get(bibliography.YEAR_FIELD), fields.get(bibliography.JOURNAL_FIELD) or fields.get(bibliography.BOOKTITLE_FIELD),
        fields.get(bibliography.DOI_FIELD), fields.get(bibliography.URL_FIELD),
        metadata.citation_key if metadata else None]


def experiment_row(record: models.PaperRecord, index: int | None, *, paper_index: int = 1,
                    experiment_index: int | None = None) -> list[object]:
    paper = record.paper
    experiment = effective_experiment(paper, paper.experiments[index]) if index is not None else None
    number = experiment_index if experiment_index is not None else index + 1 if index is not None else None
    row: list[object] = [paper_index, number, *metadata_cells(record),
        experiment_design.role_label(record, index) if index is not None else experiment_design.NO_EXPERIMENTS,
        experiment_design.structure(record), record.paper_id,
        record.experiment_ids[index] if index is not None else None, record.provenance.source]
    for _, _, path in COLUMNS:
        row.extend(field_cells(resolve_fields(experiment, path), path.startswith(('evaluations.', 'limitations.')))
                   if experiment is not None else [None] * len(COMPONENTS))
    return row


def suppress_shared_values(record: models.PaperRecord, index: int, row: list[object]) -> list[object]:
    primary = experiment_design.primary_index(record)
    if primary is None or index == primary:
        return row
    reference = experiment_row(record, primary)
    current = effective_experiment(record.paper, record.paper.experiments[index])
    main = effective_experiment(record.paper, record.paper.experiments[primary])
    # Compare statuses too: equal strings must not conceal different uncertainty.
    for field_index, (_, _, path) in enumerate(COLUMNS):
        statuses = [field.status for field in resolve_fields(current, path)]
        if statuses != [field.status for field in resolve_fields(main, path)]:
            continue
        start = len(IDENTIFIERS) + field_index * len(COMPONENTS)
        for column in range(start, start + len(COMPONENTS)):
            if row[column] not in (None, '', '[]') and row[column] == reference[column]:
                row[column] = SAME_VALUE
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


def style_sheet(sheet: Worksheet, header_rows: int, frozen_columns: int = FROZEN_COLUMNS) -> None:
    sheet.freeze_panes = f'{get_column_letter(frozen_columns + 1)}{header_rows + 1}'
    sheet.auto_filter.ref = f'A{header_rows}:{get_column_letter(sheet.max_column)}{sheet.max_row}'
    for row in sheet.iter_rows(max_row=header_rows):
        for cell in row:
            cell.font = Font(bold=True, color='FFFFFF')
            cell.fill = PatternFill('solid', fgColor=HEADER_COLOR)
            cell.alignment = Alignment(wrap_text=True, vertical='top')
    for column in range(1, sheet.max_column + 1):
        sheet.column_dimensions[get_column_letter(column)].width = FIELD_COLUMN_WIDTH if column > frozen_columns else IDENTIFIER_COLUMN_WIDTH


def style_experiment_columns(sheet: Worksheet, header_rows: int) -> None:
    for letter, width in (('A', PAPER_INDEX_COLUMN_WIDTH), ('B', EXPERIMENT_INDEX_COLUMN_WIDTH),
                          ('C', CITATION_COLUMN_WIDTH), ('D', FILENAME_COLUMN_WIDTH), ('E', ABSTRACT_COLUMN_WIDTH)):
        sheet.column_dimensions[letter].width = width
    for column in range(len(IDENTIFIERS) + 1, sheet.max_column + 1):
        component = (column - len(IDENTIFIERS) - 1) % len(COMPONENTS)
        if component == COMPONENTS.index('Other'):
            sheet.column_dimensions[get_column_letter(column)].width = OTHER_COLUMN_WIDTH
        if component == 0:
            for row in range(header_rows, sheet.max_row + 1):
                sheet.cell(row, column).border = Border(left=Side(style='thin', color=FIELD_BORDER_COLOR))


def export_workbook(records: list[models.PaperRecord], path: Path, *,
                    pdf_drive_links: Mapping[str, str] | None = None) -> None:
    workbook = Workbook()
    workbook.remove(workbook.active)
    overflow = workbook.create_sheet('Overflow')
    overflow.append(['Cell', 'Chunk', 'Full content'])
    ordered = sorted(records, key=lambda record: (record.provenance.source.casefold(), record.paper_id))
    # Review compresses repeated cells; Flat preserves explicit analysis values.
    for name, formatted in ((SUMMARY_SHEET, True), (REVIEW_SHEET, True), (FLAT_SHEET, False)):
        write_experiment_sheet(workbook, ordered, overflow, name, formatted, pdf_drive_links or {})
    write_papers(workbook, ordered, overflow)
    write_bibliography_matches(workbook, ordered, overflow)
    write_statuses(workbook, ordered, overflow)
    write_issues(workbook, ordered, overflow)
    write_designs(workbook, ordered, overflow)
    write_missing_fields(workbook, ordered, overflow)
    write_recoveries(workbook, ordered, overflow, pdf_drive_links or {})
    write_guide(workbook)
    style_sheet(overflow, 1)
    workbook.active = workbook.sheetnames.index(REVIEW_SHEET)
    temporary = path.with_suffix('.tmp.xlsx')
    workbook.save(temporary)
    temporary.replace(path)


def write_experiment_sheet(workbook: Workbook, records: list[models.PaperRecord], overflow: Worksheet,
                           name: str, formatted: bool, links: Mapping[str, str]) -> None:
    sheet = workbook.create_sheet(name)
    header_rows = headers(sheet, formatted)
    write_experiments(sheet, records, overflow, links, summary=name == SUMMARY_SHEET,
                      suppress_repeats=name == REVIEW_SHEET)
    style_sheet(sheet, header_rows)
    style_experiment_columns(sheet, header_rows)


def experiment_indices(record: models.PaperRecord, summary: bool) -> list[int | None]:
    primary = experiment_design.primary_index(record)
    if summary:
        return [primary]
    if primary is None:
        return []
    return [primary, *[index for index in range(len(record.paper.experiments)) if index != primary]]


def write_experiments(sheet: Worksheet, records: list[models.PaperRecord], overflow: Worksheet,
                      links: Mapping[str, str],
                      *, summary: bool = False, suppress_repeats: bool = False) -> None:
    for paper_index, record in enumerate(records):
        primary = experiment_design.primary_index(record)
        for display_index, index in enumerate(experiment_indices(record, summary), 1):
            values = experiment_row(record, index, paper_index=paper_index + 1,
                                    experiment_index=display_index if index is not None else None)
            if suppress_repeats and index is not None:
                values = suppress_shared_values(record, index, values)
            append_row(sheet, values, overflow)
            link_filename(sheet, record.provenance.source, links)
            if index is not None:
                add_missing_notes(sheet, record, index)
            colors = PRIMARY_COLORS if index == primary else PAPER_COLORS
            for cell in sheet[sheet.max_row]:
                cell.fill = PatternFill('solid', fgColor=colors[paper_index % len(colors)])


def link_filename(sheet: Worksheet, source: str, links: Mapping[str, str]) -> None:
    target = drive_links.for_source(links, source)
    if target:
        cell = sheet.cell(sheet.max_row, FILENAME_COLUMN)
        cell.hyperlink = target
        cell.font = Font(color=HYPERLINK_COLOR, underline='single')


def source_field_path(record: models.PaperRecord, index: int, path: str) -> str:
    original = record.paper.experiments[index]
    if path == 'domain' or path.startswith('method.'):
        if resolve_fields(original, path)[0].status == vocab.Status.NOT_REPORTED:
            return path
    limitation = re.match(r'limitations\[(\d+)\](.*)', path)
    if limitation:
        number, suffix = int(limitation[1]), limitation[2]
        if number < len(record.paper.limitations):
            return path
        path = f'limitations[{number - len(record.paper.limitations)}]{suffix}'
    return f'experiments[{index}].{path}'


def missing_note(record: models.PaperRecord, path: str, field: models.Extraction[object]) -> str:
    assessment = next((item for item in record.missing_fields if item.field_path == path), None)
    if assessment is None:
        explanation = MISSING_STATUS_NOTES[field.status]
    else:
        explanation = f'{assessment.potential_reason.value}: {assessment.explanation}'
    return f'{path}\nStatus: {field.status.value}\n{explanation}'


def add_missing_notes(sheet: Worksheet, record: models.PaperRecord, index: int) -> None:
    experiment = effective_experiment(record.paper, record.paper.experiments[index])
    fields = list(validation.fields_in(experiment))
    # Notes annotate blanks; they never replace canonical or analysis values.
    for column_index, (_, _, column_path) in enumerate(COLUMNS):
        notes = [missing_note(record, source_field_path(record, index, path), field)
                 for path, field in fields if field.value is None
                 and re.sub(ARRAY_INDEX_PATTERN, '', path) == column_path]
        if notes:
            cell = sheet.cell(sheet.max_row, len(IDENTIFIERS) + column_index * len(COMPONENTS) + 1)
            cell.comment = Comment('\n\n'.join(notes), NOTE_AUTHOR, width=NOTE_WIDTH, height=NOTE_HEIGHT)


def write_designs(workbook: Workbook, records: list[models.PaperRecord], overflow: Worksheet) -> None:
    sheet = workbook.create_sheet('Experiment Roles')
    sheet.append(['Paper Name', 'Paper ID', 'Experiment ID', 'Role', 'Rationale', 'Evidence', 'Status'])
    for record in records:
        if record.experiment_design is None:
            continue
        for assignment in record.experiment_design.assignments:
            append_row(sheet, [paper_name(record), record.paper_id,
                record.experiment_ids[assignment.experiment_number - 1],
                experiment_design.role_label(record, assignment.experiment_number - 1),
                assignment.rationale.value, evidence_text(assignment.rationale),
                assignment.rationale.status.value], overflow)
    style_sheet(sheet, 1, 2)


def write_guide(workbook: Workbook) -> None:
    sheet = workbook.create_sheet('Guide')
    sheet.append(['Feature', 'Meaning'])
    for label, explanation in (
        ('Paper Summary', 'One representative main experiment per paper; other main studies remain in Review.'),
        ('Darker row', 'Primary main experiment, or an explicitly unclassified reference for legacy records.'),
        ('Paper colors', 'One color block per paper. Supporting and additional main experiments use lighter rows.'),
        ('Frozen columns', 'Paper index, experiment index and BibTeX citation. Filename and abstract scroll.'),
        ('Filename', 'PDF filename links to its Drive file when present in the local filename-to-link map.'),
        ('Metadata', 'Taken exclusively from matched BibTeX entries; missing entries remain blank.'),
        (SAME_VALUE, 'Review only: this cell equals the primary/reference row for this paper, including field status.'),
        ('Flat', 'All experiment values are explicit; no (same) markers. Use for analysis.'),
        ('Unclassified', 'No main/supporting classification is available; the first row is a reference only.'),
        ('Experiment Roles', 'Evidence and rationale for primary, additional main, and supporting assignments.'),
        ('Missing Fields', 'Missing values and potential reasons. Hypotheses are not established causes or imputed values.'),
        ('Blank value notes', 'Cell comments explain missing or inapplicable values. Blanks are acceptable; do not force a category.'),
        ('Recovery', 'Audited local repairs and imported retries. Unknown roles and missing explanations remain flagged.'),
    ):
        sheet.append([label, explanation])
    style_sheet(sheet, 1, 1)
    sheet.column_dimensions['B'].width = 100


def inherits_reported_value(paper: models.Paper, path: str, field: models.Extraction[object]) -> bool:
    if not path.startswith('experiments[') or field.status != vocab.Status.NOT_REPORTED:
        return False
    suffix = path.split('].', 1)[-1]
    if suffix == 'domain' or suffix.startswith('method.'):
        return resolve_fields(paper, suffix)[0].value is not None
    return False


def missing_field_rows(record: models.PaperRecord) -> list[list[object]]:
    explanations = {assessment.field_path: assessment for assessment in record.missing_fields}
    rows = []
    for path, field in validation.fields_in(record.paper):
        if path in bibliography.METADATA_PATHS or field.value is not None or inherits_reported_value(record.paper, path, field):
            continue
        assessment = explanations.get(path)
        rows.append([paper_name(record), record.paper_id, path, field.status.value,
            assessment.potential_reason.value if assessment else models.MissingReason.UNKNOWN.value,
            assessment.explanation if assessment else 'No model explanation available; reason not established.',
            '\n'.join(f'PDF p. {item.page}; {item.location}: {item.text}' for item in assessment.evidence)
                if assessment else None,
            'No value expected; retain blank.' if field.status == vocab.Status.NOT_APPLICABLE
                else 'Blank is acceptable. Optionally verify the PDF or supplements; do not infer a value.'])
    return rows


def write_missing_fields(workbook: Workbook, records: list[models.PaperRecord], overflow: Worksheet) -> None:
    sheet = workbook.create_sheet('Missing Fields')
    sheet.append(['Paper Name', 'Paper ID', 'Field path', 'Status', 'Potential reason',
                  'Explanation (may be a hypothesis)', 'Supporting evidence', 'Review action'])
    for record in records:
        for row in missing_field_rows(record):
            append_row(sheet, row, overflow)
    style_sheet(sheet, 1, 2)


def write_papers(workbook: Workbook, records: list[models.PaperRecord], overflow: Worksheet) -> None:
    sheet = workbook.create_sheet('Papers')
    sheet.append(['Paper ID', 'Source', 'Experiments', 'Paper JSON', 'Provenance JSON', 'BibTeX metadata JSON', 'Recovery audit JSON'])
    for record in records:
        append_row(sheet, [record.paper_id, record.provenance.source, len(record.paper.experiments),
                           record.paper.model_dump_json(), record.provenance.model_dump_json(),
                           record.bibliography.model_dump_json() if record.bibliography else None,
                           record.recovery.model_dump_json() if record.recovery else None], overflow)
    style_sheet(sheet, 1)


def write_recoveries(workbook: Workbook, records: list[models.PaperRecord], overflow: Worksheet,
                      links: Mapping[str, str]) -> None:
    sheet = workbook.create_sheet('Recovery')
    sheet.append(['Paper index', 'Paper ID', 'Source', 'Filename', 'Recovery actions', 'Unresolved fields',
                  'Raw response status', 'Raw response path', 'Raw response SHA256', 'Recovered at'])
    for index, record in enumerate(records, 1):
        audit = record.recovery
        if audit is None:
            continue
        append_row(sheet, [index, record.paper_id, record.provenance.source, Path(record.provenance.source).name,
            '\n'.join(audit.actions), '\n'.join(audit.unresolved_fields), audit.source_response_status,
            audit.source_response_path, audit.source_response_sha256, audit.recovered_at], overflow)
        link_filename(sheet, record.provenance.source, links)
    style_sheet(sheet, 1)


def write_statuses(workbook: Workbook, records: list[models.PaperRecord], overflow: Worksheet) -> None:
    from validation import fields_in
    sheet = workbook.create_sheet('Field Status')
    sheet.append(['Paper ID', 'Field path', 'Status', 'Export inheritance'])
    for record in records:
        for path, field in fields_in(record.paper):
            if path in bibliography.METADATA_PATHS:
                continue
            inherited = 'paper' if path.startswith('experiments[') and field.status == vocab.Status.NOT_REPORTED and ('.method.' in path or path.endswith('.domain')) else ''
            append_row(sheet, [record.paper_id, path, field.status.value, inherited], overflow)
    style_sheet(sheet, 1, 1)


def write_bibliography_matches(workbook: Workbook, records: list[models.PaperRecord], overflow: Worksheet) -> None:
    sheet = workbook.create_sheet('Bibliography Matches')
    sheet.append(['Paper index', 'Source', 'BibTeX key', 'Match basis', 'Alternative keys', 'Bibliography', 'SHA256'])
    for index, record in enumerate(records, 1):
        metadata = record.bibliography
        append_row(sheet, [index, record.provenance.source, metadata.citation_key if metadata else None,
            metadata.match_basis if metadata else 'Unmatched; no LLM metadata substituted',
            compact(metadata.alternative_keys) if metadata else None,
            metadata.source if metadata else None, metadata.source_sha256 if metadata else None], overflow)
    style_sheet(sheet, 1)


def write_issues(workbook: Workbook, records: list[models.PaperRecord], overflow: Worksheet) -> None:
    sheet = workbook.create_sheet('Manual Review')
    sheet.append(['Paper ID', 'Field path', 'Issue'])
    for record in records:
        for issue in record.review_issues:
            append_row(sheet, [record.paper_id, issue.field, issue.reason], overflow)
    style_sheet(sheet, 1, 1)

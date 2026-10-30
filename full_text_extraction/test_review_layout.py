"""Synthetic checks of primary rows, repeated values and missing explanations."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from openai.lib._pydantic import to_strict_json_schema
from openpyxl import load_workbook

import experiment_design
import bibliography
import models
import spreadsheet
import test_extract as fixtures
import validation
import vocabulary as vocab


def classified_record() -> models.PaperRecord:
    record = fixtures.record(3)
    record.experiment_design = models.ExperimentDesign.model_validate_json(json.dumps({
        'primary_experiment_number': 2,
        'assignments': [{'experiment_number': index + 1, 'role': role,
                         'rationale': fixtures.field('Central study' if role == 'main' else 'Auxiliary check')}
                        for index, role in enumerate(('main', 'main', 'supporting'))]}))
    return record


class ReviewLayoutTests(unittest.TestCase):
    def test_api_schema_remains_strict_and_legacy_records_remain_readable(self) -> None:
        schema = models.ExtractionPaper.model_json_schema()
        self.assertEqual(schema, to_strict_json_schema(models.ExtractionPaper))
        record = fixtures.record()
        self.assertIsNone(record.experiment_design)
        self.assertEqual(experiment_design.role_label(record, 0), experiment_design.REFERENCE_LABEL)

    def test_primary_row_colors_columns_and_lossless_flat_export(self) -> None:
        record = classified_record()
        original = record.model_dump_json()
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / 'review.xlsx'
            spreadsheet.export_workbook([record], path)
            workbook = load_workbook(path)
            review, flat = workbook['Review'], workbook['Flat']
            self.assertEqual(review['A4'].value, 1)
            self.assertEqual(review['B4'].value, 1)
            self.assertIsNone(review['C4'].value)
            self.assertEqual(review['D4'].value, 'synthetic.pdf')
            self.assertEqual(review['P4'].value, record.experiment_ids[1])
            self.assertEqual(review['M4'].value, experiment_design.PRIMARY_LABEL)
            self.assertEqual(review['N4'].value, experiment_design.MULTIPLE_MAIN)
            self.assertNotEqual(review['A4'].fill.fgColor.rgb, review['A5'].fill.fgColor.rgb)
            self.assertEqual(review['A5'].fill.fgColor.rgb, review['A6'].fill.fgColor.rgb)
            headers = [cell.value for cell in flat[1]]
            method = headers.index('Method Family.Primary Family.Value') + 1
            self.assertEqual(review.cell(5, method).value, spreadsheet.SAME_VALUE)
            self.assertEqual(flat.cell(3, method).value, 'statistical')
            self.assertEqual(review.column_dimensions['S'].width, spreadsheet.OTHER_COLUMN_WIDTH)
            self.assertEqual(len({review.cell(3, column).fill.fgColor.rgb for column in (18, 19, 20)}), 1)
            self.assertEqual(workbook['Paper Summary'].max_row, 4)
            self.assertEqual(review.max_row, 6)
            workbook.close()
        self.assertEqual(record.model_dump_json(), original)

    def test_uncertain_status_differences_are_not_hidden_by_same_marker(self) -> None:
        record = classified_record()
        record.paper.experiments[0].conditions.data_type.value = record.paper.experiments[1].conditions.data_type.value
        record.paper.experiments[0].conditions.data_type.status = vocab.Status.AMBIGUOUS
        row = spreadsheet.suppress_shared_values(record, 0, spreadsheet.experiment_row(record, 0))
        column = len(spreadsheet.IDENTIFIERS) + next(index for index, item in enumerate(spreadsheet.COLUMNS)
            if item[2] == 'conditions.data_type') * len(spreadsheet.COMPONENTS)
        self.assertNotEqual(row[column], spreadsheet.SAME_VALUE)

    def test_missing_fields_skip_inherited_values_and_flag_speculative_reasons(self) -> None:
        record = fixtures.record()
        assessment = models.MissingFieldAssessment(field_path='experiments[0].conditions.item_quality',
            potential_reason=models.MissingReason.POSSIBLY_VISUAL,
            explanation='Possibly in a figure; requires verification.', evidence=[])
        record.missing_fields = [assessment]
        rows = spreadsheet.missing_field_rows(record)
        self.assertNotIn('experiments[0].method.family', [row[2] for row in rows])
        target = next(row for row in rows if row[2] == assessment.field_path)
        self.assertEqual(target[4], models.MissingReason.POSSIBLY_VISUAL.value)
        self.assertIsNone(record.paper.experiments[0].conditions.item_quality.value)
        issues = validation.missing_assessment_issues(record.paper, [assessment], [fixtures.SYNTHETIC_TEXT])
        self.assertTrue(any('lacks supporting evidence' in issue.reason for issue in issues))

    def test_invalid_design_does_not_silently_choose_a_main_experiment(self) -> None:
        record = classified_record()
        record.experiment_design.primary_experiment_number = 3
        with self.assertRaisesRegex(ValueError, 'one of the main'):
            experiment_design.validate(record.experiment_design, 3)
        record.experiment_design.assignments.pop()
        with self.assertRaisesRegex(ValueError, 'exactly once'):
            experiment_design.validate(record.experiment_design, 3)

    def test_unjustified_roles_are_flagged_and_reference_row_is_explicit(self) -> None:
        record = classified_record()
        design = record.experiment_design
        design.primary_experiment_number = None
        for assignment in design.assignments:
            assignment.role = models.ExperimentRole.UNCLEAR
        experiment_design.validate(design, 3)
        self.assertEqual(experiment_design.role_label(record, 0), experiment_design.NO_MAIN_REFERENCE_LABEL)
        self.assertTrue(validation.design_issues(design, [fixtures.SYNTHETIC_TEXT]))
        design.assignments[0].role = models.ExperimentRole.MAIN
        design.assignments[0].rationale.raw_text = []
        self.assertTrue(any('lacks an evidence-backed rationale' in issue.reason
                            for issue in validation.design_issues(design, [fixtures.SYNTHETIC_TEXT])))

    def test_legitimate_missing_values_stay_blank_with_explanatory_comments(self) -> None:
        record = fixtures.record()
        record.paper.experiments[0].conditions.item_quality.status = vocab.Status.NOT_APPLICABLE
        record.missing_fields = [models.MissingFieldAssessment(
            field_path='experiments[0].conditions.item_quality',
            potential_reason=models.MissingReason.NOT_APPLICABLE,
            explanation='This synthetic design has no item-quality manipulation.', evidence=[])]
        self.assertFalse(validation.field_issues('conditions.item_quality',
            record.paper.experiments[0].conditions.item_quality, [fixtures.SYNTHETIC_TEXT]))
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / 'review.xlsx'
            spreadsheet.export_workbook([record], path)
            workbook = load_workbook(path)
            headers = [cell.value for cell in workbook['Flat'][1]]
            column = headers.index('Testing Conditions.Item Quality.Value') + 1
            cell = workbook['Review'].cell(4, column)
            self.assertIsNone(cell.value)
            self.assertIn('no item-quality manipulation', cell.comment.text)
            self.assertIsNone(workbook['Flat'].cell(2, column).value)
            workbook.close()


if __name__ == '__main__':
    unittest.main()

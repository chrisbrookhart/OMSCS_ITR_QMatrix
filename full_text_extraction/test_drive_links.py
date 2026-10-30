"""Synthetic link maps and real XLSX hyperlink relationships; no Drive calls."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from openpyxl import load_workbook
from pydantic import ValidationError

import drive_links
import spreadsheet
import test_extract as fixtures

SYNTHETIC_URL = 'https://drive.google.com/file/d/synthetic/view'


class DriveLinkTests(unittest.TestCase):
    def test_optional_default_map_and_explicit_missing_path(self) -> None:
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / drive_links.LINKS_FILENAME
            with patch('drive_links.DEFAULT_LINKS_PATH', path):
                self.assertEqual(drive_links.load_links(), {})
                path.write_text(json.dumps({'synthetic.pdf': SYNTHETIC_URL}))
                self.assertEqual(drive_links.load_links(), {'synthetic.pdf': SYNTHETIC_URL})
            with self.assertRaises(FileNotFoundError):
                drive_links.load_links(Path(temporary) / 'missing.json')

    def test_invalid_link_values_are_rejected(self) -> None:
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / drive_links.LINKS_FILENAME
            path.write_text(json.dumps({'synthetic.pdf': 123}))
            with self.assertRaises(ValidationError):
                drive_links.load_links(path)

    def test_exact_source_path_precedes_filename_fallback(self) -> None:
        links = {'folder/synthetic.pdf': SYNTHETIC_URL, 'synthetic.pdf': SYNTHETIC_URL + '?fallback=1'}
        self.assertEqual(drive_links.for_source(links, 'folder/synthetic.pdf'), SYNTHETIC_URL)
        self.assertEqual(drive_links.for_source(links, 'other/synthetic.pdf'), SYNTHETIC_URL + '?fallback=1')
        self.assertIsNone(drive_links.for_source(links, 'missing.pdf'))

    def test_linked_filenames_survive_excel_save_in_all_review_layouts(self) -> None:
        record = fixtures.record(2)
        record.provenance.source = 'folder/synthetic.pdf'
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / 'linked.xlsx'
            spreadsheet.export_workbook([record], path, pdf_drive_links={'synthetic.pdf': SYNTHETIC_URL})
            workbook = load_workbook(path)
            for name, start in (('Review', 4), ('Paper Summary', 4), ('Flat', 2)):
                sheet = workbook[name]
                self.assertEqual(sheet.freeze_panes, f'D{start}')
                for row in range(start, sheet.max_row + 1):
                    cell = sheet.cell(row, spreadsheet.FILENAME_COLUMN)
                    self.assertEqual(cell.value, 'synthetic.pdf')
                    self.assertEqual(cell.hyperlink.target, SYNTHETIC_URL)
            workbook.close()

    def test_missing_link_keeps_plain_filename(self) -> None:
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / 'unlinked.xlsx'
            spreadsheet.export_workbook([fixtures.record()], path)
            workbook = load_workbook(path)
            cell = workbook['Review'].cell(4, spreadsheet.FILENAME_COLUMN)
            self.assertEqual(cell.value, 'synthetic.pdf')
            self.assertIsNone(cell.hyperlink)
            workbook.close()


if __name__ == '__main__':
    unittest.main()

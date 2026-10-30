"""Synthetic BibTeX metadata, exact associations and workbook identifiers."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from openpyxl import load_workbook

import bibliography
import models
import spreadsheet
import test_extract as fixtures

SYNTHETIC_BIBTEX = r'''@string{venue = "Synthetic Journal"}
@article{F0001,
  title = {A {Synthetic} Q-Matrix Study},
  author = {Doe, Jane and Smith, Sam},
  year = {2024},
  journal = venue,
  doi = {10.0000/synthetic},
  abstract = {A synthetic abstract with {nested braces} and a comma, preserved.}
}
'''


class BibliographyTests(unittest.TestCase):
    def test_parser_preserves_metadata_and_matches_pdf_source_without_llm(self) -> None:
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / 'synthetic.bib'
            path.write_text(SYNTHETIC_BIBTEX, encoding='utf-8')
            entries = bibliography.load_entries([path])
        result = bibliography.match_entry(entries, 'F0001.pdf', [])
        self.assertEqual(result.citation_key, 'F0001')
        self.assertEqual(result.fields[bibliography.JOURNAL_FIELD], 'Synthetic Journal')
        self.assertIn('synthetic abstract', result.fields[bibliography.ABSTRACT_FIELD])
        self.assertIn('Doe, Jane', bibliography.citation(result))
        self.assertEqual(result.match_basis, 'source_map_or_filename')

    def test_text_matching_is_exact_and_ambiguous_matches_are_rejected(self) -> None:
        entry = models.BibliographicMetadata(citation_key='Synthetic2024',
            fields={'title': 'Exact Synthetic Title', 'doi': '10.0000/synthetic'},
            source='synthetic.bib', source_sha256='synthetic')
        self.assertIsNone(bibliography.match_entry([entry], 'unknown.pdf', ['A different title']))
        self.assertEqual(bibliography.match_entry([entry], 'unknown.pdf', ['Exact Synthetic Title']).citation_key,
                         entry.citation_key)
        duplicate = entry.model_copy(update={'citation_key': 'AnotherKey',
            'fields': {'title': 'Different Synthetic Title', 'doi': '10.0000/different'}})
        with self.assertRaisesRegex(ValueError, 'Ambiguous BibTeX'):
            bibliography.match_entry([entry, duplicate], 'unknown.pdf', ['doi:10.0000/synthetic doi:10.0000/different'])

    def test_duplicate_work_prefers_abstract_and_preserves_alternative_keys(self) -> None:
        attachment = models.BibliographicMetadata(citation_key='Synthetic2024-1',
            fields={'title': 'Synthetic study', 'doi': '10.0000/synthetic', 'file': 'synthetic.pdf'},
            source='synthetic.bib', source_sha256='synthetic')
        complete = attachment.model_copy(update={'citation_key': 'Synthetic2024',
            'fields': {'title': 'Synthetic study', 'doi': '10.0000/synthetic', 'abstract': 'Synthetic abstract'}})
        selected = bibliography.match_entry([attachment, complete], 'unknown.pdf', ['10.0000/synthetic'])
        self.assertEqual(selected.citation_key, 'Synthetic2024')
        self.assertEqual(selected.alternative_keys, ['Synthetic2024-1'])

    def test_conflicting_duplicate_bibtex_keys_fail_explicitly(self) -> None:
        with TemporaryDirectory() as temporary:
            first, second = [Path(temporary) / name for name in ('first.bib', 'second.bib')]
            first.write_text(SYNTHETIC_BIBTEX)
            second.write_text(SYNTHETIC_BIBTEX.replace('2024', '2025'))
            with self.assertRaisesRegex(ValueError, 'Conflicting BibTeX'):
                bibliography.load_entries([first, second])

    def test_workbook_uses_bibtex_metadata_and_freezes_only_first_three_columns(self) -> None:
        record = fixtures.record(2)
        record.paper.title.value = 'LLM guess that must not appear as metadata'
        record.bibliography = models.BibliographicMetadata(citation_key='Synthetic2024',
            fields={'title': 'BibTeX title', 'abstract': 'BibTeX abstract', 'author': 'Doe, Jane', 'year': '2024'},
            source='synthetic.bib', source_sha256='synthetic')
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / 'review.xlsx'
            spreadsheet.export_workbook([record], path)
            workbook = load_workbook(path)
            sheet = workbook['Review']
            self.assertEqual([sheet.cell(1, column).value for column in range(1, 6)],
                             ['Paper index', 'Experiment index', 'Citation', 'Filename', 'Abstract'])
            self.assertEqual(sheet.freeze_panes, 'D4')
            self.assertEqual(sheet['A4'].value, 1)
            self.assertEqual([sheet.cell(row, 2).value for row in (4, 5)], [1, 2])
            self.assertIn('BibTeX title', sheet['C4'].value)
            self.assertEqual(sheet['D4'].value, 'synthetic.pdf')
            self.assertEqual(sheet['E4'].value, 'BibTeX abstract')
            self.assertEqual(sheet['F4'].value, 'BibTeX title')
            workbook.close()

    def test_only_two_paper_color_families_with_two_shades_each(self) -> None:
        records = [fixtures.record(2) for _ in range(3)]
        for index, record in enumerate(records):
            record.paper_id = f'synthetic-{index}'
            record.provenance.source = f'synthetic-{index}.pdf'
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / 'review.xlsx'
            spreadsheet.export_workbook(records, path)
            workbook = load_workbook(path)
            colors = [workbook['Review'].cell(row, 1).fill.fgColor.rgb for row in range(4, 10)]
            self.assertEqual(len(set(colors)), 4)
            self.assertEqual(colors[:2], colors[4:])
            self.assertNotEqual(colors[:2], colors[2:4])
            workbook.close()


if __name__ == '__main__':
    unittest.main()

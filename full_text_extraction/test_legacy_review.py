"""Historical exports remain readable without invoking the new extractor."""
import json
from pathlib import Path
import tempfile
import unittest
from coverage_report import write_coverage
from legacy_review import evidence_warnings


class HistoricalReviewTests(unittest.TestCase):
    def test_historical_numeric_and_quote_checks(self) -> None:
        field = {'status': 'reported', 'value': '100 or 500', 'evidence': [{'page': 1, 'quote': '100 or 500'}],
            'typed_value': [{'condition': 'Synthetic', 'measure': 'participants', 'unit': 'participants',
                             'values': [100, 500], 'minimum': None, 'maximum': None}]}
        self.assertEqual(evidence_warnings({'sample_size': field}, ['100 or 500']), [])
        field['typed_value'][0]['values'] = [-1]
        self.assertTrue(evidence_warnings({'sample_size': field}, ['100 or 500']))

    def test_historical_coverage_export_still_works(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            folder = run / 'paper'
            folder.mkdir()
            field = {'status': 'reported', 'value': '100', 'evidence': [{'page': 1, 'quote': '100'}],
                     'typed_value': [{'condition': 'A', 'measure': 'participants', 'unit': 'participants',
                                      'values': [100], 'minimum': None, 'maximum': None}]}
            (folder / 'extraction.json').write_text(json.dumps({'fields': {'sample_size': field}, 'review_warnings': []}))
            (folder / 'pages.json').write_text(json.dumps(['100']))
            (run / 'manifest.json').write_text(json.dumps({'selected_pdfs': 1,
                'papers': [{'directory': 'paper', 'source': 'synthetic.pdf', 'status': 'extracted'}]}))
            result = write_coverage(run, {'sample_size': {'value_type': 'integer_conditions'}})
            self.assertEqual(result['fields'][0]['evidence_supported_reported'], 1)
            self.assertTrue((run / 'numeric_observations.csv').exists())


if __name__ == '__main__':
    unittest.main()

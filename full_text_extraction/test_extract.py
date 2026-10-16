import unittest
from unittest.mock import Mock, patch
from pathlib import Path
import tempfile
import json
import sys

from extract import evidence_warnings, load_api_key, main, schema_for


class ExtractionTests(unittest.TestCase):
    def test_local_config_key_and_missing_config(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            with patch('extract.PROJECT', folder):
                with self.assertRaises(ValueError):
                    load_api_key()
                (folder / 'config.py').write_text('OPENAI_API_KEY = ""\n')
                with self.assertRaises(ValueError):
                    load_api_key()
                (folder / 'config.py').write_text('OPENAI_API_KEY = "synthetic-config-key"\n')
                with patch.dict('os.environ', {'OPENAI_API_KEY': 'synthetic-env-key'}):
                    self.assertEqual(load_api_key(), 'synthetic-config-key')

    def test_evidence_checks_page_and_quote(self):
        result = {'sample': {'status': 'reported', 'value': '20',
                             'evidence': [{'page': 1, 'quote': '20 participants'}]}}
        self.assertEqual(evidence_warnings(result, ['We used 20\nparticipants.']), [])
        result['sample']['evidence'][0]['page'] = 2
        self.assertTrue(evidence_warnings(result, ['We used 20 participants.']))

    def test_mock_api_request_and_saved_output(self):
        from jsonschema import validate
        result = {'title': {'status': 'reported', 'value': 'Synthetic paper',
                            'evidence': [{'page': 1, 'quote': 'Synthetic paper'}]}}
        validate(result, schema_for({'title': 'Title'}))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            inputs = root / 'input'
            inputs.mkdir()
            (inputs / 'synthetic.pdf').write_bytes(b'synthetic placeholder')
            settings = root / 'settings.json'
            settings.write_text(json.dumps({'fields': {'title': 'Title'}, 'model': 'gpt-6-luna',
                'timeout_seconds': 1, 'reasoning_effort': 'low', 'max_output_tokens': 1000,
                'max_input_characters': 10000}))
            response = Mock(status='completed', output_text=json.dumps(result), id='synthetic-id', usage=None)
            response.model_dump.return_value = {'status': 'completed'}
            client = Mock()
            client.responses.create.return_value = response
            with patch('extract.ROOT', root), patch('extract.read_pdf', return_value=['Synthetic paper']), \
                 patch('openai.OpenAI', return_value=client) as constructor, \
                 patch('extract.load_api_key', return_value='synthetic-test-key'), \
                 patch.object(sys, 'argv', ['extract', '--input', str(inputs), '--settings', str(settings), '--execute']):
                self.assertEqual(main(), 0)
            self.assertEqual(constructor.call_args.kwargs['api_key'], 'synthetic-test-key')
            call = client.responses.create.call_args.kwargs
            self.assertEqual(call['model'], 'gpt-6-luna')
            self.assertFalse(call['store'])
            self.assertTrue(call['text']['format']['strict'])
            manifest = next((root / 'output').rglob('manifest.json'))
            self.assertEqual(json.loads(manifest.read_text())['papers'][0]['status'], 'extracted')
            with patch('extract.ROOT', root), patch('extract.read_pdf') as pdf_reader, \
                 patch('openai.OpenAI', return_value=client), \
                 patch('extract.load_api_key', return_value='synthetic-test-key'), \
                 patch.object(sys, 'argv', ['extract', '--input', str(inputs), '--settings', str(settings), '--execute', '--resume', str(manifest.parent)]):
                self.assertEqual(main(), 0)
                pdf_reader.assert_not_called()
            self.assertEqual(client.responses.create.call_count, 1)


    def test_typed_numeric_and_enum_values(self):
        from jsonschema import validate, ValidationError
        definitions = {
            'sample_size': {'description': 'Sample size', 'value_type': 'integer_conditions', 'codes': []},
            'family': {'description': 'Family', 'value_type': 'enum_list', 'codes': ['statistical']}}
        observation = {'condition': 'Synthetic simulation', 'measure': 'participants', 'unit': 'participants',
                       'values': [100, 500], 'minimum': None, 'maximum': None}
        result = {
            'sample_size': {'status': 'reported', 'value': '100 or 500 participants',
                            'typed_value': [observation], 'evidence': [{'page': 1, 'quote': '100 or 500'}]},
            'family': {'status': 'reported', 'value': 'Statistical mapping estimation',
                       'typed_value': ['statistical'], 'evidence': [{'page': 1, 'quote': 'Statistical'}]}}
        validate(result, schema_for(definitions))
        result['sample_size']['typed_value'][0]['values'] = ['100']
        with self.assertRaises(ValidationError):
            validate(result, schema_for(definitions))
        result['sample_size']['typed_value'][0]['values'] = [100.5]
        with self.assertRaises(ValidationError):
            validate(result, schema_for(definitions))
        result['sample_size']['typed_value'][0]['values'] = [100]
        result['family']['typed_value'] = ['invented']
        with self.assertRaises(ValidationError):
            validate(result, schema_for(definitions))

    def test_numeric_export_retains_conditions_and_types(self):
        import csv
        from export_typed import export_typed
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            folder = run / 'paper'
            folder.mkdir()
            observation = {'condition': 'Simulation A', 'measure': 'participants', 'unit': 'participants',
                           'values': [100, 500], 'minimum': None, 'maximum': None}
            field = {'status': 'reported', 'value': 'Synthetic sample sizes', 'typed_value': [observation], 'evidence': []}
            (folder / 'extraction.json').write_text(json.dumps({'fields': {'sample_size': field}}))
            export_typed(run, {'sample_size': {'value_type': 'integer_conditions'}}, [{'directory': 'paper', 'source': 'synthetic.pdf'}])
            native = json.loads((run / 'typed_values.jsonl').read_text())
            self.assertIsInstance(native['typed_value'][0]['values'][0], int)
            with (run / 'numeric_observations.csv').open() as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual([r['value'] for r in rows], ['100', '500'])
            self.assertEqual(rows[0]['condition'], 'Simulation A')
            self.assertEqual(rows[0]['minimum'], '')

    def test_taxonomy_codes_and_coverage_denominators(self):
        from jsonschema import validate, ValidationError
        from coverage_report import write_coverage
        definitions = {'data': {'rq': 'RQ2', 'description': 'Data type', 'codes': ['empirical', 'simulated']}}
        field = {'status': 'reported', 'value': 'Empirical sample', 'codes': ['empirical'],
                 'evidence': [{'page': 1, 'quote': 'Empirical sample'}]}
        validate({'data': field}, schema_for(definitions))
        with self.assertRaises(ValidationError):
            validate({'data': {**field, 'codes': ['invented']}}, schema_for(definitions))
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            papers = []
            for i, status in enumerate(['reported', 'not_reported', 'not_applicable', 'unclear']):
                folder = run / str(i)
                folder.mkdir()
                result = {'fields': {'data': {**field, 'status': status}}, 'review_warnings': []}
                (folder / 'extraction.json').write_text(json.dumps(result))
                papers.append({'directory': str(i), 'source': f'synthetic-{i}.pdf', 'status': 'extracted'})
            papers.append({'status': 'error'})
            (run / 'manifest.json').write_text(json.dumps({'selected_pdfs': 6, 'papers': papers}))
            coverage = write_coverage(run, definitions)
            row = coverage['fields'][0]
            self.assertEqual(row['applicable_extracted'], 3)
            self.assertEqual(row['reported_pct_applicable'], 33.3)
            self.assertEqual(coverage['failed'], 1)
            self.assertEqual(coverage['not_attempted'], 1)

    def test_coverage_numeric_presence_requires_actual_numbers(self):
        from coverage_report import write_coverage
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            papers = []
            for i, values in enumerate([[], [0.0]]):
                folder = run / str(i)
                folder.mkdir()
                observation = {'condition': 'Synthetic condition', 'measure': 'error', 'unit': 'proportion',
                               'values': values, 'minimum': None, 'maximum': None}
                field = {'status': 'reported', 'value': 'A criterion was evaluated', 'evidence': [], 'typed_value': [observation]}
                (folder / 'extraction.json').write_text(json.dumps({'fields': {'metric': field}, 'review_warnings': []}))
                papers.append({'directory': str(i), 'source': f'synthetic-{i}.pdf', 'status': 'extracted'})
            (run / 'manifest.json').write_text(json.dumps({'selected_pdfs': 2, 'papers': papers}))
            report = write_coverage(run, {'metric': {'value_type': 'numeric_conditions'}})
            self.assertEqual(report['fields'][0]['reported'], 2)
            self.assertEqual(report['fields'][0]['typed_values_present'], 1)

    def test_empty_pdf_does_not_call_api(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'synthetic.pdf').write_bytes(b'placeholder')
            with patch('extract.ROOT', root), patch('extract.read_pdf', return_value=['']), \
                 patch.object(sys, 'argv', ['extract', '--input', str(root)]):
                self.assertEqual(main(), 1)
            manifest = next((root / 'output').rglob('manifest.json'))
            self.assertEqual(json.loads(manifest.read_text())['papers'][0]['status'], 'error')


if __name__ == '__main__':
    unittest.main()

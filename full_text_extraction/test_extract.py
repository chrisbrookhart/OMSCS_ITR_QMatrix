import unittest
from unittest.mock import Mock, patch
from pathlib import Path
import tempfile
import json
import sys

from extract import evidence_warnings, main, schema_for


class ExtractionTests(unittest.TestCase):
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
                 patch('openai.OpenAI', return_value=client), \
                 patch.dict('os.environ', {'OPENAI_API_KEY': 'synthetic-test-key'}), \
                 patch.object(sys, 'argv', ['extract', '--input', str(inputs), '--settings', str(settings), '--execute']):
                self.assertEqual(main(), 0)
            call = client.responses.create.call_args.kwargs
            self.assertEqual(call['model'], 'gpt-6-luna')
            self.assertFalse(call['store'])
            self.assertTrue(call['text']['format']['strict'])
            manifest = next((root / 'output').rglob('manifest.json'))
            self.assertEqual(json.loads(manifest.read_text())['papers'][0]['status'], 'extracted')

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

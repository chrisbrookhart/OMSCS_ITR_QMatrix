"""CLI defaults, restricted model selection and flushed waiting progress."""
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from threading import Event, Thread
import unittest
from unittest.mock import Mock, patch
import extract
import progress
import storage


class CommandLineTests(unittest.TestCase):
    def test_help_explains_defaults_output_and_examples(self) -> None:
        help_text = extract.get_parser().format_help()
        self.assertIn(str(storage.ROOT / 'output/full_text_extraction'), help_text)
        self.assertIn(str(storage.ROOT / 'input/full_text'), help_text)
        for phrase in ('default: 1', 'timestamp', 'extraction.xlsx', 'no API calls', '--model', 'Examples'):
            self.assertIn(phrase, help_text)

    def test_model_choices_accept_only_documented_ids(self) -> None:
        parser = extract.get_parser()
        for model in storage.SUPPORTED_MODELS:
            self.assertEqual(parser.parse_args(['--model', model]).model, model)
        with redirect_stderr(StringIO()), self.assertRaises(SystemExit) as error:
            parser.parse_args(['--model', 'gpt-6.1-luna'])
        self.assertEqual(error.exception.code, 2)
        self.assertIsNone(parser.parse_args([]).model)

    def test_cli_forwards_model_override(self) -> None:
        with patch('sys.argv', ['extract', '--execute', '--model', 'gpt-6.1-sol']), patch('pipeline.main', return_value=0) as main:
            self.assertEqual(extract.main(), 0)
        self.assertEqual(main.call_args.kwargs['model'], 'gpt-6.1-sol')
        self.assertTrue(main.call_args.kwargs['execute'])

    def test_large_concurrency_forwards_the_explicit_token_rate_limit(self) -> None:
        arguments = ['extract', '--workers', '110', '--tokens-per-minute', '2000000']
        with patch('sys.argv', arguments), patch('pipeline.main', return_value=0) as main:
            self.assertEqual(extract.main(), 0)
        self.assertEqual(main.call_args.kwargs['workers'], 110)
        self.assertEqual(main.call_args.kwargs['tokens_per_minute'], 2000000)

    def test_progress_flushes_stdout(self) -> None:
        with patch('builtins.print') as output:
            progress.log('Preparing PDF')
        self.assertTrue(output.call_args.kwargs['flush'])
        self.assertIn('Preparing PDF', output.call_args.args[0])

    def test_heartbeat_reports_elapsed_time_and_stops(self) -> None:
        finished = Mock(spec=Event)
        finished.wait.side_effect = [False, True]
        with patch('progress.monotonic', return_value=30), patch('progress.log') as log:
            progress.report_wait(finished, 'gpt-6.1-sol', 0)
        self.assertIn('30s elapsed', log.call_args.args[0])
        self.assertIn('gpt-6.1-sol', log.call_args.args[0])
        finished.wait.assert_called_with(progress.HEARTBEAT_SECONDS)
        self.assertEqual(log.call_count, 1)

    def test_waiting_worker_stops_on_exception(self) -> None:
        workers: list[Thread] = []

        def create_worker(**kwargs: object) -> Thread:
            worker = Thread(**kwargs)
            workers.append(worker)
            return worker

        with patch('progress.Thread', side_effect=create_worker):
            with self.assertRaisesRegex(RuntimeError, 'synthetic failure'):
                with progress.waiting_for_response('gpt-6-luna'):
                    raise RuntimeError('synthetic failure')
        self.assertEqual(len(workers), 1)
        self.assertFalse(workers[0].is_alive())


if __name__ == '__main__':
    unittest.main()

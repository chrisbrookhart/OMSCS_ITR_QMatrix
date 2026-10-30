"""Synthetic whole-paper fixtures; no live API calls or private study text."""
from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
from threading import Barrier, Lock, get_ident
import unittest
from unittest.mock import Mock, patch
from openpyxl import load_workbook
from openai.lib._pydantic import to_strict_json_schema
from pydantic import ValidationError
import api
import citation_keys
import export_workbook
import models
import pipeline
import prompts
import reporting
import spreadsheet
import storage
import validation
import vocabulary as vocab

SYNTHETIC_TEXT = ('Synthetic study. In our educational assessment study, our hybrid method '
    'combined expert judgment and statistical optimization. We generated Q-matrices. '
    'Simulation 1 used DINA, 500, 1000 and 2000 participants, 20 items and 4 attributes. '
    'Responses were dichotomous, attributes independent. We measured Q recovery with '
    'RMSE and fit with AIC. Our small samples limit generalizability. '
    'Our computational cost is a limitation. Empirical study 2 used Benchmark A. '
    'A second supporting passage.')


def evidence(text: str = 'Synthetic study.') -> list[dict[str, object]]:
    return [{'page': 1, 'location': 'Methods, paragraph 1', 'text': text}]


def field(value: object = None, other: list[object] | None = None,
          quote: str = 'Synthetic study.', status: str | None = None) -> dict[str, object]:
    return {'value': value, 'other': other or [], 'raw_text': evidence(quote) if value is not None else [],
            'status': status or ('extracted' if value is not None else 'not_reported')}


def method(reported: bool = True) -> dict[str, object]:
    if not reported:
        return {name: field() for name in ('family', 'name', 'task')}
    return {'family': field('statistical', ['expert_driven'], 'combined expert judgment and statistical optimization.'),
            'name': field('hybrid method', quote='our hybrid method'),
            'task': field('generation', quote='We generated Q-matrices.')}


def numeric(values: list[int | float], unit: str = 'participants') -> dict[str, object]:
    return {'condition': 'Simulation 1', 'unit': unit, 'values': values, 'range': None}


def conditions(data_type: str = 'simulated') -> dict[str, object]:
    result = {name: field() for name in models.Conditions.model_fields}
    result.update(data_type=field(data_type), sample_size=field(numeric([500, 1000, 2000]), quote='500, 1000 and 2000 participants'),
        number_of_items=field(numeric([20], 'items'), quote='20 items'),
        number_of_attributes=field(numeric([4], 'attributes'), quote='4 attributes'),
        response_type=field('dichotomous', quote='Responses were dichotomous'),
        attribute_structure=field('independent', quote='attributes independent.'),
        diagnostic_model=field({'canonical': 'DINA', 'reported_name': 'DINA'}, quote='Simulation 1 used DINA'))
    return result


def limitations() -> list[dict[str, object]]:
    return [
        {'theme': field('small_sample_size', quote='Our small samples limit generalizability.'),
         'description': field('Small samples', quote='Our small samples limit generalizability.')},
        {'theme': field('computational_cost', quote='Our computational cost is a limitation.'),
         'description': field('Expensive computation', quote='Our computational cost is a limitation.')},
    ]


def experiment(data_type: str = 'simulated') -> dict[str, object]:
    return {'description': field('Simulation 1' if data_type == 'simulated' else 'Empirical study 2'),
        'method': method(False), 'domain': field(), 'conditions': conditions(data_type),
        'evaluations': [
            {'criterion': field('q_matrix_recovery', quote='We measured Q recovery with RMSE'),
             'metrics': field('RMSE', quote='We measured Q recovery with RMSE')},
            {'criterion': field('model_fit', quote='fit with AIC'), 'metrics': field('AIC', quote='fit with AIC')}],
        'limitations': []}


def paper_payload(count: int = 1) -> dict[str, object]:
    return {'title': field('Synthetic study', quote='Synthetic study.'), 'doi': field(),
        'publication_year': field(), 'method': method(),
        'domain': field('educational_measurement', quote='In our educational assessment study'),
        'limitations': limitations(),
        'experiments': [experiment('simulated' if index == 0 else 'empirical') for index in range(count)]}


def paper(count: int = 1) -> models.Paper:
    return models.Paper.model_validate_json(json.dumps(paper_payload(count)))


def settings() -> storage.Settings:
    return storage.Settings(model='gpt-6-luna', reasoning_effort='low', max_output_tokens=14000,
                            max_input_characters=10000, timeout_seconds=1, max_retries=2)


def response(payload: dict[str, object] | None = None, status: str = 'completed') -> Mock:
    data = dict(payload or paper_payload())
    count = len(data.get('experiments', []))
    data['experiment_design'] = {'primary_experiment_number': 1 if count else None,
        'assignments': [{'experiment_number': index + 1, 'role': 'main' if index == 0 else 'supporting',
                         'rationale': field('Central study' if index == 0 else 'Auxiliary check')}
                        for index in range(count)]}
    data['missing_fields'] = []
    for name in ('title', 'doi', 'publication_year'):
        data.pop(name, None)
    text = json.dumps(data)
    result = Mock(status=status, output_text=text, incomplete_details=None)
    result.model_dump.return_value = {'id': 'synthetic-response', 'model': 'gpt-6-luna', 'status': status,
        'usage': {'total_tokens': 10},
        'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': text}]}]}
    return result


def record(count: int = 1) -> models.PaperRecord:
    result = paper(count)
    provenance = models.Provenance(model='synthetic', prompt_version=models.PROMPT_VERSION,
        schema_version=models.SCHEMA_VERSION, request_fingerprint='synthetic-hash', extracted_at='2026-01-01T00:00:00Z',
        source='synthetic.pdf', source_sha256='synthetic-sha', page_numbering=models.PAGE_NUMBERING,
        response_id='synthetic-response')
    return models.PaperRecord(paper_id='bibliography-42', experiment_ids=pipeline.experiment_ids('bibliography-42', result),
        provenance=provenance, paper=result, review_issues=validation.review_issues(result, [SYNTHETIC_TEXT]))


class SchemaTests(unittest.TestCase):
    def test_round_trip_one_multiple_and_no_experiments(self) -> None:
        for count in (0, 1, 3, 7):
            result = record(count)
            self.assertEqual(len(result.paper.experiments), count)
            self.assertEqual(models.PaperRecord.model_validate_json(result.model_dump_json()), result)
            self.assertEqual(result.experiment_ids, [f'bibliography-42:E{i:03d}' for i in range(1, count + 1)])

    def test_schema_is_already_strict_and_all_fields_required(self) -> None:
        schema = models.Paper.model_json_schema()
        self.assertEqual(schema, to_strict_json_schema(models.Paper))
        for definition in [schema, *schema['$defs'].values()]:
            if definition.get('type') == 'object':
                self.assertFalse(definition['additionalProperties'])
                self.assertEqual(set(definition['required']), set(definition['properties']))

    def test_invalid_enum_extra_field_and_missing_field_rejected(self) -> None:
        for change in ('enum', 'extra', 'missing'):
            payload = paper_payload()
            if change == 'enum':
                payload['domain']['value'] = 'invented'
            elif change == 'extra':
                payload['surprise'] = 1
            else:
                del payload['doi']
            with self.assertRaises(ValidationError):
                models.Paper.model_validate_json(json.dumps(payload))

    def test_parameter_sweep_stays_in_one_experiment(self) -> None:
        result = paper()
        self.assertEqual(len(result.experiments), 1)
        self.assertEqual(result.experiments[0].conditions.sample_size.value.values, [500, 1000, 2000])
        self.assertIn('Group parameter sweeps', prompts.INSTRUCTIONS)

    def test_hybrid_criteria_limitations_and_inheritance(self) -> None:
        result = paper()
        self.assertEqual(result.method.family.other, [vocab.MethodFamily.EXPERT])
        resolved = spreadsheet.effective_experiment(result, result.experiments[0])
        self.assertEqual(resolved.method, result.method)
        self.assertEqual(len(resolved.evaluations), 2)
        self.assertEqual(len(resolved.limitations), 2)
        self.assertIsNone(result.experiments[0].method.family.value)

    def test_explicit_override_and_inapplicable_do_not_inherit(self) -> None:
        payload = paper_payload()
        payload['experiments'][0]['domain'] = field('clinical_assessment')
        payload['experiments'][0]['method']['family'] = field(status='not_applicable')
        result = models.Paper.model_validate_json(json.dumps(payload))
        resolved = spreadsheet.effective_experiment(result, result.experiments[0])
        self.assertEqual(resolved.domain.value, vocab.Domain.CLINICAL)
        self.assertIsNone(resolved.method.family.value)

    def test_missing_inapplicable_ambiguous_and_zero(self) -> None:
        payload = paper_payload()
        conditions_value = payload['experiments'][0]['conditions']
        conditions_value['item_quality'] = field(status='not_applicable')
        conditions_value['response_type'] = field(status='ambiguous')
        conditions_value['misspecification'] = field(numeric([0], 'proportion'))
        result = models.Paper.model_validate_json(json.dumps(payload))
        warnings = validation.review_issues(result, [SYNTHETIC_TEXT])
        self.assertTrue(any('ambiguous' in issue.reason for issue in warnings))
        self.assertFalse(any('misspecification' in issue.field for issue in warnings))
        self.assertEqual(result.experiments[0].conditions.misspecification.value.values, [0])

    def test_unknown_diagnostic_model_and_range_preserved(self) -> None:
        payload = paper_payload()
        conditions_value = payload['experiments'][0]['conditions']
        conditions_value['diagnostic_model'] = field({'canonical': 'other', 'reported_name': 'Novel CDM'})
        conditions_value['sample_size'] = field({'condition': 'A', 'unit': 'participants', 'values': [],
            'range': {'minimum': 100, 'maximum': 400}})
        result = models.Paper.model_validate_json(json.dumps(payload))
        self.assertEqual(result.experiments[0].conditions.diagnostic_model.value.reported_name, 'Novel CDM')
        self.assertEqual(result.experiments[0].conditions.sample_size.value.range.maximum, 400)


class EvidenceTests(unittest.TestCase):
    def test_multiple_citations_and_whitespace_normalization(self) -> None:
        payload = paper_payload()
        payload['title']['raw_text'] += [{'page': 2, 'location': 'Discussion', 'text': 'A second supporting passage.'}]
        result = models.Paper.model_validate_json(json.dumps(payload))
        issues = validation.review_issues(result, [SYNTHETIC_TEXT.replace('Synthetic study.', 'Synthetic\nstudy.'), 'A second supporting passage.'])
        self.assertEqual(issues, [])

    def test_bad_quote_unknown_page_missing_evidence_all_flagged(self) -> None:
        result = paper()
        result.title.raw_text[0].page = 9
        result.method.name.raw_text[0].text = 'Invented quote'
        result.domain.raw_text.clear()
        issues = validation.review_issues(result, [SYNTHETIC_TEXT])
        self.assertEqual({issue.field for issue in issues}, {'title', 'method.name', 'domain'})
        self.assertEqual(result.method.name.value, 'hybrid method')

    def test_reversed_range_and_fractional_count_flagged(self) -> None:
        result = paper()
        setting = result.experiments[0].conditions.sample_size.value
        setting.values = [0.5]
        setting.range = models.NumericRange(minimum=500, maximum=100)
        issues = validation.review_issues(result, [SYNTHETIC_TEXT])
        self.assertTrue(any('reversed' in issue.reason for issue in issues))
        self.assertTrue(any('integers' in issue.reason for issue in issues))


class WorkbookTests(unittest.TestCase):
    def test_wide_rows_headers_arrays_and_no_experiment_paper(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'review.xlsx'
            no_experiments = record(0).model_copy(update={'paper_id': 'zero'})
            spreadsheet.export_workbook([record(2), no_experiments], path)
            workbook = load_workbook(path)
            flat, review = workbook['Flat'], workbook['Review']
            self.assertEqual(flat.max_row, 3)
            self.assertEqual(workbook['Papers'].max_row, 3)
            self.assertEqual(review.freeze_panes, 'D4')
            self.assertEqual(flat.freeze_panes, 'D2')
            self.assertTrue(flat.auto_filter.ref)
            self.assertTrue(all(merged.max_row <= 3 for merged in review.merged_cells.ranges))
            headers = [cell.value for cell in flat[1]]
            criteria = headers.index('Evaluation Criteria.Criteria Used.Value') + 1
            themes = headers.index('Author-Reported Limitations.Limitation Themes.Value') + 1
            self.assertEqual(json.loads(flat.cell(2, criteria).value), ['q_matrix_recovery', 'model_fit'])
            self.assertEqual(len(json.loads(flat.cell(2, themes).value)), 2)
            size = headers.index('Testing Conditions.Sample Size.Value') + 1
            self.assertEqual(json.loads(flat.cell(2, size).value)['values'], [500, 1000, 2000])
            data_type = headers.index('Testing Conditions.Data Type.Value') + 1
            self.assertEqual([flat.cell(i, data_type).value for i in (2, 3)], ['simulated', 'empirical'])
            workbook.close()

    def test_long_text_formula_and_control_characters(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'review.xlsx'
            result = record()
            result.bibliography = models.BibliographicMetadata(citation_key='synthetic',
                fields={'title': '=1+1'}, source='synthetic.bib', source_sha256='synthetic')
            result.paper.experiments[0].description.value = 'x' * 40000
            result.paper.experiments[0].conditions.item_quality.value = 'a\x01b'
            spreadsheet.export_workbook([result], path)
            workbook = load_workbook(path)
            self.assertTrue(workbook['Overflow'].max_row > 1)
            self.assertEqual(workbook['Flat']['F2'].data_type, 's')
            self.assertEqual(workbook['Flat']['F2'].value, '=1+1')
            workbook.close()


class PipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.inputs = self.root / 'input'
        self.inputs.mkdir()
        (self.inputs / 'synthetic.pdf').write_bytes(b'synthetic PDF placeholder')
        self.settings_path = self.root / 'settings.json'
        self.settings_path.write_text(settings().model_dump_json())
        self.client = Mock()
        self.client.responses.create.return_value = response()

    def run_pipeline(self, execute: bool = True, resume: Path | None = None,
                     source_map: Path | None = None, retry_failed: bool = False,
                     model: str | None = None, workers: int = 1,
                     bibliography_paths: list[Path] | None = None) -> int:
        with patch('pdf_text.read_pdf', return_value=[SYNTHETIC_TEXT]), patch('api.create_client', return_value=self.client):
            return pipeline.main(input_directory=self.inputs, settings_path=self.settings_path,
                limit=10, execute=execute, resume=resume, output_directory=self.root / 'output',
                source_map=source_map, retry_failed=retry_failed, model=model, workers=workers,
                bibliography_paths=bibliography_paths)

    def runs(self) -> list[Path]:
        return sorted(path.parent for path in (self.root / 'output').glob('*/manifest.json'))

    def test_strict_request_and_reuse_across_resume_and_new_runs(self) -> None:
        self.assertEqual(self.run_pipeline(), 0)
        first_run = self.runs()[0]
        first = next(first_run.glob('*/extraction.json')).read_text()
        self.assertEqual(self.run_pipeline(resume=first_run), 0)
        self.assertEqual(self.run_pipeline(), 0)
        self.assertEqual(self.client.responses.create.call_count, 1)
        last = next(self.runs()[-1].glob('*/extraction.json')).read_text()
        self.assertEqual(first, last)
        call = self.client.responses.create.call_args.kwargs
        self.assertTrue(call['text']['format']['strict'])
        self.assertFalse(call['store'])
        self.assertNotIn('FIELD DEFINITIONS', call['input'])

    def test_pdf_content_model_and_prompt_changes_invalidate_cache(self) -> None:
        self.run_pipeline()
        (self.inputs / 'synthetic.pdf').write_bytes(b'changed PDF')
        self.run_pipeline()
        new_settings = settings().model_copy(update={'model': 'another-model'})
        self.settings_path.write_text(new_settings.model_dump_json())
        self.run_pipeline()
        with patch('prompts.INSTRUCTIONS', prompts.INSTRUCTIONS + '\nChanged prompt'):
            self.run_pipeline()
        self.assertEqual(self.client.responses.create.call_count, 4)

    def test_source_map_preserves_bibliography_id(self) -> None:
        mapping = self.root / 'source_map.json'
        mapping.write_text(json.dumps([{'source': 'synthetic.pdf', 'paper_id': 'existing-ris-ID'}]))
        self.assertEqual(self.run_pipeline(source_map=mapping), 0)
        saved = models.PaperRecord.model_validate_json(next(self.runs()[0].glob('*/extraction.json')).read_text())
        self.assertEqual(saved.paper_id, 'existing-ris-ID')
        self.assertEqual(saved.experiment_ids, ['existing-ris-ID:E001'])
        self.assertEqual(saved.provenance.source, 'synthetic.pdf')

    def test_local_preparation_and_empty_pdf(self) -> None:
        self.assertEqual(self.run_pipeline(execute=False), 0)
        self.client.responses.create.assert_not_called()
        with patch('pdf_text.read_pdf', return_value=['']), patch('api.create_client') as constructor:
            result = pipeline.main(input_directory=self.inputs, settings_path=self.settings_path,
                limit=1, execute=True, resume=None, output_directory=self.root / 'empty', source_map=None, retry_failed=False)
        self.assertEqual(result, 1)
        constructor.assert_not_called()

    def test_character_limit_fails_without_request(self) -> None:
        self.settings_path.write_text(settings().model_copy(update={'max_input_characters': 5}).model_dump_json())
        self.assertEqual(self.run_pipeline(), 1)
        self.client.responses.create.assert_not_called()
        self.assertTrue(next(self.runs()[0].glob('*/pages.json')).exists())

    def test_incomplete_retained_and_not_repeated_without_explicit_retry(self) -> None:
        self.client.responses.create.return_value = response(status='incomplete')
        self.assertEqual(self.run_pipeline(), 1)
        self.assertTrue(next(self.runs()[0].glob('*/response.json')).exists())
        self.assertEqual(self.run_pipeline(), 1)
        self.assertEqual(self.client.responses.create.call_count, 1)
        self.client.responses.create.return_value = response()
        self.assertEqual(self.run_pipeline(retry_failed=True), 0)
        self.assertEqual(self.client.responses.create.call_count, 2)
        self.assertTrue(next(self.runs()[-1].glob('*/response-*.json')).exists())

    def test_completed_response_recovers_after_interrupted_canonical_write(self) -> None:
        with patch('pipeline.make_record', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.run_pipeline()
        self.assertEqual(self.run_pipeline(resume=self.runs()[0]), 0)
        self.assertEqual(self.client.responses.create.call_count, 1)

    def test_malformed_response_and_api_errors_are_retained(self) -> None:
        self.client.responses.create.return_value = response({'unexpected': 'value'})
        self.assertEqual(self.run_pipeline(), 1)
        self.assertEqual(self.run_pipeline(), 1)
        self.assertEqual(self.client.responses.create.call_count, 1)
        self.assertTrue(next(self.runs()[0].glob('*/response.json')).exists())

    def test_resume_configuration_change_rejected(self) -> None:
        self.run_pipeline()
        self.settings_path.write_text(settings().model_copy(update={'max_output_tokens': 15000}).model_dump_json())
        with self.assertRaisesRegex(ValueError, 'Resume mode'):
            self.run_pipeline(resume=self.runs()[0])

    def test_rate_limit_preserves_completed_papers_and_continues_on_rerun(self) -> None:
        import httpx
        from openai import RateLimitError
        (self.inputs / 'second.pdf').write_bytes(b'a distinct synthetic PDF')
        request = httpx.Request('POST', 'https://api.openai.com/v1/responses')
        error = RateLimitError('synthetic rate limit', response=httpx.Response(429, request=request), body=None)
        self.client.responses.create.side_effect = [response(), error, response()]
        self.assertEqual(self.run_pipeline(), 1)
        manifest = pipeline.Manifest.model_validate_json((self.runs()[0] / storage.MANIFEST_FILE).read_text())
        self.assertEqual([job.status for job in manifest.papers], [pipeline.RunStatus.EXTRACTED, pipeline.RunStatus.ERROR])
        self.assertEqual(manifest.papers[1].http_status, 429)
        self.assertEqual(self.run_pipeline(), 0)
        self.assertEqual(self.client.responses.create.call_count, 3)

    def test_resume_restores_missing_shared_cache(self) -> None:
        self.run_pipeline()
        first_run = self.runs()[0]
        cache = self.root / 'output' / storage.CACHE_DIRECTORY
        cache.rename(self.root / 'old-cache')
        self.assertEqual(self.run_pipeline(resume=first_run), 0)
        self.assertEqual(self.client.responses.create.call_count, 1)

    def test_corrupt_cache_fails_without_rebilling(self) -> None:
        self.run_pipeline()
        saved = next((self.root / 'output' / storage.CACHE_DIRECTORY).glob('*/extraction.json'))
        payload = json.loads(saved.read_text())
        payload['provenance']['source_sha256'] = 'wrong'
        saved.write_text(json.dumps(payload))
        self.assertEqual(self.run_pipeline(), 1)
        self.assertEqual(self.client.responses.create.call_count, 1)

    def test_zero_experiment_paper_and_export_rebuild(self) -> None:
        self.client.responses.create.return_value = response(paper_payload(0))
        self.assertEqual(self.run_pipeline(), 0)
        run = self.runs()[0]
        export_workbook.main(run=run)
        coverage = json.loads((run / reporting.COVERAGE_JSON).read_text())
        self.assertEqual(coverage['experiments'], 0)
        self.assertEqual(coverage['extracted_papers'], 1)
        workbook = load_workbook(run / storage.WORKBOOK_FILE)
        self.assertEqual(workbook['Flat'].max_row, 1)
        self.assertEqual(workbook['Papers'].max_row, 2)
        workbook.close()
        self.assertEqual(self.client.responses.create.call_count, 1)

    def test_duplicate_pdf_sources_do_not_create_duplicate_citation_keys(self) -> None:
        (self.inputs / 'duplicate.pdf').write_bytes((self.inputs / 'synthetic.pdf').read_bytes())
        with self.assertRaisesRegex(ValueError, 'Multiple selected PDFs'):
            self.run_pipeline()
        self.client.responses.create.assert_not_called()

    def test_generated_citation_key_is_used_in_records_manifest_and_workbook(self) -> None:
        self.run_pipeline()
        run = self.runs()[0]
        record = models.PaperRecord.model_validate_json(next(run.glob('*/extraction.json')).read_text())
        expected = citation_keys.from_paper(record.paper, 'synthetic.pdf', record.provenance.source_sha256)
        self.assertEqual(record.paper_id, expected)
        self.assertTrue(expected.startswith('Syntheticnd_'))
        self.assertEqual(record.experiment_ids, [f'{expected}:E001'])
        manifest = pipeline.Manifest.model_validate_json((run / storage.MANIFEST_FILE).read_text())
        self.assertEqual(manifest.papers[0].paper_id, expected)
        workbook = load_workbook(run / storage.WORKBOOK_FILE)
        self.assertEqual(workbook['Flat']['A2'].value, 1)
        self.assertEqual(workbook['Flat']['O2'].value, expected)
        workbook.close()

    def test_old_hash_ids_upgrade_locally_without_repeating_paid_request(self) -> None:
        self.run_pipeline()
        run = self.runs()[0]
        path = next((self.root / 'output' / storage.CACHE_DIRECTORY).glob('*/extraction.json'))
        saved = json.loads(path.read_text())
        original_provenance = saved['provenance'].copy()
        old_id = 'pdf-' + saved['provenance']['source_sha256']
        saved['paper_id'] = old_id
        saved['experiment_ids'] = [f'{old_id}:E001']
        path.write_text(json.dumps(saved))
        # Simulate a manifest written before citation-key support was added.
        manifest_path = run / storage.MANIFEST_FILE
        manifest = json.loads(manifest_path.read_text())
        manifest['papers'][0]['paper_id'] = old_id
        manifest['papers'][0].pop('bibliography_id')
        manifest_path.write_text(json.dumps(manifest))
        self.assertEqual(self.run_pipeline(resume=run), 0)
        upgraded = json.loads(path.read_text())
        self.assertTrue(upgraded['paper_id'].startswith('Syntheticnd_'))
        self.assertEqual(upgraded['provenance'], original_provenance)
        self.assertEqual(self.client.responses.create.call_count, 1)

    def test_model_override_is_saved_cached_and_leaves_settings_unchanged(self) -> None:
        original = self.settings_path.read_text()
        self.run_pipeline()
        self.run_pipeline(model='gpt-6.1-sol')
        self.run_pipeline(model='gpt-6.1-sol')
        self.assertEqual(self.client.responses.create.call_count, 2)
        self.assertEqual(self.client.responses.create.call_args.kwargs['model'], 'gpt-6.1-sol')
        manifest = pipeline.Manifest.model_validate_json((self.runs()[-1] / storage.MANIFEST_FILE).read_text())
        self.assertEqual(manifest.settings.model, 'gpt-6.1-sol')
        self.assertEqual(self.settings_path.read_text(), original)

    def test_progress_is_visible_before_blocking_api_request(self) -> None:
        output = StringIO()

        def check_progress(**kwargs: object) -> Mock:
            visible = output.getvalue()
            self.assertIn('[1/1] synthetic.pdf', visible)
            self.assertIn('Output:', visible)
            self.assertIn('waiting for the API response', visible)
            return response()

        self.client.responses.create.side_effect = check_progress
        with redirect_stdout(output):
            self.assertEqual(self.run_pipeline(), 0)
        self.assertIn('[1/1] extracted', output.getvalue())
        self.assertIn('Workbook:', output.getvalue())

    def test_client_retries_are_explicit(self) -> None:
        with patch('api.OpenAI') as constructor, patch('storage.load_api_key', return_value='synthetic-key'):
            api.create_client(settings())
        self.assertEqual(constructor.call_args.kwargs['max_retries'], 2)
        self.assertEqual(constructor.call_args.kwargs['api_key'], 'synthetic-key')

    def test_bibtex_metadata_updates_locally_without_repeating_paid_extraction(self) -> None:
        path = self.root / 'synthetic.bib'
        path.write_text('@article{synthetic, title={BibTeX title}, abstract={First abstract}, year={2024}}')
        self.assertEqual(self.run_pipeline(bibliography_paths=[path]), 0)
        run = self.runs()[0]
        saved = models.PaperRecord.model_validate_json(next(run.glob('*/extraction.json')).read_text())
        self.assertEqual(saved.paper_id, 'synthetic')
        self.assertIsNone(saved.paper.title.value)
        self.assertEqual(saved.bibliography.fields['title'], 'BibTeX title')
        schema = self.client.responses.create.call_args.kwargs['text']['format']['schema']
        self.assertNotIn('title', schema['properties'])
        path.write_text(path.read_text().replace('First abstract', 'Updated abstract'))
        self.assertEqual(self.run_pipeline(resume=run), 0)
        updated = models.PaperRecord.model_validate_json(next(run.glob('*/extraction.json')).read_text())
        self.assertEqual(updated.bibliography.fields['abstract'], 'Updated abstract')
        self.assertEqual(self.client.responses.create.call_count, 1)

    def test_drive_links_are_added_by_exporter_without_new_api_requests(self) -> None:
        self.assertEqual(self.run_pipeline(), 0)
        mapping = self.root / 'drive-links.json'
        target = 'https://drive.google.com/file/d/synthetic/view'
        mapping.write_text(json.dumps({'synthetic.pdf': target}))
        with patch('drive_links.DEFAULT_LINKS_PATH', mapping):
            export_workbook.main(run=self.runs()[0])
        workbook = load_workbook(self.runs()[0] / storage.WORKBOOK_FILE)
        self.assertEqual(workbook['Review']['D4'].value, 'synthetic.pdf')
        self.assertEqual(workbook['Review']['D4'].hyperlink.target, target)
        self.assertEqual(workbook['Review'].freeze_panes, 'D4')
        workbook.close()
        self.assertEqual(self.client.responses.create.call_count, 1)

    def test_concurrent_failures_checkpoint_on_coordinator_and_resume_from_cache(self) -> None:
        for name in ('second', 'third'):
            (self.inputs / f'{name}.pdf').write_bytes(name.encode())
        barrier, lock = Barrier(2, timeout=5), Lock()
        calls: list[int] = []
        coordinator = get_ident()
        checkpoint_threads: list[int] = []
        original_checkpoint = pipeline.checkpoint

        def request(**kwargs: object) -> Mock:
            with lock:
                calls.append(get_ident())
                number = len(calls)
            if number <= 2:
                barrier.wait()
            if number == 3:
                raise RuntimeError('Synthetic request failure')
            return response()

        def checkpoint(*args: object) -> None:
            checkpoint_threads.append(get_ident())
            original_checkpoint(*args)

        self.client.responses.create.side_effect = request
        with patch('pipeline.checkpoint', side_effect=checkpoint):
            self.assertEqual(self.run_pipeline(workers=2), 1)
        self.assertEqual(len(set(calls[:2])), 2)
        self.assertEqual(set(checkpoint_threads), {coordinator})
        manifest_path = self.runs()[0] / storage.MANIFEST_FILE
        manifest = pipeline.Manifest.model_validate_json(manifest_path.read_text())
        self.assertEqual(sum(job.status == pipeline.RunStatus.EXTRACTED for job in manifest.papers), 2)
        self.assertEqual(self.run_pipeline(resume=self.runs()[0], workers=1), 0)
        self.assertEqual(len(calls), 4)

    def test_interrupt_drains_active_requests_and_resume_reuses_saved_results(self) -> None:
        (self.inputs / 'second.pdf').write_bytes(b'second synthetic PDF')
        with patch('pipeline.wait', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.run_pipeline(workers=2)
        cache = self.root / 'output' / storage.CACHE_DIRECTORY
        self.assertEqual(len(list(cache.glob('*/extraction.json'))), 2)
        self.assertEqual(self.run_pipeline(resume=self.runs()[0], workers=2), 0)
        self.assertEqual(self.client.responses.create.call_count, 2)


if __name__ == '__main__':
    unittest.main()

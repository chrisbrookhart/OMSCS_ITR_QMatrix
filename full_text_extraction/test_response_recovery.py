"""Synthetic recovery cases preserve complete values and original paid responses."""
import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock
import unittest
from unittest.mock import patch

import models
import pipeline
import recover_response
import response_recovery as recovery
import storage
import test_extract as fixtures


def payload(count: int = 2) -> dict[str, object]:
    return json.loads(fixtures.response(fixtures.paper_payload(count)).output_text)


class PayloadRecoveryTests(unittest.TestCase):
    def test_exact_duplicate_is_removed_without_changing_experiments(self) -> None:
        data = payload()
        data['experiment_design']['assignments'].append(copy.deepcopy(data['experiment_design']['assignments'][0]))
        result = recovery.recover_paper(json.dumps(data), recovery.RecoveryMode.DEDUPLICATE_ROLES)
        self.assertEqual(len(result.paper.experiment_design.assignments), 2)
        self.assertEqual(json.loads(result.paper.model_dump_json())['experiments'], data['experiments'])
        self.assertTrue(result.actions)

    def test_conflicting_duplicate_is_not_automatically_resolved(self) -> None:
        data = payload()
        duplicate = copy.deepcopy(data['experiment_design']['assignments'][0])
        duplicate['role'] = 'supporting'
        data['experiment_design']['assignments'].append(duplicate)
        with self.assertRaisesRegex(ValueError, 'Conflicting experiment roles'):
            recovery.recover_paper(json.dumps(data), recovery.RecoveryMode.DEDUPLICATE_ROLES)

    def test_missing_role_remains_unclear_without_fabricated_evidence(self) -> None:
        data = payload()
        data['experiment_design']['assignments'].pop()
        result = recovery.recover_paper(json.dumps(data), recovery.RecoveryMode.COMPLETE_ROLES)
        assignment = result.paper.experiment_design.assignments[1]
        self.assertEqual(assignment.role, models.ExperimentRole.UNCLEAR)
        self.assertIsNone(assignment.rationale.value)
        self.assertEqual(assignment.rationale.raw_text, [])
        self.assertEqual(result.paper.experiment_design.primary_experiment_number, 1)
        self.assertIn('experiment_design.assignments[1].role', result.unresolved_fields)

    def test_complete_missing_notes_are_preserved_before_truncated_note(self) -> None:
        data = payload()
        data.pop('missing_fields')
        note = {'field_path': 'experiments[0].conditions.item_quality', 'potential_reason': 'unknown',
                'explanation': 'Reason not established.', 'evidence': []}
        text = json.dumps(data)[:-1] + ',"missing_fields":[' + json.dumps(note) + ',{"field_path":"unfinished'
        result = recovery.recover_paper(text, recovery.RecoveryMode.RECOVER_NOTES)
        self.assertEqual(len(result.paper.experiments), 2)
        self.assertEqual(len(result.paper.missing_fields), 1)
        self.assertEqual(result.paper.missing_fields[0].explanation, note['explanation'])
        self.assertIn('missing_fields', result.unresolved_fields)

    def test_unfinished_design_does_not_supply_a_main_experiment(self) -> None:
        data = payload()
        data.pop('experiment_design')
        data.pop('missing_fields')
        text = json.dumps(data)[:-1] + ',"experiment_design":{"primary_experiment_number":1,"assignments":['
        result = recovery.recover_paper(text, recovery.RecoveryMode.RECOVER_DESIGN)
        self.assertIsNone(result.paper.experiment_design.primary_experiment_number)
        self.assertTrue(all(item.role == models.ExperimentRole.UNCLEAR for item in result.paper.experiment_design.assignments))
        self.assertEqual(json.loads(result.paper.model_dump_json())['experiments'], data['experiments'])

    def test_partial_experimental_array_cannot_be_treated_as_complete(self) -> None:
        data = payload()
        fields = {name: data[name] for name in ('method', 'domain', 'limitations')}
        text = json.dumps(fields)[:-1] + ',"experiments":[' + json.dumps(data['experiments'][0]) + ',{"description":'
        with self.assertRaisesRegex(ValueError, 'Experimental content is incomplete'):
            recovery.recover_paper(text, recovery.RecoveryMode.RECOVER_DESIGN)

    def test_duplicate_top_level_keys_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, 'Duplicate JSON property'):
            recovery.complete_properties('{"method":{},"method":{}}')


class RecoveryPersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.run = Path(self.temporary.name) / 'run'
        self.folder = self.run / 'paper'
        self.folder.mkdir(parents=True)
        self.job = pipeline.PaperJob(source='synthetic.pdf', paper_id='pending', sha256='synthetic-sha',
            directory='paper', status=pipeline.RunStatus.ERROR, error='synthetic role error')
        self.manifest = pipeline.Manifest(execute=True, settings=fixtures.settings(),
            request_fingerprint='synthetic-fingerprint', papers=[self.job])
        storage.write_json(self.run / storage.MANIFEST_FILE, self.manifest)
        data = payload()
        data['experiment_design']['assignments'].append(copy.deepcopy(data['experiment_design']['assignments'][0]))
        response = fixtures.response().model_dump()
        response['output'][0]['content'][0]['text'] = json.dumps(data)
        storage.write_json(self.folder / storage.RESPONSE_FILE, response)
        storage.write_json(self.folder / storage.PAGES_FILE, [fixtures.SYNTHETIC_TEXT])

    def test_recovery_preserves_raw_response_and_survives_resume(self) -> None:
        original = (self.folder / storage.RESPONSE_FILE).read_bytes()
        with patch('api.create_client', side_effect=AssertionError('No API calls allowed')):
            record = recover_response.local_recovery(run=self.run, source=self.job.source,
                                                    mode=recovery.RecoveryMode.DEDUPLICATE_ROLES)
        self.assertEqual((self.folder / storage.RESPONSE_FILE).read_bytes(), original)
        self.assertEqual(record.recovery.source_response_sha256, storage.digest_bytes(original))
        manifest = pipeline.Manifest.model_validate_json((self.run / storage.MANIFEST_FILE).read_text())
        with patch('pipeline.extract_job', side_effect=AssertionError('Must reuse recovery')):
            result = pipeline.process_job(0, manifest, self.run, self.run, self.run / 'cache', False, Lock())
        self.assertEqual(result.record.recovery, record.recovery)
        self.assertEqual(result.job.status, pipeline.RunStatus.EXTRACTED)
        pipeline.checkpoint(manifest, self.run, result.job, result.folder, [result.record])
        self.assertTrue((self.run / storage.WORKBOOK_FILE).exists())
        backup = pipeline.Manifest.model_validate_json((self.run / recovery.BACKUP_DIRECTORY / storage.MANIFEST_FILE).read_text())
        self.assertEqual(backup.papers[0].status, pipeline.RunStatus.ERROR)

    def test_retry_import_preserves_distinct_request_fingerprint(self) -> None:
        retry = self.run.parent / 'retry'
        retry_folder = retry / 'paper'
        retry_folder.mkdir(parents=True)
        record = fixtures.record()
        record.provenance.request_fingerprint = 'retry-fingerprint'
        retry_job = self.job.model_copy(update={'status': pipeline.RunStatus.EXTRACTED})
        manifest = self.manifest.model_copy(update={'request_fingerprint': 'retry-fingerprint', 'papers': [retry_job]})
        storage.write_json(retry / storage.MANIFEST_FILE, manifest)
        storage.write_json(retry_folder / storage.RECORD_FILE, record)
        storage.write_json(retry_folder / storage.RESPONSE_FILE, fixtures.response().model_dump())
        imported = recover_response.import_retry(run=self.run, source=self.job.source, retry_run=retry)
        self.assertEqual(imported.provenance.request_fingerprint, 'retry-fingerprint')
        self.assertEqual(imported.recovery.run_request_fingerprint, 'synthetic-fingerprint')
        saved = pipeline.recovered_run_record(self.folder, self.job, 'synthetic-fingerprint')
        self.assertEqual(saved.provenance.request_fingerprint, 'retry-fingerprint')
        with self.assertRaisesRegex(ValueError, 'different run settings'):
            pipeline.recovered_run_record(self.folder, self.job, 'unrelated-fingerprint')


if __name__ == '__main__':
    unittest.main()

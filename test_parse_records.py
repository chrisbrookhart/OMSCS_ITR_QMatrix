"""Synthetic checks for candidate record labels and nonmutating updates."""

from dataclasses import asdict, replace
import unittest

from parse_records import Label, OutputRecord, SourceRecord, get_labels, update_records


def source_row(**changes):
    row = dict.fromkeys((
        "ID", "Sept ID", "Year", "Title", "Authors", "Venue", "Document type",
        "Found in", "DOI", "Abstract", "Keywords", "Language", "Screening flags",
        "Stage", "Assigned to", "Screener 1", "Screener 2", "Decision",
        "Exclusion reason", "Excluded at stage", "Notes",
    ), "")
    row.update({"ID": "synthetic", "Year": "2026", "Found in": "Scopus"})
    row.update(changes)
    return row


class RecordLabelTests(unittest.TestCase):
    def test_absent_or_empty_labels_are_independent_empty_lists(self):
        first = SourceRecord.from_csv_row(source_row())
        second = SourceRecord.from_csv_row(source_row(Labels=""))
        self.assertEqual(first.labels, [])
        self.assertEqual(second.labels, [])
        self.assertIsNot(first.labels, second.labels)

    def test_optional_labels_column_uses_string_enum_values(self):
        record = SourceRecord.from_csv_row(source_row(Labels="statistical; LLM-based"))
        self.assertEqual(record.labels, [Label.STATISTICAL, Label.LLM_BASED])
        self.assertIsInstance(record.labels[0], str)
        self.assertEqual(str(record.labels[0]), "statistical")
        with self.assertRaises(ValueError):
            SourceRecord.from_csv_row(source_row(Labels="unknown category"))

    def test_hybrid_methods_domains_and_data_types(self):
        record = SourceRecord.from_csv_row(source_row(
            Title="Expert-driven Q-matrix refinement with large language models",
            Abstract="Bayesian and neural methods for educational measurement and "
            "intelligent tutoring systems. A clinical assessment uses simulated "
            "and empirical data.",
        ))
        self.assertEqual(get_labels(record), [
            Label.EXPERT_DRIVEN, Label.STATISTICAL, Label.MACHINE_LEARNING,
            Label.LLM_BASED, Label.EDUCATIONAL_MEASUREMENT,
            Label.ITS_LEARNING_ANALYTICS, Label.PSYCHOLOGICAL_CLINICAL,
            Label.REFINEMENT, Label.SIMULATED, Label.EMPIRICAL,
        ])

    def test_tasks_match_equivalent_terms_and_unicode_hyphens(self):
        cases = [
            ("Generating a Q‑matrix", Label.GENERATION),
            ("Knowledge-component model validation", Label.VALIDATION),
            ("Refining skill models", Label.REFINEMENT),
        ]
        for title, label in cases:
            with self.subTest(title=title):
                record = SourceRecord.from_csv_row(source_row(Title=title))
                self.assertIn(label, get_labels(record))

    def test_task_labels_need_a_mapping_in_the_same_sentence(self):
        for title in ("Generating a report", "Q-matrix. Generating a report"):
            with self.subTest(title=title):
                record = SourceRecord.from_csv_row(source_row(Title=title))
                self.assertEqual(get_labels(record), [])

    def test_labels_deduplicate_and_ignore_screening_notes(self):
        record = SourceRecord.from_csv_row(source_row(
            Title="Bayesian Q-matrix validation",
            Keywords="Bayesian; statistical; Bayesian",
            Notes="clinical; large language models",
            **{"Screening flags": "machine learning"},
        ))
        self.assertEqual(get_labels(record), [Label.STATISTICAL, Label.VALIDATION])

    def test_updates_copy_records_and_are_repeatable(self):
        record = SourceRecord.from_csv_row(source_row(
            Title="Bayesian Q-matrix validation", Notes="Existing note",
            Labels="LLM-based",
        ))
        original = asdict(record)
        records = [record]
        updated = update_records(records)
        self.assertIsNot(updated, records)
        self.assertIsNot(updated[0], record)
        self.assertIsNot(updated[0].labels, record.labels)
        self.assertEqual(asdict(record), original)
        self.assertEqual(updated[0].labels, [Label.STATISTICAL, Label.VALIDATION])
        self.assertEqual(updated[0].notes, "Existing note")
        self.assertEqual(update_records(updated), updated)
        self.assertEqual(update_records([]), [])

    def test_export_notes_use_strings_and_conditional_pipe(self):
        record = SourceRecord.from_csv_row(source_row(Labels="statistical; LLM-based"))
        suffix = "Labels: statistical; LLM-based"
        self.assertEqual(OutputRecord.from_record(record).notes, suffix)
        self.assertEqual(OutputRecord.from_record(replace(record, notes="Existing note")).notes,
                         "Existing note | " + suffix)
        self.assertEqual(OutputRecord.from_record(replace(record, labels=[], notes="Keep")).notes,
                         "Keep")


if __name__ == "__main__":
    unittest.main()

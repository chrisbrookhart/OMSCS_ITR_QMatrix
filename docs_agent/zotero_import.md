# Zotero import from the new extraction

The current combined source is `input/20261009/Candidate Records - Final Search.xlsx`, worksheet `Records`. The historical CSV is `input/20261008/input.csv`. The workbook contains 1,389 candidate rows; the old 836-record total in historical documentation does not describe this new extraction.

Generate a fresh local import with Python 3.10 or newer, without additional dependencies:

```bash
python prepare_zotero.py
```

Outputs are `output/zotero_<timestamp>/candidates.ris` and `audit.json`. The audit records the source checksum, count, missing metadata and database memberships. These files remain ignored by Git.

In Zotero Desktop, select **File → Import… → A file**, choose `candidates.ris`, and import into a new collection. Check that the imported item count matches the audit. See [Zotero’s import instructions](https://www.zotero.org/support/kb/importing_standardized_formats).

The converter uses the already combined candidate workbook, rather than importing overlapping raw database batches. It writes each workbook row once, with no additional deduplication, eligibility filtering or metadata lookup. It retains title, authors, venue, year, DOI, abstract, language and keywords. Trailing numeric author identifiers are removed. Source IDs, database memberships, original document type and screening fields are retained as notes. Suggested labels use the existing keyword rules and become tags prefixed `Suggested label:`; they require human review. Missing bibliographic fields remain absent. No PDFs are attached, and no Zotero library is modified by the script.

Article/review types map to journal articles, conference types to conference papers, chapters to book sections, books to books, and thesis/dissertation types to theses. Other types use generic RIS records and need review after import. Multiline text is flattened within fields to prevent accidental RIS tag interpretation.

Choose another combined XLSX or historical candidate CSV with:

```bash
python prepare_zotero.py input/20261008/input.csv
```

CSV reading requires pandas from `requirements.txt`. The existing `parse_records.py` now also defaults to the new workbook; its per-database CSV writing still requires pandas. Native RIS/NBIB/EndNote workflows retain their own explicit input directories and do not parse the mixed CSV/BibTeX/XLS files in `input/20261009`.

Synthetic verification:

```bash
python -m unittest test_prepare_zotero test_parse_records test_prepare_rayyan test_label_exports -q
```

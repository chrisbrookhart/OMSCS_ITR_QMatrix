# Full-text extraction pilot with GPT-6 Luna

The new project is `full_text_extraction/`. It defaults to the 21 PDFs currently in `input/full_text/`, uses the OpenAI Responses API, and selects `gpt-6-luna` with low reasoning effort. Model access depends on your API project. The [official model page](https://developers.openai.com/api/docs/models/gpt-6-luna) confirms the model ID and structured-output support; the implementation follows the [structured-output guide](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses).

## 1. Install and inspect the local preparation

Run from the repository root:

```bash
uv sync --project full_text_extraction
full_text_extraction/.venv/bin/python full_text_extraction/extract.py --limit 1
```

Without `--execute`, the command extracts text locally and makes no API calls. Inspect the new directory under `output/full_text_extraction/`: `manifest.json` lists page counts, text size, sparse pages and errors; each paper folder has `paper.txt`, `pages.json` and `pdf_warnings.log`. Page markers use PDF page positions starting at 1, not printed page numbers.

Prepare all the current papers locally:

```bash
full_text_extraction/.venv/bin/python full_text_extraction/extract.py --limit 21
```

Scanned PDFs require separate OCR; this skeleton does not perform OCR. Text extraction can scramble tables, formulas and multiple columns, so check the prepared text. Empty documents fail. Papers above the configured character limit fail instead of being truncated. Sparse-page flags help identify problems but do not establish extraction quality.

## 2. Review the fields

Edit `full_text_extraction/taxonomy.json` for the versioned RQ1–RQ4 field definitions and controlled categories; `settings.json` selects this taxonomy and defines the model, reasoning effort and token limits. See the [taxonomy and screening plan](extraction_taxonomy.md) for definitions, missingness rules and the hybrid screening recommendation.

The taxonomy covers 31 basic, screening and RQ fields, including separate item/attribute counts, simulation misspecification and item quality, every named RQ3 criterion, and author-reported limitations with provisional themes. Each field includes status, value and PDF-page evidence; categorical fields use enum lists in `typed_value`. Narrative `value` and evidence remain alongside typed scalars/lists and condition-specific numeric observations. Automatic quote checks flag review needs rather than determining correctness or eligibility.

## 3. Set your OpenAI API key

The existing key has been moved from the repository-root `config.py` to `full_text_extraction/config.py`. The root file retains the database-search settings. The extraction config is ignored by Git; `config.py.template` contains only an empty placeholder.

On a fresh checkout, run this only if the local config does not already exist:

```bash
cp full_text_extraction/config.py.template full_text_extraction/config.py
```

Edit `full_text_extraction/config.py` and fill in `OPENAI_API_KEY`. Ensure API billing and GPT-6 Luna access are available for your API project. The program loads this config from its own project folder regardless of your working directory, then passes the key directly to the OpenAI client. It does not use an environment-variable key or the root database config. Local preparation works without credentials. The config is never copied into run outputs.

The client accepts an explicit key through its `api_key` parameter; see the [official OpenAI Python documentation](https://developers.openai.com/api/reference/python).

## 4. Run one paper, review, then expand

```bash
full_text_extraction/.venv/bin/python full_text_extraction/extract.py --limit 1 --execute
```

This sends the locally extracted full paper text to OpenAI and incurs API usage. Inspect `extraction.json` alongside the PDF and check field definitions before expanding:

```bash
full_text_extraction/.venv/bin/python full_text_extraction/extract.py --limit 21 --execute
```

Files are selected recursively in sorted path order. `--limit` defaults to 1. To select a particular paper, put a copy in a separate ignored input folder and pass `--input input/pilot_full_text --limit 1`.

Every invocation creates a fresh output directory. Successful papers get `extraction.json` and a raw `response.json`; `review.csv` combines extracted fields for manual review with narrative and typed-value columns; `typed_values.jsonl` preserves native data types, and `numeric_observations.csv` provides separate numeric cells for spreadsheet review. `coverage.json` and `coverage.csv` summarize field coverage, applicability, evidence checks and codes; `manifest.json` records source file hashes, response IDs, actual token usage, errors and evidence warnings. The run saves the settings, schema, prompt and script checksum. PDFs and all derived paper data remain in ignored `input/` and `output/` directories.

The script makes one request per selected readable paper and disables automatic SDK retries. It continues after a paper fails and exits nonzero if any fail. Inspect errors before rerunning: rerunning processes the selected set again and can incur new charges. To resume an interrupted API run without repeating successful papers, add `--resume output/full_text_extraction/<run-directory>` with the same `--execute`, input, taxonomy, settings and limit. Unsuccessful requests can be retried and billed again. There is no automatic chunking. The output-token cap limits each response but is not a dollar budget; configure API spend controls and inspect usage from the pilot.

Requests use `store=False`. The command still transmits paper text to the API; this setting does not mean the processing is local or define every aspect of API retention. See [OpenAI API data controls](https://developers.openai.com/api/docs/guides/your-data).

## Project checks

```bash
cd full_text_extraction
.venv/bin/python -m unittest test_extract -v
```

Tests use synthetic text and a mocked OpenAI client. They check evidence validation, request configuration, saved outputs and empty-PDF handling. No paid API test is included.

## Initial local check

During the initial skeleton check on 2026-10-13, local preparation completed for all 21 PDFs without errors and three synthetic tests passed. That initial check used no API tokens. The subsequent RQ taxonomy pilot is documented separately in [the pilot report](full_text_pilot.md).

Regenerate coverage for a saved run:

```bash
full_text_extraction/.venv/bin/python full_text_extraction/coverage_report.py output/full_text_extraction/<run-directory>
```

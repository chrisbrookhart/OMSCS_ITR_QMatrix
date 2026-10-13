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

Edit `full_text_extraction/settings.json` before spending API tokens. It defines the model, reasoning effort, output-token cap and field descriptions.

The starter fields cover title, publication year, Q-matrix contribution, method family, domain, data type, sample size, items and attributes, response type, diagnostic model, evaluation and benchmarks, and author-reported limitations. These are a pilot subset of the working document's RQs. Attribute structure, simulation misspecification and item quality can be added as new field names with descriptions.

Each field returns `reported`, `not_reported` or `unclear`, a concise value, and short evidence quotes with PDF page numbers. Missing values stay null. The script flags unmatched evidence and unclear values for review. Matching a quote verifies its location, not the correctness of the interpretation. Extraction does not determine eligibility.

## 3. Set your OpenAI API key

Create an API key for your OpenAI project and ensure API billing and GPT-6 Luna access are available. In bash, enter the key without placing it in shell history:

```bash
read -rsp 'OpenAI API key: ' OPENAI_API_KEY
export OPENAI_API_KEY
printf '\n'
```

The program reads `OPENAI_API_KEY` from your environment. It does not read `.env` files or the database-search `config.py`. Keep the key out of source files and documentation.

## 4. Run one paper, review, then expand

```bash
full_text_extraction/.venv/bin/python full_text_extraction/extract.py --limit 1 --execute
```

This sends the locally extracted full paper text to OpenAI and incurs API usage. Inspect `extraction.json` alongside the PDF and check field definitions before expanding:

```bash
full_text_extraction/.venv/bin/python full_text_extraction/extract.py --limit 21 --execute
```

Files are selected recursively in sorted path order. `--limit` defaults to 1. To select a particular paper, put a copy in a separate ignored input folder and pass `--input input/pilot_full_text --limit 1`.

Every invocation creates a fresh output directory. Successful papers get `extraction.json` and a raw `response.json`; `review.csv` combines extracted fields for manual review. `manifest.json` records source file hashes, response IDs, actual token usage, errors and evidence warnings. The run saves the settings, schema, prompt and script checksum. PDFs and all derived paper data remain in ignored `input/` and `output/` directories.

The script makes one request per selected readable paper and disables automatic SDK retries. It continues after a paper fails and exits nonzero if any fail. Inspect errors before rerunning: rerunning processes the selected set again and can incur new charges. There is no resume mechanism or automatic chunking in this starter project. The output-token cap limits each response but is not a dollar budget; configure API spend controls and inspect usage from the pilot.

Requests use `store=False`. The command still transmits paper text to the API; this setting does not mean the processing is local or define every aspect of API retention. See [OpenAI API data controls](https://developers.openai.com/api/docs/guides/your-data).

## Project checks

```bash
cd full_text_extraction
.venv/bin/python -m unittest test_extract -v
```

Tests use synthetic text and a mocked OpenAI client. They check evidence validation, request configuration, saved outputs and empty-PDF handling. No paid API test is included.

## Initial local check

On 2026-10-13, local preparation completed for all 21 PDFs without errors. Three synthetic tests passed. No live API extraction was run and no API tokens were spent. Review text quality before the paid one-paper pilot.

# Evidence-grounded SLR extraction

The existing `full_text_extraction/extract.py` command now produces version 2 paper
and experiment records for *Recent Advancements in Q-Matrix Generation Across
Application Domains*. Run these commands from `check-in-2/`:

```bash
uv sync --project full_text_extraction
full_text_extraction/.venv/bin/python full_text_extraction/extract.py --limit 1
full_text_extraction/.venv/bin/python full_text_extraction/extract.py --limit 1 --execute
```

Preparation is local by default. `--execute` authorizes a paid request for each
uncached paper. The model remains `gpt-6-luna`; configure model, reasoning, input
character limit, output-token limit, timeout and bounded SDK retries in
`full_text_extraction/settings.json`. Credentials still come exclusively from the
ignored `full_text_extraction/config.py`, using `config.py.template` on a fresh
checkout. Cached-only and preparation runs need no credentials.

Progress is printed immediately to stdout, including the selected model, output
folder, `[current/total]` paper, preparation, cache reuse, API submission, validation,
checkpointing and completion or failure. A waiting message reports elapsed time
every 15 seconds during an API request (including SDK retries), even when stdout
is redirected. No additional requests are made to report progress.

Use `--help` to see default paths and examples. `--limit` still defaults to **one
PDF**. To select a model without editing the settings file:

```bash
uv run full_text_extraction/extract.py --execute --model gpt-6.1-sol
uv run full_text_extraction/extract.py --execute --model gpt-6-luna --limit 21
```

`--model` accepts only `gpt-6.1-sol` and `gpt-6-luna`, the documented
[Sol](https://developers.openai.com/api/docs/models/gpt-6.1-sol) and
[Luna](https://developers.openai.com/api/docs/models/gpt-6-luna) API names.
Omitting it preserves the model in `--settings`. An override is saved in the run's
settings and cache identity without changing the source settings file. Resuming
an overridden run requires the same override (or equivalent settings). The default
output root is `check-in-2/output/full_text_extraction/`, with a timestamped run
folder and a shared `cache_v2/` beneath that root; `--output` changes the root.

## Inspect the implementation

The prior implementation used a single Responses API call, flat paper-level fields
from `taxonomy.json`, a manually constructed schema, quotation checking, saved
responses, manifests, resume support, and CSV/JSONL/coverage exports. The refactor
retains the existing CLI, environment, local credential handling, PDF preparation,
physical page numbering, Responses API and raw response persistence. It replaces
flat fields with the following focused modules:

- `vocabulary.py`: controlled categories, including editable limitation themes.
- `models.py`: required, extra-forbidden Pydantic fields; paper/experiment hierarchy.
- `prompts.py`: RQ1–RQ4 instructions, experiment boundaries and evidence rules.
- `pdf_text.py`: page extraction and text preparation without truncation.
- `api.py`: one strict JSON Schema request per whole paper.
- `validation.py`: non-destructive field, numeric and quotation review checks.
- `storage.py`: settings, stable source mapping, atomic JSON writes and hashing.
- `citation_keys.py`: readable BibTeX-safe paper IDs, separate from cache identity.
- `progress.py`: flushed progress messages and API-wait heartbeats.
- `pipeline.py`: caching, checkpoints, provenance and orchestration.
- `spreadsheet.py`: formatted review and flat analysis worksheets.
- `reporting.py`: status and review-flag coverage counts in JSON and CSV.

A second API stage would add cost and require reconciling independently extracted
paper context. One full-paper request is simpler and lets the model identify
experiments before filling fields in the same response. The request follows the
[official structured output requirements](https://developers.openai.com/api/docs/guides/structured-outputs):
all properties are required (nullable when missing), object properties are closed,
and the schema uses the supported object/array/enum/anyOf types. Tests check that
the generated schema is already equivalent to the SDK strict-schema conversion.

## Paper IDs and source associations

Supply existing bibliography/RIS IDs verbatim with `--source-map input/paper_sources.json`.
The JSON file is an array, for example:

```json
[{"source":"folder/synthetic.pdf","paper_id":"Smith2024QMatrix"}]
```

`source` is a relative POSIX path from `--input`. Explicit bibliography IDs remain
unchanged. Otherwise, Zotero-style `Author - Year - Title.pdf` source names produce
BibTeX-safe keys such as `Smith2024QMatrixGenerationAcross_ab12cd34`. Only the first
creator label is used; name particles are preserved. These filename components
construct an identifier; they do not populate evidence-grounded paper fields.
For other source names, IDs use the extracted short title and year, such as
`QMatrixGeneration2024_ab12cd34`. Keys use up to four significant title words and
an eight-character source hash suffix to distinguish documents. Missing years use
`nd`; a missing title falls back to the filename. No author name or year is guessed.
To use an exact existing key such as `Smith2024QMatrix`, supply it in the source map.

The original relative source path and full PDF hash are always retained. Internal
source identity, rather than the displayed citation key, determines the cache
location. Existing hash-based version 2 records are relabeled locally when reused;
this requires no new API request and preserves extraction provenance. Explicit
source-map IDs remain authoritative; changing that association changes its cache
identity. Select one source PDF per study; duplicate selected source identities or
bibliography IDs are rejected. Citation-key collisions require distinct source-map
IDs rather than silently combining records.

Experiment IDs are `<paper-id>:E001`, `E002`, etc., in the saved whole-paper
experiment order. They remain stable on cached reruns; an explicitly changed
extraction can identify different boundaries. Canonical JSON, manifest rows and
spreadsheet identifiers use the same citation key.

## Records and evidence

Each paper contains wrapped title, DOI, publication year, investigated method,
domain, paper limitations, and an experiment array (possibly empty). Experiments
contain their description, method/domain overrides, conditions, evaluation entries
and experiment limitations. The pipeline supplies IDs; they are identifiers rather
than claims extracted from the paper. Each extracted field has `value`, `other`,
`raw_text`, and one of `extracted`, `not_reported`, `not_applicable`, `ambiguous`.
Null means missing; zero remains a real number. Evidence is an array of `{page,
location, text}`. Page numbers are **1-based physical PDF pages**, never printed
page numbers. Unknown locations/pages remain null and are flagged for review.

Numeric settings preserve explicit value sets or ranges, units and condition labels.
Misspecification percentages remain percentages; no hidden conversion occurs.
Diagnostic models pair canonical names with the originally reported name, including
unknown models. Evaluations pair each criterion with its own metric field.
Limitations pair themes with descriptions and their original evidence. The enum
schema and prompt define the exact requested controlled vocabularies. There is no
assumed mapping of the five domain categories to three broader domains; define that
mapping during analysis when the three domain definitions are available.

Paper method/domain fields remain separate in JSON. For export only, each
experiment method subfield and domain inherits its paper counterpart when its
status is `not_reported`. Explicit, ambiguous and inapplicable overrides are kept.
Paper limitations are included alongside experiment limitations for review, and
retain their scope in canonical JSON. Baselines are excluded from investigated
method categories. Parameter sweeps stay within an experimental design.

Quote checks normalize whitespace only and compare each quotation with its stated
PDF page. They do not establish whether a quotation semantically supports a
category or every secondary value. All non-null primary/secondary values require
evidence, and missing evidence, ambiguous status, unverified quotations, missing
locations and invalid numeric settings produce field-specific `review_issues`.
Values are preserved for human correction, never silently dropped. PDF text
extraction can scramble tables and columns; table locations must identify the
table and row/column context, and reviewers should check the PDF. OCR is not
included. Empty PDFs and documents over the character limit fail without a request.

## Outputs, caching and interrupted runs

Runs are under `output/full_text_extraction/<timestamp>/`. Each contains settings,
schema, prompt, `manifest.json`, `extraction.xlsx`, and per-paper directories with
`pages.json`, `paper.txt`, `pdf_warnings.log`, raw `response.json` and canonical
`extraction.json`. Raw responses preserve API usage, refusals and incomplete output.
`coverage.json` and `coverage.csv` retain coverage reporting for the new hierarchy.
They count field observations (array entries remain observations), statuses and
flagged fields, and give selected/extracted/failed paper and experiment totals.
Empty arrays contribute no field observations. These counts are not study prevalence
or human-validated accuracy.
Canonical provenance records model, versions, request fingerprint, timestamp,
source/hash, response ID and page convention. Derived study data stay ignored.

A shared `cache_v2/` under the output root reuses completed records across new runs.
The cache identity includes source path, PDF content hash, paper ID, complete model
settings, prompt and schema. Unchanged reruns reuse canonical records, including
the original timestamp. `--resume <run>` requires unchanged selected PDFs, settings,
IDs, prompt and mode; per-paper run checkpoints also restore a missing shared cache.
Atomic writes protect JSON from interrupted replacement. A saved completed response
can recover an interrupted canonical write without another paid call. Do not run
multiple writers against the same cache/run at once.

SDK retries cover transient API failures and rate limits (`max_retries`, default 2).
Per-paper errors are checkpointed; remaining papers continue and the command exits
nonzero if any paper failed. Partial/malformed/refused responses remain inspectable;
they are not automatically re-requested. After inspection, `--retry-failed` archives
the raw response and permits another paid attempt. There is no guaranteed API
idempotency if processing stops after the server bills a request but before its
response reaches disk. Keep the output directory for reliable reuse.

Old flat pilot runs cannot safely acquire experiment boundaries without a new
extraction. They are preserved, not automatically converted or treated as new
cache entries. The historical `taxonomy.json`, `export_typed.py`,
`coverage_report.py` and `legacy_review.py` only support inspecting/regenerating old
flat exports. They are not used by the new extraction path.

## Workbook interpretation

`Review` has category, variable and Value/Other/Raw Text header rows. Three header
rows faithfully express the three requested levels. `Flat` uses unique
`Category.Variable.Component` headers and identical data for filtering and analysis.
Each has exactly one row per real experiment, sorted/grouped by paper; paper
metadata repeats. Identifying columns and headers are frozen, filters are enabled,
text wraps and alternating paper fills aid review. Only header cells are merged.

Arrays and structured numeric settings use compact JSON. Evaluation and limitation
Value cells are arrays, Other cells are aligned arrays of arrays, and Raw Text
entries use matching 1-based indexes. No arbitrary primary criterion/limitation is
selected. Source path and IDs are repeated as identifying columns.

`Papers` preserves every paper, including those without experiments, with canonical
paper/provenance JSON. `Field Status` exposes statuses and export inheritance.
`Manual Review` lists validation issues. `Overflow` preserves complete text in
ordered chunks when Excel's 32,767-character cell limit is exceeded; the original
cell links by reference text. Formula-looking strings are literal text. XML-invalid
control characters are escaped in cells; canonical JSON preserves original text.

After editing a run's canonical JSON for review, regenerate the workbook locally:

```bash
full_text_extraction/.venv/bin/python full_text_extraction/export_workbook.py output/full_text_extraction/<run>
```

The exporter uses saved issues/statuses, so update those alongside corrections.
Keep human-corrected run files separate from the shared machine-extraction cache;
a later extraction run may copy the cached machine record over its run copy.

## Tests

```bash
full_text_extraction/.venv/bin/python -m unittest discover -s full_text_extraction -v
```

Tests use synthetic text and mocked clients, covering schema strictness,
serialization, zero/one/many experiments, sweeps, hybrid methods, inheritance,
criteria/limitations, statuses, multiple quotations, ranges, empirical/simulated
conditions, workbook preservation/overflow, source IDs, cache invalidation/reuse,
resume and interrupted-response recovery. No live API calls are required.

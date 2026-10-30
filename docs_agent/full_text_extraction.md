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
The current extraction defaults are Luna with max reasoning, an 80,000-token
output ceiling and a 1,200-second request timeout. An allowance is a ceiling;
actual token usage can be lower. Saved settings preserve earlier run parameters.

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

`--model` accepts `gpt-6-sol`, `gpt-6.1-sol` and `gpt-6-luna`, the documented
[Sol](https://developers.openai.com/api/docs/models/gpt-6.1-sol) and
[Luna](https://developers.openai.com/api/docs/models/gpt-6-luna) API names.
Omitting it preserves the model in `--settings`. An override is saved in the run's
settings and cache identity without changing the source settings file. Resuming
an overridden run requires the same override (or equivalent settings). The default
output root is `check-in-2/output/full_text_extraction/`, with a timestamped run
folder and a shared `cache_v2/` beneath that root; `--output` changes the root.

Use `--workers 4` to process up to four papers concurrently. The default is one;
the supported range is 1–128. More than 16 workers requires `--tokens-per-minute`
with the observed account limit. For example, `--workers 110
--tokens-per-minute 2000000` permits all selected papers to be in flight, while
pacing request starts at 80% of that limit. At an 80,000-token reservation this is
about one request every three seconds. Longer estimated inputs are paced more
slowly. The input estimate uses total PDF/prompt/schema characters divided by
three; server token accounting remains authoritative and SDK retries still apply.
This spreads admissions over minutes rather than submitting one large burst.
Each worker owns a separate paper cache folder, while
one coordinator writes the manifest, workbook and coverage reports. PDF text
preparation is serialized because its warning logger is process-wide. Requests
and validation can proceed concurrently. Heartbeats identify their source paper.
Account request/token limits still apply; SDK retries handle transient rate limits.
Changing worker count does not change the request fingerprint or invalidate caches.
Do not start a second process writing the same run or cache.

To change concurrency, interrupt the coordinator once, allow active request
threads to finish and save their cache records, and wait for the process to exit
before resuming with the new worker count. A second interrupt can abandon active
responses. Saved request fingerprints exclude scheduling options, so completed
cache records remain reusable when worker count or pacing changes. Resume also
restores a previously saved token-rate limit unless explicitly overridden.

Set `reasoning_effort` and `max_output_tokens` in a settings JSON file, then pass
it with `--settings`. The token allowance covers reasoning and returned JSON
together. High reasoning effort may consume a small allowance before producing
any visible output. A larger allowance is a ceiling, not a requirement to spend
every token. Inspect saved `response.json` usage and `incomplete_details` before
changing limits or reissuing requests. Configuration changes create separate cache
identities, so token-budget comparisons intentionally make new paid requests.

## Token-budget pilot

Test a small local sample before changing all papers. Include a long-output paper,
a paper with many review issues, and a PDF that previously caused preparation
problems. Keep the same revised prompt, schema, input files and reasoning effort
across the compared output limits. Use separate settings files and run folders.
Compare completed records, truncation, reasoning/visible tokens, field coverage
and quotation issues. Missing counts and review flags do not prove factual accuracy;
human inspection of evidence and experiment boundaries remains necessary.

The local reporter reads saved runs without API calls:

```bash
full_text_extraction/.venv/bin/python full_text_extraction/token_budget_report.py \
  --runs output/full_text_extraction/<pilot-run-1> output/full_text_extraction/<pilot-run-2> \
  --output output/luna_max_token_test
```

It writes local CSV/JSON comparisons and recommends the smallest tested max-effort
limit that completes every sample with at least 20% unused allowance. If no tested
limit has that reserve, it separately identifies the smallest successful tested
limit and suggests a larger ceiling from observed usage, rounded up to 10,000
tokens. That derived ceiling is not itself a tested result. This is a sample-based
budget recommendation, not a universal optimum or accuracy score.
Historical low-effort results used an older prompt, so they are a contextual
baseline rather than a controlled comparison of reasoning effort alone.

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

Pass `--bibliography input/library.bib` (or several files after that option) to
load paper metadata locally with BibTeX parsing, string expansion and LaTeX-to-
Unicode conversion. Citations, abstracts, title, authors, year, venue, DOI and URL
come exclusively from these entries. They have ordinary single workbook columns,
not evidence/secondary-value triplets. The complete parsed entry and bibliography
path/hash remain in `Papers`; `Bibliography Matches` records the matching basis and
alternative duplicate keys. Unmatched entries remain blank, without LLM fallback.

Associations use explicit source-map keys, source filenames/attachment paths,
DOIs on the first PDF page, then exact normalized titles in the first two pages.
Different DOIs or otherwise ambiguous works are rejected. Duplicate entries for
the same work prefer an exact title match, an available abstract, then metadata
completeness with a deterministic citation-key tie break. Values come from the
selected entry rather than being merged or generated. The supplied bibliography
is not modified. Changing bibliography metadata alone does not require new API
requests; a cached record can be associated and relabeled locally.

To revise only the workbook and preserve the existing version:

```bash
full_text_extraction/.venv/bin/python full_text_extraction/export_workbook.py \
  output/full_text_extraction/<run> --bibliography input/library.bib \
  --output output/full_text_extraction/<run>/extraction_revised.xlsx
```

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

Current requests extract investigated method, domain, paper limitations, and an
experiment array (possibly empty). BibTeX metadata is stored separately. Legacy
canonical title/DOI/year wrappers remain readable for compatibility; new requests
leave those slots empty and never use them to populate workbook metadata. Experiments
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
Malformed Unicode surrogate pairs from PDF text extraction are combined when
valid; isolated surrogate characters become Unicode replacement characters.
Affected physical page numbers are logged in `pdf_warnings.log` for review.

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

## Audited recovery of saved responses

`recover_response.py` performs only an explicitly selected local repair. It never
submits API requests, rewrites raw responses, or edits shared machine caches.
Available modes are:

- `deduplicate_roles`: remove exactly identical role assignments; reject conflicts.
- `complete_roles`: retain missing roles as unclear with null rationale and no invented evidence.
- `recover_notes`: preserve complete scientific fields, roles and complete missing-field
  assessments before a truncated assessment; unavailable explanations stay unknown.
- `recover_design`: preserve complete scientific fields while leaving unfinished
  role/design information unclear, without inferring a main experiment.

Recovery uses JSON decoding of complete top-level values and complete assessment
array entries, followed by schema and role-coverage validation. A partially written
experimental array cannot be declared complete. Inspect each case before selecting
a mode. Local recovery does not establish factual accuracy or resolve review flags.

```bash
full_text_extraction/.venv/bin/python full_text_extraction/recover_response.py \
  output/full_text_extraction/<run> --source synthetic.pdf --mode complete_roles
```

Each recovered run record carries a `recovery` audit: raw response path, hash and
status, recovery timestamp, actions, unresolved fields, and the parent run's
request fingerprint. Per-paper `recovery.json` and `recovered_payload.json` files
retain local details. The original manifest is saved once under `recovery_original/`.
The workbook's `Recovery` sheet displays the audit, and `Manual Review` retains
unresolved issues. Missing value comments continue to use cautious unknown notes.

An explicitly completed retry can be imported with `--retry-run <retry-run>` in
place of `--mode`. Source hashes must match. The retry's actual request fingerprint
and provenance remain intact even when its token allowance differs from the parent
run. The original unsuccessful response remains preserved in the parent folder.
Audited run records take precedence over shared caches on resume, preserving local
repairs and retry imports. Changed parent request settings reject the recovery
rather than silently treating it as a fresh model result. Rebuild the workbook with
`export_workbook.py` after applying recoveries or imports.

## Workbook interpretation

`Review` has category, variable and Value/Other/Raw Text header rows. `Flat` uses
unique `Category.Variable.Component` headers. Both start with paper index (1–n),
experiment index (1–k within each paper), citation, PDF filename, and abstract. Papers sort by
source path; experiments display the primary/reference row first, numbered one.
Canonical experiment IDs are retained separately and do not change with display
order. Each sheet has one row per real experiment. Columns 1–3 and headers are frozen, filters are
enabled, and text wraps. Only header cells are merged.

The Filename column (D) links to the existing Drive file using the local
`input/pdf_drive_links.json` object, whose keys are PDF filenames and values are
Drive URLs. Exact relative source-path keys take precedence over basename keys.
Review, Flat and Paper Summary all receive the links. Missing mappings leave a
plain filename. Columns 1–3 remain frozen; filename and abstract scroll. The loader
never contacts Drive or changes file permissions, and the map stays untracked.

Checkpoint exports and the standalone exporter use the map automatically when
present. To use another map, pass `--pdf-drive-links input/custom_links.json` to
`export_workbook.py`. Rebuilding a workbook changes no model requests or cache
identity and does not incur API usage. Wait until an active pipeline writer exits
before replacing its workbook, or export a snapshot to a separate output path.

Paper colors alternate between blue and green, each with exactly two shades.
Headers have a uniform fill. Experimental Other columns are narrow and empty
secondary arrays display as blank cells. Each paper has a color block:
its primary main experiment appears first in a darker shade;
additional main or supporting experiments appear underneath in lighter shades.
`Review` uses `(same)` for cells equal to the primary row, provided field statuses
also match. Missing values are never converted to `(same)`. Evidence is compressed
only when the evidence text itself matches. `Flat` always retains explicit values.

`Paper Summary` provides one representative experiment per paper and includes
papers without experiments. It does not combine incompatible conditions across
experiments. The study-structure column identifies papers with multiple main
experiments; consult their other rows before treating the summary as study-level
coverage. `Experiment Roles` records the model's rationale, exact evidence and
status for main/supporting/unclear classifications. Independent central studies
remain main experiments, even when another is selected as the summary row.

New requests use schema/prompt 2.3, adding experiment-design assignments and
missing-field assessments while removing bibliographic metadata from the LLM
response schema. Existing 2.0 canonical records remain exportable.
They have no role classification: the first experiment is explicitly labeled as
an unclassified reference, never silently called the main experiment. New prompts
invalidate paid-request caches and require a new run instead of resuming a 2.0 run.

`Missing Fields` lists missing primary values, their statuses, potential reasons,
supporting evidence and review actions. Intentionally inherited method/domain
overrides are excluded when a reported paper-level value supplies them. Reasons
such as a possible table/figure or extraction issue are hypotheses, not imputed
values or proven causes. Unsupported speculation, invalid field paths, duplicate
assessments and unverified quotations are flagged for review. Without an assessment,
the reason remains unknown. A useful review sequence is to check the cited PDF
section, inspect tables/figures and supplements, then retain missing if unresolved.
Blank experimental value cells also carry comments explaining their status and
available reason. Fields can legitimately be unreported, structurally inapplicable,
or outside the taxonomy. The prompt explicitly forbids nearest-category guesses,
invented conditions, and using `other` simply to fill a cell. An outside-taxonomy
note describes the mismatch without assigning an unsupported category. These gaps
do not fail a paper's extraction. Any verification is optional; retain a blank
when no value is justified. Explanations never replace canonical null values.

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

# CSV conversion

For new manual searches, use the [native export and Rayyan workflow](rayyan_exports.md) and [Colab labeling notebook](colab.md) to preserve additional metadata without converting to this older CSV schema.

`parse_records.py` converts the combined candidate records into one CSV per database. Output columns match `input/excel-example.csv`; each input record is assigned to its alphabetically first database.

## Run from the repository root

Use Python 3.10 or newer and uv. The dependencies are listed in `requirements.txt`.

CSV conversion does not need API credentials or `config.py`. That private file is used by the separate database search runner; see the [usage and setup](usage.md#api-credentials) for configuration.

The normal command is:

```bash
uv run --no-project --with-requirements requirements.txt python parse_records.py
```

The command reads `input/input.csv`, applies the shared title/abstract/keyword labeling rules, and writes one CSV per assigned database. To select another input or output location:

```bash
uv run --no-project --with-requirements requirements.txt python parse_records.py other.csv --output outputs
```

Use `--help` to display the CLI arguments without processing records.

## Input and row structures

The input must have the column names used by `input/input.csv`, including capitalization and spaces. `read_records()` uses pandas to read UTF-8 CSVs, including files with a byte-order mark. It reads cells as strings and preserves empty cells instead of converting them to `NaN`.

Each row becomes a frozen `SourceRecord` through `SourceRecord.from_csv_row()`:

- `Year` becomes an integer, or `None` when empty.
- `Authors`, `Found in`, and `Keywords` become tuples split on semicolons. Whitespace around each entry is stripped; empty entries are removed.
- Other source fields remain strings.
- `labels` is a separate list of string-valued `Label` enum members. It starts empty when the optional `Labels` column is absent or blank. If supplied, that column uses semicolon-separated enum values; unknown values raise `ValueError`.

`OutputRecord` is also a frozen dataclass. Its `from_record()` class method accepts a `SourceRecord` and creates the row in the new format. Frozen instances cannot be modified directly; use `dataclasses.replace()` if an update needs a new instance.

The example CSV establishes the output shape. The script does not read it at runtime.

## Labeling rules

`get_labels(record)` uses the record's title, abstract, and keywords through the shared `get_labels_from_text()` function. The categories follow RQ1 and the data-type distinction in RQ2 of the [working doc](../docs_human/Check-in%202%20working%20doc.md):

- Method families: expert-driven, statistical, machine learning, LLM-based.
- Domains: educational measurement; intelligent tutoring systems and learning analytics; psychological and clinical assessment.
- Tasks: Q-matrix generation, validation, refinement.
- Data types: simulated data, empirical data.

The patterns in `LABEL_PATTERNS` and `TASK_PATTERNS` make the rules editable. Matching ignores case and normalizes hyphens and whitespace. Task terms must occur within 100 characters of a Q-matrix or an equivalent mapping term in the same sentence or keyword. Multiple categories can match; duplicates are removed and labels follow enum declaration order.

`update_records()` returns a new list of copied records with recomputed labels. It preserves the original records and their notes, replacing any previously supplied label list. CSV conversion appends the label values to output notes, using ` | ` only when an existing note is present. Records with no labels retain their original notes. Output headers still match the example CSV.

These are descriptive keyword suggestions for review. A mention of a method may describe background work, and a domain term may have another meaning. The rules do not determine inclusion, exclusion, peer-review status, full-text availability, or the detailed extraction items in RQ2–RQ4. Absence of a matching term produces no label; labeling accuracy needs human review.

Synthetic checks can be run without pandas:

```bash
python -m unittest test_parse_records -v
```

## Column mapping

The rows below give the exact output column order.

| Output column | Source / conversion |
| --- | --- |
| `key` | `ID`, preserved as a string |
| `title` | `Title` |
| `authors` | Parsed `Authors`, with trailing numeric identifiers removed, joined with ` and ` |
| `journal` | `Venue`, including conference venues |
| `issn` | Empty |
| `volume` | Empty |
| `issue` | Empty |
| `pages` | Empty |
| `year` | Parsed `Year`, converted back to a string; empty if missing |
| `publisher` | Empty |
| `url` | Empty |
| `abstract` | `Abstract` |
| `notes` | `Notes`, plus nonempty computed labels |
| `doi` | `DOI`, preserved without normalization |
| `keywords` | Parsed `Keywords`, joined with `;` |

For example:

```text
Input authors:  Zhang, Ying (60612336400); Cheng, Ningxi (60351872100)
Output authors: Zhang, Ying and Cheng, Ningxi
```

Names are preserved rather than shortened to initials. Only a trailing parenthesized sequence of digits is removed from each author entry.

`Found in` determines the destination file. The remaining source-only fields are retained in `SourceRecord` but omitted from the output: `Sept ID`, `Document type`, `Language`, `Screening flags`, `Stage`, `Assigned to`, `Screener 1`, `Screener 2`, `Decision`, `Exclusion reason`, and `Excluded at stage`.

## Database assignment and output

`SourceRecord.database` selects the smallest database name using case-insensitive alphabetical comparison. Input order does not determine the choice.

```text
Found in: Scopus; Web of Science; APA PsycInfo; PubMed
File:     APA PsycInfo.csv
```

Each input row is written once. This assignment does not indicate which database originally supplied the record. Duplicate input rows remain duplicates; the converter does not deduplicate them.

`write_records()` creates a new directory using the machine's local time:

```text
output/
  20261009_1342/
    APA PsycInfo.csv
    IEEE Xplore.csv
    Scopus.csv
    ...
```

The requested `yyyymmdd_hhss` format uses **hour and second**, with no minutes. In this example, `13` is the hour and `42` is the second. Runs at the same second value within the same hour can therefore collide; an existing directory causes an error rather than being reused.

Each database represented in the input gets a file named directly after it, including spaces. CSVs use UTF-8, include a header row, and omit the pandas index. Records retain their input order within each file. Commas, quotes, and multiline text are escaped by pandas.

## Limits and errors

- Missing required columns or a nonempty, noninteger year cause parsing to fail.
- An empty `Found in` field causes database assignment to fail before the output directory is created.
- Database names are used directly as filenames; they should not contain path separators or characters invalid on the target filesystem.
- Bibliographic fields absent from the source remain blank. There are no API calls or metadata lookups.
- The converter applies no date, language, inclusion, or exclusion filters. Screening fields do not affect which rows are written.
- A write failure can leave a partially populated output directory.

The read/write functions were previously checked against the supplied 836-record input for matching example headers and exactly one database assignment per record. That historical check did not validate labeling accuracy.

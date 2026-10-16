# Full-text extraction pilot: 21 papers

Completed on 2026-10-13 with GPT-6 Luna, low reasoning effort, taxonomy version 0.2.0, using all 21 currently available full-text PDFs. All 21 responses completed and passed the 31-field typed JSON Schema. This evaluates extraction coverage on available candidates; these are not 21 confirmed eligible studies.

The [taxonomy and screening plan](extraction_taxonomy.md) documents the fields and recommends abstract screening followed by full-text eligibility verification and extraction. Q1 abstract labels are provisional; Q4 author-reported limitations require full-text review.

## Initial findings

The model reported sample size in 19/21 papers, item count in 18/21 and attribute count in 19/21. It reported author limitations in all 21. These are populated-cell counts, not validated recall: only 7 sample-size cells and 6 limitation cells passed all conservative automatic grounding checks.

RQ3 numeric coverage was thinner. Attribute classification accuracy was described in 12 papers but supplied usable numeric values in 5; model fit was described in 16 with numeric values in 10. Q-matrix recovery and expert-matrix agreement were each reported in one paper; power, validation-test Type I error and held-out prediction were not reported by the model in this sample. These findings do not establish absence from the papers or the literature. Review eligibility and missed statements before changing the taxonomy or interpreting these as research gaps.

All 651 paper-field cells are available for review. The next priority is adjudicating relevance and evidence, then expanding the pilot to cover mapping-method studies and underrepresented families/domains, rather than optimizing only the proportion of filled cells.

## Local results

Run directory: `output/full_text_extraction/20261013_184539_041971_UTC`. All record-level files stay local and ignored by Git.

- `review.csv`: narrative context, typed-value JSON and page evidence for every field.
- `typed_values.jsonl`: native typed scalars/lists and numeric observations.
- `numeric_observations.csv`: one explicit numerical value per condition, separate numeric bounds and units.
- `coverage.csv` and `coverage.json`: field coverage and applicability denominators.
- Per-paper `extraction.json`, `response.json`, `pages.json` and text: source and model output for review.

Saved responses used 658,055 input tokens and 84,558 output tokens, including reasoning tokens. These counts do not establish billing totals: an earlier request was interrupted when the typed-value requirement arrived, before its usage was available. No model substitution was made.

## Coverage by field

Reported percentages use successful applicable extractions. Only unflagged structural not-applicable cells are removed from the denominator. “Grounded” below means reported with matching page quotes and no automatic field warnings; it is not human-validated correctness. “Typed present” counts usable typed values; numeric fields require at least one actual numerical value or range bound. The model can describe a metric without reporting its numeric results.

| Field | RQ | Reported | Not reported | N/A | Unclear | Applicable n | Reported % | Grounded | Typed present | Flagged |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `title` | basic | 21 | 0 | 0 | 0 | 21 | 100.0 | 19 | 21 | 2 |
| `doi` | basic | 19 | 2 | 0 | 0 | 21 | 90.5 | 19 | 19 | 0 |
| `publication_year` | basic | 20 | 1 | 0 | 0 | 21 | 95.2 | 19 | 20 | 1 |
| `mapping_contribution` | screening | 21 | 0 | 0 | 0 | 21 | 100.0 | 4 | 21 | 17 |
| `methods_investigated` | RQ1 | 21 | 0 | 0 | 0 | 21 | 100.0 | 5 | 21 | 16 |
| `method_family` | RQ1 | 19 | 0 | 2 | 0 | 21 | 90.5 | 6 | 18 | 15 |
| `domain` | RQ1 | 21 | 0 | 0 | 0 | 21 | 100.0 | 13 | 21 | 8 |
| `q_matrix_task` | RQ1 | 13 | 4 | 4 | 0 | 21 | 61.9 | 3 | 10 | 18 |
| `data_type` | RQ2 | 21 | 0 | 0 | 0 | 21 | 100.0 | 10 | 21 | 11 |
| `sample_size` | RQ2 | 19 | 2 | 0 | 0 | 21 | 90.5 | 7 | 19 | 12 |
| `number_of_items` | RQ2 | 18 | 3 | 0 | 0 | 21 | 85.7 | 7 | 18 | 11 |
| `number_of_attributes` | RQ2 | 19 | 2 | 0 | 0 | 21 | 90.5 | 7 | 19 | 12 |
| `response_type` | RQ2 | 18 | 3 | 0 | 0 | 21 | 85.7 | 10 | 18 | 9 |
| `attribute_structure` | RQ2 | 18 | 3 | 0 | 0 | 21 | 85.7 | 11 | 18 | 7 |
| `diagnostic_model` | RQ2 | 19 | 2 | 0 | 0 | 21 | 90.5 | 5 | 19 | 14 |
| `simulation_misspecification_proportion` | RQ2 | 1 | 9 | 11 | 0 | 16 | 6.2 | 0 | 1 | 10 |
| `simulation_item_quality` | RQ2 | 9 | 1 | 11 | 0 | 16 | 56.2 | 1 | 9 | 14 |
| `benchmark_datasets` | RQ3 | 15 | 3 | 3 | 0 | 21 | 71.4 | 8 | 15 | 10 |
| `q_matrix_recovery` | RQ3 | 1 | 16 | 4 | 0 | 21 | 4.8 | 0 | 1 | 7 |
| `attribute_classification_accuracy` | RQ3 | 12 | 9 | 0 | 0 | 21 | 57.1 | 2 | 5 | 10 |
| `classification_reliability` | RQ3 | 9 | 12 | 0 | 0 | 21 | 42.9 | 3 | 6 | 7 |
| `power` | RQ3 | 0 | 13 | 8 | 0 | 21 | 0.0 | 0 | 0 | 10 |
| `type_i_error` | RQ3 | 0 | 13 | 8 | 0 | 21 | 0.0 | 0 | 0 | 10 |
| `model_fit` | RQ3 | 16 | 5 | 0 | 0 | 21 | 76.2 | 2 | 10 | 14 |
| `held_out_prediction` | RQ3 | 0 | 20 | 1 | 0 | 21 | 0.0 | 0 | 0 | 3 |
| `expert_matrix_agreement` | RQ3 | 1 | 15 | 5 | 0 | 21 | 4.8 | 0 | 1 | 8 |
| `expert_review` | RQ3 | 6 | 14 | 1 | 0 | 21 | 28.6 | 0 | 5 | 8 |
| `think_aloud_review` | RQ3 | 4 | 16 | 1 | 0 | 21 | 19.0 | 1 | 4 | 5 |
| `computational_cost` | RQ3 | 6 | 15 | 0 | 0 | 21 | 28.6 | 4 | 2 | 4 |
| `author_reported_limitations` | RQ4 | 21 | 0 | 0 | 0 | 21 | 100.0 | 6 | 21 | 15 |
| `limitation_themes` | RQ4 | 21 | 0 | 0 | 0 | 21 | 100.0 | 9 | 21 | 12 |

## Evidence checks and limits

21 of 21 papers have at least one automatic review warning. Across 900 evidence quotes, 577 match the cited PDF page, 39 match a different page, 178 have possible matches after more permissive typography normalization, and 106 were not located by these checks. The permissive diagnostic removes punctuation/case and can conceal meaningful differences; it does not clear any warnings or certify those quotes.

Model-populated fields, exact quotes and correct scientific interpretation are different things. Page errors, paraphrases, typography and status inconsistencies need reviewer adjudication. Automated relevance codes are also provisional; parameter estimation or model evaluation with an unchanged Q-matrix should not be counted as a mapping-method contribution.

## Next review step

Review all 21 draft relevance decisions and Q1/Q4 codes against the PDFs. Check each numerical observation and every evidence/applicability warning. Keep corrections and reviewer decisions under ignored `output/`; then recompute eligible-only coverage before synthesizing RQ distributions. Expand toward 100 with a sample covering families, domains, hybrid methods and borderline cases. Missing RQ measures or limitations alone are not an exclusion reason.

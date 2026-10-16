# Initial Q-matrix extraction taxonomy and screening plan

This codebook implements sections 1, 2.3 and 2.4 of the local `input/qmatrix_checkin_2.pdf`. Version 0.2.0 is in `full_text_extraction/taxonomy.json`. It supersedes the smaller starter field list. The document retains an October 8, 2026 eligibility cutoff even though searches ran October 9; the taxonomy does not silently change that protocol detail.

## Screening: hybrid, followed by full-text extraction

Use title-and-abstract review for clear relevance exclusions and provisional method/domain/task labels. Retain uncertain cases for full text. Missing abstract details, missing limitations, or missing RQ2/RQ3 measures do not establish ineligibility. The check-in protocol explicitly permits missing extraction items.

Full-text review establishes whether the study contributes a mapping-generation, validation or refinement method; only using an existing Q-matrix does not qualify. Check equivalent KC/skill mappings, actual empirical domain or simulation data, sufficient method detail, publication window, English full text, publication type and peer review. These checks require reviewer decisions and sometimes external bibliographic verification. The pipeline's `mapping_contribution` is a draft relevance aid, not a complete screen or automatic exclusion.

RQ1 can be provisionally coded from abstracts but must be verified against the paper's actual methods: abstract keywords can describe background, comparators or a diagnostic model using a fixed mapping. RQ4 requires full text, particularly discussion and limitations sections. Abstracts rarely enumerate all author-reported limitations. RQ2 and RQ3 need methods, simulations, experiments, tables and results.

This follows the check-in's stated two-stage approach. As an external methodological reference, [Cochrane's selection guidance](https://www.cochrane.org/authors/handbooks-and-manuals/mecir-manual/standards-conduct-new-cochrane-intervention-reviews-c1-c75/performing-review-c24-c75/selecting-studies-include-review-c39-c42) also recommends full-text inclusion decisions following initial title/abstract screening. Its independent-reviewer requirement applies to Cochrane reviews; for this project, agree and document the team's review/adjudication procedure rather than treating model outputs as reviewer consensus.

## Coding rules

Every field has a status, a value and page-specific verbatim evidence. Categorical typed values use controlled enum codes. Codes can be multi-label. Hybrid families remain explicit rather than being forced into one family. Domain is based on the application, not on a model acronym: pure simulations can have an unspecified domain.

- `reported`: the paper provides the information and supporting evidence.
- `not_reported`: no usable statement found; this includes a metric not evaluated. This is a model finding requiring review, not proof of absence.
- `not_applicable`: structurally inapplicable, particularly simulation-only fields in empirical-only studies.
- `unclear`: evidence is ambiguous or insufficient; retain for human review.

API failure, refusal, incomplete response or unreadable text is recorded separately and never treated as `not_reported`. Missing values remain null. A reported categorical field requires at least one controlled code. Unknown categories use `other` where available and an explanatory value.

Maintain dataset/experiment/condition names in values. Separate sample size, items and attributes; distinguish simulation replications from participants and item-response categories from latent-attribute levels. The pilot stores condition-qualified prose and typed observation lists; it is not yet a fully relational study/experiment table. Before quantitative pooling, normalize these into experiment rows under stable study IDs and collate multiple reports of the same study.

Q-matrix recovery, attribute classification accuracy and reliability are separate. Validation-test power and Type I error are separate. Expert-reference agreement, expert review and think-aloud review are separate. Simulation entry misspecification and item quality are separate. A true simulated matrix is not automatically an expert-specified matrix.

RQ4 uses the verified RQ1 family/domain codes for grouping, rather than asking the model to create duplicate labels. Initial limitation themes cover sample size, generalizability, data quality, assumptions, identifiability, computational cost, expert subjectivity, interpretability, validation/benchmark limits, mapping complexity and LLM reliability. These are provisional reviewer codes, not findings that these limitations recur. Preserve author statements and add emergent themes through `other` before revising the taxonomy.

## Field dictionary

| Field | RQ | Definition | Controlled codes |
| --- | --- | --- | --- |
| `title` | basic | Title of this paper, not a cited work. | Condition-qualified text |
| `doi` | basic | DOI of this paper, if present. | Condition-qualified text |
| `publication_year` | basic | Publication year; distinguish first online year where explicitly reported. | Condition-qualified text |
| `mapping_contribution` | screening | Draft assessment of whether THIS study generates, validates, refines, only uses an existing item-attribute mapping, or is unrelated. Equivalent KC/skill models count. Do not confuse estimating CDM parameters with estimating a Q-matrix. Not a final eligibility decision. | generation, validation, refinement, uses_existing_only, unrelated, uncertain |
| `methods_investigated` | RQ1 | Names and brief descriptions of this study’s own mapping methods and comparators; distinguish their roles. | Condition-qualified text |
| `method_family` | RQ1 | Classify mapping methods investigated by this study, not background mentions. Multi-label hybrids allowed. Expert-driven: substantive expert specification/judgment; statistical: psychometric, Bayesian, likelihood, regularization or factorization estimation/testing; machine learning: learned predictive/neural/tree/clustering mapping methods; LLM-based: large language model generates/validates/refines mapping. Explain borderline classifications in value. | expert-driven, statistical, machine learning, LLM-based, other |
| `domain` | RQ1 | Empirical application setting: educational measurement (assessment/test diagnosis), ITS/learning analytics (tutoring/logs/KC models), psychological/clinical assessment (symptoms/personality/noncognitive attributes). Multi-label allowed. Pure simulations without an explicit domain use domain_unspecified_simulation; do not assume educational measurement from DINA alone. | educational measurement, intelligent tutoring systems and learning analytics, psychological and clinical assessment, domain_unspecified_simulation, other |
| `q_matrix_task` | RQ1 | Task applied to the item-attribute mapping itself: initial generation, validation, or refinement. Mere use of a fixed mapping is not a task contribution. Multi-label allowed. | generation, validation, refinement |
| `data_type` | RQ2 | Data actually used by this study: simulated and/or empirical. Code both when both occur. A theoretical/no-data paper uses neither. | simulated, empirical, neither |
| `sample_size` | RQ2 | Sample sizes per named empirical dataset and simulation condition; distinguish participants from interactions and simulation replications. Preserve ranges/conditions and units. | Condition-qualified text |
| `number_of_items` | RQ2 | Number of assessment items per dataset/experiment or simulation condition; identify conditions rather than conflating them. | Condition-qualified text |
| `number_of_attributes` | RQ2 | Number of diagnostic attributes/skills per named dataset or simulation condition. | Condition-qualified text |
| `response_type` | RQ2 | Observed item-response categories: dichotomous versus polytomous. Distinguish polytomous latent attributes from polytomous item responses. Mention response times separately, not as polytomous responses. | dichotomous, polytomous, other |
| `attribute_structure` | RQ2 | Independent/nonhierarchical, hierarchical/prerequisite, correlated or mixed attribute structures, with details. Attribute correlations are not automatically prerequisite hierarchies. | independent, hierarchical, correlated, mixed, other |
| `diagnostic_model` | RQ2 | Names of diagnostic models used in this study and relation to conditions, e.g. DINA, G-DINA, DINO, LCDM. Not models mentioned only in background. | Condition-qualified text |
| `simulation_misspecification_proportion` | RQ2 | In simulations, fraction/percentage of Q-matrix entries initially misspecified and how errors were introduced; distinguish entry error rate from fraction of items altered. not_applicable only if the study has no simulations. If simulations exist but this is unspecified, not_reported. | Condition-qualified text |
| `simulation_item_quality` | RQ2 | In simulations, item-quality conditions, e.g. slipping/guessing/discrimination parameters and levels. not_applicable only if there are no simulations; otherwise not_reported if missing. | Condition-qualified text |
| `benchmark_datasets` | RQ3 | Names/sources of benchmark datasets actually used to evaluate the mapping method, linking metrics to datasets. Explicitly unnamed empirical data are not named benchmarks. | Condition-qualified text |
| `q_matrix_recovery` | RQ3 | Mapping recovery criterion, operational definition, results and condition: entrywise accuracy, exact Q-matrix recovery, item-vector recovery etc. Not latent-attribute classification accuracy. | Condition-qualified text |
| `attribute_classification_accuracy` | RQ3 | Attribute-profile or attribute-wise classification accuracy, metric, results and conditions; distinguish from mapping recovery. | Condition-qualified text |
| `classification_reliability` | RQ3 | Reliability/consistency of diagnostic classifications; distinguish from classification accuracy and generic test reliability. | Condition-qualified text |
| `power` | RQ3 | Power/sensitivity of Q-matrix validation tests, with test, criterion, numerical findings and conditions. Generic predictive accuracy is not power. | Condition-qualified text |
| `type_i_error` | RQ3 | Type I error/false-positive rate of Q-matrix validation tests, with test, nominal alpha, results and conditions. Not generic misclassification error. | Condition-qualified text |
| `model_fit` | RQ3 | Fit criteria used to assess the mapping method (likelihood, AIC/BIC, RMSEA, residuals etc), results and conditions. Distinguish evaluation of a fixed CDM from evaluation of mapping changes. | Condition-qualified text |
| `held_out_prediction` | RQ3 | Prediction of held-out responses: split/CV protocol, metrics and results. Training fit alone is not held-out prediction. | Condition-qualified text |
| `expert_matrix_agreement` | RQ3 | Agreement with expert-specified mappings: reference construction, agreement metric, results. A simulation true matrix is not an expert reference. | Condition-qualified text |
| `expert_review` | RQ3 | Expert judgment/review used to evaluate the mapping and its findings, distinct from expert generation. | expert_review |
| `think_aloud_review` | RQ3 | Think-aloud/cognitive interview evidence used to evaluate item-skill mappings and findings. | think_aloud_review |
| `computational_cost` | RQ3 | Reported runtime, memory, hardware, complexity or resource requirements, with conditions. Algorithm iterations alone are not elapsed time. | Condition-qualified text |
| `author_reported_limitations` | RQ4 | Limitations explicitly acknowledged by authors of THIS mapping study; preserve each limitation and its method/condition, with short evidence. Do not invent weaknesses or borrow cited studies’ limitations. | Condition-qualified text |
| `limitation_themes` | RQ4 | Provisional multi-label themes grounded only in author_reported_limitations. Retain emergent themes as other with explanation; not an exhaustive final codebook. Never add a theme without an author statement. | sample_size, generalizability, data_quality_or_availability, model_assumptions, identifiability, computational_cost, expert_subjectivity, interpretability, validation_or_benchmark_limits, mapping_or_attribute_complexity, LLM_reliability, other |

## Pilot coverage and review

Run on all 21 available PDFs to meet the requested initial n=20–100. This is a convenience sample of available candidates, not a representative method-by-domain sample and not an already confirmed eligible set. Do not infer review-wide distributions from it. Expand toward 100 after checking missing cells and including underrepresented families/domains where available.

The pipeline produces `coverage.json` and `coverage.csv` with per-field reported, not-reported, not-applicable and unclear counts, failed/unprocessed papers, evidence-supported counts and categorical code frequencies. Coverage percentages use successfully extracted applicable papers as the denominator, with the denominator shown. Only unflagged structural not-applicable cells are removed from that denominator; ambiguous or inconsistent not-applicable cells remain in it pending review. Failures and structural inapplicability remain visible. All-candidate coverage can include irrelevant papers, so review eligibility before interpreting substantive RQ distributions.

Evidence-supported coverage means a reported field has a value and its quotes match the identified PDF pages, with no automatic warning. This checks grounding, not semantic correctness or completeness. Reviewers should inspect a stratified set of reported, missing, unclear and flagged cells against the PDFs, document corrections, and estimate accuracy on adjudicated data. High coverage alone can reflect over-extraction.

Review the pilot in `review.csv`, particularly methods that only use pre-existing mappings, unknown domains, mismatched quotes, distinctions between item and attribute categories, and limitation themes. For a pilot-wide assessment, review all 21 eligibility decisions and all Q1/Q4 codes, plus RQ2/RQ3 numerical fields and every warning. Save adjudicated record-level data only under ignored `output/`.

## Typed values alongside context

`value` retains the narrative explanation; `typed_value` is separately constrained by JSON Schema. `extraction.json` and `typed_values.jsonl` retain native JSON types. `review.csv` adds a `typed_value` column serialized as JSON because CSV has no native array/object/null types. A literal JSON null is different from zero or an empty list.

| Field kind | Typed representation | Examples |
| --- | --- | --- |
| Publication year | Integer or null | `2024` |
| Method family, domain, task, data type, response type, attribute structure, review types, limitation themes | List of controlled enum strings or null | `["statistical", "machine learning"]` |
| Sample size, item count, attribute count | List of condition-specific integer observations or null | `values: [100, 500]` |
| Simulation proportions, item quality, performance criteria, computational cost | List of condition-specific numeric observations or null | `values: [0.1, 0.2]`, `unit: "proportion"` |
| Methods, models, benchmarks, author limitations | List of strings or null | `["DINA", "G-DINA"]` |
| Title and DOI | String or null | Synthetic bibliographic text |

Each numeric observation contains `condition`, `measure`, `unit`, `values`, `minimum` and `maximum`. Explicit discrete conditions go into `values`; reported ranges go into the bounds without inventing a midpoint. Misspecified-entry proportions are normalized to 0–1, with original percentages retained in narrative context. Other units remain explicit so percentages, proportions, seconds and fit statistics cannot be silently pooled. No numerical finding is invented when the paper names a criterion but gives no numerical result: its typed numeric list can be empty while the narrative documents the criterion.

Not-reported, unclear and not-applicable fields have null typed values. A reported field must have a typed value; an empty numeric list means the criterion is described without extractable numeric results, not zero. Coverage separately counts `typed_values_present`, so criterion reporting and availability of numeric results can be distinguished.

`numeric_observations.csv` also flattens numeric lists into one row per explicit value and condition. Its `value`, `minimum` and `maximum` columns contain numbers or blanks, with separate units and narrative context. This lets a spreadsheet filter/sort numerical results without parsing JSON. Ranges stay in bounds columns; an empty explicit value is not zero. The native JSONL remains authoritative for types.

Quote checks normalize whitespace and remain conservative about punctuation, ligatures and line-break hyphenation. A mismatch can indicate PDF typography as well as an incorrect page or paraphrase; inspect it before calling the extraction unsupported. When an exact quote is found elsewhere, the warning lists candidate PDF pages without silently changing the model's citation.

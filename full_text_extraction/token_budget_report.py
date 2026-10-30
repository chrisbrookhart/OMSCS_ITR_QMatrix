"""Compare saved extraction runs locally; never submit requests or paper text."""
import argparse
import csv
import json
from math import ceil
from pathlib import Path
from pydantic import BaseModel, Field

import models
import api
import bibliography
import pipeline
import spreadsheet
import storage
import validation

REPORT_JSON = 'token_budget_comparison.json'
REPORT_CSV = 'token_budget_comparison.csv'
REQUIRED_HEADROOM_FRACTION = 0.20
TOKEN_LIMIT_ROUNDING = 10000
QUOTE_ISSUE_PREFIX = 'Quotation not verified'


class OutputDetails(BaseModel):
    reasoning_tokens: int = 0


class Usage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    output_tokens_details: OutputDetails = Field(default_factory=OutputDetails)


class SavedResponse(BaseModel):
    status: str
    usage: Usage | None = None
    incomplete_details: dict[str, str] | None = None


class Observation(BaseModel):
    run: str
    source: str
    reasoning_effort: str
    token_limit: int
    job_status: str
    response_status: str | None = None
    incomplete_reason: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    visible_output_tokens: int = 0
    experiments: int | None = None
    field_observations: int | None = None
    missing_primary_values: int | None = None
    review_issues: int | None = None
    unverified_quotations: int | None = None
    quotation_count: int | None = None
    unverified_quotation_fraction: float | None = None
    error: str | None = None


def read_observation(run: Path, manifest: pipeline.Manifest, job: pipeline.PaperJob) -> Observation:
    result = Observation(run=str(run), source=job.source, reasoning_effort=manifest.settings.reasoning_effort,
                         token_limit=manifest.settings.max_output_tokens, job_status=job.status.value, error=job.error)
    folder = run / job.directory
    response_path = folder / storage.RESPONSE_FILE
    if response_path.exists():
        response = SavedResponse.model_validate_json(response_path.read_text(encoding='utf-8'))
        usage = response.usage or Usage()
        result.response_status = response.status
        result.incomplete_reason = (response.incomplete_details or {}).get('reason')
        result.input_tokens, result.output_tokens = usage.input_tokens, usage.output_tokens
        result.reasoning_tokens = usage.output_tokens_details.reasoning_tokens
        result.visible_output_tokens = result.output_tokens - result.reasoning_tokens
    record_path = folder / storage.RECORD_FILE
    if record_path.exists():
        record = models.PaperRecord.model_validate_json(record_path.read_text(encoding='utf-8'))
        add_record_metrics(result, record)
    return result


def add_record_metrics(result: Observation, record: models.PaperRecord) -> None:
    fields = [(path, field) for path, field in validation.fields_in(record.paper)
              if path not in bibliography.METADATA_PATHS]
    result.experiments = len(record.paper.experiments)
    result.field_observations = len(fields)
    result.missing_primary_values = sum(field.value is None and not spreadsheet.inherits_reported_value(
        record.paper, path, field) for path, field in fields)
    result.review_issues = len(record.review_issues)
    result.unverified_quotations = sum(issue.reason.startswith(QUOTE_ISSUE_PREFIX) for issue in record.review_issues)
    all_fields = [field for _, field in fields]
    if record.experiment_design:
        all_fields.extend(item.rationale for item in record.experiment_design.assignments)
    result.quotation_count = sum(len(field.raw_text) for field in all_fields) + sum(
        len(item.evidence) for item in record.missing_fields)
    if result.quotation_count:
        result.unverified_quotation_fraction = result.unverified_quotations / result.quotation_count


def recommend_budget(observations: list[Observation], *,
                      headroom_fraction: float = REQUIRED_HEADROOM_FRACTION) -> int | None:
    candidates = [item for item in observations if item.reasoning_effort == 'max']
    expected_sources = {item.source for item in candidates}
    for budget in sorted({item.token_limit for item in candidates}):
        group = [item for item in candidates if item.token_limit == budget]
        complete = all(item.job_status == pipeline.RunStatus.EXTRACTED.value
                       and item.response_status == api.COMPLETED_STATUS and item.output_tokens > 0 for item in group)
        headroom = all(item.output_tokens <= budget * (1 - headroom_fraction) for item in group)
        if complete and headroom and {item.source for item in group} == expected_sources:
            return budget
    return None


def provisioned_budget(observations: list[Observation]) -> int | None:
    tested = recommend_budget(observations)
    if tested is not None:
        return tested
    successful = recommend_budget(observations, headroom_fraction=0)
    if successful is None:
        return None
    largest = max(item.output_tokens for item in observations
                  if item.reasoning_effort == 'max' and item.token_limit == successful)
    return ceil(largest / (1 - REQUIRED_HEADROOM_FRACTION) / TOKEN_LIMIT_ROUNDING) * TOKEN_LIMIT_ROUNDING


def main(*, runs: list[Path], output: Path) -> None:
    observations = []
    for run in runs:
        manifest = pipeline.Manifest.model_validate_json((run / storage.MANIFEST_FILE).read_text(encoding='utf-8'))
        observations.extend(read_observation(run, manifest, job) for job in manifest.papers)
    output.mkdir(parents=True, exist_ok=True)
    report = {'recommended_tested_budget': recommend_budget(observations),
        'smallest_successful_tested_budget': recommend_budget(observations, headroom_fraction=0),
        'suggested_limit_with_headroom': provisioned_budget(observations),
        'required_headroom_fraction': REQUIRED_HEADROOM_FRACTION,
        'interpretation': 'Select the smallest tested max-reasoning limit completing every sample with headroom. '
            'If no tested limit has enough reserve, suggest a ceiling from observed usage, rounded up to 10,000 tokens; '
            'that derived ceiling is not itself a tested result. Review flags and missing counts do not measure '
            'factual accuracy. Prompt/schema changes confound historical comparisons.',
        'observations': [item.model_dump() for item in observations]}
    storage.write_json(output / REPORT_JSON, report)
    with (output / REPORT_CSV).open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(Observation.model_fields))
        writer.writeheader()
        writer.writerows(item.model_dump() for item in observations)
    print(json.dumps(report, indent=2))


def get_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs', nargs='+', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    return parser


if __name__ == '__main__':
    arguments = get_parser().parse_args()
    main(runs=arguments.runs, output=arguments.output)

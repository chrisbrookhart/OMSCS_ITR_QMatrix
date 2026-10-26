"""Strict API models and canonical, provenance-bearing paper records."""
from __future__ import annotations

from typing import Generic, TypeVar
from pydantic import BaseModel, ConfigDict
import vocabulary as vocab

Value = TypeVar('Value')
SCHEMA_VERSION = '2.0'
PROMPT_VERSION = '2.0'
PAGE_NUMBERING = 'physical_pdf_1_based'


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class Evidence(StrictModel):
    page: int | None
    location: str | None
    text: str


class Extraction(StrictModel, Generic[Value]):
    value: Value | None
    other: list[Value]
    raw_text: list[Evidence]
    status: vocab.Status


class NumericRange(StrictModel):
    minimum: int | float | None
    maximum: int | float | None


class NumericSetting(StrictModel):
    """Explicit conditions prevent values for different datasets being conflated."""
    condition: str | None
    unit: str | None
    values: list[int | float]
    range: NumericRange | None


class ModelName(StrictModel):
    canonical: vocab.DiagnosticModel
    reported_name: str


class Method(StrictModel):
    family: Extraction[vocab.MethodFamily]
    name: Extraction[str]
    task: Extraction[vocab.Task]


class Conditions(StrictModel):
    data_type: Extraction[vocab.DataType]
    sample_size: Extraction[NumericSetting]
    number_of_items: Extraction[NumericSetting]
    number_of_attributes: Extraction[NumericSetting]
    response_type: Extraction[vocab.ResponseType]
    attribute_structure: Extraction[vocab.AttributeStructure]
    diagnostic_model: Extraction[ModelName]
    misspecification: Extraction[NumericSetting]
    item_quality: Extraction[str]
    benchmark_datasets: Extraction[str]


class Evaluation(StrictModel):
    criterion: Extraction[vocab.Criterion]
    metrics: Extraction[str]


class Limitation(StrictModel):
    theme: Extraction[vocab.LimitationTheme]
    description: Extraction[str]


class Experiment(StrictModel):
    description: Extraction[str]
    method: Method
    domain: Extraction[vocab.Domain]
    conditions: Conditions
    evaluations: list[Evaluation]
    limitations: list[Limitation]


class Paper(StrictModel):
    title: Extraction[str]
    doi: Extraction[str]
    publication_year: Extraction[int]
    method: Method
    domain: Extraction[vocab.Domain]
    limitations: list[Limitation]
    experiments: list[Experiment]


class ReviewIssue(StrictModel):
    field: str
    reason: str


class Provenance(StrictModel):
    model: str
    prompt_version: str
    schema_version: str
    request_fingerprint: str
    extracted_at: str
    source: str
    source_sha256: str
    page_numbering: str
    response_id: str


class PaperRecord(StrictModel):
    paper_id: str
    experiment_ids: list[str]
    provenance: Provenance
    paper: Paper
    review_issues: list[ReviewIssue]

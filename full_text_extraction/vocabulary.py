"""Controlled review vocabulary; limitation themes can be revised here."""
from enum import Enum


class Status(str, Enum):
    EXTRACTED = 'extracted'
    NOT_REPORTED = 'not_reported'
    NOT_APPLICABLE = 'not_applicable'
    AMBIGUOUS = 'ambiguous'


class MethodFamily(str, Enum):
    EXPERT = 'expert_driven'
    STATISTICAL = 'statistical'
    MACHINE_LEARNING = 'machine_learning'
    LLM = 'llm_based'


class Task(str, Enum):
    GENERATION = 'generation'
    VALIDATION = 'validation'
    REFINEMENT = 'refinement'


class Domain(str, Enum):
    EDUCATIONAL = 'educational_measurement'
    TUTORING = 'intelligent_tutoring_systems'
    LEARNING = 'learning_analytics'
    PSYCHOLOGICAL = 'psychological_assessment'
    CLINICAL = 'clinical_assessment'


class DataType(str, Enum):
    SIMULATED = 'simulated'
    EMPIRICAL = 'empirical'
    MIXED = 'mixed'


class ResponseType(str, Enum):
    DICHOTOMOUS = 'dichotomous'
    POLYTOMOUS = 'polytomous'
    MIXED = 'mixed'
    OTHER = 'other'


class AttributeStructure(str, Enum):
    INDEPENDENT = 'independent'
    CORRELATED = 'correlated'
    HIERARCHICAL = 'hierarchical'
    OTHER = 'other'


class DiagnosticModel(str, Enum):
    DINA = 'DINA'
    GDINA = 'G-DINA'
    DINO = 'DINO'
    LCDM = 'LCDM'
    ACDM = 'A-CDM'
    RRUM = 'R-RUM'
    NIDA = 'NIDA'
    GDM = 'GDM'
    OTHER = 'other'


class Criterion(str, Enum):
    RECOVERY = 'q_matrix_recovery'
    ACCURACY = 'attribute_classification_accuracy'
    RELIABILITY = 'classification_reliability'
    POWER = 'statistical_power'
    TYPE_I = 'type_i_error'
    FIT = 'model_fit'
    PREDICTION = 'held_out_response_prediction'
    AGREEMENT = 'expert_q_matrix_agreement'
    REVIEW = 'expert_or_think_aloud_review'
    COST = 'computational_cost'
    OTHER = 'other'


class LimitationTheme(str, Enum):
    SAMPLE = 'small_sample_size'
    GENERALIZABILITY = 'limited_generalizability'
    COST = 'computational_cost'
    DATA = 'data_requirements'
    ASSUMPTIONS = 'model_assumptions'
    INTERPRETABILITY = 'interpretability'
    VALIDATION = 'lack_of_external_validation'
    BENCHMARKS = 'benchmark_limitations'
    SUBJECTIVITY = 'expert_subjectivity'
    REPRODUCIBILITY = 'reproducibility'
    OTHER = 'other'

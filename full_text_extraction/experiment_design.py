"""Evidence-backed experiment roles and explicit legacy review fallbacks."""
import models

UNCLASSIFIED = 'Unclassified'
SINGLE_MAIN = 'One main experiment'
MULTIPLE_MAIN = 'Multiple main experiments'
NO_EXPERIMENTS = 'No experiments'
PRIMARY_LABEL = 'Primary main experiment'
REFERENCE_LABEL = 'Reference row (unclassified)'
NO_MAIN_REFERENCE_LABEL = 'Reference row (no justified main)'


def validate(design: models.ExperimentDesign, count: int) -> None:
    numbers = [assignment.experiment_number for assignment in design.assignments]
    if sorted(numbers) != list(range(1, count + 1)):
        raise ValueError('Experiment role assignments must cover each experiment exactly once')
    main_numbers = [assignment.experiment_number for assignment in design.assignments
                    if assignment.role == models.ExperimentRole.MAIN]
    if main_numbers and design.primary_experiment_number not in main_numbers:
        raise ValueError('Primary experiment must identify one of the main experiments')
    if not main_numbers and design.primary_experiment_number is not None:
        raise ValueError('Primary experiment must be null when no main experiment is justified')


def primary_index(record: models.PaperRecord) -> int | None:
    if not record.paper.experiments:
        return None
    if record.experiment_design and record.experiment_design.primary_experiment_number is not None:
        return record.experiment_design.primary_experiment_number - 1
    # Old records use an explicitly unclassified reference, never an inferred main.
    return 0


def role_label(record: models.PaperRecord, index: int) -> str:
    design = record.experiment_design
    if design is None:
        return REFERENCE_LABEL if index == primary_index(record) else UNCLASSIFIED
    if design.primary_experiment_number is None and index == primary_index(record):
        return NO_MAIN_REFERENCE_LABEL
    if design.primary_experiment_number == index + 1:
        return PRIMARY_LABEL
    assignment = next(item for item in design.assignments if item.experiment_number == index + 1)
    return f'Additional {assignment.role.value} experiment'


def structure(record: models.PaperRecord) -> str:
    if not record.paper.experiments:
        return NO_EXPERIMENTS
    design = record.experiment_design
    if design is None:
        return UNCLASSIFIED
    count = sum(item.role == models.ExperimentRole.MAIN for item in design.assignments)
    return MULTIPLE_MAIN if count > 1 else SINGLE_MAIN if count == 1 else UNCLASSIFIED

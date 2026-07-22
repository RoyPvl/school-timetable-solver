from __future__ import annotations

from dataclasses import replace
from datetime import date

from school_timetable_solver.model.input_models import FixedLessonModel, InputDataModel
from school_timetable_solver.validator.input_validators import (
    FixedLessonValidator,
    ReferenceIntegrityValidator,
    RuleConflictValidator,
)


def test_reference_integrity_validator_reports_unknown_class(
    minimal_input_data: InputDataModel,
) -> None:
    invalid_requirement = replace(minimal_input_data.lesson_requirements[0], class_id="UNKNOWN")
    invalid = replace(
        minimal_input_data,
        lesson_requirements=(invalid_requirement, *minimal_input_data.lesson_requirements[1:]),
    )

    issues = ReferenceIntegrityValidator().validate(invalid)

    assert any(issue.rule_id == "E003" and issue.target == "Q1" for issue in issues)


def test_fixed_lesson_validator_reports_teacher_conflict(
    minimal_input_data: InputDataModel,
) -> None:
    conflicting = FixedLessonModel("F2", "Q2", date(2026, 7, 27), "P1", "T1", "CL2", "S2", "R2")
    invalid = replace(
        minimal_input_data, fixed_lessons=(*minimal_input_data.fixed_lessons, conflicting)
    )

    issues = FixedLessonValidator().validate(invalid)

    assert any(issue.rule_id == "E006" for issue in issues)


def test_rule_conflict_validator_reports_same_priority_contradiction(
    minimal_input_data: InputDataModel,
) -> None:
    original = replace(minimal_input_data.placement_rules[0], allowed_period_ids=("P2",))
    conflicting = replace(
        minimal_input_data.placement_rules[0], rule_id="RULE2", allowed_period_ids=("P1",)
    )
    invalid = replace(
        minimal_input_data,
        placement_rules=(original, conflicting),
    )

    issues = RuleConflictValidator().validate(invalid)

    assert any(issue.rule_id == "E010" for issue in issues)

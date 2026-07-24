from __future__ import annotations

from dataclasses import replace

from school_timetable_solver.model.input_models import InputDataModel
from school_timetable_solver.service.planning_services import (
    CandidateBuilderService,
    RuleResolverService,
)
from school_timetable_solver.validator.input_validators import (
    CapacityFeasibilityValidator,
    ReferenceIntegrityValidator,
)


def test_validator_detects_duplicate_ids_and_output_orders(
    minimal_input_data: InputDataModel,
) -> None:
    invalid = replace(
        minimal_input_data,
        campuses=(
            minimal_input_data.campuses[0],
            replace(minimal_input_data.campuses[1], campus_id="C1", output_order=1),
        ),
        rooms=(
            minimal_input_data.rooms[0],
            replace(minimal_input_data.rooms[1], output_order=1),
            minimal_input_data.rooms[2],
        ),
    )

    rule_ids = {issue.rule_id for issue in ReferenceIntegrityValidator().validate(invalid)}

    assert {
        "DUPLICATE_ID",
        "DUPLICATE_CAMPUS_OUTPUT_ORDER",
        "DUPLICATE_ROOM_OUTPUT_ORDER",
    } <= rule_ids


def test_validator_detects_unknown_and_disabled_references(
    minimal_input_data: InputDataModel,
) -> None:
    invalid = replace(
        minimal_input_data,
        teachers=(
            replace(minimal_input_data.teachers[0], enabled=False),
            minimal_input_data.teachers[1],
        ),
        lesson_requirements=(
            minimal_input_data.lesson_requirements[0],
            replace(minimal_input_data.lesson_requirements[1], subject_id="UNKNOWN"),
        ),
    )

    rule_ids = {issue.rule_id for issue in ReferenceIntegrityValidator().validate(invalid)}

    assert {"UNKNOWN_REFERENCE", "DISABLED_MASTER_REFERENCE"} <= rule_ids


def test_validator_detects_requirement_and_availability_duplicates(
    minimal_input_data: InputDataModel,
) -> None:
    invalid = replace(
        minimal_input_data,
        lesson_requirements=(
            minimal_input_data.lesson_requirements[0],
            replace(
                minimal_input_data.lesson_requirements[1],
                class_id="CL1",
                subject_id="S1",
            ),
        ),
        teacher_availability=(
            *minimal_input_data.teacher_availability,
            minimal_input_data.teacher_availability[0],
        ),
    )

    rule_ids = {issue.rule_id for issue in ReferenceIntegrityValidator().validate(invalid)}

    assert {
        "DUPLICATE_CLASS_SUBJECT_REQUIREMENT",
        "DUPLICATE_TEACHER_AVAILABILITY",
    } <= rule_ids


def test_validator_detects_invalid_period_range_and_rule_columns(
    minimal_input_data: InputDataModel,
) -> None:
    bad_rule = replace(
        minimal_input_data.placement_rules[3],
        condition_fields=("division",),
        condition_operators=("contains",),
        condition_values=("x",),
        allowed_period_ids=("P1",),
        attendance_streak_limit=0,
    )
    invalid = replace(
        minimal_input_data,
        periods=(
            replace(
                minimal_input_data.periods[0],
                output_order=2,
                start_time=minimal_input_data.periods[0].end_time,
            ),
            *minimal_input_data.periods[1:],
        ),
        placement_rules=(*minimal_input_data.placement_rules[:3], bad_rule),
    )

    rule_ids = {issue.rule_id for issue in ReferenceIntegrityValidator().validate(invalid)}

    assert {
        "INVALID_PERIOD_OUTPUT_ORDER",
        "INVALID_PERIOD_TIME_RANGE",
        "INVALID_RULE_CONDITION_FIELD",
        "INVALID_RULE_OPERATOR",
        "INVALID_RULE_COLUMN_FOR_TARGET",
        "INVALID_RULE_LIMIT",
    } <= rule_ids


def test_capacity_validator_uses_resolved_candidates(
    minimal_input_data: InputDataModel,
) -> None:
    no_teacher_one_availability = replace(
        minimal_input_data,
        teacher_availability=tuple(
            item for item in minimal_input_data.teacher_availability if item.teacher_id != "T1"
        ),
    )
    resolved = RuleResolverService().execute(no_teacher_one_availability)
    candidates = CandidateBuilderService().execute(
        no_teacher_one_availability,
        resolved,
    )

    issues = CapacityFeasibilityValidator().validate(
        no_teacher_one_availability,
        resolved,
        candidates,
    )

    assert any(
        issue.rule_id == "CANDIDATE_SUPPLY_SHORTAGE" and issue.target == "Q1" for issue in issues
    )

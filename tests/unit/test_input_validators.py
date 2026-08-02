from __future__ import annotations

from dataclasses import replace
from datetime import date

from school_timetable_solver.model.input_models import (
    HomeroomBoundaryRuleModel,
    InputDataModel,
    LessonCountPreferenceRuleSegmentModel,
    LessonCountRuleSegmentModel,
    TeacherLeaveModel,
)
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


def test_validator_rejects_overlapping_homeroom_ranges_and_missing_homeroom(
    minimal_input_data: InputDataModel,
) -> None:
    invalid = replace(
        minimal_input_data,
        homeroom_boundary_rules=(
            HomeroomBoundaryRuleModel(
                "HB1", "前半1", True, "CL1", date(2026, 7, 27), date(2026, 7, 28)
            ),
            HomeroomBoundaryRuleModel(
                "HB2", "前半2", True, "CL1", date(2026, 7, 28), date(2026, 7, 29)
            ),
        ),
    )

    rule_ids = {issue.rule_id for issue in ReferenceIntegrityValidator().validate(invalid)}

    assert {"HOMEROOM_TEACHER_REQUIRED", "HOMEROOM_BOUNDARY_RANGE_OVERLAP"} <= rule_ids


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
        teacher_leaves=(TeacherLeaveModel("T1", date(2026, 8, 1), ("UNKNOWN",)),),
    )

    rule_ids = {issue.rule_id for issue in ReferenceIntegrityValidator().validate(invalid)}

    assert {"UNKNOWN_REFERENCE", "DISABLED_MASTER_REFERENCE"} <= rule_ids


def test_validator_detects_unknown_teacher_home_campus(
    minimal_input_data: InputDataModel,
) -> None:
    invalid = replace(
        minimal_input_data,
        teachers=(
            replace(minimal_input_data.teachers[0], home_campus_id="UNKNOWN"),
            minimal_input_data.teachers[1],
        ),
    )

    issues = ReferenceIntegrityValidator().validate(invalid)

    assert any(
        issue.rule_id == "UNKNOWN_REFERENCE"
        and issue.target == "T1"
        and "home_campus_id" in issue.message
        for issue in issues
    )


def test_validator_detects_requirement_and_teacher_leave_duplicates(
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
        teacher_leaves=(
            TeacherLeaveModel("T1", minimal_input_data.calendar_days[0].target_date, ("P1",)),
            TeacherLeaveModel(
                "T1",
                minimal_input_data.calendar_days[0].target_date,
                ("P2", "P2"),
            ),
        ),
    )

    rule_ids = {issue.rule_id for issue in ReferenceIntegrityValidator().validate(invalid)}

    assert {
        "DUPLICATE_CLASS_SUBJECT_REQUIREMENT",
        "DUPLICATE_TEACHER_LEAVE",
        "DUPLICATE_TEACHER_LEAVE_PERIOD",
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
        preferred_attendance_streak_limit=0,
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
    teacher_one_full_leave = replace(
        minimal_input_data,
        teacher_leaves=tuple(
            TeacherLeaveModel(
                "T1",
                calendar_day.target_date,
                tuple(period.period_id for period in minimal_input_data.periods),
            )
            for calendar_day in minimal_input_data.calendar_days
            if calendar_day.output_enabled
        ),
    )
    resolved = RuleResolverService().execute(teacher_one_full_leave)
    candidates = CandidateBuilderService().execute(
        teacher_one_full_leave,
        resolved,
    )

    issues = CapacityFeasibilityValidator().validate(
        teacher_one_full_leave,
        resolved,
        candidates,
    )

    assert any(
        issue.rule_id == "CANDIDATE_SUPPLY_SHORTAGE" and issue.target == "Q1" for issue in issues
    )


def test_validator_detects_lesson_count_rule_group_and_reference_errors(
    minimal_input_data: InputDataModel,
) -> None:
    invalid = replace(
        minimal_input_data,
        lesson_count_rule_segments=(
            LessonCountRuleSegmentModel(
                "LC1",
                "SEG1",
                "対象",
                True,
                "CL1",
                "S1",
                0,
                date(2026, 7, 27),
                date(2026, 7, 27),
                ("ALL", "P1"),
            ),
            LessonCountRuleSegmentModel(
                "LC1",
                "SEG2",
                "対象",
                True,
                "UNKNOWN",
                "S1",
                1,
                date(2026, 7, 28),
                date(2026, 7, 28),
                ("P1",),
            ),
        ),
    )

    rule_ids = {issue.rule_id for issue in ReferenceIntegrityValidator().validate(invalid)}

    assert {
        "INVALID_LESSON_COUNT_RULE_PERIODS",
        "UNKNOWN_REFERENCE",
        "LESSON_COUNT_RULE_GROUP_MISMATCH",
    } <= rule_ids


def test_capacity_validator_detects_h17_scope_supply_shortage(
    minimal_input_data: InputDataModel,
) -> None:
    input_data = replace(
        minimal_input_data,
        lesson_count_rule_segments=(
            LessonCountRuleSegmentModel(
                "LC1",
                "SEG1",
                "範囲不足",
                True,
                "CL1",
                "S1",
                2,
                date(2026, 7, 27),
                date(2026, 7, 27),
                ("P1",),
            ),
        ),
    )
    resolved = RuleResolverService().execute(input_data)
    candidates = CandidateBuilderService().execute(input_data, resolved)

    issues = CapacityFeasibilityValidator().validate(input_data, resolved, candidates)

    assert any(issue.rule_id == "LESSON_COUNT_RULE_SCOPE_SUPPLY_SHORTAGE" for issue in issues)


def test_capacity_validator_detects_h18_homeroom_candidate_shortage(
    minimal_input_data: InputDataModel,
) -> None:
    input_data = replace(
        minimal_input_data,
        homeroom_boundary_rules=(
            HomeroomBoundaryRuleModel(
                "HB1", "前半", True, "CL2", date(2026, 7, 27), date(2026, 7, 28)
            ),
        ),
    )
    resolved = RuleResolverService().execute(input_data)
    candidates = CandidateBuilderService().execute(input_data, resolved)
    candidates_without_homeroom = replace(
        candidates,
        candidates=tuple(
            replace(candidate, teacher_id="T1") if candidate.class_id == "CL2" else candidate
            for candidate in candidates.candidates
        ),
    )

    issues = CapacityFeasibilityValidator().validate(
        input_data,
        resolved,
        candidates_without_homeroom,
    )

    assert any(issue.rule_id == "HOMEROOM_BOUNDARY_TEACHER_SUPPLY_SHORTAGE" for issue in issues)


def test_validator_detects_lesson_count_preference_group_and_range_errors(
    minimal_input_data: InputDataModel,
) -> None:
    invalid = replace(
        minimal_input_data,
        lesson_count_preference_rule_segments=(
            LessonCountPreferenceRuleSegmentModel(
                "LP1",
                "LP1_SEG1",
                "3限を避ける",
                True,
                "CL1",
                "S1",
                -1,
                date(2026, 7, 27),
                date(2026, 7, 27),
                ("ALL", "P3"),
            ),
            LessonCountPreferenceRuleSegmentModel(
                "LP1",
                "LP1_SEG2",
                "3限を避ける",
                True,
                "CL1",
                "S1",
                3,
                date(2026, 7, 28),
                date(2026, 7, 28),
                ("P3",),
            ),
        ),
    )

    rule_ids = {issue.rule_id for issue in ReferenceIntegrityValidator().validate(invalid)}

    assert {
        "INVALID_LESSON_COUNT_PREFERENCE_PERIODS",
        "LESSON_COUNT_PREFERENCE_GROUP_MISMATCH",
    } <= rule_ids


def test_validator_rejects_preference_above_required_periods(
    minimal_input_data: InputDataModel,
) -> None:
    invalid = replace(
        minimal_input_data,
        lesson_count_preference_rule_segments=(
            LessonCountPreferenceRuleSegmentModel(
                "LP_TOO_HIGH",
                "LP_TOO_HIGH_SEG1",
                "希望過大",
                True,
                "CL1",
                "S1",
                3,
                date(2026, 7, 27),
                date(2026, 7, 27),
                ("P3",),
            ),
        ),
    )

    rule_ids = {issue.rule_id for issue in ReferenceIntegrityValidator().validate(invalid)}

    assert "LESSON_COUNT_PREFERENCE_EXCEEDS_REQUIRED" in rule_ids

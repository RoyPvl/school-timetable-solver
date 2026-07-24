from __future__ import annotations

from dataclasses import replace
from datetime import date

from school_timetable_solver.model.input_models import InputDataModel, PlacementRuleModel
from school_timetable_solver.service.planning_services import (
    CandidateBuilderService,
    RuleResolverService,
)


def test_rule_resolver_applies_hard_intersection_override_and_minimum_limits(
    minimal_input_data: InputDataModel,
) -> None:
    resolved = RuleResolverService().execute(minimal_input_data)

    first = next(
        item
        for item in resolved.class_date_rules
        if item.class_id == "CL1" and item.target_date == date(2026, 7, 27)
    )
    overridden = next(
        item
        for item in resolved.class_date_rules
        if item.class_id == "CL2" and item.target_date == date(2026, 7, 28)
    )

    assert first.allowed_period_ids == ("P1", "P2", "P3")
    assert first.daily_hard_limit == 3
    assert overridden.allowed_period_ids == ("P4", "P5", "P6")
    assert overridden.daily_hard_limit == 2
    assert overridden.attendance_streak_limit == 2
    assert not resolved.issues


def test_rule_resolver_supports_class_attributes_teacher_id_campus_date_weekday_and_between(
    minimal_input_data: InputDataModel,
) -> None:
    resolved = RuleResolverService().execute(minimal_input_data)
    override = next(
        item
        for item in resolved.class_date_rules
        if item.class_id == "CL2" and item.target_date == date(2026, 7, 28)
    )
    teacher = next(
        item
        for item in resolved.teacher_date_rules
        if item.teacher_id == "T1" and item.target_date == date(2026, 7, 27)
    )

    assert "R_JH_OVERRIDE" in override.applied_rule_ids
    assert "R_TEACHER_BASE" in teacher.applied_rule_ids


def test_rule_resolver_reports_same_priority_conflict_and_missing_values(
    minimal_input_data: InputDataModel,
) -> None:
    conflict = replace(
        minimal_input_data.placement_rules[1],
        rule_id="R_CONFLICT",
        allowed_period_ids=("P4",),
    )
    without_teacher_rules = tuple(
        rule for rule in minimal_input_data.placement_rules if rule.target_entity != "teacher"
    )
    invalid = replace(
        minimal_input_data,
        placement_rules=(*without_teacher_rules, conflict),
    )

    resolved = RuleResolverService().execute(invalid)
    rule_ids = {issue.rule_id for issue in resolved.issues}

    assert {"RULE_PRIORITY_CONFLICT", "RULE_REQUIRED_VALUE_MISSING"} <= rule_ids


def test_candidate_builder_uses_output_periods_assigned_teacher_and_same_campus_rooms(
    minimal_input_data: InputDataModel,
) -> None:
    resolved = RuleResolverService().execute(minimal_input_data)
    result = CandidateBuilderService().execute(minimal_input_data, resolved)
    q1 = [candidate for candidate in result.candidates if candidate.requirement_id == "Q1"]

    assert q1
    assert {candidate.target_date for candidate in q1} == {
        date(2026, 7, 27),
        date(2026, 7, 28),
    }
    assert {candidate.period_id for candidate in q1} <= {"P1", "P2", "P3"}
    assert {candidate.teacher_id for candidate in q1} == {"T1"}
    assert {candidate.room_id for candidate in q1} == {"R1", "R2"}


def test_candidate_builder_treats_missing_teacher_row_as_unavailable(
    minimal_input_data: InputDataModel,
) -> None:
    input_data = replace(
        minimal_input_data,
        teacher_availability=tuple(
            item
            for item in minimal_input_data.teacher_availability
            if not (item.teacher_id == "T1" and item.target_date == date(2026, 7, 27))
        ),
    )
    resolved = RuleResolverService().execute(input_data)
    result = CandidateBuilderService().execute(input_data, resolved)

    assert not [
        item
        for item in result.candidates
        if item.teacher_id == "T1" and item.target_date == date(2026, 7, 27)
    ]
    assert any(summary.rule_id == "H05" for summary in result.rejection_summaries)


def test_rule_resolver_in_operator_uses_slash_values(
    minimal_input_data: InputDataModel,
) -> None:
    in_rule = PlacementRuleModel(
        "R_IN",
        "受験区分",
        True,
        "hard",
        "class",
        ("exam_category",),
        ("in",),
        ("exam/special",),
        "C2",
        None,
        None,
        (),
        ("P1", "P2"),
        None,
        None,
        None,
        25,
    )
    input_data = replace(
        minimal_input_data,
        placement_rules=(*minimal_input_data.placement_rules, in_rule),
    )

    resolved = RuleResolverService().execute(input_data)
    target = next(
        item
        for item in resolved.class_date_rules
        if item.class_id == "CL2" and item.target_date == date(2026, 7, 27)
    )

    assert target.allowed_period_ids == ("P1", "P2")

from __future__ import annotations

from dataclasses import replace
from datetime import date

from school_timetable_solver.model.input_models import (
    ClassPairOverlapRuleModel,
    HomeroomBoundaryRuleModel,
    InputDataModel,
    LessonCountPreferenceRuleSegmentModel,
    LessonCountRuleSegmentModel,
    LessonRequirementModel,
    PlacementRuleModel,
    TeacherLeaveModel,
)
from school_timetable_solver.model.master_models import SubjectModel
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


def test_rule_resolver_unions_and_overrides_required_lesson_periods(
    minimal_input_data: InputDataModel,
) -> None:
    base = replace(
        minimal_input_data.placement_rules[0],
        rule_id="R_REQUIRED_BASE",
        required_lesson_period_ids=("P1",),
        priority=40,
    )
    hard = replace(
        base,
        rule_id="R_REQUIRED_HARD",
        required_lesson_period_ids=("P2",),
        priority=50,
    )
    override = replace(
        base,
        rule_id="R_REQUIRED_OVERRIDE",
        constraint_type="override",
        required_lesson_period_ids=("P3",),
        priority=60,
    )
    input_data = replace(
        minimal_input_data,
        placement_rules=(*minimal_input_data.placement_rules, base, hard, override),
    )

    resolved = RuleResolverService().execute(input_data)
    rule = next(
        item
        for item in resolved.class_date_rules
        if item.class_id == "CL1" and item.target_date == date(2026, 7, 27)
    )

    assert rule.required_lesson_period_ids == ("P3",)


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


def test_rule_resolver_allows_missing_hard_attendance_limit_and_resolves_preference(
    minimal_input_data: InputDataModel,
) -> None:
    placement_rules = tuple(
        replace(
            rule,
            attendance_streak_limit=None,
            preferred_attendance_streak_limit=3 if rule.target_entity == "class" else None,
        )
        for rule in minimal_input_data.placement_rules
    )
    input_data = replace(minimal_input_data, placement_rules=placement_rules)

    resolved = RuleResolverService().execute(input_data)

    assert not resolved.issues
    assert all(rule.attendance_streak_limit is None for rule in resolved.class_date_rules)
    assert all(rule.preferred_attendance_streak_limit == 3 for rule in resolved.class_date_rules)


def test_rule_resolver_builds_one_attendance_group_for_a_configured_pair(
    minimal_input_data: InputDataModel,
) -> None:
    placement_rules = tuple(
        replace(
            rule,
            attendance_streak_limit=(3 if rule.target_entity == "class" else None),
            preferred_attendance_streak_limit=(2 if rule.target_entity == "class" else None),
        )
        for rule in minimal_input_data.placement_rules
    )
    input_data = replace(
        minimal_input_data,
        placement_rules=placement_rules,
        class_pair_overlap_rules=(ClassPairOverlapRuleModel("PAIR1", "組1", True, "CL1", "CL2"),),
    )

    resolved = RuleResolverService().execute(input_data)

    assert not resolved.issues
    assert len(resolved.attendance_groups) == 1
    group = resolved.attendance_groups[0]
    assert group.group_id == "PAIR::PAIR1"
    assert group.class_ids == ("CL1", "CL2")
    assert {limit for _, limit in group.attendance_streak_limits} == {3}
    assert {limit for _, limit in group.preferred_attendance_streak_limits} == {2}


def test_rule_resolver_rejects_mismatched_pair_attendance_limits(
    minimal_input_data: InputDataModel,
) -> None:
    input_data = replace(
        minimal_input_data,
        class_pair_overlap_rules=(ClassPairOverlapRuleModel("PAIR1", "組1", True, "CL1", "CL2"),),
    )

    resolved = RuleResolverService().execute(input_data)

    assert any(issue.rule_id == "PAIR_ATTENDANCE_LIMIT_MISMATCH" for issue in resolved.issues)


def test_rule_resolver_expands_homeroom_boundary_rule_to_matching_class_and_all_lessons(
    minimal_input_data: InputDataModel,
) -> None:
    rule = HomeroomBoundaryRuleModel(
        "HB1",
        "中学の夏期期間端",
        True,
        ("division", "has_regular_homeroom_lesson"),
        ("eq", "eq"),
        ("junior_high", "TRUE"),
        date(2026, 7, 27),
        date(2026, 7, 28),
    )
    input_data = replace(
        minimal_input_data,
        subjects=(*minimal_input_data.subjects, SubjectModel("S3", "特別講座", "special", True)),
        lesson_requirements=(
            *minimal_input_data.lesson_requirements,
            LessonRequirementModel("Q3", "CL2", "S3", "T1", 1, 1, True),
        ),
        homeroom_boundary_rules=(rule,),
    )

    resolved = RuleResolverService().execute(input_data)

    assert not resolved.issues
    assert len(resolved.homeroom_boundary_rules) == 1
    boundary = resolved.homeroom_boundary_rules[0]
    assert boundary.class_id == "CL2"
    assert boundary.teacher_id == "T2"
    assert boundary.attendance_requirement_ids == ("Q2", "Q3")
    assert boundary.eligible_requirement_ids == ("Q2",)


def test_rule_resolver_rejects_preferred_attendance_limit_above_hard_limit(
    minimal_input_data: InputDataModel,
) -> None:
    invalid_rule = replace(
        minimal_input_data.placement_rules[0],
        attendance_streak_limit=3,
        preferred_attendance_streak_limit=4,
    )
    input_data = replace(
        minimal_input_data,
        placement_rules=(invalid_rule, *minimal_input_data.placement_rules[1:]),
    )

    resolved = RuleResolverService().execute(input_data)

    assert any(issue.rule_id == "RULE_ATTENDANCE_LIMIT_ORDER" for issue in resolved.issues)


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
    assert {candidate.campus_id for candidate in q1} == {"C1"}
    assert len(q1) == len(
        {(candidate.requirement_id, candidate.target_date, candidate.period_id) for candidate in q1}
    )


def test_candidate_builder_treats_missing_teacher_leave_row_as_available(
    minimal_input_data: InputDataModel,
) -> None:
    resolved = RuleResolverService().execute(minimal_input_data)
    result = CandidateBuilderService().execute(minimal_input_data, resolved)

    assert [
        item
        for item in result.candidates
        if item.teacher_id == "T1" and item.target_date == date(2026, 7, 27)
    ]
    assert not [summary for summary in result.rejection_summaries if summary.rule_id == "H05"]


def test_candidate_builder_excludes_only_teacher_leave_periods(
    minimal_input_data: InputDataModel,
) -> None:
    input_data = replace(
        minimal_input_data,
        teacher_leaves=(TeacherLeaveModel("T1", date(2026, 7, 27), ("P1", "P2")),),
    )
    resolved = RuleResolverService().execute(input_data)
    result = CandidateBuilderService().execute(input_data, resolved)
    t1_candidates = [
        item
        for item in result.candidates
        if item.teacher_id == "T1" and item.target_date == date(2026, 7, 27)
    ]

    assert {item.period_id for item in t1_candidates} == {"P3"}
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


def test_rule_resolver_unions_segments_and_keeps_overlapping_rules_as_and_conditions(
    minimal_input_data: InputDataModel,
) -> None:
    segments = (
        LessonCountRuleSegmentModel(
            "LC_A",
            "LC_A_1",
            "複数日",
            True,
            "CL1",
            "S1",
            1,
            date(2026, 7, 27),
            date(2026, 7, 27),
            ("P1", "P2"),
        ),
        LessonCountRuleSegmentModel(
            "LC_A",
            "LC_A_2",
            "複数日",
            True,
            "CL1",
            "S1",
            1,
            date(2026, 7, 28),
            date(2026, 7, 28),
            ("ALL",),
        ),
        LessonCountRuleSegmentModel(
            "LC_B",
            "LC_B_1",
            "重複範囲",
            True,
            "CL1",
            "S1",
            1,
            date(2026, 7, 27),
            date(2026, 7, 27),
            ("P2", "P3"),
        ),
    )
    input_data = replace(minimal_input_data, lesson_count_rule_segments=segments)

    resolved = RuleResolverService().execute(input_data)

    assert len(resolved.lesson_count_rules) == 2
    rule_a, rule_b = resolved.lesson_count_rules
    assert rule_a.rule_id == "LC_A"
    assert (date(2026, 7, 27), "P2") in rule_a.target_slots
    assert (date(2026, 7, 28), "P3") in rule_a.target_slots
    assert rule_b.rule_id == "LC_B"
    assert set(rule_a.target_slots).intersection(rule_b.target_slots) == {(date(2026, 7, 27), "P2")}


def test_candidate_builder_excludes_h17_zero_count_slots(
    minimal_input_data: InputDataModel,
) -> None:
    input_data = replace(
        minimal_input_data,
        lesson_count_rule_segments=(
            LessonCountRuleSegmentModel(
                "LC_ZERO",
                "LC_ZERO_1",
                "配置禁止",
                True,
                "CL1",
                "S1",
                0,
                date(2026, 7, 27),
                date(2026, 7, 27),
                ("P1", "P2"),
            ),
        ),
    )
    resolved = RuleResolverService().execute(input_data)

    result = CandidateBuilderService().execute(input_data, resolved)

    day_one_q1 = {
        candidate.period_id
        for candidate in result.candidates
        if candidate.requirement_id == "Q1" and candidate.target_date == date(2026, 7, 27)
    }
    assert day_one_q1 == {"P3"}
    assert any(summary.rule_id == "H17" for summary in result.rejection_summaries)


def test_rule_resolver_unions_lesson_count_preference_segments(
    minimal_input_data: InputDataModel,
) -> None:
    input_data = replace(
        minimal_input_data,
        lesson_count_preference_rule_segments=(
            LessonCountPreferenceRuleSegmentModel(
                "LP1",
                "LP1_SEG1",
                "3限を避ける",
                True,
                "CL1",
                "S1",
                0,
                date(2026, 7, 27),
                date(2026, 7, 27),
                ("P3",),
            ),
            LessonCountPreferenceRuleSegmentModel(
                "LP1",
                "LP1_SEG2",
                "3限を避ける",
                True,
                "CL1",
                "S1",
                0,
                date(2026, 7, 28),
                date(2026, 7, 28),
                ("P3",),
            ),
        ),
    )

    resolved = RuleResolverService().execute(input_data)

    assert len(resolved.lesson_count_preference_rules) == 1
    assert resolved.lesson_count_preference_rules[0].target_slots == (
        (date(2026, 7, 27), "P3"),
        (date(2026, 7, 28), "P3"),
    )


def test_candidate_builder_does_not_exclude_s17_zero_preference_slots(
    minimal_input_data: InputDataModel,
) -> None:
    input_data = replace(
        minimal_input_data,
        lesson_count_preference_rule_segments=(
            LessonCountPreferenceRuleSegmentModel(
                "LP_ZERO",
                "LP_ZERO_SEG1",
                "3限を避ける",
                True,
                "CL1",
                "S1",
                0,
                date(2026, 7, 27),
                date(2026, 7, 27),
                ("P3",),
            ),
        ),
    )
    resolved = RuleResolverService().execute(input_data)

    result = CandidateBuilderService().execute(input_data, resolved)

    assert any(
        candidate.requirement_id == "Q1"
        and candidate.target_date == date(2026, 7, 27)
        and candidate.period_id == "P3"
        for candidate in result.candidates
    )
    assert not [summary for summary in result.rejection_summaries if summary.rule_id == "S17"]

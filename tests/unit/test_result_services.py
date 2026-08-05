from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta

import pytest

from school_timetable_solver.model.input_models import (
    InputDataModel,
    LessonCountPreferenceRuleSegmentModel,
    LessonCountRuleSegmentModel,
    TeacherDayOffRuleModel,
    TeacherLeaveModel,
)
from school_timetable_solver.model.result_models import (
    ScheduledLessonDraftModel,
    ScheduledLessonModel,
    ScheduledTeacherDayOffModel,
)
from school_timetable_solver.service.planning_services import (
    CandidateBuilderService,
    RuleResolverService,
)
from school_timetable_solver.service.result_services import (
    AssignRoomsService,
    BuildTimetableDocumentService,
    ValidateResultService,
)


def _draft(
    requirement_id: str,
    class_id: str,
    campus_id: str = "C1",
    period_id: str = "P1",
    room_index: int = 0,
) -> ScheduledLessonDraftModel:
    return ScheduledLessonDraftModel(
        requirement_id=requirement_id,
        target_date=date(2026, 7, 27),
        period_id=period_id,
        teacher_id="T1",
        campus_id=campus_id,
        class_id=class_id,
        subject_id="S1",
        room_index=room_index,
    )


def _lesson(
    requirement_id: str = "Q1",
    target_date: date = date(2026, 7, 27),
    period_id: str = "P1",
    teacher_id: str = "T1",
    room_id: str = "R1",
    campus_id: str = "C1",
    class_id: str = "CL1",
    subject_id: str = "S1",
) -> ScheduledLessonModel:
    return ScheduledLessonModel(
        requirement_id,
        target_date,
        period_id,
        teacher_id,
        room_id,
        campus_id,
        class_id,
        subject_id,
    )


def test_validate_result_reports_output_date_teacher_leave_allowed_period_and_campus(
    minimal_input_data: InputDataModel,
) -> None:
    input_data = replace(
        minimal_input_data,
        teacher_leaves=(TeacherLeaveModel("T1", date(2026, 7, 27), ("P6",)),),
    )
    resolved = RuleResolverService().execute(input_data)
    lessons = (
        _lesson(period_id="P6", room_id="R3"),
        _lesson(
            requirement_id="Q2",
            teacher_id="T1",
            room_id="R3",
            campus_id="C2",
            class_id="CL2",
            subject_id="S2",
        ),
        _lesson(
            requirement_id="Q2",
            target_date=date(2026, 7, 30),
            teacher_id="T2",
            room_id="R3",
            campus_id="C2",
            class_id="CL2",
            subject_id="S2",
        ),
    )

    report = ValidateResultService().execute(input_data, resolved, lessons)
    rule_ids = {issue.rule_id for issue in report.issues}

    assert {"H04", "H05", "H06", "H11", "H13", "H14"} <= rule_ids


@pytest.mark.parametrize(
    ("period_ids", "has_h09_issue"),
    (
        (("P1", "P2", "P3", "P4", "P5"), False),
        (("P2", "P3", "P4", "P5", "P6"), False),
        (("P1", "P3", "P4", "P5", "P6"), True),
        (("P2", "P4", "P5", "P6"), False),
        (("P1", "P2", "P3", "P4", "P5", "P6"), True),
    ),
)
def test_result_validator_applies_h09_teacher_work_pattern(
    minimal_input_data: InputDataModel,
    period_ids: tuple[str, ...],
    has_h09_issue: bool,
) -> None:
    input_data = replace(
        minimal_input_data,
        placement_rules=tuple(
            replace(rule, consecutive_limit=5) if rule.rule_id == "R_TEACHER_BASE" else rule
            for rule in minimal_input_data.placement_rules
        ),
    )
    resolved = RuleResolverService().execute(input_data)
    lessons = tuple(
        _lesson(requirement_id=f"Q{index}", period_id=period_id)
        for index, period_id in enumerate(period_ids, start=1)
    )

    report = ValidateResultService().execute(input_data, resolved, lessons)
    h09_issues = [issue for issue in report.issues if issue.rule_id == "H09"]

    assert bool(h09_issues) is has_h09_issue


def test_assign_rooms_uses_class_id_and_room_output_order_stably(
    minimal_input_data: InputDataModel,
) -> None:
    assigned = AssignRoomsService().execute(
        minimal_input_data,
        (
            _draft("Q2", "CL2", room_index=1),
            _draft("Q1", "CL1"),
        ),
    )

    assert [(item.class_id, item.room_id) for item in assigned] == [
        ("CL1", "R1"),
        ("CL2", "R2"),
    ]


def test_assign_rooms_rejects_anonymous_room_index_out_of_range(
    minimal_input_data: InputDataModel,
) -> None:
    with pytest.raises(ValueError, match="範囲外"):
        AssignRoomsService().execute(
            minimal_input_data,
            (_draft("Q1", "CL1", room_index=2),),
        )


def test_assign_rooms_maps_same_anonymous_room_to_same_physical_room(
    minimal_input_data: InputDataModel,
) -> None:
    assigned = AssignRoomsService().execute(
        minimal_input_data,
        (
            _draft("Q1", "CL1", period_id="P1"),
            _draft("Q2", "CL1", period_id="P3"),
            _draft("Q3", "CL2", period_id="P2", room_index=1),
        ),
    )

    assert [(item.class_id, item.room_id) for item in assigned] == [
        ("CL1", "R1"),
        ("CL2", "R2"),
        ("CL1", "R1"),
    ]
    assert {item.room_id for item in assigned if item.class_id == "CL1"} == {"R1"}


def test_document_builder_sorts_axes_and_maps_ids_to_display_names(
    minimal_input_data: InputDataModel,
) -> None:
    lessons = (
        _lesson(
            requirement_id="Q2",
            target_date=date(2026, 7, 28),
            period_id="P4",
            teacher_id="T2",
            room_id="R3",
            campus_id="C2",
            class_id="CL2",
            subject_id="S2",
        ),
        _lesson(),
    )

    document = BuildTimetableDocumentService().execute(minimal_input_data, lessons)

    assert [item.target_date for item in document.dates] == sorted(
        item.target_date for item in document.dates
    )
    assert [item.campus_id for item in document.campuses] == ["C1", "C2"]
    assert [item.room_id for item in document.campuses[0].rooms] == ["R1", "R2"]
    assert [item.period_id for item in document.periods] == [f"P{i}" for i in range(1, 7)]
    output_lesson = document.dates[0].lessons_by_period_and_room[("P1", "R1")]
    assert (
        output_lesson.class_display_name,
        output_lesson.subject_display_name,
        output_lesson.teacher_display_name,
    ) == ("小学A", "算数", "教師一")


def test_flexible_teacher_day_off_is_validated_and_rendered_as_full_day(
    minimal_input_data: InputDataModel,
) -> None:
    target_date = minimal_input_data.calendar_days[0].target_date
    input_data = replace(
        minimal_input_data,
        teacher_day_off_rules=(
            TeacherDayOffRuleModel("DAY_OFF_T1", "T1", True, target_date, target_date, 1),
        ),
    )
    day_offs = (ScheduledTeacherDayOffModel("T1", target_date),)
    resolved = RuleResolverService().execute(input_data)

    report = ValidateResultService().execute(
        input_data,
        resolved,
        (),
        teacher_day_offs=day_offs,
    )
    document = BuildTimetableDocumentService().execute(input_data, (), day_offs)

    assert not {issue.rule_id for issue in report.issues} & {"H18", "H19"}
    output_leave = document.dates[0].teacher_leaves[0]
    assert output_leave.teacher_display_name == "教師一"
    assert output_leave.unavailable_period_ids == tuple(f"P{i}" for i in range(1, 7))


def test_result_validator_reports_teacher_day_off_work_and_annotation_overflow(
    minimal_input_data: InputDataModel,
) -> None:
    target_date = minimal_input_data.calendar_days[0].target_date
    input_data = replace(
        minimal_input_data,
        rooms=(minimal_input_data.rooms[0], minimal_input_data.rooms[2]),
        teachers=(
            minimal_input_data.teachers[0],
            replace(minimal_input_data.teachers[1], home_campus_id="C1"),
        ),
        teacher_day_off_rules=(
            TeacherDayOffRuleModel("DAY_OFF_T1", "T1", True, target_date, target_date, 1),
            TeacherDayOffRuleModel("DAY_OFF_T2", "T2", True, target_date, target_date, 1),
        ),
    )
    resolved = RuleResolverService().execute(input_data)
    day_offs = (
        ScheduledTeacherDayOffModel("T1", target_date),
        ScheduledTeacherDayOffModel("T2", target_date),
    )

    report = ValidateResultService().execute(
        input_data,
        resolved,
        (_lesson(),),
        teacher_day_offs=day_offs,
    )

    assert {"H18", "H19"} <= {issue.rule_id for issue in report.issues}


def test_document_builder_rejects_duplicate_slot_and_output_excluded_date(
    minimal_input_data: InputDataModel,
) -> None:
    builder = BuildTimetableDocumentService()

    with pytest.raises(ValueError, match="重複"):
        builder.execute(minimal_input_data, (_lesson(), _lesson(requirement_id="Q2")))
    with pytest.raises(ValueError, match="出力対象外日"):
        builder.execute(
            minimal_input_data,
            (_lesson(target_date=date(2026, 7, 30)),),
        )


def test_result_validator_reports_required_count_and_overlaps(
    minimal_input_data: InputDataModel,
) -> None:
    resolved = RuleResolverService().execute(minimal_input_data)
    duplicate = replace(_lesson(requirement_id="Q2"), subject_id="S2")

    report = ValidateResultService().execute(
        minimal_input_data,
        resolved,
        (_lesson(), duplicate),
    )

    assert {"H01", "H02", "H03", "H06"} <= {issue.rule_id for issue in report.issues}


def test_result_validator_reports_lesson_count_in_scope(
    minimal_input_data: InputDataModel,
) -> None:
    input_data = replace(
        minimal_input_data,
        lesson_count_rule_segments=(
            LessonCountRuleSegmentModel(
                "LC1",
                "LC1_SEG1",
                "初日1コマ",
                True,
                "CL1",
                "S1",
                1,
                date(2026, 7, 27),
                date(2026, 7, 27),
                ("ALL",),
            ),
        ),
    )
    resolved = RuleResolverService().execute(input_data)
    lessons = (
        _lesson(requirement_id="Q1", period_id="P1"),
        _lesson(requirement_id="Q1", period_id="P2"),
    )

    report = ValidateResultService().execute(input_data, resolved, lessons)

    assert "H17" in {issue.rule_id for issue in report.issues}


def test_result_validator_warns_for_lesson_count_preference_deviation(
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
        ),
    )
    resolved = RuleResolverService().execute(input_data)
    lessons = (
        _lesson(requirement_id="Q1", period_id="P1"),
        _lesson(requirement_id="Q1", period_id="P3"),
    )

    report = ValidateResultService().execute(input_data, resolved, lessons)

    s17_issues = [issue for issue in report.issues if issue.rule_id == "S17"]
    assert len(s17_issues) == 1
    assert s17_issues[0].severity == "WARNING"
    assert s17_issues[0].target == "LP1"
    assert "deviation=1" in s17_issues[0].message


def test_result_validator_reports_room_move_and_warns_room_change_without_gap(
    minimal_input_data: InputDataModel,
) -> None:
    resolved = RuleResolverService().execute(minimal_input_data)
    lessons = (
        _lesson(requirement_id="Q1", period_id="P1", room_id="R1", class_id="CL1"),
        _lesson(requirement_id="Q2", period_id="P3", room_id="R2", class_id="CL1"),
        _lesson(requirement_id="Q3", period_id="P2", room_id="R1", class_id="CL3"),
    )

    report = ValidateResultService().execute(minimal_input_data, resolved, lessons)
    h15_messages = [issue.message for issue in report.issues if issue.rule_id == "H15"]
    s10_issues = [issue for issue in report.issues if issue.rule_id == "S10"]
    s11_issues = [issue for issue in report.issues if issue.rule_id == "S11"]

    assert any("複数教室" in message for message in h15_messages)
    assert any("空き時限なし" in issue.message for issue in s10_issues)
    assert all(issue.severity == "WARNING" for issue in s10_issues)
    assert any("空き時限" in issue.message for issue in s11_issues)
    assert all(issue.severity == "WARNING" for issue in s11_issues)


def test_result_validator_allows_room_reuse_after_one_empty_period(
    minimal_input_data: InputDataModel,
) -> None:
    resolved = RuleResolverService().execute(minimal_input_data)
    lessons = (
        _lesson(requirement_id="Q1", period_id="P1", room_id="R1", class_id="CL1"),
        _lesson(requirement_id="Q2", period_id="P3", room_id="R1", class_id="CL2"),
    )

    report = ValidateResultService().execute(minimal_input_data, resolved, lessons)

    assert not [issue for issue in report.issues if issue.rule_id in {"H15", "S10", "S11"}]
    assert len([issue for issue in report.issues if issue.rule_id == "S12"]) == 2


def test_result_validator_reports_s19_room_priority_penalty(
    minimal_input_data: InputDataModel,
) -> None:
    resolved = RuleResolverService().execute(minimal_input_data)
    lessons = (_lesson(requirement_id="Q1", period_id="P1", room_id="R1", class_id="CL1"),)

    report = ValidateResultService().execute(minimal_input_data, resolved, lessons)

    s19_issues = [issue for issue in report.issues if issue.rule_id == "S19"]
    assert len(s19_issues) == 1
    assert s19_issues[0].severity == "WARNING"
    assert "lessons=1" in s19_issues[0].message
    assert "penalty=100" in s19_issues[0].message


def test_result_validator_warns_only_for_exactly_one_lesson_class_days(
    minimal_input_data: InputDataModel,
) -> None:
    resolved = RuleResolverService().execute(minimal_input_data)
    lessons = (
        _lesson(requirement_id="Q1", period_id="P1", class_id="CL1"),
        _lesson(requirement_id="Q2", period_id="P2", class_id="CL1"),
        _lesson(
            requirement_id="Q3",
            teacher_id="T2",
            room_id="R3",
            campus_id="C2",
            class_id="CL2",
            subject_id="S2",
        ),
    )

    report = ValidateResultService().execute(minimal_input_data, resolved, lessons)
    s12_issues = [issue for issue in report.issues if issue.rule_id == "S12"]

    assert len(s12_issues) == 1
    assert "CL2" in s12_issues[0].target
    assert s12_issues[0].severity == "WARNING"


def test_result_validator_warns_for_each_adjacent_same_subject_pair(
    minimal_input_data: InputDataModel,
) -> None:
    resolved = RuleResolverService().execute(minimal_input_data)
    lessons = (
        _lesson(requirement_id="Q1", period_id="P1", teacher_id="T1", subject_id="S1"),
        _lesson(requirement_id="Q2", period_id="P2", teacher_id="T2", subject_id="S1"),
        _lesson(requirement_id="Q3", period_id="P3", teacher_id="T1", subject_id="S1"),
        _lesson(requirement_id="Q4", period_id="P4", teacher_id="T2", subject_id="S2"),
    )

    report = ValidateResultService().execute(minimal_input_data, resolved, lessons)
    s13_issues = [issue for issue in report.issues if issue.rule_id == "S13"]

    assert len(s13_issues) == 2
    assert all(issue.severity == "WARNING" for issue in s13_issues)


def test_result_validator_warns_for_double_day_and_same_subject_next_day(
    minimal_input_data: InputDataModel,
) -> None:
    resolved = RuleResolverService().execute(minimal_input_data)
    lessons = (
        _lesson(
            requirement_id="Q1",
            target_date=date(2026, 7, 27),
            period_id="P1",
            teacher_id="T1",
            subject_id="S1",
        ),
        _lesson(
            requirement_id="Q2",
            target_date=date(2026, 7, 27),
            period_id="P2",
            teacher_id="T2",
            subject_id="S1",
        ),
        _lesson(
            requirement_id="Q3",
            target_date=date(2026, 7, 28),
            period_id="P1",
            teacher_id="T1",
            subject_id="S1",
        ),
    )

    report = ValidateResultService().execute(minimal_input_data, resolved, lessons)
    s14_issues = [issue for issue in report.issues if issue.rule_id == "S14"]
    s15_issues = [issue for issue in report.issues if issue.rule_id == "S15"]

    assert len(s14_issues) == 1
    assert len(s15_issues) == 1
    assert all(issue.severity == "WARNING" for issue in (*s14_issues, *s15_issues))


def test_result_validator_does_not_treat_the_next_output_date_as_next_calendar_day(
    minimal_input_data: InputDataModel,
) -> None:
    resolved = RuleResolverService().execute(minimal_input_data)
    lessons = (
        _lesson(
            requirement_id="Q1",
            target_date=date(2026, 7, 27),
            period_id="P1",
            teacher_id="T1",
            subject_id="S1",
        ),
        _lesson(
            requirement_id="Q2",
            target_date=date(2026, 7, 27),
            period_id="P2",
            teacher_id="T2",
            subject_id="S1",
        ),
        _lesson(
            requirement_id="Q3",
            target_date=date(2026, 7, 29),
            period_id="P1",
            teacher_id="T1",
            subject_id="S1",
        ),
    )

    report = ValidateResultService().execute(minimal_input_data, resolved, lessons)

    assert len([issue for issue in report.issues if issue.rule_id == "S14"]) == 1
    assert not [issue for issue in report.issues if issue.rule_id == "S15"]


def test_result_validator_recomputes_s16_from_candidate_capacity(
    minimal_input_data: InputDataModel,
) -> None:
    dates = tuple(date(2026, 7, 27 + offset) for offset in range(4))
    input_data = replace(
        minimal_input_data,
        calendar_days=tuple(
            replace(
                minimal_input_data.calendar_days[0],
                target_date=target_date,
                enabled_period_ids=("P1",),
            )
            for target_date in dates
        ),
        campuses=(minimal_input_data.campuses[0],),
        rooms=minimal_input_data.rooms[:2],
        teachers=(minimal_input_data.teachers[0],),
        classes=(minimal_input_data.classes[0],),
        subjects=(minimal_input_data.subjects[0],),
        lesson_requirements=(minimal_input_data.lesson_requirements[0],),
        teacher_leaves=(),
    )
    resolved = RuleResolverService().execute(input_data)
    candidates = CandidateBuilderService().execute(input_data, resolved)
    balanced_lessons = (
        _lesson(target_date=dates[0]),
        _lesson(target_date=dates[2]),
    )
    clustered_lessons = (
        _lesson(target_date=dates[0]),
        _lesson(target_date=dates[1]),
    )

    balanced_report = ValidateResultService().execute(
        input_data,
        resolved,
        balanced_lessons,
        candidates,
    )
    clustered_report = ValidateResultService().execute(
        input_data,
        resolved,
        clustered_lessons,
        candidates,
    )
    balanced_s16 = [issue for issue in balanced_report.issues if issue.rule_id == "S16"]
    clustered_s16 = [issue for issue in clustered_report.issues if issue.rule_id == "S16"]

    assert not balanced_s16
    assert len(clustered_s16) == 1
    assert clustered_s16[0].severity == "WARNING"
    assert "score=" in clustered_s16[0].message


def test_result_validator_reports_s18_triangular_attendance_penalty(
    minimal_input_data: InputDataModel,
) -> None:
    dates = tuple(date(2026, 7, 27) + timedelta(days=offset) for offset in range(5))
    input_data = replace(
        minimal_input_data,
        calendar_days=tuple(
            replace(minimal_input_data.calendar_days[0], target_date=target_date)
            for target_date in dates
        ),
    )
    resolved = RuleResolverService().execute(input_data)
    class_rules = tuple(
        replace(
            resolved.class_date_rules[0],
            class_id="CL1",
            target_date=target_date,
            attendance_streak_limit=None,
            preferred_attendance_streak_limit=3,
        )
        for target_date in dates
    )
    resolved = replace(resolved, class_date_rules=class_rules)
    lessons = tuple(
        _lesson(
            requirement_id=f"Q{index}",
            target_date=target_date,
            teacher_id=f"T{index}",
        )
        for index, target_date in enumerate(dates, start=1)
    )

    report = ValidateResultService().execute(input_data, resolved, lessons)
    s18_issues = [issue for issue in report.issues if issue.rule_id == "S18"]

    assert len(s18_issues) == 1
    assert s18_issues[0].severity == "WARNING"
    assert "days=5" in s18_issues[0].message
    assert "penalty=3" in s18_issues[0].message


def test_result_validator_rejects_two_consecutive_empty_periods_between_lessons(
    minimal_input_data: InputDataModel,
) -> None:
    resolved = RuleResolverService().execute(minimal_input_data)
    lessons = (
        _lesson(requirement_id="Q1", period_id="P1", room_id="R1", class_id="CL1"),
        _lesson(requirement_id="Q2", period_id="P4", room_id="R1", class_id="CL1"),
    )

    report = ValidateResultService().execute(minimal_input_data, resolved, lessons)
    h16_issues = [issue for issue in report.issues if issue.rule_id == "H16"]

    assert any("2コマ以上" in issue.message for issue in h16_issues)
    assert all(issue.severity == "ERROR" for issue in h16_issues)


def test_result_validator_allows_multiple_single_period_internal_gaps(
    minimal_input_data: InputDataModel,
) -> None:
    resolved = RuleResolverService().execute(minimal_input_data)
    lessons = (
        _lesson(requirement_id="Q1", period_id="P1", room_id="R1", class_id="CL1"),
        _lesson(requirement_id="Q2", period_id="P3", room_id="R1", class_id="CL1"),
        _lesson(requirement_id="Q3", period_id="P5", room_id="R1", class_id="CL1"),
    )

    report = ValidateResultService().execute(minimal_input_data, resolved, lessons)

    assert not [issue for issue in report.issues if issue.rule_id == "H16"]
    assert [issue for issue in report.issues if issue.rule_id == "S11"]

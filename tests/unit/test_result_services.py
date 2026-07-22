from __future__ import annotations

from dataclasses import replace
from datetime import date

from school_timetable_solver.model.input_models import InputDataModel
from school_timetable_solver.model.result_models import ScheduledLessonModel
from school_timetable_solver.service.planning_services import RuleResolverService
from school_timetable_solver.service.result_services import ValidateResultService


def test_validate_result_service_accepts_valid_lessons(
    minimal_input_data: InputDataModel,
) -> None:
    lessons = (
        ScheduledLessonModel("Q1", date(2026, 7, 27), "P1", "T1", "R1", "C1", "CL1", "S1"),
        ScheduledLessonModel("Q2", date(2026, 7, 27), "P2", "T2", "R2", "C1", "CL2", "S2"),
    )
    resolved = RuleResolverService().execute(minimal_input_data)

    report = ValidateResultService().execute(minimal_input_data, resolved, lessons)

    assert report.issues == ()


def test_validate_result_service_reports_every_formal_hard_rule(
    minimal_input_data: InputDataModel,
) -> None:
    closed = replace(minimal_input_data.calendar_days[0], is_open=False)
    classes = tuple(
        replace(item, daily_hard_limit=1, attendance_streak_limit=1)
        for item in minimal_input_data.classes
    )
    teachers = tuple(
        replace(item, daily_hard_limit=1, consecutive_hard_limit=1)
        for item in minimal_input_data.teachers
    )
    rules = (replace(minimal_input_data.placement_rules[0], allowed_period_ids=("P3",)),)
    rooms = (replace(minimal_input_data.rooms[0], enabled=False), minimal_input_data.rooms[1])
    fixed = (replace(minimal_input_data.fixed_lessons[0], period_id="P3"),)
    invalid_input = replace(
        minimal_input_data,
        calendar_days=(closed, minimal_input_data.calendar_days[1]),
        teacher_availability=(),
        classes=classes,
        teachers=teachers,
        rooms=rooms,
        placement_rules=rules,
        fixed_lessons=fixed,
    )
    lessons = (
        ScheduledLessonModel("Q1", date(2026, 7, 27), "P1", "T1", "R1", "C1", "CL1", "S1"),
        ScheduledLessonModel("Q2", date(2026, 7, 27), "P1", "T1", "R1", "C2", "CL1", "S2"),
        ScheduledLessonModel("Q2", date(2026, 7, 27), "P2", "T1", "R1", "C1", "CL1", "S2"),
        ScheduledLessonModel("Q2", date(2026, 7, 28), "P1", "T1", "R1", "C1", "CL1", "S2"),
    )
    resolved = RuleResolverService().execute(invalid_input)

    report = ValidateResultService().execute(invalid_input, resolved, lessons)
    rule_ids = {issue.rule_id for issue in report.issues}

    assert rule_ids >= {f"H{index:02d}" for index in range(1, 15)}

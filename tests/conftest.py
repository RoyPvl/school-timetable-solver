from __future__ import annotations

from datetime import date, time

import pytest

from school_timetable_solver.model.input_models import (
    CalendarDayModel,
    InputDataModel,
    InputWorkbookSettingsModel,
    LessonRequirementModel,
    PlacementRuleModel,
)
from school_timetable_solver.model.master_models import (
    CampusModel,
    ClassModel,
    PeriodModel,
    RoomModel,
    SubjectModel,
    TeacherModel,
)


@pytest.fixture
def minimal_input_data() -> InputDataModel:
    output_dates = (date(2026, 7, 27), date(2026, 7, 28), date(2026, 7, 29))
    periods = tuple(
        PeriodModel(
            f"P{order}",
            chr(0x2460 + order - 1),
            order,
            time(8 + order, 0),
            time(9 + order, 0),
        )
        for order in range(1, 7)
    )
    return InputDataModel(
        settings=InputWorkbookSettingsModel("0.2", "テスト時間割", None),
        calendar_days=(
            CalendarDayModel(
                output_dates[0], True, tuple(item.period_id for item in periods), None
            ),
            CalendarDayModel(
                output_dates[1], True, tuple(item.period_id for item in periods), None
            ),
            CalendarDayModel(output_dates[2], True, (), "授業なし日"),
            CalendarDayModel(
                date(2026, 7, 30), False, tuple(item.period_id for item in periods), None
            ),
        ),
        periods=periods,
        campuses=(
            CampusModel("C1", "第一校舎", 1, True),
            CampusModel("C2", "第二校舎", 2, True),
        ),
        rooms=(
            RoomModel("R1", "101", "C1", 1, 0, True),
            RoomModel("R2", "102", "C1", 2, 100, True),
            RoomModel("R3", "201", "C2", 1, 100, True),
        ),
        teachers=(
            TeacherModel("T1", "教師一", "C1", True),
            TeacherModel("T2", "教師二", "C2", True),
        ),
        classes=(
            ClassModel("CL1", "小学A", "C1", "elementary", 6, "non_exam", None, True),
            ClassModel("CL2", "中学B", "C2", "junior_high", 3, "exam", "T2", True),
        ),
        subjects=(
            SubjectModel("S1", "算数", "regular", True),
            SubjectModel("S2", "英語", "regular", True),
        ),
        lesson_requirements=(
            LessonRequirementModel("Q1", "CL1", "S1", "T1", 2, 1, True),
            LessonRequirementModel("Q2", "CL2", "S2", "T2", 2, 1, True),
        ),
        teacher_leaves=(),
        placement_rules=(
            PlacementRuleModel(
                "R_CLASS_BASE",
                "クラス共通",
                True,
                "hard",
                "class",
                (),
                (),
                (),
                None,
                None,
                None,
                (),
                tuple(item.period_id for item in periods),
                3,
                None,
                3,
                10,
            ),
            PlacementRuleModel(
                "R_ELEMENTARY",
                "小学部",
                True,
                "hard",
                "class",
                ("division",),
                ("eq",),
                ("elementary",),
                None,
                None,
                None,
                (),
                ("P1", "P2", "P3"),
                None,
                None,
                None,
                20,
            ),
            PlacementRuleModel(
                "R_JH_OVERRIDE",
                "中学部指定日",
                True,
                "override",
                "class",
                ("division", "grade"),
                ("eq", "between"),
                ("junior_high", "1/3"),
                None,
                output_dates[1],
                output_dates[1],
                ("TUE",),
                ("P4", "P5", "P6"),
                2,
                None,
                2,
                30,
            ),
            PlacementRuleModel(
                "R_TEACHER_BASE",
                "教師共通",
                True,
                "hard",
                "teacher",
                (),
                (),
                (),
                None,
                None,
                None,
                (),
                (),
                4,
                True,
                None,
                10,
            ),
        ),
    )

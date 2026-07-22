from __future__ import annotations

from datetime import date, time

import pytest

from school_timetable_solver.model.input_models import (
    CalendarDayModel,
    FixedLessonModel,
    GenerationMode,
    GenerationSettingsModel,
    InputDataModel,
    LessonRequirementModel,
    PlacementRuleModel,
    TeacherAvailabilityModel,
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
    dates = (date(2026, 7, 27), date(2026, 7, 28))
    periods = (
        PeriodModel("P1", "1限", 1, time(9), time(10)),
        PeriodModel("P2", "2限", 2, time(10, 10), time(11, 10)),
        PeriodModel("P3", "3限", 3, time(11, 20), time(12, 20)),
    )
    return InputDataModel(
        settings=GenerationSettingsModel(
            2026, "test", dates[0], dates[-1], GenerationMode.STRICT, 5.0, 1
        ),
        calendar_days=tuple(
            CalendarDayModel(target, weekday, True, ("P1", "P2", "P3"), "normal", None)
            for target, weekday in zip(dates, ("月", "火"), strict=True)
        ),
        periods=periods,
        campuses=(CampusModel("C1", "校舎", 2, 2, "G1", True),),
        rooms=(
            RoomModel("R1", "教室1", "C1", True),
            RoomModel("R2", "教室2", "C1", True),
        ),
        teachers=(
            TeacherModel("T1", "教師1", "C1", ("S1", "S2"), 2, 2, True, 1, True),
            TeacherModel("T2", "教師2", "C1", ("S1", "S2"), 2, 2, True, 1, True),
        ),
        classes=(
            ClassModel("CL1", "クラス1", "C1", "junior_high", 1, "non_exam", (), 2, 2, 2, (), True),
            ClassModel("CL2", "クラス2", "C1", "junior_high", 2, "non_exam", (), 2, 2, 2, (), True),
        ),
        subjects=(SubjectModel("S1", "数学", True), SubjectModel("S2", "英語", True)),
        lesson_requirements=(
            LessonRequirementModel("Q1", "CL1", "S1", 1, "T1", (), ("R1",), True, 1, True),
            LessonRequirementModel("Q2", "CL2", "S2", 1, "T2", (), ("R2",), True, 1, True),
        ),
        teacher_availability=tuple(
            TeacherAvailabilityModel(teacher, target, period.period_id, "available")
            for teacher in ("T1", "T2")
            for target in dates
            for period in periods
        ),
        fixed_lessons=(FixedLessonModel("F1", "Q1", dates[0], "P1", "T1", "CL1", "S1", "R1"),),
        placement_rules=(
            PlacementRuleModel(
                "RULE1",
                "許可時限",
                True,
                "hard",
                "class",
                ("exam_category",),
                ("eq",),
                ("non_exam",),
                "C1",
                dates[0],
                dates[-1],
                (),
                ("P1", "P2", "P3"),
                (),
                2,
                None,
                None,
                2,
                100,
            ),
        ),
    )

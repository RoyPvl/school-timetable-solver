from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from typing import cast

from school_timetable_solver.model.input_models import (
    ClassPairOverlapRuleModel,
    InputDataModel,
)
from school_timetable_solver.model.result_models import (
    ScheduledLessonModel,
    ValidationIssueModel,
)
from school_timetable_solver.service.result_services import ValidateResultService

DAY = date(2026, 7, 27)


def _lesson(class_id: str, period_id: str, room_id: str = "R1") -> ScheduledLessonModel:
    return ScheduledLessonModel(
        requirement_id=f"Q_{class_id}",
        target_date=DAY,
        period_id=period_id,
        teacher_id=f"T_{class_id}",
        room_id=room_id,
        campus_id="C1",
        class_id=class_id,
        subject_id="S1",
    )


def _input_data(pairs: tuple[tuple[str, str], ...]) -> InputDataModel:
    return cast(
        InputDataModel,
        SimpleNamespace(
            periods=tuple(
                SimpleNamespace(period_id=f"P{index}", output_order=index) for index in range(1, 7)
            ),
            class_pair_overlap_rules=tuple(
                ClassPairOverlapRuleModel(f"PAIR_{index}", "pair", True, first, second)
                for index, (first, second) in enumerate(pairs, start=1)
            ),
        ),
    )


def test_result_h23_accepts_any_configured_first_predecessor() -> None:
    lessons = (
        _lesson("FA", "P2", "R2"),
        _lesson("FB", "P3", "R1"),
        _lesson("S", "P4", "R1"),
    )
    issues: list[ValidationIssueModel] = []
    ValidateResultService()._validate_class_successors(
        _input_data((("FA", "S"), ("FB", "S"))), lessons, issues
    )
    assert not any(issue.rule_id == "H23" for issue in issues)


def test_result_h23_rejects_second_only_day() -> None:
    issues: list[ValidationIssueModel] = []
    ValidateResultService()._validate_class_successors(
        _input_data((("F", "S"),)), (_lesson("S", "P3"),), issues
    )
    assert [issue.rule_id for issue in issues] == ["H23"]


def test_result_h23_rejects_wrong_room() -> None:
    issues: list[ValidationIssueModel] = []
    ValidateResultService()._validate_class_successors(
        _input_data((("F", "S"),)),
        (_lesson("F", "P2", "R1"), _lesson("S", "P3", "R2")),
        issues,
    )
    assert [issue.rule_id for issue in issues] == ["H23"]


def test_result_h23_uses_latest_first_and_earliest_second() -> None:
    issues: list[ValidationIssueModel] = []
    ValidateResultService()._validate_class_successors(
        _input_data((("F", "S"),)),
        (_lesson("F", "P1"), _lesson("S", "P2"), _lesson("F", "P3")),
        issues,
    )
    assert [issue.rule_id for issue in issues] == ["H23"]

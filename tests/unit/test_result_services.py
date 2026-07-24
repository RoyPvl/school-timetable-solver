from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest

from school_timetable_solver.model.input_models import InputDataModel
from school_timetable_solver.model.result_models import (
    ScheduledLessonDraftModel,
    ScheduledLessonModel,
)
from school_timetable_solver.service.planning_services import RuleResolverService
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
) -> ScheduledLessonDraftModel:
    return ScheduledLessonDraftModel(
        requirement_id=requirement_id,
        target_date=date(2026, 7, 27),
        period_id=period_id,
        teacher_id="T1",
        campus_id=campus_id,
        class_id=class_id,
        subject_id="S1",
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


def test_validate_result_reports_output_date_availability_allowed_period_and_campus(
    minimal_input_data: InputDataModel,
) -> None:
    resolved = RuleResolverService().execute(minimal_input_data)
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

    report = ValidateResultService().execute(minimal_input_data, resolved, lessons)
    rule_ids = {issue.rule_id for issue in report.issues}

    assert {"H04", "H05", "H06", "H11", "H13", "H14"} <= rule_ids


def test_assign_rooms_uses_class_id_and_room_output_order_stably(
    minimal_input_data: InputDataModel,
) -> None:
    assigned = AssignRoomsService().execute(
        minimal_input_data,
        (
            _draft("Q2", "CL2"),
            _draft("Q1", "CL1"),
        ),
    )

    assert [(item.class_id, item.room_id) for item in assigned] == [
        ("CL1", "R1"),
        ("CL2", "R2"),
    ]


def test_assign_rooms_rejects_campus_slot_capacity_overflow(
    minimal_input_data: InputDataModel,
) -> None:
    with pytest.raises(ValueError, match="有効教室数を超え"):
        AssignRoomsService().execute(
            minimal_input_data,
            (
                _draft("Q1", "CL1"),
                _draft("Q2", "CL2"),
                _draft("Q3", "CL3"),
            ),
        )


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

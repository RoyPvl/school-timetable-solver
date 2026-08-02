from __future__ import annotations

from collections import Counter
from dataclasses import replace
from pathlib import Path

from school_timetable_solver.adapter.excel_input_adapter import ExcelInputReaderAdapter
from school_timetable_solver.constraint.hard_constraints import DEFAULT_HARD_CONSTRAINTS
from school_timetable_solver.constraint.soft_constraints import DEFAULT_SOFT_CONSTRAINTS
from school_timetable_solver.model.input_models import (
    GenerationMode,
    InputDataModel,
    LessonCountPreferenceRuleSegmentModel,
    LessonCountRuleSegmentModel,
)
from school_timetable_solver.model.result_models import GenerationRequestModel
from school_timetable_solver.service.planning_services import (
    CandidateBuilderService,
    RuleResolverService,
)
from school_timetable_solver.service.result_services import (
    AssignRoomsService,
    BuildTimetableDocumentService,
    ValidateResultService,
)
from school_timetable_solver.service.solver_service import TimetableSolverService
from school_timetable_solver.validator.input_validators import (
    DEFAULT_INPUT_VALIDATORS,
    CapacityFeasibilityValidator,
)


def test_real_excel_flows_through_validation_solver_result_and_document() -> None:
    path = Path("projects/sample/input/時間割入力_サンプル.xlsx")
    read_result = ExcelInputReaderAdapter().read(path)
    assert read_result.input_data is not None
    input_data = read_result.input_data
    assert not [
        issue for validator in DEFAULT_INPUT_VALIDATORS for issue in validator.validate(input_data)
    ]
    resolved = RuleResolverService().execute(input_data)
    assert not resolved.issues
    candidates = CandidateBuilderService().execute(input_data, resolved)
    assert not CapacityFeasibilityValidator().validate(
        input_data,
        resolved,
        candidates,
    )
    request = GenerationRequestModel(
        path,
        Path("unused.xlsx"),
        None,
        GenerationMode.STRICT,
        10.0,
        1,
        1,
    )
    solver_result = TimetableSolverService(
        DEFAULT_HARD_CONSTRAINTS,
        DEFAULT_SOFT_CONSTRAINTS,
    ).execute(
        request,
        input_data,
        resolved,
        candidates,
    )
    lessons = AssignRoomsService().execute(input_data, solver_result.lessons)
    report = ValidateResultService().execute(
        input_data,
        resolved,
        lessons,
        candidates,
    )
    document = BuildTimetableDocumentService().execute(
        input_data,
        lessons,
    )

    assert solver_result.statistics.status in {"OPTIMAL", "FEASIBLE"}
    assert "H18" in solver_result.statistics.constraint_rule_ids
    assert len(lessons) == 4
    assert {issue.rule_id for issue in report.issues} == {"S12"}
    assert len(document.dates) == 3


def test_higher_priority_s14_prevents_s12_from_adding_another_double_day(
    minimal_input_data: InputDataModel,
    tmp_path: Path,
) -> None:
    input_data = replace(
        minimal_input_data,
        calendar_days=(
            minimal_input_data.calendar_days[0],
            minimal_input_data.calendar_days[1],
            replace(
                minimal_input_data.calendar_days[2],
                enabled_period_ids=tuple(period.period_id for period in minimal_input_data.periods),
                note=None,
            ),
        ),
        campuses=(minimal_input_data.campuses[0],),
        rooms=minimal_input_data.rooms[:2],
        teachers=(minimal_input_data.teachers[0],),
        classes=(minimal_input_data.classes[0],),
        subjects=(minimal_input_data.subjects[0],),
        lesson_requirements=(
            replace(
                minimal_input_data.lesson_requirements[0],
                required_periods=4,
                max_periods_per_day=3,
            ),
        ),
        teacher_leaves=(),
    )
    resolved = RuleResolverService().execute(input_data)
    candidates = CandidateBuilderService().execute(input_data, resolved)
    request = GenerationRequestModel(
        tmp_path / "input.xlsx",
        tmp_path / "output.xlsx",
        None,
        GenerationMode.STRICT,
        10.0,
        1,
        1,
    )

    solver_result = TimetableSolverService(
        DEFAULT_HARD_CONSTRAINTS,
        DEFAULT_SOFT_CONSTRAINTS,
    ).execute(
        request,
        input_data,
        resolved,
        candidates,
    )
    lesson_counts = Counter(
        (lesson.class_id, lesson.target_date) for lesson in solver_result.lessons
    )

    assert solver_result.statistics.status in {"OPTIMAL", "FEASIBLE"}
    assert sorted(lesson_counts.values()) == [1, 1, 2]
    assert solver_result.statistics.constraint_rule_ids[-9:] == (
        "S14",
        "S15",
        "S11",
        "S18",
        "S12",
        "S16",
        "S13",
        "S17",
        "S10",
    )


def test_h17_places_exact_count_in_resolved_scope(
    minimal_input_data: InputDataModel,
    tmp_path: Path,
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
                minimal_input_data.calendar_days[0].target_date,
                minimal_input_data.calendar_days[0].target_date,
                ("ALL",),
            ),
        ),
    )
    resolved = RuleResolverService().execute(input_data)
    candidates = CandidateBuilderService().execute(input_data, resolved)
    request = GenerationRequestModel(
        tmp_path / "input.xlsx",
        tmp_path / "output.xlsx",
        None,
        GenerationMode.STRICT,
        10.0,
        1,
        1,
    )

    solver_result = TimetableSolverService(
        DEFAULT_HARD_CONSTRAINTS,
        DEFAULT_SOFT_CONSTRAINTS,
    ).execute(request, input_data, resolved, candidates)
    scoped_lessons = [
        lesson
        for lesson in solver_result.lessons
        if lesson.requirement_id == "Q1"
        and lesson.target_date == minimal_input_data.calendar_days[0].target_date
    ]

    assert solver_result.statistics.status in {"OPTIMAL", "FEASIBLE"}
    assert len(scoped_lessons) == 1
    assert "H17" in solver_result.statistics.constraint_rule_ids


def test_s17_avoids_preferred_zero_scope_when_other_slots_are_available(
    minimal_input_data: InputDataModel,
    tmp_path: Path,
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
                minimal_input_data.calendar_days[0].target_date,
                minimal_input_data.calendar_days[1].target_date,
                ("P3",),
            ),
        ),
    )
    resolved = RuleResolverService().execute(input_data)
    candidates = CandidateBuilderService().execute(input_data, resolved)
    request = GenerationRequestModel(
        tmp_path / "input.xlsx",
        tmp_path / "output.xlsx",
        None,
        GenerationMode.STRICT,
        10.0,
        1,
        1,
    )

    solver_result = TimetableSolverService(
        DEFAULT_HARD_CONSTRAINTS,
        DEFAULT_SOFT_CONSTRAINTS,
    ).execute(request, input_data, resolved, candidates)

    assert solver_result.statistics.status in {"OPTIMAL", "FEASIBLE"}
    assert not [
        lesson
        for lesson in solver_result.lessons
        if lesson.requirement_id == "Q1" and lesson.period_id == "P3"
    ]
    assert "S17" in solver_result.statistics.constraint_rule_ids


def test_lower_priority_s13_mixes_subjects_without_worsening_s11_or_s12(
    minimal_input_data: InputDataModel,
    tmp_path: Path,
) -> None:
    input_data = replace(
        minimal_input_data,
        campuses=(minimal_input_data.campuses[0],),
        rooms=minimal_input_data.rooms[:2],
        classes=(minimal_input_data.classes[0],),
        lesson_requirements=(
            replace(
                minimal_input_data.lesson_requirements[0],
                required_periods=2,
                max_periods_per_day=2,
            ),
            replace(
                minimal_input_data.lesson_requirements[1],
                class_id="CL1",
                required_periods=2,
                max_periods_per_day=2,
            ),
        ),
    )
    resolved = RuleResolverService().execute(input_data)
    candidates = CandidateBuilderService().execute(input_data, resolved)
    request = GenerationRequestModel(
        tmp_path / "input.xlsx",
        tmp_path / "output.xlsx",
        None,
        GenerationMode.STRICT,
        10.0,
        1,
        1,
    )

    solver_result = TimetableSolverService(
        DEFAULT_HARD_CONSTRAINTS,
        DEFAULT_SOFT_CONSTRAINTS,
    ).execute(
        request,
        input_data,
        resolved,
        candidates,
    )
    lessons_by_date = {}
    for lesson in solver_result.lessons:
        lessons_by_date.setdefault(lesson.target_date, []).append(lesson)

    assert solver_result.statistics.status in {"OPTIMAL", "FEASIBLE"}
    assert sorted(len(lessons) for lessons in lessons_by_date.values()) == [2, 2]
    assert all(
        len({lesson.subject_id for lesson in lessons}) == 2 for lessons in lessons_by_date.values()
    )

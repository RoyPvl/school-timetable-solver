from __future__ import annotations

from datetime import date

from ortools.sat.python import cp_model

from school_timetable_solver.constraint.hard_constraints import (
    DAY_LEVEL_MASTER_CONSTRAINTS,
    DEFAULT_HARD_CONSTRAINTS,
    ClassRoomContinuityConstraint,
    ClassSuccessorConstraint,
    ClassSuccessorDayConstraint,
)
from school_timetable_solver.constraint.soft_constraints import (
    ClassSingleLessonDayPreferenceConstraint,
    RoomChangeGapPreferenceConstraint,
)
from school_timetable_solver.constraint.solver_context import SolverContext
from school_timetable_solver.model.input_models import ClassPairOverlapRuleModel
from school_timetable_solver.model.solver_models import CandidateSlotModel

DAY = date(2026, 7, 27)


def _candidate(class_id: str, period_id: str) -> CandidateSlotModel:
    candidate_id = f"Q_{class_id}__{period_id}"
    return CandidateSlotModel(
        candidate_id,
        f"Q_{class_id}",
        DAY,
        period_id,
        f"T_{class_id}",
        "C1",
        class_id,
        "S1",
    )


def _context(candidates: tuple[CandidateSlotModel, ...]) -> SolverContext:
    model = cp_model.CpModel()
    variables = {
        candidate.candidate_id: model.new_bool_var(candidate.candidate_id)
        for candidate in candidates
    }
    return SolverContext(
        model=model,
        candidates=candidates,
        assignment_variables=variables,
        required_counts={candidate.requirement_id: 6 for candidate in candidates},
        room_capacities={"C1": 3},
        class_daily_limits={(candidate.class_id, DAY): 6 for candidate in candidates},
        requirement_daily_limits={candidate.requirement_id: None for candidate in candidates},
        teacher_daily_limits={(candidate.teacher_id, DAY): 6 for candidate in candidates},
        teacher_first_last_period_forbidden={
            (candidate.teacher_id, DAY): False for candidate in candidates
        },
        class_attendance_limits={(candidate.class_id, DAY): None for candidate in candidates},
        period_orders={f"P{index}": index for index in range(1, 7)},
        calendar_dates=(DAY,),
    )


def _solve(context: SolverContext, selected: set[tuple[str, str]]) -> str:
    for candidate in context.candidates:
        context.model.add(
            context.assignment_variables[candidate.candidate_id]
            == int((candidate.class_id, candidate.period_id) in selected)
        )
    solver = cp_model.CpSolver()
    return solver.status_name(solver.solve(context.model))


def _apply_period_h23(
    candidates: tuple[CandidateSlotModel, ...],
    pairs: tuple[tuple[str, str], ...],
) -> SolverContext:
    context = _context(candidates)
    context.class_pair_overlap_rules = tuple(
        ClassPairOverlapRuleModel(f"PAIR_{index}", "pair", True, first, second)
        for index, (first, second) in enumerate(pairs, start=1)
    )
    ClassRoomContinuityConstraint().apply(context)
    ClassSuccessorConstraint().apply(context)
    return context


def test_h23_accepts_second_immediately_after_latest_first() -> None:
    candidates = tuple(
        _candidate(class_id, period_id)
        for class_id, period_id in (
            ("F", "P1"),
            ("F", "P3"),
            ("S", "P4"),
            ("S", "P5"),
        )
    )
    context = _apply_period_h23(candidates, (("F", "S"),))

    status = _solve(context, {("F", "P1"), ("F", "P3"), ("S", "P4"), ("S", "P5")})

    assert status in {"OPTIMAL", "FEASIBLE"}


def test_h23_rejects_second_when_first_has_a_later_lesson() -> None:
    candidates = tuple(
        _candidate(class_id, period_id)
        for class_id, period_id in (
            ("F", "P1"),
            ("S", "P2"),
            ("F", "P3"),
        )
    )
    context = _apply_period_h23(candidates, (("F", "S"),))

    status = _solve(context, {("F", "P1"), ("S", "P2"), ("F", "P3")})

    assert status == "INFEASIBLE"


def test_h23_rejects_second_only_day() -> None:
    candidates = (_candidate("F", "P2"), _candidate("S", "P3"))
    context = _apply_period_h23(candidates, (("F", "S"),))

    status = _solve(context, {("S", "P3")})

    assert status == "INFEASIBLE"


def test_h23_aggregates_multiple_first_classes_as_or() -> None:
    candidates = tuple(
        _candidate(class_id, period_id)
        for class_id, period_id in (
            ("FA", "P2"),
            ("FB", "P3"),
            ("S", "P4"),
        )
    )
    context = _apply_period_h23(candidates, (("FA", "S"), ("FB", "S")))

    status = _solve(context, {("FA", "P2"), ("FB", "P3"), ("S", "P4")})

    assert status in {"OPTIMAL", "FEASIBLE"}


def test_h23_requires_same_room_for_selected_first_and_second() -> None:
    candidates = (_candidate("F", "P2"), _candidate("S", "P3"))
    context = _apply_period_h23(candidates, (("F", "S"),))
    context.model.add(
        context.class_room_variables[("C1", DAY, "F")]
        != context.class_room_variables[("C1", DAY, "S")]
    )

    status = _solve(context, {("F", "P2"), ("S", "P3")})

    assert status == "INFEASIBLE"


def test_h23_day_master_rejects_second_without_any_first_day() -> None:
    candidates = (_candidate("F", "P2"), _candidate("S", "P3"))
    context = _context(candidates)
    context.class_pair_overlap_rules = (
        ClassPairOverlapRuleModel("PAIR", "pair", True, "F", "S"),
    )
    ClassSuccessorDayConstraint().apply(context)

    status = _solve(context, {("S", "P3")})

    assert status == "INFEASIBLE"


def test_s10_excludes_configured_first_to_second_transition() -> None:
    candidates = (_candidate("F", "P2"), _candidate("S", "P3"))
    context = _context(candidates)
    context.class_pair_overlap_rules = (
        ClassPairOverlapRuleModel("PAIR", "pair", True, "F", "S"),
    )
    ClassRoomContinuityConstraint().apply(context)

    RoomChangeGapPreferenceConstraint().apply(context)

    assert context.penalty_terms_by_priority.get(9, []) == []


def test_s12_excludes_configured_second_class() -> None:
    candidates = (_candidate("F", "P2"), _candidate("S", "P3"))
    context = _context(candidates)
    context.class_pair_overlap_rules = (
        ClassPairOverlapRuleModel("PAIR", "pair", True, "F", "S"),
    )
    ClassRoomContinuityConstraint().apply(context)

    ClassSingleLessonDayPreferenceConstraint().apply(context)

    assert len(context.penalty_terms_by_priority[15]) == 1


def test_h23_is_registered_in_full_and_day_level_models() -> None:
    assert any(isinstance(item, ClassSuccessorConstraint) for item in DEFAULT_HARD_CONSTRAINTS)
    assert any(isinstance(item, ClassSuccessorDayConstraint) for item in DAY_LEVEL_MASTER_CONSTRAINTS)

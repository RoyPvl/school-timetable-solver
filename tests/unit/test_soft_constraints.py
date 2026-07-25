from __future__ import annotations

from datetime import date

from ortools.sat.python import cp_model

from school_timetable_solver.constraint.hard_constraints import (
    ClassRoomContinuityConstraint,
)
from school_timetable_solver.constraint.soft_constraints import (
    ClassDailyContiguityPreferenceConstraint,
    RoomChangeGapPreferenceConstraint,
)
from school_timetable_solver.constraint.solver_context import SolverContext
from school_timetable_solver.model.solver_models import CandidateSlotModel

TARGET_DATE = date(2026, 7, 27)


def _context(room_capacity: int) -> SolverContext:
    candidates = (
        CandidateSlotModel("Q1__P1", "Q1", TARGET_DATE, "P1", "T1", "C1", "CL1", "S1"),
        CandidateSlotModel("Q2__P2", "Q2", TARGET_DATE, "P2", "T2", "C1", "CL2", "S1"),
    )
    model = cp_model.CpModel()
    variables = {
        candidate.candidate_id: model.new_bool_var(candidate.candidate_id)
        for candidate in candidates
    }
    return SolverContext(
        model=model,
        candidates=candidates,
        assignment_variables=variables,
        required_counts={"Q1": 1, "Q2": 1},
        room_capacities={"C1": room_capacity},
        class_daily_limits={("CL1", TARGET_DATE): 6, ("CL2", TARGET_DATE): 6},
        requirement_daily_limits={"Q1": None, "Q2": None},
        teacher_daily_limits={("T1", TARGET_DATE): 6, ("T2", TARGET_DATE): 6},
        teacher_consecutive_limits={("T1", TARGET_DATE): 6, ("T2", TARGET_DATE): 6},
        class_attendance_limits={("CL1", TARGET_DATE): 6, ("CL2", TARGET_DATE): 6},
        period_orders={f"P{index}": index for index in range(1, 7)},
        calendar_dates=(TARGET_DATE,),
    )


def _solve(room_capacity: int) -> tuple[cp_model.CpSolver, SolverContext]:
    context = _context(room_capacity)
    ClassRoomContinuityConstraint().apply(context)
    constraint = RoomChangeGapPreferenceConstraint()
    constraint.apply(context)
    for variable in context.assignment_variables.values():
        context.model.add(variable == 1)
    context.model.minimize(sum(context.penalty_terms_by_priority[constraint.priority]))
    solver = cp_model.CpSolver()
    status = solver.status_name(solver.solve(context.model))
    assert status in {"OPTIMAL", "FEASIBLE"}
    return solver, context


def test_s10_uses_different_rooms_to_avoid_adjacent_class_change_when_possible() -> None:
    solver, context = _solve(room_capacity=2)

    assert solver.objective_value == 0
    assert solver.value(context.class_room_variables[("C1", TARGET_DATE, "CL1")]) != (
        solver.value(context.class_room_variables[("C1", TARGET_DATE, "CL2")])
    )


def test_s10_allows_adjacent_class_change_when_only_one_room_exists() -> None:
    solver, _ = _solve(room_capacity=1)

    assert solver.objective_value == 1


def _solve_contiguity(
    selected_period_ids: set[str],
) -> tuple[cp_model.CpSolver, SolverContext]:
    candidates = tuple(
        CandidateSlotModel(
            f"Q{period_index}__P{period_index}",
            f"Q{period_index}",
            TARGET_DATE,
            f"P{period_index}",
            f"T{period_index}",
            "C1",
            "CL1",
            "S1",
        )
        for period_index in range(1, 7)
    )
    model = cp_model.CpModel()
    variables = {
        candidate.candidate_id: model.new_bool_var(candidate.candidate_id)
        for candidate in candidates
    }
    context = SolverContext(
        model=model,
        candidates=candidates,
        assignment_variables=variables,
        required_counts={candidate.requirement_id: 1 for candidate in candidates},
        room_capacities={"C1": 1},
        class_daily_limits={("CL1", TARGET_DATE): 6},
        requirement_daily_limits={candidate.requirement_id: None for candidate in candidates},
        teacher_daily_limits={(candidate.teacher_id, TARGET_DATE): 6 for candidate in candidates},
        teacher_consecutive_limits={
            (candidate.teacher_id, TARGET_DATE): 6 for candidate in candidates
        },
        class_attendance_limits={("CL1", TARGET_DATE): 6},
        period_orders={f"P{index}": index for index in range(1, 7)},
        calendar_dates=(TARGET_DATE,),
    )
    ClassRoomContinuityConstraint().apply(context)
    constraint = ClassDailyContiguityPreferenceConstraint()
    constraint.apply(context)
    for candidate in candidates:
        context.model.add(
            variables[candidate.candidate_id] == (candidate.period_id in selected_period_ids)
        )
    context.model.minimize(sum(context.penalty_terms_by_priority[constraint.priority]))
    solver = cp_model.CpSolver()
    status = solver.status_name(solver.solve(context.model))
    assert status == "OPTIMAL"
    return solver, context


def test_s11_has_no_penalty_for_one_contiguous_class_block() -> None:
    solver, _ = _solve_contiguity({"P2", "P3", "P4"})

    assert solver.objective_value == 0


def test_s11_counts_one_split_class_day_even_with_multiple_empty_periods() -> None:
    solver, _ = _solve_contiguity({"P1", "P4"})

    assert solver.objective_value == 1


def test_s11_has_higher_priority_than_s10() -> None:
    assert (
        ClassDailyContiguityPreferenceConstraint.priority
        > RoomChangeGapPreferenceConstraint.priority
    )

from __future__ import annotations

from datetime import date, timedelta

from ortools.sat.python import cp_model

from school_timetable_solver.constraint.soft_constraints import (
    TeacherCampusTransferPreferenceConstraint,
)
from school_timetable_solver.constraint.solver_context import SolverContext
from school_timetable_solver.model.solver_models import CandidateSlotModel

TARGET_DATE = date(2026, 7, 27)


def _context(
    candidates: tuple[CandidateSlotModel, ...],
    calendar_dates: tuple[date, ...],
) -> SolverContext:
    model = cp_model.CpModel()
    variables = {
        candidate.candidate_id: model.new_bool_var(candidate.candidate_id)
        for candidate in candidates
    }
    return SolverContext(
        model=model,
        candidates=candidates,
        assignment_variables=variables,
        required_counts={candidate.requirement_id: 1 for candidate in candidates},
        room_capacities={candidate.campus_id: 2 for candidate in candidates},
        class_daily_limits={
            (candidate.class_id, candidate.target_date): 6 for candidate in candidates
        },
        requirement_daily_limits={candidate.requirement_id: None for candidate in candidates},
        teacher_daily_limits={
            (candidate.teacher_id, candidate.target_date): 6 for candidate in candidates
        },
        teacher_first_last_period_forbidden={
            (candidate.teacher_id, candidate.target_date): False for candidate in candidates
        },
        class_attendance_limits={
            (candidate.class_id, candidate.target_date): None for candidate in candidates
        },
        period_orders={f"P{period_index}": period_index for period_index in range(1, 7)},
        calendar_dates=calendar_dates,
    )


def _solve_fixed(candidates: tuple[CandidateSlotModel, ...]) -> cp_model.CpSolver:
    calendar_dates = tuple(sorted({candidate.target_date for candidate in candidates}))
    context = _context(candidates, calendar_dates)
    constraint = TeacherCampusTransferPreferenceConstraint()
    constraint.apply(context)
    for variable in context.assignment_variables.values():
        context.model.add(variable == 1)
    context.model.minimize(sum(context.penalty_terms_by_priority.get(constraint.priority, ())))

    solver = cp_model.CpSolver()
    assert solver.status_name(solver.solve(context.model)) == "OPTIMAL"
    return solver


def test_s24_has_no_penalty_when_teacher_stays_on_one_campus() -> None:
    candidates = (
        CandidateSlotModel("Q1__P1", "Q1", TARGET_DATE, "P1", "T1", "C1", "CL1", "S1"),
        CandidateSlotModel("Q2__P2", "Q2", TARGET_DATE, "P2", "T1", "C1", "CL2", "S2"),
    )

    solver = _solve_fixed(candidates)

    assert solver.objective_value == 0


def test_s24_penalizes_one_teacher_day_using_two_campuses() -> None:
    candidates = (
        CandidateSlotModel("Q1__P1", "Q1", TARGET_DATE, "P1", "T1", "C1", "CL1", "S1"),
        CandidateSlotModel("Q2__P4", "Q2", TARGET_DATE, "P4", "T1", "C2", "CL2", "S2"),
    )

    solver = _solve_fixed(candidates)

    assert solver.objective_value == 1


def test_s24_does_not_penalize_different_campuses_on_different_days() -> None:
    next_date = TARGET_DATE + timedelta(days=1)
    candidates = (
        CandidateSlotModel("Q1__P1", "Q1", TARGET_DATE, "P1", "T1", "C1", "CL1", "S1"),
        CandidateSlotModel("Q2__P1", "Q2", next_date, "P1", "T1", "C2", "CL2", "S2"),
    )

    solver = _solve_fixed(candidates)

    assert solver.objective_value == 0


def test_s24_prefers_same_campus_when_flexible_lesson_has_two_campus_options() -> None:
    candidates = (
        CandidateSlotModel(
            "FIXED_C1",
            "Q_FIXED",
            TARGET_DATE,
            "P1",
            "T1",
            "C1",
            "CL1",
            "S1",
        ),
        CandidateSlotModel(
            "FLEX_C1",
            "Q_FLEX",
            TARGET_DATE,
            "P4",
            "T1",
            "C1",
            "CL2",
            "S2",
        ),
        CandidateSlotModel(
            "FLEX_C2",
            "Q_FLEX",
            TARGET_DATE,
            "P4",
            "T1",
            "C2",
            "CL2",
            "S2",
        ),
    )
    context = _context(candidates, (TARGET_DATE,))
    constraint = TeacherCampusTransferPreferenceConstraint()
    constraint.apply(context)
    context.model.add(context.assignment_variables["FIXED_C1"] == 1)
    context.model.add(
        context.assignment_variables["FLEX_C1"] + context.assignment_variables["FLEX_C2"] == 1
    )
    context.model.minimize(sum(context.penalty_terms_by_priority[constraint.priority]))

    solver = cp_model.CpSolver()
    assert solver.status_name(solver.solve(context.model)) == "OPTIMAL"
    assert solver.objective_value == 0
    assert solver.value(context.assignment_variables["FLEX_C1"]) == 1
    assert solver.value(context.assignment_variables["FLEX_C2"]) == 0

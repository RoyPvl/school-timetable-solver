from __future__ import annotations

from datetime import date

import pytest
from ortools.sat.python import cp_model

from school_timetable_solver.constraint.hard_constraints import (
    ClassOverlapConstraint,
    RequiredLessonCountConstraint,
    TeacherSingleCampusPerDayConstraint,
)
from school_timetable_solver.constraint.solver_context import SolverContext
from school_timetable_solver.model.solver_models import CandidateSlotModel

DAY_ONE = date(2026, 7, 27)
DAY_TWO = date(2026, 7, 28)


def _candidate(
    candidate_id: str,
    teacher_id: str,
    target_date: date,
    campus_id: str,
    period_id: str,
    class_id: str = "CL1",
) -> CandidateSlotModel:
    return CandidateSlotModel(
        candidate_id,
        candidate_id.split("__")[0],
        target_date,
        period_id,
        teacher_id,
        f"R_{campus_id}_{period_id}",
        campus_id,
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
        required_counts={candidate.requirement_id: 1 for candidate in candidates},
        class_daily_limits={
            (candidate.class_id, candidate.target_date): 6 for candidate in candidates
        },
        requirement_daily_limits={candidate.requirement_id: None for candidate in candidates},
        teacher_daily_limits={
            (candidate.teacher_id, candidate.target_date): 6 for candidate in candidates
        },
        teacher_consecutive_limits={
            (candidate.teacher_id, candidate.target_date): 6 for candidate in candidates
        },
        class_attendance_limits={
            (candidate.class_id, candidate.target_date): 6 for candidate in candidates
        },
        period_orders={f"P{index}": index for index in range(1, 7)},
        calendar_dates=(DAY_ONE, DAY_TWO),
    )


def _force_all_and_solve(context: SolverContext) -> str:
    for variable in context.assignment_variables.values():
        context.model.add(variable == 1)
    solver = cp_model.CpSolver()
    return solver.status_name(solver.solve(context.model))


@pytest.mark.parametrize(
    ("candidates", "expected_feasible"),
    (
        (
            (
                _candidate("Q1__1", "T1", DAY_ONE, "C1", "P1"),
                _candidate("Q2__1", "T1", DAY_ONE, "C1", "P2", "CL2"),
            ),
            True,
        ),
        (
            (
                _candidate("Q1__1", "T1", DAY_ONE, "C1", "P1"),
                _candidate("Q2__1", "T1", DAY_ONE, "C2", "P2", "CL2"),
            ),
            False,
        ),
        (
            (
                _candidate("Q1__1", "T1", DAY_ONE, "C1", "P1"),
                _candidate("Q2__1", "T1", DAY_TWO, "C2", "P2", "CL2"),
            ),
            True,
        ),
        (
            (
                _candidate("Q1__1", "T1", DAY_ONE, "C1", "P1"),
                _candidate("Q2__1", "T2", DAY_ONE, "C2", "P2", "CL2"),
            ),
            True,
        ),
    ),
)
def test_h11_teacher_single_campus_per_day(
    candidates: tuple[CandidateSlotModel, ...],
    expected_feasible: bool,
) -> None:
    context = _context(candidates)
    TeacherSingleCampusPerDayConstraint().apply(context)

    status = _force_all_and_solve(context)

    assert (status in {"OPTIMAL", "FEASIBLE"}) is expected_feasible


def test_required_count_constraint_rejects_missing_assignment() -> None:
    candidates = (_candidate("Q1__1", "T1", DAY_ONE, "C1", "P1"),)
    context = _context(candidates)
    context.required_counts["Q1"] = 1
    RequiredLessonCountConstraint().apply(context)
    context.model.add(context.assignment_variables["Q1__1"] == 0)

    assert _force_all_and_solve(context) == "INFEASIBLE"


def test_class_overlap_constraint_rejects_same_class_slot() -> None:
    candidates = (
        _candidate("Q1__1", "T1", DAY_ONE, "C1", "P1"),
        _candidate("Q2__1", "T2", DAY_ONE, "C1", "P1"),
    )
    context = _context(candidates)
    ClassOverlapConstraint().apply(context)

    assert _force_all_and_solve(context) == "INFEASIBLE"

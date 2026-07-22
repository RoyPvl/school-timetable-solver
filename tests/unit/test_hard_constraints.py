from __future__ import annotations

from datetime import date, timedelta

import pytest
from ortools.sat.python import cp_model

from school_timetable_solver.constraint.hard_constraints import (
    CampusTransferConstraint,
    ClassDailyLimitConstraint,
    ClassOverlapConstraint,
    ConsecutiveAttendanceConstraint,
    FixedLessonConstraint,
    RequiredLessonCountConstraint,
    RoomOverlapConstraint,
    TeacherConsecutivePeriodConstraint,
    TeacherDailyLimitConstraint,
    TeacherOverlapConstraint,
)
from school_timetable_solver.constraint.solver_context import SolverContext
from school_timetable_solver.model.input_models import FixedLessonModel
from school_timetable_solver.model.solver_models import CandidateSlotModel

DAY = date(2026, 7, 27)


def _candidate(
    candidate_id: str,
    *,
    requirement_id: str = "Q1",
    target_date: date = DAY,
    period_id: str = "P1",
    teacher_id: str = "T1",
    room_id: str = "R1",
    campus_id: str = "C1",
    class_id: str = "CL1",
) -> CandidateSlotModel:
    return CandidateSlotModel(
        candidate_id,
        requirement_id,
        target_date,
        period_id,
        teacher_id,
        room_id,
        campus_id,
        class_id,
        "S1",
    )


def _context(
    candidates: tuple[CandidateSlotModel, ...],
    *,
    dates: tuple[date, ...] = (DAY,),
    fixed_lessons: tuple[FixedLessonModel, ...] = (),
) -> SolverContext:
    model = cp_model.CpModel()
    variables = {
        candidate.candidate_id: model.new_bool_var(candidate.candidate_id)
        for candidate in candidates
    }
    class_date_keys = {(item.class_id, target) for item in candidates for target in dates}
    teacher_date_keys = {(item.teacher_id, target) for item in candidates for target in dates}
    return SolverContext(
        model=model,
        candidates=candidates,
        assignment_variables=variables,
        required_counts={item.requirement_id: 1 for item in candidates},
        fixed_lessons=fixed_lessons,
        class_daily_limits={key: None for key in class_date_keys},
        requirement_daily_limits={item.requirement_id: None for item in candidates},
        teacher_daily_limits={key: None for key in teacher_date_keys},
        teacher_consecutive_limits={key: None for key in teacher_date_keys},
        class_attendance_limits={key: None for key in class_date_keys},
        teacher_transfer_gaps={item.teacher_id: 1 for item in candidates},
        teacher_can_transfer={item.teacher_id: True for item in candidates},
        period_orders={"P1": 1, "P2": 2, "P3": 3},
        calendar_dates=dates,
    )


def _solve(context: SolverContext) -> cp_model.CpSolverStatus:
    return cp_model.CpSolver().solve(context.model)


def _force_all(context: SolverContext) -> None:
    for variable in context.assignment_variables.values():
        context.model.add(variable == 1)


def test_required_lesson_count_constraint_accepts_exact_count_and_rejects_shortage() -> None:
    candidate = _candidate("A")
    valid = _context((candidate,))
    RequiredLessonCountConstraint().apply(valid)
    assert _solve(valid) == cp_model.OPTIMAL

    invalid = _context((candidate,))
    invalid.required_counts["Q1"] = 2
    RequiredLessonCountConstraint().apply(invalid)
    assert _solve(invalid) == cp_model.INFEASIBLE


def test_fixed_lesson_constraint_accepts_match_and_rejects_missing_candidate() -> None:
    candidate = _candidate("A")
    fixed = FixedLessonModel("F1", "Q1", DAY, "P1", "T1", "CL1", "S1", "R1")
    valid = _context((candidate,), fixed_lessons=(fixed,))
    FixedLessonConstraint().apply(valid)
    assert _solve(valid) == cp_model.OPTIMAL

    missing = FixedLessonModel("F2", "Q1", DAY, "P2", "T1", "CL1", "S1", "R1")
    invalid = _context((candidate,), fixed_lessons=(missing,))
    FixedLessonConstraint().apply(invalid)
    assert _solve(invalid) == cp_model.INFEASIBLE


@pytest.mark.parametrize(
    ("constraint", "second"),
    (
        (TeacherOverlapConstraint(), _candidate("B", requirement_id="Q2", class_id="CL2")),
        (ClassOverlapConstraint(), _candidate("B", requirement_id="Q2", teacher_id="T2")),
        (
            RoomOverlapConstraint(),
            _candidate("B", requirement_id="Q2", class_id="CL2", teacher_id="T2"),
        ),
    ),
)
def test_overlap_constraints_reject_same_slot_and_allow_different_period(
    constraint: TeacherOverlapConstraint | ClassOverlapConstraint | RoomOverlapConstraint,
    second: CandidateSlotModel,
) -> None:
    invalid = _context((_candidate("A"), second))
    _force_all(invalid)
    constraint.apply(invalid)
    assert _solve(invalid) == cp_model.INFEASIBLE

    valid_second = CandidateSlotModel(
        second.candidate_id,
        second.requirement_id,
        second.target_date,
        "P2",
        second.teacher_id,
        second.room_id,
        second.campus_id,
        second.class_id,
        second.subject_id,
    )
    valid = _context((_candidate("A"), valid_second))
    _force_all(valid)
    constraint.apply(valid)
    assert _solve(valid) == cp_model.OPTIMAL


def test_class_daily_limit_constraint_enforces_limit_boundary() -> None:
    candidates = (
        _candidate("A"),
        _candidate("B", requirement_id="Q2", period_id="P2", teacher_id="T2", room_id="R2"),
    )
    valid = _context(candidates)
    valid.class_daily_limits[("CL1", DAY)] = 2
    _force_all(valid)
    ClassDailyLimitConstraint().apply(valid)
    assert _solve(valid) == cp_model.OPTIMAL

    invalid = _context(candidates)
    invalid.class_daily_limits[("CL1", DAY)] = 1
    _force_all(invalid)
    ClassDailyLimitConstraint().apply(invalid)
    assert _solve(invalid) == cp_model.INFEASIBLE


def test_teacher_daily_limit_constraint_enforces_limit_boundary() -> None:
    candidates = (
        _candidate("A"),
        _candidate("B", requirement_id="Q2", period_id="P2", class_id="CL2", room_id="R2"),
    )
    valid = _context(candidates)
    valid.teacher_daily_limits[("T1", DAY)] = 2
    _force_all(valid)
    TeacherDailyLimitConstraint().apply(valid)
    assert _solve(valid) == cp_model.OPTIMAL

    invalid = _context(candidates)
    invalid.teacher_daily_limits[("T1", DAY)] = 1
    _force_all(invalid)
    TeacherDailyLimitConstraint().apply(invalid)
    assert _solve(invalid) == cp_model.INFEASIBLE


def test_teacher_consecutive_constraint_rejects_three_and_allows_gap() -> None:
    consecutive = tuple(
        _candidate(
            period,
            requirement_id=f"Q{index}",
            period_id=period,
            class_id=f"CL{index}",
            room_id=f"R{index}",
        )
        for index, period in enumerate(("P1", "P2", "P3"), start=1)
    )
    invalid = _context(consecutive)
    invalid.teacher_consecutive_limits[("T1", DAY)] = 2
    _force_all(invalid)
    TeacherConsecutivePeriodConstraint().apply(invalid)
    assert _solve(invalid) == cp_model.INFEASIBLE

    valid = _context((consecutive[0], consecutive[2]))
    valid.teacher_consecutive_limits[("T1", DAY)] = 1
    _force_all(valid)
    TeacherConsecutivePeriodConstraint().apply(valid)
    assert _solve(valid) == cp_model.OPTIMAL


def test_attendance_streak_constraint_rejects_consecutive_days_and_allows_gap() -> None:
    dates = (DAY, DAY + timedelta(days=1), DAY + timedelta(days=2))
    candidates = tuple(
        _candidate(
            f"A{index}",
            requirement_id=f"Q{index}",
            target_date=target,
            period_id="P1",
        )
        for index, target in enumerate(dates, start=1)
    )
    invalid = _context(candidates, dates=dates)
    for target in dates:
        invalid.class_attendance_limits[("CL1", target)] = 2
    _force_all(invalid)
    ConsecutiveAttendanceConstraint().apply(invalid)
    assert _solve(invalid) == cp_model.INFEASIBLE

    valid = _context((candidates[0], candidates[2]), dates=dates)
    for target in dates:
        valid.class_attendance_limits[("CL1", target)] = 1
    _force_all(valid)
    ConsecutiveAttendanceConstraint().apply(valid)
    assert _solve(valid) == cp_model.OPTIMAL


def test_campus_transfer_constraint_enforces_required_empty_period_boundary() -> None:
    first = _candidate("A", period_id="P1")
    adjacent = _candidate(
        "B", requirement_id="Q2", period_id="P2", campus_id="C2", class_id="CL2", room_id="R2"
    )
    invalid = _context((first, adjacent))
    _force_all(invalid)
    CampusTransferConstraint().apply(invalid)
    assert _solve(invalid) == cp_model.INFEASIBLE

    separated = _candidate(
        "C", requirement_id="Q2", period_id="P3", campus_id="C2", class_id="CL2", room_id="R2"
    )
    valid = _context((first, separated))
    _force_all(valid)
    CampusTransferConstraint().apply(valid)
    assert _solve(valid) == cp_model.OPTIMAL

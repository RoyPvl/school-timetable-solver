from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from ortools.sat.python import cp_model

from school_timetable_solver.model.input_models import FixedLessonModel
from school_timetable_solver.model.solver_models import CandidateSlotModel


@dataclass(slots=True)
class SolverContext:
    """Mutable OR-Tools state scoped to one solve operation."""

    model: cp_model.CpModel
    candidates: tuple[CandidateSlotModel, ...]
    assignment_variables: dict[str, cp_model.IntVar]
    required_counts: dict[str, int]
    fixed_lessons: tuple[FixedLessonModel, ...]
    class_daily_limits: dict[tuple[str, date], int | None]
    requirement_daily_limits: dict[str, int | None]
    teacher_daily_limits: dict[tuple[str, date], int | None]
    teacher_consecutive_limits: dict[tuple[str, date], int | None]
    class_attendance_limits: dict[tuple[str, date], int | None]
    teacher_transfer_gaps: dict[str, int]
    teacher_can_transfer: dict[str, bool]
    period_orders: dict[str, int]
    calendar_dates: tuple[date, ...]
    applied_rule_ids: list[str] = field(default_factory=list)
    class_day_variables: dict[tuple[str, date], cp_model.IntVar] = field(default_factory=dict)

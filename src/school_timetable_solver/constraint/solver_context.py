from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from ortools.sat.python import cp_model

from school_timetable_solver.model.solver_models import CandidateSlotModel


@dataclass(slots=True)
class SolverContext:
    """Mutable OR-Tools state scoped to one strict solve."""

    model: cp_model.CpModel
    candidates: tuple[CandidateSlotModel, ...]
    assignment_variables: dict[str, cp_model.IntVar]
    required_counts: dict[str, int]
    room_capacities: dict[str, int]
    class_daily_limits: dict[tuple[str, date], int | None]
    requirement_daily_limits: dict[str, int | None]
    teacher_daily_limits: dict[tuple[str, date], int | None]
    teacher_consecutive_limits: dict[tuple[str, date], int | None]
    class_attendance_limits: dict[tuple[str, date], int | None]
    period_orders: dict[str, int]
    calendar_dates: tuple[date, ...]
    applied_rule_ids: list[str] = field(default_factory=list)
    class_day_variables: dict[tuple[str, date], cp_model.IntVar] = field(default_factory=dict)
    class_room_variables: dict[tuple[str, date, str], cp_model.IntVar] = field(default_factory=dict)
    class_room_presence_variables: dict[tuple[str, date, str], cp_model.IntVar] = field(
        default_factory=dict
    )
    class_slot_variables: dict[tuple[str, date, str, str], cp_model.IntVar] = field(
        default_factory=dict
    )
    penalty_terms_by_priority: dict[int, list[cp_model.IntVar]] = field(default_factory=dict)

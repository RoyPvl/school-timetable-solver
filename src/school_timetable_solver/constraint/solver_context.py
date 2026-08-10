from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from ortools.sat.python import cp_model

from school_timetable_solver.model.input_models import TeacherDayOffRuleModel
from school_timetable_solver.model.solver_models import (
    CandidateSlotModel,
    ResolvedHomeroomBoundaryRuleModel,
    ResolvedLessonCountPreferenceRuleModel,
    ResolvedLessonCountRuleModel,
)


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
    teacher_first_last_period_forbidden: dict[tuple[str, date], bool]
    class_attendance_limits: dict[tuple[str, date], int | None]
    period_orders: dict[str, int]
    calendar_dates: tuple[date, ...]
    class_required_lesson_periods: dict[tuple[str, date], tuple[str, ...]] = field(
        default_factory=dict
    )
    room_priorities_by_campus: dict[str, tuple[int, ...]] = field(default_factory=dict)
    class_attendance_preference_limits: dict[tuple[str, date], int | None] = field(
        default_factory=dict
    )
    lesson_count_rules: tuple[ResolvedLessonCountRuleModel, ...] = ()
    lesson_count_preference_rules: tuple[ResolvedLessonCountPreferenceRuleModel, ...] = ()
    homeroom_boundary_rules: tuple[ResolvedHomeroomBoundaryRuleModel, ...] = ()
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
    penalty_term_groups_by_priority: dict[
        int,
        dict[tuple[str, ...], list[cp_model.IntVar]],
    ] = field(default_factory=dict)
    teacher_day_off_rules: tuple[TeacherDayOffRuleModel, ...] = ()
    teacher_day_off_variables: dict[tuple[str, date], cp_model.IntVar] = field(default_factory=dict)
    homeroom_first_date_variables: dict[tuple[str, str, date], cp_model.IntVar] = field(
        default_factory=dict
    )
    homeroom_last_date_variables: dict[tuple[str, str, date], cp_model.IntVar] = field(
        default_factory=dict
    )
    homeroom_attendance_variables: dict[tuple[str, str, date], cp_model.IntVar] = field(
        default_factory=dict
    )
    teacher_home_campuses: dict[str, str] = field(default_factory=dict)
    fixed_teacher_leave_cell_counts: dict[tuple[str, date], int] = field(default_factory=dict)

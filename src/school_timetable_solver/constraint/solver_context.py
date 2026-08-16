from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from ortools.sat.python import cp_model

from school_timetable_solver.model.input_models import (
    ClassPairOverlapRuleModel,
    TeacherDayOffRuleModel,
)
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
    attendance_group_class_ids: dict[str, tuple[str, ...]] = field(default_factory=dict)
    attendance_group_limits: dict[tuple[str, date], int | None] = field(default_factory=dict)
    attendance_group_preference_limits: dict[tuple[str, date], int | None] = field(
        default_factory=dict
    )
    lesson_count_rules: tuple[ResolvedLessonCountRuleModel, ...] = ()
    lesson_count_preference_rules: tuple[ResolvedLessonCountPreferenceRuleModel, ...] = ()
    homeroom_boundary_rules: tuple[ResolvedHomeroomBoundaryRuleModel, ...] = ()
    class_pair_overlap_rules: tuple[ClassPairOverlapRuleModel, ...] = ()
    single_subject_class_ids: frozenset[str] = frozenset()
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


def ensure_attendance_group_day_variables(context: SolverContext) -> None:
    group_class_ids = context.attendance_group_class_ids
    if not group_class_ids:
        class_ids = {class_id for class_id, _ in context.class_attendance_limits} | {
            class_id for class_id, _ in context.class_attendance_preference_limits
        }
        group_class_ids = {class_id: (class_id,) for class_id in class_ids}

    group_ids_by_class: dict[str, list[str]] = {}
    for group_id, class_ids in group_class_ids.items():
        for class_id in class_ids:
            group_ids_by_class.setdefault(class_id, []).append(group_id)

    variables_by_group_day: dict[tuple[str, date], list[cp_model.IntVar]] = {}
    for candidate in context.candidates:
        for group_id in group_ids_by_class.get(candidate.class_id, ()):
            variables_by_group_day.setdefault((group_id, candidate.target_date), []).append(
                context.assignment_variables[candidate.candidate_id]
            )

    for group_id in group_class_ids:
        for target_date in context.calendar_dates:
            key = (group_id, target_date)
            if key in context.class_day_variables:
                continue
            day_variable = context.model.new_bool_var(
                f"attendance_group_day__{group_id}__{target_date.isoformat()}"
            )
            context.class_day_variables[key] = day_variable
            variables = variables_by_group_day.get(key, ())
            if variables:
                context.model.add_max_equality(day_variable, variables)
            else:
                context.model.add(day_variable == 0)

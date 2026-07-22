from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from itertools import pairwise

from ortools.sat.python import cp_model

from school_timetable_solver.constraint.solver_context import SolverContext
from school_timetable_solver.model.solver_models import CandidateSlotModel


class RequiredLessonCountConstraint:
    """H06: require exactly the requested number of lessons."""

    rule_id = "H06"

    def apply(self, context: SolverContext) -> None:
        variables_by_requirement: dict[str, list[cp_model.IntVar]] = defaultdict(list)
        for candidate in context.candidates:
            variables_by_requirement[candidate.requirement_id].append(
                context.assignment_variables[candidate.candidate_id]
            )
        for requirement_id, required_count in context.required_counts.items():
            context.model.add(sum(variables_by_requirement[requirement_id]) == required_count)
        context.applied_rule_ids.append(self.rule_id)


class FixedLessonConstraint:
    """H12: force every fixed lesson onto its specified assignment."""

    rule_id = "H12"

    def apply(self, context: SolverContext) -> None:
        for fixed in context.fixed_lessons:
            variables = [
                context.assignment_variables[candidate.candidate_id]
                for candidate in context.candidates
                if candidate.requirement_id == fixed.requirement_id
                and candidate.target_date == fixed.target_date
                and candidate.period_id == fixed.period_id
                and candidate.teacher_id == fixed.teacher_id
                and candidate.room_id == fixed.room_id
                and candidate.class_id == fixed.class_id
                and candidate.subject_id == fixed.subject_id
            ]
            if variables:
                context.model.add(sum(variables) == 1)
            else:
                context.model.add_bool_or([])
        context.applied_rule_ids.append(self.rule_id)


class TeacherOverlapConstraint:
    """H01: prohibit simultaneous lessons for the same teacher."""

    rule_id = "H01"

    def apply(self, context: SolverContext) -> None:
        groups: dict[tuple[str, date, str], list[cp_model.IntVar]] = defaultdict(list)
        for candidate in context.candidates:
            groups[(candidate.teacher_id, candidate.target_date, candidate.period_id)].append(
                context.assignment_variables[candidate.candidate_id]
            )
        for variables in groups.values():
            context.model.add(sum(variables) <= 1)
        context.applied_rule_ids.append(self.rule_id)


class ClassOverlapConstraint:
    """H02: prohibit simultaneous lessons for the same class."""

    rule_id = "H02"

    def apply(self, context: SolverContext) -> None:
        groups: dict[tuple[str, date, str], list[cp_model.IntVar]] = defaultdict(list)
        for candidate in context.candidates:
            groups[(candidate.class_id, candidate.target_date, candidate.period_id)].append(
                context.assignment_variables[candidate.candidate_id]
            )
        for variables in groups.values():
            context.model.add(sum(variables) <= 1)
        context.applied_rule_ids.append(self.rule_id)


class RoomOverlapConstraint:
    """H03: prohibit simultaneous lessons in the same room."""

    rule_id = "H03"

    def apply(self, context: SolverContext) -> None:
        groups: dict[tuple[str, date, str], list[cp_model.IntVar]] = defaultdict(list)
        for candidate in context.candidates:
            groups[(candidate.room_id, candidate.target_date, candidate.period_id)].append(
                context.assignment_variables[candidate.candidate_id]
            )
        for variables in groups.values():
            context.model.add(sum(variables) <= 1)
        context.applied_rule_ids.append(self.rule_id)


class ClassDailyLimitConstraint:
    """H07: enforce class and per-requirement daily hard limits."""

    rule_id = "H07"

    def apply(self, context: SolverContext) -> None:
        class_groups: dict[tuple[str, date], list[cp_model.IntVar]] = defaultdict(list)
        requirement_groups: dict[tuple[str, date], list[cp_model.IntVar]] = defaultdict(list)
        for candidate in context.candidates:
            variable = context.assignment_variables[candidate.candidate_id]
            class_groups[(candidate.class_id, candidate.target_date)].append(variable)
            requirement_groups[(candidate.requirement_id, candidate.target_date)].append(variable)
        for key, variables in class_groups.items():
            limit = context.class_daily_limits[key]
            if limit is not None:
                context.model.add(sum(variables) <= limit)
        for (requirement_id, _target_date), variables in requirement_groups.items():
            limit = context.requirement_daily_limits[requirement_id]
            if limit is not None:
                context.model.add(sum(variables) <= limit)
        context.applied_rule_ids.append(self.rule_id)


class TeacherDailyLimitConstraint:
    """H08: enforce each teacher's resolved daily hard limit."""

    rule_id = "H08"

    def apply(self, context: SolverContext) -> None:
        groups: dict[tuple[str, date], list[cp_model.IntVar]] = defaultdict(list)
        for candidate in context.candidates:
            groups[(candidate.teacher_id, candidate.target_date)].append(
                context.assignment_variables[candidate.candidate_id]
            )
        for key, variables in groups.items():
            limit = context.teacher_daily_limits[key]
            if limit is not None:
                context.model.add(sum(variables) <= limit)
        context.applied_rule_ids.append(self.rule_id)


class TeacherConsecutivePeriodConstraint:
    """H09: enforce the maximum consecutive period count for each teacher."""

    rule_id = "H09"

    def apply(self, context: SolverContext) -> None:
        groups: dict[tuple[str, date, str], list[cp_model.IntVar]] = defaultdict(list)
        for candidate in context.candidates:
            groups[(candidate.teacher_id, candidate.target_date, candidate.period_id)].append(
                context.assignment_variables[candidate.candidate_id]
            )
        ordered_periods = [
            period_id
            for period_id, _ in sorted(context.period_orders.items(), key=lambda item: item[1])
        ]
        teacher_dates = {(key[0], key[1]) for key in groups}
        for teacher_id, target_date in teacher_dates:
            limit = context.teacher_consecutive_limits[(teacher_id, target_date)]
            if limit is None or limit >= len(ordered_periods):
                continue
            for start in range(len(ordered_periods) - limit):
                variables = [
                    variable
                    for period_id in ordered_periods[start : start + limit + 1]
                    for variable in groups.get((teacher_id, target_date, period_id), [])
                ]
                context.model.add(sum(variables) <= limit)
        context.applied_rule_ids.append(self.rule_id)


class ConsecutiveAttendanceConstraint:
    """H10: enforce the maximum streak of calendar-day attendance per class."""

    rule_id = "H10"

    def apply(self, context: SolverContext) -> None:
        groups: dict[tuple[str, date], list[cp_model.IntVar]] = defaultdict(list)
        for candidate in context.candidates:
            groups[(candidate.class_id, candidate.target_date)].append(
                context.assignment_variables[candidate.candidate_id]
            )
        class_ids = {key[0] for key in context.class_attendance_limits}
        for class_id in class_ids:
            for target_date in context.calendar_dates:
                key = (class_id, target_date)
                day_variable = context.model.new_bool_var(
                    f"class_day__{class_id}__{target_date.isoformat()}"
                )
                context.class_day_variables[key] = day_variable
                variables = groups.get(key, [])
                if variables:
                    context.model.add_max_equality(day_variable, variables)
                else:
                    context.model.add(day_variable == 0)
            for start_index, start_date in enumerate(context.calendar_dates):
                limit = context.class_attendance_limits[(class_id, start_date)]
                if limit is None:
                    continue
                window = context.calendar_dates[start_index : start_index + limit + 1]
                if len(window) != limit + 1:
                    continue
                if any(right - left != timedelta(days=1) for left, right in pairwise(window)):
                    continue
                context.model.add(
                    sum(
                        context.class_day_variables[(class_id, target_date)]
                        for target_date in window
                    )
                    <= limit
                )
        context.applied_rule_ids.append(self.rule_id)


class CampusTransferConstraint:
    """H11: require enough empty periods between different-campus assignments."""

    rule_id = "H11"

    def apply(self, context: SolverContext) -> None:
        groups: dict[tuple[str, date], list[CandidateSlotModel]] = defaultdict(list)
        for candidate in context.candidates:
            groups[(candidate.teacher_id, candidate.target_date)].append(candidate)
        for (teacher_id, _target_date), candidates in groups.items():
            can_transfer = context.teacher_can_transfer[teacher_id]
            gap = context.teacher_transfer_gaps[teacher_id]
            for index, left in enumerate(candidates):
                for right in candidates[index + 1 :]:
                    if left.campus_id == right.campus_id:
                        continue
                    period_distance = abs(
                        context.period_orders[left.period_id]
                        - context.period_orders[right.period_id]
                    )
                    if not can_transfer or period_distance - 1 < gap:
                        context.model.add(
                            context.assignment_variables[left.candidate_id]
                            + context.assignment_variables[right.candidate_id]
                            <= 1
                        )
        context.applied_rule_ids.append(self.rule_id)


DEFAULT_HARD_CONSTRAINTS = (
    RequiredLessonCountConstraint(),
    FixedLessonConstraint(),
    TeacherOverlapConstraint(),
    ClassOverlapConstraint(),
    RoomOverlapConstraint(),
    ClassDailyLimitConstraint(),
    TeacherDailyLimitConstraint(),
    TeacherConsecutivePeriodConstraint(),
    ConsecutiveAttendanceConstraint(),
    CampusTransferConstraint(),
)

HardConstraint = (
    RequiredLessonCountConstraint
    | FixedLessonConstraint
    | TeacherOverlapConstraint
    | ClassOverlapConstraint
    | RoomOverlapConstraint
    | ClassDailyLimitConstraint
    | TeacherDailyLimitConstraint
    | TeacherConsecutivePeriodConstraint
    | ConsecutiveAttendanceConstraint
    | CampusTransferConstraint
)

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from itertools import pairwise

from ortools.sat.python import cp_model

from school_timetable_solver.constraint.solver_context import SolverContext


class RequiredLessonCountConstraint:
    """H06: require exactly the requested number of lessons."""

    rule_id = "H06"

    def apply(self, context: SolverContext) -> None:
        groups: dict[str, list[cp_model.IntVar]] = defaultdict(list)
        for candidate in context.candidates:
            groups[candidate.requirement_id].append(
                context.assignment_variables[candidate.candidate_id]
            )
        for requirement_id, required_count in context.required_counts.items():
            context.model.add(sum(groups[requirement_id]) == required_count)
        context.applied_rule_ids.append(self.rule_id)


class TeacherOverlapConstraint:
    """H01: prohibit simultaneous lessons for one teacher."""

    rule_id = "H01"

    def apply(self, context: SolverContext) -> None:
        groups: dict[tuple[str, date, str], list[cp_model.IntVar]] = defaultdict(list)
        requirement_ids_by_teacher: dict[str, set[str]] = defaultdict(set)
        slots_by_teacher: dict[str, set[tuple[date, str]]] = defaultdict(set)
        for candidate in context.candidates:
            groups[(candidate.teacher_id, candidate.target_date, candidate.period_id)].append(
                context.assignment_variables[candidate.candidate_id]
            )
            requirement_ids_by_teacher[candidate.teacher_id].add(candidate.requirement_id)
            slots_by_teacher[candidate.teacher_id].add((candidate.target_date, candidate.period_id))
        saturated_teachers = {
            teacher_id
            for teacher_id, slots in slots_by_teacher.items()
            if sum(
                context.required_counts[requirement_id]
                for requirement_id in requirement_ids_by_teacher[teacher_id]
            )
            == len(slots)
        }
        for (teacher_id, _, _), variables in groups.items():
            if teacher_id in saturated_teachers:
                # H06 and H01 imply every available slot is occupied when demand equals supply.
                context.model.add(sum(variables) == 1)
            else:
                context.model.add(sum(variables) <= 1)
        context.applied_rule_ids.append(self.rule_id)


class ClassOverlapConstraint:
    """H02: prohibit simultaneous lessons for one class."""

    rule_id = "H02"

    def apply(self, context: SolverContext) -> None:
        groups: dict[tuple[str, date, str], list[cp_model.IntVar]] = defaultdict(list)
        requirement_ids_by_class: dict[str, set[str]] = defaultdict(set)
        slots_by_class: dict[str, set[tuple[date, str]]] = defaultdict(set)
        for candidate in context.candidates:
            groups[(candidate.class_id, candidate.target_date, candidate.period_id)].append(
                context.assignment_variables[candidate.candidate_id]
            )
            requirement_ids_by_class[candidate.class_id].add(candidate.requirement_id)
            slots_by_class[candidate.class_id].add((candidate.target_date, candidate.period_id))
        saturated_classes = {
            class_id
            for class_id, slots in slots_by_class.items()
            if sum(
                context.required_counts[requirement_id]
                for requirement_id in requirement_ids_by_class[class_id]
            )
            == len(slots)
        }
        for (class_id, _, _), variables in groups.items():
            if class_id in saturated_classes:
                # H06 and H02 imply every available slot is occupied when demand equals supply.
                context.model.add(sum(variables) == 1)
            else:
                context.model.add(sum(variables) <= 1)
        context.applied_rule_ids.append(self.rule_id)


class CampusRoomCapacityConstraint:
    """H03: keep concurrent campus lessons within assignable room capacity."""

    rule_id = "H03"

    def apply(self, context: SolverContext) -> None:
        groups: dict[tuple[str, date, str], list[cp_model.IntVar]] = defaultdict(list)
        for candidate in context.candidates:
            groups[(candidate.campus_id, candidate.target_date, candidate.period_id)].append(
                context.assignment_variables[candidate.candidate_id]
            )
        for (campus_id, _, _), variables in groups.items():
            context.model.add(sum(variables) <= context.room_capacities[campus_id])
        context.applied_rule_ids.append(self.rule_id)


class ClassDailyLimitConstraint:
    """H07: enforce class and requirement daily limits."""

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
        for (requirement_id, _), variables in requirement_groups.items():
            limit = context.requirement_daily_limits[requirement_id]
            if limit is not None:
                context.model.add(sum(variables) <= limit)
        context.applied_rule_ids.append(self.rule_id)


class TeacherDailyLimitConstraint:
    """H08: enforce each teacher's resolved daily limit."""

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
    """H09: enforce each teacher's maximum consecutive period count."""

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
        for teacher_id, target_date in {(key[0], key[1]) for key in groups}:
            limit = context.teacher_consecutive_limits[(teacher_id, target_date)]
            if limit is None or limit >= len(ordered_periods):
                continue
            for start in range(len(ordered_periods) - limit):
                variables = [
                    variable
                    for period_id in ordered_periods[start : start + limit + 1]
                    for variable in groups.get((teacher_id, target_date, period_id), ())
                ]
                context.model.add(sum(variables) <= limit)
        context.applied_rule_ids.append(self.rule_id)


class ConsecutiveAttendanceConstraint:
    """H10: enforce each class's maximum consecutive calendar-day attendance."""

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
                variables = groups.get(key, ())
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
                    sum(context.class_day_variables[(class_id, day)] for day in window) <= limit
                )
        context.applied_rule_ids.append(self.rule_id)


class TeacherSingleCampusPerDayConstraint:
    """H11: allow each teacher to work at at most one campus per date."""

    rule_id = "H11"

    def apply(self, context: SolverContext) -> None:
        campus_groups: dict[tuple[str, date, str], list[cp_model.IntVar]] = defaultdict(list)
        for candidate in context.candidates:
            campus_groups[
                (candidate.teacher_id, candidate.target_date, candidate.campus_id)
            ].append(context.assignment_variables[candidate.candidate_id])
        campus_day_variables: dict[tuple[str, date], list[cp_model.IntVar]] = defaultdict(list)
        for (teacher_id, target_date, campus_id), variables in campus_groups.items():
            campus_variable = context.model.new_bool_var(
                f"teacher_campus_day__{teacher_id}__{target_date.isoformat()}__{campus_id}"
            )
            context.model.add_max_equality(campus_variable, variables)
            campus_day_variables[(teacher_id, target_date)].append(campus_variable)
        for variables in campus_day_variables.values():
            context.model.add(sum(variables) <= 1)
        context.applied_rule_ids.append(self.rule_id)


DEFAULT_HARD_CONSTRAINTS = (
    RequiredLessonCountConstraint(),
    TeacherOverlapConstraint(),
    ClassOverlapConstraint(),
    CampusRoomCapacityConstraint(),
    ClassDailyLimitConstraint(),
    TeacherDailyLimitConstraint(),
    TeacherConsecutivePeriodConstraint(),
    ConsecutiveAttendanceConstraint(),
    TeacherSingleCampusPerDayConstraint(),
)

HardConstraint = (
    RequiredLessonCountConstraint
    | TeacherOverlapConstraint
    | ClassOverlapConstraint
    | CampusRoomCapacityConstraint
    | ClassDailyLimitConstraint
    | TeacherDailyLimitConstraint
    | TeacherConsecutivePeriodConstraint
    | ConsecutiveAttendanceConstraint
    | TeacherSingleCampusPerDayConstraint
)

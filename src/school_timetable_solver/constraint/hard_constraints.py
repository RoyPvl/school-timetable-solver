from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from itertools import combinations, pairwise

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


class LessonCountInScopeConstraint:
    """H17: require the exact lesson count in every configured slot scope."""

    rule_id = "H17"

    def apply(self, context: SolverContext) -> None:
        variables_by_requirement_and_slot: dict[
            tuple[str, date, str],
            list[cp_model.IntVar],
        ] = defaultdict(list)
        for candidate in context.candidates:
            variables_by_requirement_and_slot[
                (
                    candidate.requirement_id,
                    candidate.target_date,
                    candidate.period_id,
                )
            ].append(context.assignment_variables[candidate.candidate_id])
        for rule in context.lesson_count_rules:
            if rule.exact_periods == 0:
                continue
            variables = [
                variable
                for target_date, period_id in rule.target_slots
                for variable in variables_by_requirement_and_slot[
                    (rule.requirement_id, target_date, period_id)
                ]
            ]
            context.model.add(sum(variables) == rule.exact_periods)
        context.applied_rule_ids.append(self.rule_id)


class HomeroomBoundaryConstraint:
    """H18: put a homeroom lesson on the first and last attendance day."""

    rule_id = "H18"

    def apply(self, context: SolverContext) -> None:
        variables_by_class_date: dict[
            tuple[str, date],
            list[tuple[str, cp_model.IntVar]],
        ] = defaultdict(list)
        for candidate in context.candidates:
            variables_by_class_date[(candidate.class_id, candidate.target_date)].append(
                (
                    candidate.teacher_id,
                    context.assignment_variables[candidate.candidate_id],
                )
            )

        for rule in context.homeroom_boundary_rules:
            target_dates = sorted(
                target_date
                for class_id, target_date in variables_by_class_date
                if class_id == rule.class_id and rule.start_date <= target_date <= rule.end_date
            )
            if not target_dates:
                context.model.add(0 >= 1)
                continue

            homeroom_variables_by_date: dict[date, list[cp_model.IntVar]] = {
                target_date: [
                    variable
                    for teacher_id, variable in variables_by_class_date[
                        (rule.class_id, target_date)
                    ]
                    if teacher_id == rule.teacher_id
                ]
                for target_date in target_dates
            }
            eligible_boundary_dates = [
                target_date
                for target_date in target_dates
                if homeroom_variables_by_date[target_date]
            ]
            if not eligible_boundary_dates:
                context.model.add(0 >= 1)
                continue

            attendance_variables_by_date: dict[date, cp_model.IntVar] = {}
            for target_date in target_dates:
                attendance_variable = context.model.new_bool_var(
                    f"h18_attendance__{rule.rule_id}__{target_date.isoformat()}"
                )
                context.model.add_max_equality(
                    attendance_variable,
                    [
                        variable
                        for _, variable in variables_by_class_date[(rule.class_id, target_date)]
                    ],
                )
                attendance_variables_by_date[target_date] = attendance_variable

            first_date_variables = self._add_boundary_date_variables(
                context,
                rule.rule_id,
                target_dates,
                attendance_variables_by_date,
                "first",
            )
            last_date_variables = self._add_boundary_date_variables(
                context,
                rule.rule_id,
                list(reversed(target_dates)),
                attendance_variables_by_date,
                "last",
            )
            context.model.add_exactly_one(first_date_variables)
            context.model.add_exactly_one(last_date_variables)

            for target_date in eligible_boundary_dates:
                first_date_variable = first_date_variables[target_dates.index(target_date)]
                last_date_variable = last_date_variables[
                    list(reversed(target_dates)).index(target_date)
                ]
                context.homeroom_first_date_variables[(rule.rule_id, target_date)] = (
                    first_date_variable
                )
                context.homeroom_last_date_variables[(rule.rule_id, target_date)] = (
                    last_date_variable
                )
                context.model.add_bool_or(homeroom_variables_by_date[target_date]).only_enforce_if(
                    first_date_variable
                )
                context.model.add_bool_or(homeroom_variables_by_date[target_date]).only_enforce_if(
                    last_date_variable
                )
            for target_date in set(target_dates) - set(eligible_boundary_dates):
                context.model.add(first_date_variables[target_dates.index(target_date)] == 0)
                context.model.add(
                    last_date_variables[list(reversed(target_dates)).index(target_date)] == 0
                )
        context.applied_rule_ids.append(self.rule_id)

    def _add_boundary_date_variables(
        self,
        context: SolverContext,
        rule_id: str,
        ordered_dates: list[date],
        attendance_variables_by_date: dict[date, cp_model.IntVar],
        boundary_name: str,
    ) -> list[cp_model.IntVar]:
        boundary_variables: list[cp_model.IntVar] = []
        attendance_seen: cp_model.IntVar | None = None
        for date_index, target_date in enumerate(ordered_dates):
            attendance_variable = attendance_variables_by_date[target_date]
            boundary_variable = context.model.new_bool_var(
                f"h18_{boundary_name}_date__{rule_id}__{target_date.isoformat()}"
            )
            if attendance_seen is None:
                context.model.add(boundary_variable == attendance_variable)
                attendance_seen = attendance_variable
            else:
                context.model.add(boundary_variable <= attendance_variable)
                context.model.add(boundary_variable + attendance_seen <= 1)
                context.model.add(boundary_variable >= attendance_variable - attendance_seen)
                next_attendance_seen = context.model.new_bool_var(
                    f"h18_{boundary_name}_seen__{rule_id}__{date_index}"
                )
                context.model.add_max_equality(
                    next_attendance_seen,
                    [attendance_seen, attendance_variable],
                )
                attendance_seen = next_attendance_seen
            boundary_variables.append(boundary_variable)
        return boundary_variables


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


class ClassRoomContinuityConstraint:
    """H15: assign every lesson of one class and date to one anonymous room."""

    rule_id = "H15"

    def apply(self, context: SolverContext) -> None:
        variables_by_class_day: dict[
            tuple[str, date, str],
            list[cp_model.IntVar],
        ] = defaultdict(list)
        variables_by_class_slot: dict[
            tuple[str, date, str, str],
            list[cp_model.IntVar],
        ] = defaultdict(list)
        for candidate in context.candidates:
            variable = context.assignment_variables[candidate.candidate_id]
            variables_by_class_day[
                (candidate.campus_id, candidate.target_date, candidate.class_id)
            ].append(variable)
            variables_by_class_slot[
                (
                    candidate.campus_id,
                    candidate.target_date,
                    candidate.class_id,
                    candidate.period_id,
                )
            ].append(variable)

        class_days_by_campus_day: dict[
            tuple[str, date],
            list[tuple[str, cp_model.IntVar, cp_model.IntVar]],
        ] = defaultdict(list)
        for key, variables in variables_by_class_day.items():
            campus_id, target_date, class_id = key
            presence = context.model.new_bool_var(
                f"class_room_day__{class_id}__{target_date.isoformat()}"
            )
            context.model.add_max_equality(presence, variables)
            room = context.model.new_int_var(
                0,
                context.room_capacities[campus_id] - 1,
                f"class_room__{class_id}__{target_date.isoformat()}",
            )
            context.model.add(room == 0).only_enforce_if(presence.negated())
            context.class_room_variables[key] = room
            context.class_room_presence_variables[key] = presence
            class_days_by_campus_day[(campus_id, target_date)].append((class_id, presence, room))

        for class_days in class_days_by_campus_day.values():
            previous_presence_variables: list[cp_model.IntVar] = []
            for _, presence, room in sorted(class_days):
                if previous_presence_variables:
                    context.model.add(room <= sum(previous_presence_variables)).only_enforce_if(
                        presence
                    )
                else:
                    context.model.add(room == 0).only_enforce_if(presence)
                previous_presence_variables.append(presence)

        classes_by_campus_slot: dict[
            tuple[str, date, str],
            list[tuple[str, cp_model.IntVar, cp_model.IntVar]],
        ] = defaultdict(list)
        for key, variables in variables_by_class_slot.items():
            campus_id, target_date, class_id, period_id = key
            slot = context.model.new_bool_var(
                f"class_slot__{class_id}__{target_date.isoformat()}__{period_id}"
            )
            context.model.add_max_equality(slot, variables)
            context.class_slot_variables[key] = slot
            classes_by_campus_slot[(campus_id, target_date, period_id)].append(
                (
                    class_id,
                    slot,
                    context.class_room_variables[(campus_id, target_date, class_id)],
                )
            )

        for classes in classes_by_campus_slot.values():
            for left, right in combinations(classes, 2):
                context.model.add(left[2] != right[2]).only_enforce_if([left[1], right[1]])
        context.applied_rule_ids.append(self.rule_id)


class ClassLongInternalGapConstraint:
    """H16: forbid two consecutive empty periods between one class's lessons."""

    rule_id = "H16"

    def apply(self, context: SolverContext) -> None:
        ordered_period_ids = tuple(
            period_id
            for period_id, _ in sorted(
                context.period_orders.items(),
                key=lambda item: item[1],
            )
        )
        for campus_id, target_date, class_id in context.class_room_variables:
            slots = tuple(
                context.class_slot_variables.get((campus_id, target_date, class_id, period_id))
                for period_id in ordered_period_ids
            )
            for first_gap_index in range(1, len(slots) - 2):
                second_gap_index = first_gap_index + 1
                gap_slots = tuple(
                    slot
                    for slot in (slots[first_gap_index], slots[second_gap_index])
                    if slot is not None
                )
                for left_index in range(first_gap_index):
                    left_slot = slots[left_index]
                    if left_slot is None:
                        continue
                    for right_index in range(second_gap_index + 1, len(slots)):
                        right_slot = slots[right_index]
                        if right_slot is None:
                            continue
                        context.model.add(left_slot + right_slot - sum(gap_slots) <= 1)
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
            for end_index, end_date in enumerate(context.calendar_dates):
                limit = context.class_attendance_limits[(class_id, end_date)]
                if limit is None:
                    continue
                window = context.calendar_dates[max(0, end_index - limit) : end_index + 1]
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
        variables_by_teacher_date_campus: dict[
            tuple[str, date, str],
            list[cp_model.IntVar],
        ] = defaultdict(list)
        for candidate in context.candidates:
            key = (candidate.teacher_id, candidate.target_date, candidate.campus_id)
            variables_by_teacher_date_campus[key].append(
                context.assignment_variables[candidate.candidate_id]
            )

        variables_by_teacher_date: dict[tuple[str, date], list[cp_model.IntVar]] = defaultdict(list)
        for (
            teacher_id,
            target_date,
            campus_id,
        ), assignment_variables in variables_by_teacher_date_campus.items():
            campus_day_variable = context.model.new_bool_var(
                f"teacher_campus_day__{teacher_id}__{target_date.isoformat()}__{campus_id}"
            )
            context.teacher_campus_day_variables[(teacher_id, target_date, campus_id)] = (
                campus_day_variable
            )
            variables_by_teacher_date[(teacher_id, target_date)].append(campus_day_variable)
            assignment_count = sum(assignment_variables)
            context.model.add(assignment_count >= campus_day_variable)
            context.model.add(assignment_count <= len(assignment_variables) * campus_day_variable)

        for variables in variables_by_teacher_date.values():
            context.model.add_at_most_one(variables)
        context.applied_rule_ids.append(self.rule_id)


DEFAULT_HARD_CONSTRAINTS = (
    RequiredLessonCountConstraint(),
    LessonCountInScopeConstraint(),
    HomeroomBoundaryConstraint(),
    TeacherOverlapConstraint(),
    ClassOverlapConstraint(),
    CampusRoomCapacityConstraint(),
    ClassRoomContinuityConstraint(),
    ClassLongInternalGapConstraint(),
    ClassDailyLimitConstraint(),
    TeacherDailyLimitConstraint(),
    TeacherConsecutivePeriodConstraint(),
    ConsecutiveAttendanceConstraint(),
    TeacherSingleCampusPerDayConstraint(),
)

HardConstraint = (
    RequiredLessonCountConstraint
    | LessonCountInScopeConstraint
    | HomeroomBoundaryConstraint
    | TeacherOverlapConstraint
    | ClassOverlapConstraint
    | CampusRoomCapacityConstraint
    | ClassRoomContinuityConstraint
    | ClassLongInternalGapConstraint
    | ClassDailyLimitConstraint
    | TeacherDailyLimitConstraint
    | TeacherConsecutivePeriodConstraint
    | ConsecutiveAttendanceConstraint
    | TeacherSingleCampusPerDayConstraint
)

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


class HomeroomAttendanceBoundaryConstraint:
    """H20: require a regular homeroom-teacher lesson on each attendance boundary day."""

    rule_id = "H20"

    def apply(self, context: SolverContext) -> None:
        variables_by_class_date: dict[
            tuple[str, date],
            list[tuple[str, cp_model.IntVar]],
        ] = defaultdict(list)
        for candidate in context.candidates:
            variables_by_class_date[(candidate.class_id, candidate.target_date)].append(
                (
                    candidate.requirement_id,
                    context.assignment_variables[candidate.candidate_id],
                )
            )

        for rule in context.homeroom_boundary_rules:
            attendance_requirement_ids = set(rule.attendance_requirement_ids)
            attendance_variables_by_date = {
                target_date: [
                    variable
                    for requirement_id, variable in variables
                    if requirement_id in attendance_requirement_ids
                ]
                for (class_id, target_date), variables in variables_by_class_date.items()
                if class_id == rule.class_id and rule.start_date <= target_date <= rule.end_date
            }
            attendance_variables_by_date = {
                target_date: variables
                for target_date, variables in attendance_variables_by_date.items()
                if variables
            }
            target_dates = sorted(attendance_variables_by_date)
            if not target_dates:
                context.model.add(0 >= 1)
                continue
            eligible_requirement_ids = set(rule.eligible_requirement_ids)
            eligible_variables_by_date = {
                target_date: [
                    variable
                    for requirement_id, variable in variables_by_class_date[
                        (rule.class_id, target_date)
                    ]
                    if requirement_id in eligible_requirement_ids
                ]
                for target_date in target_dates
            }
            attendance_variables: dict[date, cp_model.IntVar] = {}
            for target_date in target_dates:
                attendance = context.model.new_bool_var(
                    f"h20_attendance__{rule.source_rule_id}__{rule.class_id}__"
                    f"{target_date.isoformat()}"
                )
                context.model.add_max_equality(
                    attendance,
                    attendance_variables_by_date[target_date],
                )
                attendance_variables[target_date] = attendance
                context.homeroom_attendance_variables[
                    (rule.source_rule_id, rule.class_id, target_date)
                ] = attendance

            # H06 normally guarantees attendance, but keeping this explicit makes H20
            # independently equivalent to the former exactly-one boundary encoding.
            context.model.add(sum(attendance_variables.values()) >= 1)
            earlier_attendance: list[cp_model.IntVar] = []
            for target_date in target_dates:
                eligible_variables = eligible_variables_by_date[target_date]
                context.model.add(
                    attendance_variables[target_date]
                    <= sum(eligible_variables) + sum(earlier_attendance)
                )
                earlier_attendance.append(attendance_variables[target_date])

            later_attendance: list[cp_model.IntVar] = []
            for target_date in reversed(target_dates):
                context.model.add(
                    attendance_variables[target_date]
                    <= sum(eligible_variables_by_date[target_date]) + sum(later_attendance)
                )
                later_attendance.append(attendance_variables[target_date])
        context.applied_rule_ids.append(self.rule_id)


class ClassRequiredLessonSlotConstraint:
    """H21: require one lesson in every configured class/date/period slot."""

    rule_id = "H21"

    def apply(self, context: SolverContext) -> None:
        variables_by_class_slot: dict[
            tuple[str, date, str],
            list[cp_model.IntVar],
        ] = defaultdict(list)
        for candidate in context.candidates:
            variables_by_class_slot[
                (candidate.class_id, candidate.target_date, candidate.period_id)
            ].append(context.assignment_variables[candidate.candidate_id])
        for (class_id, target_date), period_ids in context.class_required_lesson_periods.items():
            for period_id in period_ids:
                context.model.add(
                    sum(variables_by_class_slot[(class_id, target_date, period_id)]) == 1
                )
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


class TeacherFirstLastPeriodConstraint:
    """H09: prevent a teacher from working both boundary periods on one day."""

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
        if len(ordered_periods) >= 2:
            first_period_id = ordered_periods[0]
            last_period_id = ordered_periods[-1]
            for (
                teacher_id,
                target_date,
            ), forbidden in context.teacher_first_last_period_forbidden.items():
                if not forbidden:
                    continue
                first_period_variables = groups.get((teacher_id, target_date, first_period_id), ())
                last_period_variables = groups.get((teacher_id, target_date, last_period_id), ())
                context.model.add(sum(first_period_variables) + sum(last_period_variables) <= 1)
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


class TeacherDayOffQuotaConstraint:
    """H18: select the exact number of full teacher days off in each input range."""

    rule_id = "H18"

    def apply(self, context: SolverContext) -> None:
        assignments_by_teacher_day: dict[
            tuple[str, date],
            list[cp_model.IntVar],
        ] = defaultdict(list)
        for candidate in context.candidates:
            assignments_by_teacher_day[(candidate.teacher_id, candidate.target_date)].append(
                context.assignment_variables[candidate.candidate_id]
            )

        variables_by_group: dict[tuple[str, str], list[cp_model.IntVar]] = defaultdict(list)
        group_totals: dict[tuple[str, str], int] = {}
        for rule in context.teacher_day_off_rules:
            if not rule.enabled:
                continue
            rule_variables: list[cp_model.IntVar] = []
            for target_date in context.calendar_dates:
                if not rule.start_date <= target_date <= rule.end_date:
                    continue
                key = (rule.teacher_id, target_date)
                day_off = context.teacher_day_off_variables.get(key)
                if day_off is None:
                    day_off = context.model.new_bool_var(
                        f"teacher_day_off__{rule.teacher_id}__{target_date.isoformat()}"
                    )
                    context.teacher_day_off_variables[key] = day_off
                    assignments = assignments_by_teacher_day.get(key, ())
                    if assignments:
                        context.model.add(sum(assignments) == 0).only_enforce_if(day_off)
                rule_variables.append(day_off)
            rule_sum = sum(rule_variables)
            if rule.required_days_off is not None:
                context.model.add(rule_sum == rule.required_days_off)
            else:
                assert rule.minimum_days_off is not None
                assert rule.maximum_days_off is not None
                context.model.add(rule_sum >= rule.minimum_days_off)
                context.model.add(rule_sum <= rule.maximum_days_off)
            if rule.quota_group_id is not None:
                group_key = (rule.teacher_id, rule.quota_group_id)
                variables_by_group[group_key].extend(rule_variables)
                assert rule.group_required_days_off is not None
                group_totals[group_key] = rule.group_required_days_off
        for group_key, variables in variables_by_group.items():
            context.model.add(sum(variables) == group_totals[group_key])
        context.applied_rule_ids.append(self.rule_id)


class TeacherLeaveAnnotationCapacityConstraint:
    """H19: keep fixed and selected leave annotations within campus room columns."""

    rule_id = "H19"

    def apply(self, context: SolverContext) -> None:
        variables_by_campus_day: dict[
            tuple[str, date],
            list[cp_model.IntVar],
        ] = defaultdict(list)
        for (teacher_id, target_date), variable in context.teacher_day_off_variables.items():
            variables_by_campus_day[
                (context.teacher_home_campuses[teacher_id], target_date)
            ].append(variable)
        for key, variables in variables_by_campus_day.items():
            campus_id, _ = key
            fixed_cells = context.fixed_teacher_leave_cell_counts.get(key, 0)
            context.model.add(sum(variables) + fixed_cells <= context.room_capacities[campus_id])
        context.applied_rule_ids.append(self.rule_id)


DEFAULT_HARD_CONSTRAINTS = (
    RequiredLessonCountConstraint(),
    LessonCountInScopeConstraint(),
    HomeroomAttendanceBoundaryConstraint(),
    ClassRequiredLessonSlotConstraint(),
    TeacherOverlapConstraint(),
    ClassOverlapConstraint(),
    CampusRoomCapacityConstraint(),
    ClassRoomContinuityConstraint(),
    ClassLongInternalGapConstraint(),
    ClassDailyLimitConstraint(),
    TeacherDailyLimitConstraint(),
    TeacherFirstLastPeriodConstraint(),
    ConsecutiveAttendanceConstraint(),
    TeacherSingleCampusPerDayConstraint(),
    TeacherDayOffQuotaConstraint(),
    TeacherLeaveAnnotationCapacityConstraint(),
)

HardConstraint = (
    RequiredLessonCountConstraint
    | LessonCountInScopeConstraint
    | HomeroomAttendanceBoundaryConstraint
    | ClassRequiredLessonSlotConstraint
    | TeacherOverlapConstraint
    | ClassOverlapConstraint
    | CampusRoomCapacityConstraint
    | ClassRoomContinuityConstraint
    | ClassLongInternalGapConstraint
    | ClassDailyLimitConstraint
    | TeacherDailyLimitConstraint
    | TeacherFirstLastPeriodConstraint
    | ConsecutiveAttendanceConstraint
    | TeacherSingleCampusPerDayConstraint
    | TeacherDayOffQuotaConstraint
    | TeacherLeaveAnnotationCapacityConstraint
)

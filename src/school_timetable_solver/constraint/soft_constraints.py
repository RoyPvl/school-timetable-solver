from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from itertools import combinations, pairwise

from ortools.sat.python import cp_model

from school_timetable_solver.constraint.solver_context import (
    SolverContext,
    ensure_attendance_group_day_variables,
)


class RoomChangeGapPreferenceConstraint:
    """S10: minimize adjacent-period changes between different classes in one room."""

    rule_id = "S10"
    priority = 9
    optimization_scope = "room"

    def apply(self, context: SolverContext) -> None:
        excluded_transitions = {
            (rule.first_class_id, rule.second_class_id)
            for rule in context.class_pair_overlap_rules
            if rule.enabled
        }
        ordered_period_ids = tuple(
            period_id
            for period_id, _ in sorted(
                context.period_orders.items(),
                key=lambda item: item[1],
            )
        )
        classes_by_campus_day: dict[tuple[str, date], set[str]] = defaultdict(set)
        for campus_id, target_date, class_id in context.class_room_variables:
            classes_by_campus_day[(campus_id, target_date)].add(class_id)

        for (campus_id, target_date), class_ids in classes_by_campus_day.items():
            for left_class_id, right_class_id in combinations(sorted(class_ids), 2):
                left_room = context.class_room_variables[(campus_id, target_date, left_class_id)]
                right_room = context.class_room_variables[(campus_id, target_date, right_class_id)]
                same_room = context.model.new_bool_var(
                    f"same_room__{campus_id}__{target_date.isoformat()}__"
                    f"{left_class_id}__{right_class_id}"
                )
                context.model.add(left_room == right_room).only_enforce_if(same_room)
                context.model.add(left_room != right_room).only_enforce_if(same_room.negated())
                for left_period_id, right_period_id in pairwise(ordered_period_ids):
                    for first_class_id, second_class_id in (
                        (left_class_id, right_class_id),
                        (right_class_id, left_class_id),
                    ):
                        if (first_class_id, second_class_id) in excluded_transitions:
                            continue
                        first_slot = context.class_slot_variables.get(
                            (
                                campus_id,
                                target_date,
                                first_class_id,
                                left_period_id,
                            )
                        )
                        second_slot = context.class_slot_variables.get(
                            (
                                campus_id,
                                target_date,
                                second_class_id,
                                right_period_id,
                            )
                        )
                        if first_slot is None or second_slot is None:
                            continue
                        penalty = context.model.new_bool_var(
                            f"room_change_without_gap__{campus_id}__"
                            f"{target_date.isoformat()}__{left_period_id}__"
                            f"{first_class_id}__{second_class_id}"
                        )
                        context.model.add_bool_and(
                            [first_slot, second_slot, same_room]
                        ).only_enforce_if(penalty)
                        context.model.add_bool_or(
                            [
                                first_slot.negated(),
                                second_slot.negated(),
                                same_room.negated(),
                                penalty,
                            ]
                        )
                        context.penalty_terms_by_priority.setdefault(self.priority, []).append(
                            penalty
                        )
        context.applied_rule_ids.append(self.rule_id)


class RoomPriorityPreferenceConstraint:
    """S19: prefer higher-priority rooms for each scheduled lesson."""

    rule_id = "S19"
    priority = 10
    optimization_scope = "room"

    def apply(self, context: SolverContext) -> None:
        for (campus_id, target_date, class_id), room in context.class_room_variables.items():
            priorities = context.room_priorities_by_campus.get(campus_id, ())
            if not priorities:
                continue
            highest_priority = max(priorities)
            for room_index, room_priority in enumerate(priorities):
                priority_gap = highest_priority - room_priority
                if priority_gap == 0:
                    continue
                uses_room = context.model.new_bool_var(
                    f"uses_room__{campus_id}__{target_date.isoformat()}__{class_id}__{room_index}"
                )
                context.model.add(room == room_index).only_enforce_if(uses_room)
                context.model.add(room != room_index).only_enforce_if(uses_room.negated())
                for period_id in context.period_orders:
                    slot = context.class_slot_variables.get(
                        (campus_id, target_date, class_id, period_id)
                    )
                    if slot is None:
                        continue
                    low_priority_lesson = context.model.new_bool_var(
                        f"room_priority_usage__{campus_id}__{target_date.isoformat()}__"
                        f"{class_id}__{period_id}__{room_index}"
                    )
                    context.model.add_bool_and([slot, uses_room]).only_enforce_if(
                        low_priority_lesson
                    )
                    context.model.add_bool_or(
                        [slot.negated(), uses_room.negated(), low_priority_lesson]
                    )
                    penalty = context.model.new_int_var(
                        0,
                        priority_gap,
                        f"room_priority_penalty__{campus_id}__"
                        f"{target_date.isoformat()}__{class_id}__{period_id}__{room_index}",
                    )
                    context.model.add(penalty == priority_gap * low_priority_lesson)
                    context.penalty_terms_by_priority.setdefault(self.priority, []).append(penalty)
        context.applied_rule_ids.append(self.rule_id)


class HomeroomBoundarySlotPreferenceConstraint:
    """S20: prefer the homeroom lesson at the class day's first and last slot."""

    rule_id = "S20"
    priority = 35
    optimization_scope = "assignment"

    def apply(self, context: SolverContext) -> None:
        eligible_by_rule_date_period: dict[
            tuple[str, str, date, str],
            list[cp_model.IntVar],
        ] = defaultdict(list)
        rules_by_class = defaultdict(list)
        for rule in context.homeroom_boundary_rules:
            rules_by_class[rule.class_id].append(rule)
        for candidate in context.candidates:
            for rule in rules_by_class[candidate.class_id]:
                if (
                    rule.start_date <= candidate.target_date <= rule.end_date
                    and candidate.requirement_id in rule.eligible_requirement_ids
                ):
                    eligible_by_rule_date_period[
                        (
                            rule.source_rule_id,
                            rule.class_id,
                            candidate.target_date,
                            candidate.period_id,
                        )
                    ].append(context.assignment_variables[candidate.candidate_id])

        ordered_period_ids = tuple(
            period_id
            for period_id, _ in sorted(context.period_orders.items(), key=lambda item: item[1])
        )
        penalty_groups = context.penalty_term_groups_by_priority.setdefault(self.priority, {})
        for rule in context.homeroom_boundary_rules:
            target_dates = [
                target_date
                for target_date in context.calendar_dates
                if (rule.source_rule_id, rule.class_id, target_date)
                in context.homeroom_attendance_variables
            ]
            attendance_variables = {
                target_date: context.homeroom_attendance_variables[
                    (rule.source_rule_id, rule.class_id, target_date)
                ]
                for target_date in target_dates
            }
            first_boundaries = self._add_boundary_date_variables(
                context,
                rule.source_rule_id,
                rule.class_id,
                target_dates,
                attendance_variables,
                "first",
            )
            reversed_dates = list(reversed(target_dates))
            last_boundaries = self._add_boundary_date_variables(
                context,
                rule.source_rule_id,
                rule.class_id,
                reversed_dates,
                attendance_variables,
                "last",
            )
            if first_boundaries:
                context.model.add_exactly_one(first_boundaries)
                context.model.add_exactly_one(last_boundaries)
            for target_date, boundary in zip(target_dates, first_boundaries, strict=True):
                context.homeroom_first_date_variables[
                    (rule.source_rule_id, rule.class_id, target_date)
                ] = boundary
            for target_date, boundary in zip(reversed_dates, last_boundaries, strict=True):
                context.homeroom_last_date_variables[
                    (rule.source_rule_id, rule.class_id, target_date)
                ] = boundary

            for target_date in context.calendar_dates:
                key = (rule.source_rule_id, rule.class_id, target_date)
                first_boundary = context.homeroom_first_date_variables.get(key)
                last_boundary = context.homeroom_last_date_variables.get(key)
                if first_boundary is None or last_boundary is None:
                    continue
                slots = [
                    context.class_slot_variables.get(
                        (rule.campus_id, target_date, rule.class_id, period_id)
                    )
                    for period_id in ordered_period_ids
                ]
                first_slots = self._add_edge_slot_variables(
                    context,
                    rule.source_rule_id,
                    rule.class_id,
                    target_date,
                    ordered_period_ids,
                    slots,
                    "first",
                )
                last_slots_reversed = self._add_edge_slot_variables(
                    context,
                    rule.source_rule_id,
                    rule.class_id,
                    target_date,
                    tuple(reversed(ordered_period_ids)),
                    list(reversed(slots)),
                    "last",
                )
                last_slots = list(reversed(last_slots_reversed))
                for period_id, first_slot, last_slot in zip(
                    ordered_period_ids,
                    first_slots,
                    last_slots,
                    strict=True,
                ):
                    eligible_variables = eligible_by_rule_date_period.get(
                        (rule.source_rule_id, rule.class_id, target_date, period_id),
                        (),
                    )
                    eligible = context.model.new_bool_var(
                        f"s20_eligible__{rule.source_rule_id}__{rule.class_id}__"
                        f"{target_date.isoformat()}__{period_id}"
                    )
                    if eligible_variables:
                        context.model.add_max_equality(eligible, eligible_variables)
                    else:
                        context.model.add(eligible == 0)
                    for boundary_name, boundary, edge_slot in (
                        ("first", first_boundary, first_slot),
                        ("last", last_boundary, last_slot),
                    ):
                        penalty = context.model.new_bool_var(
                            f"s20_{boundary_name}__{rule.source_rule_id}__{rule.class_id}__"
                            f"{target_date.isoformat()}__{period_id}"
                        )
                        context.model.add(penalty <= boundary)
                        context.model.add(penalty <= edge_slot)
                        context.model.add(penalty + eligible <= 1)
                        context.model.add(penalty >= boundary + edge_slot - eligible - 1)
                        context.penalty_terms_by_priority.setdefault(self.priority, []).append(
                            penalty
                        )
                        penalty_groups.setdefault((rule.source_rule_id, rule.class_id), []).append(
                            penalty
                        )
        context.applied_rule_ids.append(self.rule_id)

    def _add_boundary_date_variables(
        self,
        context: SolverContext,
        source_rule_id: str,
        class_id: str,
        ordered_dates: list[date],
        attendance_variables: dict[date, cp_model.IntVar],
        boundary_name: str,
    ) -> list[cp_model.IntVar]:
        boundary_variables: list[cp_model.IntVar] = []
        attendance_seen: cp_model.IntVar | None = None
        for date_index, target_date in enumerate(ordered_dates):
            attendance = attendance_variables[target_date]
            boundary = context.model.new_bool_var(
                f"s20_{boundary_name}_date__{source_rule_id}__{class_id}__{target_date.isoformat()}"
            )
            if attendance_seen is None:
                context.model.add(boundary == attendance)
                attendance_seen = attendance
            else:
                context.model.add(boundary <= attendance)
                context.model.add(boundary + attendance_seen <= 1)
                context.model.add(boundary >= attendance - attendance_seen)
                next_attendance_seen = context.model.new_bool_var(
                    f"s20_{boundary_name}_date_seen__{source_rule_id}__{class_id}__{date_index}"
                )
                context.model.add_max_equality(
                    next_attendance_seen,
                    [attendance_seen, attendance],
                )
                attendance_seen = next_attendance_seen
            boundary_variables.append(boundary)
        return boundary_variables

    def _add_edge_slot_variables(
        self,
        context: SolverContext,
        source_rule_id: str,
        class_id: str,
        target_date: date,
        ordered_period_ids: tuple[str, ...],
        slots: list[cp_model.IntVar | None],
        edge_name: str,
    ) -> list[cp_model.IntVar]:
        edge_variables: list[cp_model.IntVar] = []
        seen: cp_model.IntVar | None = None
        for index, (period_id, slot) in enumerate(zip(ordered_period_ids, slots, strict=True)):
            edge = context.model.new_bool_var(
                f"s20_{edge_name}_slot__{source_rule_id}__{class_id}__"
                f"{target_date.isoformat()}__{period_id}"
            )
            if slot is None:
                context.model.add(edge == 0)
                edge_variables.append(edge)
                continue
            if seen is None:
                context.model.add(edge == slot)
                seen = slot
            else:
                context.model.add(edge <= slot)
                context.model.add(edge + seen <= 1)
                context.model.add(edge >= slot - seen)
                next_seen = context.model.new_bool_var(
                    f"s20_{edge_name}_seen__{source_rule_id}__{class_id}__"
                    f"{target_date.isoformat()}__{index}"
                )
                context.model.add_max_equality(next_seen, [seen, slot])
                seen = next_seen
            edge_variables.append(edge)
        return edge_variables


class TeacherDayOffDistributionPreferenceConstraint:
    """S21: prefer configured day-off counts while retaining H18 flexibility."""

    rule_id = "S21"
    priority = 34
    optimization_scope = "assignment"

    def apply(self, context: SolverContext) -> None:
        penalty_groups = context.penalty_term_groups_by_priority.setdefault(self.priority, {})
        for rule in context.teacher_day_off_rules:
            if not rule.enabled or rule.preferred_days_off is None:
                continue
            variables = [
                context.teacher_day_off_variables[(rule.teacher_id, target_date)]
                for target_date in rule.eligible_dates
            ]
            deviation = context.model.new_int_var(
                0,
                len(variables),
                f"teacher_day_off_preference__{rule.rule_id}",
            )
            context.model.add_abs_equality(
                deviation,
                sum(variables) - rule.preferred_days_off,
            )
            context.penalty_terms_by_priority.setdefault(self.priority, []).append(deviation)
            penalty_groups.setdefault((rule.rule_id,), []).append(deviation)
        context.applied_rule_ids.append(self.rule_id)


class TeacherCampusTransferGapPreferenceConstraint:
    """S22: prefer two or more empty periods around a same-day campus transfer."""

    rule_id = "S22"
    priority = 33
    optimization_scope = "assignment"

    def apply(self, context: SolverContext) -> None:
        slot_groups: dict[tuple[str, date, str, str], list[cp_model.IntVar]] = defaultdict(list)
        for candidate in context.candidates:
            slot_groups[
                (
                    candidate.teacher_id,
                    candidate.target_date,
                    candidate.campus_id,
                    candidate.period_id,
                )
            ].append(context.assignment_variables[candidate.candidate_id])
        slot_presence: dict[tuple[str, date, str, str], cp_model.IntVar] = {}
        campuses_by_teacher_day: dict[tuple[str, date], set[str]] = defaultdict(set)
        for key, variables in slot_groups.items():
            teacher_id, target_date, campus_id, period_id = key
            presence = context.model.new_bool_var(
                f"s22_teacher_campus_slot__{teacher_id}__{target_date.isoformat()}__"
                f"{campus_id}__{period_id}"
            )
            context.model.add_max_equality(presence, variables)
            slot_presence[key] = presence
            campuses_by_teacher_day[(teacher_id, target_date)].add(campus_id)

        for (teacher_id, target_date), campus_ids in campuses_by_teacher_day.items():
            for left_campus, right_campus in combinations(sorted(campus_ids), 2):
                for left_period, left_order in context.period_orders.items():
                    left = slot_presence.get((teacher_id, target_date, left_campus, left_period))
                    if left is None:
                        continue
                    for right_period, right_order in context.period_orders.items():
                        if abs(right_order - left_order) != 2:
                            continue
                        right = slot_presence.get(
                            (teacher_id, target_date, right_campus, right_period)
                        )
                        if right is None:
                            continue
                        penalty = context.model.new_bool_var(
                            f"s22_transfer_one_gap__{teacher_id}__"
                            f"{target_date.isoformat()}__{left_campus}__{left_period}__"
                            f"{right_campus}__{right_period}"
                        )
                        context.model.add_bool_and([left, right]).only_enforce_if(penalty)
                        context.model.add_bool_or([left.negated(), right.negated(), penalty])
                        context.penalty_terms_by_priority.setdefault(self.priority, []).append(
                            penalty
                        )
        context.applied_rule_ids.append(self.rule_id)


class ClassDailyContiguityPreferenceConstraint:
    """S11: minimize empty periods between one class's first and last lesson."""

    rule_id = "S11"
    priority = 20
    optimization_scope = "assignment"

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
            split = context.model.new_bool_var(
                f"class_day_split__{class_id}__{target_date.isoformat()}"
            )
            split_can_occur = False
            for left_index, middle_index, right_index in combinations(
                range(len(ordered_period_ids)), 3
            ):
                left_slot = slots[left_index]
                right_slot = slots[right_index]
                if left_slot is None or right_slot is None:
                    continue
                split_can_occur = True
                middle_slot = slots[middle_index]
                if middle_slot is None:
                    context.model.add(left_slot + right_slot <= 1 + split)
                else:
                    context.model.add(left_slot + right_slot - middle_slot <= 1 + split)
            if not split_can_occur:
                continue
            context.penalty_terms_by_priority.setdefault(self.priority, []).append(split)
        context.applied_rule_ids.append(self.rule_id)


class ClassSubjectDailyRepeatPreferenceConstraint:
    """S14: minimize same-day lesson pairs per class and subject."""

    rule_id = "S14"
    priority = 30
    optimization_scope = "assignment"

    def apply(self, context: SolverContext) -> None:
        variables_by_class_subject_day: dict[
            tuple[str, str, date],
            list[cp_model.IntVar],
        ] = defaultdict(list)
        requirement_ids_by_class_subject_day: dict[
            tuple[str, str, date],
            set[str],
        ] = defaultdict(set)
        for candidate in context.candidates:
            key = (
                candidate.class_id,
                candidate.subject_id,
                candidate.target_date,
            )
            variables_by_class_subject_day[key].append(
                context.assignment_variables[candidate.candidate_id]
            )
            requirement_ids_by_class_subject_day[key].add(candidate.requirement_id)

        penalty_groups = context.penalty_term_groups_by_priority.setdefault(
            self.priority,
            {},
        )
        for (
            class_id,
            subject_id,
            target_date,
        ), variables in variables_by_class_subject_day.items():
            if len(variables) < 2:
                continue
            class_daily_limit = context.class_daily_limits.get((class_id, target_date))
            requirement_limit = 0
            for requirement_id in requirement_ids_by_class_subject_day[
                (class_id, subject_id, target_date)
            ]:
                required_count = context.required_counts[requirement_id]
                daily_limit = context.requirement_daily_limits[requirement_id]
                requirement_limit += min(
                    required_count,
                    daily_limit if daily_limit is not None else required_count,
                )
            max_daily_lessons = min(len(context.period_orders), requirement_limit)
            if class_daily_limit is not None:
                max_daily_lessons = min(max_daily_lessons, class_daily_limit)
            if max_daily_lessons < 2:
                continue
            for threshold in range(2, max_daily_lessons + 1):
                threshold_reached = context.model.new_bool_var(
                    f"class_subject_daily_repeat_threshold_{threshold}__"
                    f"{class_id}__{subject_id}__{target_date.isoformat()}"
                )
                context.model.add(sum(variables) >= threshold).only_enforce_if(threshold_reached)
                context.model.add(sum(variables) <= threshold - 1).only_enforce_if(
                    threshold_reached.negated()
                )
                penalty = threshold_reached
                if threshold > 2:
                    penalty = context.model.new_int_var(
                        0,
                        threshold - 1,
                        f"class_subject_daily_repeat_penalty_{threshold}__"
                        f"{class_id}__{subject_id}__{target_date.isoformat()}",
                    )
                    context.model.add(penalty == (threshold - 1) * threshold_reached)
                context.penalty_terms_by_priority.setdefault(self.priority, []).append(penalty)
                penalty_groups.setdefault((class_id, subject_id), []).append(penalty)
        context.applied_rule_ids.append(self.rule_id)


class ClassSubjectScheduleBalancePreferenceConstraint:
    """S16: balance each class-subject requirement across its candidate dates."""

    rule_id = "S16"
    priority = 14
    optimization_scope = "assignment"
    _SCORE_SCALE = 1000

    def apply(self, context: SolverContext) -> None:
        variables_by_requirement_day: dict[
            tuple[str, date],
            list[cp_model.IntVar],
        ] = defaultdict(list)
        period_ids_by_requirement_day: dict[tuple[str, date], set[str]] = defaultdict(set)
        class_subject_by_requirement: dict[str, tuple[str, str]] = {}
        for candidate in context.candidates:
            key = (candidate.requirement_id, candidate.target_date)
            variables_by_requirement_day[key].append(
                context.assignment_variables[candidate.candidate_id]
            )
            period_ids_by_requirement_day[key].add(candidate.period_id)
            class_subject_by_requirement[candidate.requirement_id] = (
                candidate.class_id,
                candidate.subject_id,
            )

        penalty_groups = context.penalty_term_groups_by_priority.setdefault(
            self.priority,
            {},
        )
        dates_by_requirement: dict[str, list[date]] = defaultdict(list)
        for requirement_id, target_date in variables_by_requirement_day:
            dates_by_requirement[requirement_id].append(target_date)

        for requirement_id, unsorted_dates in dates_by_requirement.items():
            required_count = context.required_counts[requirement_id]
            dates = sorted(unsorted_dates)
            if required_count <= 1 or len(dates) <= 1:
                continue

            daily_capacities = []
            for target_date in dates:
                capacity = len(period_ids_by_requirement_day[(requirement_id, target_date)])
                requirement_limit = context.requirement_daily_limits[requirement_id]
                if requirement_limit is not None:
                    capacity = min(capacity, requirement_limit)
                class_id, _ = class_subject_by_requirement[requirement_id]
                class_limit = context.class_daily_limits.get((class_id, target_date))
                if class_limit is not None:
                    capacity = min(capacity, class_limit)
                daily_capacities.append(min(capacity, required_count))

            total_capacity = sum(daily_capacities)
            if total_capacity <= required_count:
                continue

            cumulative_capacity = 0
            cumulative_variables: list[cp_model.IntVar] = []
            deviations: list[cp_model.IntVar] = []
            for target_date, daily_capacity in zip(
                dates[:-1],
                daily_capacities[:-1],
                strict=True,
            ):
                cumulative_capacity += daily_capacity
                cumulative_variables.extend(
                    variables_by_requirement_day[(requirement_id, target_date)]
                )
                target_count = (2 * required_count * cumulative_capacity + total_capacity) // (
                    2 * total_capacity
                )
                deviation = context.model.new_int_var(
                    0,
                    required_count,
                    "class_subject_schedule_balance_deviation__"
                    f"{requirement_id}__{target_date.isoformat()}",
                )
                context.model.add_abs_equality(
                    deviation,
                    sum(cumulative_variables) - target_count,
                )
                deviations.append(deviation)

            denominator = required_count * (len(dates) - 1)
            normalized_score = context.model.new_int_var(
                0,
                self._SCORE_SCALE,
                f"class_subject_schedule_balance_score__{requirement_id}",
            )
            scaled_deviation = self._SCORE_SCALE * sum(deviations)
            context.model.add(normalized_score * denominator >= scaled_deviation)
            context.model.add(normalized_score * denominator <= scaled_deviation + denominator - 1)
            context.penalty_terms_by_priority.setdefault(self.priority, []).append(normalized_score)
            penalty_groups.setdefault(
                class_subject_by_requirement[requirement_id],
                [],
            ).append(normalized_score)
        context.applied_rule_ids.append(self.rule_id)


class ClassSubjectDoubleThenNextDayPreferenceConstraint:
    """S15: minimize a subject recurring the day after a double lesson."""

    rule_id = "S15"
    priority = 25
    optimization_scope = "assignment"

    def apply(self, context: SolverContext) -> None:
        variables_by_class_subject_day: dict[
            tuple[str, str, date],
            list[cp_model.IntVar],
        ] = defaultdict(list)
        for candidate in context.candidates:
            variables_by_class_subject_day[
                (
                    candidate.class_id,
                    candidate.subject_id,
                    candidate.target_date,
                )
            ].append(context.assignment_variables[candidate.candidate_id])

        presence_by_class_subject_day: dict[
            tuple[str, str, date],
            cp_model.IntVar,
        ] = {}
        for (
            class_id,
            subject_id,
            target_date,
        ), variables in variables_by_class_subject_day.items():
            presence = context.model.new_bool_var(
                f"class_subject_day_presence__{class_id}__{subject_id}__{target_date.isoformat()}"
            )
            context.model.add_max_equality(presence, variables)
            presence_by_class_subject_day[(class_id, subject_id, target_date)] = presence

        for (
            class_id,
            subject_id,
            target_date,
        ), variables in variables_by_class_subject_day.items():
            next_day_presence = presence_by_class_subject_day.get(
                (class_id, subject_id, target_date + timedelta(days=1))
            )
            if len(variables) < 2 or next_day_presence is None:
                continue
            repeated_day = context.model.new_bool_var(
                f"class_subject_double_day__{class_id}__{subject_id}__{target_date.isoformat()}"
            )
            context.model.add(sum(variables) >= 2).only_enforce_if(repeated_day)
            context.model.add(sum(variables) <= 1).only_enforce_if(repeated_day.negated())
            penalty = context.model.new_bool_var(
                "class_subject_double_then_next_day__"
                f"{class_id}__{subject_id}__{target_date.isoformat()}"
            )
            context.model.add_bool_and([repeated_day, next_day_presence]).only_enforce_if(penalty)
            context.model.add_bool_or(
                [repeated_day.negated(), next_day_presence.negated(), penalty]
            )
            context.penalty_terms_by_priority.setdefault(self.priority, []).append(penalty)
        context.applied_rule_ids.append(self.rule_id)


class ClassConsecutiveAttendancePreferenceConstraint:
    """S18: progressively penalize attendance beyond each class's preferred streak."""

    rule_id = "S18"
    priority = 18
    optimization_scope = "assignment"

    def apply(self, context: SolverContext) -> None:
        preference_limits = (
            context.attendance_group_preference_limits
            if context.attendance_group_class_ids
            else context.class_attendance_preference_limits
        )
        group_ids = {
            group_id for (group_id, _), limit in preference_limits.items() if limit is not None
        }
        ensure_attendance_group_day_variables(context)
        penalty_groups = context.penalty_term_groups_by_priority.setdefault(
            self.priority,
            {},
        )
        for group_id in group_ids:
            for end_index, end_date in enumerate(context.calendar_dates):
                preferred_limit = preference_limits.get((group_id, end_date))
                if preferred_limit is None:
                    continue
                for streak_length in range(preferred_limit + 1, end_index + 2):
                    window = context.calendar_dates[end_index - streak_length + 1 : end_index + 1]
                    if any(right - left != timedelta(days=1) for left, right in pairwise(window)):
                        continue
                    threshold_reached = context.model.new_bool_var(
                        "class_attendance_preference__"
                        f"{group_id}__{end_date.isoformat()}__{streak_length}"
                    )
                    day_variables = [
                        context.class_day_variables[(group_id, target_date)]
                        for target_date in window
                    ]
                    context.model.add_bool_and(day_variables).only_enforce_if(threshold_reached)
                    context.model.add_bool_or(
                        [variable.negated() for variable in day_variables]
                    ).only_enforce_if(threshold_reached.negated())
                    context.penalty_terms_by_priority.setdefault(self.priority, []).append(
                        threshold_reached
                    )
                    penalty_groups.setdefault((group_id,), []).append(threshold_reached)
        context.applied_rule_ids.append(self.rule_id)


class ClassSingleLessonDayPreferenceConstraint:
    """S12: minimize one-lesson class days, excluding H23 second and single-subject classes."""

    rule_id = "S12"
    priority = 15
    optimization_scope = "assignment"

    def apply(self, context: SolverContext) -> None:
        second_class_ids = {
            rule.second_class_id for rule in context.class_pair_overlap_rules if rule.enabled
        }
        ordered_period_ids = tuple(
            period_id
            for period_id, _ in sorted(
                context.period_orders.items(),
                key=lambda item: item[1],
            )
        )
        excluded_class_ids = second_class_ids | context.single_subject_class_ids
        for campus_id, target_date, class_id in context.class_room_variables:
            if class_id in excluded_class_ids:
                continue
            slots = []
            for period_id in ordered_period_ids:
                slot = context.class_slot_variables.get(
                    (campus_id, target_date, class_id, period_id)
                )
                if slot is not None:
                    slots.append(slot)
            single_lesson_day = context.model.new_bool_var(
                f"class_single_lesson_day__{class_id}__{target_date.isoformat()}"
            )
            context.model.add(sum(slots) == 1).only_enforce_if(single_lesson_day)
            context.model.add(sum(slots) != 1).only_enforce_if(single_lesson_day.negated())
            context.penalty_terms_by_priority.setdefault(self.priority, []).append(
                single_lesson_day
            )
        context.applied_rule_ids.append(self.rule_id)


class ClassSubjectConsecutiveRepeatPreferenceConstraint:
    """S13: minimize adjacent lessons of one subject for one class."""

    rule_id = "S13"
    priority = 12
    optimization_scope = "assignment"

    def apply(self, context: SolverContext) -> None:
        variables_by_class_subject_slot: dict[
            tuple[str, str, date, str],
            list[cp_model.IntVar],
        ] = defaultdict(list)
        for candidate in context.candidates:
            variables_by_class_subject_slot[
                (
                    candidate.class_id,
                    candidate.subject_id,
                    candidate.target_date,
                    candidate.period_id,
                )
            ].append(context.assignment_variables[candidate.candidate_id])

        presence_by_class_subject_slot: dict[
            tuple[str, str, date, str],
            cp_model.IntVar,
        ] = {}
        for key, variables in variables_by_class_subject_slot.items():
            if len(variables) == 1:
                presence_by_class_subject_slot[key] = variables[0]
                continue
            presence = context.model.new_bool_var(
                f"class_subject_slot__{key[0]}__{key[1]}__{key[2].isoformat()}__{key[3]}"
            )
            context.model.add_max_equality(presence, variables)
            presence_by_class_subject_slot[key] = presence

        ordered_period_ids = tuple(
            period_id
            for period_id, _ in sorted(
                context.period_orders.items(),
                key=lambda item: item[1],
            )
        )
        class_subject_days = {
            (class_id, subject_id, target_date)
            for class_id, subject_id, target_date, _ in presence_by_class_subject_slot
        }
        for class_id, subject_id, target_date in class_subject_days:
            for left_period_id, right_period_id in pairwise(ordered_period_ids):
                left_slot = presence_by_class_subject_slot.get(
                    (class_id, subject_id, target_date, left_period_id)
                )
                right_slot = presence_by_class_subject_slot.get(
                    (class_id, subject_id, target_date, right_period_id)
                )
                if left_slot is None or right_slot is None:
                    continue
                penalty = context.model.new_bool_var(
                    "class_subject_consecutive_repeat__"
                    f"{class_id}__{subject_id}__{target_date.isoformat()}__"
                    f"{left_period_id}"
                )
                context.model.add_bool_and([left_slot, right_slot]).only_enforce_if(penalty)
                context.model.add_bool_or([left_slot.negated(), right_slot.negated(), penalty])
                context.penalty_terms_by_priority.setdefault(self.priority, []).append(penalty)
        context.applied_rule_ids.append(self.rule_id)


class LessonCountInScopePreferenceConstraint:
    """S17: minimize deviation from configured lesson counts in slot scopes."""

    rule_id = "S17"
    priority = 11
    optimization_scope = "assignment"

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

        penalty_groups = context.penalty_term_groups_by_priority.setdefault(
            self.priority,
            {},
        )
        for rule in context.lesson_count_preference_rules:
            variables = [
                variable
                for target_date, period_id in rule.target_slots
                for variable in variables_by_requirement_and_slot[
                    (rule.requirement_id, target_date, period_id)
                ]
            ]
            deviation = context.model.new_int_var(
                0,
                context.required_counts[rule.requirement_id],
                f"lesson_count_preference_deviation__{rule.rule_id}",
            )
            context.model.add_abs_equality(
                deviation,
                sum(variables) - rule.preferred_periods,
            )
            context.penalty_terms_by_priority.setdefault(self.priority, []).append(deviation)
            penalty_groups.setdefault((rule.rule_id,), []).append(deviation)
        context.applied_rule_ids.append(self.rule_id)


DEFAULT_SOFT_CONSTRAINTS = (
    HomeroomBoundarySlotPreferenceConstraint(),
    TeacherDayOffDistributionPreferenceConstraint(),
    TeacherCampusTransferGapPreferenceConstraint(),
    RoomChangeGapPreferenceConstraint(),
    RoomPriorityPreferenceConstraint(),
    ClassDailyContiguityPreferenceConstraint(),
    ClassSubjectDailyRepeatPreferenceConstraint(),
    ClassSubjectScheduleBalancePreferenceConstraint(),
    ClassSubjectDoubleThenNextDayPreferenceConstraint(),
    ClassConsecutiveAttendancePreferenceConstraint(),
    ClassSingleLessonDayPreferenceConstraint(),
    ClassSubjectConsecutiveRepeatPreferenceConstraint(),
    LessonCountInScopePreferenceConstraint(),
)

SoftConstraint = (
    HomeroomBoundarySlotPreferenceConstraint
    | TeacherDayOffDistributionPreferenceConstraint
    | TeacherCampusTransferGapPreferenceConstraint
    | RoomChangeGapPreferenceConstraint
    | RoomPriorityPreferenceConstraint
    | ClassDailyContiguityPreferenceConstraint
    | ClassSubjectDailyRepeatPreferenceConstraint
    | ClassSubjectScheduleBalancePreferenceConstraint
    | ClassSubjectDoubleThenNextDayPreferenceConstraint
    | ClassConsecutiveAttendancePreferenceConstraint
    | ClassSingleLessonDayPreferenceConstraint
    | ClassSubjectConsecutiveRepeatPreferenceConstraint
    | LessonCountInScopePreferenceConstraint
)

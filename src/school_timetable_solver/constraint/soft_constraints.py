from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from itertools import combinations, pairwise

from ortools.sat.python import cp_model

from school_timetable_solver.constraint.solver_context import SolverContext


class RoomChangeGapPreferenceConstraint:
    """S10: minimize adjacent-period changes between different classes in one room."""

    rule_id = "S10"
    priority = 10
    optimization_scope = "room"

    def apply(self, context: SolverContext) -> None:
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


class ClassSingleLessonDayPreferenceConstraint:
    """S12: minimize class days containing exactly one lesson."""

    rule_id = "S12"
    priority = 15
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


DEFAULT_SOFT_CONSTRAINTS = (
    RoomChangeGapPreferenceConstraint(),
    ClassDailyContiguityPreferenceConstraint(),
    ClassSubjectDailyRepeatPreferenceConstraint(),
    ClassSubjectScheduleBalancePreferenceConstraint(),
    ClassSubjectDoubleThenNextDayPreferenceConstraint(),
    ClassSingleLessonDayPreferenceConstraint(),
    ClassSubjectConsecutiveRepeatPreferenceConstraint(),
)

SoftConstraint = (
    RoomChangeGapPreferenceConstraint
    | ClassDailyContiguityPreferenceConstraint
    | ClassSubjectDailyRepeatPreferenceConstraint
    | ClassSubjectScheduleBalancePreferenceConstraint
    | ClassSubjectDoubleThenNextDayPreferenceConstraint
    | ClassSingleLessonDayPreferenceConstraint
    | ClassSubjectConsecutiveRepeatPreferenceConstraint
)

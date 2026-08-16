from __future__ import annotations

from collections import defaultdict
from datetime import date
from itertools import combinations, pairwise

from ortools.sat.python import cp_model

from school_timetable_solver.constraint.hard_constraints import ClassPairOverlapConstraint
from school_timetable_solver.constraint.soft_constraints import (
    ClassSingleLessonDayPreferenceConstraint,
    ClassSubjectScheduleBalancePreferenceConstraint,
    RoomChangeGapPreferenceConstraint,
)
from school_timetable_solver.constraint.solver_context import SolverContext


def _first_classes_by_second(context: SolverContext) -> dict[str, tuple[str, ...]]:
    grouped: dict[str, set[str]] = defaultdict(set)
    for rule in context.class_pair_overlap_rules:
        if rule.enabled:
            grouped[rule.second_class_id].add(rule.first_class_id)
    return {second: tuple(sorted(firsts)) for second, firsts in grouped.items()}


class ClassSuccessorConstraint(ClassPairOverlapConstraint):
    """H23: place a second class immediately after one configured first class."""

    rule_id = "H23"

    def apply(self, context: SolverContext) -> None:
        first_classes_by_second = _first_classes_by_second(context)
        ordered_period_ids = tuple(
            period_id
            for period_id, _ in sorted(context.period_orders.items(), key=lambda item: item[1])
        )
        classes_by_campus_day: dict[tuple[str, date], set[str]] = defaultdict(set)
        for campus_id, target_date, class_id in context.class_room_variables:
            classes_by_campus_day[(campus_id, target_date)].add(class_id)

        for (campus_id, target_date), class_ids in classes_by_campus_day.items():
            for second_class_id, first_class_ids in first_classes_by_second.items():
                if second_class_id not in class_ids:
                    continue
                second_slots = [
                    context.class_slot_variables.get(
                        (campus_id, target_date, second_class_id, period_id)
                    )
                    for period_id in ordered_period_ids
                ]
                second_present_slots = [slot for slot in second_slots if slot is not None]
                if not second_present_slots:
                    continue
                second_day = context.model.new_bool_var(
                    f"h23_second_day__{second_class_id}__{target_date.isoformat()}"
                )
                context.model.add_max_equality(second_day, second_present_slots)

                matches: list[cp_model.IntVar] = []
                for first_class_id in first_class_ids:
                    if first_class_id not in class_ids:
                        continue
                    first_room = context.class_room_variables[
                        (campus_id, target_date, first_class_id)
                    ]
                    second_room = context.class_room_variables[
                        (campus_id, target_date, second_class_id)
                    ]
                    first_slots = [
                        context.class_slot_variables.get(
                            (campus_id, target_date, first_class_id, period_id)
                        )
                        for period_id in ordered_period_ids
                    ]
                    for index in range(len(ordered_period_ids) - 1):
                        first_slot = first_slots[index]
                        second_slot = second_slots[index + 1]
                        if first_slot is None or second_slot is None:
                            continue
                        match = context.model.new_bool_var(
                            f"h23_match__{first_class_id}__{second_class_id}__"
                            f"{target_date.isoformat()}__{ordered_period_ids[index]}"
                        )
                        context.model.add(match <= first_slot)
                        context.model.add(match <= second_slot)
                        for later_first in first_slots[index + 1 :]:
                            if later_first is not None:
                                context.model.add(match + later_first <= 1)
                        for earlier_second in second_slots[: index + 1]:
                            if earlier_second is not None:
                                context.model.add(match + earlier_second <= 1)
                        context.model.add(first_room == second_room).only_enforce_if(match)
                        matches.append(match)

                if matches:
                    context.model.add(sum(matches) == second_day)
                else:
                    context.model.add(second_day == 0)
        context.applied_rule_ids.append(self.rule_id)


class ClassSuccessorDayConstraint(ClassPairOverlapConstraint):
    """H23 day-level relaxation: a second-class day requires any first-class day."""

    rule_id = "H23"

    def apply(self, context: SolverContext) -> None:
        first_classes_by_second = _first_classes_by_second(context)
        variables_by_class_day: dict[tuple[str, date], list[cp_model.IntVar]] = defaultdict(list)
        for candidate in context.candidates:
            variables_by_class_day[(candidate.class_id, candidate.target_date)].append(
                context.assignment_variables[candidate.candidate_id]
            )

        for second_class_id, first_class_ids in first_classes_by_second.items():
            for target_date in context.calendar_dates:
                second_variables = variables_by_class_day.get((second_class_id, target_date), ())
                if not second_variables:
                    continue
                second_day = context.model.new_bool_var(
                    f"h23_master_second_day__{second_class_id}__{target_date.isoformat()}"
                )
                context.model.add_max_equality(second_day, second_variables)
                first_days: list[cp_model.IntVar] = []
                for first_class_id in first_class_ids:
                    first_variables = variables_by_class_day.get((first_class_id, target_date), ())
                    if not first_variables:
                        continue
                    first_day = context.model.new_bool_var(
                        f"h23_master_first_day__{first_class_id}__{second_class_id}__"
                        f"{target_date.isoformat()}"
                    )
                    context.model.add_max_equality(first_day, first_variables)
                    first_days.append(first_day)
                if first_days:
                    context.model.add(second_day <= sum(first_days))
                else:
                    context.model.add(second_day == 0)
        context.applied_rule_ids.append(self.rule_id)


class SuccessorAwareRoomChangeGapPreferenceConstraint(RoomChangeGapPreferenceConstraint):
    """S10: keep H23 first->second transitions out of the room-change penalty."""

    def apply(self, context: SolverContext) -> None:
        excluded_transitions = {
            (rule.first_class_id, rule.second_class_id)
            for rule in context.class_pair_overlap_rules
            if rule.enabled
        }
        ordered_period_ids = tuple(
            period_id
            for period_id, _ in sorted(context.period_orders.items(), key=lambda item: item[1])
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
                            (campus_id, target_date, first_class_id, left_period_id)
                        )
                        second_slot = context.class_slot_variables.get(
                            (campus_id, target_date, second_class_id, right_period_id)
                        )
                        if first_slot is None or second_slot is None:
                            continue
                        penalty = context.model.new_bool_var(
                            f"room_change_without_gap__{campus_id}__{target_date.isoformat()}__"
                            f"{left_period_id}__{first_class_id}__{second_class_id}"
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


class SuccessorAwareSingleLessonDayPreferenceConstraint(
    ClassSingleLessonDayPreferenceConstraint
):
    """S12: configured second classes are exempt from the single-lesson-day penalty."""

    def apply(self, context: SolverContext) -> None:
        second_class_ids = {
            rule.second_class_id for rule in context.class_pair_overlap_rules if rule.enabled
        }
        ordered_period_ids = tuple(
            period_id
            for period_id, _ in sorted(context.period_orders.items(), key=lambda item: item[1])
        )
        for campus_id, target_date, class_id in context.class_room_variables:
            if class_id in second_class_ids:
                continue
            slots = [
                slot
                for period_id in ordered_period_ids
                if (
                    slot := context.class_slot_variables.get(
                        (campus_id, target_date, class_id, period_id)
                    )
                )
                is not None
            ]
            single_lesson_day = context.model.new_bool_var(
                f"class_single_lesson_day__{class_id}__{target_date.isoformat()}"
            )
            context.model.add(sum(slots) == 1).only_enforce_if(single_lesson_day)
            context.model.add(sum(slots) != 1).only_enforce_if(single_lesson_day.negated())
            context.penalty_terms_by_priority.setdefault(self.priority, []).append(single_lesson_day)
        context.applied_rule_ids.append(self.rule_id)


class SuccessorAwareScheduleBalancePreferenceConstraint(
    ClassSubjectScheduleBalancePreferenceConstraint
):
    """S16: ignore second-class candidate slots with no possible preceding first slot."""

    def apply(self, context: SolverContext) -> None:
        first_classes_by_second = _first_classes_by_second(context)
        period_id_by_order = {order: period_id for period_id, order in context.period_orders.items()}
        available_class_slots = {
            (candidate.class_id, candidate.target_date, candidate.period_id)
            for candidate in context.candidates
        }
        viable_candidate_ids: set[str] = set()
        for candidate in context.candidates:
            first_class_ids = first_classes_by_second.get(candidate.class_id)
            if first_class_ids is None:
                viable_candidate_ids.add(candidate.candidate_id)
                continue
            previous_period_id = period_id_by_order.get(context.period_orders[candidate.period_id] - 1)
            if previous_period_id is None:
                continue
            if any(
                (first_class_id, candidate.target_date, previous_period_id)
                in available_class_slots
                for first_class_id in first_class_ids
            ):
                viable_candidate_ids.add(candidate.candidate_id)

        variables_by_requirement_day: dict[tuple[str, date], list[cp_model.IntVar]] = defaultdict(list)
        period_ids_by_requirement_day: dict[tuple[str, date], set[str]] = defaultdict(set)
        class_subject_by_requirement: dict[str, tuple[str, str]] = {}
        for candidate in context.candidates:
            if candidate.candidate_id not in viable_candidate_ids:
                continue
            key = (candidate.requirement_id, candidate.target_date)
            variables_by_requirement_day[key].append(
                context.assignment_variables[candidate.candidate_id]
            )
            period_ids_by_requirement_day[key].add(candidate.period_id)
            class_subject_by_requirement[candidate.requirement_id] = (
                candidate.class_id,
                candidate.subject_id,
            )

        penalty_groups = context.penalty_term_groups_by_priority.setdefault(self.priority, {})
        dates_by_requirement: dict[str, list[date]] = defaultdict(list)
        for requirement_id, target_date in variables_by_requirement_day:
            dates_by_requirement[requirement_id].append(target_date)

        for requirement_id, unsorted_dates in dates_by_requirement.items():
            required_count = context.required_counts[requirement_id]
            dates = sorted(unsorted_dates)
            if required_count <= 1 or len(dates) <= 1:
                continue
            daily_capacities: list[int] = []
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
            for target_date, daily_capacity in zip(dates[:-1], daily_capacities[:-1], strict=True):
                cumulative_capacity += daily_capacity
                cumulative_variables.extend(variables_by_requirement_day[(requirement_id, target_date)])
                target_count = (
                    2 * required_count * cumulative_capacity + total_capacity
                ) // (2 * total_capacity)
                deviation = context.model.new_int_var(
                    0,
                    required_count,
                    f"class_subject_schedule_balance_deviation__{requirement_id}__"
                    f"{target_date.isoformat()}",
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
            penalty_groups.setdefault(class_subject_by_requirement[requirement_id], []).append(
                normalized_score
            )
        context.applied_rule_ids.append(self.rule_id)

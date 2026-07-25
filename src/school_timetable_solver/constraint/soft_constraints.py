from __future__ import annotations

from collections import defaultdict
from datetime import date
from itertools import combinations, pairwise

from school_timetable_solver.constraint.solver_context import SolverContext


class RoomChangeGapPreferenceConstraint:
    """S10: minimize adjacent-period changes between different classes in one room."""

    rule_id = "S10"
    priority = 10

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


DEFAULT_SOFT_CONSTRAINTS = (
    RoomChangeGapPreferenceConstraint(),
    ClassDailyContiguityPreferenceConstraint(),
)

SoftConstraint = RoomChangeGapPreferenceConstraint | ClassDailyContiguityPreferenceConstraint

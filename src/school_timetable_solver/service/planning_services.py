from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from datetime import date

from school_timetable_solver.model.input_models import InputDataModel, PlacementRuleModel
from school_timetable_solver.model.master_models import ClassModel, RoomModel, TeacherModel
from school_timetable_solver.model.solver_models import (
    CandidateBuildResultModel,
    CandidateRejectionSummaryModel,
    CandidateSlotModel,
    EffectiveClassDateRuleModel,
    EffectiveTeacherDateRuleModel,
    ResolvedRuleSetModel,
)


class RuleResolverService:
    """Resolve data-driven class and teacher policies for every calendar date."""

    def execute(self, input_data: InputDataModel) -> ResolvedRuleSetModel:
        all_period_ids = tuple(
            item.period_id for item in sorted(input_data.periods, key=lambda item: item.sort_order)
        )
        campuses = {item.campus_id: item for item in input_data.campuses}
        class_rules: list[EffectiveClassDateRuleModel] = []
        teacher_rules: list[EffectiveTeacherDateRuleModel] = []
        for class_model in input_data.classes:
            campus = campuses[class_model.campus_id]
            initial_limit = (
                class_model.daily_hard_limit
                if class_model.daily_hard_limit is not None
                else campus.standard_class_daily_limit
            )
            for calendar_day in input_data.calendar_days:
                applicable = [
                    rule
                    for rule in input_data.placement_rules
                    if self._matches_class(
                        rule, class_model, calendar_day.target_date, calendar_day.weekday
                    )
                ]
                allowed = set(class_model.default_allowed_periods or all_period_ids)
                daily_limit = initial_limit
                attendance_limit = class_model.attendance_streak_limit
                applied: list[str] = []
                for rule in sorted(applicable, key=lambda item: item.priority):
                    if rule.allowed_period_ids:
                        if rule.constraint_type == "override":
                            allowed = set(rule.allowed_period_ids)
                        else:
                            allowed.intersection_update(rule.allowed_period_ids)
                    allowed.difference_update(rule.prohibited_period_ids)
                    daily_limit = self._resolve_limit(
                        daily_limit, rule.daily_hard_limit, rule.constraint_type
                    )
                    attendance_limit = self._resolve_limit(
                        attendance_limit, rule.attendance_streak_limit, rule.constraint_type
                    )
                    applied.append(rule.rule_id)
                class_rules.append(
                    EffectiveClassDateRuleModel(
                        class_id=class_model.class_id,
                        target_date=calendar_day.target_date,
                        allowed_period_ids=tuple(
                            period_id for period_id in all_period_ids if period_id in allowed
                        ),
                        daily_hard_limit=daily_limit,
                        attendance_streak_limit=attendance_limit,
                        applied_rule_ids=tuple(applied),
                    )
                )
        for teacher in input_data.teachers:
            campus_limit = None
            if teacher.home_campus_id is not None and teacher.home_campus_id in campuses:
                campus_limit = campuses[teacher.home_campus_id].standard_teacher_daily_limit
            for calendar_day in input_data.calendar_days:
                applicable = [
                    rule
                    for rule in input_data.placement_rules
                    if self._matches_teacher(
                        rule, teacher, calendar_day.target_date, calendar_day.weekday
                    )
                ]
                daily_limit = (
                    teacher.daily_hard_limit
                    if teacher.daily_hard_limit is not None
                    else campus_limit
                )
                consecutive_limit = teacher.consecutive_hard_limit
                transfer_gap = teacher.required_transfer_gap
                applied = []
                for rule in sorted(applicable, key=lambda item: item.priority):
                    daily_limit = self._resolve_limit(
                        daily_limit, rule.daily_hard_limit, rule.constraint_type
                    )
                    consecutive_limit = self._resolve_limit(
                        consecutive_limit, rule.consecutive_limit, rule.constraint_type
                    )
                    applied.append(rule.rule_id)
                teacher_rules.append(
                    EffectiveTeacherDateRuleModel(
                        teacher_id=teacher.teacher_id,
                        target_date=calendar_day.target_date,
                        daily_hard_limit=daily_limit,
                        consecutive_hard_limit=consecutive_limit,
                        required_transfer_gap=transfer_gap,
                        applied_rule_ids=tuple(applied),
                    )
                )
        return ResolvedRuleSetModel(tuple(class_rules), tuple(teacher_rules))

    def _matches_class(
        self, rule: PlacementRuleModel, class_model: ClassModel, target_date: date, weekday: str
    ) -> bool:
        if not rule.enabled or rule.constraint_type == "soft":
            return False
        if rule.target_entity not in {"class", "campus"}:
            return False
        if rule.campus_id is not None and rule.campus_id != class_model.campus_id:
            return False
        if not self._matches_date(rule, target_date, weekday):
            return False
        attributes: dict[str, object] = {
            "class_id": class_model.class_id,
            "division": class_model.division,
            "grade": class_model.grade,
            "exam_category": class_model.exam_category,
            "category_tags": class_model.category_tags,
            "campus_id": class_model.campus_id,
        }
        return self._matches_conditions(rule, attributes)

    def _matches_teacher(
        self, rule: PlacementRuleModel, teacher: TeacherModel, target_date: date, weekday: str
    ) -> bool:
        if not rule.enabled or rule.constraint_type == "soft" or rule.target_entity != "teacher":
            return False
        if rule.campus_id is not None and rule.campus_id != teacher.home_campus_id:
            return False
        if not self._matches_date(rule, target_date, weekday):
            return False
        attributes: dict[str, object] = {
            "teacher_id": teacher.teacher_id,
            "home_campus_id": teacher.home_campus_id or "",
            "can_transfer_campus": str(teacher.can_transfer_campus).lower(),
            "subject_ids": teacher.subject_ids,
        }
        return self._matches_conditions(rule, attributes)

    def _matches_date(self, rule: PlacementRuleModel, target_date: date, weekday: str) -> bool:
        return not (
            (rule.start_date is not None and target_date < rule.start_date)
            or (rule.end_date is not None and target_date > rule.end_date)
            or (rule.weekdays and weekday not in rule.weekdays)
        )

    def _matches_conditions(self, rule: PlacementRuleModel, attributes: dict[str, object]) -> bool:
        return all(
            self._matches_value(attributes.get(field), operator, expected)
            for field, operator, expected in zip(
                rule.condition_fields,
                rule.condition_operators,
                rule.condition_values,
                strict=True,
            )
        )

    def _matches_value(self, actual: object, operator: str, expected: str) -> bool:
        if isinstance(actual, tuple):
            actual_values = {str(value) for value in actual}
            if operator == "contains":
                return expected in actual_values
            if operator == "in":
                return bool(actual_values.intersection(expected.split("|")))
        actual_text = str(actual)
        if operator == "eq":
            return actual_text == expected
        if operator == "ne":
            return actual_text != expected
        if operator == "in":
            return actual_text in expected.split("|")
        if operator == "contains":
            return expected in actual_text
        if operator in {"ge", "le"}:
            try:
                actual_number = float(actual_text)
                expected_number = float(expected)
            except ValueError:
                return False
            return (
                actual_number >= expected_number
                if operator == "ge"
                else actual_number <= expected_number
            )
        if operator == "between":
            try:
                lower, upper = (float(value) for value in expected.split("|", maxsplit=1))
                return lower <= float(actual_text) <= upper
            except (ValueError, TypeError):
                return False
        return False

    def _resolve_limit(
        self, current: int | None, proposed: int | None, constraint_type: str
    ) -> int | None:
        if proposed is None:
            return current
        if current is None or constraint_type == "override":
            return proposed
        return min(current, proposed)


class CandidateBuilderService:
    """Build candidates and reject only facts decidable from one candidate."""

    def execute(
        self, input_data: InputDataModel, resolved_rules: ResolvedRuleSetModel
    ) -> CandidateBuildResultModel:
        classes = {item.class_id: item for item in input_data.classes}
        teachers = {item.teacher_id: item for item in input_data.teachers}
        rooms = {item.room_id: item for item in input_data.rooms}
        availability = {
            (item.teacher_id, item.target_date, item.period_id): item.availability
            for item in input_data.teacher_availability
        }
        class_rules = {
            (item.class_id, item.target_date): item for item in resolved_rules.class_date_rules
        }
        candidates: list[CandidateSlotModel] = []
        rejection_counts: Counter[tuple[str, str]] = Counter()
        for requirement in input_data.lesson_requirements:
            class_model = classes[requirement.class_id]
            teacher_ids: Sequence[str] = (requirement.primary_teacher_id,)
            if not requirement.fixed_teacher:
                teacher_ids = (requirement.primary_teacher_id, *requirement.alternative_teacher_ids)
            room_ids: Sequence[str] = requirement.room_ids or tuple(rooms)
            for calendar_day in input_data.calendar_days:
                for period in input_data.periods:
                    for teacher_id in teacher_ids:
                        for room_id in room_ids:
                            rejection_rule = self._rejection_rule(
                                requirement.subject_id,
                                class_model.campus_id,
                                calendar_day.target_date,
                                calendar_day.is_open,
                                calendar_day.available_period_ids,
                                period.period_id,
                                teacher_id,
                                room_id,
                                teachers,
                                rooms,
                                availability,
                                class_rules,
                                requirement.class_id,
                            )
                            if rejection_rule is not None:
                                rejection_counts[(requirement.requirement_id, rejection_rule)] += 1
                                continue
                            candidate_id = "__".join(
                                (
                                    requirement.requirement_id,
                                    calendar_day.target_date.isoformat(),
                                    period.period_id,
                                    teacher_id,
                                    room_id,
                                )
                            )
                            candidates.append(
                                CandidateSlotModel(
                                    candidate_id=candidate_id,
                                    requirement_id=requirement.requirement_id,
                                    target_date=calendar_day.target_date,
                                    period_id=period.period_id,
                                    teacher_id=teacher_id,
                                    room_id=room_id,
                                    campus_id=class_model.campus_id,
                                    class_id=requirement.class_id,
                                    subject_id=requirement.subject_id,
                                )
                            )
        summaries = tuple(
            CandidateRejectionSummaryModel(requirement_id, rule_id, rejected_count)
            for (requirement_id, rule_id), rejected_count in sorted(rejection_counts.items())
        )
        return CandidateBuildResultModel(tuple(candidates), summaries)

    def _rejection_rule(
        self,
        subject_id: str,
        campus_id: str,
        target_date: date,
        is_open: bool,
        available_period_ids: tuple[str, ...],
        period_id: str,
        teacher_id: str,
        room_id: str,
        teachers: dict[str, TeacherModel],
        rooms: dict[str, RoomModel],
        availability: dict[tuple[str, date, str], str],
        class_rules: dict[tuple[str, date], EffectiveClassDateRuleModel],
        class_id: str,
    ) -> str | None:
        if not is_open or period_id not in available_period_ids:
            return "H04"
        if period_id not in class_rules[(class_id, target_date)].allowed_period_ids:
            return "H13"
        teacher = teachers[teacher_id]
        if (
            not teacher.enabled
            or subject_id not in teacher.subject_ids
            or availability.get((teacher_id, target_date, period_id))
            not in {"available", "preferred"}
        ):
            return "H05"
        room = rooms.get(room_id)
        if room is None or not room.enabled or room.campus_id != campus_id:
            return "H14"
        return None

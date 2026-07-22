from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from datetime import date

from school_timetable_solver.model.input_models import (
    GenerationMode,
    InputDataModel,
    PlacementRuleModel,
)
from school_timetable_solver.model.master_models import ClassModel
from school_timetable_solver.model.result_models import ValidationIssueModel


class ReferenceIntegrityValidator:
    """Validate identifier uniqueness, references, ranges, and supported input values."""

    def validate(self, input_data: InputDataModel) -> list[ValidationIssueModel]:
        issues: list[ValidationIssueModel] = []
        id_groups: tuple[tuple[str, Iterable[str]], ...] = (
            ("campus_id", (item.campus_id for item in input_data.campuses)),
            ("room_id", (item.room_id for item in input_data.rooms)),
            ("teacher_id", (item.teacher_id for item in input_data.teachers)),
            ("class_id", (item.class_id for item in input_data.classes)),
            ("subject_id", (item.subject_id for item in input_data.subjects)),
            ("period_id", (item.period_id for item in input_data.periods)),
            (
                "requirement_id",
                (item.requirement_id for item in input_data.lesson_requirements),
            ),
            ("fixed_lesson_id", (item.fixed_lesson_id for item in input_data.fixed_lessons)),
            ("rule_id", (item.rule_id for item in input_data.placement_rules)),
        )
        for name, identifiers in id_groups:
            counts = Counter(identifiers)
            for identifier, count in counts.items():
                if count > 1:
                    issues.append(self._issue("E002", identifier, f"{name}が重複しています"))
        duplicate_keys: tuple[tuple[str, Iterable[object]], ...] = (
            ("calendar_date", (item.target_date for item in input_data.calendar_days)),
            (
                "teacher_availability_slot",
                (
                    (item.teacher_id, item.target_date, item.period_id)
                    for item in input_data.teacher_availability
                ),
            ),
        )
        for name, keys in duplicate_keys:
            counts = Counter(keys)
            for key, count in counts.items():
                if count > 1:
                    issues.append(self._issue("E002", str(key), f"{name}が重複しています"))

        campus_ids = {item.campus_id for item in input_data.campuses}
        room_ids = {item.room_id for item in input_data.rooms}
        teacher_ids = {item.teacher_id for item in input_data.teachers}
        class_ids = {item.class_id for item in input_data.classes}
        subject_ids = {item.subject_id for item in input_data.subjects}
        period_ids = {item.period_id for item in input_data.periods}
        requirement_ids = {item.requirement_id for item in input_data.lesson_requirements}
        calendar_dates = {item.target_date for item in input_data.calendar_days}

        for room in input_data.rooms:
            self._require_reference(
                issues, "room", room.room_id, "campus", room.campus_id, campus_ids
            )
        for teacher in input_data.teachers:
            if teacher.home_campus_id is not None:
                self._require_reference(
                    issues,
                    "teacher",
                    teacher.teacher_id,
                    "home_campus",
                    teacher.home_campus_id,
                    campus_ids,
                )
            for subject_id in teacher.subject_ids:
                self._require_reference(
                    issues, "teacher", teacher.teacher_id, "subject", subject_id, subject_ids
                )
        for class_model in input_data.classes:
            self._require_reference(
                issues,
                "class",
                class_model.class_id,
                "campus",
                class_model.campus_id,
                campus_ids,
            )
            for period_id in class_model.default_allowed_periods:
                self._require_reference(
                    issues, "class", class_model.class_id, "period", period_id, period_ids
                )
        for calendar_day in input_data.calendar_days:
            if not self._in_course(input_data, calendar_day.target_date):
                issues.append(
                    self._issue(
                        "E004",
                        calendar_day.target_date.isoformat(),
                        "開講カレンダーの日付が講座期間外です",
                    )
                )
            for period_id in calendar_day.available_period_ids:
                self._require_reference(
                    issues,
                    "calendar",
                    calendar_day.target_date.isoformat(),
                    "period",
                    period_id,
                    period_ids,
                )
        for requirement in input_data.lesson_requirements:
            target = requirement.requirement_id
            self._require_reference(
                issues, "requirement", target, "class", requirement.class_id, class_ids
            )
            self._require_reference(
                issues, "requirement", target, "subject", requirement.subject_id, subject_ids
            )
            self._require_reference(
                issues,
                "requirement",
                target,
                "primary_teacher",
                requirement.primary_teacher_id,
                teacher_ids,
            )
            for teacher_id in requirement.alternative_teacher_ids:
                self._require_reference(
                    issues, "requirement", target, "alternative_teacher", teacher_id, teacher_ids
                )
            for room_id in requirement.room_ids:
                self._require_reference(issues, "requirement", target, "room", room_id, room_ids)
            if requirement.required_periods <= 0:
                issues.append(
                    self._issue("INVALID_LIMIT", target, "required_periodsは1以上が必要です")
                )
        for availability in input_data.teacher_availability:
            target = (
                f"{availability.teacher_id}/{availability.target_date}/{availability.period_id}"
            )
            self._require_reference(
                issues, "availability", target, "teacher", availability.teacher_id, teacher_ids
            )
            self._require_reference(
                issues, "availability", target, "period", availability.period_id, period_ids
            )
            if availability.target_date not in calendar_dates:
                issues.append(self._issue("E003", target, "勤務日がカレンダーに存在しません"))
            if availability.availability not in {"available", "preferred", "unavailable"}:
                issues.append(self._issue("INVALID_AVAILABILITY", target, "勤務可否の値が不正です"))
        for fixed in input_data.fixed_lessons:
            target = fixed.fixed_lesson_id
            self._require_reference(
                issues, "fixed_lesson", target, "requirement", fixed.requirement_id, requirement_ids
            )
            self._require_reference(
                issues, "fixed_lesson", target, "class", fixed.class_id, class_ids
            )
            self._require_reference(
                issues, "fixed_lesson", target, "subject", fixed.subject_id, subject_ids
            )
            self._require_reference(
                issues, "fixed_lesson", target, "teacher", fixed.teacher_id, teacher_ids
            )
            self._require_reference(issues, "fixed_lesson", target, "room", fixed.room_id, room_ids)
            self._require_reference(
                issues, "fixed_lesson", target, "period", fixed.period_id, period_ids
            )
            if fixed.target_date not in calendar_dates:
                issues.append(self._issue("E003", target, "固定授業日がカレンダーに存在しません"))
            if not self._in_course(input_data, fixed.target_date):
                issues.append(self._issue("E004", target, "固定授業日が講座期間外です"))
        valid_fields = {
            "class_id",
            "division",
            "grade",
            "exam_category",
            "category_tags",
            "campus_id",
            "teacher_id",
            "home_campus_id",
            "can_transfer_campus",
            "subject_ids",
        }
        valid_operators = {"eq", "ne", "in", "contains", "ge", "le", "between"}
        for rule in input_data.placement_rules:
            if rule.campus_id is not None:
                self._require_reference(
                    issues, "rule", rule.rule_id, "campus", rule.campus_id, campus_ids
                )
            if not (
                len(rule.condition_fields)
                == len(rule.condition_operators)
                == len(rule.condition_values)
            ):
                issues.append(
                    self._issue(
                        "E012", rule.rule_id, "条件フィールド・演算子・値の数が一致しません"
                    )
                )
            for field in rule.condition_fields:
                if field not in valid_fields:
                    issues.append(
                        self._issue("E012", rule.rule_id, f"不正な条件フィールドです: {field}")
                    )
            for operator in rule.condition_operators:
                if operator not in valid_operators:
                    issues.append(
                        self._issue("E012", rule.rule_id, f"不正な条件演算子です: {operator}")
                    )
            for period_id in (*rule.allowed_period_ids, *rule.prohibited_period_ids):
                self._require_reference(
                    issues, "rule", rule.rule_id, "period", period_id, period_ids
                )
        if input_data.settings.solve_mode is GenerationMode.DIAGNOSTIC:
            issues.append(
                self._issue(
                    "UNSUPPORTED_GENERATION_MODE",
                    "diagnostic",
                    "diagnosticモードはVer.1では未対応です",
                )
            )
        return issues

    def _require_reference(
        self,
        issues: list[ValidationIssueModel],
        source_name: str,
        source_id: str,
        target_name: str,
        target_id: str,
        valid_ids: set[str],
    ) -> None:
        if target_id not in valid_ids:
            issues.append(
                self._issue(
                    "E003",
                    source_id,
                    f"{source_name}が存在しない{target_name}を参照しています: {target_id}",
                )
            )

    def _in_course(self, input_data: InputDataModel, target_date: date) -> bool:
        return input_data.settings.start_date <= target_date <= input_data.settings.end_date

    def _issue(self, rule_id: str, target: str, message: str) -> ValidationIssueModel:
        return ValidationIssueModel(rule_id, "ERROR", target, message)


class FixedLessonValidator:
    """Validate fixed lesson collisions and conflicts with immutable input facts."""

    def validate(self, input_data: InputDataModel) -> list[ValidationIssueModel]:
        issues: list[ValidationIssueModel] = []
        calendars = {item.target_date: item for item in input_data.calendar_days}
        availability = {
            (item.teacher_id, item.target_date, item.period_id): item.availability
            for item in input_data.teacher_availability
        }
        requirements = {item.requirement_id: item for item in input_data.lesson_requirements}
        rooms = {item.room_id: item for item in input_data.rooms}
        seen_teacher: set[tuple[str, date, str]] = set()
        seen_class: set[tuple[str, date, str]] = set()
        seen_room: set[tuple[str, date, str]] = set()
        for fixed in input_data.fixed_lessons:
            calendar = calendars.get(fixed.target_date)
            if calendar is not None and (
                not calendar.is_open or fixed.period_id not in calendar.available_period_ids
            ):
                issues.append(
                    self._issue("E005", fixed.fixed_lesson_id, "休館日または利用不可時限です")
                )
            if (
                availability.get(
                    (fixed.teacher_id, fixed.target_date, fixed.period_id), "unavailable"
                )
                == "unavailable"
            ):
                issues.append(
                    self._issue(
                        "FIXED_TEACHER_UNAVAILABLE", fixed.fixed_lesson_id, "教師が勤務不可です"
                    )
                )
            requirement = requirements.get(fixed.requirement_id)
            if requirement is not None and (
                requirement.class_id != fixed.class_id
                or requirement.subject_id != fixed.subject_id
                or fixed.teacher_id
                not in {requirement.primary_teacher_id, *requirement.alternative_teacher_ids}
                or (
                    requirement.fixed_teacher and fixed.teacher_id != requirement.primary_teacher_id
                )
                or (requirement.room_ids and fixed.room_id not in requirement.room_ids)
            ):
                issues.append(
                    self._issue(
                        "FIXED_REQUIREMENT_MISMATCH",
                        fixed.fixed_lesson_id,
                        "授業要求と一致しません",
                    )
                )
            room = rooms.get(fixed.room_id)
            class_model = next(
                (item for item in input_data.classes if item.class_id == fixed.class_id), None
            )
            if (
                room is not None
                and class_model is not None
                and room.campus_id != class_model.campus_id
            ):
                issues.append(
                    self._issue(
                        "FIXED_ROOM_CAMPUS_MISMATCH",
                        fixed.fixed_lesson_id,
                        "教室の校舎が不一致です",
                    )
                )
            keys = (
                ("E006", (fixed.teacher_id, fixed.target_date, fixed.period_id), seen_teacher),
                ("E007", (fixed.class_id, fixed.target_date, fixed.period_id), seen_class),
                ("E008", (fixed.room_id, fixed.target_date, fixed.period_id), seen_room),
            )
            for rule_id, key, seen in keys:
                if key in seen:
                    issues.append(
                        self._issue(rule_id, fixed.fixed_lesson_id, "固定授業同士が競合しています")
                    )
                seen.add(key)
        fixed_counts = Counter(item.requirement_id for item in input_data.fixed_lessons)
        for requirement in input_data.lesson_requirements:
            if fixed_counts[requirement.requirement_id] > requirement.required_periods:
                issues.append(
                    self._issue(
                        "FIXED_COUNT_EXCEEDS_REQUIRED",
                        requirement.requirement_id,
                        "固定授業数が必要コマ数を超えています",
                    )
                )
        return issues

    def _issue(self, rule_id: str, target: str, message: str) -> ValidationIssueModel:
        return ValidationIssueModel(rule_id, "ERROR", target, message)


class RuleConflictValidator:
    """Reject contradictory values at the same priority and applicability."""

    def validate(self, input_data: InputDataModel) -> list[ValidationIssueModel]:
        issues: list[ValidationIssueModel] = []
        enabled_rules = [rule for rule in input_data.placement_rules if rule.enabled]
        for index, left in enumerate(enabled_rules):
            for right in enabled_rules[index + 1 :]:
                if left.priority != right.priority:
                    continue
                if not self._has_common_date(left, right, input_data):
                    continue
                if not self._has_common_target(left, right, input_data):
                    continue
                if left.constraint_type == right.constraint_type == "hard":
                    allowed = {item.period_id for item in input_data.periods}
                    for rule in (left, right):
                        if rule.allowed_period_ids:
                            allowed.intersection_update(rule.allowed_period_ids)
                        allowed.difference_update(rule.prohibited_period_ids)
                    if not allowed:
                        issues.append(
                            ValidationIssueModel(
                                "E010",
                                "ERROR",
                                f"{left.rule_id},{right.rule_id}",
                                "同一優先順位のHardルールで許可時限の積集合が空です",
                            )
                        )
                    continue
                if self._override_values_conflict(left, right, input_data):
                    issues.append(
                        ValidationIssueModel(
                            "E009",
                            "ERROR",
                            f"{left.rule_id},{right.rule_id}",
                            "同一優先順位・同一適用範囲のルールが矛盾しています",
                        )
                    )
        return issues

    def _has_common_date(
        self,
        left: PlacementRuleModel,
        right: PlacementRuleModel,
        input_data: InputDataModel,
    ) -> bool:
        return any(
            self._matches_date(left, day.target_date, day.weekday)
            and self._matches_date(right, day.target_date, day.weekday)
            for day in input_data.calendar_days
        )

    def _has_common_target(
        self,
        left: PlacementRuleModel,
        right: PlacementRuleModel,
        input_data: InputDataModel,
    ) -> bool:
        class_target_types = {"class", "campus"}
        if left.target_entity in class_target_types and right.target_entity in class_target_types:
            return any(
                self._matches_class(left, class_model) and self._matches_class(right, class_model)
                for class_model in input_data.classes
            )
        if left.target_entity == right.target_entity == "teacher":
            return any(
                self._matches_conditions(
                    left,
                    {
                        "teacher_id": teacher.teacher_id,
                        "home_campus_id": teacher.home_campus_id or "",
                        "can_transfer_campus": str(teacher.can_transfer_campus).lower(),
                        "subject_ids": teacher.subject_ids,
                    },
                )
                and self._matches_conditions(
                    right,
                    {
                        "teacher_id": teacher.teacher_id,
                        "home_campus_id": teacher.home_campus_id or "",
                        "can_transfer_campus": str(teacher.can_transfer_campus).lower(),
                        "subject_ids": teacher.subject_ids,
                    },
                )
                for teacher in input_data.teachers
            )
        return left.target_entity == right.target_entity and (
            left.condition_fields,
            left.condition_operators,
            left.condition_values,
        ) == (
            right.condition_fields,
            right.condition_operators,
            right.condition_values,
        )

    def _matches_class(self, rule: PlacementRuleModel, class_model: ClassModel) -> bool:
        if rule.campus_id is not None and rule.campus_id != class_model.campus_id:
            return False
        return self._matches_conditions(
            rule,
            {
                "class_id": class_model.class_id,
                "division": class_model.division,
                "grade": class_model.grade,
                "exam_category": class_model.exam_category,
                "category_tags": class_model.category_tags,
                "campus_id": class_model.campus_id,
            },
        )

    def _matches_conditions(self, rule: PlacementRuleModel, attributes: dict[str, object]) -> bool:
        if not (
            len(rule.condition_fields)
            == len(rule.condition_operators)
            == len(rule.condition_values)
        ):
            return False
        for field, operator, expected in zip(
            rule.condition_fields,
            rule.condition_operators,
            rule.condition_values,
            strict=True,
        ):
            actual = attributes.get(field)
            actual_values = {str(value) for value in actual} if isinstance(actual, tuple) else None
            if operator == "eq" and str(actual) != expected:
                return False
            if operator == "ne" and str(actual) == expected:
                return False
            if operator == "contains" and (actual_values is None or expected not in actual_values):
                return False
            if operator == "in" and (
                (actual_values is not None and not actual_values.intersection(expected.split("|")))
                or (actual_values is None and str(actual) not in expected.split("|"))
            ):
                return False
            if operator in {"ge", "le", "between"}:
                try:
                    actual_number = float(str(actual))
                    if operator == "ge" and actual_number < float(expected):
                        return False
                    if operator == "le" and actual_number > float(expected):
                        return False
                    if operator == "between":
                        lower, upper = (float(value) for value in expected.split("|", 1))
                        if not lower <= actual_number <= upper:
                            return False
                except ValueError:
                    return False
        return True

    def _matches_date(self, rule: PlacementRuleModel, target_date: date, weekday: str) -> bool:
        return not (
            (rule.start_date is not None and target_date < rule.start_date)
            or (rule.end_date is not None and target_date > rule.end_date)
            or (rule.weekdays and weekday not in rule.weekdays)
        )

    def _override_values_conflict(
        self, left: PlacementRuleModel, right: PlacementRuleModel, input_data: InputDataModel
    ) -> bool:
        all_periods = {item.period_id for item in input_data.periods}
        left_periods = set(left.allowed_period_ids or all_periods) - set(left.prohibited_period_ids)
        right_periods = set(right.allowed_period_ids or all_periods) - set(
            right.prohibited_period_ids
        )
        both_define_periods = bool(
            left.allowed_period_ids
            or left.prohibited_period_ids
            or right.allowed_period_ids
            or right.prohibited_period_ids
        )
        if both_define_periods and left_periods != right_periods:
            return True
        for left_value, right_value in (
            (left.daily_hard_limit, right.daily_hard_limit),
            (left.consecutive_limit, right.consecutive_limit),
            (left.attendance_streak_limit, right.attendance_streak_limit),
        ):
            if left_value is not None and right_value is not None and left_value != right_value:
                return True
        return False


class CapacityFeasibilityValidator:
    """Detect obvious shortages without reproducing the full Candidate builder."""

    def validate(self, input_data: InputDataModel) -> list[ValidationIssueModel]:
        issues: list[ValidationIssueModel] = []
        classes = {item.class_id: item for item in input_data.classes}
        teachers = {item.teacher_id: item for item in input_data.teachers}
        rooms = {item.room_id: item for item in input_data.rooms}
        availability = {
            (item.teacher_id, item.target_date, item.period_id): item.availability
            for item in input_data.teacher_availability
        }
        for requirement in input_data.lesson_requirements:
            class_model = classes.get(requirement.class_id)
            if class_model is None:
                continue
            teacher_ids = (requirement.primary_teacher_id,)
            if not requirement.fixed_teacher:
                teacher_ids += requirement.alternative_teacher_ids
            eligible_teachers = {
                teacher_id
                for teacher_id in teacher_ids
                if teacher_id in teachers
                and requirement.subject_id in teachers[teacher_id].subject_ids
                and teachers[teacher_id].enabled
            }
            eligible_rooms = {
                room.room_id
                for room in rooms.values()
                if room.enabled
                and room.campus_id == class_model.campus_id
                and (not requirement.room_ids or room.room_id in requirement.room_ids)
            }
            slots = {
                (day.target_date, period_id)
                for day in input_data.calendar_days
                if day.is_open
                for period_id in day.available_period_ids
                if (
                    not class_model.default_allowed_periods
                    or period_id in class_model.default_allowed_periods
                )
                and any(
                    availability.get((teacher_id, day.target_date, period_id))
                    in {"available", "preferred"}
                    for teacher_id in eligible_teachers
                )
            }
            if not eligible_rooms or len(slots) < requirement.required_periods:
                issues.append(
                    ValidationIssueModel(
                        "E011",
                        "ERROR",
                        requirement.requirement_id,
                        (
                            "必要コマ数に対して明白な候補枠が不足しています: "
                            f"required={requirement.required_periods}, slots={len(slots)}, "
                            f"rooms={len(eligible_rooms)}"
                        ),
                    )
                )
        return issues


InputValidator = (
    ReferenceIntegrityValidator
    | FixedLessonValidator
    | RuleConflictValidator
    | CapacityFeasibilityValidator
)


DEFAULT_INPUT_VALIDATORS: tuple[InputValidator, ...] = (
    ReferenceIntegrityValidator(),
    FixedLessonValidator(),
    RuleConflictValidator(),
    CapacityFeasibilityValidator(),
)

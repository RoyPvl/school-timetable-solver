from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Container, Iterable

from school_timetable_solver.model.input_models import InputDataModel
from school_timetable_solver.model.result_models import ValidationIssueModel
from school_timetable_solver.model.solver_models import (
    CandidateBuildResultModel,
    ResolvedRuleSetModel,
)


class ReferenceIntegrityValidator:
    """Validate identifiers, references, active-state use, ranges, and rule columns."""

    def validate(self, input_data: InputDataModel) -> list[ValidationIssueModel]:
        issues: list[ValidationIssueModel] = []
        self._validate_uniqueness(input_data, issues)
        self._validate_orders_and_ranges(input_data, issues)
        self._validate_references(input_data, issues)
        self._validate_rules(input_data, issues)
        return issues

    def _validate_uniqueness(
        self,
        input_data: InputDataModel,
        issues: list[ValidationIssueModel],
    ) -> None:
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
            ("rule_id", (item.rule_id for item in input_data.placement_rules)),
        )
        for label, identifiers in id_groups:
            for identifier, count in Counter(identifiers).items():
                if count > 1:
                    issues.append(
                        self._issue("DUPLICATE_ID", identifier, f"{label}が重複しています")
                    )
        for target_date, count in Counter(
            day.target_date for day in input_data.calendar_days
        ).items():
            if count > 1:
                issues.append(
                    self._issue(
                        "DUPLICATE_CALENDAR_DATE",
                        str(target_date),
                        "開講カレンダーの日付が重複しています",
                    )
                )
        leave_days = Counter(
            (item.teacher_id, item.target_date) for item in input_data.teacher_leaves
        )
        for key, count in leave_days.items():
            if count > 1:
                issues.append(
                    self._issue(
                        "DUPLICATE_TEACHER_LEAVE",
                        str(key),
                        "教師休みのteacher_id/dateが重複しています",
                    )
                )
        for teacher_leave in input_data.teacher_leaves:
            duplicate_period_ids = {
                period_id
                for period_id, count in Counter(teacher_leave.unavailable_period_ids).items()
                if count > 1
            }
            if duplicate_period_ids:
                issues.append(
                    self._issue(
                        "DUPLICATE_TEACHER_LEAVE_PERIOD",
                        f"{teacher_leave.teacher_id}/{teacher_leave.target_date}",
                        (
                            "教師休みのunavailable_periodsに重複があります: "
                            f"{sorted(duplicate_period_ids)}"
                        ),
                    )
                )
        enabled_pairs = Counter(
            (item.class_id, item.subject_id)
            for item in input_data.lesson_requirements
            if item.enabled
        )
        for key, count in enabled_pairs.items():
            if count > 1:
                issues.append(
                    self._issue(
                        "DUPLICATE_CLASS_SUBJECT_REQUIREMENT",
                        str(key),
                        "有効なclass_id/subject_idが重複しています",
                    )
                )

    def _validate_orders_and_ranges(
        self,
        input_data: InputDataModel,
        issues: list[ValidationIssueModel],
    ) -> None:
        enabled_campus_orders = [item.output_order for item in input_data.campuses if item.enabled]
        if len(enabled_campus_orders) != len(set(enabled_campus_orders)):
            issues.append(
                self._issue(
                    "DUPLICATE_CAMPUS_OUTPUT_ORDER",
                    "campuses",
                    "有効校舎のoutput_orderが重複しています",
                )
            )
        room_orders: dict[str, list[int]] = defaultdict(list)
        for room in input_data.rooms:
            if room.enabled:
                room_orders[room.campus_id].append(room.output_order)
        for campus_id, orders in room_orders.items():
            if len(orders) != len(set(orders)):
                issues.append(
                    self._issue(
                        "DUPLICATE_ROOM_OUTPUT_ORDER",
                        campus_id,
                        "同一校舎内の有効教室output_orderが重複しています",
                    )
                )
        period_orders = [item.output_order for item in input_data.periods]
        if len(input_data.periods) != 6 or set(period_orders) != set(range(1, 7)):
            issues.append(
                self._issue(
                    "INVALID_PERIOD_OUTPUT_ORDER",
                    "periods",
                    "時限は6件でoutput_order 1-6を重複なく使用してください",
                )
            )
        for period in input_data.periods:
            if period.start_time >= period.end_time:
                issues.append(
                    self._issue(
                        "INVALID_PERIOD_TIME_RANGE",
                        period.period_id,
                        "start_timeはend_timeより前である必要があります",
                    )
                )
        if not any(day.output_enabled for day in input_data.calendar_days):
            issues.append(
                self._issue(
                    "OUTPUT_DATE_REQUIRED",
                    "calendar",
                    "output_enabled=TRUEの出力対象日が1件以上必要です",
                )
            )
        enabled_campuses = {campus.campus_id for campus in input_data.campuses if campus.enabled}
        campuses_with_rooms = {
            room.campus_id
            for room in input_data.rooms
            if room.enabled and room.campus_id in enabled_campuses
        }
        for campus_id in enabled_campuses - campuses_with_rooms:
            issues.append(
                self._issue(
                    "ENABLED_CAMPUS_ROOM_REQUIRED",
                    campus_id,
                    "有効校舎には有効な教室が1件以上必要です",
                )
            )
        for requirement in input_data.lesson_requirements:
            if requirement.required_periods < 1:
                issues.append(
                    self._issue(
                        "INVALID_REQUIRED_PERIODS",
                        requirement.requirement_id,
                        "required_periodsは1以上が必要です",
                    )
                )
            if requirement.max_periods_per_day is not None and requirement.max_periods_per_day < 1:
                issues.append(
                    self._issue(
                        "INVALID_REQUIREMENT_DAILY_LIMIT",
                        requirement.requirement_id,
                        "max_periods_per_dayは空欄または1以上が必要です",
                    )
                )

    def _validate_references(
        self,
        input_data: InputDataModel,
        issues: list[ValidationIssueModel],
    ) -> None:
        campuses = {item.campus_id: item for item in input_data.campuses}
        teachers = {item.teacher_id: item for item in input_data.teachers}
        classes = {item.class_id: item for item in input_data.classes}
        subjects = {item.subject_id: item for item in input_data.subjects}
        periods = {item.period_id: item for item in input_data.periods}
        calendar_dates = {item.target_date for item in input_data.calendar_days}

        for teacher in input_data.teachers:
            self._require_reference(
                issues,
                teacher.teacher_id,
                "home_campus_id",
                teacher.home_campus_id,
                campuses,
            )
            if (
                teacher.enabled
                and teacher.home_campus_id in campuses
                and not campuses[teacher.home_campus_id].enabled
            ):
                issues.append(
                    self._issue(
                        "DISABLED_MASTER_REFERENCE",
                        teacher.teacher_id,
                        "有効教師が無効な所属校舎を参照しています",
                    )
                )
        for room in input_data.rooms:
            self._require_reference(issues, room.room_id, "campus_id", room.campus_id, campuses)
            if room.enabled and room.campus_id in campuses and not campuses[room.campus_id].enabled:
                issues.append(
                    self._issue(
                        "DISABLED_MASTER_REFERENCE",
                        room.room_id,
                        "有効教室が無効校舎を参照しています",
                    )
                )
        for class_model in input_data.classes:
            self._require_reference(
                issues, class_model.class_id, "campus_id", class_model.campus_id, campuses
            )
            if (
                class_model.homeroom_teacher_id is not None
                and class_model.homeroom_teacher_id not in teachers
            ):
                issues.append(
                    self._issue(
                        "UNKNOWN_REFERENCE",
                        class_model.class_id,
                        f"homeroom_teacher_idが存在しません: {class_model.homeroom_teacher_id}",
                    )
                )
            if (
                class_model.enabled
                and class_model.campus_id in campuses
                and not campuses[class_model.campus_id].enabled
            ):
                issues.append(
                    self._issue(
                        "DISABLED_MASTER_REFERENCE",
                        class_model.class_id,
                        "有効クラスが無効校舎を参照しています",
                    )
                )
        for requirement in input_data.lesson_requirements:
            self._require_reference(
                issues, requirement.requirement_id, "class_id", requirement.class_id, classes
            )
            self._require_reference(
                issues, requirement.requirement_id, "subject_id", requirement.subject_id, subjects
            )
            self._require_reference(
                issues, requirement.requirement_id, "teacher_id", requirement.teacher_id, teachers
            )
            if requirement.enabled:
                referenced = (
                    classes.get(requirement.class_id),
                    subjects.get(requirement.subject_id),
                    teachers.get(requirement.teacher_id),
                )
                if any(item is not None and not item.enabled for item in referenced):
                    issues.append(
                        self._issue(
                            "DISABLED_MASTER_REFERENCE",
                            requirement.requirement_id,
                            "有効授業要求が無効マスタを参照しています",
                        )
                    )
        for teacher_leave in input_data.teacher_leaves:
            target = f"{teacher_leave.teacher_id}/{teacher_leave.target_date}"
            self._require_reference(
                issues,
                target,
                "teacher_id",
                teacher_leave.teacher_id,
                teachers,
            )
            for period_id in teacher_leave.unavailable_period_ids:
                self._require_reference(
                    issues,
                    target,
                    "period_id",
                    period_id,
                    periods,
                )
            if teacher_leave.target_date not in calendar_dates:
                issues.append(
                    self._issue(
                        "UNKNOWN_REFERENCE",
                        target,
                        "教師休みの日付が開講カレンダーに存在しません",
                    )
                )
            teacher = teachers.get(teacher_leave.teacher_id)
            if teacher is not None and not teacher.enabled:
                issues.append(
                    self._issue(
                        "DISABLED_MASTER_REFERENCE",
                        target,
                        "教師休みが無効教師を参照しています",
                    )
                )

    def _validate_rules(
        self,
        input_data: InputDataModel,
        issues: list[ValidationIssueModel],
    ) -> None:
        campuses = {item.campus_id: item for item in input_data.campuses}
        period_ids = {item.period_id for item in input_data.periods}
        valid_fields = {
            "class": {"class_id", "division", "grade", "exam_category", "campus_id"},
            "teacher": {"teacher_id"},
        }
        valid_operators = {"eq", "ne", "in", "ge", "le", "between"}
        valid_weekdays = {"MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"}
        for rule in input_data.placement_rules:
            target = rule.rule_id
            if rule.constraint_type not in {"hard", "override"}:
                issues.append(
                    self._issue(
                        "INVALID_RULE_CONSTRAINT_TYPE",
                        target,
                        f"constraint_typeが不正です: {rule.constraint_type}",
                    )
                )
            if rule.target_entity not in valid_fields:
                issues.append(
                    self._issue(
                        "INVALID_RULE_TARGET",
                        target,
                        f"target_entityが不正です: {rule.target_entity}",
                    )
                )
                continue
            if not (
                len(rule.condition_fields)
                == len(rule.condition_operators)
                == len(rule.condition_values)
            ):
                issues.append(
                    self._issue(
                        "RULE_CONDITION_LENGTH_MISMATCH",
                        target,
                        "condition_field/operator/valueの要素数が一致しません",
                    )
                )
            for field in rule.condition_fields:
                if field not in valid_fields[rule.target_entity]:
                    issues.append(
                        self._issue(
                            "INVALID_RULE_CONDITION_FIELD",
                            target,
                            f"条件項目が対象と整合しません: {field}",
                        )
                    )
            for operator in rule.condition_operators:
                if operator not in valid_operators:
                    issues.append(
                        self._issue(
                            "INVALID_RULE_OPERATOR",
                            target,
                            f"条件演算子が不正です: {operator}",
                        )
                    )
            for operator, value in zip(
                rule.condition_operators, rule.condition_values, strict=False
            ):
                if operator == "between":
                    parts = value.split("/")
                    try:
                        valid_between = len(parts) == 2 and float(parts[0]) <= float(parts[1])
                    except ValueError:
                        valid_between = False
                    if not valid_between:
                        issues.append(
                            self._issue(
                                "INVALID_RULE_CONDITION_VALUE",
                                target,
                                "betweenは下限/上限の2要素で指定してください",
                            )
                        )
                if operator == "in" and not value.split("/"):
                    issues.append(
                        self._issue(
                            "INVALID_RULE_CONDITION_VALUE",
                            target,
                            "inは半角スラッシュ区切りで指定してください",
                        )
                    )
            if rule.campus_id is not None:
                self._require_reference(issues, target, "campus_id", rule.campus_id, campuses)
                if rule.target_entity != "class" or "campus_id" in rule.condition_fields:
                    issues.append(
                        self._issue(
                            "INVALID_RULE_CAMPUS_FILTER",
                            target,
                            "campus_idはclassだけに使用でき、条件項目との重複指定はできません",
                        )
                    )
            if (
                rule.start_date is not None
                and rule.end_date is not None
                and rule.start_date > rule.end_date
            ):
                issues.append(
                    self._issue(
                        "INVALID_RULE_DATE_RANGE",
                        target,
                        "start_dateはend_date以前である必要があります",
                    )
                )
            unknown_weekdays = set(rule.weekdays) - valid_weekdays
            if unknown_weekdays:
                issues.append(
                    self._issue(
                        "INVALID_RULE_WEEKDAY",
                        target,
                        f"曜日コードが不正です: {sorted(unknown_weekdays)}",
                    )
                )
            for period_id in rule.allowed_period_ids:
                self._require_reference(issues, target, "allowed_period", period_id, period_ids)
            if rule.target_entity == "teacher" and (
                rule.allowed_period_ids or rule.attendance_streak_limit is not None
            ):
                issues.append(
                    self._issue(
                        "INVALID_RULE_COLUMN_FOR_TARGET",
                        target,
                        "teacherではallowed_periods/attendance_streak_limitを使用できません",
                    )
                )
            if rule.target_entity == "class" and rule.consecutive_limit is not None:
                issues.append(
                    self._issue(
                        "INVALID_RULE_COLUMN_FOR_TARGET",
                        target,
                        "classではconsecutive_limitを使用できません",
                    )
                )
            for label, value in (
                ("daily_hard_limit", rule.daily_hard_limit),
                ("consecutive_limit", rule.consecutive_limit),
                ("attendance_streak_limit", rule.attendance_streak_limit),
            ):
                if value is not None and value < 1:
                    issues.append(
                        self._issue("INVALID_RULE_LIMIT", target, f"{label}は1以上が必要です")
                    )
            if not (
                rule.allowed_period_ids
                or rule.daily_hard_limit is not None
                or rule.consecutive_limit is not None
                or rule.attendance_streak_limit is not None
            ):
                issues.append(
                    self._issue(
                        "RULE_VALUE_REQUIRED",
                        target,
                        "配置ルールには少なくとも1つの制約値が必要です",
                    )
                )

    def _require_reference(
        self,
        issues: list[ValidationIssueModel],
        source_id: str,
        field: str,
        target_id: str,
        known: Container[str],
    ) -> None:
        if target_id not in known:
            issues.append(
                self._issue(
                    "UNKNOWN_REFERENCE",
                    source_id,
                    f"{field}が存在しません: {target_id}",
                )
            )

    def _issue(self, rule_id: str, target: str, message: str) -> ValidationIssueModel:
        return ValidationIssueModel(rule_id, "ERROR", target, message)


class CapacityFeasibilityValidator:
    """Detect obvious supply shortages from the already resolved candidate set."""

    def validate(
        self,
        input_data: InputDataModel,
        resolved_rules: ResolvedRuleSetModel,
        candidate_result: CandidateBuildResultModel,
    ) -> list[ValidationIssueModel]:
        del resolved_rules
        issues: list[ValidationIssueModel] = []
        active_requirements = [
            requirement for requirement in input_data.lesson_requirements if requirement.enabled
        ]
        slots_by_requirement: dict[str, set[tuple[object, str]]] = defaultdict(set)
        slots_by_class: dict[str, set[tuple[object, str]]] = defaultdict(set)
        for candidate in candidate_result.candidates:
            slot = (candidate.target_date, candidate.period_id)
            slots_by_requirement[candidate.requirement_id].add(slot)
            slots_by_class[candidate.class_id].add(slot)
        for requirement in active_requirements:
            slot_count = len(slots_by_requirement[requirement.requirement_id])
            if slot_count < requirement.required_periods:
                issues.append(
                    ValidationIssueModel(
                        "CANDIDATE_SUPPLY_SHORTAGE",
                        "ERROR",
                        requirement.requirement_id,
                        (
                            "必要コマ数に対して候補枠が不足しています: "
                            f"required={requirement.required_periods}, slots={slot_count}"
                        ),
                    )
                )
        required_by_class = Counter()
        for requirement in active_requirements:
            required_by_class[requirement.class_id] += requirement.required_periods
        for class_id, required in required_by_class.items():
            slot_count = len(slots_by_class[class_id])
            if slot_count < required:
                issues.append(
                    ValidationIssueModel(
                        "CLASS_SUPPLY_SHORTAGE",
                        "ERROR",
                        class_id,
                        (
                            "クラスの総必要コマ数に対して候補枠が不足しています: "
                            f"required={required}, slots={slot_count}"
                        ),
                    )
                )
        active_campus_ids = {campus.campus_id for campus in input_data.campuses if campus.enabled}
        rooms_by_campus = Counter(
            room.campus_id
            for room in input_data.rooms
            if room.enabled and room.campus_id in active_campus_ids
        )
        for class_model in input_data.classes:
            if class_model.enabled and rooms_by_campus[class_model.campus_id] == 0:
                issues.append(
                    ValidationIssueModel(
                        "ROOM_SUPPLY_SHORTAGE",
                        "ERROR",
                        class_model.class_id,
                        "クラス所属校舎に有効な教室がありません",
                    )
                )
        return issues


InputValidator = ReferenceIntegrityValidator
DEFAULT_INPUT_VALIDATORS: tuple[InputValidator, ...] = (ReferenceIntegrityValidator(),)

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
from itertools import pairwise

from school_timetable_solver.model.input_models import (
    CalendarDayModel,
    HomeroomBoundaryRuleModel,
    InputDataModel,
    LessonCountPreferenceRuleSegmentModel,
    LessonCountRuleSegmentModel,
    LessonRequirementModel,
    PlacementRuleModel,
)
from school_timetable_solver.model.master_models import ClassModel, TeacherModel
from school_timetable_solver.model.solver_models import (
    CandidateBuildResultModel,
    CandidateRejectionSummaryModel,
    CandidateSlotModel,
    EffectiveClassDateRuleModel,
    EffectiveTeacherDateRuleModel,
    ResolvedHomeroomBoundaryRuleModel,
    ResolvedLessonCountPreferenceRuleModel,
    ResolvedLessonCountRuleModel,
    ResolvedRuleSetModel,
    RuleResolutionIssueModel,
)

_WEEKDAYS = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")


class RuleResolverService:
    """Resolve all data-driven class and teacher rules without implicit defaults."""

    def execute(self, input_data: InputDataModel) -> ResolvedRuleSetModel:
        period_ids = tuple(
            period.period_id
            for period in sorted(input_data.periods, key=lambda item: item.output_order)
        )
        output_days = sorted(
            (day for day in input_data.calendar_days if day.output_enabled),
            key=lambda item: item.target_date,
        )
        issues: list[RuleResolutionIssueModel] = []
        class_rules: list[EffectiveClassDateRuleModel] = []
        teacher_rules: list[EffectiveTeacherDateRuleModel] = []

        for class_model in (item for item in input_data.classes if item.enabled):
            for calendar_day in output_days:
                applicable = [
                    rule
                    for rule in input_data.placement_rules
                    if self._matches_class(rule, class_model, calendar_day.target_date)
                ]
                self._detect_same_priority_conflicts(
                    applicable,
                    f"class={class_model.class_id}/date={calendar_day.target_date}",
                    issues,
                )
                allowed: set[str] | None = None
                daily_limit: int | None = None
                attendance_limit: int | None = None
                attendance_preference_limit: int | None = None
                required_lesson_periods: set[str] = set()
                applied: list[str] = []
                for rule in sorted(applicable, key=lambda item: item.priority):
                    changed = False
                    if rule.allowed_period_ids:
                        proposed = set(rule.allowed_period_ids)
                        allowed = (
                            proposed
                            if allowed is None or rule.constraint_type == "override"
                            else allowed.intersection(proposed)
                        )
                        changed = True
                    if rule.required_lesson_period_ids:
                        proposed_required = set(rule.required_lesson_period_ids)
                        required_lesson_periods = (
                            proposed_required
                            if rule.constraint_type == "override"
                            else required_lesson_periods.union(proposed_required)
                        )
                        changed = True
                    daily_limit = self._resolve_limit(
                        daily_limit, rule.daily_hard_limit, rule.constraint_type
                    )
                    attendance_limit = self._resolve_limit(
                        attendance_limit,
                        rule.attendance_streak_limit,
                        rule.constraint_type,
                    )
                    attendance_preference_limit = self._resolve_limit(
                        attendance_preference_limit,
                        rule.preferred_attendance_streak_limit,
                        rule.constraint_type,
                    )
                    changed = changed or rule.daily_hard_limit is not None
                    changed = changed or rule.attendance_streak_limit is not None
                    changed = changed or rule.preferred_attendance_streak_limit is not None
                    if changed:
                        applied.append(rule.rule_id)
                target = f"class={class_model.class_id}/date={calendar_day.target_date}"
                if allowed is None:
                    issues.append(
                        RuleResolutionIssueModel(
                            "RULE_REQUIRED_VALUE_MISSING", target, "allowed_periodsが未解決です"
                        )
                    )
                elif not allowed:
                    issues.append(
                        RuleResolutionIssueModel(
                            "RULE_ALLOWED_PERIODS_EMPTY",
                            target,
                            "allowed_periodsの解決結果が空です",
                        )
                    )
                if daily_limit is None:
                    issues.append(
                        RuleResolutionIssueModel(
                            "RULE_REQUIRED_VALUE_MISSING", target, "daily_hard_limitが未解決です"
                        )
                    )
                if allowed is not None and not required_lesson_periods.issubset(allowed):
                    issues.append(
                        RuleResolutionIssueModel(
                            "RULE_REQUIRED_LESSON_PERIOD_NOT_ALLOWED",
                            target,
                            (
                                "required_lesson_periodsはallowed_periodsの部分集合が必要です: "
                                f"required={sorted(required_lesson_periods)}, "
                                f"allowed={sorted(allowed)}"
                            ),
                        )
                    )
                if daily_limit is not None and len(required_lesson_periods) > daily_limit:
                    issues.append(
                        RuleResolutionIssueModel(
                            "RULE_REQUIRED_LESSON_PERIODS_EXCEED_DAILY_LIMIT",
                            target,
                            (
                                "必須授業時限数がdaily_hard_limitを超えています: "
                                f"required={len(required_lesson_periods)}, limit={daily_limit}"
                            ),
                        )
                    )
                if (
                    attendance_limit is not None
                    and attendance_preference_limit is not None
                    and attendance_preference_limit > attendance_limit
                ):
                    issues.append(
                        RuleResolutionIssueModel(
                            "RULE_ATTENDANCE_LIMIT_ORDER",
                            target,
                            (
                                "preferred_attendance_streak_limitは"
                                "attendance_streak_limit以下である必要があります: "
                                f"preferred={attendance_preference_limit}, "
                                f"hard={attendance_limit}"
                            ),
                        )
                    )
                class_rules.append(
                    EffectiveClassDateRuleModel(
                        class_id=class_model.class_id,
                        target_date=calendar_day.target_date,
                        allowed_period_ids=(
                            tuple(period_id for period_id in period_ids if period_id in allowed)
                            if allowed is not None
                            else None
                        ),
                        daily_hard_limit=daily_limit,
                        attendance_streak_limit=attendance_limit,
                        applied_rule_ids=tuple(dict.fromkeys(applied)),
                        preferred_attendance_streak_limit=attendance_preference_limit,
                        required_lesson_period_ids=tuple(
                            period_id
                            for period_id in period_ids
                            if period_id in required_lesson_periods
                        ),
                    )
                )

        for teacher in (item for item in input_data.teachers if item.enabled):
            for calendar_day in output_days:
                applicable = [
                    rule
                    for rule in input_data.placement_rules
                    if self._matches_teacher(rule, teacher, calendar_day.target_date)
                ]
                self._detect_same_priority_conflicts(
                    applicable,
                    f"teacher={teacher.teacher_id}/date={calendar_day.target_date}",
                    issues,
                )
                daily_limit: int | None = None
                forbid_first_last_same_day: bool | None = None
                applied: list[str] = []
                for rule in sorted(applicable, key=lambda item: item.priority):
                    daily_limit = self._resolve_limit(
                        daily_limit, rule.daily_hard_limit, rule.constraint_type
                    )
                    forbid_first_last_same_day = self._resolve_boolean(
                        forbid_first_last_same_day,
                        rule.forbid_first_last_same_day,
                        rule.constraint_type,
                    )
                    if (
                        rule.daily_hard_limit is not None
                        or rule.forbid_first_last_same_day is not None
                    ):
                        applied.append(rule.rule_id)
                target = f"teacher={teacher.teacher_id}/date={calendar_day.target_date}"
                if daily_limit is None:
                    issues.append(
                        RuleResolutionIssueModel(
                            "RULE_REQUIRED_VALUE_MISSING", target, "daily_hard_limitが未解決です"
                        )
                    )
                if forbid_first_last_same_day is None:
                    issues.append(
                        RuleResolutionIssueModel(
                            "RULE_REQUIRED_VALUE_MISSING",
                            target,
                            "forbid_first_last_same_dayが未解決です",
                        )
                    )
                teacher_rules.append(
                    EffectiveTeacherDateRuleModel(
                        teacher_id=teacher.teacher_id,
                        target_date=calendar_day.target_date,
                        daily_hard_limit=daily_limit,
                        forbid_first_last_same_day=forbid_first_last_same_day,
                        applied_rule_ids=tuple(dict.fromkeys(applied)),
                    )
                )
        lesson_count_rules = self._resolve_lesson_count_rules(
            input_data,
            output_days,
            period_ids,
            issues,
        )
        lesson_count_preference_rules = self._resolve_lesson_count_preference_rules(
            input_data,
            output_days,
            period_ids,
            issues,
        )
        homeroom_boundary_rules = self._resolve_homeroom_boundary_rules(input_data, issues)
        return ResolvedRuleSetModel(
            class_date_rules=tuple(class_rules),
            teacher_date_rules=tuple(teacher_rules),
            issues=tuple(issues),
            lesson_count_rules=tuple(lesson_count_rules),
            lesson_count_preference_rules=tuple(lesson_count_preference_rules),
            homeroom_boundary_rules=tuple(homeroom_boundary_rules),
        )

    def _resolve_homeroom_boundary_rules(
        self,
        input_data: InputDataModel,
        issues: list[RuleResolutionIssueModel],
    ) -> list[ResolvedHomeroomBoundaryRuleModel]:
        regular_subject_ids = {
            subject.subject_id
            for subject in input_data.subjects
            if subject.enabled and subject.lesson_type == "regular"
        }
        requirements_by_class: dict[str, list[LessonRequirementModel]] = defaultdict(list)
        for requirement in input_data.lesson_requirements:
            if requirement.enabled:
                requirements_by_class[requirement.class_id].append(requirement)

        resolved: list[ResolvedHomeroomBoundaryRuleModel] = []
        for rule in input_data.homeroom_boundary_rules:
            if not rule.enabled:
                continue
            matched_count = 0
            for class_model in input_data.classes:
                if not class_model.enabled:
                    continue
                # Attendance is determined by every valid lesson; only the required
                # homeroom lesson remains limited to the teacher's regular lessons.
                attendance_requirement_ids = tuple(
                    requirement.requirement_id
                    for requirement in requirements_by_class[class_model.class_id]
                )
                eligible_requirement_ids = tuple(
                    requirement.requirement_id
                    for requirement in requirements_by_class[class_model.class_id]
                    if requirement.teacher_id == class_model.homeroom_teacher_id
                    and requirement.subject_id in regular_subject_ids
                )
                attributes = {
                    "class_id": class_model.class_id,
                    "division": class_model.division,
                    "grade": class_model.grade,
                    "exam_category": class_model.exam_category,
                    "campus_id": class_model.campus_id,
                    "has_regular_homeroom_lesson": bool(eligible_requirement_ids),
                }
                if not self._matches_boundary_rule(rule, attributes):
                    continue
                matched_count += 1
                if class_model.homeroom_teacher_id is None or not eligible_requirement_ids:
                    issues.append(
                        RuleResolutionIssueModel(
                            "HOMEROOM_BOUNDARY_TARGET_UNRESOLVED",
                            f"{rule.rule_id}/{class_model.class_id}",
                            "担任と、その担任が担当する通常授業を解決できません",
                        )
                    )
                    continue
                resolved.append(
                    ResolvedHomeroomBoundaryRuleModel(
                        source_rule_id=rule.rule_id,
                        class_id=class_model.class_id,
                        campus_id=class_model.campus_id,
                        teacher_id=class_model.homeroom_teacher_id,
                        attendance_requirement_ids=attendance_requirement_ids,
                        eligible_requirement_ids=eligible_requirement_ids,
                        start_date=rule.start_date,
                        end_date=rule.end_date,
                    )
                )
            if matched_count == 0:
                issues.append(
                    RuleResolutionIssueModel(
                        "HOMEROOM_BOUNDARY_TARGET_EMPTY",
                        rule.rule_id,
                        "担任授業期間ルールに一致する有効クラスがありません",
                    )
                )

        rules_by_class: dict[str, list[ResolvedHomeroomBoundaryRuleModel]] = defaultdict(list)
        for rule in resolved:
            rules_by_class[rule.class_id].append(rule)
        for class_id, class_rules in rules_by_class.items():
            ordered_rules = sorted(class_rules, key=lambda item: (item.start_date, item.end_date))
            for left, right in pairwise(ordered_rules):
                if right.start_date <= left.end_date:
                    issues.append(
                        RuleResolutionIssueModel(
                            "HOMEROOM_BOUNDARY_PERIOD_OVERLAP",
                            class_id,
                            (
                                "担任授業期間ルールの期間が重複しています: "
                                f"{left.source_rule_id}/{right.source_rule_id}"
                            ),
                        )
                    )
        return resolved

    def _matches_boundary_rule(
        self,
        rule: HomeroomBoundaryRuleModel,
        attributes: dict[str, object],
    ) -> bool:
        return self._matches_conditions(
            rule,
            attributes,
        )

    def _resolve_lesson_count_rules(
        self,
        input_data: InputDataModel,
        output_days: list[CalendarDayModel],
        ordered_period_ids: tuple[str, ...],
        issues: list[RuleResolutionIssueModel],
    ) -> list[ResolvedLessonCountRuleModel]:
        requirements_by_target: dict[tuple[str, str], list[str]] = defaultdict(list)
        for requirement in input_data.lesson_requirements:
            if requirement.enabled:
                requirements_by_target[(requirement.class_id, requirement.subject_id)].append(
                    requirement.requirement_id
                )
        segments_by_rule: dict[str, list[LessonCountRuleSegmentModel]] = defaultdict(list)
        for segment in input_data.lesson_count_rule_segments:
            segments_by_rule[segment.rule_id].append(segment)

        period_orders = {period_id: order for order, period_id in enumerate(ordered_period_ids)}
        resolved: list[ResolvedLessonCountRuleModel] = []
        for rule_id, segments in sorted(segments_by_rule.items()):
            if not segments or not segments[0].enabled:
                continue
            target = (segments[0].class_id, segments[0].subject_id)
            requirement_ids = requirements_by_target[target]
            if len(requirement_ids) != 1:
                issues.append(
                    RuleResolutionIssueModel(
                        "LESSON_COUNT_RULE_TARGET_UNRESOLVED",
                        rule_id,
                        (
                            "有効なclass_id/subject_idの授業要求を一意に解決できません: "
                            f"class_id={target[0]}, subject_id={target[1]}"
                        ),
                    )
                )
                continue
            target_slots: set[tuple[date, str]] = set()
            for segment in segments:
                for calendar_day in output_days:
                    target_date = calendar_day.target_date
                    if not (segment.start_date <= target_date <= segment.end_date):
                        continue
                    period_ids = (
                        calendar_day.enabled_period_ids
                        if segment.target_period_ids == ("ALL",)
                        else segment.target_period_ids
                    )
                    target_slots.update((target_date, period_id) for period_id in period_ids)
            resolved.append(
                ResolvedLessonCountRuleModel(
                    rule_id=rule_id,
                    requirement_id=requirement_ids[0],
                    class_id=target[0],
                    subject_id=target[1],
                    exact_periods=segments[0].exact_periods,
                    target_slots=tuple(
                        sorted(
                            target_slots,
                            key=lambda item: (item[0], period_orders[item[1]]),
                        )
                    ),
                )
            )
        return resolved

    def _resolve_lesson_count_preference_rules(
        self,
        input_data: InputDataModel,
        output_days: list[CalendarDayModel],
        ordered_period_ids: tuple[str, ...],
        issues: list[RuleResolutionIssueModel],
    ) -> list[ResolvedLessonCountPreferenceRuleModel]:
        requirements_by_target: dict[tuple[str, str], list[str]] = defaultdict(list)
        for requirement in input_data.lesson_requirements:
            if requirement.enabled:
                requirements_by_target[(requirement.class_id, requirement.subject_id)].append(
                    requirement.requirement_id
                )
        segments_by_rule: dict[str, list[LessonCountPreferenceRuleSegmentModel]] = defaultdict(list)
        for segment in input_data.lesson_count_preference_rule_segments:
            segments_by_rule[segment.rule_id].append(segment)

        period_orders = {period_id: order for order, period_id in enumerate(ordered_period_ids)}
        resolved: list[ResolvedLessonCountPreferenceRuleModel] = []
        for rule_id, segments in sorted(segments_by_rule.items()):
            if not segments or not segments[0].enabled:
                continue
            target = (segments[0].class_id, segments[0].subject_id)
            requirement_ids = requirements_by_target[target]
            if len(requirement_ids) != 1:
                issues.append(
                    RuleResolutionIssueModel(
                        "LESSON_COUNT_PREFERENCE_TARGET_UNRESOLVED",
                        rule_id,
                        (
                            "有効なclass_id/subject_idの授業要求を一意に解決できません: "
                            f"class_id={target[0]}, subject_id={target[1]}"
                        ),
                    )
                )
                continue
            target_slots: set[tuple[date, str]] = set()
            for segment in segments:
                for calendar_day in output_days:
                    target_date = calendar_day.target_date
                    if not (segment.start_date <= target_date <= segment.end_date):
                        continue
                    period_ids = (
                        calendar_day.enabled_period_ids
                        if segment.target_period_ids == ("ALL",)
                        else segment.target_period_ids
                    )
                    target_slots.update((target_date, period_id) for period_id in period_ids)
            resolved.append(
                ResolvedLessonCountPreferenceRuleModel(
                    rule_id=rule_id,
                    requirement_id=requirement_ids[0],
                    class_id=target[0],
                    subject_id=target[1],
                    preferred_periods=segments[0].preferred_periods,
                    target_slots=tuple(
                        sorted(
                            target_slots,
                            key=lambda item: (item[0], period_orders[item[1]]),
                        )
                    ),
                )
            )
        return resolved

    def _matches_class(
        self,
        rule: PlacementRuleModel,
        class_model: ClassModel,
        target_date: date,
    ) -> bool:
        if not rule.enabled or rule.target_entity != "class":
            return False
        if rule.campus_id is not None and rule.campus_id != class_model.campus_id:
            return False
        if not self._matches_date(rule, target_date):
            return False
        return self._matches_conditions(
            rule,
            {
                "class_id": class_model.class_id,
                "division": class_model.division,
                "grade": class_model.grade,
                "exam_category": class_model.exam_category,
                "campus_id": class_model.campus_id,
            },
        )

    def _matches_teacher(
        self,
        rule: PlacementRuleModel,
        teacher: TeacherModel,
        target_date: date,
    ) -> bool:
        return (
            rule.enabled
            and rule.target_entity == "teacher"
            and self._matches_date(rule, target_date)
            and self._matches_conditions(rule, {"teacher_id": teacher.teacher_id})
        )

    def _matches_date(self, rule: PlacementRuleModel, target_date: date) -> bool:
        return not (
            (rule.start_date is not None and target_date < rule.start_date)
            or (rule.end_date is not None and target_date > rule.end_date)
            or (rule.weekdays and _WEEKDAYS[target_date.weekday()] not in rule.weekdays)
        )

    def _matches_conditions(
        self,
        rule: PlacementRuleModel | HomeroomBoundaryRuleModel,
        attributes: dict[str, object],
    ) -> bool:
        if not (
            len(rule.condition_fields)
            == len(rule.condition_operators)
            == len(rule.condition_values)
        ):
            return False
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
        actual_text = str(actual).upper() if isinstance(actual, bool) else str(actual)
        if operator == "eq":
            return actual_text == expected
        if operator == "ne":
            return actual_text != expected
        if operator == "in":
            return actual_text in expected.split("/")
        if operator in {"ge", "le", "between"}:
            try:
                actual_number = float(actual_text)
                if operator == "ge":
                    return actual_number >= float(expected)
                if operator == "le":
                    return actual_number <= float(expected)
                lower, upper = (float(value) for value in expected.split("/", maxsplit=1))
                return lower <= actual_number <= upper
            except (TypeError, ValueError):
                return False
        return False

    def _detect_same_priority_conflicts(
        self,
        rules: list[PlacementRuleModel],
        target: str,
        issues: list[RuleResolutionIssueModel],
    ) -> None:
        values: dict[tuple[int, str], set[object]] = defaultdict(set)
        rule_ids: dict[tuple[int, str], list[str]] = defaultdict(list)
        for rule in rules:
            properties: tuple[tuple[str, object | None], ...] = (
                ("allowed_periods", rule.allowed_period_ids or None),
                ("daily_hard_limit", rule.daily_hard_limit),
                ("forbid_first_last_same_day", rule.forbid_first_last_same_day),
                ("attendance_streak_limit", rule.attendance_streak_limit),
                (
                    "preferred_attendance_streak_limit",
                    rule.preferred_attendance_streak_limit,
                ),
                ("required_lesson_periods", rule.required_lesson_period_ids or None),
            )
            for field, value in properties:
                if value is None:
                    continue
                key = (rule.priority, field)
                values[key].add(value)
                rule_ids[key].append(rule.rule_id)
        for (priority, field), proposed_values in values.items():
            if len(proposed_values) > 1:
                issues.append(
                    RuleResolutionIssueModel(
                        "RULE_PRIORITY_CONFLICT",
                        target,
                        (
                            f"同一priorityで{field}が競合しています: priority={priority}, "
                            f"rule_ids={','.join(rule_ids[(priority, field)])}"
                        ),
                    )
                )

    def _resolve_limit(
        self,
        current: int | None,
        proposed: int | None,
        constraint_type: str,
    ) -> int | None:
        if proposed is None:
            return current
        if current is None or constraint_type == "override":
            return proposed
        return min(current, proposed)

    def _resolve_boolean(
        self,
        current: bool | None,
        proposed: bool | None,
        constraint_type: str,
    ) -> bool | None:
        if proposed is None:
            return current
        if current is None or constraint_type == "override":
            return proposed
        return current or proposed


class CandidateBuilderService:
    """Build candidates from active requirements and facts decidable per candidate."""

    def execute(
        self,
        input_data: InputDataModel,
        resolved_rules: ResolvedRuleSetModel,
    ) -> CandidateBuildResultModel:
        classes = {item.class_id: item for item in input_data.classes}
        campuses = {item.campus_id: item for item in input_data.campuses}
        teachers = {item.teacher_id: item for item in input_data.teachers}
        subjects = {item.subject_id: item for item in input_data.subjects}
        teacher_leave_slots = {
            (item.teacher_id, item.target_date, period_id)
            for item in input_data.teacher_leaves
            for period_id in item.unavailable_period_ids
        }
        class_rules = {
            (item.class_id, item.target_date): item for item in resolved_rules.class_date_rules
        }
        prohibited_slots_by_requirement: dict[str, set[tuple[date, str]]] = defaultdict(set)
        for rule in resolved_rules.lesson_count_rules:
            if rule.exact_periods == 0:
                prohibited_slots_by_requirement[rule.requirement_id].update(rule.target_slots)
        output_days = [day for day in input_data.calendar_days if day.output_enabled]
        ordered_periods = sorted(input_data.periods, key=lambda item: item.output_order)
        candidates: list[CandidateSlotModel] = []
        rejection_counts: Counter[tuple[str, str]] = Counter()

        for requirement in (item for item in input_data.lesson_requirements if item.enabled):
            class_model = classes[requirement.class_id]
            teacher = teachers[requirement.teacher_id]
            campus = campuses[class_model.campus_id]
            subject = subjects[requirement.subject_id]
            if not (class_model.enabled and teacher.enabled and campus.enabled and subject.enabled):
                rejection_counts[(requirement.requirement_id, "H14")] += 1
                continue
            for calendar_day in output_days:
                class_rule = class_rules[(class_model.class_id, calendar_day.target_date)]
                allowed_periods = set(class_rule.allowed_period_ids or ())
                for period in ordered_periods:
                    if period.period_id not in calendar_day.enabled_period_ids:
                        rejection_counts[(requirement.requirement_id, "H04")] += 1
                        continue
                    if period.period_id not in allowed_periods:
                        rejection_counts[(requirement.requirement_id, "H13")] += 1
                        continue
                    if (
                        teacher.teacher_id,
                        calendar_day.target_date,
                        period.period_id,
                    ) in teacher_leave_slots:
                        rejection_counts[(requirement.requirement_id, "H05")] += 1
                        continue
                    if (
                        calendar_day.target_date,
                        period.period_id,
                    ) in prohibited_slots_by_requirement[requirement.requirement_id]:
                        rejection_counts[(requirement.requirement_id, "H17")] += 1
                        continue
                    candidate_id = "__".join(
                        (
                            requirement.requirement_id,
                            calendar_day.target_date.isoformat(),
                            period.period_id,
                            teacher.teacher_id,
                        )
                    )
                    candidates.append(
                        CandidateSlotModel(
                            candidate_id=candidate_id,
                            requirement_id=requirement.requirement_id,
                            target_date=calendar_day.target_date,
                            period_id=period.period_id,
                            teacher_id=teacher.teacher_id,
                            campus_id=class_model.campus_id,
                            class_id=class_model.class_id,
                            subject_id=requirement.subject_id,
                        )
                    )
        summaries = tuple(
            CandidateRejectionSummaryModel(requirement_id, rule_id, rejected_count)
            for (requirement_id, rule_id), rejected_count in sorted(rejection_counts.items())
        )
        return CandidateBuildResultModel(tuple(candidates), summaries)

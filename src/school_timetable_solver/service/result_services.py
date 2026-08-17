from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, timedelta
from itertools import pairwise
from types import MappingProxyType

from school_timetable_solver.model.input_models import InputDataModel, TeacherDayOffRuleModel
from school_timetable_solver.model.result_models import (
    CampusColumnGroupModel,
    DailyTimetableModel,
    OutputLessonModel,
    OutputPeriodModel,
    OutputTeacherLeaveModel,
    RoomColumnModel,
    ScheduledLessonDraftModel,
    ScheduledLessonModel,
    ScheduledTeacherDayOffModel,
    TimetableDocumentModel,
    ValidationIssueModel,
    ValidationReportModel,
)
from school_timetable_solver.model.solver_models import (
    CandidateBuildResultModel,
    EffectiveClassDateRuleModel,
    ResolvedRuleSetModel,
)


class AssignRoomsService:
    """Map anonymous solver room indexes to stable campus room IDs."""

    def execute(
        self,
        input_data: InputDataModel,
        lessons: tuple[ScheduledLessonDraftModel, ...],
    ) -> tuple[ScheduledLessonModel, ...]:
        campus_orders = {
            campus.campus_id: campus.output_order
            for campus in input_data.campuses
            if campus.enabled
        }
        room_orders: dict[str, int] = {}
        rooms_by_campus: dict[str, list[str]] = defaultdict(list)
        for room in sorted(input_data.rooms, key=lambda item: item.output_order):
            if room.enabled and room.campus_id in campus_orders:
                rooms_by_campus[room.campus_id].append(room.room_id)
                room_orders[room.room_id] = room.output_order
        period_orders = {period.period_id: period.output_order for period in input_data.periods}
        assigned: list[ScheduledLessonModel] = []
        for lesson in lessons:
            room_ids = rooms_by_campus.get(lesson.campus_id, ())
            if not 0 <= lesson.room_index < len(room_ids):
                raise ValueError(
                    "匿名教室番号が有効教室の範囲外です: "
                    f"{lesson.campus_id}/{lesson.target_date}/{lesson.class_id} "
                    f"room_index={lesson.room_index}, rooms={len(room_ids)}"
                )
            room_id = room_ids[lesson.room_index]
            assigned.append(
                ScheduledLessonModel(
                    requirement_id=lesson.requirement_id,
                    target_date=lesson.target_date,
                    period_id=lesson.period_id,
                    teacher_id=lesson.teacher_id,
                    room_id=room_id,
                    campus_id=lesson.campus_id,
                    class_id=lesson.class_id,
                    subject_id=lesson.subject_id,
                )
            )
        assigned.sort(
            key=lambda item: (
                item.target_date,
                period_orders[item.period_id],
                campus_orders[item.campus_id],
                room_orders[item.room_id],
            )
        )
        return tuple(assigned)


class ValidateResultService:
    """Independently verify all input/output-contract hard rules."""

    def execute(
        self,
        input_data: InputDataModel,
        resolved_rules: ResolvedRuleSetModel,
        lessons: tuple[ScheduledLessonModel, ...],
        candidate_result: CandidateBuildResultModel | None = None,
        teacher_day_offs: tuple[ScheduledTeacherDayOffModel, ...] = (),
    ) -> ValidationReportModel:
        issues: list[ValidationIssueModel] = []
        self._validate_required_counts(input_data, lessons, issues)
        self._validate_lesson_counts_in_scope(resolved_rules, lessons, issues)
        self._validate_homeroom_attendance_boundaries(resolved_rules, lessons, issues)
        self._validate_required_lesson_slots(resolved_rules, lessons, issues)
        self._validate_overlaps(lessons, issues)
        self._validate_class_pair_overlaps(input_data, lessons, issues)
        self._validate_class_successors(input_data, lessons, issues)
        self._validate_candidate_facts(input_data, resolved_rules, lessons, issues)
        self._validate_daily_limits(input_data, resolved_rules, lessons, issues)
        self._validate_first_last_periods(input_data, resolved_rules, lessons, issues)
        self._validate_attendance_streaks(input_data, resolved_rules, lessons, issues)
        self._validate_campus_transfers(input_data, lessons, issues)
        self._validate_teacher_day_offs(input_data, lessons, teacher_day_offs, issues)
        self._report_teacher_day_off_distribution_preference(
            input_data,
            teacher_day_offs,
            issues,
        )
        self._validate_teacher_leave_annotation_capacity(
            input_data,
            teacher_day_offs,
            issues,
        )
        self._validate_class_room_continuity(lessons, issues)
        self._validate_class_long_internal_gaps(input_data, lessons, issues)
        self._report_room_priority_preference(input_data, lessons, issues)
        self._report_homeroom_boundary_slot_preference(
            input_data,
            resolved_rules,
            lessons,
            issues,
        )
        self._report_room_change_gap_preference(input_data, lessons, issues)
        self._report_teacher_campus_transfer_gap_preference(input_data, lessons, issues)
        self._report_teacher_late_then_early_preference(input_data, lessons, issues)
        self._report_class_daily_contiguity_preference(input_data, lessons, issues)
        self._report_class_consecutive_attendance_preference(
            resolved_rules,
            lessons,
            issues,
        )
        self._report_class_single_lesson_day_preference(input_data, lessons, issues)
        self._report_class_subject_consecutive_repeat_preference(
            input_data,
            lessons,
            issues,
        )
        self._report_class_subject_daily_repeat_preference(lessons, issues)
        self._report_lesson_count_in_scope_preference(
            resolved_rules,
            lessons,
            issues,
        )
        if candidate_result is not None:
            self._report_class_subject_schedule_balance_preference(
                input_data,
                resolved_rules,
                candidate_result,
                lessons,
                issues,
            )
        self._report_class_subject_double_then_next_day_preference(lessons, issues)
        return ValidationReportModel(tuple(issues))

    def _validate_teacher_day_offs(
        self,
        input_data: InputDataModel,
        lessons: tuple[ScheduledLessonModel, ...],
        teacher_day_offs: tuple[ScheduledTeacherDayOffModel, ...],
        issues: list[ValidationIssueModel],
    ) -> None:
        selected_counts = Counter(
            (day_off.teacher_id, day_off.target_date) for day_off in teacher_day_offs
        )
        for key, count in selected_counts.items():
            if count > 1:
                issues.append(self._issue("H18", str(key), "同じ教師休業日が重複しています"))

        allowed_slots = {
            (rule.teacher_id, target_date)
            for rule in input_data.teacher_day_off_rules
            if rule.enabled
            for target_date in rule.eligible_dates
        }
        for key in selected_counts:
            if key not in allowed_slots:
                issues.append(self._issue("H18", str(key), "休日日数ルール対象外の休業日です"))

        worked_days = {(lesson.teacher_id, lesson.target_date) for lesson in lessons}
        for key in selected_counts.keys() & worked_days:
            issues.append(self._issue("H18", str(key), "終日休みに授業が配置されています"))

        selected_slots = set(selected_counts)
        for rule in input_data.teacher_day_off_rules:
            if not rule.enabled:
                continue
            actual = sum(
                (rule.teacher_id, target_date) in selected_slots
                for target_date in rule.eligible_dates
            )
            count_is_valid = (
                actual == rule.required_days_off
                if rule.required_days_off is not None
                else (
                    rule.minimum_days_off is not None
                    and rule.maximum_days_off is not None
                    and rule.minimum_days_off <= actual <= rule.maximum_days_off
                )
            )
            if not count_is_valid:
                issues.append(
                    self._issue(
                        "H18",
                        rule.rule_id,
                        (
                            "期間内の教師休日日数が条件を満たしません: "
                            f"actual={actual}, required={rule.required_days_off}, "
                            f"minimum={rule.minimum_days_off}, maximum={rule.maximum_days_off}"
                        ),
                    )
                )

        rules_by_group: dict[tuple[str, str], list[TeacherDayOffRuleModel]] = defaultdict(list)
        for rule in input_data.teacher_day_off_rules:
            if rule.enabled and rule.quota_group_id is not None:
                rules_by_group[(rule.teacher_id, rule.quota_group_id)].append(rule)
        for (teacher_id, group_id), rules in rules_by_group.items():
            actual = sum(
                (teacher_id, target_date) in selected_slots
                for rule in rules
                for target_date in rule.eligible_dates
            )
            required = rules[0].group_required_days_off
            if actual != required:
                issues.append(
                    self._issue(
                        "H18",
                        group_id,
                        f"教師休日グループ合計が一致しません: actual={actual}, required={required}",
                    )
                )

    def _report_teacher_day_off_distribution_preference(
        self,
        input_data: InputDataModel,
        teacher_day_offs: tuple[ScheduledTeacherDayOffModel, ...],
        issues: list[ValidationIssueModel],
    ) -> None:
        selected_slots = {(day_off.teacher_id, day_off.target_date) for day_off in teacher_day_offs}
        for rule in input_data.teacher_day_off_rules:
            if not rule.enabled or rule.preferred_days_off is None:
                continue
            actual = sum(
                (rule.teacher_id, target_date) in selected_slots
                for target_date in rule.eligible_dates
            )
            if actual == rule.preferred_days_off:
                continue
            issues.append(
                ValidationIssueModel(
                    "S21",
                    "WARNING",
                    rule.rule_id,
                    (
                        "期間内の教師休日日数が希望値と異なります: "
                        f"actual={actual}, preferred={rule.preferred_days_off}"
                    ),
                )
            )

    def _validate_teacher_leave_annotation_capacity(
        self,
        input_data: InputDataModel,
        teacher_day_offs: tuple[ScheduledTeacherDayOffModel, ...],
        issues: list[ValidationIssueModel],
    ) -> None:
        teachers = {teacher.teacher_id: teacher for teacher in input_data.teachers}
        period_ids = {period.period_id for period in input_data.periods}
        room_counts = Counter(room.campus_id for room in input_data.rooms if room.enabled)
        required_cells: Counter[tuple[str, date]] = Counter()
        for leave in input_data.teacher_leaves:
            teacher = teachers[leave.teacher_id]
            required_cells[(teacher.home_campus_id, leave.target_date)] += (
                1 if set(leave.unavailable_period_ids) == period_ids else 2
            )
        for day_off in teacher_day_offs:
            teacher = teachers[day_off.teacher_id]
            required_cells[(teacher.home_campus_id, day_off.target_date)] += 1
        for (campus_id, target_date), required in required_cells.items():
            available = room_counts[campus_id]
            if required > available:
                issues.append(
                    self._issue(
                        "H19",
                        f"{campus_id}/{target_date}",
                        f"教師休み注記容量超過: required={required}, available={available}",
                    )
                )

    def _validate_lesson_counts_in_scope(
        self,
        resolved_rules: ResolvedRuleSetModel,
        lessons: tuple[ScheduledLessonModel, ...],
        issues: list[ValidationIssueModel],
    ) -> None:
        lesson_slots_by_requirement: dict[str, set[tuple[date, str]]] = defaultdict(set)
        for lesson in lessons:
            lesson_slots_by_requirement[lesson.requirement_id].add(
                (lesson.target_date, lesson.period_id)
            )
        for rule in resolved_rules.lesson_count_rules:
            generated = len(
                lesson_slots_by_requirement[rule.requirement_id].intersection(rule.target_slots)
            )
            if generated != rule.exact_periods:
                issues.append(
                    self._issue(
                        "H17",
                        rule.rule_id,
                        (
                            "指定範囲内授業数不一致: "
                            f"exact={rule.exact_periods}, generated={generated}"
                        ),
                    )
                )

    def _validate_required_lesson_slots(
        self,
        resolved_rules: ResolvedRuleSetModel,
        lessons: tuple[ScheduledLessonModel, ...],
        issues: list[ValidationIssueModel],
    ) -> None:
        occupied_slots = {
            (lesson.class_id, lesson.target_date, lesson.period_id) for lesson in lessons
        }
        for rule in resolved_rules.class_date_rules:
            for period_id in rule.required_lesson_period_ids:
                slot = (rule.class_id, rule.target_date, period_id)
                if slot not in occupied_slots:
                    issues.append(
                        self._issue(
                            "H21",
                            f"{rule.class_id}/{rule.target_date}/{period_id}",
                            "必須授業時限に授業がありません",
                        )
                    )

    def _report_lesson_count_in_scope_preference(
        self,
        resolved_rules: ResolvedRuleSetModel,
        lessons: tuple[ScheduledLessonModel, ...],
        issues: list[ValidationIssueModel],
    ) -> None:
        lesson_slots_by_requirement: dict[str, set[tuple[date, str]]] = defaultdict(set)
        for lesson in lessons:
            lesson_slots_by_requirement[lesson.requirement_id].add(
                (lesson.target_date, lesson.period_id)
            )
        for rule in resolved_rules.lesson_count_preference_rules:
            generated = len(
                lesson_slots_by_requirement[rule.requirement_id].intersection(rule.target_slots)
            )
            if generated == rule.preferred_periods:
                continue
            issues.append(
                ValidationIssueModel(
                    "S17",
                    "WARNING",
                    rule.rule_id,
                    (
                        "指定範囲内授業数が希望値と異なります: "
                        f"preferred={rule.preferred_periods}, generated={generated}, "
                        f"deviation={abs(generated - rule.preferred_periods)}"
                    ),
                )
            )

    def _validate_required_counts(
        self,
        input_data: InputDataModel,
        lessons: tuple[ScheduledLessonModel, ...],
        issues: list[ValidationIssueModel],
    ) -> None:
        requirements = {
            requirement.requirement_id: requirement
            for requirement in input_data.lesson_requirements
            if requirement.enabled
        }
        counts = Counter(lesson.requirement_id for lesson in lessons)
        for requirement in requirements.values():
            generated = counts[requirement.requirement_id]
            if generated != requirement.required_periods:
                issues.append(
                    self._issue(
                        "H06",
                        requirement.requirement_id,
                        (
                            "必要コマ数不一致: "
                            f"required={requirement.required_periods}, generated={generated}"
                        ),
                    )
                )
        for lesson in lessons:
            requirement = requirements.get(lesson.requirement_id)
            if requirement is None or (
                requirement.class_id != lesson.class_id
                or requirement.subject_id != lesson.subject_id
                or requirement.teacher_id != lesson.teacher_id
            ):
                issues.append(
                    self._issue(
                        "H06",
                        self._lesson_target(lesson),
                        "授業結果が有効な授業要求と一致しません",
                    )
                )

    def _validate_overlaps(
        self,
        lessons: tuple[ScheduledLessonModel, ...],
        issues: list[ValidationIssueModel],
    ) -> None:
        specifications = (
            (
                "H01",
                "教師",
                Counter((item.teacher_id, item.target_date, item.period_id) for item in lessons),
            ),
            (
                "H02",
                "クラス",
                Counter((item.class_id, item.target_date, item.period_id) for item in lessons),
            ),
            (
                "H03",
                "教室",
                Counter((item.room_id, item.target_date, item.period_id) for item in lessons),
            ),
        )
        for rule_id, label, counts in specifications:
            for key, count in counts.items():
                if count > 1:
                    issues.append(
                        self._issue(rule_id, str(key), f"{label}が同一時限に重複しています")
                    )

    def _validate_class_pair_overlaps(
        self,
        input_data: InputDataModel,
        lessons: tuple[ScheduledLessonModel, ...],
        issues: list[ValidationIssueModel],
    ) -> None:
        occupied_slots_by_class: dict[str, set[tuple[date, str]]] = defaultdict(set)
        for lesson in lessons:
            occupied_slots_by_class[lesson.class_id].add((lesson.target_date, lesson.period_id))
        for rule in input_data.class_pair_overlap_rules:
            if not rule.enabled:
                continue
            overlapping_slots = sorted(
                occupied_slots_by_class[rule.first_class_id]
                & occupied_slots_by_class[rule.second_class_id]
            )
            for target_date, period_id in overlapping_slots:
                issues.append(
                    self._issue(
                        "H22",
                        f"{rule.rule_id}/{target_date}/{period_id}",
                        (
                            "重複禁止クラス組が同一時限に配置されています: "
                            f"{rule.first_class_id}/{rule.second_class_id}"
                        ),
                    )
                )

    def _validate_class_successors(
        self,
        input_data: InputDataModel,
        lessons: tuple[ScheduledLessonModel, ...],
        issues: list[ValidationIssueModel],
    ) -> None:
        first_classes_by_second: dict[str, set[str]] = defaultdict(set)
        for rule in input_data.class_pair_overlap_rules:
            if rule.enabled:
                first_classes_by_second[rule.second_class_id].add(rule.first_class_id)
        if not first_classes_by_second:
            return
        period_orders = {period.period_id: period.output_order for period in input_data.periods}
        lessons_by_class_day: dict[tuple[str, date], list[ScheduledLessonModel]] = defaultdict(list)
        for lesson in lessons:
            lessons_by_class_day[(lesson.class_id, lesson.target_date)].append(lesson)

        second_days = sorted(
            (class_id, target_date)
            for class_id, target_date in lessons_by_class_day
            if class_id in first_classes_by_second
        )
        for second_class_id, target_date in second_days:
            second_lessons = lessons_by_class_day[(second_class_id, target_date)]
            earliest_second = min(second_lessons, key=lambda item: period_orders[item.period_id])
            earliest_order = period_orders[earliest_second.period_id]
            valid_first = False
            for first_class_id in sorted(first_classes_by_second[second_class_id]):
                first_lessons = lessons_by_class_day.get((first_class_id, target_date), ())
                if not first_lessons:
                    continue
                latest_first = max(first_lessons, key=lambda item: period_orders[item.period_id])
                if period_orders[latest_first.period_id] + 1 != earliest_order:
                    continue
                if latest_first.room_id != earliest_second.room_id:
                    continue
                valid_first = True
                break
            if not valid_first:
                issues.append(
                    self._issue(
                        "H23",
                        f"{second_class_id}/{target_date}",
                        (
                            "second classの最初のコマが、同一教室での"
                            "first class最終コマ直後になっていません"
                        ),
                    )
                )

    def _validate_candidate_facts(
        self,
        input_data: InputDataModel,
        resolved_rules: ResolvedRuleSetModel,
        lessons: tuple[ScheduledLessonModel, ...],
        issues: list[ValidationIssueModel],
    ) -> None:
        calendars = {day.target_date: day for day in input_data.calendar_days if day.output_enabled}
        periods = {period.period_id: period for period in input_data.periods}
        teacher_leave_slots = {
            (item.teacher_id, item.target_date, period_id)
            for item in input_data.teacher_leaves
            for period_id in item.unavailable_period_ids
        }
        class_rules = {
            (item.class_id, item.target_date): item for item in resolved_rules.class_date_rules
        }
        campuses = {item.campus_id: item for item in input_data.campuses}
        rooms = {item.room_id: item for item in input_data.rooms}
        classes = {item.class_id: item for item in input_data.classes}
        teachers = {item.teacher_id: item for item in input_data.teachers}
        subjects = {item.subject_id: item for item in input_data.subjects}
        for lesson in lessons:
            target = self._lesson_target(lesson)
            calendar = calendars.get(lesson.target_date)
            if calendar is None:
                issues.append(self._issue("H04", target, "出力対象外日への配置です"))
            elif lesson.period_id not in calendar.enabled_period_ids:
                issues.append(self._issue("H04", target, "日付上利用不可時限への配置です"))
            if lesson.period_id not in periods:
                issues.append(self._issue("H04", target, "未知の時限への配置です"))
            if (
                lesson.teacher_id,
                lesson.target_date,
                lesson.period_id,
            ) in teacher_leave_slots:
                issues.append(self._issue("H05", target, "教師休み日時への配置です"))
            rule = class_rules.get((lesson.class_id, lesson.target_date))
            if rule is None or lesson.period_id not in (rule.allowed_period_ids or ()):
                issues.append(self._issue("H13", target, "クラス許可時限外への配置です"))

            room = rooms.get(lesson.room_id)
            class_model = classes.get(lesson.class_id)
            teacher = teachers.get(lesson.teacher_id)
            subject = subjects.get(lesson.subject_id)
            campus = campuses.get(lesson.campus_id)
            if (
                room is None
                or class_model is None
                or teacher is None
                or subject is None
                or campus is None
                or not room.enabled
                or not class_model.enabled
                or not teacher.enabled
                or not subject.enabled
                or not campus.enabled
            ):
                issues.append(self._issue("H14", target, "未知または無効なマスタへの配置です"))
                continue
            if room.campus_id != class_model.campus_id or lesson.campus_id != class_model.campus_id:
                issues.append(self._issue("H14", target, "教室とクラス所属校舎が一致しません"))

    def _validate_daily_limits(
        self,
        input_data: InputDataModel,
        resolved_rules: ResolvedRuleSetModel,
        lessons: tuple[ScheduledLessonModel, ...],
        issues: list[ValidationIssueModel],
    ) -> None:
        class_limits = {
            (item.class_id, item.target_date): item.daily_hard_limit
            for item in resolved_rules.class_date_rules
        }
        teacher_limits = {
            (item.teacher_id, item.target_date): item.daily_hard_limit
            for item in resolved_rules.teacher_date_rules
        }
        requirement_limits = {
            item.requirement_id: item.max_periods_per_day
            for item in input_data.lesson_requirements
            if item.enabled
        }
        for key, count in Counter((item.class_id, item.target_date) for item in lessons).items():
            limit = class_limits.get(key)
            if limit is not None and count > limit:
                issues.append(self._issue("H07", str(key), f"クラス日別上限超過: {count}>{limit}"))
        for key, count in Counter(
            (item.requirement_id, item.target_date) for item in lessons
        ).items():
            limit = requirement_limits.get(key[0])
            if limit is not None and count > limit:
                issues.append(
                    self._issue("H07", str(key), f"授業要求日別上限超過: {count}>{limit}")
                )
        for key, count in Counter((item.teacher_id, item.target_date) for item in lessons).items():
            limit = teacher_limits.get(key)
            if limit is not None and count > limit:
                issues.append(self._issue("H08", str(key), f"教師日別上限超過: {count}>{limit}"))

    def _validate_first_last_periods(
        self,
        input_data: InputDataModel,
        resolved_rules: ResolvedRuleSetModel,
        lessons: tuple[ScheduledLessonModel, ...],
        issues: list[ValidationIssueModel],
    ) -> None:
        period_orders = {period.period_id: period.output_order for period in input_data.periods}
        forbidden_by_teacher_date = {
            (item.teacher_id, item.target_date): item.forbid_first_last_same_day
            for item in resolved_rules.teacher_date_rules
        }
        grouped: dict[tuple[str, date], set[int]] = defaultdict(set)
        for lesson in lessons:
            if lesson.period_id in period_orders:
                grouped[(lesson.teacher_id, lesson.target_date)].add(
                    period_orders[lesson.period_id]
                )
        if len(period_orders) < 2:
            return
        first_period_order = min(period_orders.values())
        last_period_order = max(period_orders.values())
        for key, orders in grouped.items():
            if (
                forbidden_by_teacher_date.get(key, False)
                and first_period_order in orders
                and last_period_order in orders
            ):
                issues.append(
                    self._issue(
                        "H09",
                        str(key),
                        (
                            "教師が同日に最初と最後の時限を担当しています: "
                            f"occupied_periods={tuple(sorted(orders))}"
                        ),
                    )
                )

    def _validate_homeroom_attendance_boundaries(
        self,
        resolved_rules: ResolvedRuleSetModel,
        lessons: tuple[ScheduledLessonModel, ...],
        issues: list[ValidationIssueModel],
    ) -> None:
        for rule in resolved_rules.homeroom_boundary_rules:
            attendance_requirement_ids = set(rule.attendance_requirement_ids)
            period_lessons = [
                lesson
                for lesson in lessons
                if lesson.class_id == rule.class_id
                and rule.start_date <= lesson.target_date <= rule.end_date
                and lesson.requirement_id in attendance_requirement_ids
            ]
            target = f"{rule.source_rule_id}/{rule.class_id}"
            if not period_lessons:
                issues.append(
                    ValidationIssueModel(
                        "H20",
                        "ERROR",
                        target,
                        "対象期間内にクラス授業がありません",
                    )
                )
                continue
            boundary_dates = {
                min(lesson.target_date for lesson in period_lessons),
                max(lesson.target_date for lesson in period_lessons),
            }
            eligible_requirement_ids = set(rule.eligible_requirement_ids)
            for boundary_date in sorted(boundary_dates):
                if not any(
                    lesson.target_date == boundary_date
                    and lesson.requirement_id in eligible_requirement_ids
                    for lesson in period_lessons
                ):
                    issues.append(
                        ValidationIssueModel(
                            "H20",
                            "ERROR",
                            f"{target}/{boundary_date}",
                            "実際の初回・最終登校日に担任の通常授業がありません",
                        )
                    )

    def _report_homeroom_boundary_slot_preference(
        self,
        input_data: InputDataModel,
        resolved_rules: ResolvedRuleSetModel,
        lessons: tuple[ScheduledLessonModel, ...],
        issues: list[ValidationIssueModel],
    ) -> None:
        period_orders = {period.period_id: period.output_order for period in input_data.periods}
        for rule in resolved_rules.homeroom_boundary_rules:
            class_period_lessons = [
                lesson
                for lesson in lessons
                if lesson.class_id == rule.class_id
                and rule.start_date <= lesson.target_date <= rule.end_date
            ]
            attendance_requirement_ids = set(rule.attendance_requirement_ids)
            attendance_lessons = [
                lesson
                for lesson in class_period_lessons
                if lesson.requirement_id in attendance_requirement_ids
            ]
            if not attendance_lessons:
                continue
            first_date = min(lesson.target_date for lesson in attendance_lessons)
            last_date = max(lesson.target_date for lesson in attendance_lessons)
            eligible_requirement_ids = set(rule.eligible_requirement_ids)
            checks = (
                (
                    "first",
                    first_date,
                    min(
                        (
                            lesson
                            for lesson in class_period_lessons
                            if lesson.target_date == first_date
                        ),
                        key=lambda item: period_orders[item.period_id],
                    ),
                ),
                (
                    "last",
                    last_date,
                    max(
                        (
                            lesson
                            for lesson in class_period_lessons
                            if lesson.target_date == last_date
                        ),
                        key=lambda item: period_orders[item.period_id],
                    ),
                ),
            )
            for boundary_name, boundary_date, edge_lesson in checks:
                if edge_lesson.requirement_id in eligible_requirement_ids:
                    continue
                issues.append(
                    ValidationIssueModel(
                        "S20",
                        "WARNING",
                        f"{rule.source_rule_id}/{rule.class_id}/{boundary_date}/{boundary_name}",
                        "境界日の最初または最後の授業が担任の通常授業ではありません",
                    )
                )

    def _validate_attendance_streaks(
        self,
        input_data: InputDataModel,
        resolved_rules: ResolvedRuleSetModel,
        lessons: tuple[ScheduledLessonModel, ...],
        issues: list[ValidationIssueModel],
    ) -> None:
        attendance = {(item.class_id, item.target_date) for item in lessons}
        dates = tuple(
            sorted(day.target_date for day in input_data.calendar_days if day.output_enabled)
        )
        for group_id, class_ids, limits, _ in self._attendance_group_data(resolved_rules):
            attendance_streak = 0
            previous_date: date | None = None
            for target_date in dates:
                attends = any((class_id, target_date) in attendance for class_id in class_ids)
                if not attends:
                    attendance_streak = 0
                    previous_date = None
                    continue
                attendance_streak = (
                    attendance_streak + 1
                    if previous_date is not None
                    and target_date - previous_date == timedelta(days=1)
                    else 1
                )
                previous_date = target_date
                limit = limits.get(target_date)
                if limit is None or attendance_streak <= limit:
                    continue
                issues.append(
                    self._issue(
                        "H10",
                        f"{group_id}/{target_date}",
                        (
                            "最大連続登校日数を超過しています: "
                            f"classes={'|'.join(class_ids)}, {attendance_streak}>{limit}"
                        ),
                    )
                )

    def _report_class_consecutive_attendance_preference(
        self,
        resolved_rules: ResolvedRuleSetModel,
        lessons: tuple[ScheduledLessonModel, ...],
        issues: list[ValidationIssueModel],
    ) -> None:
        attendance_dates: dict[str, set[date]] = defaultdict(set)
        for lesson in lessons:
            attendance_dates[lesson.class_id].add(lesson.target_date)

        for group_id, class_ids, _, preferences in self._attendance_group_data(resolved_rules):
            class_dates = set().union(
                *(attendance_dates.get(class_id, set()) for class_id in class_ids)
            )
            streak: list[date] = []
            for target_date in sorted(class_dates):
                if streak and target_date - streak[-1] != timedelta(days=1):
                    self._append_attendance_preference_issue(
                        group_id,
                        class_ids,
                        streak,
                        preferences,
                        issues,
                    )
                    streak = []
                streak.append(target_date)
            self._append_attendance_preference_issue(
                group_id,
                class_ids,
                streak,
                preferences,
                issues,
            )

    def _attendance_group_data(
        self,
        resolved_rules: ResolvedRuleSetModel,
    ) -> tuple[
        tuple[str, tuple[str, ...], dict[date, int | None], dict[date, int | None]],
        ...,
    ]:
        if resolved_rules.attendance_groups:
            return tuple(
                (
                    group.source_pair_rule_id or group.class_ids[0],
                    group.class_ids,
                    dict(group.attendance_streak_limits),
                    dict(group.preferred_attendance_streak_limits),
                )
                for group in resolved_rules.attendance_groups
            )

        rules_by_class: dict[str, list[EffectiveClassDateRuleModel]] = defaultdict(list)
        for rule in resolved_rules.class_date_rules:
            rules_by_class[rule.class_id].append(rule)
        return tuple(
            (
                class_id,
                (class_id,),
                {rule.target_date: rule.attendance_streak_limit for rule in class_rules},
                {rule.target_date: rule.preferred_attendance_streak_limit for rule in class_rules},
            )
            for class_id, class_rules in sorted(rules_by_class.items())
        )

    def _append_attendance_preference_issue(
        self,
        group_id: str,
        class_ids: tuple[str, ...],
        streak: list[date],
        preferences: dict[date, int | None],
        issues: list[ValidationIssueModel],
    ) -> None:
        if not streak:
            return
        daily_preferences = [preferences.get(target_date) for target_date in streak]
        penalty = sum(
            max(0, streak_length - preferred_limit)
            for streak_length, preferred_limit in enumerate(daily_preferences, start=1)
            if preferred_limit is not None
        )
        if penalty == 0:
            return
        configured_limits = sorted({limit for limit in daily_preferences if limit is not None})
        issues.append(
            ValidationIssueModel(
                "S18",
                "WARNING",
                f"{group_id}/{streak[0]}/{streak[-1]}",
                (
                    "連続登校日数が推奨上限を超えています: "
                    f"classes={'|'.join(class_ids)}, "
                    f"days={len(streak)}, preferred_limits={configured_limits}, "
                    f"penalty={penalty}"
                ),
            )
        )

    def _validate_campus_transfers(
        self,
        input_data: InputDataModel,
        lessons: tuple[ScheduledLessonModel, ...],
        issues: list[ValidationIssueModel],
    ) -> None:
        period_orders = {period.period_id: period.output_order for period in input_data.periods}
        lessons_by_teacher_day: dict[tuple[str, date], list[ScheduledLessonModel]] = defaultdict(
            list
        )
        for lesson in lessons:
            lessons_by_teacher_day[(lesson.teacher_id, lesson.target_date)].append(lesson)
        for key, daily_lessons in lessons_by_teacher_day.items():
            ordered = sorted(daily_lessons, key=lambda item: period_orders[item.period_id])
            campus_ids = {lesson.campus_id for lesson in ordered}
            if len(campus_ids) > 2:
                issues.append(
                    self._issue(
                        "H11",
                        str(key),
                        f"同一教師・同一日に3校舎以上へ配置されています: {sorted(campus_ids)}",
                    )
                )
            transitions = [
                (left, right)
                for left, right in pairwise(ordered)
                if left.campus_id != right.campus_id
            ]
            if len(transitions) > 1:
                issues.append(
                    self._issue(
                        "H11",
                        str(key),
                        f"同一日に校舎間を2回以上移動しています: transitions={len(transitions)}",
                    )
                )
            for left, right in transitions:
                gap = period_orders[right.period_id] - period_orders[left.period_id] - 1
                if gap < 1:
                    issues.append(
                        self._issue(
                            "H11",
                            str(key),
                            (
                                "校舎移動の前後に空きコマがありません: "
                                f"{left.campus_id}/{left.period_id} -> "
                                f"{right.campus_id}/{right.period_id}"
                            ),
                        )
                    )

    def _report_teacher_campus_transfer_gap_preference(
        self,
        input_data: InputDataModel,
        lessons: tuple[ScheduledLessonModel, ...],
        issues: list[ValidationIssueModel],
    ) -> None:
        period_orders = {period.period_id: period.output_order for period in input_data.periods}
        lessons_by_teacher_day: dict[tuple[str, date], list[ScheduledLessonModel]] = defaultdict(
            list
        )
        for lesson in lessons:
            lessons_by_teacher_day[(lesson.teacher_id, lesson.target_date)].append(lesson)
        for key, daily_lessons in lessons_by_teacher_day.items():
            ordered = sorted(daily_lessons, key=lambda item: period_orders[item.period_id])
            for left, right in pairwise(ordered):
                if left.campus_id == right.campus_id:
                    continue
                gap = period_orders[right.period_id] - period_orders[left.period_id] - 1
                if gap == 1:
                    issues.append(
                        ValidationIssueModel(
                            "S22",
                            "WARNING",
                            str(key),
                            (
                                "校舎移動の空きが1コマです。2コマ以上を推奨します: "
                                f"{left.campus_id}/{left.period_id} -> "
                                f"{right.campus_id}/{right.period_id}"
                            ),
                        )
                    )

    def _report_teacher_late_then_early_preference(
        self,
        input_data: InputDataModel,
        lessons: tuple[ScheduledLessonModel, ...],
        issues: list[ValidationIssueModel],
    ) -> None:
        if not input_data.periods:
            return
        first_period = min(input_data.periods, key=lambda item: item.output_order)
        last_period = max(input_data.periods, key=lambda item: item.output_order)
        occupied = {(lesson.teacher_id, lesson.target_date, lesson.period_id) for lesson in lessons}
        late_slots = sorted(
            (teacher_id, target_date)
            for teacher_id, target_date, period_id in occupied
            if period_id == last_period.period_id
        )
        for teacher_id, target_date in late_slots:
            next_date = target_date + timedelta(days=1)
            if (teacher_id, next_date, first_period.period_id) not in occupied:
                continue
            issues.append(
                ValidationIssueModel(
                    "S23",
                    "WARNING",
                    f"{teacher_id}/{target_date}/{next_date}",
                    (
                        "教師が最終時限を担当した翌暦日の最初時限にも配置されています: "
                        f"{last_period.period_id} -> {first_period.period_id}"
                    ),
                )
            )

    def _validate_class_room_continuity(
        self,
        lessons: tuple[ScheduledLessonModel, ...],
        issues: list[ValidationIssueModel],
    ) -> None:
        rooms_by_class_day: dict[tuple[str, date], set[str]] = defaultdict(set)
        for lesson in lessons:
            rooms_by_class_day[(lesson.class_id, lesson.target_date)].add(lesson.room_id)

        for key, room_ids in rooms_by_class_day.items():
            if len(room_ids) > 1:
                issues.append(
                    self._issue(
                        "H15",
                        str(key),
                        f"同一クラス・同一日に複数教室へ配置されています: {sorted(room_ids)}",
                    )
                )

    def _validate_class_long_internal_gaps(
        self,
        input_data: InputDataModel,
        lessons: tuple[ScheduledLessonModel, ...],
        issues: list[ValidationIssueModel],
    ) -> None:
        period_indexes = {
            period.period_id: index
            for index, period in enumerate(
                sorted(input_data.periods, key=lambda item: item.output_order)
            )
        }
        periods_by_class_day: dict[tuple[str, date], set[int]] = defaultdict(set)
        for lesson in lessons:
            period_index = period_indexes.get(lesson.period_id)
            if period_index is not None:
                periods_by_class_day[(lesson.class_id, lesson.target_date)].add(period_index)

        for key, period_index_set in periods_by_class_day.items():
            ordered = sorted(period_index_set)
            long_gaps = [
                (left_index + 1, right_index + 1, right_index - left_index - 1)
                for left_index, right_index in pairwise(ordered)
                if right_index - left_index - 1 >= 2
            ]
            if long_gaps:
                issues.append(
                    self._issue(
                        "H16",
                        str(key),
                        (
                            "同一クラスの授業間に2コマ以上連続する空きがあります: "
                            f"授業間={long_gaps}"
                        ),
                    )
                )

    def _report_room_change_gap_preference(
        self,
        input_data: InputDataModel,
        lessons: tuple[ScheduledLessonModel, ...],
        issues: list[ValidationIssueModel],
    ) -> None:
        excluded_transitions = {
            (rule.first_class_id, rule.second_class_id)
            for rule in input_data.class_pair_overlap_rules
            if rule.enabled
        }
        ordered_periods = tuple(sorted(input_data.periods, key=lambda item: item.output_order))
        classes_by_room_day_period = {
            (lesson.room_id, lesson.target_date, lesson.period_id): lesson.class_id
            for lesson in lessons
        }
        room_days = {(lesson.room_id, lesson.target_date) for lesson in lessons}
        for room_id, target_date in room_days:
            for left_period, right_period in pairwise(ordered_periods):
                left_class_id = classes_by_room_day_period.get(
                    (room_id, target_date, left_period.period_id)
                )
                right_class_id = classes_by_room_day_period.get(
                    (room_id, target_date, right_period.period_id)
                )
                if (
                    left_class_id is not None
                    and right_class_id is not None
                    and left_class_id != right_class_id
                    and (left_class_id, right_class_id) not in excluded_transitions
                ):
                    issues.append(
                        ValidationIssueModel(
                            "S10",
                            "WARNING",
                            (
                                f"{room_id}/{target_date}/"
                                f"{left_period.period_id}/{right_period.period_id}"
                            ),
                            (
                                "同一教室を空き時限なしで別クラスへ交替しています: "
                                f"{left_class_id}->{right_class_id}"
                            ),
                        )
                    )

    def _report_room_priority_preference(
        self,
        input_data: InputDataModel,
        lessons: tuple[ScheduledLessonModel, ...],
        issues: list[ValidationIssueModel],
    ) -> None:
        rooms = {room.room_id: room for room in input_data.rooms if room.enabled}
        highest_priorities: dict[str, int] = {}
        for room in rooms.values():
            highest_priorities[room.campus_id] = max(
                highest_priorities.get(room.campus_id, room.priority),
                room.priority,
            )
        penalty_by_room: Counter[str] = Counter()
        lesson_count_by_room: Counter[str] = Counter()
        for lesson in lessons:
            room = rooms.get(lesson.room_id)
            if room is None:
                continue
            priority_gap = highest_priorities[room.campus_id] - room.priority
            if priority_gap > 0:
                penalty_by_room[room.room_id] += priority_gap
                lesson_count_by_room[room.room_id] += 1
        for room_id, penalty in penalty_by_room.items():
            room = rooms[room_id]
            issues.append(
                ValidationIssueModel(
                    "S19",
                    "WARNING",
                    room_id,
                    (
                        "校舎内最高priorityより低い教室へ授業が配置されています: "
                        f"priority={room.priority}, "
                        f"highest_priority={highest_priorities[room.campus_id]}, "
                        f"lessons={lesson_count_by_room[room_id]}, penalty={penalty}"
                    ),
                )
            )

    def _report_class_daily_contiguity_preference(
        self,
        input_data: InputDataModel,
        lessons: tuple[ScheduledLessonModel, ...],
        issues: list[ValidationIssueModel],
    ) -> None:
        period_orders = {period.period_id: period.output_order for period in input_data.periods}
        periods_by_class_day: dict[tuple[str, date], set[int]] = defaultdict(set)
        for lesson in lessons:
            period_order = period_orders.get(lesson.period_id)
            if period_order is not None:
                periods_by_class_day[(lesson.class_id, lesson.target_date)].add(period_order)

        for key, period_order_set in periods_by_class_day.items():
            if len(period_order_set) < 2:
                continue
            ordered = sorted(period_order_set)
            internal_gaps = [
                period_order
                for period_order in range(ordered[0] + 1, ordered[-1])
                if period_order not in period_order_set
            ]
            if internal_gaps:
                issues.append(
                    ValidationIssueModel(
                        "S11",
                        "WARNING",
                        str(key),
                        (
                            "同一クラスの最初と最後の授業の間に空き時限があります: "
                            f"授業時限={ordered}, 空き時限={internal_gaps}"
                        ),
                    )
                )

    def _report_class_single_lesson_day_preference(
        self,
        input_data: InputDataModel,
        lessons: tuple[ScheduledLessonModel, ...],
        issues: list[ValidationIssueModel],
    ) -> None:
        second_class_ids = {
            rule.second_class_id for rule in input_data.class_pair_overlap_rules if rule.enabled
        }
        subjects_by_class: dict[str, set[str]] = defaultdict(set)
        for requirement in input_data.lesson_requirements:
            if requirement.enabled:
                subjects_by_class[requirement.class_id].add(requirement.subject_id)
        single_subject_class_ids = {
            class_id for class_id, subject_ids in subjects_by_class.items() if len(subject_ids) == 1
        }
        excluded_class_ids = second_class_ids | single_subject_class_ids
        lesson_counts = Counter((lesson.class_id, lesson.target_date) for lesson in lessons)
        for key, lesson_count in lesson_counts.items():
            if key[0] in excluded_class_ids or lesson_count != 1:
                continue
            issues.append(
                ValidationIssueModel(
                    "S12",
                    "WARNING",
                    str(key),
                    "同一クラスの授業がこの日に1コマだけ配置されています",
                )
            )

    def _report_class_subject_consecutive_repeat_preference(
        self,
        input_data: InputDataModel,
        lessons: tuple[ScheduledLessonModel, ...],
        issues: list[ValidationIssueModel],
    ) -> None:
        period_orders = {period.period_id: period.output_order for period in input_data.periods}
        periods_by_class_subject_day: dict[
            tuple[str, str, date],
            set[int],
        ] = defaultdict(set)
        for lesson in lessons:
            period_order = period_orders.get(lesson.period_id)
            if period_order is not None:
                periods_by_class_subject_day[
                    (lesson.class_id, lesson.subject_id, lesson.target_date)
                ].add(period_order)

        for key, period_order_set in periods_by_class_subject_day.items():
            for left_period_order, right_period_order in pairwise(sorted(period_order_set)):
                if right_period_order != left_period_order + 1:
                    continue
                issues.append(
                    ValidationIssueModel(
                        "S13",
                        "WARNING",
                        f"{key}/{left_period_order}/{right_period_order}",
                        (
                            "同一クラスが連続時限で同じ教科を受講しています: "
                            f"時限={left_period_order},{right_period_order}"
                        ),
                    )
                )

    def _report_class_subject_daily_repeat_preference(
        self,
        lessons: tuple[ScheduledLessonModel, ...],
        issues: list[ValidationIssueModel],
    ) -> None:
        lesson_counts = Counter(
            (lesson.class_id, lesson.subject_id, lesson.target_date) for lesson in lessons
        )
        for key, lesson_count in lesson_counts.items():
            if lesson_count < 2:
                continue
            issues.append(
                ValidationIssueModel(
                    "S14",
                    "WARNING",
                    str(key),
                    (
                        "同一クラスの同じ教科がこの日に2コマ以上配置されています: "
                        f"コマ数={lesson_count}"
                    ),
                )
            )

    def _report_class_subject_double_then_next_day_preference(
        self,
        lessons: tuple[ScheduledLessonModel, ...],
        issues: list[ValidationIssueModel],
    ) -> None:
        lesson_counts = Counter(
            (lesson.class_id, lesson.subject_id, lesson.target_date) for lesson in lessons
        )
        for (class_id, subject_id, target_date), lesson_count in lesson_counts.items():
            if lesson_count < 2:
                continue
            next_date = target_date + timedelta(days=1)
            if lesson_counts[(class_id, subject_id, next_date)] == 0:
                continue
            issues.append(
                ValidationIssueModel(
                    "S15",
                    "WARNING",
                    f"{class_id}/{subject_id}/{target_date}/{next_date}",
                    (
                        "同日2コマ以上の翌日にも同じ教科が配置されています: "
                        f"同日コマ数={lesson_count}"
                    ),
                )
            )

    def _report_class_subject_schedule_balance_preference(
        self,
        input_data: InputDataModel,
        resolved_rules: ResolvedRuleSetModel,
        candidate_result: CandidateBuildResultModel,
        lessons: tuple[ScheduledLessonModel, ...],
        issues: list[ValidationIssueModel],
    ) -> None:
        score_scale = 1000
        requirements = {
            requirement.requirement_id: requirement
            for requirement in input_data.lesson_requirements
            if requirement.enabled
        }
        class_limits = {
            (rule.class_id, rule.target_date): rule.daily_hard_limit
            for rule in resolved_rules.class_date_rules
        }
        period_ids_by_requirement_day: dict[tuple[str, date], set[str]] = defaultdict(set)
        dates_by_requirement: dict[str, set[date]] = defaultdict(set)
        for candidate in candidate_result.candidates:
            key = (candidate.requirement_id, candidate.target_date)
            period_ids_by_requirement_day[key].add(candidate.period_id)
            dates_by_requirement[candidate.requirement_id].add(candidate.target_date)
        generated_counts = Counter(
            (lesson.requirement_id, lesson.target_date) for lesson in lessons
        )

        for requirement_id, candidate_dates in dates_by_requirement.items():
            requirement = requirements[requirement_id]
            dates = sorted(candidate_dates)
            if requirement.required_periods <= 1 or len(dates) <= 1:
                continue

            daily_capacities = []
            for target_date in dates:
                capacity = len(period_ids_by_requirement_day[(requirement_id, target_date)])
                if requirement.max_periods_per_day is not None:
                    capacity = min(capacity, requirement.max_periods_per_day)
                class_limit = class_limits.get((requirement.class_id, target_date))
                if class_limit is not None:
                    capacity = min(capacity, class_limit)
                daily_capacities.append(min(capacity, requirement.required_periods))

            total_capacity = sum(daily_capacities)
            if total_capacity <= requirement.required_periods:
                continue

            cumulative_capacity = 0
            cumulative_generated = 0
            deviation_sum = 0
            for target_date, daily_capacity in zip(
                dates[:-1],
                daily_capacities[:-1],
                strict=True,
            ):
                cumulative_capacity += daily_capacity
                cumulative_generated += generated_counts[(requirement_id, target_date)]
                target_count = (
                    2 * requirement.required_periods * cumulative_capacity + total_capacity
                ) // (2 * total_capacity)
                deviation_sum += abs(cumulative_generated - target_count)

            denominator = requirement.required_periods * (len(dates) - 1)
            normalized_score = (score_scale * deviation_sum + denominator - 1) // denominator
            if normalized_score == 0:
                continue
            issues.append(
                ValidationIssueModel(
                    "S16",
                    "WARNING",
                    f"{requirement.class_id}/{requirement.subject_id}",
                    (
                        "日程全体に対する教科配置の累積バランスに偏りがあります: "
                        f"score={normalized_score}/{score_scale}, "
                        f"cumulative_deviation={deviation_sum}"
                    ),
                )
            )

    def _lesson_target(self, lesson: ScheduledLessonModel) -> str:
        return f"{lesson.requirement_id}/{lesson.target_date}/{lesson.period_id}/{lesson.room_id}"

    def _issue(self, rule_id: str, target: str, message: str) -> ValidationIssueModel:
        return ValidationIssueModel(rule_id, "ERROR", target, message)


class BuildTimetableDocumentService:
    """Build the Excel-independent timetable document in contractual output order."""

    def execute(
        self,
        input_data: InputDataModel,
        lessons: tuple[ScheduledLessonModel, ...],
        teacher_day_offs: tuple[ScheduledTeacherDayOffModel, ...] = (),
    ) -> TimetableDocumentModel:
        output_days = sorted(
            (day for day in input_data.calendar_days if day.output_enabled),
            key=lambda item: item.target_date,
        )
        if not output_days:
            raise ValueError("出力対象日がありません")
        output_dates = {day.target_date for day in output_days}
        campuses = sorted(
            (campus for campus in input_data.campuses if campus.enabled),
            key=lambda item: item.output_order,
        )
        rooms_by_campus = {
            campus.campus_id: tuple(
                sorted(
                    (
                        room
                        for room in input_data.rooms
                        if room.enabled and room.campus_id == campus.campus_id
                    ),
                    key=lambda item: item.output_order,
                )
            )
            for campus in campuses
        }
        campus_models = tuple(
            CampusColumnGroupModel(
                campus_id=campus.campus_id,
                campus_display_name=campus.campus_name,
                rooms=tuple(
                    RoomColumnModel(room.room_id, room.room_name)
                    for room in rooms_by_campus[campus.campus_id]
                ),
            )
            for campus in campuses
        )
        if not any(campus.rooms for campus in campus_models):
            raise ValueError("出力対象の有効教室がありません")
        period_models = tuple(
            OutputPeriodModel(
                period.period_id,
                period.period_name,
                period.output_order,
                period.start_time,
                period.end_time,
            )
            for period in sorted(input_data.periods, key=lambda item: item.output_order)
        )
        if len(period_models) != 6:
            raise ValueError("出力時限が6件ではありません")
        valid_period_ids = {period.period_id for period in period_models}
        room_ids = {room.room_id for campus in campus_models for room in campus.rooms}
        classes = {item.class_id: item for item in input_data.classes if item.enabled}
        subjects = {item.subject_id: item for item in input_data.subjects if item.enabled}
        teachers = {item.teacher_id: item for item in input_data.teachers if item.enabled}
        by_date: dict[date, dict[tuple[str, str], OutputLessonModel]] = {
            target_date: {} for target_date in output_dates
        }
        teacher_leaves_by_date: dict[date, list[OutputTeacherLeaveModel]] = {
            target_date: [] for target_date in output_dates
        }
        for lesson in lessons:
            if lesson.target_date not in output_dates:
                raise ValueError(f"出力対象外日の授業です: {lesson.target_date}")
            if lesson.period_id not in valid_period_ids:
                raise ValueError(f"未知の時限です: {lesson.period_id}")
            if lesson.room_id not in room_ids:
                raise ValueError(f"未知または無効な教室です: {lesson.room_id}")
            if (
                lesson.class_id not in classes
                or lesson.subject_id not in subjects
                or lesson.teacher_id not in teachers
            ):
                raise ValueError(f"未知または無効な表示IDです: {lesson.requirement_id}")
            key = (lesson.period_id, lesson.room_id)
            if key in by_date[lesson.target_date]:
                raise ValueError(
                    "日付/時限/教室が重複しています: "
                    f"{lesson.target_date}/{lesson.period_id}/{lesson.room_id}"
                )
            by_date[lesson.target_date][key] = OutputLessonModel(
                classes[lesson.class_id].class_name,
                subjects[lesson.subject_id].subject_name,
                teachers[lesson.teacher_id].teacher_name,
            )
        period_orders = {period.period_id: period.output_order for period in period_models}
        campus_room_counts = {campus.campus_id: len(campus.rooms) for campus in campus_models}
        for teacher_leave in input_data.teacher_leaves:
            if teacher_leave.target_date not in output_dates:
                continue
            teacher = teachers.get(teacher_leave.teacher_id)
            if teacher is None:
                raise ValueError(
                    f"教師休みが未知または無効な教師を参照しています: {teacher_leave.teacher_id}"
                )
            if teacher.home_campus_id not in campus_room_counts:
                raise ValueError(
                    "教師休みの所属校舎が出力対象外です: "
                    f"{teacher.teacher_id}/{teacher.home_campus_id}"
                )
            unknown_period_ids = set(teacher_leave.unavailable_period_ids) - valid_period_ids
            if unknown_period_ids:
                raise ValueError(
                    "教師休みが未知の時限を参照しています: "
                    f"{teacher.teacher_id}/{sorted(unknown_period_ids)}"
                )
            teacher_leaves_by_date[teacher_leave.target_date].append(
                OutputTeacherLeaveModel(
                    teacher_display_name=teacher.teacher_name,
                    campus_id=teacher.home_campus_id,
                    unavailable_period_ids=tuple(
                        sorted(
                            teacher_leave.unavailable_period_ids,
                            key=period_orders.__getitem__,
                        )
                    ),
                )
            )
        for day_off in teacher_day_offs:
            if day_off.target_date not in output_dates:
                continue
            teacher = teachers.get(day_off.teacher_id)
            if teacher is None:
                raise ValueError(
                    "教師休日日数ルールが未知または無効な教師を参照しています: "
                    f"{day_off.teacher_id}"
                )
            teacher_leaves_by_date[day_off.target_date].append(
                OutputTeacherLeaveModel(
                    teacher_display_name=teacher.teacher_name,
                    campus_id=teacher.home_campus_id,
                    unavailable_period_ids=tuple(
                        period.period_id
                        for period in sorted(period_models, key=lambda item: item.output_order)
                    ),
                )
            )
        all_period_ids = set(valid_period_ids)
        for target_date, teacher_leaves in teacher_leaves_by_date.items():
            required_cells_by_campus = Counter(
                {
                    campus_id: sum(
                        1 if set(teacher_leave.unavailable_period_ids) == all_period_ids else 2
                        for teacher_leave in teacher_leaves
                        if teacher_leave.campus_id == campus_id
                    )
                    for campus_id in campus_room_counts
                }
            )
            for campus_id, required_cells in required_cells_by_campus.items():
                available_cells = campus_room_counts[campus_id]
                if required_cells > available_cells:
                    raise ValueError(
                        "OUTPUT_TEACHER_LEAVE_OVERFLOW: "
                        f"{target_date}/{campus_id}/"
                        f"required={required_cells}/available={available_cells}"
                    )
        daily_models = tuple(
            DailyTimetableModel(
                day.target_date,
                MappingProxyType(dict(by_date[day.target_date])),
                tuple(teacher_leaves_by_date[day.target_date]),
            )
            for day in output_days
        )
        return TimetableDocumentModel(daily_models, campus_models, period_models)

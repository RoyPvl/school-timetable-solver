from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, timedelta
from itertools import pairwise

from school_timetable_solver.model.input_models import InputDataModel
from school_timetable_solver.model.result_models import (
    ScheduledLessonModel,
    ValidationIssueModel,
    ValidationReportModel,
)
from school_timetable_solver.model.solver_models import ResolvedRuleSetModel


class ValidateResultService:
    """Independently verify every Ver.1 hard rule without OR-Tools types."""

    def execute(
        self,
        input_data: InputDataModel,
        resolved_rules: ResolvedRuleSetModel,
        lessons: tuple[ScheduledLessonModel, ...],
    ) -> ValidationReportModel:
        issues: list[ValidationIssueModel] = []
        self._validate_required_counts(input_data, lessons, issues)
        self._validate_overlaps(lessons, issues)
        self._validate_candidate_facts(input_data, resolved_rules, lessons, issues)
        self._validate_fixed_lessons(input_data, lessons, issues)
        self._validate_daily_limits(input_data, resolved_rules, lessons, issues)
        self._validate_consecutive_periods(input_data, resolved_rules, lessons, issues)
        self._validate_attendance_streaks(input_data, resolved_rules, lessons, issues)
        self._validate_campus_transfers(input_data, lessons, issues)
        return ValidationReportModel(tuple(issues))

    def _validate_required_counts(
        self,
        input_data: InputDataModel,
        lessons: tuple[ScheduledLessonModel, ...],
        issues: list[ValidationIssueModel],
    ) -> None:
        counts = Counter(lesson.requirement_id for lesson in lessons)
        for requirement in input_data.lesson_requirements:
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

    def _validate_overlaps(
        self,
        lessons: tuple[ScheduledLessonModel, ...],
        issues: list[ValidationIssueModel],
    ) -> None:
        key_specs = (
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
        for rule_id, label, counts in key_specs:
            for key, count in counts.items():
                if count > 1:
                    issues.append(
                        self._issue(rule_id, str(key), f"{label}が同一時限に重複しています")
                    )

    def _validate_candidate_facts(
        self,
        input_data: InputDataModel,
        resolved_rules: ResolvedRuleSetModel,
        lessons: tuple[ScheduledLessonModel, ...],
        issues: list[ValidationIssueModel],
    ) -> None:
        calendars = {item.target_date: item for item in input_data.calendar_days}
        availability = {
            (item.teacher_id, item.target_date, item.period_id): item.availability
            for item in input_data.teacher_availability
        }
        class_rules = {
            (item.class_id, item.target_date): item for item in resolved_rules.class_date_rules
        }
        rooms = {item.room_id: item for item in input_data.rooms}
        classes = {item.class_id: item for item in input_data.classes}
        teachers = {item.teacher_id: item for item in input_data.teachers}
        for lesson in lessons:
            target = self._lesson_target(lesson)
            calendar = calendars[lesson.target_date]
            if not calendar.is_open or lesson.period_id not in calendar.available_period_ids:
                issues.append(self._issue("H04", target, "休館日または利用不可時限への配置です"))
            if availability.get((lesson.teacher_id, lesson.target_date, lesson.period_id)) not in {
                "available",
                "preferred",
            }:
                issues.append(self._issue("H05", target, "教師勤務不可日時への配置です"))
            rule = class_rules[(lesson.class_id, lesson.target_date)]
            if lesson.period_id not in rule.allowed_period_ids:
                issues.append(self._issue("H13", target, "配置ルールの許可時限外です"))
            room = rooms[lesson.room_id]
            class_model = classes[lesson.class_id]
            teacher = teachers[lesson.teacher_id]
            if not room.enabled or room.campus_id != class_model.campus_id:
                issues.append(self._issue("H14", target, "利用不可教室または校舎不一致です"))
            if not teacher.enabled or lesson.subject_id not in teacher.subject_ids:
                issues.append(self._issue("H05", target, "無効な教師または担当外教科です"))

    def _validate_fixed_lessons(
        self,
        input_data: InputDataModel,
        lessons: tuple[ScheduledLessonModel, ...],
        issues: list[ValidationIssueModel],
    ) -> None:
        lesson_keys = {
            (
                item.requirement_id,
                item.target_date,
                item.period_id,
                item.teacher_id,
                item.class_id,
                item.subject_id,
                item.room_id,
            )
            for item in lessons
        }
        for fixed in input_data.fixed_lessons:
            key = (
                fixed.requirement_id,
                fixed.target_date,
                fixed.period_id,
                fixed.teacher_id,
                fixed.class_id,
                fixed.subject_id,
                fixed.room_id,
            )
            if key not in lesson_keys:
                issues.append(
                    self._issue("H12", fixed.fixed_lesson_id, "固定授業が配置されていません")
                )

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
            item.requirement_id: item.max_periods_per_day for item in input_data.lesson_requirements
        }
        class_counts = Counter((item.class_id, item.target_date) for item in lessons)
        teacher_counts = Counter((item.teacher_id, item.target_date) for item in lessons)
        requirement_counts = Counter((item.requirement_id, item.target_date) for item in lessons)
        for key, count in class_counts.items():
            limit = class_limits[key]
            if limit is not None and count > limit:
                issues.append(self._issue("H07", str(key), f"クラス日別上限超過: {count}>{limit}"))
        for (requirement_id, target_date), count in requirement_counts.items():
            limit = requirement_limits[requirement_id]
            if limit is not None and count > limit:
                issues.append(
                    self._issue(
                        "H07",
                        f"{requirement_id}/{target_date}",
                        f"授業要求の日別上限超過: {count}>{limit}",
                    )
                )
        for key, count in teacher_counts.items():
            limit = teacher_limits[key]
            if limit is not None and count > limit:
                issues.append(self._issue("H08", str(key), f"教師日別上限超過: {count}>{limit}"))

    def _validate_consecutive_periods(
        self,
        input_data: InputDataModel,
        resolved_rules: ResolvedRuleSetModel,
        lessons: tuple[ScheduledLessonModel, ...],
        issues: list[ValidationIssueModel],
    ) -> None:
        period_orders = {
            period.period_id: order
            for order, period in enumerate(
                sorted(input_data.periods, key=lambda item: item.sort_order), start=1
            )
        }
        limits = {
            (item.teacher_id, item.target_date): item.consecutive_hard_limit
            for item in resolved_rules.teacher_date_rules
        }
        grouped: dict[tuple[str, date], set[int]] = defaultdict(set)
        for lesson in lessons:
            grouped[(lesson.teacher_id, lesson.target_date)].add(period_orders[lesson.period_id])
        for key, orders in grouped.items():
            limit = limits[key]
            if limit is None:
                continue
            longest = 0
            current = 0
            previous: int | None = None
            for order in sorted(orders):
                current = current + 1 if previous is not None and order == previous + 1 else 1
                longest = max(longest, current)
                previous = order
            if longest > limit:
                issues.append(
                    self._issue("H09", str(key), f"教師連続コマ上限超過: {longest}>{limit}")
                )

    def _validate_attendance_streaks(
        self,
        input_data: InputDataModel,
        resolved_rules: ResolvedRuleSetModel,
        lessons: tuple[ScheduledLessonModel, ...],
        issues: list[ValidationIssueModel],
    ) -> None:
        attendance = {(item.class_id, item.target_date) for item in lessons}
        limits = {
            (item.class_id, item.target_date): item.attendance_streak_limit
            for item in resolved_rules.class_date_rules
        }
        dates = tuple(sorted(day.target_date for day in input_data.calendar_days))
        for (class_id, start_date), limit in limits.items():
            if limit is None:
                continue
            start_index = dates.index(start_date)
            window = dates[start_index : start_index + limit + 1]
            if len(window) != limit + 1:
                continue
            if any(right - left != timedelta(days=1) for left, right in pairwise(window)):
                continue
            if all((class_id, target_date) in attendance for target_date in window):
                issues.append(
                    self._issue(
                        "H10", f"{class_id}/{start_date}", f"最大連続登校日数を超過: {limit}"
                    )
                )

    def _validate_campus_transfers(
        self,
        input_data: InputDataModel,
        lessons: tuple[ScheduledLessonModel, ...],
        issues: list[ValidationIssueModel],
    ) -> None:
        teachers = {item.teacher_id: item for item in input_data.teachers}
        period_orders = {
            period.period_id: order
            for order, period in enumerate(
                sorted(input_data.periods, key=lambda item: item.sort_order), start=1
            )
        }
        grouped: dict[tuple[str, date], list[ScheduledLessonModel]] = defaultdict(list)
        for lesson in lessons:
            grouped[(lesson.teacher_id, lesson.target_date)].append(lesson)
        for (teacher_id, target_date), daily_lessons in grouped.items():
            teacher = teachers[teacher_id]
            for index, left in enumerate(daily_lessons):
                for right in daily_lessons[index + 1 :]:
                    if left.campus_id == right.campus_id:
                        continue
                    distance = abs(period_orders[left.period_id] - period_orders[right.period_id])
                    if (
                        not teacher.can_transfer_campus
                        or distance - 1 < teacher.required_transfer_gap
                    ):
                        issues.append(
                            self._issue(
                                "H11",
                                f"{teacher_id}/{target_date}",
                                "校舎移動に必要な空き時限数を満たしていません",
                            )
                        )

    def _lesson_target(self, lesson: ScheduledLessonModel) -> str:
        return f"{lesson.requirement_id}/{lesson.target_date}/{lesson.period_id}"

    def _issue(self, rule_id: str, target: str, message: str) -> ValidationIssueModel:
        return ValidationIssueModel(rule_id, "ERROR", target, message)

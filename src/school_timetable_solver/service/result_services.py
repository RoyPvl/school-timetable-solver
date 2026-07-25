from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, timedelta
from itertools import pairwise
from types import MappingProxyType

from school_timetable_solver.model.input_models import InputDataModel
from school_timetable_solver.model.result_models import (
    CampusColumnGroupModel,
    DailyTimetableModel,
    OutputLessonModel,
    OutputPeriodModel,
    RoomColumnModel,
    ScheduledLessonDraftModel,
    ScheduledLessonModel,
    TimetableDocumentModel,
    ValidationIssueModel,
    ValidationReportModel,
)
from school_timetable_solver.model.solver_models import ResolvedRuleSetModel


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
    """Independently verify all input/output-contract v0.1 hard rules."""

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
        self._validate_daily_limits(input_data, resolved_rules, lessons, issues)
        self._validate_consecutive_periods(input_data, resolved_rules, lessons, issues)
        self._validate_attendance_streaks(input_data, resolved_rules, lessons, issues)
        self._validate_single_campus_per_day(lessons, issues)
        self._validate_class_room_continuity(lessons, issues)
        self._validate_class_long_internal_gaps(input_data, lessons, issues)
        self._report_room_change_gap_preference(input_data, lessons, issues)
        self._report_class_daily_contiguity_preference(input_data, lessons, issues)
        return ValidationReportModel(tuple(issues))

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

    def _validate_candidate_facts(
        self,
        input_data: InputDataModel,
        resolved_rules: ResolvedRuleSetModel,
        lessons: tuple[ScheduledLessonModel, ...],
        issues: list[ValidationIssueModel],
    ) -> None:
        calendars = {day.target_date: day for day in input_data.calendar_days if day.output_enabled}
        periods = {period.period_id: period for period in input_data.periods}
        availability = {
            (item.teacher_id, item.target_date, item.period_id): item.available
            for item in input_data.teacher_availability
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
            if not availability.get(
                (lesson.teacher_id, lesson.target_date, lesson.period_id), False
            ):
                issues.append(self._issue("H05", target, "教師勤務不可日時への配置です"))
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

    def _validate_consecutive_periods(
        self,
        input_data: InputDataModel,
        resolved_rules: ResolvedRuleSetModel,
        lessons: tuple[ScheduledLessonModel, ...],
        issues: list[ValidationIssueModel],
    ) -> None:
        period_orders = {period.period_id: period.output_order for period in input_data.periods}
        limits = {
            (item.teacher_id, item.target_date): item.consecutive_hard_limit
            for item in resolved_rules.teacher_date_rules
        }
        grouped: dict[tuple[str, date], set[int]] = defaultdict(set)
        for lesson in lessons:
            if lesson.period_id in period_orders:
                grouped[(lesson.teacher_id, lesson.target_date)].add(
                    period_orders[lesson.period_id]
                )
        for key, orders in grouped.items():
            limit = limits.get(key)
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
                    self._issue("H09", str(key), f"教師連続時限上限超過: {longest}>{limit}")
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
        dates = tuple(
            sorted(day.target_date for day in input_data.calendar_days if day.output_enabled)
        )
        date_indexes = {target_date: index for index, target_date in enumerate(dates)}
        for (class_id, start_date), limit in limits.items():
            if limit is None or start_date not in date_indexes:
                continue
            start_index = date_indexes[start_date]
            window = dates[start_index : start_index + limit + 1]
            if len(window) != limit + 1:
                continue
            if any(right - left != timedelta(days=1) for left, right in pairwise(window)):
                continue
            if all((class_id, target_date) in attendance for target_date in window):
                issues.append(
                    self._issue(
                        "H10",
                        f"{class_id}/{start_date}",
                        f"最大連続登校日数を超過しています: {limit}",
                    )
                )

    def _validate_single_campus_per_day(
        self,
        lessons: tuple[ScheduledLessonModel, ...],
        issues: list[ValidationIssueModel],
    ) -> None:
        campuses: dict[tuple[str, date], set[str]] = defaultdict(set)
        for lesson in lessons:
            campuses[(lesson.teacher_id, lesson.target_date)].add(lesson.campus_id)
        for key, campus_ids in campuses.items():
            if len(campus_ids) > 1:
                issues.append(
                    self._issue(
                        "H11",
                        str(key),
                        f"同一教師・同一日に複数校舎へ配置されています: {sorted(campus_ids)}",
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
        daily_models = tuple(
            DailyTimetableModel(
                day.target_date,
                MappingProxyType(dict(by_date[day.target_date])),
            )
            for day in output_days
        )
        return TimetableDocumentModel(daily_models, campus_models, period_models)

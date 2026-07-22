from __future__ import annotations

from datetime import date, datetime, time
from pathlib import Path
from typing import ClassVar

from openpyxl import load_workbook
from openpyxl.worksheet.worksheet import Worksheet

from school_timetable_solver.model.input_models import (
    CalendarDayModel,
    FixedLessonModel,
    GenerationMode,
    GenerationSettingsModel,
    InputDataModel,
    LessonRequirementModel,
    PlacementRuleModel,
    TeacherAvailabilityModel,
)
from school_timetable_solver.model.master_models import (
    CampusModel,
    ClassModel,
    PeriodModel,
    RoomModel,
    SubjectModel,
    TeacherModel,
)
from school_timetable_solver.model.result_models import (
    InputReadResultModel,
    ValidationIssueModel,
)


class ExcelInputReaderAdapter:
    """Read the defined workbook schema and convert cell values to internal models."""

    _required_headers: ClassVar[dict[str, tuple[str, ...]]] = {
        "00_操作説明": ("section", "description"),
        "01_基本設定": ("setting_key", "setting_value", "description"),
        "02_開講カレンダー": (
            "date",
            "weekday",
            "is_open",
            "available_periods",
            "calendar_type",
            "reason",
            "note",
        ),
        "03_時限": ("period_id", "period_name", "sort_order", "start_time", "end_time"),
        "04_校舎": (
            "campus_id",
            "campus_name",
            "standard_class_daily_limit",
            "standard_teacher_daily_limit",
            "transfer_group",
            "enabled",
        ),
        "05_教室": ("room_id", "room_name", "campus_id", "enabled"),
        "06_教師": (
            "teacher_id",
            "teacher_name",
            "home_campus_id",
            "subject_ids",
            "daily_hard_limit",
            "consecutive_hard_limit",
            "can_transfer_campus",
            "required_transfer_gap",
            "enabled",
        ),
        "07_クラス": (
            "class_id",
            "class_name",
            "campus_id",
            "division",
            "grade",
            "exam_category",
            "category_tags",
            "daily_hard_limit",
            "daily_preferred_limit",
            "attendance_streak_limit",
            "default_allowed_periods",
            "enabled",
        ),
        "08_教科": ("subject_id", "subject_name", "enabled"),
        "09_授業要求": (
            "requirement_id",
            "class_id",
            "subject_id",
            "required_periods",
            "primary_teacher_id",
            "alternative_teacher_ids",
            "room_ids",
            "fixed_teacher",
            "max_periods_per_day",
            "allow_consecutive",
            "note",
        ),
        "10_教師勤務": ("teacher_id", "date", "period_id", "availability"),
        "11_固定授業": (
            "fixed_lesson_id",
            "requirement_id",
            "date",
            "period_id",
            "teacher_id",
            "class_id",
            "subject_id",
            "room_id",
        ),
        "12_配置ルール": (
            "rule_id",
            "rule_name",
            "enabled",
            "constraint_type",
            "target_entity",
            "condition_field",
            "condition_operator",
            "condition_value",
            "campus_id",
            "start_date",
            "end_date",
            "weekdays",
            "allowed_periods",
            "prohibited_periods",
            "daily_hard_limit",
            "daily_preferred_limit",
            "consecutive_limit",
            "attendance_streak_limit",
            "priority",
            "penalty_weight",
            "note",
        ),
        "13_選好設定": ("rule_id", "enabled", "weight", "note"),
        "14_出力設定": ("setting_key", "setting_value"),
    }

    def read(self, path: Path) -> InputReadResultModel:
        issues: list[ValidationIssueModel] = []
        if not path.is_file():
            return InputReadResultModel(
                input_data=None,
                issues=(
                    self._format_issue("INPUT_FILE_NOT_FOUND", str(path), "ファイルが存在しません"),
                ),
            )
        try:
            workbook = load_workbook(path, data_only=True)
        except (OSError, ValueError) as exc:
            return InputReadResultModel(
                input_data=None,
                issues=(
                    self._format_issue(
                        "INPUT_WORKBOOK_ERROR", str(path), f"Workbookを開けません: {exc}"
                    ),
                ),
            )

        rows_by_sheet: dict[str, list[tuple[int, dict[str, object]]]] = {}
        for sheet_name, required_headers in self._required_headers.items():
            if sheet_name not in workbook.sheetnames:
                issues.append(
                    self._format_issue(
                        "REQUIRED_SHEET_MISSING", sheet_name, "必須シートが存在しません"
                    )
                )
                continue
            rows_by_sheet[sheet_name] = self._read_rows(
                workbook[sheet_name], required_headers, issues
            )

        if any(
            issue.rule_id in {"REQUIRED_SHEET_MISSING", "REQUIRED_COLUMN_MISSING"}
            for issue in issues
        ):
            return InputReadResultModel(input_data=None, issues=tuple(issues))

        settings = self._read_settings(rows_by_sheet["01_基本設定"], issues)
        calendar_days = self._read_calendar(rows_by_sheet["02_開講カレンダー"], issues)
        periods = self._read_periods(rows_by_sheet["03_時限"], issues)
        campuses = self._read_campuses(rows_by_sheet["04_校舎"], issues)
        rooms = self._read_rooms(rows_by_sheet["05_教室"], issues)
        teachers = self._read_teachers(rows_by_sheet["06_教師"], issues)
        classes = self._read_classes(rows_by_sheet["07_クラス"], issues)
        subjects = self._read_subjects(rows_by_sheet["08_教科"], issues)
        requirements = self._read_requirements(rows_by_sheet["09_授業要求"], issues)
        availability = self._read_availability(rows_by_sheet["10_教師勤務"], issues)
        fixed_lessons = self._read_fixed_lessons(rows_by_sheet["11_固定授業"], issues)
        placement_rules = self._read_placement_rules(rows_by_sheet["12_配置ルール"], issues)

        if settings is None or issues:
            return InputReadResultModel(input_data=None, issues=tuple(issues))
        return InputReadResultModel(
            input_data=InputDataModel(
                settings=settings,
                calendar_days=tuple(calendar_days),
                periods=tuple(periods),
                campuses=tuple(campuses),
                rooms=tuple(rooms),
                teachers=tuple(teachers),
                classes=tuple(classes),
                subjects=tuple(subjects),
                lesson_requirements=tuple(requirements),
                teacher_availability=tuple(availability),
                fixed_lessons=tuple(fixed_lessons),
                placement_rules=tuple(placement_rules),
            ),
            issues=(),
        )

    def _read_rows(
        self,
        worksheet: Worksheet,
        required_headers: tuple[str, ...],
        issues: list[ValidationIssueModel],
    ) -> list[tuple[int, dict[str, object]]]:
        header_cells = list(worksheet[1])
        headers = [
            str(cell.value).strip() if cell.value is not None else "" for cell in header_cells
        ]
        header_index = {header: index for index, header in enumerate(headers) if header}
        for header in required_headers:
            if header not in header_index:
                issues.append(
                    self._format_issue(
                        "REQUIRED_COLUMN_MISSING",
                        worksheet.title,
                        f"必須列が存在しません: {header}",
                        f"{worksheet.title}!1",
                    )
                )
        if any(header not in header_index for header in required_headers):
            return []

        rows: list[tuple[int, dict[str, object]]] = []
        for row_number, cells in enumerate(worksheet.iter_rows(min_row=2), start=2):
            if all(cell.value is None for cell in cells):
                continue
            values: dict[str, object] = {}
            for header, index in header_index.items():
                values[header] = cells[index].value if index < len(cells) else None
            rows.append((row_number, values))
        return rows

    def _read_settings(
        self,
        rows: list[tuple[int, dict[str, object]]],
        issues: list[ValidationIssueModel],
    ) -> GenerationSettingsModel | None:
        values: dict[str, tuple[int, object]] = {}
        for row_number, row in rows:
            key = self._text(row["setting_key"], "01_基本設定", row_number, "setting_key", issues)
            if key is not None:
                values[key] = (row_number, row["setting_value"])
        required_keys = {
            "fiscal_year",
            "course_name",
            "start_date",
            "end_date",
            "solve_mode",
            "max_solve_seconds",
            "random_seed",
        }
        for key in sorted(required_keys - values.keys()):
            issues.append(
                self._format_issue("REQUIRED_SETTING_MISSING", key, "必須設定が存在しません")
            )
        if required_keys - values.keys():
            return None

        fiscal_year = self._integer(*self._setting_args(values, "fiscal_year"), issues)
        course_name = self._text(*self._setting_args(values, "course_name"), issues)
        start_date = self._date(*self._setting_args(values, "start_date"), issues)
        end_date = self._date(*self._setting_args(values, "end_date"), issues)
        mode_text = self._text(*self._setting_args(values, "solve_mode"), issues)
        max_seconds = self._number(*self._setting_args(values, "max_solve_seconds"), issues)
        random_seed = self._integer(*self._setting_args(values, "random_seed"), issues)
        mode: GenerationMode | None = None
        if mode_text is not None:
            normalized = "validate_only" if mode_text == "validate" else mode_text
            try:
                mode = GenerationMode(normalized)
            except ValueError:
                issues.append(
                    self._format_issue(
                        "INVALID_GENERATION_MODE",
                        "solve_mode",
                        f"不正な生成モードです: {mode_text}",
                    )
                )
        if None in (fiscal_year, course_name, start_date, end_date, mode, max_seconds, random_seed):
            return None
        assert fiscal_year is not None
        assert course_name is not None
        assert start_date is not None
        assert end_date is not None
        assert mode is not None
        assert max_seconds is not None
        assert random_seed is not None
        return GenerationSettingsModel(
            fiscal_year=fiscal_year,
            course_name=course_name,
            start_date=start_date,
            end_date=end_date,
            solve_mode=mode,
            max_solve_seconds=max_seconds,
            random_seed=random_seed,
        )

    def _setting_args(
        self, values: dict[str, tuple[int, object]], key: str
    ) -> tuple[object, str, int, str]:
        row_number, value = values[key]
        return value, "01_基本設定", row_number, "setting_value"

    def _read_calendar(
        self, rows: list[tuple[int, dict[str, object]]], issues: list[ValidationIssueModel]
    ) -> list[CalendarDayModel]:
        result: list[CalendarDayModel] = []
        for row_number, row in rows:
            target_date = self._date(row["date"], "02_開講カレンダー", row_number, "date", issues)
            weekday = self._text(row["weekday"], "02_開講カレンダー", row_number, "weekday", issues)
            is_open = self._boolean(
                row["is_open"], "02_開講カレンダー", row_number, "is_open", issues
            )
            calendar_type = self._text(
                row["calendar_type"],
                "02_開講カレンダー",
                row_number,
                "calendar_type",
                issues,
            )
            if None not in (target_date, weekday, is_open, calendar_type):
                assert target_date is not None
                assert weekday is not None
                assert is_open is not None
                assert calendar_type is not None
                result.append(
                    CalendarDayModel(
                        target_date=target_date,
                        weekday=weekday,
                        is_open=is_open,
                        available_period_ids=self._csv(row["available_periods"]),
                        calendar_type=calendar_type,
                        reason=self._optional_text(row["reason"]),
                    )
                )
        return result

    def _read_periods(
        self, rows: list[tuple[int, dict[str, object]]], issues: list[ValidationIssueModel]
    ) -> list[PeriodModel]:
        result: list[PeriodModel] = []
        for row_number, row in rows:
            values = (
                self._text(row["period_id"], "03_時限", row_number, "period_id", issues),
                self._text(row["period_name"], "03_時限", row_number, "period_name", issues),
                self._integer(row["sort_order"], "03_時限", row_number, "sort_order", issues),
                self._time(row["start_time"], "03_時限", row_number, "start_time", issues),
                self._time(row["end_time"], "03_時限", row_number, "end_time", issues),
            )
            if all(value is not None for value in values):
                period_id, period_name, sort_order, start_time, end_time = values
                assert period_id is not None
                assert period_name is not None
                assert sort_order is not None
                assert start_time is not None
                assert end_time is not None
                result.append(PeriodModel(period_id, period_name, sort_order, start_time, end_time))
        return result

    def _read_campuses(
        self, rows: list[tuple[int, dict[str, object]]], issues: list[ValidationIssueModel]
    ) -> list[CampusModel]:
        result: list[CampusModel] = []
        for row_number, row in rows:
            campus_id = self._text(row["campus_id"], "04_校舎", row_number, "campus_id", issues)
            name = self._text(row["campus_name"], "04_校舎", row_number, "campus_name", issues)
            enabled = self._boolean(row["enabled"], "04_校舎", row_number, "enabled", issues)
            if None not in (campus_id, name, enabled):
                assert campus_id is not None
                assert name is not None
                assert enabled is not None
                result.append(
                    CampusModel(
                        campus_id=campus_id,
                        campus_name=name,
                        standard_class_daily_limit=self._optional_integer(
                            row["standard_class_daily_limit"],
                            "04_校舎",
                            row_number,
                            "standard_class_daily_limit",
                            issues,
                        ),
                        standard_teacher_daily_limit=self._optional_integer(
                            row["standard_teacher_daily_limit"],
                            "04_校舎",
                            row_number,
                            "standard_teacher_daily_limit",
                            issues,
                        ),
                        transfer_group=self._optional_text(row["transfer_group"]),
                        enabled=enabled,
                    )
                )
        return result

    def _read_rooms(
        self, rows: list[tuple[int, dict[str, object]]], issues: list[ValidationIssueModel]
    ) -> list[RoomModel]:
        result: list[RoomModel] = []
        for row_number, row in rows:
            room_id = self._text(row["room_id"], "05_教室", row_number, "room_id", issues)
            name = self._text(row["room_name"], "05_教室", row_number, "room_name", issues)
            campus_id = self._text(row["campus_id"], "05_教室", row_number, "campus_id", issues)
            enabled = self._boolean(row["enabled"], "05_教室", row_number, "enabled", issues)
            if None not in (room_id, name, campus_id, enabled):
                assert room_id is not None
                assert name is not None
                assert campus_id is not None
                assert enabled is not None
                result.append(RoomModel(room_id, name, campus_id, enabled))
        return result

    def _read_teachers(
        self, rows: list[tuple[int, dict[str, object]]], issues: list[ValidationIssueModel]
    ) -> list[TeacherModel]:
        result: list[TeacherModel] = []
        for row_number, row in rows:
            teacher_id = self._text(row["teacher_id"], "06_教師", row_number, "teacher_id", issues)
            name = self._text(row["teacher_name"], "06_教師", row_number, "teacher_name", issues)
            can_transfer = self._boolean(
                row["can_transfer_campus"],
                "06_教師",
                row_number,
                "can_transfer_campus",
                issues,
            )
            enabled = self._boolean(row["enabled"], "06_教師", row_number, "enabled", issues)
            gap = self._optional_integer(
                row["required_transfer_gap"],
                "06_教師",
                row_number,
                "required_transfer_gap",
                issues,
            )
            if None not in (teacher_id, name, can_transfer, enabled):
                assert teacher_id is not None
                assert name is not None
                assert can_transfer is not None
                assert enabled is not None
                result.append(
                    TeacherModel(
                        teacher_id=teacher_id,
                        teacher_name=name,
                        home_campus_id=self._optional_text(row["home_campus_id"]),
                        subject_ids=self._csv(row["subject_ids"]),
                        daily_hard_limit=self._optional_integer(
                            row["daily_hard_limit"],
                            "06_教師",
                            row_number,
                            "daily_hard_limit",
                            issues,
                        ),
                        consecutive_hard_limit=self._optional_integer(
                            row["consecutive_hard_limit"],
                            "06_教師",
                            row_number,
                            "consecutive_hard_limit",
                            issues,
                        ),
                        can_transfer_campus=can_transfer,
                        required_transfer_gap=gap or 0,
                        enabled=enabled,
                    )
                )
        return result

    def _read_classes(
        self, rows: list[tuple[int, dict[str, object]]], issues: list[ValidationIssueModel]
    ) -> list[ClassModel]:
        result: list[ClassModel] = []
        for row_number, row in rows:
            required = (
                self._text(row["class_id"], "07_クラス", row_number, "class_id", issues),
                self._text(row["class_name"], "07_クラス", row_number, "class_name", issues),
                self._text(row["campus_id"], "07_クラス", row_number, "campus_id", issues),
                self._text(row["division"], "07_クラス", row_number, "division", issues),
                self._integer(row["grade"], "07_クラス", row_number, "grade", issues),
                self._text(row["exam_category"], "07_クラス", row_number, "exam_category", issues),
                self._boolean(row["enabled"], "07_クラス", row_number, "enabled", issues),
            )
            if all(value is not None for value in required):
                class_id, class_name, campus_id, division, grade, exam_category, enabled = required
                assert class_id is not None
                assert class_name is not None
                assert campus_id is not None
                assert division is not None
                assert grade is not None
                assert exam_category is not None
                assert enabled is not None
                result.append(
                    ClassModel(
                        class_id=class_id,
                        class_name=class_name,
                        campus_id=campus_id,
                        division=division,
                        grade=grade,
                        exam_category=exam_category,
                        category_tags=self._csv(row["category_tags"]),
                        daily_hard_limit=self._optional_integer(
                            row["daily_hard_limit"],
                            "07_クラス",
                            row_number,
                            "daily_hard_limit",
                            issues,
                        ),
                        daily_preferred_limit=self._optional_integer(
                            row["daily_preferred_limit"],
                            "07_クラス",
                            row_number,
                            "daily_preferred_limit",
                            issues,
                        ),
                        attendance_streak_limit=self._optional_integer(
                            row["attendance_streak_limit"],
                            "07_クラス",
                            row_number,
                            "attendance_streak_limit",
                            issues,
                        ),
                        default_allowed_periods=self._csv(row["default_allowed_periods"]),
                        enabled=enabled,
                    )
                )
        return result

    def _read_subjects(
        self, rows: list[tuple[int, dict[str, object]]], issues: list[ValidationIssueModel]
    ) -> list[SubjectModel]:
        result: list[SubjectModel] = []
        for row_number, row in rows:
            subject_id = self._text(row["subject_id"], "08_教科", row_number, "subject_id", issues)
            name = self._text(row["subject_name"], "08_教科", row_number, "subject_name", issues)
            enabled = self._boolean(row["enabled"], "08_教科", row_number, "enabled", issues)
            if None not in (subject_id, name, enabled):
                assert subject_id is not None
                assert name is not None
                assert enabled is not None
                result.append(SubjectModel(subject_id, name, enabled))
        return result

    def _read_requirements(
        self, rows: list[tuple[int, dict[str, object]]], issues: list[ValidationIssueModel]
    ) -> list[LessonRequirementModel]:
        result: list[LessonRequirementModel] = []
        for row_number, row in rows:
            required = (
                self._text(
                    row["requirement_id"], "09_授業要求", row_number, "requirement_id", issues
                ),
                self._text(row["class_id"], "09_授業要求", row_number, "class_id", issues),
                self._text(row["subject_id"], "09_授業要求", row_number, "subject_id", issues),
                self._integer(
                    row["required_periods"],
                    "09_授業要求",
                    row_number,
                    "required_periods",
                    issues,
                ),
                self._text(
                    row["primary_teacher_id"],
                    "09_授業要求",
                    row_number,
                    "primary_teacher_id",
                    issues,
                ),
                self._boolean(
                    row["fixed_teacher"], "09_授業要求", row_number, "fixed_teacher", issues
                ),
                self._boolean(
                    row["allow_consecutive"],
                    "09_授業要求",
                    row_number,
                    "allow_consecutive",
                    issues,
                ),
            )
            if all(value is not None for value in required):
                (
                    requirement_id,
                    class_id,
                    subject_id,
                    required_periods,
                    primary_teacher_id,
                    fixed_teacher,
                    allow_consecutive,
                ) = required
                assert requirement_id is not None
                assert class_id is not None
                assert subject_id is not None
                assert required_periods is not None
                assert primary_teacher_id is not None
                assert fixed_teacher is not None
                assert allow_consecutive is not None
                result.append(
                    LessonRequirementModel(
                        requirement_id=requirement_id,
                        class_id=class_id,
                        subject_id=subject_id,
                        required_periods=required_periods,
                        primary_teacher_id=primary_teacher_id,
                        alternative_teacher_ids=self._csv(row["alternative_teacher_ids"]),
                        room_ids=self._csv(row["room_ids"]),
                        fixed_teacher=fixed_teacher,
                        max_periods_per_day=self._optional_integer(
                            row["max_periods_per_day"],
                            "09_授業要求",
                            row_number,
                            "max_periods_per_day",
                            issues,
                        ),
                        allow_consecutive=allow_consecutive,
                    )
                )
        return result

    def _read_availability(
        self, rows: list[tuple[int, dict[str, object]]], issues: list[ValidationIssueModel]
    ) -> list[TeacherAvailabilityModel]:
        result: list[TeacherAvailabilityModel] = []
        for row_number, row in rows:
            values = (
                self._text(row["teacher_id"], "10_教師勤務", row_number, "teacher_id", issues),
                self._date(row["date"], "10_教師勤務", row_number, "date", issues),
                self._text(row["period_id"], "10_教師勤務", row_number, "period_id", issues),
                self._text(row["availability"], "10_教師勤務", row_number, "availability", issues),
            )
            if all(value is not None for value in values):
                teacher_id, target_date, period_id, availability = values
                assert teacher_id is not None
                assert target_date is not None
                assert period_id is not None
                assert availability is not None
                result.append(
                    TeacherAvailabilityModel(teacher_id, target_date, period_id, availability)
                )
        return result

    def _read_fixed_lessons(
        self, rows: list[tuple[int, dict[str, object]]], issues: list[ValidationIssueModel]
    ) -> list[FixedLessonModel]:
        result: list[FixedLessonModel] = []
        for row_number, row in rows:
            values = (
                self._text(
                    row["fixed_lesson_id"],
                    "11_固定授業",
                    row_number,
                    "fixed_lesson_id",
                    issues,
                ),
                self._text(
                    row["requirement_id"], "11_固定授業", row_number, "requirement_id", issues
                ),
                self._date(row["date"], "11_固定授業", row_number, "date", issues),
                self._text(row["period_id"], "11_固定授業", row_number, "period_id", issues),
                self._text(row["teacher_id"], "11_固定授業", row_number, "teacher_id", issues),
                self._text(row["class_id"], "11_固定授業", row_number, "class_id", issues),
                self._text(row["subject_id"], "11_固定授業", row_number, "subject_id", issues),
                self._text(row["room_id"], "11_固定授業", row_number, "room_id", issues),
            )
            if all(value is not None for value in values):
                (
                    fixed_lesson_id,
                    requirement_id,
                    target_date,
                    period_id,
                    teacher_id,
                    class_id,
                    subject_id,
                    room_id,
                ) = values
                assert fixed_lesson_id is not None
                assert requirement_id is not None
                assert target_date is not None
                assert period_id is not None
                assert teacher_id is not None
                assert class_id is not None
                assert subject_id is not None
                assert room_id is not None
                result.append(
                    FixedLessonModel(
                        fixed_lesson_id,
                        requirement_id,
                        target_date,
                        period_id,
                        teacher_id,
                        class_id,
                        subject_id,
                        room_id,
                    )
                )
        return result

    def _read_placement_rules(
        self, rows: list[tuple[int, dict[str, object]]], issues: list[ValidationIssueModel]
    ) -> list[PlacementRuleModel]:
        result: list[PlacementRuleModel] = []
        for row_number, row in rows:
            required = (
                self._text(row["rule_id"], "12_配置ルール", row_number, "rule_id", issues),
                self._text(row["rule_name"], "12_配置ルール", row_number, "rule_name", issues),
                self._boolean(row["enabled"], "12_配置ルール", row_number, "enabled", issues),
                self._text(
                    row["constraint_type"],
                    "12_配置ルール",
                    row_number,
                    "constraint_type",
                    issues,
                ),
                self._text(
                    row["target_entity"],
                    "12_配置ルール",
                    row_number,
                    "target_entity",
                    issues,
                ),
                self._integer(row["priority"], "12_配置ルール", row_number, "priority", issues),
            )
            if all(value is not None for value in required):
                rule_id, rule_name, enabled, constraint_type, target_entity, priority = required
                assert rule_id is not None
                assert rule_name is not None
                assert enabled is not None
                assert constraint_type is not None
                assert target_entity is not None
                assert priority is not None
                result.append(
                    PlacementRuleModel(
                        rule_id=rule_id,
                        rule_name=rule_name,
                        enabled=enabled,
                        constraint_type=constraint_type,
                        target_entity=target_entity,
                        condition_fields=self._csv(row["condition_field"]),
                        condition_operators=self._csv(row["condition_operator"]),
                        condition_values=self._csv(row["condition_value"]),
                        campus_id=self._optional_text(row["campus_id"]),
                        start_date=self._optional_date(
                            row["start_date"],
                            "12_配置ルール",
                            row_number,
                            "start_date",
                            issues,
                        ),
                        end_date=self._optional_date(
                            row["end_date"],
                            "12_配置ルール",
                            row_number,
                            "end_date",
                            issues,
                        ),
                        weekdays=self._csv(row["weekdays"]),
                        allowed_period_ids=self._csv(row["allowed_periods"]),
                        prohibited_period_ids=self._csv(row["prohibited_periods"]),
                        daily_hard_limit=self._optional_integer(
                            row["daily_hard_limit"],
                            "12_配置ルール",
                            row_number,
                            "daily_hard_limit",
                            issues,
                        ),
                        daily_preferred_limit=self._optional_integer(
                            row["daily_preferred_limit"],
                            "12_配置ルール",
                            row_number,
                            "daily_preferred_limit",
                            issues,
                        ),
                        consecutive_limit=self._optional_integer(
                            row["consecutive_limit"],
                            "12_配置ルール",
                            row_number,
                            "consecutive_limit",
                            issues,
                        ),
                        attendance_streak_limit=self._optional_integer(
                            row["attendance_streak_limit"],
                            "12_配置ルール",
                            row_number,
                            "attendance_streak_limit",
                            issues,
                        ),
                        priority=priority,
                    )
                )
        return result

    def _text(
        self,
        value: object,
        sheet: str,
        row: int,
        header: str,
        issues: list[ValidationIssueModel],
    ) -> str | None:
        text = self._optional_text(value)
        if text is None:
            issues.append(
                self._cell_issue("REQUIRED_VALUE_EMPTY", sheet, row, header, "必須値が空欄です")
            )
        return text

    def _integer(
        self,
        value: object,
        sheet: str,
        row: int,
        header: str,
        issues: list[ValidationIssueModel],
    ) -> int | None:
        if isinstance(value, bool):
            parsed = None
        elif isinstance(value, int):
            parsed = value
        elif isinstance(value, float) and value.is_integer():
            parsed = int(value)
        elif isinstance(value, str):
            try:
                parsed = int(value.strip())
            except ValueError:
                parsed = None
        else:
            parsed = None
        if parsed is None:
            issues.append(
                self._cell_issue(
                    "INVALID_INTEGER", sheet, row, header, f"整数へ変換できません: {value}"
                )
            )
        return parsed

    def _optional_integer(
        self,
        value: object,
        sheet: str,
        row: int,
        header: str,
        issues: list[ValidationIssueModel],
    ) -> int | None:
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        return self._integer(value, sheet, row, header, issues)

    def _number(
        self,
        value: object,
        sheet: str,
        row: int,
        header: str,
        issues: list[ValidationIssueModel],
    ) -> float | None:
        if isinstance(value, bool):
            parsed = None
        elif isinstance(value, (int, float)):
            parsed = float(value)
        elif isinstance(value, str):
            try:
                parsed = float(value.strip())
            except ValueError:
                parsed = None
        else:
            parsed = None
        if parsed is None:
            issues.append(
                self._cell_issue(
                    "INVALID_NUMBER", sheet, row, header, f"数値へ変換できません: {value}"
                )
            )
        return parsed

    def _boolean(
        self,
        value: object,
        sheet: str,
        row: int,
        header: str,
        issues: list[ValidationIssueModel],
    ) -> bool | None:
        if isinstance(value, bool):
            return value
        if isinstance(value, int) and value in (0, 1):
            return bool(value)
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "1", "yes", "available"}:
                return True
            if normalized in {"false", "0", "no", "unavailable"}:
                return False
        issues.append(
            self._cell_issue(
                "INVALID_BOOLEAN", sheet, row, header, f"真偽値へ変換できません: {value}"
            )
        )
        return None

    def _date(
        self,
        value: object,
        sheet: str,
        row: int,
        header: str,
        issues: list[ValidationIssueModel],
    ) -> date | None:
        parsed: date | None = None
        if isinstance(value, datetime):
            parsed = value.date()
        elif isinstance(value, date):
            parsed = value
        elif isinstance(value, str):
            try:
                parsed = date.fromisoformat(value.strip())
            except ValueError:
                parsed = None
        if parsed is None:
            issues.append(
                self._cell_issue(
                    "INVALID_DATE", sheet, row, header, f"日付へ変換できません: {value}"
                )
            )
        return parsed

    def _optional_date(
        self,
        value: object,
        sheet: str,
        row: int,
        header: str,
        issues: list[ValidationIssueModel],
    ) -> date | None:
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        return self._date(value, sheet, row, header, issues)

    def _time(
        self,
        value: object,
        sheet: str,
        row: int,
        header: str,
        issues: list[ValidationIssueModel],
    ) -> time | None:
        parsed: time | None = None
        if isinstance(value, datetime):
            parsed = value.time()
        elif isinstance(value, time):
            parsed = value
        elif isinstance(value, str):
            try:
                parsed = time.fromisoformat(value.strip())
            except ValueError:
                parsed = None
        if parsed is None:
            issues.append(
                self._cell_issue(
                    "INVALID_TIME", sheet, row, header, f"時刻へ変換できません: {value}"
                )
            )
        return parsed

    def _optional_text(self, value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _csv(self, value: object) -> tuple[str, ...]:
        text = self._optional_text(value)
        if text is None:
            return ()
        return tuple(part.strip() for part in text.split(",") if part.strip())

    def _cell_issue(
        self, rule_id: str, sheet: str, row: int, header: str, message: str
    ) -> ValidationIssueModel:
        return self._format_issue(rule_id, f"{sheet}.{header}", message, f"{sheet}!{header}@{row}")

    def _format_issue(
        self, rule_id: str, target: str, message: str, cell: str | None = None
    ) -> ValidationIssueModel:
        return ValidationIssueModel(rule_id, "ERROR", target, message, cell)

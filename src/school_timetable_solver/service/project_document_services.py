from __future__ import annotations

from datetime import date, time

from school_timetable_solver.model.input_models import (
    CalendarDayModel,
    ClassPairOverlapRuleModel,
    HomeroomBoundaryRuleModel,
    InputDataModel,
    InputWorkbookSettingsModel,
    LessonCountPreferenceRuleSegmentModel,
    LessonCountRuleSegmentModel,
    LessonRequirementModel,
    PlacementRuleModel,
    TeacherDayOffRuleModel,
    TeacherLeaveModel,
)
from school_timetable_solver.model.master_models import (
    CampusModel,
    ClassModel,
    PeriodModel,
    RoomModel,
    SubjectModel,
    TeacherModel,
)
from school_timetable_solver.model.project_document_models import (
    DraftCalendarDayModel,
    DraftCampusModel,
    DraftClassModel,
    DraftClassPairOverlapRuleModel,
    DraftHomeroomBoundaryRuleModel,
    DraftLessonCountPreferenceRuleSegmentModel,
    DraftLessonCountRuleSegmentModel,
    DraftLessonRequirementModel,
    DraftPeriodModel,
    DraftPlacementRuleModel,
    DraftRoomModel,
    DraftSubjectModel,
    DraftTeacherDayOffRuleModel,
    DraftTeacherLeaveModel,
    DraftTeacherModel,
    ProjectDocumentModel,
)
from school_timetable_solver.model.project_models import ProjectModel
from school_timetable_solver.model.result_models import InputReadResultModel, ValidationIssueModel
from school_timetable_solver.service.protocols import InputReader, ProjectStore
from school_timetable_solver.validator.input_validators import ProjectDocumentValidator


class ImportProjectDocumentService:
    def execute(self, data: InputDataModel) -> ProjectDocumentModel:
        document = ProjectDocumentModel(input_contract_version=data.settings.schema_version)
        document.calendar_days = [
            DraftCalendarDayModel(
                target_date=row.target_date.isoformat(),
                output_enabled=row.output_enabled,
                enabled_period_ids="|".join(row.enabled_period_ids),
                note="" if row.note is None else str(row.note),
            )
            for row in data.calendar_days
        ]
        document.periods = [
            DraftPeriodModel(
                period_id=row.period_id,
                period_name=row.period_name,
                output_order=str(row.output_order),
                start_time=row.start_time.isoformat(),
                end_time=row.end_time.isoformat(),
            )
            for row in data.periods
        ]
        document.campuses = [
            DraftCampusModel(
                campus_id=row.campus_id,
                campus_name=row.campus_name,
                output_order=str(row.output_order),
                enabled=row.enabled,
            )
            for row in data.campuses
        ]
        document.rooms = [
            DraftRoomModel(
                room_id=row.room_id,
                room_name=row.room_name,
                campus_id=row.campus_id,
                output_order=str(row.output_order),
                priority=str(row.priority),
                enabled=row.enabled,
            )
            for row in data.rooms
        ]
        document.teachers = [
            DraftTeacherModel(
                teacher_id=row.teacher_id,
                teacher_name=row.teacher_name,
                home_campus_id=row.home_campus_id,
                enabled=row.enabled,
            )
            for row in data.teachers
        ]
        document.classes = [
            DraftClassModel(
                class_id=row.class_id,
                class_name=row.class_name,
                campus_id=row.campus_id,
                division=row.division,
                grade=str(row.grade),
                exam_category=row.exam_category,
                homeroom_teacher_id=""
                if row.homeroom_teacher_id is None
                else str(row.homeroom_teacher_id),
                enabled=row.enabled,
            )
            for row in data.classes
        ]
        document.subjects = [
            DraftSubjectModel(
                subject_id=row.subject_id,
                subject_name=row.subject_name,
                lesson_type=row.lesson_type,
                enabled=row.enabled,
            )
            for row in data.subjects
        ]
        document.lesson_requirements = [
            DraftLessonRequirementModel(
                requirement_id=row.requirement_id,
                class_id=row.class_id,
                subject_id=row.subject_id,
                teacher_id=row.teacher_id,
                required_periods=str(row.required_periods),
                max_periods_per_day=""
                if row.max_periods_per_day is None
                else str(row.max_periods_per_day),
                enabled=row.enabled,
            )
            for row in data.lesson_requirements
        ]
        document.teacher_leaves = [
            DraftTeacherLeaveModel(
                teacher_id=row.teacher_id,
                target_date=row.target_date.isoformat(),
                unavailable_period_ids="|".join(row.unavailable_period_ids),
            )
            for row in data.teacher_leaves
        ]
        document.placement_rules = [
            DraftPlacementRuleModel(
                rule_id=row.rule_id,
                rule_name=row.rule_name,
                enabled=row.enabled,
                constraint_type=row.constraint_type,
                target_entity=row.target_entity,
                condition_fields="|".join(row.condition_fields),
                condition_operators="|".join(row.condition_operators),
                condition_values="|".join(row.condition_values),
                campus_id="" if row.campus_id is None else str(row.campus_id),
                start_date="" if row.start_date is None else row.start_date.isoformat(),
                end_date="" if row.end_date is None else row.end_date.isoformat(),
                weekdays="|".join(row.weekdays),
                allowed_period_ids="|".join(row.allowed_period_ids),
                daily_hard_limit="" if row.daily_hard_limit is None else str(row.daily_hard_limit),
                forbid_first_last_same_day=""
                if row.forbid_first_last_same_day is None
                else str(row.forbid_first_last_same_day).lower(),
                attendance_streak_limit=""
                if row.attendance_streak_limit is None
                else str(row.attendance_streak_limit),
                priority=str(row.priority),
                preferred_attendance_streak_limit=""
                if row.preferred_attendance_streak_limit is None
                else str(row.preferred_attendance_streak_limit),
                required_lesson_period_ids="|".join(row.required_lesson_period_ids),
            )
            for row in data.placement_rules
        ]
        document.lesson_count_rule_segments = [
            DraftLessonCountRuleSegmentModel(
                rule_id=row.rule_id,
                segment_id=row.segment_id,
                rule_name=row.rule_name,
                enabled=row.enabled,
                class_id=row.class_id,
                subject_id=row.subject_id,
                exact_periods=str(row.exact_periods),
                start_date=row.start_date.isoformat(),
                end_date=row.end_date.isoformat(),
                target_period_ids="|".join(row.target_period_ids),
            )
            for row in data.lesson_count_rule_segments
        ]
        document.lesson_count_preference_rule_segments = [
            DraftLessonCountPreferenceRuleSegmentModel(
                rule_id=row.rule_id,
                segment_id=row.segment_id,
                rule_name=row.rule_name,
                enabled=row.enabled,
                class_id=row.class_id,
                subject_id=row.subject_id,
                preferred_periods=str(row.preferred_periods),
                start_date=row.start_date.isoformat(),
                end_date=row.end_date.isoformat(),
                target_period_ids="|".join(row.target_period_ids),
            )
            for row in data.lesson_count_preference_rule_segments
        ]
        document.teacher_day_off_rules = [
            DraftTeacherDayOffRuleModel(
                rule_id=row.rule_id,
                teacher_id=row.teacher_id,
                enabled=row.enabled,
                eligible_dates="|".join(value.isoformat() for value in row.eligible_dates),
                required_days_off=""
                if row.required_days_off is None
                else str(row.required_days_off),
                minimum_days_off="" if row.minimum_days_off is None else str(row.minimum_days_off),
                maximum_days_off="" if row.maximum_days_off is None else str(row.maximum_days_off),
                quota_group_id="" if row.quota_group_id is None else str(row.quota_group_id),
                group_required_days_off=""
                if row.group_required_days_off is None
                else str(row.group_required_days_off),
                preferred_days_off=""
                if row.preferred_days_off is None
                else str(row.preferred_days_off),
            )
            for row in data.teacher_day_off_rules
        ]
        document.homeroom_boundary_rules = [
            DraftHomeroomBoundaryRuleModel(
                rule_id=row.rule_id,
                rule_name=row.rule_name,
                enabled=row.enabled,
                condition_fields="|".join(row.condition_fields),
                condition_operators="|".join(row.condition_operators),
                condition_values="|".join(row.condition_values),
                start_date=row.start_date.isoformat(),
                end_date=row.end_date.isoformat(),
            )
            for row in data.homeroom_boundary_rules
        ]
        document.class_pair_overlap_rules = [
            DraftClassPairOverlapRuleModel(
                rule_id=row.rule_id,
                rule_name=row.rule_name,
                enabled=row.enabled,
                first_class_id=row.first_class_id,
                second_class_id=row.second_class_id,
            )
            for row in data.class_pair_overlap_rules
        ]
        if data.calendar_days:
            document.start_date = min(day.target_date for day in data.calendar_days).isoformat()
            document.end_date = max(day.target_date for day in data.calendar_days).isoformat()
        return document


class BuildProjectInputService:
    def __init__(self, validator: ProjectDocumentValidator) -> None:
        self._validator = validator

    def execute(
        self, document: ProjectDocumentModel, project: ProjectModel
    ) -> InputReadResultModel:
        issues = self._validator.validate(document)
        if issues:
            return InputReadResultModel(None, tuple(issues))
        try:
            data = InputDataModel(
                settings=InputWorkbookSettingsModel(
                    document.input_contract_version, project.name, project.note or None
                ),
                calendar_days=tuple(
                    CalendarDayModel(
                        target_date=date.fromisoformat(row.target_date),
                        output_enabled=row.output_enabled,
                        enabled_period_ids=_values(row.enabled_period_ids),
                        note=row.note.strip() or None,
                    )
                    for row in document.calendar_days
                ),
                periods=tuple(
                    PeriodModel(
                        period_id=row.period_id.strip(),
                        period_name=row.period_name.strip(),
                        output_order=int(row.output_order),
                        start_time=time.fromisoformat(row.start_time),
                        end_time=time.fromisoformat(row.end_time),
                    )
                    for row in document.periods
                ),
                campuses=tuple(
                    CampusModel(
                        campus_id=row.campus_id.strip(),
                        campus_name=row.campus_name.strip(),
                        output_order=int(row.output_order),
                        enabled=row.enabled,
                    )
                    for row in document.campuses
                ),
                rooms=tuple(
                    RoomModel(
                        room_id=row.room_id.strip(),
                        room_name=row.room_name.strip(),
                        campus_id=row.campus_id.strip(),
                        output_order=int(row.output_order),
                        priority=int(row.priority),
                        enabled=row.enabled,
                    )
                    for row in document.rooms
                ),
                teachers=tuple(
                    TeacherModel(
                        teacher_id=row.teacher_id.strip(),
                        teacher_name=row.teacher_name.strip(),
                        home_campus_id=row.home_campus_id.strip(),
                        enabled=row.enabled,
                    )
                    for row in document.teachers
                ),
                classes=tuple(
                    ClassModel(
                        class_id=row.class_id.strip(),
                        class_name=row.class_name.strip(),
                        campus_id=row.campus_id.strip(),
                        division=row.division.strip(),
                        grade=int(row.grade),
                        exam_category=row.exam_category.strip(),
                        homeroom_teacher_id=row.homeroom_teacher_id.strip() or None,
                        enabled=row.enabled,
                    )
                    for row in document.classes
                ),
                subjects=tuple(
                    SubjectModel(
                        subject_id=row.subject_id.strip(),
                        subject_name=row.subject_name.strip(),
                        lesson_type=row.lesson_type.strip(),
                        enabled=row.enabled,
                    )
                    for row in document.subjects
                ),
                lesson_requirements=tuple(
                    LessonRequirementModel(
                        requirement_id=row.requirement_id.strip(),
                        class_id=row.class_id.strip(),
                        subject_id=row.subject_id.strip(),
                        teacher_id=row.teacher_id.strip(),
                        required_periods=int(row.required_periods),
                        max_periods_per_day=int(row.max_periods_per_day)
                        if row.max_periods_per_day.strip()
                        else None,
                        enabled=row.enabled,
                    )
                    for row in document.lesson_requirements
                    if row.enabled or row.required_periods.strip() not in {"", "0"}
                ),
                teacher_leaves=tuple(
                    TeacherLeaveModel(
                        teacher_id=row.teacher_id.strip(),
                        target_date=date.fromisoformat(row.target_date),
                        unavailable_period_ids=_values(row.unavailable_period_ids),
                    )
                    for row in document.teacher_leaves
                ),
                placement_rules=tuple(
                    PlacementRuleModel(
                        rule_id=row.rule_id.strip(),
                        rule_name=row.rule_name.strip(),
                        enabled=row.enabled,
                        constraint_type=row.constraint_type.strip(),
                        target_entity=row.target_entity.strip(),
                        condition_fields=_values(row.condition_fields),
                        condition_operators=_values(row.condition_operators),
                        condition_values=_values(row.condition_values),
                        campus_id=row.campus_id.strip() or None,
                        start_date=date.fromisoformat(row.start_date)
                        if row.start_date.strip()
                        else None,
                        end_date=date.fromisoformat(row.end_date) if row.end_date.strip() else None,
                        weekdays=_values(row.weekdays),
                        allowed_period_ids=_values(row.allowed_period_ids),
                        daily_hard_limit=int(row.daily_hard_limit)
                        if row.daily_hard_limit.strip()
                        else None,
                        forbid_first_last_same_day=_optional_boolean(
                            row.forbid_first_last_same_day
                        ),
                        attendance_streak_limit=int(row.attendance_streak_limit)
                        if row.attendance_streak_limit.strip()
                        else None,
                        priority=int(row.priority),
                        preferred_attendance_streak_limit=int(row.preferred_attendance_streak_limit)
                        if row.preferred_attendance_streak_limit.strip()
                        else None,
                        required_lesson_period_ids=_values(row.required_lesson_period_ids),
                    )
                    for row in document.placement_rules
                ),
                lesson_count_rule_segments=tuple(
                    LessonCountRuleSegmentModel(
                        rule_id=row.rule_id.strip(),
                        segment_id=row.segment_id.strip(),
                        rule_name=row.rule_name.strip(),
                        enabled=row.enabled,
                        class_id=row.class_id.strip(),
                        subject_id=row.subject_id.strip(),
                        exact_periods=int(row.exact_periods),
                        start_date=date.fromisoformat(row.start_date),
                        end_date=date.fromisoformat(row.end_date),
                        target_period_ids=_values(row.target_period_ids),
                    )
                    for row in document.lesson_count_rule_segments
                ),
                lesson_count_preference_rule_segments=tuple(
                    LessonCountPreferenceRuleSegmentModel(
                        rule_id=row.rule_id.strip(),
                        segment_id=row.segment_id.strip(),
                        rule_name=row.rule_name.strip(),
                        enabled=row.enabled,
                        class_id=row.class_id.strip(),
                        subject_id=row.subject_id.strip(),
                        preferred_periods=int(row.preferred_periods),
                        start_date=date.fromisoformat(row.start_date),
                        end_date=date.fromisoformat(row.end_date),
                        target_period_ids=_values(row.target_period_ids),
                    )
                    for row in document.lesson_count_preference_rule_segments
                ),
                teacher_day_off_rules=tuple(
                    TeacherDayOffRuleModel(
                        rule_id=row.rule_id.strip(),
                        teacher_id=row.teacher_id.strip(),
                        enabled=row.enabled,
                        eligible_dates=tuple(
                            date.fromisoformat(value) for value in _values(row.eligible_dates)
                        ),
                        required_days_off=int(row.required_days_off)
                        if row.required_days_off.strip()
                        else None,
                        minimum_days_off=int(row.minimum_days_off)
                        if row.minimum_days_off.strip()
                        else None,
                        maximum_days_off=int(row.maximum_days_off)
                        if row.maximum_days_off.strip()
                        else None,
                        quota_group_id=row.quota_group_id.strip() or None,
                        group_required_days_off=int(row.group_required_days_off)
                        if row.group_required_days_off.strip()
                        else None,
                        preferred_days_off=int(row.preferred_days_off)
                        if row.preferred_days_off.strip()
                        else None,
                    )
                    for row in document.teacher_day_off_rules
                ),
                homeroom_boundary_rules=tuple(
                    HomeroomBoundaryRuleModel(
                        rule_id=row.rule_id.strip(),
                        rule_name=row.rule_name.strip(),
                        enabled=row.enabled,
                        condition_fields=_values(row.condition_fields),
                        condition_operators=_values(row.condition_operators),
                        condition_values=_values(row.condition_values),
                        start_date=date.fromisoformat(row.start_date),
                        end_date=date.fromisoformat(row.end_date),
                    )
                    for row in document.homeroom_boundary_rules
                ),
                class_pair_overlap_rules=tuple(
                    ClassPairOverlapRuleModel(
                        rule_id=row.rule_id.strip(),
                        rule_name=row.rule_name.strip(),
                        enabled=row.enabled,
                        first_class_id=row.first_class_id.strip(),
                        second_class_id=row.second_class_id.strip(),
                    )
                    for row in document.class_pair_overlap_rules
                ),
            )
        except ValueError as exc:
            issues.append(
                ValidationIssueModel(
                    "DOCUMENT_FIELD_FORMAT",
                    "ERROR",
                    "入力",
                    f"数値・日付・時刻の入力形式を確認してください: {exc}",
                )
            )
            return InputReadResultModel(None, tuple(issues))
        return InputReadResultModel(data, ())


def _values(value: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in value.split("|") if part.strip())


def _optional_boolean(value: str) -> bool | None:
    if not value.strip():
        return None
    if value == "true":
        return True
    if value == "false":
        return False
    raise ValueError("真偽値はtrue / false / 空欄です")


class LoadProjectDocumentService:
    """Upgrade legacy Excel projects once; thereafter SQLite owns the draft."""

    def __init__(
        self,
        project_store: ProjectStore,
        input_reader: InputReader,
        importer: ImportProjectDocumentService,
    ) -> None:
        self._project_store = project_store
        self._input_reader = input_reader
        self._importer = importer

    def execute(self, project_id: str) -> ProjectDocumentModel:
        document = self._project_store.load_document(project_id)
        if document is not None:
            return document
        project = self._project_store.load(project_id)
        if project is None:
            raise ValueError("保存済みデータが見つかりません")
        document = ProjectDocumentModel()
        if project.imported_workbook_path is not None:
            result = self._input_reader.read(project.imported_workbook_path)
            if result.input_data is None or any(
                issue.severity == "ERROR" for issue in result.issues
            ):
                raise ValueError("元のExcelを読み込めません。保存データへの移行は行いません")
            document = self._importer.execute(result.input_data)
        self._project_store.save_document(project_id, document)
        return document


class SaveProjectDocumentService:
    def __init__(self, project_store: ProjectStore) -> None:
        self._project_store = project_store

    def execute(self, project_id: str, document: ProjectDocumentModel) -> None:
        self._project_store.save_document(project_id, document)

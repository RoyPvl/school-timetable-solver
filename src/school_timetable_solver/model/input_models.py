from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from school_timetable_solver.model.master_models import (
    CampusModel,
    ClassModel,
    PeriodModel,
    RoomModel,
    SubjectModel,
    TeacherModel,
)


class GenerationMode(StrEnum):
    VALIDATE_ONLY = "validate_only"
    STRICT = "strict"


@dataclass(frozen=True, slots=True)
class InputWorkbookSettingsModel:
    schema_version: str
    timetable_name: str
    description: str | None


@dataclass(frozen=True, slots=True)
class CalendarDayModel:
    target_date: date
    output_enabled: bool
    enabled_period_ids: tuple[str, ...]
    note: str | None


@dataclass(frozen=True, slots=True)
class LessonRequirementModel:
    requirement_id: str
    class_id: str
    subject_id: str
    teacher_id: str
    required_periods: int
    max_periods_per_day: int | None
    enabled: bool


@dataclass(frozen=True, slots=True)
class TeacherLeaveModel:
    teacher_id: str
    target_date: date
    unavailable_period_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PlacementRuleModel:
    rule_id: str
    rule_name: str
    enabled: bool
    constraint_type: str
    target_entity: str
    condition_fields: tuple[str, ...]
    condition_operators: tuple[str, ...]
    condition_values: tuple[str, ...]
    campus_id: str | None
    start_date: date | None
    end_date: date | None
    weekdays: tuple[str, ...]
    allowed_period_ids: tuple[str, ...]
    daily_hard_limit: int | None
    consecutive_limit: int | None
    attendance_streak_limit: int | None
    priority: int
    preferred_attendance_streak_limit: int | None = None


@dataclass(frozen=True, slots=True)
class LessonCountRuleSegmentModel:
    rule_id: str
    segment_id: str
    rule_name: str
    enabled: bool
    class_id: str
    subject_id: str
    exact_periods: int
    start_date: date
    end_date: date
    target_period_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class LessonCountPreferenceRuleSegmentModel:
    rule_id: str
    segment_id: str
    rule_name: str
    enabled: bool
    class_id: str
    subject_id: str
    preferred_periods: int
    start_date: date
    end_date: date
    target_period_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class InputDataModel:
    settings: InputWorkbookSettingsModel
    calendar_days: tuple[CalendarDayModel, ...]
    periods: tuple[PeriodModel, ...]
    campuses: tuple[CampusModel, ...]
    rooms: tuple[RoomModel, ...]
    teachers: tuple[TeacherModel, ...]
    classes: tuple[ClassModel, ...]
    subjects: tuple[SubjectModel, ...]
    lesson_requirements: tuple[LessonRequirementModel, ...]
    teacher_leaves: tuple[TeacherLeaveModel, ...]
    placement_rules: tuple[PlacementRuleModel, ...]
    lesson_count_rule_segments: tuple[LessonCountRuleSegmentModel, ...] = ()
    lesson_count_preference_rule_segments: tuple[
        LessonCountPreferenceRuleSegmentModel,
        ...,
    ] = ()

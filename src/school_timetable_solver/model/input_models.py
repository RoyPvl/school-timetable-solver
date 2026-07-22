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
    DIAGNOSTIC = "diagnostic"
    STRICT = "strict"


@dataclass(frozen=True, slots=True)
class GenerationSettingsModel:
    fiscal_year: int
    course_name: str
    start_date: date
    end_date: date
    solve_mode: GenerationMode
    max_solve_seconds: float
    random_seed: int


@dataclass(frozen=True, slots=True)
class CalendarDayModel:
    target_date: date
    weekday: str
    is_open: bool
    available_period_ids: tuple[str, ...]
    calendar_type: str
    reason: str | None


@dataclass(frozen=True, slots=True)
class LessonRequirementModel:
    requirement_id: str
    class_id: str
    subject_id: str
    required_periods: int
    primary_teacher_id: str
    alternative_teacher_ids: tuple[str, ...]
    room_ids: tuple[str, ...]
    fixed_teacher: bool
    max_periods_per_day: int | None
    allow_consecutive: bool


@dataclass(frozen=True, slots=True)
class TeacherAvailabilityModel:
    teacher_id: str
    target_date: date
    period_id: str
    availability: str


@dataclass(frozen=True, slots=True)
class FixedLessonModel:
    fixed_lesson_id: str
    requirement_id: str
    target_date: date
    period_id: str
    teacher_id: str
    class_id: str
    subject_id: str
    room_id: str


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
    prohibited_period_ids: tuple[str, ...]
    daily_hard_limit: int | None
    daily_preferred_limit: int | None
    consecutive_limit: int | None
    attendance_streak_limit: int | None
    priority: int


@dataclass(frozen=True, slots=True)
class InputDataModel:
    settings: GenerationSettingsModel
    calendar_days: tuple[CalendarDayModel, ...]
    periods: tuple[PeriodModel, ...]
    campuses: tuple[CampusModel, ...]
    rooms: tuple[RoomModel, ...]
    teachers: tuple[TeacherModel, ...]
    classes: tuple[ClassModel, ...]
    subjects: tuple[SubjectModel, ...]
    lesson_requirements: tuple[LessonRequirementModel, ...]
    teacher_availability: tuple[TeacherAvailabilityModel, ...]
    fixed_lessons: tuple[FixedLessonModel, ...]
    placement_rules: tuple[PlacementRuleModel, ...]

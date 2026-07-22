from __future__ import annotations

from dataclasses import dataclass
from datetime import time


@dataclass(frozen=True, slots=True)
class CampusModel:
    campus_id: str
    campus_name: str
    standard_class_daily_limit: int | None
    standard_teacher_daily_limit: int | None
    transfer_group: str | None
    enabled: bool


@dataclass(frozen=True, slots=True)
class RoomModel:
    room_id: str
    room_name: str
    campus_id: str
    enabled: bool


@dataclass(frozen=True, slots=True)
class TeacherModel:
    teacher_id: str
    teacher_name: str
    home_campus_id: str | None
    subject_ids: tuple[str, ...]
    daily_hard_limit: int | None
    consecutive_hard_limit: int | None
    can_transfer_campus: bool
    required_transfer_gap: int
    enabled: bool


@dataclass(frozen=True, slots=True)
class ClassModel:
    class_id: str
    class_name: str
    campus_id: str
    division: str
    grade: int
    exam_category: str
    category_tags: tuple[str, ...]
    daily_hard_limit: int | None
    daily_preferred_limit: int | None
    attendance_streak_limit: int | None
    default_allowed_periods: tuple[str, ...]
    enabled: bool


@dataclass(frozen=True, slots=True)
class SubjectModel:
    subject_id: str
    subject_name: str
    enabled: bool


@dataclass(frozen=True, slots=True)
class PeriodModel:
    period_id: str
    period_name: str
    sort_order: int
    start_time: time
    end_time: time

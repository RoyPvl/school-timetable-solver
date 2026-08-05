from __future__ import annotations

from dataclasses import dataclass
from datetime import time


@dataclass(frozen=True, slots=True)
class CampusModel:
    campus_id: str
    campus_name: str
    output_order: int
    enabled: bool


@dataclass(frozen=True, slots=True)
class RoomModel:
    room_id: str
    room_name: str
    campus_id: str
    output_order: int
    priority: int
    enabled: bool


@dataclass(frozen=True, slots=True)
class TeacherModel:
    teacher_id: str
    teacher_name: str
    home_campus_id: str
    enabled: bool


@dataclass(frozen=True, slots=True)
class ClassModel:
    class_id: str
    class_name: str
    campus_id: str
    division: str
    grade: int
    exam_category: str
    homeroom_teacher_id: str | None
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
    output_order: int
    start_time: time
    end_time: time

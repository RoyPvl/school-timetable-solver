from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, time
from pathlib import Path

from school_timetable_solver.model.input_models import GenerationMode, InputDataModel
from school_timetable_solver.model.solver_models import SolverStatisticsModel


@dataclass(frozen=True, slots=True)
class ValidationIssueModel:
    rule_id: str
    severity: str
    target: str
    message: str
    cell: str | None = None


@dataclass(frozen=True, slots=True)
class ValidationReportModel:
    issues: tuple[ValidationIssueModel, ...]

    def has_errors(self) -> bool:
        return any(issue.severity == "ERROR" for issue in self.issues)


@dataclass(frozen=True, slots=True)
class InputReadResultModel:
    input_data: InputDataModel | None
    issues: tuple[ValidationIssueModel, ...]


@dataclass(frozen=True, slots=True)
class ScheduledLessonModel:
    requirement_id: str
    target_date: date
    period_id: str
    teacher_id: str
    room_id: str
    campus_id: str
    class_id: str
    subject_id: str


@dataclass(frozen=True, slots=True)
class ScheduledLessonDraftModel:
    requirement_id: str
    target_date: date
    period_id: str
    teacher_id: str
    campus_id: str
    class_id: str
    subject_id: str


@dataclass(frozen=True, slots=True)
class SolverResultModel:
    lessons: tuple[ScheduledLessonDraftModel, ...]
    statistics: SolverStatisticsModel


@dataclass(frozen=True, slots=True)
class GenerationRequestModel:
    input_path: Path
    output_path: Path
    log_path: Path | None
    solve_mode: GenerationMode
    max_solve_seconds: float
    random_seed: int
    num_search_workers: int


@dataclass(frozen=True, slots=True)
class GenerationResultModel:
    status: str
    exit_code: int
    request: GenerationRequestModel
    input_data: InputDataModel | None
    lessons: tuple[ScheduledLessonModel, ...]
    validation_report: ValidationReportModel
    solver_statistics: SolverStatisticsModel | None


@dataclass(frozen=True, slots=True)
class OutputLessonModel:
    class_display_name: str
    subject_display_name: str
    teacher_display_name: str


@dataclass(frozen=True, slots=True)
class DailyTimetableModel:
    target_date: date
    lessons_by_period_and_room: Mapping[tuple[str, str], OutputLessonModel]


@dataclass(frozen=True, slots=True)
class RoomColumnModel:
    room_id: str
    room_display_name: str


@dataclass(frozen=True, slots=True)
class CampusColumnGroupModel:
    campus_id: str
    campus_display_name: str
    rooms: tuple[RoomColumnModel, ...]


@dataclass(frozen=True, slots=True)
class OutputPeriodModel:
    period_id: str
    period_name: str
    output_order: int
    start_time: time
    end_time: time


@dataclass(frozen=True, slots=True)
class TimetableDocumentModel:
    dates: tuple[DailyTimetableModel, ...]
    campuses: tuple[CampusColumnGroupModel, ...]
    periods: tuple[OutputPeriodModel, ...]

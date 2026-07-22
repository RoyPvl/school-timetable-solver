from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from school_timetable_solver.model.input_models import InputDataModel
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
class UnplacedLessonModel:
    requirement_id: str
    required_periods: int
    generated_periods: int
    shortage: int
    reason: str


@dataclass(frozen=True, slots=True)
class SolverResultModel:
    lessons: tuple[ScheduledLessonModel, ...]
    statistics: SolverStatisticsModel


@dataclass(frozen=True, slots=True)
class GenerationRequestModel:
    input_path: Path
    output_path: Path
    log_path: Path | None = None


@dataclass(frozen=True, slots=True)
class GenerationResultModel:
    status: str
    exit_code: int
    request: GenerationRequestModel
    input_data: InputDataModel | None
    lessons: tuple[ScheduledLessonModel, ...]
    unplaced_lessons: tuple[UnplacedLessonModel, ...]
    validation_report: ValidationReportModel
    solver_statistics: SolverStatisticsModel | None

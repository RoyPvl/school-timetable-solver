from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path

from school_timetable_solver.model.result_models import ValidationIssueModel


class ProjectSource(StrEnum):
    BLANK = "blank"
    EXCEL_IMPORT = "excel_import"


@dataclass(frozen=True, slots=True)
class ProjectModel:
    project_id: str
    name: str
    note: str
    source: ProjectSource
    imported_workbook_path: Path | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class ProjectImportResultModel:
    project: ProjectModel | None
    issues: tuple[ValidationIssueModel, ...]

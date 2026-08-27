from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Protocol

from school_timetable_solver.model.project_models import ProjectModel
from school_timetable_solver.model.result_models import (
    InputReadResultModel,
    TimetableDocumentModel,
)


class InputReader(Protocol):
    def read(self, path: Path) -> InputReadResultModel: ...


class TimetableWriter(Protocol):
    def write(self, document: TimetableDocumentModel, path: Path) -> None: ...


class ProjectStore(Protocol):
    def list(self) -> tuple[ProjectModel, ...]: ...

    def load(self, project_id: str) -> ProjectModel | None: ...

    def create(
        self,
        project: ProjectModel,
        imported_source_path: Path | None = None,
    ) -> ProjectModel: ...

    def update_metadata(
        self,
        project_id: str,
        name: str,
        note: str,
        updated_at: datetime,
    ) -> ProjectModel | None: ...

    def delete(self, project_id: str) -> bool: ...

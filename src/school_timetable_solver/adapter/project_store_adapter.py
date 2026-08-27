from __future__ import annotations

import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from school_timetable_solver.model.project_models import ProjectModel, ProjectSource


class LocalProjectStoreAdapter:
    """Persist desktop project metadata and imported workbook copies locally."""

    def __init__(self, data_directory: Path) -> None:
        self._data_directory = data_directory
        self._database_path = data_directory / "timetable.db"
        self._imports_directory = data_directory / "imports"

    def initialize(self) -> None:
        self._data_directory.mkdir(parents=True, exist_ok=True)
        self._imports_directory.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    project_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    note TEXT NOT NULL,
                    source TEXT NOT NULL,
                    imported_workbook_path TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def list(self) -> tuple[ProjectModel, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT project_id, name, note, source, imported_workbook_path,
                       created_at, updated_at
                FROM projects
                ORDER BY updated_at DESC, project_id ASC
                """
            ).fetchall()
        return tuple(self._row_to_model(row) for row in rows)

    def load(self, project_id: str) -> ProjectModel | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT project_id, name, note, source, imported_workbook_path,
                       created_at, updated_at
                FROM projects
                WHERE project_id = ?
                """,
                (project_id,),
            ).fetchone()
        return self._row_to_model(row) if row is not None else None

    def create(
        self,
        project: ProjectModel,
        imported_source_path: Path | None = None,
    ) -> ProjectModel:
        stored_import_path = self._copy_imported_workbook(project, imported_source_path)
        stored_project = ProjectModel(
            project_id=project.project_id,
            name=project.name,
            note=project.note,
            source=project.source,
            imported_workbook_path=stored_import_path,
            created_at=project.created_at,
            updated_at=project.updated_at,
        )
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO projects (
                        project_id, name, note, source, imported_workbook_path,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        stored_project.project_id,
                        stored_project.name,
                        stored_project.note,
                        stored_project.source.value,
                        self._relative_import_path(stored_import_path),
                        stored_project.created_at.isoformat(),
                        stored_project.updated_at.isoformat(),
                    ),
                )
        except Exception:
            if stored_import_path is not None:
                stored_import_path.unlink(missing_ok=True)
            raise
        return stored_project

    def update_metadata(
        self,
        project_id: str,
        name: str,
        note: str,
        updated_at: datetime,
    ) -> ProjectModel | None:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE projects
                SET name = ?, note = ?, updated_at = ?
                WHERE project_id = ?
                """,
                (name, note, updated_at.isoformat(), project_id),
            )
            if cursor.rowcount == 0:
                return None
        return self.load(project_id)

    def delete(self, project_id: str) -> bool:
        project = self.load(project_id)
        if project is None:
            return False
        with self._connect() as connection:
            connection.execute("DELETE FROM projects WHERE project_id = ?", (project_id,))
        if project.imported_workbook_path is not None:
            project.imported_workbook_path.unlink(missing_ok=True)
        return True

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _copy_imported_workbook(
        self,
        project: ProjectModel,
        imported_source_path: Path | None,
    ) -> Path | None:
        if project.source is ProjectSource.BLANK:
            if imported_source_path is not None:
                raise ValueError("blank project cannot include an imported workbook")
            return None
        if imported_source_path is None or not imported_source_path.is_file():
            raise ValueError("imported project requires an existing workbook")
        if imported_source_path.suffix.lower() != ".xlsx":
            raise ValueError("imported project requires an .xlsx workbook")
        destination = self._imports_directory / f"{project.project_id}.xlsx"
        shutil.copy2(imported_source_path, destination)
        return destination

    def _relative_import_path(self, path: Path | None) -> str | None:
        if path is None:
            return None
        return str(path.relative_to(self._data_directory))

    def _row_to_model(self, row: sqlite3.Row) -> ProjectModel:
        relative_path = row["imported_workbook_path"]
        imported_path = self._data_directory / relative_path if relative_path else None
        return ProjectModel(
            project_id=row["project_id"],
            name=row["name"],
            note=row["note"],
            source=ProjectSource(row["source"]),
            imported_workbook_path=imported_path,
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

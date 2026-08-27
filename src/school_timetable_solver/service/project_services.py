from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from school_timetable_solver.model.project_models import (
    ProjectExecutionSettingsModel,
    ProjectImportResultModel,
    ProjectModel,
    ProjectSource,
)
from school_timetable_solver.model.result_models import GenerationRequestModel, GenerationResultModel
from school_timetable_solver.service.protocols import (
    ExecutionLogger,
    InputReader,
    ProjectStore,
    TimetableGenerator,
)


class ListProjectsService:
    def __init__(self, project_store: ProjectStore) -> None:
        self._project_store = project_store

    def execute(self) -> tuple[ProjectModel, ...]:
        return self._project_store.list()


class LoadProjectService:
    def __init__(self, project_store: ProjectStore) -> None:
        self._project_store = project_store

    def execute(self, project_id: str) -> ProjectModel | None:
        return self._project_store.load(project_id)


class CreateProjectService:
    def __init__(self, project_store: ProjectStore) -> None:
        self._project_store = project_store

    def execute(self, name: str | None = None) -> ProjectModel:
        now = datetime.now(UTC)
        project_name = name.strip() if name and name.strip() else self._next_untitled_name()
        project = ProjectModel(
            project_id=uuid4().hex,
            name=project_name,
            note="",
            source=ProjectSource.BLANK,
            imported_workbook_path=None,
            created_at=now,
            updated_at=now,
        )
        return self._project_store.create(project)

    def _next_untitled_name(self) -> str:
        existing_names = {project.name for project in self._project_store.list()}
        base_name = "無題の時間割"
        if base_name not in existing_names:
            return base_name
        index = 2
        while f"{base_name} {index}" in existing_names:
            index += 1
        return f"{base_name} {index}"


class ImportProjectService:
    def __init__(self, project_store: ProjectStore, input_reader: InputReader) -> None:
        self._project_store = project_store
        self._input_reader = input_reader

    def execute(self, path: Path) -> ProjectImportResultModel:
        read_result = self._input_reader.read(path)
        has_errors = any(issue.severity == "ERROR" for issue in read_result.issues)
        if read_result.input_data is None or has_errors:
            return ProjectImportResultModel(None, read_result.issues)

        settings = read_result.input_data.settings
        now = datetime.now(UTC)
        name = settings.timetable_name.strip() or path.stem
        project = ProjectModel(
            project_id=uuid4().hex,
            name=name,
            note=settings.description or "",
            source=ProjectSource.EXCEL_IMPORT,
            imported_workbook_path=None,
            created_at=now,
            updated_at=now,
        )
        stored_project = self._project_store.create(project, path)
        return ProjectImportResultModel(stored_project, read_result.issues)


class UpdateProjectMetadataService:
    def __init__(self, project_store: ProjectStore) -> None:
        self._project_store = project_store

    def execute(self, project_id: str, name: str, note: str) -> ProjectModel | None:
        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("project name must not be blank")
        return self._project_store.update_metadata(
            project_id,
            normalized_name,
            note.strip(),
            datetime.now(UTC),
        )


class DuplicateProjectService:
    def __init__(self, project_store: ProjectStore) -> None:
        self._project_store = project_store

    def execute(self, project_id: str) -> ProjectModel | None:
        source = self._project_store.load(project_id)
        if source is None:
            return None
        now = datetime.now(UTC)
        duplicate = ProjectModel(
            project_id=uuid4().hex,
            name=f"{source.name} のコピー",
            note=source.note,
            source=source.source,
            imported_workbook_path=None,
            created_at=now,
            updated_at=now,
        )
        return self._project_store.create(duplicate, source.imported_workbook_path)


class DeleteProjectService:
    def __init__(self, project_store: ProjectStore) -> None:
        self._project_store = project_store

    def execute(self, project_id: str) -> bool:
        return self._project_store.delete(project_id)


class ExecuteProjectService:
    """Run an imported project with the existing generation use case."""

    def __init__(
        self,
        project_store: ProjectStore,
        generator: TimetableGenerator,
        execution_logger: ExecutionLogger,
    ) -> None:
        self._project_store = project_store
        self._generator = generator
        self._execution_logger = execution_logger

    def execute(
        self,
        project_id: str,
        settings: ProjectExecutionSettingsModel,
    ) -> GenerationResultModel:
        project = self._project_store.load(project_id)
        if project is None:
            raise ValueError("保存済みデータが見つかりません")
        input_path = project.imported_workbook_path
        if input_path is None or not input_path.is_file():
            raise ValueError("このデータには実行可能な入力がまだありません")

        request = GenerationRequestModel(
            input_path=input_path,
            output_path=settings.output_path,
            log_path=settings.log_path,
            solve_mode=settings.solve_mode,
            max_solve_seconds=settings.max_solve_seconds,
            random_seed=settings.random_seed,
            num_search_workers=settings.num_search_workers,
        )
        self._execution_logger.configure(settings.log_path)
        return self._generator.execute(request)

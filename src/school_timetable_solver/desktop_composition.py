from __future__ import annotations

from pathlib import Path

from school_timetable_solver.adapter.excel_input_router import CompatibleExcelInputReaderAdapter
from school_timetable_solver.adapter.execution_log_adapter import ExecutionLogAdapter
from school_timetable_solver.adapter.project_store_adapter import LocalProjectStoreAdapter
from school_timetable_solver.composition import ApplicationComposition
from school_timetable_solver.service.project_document_services import (
    BuildProjectInputService,
    ImportProjectDocumentService,
    LoadProjectDocumentService,
    SaveProjectDocumentService,
)
from school_timetable_solver.service.project_services import (
    CreateProjectService,
    DeleteProjectService,
    DuplicateProjectService,
    ExecuteProjectService,
    ImportProjectService,
    ListProjectsService,
    LoadProjectService,
    UpdateProjectMetadataService,
)
from school_timetable_solver.ui.seasonal_desktop_window import SeasonalDesktopWindow
from school_timetable_solver.validator.input_validators import ProjectDocumentValidator


class DesktopApplicationComposition:
    """Create the desktop application with local persistence."""

    def create_desktop_window(self, data_directory: Path) -> SeasonalDesktopWindow:
        project_store = LocalProjectStoreAdapter(data_directory)
        project_store.initialize()
        input_reader = CompatibleExcelInputReaderAdapter()
        generator = ApplicationComposition().create_generate_from_input_data_service()
        document_importer = ImportProjectDocumentService()
        load_document = LoadProjectDocumentService(project_store, input_reader, document_importer)
        return SeasonalDesktopWindow(
            load_document=load_document,
            save_document=SaveProjectDocumentService(project_store),
            list_projects=ListProjectsService(project_store),
            load_project=LoadProjectService(project_store),
            create_project=CreateProjectService(project_store),
            import_project=ImportProjectService(project_store, input_reader, document_importer),
            update_project=UpdateProjectMetadataService(project_store),
            duplicate_project=DuplicateProjectService(project_store),
            delete_project=DeleteProjectService(project_store),
            execute_project=ExecuteProjectService(
                project_store,
                generator,
                load_document,
                BuildProjectInputService(ProjectDocumentValidator()),
                ExecutionLogAdapter(),
            ),
        )

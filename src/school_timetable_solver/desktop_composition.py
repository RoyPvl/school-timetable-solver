from __future__ import annotations

from pathlib import Path

from school_timetable_solver.adapter.excel_input_router import CompatibleExcelInputReaderAdapter
from school_timetable_solver.adapter.execution_log_adapter import ExecutionLogAdapter
from school_timetable_solver.adapter.project_store_adapter import LocalProjectStoreAdapter
from school_timetable_solver.composition import ApplicationComposition
from school_timetable_solver.service.project_services import (
    CreateProjectService,
    DeleteProjectService,
    DuplicateProjectService,
    ExecuteProjectService,
    ImportProjectService,
    ListProjectsService,
    LoadProjectInputService,
    LoadProjectService,
    UpdateProjectMetadataService,
)
from school_timetable_solver.ui.seasonal_desktop_window import SeasonalDesktopWindow


class DesktopApplicationComposition:
    """Create the desktop application with local persistence."""

    def create_desktop_window(self, data_directory: Path) -> SeasonalDesktopWindow:
        project_store = LocalProjectStoreAdapter(data_directory)
        project_store.initialize()
        input_reader = CompatibleExcelInputReaderAdapter()
        generator = ApplicationComposition().create_generate_timetable_service()
        return SeasonalDesktopWindow(
            list_projects=ListProjectsService(project_store),
            load_project=LoadProjectService(project_store),
            load_project_input=LoadProjectInputService(project_store, input_reader),
            create_project=CreateProjectService(project_store),
            import_project=ImportProjectService(project_store, input_reader),
            update_project=UpdateProjectMetadataService(project_store),
            duplicate_project=DuplicateProjectService(project_store),
            delete_project=DeleteProjectService(project_store),
            execute_project=ExecuteProjectService(
                project_store,
                generator,
                ExecutionLogAdapter(),
            ),
        )

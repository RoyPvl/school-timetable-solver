from __future__ import annotations

from pathlib import Path

from school_timetable_solver.adapter.excel_input_router import CompatibleExcelInputReaderAdapter
from school_timetable_solver.adapter.project_store_adapter import LocalProjectStoreAdapter
from school_timetable_solver.service.project_services import (
    CreateProjectService,
    DeleteProjectService,
    DuplicateProjectService,
    ImportProjectService,
    ListProjectsService,
    LoadProjectService,
    UpdateProjectMetadataService,
)
from school_timetable_solver.ui.desktop_window import DesktopWindow


class DesktopApplicationComposition:
    """Create the desktop application with local persistence."""

    def create_desktop_window(self, data_directory: Path) -> DesktopWindow:
        project_store = LocalProjectStoreAdapter(data_directory)
        project_store.initialize()
        return DesktopWindow(
            list_projects=ListProjectsService(project_store),
            load_project=LoadProjectService(project_store),
            create_project=CreateProjectService(project_store),
            import_project=ImportProjectService(
                project_store,
                CompatibleExcelInputReaderAdapter(),
            ),
            update_project=UpdateProjectMetadataService(project_store),
            duplicate_project=DuplicateProjectService(project_store),
            delete_project=DeleteProjectService(project_store),
        )

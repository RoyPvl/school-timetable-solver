from __future__ import annotations

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
from school_timetable_solver.ui.desktop_window import DesktopWindow
from school_timetable_solver.ui.editor_theme import DARK_EDITOR_STYLE
from school_timetable_solver.ui.editor_workspace import SeasonalEditorWorkspace


class SeasonalDesktopWindow(DesktopWindow):
    """Desktop window using the seasonal-workflow editor during UI prototyping."""

    def __init__(
        self,
        list_projects: ListProjectsService,
        load_project: LoadProjectService,
        create_project: CreateProjectService,
        import_project: ImportProjectService,
        update_project: UpdateProjectMetadataService,
        duplicate_project: DuplicateProjectService,
        delete_project: DeleteProjectService,
        execute_project: ExecuteProjectService,
    ) -> None:
        super().__init__(
            list_projects=list_projects,
            load_project=load_project,
            create_project=create_project,
            import_project=import_project,
            update_project=update_project,
            duplicate_project=duplicate_project,
            delete_project=delete_project,
            execute_project=execute_project,
        )

        previous_editor = self._editor
        self._stack.removeWidget(previous_editor)
        previous_editor.deleteLater()

        editor = SeasonalEditorWorkspace()
        editor.setStyleSheet(DARK_EDITOR_STYLE)
        editor.back_requested.connect(self._show_home)
        self._editor = editor
        self._stack.addWidget(editor)
        self.resize(1180, 780)

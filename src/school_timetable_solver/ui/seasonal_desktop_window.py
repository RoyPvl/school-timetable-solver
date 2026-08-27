from __future__ import annotations

from PySide6.QtWidgets import QMessageBox

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
from school_timetable_solver.ui.desktop_window import DesktopWindow
from school_timetable_solver.ui.editor_presentation import apply_editor_presentation
from school_timetable_solver.ui.editor_theme import DARK_EDITOR_STYLE
from school_timetable_solver.ui.editor_workspace import SeasonalEditorWorkspace


class SeasonalDesktopWindow(DesktopWindow):
    """Desktop window using the seasonal-workflow editor during UI prototyping."""

    def __init__(
        self,
        list_projects: ListProjectsService,
        load_project: LoadProjectService,
        load_project_input: LoadProjectInputService,
        create_project: CreateProjectService,
        import_project: ImportProjectService,
        update_project: UpdateProjectMetadataService,
        duplicate_project: DuplicateProjectService,
        delete_project: DeleteProjectService,
        execute_project: ExecuteProjectService,
    ) -> None:
        self._load_project_input = load_project_input
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

    def _create_new_project(self) -> None:
        project = self._create_project.execute()
        editor = self._seasonal_editor()
        editor.load_project(project, None)
        apply_editor_presentation(editor)
        self._stack.setCurrentWidget(self._editor)

    def _open_project(self, project_id: str) -> None:
        project = self._load_project.execute(project_id)
        if project is None:
            QMessageBox.warning(self, "読込エラー", "保存済みデータが見つかりません。")
            self._refresh_home()
            return
        try:
            read_result = self._load_project_input.execute(project_id)
        except ValueError as exc:
            QMessageBox.warning(self, "読込エラー", str(exc))
            return
        editor = self._seasonal_editor()
        editor.load_project(project, read_result.input_data)
        apply_editor_presentation(editor)
        self._stack.setCurrentWidget(self._editor)

    def _seasonal_editor(self) -> SeasonalEditorWorkspace:
        if not isinstance(self._editor, SeasonalEditorWorkspace):
            raise RuntimeError("seasonal editor is not initialized")
        return self._editor

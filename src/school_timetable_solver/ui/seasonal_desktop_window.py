from __future__ import annotations

import sqlite3
from pathlib import Path

from PySide6.QtCore import Slot
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QMessageBox

from school_timetable_solver.model.input_models import GenerationMode
from school_timetable_solver.model.project_models import ProjectExecutionSettingsModel
from school_timetable_solver.model.result_models import GenerationResultModel
from school_timetable_solver.service.project_document_services import (
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
from school_timetable_solver.ui.desktop_window import DesktopWindow
from school_timetable_solver.ui.editor_theme import DARK_EDITOR_STYLE
from school_timetable_solver.ui.editor_workspace import SeasonalEditorWorkspace


class SeasonalDesktopWindow(DesktopWindow):
    """Save drafts independently of whether validation permits generation."""

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
        load_document: LoadProjectDocumentService,
        save_document: SaveProjectDocumentService,
    ) -> None:
        self._load_document = load_document
        self._save_document = save_document
        self._current_project_id: str | None = None
        self._dirty = False
        super().__init__(
            list_projects,
            load_project,
            create_project,
            import_project,
            update_project,
            duplicate_project,
            delete_project,
            execute_project,
        )
        previous = self._editor
        self._stack.removeWidget(previous)
        previous.deleteLater()
        editor = SeasonalEditorWorkspace()
        editor.setStyleSheet(DARK_EDITOR_STYLE)
        editor.back_requested.connect(self._show_home)
        editor.document_changed.connect(self._autosave)
        editor.save_requested.connect(self._autosave)
        editor.validate_requested.connect(self._validate_current)
        editor.run_requested.connect(self._run_current)
        editor.reload_requested.connect(self._reload_current)
        self._editor = editor
        self._stack.addWidget(editor)
        self.resize(1180, 780)

    def _create_new_project(self) -> None:
        self._open_project(self._create_project.execute().project_id)

    def _open_project(self, project_id: str) -> None:
        if self._dirty and not self._autosave():
            return
        project = self._load_project.execute(project_id)
        if project is None:
            QMessageBox.warning(self, "読込エラー", "保存済みデータが見つかりません。")
            return
        try:
            document = self._load_document.execute(project_id)
        except (ValueError, OSError, sqlite3.Error) as exc:
            QMessageBox.warning(self, "読込エラー", str(exc))
            return
        self._current_project_id = project_id
        self._dirty = False
        self._seasonal_editor().load_project(project, document)
        self._stack.setCurrentWidget(self._editor)

    def _reload_current(self) -> None:
        if self._current_project_id is None:
            return
        if self._dirty:
            answer = QMessageBox.question(
                self,
                "再読込",
                "未保存の変更を破棄して再読込しますか?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        project_id = self._current_project_id
        self._dirty = False
        self._open_project(project_id)

    def _autosave(self) -> bool:
        if self._current_project_id is None:
            return True
        editor = self._seasonal_editor()
        self._dirty = True
        try:
            self._save_document.execute(self._current_project_id, editor.document)
        except (ValueError, OSError, sqlite3.Error) as exc:
            editor.set_save_status(f"未保存: {exc}")
            return False
        self._dirty = False
        editor.set_save_status("保存済み")
        return True

    def _show_home(self) -> None:
        if self._dirty and not self._autosave():
            QMessageBox.warning(
                self, "保存できません", "変更は未保存です。画面上の保存エラーを確認してください。"
            )
            return
        super()._show_home()
        self._current_project_id = None

    def _run_current(self) -> None:
        if self._current_project_id is not None and self._autosave():
            self._run_existing_project(self._current_project_id)

    def _validate_current(self) -> None:
        if self._current_project_id is None or not self._autosave():
            return
        settings = ProjectExecutionSettingsModel(
            Path.cwd() / "validation-only.xlsx", None, GenerationMode.VALIDATE_ONLY, 60.0, 1, 1
        )
        self._start_project_run(self._current_project_id, settings)

    @Slot(object)
    def _run_completed(self, raw_result: object) -> None:
        if isinstance(raw_result, GenerationResultModel) and self._current_project_id is not None:
            self._seasonal_editor().show_validation(
                raw_result.validation_report.issues,
                "入力確認完了" if raw_result.exit_code == 0 else "入力・実行結果を確認してください",
            )
        super()._run_completed(raw_result)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._run_thread is not None:
            QMessageBox.information(self, "実行中", "実行が終わってから閉じてください。")
            event.ignore()
            return
        if self._dirty and not self._autosave():
            QMessageBox.warning(
                self, "保存できません", "変更は未保存です。保存エラーを解消してから閉じてください。"
            )
            event.ignore()
            return
        super().closeEvent(event)

    def _seasonal_editor(self) -> SeasonalEditorWorkspace:
        if not isinstance(self._editor, SeasonalEditorWorkspace):
            raise RuntimeError("seasonal editor is not initialized")
        return self._editor

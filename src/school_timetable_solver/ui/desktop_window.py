from __future__ import annotations

import logging
from pathlib import Path
from typing import cast

from PySide6.QtCore import QObject, QStandardPaths, Qt, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QProgressDialog,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from school_timetable_solver.model.input_models import GenerationMode
from school_timetable_solver.model.project_models import (
    ProjectExecutionSettingsModel,
    ProjectModel,
    ProjectSource,
)
from school_timetable_solver.model.result_models import GenerationResultModel
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

LOGGER = logging.getLogger(__name__)


class ProjectCardWidget(QFrame):
    open_requested = Signal(str)
    run_requested = Signal(str)
    edit_requested = Signal(str)
    duplicate_requested = Signal(str)
    delete_requested = Signal(str)

    def __init__(self, project: ProjectModel) -> None:
        super().__init__()
        self.setFrameShape(QFrame.Shape.StyledPanel)

        layout = QHBoxLayout(self)
        open_button = QPushButton(self._build_text(project))
        open_button.setFlat(True)
        open_button.setMinimumHeight(74)
        open_button.clicked.connect(
            lambda _checked=False: self.open_requested.emit(project.project_id)
        )
        layout.addWidget(open_button, 1)

        run_button = QPushButton("実行")
        can_run = (
            project.imported_workbook_path is not None
            and project.imported_workbook_path.is_file()
        )
        run_button.setEnabled(can_run)
        if not can_run:
            run_button.setToolTip("Editor入力の保存機能を実装後に実行可能になります")
        run_button.clicked.connect(
            lambda _checked=False: self.run_requested.emit(project.project_id)
        )
        layout.addWidget(run_button)

        menu_button = QToolButton()
        menu_button.setText("⋮")
        menu_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(menu_button)
        menu_button.setMenu(menu)
        edit_action = menu.addAction("名前・備考を変更")
        duplicate_action = menu.addAction("複製")
        delete_action = menu.addAction("削除")
        edit_action.triggered.connect(
            lambda _checked=False: self.edit_requested.emit(project.project_id)
        )
        duplicate_action.triggered.connect(
            lambda _checked=False: self.duplicate_requested.emit(project.project_id)
        )
        delete_action.triggered.connect(
            lambda _checked=False: self.delete_requested.emit(project.project_id)
        )
        layout.addWidget(menu_button)

    @staticmethod
    def _build_text(project: ProjectModel) -> str:
        lines = [project.name]
        if project.note:
            lines.append(project.note)
        lines.append(f"更新 {project.updated_at.astimezone():%Y/%m/%d %H:%M}")
        return "\n".join(lines)


class HomePage(QWidget):
    new_requested = Signal()
    import_requested = Signal()
    open_requested = Signal(str)
    run_requested = Signal(str)
    edit_requested = Signal(str)
    duplicate_requested = Signal(str)
    delete_requested = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        root = QVBoxLayout(self)

        title = QLabel("時間割解決システム")
        title.setStyleSheet("font-size: 24px; font-weight: 600;")
        root.addWidget(title)

        actions = QHBoxLayout()
        new_button = QPushButton("+ 新規作成")
        import_button = QPushButton("Excelからインポート")
        new_button.clicked.connect(lambda _checked=False: self.new_requested.emit())
        import_button.clicked.connect(lambda _checked=False: self.import_requested.emit())
        actions.addWidget(new_button)
        actions.addWidget(import_button)
        actions.addStretch(1)
        root.addLayout(actions)

        root.addWidget(QLabel("保存済み時間割"))
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._list_container = QWidget()
        self._list_layout = QVBoxLayout(self._list_container)
        self._list_layout.addStretch(1)
        self._scroll.setWidget(self._list_container)
        root.addWidget(self._scroll, 1)

    def set_projects(self, projects: tuple[ProjectModel, ...]) -> None:
        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        if not projects:
            empty = QLabel("保存済みの時間割はありません。")
            self._list_layout.insertWidget(0, empty)
            return

        for project in projects:
            card = ProjectCardWidget(project)
            card.open_requested.connect(self.open_requested.emit)
            card.run_requested.connect(self.run_requested.emit)
            card.edit_requested.connect(self.edit_requested.emit)
            card.duplicate_requested.connect(self.duplicate_requested.emit)
            card.delete_requested.connect(self.delete_requested.emit)
            self._list_layout.insertWidget(self._list_layout.count() - 1, card)


class EditorPage(QWidget):
    back_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        root = QVBoxLayout(self)
        back_button = QPushButton("← 一覧へ戻る")
        back_button.clicked.connect(lambda _checked=False: self.back_requested.emit())
        root.addWidget(back_button)

        self._title = QLabel()
        self._title.setStyleSheet("font-size: 22px; font-weight: 600;")
        self._note = QLabel()
        self._source = QLabel()
        root.addWidget(self._title)
        root.addWidget(self._note)
        root.addWidget(self._source)
        root.addSpacing(24)
        root.addWidget(QLabel("Editorの詳細入力画面は次の画面設計フェーズで実装します。"))
        root.addStretch(1)

    def load_project(self, project: ProjectModel) -> None:
        self._title.setText(project.name)
        self._note.setText(project.note or "備考なし")
        if project.source is ProjectSource.EXCEL_IMPORT:
            workbook_name = (
                project.imported_workbook_path.name
                if project.imported_workbook_path is not None
                else "不明"
            )
            self._source.setText(f"Excelインポート済み: {workbook_name}")
        else:
            self._source.setText("新規作成データ (空)")


class ProjectMetadataDialog(QDialog):
    def __init__(self, project: ProjectModel, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("名前・備考を変更")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("名前"))
        self._name = QLineEdit(project.name)
        layout.addWidget(self._name)
        layout.addWidget(QLabel("備考"))
        self._note = QPlainTextEdit(project.note)
        self._note.setMaximumHeight(100)
        layout.addWidget(self._note)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self) -> tuple[str, str]:
        return self._name.text(), self._note.toPlainText()


class RunProjectDialog(QDialog):
    def __init__(self, project: ProjectModel, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("時間割を実行")
        self.setMinimumWidth(600)

        output_path = self._default_output_path(project)
        self._auto_log_path = str(output_path.with_suffix(".log"))

        root = QVBoxLayout(self)
        root.addWidget(QLabel(f"実行対象: {project.name}"))
        form = QFormLayout()

        self._output = QLineEdit(str(output_path))
        form.addRow("出力Excel", self._create_path_row(self._output, self._browse_output))

        self._log = QLineEdit(self._auto_log_path)
        self._log.setPlaceholderText("空欄の場合はファイルへ保存しません")
        form.addRow("実行ログ", self._create_path_row(self._log, self._browse_log))

        self._mode = QComboBox()
        self._mode.addItem("時間割を生成", GenerationMode.STRICT)
        self._mode.addItem("入力検証のみ", GenerationMode.VALIDATE_ONLY)
        form.addRow("実行モード", self._mode)

        self._max_seconds = QDoubleSpinBox()
        self._max_seconds.setRange(0.1, 86400.0)
        self._max_seconds.setDecimals(1)
        self._max_seconds.setValue(60.0)
        self._max_seconds.setSuffix(" 秒")
        form.addRow("最大実行時間", self._max_seconds)

        self._random_seed = QSpinBox()
        self._random_seed.setRange(0, 2_147_483_647)
        self._random_seed.setValue(1)
        form.addRow("乱数シード", self._random_seed)

        self._workers = QSpinBox()
        self._workers.setRange(1, 256)
        self._workers.setValue(8)
        self._workers.setToolTip("再現性を優先する場合は1を指定します")
        form.addRow("並列ワーカー数", self._workers)
        root.addLayout(form)

        note = QLabel("入力検証のみを選んだ場合、出力Excelは生成されません。")
        note.setWordWrap(True)
        root.addWidget(note)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        run_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        if run_button is not None:
            run_button.setText("実行")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def values(self) -> ProjectExecutionSettingsModel:
        log_text = self._log.text().strip()
        mode = cast(GenerationMode, self._mode.currentData())
        return ProjectExecutionSettingsModel(
            output_path=Path(self._output.text().strip()).expanduser(),
            log_path=Path(log_text).expanduser() if log_text else None,
            solve_mode=mode,
            max_solve_seconds=self._max_seconds.value(),
            random_seed=self._random_seed.value(),
            num_search_workers=self._workers.value(),
        )

    def accept(self) -> None:
        output_text = self._output.text().strip()
        if not output_text:
            QMessageBox.warning(self, "入力エラー", "出力Excelの保存先を指定してください。")
            return
        if Path(output_text).suffix.lower() != ".xlsx":
            QMessageBox.warning(self, "入力エラー", "出力Excelは.xlsx形式で指定してください。")
            return
        super().accept()

    def _browse_output(self) -> None:
        previous_auto_log = self._auto_log_path
        selected, _ = QFileDialog.getSaveFileName(
            self,
            "出力Excelの保存先",
            self._output.text(),
            "Excel Workbook (*.xlsx)",
        )
        if not selected:
            return
        self._output.setText(selected)
        self._auto_log_path = str(Path(selected).with_suffix(".log"))
        if self._log.text().strip() == previous_auto_log:
            self._log.setText(self._auto_log_path)

    def _browse_log(self) -> None:
        selected, _ = QFileDialog.getSaveFileName(
            self,
            "実行ログの保存先",
            self._log.text(),
            "Log File (*.log);;All Files (*)",
        )
        if selected:
            self._log.setText(selected)

    @staticmethod
    def _create_path_row(line_edit: QLineEdit, browse: object) -> QWidget:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(line_edit, 1)
        button = QPushButton("参照")
        button.clicked.connect(browse)  # type: ignore[arg-type]
        layout.addWidget(button)
        return container

    @staticmethod
    def _default_output_path(project: ProjectModel) -> Path:
        documents = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.DocumentsLocation
        )
        base_directory = Path(documents) if documents else Path.home()
        invalid_characters = '<>:"/\\|?*'
        safe_name = "".join(
            "_" if character in invalid_characters else character for character in project.name
        ).strip()
        if not safe_name:
            safe_name = "時間割"
        return base_directory / f"{safe_name}_生成結果.xlsx"


class RunProjectWorker(QObject):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        service: ExecuteProjectService,
        project_id: str,
        settings: ProjectExecutionSettingsModel,
    ) -> None:
        super().__init__()
        self._service = service
        self._project_id = project_id
        self._settings = settings

    @Slot()
    def execute(self) -> None:
        try:
            result = self._service.execute(self._project_id, self._settings)
        except Exception as exc:
            LOGGER.exception("GUIからの時間割実行に失敗しました")
            self.failed.emit(str(exc))
            return
        self.completed.emit(result)


class DesktopWindow(QMainWindow):
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
        super().__init__()
        self._list_projects = list_projects
        self._load_project = load_project
        self._create_project = create_project
        self._import_project = import_project
        self._update_project = update_project
        self._duplicate_project = duplicate_project
        self._delete_project = delete_project
        self._execute_project = execute_project
        self._run_thread: QThread | None = None
        self._run_worker: RunProjectWorker | None = None
        self._run_progress: QProgressDialog | None = None

        self.setWindowTitle("時間割解決システム")
        self.resize(900, 640)
        self._stack = QStackedWidget()
        self._home = HomePage()
        self._editor = EditorPage()
        self._stack.addWidget(self._home)
        self._stack.addWidget(self._editor)
        self.setCentralWidget(self._stack)

        self._home.new_requested.connect(self._create_new_project)
        self._home.import_requested.connect(self._import_excel)
        self._home.open_requested.connect(self._open_project)
        self._home.run_requested.connect(self._run_existing_project)
        self._home.edit_requested.connect(self._edit_project_metadata)
        self._home.duplicate_requested.connect(self._duplicate_existing_project)
        self._home.delete_requested.connect(self._delete_existing_project)
        self._editor.back_requested.connect(self._show_home)
        self._refresh_home()

    def _refresh_home(self) -> None:
        self._home.set_projects(self._list_projects.execute())

    def _show_home(self) -> None:
        self._refresh_home()
        self._stack.setCurrentWidget(self._home)

    def _create_new_project(self) -> None:
        project = self._create_project.execute()
        self._editor.load_project(project)
        self._stack.setCurrentWidget(self._editor)

    def _open_project(self, project_id: str) -> None:
        project = self._load_project.execute(project_id)
        if project is None:
            QMessageBox.warning(self, "読込エラー", "保存済みデータが見つかりません。")
            self._refresh_home()
            return
        self._editor.load_project(project)
        self._stack.setCurrentWidget(self._editor)

    def _import_excel(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "時間割Excelを選択",
            "",
            "Excel Workbook (*.xlsx)",
        )
        if not selected:
            return
        result = self._import_project.execute(Path(selected))
        if result.project is None:
            messages = [issue.message for issue in result.issues if issue.severity == "ERROR"]
            detail = "\n".join(messages[:5]) or "Excelを読み込めませんでした。"
            QMessageBox.critical(self, "インポート失敗", detail)
            return
        self._refresh_home()
        warning_count = sum(issue.severity == "WARNING" for issue in result.issues)
        suffix = f"\n警告: {warning_count}件" if warning_count else ""
        QMessageBox.information(
            self,
            "インポート完了",
            f"「{result.project.name}」を保存しました。{suffix}",
        )

    def _run_existing_project(self, project_id: str) -> None:
        if self._run_thread is not None:
            QMessageBox.information(self, "実行中", "別の時間割を実行中です。")
            return
        project = self._load_project.execute(project_id)
        if project is None:
            QMessageBox.warning(self, "実行エラー", "保存済みデータが見つかりません。")
            self._refresh_home()
            return
        if project.imported_workbook_path is None or not project.imported_workbook_path.is_file():
            QMessageBox.information(
                self,
                "実行できません",
                "このデータには実行可能な入力がまだありません。",
            )
            return

        dialog = RunProjectDialog(project, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        settings = dialog.values()

        thread = QThread(self)
        worker = RunProjectWorker(self._execute_project, project_id, settings)
        worker.moveToThread(thread)
        worker.completed.connect(self._run_completed)
        worker.failed.connect(self._run_failed)
        worker.completed.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        worker.completed.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._run_thread_finished)

        self._run_thread = thread
        self._run_worker = worker
        self._run_progress = QProgressDialog(self)
        self._run_progress.setWindowTitle("時間割を実行")
        self._run_progress.setLabelText("時間割を生成しています...")
        self._run_progress.setRange(0, 0)
        self._run_progress.setCancelButton(None)
        self._run_progress.setWindowModality(Qt.WindowModality.WindowModal)
        self._run_progress.setMinimumDuration(0)
        self._run_progress.show()
        thread.started.connect(worker.execute)
        thread.start()

    @Slot(object)
    def _run_completed(self, raw_result: object) -> None:
        self._close_run_progress()
        result = cast(GenerationResultModel, raw_result)
        if result.exit_code == 0:
            if result.status == "VALIDATED":
                message = "入力検証が完了しました。"
            else:
                message = f"時間割生成が完了しました。\n保存先: {result.request.output_path}"
            QMessageBox.information(self, "実行完了", message)
            return

        errors = [
            issue.message
            for issue in result.validation_report.issues
            if issue.severity == "ERROR"
        ]
        details = "\n".join(errors[:5])
        message = f"実行は完了しましたが、時間割を出力できませんでした。\nstatus: {result.status}"
        if details:
            message = f"{message}\n\n{details}"
        QMessageBox.warning(self, "実行結果", message)

    @Slot(str)
    def _run_failed(self, message: str) -> None:
        self._close_run_progress()
        detail = message or "予期しないエラーが発生しました。"
        QMessageBox.critical(self, "実行エラー", detail)

    @Slot()
    def _run_thread_finished(self) -> None:
        self._run_thread = None
        self._run_worker = None

    def _close_run_progress(self) -> None:
        if self._run_progress is not None:
            self._run_progress.close()
            self._run_progress.deleteLater()
            self._run_progress = None

    def _edit_project_metadata(self, project_id: str) -> None:
        project = self._load_project.execute(project_id)
        if project is None:
            self._refresh_home()
            return
        dialog = ProjectMetadataDialog(project, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        name, note = dialog.values()
        try:
            self._update_project.execute(project_id, name, note)
        except ValueError:
            QMessageBox.warning(self, "入力エラー", "名前は空欄にできません。")
            return
        self._refresh_home()

    def _duplicate_existing_project(self, project_id: str) -> None:
        if self._duplicate_project.execute(project_id) is None:
            QMessageBox.warning(self, "複製エラー", "対象データが見つかりません。")
        self._refresh_home()

    def _delete_existing_project(self, project_id: str) -> None:
        project = self._load_project.execute(project_id)
        if project is None:
            self._refresh_home()
            return
        answer = QMessageBox.question(
            self,
            "削除の確認",
            f"「{project.name}」を削除しますか?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._delete_project.execute(project_id)
        self._refresh_home()

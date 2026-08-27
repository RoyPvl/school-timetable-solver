from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from school_timetable_solver.model.project_models import ProjectModel, ProjectSource
from school_timetable_solver.service.project_services import (
    CreateProjectService,
    DeleteProjectService,
    DuplicateProjectService,
    ImportProjectService,
    ListProjectsService,
    LoadProjectService,
    UpdateProjectMetadataService,
)


class ProjectCardWidget(QFrame):
    open_requested = Signal(str)
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
    ) -> None:
        super().__init__()
        self._list_projects = list_projects
        self._load_project = load_project
        self._create_project = create_project
        self._import_project = import_project
        self._update_project = update_project
        self._duplicate_project = duplicate_project
        self._delete_project = delete_project

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

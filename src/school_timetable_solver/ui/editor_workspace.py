from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from datetime import date, timedelta
from uuid import uuid4

from PySide6.QtCore import QDate, QLocale, Qt, QTime, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from school_timetable_solver.model.project_document_models import (
    DraftCalendarDayModel,
    DraftCampusModel,
    DraftClassModel,
    DraftClassPairOverlapRuleModel,
    DraftHomeroomBoundaryRuleModel,
    DraftLessonCountPreferenceRuleSegmentModel,
    DraftLessonCountRuleSegmentModel,
    DraftLessonRequirementModel,
    DraftPeriodModel,
    DraftPlacementRuleModel,
    DraftRoomModel,
    DraftSubjectModel,
    DraftTeacherDayOffRuleModel,
    DraftTeacherLeaveModel,
    DraftTeacherModel,
    ProjectDocumentModel,
)
from school_timetable_solver.model.project_models import ProjectModel
from school_timetable_solver.model.result_models import ValidationIssueModel
from school_timetable_solver.ui.editor_navigation import (
    COMMON_NAVIGATION,
    SEASONAL_NAVIGATION,
    EditorSection,
)
from school_timetable_solver.ui.editor_widgets import (
    EditorChoiceBox,
    EditorDateEdit,
    EditorTimeEdit,
)

DraftRow = (
    DraftCampusModel
    | DraftRoomModel
    | DraftTeacherModel
    | DraftClassModel
    | DraftSubjectModel
    | DraftPeriodModel
    | DraftCalendarDayModel
    | DraftLessonRequirementModel
    | DraftTeacherLeaveModel
    | DraftTeacherDayOffRuleModel
    | DraftHomeroomBoundaryRuleModel
    | DraftClassPairOverlapRuleModel
    | DraftPlacementRuleModel
    | DraftLessonCountRuleSegmentModel
    | DraftLessonCountPreferenceRuleSegmentModel
)

DIVISION_CHOICES = (
    ("小学", "elementary"),
    ("中学", "junior_high"),
    ("高校", "high_school"),
    ("その他", "other"),
)
EXAM_CATEGORY_CHOICES = (
    ("受験", "exam"),
    ("非受験", "non_exam"),
    ("特別", "special"),
    ("その他", "none"),
)
LESSON_TYPE_CHOICES = (("通常", "regular"), ("特別", "special"), ("その他", "other"))


class SeasonalEditorWorkspace(QWidget):
    """Widgets edit a project-owned draft; display labels never identify references."""

    back_requested = Signal()
    document_changed = Signal()
    save_requested = Signal()
    validate_requested = Signal()
    run_requested = Signal()
    reload_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.document = ProjectDocumentModel()
        self._current_project: ProjectModel | None = None
        self._section = EditorSection.SCHEDULE
        self._issues: tuple[ValidationIssueModel, ...] = ()
        self._row_indices: dict[str, list[int]] = {}
        self._master_tab_index = 0
        self._rule_tab_index = 0
        self._validation_status = "未検証"
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        header = QFrame()
        header.setObjectName("editorHeader")
        header_layout = QHBoxLayout(header)
        back = QPushButton("← 一覧")
        back.clicked.connect(lambda _checked=False: self.back_requested.emit())
        header_layout.addWidget(back)
        self._title = QLabel("時間割")
        self._title.setObjectName("projectTitle")
        header_layout.addWidget(self._title, 1)
        self._save_status = QLabel("保存済み")
        header_layout.addWidget(self._save_status)
        for label, signal in (
            ("保存", self.save_requested),
            ("再読込", self.reload_requested),
            ("入力を確認", self.validate_requested),
            ("時間割を生成", self.run_requested),
        ):
            button = QPushButton(label)
            button.clicked.connect(lambda _checked=False, signal=signal: signal.emit())
            header_layout.addWidget(button)
        root.addWidget(header)
        body = QHBoxLayout()
        navigation = QFrame()
        navigation.setObjectName("navigationPanel")
        navigation.setFixedWidth(224)
        nav = QVBoxLayout(navigation)
        nav.addWidget(QLabel("設定の土台 → 毎季の入力"))
        self._navigation_buttons: dict[EditorSection, QPushButton] = {}
        button_group = QButtonGroup(self)
        for title, items in (("共通設定", COMMON_NAVIGATION), ("講習設定", SEASONAL_NAVIGATION)):
            nav.addWidget(QLabel(title))
            for item in items:
                button = QPushButton(item.label)
                button.setCheckable(True)
                button.setProperty("navigation", True)
                button.clicked.connect(
                    lambda _checked=False, section=item.section: self._select_section(section)
                )
                button_group.addButton(button)
                self._navigation_buttons[item.section] = button
                nav.addWidget(button)
        nav.addStretch(1)
        body.addWidget(navigation)
        self._content_stack = QStackedWidget()
        body.addWidget(self._content_stack, 1)
        root.addLayout(body, 1)
        self.document_changed.connect(self._mark_changed)
        self._render_section()

    def load_project(self, project: ProjectModel, document: ProjectDocumentModel) -> None:
        self._current_project = project
        self.document = document
        self._title.setText(project.name)
        self._issues = ()
        self._validation_status = "未検証"
        self._save_status.setText("保存済み")
        self._select_section(EditorSection.SCHEDULE)

    def set_save_status(self, status: str) -> None:
        self._save_status.setText(status)

    def show_validation(self, issues: tuple[ValidationIssueModel, ...], status: str) -> None:
        self._issues = issues
        self._validation_status = status
        self._select_section(EditorSection.REVIEW)

    def _mark_changed(self) -> None:
        self._issues = ()
        self._validation_status = "変更後は未検証"
        self._save_status.setText("保存中…")

    def _select_section(self, section: EditorSection) -> None:
        self._section = section
        self._render_section()

    def _render_section(self) -> None:
        previous = self._content_stack.currentWidget()
        if previous is not None:
            self._content_stack.removeWidget(previous)
            previous.setParent(None)
            previous.deleteLater()
        self._navigation_buttons[self._section].setChecked(True)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(28, 24, 28, 28)
        label = self._navigation_buttons[self._section].text()
        title = QLabel(label)
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        if self._section == EditorSection.MASTER:
            tabs = QTabWidget()
            for title, builders in (
                ("校舎・教室", (self._campuses, self._rooms)),
                ("教師", (self._teachers,)),
                ("クラス", (self._classes,)),
                ("教科", (self._subjects,)),
                ("時限", (self._periods,)),
            ):
                tab = QWidget()
                tab_layout = QVBoxLayout(tab)
                for builder in builders:
                    builder(tab_layout)
                tabs.addTab(tab, title)
            tabs.setCurrentIndex(self._master_tab_index)
            tabs.currentChanged.connect(self._remember_master_tab)
            layout.addWidget(tabs)
        elif self._section == EditorSection.SCHEDULE:
            self._schedule(layout)
        elif self._section == EditorSection.LESSON_COUNTS:
            self._lesson_matrix(layout, False)
        elif self._section == EditorSection.TEACHER_ASSIGNMENTS:
            self._lesson_matrix(layout, True)
        elif self._section == EditorSection.TEACHER_LEAVES:
            self._leave_matrix(layout)
        elif self._section == EditorSection.PLACEMENT_CONDITIONS:
            tabs = QTabWidget()
            builders = (
                ("配置条件", self._placement_rules),
                ("厳密配置数", self._lesson_count_rule_segments),
                ("希望配置数", self._lesson_count_preference_rule_segments),
                ("担任授業期間", self._homeroom_boundary_rules),
                ("クラス組", self._class_pair_overlap_rules),
                ("教科別の1日上限", self._requirement_limits),
            )
            for title, builder in builders:
                tab = QWidget()
                builder(QVBoxLayout(tab))
                tabs.addTab(tab, title)
            tabs.setCurrentIndex(self._rule_tab_index)
            tabs.currentChanged.connect(self._remember_rule_tab)
            layout.addWidget(tabs)
        elif self._section == EditorSection.REVIEW:
            layout.addWidget(QLabel(self._validation_status))
            total = sum(
                int(row.required_periods)
                for row in self.document.lesson_requirements
                if row.enabled and row.required_periods.isdigit()
            )
            layout.addWidget(QLabel(f"授業回数合計: {total} コマ"))
            table = self._table(
                layout, "review_issues", ("ルール", "種類", "対象", "内容"), len(self._issues)
            )
            for index, issue in enumerate(self._issues):
                for column, value in enumerate(
                    (issue.rule_id, issue.severity, issue.target, issue.message)
                ):
                    self._display(table, index, column, value)
        layout.addStretch(1)
        scroll.setWidget(content)
        self._content_stack.addWidget(scroll)

    def _remember_master_tab(self, index: int) -> None:
        self._master_tab_index = index

    def _remember_rule_tab(self, index: int) -> None:
        self._rule_tab_index = index

    def _table(
        self, layout: QVBoxLayout, name: str, headers: tuple[str, ...], count: int
    ) -> QTableWidget:
        table = QTableWidget(count, len(headers))
        table.setObjectName(name)
        table.setHorizontalHeaderLabels(headers)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setDefaultSectionSize(38)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        table.horizontalHeader().setStretchLastSection(True)
        for column in range(len(headers)):
            table.setColumnWidth(column, 140)
        table.setMinimumHeight(240)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        layout.addWidget(table)
        return table

    @staticmethod
    def _display(table: QTableWidget, row: int, column: int, text: str) -> None:
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        table.setItem(row, column, item)

    def _choices(self, group: str) -> tuple[tuple[str, str], ...]:
        pairs: list[tuple[str, str]] = []
        if group == "campuses":
            pairs = [
                (row.campus_name, row.campus_id) for row in self.document.campuses if row.enabled
            ]
        elif group == "teachers":
            pairs = [
                (row.teacher_name, row.teacher_id) for row in self.document.teachers if row.enabled
            ]
        elif group == "classes":
            campus_names = dict(
                (identifier, name) for name, identifier in self._choices("campuses")
            )
            pairs = [
                (f"{campus_names.get(row.campus_id, '')} / {row.class_name}", row.class_id)
                for row in self.document.classes
                if row.enabled
            ]
        elif group == "subjects":
            pairs = [
                (row.subject_name, row.subject_id) for row in self.document.subjects if row.enabled
            ]
        elif group == "periods":
            pairs = [(row.period_name, row.period_id) for row in self.document.periods]
        counts = Counter(name for name, _identifier in pairs)
        return tuple(
            (
                f"{name or '(空欄表示)'} ({identifier[-6:]})"
                if counts[name] > 1
                else name or "(空欄表示)",
                identifier,
            )
            for name, identifier in pairs
        )

    def _cell(
        self,
        table: QTableWidget,
        row: int,
        column: int,
        value: str | bool,
        setter: Callable[[str | bool], None],
        kind: str = "text",
        choices: tuple[tuple[str, str], ...] | None = None,
    ) -> None:
        if kind == "boolean":
            checkbox = QCheckBox()
            checkbox.setChecked(value is True)
            checkbox.toggled.connect(setter)
            table.setCellWidget(row, column, checkbox)
            return
        text = str(value)
        if kind == "choice":
            combo = EditorChoiceBox()
            combo.addItem("未指定", "")
            for label, identifier in choices or ():
                combo.addItem(label, identifier)
            index = combo.findData(text)
            if index < 0:
                combo.addItem("参照先がありません" if text else "未指定", text)
                index = combo.count() - 1
            combo.setCurrentIndex(index)
            combo.setMinimumWidth(100)
            combo.currentIndexChanged.connect(lambda _index: setter(str(combo.currentData())))
            table.setCellWidget(row, column, combo)
        elif kind == "date":
            edit = EditorDateEdit()
            edit.setCalendarPopup(True)
            edit.setLocale(QLocale(QLocale.Language.Japanese, QLocale.Country.Japan))
            edit.setDisplayFormat("yyyy/MM/dd (ddd)")
            edit.setMinimumDate(QDate(1752, 9, 14))
            edit.setSpecialValueText("未入力")
            selected = QDate.fromString(text, "yyyy-MM-dd")
            if text and not selected.isValid():
                self._cell(table, row, column, text, setter)
                return
            edit.setDate(selected if selected.isValid() else edit.minimumDate())
            edit.dateChanged.connect(
                lambda selected: setter(
                    "" if selected == edit.minimumDate() else selected.toString("yyyy-MM-dd")
                )
            )
            table.setCellWidget(row, column, edit)
        elif kind == "time":
            edit = EditorTimeEdit()
            edit.setDisplayFormat("HH:mm")
            selected = QTime.fromString(text, "HH:mm:ss")
            if not selected.isValid():
                selected = QTime.fromString(text, "HH:mm")
            if text and not selected.isValid():
                self._cell(table, row, column, text, setter)
                return
            edit.setTime(selected if selected.isValid() else QTime(0, 0))
            edit.timeChanged.connect(lambda selected: setter(selected.toString("HH:mm:ss")))
            edit.editingFinished.connect(lambda: setter(edit.time().toString("HH:mm:ss")))
            table.setCellWidget(row, column, edit)
        elif kind == "periods":
            button = QToolButton()
            selected_ids = [part for part in text.split("|") if part]
            labels = dict((identifier, label) for label, identifier in choices or ())
            button.setText(
                " ".join(labels.get(identifier, "不明") for identifier in selected_ids)
                or "指定なし"
            )
            button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            menu = QMenu(button)
            for label, identifier in choices or ():
                action = menu.addAction(label)
                action.setCheckable(True)
                action.setChecked(identifier in selected_ids)
                action.toggled.connect(
                    lambda checked, identifier=identifier: self._toggle_period(
                        selected_ids, identifier, checked, setter, button, labels
                    )
                )
            button.setMenu(menu)
            table.setCellWidget(row, column, button)
        else:
            edit = QLineEdit(text)
            edit.textChanged.connect(setter)
            table.setCellWidget(row, column, edit)

    @staticmethod
    def _toggle_period(
        selected: list[str],
        identifier: str,
        checked: bool,
        setter: Callable[[str | bool], None],
        button: QToolButton,
        labels: dict[str, str],
    ) -> None:
        if checked and identifier not in selected:
            selected.append(identifier)
        elif not checked and identifier in selected:
            selected.remove(identifier)
        setter("|".join(selected))
        button.setText(" ".join(labels.get(value, "不明") for value in selected) or "指定なし")

    def _schedule(self, layout: QVBoxLayout) -> None:
        group = QGroupBox("講習期間")
        bar = QHBoxLayout(group)
        for label, field in (("開始日", "start_date"), ("終了日", "end_date")):
            bar.addWidget(QLabel(label))
            edit = EditorDateEdit()
            edit.setCalendarPopup(True)
            edit.setDisplayFormat("yyyy/MM/dd")
            text = self.document.start_date if field == "start_date" else self.document.end_date
            edit.setMinimumDate(QDate(1752, 9, 14))
            edit.setSpecialValueText("未入力")
            selected = QDate.fromString(text, "yyyy-MM-dd")
            edit.setDate(selected if selected.isValid() else edit.minimumDate())
            edit.setObjectName(field)
            edit.dateChanged.connect(
                lambda selected, field=field: self._set_range(
                    field, selected.toString("yyyy-MM-dd")
                )
            )
            bar.addWidget(edit)
        create = QPushButton("期間から日付を作成")
        create.clicked.connect(self._create_dates)
        bar.addWidget(create)
        layout.addWidget(group)
        rows = self.document.calendar_days
        periods = self._choices("periods")
        table = self._table(
            layout,
            "calendar_days",
            ("日付", *(name for name, _identifier in periods), "備考", "出力"),
            len(rows),
        )
        table.setColumnWidth(0, 190)
        table.horizontalHeader().setStretchLastSection(False)
        table.horizontalHeader().setSectionResizeMode(
            len(periods) + 1, QHeaderView.ResizeMode.Stretch
        )
        table.setColumnWidth(len(periods) + 2, 70)
        for index, row in enumerate(rows):
            self._cell(
                table,
                index,
                0,
                row.target_date,
                lambda value, row=row: self._set_value(row, "target_date", value),
                "date",
            )
            for column, (_name, period_id) in enumerate(periods, 1):
                table.setColumnWidth(column, 70)
                selected = period_id in row.enabled_period_ids.split("|")
                combo = EditorChoiceBox()
                combo.setProperty("selectionField", False)
                combo.addItems(("✓", "—"))
                combo.setCurrentIndex(0 if selected else 1)
                combo.currentIndexChanged.connect(
                    lambda selected, row=row, period_id=period_id: self._set_calendar_period(
                        row, period_id, selected == 0
                    )
                )
                table.setCellWidget(index, column, combo)
            self._cell(
                table,
                index,
                len(periods) + 1,
                row.note,
                lambda value, row=row: self._set_value(row, "note", value),
            )
            self._cell(
                table,
                index,
                len(periods) + 2,
                row.output_enabled,
                lambda value, row=row: self._set_value(row, "output_enabled", value),
                "boolean",
            )
        actions = QHBoxLayout()
        for text, callback in (
            ("+ 日付を追加", self._add_date),
            ("選択日の全時限をON", lambda: self._set_day_periods(table.currentRow(), True)),
            ("選択日を休館日にする", lambda: self._set_day_periods(table.currentRow(), False)),
            ("選択日を削除", lambda: self._remove_row("calendar_days", table.currentRow())),
        ):
            button = QPushButton(text)
            button.clicked.connect(callback)
            actions.addWidget(button)
        layout.addLayout(actions)

    def _set_range(self, field: str, value: str) -> None:
        if field == "start_date":
            self.document.start_date = value
        else:
            self.document.end_date = value
        self.document_changed.emit()

    def _create_dates(self) -> None:
        try:
            first = date.fromisoformat(self.document.start_date)
            last = date.fromisoformat(self.document.end_date)
        except ValueError:
            self.set_save_status("開始日と終了日を選んでください")
            return
        if last < first:
            self.set_save_status("終了日は開始日以降にしてください")
            return
        existing = {row.target_date for row in self.document.calendar_days}
        for offset in range((last - first).days + 1):
            value = (first + timedelta(days=offset)).isoformat()
            if value not in existing:
                self.document.calendar_days.append(
                    DraftCalendarDayModel(
                        value,
                        True,
                        "|".join(identifier for _label, identifier in self._choices("periods")),
                        "",
                    )
                )
        self.document.calendar_days.sort(key=lambda row: row.target_date)
        self.document_changed.emit()
        self._render_section()

    def _add_date(self) -> None:
        self.document.calendar_days.append(DraftCalendarDayModel())
        self.document_changed.emit()
        self._render_section()

    def _set_day_periods(self, index: int, enabled: bool) -> None:
        if index < 0:
            return
        self.document.calendar_days[index].enabled_period_ids = (
            "|".join(identifier for _label, identifier in self._choices("periods"))
            if enabled
            else ""
        )
        self.document_changed.emit()
        self._render_section()

    def _set_calendar_period(
        self, row: DraftCalendarDayModel, period_id: str, enabled: bool
    ) -> None:
        values = [value for value in row.enabled_period_ids.split("|") if value]
        if enabled and period_id not in values:
            values.append(period_id)
        elif not enabled and period_id in values:
            values.remove(period_id)
        row.enabled_period_ids = "|".join(values)
        self.document_changed.emit()

    def _lesson_matrix(self, layout: QVBoxLayout, assignments: bool) -> None:
        classes = [row for row in self.document.classes if row.enabled]
        subjects = self._choices("subjects")
        headers = (
            ("クラス", "担任", *(name for name, _identifier in subjects))
            if assignments
            else ("クラス", *(name for name, _identifier in subjects), "計")
        )
        table = self._table(
            layout, "teacher_assignments" if assignments else "lesson_counts", headers, len(classes)
        )
        names = dict((identifier, name) for name, identifier in self._choices("classes"))
        for index, class_row in enumerate(classes):
            self._display(table, index, 0, names[class_row.class_id])
            if assignments:
                self._cell(
                    table,
                    index,
                    1,
                    class_row.homeroom_teacher_id,
                    lambda value, row=class_row: self._set_value(row, "homeroom_teacher_id", value),
                    "choice",
                    self._choices("teachers"),
                )
            total = 0
            for column, (_name, subject_id) in enumerate(subjects, 2 if assignments else 1):
                requirement = next(
                    (
                        row
                        for row in self.document.lesson_requirements
                        if row.class_id == class_row.class_id and row.subject_id == subject_id
                    ),
                    None,
                )
                value = (
                    requirement.teacher_id
                    if assignments and requirement
                    else requirement.required_periods
                    if requirement
                    else ""
                )
                self._cell(
                    table,
                    index,
                    column,
                    value,
                    lambda value, class_id=class_row.class_id, subject_id=subject_id: (
                        self._set_requirement(class_id, subject_id, assignments, str(value), table)
                    ),
                    "choice" if assignments else "text",
                    self._choices("teachers") if assignments else None,
                )
                if requirement and requirement.required_periods.isdigit():
                    total += int(requirement.required_periods)
            if not assignments:
                self._display(table, index, len(headers) - 1, str(total))
        if assignments:
            teacher_names = dict(
                (identifier, name) for name, identifier in self._choices("teachers")
            )
            self._teacher_load = QLabel()
            layout.addWidget(self._teacher_load)
            self._update_teacher_load(teacher_names)
        hint = QLabel(
            "クラス・教科の追加は共通設定から行います。授業回数を空欄または0にすると、この講習では開講しません。"
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

    def _set_requirement(
        self, class_id: str, subject_id: str, assignments: bool, value: str, table: QTableWidget
    ) -> None:
        row = next(
            (
                row
                for row in self.document.lesson_requirements
                if row.class_id == class_id and row.subject_id == subject_id
            ),
            None,
        )
        if row is None:
            row = DraftLessonRequirementModel(
                requirement_id=uuid4().hex, class_id=class_id, subject_id=subject_id
            )
            self.document.lesson_requirements.append(row)
        if assignments:
            row.teacher_id = value
        else:
            row.required_periods = value
        row.enabled = row.required_periods.strip() not in ("", "0")
        self.document_changed.emit()
        if not assignments:
            classes = [item for item in self.document.classes if item.enabled]
            index = next(index for index, item in enumerate(classes) if item.class_id == class_id)
            total = sum(
                int(item.required_periods)
                for item in self.document.lesson_requirements
                if item.enabled and item.class_id == class_id and item.required_periods.isdigit()
            )
            self._display(table, index, table.columnCount() - 1, str(total))
        else:
            self._update_teacher_load(
                dict((identifier, name) for name, identifier in self._choices("teachers"))
            )

    def _update_teacher_load(self, names: dict[str, str]) -> None:
        totals: dict[str, int] = {}
        for row in self.document.lesson_requirements:
            if row.enabled and row.required_periods.isdigit():
                totals[row.teacher_id] = totals.get(row.teacher_id, 0) + int(row.required_periods)
        self._teacher_load.setText(
            "教師別予定コマ数: "
            + " / ".join(
                f"{names.get(identifier, '未指定')}: {count}"
                for identifier, count in totals.items()
            )
        )

    def _requirement_limits(self, layout: QVBoxLayout) -> None:
        rows = [row for row in self.document.lesson_requirements if row.enabled]
        classes = dict((identifier, name) for name, identifier in self._choices("classes"))
        subjects = dict((identifier, name) for name, identifier in self._choices("subjects"))
        table = self._table(
            layout, "requirement_limits", ("クラス", "教科", "教科ごとの1日上限"), len(rows)
        )
        for index, row in enumerate(rows):
            self._display(table, index, 0, classes.get(row.class_id, "参照先がありません"))
            self._display(table, index, 1, subjects.get(row.subject_id, "参照先がありません"))
            self._cell(
                table,
                index,
                2,
                row.max_periods_per_day,
                lambda value, row=row: self._set_value(row, "max_periods_per_day", value),
            )
        layout.addWidget(QLabel("空欄の場合、このクラス・教科の1日上限は設定しません。"))

    def _leave_matrix(self, layout: QVBoxLayout) -> None:
        teachers = self._choices("teachers")
        dates = [row.target_date for row in self.document.calendar_days if row.output_enabled]
        table = self._table(layout, "teacher_leaves", ("教師", *dates), len(teachers))
        table.setColumnWidth(0, 120)
        for column in range(1, len(dates) + 1):
            table.setColumnWidth(column, 88)
        for index, (name, teacher_id) in enumerate(teachers):
            self._display(table, index, 0, name)
            for column, target_date in enumerate(dates, 1):
                leave = next(
                    (
                        row
                        for row in self.document.teacher_leaves
                        if row.teacher_id == teacher_id and row.target_date == target_date
                    ),
                    None,
                )
                self._cell(
                    table,
                    index,
                    column,
                    leave.unavailable_period_ids if leave else "",
                    lambda value, teacher_id=teacher_id, target_date=target_date: self._set_leave(
                        teacher_id, target_date, str(value)
                    ),
                    "periods",
                    self._choices("periods"),
                )
        self._teacher_day_off_rules(layout)

    def _set_leave(self, teacher_id: str, target_date: str, value: str) -> None:
        leave = next(
            (
                row
                for row in self.document.teacher_leaves
                if row.teacher_id == teacher_id and row.target_date == target_date
            ),
            None,
        )
        if leave is None and value:
            self.document.teacher_leaves.append(
                DraftTeacherLeaveModel(teacher_id, target_date, value)
            )
        elif leave is not None:
            if value:
                leave.unavailable_period_ids = value
            else:
                self.document.teacher_leaves.remove(leave)
        self.document_changed.emit()

    def _periods(self, layout: QVBoxLayout) -> None:
        rows = self.document.periods
        table = self._table(
            layout,
            "periods",
            (
                "時限",
                "開始",
                "終了",
            ),
            len(rows),
        )
        for index, row in enumerate(rows):
            self._cell(
                table,
                index,
                0,
                row.period_name,
                lambda value, row=row: self._set_value(row, "period_name", value),
                "text",
                None,
            )
            self._cell(
                table,
                index,
                1,
                row.start_time,
                lambda value, row=row: self._set_value(row, "start_time", value),
                "time",
                None,
            )
            self._cell(
                table,
                index,
                2,
                row.end_time,
                lambda value, row=row: self._set_value(row, "end_time", value),
                "time",
                None,
            )
        actions = QHBoxLayout()
        add = QPushButton("+ 追加")
        add.clicked.connect(lambda: self._append_row("periods"))
        actions.addWidget(add)
        remove = QPushButton("選択行を削除")
        remove.clicked.connect(lambda: self._remove_row("periods", table.currentRow()))
        actions.addWidget(remove)
        up = QPushButton("↑")
        down = QPushButton("↓")
        up.clicked.connect(lambda: self._move_row("periods", table.currentRow(), -1))
        down.clicked.connect(lambda: self._move_row("periods", table.currentRow(), 1))
        actions.addWidget(up)
        actions.addWidget(down)
        actions.addStretch(1)
        layout.addLayout(actions)

    def _campuses(self, layout: QVBoxLayout) -> None:
        self._row_indices["campuses"] = [
            index for index, row in enumerate(self.document.campuses) if row.enabled
        ]
        rows = [row for row in self.document.campuses if row.enabled]
        table = self._table(layout, "campuses", ("校舎",), len(rows))
        for index, row in enumerate(rows):
            self._cell(
                table,
                index,
                0,
                row.campus_name,
                lambda value, row=row: self._set_value(row, "campus_name", value),
                "text",
                None,
            )
        actions = QHBoxLayout()
        add = QPushButton("+ 追加")
        add.clicked.connect(lambda: self._append_row("campuses"))
        actions.addWidget(add)
        remove = QPushButton("選択行を削除")
        remove.clicked.connect(lambda: self._remove_row("campuses", table.currentRow()))
        actions.addWidget(remove)
        up = QPushButton("↑")
        down = QPushButton("↓")
        up.clicked.connect(lambda: self._move_row("campuses", table.currentRow(), -1))
        down.clicked.connect(lambda: self._move_row("campuses", table.currentRow(), 1))
        actions.addWidget(up)
        actions.addWidget(down)
        actions.addStretch(1)
        layout.addLayout(actions)

    def _rooms(self, layout: QVBoxLayout) -> None:
        self._row_indices["rooms"] = [
            index for index, row in enumerate(self.document.rooms) if row.enabled
        ]
        rows = [row for row in self.document.rooms if row.enabled]
        table = self._table(
            layout,
            "rooms",
            (
                "教室",
                "校舎",
                "優先度",
            ),
            len(rows),
        )
        for index, row in enumerate(rows):
            self._cell(
                table,
                index,
                0,
                row.room_name,
                lambda value, row=row: self._set_value(row, "room_name", value),
                "text",
                None,
            )
            self._cell(
                table,
                index,
                1,
                row.campus_id,
                lambda value, row=row: self._set_value(row, "campus_id", value),
                "choice",
                self._choices("campuses"),
            )
            self._cell(
                table,
                index,
                2,
                row.priority,
                lambda value, row=row: self._set_value(row, "priority", value),
                "text",
                None,
            )
        actions = QHBoxLayout()
        add = QPushButton("+ 追加")
        add.clicked.connect(lambda: self._append_row("rooms"))
        actions.addWidget(add)
        remove = QPushButton("選択行を削除")
        remove.clicked.connect(lambda: self._remove_row("rooms", table.currentRow()))
        actions.addWidget(remove)
        up = QPushButton("↑")
        down = QPushButton("↓")
        up.clicked.connect(lambda: self._move_row("rooms", table.currentRow(), -1))
        down.clicked.connect(lambda: self._move_row("rooms", table.currentRow(), 1))
        actions.addWidget(up)
        actions.addWidget(down)
        actions.addStretch(1)
        layout.addLayout(actions)

    def _teachers(self, layout: QVBoxLayout) -> None:
        self._row_indices["teachers"] = [
            index for index, row in enumerate(self.document.teachers) if row.enabled
        ]
        rows = [row for row in self.document.teachers if row.enabled]
        table = self._table(
            layout,
            "teachers",
            (
                "教師",
                "所属校舎",
            ),
            len(rows),
        )
        for index, row in enumerate(rows):
            self._cell(
                table,
                index,
                0,
                row.teacher_name,
                lambda value, row=row: self._set_value(row, "teacher_name", value),
                "text",
                None,
            )
            self._cell(
                table,
                index,
                1,
                row.home_campus_id,
                lambda value, row=row: self._set_value(row, "home_campus_id", value),
                "choice",
                self._choices("campuses"),
            )
        actions = QHBoxLayout()
        add = QPushButton("+ 追加")
        add.clicked.connect(lambda: self._append_row("teachers"))
        actions.addWidget(add)
        remove = QPushButton("選択行を削除")
        remove.clicked.connect(lambda: self._remove_row("teachers", table.currentRow()))
        actions.addWidget(remove)
        up = QPushButton("↑")
        down = QPushButton("↓")
        up.clicked.connect(lambda: self._move_row("teachers", table.currentRow(), -1))
        down.clicked.connect(lambda: self._move_row("teachers", table.currentRow(), 1))
        actions.addWidget(up)
        actions.addWidget(down)
        actions.addStretch(1)
        layout.addLayout(actions)

    def _classes(self, layout: QVBoxLayout) -> None:
        self._row_indices["classes"] = [
            index for index, row in enumerate(self.document.classes) if row.enabled
        ]
        rows = [row for row in self.document.classes if row.enabled]
        table = self._table(
            layout,
            "classes",
            (
                "クラス",
                "校舎",
                "学部",
                "学年",
                "受験区分",
                "担任",
            ),
            len(rows),
        )
        for index, row in enumerate(rows):
            self._cell(
                table,
                index,
                0,
                row.class_name,
                lambda value, row=row: self._set_value(row, "class_name", value),
                "text",
                None,
            )
            self._cell(
                table,
                index,
                1,
                row.campus_id,
                lambda value, row=row: self._set_value(row, "campus_id", value),
                "choice",
                self._choices("campuses"),
            )
            self._cell(
                table,
                index,
                2,
                row.division,
                lambda value, row=row: self._set_value(row, "division", value),
                "choice",
                DIVISION_CHOICES,
            )
            self._cell(
                table,
                index,
                3,
                row.grade,
                lambda value, row=row: self._set_value(row, "grade", value),
                "text",
                None,
            )
            self._cell(
                table,
                index,
                4,
                row.exam_category,
                lambda value, row=row: self._set_value(row, "exam_category", value),
                "choice",
                EXAM_CATEGORY_CHOICES,
            )
            self._cell(
                table,
                index,
                5,
                row.homeroom_teacher_id,
                lambda value, row=row: self._set_value(row, "homeroom_teacher_id", value),
                "choice",
                self._choices("teachers"),
            )
        actions = QHBoxLayout()
        add = QPushButton("+ 追加")
        add.clicked.connect(lambda: self._append_row("classes"))
        actions.addWidget(add)
        remove = QPushButton("選択行を削除")
        remove.clicked.connect(lambda: self._remove_row("classes", table.currentRow()))
        actions.addWidget(remove)
        up = QPushButton("↑")
        down = QPushButton("↓")
        up.clicked.connect(lambda: self._move_row("classes", table.currentRow(), -1))
        down.clicked.connect(lambda: self._move_row("classes", table.currentRow(), 1))
        actions.addWidget(up)
        actions.addWidget(down)
        actions.addStretch(1)
        layout.addLayout(actions)

    def _subjects(self, layout: QVBoxLayout) -> None:
        self._row_indices["subjects"] = [
            index for index, row in enumerate(self.document.subjects) if row.enabled
        ]
        rows = [row for row in self.document.subjects if row.enabled]
        table = self._table(
            layout,
            "subjects",
            (
                "教科",
                "授業種別",
            ),
            len(rows),
        )
        for index, row in enumerate(rows):
            self._cell(
                table,
                index,
                0,
                row.subject_name,
                lambda value, row=row: self._set_value(row, "subject_name", value),
                "text",
                None,
            )
            self._cell(
                table,
                index,
                1,
                row.lesson_type,
                lambda value, row=row: self._set_value(row, "lesson_type", value),
                "choice",
                LESSON_TYPE_CHOICES,
            )
        actions = QHBoxLayout()
        add = QPushButton("+ 追加")
        add.clicked.connect(lambda: self._append_row("subjects"))
        actions.addWidget(add)
        remove = QPushButton("選択行を削除")
        remove.clicked.connect(lambda: self._remove_row("subjects", table.currentRow()))
        actions.addWidget(remove)
        up = QPushButton("↑")
        down = QPushButton("↓")
        up.clicked.connect(lambda: self._move_row("subjects", table.currentRow(), -1))
        down.clicked.connect(lambda: self._move_row("subjects", table.currentRow(), 1))
        actions.addWidget(up)
        actions.addWidget(down)
        actions.addStretch(1)
        layout.addLayout(actions)

    def _placement_rules(self, layout: QVBoxLayout) -> None:
        rows = self.document.placement_rules
        table = self._table(
            layout,
            "placement_rules",
            (
                "名称",
                "使用",
                "条件種別",
                "対象種別",
                "条件項目",
                "比較方法",
                "条件値",
                "校舎",
                "開始日",
                "終了日",
                "曜日",
                "利用可能時限",
                "1日上限",
                "初限・最終限の同日禁止",
                "連続登校上限",
                "優先度",
                "希望連続登校日数",
                "必須授業時限",
            ),
            len(rows),
        )
        for index, row in enumerate(rows):
            self._cell(
                table,
                index,
                0,
                row.rule_name,
                lambda value, row=row: self._set_value(row, "rule_name", value),
                "text",
                None,
            )
            self._cell(
                table,
                index,
                1,
                row.enabled,
                lambda value, row=row: self._set_value(row, "enabled", value),
                "boolean",
                None,
            )
            self._cell(
                table,
                index,
                2,
                row.constraint_type,
                lambda value, row=row: self._set_value(row, "constraint_type", value),
                "choice",
                (("絶対条件", "hard"), ("上書き", "override")),
            )
            self._cell(
                table,
                index,
                3,
                row.target_entity,
                lambda value, row=row: self._set_value(row, "target_entity", value),
                "choice",
                (("クラス", "class"), ("教師", "teacher")),
            )
            self._cell(
                table,
                index,
                4,
                row.condition_fields,
                lambda value, row=row: self._set_value(row, "condition_fields", value),
                "text",
                None,
            )
            self._cell(
                table,
                index,
                5,
                row.condition_operators,
                lambda value, row=row: self._set_value(row, "condition_operators", value),
                "text",
                None,
            )
            self._cell(
                table,
                index,
                6,
                row.condition_values,
                lambda value, row=row: self._set_value(row, "condition_values", value),
                "text",
                None,
            )
            self._cell(
                table,
                index,
                7,
                row.campus_id,
                lambda value, row=row: self._set_value(row, "campus_id", value),
                "choice",
                self._choices("campuses"),
            )
            self._cell(
                table,
                index,
                8,
                row.start_date,
                lambda value, row=row: self._set_value(row, "start_date", value),
                "date",
                None,
            )
            self._cell(
                table,
                index,
                9,
                row.end_date,
                lambda value, row=row: self._set_value(row, "end_date", value),
                "date",
                None,
            )
            self._cell(
                table,
                index,
                10,
                row.weekdays,
                lambda value, row=row: self._set_value(row, "weekdays", value),
                "text",
                None,
            )
            self._cell(
                table,
                index,
                11,
                row.allowed_period_ids,
                lambda value, row=row: self._set_value(row, "allowed_period_ids", value),
                "periods",
                self._choices("periods"),
            )
            self._cell(
                table,
                index,
                12,
                row.daily_hard_limit,
                lambda value, row=row: self._set_value(row, "daily_hard_limit", value),
                "text",
                None,
            )
            self._cell(
                table,
                index,
                13,
                row.forbid_first_last_same_day,
                lambda value, row=row: self._set_value(row, "forbid_first_last_same_day", value),
                "choice",
                (("指定なし", ""), ("禁止", "true"), ("許可", "false")),
            )
            self._cell(
                table,
                index,
                14,
                row.attendance_streak_limit,
                lambda value, row=row: self._set_value(row, "attendance_streak_limit", value),
                "text",
                None,
            )
            self._cell(
                table,
                index,
                15,
                row.priority,
                lambda value, row=row: self._set_value(row, "priority", value),
                "text",
                None,
            )
            self._cell(
                table,
                index,
                16,
                row.preferred_attendance_streak_limit,
                lambda value, row=row: self._set_value(
                    row, "preferred_attendance_streak_limit", value
                ),
                "text",
                None,
            )
            self._cell(
                table,
                index,
                17,
                row.required_lesson_period_ids,
                lambda value, row=row: self._set_value(row, "required_lesson_period_ids", value),
                "periods",
                self._choices("periods"),
            )
        actions = QHBoxLayout()
        add = QPushButton("+ 追加")
        add.clicked.connect(lambda: self._append_row("placement_rules"))
        actions.addWidget(add)
        remove = QPushButton("選択行を削除")
        remove.clicked.connect(lambda: self._remove_row("placement_rules", table.currentRow()))
        actions.addWidget(remove)
        actions.addStretch(1)
        layout.addLayout(actions)

    def _lesson_count_rule_segments(self, layout: QVBoxLayout) -> None:
        rows = self.document.lesson_count_rule_segments
        table = self._table(
            layout,
            "lesson_count_rule_segments",
            (
                "名称",
                "使用",
                "クラス",
                "教科",
                "厳密コマ数",
                "開始日",
                "終了日",
                "対象時限",
            ),
            len(rows),
        )
        for index, row in enumerate(rows):
            self._cell(
                table,
                index,
                0,
                row.rule_name,
                lambda value, row=row: self._set_value(row, "rule_name", value),
                "text",
                None,
            )
            self._cell(
                table,
                index,
                1,
                row.enabled,
                lambda value, row=row: self._set_value(row, "enabled", value),
                "boolean",
                None,
            )
            self._cell(
                table,
                index,
                2,
                row.class_id,
                lambda value, row=row: self._set_value(row, "class_id", value),
                "choice",
                self._choices("classes"),
            )
            self._cell(
                table,
                index,
                3,
                row.subject_id,
                lambda value, row=row: self._set_value(row, "subject_id", value),
                "choice",
                self._choices("subjects"),
            )
            self._cell(
                table,
                index,
                4,
                row.exact_periods,
                lambda value, row=row: self._set_value(row, "exact_periods", value),
                "text",
                None,
            )
            self._cell(
                table,
                index,
                5,
                row.start_date,
                lambda value, row=row: self._set_value(row, "start_date", value),
                "date",
                None,
            )
            self._cell(
                table,
                index,
                6,
                row.end_date,
                lambda value, row=row: self._set_value(row, "end_date", value),
                "date",
                None,
            )
            self._cell(
                table,
                index,
                7,
                row.target_period_ids,
                lambda value, row=row: self._set_value(row, "target_period_ids", value),
                "periods",
                self._choices("periods"),
            )
        actions = QHBoxLayout()
        add = QPushButton("+ 追加")
        add.clicked.connect(lambda: self._append_row("lesson_count_rule_segments"))
        actions.addWidget(add)
        remove = QPushButton("選択行を削除")
        remove.clicked.connect(
            lambda: self._remove_row("lesson_count_rule_segments", table.currentRow())
        )
        actions.addWidget(remove)
        actions.addStretch(1)
        layout.addLayout(actions)

    def _lesson_count_preference_rule_segments(self, layout: QVBoxLayout) -> None:
        rows = self.document.lesson_count_preference_rule_segments
        table = self._table(
            layout,
            "lesson_count_preference_rule_segments",
            (
                "名称",
                "使用",
                "クラス",
                "教科",
                "希望コマ数",
                "開始日",
                "終了日",
                "対象時限",
            ),
            len(rows),
        )
        for index, row in enumerate(rows):
            self._cell(
                table,
                index,
                0,
                row.rule_name,
                lambda value, row=row: self._set_value(row, "rule_name", value),
                "text",
                None,
            )
            self._cell(
                table,
                index,
                1,
                row.enabled,
                lambda value, row=row: self._set_value(row, "enabled", value),
                "boolean",
                None,
            )
            self._cell(
                table,
                index,
                2,
                row.class_id,
                lambda value, row=row: self._set_value(row, "class_id", value),
                "choice",
                self._choices("classes"),
            )
            self._cell(
                table,
                index,
                3,
                row.subject_id,
                lambda value, row=row: self._set_value(row, "subject_id", value),
                "choice",
                self._choices("subjects"),
            )
            self._cell(
                table,
                index,
                4,
                row.preferred_periods,
                lambda value, row=row: self._set_value(row, "preferred_periods", value),
                "text",
                None,
            )
            self._cell(
                table,
                index,
                5,
                row.start_date,
                lambda value, row=row: self._set_value(row, "start_date", value),
                "date",
                None,
            )
            self._cell(
                table,
                index,
                6,
                row.end_date,
                lambda value, row=row: self._set_value(row, "end_date", value),
                "date",
                None,
            )
            self._cell(
                table,
                index,
                7,
                row.target_period_ids,
                lambda value, row=row: self._set_value(row, "target_period_ids", value),
                "periods",
                self._choices("periods"),
            )
        actions = QHBoxLayout()
        add = QPushButton("+ 追加")
        add.clicked.connect(lambda: self._append_row("lesson_count_preference_rule_segments"))
        actions.addWidget(add)
        remove = QPushButton("選択行を削除")
        remove.clicked.connect(
            lambda: self._remove_row("lesson_count_preference_rule_segments", table.currentRow())
        )
        actions.addWidget(remove)
        actions.addStretch(1)
        layout.addLayout(actions)

    def _teacher_day_off_rules(self, layout: QVBoxLayout) -> None:
        rows = self.document.teacher_day_off_rules
        table = self._table(
            layout,
            "teacher_day_off_rules",
            (
                "教師",
                "使用",
                "対象日(日付を | 区切り)",
                "必要休日日数",
                "最小休日日数",
                "最大休日日数",
                "休日日数グループ",
                "グループ必要休日数",
                "希望休日日数",
            ),
            len(rows),
        )
        for index, row in enumerate(rows):
            self._cell(
                table,
                index,
                0,
                row.teacher_id,
                lambda value, row=row: self._set_value(row, "teacher_id", value),
                "choice",
                self._choices("teachers"),
            )
            self._cell(
                table,
                index,
                1,
                row.enabled,
                lambda value, row=row: self._set_value(row, "enabled", value),
                "boolean",
                None,
            )
            self._cell(
                table,
                index,
                2,
                row.eligible_dates,
                lambda value, row=row: self._set_value(row, "eligible_dates", value),
                "text",
                None,
            )
            self._cell(
                table,
                index,
                3,
                row.required_days_off,
                lambda value, row=row: self._set_value(row, "required_days_off", value),
                "text",
                None,
            )
            self._cell(
                table,
                index,
                4,
                row.minimum_days_off,
                lambda value, row=row: self._set_value(row, "minimum_days_off", value),
                "text",
                None,
            )
            self._cell(
                table,
                index,
                5,
                row.maximum_days_off,
                lambda value, row=row: self._set_value(row, "maximum_days_off", value),
                "text",
                None,
            )
            self._cell(
                table,
                index,
                6,
                row.quota_group_id,
                lambda value, row=row: self._set_value(row, "quota_group_id", value),
                "text",
                None,
            )
            self._cell(
                table,
                index,
                7,
                row.group_required_days_off,
                lambda value, row=row: self._set_value(row, "group_required_days_off", value),
                "text",
                None,
            )
            self._cell(
                table,
                index,
                8,
                row.preferred_days_off,
                lambda value, row=row: self._set_value(row, "preferred_days_off", value),
                "text",
                None,
            )
        actions = QHBoxLayout()
        add = QPushButton("+ 追加")
        add.clicked.connect(lambda: self._append_row("teacher_day_off_rules"))
        actions.addWidget(add)
        remove = QPushButton("選択行を削除")
        remove.clicked.connect(
            lambda: self._remove_row("teacher_day_off_rules", table.currentRow())
        )
        actions.addWidget(remove)
        actions.addStretch(1)
        layout.addLayout(actions)

    def _homeroom_boundary_rules(self, layout: QVBoxLayout) -> None:
        rows = self.document.homeroom_boundary_rules
        table = self._table(
            layout,
            "homeroom_boundary_rules",
            (
                "名称",
                "使用",
                "条件項目",
                "比較方法",
                "条件値",
                "開始日",
                "終了日",
            ),
            len(rows),
        )
        for index, row in enumerate(rows):
            self._cell(
                table,
                index,
                0,
                row.rule_name,
                lambda value, row=row: self._set_value(row, "rule_name", value),
                "text",
                None,
            )
            self._cell(
                table,
                index,
                1,
                row.enabled,
                lambda value, row=row: self._set_value(row, "enabled", value),
                "boolean",
                None,
            )
            self._cell(
                table,
                index,
                2,
                row.condition_fields,
                lambda value, row=row: self._set_value(row, "condition_fields", value),
                "text",
                None,
            )
            self._cell(
                table,
                index,
                3,
                row.condition_operators,
                lambda value, row=row: self._set_value(row, "condition_operators", value),
                "text",
                None,
            )
            self._cell(
                table,
                index,
                4,
                row.condition_values,
                lambda value, row=row: self._set_value(row, "condition_values", value),
                "text",
                None,
            )
            self._cell(
                table,
                index,
                5,
                row.start_date,
                lambda value, row=row: self._set_value(row, "start_date", value),
                "date",
                None,
            )
            self._cell(
                table,
                index,
                6,
                row.end_date,
                lambda value, row=row: self._set_value(row, "end_date", value),
                "date",
                None,
            )
        actions = QHBoxLayout()
        add = QPushButton("+ 追加")
        add.clicked.connect(lambda: self._append_row("homeroom_boundary_rules"))
        actions.addWidget(add)
        remove = QPushButton("選択行を削除")
        remove.clicked.connect(
            lambda: self._remove_row("homeroom_boundary_rules", table.currentRow())
        )
        actions.addWidget(remove)
        actions.addStretch(1)
        layout.addLayout(actions)

    def _class_pair_overlap_rules(self, layout: QVBoxLayout) -> None:
        rows = self.document.class_pair_overlap_rules
        table = self._table(
            layout,
            "class_pair_overlap_rules",
            (
                "名称",
                "使用",
                "先行クラス",
                "後続クラス",
            ),
            len(rows),
        )
        for index, row in enumerate(rows):
            self._cell(
                table,
                index,
                0,
                row.rule_name,
                lambda value, row=row: self._set_value(row, "rule_name", value),
                "text",
                None,
            )
            self._cell(
                table,
                index,
                1,
                row.enabled,
                lambda value, row=row: self._set_value(row, "enabled", value),
                "boolean",
                None,
            )
            self._cell(
                table,
                index,
                2,
                row.first_class_id,
                lambda value, row=row: self._set_value(row, "first_class_id", value),
                "choice",
                self._choices("classes"),
            )
            self._cell(
                table,
                index,
                3,
                row.second_class_id,
                lambda value, row=row: self._set_value(row, "second_class_id", value),
                "choice",
                self._choices("classes"),
            )
        actions = QHBoxLayout()
        add = QPushButton("+ 追加")
        add.clicked.connect(lambda: self._append_row("class_pair_overlap_rules"))
        actions.addWidget(add)
        remove = QPushButton("選択行を削除")
        remove.clicked.connect(
            lambda: self._remove_row("class_pair_overlap_rules", table.currentRow())
        )
        actions.addWidget(remove)
        actions.addStretch(1)
        layout.addLayout(actions)

    def _set_value(self, row: DraftRow, field: str, value: str | bool) -> None:
        if isinstance(value, bool):
            if isinstance(row, DraftCampusModel) and field == "enabled":
                row.enabled = value
                self.document_changed.emit()
                return
            if isinstance(row, DraftRoomModel) and field == "enabled":
                row.enabled = value
                self.document_changed.emit()
                return
            if isinstance(row, DraftTeacherModel) and field == "enabled":
                row.enabled = value
                self.document_changed.emit()
                return
            if isinstance(row, DraftClassModel) and field == "enabled":
                row.enabled = value
                self.document_changed.emit()
                return
            if isinstance(row, DraftSubjectModel) and field == "enabled":
                row.enabled = value
                self.document_changed.emit()
                return
            if isinstance(row, DraftCalendarDayModel) and field == "output_enabled":
                row.output_enabled = value
                self.document_changed.emit()
                return
            if isinstance(row, DraftLessonRequirementModel) and field == "enabled":
                row.enabled = value
                self.document_changed.emit()
                return
            if isinstance(row, DraftTeacherDayOffRuleModel) and field == "enabled":
                row.enabled = value
                self.document_changed.emit()
                return
            if isinstance(row, DraftHomeroomBoundaryRuleModel) and field == "enabled":
                row.enabled = value
                self.document_changed.emit()
                return
            if isinstance(row, DraftClassPairOverlapRuleModel) and field == "enabled":
                row.enabled = value
                self.document_changed.emit()
                return
            if isinstance(row, DraftPlacementRuleModel) and field == "enabled":
                row.enabled = value
                self.document_changed.emit()
                return
            if isinstance(row, DraftLessonCountRuleSegmentModel) and field == "enabled":
                row.enabled = value
                self.document_changed.emit()
                return
            if isinstance(row, DraftLessonCountPreferenceRuleSegmentModel) and field == "enabled":
                row.enabled = value
                self.document_changed.emit()
                return
        else:
            if isinstance(row, DraftCampusModel):
                match field:
                    case "campus_id":
                        row.campus_id = value
                    case "campus_name":
                        row.campus_name = value
                    case "output_order":
                        row.output_order = value
                    case _:
                        raise ValueError(f"未対応の入力項目です: {field}")
                self.document_changed.emit()
                return
            if isinstance(row, DraftRoomModel):
                match field:
                    case "room_id":
                        row.room_id = value
                    case "room_name":
                        row.room_name = value
                    case "campus_id":
                        row.campus_id = value
                    case "output_order":
                        row.output_order = value
                    case "priority":
                        row.priority = value
                    case _:
                        raise ValueError(f"未対応の入力項目です: {field}")
                self.document_changed.emit()
                return
            if isinstance(row, DraftTeacherModel):
                match field:
                    case "teacher_id":
                        row.teacher_id = value
                    case "teacher_name":
                        row.teacher_name = value
                    case "home_campus_id":
                        row.home_campus_id = value
                    case _:
                        raise ValueError(f"未対応の入力項目です: {field}")
                self.document_changed.emit()
                return
            if isinstance(row, DraftClassModel):
                match field:
                    case "class_id":
                        row.class_id = value
                    case "class_name":
                        row.class_name = value
                    case "campus_id":
                        row.campus_id = value
                    case "division":
                        row.division = value
                    case "grade":
                        row.grade = value
                    case "exam_category":
                        row.exam_category = value
                    case "homeroom_teacher_id":
                        row.homeroom_teacher_id = value
                    case _:
                        raise ValueError(f"未対応の入力項目です: {field}")
                self.document_changed.emit()
                return
            if isinstance(row, DraftSubjectModel):
                match field:
                    case "subject_id":
                        row.subject_id = value
                    case "subject_name":
                        row.subject_name = value
                    case "lesson_type":
                        row.lesson_type = value
                    case _:
                        raise ValueError(f"未対応の入力項目です: {field}")
                self.document_changed.emit()
                return
            if isinstance(row, DraftPeriodModel):
                match field:
                    case "period_id":
                        row.period_id = value
                    case "period_name":
                        row.period_name = value
                    case "output_order":
                        row.output_order = value
                    case "start_time":
                        row.start_time = value
                    case "end_time":
                        row.end_time = value
                    case _:
                        raise ValueError(f"未対応の入力項目です: {field}")
                self.document_changed.emit()
                return
            if isinstance(row, DraftCalendarDayModel):
                match field:
                    case "target_date":
                        row.target_date = value
                    case "enabled_period_ids":
                        row.enabled_period_ids = value
                    case "note":
                        row.note = value
                    case _:
                        raise ValueError(f"未対応の入力項目です: {field}")
                self.document_changed.emit()
                return
            if isinstance(row, DraftLessonRequirementModel):
                match field:
                    case "requirement_id":
                        row.requirement_id = value
                    case "class_id":
                        row.class_id = value
                    case "subject_id":
                        row.subject_id = value
                    case "teacher_id":
                        row.teacher_id = value
                    case "required_periods":
                        row.required_periods = value
                    case "max_periods_per_day":
                        row.max_periods_per_day = value
                    case _:
                        raise ValueError(f"未対応の入力項目です: {field}")
                self.document_changed.emit()
                return
            if isinstance(row, DraftTeacherLeaveModel):
                match field:
                    case "teacher_id":
                        row.teacher_id = value
                    case "target_date":
                        row.target_date = value
                    case "unavailable_period_ids":
                        row.unavailable_period_ids = value
                    case _:
                        raise ValueError(f"未対応の入力項目です: {field}")
                self.document_changed.emit()
                return
            if isinstance(row, DraftTeacherDayOffRuleModel):
                match field:
                    case "rule_id":
                        row.rule_id = value
                    case "teacher_id":
                        row.teacher_id = value
                    case "eligible_dates":
                        row.eligible_dates = value
                    case "required_days_off":
                        row.required_days_off = value
                    case "minimum_days_off":
                        row.minimum_days_off = value
                    case "maximum_days_off":
                        row.maximum_days_off = value
                    case "quota_group_id":
                        row.quota_group_id = value
                    case "group_required_days_off":
                        row.group_required_days_off = value
                    case "preferred_days_off":
                        row.preferred_days_off = value
                    case _:
                        raise ValueError(f"未対応の入力項目です: {field}")
                self.document_changed.emit()
                return
            if isinstance(row, DraftHomeroomBoundaryRuleModel):
                match field:
                    case "rule_id":
                        row.rule_id = value
                    case "rule_name":
                        row.rule_name = value
                    case "condition_fields":
                        row.condition_fields = value
                    case "condition_operators":
                        row.condition_operators = value
                    case "condition_values":
                        row.condition_values = value
                    case "start_date":
                        row.start_date = value
                    case "end_date":
                        row.end_date = value
                    case _:
                        raise ValueError(f"未対応の入力項目です: {field}")
                self.document_changed.emit()
                return
            if isinstance(row, DraftClassPairOverlapRuleModel):
                match field:
                    case "rule_id":
                        row.rule_id = value
                    case "rule_name":
                        row.rule_name = value
                    case "first_class_id":
                        row.first_class_id = value
                    case "second_class_id":
                        row.second_class_id = value
                    case _:
                        raise ValueError(f"未対応の入力項目です: {field}")
                self.document_changed.emit()
                return
            if isinstance(row, DraftPlacementRuleModel):
                match field:
                    case "rule_id":
                        row.rule_id = value
                    case "rule_name":
                        row.rule_name = value
                    case "constraint_type":
                        row.constraint_type = value
                    case "target_entity":
                        row.target_entity = value
                    case "condition_fields":
                        row.condition_fields = value
                    case "condition_operators":
                        row.condition_operators = value
                    case "condition_values":
                        row.condition_values = value
                    case "campus_id":
                        row.campus_id = value
                    case "start_date":
                        row.start_date = value
                    case "end_date":
                        row.end_date = value
                    case "weekdays":
                        row.weekdays = value
                    case "allowed_period_ids":
                        row.allowed_period_ids = value
                    case "daily_hard_limit":
                        row.daily_hard_limit = value
                    case "forbid_first_last_same_day":
                        row.forbid_first_last_same_day = value
                    case "attendance_streak_limit":
                        row.attendance_streak_limit = value
                    case "priority":
                        row.priority = value
                    case "preferred_attendance_streak_limit":
                        row.preferred_attendance_streak_limit = value
                    case "required_lesson_period_ids":
                        row.required_lesson_period_ids = value
                    case _:
                        raise ValueError(f"未対応の入力項目です: {field}")
                self.document_changed.emit()
                return
            if isinstance(row, DraftLessonCountRuleSegmentModel):
                match field:
                    case "rule_id":
                        row.rule_id = value
                    case "segment_id":
                        row.segment_id = value
                    case "rule_name":
                        row.rule_name = value
                    case "class_id":
                        row.class_id = value
                    case "subject_id":
                        row.subject_id = value
                    case "exact_periods":
                        row.exact_periods = value
                    case "start_date":
                        row.start_date = value
                    case "end_date":
                        row.end_date = value
                    case "target_period_ids":
                        row.target_period_ids = value
                    case _:
                        raise ValueError(f"未対応の入力項目です: {field}")
                self.document_changed.emit()
                return
            if isinstance(row, DraftLessonCountPreferenceRuleSegmentModel):
                match field:
                    case "rule_id":
                        row.rule_id = value
                    case "segment_id":
                        row.segment_id = value
                    case "rule_name":
                        row.rule_name = value
                    case "class_id":
                        row.class_id = value
                    case "subject_id":
                        row.subject_id = value
                    case "preferred_periods":
                        row.preferred_periods = value
                    case "start_date":
                        row.start_date = value
                    case "end_date":
                        row.end_date = value
                    case "target_period_ids":
                        row.target_period_ids = value
                    case _:
                        raise ValueError(f"未対応の入力項目です: {field}")
                self.document_changed.emit()
                return
        raise TypeError("入力値の型が不正です")

    def _append_row(self, group: str) -> None:
        identifier = uuid4().hex
        if group == "periods":
            self.document.periods.append(
                DraftPeriodModel(
                    period_id=identifier, output_order=str(len(self.document.periods) + 1)
                )
            )
        if group == "campuses":
            self.document.campuses.append(
                DraftCampusModel(
                    campus_id=identifier, output_order=str(len(self.document.campuses) + 1)
                )
            )
        if group == "rooms":
            self.document.rooms.append(
                DraftRoomModel(
                    room_id=identifier, output_order=str(len(self.document.rooms) + 1), priority="0"
                )
            )
        if group == "teachers":
            self.document.teachers.append(DraftTeacherModel(teacher_id=identifier))
        if group == "classes":
            self.document.classes.append(
                DraftClassModel(class_id=identifier, division="other", exam_category="none")
            )
        if group == "subjects":
            self.document.subjects.append(
                DraftSubjectModel(subject_id=identifier, lesson_type="regular")
            )
        if group == "placement_rules":
            self.document.placement_rules.append(DraftPlacementRuleModel(rule_id=identifier))
        if group == "lesson_count_rule_segments":
            self.document.lesson_count_rule_segments.append(
                DraftLessonCountRuleSegmentModel(
                    rule_id=identifier, segment_id=identifier + "_segment"
                )
            )
        if group == "lesson_count_preference_rule_segments":
            self.document.lesson_count_preference_rule_segments.append(
                DraftLessonCountPreferenceRuleSegmentModel(
                    rule_id=identifier, segment_id=identifier + "_segment"
                )
            )
        if group == "teacher_day_off_rules":
            self.document.teacher_day_off_rules.append(
                DraftTeacherDayOffRuleModel(rule_id=identifier)
            )
        if group == "homeroom_boundary_rules":
            self.document.homeroom_boundary_rules.append(
                DraftHomeroomBoundaryRuleModel(rule_id=identifier)
            )
        if group == "class_pair_overlap_rules":
            self.document.class_pair_overlap_rules.append(
                DraftClassPairOverlapRuleModel(rule_id=identifier)
            )
        self.document_changed.emit()
        self._render_section()

    def _remove_row(self, group: str, index: int) -> None:
        if index < 0:
            return
        if group in self._row_indices:
            index = self._row_indices[group][index]
        if group == "calendar_days":
            del self.document.calendar_days[index]
        if group == "periods":
            del self.document.periods[index]
        if group == "campuses":
            del self.document.campuses[index]
        if group == "rooms":
            del self.document.rooms[index]
        if group == "teachers":
            del self.document.teachers[index]
        if group == "classes":
            del self.document.classes[index]
        if group == "subjects":
            del self.document.subjects[index]
        if group == "lesson_requirements":
            del self.document.lesson_requirements[index]
        if group == "teacher_leaves":
            del self.document.teacher_leaves[index]
        if group == "placement_rules":
            del self.document.placement_rules[index]
        if group == "lesson_count_rule_segments":
            del self.document.lesson_count_rule_segments[index]
        if group == "lesson_count_preference_rule_segments":
            del self.document.lesson_count_preference_rule_segments[index]
        if group == "teacher_day_off_rules":
            del self.document.teacher_day_off_rules[index]
        if group == "homeroom_boundary_rules":
            del self.document.homeroom_boundary_rules[index]
        if group == "class_pair_overlap_rules":
            del self.document.class_pair_overlap_rules[index]
        self.document_changed.emit()
        self._render_section()

    def _move_row(self, group: str, index: int, direction: int) -> None:
        if index < 0:
            return
        visible = self._row_indices.get(group)
        if visible is not None:
            target = index + direction
            if not 0 <= target < len(visible):
                return
            direction = visible[target] - visible[index]
            index = visible[index]
        if group == "campuses":
            rows = self.document.campuses
            destination = index + direction
            if not 0 <= destination < len(rows):
                return
            rows[index], rows[destination] = rows[destination], rows[index]
            for order, row in enumerate(rows, 1):
                row.output_order = str(order)
        if group == "rooms":
            rows = self.document.rooms
            destination = index + direction
            if not 0 <= destination < len(rows):
                return
            rows[index], rows[destination] = rows[destination], rows[index]
            orders: dict[str, int] = {}
            for row in rows:
                orders[row.campus_id] = orders.get(row.campus_id, 0) + 1
                row.output_order = str(orders[row.campus_id])
        if group == "periods":
            rows = self.document.periods
            destination = index + direction
            if not 0 <= destination < len(rows):
                return
            rows[index], rows[destination] = rows[destination], rows[index]
            for order, row in enumerate(rows, 1):
                row.output_order = str(order)
        if group == "teachers":
            rows = self.document.teachers
            destination = index + direction
            if not 0 <= destination < len(rows):
                return
            rows[index], rows[destination] = rows[destination], rows[index]
        if group == "classes":
            rows = self.document.classes
            destination = index + direction
            if not 0 <= destination < len(rows):
                return
            rows[index], rows[destination] = rows[destination], rows[index]
        if group == "subjects":
            rows = self.document.subjects
            destination = index + direction
            if not 0 <= destination < len(rows):
                return
            rows[index], rows[destination] = rows[destination], rows[index]
        self.document_changed.emit()
        self._render_section()

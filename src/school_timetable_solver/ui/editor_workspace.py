from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from typing import cast

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from school_timetable_solver.model.input_models import InputDataModel
from school_timetable_solver.model.project_models import ProjectModel, ProjectSource
from school_timetable_solver.ui.editor_navigation import (
    COMMON_NAVIGATION,
    SEASONAL_NAVIGATION,
    EditorNavigationItem,
    EditorSection,
)

_WEEKDAYS = ("月", "火", "水", "木", "金", "土", "日")


class SeasonalEditorWorkspace(QWidget):
    """Editor arranged around common masters and the seasonal maintenance workflow."""

    back_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._navigation_buttons: dict[EditorSection, QPushButton] = {}
        self._pages: dict[EditorSection, QWidget] = {}
        self._current_project: ProjectModel | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_header())
        root.addWidget(self._build_prototype_notice())

        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)
        body_layout.addWidget(self._build_navigation())

        self._content_stack = QStackedWidget()
        self._build_pages()
        body_layout.addWidget(self._content_stack, 1)
        root.addWidget(body, 1)

        self._select_section(EditorSection.SCHEDULE)

    def load_project(
        self,
        project: ProjectModel,
        input_data: InputDataModel | None = None,
    ) -> None:
        self._current_project = project
        self._title.setText(project.name)
        self._note.setText(project.note or "備考なし")
        if project.source is ProjectSource.EXCEL_IMPORT:
            self._source.setText("Excelインポート済み")
        else:
            self._source.setText("新規作成")

        cast(SchedulePage, self._pages[EditorSection.SCHEDULE]).load_input_data(input_data)
        cast(LessonCountsPage, self._pages[EditorSection.LESSON_COUNTS]).load_input_data(
            input_data
        )
        cast(
            TeacherAssignmentsPage,
            self._pages[EditorSection.TEACHER_ASSIGNMENTS],
        ).load_input_data(input_data)
        cast(TeacherLeavesPage, self._pages[EditorSection.TEACHER_LEAVES]).load_input_data(
            input_data
        )
        cast(MasterPage, self._pages[EditorSection.MASTER]).load_input_data(input_data)
        cast(ReviewPage, self._pages[EditorSection.REVIEW]).load_input_data(input_data)
        self._select_section(EditorSection.SCHEDULE)

    def _build_header(self) -> QWidget:
        header = QFrame()
        header.setObjectName("editorHeader")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(20, 14, 20, 14)

        back = QPushButton("← 一覧")
        back.setObjectName("backButton")
        back.clicked.connect(lambda _checked=False: self.back_requested.emit())
        layout.addWidget(back)

        title_area = QVBoxLayout()
        title_area.setSpacing(2)
        self._title = QLabel("時間割")
        self._title.setObjectName("projectTitle")
        self._note = QLabel("備考なし")
        self._note.setObjectName("projectNote")
        title_area.addWidget(self._title)
        title_area.addWidget(self._note)
        layout.addLayout(title_area, 1)

        self._source = QLabel("新規作成")
        self._source.setObjectName("sourceBadge")
        layout.addWidget(self._source)
        return header

    def _build_prototype_notice(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("prototypeNotice")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(20, 8, 20, 8)
        title = QLabel("UIプロトタイプ")
        title.setObjectName("prototypeTitle")
        detail = QLabel(
            "インポート済みデータは実値を表示します。ここで変更した値の保存はまだ接続していません。"
        )
        detail.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(detail, 1)
        return frame

    def _build_navigation(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("navigationPanel")
        panel.setFixedWidth(224)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 18, 14, 18)
        layout.setSpacing(5)

        guide = QLabel("設定の土台 → 毎季の入力")
        guide.setObjectName("navigationGuide")
        layout.addWidget(guide)
        layout.addSpacing(6)

        self._button_group = QButtonGroup(self)
        self._button_group.setExclusive(True)

        common_title = QLabel("共通設定")
        common_title.setObjectName("navigationGroupTitle")
        layout.addWidget(common_title)
        for item in COMMON_NAVIGATION:
            layout.addWidget(self._create_navigation_button(item))

        layout.addSpacing(18)
        seasonal_title = QLabel("講習設定")
        seasonal_title.setObjectName("navigationGroupTitle")
        layout.addWidget(seasonal_title)
        for item in SEASONAL_NAVIGATION:
            layout.addWidget(self._create_navigation_button(item))

        layout.addStretch(1)
        note = QLabel("教科・教師・クラスなどの共通設定を基準に、下の講習設定を作ります。")
        note.setObjectName("navigationNote")
        note.setWordWrap(True)
        layout.addWidget(note)
        return panel

    def _create_navigation_button(self, item: EditorNavigationItem) -> QPushButton:
        button = QPushButton(item.label)
        button.setCheckable(True)
        button.setProperty("navigation", True)
        button.clicked.connect(
            lambda _checked=False, section=item.section: self._select_section(section)
        )
        self._button_group.addButton(button)
        self._navigation_buttons[item.section] = button
        return button

    def _build_pages(self) -> None:
        pages: tuple[tuple[EditorSection, QWidget], ...] = (
            (EditorSection.MASTER, MasterPage()),
            (EditorSection.SCHEDULE, SchedulePage()),
            (EditorSection.LESSON_COUNTS, LessonCountsPage()),
            (EditorSection.TEACHER_ASSIGNMENTS, TeacherAssignmentsPage()),
            (EditorSection.TEACHER_LEAVES, TeacherLeavesPage()),
            (EditorSection.PLACEMENT_CONDITIONS, PlacementConditionsPage()),
            (EditorSection.REVIEW, ReviewPage()),
        )
        for section, page in pages:
            self._pages[section] = page
            self._content_stack.addWidget(page)

    def _select_section(self, section: EditorSection) -> None:
        button = self._navigation_buttons.get(section)
        page = self._pages.get(section)
        if button is not None:
            button.setChecked(True)
        if page is not None:
            self._content_stack.setCurrentWidget(page)


class SchedulePage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        root, content = _page_shell(
            self,
            "日程",
            "最初に講習期間、休館日、学校行事、日ごとの使用可能時限を決めます。",
            "毎季更新",
        )

        period_group = QGroupBox("講習期間")
        period_layout = QHBoxLayout(period_group)
        period_layout.addWidget(QLabel("開始日"))
        self._start = QDateEdit()
        self._start.setCalendarPopup(True)
        self._start.setDisplayFormat("yyyy/MM/dd")
        period_layout.addWidget(self._start)
        period_layout.addWidget(QLabel("終了日"))
        self._end = QDateEdit()
        self._end.setCalendarPopup(True)
        self._end.setDisplayFormat("yyyy/MM/dd")
        period_layout.addWidget(self._end)
        period_layout.addWidget(QPushButton("期間から日付を作成"))
        period_layout.addStretch(1)
        content.addWidget(period_group)

        calendar_group = QGroupBox("開講日と利用可能時限")
        calendar_layout = QVBoxLayout(calendar_group)
        actions = QHBoxLayout()
        actions.addWidget(QPushButton("+ 日付を追加"))
        actions.addWidget(QPushButton("選択日の全時限をON"))
        actions.addWidget(QPushButton("選択日を休館日にする"))
        actions.addStretch(1)
        calendar_layout.addLayout(actions)
        self._table = _editable_table(
            ("日付", "曜", "①", "②", "③", "④", "⑤", "⑥", "備考"),
            0,
        )
        calendar_layout.addWidget(self._table)
        content.addWidget(calendar_group)

        hint = QLabel(
            "学校の終業式・始業式、休館、模試などの特殊日は、日付行の時限ON/OFFと備考で扱います。"
        )
        hint.setObjectName("pageHint")
        hint.setWordWrap(True)
        content.addWidget(hint)
        content.addStretch(1)
        root.setWidget(_wrap_content(content))

    def load_input_data(self, input_data: InputDataModel | None) -> None:
        if input_data is None:
            _set_table_data(
                self._table,
                ("日付", "曜", "①", "②", "③", "④", "⑤", "⑥", "備考"),
                (),
            )
            return
        periods = tuple(sorted(input_data.periods, key=lambda period: period.output_order))
        days = tuple(sorted(input_data.calendar_days, key=lambda day: day.target_date))
        if days:
            first = days[0].target_date
            last = days[-1].target_date
            self._start.setDate(QDate(first.year, first.month, first.day))
            self._end.setDate(QDate(last.year, last.month, last.day))
        rows = []
        for day in days:
            enabled = set(day.enabled_period_ids) if day.output_enabled else set()
            rows.append(
                (
                    day.target_date.strftime("%Y/%m/%d"),
                    _WEEKDAYS[day.target_date.weekday()],
                    *("✓" if period.period_id in enabled else "—" for period in periods),
                    day.note or "",
                )
            )
        _set_table_data(
            self._table,
            ("日付", "曜", *(period.period_name for period in periods), "備考"),
            rows,
        )


class LessonCountsPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._input_data: InputDataModel | None = None
        root, content = _page_shell(
            self,
            "授業回数",
            "今期開講するクラスと、クラス・教科ごとの必要コマ数をまとめて設定します。",
            "毎季更新",
        )

        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("校舎"))
        self._campus = QComboBox()
        self._campus.currentIndexChanged.connect(self._render)
        toolbar.addWidget(self._campus)
        toolbar.addWidget(QPushButton("+ クラスを追加"))
        toolbar.addStretch(1)
        content.addLayout(toolbar)

        group = QGroupBox("クラス別 授業回数")
        group_layout = QVBoxLayout(group)
        self._table = _editable_table(("クラス", "計"), 0)
        group_layout.addWidget(self._table)
        content.addWidget(group)

        summary = QHBoxLayout()
        total_card, self._total_value = _summary_card_parts("コマ合計", "0")
        campus_card, self._campus_value = _summary_card_parts("校舎別合計", "0")
        summary.addWidget(total_card)
        summary.addWidget(campus_card)
        summary.addStretch(1)
        content.addLayout(summary)

        hint = QLabel("教科列は共通設定の教科マスタから動的に生成します。")
        hint.setObjectName("pageHint")
        content.addWidget(hint)
        content.addStretch(1)
        root.setWidget(_wrap_content(content))

    def load_input_data(self, input_data: InputDataModel | None) -> None:
        self._input_data = input_data
        self._campus.blockSignals(True)
        self._campus.clear()
        self._campus.addItem("すべて", None)
        if input_data is not None:
            for campus in sorted(input_data.campuses, key=lambda item: item.output_order):
                if campus.enabled:
                    self._campus.addItem(campus.campus_name, campus.campus_id)
        self._campus.blockSignals(False)
        self._render()

    def _render(self, _index: int = 0) -> None:
        data = self._input_data
        if data is None:
            _set_table_data(self._table, ("クラス", "計"), ())
            self._total_value.setText("0")
            self._campus_value.setText("0")
            return
        campus_id = self._campus.currentData()
        subjects = tuple(subject for subject in data.subjects if subject.enabled)
        classes = tuple(
            class_model
            for class_model in data.classes
            if class_model.enabled
            and (campus_id is None or class_model.campus_id == campus_id)
        )
        counts: dict[tuple[str, str], int] = defaultdict(int)
        for requirement in data.lesson_requirements:
            if requirement.enabled:
                counts[(requirement.class_id, requirement.subject_id)] += requirement.required_periods
        rows = []
        visible_total = 0
        for class_model in classes:
            values = [counts[(class_model.class_id, subject.subject_id)] for subject in subjects]
            row_total = sum(values)
            visible_total += row_total
            rows.append((class_model.class_name, *values, row_total))
        _set_table_data(
            self._table,
            ("クラス", *(subject.subject_name for subject in subjects), "計"),
            rows,
        )
        all_total = sum(
            requirement.required_periods
            for requirement in data.lesson_requirements
            if requirement.enabled
        )
        self._total_value.setText(f"{all_total} コマ")
        self._campus_value.setText(f"{visible_total} コマ")


class TeacherAssignmentsPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._input_data: InputDataModel | None = None
        root, content = _page_shell(
            self,
            "担当教師",
            "クラスを行、担任・教科を列にして、今使っている担当者表に近い形で割り当てます。",
            "毎季確認・変更",
        )

        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("校舎"))
        self._campus = QComboBox()
        self._campus.currentIndexChanged.connect(self._render)
        toolbar.addWidget(self._campus)
        toolbar.addWidget(QPushButton("前回の担当を引き継ぐ"))
        toolbar.addStretch(1)
        content.addLayout(toolbar)

        assignment_group = QGroupBox("クラス別 担当者")
        assignment_layout = QVBoxLayout(assignment_group)
        self._table = _editable_table(("クラス", "担任"), 0)
        assignment_layout.addWidget(self._table)
        content.addWidget(assignment_group)

        self._load_group = QGroupBox("教師別 予定コマ数 - 自動集計")
        self._load_layout = QGridLayout(self._load_group)
        content.addWidget(self._load_group)

        hint = QLabel("担当列も共通設定の教科マスタを基準に生成します。")
        hint.setObjectName("pageHint")
        content.addWidget(hint)
        content.addStretch(1)
        root.setWidget(_wrap_content(content))

    def load_input_data(self, input_data: InputDataModel | None) -> None:
        self._input_data = input_data
        self._campus.blockSignals(True)
        self._campus.clear()
        self._campus.addItem("すべて", None)
        if input_data is not None:
            for campus in sorted(input_data.campuses, key=lambda item: item.output_order):
                if campus.enabled:
                    self._campus.addItem(campus.campus_name, campus.campus_id)
        self._campus.blockSignals(False)
        self._render()

    def _render(self, _index: int = 0) -> None:
        data = self._input_data
        if data is None:
            _set_table_data(self._table, ("クラス", "担任"), ())
            _clear_layout(self._load_layout)
            return
        campus_id = self._campus.currentData()
        subjects = tuple(subject for subject in data.subjects if subject.enabled)
        classes = tuple(
            class_model
            for class_model in data.classes
            if class_model.enabled
            and (campus_id is None or class_model.campus_id == campus_id)
        )
        teacher_names = {teacher.teacher_id: teacher.teacher_name for teacher in data.teachers}
        assignments: dict[tuple[str, str], set[str]] = defaultdict(set)
        teacher_loads: dict[str, int] = defaultdict(int)
        for requirement in data.lesson_requirements:
            if not requirement.enabled:
                continue
            assignments[(requirement.class_id, requirement.subject_id)].add(
                teacher_names.get(requirement.teacher_id, requirement.teacher_id)
            )
            teacher_loads[requirement.teacher_id] += requirement.required_periods
        rows = []
        for class_model in classes:
            homeroom = teacher_names.get(class_model.homeroom_teacher_id or "", "")
            subject_teachers = [
                " / ".join(sorted(assignments[(class_model.class_id, subject.subject_id)]))
                for subject in subjects
            ]
            rows.append((class_model.class_name, homeroom, *subject_teachers))
        _set_table_data(
            self._table,
            ("クラス", "担任", *(subject.subject_name for subject in subjects)),
            rows,
        )
        _clear_layout(self._load_layout)
        ranked = sorted(
            (
                (teacher_names.get(teacher_id, teacher_id), periods)
                for teacher_id, periods in teacher_loads.items()
            ),
            key=lambda item: (-item[1], item[0]),
        )
        for index, (teacher_name, periods) in enumerate(ranked):
            self._load_layout.addWidget(
                _summary_card(teacher_name, f"{periods} コマ"), index // 4, index % 4
            )


class TeacherLeavesPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        root, content = _page_shell(
            self,
            "教師の休み",
            "提出された休み希望を、教師 x 日付の表でまとめて入力します。",
            "毎季更新",
        )

        toolbar = QHBoxLayout()
        toolbar.addWidget(QPushButton("希望休を入力"))
        toolbar.addWidget(QPushButton("選択範囲を休みにする"))
        toolbar.addWidget(QPushButton("選択範囲を解除"))
        toolbar.addStretch(1)
        content.addLayout(toolbar)

        matrix_group = QGroupBox("休み希望マトリクス")
        matrix_layout = QVBoxLayout(matrix_group)
        self._table = _editable_table(("教師",), 0)
        matrix_layout.addWidget(self._table)
        content.addWidget(matrix_group)

        quota_group = QGroupBox("期間内の休日日数")
        quota_layout = QVBoxLayout(quota_group)
        self._quota_table = _editable_table(
            ("教師", "対象期間", "必要休日日数", "希望休日日数"), 0
        )
        quota_layout.addWidget(self._quota_table)
        content.addWidget(quota_group)
        content.addStretch(1)
        root.setWidget(_wrap_content(content))

    def load_input_data(self, input_data: InputDataModel | None) -> None:
        if input_data is None:
            _set_table_data(self._table, ("教師",), ())
            _set_table_data(
                self._quota_table,
                ("教師", "対象期間", "必要休日日数", "希望休日日数"),
                (),
            )
            return
        days = tuple(
            day for day in sorted(input_data.calendar_days, key=lambda item: item.target_date)
            if day.output_enabled
        )
        periods = {period.period_id: period.period_name for period in input_data.periods}
        leaves: dict[tuple[str, object], tuple[str, ...]] = {}
        for leave in input_data.teacher_leaves:
            leaves[(leave.teacher_id, leave.target_date)] = leave.unavailable_period_ids
        rows = []
        for teacher in input_data.teachers:
            if not teacher.enabled:
                continue
            values = []
            for day in days:
                unavailable = leaves.get((teacher.teacher_id, day.target_date), ())
                values.append(" ".join(periods.get(period_id, period_id) for period_id in unavailable))
            rows.append((teacher.teacher_name, *values))
        _set_table_data(
            self._table,
            ("教師", *(day.target_date.strftime("%-m/%-d") for day in days)),
            rows,
        )

        teacher_names = {teacher.teacher_id: teacher.teacher_name for teacher in input_data.teachers}
        quota_rows = []
        for rule in input_data.teacher_day_off_rules:
            if not rule.enabled:
                continue
            dates = sorted(rule.eligible_dates)
            date_range = ""
            if dates:
                date_range = f"{dates[0]:%m/%d} - {dates[-1]:%m/%d}"
            quota_rows.append(
                (
                    teacher_names.get(rule.teacher_id, rule.teacher_id),
                    date_range,
                    rule.required_days_off if rule.required_days_off is not None else "",
                    rule.preferred_days_off if rule.preferred_days_off is not None else "",
                )
            )
        _set_table_data(
            self._quota_table,
            ("教師", "対象期間", "必要休日日数", "希望休日日数"),
            quota_rows,
        )


class PlacementConditionsPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        root, content = _page_shell(
            self,
            "配置条件",
            "通常の方針は分かりやすい項目で確認し、今期だけの例外を追加します。",
            "毎季確認・例外追加",
        )
        common_group = QGroupBox("よく使う配置条件")
        common_layout = QGridLayout(common_group)
        cards = (
            ("クラスの利用可能時限", "小学部・中学部などの時間帯"),
            ("1日の授業上限", "クラス・教師の1日コマ数"),
            ("連続登校", "最大連続日数と希望値"),
            ("教師の勤務", "1限と最終限の同日回避など"),
        )
        for index, (title, description) in enumerate(cards):
            common_layout.addWidget(_condition_card(title, description), index // 2, index % 2)
        content.addWidget(common_group)

        exception_group = QGroupBox("今期だけの例外")
        exception_layout = QVBoxLayout(exception_group)
        actions = QHBoxLayout()
        actions.addWidget(QPushButton("+ 例外を追加"))
        actions.addStretch(1)
        exception_layout.addLayout(actions)
        exception_layout.addWidget(
            _editable_table(("対象", "期間・日付", "条件", "内容", "有効"), 6)
        )
        content.addWidget(exception_group)
        advanced = QPushButton("高度なルールを表示")
        advanced.setToolTip("配置数、担任授業期間、クラス組重複禁止など")
        content.addWidget(advanced, 0, Qt.AlignmentFlag.AlignLeft)
        content.addStretch(1)
        root.setWidget(_wrap_content(content))


class ReviewPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        root, content = _page_shell(
            self,
            "入力確認",
            "実行前に不足・矛盾と、自動集計した負荷をまとめて確認します。",
            "実行前",
        )
        status_group = QGroupBox("入力状況")
        status_layout = QVBoxLayout(status_group)
        self._statuses: list[QLabel] = []
        for label in ("日程", "授業回数", "担当教師", "教師の休み", "配置条件"):
            row = QHBoxLayout()
            row.addWidget(QLabel(label))
            row.addStretch(1)
            status = QLabel("未検証")
            status.setObjectName("reviewStatus")
            self._statuses.append(status)
            row.addWidget(status)
            status_layout.addLayout(row)
        content.addWidget(status_group)
        summary = QHBoxLayout()
        summary.addWidget(_summary_card("コマ合計", "自動集計"))
        summary.addWidget(_summary_card("教師負荷", "自動集計"))
        summary.addWidget(_summary_card("エラー", "未検証"))
        content.addLayout(summary)
        issues_group = QGroupBox("確認事項")
        issues_layout = QVBoxLayout(issues_group)
        issues_layout.addWidget(QLabel("Validation接続は次段階です。"))
        issues_layout.addWidget(_editable_table(("種類", "対象", "内容", "移動"), 5))
        content.addWidget(issues_group)
        content.addStretch(1)
        root.setWidget(_wrap_content(content))

    def load_input_data(self, input_data: InputDataModel | None) -> None:
        text = "読込済み" if input_data is not None else "未入力"
        for status in self._statuses:
            status.setText(text)


class MasterPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        root, content = _page_shell(
            self,
            "マスタ管理",
            "毎季ほぼ変わらない情報です。講習作成時は必要な変更だけ行います。",
            "共通設定",
        )
        tabs = QTabWidget()
        campus_tab, self._campus_table = _master_tab(
            "校舎と教室を管理します。教室は校舎に紐づけます。",
            ("校舎", "教室", "表示順", "優先度", "有効"),
        )
        tabs.addTab(campus_tab, "校舎・教室")
        teacher_tab, self._teacher_table = _master_tab(
            "教師の基本情報を管理します。休み希望は講習設定側で入力します。",
            ("教師", "所属校舎", "有効"),
        )
        tabs.addTab(teacher_tab, "教師")
        class_tab, self._class_table = _master_tab(
            "年度中のクラス基本情報を管理します。授業回数と担当は講習設定側です。",
            ("クラス", "校舎", "学部", "学年", "受験区分", "担任", "有効"),
        )
        tabs.addTab(class_tab, "クラス")
        subject_tab, self._subject_table = _master_tab(
            "教科マスタです。授業回数・担当教師の列はここから生成します。",
            ("教科", "授業種別", "有効"),
        )
        tabs.addTab(subject_tab, "教科")
        period_tab, self._period_table = _master_tab(
            "①〜⑥などの時限名と開始・終了時刻を管理します。",
            ("時限", "開始", "終了", "表示順"),
        )
        tabs.addTab(period_tab, "時限")
        content.addWidget(tabs)
        content.addStretch(1)
        root.setWidget(_wrap_content(content))

    def load_input_data(self, input_data: InputDataModel | None) -> None:
        if input_data is None:
            for table in (
                self._campus_table,
                self._teacher_table,
                self._class_table,
                self._subject_table,
                self._period_table,
            ):
                table.setRowCount(0)
            return
        campuses = {campus.campus_id: campus.campus_name for campus in input_data.campuses}
        teachers = {teacher.teacher_id: teacher.teacher_name for teacher in input_data.teachers}
        rooms = sorted(
            input_data.rooms,
            key=lambda room: (campuses.get(room.campus_id, ""), room.output_order),
        )
        _set_table_data(
            self._campus_table,
            ("校舎", "教室", "表示順", "優先度", "有効"),
            tuple(
                (
                    campuses.get(room.campus_id, room.campus_id),
                    room.room_name,
                    room.output_order,
                    room.priority,
                    "✓" if room.enabled else "—",
                )
                for room in rooms
            ),
        )
        _set_table_data(
            self._teacher_table,
            ("教師", "所属校舎", "有効"),
            tuple(
                (
                    teacher.teacher_name,
                    campuses.get(teacher.home_campus_id, teacher.home_campus_id),
                    "✓" if teacher.enabled else "—",
                )
                for teacher in input_data.teachers
            ),
        )
        _set_table_data(
            self._class_table,
            ("クラス", "校舎", "学部", "学年", "受験区分", "担任", "有効"),
            tuple(
                (
                    class_model.class_name,
                    campuses.get(class_model.campus_id, class_model.campus_id),
                    class_model.division,
                    class_model.grade,
                    class_model.exam_category,
                    teachers.get(class_model.homeroom_teacher_id or "", ""),
                    "✓" if class_model.enabled else "—",
                )
                for class_model in input_data.classes
            ),
        )
        _set_table_data(
            self._subject_table,
            ("教科", "授業種別", "有効"),
            tuple(
                (subject.subject_name, subject.lesson_type, "✓" if subject.enabled else "—")
                for subject in input_data.subjects
            ),
        )
        _set_table_data(
            self._period_table,
            ("時限", "開始", "終了", "表示順"),
            tuple(
                (
                    period.period_name,
                    period.start_time.strftime("%H:%M"),
                    period.end_time.strftime("%H:%M"),
                    period.output_order,
                )
                for period in sorted(input_data.periods, key=lambda item: item.output_order)
            ),
        )


def _page_shell(
    owner: QWidget,
    title: str,
    description: str,
    badge: str,
) -> tuple[QScrollArea, QVBoxLayout]:
    root_layout = QVBoxLayout(owner)
    root_layout.setContentsMargins(0, 0, 0, 0)
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    root_layout.addWidget(scroll)

    content = QVBoxLayout()
    content.setContentsMargins(28, 24, 28, 28)
    content.setSpacing(16)
    title_row = QHBoxLayout()
    title_label = QLabel(title)
    title_label.setObjectName("pageTitle")
    title_row.addWidget(title_label)
    badge_label = QLabel(badge)
    badge_label.setObjectName("maintenanceBadge")
    title_row.addWidget(badge_label)
    title_row.addStretch(1)
    content.addLayout(title_row)
    description_label = QLabel(description)
    description_label.setObjectName("pageDescription")
    description_label.setWordWrap(True)
    content.addWidget(description_label)
    return scroll, content


def _wrap_content(layout: QVBoxLayout) -> QWidget:
    widget = QWidget()
    widget.setLayout(layout)
    return widget


def _editable_table(headers: Iterable[str], rows: int) -> QTableWidget:
    header_tuple = tuple(headers)
    table = QTableWidget(rows, len(header_tuple))
    table.setHorizontalHeaderLabels(header_tuple)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    table.verticalHeader().setVisible(False)
    table.setAlternatingRowColors(True)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
    table.setEditTriggers(
        QAbstractItemView.EditTrigger.DoubleClicked
        | QAbstractItemView.EditTrigger.EditKeyPressed
        | QAbstractItemView.EditTrigger.SelectedClicked
    )
    table.setMinimumHeight(max(220, min(390, 82 + max(rows, 5) * 27)))
    return table


def _set_table_data(
    table: QTableWidget,
    headers: Iterable[str],
    rows: Iterable[Iterable[object]],
) -> None:
    header_tuple = tuple(headers)
    row_tuple = tuple(tuple(row) for row in rows)
    table.setColumnCount(len(header_tuple))
    table.setHorizontalHeaderLabels(header_tuple)
    table.setRowCount(len(row_tuple))
    for row_index, row in enumerate(row_tuple):
        for column_index, value in enumerate(row):
            table.setItem(row_index, column_index, QTableWidgetItem(str(value)))
    table.resizeRowsToContents()


def _summary_card_parts(title: str, value: str) -> tuple[QWidget, QLabel]:
    frame = QFrame()
    frame.setObjectName("summaryCard")
    layout = QVBoxLayout(frame)
    label = QLabel(title)
    label.setObjectName("summaryTitle")
    value_label = QLabel(value)
    value_label.setObjectName("summaryValue")
    layout.addWidget(label)
    layout.addWidget(value_label)
    return frame, value_label


def _summary_card(title: str, value: str) -> QWidget:
    frame, _value_label = _summary_card_parts(title, value)
    return frame


def _condition_card(title: str, description: str) -> QWidget:
    frame = QFrame()
    frame.setObjectName("conditionCard")
    layout = QVBoxLayout(frame)
    title_label = QLabel(title)
    title_label.setObjectName("conditionTitle")
    description_label = QLabel(description)
    description_label.setWordWrap(True)
    enabled = QCheckBox("この講習で使用")
    edit = QPushButton("設定を確認")
    layout.addWidget(title_label)
    layout.addWidget(description_label)
    layout.addWidget(enabled)
    layout.addWidget(edit, 0, Qt.AlignmentFlag.AlignLeft)
    return frame


def _master_tab(
    description: str,
    headers: tuple[str, ...],
) -> tuple[QWidget, QTableWidget]:
    widget = QWidget()
    layout = QVBoxLayout(widget)
    description_label = QLabel(description)
    description_label.setWordWrap(True)
    layout.addWidget(description_label)
    actions = QHBoxLayout()
    actions.addWidget(QPushButton("+ 追加"))
    actions.addStretch(1)
    layout.addLayout(actions)
    table = _editable_table(headers, 0)
    layout.addWidget(table)
    return widget, table


def _clear_layout(layout: QGridLayout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.deleteLater()

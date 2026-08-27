from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import Qt, Signal
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
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from school_timetable_solver.model.project_models import ProjectModel, ProjectSource
from school_timetable_solver.ui.editor_navigation import (
    COMMON_NAVIGATION,
    SEASONAL_NAVIGATION,
    EditorNavigationItem,
    EditorSection,
)


class SeasonalEditorWorkspace(QWidget):
    """Prototype editor arranged around the seasonal timetable maintenance workflow."""

    back_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._navigation_buttons: dict[EditorSection, QPushButton] = {}
        self._pages: dict[EditorSection, QWidget] = {}
        self._current_project: ProjectModel | None = None

        self.setStyleSheet(_WORKSPACE_STYLE)
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

    def load_project(self, project: ProjectModel) -> None:
        self._current_project = project
        self._title.setText(project.name)
        self._note.setText(project.note or "備考なし")
        if project.source is ProjectSource.EXCEL_IMPORT:
            self._source.setText("Excelインポート済み")
        else:
            self._source.setText("新規作成")
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
            "毎季の入力順と配置を確認する段階です。ここで変更した値はまだ保存されません。"
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

        guide = QLabel("上から順に設定")
        guide.setObjectName("navigationGuide")
        layout.addWidget(guide)
        layout.addSpacing(6)

        self._button_group = QButtonGroup(self)
        self._button_group.setExclusive(True)

        seasonal_title = QLabel("講習設定")
        seasonal_title.setObjectName("navigationGroupTitle")
        layout.addWidget(seasonal_title)
        for item in SEASONAL_NAVIGATION:
            layout.addWidget(self._create_navigation_button(item))

        layout.addSpacing(18)
        common_title = QLabel("共通設定")
        common_title.setObjectName("navigationGroupTitle")
        layout.addWidget(common_title)
        for item in COMMON_NAVIGATION:
            layout.addWidget(self._create_navigation_button(item))

        layout.addStretch(1)
        note = QLabel("校舎や教室など、毎季ほぼ変わらない情報は下段にまとめます。")
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
            (EditorSection.SCHEDULE, SchedulePage()),
            (EditorSection.LESSON_COUNTS, LessonCountsPage()),
            (EditorSection.TEACHER_ASSIGNMENTS, TeacherAssignmentsPage()),
            (EditorSection.TEACHER_LEAVES, TeacherLeavesPage()),
            (EditorSection.PLACEMENT_CONDITIONS, PlacementConditionsPage()),
            (EditorSection.REVIEW, ReviewPage()),
            (EditorSection.MASTER, MasterPage()),
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
        start = QDateEdit()
        start.setCalendarPopup(True)
        start.setDisplayFormat("yyyy/MM/dd")
        period_layout.addWidget(start)
        period_layout.addWidget(QLabel("終了日"))
        end = QDateEdit()
        end.setCalendarPopup(True)
        end.setDisplayFormat("yyyy/MM/dd")
        period_layout.addWidget(end)
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
        table = _editable_table(
            ("日付", "曜", "①", "②", "③", "④", "⑤", "⑥", "備考"),
            9,
        )
        calendar_layout.addWidget(table)
        content.addWidget(calendar_group)

        hint = QLabel(
            "学校の終業式・始業式、休館、模試などの特殊日は、日付行の時限ON/OFFと備考で扱う想定です。"
        )
        hint.setObjectName("pageHint")
        hint.setWordWrap(True)
        content.addWidget(hint)
        content.addStretch(1)
        root.setWidget(_wrap_content(content))


class LessonCountsPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        root, content = _page_shell(
            self,
            "授業回数",
            "今期開講するクラスと、クラス・教科ごとの必要コマ数をまとめて設定します。",
            "毎季更新",
        )

        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("校舎"))
        campus = QComboBox()
        campus.addItem("すべて")
        toolbar.addWidget(campus)
        toolbar.addWidget(QPushButton("+ クラスを追加"))
        toolbar.addStretch(1)
        content.addLayout(toolbar)

        group = QGroupBox("クラス別 授業回数")
        group_layout = QVBoxLayout(group)
        table = _editable_table(
            ("クラス", "国語", "算数・数学", "社会", "理科", "英語", "計"),
            12,
        )
        group_layout.addWidget(table)
        content.addWidget(group)

        summary = QHBoxLayout()
        summary.addWidget(_summary_card("必要コマ合計", "自動集計"))
        summary.addWidget(_summary_card("昨季との差", "将来自動集計"))
        summary.addWidget(_summary_card("校舎別合計", "自動集計"))
        content.addLayout(summary)

        hint = QLabel(
            "教科列は本実装では教科マスタから生成します。現在の紙の授業回数表と同じ横持ちを評価するための表示です。"
        )
        hint.setObjectName("pageHint")
        hint.setWordWrap(True)
        content.addWidget(hint)
        content.addStretch(1)
        root.setWidget(_wrap_content(content))


class TeacherAssignmentsPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        root, content = _page_shell(
            self,
            "担当教師",
            "クラスを行、担任・教科を列にして、今使っている担当者表に近い形で割り当てます。",
            "毎季確認・変更",
        )

        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("校舎"))
        campus = QComboBox()
        campus.addItem("すべて")
        toolbar.addWidget(campus)
        toolbar.addWidget(QPushButton("前回の担当を引き継ぐ"))
        toolbar.addStretch(1)
        content.addLayout(toolbar)

        assignment_group = QGroupBox("クラス別 担当者")
        assignment_layout = QVBoxLayout(assignment_group)
        table = _editable_table(
            ("クラス", "担任", "国語", "算数・数学", "社会", "理科", "英語"),
            12,
        )
        assignment_layout.addWidget(table)
        content.addWidget(assignment_group)

        load_group = QGroupBox("教師別 予定コマ数 - 自動集計")
        load_layout = QGridLayout(load_group)
        for index in range(6):
            load_layout.addWidget(_summary_card("教師", "0コマ"), index // 3, index % 3)
        content.addWidget(load_group)

        hint = QLabel(
            "担当を変更すると教師別予定コマ数を即時再集計し、負荷の偏りをこの画面内で確認できる形を想定しています。"
        )
        hint.setObjectName("pageHint")
        hint.setWordWrap(True)
        content.addWidget(hint)
        content.addStretch(1)
        root.setWidget(_wrap_content(content))


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
        note = QLabel("日程画面で設定した開講日を横方向に自動表示する想定です。")
        note.setObjectName("pageHint")
        matrix_layout.addWidget(note)
        table = _editable_table(
            ("教師", "日程1", "日程2", "日程3", "日程4", "日程5", "日程6"),
            10,
        )
        matrix_layout.addWidget(table)
        content.addWidget(matrix_group)

        quota_group = QGroupBox("期間内の休日日数")
        quota_layout = QVBoxLayout(quota_group)
        quota_layout.addWidget(
            _editable_table(("教師", "対象期間", "必要休日日数", "希望休日日数"), 5)
        )
        content.addWidget(quota_group)
        content.addStretch(1)
        root.setWidget(_wrap_content(content))


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
            common_layout.addWidget(
                _condition_card(title, description),
                index // 2,
                index % 2,
            )
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
        for label in ("日程", "授業回数", "担当教師", "教師の休み", "配置条件"):
            row = QHBoxLayout()
            row.addWidget(QLabel(label))
            row.addStretch(1)
            status = QLabel("未検証")
            status.setObjectName("reviewStatus")
            row.addWidget(status)
            status_layout.addLayout(row)
        content.addWidget(status_group)

        summary = QHBoxLayout()
        summary.addWidget(_summary_card("必要コマ", "自動集計"))
        summary.addWidget(_summary_card("教師負荷", "自動集計"))
        summary.addWidget(_summary_card("エラー", "未検証"))
        content.addLayout(summary)

        issues_group = QGroupBox("確認事項")
        issues_layout = QVBoxLayout(issues_group)
        issues_layout.addWidget(
            QLabel("Validation接続後は、エラーから該当する入力画面へ直接移動できるようにします。")
        )
        issues_layout.addWidget(_editable_table(("種類", "対象", "内容", "移動"), 5))
        content.addWidget(issues_group)
        content.addStretch(1)
        root.setWidget(_wrap_content(content))


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
        tabs.addTab(
            _master_tab(
                "校舎と教室を管理します。教室は校舎に紐づけます。",
                ("校舎", "教室", "表示順", "優先度", "有効"),
            ),
            "校舎・教室",
        )
        tabs.addTab(
            _master_tab(
                "教師の基本情報を管理します。休み希望は講習設定側で入力します。",
                ("教師", "所属校舎", "有効"),
            ),
            "教師",
        )
        tabs.addTab(
            _master_tab(
                "年度中のクラス基本情報を管理します。授業回数と担当は講習設定側です。",
                ("クラス", "校舎", "学部", "学年", "受験区分", "担任", "有効"),
            ),
            "クラス",
        )
        tabs.addTab(
            _master_tab(
                "教科マスタです。授業回数・担当教師の列はここから生成します。",
                ("教科", "授業種別", "有効"),
            ),
            "教科",
        )
        tabs.addTab(
            _master_tab(
                "①〜⑥などの時限名と開始・終了時刻を管理します。",
                ("時限", "開始", "終了", "表示順"),
            ),
            "時限",
        )
        content.addWidget(tabs)
        content.addStretch(1)
        root.setWidget(_wrap_content(content))


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
    table.setMinimumHeight(min(390, 82 + rows * 27))
    return table


def _summary_card(title: str, value: str) -> QWidget:
    frame = QFrame()
    frame.setObjectName("summaryCard")
    layout = QVBoxLayout(frame)
    label = QLabel(title)
    label.setObjectName("summaryTitle")
    value_label = QLabel(value)
    value_label.setObjectName("summaryValue")
    layout.addWidget(label)
    layout.addWidget(value_label)
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


def _master_tab(description: str, headers: tuple[str, ...]) -> QWidget:
    widget = QWidget()
    layout = QVBoxLayout(widget)
    description_label = QLabel(description)
    description_label.setWordWrap(True)
    layout.addWidget(description_label)
    actions = QHBoxLayout()
    actions.addWidget(QPushButton("+ 追加"))
    actions.addStretch(1)
    layout.addLayout(actions)
    layout.addWidget(_editable_table(headers, 9))
    return widget


_WORKSPACE_STYLE = """
QFrame#editorHeader {
    background: #ffffff;
    border-bottom: 1px solid #d9dde5;
}
QLabel#projectTitle {
    font-size: 20px;
    font-weight: 600;
}
QLabel#projectNote, QLabel#navigationNote, QLabel#pageDescription, QLabel#pageHint {
    color: #667085;
}
QLabel#sourceBadge, QLabel#maintenanceBadge, QLabel#reviewStatus {
    background: #eef2f7;
    border-radius: 5px;
    padding: 4px 8px;
    color: #475467;
}
QFrame#prototypeNotice {
    background: #fff8e6;
    border-bottom: 1px solid #ead9a2;
}
QLabel#prototypeTitle {
    font-weight: 600;
}
QFrame#navigationPanel {
    background: #f7f8fa;
    border-right: 1px solid #d9dde5;
}
QLabel#navigationGuide {
    color: #667085;
    font-size: 12px;
}
QLabel#navigationGroupTitle {
    font-weight: 600;
    color: #344054;
    padding: 4px 6px;
}
QPushButton[navigation="true"] {
    text-align: left;
    border: 0;
    border-radius: 6px;
    padding: 9px 10px;
    background: transparent;
}
QPushButton[navigation="true"]:hover {
    background: #eaecf0;
}
QPushButton[navigation="true"]:checked {
    background: #e5edff;
    font-weight: 600;
}
QLabel#pageTitle {
    font-size: 24px;
    font-weight: 600;
}
QGroupBox {
    font-weight: 600;
    border: 1px solid #d9dde5;
    border-radius: 7px;
    margin-top: 12px;
    padding-top: 12px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 5px;
}
QFrame#summaryCard, QFrame#conditionCard {
    border: 1px solid #d9dde5;
    border-radius: 7px;
    background: #ffffff;
}
QLabel#summaryTitle {
    color: #667085;
}
QLabel#summaryValue {
    font-size: 18px;
    font-weight: 600;
}
QLabel#conditionTitle {
    font-weight: 600;
}
QTableWidget {
    border: 1px solid #d9dde5;
    gridline-color: #eaecf0;
}
"""

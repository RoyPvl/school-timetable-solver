from __future__ import annotations

from collections.abc import Callable, Iterable

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

_DIVISION_CHOICES = ("小学", "中学", "高校", "その他")
_EXAM_CATEGORY_CHOICES = ("受験", "非受験", "特別", "その他")
_ENABLED_CHOICES = ("✓", "—")

_DIVISION_LABELS = {
    "小学": "小学",
    "小学校": "小学",
    "elementary": "小学",
    "elementary_school": "小学",
    "primary": "小学",
    "primary_school": "小学",
    "elem": "小学",
    "中学": "中学",
    "中学校": "中学",
    "middle": "中学",
    "middle_school": "中学",
    "junior_high": "中学",
    "junior_high_school": "中学",
    "高校": "高校",
    "高等学校": "高校",
    "high": "高校",
    "high_school": "高校",
    "senior_high": "高校",
    "senior_high_school": "高校",
    "その他": "その他",
    "other": "その他",
    "others": "その他",
}

_EXAM_CATEGORY_LABELS = {
    "受験": "受験",
    "exam": "受験",
    "examination": "受験",
    "entrance_exam": "受験",
    "受験学年": "受験",
    "非受験": "非受験",
    "non_exam": "非受験",
    "nonexam": "非受験",
    "non_examinee": "非受験",
    "regular": "非受験",
    "特別": "特別",
    "special": "特別",
    "その他": "その他",
    "なし": "その他",
    "none": "その他",
    "null": "その他",
    "other": "その他",
    "others": "その他",
    "": "その他",
}

_ENABLED_LABELS = {
    "✓": "✓",
    "true": "✓",
    "1": "✓",
    "yes": "✓",
    "on": "✓",
    "enabled": "✓",
    "有効": "✓",
    "○": "✓",
    "—": "—",
    "false": "—",
    "0": "—",
    "no": "—",
    "off": "—",
    "disabled": "—",
    "無効": "—",
    "": "—",
}


def apply_editor_presentation(root: QWidget) -> None:
    """Apply the current human-in-the-loop presentation rules to the editor."""
    if root.property("presentationApplying"):
        return
    root.setProperty("presentationApplying", True)
    try:
        for table in root.findChildren(QTableWidget):
            _polish_table(table)
        _ensure_campus_master(root)
        _apply_dependency_choices(root)
        _compact_teacher_load_cards(root)
        _install_dynamic_refresh_hooks(root)
    finally:
        root.setProperty("presentationApplying", False)


def _polish_table(table: QTableWidget) -> None:
    previously_blocked = table.blockSignals(True)
    try:
        _rename_header(table, "曜", "曜日")
        _remove_header_column(table, "表示順")

        # Presentation-only row index. It is not part of table business data and must
        # never be serialized into ProjectDocument/InputDataModel or sent to Solver.
        vertical_header = table.verticalHeader()
        vertical_header.setVisible(True)
        vertical_header.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        vertical_header.setFixedWidth(42)
        table.setVerticalHeaderLabels(
            tuple(str(index + 1) for index in range(table.rowCount()))
        )

        for row in range(table.rowCount()):
            for column in range(table.columnCount()):
                item = table.item(row, column)
                if item is not None:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
    finally:
        table.blockSignals(previously_blocked)


def _rename_header(table: QTableWidget, before: str, after: str) -> None:
    for column in range(table.columnCount()):
        item = table.horizontalHeaderItem(column)
        if item is not None and item.text() == before:
            item.setText(after)


def _remove_header_column(table: QTableWidget, header: str) -> None:
    for column in reversed(range(table.columnCount())):
        item = table.horizontalHeaderItem(column)
        if item is not None and item.text() == header:
            table.removeColumn(column)


def _ensure_campus_master(root: QWidget) -> None:
    if root.property("campusMasterCreated"):
        return

    tables = root.findChildren(QTableWidget)
    room_table = _find_table(tables, ("校舎", "教室", "優先度", "有効"))
    if room_table is None:
        return

    tab = room_table.parentWidget()
    if tab is None or not isinstance(tab.layout(), QVBoxLayout):
        return

    campus_names = _column_values(room_table, "校舎")

    group = QGroupBox("校舎")
    group.setObjectName("campusMasterGroup")
    group_layout = QVBoxLayout(group)

    actions = QHBoxLayout()
    add_button = QPushButton("+ 校舎を追加")
    actions.addWidget(add_button)
    actions.addStretch(1)
    group_layout.addLayout(actions)

    campus_table = QTableWidget(len(campus_names), 1)
    campus_table.setObjectName("campusMasterTable")
    campus_table.setHorizontalHeaderLabels(("校舎名",))
    campus_table.horizontalHeader().setStretchLastSection(True)
    for row, campus_name in enumerate(campus_names):
        campus_table.setItem(row, 0, QTableWidgetItem(campus_name))
    campus_table.setMinimumHeight(max(150, 82 + max(len(campus_names), 2) * 27))
    group_layout.addWidget(campus_table)

    tab_layout = tab.layout()
    assert isinstance(tab_layout, QVBoxLayout)
    tab_layout.insertWidget(1, group)

    add_button.clicked.connect(lambda _checked=False, table=campus_table: _append_row(table))
    root.setProperty("campusMasterCreated", True)
    _polish_table(campus_table)


def _append_row(table: QTableWidget) -> None:
    row = table.rowCount()
    table.insertRow(row)
    table.setItem(row, 0, QTableWidgetItem(""))
    _polish_table(table)
    table.setCurrentCell(row, 0)
    table.editItem(table.item(row, 0))


def _apply_dependency_choices(root: QWidget) -> None:
    tables = root.findChildren(QTableWidget)
    campus_master = _find_table(tables, ("校舎名",))
    room_table = _find_table(tables, ("校舎", "教室", "優先度", "有効"))
    teacher_table = _find_table(tables, ("教師", "所属校舎"))
    class_table = _find_table(tables, ("クラス", "校舎", "学部", "担任"))
    subject_table = _find_table(tables, ("教科", "授業種別"))

    # Campus names are defined only in the campus master. Every campus reference in
    # the editor must be a strict selection from this source.
    campus_choices = _column_values(campus_master, "校舎名") if campus_master else ()
    teacher_choices = _column_values(teacher_table, "教師") if teacher_table else ()

    if room_table is not None:
        _configure_choice_column(room_table, "校舎", campus_choices)

    if teacher_table is not None:
        _configure_choice_column(teacher_table, "所属校舎", campus_choices)

    if class_table is not None:
        _configure_choice_column(class_table, "校舎", campus_choices)
        _configure_choice_column(class_table, "担任", teacher_choices, allow_blank=True)
        _configure_choice_column(
            class_table,
            "学部",
            _DIVISION_CHOICES,
            normalize_current=_normalize_division,
        )
        _configure_choice_column(
            class_table,
            "受験区分",
            _EXAM_CATEGORY_CHOICES,
            normalize_current=_normalize_exam_category,
        )

    if subject_table is not None:
        _configure_choice_column(
            subject_table,
            "授業種別",
            _column_values(subject_table, "授業種別"),
            editable=True,
        )

    for table in tables:
        headers = _table_headers(table)
        if "有効" in headers:
            _configure_choice_column(
                table,
                "有効",
                _ENABLED_CHOICES,
                normalize_current=_normalize_enabled,
            )
        if (
            "クラス" in headers
            and "担任" in headers
            and "校舎" not in headers
            and len(headers) > 2
        ):
            # Teacher assignment table: homeroom and every subject column reference
            # the teacher master. Blank is allowed while editing incomplete data.
            for header in headers[1:]:
                _configure_choice_column(
                    table,
                    header,
                    teacher_choices,
                    allow_blank=True,
                )
        elif (
            "教師" in headers
            and "対象期間" in headers
            and "必要休日日数" in headers
        ):
            _configure_choice_column(table, "教師", teacher_choices)


def _find_table(
    tables: Iterable[QTableWidget],
    required_headers: tuple[str, ...],
) -> QTableWidget | None:
    required = set(required_headers)
    for table in tables:
        if required.issubset(_table_headers(table)):
            return table
    return None


def _table_headers(table: QTableWidget) -> tuple[str, ...]:
    return tuple(
        item.text() if item is not None else ""
        for item in (
            table.horizontalHeaderItem(column) for column in range(table.columnCount())
        )
    )


def _column_index(table: QTableWidget, header: str) -> int | None:
    for column, current in enumerate(_table_headers(table)):
        if current == header:
            return column
    return None


def _column_values(table: QTableWidget, header: str) -> tuple[str, ...]:
    column = _column_index(table, header)
    if column is None:
        return ()
    values: list[str] = []
    for row in range(table.rowCount()):
        value = _cell_text(table, row, column).strip()
        if value and value not in values:
            values.append(value)
    return tuple(values)


def _cell_text(table: QTableWidget, row: int, column: int) -> str:
    widget = table.cellWidget(row, column)
    if isinstance(widget, QComboBox):
        return widget.currentText()
    item = table.item(row, column)
    return item.text() if item is not None else ""


def _configure_choice_column(
    table: QTableWidget,
    header: str,
    choices: tuple[str, ...],
    *,
    editable: bool = False,
    allow_blank: bool = False,
    normalize_current: Callable[[str], str] | None = None,
) -> None:
    column = _column_index(table, header)
    if column is None:
        return
    for row in range(table.rowCount()):
        _set_choice_cell(
            table,
            row,
            column,
            choices,
            editable=editable,
            allow_blank=allow_blank,
            normalize_current=normalize_current,
        )


def _set_choice_cell(
    table: QTableWidget,
    row: int,
    column: int,
    choices: tuple[str, ...],
    *,
    editable: bool,
    allow_blank: bool,
    normalize_current: Callable[[str], str] | None,
) -> None:
    current = _cell_text(table, row, column)
    if normalize_current is not None:
        current = normalize_current(current)

    existing = table.cellWidget(row, column)
    is_new = not isinstance(existing, QComboBox)
    combo = QComboBox(table) if is_new else existing
    assert isinstance(combo, QComboBox)

    values = list(choices)
    if allow_blank and "" not in values:
        values.insert(0, "")
    if current and current not in values:
        values.append(current)

    desired_values = tuple(values)
    current_values = tuple(combo.itemText(index) for index in range(combo.count()))
    needs_item_refresh = current_values != desired_values
    needs_mode_refresh = combo.isEditable() != editable

    if needs_item_refresh or needs_mode_refresh:
        combo.blockSignals(True)
        combo.setEditable(editable)
        if editable:
            line_edit = combo.lineEdit()
            if line_edit is not None:
                line_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if needs_item_refresh:
            combo.clear()
            combo.addItems(values)
        combo.setCurrentText(current)
        combo.blockSignals(False)
    elif combo.currentText() != current:
        combo.blockSignals(True)
        combo.setCurrentText(current)
        combo.blockSignals(False)

    combo.setProperty("dependencyChoice", True)
    if is_new:
        table.setCellWidget(row, column, combo)


def _normalize_division(value: str) -> str:
    return _DIVISION_LABELS.get(_normalized_token(value), "その他")


def _normalize_exam_category(value: str) -> str:
    return _EXAM_CATEGORY_LABELS.get(_normalized_token(value), "その他")


def _normalize_enabled(value: str) -> str:
    return _ENABLED_LABELS.get(_normalized_token(value), "—")


def _normalized_token(value: str) -> str:
    return value.strip().casefold().replace("-", "_").replace(" ", "_")


def _compact_teacher_load_cards(root: QWidget) -> None:
    for group in root.findChildren(QGroupBox):
        if group.title() != "教師別 予定コマ数 - 自動集計":
            continue

        # Keep the area compact without clipping rows when many teachers exist.
        group.setMinimumHeight(0)
        group.setMaximumHeight(16777215)
        layout = group.layout()
        if isinstance(layout, QGridLayout):
            layout.setContentsMargins(8, 8, 8, 8)
            layout.setHorizontalSpacing(6)
            layout.setVerticalSpacing(6)

        for card in group.findChildren(QFrame, "summaryCard"):
            card.setMinimumHeight(54)
            card.setMaximumHeight(60)
            card_layout = card.layout()
            if card_layout is not None:
                card_layout.setContentsMargins(8, 5, 8, 5)
                card_layout.setSpacing(1)
            for label in card.findChildren(QLabel):
                if label.objectName() == "summaryTitle":
                    label.setStyleSheet("font-size: 14px;")
                elif label.objectName() == "summaryValue":
                    label.setStyleSheet("font-size: 14px; font-weight: 600;")


def _install_dynamic_refresh_hooks(root: QWidget) -> None:
    tables = root.findChildren(QTableWidget)
    source_tables = (
        _find_table(tables, ("校舎名",)),
        _find_table(tables, ("教師", "所属校舎")),
    )

    # Only source masters trigger dependency regeneration. Dependent QComboBoxes do
    # not refresh the whole editor when selected; rebuilding them during popup
    # interaction caused dropdowns to close or become unresponsive on later rows.
    for table in source_tables:
        if table is None or table.property("dependencySourceRefreshHooked"):
            continue
        table.setProperty("dependencySourceRefreshHooked", True)
        table.cellChanged.connect(
            lambda _row, _column, editor=root: _schedule_refresh(editor)
        )


def _schedule_refresh(root: QWidget) -> None:
    if root.property("presentationApplying"):
        return
    QTimer.singleShot(0, lambda: apply_editor_presentation(root))
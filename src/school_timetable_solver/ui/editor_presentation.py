from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QLabel,
    QTableWidget,
    QWidget,
)


def apply_editor_presentation(root: QWidget) -> None:
    """Apply the current human-in-the-loop presentation rules to the editor."""
    for table in root.findChildren(QTableWidget):
        _polish_table(table)
    _compact_teacher_load_cards(root)
    _install_dynamic_refresh_hooks(root)


def _polish_table(table: QTableWidget) -> None:
    _rename_header(table, "曜", "曜日")
    _remove_header_column(table, "表示順")

    # Presentation-only row index. It is not part of table business data and must
    # never be serialized into ProjectDocument/InputDataModel or sent to Solver.
    vertical_header = table.verticalHeader()
    vertical_header.setVisible(True)
    vertical_header.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
    vertical_header.setFixedWidth(42)
    table.setVerticalHeaderLabels(tuple(str(index + 1) for index in range(table.rowCount())))

    for row in range(table.rowCount()):
        for column in range(table.columnCount()):
            item = table.item(row, column)
            if item is not None:
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)


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
    for combo in root.findChildren(QComboBox):
        if combo.property("presentationRefreshHooked"):
            continue
        combo.setProperty("presentationRefreshHooked", True)
        combo.currentIndexChanged.connect(
            lambda _index, editor=root: QTimer.singleShot(
                0, lambda: apply_editor_presentation(editor)
            )
        )

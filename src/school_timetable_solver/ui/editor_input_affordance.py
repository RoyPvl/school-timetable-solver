from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtWidgets import QComboBox, QLabel, QLineEdit, QTableWidget, QWidget

_TABLE_ROW_HEIGHT = 38


class _ComboChevronController(QObject):
    """Keep a visible chevron at the right edge of combo boxes."""

    def __init__(self, combo: QComboBox) -> None:
        super().__init__(combo)
        self._combo = combo
        self._chevron = QLabel("⌄", combo)
        self._chevron.setObjectName("comboChevron")
        self._chevron.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._chevron.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._chevron.setFixedWidth(28)
        combo.installEventFilter(self)
        self._reposition()
        self._chevron.show()
        self._chevron.raise_()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self._combo and event.type() in {
            QEvent.Type.Resize,
            QEvent.Type.Show,
            QEvent.Type.StyleChange,
        }:
            QTimer.singleShot(0, self._reposition)
        return False

    def _reposition(self) -> None:
        height = self._combo.height()
        self._chevron.setGeometry(
            max(0, self._combo.width() - self._chevron.width()),
            0,
            self._chevron.width(),
            height,
        )
        self._chevron.raise_()


def apply_input_affordances(root: QWidget) -> None:
    """Make editable text and selection controls visually explicit."""
    for table in root.findChildren(QTableWidget):
        _normalize_table_row_height(table)
        _show_text_inputs(table)

    for combo in root.findChildren(QComboBox):
        _show_selection_affordance(combo)


def _normalize_table_row_height(table: QTableWidget) -> None:
    header = table.verticalHeader()
    header.setMinimumSectionSize(_TABLE_ROW_HEIGHT)
    header.setDefaultSectionSize(_TABLE_ROW_HEIGHT)
    for row in range(table.rowCount()):
        table.setRowHeight(row, _TABLE_ROW_HEIGHT)


def _show_text_inputs(table: QTableWidget) -> None:
    for row in range(table.rowCount()):
        for column in range(table.columnCount()):
            if table.cellWidget(row, column) is not None:
                continue
            item = table.item(row, column)
            if item is None or not item.flags() & Qt.ItemFlag.ItemIsEditable:
                continue

            editor = QLineEdit(item.text(), table)
            editor.setObjectName("tableTextInput")
            editor.setAlignment(Qt.AlignmentFlag.AlignCenter)
            editor.textChanged.connect(item.setText)
            table.setCellWidget(row, column, editor)


def _show_selection_affordance(combo: QComboBox) -> None:
    combo.setProperty("selectionField", True)
    if combo.property("chevronControllerInstalled"):
        return
    controller = _ComboChevronController(combo)
    combo.setProperty("chevronController", controller)
    combo.setProperty("chevronControllerInstalled", True)

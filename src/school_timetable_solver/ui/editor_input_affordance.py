from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtWidgets import QComboBox, QLabel, QLineEdit, QTableWidget, QWidget

_TABLE_ROW_HEIGHT = 38
_MASTER_ENABLED_TABLES = (
    frozenset(("校舎", "教室", "優先度", "有効")),
    frozenset(("教師", "所属校舎", "有効")),
    frozenset(("クラス", "校舎", "学部", "学年", "受験区分", "担任", "有効")),
    frozenset(("教科", "授業種別", "有効")),
)
_DISABLED_LABELS = frozenset(("—", "-", "false", "0", "no", "off", "disabled", "無効"))


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


def prepare_master_active_rows(root: QWidget) -> None:
    """Discard disabled imported master rows before dependency choices are built."""
    for table in root.findChildren(QTableWidget):
        if not _is_master_enabled_table(table):
            continue
        enabled_column = _column_index(table, "有効")
        if enabled_column is None:
            continue
        for row in reversed(range(table.rowCount())):
            if _is_disabled(_cell_text(table, row, enabled_column)):
                table.removeRow(row)


def apply_input_affordances(root: QWidget) -> None:
    """Make editable text and selection controls visually explicit."""
    for table in root.findChildren(QTableWidget):
        _remove_master_enabled_column(table)
        _normalize_table_row_height(table)
        _show_text_inputs(table)

    for combo in root.findChildren(QComboBox):
        _show_selection_affordance(combo)


def _remove_master_enabled_column(table: QTableWidget) -> None:
    if not _is_master_enabled_table(table):
        return
    enabled_column = _column_index(table, "有効")
    if enabled_column is not None:
        table.removeColumn(enabled_column)


def _is_master_enabled_table(table: QTableWidget) -> bool:
    headers = frozenset(_table_headers(table))
    return any(required.issubset(headers) for required in _MASTER_ENABLED_TABLES)


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


def _cell_text(table: QTableWidget, row: int, column: int) -> str:
    widget = table.cellWidget(row, column)
    if isinstance(widget, QComboBox):
        return widget.currentText()
    item = table.item(row, column)
    return item.text() if item is not None else ""


def _is_disabled(value: str) -> bool:
    normalized = value.strip().casefold()
    return normalized in _DISABLED_LABELS or not normalized


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

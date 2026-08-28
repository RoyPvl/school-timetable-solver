from __future__ import annotations

from PySide6.QtCore import QDate, QEvent, QModelIndex, QPointF, QLocale, QObject, Qt, QTimer
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QHeaderView,
    QLabel,
    QLineEdit,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

_TABLE_ROW_HEIGHT = 38
_DATE_DISPLAY_FORMAT = "yyyy/MM/dd (ddd)"
_JAPANESE_LOCALE = QLocale(QLocale.Language.Japanese, QLocale.Country.Japan)
_SCHEDULE_DATE_WIDTH = 190
_SCHEDULE_PERIOD_WIDTH = 58
_SCHEDULE_PERIOD_CHOICES = ("✓", "—")
_MASTER_ENABLED_TABLES = (
    frozenset(("校舎", "教室", "優先度", "有効")),
    frozenset(("教師", "所属校舎", "有効")),
    frozenset(("クラス", "校舎", "学部", "学年", "受験区分", "担任", "有効")),
    frozenset(("教科", "授業種別", "有効")),
)
_DISABLED_LABELS = frozenset(("—", "-", "false", "0", "no", "off", "disabled", "無効"))
_ENABLED_LABELS = frozenset(("✓", "true", "1", "yes", "on", "enabled", "有効", "○"))


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


class _CalendarIndicatorController(QObject):
    """Keep a calendar marker visible over the QDateEdit popup area."""

    def __init__(self, date_edit: QDateEdit) -> None:
        super().__init__(date_edit)
        self._date_edit = date_edit
        self._indicator = QLabel("📅", date_edit)
        self._indicator.setObjectName("calendarIndicator")
        self._indicator.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._indicator.setToolTip("カレンダーから選択")
        self._indicator.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._indicator.setFixedWidth(24)
        date_edit.installEventFilter(self)
        self._reposition()
        self._indicator.show()
        self._indicator.raise_()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self._date_edit and event.type() in {
            QEvent.Type.Resize,
            QEvent.Type.Show,
            QEvent.Type.StyleChange,
        }:
            QTimer.singleShot(0, self._reposition)
        return False

    def _reposition(self) -> None:
        height = self._date_edit.height()
        self._indicator.setGeometry(
            max(0, self._date_edit.width() - self._indicator.width()),
            0,
            self._indicator.width(),
            height,
        )
        self._indicator.raise_()


class _ChoiceSelectionDelegate(QStyledItemDelegate):
    """Render the current choice with a neutral circle instead of a checkmark."""

    def __init__(self, combo: QComboBox) -> None:
        super().__init__(combo.view())
        self._combo = combo

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> None:
        painter.save()
        highlighted = bool(
            option.state
            & (QStyle.StateFlag.State_Selected | QStyle.StateFlag.State_MouseOver)
        )
        background = (
            option.palette.highlight().color()
            if highlighted
            else option.palette.base().color()
        )
        text_color = (
            option.palette.highlightedText().color()
            if highlighted
            else option.palette.text().color()
        )
        painter.fillRect(option.rect, background)
        painter.setPen(text_color)
        painter.drawText(
            option.rect.adjusted(26, 0, -8, 0),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            str(index.data(Qt.ItemDataRole.DisplayRole) or ""),
        )

        if index.row() == self._combo.currentIndex():
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setPen(text_color)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            center = QPointF(option.rect.left() + 13, option.rect.center().y())
            painter.drawEllipse(center, 4.0, 4.0)
        painter.restore()


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
        _remove_weekday_column(table)
        _normalize_table_row_height(table)
        _show_schedule_period_inputs(table)
        _show_date_inputs(table)
        _show_text_inputs(table)
        _configure_schedule_column_widths(table)

    for combo in root.findChildren(QComboBox):
        _show_selection_affordance(combo)
    for date_edit in root.findChildren(QDateEdit):
        _show_calendar_affordance(date_edit)


def _remove_master_enabled_column(table: QTableWidget) -> None:
    if not _is_master_enabled_table(table):
        return
    enabled_column = _column_index(table, "有効")
    if enabled_column is not None:
        table.removeColumn(enabled_column)


def _remove_weekday_column(table: QTableWidget) -> None:
    for header in ("曜", "曜日"):
        weekday_column = _column_index(table, header)
        if weekday_column is not None:
            table.removeColumn(weekday_column)


def _is_master_enabled_table(table: QTableWidget) -> bool:
    headers = frozenset(_table_headers(table))
    return any(required.issubset(headers) for required in _MASTER_ENABLED_TABLES)


def _is_schedule_table(table: QTableWidget) -> bool:
    headers = set(_table_headers(table))
    return "日付" in headers and "備考" in headers


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
    if isinstance(widget, QDateEdit):
        return widget.date().toString("yyyy/MM/dd")
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


def _show_schedule_period_inputs(table: QTableWidget) -> None:
    if not _is_schedule_table(table):
        return

    period_columns = tuple(
        column
        for column, header in enumerate(_table_headers(table))
        if header not in {"日付", "備考"}
    )
    for row in range(table.rowCount()):
        for column in period_columns:
            existing = table.cellWidget(row, column)
            if isinstance(existing, QComboBox):
                continue

            item = table.item(row, column)
            if item is None:
                item = QTableWidgetItem("—")
                table.setItem(row, column, item)
            current = _normalize_period_choice(item.text())
            item.setText(current)

            combo = QComboBox(table)
            combo.setObjectName("schedulePeriodChoice")
            combo.addItems(_SCHEDULE_PERIOD_CHOICES)
            combo.setCurrentText(current)
            combo.currentTextChanged.connect(item.setText)
            combo.view().setItemDelegate(_ChoiceSelectionDelegate(combo))
            table.setCellWidget(row, column, combo)


def _normalize_period_choice(value: str) -> str:
    normalized = value.strip().casefold()
    return "✓" if normalized in _ENABLED_LABELS else "—"


def _show_date_inputs(table: QTableWidget) -> None:
    date_column = _column_index(table, "日付")
    if date_column is None:
        return

    for row in range(table.rowCount()):
        existing = table.cellWidget(row, date_column)
        if isinstance(existing, QDateEdit):
            continue

        item = table.item(row, date_column)
        if item is None:
            item = QTableWidgetItem("")
            table.setItem(row, date_column, item)
        parsed = _parse_date(item.text())
        if not parsed.isValid():
            continue

        editor = QDateEdit(table)
        editor.setObjectName("tableDateInput")
        editor.setCalendarPopup(True)
        editor.setLocale(_JAPANESE_LOCALE)
        editor.setDisplayFormat(_DATE_DISPLAY_FORMAT)
        editor.setDate(parsed)
        line_edit = editor.lineEdit()
        if line_edit is not None:
            line_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        editor.dateChanged.connect(
            lambda selected, cell=item: cell.setText(selected.toString("yyyy/MM/dd"))
        )
        table.setCellWidget(row, date_column, editor)


def _parse_date(value: str) -> QDate:
    text = value.strip()
    for display_format in ("yyyy/MM/dd", "yyyy-M-d", "yyyy-MM-dd", "M/d"):
        parsed = QDate.fromString(text, display_format)
        if parsed.isValid():
            return parsed
    return QDate()


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


def _configure_schedule_column_widths(table: QTableWidget) -> None:
    if not _is_schedule_table(table):
        return

    header = table.horizontalHeader()
    header.setStretchLastSection(False)
    for column, label in enumerate(_table_headers(table)):
        if label == "日付":
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
            table.setColumnWidth(column, _SCHEDULE_DATE_WIDTH)
        elif label == "備考":
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Stretch)
        else:
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
            table.setColumnWidth(column, _SCHEDULE_PERIOD_WIDTH)


def _show_selection_affordance(combo: QComboBox) -> None:
    combo.setProperty("selectionField", True)
    if combo.property("chevronControllerInstalled"):
        return
    controller = _ComboChevronController(combo)
    combo.setProperty("chevronController", controller)
    combo.setProperty("chevronControllerInstalled", True)


def _show_calendar_affordance(date_edit: QDateEdit) -> None:
    date_edit.setCalendarPopup(True)
    date_edit.setLocale(_JAPANESE_LOCALE)
    date_edit.setDisplayFormat(_DATE_DISPLAY_FORMAT)
    date_edit.setMinimumWidth(150)
    date_edit.setProperty("calendarField", True)
    if date_edit.property("calendarIndicatorControllerInstalled"):
        return
    controller = _CalendarIndicatorController(date_edit)
    date_edit.setProperty("calendarIndicatorController", controller)
    date_edit.setProperty("calendarIndicatorControllerInstalled", True)

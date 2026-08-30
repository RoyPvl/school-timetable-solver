from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import QDate, QEvent, QLocale, QModelIndex, QObject, QPointF, Qt, QTimer
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
_SCHEDULE_PERIOD_WIDTH = 70
_SCHEDULE_PERIOD_CHOICES = ("✓", "—")
_TEACHER_LEAVE_TEACHER_WIDTH = 120
_TEACHER_LEAVE_DATE_WIDTH = 88
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
    tables = root.findChildren(QTableWidget)
    for table in tables:
        _remove_master_enabled_column(table)
        _remove_weekday_column(table)

    class_choices = _master_column_values(
        tables,
        required_headers=("クラス", "校舎", "学部", "担任"),
        value_header="クラス",
    )
    teacher_choices = _master_column_values(
        tables,
        required_headers=("教師", "所属校舎"),
        value_header="教師",
    )

    for table in tables:
        _normalize_table_row_height(table)
        _show_schedule_period_inputs(table)
        _show_business_choice_inputs(table, class_choices, teacher_choices)
        _prepare_lesson_count_total(table)
        _show_date_inputs(table)
        _show_text_inputs(table)
        _install_lesson_count_total_updates(table)
        _configure_schedule_column_widths(table)
        _configure_teacher_leave_columns(table)

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


def _is_lesson_count_table(table: QTableWidget) -> bool:
    headers = set(_table_headers(table))
    return "クラス" in headers and "計" in headers and "担任" not in headers


def _is_teacher_assignment_table(table: QTableWidget) -> bool:
    headers = set(_table_headers(table))
    return "クラス" in headers and "担任" in headers and "校舎" not in headers


def _is_teacher_leave_matrix(table: QTableWidget) -> bool:
    headers = _table_headers(table)
    if not headers or headers[0] != "教師" or len(headers) < 2:
        return False
    return all(_looks_like_short_date(header) for header in headers[1:])


def _looks_like_short_date(value: str) -> bool:
    month_day = value.split("/")
    return len(month_day) == 2 and all(part.isdigit() for part in month_day)


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


def _find_table(
    tables: Iterable[QTableWidget],
    required_headers: tuple[str, ...],
) -> QTableWidget | None:
    required = set(required_headers)
    for table in tables:
        if required.issubset(_table_headers(table)):
            return table
    return None


def _master_column_values(
    tables: Iterable[QTableWidget],
    *,
    required_headers: tuple[str, ...],
    value_header: str,
) -> tuple[str, ...]:
    table = _find_table(tables, required_headers)
    if table is None:
        return ()
    column = _column_index(table, value_header)
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
    if isinstance(widget, QDateEdit):
        return widget.date().toString("yyyy/MM/dd")
    if isinstance(widget, QLineEdit):
        return widget.text()
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
            item = _ensure_item(table, row, column, "—")
            _set_choice_cell(table, row, column, _SCHEDULE_PERIOD_CHOICES, item.text())


def _show_business_choice_inputs(
    table: QTableWidget,
    class_choices: tuple[str, ...],
    teacher_choices: tuple[str, ...],
) -> None:
    class_column = _column_index(table, "クラス")
    if class_column is not None and (
        _is_lesson_count_table(table) or _is_teacher_assignment_table(table)
    ):
        for row in range(table.rowCount()):
            current = _cell_text(table, row, class_column)
            _set_choice_cell(table, row, class_column, class_choices, current)

    if not _is_teacher_assignment_table(table):
        return

    # Configure by physical column index, not header name. Duplicate subject names
    # must still produce an independent teacher selector in every subject column.
    for column in range(table.columnCount()):
        if column == class_column:
            continue
        for row in range(table.rowCount()):
            current = _cell_text(table, row, column)
            _set_choice_cell(
                table,
                row,
                column,
                teacher_choices,
                current,
                allow_blank=True,
            )


def _set_choice_cell(
    table: QTableWidget,
    row: int,
    column: int,
    choices: tuple[str, ...],
    current: str,
    *,
    allow_blank: bool = False,
) -> None:
    values = list(choices)
    if allow_blank and "" not in values:
        values.insert(0, "")
    if current and current not in values:
        values.append(current)

    existing = table.cellWidget(row, column)
    if isinstance(existing, QComboBox):
        combo = existing
    else:
        if existing is not None:
            table.removeCellWidget(row, column)
            existing.deleteLater()
        combo = QComboBox(table)
        table.setCellWidget(row, column, combo)

    desired = tuple(values)
    actual = tuple(combo.itemText(index) for index in range(combo.count()))
    if actual != desired:
        combo.blockSignals(True)
        combo.clear()
        combo.addItems(values)
        combo.blockSignals(False)
    if combo.currentText() != current:
        combo.blockSignals(True)
        combo.setCurrentText(current)
        combo.blockSignals(False)

    item = _ensure_item(table, row, column, current)
    item.setText(current)
    if not combo.property("cellValueSyncInstalled"):
        combo.currentTextChanged.connect(item.setText)
        combo.setProperty("cellValueSyncInstalled", True)
    if not combo.view().property("circleSelectionDelegateInstalled"):
        combo.view().setItemDelegate(_ChoiceSelectionDelegate(combo))
        combo.view().setProperty("circleSelectionDelegateInstalled", True)


def _prepare_lesson_count_total(table: QTableWidget) -> None:
    if not _is_lesson_count_table(table):
        return
    total_column = _column_index(table, "計")
    if total_column is None:
        return
    for row in range(table.rowCount()):
        existing = table.cellWidget(row, total_column)
        if existing is not None:
            table.removeCellWidget(row, total_column)
            existing.deleteLater()
        item = _ensure_item(table, row, total_column, "0")
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        item.setToolTip("各教科のコマ数から自動計算")


def _install_lesson_count_total_updates(table: QTableWidget) -> None:
    if not _is_lesson_count_table(table):
        return
    class_column = _column_index(table, "クラス")
    total_column = _column_index(table, "計")
    if class_column is None or total_column is None:
        return

    for row in range(table.rowCount()):
        for column in range(table.columnCount()):
            if column in {class_column, total_column}:
                continue
            widget = table.cellWidget(row, column)
            if not isinstance(widget, QLineEdit) or widget.property("rowTotalHookInstalled"):
                continue
            widget.textChanged.connect(
                lambda _text, target=table, target_row=row: _recalculate_lesson_count_row(
                    target, target_row
                )
            )
            widget.setProperty("rowTotalHookInstalled", True)
        _recalculate_lesson_count_row(table, row)


def _recalculate_lesson_count_row(table: QTableWidget, row: int) -> None:
    class_column = _column_index(table, "クラス")
    total_column = _column_index(table, "計")
    if class_column is None or total_column is None:
        return
    total = 0
    for column in range(table.columnCount()):
        if column in {class_column, total_column}:
            continue
        value = _cell_text(table, row, column).strip()
        try:
            total += int(value) if value else 0
        except ValueError:
            continue
    _ensure_item(table, row, total_column, "0").setText(str(total))


def _show_date_inputs(table: QTableWidget) -> None:
    date_column = _column_index(table, "日付")
    if date_column is None:
        return

    for row in range(table.rowCount()):
        existing = table.cellWidget(row, date_column)
        if isinstance(existing, QDateEdit):
            continue

        item = _ensure_item(table, row, date_column, "")
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


def _configure_teacher_leave_columns(table: QTableWidget) -> None:
    if not _is_teacher_leave_matrix(table):
        return

    header = table.horizontalHeader()
    header.setStretchLastSection(False)
    for column in range(table.columnCount()):
        header.setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
        table.setColumnWidth(
            column,
            _TEACHER_LEAVE_TEACHER_WIDTH if column == 0 else _TEACHER_LEAVE_DATE_WIDTH,
        )
    table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)


def _ensure_item(
    table: QTableWidget,
    row: int,
    column: int,
    default: str,
) -> QTableWidgetItem:
    item = table.item(row, column)
    if item is None:
        item = QTableWidgetItem(default)
        table.setItem(row, column, item)
    return item


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

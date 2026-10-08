from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import QComboBox, QDateEdit, QLabel, QTimeEdit


class EditorChoiceBox(QComboBox):
    """Keep the accepted selection affordance visible across platform themes."""

    def __init__(self) -> None:
        super().__init__()
        self.setProperty("selectionField", True)
        self._chevron = QLabel("⌄", self)
        self._chevron.setObjectName("comboChevron")
        self._chevron.setStyleSheet(
            "color: #dfe5ed; background: transparent; border: 0; font-size: 16px;"
        )
        self._chevron.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._chevron.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._chevron.setFixedSize(24, 24)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._chevron.move(max(0, self.width() - 26), max(0, (self.height() - 24) // 2))
        self._chevron.raise_()


class EditorDateEdit(QDateEdit):
    def __init__(self) -> None:
        super().__init__()
        self._indicator = QLabel("▦", self)
        self._indicator.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._indicator.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._indicator.setFixedSize(22, 24)
        self._indicator.setToolTip("カレンダーから選択")

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._indicator.move(max(0, self.width() - 24), max(0, (self.height() - 24) // 2))
        self._indicator.raise_()


class EditorTimeEdit(QTimeEdit):
    def stepBy(self, steps: int) -> None:
        self.setTime(self.time().addSecs(steps * 5 * 60))

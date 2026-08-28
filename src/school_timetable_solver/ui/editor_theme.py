from __future__ import annotations

DARK_EDITOR_STYLE = """
QWidget {
    background-color: #1f2329;
    color: #e8ecf2;
    font-size: 14px;
}

QFrame#editorHeader {
    background: #181b20;
    border-bottom: 1px solid #343a44;
}
QLabel#projectTitle {
    color: #f7f9fc;
    font-size: 20px;
    font-weight: 600;
}
QLabel#projectNote,
QLabel#navigationNote,
QLabel#pageDescription,
QLabel#pageHint,
QLabel#navigationGuide {
    color: #a8b0bd;
}
QLabel#sourceBadge,
QLabel#maintenanceBadge,
QLabel#reviewStatus {
    background: #303744;
    border: 1px solid #444d5d;
    border-radius: 5px;
    padding: 4px 8px;
    color: #dce3ee;
}

QFrame#prototypeNotice {
    background: #3a321c;
    border-bottom: 1px solid #675929;
}
QLabel#prototypeTitle {
    color: #f4d77d;
    font-weight: 600;
}
QFrame#prototypeNotice QLabel {
    background: transparent;
    color: #eadca9;
}

QFrame#navigationPanel {
    background: #181b20;
    border-right: 1px solid #343a44;
}
QLabel#navigationGroupTitle {
    background: transparent;
    color: #7f8998;
    font-size: 11px;
    font-weight: 700;
    padding: 8px 8px 5px 8px;
    border-bottom: 1px solid #2a3038;
}
QPushButton[navigation="true"] {
    background: transparent;
    color: #bac2cf;
    text-align: left;
    border: 0;
    border-radius: 6px;
    padding: 9px 10px;
}
QPushButton[navigation="true"]:hover {
    background: #292f38;
    color: #ffffff;
}
QPushButton[navigation="true"]:checked {
    background: #263d62;
    color: #eaf2ff;
    font-weight: 600;
}

QPushButton {
    background: #303742;
    color: #e8ecf2;
    border: 1px solid #495260;
    border-radius: 6px;
    padding: 7px 12px;
}
QPushButton:hover {
    background: #39414d;
    border-color: #5d6878;
}
QPushButton:pressed {
    background: #252b33;
}
QPushButton:disabled {
    background: #252a31;
    color: #69717d;
    border-color: #343a43;
}
QPushButton#backButton {
    background: transparent;
    border: 1px solid #414956;
}

QLabel#pageTitle {
    color: #f4f6fa;
    font-size: 24px;
    font-weight: 600;
}

QGroupBox {
    background: #242930;
    color: #e5e9f0;
    font-weight: 600;
    border: 1px solid #3d4550;
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 12px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 5px;
    color: #eef2f7;
}

QFrame#summaryCard,
QFrame#conditionCard {
    background: #292f37;
    border: 1px solid #414a56;
    border-radius: 8px;
}
QLabel#summaryTitle {
    color: #9ea8b6;
}
QLabel#summaryValue {
    color: #f1f4f8;
    font-size: 18px;
    font-weight: 600;
}
QLabel#conditionTitle {
    color: #f0f3f7;
    font-weight: 600;
}

QTableWidget {
    background: #1c2026;
    alternate-background-color: #22272e;
    color: #e5e9ef;
    border: 1px solid #424a56;
    border-radius: 4px;
    gridline-color: #3a424d;
    selection-background-color: #2f5689;
    selection-color: #ffffff;
}
QTableWidget::item {
    padding: 5px;
}
QTableWidget::item:selected {
    background: #2f5689;
    color: #ffffff;
}
QHeaderView::section {
    background: #303640;
    color: #e8ecf2;
    border: 0;
    border-right: 1px solid #49515d;
    border-bottom: 1px solid #49515d;
    padding: 6px;
    font-weight: 600;
}
QTableCornerButton::section {
    background: #303640;
    border: 1px solid #49515d;
}

QTabWidget::pane {
    background: #242930;
    border: 1px solid #424a56;
    border-radius: 6px;
    top: -1px;
}
QTabBar::tab {
    background: #303640;
    color: #aeb7c4;
    border: 1px solid #424a56;
    padding: 7px 14px;
}
QTabBar::tab:hover {
    background: #39414c;
    color: #ffffff;
}
QTabBar::tab:selected {
    background: #2f5689;
    color: #ffffff;
    border-color: #5279aa;
}

QLineEdit,
QPlainTextEdit,
QComboBox,
QDateEdit,
QTimeEdit,
QSpinBox,
QDoubleSpinBox {
    background: #171a1f;
    color: #edf1f6;
    border: 1px solid #46505d;
    border-radius: 5px;
    padding: 6px 8px;
    selection-background-color: #2f5689;
}
QLineEdit:focus,
QPlainTextEdit:focus,
QComboBox:focus,
QDateEdit:focus,
QTimeEdit:focus,
QSpinBox:focus,
QDoubleSpinBox:focus {
    border: 1px solid #6a94c8;
}
QComboBox::drop-down,
QDateEdit::drop-down {
    border: 0;
    width: 24px;
}
QComboBox QAbstractItemView {
    background: #20252c;
    color: #e9edf3;
    border: 1px solid #46505d;
    selection-background-color: #2f5689;
}

QCheckBox {
    background: transparent;
    color: #dce2ea;
    spacing: 7px;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
}

QScrollArea,
QScrollArea > QWidget > QWidget {
    background: #1f2329;
    border: 0;
}
QScrollBar:vertical {
    background: #181b20;
    width: 11px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #48515e;
    border-radius: 5px;
    min-height: 28px;
}
QScrollBar::handle:vertical:hover {
    background: #5b6675;
}
QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {
    height: 0;
}
QScrollBar:horizontal {
    background: #181b20;
    height: 11px;
}
QScrollBar::handle:horizontal {
    background: #48515e;
    border-radius: 5px;
    min-width: 28px;
}
QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal {
    width: 0;
}

QToolTip {
    background: #313842;
    color: #f2f4f7;
    border: 1px solid #596472;
    padding: 4px;
}
"""

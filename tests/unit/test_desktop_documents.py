from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QComboBox, QLineEdit, QMessageBox, QTableWidget

from school_timetable_solver.adapter.project_store_adapter import LocalProjectStoreAdapter
from school_timetable_solver.desktop_composition import DesktopApplicationComposition
from school_timetable_solver.model.input_models import InputDataModel
from school_timetable_solver.service.project_document_services import ImportProjectDocumentService
from school_timetable_solver.ui.editor_navigation import EditorSection


@pytest.fixture
def desktop_app() -> QApplication:
    existing = QApplication.instance()
    return cast(QApplication, existing) if existing is not None else QApplication([])


def test_editor_autosaves_count_and_uses_ids_for_renamed_duplicate_teachers(
    desktop_app: QApplication, tmp_path: Path, minimal_input_data: InputDataModel
) -> None:
    window = DesktopApplicationComposition().create_desktop_window(tmp_path)
    window._create_new_project()
    project_id = window._current_project_id
    assert project_id is not None
    editor = window._seasonal_editor()
    revision = editor.document.revision
    editor.document = ImportProjectDocumentService().execute(minimal_input_data)
    editor.document.revision = revision
    editor.document_changed.emit()
    editor._select_section(EditorSection.LESSON_COUNTS)
    table = editor.findChild(QTableWidget, "lesson_counts")
    assert table is not None
    cast(QLineEdit, table.cellWidget(0, 1)).setText("3")
    assert table.item(0, table.columnCount() - 1).text() == "3"
    stored = LocalProjectStoreAdapter(tmp_path).load_document(project_id)
    assert stored is not None and stored.lesson_requirements[0].required_periods == "3"
    editor.document.teachers[1].teacher_name = editor.document.teachers[0].teacher_name
    editor.document_changed.emit()
    editor._select_section(EditorSection.TEACHER_ASSIGNMENTS)
    table = editor.findChild(QTableWidget, "teacher_assignments")
    assert table is not None
    combo = cast(QComboBox, table.cellWidget(0, 2))
    assert combo.currentData() == "T1"
    assert combo.itemData(1) != combo.itemData(2)
    combo.setCurrentIndex(combo.findData("T2"))
    window._show_home()
    window._open_project(project_id)
    assert window._seasonal_editor().document.lesson_requirements[0].teacher_id == "T2"
    window.close()


def test_master_creation_and_removal_preserve_references_and_incomplete_drafts(
    desktop_app: QApplication, tmp_path: Path
) -> None:
    window = DesktopApplicationComposition().create_desktop_window(tmp_path)
    window._create_new_project()
    editor = window._seasonal_editor()
    editor._select_section(EditorSection.MASTER)
    editor._append_row("campuses")
    campus_table = editor.findChild(QTableWidget, "campuses")
    assert campus_table is not None
    cast(QLineEdit, campus_table.cellWidget(0, 0)).setText("新校舎")
    campus_id = editor.document.campuses[0].campus_id
    editor._append_row("rooms")
    rooms_table = editor.findChild(QTableWidget, "rooms")
    assert rooms_table is not None
    campus_combo = cast(QComboBox, rooms_table.cellWidget(0, 1))
    campus_combo.setCurrentIndex(campus_combo.findData(campus_id))
    editor._remove_row("campuses", 0)
    assert editor.document.rooms[0].campus_id == campus_id
    assert editor.document.rooms[0].room_name == ""
    assert editor.document.revision > 1
    assert not window._dirty
    window.close()


def test_schedule_creation_preserves_existing_day_edits_and_period_ids(
    desktop_app: QApplication, tmp_path: Path, minimal_input_data: InputDataModel
) -> None:
    window = DesktopApplicationComposition().create_desktop_window(tmp_path)
    window._create_new_project()
    editor = window._seasonal_editor()
    revision = editor.document.revision
    editor.document = ImportProjectDocumentService().execute(minimal_input_data)
    editor.document.revision = revision
    editor.document_changed.emit()
    editor._set_day_periods(0, False)
    editor.document.end_date = "2026-07-31"
    editor._create_dates()
    assert editor.document.calendar_days[0].enabled_period_ids == ""
    assert len(editor.document.calendar_days) == 5
    assert editor.document.calendar_days[-1].target_date == "2026-07-31"
    assert editor.document.calendar_days[-1].enabled_period_ids == "P1|P2|P3|P4|P5|P6"
    window.close()


def test_save_conflict_keeps_editor_open_and_dirty(
    desktop_app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    window = DesktopApplicationComposition().create_desktop_window(tmp_path)
    window._create_new_project()
    editor = window._seasonal_editor()
    project_id = window._current_project_id
    assert project_id is not None
    store = LocalProjectStoreAdapter(tmp_path)
    other = store.load_document(project_id)
    assert other is not None
    store.save_document(project_id, other)
    editor.document.start_date = "2027-01-01"
    editor.document_changed.emit()
    assert window._dirty
    assert "未保存" in editor._save_status.text()
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: QMessageBox.StandardButton.Ok)
    window._show_home()
    assert window._stack.currentWidget() is editor
    window._dirty = False
    window.close()


def test_blank_project_widgets_can_produce_a_verified_timetable(
    desktop_app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from openpyxl import load_workbook
    from PySide6.QtCore import QDate, QEventLoop, QTime, QTimer
    from PySide6.QtWidgets import QDateEdit, QTimeEdit

    from school_timetable_solver.model.input_models import GenerationMode
    from school_timetable_solver.model.project_models import ProjectExecutionSettingsModel

    window = DesktopApplicationComposition().create_desktop_window(tmp_path)
    window._create_new_project()
    editor = window._seasonal_editor()
    editor._select_section(EditorSection.MASTER)
    for group in ("campuses", "rooms", "teachers", "classes", "subjects"):
        editor._append_row(group)
        table = editor.findChild(QTableWidget, group)
        assert table is not None
        cast(QLineEdit, table.cellWidget(0, 0)).setText(group)
        if group in ("rooms", "teachers", "classes"):
            cast(QComboBox, table.cellWidget(0, 1)).setCurrentIndex(1)
        if group == "classes":
            cast(QLineEdit, table.cellWidget(0, 3)).setText("1")
    for index in range(6):
        editor._append_row("periods")
        table = editor.findChild(QTableWidget, "periods")
        assert table is not None
        cast(QLineEdit, table.cellWidget(index, 0)).setText(str(index + 1))
        cast(QTimeEdit, table.cellWidget(index, 1)).setTime(QTime(index + 8, 0))
        cast(QTimeEdit, table.cellWidget(index, 2)).setTime(QTime(index + 9, 0))
    editor._select_section(EditorSection.SCHEDULE)
    first = editor.findChild(QDateEdit, "start_date")
    last = editor.findChild(QDateEdit, "end_date")
    assert first is not None and last is not None
    first.setDate(QDate(2027, 1, 1))
    last.setDate(QDate(2027, 1, 1))
    editor._create_dates()
    editor._select_section(EditorSection.LESSON_COUNTS)
    counts = editor.findChild(QTableWidget, "lesson_counts")
    assert counts is not None
    cast(QLineEdit, counts.cellWidget(0, 1)).setText("1")
    editor._select_section(EditorSection.TEACHER_ASSIGNMENTS)
    assignments = editor.findChild(QTableWidget, "teacher_assignments")
    assert assignments is not None
    cast(QComboBox, assignments.cellWidget(0, 2)).setCurrentIndex(1)
    # A class policy is a required user input, not an implicit solver default.
    editor._select_section(EditorSection.PLACEMENT_CONDITIONS)
    editor._append_row("placement_rules")
    rules = editor.findChild(QTableWidget, "placement_rules")
    assert rules is not None
    cast(QLineEdit, rules.cellWidget(0, 0)).setText("クラス基本方針")
    cast(QComboBox, rules.cellWidget(0, 2)).setCurrentIndex(1)
    cast(QComboBox, rules.cellWidget(0, 3)).setCurrentIndex(1)
    # Pick the first period through the same model binding as the checklist widget.
    row = editor.document.placement_rules[0]
    editor._set_value(row, "allowed_period_ids", editor.document.periods[0].period_id)
    editor._set_value(row, "priority", "10")
    editor._set_value(row, "daily_hard_limit", "1")
    editor._append_row("placement_rules")
    teacher_policy = editor.document.placement_rules[1]
    editor._set_value(teacher_policy, "rule_name", "教師基本方針")
    editor._set_value(teacher_policy, "constraint_type", "hard")
    editor._set_value(teacher_policy, "target_entity", "teacher")
    editor._set_value(teacher_policy, "daily_hard_limit", "1")
    editor._set_value(teacher_policy, "forbid_first_last_same_day", "false")
    editor._set_value(teacher_policy, "priority", "10")
    output = tmp_path / "new-project-result.xlsx"
    monkeypatch.setattr(QMessageBox, "information", lambda *args: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "critical", lambda *args: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: QMessageBox.StandardButton.Ok)
    project_id = window._current_project_id
    assert project_id is not None
    window._start_project_run(
        project_id, ProjectExecutionSettingsModel(output, None, GenerationMode.STRICT, 5, 1, 1)
    )
    loop = QEventLoop()
    assert window._run_thread is not None
    window._run_thread.finished.connect(loop.quit)
    QTimer.singleShot(10000, loop.quit)
    loop.exec()
    desktop_app.processEvents()
    assert window._run_thread is None
    assert output.is_file(), [(issue.rule_id, issue.message) for issue in editor._issues]
    workbook = load_workbook(output, data_only=True)
    assert workbook.sheetnames == ["全体"]
    assert editor._issues == ()
    window.close()

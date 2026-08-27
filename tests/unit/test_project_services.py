from __future__ import annotations

from pathlib import Path

from school_timetable_solver.adapter.project_store_adapter import LocalProjectStoreAdapter
from school_timetable_solver.model.input_models import InputDataModel, InputWorkbookSettingsModel
from school_timetable_solver.model.project_models import ProjectSource
from school_timetable_solver.model.result_models import InputReadResultModel, ValidationIssueModel
from school_timetable_solver.service.project_services import (
    CreateProjectService,
    DuplicateProjectService,
    ImportProjectService,
)


class SuccessfulInputReader:
    def read(self, path: Path) -> InputReadResultModel:
        input_data = InputDataModel(
            settings=InputWorkbookSettingsModel("1.1", "2026 夏期講習", "本番用"),
            calendar_days=(),
            periods=(),
            campuses=(),
            rooms=(),
            teachers=(),
            classes=(),
            subjects=(),
            lesson_requirements=(),
            teacher_leaves=(),
            placement_rules=(),
        )
        return InputReadResultModel(input_data, ())


class FailedInputReader:
    def read(self, path: Path) -> InputReadResultModel:
        return InputReadResultModel(
            None,
            (
                ValidationIssueModel(
                    "TEST_IMPORT_ERROR",
                    "ERROR",
                    str(path),
                    "invalid workbook",
                ),
            ),
        )


def test_create_project_assigns_unique_untitled_names(tmp_path: Path) -> None:
    store = LocalProjectStoreAdapter(tmp_path)
    store.initialize()
    service = CreateProjectService(store)

    first = service.execute()
    second = service.execute()

    assert first.name == "無題の時間割"
    assert second.name == "無題の時間割 2"
    assert first.source is ProjectSource.BLANK


def test_import_project_uses_workbook_metadata_and_copies_file(tmp_path: Path) -> None:
    store = LocalProjectStoreAdapter(tmp_path / "app-data")
    store.initialize()
    source = tmp_path / "input.xlsx"
    source.write_bytes(b"workbook")

    result = ImportProjectService(store, SuccessfulInputReader()).execute(source)

    assert result.project is not None
    assert result.project.name == "2026 夏期講習"
    assert result.project.note == "本番用"
    assert result.project.source is ProjectSource.EXCEL_IMPORT
    assert result.project.imported_workbook_path is not None
    assert result.project.imported_workbook_path.read_bytes() == b"workbook"


def test_import_project_does_not_save_invalid_workbook(tmp_path: Path) -> None:
    store = LocalProjectStoreAdapter(tmp_path)
    store.initialize()
    source = tmp_path / "invalid.xlsx"
    source.write_bytes(b"invalid")

    result = ImportProjectService(store, FailedInputReader()).execute(source)

    assert result.project is None
    assert result.issues[0].rule_id == "TEST_IMPORT_ERROR"
    assert store.list() == ()


def test_duplicate_project_copies_imported_workbook(tmp_path: Path) -> None:
    store = LocalProjectStoreAdapter(tmp_path / "app-data")
    store.initialize()
    source = tmp_path / "input.xlsx"
    source.write_bytes(b"workbook")
    imported = ImportProjectService(store, SuccessfulInputReader()).execute(source).project
    assert imported is not None

    duplicate = DuplicateProjectService(store).execute(imported.project_id)

    assert duplicate is not None
    assert duplicate.name == "2026 夏期講習 のコピー"
    assert duplicate.imported_workbook_path is not None
    assert imported.imported_workbook_path is not None
    assert duplicate.imported_workbook_path != imported.imported_workbook_path
    assert duplicate.imported_workbook_path.read_bytes() == b"workbook"

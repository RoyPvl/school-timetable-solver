from __future__ import annotations

from pathlib import Path

from school_timetable_solver.adapter.excel_input_router import CompatibleExcelInputReaderAdapter
from school_timetable_solver.adapter.project_store_adapter import LocalProjectStoreAdapter
from school_timetable_solver.composition import ApplicationComposition
from school_timetable_solver.model.input_models import (
    GenerationMode,
    InputDataModel,
    InputWorkbookSettingsModel,
)
from school_timetable_solver.model.project_models import (
    ProjectExecutionSettingsModel,
    ProjectSource,
)
from school_timetable_solver.model.result_models import (
    InputReadResultModel,
    ValidationIssueModel,
)
from school_timetable_solver.service.project_document_services import (
    BuildProjectInputService,
    ImportProjectDocumentService,
    LoadProjectDocumentService,
)
from school_timetable_solver.service.project_services import (
    CreateProjectService,
    DuplicateProjectService,
    ExecuteProjectService,
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


class RecordingExecutionLogger:
    def __init__(self) -> None:
        self.path: Path | None = None

    def configure(self, path: Path | None) -> None:
        self.path = path


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


def test_execute_project_maps_gui_settings_to_generation_request(
    tmp_path: Path, minimal_input_data: InputDataModel
) -> None:
    store = LocalProjectStoreAdapter(tmp_path / "app-data")
    store.initialize()
    source = tmp_path / "input.xlsx"
    source.write_bytes(b"workbook")
    project = ImportProjectService(store, SuccessfulInputReader()).execute(source).project
    assert project is not None
    assert project.imported_workbook_path is not None

    document = ImportProjectDocumentService().execute(minimal_input_data)
    document.revision = 1
    store.save_document(project.project_id, document)
    generator = ApplicationComposition().create_generate_from_input_data_service()
    execution_logger = RecordingExecutionLogger()
    settings = ProjectExecutionSettingsModel(
        output_path=tmp_path / "result.xlsx",
        log_path=tmp_path / "run.log",
        solve_mode=GenerationMode.VALIDATE_ONLY,
        max_solve_seconds=120.0,
        random_seed=7,
        num_search_workers=4,
    )

    result = ExecuteProjectService(
        store,
        generator,
        LoadProjectDocumentService(store, CompatibleExcelInputReaderAdapter()),
        BuildProjectInputService(),
        execution_logger,
    ).execute(
        project.project_id,
        settings,
    )

    assert result.exit_code == 0
    assert result.request.input_path == project.imported_workbook_path
    assert result.request.output_path == settings.output_path
    assert result.request.log_path == settings.log_path
    assert result.request.solve_mode is settings.solve_mode
    assert result.request.max_solve_seconds == 120.0
    assert result.request.random_seed == 7
    assert result.request.num_search_workers == 4
    assert execution_logger.path == settings.log_path


def test_execute_blank_project_returns_input_issues_without_output(tmp_path: Path) -> None:
    store = LocalProjectStoreAdapter(tmp_path)
    store.initialize()
    project = CreateProjectService(store).execute()
    settings = ProjectExecutionSettingsModel(
        tmp_path / "result.xlsx", None, GenerationMode.VALIDATE_ONLY, 60.0, 1, 1
    )
    result = ExecuteProjectService(
        store,
        ApplicationComposition().create_generate_from_input_data_service(),
        LoadProjectDocumentService(store, CompatibleExcelInputReaderAdapter()),
        BuildProjectInputService(),
        RecordingExecutionLogger(),
    ).execute(project.project_id, settings)
    assert result.exit_code == 2
    assert any(issue.rule_id == "OUTPUT_DATE_REQUIRED" for issue in result.validation_report.issues)
    assert not settings.output_path.exists()

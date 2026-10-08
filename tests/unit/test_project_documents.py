from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from school_timetable_solver.adapter.excel_input_router import CompatibleExcelInputReaderAdapter
from school_timetable_solver.adapter.execution_log_adapter import ExecutionLogAdapter
from school_timetable_solver.adapter.project_document_codec import (
    decode_project_document,
    encode_project_document,
)
from school_timetable_solver.adapter.project_store_adapter import LocalProjectStoreAdapter
from school_timetable_solver.composition import ApplicationComposition
from school_timetable_solver.model.input_models import GenerationMode, InputDataModel
from school_timetable_solver.model.project_models import ProjectExecutionSettingsModel
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


def test_document_round_trip_preserves_every_imported_domain_field(
    tmp_path: Path, minimal_input_data: InputDataModel
) -> None:
    store = LocalProjectStoreAdapter(tmp_path)
    store.initialize()
    project = CreateProjectService(store).execute(minimal_input_data.settings.timetable_name)
    doc = ImportProjectDocumentService().execute(minimal_input_data)
    copied = decode_project_document(encode_project_document(doc))
    result = BuildProjectInputService().execute(copied, project)
    assert result.issues == ()
    assert result.input_data == minimal_input_data


def test_draft_saves_invalid_text_and_reopens_without_silent_repair(
    tmp_path: Path, minimal_input_data: InputDataModel
) -> None:
    store = LocalProjectStoreAdapter(tmp_path)
    store.initialize()
    project = CreateProjectService(store).execute()
    doc = ImportProjectDocumentService().execute(minimal_input_data)
    doc.lesson_requirements[0].required_periods = "未定"
    doc.revision = 1
    store.save_document(project.project_id, doc)
    reopened = LocalProjectStoreAdapter(tmp_path).load_document(project.project_id)
    assert reopened is not None
    assert reopened.lesson_requirements[0].required_periods == "未定"
    result = BuildProjectInputService().execute(reopened, project)
    assert result.input_data is None
    assert result.issues[0].rule_id == "DOCUMENT_FIELD_FORMAT"


def test_stale_revision_does_not_overwrite_saved_document(tmp_path: Path) -> None:
    store = LocalProjectStoreAdapter(tmp_path)
    store.initialize()
    project = CreateProjectService(store).execute()
    loader = LoadProjectDocumentService(store, CompatibleExcelInputReaderAdapter())
    first = loader.execute(project.project_id)
    stale = loader.execute(project.project_id)
    first.start_date = "2027-01-01"
    store.save_document(project.project_id, first)
    stale.start_date = "2028-01-01"
    with pytest.raises(ValueError, match="別の画面"):
        store.save_document(project.project_id, stale)
    saved = store.load_document(project.project_id)
    assert saved is not None and saved.start_date == "2027-01-01"
    assert stale.revision == 1


def test_duplicate_snapshots_document_and_delete_cascades(
    tmp_path: Path, minimal_input_data: InputDataModel
) -> None:
    store = LocalProjectStoreAdapter(tmp_path)
    store.initialize()
    project = CreateProjectService(store).execute()
    doc = ImportProjectDocumentService().execute(minimal_input_data)
    doc.revision = 1
    store.save_document(project.project_id, doc)
    duplicate = DuplicateProjectService(store).execute(project.project_id)
    assert duplicate is not None
    copied = store.load_document(duplicate.project_id)
    assert copied is not None
    copied.teachers[0].teacher_name = "変更後"
    store.save_document(duplicate.project_id, copied)
    original = store.load_document(project.project_id)
    assert original is not None and original.teachers[0].teacher_name == "教師一"
    store.delete(duplicate.project_id)
    assert store.load_document(duplicate.project_id) is None


def test_unsupported_schema_is_rejected_without_modifying_payload(tmp_path: Path) -> None:
    store = LocalProjectStoreAdapter(tmp_path)
    store.initialize()
    project = CreateProjectService(store).execute()
    doc = LoadProjectDocumentService(store, CompatibleExcelInputReaderAdapter()).execute(
        project.project_id
    )
    payload = json.loads(encode_project_document(doc))
    payload["document_schema_version"] = 999
    raw = json.dumps(payload)
    with sqlite3.connect(tmp_path / "timetable.db") as connection:
        connection.execute(
            "UPDATE project_documents SET payload_json=? WHERE project_id=?",
            (raw, project.project_id),
        )
    with pytest.raises(ValueError, match="未対応"):
        store.load_document(project.project_id)
    with sqlite3.connect(tmp_path / "timetable.db") as connection:
        assert connection.execute("SELECT payload_json FROM project_documents").fetchone()[0] == raw


def test_imported_project_generates_from_document_after_excel_is_removed(tmp_path: Path) -> None:
    store = LocalProjectStoreAdapter(tmp_path / "app")
    store.initialize()
    reader = CompatibleExcelInputReaderAdapter()
    imported = (
        ImportProjectService(store, reader)
        .execute(Path("projects/sample/input/時間割入力_サンプル.xlsx"))
        .project
    )
    assert imported is not None and imported.imported_workbook_path is not None
    doc = store.load_document(imported.project_id)
    assert doc is not None
    doc.lesson_requirements[0].required_periods = "1"
    store.save_document(imported.project_id, doc)
    imported.imported_workbook_path.unlink()
    result = ExecuteProjectService(
        store,
        ApplicationComposition().create_generate_from_input_data_service(),
        LoadProjectDocumentService(store, reader),
        BuildProjectInputService(),
        ExecutionLogAdapter(),
    ).execute(
        imported.project_id,
        ProjectExecutionSettingsModel(
            tmp_path / "result.xlsx", None, GenerationMode.STRICT, 10, 1, 1
        ),
    )
    assert result.exit_code == 0
    assert (
        result.input_data is not None
        and result.input_data.lesson_requirements[0].required_periods == 1
    )
    assert (
        len(
            [
                lesson
                for lesson in result.lessons
                if lesson.requirement_id == doc.lesson_requirements[0].requirement_id
            ]
        )
        == 1
    )
    assert not any(issue.severity == "ERROR" for issue in result.validation_report.issues)
    assert (tmp_path / "result.xlsx").is_file()


def test_legacy_import_migrates_once_and_metadata_stays_canonical(tmp_path: Path) -> None:
    store = LocalProjectStoreAdapter(tmp_path)
    store.initialize()
    reader = CompatibleExcelInputReaderAdapter()
    project = (
        ImportProjectService(store, reader)
        .execute(Path("projects/sample/input/時間割入力_サンプル.xlsx"))
        .project
    )
    assert project is not None and project.imported_workbook_path is not None
    with sqlite3.connect(tmp_path / "timetable.db") as connection:
        connection.execute(
            "DELETE FROM project_documents WHERE project_id=?", (project.project_id,)
        )
    loader = LoadProjectDocumentService(store, reader)
    migrated = loader.execute(project.project_id)
    assert migrated.revision == 1 and migrated.lesson_requirements
    project.imported_workbook_path.unlink()
    assert loader.execute(project.project_id) == migrated
    from school_timetable_solver.service.project_services import UpdateProjectMetadataService

    renamed = UpdateProjectMetadataService(store).execute(
        project.project_id, "更新した名称", "更新した備考"
    )
    assert renamed is not None
    data = BuildProjectInputService().execute(migrated, renamed).input_data
    assert data is not None and data.settings.timetable_name == "更新した名称"
    assert data.settings.description == "更新した備考"
    duplicate = DuplicateProjectService(store).execute(project.project_id)
    assert duplicate is not None and store.load_document(duplicate.project_id) is not None


def test_invalid_document_does_not_replace_existing_output(
    tmp_path: Path, minimal_input_data: InputDataModel
) -> None:
    store = LocalProjectStoreAdapter(tmp_path)
    store.initialize()
    project = CreateProjectService(store).execute()
    doc = ImportProjectDocumentService().execute(minimal_input_data)
    doc.revision = 1
    doc.lesson_requirements[0].teacher_id = "missing-teacher"
    store.save_document(project.project_id, doc)
    output = tmp_path / "protected.xlsx"
    output.write_bytes(b"previous result")
    result = ExecuteProjectService(
        store,
        ApplicationComposition().create_generate_from_input_data_service(),
        LoadProjectDocumentService(store, CompatibleExcelInputReaderAdapter()),
        BuildProjectInputService(),
        ExecutionLogAdapter(),
    ).execute(
        project.project_id,
        ProjectExecutionSettingsModel(output, None, GenerationMode.STRICT, 5, 1, 1),
    )
    assert result.exit_code == 2
    assert output.read_bytes() == b"previous result"
    assert any(issue.rule_id == "UNKNOWN_REFERENCE" for issue in result.validation_report.issues)

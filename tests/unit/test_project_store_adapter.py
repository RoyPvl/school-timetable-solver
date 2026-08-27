from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from school_timetable_solver.adapter.project_store_adapter import LocalProjectStoreAdapter
from school_timetable_solver.model.project_models import ProjectModel, ProjectSource


def _project(
    project_id: str,
    name: str,
    source: ProjectSource,
    created_at: datetime,
) -> ProjectModel:
    return ProjectModel(
        project_id=project_id,
        name=name,
        note="",
        source=source,
        imported_workbook_path=None,
        created_at=created_at,
        updated_at=created_at,
    )


def test_project_store_persists_lists_updates_and_deletes(tmp_path: Path) -> None:
    store = LocalProjectStoreAdapter(tmp_path)
    store.initialize()
    now = datetime(2026, 8, 27, tzinfo=UTC)

    first = store.create(_project("p1", "first", ProjectSource.BLANK, now))
    second = store.create(
        _project("p2", "second", ProjectSource.BLANK, now + timedelta(minutes=1))
    )

    assert store.load(first.project_id) == first
    assert store.list() == (second, first)

    updated = store.update_metadata(
        first.project_id,
        "renamed",
        "memo",
        now + timedelta(minutes=2),
    )
    assert updated is not None
    assert updated.name == "renamed"
    assert updated.note == "memo"
    assert store.list()[0].project_id == first.project_id

    assert store.delete(second.project_id)
    assert store.load(second.project_id) is None
    assert not store.delete("missing")


def test_project_store_copies_imported_workbook_into_app_data(tmp_path: Path) -> None:
    store = LocalProjectStoreAdapter(tmp_path / "app-data")
    store.initialize()
    source = tmp_path / "input.xlsx"
    source.write_bytes(b"workbook")
    now = datetime(2026, 8, 27, tzinfo=UTC)

    stored = store.create(
        _project("imported", "imported", ProjectSource.EXCEL_IMPORT, now),
        source,
    )

    assert stored.imported_workbook_path is not None
    assert stored.imported_workbook_path != source
    assert stored.imported_workbook_path.read_bytes() == b"workbook"
    source.unlink()
    assert stored.imported_workbook_path.exists()

    imported_copy = stored.imported_workbook_path
    assert store.delete(stored.project_id)
    assert not imported_copy.exists()

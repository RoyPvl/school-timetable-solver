from __future__ import annotations

from datetime import date, time
from pathlib import Path

from school_timetable_solver.adapter.excel_input_adapter import ExcelInputReaderAdapter


def test_excel_reader_converts_dates_times_booleans_and_csv_values() -> None:
    sample = Path("projects/sample/input/時間割入力_サンプル.xlsx")
    result = ExcelInputReaderAdapter().read(sample)

    assert result.issues == ()
    assert result.input_data is not None
    assert isinstance(result.input_data.settings.start_date, date)
    assert isinstance(result.input_data.periods[0].start_time, time)
    assert result.input_data.campuses[0].enabled is True
    assert result.input_data.teachers[0].subject_ids == ("MATH", "ENGLISH")


def test_excel_reader_reports_missing_file_with_format_issue(tmp_path: Path) -> None:
    result = ExcelInputReaderAdapter().read(tmp_path / "missing.xlsx")

    assert result.input_data is None
    assert result.issues[0].rule_id == "INPUT_FILE_NOT_FOUND"

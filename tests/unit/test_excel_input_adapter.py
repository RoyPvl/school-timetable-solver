from __future__ import annotations

from pathlib import Path

from openpyxl import load_workbook

from school_timetable_solver.adapter.excel_input_adapter import ExcelInputReaderAdapter

SAMPLE = Path("projects/sample/input/時間割入力_サンプル.xlsx")


def test_reader_accepts_contract_v0_1_and_normalizes_horizontal_availability() -> None:
    result = ExcelInputReaderAdapter().read(SAMPLE)

    assert result.input_data is not None
    assert not [issue for issue in result.issues if issue.severity == "ERROR"]
    assert result.input_data.settings.schema_version == "0.1"
    assert len(result.input_data.periods) == 6
    assert len(result.input_data.teacher_availability) % 6 == 0
    assert all(isinstance(item.available, bool) for item in result.input_data.teacher_availability)


def test_operation_sheet_needs_no_header_and_preference_rows_are_ignored(
    tmp_path: Path,
) -> None:
    workbook = load_workbook(SAMPLE)
    operation = workbook["00_操作説明"]
    operation.delete_rows(1, operation.max_row)
    operation["C8"] = "自由記述"
    preference = workbook["12_選好設定"]
    preference.append(("UNIMPLEMENTED", "not-a-boolean", "not-an-integer", "ignored"))
    target = tmp_path / "free-form.xlsx"
    workbook.save(target)

    result = ExcelInputReaderAdapter().read(target)

    assert result.input_data is not None
    assert not [issue for issue in result.issues if issue.severity == "ERROR"]


def test_reader_rejects_non_boolean_values(tmp_path: Path) -> None:
    workbook = load_workbook(SAMPLE)
    workbook["02_開講カレンダー"]["B2"] = 1
    target = tmp_path / "invalid-boolean.xlsx"
    workbook.save(target)

    result = ExcelInputReaderAdapter().read(target)

    assert result.input_data is None
    assert any(issue.rule_id == "INVALID_BOOLEAN" for issue in result.issues)


def test_reader_rejects_string_date_and_unsupported_schema(tmp_path: Path) -> None:
    workbook = load_workbook(SAMPLE)
    workbook["02_開講カレンダー"]["A2"] = "2026-07-27"
    workbook["01_基本設定"]["B2"] = "9.9"
    target = tmp_path / "invalid-date-schema.xlsx"
    workbook.save(target)

    result = ExcelInputReaderAdapter().read(target)

    rule_ids = {issue.rule_id for issue in result.issues}
    assert {"INVALID_DATE", "UNSUPPORTED_SCHEMA_VERSION"} <= rule_ids


def test_reader_trims_text_skips_empty_rows_and_uses_pipe_and_slash() -> None:
    result = ExcelInputReaderAdapter().read(SAMPLE)
    assert result.input_data is not None

    input_data = result.input_data
    elementary = next(rule for rule in input_data.placement_rules if rule.rule_id == "R_ELEMENTARY")
    override = next(rule for rule in input_data.placement_rules if rule.rule_id == "R_JH_OVERRIDE")
    assert elementary.condition_fields == ("division",)
    assert elementary.allowed_period_ids == ("P1", "P2", "P3")
    assert override.condition_values == ("junior_high", "1/3")


def test_missing_required_sheet_is_format_error(tmp_path: Path) -> None:
    workbook = load_workbook(SAMPLE)
    del workbook["12_選好設定"]
    target = tmp_path / "missing-sheet.xlsx"
    workbook.save(target)

    result = ExcelInputReaderAdapter().read(target)

    assert result.input_data is None
    assert any(issue.rule_id == "REQUIRED_SHEET_MISSING" for issue in result.issues)

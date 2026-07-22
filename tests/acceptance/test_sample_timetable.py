from __future__ import annotations

from collections import Counter
from pathlib import Path

from openpyxl import load_workbook

from school_timetable_solver.main import main

REQUIRED_OUTPUT_SHEETS = {
    "全体時間割",
    "教師別時間割",
    "クラス別時間割",
    "教師別集計",
    "クラス教科別集計",
    "検証結果",
    "実行条件",
    "未配置授業",
}


def test_sample_cli_generates_verified_result_workbook(tmp_path: Path) -> None:
    output = tmp_path / "result.xlsx"
    log = tmp_path / "run.log"

    exit_code = main(
        (
            "--input",
            "projects/sample/input/時間割入力_サンプル.xlsx",
            "--output",
            str(output),
            "--log",
            str(log),
        )
    )

    assert exit_code == 0
    assert output.is_file()
    assert log.is_file()
    workbook = load_workbook(output, data_only=True)
    assert set(workbook.sheetnames) == REQUIRED_OUTPUT_SHEETS
    rows = list(workbook["全体時間割"].iter_rows(min_row=2, values_only=True))
    assert rows
    assert max(Counter((row[6], row[0], row[1]) for row in rows).values()) == 1
    assert max(Counter((row[4], row[0], row[1]) for row in rows).values()) == 1
    assert max(Counter((row[3], row[0], row[1]) for row in rows).values()) == 1
    summary_rows = list(workbook["クラス教科別集計"].iter_rows(min_row=2, values_only=True))
    assert summary_rows and all(row[6] == 0 for row in summary_rows)
    validation_rows = list(workbook["検証結果"].iter_rows(min_row=2, values_only=True))
    assert not [row for row in validation_rows if row[1] == "ERROR"]
    conditions: dict[str, object] = {
        str(row[0]): row[1] for row in workbook["実行条件"].iter_rows(min_row=2, values_only=True)
    }
    assert conditions["Solver状態"] in {"OPTIMAL", "FEASIBLE"}
    assert conditions["乱数シード"] == 1


def test_diagnostic_mode_is_reported_as_input_error(tmp_path: Path) -> None:
    source = Path("projects/sample/input/時間割入力_サンプル.xlsx")
    diagnostic_input = tmp_path / "diagnostic.xlsx"
    workbook = load_workbook(source)
    settings = workbook["01_基本設定"]
    for row_number in range(2, settings.max_row + 1):
        if settings.cell(row_number, 1).value == "solve_mode":
            settings.cell(row_number, 2, "diagnostic")
    workbook.save(diagnostic_input)
    output = tmp_path / "diagnostic_result.xlsx"

    exit_code = main(("--input", str(diagnostic_input), "--output", str(output)))

    assert exit_code == 2
    result = load_workbook(output, data_only=True)
    issues = list(result["検証結果"].iter_rows(min_row=2, values_only=True))
    assert any(row[0] == "UNSUPPORTED_GENERATION_MODE" for row in issues)


def test_validate_only_writes_report_without_running_solver(tmp_path: Path) -> None:
    source = Path("projects/sample/input/時間割入力_サンプル.xlsx")
    validate_input = tmp_path / "validate.xlsx"
    workbook = load_workbook(source)
    settings = workbook["01_基本設定"]
    for row_number in range(2, settings.max_row + 1):
        if settings.cell(row_number, 1).value == "solve_mode":
            settings.cell(row_number, 2, "validate_only")
    workbook.save(validate_input)
    output = tmp_path / "validation_result.xlsx"

    exit_code = main(("--input", str(validate_input), "--output", str(output)))

    assert exit_code == 0
    result = load_workbook(output, data_only=True)
    conditions: dict[str, object] = {
        str(row[0]): row[1] for row in result["実行条件"].iter_rows(min_row=2, values_only=True)
    }
    assert conditions["アプリ状態"] == "VALIDATED"
    assert conditions["Solver状態"] == "NOT_RUN"
    assert result["全体時間割"].max_row == 1

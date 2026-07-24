from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from openpyxl import load_workbook

from school_timetable_solver.adapter.excel_output_adapter import (
    ExcelTimetableWriterAdapter,
)
from school_timetable_solver.model.input_models import InputDataModel
from school_timetable_solver.model.result_models import ScheduledLessonModel
from school_timetable_solver.service.result_services import BuildTimetableDocumentService


def _excel_date(value: object) -> date:
    assert isinstance(value, datetime)
    return value.date()


def test_writer_generates_contractual_matrix_layout_and_borders(
    minimal_input_data: InputDataModel,
    tmp_path: Path,
) -> None:
    lesson = ScheduledLessonModel(
        "Q1",
        minimal_input_data.calendar_days[0].target_date,
        "P1",
        "T1",
        "R1",
        "C1",
        "CL1",
        "S1",
    )
    document = BuildTimetableDocumentService().execute(minimal_input_data, (lesson,))
    output = tmp_path / "result.xlsx"
    ExcelTimetableWriterAdapter().write(document, output)

    workbook = load_workbook(output, data_only=True)
    worksheet = workbook["全体"]
    assert workbook.sheetnames == ["全体"]
    assert worksheet["A1"].value is None
    assert _excel_date(worksheet["A2"].value) == minimal_input_data.calendar_days[0].target_date
    assert worksheet["A2"].number_format == 'm"月"d"日"'
    assert worksheet["A3"].value == "月曜日"
    assert worksheet["A4"].value == "①\n9:00～10:00"  # noqa: RUF001
    assert worksheet["B4"].value == "クラス"
    assert worksheet["C4"].value == "小学A"
    assert worksheet["C5"].value == "算数"
    assert worksheet["C6"].value == "教師一"
    assert {"A2:B2", "A3:B3", "C2:D2", "A4:A6"} <= {
        str(item) for item in worksheet.merged_cells.ranges
    }
    assert worksheet["A2"].border.top.style == "thin"
    assert worksheet["A2"].border.bottom.style == "hair"
    assert worksheet["A2"].border.right.style == "thin"
    assert worksheet["C4"].border.top.style == "thin"
    assert worksheet["C4"].border.bottom.style == "hair"
    assert worksheet["C4"].border.right.style == "hair"
    assert worksheet["D4"].border.right.style == "thin"
    assert worksheet["E4"].border.left.style == "thin"
    assert worksheet["A4"].border.bottom.style == "thin"
    assert workbook.__dict__.get("_external_links") == []


def test_writer_places_dates_left_right_then_down_and_leaves_odd_slot_blank(
    minimal_input_data: InputDataModel,
    tmp_path: Path,
) -> None:
    document = BuildTimetableDocumentService().execute(minimal_input_data, ())
    output = tmp_path / "dates.xlsx"
    ExcelTimetableWriterAdapter().write(document, output)

    worksheet = load_workbook(output)["全体"]
    matrix_width = 2 + len(minimal_input_data.rooms)
    right_start = 1 + matrix_width + 1
    assert _excel_date(worksheet.cell(2, 1).value) == (
        minimal_input_data.calendar_days[0].target_date
    )
    assert (
        _excel_date(worksheet.cell(2, right_start).value)
        == minimal_input_data.calendar_days[1].target_date
    )
    assert _excel_date(worksheet.cell(24, 1).value) == (
        minimal_input_data.calendar_days[2].target_date
    )
    assert worksheet.cell(22, 1).value is None
    assert worksheet.cell(23, 1).value is None
    for row in range(24, 44):
        for column in range(right_start, right_start + matrix_width):
            cell = worksheet.cell(row, column)
            assert cell.value is None
            assert cell.border.left.style is None
            assert cell.border.right.style is None
    assert worksheet.cell(24, 1).value is not None
    assert worksheet.cell(26, 3).value is None

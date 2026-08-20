from __future__ import annotations

from pathlib import Path

from school_timetable_solver.adapter.excel_input_adapter import ExcelInputReaderAdapter
from school_timetable_solver.adapter.excel_v2_workbook_adapter import ExcelV2WorkbookWriterAdapter
from school_timetable_solver.model.result_models import InputReadResultModel


class MigrateInputWorkbookToV2Service:
    """Migrate a v1.1 workbook to the human-facing v2.0 contract via InputDataModel."""

    def __init__(self) -> None:
        self._reader = ExcelInputReaderAdapter()
        self._writer = ExcelV2WorkbookWriterAdapter()

    def execute(self, source_path: Path, output_path: Path) -> InputReadResultModel:
        result = self._reader.read(source_path)
        if result.input_data is None or any(issue.severity == "ERROR" for issue in result.issues):
            return result
        self._writer.write(output_path, result.input_data)
        return result

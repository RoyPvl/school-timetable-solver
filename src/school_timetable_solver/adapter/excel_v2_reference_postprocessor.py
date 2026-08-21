from __future__ import annotations

from typing import Any

from school_timetable_solver.adapter.excel_v2_workbook_postprocessor import (
    ExcelV2WorkbookPostprocessor,
)
from school_timetable_solver.model.input_models import InputDataModel


class ReferenceLabelExcelV2WorkbookPostprocessor(ExcelV2WorkbookPostprocessor):
    """Reference-label postprocessor with empty-table placeholder handling.

    ``ExcelV2WorkbookWriterAdapter`` writes a single all-empty data row when a
    logical table has zero rows so that an Excel Table object can still exist.
    Reference rewriting must ignore that physical placeholder row.
    """

    @staticmethod
    def _nonblank_rows(worksheet: Any, headers: dict[str, int], min_row: int, max_row: int) -> list[int]:
        columns = tuple(headers.values())
        return [
            row
            for row in range(min_row + 1, max_row + 1)
            if any(worksheet.cell(row, column).value is not None for column in columns)
        ]

    def _rewrite_teacher_leaves(
        self,
        workbook: Any,
        data: InputDataModel,
        labels: dict[str, str],
    ) -> None:
        worksheet, headers, min_row, max_row = self._table(
            workbook,
            "05_教師条件",
            "T_TEACHER_LEAVES",
        )
        excel_rows = self._nonblank_rows(worksheet, headers, min_row, max_row)
        if len(excel_rows) != len(data.teacher_leaves):
            raise ValueError("T_TEACHER_LEAVES row count does not match source model")
        for row, model in zip(excel_rows, data.teacher_leaves, strict=True):
            worksheet.cell(row, headers["教師"]).value = labels[model.teacher_id]

    def _rewrite_lesson_count_targets(
        self,
        workbook: Any,
        data: InputDataModel,
        subject_labels: dict[str, str],
        *,
        soft: bool,
    ) -> None:
        segments = (
            data.lesson_count_preference_rule_segments
            if soft
            else data.lesson_count_rule_segments
        )
        table_name = "T_LESSON_COUNT_SOFT_TARGETS" if soft else "T_LESSON_COUNT_HARD_TARGETS"
        worksheet, headers, min_row, max_row = self._table(
            workbook,
            "07_個別ルール",
            table_name,
        )
        expected_subject_ids = self._grouped_target_subject_ids(data, segments)
        excel_rows = self._nonblank_rows(worksheet, headers, min_row, max_row)
        if len(excel_rows) != len(expected_subject_ids):
            raise ValueError(f"{table_name} row count does not match source model")
        for row, subject_id in zip(excel_rows, expected_subject_ids, strict=True):
            worksheet.cell(row, headers["教科"]).value = subject_labels[subject_id]

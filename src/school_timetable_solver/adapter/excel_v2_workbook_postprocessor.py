from __future__ import annotations

from pathlib import Path

from openpyxl import load_workbook
from openpyxl.utils.cell import range_boundaries

from school_timetable_solver.adapter.excel_input_v2_adapter import UNSPECIFIED
from school_timetable_solver.model.input_models import InputDataModel


class ExcelV2WorkbookPostprocessor:
    """Apply layout and migration fixes that depend on the source model."""

    def execute(self, path: Path, data: InputDataModel) -> None:
        workbook = load_workbook(path)
        try:
            for worksheet in workbook.worksheets:
                if worksheet.title == "_system":
                    continue
                # A worksheet can contain multiple vertically stacked tables. Hiding a column for
                # one table would hide the same column in every table and can make unrelated user
                # fields disappear. Internal cells are therefore kept visible and visually marked
                # by the writer instead of hiding worksheet columns globally.
                for dimension in worksheet.column_dimensions.values():
                    dimension.hidden = False

            self._fill_direct_class_rule_campuses(workbook, data)
            workbook.save(path)
        finally:
            workbook.close()

    def _fill_direct_class_rule_campuses(self, workbook: object, data: InputDataModel) -> None:
        worksheet = workbook["06_基本配置ルール"]  # type: ignore[index]
        table = worksheet.tables["T_PLACEMENT_RULES"]
        min_col, min_row, max_col, max_row = range_boundaries(table.ref)
        headers = {
            worksheet.cell(min_row, column).value: column
            for column in range(min_col, max_col + 1)
        }
        class_by_id = {item.class_id: item for item in data.classes}
        campus_name_by_id = {item.campus_id: item.campus_name for item in data.campuses}
        rule_by_id = {item.rule_id: item for item in data.placement_rules}

        for row in range(min_row + 1, max_row + 1):
            rule_id = worksheet.cell(row, headers["内部ID"]).value
            direct_class = worksheet.cell(row, headers["クラス"]).value
            campus_cell = worksheet.cell(row, headers["校舎"])
            if direct_class in (None, "", UNSPECIFIED) or campus_cell.value != UNSPECIFIED:
                continue
            rule = rule_by_id.get(str(rule_id))
            if rule is None:
                continue
            for field, operator, value in zip(
                rule.condition_fields,
                rule.condition_operators,
                rule.condition_values,
                strict=True,
            ):
                if field == "class_id" and operator == "eq" and value in class_by_id:
                    class_model = class_by_id[value]
                    campus_cell.value = campus_name_by_id[class_model.campus_id]
                    break

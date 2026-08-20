from __future__ import annotations

from pathlib import Path

from openpyxl import load_workbook


class ExcelV2WorkbookPostprocessor:
    """Apply sheet-wide layout fixes that cannot safely be expressed per stacked table."""

    def execute(self, path: Path) -> None:
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
            workbook.save(path)
        finally:
            workbook.close()

from __future__ import annotations

import os
import tempfile
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import ClassVar

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from school_timetable_solver.model.result_models import GenerationResultModel


class ExcelTimetableWriterAdapter:
    """Write all result views to one workbook and atomically replace the destination."""

    _sheet_headers: ClassVar[dict[str, tuple[str, ...]]] = {
        "全体時間割": ("日付", "時限", "校舎", "教室", "クラス", "教科", "教師"),
        "教師別時間割": ("教師", "日付", "時限", "校舎", "教室", "クラス", "教科"),
        "クラス別時間割": ("クラス", "日付", "時限", "校舎", "教室", "教科", "教師"),
        "教師別集計": ("teacher_id", "教師", "総担当コマ数"),
        "クラス教科別集計": (
            "class_id",
            "クラス",
            "subject_id",
            "教科",
            "要求数",
            "生成数",
            "差分",
        ),
        "検証結果": ("rule_id", "重要度", "対象", "内容", "セル"),
        "実行条件": ("項目", "値"),
        "未配置授業": ("requirement_id", "要求数", "生成数", "不足数", "理由"),
    }

    def __init__(self, template_path: Path | None = None) -> None:
        self._template_path = template_path

    def write(self, result: GenerationResultModel, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        workbook = self._create_workbook()
        sheets = {name: workbook[name] for name in self._sheet_headers}

        data = result.input_data
        campus_names = {item.campus_id: item.campus_name for item in data.campuses} if data else {}
        room_names = {item.room_id: item.room_name for item in data.rooms} if data else {}
        class_names = {item.class_id: item.class_name for item in data.classes} if data else {}
        subject_names = (
            {item.subject_id: item.subject_name for item in data.subjects} if data else {}
        )
        teacher_names = (
            {item.teacher_id: item.teacher_name for item in data.teachers} if data else {}
        )
        period_orders = {item.period_id: item.sort_order for item in data.periods} if data else {}

        for lesson in result.lessons:
            common = (
                lesson.target_date.isoformat(),
                lesson.period_id,
                campus_names.get(lesson.campus_id, lesson.campus_id),
                room_names.get(lesson.room_id, lesson.room_id),
                class_names.get(lesson.class_id, lesson.class_id),
                subject_names.get(lesson.subject_id, lesson.subject_id),
                teacher_names.get(lesson.teacher_id, lesson.teacher_id),
            )
            sheets["全体時間割"].append(common)
        for lesson in sorted(
            result.lessons,
            key=lambda item: (
                item.teacher_id,
                item.target_date,
                period_orders.get(item.period_id, 0),
            ),
        ):
            sheets["教師別時間割"].append(
                (
                    teacher_names.get(lesson.teacher_id, lesson.teacher_id),
                    lesson.target_date.isoformat(),
                    lesson.period_id,
                    campus_names.get(lesson.campus_id, lesson.campus_id),
                    room_names.get(lesson.room_id, lesson.room_id),
                    class_names.get(lesson.class_id, lesson.class_id),
                    subject_names.get(lesson.subject_id, lesson.subject_id),
                )
            )
        for lesson in sorted(
            result.lessons,
            key=lambda item: (
                item.class_id,
                item.target_date,
                period_orders.get(item.period_id, 0),
            ),
        ):
            sheets["クラス別時間割"].append(
                (
                    class_names.get(lesson.class_id, lesson.class_id),
                    lesson.target_date.isoformat(),
                    lesson.period_id,
                    campus_names.get(lesson.campus_id, lesson.campus_id),
                    room_names.get(lesson.room_id, lesson.room_id),
                    subject_names.get(lesson.subject_id, lesson.subject_id),
                    teacher_names.get(lesson.teacher_id, lesson.teacher_id),
                )
            )

        teacher_counts = Counter(item.teacher_id for item in result.lessons)
        teacher_ids = sorted(teacher_names) if teacher_names else sorted(teacher_counts)
        for teacher_id in teacher_ids:
            sheets["教師別集計"].append(
                (teacher_id, teacher_names.get(teacher_id, teacher_id), teacher_counts[teacher_id])
            )
        lesson_counts = Counter((item.class_id, item.subject_id) for item in result.lessons)
        if data is not None:
            for requirement in data.lesson_requirements:
                generated = lesson_counts[(requirement.class_id, requirement.subject_id)]
                sheets["クラス教科別集計"].append(
                    (
                        requirement.class_id,
                        class_names.get(requirement.class_id, requirement.class_id),
                        requirement.subject_id,
                        subject_names.get(requirement.subject_id, requirement.subject_id),
                        requirement.required_periods,
                        generated,
                        generated - requirement.required_periods,
                    )
                )
        for issue in result.validation_report.issues:
            sheets["検証結果"].append(
                (issue.rule_id, issue.severity, issue.target, issue.message, issue.cell or "")
            )
        if not result.validation_report.issues:
            sheets["検証結果"].append(("ALL", "INFO", "-", "Hard Constraint違反なし", ""))
        settings_rows = (
            ("入力パス", str(result.request.input_path)),
            ("出力パス", str(result.request.output_path)),
            ("モード", data.settings.solve_mode.value if data else "UNKNOWN"),
            ("乱数シード", data.settings.random_seed if data else ""),
            ("探索上限秒", data.settings.max_solve_seconds if data else ""),
            ("アプリ状態", result.status),
            (
                "Solver状態",
                result.solver_statistics.status
                if result.solver_statistics is not None
                else "NOT_RUN",
            ),
            (
                "処理時間秒",
                result.solver_statistics.wall_time_seconds
                if result.solver_statistics is not None
                else 0,
            ),
            (
                "変数数",
                result.solver_statistics.variable_count
                if result.solver_statistics is not None
                else 0,
            ),
            (
                "適用rule_id",
                ",".join(result.solver_statistics.constraint_rule_ids)
                if result.solver_statistics is not None
                else "",
            ),
        )
        for row in settings_rows:
            sheets["実行条件"].append(row)
        for unplaced in result.unplaced_lessons:
            sheets["未配置授業"].append(
                (
                    unplaced.requirement_id,
                    unplaced.required_periods,
                    unplaced.generated_periods,
                    unplaced.shortage,
                    unplaced.reason,
                )
            )
        self._format_sheets(sheets.values())
        self._atomic_save(workbook, path)

    def _create_workbook(self) -> Workbook:
        if self._template_path is not None and self._template_path.is_file():
            return load_workbook(self._template_path)
        workbook = Workbook()
        default_sheet = workbook.active
        assert default_sheet is not None
        workbook.remove(default_sheet)
        for name, headers in self._sheet_headers.items():
            worksheet = workbook.create_sheet(name)
            self._write_header(worksheet, headers)
        return workbook

    def _write_header(self, worksheet: Worksheet, headers: tuple[str, ...]) -> None:
        worksheet.append(headers)
        for cell in worksheet[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="355A7A")
            cell.alignment = Alignment(horizontal="center")
        worksheet.freeze_panes = "A2"
        worksheet.auto_filter.ref = worksheet.dimensions

    def _format_sheets(self, worksheets: Iterable[Worksheet]) -> None:
        for worksheet in worksheets:
            for index, column in enumerate(worksheet.columns, start=1):
                max_length = max(len(str(cell.value or "")) for cell in column)
                worksheet.column_dimensions[get_column_letter(index)].width = min(
                    max_length + 2, 60
                )

    def _atomic_save(self, workbook: Workbook, path: Path) -> None:
        descriptor, temp_name = tempfile.mkstemp(
            prefix=f".{path.stem}-", suffix=".xlsx", dir=path.parent
        )
        os.close(descriptor)
        temp_path = Path(temp_name)
        completed = False
        try:
            workbook.save(temp_path)
            temp_path.replace(path)
            completed = True
        finally:
            if not completed and temp_path.exists():
                temp_path.unlink()

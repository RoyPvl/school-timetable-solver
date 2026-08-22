from __future__ import annotations

from dataclasses import replace

from school_timetable_solver.adapter.excel_input_router import CompatibleExcelInputReaderAdapter
from school_timetable_solver.adapter.excel_v2_reference_postprocessor import (
    ReferenceLabelExcelV2WorkbookPostprocessor,
)
from school_timetable_solver.adapter.excel_v2_workbook_adapter import ExcelV2WorkbookWriterAdapter
from school_timetable_solver.model.input_models import (
    InputDataModel,
    LessonCountPreferenceRuleSegmentModel,
    LessonCountRuleSegmentModel,
)
from school_timetable_solver.validator.input_validators import ReferenceIntegrityValidator


def test_v2_reader_generates_globally_unique_lesson_count_segment_ids(
    tmp_path,
    minimal_input_data: InputDataModel,
) -> None:
    requirement = next(item for item in minimal_input_data.lesson_requirements if item.enabled)
    target_date = next(day.target_date for day in minimal_input_data.calendar_days if day.output_enabled)
    period_id = minimal_input_data.periods[0].period_id

    hard_rules = (
        LessonCountRuleSegmentModel(
            "HARD_SOURCE_A",
            "SOURCE_SEG_A",
            "hard-a",
            True,
            requirement.class_id,
            requirement.subject_id,
            0,
            target_date,
            target_date,
            (period_id,),
        ),
        LessonCountRuleSegmentModel(
            "HARD_SOURCE_B",
            "SOURCE_SEG_B",
            "hard-b",
            True,
            requirement.class_id,
            requirement.subject_id,
            0,
            target_date,
            target_date,
            (period_id,),
        ),
    )
    soft_rules = (
        LessonCountPreferenceRuleSegmentModel(
            "SOFT_SOURCE_A",
            "SOURCE_SOFT_SEG_A",
            "soft-a",
            True,
            requirement.class_id,
            requirement.subject_id,
            0,
            target_date,
            target_date,
            (period_id,),
        ),
        LessonCountPreferenceRuleSegmentModel(
            "SOFT_SOURCE_B",
            "SOURCE_SOFT_SEG_B",
            "soft-b",
            True,
            requirement.class_id,
            requirement.subject_id,
            0,
            target_date,
            target_date,
            (period_id,),
        ),
    )
    source = replace(
        minimal_input_data,
        lesson_count_rule_segments=hard_rules,
        lesson_count_preference_rule_segments=soft_rules,
    )
    path = tmp_path / "segment_ids.xlsx"

    ExcelV2WorkbookWriterAdapter().write(path, source)
    ReferenceLabelExcelV2WorkbookPostprocessor().execute(path, source)
    result = CompatibleExcelInputReaderAdapter().read(path)

    assert result.input_data is not None, result.issues
    assert not [issue for issue in result.issues if issue.severity == "ERROR"]

    hard_segment_ids = [item.segment_id for item in result.input_data.lesson_count_rule_segments]
    soft_segment_ids = [
        item.segment_id for item in result.input_data.lesson_count_preference_rule_segments
    ]
    assert len(hard_segment_ids) == len(set(hard_segment_ids))
    assert len(soft_segment_ids) == len(set(soft_segment_ids))

    validation_issues = ReferenceIntegrityValidator().validate(result.input_data)
    duplicate_segment_issues = [
        issue
        for issue in validation_issues
        if issue.rule_id == "DUPLICATE_ID"
        and issue.target in set(hard_segment_ids + soft_segment_ids)
    ]
    assert duplicate_segment_issues == []

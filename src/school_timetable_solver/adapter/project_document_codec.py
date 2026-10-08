from __future__ import annotations

import json
from dataclasses import asdict

from school_timetable_solver.model.project_document_models import (
    DraftCalendarDayModel,
    DraftCampusModel,
    DraftClassModel,
    DraftClassPairOverlapRuleModel,
    DraftHomeroomBoundaryRuleModel,
    DraftLessonCountPreferenceRuleSegmentModel,
    DraftLessonCountRuleSegmentModel,
    DraftLessonRequirementModel,
    DraftPeriodModel,
    DraftPlacementRuleModel,
    DraftRoomModel,
    DraftSubjectModel,
    DraftTeacherDayOffRuleModel,
    DraftTeacherLeaveModel,
    DraftTeacherModel,
    ProjectDocumentModel,
)


def encode_project_document(document: ProjectDocumentModel) -> str:
    return json.dumps(asdict(document), ensure_ascii=False)


def decode_project_document(payload: str) -> ProjectDocumentModel:
    data = json.loads(payload)
    if (
        not isinstance(data, dict)
        or type(data.get("document_schema_version")) is not int
        or data.get("document_schema_version") != 1
    ):
        raise ValueError("未対応の保存データ形式です。元データは変更していません")
    return ProjectDocumentModel(
        document_schema_version=1,
        input_contract_version=_text(data, "input_contract_version"),
        revision=_revision(data),
        start_date=_text(data, "start_date"),
        end_date=_text(data, "end_date"),
        calendar_days=[
            DraftCalendarDayModel(
                target_date=_text(row, "target_date"),
                output_enabled=_boolean(row, "output_enabled"),
                enabled_period_ids=_text(row, "enabled_period_ids"),
                note=_text(row, "note"),
            )
            for row in _rows(data, "calendar_days")
        ],
        periods=[
            DraftPeriodModel(
                period_id=_text(row, "period_id"),
                period_name=_text(row, "period_name"),
                output_order=_text(row, "output_order"),
                start_time=_text(row, "start_time"),
                end_time=_text(row, "end_time"),
            )
            for row in _rows(data, "periods")
        ],
        campuses=[
            DraftCampusModel(
                campus_id=_text(row, "campus_id"),
                campus_name=_text(row, "campus_name"),
                output_order=_text(row, "output_order"),
                enabled=_boolean(row, "enabled"),
            )
            for row in _rows(data, "campuses")
        ],
        rooms=[
            DraftRoomModel(
                room_id=_text(row, "room_id"),
                room_name=_text(row, "room_name"),
                campus_id=_text(row, "campus_id"),
                output_order=_text(row, "output_order"),
                priority=_text(row, "priority"),
                enabled=_boolean(row, "enabled"),
            )
            for row in _rows(data, "rooms")
        ],
        teachers=[
            DraftTeacherModel(
                teacher_id=_text(row, "teacher_id"),
                teacher_name=_text(row, "teacher_name"),
                home_campus_id=_text(row, "home_campus_id"),
                enabled=_boolean(row, "enabled"),
            )
            for row in _rows(data, "teachers")
        ],
        classes=[
            DraftClassModel(
                class_id=_text(row, "class_id"),
                class_name=_text(row, "class_name"),
                campus_id=_text(row, "campus_id"),
                division=_text(row, "division"),
                grade=_text(row, "grade"),
                exam_category=_text(row, "exam_category"),
                homeroom_teacher_id=_text(row, "homeroom_teacher_id"),
                enabled=_boolean(row, "enabled"),
            )
            for row in _rows(data, "classes")
        ],
        subjects=[
            DraftSubjectModel(
                subject_id=_text(row, "subject_id"),
                subject_name=_text(row, "subject_name"),
                lesson_type=_text(row, "lesson_type"),
                enabled=_boolean(row, "enabled"),
            )
            for row in _rows(data, "subjects")
        ],
        lesson_requirements=[
            DraftLessonRequirementModel(
                requirement_id=_text(row, "requirement_id"),
                class_id=_text(row, "class_id"),
                subject_id=_text(row, "subject_id"),
                teacher_id=_text(row, "teacher_id"),
                required_periods=_text(row, "required_periods"),
                max_periods_per_day=_text(row, "max_periods_per_day"),
                enabled=_boolean(row, "enabled"),
            )
            for row in _rows(data, "lesson_requirements")
        ],
        teacher_leaves=[
            DraftTeacherLeaveModel(
                teacher_id=_text(row, "teacher_id"),
                target_date=_text(row, "target_date"),
                unavailable_period_ids=_text(row, "unavailable_period_ids"),
            )
            for row in _rows(data, "teacher_leaves")
        ],
        placement_rules=[
            DraftPlacementRuleModel(
                rule_id=_text(row, "rule_id"),
                rule_name=_text(row, "rule_name"),
                enabled=_boolean(row, "enabled"),
                constraint_type=_text(row, "constraint_type"),
                target_entity=_text(row, "target_entity"),
                condition_fields=_text(row, "condition_fields"),
                condition_operators=_text(row, "condition_operators"),
                condition_values=_text(row, "condition_values"),
                campus_id=_text(row, "campus_id"),
                start_date=_text(row, "start_date"),
                end_date=_text(row, "end_date"),
                weekdays=_text(row, "weekdays"),
                allowed_period_ids=_text(row, "allowed_period_ids"),
                daily_hard_limit=_text(row, "daily_hard_limit"),
                forbid_first_last_same_day=_text(row, "forbid_first_last_same_day"),
                attendance_streak_limit=_text(row, "attendance_streak_limit"),
                priority=_text(row, "priority"),
                preferred_attendance_streak_limit=_text(row, "preferred_attendance_streak_limit"),
                required_lesson_period_ids=_text(row, "required_lesson_period_ids"),
            )
            for row in _rows(data, "placement_rules")
        ],
        lesson_count_rule_segments=[
            DraftLessonCountRuleSegmentModel(
                rule_id=_text(row, "rule_id"),
                segment_id=_text(row, "segment_id"),
                rule_name=_text(row, "rule_name"),
                enabled=_boolean(row, "enabled"),
                class_id=_text(row, "class_id"),
                subject_id=_text(row, "subject_id"),
                exact_periods=_text(row, "exact_periods"),
                start_date=_text(row, "start_date"),
                end_date=_text(row, "end_date"),
                target_period_ids=_text(row, "target_period_ids"),
            )
            for row in _rows(data, "lesson_count_rule_segments")
        ],
        lesson_count_preference_rule_segments=[
            DraftLessonCountPreferenceRuleSegmentModel(
                rule_id=_text(row, "rule_id"),
                segment_id=_text(row, "segment_id"),
                rule_name=_text(row, "rule_name"),
                enabled=_boolean(row, "enabled"),
                class_id=_text(row, "class_id"),
                subject_id=_text(row, "subject_id"),
                preferred_periods=_text(row, "preferred_periods"),
                start_date=_text(row, "start_date"),
                end_date=_text(row, "end_date"),
                target_period_ids=_text(row, "target_period_ids"),
            )
            for row in _rows(data, "lesson_count_preference_rule_segments")
        ],
        teacher_day_off_rules=[
            DraftTeacherDayOffRuleModel(
                rule_id=_text(row, "rule_id"),
                teacher_id=_text(row, "teacher_id"),
                enabled=_boolean(row, "enabled"),
                eligible_dates=_text(row, "eligible_dates"),
                required_days_off=_text(row, "required_days_off"),
                minimum_days_off=_text(row, "minimum_days_off"),
                maximum_days_off=_text(row, "maximum_days_off"),
                quota_group_id=_text(row, "quota_group_id"),
                group_required_days_off=_text(row, "group_required_days_off"),
                preferred_days_off=_text(row, "preferred_days_off"),
            )
            for row in _rows(data, "teacher_day_off_rules")
        ],
        homeroom_boundary_rules=[
            DraftHomeroomBoundaryRuleModel(
                rule_id=_text(row, "rule_id"),
                rule_name=_text(row, "rule_name"),
                enabled=_boolean(row, "enabled"),
                condition_fields=_text(row, "condition_fields"),
                condition_operators=_text(row, "condition_operators"),
                condition_values=_text(row, "condition_values"),
                start_date=_text(row, "start_date"),
                end_date=_text(row, "end_date"),
            )
            for row in _rows(data, "homeroom_boundary_rules")
        ],
        class_pair_overlap_rules=[
            DraftClassPairOverlapRuleModel(
                rule_id=_text(row, "rule_id"),
                rule_name=_text(row, "rule_name"),
                enabled=_boolean(row, "enabled"),
                first_class_id=_text(row, "first_class_id"),
                second_class_id=_text(row, "second_class_id"),
            )
            for row in _rows(data, "class_pair_overlap_rules")
        ],
    )


def _text(row: dict[str, object], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str):
        raise ValueError(f"保存データの文字列が不正です: {key}")
    return value


def _boolean(row: dict[str, object], key: str) -> bool:
    value = row.get(key)
    if not isinstance(value, bool):
        raise ValueError(f"保存データの真偽値が不正です: {key}")
    return value


def _revision(row: dict[str, object]) -> int:
    value = row.get("revision")
    if type(value) is not int or value < 0:
        raise ValueError("保存データのrevisionが不正です")
    return value


def _rows(data: dict[str, object], key: str) -> list[dict[str, object]]:
    rows = data.get(key)
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError(f"保存データの一覧が不正です: {key}")
    return rows

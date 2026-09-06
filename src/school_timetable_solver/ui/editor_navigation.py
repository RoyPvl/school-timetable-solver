from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class EditorSection(StrEnum):
    SCHEDULE = "schedule"
    LESSON_COUNTS = "lesson_counts"
    TEACHER_ASSIGNMENTS = "teacher_assignments"
    TEACHER_LEAVES = "teacher_leaves"
    PLACEMENT_CONDITIONS = "placement_conditions"
    REVIEW = "review"
    MASTER = "master"


@dataclass(frozen=True, slots=True)
class EditorNavigationItem:
    section: EditorSection
    label: str
    maintenance_scope: str


SEASONAL_NAVIGATION = (
    EditorNavigationItem(EditorSection.SCHEDULE, "日程", "毎季"),
    EditorNavigationItem(EditorSection.LESSON_COUNTS, "授業回数", "毎季"),
    EditorNavigationItem(EditorSection.TEACHER_ASSIGNMENTS, "担当教師", "毎季"),
    EditorNavigationItem(EditorSection.TEACHER_LEAVES, "教師の休み", "毎季"),
    EditorNavigationItem(EditorSection.PLACEMENT_CONDITIONS, "配置条件", "毎季"),
    EditorNavigationItem(EditorSection.REVIEW, "入力確認", "毎季"),
)

COMMON_NAVIGATION = (
    EditorNavigationItem(EditorSection.MASTER, "マスタ管理", "共通設定"),
)

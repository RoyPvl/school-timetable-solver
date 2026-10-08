from school_timetable_solver.ui.editor_navigation import (
    COMMON_NAVIGATION,
    SEASONAL_NAVIGATION,
    EditorSection,
)


def test_seasonal_navigation_matches_maintenance_workflow() -> None:
    assert tuple(item.section for item in SEASONAL_NAVIGATION) == (
        EditorSection.SCHEDULE,
        EditorSection.LESSON_COUNTS,
        EditorSection.TEACHER_ASSIGNMENTS,
        EditorSection.TEACHER_LEAVES,
        EditorSection.PLACEMENT_CONDITIONS,
        EditorSection.REVIEW,
    )
    assert tuple(item.label for item in SEASONAL_NAVIGATION) == (
        "日程",
        "授業回数",
        "担当教師",
        "教師の休み",
        "配置条件",
        "入力確認",
    )
    assert all(item.maintenance_scope == "毎季" for item in SEASONAL_NAVIGATION)


def test_common_navigation_keeps_master_data_outside_seasonal_flow() -> None:
    assert len(COMMON_NAVIGATION) == 1
    item = COMMON_NAVIGATION[0]
    assert item.section is EditorSection.MASTER
    assert item.label == "マスタ管理"
    assert item.maintenance_scope == "共通設定"

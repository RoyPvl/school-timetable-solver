from __future__ import annotations

from dataclasses import dataclass, field

# Numeric, date and multi-value fields retain draft text until execution validation.


@dataclass(slots=True)
class DraftCampusModel:
    campus_id: str = ""
    campus_name: str = ""
    output_order: str = ""
    enabled: bool = True


@dataclass(slots=True)
class DraftRoomModel:
    room_id: str = ""
    room_name: str = ""
    campus_id: str = ""
    output_order: str = ""
    priority: str = ""
    enabled: bool = True


@dataclass(slots=True)
class DraftTeacherModel:
    teacher_id: str = ""
    teacher_name: str = ""
    home_campus_id: str = ""
    enabled: bool = True


@dataclass(slots=True)
class DraftClassModel:
    class_id: str = ""
    class_name: str = ""
    campus_id: str = ""
    division: str = ""
    grade: str = ""
    exam_category: str = ""
    homeroom_teacher_id: str = ""
    enabled: bool = True


@dataclass(slots=True)
class DraftSubjectModel:
    subject_id: str = ""
    subject_name: str = ""
    lesson_type: str = ""
    enabled: bool = True


@dataclass(slots=True)
class DraftPeriodModel:
    period_id: str = ""
    period_name: str = ""
    output_order: str = ""
    start_time: str = ""
    end_time: str = ""


@dataclass(slots=True)
class DraftCalendarDayModel:
    target_date: str = ""
    output_enabled: bool = True
    enabled_period_ids: str = ""
    note: str = ""


@dataclass(slots=True)
class DraftLessonRequirementModel:
    requirement_id: str = ""
    class_id: str = ""
    subject_id: str = ""
    teacher_id: str = ""
    required_periods: str = ""
    max_periods_per_day: str = ""
    enabled: bool = True


@dataclass(slots=True)
class DraftTeacherLeaveModel:
    teacher_id: str = ""
    target_date: str = ""
    unavailable_period_ids: str = ""


@dataclass(slots=True)
class DraftTeacherDayOffRuleModel:
    rule_id: str = ""
    teacher_id: str = ""
    enabled: bool = True
    eligible_dates: str = ""
    required_days_off: str = ""
    minimum_days_off: str = ""
    maximum_days_off: str = ""
    quota_group_id: str = ""
    group_required_days_off: str = ""
    preferred_days_off: str = ""


@dataclass(slots=True)
class DraftHomeroomBoundaryRuleModel:
    rule_id: str = ""
    rule_name: str = ""
    enabled: bool = True
    condition_fields: str = ""
    condition_operators: str = ""
    condition_values: str = ""
    start_date: str = ""
    end_date: str = ""


@dataclass(slots=True)
class DraftClassPairOverlapRuleModel:
    rule_id: str = ""
    rule_name: str = ""
    enabled: bool = True
    first_class_id: str = ""
    second_class_id: str = ""


@dataclass(slots=True)
class DraftPlacementRuleModel:
    rule_id: str = ""
    rule_name: str = ""
    enabled: bool = True
    constraint_type: str = ""
    target_entity: str = ""
    condition_fields: str = ""
    condition_operators: str = ""
    condition_values: str = ""
    campus_id: str = ""
    start_date: str = ""
    end_date: str = ""
    weekdays: str = ""
    allowed_period_ids: str = ""
    daily_hard_limit: str = ""
    forbid_first_last_same_day: str = ""
    attendance_streak_limit: str = ""
    priority: str = ""
    preferred_attendance_streak_limit: str = ""
    required_lesson_period_ids: str = ""


@dataclass(slots=True)
class DraftLessonCountRuleSegmentModel:
    rule_id: str = ""
    segment_id: str = ""
    rule_name: str = ""
    enabled: bool = True
    class_id: str = ""
    subject_id: str = ""
    exact_periods: str = ""
    start_date: str = ""
    end_date: str = ""
    target_period_ids: str = ""


@dataclass(slots=True)
class DraftLessonCountPreferenceRuleSegmentModel:
    rule_id: str = ""
    segment_id: str = ""
    rule_name: str = ""
    enabled: bool = True
    class_id: str = ""
    subject_id: str = ""
    preferred_periods: str = ""
    start_date: str = ""
    end_date: str = ""
    target_period_ids: str = ""


@dataclass(slots=True)
class ProjectDocumentModel:
    document_schema_version: int = 1
    input_contract_version: str = "1.1"
    revision: int = 0
    start_date: str = ""
    end_date: str = ""
    calendar_days: list[DraftCalendarDayModel] = field(default_factory=list)
    periods: list[DraftPeriodModel] = field(default_factory=list)
    campuses: list[DraftCampusModel] = field(default_factory=list)
    rooms: list[DraftRoomModel] = field(default_factory=list)
    teachers: list[DraftTeacherModel] = field(default_factory=list)
    classes: list[DraftClassModel] = field(default_factory=list)
    subjects: list[DraftSubjectModel] = field(default_factory=list)
    lesson_requirements: list[DraftLessonRequirementModel] = field(default_factory=list)
    teacher_leaves: list[DraftTeacherLeaveModel] = field(default_factory=list)
    placement_rules: list[DraftPlacementRuleModel] = field(default_factory=list)
    lesson_count_rule_segments: list[DraftLessonCountRuleSegmentModel] = field(default_factory=list)
    lesson_count_preference_rule_segments: list[DraftLessonCountPreferenceRuleSegmentModel] = field(
        default_factory=list
    )
    teacher_day_off_rules: list[DraftTeacherDayOffRuleModel] = field(default_factory=list)
    homeroom_boundary_rules: list[DraftHomeroomBoundaryRuleModel] = field(default_factory=list)
    class_pair_overlap_rules: list[DraftClassPairOverlapRuleModel] = field(default_factory=list)

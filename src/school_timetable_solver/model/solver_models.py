from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class EffectiveClassDateRuleModel:
    class_id: str
    target_date: date
    allowed_period_ids: tuple[str, ...] | None
    daily_hard_limit: int | None
    attendance_streak_limit: int | None
    applied_rule_ids: tuple[str, ...]
    preferred_attendance_streak_limit: int | None = None
    required_lesson_period_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class EffectiveTeacherDateRuleModel:
    teacher_id: str
    target_date: date
    daily_hard_limit: int | None
    forbid_first_last_same_day: bool | None
    applied_rule_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RuleResolutionIssueModel:
    rule_id: str
    target: str
    message: str


@dataclass(frozen=True, slots=True)
class ResolvedLessonCountRuleModel:
    rule_id: str
    requirement_id: str
    class_id: str
    subject_id: str
    exact_periods: int
    target_slots: tuple[tuple[date, str], ...]


@dataclass(frozen=True, slots=True)
class ResolvedLessonCountPreferenceRuleModel:
    rule_id: str
    requirement_id: str
    class_id: str
    subject_id: str
    preferred_periods: int
    target_slots: tuple[tuple[date, str], ...]


@dataclass(frozen=True, slots=True)
class ResolvedHomeroomBoundaryRuleModel:
    source_rule_id: str
    class_id: str
    campus_id: str
    teacher_id: str
    attendance_requirement_ids: tuple[str, ...]
    eligible_requirement_ids: tuple[str, ...]
    start_date: date
    end_date: date


@dataclass(frozen=True, slots=True)
class ResolvedRuleSetModel:
    class_date_rules: tuple[EffectiveClassDateRuleModel, ...]
    teacher_date_rules: tuple[EffectiveTeacherDateRuleModel, ...]
    issues: tuple[RuleResolutionIssueModel, ...] = ()
    lesson_count_rules: tuple[ResolvedLessonCountRuleModel, ...] = ()
    lesson_count_preference_rules: tuple[ResolvedLessonCountPreferenceRuleModel, ...] = ()
    homeroom_boundary_rules: tuple[ResolvedHomeroomBoundaryRuleModel, ...] = ()


@dataclass(frozen=True, slots=True)
class CandidateSlotModel:
    candidate_id: str
    requirement_id: str
    target_date: date
    period_id: str
    teacher_id: str
    campus_id: str
    class_id: str
    subject_id: str


@dataclass(frozen=True, slots=True)
class CandidateRejectionSummaryModel:
    requirement_id: str
    rule_id: str
    rejected_count: int


@dataclass(frozen=True, slots=True)
class CandidateBuildResultModel:
    candidates: tuple[CandidateSlotModel, ...]
    rejection_summaries: tuple[CandidateRejectionSummaryModel, ...]


@dataclass(frozen=True, slots=True)
class SolverStatisticsModel:
    status: str
    wall_time_seconds: float
    variable_count: int
    constraint_rule_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DayLevelAssignmentKeyModel:
    """One daily count fixed between the master and period subproblem."""

    requirement_id: str
    target_date: date
    teacher_id: str
    campus_id: str


@dataclass(frozen=True, slots=True)
class DayLevelMasterSolutionModel:
    """Values selected by one feasible day-level master solve."""

    assignment_counts: tuple[tuple[DayLevelAssignmentKeyModel, int], ...]
    teacher_day_offs: tuple[tuple[str, date, int], ...]


@dataclass(frozen=True, slots=True)
class DayLevelInfeasibilityCutModel:
    """Master equalities whose conjunction was proven infeasible by the subproblem."""

    assignment_counts: tuple[tuple[DayLevelAssignmentKeyModel, int], ...]
    teacher_day_offs: tuple[tuple[str, date, int], ...]


@dataclass(frozen=True, slots=True)
class DecompositionIterationStatisticsModel:
    iteration: int
    master_status: str
    master_wall_time_seconds: float
    subproblem_status: str
    subproblem_wall_time_seconds: float
    assumption_count: int
    infeasible_core_size: int
    cut_count: int

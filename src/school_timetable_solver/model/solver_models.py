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


@dataclass(frozen=True, slots=True)
class EffectiveTeacherDateRuleModel:
    teacher_id: str
    target_date: date
    daily_hard_limit: int | None
    consecutive_hard_limit: int | None
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
class ResolvedRuleSetModel:
    class_date_rules: tuple[EffectiveClassDateRuleModel, ...]
    teacher_date_rules: tuple[EffectiveTeacherDateRuleModel, ...]
    issues: tuple[RuleResolutionIssueModel, ...] = ()
    lesson_count_rules: tuple[ResolvedLessonCountRuleModel, ...] = ()


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

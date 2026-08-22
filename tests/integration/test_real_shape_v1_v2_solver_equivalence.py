from __future__ import annotations

import base64
import json
import zlib
from datetime import date, time
from pathlib import Path

from school_timetable_solver.constraint.hard_constraints import DEFAULT_HARD_CONSTRAINTS
from school_timetable_solver.constraint.soft_constraints import DEFAULT_SOFT_CONSTRAINTS
from school_timetable_solver.model.input_models import (
    CalendarDayModel,
    ClassPairOverlapRuleModel,
    GenerationMode,
    HomeroomBoundaryRuleModel,
    InputDataModel,
    InputWorkbookSettingsModel,
    LessonCountPreferenceRuleSegmentModel,
    LessonCountRuleSegmentModel,
    LessonRequirementModel,
    PlacementRuleModel,
    TeacherDayOffRuleModel,
    TeacherLeaveModel,
)
from school_timetable_solver.model.master_models import (
    CampusModel,
    ClassModel,
    PeriodModel,
    RoomModel,
    SubjectModel,
    TeacherModel,
)
from school_timetable_solver.model.result_models import GenerationRequestModel
from school_timetable_solver.service.planning_services import (
    CandidateBuilderService,
    RuleResolverService,
)
from school_timetable_solver.service.solver_service import TimetableSolverService
from school_timetable_solver.validator.input_validators import ReferenceIntegrityValidator

_FIXTURE_DIR = Path(__file__).parents[1] / "fixtures"


def _decode_scalar(value):
    if isinstance(value, dict) and set(value) == {"__date__"}:
        return date.fromisoformat(value["__date__"])
    if isinstance(value, dict) and set(value) == {"__time__"}:
        return time.fromisoformat(value["__time__"])
    if isinstance(value, list):
        return tuple(_decode_scalar(item) for item in value)
    return value


def _rows(raw, key, model):
    return tuple(model(**{name: _decode_scalar(value) for name, value in row.items()}) for row in raw[key])


def _load_fixture(name: str) -> InputDataModel:
    encoded = (_FIXTURE_DIR / name).read_text(encoding="utf-8").strip()
    raw = json.loads(zlib.decompress(base64.b64decode(encoded)))
    settings = InputWorkbookSettingsModel(**raw["settings"])
    return InputDataModel(
        settings=settings,
        calendar_days=_rows(raw, "calendar_days", CalendarDayModel),
        periods=_rows(raw, "periods", PeriodModel),
        campuses=_rows(raw, "campuses", CampusModel),
        rooms=_rows(raw, "rooms", RoomModel),
        teachers=_rows(raw, "teachers", TeacherModel),
        classes=_rows(raw, "classes", ClassModel),
        subjects=_rows(raw, "subjects", SubjectModel),
        lesson_requirements=_rows(raw, "lesson_requirements", LessonRequirementModel),
        teacher_leaves=_rows(raw, "teacher_leaves", TeacherLeaveModel),
        placement_rules=_rows(raw, "placement_rules", PlacementRuleModel),
        lesson_count_rule_segments=_rows(raw, "lesson_count_rule_segments", LessonCountRuleSegmentModel),
        lesson_count_preference_rule_segments=_rows(
            raw,
            "lesson_count_preference_rule_segments",
            LessonCountPreferenceRuleSegmentModel,
        ),
        teacher_day_off_rules=_rows(raw, "teacher_day_off_rules", TeacherDayOffRuleModel),
        homeroom_boundary_rules=_rows(raw, "homeroom_boundary_rules", HomeroomBoundaryRuleModel),
        class_pair_overlap_rules=_rows(raw, "class_pair_overlap_rules", ClassPairOverlapRuleModel),
    )


def _resolved_semantics(resolved):
    return (
        tuple(
            sorted(
                (
                    item.class_id,
                    item.target_date,
                    item.allowed_period_ids,
                    item.daily_hard_limit,
                    item.attendance_streak_limit,
                    item.preferred_attendance_streak_limit,
                    item.required_lesson_period_ids,
                )
                for item in resolved.class_date_rules
            )
        ),
        tuple(
            sorted(
                (
                    item.teacher_id,
                    item.target_date,
                    item.daily_hard_limit,
                    item.forbid_first_last_same_day,
                )
                for item in resolved.teacher_date_rules
            )
        ),
        tuple(
            sorted(
                (
                    item.requirement_id,
                    item.class_id,
                    item.subject_id,
                    item.exact_periods,
                    item.target_slots,
                )
                for item in resolved.lesson_count_rules
            )
        ),
        tuple(
            sorted(
                (
                    item.requirement_id,
                    item.class_id,
                    item.subject_id,
                    item.preferred_periods,
                    item.target_slots,
                )
                for item in resolved.lesson_count_preference_rules
            )
        ),
        tuple(
            sorted(
                (
                    item.class_id,
                    item.campus_id,
                    item.teacher_id,
                    item.attendance_requirement_ids,
                    item.eligible_requirement_ids,
                    item.start_date,
                    item.end_date,
                )
                for item in resolved.homeroom_boundary_rules
            )
        ),
        tuple(
            sorted(
                (
                    item.class_ids,
                    item.attendance_streak_limits,
                    item.preferred_attendance_streak_limits,
                )
                for item in resolved.attendance_groups
            )
        ),
    )


def _candidate_semantics(result):
    return tuple(
        sorted(
            (
                item.requirement_id,
                item.target_date,
                item.period_id,
                item.teacher_id,
                item.campus_id,
                item.class_id,
                item.subject_id,
            )
            for item in result.candidates
        )
    )


def _lesson_semantics(result):
    return tuple(
        (
            item.requirement_id,
            item.target_date,
            item.period_id,
            item.teacher_id,
            item.campus_id,
            item.class_id,
            item.subject_id,
            item.room_index,
        )
        for item in result.lessons
    )


def test_real_shape_v1_v2_have_identical_resolved_and_solver_results(tmp_path) -> None:
    """Regression fixture is an ID/name-anonymized bijection of the real summer input.

    It retains 29 teachers, 44 classes, 11 subjects, 178 requirements, all dates,
    placement rules, 188 hard lesson-count targets, 52 soft targets, day-off rules,
    homeroom rules, and duplicate-name topology. Only names/IDs are anonymized.
    """
    old_data = _load_fixture("solver_equivalence_old.b64")
    new_data = _load_fixture("solver_equivalence_new.b64")

    assert ReferenceIntegrityValidator().validate(old_data) == ()
    assert ReferenceIntegrityValidator().validate(new_data) == ()

    resolver = RuleResolverService()
    old_resolved = resolver.execute(old_data)
    new_resolved = resolver.execute(new_data)
    assert old_resolved.issues == ()
    assert new_resolved.issues == ()
    assert _resolved_semantics(old_resolved) == _resolved_semantics(new_resolved)

    builder = CandidateBuilderService()
    old_candidates = builder.execute(old_data, old_resolved)
    new_candidates = builder.execute(new_data, new_resolved)
    assert len(old_candidates.candidates) == 14073
    assert len(new_candidates.candidates) == 14073
    assert _candidate_semantics(old_candidates) == _candidate_semantics(new_candidates)
    assert old_candidates.rejection_summaries == new_candidates.rejection_summaries

    request = GenerationRequestModel(
        input_path=tmp_path / "fixture.xlsx",
        output_path=tmp_path / "out.xlsx",
        log_path=None,
        solve_mode=GenerationMode.STRICT,
        max_solve_seconds=60.0,
        random_seed=1,
        num_search_workers=1,
    )
    solver = TimetableSolverService(DEFAULT_HARD_CONSTRAINTS, DEFAULT_SOFT_CONSTRAINTS)
    old_result = solver.execute(request, old_data, old_resolved, old_candidates)
    new_result = solver.execute(request, new_data, new_resolved, new_candidates)

    assert old_result.statistics.status in {"OPTIMAL", "FEASIBLE"}
    assert new_result.statistics.status == old_result.statistics.status
    assert _lesson_semantics(new_result) == _lesson_semantics(old_result)
    assert new_result.teacher_day_offs == old_result.teacher_day_offs
    assert new_result.statistics.variable_count == old_result.statistics.variable_count

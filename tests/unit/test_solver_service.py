from __future__ import annotations

from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest
from ortools.sat.python import cp_model, cp_model_helper

from school_timetable_solver.constraint.hard_constraints import (
    DEFAULT_HARD_CONSTRAINTS,
    HomeroomBoundaryConstraint,
)
from school_timetable_solver.constraint.soft_constraints import (
    ClassSubjectDailyRepeatPreferenceConstraint,
)
from school_timetable_solver.model.input_models import (
    GenerationMode,
    HomeroomBoundaryRuleModel,
    InputDataModel,
)
from school_timetable_solver.model.result_models import GenerationRequestModel
from school_timetable_solver.model.solver_models import (
    CandidateBuildResultModel,
    ResolvedHomeroomBoundaryRuleModel,
    ResolvedRuleSetModel,
)
from school_timetable_solver.service.planning_services import (
    CandidateBuilderService,
    RuleResolverService,
)
from school_timetable_solver.service.solver_service import TimetableSolverService


@pytest.fixture
def solver_case(
    minimal_input_data: InputDataModel,
) -> tuple[InputDataModel, ResolvedRuleSetModel, CandidateBuildResultModel]:
    resolved_rules = RuleResolverService().execute(minimal_input_data)
    candidates = CandidateBuilderService().execute(minimal_input_data, resolved_rules)
    return minimal_input_data, resolved_rules, candidates


def test_lower_priority_reserve_ratio_preserves_total_reserve_when_phase_added() -> None:
    service = TimetableSolverService(())

    assert service._lower_priority_reserve_ratio(6) == pytest.approx(0.15)
    assert service._lower_priority_reserve_ratio(7) == pytest.approx(0.125)
    assert service._lower_priority_reserve_ratio(8) == pytest.approx(0.75 / 7)
    assert service._lower_priority_reserve_ratio(9) == pytest.approx(0.75 / 8)
    assert service._lower_priority_reserve_ratio(1) == 0.0


def test_homeroom_rule_batches_add_one_interval_at_a_time() -> None:
    rules = tuple(
        ResolvedHomeroomBoundaryRuleModel(
            f"HB_{class_index}_{interval_index}",
            f"CL{class_index:02d}",
            f"T{class_index:02d}",
            date(2026, 7, 18),
            date(2026, 8, 6),
        )
        for class_index in range(12)
        for interval_index in range(2)
    )

    batches = TimetableSolverService(())._homeroom_rule_batches(rules)

    assert len(batches) == 24
    assert all(len(batch) == 1 for batch in batches)
    assert [batch[0].rule_id for batch in batches[:2]] == ["HB_0_0", "HB_0_1"]


def test_homeroom_anchor_matching_uses_distinct_teacher_periods() -> None:
    matched = TimetableSolverService(())._match_homeroom_anchor_requests(
        [
            ("HB1", (("P1", "CANDIDATE_1"), ("P2", "CANDIDATE_2"))),
            ("HB2", (("P1", "CANDIDATE_3"),)),
        ]
    )

    assert set(matched) == {"CANDIDATE_2", "CANDIDATE_3"}


def test_homeroom_local_repair_expands_from_homeroom_to_all_class_teachers(
    solver_case: tuple[InputDataModel, ResolvedRuleSetModel, CandidateBuildResultModel],
) -> None:
    input_data, resolved_rules, candidates = solver_case
    service = TimetableSolverService(())
    context, _ = service._build_solver_context(input_data, resolved_rules, candidates)
    batch = (
        ResolvedHomeroomBoundaryRuleModel(
            "HB1",
            "CL2",
            "T2",
            date(2026, 7, 27),
            date(2026, 7, 28),
        ),
    )

    local_ids = service._homeroom_mutable_candidate_ids(
        context,
        batch,
        include_all_target_class_teachers=False,
    )
    expanded_ids = service._homeroom_mutable_candidate_ids(
        context,
        batch,
        include_all_target_class_teachers=True,
    )
    related_class_ids = service._homeroom_mutable_candidate_ids(
        context,
        batch,
        include_all_target_class_teachers=False,
        include_target_teacher_classes=True,
    )
    dependency_depth_zero_ids = service._homeroom_dependency_candidate_ids(
        context,
        batch,
        0,
    )
    dependency_depth_one_ids = service._homeroom_dependency_candidate_ids(
        context,
        batch,
        1,
    )
    class_teacher_ids = {
        candidate.teacher_id for candidate in candidates.candidates if candidate.class_id == "CL2"
    }
    classes_taught_by_class_teachers = {
        candidate.class_id
        for candidate in candidates.candidates
        if candidate.teacher_id in class_teacher_ids
    }

    assert local_ids == {
        candidate.candidate_id
        for candidate in candidates.candidates
        if candidate.class_id == "CL2" or candidate.teacher_id == "T2"
    }
    assert expanded_ids == {
        candidate.candidate_id
        for candidate in candidates.candidates
        if candidate.class_id == "CL2" or candidate.teacher_id in class_teacher_ids
    }
    assert related_class_ids == {
        candidate.candidate_id
        for candidate in candidates.candidates
        if candidate.class_id in classes_taught_by_class_teachers
        or candidate.teacher_id in class_teacher_ids
    }
    assert local_ids <= expanded_ids <= related_class_ids
    assert dependency_depth_zero_ids == local_ids
    assert dependency_depth_one_ids == related_class_ids


def test_full_homeroom_search_restarts_with_different_random_seeds(
    solver_case: tuple[InputDataModel, ResolvedRuleSetModel, CandidateBuildResultModel],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_data, resolved_rules, candidates = solver_case
    service = TimetableSolverService(())
    context, _ = service._build_solver_context(input_data, resolved_rules, candidates)
    rule = ResolvedHomeroomBoundaryRuleModel(
        "HB1",
        "CL2",
        "T2",
        date(2026, 7, 27),
        date(2026, 7, 28),
    )
    context.homeroom_boundary_rules = (rule,)
    HomeroomBoundaryConstraint().apply(context)
    request = GenerationRequestModel(
        tmp_path / "input.xlsx",
        tmp_path / "output.xlsx",
        None,
        GenerationMode.STRICT,
        100.0,
        1,
        1,
    )
    statuses = iter((cp_model.UNKNOWN, cp_model.FEASIBLE))
    seed_offsets: list[int] = []
    fixed_hint_flags: list[bool] = []
    hint_counts: list[int] = []

    class StubSolver:
        wall_time = 1.0

        def __init__(self, status: cp_model_helper.CpSolverStatus) -> None:
            self._status = status

        def solve(self, model: cp_model.CpModel) -> cp_model_helper.CpSolverStatus:
            hint_counts.append(len(model.proto.solution_hint.vars))
            return self._status

        def status_name(self, status: cp_model_helper.CpSolverStatus) -> str:
            return str(status).rsplit(".", maxsplit=1)[-1]

    def create_stub_solver(
        current_request: GenerationRequestModel,
        max_solve_seconds: float,
        *,
        fix_hinted_variables: bool = False,
        random_seed_offset: int = 0,
    ) -> StubSolver:
        assert current_request is request
        assert max_solve_seconds > 0
        seed_offsets.append(random_seed_offset)
        fixed_hint_flags.append(fix_hinted_variables)
        return StubSolver(next(statuses))

    monkeypatch.setattr(service, "_new_solver", create_stub_solver)

    _, status, wall_time = service._solve_full_homeroom_with_restarts(
        request,
        context,
        (rule,),
        None,
        0,
        100.0,
    )

    assert status == "FEASIBLE"
    assert wall_time == 2.0
    assert seed_offsets == [0, 1]
    assert fixed_hint_flags == [True, True]
    assert all(hint_count > 0 for hint_count in hint_counts)


def test_initial_feasible_solution_is_hinted_to_first_soft_phase(
    solver_case: tuple[InputDataModel, ResolvedRuleSetModel, CandidateBuildResultModel],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_data, resolved_rules, candidates = solver_case
    input_data = replace(
        input_data,
        homeroom_boundary_rules=(
            HomeroomBoundaryRuleModel(
                "HB1",
                "初終登校日",
                True,
                "CL2",
                date(2026, 7, 27),
                date(2026, 7, 28),
            ),
        ),
    )
    resolved_rules = RuleResolverService().execute(input_data)
    candidates = CandidateBuilderService().execute(input_data, resolved_rules)
    request = GenerationRequestModel(
        tmp_path / "input.xlsx",
        tmp_path / "output.xlsx",
        None,
        GenerationMode.STRICT,
        5.0,
        1,
        1,
    )
    observed_models: list[tuple[bool, int]] = []
    original_solve = cp_model.CpSolver.solve

    def record_model_before_solve(
        solver: cp_model.CpSolver,
        model: cp_model.CpModel,
        solution_callback: cp_model.CpSolverSolutionCallback | None = None,
    ) -> cp_model_helper.CpSolverStatus:
        observed_models.append(
            (
                model.has_objective(),
                len(model.proto.solution_hint.vars),
            )
        )
        return original_solve(solver, model, solution_callback)

    monkeypatch.setattr(cp_model.CpSolver, "solve", record_model_before_solve)
    result = TimetableSolverService(
        DEFAULT_HARD_CONSTRAINTS,
        (ClassSubjectDailyRepeatPreferenceConstraint(),),
    ).execute(
        request,
        input_data,
        resolved_rules,
        candidates,
    )

    assert result.statistics.status in {"OPTIMAL", "FEASIBLE"}
    assert observed_models[0] == (False, 0)
    assert observed_models[1][0] is False
    assert observed_models[1][1] > 0
    assert observed_models[2][0]
    assert observed_models[2][1] > 0
    assert result.statistics.constraint_rule_ids[: len(DEFAULT_HARD_CONSTRAINTS)] == tuple(
        constraint.rule_id for constraint in DEFAULT_HARD_CONSTRAINTS
    )


def test_initial_feasible_solution_is_not_returned_when_first_soft_phase_fails(
    solver_case: tuple[InputDataModel, ResolvedRuleSetModel, CandidateBuildResultModel],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_data, resolved_rules, candidates = solver_case
    request = GenerationRequestModel(
        tmp_path / "input.xlsx",
        tmp_path / "output.xlsx",
        None,
        GenerationMode.STRICT,
        10.0,
        1,
        1,
    )

    class StubSolver:
        def __init__(
            self,
            status: cp_model_helper.CpSolverStatus,
            wall_time: float,
        ) -> None:
            self._status = status
            self.wall_time = wall_time

        def solve(self, model: cp_model.CpModel) -> cp_model_helper.CpSolverStatus:
            return self._status

        def status_name(self, status: cp_model_helper.CpSolverStatus) -> str:
            return str(status).rsplit(".", maxsplit=1)[-1]

        def value(self, variable: cp_model.IntVar) -> int:
            return 0

    stub_solvers = iter(
        (
            StubSolver(cp_model.OPTIMAL, 1.0),
            StubSolver(cp_model.UNKNOWN, 1.0),
        )
    )
    phase_budgets: list[float] = []

    def create_stub_solver(
        current_request: GenerationRequestModel,
        max_solve_seconds: float,
    ) -> StubSolver:
        assert current_request is request
        phase_budgets.append(max_solve_seconds)
        return next(stub_solvers)

    service = TimetableSolverService(
        DEFAULT_HARD_CONSTRAINTS,
        (ClassSubjectDailyRepeatPreferenceConstraint(),),
    )
    monkeypatch.setattr(service, "_new_solver", create_stub_solver)
    result = service.execute(
        request,
        input_data,
        resolved_rules,
        candidates,
    )

    assert result.statistics.status == "UNKNOWN"
    assert not result.lessons
    assert result.statistics.wall_time_seconds == 2.0
    assert phase_budgets == pytest.approx([10.0, 9.0])

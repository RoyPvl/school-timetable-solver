from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from ortools.sat.python import cp_model, cp_model_helper

from school_timetable_solver.constraint.hard_constraints import DEFAULT_HARD_CONSTRAINTS
from school_timetable_solver.constraint.soft_constraints import (
    ClassSubjectDailyRepeatPreferenceConstraint,
)
from school_timetable_solver.model.input_models import GenerationMode, InputDataModel
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


def test_homeroom_rules_reserve_sixty_percent_for_initial_feasibility(
    solver_case: tuple[InputDataModel, ResolvedRuleSetModel, CandidateBuildResultModel],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_data, resolved_rules, candidates = solver_case
    resolved_rules = replace(
        resolved_rules,
        homeroom_boundary_rules=(
            ResolvedHomeroomBoundaryRuleModel(
                "HB1",
                "CL2",
                "C2",
                "T2",
                ("Q2",),
                ("Q2",),
                input_data.calendar_days[0].target_date,
                input_data.calendar_days[1].target_date,
            ),
        ),
    )
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
        wall_time = 1.0

        def solve(self, model: cp_model.CpModel) -> cp_model_helper.CpSolverStatus:
            return cp_model.OPTIMAL

        def status_name(self, status: cp_model_helper.CpSolverStatus) -> str:
            return str(status).rsplit(".", maxsplit=1)[-1]

        def value(self, variable: cp_model.IntVar) -> int:
            return 0

    phase_budgets: list[float] = []

    def create_stub_solver(
        current_request: GenerationRequestModel,
        max_solve_seconds: float,
    ) -> StubSolver:
        assert current_request is request
        phase_budgets.append(max_solve_seconds)
        return StubSolver()

    class DiagnosticPreference:
        optimization_scope = "assignment"

        def __init__(self, priority: int) -> None:
            self.priority = priority
            self.rule_id = f"TEST_{priority}"

        def apply(self, context: object) -> None:
            return None

    service = TimetableSolverService(
        DEFAULT_HARD_CONSTRAINTS,
        (DiagnosticPreference(2), DiagnosticPreference(1)),  # type: ignore[arg-type]
    )
    monkeypatch.setattr(service, "_new_solver", create_stub_solver)

    service.execute(request, input_data, resolved_rules, candidates)

    assert phase_budgets[0] == pytest.approx(6.0)


def test_initial_feasible_solution_is_hinted_to_first_soft_phase(
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
    assert observed_models[1][1] == len(candidates.candidates)
    assert observed_models[2][0]
    assert observed_models[2][1] > 0
    assert result.statistics.constraint_rule_ids[: len(DEFAULT_HARD_CONSTRAINTS)] == tuple(
        constraint.rule_id for constraint in DEFAULT_HARD_CONSTRAINTS
    )


def test_h20_is_applied_before_preliminary_solve_and_only_h16_is_deferred() -> None:
    assert frozenset({"H16"}) == TimetableSolverService._PRELIMINARY_DEFERRED_HARD_RULE_IDS


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
    assert result.statistics.wall_time_seconds == 3.0
    assert phase_budgets == pytest.approx([10.0, 9.0, 8.0])


def test_soft_phases_are_not_run_when_initial_hard_model_is_infeasible(
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
        def __init__(self, status: cp_model_helper.CpSolverStatus) -> None:
            self._status = status
            self.wall_time = 1.0

        def solve(self, model: cp_model.CpModel) -> cp_model_helper.CpSolverStatus:
            return self._status

        def status_name(self, status: cp_model_helper.CpSolverStatus) -> str:
            return str(status).rsplit(".", maxsplit=1)[-1]

        def value(self, variable: cp_model.IntVar) -> int:
            return 0

    stub_solvers = iter((StubSolver(cp_model.OPTIMAL), StubSolver(cp_model.INFEASIBLE)))
    phase_budgets: list[float] = []
    service = TimetableSolverService(
        DEFAULT_HARD_CONSTRAINTS,
        (ClassSubjectDailyRepeatPreferenceConstraint(),),
    )

    def create_stub_solver(
        current_request: GenerationRequestModel,
        max_solve_seconds: float,
    ) -> StubSolver:
        assert current_request is request
        phase_budgets.append(max_solve_seconds)
        return next(stub_solvers)

    monkeypatch.setattr(service, "_new_solver", create_stub_solver)
    result = service.execute(request, input_data, resolved_rules, candidates)

    assert result.statistics.status == "INFEASIBLE"
    assert not result.lessons
    assert result.statistics.wall_time_seconds == 2.0
    assert phase_budgets == pytest.approx([10.0, 9.0])

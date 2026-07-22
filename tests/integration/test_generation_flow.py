from __future__ import annotations

from pathlib import Path

from school_timetable_solver.adapter.excel_input_adapter import ExcelInputReaderAdapter
from school_timetable_solver.constraint.hard_constraints import DEFAULT_HARD_CONSTRAINTS
from school_timetable_solver.service.planning_services import (
    CandidateBuilderService,
    RuleResolverService,
)
from school_timetable_solver.service.result_services import ValidateResultService
from school_timetable_solver.service.solver_service import TimetableSolverService
from school_timetable_solver.validator.input_validators import DEFAULT_INPUT_VALIDATORS


def test_real_excel_can_flow_through_models_solver_and_independent_validation() -> None:
    read_result = ExcelInputReaderAdapter().read(
        Path("projects/sample/input/時間割入力_サンプル.xlsx")
    )
    assert read_result.input_data is not None
    input_data = read_result.input_data
    assert not [
        issue for validator in DEFAULT_INPUT_VALIDATORS for issue in validator.validate(input_data)
    ]

    resolved = RuleResolverService().execute(input_data)
    candidates = CandidateBuilderService().execute(input_data, resolved)
    solver_result = TimetableSolverService(DEFAULT_HARD_CONSTRAINTS).execute(
        input_data, resolved, candidates
    )
    report = ValidateResultService().execute(input_data, resolved, solver_result.lessons)

    assert solver_result.statistics.status in {"OPTIMAL", "FEASIBLE"}
    assert solver_result.lessons
    assert report.issues == ()

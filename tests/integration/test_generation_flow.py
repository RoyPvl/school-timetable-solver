from __future__ import annotations

from pathlib import Path

from school_timetable_solver.adapter.excel_input_adapter import ExcelInputReaderAdapter
from school_timetable_solver.constraint.hard_constraints import DEFAULT_HARD_CONSTRAINTS
from school_timetable_solver.model.input_models import GenerationMode
from school_timetable_solver.model.result_models import GenerationRequestModel
from school_timetable_solver.service.planning_services import (
    CandidateBuilderService,
    RuleResolverService,
)
from school_timetable_solver.service.result_services import (
    AssignRoomsService,
    BuildTimetableDocumentService,
    ValidateResultService,
)
from school_timetable_solver.service.solver_service import TimetableSolverService
from school_timetable_solver.validator.input_validators import (
    DEFAULT_INPUT_VALIDATORS,
    CapacityFeasibilityValidator,
)


def test_real_excel_flows_through_validation_solver_result_and_document() -> None:
    path = Path("projects/sample/input/時間割入力_サンプル.xlsx")
    read_result = ExcelInputReaderAdapter().read(path)
    assert read_result.input_data is not None
    input_data = read_result.input_data
    assert not [
        issue for validator in DEFAULT_INPUT_VALIDATORS for issue in validator.validate(input_data)
    ]
    resolved = RuleResolverService().execute(input_data)
    assert not resolved.issues
    candidates = CandidateBuilderService().execute(input_data, resolved)
    assert not CapacityFeasibilityValidator().validate(
        input_data,
        resolved,
        candidates,
    )
    request = GenerationRequestModel(
        path,
        Path("unused.xlsx"),
        None,
        GenerationMode.STRICT,
        10.0,
        1,
        1,
    )
    solver_result = TimetableSolverService(DEFAULT_HARD_CONSTRAINTS).execute(
        request,
        input_data,
        resolved,
        candidates,
    )
    lessons = AssignRoomsService().execute(input_data, solver_result.lessons)
    report = ValidateResultService().execute(
        input_data,
        resolved,
        lessons,
    )
    document = BuildTimetableDocumentService().execute(
        input_data,
        lessons,
    )

    assert solver_result.statistics.status in {"OPTIMAL", "FEASIBLE"}
    assert len(lessons) == 4
    assert not report.issues
    assert len(document.dates) == 3

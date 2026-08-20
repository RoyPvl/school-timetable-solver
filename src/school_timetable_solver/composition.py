from __future__ import annotations

from pathlib import Path

from school_timetable_solver.adapter.excel_input_router import CompatibleExcelInputReaderAdapter
from school_timetable_solver.adapter.excel_output_adapter import ExcelTimetableWriterAdapter
from school_timetable_solver.adapter.execution_log_adapter import ExecutionLogAdapter
from school_timetable_solver.constraint.hard_constraints import DEFAULT_HARD_CONSTRAINTS
from school_timetable_solver.constraint.soft_constraints import DEFAULT_SOFT_CONSTRAINTS
from school_timetable_solver.service.generation_services import (
    GenerateTimetableService,
    ValidateInputService,
)
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


class ApplicationComposition:
    """Create fully wired application use cases."""

    def create_validate_input_service(
        self,
        log_path: Path | None = None,
    ) -> ValidateInputService:
        ExecutionLogAdapter().configure(log_path)
        return ValidateInputService(
            input_reader=CompatibleExcelInputReaderAdapter(),
            validators=DEFAULT_INPUT_VALIDATORS,
            rule_resolver=RuleResolverService(),
            candidate_builder=CandidateBuilderService(),
            capacity_validator=CapacityFeasibilityValidator(),
        )

    def create_generate_timetable_service(
        self,
        log_path: Path | None = None,
    ) -> GenerateTimetableService:
        ExecutionLogAdapter().configure(log_path)
        return GenerateTimetableService(
            input_reader=CompatibleExcelInputReaderAdapter(),
            validators=DEFAULT_INPUT_VALIDATORS,
            rule_resolver=RuleResolverService(),
            candidate_builder=CandidateBuilderService(),
            capacity_validator=CapacityFeasibilityValidator(),
            solver_service=TimetableSolverService(
                DEFAULT_HARD_CONSTRAINTS,
                DEFAULT_SOFT_CONSTRAINTS,
            ),
            room_assigner=AssignRoomsService(),
            result_validator=ValidateResultService(),
            document_builder=BuildTimetableDocumentService(),
            output_writer=ExcelTimetableWriterAdapter(),
        )

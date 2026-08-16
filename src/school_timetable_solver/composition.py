from __future__ import annotations

from pathlib import Path

from school_timetable_solver.adapter.excel_input_adapter import ExcelInputReaderAdapter
from school_timetable_solver.adapter.excel_output_adapter import ExcelTimetableWriterAdapter
from school_timetable_solver.adapter.execution_log_adapter import ExecutionLogAdapter
from school_timetable_solver.constraint.hard_constraints import DEFAULT_HARD_CONSTRAINTS
from school_timetable_solver.constraint.soft_constraints import DEFAULT_SOFT_CONSTRAINTS
from school_timetable_solver.constraint.successor_constraints import (
    ClassSuccessorConstraint,
    SuccessorAwareRoomChangeGapPreferenceConstraint,
    SuccessorAwareScheduleBalancePreferenceConstraint,
    SuccessorAwareSingleLessonDayPreferenceConstraint,
)
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
)
from school_timetable_solver.service.successor_services import (
    SuccessorCapacityFeasibilityValidator,
    SuccessorTimetableSolverService,
    SuccessorValidateResultService,
)
from school_timetable_solver.validator.input_validators import DEFAULT_INPUT_VALIDATORS


SUCCESSOR_HARD_CONSTRAINTS = (*DEFAULT_HARD_CONSTRAINTS, ClassSuccessorConstraint())
SUCCESSOR_SOFT_CONSTRAINTS = (
    *(
        constraint
        for constraint in DEFAULT_SOFT_CONSTRAINTS
        if constraint.rule_id not in {"S10", "S12", "S16"}
    ),
    SuccessorAwareRoomChangeGapPreferenceConstraint(),
    SuccessorAwareSingleLessonDayPreferenceConstraint(),
    SuccessorAwareScheduleBalancePreferenceConstraint(),
)


class ApplicationComposition:
    """Create fully wired application use cases."""

    def create_validate_input_service(
        self,
        log_path: Path | None = None,
    ) -> ValidateInputService:
        ExecutionLogAdapter().configure(log_path)
        return ValidateInputService(
            input_reader=ExcelInputReaderAdapter(),
            validators=DEFAULT_INPUT_VALIDATORS,
            rule_resolver=RuleResolverService(),
            candidate_builder=CandidateBuilderService(),
            capacity_validator=SuccessorCapacityFeasibilityValidator(),
        )

    def create_generate_timetable_service(
        self,
        log_path: Path | None = None,
    ) -> GenerateTimetableService:
        ExecutionLogAdapter().configure(log_path)
        return GenerateTimetableService(
            input_reader=ExcelInputReaderAdapter(),
            validators=DEFAULT_INPUT_VALIDATORS,
            rule_resolver=RuleResolverService(),
            candidate_builder=CandidateBuilderService(),
            capacity_validator=SuccessorCapacityFeasibilityValidator(),
            solver_service=SuccessorTimetableSolverService(
                SUCCESSOR_HARD_CONSTRAINTS,
                SUCCESSOR_SOFT_CONSTRAINTS,
            ),
            room_assigner=AssignRoomsService(),
            result_validator=SuccessorValidateResultService(),
            document_builder=BuildTimetableDocumentService(),
            output_writer=ExcelTimetableWriterAdapter(),
        )

from __future__ import annotations

from pathlib import Path

from school_timetable_solver.adapter.excel_input_adapter import ExcelInputReaderAdapter
from school_timetable_solver.adapter.excel_output_adapter import ExcelTimetableWriterAdapter
from school_timetable_solver.adapter.execution_log_adapter import ExecutionLogAdapter
from school_timetable_solver.constraint.hard_constraints import DEFAULT_HARD_CONSTRAINTS
from school_timetable_solver.service.generation_services import (
    GenerateTimetableService,
    ValidateInputService,
)
from school_timetable_solver.service.planning_services import (
    CandidateBuilderService,
    RuleResolverService,
)
from school_timetable_solver.service.result_services import ValidateResultService
from school_timetable_solver.service.solver_service import TimetableSolverService
from school_timetable_solver.validator.input_validators import DEFAULT_INPUT_VALIDATORS


class ApplicationComposition:
    """Create fully wired application use cases."""

    def create_validate_input_service(self, log_path: Path | None = None) -> ValidateInputService:
        ExecutionLogAdapter().configure(log_path)
        return ValidateInputService(
            ExcelInputReaderAdapter(),
            DEFAULT_INPUT_VALIDATORS,
            ExcelTimetableWriterAdapter(self._output_template_path()),
        )

    def create_generate_timetable_service(
        self, log_path: Path | None = None
    ) -> GenerateTimetableService:
        ExecutionLogAdapter().configure(log_path)
        return GenerateTimetableService(
            input_reader=ExcelInputReaderAdapter(),
            validators=DEFAULT_INPUT_VALIDATORS,
            rule_resolver=RuleResolverService(),
            candidate_builder=CandidateBuilderService(),
            solver_service=TimetableSolverService(DEFAULT_HARD_CONSTRAINTS),
            result_validator=ValidateResultService(),
            output_writer=ExcelTimetableWriterAdapter(self._output_template_path()),
        )

    def _output_template_path(self) -> Path:
        return Path(__file__).resolve().parents[2] / "templates" / "時間割出力テンプレート.xlsx"

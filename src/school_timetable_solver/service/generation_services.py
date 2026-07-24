from __future__ import annotations

import logging

from school_timetable_solver.model.input_models import GenerationMode, InputDataModel
from school_timetable_solver.model.result_models import (
    GenerationRequestModel,
    GenerationResultModel,
    ScheduledLessonModel,
    ValidationIssueModel,
    ValidationReportModel,
)
from school_timetable_solver.model.solver_models import SolverStatisticsModel
from school_timetable_solver.service.planning_services import (
    CandidateBuilderService,
    RuleResolverService,
)
from school_timetable_solver.service.protocols import InputReader, TimetableWriter
from school_timetable_solver.service.result_services import (
    AssignRoomsService,
    BuildTimetableDocumentService,
    ValidateResultService,
)
from school_timetable_solver.service.solver_service import TimetableSolverService
from school_timetable_solver.validator.input_validators import (
    CapacityFeasibilityValidator,
    InputValidator,
)

LOGGER = logging.getLogger(__name__)


class ValidateInputService:
    """Read, validate, resolve rules, and detect obvious supply shortages."""

    def __init__(
        self,
        input_reader: InputReader,
        validators: tuple[InputValidator, ...],
        rule_resolver: RuleResolverService,
        candidate_builder: CandidateBuilderService,
        capacity_validator: CapacityFeasibilityValidator,
    ) -> None:
        self._input_reader = input_reader
        self._validators = validators
        self._rule_resolver = rule_resolver
        self._candidate_builder = candidate_builder
        self._capacity_validator = capacity_validator

    def execute(self, request: GenerationRequestModel) -> GenerationResultModel:
        read_result = self._input_reader.read(request.input_path)
        issues = list(read_result.issues)
        for issue in issues:
            if issue.severity == "WARNING":
                LOGGER.warning("%s target=%s %s", issue.rule_id, issue.target, issue.message)
        input_data = read_result.input_data
        if input_data is not None and not self._has_errors(issues):
            for validator in self._validators:
                issues.extend(validator.validate(input_data))
        if input_data is not None and not self._has_errors(issues):
            resolved_rules = self._rule_resolver.execute(input_data)
            issues.extend(
                ValidationIssueModel(issue.rule_id, "ERROR", issue.target, issue.message)
                for issue in resolved_rules.issues
            )
            if not self._has_errors(issues):
                candidates = self._candidate_builder.execute(input_data, resolved_rules)
                issues.extend(
                    self._capacity_validator.validate(
                        input_data,
                        resolved_rules,
                        candidates,
                    )
                )
        has_errors = self._has_errors(issues)
        return GenerationResultModel(
            status="INPUT_ERROR" if has_errors else "VALIDATED",
            exit_code=2 if has_errors else 0,
            request=request,
            input_data=input_data,
            lessons=(),
            validation_report=ValidationReportModel(tuple(issues)),
            solver_statistics=None,
        )

    def _has_errors(self, issues: list[ValidationIssueModel]) -> bool:
        return any(issue.severity == "ERROR" for issue in issues)


class GenerateTimetableService:
    """Coordinate validation, strict solving, independent verification, and output."""

    def __init__(
        self,
        input_reader: InputReader,
        validators: tuple[InputValidator, ...],
        rule_resolver: RuleResolverService,
        candidate_builder: CandidateBuilderService,
        capacity_validator: CapacityFeasibilityValidator,
        solver_service: TimetableSolverService,
        room_assigner: AssignRoomsService,
        result_validator: ValidateResultService,
        document_builder: BuildTimetableDocumentService,
        output_writer: TimetableWriter,
    ) -> None:
        self._input_reader = input_reader
        self._validators = validators
        self._rule_resolver = rule_resolver
        self._candidate_builder = candidate_builder
        self._capacity_validator = capacity_validator
        self._solver_service = solver_service
        self._room_assigner = room_assigner
        self._result_validator = result_validator
        self._document_builder = document_builder
        self._output_writer = output_writer

    def execute(self, request: GenerationRequestModel) -> GenerationResultModel:
        LOGGER.info(
            (
                "実行開始 input=%s output=%s mode=%s max_seconds=%s "
                "random_seed=%s num_search_workers=%s"
            ),
            request.input_path,
            request.output_path,
            request.solve_mode.value,
            request.max_solve_seconds,
            request.random_seed,
            request.num_search_workers,
        )
        if request.input_path.resolve() == request.output_path.resolve():
            return self._result(
                request,
                None,
                "INPUT_ERROR",
                2,
                [
                    ValidationIssueModel(
                        "INPUT_OUTPUT_PATH_CONFLICT",
                        "ERROR",
                        str(request.input_path),
                        "入力ファイルと出力ファイルに同じパスは指定できません",
                    )
                ],
            )
        read_result = self._input_reader.read(request.input_path)
        issues = list(read_result.issues)
        for issue in issues:
            if issue.severity == "WARNING":
                LOGGER.warning("%s target=%s %s", issue.rule_id, issue.target, issue.message)
        input_data = read_result.input_data
        if input_data is None:
            return self._result(request, None, "INPUT_ERROR", 2, issues)
        for validator in self._validators:
            issues.extend(validator.validate(input_data))
        if self._has_errors(issues):
            return self._result(request, input_data, "INPUT_ERROR", 2, issues)

        resolved_rules = self._rule_resolver.execute(input_data)
        issues.extend(
            ValidationIssueModel(issue.rule_id, "ERROR", issue.target, issue.message)
            for issue in resolved_rules.issues
        )
        if self._has_errors(issues):
            return self._result(request, input_data, "INPUT_ERROR", 2, issues)
        candidates = self._candidate_builder.execute(input_data, resolved_rules)
        issues.extend(self._capacity_validator.validate(input_data, resolved_rules, candidates))
        if self._has_errors(issues):
            return self._result(request, input_data, "CANDIDATE_INSUFFICIENCY", 2, issues)
        LOGGER.info("入力検証完了 candidates=%d", len(candidates.candidates))
        if request.solve_mode is GenerationMode.VALIDATE_ONLY:
            return self._result(request, input_data, "VALIDATED", 0, issues)

        solver_result = self._solver_service.execute(
            request,
            input_data,
            resolved_rules,
            candidates,
        )
        LOGGER.info(
            "Solver完了 status=%s wall_time=%f",
            solver_result.statistics.status,
            solver_result.statistics.wall_time_seconds,
        )
        if solver_result.statistics.status not in {"OPTIMAL", "FEASIBLE"}:
            exit_code = 3 if solver_result.statistics.status in {"INFEASIBLE", "UNKNOWN"} else 1
            return self._result(
                request,
                input_data,
                solver_result.statistics.status,
                exit_code,
                issues,
                statistics=solver_result.statistics,
            )
        try:
            lessons = self._room_assigner.execute(input_data, solver_result.lessons)
        except ValueError as exc:
            issues.append(
                ValidationIssueModel(
                    "H03",
                    "ERROR",
                    "room_assignment",
                    str(exc),
                )
            )
            return self._result(
                request,
                input_data,
                "ROOM_ASSIGNMENT_ERROR",
                4,
                issues,
                statistics=solver_result.statistics,
            )
        validation_report = self._result_validator.execute(
            input_data,
            resolved_rules,
            lessons,
        )
        issues.extend(validation_report.issues)
        if self._has_errors(issues):
            return self._result(
                request,
                input_data,
                "RESULT_VALIDATION_ERROR",
                4,
                issues,
                lessons,
                solver_result.statistics,
            )
        try:
            document = self._document_builder.execute(input_data, lessons)
        except ValueError as exc:
            issues.append(
                ValidationIssueModel(
                    "OUTPUT_DOCUMENT_INVALID",
                    "ERROR",
                    "timetable_document",
                    str(exc),
                )
            )
            return self._result(
                request,
                input_data,
                "OUTPUT_DOCUMENT_ERROR",
                4,
                issues,
                lessons,
                solver_result.statistics,
            )
        self._output_writer.write(document, request.output_path)
        return self._result(
            request,
            input_data,
            solver_result.statistics.status,
            0,
            issues,
            lessons,
            solver_result.statistics,
        )

    def _result(
        self,
        request: GenerationRequestModel,
        input_data: InputDataModel | None,
        status: str,
        exit_code: int,
        issues: list[ValidationIssueModel],
        lessons: tuple[ScheduledLessonModel, ...] = (),
        statistics: SolverStatisticsModel | None = None,
    ) -> GenerationResultModel:
        LOGGER.info("実行終了 status=%s exit_code=%d errors=%d", status, exit_code, len(issues))
        return GenerationResultModel(
            status=status,
            exit_code=exit_code,
            request=request,
            input_data=input_data,
            lessons=lessons,
            validation_report=ValidationReportModel(tuple(issues)),
            solver_statistics=statistics,
        )

    def _has_errors(self, issues: list[ValidationIssueModel]) -> bool:
        return any(issue.severity == "ERROR" for issue in issues)

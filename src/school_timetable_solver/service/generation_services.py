from __future__ import annotations

import logging
from collections import Counter

from school_timetable_solver.model.input_models import GenerationMode, InputDataModel
from school_timetable_solver.model.result_models import (
    GenerationRequestModel,
    GenerationResultModel,
    ScheduledLessonModel,
    UnplacedLessonModel,
    ValidationIssueModel,
    ValidationReportModel,
)
from school_timetable_solver.model.solver_models import CandidateSlotModel, SolverStatisticsModel
from school_timetable_solver.service.planning_services import (
    CandidateBuilderService,
    RuleResolverService,
)
from school_timetable_solver.service.protocols import InputReader, TimetableWriter
from school_timetable_solver.service.result_services import ValidateResultService
from school_timetable_solver.service.solver_service import TimetableSolverService
from school_timetable_solver.validator.input_validators import InputValidator

LOGGER = logging.getLogger(__name__)


class ValidateInputService:
    """Read input, aggregate all input issues, and write a validation workbook."""

    def __init__(
        self,
        input_reader: InputReader,
        validators: tuple[InputValidator, ...],
        output_writer: TimetableWriter,
    ) -> None:
        self._input_reader = input_reader
        self._validators = validators
        self._output_writer = output_writer

    def execute(self, request: GenerationRequestModel) -> GenerationResultModel:
        read_result = self._input_reader.read(request.input_path)
        issues = list(read_result.issues)
        if read_result.input_data is not None:
            for validator in self._validators:
                issues.extend(validator.validate(read_result.input_data))
        result = GenerationResultModel(
            status="INPUT_ERROR" if issues else "VALIDATED",
            exit_code=2 if issues else 0,
            request=request,
            input_data=read_result.input_data,
            lessons=(),
            unplaced_lessons=(),
            validation_report=ValidationReportModel(tuple(issues)),
            solver_statistics=None,
        )
        self._output_writer.write(result, request.output_path)
        return result


class GenerateTimetableService:
    """Coordinate validation, planning, solving, independent validation, and output."""

    def __init__(
        self,
        input_reader: InputReader,
        validators: tuple[InputValidator, ...],
        rule_resolver: RuleResolverService,
        candidate_builder: CandidateBuilderService,
        solver_service: TimetableSolverService,
        result_validator: ValidateResultService,
        output_writer: TimetableWriter,
    ) -> None:
        self._input_reader = input_reader
        self._validators = validators
        self._rule_resolver = rule_resolver
        self._candidate_builder = candidate_builder
        self._solver_service = solver_service
        self._result_validator = result_validator
        self._output_writer = output_writer

    def execute(self, request: GenerationRequestModel) -> GenerationResultModel:
        LOGGER.info("実行開始 input=%s output=%s", request.input_path, request.output_path)
        if request.input_path.resolve() == request.output_path.resolve():
            issue = ValidationIssueModel(
                "INPUT_OUTPUT_PATH_CONFLICT",
                "ERROR",
                str(request.input_path),
                "入力ファイルと出力ファイルに同じパスは指定できません",
            )
            return GenerationResultModel(
                "INPUT_ERROR",
                2,
                request,
                None,
                (),
                (),
                ValidationReportModel((issue,)),
                None,
            )
        read_result = self._input_reader.read(request.input_path)
        issues = list(read_result.issues)
        input_data = read_result.input_data
        if input_data is not None:
            for validator in self._validators:
                issues.extend(validator.validate(input_data))
        if input_data is None or issues:
            return self._write_terminal_result(
                request, input_data, "INPUT_ERROR", 2, issues, (), (), None
            )
        LOGGER.info(
            "入力読込完了 requirements=%d teachers=%d classes=%d",
            len(input_data.lesson_requirements),
            len(input_data.teachers),
            len(input_data.classes),
        )
        if input_data.settings.solve_mode is GenerationMode.VALIDATE_ONLY:
            return self._write_terminal_result(
                request, input_data, "VALIDATED", 0, [], (), (), None
            )

        resolved_rules = self._rule_resolver.execute(input_data)
        candidate_result = self._candidate_builder.execute(input_data, resolved_rules)
        LOGGER.info("Candidate生成完了 candidates=%d", len(candidate_result.candidates))
        insufficiencies = self._candidate_insufficiencies(input_data, candidate_result.candidates)
        if insufficiencies:
            unplaced = self._build_unplaced(input_data, (), "候補枠不足")
            return self._write_terminal_result(
                request,
                input_data,
                "INPUT_ERROR",
                2,
                insufficiencies,
                (),
                unplaced,
                None,
            )

        solver_result = self._solver_service.execute(input_data, resolved_rules, candidate_result)
        LOGGER.info(
            "Solver完了 status=%s wall_time=%f",
            solver_result.statistics.status,
            solver_result.statistics.wall_time_seconds,
        )
        if solver_result.statistics.status not in {"OPTIMAL", "FEASIBLE"}:
            exit_code = 3 if solver_result.statistics.status in {"INFEASIBLE", "UNKNOWN"} else 1
            unplaced = self._build_unplaced(input_data, solver_result.lessons, "strict生成で解なし")
            return self._write_terminal_result(
                request,
                input_data,
                solver_result.statistics.status,
                exit_code,
                [],
                solver_result.lessons,
                unplaced,
                solver_result.statistics,
            )

        validation_report = self._result_validator.execute(
            input_data, resolved_rules, solver_result.lessons
        )
        if validation_report.has_errors():
            return self._write_terminal_result(
                request,
                input_data,
                "INTERNAL_VALIDATION_ERROR",
                4,
                list(validation_report.issues),
                solver_result.lessons,
                (),
                solver_result.statistics,
            )
        return self._write_terminal_result(
            request,
            input_data,
            solver_result.statistics.status,
            0,
            [],
            solver_result.lessons,
            (),
            solver_result.statistics,
        )

    def _candidate_insufficiencies(
        self, input_data: InputDataModel, candidates: tuple[CandidateSlotModel, ...]
    ) -> list[ValidationIssueModel]:
        slots_by_requirement: dict[str, set[tuple[object, str]]] = {}
        for candidate in candidates:
            slots_by_requirement.setdefault(candidate.requirement_id, set()).add(
                (candidate.target_date, candidate.period_id)
            )
        issues: list[ValidationIssueModel] = []
        for requirement in input_data.lesson_requirements:
            slot_count = len(slots_by_requirement.get(requirement.requirement_id, set()))
            if slot_count < requirement.required_periods:
                issues.append(
                    ValidationIssueModel(
                        "E011",
                        "ERROR",
                        requirement.requirement_id,
                        (
                            "解決済みルール適用後の候補枠が不足しています: "
                            f"required={requirement.required_periods}, slots={slot_count}"
                        ),
                    )
                )
        return issues

    def _build_unplaced(
        self,
        input_data: InputDataModel,
        lessons: tuple[ScheduledLessonModel, ...],
        reason: str,
    ) -> tuple[UnplacedLessonModel, ...]:
        counts = Counter(lesson.requirement_id for lesson in lessons)
        return tuple(
            UnplacedLessonModel(
                requirement.requirement_id,
                requirement.required_periods,
                counts[requirement.requirement_id],
                max(0, requirement.required_periods - counts[requirement.requirement_id]),
                reason,
            )
            for requirement in input_data.lesson_requirements
            if counts[requirement.requirement_id] < requirement.required_periods
        )

    def _write_terminal_result(
        self,
        request: GenerationRequestModel,
        input_data: InputDataModel | None,
        status: str,
        exit_code: int,
        issues: list[ValidationIssueModel],
        lessons: tuple[ScheduledLessonModel, ...],
        unplaced: tuple[UnplacedLessonModel, ...],
        statistics: SolverStatisticsModel | None,
    ) -> GenerationResultModel:
        result = GenerationResultModel(
            status=status,
            exit_code=exit_code,
            request=request,
            input_data=input_data,
            lessons=lessons,
            unplaced_lessons=unplaced,
            validation_report=ValidationReportModel(tuple(issues)),
            solver_statistics=statistics,
        )
        self._output_writer.write(result, request.output_path)
        LOGGER.info("実行終了 status=%s exit_code=%d", status, exit_code)
        return result

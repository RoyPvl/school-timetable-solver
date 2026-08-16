from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
from time import perf_counter

from school_timetable_solver.constraint.hard_constraints import DAY_LEVEL_MASTER_CONSTRAINTS
from school_timetable_solver.constraint.successor_constraints import ClassSuccessorDayConstraint
from school_timetable_solver.model.input_models import InputDataModel
from school_timetable_solver.model.result_models import (
    ScheduledLessonModel,
    ScheduledTeacherDayOffModel,
    ValidationIssueModel,
    ValidationReportModel,
)
from school_timetable_solver.model.solver_models import (
    CandidateBuildResultModel,
    DecompositionIterationStatisticsModel,
    ResolvedRuleSetModel,
)
from school_timetable_solver.service.result_services import ValidateResultService
from school_timetable_solver.service.solver_service import TimetableSolverService
from school_timetable_solver.validator.input_validators import CapacityFeasibilityValidator


class SuccessorTimetableSolverService(TimetableSolverService):
    """Timetable solver whose day-level master also knows the H23 day dependency."""

    def _find_decomposed_hard_solution(
        self,
        request,
        input_data,
        resolved_rules,
        candidate_result,
    ):
        budget = request.max_solve_seconds * self._DECOMPOSITION_BUDGET_RATIO
        started_at = perf_counter()
        master_context, _ = self._build_solver_context(
            input_data,
            resolved_rules,
            candidate_result,
        )
        for constraint in (*DAY_LEVEL_MASTER_CONSTRAINTS, ClassSuccessorDayConstraint()):
            self._apply_constraint(master_context, constraint, "day_master")
        master_groups = self._daily_assignment_groups(master_context)
        cuts = []
        iteration_statistics: list[DecompositionIterationStatisticsModel] = []

        for iteration in range(1, self._DECOMPOSITION_MAX_ITERATIONS + 1):
            elapsed = perf_counter() - started_at
            remaining = budget - elapsed
            if remaining <= 0.001:
                break
            master_seconds = min(30.0, max(remaining * 0.80, 0.001))
            master_solver = self._new_solver(request, master_seconds)
            master_status = master_solver.status_name(master_solver.solve(master_context.model))
            if master_status == "INFEASIBLE":
                return None, perf_counter() - started_at, True
            if master_status not in {"OPTIMAL", "FEASIBLE"}:
                break
            master_solution = self._read_day_level_solution(
                master_context,
                master_groups,
                master_solver,
            )
            remaining = budget - (perf_counter() - started_at)
            if remaining <= 0.001:
                break
            sub_seconds = min(120.0, remaining)
            sub_solver, sub_status, sub_context, assumption_map = self._solve_period_subproblem(
                request,
                input_data,
                resolved_rules,
                candidate_result,
                master_solution,
                sub_seconds,
            )
            core_indices = (
                tuple(sub_solver.sufficient_assumptions_for_infeasibility())
                if sub_status == "INFEASIBLE"
                else ()
            )
            iteration_statistics.append(
                DecompositionIterationStatisticsModel(
                    iteration=iteration,
                    master_status=master_status,
                    master_wall_time_seconds=master_solver.wall_time,
                    subproblem_status=sub_status,
                    subproblem_wall_time_seconds=sub_solver.wall_time,
                    assumption_count=len(assumption_map),
                    infeasible_core_size=len(core_indices),
                    cut_count=len(cuts),
                )
            )
            if sub_status in {"OPTIMAL", "FEASIBLE"}:
                candidate_values = {
                    candidate.candidate_id: sub_solver.value(
                        sub_context.assignment_variables[candidate.candidate_id]
                    )
                    for candidate in candidate_result.candidates
                }
                day_off_values = {
                    key: sub_solver.value(variable)
                    for key, variable in sub_context.teacher_day_off_variables.items()
                }
                return (candidate_values, day_off_values), perf_counter() - started_at, False
            if sub_status != "INFEASIBLE":
                break
            cut = self._cut_from_infeasible_core(
                master_solution,
                core_indices,
                assumption_map,
            )
            self._add_day_level_cut(master_context, master_groups, cut, len(cuts) + 1)
            cuts.append(cut)

        return None, perf_counter() - started_at, False


class SuccessorCapacityFeasibilityValidator(CapacityFeasibilityValidator):
    """Add obvious H21/H17 successor infeasibility checks to capacity validation."""

    def validate(
        self,
        input_data: InputDataModel,
        resolved_rules: ResolvedRuleSetModel,
        candidate_result: CandidateBuildResultModel,
    ) -> list[ValidationIssueModel]:
        issues = super().validate(input_data, resolved_rules, candidate_result)
        first_classes_by_second: dict[str, set[str]] = defaultdict(set)
        for rule in input_data.class_pair_overlap_rules:
            if rule.enabled:
                first_classes_by_second[rule.second_class_id].add(rule.first_class_id)
        if not first_classes_by_second:
            return issues

        period_order = {period.period_id: period.output_order for period in input_data.periods}
        period_id_by_order = {period.output_order: period.period_id for period in input_data.periods}
        candidate_slots = {
            (candidate.class_id, candidate.target_date, candidate.period_id)
            for candidate in candidate_result.candidates
        }

        def has_predecessor(second_class_id: str, target_date: date, period_id: str) -> bool:
            previous_period_id = period_id_by_order.get(period_order[period_id] - 1)
            return previous_period_id is not None and any(
                (first_class_id, target_date, previous_period_id) in candidate_slots
                for first_class_id in first_classes_by_second[second_class_id]
            )

        for rule in resolved_rules.class_date_rules:
            if rule.class_id not in first_classes_by_second:
                continue
            for period_id in rule.required_lesson_period_ids:
                if has_predecessor(rule.class_id, rule.target_date, period_id):
                    continue
                issues.append(
                    ValidationIssueModel(
                        "H23_REQUIRED_SLOT_NO_PREDECESSOR",
                        "ERROR",
                        f"{rule.class_id}/{rule.target_date}/{period_id}",
                        "second classの必須時限の直前に配置可能なfirst class候補がありません",
                    )
                )

        for rule in resolved_rules.lesson_count_rules:
            if rule.class_id not in first_classes_by_second or rule.exact_periods <= 0:
                continue
            viable_slots = [
                (target_date, period_id)
                for target_date, period_id in rule.target_slots
                if has_predecessor(rule.class_id, target_date, period_id)
            ]
            if viable_slots:
                continue
            issues.append(
                ValidationIssueModel(
                    "H23_LESSON_COUNT_SCOPE_NO_PREDECESSOR",
                    "ERROR",
                    rule.rule_id,
                    "second classの必須配置範囲に直前first class候補を持つ時限がありません",
                )
            )
        return issues


class SuccessorValidateResultService(ValidateResultService):
    """Result validation aligned with H23 and successor-aware S10/S12 semantics."""

    def execute(
        self,
        input_data: InputDataModel,
        resolved_rules: ResolvedRuleSetModel,
        lessons: tuple[ScheduledLessonModel, ...],
        candidate_result: CandidateBuildResultModel | None = None,
        teacher_day_offs: tuple[ScheduledTeacherDayOffModel, ...] = (),
    ) -> ValidationReportModel:
        self._successor_pairs = {
            (rule.first_class_id, rule.second_class_id)
            for rule in input_data.class_pair_overlap_rules
            if rule.enabled
        }
        self._second_class_ids = {second for _, second in self._successor_pairs}
        report = super().execute(
            input_data,
            resolved_rules,
            lessons,
            candidate_result,
            teacher_day_offs,
        )
        issues = list(report.issues)
        self._validate_class_successors(input_data, lessons, issues)
        return ValidationReportModel(tuple(issues))

    def _report_room_change_gap_preference(
        self,
        input_data: InputDataModel,
        lessons: tuple[ScheduledLessonModel, ...],
        issues: list[ValidationIssueModel],
    ) -> None:
        ordered_periods = tuple(sorted(input_data.periods, key=lambda item: item.output_order))
        classes_by_room_day_period = {
            (lesson.room_id, lesson.target_date, lesson.period_id): lesson.class_id
            for lesson in lessons
        }
        room_days = {(lesson.room_id, lesson.target_date) for lesson in lessons}
        for room_id, target_date in room_days:
            for left_period, right_period in zip(ordered_periods, ordered_periods[1:], strict=False):
                left_class_id = classes_by_room_day_period.get(
                    (room_id, target_date, left_period.period_id)
                )
                right_class_id = classes_by_room_day_period.get(
                    (room_id, target_date, right_period.period_id)
                )
                if left_class_id is None or right_class_id is None or left_class_id == right_class_id:
                    continue
                if (left_class_id, right_class_id) in self._successor_pairs:
                    continue
                issues.append(
                    ValidationIssueModel(
                        "S10",
                        "WARNING",
                        f"{room_id}/{target_date}/{left_period.period_id}/{right_period.period_id}",
                        "同一教室を空き時限なしで別クラスへ交替しています: "
                        f"{left_class_id}->{right_class_id}",
                    )
                )

    def _report_class_single_lesson_day_preference(
        self,
        lessons: tuple[ScheduledLessonModel, ...],
        issues: list[ValidationIssueModel],
    ) -> None:
        lesson_counts = Counter((lesson.class_id, lesson.target_date) for lesson in lessons)
        for key, lesson_count in lesson_counts.items():
            if key[0] in self._second_class_ids or lesson_count != 1:
                continue
            issues.append(
                ValidationIssueModel(
                    "S12",
                    "WARNING",
                    str(key),
                    "同一クラスの授業がこの日に1コマだけ配置されています",
                )
            )

    def _validate_class_successors(
        self,
        input_data: InputDataModel,
        lessons: tuple[ScheduledLessonModel, ...],
        issues: list[ValidationIssueModel],
    ) -> None:
        period_orders = {period.period_id: period.output_order for period in input_data.periods}
        first_classes_by_second: dict[str, set[str]] = defaultdict(set)
        for first_class_id, second_class_id in self._successor_pairs:
            first_classes_by_second[second_class_id].add(first_class_id)
        lessons_by_class_day: dict[tuple[str, date], list[ScheduledLessonModel]] = defaultdict(list)
        for lesson in lessons:
            lessons_by_class_day[(lesson.class_id, lesson.target_date)].append(lesson)

        second_days = {
            (class_id, target_date)
            for class_id, target_date in lessons_by_class_day
            if class_id in first_classes_by_second
        }
        for second_class_id, target_date in sorted(second_days):
            second_lessons = lessons_by_class_day[(second_class_id, target_date)]
            earliest_second = min(second_lessons, key=lambda item: period_orders[item.period_id])
            earliest_order = period_orders[earliest_second.period_id]
            valid_first = False
            for first_class_id in first_classes_by_second[second_class_id]:
                first_lessons = lessons_by_class_day.get((first_class_id, target_date), ())
                if not first_lessons:
                    continue
                latest_first = max(first_lessons, key=lambda item: period_orders[item.period_id])
                if period_orders[latest_first.period_id] + 1 != earliest_order:
                    continue
                if latest_first.room_id != earliest_second.room_id:
                    continue
                valid_first = True
                break
            if valid_first:
                continue
            issues.append(
                ValidationIssueModel(
                    "H23",
                    "ERROR",
                    f"{second_class_id}/{target_date}",
                    "second classの最初のコマが、同一教室でのfirst class最終コマ直後になっていません",
                )
            )

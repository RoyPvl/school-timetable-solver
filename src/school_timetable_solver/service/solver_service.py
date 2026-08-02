from __future__ import annotations

import logging
from collections import Counter, defaultdict
from datetime import date

from ortools.sat.python import cp_model

from school_timetable_solver.constraint.hard_constraints import HardConstraint
from school_timetable_solver.constraint.soft_constraints import SoftConstraint
from school_timetable_solver.constraint.solver_context import SolverContext
from school_timetable_solver.model.input_models import InputDataModel
from school_timetable_solver.model.result_models import (
    GenerationRequestModel,
    ScheduledLessonDraftModel,
    SolverResultModel,
)
from school_timetable_solver.model.solver_models import (
    CandidateBuildResultModel,
    ResolvedHomeroomBoundaryRuleModel,
    ResolvedRuleSetModel,
    SolverStatisticsModel,
)

LOGGER = logging.getLogger(__name__)


class TimetableSolverService:
    """Build and solve one deterministic strict CP-SAT model."""

    _LOWER_PRIORITY_TOTAL_RESERVE_RATIO = 0.75
    _HOMEROOM_INITIAL_FEASIBILITY_RATIO = 0.75
    _PRELIMINARY_RESTART_COUNT = 6
    _PRELIMINARY_RESTART_MAX_SECONDS = 120.0
    _PRELIMINARY_FALLBACK_MAX_SECONDS = 900.0
    _PRELIMINARY_ANCHOR_MAX_SECONDS = 900.0
    _HOMEROOM_PRIMARY_BOUNDARY_RETRY_MAX_SECONDS = 120.0
    _HOMEROOM_DEPENDENCY_REPAIR_PROFILES = (
        (1, True, 360.0),
        (1, False, 360.0),
        (2, True, 240.0),
        (2, False, 240.0),
    )
    _HOMEROOM_FULL_RESTART_COUNT = 6
    _HOMEROOM_FULL_RESTART_MAX_SECONDS = 240.0
    _PRELIMINARY_DEFERRED_HARD_RULE_IDS: frozenset[str] = frozenset()
    _HOMEROOM_PRELIMINARY_DEFERRED_HARD_RULE_IDS = frozenset({"H11"})

    def __init__(
        self,
        hard_constraints: tuple[HardConstraint, ...],
        soft_constraints: tuple[SoftConstraint, ...] = (),
    ) -> None:
        self._hard_constraints = hard_constraints
        self._soft_constraints = soft_constraints

    def execute(
        self,
        request: GenerationRequestModel,
        input_data: InputDataModel,
        resolved_rules: ResolvedRuleSetModel,
        candidate_result: CandidateBuildResultModel,
    ) -> SolverResultModel:
        context, variables = self._build_solver_context(
            input_data,
            resolved_rules,
            candidate_result,
        )
        soft_constraints_by_priority: dict[int, list[SoftConstraint]] = defaultdict(list)
        for constraint in self._soft_constraints:
            soft_constraints_by_priority[constraint.priority].append(constraint)

        priorities = sorted(soft_constraints_by_priority, reverse=True)
        if priorities:
            solver, status, total_wall_time = self._solve_soft_priorities(
                request,
                context,
                variables,
                soft_constraints_by_priority,
                priorities,
            )
        else:
            for constraint in self._hard_constraints:
                constraint.apply(context)
            LOGGER.info(
                "Solverフェーズ開始 phase=hard_only max_seconds=%f",
                request.max_solve_seconds,
            )
            solver = self._new_solver(request, request.max_solve_seconds)
            status = solver.status_name(solver.solve(context.model))
            total_wall_time = solver.wall_time
            LOGGER.info(
                "Solverフェーズ終了 phase=hard_only status=%s wall_time=%f",
                status,
                solver.wall_time,
            )

        lessons: list[ScheduledLessonDraftModel] = []
        if solver is not None and status in {"OPTIMAL", "FEASIBLE"}:
            for candidate in candidate_result.candidates:
                if solver.value(variables[candidate.candidate_id]):
                    lessons.append(
                        ScheduledLessonDraftModel(
                            requirement_id=candidate.requirement_id,
                            target_date=candidate.target_date,
                            period_id=candidate.period_id,
                            teacher_id=candidate.teacher_id,
                            campus_id=candidate.campus_id,
                            class_id=candidate.class_id,
                            subject_id=candidate.subject_id,
                            room_index=solver.value(
                                context.class_room_variables[
                                    (
                                        candidate.campus_id,
                                        candidate.target_date,
                                        candidate.class_id,
                                    )
                                ]
                            ),
                        )
                    )
        lessons.sort(
            key=lambda item: (
                item.target_date,
                context.period_orders[item.period_id],
                item.class_id,
                item.requirement_id,
            )
        )
        return SolverResultModel(
            lessons=tuple(lessons),
            statistics=SolverStatisticsModel(
                status=status,
                wall_time_seconds=total_wall_time,
                variable_count=len(variables),
                constraint_rule_ids=tuple(context.applied_rule_ids),
            ),
        )

    def _build_solver_context(
        self,
        input_data: InputDataModel,
        resolved_rules: ResolvedRuleSetModel,
        candidate_result: CandidateBuildResultModel,
    ) -> tuple[SolverContext, dict[str, cp_model.IntVar]]:
        model = cp_model.CpModel()
        variables = {
            candidate.candidate_id: model.new_bool_var(f"x__{candidate.candidate_id}")
            for candidate in candidate_result.candidates
        }
        enabled_campus_ids = {campus.campus_id for campus in input_data.campuses if campus.enabled}
        context = SolverContext(
            model=model,
            candidates=candidate_result.candidates,
            assignment_variables=variables,
            required_counts={
                requirement.requirement_id: requirement.required_periods
                for requirement in input_data.lesson_requirements
                if requirement.enabled
            },
            room_capacities=dict(
                Counter(
                    room.campus_id
                    for room in input_data.rooms
                    if room.enabled and room.campus_id in enabled_campus_ids
                )
            ),
            class_daily_limits={
                (rule.class_id, rule.target_date): rule.daily_hard_limit
                for rule in resolved_rules.class_date_rules
            },
            requirement_daily_limits={
                requirement.requirement_id: requirement.max_periods_per_day
                for requirement in input_data.lesson_requirements
                if requirement.enabled
            },
            teacher_daily_limits={
                (rule.teacher_id, rule.target_date): rule.daily_hard_limit
                for rule in resolved_rules.teacher_date_rules
            },
            teacher_consecutive_limits={
                (rule.teacher_id, rule.target_date): rule.consecutive_hard_limit
                for rule in resolved_rules.teacher_date_rules
            },
            class_attendance_limits={
                (rule.class_id, rule.target_date): rule.attendance_streak_limit
                for rule in resolved_rules.class_date_rules
            },
            period_orders={period.period_id: period.output_order for period in input_data.periods},
            calendar_dates=tuple(
                sorted(day.target_date for day in input_data.calendar_days if day.output_enabled)
            ),
            class_attendance_preference_limits={
                (rule.class_id, rule.target_date): rule.preferred_attendance_streak_limit
                for rule in resolved_rules.class_date_rules
            },
            lesson_count_rules=resolved_rules.lesson_count_rules,
            lesson_count_preference_rules=resolved_rules.lesson_count_preference_rules,
            homeroom_boundary_rules=resolved_rules.homeroom_boundary_rules,
        )
        return context, variables

    def _solve_soft_priorities(
        self,
        request: GenerationRequestModel,
        context: SolverContext,
        variables: dict[str, cp_model.IntVar],
        soft_constraints_by_priority: dict[int, list[SoftConstraint]],
        priorities: list[int],
    ) -> tuple[cp_model.CpSolver | None, str, float]:
        preliminary_deferred_rule_ids = (
            self._HOMEROOM_PRELIMINARY_DEFERRED_HARD_RULE_IDS
            if context.homeroom_boundary_rules
            else self._PRELIMINARY_DEFERRED_HARD_RULE_IDS
        )
        deferred_hard_constraints = [
            (index, constraint)
            for index, constraint in enumerate(self._hard_constraints)
            if constraint.rule_id in preliminary_deferred_rule_ids
        ]
        for constraint in self._hard_constraints:
            if constraint.rule_id not in preliminary_deferred_rule_ids:
                constraint.apply(context)

        assignment_priorities = {
            constraint.priority
            for constraint in self._soft_constraints
            if constraint.optimization_scope == "assignment"
        }
        last_assignment_priority = min(assignment_priorities) if assignment_priorities else None
        lower_priority_reserve_ratio = self._lower_priority_reserve_ratio(len(priorities))
        first_phase_seconds = self._priority_phase_seconds(
            request.max_solve_seconds,
            request.max_solve_seconds,
            len(priorities) - 1,
            lower_priority_reserve_ratio,
        )
        if context.homeroom_boundary_rules:
            first_phase_seconds = max(
                first_phase_seconds,
                request.max_solve_seconds * self._HOMEROOM_INITIAL_FEASIBILITY_RATIO,
            )
        preliminary_solver: cp_model.CpSolver | None = None
        preliminary_status = "SKIPPED"
        preliminary_variable_count = 0
        total_wall_time = 0.0
        if deferred_hard_constraints:
            deferred_rule_ids = ",".join(
                constraint.rule_id for _, constraint in deferred_hard_constraints
            )
            preliminary_variable_count = len(context.model.proto.variables)
            anchor_candidate_ids = (
                self._homeroom_anchor_candidate_ids(context)
                if any(constraint.rule_id == "H18" for _, constraint in deferred_hard_constraints)
                else ()
            )
            for candidate_id in anchor_candidate_ids:
                context.model.add_hint(
                    context.assignment_variables[candidate_id],
                    1,
                )
            LOGGER.info("H18事前Anchor作成 anchors=%d", len(anchor_candidate_ids))
            preliminary_solver, preliminary_status, total_wall_time = (
                self._solve_preliminary_with_restarts(
                    request,
                    context,
                    deferred_rule_ids,
                    first_phase_seconds,
                )
            )

        staged_homeroom_constraint = next(
            (
                deferred_constraint
                for deferred_constraint in deferred_hard_constraints
                if deferred_constraint[1].rule_id == "H18"
            ),
            None,
        )
        if staged_homeroom_constraint is not None and context.homeroom_boundary_rules:
            initial_solver, initial_status, total_wall_time = self._solve_homeroom_stages(
                request,
                context,
                staged_homeroom_constraint,
                preliminary_solver,
                preliminary_status,
                preliminary_variable_count,
                first_phase_seconds,
                total_wall_time,
            )
        else:
            for rule_index, constraint in deferred_hard_constraints:
                constraint.apply(context)
                applied_rule_id = context.applied_rule_ids.pop()
                context.applied_rule_ids.insert(rule_index, applied_rule_id)
            if preliminary_solver is not None and preliminary_status in {
                "OPTIMAL",
                "FEASIBLE",
            }:
                for variable_index in range(preliminary_variable_count):
                    variable = context.model.get_int_var_from_proto_index(variable_index)
                    context.model.add_hint(variable, preliminary_solver.value(variable))

            initial_feasibility_seconds = max(
                first_phase_seconds - total_wall_time,
                0.001,
            )
            LOGGER.info(
                "Solverフェーズ開始 phase=initial_feasibility max_seconds=%f hints=%d",
                initial_feasibility_seconds,
                len(context.model.proto.solution_hint.vars),
            )
            initial_solver = self._new_solver(request, initial_feasibility_seconds)
            initial_status = initial_solver.status_name(initial_solver.solve(context.model))
            total_wall_time += initial_solver.wall_time
            LOGGER.info(
                (
                    "Solverフェーズ終了 phase=initial_feasibility "
                    "status=%s wall_time=%f total_wall_time=%f"
                ),
                initial_status,
                initial_solver.wall_time,
                total_wall_time,
            )

        hint_solver = initial_solver if initial_status in {"OPTIMAL", "FEASIBLE"} else None
        solved_variable_count = len(context.model.proto.variables) if hint_solver is not None else 0
        solver: cp_model.CpSolver | None = None
        status = "UNKNOWN"
        remaining_seconds = max(
            request.max_solve_seconds - total_wall_time,
            0.001,
        )
        for priority_index, priority in enumerate(priorities):
            priority_constraints = soft_constraints_by_priority[priority]
            for constraint in priority_constraints:
                constraint.apply(context)
            priority_terms = context.penalty_terms_by_priority.get(priority, [])
            context.model.minimize(sum(priority_terms))
            context.model.clear_hints()
            if hint_solver is None:
                for penalty in priority_terms:
                    context.model.add_hint(penalty, 0)
            else:
                for variable_index in range(solved_variable_count):
                    variable = context.model.get_int_var_from_proto_index(variable_index)
                    context.model.add_hint(variable, hint_solver.value(variable))

            is_last_priority = priority_index == len(priorities) - 1
            remaining_priority_count = len(priorities) - priority_index - 1
            phase_seconds = self._priority_phase_seconds(
                request.max_solve_seconds,
                remaining_seconds,
                remaining_priority_count,
                lower_priority_reserve_ratio,
            )
            rule_ids = ",".join(constraint.rule_id for constraint in priority_constraints)
            LOGGER.info(
                ("Solverフェーズ開始 phase=soft priority=%d rule_ids=%s max_seconds=%f hints=%d"),
                priority,
                rule_ids,
                phase_seconds,
                len(context.model.proto.solution_hint.vars),
            )
            phase_solver = self._new_solver(request, phase_seconds)
            phase_status = phase_solver.status_name(phase_solver.solve(context.model))
            total_wall_time += phase_solver.wall_time
            LOGGER.info(
                (
                    "Solverフェーズ終了 phase=soft priority=%d rule_ids=%s "
                    "status=%s wall_time=%f total_wall_time=%f"
                ),
                priority,
                rule_ids,
                phase_status,
                phase_solver.wall_time,
                total_wall_time,
            )
            remaining_seconds = max(
                request.max_solve_seconds - total_wall_time,
                0.001,
            )
            if phase_status not in {"OPTIMAL", "FEASIBLE"}:
                if solver is None:
                    status = phase_status
                break

            solver = phase_solver
            hint_solver = phase_solver
            solved_variable_count = len(context.model.proto.variables)
            status = phase_status
            if not is_last_priority:
                achieved_penalty = sum(solver.value(penalty) for penalty in priority_terms)
                context.model.add(sum(priority_terms) <= achieved_penalty)
                for group_terms in context.penalty_term_groups_by_priority.get(
                    priority,
                    {},
                ).values():
                    achieved_group_penalty = sum(solver.value(penalty) for penalty in group_terms)
                    context.model.add(sum(group_terms) <= achieved_group_penalty)
                if priority == last_assignment_priority:
                    for variable in variables.values():
                        context.model.add(variable == solver.value(variable))
        if len(priorities) > 1 and status == "OPTIMAL":
            status = "FEASIBLE"
        return solver, status, total_wall_time

    def _solve_preliminary_with_restarts(
        self,
        request: GenerationRequestModel,
        context: SolverContext,
        deferred_rule_ids: str,
        max_solve_seconds: float,
    ) -> tuple[cp_model.CpSolver | None, str, float]:
        total_wall_time = 0.0
        solver: cp_model.CpSolver | None = None
        status = "UNKNOWN"
        if context.model.proto.solution_hint.vars:
            anchor_seconds = min(
                self._PRELIMINARY_ANCHOR_MAX_SECONDS,
                max_solve_seconds,
            )
            LOGGER.info(
                (
                    "Solverフェーズ開始 phase=preliminary_anchor_feasibility "
                    "deferred_rule_ids=%s max_seconds=%f anchors=%d"
                ),
                deferred_rule_ids,
                anchor_seconds,
                len(context.model.proto.solution_hint.vars),
            )
            solver = self._new_solver(
                request,
                anchor_seconds,
                fix_hinted_variables=True,
            )
            status = solver.status_name(solver.solve(context.model))
            total_wall_time += solver.wall_time
            LOGGER.info(
                (
                    "Solverフェーズ終了 phase=preliminary_anchor_feasibility "
                    "deferred_rule_ids=%s status=%s wall_time=%f total_wall_time=%f"
                ),
                deferred_rule_ids,
                status,
                solver.wall_time,
                total_wall_time,
            )
            if status in {"OPTIMAL", "FEASIBLE"}:
                return solver, status, total_wall_time
            if status == "INFEASIBLE":
                context.model.clear_hints()

        for attempt_index in range(self._PRELIMINARY_RESTART_COUNT):
            remaining_seconds = max(max_solve_seconds - total_wall_time, 0.001)
            attempt_seconds = min(
                self._PRELIMINARY_RESTART_MAX_SECONDS,
                remaining_seconds,
            )
            LOGGER.info(
                (
                    "Solverフェーズ開始 phase=preliminary_feasibility "
                    "attempt=%d/%d deferred_rule_ids=%s max_seconds=%f"
                ),
                attempt_index + 1,
                self._PRELIMINARY_RESTART_COUNT,
                deferred_rule_ids,
                attempt_seconds,
            )
            solver = self._new_solver(
                request,
                attempt_seconds,
                random_seed_offset=attempt_index,
            )
            status = solver.status_name(solver.solve(context.model))
            total_wall_time += solver.wall_time
            LOGGER.info(
                (
                    "Solverフェーズ終了 phase=preliminary_feasibility "
                    "attempt=%d/%d deferred_rule_ids=%s status=%s "
                    "wall_time=%f total_wall_time=%f"
                ),
                attempt_index + 1,
                self._PRELIMINARY_RESTART_COUNT,
                deferred_rule_ids,
                status,
                solver.wall_time,
                total_wall_time,
            )
            if status in {"OPTIMAL", "FEASIBLE"}:
                break
        if status not in {"OPTIMAL", "FEASIBLE"}:
            remaining_seconds = max(max_solve_seconds - total_wall_time, 0.001)
            fallback_seconds = min(
                self._PRELIMINARY_FALLBACK_MAX_SECONDS,
                remaining_seconds,
            )
            LOGGER.info(
                (
                    "Solverフェーズ開始 phase=preliminary_feasibility_fallback "
                    "deferred_rule_ids=%s max_seconds=%f"
                ),
                deferred_rule_ids,
                fallback_seconds,
            )
            solver = self._new_solver(
                request,
                fallback_seconds,
                random_seed_offset=self._PRELIMINARY_RESTART_COUNT,
            )
            status = solver.status_name(solver.solve(context.model))
            total_wall_time += solver.wall_time
            LOGGER.info(
                (
                    "Solverフェーズ終了 phase=preliminary_feasibility_fallback "
                    "deferred_rule_ids=%s status=%s wall_time=%f total_wall_time=%f"
                ),
                deferred_rule_ids,
                status,
                solver.wall_time,
                total_wall_time,
            )
        return solver, status, total_wall_time

    def _solve_homeroom_stages(
        self,
        request: GenerationRequestModel,
        context: SolverContext,
        staged_constraint: tuple[int, HardConstraint],
        preliminary_solver: cp_model.CpSolver | None,
        preliminary_status: str,
        preliminary_variable_count: int,
        first_phase_seconds: float,
        total_wall_time: float,
    ) -> tuple[cp_model.CpSolver | None, str, float]:
        rule_index, constraint = staged_constraint
        full_rules = context.homeroom_boundary_rules
        batches = self._homeroom_rule_batches(full_rules, context)
        hint_solver = preliminary_solver if preliminary_status in {"OPTIMAL", "FEASIBLE"} else None
        hint_status = preliminary_status
        hinted_variable_count = preliminary_variable_count if hint_solver is not None else 0
        stage_solver: cp_model.CpSolver | None = None
        stage_status = "UNKNOWN"

        for batch_index, batch in enumerate(batches):
            context.homeroom_boundary_rules = batch
            constraint.apply(context)
            context.applied_rule_ids.pop()

            remaining_batch_count = len(batches) - batch_index
            remaining_first_phase_seconds = max(
                first_phase_seconds - total_wall_time,
                0.001,
            )
            stage_seconds = max(
                remaining_first_phase_seconds / remaining_batch_count,
                0.001,
            )
            stage_variable_count = len(context.model.proto.variables)
            class_ids = tuple(dict.fromkeys(rule.class_id for rule in batch))
            stage_solver, stage_status, stage_wall_time = self._solve_homeroom_batch(
                request,
                context,
                batch,
                hint_solver,
                hinted_variable_count,
                stage_seconds,
                batch_index + 1,
                len(batches),
                class_ids,
            )
            total_wall_time += stage_wall_time
            if stage_status not in {"OPTIMAL", "FEASIBLE"}:
                (
                    dependency_solver,
                    dependency_status,
                    dependency_wall_time,
                ) = self._solve_homeroom_dependency_repairs(
                    request,
                    context,
                    batch,
                    hint_solver,
                    first_phase_seconds - total_wall_time,
                    batch_index,
                    len(batches),
                )
                total_wall_time += dependency_wall_time
                if dependency_status in {"OPTIMAL", "FEASIBLE"}:
                    hint_solver = dependency_solver
                    hint_status = dependency_status
                    hinted_variable_count = stage_variable_count
                    continue

                retry_succeeded = False
                maximum_combined_offset = self._maximum_homeroom_combined_offset(
                    context,
                    batch,
                )
                maximum_individual_offset = min(2, maximum_combined_offset)
                boundary_offset_pairs = sorted(
                    (
                        (first_offset, last_offset)
                        for first_offset in range(maximum_individual_offset + 1)
                        for last_offset in range(maximum_individual_offset + 1)
                        if first_offset + last_offset <= maximum_combined_offset
                    ),
                    key=lambda item: (sum(item), item[0]),
                )
                retry_strategies: tuple[tuple[str, tuple[int, int] | None], ...] = (
                    *(
                        (
                            f"boundary_offsets_{first_offset}_{last_offset}",
                            (first_offset, last_offset),
                        )
                        for first_offset, last_offset in boundary_offset_pairs
                    ),
                    ("no_hint", None),
                )
                for retry_index, (
                    retry_strategy,
                    boundary_offsets,
                ) in enumerate(retry_strategies):
                    remaining_first_phase_seconds = max(
                        first_phase_seconds - total_wall_time,
                        0.001,
                    )
                    remaining_retry_count = len(retry_strategies) - retry_index
                    if boundary_offsets == (0, 0):
                        retry_seconds = min(
                            self._HOMEROOM_PRIMARY_BOUNDARY_RETRY_MAX_SECONDS,
                            remaining_first_phase_seconds / (remaining_retry_count + 1),
                        )
                    else:
                        retry_seconds = min(
                            max(stage_seconds * 1.5, stage_seconds),
                            remaining_first_phase_seconds / (remaining_retry_count + 1),
                        )
                    context.model.clear_hints()
                    if boundary_offsets is not None:
                        self._add_homeroom_boundary_date_hints(
                            context,
                            batch,
                            first_boundary_offset=boundary_offsets[0],
                            last_boundary_offset=boundary_offsets[1],
                        )
                    LOGGER.info(
                        (
                            "Solverフェーズ開始 phase=homeroom_batch_retry "
                            "batch=%d/%d class_ids=%s strategy=%s "
                            "max_seconds=%f hints=%d"
                        ),
                        batch_index + 1,
                        len(batches),
                        ",".join(class_ids),
                        retry_strategy,
                        retry_seconds,
                        len(context.model.proto.solution_hint.vars),
                    )
                    retry_solver = self._new_solver(
                        request,
                        retry_seconds,
                        fix_hinted_variables=boundary_offsets is not None,
                        random_seed_offset=(batch_index + 1 + retry_index * len(batches)),
                    )
                    retry_status = retry_solver.status_name(retry_solver.solve(context.model))
                    total_wall_time += retry_solver.wall_time
                    LOGGER.info(
                        (
                            "Solverフェーズ終了 phase=homeroom_batch_retry "
                            "batch=%d/%d class_ids=%s strategy=%s status=%s "
                            "wall_time=%f total_wall_time=%f"
                        ),
                        batch_index + 1,
                        len(batches),
                        ",".join(class_ids),
                        retry_strategy,
                        retry_status,
                        retry_solver.wall_time,
                        total_wall_time,
                    )
                    if retry_status in {"OPTIMAL", "FEASIBLE"}:
                        hint_solver = retry_solver
                        hint_status = retry_status
                        hinted_variable_count = stage_variable_count
                        retry_succeeded = True
                        break
                if retry_succeeded:
                    continue

                remaining_batches = batches[batch_index + 1 :]
                for remaining_batch in remaining_batches:
                    context.homeroom_boundary_rules = remaining_batch
                    constraint.apply(context)
                    context.applied_rule_ids.pop()
                remaining_first_phase_seconds = max(
                    first_phase_seconds - total_wall_time,
                    0.001,
                )
                full_rules_to_solve = batch + tuple(
                    rule for remaining_batch in remaining_batches for rule in remaining_batch
                )
                full_solver, full_status, full_wall_time = self._solve_full_homeroom_with_restarts(
                    request,
                    context,
                    full_rules_to_solve,
                    hint_solver,
                    hinted_variable_count,
                    remaining_first_phase_seconds,
                )
                total_wall_time += full_wall_time
                if full_status in {"OPTIMAL", "FEASIBLE"}:
                    hint_solver = full_solver
                    hint_status = full_status
                break
            hint_solver = stage_solver
            hint_status = stage_status
            hinted_variable_count = stage_variable_count

        context.homeroom_boundary_rules = full_rules
        context.applied_rule_ids.insert(rule_index, constraint.rule_id)
        return hint_solver, hint_status, total_wall_time

    def _solve_full_homeroom_with_restarts(
        self,
        request: GenerationRequestModel,
        context: SolverContext,
        rules: tuple[ResolvedHomeroomBoundaryRuleModel, ...],
        hint_solver: cp_model.CpSolver | None,
        hinted_variable_count: int,
        max_solve_seconds: float,
    ) -> tuple[cp_model.CpSolver | None, str, float]:
        total_wall_time = 0.0
        solver: cp_model.CpSolver | None = None
        status = "UNKNOWN"
        hint_strategies = (
            "anchors_and_boundaries_fixed",
            "anchors_fixed",
            "solution_and_boundaries",
            "boundaries",
            "none",
            "solution",
        )
        for attempt_index, hint_strategy in enumerate(hint_strategies):
            remaining_seconds = max(max_solve_seconds - total_wall_time, 0.001)
            remaining_attempt_count = len(hint_strategies) - attempt_index
            attempt_seconds = min(
                self._HOMEROOM_FULL_RESTART_MAX_SECONDS,
                remaining_seconds / (remaining_attempt_count + 1),
            )
            context.model.clear_hints()
            if hint_strategy in {"anchors_fixed", "anchors_and_boundaries_fixed"}:
                for candidate_id in self._homeroom_anchor_candidate_ids(context, rules):
                    context.model.add_hint(
                        context.assignment_variables[candidate_id],
                        1,
                    )
            if hint_strategy in {"solution", "solution_and_boundaries"} and hint_solver is not None:
                self._add_solver_hints(
                    context,
                    hint_solver,
                    hinted_variable_count,
                )
            if hint_strategy in {
                "anchors_and_boundaries_fixed",
                "boundaries",
                "solution_and_boundaries",
            }:
                self._add_homeroom_boundary_date_hints(context, rules)
            LOGGER.info(
                (
                    "Solverフェーズ開始 phase=homeroom_full_restart "
                    "attempt=%d/%d strategy=%s max_seconds=%f hints=%d"
                ),
                attempt_index + 1,
                self._HOMEROOM_FULL_RESTART_COUNT,
                hint_strategy,
                attempt_seconds,
                len(context.model.proto.solution_hint.vars),
            )
            solver = self._new_solver(
                request,
                attempt_seconds,
                fix_hinted_variables=hint_strategy
                in {
                    "anchors_fixed",
                    "anchors_and_boundaries_fixed",
                },
                random_seed_offset=attempt_index,
            )
            status = solver.status_name(solver.solve(context.model))
            total_wall_time += solver.wall_time
            LOGGER.info(
                (
                    "Solverフェーズ終了 phase=homeroom_full_restart "
                    "attempt=%d/%d strategy=%s status=%s "
                    "wall_time=%f total_wall_time=%f"
                ),
                attempt_index + 1,
                self._HOMEROOM_FULL_RESTART_COUNT,
                hint_strategy,
                status,
                solver.wall_time,
                total_wall_time,
            )
            if status in {"OPTIMAL", "FEASIBLE"}:
                return solver, status, total_wall_time

        remaining_seconds = max(max_solve_seconds - total_wall_time, 0.001)
        context.model.clear_hints()
        LOGGER.info(
            "Solverフェーズ開始 phase=homeroom_full_fallback max_seconds=%f hints=0",
            remaining_seconds,
        )
        solver = self._new_solver(
            request,
            remaining_seconds,
            random_seed_offset=len(hint_strategies),
        )
        status = solver.status_name(solver.solve(context.model))
        total_wall_time += solver.wall_time
        LOGGER.info(
            (
                "Solverフェーズ終了 phase=homeroom_full_fallback "
                "status=%s wall_time=%f total_wall_time=%f"
            ),
            status,
            solver.wall_time,
            total_wall_time,
        )
        return solver, status, total_wall_time

    def _solve_homeroom_dependency_repairs(
        self,
        request: GenerationRequestModel,
        context: SolverContext,
        batch: tuple[ResolvedHomeroomBoundaryRuleModel, ...],
        hint_solver: cp_model.CpSolver | None,
        max_solve_seconds: float,
        batch_index: int,
        batch_count: int,
    ) -> tuple[cp_model.CpSolver | None, str, float]:
        if hint_solver is None:
            return None, "SKIPPED", 0.0

        total_wall_time = 0.0
        solver: cp_model.CpSolver | None = None
        status = "UNKNOWN"
        class_ids = tuple(dict.fromkeys(rule.class_id for rule in batch))
        all_candidate_count = len(context.candidates)
        for attempt_index, (
            dependency_depth,
            fix_boundary_extremes,
            requested_seconds,
        ) in enumerate(self._HOMEROOM_DEPENDENCY_REPAIR_PROFILES):
            remaining_seconds = max(max_solve_seconds - total_wall_time, 0.001)
            attempt_seconds = min(requested_seconds, remaining_seconds)
            mutable_candidate_ids = self._homeroom_dependency_candidate_ids(
                context,
                batch,
                dependency_depth,
            )
            if len(mutable_candidate_ids) == all_candidate_count:
                continue

            context.model.clear_hints()
            fixed_assignment_count = 0
            for candidate in context.candidates:
                if candidate.candidate_id in mutable_candidate_ids:
                    continue
                variable = context.assignment_variables[candidate.candidate_id]
                context.model.add_hint(variable, hint_solver.value(variable))
                fixed_assignment_count += 1
            if fix_boundary_extremes:
                self._add_homeroom_boundary_date_hints(context, batch)
            LOGGER.info(
                (
                    "Solverフェーズ開始 phase=homeroom_dependency_repair "
                    "batch=%d/%d class_ids=%s depth=%d boundary_extremes=%s "
                    "max_seconds=%f mutable_candidates=%d fixed_assignments=%d hints=%d"
                ),
                batch_index + 1,
                batch_count,
                ",".join(class_ids),
                dependency_depth,
                fix_boundary_extremes,
                attempt_seconds,
                len(mutable_candidate_ids),
                fixed_assignment_count,
                len(context.model.proto.solution_hint.vars),
            )
            solver = self._new_solver(
                request,
                attempt_seconds,
                fix_hinted_variables=True,
                random_seed_offset=batch_index + attempt_index + 1,
            )
            status = solver.status_name(solver.solve(context.model))
            total_wall_time += solver.wall_time
            LOGGER.info(
                (
                    "Solverフェーズ終了 phase=homeroom_dependency_repair "
                    "batch=%d/%d class_ids=%s depth=%d boundary_extremes=%s "
                    "status=%s wall_time=%f total_wall_time=%f"
                ),
                batch_index + 1,
                batch_count,
                ",".join(class_ids),
                dependency_depth,
                fix_boundary_extremes,
                status,
                solver.wall_time,
                total_wall_time,
            )
            if status in {"OPTIMAL", "FEASIBLE"}:
                return solver, status, total_wall_time
        return solver, status, total_wall_time

    def _homeroom_rule_batches(
        self,
        rules: tuple[ResolvedHomeroomBoundaryRuleModel, ...],
        context: SolverContext | None = None,
    ) -> tuple[tuple[ResolvedHomeroomBoundaryRuleModel, ...], ...]:
        rules_by_class: dict[str, list[ResolvedHomeroomBoundaryRuleModel]] = defaultdict(list)
        for rule in rules:
            rules_by_class[rule.class_id].append(rule)
        tightness_by_class = (
            self._homeroom_tightness_by_class(context) if context is not None else {}
        )
        return tuple(
            (rule,)
            for class_id in sorted(
                rules_by_class,
                key=lambda item: (-tightness_by_class.get(item, 0.0), item),
            )
            for rule in sorted(
                rules_by_class[class_id],
                key=lambda item: (item.start_date, item.end_date, item.rule_id),
            )
        )

    def _homeroom_tightness_by_class(self, context: SolverContext) -> dict[str, float]:
        requirement_ids_by_class: dict[str, set[str]] = defaultdict(set)
        slots_by_class: dict[str, set[tuple[date, str]]] = defaultdict(set)
        requirement_ids_by_teacher: dict[str, set[str]] = defaultdict(set)
        slots_by_teacher: dict[str, set[tuple[date, str]]] = defaultdict(set)
        for candidate in context.candidates:
            slot = (candidate.target_date, candidate.period_id)
            requirement_ids_by_class[candidate.class_id].add(candidate.requirement_id)
            slots_by_class[candidate.class_id].add(slot)
            requirement_ids_by_teacher[candidate.teacher_id].add(candidate.requirement_id)
            slots_by_teacher[candidate.teacher_id].add(slot)

        homeroom_teacher_by_class = {
            rule.class_id: rule.teacher_id for rule in context.homeroom_boundary_rules
        }
        return {
            class_id: (
                sum(
                    context.required_counts[requirement_id]
                    for requirement_id in requirement_ids_by_class[class_id]
                )
                / len(slots_by_class[class_id])
                + sum(
                    context.required_counts[requirement_id]
                    for requirement_id in requirement_ids_by_teacher[teacher_id]
                )
                / len(slots_by_teacher[teacher_id])
            )
            for class_id, teacher_id in homeroom_teacher_by_class.items()
            if slots_by_class[class_id] and slots_by_teacher[teacher_id]
        }

    def _solve_homeroom_batch(
        self,
        request: GenerationRequestModel,
        context: SolverContext,
        batch: tuple[ResolvedHomeroomBoundaryRuleModel, ...],
        hint_solver: cp_model.CpSolver | None,
        hinted_variable_count: int,
        max_solve_seconds: float,
        batch_number: int,
        batch_count: int,
        class_ids: tuple[str, ...],
    ) -> tuple[cp_model.CpSolver | None, str, float]:
        scopes = (
            "campus_plan_except_homeroom_current_boundaries",
            "campus_plan_except_homeroom",
            "campus_plan_current_boundaries",
            "campus_plan",
            "current_homeroom_campus_dates",
            "current_homeroom_dates",
            "target_class_and_homeroom",
            "target_class_teachers",
            "target_teacher_classes",
            "boundary_extremes",
            "global",
        )
        if hint_solver is None:
            scopes = ("global",)
        total_wall_time = 0.0
        solver: cp_model.CpSolver | None = None
        status = "UNKNOWN"

        for scope_index, scope in enumerate(scopes):
            context.model.clear_hints()
            fixed_hint_count = 0
            fix_hinted_variables = scope != "global"
            if scope in {
                "campus_plan_except_homeroom_current_boundaries",
                "campus_plan_except_homeroom",
                "campus_plan_current_boundaries",
                "campus_plan",
            }:
                if hint_solver is None:
                    continue
                mutable_teacher_ids = (
                    {rule.teacher_id for rule in batch}
                    if scope.startswith("campus_plan_except_homeroom")
                    else set()
                )
                for (
                    teacher_id,
                    _,
                    _,
                ), variable in context.teacher_campus_day_variables.items():
                    if teacher_id in mutable_teacher_ids:
                        continue
                    context.model.add_hint(variable, hint_solver.value(variable))
                    fixed_hint_count += 1
                if scope.endswith("current_boundaries"):
                    boundary_hint_count = self._add_current_homeroom_campus_date_hints(
                        context,
                        batch,
                        hint_solver,
                    )
                    if boundary_hint_count == 0:
                        continue
            elif scope == "boundary_extremes":
                self._add_homeroom_boundary_date_hints(context, batch)
                fixed_hint_count = len(context.model.proto.solution_hint.vars)
            elif hint_solver is not None:
                if fix_hinted_variables:
                    mutable_candidate_ids = self._homeroom_mutable_candidate_ids(
                        context,
                        batch,
                        include_all_target_class_teachers=(scope == "target_class_teachers"),
                        include_target_teacher_classes=(scope == "target_teacher_classes"),
                    )
                    for candidate in context.candidates:
                        if candidate.candidate_id in mutable_candidate_ids:
                            continue
                        variable = context.assignment_variables[candidate.candidate_id]
                        context.model.add_hint(variable, hint_solver.value(variable))
                        fixed_hint_count += 1
                    if scope in {
                        "current_homeroom_campus_dates",
                        "current_homeroom_dates",
                    }:
                        if scope == "current_homeroom_campus_dates":
                            boundary_hint_count = self._add_current_homeroom_campus_date_hints(
                                context,
                                batch,
                                hint_solver,
                            )
                        else:
                            boundary_hint_count = self._add_current_homeroom_date_hints(
                                context,
                                batch,
                                hint_solver,
                            )
                        if boundary_hint_count == 0:
                            continue
                else:
                    self._add_solver_hints(
                        context,
                        hint_solver,
                        hinted_variable_count,
                    )
                    self._add_homeroom_boundary_date_hints(context, batch)

            remaining_scope_count = len(scopes) - scope_index
            remaining_seconds = max(max_solve_seconds - total_wall_time, 0.001)
            scope_seconds = max(remaining_seconds / remaining_scope_count, 0.001)
            LOGGER.info(
                (
                    "Solverフェーズ開始 phase=homeroom_feasibility "
                    "batch=%d/%d class_ids=%s scope=%s max_seconds=%f "
                    "hints=%d fixed_hints=%d"
                ),
                batch_number,
                batch_count,
                ",".join(class_ids),
                scope,
                scope_seconds,
                len(context.model.proto.solution_hint.vars),
                fixed_hint_count,
            )
            solver = self._new_solver(
                request,
                scope_seconds,
                fix_hinted_variables=fix_hinted_variables,
            )
            status = solver.status_name(solver.solve(context.model))
            total_wall_time += solver.wall_time
            LOGGER.info(
                (
                    "Solverフェーズ終了 phase=homeroom_feasibility "
                    "batch=%d/%d class_ids=%s scope=%s status=%s "
                    "wall_time=%f batch_wall_time=%f"
                ),
                batch_number,
                batch_count,
                ",".join(class_ids),
                scope,
                status,
                solver.wall_time,
                total_wall_time,
            )
            if status in {"OPTIMAL", "FEASIBLE"}:
                return solver, status, total_wall_time

        return solver, status, total_wall_time

    def _homeroom_mutable_candidate_ids(
        self,
        context: SolverContext,
        batch: tuple[ResolvedHomeroomBoundaryRuleModel, ...],
        *,
        include_all_target_class_teachers: bool,
        include_target_teacher_classes: bool = False,
    ) -> set[str]:
        target_class_ids = {rule.class_id for rule in batch}
        target_teacher_ids = {rule.teacher_id for rule in batch}
        if include_all_target_class_teachers or include_target_teacher_classes:
            target_teacher_ids.update(
                candidate.teacher_id
                for candidate in context.candidates
                if candidate.class_id in target_class_ids
            )
        if include_target_teacher_classes:
            target_class_ids.update(
                candidate.class_id
                for candidate in context.candidates
                if candidate.teacher_id in target_teacher_ids
            )
        return {
            candidate.candidate_id
            for candidate in context.candidates
            if candidate.class_id in target_class_ids or candidate.teacher_id in target_teacher_ids
        }

    def _homeroom_dependency_candidate_ids(
        self,
        context: SolverContext,
        batch: tuple[ResolvedHomeroomBoundaryRuleModel, ...],
        dependency_depth: int,
    ) -> set[str]:
        target_class_ids = {rule.class_id for rule in batch}
        target_teacher_ids = {rule.teacher_id for rule in batch}
        for _ in range(dependency_depth):
            target_teacher_ids.update(
                candidate.teacher_id
                for candidate in context.candidates
                if candidate.class_id in target_class_ids
            )
            target_class_ids.update(
                candidate.class_id
                for candidate in context.candidates
                if candidate.teacher_id in target_teacher_ids
            )
        return {
            candidate.candidate_id
            for candidate in context.candidates
            if candidate.class_id in target_class_ids or candidate.teacher_id in target_teacher_ids
        }

    def _homeroom_anchor_candidate_ids(
        self,
        context: SolverContext,
        rules: tuple[ResolvedHomeroomBoundaryRuleModel, ...] | None = None,
    ) -> tuple[str, ...]:
        target_rules = rules if rules is not None else context.homeroom_boundary_rules
        requests_by_teacher_date: dict[
            tuple[str, date],
            list[tuple[str, tuple[tuple[str, str], ...]]],
        ] = defaultdict(list)
        for rule in target_rules:
            candidates = [
                candidate
                for candidate in context.candidates
                if candidate.class_id == rule.class_id
                and candidate.teacher_id == rule.teacher_id
                and rule.start_date <= candidate.target_date <= rule.end_date
            ]
            candidate_dates = sorted({candidate.target_date for candidate in candidates})
            if not candidate_dates:
                continue
            for target_date in dict.fromkeys((candidate_dates[0], candidate_dates[-1])):
                slot_candidates = tuple(
                    (candidate.period_id, candidate.candidate_id)
                    for candidate in sorted(
                        candidates,
                        key=lambda item: (
                            context.period_orders[item.period_id],
                            item.candidate_id,
                        ),
                    )
                    if candidate.target_date == target_date
                )
                requests_by_teacher_date[(rule.teacher_id, target_date)].append(
                    (rule.rule_id, slot_candidates)
                )

        anchor_candidate_ids: list[str] = []
        for requests in requests_by_teacher_date.values():
            anchor_candidate_ids.extend(self._match_homeroom_anchor_requests(requests))
        return tuple(dict.fromkeys(anchor_candidate_ids))

    def _match_homeroom_anchor_requests(
        self,
        requests: list[tuple[str, tuple[tuple[str, str], ...]]],
    ) -> tuple[str, ...]:
        ordered_requests = sorted(
            requests,
            key=lambda item: (len(item[1]), item[0]),
        )
        assignments: dict[str, str] = {}
        used_period_ids: set[str] = set()

        def assign(request_index: int) -> bool:
            if request_index == len(ordered_requests):
                return True
            request_id, slot_candidates = ordered_requests[request_index]
            for period_id, candidate_id in slot_candidates:
                if period_id in used_period_ids:
                    continue
                assignments[request_id] = candidate_id
                used_period_ids.add(period_id)
                if assign(request_index + 1):
                    return True
                used_period_ids.remove(period_id)
                assignments.pop(request_id)
            return False

        if not assign(0):
            return ()
        return tuple(assignments.values())

    def _add_solver_hints(
        self,
        context: SolverContext,
        solver: cp_model.CpSolver,
        variable_count: int,
    ) -> None:
        for variable_index in range(variable_count):
            variable = context.model.get_int_var_from_proto_index(variable_index)
            context.model.add_hint(variable, solver.value(variable))

    def _add_homeroom_boundary_date_hints(
        self,
        context: SolverContext,
        rules: tuple[ResolvedHomeroomBoundaryRuleModel, ...],
        *,
        first_boundary_offset: int = 0,
        last_boundary_offset: int = 0,
    ) -> None:
        for rule in rules:
            first_dates = sorted(
                target_date
                for rule_id, target_date in context.homeroom_first_date_variables
                if rule_id == rule.rule_id
            )
            last_dates = sorted(
                target_date
                for rule_id, target_date in context.homeroom_last_date_variables
                if rule_id == rule.rule_id
            )
            for target_date in first_dates:
                context.model.add_hint(
                    context.homeroom_first_date_variables[(rule.rule_id, target_date)],
                    int(target_date == first_dates[first_boundary_offset]),
                )
            for target_date in last_dates:
                context.model.add_hint(
                    context.homeroom_last_date_variables[(rule.rule_id, target_date)],
                    int(target_date == last_dates[-last_boundary_offset - 1]),
                )

    def _add_current_homeroom_date_hints(
        self,
        context: SolverContext,
        rules: tuple[ResolvedHomeroomBoundaryRuleModel, ...],
        solver: cp_model.CpSolver,
    ) -> int:
        hint_count = 0
        for rule in rules:
            selected_homeroom_dates = sorted(
                {
                    candidate.target_date
                    for candidate in context.candidates
                    if candidate.class_id == rule.class_id
                    and candidate.teacher_id == rule.teacher_id
                    and rule.start_date <= candidate.target_date <= rule.end_date
                    and solver.value(context.assignment_variables[candidate.candidate_id])
                }
            )
            if not selected_homeroom_dates:
                continue
            first_date = selected_homeroom_dates[0]
            last_date = selected_homeroom_dates[-1]
            first_variables = {
                target_date: variable
                for (rule_id, target_date), variable in (
                    context.homeroom_first_date_variables.items()
                )
                if rule_id == rule.rule_id
            }
            last_variables = {
                target_date: variable
                for (rule_id, target_date), variable in (
                    context.homeroom_last_date_variables.items()
                )
                if rule_id == rule.rule_id
            }
            if first_date not in first_variables or last_date not in last_variables:
                continue
            for target_date, variable in first_variables.items():
                context.model.add_hint(variable, int(target_date == first_date))
                hint_count += 1
            for target_date, variable in last_variables.items():
                context.model.add_hint(variable, int(target_date == last_date))
                hint_count += 1
        return hint_count

    def _add_current_homeroom_campus_date_hints(
        self,
        context: SolverContext,
        rules: tuple[ResolvedHomeroomBoundaryRuleModel, ...],
        solver: cp_model.CpSolver,
    ) -> int:
        hint_count = 0
        for rule in rules:
            class_campus_ids = {
                candidate.campus_id
                for candidate in context.candidates
                if candidate.class_id == rule.class_id
            }
            selected_campus_dates = sorted(
                {
                    candidate.target_date
                    for candidate in context.candidates
                    if candidate.teacher_id == rule.teacher_id
                    and candidate.campus_id in class_campus_ids
                    and rule.start_date <= candidate.target_date <= rule.end_date
                    and solver.value(context.assignment_variables[candidate.candidate_id])
                }
            )
            if not selected_campus_dates:
                continue
            first_date = selected_campus_dates[0]
            last_date = selected_campus_dates[-1]
            first_variables = {
                target_date: variable
                for (rule_id, target_date), variable in (
                    context.homeroom_first_date_variables.items()
                )
                if rule_id == rule.rule_id
            }
            last_variables = {
                target_date: variable
                for (rule_id, target_date), variable in (
                    context.homeroom_last_date_variables.items()
                )
                if rule_id == rule.rule_id
            }
            if first_date not in first_variables or last_date not in last_variables:
                continue
            for target_date, variable in first_variables.items():
                context.model.add_hint(variable, int(target_date == first_date))
                hint_count += 1
            for target_date, variable in last_variables.items():
                context.model.add_hint(variable, int(target_date == last_date))
                hint_count += 1
        return hint_count

    def _maximum_homeroom_combined_offset(
        self,
        context: SolverContext,
        rules: tuple[ResolvedHomeroomBoundaryRuleModel, ...],
    ) -> int:
        eligible_date_counts = [
            sum(
                1 for rule_id, _ in context.homeroom_first_date_variables if rule_id == rule.rule_id
            )
            for rule in rules
        ]
        if not eligible_date_counts:
            return 0
        return min(max(date_count - 1, 0) for date_count in eligible_date_counts)

    def _priority_phase_seconds(
        self,
        total_seconds: float,
        remaining_seconds: float,
        remaining_priority_count: int,
        lower_priority_reserve_ratio: float,
    ) -> float:
        if remaining_priority_count == 0:
            return remaining_seconds
        requested_reserve = total_seconds * lower_priority_reserve_ratio * remaining_priority_count
        equitable_reserve = (
            remaining_seconds * remaining_priority_count / (remaining_priority_count + 1)
        )
        return max(
            remaining_seconds - min(requested_reserve, equitable_reserve),
            0.001,
        )

    def _lower_priority_reserve_ratio(self, priority_count: int) -> float:
        if priority_count <= 1:
            return 0.0
        return self._LOWER_PRIORITY_TOTAL_RESERVE_RATIO / (priority_count - 1)

    def _new_solver(
        self,
        request: GenerationRequestModel,
        max_solve_seconds: float,
        *,
        fix_hinted_variables: bool = False,
        random_seed_offset: int = 0,
    ) -> cp_model.CpSolver:
        solver = cp_model.CpSolver()
        solver.parameters.num_search_workers = request.num_search_workers
        solver.parameters.random_seed = request.random_seed + random_seed_offset
        solver.parameters.max_time_in_seconds = max_solve_seconds
        solver.parameters.fix_variables_to_their_hinted_value = fix_hinted_variables
        return solver

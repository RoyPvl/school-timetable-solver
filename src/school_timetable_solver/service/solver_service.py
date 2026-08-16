from __future__ import annotations

import logging
from collections import Counter, defaultdict
from dataclasses import replace
from datetime import date
from time import perf_counter

from ortools.sat.python import cp_model

from school_timetable_solver.constraint.hard_constraints import (
    DAY_LEVEL_MASTER_CONSTRAINTS,
    HardConstraint,
)
from school_timetable_solver.constraint.soft_constraints import SoftConstraint
from school_timetable_solver.constraint.solver_context import SolverContext
from school_timetable_solver.model.input_models import InputDataModel
from school_timetable_solver.model.result_models import (
    GenerationRequestModel,
    ScheduledLessonDraftModel,
    ScheduledTeacherDayOffModel,
    SolverResultModel,
)
from school_timetable_solver.model.solver_models import (
    CandidateBuildResultModel,
    DayLevelAssignmentKeyModel,
    DayLevelInfeasibilityCutModel,
    DayLevelMasterSolutionModel,
    DecompositionIterationStatisticsModel,
    ResolvedRuleSetModel,
    SolverStatisticsModel,
)

LOGGER = logging.getLogger(__name__)


class TimetableSolverService:
    """Build and solve one deterministic strict CP-SAT model."""

    _LOWER_PRIORITY_TOTAL_RESERVE_RATIO = 0.75
    _HOMEROOM_INITIAL_FEASIBILITY_RATIO = 0.60
    _PRELIMINARY_DEFERRED_HARD_RULE_IDS = frozenset({"H16"})
    _DECOMPOSITION_BUDGET_RATIO = 0.60
    _DECOMPOSITION_MINIMUM_TOTAL_SECONDS = 60.0
    _DECOMPOSITION_MAX_ITERATIONS = 100

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
        decomposition_wall_time = 0.0
        if request.max_solve_seconds >= self._DECOMPOSITION_MINIMUM_TOTAL_SECONDS and any(
            rule.enabled for rule in input_data.teacher_day_off_rules
        ):
            (
                decomposition_hint,
                decomposition_wall_time,
                decomposition_proved_infeasible,
            ) = self._find_decomposed_hard_solution(
                request,
                input_data,
                resolved_rules,
                candidate_result,
            )
            if decomposition_proved_infeasible:
                return SolverResultModel(
                    lessons=(),
                    teacher_day_offs=(),
                    statistics=SolverStatisticsModel(
                        status="INFEASIBLE",
                        wall_time_seconds=decomposition_wall_time,
                        variable_count=len(variables),
                        constraint_rule_ids=tuple(
                            constraint.rule_id for constraint in self._hard_constraints
                        ),
                    ),
                )
            if decomposition_hint is not None:
                candidate_values, day_off_values = decomposition_hint
                for candidate_id, value in candidate_values.items():
                    context.model.add_hint(variables[candidate_id], value)
                for key, value in day_off_values.items():
                    day_off = context.model.new_bool_var(
                        f"teacher_day_off__{key[0]}__{key[1].isoformat()}"
                    )
                    context.teacher_day_off_variables[key] = day_off
                    context.model.add_hint(day_off, value)
                LOGGER.info(
                    "分解探索で完全Hard解を取得 hints=%d day_off_hints=%d wall_time=%f",
                    len(candidate_values),
                    len(day_off_values),
                    decomposition_wall_time,
                )
        soft_constraints_by_priority: dict[int, list[SoftConstraint]] = defaultdict(list)
        for constraint in self._soft_constraints:
            soft_constraints_by_priority[constraint.priority].append(constraint)

        priorities = sorted(soft_constraints_by_priority, reverse=True)
        solve_request = request
        if decomposition_wall_time > 0:
            solve_request = replace(
                request,
                max_solve_seconds=max(request.max_solve_seconds - decomposition_wall_time, 0.001),
            )
        if priorities:
            solver, status, total_wall_time = self._solve_soft_priorities(
                solve_request,
                context,
                variables,
                soft_constraints_by_priority,
                priorities,
            )
        else:
            for constraint in self._hard_constraints:
                self._apply_constraint(context, constraint, "hard_only")
            LOGGER.info(
                (
                    "Solverフェーズ開始 phase=hard_only max_seconds=%f "
                    "variables=%d constraints=%d hints=%d"
                ),
                solve_request.max_solve_seconds,
                len(context.model.proto.variables),
                len(context.model.proto.constraints),
                len(context.model.proto.solution_hint.vars),
            )
            solver = self._new_solver(solve_request, solve_request.max_solve_seconds)
            status = solver.status_name(solver.solve(context.model))
            total_wall_time = solver.wall_time
            LOGGER.info(
                "Solverフェーズ終了 phase=hard_only status=%s wall_time=%f",
                status,
                solver.wall_time,
            )
            self._log_search_statistics("hard_only", solver)

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
        teacher_day_offs: list[ScheduledTeacherDayOffModel] = []
        if solver is not None and status in {"OPTIMAL", "FEASIBLE"}:
            teacher_day_offs = [
                ScheduledTeacherDayOffModel(teacher_id, target_date)
                for (teacher_id, target_date), variable in context.teacher_day_off_variables.items()
                if solver.value(variable)
            ]
            teacher_day_offs.sort(key=lambda item: (item.target_date, item.teacher_id))
        result = SolverResultModel(
            lessons=tuple(lessons),
            teacher_day_offs=tuple(teacher_day_offs),
            statistics=SolverStatisticsModel(
                status=status,
                wall_time_seconds=total_wall_time + decomposition_wall_time,
                variable_count=len(variables),
                constraint_rule_ids=tuple(context.applied_rule_ids),
            ),
        )
        return result

    def _find_decomposed_hard_solution(
        self,
        request: GenerationRequestModel,
        input_data: InputDataModel,
        resolved_rules: ResolvedRuleSetModel,
        candidate_result: CandidateBuildResultModel,
    ) -> tuple[tuple[dict[str, int], dict[tuple[str, date], int]] | None, float, bool]:
        """Iterate a relaxed daily master and an exact period-placement subproblem."""

        budget = request.max_solve_seconds * self._DECOMPOSITION_BUDGET_RATIO
        started_at = perf_counter()
        master_context, _ = self._build_solver_context(
            input_data,
            resolved_rules,
            candidate_result,
        )
        for constraint in DAY_LEVEL_MASTER_CONSTRAINTS:
            self._apply_constraint(master_context, constraint, "day_master")
        master_groups = self._daily_assignment_groups(master_context)
        cuts: list[DayLevelInfeasibilityCutModel] = []
        iteration_statistics: list[DecompositionIterationStatisticsModel] = []

        for iteration in range(1, self._DECOMPOSITION_MAX_ITERATIONS + 1):
            elapsed = perf_counter() - started_at
            remaining = budget - elapsed
            if remaining <= 0.001:
                break
            master_seconds = min(30.0, max(remaining * 0.80, 0.001))
            master_solver = self._new_solver(request, master_seconds)
            master_status = master_solver.status_name(master_solver.solve(master_context.model))
            LOGGER.info(
                "分解探索 iteration=%d phase=master status=%s wall_time=%f cuts=%d",
                iteration,
                master_status,
                master_solver.wall_time,
                len(cuts),
            )
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
            (
                sub_solver,
                sub_status,
                sub_context,
                assumption_map,
            ) = self._solve_period_subproblem(
                request,
                input_data,
                resolved_rules,
                candidate_result,
                master_solution,
                sub_seconds,
            )
            core_indices: tuple[int, ...] = ()
            if sub_status == "INFEASIBLE":
                core_indices = tuple(sub_solver.sufficient_assumptions_for_infeasibility())
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
            LOGGER.info(
                (
                    "分解探索 iteration=%d phase=subproblem status=%s wall_time=%f "
                    "assumptions=%d core=%d"
                ),
                iteration,
                sub_status,
                sub_solver.wall_time,
                len(assumption_map),
                len(core_indices),
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
                # UNKNOWN is not evidence that the selected daily pattern is impossible.
                break
            cut = self._cut_from_infeasible_core(
                master_solution,
                core_indices,
                assumption_map,
            )
            self._add_day_level_cut(master_context, master_groups, cut, len(cuts) + 1)
            cuts.append(cut)

        LOGGER.info(
            "分解探索終了 status=NO_COMPLETE_SOLUTION iterations=%d cuts=%d wall_time=%f",
            len(iteration_statistics),
            len(cuts),
            perf_counter() - started_at,
        )
        return None, perf_counter() - started_at, False

    def _daily_assignment_groups(
        self,
        context: SolverContext,
    ) -> dict[DayLevelAssignmentKeyModel, list[cp_model.IntVar]]:
        groups: dict[DayLevelAssignmentKeyModel, list[cp_model.IntVar]] = defaultdict(list)
        for candidate in context.candidates:
            key = DayLevelAssignmentKeyModel(
                candidate.requirement_id,
                candidate.target_date,
                candidate.teacher_id,
                candidate.campus_id,
            )
            groups[key].append(context.assignment_variables[candidate.candidate_id])
        return dict(groups)

    def _read_day_level_solution(
        self,
        context: SolverContext,
        groups: dict[DayLevelAssignmentKeyModel, list[cp_model.IntVar]],
        solver: cp_model.CpSolver,
    ) -> DayLevelMasterSolutionModel:
        return DayLevelMasterSolutionModel(
            assignment_counts=tuple(
                (key, sum(solver.value(variable) for variable in variables))
                for key, variables in sorted(
                    groups.items(),
                    key=lambda item: (
                        item[0].requirement_id,
                        item[0].target_date,
                        item[0].teacher_id,
                        item[0].campus_id,
                    ),
                )
            ),
            teacher_day_offs=tuple(
                (teacher_id, target_date, solver.value(variable))
                for (teacher_id, target_date), variable in sorted(
                    context.teacher_day_off_variables.items()
                )
            ),
        )

    def _solve_period_subproblem(
        self,
        request: GenerationRequestModel,
        input_data: InputDataModel,
        resolved_rules: ResolvedRuleSetModel,
        candidate_result: CandidateBuildResultModel,
        master_solution: DayLevelMasterSolutionModel,
        max_seconds: float,
    ) -> tuple[
        cp_model.CpSolver,
        str,
        SolverContext,
        dict[int, tuple[str, object, int]],
    ]:
        context, _ = self._build_solver_context(input_data, resolved_rules, candidate_result)
        for constraint in self._hard_constraints:
            self._apply_constraint(context, constraint, "period_subproblem")
        groups = self._daily_assignment_groups(context)
        assumption_map: dict[int, tuple[str, object, int]] = {}
        for index, (key, value) in enumerate(master_solution.assignment_counts):
            literal = context.model.new_bool_var(f"daily_count_assumption__{index}")
            context.model.add(sum(groups[key]) == value).only_enforce_if(literal)
            context.model.add_assumption(literal)
            assumption_map[literal.index] = ("assignment", key, value)
        offset = len(master_solution.assignment_counts)
        for index, (teacher_id, target_date, value) in enumerate(master_solution.teacher_day_offs):
            literal = context.model.new_bool_var(f"day_off_assumption__{offset + index}")
            context.model.add(
                context.teacher_day_off_variables[(teacher_id, target_date)] == value
            ).only_enforce_if(literal)
            context.model.add_assumption(literal)
            assumption_map[literal.index] = (
                "day_off",
                (teacher_id, target_date),
                value,
            )
        solver = self._new_solver(request, max_seconds)
        status = solver.status_name(solver.solve(context.model))
        return solver, status, context, assumption_map

    def _cut_from_infeasible_core(
        self,
        solution: DayLevelMasterSolutionModel,
        core_indices: tuple[int, ...],
        assumption_map: dict[int, tuple[str, object, int]],
    ) -> DayLevelInfeasibilityCutModel:
        entries = [assumption_map[index] for index in core_indices if index in assumption_map]
        if not entries:
            return DayLevelInfeasibilityCutModel(
                solution.assignment_counts,
                solution.teacher_day_offs,
            )
        return DayLevelInfeasibilityCutModel(
            tuple(
                (key, value)
                for kind, key, value in entries
                if kind == "assignment" and isinstance(key, DayLevelAssignmentKeyModel)
            ),
            tuple(
                (key[0], key[1], value)
                for kind, key, value in entries
                if kind == "day_off" and isinstance(key, tuple)
            ),
        )

    def _add_day_level_cut(
        self,
        context: SolverContext,
        groups: dict[DayLevelAssignmentKeyModel, list[cp_model.IntVar]],
        cut: DayLevelInfeasibilityCutModel,
        cut_number: int,
    ) -> None:
        equalities: list[cp_model.IntVar] = []
        for index, (key, value) in enumerate(cut.assignment_counts):
            equality = context.model.new_bool_var(f"cut__{cut_number}__count__{index}")
            expression = sum(groups[key])
            context.model.add(expression == value).only_enforce_if(equality)
            context.model.add(expression != value).only_enforce_if(equality.negated())
            equalities.append(equality)
        offset = len(cut.assignment_counts)
        for index, (teacher_id, target_date, value) in enumerate(cut.teacher_day_offs):
            equality = context.model.new_bool_var(f"cut__{cut_number}__off__{offset + index}")
            variable = context.teacher_day_off_variables[(teacher_id, target_date)]
            context.model.add(variable == value).only_enforce_if(equality)
            context.model.add(variable != value).only_enforce_if(equality.negated())
            equalities.append(equality)
        if equalities:
            context.model.add_bool_or([equality.negated() for equality in equalities])

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
        period_ids = {period.period_id for period in input_data.periods}
        teacher_home_campuses = {
            teacher.teacher_id: teacher.home_campus_id
            for teacher in input_data.teachers
            if teacher.enabled
        }
        fixed_teacher_leave_cell_counts: Counter[tuple[str, date]] = Counter()
        subjects_by_class: dict[str, set[str]] = {}
        for requirement in input_data.lesson_requirements:
            if requirement.enabled:
                subjects_by_class.setdefault(requirement.class_id, set()).add(
                    requirement.subject_id
                )
        single_subject_class_ids = frozenset(
            class_id for class_id, subject_ids in subjects_by_class.items() if len(subject_ids) == 1
        )
        for leave in input_data.teacher_leaves:
            campus_id = teacher_home_campuses[leave.teacher_id]
            required_cells = 1 if set(leave.unavailable_period_ids) == period_ids else 2
            fixed_teacher_leave_cell_counts[(campus_id, leave.target_date)] += required_cells
        context = SolverContext(
            model=model,
            candidates=candidate_result.candidates,
            assignment_variables=variables,
            required_counts={
                requirement.requirement_id: requirement.required_periods
                for requirement in input_data.lesson_requirements
                if requirement.enabled
            },
            single_subject_class_ids=single_subject_class_ids,
            room_capacities=dict(
                Counter(
                    room.campus_id
                    for room in input_data.rooms
                    if room.enabled and room.campus_id in enabled_campus_ids
                )
            ),
            room_priorities_by_campus={
                campus_id: tuple(
                    room.priority
                    for room in sorted(
                        (
                            room
                            for room in input_data.rooms
                            if room.enabled and room.campus_id == campus_id
                        ),
                        key=lambda item: item.output_order,
                    )
                )
                for campus_id in enabled_campus_ids
            },
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
            teacher_first_last_period_forbidden={
                (rule.teacher_id, rule.target_date): bool(rule.forbid_first_last_same_day)
                for rule in resolved_rules.teacher_date_rules
            },
            class_attendance_limits={
                (rule.class_id, rule.target_date): rule.attendance_streak_limit
                for rule in resolved_rules.class_date_rules
            },
            class_required_lesson_periods={
                (rule.class_id, rule.target_date): rule.required_lesson_period_ids
                for rule in resolved_rules.class_date_rules
                if rule.required_lesson_period_ids
            },
            period_orders={period.period_id: period.output_order for period in input_data.periods},
            calendar_dates=tuple(
                sorted(day.target_date for day in input_data.calendar_days if day.output_enabled)
            ),
            class_attendance_preference_limits={
                (rule.class_id, rule.target_date): rule.preferred_attendance_streak_limit
                for rule in resolved_rules.class_date_rules
            },
            attendance_group_class_ids={
                group.group_id: group.class_ids for group in resolved_rules.attendance_groups
            },
            attendance_group_limits={
                (group.group_id, target_date): limit
                for group in resolved_rules.attendance_groups
                for target_date, limit in group.attendance_streak_limits
            },
            attendance_group_preference_limits={
                (group.group_id, target_date): limit
                for group in resolved_rules.attendance_groups
                for target_date, limit in group.preferred_attendance_streak_limits
            },
            lesson_count_rules=resolved_rules.lesson_count_rules,
            teacher_day_off_rules=input_data.teacher_day_off_rules,
            teacher_home_campuses=teacher_home_campuses,
            fixed_teacher_leave_cell_counts=dict(fixed_teacher_leave_cell_counts),
            lesson_count_preference_rules=resolved_rules.lesson_count_preference_rules,
            homeroom_boundary_rules=resolved_rules.homeroom_boundary_rules,
            class_pair_overlap_rules=input_data.class_pair_overlap_rules,
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
        deferred_hard_constraints = [
            (index, constraint)
            for index, constraint in enumerate(self._hard_constraints)
            if constraint.rule_id in self._PRELIMINARY_DEFERRED_HARD_RULE_IDS
        ]
        for constraint in self._hard_constraints:
            if constraint.rule_id not in self._PRELIMINARY_DEFERRED_HARD_RULE_IDS:
                self._apply_constraint(context, constraint, "preliminary_feasibility")

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
        total_wall_time = 0.0
        if deferred_hard_constraints:
            deferred_rule_ids = ",".join(
                constraint.rule_id for _, constraint in deferred_hard_constraints
            )
            LOGGER.info(
                (
                    "Solverフェーズ開始 phase=preliminary_feasibility "
                    "deferred_rule_ids=%s max_seconds=%f variables=%d constraints=%d hints=%d"
                ),
                deferred_rule_ids,
                first_phase_seconds,
                len(context.model.proto.variables),
                len(context.model.proto.constraints),
                len(context.model.proto.solution_hint.vars),
            )
            preliminary_solver = self._new_solver(request, first_phase_seconds)
            preliminary_status = preliminary_solver.status_name(
                preliminary_solver.solve(context.model)
            )
            total_wall_time = preliminary_solver.wall_time
            LOGGER.info(
                (
                    "Solverフェーズ終了 phase=preliminary_feasibility "
                    "deferred_rule_ids=%s status=%s wall_time=%f"
                ),
                deferred_rule_ids,
                preliminary_status,
                preliminary_solver.wall_time,
            )
            self._log_search_statistics("preliminary_feasibility", preliminary_solver)
            if preliminary_status not in {"OPTIMAL", "FEASIBLE"}:
                return preliminary_solver, preliminary_status, total_wall_time

        for rule_index, constraint in deferred_hard_constraints:
            self._apply_constraint(context, constraint, "initial_feasibility")
            applied_rule_id = context.applied_rule_ids.pop()
            context.applied_rule_ids.insert(rule_index, applied_rule_id)
        if preliminary_solver is not None and preliminary_status in {"OPTIMAL", "FEASIBLE"}:
            for variable in variables.values():
                context.model.add_hint(variable, preliminary_solver.value(variable))

        initial_feasibility_seconds = max(
            first_phase_seconds - total_wall_time,
            0.001,
        )
        LOGGER.info(
            (
                "Solverフェーズ開始 phase=initial_feasibility max_seconds=%f "
                "variables=%d constraints=%d hints=%d"
            ),
            initial_feasibility_seconds,
            len(context.model.proto.variables),
            len(context.model.proto.constraints),
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
        self._log_search_statistics("initial_feasibility", initial_solver)
        if initial_status not in {"OPTIMAL", "FEASIBLE"}:
            return initial_solver, initial_status, total_wall_time

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
                self._apply_constraint(context, constraint, f"soft_{priority}")
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
                (
                    "Solverフェーズ開始 phase=soft priority=%d rule_ids=%s "
                    "max_seconds=%f variables=%d constraints=%d hints=%d"
                ),
                priority,
                rule_ids,
                phase_seconds,
                len(context.model.proto.variables),
                len(context.model.proto.constraints),
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
            self._log_search_statistics(f"soft_{priority}", phase_solver)
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

    def _apply_constraint(
        self,
        context: SolverContext,
        constraint: HardConstraint | SoftConstraint,
        phase: str,
    ) -> None:
        variable_count_before = len(context.model.proto.variables)
        constraint_count_before = len(context.model.proto.constraints)
        started_at = perf_counter()
        constraint.apply(context)
        LOGGER.info(
            (
                "Solver制約追加 phase=%s rule_id=%s elapsed=%f "
                "variables_added=%d constraints_added=%d variables_total=%d constraints_total=%d"
            ),
            phase,
            constraint.rule_id,
            perf_counter() - started_at,
            len(context.model.proto.variables) - variable_count_before,
            len(context.model.proto.constraints) - constraint_count_before,
            len(context.model.proto.variables),
            len(context.model.proto.constraints),
        )

    def _log_search_statistics(self, phase: str, solver: cp_model.CpSolver) -> None:
        LOGGER.info(
            "Solver探索統計 phase=%s conflicts=%d branches=%d",
            phase,
            self._solver_integer_metric(solver, "num_conflicts"),
            self._solver_integer_metric(solver, "num_branches"),
        )

    def _solver_integer_metric(self, solver: cp_model.CpSolver, name: str) -> int:
        try:
            return int(getattr(solver, name))
        except (AttributeError, RuntimeError, TypeError, ValueError):
            return -1

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
    ) -> cp_model.CpSolver:
        solver = cp_model.CpSolver()
        solver.parameters.num_search_workers = request.num_search_workers
        solver.parameters.random_seed = request.random_seed
        solver.parameters.max_time_in_seconds = max_solve_seconds
        return solver

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from datetime import date
from time import perf_counter

from ortools.sat.python import cp_model

from school_timetable_solver.constraint.hard_constraints import HardConstraint
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
    ResolvedRuleSetModel,
    SolverStatisticsModel,
)

LOGGER = logging.getLogger(__name__)


class TimetableSolverService:
    """Build and solve one deterministic strict CP-SAT model."""

    _LOWER_PRIORITY_TOTAL_RESERVE_RATIO = 0.75
    _HOMEROOM_INITIAL_FEASIBILITY_RATIO = 0.60
    _PRELIMINARY_DEFERRED_HARD_RULE_IDS = frozenset({"H16"})

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
                self._apply_constraint(context, constraint, "hard_only")
            LOGGER.info(
                (
                    "Solverフェーズ開始 phase=hard_only max_seconds=%f "
                    "variables=%d constraints=%d hints=%d"
                ),
                request.max_solve_seconds,
                len(context.model.proto.variables),
                len(context.model.proto.constraints),
                len(context.model.proto.solution_hint.vars),
            )
            solver = self._new_solver(request, request.max_solve_seconds)
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
        return SolverResultModel(
            lessons=tuple(lessons),
            teacher_day_offs=tuple(teacher_day_offs),
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
        period_ids = {period.period_id for period in input_data.periods}
        teacher_home_campuses = {
            teacher.teacher_id: teacher.home_campus_id
            for teacher in input_data.teachers
            if teacher.enabled
        }
        fixed_teacher_leave_cell_counts: Counter[tuple[str, date]] = Counter()
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
            lesson_count_rules=resolved_rules.lesson_count_rules,
            teacher_day_off_rules=input_data.teacher_day_off_rules,
            teacher_home_campuses=teacher_home_campuses,
            fixed_teacher_leave_cell_counts=dict(fixed_teacher_leave_cell_counts),
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

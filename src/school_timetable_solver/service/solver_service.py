from __future__ import annotations

from collections import Counter, defaultdict

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
    ResolvedRuleSetModel,
    SolverStatisticsModel,
)


class TimetableSolverService:
    """Build and solve one deterministic strict CP-SAT model."""

    _LOWER_PRIORITY_TOTAL_RESERVE_RATIO = 0.75

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
            lesson_count_rules=resolved_rules.lesson_count_rules,
        )
        for constraint in self._hard_constraints:
            constraint.apply(context)
        soft_constraints_by_priority: dict[int, list[SoftConstraint]] = defaultdict(list)
        for constraint in self._soft_constraints:
            soft_constraints_by_priority[constraint.priority].append(constraint)

        priorities = sorted(soft_constraints_by_priority, reverse=True)
        assignment_priorities = {
            constraint.priority
            for constraint in self._soft_constraints
            if constraint.optimization_scope == "assignment"
        }
        last_assignment_priority = min(assignment_priorities) if assignment_priorities else None
        total_wall_time = 0.0
        solved_variable_count = 0
        solver: cp_model.CpSolver | None = None
        status = "UNKNOWN"
        if not priorities:
            solver = self._new_solver(request, request.max_solve_seconds)
            status = solver.status_name(solver.solve(model))
            total_wall_time = solver.wall_time
        else:
            remaining_seconds = request.max_solve_seconds
            lower_priority_reserve_ratio = self._lower_priority_reserve_ratio(len(priorities))
            for priority_index, priority in enumerate(priorities):
                for constraint in soft_constraints_by_priority[priority]:
                    constraint.apply(context)
                priority_terms = context.penalty_terms_by_priority.get(priority, [])
                model.minimize(sum(priority_terms))
                model.clear_hints()
                if solver is None:
                    for penalty in priority_terms:
                        model.add_hint(penalty, 0)
                else:
                    for variable_index in range(solved_variable_count):
                        variable = model.get_int_var_from_proto_index(variable_index)
                        model.add_hint(variable, solver.value(variable))

                is_last_priority = priority_index == len(priorities) - 1
                remaining_priority_count = len(priorities) - priority_index - 1
                if is_last_priority:
                    phase_seconds = remaining_seconds
                else:
                    requested_reserve = (
                        request.max_solve_seconds
                        * lower_priority_reserve_ratio
                        * remaining_priority_count
                    )
                    equitable_reserve = (
                        remaining_seconds
                        * remaining_priority_count
                        / (remaining_priority_count + 1)
                    )
                    phase_seconds = max(
                        remaining_seconds - min(requested_reserve, equitable_reserve),
                        0.001,
                    )
                phase_solver = self._new_solver(request, phase_seconds)
                phase_status = phase_solver.status_name(phase_solver.solve(model))
                total_wall_time += phase_solver.wall_time
                remaining_seconds = max(
                    request.max_solve_seconds - total_wall_time,
                    0.001,
                )
                if phase_status not in {"OPTIMAL", "FEASIBLE"}:
                    if solver is None:
                        status = phase_status
                    break

                solver = phase_solver
                solved_variable_count = len(model.proto.variables)
                status = phase_status
                if not is_last_priority:
                    achieved_penalty = sum(solver.value(penalty) for penalty in priority_terms)
                    model.add(sum(priority_terms) <= achieved_penalty)
                    for group_terms in context.penalty_term_groups_by_priority.get(
                        priority,
                        {},
                    ).values():
                        achieved_group_penalty = sum(
                            solver.value(penalty) for penalty in group_terms
                        )
                        model.add(sum(group_terms) <= achieved_group_penalty)
                    if priority == last_assignment_priority:
                        for variable in variables.values():
                            model.add(variable == solver.value(variable))
            if len(priorities) > 1 and status == "OPTIMAL":
                status = "FEASIBLE"

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

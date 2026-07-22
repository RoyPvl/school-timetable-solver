from __future__ import annotations

from ortools.sat.python import cp_model

from school_timetable_solver.constraint.hard_constraints import HardConstraint
from school_timetable_solver.constraint.solver_context import SolverContext
from school_timetable_solver.model.input_models import InputDataModel
from school_timetable_solver.model.result_models import ScheduledLessonModel, SolverResultModel
from school_timetable_solver.model.solver_models import (
    CandidateBuildResultModel,
    ResolvedRuleSetModel,
    SolverStatisticsModel,
)


class TimetableSolverService:
    """Build and solve one deterministic CP-SAT feasibility model."""

    def __init__(self, hard_constraints: tuple[HardConstraint, ...]) -> None:
        self._hard_constraints = hard_constraints

    def execute(
        self,
        input_data: InputDataModel,
        resolved_rules: ResolvedRuleSetModel,
        candidate_result: CandidateBuildResultModel,
    ) -> SolverResultModel:
        model = cp_model.CpModel()
        variables = {
            candidate.candidate_id: model.new_bool_var(f"x__{candidate.candidate_id}")
            for candidate in candidate_result.candidates
        }
        context = SolverContext(
            model=model,
            candidates=candidate_result.candidates,
            assignment_variables=variables,
            required_counts={
                requirement.requirement_id: requirement.required_periods
                for requirement in input_data.lesson_requirements
            },
            fixed_lessons=input_data.fixed_lessons,
            class_daily_limits={
                (rule.class_id, rule.target_date): rule.daily_hard_limit
                for rule in resolved_rules.class_date_rules
            },
            requirement_daily_limits={
                requirement.requirement_id: requirement.max_periods_per_day
                for requirement in input_data.lesson_requirements
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
            teacher_transfer_gaps={
                teacher.teacher_id: teacher.required_transfer_gap for teacher in input_data.teachers
            },
            teacher_can_transfer={
                teacher.teacher_id: teacher.can_transfer_campus for teacher in input_data.teachers
            },
            period_orders={
                period.period_id: order
                for order, period in enumerate(
                    sorted(input_data.periods, key=lambda item: item.sort_order), start=1
                )
            },
            calendar_dates=tuple(sorted(day.target_date for day in input_data.calendar_days)),
        )
        for constraint in self._hard_constraints:
            constraint.apply(context)

        solver = cp_model.CpSolver()
        solver.parameters.num_search_workers = 1
        solver.parameters.random_seed = input_data.settings.random_seed
        solver.parameters.max_time_in_seconds = input_data.settings.max_solve_seconds
        status_code = solver.solve(model)
        status = solver.status_name(status_code)
        lessons: list[ScheduledLessonModel] = []
        if status in {"OPTIMAL", "FEASIBLE"}:
            for candidate in candidate_result.candidates:
                if solver.value(variables[candidate.candidate_id]):
                    lessons.append(
                        ScheduledLessonModel(
                            requirement_id=candidate.requirement_id,
                            target_date=candidate.target_date,
                            period_id=candidate.period_id,
                            teacher_id=candidate.teacher_id,
                            room_id=candidate.room_id,
                            campus_id=candidate.campus_id,
                            class_id=candidate.class_id,
                            subject_id=candidate.subject_id,
                        )
                    )
        lessons.sort(
            key=lambda item: (
                item.target_date,
                context.period_orders[item.period_id],
                item.class_id,
                item.subject_id,
            )
        )
        return SolverResultModel(
            lessons=tuple(lessons),
            statistics=SolverStatisticsModel(
                status=status,
                wall_time_seconds=solver.wall_time,
                variable_count=len(variables),
                constraint_rule_ids=tuple(context.applied_rule_ids),
            ),
        )

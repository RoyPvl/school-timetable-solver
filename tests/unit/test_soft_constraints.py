from __future__ import annotations

from datetime import date, timedelta

from ortools.sat.python import cp_model

from school_timetable_solver.constraint.hard_constraints import (
    ClassRoomContinuityConstraint,
)
from school_timetable_solver.constraint.soft_constraints import (
    ClassDailyContiguityPreferenceConstraint,
    ClassSingleLessonDayPreferenceConstraint,
    ClassSubjectConsecutiveRepeatPreferenceConstraint,
    ClassSubjectDailyRepeatPreferenceConstraint,
    ClassSubjectDoubleThenNextDayPreferenceConstraint,
    RoomChangeGapPreferenceConstraint,
)
from school_timetable_solver.constraint.solver_context import SolverContext
from school_timetable_solver.model.solver_models import CandidateSlotModel

TARGET_DATE = date(2026, 7, 27)


def _context(room_capacity: int) -> SolverContext:
    candidates = (
        CandidateSlotModel("Q1__P1", "Q1", TARGET_DATE, "P1", "T1", "C1", "CL1", "S1"),
        CandidateSlotModel("Q2__P2", "Q2", TARGET_DATE, "P2", "T2", "C1", "CL2", "S1"),
    )
    model = cp_model.CpModel()
    variables = {
        candidate.candidate_id: model.new_bool_var(candidate.candidate_id)
        for candidate in candidates
    }
    return SolverContext(
        model=model,
        candidates=candidates,
        assignment_variables=variables,
        required_counts={"Q1": 1, "Q2": 1},
        room_capacities={"C1": room_capacity},
        class_daily_limits={("CL1", TARGET_DATE): 6, ("CL2", TARGET_DATE): 6},
        requirement_daily_limits={"Q1": None, "Q2": None},
        teacher_daily_limits={("T1", TARGET_DATE): 6, ("T2", TARGET_DATE): 6},
        teacher_consecutive_limits={("T1", TARGET_DATE): 6, ("T2", TARGET_DATE): 6},
        class_attendance_limits={("CL1", TARGET_DATE): 6, ("CL2", TARGET_DATE): 6},
        period_orders={f"P{index}": index for index in range(1, 7)},
        calendar_dates=(TARGET_DATE,),
    )


def _solve(room_capacity: int) -> tuple[cp_model.CpSolver, SolverContext]:
    context = _context(room_capacity)
    ClassRoomContinuityConstraint().apply(context)
    constraint = RoomChangeGapPreferenceConstraint()
    constraint.apply(context)
    for variable in context.assignment_variables.values():
        context.model.add(variable == 1)
    context.model.minimize(sum(context.penalty_terms_by_priority[constraint.priority]))
    solver = cp_model.CpSolver()
    status = solver.status_name(solver.solve(context.model))
    assert status in {"OPTIMAL", "FEASIBLE"}
    return solver, context


def test_s10_uses_different_rooms_to_avoid_adjacent_class_change_when_possible() -> None:
    solver, context = _solve(room_capacity=2)

    assert solver.objective_value == 0
    assert solver.value(context.class_room_variables[("C1", TARGET_DATE, "CL1")]) != (
        solver.value(context.class_room_variables[("C1", TARGET_DATE, "CL2")])
    )


def test_s10_allows_adjacent_class_change_when_only_one_room_exists() -> None:
    solver, _ = _solve(room_capacity=1)

    assert solver.objective_value == 1


def _solve_class_day_preference(
    constraint: (
        ClassDailyContiguityPreferenceConstraint
        | ClassSingleLessonDayPreferenceConstraint
        | ClassSubjectConsecutiveRepeatPreferenceConstraint
        | ClassSubjectDailyRepeatPreferenceConstraint
    ),
    selected_period_ids: set[str],
    subject_ids_by_period: dict[str, str] | None = None,
) -> tuple[cp_model.CpSolver, SolverContext]:
    subject_ids = subject_ids_by_period or {}
    candidates = tuple(
        CandidateSlotModel(
            f"Q{period_index}__P{period_index}",
            f"Q{period_index}",
            TARGET_DATE,
            f"P{period_index}",
            f"T{period_index}",
            "C1",
            "CL1",
            subject_ids.get(f"P{period_index}", "S1"),
        )
        for period_index in range(1, 7)
    )
    model = cp_model.CpModel()
    variables = {
        candidate.candidate_id: model.new_bool_var(candidate.candidate_id)
        for candidate in candidates
    }
    context = SolverContext(
        model=model,
        candidates=candidates,
        assignment_variables=variables,
        required_counts={candidate.requirement_id: 1 for candidate in candidates},
        room_capacities={"C1": 1},
        class_daily_limits={("CL1", TARGET_DATE): 6},
        requirement_daily_limits={candidate.requirement_id: None for candidate in candidates},
        teacher_daily_limits={(candidate.teacher_id, TARGET_DATE): 6 for candidate in candidates},
        teacher_consecutive_limits={
            (candidate.teacher_id, TARGET_DATE): 6 for candidate in candidates
        },
        class_attendance_limits={("CL1", TARGET_DATE): 6},
        period_orders={f"P{index}": index for index in range(1, 7)},
        calendar_dates=(TARGET_DATE,),
    )
    ClassRoomContinuityConstraint().apply(context)
    constraint.apply(context)
    for candidate in candidates:
        context.model.add(
            variables[candidate.candidate_id] == (candidate.period_id in selected_period_ids)
        )
    context.model.minimize(sum(context.penalty_terms_by_priority[constraint.priority]))
    solver = cp_model.CpSolver()
    status = solver.status_name(solver.solve(context.model))
    assert status == "OPTIMAL"
    return solver, context


def test_s11_has_no_penalty_for_one_contiguous_class_block() -> None:
    solver, _ = _solve_class_day_preference(
        ClassDailyContiguityPreferenceConstraint(),
        {"P2", "P3", "P4"},
    )

    assert solver.objective_value == 0


def test_s11_counts_one_split_class_day_even_with_multiple_empty_periods() -> None:
    solver, _ = _solve_class_day_preference(
        ClassDailyContiguityPreferenceConstraint(),
        {"P1", "P4"},
    )

    assert solver.objective_value == 1


def test_s12_penalizes_only_class_days_with_exactly_one_lesson() -> None:
    objectives = []
    for selected_period_ids in (set(), {"P2"}, {"P2", "P3"}):
        solver, _ = _solve_class_day_preference(
            ClassSingleLessonDayPreferenceConstraint(),
            selected_period_ids,
        )
        objectives.append(solver.objective_value)

    assert objectives == [0, 1, 0]


def test_s13_counts_each_adjacent_same_subject_pair() -> None:
    objectives = []
    for selected_period_ids in (
        set(),
        {"P2"},
        {"P2", "P3"},
        {"P2", "P3", "P4"},
        {"P2", "P4"},
    ):
        solver, _ = _solve_class_day_preference(
            ClassSubjectConsecutiveRepeatPreferenceConstraint(),
            selected_period_ids,
        )
        objectives.append(solver.objective_value)

    assert objectives == [0, 0, 1, 2, 0]


def test_s13_does_not_penalize_adjacent_different_subjects() -> None:
    solver, _ = _solve_class_day_preference(
        ClassSubjectConsecutiveRepeatPreferenceConstraint(),
        {"P2", "P3"},
        {"P2": "S1", "P3": "S2"},
    )

    assert solver.objective_value == 0


def test_s14_counts_same_day_class_subject_pairs() -> None:
    objectives = []
    for selected_period_ids in (
        set(),
        {"P2"},
        {"P2", "P4"},
        {"P2", "P3", "P4"},
    ):
        solver, context = _solve_class_day_preference(
            ClassSubjectDailyRepeatPreferenceConstraint(),
            selected_period_ids,
        )
        objectives.append(solver.objective_value)
        assert ("CL1", "S1") in context.penalty_term_groups_by_priority[
            ClassSubjectDailyRepeatPreferenceConstraint.priority
        ]

    assert objectives == [0, 0, 1, 3]


def _solve_s15(
    selected_slots: set[tuple[int, str]],
) -> cp_model.CpSolver:
    dates = tuple(TARGET_DATE + timedelta(days=offset) for offset in range(3))
    candidates = tuple(
        CandidateSlotModel(
            f"Q{day_offset}_{period_id}__{day_offset}_{period_id}",
            f"Q{day_offset}_{period_id}",
            dates[day_offset],
            period_id,
            f"T{day_offset}_{period_id}",
            "C1",
            "CL1",
            "S1",
        )
        for day_offset in range(3)
        for period_id in ("P1", "P2")
    )
    model = cp_model.CpModel()
    variables = {
        candidate.candidate_id: model.new_bool_var(candidate.candidate_id)
        for candidate in candidates
    }
    context = SolverContext(
        model=model,
        candidates=candidates,
        assignment_variables=variables,
        required_counts={candidate.requirement_id: 1 for candidate in candidates},
        room_capacities={"C1": 1},
        class_daily_limits={("CL1", target_date): 6 for target_date in dates},
        requirement_daily_limits={candidate.requirement_id: None for candidate in candidates},
        teacher_daily_limits={
            (candidate.teacher_id, candidate.target_date): 6 for candidate in candidates
        },
        teacher_consecutive_limits={
            (candidate.teacher_id, candidate.target_date): 6 for candidate in candidates
        },
        class_attendance_limits={("CL1", target_date): 6 for target_date in dates},
        period_orders={"P1": 1, "P2": 2},
        calendar_dates=dates,
    )
    constraint = ClassSubjectDoubleThenNextDayPreferenceConstraint()
    constraint.apply(context)
    for candidate in candidates:
        day_offset = (candidate.target_date - TARGET_DATE).days
        context.model.add(
            variables[candidate.candidate_id]
            == ((day_offset, candidate.period_id) in selected_slots)
        )
    context.model.minimize(sum(context.penalty_terms_by_priority[constraint.priority]))
    solver = cp_model.CpSolver()
    status = solver.status_name(solver.solve(context.model))
    assert status == "OPTIMAL"
    return solver


def test_s15_penalizes_only_the_calendar_day_after_a_double_lesson() -> None:
    double_then_next_day = _solve_s15({(0, "P1"), (0, "P2"), (1, "P1")})
    double_then_one_day_gap = _solve_s15({(0, "P1"), (0, "P2"), (2, "P1")})
    single_then_next_day = _solve_s15({(0, "P1"), (1, "P1")})

    assert double_then_next_day.objective_value == 1
    assert double_then_one_day_gap.objective_value == 0
    assert single_then_next_day.objective_value == 0


def test_soft_constraint_priorities_and_optimization_scopes_are_ordered() -> None:
    assert (
        ClassSubjectDailyRepeatPreferenceConstraint.priority
        > ClassSubjectDoubleThenNextDayPreferenceConstraint.priority
        > ClassDailyContiguityPreferenceConstraint.priority
        > ClassSingleLessonDayPreferenceConstraint.priority
        > ClassSubjectConsecutiveRepeatPreferenceConstraint.priority
        > RoomChangeGapPreferenceConstraint.priority
    )
    assert ClassSubjectDailyRepeatPreferenceConstraint.optimization_scope == "assignment"
    assert ClassSubjectDoubleThenNextDayPreferenceConstraint.optimization_scope == "assignment"
    assert ClassDailyContiguityPreferenceConstraint.optimization_scope == "assignment"
    assert ClassSingleLessonDayPreferenceConstraint.optimization_scope == "assignment"
    assert ClassSubjectConsecutiveRepeatPreferenceConstraint.optimization_scope == "assignment"
    assert RoomChangeGapPreferenceConstraint.optimization_scope == "room"

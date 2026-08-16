from __future__ import annotations

from datetime import date, timedelta

from ortools.sat.python import cp_model

from school_timetable_solver.constraint.hard_constraints import (
    ClassRoomContinuityConstraint,
    HomeroomAttendanceBoundaryConstraint,
)
from school_timetable_solver.constraint.soft_constraints import (
    ClassConsecutiveAttendancePreferenceConstraint,
    ClassDailyContiguityPreferenceConstraint,
    ClassSingleLessonDayPreferenceConstraint,
    ClassSubjectConsecutiveRepeatPreferenceConstraint,
    ClassSubjectDailyRepeatPreferenceConstraint,
    ClassSubjectDoubleThenNextDayPreferenceConstraint,
    ClassSubjectScheduleBalancePreferenceConstraint,
    HomeroomBoundarySlotPreferenceConstraint,
    LessonCountInScopePreferenceConstraint,
    RoomChangeGapPreferenceConstraint,
    RoomPriorityPreferenceConstraint,
    TeacherDayOffDistributionPreferenceConstraint,
)
from school_timetable_solver.constraint.solver_context import SolverContext
from school_timetable_solver.model.input_models import TeacherDayOffRuleModel
from school_timetable_solver.model.solver_models import (
    CandidateSlotModel,
    ResolvedHomeroomBoundaryRuleModel,
    ResolvedLessonCountPreferenceRuleModel,
)

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
        teacher_first_last_period_forbidden={
            ("T1", TARGET_DATE): False,
            ("T2", TARGET_DATE): False,
        },
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


def test_s19_avoids_lower_priority_room_when_higher_priority_room_is_available() -> None:
    context = _context(room_capacity=2)
    context.room_priorities_by_campus = {"C1": (0, 100)}
    ClassRoomContinuityConstraint().apply(context)
    constraint = RoomPriorityPreferenceConstraint()
    constraint.apply(context)
    for variable in context.assignment_variables.values():
        context.model.add(variable == 1)
    context.model.minimize(sum(context.penalty_terms_by_priority[constraint.priority]))

    solver = cp_model.CpSolver()
    status = solver.status_name(solver.solve(context.model))

    assert status == "OPTIMAL"
    assert solver.objective_value == 0
    assert {solver.value(room) for room in context.class_room_variables.values()} == {1}


def test_s19_treats_rooms_with_equal_priority_equally() -> None:
    context = _context(room_capacity=2)
    context.room_priorities_by_campus = {"C1": (100, 100)}
    ClassRoomContinuityConstraint().apply(context)
    constraint = RoomPriorityPreferenceConstraint()
    constraint.apply(context)
    for variable in context.assignment_variables.values():
        context.model.add(variable == 1)
    context.model.minimize(sum(context.penalty_terms_by_priority.get(constraint.priority, ())))

    solver = cp_model.CpSolver()
    status = solver.status_name(solver.solve(context.model))

    assert status == "OPTIMAL"
    assert solver.objective_value == 0


def _solve_s20(home_period_id: str) -> float:
    candidates = tuple(
        CandidateSlotModel(
            f"{requirement_id}__{period_id}",
            requirement_id,
            TARGET_DATE,
            period_id,
            "T1" if requirement_id == "Q_HOME" else "T2",
            "C1",
            "CL1",
            "S1",
        )
        for requirement_id in ("Q_HOME", "Q_OTHER")
        for period_id in ("P1", "P2", "P3")
    )
    model = cp_model.CpModel()
    context = SolverContext(
        model=model,
        candidates=candidates,
        assignment_variables={
            candidate.candidate_id: model.new_bool_var(candidate.candidate_id)
            for candidate in candidates
        },
        required_counts={"Q_HOME": 1, "Q_OTHER": 2},
        room_capacities={"C1": 1},
        class_daily_limits={("CL1", TARGET_DATE): 6},
        requirement_daily_limits={"Q_HOME": None, "Q_OTHER": None},
        teacher_daily_limits={("T1", TARGET_DATE): 6, ("T2", TARGET_DATE): 6},
        teacher_first_last_period_forbidden={
            ("T1", TARGET_DATE): False,
            ("T2", TARGET_DATE): False,
        },
        class_attendance_limits={("CL1", TARGET_DATE): 6},
        period_orders={"P1": 1, "P2": 2, "P3": 3},
        calendar_dates=(TARGET_DATE,),
        homeroom_boundary_rules=(
            ResolvedHomeroomBoundaryRuleModel(
                "HB1",
                "CL1",
                "C1",
                "T1",
                ("Q_HOME", "Q_OTHER"),
                ("Q_HOME",),
                TARGET_DATE,
                TARGET_DATE,
            ),
        ),
    )
    ClassRoomContinuityConstraint().apply(context)
    HomeroomAttendanceBoundaryConstraint().apply(context)
    assert not context.homeroom_first_date_variables
    assert not context.homeroom_last_date_variables
    preference = HomeroomBoundarySlotPreferenceConstraint()
    preference.apply(context)
    assert context.homeroom_first_date_variables
    assert context.homeroom_last_date_variables
    for candidate in candidates:
        selected = (
            candidate.period_id == home_period_id
            if candidate.requirement_id == "Q_HOME"
            else candidate.period_id != home_period_id
        )
        model.add(context.assignment_variables[candidate.candidate_id] == int(selected))
    model.minimize(sum(context.penalty_terms_by_priority[preference.priority]))
    solver = cp_model.CpSolver()
    assert solver.status_name(solver.solve(model)) == "OPTIMAL"
    return solver.objective_value


def test_s20_prefers_homeroom_lesson_at_first_or_last_class_slot() -> None:
    assert _solve_s20("P1") == 1
    assert _solve_s20("P2") == 2


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
        teacher_first_last_period_forbidden={
            (candidate.teacher_id, TARGET_DATE): False for candidate in candidates
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
        teacher_first_last_period_forbidden={
            (candidate.teacher_id, candidate.target_date): False for candidate in candidates
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


def _solve_s16(
    daily_period_counts: tuple[int, ...],
    selected_slots: set[tuple[int, str]],
    required_count: int,
) -> tuple[cp_model.CpSolver, SolverContext]:
    dates = tuple(
        TARGET_DATE + timedelta(days=day_offset) for day_offset in range(len(daily_period_counts))
    )
    candidates = tuple(
        CandidateSlotModel(
            f"Q1__{day_offset}__P{period_index}",
            "Q1",
            dates[day_offset],
            f"P{period_index}",
            "T1",
            "C1",
            "CL1",
            "S1",
        )
        for day_offset, period_count in enumerate(daily_period_counts)
        for period_index in range(1, period_count + 1)
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
        required_counts={"Q1": required_count},
        room_capacities={"C1": 1},
        class_daily_limits={
            ("CL1", target_date): daily_period_counts[day_offset]
            for day_offset, target_date in enumerate(dates)
        },
        requirement_daily_limits={"Q1": None},
        teacher_daily_limits={("T1", target_date): 6 for target_date in dates},
        teacher_first_last_period_forbidden={("T1", target_date): False for target_date in dates},
        class_attendance_limits={("CL1", target_date): 6 for target_date in dates},
        period_orders={
            f"P{period_index}": period_index
            for period_index in range(1, max(daily_period_counts) + 1)
        },
        calendar_dates=dates,
    )
    constraint = ClassSubjectScheduleBalancePreferenceConstraint()
    constraint.apply(context)
    for candidate in candidates:
        day_offset = (candidate.target_date - TARGET_DATE).days
        context.model.add(
            variables[candidate.candidate_id]
            == ((day_offset, candidate.period_id) in selected_slots)
        )
    context.model.add(sum(variables.values()) == required_count)
    terms = context.penalty_terms_by_priority.get(constraint.priority, [])
    context.model.minimize(sum(terms))
    solver = cp_model.CpSolver()
    status = solver.status_name(solver.solve(context.model))
    assert status == "OPTIMAL"
    return solver, context


def test_s16_prefers_proportional_distribution_over_date_clustering() -> None:
    balanced, context = _solve_s16(
        (1, 1, 1, 1),
        {(0, "P1"), (2, "P1")},
        required_count=2,
    )
    clustered, _ = _solve_s16(
        (1, 1, 1, 1),
        {(0, "P1"), (1, "P1")},
        required_count=2,
    )

    assert balanced.objective_value == 0
    assert clustered.objective_value > balanced.objective_value
    assert ("CL1", "S1") in context.penalty_term_groups_by_priority[
        ClassSubjectScheduleBalancePreferenceConstraint.priority
    ]


def test_s16_weights_targets_by_candidate_capacity() -> None:
    solver, _ = _solve_s16(
        (3, 1, 1),
        {(0, "P1"), (1, "P1")},
        required_count=2,
    )

    assert solver.objective_value == 0


def test_s16_skips_requirements_without_distribution_freedom() -> None:
    solver, context = _solve_s16(
        (1, 1),
        {(0, "P1"), (1, "P1")},
        required_count=2,
    )

    assert solver.objective_value == 0
    assert (
        ClassSubjectScheduleBalancePreferenceConstraint.priority
        not in context.penalty_terms_by_priority
    )


def _solve_s17(
    period_ids: tuple[str, ...],
) -> cp_model.CpSolver:
    candidates = tuple(
        CandidateSlotModel(
            f"Q1__{period_id}",
            "Q1",
            TARGET_DATE,
            period_id,
            "T1",
            "C1",
            "CL1",
            "S1",
        )
        for period_id in period_ids
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
        required_counts={"Q1": 1},
        room_capacities={"C1": 1},
        class_daily_limits={("CL1", TARGET_DATE): 6},
        requirement_daily_limits={"Q1": None},
        teacher_daily_limits={("T1", TARGET_DATE): 6},
        teacher_first_last_period_forbidden={("T1", TARGET_DATE): False},
        class_attendance_limits={("CL1", TARGET_DATE): 6},
        period_orders={"P1": 1, "P3": 3},
        calendar_dates=(TARGET_DATE,),
        lesson_count_preference_rules=(
            ResolvedLessonCountPreferenceRuleModel(
                "LP1",
                "Q1",
                "CL1",
                "S1",
                0,
                ((TARGET_DATE, "P3"),),
            ),
        ),
    )
    constraint = LessonCountInScopePreferenceConstraint()
    constraint.apply(context)
    model.add(sum(variables.values()) == 1)
    model.minimize(sum(context.penalty_terms_by_priority[constraint.priority]))
    solver = cp_model.CpSolver()
    status = solver.status_name(solver.solve(model))
    assert status == "OPTIMAL"
    return solver


def test_s17_prefers_outside_scope_but_keeps_unavoidable_scope_assignment_feasible() -> None:
    avoidable = _solve_s17(("P1", "P3"))
    unavoidable = _solve_s17(("P3",))

    assert avoidable.objective_value == 0
    assert unavoidable.objective_value == 1


def _solve_s18(
    dates: tuple[date, ...],
    preferred_limit: int,
) -> tuple[cp_model.CpSolver, SolverContext]:
    candidates = tuple(
        CandidateSlotModel(
            f"Q{index}__P1",
            f"Q{index}",
            target_date,
            "P1",
            f"T{index}",
            "C1",
            "CL1",
            "S1",
        )
        for index, target_date in enumerate(dates, start=1)
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
        class_daily_limits={("CL1", target_date): 1 for target_date in dates},
        requirement_daily_limits={candidate.requirement_id: 1 for candidate in candidates},
        teacher_daily_limits={
            (candidate.teacher_id, candidate.target_date): 1 for candidate in candidates
        },
        teacher_first_last_period_forbidden={
            (candidate.teacher_id, candidate.target_date): False for candidate in candidates
        },
        class_attendance_limits={("CL1", target_date): None for target_date in dates},
        period_orders={"P1": 1},
        calendar_dates=dates,
        class_attendance_preference_limits={
            ("CL1", target_date): preferred_limit for target_date in dates
        },
    )
    constraint = ClassConsecutiveAttendancePreferenceConstraint()
    constraint.apply(context)
    for variable in variables.values():
        model.add(variable == 1)
    model.minimize(sum(context.penalty_terms_by_priority.get(constraint.priority, ())))
    solver = cp_model.CpSolver()
    status = solver.status_name(solver.solve(model))
    assert status == "OPTIMAL"
    return solver, context


def test_s18_uses_triangular_penalty_for_longer_attendance_streaks() -> None:
    objectives = []
    for streak_length in (3, 4, 5, 6):
        dates = tuple(TARGET_DATE + timedelta(days=offset) for offset in range(streak_length))
        solver, context = _solve_s18(dates, preferred_limit=3)
        objectives.append(solver.objective_value)
        if streak_length > 3:
            assert ("CL1",) in context.penalty_term_groups_by_priority[
                ClassConsecutiveAttendancePreferenceConstraint.priority
            ]

    assert objectives == [0, 1, 3, 6]


def test_s18_calendar_gap_breaks_the_attendance_streak() -> None:
    dates = (
        TARGET_DATE,
        TARGET_DATE + timedelta(days=1),
        TARGET_DATE + timedelta(days=3),
        TARGET_DATE + timedelta(days=4),
    )
    solver, _ = _solve_s18(dates, preferred_limit=3)

    assert solver.objective_value == 0


def test_s18_penalizes_each_overlapping_pair_as_an_independent_group() -> None:
    dates = tuple(TARGET_DATE + timedelta(days=offset) for offset in range(3))
    candidates = tuple(
        CandidateSlotModel(
            f"Q{offset}__P1",
            f"Q{offset}",
            target_date,
            "P1",
            f"T{offset}",
            "C1",
            class_id,
            "S1",
        )
        for offset, (target_date, class_id) in enumerate(
            zip(dates, ("CL1", "SPECIAL", "CL1"), strict=True),
            start=1,
        )
    )
    model = cp_model.CpModel()
    context = SolverContext(
        model=model,
        candidates=candidates,
        assignment_variables={
            candidate.candidate_id: model.new_bool_var(candidate.candidate_id)
            for candidate in candidates
        },
        required_counts={candidate.requirement_id: 1 for candidate in candidates},
        room_capacities={"C1": 1},
        class_daily_limits={},
        requirement_daily_limits={},
        teacher_daily_limits={},
        teacher_first_last_period_forbidden={},
        class_attendance_limits={},
        period_orders={"P1": 1},
        calendar_dates=dates,
        attendance_group_class_ids={
            "PAIR::A": ("CL1", "SPECIAL"),
            "PAIR::B": ("CL2", "SPECIAL"),
        },
        attendance_group_preference_limits={
            (group_id, target_date): 2
            for group_id in ("PAIR::A", "PAIR::B")
            for target_date in dates
        },
    )
    constraint = ClassConsecutiveAttendancePreferenceConstraint()
    constraint.apply(context)
    for variable in context.assignment_variables.values():
        model.add(variable == 1)
    model.minimize(sum(context.penalty_terms_by_priority[constraint.priority]))
    solver = cp_model.CpSolver()

    assert solver.status_name(solver.solve(model)) == "OPTIMAL"
    assert solver.objective_value == 1
    assert set(context.penalty_term_groups_by_priority[constraint.priority]) == {
        ("PAIR::A",),
        ("PAIR::B",),
    }


def test_s21_prefers_three_early_and_one_late_day_off() -> None:
    context = _context(room_capacity=1)
    early_dates = tuple(TARGET_DATE + timedelta(days=offset) for offset in range(3))
    late_dates = tuple(TARGET_DATE + timedelta(days=10 + offset) for offset in range(2))
    context.calendar_dates = early_dates + late_dates
    context.teacher_day_off_variables = {
        ("T1", target_date): context.model.new_bool_var(f"off_{target_date}")
        for target_date in context.calendar_dates
    }
    context.teacher_day_off_rules = (
        TeacherDayOffRuleModel(
            "EARLY",
            "T1",
            True,
            early_dates,
            None,
            2,
            3,
            "SUMMER",
            4,
            3,
        ),
        TeacherDayOffRuleModel(
            "LATE",
            "T1",
            True,
            late_dates,
            None,
            1,
            2,
            "SUMMER",
            4,
            1,
        ),
    )
    early_variables = [context.teacher_day_off_variables[("T1", day)] for day in early_dates]
    late_variables = [context.teacher_day_off_variables[("T1", day)] for day in late_dates]
    context.model.add(sum(early_variables) >= 2)
    context.model.add(sum(early_variables) <= 3)
    context.model.add(sum(late_variables) >= 1)
    context.model.add(sum(late_variables) <= 2)
    context.model.add(sum(early_variables) + sum(late_variables) == 4)
    constraint = TeacherDayOffDistributionPreferenceConstraint()
    constraint.apply(context)
    context.model.minimize(sum(context.penalty_terms_by_priority[constraint.priority]))
    solver = cp_model.CpSolver()

    assert solver.status_name(solver.solve(context.model)) == "OPTIMAL"
    assert sum(solver.value(variable) for variable in early_variables) == 3
    assert sum(solver.value(variable) for variable in late_variables) == 1


def test_soft_constraint_priorities_and_optimization_scopes_are_ordered() -> None:
    assert (
        HomeroomBoundarySlotPreferenceConstraint.priority
        > TeacherDayOffDistributionPreferenceConstraint.priority
        > ClassSubjectDailyRepeatPreferenceConstraint.priority
    )
    assert (
        ClassSubjectDailyRepeatPreferenceConstraint.priority
        > ClassSubjectDoubleThenNextDayPreferenceConstraint.priority
        > ClassDailyContiguityPreferenceConstraint.priority
        > ClassConsecutiveAttendancePreferenceConstraint.priority
        > ClassSingleLessonDayPreferenceConstraint.priority
        > ClassSubjectScheduleBalancePreferenceConstraint.priority
        > ClassSubjectConsecutiveRepeatPreferenceConstraint.priority
        > LessonCountInScopePreferenceConstraint.priority
        > RoomChangeGapPreferenceConstraint.priority
    )
    assert ClassSubjectDailyRepeatPreferenceConstraint.optimization_scope == "assignment"
    assert ClassSubjectScheduleBalancePreferenceConstraint.optimization_scope == "assignment"
    assert ClassSubjectDoubleThenNextDayPreferenceConstraint.optimization_scope == "assignment"
    assert ClassDailyContiguityPreferenceConstraint.optimization_scope == "assignment"
    assert ClassConsecutiveAttendancePreferenceConstraint.optimization_scope == "assignment"
    assert ClassSingleLessonDayPreferenceConstraint.optimization_scope == "assignment"
    assert ClassSubjectConsecutiveRepeatPreferenceConstraint.optimization_scope == "assignment"
    assert LessonCountInScopePreferenceConstraint.optimization_scope == "assignment"
    assert RoomChangeGapPreferenceConstraint.optimization_scope == "room"

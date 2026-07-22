from __future__ import annotations

from dataclasses import replace
from datetime import date

from school_timetable_solver.model.input_models import (
    CalendarDayModel,
    InputDataModel,
    TeacherAvailabilityModel,
)
from school_timetable_solver.service.planning_services import (
    CandidateBuilderService,
    RuleResolverService,
)


def test_rule_resolver_applies_rule_on_start_date_and_not_before(
    minimal_input_data: InputDataModel,
) -> None:
    first_rule = replace(
        minimal_input_data.placement_rules[0],
        start_date=date(2026, 7, 28),
        allowed_period_ids=("P2",),
    )
    class_model = replace(minimal_input_data.classes[0], default_allowed_periods=("P1", "P2"))
    input_data = replace(
        minimal_input_data,
        placement_rules=(first_rule,),
        classes=(class_model, minimal_input_data.classes[1]),
    )

    resolved = RuleResolverService().execute(input_data)
    by_date = {
        item.target_date: item.allowed_period_ids
        for item in resolved.class_date_rules
        if item.class_id == "CL1"
    }

    assert by_date[date(2026, 7, 27)] == ("P1", "P2")
    assert by_date[date(2026, 7, 28)] == ("P2",)


def test_candidate_builder_rejects_unavailable_teacher_and_disallowed_period(
    minimal_input_data: InputDataModel,
) -> None:
    availability = tuple(
        TeacherAvailabilityModel(
            item.teacher_id,
            item.target_date,
            item.period_id,
            "unavailable"
            if (item.teacher_id, item.target_date, item.period_id)
            == ("T1", date(2026, 7, 28), "P2")
            else item.availability,
        )
        for item in minimal_input_data.teacher_availability
    )
    rule = replace(minimal_input_data.placement_rules[0], allowed_period_ids=("P1", "P2"))
    input_data = replace(
        minimal_input_data, teacher_availability=availability, placement_rules=(rule,)
    )

    resolved = RuleResolverService().execute(input_data)
    result = CandidateBuilderService().execute(input_data, resolved)

    assert all(candidate.period_id != "P3" for candidate in result.candidates)
    assert not any(
        candidate.teacher_id == "T1"
        and candidate.target_date == date(2026, 7, 28)
        and candidate.period_id == "P2"
        for candidate in result.candidates
    )
    assert {summary.rule_id for summary in result.rejection_summaries} >= {"H05", "H13"}


def test_candidate_builder_rejects_closed_calendar_and_disabled_room(
    minimal_input_data: InputDataModel,
) -> None:
    closed_day = CalendarDayModel(
        date(2026, 7, 27), "月", False, ("P1", "P2", "P3"), "closed", "休館"
    )
    disabled_room = replace(minimal_input_data.rooms[0], enabled=False)
    input_data = replace(
        minimal_input_data,
        calendar_days=(closed_day, minimal_input_data.calendar_days[1]),
        rooms=(disabled_room, minimal_input_data.rooms[1]),
    )

    resolved = RuleResolverService().execute(input_data)
    result = CandidateBuilderService().execute(input_data, resolved)

    assert {summary.rule_id for summary in result.rejection_summaries} >= {"H04", "H14"}

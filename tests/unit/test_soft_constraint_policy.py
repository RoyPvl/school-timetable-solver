from __future__ import annotations

from school_timetable_solver.constraint.soft_constraint_policy import soft_constraint_priority


def test_s10_priority_is_60() -> None:
    assert soft_constraint_priority("S10") == 60


def test_s22_priority_is_40() -> None:
    assert soft_constraint_priority("S22") == 40

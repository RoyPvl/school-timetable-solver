from __future__ import annotations

import pytest

from school_timetable_solver.service.solver_service import TimetableSolverService


def test_lower_priority_reserve_ratio_preserves_total_reserve_when_phase_added() -> None:
    service = TimetableSolverService(())

    assert service._lower_priority_reserve_ratio(6) == pytest.approx(0.15)
    assert service._lower_priority_reserve_ratio(7) == pytest.approx(0.125)
    assert service._lower_priority_reserve_ratio(1) == 0.0

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from school_timetable_solver.model.result_models import (
    GenerationResultModel,
    InputReadResultModel,
)


class InputReader(Protocol):
    def read(self, path: Path) -> InputReadResultModel: ...


class TimetableWriter(Protocol):
    def write(self, result: GenerationResultModel, path: Path) -> None: ...

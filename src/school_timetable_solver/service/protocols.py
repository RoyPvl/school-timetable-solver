from __future__ import annotations

from pathlib import Path
from typing import Protocol

from school_timetable_solver.model.result_models import (
    InputReadResultModel,
    TimetableDocumentModel,
)


class InputReader(Protocol):
    def read(self, path: Path) -> InputReadResultModel: ...


class TimetableWriter(Protocol):
    def write(self, document: TimetableDocumentModel, path: Path) -> None: ...

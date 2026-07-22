from __future__ import annotations

import logging
from pathlib import Path


class ExecutionLogAdapter:
    """Configure the process logger at the requested local file boundary."""

    def configure(self, path: Path | None) -> None:
        handlers: list[logging.Handler] = [logging.StreamHandler()]
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            handlers.append(logging.FileHandler(path, encoding="utf-8"))
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
            handlers=handlers,
            force=True,
        )

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from school_timetable_solver.service.input_migration_service import MigrateInputWorkbookToV2Service


def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="既存の入力Excel v1.1を、人間・AI向け入力Excel v2.0へ変換します"
    )
    parser.add_argument("--input", required=True, type=Path, help="v1.1入力Excel")
    parser.add_argument("--output", required=True, type=Path, help="v2.0出力Excel")
    parsed = parser.parse_args(arguments)

    result = MigrateInputWorkbookToV2Service().execute(parsed.input, parsed.output)
    errors = [issue for issue in result.issues if issue.severity == "ERROR"]
    if errors:
        for issue in errors:
            print(f"ERROR {issue.rule_id}: {issue.message}")
        return 1
    print(f"v2.0へ変換しました: {parsed.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

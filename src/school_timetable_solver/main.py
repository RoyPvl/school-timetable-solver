from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence
from pathlib import Path

from school_timetable_solver.composition import ApplicationComposition
from school_timetable_solver.model.result_models import GenerationRequestModel


def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Excel入力から学校時間割を生成します")
    parser.add_argument("--input", required=True, type=Path, help="入力Excelパス")
    parser.add_argument("--output", required=True, type=Path, help="出力Excelパス")
    parser.add_argument("--log", type=Path, help="実行ログパス")
    parsed = parser.parse_args(arguments)
    request = GenerationRequestModel(parsed.input, parsed.output, parsed.log)
    try:
        service = ApplicationComposition().create_generate_timetable_service(parsed.log)
        result = service.execute(request)
    except Exception:
        logging.getLogger(__name__).exception("予期しないアプリケーションエラー")
        return 1
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())

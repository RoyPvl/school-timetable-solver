from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence
from pathlib import Path

from school_timetable_solver.composition import ApplicationComposition
from school_timetable_solver.model.input_models import GenerationMode
from school_timetable_solver.model.result_models import GenerationRequestModel


def _positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("0より大きい実数を指定してください")
    return parsed


def _nonnegative_integer(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("0以上の整数を指定してください")
    return parsed


def _positive_integer(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("1以上の整数を指定してください")
    return parsed


def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Excel入力から学校時間割を生成します")
    parser.add_argument("--input", required=True, type=Path, help="入力Excelパス")
    parser.add_argument("--output", required=True, type=Path, help="出力Excelパス")
    parser.add_argument("--log", type=Path, help="実行ログパス")
    parser.add_argument(
        "--mode",
        choices=tuple(mode.value for mode in GenerationMode),
        default=GenerationMode.STRICT.value,
        help="strictまたはvalidate_only",
    )
    parser.add_argument(
        "--max-solve-seconds",
        type=_positive_float,
        default=60.0,
        help="探索時間上限(正の実数)",
    )
    parser.add_argument(
        "--random-seed",
        type=_nonnegative_integer,
        default=1,
        help="乱数シード(0以上の整数)",
    )
    parser.add_argument(
        "--num-search-workers",
        type=_positive_integer,
        default=8,
        help="並列探索ワーカー数(1以上、再現性優先時は1)",
    )
    parsed = parser.parse_args(arguments)
    request = GenerationRequestModel(
        input_path=parsed.input,
        output_path=parsed.output,
        log_path=parsed.log,
        solve_mode=GenerationMode(parsed.mode),
        max_solve_seconds=parsed.max_solve_seconds,
        random_seed=parsed.random_seed,
        num_search_workers=parsed.num_search_workers,
    )
    try:
        service = ApplicationComposition().create_generate_timetable_service(parsed.log)
        return service.execute(request).exit_code
    except Exception:
        logging.getLogger(__name__).exception("予期しないアプリケーションエラー")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

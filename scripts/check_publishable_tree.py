from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from hsconfig.publishable_tree import (  # noqa: E402
    PublishableTreeError,
    evaluate_repository_tree,
)


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise PublishableTreeError(f"argument_error:{message}")


def _parser() -> argparse.ArgumentParser:
    parser = _ArgumentParser(description="Diagnose the publishable repository tree.")
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument(
        "--mode",
        required=True,
        choices=("working-pre-cutover", "candidate-index", "final"),
    )
    parser.add_argument("--index-file", type=Path)
    parser.add_argument("--json", action="store_true")
    return parser


def _emit(document: object) -> None:
    sys.stdout.write(
        json.dumps(
            document,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    )


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        if not args.json:
            raise PublishableTreeError("--json is required")
        if args.mode == "candidate-index" and args.index_file is None:
            raise PublishableTreeError("candidate-index mode requires --index-file")
        if args.mode != "candidate-index" and args.index_file is not None:
            raise PublishableTreeError("--index-file is only valid in candidate-index mode")
        result = evaluate_repository_tree(
            args.root,
            mode=args.mode,
            index_file=args.index_file,
        )
    except (OSError, RuntimeError, TypeError, ValueError, PublishableTreeError) as exc:
        _emit({"error": str(exc), "schema_version": 1})
        return 2
    _emit(result)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

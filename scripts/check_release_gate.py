from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


# The documented parent process must not create source-tree bytecode before
# release-gate hygiene has a chance to inspect the checkout.
sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src"
if str(SOURCE) not in sys.path:
    sys.path.insert(0, str(SOURCE))

from hsconfig.release_gate import (  # noqa: E402
    _redact_text,
    check_repository_hygiene,
    run_release_gate,
    scan_publishable_content,
)
from hsconfig.version import __version__  # noqa: E402


class _CliError(ValueError):
    pass


class _JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise _CliError(f"argument_error:{message}")


def _parser() -> argparse.ArgumentParser:
    parser = _JsonArgumentParser(description="Run the canonical local release gate.")
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--outputs", required=True, type=Path)
    parser.add_argument(
        "--tree-mode",
        choices=("working-pre-cutover", "candidate", "final"),
        default="final",
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--internal-check",
        choices=("publishable_path_scan", "repository_hygiene"),
        help=argparse.SUPPRESS,
    )
    return parser


def _failure(message: str) -> dict[str, Any]:
    portable = _redact_text(message)
    return {
        "passed": False,
        "final_release_ready": False,
        "version": __version__,
        "commit_oid": "",
        "checks": [],
        "errors": [portable if len(portable) <= 1_000 else "internal_error_message_redacted"],
    }


def _emit(document: MappingLike) -> None:
    print(json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


MappingLike = dict[str, Any]


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        if args.internal_check == "publishable_path_scan":
            document = scan_publishable_content(
                repository=args.repo,
                outputs_root=args.outputs,
                tree_mode=args.tree_mode,
            )
            _emit(document)
            return 0 if document["passed"] else 1
        if args.internal_check == "repository_hygiene":
            document = check_repository_hygiene(args.repo, args.outputs)
            _emit(document)
            return 0 if document["passed"] else 1
        result = run_release_gate(
            repository=args.repo,
            outputs_root=args.outputs,
            tree_mode=args.tree_mode,
        )
    except Exception as exc:
        _emit(_failure(str(exc)))
        return 2
    _emit(result.to_document())
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

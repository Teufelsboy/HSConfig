from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any


PayloadWorker = Callable[[argparse.Namespace], tuple[dict[str, Any], int]]


def emit_result(payload: dict[str, Any], as_json: bool, code: int) -> int:
    if as_json:
        print(json.dumps(payload, sort_keys=True))
    else:
        print(json.dumps(payload, indent=2, sort_keys=True))
    return code


def run_payload_command(args: argparse.Namespace, worker: PayloadWorker) -> int:
    try:
        payload, code = worker(args)
    except Exception as exc:
        payload, code = {"status": "failed", "errors": [str(exc)]}, 1
    return emit_result(payload, bool(getattr(args, "json", False)), code)


def prepare_research_output_dir(out: Path) -> None:
    if not out.exists():
        return
    if not out.is_dir():
        raise ValueError(f"Research output path exists and is not a directory: {out}")
    if list(out.iterdir()):
        raise ValueError(f"Refusing to overwrite non-empty research output directory: {out}")

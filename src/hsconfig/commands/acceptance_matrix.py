from __future__ import annotations

from pathlib import Path

from hsconfig.acceptance_matrix import build_acceptance_matrix
from hsconfig.commands.common import emit_result
from hsconfig.io import write_json


def run_acceptance_matrix_command(args) -> int:
    payload = build_acceptance_matrix([Path(package) for package in args.package])

    output_path = getattr(args, "out", None)
    if output_path:
        write_json(output_path, payload)

    code = 0 if payload.get("status") == "passed" else 1
    return emit_result(payload, bool(getattr(args, "json", False)), code)

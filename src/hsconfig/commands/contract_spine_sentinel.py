from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from hsconfig.commands.common import run_payload_command
from hsconfig.contract_spine_sentinel import build_contract_spine_sentinel_report
from hsconfig.io import write_json


def run_contract_spine_sentinel_command(args: argparse.Namespace) -> int:
    return run_payload_command(args, contract_spine_sentinel_payload)


def contract_spine_sentinel_payload(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    report = build_contract_spine_sentinel_report()
    if getattr(args, "out", None):
        out = Path(args.out)
        _assert_safe_json_output(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        write_json(out, report)
        report = {**report, "written_report": str(out)}
    return report, 0 if report.get("status") == "clean" else 1


def _assert_safe_json_output(path: Path) -> None:
    parts = {part.lower() for part in path.parts}
    runtime_file_names = {
        "deck_config.ini",
        "globalvalues.json",
        "mulligan.json",
        "combo.json",
        "concede.json",
        "presume.json",
    }
    name = path.name.lower()
    if path.suffix.lower() != ".json":
        raise ValueError("contract-spine-sentinel --out must be a .json diagnostic report path")
    if "customconfig" in parts or name in runtime_file_names:
        raise ValueError(
            "contract-spine-sentinel --out must not target HearthRanger runtime files"
        )

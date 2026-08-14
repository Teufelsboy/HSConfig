from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from hsconfig.commands.common import run_payload_command
from hsconfig.contract_doctor import (
    build_contract_doctor_report,
    render_contract_doctor_markdown,
)


def run_contract_doctor_command(args: argparse.Namespace) -> int:
    return run_payload_command(args, contract_doctor_payload)


def contract_doctor_payload(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    report = build_contract_doctor_report(Path(args.package))
    if getattr(args, "out", None):
        out = Path(args.out)
        _assert_safe_markdown_output(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(render_contract_doctor_markdown(report), encoding="utf-8")
        report = {**report, "written_report": str(out)}
    return report, 0 if report.get("status") == "ok" else 1


def _assert_safe_markdown_output(path: Path) -> None:
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
    if path.suffix.lower() != ".md":
        raise ValueError("contract-doctor --out must be a .md diagnostic report path")
    if "customconfig" in parts or name in runtime_file_names:
        raise ValueError("contract-doctor --out must not target HearthRanger runtime files")

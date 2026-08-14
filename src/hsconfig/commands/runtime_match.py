from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from hsconfig.commands.common import run_payload_command
from hsconfig.runtime_package_match import build_runtime_package_match_report


def run_runtime_match_command(args: argparse.Namespace) -> int:
    return run_payload_command(args, runtime_match_payload)


def runtime_match_payload(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    package = Path(args.package)
    runtime = Path(args.runtime_root)
    if not package.exists():
        return {"status": "failed", "errors": [f"Package not found: {package}"]}, 1
    report = build_runtime_package_match_report(
        package_root=package,
        runtime_root=runtime,
        config_dir=getattr(args, "config_dir", None),
    )
    return report, 0 if report["status"] == "matched" else 1

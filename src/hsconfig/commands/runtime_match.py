from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from hsconfig.commands.common import run_payload_command
from hsconfig.current_output import lease_package_input
from hsconfig.runtime_package_match import build_runtime_package_match_report


def run_runtime_match_command(args: argparse.Namespace) -> int:
    return run_payload_command(args, runtime_match_payload)


def runtime_match_payload(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    package_input = Path(args.package)
    runtime = Path(args.runtime_root)
    try:
        with lease_package_input(package_input) as lease:
            package = lease.package_root
            if not package.exists():
                return {
                    "status": "failed",
                    "errors": [f"Package not found: {package}"],
                }, 1
            report = build_runtime_package_match_report(
                package_root=package,
                runtime_root=runtime,
                config_dir=getattr(args, "config_dir", None),
            )
            if lease.content_root_sha256 is not None:
                report = {
                    **report,
                    "publication_content_root_sha256": (
                        lease.content_root_sha256
                    ),
                }
            return report, 0 if report["status"] == "matched" else 1
    except ValueError as error:
        return {
            "status": "failed",
            "errors": [str(error)],
        }, 1

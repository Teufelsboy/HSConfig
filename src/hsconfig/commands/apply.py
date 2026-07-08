from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from hsconfig.apply_gate import evaluate_apply_gate
from hsconfig.commands.common import run_payload_command
from hsconfig.package_io import read_optional_profile, read_required_baseline
from hsconfig.runtime_apply import apply_package
from hsconfig.validate_package import validate_config_package


def run_apply_command(args: argparse.Namespace) -> int:
    return run_payload_command(args, apply_payload)


def run_validate_command(args: argparse.Namespace) -> int:
    return run_payload_command(args, validate_payload)


def validate_payload(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    package = Path(args.package)
    if not package.exists():
        return {
            "status": "failed",
            "errors": [f"Package not found: {package}"],
            "checked_files": 0,
        }, 1

    baseline = read_required_baseline(package)
    profile = read_optional_profile(package)
    report = validate_config_package(
        package,
        globalvalues_baseline=baseline,
        globalvalues_profile=profile,
        require_complete_package=True,
        require_globalvalues_profile=True,
    )
    return report, 0 if report["status"] == "passed" else 1


def apply_payload(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    package = Path(args.package)
    if not package.exists():
        return {"status": "failed", "errors": [f"Package not found: {package}"]}, 1

    baseline = read_required_baseline(package)
    profile = read_optional_profile(package)
    report = validate_config_package(
        package,
        globalvalues_baseline=baseline,
        globalvalues_profile=profile,
        require_complete_package=True,
        require_globalvalues_profile=True,
    )
    if report["status"] != "passed":
        return {"status": "failed", "errors": report["errors"], "validation_report": report}, 1

    apply_gate = evaluate_apply_gate(
        package,
        allow_source_informed=bool(getattr(args, "allow_source_informed", False)),
    )
    if apply_gate["status"] != "allowed":
        return {
            "status": "blocked",
            "errors": ["Operator summary does not allow runtime apply."],
            "validation_report": report,
            "apply_gate": apply_gate,
        }, 1

    receipt = apply_package(package_root=package, runtime_root=args.runtime_root)
    return {"status": "applied", "apply_gate": apply_gate, "receipt": receipt}, 0

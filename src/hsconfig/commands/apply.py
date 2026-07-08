from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from hsconfig.apply_gate import evaluate_apply_gate
from hsconfig.commands.common import run_payload_command
from hsconfig.io import read_json
from hsconfig.package_io import read_optional_profile, read_required_baseline
from hsconfig.runtime_apply import apply_package, plan_apply_package
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

    if bool(getattr(args, "fake", False)):
        receipt = plan_apply_package(
            package_root=package,
            runtime_root=args.runtime_root,
            apply_gate=apply_gate,
        )
        return {
            "status": "fake_apply_ready",
            "validation_report": report,
            "apply_gate": apply_gate,
            "receipt": receipt,
        }, 0

    fake_receipt = None
    from_fake_receipt = getattr(args, "from_fake_receipt", None)
    if from_fake_receipt:
        fake_receipt = read_json(Path(from_fake_receipt))

    receipt = apply_package(
        package_root=package,
        runtime_root=args.runtime_root,
        fake_receipt=fake_receipt,
        apply_gate=apply_gate,
        allow_source_informed=bool(getattr(args, "allow_source_informed", False)),
    )
    return {"status": "applied", "apply_gate": apply_gate, "receipt": receipt}, 0

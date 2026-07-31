from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from hsconfig.apply_gate import evaluate_apply_gate
from hsconfig.commands.common import run_payload_command
from hsconfig.current_output import lease_package_input
from hsconfig.io import read_json
from hsconfig.runtime_apply import apply_package, plan_apply_package
from hsconfig.strict_package_validation import validate_complete_package


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

    report = validate_complete_package(package)
    return report, 0 if report["status"] == "passed" else 1


def apply_payload(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    package_input = Path(args.package)
    try:
        with lease_package_input(package_input) as lease:
            package = lease.package_root
            digest = lease.content_root_sha256
            expected_digest = getattr(
                args,
                "expected_publication_content_root_sha256",
                None,
            )
            expected_package = getattr(
                args,
                "expected_published_package",
                None,
            )
            if (
                expected_digest is not None
                and (
                    lease.publication is None
                    or digest != expected_digest
                    or expected_package is None
                    or package.resolve()
                    != Path(str(expected_package)).resolve()
                )
            ):
                return _with_publication_digest(
                    {
                        "status": "failed",
                        "errors": [
                            "configure_apply_publication_digest_mismatch"
                        ],
                    },
                    digest,
                ), 1
            if not package.exists():
                return _with_publication_digest(
                    {
                        "status": "failed",
                        "errors": [f"Package not found: {package}"],
                    },
                    digest,
                ), 1

            report = validate_complete_package(package)
            if report["status"] != "passed":
                return _with_publication_digest(
                    {
                        "status": "failed",
                        "errors": report["errors"],
                        "validation_report": report,
                    },
                    digest,
                ), 1

            apply_gate = evaluate_apply_gate(package)
            if apply_gate["status"] != "allowed":
                return _with_publication_digest(
                    {
                        "status": "blocked",
                        "errors": [
                            "Operator summary does not allow runtime apply."
                        ],
                        "validation_report": report,
                        "apply_gate": apply_gate,
                    },
                    digest,
                ), 1

            if bool(getattr(args, "fake", False)):
                receipt = plan_apply_package(
                    package_root=package,
                    runtime_root=args.runtime_root,
                    apply_gate=apply_gate,
                )
                return _with_publication_digest(
                    {
                        "status": "fake_apply_ready",
                        "validation_report": report,
                        "apply_gate": apply_gate,
                        "receipt": receipt,
                    },
                    digest,
                ), 0

        fake_receipt = None
        from_fake_receipt = getattr(args, "from_fake_receipt", None)
        if from_fake_receipt:
            fake_receipt = read_json(Path(from_fake_receipt))
        receipt = apply_package(
            package_root=package_input,
            runtime_root=args.runtime_root,
            fake_receipt=fake_receipt,
            apply_gate=apply_gate,
        )
        return _with_publication_digest(
            {
                "status": receipt["status"],
                "apply_gate": apply_gate,
                "receipt": receipt,
            },
            digest,
        ), 0
    except Exception as error:
        return {
            "status": "failed",
            "errors": [str(error)],
        }, 1


def _with_publication_digest(
    payload: dict[str, Any],
    content_root_sha256: str | None,
) -> dict[str, Any]:
    if content_root_sha256 is None:
        return payload
    return {
        **payload,
        "publication_content_root_sha256": content_root_sha256,
    }

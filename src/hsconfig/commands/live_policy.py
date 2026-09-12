"""Thin CLI adapter for read-only status and explicit profile mutations."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from hsconfig.commands.common import run_payload_command
from hsconfig.operator_profile import (
    OperatorProfile,
    OperatorProfileEnvironmentError,
    disable_operator_profile,
    enable_operator_profile,
    load_operator_profile_if_present,
)


def run_live_policy_command(args: argparse.Namespace) -> int:
    return run_payload_command(args, _live_policy_payload)


def _live_policy_payload(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    if args.live_policy_action == "status":
        return _status_payload()
    if args.live_policy_action == "enable":
        expected_predecessor = (
            None
            if args.expected_absent
            else args.expected_predecessor_sha256
        )
        profile = enable_operator_profile(
            runtime_root=Path(args.runtime_root),
            output_base_root=Path(args.output_base_root),
            expected_predecessor_sha256=expected_predecessor,
        )
        return _profile_payload(profile, status="enabled", as_json=args.json), 0
    if args.live_policy_action == "disable":
        profile = disable_operator_profile(
            expected_predecessor_sha256=args.expected_predecessor_sha256
        )
        return _profile_payload(profile, status="disabled", as_json=args.json), 0
    raise ValueError("live_policy_action_invalid")


def _status_payload() -> tuple[dict[str, Any], int]:
    payload: dict[str, Any] = {
        "status": "invalid",
        "diagnostic_only": True,
        "runtime_write_performed": False,
    }
    try:
        profile = load_operator_profile_if_present()
    except OperatorProfileEnvironmentError:
        payload["error_code"] = "operator_profile_environment_invalid"
        return payload, 1
    except (OSError, RuntimeError, ValueError):
        payload["error_code"] = "operator_profile_invalid"
        return payload, 1
    if profile is None:
        payload["status"] = "absent"
    else:
        payload.update(
            _profile_payload(
                profile,
                status="enabled" if profile.live_by_default else "disabled",
                as_json=True,
            )
        )
    return payload, 0


def _profile_payload(
    profile: OperatorProfile,
    *,
    status: str,
    as_json: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": status,
        "content_sha256": profile.content_sha256,
        "runtime_root": str(profile.runtime_root),
        "output_base_root": str(profile.output_base_root),
    }
    if as_json:
        payload.update(
            {
                "runtime_root_identity": list(profile.runtime_root_identity),
                "output_base_root_identity": list(
                    profile.output_base_root_identity
                ),
            }
        )
    return payload


__all__ = ("run_live_policy_command",)

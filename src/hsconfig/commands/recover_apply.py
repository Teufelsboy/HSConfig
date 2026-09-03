"""Thin CLI adapter for exact-attempt apply recovery."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from hsconfig.commands.common import run_payload_command


def run_recover_apply_command(args: argparse.Namespace) -> int:
    return run_payload_command(args, _recover_apply_payload)


def _recover_apply_payload(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    from hsconfig import published_apply

    result = published_apply.recover_apply_attempt(
        session_root=Path(args.session),
    )
    if isinstance(result, published_apply.RecoverApplyNotStarted):
        return {
            "status": result.status,
            "run_id": result.run_id,
            "session_root": str(result.session_root),
            "session_root_identity": list(result.session_root_identity),
            "persisted_session_sha256": result.persisted_session_sha256,
            "runtime_write_performed": result.runtime_write_performed,
        }, 0

    payload: dict[str, Any] = {
        "raw_apply_status": result.raw_apply_status,
        "physical_disposition": result.physical_disposition.value,
        "runtime_match_status": result.runtime_match_status,
        "runtime_match_sha256": result.runtime_match_sha256,
        "package_root_sha256": result.package_root_sha256,
        "last_apply_receipt_sha256": result.last_apply_receipt_sha256,
        "runtime_state_sha256": result.runtime_state_sha256,
        "deck_config_ini_sha256": result.deck_config_ini_sha256,
        "retained_attempt_record_path": _path_value(
            result.retained_attempt_record_path
        ),
        "retained_attempt_record_identity": _identity_value(
            result.retained_attempt_record_identity
        ),
        "retained_attempt_record_sha256": (
            result.retained_attempt_record_sha256
        ),
        "retained_journal_path": _path_value(result.retained_journal_path),
        "retained_journal_identity": _identity_value(
            result.retained_journal_identity
        ),
        "retained_journal_sha256": result.retained_journal_sha256,
        "retained_target_owner_journal_path": _path_value(
            result.retained_target_owner_journal_path
        ),
        "retained_target_owner_journal_identity": _identity_value(
            result.retained_target_owner_journal_identity
        ),
        "retained_target_owner_journal_sha256": (
            result.retained_target_owner_journal_sha256
        ),
        "runtime_admission_path": _path_value(result.runtime_admission_path),
        "runtime_admission_parent_identity": _identity_value(
            result.runtime_admission_parent_identity
        ),
        "runtime_admission_identity": _identity_value(
            result.runtime_admission_identity
        ),
        "runtime_admission_sha256": result.runtime_admission_sha256,
        "terminal_status": result.terminal_status,
        "error_code": result.error_code,
    }
    return payload, 0 if result.terminal_status in {
        "LIVE_AND_MATCHED",
        "ALREADY_LIVE",
    } else 1


def _path_value(value: Path | None) -> str | None:
    return None if value is None else str(value)


def _identity_value(value: tuple[int, int, int] | None) -> list[int] | None:
    return None if value is None else list(value)


__all__ = ("run_recover_apply_command",)

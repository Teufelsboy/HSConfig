"""Thin CLI adapter for the typed configure workflow."""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
from typing import Any

from hsconfig.commands.apply import apply_payload
from hsconfig.commands.common import emit_result
from hsconfig.commands.source_workflow import (
    source_acquire_for_configure,
    source_manifest_payload,
)
from hsconfig.config_quality_contract import build_config_quality_report
from hsconfig.configure_models import ConfigureRequest
from hsconfig.configure_stages import StageObserver
from hsconfig.configure_workflow import (
    _build_acceptance_summary,
    _build_config_proof_summary,
    _build_handoff_contract,
    _compact_config_quality_summary,
    execute_configure,
)
from hsconfig.internal_source_authority import (
    reject_caller_supplied_source_authority,
)

__all__ = (
    "run_configure_command",
    "configure_payload",
    "configure_request_from_args",
    "execute_configure",
    "apply_payload",
    "build_config_quality_report",
    "source_manifest_payload",
    "source_acquire_for_configure",
    "_build_acceptance_summary",
    "_build_config_proof_summary",
    "_build_handoff_contract",
    "_compact_config_quality_summary",
)


def run_configure_command(args: argparse.Namespace) -> int:
    reject_caller_supplied_source_authority(args)
    try:
        payload, status = configure_payload(args)
    except Exception as exc:
        payload = {
            "schema_version": 1,
            "status": "failed",
            "stage": "configure",
            "errors": [str(exc)],
        }
        status = 1
    return emit_result(payload, bool(getattr(args, "json", False)), status)


def configure_payload(
    args: argparse.Namespace,
    *,
    stage_observer: StageObserver | None = None,
) -> tuple[dict[str, Any], int]:
    reject_caller_supplied_source_authority(args)
    result = execute_configure(
        configure_request_from_args(args),
        stage_observer=stage_observer,
        apply_payload_fn=apply_payload,
        build_config_quality_report_fn=build_config_quality_report,
        source_manifest_payload_fn=source_manifest_payload,
        source_acquire_for_configure_fn=source_acquire_for_configure,
    )
    return result.materialized_summary(), result.exit_code


def configure_request_from_args(args: argparse.Namespace) -> ConfigureRequest:
    reject_caller_supplied_source_authority(args)
    current_date = _operator_date(getattr(args, "current_date", None))
    return ConfigureRequest(
        deck_name=str(args.deck_name),
        deck_code=str(args.deck_code),
        output_root=Path(args.out),
        runtime_root=_optional_path(getattr(args, "runtime_root", None)),
        apply_requested=bool(getattr(args, "apply", False)),
        current_date=current_date,
        source_urls=tuple(getattr(args, "source_url", ()) or ()),
        online_source=bool(getattr(args, "online_source", False)),
        auto_source=bool(getattr(args, "auto_source", False)),
        source_evidence_json=_optional_path(
            getattr(args, "source_evidence_json", None)
        ),
        source_search_results_json=_optional_path(
            getattr(args, "source_search_results_json", None)
        ),
        cards_json=_optional_path(getattr(args, "cards_json", None)),
        collectible_cards_json=_optional_path(
            getattr(args, "collectible_cards_json", None)
        ),
        full_cards_json=_optional_path(
            getattr(args, "full_cards_json", None)
        ),
        source_fixture_url_map_json=_optional_path(
            getattr(args, "source_fixture_url_map_json", None)
        ),
        source_fetch_timeout_seconds=float(
            getattr(args, "source_fetch_timeout_seconds", 6.0)
        ),
        allow_placeholder=bool(
            getattr(args, "allow_placeholder", False)
        ),
        json_output=bool(getattr(args, "json", False)),
        optimized_start=bool(getattr(args, "optimized_start", False)),
        starter_decision_json=_optional_path(
            getattr(args, "starter_decision_json", None)
        ),
    )


def _operator_date(value: Any) -> date:
    if value is None:
        return date.today()
    return value if isinstance(value, date) else date.fromisoformat(str(value))


def _optional_path(value: Any) -> Path | None:
    return None if value is None else Path(value)

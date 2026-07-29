from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from hsconfig.source_acquisition_closure import (
    AcquisitionClosure,
    freeze_source_bundle,
)


__all__ = [
    "AcquisitionClosure",
    "build_source_bundle",
    "freeze_source_bundle",
]


def build_source_bundle(
    *,
    deck_name: str,
    deck_code: str,
    source_records: Sequence[Mapping[str, Any]],
    claims: Sequence[Mapping[str, Any]],
    operator_summary: Mapping[str, Any],
    explainability_report: Mapping[str, Any],
) -> dict[str, Any]:
    default_only = list(operator_summary.get("default_only_runtime_surfaces") or [])
    card_rows = list(explainability_report.get("card_rows") or [])
    source_backed_status = str(
        operator_summary.get("source_backed_status")
        or operator_summary.get("semantic_status")
        or "SOURCE_BACKED_PARTIAL"
    )
    first_missing = str(operator_summary.get("first_missing_source_action") or "none")
    missing_actions = list(operator_summary.get("source_missing_source_actions") or [])
    if not missing_actions and first_missing != "none":
        missing_actions = [first_missing]
    return {
        "schema_version": 1,
        "deck": {"name": deck_name, "code": deck_code},
        "source_record_count": len(source_records),
        "claim_count": len(claims),
        "source_records": [dict(row) for row in source_records],
        "claims": [dict(row) for row in claims],
        "pre_run_contract": _pre_run_projection(operator_summary),
        "default_only_runtime_surfaces": default_only,
        "card_coverage": [dict(row) for row in card_rows],
        "promotion": {
            "technical_status": operator_summary.get("technical_status"),
            "source_backed_status": source_backed_status,
            "semantic_status": source_backed_status,
            "source_strong_ready": bool(
                operator_summary.get(
                    "source_strong_ready",
                    source_backed_status == "SOURCE_BACKED_STRONG"
                    and first_missing == "none",
                )
            ),
            "first_missing_source_action": first_missing,
            "source_missing_source_actions": missing_actions,
            "source_status_reasons": list(
                operator_summary.get("source_status_reasons") or []
            ),
            "source_status_diagnostic_only": bool(
                operator_summary.get("source_status_diagnostic_only", True)
            ),
            "source_status_apply_blocking": bool(
                operator_summary.get("source_status_apply_blocking", False)
            ),
        },
    }


def _pre_run_projection(
    operator_summary: Mapping[str, Any],
) -> dict[str, Any]:
    status = operator_summary.get("pre_run_contract_status")
    strategy = operator_summary.get("strategy_authority_status")
    if status not in {"complete", "incomplete"}:
        return {}
    if strategy not in {"partial", "strong"}:
        raise ValueError("strategy_authority_status_invalid")
    return {
        "hsconfig_scope": "PRE_RUN_CONTRACT",
        "gameplay_strategy_owner": "hearthranger_bot",
        "gameplay_quality": "OUT_OF_SCOPE_ASSUMED_EXTERNAL",
        "bot_gameplay_assumption": "trusted_external",
        "pre_run_contract_status": status,
        "strategy_authority_status": strategy,
        "diagnostic_only": True,
        "apply_blocking": False,
    }

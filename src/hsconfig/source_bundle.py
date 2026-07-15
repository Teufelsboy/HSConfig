from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


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
    first_missing = _first_missing_source_action(card_rows, default_only)
    return {
        "schema_version": 1,
        "deck": {"name": deck_name, "code": deck_code},
        "source_record_count": len(source_records),
        "claim_count": len(claims),
        "source_records": [dict(row) for row in source_records],
        "claims": [dict(row) for row in claims],
        "default_only_runtime_surfaces": default_only,
        "card_coverage": [dict(row) for row in card_rows],
        "promotion": {
            "technical_status": operator_summary.get("technical_status"),
            "semantic_status": operator_summary.get("semantic_status"),
            "first_missing_source_action": first_missing,
        },
    }


def _first_missing_source_action(
    card_rows: Sequence[Mapping[str, Any]], default_only: Sequence[Any]
) -> str:
    if default_only:
        return "replace_default_only_runtime_surface_with_source_or_policy_claim"
    for row in card_rows:
        action = row.get("first_missing_source_action") or row.get("next_source_action")
        if action and action != "none":
            return _bundle_source_action(str(action), row)
    return "none"


def _bundle_source_action(action: str, row: Mapping[str, Any]) -> str:
    if action == "add_runtime_lowerable_claim_or_router_support":
        if str(row.get("strongest_claim_kind", "")).startswith("mulligan_"):
            return "add_explicit_mulligan_source"
        return "map_claim_kind_or_keep_report_only"
    if action == "add_card_specific_source_claim":
        return "map_claim_kind_or_keep_report_only"
    return action

from __future__ import annotations

from typing import Any


def build_strong_promotion_report(
    *,
    deck_name: str,
    fixture_stage: str,
    operator_summary: dict[str, Any],
    source_claim_gap_report: dict[str, Any],
) -> dict[str, Any]:
    promotion_ready = (
        operator_summary.get("technical_status") == "VALID_PACKAGE"
        and operator_summary.get("semantic_status") == "SOURCE_BACKED_STRONG"
        and operator_summary.get("next_action") == "READY_TO_APPLY_OR_HANDOFF"
        and not operator_summary.get("semantic_blockers")
        and int(source_claim_gap_report.get("summary", {}).get("blocked_cards", 0)) == 0
    )
    first_missing_chain = _first_missing_chain(source_claim_gap_report)
    return {
        "schema_version": 1,
        "deck_name": deck_name,
        "fixture_stage": fixture_stage,
        "promotion_ready": promotion_ready,
        "verdict": "SOURCE_BACKED_STRONG_CONFIRMED" if promotion_ready else "PROMOTION_BLOCKED",
        "next_action": "fixture_can_be_core_source_backed" if promotion_ready else "close_first_missing_chain",
        "operator_status": {
            "technical_status": operator_summary.get("technical_status"),
            "semantic_status": operator_summary.get("semantic_status"),
            "operator_next_action": operator_summary.get("next_action"),
        },
        "semantic_blockers": operator_summary.get("semantic_blockers", []),
        "first_missing_chain": first_missing_chain,
    }


def _first_missing_chain(source_claim_gap_report: dict[str, Any]) -> dict[str, str] | None:
    cards = source_claim_gap_report.get("cards", {})
    if not isinstance(cards, dict):
        return None
    for card_id, row in sorted(cards.items()):
        if not isinstance(row, dict):
            continue
        if row.get("first_missing_link") == "none":
            continue
        return {
            "card_id": str(card_id),
            "first_missing_link": str(row.get("first_missing_link", "")),
            "recommended_source_claim_kind": str(row.get("recommended_source_claim_kind", "")),
            "next_action": str(row.get("next_action", "")),
        }
    return None

from __future__ import annotations

from collections import Counter
from typing import Any


RECOMMENDED_CLAIM_KIND_BY_MISSING_LINK = {
    "none": "none",
    "needs_guide_claim": "card_role",
    "needs_runtime_surface": "targeting_rule",
    "needs_mulligan_claim": "mulligan_keep",
    "needs_combo_sequence": "combo_sequence",
    "needs_condition_lowering": "targeting_rule",
    "needs_mechanic_lowering": "mechanic_usage",
}

NEXT_ACTION_BY_MISSING_LINK = {
    "none": "card_ready_for_strong_gate",
    "needs_guide_claim": "add_card_specific_source_claim",
    "needs_runtime_surface": "add_runtime_lowerable_claim_or_router_support",
    "needs_mulligan_claim": "add_mulligan_keep_or_discard_claim",
    "needs_combo_sequence": "add_exact_combo_sequence_claim",
    "needs_condition_lowering": "rewrite_condition_to_supported_visionai_syntax",
    "needs_mechanic_lowering": "add_documented_mechanic_runtime_lowering",
}


def build_source_claim_gap_report(
    *,
    deck_name: str,
    config_readiness_report: dict[str, Any],
    claim_coverage_report: dict[str, Any],
    card_behavior_plan: dict[str, Any],
    mulligan_plan: dict[str, Any],
    combo_plan: dict[str, Any],
) -> dict[str, Any]:
    cards = config_readiness_report.get("cards", {})
    if not isinstance(cards, dict):
        cards = {}
    coverage_cards = claim_coverage_report.get("cards", {})
    if not isinstance(coverage_cards, dict):
        coverage_cards = {}

    counts: Counter[str] = Counter()
    rows: dict[str, dict[str, Any]] = {}
    for card_id, row in sorted(cards.items()):
        if not isinstance(row, dict):
            continue
        missing_link = str(row.get("first_missing_link", "needs_guide_claim"))
        counts[missing_link] += 1
        coverage = coverage_cards.get(card_id, {})
        if not isinstance(coverage, dict):
            coverage = {}
        rows[str(card_id)] = {
            "card_id": str(card_id),
            "name": str(row.get("name", card_id)),
            "readiness_lane": str(row.get("readiness_lane", "")),
            "first_missing_link": missing_link,
            "coverage_status": str(coverage.get("coverage_status", row.get("coverage_status", ""))),
            "source_claim_ids": [str(item) for item in coverage.get("source_claim_ids", row.get("source_claim_ids", []))],
            "runtime_surfaces": [str(item) for item in row.get("runtime_surfaces", [])],
            "recommended_source_claim_kind": RECOMMENDED_CLAIM_KIND_BY_MISSING_LINK.get(
                missing_link,
                "card_role",
            ),
            "next_action": NEXT_ACTION_BY_MISSING_LINK.get(missing_link, "inspect_card_gap"),
        }

    blocked_cards = sum(count for key, count in counts.items() if key != "none")
    return {
        "schema_version": 1,
        "deck_name": deck_name,
        "summary": {
            "total_cards": len(rows),
            "blocked_cards": blocked_cards,
            "needs_guide_claim": counts["needs_guide_claim"],
            "needs_runtime_surface": counts["needs_runtime_surface"],
            "needs_combo_sequence": counts["needs_combo_sequence"],
            "needs_mulligan_claim": counts["needs_mulligan_claim"],
            "needs_condition_lowering": counts["needs_condition_lowering"],
            "needs_mechanic_lowering": counts["needs_mechanic_lowering"],
        },
        "cards": rows,
        "inputs": {
            "card_behavior_rows": len(card_behavior_plan.get("rows", [])),
            "mulligan_rules": len(mulligan_plan.get("rules", [])),
            "combo_count": len(combo_plan.get("combos", [])),
        },
    }

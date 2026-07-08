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

BASE_PRIORITY_BY_MISSING_LINK = {
    "none": 0,
    "needs_mulligan_claim": 90,
    "needs_runtime_surface": 80,
    "needs_combo_sequence": 75,
    "needs_condition_lowering": 70,
    "needs_mechanic_lowering": 65,
    "needs_guide_claim": 50,
}

SOURCE_DEPTH_LANE_BY_MISSING_LINK = {
    "none": "closed",
    "needs_guide_claim": "source_claim_gap",
    "needs_runtime_surface": "runtime_surface_gap",
    "needs_mulligan_claim": "mulligan_claim_gap",
    "needs_combo_sequence": "combo_sequence_gap",
    "needs_condition_lowering": "condition_lowering_gap",
    "needs_mechanic_lowering": "mechanic_lowering_gap",
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
        source_depth_lane = str(
            row.get("source_depth_lane", _source_depth_lane_from_missing_link(missing_link))
        )
        counts[missing_link] += 1
        coverage = coverage_cards.get(card_id, {})
        if not isinstance(coverage, dict):
            coverage = {}
        priority_score, priority_reason = _priority_for_row(
            missing_link=missing_link,
            readiness_lane=str(row.get("readiness_lane", "")),
            runtime_surfaces=[str(item) for item in row.get("runtime_surfaces", [])],
        )
        rows[str(card_id)] = {
            "card_id": str(card_id),
            "name": str(row.get("name", card_id)),
            "readiness_lane": str(row.get("readiness_lane", "")),
            "first_missing_link": missing_link,
            "source_depth_lane": source_depth_lane,
            "coverage_status": str(coverage.get("coverage_status", row.get("coverage_status", ""))),
            "source_claim_ids": [str(item) for item in coverage.get("source_claim_ids", row.get("source_claim_ids", []))],
            "runtime_surfaces": [str(item) for item in row.get("runtime_surfaces", [])],
            "recommended_source_claim_kind": RECOMMENDED_CLAIM_KIND_BY_MISSING_LINK.get(
                missing_link,
                "card_role",
            ),
            "next_action": NEXT_ACTION_BY_MISSING_LINK.get(missing_link, "inspect_card_gap"),
            "priority_score": priority_score,
            "priority_reason": priority_reason,
        }

    blocked_cards = sum(count for key, count in counts.items() if key != "none")
    first_missing_chain = _first_missing_chain(rows)
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
            "first_missing_chain": first_missing_chain,
            "next_source_builder_action": (
                first_missing_chain["next_action"]
                if first_missing_chain is not None
                else "card_ready_for_strong_gate"
            ),
        },
        "cards": rows,
        "inputs": {
            "card_behavior_rows": len(card_behavior_plan.get("rows", [])),
            "mulligan_rules": len(mulligan_plan.get("rules", [])),
            "combo_count": len(combo_plan.get("combos", [])),
        },
    }


def _priority_for_row(
    *,
    missing_link: str,
    readiness_lane: str,
    runtime_surfaces: list[str],
) -> tuple[int, str]:
    score = BASE_PRIORITY_BY_MISSING_LINK.get(missing_link, 40)
    reasons = [f"missing_link:{missing_link}"]
    if readiness_lane == "report_only_supported" and missing_link != "none":
        score += 5
        reasons.append("report_only_supported:+5")
    if runtime_surfaces and missing_link not in {"none", "needs_runtime_surface"}:
        score -= 10
        reasons.append("partial_runtime_surface:-10")
    return score, ", ".join(reasons)


def _source_depth_lane_from_missing_link(missing_link: str) -> str:
    return SOURCE_DEPTH_LANE_BY_MISSING_LINK.get(missing_link, "inspect_card_gap")


def _first_missing_chain(rows: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    blocked = [row for row in rows.values() if row["first_missing_link"] != "none"]
    if not blocked:
        return None
    selected = max(blocked, key=lambda row: (row["priority_score"], row["card_id"]))
    return {
        "card_id": selected["card_id"],
        "name": selected["name"],
        "first_missing_link": selected["first_missing_link"],
        "source_depth_lane": selected["source_depth_lane"],
        "recommended_source_claim_kind": selected["recommended_source_claim_kind"],
        "next_action": selected["next_action"],
        "priority_score": selected["priority_score"],
        "priority_reason": selected["priority_reason"],
    }

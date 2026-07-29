from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any


SOURCE_QUALITY_LANES = {
    "guide_backed",
    "source_backed_static_semantics",
    "archetype_inferred",
    "explicit_low_confidence",
    "generic_low_confidence",
    "contract_gap",
}

COVERAGE_STATUS_TO_QUALITY_LANE = {
    "guide_backed": "guide_backed",
    "source_backed": "guide_backed",
    "source_backed_static_semantics": "source_backed_static_semantics",
    "static_semantics_backfilled": "source_backed_static_semantics",
    "uncovered_low_confidence": "generic_low_confidence",
}

CONTRACT_GAP_MISSING_LINKS = {
    "needs_runtime_surface",
    "needs_condition_lowering",
    "needs_target_scope",
    "needs_invalid_target_scope",
    "needs_target_surface",
    "needs_mechanic_lowering",
    "unsupported_claim_kind",
    "surface_gate_rejected",
}


RECOMMENDED_CLAIM_KIND_BY_MISSING_LINK = {
    "none": "none",
    "needs_guide_claim": "card_role",
    "needs_runtime_surface": "targeting_rule",
    "needs_mulligan_claim": "mulligan_claim",
    "needs_combo_sequence": "combo_sequence",
    "needs_condition_lowering": "targeting_rule",
    "needs_target_scope": "targeting_rule",
    "needs_invalid_target_scope": "targeting_rule",
    "needs_target_surface": "targeting_rule",
    "needs_mechanic_lowering": "mechanic_usage",
}

NEXT_ACTION_BY_MISSING_LINK = {
    "none": "card_ready_for_strong_gate",
    "needs_guide_claim": "add_card_specific_source_claim",
    "needs_runtime_surface": "add_runtime_lowerable_claim_or_router_support",
    "needs_mulligan_claim": "add_mulligan_keep_or_discard_claim",
    "needs_combo_sequence": "add_exact_combo_sequence_claim",
    "needs_condition_lowering": "rewrite_condition_to_supported_visionai_syntax",
    "needs_target_scope": "add_explicit_target_scope",
    "needs_invalid_target_scope": "replace_invalid_target_scope_with_documented_scope",
    "needs_target_surface": "add_documented_target_runtime_surface",
    "needs_mechanic_lowering": "add_documented_mechanic_runtime_lowering",
}

BASE_PRIORITY_BY_MISSING_LINK = {
    "none": 0,
    "needs_mulligan_claim": 90,
    "needs_runtime_surface": 80,
    "needs_combo_sequence": 75,
    "needs_condition_lowering": 70,
    "needs_target_scope": 70,
    "needs_invalid_target_scope": 70,
    "needs_target_surface": 70,
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
    "needs_target_scope": "target_scope_gap",
    "needs_invalid_target_scope": "invalid_target_scope_gap",
    "needs_target_surface": "target_surface_gap",
    "needs_mechanic_lowering": "mechanic_lowering_gap",
}


def suppressed_mulligan_claims_from_lifecycle(
    lifecycle_rows: Sequence[Mapping[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Return report-only Mulligan claims with their real lifecycle provenance."""
    claims: list[dict[str, Any]] = []
    for row in lifecycle_rows or []:
        if not isinstance(row, Mapping):
            continue
        if row.get("runtime_eligibility") != "report_only":
            continue
        claim_kind = str(row.get("claim_kind", ""))
        if claim_kind not in {"mulligan_keep", "mulligan_discard"}:
            continue
        source_claim = row.get("claim")
        if not isinstance(source_claim, Mapping):
            continue
        claim = dict(source_claim)
        claim["claim_kind"] = claim_kind
        claim["_claim_lifecycle"] = {
            "claim_id": str(row.get("claim_id", "")),
            "surface": "mulligan",
            "policy_lane": str(row.get("policy_lane", "")),
            "surface_gate_allowed": False,
            "surface_gate_reason": str(
                claim.get("runtime_lowering_reason")
                or "claim_not_runtime_lowerable"
            ),
        }
        claims.append(claim)
    return claims


def build_source_claim_gap_report(
    *,
    deck_name: str = "",
    config_readiness_report: dict[str, Any] | None = None,
    claim_coverage_report: dict[str, Any],
    card_behavior_plan: dict[str, Any] | None = None,
    mulligan_plan: dict[str, Any] | None = None,
    combo_plan: dict[str, Any] | None = None,
    deck_cards: list[dict[str, Any]] | None = None,
    source_contract_audit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config_readiness_report = config_readiness_report or {}
    card_behavior_plan = card_behavior_plan or {}
    mulligan_plan = mulligan_plan or {}
    combo_plan = combo_plan or {}
    if deck_cards is not None:
        config_readiness_report = _compatibility_readiness_report(
            deck_cards=deck_cards,
            claim_coverage_report=claim_coverage_report,
            source_contract_audit=source_contract_audit or {},
        )
    cards = config_readiness_report.get("cards", {})
    if not isinstance(cards, dict):
        cards = {}
    coverage_cards = claim_coverage_report.get("cards", claim_coverage_report.get("card_rows", {}))
    if not isinstance(coverage_cards, dict):
        coverage_cards = {}

    counts: Counter[str] = Counter()
    quality_lane_counts: Counter[str] = Counter()
    next_claim_kind_counts: Counter[str] = Counter()
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
        quality_lane = _source_quality_lane(readiness_row=row, coverage_row=coverage)
        next_claim_kind = _recommended_next_claim_kind(missing_link, quality_lane)
        next_claim_kinds = _recommended_next_claim_kinds(missing_link, next_claim_kind)
        if next_claim_kind != "none":
            next_claim_kind_counts[next_claim_kind] += 1
        quality_lane_counts[quality_lane] += 1
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
            "source_quality_lane": quality_lane,
            "recommended_next_claim_kind": next_claim_kind,
            "recommended_next_claim_kinds": next_claim_kinds,
            "recommended_next_source_action": _recommended_next_source_action(
                missing_link,
                next_claim_kind,
            ),
        }

    blocked_cards = sum(count for key, count in counts.items() if key != "none")
    deck_surfaces = {"mulligan": _mulligan_surface_row(mulligan_plan)}
    deck_surface_gap_count = sum(
        1
        for row in deck_surfaces.values()
        if row["first_missing_link"] != "none"
    )
    card_first_missing_chain = _first_missing_chain(rows)
    deck_first_missing_chain = _first_missing_surface_chain(deck_surfaces)
    first_missing_chain = card_first_missing_chain or deck_first_missing_chain
    suppressed_claim_rows = _suppressed_claim_rows(
        card_behavior_plan=card_behavior_plan,
        source_contract_audit=source_contract_audit or {},
    )
    return {
        "schema_version": 1,
        "deck_name": deck_name,
        "summary": {
            "total_cards": len(rows),
            "blocked_cards": blocked_cards,
            "deck_surface_gap_count": deck_surface_gap_count,
            "needs_guide_claim": counts["needs_guide_claim"],
            "needs_runtime_surface": counts["needs_runtime_surface"],
            "needs_combo_sequence": counts["needs_combo_sequence"],
            "needs_mulligan_claim": counts["needs_mulligan_claim"],
            "needs_condition_lowering": counts["needs_condition_lowering"],
            "needs_target_scope": counts["needs_target_scope"],
            "needs_invalid_target_scope": counts["needs_invalid_target_scope"],
            "needs_target_surface": counts["needs_target_surface"],
            "needs_mechanic_lowering": counts["needs_mechanic_lowering"],
            "first_missing_chain": first_missing_chain,
            "next_source_builder_action": (
                first_missing_chain["next_action"]
                if first_missing_chain is not None
                else "card_ready_for_strong_gate"
            ),
            "source_quality_lane_counts": dict(sorted(quality_lane_counts.items())),
            "cards_with_generic_low_confidence": quality_lane_counts["generic_low_confidence"],
            "cards_with_contract_gap": quality_lane_counts["contract_gap"],
            "next_claim_kind_counts": dict(sorted(next_claim_kind_counts.items())),
        },
        "cards": rows,
        "card_rows": rows,
        "deck_surfaces": deck_surfaces,
        "suppressed_claim_rows": suppressed_claim_rows,
        "inputs": {
            "card_behavior_rows": len(card_behavior_plan.get("rows", [])),
            "mulligan_rules": len(mulligan_plan.get("rules", [])),
            "combo_count": len(combo_plan.get("combos", [])),
        },
    }


def normalize_first_missing_link(row: dict[str, Any]) -> str:
    first_missing_link = str(row.get("first_missing_link") or "")
    normalized_first_missing_link = _normalized_missing_link(first_missing_link)
    if normalized_first_missing_link is not None:
        return normalized_first_missing_link
    if first_missing_link and not _is_generic_first_missing_link(first_missing_link):
        return first_missing_link

    suppressed_reason = str(row.get("suppressed_reason") or "")
    normalized_suppressed_reason = _normalized_missing_link(suppressed_reason)
    if normalized_suppressed_reason is not None:
        return normalized_suppressed_reason

    reason = str(row.get("reason") or "")
    normalized_reason = _normalized_missing_link(reason)
    if normalized_reason is not None:
        return normalized_reason
    if reason:
        return reason
    if suppressed_reason:
        return suppressed_reason
    return "claim_kind_supported_surface"


def _is_generic_first_missing_link(value: str) -> bool:
    return value in {"none", "closed", "runtime_surface", "suppressed"}


def _normalized_missing_link(reason: str) -> str | None:
    if reason in {"missing_target_scope", "no_target_scope"}:
        return "needs_target_scope"
    if reason == "invalid_target_scope":
        return "needs_invalid_target_scope"
    if reason == "target_scope_not_encoded":
        return "needs_target_surface"
    if reason in {"requires_runtime_evidence", "globalvalue_runtime_evidence_required"}:
        return "runtime_evidence"
    if reason in {"requires_exact_option_identity", "unresolved_option_identity"}:
        return "option_identity"
    if reason == "requires_supported_cardid_surface":
        return "supported_cardid_surface"
    if reason == "source_claim_conflict":
        return "source_claim_conflict"
    return None


def _suppressed_claim_rows(
    *,
    card_behavior_plan: dict[str, Any],
    source_contract_audit: dict[str, Any],
) -> list[dict[str, Any]]:
    rows_by_claim_id: dict[str, dict[str, Any]] = {}
    for row in card_behavior_plan.get("suppressed", []):
        if not isinstance(row, dict):
            continue
        suppressed_row = _suppressed_claim_row(row)
        rows_by_claim_id[suppressed_row["claim_id"]] = suppressed_row
    for row in source_contract_audit.get("claim_lifecycle_rows", []):
        if not isinstance(row, dict):
            continue
        if row.get("builder_or_router_decision") not in {
            "suppressed",
            "not_seen_by_builder",
        }:
            continue
        suppressed_row = _suppressed_claim_row(row)
        rows_by_claim_id[suppressed_row["claim_id"]] = suppressed_row
    return list(rows_by_claim_id.values())


def _suppressed_claim_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "claim_id": str(row.get("claim_id", "")),
        "claim_kind": str(row.get("claim_kind", "")),
        "builder_or_router_decision": str(
            row.get("builder_or_router_decision") or "suppressed"
        ),
        "first_missing_link": normalize_first_missing_link(row),
        "operator_impact": "diagnostic_only",
    }


def _mulligan_surface_row(mulligan_plan: dict[str, Any]) -> dict[str, Any]:
    quality = mulligan_plan.get("quality", {})
    if not isinstance(quality, dict):
        quality = {}
    rules = mulligan_plan.get("rules", [])
    if not isinstance(rules, list):
        rules = []
    policy_count = _safe_int(quality.get("policy_backed_keep_rule_count", 0))
    source_count = _safe_int(quality.get("source_backed_keep_rule_count", 0))
    has_keeps = bool(quality.get("has_concrete_keeps")) or any(
        isinstance(row, dict)
        and row.get("action") == "hold"
        and row.get("selector_kind") != "wildcard"
        for row in rules
    )
    if source_count:
        return {
            "surface": "mulligan",
            "first_missing_link": "none",
            "source_depth_lane": "source_backed_mulligan",
            "source_quality_lane": "guide_backed",
            "recommended_source_claim_kind": "none",
            "recommended_next_claim_kind": "none",
            "recommended_next_claim_kinds": [],
            "next_action": "mulligan_surface_closed",
        }
    if policy_count or has_keeps:
        return {
            "surface": "mulligan",
            "first_missing_link": "none",
            "source_depth_lane": "versioned_internal_policy",
            "source_quality_lane": "policy_backed",
            "policy_lanes": _string_list(quality.get("policy_lanes")),
            "policy_reasons": _string_list(quality.get("policy_reasons")),
            "recommended_source_claim_kind": "none",
            "recommended_next_claim_kind": "none",
            "recommended_next_claim_kinds": [],
            "next_action": "mulligan_surface_closed_by_policy",
        }
    if quality.get("default_only") is not True and quality.get("status") != "thin":
        return {
            "surface": "mulligan",
            "first_missing_link": "none",
            "source_depth_lane": "not_evaluated",
            "source_quality_lane": "not_evaluated",
            "recommended_source_claim_kind": "none",
            "recommended_next_claim_kind": "none",
            "recommended_next_claim_kinds": [],
            "next_action": "none",
        }
    return {
        "surface": "mulligan",
        "first_missing_link": "needs_mulligan_claim",
        "source_depth_lane": "mulligan_claim_gap",
        "source_quality_lane": "contract_gap",
        "recommended_source_claim_kind": "mulligan_claim",
        "recommended_next_claim_kind": "mulligan_claim",
        "recommended_next_claim_kinds": ["mulligan_keep", "mulligan_discard"],
        "next_action": "build_source_or_policy_backed_mulligan",
    }


def _source_quality_lane(
    *,
    readiness_row: dict[str, Any],
    coverage_row: dict[str, Any],
) -> str:
    first_missing_link = str(readiness_row.get("first_missing_link", ""))
    if first_missing_link in CONTRACT_GAP_MISSING_LINKS:
        return "contract_gap"

    coverage_status = str(
        coverage_row.get("coverage_status", readiness_row.get("coverage_status", ""))
    )
    coverage_lane = COVERAGE_STATUS_TO_QUALITY_LANE.get(coverage_status)
    if coverage_lane is not None:
        return coverage_lane

    readiness_lane = str(readiness_row.get("readiness_lane", ""))
    if readiness_lane in SOURCE_QUALITY_LANES:
        return readiness_lane

    source_depth_lane = str(readiness_row.get("source_depth_lane", ""))
    if source_depth_lane in SOURCE_QUALITY_LANES:
        return source_depth_lane

    if first_missing_link in {"missing_source_claim", "missing_card_specific_source"}:
        return "generic_low_confidence"
    if first_missing_link == "needs_guide_claim":
        return "generic_low_confidence"
    return "archetype_inferred"


def _recommended_next_claim_kind(first_missing_link: str, lane: str) -> str:
    if first_missing_link in {"missing_source_claim", "missing_card_specific_source", "needs_guide_claim"}:
        return "card_role"
    if first_missing_link in {
        "missing_targeting_claim",
        "needs_runtime_surface",
        "needs_target_scope",
        "needs_invalid_target_scope",
        "needs_target_surface",
    }:
        return "targeting_rule"
    if first_missing_link in {"missing_mulligan_claim", "needs_mulligan_claim"}:
        return "mulligan_claim"
    if first_missing_link in {"missing_combo_sequence", "needs_combo_sequence"}:
        return "combo_sequence"
    if lane == "generic_low_confidence":
        return "card_role"
    return "none"


def _recommended_next_claim_kinds(first_missing_link: str, next_claim_kind: str) -> list[str]:
    if first_missing_link in {"missing_mulligan_claim", "needs_mulligan_claim"}:
        return ["mulligan_keep", "mulligan_discard"]
    if next_claim_kind == "none":
        return []
    return [next_claim_kind]


def _recommended_next_source_action(first_missing_link: str, next_claim_kind: str) -> str:
    if next_claim_kind == "none":
        return "none"
    if next_claim_kind == "mulligan_claim":
        return "add explicit mulligan_keep or mulligan_discard source evidence"
    if next_claim_kind == "targeting_rule":
        return "add a card-specific target or usage claim"
    if next_claim_kind == "combo_sequence":
        return "add an ordered combo sequence with timing fields"
    return "add a card-specific guide claim or source-backed static semantic claim"


def _compatibility_readiness_report(
    *,
    deck_cards: list[dict[str, Any]],
    claim_coverage_report: dict[str, Any],
    source_contract_audit: dict[str, Any],
) -> dict[str, Any]:
    coverage_rows = claim_coverage_report.get("card_rows", {})
    audit_rows = source_contract_audit.get("card_rows", {})
    cards: dict[str, dict[str, Any]] = {}
    for card in deck_cards:
        card_id = str(card["card_id"])
        coverage = coverage_rows.get(card_id, {})
        audit = audit_rows.get(card_id, {})
        cards[card_id] = {
            "card_id": card_id,
            "name": str(card.get("name", card_id)),
            "source_depth_lane": coverage.get("source_depth_lane", ""),
            "first_missing_link": (
                "none"
                if audit.get("first_missing_link") == "closed"
                else str(audit.get("first_missing_link", "missing_source_claim"))
            ),
            "runtime_surfaces": list(audit.get("runtime_surfaces", [])),
        }
    return {"cards": cards}


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
        "recommended_next_claim_kind": selected["recommended_next_claim_kind"],
        "recommended_next_claim_kinds": selected["recommended_next_claim_kinds"],
        "next_action": selected["next_action"],
        "priority_score": selected["priority_score"],
        "priority_reason": selected["priority_reason"],
    }


def _first_missing_surface_chain(
    deck_surfaces: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    blocked = [row for row in deck_surfaces.values() if row["first_missing_link"] != "none"]
    if not blocked:
        return None
    selected = max(blocked, key=lambda row: BASE_PRIORITY_BY_MISSING_LINK.get(row["first_missing_link"], 40))
    return {
        **selected,
        "priority_score": BASE_PRIORITY_BY_MISSING_LINK.get(selected["first_missing_link"], 40),
        "priority_reason": f"deck_surface:{selected['surface']}",
    }


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item)]

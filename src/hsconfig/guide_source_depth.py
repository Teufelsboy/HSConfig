from __future__ import annotations

from collections import Counter
from typing import Any

from hsconfig.source_document_model import claim_can_lower_to_runtime


SUPPORTED_READINESS_LANES = {
    "runtime_emitted",
    "mulligan_only",
    "globalvalues_only",
    "report_only_supported",
}


def build_guide_source_depth_report(
    *,
    guide_claim_bundle: dict[str, Any],
    config_readiness_report: dict[str, Any],
    source_evidence_verification_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    claims = [claim for claim in guide_claim_bundle.get("claims", []) if isinstance(claim, dict)]
    unsupported_claims = [
        claim for claim in guide_claim_bundle.get("unsupported_claims", []) if isinstance(claim, dict)
    ]
    source_families = Counter(_claim_source_family(claim) for claim in claims)
    claim_kinds = Counter(_claim_kind(claim) for claim in claims)
    lowerable_claims = sum(1 for claim in claims if claim_can_lower_to_runtime(claim))
    report_only_claims = sum(
        1
        for claim in claims
        if str(claim.get("trust_ceiling", "")).lower() == "report_only"
        or str(claim.get("claim_readiness", "")).lower()
        in {"explicit_low_confidence", "generic_low_confidence", "contract_gap"}
    )

    cards = _cards(config_readiness_report)
    warnings: list[dict[str, str]] = []
    supported_cards = 0
    for card_id, row in sorted(cards.items()):
        lane = str(row.get("readiness_lane", "generic_low_confidence"))
        first_missing_link = str(row.get("first_missing_link", "needs_guide_claim"))
        if lane in SUPPORTED_READINESS_LANES:
            supported_cards += 1
        if first_missing_link != "none":
            warnings.append(
                {
                    "card_id": str(card_id),
                    "reason": first_missing_link,
                    "readiness_lane": lane,
                }
            )
    warnings.extend(_claim_gate_warnings(guide_claim_bundle))

    total_cards = _total_cards(config_readiness_report, cards)
    cards_needing_guide_claims = sum(
        1 for warning in warnings if warning["reason"] == "needs_guide_claim"
    )
    cards_needing_runtime_surface = sum(
        1 for warning in warnings if warning["reason"] == "needs_runtime_surface"
    )
    depth_status = "usable"
    if total_cards > 0 and supported_cards == 0 and cards_needing_guide_claims == 0:
        depth_status = "insufficient"
    if (
        total_cards > 0
        and cards_needing_runtime_surface > 0
        and cards_needing_guide_claims == 0
    ):
        depth_status = "usable_with_runtime_gaps"
    if total_cards > 0 and cards_needing_guide_claims > 0:
        depth_status = "needs_more_research"
    source_depth_status = depth_status
    if lowerable_claims > 0 and report_only_claims == 0 and not warnings:
        source_depth_status = "source_backed"
    if lowerable_claims == 0 or cards_needing_guide_claims > 0:
        source_depth_status = "needs_more_research"

    return {
        "depth_status": depth_status,
        "source_depth_status": source_depth_status,
        "summary": {
            "claim_count": len(claims),
            "unsupported_claim_count": len(unsupported_claims),
            "lowerable_claims": lowerable_claims,
            "report_only_claims": report_only_claims,
            "total_cards": total_cards,
            "supported_cards": supported_cards,
            "cards_needing_guide_claims": cards_needing_guide_claims,
            "cards_needing_runtime_surface": cards_needing_runtime_surface,
            "warnings_count": len(warnings),
        },
        "source_families": dict(sorted(source_families.items())),
        "claim_kinds": dict(sorted(claim_kinds.items())),
        "source_evidence": _source_evidence_summary(source_evidence_verification_report),
        "warnings": warnings,
    }


def _cards(config_readiness_report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw_cards = config_readiness_report.get("cards", {})
    if not isinstance(raw_cards, dict):
        return {}
    return {str(card_id): row for card_id, row in raw_cards.items() if isinstance(row, dict)}


def _total_cards(
    config_readiness_report: dict[str, Any],
    cards: dict[str, dict[str, Any]],
) -> int:
    summary = config_readiness_report.get("summary", {})
    if isinstance(summary, dict):
        try:
            return int(summary.get("total_cards", len(cards)))
        except (TypeError, ValueError):
            return len(cards)
    return len(cards)


def _claim_gate_warnings(guide_claim_bundle: dict[str, Any]) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    conflict_report = guide_claim_bundle.get("claim_conflict_report", {})
    if isinstance(conflict_report, dict):
        conflict_count = _int_value(conflict_report.get("conflict_count", 0))
        if conflict_count > 0:
            warnings.append(
                {"reason": "claim_conflicts_present", "conflict_count": conflict_count}
            )
    coverage_report = guide_claim_bundle.get("claim_coverage_report", {})
    if isinstance(coverage_report, dict):
        low_confidence_count = _low_confidence_card_count(coverage_report)
        if low_confidence_count > 0:
            warnings.append(
                {
                    "reason": "cards_still_low_confidence",
                    "card_count": low_confidence_count,
                }
            )
    return warnings


def _source_evidence_summary(report: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(report, dict):
        return {"warnings_count": 0}

    summary = report.get("summary", {})
    if not isinstance(summary, dict):
        summary = {}
    return {
        "status": str(report.get("status", "")),
        "document_count": _int_value(summary.get("document_count", 0)),
        "claim_count": _int_value(summary.get("claim_count", 0)),
        "runtime_lowering_claims": _int_value(summary.get("runtime_lowering_claims", 0)),
        "warnings_count": _int_value(summary.get("warnings_count", 0)),
    }


def _low_confidence_card_count(report: dict[str, Any]) -> int:
    summary = report.get("summary", {})
    if isinstance(summary, dict) and "uncovered_low_confidence" in summary:
        return _int_value(summary.get("uncovered_low_confidence", 0))
    cards = report.get("cards", {})
    if not isinstance(cards, dict):
        return 0
    return sum(
        1
        for row in cards.values()
        if isinstance(row, dict) and row.get("coverage_status") == "uncovered_low_confidence"
    )


def _int_value(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _claim_source_family(claim: dict[str, Any]) -> str:
    return str(claim.get("source_family", "unknown"))


def _claim_kind(claim: dict[str, Any]) -> str:
    return str(claim.get("claim_kind", claim.get("claim_type", "unknown")))

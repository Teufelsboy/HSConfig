from __future__ import annotations

from collections import Counter
from typing import Any


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
) -> dict[str, Any]:
    claims = [claim for claim in guide_claim_bundle.get("claims", []) if isinstance(claim, dict)]
    unsupported_claims = [
        claim for claim in guide_claim_bundle.get("unsupported_claims", []) if isinstance(claim, dict)
    ]
    source_families = Counter(_claim_source_family(claim) for claim in claims)
    claim_kinds = Counter(_claim_kind(claim) for claim in claims)

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

    return {
        "depth_status": depth_status,
        "summary": {
            "claim_count": len(claims),
            "unsupported_claim_count": len(unsupported_claims),
            "total_cards": total_cards,
            "supported_cards": supported_cards,
            "cards_needing_guide_claims": cards_needing_guide_claims,
            "cards_needing_runtime_surface": cards_needing_runtime_surface,
            "warnings_count": len(warnings),
        },
        "source_families": dict(sorted(source_families.items())),
        "claim_kinds": dict(sorted(claim_kinds.items())),
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


def _claim_source_family(claim: dict[str, Any]) -> str:
    return str(claim.get("source_family", "unknown"))


def _claim_kind(claim: dict[str, Any]) -> str:
    return str(claim.get("claim_kind", claim.get("claim_type", "unknown")))

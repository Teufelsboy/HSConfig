from __future__ import annotations

from hsconfig.strong_promotion_report import build_strong_promotion_report


def test_strong_promotion_requires_no_default_only_surfaces():
    report = build_strong_promotion_report(
        deck_name="ShadowPriest",
        fixture_stage="runtime",
        operator_summary={
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "SOURCE_BACKED_STRONG",
            "next_action": "READY_TO_APPLY_OR_HANDOFF",
            "default_only_runtime_surfaces": ["Mulligan.json"],
            "semantic_blockers": [],
        },
        source_claim_gap_report={
            "summary": {
                "blocked_cards": 0,
                "deck_surface_gap_count": 0,
            }
        },
    )

    assert report["promotion_ready"] is False
    assert report["verdict"] == "PROMOTION_BLOCKED"
    assert (
        report["first_missing_source_action"]
        == "replace_default_only_runtime_surface_with_source_or_policy_claim"
    )


def test_strong_promotion_accepts_closed_chain():
    report = build_strong_promotion_report(
        deck_name="ShadowPriest",
        fixture_stage="runtime",
        operator_summary={
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "SOURCE_BACKED_STRONG",
            "next_action": "READY_TO_APPLY_OR_HANDOFF",
            "default_only_runtime_surfaces": [],
            "semantic_blockers": [],
        },
        source_claim_gap_report={
            "summary": {
                "blocked_cards": 0,
                "deck_surface_gap_count": 0,
                "first_missing_chain": None,
            }
        },
    )

    assert report["promotion_ready"] is True
    assert report["first_missing_source_action"] == "none"

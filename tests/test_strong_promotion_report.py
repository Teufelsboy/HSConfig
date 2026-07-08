import pytest

from hsconfig.strong_promotion_report import build_strong_promotion_report


def test_report_marks_source_backed_strong_as_promotable():
    report = build_strong_promotion_report(
        deck_name="ShadowPriest",
        fixture_stage="core_source_backed_fixture",
        operator_summary={
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "SOURCE_BACKED_STRONG",
            "next_action": "READY_TO_APPLY_OR_HANDOFF",
            "semantic_blockers": [],
            "guide_strength_summary": {"generic_low_confidence_cards": 0},
        },
        source_claim_gap_report={"summary": {"blocked_cards": 0}, "cards": {}},
    )

    assert report["promotion_ready"] is True
    assert report["verdict"] == "SOURCE_BACKED_STRONG_CONFIRMED"
    assert report["next_action"] == "fixture_can_be_core_source_backed"


def test_report_explains_first_missing_chain_for_non_strong_deck():
    report = build_strong_promotion_report(
        deck_name="MechPala",
        fixture_stage="source_informed_valid_fixture",
        operator_summary={
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "VALID_BUT_NOT_GUIDE_STRONG",
            "next_action": "IMPROVE_GUIDE_SOURCES_BEFORE_STRONG_APPLY",
            "semantic_blockers": [{"reason": "cards_need_guide_claims", "count": 4}],
            "guide_strength_summary": {"generic_low_confidence_cards": 4},
        },
        source_claim_gap_report={
            "summary": {"blocked_cards": 4},
            "cards": {
                "CARD_A": {
                    "first_missing_link": "needs_guide_claim",
                    "recommended_source_claim_kind": "card_role",
                    "next_action": "add_card_specific_source_claim",
                }
            },
        },
    )

    assert report["promotion_ready"] is False
    assert report["verdict"] == "PROMOTION_BLOCKED"
    assert report["first_missing_chain"] == {
        "card_id": "CARD_A",
        "first_missing_link": "needs_guide_claim",
        "recommended_source_claim_kind": "card_role",
        "next_action": "add_card_specific_source_claim",
    }


def test_report_marks_source_informed_apply_ready_without_strong_promotion():
    readiness = {
        "status": "ready",
        "requires_flag": "--allow-source-informed",
        "allowed_blocker_reasons": [
            "cards_need_guide_claims",
            "cards_need_mulligan_claims",
        ],
        "blocking_reasons": [],
        "source_gap_count": 2,
    }
    report = build_strong_promotion_report(
        deck_name="Kingslayer",
        fixture_stage="source_informed_valid_fixture",
        operator_summary={
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "VALID_BUT_NOT_GUIDE_STRONG",
            "next_action": "SOURCE_INFORMED_APPLY_READY",
            "apply_policy": "ALLOWED_SOURCE_INFORMED",
            "source_informed_apply_readiness": readiness,
            "semantic_blockers": [{"reason": "cards_need_mulligan_claims", "count": 2}],
            "guide_strength_summary": {"generic_low_confidence_cards": 0},
        },
        source_claim_gap_report={"summary": {"blocked_cards": 2}, "cards": {}},
    )

    assert report["promotion_ready"] is False
    assert report["verdict"] == "PROMOTION_BLOCKED"
    assert report["next_action"] == "source_informed_apply_ready_but_not_strong"
    assert report["source_informed_apply_readiness"] == readiness


@pytest.mark.parametrize("surface_name", ["Presume.json", "Concede.json"])
def test_report_blocks_strong_promotion_when_normal_path_optional_surface_exists(surface_name):
    report = build_strong_promotion_report(
        deck_name="PirateDH",
        fixture_stage="core_source_backed_fixture",
        operator_summary={
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "SOURCE_BACKED_STRONG",
            "next_action": "READY_TO_APPLY_OR_HANDOFF",
            "semantic_blockers": [],
            "generated_files": [f"CustomConfig/piratedh/{surface_name}"],
        },
        source_claim_gap_report={"summary": {"blocked_cards": 0}, "cards": {}},
    )

    assert report["promotion_ready"] is False
    assert report["verdict"] == "PROMOTION_BLOCKED"
    assert report["next_action"] == "close_first_missing_chain"
    assert {
        "reason": "normal_path_optional_surface_present",
        "generated_file": f"CustomConfig/piratedh/{surface_name}",
    } in report["semantic_blockers"]


def test_report_keeps_canonical_next_action_for_invalid_package():
    report = build_strong_promotion_report(
        deck_name="Boarlock",
        fixture_stage="source_informed_valid_fixture",
        operator_summary={
            "technical_status": "INVALID_PACKAGE",
            "semantic_status": "INVALID_PACKAGE",
            "next_action": "FIX_PACKAGE_BEFORE_APPLY",
            "semantic_blockers": [],
            "generated_files": [],
        },
        source_claim_gap_report={
            "summary": {"blocked_cards": 3},
            "cards": {
                "CARD_A": {
                    "first_missing_link": "needs_guide_claim",
                    "recommended_source_claim_kind": "card_role",
                    "next_action": "add_card_specific_source_claim",
                }
            },
        },
    )

    assert report["promotion_ready"] is False
    assert report["verdict"] == "PROMOTION_BLOCKED"
    assert report["next_action"] == "FIX_PACKAGE_BEFORE_APPLY"
    assert report["operator_status"]["operator_next_action"] == "FIX_PACKAGE_BEFORE_APPLY"
    assert report["first_missing_chain"] == {
        "card_id": "CARD_A",
        "first_missing_link": "needs_guide_claim",
        "recommended_source_claim_kind": "card_role",
        "next_action": "add_card_specific_source_claim",
    }

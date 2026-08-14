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
    assert report["source_backed_status"] == "SOURCE_BACKED_STRONG"
    assert report["source_strong_ready"] is True
    assert report["source_missing_source_actions"] == []
    assert report["source_status_reasons"] == ["source_backed_strong_ready"]
    assert report["source_status_diagnostic_only"] is True
    assert report["source_status_apply_blocking"] is False
    assert report["verdict"] == "SOURCE_BACKED_STRONG_CONFIRMED"
    assert report["next_action"] == "fixture_can_be_core_source_backed"


def test_report_blocks_default_only_runtime_surface_from_operator_summary():
    report = build_strong_promotion_report(
        deck_name="ThinMulliganDeck",
        fixture_stage="core_source_backed_fixture",
        operator_summary={
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "SOURCE_BACKED_STRONG",
            "next_action": "READY_TO_APPLY_OR_HANDOFF",
            "semantic_blockers": [],
            "default_only_runtime_surfaces": ["mulligan"],
        },
        source_claim_gap_report={"summary": {"blocked_cards": 0}, "cards": {}},
    )

    assert report["promotion_ready"] is False
    assert report["source_backed_status"] == "SOURCE_BACKED_PARTIAL"
    assert report["source_strong_ready"] is False
    assert report["first_missing_source_action"] == (
        "replace_default_only_runtime_surface_with_source_or_policy_claim"
    )
    assert report["default_only_runtime_surfaces"] == ["mulligan"]
    assert report["source_status_reasons"] == ["default_only_runtime_surface"]
    assert report["source_status_apply_blocking"] is False
    assert report["verdict"] == "PROMOTION_BLOCKED"
    assert report["runtime_lowering_status"] == "LOAD_SAFE_WITH_POLICY_OR_REVIEW_ROWS"
    assert {
        "reason": "default_only_surface_not_strong_evidence",
        "surface": "mulligan",
    } in report["semantic_blockers"]


def test_report_blocks_strong_promotion_when_deck_surface_gap_is_open():
    first_missing_chain = {
        "surface": "mulligan",
        "first_missing_link": "needs_mulligan_claim",
        "recommended_source_claim_kind": "mulligan_claim",
        "next_action": "build_source_or_policy_backed_mulligan",
        "priority_score": 90,
        "priority_reason": "deck_surface:mulligan",
    }
    report = build_strong_promotion_report(
        deck_name="ThinMulliganDeck",
        fixture_stage="core_source_backed_fixture",
        operator_summary={
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "SOURCE_BACKED_STRONG",
            "next_action": "READY_TO_APPLY_OR_HANDOFF",
            "semantic_blockers": [],
            "guide_strength_summary": {"generic_low_confidence_cards": 0},
        },
        source_claim_gap_report={
            "summary": {
                "blocked_cards": 0,
                "deck_surface_gap_count": 1,
                "first_missing_chain": first_missing_chain,
            },
            "cards": {},
            "deck_surfaces": {
                "mulligan": {
                    "surface": "mulligan",
                    "first_missing_link": "needs_mulligan_claim",
                }
            },
        },
    )

    assert report["promotion_ready"] is False
    assert report["verdict"] == "PROMOTION_BLOCKED"
    assert report["next_action"] == "close_first_missing_chain"
    assert report["first_missing_chain"] == first_missing_chain


def test_report_uses_resolver_status_when_closure_profile_is_open():
    report = build_strong_promotion_report(
        deck_name="ShadowPriest",
        fixture_stage="core_source_backed_fixture",
        operator_summary={
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "SOURCE_BACKED_STRONG",
            "next_action": "READY_TO_APPLY_OR_HANDOFF",
            "semantic_blockers": [],
            "source_backed_strong_closure": {
                "closure_profile_closed": False,
                "closure_profile_first_missing_link": "missing_surface:mulligan",
                "closure_profile_apply_blocking": False,
            },
        },
        source_claim_gap_report={
            "summary": {
                "blocked_cards": 0,
                "deck_surface_gap_count": 0,
                "first_missing_chain": None,
            },
            "cards": {},
        },
    )

    assert report["promotion_ready"] is False
    assert report["source_backed_status"] == "SOURCE_BACKED_PARTIAL"
    assert report["static_contract_status"] == "SOURCE_BACKED_PARTIAL"
    assert report["first_missing_source_action"] == "add_profile_runtime_surface"
    assert report["source_status_reasons"] == ["closure_profile_not_closed"]


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
            "next_action": "READY_TO_APPLY_WITH_WARNINGS",
            "apply_policy": "ALLOWED_WITH_WARNINGS",
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
    assert report["first_missing_source_action"] == "add_explicit_mulligan_source"
    assert report["source_status_reasons"] == ["semantic_blocker"]


@pytest.mark.parametrize("surface_name", ["Presume.json", "Concede.json", "CardBehavior.json"])
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
    assert report["source_backed_status"] == "SOURCE_BACKED_PARTIAL"
    assert report["source_strong_ready"] is False
    assert report["source_status_reasons"] == ["semantic_blocker"]
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
    assert report["source_backed_status"] == "INVALID_PACKAGE"
    assert report["source_strong_ready"] is False
    assert report["source_status_reasons"] == ["technical_status_not_valid"]
    assert report["verdict"] == "PROMOTION_BLOCKED"
    assert report["next_action"] == "FIX_PACKAGE_BEFORE_APPLY"
    assert report["operator_status"]["operator_next_action"] == "FIX_PACKAGE_BEFORE_APPLY"
    assert report["first_missing_chain"] == {
        "card_id": "CARD_A",
        "first_missing_link": "needs_guide_claim",
        "recommended_source_claim_kind": "card_role",
        "next_action": "add_card_specific_source_claim",
    }


def test_report_reuses_source_gap_summary_first_missing_chain_priority_order():
    canonical = {
        "card_id": "ZZZ_HIGH_PRIORITY",
        "name": "High Priority Card",
        "first_missing_link": "needs_runtime_surface",
        "recommended_source_claim_kind": "targeting_rule",
        "next_action": "add_runtime_lowerable_claim_or_router_support",
        "priority_score": 85,
        "priority_reason": "runtime surface gap outranks guide claim gap",
    }

    report = build_strong_promotion_report(
        deck_name="CuteWarrior",
        fixture_stage="runtime_prepare",
        operator_summary={
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "VALID_BUT_NOT_GUIDE_STRONG",
            "next_action": "IMPROVE_GUIDE_SOURCES_BEFORE_STRONG_APPLY",
            "semantic_blockers": [{"reason": "cards_need_runtime_surface", "count": 1}],
            "generated_files": [],
        },
        source_claim_gap_report={
            "summary": {
                "blocked_cards": 2,
                "first_missing_chain": canonical,
            },
            "cards": {
                "AAA_LOW_PRIORITY": {
                    "first_missing_link": "needs_guide_claim",
                    "recommended_source_claim_kind": "card_role",
                    "next_action": "add_card_specific_source_claim",
                },
                "ZZZ_HIGH_PRIORITY": {
                    "first_missing_link": "needs_runtime_surface",
                    "recommended_source_claim_kind": "targeting_rule",
                    "next_action": "add_runtime_lowerable_claim_or_router_support",
                },
            },
        },
    )

    assert report["promotion_ready"] is False
    assert report["verdict"] == "PROMOTION_BLOCKED"
    assert report["next_action"] == "close_first_missing_chain"
    assert report["first_missing_chain"] == canonical


def test_report_preserves_neutral_mulligan_claim_choice_in_missing_chain():
    canonical = {
        "card_id": "DEEP_014",
        "name": "Quick Pick",
        "first_missing_link": "needs_mulligan_claim",
        "recommended_source_claim_kind": "mulligan_claim",
        "recommended_next_claim_kind": "mulligan_claim",
        "recommended_next_claim_kinds": ["mulligan_keep", "mulligan_discard"],
        "next_action": "add_mulligan_keep_or_discard_claim",
        "priority_score": 90,
        "priority_reason": "missing_link:needs_mulligan_claim",
    }

    report = build_strong_promotion_report(
        deck_name="Kingslayer",
        fixture_stage="source_informed_valid_fixture",
        operator_summary={
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "VALID_BUT_NOT_GUIDE_STRONG",
            "next_action": "READY_TO_APPLY_WITH_WARNINGS",
            "source_informed_apply_readiness": {"status": "ready"},
            "semantic_blockers": [{"reason": "cards_need_mulligan_claims", "count": 1}],
            "generated_files": [],
        },
        source_claim_gap_report={
            "summary": {
                "blocked_cards": 1,
                "first_missing_chain": canonical,
            },
            "cards": {},
        },
    )

    assert report["promotion_ready"] is False
    assert report["first_missing_chain"] == canonical
    assert report["first_missing_chain"]["recommended_source_claim_kind"] == "mulligan_claim"
    assert report["first_missing_chain"]["recommended_next_claim_kinds"] == [
        "mulligan_keep",
        "mulligan_discard",
    ]

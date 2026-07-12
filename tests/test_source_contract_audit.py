from __future__ import annotations

from hsconfig.source_contract_audit import (
    build_source_contract_audit,
    render_source_contract_audit_markdown,
)


def test_source_contract_audit_explains_surface_gate_lanes():
    report = build_source_contract_audit(
        deck_name="FixtureDeck",
        deck_identity={
            "deck_name": "FixtureDeck",
            "cards": [
                {"card_id": "CARD_KEEP", "name": "Keep Card", "count": 2},
                {"card_id": "CARD_NUM", "name": "Numeric Card", "count": 1},
            ],
        },
        guide_claim_bundle={
            "claims": [
                {
                    "claim_id": "keep_claim",
                    "claim_kind": "mulligan_keep",
                    "claim_readiness": "guide_backed",
                    "trust_ceiling": "runtime_candidate",
                    "cards": ["CARD_KEEP"],
                    "source_title": "Fixture Guide",
                    "evidence_text_short": "Keep CARD_KEEP.",
                },
                {
                    "claim_id": "numeric_claim",
                    "claim_kind": "globalvalue_numeric_tuning",
                    "claim_readiness": "guide_backed",
                    "trust_ceiling": "runtime_candidate",
                    "cards": ["CARD_NUM"],
                    "source_title": "Fixture Guide",
                    "evidence_text_short": "Tune LowHpBoardValuePenalty later.",
                },
            ]
        },
        mulligan_plan={
            "rules": [
                {
                    "card": "CARD_KEEP",
                    "action": "hold",
                    "source_claim_ids": ["keep_claim"],
                }
            ],
            "suppressed_rules": [],
        },
        card_behavior_plan={"rows": [], "suppressed": []},
        combo_plan={"combos": [], "suppressed": []},
        global_values_authority_matrix={
            "allowed_step1_overlays": [],
            "blocked_until_runtime_evidence": [
                {"key": "LowHpBoardValuePenalty", "claim_id": "numeric_claim"}
            ],
        },
        config_readiness_report={
            "cards": {
                "CARD_KEEP": {
                    "name": "Keep Card",
                    "roles": ["mulligan_anchor"],
                    "runtime_surfaces": ["Mulligan.json"],
                    "readiness_lane": "mulligan_only",
                    "first_missing_link": "needs_runtime_surface",
                },
                "CARD_NUM": {
                    "name": "Numeric Card",
                    "roles": [],
                    "runtime_surfaces": [],
                    "readiness_lane": "report_only_supported",
                    "first_missing_link": "none",
                },
            }
        },
    )

    assert report["schema_version"] == 1
    assert report["summary"]["claims_total"] == 2
    assert report["summary"]["runtime_lowered_claims"] == 1
    assert report["summary"]["runtime_evidence_required_claims"] == 1
    assert report["claim_rows"]["keep_claim"]["lane"] == "runtime_lowered"
    assert report["claim_rows"]["keep_claim"]["surfaces"]["mulligan"]["allowed"] is True
    assert report["claim_rows"]["numeric_claim"]["lane"] == "runtime_evidence_required"
    assert report["claim_rows"]["numeric_claim"]["surfaces"]["globalvalues"]["reason"] == (
        "requires_runtime_evidence"
    )
    assert report["card_rows"]["CARD_KEEP"]["first_missing_link"] == "needs_runtime_surface"
    assert report["card_rows"]["CARD_KEEP"]["claim_lanes"]["runtime_lowered"] == 1


def test_source_contract_audit_matches_real_source_claim_ids_and_claim_refs():
    report = build_source_contract_audit(
        deck_name="FixtureDeck",
        deck_identity={
            "deck_name": "FixtureDeck",
            "cards": [{"card_id": "CARD_KEEP", "name": "Keep Card", "count": 2}],
        },
        guide_claim_bundle={
            "claims": [
                {
                    "claim_id": "keep_claim",
                    "claim_kind": "mulligan_keep",
                    "claim_readiness": "guide_backed",
                    "trust_ceiling": "runtime_candidate",
                    "cards": ["CARD_KEEP"],
                    "source_title": "Fixture Guide",
                    "evidence_text_short": "Keep CARD_KEEP.",
                },
                {
                    "claim_id": "posture_claim",
                    "claim_kind": "gameplan_posture",
                    "claim_readiness": "guide_backed",
                    "trust_ceiling": "runtime_candidate",
                    "cards": [],
                    "source_title": "Fixture Guide",
                    "evidence_text_short": "Use an aggressive Hero Power posture.",
                },
            ]
        },
        mulligan_plan={
            "rules": [
                {
                    "card": "CARD_KEEP",
                    "action": "hold",
                    "source_claim_ids": ["keep_claim"],
                }
            ],
            "suppressed_rules": [],
        },
        card_behavior_plan={"rows": [], "suppressed": []},
        combo_plan={"combos": [], "suppressed": []},
        global_values_authority_matrix={
            "allowed_step1_overlays": [
                {
                    "key": "MyHeroPowerValue",
                    "operation": "increase",
                    "claim_refs": ["posture_claim"],
                }
            ],
            "blocked_until_runtime_evidence": [],
        },
        config_readiness_report={
            "cards": {
                "CARD_KEEP": {
                    "name": "Keep Card",
                    "roles": ["mulligan_anchor"],
                    "runtime_surfaces": ["Mulligan.json"],
                    "readiness_lane": "mulligan_only",
                    "first_missing_link": "none",
                }
            }
        },
    )

    assert report["claim_rows"]["keep_claim"]["lowered_surfaces"] == ["mulligan"]
    assert report["claim_rows"]["posture_claim"]["lowered_surfaces"] == [
        "globalvalues"
    ]
    assert report["summary"]["runtime_lowered_claims"] == 2


def test_source_contract_audit_preserves_start_of_game_effect_without_mulligan_keep():
    report = build_source_contract_audit(
        deck_name="ShadowPriest",
        deck_identity={
            "deck_name": "ShadowPriest",
            "cards": [{"card_id": "SW_448", "name": "Darkbishop Benedictus", "count": 1}],
        },
        guide_claim_bundle={
            "claims": [
                {
                    "claim_id": "darkbishop_effect",
                    "claim_kind": "hero_power_transform",
                    "claim_readiness": "source_backed_static_semantics",
                    "trust_ceiling": "runtime_candidate",
                    "cards": ["SW_448"],
                    "source_title": "Hearthstone card data",
                    "evidence_text_short": "Start of Game hero power transform.",
                },
                {
                    "claim_id": "bad_keep",
                    "claim_kind": "mulligan_keep",
                    "claim_readiness": "guide_backed",
                    "trust_ceiling": "runtime_candidate",
                    "cards": ["SW_448"],
                    "source_title": "Bad fixture",
                    "evidence_text_short": "Keep because the effect matters.",
                },
            ]
        },
        mulligan_plan={
            "rules": [],
            "suppressed_rules": [
                {
                    "claim_id": "bad_keep",
                    "card": "SW_448",
                    "reason": "start_of_game_effect_does_not_require_opening_hand",
                }
            ],
        },
        card_behavior_plan={
            "rows": [
                {
                    "claim_id": "darkbishop_effect",
                    "card_id": "SW_448",
                    "surface_family": "CARDID.json",
                    "meaningful_runtime_surface": True,
                    "behavior_block": {"BeforeUseHeroPowerBonus": {"values": []}},
                }
            ],
            "suppressed": [],
        },
        combo_plan={"combos": [], "suppressed": []},
        global_values_authority_matrix={
            "allowed_step1_overlays": [],
            "blocked_until_runtime_evidence": [],
        },
        config_readiness_report={
            "cards": {
                "SW_448": {
                    "name": "Darkbishop Benedictus",
                    "roles": ["start_of_game", "hero_power_transform"],
                    "runtime_surfaces": ["SW_448.json"],
                    "readiness_lane": "runtime_emitted",
                    "first_missing_link": "none",
                }
            }
        },
    )

    assert report["claim_rows"]["darkbishop_effect"]["lane"] == "runtime_lowered"
    assert report["claim_rows"]["darkbishop_effect"]["surfaces"]["cardid"]["allowed"] is True
    assert report["claim_rows"]["bad_keep"]["lane"] == "suppressed_with_reason"
    assert report["claim_rows"]["bad_keep"]["first_reason"] == (
        "start_of_game_effect_does_not_require_opening_hand"
    )
    assert report["card_rows"]["SW_448"]["claim_lanes"]["runtime_lowered"] == 1
    assert report["card_rows"]["SW_448"]["claim_lanes"]["suppressed_with_reason"] == 1


def test_source_contract_audit_markdown_is_compact_and_operator_readable():
    report = {
        "deck_name": "FixtureDeck",
        "summary": {
            "claims_total": 2,
            "runtime_lowered_claims": 1,
            "suppressed_claims": 1,
            "runtime_evidence_required_claims": 0,
            "report_only_claims": 0,
            "cards_total": 1,
            "cards_with_missing_links": 1,
        },
        "card_rows": {
            "CARD_001": {
                "name": "Fixture Card",
                "readiness_lane": "report_only_supported",
                "first_missing_link": "needs_runtime_surface",
                "runtime_surfaces": [],
                "claim_lanes": {"suppressed_with_reason": 1},
            }
        },
    }

    markdown = render_source_contract_audit_markdown(report)

    assert "# Source Contract Audit - FixtureDeck" in markdown
    assert "Runtime-lowered claims: 1" in markdown
    assert "| CARD_001 Fixture Card | report_only_supported | needs_runtime_surface |" in markdown

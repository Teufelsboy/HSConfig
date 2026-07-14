from __future__ import annotations

from hsconfig.source_contract_matrix import source_contract_policy_by_claim_kind
from hsconfig.source_claim_lifecycle import build_initial_lifecycle_rows
from hsconfig.source_contract_audit import (
    build_source_contract_audit,
    render_source_contract_audit_markdown,
)


REQUIRED_LIFECYCLE_FIELDS = {
    "claim_id",
    "claim_kind",
    "policy_lane",
    "surface_gate_decision",
    "surface_gate_reason",
    "builder_or_router_decision",
    "runtime_surface",
    "emitted_files",
    "suppressed_reason",
    "first_missing_link",
    "operator_impact",
}


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


def test_claim_lifecycle_rows_explain_static_policy_and_runtime_outcome():
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
                    "evidence_text_short": "Tune LowHpBoardValuePenalty after games.",
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
                {
                    "key": "LowHpBoardValuePenalty",
                    "claim_id": "numeric_claim",
                    "reason": "runtime_evidence_required",
                }
            ],
        },
        config_readiness_report={
            "cards": {
                "CARD_KEEP": {
                    "name": "Keep Card",
                    "roles": ["mulligan_anchor"],
                    "runtime_surfaces": ["Mulligan.json"],
                    "readiness_lane": "mulligan_only",
                    "first_missing_link": "none",
                },
                "CARD_NUM": {
                    "name": "Numeric Card",
                    "roles": [],
                    "runtime_surfaces": [],
                    "readiness_lane": "report_only_supported",
                    "first_missing_link": "runtime_evidence",
                },
            }
        },
    )
    policy_by_claim_kind = source_contract_policy_by_claim_kind()

    lifecycle_rows = report["claim_lifecycle_rows"]
    assert lifecycle_rows
    assert all(REQUIRED_LIFECYCLE_FIELDS <= set(row) for row in lifecycle_rows)
    assert all(row["operator_impact"] == "diagnostic_only" for row in lifecycle_rows)

    rows_by_claim_id = {row["claim_id"]: row for row in lifecycle_rows}
    assert rows_by_claim_id["keep_claim"] == {
        "claim_id": "keep_claim",
        "claim_kind": "mulligan_keep",
        "policy_lane": policy_by_claim_kind["mulligan_keep"]["lane"],
        "surface_gate_decision": "allowed",
        "surface_gate_reason": "allowed",
        "builder_or_router_decision": "emitted",
        "runtime_surface": "Mulligan.json",
        "emitted_files": ["Mulligan.json"],
        "suppressed_reason": None,
        "first_missing_link": None,
        "operator_impact": "diagnostic_only",
    }
    assert rows_by_claim_id["numeric_claim"] == {
        "claim_id": "numeric_claim",
        "claim_kind": "globalvalue_numeric_tuning",
        "policy_lane": policy_by_claim_kind["globalvalue_numeric_tuning"]["lane"],
        "surface_gate_decision": "rejected",
        "surface_gate_reason": "requires_runtime_evidence",
        "builder_or_router_decision": "suppressed",
        "runtime_surface": None,
        "emitted_files": [],
        "suppressed_reason": "runtime_evidence_required",
        "first_missing_link": "runtime_evidence",
        "operator_impact": "diagnostic_only",
    }


def test_claim_lifecycle_uses_canonical_quarantine_rows():
    claims = [
        {
            "claim_id": "keep_card",
            "claim_kind": "mulligan_keep",
            "source_confidence": "guide_backed",
            "cards": ["CARD_001"],
            "source_title": "Fixture Guide",
            "evidence_text_short": "Keep CARD_001.",
        },
        {
            "claim_id": "discard_card",
            "claim_kind": "mulligan_discard",
            "source_confidence": "guide_backed",
            "cards": ["CARD_001"],
            "source_title": "Fixture Guide",
            "evidence_text_short": "Discard CARD_001.",
        },
    ]
    lifecycle_rows = build_initial_lifecycle_rows(
        claims,
        conflict_report={
            "conflicts": [
                {
                    "claim_ids": ["keep_card", "discard_card"],
                    "reason": "contradictory_mulligan_keep_discard",
                }
            ]
        },
    )

    report = build_source_contract_audit(
        deck_name="FixtureDeck",
        deck_identity={
            "deck_name": "FixtureDeck",
            "cards": [{"card_id": "CARD_001", "name": "Conflict Card", "count": 1}],
        },
        guide_claim_bundle={"claims": claims},
        mulligan_plan={"rules": [], "suppressed_rules": []},
        card_behavior_plan={"rows": [], "suppressed": []},
        combo_plan={"combos": [], "suppressed": []},
        global_values_authority_matrix={
            "allowed_step1_overlays": [],
            "blocked_until_runtime_evidence": [],
        },
        config_readiness_report={
            "cards": {
                "CARD_001": {
                    "name": "Conflict Card",
                    "roles": ["mulligan_anchor"],
                    "runtime_surfaces": [],
                    "readiness_lane": "mulligan_only",
                    "first_missing_link": "source_claim_conflict",
                }
            }
        },
        initial_lifecycle_rows=lifecycle_rows,
    )

    rows_by_claim_id = {row["claim_id"]: row for row in report["claim_lifecycle_rows"]}
    row = rows_by_claim_id["discard_card"]

    assert REQUIRED_LIFECYCLE_FIELDS <= set(row)
    assert row["quarantine_status"] == "quarantined"
    assert row["quarantine_reason"] == "contradictory_mulligan_keep_discard"
    assert row["runtime_eligibility"] == "quarantined"
    assert row["builder_or_router_decision"] == "suppressed"
    assert row["suppressed_reason"] == "contradictory_mulligan_keep_discard"
    assert row["first_missing_link"] == "source_claim_conflict"
    assert row["final_runtime_effect"] == "suppressed_quarantined_claim"
    assert report["summary"]["claim_lifecycle_decision_counts"] == {"suppressed": 2}


def test_initial_source_ineligible_runtime_claim_is_not_seen_by_builder_with_source_reason():
    claims = [
        {
            "claim_id": "report_only_posture",
            "claim_kind": "gameplan_posture",
            "source_confidence": "report_only",
            "source_title": "Fixture Guide",
            "evidence_text_short": "Maintain an aggressive posture.",
        }
    ]
    initial_lifecycle_rows = build_initial_lifecycle_rows(claims)

    report = build_source_contract_audit(
        deck_name="FixtureDeck",
        deck_identity={"deck_name": "FixtureDeck", "cards": []},
        guide_claim_bundle={"claims": claims},
        mulligan_plan={"rules": [], "suppressed_rules": []},
        card_behavior_plan={"rows": [], "suppressed": []},
        combo_plan={"combos": [], "suppressed": []},
        global_values_authority_matrix={
            "allowed_step1_overlays": [],
            "blocked_until_runtime_evidence": [],
        },
        config_readiness_report={"cards": {}},
        initial_lifecycle_rows=initial_lifecycle_rows,
    )

    row = report["claim_lifecycle_rows"][0]

    assert initial_lifecycle_rows[0]["runtime_eligibility"] == "report_only"
    assert row["builder_or_router_decision"] == "not_seen_by_builder"
    assert row["suppressed_reason"] == "source_eligibility"
    assert row["first_missing_link"] == "source_eligibility"
    assert row["final_runtime_effect"] == "not_emitted_by_builder_or_router"


def test_initial_policy_report_only_claim_keeps_claim_kind_policy_reason():
    claims = [
        {
            "claim_id": "archetype_context",
            "claim_kind": "archetype",
            "source_confidence": "guide_backed",
            "source_title": "Fixture Guide",
            "evidence_text_short": "The deck is an archetype.",
        }
    ]

    report = build_source_contract_audit(
        deck_name="FixtureDeck",
        guide_claim_bundle={"claims": claims},
        initial_lifecycle_rows=build_initial_lifecycle_rows(claims),
    )

    row = report["claim_lifecycle_rows"][0]

    assert row["runtime_eligibility"] == "runtime_candidate"
    assert row["suppressed_reason"] == "claim_kind_policy"
    assert row["first_missing_link"] == "claim_kind_policy"


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


def test_source_contract_audit_adds_policy_lane_for_each_claim():
    report = build_source_contract_audit(
        deck_name="FixtureDeck",
        deck_identity={
            "deck_name": "FixtureDeck",
            "cards": [{"card_id": "CARD_001", "name": "Fixture", "count": 1}],
        },
        guide_claim_bundle={
            "claims": [
                {
                    "claim_id": "posture",
                    "claim_kind": "gameplan_posture",
                    "claim_readiness": "guide_backed",
                    "trust_ceiling": "runtime_candidate",
                    "cards": ["CARD_001"],
                    "source_title": "Fixture",
                    "evidence_text_short": "Push aggressive posture.",
                },
                {
                    "claim_id": "numeric",
                    "claim_kind": "globalvalue_numeric_tuning",
                    "claim_readiness": "guide_backed",
                    "trust_ceiling": "runtime_candidate",
                    "cards": ["CARD_001"],
                    "source_title": "Fixture",
                    "evidence_text_short": "Tune a numeric key after games.",
                },
            ]
        },
        global_values_authority_matrix={
            "allowed_step1_overlays": [
                {"key": "MyHeroPowerValue", "claim_refs": ["posture"]}
            ],
            "blocked_until_runtime_evidence": [
                {"key": "LowHpBoardValuePenalty", "claim_id": "numeric"}
            ],
        },
    )

    assert report["claim_rows"]["posture"]["policy_lane"] == "runtime_lowerable"
    assert report["claim_rows"]["numeric"]["policy_lane"] == "runtime_evidence_required"
    assert report["summary"]["claim_kind_policy_counts"]["runtime_lowerable"] == 1
    assert report["summary"]["claim_kind_policy_counts"]["runtime_evidence_required"] == 1


def test_source_contract_audit_marks_unknown_claim_kind_as_unsupported_or_unmapped():
    report = build_source_contract_audit(
        deck_name="FixtureDeck",
        guide_claim_bundle={
            "claims": [
                {
                    "claim_id": "unknown",
                    "claim_kind": "future_claim_kind",
                    "claim_readiness": "guide_backed",
                    "trust_ceiling": "runtime_candidate",
                    "source_title": "Fixture",
                    "evidence_text_short": "Future claim.",
                }
            ]
        },
    )

    assert report["claim_rows"]["unknown"]["policy_lane"] == "unsupported_or_unmapped"
    assert report["claim_rows"]["unknown"]["lane"] == "unsupported_or_unmapped"


def test_source_contract_audit_policy_matrix_failure_is_nonblocking(monkeypatch):
    def fail_policy_matrix():
        raise RuntimeError("stale source contract policy")

    monkeypatch.setattr(
        "hsconfig.source_contract_audit.source_contract_policy_by_claim_kind",
        fail_policy_matrix,
    )

    report = build_source_contract_audit(
        deck_name="FixtureDeck",
        guide_claim_bundle={
            "claims": [
                {
                    "claim_id": "posture",
                    "claim_kind": "gameplan_posture",
                    "claim_readiness": "guide_backed",
                    "trust_ceiling": "runtime_candidate",
                    "source_title": "Fixture",
                    "evidence_text_short": "Aggressive posture.",
                }
            ]
        },
    )

    assert report["claim_rows"]["posture"]["policy_lane"] == "unsupported_or_unmapped"
    assert report["summary"]["claim_kind_policy_counts"] == {
        "unsupported_or_unmapped": 1
    }


def test_claim_lifecycle_marks_allowed_claim_without_builder_emission_as_not_seen_by_builder():
    report = build_source_contract_audit(
        deck_name="FixtureDeck",
        deck_identity={"deck_name": "FixtureDeck", "cards": []},
        guide_claim_bundle={
            "claims": [
                {
                    "claim_id": "posture_claim",
                    "claim_kind": "gameplan_posture",
                    "claim_readiness": "guide_backed",
                    "trust_ceiling": "runtime_candidate",
                    "cards": [],
                    "source_title": "Fixture Guide",
                    "evidence_text_short": "Use a more aggressive posture.",
                }
            ]
        },
        mulligan_plan={"rules": [], "suppressed_rules": []},
        card_behavior_plan={"rows": [], "suppressed": []},
        combo_plan={"combos": [], "suppressed": []},
        global_values_authority_matrix={
            "allowed_step1_overlays": [],
            "blocked_until_runtime_evidence": [],
        },
        config_readiness_report={"cards": {}},
    )

    row = report["claim_lifecycle_rows"][0]

    assert row["claim_id"] == "posture_claim"
    assert row["claim_kind"] == "gameplan_posture"
    assert row["surface_gate_decision"] == "allowed"
    assert row["surface_gate_reason"] == "allowed"
    assert row["builder_or_router_decision"] == "not_seen_by_builder"
    assert row["suppressed_reason"] == "builder_or_router_missing"
    assert row["first_missing_link"] == "builder_or_router"
    assert row["operator_impact"] == "diagnostic_only"


def test_source_contract_audit_summarizes_claim_lifecycle_decisions():
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
                    "evidence_text_short": "Use a more aggressive posture.",
                },
                {
                    "claim_id": "numeric_claim",
                    "claim_kind": "globalvalue_numeric_tuning",
                    "claim_readiness": "guide_backed",
                    "trust_ceiling": "runtime_candidate",
                    "cards": [],
                    "source_title": "Fixture Guide",
                    "evidence_text_short": "Tune a numeric GlobalValues key only after games.",
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
                {
                    "key": "LowHpBoardValuePenalty",
                    "claim_id": "numeric_claim",
                    "reason": "runtime_evidence_required",
                }
            ],
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

    assert report["summary"]["claim_lifecycle_decision_counts"] == {
        "emitted": 1,
        "not_seen_by_builder": 1,
        "suppressed": 1,
    }

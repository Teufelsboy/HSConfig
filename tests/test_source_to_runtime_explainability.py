from __future__ import annotations

from hsconfig.source_to_runtime_explainability import (
    build_source_to_runtime_explainability_report,
)
from hsconfig.source_contract_audit import build_source_contract_audit


def _fixture_audit() -> dict:
    return {
        "schema_version": 1,
        "deck_name": "FixtureDeck",
        "summary": {
            "claims_total": 3,
            "runtime_lowered_claims": 1,
            "suppressed_claims": 1,
            "runtime_evidence_required_claims": 1,
            "cards_total": 2,
            "cards_with_missing_links": 1,
        },
        "claim_rows": {
            "keep_claim": {
                "claim_id": "keep_claim",
                "claim_kind": "mulligan_keep",
                "lane": "runtime_lowered",
                "policy_lane": "runtime_lowerable",
                "lowered_surfaces": ["mulligan"],
                "first_reason": "allowed",
                "cards": ["CARD_KEEP"],
            },
            "numeric_claim": {
                "claim_id": "numeric_claim",
                "claim_kind": "globalvalue_numeric_tuning",
                "lane": "runtime_evidence_required",
                "policy_lane": "runtime_evidence_required",
                "lowered_surfaces": [],
                "first_reason": "requires_runtime_evidence",
                "cards": ["CARD_NUM"],
            },
            "unknown_claim": {
                "claim_id": "unknown_claim",
                "claim_kind": "future_claim_kind",
                "lane": "unsupported_or_unmapped",
                "policy_lane": "unsupported_or_unmapped",
                "lowered_surfaces": [],
                "first_reason": "unsupported_or_unmapped",
                "cards": ["CARD_NUM"],
            },
        },
        "claim_lifecycle_rows": [
            {
                "claim_id": "keep_claim",
                "claim_kind": "mulligan_keep",
                "policy_lane": "runtime_lowerable",
                "surface_gate_decision": "allowed",
                "surface_gate_reason": "allowed",
                "builder_or_router_decision": "emitted",
                "runtime_surface": "Mulligan.json",
                "emitted_files": ["Mulligan.json"],
                "suppressed_reason": None,
                "first_missing_link": None,
                "operator_impact": "diagnostic_only",
            },
            {
                "claim_id": "numeric_claim",
                "claim_kind": "globalvalue_numeric_tuning",
                "policy_lane": "runtime_evidence_required",
                "surface_gate_decision": "rejected",
                "surface_gate_reason": "requires_runtime_evidence",
                "builder_or_router_decision": "suppressed",
                "runtime_surface": None,
                "emitted_files": [],
                "suppressed_reason": "runtime_evidence_required",
                "first_missing_link": "runtime_evidence",
                "operator_impact": "diagnostic_only",
            },
            {
                "claim_id": "unknown_claim",
                "claim_kind": "future_claim_kind",
                "policy_lane": "unsupported_or_unmapped",
                "surface_gate_decision": "rejected",
                "surface_gate_reason": "unsupported_or_unmapped",
                "builder_or_router_decision": "suppressed",
                "runtime_surface": None,
                "emitted_files": [],
                "suppressed_reason": "unsupported_or_unmapped",
                "first_missing_link": "claim_kind_policy",
                "operator_impact": "diagnostic_only",
            },
        ],
        "card_rows": {
            "CARD_KEEP": {
                "name": "Keep Card",
                "readiness_lane": "mulligan_only",
                "first_missing_link": "none",
                "runtime_surfaces": ["Mulligan.json"],
                "claim_lanes": {"runtime_lowered": 1},
            },
            "CARD_NUM": {
                "name": "Numeric Card",
                "readiness_lane": "report_only_supported",
                "first_missing_link": "runtime_evidence",
                "runtime_surfaces": [],
                "claim_lanes": {
                    "runtime_evidence_required": 1,
                    "unsupported_or_unmapped": 1,
                },
            },
        },
    }


def test_explainability_report_summarizes_claim_chain_without_apply_authority():
    report = build_source_to_runtime_explainability_report(_fixture_audit())

    assert report["schema_version"] == 1
    assert report["authority"] == "diagnostic_only"
    assert report["operator_gate_impact"] == "diagnostic_only"
    assert report["apply_blocking"] is False
    assert report["summary"] == {
        "cards_total": 2,
        "claims_total": 3,
        "runtime_lowered_claims": 1,
        "claims_with_first_missing_link": 2,
        "cards_with_first_missing_link": 1,
        "apply_blocking": False,
        "next_report_to_open": "reports/source_to_runtime_explainability.json",
    }


def test_explainability_claim_rows_show_first_missing_link_and_runtime_files():
    report = build_source_to_runtime_explainability_report(_fixture_audit())
    rows = {row["claim_id"]: row for row in report["claim_rows"]}

    assert rows["keep_claim"] == {
        "claim_id": "keep_claim",
        "claim_kind": "mulligan_keep",
        "policy_lane": "runtime_lowerable",
        "surface_gate_decision": "allowed",
        "surface_gate_reason": "allowed",
        "builder_or_router_decision": "emitted",
        "emitted_runtime_files": ["Mulligan.json"],
        "not_emitted_runtime_files": [],
        "first_missing_link": None,
        "why_not_emitted": None,
        "apply_blocked": False,
        "next_source_action": "none",
    }
    assert rows["numeric_claim"]["first_missing_link"] == "runtime_evidence"
    assert rows["numeric_claim"]["why_not_emitted"] == "runtime_evidence_required"
    assert rows["numeric_claim"]["next_source_action"] == "collect_runtime_evidence"
    assert rows["unknown_claim"]["first_missing_link"] == "claim_kind_policy"
    assert rows["unknown_claim"]["next_source_action"] == (
        "map_claim_kind_or_keep_report_only"
    )


def test_explainability_card_rows_pick_strongest_claim_and_next_action():
    report = build_source_to_runtime_explainability_report(_fixture_audit())
    rows = {row["card_id"]: row for row in report["card_rows"]}

    assert rows["CARD_KEEP"] == {
        "card_id": "CARD_KEEP",
        "name": "Keep Card",
        "best_source_lane": "runtime_lowered",
        "source_lane": "runtime_lowered",
        "strongest_claim_id": "keep_claim",
        "strongest_claim_kind": "mulligan_keep",
        "first_missing_link": None,
        "emitted_runtime_files": ["Mulligan.json"],
        "not_emitted_runtime_files": [],
        "why_not_emitted": None,
        "apply_blocked": False,
        "next_source_action": "none",
        "first_missing_source_action": "none",
        "runtime_lowering_status": "source_backed_runtime",
        "closure_lane": "source_backed_runtime_lowered",
        "strong_ready": True,
        "default_only_blocker": False,
        "closure": {
            "lane": "runtime_backed",
            "claim_kinds": ["mulligan_keep"],
            "source_lanes": ["runtime_lowered"],
            "runtime_surfaces": ["Mulligan.json"],
            "expected_runtime_surfaces": ["Mulligan.json"],
            "missing_runtime_surfaces": [],
            "default_only_risk": False,
            "suppressed_reasons": [],
            "first_missing_link": None,
            "next_source_action": "none",
        },
        "evidence_chain": [
            {
                "claim_id": "keep_claim",
                "claim_kind": "mulligan_keep",
                "source_lane": "runtime_lowered",
                "source_type": "",
                "runtime_surface": "mulligan",
                "runtime_files": ["Mulligan.json"],
                "resolution_reason": "emitted",
                "first_missing_link": None,
                "first_missing_source_action": "none",
            }
        ],
    }
    assert rows["CARD_NUM"]["best_source_lane"] == "runtime_evidence_required"
    assert rows["CARD_NUM"]["first_missing_link"] == "runtime_evidence"
    assert rows["CARD_NUM"]["why_not_emitted"] == "runtime_evidence_required"
    assert rows["CARD_NUM"]["apply_blocked"] is False
    assert rows["CARD_NUM"]["next_source_action"] == "collect_runtime_evidence"
    assert rows["CARD_NUM"]["closure"] == {
        "lane": "source_action_needed",
        "claim_kinds": ["future_claim_kind", "globalvalue_numeric_tuning"],
        "source_lanes": ["runtime_evidence_required", "unsupported_or_unmapped"],
        "runtime_surfaces": [],
        "expected_runtime_surfaces": ["GlobalValues.json"],
        "missing_runtime_surfaces": ["GlobalValues.json"],
        "default_only_risk": False,
        "suppressed_reasons": [
            "runtime_evidence_required",
            "unsupported_or_unmapped",
        ],
        "first_missing_link": "runtime_evidence",
        "next_source_action": "collect_runtime_evidence",
    }


def test_explainability_card_rows_include_evidence_chain_for_runtime_and_gaps():
    report = build_source_to_runtime_explainability_report(_fixture_audit())
    rows = {row["card_id"]: row for row in report["card_rows"]}

    assert rows["CARD_KEEP"]["evidence_chain"] == [
        {
            "claim_id": "keep_claim",
            "claim_kind": "mulligan_keep",
            "source_lane": "runtime_lowered",
            "source_type": "",
            "runtime_surface": "mulligan",
            "runtime_files": ["Mulligan.json"],
            "resolution_reason": "emitted",
            "first_missing_link": None,
            "first_missing_source_action": "none",
        }
    ]
    numeric_chain = {
        row["claim_id"]: row for row in rows["CARD_NUM"]["evidence_chain"]
    }
    assert numeric_chain["numeric_claim"] == {
        "claim_id": "numeric_claim",
        "claim_kind": "globalvalue_numeric_tuning",
        "source_lane": "runtime_evidence_required",
        "source_type": "",
        "runtime_surface": "globalvalues",
        "runtime_files": ["GlobalValues.json"],
        "resolution_reason": "runtime_evidence_required",
        "first_missing_link": "runtime_evidence",
        "first_missing_source_action": "collect_runtime_evidence",
    }
    assert numeric_chain["unknown_claim"]["resolution_reason"] == "unsupported_or_unmapped"
    assert numeric_chain["unknown_claim"]["first_missing_source_action"] == (
        "map_claim_kind_or_keep_report_only"
    )


def test_explainability_operator_attention_rows_prioritize_missing_links():
    report = build_source_to_runtime_explainability_report(_fixture_audit())

    assert report["operator_attention"] == [
        {
            "card_id": "CARD_NUM",
            "name": "Numeric Card",
            "status": "source_action_needed",
            "closure_lane": "source_action_needed",
            "default_only_risk": False,
            "first_missing_link": "runtime_evidence",
            "next_source_action": "collect_runtime_evidence",
            "source_lane": "runtime_evidence_required",
            "first_missing_source_action": "collect_runtime_evidence",
            "runtime_lowering_status": "source_backed_contract_only",
            "strongest_claim_id": "numeric_claim",
            "strongest_claim_kind": "globalvalue_numeric_tuning",
            "emitted_runtime_files": [],
            "not_emitted_runtime_files": ["GlobalValues.json"],
        },
        {
            "card_id": "CARD_KEEP",
            "name": "Keep Card",
            "status": "runtime_backed",
            "closure_lane": "runtime_backed",
            "default_only_risk": False,
            "first_missing_link": None,
            "next_source_action": "none",
            "source_lane": "runtime_lowered",
            "first_missing_source_action": "none",
            "runtime_lowering_status": "source_backed_runtime",
            "strongest_claim_id": "keep_claim",
            "strongest_claim_kind": "mulligan_keep",
            "emitted_runtime_files": ["Mulligan.json"],
            "not_emitted_runtime_files": [],
        },
    ]


def test_explainability_operator_attention_marks_no_missing_link_without_runtime_files():
    audit = {
        "schema_version": 1,
        "deck_name": "FixtureDeck",
        "claim_rows": {
            "report_claim": {
                "claim_id": "report_claim",
                "claim_kind": "source_note",
                "lane": "report_only",
                "policy_lane": "report_only",
                "lowered_surfaces": [],
                "first_reason": "report_only",
                "cards": ["CARD_NOTE"],
            }
        },
        "claim_lifecycle_rows": [
            {
                "claim_id": "report_claim",
                "claim_kind": "source_note",
                "policy_lane": "report_only",
                "surface_gate_decision": "suppressed",
                "surface_gate_reason": "report_only",
                "builder_or_router_decision": "suppressed",
                "runtime_surface": None,
                "emitted_files": [],
                "suppressed_reason": None,
                "first_missing_link": None,
                "operator_impact": "diagnostic_only",
            }
        ],
        "card_rows": {
            "CARD_NOTE": {
                "name": "Report Only Card",
                "readiness_lane": "report_only_supported",
                "first_missing_link": "none",
                "runtime_surfaces": [],
                "claim_lanes": {"report_only": 1},
            }
        },
    }

    report = build_source_to_runtime_explainability_report(audit)

    assert report["operator_attention"] == [
        {
            "card_id": "CARD_NOTE",
            "name": "Report Only Card",
            "status": "diagnostic_only",
            "closure_lane": "diagnostic_only",
            "default_only_risk": False,
            "first_missing_link": None,
            "next_source_action": "none",
            "source_lane": "report_only",
            "first_missing_source_action": "none",
            "runtime_lowering_status": "source_backed_contract_only",
            "strongest_claim_id": "report_claim",
            "strongest_claim_kind": "source_note",
            "emitted_runtime_files": [],
            "not_emitted_runtime_files": [],
        }
    ]


def test_explainability_operator_attention_exposes_baseline_default_only_risk():
    audit = {
        "schema_version": 1,
        "deck_name": "FixtureDeck",
        "claim_rows": {},
        "claim_lifecycle_rows": [],
        "card_rows": {
            "CARD_BASE": {
                "name": "Baseline Card",
                "readiness_lane": "generic_low_confidence",
                "first_missing_link": "none",
                "runtime_surfaces": [],
                "claim_lanes": {},
            }
        },
    }

    report = build_source_to_runtime_explainability_report(audit)

    assert report["apply_blocking"] is False
    assert report["operator_attention"] == [
        {
            "card_id": "CARD_BASE",
            "name": "Baseline Card",
            "status": "baseline_only_visible",
            "closure_lane": "baseline_only_visible",
            "default_only_risk": True,
            "first_missing_link": None,
            "next_source_action": "none",
            "source_lane": "report_only",
            "first_missing_source_action": "none",
            "runtime_lowering_status": "missing_source_claim",
            "strongest_claim_id": None,
            "strongest_claim_kind": None,
            "emitted_runtime_files": [],
            "not_emitted_runtime_files": [],
        }
    ]


def test_explainability_closure_separates_surface_intent_from_unassigned_risk():
    audit = {
        "schema_version": 1,
        "deck_name": "FixtureDeck",
        "claim_rows": {
            "suppressed_keep": {
                "claim_id": "suppressed_keep",
                "claim_kind": "mulligan_keep",
                "lane": "suppressed_with_reason",
                "policy_lane": "runtime_lowerable",
                "lowered_surfaces": [],
                "first_reason": "start_of_game_effect_does_not_require_opening_hand",
                "cards": ["CARD_SUPPRESSED"],
            }
        },
        "claim_lifecycle_rows": [
            {
                "claim_id": "suppressed_keep",
                "claim_kind": "mulligan_keep",
                "policy_lane": "runtime_lowerable",
                "surface_gate_decision": "rejected",
                "surface_gate_reason": "start_of_game_effect_does_not_require_opening_hand",
                "builder_or_router_decision": "suppressed",
                "runtime_surface": "Mulligan.json",
                "emitted_files": [],
                "suppressed_reason": "start_of_game_effect_does_not_require_opening_hand",
                "first_missing_link": "opening_hand_mulligan_intent",
                "operator_impact": "diagnostic_only",
            }
        ],
        "card_rows": {
            "CARD_BASE": {
                "name": "Unassigned Baseline Card",
                "readiness_lane": "generic_low_confidence",
                "first_missing_link": "none",
                "runtime_surfaces": [],
                "claim_lanes": {},
            },
            "CARD_SUPPRESSED": {
                "name": "Suppressed Mulligan Card",
                "readiness_lane": "mulligan_only",
                "first_missing_link": "opening_hand_mulligan_intent",
                "runtime_surfaces": [],
                "claim_lanes": {"suppressed_with_reason": 1},
            },
        },
    }

    report = build_source_to_runtime_explainability_report(audit)
    rows = {row["card_id"]: row for row in report["card_rows"]}

    assert rows["CARD_BASE"]["closure"]["default_only_risk"] is True
    assert rows["CARD_BASE"]["closure"]["runtime_surfaces"] == []
    assert rows["CARD_BASE"]["closure"]["expected_runtime_surfaces"] == []
    assert rows["CARD_BASE"]["closure"]["missing_runtime_surfaces"] == []
    assert rows["CARD_SUPPRESSED"]["closure"]["default_only_risk"] is False
    assert rows["CARD_SUPPRESSED"]["closure"]["runtime_surfaces"] == []
    assert rows["CARD_SUPPRESSED"]["closure"]["expected_runtime_surfaces"] == [
        "Mulligan.json"
    ]
    assert rows["CARD_SUPPRESSED"]["closure"]["missing_runtime_surfaces"] == [
        "Mulligan.json"
    ]


def test_explainability_card_rows_aggregate_runtime_files_across_claims():
    audit = _fixture_audit()
    audit["claim_rows"]["behavior_claim"] = {
        "claim_id": "behavior_claim",
        "claim_kind": "targeting_rule",
        "lane": "runtime_lowered",
        "policy_lane": "runtime_lowerable",
        "lowered_surfaces": ["cardid"],
        "first_reason": "allowed",
        "cards": ["CARD_KEEP"],
    }
    audit["claim_lifecycle_rows"].append(
        {
            "claim_id": "behavior_claim",
            "claim_kind": "targeting_rule",
            "policy_lane": "runtime_lowerable",
            "surface_gate_decision": "allowed",
            "surface_gate_reason": "allowed",
            "builder_or_router_decision": "emitted",
            "runtime_surface": "CARD_KEEP.json",
            "emitted_files": ["CARD_KEEP.json"],
            "suppressed_reason": None,
            "first_missing_link": None,
            "operator_impact": "diagnostic_only",
        }
    )
    audit["card_rows"]["CARD_KEEP"]["claim_lanes"]["runtime_lowered"] = 2

    report = build_source_to_runtime_explainability_report(audit)
    rows = {row["card_id"]: row for row in report["card_rows"]}

    assert rows["CARD_KEEP"]["strongest_claim_id"] == "behavior_claim"
    assert rows["CARD_KEEP"]["emitted_runtime_files"] == [
        "CARD_KEEP.json",
        "Mulligan.json",
    ]
    assert rows["CARD_KEEP"]["not_emitted_runtime_files"] == []


def test_explainability_card_rows_surface_missing_related_claims():
    audit = _fixture_audit()
    audit["claim_rows"]["blocked_related_claim"] = {
        "claim_id": "blocked_related_claim",
        "claim_kind": "future_claim_kind",
        "lane": "unsupported_or_unmapped",
        "policy_lane": "unsupported_or_unmapped",
        "lowered_surfaces": [],
        "first_reason": "unsupported_or_unmapped",
        "cards": ["CARD_KEEP"],
    }
    audit["claim_lifecycle_rows"].append(
        {
            "claim_id": "blocked_related_claim",
            "claim_kind": "future_claim_kind",
            "policy_lane": "unsupported_or_unmapped",
            "surface_gate_decision": "rejected",
            "surface_gate_reason": "unsupported_or_unmapped",
            "builder_or_router_decision": "suppressed",
            "runtime_surface": None,
            "emitted_files": [],
            "suppressed_reason": "unsupported_or_unmapped",
            "first_missing_link": "claim_kind_policy",
            "operator_impact": "diagnostic_only",
        }
    )

    report = build_source_to_runtime_explainability_report(audit)
    rows = {row["card_id"]: row for row in report["card_rows"]}

    assert report["summary"]["cards_with_first_missing_link"] == 2
    assert rows["CARD_KEEP"]["strongest_claim_id"] == "keep_claim"
    assert rows["CARD_KEEP"]["first_missing_link"] == "claim_kind_policy"
    assert rows["CARD_KEEP"]["why_not_emitted"] == "unsupported_or_unmapped"
    assert rows["CARD_KEEP"]["next_source_action"] == (
        "map_claim_kind_or_keep_report_only"
    )


def test_explainability_uses_canonical_action_for_readiness_missing_links():
    audit = {
        "schema_version": 1,
        "deck_name": "FixtureDeck",
        "claim_rows": {},
        "claim_lifecycle_rows": [],
        "card_rows": {
            "CARD_MULL": {
                "name": "Mulligan Gap Card",
                "readiness_lane": "report_only_supported",
                "first_missing_link": "needs_mulligan_claim",
                "runtime_surfaces": [],
                "claim_lanes": {},
            }
        },
    }

    report = build_source_to_runtime_explainability_report(audit)
    rows = {row["card_id"]: row for row in report["card_rows"]}

    assert rows["CARD_MULL"]["first_missing_link"] == "needs_mulligan_claim"
    assert rows["CARD_MULL"]["next_source_action"] == (
        "add_mulligan_keep_or_discard_claim"
    )


def test_explainability_card_rows_include_compact_closure_lane():
    audit = _fixture_audit()
    audit["claim_rows"]["suppressed_start_effect"] = {
        "claim_id": "suppressed_start_effect",
        "claim_kind": "mulligan_keep",
        "lane": "suppressed_with_reason",
        "policy_lane": "runtime_lowerable",
        "lowered_surfaces": [],
        "first_reason": "start_of_game_effect_does_not_require_opening_hand",
        "cards": ["CARD_KEEP"],
    }
    audit["claim_lifecycle_rows"].append(
        {
            "claim_id": "suppressed_start_effect",
            "claim_kind": "mulligan_keep",
            "policy_lane": "runtime_lowerable",
            "surface_gate_decision": "rejected",
            "surface_gate_reason": "start_of_game_effect_does_not_require_opening_hand",
            "builder_or_router_decision": "suppressed",
            "runtime_surface": "Mulligan.json",
            "emitted_files": [],
            "suppressed_reason": "start_of_game_effect_does_not_require_opening_hand",
            "first_missing_link": "opening_hand_mulligan_intent",
            "operator_impact": "diagnostic_only",
        }
    )

    report = build_source_to_runtime_explainability_report(audit)
    rows = {row["card_id"]: row for row in report["card_rows"]}

    assert rows["CARD_KEEP"]["closure"] == {
        "lane": "source_action_needed",
        "claim_kinds": ["mulligan_keep"],
        "source_lanes": ["runtime_lowered", "suppressed_with_reason"],
        "runtime_surfaces": ["Mulligan.json"],
        "expected_runtime_surfaces": ["Mulligan.json"],
        "missing_runtime_surfaces": [],
        "default_only_risk": False,
        "suppressed_reasons": [
            "start_of_game_effect_does_not_require_opening_hand"
        ],
        "first_missing_link": "opening_hand_mulligan_intent",
        "next_source_action": "add_explicit_opening_hand_mulligan_source",
    }


def test_explainability_points_to_first_missing_source_action_for_partial_deck():
    report = build_source_to_runtime_explainability_report(
        audit={
            "claim_rows": [
                {
                    "card_id": "PIRATE_DH_CARD",
                    "claim_kind": "mulligan_keep",
                    "source_type": "policy_backed_autonomous_mulligan",
                    "source_lane": "policy_fallback",
                    "runtime_backed": True,
                }
            ]
        },
        runtime_files={"Mulligan.json"},
    )

    row = report["card_rows"][0]
    assert row["source_lane"] == "policy_fallback"
    assert row["first_missing_source_action"] == "add_explicit_mulligan_source"
    assert row["runtime_lowering_status"] == "policy_backed_runtime"


def test_explainability_exposes_policy_backed_runtime_as_non_strong():
    report = build_source_to_runtime_explainability_report(
        audit={
            "claim_rows": [
                {
                    "card_id": "CARD_001",
                    "claim_kind": "mulligan_keep",
                    "source_type": "policy_backed_autonomous_mulligan",
                    "source_lane": "policy_fallback",
                    "runtime_backed": True,
                }
            ]
        },
        runtime_files={"Mulligan.json"},
    )

    row = report["card_rows"][0]
    assert row["source_lane"] == "policy_fallback"
    assert row["runtime_lowering_status"] == "policy_backed_runtime"
    assert row["first_missing_source_action"] == "add_explicit_mulligan_source"
    assert row["closure_lane"] == "policy_backed"
    assert row["strong_ready"] is False
    assert row["default_only_blocker"] is False


def test_explainability_exposes_default_only_blocker_on_card_row():
    report = build_source_to_runtime_explainability_report(
        audit={
            "claim_rows": [
                {
                    "card_id": "CARD_DEFAULT",
                    "claim_kind": "mulligan_keep",
                    "source_lane": "runtime_lowered",
                    "first_missing_link": "default_only_runtime_surface",
                    "runtime_backed": False,
                }
            ]
        },
        runtime_files=set(),
    )

    row = report["card_rows"][0]
    assert row["closure_lane"] == "explicit_gap"
    assert row["strong_ready"] is False
    assert row["default_only_blocker"] is True


def test_explainability_does_not_treat_policy_fallback_non_mulligan_as_mulligan():
    report = build_source_to_runtime_explainability_report(
        audit={
            "claim_rows": [
                {
                    "card_id": "POLICY_ROLE",
                    "claim_kind": "card_role",
                    "source_type": "policy_backed_autonomous_mulligan",
                    "runtime_backed": True,
                }
            ]
        },
        runtime_files={"CardRole.json"},
    )

    row = report["card_rows"][0]
    assert row["first_missing_source_action"] == "none"
    assert row["runtime_lowering_status"] == "source_backed_runtime"


def test_explainability_preserves_policy_fallback_from_legacy_audit_report():
    audit_report = build_source_contract_audit(
        deck_name="FixtureDeck",
        deck_identity={
            "deck_name": "FixtureDeck",
            "cards": [
                {
                    "card_id": "POLICY_KEEP",
                    "name": "Policy Keep",
                    "count": 1,
                }
            ],
        },
        guide_claim_bundle={
            "claims": [
                {
                    "claim_id": "policy_keep_claim",
                    "claim_kind": "mulligan_keep",
                    "claim_readiness": "guide_backed",
                    "trust_ceiling": "runtime_candidate",
                    "cards": ["POLICY_KEEP"],
                    "source_type": "policy_backed_autonomous_mulligan",
                    "source_lane": "policy_fallback",
                }
            ]
        },
        mulligan_plan={
            "rules": [
                {
                    "card": "POLICY_KEEP",
                    "action": "hold",
                    "source_claim_ids": ["policy_keep_claim"],
                }
            ],
            "suppressed_rules": [],
        },
        config_readiness_report={
            "cards": {
                "POLICY_KEEP": {
                    "name": "Policy Keep",
                    "runtime_surfaces": ["Mulligan.json"],
                    "readiness_lane": "mulligan_only",
                    "first_missing_link": "none",
                }
            }
        },
        runtime_emission_index={
            "policy_keep_claim": {
                "decision": "emitted",
                "runtime_surface": "Mulligan.json",
                "emitted_files": ["Mulligan.json"],
            }
        },
    )

    report = build_source_to_runtime_explainability_report(audit_report)

    row = report["card_rows"][0]
    assert row["source_lane"] == "policy_fallback"
    assert row["first_missing_source_action"] == "add_explicit_mulligan_source"
    assert row["runtime_lowering_status"] == "policy_backed_runtime"

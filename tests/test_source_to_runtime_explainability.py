from __future__ import annotations

import pytest

from hsconfig.config_readiness import build_config_readiness_report
from hsconfig.runtime_surface_ledger import build_runtime_surface_ledger
from hsconfig.source_contract_audit import build_source_contract_audit
from hsconfig.source_to_runtime_explainability import (
    build_source_to_runtime_explainability_report,
)
from hsconfig.source_to_runtime_explainability import _card_expected_runtime_files


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


def test_explainability_prefers_hero_power_transform_over_generic_mechanic_usage():
    audit = {
        "schema_version": 1,
        "deck_name": "FixtureDeck",
        "claim_rows": {
            "claim_000_mechanic": {
                "claim_id": "claim_000_mechanic",
                "claim_kind": "mechanic_usage",
                "lane": "runtime_lowered",
                "policy_lane": "runtime_lowerable",
                "cards": ["SW_448"],
            },
            "claim_999_hero_power": {
                "claim_id": "claim_999_hero_power",
                "claim_kind": "hero_power_transform",
                "lane": "runtime_lowered",
                "policy_lane": "runtime_lowerable",
                "cards": ["SW_448"],
            },
        },
        "claim_lifecycle_rows": [
            {
                "claim_id": "claim_000_mechanic",
                "claim_kind": "mechanic_usage",
                "policy_lane": "runtime_lowerable",
                "surface_gate_decision": "allowed",
                "surface_gate_reason": "allowed",
                "builder_or_router_decision": "emitted",
                "runtime_surface": "SW_448.json",
                "emitted_files": ["SW_448.json"],
                "suppressed_reason": None,
                "first_missing_link": None,
                "operator_impact": "diagnostic_only",
            },
            {
                "claim_id": "claim_999_hero_power",
                "claim_kind": "hero_power_transform",
                "policy_lane": "runtime_lowerable",
                "surface_gate_decision": "allowed",
                "surface_gate_reason": "allowed",
                "builder_or_router_decision": "emitted",
                "runtime_surface": "SW_448.json",
                "emitted_files": ["SW_448.json"],
                "suppressed_reason": None,
                "first_missing_link": None,
                "operator_impact": "diagnostic_only",
            },
        ],
        "card_rows": {
            "SW_448": {
                "name": "Darkbishop Benedictus",
                "readiness_lane": "runtime_emitted",
                "first_missing_link": "none",
                "runtime_surfaces": ["SW_448.json"],
                "claim_lanes": {"runtime_lowered": 2},
            }
        },
    }

    report = build_source_to_runtime_explainability_report(audit)
    row = report["card_rows"][0]

    assert row["strongest_claim_id"] == "claim_999_hero_power"
    assert row["strongest_claim_kind"] == "hero_power_transform"
    assert {claim["claim_kind"] for claim in row["evidence_chain"]} == {
        "hero_power_transform",
        "mechanic_usage",
    }


def test_explainability_uses_empty_ledger_not_plan_emission_for_closure_and_attention():
    report = build_source_to_runtime_explainability_report(
        _fixture_audit(),
        runtime_surface_ledger={
            "cards": {
                "CARD_KEEP": {"runtime_surfaces": []},
                "CARD_NUM": {"runtime_surfaces": []},
            },
            "linked_runtime_entities": {},
            "surface_ledger_sha256": "d" * 64,
        },
    )
    row = next(row for row in report["card_rows"] if row["card_id"] == "CARD_KEEP")
    attention = next(row for row in report["operator_attention"] if row["card_id"] == "CARD_KEEP")

    assert row["emitted_runtime_files"] == []
    assert row["not_emitted_runtime_files"] == ["Mulligan.json"]
    assert row["runtime_lowering_status"] == "source_backed_contract_only"
    assert row["closure"]["runtime_surfaces"] == []
    assert row["evidence_chain"][0]["runtime_files"] == ["Mulligan.json"]
    assert attention["status"] == "source_action_needed"
    keep_claim = next(row for row in report["claim_rows"] if row["claim_id"] == "keep_claim")
    assert keep_claim["emitted_runtime_files"] == []
    assert keep_claim["builder_or_router_decision"] != "emitted"
    assert report["summary"]["runtime_lowered_claims"] == 0


def test_explainability_preserves_strong_claim_when_ledger_has_matching_mulligan_surface():
    report = build_source_to_runtime_explainability_report(
        _fixture_audit(),
        runtime_surface_ledger={
            "cards": {"CARD_KEEP": {"runtime_surfaces": ["Mulligan.json"]}},
            "linked_runtime_entities": {},
            "surface_ledger_sha256": "e" * 64,
        },
    )
    card = next(row for row in report["card_rows"] if row["card_id"] == "CARD_KEEP")
    claim = next(row for row in report["claim_rows"] if row["claim_id"] == "keep_claim")

    assert claim["emitted_runtime_files"] == ["Mulligan.json"]
    assert card["strong_ready"] is True
    assert card["closure_lane"] == "source_backed_runtime_lowered"
    assert report["summary"]["runtime_lowered_claims"] == 1


def test_explainability_emits_discard_claim_only_for_matching_discard_selector():
    audit = _fixture_audit()
    audit["claim_rows"]["keep_claim"].update(
        {"claim_kind": "mulligan_discard", "selector": "CARD_KEEP"}
    )
    audit["claim_lifecycle_rows"][0]["claim_kind"] = "mulligan_discard"
    ledger = build_runtime_surface_ledger(
        deck_identity={"deck_name": "Discard", "cards": [{"card_id": "CARD_KEEP", "count": 1}]},
        compiled_mulligan={
            "Mulligan": {"values": [{"mulligan": "CARD_KEEP", "value": "discard"}]}
        },
        compiled_globalvalues={},
        compiled_combo=None,
        compiled_cardid_files={},
        linked_runtime_owners=[],
    )

    report = build_source_to_runtime_explainability_report(
        audit, runtime_surface_ledger=ledger
    )
    claim = next(row for row in report["claim_rows"] if row["claim_id"] == "keep_claim")
    card = next(row for row in report["card_rows"] if row["card_id"] == "CARD_KEEP")

    assert ledger["cards"]["CARD_KEEP"]["runtime_surfaces"] == ["Mulligan.json"]
    assert claim["emitted_runtime_files"] == ["Mulligan.json"]
    assert card["emitted_runtime_files"] == ["Mulligan.json"]
    assert report["summary"]["runtime_lowered_claims"] == 1


def test_explainability_does_not_match_keep_claim_to_discard_surface():
    audit = _fixture_audit()
    audit["claim_rows"]["keep_claim"]["selector"] = "CARD_KEEP"
    ledger = build_runtime_surface_ledger(
        deck_identity={"deck_name": "Discard", "cards": [{"card_id": "CARD_KEEP", "count": 1}]},
        compiled_mulligan={
            "Mulligan": {"values": [{"mulligan": "CARD_KEEP", "value": "discard"}]}
        },
        compiled_globalvalues={},
        compiled_combo=None,
        compiled_cardid_files={},
        linked_runtime_owners=[],
    )

    report = build_source_to_runtime_explainability_report(
        audit, runtime_surface_ledger=ledger
    )
    claim = next(row for row in report["claim_rows"] if row["claim_id"] == "keep_claim")

    assert claim["emitted_runtime_files"] == []


def test_explainability_requires_exact_combo_operator_and_order():
    audit = _fixture_audit()
    audit["claim_rows"]["keep_claim"].update(
        {
            "claim_kind": "combo_sequence",
            "cards": ["CARD_KEEP", "CARD_NUM"],
            "operator": ">>",
        }
    )
    audit["claim_lifecycle_rows"][0].update(
        {
            "claim_kind": "combo_sequence",
            "runtime_surface": "Combo.json",
            "emitted_files": ["Combo.json"],
        }
    )
    ledger = {
        "cards": {
            "CARD_KEEP": {"runtime_surfaces": ["Combo.json"]},
            "CARD_NUM": {"runtime_surfaces": ["Combo.json"]},
        },
        "combo": {"row_count": 1, "rows": ["CARD_KEEP>->CARD_NUM"]},
        "linked_runtime_entities": {},
    }

    report = build_source_to_runtime_explainability_report(
        audit, runtime_surface_ledger=ledger
    )
    claim = next(row for row in report["claim_rows"] if row["claim_id"] == "keep_claim")

    assert claim["emitted_runtime_files"] == []


def test_explainability_keeps_darkbishop_as_source_and_mind_spike_as_runtime_owner():
    audit = {
        "schema_version": 1,
        "deck_name": "ShadowPriest",
        "claim_rows": {
            "claim_darkbishop": {
                "claim_id": "claim_darkbishop",
                "claim_kind": "hero_power_transform",
                "lane": "runtime_lowered",
                "policy_lane": "runtime_lowerable",
                "cards": ["SW_448"],
            }
        },
        "claim_lifecycle_rows": [
            {
                "claim_id": "claim_darkbishop",
                "claim_kind": "hero_power_transform",
                "policy_lane": "runtime_lowerable",
                "surface_gate_decision": "allowed",
                "surface_gate_reason": "allowed",
                "builder_or_router_decision": "emitted",
                "runtime_surface": "SW_448.json",
                "emitted_files": ["SW_448.json"],
                "suppressed_reason": None,
                "first_missing_link": None,
                "operator_impact": "diagnostic_only",
            }
        ],
        "card_rows": {
            "SW_448": {
                "name": "Darkbishop Benedictus",
                "readiness_lane": "globalvalues_only",
                "first_missing_link": "none",
                "runtime_surfaces": ["GlobalValues.json", "SW_448.json"],
                "claim_lanes": {"runtime_lowered": 1},
            }
        },
    }
    card_behavior_plan = {
        "rows": [
            {
                "claim_id": "claim_darkbishop",
                "claim_kind": "hero_power_transform",
                "card_id": "SW_448",
                "source_card_id": "SW_448",
                "runtime_card_id": "EX1_625t",
                "link_kind": "hero_power_transform",
                "behavior_block": "BeforeUseHeroPowerBonus",
                "meaningful_runtime_surface": True,
            }
        ]
    }

    report = build_source_to_runtime_explainability_report(
        audit,
        card_behavior_plan=card_behavior_plan,
    )
    claim = report["claim_rows"][0]
    card = report["card_rows"][0]

    assert report["runtime_entity_transitions"] == [
        {
            "source_card_id": "SW_448",
            "source_role": "hero_power_transform_source",
            "runtime_card_id": "EX1_625t",
            "runtime_owner_role": "hero_power",
            "link_kind": "hero_power_transform",
            "runtime_file": "EX1_625t.json",
        }
    ]
    assert claim["source_card_id"] == "SW_448"
    assert claim["runtime_card_id"] == "EX1_625t"
    assert claim["emitted_runtime_files"] == ["EX1_625t.json"]
    assert claim["not_emitted_runtime_files"] == []
    assert card["card_id"] == "SW_448"
    assert card["emitted_runtime_files"] == ["EX1_625t.json"]
    assert card["evidence_chain"][0]["runtime_card_id"] == "EX1_625t"


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

    assert report["summary"]["cards_with_first_missing_link"] == 1
    assert rows["CARD_KEEP"]["strongest_claim_id"] == "keep_claim"
    assert rows["CARD_KEEP"]["first_missing_link"] is None
    assert rows["CARD_KEEP"]["why_not_emitted"] == "unsupported_or_unmapped"
    assert rows["CARD_KEEP"]["next_source_action"] == (
        "map_claim_kind_or_keep_report_only"
    )


def test_explainability_keeps_claim_gap_but_not_card_gap_when_runtime_is_emitted():
    audit = {
        "schema_version": 1,
        "deck_name": "FixtureDeck",
        "claim_rows": {
            "claim_runtime": {
                "claim_id": "claim_runtime",
                "claim_kind": "targeting_rule",
                "lane": "runtime_lowered",
                "policy_lane": "runtime_lowerable",
                "lowered_surfaces": ["cardid"],
                "first_reason": "allowed",
                "cards": ["NX2_019"],
            },
            "claim_role": {
                "claim_id": "claim_role",
                "claim_kind": "card_role",
                "lane": "runtime_lowerable",
                "policy_lane": "runtime_lowerable",
                "lowered_surfaces": ["cardid"],
                "first_reason": "not_seen_by_builder",
                "cards": ["NX2_019"],
            },
        },
        "claim_lifecycle_rows": [
            {
                "claim_id": "claim_runtime",
                "claim_kind": "targeting_rule",
                "policy_lane": "runtime_lowerable",
                "surface_gate_decision": "allowed",
                "surface_gate_reason": "allowed",
                "builder_or_router_decision": "emitted",
                "runtime_surface": "NX2_019.json",
                "emitted_files": ["NX2_019.json"],
                "suppressed_reason": None,
                "first_missing_link": None,
                "operator_impact": "diagnostic_only",
            },
            {
                "claim_id": "claim_role",
                "claim_kind": "card_role",
                "policy_lane": "runtime_lowerable",
                "surface_gate_decision": "allowed",
                "surface_gate_reason": "allowed",
                "builder_or_router_decision": "not_seen_by_builder",
                "runtime_surface": "NX2_019.json",
                "emitted_files": [],
                "suppressed_reason": None,
                "first_missing_link": "builder_or_router",
                "operator_impact": "diagnostic_only",
            },
        ],
        "card_rows": {
            "NX2_019": {
                "name": "Mind Sear",
                "readiness_lane": "cardid_only",
                "first_missing_link": "none",
                "runtime_surfaces": ["NX2_019.json"],
                "claim_lanes": {"runtime_lowered": 1, "runtime_lowerable": 1},
            }
        },
    }

    report = build_source_to_runtime_explainability_report(audit)

    card = report["card_rows"][0]
    assert card.get("first_missing_link") is None
    assert report["summary"]["cards_with_first_missing_link"] == 0
    role_claim = next(
        row for row in report["claim_rows"] if row["claim_id"] == "claim_role"
    )
    assert role_claim["first_missing_link"] == "builder_or_router"


def test_suppressed_combo_claim_does_not_expect_card_level_combo_runtime_link():
    claim = {
        "claim_kind": "combo_sequence",
        "cards": ["DS1_233", "VAC_419"],
        "suppressed_reason": "missing_timing",
    }

    assert _card_expected_runtime_files("DS1_233", claim) == []


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


@pytest.mark.parametrize(
    ("override", "reason", "expected_action"),
    [
        (
            {"deck_match_scope": "archetype_matched"},
            "mulligan_requires_exact_deck_match",
            "add_exact_deck_matched_source",
        ),
        (
            {"promotion_eligible": False},
            "mulligan_requires_promotion_eligible_source",
            "add_promotion_eligible_source",
        ),
        (
            {"source_visibility": "snippet_only"},
            "mulligan_requires_full_text_source",
            "add_full_text_public_guide_source",
        ),
        (
            {"source_lane": "archetype_matched_public_guide"},
            "mulligan_requires_deck_matched_public_guide_lane",
            "add_deck_matched_public_guide_source",
        ),
    ],
)
def test_mulligan_authority_suppression_recommends_authority_repair(
    override: dict[str, object],
    reason: str,
    expected_action: str,
):
    card_id = "AUTHORITY_CARD"
    claim_id = "authority_claim"
    deck_identity = {
        "deck_name": "FixtureDeck",
        "cards": [{"card_id": card_id, "name": "Authority Card", "count": 1}],
    }
    gameplan_contract = {
        "cards": {
            card_id: {
                "card_id": card_id,
                "name": "Authority Card",
                "count": 1,
                "coverage_status": "generic_low_confidence",
                "roles": [],
            }
        }
    }
    claim = {
        "claim_id": claim_id,
        "claim_kind": "mulligan_keep",
        "source_family": "guide",
        "cards": [card_id],
        "deck_match_scope": "exact_deck_matched",
        "promotion_eligible": True,
        "source_visibility": "full_text",
        "source_lane": "deck_matched_public_guide",
        "claim_readiness": "guide_backed",
        **override,
    }
    mulligan_plan = {
        "rules": [],
        "suppressed_rules": [
            {
                "claim_id": claim_id,
                "card": card_id,
                "reason": reason,
            }
        ],
    }
    config_readiness = build_config_readiness_report(
        deck_identity=deck_identity,
        claim_coverage={"uncovered_cards": [card_id], "total_cards": 1},
        gameplan_contract=gameplan_contract,
        mulligan_plan=mulligan_plan,
        card_behavior_plan={"rows": [], "suppressed": []},
        combo_plan={"combos": [], "suppressed": []},
        global_values_authority_matrix={"allowed_step1_overlays": []},
    )

    assert config_readiness["cards"][card_id]["first_missing_link"] == (
        "needs_mulligan_claim"
    )

    audit = build_source_contract_audit(
        deck_name="FixtureDeck",
        deck_identity=deck_identity,
        guide_claim_bundle={"claims": [claim]},
        mulligan_plan=mulligan_plan,
        config_readiness_report=config_readiness,
    )
    report = build_source_to_runtime_explainability_report(audit)
    claim_row = next(
        row for row in report["claim_rows"] if row["claim_id"] == claim_id
    )
    card_row = next(row for row in report["card_rows"] if row["card_id"] == card_id)
    attention_row = next(
        row for row in report["operator_attention"] if row["card_id"] == card_id
    )

    assert claim_row["why_not_emitted"] == reason
    assert card_row["why_not_emitted"] == reason
    assert card_row["next_source_action"] == expected_action
    assert card_row["first_missing_source_action"] == expected_action
    assert attention_row["next_source_action"] == expected_action
    assert attention_row["first_missing_source_action"] == expected_action
    assert claim_row["next_source_action"] == expected_action
    assert "add_mulligan_keep_or_discard_claim" not in {
        claim_row["next_source_action"],
        card_row["next_source_action"],
        card_row["first_missing_source_action"],
        attention_row["next_source_action"],
        attention_row["first_missing_source_action"],
    }


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

    assert rows["CARD_KEEP"]["first_missing_link"] is None
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

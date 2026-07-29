from __future__ import annotations

import pytest

from hsconfig.config_readiness import build_config_readiness_report
from hsconfig.globalvalues_authority import (
    build_globalvalues_authority_matrix,
)
from hsconfig.operator_summary import build_operator_summary
from hsconfig.runtime_surface_ledger import build_runtime_surface_ledger
from hsconfig.source_contract_audit import build_source_contract_audit
from hsconfig.source_document_builder import build_source_document_bundle
from hsconfig.source_to_runtime_explainability import (
    build_source_to_runtime_explainability_report,
)
from hsconfig.source_to_runtime_explainability import _card_expected_runtime_files
from tests.mulligan_authority_fixtures import build_canonical_mulligan_bundle
from tests.helpers.live_acquisition import acquire_live_test_provenance


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
        "condition": "*",
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
        {
            "claim_kind": "mulligan_discard",
            "selector": "CARD_KEEP",
            "condition": "*",
        }
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

    assert claim["operator"] == ">>"
    assert claim["emitted_runtime_files"] == []


def test_wrong_mulligan_condition_keeps_claim_card_closure_and_attention_missing():
    audit = _fixture_audit()
    audit["claim_rows"]["keep_claim"].update({"selector": "CARD_KEEP", "condition": "coin"})
    ledger = {
        "cards": {"CARD_KEEP": {"runtime_surfaces": ["Mulligan.json"]}, "CARD_NUM": {"runtime_surfaces": []}},
        "mulligan": {"rules": [{"mulligan": "CARD_KEEP", "value": "hold", "condition": "no_coin"}]},
        "linked_runtime_entities": {},
    }
    report = build_source_to_runtime_explainability_report(audit, runtime_surface_ledger=ledger)
    claim = next(row for row in report["claim_rows"] if row["claim_id"] == "keep_claim")
    card = next(row for row in report["card_rows"] if row["card_id"] == "CARD_KEEP")
    attention = next(row for row in report["operator_attention"] if row["card_id"] == "CARD_KEEP")
    assert claim["emitted_runtime_files"] == []
    assert claim["selector"] == "CARD_KEEP"
    assert claim["condition"] == "coin"
    assert card["emitted_runtime_files"] == []
    assert set(card["emitted_runtime_files"]).isdisjoint(card["not_emitted_runtime_files"])
    assert card["closure"]["missing_runtime_surfaces"] == ["Mulligan.json"]
    assert attention["status"] == "source_action_needed"


def test_globalvalues_claim_requires_and_preserves_exact_changed_key():
    audit = _fixture_audit()
    audit["claim_rows"]["numeric_claim"]["key"] = "GlobalAggroValue"
    audit["claim_lifecycle_rows"][1].update(
        {
            "builder_or_router_decision": "emitted",
            "runtime_surface": "GlobalValues.json",
            "emitted_files": ["GlobalValues.json"],
            "suppressed_reason": None,
            "first_missing_link": None,
        }
    )
    ledger = {
        "cards": {
            "CARD_KEEP": {"runtime_surfaces": []},
            "CARD_NUM": {"runtime_surfaces": []},
        },
        "globalvalues": {"changed_keys": ["DiscoverSimulationValueThresholdPercent"]},
        "linked_runtime_entities": {},
    }

    wrong_report = build_source_to_runtime_explainability_report(
        audit,
        runtime_surface_ledger=ledger,
    )
    wrong_claim = next(
        row
        for row in wrong_report["claim_rows"]
        if row["claim_id"] == "numeric_claim"
    )
    assert wrong_claim["key"] == "GlobalAggroValue"
    assert wrong_claim["emitted_runtime_files"] == []

    ledger["globalvalues"]["changed_keys"] = ["GlobalAggroValue"]
    matching_report = build_source_to_runtime_explainability_report(
        audit,
        runtime_surface_ledger=ledger,
    )
    matching_claim = next(
        row
        for row in matching_report["claim_rows"]
        if row["claim_id"] == "numeric_claim"
    )
    assert matching_claim["emitted_runtime_files"] == ["GlobalValues.json"]


@pytest.mark.parametrize(
    ("condition_field", "source_condition", "compiled_condition"),
    [
        (None, None, "*"),
        ("condition", {"coin": True}, "coin"),
        (
            "conditions",
            {"hand_contains": "CARD_SUPPORT"},
            "my_hand(count(),cardid=CARD_SUPPORT) > 0",
        ),
    ],
)
def test_productive_audit_mulligan_identity_matches_compiler_condition(
    condition_field,
    source_condition,
    compiled_condition,
):
    source_claim = {
        "claim_id": "keep_claim",
        "claim_kind": "mulligan_keep",
        "cards": ["CARD_KEEP"],
        "selector": "CARD_KEEP",
        "action": "hold",
    }
    if condition_field is not None:
        source_claim[condition_field] = source_condition
    bundle, deck_identity = build_canonical_mulligan_bundle([source_claim])
    deck_identity["cards"].append(
        {"card_id": "CARD_SUPPORT", "name": "Support", "count": 1}
    )
    claim_id = bundle["claims"][0]["claim_id"]
    mulligan_plan = {
        "rules": [
            {
                "card": "CARD_KEEP",
                "selector": "CARD_KEEP",
                "action": "hold",
                "condition": compiled_condition,
                "source_claim_ids": [claim_id],
            }
        ],
        "suppressed_rules": [],
    }
    audit = build_source_contract_audit(
        deck_name="CanonicalMulliganFixture",
        deck_identity=deck_identity,
        guide_claim_bundle=bundle,
        mulligan_plan=mulligan_plan,
    )
    ledger = build_runtime_surface_ledger(
        deck_identity=deck_identity,
        compiled_mulligan={
            "Mulligan": {
                "values": [
                    {
                        "mulligan": "CARD_KEEP",
                        "condition": compiled_condition,
                        "value": "hold",
                    }
                ]
            }
        },
        compiled_globalvalues={},
        compiled_combo=None,
        compiled_cardid_files={},
        linked_runtime_owners=[],
    )

    report = build_source_to_runtime_explainability_report(
        audit,
        runtime_surface_ledger=ledger,
    )
    audit_claim = audit["claim_rows"][claim_id]
    claim = next(
        row for row in report["claim_rows"] if row["claim_id"] == claim_id
    )

    assert audit_claim["selector"] == "CARD_KEEP"
    assert audit_claim["action"] == "hold"
    assert audit_claim["condition"] == (
        {} if source_condition is None else source_condition
    )
    assert claim["selector"] == "CARD_KEEP"
    assert claim["action"] == "hold"
    assert claim["condition"] == compiled_condition
    assert claim["emitted_runtime_files"] == ["Mulligan.json"]


def test_productive_audit_structured_mulligan_condition_rejects_mismatch():
    bundle, deck_identity = build_canonical_mulligan_bundle(
        [
            {
                "claim_id": "coin_keep",
                "claim_kind": "mulligan_keep",
                "cards": ["CARD_KEEP"],
                "selector": "CARD_KEEP",
                "action": "hold",
                "condition": {"coin": True},
            }
        ]
    )
    claim_id = bundle["claims"][0]["claim_id"]
    mulligan_plan = {
        "rules": [
            {
                "card": "CARD_KEEP",
                "selector": "CARD_KEEP",
                "action": "hold",
                "condition": "coin",
                "source_claim_ids": [claim_id],
            }
        ],
        "suppressed_rules": [],
    }
    audit = build_source_contract_audit(
        deck_name="CanonicalMulliganFixture",
        deck_identity=deck_identity,
        guide_claim_bundle=bundle,
        mulligan_plan=mulligan_plan,
    )
    ledger = build_runtime_surface_ledger(
        deck_identity=deck_identity,
        compiled_mulligan={
            "Mulligan": {
                "values": [
                    {
                        "mulligan": "CARD_KEEP",
                        "condition": "nocoin",
                        "value": "hold",
                    }
                ]
            }
        },
        compiled_globalvalues={},
        compiled_combo=None,
        compiled_cardid_files={},
        linked_runtime_owners=[],
    )

    report = build_source_to_runtime_explainability_report(
        audit,
        runtime_surface_ledger=ledger,
    )
    claim = next(
        row for row in report["claim_rows"] if row["claim_id"] == claim_id
    )

    assert claim["condition"] == "coin"
    assert claim["emitted_runtime_files"] == []


@pytest.mark.parametrize("identity_field", ["key", "globalvalues_key"])
def test_productive_audit_preserves_globalvalues_key_in_explainability(
    identity_field,
):
    audit = build_source_contract_audit(
        deck_name="GlobalFixture",
        deck_identity={
            "deck_name": "GlobalFixture",
            "cards": [{"card_id": "CARD_NUM", "count": 1}],
        },
        guide_claim_bundle={
            "claims": [
                {
                    "claim_id": "global_claim",
                    "claim_kind": "globalvalue_numeric_tuning",
                    "cards": ["CARD_NUM"],
                    identity_field: "GlobalAggroValue",
                }
            ]
        },
    )

    report = build_source_to_runtime_explainability_report(audit)
    claim = next(
        row
        for row in report["claim_rows"]
        if row["claim_id"] == "global_claim"
    )

    assert (
        audit["claim_rows"]["global_claim"][identity_field]
        == "GlobalAggroValue"
    )
    assert claim[identity_field] == "GlobalAggroValue"


def test_productive_matrix_globalvalues_identity_matches_exact_physical_key():
    deck_identity = {
        "deck_name": "MatrixGlobalValues",
        "deck_fingerprint": "sha256:matrix-globalvalues",
        "cards": [{"card_id": "CARD_HP", "name": "Hero Power Card", "count": 1}],
    }
    bundle = build_source_document_bundle(
        deck_identity=deck_identity,
        card_metadata={"cards": deck_identity["cards"]},
        source_documents=[
            {
                "source_url": "https://example.test/matrix-globalvalues",
                "source_title": "Matrix GlobalValues Guide",
                "source_family": "guide",
                "source_type": "public_guide",
                "retrieved_at": "2026-07-27T00:00:00Z",
                "acquisition_provenance": acquire_live_test_provenance(),
                "source_visibility": "full_text",
                "source_lane": "deck_matched_public_guide",
                "deck_match_scope": "exact_deck_matched",
                "deck_match": {
                    "exact_deck_evidence": {
                        "candidate_count": 1,
                        "decoded_candidate_count": 1,
                        "matched": True,
                        "matched_deck_fingerprint": (
                            "sha256:matrix-globalvalues"
                        ),
                        "candidate_deck_code_hashes": [
                            "sha256:matrix-globalvalues-source"
                        ],
                    }
                },
                "claims": [
                    {
                        "claim_id": "hero-power-posture",
                        "claim_kind": "gameplan_posture",
                        "cards": ["CARD_HP"],
                        "scope": "deck",
                        "stance": "hero_power_pressure",
                        "evidence_text_short": (
                            "Prioritize repeated hero power pressure."
                        ),
                        "source_confidence": "high",
                        "promotion_eligible": True,
                    }
                ],
            }
        ],
        current_date="2026-07-27",
    )
    claim = bundle["claims"][0]
    claim_id = claim["claim_id"]
    matrix = build_globalvalues_authority_matrix(
        aggression_profile="baseline",
        claims=bundle["claims"],
        deck_identity=deck_identity,
        verified_source_receipts=bundle["canonical_source_receipts"],
    )
    assert [
        row["key"] for row in matrix["allowed_step1_overlays"]
    ] == ["MyHeroPowerValue"]
    audit = build_source_contract_audit(
        deck_name="MatrixGlobalValues",
        deck_identity=deck_identity,
        guide_claim_bundle=bundle,
        global_values_authority_matrix=matrix,
    )
    matching_ledger = build_runtime_surface_ledger(
        deck_identity=deck_identity,
        compiled_mulligan={},
        compiled_globalvalues={
            "MyHeroPowerValue": {
                "values": [{"condition": "*", "value": "9"}]
            }
        },
        globalvalues_baseline={
            "MyHeroPowerValue": {
                "values": [{"condition": "*", "value": "5"}]
            }
        },
        compiled_combo=None,
        compiled_cardid_files={},
        linked_runtime_owners=[],
    )

    matching = build_source_to_runtime_explainability_report(
        audit,
        runtime_surface_ledger=matching_ledger,
    )
    audit_claim = audit["claim_rows"][claim_id]
    matching_claim = next(
        row for row in matching["claim_rows"] if row["claim_id"] == claim_id
    )
    assert audit_claim["key"] == "MyHeroPowerValue"
    assert audit_claim["globalvalues_keys"] == ["MyHeroPowerValue"]
    assert matching_claim["emitted_runtime_files"] == ["GlobalValues.json"]

    mismatching_ledger = build_runtime_surface_ledger(
        deck_identity=deck_identity,
        compiled_mulligan={},
        compiled_globalvalues={
            "FirstTurnValueWeight": {
                "values": [{"condition": "*", "value": "0.75"}]
            }
        },
        globalvalues_baseline={
            "FirstTurnValueWeight": {
                "values": [{"condition": "*", "value": "0.50"}]
            }
        },
        compiled_combo=None,
        compiled_cardid_files={},
        linked_runtime_owners=[],
    )
    mismatching = build_source_to_runtime_explainability_report(
        audit,
        runtime_surface_ledger=mismatching_ledger,
    )
    mismatching_claim = next(
        row
        for row in mismatching["claim_rows"]
        if row["claim_id"] == claim_id
    )
    assert mismatching_claim["emitted_runtime_files"] == []
    assert mismatching_claim["not_emitted_runtime_files"] == [
        "GlobalValues.json"
    ]


def test_multi_identity_behavior_claim_reconciles_each_physical_runtime_file():
    claim_id = "multi_behavior_claim"
    deck_identity = {
        "deck_name": "MultiBehavior",
        "cards": [
            {"card_id": "CARD_A", "count": 1},
            {"card_id": "CARD_B", "count": 1},
        ],
    }
    behavior_rows = [
        {
            "claim_id": claim_id,
            "source_claim_ids": [claim_id],
            "card_id": card_id,
            "source_card_id": card_id,
            "runtime_card_id": card_id,
            "link_kind": "self",
            "surface_family": "CARDID.json",
            "behavior_block": "BeforePlayCardBonus",
            "condition": "*",
            "value": value,
            "meaningful_runtime_surface": True,
        }
        for card_id, value in (("CARD_A", "7"), ("CARD_B", "9"))
    ]
    behavior_plan = {"rows": behavior_rows, "suppressed": []}
    audit = build_source_contract_audit(
        deck_name="MultiBehavior",
        deck_identity=deck_identity,
        guide_claim_bundle={
            "claims": [
                {
                    "claim_id": claim_id,
                    "claim_kind": "targeting_rule",
                    "cards": ["CARD_A", "CARD_B"],
                    "source_lane": "deck_matched_public_guide",
                    "strategic_receipt_verified": True,
                }
            ]
        },
        card_behavior_plan=behavior_plan,
    )
    ledger = build_runtime_surface_ledger(
        deck_identity=deck_identity,
        compiled_mulligan={},
        compiled_globalvalues={},
        compiled_combo=None,
        compiled_cardid_files={
            f"{row['card_id']}.json": {
                "GameCardId": row["card_id"],
                "BeforePlayCardBonus": {
                    "values": [
                        {
                            "condition": row["condition"],
                            "value": row["value"],
                        }
                    ]
                },
            }
            for row in behavior_rows
        },
        linked_runtime_owners=behavior_rows,
    )

    complete = build_source_to_runtime_explainability_report(
        audit,
        card_behavior_plan=behavior_plan,
        runtime_surface_ledger=ledger,
    )
    complete_claim = next(
        row
        for row in complete["claim_rows"]
        if row["claim_id"] == claim_id
    )
    assert complete_claim["emitted_runtime_files"] == [
        "CARD_A.json",
        "CARD_B.json",
    ]
    assert len(complete_claim["behavior_identities"]) == 2

    ledger["cardid"]["entities"][1]["behavior_rows"][0]["value"] = "WRONG"
    partial = build_source_to_runtime_explainability_report(
        audit,
        card_behavior_plan=behavior_plan,
        runtime_surface_ledger=ledger,
    )
    partial_claim = next(
        row
        for row in partial["claim_rows"]
        if row["claim_id"] == claim_id
    )
    assert partial_claim["emitted_runtime_files"] == ["CARD_A.json"]
    assert partial_claim["not_emitted_runtime_files"] == ["CARD_B.json"]
    assert partial_claim["builder_or_router_decision"] == "physical_partial"
    assert partial_claim["first_missing_link"] == "needs_runtime_surface"
    assert (
        partial_claim["why_not_emitted"]
        == "physical_runtime_surface_missing"
    )
    assert partial_claim["next_source_action"] == (
        "add_runtime_lowerable_claim_or_router_support"
    )
    assert partial["summary"]["runtime_lowered_claims"] == 0
    assert partial["summary"]["claims_with_first_missing_link"] == 1
    assert partial["summary"]["cards_with_first_missing_link"] == 1

    cards = {row["card_id"]: row for row in partial["card_rows"]}
    assert cards["CARD_A"]["emitted_runtime_files"] == ["CARD_A.json"]
    assert cards["CARD_A"]["not_emitted_runtime_files"] == []
    assert cards["CARD_A"]["first_missing_link"] is None
    assert cards["CARD_A"]["closure_lane"] == "runtime_backed_non_strong"
    assert cards["CARD_A"]["strong_ready"] is False
    assert cards["CARD_B"]["emitted_runtime_files"] == []
    assert cards["CARD_B"]["not_emitted_runtime_files"] == ["CARD_B.json"]
    assert cards["CARD_B"]["first_missing_link"] == "needs_runtime_surface"
    assert cards["CARD_B"]["closure_lane"] == "explicit_gap"
    assert cards["CARD_B"]["strong_ready"] is False
    attention = {
        row["card_id"]: row for row in partial["operator_attention"]
    }
    assert attention["CARD_A"]["status"] == "runtime_backed"
    assert attention["CARD_B"]["status"] == "source_action_needed"

    operator_summary = build_operator_summary(
        deck_name="MultiBehavior",
        deck_code="AAEBA-test",
        technical_validation={"status": "passed"},
        guide_source_depth={
            "source_depth_status": "source_backed",
            "claim_count": 1,
            "source_evidence": {"warnings_count": 0},
        },
        generated_files=["CARD_A.json", "CARD_B.json"],
        runtime_surface_ledger={
            "mulligan": {"rule_count": 0},
            "globalvalues": {"changed_key_count": 0},
            "cardid": {"entity_count": 2},
            "combo": {"row_count": 0},
        },
        source_to_runtime_explainability_report=partial,
    )
    strong_closure = operator_summary["source_backed_strong_closure"]
    assert strong_closure["promotion_ready"] is False
    assert strong_closure["strong_closure_diagnostics"] == [
        {
            "claim_id": claim_id,
            "reason": "strong_closure_claim_not_eligible",
        }
    ]


def test_multi_row_behavior_claim_requires_every_identity_in_runtime_file():
    claim_id = "multi_row_behavior_claim"
    deck_identity = {
        "deck_name": "MultiRowBehavior",
        "cards": [{"card_id": "CARD_A", "count": 1}],
    }
    behavior_rows = [
        {
            "claim_id": claim_id,
            "source_claim_ids": [claim_id],
            "card_id": "CARD_A",
            "source_card_id": "CARD_A",
            "runtime_card_id": "CARD_A",
            "link_kind": "self",
            "surface_family": "CARDID.json",
            "behavior_block": behavior_block,
            "condition": "*",
            "value": value,
            "meaningful_runtime_surface": True,
        }
        for behavior_block, value in (
            ("BeforePlayCardBonus", "7"),
            ("InHandBonus", "9"),
        )
    ]
    behavior_plan = {"rows": behavior_rows, "suppressed": []}
    audit = build_source_contract_audit(
        deck_name="MultiRowBehavior",
        deck_identity=deck_identity,
        guide_claim_bundle={
            "claims": [
                {
                    "claim_id": claim_id,
                    "claim_kind": "targeting_rule",
                    "cards": ["CARD_A"],
                }
            ]
        },
        card_behavior_plan=behavior_plan,
    )
    ledger = build_runtime_surface_ledger(
        deck_identity=deck_identity,
        compiled_mulligan={},
        compiled_globalvalues={},
        compiled_combo=None,
        compiled_cardid_files={
            "CARD_A.json": {
                "GameCardId": "CARD_A",
                "BeforePlayCardBonus": {
                    "values": [{"condition": "*", "value": "7"}]
                },
                "InHandBonus": {
                    "values": [{"condition": "*", "value": "9"}]
                },
            }
        },
        linked_runtime_owners=behavior_rows,
    )

    complete = build_source_to_runtime_explainability_report(
        audit,
        card_behavior_plan=behavior_plan,
        runtime_surface_ledger=ledger,
    )
    complete_claim = next(
        row
        for row in complete["claim_rows"]
        if row["claim_id"] == claim_id
    )
    assert complete_claim["emitted_runtime_files"] == ["CARD_A.json"]

    ledger["cardid"]["entities"][0]["behavior_rows"][1]["value"] = "WRONG"
    partial = build_source_to_runtime_explainability_report(
        audit,
        card_behavior_plan=behavior_plan,
        runtime_surface_ledger=ledger,
    )
    partial_claim = next(
        row
        for row in partial["claim_rows"]
        if row["claim_id"] == claim_id
    )
    assert partial_claim["emitted_runtime_files"] == []
    assert partial_claim["not_emitted_runtime_files"] == ["CARD_A.json"]


def test_card_behavior_plan_requires_exact_block_for_self_runtime_owner():
    audit = _fixture_audit()
    audit["claim_rows"]["keep_claim"].update(
        {
            "claim_kind": "mechanic_usage",
            "cards": ["CARD_KEEP"],
        }
    )
    audit["claim_lifecycle_rows"][0].update(
        {
            "claim_kind": "mechanic_usage",
            "runtime_surface": "CARD_KEEP.json",
            "emitted_files": ["CARD_KEEP.json"],
        }
    )
    behavior_plan = {
        "rows": [
            {
                "claim_id": "keep_claim",
                "card_id": "CARD_KEEP",
                "source_card_id": "CARD_KEEP",
                "runtime_card_id": "CARD_KEEP",
                "link_kind": "self",
                "behavior_block": "BeforePlayCardBonus",
                "condition": "coin",
                "value": "9",
                "meaningful_runtime_surface": True,
            }
        ]
    }
    ledger = {
        "cards": {
            "CARD_KEEP": {"runtime_surfaces": ["CARD_KEEP.json"]},
            "CARD_NUM": {"runtime_surfaces": []},
        },
        "cardid": {
            "entities": [
                {
                    "card_id": "CARD_KEEP",
                    "behavior_blocks": {"BeforeUseHeroPowerBonus": 1},
                }
            ]
        },
        "linked_runtime_entities": {},
    }

    wrong_report = build_source_to_runtime_explainability_report(
        audit,
        card_behavior_plan=behavior_plan,
        runtime_surface_ledger=ledger,
    )
    wrong_claim = next(
        row for row in wrong_report["claim_rows"] if row["claim_id"] == "keep_claim"
    )
    wrong_card = next(
        row for row in wrong_report["card_rows"] if row["card_id"] == "CARD_KEEP"
    )
    assert wrong_claim["emitted_runtime_files"] == []
    assert wrong_card["emitted_runtime_files"] == []
    assert wrong_card["closure"]["missing_runtime_surfaces"] == ["CARD_KEEP.json"]
    assert wrong_claim["behavior_block"] == "BeforePlayCardBonus"
    assert wrong_claim["condition"] == "coin"
    assert wrong_claim["value"] == "9"
    assert wrong_claim["source_card_id"] == "CARD_KEEP"
    assert wrong_claim["runtime_card_id"] == "CARD_KEEP"

    ledger["cardid"]["entities"][0]["behavior_blocks"] = {
        "BeforePlayCardBonus": 1
    }
    ledger["cardid"]["entities"][0]["behavior_rows"] = [
        {
            "behavior_block": "BeforePlayCardBonus",
            "condition": "no_coin",
            "value": "9",
        }
    ]
    wrong_row_report = build_source_to_runtime_explainability_report(
        audit,
        card_behavior_plan=behavior_plan,
        runtime_surface_ledger=ledger,
    )
    wrong_row_claim = next(
        row
        for row in wrong_row_report["claim_rows"]
        if row["claim_id"] == "keep_claim"
    )
    assert wrong_row_claim["emitted_runtime_files"] == []

    ledger["cardid"]["entities"][0]["behavior_rows"][0]["condition"] = "coin"
    matching_report = build_source_to_runtime_explainability_report(
        audit,
        card_behavior_plan=behavior_plan,
        runtime_surface_ledger=ledger,
    )
    matching_claim = next(
        row
        for row in matching_report["claim_rows"]
        if row["claim_id"] == "keep_claim"
    )
    matching_card = next(
        row
        for row in matching_report["card_rows"]
        if row["card_id"] == "CARD_KEEP"
    )
    assert matching_claim["emitted_runtime_files"] == ["CARD_KEEP.json"]
    assert matching_card["emitted_runtime_files"] == ["CARD_KEEP.json"]


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


def test_explainability_points_to_source_action_for_versioned_policy_keep():
    report = build_source_to_runtime_explainability_report(
        audit={
            "claim_rows": [
                {
                    "card_id": "PIRATE_DH_CARD",
                    "claim_kind": "mulligan_keep",
                    "source_type": "versioned_internal_policy",
                    "source_lane": "versioned_internal_policy",
                    "runtime_backed": True,
                }
            ]
        },
        runtime_files={"Mulligan.json"},
    )

    row = report["card_rows"][0]
    assert row["source_lane"] == "versioned_internal_policy"
    assert row["first_missing_source_action"] == "add_explicit_mulligan_source"
    assert row["runtime_lowering_status"] == "policy_backed_runtime"


def test_explainability_exposes_versioned_policy_runtime_as_non_strong():
    report = build_source_to_runtime_explainability_report(
        audit={
            "claim_rows": [
                {
                    "card_id": "CARD_001",
                    "claim_kind": "mulligan_keep",
                    "source_type": "versioned_internal_policy",
                    "source_lane": "versioned_internal_policy",
                    "runtime_backed": True,
                }
            ]
        },
        runtime_files={"Mulligan.json"},
    )

    row = report["card_rows"][0]
    assert row["source_lane"] == "versioned_internal_policy"
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


def test_explainability_does_not_treat_versioned_policy_non_mulligan_as_mulligan():
    report = build_source_to_runtime_explainability_report(
        audit={
            "claim_rows": [
                {
                    "card_id": "POLICY_ROLE",
                    "claim_kind": "card_role",
                    "source_type": "versioned_internal_policy",
                    "runtime_backed": True,
                }
            ]
        },
        runtime_files={"CardRole.json"},
    )

    row = report["card_rows"][0]
    assert row["first_missing_source_action"] == "none"
    assert row["runtime_lowering_status"] == "source_backed_runtime"


def test_explainability_preserves_versioned_policy_from_audit_report():
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
                    "source_type": "versioned_internal_policy",
                    "source_lane": "versioned_internal_policy",
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
    assert row["source_lane"] == "versioned_internal_policy"
    assert row["first_missing_source_action"] == "add_explicit_mulligan_source"
    assert row["runtime_lowering_status"] == "policy_backed_runtime"

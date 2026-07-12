from __future__ import annotations

from hsconfig.source_contract_conformance import (
    build_source_contract_conformance_snapshot,
    render_source_contract_conformance_markdown,
)
from hsconfig.source_document_model import SUPPORTED_ATOMIC_CLAIM_KINDS


def test_conformance_snapshot_covers_every_supported_claim_kind():
    snapshot = build_source_contract_conformance_snapshot()

    assert snapshot["schema_version"] == 1
    assert snapshot["operator_gate_impact"] == "diagnostic_only"
    assert set(snapshot["claim_kind_rows"]) == set(SUPPORTED_ATOMIC_CLAIM_KINDS)
    assert snapshot["summary"]["claim_kinds_total"] == len(SUPPORTED_ATOMIC_CLAIM_KINDS)
    assert snapshot["summary"]["missing_claim_kinds"] == []
    assert snapshot["summary"]["extra_claim_kinds"] == []


def test_conformance_snapshot_keeps_key_boundaries_explicit():
    rows = build_source_contract_conformance_snapshot()["claim_kind_rows"]

    assert rows["mulligan_keep"]["policy_lane"] == "runtime_lowerable"
    assert rows["mulligan_keep"]["surface_gates"]["mulligan"]["decision"] == "allowed"
    assert rows["mulligan_keep"]["surface_gates"]["cardid"]["decision"] == "rejected"

    assert rows["hero_power_transform"]["policy_lane"] == "suppressed_or_conditional"
    assert rows["hero_power_transform"]["surface_gates"]["cardid"]["decision"] == "allowed"
    assert rows["hero_power_transform"]["surface_gates"]["mulligan"]["decision"] == "rejected"

    assert rows["globalvalue_numeric_tuning"]["policy_lane"] == "runtime_evidence_required"
    assert rows["globalvalue_numeric_tuning"]["surface_gates"]["globalvalues"]["decision"] == "rejected"
    assert rows["globalvalue_numeric_tuning"]["surface_gates"]["globalvalues"]["reason"] == (
        "requires_runtime_evidence"
    )


def test_conformance_snapshot_reports_no_policy_gate_mismatches_for_representative_context():
    snapshot = build_source_contract_conformance_snapshot()

    assert snapshot["summary"]["policy_gate_mismatch_count"] == 0
    assert snapshot["summary"]["policy_gate_mismatches"] == []


def test_conformance_snapshot_describes_a_policy_gate_mismatch(monkeypatch):
    from hsconfig import source_contract_conformance as conformance

    original = conformance.surface_gate_decision

    def mismatching_gate(claim, surface, context=None):
        decision = original(claim, surface, context=context)
        if decision.claim_kind == "mulligan_keep" and surface == "mulligan":
            return type(decision)(False, "forced_test_mismatch", decision.claim_kind, surface)
        return decision

    monkeypatch.setattr(conformance, "surface_gate_decision", mismatching_gate)
    mismatches = build_source_contract_conformance_snapshot()["summary"][
        "policy_gate_mismatches"
    ]

    assert mismatches == [
        {
            "claim_kind": "mulligan_keep",
            "surface": "mulligan",
            "policy_allowed": True,
            "gate_decision": "rejected",
            "gate_reason": "forced_test_mismatch",
        }
    ]


def test_conformance_snapshot_proves_start_of_game_effect_is_not_hand_keep():
    snapshot = build_source_contract_conformance_snapshot()
    row = snapshot["start_of_game_mulligan_suppression"]

    assert row["claim_kind"] == "mulligan_keep"
    assert row["surface"] == "mulligan"
    assert row["decision"] == "rejected"
    assert row["reason"] == "start_of_game_effect_does_not_require_opening_hand"
    assert row["operator_meaning"] == (
        "Start-of-game effects remain effect-visible but do not become opening-hand keeps."
    )


def test_darkbishop_effect_boundary_is_visible_in_conformance_contract():
    snapshot = build_source_contract_conformance_snapshot()
    hero_power_row = snapshot["claim_kind_rows"]["hero_power_transform"]
    suppression = snapshot["start_of_game_mulligan_suppression"]

    assert hero_power_row["surface_gates"]["cardid"]["decision"] == "allowed"
    assert hero_power_row["surface_gates"]["mulligan"]["decision"] == "rejected"
    assert suppression["reason"] == "start_of_game_effect_does_not_require_opening_hand"


def test_conformance_markdown_is_compact_and_diagnostic_only():
    markdown = render_source_contract_conformance_markdown(
        build_source_contract_conformance_snapshot()
    )

    assert "# Source Contract Conformance Snapshot" in markdown
    assert "Diagnostic only" in markdown
    assert "| mulligan_keep | runtime_lowerable | mulligan |" in markdown
    assert "| globalvalue_numeric_tuning | runtime_evidence_required | none |" in markdown
    assert "operator_summary.json remains the apply authority" in markdown


def test_conformance_snapshot_contains_no_apply_authority_fields():
    snapshot = build_source_contract_conformance_snapshot()

    forbidden_keys = {
        "runtime_apply_allowed",
        "runtime_apply_mode",
        "apply_policy",
        "next_action",
        "technical_status",
    }
    assert forbidden_keys.isdisjoint(snapshot)
    assert snapshot["operator_gate_impact"] == "diagnostic_only"

from __future__ import annotations

from hsconfig.contract_spine_sentinel import build_contract_spine_sentinel_report
from hsconfig.source_document_model import SUPPORTED_ATOMIC_CLAIM_KINDS


def test_contract_spine_sentinel_report_is_clean_for_current_repo():
    report = build_contract_spine_sentinel_report()

    assert report["schema_version"] == 1
    assert report["status"] == "clean"
    assert report["operator_gate_impact"] == "diagnostic_only"
    assert report["apply_blocking"] is False
    assert report["problems"] == []


def test_contract_spine_sentinel_covers_every_supported_claim_kind():
    report = build_contract_spine_sentinel_report()
    checks = report["checks"]

    assert set(checks["supported_claim_kinds"]) == set(SUPPORTED_ATOMIC_CLAIM_KINDS)
    assert checks["policy_missing_claim_kinds"] == []
    assert checks["policy_extra_claim_kinds"] == []
    assert checks["spine_missing_claim_kinds"] == []
    assert checks["spine_extra_claim_kinds"] == []


def test_contract_spine_sentinel_preserves_diagnostic_only_boundary():
    report = build_contract_spine_sentinel_report()
    checks = report["checks"]

    assert checks["non_diagnostic_policy_claim_kinds"] == []
    assert checks["spine_rows_with_apply_authority_fields"] == []
    assert checks["conformance_operator_gate_impact"] == "diagnostic_only"
    assert checks["conformance_apply_authority_fields_present"] == []


def test_contract_spine_sentinel_keeps_critical_runtime_boundaries_visible():
    report = build_contract_spine_sentinel_report()
    critical = report["checks"]["critical_boundary_rows"]

    assert critical["mulligan_keep"]["allowed_surfaces"] == ["mulligan"]
    assert critical["mulligan_keep"]["final_runtime_effect"] == "emits_mulligan_runtime_row"

    assert critical["hero_power_transform"]["allowed_surfaces"] == ["cardid"]
    assert critical["hero_power_transform"]["final_runtime_effect"] == "emits_cardid_runtime_row"

    assert critical["globalvalue_numeric_tuning"]["allowed_surfaces"] == []
    assert critical["globalvalue_numeric_tuning"]["final_runtime_effect"] == (
        "suppressed_until_runtime_evidence"
    )


def test_contract_spine_sentinel_keeps_start_of_game_out_of_mulligan_keep():
    report = build_contract_spine_sentinel_report()
    suppression = report["checks"]["start_of_game_mulligan_suppression"]

    assert suppression["decision"] == "rejected"
    assert suppression["reason"] == "start_of_game_effect_does_not_require_opening_hand"
    assert "do not become opening-hand keeps" in suppression["operator_meaning"]

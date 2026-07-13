from hsconfig.source_claim_family_registry import (
    build_claim_family_registry_report,
    claim_family_registry,
)
from hsconfig.source_contract_matrix import source_contract_policy_by_claim_kind
from hsconfig.source_document_model import SUPPORTED_ATOMIC_CLAIM_KINDS


def test_claim_family_registry_covers_every_supported_claim_kind():
    registry = claim_family_registry()
    policy = source_contract_policy_by_claim_kind()

    assert set(registry) == set(SUPPORTED_ATOMIC_CLAIM_KINDS)
    assert set(registry) == set(policy)
    for claim_kind, row in registry.items():
        assert row["claim_kind"] == claim_kind
        assert row["policy_lane"] == policy[claim_kind]["lane"]
        assert row["allowed_surfaces"] == policy[claim_kind]["allowed_surfaces"]
        assert row["operator_gate_impact"] == "diagnostic_only"
        assert row["normal_apply_gate"] == "reports/operator_summary.json"


def test_critical_false_lowering_boundaries_are_named():
    registry = claim_family_registry()

    assert registry["hero_power_transform"]["negative_boundary"] == (
        "not_opening_hand_keep_without_explicit_mulligan_claim"
    )
    assert registry["globalvalue_numeric_tuning"]["negative_boundary"] == (
        "requires_runtime_evidence_before_numeric_write"
    )
    assert registry["discover_choice"]["negative_boundary"] == (
        "requires_exact_option_identity"
    )
    assert registry["choose_one_choice"]["negative_boundary"] == (
        "requires_exact_option_identity"
    )
    assert registry["combo_sequence"]["negative_boundary"] == (
        "requires_complete_ordered_sequence"
    )


def test_claim_family_registry_report_is_clean_for_current_contract():
    report = build_claim_family_registry_report()

    assert report["status"] == "clean"
    assert report["authority"] == "diagnostic_only"
    assert report["apply_blocking"] is False
    assert report["problems"] == []

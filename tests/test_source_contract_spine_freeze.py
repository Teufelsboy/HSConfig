import pytest

from hsconfig.source_contract_matrix import source_contract_policy_by_claim_kind
from hsconfig.source_document_model import (
    SUPPORTED_ATOMIC_CLAIM_KINDS,
    surface_gate_decision,
)


EXPECTED_POLICY = {
    "archetype": ("report_only", ()),
    "mulligan_keep": ("runtime_lowerable", ("mulligan",)),
    "mulligan_discard": ("runtime_lowerable", ("mulligan",)),
    "card_role": ("suppressed_or_conditional", ("cardid",)),
    "targeting_rule": ("runtime_lowerable", ("cardid",)),
    "combo_sequence": ("runtime_lowerable", ("combo",)),
    "gameplan_posture": ("runtime_lowerable", ("globalvalues",)),
    "hero_power_transform": ("suppressed_or_conditional", ("cardid",)),
    "mechanic_usage": ("suppressed_or_conditional", ("cardid",)),
    "known_bad_pattern": ("suppressed_or_conditional", ("cardid",)),
    "tech_slot": ("report_only", ()),
    "replacement_option": ("report_only", ()),
    "discover_choice": ("suppressed_or_conditional", ("cardid",)),
    "choose_one_choice": ("suppressed_or_conditional", ("cardid",)),
    "globalvalue_numeric_tuning": ("runtime_evidence_required", ()),
}


def test_supported_claim_kinds_match_frozen_policy():
    policy = source_contract_policy_by_claim_kind()

    assert set(policy) == set(SUPPORTED_ATOMIC_CLAIM_KINDS)
    assert set(policy) == set(EXPECTED_POLICY)

    for claim_kind, (lane, surfaces) in EXPECTED_POLICY.items():
        row = policy[claim_kind]
        assert row["lane"] == lane
        assert tuple(row["allowed_surfaces"]) == surfaces


@pytest.mark.parametrize("claim_kind,expected", sorted(EXPECTED_POLICY.items()))
def test_surface_gate_matches_policy_matrix(claim_kind, expected):
    _, surfaces = expected
    claim = {
        "claim_kind": claim_kind,
        "claim_readiness": "guide_backed",
        "trust_ceiling": "runtime_candidate",
        "cards": ["CARD_001"],
    }
    context = {
        "card_roles": {
            "CARD_001": {
                "roles": ["mulligan_anchor"],
                "semantic_families": [],
            }
        }
    }

    for surface in ("mulligan", "globalvalues", "cardid", "combo"):
        decision = surface_gate_decision(claim, surface, context=context)
        if surface in surfaces:
            assert decision.allowed is True, (claim_kind, surface, decision.reason)
        else:
            assert decision.allowed is False, (claim_kind, surface)


def test_globalvalue_numeric_tuning_is_never_step1_lowerable():
    claim = {
        "claim_kind": "globalvalue_numeric_tuning",
        "claim_readiness": "guide_backed",
        "trust_ceiling": "runtime_candidate",
        "cards": [],
    }

    decision = surface_gate_decision(claim, "globalvalues")

    assert decision.allowed is False
    assert decision.reason == "requires_runtime_evidence"

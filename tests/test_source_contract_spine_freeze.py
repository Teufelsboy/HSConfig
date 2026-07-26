import pytest

from hsconfig.source_contract_matrix import source_contract_policy_by_claim_kind
from hsconfig.source_document_builder import build_source_document_bundle
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


def _canonical_posture_bundle():
    deck_identity = {
        "deck_name": "FixtureDeck",
        "deck_fingerprint": "fixture-deck-fingerprint",
        "cards": [{"card_id": "CARD_001", "name": "Fixture Card", "count": 1}],
    }
    return build_source_document_bundle(
        deck_identity=deck_identity,
        card_metadata={"cards": deck_identity["cards"]},
        source_documents=[
            {
                "source_url": "https://example.invalid/fixture-guide",
                "source_title": "Fixture exact-deck guide",
                "source_family": "guide",
                "source_type": "public_guide",
                "retrieved_at": "2026-07-26T00:00:00Z",
                "source_visibility": "full_text",
                "source_lane": "deck_matched_public_guide",
                "deck_match_scope": "exact_deck_matched",
                "deck_match": {
                    "exact_deck_evidence": {
                        "candidate_count": 1,
                        "decoded_candidate_count": 1,
                        "matched": True,
                        "matched_deck_fingerprint": "fixture-deck-fingerprint",
                        "candidate_deck_code_hashes": ["sha256:fixture-source"],
                    }
                },
                "claims": [
                    {
                        "claim_kind": "gameplan_posture",
                        "cards": ["CARD_001"],
                        "scope": "deck",
                        "stance": "aggro_burn",
                        "evidence_text_short": "Use an aggro burn posture.",
                        "source_confidence": "high",
                        "promotion_eligible": True,
                    }
                ],
            }
        ],
        current_date="2026-07-26",
    )


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
    if claim_kind == "gameplan_posture":
        bundle = _canonical_posture_bundle()
        claim = bundle["claims"][0]
        context["deck_identity"] = {
            "deck_fingerprint": "fixture-deck-fingerprint"
        }
        context["verified_source_receipts"] = bundle[
            "globalvalues_source_receipts"
        ]

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


def test_each_policy_row_has_complete_contract_metadata():
    policy = source_contract_policy_by_claim_kind()

    for claim_kind, row in policy.items():
        assert row["semantic_lane"] == row["lane"], claim_kind
        assert isinstance(row["required_fields"], tuple), claim_kind
        assert "claim_kind" in row["required_fields"], claim_kind
        assert "claim_readiness" in row["required_fields"], claim_kind
        assert "trust_ceiling" in row["required_fields"], claim_kind
        assert isinstance(row["runtime_lowerable"], bool), claim_kind
        assert isinstance(row["default_suppression_reason"], str), claim_kind
        assert row["default_suppression_reason"], claim_kind
        assert row["operator_gate_impact"] == "diagnostic_only", claim_kind
        assert set(row["allowed_surfaces"]).issubset(
            {"mulligan", "globalvalues", "cardid", "combo"}
        ), claim_kind

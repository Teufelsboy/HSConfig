import pytest

from hsconfig.card_behavior_router import route_card_behavior_claims
from hsconfig.card_behavior_surface_router import route_card_behavior_surfaces
from hsconfig.combo_plan import build_combo_plan
from hsconfig.source_document_model import (
    can_lower_to_globalvalues,
    can_lower_to_mulligan,
    surface_gate_decision,
)


def test_start_of_game_hero_power_transform_does_not_lower_to_mulligan_keep():
    claim = {
        "claim_id": "darkbishop_wrong_keep",
        "claim_kind": "mulligan_keep",
        "claim_readiness": "guide_backed",
        "trust_ceiling": "runtime_candidate",
        "cards": ["SW_448"],
    }

    decision = can_lower_to_mulligan(
        claim,
        card_roles={
            "SW_448": {
                "roles": ["start_of_game", "hero_power_transform"],
                "semantic_families": ["start_of_game", "hero_power_transform"],
            }
        },
    )

    assert decision.allowed is False
    assert decision.reason == "start_of_game_effect_does_not_require_opening_hand"


def test_globalvalue_numeric_tuning_requires_runtime_evidence_in_step1():
    claim = {
        "claim_id": "numeric_tuning_from_guide",
        "claim_kind": "globalvalue_numeric_tuning",
        "claim_readiness": "guide_backed",
        "trust_ceiling": "runtime_candidate",
        "key": "LowHpBoardValuePenalty",
    }

    decision = can_lower_to_globalvalues(claim)

    assert decision.allowed is False
    assert decision.reason == "requires_runtime_evidence"


def test_unresolved_discover_choice_stays_suppressed_until_option_identity_is_linked():
    claim = {
        "claim_id": "discover_without_identity_link",
        "claim_kind": "discover_choice",
        "claim_readiness": "guide_backed",
        "trust_ceiling": "runtime_candidate",
        "cards": ["CARD_001"],
        "option_card_id": "OPTION_001",
    }

    result = route_card_behavior_surfaces([claim], identity_links={})

    assert result["rows"] == []
    assert result["suppressed"][0]["claim_id"] == "discover_without_identity_link"
    assert result["suppressed"][0]["reason"] == "unresolved_option_identity"


def test_vague_combo_sequence_without_two_cards_stays_suppressed():
    claim = {
        "claim_id": "vague_combo",
        "claim_kind": "combo_sequence",
        "claim_readiness": "guide_backed",
        "trust_ceiling": "runtime_candidate",
        "cards": ["CARD_001"],
        "sequence": ["CARD_001"],
        "timing_kind": "same_turn",
        "operator": ">>",
        "values": ["6"],
    }

    result = build_combo_plan(deck_cards={"CARD_001"}, claims=[claim])

    assert result["combos"] == []
    assert result["suppressed"][0]["claim_id"] == "vague_combo"
    assert result["suppressed"][0]["reason"] == "sequence_too_short"


@pytest.mark.parametrize(
    ("claim", "surface", "expected_reason"),
    [
        (
            {
                "claim_id": "darkbishop_effect_only",
                "claim_kind": "hero_power_transform",
                "claim_readiness": "guide_backed",
                "cards": ["SW_448"],
                "semantic_qualifiers": {
                    "timing": "start_of_game",
                    "state_requirements": "hero_power_transform",
                },
            },
            "mulligan",
            "claim_kind_not_mulligan_surface",
        ),
        (
            {
                "claim_id": "deck_effect_misread_as_keep",
                "claim_kind": "mulligan_keep",
                "claim_readiness": "guide_backed",
                "cards": ["SW_448"],
                "semantic_qualifiers": {
                    "timing": "start_of_game",
                    "zone_scope": "deck",
                },
            },
            "mulligan",
            "start_of_game_effect_does_not_require_opening_hand",
        ),
        (
            {
                "claim_id": "runtime_only_globalvalue",
                "claim_kind": "globalvalue_numeric_tuning",
                "claim_readiness": "guide_backed",
                "key": "FirstTurnValueWeight",
                "runtime_value": 1.2,
            },
            "globalvalues",
            "requires_runtime_evidence",
        ),
        (
            {
                "claim_id": "discover_without_option",
                "claim_kind": "discover_choice",
                "claim_readiness": "guide_backed",
                "cards": ["DISCOVER_TEST_CARD"],
            },
            "mulligan",
            "claim_kind_not_mulligan_surface",
        ),
        (
            {
                "claim_id": "vague_combo_not_mulligan",
                "claim_kind": "combo_sequence",
                "claim_readiness": "guide_backed",
                "cards": ["CARD_A"],
                "sequence": ["CARD_A"],
            },
            "mulligan",
            "claim_kind_not_mulligan_surface",
        ),
    ],
)
def test_false_runtime_lowering_boundaries_do_not_cross_surfaces(
    claim,
    surface,
    expected_reason,
):
    decision = surface_gate_decision(claim, surface)

    assert decision.allowed is False
    assert decision.reason == expected_reason


def test_discover_choice_without_option_identity_is_suppressed_not_lowered():
    claims = [
        {
            "claim_id": "discover_generic_burn",
            "claim_kind": "discover_choice",
            "claim_readiness": "guide_backed",
            "cards": ["DISCOVER_TEST_CARD"],
            "evidence_text_short": "Choose burn from Discover.",
        }
    ]

    routed = route_card_behavior_claims(claims, identity_links={})

    assert routed["card_rows"] == {}
    assert routed["suppressed"][0]["claim_id"] == "discover_generic_burn"
    assert routed["suppressed"][0]["reason"] in {
        "requires_exact_option_identity",
        "unresolved_option_identity",
    }


def test_one_card_or_vague_combo_sequence_does_not_emit_combo_json_rows():
    contract = {
        "claims": [
            {
                "claim_id": "vague_combo",
                "claim_kind": "combo_sequence",
                "claim_readiness": "guide_backed",
                "cards": ["CARD_A"],
                "sequence": ["CARD_A"],
            }
        ]
    }

    combo = build_combo_plan(deck_cards={"CARD_A"}, claims=contract["claims"])

    assert combo["combos"] == []
    assert combo["suppressed"][0]["claim_id"] == "vague_combo"
    assert combo["suppressed"][0]["reason"] == "sequence_too_short"

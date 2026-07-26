import pytest

from hsconfig.card_behavior_router import route_card_behavior_claims
from hsconfig.card_behavior_surface_router import route_card_behavior_surfaces
from hsconfig.combo_plan import build_combo_plan as _build_combo_plan
from hsconfig.static_semantics import infer_static_semantics
from hsconfig.source_document_model import (
    can_lower_to_globalvalues,
    can_lower_to_mulligan,
    source_claim_signature,
    surface_gate_decision,
)


_COMBO_TEST_FINGERPRINT = "semantic-boundary-combo-fingerprint"


def build_combo_plan(*, deck_cards, claims):
    authoritative_claims = [
        {
            **claim,
            "source_family": "guide",
            "source_type": "public_guide",
            "source_visibility": "full_text",
            "source_lane": "deck_matched_public_guide",
            "deck_match_scope": "exact_deck_matched",
            "promotion_eligible": True,
            "deck_match": {
                "exact_deck_evidence": {
                    "candidate_count": 1,
                    "decoded_candidate_count": 1,
                    "matched": True,
                    "matched_deck_fingerprint": _COMBO_TEST_FINGERPRINT,
                    "candidate_deck_code_hashes": ["sha256:semantic-boundary-combo"],
                }
            },
        }
        for claim in claims
    ]
    receipts = [
        {
            "receipt_kind": "canonical_exact_deck_source_document",
            "matched_deck_fingerprint": _COMBO_TEST_FINGERPRINT,
            "claim_id": str(claim.get("claim_id", "")),
            "claim_signature": source_claim_signature(claim),
        }
        for claim in authoritative_claims
    ]
    return _build_combo_plan(
        deck_cards=deck_cards,
        claims=authoritative_claims,
        deck_identity={"deck_fingerprint": _COMBO_TEST_FINGERPRINT},
        verified_source_receipts=receipts,
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


def test_deckbuilding_effect_does_not_lower_to_opening_hand_keep():
    claim = {
        "claim_id": "highlander_effect_not_keep",
        "claim_kind": "mulligan_keep",
        "claim_readiness": "guide_backed",
        "trust_ceiling": "runtime_candidate",
        "cards": ["HIGHLANDER_FIXTURE"],
        "semantic_qualifiers": {
            "timing": "start_of_game",
            "state_requirements": "deckbuilding_effect",
            "zone_scope": "deck",
        },
    }

    decision = can_lower_to_mulligan(
        claim,
        card_roles={
            "HIGHLANDER_FIXTURE": {
                "roles": ["start_of_game", "deckbuilding_modifier"],
                "semantic_families": ["start_of_game", "deckbuilding_modifier"],
            }
        },
    )

    assert decision.allowed is False
    assert decision.reason == "start_of_game_effect_does_not_require_opening_hand"


def test_generated_random_pool_does_not_become_deterministic_cardid_behavior():
    claim = {
        "claim_id": "random_generate_claim",
        "claim_kind": "mechanic_usage",
        "claim_readiness": "guide_backed",
        "trust_ceiling": "runtime_candidate",
        "cards": ["RANDOM_POOL_CARD"],
        "mechanic": "generated_entity_random_pool",
        "evidence_text_short": "Generate a random minion.",
    }

    result = route_card_behavior_surfaces([claim], identity_links={})

    assert result["rows"] == []
    assert result["suppressed"][0]["claim_id"] == "random_generate_claim"
    assert result["suppressed"][0]["reason"] == "requires_supported_cardid_surface"
    assert result["suppressed"][0]["lowering_policy"] == "report_only"


def test_choice_claim_with_unresolved_option_identity_stays_diagnostic():
    claim = {
        "claim_id": "choose_option_without_identity",
        "claim_kind": "choose_one_choice",
        "claim_readiness": "guide_backed",
        "cards": ["CHOOSE_ONE_CARD"],
        "option_card_id": "UNRESOLVED_OPTION",
    }

    decision = surface_gate_decision(claim, "card_behavior")
    routed = route_card_behavior_surfaces([claim], identity_links={})

    assert decision.allowed is False
    assert decision.reason == "requires_exact_option_identity"
    assert routed["rows"] == []
    assert routed["suppressed"][0]["claim_id"] == "choose_option_without_identity"


def test_choice_claim_with_resolved_option_identity_uses_cardid_gate():
    claim = {
        "claim_id": "choose_option_with_identity",
        "claim_kind": "choose_one_choice",
        "claim_readiness": "guide_backed",
        "cards": ["CHOOSE_ONE_CARD"],
        "option_card_id": "OPTION_001",
    }

    decision = surface_gate_decision(
        claim,
        "card_behavior",
        context={
            "identity_links": {
                "CHOOSE_ONE_CARD": [{"card_id": "OPTION_001"}],
            }
        },
    )

    assert decision.allowed is True
    assert decision.reason == "allowed"
    assert decision.surface == "cardid"


def test_timing_mechanics_are_warning_first_not_cross_surface_claims():
    cards = [
        {
            "id": "SECRET_FIXTURE",
            "type": "SPELL",
            "mechanics": ["SECRET"],
            "text": "Secret: When your opponent casts a spell, summon a random minion.",
        },
        {
            "id": "LOCATION_FIXTURE",
            "type": "LOCATION",
            "text": "Summon two Treants.",
        },
        {
            "id": "WEAPON_FIXTURE",
            "type": "WEAPON",
            "text": "After your hero attacks, Discover a spell.",
        },
    ]

    semantics_by_id = {card["id"]: infer_static_semantics(card) for card in cards}
    families_by_id = {
        card_id: set(semantics["families"])
        for card_id, semantics in semantics_by_id.items()
    }
    warning_only_by_id = {
        card_id: set(semantics["warning_only"])
        for card_id, semantics in semantics_by_id.items()
    }

    assert {"secret", "generated_entity_random_pool"} <= families_by_id["SECRET_FIXTURE"]
    assert {"secret_timing", "generated_entity_random_pool"} <= warning_only_by_id[
        "SECRET_FIXTURE"
    ]
    assert "location" in families_by_id["LOCATION_FIXTURE"]
    assert "location_activation" in warning_only_by_id["LOCATION_FIXTURE"]
    assert {"weapon", "discover"} <= families_by_id["WEAPON_FIXTURE"]


def test_modern_wild_keywords_remain_report_first_until_surface_exists():
    for keyword in ("Titan", "Tourist", "Imbue", "Forge", "Excavate"):
        result = infer_static_semantics(
            {
                "id": f"{keyword.upper()}_FIXTURE",
                "type": "MINION",
                "text": f"{keyword}: fixture text.",
            }
        )

        assert keyword.lower() in result["families"]
        assert keyword.lower() in result["warning_only"]

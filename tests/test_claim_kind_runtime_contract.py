import pytest

from hsconfig.card_behavior_surface_router import route_card_behavior_surfaces
from hsconfig.gameplan_contract import build_gameplan_contract
from hsconfig.guide_research import normalize_source_claims
from hsconfig.input_loading import guide_documents_from_legacy_claims
from hsconfig.mulligan_plan import build_mulligan_plan
from hsconfig.research_contract import build_research_contract_bundle
from hsconfig.source_document_model import runtime_claim_kind, surface_gate_decision


def test_broad_legacy_mulligan_claim_type_does_not_create_hold():
    deck_identity = {
        "deck_name": "FixtureDeck",
        "cards": [{"card_id": "SW_448", "count": 1, "name": "Darkbishop Benedictus"}],
    }
    card_metadata = {
        "cards": [
            {
                "card_id": "SW_448",
                "name": "Darkbishop Benedictus",
                "semantic_families": [
                    "start_of_game",
                    "hero_power_transform",
                    "hero_power_pressure",
                ],
            }
        ]
    }
    source_claims = normalize_source_claims(
        [
            {
                "source": "fixture",
                "claim_type": "mulligan_and_gameplan",
                "claim": "The effect enables Shadowform at game start.",
                "cards": ["SW_448"],
                "confidence": "guide_backed",
            }
        ]
    )

    bundle = build_research_contract_bundle(deck_identity, card_metadata, source_claims)
    contract = build_gameplan_contract(deck_identity, card_metadata, source_claims)

    assert bundle["mulligan_anchor_map"]["SW_448"]["intent"] != "hold"
    assert contract["mulligan_anchors"] == []


def test_explicit_mulligan_keep_claim_kind_creates_hold():
    deck_identity = {
        "deck_name": "FixtureDeck",
        "cards": [{"card_id": "EX1_001", "count": 2, "name": "Fixture One-Drop"}],
    }
    card_metadata = {
        "cards": [
            {
                "card_id": "EX1_001",
                "name": "Fixture One-Drop",
                "mechanic_families": ["battlecry"],
            }
        ]
    }
    source_claims = normalize_source_claims(
        [
            {
                "source": "fixture-guide",
                "claim_kind": "mulligan_keep",
                "claim_readiness": "guide_backed",
                "trust_ceiling": "runtime_candidate",
                "claim": "Keep this one-drop in the mulligan.",
                "cards": ["EX1_001"],
                "confidence": "guide_backed",
            }
        ]
    )

    bundle = build_research_contract_bundle(deck_identity, card_metadata, source_claims)
    contract = build_gameplan_contract(deck_identity, card_metadata, source_claims)

    assert bundle["mulligan_anchor_map"]["EX1_001"]["intent"] == "hold"
    assert contract["mulligan_anchors"][0]["card_id"] == "EX1_001"


def test_legacy_exact_mulligan_keep_claim_type_is_accepted_for_runtime():
    plan = build_mulligan_plan(
        deck_name="FixtureDeck",
        claims=[
            {
                "claim_type": "mulligan_keep",
                "cards": ["EX1_001"],
                "claim_id": "legacy_exact_keep",
                "claim_readiness": "guide_backed",
            }
        ],
        card_roles={},
    )

    assert plan["rules"][0]["card"] == "EX1_001"
    assert plan["rules"][0]["action"] == "hold"


def test_broad_legacy_mulligan_claim_type_is_not_accepted_for_runtime():
    plan = build_mulligan_plan(
        deck_name="FixtureDeck",
        claims=[
            {
                "claim_type": "mulligan_and_gameplan",
                "cards": ["EX1_001"],
                "claim_id": "legacy_broad_keep",
                "claim_readiness": "guide_backed",
            }
        ],
        card_roles={},
    )

    assert plan["rules"] == []
    assert plan["quality"]["blocked_reason"] == "no_source_backed_mulligan_keeps"


def test_runtime_claim_kind_maps_only_exact_legacy_runtime_types():
    assert runtime_claim_kind({"claim_type": "mulligan_keep"}) == "mulligan_keep"
    assert runtime_claim_kind({"claim_type": "mulligan_discard"}) == "mulligan_discard"
    assert runtime_claim_kind({"claim_type": "combo"}) == "combo_sequence"
    assert runtime_claim_kind({"claim_type": "bad_pattern"}) == "known_bad_pattern"
    assert runtime_claim_kind({"claim_type": "mulligan"}) == ""
    assert runtime_claim_kind({"claim_type": "mulligan_and_gameplan"}) == ""


def test_globalvalue_numeric_tuning_is_valid_but_requires_runtime_evidence():
    claim = {
        "claim_kind": "globalvalue_numeric_tuning",
        "claim_readiness": "guide_backed",
        "trust_ceiling": "runtime_candidate",
        "cards": [],
    }

    decision = surface_gate_decision(claim, "globalvalues")

    assert decision.allowed is False
    assert decision.claim_kind == "globalvalue_numeric_tuning"
    assert decision.reason == "requires_runtime_evidence"


def test_gameplan_posture_can_lower_to_globalvalues_when_runtime_lowerable():
    claim = {
        "claim_kind": "gameplan_posture",
        "claim_readiness": "guide_backed",
        "trust_ceiling": "runtime_candidate",
    }

    decision = surface_gate_decision(claim, "globalvalues")

    assert decision.allowed is True
    assert decision.reason == "allowed"


def test_mulligan_claim_does_not_lower_to_cardid_or_globalvalues():
    claim = {
        "claim_kind": "mulligan_keep",
        "claim_readiness": "guide_backed",
        "trust_ceiling": "runtime_candidate",
        "cards": ["EX1_001"],
    }

    cardid_decision = surface_gate_decision(claim, "cardid")
    globalvalues_decision = surface_gate_decision(claim, "globalvalues")

    assert cardid_decision.allowed is False
    assert cardid_decision.reason == "claim_kind_not_cardid_surface"
    assert globalvalues_decision.allowed is False
    assert globalvalues_decision.reason == "claim_kind_not_globalvalues_surface"


def test_mulligan_discard_can_lower_to_mulligan_surface():
    claim = {
        "claim_kind": "mulligan_discard",
        "claim_readiness": "guide_backed",
        "trust_ceiling": "runtime_candidate",
        "cards": ["EX1_001"],
    }

    decision = surface_gate_decision(claim, "mulligan")

    assert decision.allowed is True
    assert decision.reason == "allowed"


def test_runtime_valid_non_mulligan_claim_does_not_lower_to_mulligan_surface():
    claim = {
        "claim_kind": "hero_power_transform",
        "claim_readiness": "source_backed_static_semantics",
        "trust_ceiling": "runtime_candidate",
        "cards": ["SW_448"],
    }

    decision = surface_gate_decision(claim, "mulligan")

    assert decision.allowed is False
    assert decision.reason == "claim_kind_not_mulligan_surface"


def test_hero_power_transform_can_emit_cardid_without_mulligan_keep():
    claim = {
        "claim_id": "hero_power_transform_fixture",
        "claim_kind": "hero_power_transform",
        "claim_readiness": "source_backed_static_semantics",
        "trust_ceiling": "runtime_candidate",
        "cards": ["CARD_HP"],
        "runtime_block": "BeforeUseHeroPowerBonus",
        "runtime_value": 25,
    }

    cardid_decision = surface_gate_decision(claim, "cardid")
    mulligan_decision = surface_gate_decision(claim, "mulligan")
    routed = route_card_behavior_surfaces([claim])

    assert cardid_decision.allowed is True
    assert mulligan_decision.allowed is False
    assert mulligan_decision.reason == "claim_kind_not_mulligan_surface"
    assert routed["rows"][0]["card_id"] == "CARD_HP"
    assert routed["rows"][0]["behavior_block"] == "BeforeUseHeroPowerBonus"
    assert routed["suppressed"] == []


def test_legacy_claims_json_broad_keep_text_stays_non_mulligan_runtime():
    documents = guide_documents_from_legacy_claims(
        [
            {
                "source": "guide",
                "url": "https://example.invalid/deck-guide",
                "claim": "Always keep Pressure One and push face damage early.",
                "cards": ["EX1_001"],
                "claim_type": "mulligan_and_gameplan",
            }
        ]
    )

    claim = documents[0]["claims"][0]

    assert claim["claim_kind"] == "targeting_rule"
    assert claim["claim_kind"] != "mulligan_keep"


def test_legacy_claims_json_exact_mulligan_keep_still_creates_mulligan_runtime_kind():
    documents = guide_documents_from_legacy_claims(
        [
            {
                "source": "guide",
                "url": "https://example.invalid/deck-guide",
                "claim": "Always keep Pressure One.",
                "cards": ["EX1_001"],
                "claim_type": "mulligan_keep",
            }
        ]
    )

    claim = documents[0]["claims"][0]

    assert claim["claim_kind"] == "mulligan_keep"
    assert claim["stance"] == "keep"


def test_start_of_game_transform_claim_remains_effect_not_mulligan_hold():
    deck_identity = {
        "deck_name": "ShadowPriest",
        "cards": [{"card_id": "SW_448", "count": 1, "name": "Darkbishop Benedictus"}],
    }
    card_metadata = {
        "cards": [
            {
                "card_id": "SW_448",
                "name": "Darkbishop Benedictus",
                "semantic_families": [
                    "start_of_game",
                    "shadowform",
                    "hero_power_transform",
                    "hero_power_pressure",
                ],
                "linked_entities": [
                    {
                        "card_id": "EX1_625t",
                        "name": "Mind Spike",
                        "type": "HERO_POWER",
                    }
                ],
            }
        ]
    }
    source_claims = normalize_source_claims(
        [
            {
                "source": "hearthstonejson",
                "claim_kind": "hero_power_transform",
                "claim_readiness": "source_backed_static_semantics",
                "trust_ceiling": "runtime_candidate",
                "claim": "If the deck has only Shadow spells, the starting Hero Power becomes Mind Spike.",
                "cards": ["SW_448"],
                "confidence": "source_backed_static_semantics",
            }
        ]
    )

    bundle = build_research_contract_bundle(deck_identity, card_metadata, source_claims)
    contract = build_gameplan_contract(
        deck_identity,
        card_metadata,
        source_claims,
        research_bundle=bundle,
    )

    assert "hero_power_transform" in bundle["card_role_map"]["SW_448"]["roles"]
    assert bundle["mulligan_anchor_map"]["SW_448"]["intent"] != "hold"
    assert contract["mulligan_anchors"] == []
    assert (
        contract["card_usage_expectations"]["SW_448"]["expected_use"]
        == "start_of_game_shadowform_enables_hero_power_pressure"
    )


def test_explicit_start_of_game_mulligan_keep_is_suppressed():
    plan = build_mulligan_plan(
        deck_name="ShadowPriest",
        claims=[
            {
                "claim_kind": "mulligan_keep",
                "claim_readiness": "guide_backed",
                "trust_ceiling": "runtime_candidate",
                "cards": ["SW_448"],
                "claim_id": "keep_start_effect",
            }
        ],
        card_roles={
            "SW_448": {
                "roles": ["start_of_game", "hero_power_transform"],
                "confidence": "source_backed_static_semantics",
            }
        },
    )

    assert plan["rules"] == []
    assert plan["suppressed_rules"][0]["reason"] == (
        "start_of_game_effect_does_not_require_opening_hand"
    )


@pytest.mark.parametrize(
    "role",
    [
        "deck_state_modifier",
        "deckbuilding_modifier",
        "deck_size_modifier",
        "even_odd_modifier",
        "highlander_modifier",
        "hero_power_transform",
        "passive_start_effect",
        "start_in_deck_requirement",
        "start_of_game_modifier",
    ],
)
def test_start_of_game_non_hand_roles_suppress_mulligan_keep(role):
    claim = {
        "claim_kind": "mulligan_keep",
        "claim_readiness": "guide_backed",
        "trust_ceiling": "runtime_candidate",
        "cards": ["CARD_001"],
    }
    context = {
        "card_roles": {
            "CARD_001": {
                "roles": ["start_of_game", role],
            }
        }
    }

    decision = surface_gate_decision(claim, "mulligan", context)

    assert decision.allowed is False
    assert decision.reason == "start_of_game_effect_does_not_require_opening_hand"


def test_start_of_game_without_mulligan_anchor_suppresses_mulligan_keep():
    claim = {
        "claim_kind": "mulligan_keep",
        "claim_readiness": "guide_backed",
        "trust_ceiling": "runtime_candidate",
        "cards": ["CARD_001"],
    }
    context = {
        "card_roles": {
            "CARD_001": {
                "roles": ["start_of_game"],
            }
        }
    }

    decision = surface_gate_decision(claim, "mulligan", context)

    assert decision.allowed is False
    assert decision.reason == "start_of_game_effect_does_not_require_opening_hand"


def test_start_of_game_with_mulligan_anchor_allows_explicit_mulligan_keep():
    claim = {
        "claim_kind": "mulligan_keep",
        "claim_readiness": "guide_backed",
        "trust_ceiling": "runtime_candidate",
        "cards": ["CARD_001"],
    }
    context = {
        "card_roles": {
            "CARD_001": {
                "roles": ["start_of_game", "mulligan_anchor"],
            }
        }
    }

    decision = surface_gate_decision(claim, "mulligan", context)

    assert decision.allowed is True
    assert decision.reason == "allowed"


def test_start_of_game_semantic_family_suppresses_mulligan_keep():
    claim = {
        "claim_kind": "mulligan_keep",
        "claim_readiness": "guide_backed",
        "trust_ceiling": "runtime_candidate",
        "cards": ["CARD_001"],
    }
    context = {
        "card_roles": {
            "CARD_001": {
                "roles": ["start_of_game"],
                "semantic_families": ["passive_start_effect"],
            }
        }
    }

    decision = surface_gate_decision(claim, "mulligan", context)

    assert decision.allowed is False
    assert decision.reason == "start_of_game_effect_does_not_require_opening_hand"

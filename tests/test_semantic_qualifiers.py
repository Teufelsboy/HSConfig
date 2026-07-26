from hsconfig.source_document_builder import build_source_document_bundle
from hsconfig.source_document_model import can_lower_to_mulligan
from hsconfig.source_semantic_qualifiers import normalize_semantic_qualifiers
from hsconfig.source_evidence_verifier import claim_evidence_status
from hsconfig.guide_claim_builder import build_guide_claim_bundle
from tests.mulligan_authority_fixtures import (
    build_canonical_mulligan_bundle,
)


def test_normalize_semantic_qualifiers_keeps_known_fields_and_drops_empty_values():
    result = normalize_semantic_qualifiers(
        {
            "timing": "Start of Game",
            "zone_scope": "Deck",
            "target_scope": "",
            "option_surface": "Discover",
            "state_requirements": ["all_shadow_spells", ""],
        }
    )

    assert result == {
        "timing": "start_of_game",
        "zone_scope": "deck",
        "option_surface": "discover",
        "state_requirements": ["all_shadow_spells"],
    }


def test_hero_power_transform_coerces_singleton_state_requirement_to_list():
    result = normalize_semantic_qualifiers(
        {
            "claim_kind": "hero_power_transform",
            "cards": ["SW_448"],
            "semantic_qualifiers": {"state_requirements": "all_shadow_spells"},
        },
        card_roles={"SW_448": {"roles": ["hero_power_transform"]}},
    )

    assert result["state_requirements"] == [
        "all_shadow_spells",
        "hero_power_transform",
    ]


def test_source_document_claim_preserves_semantic_qualifiers():
    bundle = build_source_document_bundle(
        deck_identity={
            "deck_name": "ShadowPriest",
            "cards": [{"card_id": "SW_448", "name": "Darkbishop Benedictus"}],
        },
        card_metadata={
            "SW_448": {
                "card_id": "SW_448",
                "name": "Darkbishop Benedictus",
                "text": "Start of Game: Enter Shadowform.",
            }
        },
        source_documents=[
            {
                "source_url": "https://example.com/shadowpriest",
                "source_title": "ShadowPriest Guide",
                "source_family": "guide",
                "retrieved_at": "2026-07-13",
                "claims": [
                    {
                        "claim_kind": "hero_power_transform",
                        "cards": ["SW_448"],
                        "evidence_text_short": "Start of Game changes Hero Power.",
                        "source_confidence": "high",
                        "timing": "start_of_game",
                        "zone_scope": "deck",
                        "state_requirements": ["all_shadow_spells"],
                    }
                ],
            }
        ],
    )

    claim = bundle["claims"][0]
    assert claim["semantic_qualifiers"] == {
        "timing": "start_of_game",
        "zone_scope": "deck",
        "state_requirements": ["all_shadow_spells"],
    }


def test_semantic_qualifiers_count_as_actionable_specificity_for_runtime_hints():
    row = claim_evidence_status(
        {
            "claim_kind": "targeting_rule",
            "cards": ["CARD_001"],
            "evidence_text_short": "Send burn face.",
            "source_confidence": "high",
            "runtime_block": "BeforeBattlecryTargetBonus",
            "semantic_qualifiers": {"target_scope": "enemy_hero"},
        },
        {"source_family": "guide", "source_url": "https://example.com"},
    )

    assert not any(
        warning["reason"] == "runtime_lowering_claim_lacks_actionable_specificity"
        for warning in row["warnings"]
    )


def test_static_darkbishop_claim_derives_start_effect_qualifiers():
    bundle = build_guide_claim_bundle(
        deck_identity={"deck_name": "ShadowPriest"},
        card_metadata={
            "SW_448": {
                "card_id": "SW_448",
                "name": "Darkbishop Benedictus",
                "text": "Start of Game: Enter Shadowform. Your hero power becomes Mind Spike.",
            }
        },
    )

    claim = next(
        claim
        for claim in bundle["claims"]
        if claim["claim_kind"] == "hero_power_transform"
    )

    assert claim["semantic_qualifiers"]["timing"] == "start_of_game"
    assert "hero_power_transform" in claim["semantic_qualifiers"]["state_requirements"]


def test_start_of_game_qualifier_blocks_mulligan_keep_without_opening_hand_text():
    claim = {
        "claim_kind": "mulligan_keep",
        "claim_readiness": "guide_backed",
        "trust_ceiling": "runtime_candidate",
        "cards": ["START_EFFECT"],
        "evidence_text_short": "Core deck enabler.",
        "semantic_qualifiers": {
            "timing": "start_of_game",
            "zone_scope": "deck",
            "state_requirements": ["hero_power_transform"],
        },
    }

    decision = can_lower_to_mulligan(claim)

    assert decision.allowed is False
    assert decision.reason == "start_of_game_effect_does_not_require_opening_hand"


def test_start_of_game_qualifier_allows_explicit_opening_hand_text():
    bundle, deck_identity = build_canonical_mulligan_bundle(
        [
            {
                "claim_kind": "mulligan_keep",
                "cards": ["START_EFFECT"],
                "evidence_text_short": (
                    "Always keep START_EFFECT in your opening hand."
                ),
                "semantic_qualifiers": {
                    "timing": "start_of_game",
                    "zone_scope": "deck",
                    "state_requirements": ["hero_power_transform"],
                },
            }
        ]
    )
    claim = bundle["claims"][0]

    decision = can_lower_to_mulligan(
        claim,
        deck_identity=deck_identity,
        verified_source_receipts=bundle["canonical_source_receipts"],
    )

    assert decision.allowed is True


def test_start_of_game_qualifier_warns_about_suspicious_mulligan_keep():
    row = claim_evidence_status(
        {
            "claim_kind": "mulligan_keep",
            "cards": ["START_EFFECT"],
            "evidence_text_short": "Core deck enabler.",
            "source_confidence": "high",
            "semantic_qualifiers": {
                "timing": "start_of_game",
                "zone_scope": "deck",
                "state_requirements": ["hero_power_transform"],
            },
        },
        {"source_family": "guide", "source_url": "https://example.com"},
    )

    assert any(
        warning["reason"] == "suspicious_mulligan_keep_non_hand_effect"
        for warning in row["warnings"]
    )


def test_normalize_semantic_qualifiers_accepts_generation_and_deck_evaluation():
    result = normalize_semantic_qualifiers(
        {
            "semantic_qualifiers": {
                "generation_scope": "Generated Card",
                "deck_evaluation": ["No Duplicates", "Odd Cost"],
            }
        }
    )

    assert result["generation_scope"] == "generated"
    assert result["deck_evaluation"] == ["highlander", "odd"]


def test_deck_evaluation_qualifier_blocks_mulligan_keep_without_opening_hand_text():
    claim = {
        "claim_kind": "mulligan_keep",
        "claim_readiness": "guide_backed",
        "trust_ceiling": "runtime_candidate",
        "cards": ["DECK_MODIFIER"],
        "evidence_text_short": "Core highlander payoff for this deck.",
        "semantic_qualifiers": {
            "deck_evaluation": "highlander",
        },
    }

    decision = can_lower_to_mulligan(claim)

    assert decision.allowed is False
    assert decision.reason == "start_of_game_effect_does_not_require_opening_hand"


def test_generated_qualifier_blocks_mulligan_keep_without_opening_hand_text():
    claim = {
        "claim_kind": "mulligan_keep",
        "claim_readiness": "guide_backed",
        "trust_ceiling": "runtime_candidate",
        "cards": ["GENERATED_OPTION"],
        "evidence_text_short": "Generated payoff card matters later.",
        "semantic_qualifiers": {
            "generation_scope": "generated",
        },
    }

    decision = can_lower_to_mulligan(claim)

    assert decision.allowed is False
    assert decision.reason == "start_of_game_effect_does_not_require_opening_hand"


def test_deck_evaluation_qualifier_allows_explicit_opening_hand_text():
    bundle, deck_identity = build_canonical_mulligan_bundle(
        [
            {
                "claim_kind": "mulligan_keep",
                "cards": ["DECK_MODIFIER"],
                "evidence_text_short": (
                    "Always keep DECK_MODIFIER in your opening hand."
                ),
                "semantic_qualifiers": {
                    "deck_evaluation": "highlander",
                },
            }
        ]
    )
    claim = bundle["claims"][0]

    decision = can_lower_to_mulligan(
        claim,
        deck_identity=deck_identity,
        verified_source_receipts=bundle["canonical_source_receipts"],
    )

    assert decision.allowed is True


def test_opening_hand_qualifier_allows_deck_evaluation_keep_without_prose_marker():
    bundle, deck_identity = build_canonical_mulligan_bundle(
        [
            {
                "claim_kind": "mulligan_keep",
                "cards": ["DECK_MODIFIER"],
                "evidence_text_short": "Always keep this card.",
                "semantic_qualifiers": normalize_semantic_qualifiers(
                    {
                        "semantic_qualifiers": {
                            "timing": "Opening Hand",
                            "deck_evaluation": "No Duplicates",
                        }
                    }
                ),
            }
        ]
    )
    claim = bundle["claims"][0]

    decision = can_lower_to_mulligan(
        claim,
        deck_identity=deck_identity,
        verified_source_receipts=bundle["canonical_source_receipts"],
    )

    assert claim["semantic_qualifiers"]["timing"] == "mulligan"
    assert decision.allowed is True

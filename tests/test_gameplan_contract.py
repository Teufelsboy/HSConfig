from hsconfig.gameplan_contract import build_gameplan_contract
from hsconfig.guide_research import normalize_source_claims


def test_gameplan_contract_covers_every_card_with_source_confidence():
    deck_identity = {
        "deck_name": "Fixture Aggro",
        "deck_slug": "fixture_aggro",
        "cards": [
            {"card_id": "EX1_001", "count": 2},
            {"card_id": "EX1_002", "count": 1},
            {"card_id": "EX1_003", "count": 1},
        ],
    }
    card_metadata = {
        "cards": [
            {"card_id": "EX1_001", "name": "One", "mechanic_families": ["battlecry"]},
            {"card_id": "EX1_002", "name": "Two", "mechanic_families": ["damage"]},
            {"card_id": "EX1_003", "name": "Three", "mechanic_families": ["draw"]},
        ]
    }
    source_claims = normalize_source_claims(
        [
            {
                "source": "guide",
                "url": "https://example.invalid/deck",
                "claim": "Always keep One and push face damage early.",
                "cards": ["EX1_001"],
                "claim_kind": "mulligan_keep",
                "claim_type": "mulligan_and_gameplan",
                "claim_readiness": "guide_backed",
                "trust_ceiling": "runtime_candidate",
            },
            {
                "source": "guide",
                "url": "https://example.invalid/deck",
                "claim": "Use One with Two for a burst combo turn.",
                "cards": ["EX1_001", "EX1_002"],
                "claim_type": "combo",
            },
            {
                "source": "guide",
                "url": "https://example.invalid/deck",
                "claim": "Never keep Three in the opener.",
                "cards": ["EX1_003"],
                "claim_kind": "mulligan_discard",
                "claim_type": "bad_pattern",
                "claim_readiness": "guide_backed",
                "trust_ceiling": "runtime_candidate",
            },
        ]
    )

    contract = build_gameplan_contract(deck_identity, card_metadata, source_claims)

    assert contract["archetype"] == "aggressive_gameplan"
    assert contract["aggression_profile"]["speed"] == "aggro"
    assert set(contract["cards"]) == {"EX1_001", "EX1_002", "EX1_003"}
    assert contract["cards"]["EX1_001"]["coverage_status"] == "guide_backed"
    assert contract["cards"]["EX1_001"]["roles"] == [
        "battlecry",
        "combo_piece",
        "mulligan_anchor",
        "pressure",
    ]
    assert contract["cards"]["EX1_003"]["coverage_status"] == "guide_backed"
    assert contract["mulligan_anchors"][0]["card_id"] == "EX1_001"
    assert contract["card_usage_expectations"]["EX1_001"]["expected_use"] == "keep_and_pressure"
    assert contract["known_bad_patterns"][0]["card_id"] == "EX1_003"
    assert contract["combos"][0]["cards"] == ["EX1_001", "EX1_002"]
    assert contract["confidence_label"] == "guide_backed"
    assert contract["aggression_profile"]["global_value_overlays"][
        "OppGlobalHeroHealth"
    ] == "increase"
    assert contract["aggression_profile"]["global_value_overlays"][
        "OppGlobalMinionIntrinsicValue"
    ] == "decrease"


def test_gameplan_contract_without_claims_is_generic_but_card_specific():
    deck_identity = {
        "deck_name": "Fixture",
        "cards": [{"card_id": "EX1_001", "count": 1}],
    }
    card_metadata = {"cards": [{"card_id": "EX1_001", "name": "One", "mechanic_families": []}]}

    contract = build_gameplan_contract(deck_identity, card_metadata)

    assert set(contract["cards"]) == {"EX1_001"}
    assert contract["cards"]["EX1_001"]["coverage_status"] == "generic_low_confidence"
    assert contract["confidence_label"] == "generic_low_confidence"


def test_gameplan_contract_suppresses_combo_claims_for_cards_outside_deck():
    deck_identity = {
        "deck_name": "Fixture",
        "cards": [{"card_id": "EX1_001", "count": 1}],
    }
    card_metadata = {"cards": [{"card_id": "EX1_001", "name": "One", "mechanic_families": []}]}
    source_claims = normalize_source_claims(
        [
            {
                "source": "guide",
                "claim": "Use One with Missing for a burst combo turn.",
                "cards": ["EX1_001", "MISSING_999"],
                "claim_type": "combo",
            }
        ]
    )

    contract = build_gameplan_contract(deck_identity, card_metadata, source_claims)

    assert contract["combos"] == []
    assert contract["combo_suppression_report"][0]["reason"] == "card_not_in_deck"


def test_gameplan_contract_preserves_combo_order_from_normalized_claims():
    deck_identity = {
        "deck_name": "Fixture",
        "cards": [{"card_id": "BBB_002", "count": 1}, {"card_id": "AAA_001", "count": 1}],
    }
    card_metadata = {
        "cards": [
            {"card_id": "BBB_002", "name": "Setup", "mechanic_families": []},
            {"card_id": "AAA_001", "name": "Payoff", "mechanic_families": []},
        ]
    }
    source_claims = normalize_source_claims(
        [
            {
                "source": "guide",
                "claim": "Play setup before payoff for the combo.",
                "cards": ["BBB_002", "AAA_001"],
                "claim_type": "combo",
            }
        ]
    )

    contract = build_gameplan_contract(deck_identity, card_metadata, source_claims)

    assert contract["combos"][0]["cards"] == ["BBB_002", "AAA_001"]


def test_gameplan_contract_turns_shadowform_semantics_into_hero_power_pressure():
    deck_identity = {
        "deck_name": "ShadowPriest",
        "cards": [{"card_id": "SW_448", "count": 1}],
    }
    card_metadata = {
        "cards": [
            {
                "card_id": "SW_448",
                "name": "Darkbishop Benedictus",
                "mechanic_families": ["minion"],
                "semantic_families": [
                    "minion",
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
                        "text": "Deal $2 damage.",
                    }
                ],
                "deckwide_effects": [
                    {
                        "effect": "replace_starting_hero_power",
                        "target_card_id": "EX1_625t",
                        "target_name": "Mind Spike",
                    }
                ],
            }
        ]
    }

    contract = build_gameplan_contract(deck_identity, card_metadata)

    darkbishop = contract["cards"]["SW_448"]
    assert darkbishop["confidence"] == "source_backed_static_semantics"
    assert "hero_power_transform" in darkbishop["roles"]
    assert "hero_power_pressure" in darkbishop["roles"]
    assert darkbishop["linked_entities"][0]["card_id"] == "EX1_625t"
    assert contract["deckwide_effects"][0]["effect"] == "replace_starting_hero_power"
    assert (
        contract["card_usage_expectations"]["SW_448"]["expected_use"]
        == "start_of_game_shadowform_enables_hero_power_pressure"
    )
    assert contract["aggression_profile"]["global_value_overlays"]["MyHeroPowerValue"] == "increase"
    assert "Mind Spike" in contract["aggression_profile"]["global_value_overlay_reasons"]["MyHeroPowerValue"]


def test_gameplan_contract_preserves_guide_backed_confidence_lane():
    deck_identity = {
        "deck_name": "Fixture Aggro",
        "cards": [{"card_id": "EX1_001", "count": 2}],
    }
    card_metadata = {"cards": [{"card_id": "EX1_001", "name": "One", "mechanic_families": []}]}
    source_claims = normalize_source_claims(
        [
            {
                "source": "guide",
                "claim": "Always keep One and push face damage early.",
                "cards": ["EX1_001"],
                "claim_kind": "mulligan_keep",
                "claim_type": "mulligan_and_gameplan",
                "claim_readiness": "guide_backed",
                "trust_ceiling": "runtime_candidate",
                "confidence": "guide_backed",
            }
        ]
    )

    contract = build_gameplan_contract(deck_identity, card_metadata, source_claims)

    assert contract["cards"]["EX1_001"]["coverage_status"] == "guide_backed"
    assert contract["cards"]["EX1_001"]["confidence"] == "guide_backed"
    assert contract["mulligan_anchors"][0]["confidence"] == "guide_backed"


def test_gameplan_contract_treats_guide_sources_as_guide_backed_without_explicit_confidence():
    deck_identity = {
        "deck_name": "Fixture Guide",
        "cards": [{"card_id": "EX1_001", "count": 2}],
    }
    card_metadata = {"cards": [{"card_id": "EX1_001", "name": "One", "mechanic_families": []}]}
    source_claims = normalize_source_claims(
        [
            {
                "source": "guide",
                "url": "https://example.invalid/deck-guide",
                "claim": "Always keep One and push face damage early.",
                "cards": ["EX1_001"],
                "claim_kind": "mulligan_keep",
                "claim_type": "mulligan_and_gameplan",
                "claim_readiness": "guide_backed",
                "trust_ceiling": "runtime_candidate",
            }
        ]
    )

    contract = build_gameplan_contract(deck_identity, card_metadata, source_claims)

    assert contract["cards"]["EX1_001"]["coverage_status"] == "guide_backed"
    assert contract["cards"]["EX1_001"]["confidence"] == "guide_backed"


def test_gameplan_contract_consumes_research_bundle_as_authority():
    deck_identity = {
        "deck_name": "Fixture",
        "cards": [{"card_id": "EX1_001", "count": 1}],
    }
    card_metadata = {"cards": [{"card_id": "EX1_001", "name": "One"}]}
    research_bundle = {
        "card_role_map": {
            "EX1_001": {
                "card_id": "EX1_001",
                "name": "One",
                "roles": ["deck_card", "pressure"],
                "semantic_families": [],
                "linked_entities": [],
                "confidence": "guide_backed",
                "source_claim_ids": ["claim_research"],
            }
        },
        "mulligan_anchor_map": {
            "EX1_001": {
                "card_id": "EX1_001",
                "intent": "hold",
                "condition": "*",
                "confidence": "guide_backed",
                "source_claim_ids": ["claim_research"],
            }
        },
        "card_usage_expectations": {
            "EX1_001": {
                "card_id": "EX1_001",
                "expected_use": "keep_and_pressure",
                "confidence": "guide_backed",
                "source_claim_ids": ["claim_research"],
            }
        },
        "known_bad_patterns": [
            {
                "card_id": "EX1_001",
                "claim_id": "claim_bad",
                "pattern": "Avoid playing One into removal.",
                "source_claim_ids": ["claim_bad"],
            }
        ],
        "globalvalue_intent": {
            "pressure_bias": "high",
            "overlays": {"OppGlobalHeroHealth": "increase"},
            "overlay_reasons": {"OppGlobalHeroHealth": "Research expects face pressure."},
        },
    }

    contract = build_gameplan_contract(
        deck_identity,
        card_metadata,
        {"claims": []},
        research_bundle=research_bundle,
    )

    card = contract["cards"]["EX1_001"]
    assert card["confidence"] == "guide_backed"
    assert "pressure" in card["roles"]
    assert card["source_claim_ids"] == ["claim_research"]
    assert contract["mulligan_anchors"][0]["source_claim_ids"] == ["claim_research"]
    assert contract["card_usage_expectations"]["EX1_001"]["expected_use"] == "keep_and_pressure"
    assert contract["known_bad_patterns"] == research_bundle["known_bad_patterns"]
    assert contract["aggression_profile"]["global_value_overlays"]["OppGlobalHeroHealth"] == (
        "increase"
    )
    assert contract["aggression_profile"]["global_value_overlays"]["GlobalMinionAttack"] == (
        "increase"
    )
    assert contract["aggression_profile"]["global_value_overlay_reasons"] == {
        "OppGlobalHeroHealth": "Research expects face pressure."
    }


def test_gameplan_contract_merges_research_and_mechanic_globalvalue_intent():
    deck_identity = {
        "deck_name": "Fixture Charge",
        "cards": [{"card_id": "EX1_CHARGE", "count": 1}],
    }
    card_metadata = {
        "cards": [
            {
                "card_id": "EX1_CHARGE",
                "name": "Charge One",
                "mechanic_families": ["charge", "damage"],
                "semantic_families": ["charge", "damage"],
            }
        ]
    }
    research_bundle = {
        "card_role_map": {
            "EX1_CHARGE": {
                "card_id": "EX1_CHARGE",
                "name": "Charge One",
                "roles": ["charge", "damage", "pressure"],
                "semantic_families": ["charge", "damage"],
                "linked_entities": [],
                "confidence": "source_backed",
                "source_claim_ids": [],
            }
        },
        "globalvalue_intent": {
            "pressure_bias": "high",
            "overlays": {"OppGlobalHeroHealth": "increase"},
            "overlay_reasons": {"OppGlobalHeroHealth": "Research expects face pressure."},
        },
    }

    contract = build_gameplan_contract(
        deck_identity,
        card_metadata,
        {"claims": []},
        research_bundle=research_bundle,
    )

    overlays = contract["aggression_profile"]["global_value_overlays"]
    assert overlays["OppGlobalHeroHealth"] == "increase"
    assert overlays["GlobalCharge"] == "increase"

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
                "claim_type": "mulligan_and_gameplan",
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
                "claim_type": "bad_pattern",
            },
        ]
    )

    contract = build_gameplan_contract(deck_identity, card_metadata, source_claims)

    assert contract["archetype"] == "aggressive_gameplan"
    assert contract["aggression_profile"]["speed"] == "aggro"
    assert set(contract["cards"]) == {"EX1_001", "EX1_002", "EX1_003"}
    assert contract["cards"]["EX1_001"]["coverage_status"] == "source_backed"
    assert contract["cards"]["EX1_001"]["roles"] == [
        "battlecry",
        "combo_piece",
        "mulligan_anchor",
        "pressure",
    ]
    assert contract["cards"]["EX1_003"]["coverage_status"] == "source_backed"
    assert contract["mulligan_anchors"][0]["card_id"] == "EX1_001"
    assert contract["card_usage_expectations"]["EX1_001"]["expected_use"] == "keep_and_pressure"
    assert contract["known_bad_patterns"][0]["card_id"] == "EX1_003"
    assert contract["combos"][0]["cards"] == ["EX1_001", "EX1_002"]
    assert contract["confidence_label"] == "source_backed"
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

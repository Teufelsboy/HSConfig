from hsconfig.card_metadata import (
    analysis_cards_from_deck_identity,
    assign_mechanic_families,
    hydrate_card_metadata,
)


def test_assign_mechanic_families_from_text_and_tags():
    card = {
        "card_id": "TEST",
        "mechanics": ["BATTLECRY"],
        "text": "Battlecry: Discover a spell.",
        "type": "MINION",
    }

    families = assign_mechanic_families(card)

    assert "battlecry" in families
    assert "discover" in families
    assert "minion" in families


def test_hydrate_card_metadata_uses_source_records():
    snapshot = hydrate_card_metadata(
        cards=[{"card_id": "CS2_235", "dbf_id": 1367, "count": 1}],
        source_records={
            "CS2_235": {
                "name": "Northshire Cleric",
                "cost": 1,
                "type": "MINION",
                "text": "Whenever a minion is healed, draw a card.",
            }
        },
    )

    card = snapshot["cards"][0]
    assert card["name"] == "Northshire Cleric"
    assert card["card_id"] == "CS2_235"
    assert {"draw", "heal", "minion"} <= set(card["mechanic_families"])


def test_hydrate_card_metadata_keeps_missing_records_visible():
    snapshot = hydrate_card_metadata(
        cards=[{"card_id": "MISSING_001", "dbf_id": 1, "count": 2}],
        source_records={},
    )

    card = snapshot["cards"][0]
    assert card["name"] == "MISSING_001"
    assert card["metadata_status"] == "missing_source_record"
    assert card["mechanic_families"] == []


def test_hydrate_card_metadata_preserves_referenced_tags_and_entourage():
    snapshot = hydrate_card_metadata(
        cards=[{"card_id": "SW_448", "dbf_id": 64443, "count": 1}],
        source_records={
            "SW_448": {
                "name": "Darkbishop Benedictus",
                "type": "MINION",
                "text": "Start of Game: enter Shadowform.",
                "referenced_tags": ["START_OF_GAME_KEYWORD"],
                "entourage": ["EX1_625t"],
            }
        },
    )

    card = snapshot["cards"][0]
    assert card["referenced_tags"] == ["START_OF_GAME_KEYWORD"]
    assert card["entourage"] == ["EX1_625t"]


def test_hydrate_card_metadata_adds_static_semantic_evidence():
    snapshot = hydrate_card_metadata(
        cards=[{"card_id": "TEST_001", "dbf_id": 1, "count": 1}],
        source_records={
            "TEST_001": {
                "name": "Test Dredge",
                "type": "SPELL",
                "text": "Dredge. Tradeable.",
                "mechanics": ["TRADEABLE"],
            }
        },
    )

    card = snapshot["cards"][0]

    assert "dredge" in card["mechanic_families"]
    assert "tradeable" in card["mechanic_families"]
    assert "dredge" in card["warning_only_mechanics"]
    assert any(row["family"] == "tradeable" for row in card["static_semantic_evidence"])


def test_analysis_cards_preserve_sideboard_zone_owner_and_runtime_boundary():
    cards = analysis_cards_from_deck_identity(
        {
            "cards": [
                {"card_id": "TOY_330", "dbf_id": 102983, "count": 1, "cost": 0},
                {"card_id": "MAIN_001", "dbf_id": 1, "count": 2, "cost": 1},
            ],
            "sideboards": [
                {
                    "owner_card_id": "TOY_330",
                    "cards": [
                        {"card_id": "TOY_330t95", "dbf_id": 104947, "count": 1},
                        {"card_id": "TOY_330t98", "dbf_id": 104950, "count": 1},
                        {"card_id": "TOY_330t11", "dbf_id": 110446, "count": 1},
                    ],
                }
            ],
        }
    )

    by_card = {card["card_id"]: card for card in cards}
    assert by_card["MAIN_001"]["deck_zone"] == "main"
    assert by_card["MAIN_001"]["runtime_eligible"] is True
    assert by_card["TOY_330"]["analysis_roles"] == [
        "deckbuilding_modifier",
        "sideboard_owner",
    ]
    for card_id in {"TOY_330t95", "TOY_330t98", "TOY_330t11"}:
        assert by_card[card_id]["deck_zone"] == "sideboard"
        assert by_card[card_id]["sideboard_owner_card_id"] == "TOY_330"
        assert by_card[card_id]["runtime_eligible"] is False


def test_hydrate_card_metadata_carries_analysis_annotations():
    snapshot = hydrate_card_metadata(
        cards=[
            {
                "card_id": "TOY_330t95",
                "dbf_id": 104947,
                "count": 1,
                "name": "Virus Module",
                "deck_zone": "sideboard",
                "sideboard_owner_card_id": "TOY_330",
                "runtime_eligible": False,
            }
        ],
        source_records={},
    )

    card = snapshot["cards"][0]
    assert card["name"] == "Virus Module"
    assert card["deck_zone"] == "sideboard"
    assert card["sideboard_owner_card_id"] == "TOY_330"
    assert card["runtime_eligible"] is False

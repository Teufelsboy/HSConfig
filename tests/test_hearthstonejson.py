import json
from pathlib import Path

from hsconfig.hearthstonejson import (
    HEARTHSTONEJSON_LATEST_ENUS_CARDS_URL,
    index_cards_by_id,
    load_cards_json,
    normalize_card_row,
)


FIXTURE = Path("tests/fixtures/hearthstonejson_shadowpriest_cards.json")


def test_load_cards_json_reads_fixture_rows():
    cards = load_cards_json(FIXTURE)

    assert {card["id"] for card in cards} == {
        "SW_448",
        "EX1_625t",
        "BOM_05_Xyrella_006p2",
    }


def test_normalize_card_row_preserves_semantic_fields():
    row = normalize_card_row(
        {
            "id": "SW_448",
            "dbfId": 64443,
            "name": "Darkbishop Benedictus",
            "type": "MINION",
            "cardClass": "PRIEST",
            "text": "enter Shadowform",
            "referencedTags": ["START_OF_GAME_KEYWORD"],
        }
    )

    assert row == {
        "id": "SW_448",
        "dbf_id": 64443,
        "name": "Darkbishop Benedictus",
        "type": "MINION",
        "card_class": "PRIEST",
        "classes": [],
        "collectible": False,
        "cost": None,
        "attack": None,
        "health": None,
        "durability": None,
        "text": "enter Shadowform",
        "mechanics": [],
        "referenced_tags": ["START_OF_GAME_KEYWORD"],
        "spell_school": "",
        "race": None,
        "races": [],
        "overload": None,
        "spell_damage": None,
        "targeting_arrow_text": "",
        "hero_power_dbf_id": None,
        "quest_reward": None,
        "play_requirements": {},
        "entourage": [],
    }


def test_normalize_card_row_preserves_static_semantic_fields():
    row = normalize_card_row(
        {
            "id": "TEST_001",
            "dbfId": 1001,
            "name": "Test Weapon",
            "type": "WEAPON",
            "cardClass": "WARRIOR",
            "classes": ["WARRIOR", "ROGUE"],
            "cost": 3,
            "attack": 4,
            "health": 0,
            "durability": 2,
            "collectible": True,
            "text": "Tradeable. Overload: (1).",
            "mechanics": ["TRADEABLE"],
            "referencedTags": ["OVERLOAD"],
            "spellSchool": "FIRE",
            "race": "MECHANICAL",
            "races": ["MECHANICAL"],
            "overload": 1,
            "spellDamage": 2,
            "targetingArrowText": "Deal damage.",
            "heroPowerDbfId": 479,
            "entourage": ["TEST_001t"],
        }
    )

    assert row["collectible"] is True
    assert row["attack"] == 4
    assert row["health"] == 0
    assert row["durability"] == 2
    assert row["classes"] == ["WARRIOR", "ROGUE"]
    assert row["spell_school"] == "FIRE"
    assert row["race"] == "MECHANICAL"
    assert row["races"] == ["MECHANICAL"]
    assert row["overload"] == 1
    assert row["spell_damage"] == 2
    assert row["targeting_arrow_text"] == "Deal damage."


def test_normalize_card_row_preserves_identity_link_fields():
    row = normalize_card_row(
        {
            "id": "HERO_09",
            "dbfId": 637,
            "name": "Anduin",
            "type": "HERO",
            "heroPowerDbfId": 479,
            "questReward": "QUEST_REWARD_CARD",
            "playRequirements": {"REQ_TARGET_TO_PLAY": 0},
            "entourage": ["TOKEN_001"],
        }
    )

    assert row["hero_power_dbf_id"] == 479
    assert row["quest_reward"] == "QUEST_REWARD_CARD"
    assert row["play_requirements"] == {"REQ_TARGET_TO_PLAY": 0}
    assert row["entourage"] == ["TOKEN_001"]


def test_index_cards_by_id_supports_id_and_dbf_lookup():
    cards = [normalize_card_row(row) for row in json.loads(FIXTURE.read_text(encoding="utf-8"))]
    index = index_cards_by_id(cards)

    assert index["SW_448"]["name"] == "Darkbishop Benedictus"
    assert index["64443"]["id"] == "SW_448"
    assert index["EX1_625t"]["type"] == "HERO_POWER"


def test_index_cards_by_id_normalizes_raw_hearthstonejson_rows():
    cards = json.loads(FIXTURE.read_text(encoding="utf-8"))

    index = index_cards_by_id(cards)

    assert index["64443"]["id"] == "SW_448"
    assert index["SW_448"]["referenced_tags"] == ["START_OF_GAME_KEYWORD"]


def test_latest_url_points_to_hearthstonejson_latest_cards():
    assert HEARTHSTONEJSON_LATEST_ENUS_CARDS_URL == (
        "https://api.hearthstonejson.com/v1/latest/enUS/cards.json"
    )

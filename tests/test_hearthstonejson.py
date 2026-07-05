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
        "cost": None,
        "text": "enter Shadowform",
        "mechanics": [],
        "referenced_tags": ["START_OF_GAME_KEYWORD"],
        "entourage": [],
    }


def test_index_cards_by_id_supports_id_and_dbf_lookup():
    cards = [normalize_card_row(row) for row in json.loads(FIXTURE.read_text(encoding="utf-8"))]
    index = index_cards_by_id(cards)

    assert index["SW_448"]["name"] == "Darkbishop Benedictus"
    assert index["64443"]["id"] == "SW_448"
    assert index["EX1_625t"]["type"] == "HERO_POWER"


def test_latest_url_points_to_hearthstonejson_latest_cards():
    assert HEARTHSTONEJSON_LATEST_ENUS_CARDS_URL == (
        "https://api.hearthstonejson.com/v1/latest/enUS/cards.json"
    )

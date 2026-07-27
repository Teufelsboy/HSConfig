from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from hearthstone.deckstrings import Deck, FormatType
from hsconfig.deck_identity import build_deck_identity
from hsconfig.deck_input_verification import verify_deck_input
from hsconfig.deckstring_decode import decode_deck_code
from hsconfig.io import read_json, write_json


VERIFIED_TEST_DECK_CODE = "AAEBAa0GAAGhBAAA"
VERIFIED_TEST_CARDS = [
    {
        "card_id": "DS1_233",
        "dbf_id": 545,
        "count": 2,
        "name": "Mind Blast",
    }
]
VERIFIED_FIXTURE_CARDS = [
    {
        "card_id": "DS1_233",
        "dbf_id": 545,
        "count": 2,
        "name": "Fixture Card A",
    },
    {
        "card_id": "CS2_172",
        "dbf_id": 216,
        "count": 2,
        "name": "Fixture Card B",
    },
    {
        "card_id": "CS2_182",
        "dbf_id": 90,
        "count": 2,
        "name": "Fixture Card C",
    },
    {
        "card_id": "CS2_189",
        "dbf_id": 389,
        "count": 1,
        "name": "Fixture Card D",
    },
]
VERIFIED_SYNTHETIC_CARDS = [
    {
        "card_id": "UNRESOLVED_DBF_900001",
        "dbf_id": 900001,
        "count": 2,
        "name": "Synthetic Fixture Card A",
    },
    {
        "card_id": "UNRESOLVED_DBF_900002",
        "dbf_id": 900002,
        "count": 2,
        "name": "Synthetic Fixture Card B",
    },
    {
        "card_id": "UNRESOLVED_DBF_900003",
        "dbf_id": 900003,
        "count": 2,
        "name": "Synthetic Fixture Card C",
    },
    {
        "card_id": "UNRESOLVED_DBF_900004",
        "dbf_id": 900004,
        "count": 1,
        "name": "Synthetic Fixture Card D",
    },
]
VERIFIED_CARD_DBF_IDS = {
    "EX1_001": 1655,
    "EX1_002": 1656,
    "EX1_004": 1634,
    "EX1_005": 1657,
    "EX1_006": 1658,
    "EX1_007": 1659,
    "REV_290": 82310,
}


def deck_code_for_cards(cards: Sequence[Mapping[str, Any]]) -> str:
    deck = Deck()
    deck.cards = [
        (int(card["dbf_id"]), int(card.get("count", 1)))
        for card in cards
    ]
    deck.heroes = [813]
    deck.format = FormatType.FT_WILD
    return deck.as_deckstring


def verified_roster_for_card_ids(
    card_ids: Sequence[str],
    *,
    count: int = 1,
) -> list[dict[str, Any]]:
    return [
        {
            "card_id": card_id,
            "dbf_id": VERIFIED_CARD_DBF_IDS[card_id],
            "count": count,
            "name": f"Fixture {card_id}",
        }
        for card_id in card_ids
    ]


def remap_card_ids(value: Any, mapping: Mapping[str, str]) -> Any:
    if isinstance(value, str):
        remapped = value
        for old_card_id, new_card_id in mapping.items():
            remapped = remapped.replace(old_card_id, new_card_id)
        return remapped
    if isinstance(value, list):
        return [remap_card_ids(item, mapping) for item in value]
    if isinstance(value, dict):
        return {
            key: remap_card_ids(item, mapping)
            for key, item in value.items()
        }
    return value


def install_verified_deck_input(
    package: Path,
    *,
    deck_name: str = "deck",
) -> dict[str, Any]:
    reports = package / "reports"
    manifest_path = reports / "input_manifest.json"
    manifest = read_json(manifest_path) if manifest_path.is_file() else {}
    verdict = verify_deck_input(
        deck_code=VERIFIED_TEST_DECK_CODE,
        cards=VERIFIED_TEST_CARDS,
        source="cards_json",
    )
    write_json(
        manifest_path,
        {
            **manifest,
            "deck_name": deck_name,
            "deck_code": VERIFIED_TEST_DECK_CODE,
            "card_source": "cards_json",
            "deck_input_verification": verdict,
        },
    )
    identity = build_deck_identity(
        deck_name=deck_name,
        deck_code=VERIFIED_TEST_DECK_CODE,
        cards=VERIFIED_TEST_CARDS,
    )
    write_json(reports / "deck_identity.json", identity)
    write_json(
        reports / "deck_fingerprint.json",
        {"deck_fingerprint": identity["deck_fingerprint"]},
    )
    return verdict


def install_verified_deckstring_input(
    package: Path,
    *,
    deck_name: str,
    deck_code: str,
) -> dict[str, Any]:
    reports = package / "reports"
    manifest_path = reports / "input_manifest.json"
    manifest = read_json(manifest_path) if manifest_path.is_file() else {}
    cards = decode_deck_code(deck_code)["cards"]
    verdict = verify_deck_input(
        deck_code=deck_code,
        cards=cards,
        source="deckstring",
    )
    write_json(
        manifest_path,
        {
            **manifest,
            "deck_name": deck_name,
            "deck_code": deck_code,
            "card_source": "deckstring",
            "deck_input_verification": verdict,
        },
    )
    identity = build_deck_identity(
        deck_name=deck_name,
        deck_code=deck_code,
        cards=cards,
    )
    write_json(reports / "deck_identity.json", identity)
    write_json(
        reports / "deck_fingerprint.json",
        {"deck_fingerprint": identity["deck_fingerprint"]},
    )
    return verdict

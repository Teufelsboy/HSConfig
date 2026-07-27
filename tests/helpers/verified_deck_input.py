from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from hearthstone.deckstrings import Deck, FormatType
from hsconfig.deck_identity import build_deck_identity
from hsconfig.deck_input_verification import verify_deck_input
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


def deck_code_for_cards(cards: Sequence[Mapping[str, Any]]) -> str:
    deck = Deck()
    deck.cards = [
        (int(card["dbf_id"]), int(card.get("count", 1)))
        for card in cards
    ]
    deck.heroes = [813]
    deck.format = FormatType.FT_WILD
    return deck.as_deckstring


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

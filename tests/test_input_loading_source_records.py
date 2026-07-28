import pytest

from hsconfig.card_metadata import (
    analysis_cards_from_deck_identity,
    hydrate_card_metadata,
)
from hsconfig.deck_identity import build_deck_identity
from hsconfig.input_loading import source_records_from_cards


def test_source_records_from_cards_excludes_deckstring_identity_only_rows():
    records = source_records_from_cards(
        [
            {
                "card_id": "IDENTITY_ONLY",
                "name": "Secret Identity",
                "cost": 3,
                "type": "SPELL",
                "text": "Secret: When your opponent plays a card, draw a card.",
                "mechanics": ["secret"],
                "card_class": "MAGE",
                "deckstring_identity_only": True,
            },
            {
                "card_id": "REAL_SOURCE",
                "name": "Ordinary Source Record",
                "cost": 3,
                "type": "MINION",
                "text": "Battlecry: Gain Armor.",
                "mechanics": ["battlecry"],
                "card_class": "WARRIOR",
            },
        ]
    )

    assert records == {
        "REAL_SOURCE": {
            "name": "Ordinary Source Record",
            "cost": 3,
            "type": "MINION",
            "text": "Battlecry: Gain Armor.",
            "mechanics": ["battlecry"],
            "card_class": "WARRIOR",
        }
    }


@pytest.mark.parametrize("deck_zone", ["main", "sideboard"])
def test_identity_only_provenance_survives_normalization_without_semantics(
    deck_zone,
):
    identity_only_card = {
        "card_id": "IDENTITY_ONLY",
        "dbf_id": 424242,
        "count": 1,
        "name": "Secret Identity",
        "cost": 3,
        "type": "SPELL",
        "card_class": "MAGE",
        "text": "Secret: When your opponent plays a card, draw a card.",
        "mechanics": ["secret"],
        "metadata_status": "source_record",
        "deckstring_identity_only": True,
    }
    cards = [identity_only_card] if deck_zone == "main" else [
        {"card_id": "SIDEBOARD_OWNER", "dbf_id": 434343, "count": 1}
    ]
    sideboards = [] if deck_zone == "main" else [
        {
            "sideboard_index": 1,
            "owner_dbf_id": 434343,
            "owner_card_id": "SIDEBOARD_OWNER",
            "cards": [identity_only_card],
        }
    ]
    deck_identity = build_deck_identity(
        deck_name="Identity Boundary",
        deck_code="test-code",
        cards=cards,
        sideboards=sideboards,
    )

    analysis_cards = analysis_cards_from_deck_identity(deck_identity)
    normalized = next(
        card for card in analysis_cards if card["card_id"] == "IDENTITY_ONLY"
    )
    records = source_records_from_cards(analysis_cards)
    hydrated = hydrate_card_metadata(
        cards=analysis_cards,
        source_records=records,
    )
    hydrated_identity = next(
        card for card in hydrated["cards"] if card["card_id"] == "IDENTITY_ONLY"
    )

    assert normalized["deckstring_identity_only"] is True
    assert records == {}
    assert hydrated_identity["metadata_status"] == "missing_source_record"
    assert hydrated_identity["source_record_key"] is None
    assert {"secret", "secret_timing"}.isdisjoint(
        hydrated_identity["mechanic_families"]
    )

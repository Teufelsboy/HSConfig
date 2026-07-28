from hsconfig.input_loading import source_records_from_cards


def test_source_records_from_cards_excludes_deckstring_identity_only_rows():
    records = source_records_from_cards(
        [
            {
                "card_id": "IDENTITY_ONLY",
                "name": "Plausible Card Name",
                "cost": 2,
                "type": "MINION",
                "text": "Battlecry: Draw a card.",
                "mechanics": ["battlecry"],
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

from pathlib import Path

from hsconfig.hearthstonejson import load_cards_json
from hsconfig.semantic_enrichment import enrich_card_metadata


FIXTURE = Path("tests/fixtures/hearthstonejson_shadowpriest_cards.json")


def test_enrich_darkbishop_links_shadowform_and_mind_spike():
    card_metadata = {
        "cards": [
            {
                "card_id": "SW_448",
                "dbf_id": 64443,
                "name": "Darkbishop Benedictus",
                "type": "MINION",
                "text": "<b>Start of Game:</b> If the spells in your deck are all Shadow, enter Shadowform.",
                "mechanic_families": ["minion"],
                "metadata_status": "source_record",
            }
        ]
    }

    enriched = enrich_card_metadata(
        card_metadata,
        hearthstonejson_cards=load_cards_json(FIXTURE),
    )

    card = enriched["cards"][0]
    assert "start_of_game" in card["semantic_families"]
    assert "shadowform" in card["semantic_families"]
    assert "hero_power_transform" in card["semantic_families"]
    assert "hero_power_pressure" in card["semantic_families"]
    assert card["linked_entities"][0]["card_id"] == "EX1_625t"
    assert card["linked_entities"][0]["type"] == "HERO_POWER"
    assert enriched["deckwide_effects"][0]["effect"] == "replace_starting_hero_power"


def test_enrichment_uses_fallback_mind_spike_when_json_rows_are_missing():
    card_metadata = {
        "cards": [
            {
                "card_id": "SW_448",
                "dbf_id": 64443,
                "name": "Darkbishop Benedictus",
                "type": "MINION",
                "text": "Start of Game: enter Shadowform.",
                "mechanic_families": ["minion"],
                "metadata_status": "source_record",
            }
        ]
    }

    enriched = enrich_card_metadata(card_metadata, hearthstonejson_cards=[])

    card = enriched["cards"][0]
    assert card["linked_entities"][0]["card_id"] == "EX1_625t"
    assert enriched["semantic_enrichment_status"] == "partial"
    assert enriched["semantic_enrichment_warnings"]


def test_non_shadowform_cards_keep_existing_mechanic_families():
    card_metadata = {
        "cards": [
            {
                "card_id": "EX1_001",
                "name": "Example",
                "mechanic_families": ["battlecry"],
                "metadata_status": "source_record",
            }
        ]
    }

    enriched = enrich_card_metadata(card_metadata, hearthstonejson_cards=[])

    assert enriched["cards"][0]["semantic_families"] == ["battlecry"]
    assert enriched["deckwide_effects"] == []

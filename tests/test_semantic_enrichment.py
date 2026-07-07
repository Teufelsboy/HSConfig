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
    assert card["linked_entities"][0]["source"] == "curated_linked_entity_supplement"
    assert enriched["deckwide_effects"][0]["effect"] == "replace_starting_hero_power"


def test_enrichment_adds_direct_hjson_linked_entities_from_hero_power_dbf_id():
    card_metadata = {
        "cards": [
            {
                "card_id": "HERO_09",
                "dbf_id": 637,
                "name": "Anduin",
                "type": "HERO",
                "mechanic_families": [],
                "metadata_status": "source_record",
            }
        ]
    }

    enriched = enrich_card_metadata(
        card_metadata,
        hearthstonejson_cards=[
            {
                "id": "HERO_09",
                "dbfId": 637,
                "name": "Anduin",
                "type": "HERO",
                "heroPowerDbfId": 479,
            },
            {
                "id": "CS1h_001",
                "dbfId": 479,
                "name": "Lesser Heal",
                "type": "HERO_POWER",
            },
        ],
    )

    card = enriched["cards"][0]
    assert card["hero_power_dbf_id"] == 479
    assert card["linked_entities"] == [
        {
            "link_kind": "starting_hero_power",
            "card_id": "CS1h_001",
            "dbf_id": 479,
            "name": "Lesser Heal",
            "type": "HERO_POWER",
            "source": "hearthstonejson.heroPowerDbfId",
        }
    ]


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
    assert enriched["semantic_enrichment_status"] == "complete"
    assert enriched["semantic_enrichment_warnings"] == []


def test_enrichment_hydrates_sparse_darkbishop_from_hearthstonejson():
    card_metadata = {
        "cards": [
            {
                "card_id": "SW_448",
                "dbf_id": 64443,
                "name": "SW_448",
                "type": "UNKNOWN",
                "text": "",
                "mechanic_families": [],
                "metadata_status": "source_record",
            }
        ]
    }

    enriched = enrich_card_metadata(
        card_metadata,
        hearthstonejson_cards=load_cards_json(FIXTURE),
    )

    card = enriched["cards"][0]
    assert card["name"] == "Darkbishop Benedictus"
    assert card["type"] == "MINION"
    assert "shadowform" in card["semantic_families"]
    assert "hero_power_transform" in card["semantic_families"]
    assert enriched["deckwide_effects"][0]["target_name"] == "Mind Spike"


def test_shadowform_spell_does_not_replace_starting_hero_power():
    card_metadata = {
        "cards": [
            {
                "card_id": "EX1_625",
                "name": "Shadowform",
                "type": "SPELL",
                "text": "Enter Shadowform. Your Hero Power becomes 'Deal 2 damage.'",
                "mechanic_families": ["spell"],
                "metadata_status": "source_record",
            }
        ]
    }

    enriched = enrich_card_metadata(card_metadata, hearthstonejson_cards=[])

    card = enriched["cards"][0]
    assert "shadowform" in card["semantic_families"]
    assert "hero_power_transform" not in card["semantic_families"]
    assert enriched["deckwide_effects"] == []


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


def test_shadowpriest_hero_power_transform_uses_curated_supplement_before_builtin_warning():
    report = enrich_card_metadata(
        {
            "cards": [
                {
                    "card_id": "SW_448",
                    "dbf_id": 101,
                    "name": "Darkbishop Benedictus",
                    "type": "MINION",
                    "text": "At the start of the game, if the spells in your deck are all Shadow, enter Shadowform.",
                    "referenced_tags": ["START_OF_GAME_KEYWORD"],
                }
            ]
        },
        hearthstonejson_cards=[],
    )

    effect = report["deckwide_effects"][0]
    assert effect["source_card_id"] == "SW_448"
    assert effect["target_card_id"] == "EX1_625t"
    assert report["semantic_enrichment_warnings"] == []
    assert report["cards"][0]["linked_entities"][0]["source"] == "curated_linked_entity_supplement"

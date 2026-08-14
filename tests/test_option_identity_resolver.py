from hsconfig.option_identity_resolver import resolve_linked_entities


def test_resolve_linked_entities_from_static_identity_fields():
    cards = [
        {
            "id": "HERO_09",
            "hero_power_dbf_id": 479,
            "quest_reward": "QUEST_REWARD_CARD",
            "entourage": ["TOKEN_001", "MISSING_TOKEN"],
        }
    ]
    index = {
        "479": {
            "id": "CS1h_001",
            "dbf_id": 479,
            "name": "Lesser Heal",
            "type": "HERO_POWER",
        },
        "QUEST_REWARD_CARD": {
            "id": "QUEST_REWARD_CARD",
            "dbf_id": 111,
            "name": "Quest Reward",
            "type": "SPELL",
        },
        "TOKEN_001": {
            "id": "TOKEN_001",
            "dbf_id": 222,
            "name": "Generated Token",
            "type": "MINION",
        },
    }

    links = resolve_linked_entities(cards, index)

    assert [row["link_kind"] for row in links["HERO_09"]] == [
        "starting_hero_power",
        "quest_reward",
        "entourage",
    ]
    assert links["HERO_09"][0]["card_id"] == "CS1h_001"
    assert links["HERO_09"][0]["source"] == "hearthstonejson.heroPowerDbfId"


def test_curated_supplement_adds_missing_link_source_last():
    cards = [{"id": "CARD_PARENT", "name": "Parent"}]
    index = {
        "CARD_CHILD": {
            "id": "CARD_CHILD",
            "dbf_id": 101,
            "name": "Child",
            "type": "SPELL",
        }
    }
    supplement = {
        "CARD_PARENT": [
            {
                "link_kind": "option_identity",
                "card_id": "CARD_CHILD",
                "dbf_id": 101,
                "name": "Child",
                "type": "SPELL",
                "source": "curated_linked_entity_supplement",
            }
        ]
    }

    links = resolve_linked_entities(cards, index, supplement_links=supplement)

    assert links["CARD_PARENT"] == [
        {
            "link_kind": "option_identity",
            "card_id": "CARD_CHILD",
            "dbf_id": 101,
            "name": "Child",
            "type": "SPELL",
            "source": "curated_linked_entity_supplement",
        }
    ]


def test_upstream_link_wins_over_curated_duplicate():
    cards = [{"id": "CARD_PARENT", "entourage": ["CARD_CHILD"]}]
    index = {
        "CARD_CHILD": {
            "id": "CARD_CHILD",
            "dbf_id": 101,
            "name": "Child",
            "type": "SPELL",
        }
    }
    supplement = {
        "CARD_PARENT": [
            {
                "link_kind": "entourage",
                "card_id": "CARD_CHILD",
                "dbf_id": 101,
                "name": "Child",
                "type": "SPELL",
                "source": "curated_linked_entity_supplement",
            }
        ]
    }

    links = resolve_linked_entities(cards, index, supplement_links=supplement)

    assert links["CARD_PARENT"] == [
        {
            "link_kind": "entourage",
            "card_id": "CARD_CHILD",
            "dbf_id": 101,
            "name": "Child",
            "type": "SPELL",
            "source": "hearthstonejson.entourage",
        }
    ]

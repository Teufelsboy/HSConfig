import io

from hsconfig import hearthstonejson
from hsconfig.card_data_intake import build_card_data_context


def test_card_data_context_gates_deck_cards_with_collectible_feed():
    deck_cards = [{"card_id": "EX1_001", "dbf_id": 1, "count": 2}]
    collectible = [
        {
            "id": "EX1_001",
            "dbf_id": 1,
            "name": "Deck Card",
            "type": "MINION",
            "text": "Battlecry: do something.",
            "mechanics": ["BATTLECRY"],
            "referenced_tags": [],
            "entourage": [],
            "hero_power_dbf_id": None,
        }
    ]
    full = []

    context = build_card_data_context(
        deck_cards=deck_cards,
        collectible_cards=collectible,
        full_cards=full,
    )

    assert context["deck_source_records"]["EX1_001"]["name"] == "Deck Card"
    assert context["card_data_intake_report"]["summary"]["matched_deck_cards"] == 1
    assert context["card_data_intake_report"]["summary"]["missing_deck_cards"] == 0


def test_card_data_context_enriches_referenced_companions_from_full_feed():
    deck_cards = [{"card_id": "HERO_01", "dbf_id": 10, "count": 1}]
    collectible = [
        {
            "id": "HERO_01",
            "dbf_id": 10,
            "name": "Hero",
            "type": "HERO",
            "text": "",
            "mechanics": [],
            "referenced_tags": [],
            "entourage": ["TOKEN_01"],
            "hero_power_dbf_id": 20,
        }
    ]
    full = [
        {
            "id": "HP_01",
            "dbf_id": 20,
            "name": "Hero Power",
            "type": "HERO_POWER",
            "text": "Deal 2 damage.",
            "mechanics": [],
            "referenced_tags": [],
            "entourage": [],
            "hero_power_dbf_id": None,
        },
        {
            "id": "TOKEN_01",
            "dbf_id": 30,
            "name": "Generated Token",
            "type": "MINION",
            "text": "Generated helper.",
            "mechanics": [],
            "referenced_tags": [],
            "entourage": [],
            "hero_power_dbf_id": None,
        },
    ]

    context = build_card_data_context(
        deck_cards=deck_cards,
        collectible_cards=collectible,
        full_cards=full,
    )

    companions = context["companion_source_records"]
    assert companions["HP_01"]["type"] == "HERO_POWER"
    assert companions["TOKEN_01"]["name"] == "Generated Token"
    assert context["card_data_intake_report"]["summary"]["companion_records"] == 2


def test_card_data_context_enriches_child_id_companions_from_full_feed():
    deck_cards = [{"card_id": "PARENT_01", "dbf_id": 100, "count": 1}]
    collectible = [
        {
            "id": "PARENT_01",
            "dbf_id": 100,
            "name": "Parent Card",
            "type": "SPELL",
            "text": "Creates a helper.",
            "mechanics": [],
            "referenced_tags": [],
            "entourage": [],
            "childIds": ["CHILD_01"],
            "hero_power_dbf_id": None,
        }
    ]
    full = [
        {
            "id": "CHILD_01",
            "dbf_id": 101,
            "name": "Child Token",
            "type": "MINION",
            "text": "Created helper.",
            "mechanics": [],
            "referenced_tags": [],
            "entourage": [],
            "hero_power_dbf_id": None,
        }
    ]

    context = build_card_data_context(
        deck_cards=deck_cards,
        collectible_cards=collectible,
        full_cards=full,
    )

    assert context["deck_source_records"]["PARENT_01"]["child_ids"] == ["CHILD_01"]
    assert context["companion_source_records"]["CHILD_01"]["name"] == "Child Token"
    assert context["card_data_intake_report"]["summary"]["companion_records"] == 1
    assert context["card_data_intake_report"]["summary"]["missing_companion_records"] == 0


def test_card_data_context_keeps_missing_companions_non_blocking():
    deck_cards = [{"card_id": "HERO_01", "dbf_id": 10, "count": 1}]
    collectible = [
        {
            "id": "HERO_01",
            "dbf_id": 10,
            "name": "Hero",
            "type": "HERO",
            "text": "",
            "mechanics": [],
            "referenced_tags": [],
            "entourage": ["MISSING_TOKEN"],
            "hero_power_dbf_id": 999,
        }
    ]

    context = build_card_data_context(
        deck_cards=deck_cards,
        collectible_cards=collectible,
        full_cards=[],
    )

    report = context["card_data_intake_report"]
    assert report["non_blocking"] is True
    assert report["summary"]["missing_companion_records"] == 2
    assert report["warnings"][0]["reason"] in {
        "missing_companion_card",
        "missing_companion_dbf_id",
    }


def test_card_data_context_keeps_missing_child_id_companions_non_blocking():
    deck_cards = [{"card_id": "PARENT_01", "dbf_id": 100, "count": 1}]
    collectible = [
        {
            "id": "PARENT_01",
            "dbf_id": 100,
            "name": "Parent Card",
            "type": "SPELL",
            "text": "Creates a helper.",
            "mechanics": [],
            "referenced_tags": [],
            "entourage": [],
            "child_ids": ["MISSING_CHILD"],
            "hero_power_dbf_id": None,
        }
    ]

    context = build_card_data_context(
        deck_cards=deck_cards,
        collectible_cards=collectible,
        full_cards=[],
    )

    report = context["card_data_intake_report"]
    assert report["non_blocking"] is True
    assert report["summary"]["missing_companion_records"] == 1
    assert {
        "reason": "missing_companion_card",
        "card_id": "MISSING_CHILD",
    } in report["warnings"]


def test_fetch_latest_collectible_cards_uses_collectible_feed(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["user_agent"] = request.headers["User-agent"]
        captured["timeout"] = timeout
        return io.StringIO(
            '[{"id": "EX1_001", "dbfId": 1, "name": "Deck Card", "type": "MINION"}]'
        )

    monkeypatch.setattr(hearthstonejson, "urlopen", fake_urlopen)

    cards = hearthstonejson.fetch_latest_collectible_cards(timeout=3.5)

    assert hearthstonejson.HEARTHSTONEJSON_LATEST_ENUS_COLLECTIBLE_CARDS_URL == (
        "https://api.hearthstonejson.com/v1/latest/enUS/cards.collectible.json"
    )
    assert captured == {
        "url": "https://api.hearthstonejson.com/v1/latest/enUS/cards.collectible.json",
        "user_agent": "HSConfig/0.1 semantic-enrichment",
        "timeout": 3.5,
    }
    assert cards[0]["id"] == "EX1_001"
    assert cards[0]["dbf_id"] == 1

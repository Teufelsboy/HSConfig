from __future__ import annotations

from typing import Any


def resolve_linked_entities(
    cards: list[dict[str, Any]],
    card_index: dict[str, dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    links: dict[str, list[dict[str, Any]]] = {}
    for card in cards:
        card_id = str(card.get("id") or card.get("card_id") or "")
        rows: list[dict[str, Any]] = []
        hero_power_dbf_id = card.get("hero_power_dbf_id")
        if hero_power_dbf_id is not None and str(hero_power_dbf_id) in card_index:
            target = card_index[str(hero_power_dbf_id)]
            rows.append(_link("starting_hero_power", target, "hearthstonejson.heroPowerDbfId"))
        quest_reward = card.get("quest_reward")
        if quest_reward and str(quest_reward) in card_index:
            rows.append(_link("quest_reward", card_index[str(quest_reward)], "hearthstonejson.questReward"))
        for entourage_id in card.get("entourage", []) or []:
            if str(entourage_id) in card_index:
                rows.append(_link("entourage", card_index[str(entourage_id)], "hearthstonejson.entourage"))
        if card_id and rows:
            links[card_id] = rows
    return links


def _link(kind: str, target: dict[str, Any], source: str) -> dict[str, Any]:
    return {
        "link_kind": kind,
        "card_id": str(target.get("id") or target.get("card_id")),
        "dbf_id": target.get("dbf_id"),
        "name": str(target.get("name", target.get("id", ""))),
        "type": str(target.get("type", "UNKNOWN")),
        "source": source,
    }

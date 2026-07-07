from __future__ import annotations

from typing import Any


CURATED_LINKED_ENTITIES: dict[str, list[dict[str, Any]]] = {
    "SW_448": [
        {
            "link_kind": "hero_power_transform",
            "card_id": "EX1_625t",
            "dbf_id": 1622,
            "name": "Mind Spike",
            "type": "HERO_POWER",
            "source": "curated_linked_entity_supplement",
            "reason": (
                "Darkbishop Benedictus enters Shadowform at start of game, replacing the "
                "starting Hero Power with Mind Spike."
            ),
        }
    ],
    "EX1_625": [
        {
            "link_kind": "hero_power_transform",
            "card_id": "EX1_625t",
            "dbf_id": 1622,
            "name": "Mind Spike",
            "type": "HERO_POWER",
            "source": "curated_linked_entity_supplement",
            "reason": "Shadowform changes the Priest Hero Power to Mind Spike.",
        }
    ],
}


def curated_links_for(card_id: str) -> list[dict[str, Any]]:
    return [dict(row) for row in CURATED_LINKED_ENTITIES.get(str(card_id), [])]


def curated_link_map_for(card_ids: list[str] | set[str] | tuple[str, ...]) -> dict[str, list[dict[str, Any]]]:
    return {
        str(card_id): curated_links_for(str(card_id))
        for card_id in card_ids
        if curated_links_for(str(card_id))
    }

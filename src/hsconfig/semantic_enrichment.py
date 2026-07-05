from __future__ import annotations

import re
from typing import Any

from hsconfig.hearthstonejson import index_cards_by_id


MIND_SPIKE_FALLBACK = {
    "card_id": "EX1_625t",
    "dbf_id": 1622,
    "name": "Mind Spike",
    "type": "HERO_POWER",
    "card_class": "PRIEST",
    "text": "Deal $2 damage.",
    "source": "builtin_shadowform_fallback",
}


def enrich_card_metadata(
    card_metadata: dict[str, Any],
    *,
    hearthstonejson_cards: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    hjson_index = index_cards_by_id(hearthstonejson_cards or [])
    warnings: list[dict[str, Any]] = []
    deckwide_effects: list[dict[str, Any]] = []
    enriched_cards = []

    for card in card_metadata.get("cards", []):
        enriched = dict(card)
        hjson = hjson_index.get(str(card.get("card_id"))) or hjson_index.get(str(card.get("dbf_id")))
        if hjson:
            enriched = _merge_hjson(enriched, hjson)

        semantic_families = {str(item) for item in enriched.get("mechanic_families", [])}
        semantic_families.update(_semantic_families_from_card(enriched))
        linked_entities = list(enriched.get("linked_entities", []))

        if "shadowform" in semantic_families and "start_of_game" in semantic_families:
            hero_power, warning = _mind_spike_entity(hjson_index)
            linked_entities.append(hero_power)
            if warning:
                warnings.append({"card_id": enriched["card_id"], "warning": warning})
            semantic_families.update({"hero_power_transform", "hero_power_pressure"})
            deckwide_effects.append(
                {
                    "source_card_id": enriched["card_id"],
                    "source_card_name": enriched.get("name", enriched["card_id"]),
                    "effect": "replace_starting_hero_power",
                    "target_card_id": hero_power["card_id"],
                    "target_name": hero_power["name"],
                    "target_type": hero_power["type"],
                    "reason": (
                        "Darkbishop Benedictus enters Shadowform at Start of Game; "
                        "Mind Spike is a damage Hero Power for the ShadowPriest pressure plan."
                    ),
                }
            )

        enriched["semantic_families"] = sorted(semantic_families)
        enriched["linked_entities"] = linked_entities
        enriched_cards.append(enriched)

    return {
        "cards": enriched_cards,
        "deckwide_effects": _dedupe_deckwide_effects(deckwide_effects),
        "semantic_enrichment_status": "partial" if warnings else "complete",
        "semantic_enrichment_warnings": warnings,
    }


def _merge_hjson(card: dict[str, Any], hjson: dict[str, Any]) -> dict[str, Any]:
    merged = dict(card)
    if _is_missing_value(merged.get("name")) or merged.get("name") == merged.get("card_id"):
        merged["name"] = hjson.get("name")
    if _is_missing_value(merged.get("type")) or str(merged.get("type")).upper() == "UNKNOWN":
        merged["type"] = hjson.get("type")
    if _is_missing_value(merged.get("text")):
        merged["text"] = hjson.get("text", "")
    merged["referenced_tags"] = list(
        dict.fromkeys([*merged.get("referenced_tags", []), *hjson.get("referenced_tags", [])])
    )
    merged["entourage"] = list(
        dict.fromkeys([*merged.get("entourage", []), *hjson.get("entourage", [])])
    )
    return merged


def _semantic_families_from_card(card: dict[str, Any]) -> set[str]:
    text = _plain_text(f"{card.get('name', '')} {card.get('text', '')}").lower()
    tags = {str(tag).upper() for tag in card.get("referenced_tags", [])}
    families: set[str] = set()
    if "START_OF_GAME_KEYWORD" in tags or "start of game" in text:
        families.add("start_of_game")
    if "enter shadowform" in text or "shadowform" in text:
        families.add("shadowform")
    if "hero power" in text:
        families.add("hero_power")
    if str(card.get("type", "")).upper() == "HERO_POWER":
        families.add("hero_power")
    return families


def _is_missing_value(value: Any) -> bool:
    return value is None or str(value).strip() == ""


def _mind_spike_entity(index: dict[str, dict[str, Any]]) -> tuple[dict[str, Any], str | None]:
    row = index.get("EX1_625t")
    if row:
        return (
            {
                "card_id": str(row["id"]),
                "dbf_id": row.get("dbf_id"),
                "name": str(row.get("name", "Mind Spike")),
                "type": str(row.get("type", "HERO_POWER")),
                "text": str(row.get("text", "")),
                "source": "hearthstonejson",
            },
            None,
        )
    return dict(MIND_SPIKE_FALLBACK), "mind_spike_resolved_from_builtin_fallback"


def _plain_text(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).replace("$", "")


def _dedupe_deckwide_effects(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str]] = set()
    deduped = []
    for row in rows:
        key = (str(row["source_card_id"]), str(row["effect"]), str(row["target_card_id"]))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return sorted(deduped, key=lambda row: (row["source_card_id"], row["effect"], row["target_card_id"]))

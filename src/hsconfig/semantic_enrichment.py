from __future__ import annotations

import re
from typing import Any

from hsconfig.hearthstonejson import index_cards_by_id
from hsconfig.linked_entity_supplement import curated_link_map_for
from hsconfig.option_identity_resolver import resolve_linked_entities


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
    card_ids = [
        str(card.get("card_id") or card.get("id") or "")
        for card in card_metadata.get("cards", [])
        if str(card.get("card_id") or card.get("id") or "")
    ]
    curated_supplement = curated_link_map_for(card_ids)

    for card in card_metadata.get("cards", []):
        enriched = dict(card)
        hjson = hjson_index.get(str(card.get("card_id"))) or hjson_index.get(str(card.get("dbf_id")))
        if hjson:
            enriched = _merge_hjson(enriched, hjson)

        semantic_families = {str(item) for item in enriched.get("mechanic_families", [])}
        semantic_families.update(_semantic_families_from_card(enriched))
        card_id = str(enriched.get("card_id") or enriched.get("id") or "")
        resolved_links = resolve_linked_entities(
            [enriched],
            hjson_index,
            supplement_links=curated_supplement,
        ).get(card_id, [])
        linked_entities = _merge_linked_entities(enriched.get("linked_entities", []), resolved_links)

        if "shadowform" in semantic_families and "start_of_game" in semantic_families:
            hero_power = _starting_hero_power_link(linked_entities)
            warning = None
            if hero_power is None:
                hero_power, warning = _mind_spike_entity(hjson_index)
                linked_entities = _merge_linked_entities(linked_entities, [hero_power])
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
    if _is_missing_value(merged.get("hero_power_dbf_id")):
        merged["hero_power_dbf_id"] = hjson.get("hero_power_dbf_id")
    if _is_missing_value(merged.get("quest_reward")):
        merged["quest_reward"] = hjson.get("quest_reward")
    play_requirements = dict(hjson.get("play_requirements", {}) or {})
    play_requirements.update(dict(merged.get("play_requirements", {}) or {}))
    merged["play_requirements"] = play_requirements
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
                "link_kind": "starting_hero_power",
                "card_id": str(row["id"]),
                "dbf_id": row.get("dbf_id"),
                "name": str(row.get("name", "Mind Spike")),
                "type": str(row.get("type", "HERO_POWER")),
                "text": str(row.get("text", "")),
                "source": "builtin_shadowform_fallback",
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


def _merge_linked_entities(existing: Any, additions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = [dict(row) for row in existing if isinstance(row, dict)] if isinstance(existing, list) else []
    seen = {
        (str(row.get("link_kind", "")), str(row.get("card_id", "")), str(row.get("source", "")))
        for row in rows
    }
    for row in additions:
        key = (str(row.get("link_kind", "")), str(row.get("card_id", "")), str(row.get("source", "")))
        if key in seen:
            continue
        seen.add(key)
        rows.append(dict(row))
    return rows


def _starting_hero_power_link(linked_entities: list[dict[str, Any]]) -> dict[str, Any] | None:
    for row in linked_entities:
        if row.get("link_kind") in {"starting_hero_power", "hero_power_transform"}:
            return row
    return None

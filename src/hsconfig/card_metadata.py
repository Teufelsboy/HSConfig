from __future__ import annotations

import re
from typing import Any


MECHANIC_ALIASES: dict[str, tuple[str, ...]] = {
    "battlecry": ("battlecry", "BATTLECRY"),
    "deathrattle": ("deathrattle", "DEATHRATTLE"),
    "discover": ("discover", "DISCOVER"),
    "dredge": ("dredge", "DREDGE"),
    "tradeable": ("tradeable", "TRADEABLE"),
    "overload": ("overload", "OVERLOAD"),
    "lifesteal": ("lifesteal", "LIFESTEAL"),
    "reborn": ("reborn", "REBORN"),
    "rush": ("rush", "RUSH"),
    "charge": ("charge", "CHARGE"),
    "taunt": ("taunt", "TAUNT"),
    "secret": ("secret", "SECRET"),
    "weapon": ("weapon", "WEAPON"),
    "location": ("location", "LOCATION"),
    "minion": ("minion", "MINION"),
    "spell": ("spell", "SPELL"),
    "draw": ("draw", "draws", "drawn"),
    "heal": ("heal", "healed", "healing", "restore health"),
    "damage": ("damage", "deal damage", "deals damage"),
    "summon": ("summon", "summons", "summoned"),
    "discard": ("discard", "discards"),
    "silence": ("silence", "silences"),
    "transform": ("transform", "transforms"),
    "destroy": ("destroy", "destroys"),
}


def assign_mechanic_families(card: dict[str, Any]) -> list[str]:
    haystack = _mechanic_haystack(card)
    families = [
        family
        for family, aliases in MECHANIC_ALIASES.items()
        if any(_contains_alias(haystack, alias) for alias in aliases)
    ]
    return sorted(set(families))


def hydrate_card_metadata(
    *,
    cards: list[dict[str, Any]],
    source_records: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    hydrated = []
    missing_count = 0
    for card in cards:
        card_id = str(card["card_id"])
        dbf_id = card.get("dbf_id")
        source_key = card_id if card_id in source_records else str(dbf_id)
        source = source_records.get(source_key, {})
        metadata_status = "source_record" if source else "missing_source_record"
        if not source:
            missing_count += 1
        merged = {
            "card_id": card_id,
            "dbf_id": int(dbf_id) if dbf_id is not None else None,
            "count": int(card.get("count", 1)),
            "name": source.get("name", card_id),
            "cost": source.get("cost"),
            "type": source.get("type", card.get("type", "UNKNOWN")),
            "card_class": source.get("card_class", source.get("class")),
            "text": source.get("text", ""),
            "mechanics": list(source.get("mechanics", card.get("mechanics", [])) or []),
            "metadata_status": metadata_status,
            "source_record_key": source_key if source else None,
        }
        merged["mechanic_families"] = assign_mechanic_families(merged)
        hydrated.append(merged)
    return {"cards": hydrated, "unresolved_metadata_count": missing_count}


def _mechanic_haystack(card: dict[str, Any]) -> str:
    values = [str(card.get("type", "")), str(card.get("text", ""))]
    values.extend(str(item) for item in card.get("mechanics", []) or [])
    return " ".join(values).lower()


def _contains_alias(haystack: str, alias: str) -> bool:
    normalized = alias.lower()
    if " " in normalized:
        return normalized in haystack
    return bool(re.search(rf"(?<![a-z0-9]){re.escape(normalized)}(?![a-z0-9])", haystack))

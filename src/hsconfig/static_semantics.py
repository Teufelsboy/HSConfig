from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any


TEXT_PATTERNS: dict[str, tuple[str, ...]] = {
    "battlecry": ("battlecry",),
    "deathrattle": ("deathrattle",),
    "discover": ("discover",),
    "dredge": ("dredge",),
    "tradeable": ("tradeable",),
    "overload": ("overload",),
    "weapon": ("weapon", "equip", "equips"),
    "freeze": ("freeze", "frozen"),
    "lifesteal": ("lifesteal",),
    "reborn": ("reborn",),
    "rush": ("rush",),
    "charge": ("charge",),
    "taunt": ("taunt",),
    "secret": ("secret",),
    "draw": ("draw", "draws", "drawn"),
    "heal": ("heal", "healed", "healing", "restore health"),
    "damage": ("damage", "deal damage", "deals damage"),
    "summon": ("summon", "summons", "summoned"),
    "recruit": ("recruit",),
    "discard": ("discard", "discards"),
    "silence": ("silence", "silences"),
    "transform": ("transform", "transforms", "becomes"),
    "destroy": ("destroy", "destroys"),
    "choose_one": ("choose one",),
    "aura": ("adjacent", "your other", "your minions have"),
    "spellburst": ("spellburst",),
    "quickdraw": ("quickdraw",),
    "finale": ("finale",),
    "manathirst": ("manathirst", "mana thirst"),
    "infuse": ("infuse", "infused"),
    "corrupt": ("corrupt", "corrupted"),
    "forge": ("forge", "forged"),
    "outcast": ("outcast",),
    "titan": ("titan",),
    "starship": ("starship", "launch your starship"),
}

TYPE_TO_FAMILY = {
    "HERO_POWER": "hero_power",
    "LOCATION": "location",
    "MINION": "minion",
    "SPELL": "spell",
    "WEAPON": "weapon",
}

REFERENCED_TAG_TO_FAMILY = {
    "BATTLECRY": "battlecry",
    "CHOOSE_ONE": "choose_one",
    "DEATHRATTLE": "deathrattle",
    "DISCOVER": "discover",
    "DREDGE": "dredge",
    "TRADEABLE": "tradeable",
    "OVERLOAD": "overload",
    "FREEZE": "freeze",
    "LIFESTEAL": "lifesteal",
    "REBORN": "reborn",
    "RUSH": "rush",
    "CHARGE": "charge",
    "TAUNT": "taunt",
    "SECRET": "secret",
    "START_OF_GAME_KEYWORD": "start_of_game",
    "SPELLBURST": "spellburst",
    "QUICKDRAW": "quickdraw",
    "FINALE": "finale",
    "MANATHIRST": "manathirst",
    "INFUSE": "infuse",
    "CORRUPT": "corrupt",
    "FORGE": "forge",
    "OUTCAST": "outcast",
    "TITAN": "titan",
    "STARSHIP": "starship",
    "KINDRED": "kindred",
    "TOURIST": "tourist",
    "REWIND": "rewind",
    "HERALD": "herald",
    "SHATTER": "shatter",
}

WARNING_ONLY_MECHANICS = {
    "board_position",
    "dredge",
    "generated_entity_random_pool",
    "location_activation",
    "secret_timing",
    "forge",
    "tradeable",
    "outcast",
    "titan",
    "starship",
    "kindred",
    "tourist",
    "rewind",
    "herald",
    "shatter",
}


def infer_static_semantics(card: Mapping[str, Any]) -> dict[str, Any]:
    families: set[str] = set()
    evidence: list[dict[str, str]] = []

    card_type = str(card.get("type", "") or "").upper()
    if card_type in TYPE_TO_FAMILY:
        _add(families, evidence, TYPE_TO_FAMILY[card_type], "type", card_type)

    for mechanic in card.get("mechanics", []) or []:
        family = _normalize_family(str(mechanic))
        _add(families, evidence, family, "mechanics", str(mechanic))

    for tag in card.get("referenced_tags", card.get("referencedTags", [])) or []:
        tag_text = str(tag).upper()
        family = REFERENCED_TAG_TO_FAMILY.get(tag_text)
        if family:
            _add(families, evidence, family, "referenced_tags", tag_text)

    text = _plain_text(
        f"{card.get('name', '')} {card.get('text', '')} {card.get('targeting_arrow_text', '')}"
    )
    lowered = text.lower()
    for family, patterns in TEXT_PATTERNS.items():
        match = next((pattern for pattern in patterns if _contains(lowered, pattern)), None)
        if match:
            _add(families, evidence, family, "text", match)

    if card.get("overload") is not None:
        _add(families, evidence, "overload", "overload", str(card["overload"]))
    if card.get("spell_damage") is not None:
        _add(families, evidence, "spell_damage", "spell_damage", str(card["spell_damage"]))
    if card.get("hero_power_dbf_id") is not None:
        _add(families, evidence, "hero_power", "heroPowerDbfId", str(card["hero_power_dbf_id"]))

    if "start of game" in lowered:
        _add(families, evidence, "start_of_game", "text", "start of game")
    if "shadowform" in lowered:
        _add(families, evidence, "shadowform", "text", "shadowform")
        _add(families, evidence, "hero_power", "text", "shadowform")
        if "start_of_game" in families:
            _add(families, evidence, "hero_power_transform", "text", "shadowform start of game")
    if (
        "random" in lowered
        and (
            "summon" in families
            or _contains(lowered, "add")
            or _contains(lowered, "generate")
        )
        and any(
            _contains(lowered, object_word)
            for object_word in ("card", "copy", "minion", "secret", "spell", "weapon")
        )
    ):
        _add(families, evidence, "generated_entity", "text", "random generated entity")
        _add(families, evidence, "generated_entity_random_pool", "text", "random generated entity")
    if "secret" in families:
        _add(families, evidence, "secret_timing", "mechanic", "secret")
    if "location" in families:
        _add(families, evidence, "location_activation", "type", "LOCATION")

    return {
        "families": sorted(families),
        "evidence": _dedupe_evidence(evidence),
        "warning_only": sorted(families & WARNING_ONLY_MECHANICS),
    }


def _add(families: set[str], evidence: list[dict[str, str]], family: str, source: str, value: str) -> None:
    if not family:
        return
    families.add(family)
    evidence.append({"family": family, "source": source, "value": value})


def _normalize_family(value: str) -> str:
    return value.strip().lower().replace(" ", "_")


def _plain_text(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).replace("$", "")


def _contains(haystack: str, needle: str) -> bool:
    if " " in needle:
        return needle in haystack
    return bool(re.search(rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])", haystack))


def _dedupe_evidence(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str, str]] = set()
    deduped = []
    for row in rows:
        key = (row["family"], row["source"], row["value"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return sorted(deduped, key=lambda row: (row["family"], row["source"], row["value"]))

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen


HEARTHSTONEJSON_LATEST_ENUS_CARDS_URL = (
    "https://api.hearthstonejson.com/v1/latest/enUS/cards.json"
)
USER_AGENT = "HSConfig/0.1 semantic-enrichment"


def load_cards_json(path: str | Path) -> list[dict[str, Any]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"HearthstoneJSON card payload must be a list: {path}")
    return [normalize_card_row(row) for row in payload]


def fetch_latest_cards(timeout: float = 10.0) -> list[dict[str, Any]]:
    request = Request(
        HEARTHSTONEJSON_LATEST_ENUS_CARDS_URL,
        headers={"User-Agent": USER_AGENT},
    )
    with urlopen(request, timeout=timeout) as response:
        payload = json.load(response)
    if not isinstance(payload, list):
        raise ValueError("HearthstoneJSON latest cards response must be a list")
    return [normalize_card_row(row) for row in payload]


def normalize_card_row(row: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(row, dict):
        raise ValueError("HearthstoneJSON card row must be an object")
    card_id = str(row.get("id") or "").strip()
    if not card_id:
        raise ValueError("HearthstoneJSON card row missing id")
    dbf_id = row.get("dbfId", row.get("dbf_id"))
    cost = row.get("cost")
    hero_power_dbf_id = row.get("heroPowerDbfId", row.get("hero_power_dbf_id"))
    return {
        "id": card_id,
        "dbf_id": _int_or_none(dbf_id),
        "name": str(row.get("name") or card_id),
        "type": str(row.get("type") or "UNKNOWN"),
        "card_class": row.get("cardClass", row.get("card_class")),
        "classes": _string_list(row.get("classes", [])),
        "collectible": bool(row.get("collectible", False)),
        "cost": _int_or_none(cost),
        "attack": _int_or_none(row.get("attack")),
        "health": _int_or_none(row.get("health")),
        "durability": _int_or_none(row.get("durability")),
        "text": str(row.get("text") or ""),
        "mechanics": _string_list(row.get("mechanics", [])),
        "referenced_tags": _string_list(
            row.get("referencedTags", row.get("referenced_tags", []))
        ),
        "spell_school": str(row.get("spellSchool", row.get("spell_school", "")) or ""),
        "race": str(row.get("race", "")) if row.get("race") is not None else None,
        "races": _string_list(row.get("races", [])),
        "overload": _int_or_none(row.get("overload")),
        "spell_damage": _int_or_none(row.get("spellDamage", row.get("spell_damage"))),
        "targeting_arrow_text": str(
            row.get("targetingArrowText", row.get("targeting_arrow_text", "")) or ""
        ),
        "hero_power_dbf_id": _int_or_none(hero_power_dbf_id),
        "quest_reward": row.get("questReward", row.get("quest_reward")),
        "play_requirements": dict(
            row.get("playRequirements", row.get("play_requirements", {})) or {}
        ),
        "entourage": _string_list(row.get("entourage", [])),
    }


def index_cards_by_id(cards: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for card in cards:
        normalized = normalize_card_row(card)
        index[str(normalized["id"])] = normalized
        if normalized.get("dbf_id") is not None:
            index[str(normalized["dbf_id"])] = normalized
    return index


def _int_or_none(value: Any) -> int | None:
    return int(value) if value is not None else None


def _string_list(value: Any) -> list[str]:
    return [str(item) for item in value or []]

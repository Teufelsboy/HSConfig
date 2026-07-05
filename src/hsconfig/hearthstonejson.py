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
    return {
        "id": card_id,
        "dbf_id": int(row["dbfId"]) if row.get("dbfId") is not None else None,
        "name": str(row.get("name") or card_id),
        "type": str(row.get("type") or "UNKNOWN"),
        "card_class": row.get("cardClass"),
        "cost": int(row["cost"]) if row.get("cost") is not None else None,
        "text": str(row.get("text") or ""),
        "mechanics": [str(item) for item in row.get("mechanics", []) or []],
        "referenced_tags": [str(item) for item in row.get("referencedTags", []) or []],
        "entourage": [str(item) for item in row.get("entourage", []) or []],
    }


def index_cards_by_id(cards: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for card in cards:
        normalized = normalize_card_row(card) if "id" not in card else dict(card)
        index[str(normalized["id"])] = normalized
        if normalized.get("dbf_id") is not None:
            index[str(normalized["dbf_id"])] = normalized
    return index

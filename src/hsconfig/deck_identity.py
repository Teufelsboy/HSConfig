from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from typing import Any

from hsconfig.io import slugify_deck_name


def stable_deck_fingerprint(cards: Iterable[tuple[str, int]]) -> str:
    card_counts: dict[str, int] = {}
    for card_id, count in cards:
        normalized_card_id = str(card_id)
        card_counts[normalized_card_id] = card_counts.get(normalized_card_id, 0) + int(count)
    canonical = sorted(card_counts.items(), key=lambda row: row[0])
    payload = json.dumps(canonical, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_deck_identity(
    *,
    deck_name: str,
    deck_code: str,
    cards: list[dict[str, Any]],
    hero_dbf_id: int | None = None,
    format: str | None = None,
    sideboards: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    normalized_cards = [_normalize_card(card) for card in cards]
    normalized_sideboards = _normalize_sideboards(sideboards or [])
    fingerprint = stable_deck_fingerprint(
        (card["card_id"], card["count"]) for card in normalized_cards
    )
    return {
        "deck_name": deck_name,
        "deck_slug": slugify_deck_name(deck_name),
        "deck_code_hash": hashlib.sha256(deck_code.encode("utf-8")).hexdigest(),
        "hero_dbf_id": hero_dbf_id,
        "format": format,
        "cards": normalized_cards,
        "main_deck": normalized_cards,
        "sideboards": normalized_sideboards,
        "deck_fingerprint": fingerprint,
        "card_count_total": sum(card["count"] for card in normalized_cards),
        "sideboard_count": sum(
            card["count"]
            for sideboard in normalized_sideboards
            for card in sideboard.get("cards", [])
        ),
        "unresolved_card_count": sum(1 for card in normalized_cards if not card["card_id"]),
    }


def _normalize_card(card: dict[str, Any]) -> dict[str, Any]:
    dbf_id = card.get("dbf_id")
    card_id = str(card.get("card_id") or "").strip()
    if not card_id:
        raise ValueError("card_id is required for every deck card")
    return {
        "card_id": card_id,
        "dbf_id": int(dbf_id) if dbf_id is not None else None,
        "count": int(card.get("count", 1)),
    }


def _normalize_sideboards(sideboards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = []
    for index, sideboard in enumerate(sideboards, start=1):
        if not isinstance(sideboard, dict):
            continue
        normalized.append(
            {
                "sideboard_index": int(sideboard.get("sideboard_index", index)),
                "owner_dbf_id": (
                    int(sideboard["owner_dbf_id"])
                    if sideboard.get("owner_dbf_id") is not None
                    else None
                ),
                "owner_card_id": sideboard.get("owner_card_id"),
                "cards": [_normalize_card(card) for card in sideboard.get("cards", [])],
            }
        )
    return normalized

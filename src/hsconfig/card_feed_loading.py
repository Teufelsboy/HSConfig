from __future__ import annotations

from pathlib import Path
from typing import Any

from hsconfig.io import read_json


def load_optional_card_feed(path_value: str | None) -> list[dict[str, Any]] | None:
    if not path_value:
        return None
    payload = read_json(Path(path_value))
    if isinstance(payload, list):
        return _require_card_feed_list(payload, path_value)
    if isinstance(payload, dict) and isinstance(payload.get("cards"), list):
        return _require_card_feed_list(payload["cards"], path_value)
    raise ValueError(
        f"Card feed must be a JSON list or an object with a cards list: {path_value}"
    )


def card_feed_receipt_source(
    *,
    collectible_cards_json: str | None,
    full_cards_json: str | None,
) -> str:
    if collectible_cards_json and full_cards_json:
        return "local_card_feed_files"
    if collectible_cards_json or full_cards_json:
        return "local_card_feed_files_and_hearthstonejson_latest_enus_cards"
    return "hearthstonejson_latest_enus_cards"


def card_feed_receipt_status(
    *,
    collectible_cards_json: str | None,
    full_cards_json: str | None,
    semantic_fetch_skipped: bool,
    semantic_fetch_error: str | None,
) -> str:
    if semantic_fetch_error is not None:
        return "fetch_failed"
    if collectible_cards_json and full_cards_json:
        return "local_files"
    if collectible_cards_json or full_cards_json:
        return "local_files_with_fetch"
    if semantic_fetch_skipped:
        return "skipped"
    return "fetched"


def _require_card_feed_list(payload: list[Any], path_value: str) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for index, row in enumerate(payload):
        if not isinstance(row, dict):
            raise ValueError(f"Card feed row {index} must be an object: {path_value}")
        cards.append(row)
    return cards

from __future__ import annotations

from typing import Any

from hsconfig.hearthstonejson import index_cards_by_id, normalize_card_row


COMPANION_ID_KEYS = ("entourage", "child_ids", "childIds")
COMPANION_DBF_KEYS = ("hero_power_dbf_id", "heroPowerDbfId")


def build_card_data_context(
    *,
    deck_cards: list[dict[str, Any]],
    collectible_cards: list[dict[str, Any]],
    full_cards: list[dict[str, Any]],
) -> dict[str, Any]:
    collectible_index = index_cards_by_id(collectible_cards)
    full_index = index_cards_by_id(full_cards)

    deck_source_records: dict[str, dict[str, Any]] = {}
    companion_source_records: dict[str, dict[str, Any]] = {}
    missing_deck_cards: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    for deck_card in deck_cards:
        card_id = str(deck_card.get("card_id", ""))
        dbf_id = deck_card.get("dbf_id")
        source = collectible_index.get(card_id) or collectible_index.get(str(dbf_id))
        if source is None:
            missing_deck_cards.append({"card_id": card_id, "dbf_id": dbf_id})
            warnings.append({"reason": "missing_collectible_deck_card", "card_id": card_id})
            continue
        normalized = normalize_card_row(source)
        deck_source_records[card_id] = normalized
        _collect_companions(
            source=normalized,
            full_index=full_index,
            companion_source_records=companion_source_records,
            warnings=warnings,
        )

    missing_companions = [
        warning
        for warning in warnings
        if warning["reason"] in {"missing_companion_card", "missing_companion_dbf_id"}
    ]
    return {
        "deck_source_records": deck_source_records,
        "companion_source_records": companion_source_records,
        "card_data_intake_report": {
            "schema_version": 1,
            "non_blocking": True,
            "warnings": warnings,
            "missing_deck_cards": missing_deck_cards,
            "summary": {
                "deck_cards": len(deck_cards),
                "matched_deck_cards": len(deck_source_records),
                "missing_deck_cards": len(missing_deck_cards),
                "companion_records": len(companion_source_records),
                "missing_companion_records": len(missing_companions),
            },
        },
    }


def _collect_companions(
    *,
    source: dict[str, Any],
    full_index: dict[str, dict[str, Any]],
    companion_source_records: dict[str, dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> None:
    for key in COMPANION_ID_KEYS:
        for companion_id in source.get(key, []) or []:
            companion = full_index.get(str(companion_id))
            if companion is None:
                warnings.append(
                    {"reason": "missing_companion_card", "card_id": str(companion_id)}
                )
                continue
            normalized = normalize_card_row(companion)
            companion_source_records[normalized["id"]] = normalized

    for key in COMPANION_DBF_KEYS:
        dbf_id = source.get(key)
        if dbf_id in (None, ""):
            continue
        companion = full_index.get(str(dbf_id))
        if companion is None:
            warnings.append({"reason": "missing_companion_dbf_id", "dbf_id": int(dbf_id)})
            continue
        normalized = normalize_card_row(companion)
        companion_source_records[normalized["id"]] = normalized

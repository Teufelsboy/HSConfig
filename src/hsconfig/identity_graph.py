from __future__ import annotations

from typing import Any


def build_identity_graph_report(
    *,
    deck_identity: dict[str, Any],
    hearthstonejson_receipt: dict[str, Any] | None = None,
) -> dict[str, Any]:
    main_multiset = _card_multiset(deck_identity.get("cards", []))
    sideboard_multiset = _sideboard_multiset(deck_identity.get("sideboards", []))
    return {
        "schema_version": 1,
        "deck_name": str(deck_identity.get("deck_name", "")),
        "deck_code_hash": str(deck_identity.get("deck_code_hash", "")),
        "format": deck_identity.get("format"),
        "hero_dbf_id": deck_identity.get("hero_dbf_id"),
        "starting_hero_power_id": deck_identity.get("starting_hero_power_id"),
        "main_deck_multiset": main_multiset,
        "sideboard_multiset": sideboard_multiset,
        "main_deck_card_count": sum(main_multiset.values()),
        "sideboard_card_count": sum(sideboard_multiset.values()),
        "hearthstonejson_receipt": hearthstonejson_receipt or {},
        "generated_token_closure": "not_in_scope_for_step1_identity_graph",
    }


def build_identity_gap_report(identity_graph_report: dict[str, Any]) -> dict[str, Any]:
    required_fields = [
        "deck_name",
        "deck_code_hash",
        "format",
        "hero_dbf_id",
        "starting_hero_power_id",
    ]
    missing = [
        field
        for field in required_fields
        if identity_graph_report.get(field) in (None, "", [], {})
    ]
    return {
        "schema_version": 1,
        "deck_name": identity_graph_report.get("deck_name", ""),
        "missing_identity_fields": missing,
        "gap_count": len(missing),
    }


def _card_multiset(cards: Any) -> dict[str, int]:
    multiset: dict[str, int] = {}
    if not isinstance(cards, list):
        return multiset
    for card in cards:
        if not isinstance(card, dict):
            continue
        card_id = str(card.get("card_id", "")).strip()
        if not card_id:
            continue
        multiset[card_id] = multiset.get(card_id, 0) + int(card.get("count", 1))
    return dict(sorted(multiset.items()))

def _sideboard_multiset(sideboards: Any) -> dict[str, int]:
    multiset: dict[str, int] = {}
    if not isinstance(sideboards, list):
        return multiset
    for sideboard in sideboards:
        if not isinstance(sideboard, dict):
            continue
        for card in sideboard.get("cards", []) or []:
            if not isinstance(card, dict):
                continue
            card_id = str(card.get("card_id", "")).strip()
            if not card_id:
                continue
            multiset[card_id] = multiset.get(card_id, 0) + int(card.get("count", 1))
    return dict(sorted(multiset.items()))

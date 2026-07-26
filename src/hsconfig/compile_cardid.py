from __future__ import annotations

from typing import Any, Iterable

from hsconfig.mechanic_support import (
    ROLE_ALIASES,
    normalize_role_token,
)


EFFECT_ONLY_START_OF_GAME_ROLES = {
    "deckbuilding_modifier",
    "hero_power_transform",
    "passive_start_effect",
    "shadow_hero_power",
    "shadowform",
    "start_of_game",
    "start_of_game_keyword",
    "start_of_game_modifier",
}
BODY_AUTHORITY_ROLES = {
    "body_pressure",
    "board_tempo",
    "mulligan_anchor",
    "playable_body",
    "tempo_body",
}


def compile_cardid_behaviors(
    contract: dict[str, Any] | None = None,
    *,
    deck_name: str | None = None,
    rows: list[dict[str, Any]] | None = None,
    static_runtime_suppressed_card_ids: Iterable[str] | None = None,
) -> dict[str, dict[str, Any]]:
    contract = contract or {}
    deck_name = deck_name or str(contract.get("deck_name", "Deck"))
    del static_runtime_suppressed_card_ids
    cards = _cards_from_contract(contract)
    if rows:
        _merge_row_cards(cards, _cards_from_rows(rows))

    files: dict[str, dict[str, Any]] = {}
    for card_id, card in sorted(cards.items()):
        config: dict[str, Any] = {
            "GameCardId": card_id,
            "ConfigComment": f"{deck_name}: generated behavior for {card_id}",
        }
        _append_explicit_behavior_rows(
            config,
            deck_name,
            card_id,
            card.get("behavior_rows", []),
        )
        files[f"{card_id}.json"] = config
    return files


def _is_effect_only_start_of_game_card(roles: Iterable[str]) -> bool:
    role_set = {normalize_role_token(role) for role in roles if role}
    canonical_roles = {ROLE_ALIASES.get(role, role) for role in role_set}
    combined_roles = role_set | canonical_roles
    if not combined_roles.intersection(EFFECT_ONLY_START_OF_GAME_ROLES):
        return False
    if combined_roles.intersection(BODY_AUTHORITY_ROLES):
        return False
    return True


def _cards_from_contract(contract: dict[str, Any]) -> dict[str, dict[str, Any]]:
    cards = contract.get("cards", {})
    if isinstance(cards, dict):
        return {str(card_id): dict(card) for card_id, card in cards.items()}
    return {str(card["card_id"]): dict(card) for card in cards}


def _cards_from_rows(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    cards: dict[str, dict[str, Any]] = {}
    for row in rows:
        if row.get("surface_family") != "CARDID.json" and row.get("surface") != "CARDID.json":
            continue
        card_id = str(row["card_id"])
        card = cards.setdefault(
            card_id,
            {
                "roles": [],
                "source_claim_ids": [],
                "confidence": row.get("confidence", "source_backed"),
            },
        )
        card["roles"].extend(str(role) for role in row.get("roles", []))
        if row.get("intent"):
            card["roles"].append(str(row["intent"]))
        card["source_claim_ids"].extend(row.get("source_claim_ids", []))
        if row.get("behavior_block"):
            card.setdefault("behavior_rows", []).append(dict(row))
    return cards


def _merge_row_cards(
    cards: dict[str, dict[str, Any]], row_cards: dict[str, dict[str, Any]]
) -> None:
    for card_id, row_card in row_cards.items():
        card = cards.setdefault(
            card_id,
            {
                "roles": [],
                "source_claim_ids": [],
                "confidence": row_card.get("confidence", "source_backed"),
            },
        )
        card["roles"] = sorted(
            {
                *[str(role) for role in card.get("roles", [])],
                *[str(role) for role in row_card.get("roles", [])],
            }
        )
        card["source_claim_ids"] = sorted(
            {
                *[str(claim_id) for claim_id in card.get("source_claim_ids", [])],
                *[str(claim_id) for claim_id in row_card.get("source_claim_ids", [])],
            }
        )
        card.setdefault("behavior_rows", []).extend(row_card.get("behavior_rows", []))
        if card.get("confidence") != "source_backed":
            card["confidence"] = row_card.get("confidence", card.get("confidence", "source_backed"))


def _append_explicit_behavior_rows(
    config: dict[str, Any],
    deck_name: str,
    card_id: str,
    behavior_rows: list[dict[str, Any]],
) -> set[str]:
    emitted_blocks: set[str] = set()
    for row in behavior_rows:
        block = str(row["behavior_block"])
        _append_block_row(
            config,
            block,
            deck_name,
            card_id,
            str(row.get("rule_id_suffix") or row.get("intent") or "behavior"),
            str(row.get("value", "6")),
            [str(claim_id) for claim_id in row.get("source_claim_ids", [])],
            str(row.get("confidence", "source_backed")),
            condition=str(row.get("condition", "*")),
        )
        emitted_blocks.add(block)
    return emitted_blocks


def _append_block_row(
    config: dict[str, Any],
    block: str,
    deck_name: str,
    card_id: str,
    rule_id_suffix: str,
    value: str,
    source_claim_ids: list[str],
    confidence: str,
    *,
    condition: str = "*",
) -> None:
    rule_id = f"{card_id}_{rule_id_suffix}"
    config.setdefault(block, {"values": []})["values"].append(
        {
            "comment": f"{deck_name}: {rule_id}",
            "condition": condition,
            "value": value,
        }
    )

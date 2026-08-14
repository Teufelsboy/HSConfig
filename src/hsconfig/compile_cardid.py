from __future__ import annotations

from typing import Any, Iterable

from hsconfig.mechanic_support import (
    ROLE_ALIASES,
    normalize_role_token,
)
from hsconfig.package_domain import deep_freeze_definition
from hsconfig.runtime_entity_owner import partition_runtime_entity_owner_rows
from hsconfig.runtime_row_identity import canonicalize_runtime_rows


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
EFFECT_ONLY_START_OF_GAME_ROLES = deep_freeze_definition(
    EFFECT_ONLY_START_OF_GAME_ROLES
)
BODY_AUTHORITY_ROLES = deep_freeze_definition(BODY_AUTHORITY_ROLES)


class CompiledCardIdFiles(dict[str, dict[str, Any]]):
    def __init__(
        self,
        *args: Any,
        merged_duplicate_runtime_row_count: int = 0,
        runtime_row_conflicts: list[dict[str, Any]] | None = None,
        runtime_entity_owner_collisions: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.merged_duplicate_runtime_row_count = merged_duplicate_runtime_row_count
        self.runtime_row_conflicts = list(runtime_row_conflicts or [])
        self.runtime_entity_owner_collisions = list(
            runtime_entity_owner_collisions or []
        )


def compile_cardid_behaviors(
    contract: dict[str, Any] | None = None,
    *,
    deck_name: str | None = None,
    rows: list[dict[str, Any]] | None = None,
    static_runtime_suppressed_card_ids: Iterable[str] | None = None,
) -> CompiledCardIdFiles:
    contract = contract or {}
    deck_name = deck_name or str(contract.get("deck_name", "Deck"))
    del static_runtime_suppressed_card_ids
    accepted_rows, owner_collisions = partition_runtime_entity_owner_rows(
        rows or []
    )
    cards = _cards_from_contract(contract)
    if accepted_rows:
        _merge_row_cards(cards, _cards_from_rows(accepted_rows))
    canonical = _canonicalize_card_behavior_rows(cards)

    files = CompiledCardIdFiles(
        merged_duplicate_runtime_row_count=canonical["merged_duplicate_count"],
        runtime_row_conflicts=canonical["conflicts"],
        runtime_entity_owner_collisions=owner_collisions,
    )
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


def _canonicalize_card_behavior_rows(
    cards: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for card_id, card in cards.items():
        for behavior_row in card.get("behavior_rows", []):
            row = dict(behavior_row)
            row["card_id"] = card_id
            row.setdefault("value", "6")
            rows.append(row)

    result = canonicalize_runtime_rows(rows)
    for card in cards.values():
        card["behavior_rows"] = []
    for row in result["rows"]:
        cards[str(row["card_id"])]["behavior_rows"].append(row)
    return result


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
        card_id = str(row.get("runtime_card_id") or row["card_id"])
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

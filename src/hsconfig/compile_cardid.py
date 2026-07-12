from __future__ import annotations

from typing import Any

from hsconfig.mechanic_support import (
    ROLE_ALIASES,
    mechanic_default_runtime_block,
    mechanic_lowering_policy,
    normalize_role_token,
)


NON_MECHANIC_FALLBACK_BLOCKS = {
    "prefer_enemy_minion": "BeforeBattlecryTargetBonus",
    "prefer_friendly_minion": "BeforePlayCardBonus",
}
DIAGNOSTIC_ONLY_ROLE_FALLBACKS = {
    "destroy",
    "generic_spell_target",
    "hero_power",
    "silence",
    "transform",
}

BACKED_CONFIDENCE_LANES = {
    "guide_backed",
    "source_backed",
    "source_backed_static_semantics",
}


def compile_cardid_behaviors(
    contract: dict[str, Any] | None = None,
    *,
    deck_name: str | None = None,
    rows: list[dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    contract = contract or {}
    deck_name = deck_name or str(contract.get("deck_name", "Deck"))
    cards = _cards_from_contract(contract)
    if rows:
        _merge_row_cards(cards, _cards_from_rows(rows))

    files: dict[str, dict[str, Any]] = {}
    for card_id, card in sorted(cards.items()):
        roles = set(card.get("roles", []))
        source_claim_ids = list(card.get("source_claim_ids", []))
        confidence = str(card.get("confidence", card.get("coverage_status", "generic_low_confidence")))
        config: dict[str, Any] = {
            "GameCardId": card_id,
            "ConfigComment": f"{deck_name}: generated behavior for {card_id}",
        }
        _append_block_row(
            config,
            "InHandPlayPriority",
            deck_name,
            card_id,
            "in_hand_priority",
            _priority_value(roles, confidence),
            source_claim_ids,
            confidence,
        )
        explicit_blocks = _append_explicit_behavior_rows(
            config,
            deck_name,
            card_id,
            card.get("behavior_rows", []),
        )
        if "pressure" in roles and "BeforePlayCardBonus" not in explicit_blocks:
            _append_block_row(
                config,
                "BeforePlayCardBonus",
                deck_name,
                card_id,
                "pressure_play_bonus",
                "8",
                source_claim_ids,
                confidence,
            )
        if "prefer_enemy_hero" in roles and "BeforePlayCardBonus" not in explicit_blocks:
            _append_block_row(
                config,
                "BeforePlayCardBonus",
                deck_name,
                card_id,
                "prefer_enemy_hero_bonus",
                "12",
                source_claim_ids,
                confidence,
            )
        for role in sorted(roles):
            block = _role_fallback_block(role)
            if block is None:
                continue
            if block in explicit_blocks:
                continue
            policy = mechanic_lowering_policy(role)
            _append_block_row(
                config,
                block,
                deck_name,
                card_id,
                f"{role}_behavior",
                str(policy.get("default_value", "6")),
                source_claim_ids,
                confidence,
                condition=str(policy.get("default_condition", "*")),
            )
        files[f"{card_id}.json"] = config
    return files


def _role_fallback_block(role: str) -> str | None:
    canonical_role = ROLE_ALIASES.get(normalize_role_token(role), normalize_role_token(role))
    if canonical_role in DIAGNOSTIC_ONLY_ROLE_FALLBACKS:
        return None
    if role in NON_MECHANIC_FALLBACK_BLOCKS:
        return NON_MECHANIC_FALLBACK_BLOCKS[role]
    policy = mechanic_lowering_policy(canonical_role)
    if policy["policy"] == "report_only":
        return None
    return mechanic_default_runtime_block(role)


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


def _priority_value(roles: set[str], confidence: str) -> str:
    if "mulligan_anchor" in roles and "pressure" in roles:
        return "12"
    if "pressure" in roles or "combo_piece" in roles:
        return "10"
    if confidence in BACKED_CONFIDENCE_LANES:
        return "7"
    return "5"


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

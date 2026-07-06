from __future__ import annotations

from typing import Any

from hsconfig.condition_format import lower_runtime_condition
from hsconfig.visionai_registry import CARD_BEHAVIOR_BLOCKS


DEFAULT_ROW_VALUE = "6"

TARGETING_STANCES = {
    "prefer_enemy_hero",
    "prefer_enemy_minion",
    "prefer_friendly_minion",
}
ROLE_BLOCKS = {
    "battlecry": "BeforeBattlecryTargetBonus",
    "discover": "OnDiscoverCardBonus",
    "dredge": "OnDiscoverCardBonus",
    "freeze": "BeforePlayCardBonus",
    "hero_power": "BeforeUseHeroPowerBonus",
    "location": "BeforePlayCardBonus",
    "overkill": "BeforeOverkilledBonus",
    "overload": "BeforePlayCardBonus",
    "prefer_enemy_hero": "BeforePlayCardBonus",
    "prefer_enemy_minion": "BeforeBattlecryTargetBonus",
    "prefer_friendly_minion": "BeforePlayCardBonus",
    "secret": "BeforePlayCardBonus",
    "tradeable": "BeforePlayCardBonus",
    "weapon": "BeforePhysicalAttackBonus",
}
MECHANIC_ROLE_MAP = {
    "battlecry": "battlecry",
    "discover": "discover",
    "dredge": "discover",
    "tradeable": "tradeable",
    "overload": "overload",
    "overkill": "overkill",
    "freeze": "freeze",
    "weapon": "weapon",
    "secret": "secret",
    "location": "location",
}


def route_card_behavior_claims(claims: list[dict[str, Any]]) -> dict[str, Any]:
    card_rows: dict[str, list[dict[str, Any]]] = {}
    suppressed: list[dict[str, Any]] = []
    strong_cards: set[str] = set()

    for claim in claims:
        claim_kind = str(claim.get("claim_kind", claim.get("claim_type", "")))
        cards = _claim_cards(claim)
        condition, condition_error = _condition(claim)
        if condition_error is not None:
            suppressed.append(
                {
                    "claim_id": claim.get("claim_id"),
                    "claim_kind": claim_kind,
                    "cards": cards,
                    "reason": condition_error,
                }
            )
            continue
        explicit_block, explicit_error = _explicit_runtime_block(claim)
        if explicit_error is not None:
            suppressed.append(
                {
                    "claim_id": claim.get("claim_id"),
                    "claim_kind": claim_kind,
                    "cards": cards,
                    **explicit_error,
                }
            )
            continue
        if claim_kind == "targeting_rule" and str(claim.get("stance")) in TARGETING_STANCES:
            intent = str(claim["stance"])
            behavior_block = explicit_block or ROLE_BLOCKS[intent]
            for card_id in cards:
                row = _base_row(claim, card_id, condition=condition)
                card_rows.setdefault(card_id, []).append(
                    _attach_behavior_fields(
                        row,
                        behavior_block=behavior_block,
                        intent=intent,
                        roles=[intent],
                        claim=claim,
                    )
                )
                strong_cards.add(card_id)
            continue
        if claim_kind == "mechanic_usage":
            mechanic = str(claim.get("mechanic", claim.get("stance", ""))).lower()
            role = MECHANIC_ROLE_MAP.get(mechanic)
            if role is not None:
                behavior_block = explicit_block or ROLE_BLOCKS[role]
                for card_id in cards:
                    row = _base_row(claim, card_id, condition=condition)
                    card_rows.setdefault(card_id, []).append(
                        _attach_behavior_fields(
                            row,
                            behavior_block=behavior_block,
                            intent=f"use_{role}_according_to_card_text",
                            roles=[role],
                            claim=claim,
                        )
                    )
                continue
        if claim_kind == "card_role":
            for card_id in cards:
                if card_id in strong_cards:
                    continue
                intent = str(claim.get("stance", "deck_card"))
                row = _base_row(claim, card_id, condition=condition)
                if explicit_block is not None:
                    row = _attach_behavior_fields(
                        row,
                        behavior_block=explicit_block,
                        intent=intent,
                        roles=[intent],
                        claim=claim,
                    )
                else:
                    row["intent"] = "in_hand_priority"
                    row["roles"] = [intent]
                    row["rule_id_suffix"] = "in_hand_priority"
                    row["value"] = _runtime_value(claim, default="7")
                    row["meaningful_runtime_surface"] = False
                card_rows.setdefault(card_id, []).append(row)
            continue
        suppressed.append(
            {
                "claim_id": claim.get("claim_id"),
                "claim_kind": claim_kind,
                "cards": cards,
                "reason": "no_documented_card_behavior_surface",
            }
        )

    rows = [row for card_id in sorted(card_rows) for row in card_rows[card_id]]
    return {
        "card_rows": {card_id: card_rows[card_id] for card_id in sorted(card_rows)},
        "rows": rows,
        "suppressed": suppressed,
    }


def _base_row(claim: dict[str, Any], card_id: str, *, condition: str) -> dict[str, Any]:
    return {
        "surface": "CardID.json",
        "surface_family": "CARDID.json",
        "card_id": card_id,
        "condition": condition,
        "confidence": str(claim.get("claim_confidence", claim.get("confidence", "source_backed"))),
        "source_claim_ids": _source_claim_ids(claim),
        "source_refs": [str(item) for item in claim.get("source_refs", [])],
        "claim_confidence": str(claim.get("claim_confidence", claim.get("confidence", "source_backed"))),
    }


def _claim_cards(claim: dict[str, Any]) -> list[str]:
    cards = claim.get("cards", [])
    if isinstance(cards, str):
        cards = [cards]
    return [str(card) for card in cards if str(card)]


def _source_claim_ids(claim: dict[str, Any]) -> list[str]:
    if isinstance(claim.get("source_claim_ids"), list):
        return [str(item) for item in claim["source_claim_ids"]]
    if claim.get("claim_id"):
        return [str(claim["claim_id"])]
    return []


def _condition(claim: dict[str, Any]) -> tuple[str, str | None]:
    return lower_runtime_condition(claim.get("conditions", claim.get("condition", "*")))


def _explicit_runtime_block(claim: dict[str, Any]) -> tuple[str | None, dict[str, Any] | None]:
    block = claim.get("runtime_block")
    if block is None:
        return None, None
    normalized = str(block)
    if normalized not in CARD_BEHAVIOR_BLOCKS:
        return None, {
            "runtime_block": normalized,
            "reason": "unsupported_card_behavior_block",
        }
    return normalized, None


def _runtime_value(claim: dict[str, Any], default: str = DEFAULT_ROW_VALUE) -> str:
    return str(claim.get("runtime_value", claim.get("value", default)))


def _attach_behavior_fields(
    row: dict[str, Any],
    *,
    behavior_block: str,
    intent: str,
    roles: list[str],
    claim: dict[str, Any],
) -> dict[str, Any]:
    row["behavior_block"] = behavior_block
    row["intent"] = intent
    row["roles"] = roles
    row["rule_id_suffix"] = str(claim.get("rule_id_suffix", intent))
    row["value"] = _runtime_value(claim)
    row["meaningful_runtime_surface"] = True
    return row

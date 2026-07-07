from __future__ import annotations

from typing import Any

from hsconfig.condition_format import lower_runtime_condition
from hsconfig.source_document_model import claim_can_lower_to_runtime
from hsconfig.visionai_registry import CARD_BEHAVIOR_BLOCKS


DEFAULT_ROW_VALUE = "6"

TARGETING_STANCES = {
    "prefer_enemy_hero",
    "prefer_enemy_minion",
    "prefer_friendly_minion",
}
INTENT_BLOCKS = {
    "in_hand_value": "InHandBonus",
    "on_board_value": "OnBoardBonus",
    "play_timing": "BeforePlayCardBonus",
    "targeting_rule": "BeforeBattlecryTargetBonus",
    "hero_power_use": "BeforeUseHeroPowerBonus",
    "hero_power_transform": "BeforeUseHeroPowerBonus",
    "attack_posture": "BeforePhysicalAttackBonus",
    "discover_choice": "OnDiscoverCardBonus",
    "choose_one_choice": "OnChooseOneCardBonus",
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
OPTION_CLAIM_KINDS = {"discover_choice", "choose_one_choice"}
OPTION_CARD_KEYS = (
    "option_card_id",
    "option_card",
    "choice_card_id",
    "choice_card",
)


def route_card_behavior_surfaces(
    claims: list[dict[str, Any]],
    identity_links: dict[str, Any] | None = None,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    suppressed: list[dict[str, Any]] = []
    option_resolution: list[dict[str, Any]] = []
    strong_cards: set[str] = set()

    for claim in claims:
        claim_kind = str(claim.get("claim_kind", claim.get("claim_type", "")))
        cards = _claim_cards(claim)
        if not claim_can_lower_to_runtime(claim):
            suppressed.append(
                _suppressed_row(claim, claim_kind, cards, "claim_not_runtime_lowerable")
            )
            continue
        condition, condition_error = _condition(claim)
        if condition_error is not None:
            suppressed.append(_suppressed_row(claim, claim_kind, cards, condition_error))
            continue

        explicit_block, explicit_error = _explicit_runtime_block(claim)
        if explicit_error is not None:
            suppressed.append(
                {
                    **_suppressed_row(
                        claim,
                        claim_kind,
                        cards,
                        str(explicit_error["reason"]),
                    ),
                    "runtime_block": explicit_error["runtime_block"],
                }
            )
            continue

        unresolved = _option_resolution_rows(
            claim=claim,
            claim_kind=claim_kind,
            cards=cards,
            identity_links=identity_links,
        )
        option_resolution.extend(unresolved)
        if any(row["status"] == "unresolved" for row in unresolved):
            suppressed.append(
                _suppressed_row(claim, claim_kind, cards, "unresolved_option_identity")
            )
            continue

        if claim_kind == "targeting_rule":
            intent = _claim_intent(claim, fallback=claim_kind)
            behavior_block = explicit_block or INTENT_BLOCKS[claim_kind]
            rows.extend(
                _rows_for_cards(
                    claim,
                    cards,
                    condition=condition,
                    behavior_block=behavior_block,
                    intent=intent,
                    roles=[intent],
                )
            )
            if intent in TARGETING_STANCES:
                strong_cards.update(cards)
            continue

        if claim_kind == "mechanic_usage":
            mechanic = str(claim.get("mechanic", claim.get("stance", ""))).lower()
            role = MECHANIC_ROLE_MAP.get(mechanic)
            if role is not None:
                rows.extend(
                    _rows_for_cards(
                        claim,
                        cards,
                        condition=condition,
                        behavior_block=explicit_block or ROLE_BLOCKS[role],
                        intent=f"use_{role}_according_to_card_text",
                        roles=[role],
                    )
                )
                continue

        if claim_kind in INTENT_BLOCKS:
            intent = _claim_intent(claim, fallback=claim_kind)
            rows.extend(
                _rows_for_cards(
                    claim,
                    cards,
                    condition=condition,
                    behavior_block=explicit_block or INTENT_BLOCKS[claim_kind],
                    intent=intent,
                    roles=[claim_kind],
                )
            )
            continue

        if claim_kind == "card_role":
            for card_id in cards:
                if card_id in strong_cards:
                    continue
                intent = _claim_intent(claim, fallback="deck_card")
                row = _base_row(claim, card_id, condition=condition)
                if explicit_block is not None:
                    rows.append(
                        _attach_behavior_fields(
                            row,
                            behavior_block=explicit_block,
                            intent=intent,
                            roles=[intent],
                            claim=claim,
                        )
                    )
                else:
                    row["intent"] = "in_hand_priority"
                    row["roles"] = [intent]
                    row["rule_id_suffix"] = "in_hand_priority"
                    row["value"] = _runtime_value(claim, default="7")
                    row["meaningful_runtime_surface"] = False
                    rows.append(row)
            continue

        if claim_kind == "known_bad_pattern":
            if explicit_block is not None:
                intent = _claim_intent(claim, fallback=claim_kind)
                rows.extend(
                    _rows_for_cards(
                        claim,
                        cards,
                        condition=condition,
                        behavior_block=explicit_block,
                        intent=intent,
                        roles=[claim_kind],
                    )
                )
            else:
                suppressed.append(
                    _suppressed_row(
                        claim,
                        claim_kind,
                        cards,
                        "no_documented_card_behavior_surface",
                    )
                )
            continue

        if claim_kind == "combo_sequence":
            continue

        suppressed.append(
            _suppressed_row(claim, claim_kind, cards, "no_documented_card_behavior_surface")
        )

    return {
        "rows": rows,
        "suppressed": suppressed,
        "option_resolution": option_resolution,
    }


def _rows_for_cards(
    claim: dict[str, Any],
    cards: list[str],
    *,
    condition: str,
    behavior_block: str,
    intent: str,
    roles: list[str],
) -> list[dict[str, Any]]:
    return [
        _attach_behavior_fields(
            _base_row(claim, card_id, condition=condition),
            behavior_block=behavior_block,
            intent=intent,
            roles=roles,
            claim=claim,
        )
        for card_id in cards
    ]


def _base_row(claim: dict[str, Any], card_id: str, *, condition: str) -> dict[str, Any]:
    return {
        "surface": "CardID.json",
        "surface_family": "CARDID.json",
        "card_id": card_id,
        "claim_id": claim.get("claim_id"),
        "condition": condition,
        "confidence": str(claim.get("claim_confidence", claim.get("confidence", "source_backed"))),
        "source_claim_ids": _source_claim_ids(claim),
        "source_refs": [str(item) for item in claim.get("source_refs", [])],
        "claim_confidence": str(claim.get("claim_confidence", claim.get("confidence", "source_backed"))),
    }


def _suppressed_row(
    claim: dict[str, Any],
    claim_kind: str,
    cards: list[str],
    reason: str,
) -> dict[str, Any]:
    return {
        "claim_id": claim.get("claim_id"),
        "claim_kind": claim_kind,
        "cards": cards,
        "reason": reason,
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


def _claim_intent(claim: dict[str, Any], *, fallback: str) -> str:
    return str(claim.get("stance") or claim.get("intent") or fallback)


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


def _option_resolution_rows(
    *,
    claim: dict[str, Any],
    claim_kind: str,
    cards: list[str],
    identity_links: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if claim_kind not in OPTION_CLAIM_KINDS:
        return []

    option_card_id = _claim_option_card_id(claim)
    rows: list[dict[str, Any]] = []
    identity_links = identity_links or {}
    for card_id in cards:
        linked_ids = _linked_card_ids(identity_links.get(card_id, []))
        status = "resolved" if option_card_id and option_card_id in linked_ids else "unresolved"
        rows.append(
            {
                "claim_id": claim.get("claim_id"),
                "card_id": card_id,
                "option_card_id": option_card_id or "",
                "status": status,
            }
        )
    return rows


def _claim_option_card_id(claim: dict[str, Any]) -> str | None:
    for key in OPTION_CARD_KEYS:
        if claim.get(key):
            return str(claim[key])
    return None


def _linked_card_ids(value: Any) -> set[str]:
    if isinstance(value, dict):
        if isinstance(value.get("links"), list):
            value = value["links"]
        else:
            return {str(value["card_id"])} if value.get("card_id") else set()
    if not isinstance(value, list):
        return set()
    linked_ids = set()
    for row in value:
        if isinstance(row, dict) and row.get("card_id"):
            linked_ids.add(str(row["card_id"]))
        elif isinstance(row, str):
            linked_ids.add(row)
    return linked_ids

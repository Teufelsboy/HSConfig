from __future__ import annotations

from typing import Any

from hsconfig.condition_format import lower_runtime_condition


TARGETING_STANCES = {
    "prefer_enemy_hero",
    "prefer_enemy_minion",
    "prefer_friendly_minion",
}
MECHANIC_ROLE_MAP = {
    "battlecry": "battlecry",
    "discover": "discover",
    "dredge": "discover",
    "tradeable": "tradeable",
    "overload": "overload",
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
        if claim_kind == "targeting_rule" and str(claim.get("stance")) in TARGETING_STANCES:
            for card_id in cards:
                row = _base_row(claim, card_id, condition=condition)
                row["intent"] = str(claim["stance"])
                row["roles"] = [str(claim["stance"])]
                card_rows.setdefault(card_id, []).append(row)
                strong_cards.add(card_id)
            continue
        if claim_kind == "mechanic_usage":
            mechanic = str(claim.get("mechanic", claim.get("stance", ""))).lower()
            role = MECHANIC_ROLE_MAP.get(mechanic)
            if role is not None:
                for card_id in cards:
                    row = _base_row(claim, card_id, condition=condition)
                    row["intent"] = f"use_{role}_according_to_card_text"
                    row["roles"] = [role]
                    card_rows.setdefault(card_id, []).append(row)
                continue
        if claim_kind == "card_role":
            for card_id in cards:
                if card_id in strong_cards:
                    continue
                row = _base_row(claim, card_id, condition=condition)
                row["intent"] = "in_hand_priority"
                row["roles"] = [str(claim.get("stance", "deck_card"))]
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

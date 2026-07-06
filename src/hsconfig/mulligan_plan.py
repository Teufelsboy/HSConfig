from __future__ import annotations

from typing import Any

from hsconfig.condition_format import lower_runtime_condition


EARLY_HOLD_ROLES = {"one_drop", "early_pressure", "early_curve", "mulligan_anchor"}


def build_mulligan_plan(
    *,
    deck_name: str,
    claims: list[dict[str, Any]],
    card_roles: dict[str, Any],
) -> dict[str, Any]:
    rules: list[dict[str, Any]] = []
    seen_cards: set[str] = set()

    for claim in claims:
        claim_kind = str(claim.get("claim_kind", claim.get("claim_type", "")))
        if claim_kind not in {"mulligan_keep", "mulligan_discard"}:
            continue
        action = "hold" if claim_kind == "mulligan_keep" else "discard"
        for card_id in _claim_cards(claim):
            if card_id in seen_cards:
                continue
            seen_cards.add(card_id)
            rules.append(
                {
                    "card": card_id,
                    "action": action,
                    "condition": _condition(claim),
                    "reason": str(
                        claim.get(
                            "evidence_text_short",
                            f"source_backed_mulligan_{action}",
                        )
                    ),
                    "confidence": str(claim.get("claim_confidence", claim.get("confidence", "source_backed"))),
                    "source_claim_ids": _source_claim_ids(claim),
                }
            )

    for card_id, role_row in sorted(card_roles.items()):
        if card_id in seen_cards:
            continue
        roles = set(str(role) for role in role_row.get("roles", []))
        if not roles & EARLY_HOLD_ROLES:
            continue
        seen_cards.add(card_id)
        rules.append(
            {
                "card": str(card_id),
                "action": "hold",
                "condition": "*",
                "reason": "early_curve_role_fallback",
                "confidence": str(role_row.get("confidence", "archetype_inferred")),
                "source_claim_ids": [str(item) for item in role_row.get("source_claim_ids", [])],
            }
        )

    has_concrete_keeps = any(row["action"] == "hold" and row["card"] != "*" for row in rules)
    quality: dict[str, Any] = {"has_concrete_keeps": has_concrete_keeps}
    if has_concrete_keeps:
        rules.append(
            {
                "card": "*",
                "action": "discard",
                "reason": "discard_unlisted_cards_after_source_backed_keeps",
            }
        )
    else:
        quality["blocked_reason"] = "no_source_backed_mulligan_keeps"

    return {
        "deck_name": deck_name,
        "rules": rules,
        "quality": quality,
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


def _condition(claim: dict[str, Any]) -> str:
    condition, _unsupported_reason = lower_runtime_condition(
        claim.get("conditions", claim.get("condition", "*"))
    )
    return condition

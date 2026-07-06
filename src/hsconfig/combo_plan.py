from __future__ import annotations

from typing import Any

from hsconfig.condition_format import lower_runtime_condition


def build_combo_plan(
    *,
    deck_cards: set[str],
    claims: list[dict[str, Any]],
) -> dict[str, Any]:
    combos: list[dict[str, Any]] = []
    suppressed: list[dict[str, Any]] = []

    for index, claim in enumerate(claims, start=1):
        claim_kind = str(claim.get("claim_kind", claim.get("claim_type", "")))
        if claim_kind != "combo_sequence":
            continue
        sequence = [str(card) for card in claim.get("sequence", []) if str(card)]
        cards = [str(card) for card in claim.get("cards", []) if str(card)]
        if len(sequence) < 2:
            suppressed.append(_suppression(claim, cards, "missing_ordered_sequence"))
            continue
        missing_cards = [card for card in sequence if card not in deck_cards]
        if missing_cards:
            row = _suppression(claim, sequence, "sequence_card_not_in_deck")
            row["missing_cards"] = missing_cards
            suppressed.append(row)
            continue
        values = _combo_values(claim, sequence)
        value = int(values[0]) if values else 10
        combos.append(
            {
                "rule_id": str(claim.get("claim_id", f"combo_sequence_{index}")),
                "cards": sequence,
                "values": values,
                "operator": ">>",
                "combo": ">>".join(sequence),
                "value": value,
                "condition": _condition(claim),
                "source_claim_ids": _source_claim_ids(claim),
                "confidence": str(claim.get("claim_confidence", claim.get("confidence", "source_backed"))),
                "source_refs": [str(item) for item in claim.get("source_refs", [])],
            }
        )

    return {"combos": combos, "suppressed": suppressed}


def _combo_values(claim: dict[str, Any], sequence: list[str]) -> list[str]:
    raw_values = claim.get("values")
    if isinstance(raw_values, list) and len(raw_values) == len(sequence):
        return [str(value) for value in raw_values]
    value = claim.get("value", claim.get("combo_value", 10))
    try:
        numeric = int(value)
    except (TypeError, ValueError):
        numeric = 10
    return [str(numeric) for _ in sequence]


def _suppression(claim: dict[str, Any], cards: list[str], reason: str) -> dict[str, Any]:
    return {
        "claim_id": claim.get("claim_id"),
        "cards": cards,
        "reason": reason,
    }


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

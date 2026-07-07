from __future__ import annotations

from typing import Any

from hsconfig.condition_format import lower_runtime_condition
from hsconfig.combo_sequence_contract import build_combo_sequence_contract


def build_combo_plan(
    *,
    deck_cards: set[str],
    claims: list[dict[str, Any]],
) -> dict[str, Any]:
    combos: list[dict[str, Any]] = []
    suppressed: list[dict[str, Any]] = []

    for claim in claims:
        claim_kind = str(claim.get("claim_kind", claim.get("claim_type", "")))
        if claim_kind != "combo_sequence":
            continue

        contract = build_combo_sequence_contract(claim, deck_cards)
        if contract.get("emittable") is not True:
            row = _suppression(
                claim,
                [str(card) for card in contract.get("cards", [])],
                str(contract.get("reason", "not_emittable")),
            )
            if "missing_cards" in contract:
                row["missing_cards"] = [str(card) for card in contract["missing_cards"]]
            suppressed.append(row)
            continue

        row = {key: value for key, value in contract.items() if key != "emittable"}
        row["condition"] = _condition(claim)
        row["source_claim_ids"] = _source_claim_ids(claim)
        row["confidence"] = str(
            claim.get("claim_confidence", claim.get("confidence", "source_backed"))
        )
        row["source_refs"] = [str(item) for item in claim.get("source_refs", [])]
        row["combo"] = str(row["operator"]).join(row["cards"])
        row["value"] = _combo_row_value(row["values"])
        combos.append(row)

    return {"combos": combos, "suppressed": suppressed}


def _combo_row_value(values: list[str]) -> int:
    value = values[0] if values else 10
    try:
        return int(value)
    except (TypeError, ValueError):
        return 10


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

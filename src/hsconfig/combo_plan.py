from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from hsconfig.condition_format import lower_runtime_condition
from hsconfig.source_claim_lifecycle import lifecycle_claim_id
from hsconfig.source_document_model import (
    evaluate_combo_surface_gate,
    normalized_claim_kind,
)


def build_combo_plan(
    *,
    deck_cards: set[str],
    claims: list[dict[str, Any]],
    deck_identity: Mapping[str, Any] | None = None,
    verified_source_receipts: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    combos: list[dict[str, Any]] = []
    suppressed: list[dict[str, Any]] = []

    for claim in claims:
        claim_kind = normalized_claim_kind(claim)
        gate_evaluation = evaluate_combo_surface_gate(
            claim,
            deck_identity=deck_identity,
            deck_cards=deck_cards,
            verified_source_receipts=verified_source_receipts,
            contract_claim_id=lifecycle_claim_id(claim),
        )
        gate = gate_evaluation.decision
        if not gate.allowed:
            if _is_combo_surface_candidate(claim, claim_kind):
                contract = gate_evaluation.contract
                row = _suppression(
                    claim,
                    [
                        str(card)
                        for card in contract.get("cards", _claim_cards(claim))
                    ],
                    gate.reason,
                )
                if "missing_cards" in contract:
                    row["missing_cards"] = [
                        str(card) for card in contract["missing_cards"]
                    ]
                suppressed.append(row)
            continue

        contract = gate_evaluation.contract
        row = {key: value for key, value in contract.items() if key != "emittable"}
        _with_claim_id(row, claim)
        condition, condition_error = _condition(claim)
        if condition_error is not None:
            suppressed.append(
                _suppression(
                    claim,
                    [str(card) for card in contract.get("cards", [])],
                    condition_error,
                )
            )
            continue
        row["condition"] = condition
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
    return _with_claim_id(
        {
            "cards": cards,
            "reason": reason,
        },
        claim,
    )


def _claim_cards(claim: dict[str, Any]) -> list[str]:
    cards = claim.get("cards", [])
    if isinstance(cards, str):
        cards = [cards]
    return [str(card) for card in cards if str(card)]


def _is_combo_surface_candidate(claim: dict[str, Any], claim_kind: str) -> bool:
    if claim_kind == "combo_sequence":
        return True
    surface_fields = (
        "surface",
        "target_surface",
        "runtime_surface",
        "runtime_surface_family",
    )
    for field in surface_fields:
        if "combo" in str(claim.get(field, "")).lower():
            return True
    return False


def _source_claim_ids(claim: dict[str, Any]) -> list[str]:
    if isinstance(claim.get("source_claim_ids"), list):
        return [str(item) for item in claim["source_claim_ids"]]
    if claim.get("claim_id"):
        return [str(claim["claim_id"])]
    return []


def _with_claim_id(row: dict[str, Any], claim: dict[str, Any]) -> dict[str, Any]:
    claim_id = lifecycle_claim_id(claim)
    if claim_id:
        row["claim_id"] = claim_id
    return row


def _condition(claim: dict[str, Any]) -> tuple[str, str | None]:
    return lower_runtime_condition(
        claim.get("conditions", claim.get("condition", "*"))
    )

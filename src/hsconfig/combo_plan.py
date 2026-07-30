from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from hsconfig.condition_format import lower_runtime_condition
from hsconfig.package_domain import (
    ComboDecisionModel,
    ComboPlanModel,
    ComboSuppressionModel,
)
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
    return build_typed_combo_plan(
        deck_cards=deck_cards,
        claims=claims,
        deck_identity=deck_identity,
        verified_source_receipts=verified_source_receipts,
    ).to_report()


def build_typed_combo_plan(
    *,
    deck_cards: set[str],
    claims: list[dict[str, Any]],
    deck_identity: Mapping[str, Any] | None = None,
    verified_source_receipts: Sequence[Mapping[str, Any]] | None = None,
) -> ComboPlanModel:
    decisions: list[ComboDecisionModel] = []
    suppressions: list[ComboSuppressionModel] = []

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
                suppressions.append(
                    _typed_suppression(
                        claim,
                        [
                            str(card)
                            for card in contract.get(
                                "cards",
                                _claim_cards(claim),
                            )
                        ],
                        gate.reason,
                        missing_cards=[
                            str(card)
                            for card in contract.get("missing_cards", ())
                        ],
                    )
                )
            continue

        contract = gate_evaluation.contract
        row = {key: value for key, value in contract.items() if key != "emittable"}
        _with_claim_id(row, claim)
        condition, condition_error = _condition(claim)
        if condition_error is not None:
            suppressions.append(
                _typed_suppression(
                    claim,
                    [str(card) for card in contract.get("cards", [])],
                    condition_error,
                )
            )
            continue
        row["condition"] = condition
        row["source_claim_ids"] = _source_claim_ids(claim)
        row["confidence"] = str(
            claim.get(
                "claim_confidence",
                claim.get("confidence", "source_backed"),
            )
        )
        row["source_refs"] = [str(item) for item in claim.get("source_refs", [])]
        decisions.append(ComboDecisionModel.from_plan_row(row))

    return ComboPlanModel(
        decisions=tuple(decisions),
        suppressions=tuple(sorted(suppressions, key=lambda row: row.identity)),
    )


def _typed_suppression(
    claim: dict[str, Any],
    cards: list[str],
    reason: str,
    *,
    missing_cards: list[str] | None = None,
) -> ComboSuppressionModel:
    return ComboSuppressionModel(
        cards=tuple(cards),
        reason_code=reason,
        claim_id=lifecycle_claim_id(claim) or None,
        missing_cards=tuple(missing_cards or ()),
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

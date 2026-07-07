from __future__ import annotations

from typing import Any


SUPPORTED_TIMING_TO_OPERATOR = {"same_turn": ">>", "cross_turn": ">->"}


def build_combo_sequence_contract(claim: dict[str, Any], deck_cards: set[str]) -> dict[str, Any]:
    sequence = [str(card) for card in claim.get("sequence", claim.get("cards", [])) if str(card)]
    timing_kind = str(claim.get("timing_kind", "")).strip()
    if len(sequence) < 2:
        return {"emittable": False, "reason": "sequence_too_short", "cards": sequence}
    missing = [card for card in sequence if card not in deck_cards]
    if missing:
        return {
            "emittable": False,
            "reason": "card_not_in_deck",
            "cards": sequence,
            "missing_cards": missing,
        }
    if timing_kind not in SUPPORTED_TIMING_TO_OPERATOR:
        return {"emittable": False, "reason": "missing_timing", "cards": sequence}
    operator = str(claim.get("operator", SUPPORTED_TIMING_TO_OPERATOR[timing_kind]))
    if operator != SUPPORTED_TIMING_TO_OPERATOR[timing_kind]:
        return {"emittable": False, "reason": "operator_timing_mismatch", "cards": sequence}
    values = [str(value) for value in claim.get("values", [])]
    if len(values) != len(sequence):
        return {"emittable": False, "reason": "value_segment_mismatch", "cards": sequence}
    claim_id = str(claim["claim_id"])
    return {
        "emittable": True,
        "rule_id": f"{claim_id}_combo",
        "cards": sequence,
        "timing_kind": timing_kind,
        "operator": operator,
        "values": values,
        "condition": claim.get("condition", "*"),
        "source_claim_ids": [claim_id],
        "confidence": claim.get("confidence", "source_backed"),
    }

from __future__ import annotations

from typing import Any


def compile_mulligan(
    contract: dict[str, Any] | None = None,
    *,
    deck_name: str | None = None,
    rows: list[dict[str, Any]] | None = None,
    add_discard_fallback: bool = True,
) -> dict[str, Any]:
    contract = contract or {}
    deck_name = deck_name or str(contract.get("deck_name", "Deck"))
    anchors = _anchors_from_contract(contract)
    if rows is not None:
        anchors.extend(_anchors_from_rows(rows))

    config: dict[str, Any] = {
        "GameCardId": "Mulligan",
        "ConfigComment": f"{deck_name} generated mulligan rules",
        "Mulligan": {"values": []},
    }
    for anchor in sorted(anchors, key=lambda row: (row["card_id"], row.get("rule_id", ""))):
        card_id = str(anchor["card_id"])
        config["Mulligan"]["values"].append(
            {
                "comment": f"{deck_name}: {anchor.get('rule_id', f'{card_id}_mulligan_hold')}",
                "mulligan": card_id,
                "condition": anchor.get("condition", "*"),
                "value": anchor.get("intent", "hold"),
                "source_rule_id": anchor.get("rule_id", f"{card_id}_mulligan_hold"),
                "source_claim_ids": list(anchor.get("source_claim_ids", [])),
                "confidence": anchor.get("confidence", "source_backed"),
            }
        )

    if add_discard_fallback:
        config["Mulligan"]["values"].append(
            {
                "comment": f"{deck_name}: discard cards not covered by guide-backed holds",
                "mulligan": "*",
                "condition": "*",
                "value": "discard",
                "source_rule_id": "default_mulligan_discard",
                "source_claim_ids": [],
                "confidence": "generic_low_confidence",
            }
        )
    return config


def _anchors_from_contract(contract: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "rule_id": str(anchor.get("rule_id", f"{anchor['card_id']}_mulligan_hold")),
            "card_id": str(anchor["card_id"]),
            "intent": str(anchor.get("intent", "hold")),
            "condition": anchor.get("condition", "*"),
            "source_claim_ids": list(anchor.get("source_claim_ids", [])),
            "confidence": anchor.get("confidence", "source_backed"),
        }
        for anchor in contract.get("mulligan_anchors", [])
    ]


def _anchors_from_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    anchors = []
    for row in rows:
        if row.get("surface") not in {"Mulligan.json", "Mulligan"}:
            continue
        anchors.append(
            {
                "rule_id": str(row.get("rule_id", f"{row['card_id']}_mulligan_hold")),
                "card_id": str(row["card_id"]),
                "intent": str(row.get("intent", "hold")),
                "condition": row.get("condition", "*"),
                "source_claim_ids": list(row.get("source_claim_ids", [])),
                "confidence": row.get("confidence", "source_backed"),
            }
        )
    return anchors

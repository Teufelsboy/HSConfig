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
    plan = contract.get("mulligan_plan")
    preserve_order = False
    if isinstance(plan, dict):
        anchors = _anchors_from_plan(plan)
        add_discard_fallback = False
        preserve_order = True
    else:
        anchors = _anchors_from_contract(contract)
    if rows is not None:
        anchors.extend(_anchors_from_rows(rows))

    config: dict[str, Any] = {
        "GameCardId": "Mulligan",
        "ConfigComment": f"{deck_name} generated mulligan rules",
        "Mulligan": {"values": []},
    }
    ordered_anchors = anchors if preserve_order else sorted(
        anchors, key=lambda row: (row["card_id"], row.get("rule_id", ""))
    )
    for anchor in ordered_anchors:
        card_id = str(anchor["card_id"])
        config["Mulligan"]["values"].append(
            {
                "comment": f"{deck_name}: {anchor.get('rule_id', f'{card_id}_mulligan_hold')}",
                "mulligan": card_id,
                "condition": anchor.get("condition", "*"),
                "value": anchor.get("intent", "hold"),
            }
        )

    if add_discard_fallback and anchors:
        config["Mulligan"]["values"].append(
            {
                "comment": f"{deck_name}: discard cards not covered by guide-backed holds",
                "mulligan": "*",
                "condition": "*",
                "value": "discard",
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


def _anchors_from_plan(plan: dict[str, Any]) -> list[dict[str, Any]]:
    anchors = []
    for index, rule in enumerate(plan.get("rules", []), start=1):
        if not isinstance(rule, dict):
            continue
        card_id = str(rule.get("card", ""))
        if not card_id:
            continue
        anchors.append(
            {
                "rule_id": str(rule.get("rule_id", f"{card_id}_mulligan_{index}")),
                "card_id": card_id,
                "intent": str(rule.get("action", rule.get("intent", "hold"))),
                "condition": rule.get("condition", "*"),
                "source_claim_ids": list(rule.get("source_claim_ids", [])),
                "confidence": rule.get("confidence", "source_backed"),
            }
        )
    return anchors


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

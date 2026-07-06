from __future__ import annotations

from typing import Any


SUPPORTED_OPERATORS = {">>", ">->"}


def compile_combo(
    contract: dict[str, Any] | None = None,
    *,
    deck_name: str | None = None,
    sequences: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    contract = contract or {}
    deck_name = deck_name or str(contract.get("deck_name", "Deck"))
    combos = sequences if sequences is not None else list(contract.get("combos", []))
    if not combos:
        return None

    values = []
    for sequence in combos:
        cards = [str(card) for card in sequence.get("cards", [])]
        value_parts = [str(value) for value in sequence.get("values", [])]
        operator = str(sequence.get("operator", ">>"))
        rule_id = str(sequence.get("rule_id", "combo_sequence"))
        if operator not in SUPPORTED_OPERATORS or len(cards) < 2 or len(cards) != len(value_parts):
            raise ValueError(f"Invalid combo sequence {rule_id}")
        values.append(
            {
                "comment": f"{deck_name}: {rule_id}",
                "condition": sequence.get("condition", "*"),
                "combo": operator.join(cards),
                "value": operator.join(value_parts),
            }
        )
    return {
        "GameCardId": "Combo",
        "ConfigComment": f"{deck_name} generated combos",
        "ComboList": {"values": values},
    }

from __future__ import annotations

from collections import defaultdict
from typing import Any


def build_claim_conflict_report(claims: list[dict[str, Any]]) -> dict[str, Any]:
    conflicts: list[dict[str, Any]] = []
    conflicts.extend(_mulligan_conflicts(claims))
    conflicts.extend(_targeting_conflicts(claims))
    conflicts.extend(_combo_timing_conflicts(claims))
    conflicts.extend(_option_choice_conflicts(claims))
    return {"conflict_count": len(conflicts), "conflicts": conflicts}


def _mulligan_conflicts(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_card: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for claim in claims:
        kind = str(claim.get("claim_kind", ""))
        if kind not in {"mulligan_keep", "mulligan_discard"}:
            continue
        for card_id in _cards(claim):
            by_card[card_id][kind].add(str(claim.get("claim_id", "")))
    conflicts = []
    for card_id, kinds in sorted(by_card.items()):
        if {"mulligan_keep", "mulligan_discard"} <= set(kinds):
            claim_ids = sorted(set().union(*kinds.values()))
            conflicts.append(
                {
                    "card_id": card_id,
                    "conflict_family": "mulligan",
                    "claim_ids": claim_ids,
                    "resolution": "downgrade_to_report_visible_conflict",
                }
            )
    return conflicts


def _targeting_conflicts(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_card: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for claim in claims:
        if str(claim.get("claim_kind", "")) != "targeting_rule":
            continue
        scope = _qualifier(claim, "target_scope") or str(
            claim.get("target", claim.get("stance", ""))
        )
        if not scope:
            continue
        for card_id in _cards(claim):
            by_card[card_id][scope].add(str(claim.get("claim_id", "")))
    return _value_conflicts(by_card, "targeting")


def _combo_timing_conflicts(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_sequence: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for claim in claims:
        if str(claim.get("claim_kind", "")) != "combo_sequence":
            continue
        sequence = tuple(str(card) for card in claim.get("sequence", claim.get("cards", [])))
        if not sequence:
            continue
        timing = str(claim.get("timing_kind", _qualifier(claim, "timing") or ""))
        if not timing:
            continue
        by_sequence["|".join(sequence)][timing].add(str(claim.get("claim_id", "")))
    return _value_conflicts(by_sequence, "combo_timing", key_name="sequence_key")


def _option_choice_conflicts(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_card: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for claim in claims:
        if str(claim.get("claim_kind", "")) not in {
            "discover_choice",
            "choose_one_choice",
        }:
            continue
        option = str(
            claim.get(
                "option_card_id",
                claim.get(
                    "option_card",
                    claim.get("choice_card_id", claim.get("choice_card", "")),
                ),
            )
        )
        if not option:
            continue
        for card_id in _cards(claim):
            by_card[card_id][option].add(str(claim.get("claim_id", "")))
    return _value_conflicts(by_card, "option_choice")


def _value_conflicts(
    grouped: dict[str, dict[str, set[str]]],
    family: str,
    *,
    key_name: str = "card_id",
) -> list[dict[str, Any]]:
    conflicts = []
    for key, values in sorted(grouped.items()):
        clean_values = {value: ids for value, ids in values.items() if value}
        if len(clean_values) <= 1:
            continue
        claim_ids = sorted(set().union(*clean_values.values()))
        conflicts.append(
            {
                key_name: key,
                "conflict_family": family,
                "values": sorted(clean_values),
                "claim_ids": claim_ids,
                "resolution": "downgrade_to_report_visible_conflict",
            }
        )
    return conflicts


def _cards(claim: dict[str, Any]) -> list[str]:
    cards = claim.get("cards", [])
    if isinstance(cards, str):
        cards = [cards]
    return [str(card) for card in cards if str(card)]


def _qualifier(claim: dict[str, Any], key: str) -> str:
    qualifiers = claim.get("semantic_qualifiers", {})
    if not isinstance(qualifiers, dict):
        return ""
    value = qualifiers.get(key, "")
    return str(value) if not isinstance(value, list) else "|".join(str(item) for item in value)

from __future__ import annotations

from collections import defaultdict
from typing import Any


def build_claim_conflict_report(claims: list[dict[str, Any]]) -> dict[str, Any]:
    conflicts: list[dict[str, Any]] = []
    conflicts.extend(_mulligan_conflicts(claims))
    conflicts.extend(_targeting_conflicts(claims))
    conflicts.extend(_combo_timing_conflicts(claims))
    conflicts.extend(_option_choice_conflicts(claims))
    conflicts.extend(_role_bad_pattern_conflicts(claims))
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


def _role_bad_pattern_conflicts(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    usage_by_card: dict[str, list[tuple[str, str]]] = defaultdict(list)
    bad_patterns_by_card: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for claim in claims:
        claim_id = str(claim.get("claim_id", ""))
        purposes = _claim_purposes(claim)
        if not purposes:
            continue
        destination = (
            bad_patterns_by_card
            if str(claim.get("claim_kind", "")) == "known_bad_pattern"
            else usage_by_card
        )
        for card_id in _cards(claim):
            destination[card_id].extend((claim_id, purpose) for purpose in purposes)

    conflicts = []
    for card_id in sorted(set(usage_by_card) & set(bad_patterns_by_card)):
        matches = {
            (usage_id, usage, bad_id, bad)
            for usage_id, usage in usage_by_card[card_id]
            for bad_id, bad in bad_patterns_by_card[card_id]
            if _purpose_conflicts_with_bad_pattern(usage, bad)
        }
        if not matches:
            continue
        conflicts.append(
            {
                "card_id": card_id,
                "conflict_family": "role_vs_known_bad_pattern",
                "values": sorted(f"{usage}->{bad}" for _, usage, _, bad in matches),
                "claim_ids": sorted(
                    {claim_id for usage_id, _, bad_id, _ in matches for claim_id in (usage_id, bad_id)}
                ),
                "resolution": "downgrade_to_report_visible_conflict",
            }
        )
    return conflicts


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


def _claim_purposes(claim: dict[str, Any]) -> set[str]:
    values = [
        claim.get("stance"),
        claim.get("intent"),
        claim.get("target"),
        _qualifier(claim, "target_scope"),
    ]
    purposes = set()
    for value in values:
        if not isinstance(value, str):
            continue
        normalized = _normalize_purpose(value)
        if normalized:
            purposes.add(normalized)
    return purposes


def _purpose_conflicts_with_bad_pattern(usage: str, bad_pattern: str) -> bool:
    prohibited = _prohibited_purpose(bad_pattern)
    if not prohibited:
        return False
    usage_tokens = set(usage.split("_"))
    prohibited_tokens = set(prohibited.split("_"))
    return (
        usage == prohibited
        or usage.endswith(f"_{prohibited}")
        or prohibited.endswith(f"_{usage}")
        or prohibited_tokens <= usage_tokens
    )


def _prohibited_purpose(value: str) -> str:
    for prefix in ("do_not_", "dont_", "avoid_", "never_", "not_"):
        if value.startswith(prefix):
            value = value.removeprefix(prefix)
            break
    else:
        return value
    return value.removeprefix("target_")


def _normalize_purpose(value: Any) -> str:
    normalized = "_".join(str(value).strip().lower().replace("-", " ").split())
    for prefix in ("use_", "prefer_", "prioritize_", "target_", "play_"):
        if normalized.startswith(prefix):
            return normalized.removeprefix(prefix)
    return normalized

from __future__ import annotations

from typing import Any

from hsconfig.condition_format import lower_runtime_condition
from hsconfig.mulligan_selector import normalize_mulligan_selector
from hsconfig.source_document_model import can_lower_to_mulligan, normalized_claim_kind


SURFACE_REJECTION_REASONS = {
    "claim_kind_not_mulligan_surface",
}

def build_mulligan_plan(
    *,
    deck_name: str,
    claims: list[dict[str, Any]],
    card_roles: dict[str, Any],
) -> dict[str, Any]:
    rules: list[dict[str, Any]] = []
    suppressed_rules: list[dict[str, Any]] = []
    seen_rule_keys: set[tuple[Any, ...]] = set()

    for claim in claims:
        claim_kind = normalized_claim_kind(claim)
        claim_cards = _claim_cards(claim)
        gate = can_lower_to_mulligan(claim, card_roles=card_roles)
        if not gate.allowed:
            if claim_cards:
                suppressed_rules.append(
                    {
                        "card": claim_cards[0],
                        "action": "hold" if claim_kind == "mulligan_keep" else "none",
                        "reason": gate.reason,
                        "source_claim_ids": _source_claim_ids(claim),
                    }
                )
            continue
        action = "hold" if claim_kind == "mulligan_keep" else "discard"
        condition, unsupported_reason = lower_runtime_condition(
            claim.get("conditions", claim.get("condition", "*"))
        )
        for card_id, selector_seed, explicit_selector in _selector_rows_from_claim(
            claim, claim_cards
        ):
            selector_info = normalize_mulligan_selector(
                {
                    "card": card_id,
                    "selector_kind": claim.get("selector_kind", ""),
                    "selector": selector_seed,
                }
            )
            if not selector_info["supported"]:
                suppressed_rules.append(
                    {
                        "card": card_id,
                        "selector": selector_info["selector"],
                        "action": action,
                        "reason": selector_info["reason"],
                        "source_claim_ids": _source_claim_ids(claim),
                    }
                )
                continue
            selector_cards = [str(card) for card in selector_info.get("selector_cards", [])]
            if (
                explicit_selector
                and selector_cards
                and not set(selector_cards).issubset(set(claim_cards))
            ):
                suppressed_rules.append(
                    {
                        "card": card_id,
                        "selector_kind": selector_info["selector_kind"],
                        "selector": selector_info["selector"],
                        "selector_cards": selector_cards,
                        "claim_cards": claim_cards,
                        "action": action,
                        "reason": "selector_cards_not_in_claim",
                        "source_claim_ids": _source_claim_ids(claim),
                    }
                )
                continue
            if explicit_selector and selector_cards:
                card_id = selector_cards[0]
            if unsupported_reason is not None:
                suppressed_rules.append(
                    {
                        "card": card_id,
                        "selector_kind": selector_info["selector_kind"],
                        "selector": selector_info["selector"],
                        "action": action,
                        "reason": _mulligan_condition_reason(unsupported_reason),
                        "source_claim_ids": _source_claim_ids(claim),
                    }
                )
                continue
            rule = {
                "card": card_id,
                "selector_kind": selector_info["selector_kind"],
                "selector": selector_info["selector"],
                "action": action,
                "condition": condition,
                "reason": str(
                    claim.get(
                        "evidence_text_short",
                        f"source_backed_mulligan_{action}",
                    )
                ),
                "confidence": str(claim.get("claim_confidence", claim.get("confidence", "source_backed"))),
                "source_claim_ids": _source_claim_ids(claim),
                "source_type": "source_claim",
            }
            if selector_cards:
                rule["selector_cards"] = selector_cards
            key = mulligan_rule_key(rule)
            if key in seen_rule_keys:
                continue
            seen_rule_keys.add(key)
            rules.append(rule)

    rules = _apply_mulligan_precedence(rules)
    has_concrete_keeps = any(
        row["action"] == "hold" and row.get("selector_kind") != "wildcard" for row in rules
    )
    suppressed_reasons = _suppressed_reason_counts(suppressed_rules)
    source_backed_rule_count = sum(
        1
        for row in rules
        if row.get("source_type") == "source_claim" and row.get("selector_kind") != "wildcard"
    )
    source_backed_keep_rule_count = sum(
        1
        for row in rules
        if row.get("source_type") == "source_claim"
        and row.get("selector_kind") != "wildcard"
        and row.get("action") == "hold"
    )
    has_source_backed_keeps = source_backed_keep_rule_count > 0
    actionable_suppressed_rules = [
        row
        for row in suppressed_rules
        if str(row.get("reason")) not in SURFACE_REJECTION_REASONS
    ]
    first_gap_reason = (
        str(actionable_suppressed_rules[0]["reason"])
        if actionable_suppressed_rules
        else ("none" if has_source_backed_keeps else "no_source_backed_mulligan_keeps")
    )
    quality: dict[str, Any] = {
        "has_concrete_keeps": has_concrete_keeps,
        "status": "rich" if has_source_backed_keeps else "thin",
        "first_gap_reason": first_gap_reason,
        "source_backed_rule_count": source_backed_rule_count,
        "source_backed_keep_rule_count": source_backed_keep_rule_count,
        "suppressed_rule_count": len(suppressed_rules),
        "suppressed_reasons": suppressed_reasons,
    }
    if has_concrete_keeps:
        rules.append(
            {
                "card": "*",
                "selector_kind": "wildcard",
                "selector": "*",
                "action": "discard",
                "condition": "*",
                "reason": "discard_unlisted_cards_after_source_backed_keeps",
            }
        )
    else:
        quality["blocked_reason"] = "no_source_backed_mulligan_keeps"

    return {
        "deck_name": deck_name,
        "rules": rules,
        "suppressed_rules": suppressed_rules,
        "quality": quality,
    }


def mulligan_rule_key(rule: dict[str, Any]) -> tuple[Any, ...]:
    return (
        rule.get("card"),
        rule.get("selector_kind"),
        rule.get("selector"),
        tuple(str(item) for item in rule.get("selector_cards", [])),
        rule.get("action"),
        rule.get("condition", "*"),
        tuple(sorted(str(item) for item in rule.get("source_claim_ids", []))),
    )


def _apply_mulligan_precedence(rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    key_counts: dict[tuple[Any, Any], int] = {}
    for rule in rules:
        key = (rule.get("selector", rule.get("card")), rule.get("condition", "*"))
        key_counts[key] = key_counts.get(key, 0) + 1

    def sort_key(indexed_rule: tuple[int, dict[str, Any]]) -> tuple[Any, ...]:
        index, rule = indexed_rule
        key = (rule.get("selector", rule.get("card")), rule.get("condition", "*"))
        has_exact_conflict = key_counts[key] > 1
        action_rank = 0 if has_exact_conflict and rule.get("action") == "discard" else 1
        fallback_rank = 1 if rule.get("source_type") == "fallback" else 0
        return (fallback_rank, action_rank, index)

    return [rule for _index, rule in sorted(enumerate(rules), key=sort_key)]


def _claim_cards(claim: dict[str, Any]) -> list[str]:
    cards = claim.get("cards", [])
    if isinstance(cards, str):
        cards = [cards]
    return [str(card) for card in cards if str(card)]


def _selector_rows_from_claim(
    claim: dict[str, Any],
    claim_cards: list[str],
) -> list[tuple[str, str, bool]]:
    if claim.get("selector") is not None:
        selector = str(claim.get("selector", "")).strip()
        card_id = "*" if selector == "*" else (claim_cards[0] if claim_cards else selector)
        return [(card_id, selector, True)]
    return [(card_id, card_id, False) for card_id in claim_cards]


def _source_claim_ids(claim: dict[str, Any]) -> list[str]:
    if isinstance(claim.get("source_claim_ids"), list):
        return [str(item) for item in claim["source_claim_ids"]]
    if claim.get("claim_id"):
        return [str(claim["claim_id"])]
    return []


def _mulligan_condition_reason(reason: str) -> str:
    if reason == "unsupported_condition":
        return "unsupported_mulligan_condition"
    return reason


def _suppressed_reason_counts(suppressed_rules: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in suppressed_rules:
        reason = str(row.get("reason", "unknown"))
        counts[reason] = counts.get(reason, 0) + 1
    return counts

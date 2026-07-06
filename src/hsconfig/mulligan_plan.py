from __future__ import annotations

from typing import Any

from hsconfig.condition_format import lower_runtime_condition
from hsconfig.mulligan_selector import normalize_mulligan_selector


EARLY_HOLD_ROLES = {"one_drop", "early_pressure", "early_curve", "mulligan_anchor"}


def build_mulligan_plan(
    *,
    deck_name: str,
    claims: list[dict[str, Any]],
    card_roles: dict[str, Any],
) -> dict[str, Any]:
    rules: list[dict[str, Any]] = []
    suppressed_rules: list[dict[str, Any]] = []
    seen_rule_keys: set[tuple[Any, ...]] = set()
    claimed_cards: set[str] = set()

    for claim in claims:
        claim_kind = str(claim.get("claim_kind", claim.get("claim_type", "")))
        if claim_kind not in {"mulligan_keep", "mulligan_discard"}:
            continue
        action = "hold" if claim_kind == "mulligan_keep" else "discard"
        claim_cards = _claim_cards(claim)
        condition, unsupported_reason = lower_runtime_condition(
            claim.get("conditions", claim.get("condition", "*"))
        )
        for card_id, selector_seed in _selector_rows_from_claim(claim, claim_cards):
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
            if unsupported_reason is not None:
                suppressed_rules.append(
                    {
                        "card": card_id,
                        "selector_kind": selector_info["selector_kind"],
                        "selector": selector_info["selector"],
                        "action": action,
                        "reason": unsupported_reason,
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
            key = mulligan_rule_key(rule)
            if key in seen_rule_keys:
                continue
            seen_rule_keys.add(key)
            claimed_cards.update(claim_cards or [card_id])
            rules.append(rule)

    for card_id, role_row in sorted(card_roles.items()):
        if card_id in claimed_cards:
            continue
        roles = set(str(role) for role in role_row.get("roles", []))
        if not roles & EARLY_HOLD_ROLES:
            continue
        rule = {
            "card": str(card_id),
            "selector_kind": "card",
            "selector": str(card_id),
            "action": "hold",
            "condition": "*",
            "reason": "early_curve_role_fallback",
            "confidence": str(role_row.get("confidence", "archetype_inferred")),
            "source_claim_ids": [str(item) for item in role_row.get("source_claim_ids", [])],
            "source_type": "fallback",
        }
        key = mulligan_rule_key(rule)
        if key in seen_rule_keys:
            continue
        seen_rule_keys.add(key)
        claimed_cards.add(card_id)
        rules.append(rule)

    rules = _apply_mulligan_precedence(rules)
    has_concrete_keeps = any(
        row["action"] == "hold" and row.get("selector_kind") != "wildcard" for row in rules
    )
    quality: dict[str, Any] = {"has_concrete_keeps": has_concrete_keeps}
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
) -> list[tuple[str, str]]:
    if claim.get("selector") is not None:
        selector = str(claim.get("selector", "")).strip()
        card_id = "*" if selector == "*" else (claim_cards[0] if claim_cards else selector)
        return [(card_id, selector)]
    return [(card_id, card_id) for card_id in claim_cards]


def _source_claim_ids(claim: dict[str, Any]) -> list[str]:
    if isinstance(claim.get("source_claim_ids"), list):
        return [str(item) for item in claim["source_claim_ids"]]
    if claim.get("claim_id"):
        return [str(claim["claim_id"])]
    return []

from __future__ import annotations

from typing import Any

from hsconfig.autonomous_mulligan_policy import build_policy_backed_mulligan_rules
from hsconfig.condition_format import lower_runtime_condition
from hsconfig.mulligan_selector import normalize_mulligan_selector
from hsconfig.source_claim_lifecycle import lifecycle_claim_id
from hsconfig.source_document_model import can_lower_to_mulligan, normalized_claim_kind


SURFACE_REJECTION_REASONS = {
    "claim_kind_not_mulligan_surface",
}

def build_mulligan_plan(
    *,
    deck_name: str,
    claims: list[dict[str, Any]],
    card_roles: dict[str, Any],
    deck_cards: dict[str, Any] | list[dict[str, Any]] | None = None,
    allow_policy_backed: bool = False,
    policy_excluded_card_ids: set[str] | None = None,
) -> dict[str, Any]:
    rules: list[dict[str, Any]] = []
    suppressed_rules: list[dict[str, Any]] = []
    rules_by_key: dict[tuple[Any, ...], dict[str, Any]] = {}
    merged_duplicate_rule_count = 0

    for claim in claims:
        claim_kind = normalized_claim_kind(claim)
        claim_cards = _claim_cards(claim)
        gate = can_lower_to_mulligan(claim, card_roles=card_roles)
        if not gate.allowed:
            if claim_cards:
                suppressed_rules.append(
                    _with_claim_id(
                        {
                            "card": claim_cards[0],
                            "action": "hold" if claim_kind == "mulligan_keep" else "none",
                            "reason": gate.reason,
                            "source_claim_ids": _source_claim_ids(claim),
                        },
                        claim,
                    )
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
                    _with_claim_id(
                        {
                            "card": card_id,
                            "selector": selector_info["selector"],
                            "action": action,
                            "reason": selector_info["reason"],
                            "source_claim_ids": _source_claim_ids(claim),
                        },
                        claim,
                    )
                )
                continue
            selector_cards = [str(card) for card in selector_info.get("selector_cards", [])]
            if (
                explicit_selector
                and selector_cards
                and not set(selector_cards).issubset(set(claim_cards))
            ):
                suppressed_rules.append(
                    _with_claim_id(
                        {
                            "card": card_id,
                            "selector_kind": selector_info["selector_kind"],
                            "selector": selector_info["selector"],
                            "selector_cards": selector_cards,
                            "claim_cards": claim_cards,
                            "action": action,
                            "reason": "selector_cards_not_in_claim",
                            "source_claim_ids": _source_claim_ids(claim),
                        },
                        claim,
                    )
                )
                continue
            if explicit_selector and selector_cards:
                card_id = selector_cards[0]
            if unsupported_reason is not None:
                suppressed_rules.append(
                    _with_claim_id(
                        {
                            "card": card_id,
                            "selector_kind": selector_info["selector_kind"],
                            "selector": selector_info["selector"],
                            "action": action,
                            "reason": _mulligan_condition_reason(unsupported_reason),
                            "source_claim_ids": _source_claim_ids(claim),
                        },
                        claim,
                    )
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
            _with_claim_id(rule, claim)
            if selector_cards:
                rule["selector_cards"] = selector_cards
            if _add_or_merge_mulligan_rule(rules, rules_by_key, rule):
                merged_duplicate_rule_count += 1

    rules = _apply_mulligan_precedence(rules)
    policy_result = {
        "status": "not_needed",
        "rules": [],
        "suppressed": [],
        "candidate_count": 0,
        "selected_count": 0,
        "excluded_count": 0,
    }
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
    if allow_policy_backed and not has_source_backed_keeps:
        policy_result = build_policy_backed_mulligan_rules(
            deck_name=deck_name,
            deck_cards=deck_cards or {},
            card_roles=card_roles,
            excluded_card_ids=_source_mulligan_intent_cards_for_policy(
                claims=claims,
                rules=rules,
                suppressed_rules=suppressed_rules,
                extra_card_ids=policy_excluded_card_ids or set(),
            ),
        )
        for row in policy_result["rules"]:
            if _add_or_merge_mulligan_rule(rules, rules_by_key, row):
                merged_duplicate_rule_count += 1
        for row in policy_result["suppressed"]:
            suppressed_rules.append(row)
        rules = _apply_mulligan_precedence(rules)

    has_concrete_keeps = any(
        row["action"] == "hold" and row.get("selector_kind") != "wildcard" for row in rules
    )
    suppressed_reasons = _suppressed_reason_counts(suppressed_rules)
    policy_backed_rule_count = sum(
        1
        for row in rules
        if row.get("source_type") == "policy_backed_autonomous_mulligan"
        and row.get("selector_kind") != "wildcard"
    )
    policy_backed_keep_rule_count = sum(
        1
        for row in rules
        if row.get("source_type") == "policy_backed_autonomous_mulligan"
        and row.get("selector_kind") != "wildcard"
        and row.get("action") == "hold"
    )
    policy_lanes = sorted(
        {
            str(row.get("policy_lane", "generic"))
            for row in rules
            if row.get("source_type") == "policy_backed_autonomous_mulligan"
            and row.get("selector_kind") != "wildcard"
        }
    )
    policy_reasons = sorted(
        {
            str(row.get("policy_reason", "")).strip()
            for row in rules
            if row.get("source_type") == "policy_backed_autonomous_mulligan"
            and str(row.get("policy_reason", "")).strip()
        }
    )
    has_policy_backed_keeps = policy_backed_keep_rule_count > 0
    actionable_suppressed_rules = [
        row
        for row in suppressed_rules
        if str(row.get("reason")) not in SURFACE_REJECTION_REASONS
    ]
    missing_keep_reason = (
        "no_source_backed_or_policy_backed_mulligan_keeps"
        if allow_policy_backed
        else "no_source_backed_mulligan_keeps"
    )
    first_gap_reason = (
        str(actionable_suppressed_rules[0]["reason"])
        if actionable_suppressed_rules
        else (
            "none"
            if has_source_backed_keeps
            else (
                "policy_backed_autonomous_mulligan"
                if has_policy_backed_keeps
                else missing_keep_reason
            )
        )
    )
    runtime_rule_count = sum(
        1
        for row in rules
        if row.get("selector_kind") != "wildcard" or row.get("action") != "discard"
    )
    quality: dict[str, Any] = {
        "has_concrete_keeps": has_concrete_keeps,
        "status": (
            "rich"
            if has_source_backed_keeps
            else ("policy_backed" if has_policy_backed_keeps else "thin")
        ),
        "first_gap_reason": first_gap_reason,
        "source_backed_rule_count": source_backed_rule_count,
        "source_backed_keep_rule_count": source_backed_keep_rule_count,
        "policy_backed_rule_count": policy_backed_rule_count,
        "policy_backed_keep_rule_count": policy_backed_keep_rule_count,
        "policy_lanes": policy_lanes,
        "policy_reasons": policy_reasons,
        "policy_result": policy_result,
        "default_only": runtime_rule_count == 0,
        "suppressed_rule_count": len(suppressed_rules),
        "suppressed_reasons": suppressed_reasons,
        "merged_duplicate_rule_count": merged_duplicate_rule_count,
    }
    if has_concrete_keeps:
        wildcard_reason = (
            "discard_unlisted_cards_after_source_backed_keeps"
            if has_source_backed_keeps
            else "discard_unlisted_cards_after_policy_backed_keeps"
        )
        rules.append(
            {
                "card": "*",
                "selector_kind": "wildcard",
                "selector": "*",
                "action": "discard",
                "condition": "*",
                "reason": wildcard_reason,
            }
        )
    else:
        quality["blocked_reason"] = missing_keep_reason

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
        rule.get("source_type", ""),
    )


def _add_or_merge_mulligan_rule(
    rules: list[dict[str, Any]],
    rules_by_key: dict[tuple[Any, ...], dict[str, Any]],
    rule: dict[str, Any],
) -> bool:
    key = mulligan_rule_key(rule)
    existing = rules_by_key.get(key)
    if existing is None:
        rules_by_key[key] = rule
        rules.append(rule)
        return False

    _merge_unique_list(existing, "source_claim_ids", rule.get("source_claim_ids", []))
    _merge_unique_list(
        existing,
        "merged_claim_ids",
        [
            existing.get("claim_id"),
            *existing.get("merged_claim_ids", []),
            rule.get("claim_id"),
            *rule.get("merged_claim_ids", []),
        ],
    )
    _merge_unique_list(
        existing,
        "merged_reasons",
        [
            existing.get("reason"),
            *existing.get("merged_reasons", []),
            rule.get("reason"),
            *rule.get("merged_reasons", []),
        ],
    )
    return True


def _merge_unique_list(
    target: dict[str, Any],
    key: str,
    values: list[Any],
) -> None:
    merged: list[str] = []
    seen: set[str] = set()
    for value in [*target.get(key, []), *values]:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        merged.append(text)
    if merged:
        target[key] = merged


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


def _source_mulligan_intent_cards_for_policy(
    *,
    claims: list[dict[str, Any]],
    rules: list[dict[str, Any]],
    suppressed_rules: list[dict[str, Any]],
    extra_card_ids: set[str],
) -> set[str]:
    cards = {str(card_id) for card_id in extra_card_ids if str(card_id)}
    for claim in claims:
        if normalized_claim_kind(claim) not in {"mulligan_keep", "mulligan_discard"}:
            continue
        cards.update(_claim_cards(claim))
    for row in [*rules, *suppressed_rules]:
        if row.get("action") not in {"hold", "discard"}:
            continue
        if str(row.get("reason", "")) in SURFACE_REJECTION_REASONS:
            continue
        _add_row_cards(cards, row)
    return {card_id for card_id in cards if card_id and card_id != "*"}


def _add_row_cards(cards: set[str], row: dict[str, Any]) -> None:
    for card_id in row.get("selector_cards", []):
        if str(card_id):
            cards.add(str(card_id))
    card_id = str(row.get("card", ""))
    if card_id and card_id != "*":
        cards.add(card_id)


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


def _with_claim_id(row: dict[str, Any], claim: dict[str, Any]) -> dict[str, Any]:
    claim_id = lifecycle_claim_id(claim)
    if claim_id:
        row["claim_id"] = claim_id
    return row


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

from __future__ import annotations

from typing import Any

from hsconfig.autonomous_mulligan_policy import build_policy_backed_mulligan_rules
from hsconfig.condition_format import lower_runtime_condition
from hsconfig.mulligan_selector import normalize_mulligan_selector
from hsconfig.role_tokens import (
    claim_role_tokens,
    has_start_of_game_non_hand_effect,
    role_tokens,
)
from hsconfig.source_claim_lifecycle import lifecycle_claim_id
from hsconfig.source_claim_gap_report import suppressed_mulligan_claims_from_lifecycle
from hsconfig.source_document_model import can_lower_to_mulligan, normalized_claim_kind


SURFACE_REJECTION_REASONS = {
    "claim_kind_not_mulligan_surface",
    "mulligan_requires_public_guide_source",
    "mulligan_requires_exact_deck_match",
    "mulligan_requires_target_deck_fingerprint",
    "mulligan_requires_verified_exact_deck_evidence",
    "mulligan_exact_deck_fingerprint_mismatch",
    "mulligan_requires_complete_exact_deck_evidence",
    "mulligan_requires_verified_source_receipt",
    "mulligan_requires_promotion_eligible_source",
    "mulligan_requires_full_text_source",
    "mulligan_requires_deck_matched_public_guide_lane",
}

def build_mulligan_plan(
    *,
    deck_name: str,
    claims: list[dict[str, Any]],
    card_roles: dict[str, Any],
    deck_cards: dict[str, Any] | list[dict[str, Any]] | None = None,
    allow_policy_backed: bool = False,
    policy_excluded_card_ids: set[str] | None = None,
    source_claim_lifecycle_rows: list[dict[str, Any]] | None = None,
    deck_identity: dict[str, Any] | None = None,
    verified_source_receipts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    rules: list[dict[str, Any]] = []
    suppressed_rules: list[dict[str, Any]] = []
    rules_by_key: dict[tuple[Any, ...], dict[str, Any]] = {}
    merged_duplicate_rule_count = 0
    claims = _merge_claim_rows(
        claims,
        suppressed_mulligan_claims_from_lifecycle(
            source_claim_lifecycle_rows
        ),
    )

    for claim in claims:
        claim_kind = normalized_claim_kind(claim)
        claim_cards = _claim_cards(claim)
        lifecycle = claim.get("_claim_lifecycle")
        if isinstance(lifecycle, dict) and lifecycle.get("surface_gate_allowed") is False:
            reason = str(lifecycle.get("surface_gate_reason") or "surface_gate_rejected")
            suppressed_rules.extend(
                _suppressed_exact_card_rows(
                    claim=claim,
                    claim_cards=claim_cards,
                    claim_kind=claim_kind,
                    reason=reason,
                )
            )
            continue
        gate = can_lower_to_mulligan(
            claim,
            card_roles=card_roles,
            deck_identity=deck_identity,
            verified_source_receipts=verified_source_receipts,
        )
        if not gate.allowed:
            if claim_cards:
                suppressed_rules.append(
                    _with_claim_id(
                        {
                            "card": claim_cards[0],
                            "action": (
                                "hold"
                                if claim_kind == "mulligan_keep"
                                else "none"
                            ),
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
        policy_veto_card_ids = _policy_veto_card_ids(
            claims=claims,
            rules=rules,
            suppressed_rules=suppressed_rules,
            card_roles=card_roles,
            extra_card_ids=policy_excluded_card_ids or set(),
        )
        policy_result = build_policy_backed_mulligan_rules(
            deck_name=deck_name,
            deck_cards=deck_cards or {},
            card_roles=card_roles,
            excluded_card_reasons=policy_veto_card_ids,
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


def _policy_veto_card_ids(
    *,
    claims: list[dict[str, Any]],
    rules: list[dict[str, Any]],
    suppressed_rules: list[dict[str, Any]],
    card_roles: dict[str, Any],
    extra_card_ids: set[str],
) -> dict[str, str]:
    vetoes = {
        str(card_id): "excluded_source_mulligan_intent"
        for card_id in extra_card_ids
        if str(card_id)
    }
    exact_authority_cards = _exact_source_mulligan_authority_cards(rules)
    for claim in claims:
        if normalized_claim_kind(claim) not in {"mulligan_keep", "mulligan_discard"}:
            continue
        lifecycle = claim.get("_claim_lifecycle")
        for card_id in _claim_cards(claim):
            vetoes.setdefault(card_id, "excluded_source_mulligan_intent")
            if (
                isinstance(lifecycle, dict)
                and lifecycle.get("surface_gate_allowed") is False
            ):
                vetoes[card_id] = "explicit_source_gap_requires_resolution"
    for row in rules:
        if row.get("action") not in {"hold", "discard"}:
            continue
        for card_id in _row_card_ids(row):
            vetoes.setdefault(card_id, "excluded_source_mulligan_intent")
    for row in suppressed_rules:
        if row.get("action") not in {"hold", "discard"}:
            continue
        reason = str(row.get("reason", ""))
        for card_id in _row_card_ids(row):
            vetoes.setdefault(card_id, "excluded_source_mulligan_intent")
            if (
                reason == "claim_not_runtime_lowerable"
                or reason in SURFACE_REJECTION_REASONS
            ):
                vetoes[card_id] = "explicit_source_gap_requires_resolution"
    for card_id, role_row in card_roles.items():
        card_id = str(card_id)
        if not card_id:
            continue
        roles = _card_role_tokens(role_row)
        if "sideboard_owner" in roles:
            vetoes.setdefault(card_id, "sideboard_owner_not_curve_anchor")
        elif (
            card_id not in exact_authority_cards
            and (
                has_start_of_game_non_hand_effect(roles)
                or "start_of_game" in roles
            )
        ):
            vetoes.setdefault(
                card_id,
                "excluded_non_hand_start_of_game_effect",
            )
    return vetoes


def _row_card_ids(row: dict[str, Any]) -> set[str]:
    selector_cards = row.get("selector_cards", [])
    if isinstance(selector_cards, str):
        selector_cards = [selector_cards]
    if not isinstance(selector_cards, list):
        selector_cards = []
    cards = {
        str(card_id)
        for card_id in selector_cards
        if str(card_id)
    }
    card_id = str(row.get("card", ""))
    if card_id and card_id != "*":
        cards.add(card_id)
    return cards


def _exact_source_mulligan_authority_cards(
    rules: list[dict[str, Any]],
) -> set[str]:
    cards: set[str] = set()
    for row in rules:
        if (
            row.get("source_type") != "source_claim"
            or row.get("action") not in {"hold", "discard"}
            or row.get("selector_kind") == "wildcard"
        ):
            continue
        selector_cards = row.get("selector_cards", [])
        if isinstance(selector_cards, list):
            cards.update(str(card_id) for card_id in selector_cards if str(card_id))
        card_id = str(row.get("card", ""))
        if card_id and card_id != "*":
            cards.add(card_id)
    return cards


def _card_role_tokens(row: Any) -> set[str]:
    if not isinstance(row, dict):
        return set()
    values = claim_role_tokens(row)
    values.update(role_tokens(row.get("mechanics")))
    values.update(role_tokens(row.get("tags")))
    return values


def _claim_cards(claim: dict[str, Any]) -> list[str]:
    cards = claim.get("cards", [])
    if isinstance(cards, str):
        cards = [cards]
    return [str(card) for card in cards if str(card)]


def _merge_claim_rows(
    claims: list[dict[str, Any]],
    additional_claims: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged = list(claims)
    seen_claim_ids = {
        lifecycle_claim_id(claim)
        for claim in claims
        if lifecycle_claim_id(claim)
    }
    for claim in additional_claims:
        claim_id = lifecycle_claim_id(claim)
        if claim_id and claim_id in seen_claim_ids:
            continue
        merged.append(claim)
        if claim_id:
            seen_claim_ids.add(claim_id)
    return merged


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
        source_claim_ids = [
            str(item) for item in claim["source_claim_ids"] if str(item)
        ]
        if source_claim_ids:
            return source_claim_ids
    claim_id = lifecycle_claim_id(claim)
    if claim_id:
        return [claim_id]
    return []


def _suppressed_exact_card_rows(
    *,
    claim: dict[str, Any],
    claim_cards: list[str],
    claim_kind: str,
    reason: str,
) -> list[dict[str, Any]]:
    action = {
        "mulligan_keep": "hold",
        "mulligan_discard": "discard",
    }.get(claim_kind, "none")
    rows: list[dict[str, Any]] = []
    for card_id in claim_cards:
        row = _with_claim_id(
            {
                "card": card_id,
                "action": action,
                "reason": reason,
                "source_claim_ids": _source_claim_ids(claim),
            },
            claim,
        )
        rows.append(_with_source_claim_provenance(row, claim))
    return rows


def _with_claim_id(row: dict[str, Any], claim: dict[str, Any]) -> dict[str, Any]:
    claim_id = lifecycle_claim_id(claim)
    if claim_id:
        row["claim_id"] = claim_id
    return row


def _with_source_claim_provenance(
    row: dict[str, Any],
    claim: dict[str, Any],
) -> dict[str, Any]:
    provenance_keys = (
        "source_url",
        "source_title",
        "source_refs",
        "acquisition_provenance",
        "claim_readiness",
        "trust_ceiling",
    )
    copied = False
    for key in provenance_keys:
        if key not in claim:
            continue
        row[key] = claim[key]
        copied = True
    if copied:
        row["source_type"] = "source_claim"
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

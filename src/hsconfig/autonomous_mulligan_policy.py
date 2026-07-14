from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from hsconfig.role_tokens import (
    START_OF_GAME_NON_HAND_EFFECT_ROLES,
    claim_role_tokens,
    has_start_of_game_non_hand_effect,
    role_tokens,
)


PREFERRED_KEEP_ROLES = (
    "mulligan_anchor",
    "early_pressure",
    "one_drop",
    "tempo_draw",
    "pressure",
    "damage",
    "self_damage_pressure",
    "burn_reach",
    "board_flood",
    "token_board",
    "pirate_pressure",
    "mech_curve",
    "weapon_setup",
    "discard_setup",
)
PREFERRED_KEEP_ROLE_RANK = {
    role: rank for rank, role in enumerate(PREFERRED_KEEP_ROLES)
}

EXCLUDED_POLICY_ROLES = frozenset(
    {
        "deckbuilding_modifier",
        "deck_state_modifier",
        "passive_start_effect",
        "late_payoff",
        "combo_finisher",
        "generated_only",
        "tech_slot",
        *(START_OF_GAME_NON_HAND_EFFECT_ROLES - {"hero_power_transform"}),
    }
)


def build_policy_backed_mulligan_rules(
    *,
    deck_name: str,
    deck_cards: Mapping[str, Any] | list[dict[str, Any]],
    card_roles: Mapping[str, Any],
    excluded_card_ids: set[str] | None = None,
    excluded_card_reasons: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    cards = _normalise_deck_cards(deck_cards)
    excluded_reasons = {
        str(card_id): str(reason)
        for card_id, reason in (excluded_card_reasons or {}).items()
    }
    excluded_cards = {
        str(card_id) for card_id in (excluded_card_ids or set())
    } | set(excluded_reasons)
    candidates: list[dict[str, Any]] = []
    suppressed: list[dict[str, Any]] = []

    for card_id, card in sorted(cards.items()):
        if card_id in excluded_cards:
            suppressed.append(
                {
                    "card": card_id,
                    "reason": excluded_reasons.get(
                        card_id,
                        "excluded_source_mulligan_intent",
                    ),
                    "source_type": "policy_backed_autonomous_mulligan",
                }
            )
            continue
        roles = _role_tokens(card_roles.get(card_id, {}))
        exclusion_reason = _exclusion_reason(roles)
        if exclusion_reason:
            suppressed.append(
                {
                    "card": card_id,
                    "reason": exclusion_reason,
                    "source_type": "policy_backed_autonomous_mulligan",
                }
            )
            continue
        role_reason = _preferred_role_reason(roles)
        if role_reason and _safe_cost(card) <= 3:
            candidates.append(
                _candidate(
                    card_id,
                    card,
                    role_reason,
                    role_rank=PREFERRED_KEEP_ROLE_RANK[role_reason],
                )
            )

    if not candidates:
        fallback = _lowest_curve_anchor(cards, suppressed)
        if fallback is not None:
            candidates.append(fallback)

    selected = sorted(candidates, key=_candidate_sort_key)[:3]
    rules = [_rule_from_candidate(candidate) for candidate in selected]
    return {
        "deck_name": deck_name,
        "status": "applied" if rules else "no_safe_candidate",
        "rules": rules,
        "suppressed": suppressed,
        "candidate_count": len(candidates),
        "selected_count": len(rules),
        "excluded_count": len(suppressed),
    }


def _normalise_deck_cards(
    deck_cards: Mapping[str, Any] | list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    if isinstance(deck_cards, Mapping):
        return {
            str(card_id): dict(row) if isinstance(row, Mapping) else {"name": str(card_id)}
            for card_id, row in deck_cards.items()
        }
    cards: dict[str, dict[str, Any]] = {}
    for row in deck_cards:
        if not isinstance(row, Mapping):
            continue
        card_id = str(row.get("card_id", row.get("id", ""))).strip()
        if card_id:
            cards[card_id] = dict(row)
    return cards


def _role_tokens(row: Any) -> set[str]:
    if not isinstance(row, Mapping):
        return set()
    values = claim_role_tokens(row)
    values.update(role_tokens(row.get("mechanics")))
    values.update(role_tokens(row.get("tags")))
    return values


def _exclusion_reason(roles: set[str]) -> str:
    if has_start_of_game_non_hand_effect(roles) or "start_of_game" in roles:
        return "excluded_non_hand_start_of_game_effect"
    if roles & EXCLUDED_POLICY_ROLES:
        return "excluded_policy_role"
    return ""


def _preferred_role_reason(roles: set[str]) -> str:
    for role in PREFERRED_KEEP_ROLES:
        if role in roles:
            return role
    return ""


def _lowest_curve_anchor(
    cards: dict[str, dict[str, Any]],
    suppressed: list[dict[str, Any]],
) -> dict[str, Any] | None:
    suppressed_cards = {row["card"] for row in suppressed}
    candidates = [
        _candidate(card_id, card, "lowest_curve_anchor", role_rank=10)
        for card_id, card in cards.items()
        if card_id not in suppressed_cards and _safe_cost(card) <= 3
    ]
    if not candidates:
        return None
    return sorted(candidates, key=_candidate_sort_key)[0]


def _candidate(
    card_id: str,
    card: Mapping[str, Any],
    reason: str,
    role_rank: int,
) -> dict[str, Any]:
    return {
        "card": card_id,
        "cost": _safe_cost(card),
        "reason": reason,
        "role_rank": role_rank,
    }


def _rule_from_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    card_id = str(candidate["card"])
    return {
        "card": card_id,
        "selector_kind": "card",
        "selector": card_id,
        "action": "hold",
        "condition": "*",
        "reason": f"policy_backed_autonomous_mulligan:{candidate['reason']}",
        "confidence": "policy_backed",
        "source_type": "policy_backed_autonomous_mulligan",
        "source_claim_ids": [],
    }


def _candidate_sort_key(candidate: dict[str, Any]) -> tuple[int, int, str]:
    return (int(candidate["role_rank"]), int(candidate["cost"]), str(candidate["card"]))


def _safe_cost(card: Mapping[str, Any]) -> int:
    try:
        return int(card.get("cost", 99))
    except (TypeError, ValueError):
        return 99

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
ARCHETYPE_LANE_ROLE_HINTS = {
    "aggro": {
        "one_drop",
        "early_pressure",
        "pressure",
        "damage",
        "burn_reach",
        "board_flood",
        "token_board",
        "pirate_pressure",
        "mech_curve",
        "self_damage_pressure",
    },
    "combo": {
        "combo_setup",
        "combo_enabler",
        "tutor",
        "draw",
        "tempo_draw",
        "cycle",
    },
    "big": {
        "ramp",
        "mana_cheat_setup",
        "cheat",
        "summon_from_deck",
        "recruit",
        "defensive_setup",
    },
    "weapon": {
        "weapon_setup",
        "weapon",
        "pirate_pressure",
        "tutor",
        "draw",
    },
    "discard": {
        "discard_setup",
        "discard_outlet",
        "discard_payoff",
        "draw",
    },
    "board": {
        "board_flood",
        "token_board",
        "mech_curve",
        "treant_board",
        "early_pressure",
    },
}

ARCHETYPE_LANE_ROLE_RANKS = {
    "aggro": (
        "one_drop",
        "early_pressure",
        "pirate_pressure",
        "mech_curve",
        "board_flood",
        "token_board",
        "tempo_draw",
        "damage",
        "burn_reach",
    ),
    "combo": (
        "tutor",
        "draw",
        "tempo_draw",
        "cycle",
        "combo_setup",
        "combo_enabler",
    ),
    "big": (
        "ramp",
        "mana_cheat_setup",
        "cheat",
        "summon_from_deck",
        "recruit",
        "defensive_setup",
    ),
    "weapon": (
        "weapon_setup",
        "weapon",
        "pirate_pressure",
        "tutor",
        "draw",
    ),
    "discard": (
        "discard_outlet",
        "discard_setup",
        "discard_payoff",
        "draw",
    ),
    "board": (
        "board_flood",
        "token_board",
        "treant_board",
        "mech_curve",
        "early_pressure",
    ),
    "generic": PREFERRED_KEEP_ROLES,
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
                    "policy_lane": "source_veto",
                    "source_type": "policy_backed_autonomous_mulligan",
                }
            )
            continue
        roles = _role_tokens(card_roles.get(card_id, {}))
        lane = _policy_lane(deck_name, roles)
        exclusion_reason = _exclusion_reason(roles)
        if exclusion_reason:
            suppressed.append(
                {
                    "card": card_id,
                    "reason": exclusion_reason,
                    "policy_lane": lane,
                    "source_type": "policy_backed_autonomous_mulligan",
                }
            )
            continue
        role_reason = _lane_role_reason(lane, roles)
        if role_reason and _safe_cost(card) <= 3:
            candidates.append(
                _candidate(
                    card_id,
                    card,
                    role_reason,
                    role_rank=_lane_role_rank(lane, role_reason),
                    policy_lane=lane,
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


def _policy_lane(deck_name: str, roles: set[str]) -> str:
    lowered_name = deck_name.lower()
    name_lane = _lane_from_deck_name(lowered_name)
    if name_lane != "generic":
        return name_lane
    best_lane = "generic"
    best_score = 0
    for lane, hints in ARCHETYPE_LANE_ROLE_HINTS.items():
        score = len(roles & hints)
        if score > best_score:
            best_lane = lane
            best_score = score
    return best_lane


def _lane_from_deck_name(lowered_name: str) -> str:
    if any(token in lowered_name for token in ("pirate", "shadow", "aggro")):
        return "aggro"
    if any(token in lowered_name for token in ("big", "recruit")):
        return "big"
    if any(token in lowered_name for token in ("kingslayer", "weapon")):
        return "weapon"
    if any(token in lowered_name for token in ("disco", "discard")):
        return "discard"
    if "treant" in lowered_name or (
        "mech" in lowered_name and "mechanic" not in lowered_name
    ):
        return "board"
    if any(token in lowered_name for token in ("combo", "boar")):
        return "combo"
    return "generic"


def _lane_role_reason(lane: str, roles: set[str]) -> str:
    for role in ARCHETYPE_LANE_ROLE_RANKS.get(lane, PREFERRED_KEEP_ROLES):
        if role in roles:
            return role
    return _preferred_role_reason(roles)


def _lane_role_rank(lane: str, reason: str) -> int:
    ranked_roles = ARCHETYPE_LANE_ROLE_RANKS.get(lane, PREFERRED_KEEP_ROLES)
    try:
        return list(ranked_roles).index(reason)
    except ValueError:
        return 99


def _lowest_curve_anchor(
    cards: dict[str, dict[str, Any]],
    suppressed: list[dict[str, Any]],
) -> dict[str, Any] | None:
    suppressed_cards = {row["card"] for row in suppressed}
    candidates = [
        _candidate(
            card_id,
            card,
            "lowest_curve_anchor",
            role_rank=10,
            policy_lane="generic",
        )
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
    policy_lane: str,
) -> dict[str, Any]:
    return {
        "card": card_id,
        "cost": _safe_cost(card),
        "reason": reason,
        "role_rank": role_rank,
        "policy_lane": policy_lane,
    }


def _rule_from_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    card_id = str(candidate["card"])
    policy_lane = str(candidate.get("policy_lane", "generic"))
    reason = str(candidate["reason"])
    return {
        "card": card_id,
        "selector_kind": "card",
        "selector": card_id,
        "action": "hold",
        "condition": "*",
        "reason": f"policy_backed_autonomous_mulligan:{reason}",
        "confidence": "policy_backed",
        "source_type": "policy_backed_autonomous_mulligan",
        "policy_lane": policy_lane,
        "policy_reason": reason,
        "source_claim_ids": [],
    }


def _candidate_sort_key(candidate: dict[str, Any]) -> tuple[int, int, str]:
    return (int(candidate["role_rank"]), int(candidate["cost"]), str(candidate["card"]))


def _safe_cost(card: Mapping[str, Any]) -> int:
    try:
        return int(card.get("cost", 99))
    except (TypeError, ValueError):
        return 99

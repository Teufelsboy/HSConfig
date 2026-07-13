from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


ROLE_HINT_KEYS = ("roles", "semantic_families", "mechanic_families")
OPENING_HAND_MULLIGAN_TEXT_MARKERS = (
    "opening hand",
    "opening-hand",
    "mulligan",
    "starting hand",
)
EXPLICIT_OPENING_HAND_MULLIGAN_ROLES = frozenset(
    {
        "mulligan_anchor",
        "mulligan_keep",
        "opening_hand_keep",
        "opening_hand_mulligan",
    }
)

START_OF_GAME_NON_HAND_EFFECT_ROLES = frozenset(
    {
        "deck_state_modifier",
        "deckbuilding_modifier",
        "deck_size_modifier",
        "even_odd_modifier",
        "highlander_modifier",
        "hero_power_transform",
        "passive_start_effect",
        "start_in_deck_requirement",
        "start_of_game_modifier",
    }
)


def role_tokens(value: Any) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, str):
        token = value.strip().lower()
        return {token} if token else set()
    if isinstance(value, (list, tuple, set, frozenset)):
        return {
            token
            for item in value
            if isinstance(item, str)
            for token in (item.strip().lower(),)
            if token
        }
    return set()


def claim_role_tokens(
    claim: Mapping[str, Any],
    keys: Iterable[str] = ROLE_HINT_KEYS,
) -> set[str]:
    roles: set[str] = set()
    for key in keys:
        roles.update(role_tokens(claim.get(key)))
    return roles


def card_role_tokens(
    card_role: Mapping[str, Any],
    claim: Mapping[str, Any] | None = None,
) -> set[str]:
    roles = claim_role_tokens(card_role, keys=("roles", "semantic_families"))
    if claim is not None:
        roles.update(claim_role_tokens(claim))
    return roles


def has_start_of_game_non_hand_effect(roles: Iterable[str]) -> bool:
    normalized = {
        token
        for role in roles
        for token in role_tokens(role)
    }
    return "start_of_game" in normalized and bool(
        normalized & START_OF_GAME_NON_HAND_EFFECT_ROLES
    )


def has_explicit_opening_hand_mulligan_intent(
    claims: Mapping[str, Any] | Iterable[Mapping[str, Any]] | None,
    *,
    roles: Iterable[str] = (),
) -> bool:
    normalized_roles = {
        token
        for role in roles
        for token in role_tokens(role)
    }
    if normalized_roles & EXPLICIT_OPENING_HAND_MULLIGAN_ROLES:
        return True

    text_parts: list[str] = []
    for claim in _iter_claims(claims):
        if claim_role_tokens(claim) & EXPLICIT_OPENING_HAND_MULLIGAN_ROLES:
            return True
        for key in ("evidence_text_short", "claim", "text", "operator_meaning"):
            value = claim.get(key)
            if value:
                text_parts.append(str(value))
    text = " ".join(text_parts).lower()
    return any(marker in text for marker in OPENING_HAND_MULLIGAN_TEXT_MARKERS)


def _iter_claims(
    claims: Mapping[str, Any] | Iterable[Mapping[str, Any]] | None,
) -> list[Mapping[str, Any]]:
    if claims is None:
        return []
    if isinstance(claims, Mapping):
        return [claims]
    return [claim for claim in claims if isinstance(claim, Mapping)]

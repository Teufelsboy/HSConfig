from __future__ import annotations

from typing import Any, Mapping


QUALIFIER_KEYS = (
    "timing",
    "zone_scope",
    "target_scope",
    "option_surface",
    "state_requirements",
)

ALIASES = {
    "start of game": "start_of_game",
    "opening hand": "mulligan",
    "starting hand": "mulligan",
    "in deck": "deck",
    "deck": "deck",
    "hand": "hand",
    "board": "board",
    "enemy hero": "enemy_hero",
    "enemy face": "enemy_hero",
    "friendly minion": "friendly_minion",
    "enemy minion": "enemy_minion",
    "discover": "discover",
    "choose one": "choose_one",
}


def normalize_semantic_qualifiers(
    claim: Mapping[str, Any],
    *,
    card_roles: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    raw = claim.get("semantic_qualifiers", {})
    if isinstance(raw, Mapping):
        for key in QUALIFIER_KEYS:
            _add_value(result, key, raw.get(key))
    for key in QUALIFIER_KEYS:
        _add_value(result, key, claim.get(key))

    roles = _role_tokens(claim, card_roles or {})
    if "start_of_game" in roles:
        result.setdefault("timing", "start_of_game")
    if "hero_power_transform" in roles:
        result.setdefault("state_requirements", [])
        if "hero_power_transform" not in result["state_requirements"]:
            result["state_requirements"].append("hero_power_transform")
    return result


def has_qualifier(claim: Mapping[str, Any], key: str, value: str) -> bool:
    qualifiers = claim.get("semantic_qualifiers", {})
    if not isinstance(qualifiers, Mapping):
        return False
    current = qualifiers.get(key)
    if isinstance(current, list):
        return value in current
    return current == value


def _add_value(result: dict[str, Any], key: str, value: Any) -> None:
    if value is None:
        return
    if isinstance(value, str):
        normalized = _normalize_text(value)
        if normalized:
            result[key] = [normalized] if key == "state_requirements" else normalized
        return
    if isinstance(value, list):
        values = [_normalize_text(item) for item in value]
        values = [item for item in values if item]
        if values:
            result[key] = list(dict.fromkeys(values))


def _normalize_text(value: Any) -> str:
    text = " ".join(str(value).strip().lower().replace("-", " ").split())
    return ALIASES.get(text, text.replace(" ", "_"))


def _role_tokens(claim: Mapping[str, Any], card_roles: Mapping[str, Any]) -> set[str]:
    roles: set[str] = set()
    for key in ("mechanic", "mechanic_family"):
        value = claim.get(key)
        if isinstance(value, str) and value.strip():
            roles.add(_normalize_text(value))
    for key in ("roles", "semantic_families", "mechanic_families"):
        value = claim.get(key, [])
        if isinstance(value, str):
            value = [value]
        if isinstance(value, list):
            roles.update(_normalize_text(item) for item in value if str(item).strip())
    cards = claim.get("cards", [])
    if not isinstance(cards, list):
        return roles
    for card_id in cards:
        row = card_roles.get(str(card_id), {})
        if not isinstance(row, Mapping):
            continue
        for key in ("roles", "semantic_families", "mechanic_families"):
            value = row.get(key, [])
            if isinstance(value, str):
                value = [value]
            if isinstance(value, list):
                roles.update(_normalize_text(item) for item in value if str(item).strip())
    return roles

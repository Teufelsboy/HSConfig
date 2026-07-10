from __future__ import annotations

import re
from typing import Any, Iterable

from hsconfig.mechanic_support import normalize_role_token, support_for_roles


KNOWN_CARD_TYPES = {
    "enchantment",
    "hero",
    "hero_power",
    "location",
    "minion",
    "spell",
    "weapon",
}

TEXT_MECHANIC_PATTERNS: dict[str, tuple[str, ...]] = {
    "choose_one": ("choose one",),
    "discover": ("discover",),
    "dredge": ("dredge",),
    "tradeable": ("tradeable",),
    "start_of_game": ("start of game",),
    "forge": ("forge",),
    "finale": ("finale",),
    "manathirst": ("manathirst",),
    "infuse": ("infuse", "infused"),
    "corrupt": ("corrupt", "corrupted"),
    "outcast": ("outcast",),
    "excavate": ("excavate",),
    "plague": ("plague",),
    "dormant": ("dormant",),
    "invoke": ("invoke",),
    "questline": ("questline",),
    "titan": ("titan",),
    "colossal": ("colossal",),
    "highlander": ("if your deck has no duplicates", "no duplicates"),
    "jade": ("jade golem",),
    "cthun_package": ("c'thun", "cthun"),
    "spell_school": (
        "fire spell",
        "frost spell",
        "fel spell",
        "shadow spell",
        "holy spell",
        "nature spell",
        "arcane spell",
    ),
}


def build_mechanic_drift_report(cards: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = [card for card in cards if isinstance(card, dict)]
    mechanics_by_card: dict[str, list[str]] = {}
    text_only_mechanics: set[str] = set()
    all_mechanics: set[str] = set()
    card_types: set[str] = set()

    for index, card in enumerate(rows):
        card_id = str(card.get("id") or card.get("card_id") or f"row_{index}")
        explicit = _explicit_mechanics(card)
        text_mechanics = _text_mechanics(str(card.get("text", "")))
        mechanic_set = set(explicit) | set(text_mechanics)
        text_only_mechanics.update(
            mechanic for mechanic in text_mechanics if mechanic not in explicit
        )
        all_mechanics.update(mechanic_set)
        mechanics_by_card[card_id] = sorted(mechanic_set)
        card_type = str(card.get("type", "")).strip().lower()
        if card_type:
            card_types.add(card_type)

    support_rows = support_for_roles(sorted(all_mechanics))
    support_by_mechanic = {str(row["mechanic"]): row for row in support_rows}
    unknown_mechanics = sorted(
        mechanic
        for mechanic, support in support_by_mechanic.items()
        if support.get("registered") is False
    )
    unknown_card_types = sorted(
        card_type for card_type in card_types if card_type not in KNOWN_CARD_TYPES
    )

    return {
        "schema_version": 1,
        "non_blocking": True,
        "total_cards": len(rows),
        "card_types": sorted(card_types),
        "unknown_card_types": unknown_card_types,
        "mechanics": sorted(all_mechanics),
        "unknown_mechanics": unknown_mechanics,
        "text_only_mechanics": sorted(text_only_mechanics),
        "mechanics_by_card": mechanics_by_card,
        "support_by_mechanic": support_by_mechanic,
        "summary": {
            "mechanic_count": len(all_mechanics),
            "unknown_mechanic_count": len(unknown_mechanics),
            "text_only_mechanic_count": len(text_only_mechanics),
            "unknown_card_type_count": len(unknown_card_types),
        },
    }


def _explicit_mechanics(card: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ("mechanics", "referencedTags", "referenced_tags"):
        raw = card.get(key, [])
        if isinstance(raw, list):
            values.extend(_canonical_token(item) for item in raw if str(item).strip())
    return sorted(set(values))


def _text_mechanics(text: str) -> list[str]:
    normalized = " ".join(re.sub(r"<[^>]+>", " ", text).lower().split())
    found = set()
    for mechanic, patterns in TEXT_MECHANIC_PATTERNS.items():
        if any(pattern in normalized for pattern in patterns):
            found.add(mechanic)
    return sorted(found)


def _normalize_token(value: Any) -> str:
    return normalize_role_token(value)


def _canonical_token(value: Any) -> str:
    token = _normalize_token(value)
    rows = support_for_roles([token])
    if not rows:
        return token
    return str(rows[0].get("mechanic", token))

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any


REPORT_ONLY_CONDITION_KEYS = {"phase", "posture"}
STRUCTURED_RUNTIME_CONDITION_KEYS = {
    "coin",
    "nocoin",
    "opponent_class",
    "opponent_classes",
    "hand_contains",
    "hand_contains_any",
    "combo_partner",
}
CARD_ID_PATTERN = r"[A-Za-z0-9_]+"
CLASS_PATTERN = r"[a-z]+"
CLASS_LIST_PATTERN = rf"{CLASS_PATTERN}(?:\s*\|\s*{CLASS_PATTERN})*"
CLASS_RE = re.compile(rf"^{CLASS_PATTERN}$")
ALLOWED_ATOM_PATTERNS = [
    re.compile(r"^\*$"),
    re.compile(r"^coin$"),
    re.compile(r"^nocoin$"),
    re.compile(r"^my_hand\(count\(\)\)\s*==\s*\d+$"),
    re.compile(rf"^my_hand\(count\(\),cardid={CARD_ID_PATTERN}\)\s*>\s*0$"),
    re.compile(rf"^opp_hero\(count\(\),{CLASS_PATTERN}=true\)\s*>\s*0$"),
    re.compile(
        rf"^opp_hero\(count\(\),\s*hero_class\s*=\s*{CLASS_LIST_PATTERN}\s*\)\s*>\s*0$"
    ),
    re.compile(r"^my_target\(count\(\),hero=true\)\s*>\s*0$"),
    re.compile(rf"^my_minion\(count\(\),cardid={CARD_ID_PATTERN}\)\s*>\s*0$"),
    re.compile(rf"^my_discover\(count\(\),cardid={CARD_ID_PATTERN}\)\s*>\s*0$"),
]


@dataclass(frozen=True)
class LoweredCondition:
    value: str
    status: str
    reason: str | None = None


def classify_runtime_condition(value: Any) -> LoweredCondition:
    lowered, reason = _lower(value)
    if reason is not None:
        return LoweredCondition(lowered, "unsupported", reason)
    if _is_runtime_safe(lowered):
        return LoweredCondition(lowered, "runtime_safe", None)
    return LoweredCondition("*", "unsupported", "unsupported_condition")


def lower_runtime_condition(value: Any) -> tuple[str, str | None]:
    classified = classify_runtime_condition(value)
    if classified.status == "runtime_safe":
        return classified.value, None
    return classified.value, classified.reason


def _lower(value: Any) -> tuple[str, str | None]:
    if value in (None, "", {}):
        return "*", None
    if isinstance(value, str):
        cleaned = " ".join(value.strip().split())
        return cleaned or "*", None
    if isinstance(value, dict):
        if "runtime_condition" in value:
            return _lower(value["runtime_condition"])
        keys = {str(key) for key in value}
        if keys <= REPORT_ONLY_CONDITION_KEYS:
            return "*", None
        if not keys <= (REPORT_ONLY_CONDITION_KEYS | STRUCTURED_RUNTIME_CONDITION_KEYS):
            return "*", "unsupported_condition"
        if "hand_contains_any" in keys and len(keys & STRUCTURED_RUNTIME_CONDITION_KEYS) > 1:
            return "*", "unsupported_condition"
        atoms, reason = _atoms_from_structured_condition(value)
        if reason is not None:
            return "*", reason
        if atoms:
            joiner = " OR " if "hand_contains_any" in value else " AND "
            return joiner.join(atoms), None
        return "*", "unsupported_condition"
    return "*", "unsupported_condition"


def _atoms_from_structured_condition(
    value: dict[str, Any],
) -> tuple[list[str], str | None]:
    atoms: list[str] = []
    if value.get("coin") is True:
        atoms.append("coin")
    if value.get("nocoin") is True:
        atoms.append("nocoin")
    if value.get("opponent_class"):
        atoms.append(f"opp_hero(count(),{str(value['opponent_class']).lower()}=true) > 0")
    if "opponent_classes" in value:
        clean_classes = _normalize_opponent_classes(value["opponent_classes"])
        if clean_classes is None:
            return [], "unsupported_condition"
        atoms.append(
            "opp_hero(count(), hero_class="
            + " | ".join(clean_classes)
            + " ) > 0"
        )
    if value.get("hand_contains"):
        atoms.append(f"my_hand(count(),cardid={value['hand_contains']}) > 0")
    if value.get("combo_partner"):
        atoms.append(f"my_hand(count(),cardid={value['combo_partner']}) > 0")
    if value.get("hand_contains_any"):
        raw_cards = value["hand_contains_any"]
        cards = [raw_cards] if isinstance(raw_cards, str) else list(raw_cards)
        atoms.extend(f"my_hand(count(),cardid={card}) > 0" for card in cards)
    return [atom for atom in atoms if _is_atom_safe(atom)], None


def _normalize_opponent_classes(value: Any) -> list[str] | None:
    if isinstance(value, str):
        classes = [value]
    elif isinstance(value, (list, tuple)):
        classes = list(value)
    else:
        return None
    if not classes:
        return None
    clean_classes: list[str] = []
    for hero_class in classes:
        if not isinstance(hero_class, str):
            return None
        clean_class = hero_class.lower()
        if not CLASS_RE.match(clean_class):
            return None
        clean_classes.append(clean_class)
    return clean_classes


def _is_runtime_safe(condition: str) -> bool:
    condition = " ".join(condition.strip().split())
    if any(joiner in condition for joiner in (" AND ", " OR ")):
        atoms = re.split(r"\s+(?:AND|OR)\s+", condition)
        return bool(atoms) and all(_is_atom_safe(atom) for atom in atoms)
    if "|" in condition:
        return _is_atom_safe(condition)
    return _is_atom_safe(condition)


def _is_atom_safe(condition: str) -> bool:
    return any(pattern.match(condition) for pattern in ALLOWED_ATOM_PATTERNS)

from __future__ import annotations

import re
from typing import Any


SUPPORTED_SELECTOR_KINDS = frozenset(
    {"card", "card_list", "drop_n", "plus_combo", "wildcard"}
)
DROP_RE = re.compile(r"^DROP\d+$")
CARD_RE = re.compile(r"^[A-Za-z0-9_]+$")


def normalize_mulligan_selector(rule: dict[str, Any]) -> dict[str, Any]:
    selector = str(rule.get("selector", rule.get("card", ""))).strip()
    explicit_kind = str(rule.get("selector_kind", "")).strip()
    inferred_kind = _infer_selector_kind(selector)
    if inferred_kind is None:
        return {
            "supported": False,
            "reason": "unsupported_mulligan_selector",
            "selector": selector,
        }
    if explicit_kind:
        if explicit_kind not in SUPPORTED_SELECTOR_KINDS or explicit_kind != inferred_kind:
            return {
                "supported": False,
                "reason": "unsupported_mulligan_selector",
                "selector": selector,
                "selector_kind": explicit_kind,
            }
        selector_kind = explicit_kind
    else:
        selector_kind = inferred_kind
    return {
        "supported": True,
        "selector_kind": selector_kind,
        "selector": selector,
        "selector_cards": _selector_cards(selector, selector_kind),
    }


def _infer_selector_kind(selector: str) -> str | None:
    if selector == "*":
        return "wildcard"
    if DROP_RE.fullmatch(selector):
        return "drop_n"
    if "+" in selector:
        return "plus_combo" if _all_card_segments(selector, "+") else None
    if "," in selector:
        return "card_list" if _all_card_segments(selector, ",") else None
    if CARD_RE.fullmatch(selector):
        return "card"
    return None


def _selector_cards(selector: str, selector_kind: str) -> list[str]:
    if selector_kind == "card":
        return [selector]
    if selector_kind == "card_list":
        return _card_segments(selector, ",")
    if selector_kind == "plus_combo":
        return _card_segments(selector, "+")
    return []


def _all_card_segments(selector: str, separator: str) -> bool:
    parts = [part.strip() for part in selector.split(separator)]
    return len(parts) >= 2 and all(CARD_RE.fullmatch(part) for part in parts)


def _card_segments(selector: str, separator: str) -> list[str]:
    return [part.strip() for part in selector.split(separator) if part.strip()]

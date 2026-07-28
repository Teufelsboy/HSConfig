from __future__ import annotations

import re
from typing import Any, Mapping


MULLIGAN_CONTEXT_PATTERNS = (
    re.compile(r"\bmulligan(?:ing)?\b"),
    re.compile(r"\bopening[ -]hand(?![\w-])"),
)
BOILERPLATE_MARKERS = (
    "follow us on twitter",
    "follow us on bluesky",
    "join us on discord",
    "help sign in",
    "home cards",
    "like us on facebook",
)
EXPLICIT_COMBO_MARKERS = ("combo sequence", "combo:", "sequence:")
ORDERED_CONNECTORS = (" then ", " into ", " followed by ", " + ", " -> ")


def normalized(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def claim_text(claim: Mapping[str, Any]) -> str:
    return " ".join(
        str(claim[key])
        for key in ("evidence_text_short", "claim", "text", "operator_meaning")
        if claim.get(key)
    )


def has_explicit_mulligan_context(text: str) -> bool:
    lowered = normalized(text)
    return any(pattern.search(lowered) for pattern in MULLIGAN_CONTEXT_PATTERNS)


def is_content_evidence(text: str) -> bool:
    lowered = " ".join(text.lower().split())
    return bool(lowered) and not any(marker in lowered for marker in BOILERPLATE_MARKERS)


def is_explicit_combo_sentence(sentence: str, card_names: list[str]) -> bool:
    lowered = " ".join(sentence.lower().split())
    if len(lowered) > 500 or not is_content_evidence(lowered):
        return False
    positions = sorted(
        lowered.find(name.lower())
        for name in card_names
        if name and lowered.find(name.lower()) >= 0
    )
    if len(positions) < 2:
        return False
    if any(marker in lowered for marker in EXPLICIT_COMBO_MARKERS):
        return True
    return any(connector in lowered for connector in ORDERED_CONNECTORS)

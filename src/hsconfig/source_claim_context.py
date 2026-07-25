from __future__ import annotations

import re


MULLIGAN_CONTEXT_MARKERS = ("mulligan", "opening hand", "opening-hand")
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


def has_explicit_mulligan_context(text: str) -> bool:
    lowered = " ".join(text.lower().split())
    return any(marker in lowered for marker in MULLIGAN_CONTEXT_MARKERS)


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

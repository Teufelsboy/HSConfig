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
ORDERED_CONNECTORS = (" then ", " into ", " followed by ", " -> ")


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
    spans = _ordered_mention_spans(
        lowered,
        [[name] for name in card_names],
    )
    if spans is None:
        return False
    return _has_connectors_between_mentions(lowered, spans)


def claim_has_directed_combo_evidence(
    claim: Mapping[str, Any],
    deck_identity: Mapping[str, Any] | None,
) -> bool:
    sequence = claim.get("sequence", claim.get("cards", []))
    if isinstance(sequence, str):
        sequence = [sequence]
    ordered_card_ids = [str(card_id) for card_id in sequence if str(card_id)]
    if len(ordered_card_ids) < 2:
        return False

    cards = (
        deck_identity.get("cards", [])
        if isinstance(deck_identity, Mapping)
        else []
    )
    names_by_card_id = {
        str(card.get("card_id", "")): str(card.get("name", ""))
        for card in cards
        if isinstance(card, Mapping) and card.get("card_id")
    }
    mention_groups = [
        [
            alias
            for alias in (names_by_card_id.get(card_id, ""), card_id)
            if alias
        ]
        for card_id in ordered_card_ids
    ]
    lowered = normalized(claim_text(claim))
    if len(lowered) > 500 or not is_content_evidence(lowered):
        return False
    spans = _ordered_mention_spans(lowered, mention_groups)
    if spans is None:
        return False
    return _has_connectors_between_mentions(lowered, spans)


def _ordered_mention_spans(
    lowered: str,
    mention_groups: list[list[str]],
) -> list[tuple[int, int]] | None:
    spans: list[tuple[int, int]] = []
    for aliases in mention_groups:
        candidates = [
            (start, start + len(alias_lowered))
            for alias in aliases
            if (alias_lowered := normalized(alias))
            and (start := lowered.find(alias_lowered)) >= 0
        ]
        if not candidates:
            return None
        span = min(candidates)
        if spans and span[0] < spans[-1][1]:
            return None
        spans.append(span)
    return spans if len(spans) >= 2 else None


def _has_connectors_between_mentions(
    lowered: str,
    spans: list[tuple[int, int]],
) -> bool:
    for left, right in zip(spans, spans[1:]):
        between = f" {lowered[left[1]:right[0]].strip()} "
        if not any(connector in between for connector in ORDERED_CONNECTORS):
            return False
    return True

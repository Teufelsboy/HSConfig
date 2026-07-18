from __future__ import annotations

import re
from datetime import date
from typing import Any, Mapping


STRONG_SOURCE_LANES = {"deck_matched_public_guide"}
STRONG_RANK_LANES = {"guide_current_deck_match", "guide_evergreen_wild_archetype"}


def extract_text_claims(
    *,
    deck_name: str,
    deck_identity: Mapping[str, Any],
    source_record: Mapping[str, Any],
    current_date: str | date | None = None,
) -> list[dict[str, Any]]:
    del deck_name, current_date
    if not _is_full_text_guide(source_record):
        return []

    text = _text(source_record.get("normalized_text") or source_record.get("text")).lower()
    if not text:
        return []

    cards = [card for card in deck_identity.get("cards", []) if isinstance(card, Mapping)]
    cards_by_name = {
        _text(card.get("name")).lower(): card
        for card in cards
        if _text(card.get("name"))
    }
    claims: list[dict[str, Any]] = []
    claims.extend(
        _extract_listed_keep_claims(
            cards_by_name=cards_by_name,
            text=text,
            source_record=source_record,
        )
    )
    claims.extend(_cost_based_discard_claims(cards, text, source_record))
    claims.extend(_hero_power_transform_claims(cards, text, source_record))
    claims.extend(_extract_gameplan_posture_claims(text=text, source_record=source_record))
    return _dedupe_claims(claims)


def _is_full_text_guide(source_record: Mapping[str, Any]) -> bool:
    strength = _text(source_record.get("source_record_strength")).lower()
    family = _text(source_record.get("source_family")).lower()
    visibility = _text(source_record.get("source_visibility")).lower()
    lane = _text(source_record.get("source_lane")).lower()
    rank_lane = _text(source_record.get("source_rank_lane")).lower()
    return (
        strength == "candidate_strong"
        and family in {
            "guide",
            "public_guide",
            "community_guide",
            "mulligan_guide",
            "matchup_guide",
            "guide_fixture",
        }
        and visibility == "full_text"
        and lane in STRONG_SOURCE_LANES
        and rank_lane in STRONG_RANK_LANES
    )


def _extract_listed_keep_claims(
    *,
    cards_by_name: Mapping[str, Mapping[str, Any]],
    text: str,
    source_record: Mapping[str, Any],
) -> list[dict[str, Any]]:
    claims: list[dict[str, Any]] = []
    for segment in _positive_keep_segments(text):
        segment_l = segment.lower()
        for name_l, card in cards_by_name.items():
            if name_l not in segment_l:
                continue
            card_id = _text(card.get("card_id"))
            name = _text(card.get("name"))
            if not card_id or not name or _is_non_opening_hand_effect_card(card):
                continue
            claims.append(
                _claim(
                    source_record,
                    "mulligan_keep",
                    card_id,
                    f"Guide explicitly keeps {name}.",
                )
            )
    return claims


def _extract_gameplan_posture_claims(
    *,
    text: str,
    source_record: Mapping[str, Any],
) -> list[dict[str, Any]]:
    if not _has_aggressive_shadow_burn_posture(text):
        return []
    return [
        _deck_claim(
            source_record,
            "gameplan_posture",
            "ShadowPriest guide describes an aggressive burn Shadow hero power plan.",
            value="aggressive_burn_shadow_hero_power",
            surface="GlobalValues",
            stance="aggro_burn",
        )
    ]


def _cost_based_discard_claims(
    cards: list[Mapping[str, Any]],
    text: str,
    source_record: Mapping[str, Any],
) -> list[dict[str, Any]]:
    if not _has_cost_discard_policy(text, 4):
        return []
    claims: list[dict[str, Any]] = []
    for card in cards:
        cost = _int_or_none(card.get("cost"))
        card_id = _text(card.get("card_id"))
        if card_id and cost is not None and cost >= 4:
            claims.append(
                _claim(source_record, "mulligan_discard", card_id, "Guide discards 4-cost or higher cards.")
            )
    return claims


def _hero_power_transform_claims(
    cards: list[Mapping[str, Any]],
    text: str,
    source_record: Mapping[str, Any],
) -> list[dict[str, Any]]:
    claims: list[dict[str, Any]] = []
    for card in cards:
        card_id = _text(card.get("card_id"))
        name = _text(card.get("name"))
        if not card_id or not name:
            continue
        if _has_explicit_hero_power_association(name, text):
            claims.append(
                _claim(source_record, "hero_power_transform", card_id, f"{name} transforms the hero power.")
            )
    return claims


def _has_explicit_hero_power_association(card_name: str, text: str) -> bool:
    card = re.escape(card_name.lower())
    action = r"(?:change|changes|turn|turns|transform|transforms|upgrade|upgrades|replace|replaces)"
    enable = r"(?:enable|enables|unlock|unlocks)"
    modifier = r"(?:(?:your|the|their|a|an|this|that|new|current)\s+){0,3}"
    hero_power = rf"{modifier}hero power\b"
    shadow_hero_power = rf"{modifier}shadow\s+hero power\b"
    direct_hero_power = rf"{hero_power}(?!\s+[a-z])"
    hero_power_target = rf"{hero_power}\s+(?:into|to)\s+(?:mind spike|shadowform)\b"
    named_power_target = rf"{modifier}(?:mind spike|shadowform)\b"
    return bool(
        re.search(rf"\b{card}\s+{action}\s+{direct_hero_power}", text)
        or re.search(rf"\b{card}\s+{action}\s+{hero_power_target}", text)
        or re.search(rf"\b{card}\s+{action}\s+{named_power_target}", text)
        or re.search(rf"\b{card}\s+{enable}\s+{shadow_hero_power}", text)
        or re.search(
            rf"\b{card}\s+{enable}\s+{shadow_hero_power}\s+and\s+(?:the\s+)?mind spike\s+plan\b",
            text,
        )
    )


def _claim(source_record: Mapping[str, Any], claim_kind: str, card_id: str, evidence: str) -> dict[str, Any]:
    return {
        "source_url": _text(source_record.get("source_url")),
        "source_title": _text(source_record.get("source_title")),
        "source_family": _text(source_record.get("source_family")),
        "source_visibility": _text(source_record.get("source_visibility")),
        "source_lane": _text(source_record.get("source_lane")),
        "source_rank_lane": _text(source_record.get("source_rank_lane")),
        "source_record_strength": _text(source_record.get("source_record_strength")),
        "source_strength": _text(source_record.get("source_record_strength")),
        "publication_year": source_record.get("publication_year"),
        "claim_kind": claim_kind,
        "cards": [card_id],
        "scope": "card",
        "source_confidence": "high",
        "evidence_text_short": evidence,
    }


def _deck_claim(
    source_record: Mapping[str, Any],
    claim_kind: str,
    evidence: str,
    *,
    value: str,
    surface: str,
    stance: str,
) -> dict[str, Any]:
    return {
        "source_url": _text(source_record.get("source_url")),
        "source_title": _text(source_record.get("source_title")),
        "source_family": _text(source_record.get("source_family")),
        "source_visibility": _text(source_record.get("source_visibility")),
        "source_lane": _text(source_record.get("source_lane")),
        "source_rank_lane": _text(source_record.get("source_rank_lane")),
        "source_record_strength": _text(source_record.get("source_record_strength")),
        "source_strength": _text(source_record.get("source_record_strength")),
        "publication_year": source_record.get("publication_year"),
        "claim_kind": claim_kind,
        "cards": [],
        "scope": "deck",
        "surface": surface,
        "stance": stance,
        "value": value,
        "source_confidence": "high",
        "evidence_text_short": evidence,
    }


def _dedupe_claims(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, tuple[str, ...]]] = set()
    deduped: list[dict[str, Any]] = []
    for claim in claims:
        key = (claim["source_url"], claim["claim_kind"], tuple(claim["cards"]))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(claim)
    return deduped


NEGATIVE_KEEP_MARKERS = (
    "do not keep",
    "don't keep",
    "dont keep",
    "never keep",
    "not keep",
)


def _positive_keep_segments(text: str) -> list[str]:
    segments: list[str] = []
    for sentence in _sentences(text):
        lowered = sentence.lower()
        if "keep" not in lowered:
            continue
        segments.extend(_keep_clause_segments(sentence, polarity="positive"))
    return segments


def _keep_clause_segments(sentence: str, *, polarity: str) -> list[str]:
    lowered = sentence.lower()
    events: list[tuple[int, str]] = []
    negative_spans = _negative_keep_marker_spans(lowered)
    events.extend((start, "negative") for start, _end in negative_spans)
    for match in re.finditer(r"\bkeep\b", lowered):
        if any(start <= match.start() < end for start, end in negative_spans):
            continue
        events.append((match.start(), "positive"))
    events.sort(key=lambda row: row[0])
    if not events:
        return []

    polarity_events: list[tuple[int, str]] = []
    for event in events:
        if not polarity_events or polarity_events[-1][1] != event[1]:
            polarity_events.append(event)

    segments: list[str] = []
    for index, (start_index, event_polarity) in enumerate(polarity_events):
        if event_polarity != polarity:
            continue
        next_start = (
            polarity_events[index + 1][0]
            if index + 1 < len(polarity_events)
            else len(sentence)
        )
        segment_start = 0 if index == 0 else start_index
        segment = sentence[segment_start:next_start].strip(" -,:;")
        if segment:
            segments.append(segment)
    return segments


def _negative_keep_marker_spans(lowered_sentence: str) -> list[tuple[int, int]]:
    spans = []
    for marker in NEGATIVE_KEEP_MARKERS:
        start = lowered_sentence.find(marker)
        while start != -1:
            spans.append((start, start + len(marker)))
            start = lowered_sentence.find(marker, start + 1)
    return sorted(spans)


def _has_cost_discard_policy(text: str, cost: int) -> bool:
    phrases = (
        f"do not keep any {cost}-cost or higher",
        f"do not keep any {cost} cost or higher",
        f"do not keep {cost}-cost or higher",
        f"do not keep {cost} cost or higher",
        f"don't keep any {cost}-cost or higher",
        f"don't keep any {cost} cost or higher",
        f"don't keep {cost}-cost or higher",
        f"don't keep {cost} cost or higher",
        f"dont keep any {cost}-cost or higher",
        f"dont keep any {cost} cost or higher",
    )
    return any(phrase in text for phrase in phrases)


def _has_aggressive_shadow_burn_posture(text: str) -> bool:
    return (
        ("shadow priest" in text or "shadowpriest" in text)
        and any(marker in text for marker in ("aggressive", "aggro", "pressure"))
        and any(marker in text for marker in ("burn", "face", "close games"))
        and any(marker in text for marker in ("shadow hero power", "mind spike"))
    )


def _sentences(text: str) -> list[str]:
    normalized = text.replace("!", ".").replace("?", ".").replace("\n", ".")
    return [part.strip() for part in normalized.split(".") if part.strip()]


def _is_non_opening_hand_effect_card(card: Mapping[str, Any]) -> bool:
    name = _text(card.get("name")).lower()
    text = _text(card.get("text")).lower()
    roles = {_text(role).lower() for role in _as_list(card.get("roles"))}
    return (
        name == "darkbishop benedictus"
        or "start of game" in text
        or "hero_power_transform" in roles
        or "start_of_game" in roles
    )


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _text(value: Any) -> str:
    return str(value or "").strip()

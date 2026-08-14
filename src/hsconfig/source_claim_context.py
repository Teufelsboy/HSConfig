from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Iterable, Mapping


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
ORDERED_CONNECTORS = ("then", "into", "followed by", "->")
ORDERED_CONNECTOR_GAP_PATTERN = re.compile(
    r"\s*,?\s*(?:then|into|followed\s+by|->)\s*",
)


@dataclass(frozen=True)
class DirectedMentionChain:
    group_indices: tuple[int, ...]
    spans: tuple[tuple[int, int], ...]


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
    return resolve_directed_mention_chain(
        sentence,
        [[name] for name in card_names],
        preserve_group_order=True,
    ) is not None


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
    return resolve_directed_mention_chain(
        lowered,
        mention_groups,
        preserve_group_order=True,
    ) is not None


def bounded_mention_spans(
    text: str,
    aliases: Iterable[str],
) -> list[tuple[int, int]]:
    lowered = normalized(text)
    spans: set[tuple[int, int]] = set()
    for alias in aliases:
        alias_lowered = normalized(alias)
        if not alias_lowered:
            continue
        pattern = re.compile(
            rf"(?<![\w-]){re.escape(alias_lowered)}(?![\w-])",
        )
        spans.update(match.span() for match in pattern.finditer(lowered))
    return sorted(spans)


def resolve_directed_mention_chain(
    text: str,
    mention_groups: list[list[str]],
    *,
    preserve_group_order: bool,
) -> DirectedMentionChain | None:
    lowered = normalized(text)
    if len(lowered) > 500 or not is_content_evidence(lowered):
        return None
    candidates_by_group = [
        bounded_mention_spans(lowered, aliases)
        for aliases in mention_groups
    ]
    if preserve_group_order:
        group_indices = tuple(range(len(candidates_by_group)))
        if len(group_indices) < 2 or any(
            not candidates_by_group[index] for index in group_indices
        ):
            return None
        spans = _search_ordered_span_chain(
            lowered,
            candidates_by_group,
            group_indices,
        )
        if spans is None:
            return None
        return DirectedMentionChain(group_indices, spans)

    mentioned_group_indices = tuple(
        index
        for index, candidates in enumerate(candidates_by_group)
        if candidates
    )
    if len(mentioned_group_indices) < 2:
        return None
    return _search_unordered_group_chain(
        lowered,
        candidates_by_group,
        mentioned_group_indices,
    )


def _search_ordered_span_chain(
    lowered: str,
    candidates_by_group: list[list[tuple[int, int]]],
    group_indices: tuple[int, ...],
    *,
    position: int = 0,
    spans: tuple[tuple[int, int], ...] = (),
) -> tuple[tuple[int, int], ...] | None:
    if position == len(group_indices):
        return spans
    group_index = group_indices[position]
    for span in candidates_by_group[group_index]:
        if spans and not _spans_have_directed_gap(lowered, spans[-1], span):
            continue
        resolved = _search_ordered_span_chain(
            lowered,
            candidates_by_group,
            group_indices,
            position=position + 1,
            spans=(*spans, span),
        )
        if resolved is not None:
            return resolved
    return None


def _search_unordered_group_chain(
    lowered: str,
    candidates_by_group: list[list[tuple[int, int]]],
    mentioned_group_indices: tuple[int, ...],
) -> DirectedMentionChain | None:
    occurrences = sorted(
        (
            span[0],
            span[1],
            group_index,
        )
        for group_index in mentioned_group_indices
        for span in candidates_by_group[group_index]
    )
    required_groups = frozenset(mentioned_group_indices)
    for start, end, group_index in occurrences:
        resolved = _extend_unordered_group_chain(
            lowered,
            occurrences,
            remaining_groups=required_groups - {group_index},
            group_indices=(group_index,),
            spans=((start, end),),
        )
        if resolved is not None:
            return resolved
    return None


def _extend_unordered_group_chain(
    lowered: str,
    occurrences: list[tuple[int, int, int]],
    *,
    remaining_groups: frozenset[int],
    group_indices: tuple[int, ...],
    spans: tuple[tuple[int, int], ...],
) -> DirectedMentionChain | None:
    if not remaining_groups:
        return DirectedMentionChain(group_indices, spans)
    previous = spans[-1]
    for start, end, group_index in occurrences:
        if group_index not in remaining_groups:
            continue
        span = (start, end)
        if not _spans_have_directed_gap(lowered, previous, span):
            continue
        resolved = _extend_unordered_group_chain(
            lowered,
            occurrences,
            remaining_groups=remaining_groups - {group_index},
            group_indices=(*group_indices, group_index),
            spans=(*spans, span),
        )
        if resolved is not None:
            return resolved
    return None


def _spans_have_directed_gap(
    lowered: str,
    left: tuple[int, int],
    right: tuple[int, int],
) -> bool:
    if right[0] < left[1]:
        return False
    between = lowered[left[1]:right[0]]
    return ORDERED_CONNECTOR_GAP_PATTERN.fullmatch(between) is not None

from __future__ import annotations

from typing import Any

from hsconfig.source_semantic_qualifiers import QUALIFIER_KEYS


def draft_source_documents(
    *,
    deck_name: str,
    deck_identity: dict[str, Any],
    evidence_rows: list[dict[str, Any]],
    current_date: Any = None,
) -> dict[str, Any]:
    del current_date
    name_map = _card_name_map(deck_identity)
    grouped: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    unresolved_mentions: list[dict[str, Any]] = []
    resolved_claims = 0
    dropped_claims = 0

    for index, row in enumerate(evidence_rows, start=1):
        key = (
            str(row.get("source_url", "")),
            str(row.get("source_title", "")),
            str(row.get("source_family", "guide")),
            str(row.get("retrieved_at", "")),
        )
        document = grouped.setdefault(
            key,
            {
                "source_url": key[0],
                "source_title": key[1],
                "source_family": key[2],
                "retrieved_at": key[3],
                "deck_name": str(row.get("deck_name", "")),
                "archetype": str(row.get("archetype", "")),
                "source_lane": str(row.get("source_lane", "unknown")),
                "deck_match_scope": str(row.get("deck_match_scope", "unknown")),
                "source_visibility": str(row.get("source_visibility", "unknown")),
                "claims": [],
            },
        )
        cards, unresolved = _resolve_mentions(row, name_map)
        unresolved_mentions.extend(
            {
                "row_index": index,
                "mention": mention,
                "source_url": key[0],
                "claim_kind": str(row.get("claim_kind", "")),
            }
            for mention in unresolved
        )
        if unresolved:
            dropped_claims += 1
            continue
        if not cards and str(row.get("scope", "card")) not in {"deck", "archetype"}:
            dropped_claims += 1
            continue
        document["claims"].append(_claim_from_row(row, cards))
        resolved_claims += 1

    documents = list(grouped.values())
    return {
        "schema_version": 1,
        "deck_name": deck_name,
        "source_documents": documents,
        "unresolved_mentions": unresolved_mentions,
        "draft_summary": {
            "source_count": len(documents),
            "evidence_rows": len(evidence_rows),
            "resolved_claims": resolved_claims,
            "dropped_claims": dropped_claims,
            "unresolved_mentions": len(unresolved_mentions),
        },
    }


def _card_name_map(deck_identity: dict[str, Any]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for card in deck_identity.get("cards", []):
        if not isinstance(card, dict):
            continue
        card_id = str(card.get("card_id", "")).strip()
        name = str(card.get("name", "")).strip()
        if card_id:
            mapping[card_id.lower()] = card_id
        if name and card_id:
            mapping[name.lower()] = card_id
    return mapping


def _resolve_mentions(
    row: dict[str, Any],
    name_map: dict[str, str],
) -> tuple[list[str], list[str]]:
    candidates = [*_as_list(row.get("cards", [])), *_as_list(row.get("card_mentions", []))]
    cards: list[str] = []
    unresolved: list[str] = []
    for candidate in candidates:
        text = str(candidate).strip()
        if not text:
            continue
        resolved = name_map.get(text.lower())
        if resolved is None:
            unresolved.append(text)
            continue
        if resolved not in cards:
            cards.append(resolved)
    return cards, unresolved


def _claim_from_row(row: dict[str, Any], cards: list[str]) -> dict[str, Any]:
    claim = {
        "claim_kind": str(row.get("claim_kind", "")),
        "cards": cards,
        "scope": str(row.get("scope", "card")),
        "stance": str(row.get("stance", "")),
        "evidence_text_short": str(row.get("evidence_text_short", row.get("reason", ""))),
        "source_confidence": str(row.get("source_confidence", "medium")),
    }
    for key in (
        "claim_confidence",
        "condition",
        "conditions",
        "selector",
        "selector_kind",
        "runtime_block",
        "runtime_value",
        "mechanic",
        "sequence",
        "timing_kind",
        "operator",
        "values",
        "option_card_id",
        "choice_card_id",
        "semantic_qualifiers",
        "source_lane",
        "deck_match_scope",
        "source_visibility",
        *QUALIFIER_KEYS,
    ):
        if key in row:
            claim[key] = row[key]
    return claim


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]

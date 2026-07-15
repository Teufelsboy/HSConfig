from __future__ import annotations

from datetime import date, datetime
from typing import Any, Mapping


GUIDE_FAMILIES = {"guide", "public_guide", "community_guide", "mulligan_guide", "matchup_guide", "guide_fixture"}
DECKLIST_FAMILIES = {"decklist", "decklist_only", "deck_aggregator", "deck_snapshot", "deck_code"}
STATS_FAMILIES = {"stats", "statistical_enrichment", "hsreplay", "hsguru"}
STATIC_FAMILIES = {
    "hearthstonejson_static_semantics",
    "hearthstonejson",
    "official_card_data",
    "static_semantics",
    "metadata",
    "card_text",
}
NON_PROMOTING_SOURCE_TYPES = {
    "policy_backed_autonomous_mulligan",
    "default_runtime",
    "generated_default",
}


def classify_source_evidence(
    record: Mapping[str, Any],
    *,
    deck_name: str,
    current_date: str | date | None,
) -> dict[str, Any]:
    """Classify one source record without deciding package/apply authority."""
    result = dict(record)
    family = _source_family(record)
    source_type = _text(record.get("source_type") or record.get("provenance")).lower()
    visibility = _source_visibility(record, family)
    deck_scope = _deck_match_scope(record, deck_name)
    publication_year = _publication_year(record)
    current_year = _current_year(current_date)
    source_rank_lane = _source_rank_lane(
        family,
        visibility,
        deck_scope,
        publication_year,
        current_year,
    )
    source_lane = _source_lane(source_rank_lane, deck_scope)
    blockers = _promotion_blockers(
        record,
        family=family,
        source_type=source_type,
        visibility=visibility,
        deck_scope=deck_scope,
        publication_year=publication_year,
        current_year=current_year,
        source_rank_lane=source_rank_lane,
    )
    promotion_eligible = not blockers and family in GUIDE_FAMILIES

    result.update(
        {
            "source_visibility": visibility,
            "source_rank_lane": source_rank_lane,
            "source_lane": source_lane,
            "deck_match_scope": deck_scope,
            "publication_year": publication_year,
            "promotion_eligible": promotion_eligible,
            "strong_promotion_eligible": (
                promotion_eligible and source_lane == "deck_matched_public_guide"
            ),
            "trust_ceiling": (
                "source_backed_strong"
                if promotion_eligible
                else _trust_ceiling(family, visibility)
            ),
            "promotion_blockers": blockers,
            "first_missing_source_action": (
                "none" if promotion_eligible else _first_missing_source_action(blockers)
            ),
        }
    )
    return result


def _source_family(record: Mapping[str, Any]) -> str:
    raw = _text(
        record.get("source_family")
        or record.get("source_type_family")
        or record.get("source_type")
    ).lower()
    if raw in {"public_guide", "community_guide"}:
        return raw
    if raw in {"decklist_only", "deck_aggregator"}:
        return raw
    return raw or "unknown"


def _source_visibility(record: Mapping[str, Any], family: str) -> str:
    explicit = _text(record.get("source_visibility")).lower()
    if explicit:
        return explicit
    if family in DECKLIST_FAMILIES:
        return "decklist_only"
    text = _text(record.get("normalized_text") or record.get("text"))
    if family in GUIDE_FAMILIES and len(text) >= 180:
        return "full_text"
    if family in GUIDE_FAMILIES and text:
        return "snippet_only"
    if family in STATIC_FAMILIES:
        return "full_text"
    return "unknown"


def _deck_match_scope(record: Mapping[str, Any], deck_name: str) -> str:
    explicit = _text(record.get("deck_match_scope")).lower()
    if explicit:
        return explicit
    match = record.get("deck_match", {})
    if not isinstance(match, Mapping):
        return "unknown"
    declared = _norm(match.get("deck_name"))
    matched_ids = match.get("matched_card_ids", [])
    has_overlap = isinstance(matched_ids, list) and bool(matched_ids)
    source_text = _norm(f"{record.get('source_title', '')} {record.get('normalized_text', '')}")
    if declared == _norm(deck_name) and (has_overlap or _norm(deck_name) in source_text):
        return "deck_or_archetype_matched"
    return "unknown"


def _source_rank_lane(
    family: str,
    visibility: str,
    deck_scope: str,
    publication_year: int | None,
    current_year: int | None,
) -> str:
    if family in DECKLIST_FAMILIES:
        return "decklist_only"
    if family in STATS_FAMILIES:
        return "statistical_enrichment"
    if family in STATIC_FAMILIES:
        return "static_semantics_only"
    if (
        family in GUIDE_FAMILIES
        and visibility == "full_text"
        and deck_scope in {"deck_matched", "deck_or_archetype_matched"}
        and current_year is not None
        and publication_year == current_year
    ):
        return "guide_current_deck_match"
    if family in GUIDE_FAMILIES and visibility == "full_text":
        return "guide_full_text_not_current"
    if family in GUIDE_FAMILIES:
        return "guide_not_full_text"
    return "source_unclassified"


def _source_lane(source_rank_lane: str, deck_scope: str) -> str:
    if source_rank_lane == "guide_current_deck_match" and deck_scope in {
        "deck_matched",
        "deck_or_archetype_matched",
    }:
        return "deck_matched_public_guide"
    return source_rank_lane or "unknown"


def _promotion_blockers(
    record: Mapping[str, Any],
    *,
    family: str,
    source_type: str,
    visibility: str,
    deck_scope: str,
    publication_year: int | None,
    current_year: int | None,
    source_rank_lane: str,
) -> list[str]:
    blockers: list[str] = []
    if record.get("promotion_eligible") is False:
        blockers.append("promotion_explicitly_disabled")
    if source_type in NON_PROMOTING_SOURCE_TYPES:
        blockers.append(f"non_promoting_source_type_{source_type}")
    if family in DECKLIST_FAMILIES:
        blockers.append("decklist_only_not_strong_evidence")
    if family in STATS_FAMILIES:
        blockers.append("stats_only_not_strong_evidence")
    if family in STATIC_FAMILIES:
        blockers.append("static_semantics_not_public_guide")
    if visibility != "full_text":
        blockers.append(f"source_visibility_{visibility}_not_strong")
    if deck_scope not in {"deck_matched", "deck_or_archetype_matched"}:
        blockers.append("deck_match_scope_not_strong")
    if publication_year is None:
        blockers.append("missing_publication_year")
    elif current_year is not None and publication_year != current_year:
        blockers.append("source_not_current_year")
    strength = _text(record.get("source_record_strength")).lower()
    if strength and strength != "candidate_strong":
        blockers.append(f"non_strong_source_record_strength_{strength}")
    if source_rank_lane != "guide_current_deck_match":
        blockers.append(f"source_rank_lane_{source_rank_lane}_not_strong")
    return sorted(set(blockers))


def _first_missing_source_action(blockers: list[str]) -> str:
    if "missing_publication_year" in blockers or "source_not_current_year" in blockers:
        return "add_current_publication_metadata_or_current_guide"
    if any(blocker.startswith("source_visibility_") for blocker in blockers):
        return "add_full_text_public_guide_source"
    if "deck_match_scope_not_strong" in blockers:
        return "add_deck_or_archetype_matched_source"
    return "add_current_deck_guide_or_mulligan_guide"


def _trust_ceiling(family: str, visibility: str) -> str:
    if family in STATIC_FAMILIES:
        return "static_semantics_only"
    if visibility == "decklist_only":
        return "decklist_informed"
    return "source_informed_partial"


def _publication_year(record: Mapping[str, Any]) -> int | None:
    explicit = record.get("publication_year")
    if isinstance(explicit, int):
        return explicit
    published = _text(
        record.get("published_at")
        or record.get("publication_date")
        or record.get("published_date")
    )
    if len(published) >= 4 and published[:4].isdigit():
        return int(published[:4])
    return None


def _current_year(value: str | date | None) -> int | None:
    if isinstance(value, date):
        return value.year
    text = _text(value)
    if len(text) >= 4 and text[:4].isdigit():
        return int(text[:4])
    return datetime.utcnow().year


def _text(value: Any) -> str:
    return str(value or "").strip()


def _norm(value: Any) -> str:
    return "".join(ch for ch in _text(value).lower() if ch.isalnum())

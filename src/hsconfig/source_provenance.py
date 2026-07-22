from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from typing import Any


GUIDE_FAMILIES = {
    "guide",
    "public_guide",
    "community_guide",
    "mulligan_guide",
    "matchup_guide",
    "guide_fixture",
}
DECKLIST_FAMILIES = {
    "decklist",
    "decklist_only",
    "deck_aggregator",
    "deck_snapshot",
    "deck_code",
}
STATIC_FAMILIES = {
    "official_static_semantics",
    "blizzard_card_library",
    "hearthstonejson_static_semantics",
    "hearthstonejson",
    "official_card_data",
    "static_semantics",
    "metadata",
    "card_text",
}
CURRENT_MARKERS = {
    "current",
    "current_deck",
    "current_full_text",
    "current_or_evergreen",
    "same_year",
}
EVERGREEN_MARKERS = {
    "evergreen",
    "evergreen_wild",
    "evergreen_wild_archetype",
    "guide_evergreen_wild_archetype",
}
EVERGREEN_WILD_MAX_AGE_YEARS = 10
EVERGREEN_WILD_MIN_MATCHED_CARDS = 2


def normalize_source_provenance(
    record: Mapping[str, Any],
    *,
    deck_name: str,
    deck_identity: Mapping[str, Any] | None = None,
    current_date: str | date | None = None,
) -> dict[str, Any]:
    family = _source_family(record)
    visibility = _source_visibility(record, family)
    publication_year = _publication_year(record)
    current_year = _current_year(current_date)
    deck_match = _deck_identity_match(record, deck_name, deck_identity)
    freshness_status, reason = _freshness_status(
        record,
        family=family,
        publication_year=publication_year,
        current_year=current_year,
        visibility=visibility,
        deck_identity=deck_identity,
    )
    return {
        "source_visibility": visibility,
        "deck_identity_match": deck_match["matched"],
        "deck_identity_match_basis": deck_match["basis"],
        "freshness_status": freshness_status,
        "current_or_evergreen": freshness_status in {"current", "evergreen"},
        "current_or_evergreen_reason": reason,
        "source_status_apply_blocking": False,
    }


def research_payload_provenance(payload: Mapping[str, Any]) -> dict[str, Any]:
    if payload.get("canonical_evidence") is True:
        return _provenance_result("current", _reason(payload, "canonical_evidence"))
    top_level_status = _normalized_marker(payload.get("freshness_status"))
    if top_level_status in CURRENT_MARKERS:
        return _provenance_result("current", _reason(payload, "top_level_current"))
    if top_level_status in EVERGREEN_MARKERS:
        return _provenance_result("evergreen", _reason(payload, "top_level_evergreen"))
    source_freshness = _normalized_marker(payload.get("source_freshness"))
    if source_freshness in CURRENT_MARKERS:
        return _provenance_result("current", _reason(payload, "top_level_source_freshness"))
    if source_freshness in EVERGREEN_MARKERS:
        return _provenance_result("evergreen", _reason(payload, "top_level_source_freshness"))
    currency_status = _normalized_marker(payload.get("currency_status"))
    if currency_status in CURRENT_MARKERS:
        return _provenance_result("current", _reason(payload, "top_level_currency_status"))
    if currency_status in EVERGREEN_MARKERS:
        return _provenance_result("evergreen", _reason(payload, "top_level_currency_status"))
    if _truthy(payload.get("current_or_evergreen")):
        return _provenance_result("current", _reason(payload, "top_level_current_or_evergreen"))
    if _truthy(payload.get("evergreen_wild_archetype")):
        return _provenance_result("evergreen", _reason(payload, "top_level_evergreen_wild_archetype"))

    for row in _nested_rows(payload):
        marker = _normalized_marker(row.get("freshness_status"))
        lane = _normalized_marker(row.get("source_freshness_lane") or row.get("source_rank_lane"))
        if marker in CURRENT_MARKERS or lane in CURRENT_MARKERS or lane == "guide_current_deck_match":
            return _provenance_result("current", _reason(row, "nested_current_marker"))
        if marker in EVERGREEN_MARKERS or lane in EVERGREEN_MARKERS:
            return _provenance_result("evergreen", _reason(row, "nested_evergreen_marker"))
        source_freshness = _normalized_marker(row.get("source_freshness"))
        if source_freshness in CURRENT_MARKERS:
            return _provenance_result("current", _reason(row, "nested_source_freshness"))
        if source_freshness in EVERGREEN_MARKERS:
            return _provenance_result("evergreen", _reason(row, "nested_source_freshness"))
        currency_status = _normalized_marker(row.get("currency_status"))
        if currency_status in CURRENT_MARKERS:
            return _provenance_result("current", _reason(row, "nested_currency_status"))
        if currency_status in EVERGREEN_MARKERS:
            return _provenance_result("evergreen", _reason(row, "nested_currency_status"))
        if _truthy(row.get("current_or_evergreen")):
            return _provenance_result("current", _reason(row, "nested_current_or_evergreen"))
        if _truthy(row.get("evergreen_wild_archetype")):
            return _provenance_result("evergreen", _reason(row, "nested_evergreen_wild_archetype"))

    return _provenance_result("unknown", "missing_current_or_evergreen_marker")


def _provenance_result(status: str, reason: str) -> dict[str, Any]:
    return {
        "freshness_status": status,
        "current_or_evergreen": status in {"current", "evergreen"},
        "current_or_evergreen_reason": reason,
        "source_status_apply_blocking": False,
    }


def _nested_rows(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    rows: list[Mapping[str, Any]] = []
    for key in ("guide_sources", "current_deck_sources", "full_text_claim_sources", "records"):
        value = payload.get(key)
        if isinstance(value, list):
            rows.extend(row for row in value if isinstance(row, Mapping))
    return rows


def _source_family(record: Mapping[str, Any]) -> str:
    family = _text(
        record.get("source_family")
        or record.get("source_type_family")
        or record.get("source_type")
    ).lower()
    return family or "unknown"


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


def _deck_identity_match(
    record: Mapping[str, Any],
    deck_name: str,
    deck_identity: Mapping[str, Any] | None,
) -> dict[str, Any]:
    explicit = _text(record.get("deck_match_scope")).lower()
    if explicit in {"deck_matched", "deck_or_archetype_matched"}:
        return {"matched": True, "basis": explicit}
    match = record.get("deck_match", {})
    if not isinstance(match, Mapping):
        return {"matched": False, "basis": "missing_deck_match"}
    declared = _norm(match.get("deck_name"))
    matched_ids = match.get("matched_card_ids", [])
    has_card_overlap = bool(_validated_matched_card_ids(matched_ids, deck_identity))
    if declared == _norm(deck_name) and has_card_overlap:
        return {"matched": True, "basis": "deck_name_and_card_overlap"}
    if declared == _norm(deck_name):
        return {"matched": True, "basis": "deck_name"}
    if has_card_overlap:
        return {"matched": True, "basis": "card_overlap"}
    return {"matched": False, "basis": "no_identity_match"}


def _canonical_card_ids(deck_identity: Mapping[str, Any] | None) -> set[str]:
    if not isinstance(deck_identity, Mapping):
        return set()
    cards = deck_identity.get("cards", [])
    if not isinstance(cards, list):
        return set()
    return {
        _text(card.get("card_id"))
        for card in cards
        if isinstance(card, Mapping) and _text(card.get("card_id"))
    }


def _validated_matched_card_ids(
    matched_ids: Any,
    deck_identity: Mapping[str, Any] | None,
) -> set[str]:
    if not isinstance(matched_ids, list):
        return set()
    normalized = {_text(card_id) for card_id in matched_ids if _text(card_id)}
    canonical_ids = _canonical_card_ids(deck_identity)
    return normalized.intersection(canonical_ids) if canonical_ids else normalized


def _freshness_status(
    record: Mapping[str, Any],
    *,
    family: str,
    publication_year: int | None,
    current_year: int | None,
    visibility: str,
    deck_identity: Mapping[str, Any] | None,
) -> tuple[str, str]:
    explicit = _normalized_marker(record.get("freshness_status"))
    if explicit in CURRENT_MARKERS:
        return "current", _reason(record, "explicit_current")
    if explicit in EVERGREEN_MARKERS:
        return "evergreen", _reason(record, "explicit_evergreen")
    if _truthy(record.get("current_or_evergreen")):
        return "current", _reason(record, "explicit_current_or_evergreen")
    if _truthy(record.get("evergreen_wild_archetype")):
        return "evergreen", _reason(record, "explicit_evergreen_wild_archetype")
    if family in DECKLIST_FAMILIES:
        return "not_strategy_guide", "decklist_not_strategy_guide"
    if family not in GUIDE_FAMILIES:
        return "not_strategy_guide", f"{family}_not_strategy_guide"
    if visibility != "full_text":
        return "unknown", f"source_visibility_{visibility}_not_full_text"
    if publication_year is None or current_year is None:
        return "unknown", "missing_publication_year"
    if publication_year == current_year:
        return "current", "publication_year_matches_current_year"
    if _is_evergreen_wild_source(
        record,
        publication_year=publication_year,
        current_year=current_year,
        deck_identity=deck_identity,
    ):
        return "evergreen", "wild_guide_with_card_overlap"
    return "stale", "publication_year_not_current_or_evergreen"


def _is_evergreen_wild_source(
    record: Mapping[str, Any],
    *,
    publication_year: int,
    current_year: int,
    deck_identity: Mapping[str, Any] | None,
) -> bool:
    age = current_year - publication_year
    if age < 1 or age > EVERGREEN_WILD_MAX_AGE_YEARS:
        return False
    format_scope = _text(record.get("format_scope") or record.get("format")).lower()
    if format_scope not in {"wild", "wild_archetype", "hearthstone_wild"}:
        return False
    match = record.get("deck_match", {})
    if not isinstance(match, Mapping):
        return False
    matched = match.get("matched_card_ids", [])
    return len(_validated_matched_card_ids(matched, deck_identity)) >= EVERGREEN_WILD_MIN_MATCHED_CARDS


def _reason(row: Mapping[str, Any], fallback: str) -> str:
    return _text(row.get("current_or_evergreen_reason")) or fallback


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


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return _text(value).lower() in {"1", "true", "yes", "y"}


def _normalized_marker(value: Any) -> str:
    return _text(value).lower()


def _norm(value: Any) -> str:
    return "".join(ch for ch in _text(value).lower() if ch.isalnum())


def _text(value: Any) -> str:
    return str(value or "").strip()

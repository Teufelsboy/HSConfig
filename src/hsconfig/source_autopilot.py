from __future__ import annotations

from collections import Counter
from datetime import date, datetime
from typing import Any, Mapping, Sequence

from hsconfig.source_document_drafter import draft_source_documents
from hsconfig.source_evidence_verifier import verify_source_documents

GUIDE_FAMILIES = {"guide", "mulligan_guide", "matchup_guide", "guide_fixture"}
DECKLIST_FAMILIES = {"decklist", "deck_snapshot", "deck_code"}
STATIC_FAMILIES = {
    "hearthstonejson_static_semantics",
    "static_semantics",
    "metadata",
    "card_text",
}


def rank_public_sources(
    *,
    deck_name: str,
    deck_identity: Mapping[str, Any],
    source_search_records: Sequence[Mapping[str, Any]],
    current_date: str | date | None = None,
) -> list[dict[str, Any]]:
    ranked: list[dict[str, Any]] = []
    current_year = _current_year(current_date)
    deck_card_ids = _deck_card_ids(deck_identity)
    normalized_deck_name = _norm(deck_name)

    for index, record in enumerate(source_search_records):
        row = dict(record)
        family = _text(row.get("source_family", "")).lower()
        match = row.get("deck_match", {})
        if not isinstance(match, Mapping):
            match = {}
        matched_ids = {
            _text(card_id)
            for card_id in _as_list(match.get("matched_card_ids", []))
            if _text(card_id)
        }
        deck_name_match = _norm(match.get("deck_name", "")) == normalized_deck_name
        card_overlap = len(deck_card_ids & matched_ids)
        score = 0
        if family in GUIDE_FAMILIES:
            score += 60
        if family in DECKLIST_FAMILIES:
            score += 15
        if family in STATIC_FAMILIES:
            score -= 20
        if deck_name_match:
            score += 25
        score += min(card_overlap, 10) * 3
        if _record_year(row) == current_year:
            score += 10
        if not _is_public_https(row.get("source_url", "")):
            score -= 100
        row["source_rank_score"] = score
        row["source_rank_lane"] = _rank_lane(
            family,
            deck_name_match,
            card_overlap,
            current_year,
            row,
        )
        row["source_rank_index"] = index
        ranked.append(row)

    ranked.sort(key=lambda item: (-int(item["source_rank_score"]), int(item["source_rank_index"])))
    return ranked


def extract_source_evidence_rows(
    *,
    deck_name: str,
    deck_identity: Mapping[str, Any],
    ranked_sources: Sequence[Mapping[str, Any]],
    current_date: str | date | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for source in ranked_sources:
        base = _source_base(deck_name, source, current_date)
        for row in _mulligan_rows(deck_identity, source, base):
            _append_unique(rows, seen, row)
        for row in _explicit_claim_rows(source, base):
            _append_unique(rows, seen, row)
    return rows


def build_source_autopilot_bundle(
    *,
    deck_name: str,
    deck_identity: Mapping[str, Any],
    source_search_records: Sequence[Mapping[str, Any]],
    current_date: str | date | None = None,
) -> dict[str, Any]:
    ranked_sources = rank_public_sources(
        deck_name=deck_name,
        deck_identity=deck_identity,
        source_search_records=source_search_records,
        current_date=current_date,
    )
    evidence_rows = extract_source_evidence_rows(
        deck_name=deck_name,
        deck_identity=deck_identity,
        ranked_sources=ranked_sources,
        current_date=current_date,
    )
    draft = draft_source_documents(
        deck_name=deck_name,
        deck_identity=dict(deck_identity),
        evidence_rows=evidence_rows,
        current_date=current_date,
    )
    source_documents_payload = {
        "schema_version": 1,
        "deck_name": deck_name,
        "source_documents": draft["source_documents"],
    }
    verification = verify_source_documents(draft["source_documents"])
    return {
        "schema_version": 1,
        "deck_name": deck_name,
        "ranked_sources": ranked_sources,
        "source_evidence_rows": evidence_rows,
        "source_documents_payload": source_documents_payload,
        "source_document_draft_report": {
            "schema_version": 1,
            "deck_name": deck_name,
            "draft_summary": draft["draft_summary"],
            "unresolved_mentions": draft["unresolved_mentions"],
            "source_evidence_report": verification,
        },
        "source_autopilot_report": _build_report(
            deck_name=deck_name,
            ranked_sources=ranked_sources,
            evidence_rows=evidence_rows,
            draft=draft,
            verification=verification,
        ),
    }


def _mulligan_rows(
    deck_identity: Mapping[str, Any],
    source: Mapping[str, Any],
    base: Mapping[str, Any],
) -> list[dict[str, Any]]:
    mulligan = source.get("mulligan", {})
    if not isinstance(mulligan, Mapping):
        return []
    rows: list[dict[str, Any]] = []
    evidence = _text(
        mulligan.get("evidence_text_short", "Mulligan guidance from current public source.")
    )
    for card_id in _as_list(mulligan.get("keep_card_ids", [])):
        clean_card_id = _text(card_id)
        if clean_card_id:
            rows.append(
                {
                    **base,
                    "claim_kind": "mulligan_keep",
                    "cards": [clean_card_id],
                    "scope": "card",
                    "stance": "keep",
                    "evidence_text_short": evidence,
                    "source_confidence": "high",
                    "timing": "mulligan",
                }
            )
    for card_id in _as_list(mulligan.get("discard_card_ids", [])):
        clean_card_id = _text(card_id)
        if clean_card_id:
            rows.append(
                {
                    **base,
                    "claim_kind": "mulligan_discard",
                    "cards": [clean_card_id],
                    "scope": "card",
                    "stance": "discard",
                    "evidence_text_short": evidence,
                    "source_confidence": "high",
                    "timing": "mulligan",
                }
            )
    cost_min = _int_or_none(mulligan.get("discard_cost_min"))
    if cost_min is not None:
        for card in deck_identity.get("cards", []):
            if not isinstance(card, Mapping):
                continue
            cost = _int_or_none(card.get("cost"))
            card_id = _text(card.get("card_id", ""))
            if cost is not None and cost >= cost_min and card_id:
                rows.append(
                    {
                        **base,
                        "claim_kind": "mulligan_discard",
                        "cards": [card_id],
                        "scope": "card",
                        "stance": f"discard_cost_{cost_min}_or_more",
                        "evidence_text_short": evidence,
                        "source_confidence": "high",
                        "timing": "mulligan",
                    }
                )
    return rows


def _explicit_claim_rows(source: Mapping[str, Any], base: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for claim in _as_list(source.get("claims", [])):
        if not isinstance(claim, Mapping):
            continue
        row = {**base, **dict(claim)}
        row.setdefault(
            "source_confidence",
            "high" if str(base.get("source_family", "")).lower() in GUIDE_FAMILIES else "medium",
        )
        row.setdefault("scope", "card")
        row.setdefault("evidence_text_short", "Structured public source claim.")
        rows.append(row)
    return rows


def _build_report(
    *,
    deck_name: str,
    ranked_sources: Sequence[Mapping[str, Any]],
    evidence_rows: Sequence[Mapping[str, Any]],
    draft: Mapping[str, Any],
    verification: Mapping[str, Any],
) -> dict[str, Any]:
    lane_counts = Counter(_text(source.get("source_rank_lane", "")) for source in ranked_sources)
    claim_counts = Counter(_text(row.get("claim_kind", "")) for row in evidence_rows)
    guide_rows = [
        row for row in evidence_rows if _text(row.get("source_family", "")).lower() in GUIDE_FAMILIES
    ]
    lowerable_guide_rows = [
        row
        for row in guide_rows
        if _text(row.get("claim_kind", "")) not in {"source_note", "generic_advice"}
    ]
    warnings = verification.get("warnings", [])
    strong_candidate = bool(lowerable_guide_rows) and not draft.get("unresolved_mentions") and not warnings
    return {
        "schema_version": 1,
        "deck_name": deck_name,
        "status": "OK",
        "source_rank_summary": dict(sorted(lane_counts.items())),
        "claim_kind_counts": dict(sorted(claim_counts.items())),
        "strong_candidate": strong_candidate,
        "first_missing_source_action": (
            "none" if strong_candidate else "add_current_deck_guide_or_mulligan_guide"
        ),
        "draft_summary": draft["draft_summary"],
        "verification_summary": {
            "status": verification.get("status"),
            "warning_count": len(warnings) if isinstance(warnings, list) else 0,
        },
    }


def _source_base(
    deck_name: str,
    source: Mapping[str, Any],
    current_date: str | date | None,
) -> dict[str, Any]:
    match = source.get("deck_match", {})
    if not isinstance(match, Mapping):
        match = {}
    return {
        "source_url": _text(source.get("source_url", "")),
        "source_title": _text(source.get("source_title", "")),
        "source_family": _source_family_for_documents(source),
        "retrieved_at": _text(source.get("retrieved_at", "")) or _iso_datetime(current_date),
        "deck_name": deck_name,
        "archetype": _text(match.get("archetype", "")),
    }


def _source_family_for_documents(source: Mapping[str, Any]) -> str:
    family = _text(source.get("source_family", "guide")).lower()
    if family in DECKLIST_FAMILIES:
        return "metadata"
    if family == "hearthstonejson_static_semantics":
        return "static_semantics"
    return family or "guide"


def _append_unique(rows: list[dict[str, Any]], seen: set[tuple[Any, ...]], row: dict[str, Any]) -> None:
    key = (
        row.get("source_url"),
        row.get("claim_kind"),
        tuple(row.get("cards", [])),
        tuple(row.get("card_mentions", [])),
        row.get("stance"),
        row.get("condition"),
        row.get("runtime_block"),
    )
    if key in seen:
        return
    seen.add(key)
    rows.append(row)


def _rank_lane(
    family: str,
    deck_name_match: bool,
    card_overlap: int,
    current_year: int | None,
    source: Mapping[str, Any],
) -> str:
    if (
        family in GUIDE_FAMILIES
        and deck_name_match
        and card_overlap > 0
        and _record_year(source) == current_year
    ):
        return "guide_current_deck_match"
    if family in GUIDE_FAMILIES and card_overlap > 0:
        return "guide_card_overlap"
    if family in DECKLIST_FAMILIES:
        return "decklist_only"
    if family in STATIC_FAMILIES:
        return "static_semantics_only"
    return "source_unclassified"


def _deck_card_ids(deck_identity: Mapping[str, Any]) -> set[str]:
    return {
        _text(card.get("card_id", ""))
        for card in deck_identity.get("cards", [])
        if isinstance(card, Mapping) and _text(card.get("card_id", ""))
    }


def _record_year(record: Mapping[str, Any]) -> int | None:
    retrieved = _text(record.get("retrieved_at", ""))
    if len(retrieved) >= 4 and retrieved[:4].isdigit():
        return int(retrieved[:4])
    return None


def _current_year(current_date: str | date | None) -> int | None:
    if isinstance(current_date, date):
        return current_date.year
    text = _text(current_date)
    if len(text) >= 4 and text[:4].isdigit():
        return int(text[:4])
    return None


def _iso_datetime(current_date: str | date | None) -> str:
    if isinstance(current_date, date):
        return f"{current_date.isoformat()}T00:00:00Z"
    text = _text(current_date)
    if text:
        return text if "T" in text else f"{text}T00:00:00Z"
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _is_public_https(value: Any) -> bool:
    text = _text(value)
    return text.startswith("https://") and "localhost" not in text and "127.0.0.1" not in text


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _text(value: Any) -> str:
    return str(value or "").strip()


def _norm(value: Any) -> str:
    return "".join(ch for ch in _text(value).lower() if ch.isalnum())

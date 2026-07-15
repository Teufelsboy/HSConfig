from __future__ import annotations

from collections import Counter
from datetime import date, datetime
from typing import Any, Mapping, Sequence

from hsconfig.source_contract_matrix import source_contract_policy_by_claim_kind
from hsconfig.source_document_drafter import draft_source_documents
from hsconfig.source_evidence_policy import classify_source_evidence
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
        card_overlap = len(deck_card_ids & matched_ids)
        deck_name_match = _has_independent_deck_match(
            row,
            normalized_deck_name,
            card_overlap=card_overlap,
        )
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
        if current_year is not None and _publication_year(row) == current_year:
            score += 10
        if not _is_public_https(row.get("source_url", "")):
            score -= 100
        row["source_visibility"] = _source_visibility_for_documents(row)
        row["source_rank_score"] = score
        row["source_rank_lane"] = _rank_lane(
            family,
            deck_name_match,
            card_overlap,
            current_year,
            row,
        )
        policy = classify_source_evidence(
            row,
            deck_name=deck_name,
            current_date=current_date,
        )
        row.update(_policy_fields(policy, include_rank_lane=False))
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
            deck_identity=deck_identity,
            ranked_sources=ranked_sources,
            evidence_rows=evidence_rows,
            draft=draft,
            verification=verification,
            current_date=current_date,
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
            if _is_non_opening_hand_effect_card(card):
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
        if base.get("promotion_eligible") is False or claim.get("promotion_eligible") is False:
            row["promotion_eligible"] = False
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
    deck_identity: Mapping[str, Any],
    ranked_sources: Sequence[Mapping[str, Any]],
    evidence_rows: Sequence[Mapping[str, Any]],
    draft: Mapping[str, Any],
    verification: Mapping[str, Any],
    current_date: str | date | None,
) -> dict[str, Any]:
    lane_counts = Counter(_text(source.get("source_rank_lane", "")) for source in ranked_sources)
    claim_counts = Counter(_text(row.get("claim_kind", "")) for row in evidence_rows)
    guide_rows = [
        row for row in evidence_rows if _text(row.get("source_family", "")).lower() in GUIDE_FAMILIES
    ]
    lowerable_guide_rows = [
        row
        for row in guide_rows
        if _is_runtime_contract_candidate(row)
    ]
    strong_lowerable_guide_rows = [
        row for row in lowerable_guide_rows if _is_strong_guide_lane(row, current_date)
    ]
    strong_shaped_non_promoting_rows = [
        row
        for row in lowerable_guide_rows
        if _is_strong_guide_lane_shape(row, current_date)
        and _strong_lane_blockers(row)
    ]
    card_specific_lowerable_guide_rows = [
        row
        for row in strong_lowerable_guide_rows
        if _row_has_card_specific_claim(row)
    ]
    apply_surface_guide_rows = [
        row
        for row in strong_lowerable_guide_rows
        if _is_apply_surface_candidate(row)
    ]
    warnings = verification.get("warnings", [])
    blockers = _strong_candidate_blockers(
        card_specific_lowerable_guide_rows=card_specific_lowerable_guide_rows,
        apply_surface_guide_rows=apply_surface_guide_rows,
        strong_shaped_non_promoting_rows=strong_shaped_non_promoting_rows,
        draft=draft,
        verification=verification,
    )
    strong_candidate = not blockers
    strong_closure_summary = _build_strong_closure_summary(
        evidence_rows=evidence_rows,
        current_date=current_date,
        strong_candidate=strong_candidate,
        blockers=blockers,
    )
    return {
        "schema_version": 1,
        "deck_name": deck_name,
        "status": "OK",
        "source_rank_summary": dict(sorted(lane_counts.items())),
        "claim_kind_counts": dict(sorted(claim_counts.items())),
        "runtime_contract_candidate_count": len(lowerable_guide_rows),
        "card_specific_runtime_contract_candidate_count": len(
            card_specific_lowerable_guide_rows
        ),
        "strong_candidate": strong_candidate,
        "strong_candidate_blockers": blockers,
        "strong_closure_summary": strong_closure_summary,
        "first_missing_source_action": strong_closure_summary["first_missing_source_action"],
        "first_missing_source_action_by_card": _first_missing_source_action_by_card(
            deck_identity,
            evidence_rows,
            current_date=current_date,
        ),
        "non_promoting_claim_count": _non_promoting_claim_count(evidence_rows),
        "draft_summary": draft["draft_summary"],
        "verification_summary": {
            "status": verification.get("status"),
            "warning_count": len(warnings) if isinstance(warnings, list) else 0,
        },
    }


def _build_strong_closure_summary(
    *,
    evidence_rows: Sequence[Mapping[str, Any]],
    current_date: str | date | None,
    strong_candidate: bool,
    blockers: Sequence[str],
) -> dict[str, Any]:
    strong_rows = [
        row
        for row in evidence_rows
        if _is_strong_guide_lane(row, current_date) and _is_runtime_contract_candidate(row)
    ]
    has_explicit_mulligan_source = any(
        _text(row.get("claim_kind", "")) in {"mulligan_keep", "mulligan_discard"}
        for row in strong_rows
    )
    source_backed_strong_ready = (
        strong_candidate
        and bool(strong_rows)
        and has_explicit_mulligan_source
    )
    first_missing_source_action = _strong_closure_first_missing_source_action(
        source_backed_strong_ready=source_backed_strong_ready,
        has_explicit_mulligan_source=has_explicit_mulligan_source,
        blockers=blockers,
    )
    return {
        "technical_no_block": True,
        "semantic_status": (
            "SOURCE_BACKED_STRONG"
            if source_backed_strong_ready
            else "SOURCE_BACKED_PARTIAL"
        ),
        "source_backed_strong_ready": source_backed_strong_ready,
        "strong_evidence_row_count": len(strong_rows),
        "strong_candidate": strong_candidate,
        "strong_candidate_blockers": list(blockers),
        "first_missing_source_action": first_missing_source_action,
    }


def _strong_closure_first_missing_source_action(
    *,
    source_backed_strong_ready: bool,
    has_explicit_mulligan_source: bool,
    blockers: Sequence[str],
) -> str:
    if source_backed_strong_ready:
        return "none"
    if not has_explicit_mulligan_source:
        return "add_explicit_mulligan_source"
    if "no_apply_surface_guide_candidate" in blockers:
        return "add_runtime_lowerable_apply_surface_source"
    return "add_current_deck_guide_or_mulligan_guide"


def _strong_candidate_blockers(
    *,
    card_specific_lowerable_guide_rows: Sequence[Mapping[str, Any]],
    apply_surface_guide_rows: Sequence[Mapping[str, Any]],
    strong_shaped_non_promoting_rows: Sequence[Mapping[str, Any]],
    draft: Mapping[str, Any],
    verification: Mapping[str, Any],
) -> list[str]:
    blockers: list[str] = []
    if not card_specific_lowerable_guide_rows or not apply_surface_guide_rows:
        for blocker in sorted(
            {
                blocker
                for row in strong_shaped_non_promoting_rows
                for blocker in _strong_lane_blockers(row)
            }
        ):
            blockers.append(blocker)
    if not card_specific_lowerable_guide_rows:
        blockers.append("no_card_specific_runtime_contract_candidate")
    if not apply_surface_guide_rows:
        blockers.append("no_apply_surface_guide_candidate")
    if draft.get("unresolved_mentions"):
        blockers.append("unresolved_source_mentions")
    if verification.get("status") != "passed":
        blockers.append("source_document_verification_failed")
    warnings = verification.get("warnings", [])
    if warnings:
        blockers.append("source_document_warnings")
    return blockers


def _first_missing_source_action_by_card(
    deck_identity: Mapping[str, Any],
    evidence_rows: Sequence[Mapping[str, Any]],
    *,
    current_date: str | date | None,
) -> dict[str, str]:
    by_card: dict[str, str] = {}
    source_backed_cards = {
        str(card_id)
        for row in evidence_rows
        if _is_strong_guide_lane(row, current_date) and _is_runtime_contract_candidate(row)
        for card_id in _as_list(row.get("cards", []))
        if str(card_id)
    }
    for card in deck_identity.get("cards", []):
        if not isinstance(card, Mapping):
            continue
        card_id = _text(card.get("card_id", ""))
        if not card_id:
            continue
        by_card[card_id] = (
            "none"
            if card_id in source_backed_cards
            else "add_current_deck_guide_or_mulligan_guide"
        )
    return by_card


def _non_promoting_claim_count(evidence_rows: Sequence[Mapping[str, Any]]) -> int:
    return sum(1 for row in evidence_rows if _is_non_promoting_claim(row))


def _is_non_promoting_claim(row: Mapping[str, Any]) -> bool:
    if row.get("promotion_eligible") is False:
        return True
    family = _text(row.get("source_family", "")).lower()
    return family in (DECKLIST_FAMILIES | STATIC_FAMILIES) and row.get("claim_kind") == "card_role"


def _is_runtime_contract_candidate(row: Mapping[str, Any]) -> bool:
    policy = source_contract_policy_by_claim_kind().get(_text(row.get("claim_kind", "")))
    if not isinstance(policy, Mapping):
        return False
    if not bool(policy.get("runtime_lowerable")):
        return False
    allowed_surfaces = {str(surface) for surface in policy.get("allowed_surfaces", [])}
    if not allowed_surfaces:
        return False
    if (
        allowed_surfaces & {"mulligan", "cardid", "combo"}
        and not _row_has_card_specific_claim(row)
    ):
        return False
    if "combo" in allowed_surfaces and not row.get("sequence"):
        return False
    claim_kind = _text(row.get("claim_kind", ""))
    if claim_kind in {"discover_choice", "choose_one_choice"} and not row.get(
        "option_card_id"
    ):
        return False
    if claim_kind in {"card_role", "known_bad_pattern"} and not row.get("runtime_block"):
        return False
    return True


def _row_has_card_specific_claim(row: Mapping[str, Any]) -> bool:
    return bool(
        _as_list(row.get("cards", [])) or _as_list(row.get("card_mentions", []))
    )


def _is_apply_surface_candidate(row: Mapping[str, Any]) -> bool:
    claim_kind = _text(row.get("claim_kind", ""))
    if claim_kind in {"mulligan_keep", "mulligan_discard", "hero_power_transform"}:
        return False
    return _is_runtime_contract_candidate(row)


def _source_base(
    deck_name: str,
    source: Mapping[str, Any],
    current_date: str | date | None,
) -> dict[str, Any]:
    match = source.get("deck_match", {})
    if not isinstance(match, Mapping):
        match = {}
    source_rank_lane = _text(source.get("source_rank_lane", ""))
    deck_match_scope = _deck_match_scope(source, deck_name)
    source_visibility = _source_visibility_for_documents(source)
    source_for_policy = {**dict(source), "source_visibility": source_visibility}
    policy = classify_source_evidence(
        source_for_policy,
        deck_name=deck_name,
        current_date=current_date,
    )
    base: dict[str, Any] = {
        "source_url": _text(source.get("source_url", "")),
        "source_title": _text(source.get("source_title", "")),
        "source_family": _source_family_for_documents(source),
        "retrieved_at": _text(source.get("retrieved_at", "")) or _iso_datetime(current_date),
        "source_visibility": source_visibility,
        "source_rank_lane": source_rank_lane,
        "source_lane": _text(source.get("source_lane", ""))
        or _source_lane_for_rank(source_rank_lane, deck_match_scope),
        "deck_match_scope": deck_match_scope,
        "deck_name": _text(match.get("deck_name", "")),
        "archetype": _text(match.get("archetype", "")),
    }
    base.update(_policy_fields(policy, include_rank_lane=False))
    base["source_rank_lane"] = source_rank_lane
    base["source_visibility"] = source_visibility
    base["deck_match_scope"] = deck_match_scope
    base["source_lane"] = _text(source.get("source_lane", "")) or base["source_lane"]
    source_record_strength = _text(source.get("source_record_strength", ""))
    if source_record_strength:
        base["source_record_strength"] = source_record_strength
    if source.get("promotion_eligible") is False:
        base["promotion_eligible"] = False
    if source.get("publication_year") is not None:
        base["publication_year"] = source["publication_year"]
    for key in ("published_at", "publication_date", "published_date"):
        if _text(source.get(key, "")):
            base[key] = _text(source[key])
    return base


def _policy_fields(
    policy: Mapping[str, Any],
    *,
    include_rank_lane: bool,
) -> dict[str, Any]:
    keys = [
        "source_lane",
        "deck_match_scope",
        "promotion_eligible",
        "strong_promotion_eligible",
        "trust_ceiling",
        "promotion_blockers",
        "first_missing_source_action",
    ]
    if include_rank_lane:
        keys.append("source_rank_lane")
    return {key: policy[key] for key in keys if key in policy}


def _source_family_for_documents(source: Mapping[str, Any]) -> str:
    family = _text(source.get("source_family", "guide")).lower()
    if family in DECKLIST_FAMILIES:
        return "metadata"
    if family == "hearthstonejson_static_semantics":
        return "static_semantics"
    return family or "guide"


def _source_visibility_for_documents(source: Mapping[str, Any]) -> str:
    explicit = _text(source.get("source_visibility", "")).lower()
    if explicit:
        return explicit
    family = _text(source.get("source_family", "")).lower()
    if family in DECKLIST_FAMILIES:
        return "decklist_only"
    if family in GUIDE_FAMILIES:
        normalized_text = _text(source.get("normalized_text", ""))
        if len(normalized_text) >= 180:
            return "full_text"
        if normalized_text:
            return "snippet_only"
    return "unknown"


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
        and current_year is not None
        and _publication_year(source) == current_year
    ):
        return "guide_current_deck_match"
    if family in GUIDE_FAMILIES and card_overlap > 0:
        return "guide_card_overlap"
    if family in DECKLIST_FAMILIES:
        return "decklist_only"
    if family in STATIC_FAMILIES:
        return "static_semantics_only"
    return "source_unclassified"


def _source_lane_for_rank(source_rank_lane: str, deck_match_scope: str) -> str:
    if source_rank_lane in {"guide_current_deck_match", "guide_card_overlap"} and deck_match_scope in {
        "deck_matched",
        "deck_or_archetype_matched",
    }:
        return "deck_matched_public_guide"
    return source_rank_lane or "unknown"


def _is_non_opening_hand_effect_card(card: Mapping[str, Any]) -> bool:
    role_tokens = {
        _text(role).lower()
        for role in _as_list(card.get("roles", []))
        if _text(role)
    }
    if role_tokens & {"start_of_game", "hero_power_transform", "deckbuilding_effect"}:
        return True
    text = _text(card.get("text", "")).lower()
    if "start of game" in text:
        return True
    return _norm(card.get("name", "")) == "darkbishopbenedictus"


def _deck_card_ids(deck_identity: Mapping[str, Any]) -> set[str]:
    return {
        _text(card.get("card_id", ""))
        for card in deck_identity.get("cards", [])
        if isinstance(card, Mapping) and _text(card.get("card_id", ""))
    }


def _record_year(record: Mapping[str, Any]) -> int | None:
    return _publication_year(record)


def _publication_year(record: Mapping[str, Any]) -> int | None:
    explicit_year = _int_or_none(record.get("publication_year"))
    if explicit_year is not None:
        return explicit_year
    published = _text(
        record.get("published_at")
        or record.get("publication_date")
        or record.get("published_date")
    )
    if len(published) >= 4 and published[:4].isdigit():
        return int(published[:4])
    return None


def _has_independent_deck_match(
    source: Mapping[str, Any],
    normalized_deck_name: str,
    *,
    card_overlap: int,
) -> bool:
    if not normalized_deck_name:
        return False
    source_text = _norm(
        f"{_text(source.get('source_title', ''))} "
        f"{_text(source.get('normalized_text', ''))}"
    )
    match = source.get("deck_match", {})
    declared_deck_name = _norm(match.get("deck_name", "")) if isinstance(match, Mapping) else ""
    return declared_deck_name == normalized_deck_name and (
        normalized_deck_name in source_text or card_overlap > 0
    )


def _deck_match_scope(source: Mapping[str, Any], deck_name: str) -> str:
    explicit = _text(source.get("deck_match_scope", ""))
    if explicit:
        return explicit
    match = source.get("deck_match", {})
    if not isinstance(match, Mapping):
        match = {}
    matched_ids = _as_list(match.get("matched_card_ids", []))
    if _has_independent_deck_match(source, _norm(deck_name), card_overlap=len(matched_ids)):
        return "deck_or_archetype_matched"
    return "unknown"


def _is_strong_guide_lane(
    row: Mapping[str, Any],
    current_date: str | date | None,
) -> bool:
    return _is_strong_guide_lane_shape(row, current_date) and not _strong_lane_blockers(row)


def _is_strong_guide_lane_shape(
    row: Mapping[str, Any],
    current_date: str | date | None,
) -> bool:
    if _text(row.get("source_lane", "")) != "deck_matched_public_guide":
        return False
    if _text(row.get("source_rank_lane", "")) != "guide_current_deck_match":
        return False
    if _text(row.get("source_visibility", "")).lower() != "full_text":
        return False
    current_year = _current_year(current_date)
    if current_year is None:
        return False
    return _publication_year(row) == current_year


def _strong_lane_blockers(row: Mapping[str, Any]) -> list[str]:
    blockers: list[str] = []
    if row.get("promotion_eligible") is False:
        blockers.append("promotion_explicitly_disabled")
    if row.get("strong_promotion_eligible") is False:
        blockers.extend(
            str(blocker)
            for blocker in _as_list(row.get("promotion_blockers", []))
            if str(blocker)
        )
    if _is_non_promoting_claim(row):
        blockers.append("non_promoting_source_record")
    source_record_strength = _text(row.get("source_record_strength", "")).lower()
    if source_record_strength and source_record_strength != "candidate_strong":
        blockers.append(f"non_strong_source_record_strength_{source_record_strength}")
    return sorted(set(blockers))


def _current_year(current_date: str | date | None) -> int | None:
    if isinstance(current_date, date):
        return current_date.year
    text = _text(current_date)
    if len(text) >= 4 and text[:4].isdigit():
        return int(text[:4])
    return datetime.utcnow().year


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

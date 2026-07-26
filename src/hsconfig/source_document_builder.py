from __future__ import annotations

from hashlib import sha256
import json
from typing import Any

from hsconfig.source_freshness import classify_freshness as _classify_freshness
from hsconfig.source_document_model import (
    PUBLIC_GUIDE_IDENTITY_FIELDS,
    REQUIRED_CLAIM_KEYS,
    REQUIRED_SOURCE_KEYS,
    SUPPORTED_ATOMIC_CLAIM_KINDS,
    claim_can_lower_to_runtime,
    globalvalues_claim_signature,
)
from hsconfig.source_claim_conflicts import build_claim_conflict_report
from hsconfig.source_semantic_qualifiers import normalize_semantic_qualifiers


DECK_SCOPED_CLAIM_KINDS = {
    "archetype",
    "gameplan_posture",
    "globalvalue_numeric_tuning",
}


def classify_freshness(
    retrieved_at: str,
    *,
    current_date: Any = None,
) -> str:
    return _classify_freshness(retrieved_at, current_date=current_date)


def build_source_document_bundle(
    *,
    deck_identity: dict[str, Any],
    card_metadata: dict[str, Any],
    source_documents: list[dict[str, Any]],
    current_date: Any = None,
) -> dict[str, Any]:
    cards = _card_metadata_by_id(card_metadata)
    _merge_deck_identity_cards(cards, deck_identity)
    deck_card_ids = _deck_card_ids(deck_identity, cards)
    claims: list[dict[str, Any]] = []
    unsupported_claims: list[dict[str, Any]] = []
    source_evidence_index: list[dict[str, Any]] = []
    globalvalues_source_receipts: list[dict[str, Any]] = []

    for source_index, document in enumerate(source_documents, start=1):
        source_ref = f"source:{source_index}"
        missing_source_keys = _missing_keys(document, REQUIRED_SOURCE_KEYS)
        raw_claims = document.get("claims", [])
        if not isinstance(raw_claims, list):
            unsupported_claims.append(
                {
                    "source_ref": source_ref,
                    "reason": "claims_not_list",
                    "source_url": str(document.get("source_url", "")),
                    "missing_source_keys": missing_source_keys,
                }
            )
            raw_claims = []

        promoted_count = 0
        unsupported_count_before = len(unsupported_claims)
        if missing_source_keys:
            if raw_claims:
                for claim_index, raw_claim in enumerate(raw_claims, start=1):
                    if isinstance(raw_claim, dict):
                        unsupported = _unsupported(
                            raw_claim,
                            document,
                            source_ref,
                            claim_index,
                            "missing_source_keys",
                        )
                    else:
                        unsupported = {
                            "source_ref": source_ref,
                            "claim_index": claim_index,
                            "reason": "missing_source_keys",
                            "source_url": str(document.get("source_url", "")),
                        }
                    unsupported["missing_source_keys"] = missing_source_keys
                    unsupported_claims.append(unsupported)
            else:
                unsupported_claims.append(
                    {
                        "source_ref": source_ref,
                        "reason": "missing_source_keys",
                        "source_url": str(document.get("source_url", "")),
                        "missing_source_keys": missing_source_keys,
                    }
                )
            source_evidence_index.append(
                {
                    "source_ref": source_ref,
                    "source_id": str(document.get("source_id", f"source_{source_index}")),
                    "source_url": str(document.get("source_url", "")),
                    "source_title": str(document.get("source_title", "")),
                    "source_family": str(document.get("source_family", "unknown")),
                    "retrieved_at": str(document.get("retrieved_at", "")),
                    "claim_count": promoted_count,
                    "unsupported_claim_count": len(unsupported_claims) - unsupported_count_before,
                    "missing_source_keys": missing_source_keys,
                }
            )
            continue

        for claim_index, raw_claim in enumerate(raw_claims, start=1):
            if not isinstance(raw_claim, dict):
                unsupported_claims.append(
                    {
                        "source_ref": source_ref,
                        "claim_index": claim_index,
                        "reason": "claim_not_object",
                    }
                )
                continue
            normalized, unsupported = _normalize_source_claim(
                raw_claim,
                document=document,
                deck_identity=deck_identity,
                source_ref=source_ref,
                claim_index=claim_index,
                known_card_ids=deck_card_ids,
                current_date=current_date,
            )
            if unsupported is not None:
                unsupported_claims.append(unsupported)
                continue
            assert normalized is not None
            claims.append(normalized)
            receipt = _globalvalues_source_receipt(
                normalized,
                document=document,
                deck_identity=deck_identity,
                source_ref=source_ref,
            )
            if receipt is not None:
                globalvalues_source_receipts.append(receipt)
            promoted_count += 1

        source_evidence_index.append(
            {
                "source_ref": source_ref,
                "source_id": str(document.get("source_id", f"source_{source_index}")),
                "source_url": str(document.get("source_url", "")),
                "source_title": str(document.get("source_title", "")),
                "source_family": str(document.get("source_family", "unknown")),
                "retrieved_at": str(document.get("retrieved_at", "")),
                "claim_count": promoted_count,
                "unsupported_claim_count": len(unsupported_claims) - unsupported_count_before,
                "missing_source_keys": missing_source_keys,
            }
        )

    return {
        "claims": claims,
        "source_evidence_index": source_evidence_index,
        "globalvalues_source_receipts": globalvalues_source_receipts,
        "claim_coverage_report": _build_claim_coverage_report(
            deck_identity=deck_identity,
            cards=cards,
            claims=claims,
        ),
        "claim_conflict_report": build_claim_conflict_report(claims),
        "unsupported_claims": unsupported_claims,
    }


def _normalize_source_claim(
    raw_claim: dict[str, Any],
    *,
    document: dict[str, Any],
    deck_identity: dict[str, Any],
    source_ref: str,
    claim_index: int,
    known_card_ids: set[str],
    current_date: Any = None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    claim_kind = _clean_text(_raw_claim_kind(raw_claim))
    cards = _normalize_cards(_raw_claim_cards(raw_claim))
    scope = _clean_text(raw_claim.get("scope", "card")).lower() or "card"
    if claim_kind == "archetype" and not cards:
        scope = "deck"
    missing_claim_keys = _missing_claim_keys(raw_claim)
    if missing_claim_keys:
        unsupported = _unsupported(
            raw_claim,
            document,
            source_ref,
            claim_index,
            "missing_claim_keys",
        )
        unsupported["missing_claim_keys"] = missing_claim_keys
        return None, unsupported
    if not cards and not _is_deck_scoped(claim_kind, scope):
        return None, _unsupported(raw_claim, document, source_ref, claim_index, "not_card_specific")
    if claim_kind not in SUPPORTED_ATOMIC_CLAIM_KINDS:
        return None, _unsupported(
            raw_claim,
            document,
            source_ref,
            claim_index,
            "unsupported_claim_kind",
        )
    missing_cards = [card for card in cards if card not in known_card_ids]
    if missing_cards:
        unsupported = _unsupported(raw_claim, document, source_ref, claim_index, "card_not_in_deck")
        unsupported["missing_cards"] = missing_cards
        return None, unsupported

    evidence = _claim_evidence(raw_claim)
    source_confidence = _clean_text(raw_claim.get("source_confidence", ""))
    freshness_status = classify_freshness(
        str(document.get("retrieved_at", "")),
        current_date=current_date,
    )
    claim_confidence = _clean_text(raw_claim.get("claim_confidence", "")) or source_confidence
    if freshness_status == "stale" and claim_confidence == "high":
        claim_confidence = "medium"
    readiness = _claim_readiness(
        claim_kind=claim_kind,
        claim_confidence=claim_confidence,
        source_family=str(document.get("source_family", "guide")),
        cards=cards,
        scope=scope,
    )
    source_refs = [source_ref, *[str(item) for item in raw_claim.get("source_refs", [])]]
    if document.get("source_url"):
        source_refs.append(str(document["source_url"]))
    deck_match_scope = _claim_deck_match_scope(raw_claim, document, deck_identity)
    deck_name = _clean_text(document.get("deck_name", ""))
    if not deck_name and deck_match_scope in {
        "exact_deck_matched",
        "archetype_matched",
    }:
        deck_name = _clean_text(deck_identity.get("deck_name", ""))
    claim = {
        "claim_kind": claim_kind,
        "claim_type": _legacy_claim_type(claim_kind),
        "source": str(document.get("source_family", "guide")),
        "url": str(document.get("source_url", "")),
        "source_url": str(document.get("source_url", "")),
        "source_title": str(document.get("source_title", "")),
        "source_family": str(document.get("source_family", "guide")),
        "retrieved_at": str(document.get("retrieved_at", "")),
        "source_visibility": _claim_source_visibility(raw_claim, document),
        "deck_match_scope": deck_match_scope,
        "freshness_status": freshness_status,
        "cards": cards,
        "scope": scope,
        "stance": _clean_text(raw_claim.get("stance", "")),
        "conditions": _normalize_optional(raw_claim.get("conditions", raw_claim.get("condition", {}))),
        "claim": evidence,
        "evidence_text_short": evidence,
        "source_confidence": source_confidence,
        "claim_confidence": claim_confidence,
        "claim_readiness": readiness,
        "specificity_status": _specificity_status(cards=cards, scope=scope),
        "trust_ceiling": _trust_ceiling(
            claim_readiness=readiness,
            source_family=str(document.get("source_family", "guide")),
        ),
        "confidence": _confidence_for_readiness(readiness),
        "support_status": _support_status_for_readiness(readiness),
        "source_refs": list(dict.fromkeys(source_refs)),
    }
    source_lane = _claim_source_lane(raw_claim, document, deck_match_scope)
    if source_lane:
        claim["source_lane"] = source_lane
    exact_deck_evidence = _canonical_exact_deck_evidence(
        document,
        deck_identity,
    )
    if deck_match_scope == "exact_deck_matched" and exact_deck_evidence:
        claim["deck_match"] = {
            "exact_deck_evidence": exact_deck_evidence,
        }
    for key in ("source_type", "provenance", "source_type_family"):
        value = raw_claim.get(key, document.get(key))
        if value is not None and str(value).strip():
            claim[key] = str(value)
    source_identity_signals = _source_identity_signals(raw_claim, document)
    if source_identity_signals:
        claim["source_identity_signals"] = source_identity_signals
    for key in ("promotion_eligible", "source_record_strength"):
        if key in raw_claim:
            claim[key] = raw_claim[key]
    if deck_name:
        claim["deck_name"] = deck_name
    if document.get("archetype"):
        claim["archetype"] = str(document.get("archetype", ""))
    if "sequence" in raw_claim:
        claim["sequence"] = _normalize_cards(raw_claim["sequence"])
    if "values" in raw_claim:
        claim["values"] = _normalize_optional(raw_claim["values"])
    if claim_kind == "combo_sequence":
        for key in ("timing_kind", "operator"):
            if key in raw_claim:
                claim[key] = _clean_text(raw_claim[key])
    if "condition" in raw_claim:
        condition = _normalize_optional(raw_claim["condition"])
        claim["condition"] = condition
        if "runtime_block" in raw_claim:
            claim["conditions"] = condition
    if "runtime_block" in raw_claim:
        claim["runtime_block"] = _clean_text(raw_claim["runtime_block"])
    if "runtime_value" in raw_claim:
        claim["runtime_value"] = _clean_text(raw_claim["runtime_value"])
    if "key" in raw_claim:
        claim["key"] = _clean_text(raw_claim["key"])
    if "mechanic" in raw_claim:
        claim["mechanic"] = _clean_text(raw_claim["mechanic"]).lower()
    if "selector_kind" in raw_claim:
        claim["selector_kind"] = _clean_text(raw_claim["selector_kind"])
    if "selector" in raw_claim:
        claim["selector"] = _clean_text(raw_claim["selector"])
    for key in ("option_card_id", "option_card", "choice_card_id", "choice_card"):
        if key in raw_claim:
            claim[key] = _clean_text(raw_claim[key])
    qualifier_input = dict(raw_claim)
    qualifier_input.update(claim)
    semantic_qualifiers = normalize_semantic_qualifiers(qualifier_input)
    if semantic_qualifiers:
        claim["semantic_qualifiers"] = semantic_qualifiers
    runtime_lowerable = claim_can_lower_to_runtime(claim)
    claim["runtime_lowerable"] = runtime_lowerable
    claim["runtime_lowering_reason"] = (
        "runtime_lowerable" if runtime_lowerable else "claim_not_runtime_lowerable"
    )
    if evidence:
        claim["evidence_hash"] = sha256(evidence.encode("utf-8")).hexdigest()[:16]
    claim["claim_id"] = _clean_text(raw_claim.get("claim_id", "")) or _claim_id(claim)
    claim["source_claim_ids"] = [claim["claim_id"]]
    return claim, None


def _claim_source_visibility(
    raw_claim: dict[str, Any],
    document: dict[str, Any],
) -> str:
    value = _clean_text(raw_claim.get("source_visibility", ""))
    if value:
        return value
    value = _clean_text(document.get("source_visibility", ""))
    return value or "full_text"


def _claim_source_lane(
    raw_claim: dict[str, Any],
    document: dict[str, Any],
    deck_match_scope: str,
) -> str:
    for container in (raw_claim, document):
        value = _clean_text(container.get("source_lane", ""))
        if value and value.lower() != "unknown":
            if (
                deck_match_scope == "archetype_matched"
                and value.lower() == "deck_matched_public_guide"
            ):
                return "archetype_matched_public_guide"
            return value
    return ""


def _claim_deck_match_scope(
    raw_claim: dict[str, Any],
    document: dict[str, Any],
    deck_identity: dict[str, Any],
) -> str:
    for container in (raw_claim, document):
        value = _clean_text(container.get("deck_match_scope", ""))
        normalized = value.lower()
        if normalized == "exact_deck_matched":
            return (
                "exact_deck_matched"
                if _document_has_exact_deck_evidence(document, deck_identity)
                else "archetype_matched"
            )
        if normalized in {"deck_matched", "deck_or_archetype_matched"}:
            return "archetype_matched"
        if value and normalized != "unknown":
            return value
    if _clean_text(document.get("deck_name", "")) or _clean_text(
        document.get("archetype", "")
    ):
        return "archetype_matched"
    if _document_matches_deck_identity(document, deck_identity):
        return "archetype_matched"
    return "unknown"


def _document_has_exact_deck_evidence(
    document: dict[str, Any],
    deck_identity: dict[str, Any],
) -> bool:
    return bool(_canonical_exact_deck_evidence(document, deck_identity))


def _canonical_exact_deck_evidence(
    document: dict[str, Any],
    deck_identity: dict[str, Any],
) -> dict[str, Any]:
    deck_match = document.get("deck_match", {})
    if not isinstance(deck_match, dict):
        return {}
    exact = deck_match.get("exact_deck_evidence", {})
    if not isinstance(exact, dict) or exact.get("matched") is not True:
        return {}
    evidence_fingerprint = _clean_text(
        exact.get("matched_deck_fingerprint", "")
    )
    target_fingerprint = _clean_text(deck_identity.get("deck_fingerprint", ""))
    if not evidence_fingerprint or evidence_fingerprint != target_fingerprint:
        return {}
    canonical = {
        "matched": True,
        "matched_deck_fingerprint": target_fingerprint,
    }
    for key in ("candidate_count", "decoded_candidate_count"):
        if key in exact:
            count = _nonnegative_int(exact.get(key))
            if count is not None:
                canonical[key] = count
    hashes = exact.get("candidate_deck_code_hashes")
    if isinstance(hashes, list):
        canonical["candidate_deck_code_hashes"] = sorted(
            str(value).strip() for value in hashes if str(value).strip()
        )
    return canonical


def _source_identity_signals(
    raw_claim: dict[str, Any],
    document: dict[str, Any],
) -> list[dict[str, str]]:
    signals: list[dict[str, str]] = []
    for origin, container in (("document", document), ("claim", raw_claim)):
        for field in PUBLIC_GUIDE_IDENTITY_FIELDS:
            value = _clean_text(container.get(field, ""))
            if value:
                signals.append(
                    {
                        "origin": origin,
                        "field": field,
                        "value": value,
                    }
                )
    return signals


def _nonnegative_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = int(value.strip())
        except ValueError:
            return None
    else:
        return None
    return parsed if parsed >= 0 else None


def _globalvalues_source_receipt(
    claim: dict[str, Any],
    *,
    document: dict[str, Any],
    deck_identity: dict[str, Any],
    source_ref: str,
) -> dict[str, Any] | None:
    exact = _canonical_exact_deck_evidence(document, deck_identity)
    if (
        int(exact.get("candidate_count", 0)) < 1
        or int(exact.get("decoded_candidate_count", 0)) < 1
        or not exact.get("candidate_deck_code_hashes")
    ):
        return None
    return {
        "receipt_kind": "canonical_exact_deck_source_document",
        "source_ref": source_ref,
        "source_url": str(document.get("source_url", "")),
        "matched_deck_fingerprint": str(
            exact["matched_deck_fingerprint"]
        ),
        "claim_id": str(claim.get("claim_id", "")),
        "claim_signature": globalvalues_claim_signature(claim),
    }


def _document_matches_deck_identity(
    document: dict[str, Any],
    deck_identity: dict[str, Any],
) -> bool:
    deck_name = _compact_text(deck_identity.get("deck_name", ""))
    if not deck_name:
        return False
    searchable = _compact_text(
        f"{document.get('source_title', '')} {document.get('source_url', '')}"
    )
    return bool(searchable and deck_name in searchable)


def _build_claim_coverage_report(
    *,
    deck_identity: dict[str, Any],
    cards: dict[str, dict[str, Any]],
    claims: list[dict[str, Any]],
) -> dict[str, Any]:
    source_claim_ids_by_card: dict[str, list[str]] = {card_id: [] for card_id in cards}
    guide_claim_ids_by_card: dict[str, list[str]] = {card_id: [] for card_id in cards}
    static_claim_ids_by_card: dict[str, list[str]] = {card_id: [] for card_id in cards}
    for claim in claims:
        for card_id in claim.get("cards", []):
            normalized_card_id = str(card_id)
            claim_id = str(claim["claim_id"])
            source_claim_ids_by_card.setdefault(normalized_card_id, []).append(claim_id)
            if _claim_counts_as_guide_backed(claim):
                guide_claim_ids_by_card.setdefault(normalized_card_id, []).append(claim_id)
            elif _claim_counts_as_static_semantics(claim):
                static_claim_ids_by_card.setdefault(normalized_card_id, []).append(claim_id)

    rows: dict[str, dict[str, Any]] = {}
    status_counts = {
        "guide_backed": 0,
        "static_semantics_backfilled": 0,
        "uncovered_low_confidence": 0,
    }
    for card_id, card in sorted(cards.items()):
        source_claim_ids = list(dict.fromkeys(source_claim_ids_by_card.get(card_id, [])))
        guide_claim_ids = list(dict.fromkeys(guide_claim_ids_by_card.get(card_id, [])))
        static_claim_ids = list(dict.fromkeys(static_claim_ids_by_card.get(card_id, [])))
        if guide_claim_ids:
            coverage_status = "guide_backed"
        elif static_claim_ids:
            coverage_status = "static_semantics_backfilled"
        else:
            coverage_status = "uncovered_low_confidence"
        status_counts[coverage_status] += 1
        rows[card_id] = {
            "card_id": card_id,
            "name": str(card.get("name", card_id)),
            "coverage_status": coverage_status,
            "source_claim_ids": source_claim_ids,
        }

    return {
        "deck_name": str(deck_identity.get("deck_name", "Deck")),
        "total_cards": len(cards),
        "cards": rows,
        "summary": status_counts,
    }


def _unsupported(
    raw_claim: dict[str, Any],
    document: dict[str, Any],
    source_ref: str,
    claim_index: int,
    reason: str,
) -> dict[str, Any]:
    return {
        "source_ref": source_ref,
        "claim_index": claim_index,
        "reason": reason,
        "claim_kind": _clean_text(_raw_claim_kind(raw_claim)),
        "cards": _normalize_cards(_raw_claim_cards(raw_claim)),
        "source_url": str(document.get("source_url", "")),
        "source_title": str(document.get("source_title", "")),
        "evidence_text_short": _claim_evidence(raw_claim),
    }


def _card_metadata_by_id(card_metadata: dict[str, Any] | list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    if isinstance(card_metadata, list):
        return {str(row["card_id"]): dict(row) for row in card_metadata}
    if isinstance(card_metadata, dict) and isinstance(card_metadata.get("cards"), list):
        return {str(row["card_id"]): dict(row) for row in card_metadata["cards"]}
    cards: dict[str, dict[str, Any]] = {}
    if isinstance(card_metadata, dict):
        for card_id, row in card_metadata.items():
            if isinstance(row, dict):
                value = dict(row)
                value.setdefault("card_id", str(card_id))
                cards[str(card_id)] = value
    return cards


def _merge_deck_identity_cards(cards: dict[str, dict[str, Any]], deck_identity: dict[str, Any]) -> None:
    for card in deck_identity.get("cards", []):
        if not isinstance(card, dict):
            continue
        card_id = str(card.get("card_id", "")).strip()
        if not card_id:
            continue
        row = cards.setdefault(card_id, {})
        row.setdefault("card_id", card_id)
        for key in ("name", "count"):
            if key in card and key not in row:
                row[key] = card[key]


def _deck_card_ids(deck_identity: dict[str, Any], cards: dict[str, dict[str, Any]]) -> set[str]:
    deck_cards = [
        str(card.get("card_id", "")).strip()
        for card in deck_identity.get("cards", [])
        if isinstance(card, dict) and str(card.get("card_id", "")).strip()
    ]
    if deck_cards:
        return set(deck_cards)
    return set(cards)


def _missing_keys(document: dict[str, Any], keys: tuple[str, ...]) -> list[str]:
    return [key for key in keys if not _clean_text(document.get(key, ""))]


def _missing_claim_keys(raw_claim: dict[str, Any]) -> list[str]:
    missing = []
    for key in REQUIRED_CLAIM_KEYS:
        if key == "claim_kind":
            value = _raw_claim_kind(raw_claim)
        elif key == "evidence_text_short":
            value = _claim_evidence(raw_claim)
        else:
            value = raw_claim.get(key, "")
        if not _clean_text(value):
            missing.append(key)
    return missing


def _is_deck_scoped(claim_kind: str, scope: str) -> bool:
    return claim_kind in DECK_SCOPED_CLAIM_KINDS and scope in {"deck", "archetype"}


def _legacy_claim_type(claim_kind: str) -> str:
    return {
        "mulligan_keep": "mulligan_keep",
        "mulligan_discard": "mulligan_discard",
        "card_role": "card_role",
        "targeting_rule": "targeting",
        "combo_sequence": "combo",
        "gameplan_posture": "gameplan_posture",
        "hero_power_transform": "hero_power_transform",
        "mechanic_usage": "mechanic_usage",
        "known_bad_pattern": "bad_pattern",
        "tech_slot": "tech_slot",
        "replacement_option": "replacement_option",
        "archetype": "archetype",
        "discover_choice": "discover_choice",
        "choose_one_choice": "choose_one_choice",
        "globalvalue_numeric_tuning": "globalvalue_numeric_tuning",
    }.get(claim_kind, "general")


def _claim_readiness(
    *,
    claim_kind: str,
    claim_confidence: str,
    source_family: str,
    cards: list[str],
    scope: str,
) -> str:
    confidence = claim_confidence.lower()
    family = source_family.lower()
    if confidence == "low":
        return "explicit_low_confidence"
    if family in {"card_text", "metadata", "hearthstonejson", "static_semantics"}:
        return "source_backed_static_semantics"
    if cards:
        return "guide_backed"
    if claim_kind == "gameplan_posture" and scope in {"deck", "archetype"}:
        return "guide_backed"
    if scope in {"deck", "archetype"}:
        return "archetype_inferred"
    return "contract_gap"


def _specificity_status(*, cards: list[str], scope: str) -> str:
    if len(cards) > 1:
        return "multi_card_specific"
    if len(cards) == 1:
        return "card_specific"
    if scope in {"deck", "archetype"}:
        return "deck_scoped"
    return "not_card_specific"


def _trust_ceiling(*, claim_readiness: str, source_family: str) -> str:
    if claim_readiness == "explicit_low_confidence":
        return "report_only"
    if claim_readiness == "source_backed_static_semantics":
        return "static_semantics"
    if source_family.lower() in {"guide", "guide_fixture", "mulligan_guide", "matchup_guide"}:
        return "guide"
    return "source"


def _confidence_for_readiness(readiness: str) -> str:
    if readiness == "guide_backed":
        return "guide_backed"
    if readiness == "source_backed_static_semantics":
        return "source_backed_static_semantics"
    if readiness == "archetype_inferred":
        return "archetype_inferred"
    return "generic_low_confidence"


def _support_status_for_readiness(readiness: str) -> str:
    if readiness == "source_backed_static_semantics":
        return "static_semantics"
    return "source_backed"


def _claim_counts_as_guide_backed(claim: dict[str, Any]) -> bool:
    return str(claim.get("claim_readiness", "")).lower() == "guide_backed"


def _claim_counts_as_static_semantics(claim: dict[str, Any]) -> bool:
    return str(claim.get("claim_readiness", "")).lower() == "source_backed_static_semantics"


def _claim_id(claim: dict[str, Any]) -> str:
    payload = {
        key: value
        for key, value in claim.items()
        if key not in {"claim_id", "source_claim_ids"}
    }
    canonical = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    return f"claim_{sha256(canonical.encode('utf-8')).hexdigest()[:12]}"


def _normalize_cards(cards: Any) -> list[str]:
    if cards is None:
        return []
    if isinstance(cards, str):
        candidates = [cards]
    else:
        candidates = list(cards)
    normalized: list[str] = []
    for candidate in candidates:
        card = _clean_text(candidate)
        if card and card not in normalized:
            normalized.append(card)
    return normalized


def _compact_text(value: Any) -> str:
    return "".join(ch for ch in str(value or "").lower() if ch.isalnum())


def _raw_claim_kind(raw_claim: dict[str, Any]) -> Any:
    return raw_claim.get("claim_kind", raw_claim.get("claim_type", raw_claim.get("kind", "")))


def _raw_claim_cards(raw_claim: dict[str, Any]) -> Any:
    if "cards" in raw_claim:
        return raw_claim["cards"]
    if "card_id" in raw_claim:
        return raw_claim["card_id"]
    return []


def _normalize_optional(value: Any) -> Any:
    if isinstance(value, str):
        return _clean_text(value)
    if isinstance(value, list):
        return [_normalize_optional(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _normalize_optional(value[key]) for key in sorted(value)}
    return value


def _claim_evidence(raw_claim: dict[str, Any]) -> str:
    return _clean_text(
        raw_claim.get(
            "evidence_text_short",
            raw_claim.get("claim", raw_claim.get("reason", "")),
        )
    )


def _clean_text(value: Any) -> str:
    return " ".join(str(value).strip().split())

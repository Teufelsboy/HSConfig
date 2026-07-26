from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any

from hsconfig.mechanic_support import mechanic_static_claim_allowed
from hsconfig.source_document_builder import build_source_document_bundle
from hsconfig.source_semantic_qualifiers import normalize_semantic_qualifiers
from hsconfig.static_semantics import (
    infer_static_semantics,
    static_semantic_deck_card_counts,
    static_semantic_has_unsatisfied_highlander_condition,
    static_semantic_runtime_claim_allowed,
)


SUPPORTED_CLAIM_KINDS = {
    "mulligan_keep",
    "mulligan_discard",
    "card_role",
    "discover_choice",
    "choose_one_choice",
    "targeting_rule",
    "combo_sequence",
    "gameplan_posture",
    "hero_power_transform",
    "mechanic_usage",
}

STATIC_TEXT_CLAIM_RULES = (
    ("discover", "discover_choice", "discover"),
    ("choose one", "choose_one_choice", "choose_one"),
    ("equip", "mechanic_usage", "weapon"),
    ("weapon", "mechanic_usage", "weapon"),
)
DIAGNOSTIC_ONLY_STATIC_MECHANICS = {
    "destroy",
    "hero_power",
    "silence",
    "transform",
}

@dataclass(frozen=True)
class ClaimBuildResult:
    claims: list[dict[str, Any]]
    unsupported_claims: list[dict[str, Any]]
    coverage: dict[str, Any]
    source_evidence_index: list[dict[str, Any]]


def build_guide_claim_bundle(
    *,
    deck_identity: dict[str, Any],
    card_metadata: dict[str, dict[str, Any]] | dict[str, Any] | list[dict[str, Any]],
    source_documents: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    cards = _card_metadata_by_id(card_metadata)
    source_documents = source_documents or []
    claims: list[dict[str, Any]] = []
    unsupported_claims: list[dict[str, Any]] = []
    source_evidence_index: list[dict[str, Any]] = []
    canonical_source_receipts: list[dict[str, Any]] = []
    claim_conflict_report = {"conflict_count": 0, "conflicts": []}

    if source_documents:
        source_document_bundle = build_source_document_bundle(
            deck_identity=deck_identity,
            card_metadata=card_metadata,
            source_documents=source_documents,
        )
        claims.extend(source_document_bundle["claims"])
        unsupported_claims.extend(source_document_bundle["unsupported_claims"])
        source_evidence_index.extend(source_document_bundle["source_evidence_index"])
        canonical_source_receipts.extend(
            source_document_bundle.get(
                "canonical_source_receipts",
                source_document_bundle.get("globalvalues_source_receipts", []),
            )
        )
        claim_conflict_report = source_document_bundle["claim_conflict_report"]

    guide_backed_cards = {
        card
        for claim in claims
        if _claim_counts_as_guide_backed(claim)
        for card in claim.get("cards", [])
    }

    static_claims = _static_semantic_claims(
        cards,
        deck_identity=deck_identity,
        existing_claims=claims,
    )
    claims.extend(static_claims)
    claims = _dedupe_claims(claims)
    static_semantic_cards = {
        card
        for claim in claims
        if _claim_counts_as_static_semantics(claim)
        for card in claim.get("cards", [])
    }
    uncovered_cards = sorted(set(cards) - guide_backed_cards - static_semantic_cards)
    coverage = {
        "deck_name": str(deck_identity.get("deck_name", "Deck")),
        "total_cards": len(cards),
        "guide_backed_cards": len(guide_backed_cards),
        "static_semantic_cards": len(static_semantic_cards),
        "uncovered_cards": uncovered_cards,
        "claim_kinds": sorted({str(claim.get("claim_kind")) for claim in claims}),
    }
    claim_coverage_report = _build_claim_coverage_report(
        deck_identity=deck_identity,
        cards=cards,
        claims=claims,
        guide_backed_cards=guide_backed_cards,
        static_semantic_cards=static_semantic_cards,
    )
    result = ClaimBuildResult(
        claims=claims,
        unsupported_claims=unsupported_claims,
        coverage=coverage,
        source_evidence_index=source_evidence_index,
    )
    return {
        "claims": result.claims,
        "unsupported_claims": result.unsupported_claims,
        "coverage": result.coverage,
        "source_evidence_index": result.source_evidence_index,
        "canonical_source_receipts": canonical_source_receipts,
        "globalvalues_source_receipts": canonical_source_receipts,
        "claim_coverage_report": claim_coverage_report,
        "claim_conflict_report": claim_conflict_report,
    }


def _build_claim_coverage_report(
    *,
    deck_identity: dict[str, Any],
    cards: dict[str, dict[str, Any]],
    claims: list[dict[str, Any]],
    guide_backed_cards: set[str],
    static_semantic_cards: set[str],
) -> dict[str, Any]:
    claim_ids_by_card: dict[str, list[str]] = {card_id: [] for card_id in cards}
    for claim in claims:
        for card_id in claim.get("cards", []):
            claim_ids_by_card.setdefault(str(card_id), []).append(str(claim["claim_id"]))

    status_counts = {
        "guide_backed": 0,
        "static_semantics_backfilled": 0,
        "uncovered_low_confidence": 0,
    }
    rows: dict[str, dict[str, Any]] = {}
    for card_id, card in sorted(cards.items()):
        if card_id in guide_backed_cards:
            coverage_status = "guide_backed"
        elif card_id in static_semantic_cards:
            coverage_status = "static_semantics_backfilled"
        else:
            coverage_status = "uncovered_low_confidence"
        status_counts[coverage_status] += 1
        rows[card_id] = {
            "card_id": card_id,
            "name": str(card.get("name", card_id)),
            "coverage_status": coverage_status,
            "source_claim_ids": list(dict.fromkeys(claim_ids_by_card.get(card_id, []))),
        }

    return {
        "deck_name": str(deck_identity.get("deck_name", "Deck")),
        "total_cards": len(cards),
        "cards": rows,
        "summary": status_counts,
    }


def _normalize_source_claim(
    raw_claim: dict[str, Any],
    *,
    document: dict[str, Any],
    source_ref: str,
    claim_index: int,
    known_card_ids: set[str],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    claim_kind = _clean_text(raw_claim.get("claim_kind", raw_claim.get("claim_type", "")))
    cards = _normalize_cards(raw_claim.get("cards", []))
    scope = _clean_text(raw_claim.get("scope", "card")).lower() or "card"
    if not cards and not (claim_kind == "gameplan_posture" and scope == "deck"):
        return None, _unsupported(raw_claim, document, source_ref, claim_index, "not_card_specific")
    if claim_kind not in SUPPORTED_CLAIM_KINDS:
        return None, _unsupported(raw_claim, document, source_ref, claim_index, "unsupported_claim_kind")
    missing_cards = [card for card in cards if card not in known_card_ids]
    if missing_cards:
        unsupported = _unsupported(raw_claim, document, source_ref, claim_index, "card_not_in_deck")
        unsupported["missing_cards"] = missing_cards
        return None, unsupported

    evidence = _clean_text(raw_claim.get("evidence_text_short", raw_claim.get("claim", "")))
    source_refs = [source_ref, *[str(item) for item in raw_claim.get("source_refs", [])]]
    if document.get("source_url"):
        source_refs.append(str(document["source_url"]))
    claim = {
        "claim_kind": claim_kind,
        "claim_type": _legacy_claim_type(claim_kind),
        "source": str(document.get("source_family", "guide")),
        "url": str(document.get("source_url", "")),
        "source_url": str(document.get("source_url", "")),
        "source_title": str(document.get("source_title", "")),
        "source_family": str(document.get("source_family", "guide")),
        "retrieved_at": str(document.get("retrieved_at", "")),
        "cards": cards,
        "scope": scope,
        "stance": _clean_text(raw_claim.get("stance", "")),
        "conditions": _normalize_optional(raw_claim.get("conditions", raw_claim.get("condition", {}))),
        "claim": evidence,
        "evidence_text_short": evidence,
        "source_confidence": _clean_text(raw_claim.get("source_confidence", "medium")) or "medium",
        "claim_confidence": _clean_text(raw_claim.get("claim_confidence", raw_claim.get("source_confidence", "medium"))) or "medium",
        "confidence": "guide_backed",
        "support_status": "source_backed",
        "source_refs": list(dict.fromkeys(source_refs)),
    }
    if "sequence" in raw_claim:
        claim["sequence"] = _normalize_cards(raw_claim["sequence"])
    if "values" in raw_claim:
        claim["values"] = _normalize_optional(raw_claim["values"])
    if "condition" in raw_claim:
        condition = _normalize_optional(raw_claim["condition"])
        claim["condition"] = condition
        if "runtime_block" in raw_claim:
            claim["conditions"] = condition
    if "runtime_block" in raw_claim:
        claim["runtime_block"] = _clean_text(raw_claim["runtime_block"])
    if "runtime_value" in raw_claim:
        claim["runtime_value"] = _clean_text(raw_claim["runtime_value"])
    if "mechanic" in raw_claim:
        claim["mechanic"] = _clean_text(raw_claim["mechanic"]).lower()
    if evidence:
        claim["evidence_hash"] = sha256(evidence.encode("utf-8")).hexdigest()[:16]
    claim["claim_id"] = _claim_id(claim)
    claim["source_claim_ids"] = [claim["claim_id"]]
    return claim, None


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
        "claim_kind": _clean_text(raw_claim.get("claim_kind", raw_claim.get("claim_type", ""))),
        "cards": _normalize_cards(raw_claim.get("cards", [])),
        "source_url": str(document.get("source_url", "")),
        "source_title": str(document.get("source_title", "")),
        "evidence_text_short": _clean_text(raw_claim.get("evidence_text_short", raw_claim.get("claim", ""))),
    }


def _static_semantic_claims(
    cards: dict[str, dict[str, Any]],
    *,
    deck_identity: dict[str, Any],
    existing_claims: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    existing_pairs = {
        (claim.get("claim_kind"), card, claim.get("mechanic", ""))
        for claim in existing_claims
        for card in claim.get("cards", [])
    }
    existing_kind_cards = {
        (claim.get("claim_kind"), card)
        for claim in existing_claims
        for card in claim.get("cards", [])
    }
    emitted_keys = set(existing_pairs)
    deck_card_counts = static_semantic_deck_card_counts(deck_identity)
    claims = []
    for card_id, card in sorted(cards.items()):
        text = _card_text(card).lower()
        semantics = infer_static_semantics(card)
        unsatisfied_highlander = static_semantic_has_unsatisfied_highlander_condition(
            semantics,
            deck_card_counts,
        )
        if (
            ("hero power becomes" in text or "enter shadowform" in text)
            and ("hero_power_transform", card_id) not in existing_kind_cards
            and not unsatisfied_highlander
        ):
            claims.append(
                _static_claim(
                    card_id=card_id,
                    card=card,
                    claim_kind="hero_power_transform",
                    mechanic="hero_power_transform",
                    stance="enable_transformed_hero_power",
                )
            )
            emitted_keys.add(("hero_power_transform", card_id, "hero_power_transform"))
        for keyword, claim_kind, mechanic_family in STATIC_TEXT_CLAIM_RULES:
            if keyword not in text or (claim_kind, card_id) in existing_kind_cards:
                continue
            if (
                keyword == "hero power"
                and ("hero power becomes" in text or "enter shadowform" in text)
            ):
                continue
            if unsatisfied_highlander and mechanic_static_claim_allowed(mechanic_family):
                continue
            key = (claim_kind, card_id, mechanic_family)
            if key in emitted_keys:
                continue
            claims.append(
                _static_claim(
                    card_id=card_id,
                    card=card,
                    claim_kind=claim_kind,
                    mechanic=mechanic_family,
                    mechanic_family=mechanic_family,
                    keyword=keyword,
                    stance=f"use_{mechanic_family}_according_to_card_text",
                )
            )
            emitted_keys.add(key)
        for mechanic in _static_mechanic_usage_families(
            card,
            text=text,
            semantics=semantics,
            suppress_lowerable=unsatisfied_highlander,
        ):
            key = ("mechanic_usage", card_id, mechanic)
            if key in emitted_keys:
                continue
            claims.append(
                _static_claim(
                    card_id=card_id,
                    card=card,
                    claim_kind="mechanic_usage",
                    mechanic=mechanic,
                    stance=f"use_{mechanic}_according_to_card_text",
                )
            )
            emitted_keys.add(key)
    return claims


def _static_mechanic_usage_families(
    card: dict[str, Any],
    *,
    text: str,
    semantics: dict[str, Any] | None = None,
    suppress_lowerable: bool = False,
) -> list[str]:
    if semantics is None:
        semantics = infer_static_semantics(card)
    families = semantics.get("families", [])
    mechanics: list[str] = []
    for family in families:
        mechanic = _clean_text(family).lower()
        if not mechanic or mechanic in mechanics:
            continue
        if not _static_mechanic_usage_allowed(
            mechanic,
            text=text,
            semantics=semantics,
            suppress_lowerable=suppress_lowerable,
        ):
            continue
        mechanics.append(mechanic)
    return mechanics


def _static_mechanic_usage_allowed(
    mechanic: str,
    *,
    text: str,
    semantics: dict[str, Any] | None = None,
    suppress_lowerable: bool = False,
) -> bool:
    if mechanic == "hero_power_transform":
        return False
    if mechanic == "transform" and ("hero power becomes" in text or "enter shadowform" in text):
        return False
    if mechanic == "hero_power" and ("hero power becomes" in text or "shadowform" in text):
        return False
    if suppress_lowerable and mechanic_static_claim_allowed(mechanic):
        return False
    return mechanic_static_claim_allowed(mechanic) and static_semantic_runtime_claim_allowed(
        mechanic,
        semantics,
    )


def _static_claim(
    *,
    card_id: str,
    card: dict[str, Any],
    claim_kind: str,
    mechanic: str,
    stance: str,
    mechanic_family: str | None = None,
    keyword: str | None = None,
) -> dict[str, Any]:
    evidence = _card_text(card)
    evidence_text_short = (
        f"Static card text contains {keyword}." if keyword else evidence
    )
    claim = {
        "claim_kind": claim_kind,
        "claim_type": _legacy_claim_type(claim_kind),
        "source": "hearthstonejson_static_semantics",
        "url": "",
        "source_url": "",
        "source_title": "HearthstoneJSON static card text",
        "source_family": "hearthstonejson_static_semantics",
        "retrieved_at": "",
        "cards": [card_id],
        "stance": stance,
        "conditions": {},
        "claim": evidence,
        "evidence_text_short": evidence_text_short,
        "source_confidence": "medium",
        "claim_confidence": "medium",
        "claim_readiness": "source_backed_static_semantics",
        "specificity_status": "card_specific",
        "trust_ceiling": (
            "report_only" if mechanic in DIAGNOSTIC_ONLY_STATIC_MECHANICS else "static_semantics"
        ),
        "confidence": "source_backed_static_semantics",
        "support_status": "static_semantics",
        "mechanic": mechanic,
        "source_refs": ["hearthstonejson_static_semantics"],
    }
    claim["mechanic_family"] = mechanic_family or mechanic
    semantic_qualifiers = normalize_semantic_qualifiers(
        claim,
        card_roles={
            card_id: {"semantic_families": infer_static_semantics(card).get("families", [])}
        },
    )
    if semantic_qualifiers:
        claim["semantic_qualifiers"] = semantic_qualifiers
    if evidence:
        claim["evidence_hash"] = sha256(evidence.encode("utf-8")).hexdigest()[:16]
    claim["claim_id"] = _claim_id(claim)
    claim["source_claim_ids"] = [claim["claim_id"]]
    return claim


def _card_metadata_by_id(
    card_metadata: dict[str, dict[str, Any]] | dict[str, Any] | list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
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


def _dedupe_claims(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for claim in claims:
        claim_id = str(claim["claim_id"])
        if claim_id in seen:
            continue
        seen.add(claim_id)
        deduped.append(claim)
    return deduped


def _legacy_claim_type(claim_kind: str) -> str:
    return {
        "mulligan_keep": "mulligan_keep",
        "mulligan_discard": "mulligan_discard",
        "card_role": "card_role",
        "discover_choice": "discover_choice",
        "choose_one_choice": "choose_one_choice",
        "targeting_rule": "targeting",
        "combo_sequence": "combo",
        "gameplan_posture": "gameplan_posture",
        "hero_power_transform": "hero_power_transform",
        "mechanic_usage": "mechanic_usage",
    }.get(claim_kind, "general")


def _claim_id(claim: dict[str, Any]) -> str:
    payload = {
        key: value
        for key, value in claim.items()
        if key not in {"claim_id", "source_claim_ids"}
    }
    canonical = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    return f"claim_{sha256(canonical.encode('utf-8')).hexdigest()[:12]}"


def _claim_counts_as_guide_backed(claim: dict[str, Any]) -> bool:
    readiness = str(claim.get("claim_readiness", "")).lower()
    if readiness:
        return readiness == "guide_backed"
    return (
        str(claim.get("support_status", "")).lower() == "source_backed"
        and str(claim.get("confidence", "guide_backed")).lower()
        in {"guide_backed", "source_backed"}
    )


def _claim_counts_as_static_semantics(claim: dict[str, Any]) -> bool:
    readiness = str(claim.get("claim_readiness", "")).lower()
    if readiness:
        return readiness == "source_backed_static_semantics"
    return (
        str(claim.get("source_family", "")) == "hearthstonejson_static_semantics"
        or str(claim.get("support_status", "")).lower() == "static_semantics"
        or str(claim.get("confidence", "")).lower() == "source_backed_static_semantics"
    )


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


def _normalize_optional(value: Any) -> Any:
    if isinstance(value, str):
        return _clean_text(value)
    if isinstance(value, list):
        return [_normalize_optional(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _normalize_optional(value[key]) for key in sorted(value)}
    return value


def _card_text(card: dict[str, Any]) -> str:
    parts = [str(card.get("text", ""))]
    mechanics = card.get("mechanics", [])
    if isinstance(mechanics, list):
        parts.extend(str(item) for item in mechanics)
    return " ".join(part for part in parts if part)


def _clean_text(value: Any) -> str:
    return " ".join(str(value).strip().split())

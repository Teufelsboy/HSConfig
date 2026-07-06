from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any


SUPPORTED_CLAIM_KINDS = {
    "mulligan_keep",
    "mulligan_discard",
    "card_role",
    "targeting_rule",
    "combo_sequence",
    "gameplan_posture",
    "hero_power_transform",
    "mechanic_usage",
}

MECHANIC_TEXT_MARKERS = {
    "battlecry": ("battlecry",),
    "deathrattle": ("deathrattle",),
    "discover": ("discover",),
    "dredge": ("dredge",),
    "tradeable": ("tradeable",),
    "overload": ("overload",),
    "freeze": ("freeze", "frozen"),
    "lifesteal": ("lifesteal",),
    "taunt": ("taunt",),
    "rush": ("rush",),
    "charge": ("charge",),
    "secret": ("secret",),
    "location": ("location",),
    "weapon": ("weapon", "equip"),
    "silence": ("silence",),
    "transform": ("transform",),
    "destroy": ("destroy",),
    "discard": ("discard",),
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
    guide_backed_cards: set[str] = set()

    for doc_index, document in enumerate(source_documents, start=1):
        source_ref = f"source:{doc_index}"
        raw_claims = document.get("claims", [])
        if not isinstance(raw_claims, list):
            unsupported_claims.append(
                {
                    "source_ref": source_ref,
                    "reason": "claims_not_list",
                    "source_url": document.get("source_url", ""),
                }
            )
            raw_claims = []
        promoted_count = 0
        for claim_index, raw_claim in enumerate(raw_claims, start=1):
            if not isinstance(raw_claim, dict):
                unsupported_claims.append(
                    {"source_ref": source_ref, "claim_index": claim_index, "reason": "claim_not_object"}
                )
                continue
            normalized, unsupported = _normalize_source_claim(
                raw_claim,
                document=document,
                source_ref=source_ref,
                claim_index=claim_index,
                known_card_ids=set(cards),
            )
            if unsupported is not None:
                unsupported_claims.append(unsupported)
                continue
            assert normalized is not None
            claims.append(normalized)
            guide_backed_cards.update(normalized["cards"])
            promoted_count += 1
        source_evidence_index.append(
            {
                "source_ref": source_ref,
                "source_url": str(document.get("source_url", "")),
                "source_title": str(document.get("source_title", "")),
                "source_family": str(document.get("source_family", "unknown")),
                "retrieved_at": str(document.get("retrieved_at", "")),
                "claim_count": promoted_count,
            }
        )

    static_claims = _static_semantic_claims(cards, existing_claims=claims)
    claims.extend(static_claims)
    claims = _dedupe_claims(claims)
    static_semantic_cards = {
        card
        for claim in claims
        if claim.get("source_family") == "hearthstonejson_static_semantics"
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
        claim["condition"] = _normalize_optional(raw_claim["condition"])
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
    claims = []
    for card_id, card in sorted(cards.items()):
        text = _card_text(card).lower()
        if (
            ("hero power becomes" in text or "enter shadowform" in text)
            and ("hero_power_transform", card_id) not in existing_kind_cards
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
        for mechanic, markers in MECHANIC_TEXT_MARKERS.items():
            if (mechanic == "transform" and "hero power becomes" in text) or not any(
                marker in text for marker in markers
            ):
                continue
            key = ("mechanic_usage", card_id, mechanic)
            if key in existing_pairs:
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
    return claims


def _static_claim(
    *,
    card_id: str,
    card: dict[str, Any],
    claim_kind: str,
    mechanic: str,
    stance: str,
) -> dict[str, Any]:
    evidence = _card_text(card)
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
        "evidence_text_short": evidence,
        "source_confidence": "medium",
        "claim_confidence": "medium",
        "confidence": "source_backed_static_semantics",
        "support_status": "static_semantics",
        "mechanic": mechanic,
        "source_refs": ["hearthstonejson_static_semantics"],
    }
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

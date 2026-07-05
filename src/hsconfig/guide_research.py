from __future__ import annotations

import hashlib
import json
from typing import Any


def normalize_source_claims(claims: list[dict[str, Any]]) -> dict[str, Any]:
    normalized_by_id: dict[str, dict[str, Any]] = {}
    for raw_claim in claims:
        claim = _normalize_claim(raw_claim)
        claim_id = _stable_claim_id(claim)
        claim["claim_id"] = claim_id
        normalized_by_id.setdefault(claim_id, claim)

    normalized = [normalized_by_id[claim_id] for claim_id in sorted(normalized_by_id)]
    return {"claims": normalized, "claim_count": len(normalized)}


def _normalize_claim(raw_claim: dict[str, Any]) -> dict[str, Any]:
    claim = {
        "source": _clean_text(raw_claim.get("source", "unknown")) or "unknown",
        "url": _clean_text(raw_claim.get("url", "")),
        "claim": _clean_text(raw_claim.get("claim", "")),
        "cards": _normalize_cards(raw_claim.get("cards", [])),
        "claim_type": _clean_text(raw_claim.get("claim_type", "general")) or "general",
        "confidence": _clean_text(raw_claim.get("confidence", "source_backed"))
        or "source_backed",
    }
    for optional_key in (
        "condition",
        "matchup",
        "operator",
        "patch",
        "policy",
        "retrieved_at",
        "source_title",
        "values",
    ):
        if optional_key in raw_claim:
            claim[optional_key] = _normalize_optional(raw_claim[optional_key])
    claim["source_refs"] = _source_refs(claim)
    return claim


def _stable_claim_id(claim: dict[str, Any]) -> str:
    payload = {
        key: value
        for key, value in claim.items()
        if key not in {"claim_id", "source_refs"}
    }
    canonical = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    return f"claim_{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:12]}"


def _normalize_cards(cards: Any) -> list[str]:
    if cards is None:
        return []
    if isinstance(cards, str):
        candidates = [cards]
    else:
        candidates = list(cards)
    normalized: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        card = _clean_text(candidate)
        if card and card not in seen:
            normalized.append(card)
            seen.add(card)
    return normalized


def _clean_text(value: Any) -> str:
    return " ".join(str(value).strip().split())


def _normalize_optional(value: Any) -> Any:
    if isinstance(value, str):
        return _clean_text(value)
    if isinstance(value, list):
        return [_normalize_optional(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _normalize_optional(value[key]) for key in sorted(value)}
    return value


def _source_refs(claim: dict[str, Any]) -> list[str]:
    refs = []
    if claim.get("url"):
        refs.append(str(claim["url"]))
    elif claim.get("source"):
        refs.append(str(claim["source"]))
    return refs

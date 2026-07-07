from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import Any

from hsconfig.source_freshness import is_stale_source


def build_deck_fingerprint(deck_identity: dict[str, Any], cards: list[dict[str, Any]]) -> dict[str, Any]:
    card_counts: dict[str, int] = {}
    for card in cards or deck_identity.get("cards", []):
        card_id = str(card.get("card_id", "")).strip()
        if not card_id:
            continue
        card_counts[card_id] = card_counts.get(card_id, 0) + int(card.get("count", 1))
    canonical = sorted(card_counts.items())
    digest = hashlib.sha256(
        json.dumps(canonical, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()
    return {
        "schema_version": 1,
        "deck_name": str(deck_identity.get("deck_name", "")),
        "deck_code_hash": str(deck_identity.get("deck_code_hash", "")),
        "deck_fingerprint": f"sha256:{digest}",
        "card_count": sum(card_counts.values()),
        "unique_card_count": len(card_counts),
        "cards": [{"card_id": card_id, "count": count} for card_id, count in canonical],
    }


def build_candidate_archetypes(
    *,
    deck_name: str,
    deck_identity: dict[str, Any],
    card_roles: dict[str, Any] | list[dict[str, Any]],
    source_documents: list[dict[str, Any]],
) -> dict[str, Any]:
    source_archetypes = Counter(
        str(document.get("archetype", "")).strip()
        for document in source_documents
        if str(document.get("archetype", "")).strip()
    )
    role_map = _role_map(card_roles)
    if source_archetypes:
        candidates = [
            {
                "archetype": archetype,
                "source_count": count,
                "confidence": "source_backed",
                "reason": "archetype_declared_by_source_documents",
            }
            for archetype, count in source_archetypes.most_common()
        ]
    else:
        inferred = _infer_archetype_from_roles(role_map)
        candidates = [
            {
                "archetype": inferred,
                "source_count": 0,
                "confidence": "static_semantics",
                "reason": "inferred_from_card_roles",
            }
        ]
    return {
        "schema_version": 1,
        "deck_name": deck_name,
        "deck_code_hash": str(deck_identity.get("deck_code_hash", "")),
        "primary_archetype": candidates[0]["archetype"],
        "candidates": candidates,
    }


def build_guide_sources(
    *,
    deck_name: str,
    deck_identity: dict[str, Any],
    card_roles: dict[str, Any] | list[dict[str, Any]],
    source_documents: list[dict[str, Any]],
    current_date: Any = None,
) -> dict[str, Any]:
    normalized_sources: list[dict[str, Any]] = []
    stale_count = 0
    downgraded_count = 0
    for index, document in enumerate(source_documents, start=1):
        warnings = _source_warnings(deck_name, document, current_date=current_date)
        stale_count += int(any(warning["reason"] == "stale_source" for warning in warnings))
        downgraded_count += int(bool(warnings))
        claims = [
            _normalize_claim(claim, source_index=index, claim_index=claim_index)
            for claim_index, claim in enumerate(document.get("claims", []) or [], start=1)
            if isinstance(claim, dict)
        ]
        normalized_sources.append(
            {
                "source_id": str(document.get("source_id", f"source_{index}")),
                "source_url": str(document.get("source_url", "")),
                "source_title": str(document.get("source_title", "")),
                "source_family": str(document.get("source_family", "guide")),
                "retrieved_at": str(document.get("retrieved_at", "")),
                "deck_name": str(document.get("deck_name", "")),
                "archetype": str(document.get("archetype", "")),
                "claims": claims,
                "warnings": warnings,
            }
        )
    source_depth_status = "static_semantics_only"
    claim_count = sum(len(source["claims"]) for source in normalized_sources)
    if normalized_sources and downgraded_count == 0 and claim_count > 0:
        source_depth_status = "source_backed"
    elif normalized_sources:
        source_depth_status = "needs_more_research"
    return {
        "schema_version": 1,
        "deck_name": deck_name,
        "deck_code_hash": str(deck_identity.get("deck_code_hash", "")),
        "source_depth_status": source_depth_status,
        "sources": normalized_sources,
        "summary": {
            "source_count": len(normalized_sources),
            "claim_count": claim_count,
            "stale_source_count": stale_count,
            "downgraded_source_count": downgraded_count,
            "static_card_semantics_used": not normalized_sources,
        },
    }


def build_guide_builder_receipt(
    *,
    deck_name: str,
    deck_identity: dict[str, Any],
    source_documents: list[dict[str, Any]],
    guide_sources: dict[str, Any],
) -> dict[str, Any]:
    summary = guide_sources.get("summary", {})
    return {
        "schema_version": 1,
        "deck_name": deck_name,
        "deck_code_hash": str(deck_identity.get("deck_code_hash", "")),
        "source_depth_status": str(guide_sources.get("source_depth_status", "")),
        "source_count": int(summary.get("source_count", len(source_documents))),
        "claim_count": int(summary.get("claim_count", 0)),
        "stale_source_count": int(summary.get("stale_source_count", 0)),
        "static_card_semantics_used": bool(summary.get("static_card_semantics_used", False)),
    }


def _normalize_claim(claim: dict[str, Any], *, source_index: int, claim_index: int) -> dict[str, Any]:
    normalized = dict(claim)
    if "reason" in normalized and "evidence_text_short" not in normalized:
        normalized["evidence_text_short"] = normalized["reason"]
    normalized.setdefault("confidence", normalized.get("claim_confidence", "source_backed"))
    normalized["claim_id"] = str(normalized.get("claim_id") or _claim_id(normalized, source_index, claim_index))
    normalized["source_claim_ids"] = [normalized["claim_id"]]
    return normalized


def _claim_id(claim: dict[str, Any], source_index: int, claim_index: int) -> str:
    payload = {
        "source_index": source_index,
        "claim_index": claim_index,
        "claim": claim,
    }
    digest = hashlib.sha256(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()[:12]
    return f"claim_{digest}"


def _source_warnings(
    deck_name: str,
    document: dict[str, Any],
    *,
    current_date: Any = None,
) -> list[dict[str, str]]:
    warnings: list[dict[str, str]] = []
    if _is_stale(document.get("retrieved_at"), current_date=current_date):
        warnings.append({"reason": "stale_source"})
    source_deck_name = str(document.get("deck_name", "")).strip()
    if source_deck_name and source_deck_name.lower() != deck_name.lower():
        warnings.append({"reason": "deck_name_mismatch"})
    return warnings


def _is_stale(value: Any, *, current_date: Any = None) -> bool:
    return is_stale_source(str(value or ""), current_date=current_date)


def _role_map(card_roles: dict[str, Any] | list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    if isinstance(card_roles, dict):
        return {
            str(card_id): dict(row)
            for card_id, row in card_roles.items()
            if isinstance(row, dict)
        }
    return {
        str(row.get("card_id")): dict(row)
        for row in card_roles
        if isinstance(row, dict) and row.get("card_id")
    }


def _infer_archetype_from_roles(role_map: dict[str, dict[str, Any]]) -> str:
    all_roles = {
        str(role)
        for row in role_map.values()
        for role in row.get("roles", [])
    }
    if {"burn_payoff", "hero_power_transform"} & all_roles:
        return "aggro_burn"
    if {"deathrattle", "recruit", "big_minion"} & all_roles:
        return "deathrattle_recruit"
    if "weapon" in all_roles:
        return "weapon_pressure"
    return "generic_low_confidence"

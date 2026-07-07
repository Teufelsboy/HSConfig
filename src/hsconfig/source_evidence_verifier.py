from __future__ import annotations

from ipaddress import ip_address
from typing import Any
from urllib.parse import urlsplit

from hsconfig.source_document_model import SUPPORTED_ATOMIC_CLAIM_KINDS
from hsconfig.visionai_registry import CARD_BEHAVIOR_BLOCKS


PUBLIC_URL_SCHEMES = {"https"}
RUNTIME_HINT_KEYS = {"runtime_block", "runtime_value"}


def source_ref_is_public_https(value: object) -> bool:
    text = str(value).strip()
    parsed = urlsplit(text)
    if parsed.scheme not in PUBLIC_URL_SCHEMES or not parsed.hostname:
        return False
    host = parsed.hostname.lower()
    if host == "localhost" or host.endswith(".localhost") or host.endswith(".local"):
        return False
    try:
        address = ip_address(host)
    except ValueError:
        return True
    return not (
        address.is_loopback
        or address.is_private
        or address.is_link_local
        or address.is_reserved
        or address.is_unspecified
    )


def verify_source_documents(source_documents: list[dict[str, Any]]) -> dict[str, Any]:
    warnings: list[dict[str, Any]] = []
    claim_rows: list[dict[str, Any]] = []
    claim_count = 0
    runtime_lowering_claims = 0

    for document_index, document in enumerate(source_documents, start=1):
        if not source_ref_is_public_https(document.get("source_url", "")):
            warnings.append(
                {
                    "reason": "source_url_not_public_https",
                    "document_index": document_index,
                    "source_url": str(document.get("source_url", "")),
                }
            )
        claims = document.get("claims", [])
        if not isinstance(claims, list) or not claims:
            warnings.append({"reason": "document_has_no_claims", "document_index": document_index})
            continue
        for claim_index, claim in enumerate(claims, start=1):
            claim_count += 1
            row = claim_evidence_status(claim, document)
            row["document_index"] = document_index
            row["claim_index"] = claim_index
            claim_rows.append(row)
            runtime_lowering_claims += int(row["has_runtime_lowering_hint"])
            warnings.extend(row["warnings"])

    return {
        "schema_version": 1,
        "status": "passed" if not warnings else "warnings",
        "summary": {
            "document_count": len(source_documents),
            "claim_count": claim_count,
            "runtime_lowering_claims": runtime_lowering_claims,
            "warnings_count": len(warnings),
        },
        "claims": claim_rows,
        "warnings": warnings,
    }


def claim_evidence_status(claim: dict[str, Any], document: dict[str, Any]) -> dict[str, Any]:
    warnings: list[dict[str, Any]] = []
    claim_kind = str(claim.get("claim_kind", claim.get("claim_type", "")))
    cards = _cards(claim)
    has_runtime_lowering_hint = any(key in claim for key in RUNTIME_HINT_KEYS)

    if claim_kind not in SUPPORTED_ATOMIC_CLAIM_KINDS:
        warnings.append({"reason": "unsupported_claim_kind", "claim_kind": claim_kind})
    if not cards and claim_kind not in {"archetype", "gameplan_posture"}:
        warnings.append({"reason": "claim_missing_cards", "claim_kind": claim_kind})
    if not str(claim.get("evidence_text_short", "")).strip():
        warnings.append({"reason": "claim_missing_evidence_text_short", "claim_kind": claim_kind})
    runtime_block = claim.get("runtime_block")
    if runtime_block is not None and str(runtime_block) not in CARD_BEHAVIOR_BLOCKS:
        warnings.append(
            {
                "reason": "unsupported_runtime_block",
                "claim_kind": claim_kind,
                "runtime_block": str(runtime_block),
            }
        )
    if has_runtime_lowering_hint and str(claim.get("source_confidence", "")).lower() == "low":
        warnings.append({"reason": "low_confidence_runtime_lowering", "claim_kind": claim_kind})

    return {
        "claim_kind": claim_kind,
        "cards": cards,
        "source_family": str(document.get("source_family", "")),
        "source_url": str(document.get("source_url", "")),
        "has_runtime_lowering_hint": has_runtime_lowering_hint,
        "status": "passed" if not warnings else "warnings",
        "warnings": warnings,
    }


def _cards(claim: dict[str, Any]) -> list[str]:
    cards = claim.get("cards", [])
    if isinstance(cards, str):
        cards = [cards]
    if not isinstance(cards, list):
        return []
    return [str(card) for card in cards if str(card)]

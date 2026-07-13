from __future__ import annotations

from ipaddress import ip_address
from typing import Any
from urllib.parse import urlsplit

from hsconfig.role_tokens import START_OF_GAME_NON_HAND_EFFECT_ROLES, claim_role_tokens
from hsconfig.source_document_model import SUPPORTED_ATOMIC_CLAIM_KINDS, runtime_claim_kind
from hsconfig.visionai_registry import CARD_BEHAVIOR_BLOCKS


PUBLIC_URL_SCHEMES = {"https"}
RUNTIME_HINT_KEYS = {"runtime_block", "runtime_value"}
SUPPORTED_SOURCE_FAMILIES = {
    "guide",
    "guide_fixture",
    "mulligan_guide",
    "matchup_guide",
    "card_text",
    "metadata",
    "hearthstonejson",
    "static_semantics",
}
ACTIONABLE_SPECIFICITY_KEYS = (
    "stance",
    "condition",
    "conditions",
    "runtime_value",
    "target",
    "target_name",
    "target_card_id",
    "role",
    "mechanic",
    "selector",
    "selector_kind",
    "sequence",
    "values",
    "timing_kind",
    "operator",
    "option_card_id",
)
OPENING_HAND_LANGUAGE = (
    "mulligan",
    "opening hand",
    "starting hand",
    "keep this",
    "always keep",
    "hard keep",
)
SUSPICIOUS_KEEP_ROLE_KEYS = (
    "roles",
    "semantic_families",
    "mechanic_families",
)


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
        source_title = _text(document.get("source_title", ""))
        if not source_title:
            warnings.append(
                {
                    "reason": "source_title_missing",
                    "document_index": document_index,
                }
            )
        source_family = _text(document.get("source_family", ""))
        if not source_family:
            warnings.append(
                {
                    "reason": "source_family_missing",
                    "document_index": document_index,
                }
            )
        elif source_family.lower() not in SUPPORTED_SOURCE_FAMILIES:
            warnings.append(
                {
                    "reason": "unsupported_source_family",
                    "document_index": document_index,
                    "source_family": source_family,
                }
            )
        if not _text(document.get("retrieved_at", "")):
            warnings.append(
                {
                    "reason": "retrieved_at_missing",
                    "document_index": document_index,
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
    claim_kind = runtime_claim_kind(claim) or str(claim.get("claim_kind", claim.get("claim_type", "")))
    cards = _cards(claim)
    has_runtime_lowering_hint = any(key in claim for key in RUNTIME_HINT_KEYS)

    if claim_kind not in SUPPORTED_ATOMIC_CLAIM_KINDS:
        warnings.append({"reason": "unsupported_claim_kind", "claim_kind": claim_kind})
    if not cards and claim_kind not in {
        "archetype",
        "gameplan_posture",
        "globalvalue_numeric_tuning",
    }:
        warnings.append({"reason": "claim_missing_cards", "claim_kind": claim_kind})
    if not _claim_evidence_text(claim):
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
    for source_ref in _source_refs(claim):
        if not source_ref_is_public_https(source_ref):
            warnings.append(
                {
                    "reason": "claim_source_ref_not_public_https",
                    "claim_kind": claim_kind,
                    "source_ref": source_ref,
                }
            )
    if has_runtime_lowering_hint and not _has_actionable_specificity(claim):
        warnings.append(
            {
                "reason": "runtime_lowering_claim_lacks_actionable_specificity",
                "claim_kind": claim_kind,
            }
        )
    suspicious_keep_warning = _suspicious_exact_keep_warning(claim, claim_kind)
    if suspicious_keep_warning is not None:
        warnings.append(suspicious_keep_warning)

    return {
        "claim_kind": claim_kind,
        "cards": cards,
        "source_family": str(document.get("source_family", "")),
        "source_url": str(document.get("source_url", "")),
        "has_runtime_lowering_hint": has_runtime_lowering_hint,
        "status": "passed" if not warnings else "warnings",
        "warnings": warnings,
    }


def _suspicious_exact_keep_warning(
    claim: dict[str, Any],
    claim_kind: str,
) -> dict[str, Any] | None:
    if claim_kind != "mulligan_keep":
        return None
    evidence = _claim_evidence_text(claim).lower()
    if _has_opening_hand_language(evidence):
        return None
    roles = _claim_role_hints(claim)
    if "start_of_game" in roles or roles & START_OF_GAME_NON_HAND_EFFECT_ROLES:
        return {
            "reason": "suspicious_mulligan_keep_non_hand_effect",
            "claim_kind": claim_kind,
            "roles": sorted(roles),
        }
    return None


def _has_opening_hand_language(evidence: str) -> bool:
    return any(term in evidence for term in OPENING_HAND_LANGUAGE)


def _claim_role_hints(claim: dict[str, Any]) -> set[str]:
    return claim_role_tokens(claim, keys=SUSPICIOUS_KEEP_ROLE_KEYS)


def _cards(claim: dict[str, Any]) -> list[str]:
    cards = claim.get("cards", [])
    if isinstance(cards, str):
        cards = [cards]
    if not isinstance(cards, list):
        return []
    return [str(card) for card in cards if str(card)]


def _claim_evidence_text(claim: dict[str, Any]) -> str:
    return str(claim.get("evidence_text_short", claim.get("claim", claim.get("reason", "")))).strip()


def _source_refs(claim: dict[str, Any]) -> list[str]:
    source_refs = claim.get("source_refs", [])
    if isinstance(source_refs, str):
        source_refs = [source_refs]
    if not isinstance(source_refs, list):
        return []
    return [_text(source_ref) for source_ref in source_refs if _text(source_ref)]


def _has_actionable_specificity(claim: dict[str, Any]) -> bool:
    for key in ACTIONABLE_SPECIFICITY_KEYS:
        value = claim.get(key)
        if _has_meaningful_value(value):
            return True
    return False


def _has_meaningful_value(value: object) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set)):
        return any(_has_meaningful_value(item) for item in value)
    if isinstance(value, dict):
        return any(_has_meaningful_value(item) for item in value.values())
    return value is not None


def _text(value: object) -> str:
    return str(value).strip()

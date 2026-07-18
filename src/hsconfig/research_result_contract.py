from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from hsconfig.source_document_model import (
    CARDID_SURFACE_CLAIM_KINDS,
    COMBO_SURFACE_CLAIM_KINDS,
    GLOBALVALUES_SURFACE_CLAIM_KINDS,
    MULLIGAN_SURFACE_CLAIM_KINDS,
)


STRONG_MARKERS = frozenset(
    {
        "SOURCE_BACKED_STRONG",
        "strong",
        "candidate_strong",
    }
)
SEED_STRENGTHS = frozenset(
    {
        "candidate_url_only",
        "decklist_only",
        "stats_only",
        "unfetched_acquisition_seed",
    }
)
RUNTIME_LOWERABLE_CLAIM_KINDS = frozenset().union(
    MULLIGAN_SURFACE_CLAIM_KINDS,
    GLOBALVALUES_SURFACE_CLAIM_KINDS,
    COMBO_SURFACE_CLAIM_KINDS,
    CARDID_SURFACE_CLAIM_KINDS,
)


def classify_research_result_contract(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Classify a research snapshot without granting it apply authority."""
    lowerable_claim_kinds = _lowerable_claim_kinds(payload)
    errors: list[str] = []
    warnings: list[str] = []
    if not _has_deck_name(payload):
        errors.append("missing_deck_identity")
        return _result(
            contract_valid=False,
            snapshot_kind="invalid",
            errors=errors,
            warnings=warnings,
            lowerable_claim_kinds=lowerable_claim_kinds,
        )

    strengths = _source_strengths(payload)
    if any(strength in SEED_STRENGTHS for strength in strengths):
        return _result(
            contract_valid=True,
            snapshot_kind="seed_only",
            errors=errors,
            warnings=warnings,
            lowerable_claim_kinds=lowerable_claim_kinds,
        )

    if not _has_exact_deck_identity(payload):
        errors.append("missing_deck_identity")
        return _result(
            contract_valid=False,
            snapshot_kind="invalid",
            errors=errors,
            warnings=warnings,
            lowerable_claim_kinds=lowerable_claim_kinds,
        )

    strong = any(strength in STRONG_MARKERS for strength in strengths)
    has_full_text_evidence = _has_full_text_or_canonical_evidence(payload)
    has_default_only_runtime_surfaces = _has_default_only_runtime_surfaces(payload)
    if strong and not lowerable_claim_kinds:
        warnings.append("no_lowerable_claim_kinds")
    if strong and not has_full_text_evidence:
        warnings.append("missing_full_text_or_canonical_evidence")
    if strong and str(payload.get("first_missing_source_action") or "") != "none":
        warnings.append("first_missing_source_action_not_none")
    if strong and has_default_only_runtime_surfaces:
        warnings.append("default_only_runtime_surfaces_present")

    promotion_allowed = bool(
        strong
        and str(payload.get("first_missing_source_action") or "") == "none"
        and lowerable_claim_kinds
        and has_full_text_evidence
        and not has_default_only_runtime_surfaces
    )
    return _result(
        contract_valid=True,
        snapshot_kind="strong" if promotion_allowed else "partial",
        canonical_promotion_allowed=promotion_allowed,
        errors=errors,
        warnings=warnings,
        lowerable_claim_kinds=lowerable_claim_kinds,
    )


def _result(
    *,
    contract_valid: bool,
    snapshot_kind: str,
    errors: list[str],
    warnings: list[str],
    lowerable_claim_kinds: list[str],
    canonical_promotion_allowed: bool = False,
) -> dict[str, Any]:
    return {
        "contract_valid": contract_valid,
        "snapshot_kind": snapshot_kind,
        "canonical_promotion_allowed": canonical_promotion_allowed,
        "canonical_downgrade_allowed": False,
        "source_status_apply_blocking": False,
        "errors": errors,
        "warnings": warnings,
        "lowerable_claim_kinds": lowerable_claim_kinds,
    }


def _has_deck_name(payload: Mapping[str, Any]) -> bool:
    return bool(str(payload.get("deck_name") or "").strip())


def _has_exact_deck_identity(payload: Mapping[str, Any]) -> bool:
    return bool(
        str(payload.get("deck_code") or "").strip()
        or str(payload.get("source_row_identity") or "").strip()
    )


def _source_strengths(payload: Mapping[str, Any]) -> set[str]:
    return {
        str(payload.get(field) or "").strip()
        for field in (
            "source_backed_status",
            "source_status",
            "source_strength",
            "source_record_strength",
        )
    }


def _lowerable_claim_kinds(payload: Mapping[str, Any]) -> list[str]:
    values = payload.get("lowerable_claim_kinds") or []
    if not isinstance(values, list):
        return []
    return sorted(
        {
            value.strip()
            for value in values
            if isinstance(value, str)
            and value.strip() in RUNTIME_LOWERABLE_CLAIM_KINDS
        }
    )


def _has_default_only_runtime_surfaces(payload: Mapping[str, Any]) -> bool:
    surfaces = payload.get("default_only_runtime_surfaces") or []
    if isinstance(surfaces, list) and any(str(value).strip() for value in surfaces):
        return True

    records = payload.get("records")
    return isinstance(records, list) and any(
        isinstance(record, Mapping)
        and _has_default_only_runtime_surfaces(record)
        for record in records
    )


def _has_full_text_or_canonical_evidence(payload: Mapping[str, Any]) -> bool:
    if payload.get("canonical_evidence") is True:
        return True
    if str(payload.get("source_visibility") or "").strip().lower() == "full_text":
        return True
    records = payload.get("records")
    return isinstance(records, list) and any(
        isinstance(record, Mapping)
        and (
            str(record.get("source_visibility") or "").strip().lower() == "full_text"
            or record.get("canonical_evidence") is True
        )
        for record in records
    )

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from hsconfig.research_result_contract import RUNTIME_LOWERABLE_CLAIM_KINDS

REQUIRED_RESULT_FIELDS = {
    "deck_name",
    "archetype",
    "current_deck_sources",
    "guide_sources",
    "source_strength",
    "lowerable_claim_kinds",
    "non_promoting_support",
    "first_missing_source_action",
    "notes",
}
ALLOWED_SOURCE_STRENGTHS = {
    "SOURCE_BACKED_STRONG",
    "archetype_full_text_guide",
    "decklist_or_stats_only",
    "exact_full_text_guide",
    "missing",
    "snippet_only",
    "static_semantics_only",
    "unfetched_acquisition_seed",
}
STRONG_STRENGTHS = {
    "SOURCE_BACKED_STRONG",
    "archetype_full_text_guide",
    "exact_full_text_guide",
}


def validate_research_result_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    missing = sorted(REQUIRED_RESULT_FIELDS - set(payload))
    errors.extend(f"missing_field:{field}" for field in missing)

    source_strength = str(payload.get("source_strength") or "")
    if source_strength not in ALLOWED_SOURCE_STRENGTHS:
        errors.append("invalid_source_strength")

    errors.extend(_list_field_errors(payload))

    lowerable_claim_kinds = [
        str(kind)
        for kind in payload.get("lowerable_claim_kinds", [])
        if str(kind) in RUNTIME_LOWERABLE_CLAIM_KINDS
    ]
    if source_strength in STRONG_STRENGTHS and not lowerable_claim_kinds:
        errors.append("strong_requires_lowerable_claim_kinds")
    if source_strength in STRONG_STRENGTHS:
        if str(payload.get("source_visibility") or "") != "full_text":
            errors.append("strong_requires_full_text_visibility")
        if str(payload.get("first_missing_source_action") or "") != "none":
            errors.append("strong_requires_first_missing_source_action_none")
        freshness = str(payload.get("freshness_status") or "")
        if freshness not in {"current", "evergreen"}:
            errors.append("strong_requires_current_or_evergreen_freshness")
    if (
        source_strength in {"decklist_or_stats_only", "unfetched_acquisition_seed"}
        and str(payload.get("first_missing_source_action") or "") == "none"
    ):
        warnings.append("seed_only_snapshot_should_name_next_source_action")

    return {
        "schema_version": 1,
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "source_status_apply_blocking": False,
        "field_count": len(
            [field for field in REQUIRED_RESULT_FIELDS if field in payload]
        ),
        "lowerable_claim_kinds": sorted(set(lowerable_claim_kinds)),
    }


def validate_fields_yaml_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    fields = payload.get("fields")
    if not isinstance(fields, Mapping):
        fields = {}
        errors.append("fields_must_be_mapping")
    missing = sorted(REQUIRED_RESULT_FIELDS - set(fields))
    errors.extend(f"missing_field_definition:{field}" for field in missing)
    return {
        "schema_version": 1,
        "valid": not errors,
        "errors": errors,
        "warnings": [],
        "field_count": len(fields),
        "required_fields": sorted(REQUIRED_RESULT_FIELDS),
        "source_status_apply_blocking": False,
    }


def _list_field_errors(payload: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    for field in (
        "current_deck_sources",
        "guide_sources",
        "lowerable_claim_kinds",
        "non_promoting_support",
    ):
        if field in payload and not isinstance(payload[field], list):
            errors.append(f"{field}_must_be_list")
    return errors

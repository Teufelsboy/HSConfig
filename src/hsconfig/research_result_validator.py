from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from hsconfig.default_only_runtime_surfaces import (
    default_only_runtime_surface_errors,
    has_default_only_runtime_surfaces,
)
from hsconfig.research_result_contract import RUNTIME_LOWERABLE_CLAIM_KINDS
from hsconfig.source_provenance import research_payload_provenance

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
    errors.extend(default_only_runtime_surface_errors(payload))
    errors.extend(_source_contract_status_field_errors(payload))

    raw_lowerable_claim_kinds = payload.get("lowerable_claim_kinds", [])
    lowerable_claim_kinds = [
        str(kind)
        for kind in (
            raw_lowerable_claim_kinds
            if isinstance(raw_lowerable_claim_kinds, list)
            else []
        )
        if str(kind) in RUNTIME_LOWERABLE_CLAIM_KINDS
    ]
    provenance = research_payload_provenance(payload)
    if source_strength in STRONG_STRENGTHS and not lowerable_claim_kinds:
        errors.append("strong_requires_lowerable_claim_kinds")
    if source_strength in STRONG_STRENGTHS:
        if str(payload.get("source_visibility") or "") != "full_text":
            errors.append("strong_requires_full_text_visibility")
        if str(payload.get("first_missing_source_action") or "") != "none":
            errors.append("strong_requires_first_missing_source_action_none")
        if not provenance["current_or_evergreen"]:
            errors.append("strong_requires_current_or_evergreen_freshness")
        if "default_only_runtime_surfaces" not in payload:
            errors.append("strong_requires_explicit_empty_default_only_runtime_surfaces")
        elif (
            payload["default_only_runtime_surfaces"] != []
            or has_default_only_runtime_surfaces(payload)
        ):
            errors.append("strong_requires_no_default_only_runtime_surfaces")
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
        "freshness_status": provenance["freshness_status"],
        "current_or_evergreen": provenance["current_or_evergreen"],
        "current_or_evergreen_reason": provenance["current_or_evergreen_reason"],
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


def _source_contract_status_field_errors(payload: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if (
        "source_status_apply_blocking_expected" in payload
        and not isinstance(payload["source_status_apply_blocking_expected"], bool)
    ):
        errors.append("source_status_apply_blocking_expected_must_be_boolean")
    if "default_only_runtime_surfaces_expected" in payload:
        value = payload["default_only_runtime_surfaces_expected"]
        if not isinstance(value, str) or not value.strip():
            errors.append("default_only_runtime_surfaces_expected_must_name_status")
    return errors

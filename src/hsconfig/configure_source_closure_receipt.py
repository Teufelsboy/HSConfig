from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from hsconfig.source_contract_matrix import source_contract_policy_by_claim_kind


NO_MISSING_SOURCE_ACTION = "none"
OPERATOR_GATE = "reports/operator_summary.json"


def build_configure_source_closure_receipt(
    *,
    operator_summary: Mapping[str, Any],
    acceptance_summary: Mapping[str, Any],
    guide_claim_bundle: Mapping[str, Any] | None,
    source_documents_payload: Mapping[str, Any] | None,
    source_candidate_urls: Sequence[str],
    source_urls: Sequence[str],
    source_closure_intake_receipt: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Return a compact diagnostic-only source closure receipt for configure."""

    normal_apply_authority = _normal_apply_authority(
        operator_summary,
        acceptance_summary,
    )
    default_only_runtime_surfaces = _string_list(
        operator_summary.get("default_only_runtime_surfaces")
    )
    first_missing_source_action = str(
        operator_summary.get("first_missing_source_action")
        or acceptance_summary.get("first_missing_source_action")
        or NO_MISSING_SOURCE_ACTION
    )
    source_backed_status = str(
        operator_summary.get("source_backed_status")
        or acceptance_summary.get("source_strength")
        or ""
    )
    source_status_apply_blocking = bool(
        operator_summary.get("source_status_apply_blocking", False)
    )
    source_status_reasons = _string_list(operator_summary.get("source_status_reasons"))
    source_intake = source_closure_intake_receipt or {}
    claims = _claim_rows(guide_claim_bundle, source_documents_payload)
    claim_kind_counts = Counter(
        str(claim.get("claim_kind") or "")
        for claim in claims
        if str(claim.get("claim_kind") or "")
    )
    lowerable_claim_kinds = _runtime_lowerable_claim_kinds()
    lowerable_claim_count = sum(
        1
        for claim in claims
        if str(claim.get("claim_kind") or "") in lowerable_claim_kinds
    )
    lowerable_claim_kind_count = len(
        {
            str(claim.get("claim_kind") or "")
            for claim in claims
            if str(claim.get("claim_kind") or "") in lowerable_claim_kinds
        }
    )
    source_documents_count = _source_documents_count(source_documents_payload)
    fetched_record_count = _int_value(source_intake.get("fetched_record_count"))
    source_strong_ready = (
        bool(operator_summary.get("source_strong_ready", False))
        and not source_status_apply_blocking
        and not default_only_runtime_surfaces
        and first_missing_source_action == NO_MISSING_SOURCE_ACTION
    )
    next_report_to_open = _next_report_to_open(
        first_missing_source_action=first_missing_source_action,
        default_only_runtime_surfaces=default_only_runtime_surfaces,
        acceptance_summary=acceptance_summary,
    )

    return {
        "schema_version": 1,
        "authority": "diagnostic_only",
        "classification": "diagnostic",
        "apply_blocking": False,
        "runtime_write_performed": False,
        "operator_gate": OPERATOR_GATE,
        "normal_apply_authority": normal_apply_authority,
        "use_config_now": bool(acceptance_summary.get("use_config_now", False)),
        "technical_status": str(operator_summary.get("technical_status") or ""),
        "runtime_apply_allowed": bool(
            operator_summary.get("runtime_apply_allowed", False)
        ),
        "runtime_apply_mode": str(operator_summary.get("runtime_apply_mode") or ""),
        "source_backed_status": source_backed_status,
        "source_strong_ready": source_strong_ready,
        "source_status_diagnostic_only": bool(
            operator_summary.get("source_status_diagnostic_only", True)
        ),
        "source_status_apply_blocking": source_status_apply_blocking,
        "source_status_reasons": source_status_reasons,
        "first_missing_source_action": first_missing_source_action,
        "source_closure_lane": _source_closure_lane(
            source_strong_ready=source_strong_ready,
            default_only_runtime_surfaces=default_only_runtime_surfaces,
            first_missing_source_action=first_missing_source_action,
            source_url_count=len(_string_list(source_urls)),
            fetched_record_count=fetched_record_count,
            source_documents_count=source_documents_count,
            lowerable_claim_count=lowerable_claim_count,
        ),
        "default_only_clean": not default_only_runtime_surfaces,
        "default_only_runtime_surfaces": default_only_runtime_surfaces,
        "source_candidate_url_count": len(_string_list(source_candidate_urls)),
        "source_url_count": len(_string_list(source_urls)),
        "source_intake_candidate_count": _int_value(source_intake.get("candidate_count")),
        "source_intake_promotion_eligible_seed_count": _int_value(
            source_intake.get("promotion_eligible_seed_count")
        ),
        "fetched_record_count": fetched_record_count,
        "source_documents_count": source_documents_count,
        "compiled_claim_count": len(claims),
        "compiled_claim_kind_counts": dict(sorted(claim_kind_counts.items())),
        "runtime_lowerable_claim_count": lowerable_claim_count,
        "runtime_lowerable_claim_kind_count": lowerable_claim_kind_count,
        "next_report_to_open": next_report_to_open,
    }


def _normal_apply_authority(
    operator_summary: Mapping[str, Any],
    acceptance_summary: Mapping[str, Any],
) -> str:
    runtime_contract = operator_summary.get("runtime_apply_contract")
    if isinstance(runtime_contract, Mapping):
        authority = str(runtime_contract.get("apply_authority") or "")
        if authority:
            return authority
    authority = str(acceptance_summary.get("normal_apply_authority") or "")
    return authority or OPERATOR_GATE


def _claim_rows(
    guide_claim_bundle: Mapping[str, Any] | None,
    source_documents_payload: Mapping[str, Any] | None,
) -> list[Mapping[str, Any]]:
    bundle_claims = _list_of_mappings(
        guide_claim_bundle.get("claims") if isinstance(guide_claim_bundle, Mapping) else []
    )
    if bundle_claims:
        return bundle_claims

    result: list[Mapping[str, Any]] = []
    for document in _source_documents(source_documents_payload):
        result.extend(_list_of_mappings(document.get("claims")))
    return result


def _source_documents_count(payload: Mapping[str, Any] | None) -> int:
    return len(_source_documents(payload))


def _source_documents(payload: Mapping[str, Any] | None) -> list[Mapping[str, Any]]:
    if not isinstance(payload, Mapping):
        return []
    return _list_of_mappings(payload.get("source_documents"))


def _runtime_lowerable_claim_kinds() -> set[str]:
    return {
        claim_kind
        for claim_kind, policy in source_contract_policy_by_claim_kind().items()
        if bool(policy.get("runtime_lowerable", False))
    }


def _source_closure_lane(
    *,
    source_strong_ready: bool,
    default_only_runtime_surfaces: Sequence[str],
    first_missing_source_action: str,
    source_url_count: int,
    fetched_record_count: int,
    source_documents_count: int,
    lowerable_claim_count: int,
) -> str:
    if source_strong_ready:
        return "strong"
    if default_only_runtime_surfaces:
        return "default_only_runtime_surface"
    if source_url_count and fetched_record_count == 0:
        return "fetch_needed"
    if fetched_record_count and source_documents_count == 0:
        return "claim_normalization_needed"
    if lowerable_claim_count == 0:
        return "runtime_lowerable_claim_needed"
    if first_missing_source_action in {
        "add_explicit_mulligan_source",
        "build_source_or_policy_backed_mulligan",
    }:
        return "mulligan_claim_needed"
    if first_missing_source_action in {
        "add_runtime_lowerable_claim_or_router_support",
        "add_runtime_source_claim",
        "replace_default_only_runtime_surface_with_source_or_policy_claim",
    }:
        return "runtime_surface_needed"
    if first_missing_source_action == NO_MISSING_SOURCE_ACTION:
        return "closed_without_strong"
    return "source_action_needed"


def _next_report_to_open(
    *,
    first_missing_source_action: str,
    default_only_runtime_surfaces: Sequence[str],
    acceptance_summary: Mapping[str, Any],
) -> str:
    if default_only_runtime_surfaces:
        return "reports/contract_doctor.json"
    if first_missing_source_action != NO_MISSING_SOURCE_ACTION:
        return "reports/source_to_runtime_explainability.json"
    return str(acceptance_summary.get("next_report_to_open") or OPERATOR_GATE)


def _list_of_mappings(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value else []
    if not isinstance(value, Sequence):
        return []
    return [str(item) for item in value if str(item)]


def _int_value(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0

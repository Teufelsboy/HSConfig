from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from hsconfig.source_status_resolver import resolve_source_status


def build_source_evidence_closure_report(
    *,
    deck_name: str,
    deck_code: str,
    operator_summary: Mapping[str, Any],
    source_to_runtime_explainability_report: Mapping[str, Any],
    source_claim_gap_report: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a compact diagnostic-only source evidence closure report."""

    source_to_runtime_summary = _mapping(
        source_to_runtime_explainability_report.get("summary")
    )
    explainability_summary = _mapping(
        operator_summary.get("source_to_runtime_explainability_summary")
    )
    closure_summary = _mapping(operator_summary.get("source_evidence_closure_summary"))
    strong_closure = _mapping(operator_summary.get("source_backed_strong_closure"))
    source_status_resolution = resolve_source_status(
        technical_status=str(operator_summary.get("technical_status") or ""),
        semantic_status=str(operator_summary.get("semantic_status") or ""),
        next_action=str(operator_summary.get("next_action") or ""),
        semantic_blockers=_list(operator_summary.get("semantic_blockers")),
        default_only_runtime_surfaces=[
            str(surface)
            for surface in _list(operator_summary.get("default_only_runtime_surfaces"))
            if str(surface)
        ],
        source_claim_gap_report=source_claim_gap_report,
        closure_profile_closed=_closure_profile_closed(strong_closure),
        closure_profile_first_missing_link=str(
            strong_closure.get("closure_profile_first_missing_link") or ""
        ),
    )
    return {
        "schema_version": 1,
        "authority": "diagnostic_only",
        "classification": "diagnostic",
        "apply_blocking": False,
        "operator_gate": "reports/operator_summary.json",
        "normal_apply_authority": "reports/operator_summary.json",
        **_pre_run_projection(operator_summary),
        "deck_name": deck_name,
        "deck_code": deck_code,
        "technical_status": operator_summary.get("technical_status"),
        "semantic_status": operator_summary.get("semantic_status"),
        "source_backed_status": source_status_resolution.source_backed_status,
        "source_strong_ready": source_status_resolution.strong_ready,
        "first_missing_source_action": (
            source_status_resolution.first_missing_source_action
        ),
        "source_missing_source_actions": list(
            source_status_resolution.missing_source_actions
        ),
        "source_status_reasons": list(source_status_resolution.reasons),
        "source_status_diagnostic_only": source_status_resolution.diagnostic_only,
        "source_status_apply_blocking": source_status_resolution.apply_blocking,
        "runtime_apply_allowed": operator_summary.get("runtime_apply_allowed"),
        "runtime_apply_mode": operator_summary.get("runtime_apply_mode"),
        "default_only_runtime_surfaces": _list(
            operator_summary.get("default_only_runtime_surfaces")
        ),
        "default_only_runtime_surface_details": _list(
            operator_summary.get("default_only_runtime_surface_details")
        ),
        "source_to_runtime_summary": dict(source_to_runtime_summary),
        "source_to_runtime_explainability_summary": dict(explainability_summary),
        "source_evidence_closure_summary": dict(closure_summary),
        "closure_profile": strong_closure.get("closure_profile", "unknown"),
        "closure_profile_closed": bool(
            strong_closure.get("closure_profile_closed", False)
        ),
        "closure_profile_first_missing_link": strong_closure.get(
            "closure_profile_first_missing_link",
            "unknown",
        ),
        "first_missing_source_action_counts": dict(
            _mapping(closure_summary.get("first_missing_source_action_counts"))
        ),
        "next_report_to_open": _next_report(
            closure_summary,
            explainability_summary,
            source_to_runtime_summary,
        ),
    }


def _pre_run_projection(
    operator_summary: Mapping[str, Any],
) -> dict[str, Any]:
    status = operator_summary.get("pre_run_contract_status")
    strategy = operator_summary.get("strategy_authority_status")
    if status not in {"complete", "incomplete"}:
        return {}
    if strategy not in {"partial", "strong"}:
        raise ValueError("strategy_authority_status_invalid")
    return {
        "hsconfig_scope": "PRE_RUN_CONTRACT",
        "gameplay_strategy_owner": "hearthranger_bot",
        "gameplay_quality": "OUT_OF_SCOPE_ASSUMED_EXTERNAL",
        "bot_gameplay_assumption": "trusted_external",
        "pre_run_contract_status": status,
        "strategy_authority_status": strategy,
        "pre_run_contract_diagnostic_only": True,
        "pre_run_contract_apply_blocking": False,
    }


def _next_report(*summaries: Mapping[str, Any]) -> str:
    for summary in summaries:
        value = summary.get("next_report_to_open")
        if isinstance(value, str) and value:
            return value
    return "reports/source_to_runtime_explainability.json"


def _closure_profile_closed(strong_closure: Mapping[str, Any]) -> bool:
    if not strong_closure:
        return False
    if strong_closure.get("closure_profile_apply_blocking") is True:
        return False
    if "closure_profile_closed" in strong_closure:
        return bool(strong_closure.get("closure_profile_closed"))
    return False


def _mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}


def _list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return list(value)
    return []

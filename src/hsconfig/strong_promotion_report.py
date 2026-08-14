from __future__ import annotations

from typing import Any

from hsconfig.source_status_resolver import (
    first_missing_chain_from_report,
    resolve_source_status,
)
from hsconfig.visionai_registry import FORBIDDEN_RUNTIME_SURFACES


def build_strong_promotion_report(
    *,
    deck_name: str,
    fixture_stage: str,
    operator_summary: dict[str, Any],
    source_claim_gap_report: dict[str, Any],
) -> dict[str, Any]:
    semantic_blockers = [
        *list(operator_summary.get("semantic_blockers", [])),
        *_default_only_runtime_surface_blockers(operator_summary),
        *_normal_path_surface_blockers(operator_summary),
    ]
    default_only_runtime_surfaces = _default_only_runtime_surfaces(operator_summary)
    first_missing_chain = first_missing_chain_from_report(source_claim_gap_report)
    source_status_resolution = resolve_source_status(
        technical_status=str(operator_summary.get("technical_status") or ""),
        semantic_status=str(operator_summary.get("semantic_status") or ""),
        next_action=str(operator_summary.get("next_action") or ""),
        semantic_blockers=semantic_blockers,
        default_only_runtime_surfaces=default_only_runtime_surfaces,
        source_claim_gap_report=source_claim_gap_report,
        closure_profile_closed=_closure_profile_closed(operator_summary),
        closure_profile_first_missing_link=_closure_profile_first_missing_link(
            operator_summary
        ),
    )
    promotion_ready = source_status_resolution.strong_ready
    operator_next_action = str(operator_summary.get("next_action", ""))
    first_missing_source_action = source_status_resolution.first_missing_source_action
    return {
        "schema_version": 1,
        "deck_name": deck_name,
        "fixture_stage": fixture_stage,
        "promotion_ready": promotion_ready,
        "source_backed_status": source_status_resolution.source_backed_status,
        "source_strong_ready": source_status_resolution.strong_ready,
        "source_missing_source_actions": list(
            source_status_resolution.missing_source_actions
        ),
        "source_status_reasons": list(source_status_resolution.reasons),
        "source_status_diagnostic_only": source_status_resolution.diagnostic_only,
        "source_status_apply_blocking": source_status_resolution.apply_blocking,
        "default_only_runtime_surfaces": default_only_runtime_surfaces,
        "verdict": "SOURCE_BACKED_STRONG_CONFIRMED" if promotion_ready else "PROMOTION_BLOCKED",
        "static_contract_status": source_status_resolution.source_backed_status,
        "runtime_lowering_status": _runtime_lowering_status(
            promotion_ready=promotion_ready,
            operator_summary=operator_summary,
        ),
        "first_missing_source_action": first_missing_source_action,
        "source_informed_apply_readiness": operator_summary.get(
            "source_informed_apply_readiness",
            {"status": "not_applicable"},
        ),
        "next_action": _report_next_action(
            promotion_ready=promotion_ready,
            operator_summary=operator_summary,
            first_missing_chain=first_missing_chain,
        ),
        "operator_status": {
            "technical_status": operator_summary.get("technical_status"),
            "semantic_status": operator_summary.get("semantic_status"),
            "operator_next_action": operator_next_action,
        },
        "semantic_blockers": semantic_blockers,
        "first_missing_chain": first_missing_chain,
    }


def _default_only_runtime_surfaces(operator_summary: dict[str, Any]) -> list[str]:
    surfaces = operator_summary.get("default_only_runtime_surfaces", [])
    if not isinstance(surfaces, list):
        return []
    return [str(surface) for surface in surfaces if str(surface)]


def _closure_profile_closed(operator_summary: dict[str, Any]) -> bool:
    strong_closure = operator_summary.get("source_backed_strong_closure")
    if not isinstance(strong_closure, dict):
        return True
    if strong_closure.get("closure_profile_apply_blocking") is True:
        return False
    if "closure_profile_closed" in strong_closure:
        return bool(strong_closure.get("closure_profile_closed"))
    return True


def _closure_profile_first_missing_link(operator_summary: dict[str, Any]) -> str:
    strong_closure = operator_summary.get("source_backed_strong_closure")
    if not isinstance(strong_closure, dict):
        return ""
    return str(strong_closure.get("closure_profile_first_missing_link") or "")


def _runtime_lowering_status(
    *,
    promotion_ready: bool,
    operator_summary: dict[str, Any],
) -> str:
    if promotion_ready:
        return "NO_DEFAULT_ONLY_RUNTIME_SURFACES"
    if operator_summary.get("technical_status") != "VALID_PACKAGE":
        return "NOT_LOAD_SAFE"
    return "LOAD_SAFE_WITH_POLICY_OR_REVIEW_ROWS"


def _normal_path_surface_blockers(operator_summary: dict[str, Any]) -> list[dict[str, str]]:
    generated_files = operator_summary.get("generated_files", [])
    if not isinstance(generated_files, list):
        return []
    blockers: list[dict[str, str]] = []
    for path in generated_files:
        normalized_path = str(path).replace("\\", "/")
        filename = normalized_path.rsplit("/", 1)[-1]
        if filename not in FORBIDDEN_RUNTIME_SURFACES:
            continue
        blockers.append(
            {
                "reason": "normal_path_optional_surface_present",
                "generated_file": normalized_path,
            }
        )
    return blockers


def _default_only_runtime_surface_blockers(
    operator_summary: dict[str, Any],
) -> list[dict[str, str]]:
    surfaces = operator_summary.get("default_only_runtime_surfaces", [])
    if not isinstance(surfaces, list):
        return []
    existing_blocked_surfaces = {
        str(row.get("surface"))
        for row in operator_summary.get("semantic_blockers", [])
        if isinstance(row, dict)
        and str(row.get("reason") or row.get("code"))
        == "default_only_surface_not_strong_evidence"
    }
    blockers: list[dict[str, str]] = []
    for surface in sorted(str(item) for item in surfaces if str(item)):
        if surface in existing_blocked_surfaces:
            continue
        blockers.append(
            {
                "reason": "default_only_surface_not_strong_evidence",
                "surface": surface,
            }
        )
    return blockers


def _report_next_action(
    *,
    promotion_ready: bool,
    operator_summary: dict[str, Any],
    first_missing_chain: dict[str, Any] | None,
) -> str:
    if promotion_ready:
        return "fixture_can_be_core_source_backed"
    if operator_summary.get("technical_status") != "VALID_PACKAGE":
        return str(operator_summary.get("next_action", ""))
    readiness = operator_summary.get("source_informed_apply_readiness")
    if (
        operator_summary.get("semantic_status") != "SOURCE_BACKED_STRONG"
        and isinstance(readiness, dict)
        and readiness.get("status") == "ready"
    ):
        return "source_informed_apply_ready_but_not_strong"
    return "close_first_missing_chain"

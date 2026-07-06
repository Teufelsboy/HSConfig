from __future__ import annotations

import hashlib
from typing import Any


VALID_STATUSES = {"passed", "pass", "valid", "ok", "success"}


def build_operator_summary(
    *,
    deck_name: str,
    deck_code: str,
    technical_validation: dict[str, Any],
    guide_source_depth: dict[str, Any] | None,
    unsupported_conditions: list[dict[str, Any]] | None,
    globalvalue_authority: dict[str, Any] | None,
    generated_files: list[str],
) -> dict[str, Any]:
    technical_status = _technical_status(technical_validation)
    semantic_status = _semantic_status(guide_source_depth)
    primary_blockers = _primary_blockers(technical_validation, technical_status)
    warnings = _warnings(
        guide_source_depth=guide_source_depth,
        semantic_status=semantic_status,
        unsupported_conditions=unsupported_conditions or [],
        globalvalue_authority=globalvalue_authority or {},
    )
    next_action, apply_policy = _next_action_and_policy(
        technical_status=technical_status,
        semantic_status=semantic_status,
        primary_blockers=primary_blockers,
    )
    return {
        "schema_version": 1,
        "deck": {
            "name": deck_name,
            "deck_code_hash": f"sha256:{hashlib.sha256(deck_code.encode('utf-8')).hexdigest()}",
        },
        "technical_status": technical_status,
        "semantic_status": semantic_status,
        "next_action": next_action,
        "apply_policy": apply_policy,
        "primary_blockers": primary_blockers,
        "warnings": warnings,
        "generated_files": sorted(str(path) for path in generated_files),
    }


def _technical_status(report: dict[str, Any]) -> str:
    status = str(report.get("status", "")).lower()
    return "VALID_PACKAGE" if status in VALID_STATUSES else "INVALID_PACKAGE"


def _semantic_status(guide_source_depth: dict[str, Any] | None) -> str:
    if not guide_source_depth:
        return "NEEDS_MORE_RESEARCH"
    if (
        str(guide_source_depth.get("source_depth_status", "")).lower() == "source_backed"
        and int(guide_source_depth.get("claim_count", 0) or 0) <= 0
    ):
        return "NEEDS_MORE_RESEARCH"
    status = str(
        guide_source_depth.get(
            "source_depth_status",
            guide_source_depth.get("depth_status", ""),
        )
    ).lower()
    if status in {"source_backed", "source_backed_strong", "strong"}:
        return "SOURCE_BACKED_STRONG"
    if status in {"static_semantics_only", "static_semantics_usable", "usable"}:
        return "STATIC_SEMANTICS_USABLE"
    if status in {"needs_more_research", "usable_with_runtime_gaps"}:
        return "NEEDS_MORE_RESEARCH"
    return "INSUFFICIENT_FOR_STRONG_CONFIG"


def _primary_blockers(report: dict[str, Any], technical_status: str) -> list[dict[str, str]]:
    if technical_status == "VALID_PACKAGE":
        return []
    errors = report.get("errors", [])
    if not isinstance(errors, list):
        errors = [errors]
    if not errors:
        errors = ["technical_validation_failed"]
    return [{"reason": str(error)} for error in errors]


def _warnings(
    *,
    guide_source_depth: dict[str, Any] | None,
    semantic_status: str,
    unsupported_conditions: list[dict[str, Any]],
    globalvalue_authority: dict[str, Any],
) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    if semantic_status == "STATIC_SEMANTICS_USABLE":
        warnings.append({"reason": "static_semantics_only"})
    elif semantic_status == "NEEDS_MORE_RESEARCH":
        warnings.append({"reason": "needs_more_research"})
    elif semantic_status == "INSUFFICIENT_FOR_STRONG_CONFIG":
        warnings.append({"reason": "insufficient_for_strong_config"})
    if guide_source_depth and isinstance(guide_source_depth.get("warnings"), list):
        warnings.extend(
            warning for warning in guide_source_depth["warnings"] if isinstance(warning, dict)
        )
    for condition in unsupported_conditions:
        warning = dict(condition)
        warning.setdefault("reason", "unsupported_condition")
        warnings.append(warning)
    for row in globalvalue_authority.get("blocked_until_runtime_evidence", []):
        if not isinstance(row, dict):
            continue
        warnings.append(
            {
                "reason": "globalvalue_runtime_evidence_required",
                "key": str(row.get("key", "")),
            }
        )
    return warnings


def _next_action_and_policy(
    *,
    technical_status: str,
    semantic_status: str,
    primary_blockers: list[dict[str, str]],
) -> tuple[str, str]:
    if technical_status == "INVALID_PACKAGE" or primary_blockers:
        return "FIX_PACKAGE_BEFORE_APPLY", "BLOCKED"
    if semantic_status == "SOURCE_BACKED_STRONG":
        return "READY_TO_APPLY_OR_HANDOFF", "ALLOWED"
    if semantic_status == "STATIC_SEMANTICS_USABLE":
        return "READY_WITH_WARNINGS", "ALLOWED_WITH_WARNINGS"
    return "RESEARCH_REQUIRED_BEFORE_STRONG_CONFIG", "ALLOWED_WITH_WARNINGS"

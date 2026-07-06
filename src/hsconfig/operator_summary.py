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
    claim_coverage_report: dict[str, Any] | None = None,
    config_readiness_summary: dict[str, Any] | None = None,
    claim_conflict_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    technical_status = _technical_status(technical_validation)
    semantic_status = _semantic_status(
        technical_status=technical_status,
        guide_source_depth=guide_source_depth,
        claim_coverage_report=claim_coverage_report,
        config_readiness_summary=config_readiness_summary,
        claim_conflict_report=claim_conflict_report,
    )
    primary_blockers = _primary_blockers(technical_validation, technical_status)
    warnings = _warnings(
        guide_source_depth=guide_source_depth,
        semantic_status=semantic_status,
        unsupported_conditions=unsupported_conditions or [],
        globalvalue_authority=globalvalue_authority or {},
        claim_conflict_report=claim_conflict_report or {},
        claim_coverage_report=claim_coverage_report or {},
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


def _semantic_status(
    *,
    technical_status: str,
    guide_source_depth: dict[str, Any] | None,
    claim_coverage_report: dict[str, Any] | None,
    config_readiness_summary: dict[str, Any] | None,
    claim_conflict_report: dict[str, Any] | None,
) -> str:
    if technical_status == "INVALID_PACKAGE":
        return "INVALID_PACKAGE"
    if not guide_source_depth:
        return "NEEDS_MORE_RESEARCH"
    source_depth_status = _source_depth_status(guide_source_depth)
    claim_count = _claim_count(guide_source_depth)
    generic_low_confidence = _generic_low_confidence_count(
        config_readiness_summary=config_readiness_summary,
        claim_coverage_report=claim_coverage_report,
    )
    uncovered_cards = _uncovered_cards(claim_coverage_report or {})
    conflict_count = _int_value((claim_conflict_report or {}).get("conflict_count", 0))

    if (
        source_depth_status == "source_backed"
        and claim_count > 0
        and generic_low_confidence == 0
        and conflict_count == 0
        and not uncovered_cards
    ):
        return "SOURCE_BACKED_STRONG"
    if generic_low_confidence > 0 or uncovered_cards or conflict_count > 0:
        return "VALID_BUT_NOT_GUIDE_STRONG"
    if source_depth_status == "static_semantics_only":
        return "STATIC_SEMANTICS_USABLE"
    return "NEEDS_MORE_RESEARCH"


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
    claim_conflict_report: dict[str, Any],
    claim_coverage_report: dict[str, Any],
) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    if semantic_status == "STATIC_SEMANTICS_USABLE":
        warnings.append({"reason": "static_semantics_only"})
    elif semantic_status == "NEEDS_MORE_RESEARCH":
        warnings.append({"reason": "needs_more_research"})
    elif semantic_status == "VALID_BUT_NOT_GUIDE_STRONG":
        warnings.append({"reason": "valid_but_not_guide_strong"})
    if guide_source_depth and isinstance(guide_source_depth.get("warnings"), list):
        warnings.extend(
            warning for warning in guide_source_depth["warnings"] if isinstance(warning, dict)
        )
    conflict_count = _int_value(claim_conflict_report.get("conflict_count", 0))
    if conflict_count > 0:
        warnings.append({"reason": "claim_conflicts_present", "conflict_count": conflict_count})
    low_confidence_count = _low_confidence_card_count(claim_coverage_report)
    if low_confidence_count > 0:
        warnings.append(
            {"reason": "cards_still_low_confidence", "card_count": low_confidence_count}
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


def _low_confidence_card_count(report: dict[str, Any]) -> int:
    summary = report.get("summary", {})
    if isinstance(summary, dict) and "uncovered_low_confidence" in summary:
        return _int_value(summary.get("uncovered_low_confidence", 0))
    uncovered_cards = report.get("uncovered_cards", [])
    if isinstance(uncovered_cards, list):
        return len(uncovered_cards)
    cards = report.get("cards", {})
    if not isinstance(cards, dict):
        return 0
    return sum(
        1
        for row in cards.values()
        if isinstance(row, dict) and row.get("coverage_status") == "uncovered_low_confidence"
    )


def _int_value(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _source_depth_status(report: dict[str, Any]) -> str:
    status = str(
        report.get(
            "source_depth_status",
            report.get("depth_status", ""),
        )
    ).lower()
    if status in {"source_backed", "source_backed_strong", "strong"}:
        return "source_backed"
    if status in {"static_semantics_only", "static_semantics_usable", "usable"}:
        return "static_semantics_only"
    return status


def _claim_count(report: dict[str, Any]) -> int:
    if "claim_count" in report:
        return _int_value(report.get("claim_count", 0))
    summary = report.get("summary", {})
    if isinstance(summary, dict):
        return _int_value(summary.get("claim_count", 0))
    return 0


def _generic_low_confidence_count(
    *,
    config_readiness_summary: dict[str, Any] | None,
    claim_coverage_report: dict[str, Any] | None,
) -> int:
    if isinstance(config_readiness_summary, dict):
        return _int_value(config_readiness_summary.get("generic_low_confidence", 0))
    return _low_confidence_card_count(claim_coverage_report or {})


def _uncovered_cards(report: dict[str, Any]) -> list[str]:
    uncovered_cards = report.get("uncovered_cards", [])
    if isinstance(uncovered_cards, list):
        return [str(card) for card in uncovered_cards]
    cards = report.get("cards", {})
    if not isinstance(cards, dict):
        return []
    return [
        str(card_id)
        for card_id, row in cards.items()
        if isinstance(row, dict) and row.get("coverage_status") == "uncovered_low_confidence"
    ]


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
    if semantic_status == "VALID_BUT_NOT_GUIDE_STRONG":
        return "IMPROVE_GUIDE_SOURCES_BEFORE_STRONG_APPLY", "ALLOWED_WITH_WARNINGS"
    return "RESEARCH_REQUIRED_BEFORE_STRONG_CONFIG", "ALLOWED_WITH_WARNINGS"

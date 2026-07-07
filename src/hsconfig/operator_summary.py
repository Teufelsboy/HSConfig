from __future__ import annotations

import hashlib
from typing import Any


VALID_STATUSES = {"passed", "pass", "valid", "ok", "success"}
SOURCE_BACKED_STRONG_REQUIREMENTS = [
    "technical_status=VALID_PACKAGE",
    "source_depth_status=source_backed",
    "claim_count>0",
    "generic_low_confidence_cards=0",
    "uncovered_cards=0",
    "claim_conflicts=0",
]
READINESS_SUMMARY_KEY_BY_BLOCKER_REASON = {
    "cards_need_guide_claims": "cards_needing_guide_claims",
    "cards_need_runtime_surface": "cards_needing_runtime_surface",
    "cards_need_mulligan_claims": "cards_needing_mulligan_claims",
    "cards_need_combo_sequence": "cards_needing_combo_sequence",
    "cards_need_condition_lowering": "cards_needing_condition_lowering",
    "cards_need_mechanic_lowering": "cards_needing_mechanic_lowering",
}


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
    config_readiness_report: dict[str, Any] | None = None,
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
    guide_strength_summary = _guide_strength_summary(
        guide_source_depth=guide_source_depth or {},
        claim_coverage_report=claim_coverage_report or {},
        config_readiness_summary=config_readiness_summary or {},
        claim_conflict_report=claim_conflict_report or {},
    )
    semantic_blockers = _semantic_blockers(
        claim_coverage_report=claim_coverage_report or {},
        config_readiness_summary=config_readiness_summary or {},
        config_readiness_report=config_readiness_report or {},
        claim_conflict_report=claim_conflict_report or {},
        globalvalue_authority=globalvalue_authority or {},
        unsupported_conditions=unsupported_conditions or [],
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
        "guide_strength_summary": guide_strength_summary,
        "semantic_blockers": semantic_blockers,
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


def _guide_strength_summary(
    *,
    guide_source_depth: dict[str, Any],
    claim_coverage_report: dict[str, Any],
    config_readiness_summary: dict[str, Any],
    claim_conflict_report: dict[str, Any],
) -> dict[str, Any]:
    coverage_summary = claim_coverage_report.get("summary", {})
    if not isinstance(coverage_summary, dict):
        coverage_summary = {}
    uncovered_cards = _uncovered_cards(claim_coverage_report)
    return {
        "total_cards": _int_value(
            config_readiness_summary.get(
                "total_cards",
                claim_coverage_report.get("total_cards", 0),
            )
        ),
        "guide_backed_cards": _int_value(
            coverage_summary.get(
                "guide_backed",
                claim_coverage_report.get("guide_backed_cards", 0),
            )
        ),
        "static_semantics_cards": _int_value(coverage_summary.get("static_semantics_backfilled", 0)),
        "generic_low_confidence_cards": _generic_low_confidence_count(
            config_readiness_summary=config_readiness_summary,
            claim_coverage_report=claim_coverage_report,
        ),
        "uncovered_cards": len(uncovered_cards),
        "claim_conflicts": _int_value(claim_conflict_report.get("conflict_count", 0)),
        "runtime_emitted_cards": _int_value(config_readiness_summary.get("runtime_emitted", 0)),
        "cards_needing_guide_claims": _int_value(
            config_readiness_summary.get("cards_needing_guide_claims", 0)
        ),
        "cards_needing_runtime_surface": _int_value(
            config_readiness_summary.get("cards_needing_runtime_surface", 0)
        ),
        "cards_needing_mulligan_claims": _int_value(
            config_readiness_summary.get("cards_needing_mulligan_claims", 0)
        ),
        "cards_needing_combo_sequence": _int_value(
            config_readiness_summary.get("cards_needing_combo_sequence", 0)
        ),
        "cards_needing_condition_lowering": _int_value(
            config_readiness_summary.get("cards_needing_condition_lowering", 0)
        ),
        "cards_needing_mechanic_lowering": _int_value(
            config_readiness_summary.get("cards_needing_mechanic_lowering", 0)
        ),
        "source_backed_strong_requires": SOURCE_BACKED_STRONG_REQUIREMENTS,
    }


def _semantic_blockers(
    *,
    claim_coverage_report: dict[str, Any],
    config_readiness_summary: dict[str, Any],
    config_readiness_report: dict[str, Any],
    claim_conflict_report: dict[str, Any],
    globalvalue_authority: dict[str, Any],
    unsupported_conditions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    missing_link_reasons = {
        "needs_guide_claim": ("cards_need_guide_claims", "blocks_source_backed_strong"),
        "needs_runtime_surface": ("cards_need_runtime_surface", "report_visible_gap"),
        "needs_mulligan_claim": ("cards_need_mulligan_claims", "report_visible_gap"),
        "needs_combo_sequence": ("cards_need_combo_sequence", "report_visible_gap"),
        "needs_condition_lowering": ("cards_need_condition_lowering", "report_visible_gap"),
        "needs_mechanic_lowering": ("cards_need_mechanic_lowering", "report_visible_gap"),
    }
    for missing_link, (reason, strength) in missing_link_reasons.items():
        affected = _affected_cards_by_missing_link(config_readiness_report, missing_link)
        summary_key = READINESS_SUMMARY_KEY_BY_BLOCKER_REASON.get(reason, reason)
        count = len(affected) or _int_value(config_readiness_summary.get(summary_key, 0))
        if count:
            blockers.append(
                {
                    "reason": reason,
                    "count": count,
                    "blocking_strength": strength,
                    "report": "reports/per_card_config_readiness_report.json",
                    "affected_cards": affected[:5],
                }
            )
    conflicts = claim_conflict_report.get("conflicts", [])
    conflict_count = _int_value(claim_conflict_report.get("conflict_count", 0))
    if conflict_count:
        blockers.append(
            {
                "reason": "claim_conflicts_present",
                "count": conflict_count,
                "blocking_strength": "blocks_source_backed_strong",
                "report": "reports/claim_conflict_report.json",
                "affected_cards": _affected_cards_from_conflicts(conflicts)[:5],
            }
        )
    if unsupported_conditions:
        blockers.append(
            {
                "reason": "unsupported_conditions_present",
                "count": len(unsupported_conditions),
                "blocking_strength": "report_visible_gap",
                "report": "reports/mulligan_plan_report.json",
                "affected_cards": _affected_cards_from_conditions(unsupported_conditions)[:5],
            }
        )
    blocked_globalvalues = [
        row
        for row in globalvalue_authority.get("blocked_until_runtime_evidence", [])
        if isinstance(row, dict)
    ]
    if blocked_globalvalues:
        blockers.append(
            {
                "reason": "globalvalues_runtime_evidence_required",
                "count": len(blocked_globalvalues),
                "blocking_strength": "runtime_evidence_required",
                "report": "reports/global_values_authority_matrix.json",
                "affected_cards": [],
            }
        )
    return blockers


def _affected_cards_by_missing_link(
    config_readiness_report: dict[str, Any],
    missing_link: str,
) -> list[dict[str, str]]:
    cards = config_readiness_report.get("cards", {})
    if not isinstance(cards, dict):
        return []
    rows = []
    for card_id, row in sorted(cards.items()):
        if not isinstance(row, dict) or row.get("first_missing_link") != missing_link:
            continue
        rows.append({"card_id": str(card_id), "name": str(row.get("name", card_id))})
    return rows


def _affected_cards_from_conflicts(conflicts: Any) -> list[dict[str, str]]:
    if not isinstance(conflicts, list):
        return []
    rows = []
    for conflict in conflicts:
        if isinstance(conflict, dict) and conflict.get("card_id"):
            rows.append({"card_id": str(conflict["card_id"]), "name": str(conflict["card_id"])})
    return rows


def _affected_cards_from_conditions(conditions: list[dict[str, Any]]) -> list[dict[str, str]]:
    rows = []
    for condition in conditions:
        card_id = condition.get("card_id") or condition.get("card")
        if card_id:
            rows.append({"card_id": str(card_id), "name": str(card_id)})
    return rows


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

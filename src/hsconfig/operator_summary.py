from __future__ import annotations

from collections import Counter
import hashlib
from typing import Any

from hsconfig.config_usefulness import build_config_usefulness
from hsconfig.operator_guidance import build_operator_guidance
from hsconfig.report_ownership import build_report_ownership


VALID_STATUSES = {"passed", "pass", "valid", "ok", "success"}
SOURCE_BACKED_STRONG_REQUIREMENTS = [
    "technical_status=VALID_PACKAGE",
    "source_depth_status=source_backed",
    "claim_count>0",
    "source_evidence_warnings=0",
    "generic_low_confidence_cards=0",
    "uncovered_cards=0",
    "claim_conflicts=0",
    "cards_needing_guide_claims=0",
    "cards_needing_runtime_surface=0",
    "cards_needing_mulligan_claims=0",
    "cards_needing_combo_sequence=0",
    "cards_needing_condition_lowering=0",
    "cards_needing_mechanic_lowering=0",
]
READINESS_GAP_SUMMARY_KEYS = (
    "cards_needing_guide_claims",
    "cards_needing_runtime_surface",
    "cards_needing_mulligan_claims",
    "cards_needing_combo_sequence",
    "cards_needing_condition_lowering",
    "cards_needing_mechanic_lowering",
)
SOURCE_INFORMED_ALLOWED_BLOCKER_REASONS = [
    "cards_need_guide_claims",
    "cards_need_mulligan_claims",
]
LEGACY_SOURCE_INFORMED_FLAG = "--allow-source-informed"
SOURCE_INFORMED_RUNTIME_GATE_IMPACT = "diagnostic_only"
SOURCE_INFORMED_LEGACY_FLAG_SCOPE = "backward_compatible_only"
SOURCE_INFORMED_BLOCKING_REASONS = {
    "cards_need_runtime_surface",
    "cards_need_combo_sequence",
    "cards_need_condition_lowering",
    "cards_need_mechanic_lowering",
    "claim_conflicts_present",
    "unsupported_conditions_present",
}
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
    deck_name: str | None = None,
    deck_code: str | None = None,
    technical_validation: dict[str, Any] | None = None,
    guide_source_depth: dict[str, Any] | None = None,
    unsupported_conditions: list[dict[str, Any]] | None = None,
    globalvalue_authority: dict[str, Any] | None = None,
    generated_files: list[str] | None = None,
    claim_coverage_report: dict[str, Any] | None = None,
    config_readiness_summary: dict[str, Any] | None = None,
    config_readiness_report: dict[str, Any] | None = None,
    claim_conflict_report: dict[str, Any] | None = None,
    mulligan_plan_report: dict[str, Any] | None = None,
    card_behavior_plan_report: dict[str, Any] | None = None,
    combo_plan_report: dict[str, Any] | None = None,
    globalvalues_profile_report: dict[str, Any] | None = None,
    semantic_enrichment_report: dict[str, Any] | None = None,
    mechanic_drift_report: dict[str, Any] | None = None,
    validation_report: dict[str, Any] | None = None,
    guide_source_depth_report: dict[str, Any] | None = None,
    source_claim_gap_report: dict[str, Any] | None = None,
    strong_promotion_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    # Compatibility inputs for callers that use the task-brief naming.
    if technical_validation is None:
        technical_validation = validation_report or {"status": "unknown"}
    if guide_source_depth is None:
        guide_source_depth = guide_source_depth_report
    if config_readiness_summary is None and config_readiness_report is not None:
        config_readiness_summary = _normalize_readiness_summary_aliases(
            config_readiness_report
        )
    _ = source_claim_gap_report
    _ = strong_promotion_report

    technical_validation = technical_validation or {"status": "unknown"}
    unsupported_conditions = unsupported_conditions or []
    globalvalue_authority = globalvalue_authority or {}
    generated_files = generated_files or []
    deck_name = deck_name or ""
    deck_code = deck_code or ""

    technical_status = _technical_status(technical_validation)
    effective_config_readiness_summary = _effective_config_readiness_summary(
        config_readiness_summary,
        config_readiness_report,
    )
    mechanic_warning_summary = _mechanic_warning_summary(
        config_readiness_report,
        effective_config_readiness_summary,
    )
    mechanic_visibility_summary = _mechanic_visibility_summary(
        config_readiness_report,
        effective_config_readiness_summary,
    )
    semantic_status = _semantic_status(
        technical_status=technical_status,
        guide_source_depth=guide_source_depth,
        claim_coverage_report=claim_coverage_report,
        config_readiness_summary=effective_config_readiness_summary,
        claim_conflict_report=claim_conflict_report,
        unsupported_conditions=unsupported_conditions,
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
        config_readiness_summary=effective_config_readiness_summary,
        claim_conflict_report=claim_conflict_report or {},
    )
    semantic_blockers = _semantic_blockers(
        claim_coverage_report=claim_coverage_report or {},
        config_readiness_summary=effective_config_readiness_summary,
        config_readiness_report=config_readiness_report or {},
        claim_conflict_report=claim_conflict_report or {},
        globalvalue_authority=globalvalue_authority or {},
        unsupported_conditions=unsupported_conditions or [],
    )
    config_usefulness = build_config_usefulness(
        technical_status=technical_status,
        semantic_status=semantic_status,
        config_readiness_summary=effective_config_readiness_summary,
        config_readiness_report=config_readiness_report or {},
        mulligan_plan_report=mulligan_plan_report or {},
        card_behavior_plan_report=card_behavior_plan_report or {},
        combo_plan_report=combo_plan_report or {},
        globalvalues_profile_report=globalvalues_profile_report or {},
    )
    source_informed_apply_readiness = _source_informed_apply_readiness(
        technical_status=technical_status,
        semantic_status=semantic_status,
        guide_strength_summary=guide_strength_summary,
        semantic_blockers=semantic_blockers,
    )
    next_action, apply_policy = _next_action_and_policy(
        technical_status=technical_status,
        semantic_status=semantic_status,
        primary_blockers=primary_blockers,
    )
    runtime_apply_mode, runtime_apply_allowed, runtime_apply_requires_flag = (
        _runtime_apply_contract(
            technical_status=technical_status,
            apply_policy=apply_policy,
        )
    )
    summary = {
        "schema_version": 1,
        "deck": {
            "name": deck_name,
            "deck_code_hash": f"sha256:{hashlib.sha256(deck_code.encode('utf-8')).hexdigest()}",
        },
        "technical_status": technical_status,
        "semantic_status": semantic_status,
        "next_action": next_action,
        "apply_policy": apply_policy,
        "runtime_load_safe": technical_status == "VALID_PACKAGE",
        "runtime_apply_mode": runtime_apply_mode,
        "runtime_apply_allowed": runtime_apply_allowed,
        "runtime_apply_requires_flag": runtime_apply_requires_flag,
        "primary_blockers": primary_blockers,
        "warnings": warnings,
        "mechanic_warning_summary": mechanic_warning_summary,
        "mechanic_visibility_summary": mechanic_visibility_summary,
        "semantic_enrichment_summary": _semantic_enrichment_summary(
            semantic_enrichment_report
        ),
        "mechanic_drift_summary": _mechanic_drift_summary(mechanic_drift_report),
        "guide_strength_summary": guide_strength_summary,
        "semantic_blockers": semantic_blockers,
        "config_usefulness": config_usefulness,
        "source_informed_apply_readiness": source_informed_apply_readiness,
        "generated_files": sorted(str(path) for path in generated_files),
        "report_ownership": build_report_ownership(),
    }
    summary["operator_guidance"] = build_operator_guidance(summary)
    return summary


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
    unsupported_conditions: list[dict[str, Any]] | None,
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
    uncovered_card_count = _uncovered_card_count_with_fallback(
        claim_coverage_report=claim_coverage_report,
        config_readiness_summary=config_readiness_summary,
    )
    conflict_count = _int_value((claim_conflict_report or {}).get("conflict_count", 0))
    readiness_gap_count = _readiness_gap_count(config_readiness_summary or {})
    unsupported_condition_count = max(
        len(unsupported_conditions or []),
        _first_present_int(
            config_readiness_summary or {},
            "unsupported_conditions_present",
        ),
    )
    source_evidence = guide_source_depth.get("source_evidence", {}) if isinstance(guide_source_depth, dict) else {}
    source_evidence_warnings = _int_value(source_evidence.get("warnings_count", 0))

    if (
        source_depth_status == "source_backed"
        and claim_count > 0
        and generic_low_confidence == 0
        and conflict_count == 0
        and readiness_gap_count == 0
        and unsupported_condition_count == 0
        and source_evidence_warnings == 0
        and uncovered_card_count == 0
    ):
        return "SOURCE_BACKED_STRONG"
    if (
        generic_low_confidence > 0
        or uncovered_card_count > 0
        or conflict_count > 0
        or readiness_gap_count > 0
        or unsupported_condition_count > 0
        or source_evidence_warnings > 0
    ):
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


def _normalize_readiness_summary_aliases(
    config_readiness_report: dict[str, Any]
) -> dict[str, Any] | None:
    summary = config_readiness_report.get("summary", {})
    if not isinstance(summary, dict):
        return None
    aliases = {
        "cards_need_guide_claims": "cards_needing_guide_claims",
        "cards_need_runtime_surface": "cards_needing_runtime_surface",
        "cards_need_mulligan_claims": "cards_needing_mulligan_claims",
        "cards_need_combo_sequence": "cards_needing_combo_sequence",
        "cards_need_condition_lowering": "cards_needing_condition_lowering",
        "cards_need_mechanic_lowering": "cards_needing_mechanic_lowering",
        "generic_low_confidence_cards": "generic_low_confidence",
    }
    normalized = dict(summary)
    for source_key, target_key in aliases.items():
        if source_key in summary:
            if target_key in normalized:
                normalized[target_key] = max(
                    _int_value(normalized.get(target_key, 0)),
                    _int_value(summary.get(source_key, 0)),
                )
            else:
                normalized[target_key] = summary[source_key]
            normalized.pop(source_key, None)
    return normalized


def _mechanic_warning_summary(
    config_readiness_report: dict[str, Any] | None,
    config_readiness_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    empty_summary = {
        "support_level_counts": {"direct": 0, "partial": 0, "warning_only": 0},
        "warning_only_mechanics": [],
        "warning_only_card_count": 0,
    }
    summary = {}
    if isinstance(config_readiness_report, dict):
        summary = config_readiness_report.get("summary", {})
    if not isinstance(summary, dict) or "mechanic_support" not in summary:
        summary = config_readiness_summary or {}
    if not isinstance(summary, dict):
        return empty_summary
    mechanic_support = summary.get("mechanic_support", {})
    if not isinstance(mechanic_support, dict):
        return empty_summary

    support_level_counts = mechanic_support.get("support_level_counts", {})
    if not isinstance(support_level_counts, dict):
        support_level_counts = {}
    warning_only_mechanics = mechanic_support.get("warning_only_mechanics", [])
    if not isinstance(warning_only_mechanics, list):
        warning_only_mechanics = []

    return {
        "support_level_counts": {
            "direct": _int_value(support_level_counts.get("direct", 0)),
            "partial": _int_value(support_level_counts.get("partial", 0)),
            "warning_only": _int_value(support_level_counts.get("warning_only", 0)),
        },
        "warning_only_mechanics": [str(item) for item in warning_only_mechanics],
        "warning_only_card_count": _int_value(mechanic_support.get("warning_only_card_count", 0)),
    }


def _mechanic_visibility_summary(
    config_readiness_report: dict[str, Any] | None,
    config_readiness_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    empty_summary = {
        "non_blocking": True,
        "bucket_counts": {
            "direct": 0,
            "identity_gated_direct": 0,
            "partial": 0,
            "warning_only": 0,
        },
        "mechanics_by_bucket": {
            "direct": [],
            "identity_gated_direct": [],
            "partial": [],
            "warning_only": [],
        },
        "warning_only_card_count": 0,
        "first_warning_boundary": None,
        "warning_boundaries": [],
    }
    summary = {}
    if isinstance(config_readiness_report, dict):
        summary = config_readiness_report.get("summary", {})
    if not isinstance(summary, dict) or "mechanic_visibility" not in summary:
        summary = config_readiness_summary or {}
    if not isinstance(summary, dict):
        return empty_summary
    visibility = summary.get("mechanic_visibility", {})
    if not isinstance(visibility, dict):
        return empty_summary

    bucket_counts = visibility.get("bucket_counts", {})
    if not isinstance(bucket_counts, dict):
        bucket_counts = {}
    mechanics_by_bucket = visibility.get("mechanics_by_bucket", {})
    if not isinstance(mechanics_by_bucket, dict):
        mechanics_by_bucket = {}
    warning_boundaries = visibility.get("warning_boundaries", [])
    if not isinstance(warning_boundaries, list):
        warning_boundaries = []

    return {
        "non_blocking": bool(visibility.get("non_blocking", True)),
        "bucket_counts": {
            "direct": _int_value(bucket_counts.get("direct", 0)),
            "identity_gated_direct": _int_value(bucket_counts.get("identity_gated_direct", 0)),
            "partial": _int_value(bucket_counts.get("partial", 0)),
            "warning_only": _int_value(bucket_counts.get("warning_only", 0)),
        },
        "mechanics_by_bucket": {
            "direct": [str(item) for item in mechanics_by_bucket.get("direct", [])],
            "identity_gated_direct": [
                str(item) for item in mechanics_by_bucket.get("identity_gated_direct", [])
            ],
            "partial": [str(item) for item in mechanics_by_bucket.get("partial", [])],
            "warning_only": [str(item) for item in mechanics_by_bucket.get("warning_only", [])],
        },
        "warning_only_card_count": _int_value(visibility.get("warning_only_card_count", 0)),
        "first_warning_boundary": visibility.get("first_warning_boundary"),
        "warning_boundaries": [
            {
                "mechanic": str(item.get("mechanic", "")),
                "warning_boundary": str(item.get("warning_boundary", "")),
            }
            for item in warning_boundaries
            if isinstance(item, dict)
        ],
    }


def _semantic_enrichment_summary(report: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(report, dict):
        return {
            "non_blocking": True,
            "total_cards": 0,
            "cards_with_warning_only_mechanics": 0,
            "deckwide_effect_count": 0,
            "warning_count": 0,
        }
    summary = report.get("summary", {})
    if not isinstance(summary, dict):
        summary = {}
    return {
        "non_blocking": bool(report.get("non_blocking", True)),
        "total_cards": _int_value(summary.get("total_cards", 0)),
        "cards_with_warning_only_mechanics": _int_value(
            summary.get("cards_with_warning_only_mechanics", 0)
        ),
        "deckwide_effect_count": _int_value(summary.get("deckwide_effect_count", 0)),
        "warning_count": _int_value(summary.get("warning_count", 0)),
    }


def _mechanic_drift_summary(report: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(report, dict):
        return {
            "non_blocking": True,
            "mechanic_count": 0,
            "unknown_mechanic_count": 0,
            "text_only_mechanic_count": 0,
            "unknown_card_type_count": 0,
            "unknown_mechanics": [],
            "text_only_mechanics": [],
            "unknown_card_types": [],
            "first_unknown_mechanic": None,
            "first_text_only_mechanic": None,
            "first_unknown_card_type": None,
            "next_report_to_open": None,
        }
    summary = report.get("summary", {})
    if not isinstance(summary, dict):
        summary = {}
    unknown_mechanics = [str(item) for item in report.get("unknown_mechanics", [])]
    text_only_mechanics = [str(item) for item in report.get("text_only_mechanics", [])]
    unknown_card_types = [str(item) for item in report.get("unknown_card_types", [])]
    has_followup = bool(unknown_mechanics or text_only_mechanics or unknown_card_types)
    return {
        "non_blocking": bool(report.get("non_blocking", True)),
        "mechanic_count": _int_value(summary.get("mechanic_count", 0)),
        "unknown_mechanic_count": _int_value(
            summary.get("unknown_mechanic_count", 0)
        ),
        "text_only_mechanic_count": _int_value(
            summary.get("text_only_mechanic_count", 0)
        ),
        "unknown_card_type_count": _int_value(
            summary.get("unknown_card_type_count", 0)
        ),
        "unknown_mechanics": unknown_mechanics,
        "text_only_mechanics": text_only_mechanics,
        "unknown_card_types": unknown_card_types,
        "first_unknown_mechanic": unknown_mechanics[0] if unknown_mechanics else None,
        "first_text_only_mechanic": text_only_mechanics[0] if text_only_mechanics else None,
        "first_unknown_card_type": unknown_card_types[0] if unknown_card_types else None,
        "next_report_to_open": "reports/mechanic_drift_report.json" if has_followup else None,
    }


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
    depth_summary = guide_source_depth.get("summary", {})
    if not isinstance(depth_summary, dict):
        depth_summary = {}
    source_evidence = guide_source_depth.get("source_evidence", {})
    if not isinstance(source_evidence, dict):
        source_evidence = {}
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
        "uncovered_cards": _uncovered_card_count_with_fallback(
            claim_coverage_report=claim_coverage_report,
            config_readiness_summary=config_readiness_summary,
        ),
        "claim_conflicts": _int_value(claim_conflict_report.get("conflict_count", 0)),
        "lowerable_claims": _int_value(depth_summary.get("lowerable_claims", 0)),
        "report_only_claims": _int_value(depth_summary.get("report_only_claims", 0)),
        "source_evidence_warnings": _int_value(source_evidence.get("warnings_count", 0)),
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
    else:
        unsupported_count = _first_present_int(
            config_readiness_summary,
            "unsupported_conditions_present",
        )
        if unsupported_count:
            blockers.append(
                {
                    "reason": "unsupported_conditions_present",
                    "count": unsupported_count,
                    "blocking_strength": "report_visible_gap",
                    "report": "reports/mulligan_plan_report.json",
                    "affected_cards": [],
                }
            )
    return blockers


def _source_informed_apply_readiness(
    *,
    technical_status: str,
    semantic_status: str,
    guide_strength_summary: dict[str, Any],
    semantic_blockers: list[dict[str, Any]],
) -> dict[str, Any]:
    allowed_reasons = list(SOURCE_INFORMED_ALLOWED_BLOCKER_REASONS)
    if technical_status != "VALID_PACKAGE":
        return {
            "status": "not_applicable",
            "requires_flag": LEGACY_SOURCE_INFORMED_FLAG,
            "runtime_gate_impact": SOURCE_INFORMED_RUNTIME_GATE_IMPACT,
            "legacy_flag_scope": SOURCE_INFORMED_LEGACY_FLAG_SCOPE,
            "allowed_blocker_reasons": allowed_reasons,
            "blocking_reasons": ["invalid_package"],
            "source_gap_count": 0,
        }
    if semantic_status != "VALID_BUT_NOT_GUIDE_STRONG":
        return {
            "status": "not_applicable",
            "requires_flag": LEGACY_SOURCE_INFORMED_FLAG,
            "runtime_gate_impact": SOURCE_INFORMED_RUNTIME_GATE_IMPACT,
            "legacy_flag_scope": SOURCE_INFORMED_LEGACY_FLAG_SCOPE,
            "allowed_blocker_reasons": allowed_reasons,
            "blocking_reasons": [],
            "source_gap_count": 0,
        }

    blocker_reasons = [
        str(blocker.get("reason", ""))
        for blocker in semantic_blockers
        if isinstance(blocker, dict)
    ]
    hard_reasons = sorted(
        {
            reason
            for reason in blocker_reasons
            if reason in SOURCE_INFORMED_BLOCKING_REASONS
            or reason not in SOURCE_INFORMED_ALLOWED_BLOCKER_REASONS
        }
    )
    if _int_value(guide_strength_summary.get("generic_low_confidence_cards", 0)) > 0:
        hard_reasons.append("generic_low_confidence_cards")
    if _int_value(guide_strength_summary.get("uncovered_cards", 0)) > 0:
        hard_reasons.append("uncovered_cards")
    if _int_value(guide_strength_summary.get("claim_conflicts", 0)) > 0:
        hard_reasons.append("claim_conflicts_present")
    if _int_value(guide_strength_summary.get("source_evidence_warnings", 0)) > 0:
        hard_reasons.append("source_evidence_warnings")

    source_gap_count = sum(
        int(blocker.get("count", 0))
        for blocker in semantic_blockers
        if isinstance(blocker, dict)
        and str(blocker.get("reason", "")) in SOURCE_INFORMED_ALLOWED_BLOCKER_REASONS
    )
    return {
        "status": "blocked" if hard_reasons else "ready",
        "requires_flag": LEGACY_SOURCE_INFORMED_FLAG,
        "runtime_gate_impact": SOURCE_INFORMED_RUNTIME_GATE_IMPACT,
        "legacy_flag_scope": SOURCE_INFORMED_LEGACY_FLAG_SCOPE,
        "allowed_blocker_reasons": allowed_reasons,
        "blocking_reasons": sorted(set(hard_reasons)),
        "source_gap_count": source_gap_count,
    }


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
        return _max_present_int(
            config_readiness_summary,
            "generic_low_confidence",
            "generic_low_confidence_cards",
        )
    return _low_confidence_card_count(claim_coverage_report or {})


def _readiness_gap_count(config_readiness_summary: dict[str, Any]) -> int:
    if not isinstance(config_readiness_summary, dict):
        return 0
    return sum(_int_value(config_readiness_summary.get(key, 0)) for key in READINESS_GAP_SUMMARY_KEYS)


def _effective_config_readiness_summary(
    config_readiness_summary: dict[str, Any] | None,
    config_readiness_report: dict[str, Any] | None,
) -> dict[str, Any]:
    if isinstance(config_readiness_summary, dict) and config_readiness_summary:
        return config_readiness_summary
    if not isinstance(config_readiness_report, dict):
        return {}
    cards = config_readiness_report.get("cards", {})
    if not isinstance(cards, dict):
        return {}

    lanes: Counter[str] = Counter()
    missing_links: Counter[str] = Counter()
    for row in cards.values():
        if not isinstance(row, dict):
            continue
        lane = str(row.get("readiness_lane", "")).strip()
        if lane:
            lanes[lane] += 1
        missing_link = str(row.get("first_missing_link", "")).strip()
        if missing_link and missing_link != "none":
            missing_links[missing_link] += 1

    return {
        "total_cards": len(cards),
        "runtime_emitted": lanes["runtime_emitted"],
        "mulligan_only": lanes["mulligan_only"],
        "globalvalues_only": lanes["globalvalues_only"],
        "report_only_supported": lanes["report_only_supported"],
        "archetype_inferred": lanes["archetype_inferred"],
        "generic_low_confidence": lanes["generic_low_confidence"],
        "cards_needing_guide_claims": missing_links["needs_guide_claim"],
        "cards_needing_runtime_surface": missing_links["needs_runtime_surface"],
        "cards_needing_mulligan_claims": missing_links["needs_mulligan_claim"],
        "cards_needing_combo_sequence": missing_links["needs_combo_sequence"],
        "cards_needing_condition_lowering": missing_links["needs_condition_lowering"],
        "cards_needing_mechanic_lowering": missing_links["needs_mechanic_lowering"],
    }


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


def _uncovered_card_count(report: dict[str, Any]) -> int:
    summary = report.get("summary", {})
    if isinstance(summary, dict) and "uncovered_low_confidence" in summary:
        return _int_value(summary.get("uncovered_low_confidence", 0))
    return len(_uncovered_cards(report))


def _uncovered_card_count_with_fallback(
    *,
    claim_coverage_report: dict[str, Any] | None,
    config_readiness_summary: dict[str, Any] | None,
) -> int:
    if isinstance(claim_coverage_report, dict):
        summary = claim_coverage_report.get("summary", {})
        uncovered_cards = claim_coverage_report.get("uncovered_cards", [])
        if (isinstance(summary, dict) and "uncovered_low_confidence" in summary) or (
            isinstance(uncovered_cards, list) and uncovered_cards
        ):
            return _uncovered_card_count(claim_coverage_report)
    if isinstance(config_readiness_summary, dict):
        return _first_present_int(config_readiness_summary, "uncovered_cards")
    return _uncovered_card_count(claim_coverage_report or {})


def _max_present_int(summary: dict[str, Any], *keys: str) -> int:
    return max((_int_value(summary.get(key, 0)) for key in keys if key in summary), default=0)


def _first_present_int(summary: dict[str, Any], *keys: str) -> int:
    for key in keys:
        if key in summary:
            return _int_value(summary.get(key, 0))
    return 0


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
    return "READY_TO_APPLY_WITH_WARNINGS", "ALLOWED_WITH_WARNINGS"


def _runtime_apply_contract(
    *,
    technical_status: str,
    apply_policy: str,
) -> tuple[str, bool, str | None]:
    if technical_status == "VALID_PACKAGE" and apply_policy != "BLOCKED":
        return "load_safe_apply", True, None
    return "blocked", False, None

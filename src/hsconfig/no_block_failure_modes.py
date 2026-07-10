from __future__ import annotations

from typing import Any


def build_no_block_failure_mode_summary(
    *,
    technical_status: str,
    runtime_apply_mode: str,
    runtime_apply_allowed: bool,
    next_action: str,
    apply_policy: str,
    primary_blockers: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    semantic_status: str,
    semantic_blockers: list[dict[str, Any]],
    guide_strength_summary: dict[str, Any],
    config_usefulness: dict[str, Any],
    mechanic_visibility_summary: dict[str, Any],
    mechanic_drift_summary: dict[str, Any],
    source_informed_apply_readiness: dict[str, Any],
) -> dict[str, Any]:
    categories = {
        "technical_hard_block": _technical_hard_blocks(primary_blockers),
        "source_depth_warning": _source_depth_warnings(semantic_blockers),
        "warning_only_mechanic": _warning_only_mechanics(mechanic_visibility_summary),
        "future_mechanic_drift": _future_mechanic_drift(mechanic_drift_summary),
        "guide_strength_gap": _guide_strength_gaps(
            semantic_status=semantic_status,
            guide_strength_summary=guide_strength_summary,
            warnings=warnings,
            config_usefulness=config_usefulness,
            source_informed_apply_readiness=source_informed_apply_readiness,
        ),
        "combo_uncertainty": _combo_uncertainty(semantic_blockers),
        "runtime_evidence_only_tuning": _runtime_evidence_warnings(warnings),
    }
    hard_block = bool(categories["technical_hard_block"]) or technical_status != "VALID_PACKAGE"
    if hard_block:
        overall = "technical_hard_block"
        operator_message = (
            "Package is not load-safe. Fix technical_hard_block items before hsconfig apply."
        )
    elif runtime_apply_allowed and runtime_apply_mode == "load_safe_apply":
        has_warnings = any(
            categories[name] for name in categories if name != "technical_hard_block"
        )
        overall = (
            "load_safe_apply_allowed_with_warnings"
            if has_warnings
            else "load_safe_apply_allowed"
        )
        operator_message = (
            "Package is load-safe. Listed warnings explain source or mechanic limits; "
            "they do not block hsconfig apply."
        )
    else:
        overall = "runtime_apply_not_allowed"
        operator_message = "Package is not currently allowed to write runtime files."

    return {
        "schema_version": 1,
        "overall": overall,
        "hard_block": hard_block,
        "runtime_apply_allowed": bool(runtime_apply_allowed),
        "runtime_apply_mode": runtime_apply_mode,
        "next_action": next_action,
        "apply_policy": apply_policy,
        "operator_message": operator_message,
        "categories": categories,
        "first_non_blocking_followup": _first_non_blocking_followup(categories),
    }


def _technical_hard_blocks(primary_blockers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for blocker in primary_blockers:
        if not isinstance(blocker, dict):
            continue
        reason = str(blocker.get("reason", "")).strip()
        if reason:
            rows.append({"reason": reason})
    return rows


def _source_depth_warnings(semantic_blockers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for blocker in semantic_blockers:
        if not isinstance(blocker, dict):
            continue
        reason = str(blocker.get("reason", "")).strip()
        if not reason:
            continue
        rows.append(
            {
                "reason": reason,
                "count": _int_value(blocker.get("count", 0)),
                "blocking_strength": str(blocker.get("blocking_strength", "")),
                "report": str(blocker.get("report", "")),
            }
        )
    return rows


def _warning_only_mechanics(
    mechanic_visibility_summary: dict[str, Any],
) -> list[dict[str, Any]]:
    mechanics_by_bucket = mechanic_visibility_summary.get("mechanics_by_bucket", {})
    if not isinstance(mechanics_by_bucket, dict):
        return []
    warning_only = mechanics_by_bucket.get("warning_only", [])
    if not isinstance(warning_only, list):
        return []
    return [{"mechanic": str(mechanic)} for mechanic in warning_only]


def _future_mechanic_drift(
    mechanic_drift_summary: dict[str, Any],
) -> list[dict[str, Any]]:
    rows = []
    for key, kind in (
        ("unknown_mechanics", "unknown_mechanic"),
        ("text_only_mechanics", "text_only_mechanic"),
        ("unknown_card_types", "unknown_card_type"),
    ):
        values = mechanic_drift_summary.get(key, [])
        if not isinstance(values, list):
            continue
        rows.extend({"kind": kind, "value": str(value)} for value in values)
    return rows


def _guide_strength_gaps(
    *,
    semantic_status: str,
    guide_strength_summary: dict[str, Any],
    warnings: list[dict[str, Any]],
    config_usefulness: dict[str, Any],
    source_informed_apply_readiness: dict[str, Any],
) -> list[dict[str, Any]]:
    rows = []
    if semantic_status in {
        "VALID_BUT_NOT_GUIDE_STRONG",
        "STATIC_SEMANTICS_USABLE",
        "NEEDS_MORE_RESEARCH",
    }:
        rows.append({"reason": semantic_status.lower()})
    for key in (
        "generic_low_confidence_cards",
        "uncovered_cards",
        "source_evidence_warnings",
        "claim_conflicts",
        "cards_needing_guide_claims",
        "cards_needing_mulligan_claims",
    ):
        count = _int_value(guide_strength_summary.get(key, 0))
        if count:
            rows.append({"reason": key, "count": count})
    status = str(config_usefulness.get("status", ""))
    if status in {"load_safe_but_thin", "usable_with_targeted_gaps"}:
        rows.append(
            {
                "reason": "config_usefulness_gap",
                "status": status,
                "first_gap": str(config_usefulness.get("first_gap", "")),
                "next_report_to_open": str(
                    config_usefulness.get("next_report_to_open", "")
                ),
            }
        )
    blocking_reasons = source_informed_apply_readiness.get("blocking_reasons", [])
    if isinstance(blocking_reasons, list):
        for reason in blocking_reasons:
            rows.append({"reason": "source_informed_apply_gap", "value": str(reason)})
    for warning in warnings:
        if not isinstance(warning, dict):
            continue
        reason = str(warning.get("reason", ""))
        if reason in {
            "static_semantics_only",
            "needs_more_research",
            "valid_but_not_guide_strong",
            "cards_still_low_confidence",
        }:
            rows.append(
                {"reason": reason, "count": _int_value(warning.get("card_count", 0))}
            )
    return _dedupe_rows(rows)


def _combo_uncertainty(semantic_blockers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for blocker in semantic_blockers:
        if not isinstance(blocker, dict):
            continue
        if str(blocker.get("reason", "")) != "cards_need_combo_sequence":
            continue
        rows.append(
            {
                "reason": "cards_need_combo_sequence",
                "count": _int_value(blocker.get("count", 0)),
            }
        )
    return rows


def _runtime_evidence_warnings(warnings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for warning in warnings:
        if not isinstance(warning, dict):
            continue
        if str(warning.get("reason", "")) != "globalvalue_runtime_evidence_required":
            continue
        rows.append(
            {
                "reason": "globalvalue_runtime_evidence_required",
                "key": str(warning.get("key", "")),
            }
        )
    return rows


def _first_non_blocking_followup(
    categories: dict[str, list[dict[str, Any]]],
) -> dict[str, Any] | None:
    for category in (
        "source_depth_warning",
        "warning_only_mechanic",
        "future_mechanic_drift",
        "guide_strength_gap",
        "combo_uncertainty",
        "runtime_evidence_only_tuning",
    ):
        rows = categories.get(category, [])
        if rows:
            return {"category": category, "item": rows[0]}
    return None


def _dedupe_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    result = []
    for row in rows:
        key = tuple(sorted((str(key), str(value)) for key, value in row.items()))
        if key in seen:
            continue
        seen.add(key)
        result.append(row)
    return result


def _int_value(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0

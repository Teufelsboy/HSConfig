from __future__ import annotations

from collections import Counter
from typing import Any


def _closure_priority(row: dict[str, Any]) -> int:
    visibility = row.get("strongness_visibility", {})
    if not isinstance(visibility, dict):
        return 0
    try:
        return int(visibility.get("closure_priority", 0))
    except (TypeError, ValueError):
        return 0


def _source_informed_closure_sequence(rows: list[dict[str, Any]]) -> list[str]:
    targets = [
        row
        for row in rows
        if isinstance(row, dict)
        and row.get("fixture_stage") == "source_informed_valid_fixture"
        and _closure_priority(row) > 0
    ]
    targets.sort(key=lambda row: (_closure_priority(row), str(row.get("deck_name", ""))))
    return [str(row["deck_name"]) for row in targets if row.get("deck_name")]


def _has_durable_preservation_stop(row: dict[str, Any]) -> bool:
    visibility = row.get("strongness_visibility", {})
    if not isinstance(visibility, dict):
        return False
    return (
        visibility.get("operator_action")
        == "preserve_source_informed_with_explicit_stop_condition"
        and isinstance(visibility.get("stop_condition"), str)
        and bool(visibility.get("stop_condition"))
    )


def _preserved_source_informed_targets(rows: list[dict[str, Any]]) -> list[str]:
    preserved = [
        row
        for row in rows
        if isinstance(row, dict)
        and row.get("fixture_stage") == "source_informed_valid_fixture"
        and _has_durable_preservation_stop(row)
    ]
    preserved.sort(
        key=lambda row: (_closure_priority(row), str(row.get("deck_name", "")))
    )
    return [str(row["deck_name"]) for row in preserved if row.get("deck_name")]


def _next_actionable_closure_target(rows: list[dict[str, Any]]) -> str | None:
    targets = [
        row
        for row in rows
        if isinstance(row, dict)
        and row.get("fixture_stage") == "source_informed_valid_fixture"
        and _closure_priority(row) > 0
    ]
    targets.sort(key=lambda row: (_closure_priority(row), str(row.get("deck_name", ""))))
    for row in targets:
        if _has_durable_preservation_stop(row):
            continue
        deck_name = row.get("deck_name")
        if deck_name:
            return str(deck_name)
    return None


def build_source_depth_closure_index(
    matrix: dict[str, Any],
    deck_reports: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    rows = matrix.get("decks", [])
    if not isinstance(rows, list):
        rows = []
    closure_sequence = _source_informed_closure_sequence(rows)
    preserved_targets = _preserved_source_informed_targets(rows)
    next_actionable_target = _next_actionable_closure_target(rows)

    summary: Counter[str] = Counter()
    decks: dict[str, dict[str, Any]] = {}

    for row in rows:
        if not isinstance(row, dict):
            continue

        deck_name = str(row.get("deck_name", ""))
        fixture_stage = str(row.get("fixture_stage", ""))
        visibility = row.get("strongness_visibility", {})
        if not isinstance(visibility, dict):
            visibility = {}
        blocking_reasons = visibility.get("source_informed_blocking_reasons", [])
        if not isinstance(blocking_reasons, list):
            blocking_reasons = []
        blocking_reasons = [str(reason) for reason in blocking_reasons]
        explicit_stop_condition = visibility.get("stop_condition")
        if not isinstance(explicit_stop_condition, str):
            explicit_stop_condition = None

        reports = deck_reports.get(deck_name, {})
        operator = reports.get("operator_summary", {}) if isinstance(reports, dict) else {}
        gap_report = reports.get("source_claim_gap_report", {}) if isinstance(reports, dict) else {}
        promotion = reports.get("strong_promotion_report", {}) if isinstance(reports, dict) else {}

        summary[fixture_stage] += 1
        first_missing_chain = _first_missing_chain(gap_report)
        promotion_ready = promotion.get("promotion_ready") is True
        closure_decision = _closure_decision(
            fixture_stage=fixture_stage,
            promotion_ready=promotion_ready,
            blocking_reasons=blocking_reasons,
        )
        if promotion_ready:
            summary["promotion_ready"] += 1
        else:
            summary["promotion_blocked"] += 1

        report_status = "available" if reports else "missing_reports"
        decks[deck_name] = {
            "deck_name": deck_name,
            "fixture_stage": fixture_stage,
            "report_status": report_status,
            "technical_status": operator.get("technical_status"),
            "semantic_status": operator.get("semantic_status"),
            "first_matrix_gap": str(visibility.get("first_strongness_gap", "")),
            "source_informed_blocking_reasons": blocking_reasons,
            "closure_blocker_stack": blocking_reasons,
            "first_blocking_reason": blocking_reasons[0] if blocking_reasons else None,
            "promotion_ready": promotion_ready,
            "first_missing_chain": first_missing_chain,
            "closure_decision": closure_decision,
            "preserve_reason": _preserve_reason(closure_decision),
            "stop_condition": _stop_condition(
                closure_decision=closure_decision,
                blocking_reasons=blocking_reasons,
                explicit_stop_condition=explicit_stop_condition,
            ),
            "stop_condition_reason": _preserve_reason(closure_decision),
            "recommended_next_target": _recommended_next_target(
                deck_name=deck_name,
                fixture_stage=fixture_stage,
                blocking_reasons=blocking_reasons,
                visibility=visibility,
            ),
            "next_action": _next_action(
                fixture_stage=fixture_stage,
                report_status=report_status,
                promotion_ready=promotion_ready,
                first_missing_chain=first_missing_chain,
            ),
        }

    return {
        "schema_version": 1,
        "summary": {
            "total_decks": len(decks),
            "core_source_backed_fixture": summary["core_source_backed_fixture"],
            "source_informed_valid_fixture": summary["source_informed_valid_fixture"],
            "promotion_ready": summary["promotion_ready"],
            "promotion_blocked": summary["promotion_blocked"],
            "next_closure_target": closure_sequence[0] if closure_sequence else None,
            "next_actionable_closure_target": next_actionable_target,
            "closure_sequence": closure_sequence,
            "preserved_source_informed_targets": preserved_targets,
        },
        "decks": decks,
    }


def _first_missing_chain(gap_report: Any) -> dict[str, Any] | None:
    if not isinstance(gap_report, dict):
        return None
    summary = gap_report.get("summary", {})
    if not isinstance(summary, dict):
        return None
    first_missing_chain = summary.get("first_missing_chain")
    return first_missing_chain if isinstance(first_missing_chain, dict) else None


def _next_action(
    *,
    fixture_stage: str,
    report_status: str,
    promotion_ready: bool,
    first_missing_chain: dict[str, Any] | None,
) -> str:
    if report_status == "missing_reports":
        return "run_prepare_fixture_and_collect_reports"
    if promotion_ready and fixture_stage == "core_source_backed_fixture":
        return "keep_as_core_control_fixture"
    if promotion_ready:
        return "promote_fixture_row_to_core_source_backed"
    if first_missing_chain is not None:
        return "close_first_missing_chain"
    return "inspect_operator_summary_and_gap_reports"


def _closure_decision(
    *,
    fixture_stage: str,
    promotion_ready: bool,
    blocking_reasons: list[str],
) -> str:
    if promotion_ready:
        return "promote_or_keep_core"
    if fixture_stage == "source_informed_valid_fixture" and blocking_reasons:
        return "preserve_source_informed_until_blockers_close"
    if fixture_stage == "source_informed_valid_fixture":
        return "close_first_missing_chain"
    return "inspect_reports"


def _preserve_reason(closure_decision: str) -> str | None:
    if closure_decision == "preserve_source_informed_until_blockers_close":
        return "source-informed row has hard blockers and cannot be promoted or applied as strong"
    return None


def _stop_condition(
    *,
    closure_decision: str,
    blocking_reasons: list[str],
    explicit_stop_condition: str | None,
) -> str | None:
    if closure_decision != "preserve_source_informed_until_blockers_close":
        return None
    if explicit_stop_condition:
        return explicit_stop_condition
    if blocking_reasons:
        return "exact_source_or_lowering_gap_still_open"
    return "first_missing_chain_still_open"


def _recommended_next_target(
    *,
    deck_name: str,
    fixture_stage: str,
    blocking_reasons: list[str],
    visibility: dict[str, Any],
) -> str | None:
    if fixture_stage != "source_informed_valid_fixture" or not blocking_reasons:
        return None
    try:
        priority = int(visibility.get("closure_priority", 0))
    except (TypeError, ValueError):
        priority = 0
    return deck_name if priority == 1 else None

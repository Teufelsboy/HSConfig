from __future__ import annotations

from collections import Counter
from typing import Any


def build_source_depth_closure_index(
    matrix: dict[str, Any],
    deck_reports: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    rows = matrix.get("decks", [])
    if not isinstance(rows, list):
        rows = []

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
            "first_blocking_reason": blocking_reasons[0] if blocking_reasons else None,
            "promotion_ready": promotion_ready,
            "first_missing_chain": first_missing_chain,
            "closure_decision": closure_decision,
            "preserve_reason": _preserve_reason(closure_decision),
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

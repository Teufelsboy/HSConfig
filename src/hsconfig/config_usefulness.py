from __future__ import annotations

from typing import Any


GAP_REPORTS = {
    "mulligan_gap": "reports/mulligan_plan_report.json",
    "runtime_surface_gap": "reports/per_card_config_readiness_report.json",
    "combo_gap": "reports/combo_plan_report.json",
    "condition_gap": "reports/per_card_config_readiness_report.json",
    "mechanic_gap": "reports/per_card_config_readiness_report.json",
    "guide_claim_gap": "reports/source_claim_gap_report.json",
    "globalvalues_thin": "reports/global_values_key_profile_report.json",
    "cardid_thin": "reports/card_behavior_plan_report.json",
}


def build_config_usefulness(
    *,
    technical_status: str,
    semantic_status: str,
    config_readiness_summary: dict[str, Any] | None,
    config_readiness_report: dict[str, Any] | None = None,
    mulligan_plan_report: dict[str, Any] | None = None,
    card_behavior_plan_report: dict[str, Any] | None = None,
    combo_plan_report: dict[str, Any] | None = None,
    globalvalues_profile_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    summary = config_readiness_summary or {}
    if technical_status != "VALID_PACKAGE":
        return {
            "schema_version": 1,
            "status": "invalid_package",
            "headline": "Package is technically invalid; config richness is not evaluated.",
            "runtime_permission_impact": "none",
            "blocking": False,
            "surfaces": {},
            "first_usefulness_gap": "technical_invalid",
            "next_report_to_open": "reports/validation_report.json",
        }

    mulligan = _mulligan_surface(mulligan_plan_report or {})
    cardid = _cardid_surface(card_behavior_plan_report or {}, summary)
    combo = _combo_surface(combo_plan_report or {}, summary)
    globalvalues = _globalvalues_surface(globalvalues_profile_report or {})
    first_gap = _first_gap(summary, mulligan, cardid, combo, globalvalues)
    status = _overall_status(
        semantic_status=semantic_status,
        first_gap=first_gap,
        summary=summary,
        mulligan=mulligan,
        cardid=cardid,
        combo=combo,
        globalvalues=globalvalues,
    )

    return {
        "schema_version": 1,
        "status": status,
        "headline": _headline(status, first_gap),
        "runtime_permission_impact": "none",
        "blocking": False,
        "surfaces": {
            "mulligan": mulligan,
            "globalvalues": globalvalues,
            "cardid_behavior": cardid,
            "combo": combo,
        },
        "first_usefulness_gap": first_gap,
        "next_report_to_open": GAP_REPORTS.get(first_gap, "reports/operator_summary.json"),
    }


def _mulligan_surface(report: dict[str, Any]) -> dict[str, Any]:
    rules = _list(report.get("rules"))
    suppressed = _list(report.get("suppressed_rules"))
    quality = report.get("quality", {})
    has_concrete_keeps = bool(quality.get("has_concrete_keeps")) if isinstance(quality, dict) else False
    quality_status = str(quality.get("status", "")).strip() if isinstance(quality, dict) else ""
    concrete_runtime_rules = [
        row
        for row in rules
        if isinstance(row, dict)
        and (row.get("selector_kind") != "wildcard" or row.get("action") != "discard")
    ]
    default_only = not concrete_runtime_rules and not has_concrete_keeps
    if quality_status in {"rich", "policy_backed", "thin"}:
        status = quality_status
    elif has_concrete_keeps or rules:
        status = "rich"
    elif suppressed:
        status = "report_only"
    else:
        status = "thin"
    first_gap_reason = (
        str(quality.get("first_gap_reason", "none"))
        if isinstance(quality, dict)
        else "none"
    )
    suppressed_reasons = (
        dict(quality.get("suppressed_reasons", {}))
        if isinstance(quality, dict) and isinstance(quality.get("suppressed_reasons"), dict)
        else {}
    )
    policy_backed_rule_count = (
        _int(quality.get("policy_backed_rule_count", 0))
        if isinstance(quality, dict)
        else 0
    )
    policy_backed_keep_rule_count = (
        _int(quality.get("policy_backed_keep_rule_count", 0))
        if isinstance(quality, dict)
        else 0
    )
    policy_lanes = (
        _string_list(quality.get("policy_lanes"))
        if isinstance(quality, dict)
        else []
    )
    policy_reasons = (
        _string_list(quality.get("policy_reasons"))
        if isinstance(quality, dict)
        else []
    )
    return {
        "status": status,
        "rule_count": len(rules),
        "suppressed_rule_count": len(suppressed),
        "has_concrete_keeps": has_concrete_keeps,
        "default_only": default_only,
        "first_gap_reason": first_gap_reason,
        "next_source_need": (
            "none"
            if status in {"rich", "policy_backed"}
            else "source_backed_or_policy_backed_mulligan_keeps"
        ),
        "source_backed_rule_count": _int(quality.get("source_backed_rule_count", 0))
        if isinstance(quality, dict)
        else 0,
        "policy_backed_rule_count": policy_backed_rule_count,
        "policy_backed_keep_rule_count": policy_backed_keep_rule_count,
        "policy_lanes": policy_lanes,
        "policy_reasons": policy_reasons,
        "suppressed_reasons": suppressed_reasons,
    }


def _cardid_surface(report: dict[str, Any], summary: dict[str, Any]) -> dict[str, Any]:
    rows = _list(report.get("rows"))
    meaningful_rows = [
        row
        for row in rows
        if isinstance(row, dict)
        and row.get("meaningful_runtime_surface") is True
        and bool(row.get("behavior_block"))
    ]
    cards = sorted({str(row.get("card_id")) for row in meaningful_rows if row.get("card_id")})
    report_only_supported = _int(summary.get("report_only_supported"))
    runtime_emitted = _int(summary.get("runtime_emitted"))
    if meaningful_rows:
        status = "rich"
    elif report_only_supported > 0:
        status = "report_only"
    else:
        status = "thin"
    return {
        "status": status,
        "meaningful_cardid_row_count": len(meaningful_rows),
        "cards_with_meaningful_cardid_rows": len(cards),
        "runtime_emitted_card_count": runtime_emitted,
        "report_only_supported_count": report_only_supported,
    }


def _combo_surface(report: dict[str, Any], summary: dict[str, Any]) -> dict[str, Any]:
    combos = _list(report.get("combos"))
    suppressed = _list(report.get("suppressed"))
    gap_count = _int(summary.get("cards_needing_combo_sequence"))
    combo_expected = bool(combos or suppressed or gap_count)
    if combos:
        status = "rich"
    elif not combo_expected:
        status = "not_expected"
    elif suppressed:
        status = "report_only"
    else:
        status = "thin"
    return {
        "status": status,
        "combo_expected": combo_expected,
        "combo_row_count": len(combos),
        "suppressed_combo_claim_count": len(suppressed),
    }


def _globalvalues_surface(report: dict[str, Any]) -> dict[str, Any]:
    changed_keys = _list(report.get("changed_keys"))
    unchanged_keys = _list(report.get("unchanged_keys"))
    profiled_key_count = len(changed_keys) + len(unchanged_keys)
    return {
        "status": "rich" if changed_keys else "thin",
        "changed_key_count": len(changed_keys),
        "unchanged_key_count": len(unchanged_keys),
        "profiled_key_count": profiled_key_count,
    }


def _first_gap(
    summary: dict[str, Any],
    mulligan: dict[str, Any],
    cardid: dict[str, Any],
    combo: dict[str, Any],
    globalvalues: dict[str, Any],
) -> str:
    if _int(summary.get("cards_needing_runtime_surface")):
        return "runtime_surface_gap"
    if _int(summary.get("cards_needing_combo_sequence")) or combo["status"] in {"thin", "report_only"} and combo["combo_expected"]:
        return "combo_gap"
    if _int(summary.get("cards_needing_condition_lowering")):
        return "condition_gap"
    if _int(summary.get("cards_needing_mechanic_lowering")):
        return "mechanic_gap"
    if _int(summary.get("cards_needing_mulligan_claims")) and mulligan["status"] != "policy_backed":
        return "mulligan_gap"
    if mulligan["status"] in {"thin", "report_only"}:
        return "mulligan_gap"
    if _int(summary.get("cards_needing_guide_claims")) or _int(summary.get("generic_low_confidence")):
        return "guide_claim_gap"
    if cardid["status"] in {"thin", "report_only"} and _int(summary.get("runtime_emitted")) == 0:
        return "cardid_thin"
    if globalvalues["status"] == "thin":
        return "globalvalues_thin"
    return "none"


def _overall_status(
    *,
    semantic_status: str,
    first_gap: str,
    summary: dict[str, Any],
    mulligan: dict[str, Any],
    cardid: dict[str, Any],
    combo: dict[str, Any],
    globalvalues: dict[str, Any],
) -> str:
    if first_gap == "none" and semantic_status == "SOURCE_BACKED_STRONG":
        return "guide_aligned"
    severe_sparse = (
        _int(summary.get("runtime_emitted")) <= 1
        and mulligan["status"] == "thin"
        and cardid["status"] in {"thin", "report_only"}
        and globalvalues["status"] == "thin"
    )
    if severe_sparse:
        return "load_safe_but_thin"
    return "usable_with_targeted_gaps"


def _headline(status: str, first_gap: str) -> str:
    if status == "guide_aligned":
        return "Package is load-safe and config-rich across the visible pre-run surfaces."
    if status == "usable_with_targeted_gaps":
        return f"Package is load-safe and usable, with the first usefulness gap at {first_gap}."
    if status == "load_safe_but_thin":
        return f"Package is load-safe, but config richness is thin; first gap is {first_gap}."
    return "Package richness status is unavailable."


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item)]

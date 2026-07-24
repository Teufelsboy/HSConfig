from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

_AUTHORITY = "diagnostic_source_readiness_preview"
_NORMAL_APPLY_AUTHORITY = "reports/operator_summary.json"


def build_source_readiness_preview(
    *,
    source_candidate_plan: Mapping[str, Any] | None = None,
    source_autopilot_report: Mapping[str, Any] | None = None,
    operator_summary: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    candidate = _mapping(source_candidate_plan)
    autopilot = _mapping(source_autopilot_report)
    operator = _mapping(operator_summary)
    strong_summary = _mapping(autopilot.get("strong_closure_summary"))
    strong_closure = _mapping(autopilot.get("source_backed_strong_closure"))
    target_summary = _mapping(candidate.get("target_summary"))
    runtime_contract = _mapping(operator.get("runtime_apply_contract"))

    semantic_status = _text(
        operator.get("semantic_status")
        or operator.get("source_backed_status")
        or autopilot.get("semantic_status")
        or strong_summary.get("semantic_status")
    )
    source_backed_strong_ready = bool(
        strong_summary.get("source_backed_strong_ready")
        or strong_closure.get("promotion_ready")
        or semantic_status == "SOURCE_BACKED_STRONG"
    )
    strong_candidate = bool(
        autopilot.get("strong_candidate")
        or strong_summary.get("strong_candidate")
        or source_backed_strong_ready
    )
    first_missing_source_action = _first_action(
        operator,
        strong_summary,
        strong_closure,
        autopilot,
        candidate,
        source_backed_strong_ready=source_backed_strong_ready,
    )
    card_rows = _mapping_rows(autopilot.get("card_rows"))
    surface_rows = _mapping_rows(autopilot.get("surface_rows"))
    default_only_runtime_surfaces = _text_list(
        operator.get("default_only_runtime_surfaces")
    )
    readiness_lane = _readiness_lane(
        source_backed_strong_ready=source_backed_strong_ready,
        autopilot_present=bool(autopilot),
        candidate_present=bool(candidate),
    )

    return {
        "schema_version": 1,
        "authority": _AUTHORITY,
        "diagnostic_only": True,
        "runtime_apply_authority": _text(
            runtime_contract.get("apply_authority") or _NORMAL_APPLY_AUTHORITY
        ),
        "apply_blocking": False,
        "runtime_write_performed": False,
        "source_status_apply_blocking": False,
        "source_candidate_plan_present": bool(candidate),
        "source_autopilot_report_present": bool(autopilot),
        "operator_summary_present": bool(operator),
        "semantic_status": semantic_status,
        "source_backed_strong_ready": source_backed_strong_ready,
        "strong_candidate": strong_candidate,
        "readiness_lane": readiness_lane,
        "first_missing_source_action": first_missing_source_action,
        "recommended_next_source_action": first_missing_source_action,
        "candidate_source_url_count": len(_text_list(candidate.get("source_urls"))),
        "strong_evidence_row_count": _int(
            strong_summary.get("strong_evidence_row_count")
        ),
        "card_target_count": _int(target_summary.get("card_targets")),
        "mulligan_keep_source_target_count": _int(
            target_summary.get("mulligan_keep_source_targets")
        ),
        "effect_semantics_not_mulligan_keep_target_count": _int(
            target_summary.get("effect_semantics_not_mulligan_keep_targets")
        ),
        "card_source_gap_count": _lane_count(card_rows, "source_gap"),
        "surface_source_gap_count": _lane_count(surface_rows, "source_gap"),
        "default_only_clean": not default_only_runtime_surfaces,
        "default_only_runtime_surfaces": default_only_runtime_surfaces,
        "runtime_apply_allowed": bool(operator.get("runtime_apply_allowed", False)),
        "runtime_apply_mode": _text(operator.get("runtime_apply_mode")),
        "readiness_summary": _readiness_summary(
            readiness_lane,
            first_missing_source_action,
        ),
    }


def _first_action(
    *sources: Mapping[str, Any],
    source_backed_strong_ready: bool,
) -> str:
    if source_backed_strong_ready:
        return "none"
    for source in sources:
        value = _text(source.get("first_missing_source_action"))
        if value and value != "none":
            return value
    return "add_public_guide_url_or_use_static_semantics"


def _readiness_lane(
    *,
    source_backed_strong_ready: bool,
    autopilot_present: bool,
    candidate_present: bool,
) -> str:
    if source_backed_strong_ready:
        return "source_backed_strong_ready"
    if autopilot_present:
        return "source_partial_no_block"
    if candidate_present:
        return "acquisition_plan_ready_no_block"
    return "source_context_missing_no_block"


def _readiness_summary(readiness_lane: str, first_missing_source_action: str) -> str:
    if readiness_lane == "source_backed_strong_ready":
        return "source-backed strong; no source action required"
    return f"{readiness_lane}; next source action: {first_missing_source_action}"


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _mapping_rows(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    return [dict(row) for row in value if isinstance(row, Mapping)]


def _text_list(value: Any) -> list[str]:
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if not isinstance(value, Sequence):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _lane_count(rows: Sequence[Mapping[str, Any]], lane: str) -> int:
    return sum(1 for row in rows if _text(row.get("lane")) == lane)


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return str(value or "").strip()

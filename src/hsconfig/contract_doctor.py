from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

from hsconfig.config_quality_contract import build_config_quality_report
from hsconfig.source_contract_conformance import build_source_contract_conformance_snapshot


def build_contract_doctor_report(package: Path) -> dict[str, Any]:
    """Build a read-only source-contract diagnostic for a prepared package."""
    package = Path(package)
    operator_path = package / "reports" / "operator_summary.json"
    authority = {
        "apply_authority": "reports/operator_summary.json",
        "diagnostic_only": True,
        "runtime_write_performed": False,
        "note": "contract-doctor explains existing reports; it does not grant apply permission",
    }
    if not operator_path.is_file():
        return {
            "schema_version": 1,
            "status": "failed",
            "errors": ["missing reports/operator_summary.json"],
            "package": str(package),
            "authority": authority,
        }

    operator = _read_json(operator_path)
    if not isinstance(operator, Mapping):
        return {
            "schema_version": 1,
            "status": "failed",
            "errors": ["invalid reports/operator_summary.json"],
            "package": str(package),
            "authority": authority,
        }

    config_quality = build_config_quality_report(package)
    audit_path = package / "reports" / "source_contract_audit.json"
    audit = _read_json(audit_path) if audit_path.is_file() else {}
    if not isinstance(audit, Mapping):
        audit = {}

    lifecycle_rows = audit.get("claim_lifecycle_rows", [])
    if not isinstance(lifecycle_rows, list):
        lifecycle_rows = []
    lifecycle_rows = [row for row in lifecycle_rows if isinstance(row, Mapping)]
    claim_rows = [_claim_lifecycle_row(row) for row in lifecycle_rows]
    missing_links = Counter(row["first_missing_link"] for row in claim_rows)
    runtime_surfaces = Counter(
        row["runtime_surface"]
        for row in claim_rows
    )
    card_diagnostics = _card_diagnostics(audit.get("card_rows", {}))

    conformance = build_source_contract_conformance_snapshot()
    summary = conformance.get("summary", {}) if isinstance(conformance, Mapping) else {}
    contract_spine = _contract_spine_summary(conformance)

    return {
        "schema_version": 1,
        "status": "ok",
        "errors": [],
        "package": str(package),
        "authority": authority,
        "config_quality": config_quality,
        "operator": {
            "technical_status": operator.get("technical_status"),
            "semantic_status": operator.get("semantic_status"),
            "next_action": operator.get("next_action"),
            "first_report_to_open": "reports/operator_summary.json",
        },
        "source_contract_audit": {
            "present": bool(audit),
            "summary": audit.get("summary", {}),
            "next_report_to_open": "reports/source_contract_audit.json" if audit else None,
        },
        "claim_lifecycle": {
            "total": len(lifecycle_rows),
            "first_missing_links": dict(sorted(missing_links.items())),
            "runtime_surfaces": dict(sorted(runtime_surfaces.items())),
            "rows": claim_rows,
        },
        "card_diagnostics": card_diagnostics,
        "contract_spine": contract_spine,
        "conformance": {
            "operator_gate_impact": conformance.get("operator_gate_impact"),
            "unexpected_contract_drift_count": summary.get(
                "unexpected_contract_drift_count"
            ),
            "builder_prerequisite_gap_count": summary.get(
                "builder_prerequisite_gap_count"
            ),
            "pipeline_attention_count": summary.get("pipeline_attention_count"),
        },
    }


def render_contract_doctor_markdown(report: Mapping[str, Any]) -> str:
    """Render the contract-doctor result as compact operator-readable Markdown."""
    authority = _mapping(report.get("authority"))
    config_quality = _mapping(report.get("config_quality"))
    config_quality_checks = _mapping(config_quality.get("checks"))
    trace_quality = _mapping(config_quality_checks.get("trace_completeness"))
    closure_quality = _mapping(config_quality_checks.get("closure_freshness"))
    runtime_quality = _mapping(config_quality_checks.get("runtime_json"))
    mechanic_quality = _mapping(
        config_quality_checks.get("mechanic_runtime_discipline")
    )
    operator = _mapping(report.get("operator"))
    lifecycle = _mapping(report.get("claim_lifecycle"))
    card_diagnostics = _mapping(report.get("card_diagnostics"))
    contract_spine = _mapping(report.get("contract_spine"))
    conformance = _mapping(report.get("conformance"))
    lines = [
        "# Contract Doctor",
        "",
        "Diagnostic only. operator_summary.json remains the only normal apply authority.",
        "",
        "## Status",
        "",
        f"- Status: {report.get('status', '')}",
        f"- Package: {report.get('package', '')}",
        f"- Apply authority: {authority.get('apply_authority', '')}",
        f"- Runtime write performed: {authority.get('runtime_write_performed', False)}",
        "",
        "## Operator Summary",
        "",
        f"- Technical status: {operator.get('technical_status', '')}",
        f"- Semantic status: {operator.get('semantic_status', '')}",
        f"- Next action: {operator.get('next_action', '')}",
        "",
        "## Config Quality",
        "",
        f"- Status: {config_quality.get('status', '')}",
        f"- Authority: {config_quality.get('authority', '')}",
        f"- Apply blocking: {config_quality.get('apply_blocking', False)}",
        f"- Problems: {config_quality.get('problems', [])}",
        f"- Trace rows missing source: {_count(trace_quality.get('runtime_rows_missing_trace'))}",
        f"- Closure current: {closure_quality.get('closure_schema_current', False)}",
        f"- Closure rows missing: {closure_quality.get('cards_missing_closure', 0)}",
        f"- Stray CardID files: {_count(runtime_quality.get('stray_cardid_files'))}",
        f"- Report-only mechanic runtime rows: {_count(mechanic_quality.get('report_only_runtime_rows'))}",
        "",
        "## Claim Lifecycle",
        "",
        f"- Rows: {lifecycle.get('total', 0)}",
        f"- First missing links: {lifecycle.get('first_missing_links', {})}",
        f"- Runtime surfaces: {lifecycle.get('runtime_surfaces', {})}",
        f"- Claim rows: {lifecycle.get('rows', [])}",
        "",
        "## Card Diagnostics",
        "",
        f"- Rows: {card_diagnostics.get('total', 0)}",
        f"- First missing links: {card_diagnostics.get('first_missing_links', {})}",
        f"- Cards with missing links: {card_diagnostics.get('cards_with_missing_links', [])}",
        "",
        "## Contract Spine",
        "",
        f"- Operator gate impact: {contract_spine.get('operator_gate_impact', '')}",
        f"- Claim kinds: {contract_spine.get('claim_kind_count', 0)}",
        f"- Policy lanes: {contract_spine.get('policy_lane_counts', {})}",
        f"- Unexpected contract drift: {contract_spine.get('unexpected_contract_drift_count', 0)}",
        f"- Builder prerequisite gaps: {contract_spine.get('builder_prerequisite_gap_count', 0)}",
        "",
        "## Conformance",
        "",
        f"- Operator gate impact: {conformance.get('operator_gate_impact', '')}",
        f"- Unexpected contract drift: {conformance.get('unexpected_contract_drift_count', '')}",
        f"- Builder prerequisite gaps: {conformance.get('builder_prerequisite_gap_count', '')}",
        f"- Pipeline attention rows: {conformance.get('pipeline_attention_count', '')}",
    ]
    return "\n".join(lines)


def _mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}


def _contract_spine_summary(conformance: Mapping[str, Any]) -> dict[str, Any]:
    summary = _mapping(conformance.get("summary"))
    rows = conformance.get("contract_spine_rows", [])
    if not isinstance(rows, list):
        rows = []
    claim_kinds = [
        str(row.get("claim_kind", ""))
        for row in rows
        if isinstance(row, Mapping) and str(row.get("claim_kind", ""))
    ]
    policy_lane_counts = summary.get("policy_lane_counts", {})
    if not isinstance(policy_lane_counts, Mapping):
        policy_lane_counts = {}
    return {
        "operator_gate_impact": str(
            conformance.get("operator_gate_impact", "diagnostic_only")
        ),
        "claim_kind_count": len(claim_kinds),
        "claim_kinds": sorted(claim_kinds),
        "policy_lane_counts": dict(policy_lane_counts),
        "unexpected_contract_drift_count": _int_value(
            summary.get("unexpected_contract_drift_count", 0)
        ),
        "builder_prerequisite_gap_count": _int_value(
            summary.get("builder_prerequisite_gap_count", 0)
        ),
        "pipeline_attention_count": _int_value(
            summary.get("pipeline_attention_count", 0)
        ),
    }


def _claim_lifecycle_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "claim_id": str(row.get("claim_id", "")),
        "claim_kind": str(row.get("claim_kind", "")),
        "policy_lane": str(row.get("policy_lane", "")),
        "surface_gate_decision": str(row.get("surface_gate_decision", "")),
        "surface_gate_reason": str(row.get("surface_gate_reason", "")),
        "builder_or_router_decision": str(row.get("builder_or_router_decision", "")),
        "runtime_surface": str(row.get("runtime_surface", "") or "none"),
        "first_missing_link": str(row.get("first_missing_link", "") or "none"),
    }


def _card_diagnostics(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {
            "total": 0,
            "first_missing_links": {},
            "cards_with_missing_links": [],
            "rows": [],
        }
    rows = []
    missing_links: Counter[str] = Counter()
    for card_id, raw_row in sorted(value.items()):
        if not isinstance(raw_row, Mapping):
            continue
        first_missing_link = str(raw_row.get("first_missing_link", "") or "none")
        row = {
            "card_id": str(card_id),
            "name": str(raw_row.get("name", "")),
            "readiness_lane": str(raw_row.get("readiness_lane", "")),
            "runtime_surfaces": _string_list(raw_row.get("runtime_surfaces", [])),
            "claim_lanes": dict(raw_row.get("claim_lanes", {}))
            if isinstance(raw_row.get("claim_lanes"), Mapping)
            else {},
            "first_missing_link": first_missing_link,
        }
        rows.append(row)
        missing_links[first_missing_link] += 1
    return {
        "total": len(rows),
        "first_missing_links": dict(sorted(missing_links.items())),
        "cards_with_missing_links": [
            row
            for row in rows
            if row["first_missing_link"].lower() not in {"", "none", "closed"}
        ],
        "rows": rows,
    }


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item)]


def _int_value(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _count(value: Any) -> int:
    if isinstance(value, list):
        return len(value)
    if isinstance(value, Mapping):
        return len(value)
    return 0


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

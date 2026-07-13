from __future__ import annotations

from pathlib import Path
from typing import Any

from hsconfig.source_contract_conformance import build_source_contract_conformance_snapshot
from hsconfig.source_contract_matrix import source_contract_policy_by_claim_kind
from hsconfig.source_document_model import SUPPORTED_ATOMIC_CLAIM_KINDS
from hsconfig.report_ownership import build_report_ownership


FORBIDDEN_APPLY_AUTHORITY_FIELDS = {
    "apply_allowed",
    "apply_gate",
    "apply_policy",
    "next_action",
    "runtime_apply_allowed",
    "runtime_apply_mode",
    "technical_status",
}

ACTIVE_APPLY_PATHS = (
    "src/hsconfig/apply_gate.py",
    "src/hsconfig/runtime_apply.py",
    "src/hsconfig/commands/apply.py",
)

DIAGNOSTIC_ONLY_TOKENS = (
    "source_contract_audit",
    "source_to_runtime_explainability",
    "source_contract_conformance",
    "contract_spine_rows",
    "claim_lifecycle_rows",
)

CRITICAL_CLAIM_KINDS = (
    "mulligan_keep",
    "hero_power_transform",
    "globalvalue_numeric_tuning",
    "combo_sequence",
    "archetype",
)


def build_contract_spine_sentinel_report(
    repo_root: str | Path | None = None,
) -> dict[str, Any]:
    """Return a read-only drift report for the source-contract spine.

    The sentinel is a developer diagnostic. It never grants or denies runtime
    apply permission; `reports/operator_summary.json` remains the apply authority.
    """
    root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[2]
    policy = source_contract_policy_by_claim_kind()
    conformance = build_source_contract_conformance_snapshot()
    spine_rows = conformance.get("contract_spine_rows", [])

    checks = {
        "supported_claim_kinds": sorted(SUPPORTED_ATOMIC_CLAIM_KINDS),
        "policy_missing_claim_kinds": _missing(SUPPORTED_ATOMIC_CLAIM_KINDS, policy),
        "policy_extra_claim_kinds": _extra(SUPPORTED_ATOMIC_CLAIM_KINDS, policy),
        "spine_missing_claim_kinds": _missing(
            SUPPORTED_ATOMIC_CLAIM_KINDS,
            {str(row.get("claim_kind")): row for row in spine_rows if isinstance(row, dict)},
        ),
        "spine_extra_claim_kinds": _extra(
            SUPPORTED_ATOMIC_CLAIM_KINDS,
            {str(row.get("claim_kind")): row for row in spine_rows if isinstance(row, dict)},
        ),
        "non_diagnostic_policy_claim_kinds": _non_diagnostic_policy_claim_kinds(policy),
        "spine_rows_with_apply_authority_fields": _spine_rows_with_apply_fields(spine_rows),
        "conformance_operator_gate_impact": conformance.get("operator_gate_impact"),
        "conformance_apply_authority_fields_present": sorted(
            FORBIDDEN_APPLY_AUTHORITY_FIELDS.intersection(conformance)
        ),
        "critical_boundary_rows": _critical_boundary_rows(spine_rows),
        "start_of_game_mulligan_suppression": conformance.get(
            "start_of_game_mulligan_suppression",
            {},
        ),
        "active_apply_diagnostic_consumers": _active_apply_diagnostic_consumers(root),
        "active_apply_paths_missing": _missing_active_apply_paths(root),
        "legacy_surface_normal_routing": _legacy_surface_normal_routing(root),
        "source_informed_apply_flag_policy": _source_informed_apply_flag_policy(root),
        "report_ownership_gate_files": _report_ownership_gate_files(),
        "report_ownership_unclassified_files": _report_ownership_unclassified_files(),
    }
    problems = _problems(checks)
    return {
        "schema_version": 1,
        "status": "clean" if not problems else "drift_detected",
        "authority": "diagnostic_only",
        "operator_gate_impact": "diagnostic_only",
        "apply_blocking": False,
        "checks": checks,
        "problems": problems,
    }


def _missing(expected: tuple[str, ...], actual: dict[str, object]) -> list[str]:
    return sorted(set(expected) - set(actual))


def _extra(expected: tuple[str, ...], actual: dict[str, object]) -> list[str]:
    return sorted(set(actual) - set(expected))


def _non_diagnostic_policy_claim_kinds(policy: dict[str, dict[str, Any]]) -> list[str]:
    return sorted(
        claim_kind
        for claim_kind, row in policy.items()
        if row.get("operator_gate_impact") != "diagnostic_only"
    )


def _spine_rows_with_apply_fields(spine_rows: object) -> list[dict[str, object]]:
    if not isinstance(spine_rows, list):
        return [{"claim_kind": "__invalid_spine_rows__", "fields": ["not_a_list"]}]
    flagged: list[dict[str, object]] = []
    for row in spine_rows:
        if not isinstance(row, dict):
            flagged.append({"claim_kind": "__invalid_row__", "fields": ["not_a_dict"]})
            continue
        fields = sorted(FORBIDDEN_APPLY_AUTHORITY_FIELDS.intersection(row))
        if fields:
            flagged.append({"claim_kind": row.get("claim_kind", ""), "fields": fields})
    return flagged


def _critical_boundary_rows(spine_rows: object) -> dict[str, dict[str, object]]:
    rows_by_kind = {
        str(row.get("claim_kind")): row
        for row in spine_rows
        if isinstance(row, dict)
    }
    return {
        claim_kind: {
            "policy_lane": rows_by_kind.get(claim_kind, {}).get("policy_lane"),
            "allowed_surfaces": rows_by_kind.get(claim_kind, {}).get("allowed_surfaces"),
            "surface_gate_status": rows_by_kind.get(claim_kind, {}).get("surface_gate_status"),
            "builder_status": rows_by_kind.get(claim_kind, {}).get("builder_status"),
            "final_runtime_effect": rows_by_kind.get(claim_kind, {}).get("final_runtime_effect"),
            "operator_gate_impact": rows_by_kind.get(claim_kind, {}).get("operator_gate_impact"),
        }
        for claim_kind in CRITICAL_CLAIM_KINDS
    }


def _active_apply_diagnostic_consumers(root: Path) -> list[dict[str, str]]:
    consumers: list[dict[str, str]] = []
    for relative_path in ACTIVE_APPLY_PATHS:
        path = root / relative_path
        if not path.exists():
            continue
        content = path.read_text(encoding="utf-8")
        for token in DIAGNOSTIC_ONLY_TOKENS:
            if token in content:
                consumers.append({"path": relative_path, "token": token})
    return consumers


def _missing_active_apply_paths(root: Path) -> list[str]:
    return [
        relative_path
        for relative_path in ACTIVE_APPLY_PATHS
        if not (root / relative_path).exists()
    ]


def _legacy_surface_normal_routing(root: Path) -> list[dict[str, str]]:
    path = root / "src/hsconfig/surface_intent.py"
    if not path.exists():
        return [{"path": "src/hsconfig/surface_intent.py", "reason": "missing"}]

    content = path.read_text(encoding="utf-8")
    flagged = []
    for token in (
        "legacy_policy_surfaces_enabled",
        'optional_surfaces.add("Presume.json")',
        'optional_surfaces.add("Concede.json")',
    ):
        if token in content:
            flagged.append({"path": "src/hsconfig/surface_intent.py", "token": token})
    return flagged


def _source_informed_apply_flag_policy(root: Path) -> dict[str, str]:
    apply_gate = root / "src/hsconfig/apply_gate.py"
    content = apply_gate.read_text(encoding="utf-8") if apply_gate.exists() else ""
    if "del allow_source_informed" in content:
        return {"behavior": "legacy_no_op"}
    return {"behavior": "drift_detected"}


def _report_ownership_gate_files() -> list[str]:
    return sorted(
        row["file"]
        for row in build_report_ownership()
        if row.get("classification") == "gate"
    )


def _report_ownership_unclassified_files() -> list[str]:
    return sorted(
        row.get("file", "")
        for row in build_report_ownership()
        if not row.get("classification")
    )


def _problems(checks: dict[str, Any]) -> list[dict[str, object]]:
    problems: list[dict[str, object]] = []
    list_checks = (
        "policy_missing_claim_kinds",
        "policy_extra_claim_kinds",
        "spine_missing_claim_kinds",
        "spine_extra_claim_kinds",
        "non_diagnostic_policy_claim_kinds",
        "spine_rows_with_apply_authority_fields",
        "conformance_apply_authority_fields_present",
        "active_apply_diagnostic_consumers",
        "active_apply_paths_missing",
        "legacy_surface_normal_routing",
        "report_ownership_unclassified_files",
    )
    for key in list_checks:
        value = checks.get(key, [])
        if value:
            problems.append({"check": key, "value": value})

    if checks.get("conformance_operator_gate_impact") != "diagnostic_only":
        problems.append(
            {
                "check": "conformance_operator_gate_impact",
                "value": checks.get("conformance_operator_gate_impact"),
            }
        )

    if checks.get("source_informed_apply_flag_policy", {}).get("behavior") != "legacy_no_op":
        problems.append(
            {
                "check": "source_informed_apply_flag_policy",
                "value": checks.get("source_informed_apply_flag_policy"),
            }
        )

    if checks.get("report_ownership_gate_files") != ["reports/operator_summary.json"]:
        problems.append(
            {
                "check": "report_ownership_gate_files",
                "value": checks.get("report_ownership_gate_files"),
            }
        )

    suppression = checks.get("start_of_game_mulligan_suppression", {})
    if not isinstance(suppression, dict) or suppression.get("decision") != "rejected":
        problems.append(
            {
                "check": "start_of_game_mulligan_suppression",
                "value": suppression,
            }
        )
    return problems

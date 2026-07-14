from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from hsconfig.config_usefulness import EXPECTED_RUNTIME_SURFACES
from hsconfig.operator_summary import build_operator_summary
from hsconfig.output_ownership_manifest import (
    KNOWN_DIAGNOSTIC_REPORT_FILES,
    KNOWN_RESEARCH_REPORT_FILES,
    build_output_ownership_manifest,
)
from hsconfig.report_ownership import build_report_ownership
from hsconfig.source_claim_family_registry import build_claim_family_registry_report
from hsconfig.source_contract_conformance import build_source_contract_conformance_snapshot
from hsconfig.source_contract_matrix import source_contract_policy_by_claim_kind
from hsconfig.source_document_model import SUPPORTED_ATOMIC_CLAIM_KINDS


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

EXPECTED_RESEARCH_REPORT_FILES = tuple(sorted(KNOWN_RESEARCH_REPORT_FILES))
EXPECTED_RUNTIME_SURFACE_FILES = (
    "CustomConfig/deck/CARDID.json",
    "CustomConfig/deck/Combo.json",
    "CustomConfig/deck/GlobalValues.json",
    "CustomConfig/deck/Mulligan.json",
)
EXPECTED_EMITTED_PACKAGE_FILES = tuple(
    sorted(
        {
            *EXPECTED_RUNTIME_SURFACE_FILES,
            *EXPECTED_RESEARCH_REPORT_FILES,
            *KNOWN_DIAGNOSTIC_REPORT_FILES,
            *(row["file"] for row in build_report_ownership()),
        }
    )
)
CLAIM_LIFECYCLE_OWNER = "hsconfig.source_claim_lifecycle"
LIFECYCLE_DIAGNOSTIC_REPORT_FILES = (
    "reports/source_contract_audit.json",
    "reports/source_to_runtime_explainability.json",
)
LIFECYCLE_DIAGNOSTIC_TOKENS = (
    "claim lifecycle",
    "claim_lifecycle",
    "contract spine",
    "contract_spine",
    "source contract",
    "source_contract",
    "source-to-runtime",
    "source_to_runtime",
)

INVARIANT_EVIDENCE = {
    "single_apply_authority": (
        "report_ownership_gate_files",
        "active_apply_diagnostic_consumers",
        "lifecycle_gate_files",
    ),
    "diagnostics_are_non_authoritative": (
        "non_diagnostic_policy_claim_kinds",
        "spine_rows_with_apply_authority_fields",
        "conformance_apply_authority_fields_present",
        "conformance_operator_gate_impact",
        "surface_status_ledger",
        "runtime_surface_coverage",
    ),
    "claim_kind_surface_policy_complete": (
        "policy_missing_claim_kinds",
        "policy_extra_claim_kinds",
        "spine_missing_claim_kinds",
        "spine_extra_claim_kinds",
        "claim_family_registry",
    ),
    "effect_not_mulligan": (
        "start_of_game_mulligan_suppression",
        "critical_boundary_rows",
    ),
    "no_forbidden_legacy_runtime_surfaces": (
        "legacy_surface_normal_routing",
        "output_ownership_forbidden_legacy_surfaces",
    ),
    "skill_and_docs_guardrail_ready": (
        "report_ownership_unclassified_files",
        "output_ownership_unclassified_files",
    ),
}


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
        "claim_lifecycle_owner": CLAIM_LIFECYCLE_OWNER,
        "report_ownership_gate_files": _report_ownership_gate_files(),
        "lifecycle_gate_files": _lifecycle_gate_files(),
        "report_ownership_unclassified_files": _report_ownership_unclassified_files(),
        "output_ownership_unclassified_files": _output_ownership_files_by_classification(
            "unclassified"
        ),
        "output_ownership_forbidden_legacy_surfaces": (
            _output_ownership_files_by_classification("forbidden_legacy_surface")
        ),
        "runtime_surface_coverage": _runtime_surface_coverage(),
    }
    family_registry_report = build_claim_family_registry_report()
    checks["claim_family_registry"] = {
        "status": family_registry_report["status"],
        "authority": family_registry_report["authority"],
        "apply_blocking": family_registry_report["apply_blocking"],
        "problem_count": len(family_registry_report["problems"]),
    }
    problems = _problems(checks)
    return {
        "schema_version": 1,
        "status": "clean" if not problems else "drift_detected",
        "authority": "diagnostic_only",
        "operator_gate_impact": "diagnostic_only",
        "apply_blocking": False,
        "checks": checks,
        "contract_invariants": _contract_invariants(checks, problems),
        "problems": problems,
    }


def _missing(expected: tuple[str, ...], actual: dict[str, object]) -> list[str]:
    return sorted(set(expected) - set(actual))


def _extra(expected: tuple[str, ...], actual: dict[str, object]) -> list[str]:
    return sorted(set(actual) - set(expected))


def _runtime_surface_coverage() -> dict[str, Any]:
    summary = build_operator_summary(
        deck_name="Surface Coverage Fixture",
        deck_code="AAEBAQAAAA==",
        technical_validation={"status": "passed", "errors": []},
        guide_source_depth={
            "source_depth_status": "static_semantics_only",
            "claim_count": 0,
        },
        mulligan_plan_report={
            "rules": [],
            "suppressed_rules": [],
            "quality": {
                "status": "thin",
                "has_concrete_keeps": False,
            },
        },
        card_behavior_plan_report={"rows": []},
        combo_plan_report={"combos": [], "suppressed": []},
        globalvalues_profile_report={"changed_keys": [], "unchanged_keys": []},
    )
    expected = sorted(EXPECTED_RUNTIME_SURFACES)
    config_surfaces = sorted(summary["config_usefulness"]["surfaces"])
    ledger_surfaces = sorted(row["surface"] for row in summary["surface_status_ledger"])
    return {
        "expected_surfaces": expected,
        "config_usefulness_surfaces": config_surfaces,
        "surface_status_ledger_surfaces": ledger_surfaces,
        "missing_from_config_usefulness": sorted(set(expected) - set(config_surfaces)),
        "missing_from_surface_status_ledger": sorted(set(expected) - set(ledger_surfaces)),
        "extra_in_config_usefulness": sorted(set(config_surfaces) - set(expected)),
        "extra_in_surface_status_ledger": sorted(set(ledger_surfaces) - set(expected)),
    }


def _runtime_surface_coverage_problem_value(
    coverage: dict[str, Any],
) -> dict[str, list[str]]:
    return {
        "missing_from_config_usefulness": list(
            coverage.get("missing_from_config_usefulness", [])
        ),
        "missing_from_surface_status_ledger": list(
            coverage.get("missing_from_surface_status_ledger", [])
        ),
        "extra_in_config_usefulness": list(
            coverage.get("extra_in_config_usefulness", [])
        ),
        "extra_in_surface_status_ledger": list(
            coverage.get("extra_in_surface_status_ledger", [])
        ),
    }


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


def _source_informed_apply_flag_policy(root: Path) -> dict[str, Any]:
    active_branches = _source_informed_active_branches(root)
    missing_noop_deletes = _source_informed_missing_noop_deletes(root)
    if active_branches or missing_noop_deletes:
        return {
            "behavior": "drift_detected",
            "active_branches": active_branches,
            "missing_noop_deletes": missing_noop_deletes,
        }
    return {
        "behavior": "legacy_no_op",
        "active_branches": [],
        "missing_noop_deletes": [],
    }


def _source_informed_active_branches(root: Path) -> list[dict[str, object]]:
    branches: list[dict[str, object]] = []
    for relative_path in ACTIVE_APPLY_PATHS:
        path = root / relative_path
        if not path.exists():
            continue
        content = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(content)
        except SyntaxError as error:
            branches.append(
                {
                    "path": relative_path,
                    "line": error.lineno or 1,
                    "reason": "syntax_error",
                }
            )
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.If) and _ast_mentions_allow_source_informed(node.test):
                branches.append({"path": relative_path, "line": node.lineno})
    return branches


def _ast_mentions_allow_source_informed(node: ast.AST) -> bool:
    for child in ast.walk(node):
        if isinstance(child, ast.Name) and child.id == "allow_source_informed":
            return True
        if isinstance(child, ast.Attribute) and child.attr == "allow_source_informed":
            return True
        if (
            isinstance(child, ast.Constant)
            and child.value in {"allow_source_informed", "allow-source-informed"}
        ):
            return True
    return False


def _source_informed_missing_noop_deletes(root: Path) -> list[dict[str, str]]:
    missing: list[dict[str, str]] = []
    for relative_path in (
        "src/hsconfig/apply_gate.py",
        "src/hsconfig/runtime_apply.py",
    ):
        path = root / relative_path
        if not path.exists():
            continue
        content = path.read_text(encoding="utf-8")
        if "allow_source_informed" in content and "del allow_source_informed" not in content:
            missing.append({"path": relative_path, "token": "del allow_source_informed"})
    return missing


def _report_ownership_gate_files() -> list[str]:
    return sorted(
        row["file"]
        for row in build_report_ownership()
        if row.get("classification") == "gate"
    )


def _lifecycle_gate_files() -> list[str]:
    return sorted(
        str(row.get("file", ""))
        for row in build_report_ownership()
        if row.get("file") != "reports/operator_summary.json"
        and row.get("classification") in {"gate", "operator_gate"}
        and _is_lifecycle_ownership_row(row)
    )


def _is_lifecycle_ownership_row(row: dict[str, Any]) -> bool:
    file_name = str(row.get("file", ""))
    if file_name in LIFECYCLE_DIAGNOSTIC_REPORT_FILES:
        return True
    text = _ownership_row_text(row)
    return any(token in text for token in LIFECYCLE_DIAGNOSTIC_TOKENS)


def _ownership_row_text(row: dict[str, Any]) -> str:
    parts: list[str] = []
    for value in row.values():
        if isinstance(value, (list, tuple, set)):
            parts.extend(str(item) for item in value)
        else:
            parts.append(str(value))
    return " ".join(parts).lower()


def _report_ownership_unclassified_files() -> list[str]:
    return sorted(
        row.get("file", "")
        for row in build_report_ownership()
        if not row.get("classification")
    )


def _output_ownership_files_by_classification(classification: str) -> list[str]:
    manifest = build_output_ownership_manifest(EXPECTED_EMITTED_PACKAGE_FILES)
    return sorted(
        row["file"]
        for row in manifest["files"]
        if row.get("classification") == classification
    )


def _contract_invariants(
    checks: dict[str, Any],
    problems: list[dict[str, object]],
) -> dict[str, dict[str, object]]:
    problem_checks = {
        str(problem.get("check"))
        for problem in problems
        if isinstance(problem, dict)
    }
    invariants: dict[str, dict[str, object]] = {}
    for name, evidence_keys in INVARIANT_EVIDENCE.items():
        failing = [key for key in evidence_keys if key in problem_checks]
        invariants[name] = {
            "status": "clean" if not failing else "drift_detected",
            "authority": "diagnostic_only",
            "apply_blocking": False,
            "evidence": list(evidence_keys),
            "failing_checks": failing,
        }

    suppression = checks.get("start_of_game_mulligan_suppression", {})
    if not isinstance(suppression, dict) or suppression.get("decision") != "rejected":
        _append_invariant_failure(
            invariants,
            "effect_not_mulligan",
            "start_of_game_mulligan_suppression",
        )

    if checks.get("report_ownership_gate_files") != ["reports/operator_summary.json"]:
        _append_invariant_failure(
            invariants,
            "single_apply_authority",
            "report_ownership_gate_files",
        )

    return invariants


def _append_invariant_failure(
    invariants: dict[str, dict[str, object]],
    invariant_name: str,
    check_name: str,
) -> None:
    row = invariants[invariant_name]
    row["status"] = "drift_detected"
    existing = row.get("failing_checks", [])
    failing = list(existing) if isinstance(existing, list) else []
    if check_name not in failing:
        failing.append(check_name)
    row["failing_checks"] = sorted(failing)


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
        "lifecycle_gate_files",
        "output_ownership_unclassified_files",
        "output_ownership_forbidden_legacy_surfaces",
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
    family_registry = checks.get("claim_family_registry", {})
    if family_registry.get("status") != "clean":
        problems.append({"check": "claim_family_registry", "value": family_registry})
    if family_registry.get("authority") != "diagnostic_only":
        problems.append(
            {
                "check": "claim_family_registry_authority",
                "value": family_registry,
            }
        )
    if family_registry.get("apply_blocking") is not False:
        problems.append(
            {
                "check": "claim_family_registry_apply_blocking",
                "value": family_registry,
            }
        )
    coverage = checks.get("runtime_surface_coverage", {})
    if isinstance(coverage, dict):
        coverage_problem = _runtime_surface_coverage_problem_value(coverage)
        if any(coverage_problem.values()):
            problems.append(
                {"check": "runtime_surface_coverage", "value": coverage_problem}
            )
    return problems

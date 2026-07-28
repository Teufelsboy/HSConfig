from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from hsconfig.visionai_registry import (
    CLAIM_SURFACE_REGISTRY,
    GLOBALVALUES_KEY_REGISTRY,
    RUNTIME_ROW_SCHEMA_KEYS,
    RUNTIME_SURFACE_REGISTRY,
)


PRODUCTION_MODULES = (
    "apply_gate.py",
    "acceptance_matrix.py",
    "config_readiness.py",
    "config_quality_contract.py",
    "operator_summary.py",
    "output_ownership_manifest.py",
    "report_ownership.py",
    "validate_package.py",
    "strong_promotion_report.py",
    "runtime_surface_ledger.py",
    "contract_preflight.py",
    "contract_spine_sentinel.py",
)

FORBIDDEN_REGISTRY_DEFINITIONS = {
    "NORMAL_APPLY_AUTHORITY",
    "REQUIRED_RUNTIME_SURFACES",
    "OPTIONAL_RUNTIME_SURFACES",
    "FORBIDDEN_RUNTIME_SURFACES",
    "REPORT_REGISTRY",
    "CLAIM_SURFACE_REGISTRY",
    "GLOBALVALUES_KEY_REGISTRY",
}

FORBIDDEN_CONSUMER_TABLE_NAMES = {
    "CARDID_NON_SURFACE_FILES",
    "CARDID_RUNTIME_VALUE_ROW_KEYS",
    "COMBO_ROW_KEYS",
    "FORBIDDEN_LEGACY_RUNTIME_SURFACES",
    "LEGACY_NON_NORMAL_SURFACES",
    "MULLIGAN_ROW_KEYS",
    "NORMAL_PATH_FORBIDDEN_SURFACE_NAMES",
    "NORMAL_RUNTIME_SURFACE_BOUNDARY",
    "REQUIRED_RUNTIME_FILES",
    "RUNTIME_SURFACE_COMBO",
    "RUNTIME_SURFACE_GLOBALVALUES",
    "RUNTIME_SURFACE_MULLIGAN",
    "RUNTIME_VALUE_ROW_KEYS",
    "SPECIAL_RUNTIME_FILES",
    "SPECIAL_RUNTIME_VALUE_ROW_KEYS",
    "SPECIAL_SURFACE_NAMES",
    "SURFACE_RUNTIME_FILES",
}


def _assignment_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        targets: list[ast.expr] = []
        if isinstance(node, ast.Assign):
            targets.extend(node.targets)
        elif isinstance(node, ast.AnnAssign):
            targets.append(node.target)
        for target in targets:
            if isinstance(target, ast.Name):
                names.add(target.id)
    return names


def _literal_value(node: ast.AST) -> Any:
    try:
        return ast.literal_eval(node)
    except (TypeError, ValueError):
        return None


def _normalized_literal(value: Any) -> Any:
    if isinstance(value, dict):
        return frozenset(
            (_normalized_literal(key), _normalized_literal(item))
            for key, item in value.items()
        )
    if isinstance(value, (list, set, tuple, frozenset)):
        return frozenset(_normalized_literal(item) for item in value)
    return value


def _duplicate_contract_literals(tree: ast.AST) -> list[tuple[int, Any]]:
    row_schemas = {
        _normalized_literal(keys)
        for keys in RUNTIME_ROW_SCHEMA_KEYS.values()
        if keys
    }
    claim_surface_table = _normalized_literal(
        {
            claim_kind: rule.allowed_surfaces
            for claim_kind, rule in CLAIM_SURFACE_REGISTRY.items()
            if rule.allowed_surfaces
        }
    )
    runtime_surface_table = _normalized_literal(
        {
            name: (
                spec.classification,
                spec.normal_apply_allowed,
                spec.row_schema_id,
                spec.value_type_id,
                spec.physical_owner_rule_id,
            )
            for name, spec in RUNTIME_SURFACE_REGISTRY.items()
        }
    )
    forbidden = {*row_schemas, claim_surface_table, runtime_surface_table}
    forbidden_projections = (
        {
            name: RUNTIME_ROW_SCHEMA_KEYS[spec.row_schema_id]
            for name, spec in RUNTIME_SURFACE_REGISTRY.items()
        },
        {
            name: spec.row_schema_id
            for name, spec in RUNTIME_SURFACE_REGISTRY.items()
        },
        {
            name: spec.value_type_id
            for name, spec in RUNTIME_SURFACE_REGISTRY.items()
        },
        {
            name: spec.physical_owner_rule_id
            for name, spec in RUNTIME_SURFACE_REGISTRY.items()
        },
        {
            claim_kind: rule.allowed_surfaces
            for claim_kind, rule in CLAIM_SURFACE_REGISTRY.items()
        },
        {
            key: spec.key_class
            for key, spec in GLOBALVALUES_KEY_REGISTRY.items()
        },
    )
    duplicates: list[tuple[int, Any]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Dict, ast.List, ast.Set, ast.Tuple)):
            continue
        value = _literal_value(node)
        if value is None:
            continue
        normalized = _normalized_literal(value)
        if normalized in forbidden:
            duplicates.append((node.lineno, value))
            continue
        if isinstance(value, dict) and value and any(
            _is_projection_subset(value, projection)
            for projection in forbidden_projections
        ):
            duplicates.append((node.lineno, value))
    return duplicates


def _is_projection_subset(
    candidate: dict[Any, Any],
    projection: dict[Any, Any],
) -> bool:
    return set(candidate) <= set(projection) and all(
        _normalized_literal(value)
        == _normalized_literal(projection[key])
        for key, value in candidate.items()
    )


def test_listed_consumers_do_not_redefine_registry_contracts():
    package_root = Path(__file__).parents[1] / "src" / "hsconfig"
    problems: list[str] = []
    for module_name in PRODUCTION_MODULES:
        path = package_root / module_name
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        assigned = _assignment_names(tree)
        duplicate_names = sorted(
            assigned
            & (FORBIDDEN_REGISTRY_DEFINITIONS | FORBIDDEN_CONSUMER_TABLE_NAMES)
        )
        if duplicate_names:
            problems.append(f"{module_name}: duplicate definitions {duplicate_names}")
        for line_number, literal in _duplicate_contract_literals(tree):
            problems.append(
                f"{module_name}:{line_number}: duplicate contract literal {literal!r}"
            )

    assert problems == []


def test_adoption_guard_detects_each_registry_literal_family():
    source = """
ROW_SCHEMA = {"comment", "condition", "value"}
ROW_SCHEMA_IDS = {"GlobalValues.json": "RUNTIME_VALUE_ROW_KEYS"}
VALUE_TYPES = {"Mulligan.json": "hold_or_discard"}
PHYSICAL_OWNERS = {"Combo.json": "physical_runtime_surface_ledger"}
CLAIM_SURFACES = {"mulligan_keep": ("Mulligan.json",)}
GLOBALVALUE_KEY_CLASSES = {
    "FirstTurnValueWeight": "step1_posture_overlay_allowed"
}
"""
    duplicates = _duplicate_contract_literals(ast.parse(source))

    assert len(duplicates) == 6

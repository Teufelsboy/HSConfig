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


def _assigned_literal_names(tree: ast.AST) -> dict[int, frozenset[str]]:
    names_by_value: dict[int, frozenset[str]] = {}
    for node in ast.walk(tree):
        targets: list[ast.expr] = []
        value: ast.expr | None = None
        if isinstance(node, ast.Assign):
            targets.extend(node.targets)
            value = node.value
        elif isinstance(node, ast.AnnAssign):
            targets.append(node.target)
            value = node.value
        if value is None:
            continue
        names = frozenset(
            target.id for target in targets if isinstance(target, ast.Name)
        )
        if names:
            names_by_value[id(value)] = names
    return names_by_value


def _forbidden_definition_names(
    tree: ast.AST,
    _module_name: str,
) -> list[str]:
    assigned = _assignment_names(tree)
    return sorted(
        assigned
        & (
            FORBIDDEN_REGISTRY_DEFINITIONS
            | FORBIDDEN_CONSUMER_TABLE_NAMES
        )
    )


def _production_module_paths(package_root: Path) -> list[Path]:
    canonical_registry = package_root / "visionai_registry.py"
    return sorted(
        path
        for path in package_root.rglob("*.py")
        if path != canonical_registry
    )


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
        (
            {
                name: RUNTIME_ROW_SCHEMA_KEYS[spec.row_schema_id]
                for name, spec in RUNTIME_SURFACE_REGISTRY.items()
            },
            ("ROW_SCHEMA",),
        ),
        (
            {
                name: spec.row_schema_id
                for name, spec in RUNTIME_SURFACE_REGISTRY.items()
            },
            ("ROW_SCHEMA_ID",),
        ),
        (
            {
                name: spec.value_type_id
                for name, spec in RUNTIME_SURFACE_REGISTRY.items()
            },
            ("VALUE_TYPE",),
        ),
        (
            {
                name: spec.physical_owner_rule_id
                for name, spec in RUNTIME_SURFACE_REGISTRY.items()
            },
            ("PHYSICAL_OWNER",),
        ),
        (
            {
                claim_kind: rule.allowed_surfaces
                for claim_kind, rule in CLAIM_SURFACE_REGISTRY.items()
            },
            ("CLAIM", "SURFACE"),
        ),
        (
            {
                key: spec.key_class
                for key, spec in GLOBALVALUES_KEY_REGISTRY.items()
            },
            ("GLOBALVALUE", "KEY_CLASS"),
        ),
    )
    assigned_literal_names = _assigned_literal_names(tree)
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
            _is_projection_subset(
                value,
                projection,
                assigned_names=assigned_literal_names.get(
                    id(node), frozenset()
                ),
                name_markers=name_markers,
            )
            for projection, name_markers in forbidden_projections
        ):
            duplicates.append((node.lineno, value))
    return duplicates


def _duplicate_claim_classification_literals(
    tree: ast.AST,
) -> list[tuple[int, str, str]]:
    known_claim_kinds = frozenset(CLAIM_SURFACE_REGISTRY)
    duplicates: list[tuple[int, str, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        value = _literal_value(node)
        if not isinstance(value, dict):
            continue
        for claim_kind, row in value.items():
            if (
                claim_kind not in known_claim_kinds
                or not isinstance(row, dict)
            ):
                continue
            for field in ("lane", "allowed_surfaces"):
                if field in row:
                    duplicates.append((node.lineno, str(claim_kind), field))
    return duplicates


def _is_projection_subset(
    candidate: dict[Any, Any],
    projection: dict[Any, Any],
    *,
    assigned_names: frozenset[str] = frozenset(),
    name_markers: tuple[str, ...] = (),
) -> bool:
    if not set(candidate) <= set(projection):
        return False
    if all(
        _normalized_literal(value)
        == _normalized_literal(projection[key])
        for key, value in candidate.items()
    ):
        return True
    return bool(name_markers) and any(
        all(marker in name.upper() for marker in name_markers)
        for name in assigned_names
    )


def test_production_tree_does_not_redefine_registry_contracts():
    package_root = Path(__file__).parents[1] / "src" / "hsconfig"
    problems: list[str] = []
    production_modules = _production_module_paths(package_root)
    assert production_modules
    for path in production_modules:
        module_name = path.relative_to(package_root).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        duplicate_names = _forbidden_definition_names(tree, module_name)
        if duplicate_names:
            problems.append(f"{module_name}: duplicate definitions {duplicate_names}")
        for line_number, literal in _duplicate_contract_literals(tree):
            problems.append(
                f"{module_name}:{line_number}: duplicate contract literal {literal!r}"
            )
        for line_number, claim_kind, field in (
            _duplicate_claim_classification_literals(tree)
        ):
            problems.append(
                f"{module_name}:{line_number}: duplicate {field} "
                f"classification for {claim_kind!r}"
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


def test_adoption_guard_detects_claim_lane_and_surface_redefinitions():
    source = """
CLAIM_POLICY = {
    "mulligan_keep": {
        "lane": "runtime_lowerable",
        "allowed_surfaces": ("mulligan",),
        "operator_meaning": "supplemental metadata may remain local",
    }
}
"""

    duplicates = _duplicate_claim_classification_literals(ast.parse(source))

    assert duplicates == [
        (2, "mulligan_keep", "lane"),
        (2, "mulligan_keep", "allowed_surfaces"),
    ]


def test_adoption_guard_detects_divergent_claim_lane():
    source = """
CLAIM_POLICY = {
    "mulligan_keep": {
        "lane": "wrong_lane",
    }
}
"""

    duplicates = _duplicate_claim_classification_literals(ast.parse(source))

    assert duplicates == [(2, "mulligan_keep", "lane")]


def test_adoption_guard_detects_divergent_claim_allowed_surfaces():
    source = """
CLAIM_POLICY = {
    "mulligan_keep": {
        "allowed_surfaces": ("combo",),
    }
}
"""

    duplicates = _duplicate_claim_classification_literals(ast.parse(source))

    assert duplicates == [(2, "mulligan_keep", "allowed_surfaces")]


def test_adoption_guard_detects_conflicting_globalvalues_key_class():
    source = """
GLOBALVALUE_KEY_CLASSES = {
    "FirstTurnValueWeight": "conflicting_key_class",
}
"""

    duplicates = _duplicate_contract_literals(ast.parse(source))

    assert len(duplicates) == 1


def test_adoption_guard_rejects_research_module_with_noncanonical_authority():
    source = """
NORMAL_APPLY_AUTHORITY = "reports/noncanonical_operator_summary.json"
"""

    duplicates = _forbidden_definition_names(
        ast.parse(source),
        "research_status_sync.py",
    )

    assert duplicates == ["NORMAL_APPLY_AUTHORITY"]


def test_adoption_guard_excludes_only_canonical_registry_path(tmp_path: Path):
    package_root = tmp_path / "src" / "hsconfig"
    nested_root = package_root / "nested"
    nested_root.mkdir(parents=True)
    canonical_registry = package_root / "visionai_registry.py"
    nested_registry = nested_root / "visionai_registry.py"
    regular_module = package_root / "consumer.py"
    for path in (canonical_registry, nested_registry, regular_module):
        path.write_text("", encoding="utf-8")

    production_modules = _production_module_paths(package_root)

    assert production_modules == [regular_module, nested_registry]

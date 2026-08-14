from __future__ import annotations

import ast
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
PACKAGE_ROOT = SRC_ROOT / "hsconfig"
FACADE_PATH = PACKAGE_ROOT / "operator_summary.py"
INTEGRITY_PATH = PACKAGE_ROOT / "operator_integrity.py"
EVALUATOR_PATH = PACKAGE_ROOT / "operator_summary_evaluator.py"
DIAGNOSTICS_PATH = PACKAGE_ROOT / "operator_diagnostics.py"

INTEGRITY_OWNER_BINDINGS = frozenset(
    {
        "_StableCounter",
        "_referenced_global_names",
        "_freeze_operator_function_graph",
        "_function_dependency_manifest",
        "_LockedGuardedCallableType",
        "_GuardedOperatorCallable",
        "_ProtectedIntegrityModule",
        "_guard_operator_callable",
        "_operator_integrity_bootstrap",
    }
)
EVALUATOR_OWNER_BINDINGS = frozenset(
    {
        "SOURCE_BACKED_STRONG_REQUIREMENTS",
        "READINESS_SUMMARY_KEY_BY_BLOCKER_REASON",
        "STRONG_SOURCE_QUALITY_LANES",
        "_build_operator_summary_unfrozen",
        "_closure_matches_surface",
        "_operator_apply_facts",
        "_operator_summary_evaluator_bootstrap",
        "_ProtectedEvaluatorModule",
        "_technical_status",
    }
)
MOVED_FACADE_DEFINITIONS = (
    INTEGRITY_OWNER_BINDINGS | EVALUATOR_OWNER_BINDINGS
)
ALLOWED_FACADE_IMPORTS = frozenset(
    {
        "_evaluate_operator_summary_inputs",
        "build_operator_summary",
        "build_operator_summary_from_inputs",
        "refresh_generated_file_accounting",
    }
)
ALLOWED_PRIVATE_FACADE_CONSUMERS = {
    "src/hsconfig/operator_summary_inputs.py": {
        "_evaluate_operator_summary_inputs"
    },
}
ALLOWED_FACADE_MODULE_CONSUMERS = {"src/hsconfig/operator_status.py"}


def _module_tree(path: Path) -> tuple[str, ast.Module]:
    assert path.is_file(), f"required architecture owner missing: {path.name}"
    source = path.read_text(encoding="utf-8")
    return source, ast.parse(source, filename=str(path))


def _top_level_bindings(tree: ast.Module) -> set[str]:
    bindings: set[str] = set()
    for node in tree.body:
        if isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef),
        ):
            bindings.add(node.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            bindings.update(
                target.id for target in targets if isinstance(target, ast.Name)
            )
    return bindings


def _function_node(tree: ast.Module, name: str) -> ast.FunctionDef:
    matches = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == name
    ]
    assert len(matches) == 1, f"expected one top-level {name}, got {len(matches)}"
    return matches[0]


def _resolved_from_module(
    node: ast.ImportFrom,
    *,
    package_name: str,
) -> str | None:
    if node.level == 0:
        return node.module
    package_parts = package_name.split(".") if package_name else []
    parent_levels = node.level - 1
    if parent_levels > len(package_parts):
        return None
    base_parts = package_parts[: len(package_parts) - parent_levels]
    if node.module is not None:
        base_parts.extend(node.module.split("."))
    return ".".join(base_parts) or None


def _imported_modules(
    tree: ast.Module,
    *,
    package_name: str,
) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            resolved = _resolved_from_module(
                node,
                package_name=package_name,
            )
            if resolved is None:
                continue
            if node.module is None or resolved == "hsconfig":
                modules.update(f"{resolved}.{alias.name}" for alias in node.names)
            else:
                modules.add(resolved)
    return modules


def _package_name(path: Path) -> str:
    try:
        relative = path.relative_to(SRC_ROOT)
    except ValueError:
        return "tests"
    return ".".join(relative.parent.parts)


def _facade_consumption(
    path: Path,
    *,
    package_name: str | None = None,
) -> tuple[set[str], bool]:
    _source, tree = _module_tree(path)
    imported: set[str] = set()
    module_imported = False
    effective_package = package_name or _package_name(path)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            resolved = _resolved_from_module(
                node,
                package_name=effective_package,
            )
            if resolved == "hsconfig.operator_summary":
                imported.update(alias.name for alias in node.names)
            elif resolved == "hsconfig" and any(
                alias.name == "operator_summary" for alias in node.names
            ):
                module_imported = True
        elif isinstance(node, ast.Import):
            module_imported = module_imported or any(
                alias.name == "hsconfig.operator_summary"
                for alias in node.names
            )
    return imported, module_imported


def test_operator_summary_facade_stays_within_hard_line_budgets() -> None:
    source, tree = _module_tree(FACADE_PATH)
    build_summary = _function_node(tree, "build_operator_summary")
    physical_lines = len(source.splitlines())
    assert build_summary.end_lineno is not None
    build_summary_lines = build_summary.end_lineno - build_summary.lineno + 1

    assert physical_lines <= 350, (
        f"operator_summary.py has {physical_lines} physical lines; limit is 350"
    )
    assert build_summary_lines <= 120, (
        "build_operator_summary has "
        f"{build_summary_lines} source lines; limit is 120"
    )


@pytest.mark.parametrize(
    ("owner_path", "expected_bindings"),
    (
        pytest.param(
            INTEGRITY_PATH,
            INTEGRITY_OWNER_BINDINGS,
            id="integrity-owner",
        ),
        pytest.param(
            EVALUATOR_PATH,
            EVALUATOR_OWNER_BINDINGS,
            id="evaluator-owner",
        ),
    ),
)
def test_extracted_modules_own_their_architecture_bindings(
    owner_path: Path,
    expected_bindings: frozenset[str],
) -> None:
    _source, tree = _module_tree(owner_path)
    missing = expected_bindings - _top_level_bindings(tree)
    assert not missing, (
        f"{owner_path.name} is missing owned bindings: {sorted(missing)}"
    )


def test_facade_does_not_define_moved_integrity_or_evaluator_helpers() -> None:
    _source, tree = _module_tree(FACADE_PATH)
    retained = MOVED_FACADE_DEFINITIONS & _top_level_bindings(tree)
    assert not retained, (
        "operator_summary.py still defines moved bindings: "
        f"{sorted(retained)}"
    )


@pytest.mark.parametrize(
    ("module_path", "forbidden_imports"),
    (
        pytest.param(
            INTEGRITY_PATH,
            {
                "hsconfig.operator_diagnostics",
                "hsconfig.operator_status",
                "hsconfig.operator_summary",
                "hsconfig.operator_summary_evaluator",
                "hsconfig.operator_summary_inputs",
            },
            id="integrity-is-leaf",
        ),
        pytest.param(
            EVALUATOR_PATH,
            {
                "hsconfig.operator_diagnostics",
                "hsconfig.operator_status",
                "hsconfig.operator_summary",
            },
            id="evaluator-does-not-import-facade",
        ),
        pytest.param(
            DIAGNOSTICS_PATH,
            {
                "hsconfig.operator_summary",
                "hsconfig.operator_summary_evaluator",
            },
            id="diagnostics-use-integrity-owner",
        ),
    ),
)
def test_operator_modules_follow_one_way_import_direction(
    module_path: Path,
    forbidden_imports: set[str],
) -> None:
    _source, tree = _module_tree(module_path)
    violations = forbidden_imports & _imported_modules(
        tree,
        package_name=_package_name(module_path),
    )
    assert not violations, (
        f"{module_path.name} has forbidden imports: {sorted(violations)}"
    )


def test_operator_diagnostics_imports_integrity_helpers_from_owner() -> None:
    _source, tree = _module_tree(DIAGNOSTICS_PATH)
    direct_integrity_names = {
        alias.name
        for node in ast.walk(tree)
        if (
            isinstance(node, ast.ImportFrom)
            and node.module == "hsconfig.operator_integrity"
        )
        for alias in node.names
    }

    assert "_operator_integrity_bootstrap" in direct_integrity_names
    assert {
        "_freeze_operator_function_graph",
        "_guard_operator_callable",
    }.isdisjoint(direct_integrity_names)


@pytest.mark.parametrize(
    ("source", "expected_modules"),
    (
        pytest.param(
            "from hsconfig.operator_summary import _private",
            {"hsconfig.operator_summary"},
            id="absolute-from",
        ),
        pytest.param(
            "from hsconfig import operator_summary",
            {"hsconfig.operator_summary"},
            id="absolute-from-package",
        ),
        pytest.param(
            "from .operator_summary import _private",
            {"hsconfig.operator_summary"},
            id="relative-from-module",
        ),
        pytest.param(
            "from . import operator_summary",
            {"hsconfig.operator_summary"},
            id="relative-from-package",
        ),
    ),
)
def test_import_scanner_normalizes_package_relative_imports(
    source: str,
    expected_modules: set[str],
) -> None:
    tree = ast.parse(source)

    assert _imported_modules(
        tree,
        package_name="hsconfig",
    ) == expected_modules


@pytest.mark.parametrize(
    ("source", "expected"),
    (
        pytest.param(
            "from .operator_summary import _private",
            ({"_private"}, False),
            id="relative-private-consumer",
        ),
        pytest.param(
            "from . import operator_summary",
            (set(), True),
            id="relative-module-consumer",
        ),
        pytest.param(
            "import hsconfig.operator_summary as summary",
            (set(), True),
            id="absolute-module-consumer",
        ),
        pytest.param(
            "from hsconfig import operator_summary",
            (set(), True),
            id="absolute-from-package-consumer",
        ),
    ),
)
def test_facade_consumer_scanner_normalizes_relative_imports(
    tmp_path: Path,
    source: str,
    expected: tuple[set[str], bool],
) -> None:
    path = tmp_path / "consumer.py"
    path.write_text(source, encoding="utf-8")

    assert _facade_consumption(
        path,
        package_name="hsconfig",
    ) == expected


def test_facade_imports_are_limited_to_compatibility_contract() -> None:
    violations: dict[str, list[str]] = {}
    private_consumers: dict[str, set[str]] = {}
    module_consumers: set[str] = set()
    for root in (SRC_ROOT, REPO_ROOT / "tests"):
        for path in root.rglob("*.py"):
            if path == FACADE_PATH:
                continue
            imported, module_imported = _facade_consumption(path)
            relative = path.relative_to(REPO_ROOT).as_posix()
            unexpected = imported - ALLOWED_FACADE_IMPORTS
            if unexpected:
                violations[relative] = sorted(unexpected)
            private = {name for name in imported if name.startswith("_")}
            if private:
                private_consumers[relative] = private
            if module_imported:
                module_consumers.add(relative)

    assert (
        not violations
        and private_consumers == ALLOWED_PRIVATE_FACADE_CONSUMERS
        and module_consumers == ALLOWED_FACADE_MODULE_CONSUMERS
    ), (
        f"unexpected facade imports: {violations}; "
        f"private consumers: {private_consumers}; "
        f"module consumers: {sorted(module_consumers)}"
    )

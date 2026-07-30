from __future__ import annotations

import ast
from pathlib import Path
from typing import get_type_hints

import pytest

from hsconfig.config_quality_checks import evaluate_config_quality
from hsconfig.config_quality_inputs import (
    ConfigQualityInputs,
    load_config_quality_inputs,
)
from hsconfig.package_assembler import PackageModel
from hsconfig.package_model import PackageView
from hsconfig.package_publication import publish_rendered_package
from hsconfig.package_render_authority import (
    RenderedAuthorityPackage,
    render_package_authority,
)


SRC_ROOT = Path("src")
PACKAGE_ROOT = SRC_ROOT / "hsconfig"
CONFIGURE_COMMAND_PATH = PACKAGE_ROOT / "commands/configure.py"
PACKAGE_BUILDER_PATH = PACKAGE_ROOT / "package_builder.py"

COMPILE_FAMILY = frozenset(
    {
        "compile_cardid.py",
        "compile_combo.py",
        "compile_globalvalues.py",
        "compile_mulligan.py",
    }
)
PACKAGE_FAMILY = frozenset(
    {
        "package_compiler.py",
        "package_compiler_support.py",
        "package_assembler.py",
    }
)
CONFIG_QUALITY_FAMILY = frozenset(
    {
        "config_quality_contract.py",
        "config_quality_inputs.py",
        "config_quality_checks.py",
    }
)
OPERATOR_FAMILY = frozenset(
    {
        "operator_summary_inputs.py",
        "operator_diagnostics.py",
        "operator_summary_evaluator.py",
        "operator_status.py",
    }
)
REVIEWED_NO_COMMANDS_FAMILY = (
    COMPILE_FAMILY
    | PACKAGE_FAMILY
    | CONFIG_QUALITY_FAMILY
    | OPERATOR_FAMILY
)


def _module_tree(path: Path) -> ast.Module:
    assert path.is_file(), f"required architecture module missing: {path}"
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _package_name(path: Path) -> str:
    relative = path.relative_to(SRC_ROOT)
    return ".".join(relative.parent.parts)


def _resolved_relative_name(name: str, *, package_name: str) -> str | None:
    if not name.startswith("."):
        return name
    level = len(name) - len(name.lstrip("."))
    package_parts = package_name.split(".") if package_name else []
    parent_levels = level - 1
    if parent_levels > len(package_parts):
        return None
    resolved = package_parts[: len(package_parts) - parent_levels]
    suffix = name[level:]
    if suffix:
        resolved.extend(suffix.split("."))
    return ".".join(resolved) or None


def _resolved_from_module(
    node: ast.ImportFrom,
    *,
    package_name: str,
) -> str | None:
    if node.level == 0:
        return node.module
    relative = "." * node.level
    if node.module is not None:
        relative += node.module
    return _resolved_relative_name(relative, package_name=package_name)


def _literal_string(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _dynamic_import_name(
    node: ast.Call,
    *,
    package_name: str,
) -> str | None:
    is_import_module = (
        isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "importlib"
        and node.func.attr == "import_module"
    )
    is_dunder_import = (
        isinstance(node.func, ast.Name) and node.func.id == "__import__"
    )
    if not (is_import_module or is_dunder_import) or not node.args:
        return None
    imported = _literal_string(node.args[0])
    if imported is None:
        return None
    if not imported.startswith("."):
        return imported
    dynamic_package = None
    if is_import_module:
        if len(node.args) > 1:
            dynamic_package = _literal_string(node.args[1])
        for keyword in node.keywords:
            if keyword.arg == "package":
                dynamic_package = _literal_string(keyword.value)
    return _resolved_relative_name(
        imported,
        package_name=dynamic_package or package_name,
    )


def _imported_modules(
    tree: ast.Module,
    *,
    package_name: str,
) -> frozenset[str]:
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
            if node.module is None or (
                node.level == 0 and node.module == "hsconfig"
            ):
                modules.update(
                    f"{resolved}.{alias.name}" for alias in node.names
                )
            else:
                modules.add(resolved)
        elif isinstance(node, ast.Call):
            imported = _dynamic_import_name(
                node,
                package_name=package_name,
            )
            if imported is not None:
                modules.add(imported)
    return frozenset(modules)


def _normalized_imports(path: Path) -> frozenset[str]:
    return _imported_modules(
        _module_tree(path),
        package_name=_package_name(path),
    )


def _function_node(tree: ast.Module, name: str) -> ast.FunctionDef:
    matches = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == name
    ]
    assert len(matches) == 1, (
        f"expected one top-level function {name}, got {len(matches)}"
    )
    return matches[0]


def _call_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def _selected_calls(
    function: ast.FunctionDef,
    names: frozenset[str],
) -> tuple[str, ...]:
    calls = sorted(
        (
            node
            for node in ast.walk(function)
            if isinstance(node, ast.Call) and _call_name(node) in names
        ),
        key=lambda node: (node.lineno, node.col_offset),
    )
    return tuple(
        name
        for node in calls
        if (name := _call_name(node)) is not None
    )


@pytest.mark.parametrize(
    ("source", "package_name", "expected"),
    (
        pytest.param(
            "import hsconfig.commands.prepare",
            "hsconfig",
            {"hsconfig.commands.prepare"},
            id="absolute-import",
        ),
        pytest.param(
            "from hsconfig import commands",
            "hsconfig",
            {"hsconfig.commands"},
            id="absolute-from-package",
        ),
        pytest.param(
            "from hsconfig.commands import prepare",
            "hsconfig",
            {"hsconfig.commands"},
            id="absolute-from-module",
        ),
        pytest.param(
            "from . import commands",
            "hsconfig",
            {"hsconfig.commands"},
            id="from-dot-package",
        ),
        pytest.param(
            "from .commands import prepare",
            "hsconfig",
            {"hsconfig.commands"},
            id="from-dot-module",
        ),
        pytest.param(
            "from .. import commands",
            "hsconfig.nested",
            {"hsconfig.commands"},
            id="parent-relative-package",
        ),
        pytest.param(
            "import importlib\n"
            "importlib.import_module('hsconfig.commands.prepare')",
            "hsconfig",
            {"importlib", "hsconfig.commands.prepare"},
            id="literal-importlib",
        ),
        pytest.param(
            "import importlib\n"
            "importlib.import_module('.commands.prepare', package='hsconfig')",
            "hsconfig",
            {"importlib", "hsconfig.commands.prepare"},
            id="literal-relative-importlib",
        ),
        pytest.param(
            "__import__('hsconfig.commands.prepare')",
            "hsconfig",
            {"hsconfig.commands.prepare"},
            id="literal-dunder-import",
        ),
    ),
)
def test_import_scanner_reproduces_forbidden_import_mutations(
    source: str,
    package_name: str,
    expected: set[str],
) -> None:
    assert _imported_modules(
        ast.parse(source),
        package_name=package_name,
    ) == expected


def test_compile_family_manifest_matches_every_compile_module() -> None:
    discovered = frozenset(path.name for path in PACKAGE_ROOT.glob("compile_*.py"))

    assert discovered == COMPILE_FAMILY


def test_reviewed_compiler_quality_and_status_families_do_not_import_commands() -> None:
    violations = {
        module: sorted(
            imported
            for imported in _normalized_imports(PACKAGE_ROOT / module)
            if imported == "hsconfig.commands"
            or imported.startswith("hsconfig.commands.")
        )
        for module in sorted(REVIEWED_NO_COMMANDS_FAMILY)
    }

    assert violations == {
        module: [] for module in sorted(REVIEWED_NO_COMMANDS_FAMILY)
    }


def test_entry_functions_delegate_once_in_exact_pipeline_order() -> None:
    configure_payload = _function_node(
        _module_tree(CONFIGURE_COMMAND_PATH),
        "configure_payload",
    )
    prepare_package_payload = _function_node(
        _module_tree(PACKAGE_BUILDER_PATH),
        "prepare_package_payload",
    )
    build_package_payload = _function_node(
        _module_tree(PACKAGE_BUILDER_PATH),
        "build_package_payload",
    )

    assert _selected_calls(
        configure_payload,
        frozenset({"execute_configure"}),
    ) == ("execute_configure",)
    assert _selected_calls(
        prepare_package_payload,
        frozenset({"build_package_payload"}),
    ) == ("build_package_payload",)
    assert _selected_calls(
        build_package_payload,
        frozenset(
            {
                "resolve_package_request",
                "compile_package",
                "assemble_package",
                "render_package_authority",
                "publish_rendered_package",
            }
        ),
    ) == (
        "resolve_package_request",
        "compile_package",
        "assemble_package",
        "render_package_authority",
        "publish_rendered_package",
    )


def test_authority_renderer_and_publisher_keep_the_typed_handoff() -> None:
    render_hints = get_type_hints(render_package_authority)
    publish_hints = get_type_hints(publish_rendered_package)

    assert render_hints["model"] is PackageModel
    assert render_hints["return"] is RenderedAuthorityPackage
    assert publish_hints["rendered"] is RenderedAuthorityPackage
    assert PackageModel not in publish_hints.values()


def test_quality_interfaces_use_typed_package_snapshot_handoff() -> None:
    loader_hints = get_type_hints(load_config_quality_inputs)
    evaluator_hints = get_type_hints(evaluate_config_quality)

    assert loader_hints["package"] is PackageView
    assert loader_hints["return"] is ConfigQualityInputs
    assert evaluator_hints["inputs"] is ConfigQualityInputs

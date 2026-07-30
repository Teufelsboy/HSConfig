from __future__ import annotations

import argparse
import ast
from datetime import date
import importlib
from pathlib import Path
from typing import Any

import hsconfig.package_builder as package_builder
import pytest


PACKAGE_BUILDER_PATH = Path("src/hsconfig/package_builder.py")
LEGACY_WORKFLOW_MODULE = "hsconfig.package_legacy_workflow"
RESEARCH_WORKFLOW_MODULE = "hsconfig.package_research_workflow"
COMPATIBILITY_SYMBOLS = (
    "prepare_package_payload",
    "build_package_payload",
    "research_contract_payload",
    "fetch_latest_cards",
    "build_lowered_runtime_stage",
    "write_json",
    "refresh_package_derivation_authority",
    "_research_required_guide_sources",
    "_with_strategic_receipt_verification",
    "_build_package_disposition_ledger",
    "_filter_globalvalues_authority_matrix",
    "_filter_runtime_rows_by_claim_ids",
)
EXPLICIT_PROJECT_MUTATION_CALLS = {
    "prepare_research_output_dir",
    "write_json",
    "write_research_contract_bundle",
    "write_research_contract_bundle_to_dir",
}
PROJECT_MUTATION_MODULES = {
    "hsconfig.io",
    "hsconfig.package_io",
    "hsconfig.research_contract",
}
OS_MUTATION_FUNCTIONS = {
    "chmod",
    "chown",
    "link",
    "lchmod",
    "lchown",
    "makedirs",
    "mkdir",
    "open",
    "remove",
    "removedirs",
    "rename",
    "renames",
    "replace",
    "rmdir",
    "symlink",
    "truncate",
    "unlink",
    "utime",
}
SHUTIL_MUTATION_FUNCTIONS = {
    "chown",
    "copy",
    "copy2",
    "copyfile",
    "copyfileobj",
    "copytree",
    "copymode",
    "copystat",
    "make_archive",
    "move",
    "rmtree",
    "unpack_archive",
}
PATH_MUTATION_METHODS = {
    "chmod",
    "hardlink_to",
    "lchmod",
    "link_to",
    "mkdir",
    "rename",
    "replace",
    "rmdir",
    "symlink_to",
    "touch",
    "unlink",
    "write_bytes",
    "write_text",
}
PATH_DERIVING_METHODS = {
    "absolute",
    "cwd",
    "expanduser",
    "home",
    "joinpath",
    "relative_to",
    "resolve",
    "with_name",
    "with_stem",
    "with_suffix",
}


def _module_tree(path: Path) -> tuple[str, ast.Module]:
    source = path.read_text(encoding="utf-8")
    return source, ast.parse(source)


def _function_node(tree: ast.Module, name: str) -> ast.FunctionDef:
    return next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == name
    )


def _direct_mutation_calls(tree: ast.Module) -> list[str]:
    bindings = _filesystem_bindings(tree)
    violations: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        function = node.func
        if isinstance(function, ast.Name):
            if function.id in EXPLICIT_PROJECT_MUTATION_CALLS:
                violations.append(f"{node.lineno}:{function.id}")
            elif function.id in bindings["direct_mutators"]:
                violations.append(
                    f"{node.lineno}:{bindings['direct_mutators'][function.id]}"
                )
            elif function.id == "open" and not _open_call_is_provably_read_only(
                node,
                bound_method=False,
            ):
                violations.append(f"{node.lineno}:open")
        elif isinstance(function, ast.Attribute):
            receiver = function.value
            receiver_name = _dotted_expression_name(receiver)
            if (
                isinstance(receiver, ast.Name)
                and receiver.id in bindings["os_modules"]
                and function.attr in OS_MUTATION_FUNCTIONS
            ):
                violations.append(f"{node.lineno}:{function.attr}")
            elif (
                isinstance(receiver, ast.Name)
                and receiver.id in bindings["shutil_modules"]
                and function.attr in SHUTIL_MUTATION_FUNCTIONS
            ):
                violations.append(f"{node.lineno}:{function.attr}")
            elif (
                receiver_name in bindings["project_modules"]
                and function.attr in EXPLICIT_PROJECT_MUTATION_CALLS
            ):
                violations.append(f"{node.lineno}:{function.attr}")
            elif _is_path_receiver(receiver, bindings):
                if (
                    function.attr == "open"
                    and not _open_call_is_provably_read_only(
                        node,
                        bound_method=True,
                    )
                ):
                    violations.append(f"{node.lineno}:open")
                elif function.attr in PATH_MUTATION_METHODS:
                    violations.append(f"{node.lineno}:{function.attr}")
    return violations


def _filesystem_bindings(tree: ast.Module) -> dict[str, Any]:
    bindings: dict[str, Any] = {
        "direct_mutators": {},
        "os_modules": set(),
        "path_constructors": set(),
        "path_variables": set(),
        "pathlib_modules": set(),
        "project_modules": set(),
        "shutil_modules": set(),
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                local_name = alias.asname or alias.name.split(".", 1)[0]
                if alias.name == "os":
                    bindings["os_modules"].add(local_name)
                elif alias.name == "pathlib":
                    bindings["pathlib_modules"].add(local_name)
                elif alias.name == "shutil":
                    bindings["shutil_modules"].add(local_name)
                elif alias.name in PROJECT_MUTATION_MODULES:
                    bindings["project_modules"].add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                local_name = alias.asname or alias.name
                if module == "pathlib" and alias.name == "Path":
                    bindings["path_constructors"].add(local_name)
                elif (
                    module == "os"
                    and alias.name in OS_MUTATION_FUNCTIONS
                ):
                    bindings["direct_mutators"][local_name] = alias.name
                elif (
                    module == "shutil"
                    and alias.name in SHUTIL_MUTATION_FUNCTIONS
                ):
                    bindings["direct_mutators"][local_name] = alias.name
                elif (
                    module in PROJECT_MUTATION_MODULES
                    and alias.name in EXPLICIT_PROJECT_MUTATION_CALLS
                ):
                    bindings["direct_mutators"][local_name] = alias.name
                elif (
                    module == "hsconfig"
                    and f"hsconfig.{alias.name}" in PROJECT_MUTATION_MODULES
                ):
                    bindings["project_modules"].add(local_name)

    assignments: list[tuple[list[ast.expr], ast.expr]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            assignments.append((list(node.targets), node.value))
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            assignments.append(([node.target], node.value))

    changed = True
    while changed:
        changed = False
        for targets, value in assignments:
            for target in targets:
                if not isinstance(target, ast.Name):
                    continue
                if (
                    _is_path_constructor_expression(value, bindings)
                    and target.id not in bindings["path_constructors"]
                ):
                    bindings["path_constructors"].add(target.id)
                    changed = True
                if (
                    _is_path_expression(value, bindings)
                    and target.id not in bindings["path_variables"]
                ):
                    bindings["path_variables"].add(target.id)
                    changed = True

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        arguments = [
            *node.args.posonlyargs,
            *node.args.args,
            *node.args.kwonlyargs,
        ]
        if node.args.vararg is not None:
            arguments.append(node.args.vararg)
        if node.args.kwarg is not None:
            arguments.append(node.args.kwarg)
        bindings["path_variables"].update(
            argument.arg
            for argument in arguments
            if argument.annotation is not None
            and _annotation_references_path(argument.annotation, bindings)
        )
    return bindings


def _dotted_expression_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _dotted_expression_name(node.value)
        if parent is not None:
            return f"{parent}.{node.attr}"
    return None


def _is_path_constructor_expression(
    node: ast.expr,
    bindings: dict[str, Any],
) -> bool:
    return (
        isinstance(node, ast.Name)
        and node.id in bindings["path_constructors"]
    ) or (
        isinstance(node, ast.Attribute)
        and node.attr == "Path"
        and isinstance(node.value, ast.Name)
        and node.value.id in bindings["pathlib_modules"]
    )


def _annotation_references_path(
    node: ast.expr,
    bindings: dict[str, Any],
) -> bool:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value in bindings["path_constructors"]
    if _is_path_constructor_expression(node, bindings):
        return True
    return any(
        _is_path_constructor_expression(child, bindings)
        for child in ast.walk(node)
        if isinstance(child, ast.expr)
    )


def _is_path_receiver(node: ast.expr, bindings: dict[str, Any]) -> bool:
    return _is_path_expression(
        node,
        bindings,
    ) or _is_path_constructor_expression(
        node,
        bindings,
    )


def _is_path_expression(node: ast.expr, bindings: dict[str, Any]) -> bool:
    if isinstance(node, ast.Name):
        return node.id in bindings["path_variables"]
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        return _is_path_expression(node.left, bindings)
    if isinstance(node, ast.Attribute) and node.attr == "parent":
        return _is_path_expression(node.value, bindings)
    if not isinstance(node, ast.Call):
        return False
    function = node.func
    if (
        isinstance(function, ast.Name)
        and function.id in bindings["path_constructors"]
    ):
        return True
    if not isinstance(function, ast.Attribute):
        return False
    if _is_path_constructor_expression(function, bindings):
        return True
    return (
        function.attr in PATH_DERIVING_METHODS
        and _is_path_receiver(function.value, bindings)
    )


def _open_call_is_provably_read_only(
    node: ast.Call,
    *,
    bound_method: bool,
) -> bool:
    mode_index = 0 if bound_method else 1
    mode: ast.expr | None = (
        node.args[mode_index] if len(node.args) > mode_index else None
    )
    for keyword in node.keywords:
        if keyword.arg == "mode":
            mode = keyword.value
    if mode is None:
        return True
    return isinstance(mode, ast.Constant) and mode.value in {
        "r",
        "rb",
        "br",
        "rt",
        "tr",
    }


def _facade_back_imports(tree: ast.Module) -> list[str]:
    target = "hsconfig.package_builder"
    importlib_modules: set[str] = set()
    import_module_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "importlib":
                    importlib_modules.add(alias.asname or "importlib")
                elif (
                    alias.name.startswith("importlib.")
                    and alias.asname is None
                ):
                    importlib_modules.add("importlib")
        elif (
            isinstance(node, ast.ImportFrom)
            and node.level == 0
            and node.module == "importlib"
        ):
            import_module_names.update(
                alias.asname or alias.name
                for alias in node.names
                if alias.name == "import_module"
            )

    assignments = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.Assign, ast.AnnAssign))
    ]
    changed = True
    while changed:
        changed = False
        for assignment in assignments:
            value = assignment.value
            if value is None or not isinstance(value, ast.Name):
                continue
            targets = (
                list(assignment.targets)
                if isinstance(assignment, ast.Assign)
                else [assignment.target]
            )
            for assignment_target in targets:
                if not isinstance(assignment_target, ast.Name):
                    continue
                if (
                    value.id in importlib_modules
                    and assignment_target.id not in importlib_modules
                ):
                    importlib_modules.add(assignment_target.id)
                    changed = True
                if (
                    value.id in import_module_names
                    and assignment_target.id not in import_module_names
                ):
                    import_module_names.add(assignment_target.id)
                    changed = True

    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == target or alias.name.startswith(f"{target}."):
                    violations.append(f"{node.lineno}:import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            relative_module = node.module or ""
            if node.level > 0 and (
                relative_module == "package_builder"
                or relative_module.startswith("package_builder.")
            ):
                dots = "." * node.level
                violations.append(
                    f"{node.lineno}:from {dots}{relative_module} import"
                )
            elif (
                node.level > 0
                and not relative_module
                and any(
                    alias.name == "package_builder" for alias in node.names
                )
            ):
                dots = "." * node.level
                violations.append(
                    f"{node.lineno}:from {dots} import package_builder"
                )
            elif node.module == target or (
                node.module is not None and node.module.startswith(f"{target}.")
            ):
                violations.append(f"{node.lineno}:from {node.module} import")
            elif node.module == "hsconfig" and any(
                alias.name == "package_builder" for alias in node.names
            ):
                violations.append(
                    f"{node.lineno}:from hsconfig import package_builder"
                )
        elif isinstance(node, ast.Call) and node.args:
            imported = node.args[0]
            if not (
                isinstance(imported, ast.Constant)
                and isinstance(imported.value, str)
                and (
                    imported.value == target
                    or imported.value.startswith(f"{target}.")
                    or imported.value == ".package_builder"
                    or imported.value.startswith(".package_builder.")
                )
            ):
                continue
            function = node.func
            if isinstance(function, ast.Name) and (
                function.id == "__import__"
                or function.id in import_module_names
            ):
                violations.append(f"{node.lineno}:{function.id}")
            elif (
                isinstance(function, ast.Attribute)
                and function.attr == "import_module"
                and isinstance(function.value, ast.Name)
                and function.value.id in importlib_modules
            ):
                violations.append(
                    f"{node.lineno}:{function.value.id}.import_module"
                )
    return violations


def test_package_builder_facade_stays_within_physical_and_ast_line_budgets() -> None:
    """Catches workflow bodies growing back into the compatibility facade."""
    source, tree = _module_tree(PACKAGE_BUILDER_PATH)
    prepare = _function_node(tree, "prepare_package_payload")

    assert len(source.splitlines()) <= 250
    assert prepare.end_lineno is not None
    assert prepare.end_lineno - prepare.lineno + 1 <= 120


def test_package_builder_facade_performs_no_direct_filesystem_mutation() -> None:
    """Catches any package write, directory mutation, or writable open in the facade."""
    _source, tree = _module_tree(PACKAGE_BUILDER_PATH)

    assert _direct_mutation_calls(tree) == []


def test_legacy_write_seams_remain_importable_but_are_never_called() -> None:
    """Catches C8 retaining either path-coupled package mutation seam."""
    _source, tree = _module_tree(PACKAGE_BUILDER_PATH)
    called_names = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }

    assert hasattr(package_builder, "write_json")
    assert hasattr(package_builder, "refresh_package_derivation_authority")
    assert "write_json" not in called_names
    assert "refresh_package_derivation_authority" not in called_names


@pytest.mark.parametrize(
    ("source", "expected"),
    (
        (
            'from pathlib import Path\nPath("x").open("w")\n',
            ["2:open"],
        ),
        (
            'from pathlib import Path\nPath("x").touch()\n',
            ["2:touch"],
        ),
        (
            'import os\nos.remove("x")\n',
            ["2:remove"],
        ),
        (
            'mode = "w"\nopen("x", mode)\n',
            ["2:open"],
        ),
    ),
)
def test_mutation_detector_rejects_previously_uncovered_write_forms(
    source: str,
    expected: list[str],
) -> None:
    """Catches representative filesystem writes that bypass exact-name guards."""
    assert _direct_mutation_calls(ast.parse(source)) == expected


@pytest.mark.parametrize(
    "source",
    (
        'open("x")\n',
        'open("x", "r")\n',
        'from pathlib import Path\nPath("x").open()\n',
        'from pathlib import Path\nPath("x").open("rb")\n',
    ),
)
def test_mutation_detector_allows_only_provably_read_only_open_calls(
    source: str,
) -> None:
    """Catches an over-broad guard that rejects ordinary read-only access."""
    assert _direct_mutation_calls(ast.parse(source)) == []


@pytest.mark.parametrize(
    "source",
    (
        "items.remove(value)\n",
        'text.replace("a", "b")\n',
        'client.open("w")\n',
        "custom.touch()\n",
    ),
)
def test_mutation_detector_allows_benign_in_memory_and_custom_methods(
    source: str,
) -> None:
    """Catches a method-name-only detector that rejects non-filesystem objects."""
    assert _direct_mutation_calls(ast.parse(source)) == []


@pytest.mark.parametrize(
    ("source", "expected"),
    (
        (
            'from pathlib import Path\nPath("a").link_to("b")\n',
            ["2:link_to"],
        ),
        (
            'from pathlib import Path as P\npath = P("x")\npath.touch()\n',
            ["3:touch"],
        ),
        (
            'import pathlib as paths\nroot = paths.Path("x")\n'
            '(root / "child").write_text("value")\n',
            ["3:write_text"],
        ),
        (
            'import os as operating_system\noperating_system.remove("x")\n',
            ["2:remove"],
        ),
        (
            'from os import remove as rm\nrm("x")\n',
            ["2:remove"],
        ),
        (
            'import shutil as files\nfiles.rmtree("x")\n',
            ["2:rmtree"],
        ),
    ),
)
def test_mutation_detector_resolves_filesystem_imports_and_path_values(
    source: str,
    expected: list[str],
) -> None:
    """Catches mutation aliases and simple Path-derived values escaping the guard."""
    assert _direct_mutation_calls(ast.parse(source)) == expected


@pytest.mark.parametrize(
    ("source", "expected"),
    (
        (
            'from pathlib import Path\nPath.cwd().joinpath("x").write_text("x")\n',
            ["2:write_text"],
        ),
        (
            "from pathlib import Path\npath = Path.home()\npath.touch()\n",
            ["3:touch"],
        ),
        (
            'from pathlib import Path\npath = Path("a/b").relative_to("a")\n'
            "path.unlink()\n",
            ["3:unlink"],
        ),
        (
            'from pathlib import Path\nP = Path\npath = P("x")\npath.touch()\n',
            ["4:touch"],
        ),
        (
            'from pathlib import Path\ndef mutate(path: Path):\n'
            '    path.write_text("x")\n',
            ["3:write_text"],
        ),
        (
            'import hsconfig.io\nhsconfig.io.write_json("x", {})\n',
            ["2:write_json"],
        ),
    ),
)
def test_mutation_detector_propagates_bounded_static_path_and_module_provenance(
    source: str,
    expected: list[str],
) -> None:
    """Catches ordinary constructor, value, annotation, and dotted-module aliases."""
    assert _direct_mutation_calls(ast.parse(source)) == expected


def test_canonical_package_pipeline_replaces_legacy_workflow() -> None:
    """Catches a C8 cutover that leaves the legacy package owner reachable."""
    research = importlib.import_module(RESEARCH_WORKFLOW_MODULE)

    assert research.research_contract_payload.__module__ == RESEARCH_WORKFLOW_MODULE
    assert not Path("src/hsconfig/package_legacy_workflow.py").exists()
    assert not hasattr(package_builder, "_reset_generated_package_dirs")


def test_production_has_no_legacy_workflow_import_or_reference() -> None:
    """Catches static imports, attributes, and dynamic legacy lookups after C8."""
    violations: list[str] = []
    target = "package_legacy_workflow"
    for relative_path in sorted(Path("src/hsconfig").rglob("*.py")):
        source, tree = _module_tree(relative_path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                if any(target in alias.name for alias in node.names):
                    violations.append(f"{relative_path}:{node.lineno}:import")
            elif isinstance(node, ast.ImportFrom):
                if target in (node.module or "") or any(
                    alias.name == target for alias in node.names
                ):
                    violations.append(f"{relative_path}:{node.lineno}:from")
            elif isinstance(node, ast.Attribute) and node.attr == target:
                violations.append(f"{relative_path}:{node.lineno}:attribute")
            elif (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and target in node.value
            ):
                violations.append(f"{relative_path}:{node.lineno}:string")
        if target in source and not any(
            item.startswith(f"{relative_path}:") for item in violations
        ):
            violations.append(f"{relative_path}:text")

    assert violations == []


def test_research_workflow_never_imports_the_compatibility_facade_back() -> None:
    """Catches circular or ambient dependency lookup through package_builder."""
    _source, tree = _module_tree(
        Path("src/hsconfig/package_research_workflow.py")
    )
    assert _facade_back_imports(tree) == []


@pytest.mark.parametrize(
    ("source", "expected"),
    (
        (
            "from hsconfig import package_builder\n",
            ["1:from hsconfig import package_builder"],
        ),
        (
            'import importlib\nimportlib.import_module("hsconfig.package_builder")\n',
            ["2:importlib.import_module"],
        ),
        (
            '__import__("hsconfig.package_builder")\n',
            ["1:__import__"],
        ),
    ),
)
def test_back_import_detector_rejects_alias_and_dynamic_facade_imports(
    source: str,
    expected: list[str],
) -> None:
    """Catches circular facade lookups hidden behind aliases or dynamic imports."""
    assert _facade_back_imports(ast.parse(source)) == expected


@pytest.mark.parametrize(
    ("source", "expected"),
    (
        (
            "from . import package_builder\n",
            ["1:from . import package_builder"],
        ),
        (
            "from .package_builder import build_package_payload\n",
            ["1:from .package_builder import"],
        ),
        (
            "from importlib import import_module as im\n"
            'im("hsconfig.package_builder")\n',
            ["2:im"],
        ),
    ),
)
def test_back_import_detector_rejects_relative_and_aliased_imports(
    source: str,
    expected: list[str],
) -> None:
    """Catches same-package and renamed importlib facade lookups."""
    assert _facade_back_imports(ast.parse(source)) == expected


@pytest.mark.parametrize(
    ("source", "expected"),
    (
        (
            "import importlib\nloader = importlib\n"
            'loader.import_module("hsconfig.package_builder")\n',
            ["3:loader.import_module"],
        ),
        (
            "from importlib import import_module\nloader = import_module\n"
            'loader("hsconfig.package_builder")\n',
            ["3:loader"],
        ),
        (
            "from importlib import import_module as im\n"
            'im(".package_builder", package=__package__)\n',
            ["2:im"],
        ),
        (
            "import importlib.util\n"
            'importlib.import_module("hsconfig.package_builder")\n',
            ["2:importlib.import_module"],
        ),
    ),
)
def test_back_import_detector_propagates_bounded_importlib_provenance(
    source: str,
    expected: list[str],
) -> None:
    """Catches ordinary importlib aliases and explicit relative facade targets."""
    assert _facade_back_imports(ast.parse(source)) == expected


@pytest.mark.parametrize(
    "source",
    (
        'loader.import_module("hsconfig.package_builder")\n',
        "from . import package_legacy_workflow\n",
    ),
)
def test_back_import_detector_allows_unrelated_import_helpers_and_workflows(
    source: str,
) -> None:
    """Catches an over-broad dynamic or relative import detector."""
    assert _facade_back_imports(ast.parse(source)) == []


def test_facade_preserves_the_measured_public_and_private_compatibility_union() -> None:
    """Catches removal of a repository import or monkeypatch seam."""
    missing = [
        symbol for symbol in COMPATIBILITY_SYMBOLS if not hasattr(package_builder, symbol)
    ]

    assert missing == []


def test_canonical_pipeline_receives_current_facade_dependencies_at_call_time(
    monkeypatch,
) -> None:
    """Catches stale imports or a return to the physical legacy writer."""
    sentinels = {
        name: object()
        for name in (
            "fetch_latest_cards",
            "_research_required_guide_sources",
            "build_lowered_runtime_stage",
        )
    }
    for name, sentinel in sentinels.items():
        monkeypatch.setattr(package_builder, name, sentinel)

    captured: dict[str, Any] = {"steps": []}

    def capture_resolution(
        args: argparse.Namespace,
        *,
        fetch_latest_cards_fn: Any,
        research_required_guide_sources_fn: Any,
        **kwargs: Any,
    ) -> object:
        captured["args"] = args
        captured["fetch_latest_cards"] = fetch_latest_cards_fn
        captured["research_required_guide_sources"] = (
            research_required_guide_sources_fn
        )
        captured["kwargs"] = kwargs
        captured["steps"].append("resolve")
        return "request"

    def compile_package(request: object, **kwargs: Any) -> object:
        assert request == "request"
        captured["compile_kwargs"] = kwargs
        captured["steps"].append("compile")
        return "compiled"

    def assemble_package(compiled: object) -> object:
        assert compiled == "compiled"
        captured["steps"].append("assemble")
        return "model"

    def render_package(model: object, **kwargs: Any) -> object:
        assert model == "model"
        captured["render_kwargs"] = kwargs
        captured["steps"].append("render")
        return "rendered"

    def publish_package(rendered: object, destination: Path, **kwargs: Any) -> object:
        assert rendered == "rendered"
        captured["destination"] = destination
        captured["publish_kwargs"] = kwargs
        captured["steps"].append("publish")
        return object()

    def payload_from_pipeline(**kwargs: Any) -> tuple[dict[str, Any], int]:
        captured["payload_kwargs"] = kwargs
        captured["steps"].append("payload")
        return {"status": "captured"}, 0

    monkeypatch.setattr(package_builder, "resolve_package_request", capture_resolution)
    monkeypatch.setattr(package_builder, "compile_package", compile_package)
    monkeypatch.setattr(package_builder, "assemble_package", assemble_package)
    monkeypatch.setattr(package_builder, "render_package_authority", render_package)
    monkeypatch.setattr(package_builder, "publish_rendered_package", publish_package)
    monkeypatch.setattr(
        package_builder,
        "_package_result_payload",
        payload_from_pipeline,
    )
    args = argparse.Namespace(out="destination")

    assert package_builder.build_package_payload(args) == (
        {"status": "captured"},
        0,
    )
    assert captured["steps"] == [
        "resolve",
        "compile",
        "assemble",
        "render",
        "publish",
        "payload",
    ]
    assert captured["args"] is args
    assert captured["fetch_latest_cards"] is sentinels["fetch_latest_cards"]
    assert (
        captured["research_required_guide_sources"]
        is sentinels["_research_required_guide_sources"]
    )
    assert (
        captured["compile_kwargs"]["build_lowered_runtime_stage_fn"]
        is sentinels["build_lowered_runtime_stage"]
    )
    assert captured["destination"] == Path("destination")


def test_research_workflow_receives_current_facade_monkeypatches_at_call_time(
    monkeypatch,
) -> None:
    """Catches stale fetch or guide-source bindings in standalone research."""
    research = importlib.import_module(RESEARCH_WORKFLOW_MODULE)
    fetch_sentinel = object()
    research_sentinel = object()
    monkeypatch.setattr(package_builder, "fetch_latest_cards", fetch_sentinel)
    monkeypatch.setattr(
        package_builder,
        "_research_required_guide_sources",
        research_sentinel,
    )
    captured: dict[str, Any] = {}

    def capture_workflow(
        args: argparse.Namespace,
        *,
        dependencies: Any,
        **kwargs: Any,
    ) -> tuple[dict[str, Any], int]:
        captured["args"] = args
        captured["dependencies"] = dependencies
        captured["kwargs"] = kwargs
        return {"status": "captured"}, 0

    monkeypatch.setattr(research, "research_contract_payload", capture_workflow)
    args = argparse.Namespace()

    assert package_builder.research_contract_payload(
        args,
        current_date=date(2026, 7, 29),
    ) == ({"status": "captured"}, 0)
    assert captured["args"] is args
    dependencies = captured["dependencies"]
    assert dependencies.fetch_latest_cards is fetch_sentinel
    assert dependencies.research_required_guide_sources is research_sentinel

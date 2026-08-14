from __future__ import annotations

import importlib
import base64
import builtins
import ctypes
from ctypes import wintypes
import hashlib
import inspect
import io
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import shlex
import shutil
import stat
import subprocess
import sys
import sysconfig
import time
import tomllib
from types import ModuleType, SimpleNamespace
import zipfile

import pytest
from pytest import MonkeyPatch


ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "scripts" / "check_coverage_contract.py"
CRITICAL_MODULES = [
    "src/hsconfig/atomic_io.py",
    "src/hsconfig/output_publisher.py",
    "src/hsconfig/current_output.py",
    "src/hsconfig/runtime_installer.py",
    "src/hsconfig/runtime_state.py",
    "src/hsconfig/deck_config_ini.py",
    "src/hsconfig/apply_gate.py",
    "src/hsconfig/apply_decision.py",
    "src/hsconfig/operator_status.py",
]
PRODUCTION_MODULES = tuple(
    sorted(
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "src" / "hsconfig").rglob("*.py")
        if "resources" not in path.relative_to(ROOT / "src" / "hsconfig").parts
    )
)


def _file_coverage(
    *,
    covered_lines: int = 2,
    num_statements: int = 2,
    covered_branches: int = 2,
    num_branches: int = 2,
    missing_lines: list[int] | None = None,
    missing_branches: list[list[int]] | None = None,
) -> dict[str, object]:
    return {
        "executed_lines": [1, 2],
        "summary": {
            "covered_lines": covered_lines,
            "num_statements": num_statements,
            "percent_covered": 100.0,
            "percent_covered_display": "100",
            "missing_lines": num_statements - covered_lines,
            "excluded_lines": 0,
            "num_branches": num_branches,
            "num_partial_branches": 0,
            "covered_branches": covered_branches,
            "missing_branches": num_branches - covered_branches,
        },
        "missing_lines": missing_lines or [],
        "excluded_lines": [],
        "executed_branches": [[1, 2], [1, 3]],
        "missing_branches": missing_branches or [],
    }


def _coverage_payload(
    *,
    global_covered_branches: int = 96,
    global_num_branches: int = 100,
) -> dict[str, object]:
    if global_num_branches < 2 * len(CRITICAL_MODULES):
        raise ValueError("global branch total cannot be below the critical-module total")
    if global_covered_branches < 2 * len(CRITICAL_MODULES):
        raise ValueError("global covered branches cannot be below the critical-module total")
    files = {
        module: _file_coverage(
            covered_lines=0,
            num_statements=0,
            covered_branches=0,
            num_branches=0,
        )
        for module in PRODUCTION_MODULES
    }
    files.update({module: _file_coverage() for module in CRITICAL_MODULES})
    aggregate_module = next(
        module for module in PRODUCTION_MODULES if module not in CRITICAL_MODULES
    )
    aggregate_num_branches = global_num_branches - 2 * len(CRITICAL_MODULES)
    aggregate_covered_branches = (
        global_covered_branches - 2 * len(CRITICAL_MODULES)
    )
    files[aggregate_module] = _file_coverage(
        covered_lines=0,
        num_statements=0,
        covered_branches=aggregate_covered_branches,
        num_branches=aggregate_num_branches,
        missing_branches=[
            [line, line + 1]
            for line in range(
                1,
                aggregate_num_branches - aggregate_covered_branches + 1,
            )
        ],
    )
    return {
        "meta": {
            "format": 3,
            "version": "7.10.0",
            "branch_coverage": True,
            "show_contexts": False,
        },
        "files": files,
        "totals": {
            "covered_lines": 2 * len(CRITICAL_MODULES),
            "num_statements": 2 * len(CRITICAL_MODULES),
            "percent_covered": 98.0,
            "percent_covered_display": "98",
            "missing_lines": 0,
            "excluded_lines": 0,
            "num_branches": global_num_branches,
            "num_partial_branches": 0,
            "covered_branches": global_covered_branches,
            "missing_branches": global_num_branches - global_covered_branches,
        },
    }


def _refresh_coverage_totals(payload: dict[str, object]) -> None:
    fields = (
        "covered_lines",
        "num_statements",
        "missing_lines",
        "excluded_lines",
        "num_branches",
        "num_partial_branches",
        "covered_branches",
        "missing_branches",
    )
    files = payload["files"]
    totals = payload["totals"]
    assert isinstance(files, dict)
    assert isinstance(totals, dict)
    for field in fields:
        totals[field] = sum(
            row["summary"][field]
            for row in files.values()
            if isinstance(row, dict) and isinstance(row.get("summary"), dict)
        )


def _checker_document(*, passed: bool = True) -> dict[str, object]:
    percent = 96.0 if passed else 88.0
    return {
        "passed": passed,
        "global_branch_percent": percent,
        "global_covered_branches": 96 if passed else 88,
        "global_num_branches": 100,
        "global_minimum": 89.0,
        "target_met": passed,
        "critical_modules": [
            {
                "module": module,
                "statement_percent": 100.0,
                "branch_percent": 100.0,
                "missing_lines": [],
                "missing_branches": [],
            }
            for module in CRITICAL_MODULES
        ],
        "errors": [] if passed else ["coverage below contract"],
    }


def _checker_document_at(percent: float) -> dict[str, object]:
    passed = percent >= 89.0
    document = _checker_document(passed=passed)
    document["global_branch_percent"] = percent
    document["global_covered_branches"] = round(percent * 100)
    document["global_num_branches"] = 10_000
    document["target_met"] = percent >= 95.0
    return document


@pytest.mark.parametrize(
    ("covered", "total", "returncode", "passed", "target_met"),
    ((17799, 20000, 1, False, False), (18999, 20000, 0, True, False)),
)
def test_forwarder_uses_exact_counts_at_rounded_contract_boundaries(
    covered: int,
    total: int,
    returncode: int,
    passed: bool,
    target_met: bool,
    capsys,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    document = _checker_document(passed=passed)
    document.update(
        {
            "global_branch_percent": round(covered * 100 / total, 2),
            "global_covered_branches": covered,
            "global_num_branches": total,
            "target_met": target_met,
            "errors": [] if passed else ["coverage below contract"],
        }
    )
    result = subprocess.CompletedProcess(
        ["checker"], returncode, stdout=json.dumps(document), stderr=""
    )

    assert runner._forward_checker_result(result) == returncode
    assert json.loads(capsys.readouterr().out)["passed"] is passed


def _lock_text(name: str = "locked-pkg", version: str = "1.0") -> str:
    return (
        'lock-version = "1.0"\n'
        "[[packages]]\n"
        f'name = "{name}"\n'
        f'version = "{version}"\n'
        "[[packages.wheels]]\n"
        f'url = "https://example.invalid/{name}-{version}-py3-none-any.whl"\n'
        "[packages.wheels.hashes]\n"
        f'sha256 = "{"0" * 64}"\n'
    )


def _run_checker(path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CHECKER), str(path)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _write_coverage(tmp_path: Path, payload: object) -> Path:
    coverage_path = tmp_path / "coverage.json"
    coverage_path.write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )
    return coverage_path


def _read_report(result: subprocess.CompletedProcess[str]) -> dict[str, object]:
    assert result.stdout.strip(), result.stderr
    return json.loads(result.stdout)


def _failure_plugin_command(
    runner,
    repository: Path,
    sideband: Path,
    *pytest_arguments: str,
) -> tuple[tuple[str, ...], dict[str, str]]:
    tests_root = repository / "tests"
    tests_metadata = tests_root.lstat()
    if (
        not stat.S_ISDIR(tests_metadata.st_mode)
        or stat.S_ISLNK(tests_metadata.st_mode)
        or runner._is_reparse(tests_metadata)
    ):
        raise AssertionError("temporary pytest tests root is unsafe")
    package_marker = tests_root / "__init__.py"
    try:
        package_marker.lstat()
    except FileNotFoundError:
        with package_marker.open("xb"):
            pass
    marker_metadata = package_marker.lstat()
    marker_source = package_marker.read_bytes()
    if (
        not stat.S_ISREG(marker_metadata.st_mode)
        or stat.S_ISLNK(marker_metadata.st_mode)
        or runner._is_reparse(marker_metadata)
        or getattr(marker_metadata, "st_nlink", 1) != 1
        or marker_source != b""
        or runner._identity(package_marker.lstat()) != runner._identity(marker_metadata)
    ):
        raise AssertionError("temporary pytest package marker is unsafe")
    import_inventory = _test_pytest_import_inventory(runner, ROOT, repository)
    inventory_document, inventory_sha256 = runner._pytest_import_inventory_document(
        import_inventory
    )
    environment = os.environ.copy()
    for name in tuple(environment):
        if name.upper().startswith(
            ("PYTEST_", "PYTHON", "HSCONFIG_COVERAGE_")
        ):
            environment.pop(name, None)
    environment.update(
        {
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
            "PYTHONPATH": str(ROOT),
            runner._PYTEST_IMPORT_INVENTORY: inventory_document,
            runner._PYTEST_IMPORT_INVENTORY_SHA256: inventory_sha256,
        }
    )
    return (
        (
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "scripts.run_coverage_gate",
            f"--hsconfig-failure-sideband={sideband}",
            *pytest_arguments,
        ),
        environment,
    )


def _valid_failure_sideband_document(
    *,
    count: int = 1,
    truncated: bool = False,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "recorder_status": "available",
        "failures": [
            {
                "path": "tests/test_coverage_contract.py",
                "class": None,
                "function": (
                    "test_coverage_runner_propagates_failure_and_cleans_temp_directory"
                    if index == 0
                    else f"test_failure_{index}"
                ),
                "parameter": None,
                "phase": "call",
            }
            for index in range(count)
        ],
        "truncated": truncated,
    }


def _call_failure_sideband_loader(
    runner,
    run_root: Path,
    sideband: Path,
    run_identity: tuple[int, int],
    sideband_identity: tuple[int, int],
    allowed_identities: frozenset[tuple[str, str | None, str]],
):
    kwargs: dict[str, object] = {}
    if "allowed_identities" in inspect.signature(
        runner._load_pytest_failure_sideband
    ).parameters:
        kwargs["allowed_identities"] = allowed_identities
    return runner._load_pytest_failure_sideband(
        run_root,
        sideband,
        run_identity,
        sideband_identity,
        **kwargs,
    )


def _test_python_source_inventory(
    runner,
    repository_root: Path,
) -> tuple[tuple[str, str, str], ...]:
    rows: list[tuple[str, str, str]] = []
    for path in sorted((repository_root / "tests").rglob("*.py")):
        payload = path.read_bytes()
        mode = runner._runtime_git_mode(path.stat().st_mode) or "100644"
        rows.append(
            (
                path.relative_to(repository_root).as_posix(),
                hashlib.sha256(payload).hexdigest(),
                mode,
            )
        )
    return tuple(rows)


def _test_pytest_import_inventory(
    runner,
    source_root: Path,
    test_root: Path | None = None,
) -> tuple[tuple[str, str, str], ...]:
    rows: list[tuple[str, str, str]] = []
    selected_test_root = source_root if test_root is None else test_root
    selected: list[tuple[str, Path]] = []
    for path in sorted((source_root / "src" / "hsconfig").rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts:
            selected.append((path.relative_to(source_root).as_posix(), path))
    for path in sorted((selected_test_root / "tests").rglob("*.py")):
        if "__pycache__" not in path.parts:
            selected.append((path.relative_to(selected_test_root).as_posix(), path))
    for relative, path in selected:
        mode = runner._runtime_git_mode(path.stat().st_mode) or "100644"
        rows.append((relative, hashlib.sha256(path.read_bytes()).hexdigest(), mode))
    return tuple(sorted(rows))


def _split_source_pytest_pythonpath(
    run,
    source_root: Path,
    build_backend_root: Path,
) -> str:
    try:
        roots = [
            source_root.resolve(strict=True),
            build_backend_root.resolve(strict=True),
        ]
        locked_runtime = run.locked_test_runtime
        bound_pythonpath = run.environment.get("PYTHONPATH")
        if locked_runtime is None:
            if bound_pythonpath is not None:
                raise AssertionError("split-source coverage authority is invalid")
        else:
            locked_backend = locked_runtime.build_backend_root.resolve(strict=True)
            if bound_pythonpath != str(locked_backend):
                raise AssertionError("split-source coverage authority is invalid")
            roots.append(locked_backend)
    except (AttributeError, OSError, TypeError) as exc:
        raise AssertionError("split-source coverage authority is invalid") from exc
    if len(set(roots)) != len(roots):
        raise AssertionError("split-source coverage authority is invalid")
    return os.pathsep.join(str(root) for root in roots)


def _split_source_pytest_environment(
    runner,
    run,
    source_root: Path,
    build_backend_root: Path,
) -> dict[str, str]:
    environment = dict(run.environment)
    outer_authorities = {
        name.upper() for name in runner._BOOTSTRAP_AUTHORITY_VARIABLES
    }
    for name in tuple(environment):
        normalized = name.upper()
        if normalized in outer_authorities or normalized == "PYTHONPATH":
            environment.pop(name)
    environment["PYTHONPATH"] = _split_source_pytest_pythonpath(
        run,
        source_root,
        build_backend_root,
    )
    return environment


def _test_coverage_runtime_binding(
    runner,
    *,
    repository: Path,
    source_root: Path,
    build_backend_root: Path,
    source_inventory: tuple[tuple[str, str, str], ...] = (),
    commit_oid: str = "a" * 40,
    tree_oid: str = "b" * 40,
):
    arguments: dict[str, object] = {
        "repository_root": repository.resolve(strict=True),
        "commit_oid": commit_oid,
        "tree_oid": tree_oid,
        "root_identity": runner._identity(repository.lstat()),
        "pythonpath": (
            source_root.resolve(strict=True),
            build_backend_root.resolve(strict=True),
        ),
        "source_inventory": source_inventory,
    }
    fields = runner._CoverageRuntimeBinding.__dataclass_fields__
    if "build_backend_identity" in fields:
        identity, digest = runner._runtime_overlay_binding(build_backend_root)
        arguments["build_backend_identity"] = identity
        arguments["build_backend_inventory_sha256"] = digest
    return runner._CoverageRuntimeBinding(**arguments)


def _call_test_identity_allowlist(
    runner,
    repository_root: Path,
    source_inventory: tuple[tuple[str, str, str], ...],
):
    kwargs: dict[str, object] = {}
    if "source_inventory" in inspect.signature(
        runner._pytest_test_identity_allowlist
    ).parameters:
        kwargs["source_inventory"] = source_inventory
    return runner._pytest_test_identity_allowlist(repository_root, **kwargs)


def _run_unit_coverage_main(runner) -> int:
    return runner.main(
        test_source_inventory=_test_python_source_inventory(runner, runner.ROOT)
    )


def test_failure_plugin_command_rebinds_nested_import_authority(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """Catches nested fixtures inheriting a foreign locked repository authority."""
    runner = importlib.import_module("scripts.run_coverage_gate")
    repository = tmp_path / "repository"
    tests_root = repository / "tests"
    tests_root.mkdir(parents=True)
    (tests_root / "test_probe.py").write_text(
        "def test_probe():\n    pass\n",
        encoding="utf-8",
    )
    sideband = tmp_path / runner.PYTEST_FAILURE_SIDEBAND_NAME
    inherited = {
        runner._COVERAGE_TEST_REPOSITORY_ROOT: "foreign-repository",
        runner._COVERAGE_TEST_REPOSITORY_BINDING: "foreign-binding",
        runner._LOCKED_TEST_RUNTIME_BINDING: "foreign-runtime",
        runner._LOCKED_TEST_RUNTIME_SHA256: "1" * 64,
        runner._PYTEST_IMPORT_INVENTORY: "foreign-inventory",
        runner._PYTEST_IMPORT_INVENTORY_SHA256: "2" * 64,
        "HSCONFIG_COVERAGE_FUTURE_AUTHORITY": "foreign-future-authority",
    }
    for name, value in inherited.items():
        monkeypatch.setenv(name, value)

    _command, environment = _failure_plugin_command(
        runner,
        repository,
        sideband,
    )

    for name in inherited:
        if name not in {
            runner._PYTEST_IMPORT_INVENTORY,
            runner._PYTEST_IMPORT_INVENTORY_SHA256,
        }:
            assert name not in environment
    document = environment[runner._PYTEST_IMPORT_INVENTORY]
    digest = environment[runner._PYTEST_IMPORT_INVENTORY_SHA256]
    assert document != inherited[runner._PYTEST_IMPORT_INVENTORY]
    assert digest != inherited[runner._PYTEST_IMPORT_INVENTORY_SHA256]
    assert hashlib.sha256(document.encode("utf-8")).hexdigest() == digest
    expected_inventory = _test_pytest_import_inventory(runner, ROOT, repository)
    assert runner._pytest_import_inventory_binding(document, digest) == expected_inventory
    assert {path for path, _digest, _mode in expected_inventory} >= {
        "src/hsconfig/__init__.py",
        "tests/__init__.py",
        "tests/test_probe.py",
    }
    package_marker = tests_root / "__init__.py"
    metadata = package_marker.lstat()
    assert stat.S_ISREG(metadata.st_mode)
    assert not stat.S_ISLNK(metadata.st_mode)
    assert not runner._is_reparse(metadata)
    assert getattr(metadata, "st_nlink", 1) == 1
    assert package_marker.read_bytes() == b""

    unsafe_repository = tmp_path / "unsafe-repository"
    unsafe_tests = unsafe_repository / "tests"
    unsafe_tests.mkdir(parents=True)
    unsafe_marker = unsafe_tests / "__init__.py"
    unsafe_marker.write_bytes(b"do-not-overwrite\n")
    with pytest.raises(AssertionError, match="pytest package marker is unsafe"):
        _failure_plugin_command(
            runner,
            unsafe_repository,
            sideband,
        )
    assert unsafe_marker.read_bytes() == b"do-not-overwrite\n"


def test_pyproject_enforces_explicit_branch_coverage_policy() -> None:
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    coverage_run = config["tool"]["coverage"]["run"]
    assert coverage_run["branch"] is True
    assert coverage_run["source"] == ["src/hsconfig"]
    assert coverage_run["patch"] == ["subprocess"]
    assert coverage_run["data_file"] == "${COVERAGE_FILE?}"
    assert set(coverage_run["omit"]) == {
        "outputs/*",
        "src/hsconfig/resources/*",
        "tests/*",
        "tests/**/*",
    }
    assert config["tool"]["coverage"]["report"]["fail_under"] == 89


def test_pytest_defers_coverage_acceptance_to_structured_checker(
    tmp_path: Path,
) -> None:
    """Catches pytest masking the structured coverage metrics with exit code 1."""
    runner = importlib.import_module("scripts.run_coverage_gate")
    sideband = tmp_path / "pytest-failure-identities.json"
    interpreter = Path(sys.executable).resolve(strict=True)
    locked_repository = tmp_path / "locked-checkout"
    command = runner._pytest_coverage_command(
        tmp_path / "coverage.json",
        sideband,
        interpreter=interpreter,
        test_root=locked_repository,
    )

    assert command[0] == str(interpreter)
    assert "--import-mode=importlib" in command
    assert "--cov-fail-under=0" in command
    assert not any(
        argument.startswith("--cov-fail-under=")
        and argument != "--cov-fail-under=0"
        for argument in command
    )
    assert ("-p", "scripts.run_coverage_gate") in tuple(
        zip(command, command[1:], strict=False)
    )
    assert f"--hsconfig-failure-sideband={sideband}" in command
    assert command[-1] == str(locked_repository / "tests")
    assert f"--rootdir={locked_repository}" in command
    config_index = command.index("-c")
    assert command[config_index : config_index + 2] == (
        "-c",
        str(locked_repository / "pyproject.toml"),
    )
    override_index = command.index("-o")
    assert command[override_index : override_index + 2] == (
        "-o",
        f"pythonpath={shlex.join([str(runner.ROOT / 'src')])}",
    )
    assert ("-o", "tmp_path_retention_policy=failed") in tuple(
        zip(command, command[1:], strict=False)
    )
    assert f"--cov={runner.ROOT / 'src' / 'hsconfig'}" in command
    assert f"--cov-config={runner.ROOT / 'pyproject.toml'}" in command
    assert f"--cov={locked_repository / 'src' / 'hsconfig'}" not in command
    assert f"--cov-config={locked_repository / 'pyproject.toml'}" not in command
    assert "--cov=src/hsconfig" not in command
    assert "--cov-config=pyproject.toml" not in command

    coverage_path = _write_coverage(
        tmp_path,
        _coverage_payload(global_covered_branches=8899, global_num_branches=10000),
    )
    result = _run_checker(coverage_path)
    report = _read_report(result)
    assert result.returncode != 0
    assert report["global_minimum"] == 89.0
    assert report["global_branch_percent"] == 88.99
    assert report["passed"] is False


def test_full_coverage_command_uses_every_bound_test_file() -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    inventory = _test_python_source_inventory(runner, ROOT)
    selected = runner._canonical_full_coverage_paths(ROOT, inventory)
    command = runner._pytest_coverage_command(
        ROOT / "coverage.json",
        ROOT / runner.PYTEST_FAILURE_SIDEBAND_NAME,
        interpreter=Path(sys.executable).resolve(strict=True),
        test_root=ROOT,
        selected_tests=selected,
    )

    expected_relatives = tuple(
        row[0]
        for row in inventory
        if PurePosixPath(row[0]).name.startswith("test_")
    )
    expected = tuple(str(ROOT / relative) for relative in expected_relatives)
    assert selected == tuple(Path(path) for path in expected)
    assert command[-len(expected) :] == expected
    assert str(ROOT / "tests") not in command[-len(expected) :]
    assert "tests/test_coverage_contract.py" in expected_relatives
    assert {
        "tests/test_configure_cli.py",
        "tests/test_configure_workflow.py",
        "tests/test_deckstring_decode.py",
        "tests/test_full_chain_cli_integration.py",
        "tests/test_real_deck_usage_loop.py",
        "tests/test_runtime_apply.py",
        "tests/test_runtime_match_cli.py",
        "tests/test_shadowpriest_e2e.py",
        "tests/test_output_publication_fault_matrix.py",
        "tests/test_runtime_install_fault_matrix.py",
        "tests/test_package_builder.py",
        "tests/test_validate_package.py",
        "tests/test_compile_mulligan.py",
    }.issubset(expected_relatives)


def test_full_coverage_rejects_duplicate_test_ownership() -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    relative = "tests/test_apply_decision.py"
    row = next(
        row
        for row in _test_python_source_inventory(runner, ROOT)
        if row[0] == relative
    )

    with pytest.raises(
        runner.CoverageGateError,
        match="full coverage inventory is invalid",
    ):
        runner._canonical_full_coverage_paths(
            ROOT,
            (row, row),
        )


def test_full_coverage_rejects_inventory_without_tests() -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")

    with pytest.raises(
        runner.CoverageGateError,
        match="full coverage inventory is incomplete",
    ):
        runner._canonical_full_coverage_paths(
            ROOT,
            (("tests/helpers.py", "0" * 64, "100644"),),
        )


def test_full_coverage_rejects_hardlinked_test_source(
    tmp_path: Path,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    repository = tmp_path / "repository"
    tests_root = repository / "tests"
    tests_root.mkdir(parents=True)
    source = tests_root / "test_probe.py"
    source.write_text("def test_probe():\n    pass\n", encoding="utf-8")
    try:
        os.link(source, tests_root / "test_probe_alias.py")
    except OSError:
        pytest.skip("hardlinks are unavailable on this platform")
    inventory = (
        (
            "tests/test_probe.py",
            hashlib.sha256(source.read_bytes()).hexdigest(),
            "100644",
        ),
    )

    with pytest.raises(
        runner.CoverageGateError,
        match="full coverage source is unsafe",
    ):
        runner._canonical_full_coverage_paths(repository, inventory)


def test_ci_runs_the_full_coverage_gate_once_on_windows_python_311() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )

    assert workflow.count("--locked-check full-tests-and-coverage") == 1
    assert "Run full locked tests and full-source coverage" in workflow
    test_job = workflow.split("\n  test:\n", maxsplit=1)[1].split(
        "\n  package:\n", maxsplit=1
    )[0]
    assert "runs-on: windows-latest" in test_job
    assert "matrix:" not in test_job
    assert 'python-version: "3.11"' in test_job


def test_pytest_pythonpath_override_roundtrips_windows_space_path(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """Catches Pytest shlex splitting or de-escaping the immutable source path."""
    runner = importlib.import_module("scripts.run_coverage_gate")
    source_root = tmp_path / "committed source with spaces"
    source_root.mkdir()
    monkeypatch.setattr(runner, "ROOT", source_root.resolve(strict=True))
    command = runner._pytest_coverage_command(
        tmp_path / "coverage.json",
        tmp_path / runner.PYTEST_FAILURE_SIDEBAND_NAME,
        interpreter=Path(sys.executable).resolve(strict=True),
        test_root=tmp_path / "checkout",
    )
    override = command[command.index("-o") + 1]

    assert shlex.split(override.removeprefix("pythonpath=")) == [
        str(source_root.resolve(strict=True) / "src")
    ]


def test_pytest_identity_projection_is_immutable_and_ast_bound(
    tmp_path: Path,
) -> None:
    """Catches mutable or invented failure-identity vocabulary."""
    runner = importlib.import_module("scripts.run_coverage_gate")
    repository = tmp_path / "repository"
    tests_root = repository / "tests"
    tests_root.mkdir(parents=True)
    (tests_root / "test_public.py").write_text(
        "def helper():\n"
        "    pass\n\n"
        "def test_plain():\n"
        "    pass\n\n"
        "class TestCases:\n"
        "    def helper(self):\n"
        "        pass\n\n"
        "    def test_param(self):\n"
        "        pass\n",
        encoding="utf-8",
    )
    builder = getattr(runner, "_pytest_test_identity_allowlist", None)

    assert builder is not None
    assert builder(
        repository,
        source_inventory=_test_python_source_inventory(runner, repository),
    ) == frozenset(
        {
            ("tests/test_public.py", None, "test_plain"),
            ("tests/test_public.py", "TestCases", "test_param"),
        }
    )


_REPOSITORY_LONG_PYTEST_FUNCTION_NAMES = (
    "test_warning_only_mechanic_with_explicit_supported_block_stays_suppressed_unless_policy_allows_explicit_override",
    "test_claim_embedded_string_semantic_and_mechanic_families_suppress_mulligan_keep_without_external_card_roles",
    "test_claim_embedded_string_roles_and_semantic_families_suppress_mulligan_keep_without_external_card_roles",
)


def test_pytest_item_identity_accepts_repository_long_function_names(
    tmp_path: Path,
) -> None:
    """Catches valid committed pytest names being rejected by provenance."""
    runner = importlib.import_module("scripts.run_coverage_gate")
    repository = tmp_path / "repository"
    test_path = repository / "tests" / "test_long_names.py"
    test_path.parent.mkdir(parents=True)
    test_path.write_text("def test_anchor():\n    pass\n", encoding="utf-8")

    for function_name in _REPOSITORY_LONG_PYTEST_FUNCTION_NAMES:
        item = SimpleNamespace(
            path=test_path,
            module=SimpleNamespace(__file__=str(test_path)),
            originalname=function_name,
            name=function_name,
            cls=None,
        )

        assert runner._safe_pytest_item_identity(item, repository) == {
            "path": "tests/test_long_names.py",
            "class": None,
            "function": function_name,
            "parameter": None,
        }


def test_pytest_identity_allowlist_accepts_repository_long_function_names(
    tmp_path: Path,
) -> None:
    """Catches AST provenance dropping valid long test definitions."""
    runner = importlib.import_module("scripts.run_coverage_gate")
    repository = tmp_path / "repository"
    test_path = repository / "tests" / "test_long_names.py"
    test_path.parent.mkdir(parents=True)
    test_path.write_text(
        "\n".join(
            [
                "def test_anchor():",
                "    pass",
                "",
                *[
                    f"def {function_name}():\n    pass\n"
                    for function_name in _REPOSITORY_LONG_PYTEST_FUNCTION_NAMES
                ],
            ]
        ),
        encoding="utf-8",
    )

    identities = _call_test_identity_allowlist(
        runner,
        repository,
        _test_python_source_inventory(runner, repository),
    )

    assert {
        ("tests/test_long_names.py", None, function_name)
        for function_name in _REPOSITORY_LONG_PYTEST_FUNCTION_NAMES
    } <= identities


def test_pytest_failure_sideband_accepts_source_backed_long_function_names(
    tmp_path: Path,
) -> None:
    """Catches the diagnostic transport rejecting valid provenance names."""
    runner = importlib.import_module("scripts.run_coverage_gate")
    run_root = tmp_path / "run"
    run_root.mkdir()
    sideband = run_root / runner.PYTEST_FAILURE_SIDEBAND_NAME
    sideband.touch()
    sideband_identity = (sideband.stat().st_dev, sideband.stat().st_ino)
    run_identity = runner._coverage_directory_identity(run_root)
    document = {
        "schema_version": 1,
        "recorder_status": "available",
        "failures": [
            {
                "path": "tests/test_long_names.py",
                "class": None,
                "function": function_name,
                "parameter": None,
                "phase": "call",
            }
            for function_name in _REPOSITORY_LONG_PYTEST_FUNCTION_NAMES
        ],
        "truncated": False,
    }
    sideband.write_bytes((json.dumps(document) + "\n").encode())

    report = _call_failure_sideband_loader(
        runner,
        run_root,
        sideband,
        run_identity,
        sideband_identity,
        frozenset(
            {
                ("tests/test_long_names.py", None, function_name)
                for function_name in _REPOSITORY_LONG_PYTEST_FUNCTION_NAMES
            }
        ),
    )

    assert report is not None
    assert report.identities == tuple(
        f"tests/test_long_names.py::{function_name} phase=call"
        for function_name in _REPOSITORY_LONG_PYTEST_FUNCTION_NAMES
    )


def test_pytest_identifier_contract_remains_finitely_fail_closed(
    tmp_path: Path,
) -> None:
    """Catches malformed or unbounded names bypassing any provenance consumer."""
    runner = importlib.import_module("scripts.run_coverage_gate")
    maximum = runner.MAX_SAFE_PYTEST_IDENTIFIER_LENGTH
    at_limit = "test_" + ("a" * (maximum - len("test_")))
    over_limit = "test_" + ("a" * (maximum - len("test_") + 1))
    class_at_limit = "T" + ("a" * (maximum - 1))
    class_over_limit = "T" + ("a" * maximum)
    repository = tmp_path / "repository"
    test_path = repository / "tests" / "test_identifier_bounds.py"
    test_path.parent.mkdir(parents=True)
    test_path.write_text(
        f"def {at_limit}():\n"
        "    pass\n\n"
        f"def {over_limit}():\n"
        "    pass\n\n"
        f"class {class_at_limit}:\n"
        "    def test_method(self):\n"
        "        pass\n\n"
        f"class {class_over_limit}:\n"
        "    def test_method(self):\n"
        "        pass\n",
        encoding="utf-8",
    )

    identities = _call_test_identity_allowlist(
        runner,
        repository,
        _test_python_source_inventory(runner, repository),
    )
    assert ("tests/test_identifier_bounds.py", None, at_limit) in identities
    assert ("tests/test_identifier_bounds.py", None, over_limit) not in identities
    assert (
        "tests/test_identifier_bounds.py",
        class_at_limit,
        "test_method",
    ) in identities
    assert (
        "tests/test_identifier_bounds.py",
        class_over_limit,
        "test_method",
    ) not in identities

    def identity_for(function_name: str, class_name: str | None = None):
        return runner._safe_pytest_item_identity(
            SimpleNamespace(
                path=test_path,
                module=SimpleNamespace(__file__=str(test_path)),
                originalname=function_name,
                name=function_name,
                cls=None if class_name is None else type(class_name, (), {}),
            ),
            repository,
        )

    assert identity_for(at_limit) is not None
    assert identity_for(over_limit) is None
    assert identity_for("test_invalid-name") is None
    assert identity_for("test_method", class_at_limit) is not None
    assert identity_for("test_method", class_over_limit) is None
    assert identity_for("test_method", "Test-invalid") is None

    run_root = tmp_path / "run"
    run_root.mkdir()
    sideband = run_root / runner.PYTEST_FAILURE_SIDEBAND_NAME
    sideband.touch()
    sideband_identity = (sideband.stat().st_dev, sideband.stat().st_ino)
    run_identity = runner._coverage_directory_identity(run_root)
    valid_document = {
        "schema_version": 1,
        "recorder_status": "available",
        "failures": [
            {
                "path": "tests/test_identifier_bounds.py",
                "class": class_at_limit,
                "function": "test_method",
                "parameter": None,
                "phase": "call",
            }
        ],
        "truncated": False,
    }
    sideband.write_bytes((json.dumps(valid_document) + "\n").encode())
    assert (
        _call_failure_sideband_loader(
            runner,
            run_root,
            sideband,
            run_identity,
            sideband_identity,
            frozenset(
                {
                    (
                        "tests/test_identifier_bounds.py",
                        class_at_limit,
                        "test_method",
                    )
                }
            ),
        )
        is not None
    )

    for function_name, class_name in (
        (over_limit, None),
        ("test_invalid-name", None),
        ("test_method", class_over_limit),
        ("test_method", "Test-invalid"),
    ):
        document = {
            "schema_version": 1,
            "recorder_status": "available",
            "failures": [
                {
                    "path": "tests/test_identifier_bounds.py",
                    "class": class_name,
                    "function": function_name,
                    "parameter": None,
                    "phase": "call",
                }
            ],
            "truncated": False,
        }
        sideband.write_bytes((json.dumps(document) + "\n").encode())
        report = _call_failure_sideband_loader(
            runner,
            run_root,
            sideband,
            run_identity,
            sideband_identity,
            frozenset(
                {
                    (
                        "tests/test_identifier_bounds.py",
                        class_name,
                        function_name,
                    )
                }
            ),
        )
        assert report.status is runner._PytestFailureSidebandStatus.INVALID_SCHEMA


def test_locked_pytest_collection_rejects_item_from_committed_source(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """Catches a source-root item becoming only unavailable diagnostic metadata."""
    runner = importlib.import_module("scripts.run_coverage_gate")
    repository = tmp_path / "repository"
    source_root = tmp_path / "committed-source"
    (repository / "tests").mkdir(parents=True)
    (source_root / "tests").mkdir(parents=True)
    source_test = source_root / "tests" / "test_probe.py"
    source_test.write_text("def test_probe():\n    pass\n", encoding="utf-8")
    item = SimpleNamespace(
        path=source_test,
        module=SimpleNamespace(__file__=str(source_test)),
        nodeid="tests/test_probe.py::test_probe",
        originalname="test_probe",
        name="test_probe",
        cls=None,
    )
    locked = SimpleNamespace(repository_root=repository.resolve(strict=True))
    state = runner._PytestFailureState(
        repository_root=repository.resolve(strict=True),
        sideband=tmp_path / runner.PYTEST_FAILURE_SIDEBAND_NAME,
        locked_runtime=locked,
        original_directory=source_root.resolve(strict=True),
    )
    monkeypatch.setattr(runner, "_ACTIVE_PYTEST_FAILURE_STATE", state)
    monkeypatch.chdir(repository)

    with pytest.raises(runner.CoverageGateError, match="locked pytest item"):
        runner.pytest_collection_modifyitems(SimpleNamespace(), [item])


def test_locked_pytest_collection_rejects_module_from_committed_source(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """Catches a checkout path masking a reused committed-source module."""
    runner = importlib.import_module("scripts.run_coverage_gate")
    repository = tmp_path / "repository"
    source_root = tmp_path / "committed-source"
    (repository / "tests").mkdir(parents=True)
    (source_root / "tests").mkdir(parents=True)
    checkout_test = repository / "tests" / "test_probe.py"
    source_test = source_root / "tests" / "test_probe.py"
    checkout_test.write_text("def test_probe():\n    pass\n", encoding="utf-8")
    source_test.write_text("def test_probe():\n    pass\n", encoding="utf-8")
    item = SimpleNamespace(
        path=checkout_test,
        module=SimpleNamespace(__file__=str(source_test)),
        nodeid="tests/test_probe.py::test_probe",
        originalname="test_probe",
        name="test_probe",
        cls=None,
    )
    locked = SimpleNamespace(repository_root=repository.resolve(strict=True))
    state = runner._PytestFailureState(
        repository_root=repository.resolve(strict=True),
        sideband=tmp_path / runner.PYTEST_FAILURE_SIDEBAND_NAME,
        locked_runtime=locked,
        original_directory=source_root.resolve(strict=True),
    )
    monkeypatch.setattr(runner, "_ACTIVE_PYTEST_FAILURE_STATE", state)
    monkeypatch.chdir(repository)

    with pytest.raises(runner.CoverageGateError, match="locked pytest item"):
        runner.pytest_collection_modifyitems(SimpleNamespace(), [item])


def test_locked_pytest_collection_rejects_foreign_duplicate_nodeid(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """Catches duplicate nodeids bypassing provenance validation."""
    runner = importlib.import_module("scripts.run_coverage_gate")
    repository = tmp_path / "repository"
    source_root = tmp_path / "committed-source"
    (repository / "tests").mkdir(parents=True)
    (source_root / "tests").mkdir(parents=True)
    checkout_test = repository / "tests" / "test_probe.py"
    source_test = source_root / "tests" / "test_probe.py"
    checkout_test.write_text("def test_probe():\n    pass\n", encoding="utf-8")
    source_test.write_text("def test_probe():\n    pass\n", encoding="utf-8")

    def item(path: Path) -> SimpleNamespace:
        return SimpleNamespace(
            path=path,
            module=SimpleNamespace(__file__=str(path)),
            nodeid="tests/test_probe.py::test_probe",
            originalname="test_probe",
            name="test_probe",
            cls=None,
        )

    locked = SimpleNamespace(repository_root=repository.resolve(strict=True))
    state = runner._PytestFailureState(
        repository_root=repository.resolve(strict=True),
        sideband=tmp_path / runner.PYTEST_FAILURE_SIDEBAND_NAME,
        locked_runtime=locked,
        original_directory=source_root.resolve(strict=True),
    )
    monkeypatch.setattr(runner, "_ACTIVE_PYTEST_FAILURE_STATE", state)
    monkeypatch.chdir(repository)

    with pytest.raises(runner.CoverageGateError, match="locked pytest item"):
        runner.pytest_collection_modifyitems(
            SimpleNamespace(),
            [item(checkout_test), item(source_test)],
        )


def test_locked_pytest_collection_rejects_non_string_nodeid(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """Catches an invalid nodeid bypassing locked item provenance."""
    runner = importlib.import_module("scripts.run_coverage_gate")
    repository = tmp_path / "repository"
    (repository / "tests").mkdir(parents=True)
    checkout_test = repository / "tests" / "test_probe.py"
    checkout_test.write_text("def test_probe():\n    pass\n", encoding="utf-8")
    item = SimpleNamespace(
        path=checkout_test,
        module=SimpleNamespace(__file__=str(checkout_test)),
        nodeid=None,
        originalname="test_probe",
        name="test_probe",
        cls=None,
    )
    locked = SimpleNamespace(repository_root=repository.resolve(strict=True))
    state = runner._PytestFailureState(
        repository_root=repository.resolve(strict=True),
        sideband=tmp_path / runner.PYTEST_FAILURE_SIDEBAND_NAME,
        locked_runtime=locked,
        original_directory=tmp_path.resolve(strict=True),
    )
    monkeypatch.setattr(runner, "_ACTIVE_PYTEST_FAILURE_STATE", state)
    monkeypatch.chdir(repository)

    with pytest.raises(runner.CoverageGateError, match="locked pytest item"):
        runner.pytest_collection_modifyitems(SimpleNamespace(), [item])


def test_runtime_binding_carries_immutable_source_inventory() -> None:
    """Catches validated manifest inventory being discarded before Pytest."""
    runner = importlib.import_module("scripts.run_coverage_gate")

    assert "source_inventory" in runner._CoverageRuntimeBinding.__dataclass_fields__


def test_pytest_identity_projection_rejects_same_inode_byte_mutation(
    tmp_path: Path,
) -> None:
    """Catches post-lock in-place test bytes authorizing an invented identity."""
    runner = importlib.import_module("scripts.run_coverage_gate")
    repository = tmp_path / "repository"
    tests_root = repository / "tests"
    tests_root.mkdir(parents=True)
    source = tests_root / "test_public.py"
    source.write_bytes(b"def test_public():\n    pass\n")
    source_inventory = _test_python_source_inventory(runner, repository)
    source_inode = (source.stat().st_dev, source.stat().st_ino)
    directory_identity = runner._identity(tests_root.stat())

    source.write_bytes(b"def test_secret():\n    pass\n")

    assert (source.stat().st_dev, source.stat().st_ino) == source_inode
    assert runner._identity(tests_root.stat()) == directory_identity
    with pytest.raises(runner.CoverageGateError, match="identity source"):
        _call_test_identity_allowlist(runner, repository, source_inventory)


@pytest.mark.parametrize("kind", ("missing", "extra", "hash", "mode"))
def test_pytest_identity_projection_rejects_unbound_inventory(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    kind: str,
) -> None:
    """Catches nonclosed test inventory or mode/hash authority drift."""
    runner = importlib.import_module("scripts.run_coverage_gate")
    repository = tmp_path / "repository"
    tests_root = repository / "tests"
    tests_root.mkdir(parents=True)
    (tests_root / "test_public.py").write_text(
        "def test_public():\n    pass\n",
        encoding="utf-8",
    )
    inventory = list(_test_python_source_inventory(runner, repository))
    if kind == "missing":
        inventory.clear()
    elif kind == "extra":
        inventory.append(("tests/test_extra.py", "a" * 64, "100644"))
    elif kind == "hash":
        path, _digest, mode = inventory[0]
        inventory[0] = (path, "b" * 64, mode)
    else:
        path, digest, _mode = inventory[0]
        inventory[0] = (path, digest, "100755")
        monkeypatch.setattr(runner, "_runtime_git_mode", lambda mode: "100644")

    with pytest.raises(runner.CoverageGateError, match="identity source"):
        _call_test_identity_allowlist(runner, repository, tuple(inventory))


def test_coverage_runner_rejects_unbound_test_inventory_before_pytest(
    monkeypatch: MonkeyPatch,
    capsys,
) -> None:
    """Catches a canonical main path falling back to current unbound bytes."""
    runner = importlib.import_module("scripts.run_coverage_gate")
    launched = False
    monkeypatch.setattr(runner, "_assert_runtime_matches_lock", lambda lock: None)

    def fake_run(command: tuple[str, ...], **kwargs: object) -> runner._PytestResult:
        nonlocal launched
        del command, kwargs
        launched = True
        return runner._PytestResult(returncode=1, timed_out=False)

    monkeypatch.setattr(runner, "_run_pytest_bounded", fake_run)

    assert runner.main() == 2
    captured = capsys.readouterr()
    assert "coverage gate validation failure phase=source_binding" in captured.err
    assert launched is False


def test_coverage_runner_preserves_pytest_execution_failure_phase(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    capsys,
) -> None:
    """Catches successful post-binding checks masking the primary process phase."""
    runner = importlib.import_module("scripts.run_coverage_gate")
    binding = SimpleNamespace(
        pythonpath=(runner.ROOT.resolve(strict=True),),
        source_inventory=(),
    )
    locked_runtime = SimpleNamespace(
        interpreter=Path(sys.executable).resolve(strict=True),
        repository_root=runner.ROOT.resolve(strict=True),
    )
    run = SimpleNamespace(
        locked_test_runtime=locked_runtime,
        coverage_json=tmp_path / "coverage.json",
        failure_sideband=tmp_path / "failures.json",
        run_root=tmp_path,
        run_identity=(1, 1),
        environment={},
    )

    class FakeIsolation:
        def __enter__(self):
            return run

        def __exit__(self, exc_type, exc, traceback):
            del exc_type, exc, traceback
            return False

    monkeypatch.setattr(runner, "_assert_runtime_matches_lock", lambda lock: binding)
    monkeypatch.setattr(runner, "_pytest_test_identity_allowlist", lambda *a, **k: frozenset())
    monkeypatch.setattr(
        runner,
        "_pytest_collection_path_allowlist",
        lambda inventory: frozenset({"tests/test_coverage_contract.py"}),
    )
    monkeypatch.setattr(runner, "isolated_coverage_environment", lambda value: FakeIsolation())
    monkeypatch.setattr(runner, "_assert_locked_test_runtime", lambda value: None)
    monkeypatch.setattr(runner, "_canonical_full_coverage_paths", lambda *a: (runner.ROOT / "tests" / "test_coverage_contract.py",))

    def fail_run(command: tuple[str, ...], **kwargs: object) -> runner._PytestResult:
        del command, kwargs
        raise runner.CoverageGateError("private transport detail")

    monkeypatch.setattr(runner, "_run_pytest_bounded", fail_run)

    assert runner.main() == 2
    captured = capsys.readouterr()
    assert "private transport detail" not in captured.err
    assert "coverage gate validation failure phase=pytest_execution" in captured.err


def test_unavailable_pytest_session_overwrites_same_inode_fabrication(
    tmp_path: Path,
    capsys,
) -> None:
    """Catches stale same-inode JSON surviving an unavailable plugin session."""
    runner = importlib.import_module("scripts.run_coverage_gate")
    run_root = tmp_path / "run"
    repository = run_root / "repository"
    tests_root = repository / "tests"
    tests_root.mkdir(parents=True)
    (tests_root / "test_attack.py").write_text(
        "def test_attack():\n"
        "    from scripts import run_coverage_gate as runner\n"
        "    state = runner._ACTIVE_PYTEST_FAILURE_STATE\n"
        "    assert state is not None\n"
        "    state.sideband.write_bytes(\n"
        "        b'{\"schema_version\":1,\"failures\":['\n"
        "        b'{\"path\":\"tests/test_LEAKEDSECRET.py\",'\n"
        "        b'\"class\":null,\"function\":\"test_LEAKEDSECRET\",'\n"
        "        b'\"parameter\":null,\"phase\":\"call\"}],'\n"
        "        b'\"truncated\":false}\\n'\n"
        "    )\n"
        "    state.unavailable = True\n"
        "    assert False, 'raw assertion must remain transport-redacted'\n",
        encoding="utf-8",
    )
    sideband = run_root / runner.PYTEST_FAILURE_SIDEBAND_NAME
    sideband.touch()
    sideband_identity = (sideband.stat().st_dev, sideband.stat().st_ino)
    run_identity = runner._coverage_directory_identity(run_root)
    command, environment = _failure_plugin_command(runner, repository, sideband)

    completed = subprocess.run(
        command,
        cwd=repository,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert completed.returncode == 2
    assert (sideband.stat().st_dev, sideband.stat().st_ino) == sideband_identity
    assert sideband.read_bytes() == (
        b'{"failures":[],"recorder_status":"unavailable",'
        b'"schema_version":1,"truncated":false}\n'
    )
    report = _call_failure_sideband_loader(
        runner,
        run_root,
        sideband,
        run_identity,
        sideband_identity,
        frozenset({("tests/test_attack.py", None, "test_attack")}),
    )
    runner._emit_pytest_failure_identities(report)
    assert report.status is runner._PytestFailureSidebandStatus.RECORDER_UNAVAILABLE
    assert capsys.readouterr().err == "pytest failure recorder unavailable\n"


def test_plugin_failure_identity_survives_module_global_shadowing(
    tmp_path: Path,
) -> None:
    """Catches a test hiding the session recorder through the module global."""
    runner = importlib.import_module("scripts.run_coverage_gate")
    run_root = tmp_path / "run"
    repository = run_root / "repository"
    tests_root = repository / "tests"
    tests_root.mkdir(parents=True)
    (tests_root / "test_shadow.py").write_text(
        "def test_shadow():\n"
        "    from scripts import run_coverage_gate as runner\n"
        "    runner._ACTIVE_PYTEST_FAILURE_STATE = None\n"
        "    assert False, 'raw assertion must remain transport-redacted'\n",
        encoding="utf-8",
    )
    sideband = run_root / runner.PYTEST_FAILURE_SIDEBAND_NAME
    sideband.touch()
    sideband_identity = (sideband.stat().st_dev, sideband.stat().st_ino)
    run_identity = runner._coverage_directory_identity(run_root)
    command, environment = _failure_plugin_command(runner, repository, sideband)

    completed = subprocess.run(
        command,
        cwd=repository,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    report = runner._load_pytest_failure_sideband(
        run_root,
        sideband,
        run_identity,
        sideband_identity,
        allowed_identities=frozenset(
            {("tests/test_shadow.py", None, "test_shadow")}
        ),
    )

    assert completed.returncode == 1
    assert report.status is runner._PytestFailureSidebandStatus.VALID
    assert report.identities == ("tests/test_shadow.py::test_shadow phase=call",)
    assert "raw assertion" not in sideband.read_text(encoding="utf-8")


def test_passing_shadowed_global_keeps_session_cleanup_authority(
    tmp_path: Path,
) -> None:
    """Catches session-finish cleanup consulting a test-shadowable global."""
    runner = importlib.import_module("scripts.run_coverage_gate")
    run_root = tmp_path / "run"
    repository = run_root / "repository"
    tests_root = repository / "tests"
    tests_root.mkdir(parents=True)
    (tests_root / "test_shadow.py").write_text(
        "def test_shadow():\n"
        "    from scripts import run_coverage_gate as runner\n"
        "    runner._ACTIVE_PYTEST_FAILURE_STATE = None\n"
        "    assert True\n",
        encoding="utf-8",
    )
    sideband = run_root / runner.PYTEST_FAILURE_SIDEBAND_NAME
    sideband.touch()
    sideband_identity = (sideband.stat().st_dev, sideband.stat().st_ino)
    run_identity = runner._coverage_directory_identity(run_root)
    pytest_temp_parent = run_root / "pytest-temp"
    pytest_temp_parent.mkdir()
    command, environment = _failure_plugin_command(
        runner,
        repository,
        sideband,
        "-o",
        "tmp_path_retention_policy=failed",
    )
    environment["PYTEST_DEBUG_TEMPROOT"] = str(pytest_temp_parent)

    completed = subprocess.run(
        command,
        cwd=repository,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    report = runner._load_pytest_failure_sideband(
        run_root,
        sideband,
        run_identity,
        sideband_identity,
        allowed_identities=frozenset(
            {("tests/test_shadow.py", None, "test_shadow")}
        ),
    )

    assert completed.returncode == 0, completed.stderr
    assert report.status is runner._PytestFailureSidebandStatus.VALID
    assert report.identities == ()
    assert all(
        child.is_dir() and not any(child.iterdir())
        for child in pytest_temp_parent.iterdir()
    )


def test_cleanup_authority_failure_marks_recorder_unavailable(
    tmp_path: Path,
) -> None:
    """Catches an authentic cleanup failure being serialized as valid empty."""
    runner = importlib.import_module("scripts.run_coverage_gate")
    run_root = tmp_path / "run"
    repository = run_root / "repository"
    tests_root = repository / "tests"
    tests_root.mkdir(parents=True)
    (tests_root / "test_cleanup.py").write_text(
        "def test_cleanup():\n"
        "    from scripts import run_coverage_gate as runner\n"
        "    state = runner._ACTIVE_PYTEST_FAILURE_STATE\n"
        "    assert state is not None\n"
        "    state.pytest_basetemp_identity = (0, 0)\n"
        "    assert True\n",
        encoding="utf-8",
    )
    sideband = run_root / runner.PYTEST_FAILURE_SIDEBAND_NAME
    sideband.touch()
    sideband_identity = (sideband.stat().st_dev, sideband.stat().st_ino)
    run_identity = runner._coverage_directory_identity(run_root)
    pytest_temp_parent = run_root / "pytest-temp"
    pytest_temp_parent.mkdir()
    command, environment = _failure_plugin_command(
        runner,
        repository,
        sideband,
        "-o",
        "tmp_path_retention_policy=failed",
    )
    environment["PYTEST_DEBUG_TEMPROOT"] = str(pytest_temp_parent)

    completed = subprocess.run(
        command,
        cwd=repository,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    report = runner._load_pytest_failure_sideband(
        run_root,
        sideband,
        run_identity,
        sideband_identity,
        allowed_identities=frozenset(
            {("tests/test_cleanup.py", None, "test_cleanup")}
        ),
    )

    assert completed.returncode != 0
    assert report.status is runner._PytestFailureSidebandStatus.RECORDER_UNAVAILABLE
    assert "cleanup authority" not in sideband.read_text(encoding="utf-8")


def test_collection_failure_emits_source_backed_path_identity(
    tmp_path: Path,
) -> None:
    """Catches import-time collection failures collapsing to valid empty."""
    runner = importlib.import_module("scripts.run_coverage_gate")
    run_root = tmp_path / "run"
    repository = run_root / "repository"
    tests_root = repository / "tests"
    tests_root.mkdir(parents=True)
    (tests_root / "test_collection.py").write_text(
        "raise RuntimeError('SECRET_COLLECTION_TRACE')\n\n"
        "def test_unreached():\n"
        "    pass\n",
        encoding="utf-8",
    )
    sideband = run_root / runner.PYTEST_FAILURE_SIDEBAND_NAME
    sideband.touch()
    sideband_identity = (sideband.stat().st_dev, sideband.stat().st_ino)
    run_identity = runner._coverage_directory_identity(run_root)
    command, environment = _failure_plugin_command(runner, repository, sideband)

    completed = subprocess.run(
        command,
        cwd=repository,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    report = runner._load_pytest_failure_sideband(
        run_root,
        sideband,
        run_identity,
        sideband_identity,
        allowed_identities=frozenset(
            {("tests/test_collection.py", None, "test_unreached")}
        ),
    )

    assert completed.returncode == 2
    assert report.status is runner._PytestFailureSidebandStatus.VALID
    assert report.identities == ("tests/test_collection.py phase=collection",)
    source = sideband.read_text(encoding="utf-8")
    assert "SECRET_COLLECTION_TRACE" not in source
    assert str(tmp_path) not in source


@pytest.mark.parametrize("nodeid", ("../SECRET.py", "tests/test_foreign.py"))
def test_collection_failure_rejects_unsafe_or_foreign_path(nodeid: str) -> None:
    """Catches a collector report escaping its source-backed vocabulary."""
    runner = importlib.import_module("scripts.run_coverage_gate")
    state = runner._PytestFailureState(
        repository_root=runner.ROOT.resolve(strict=True),
        sideband=runner.ROOT / runner.PYTEST_FAILURE_SIDEBAND_NAME,
        collection_paths=frozenset({"tests/test_public.py"}),
    )

    runner._record_pytest_collection_failure(
        state,
        SimpleNamespace(failed=True, nodeid=nodeid),
    )

    assert state.unavailable is True
    assert state.failures == []


def test_locked_runtime_collection_failure_uses_authoritative_inventory(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """Catches locked runtime dropping collection paths without import env."""
    runner = importlib.import_module("scripts.run_coverage_gate")
    repository = tmp_path / "repository"
    source_root = tmp_path / "bootstrap" / "committed-source"
    build_backend = tmp_path / "bootstrap" / "build-backend"
    (source_root / "scripts").mkdir(parents=True)
    (source_root / "src" / "hsconfig").mkdir(parents=True)
    (source_root / "tests").mkdir()
    build_backend.mkdir()
    shutil.copy2(
        ROOT / "scripts" / "run_coverage_gate.py",
        source_root / "scripts" / "run_coverage_gate.py",
    )
    (source_root / "src" / "hsconfig" / "__init__.py").write_text(
        "SOURCE_MARKER = 'committed-source'\n",
        encoding="utf-8",
    )
    (source_root / "tests" / "__init__.py").write_text("\n", encoding="utf-8")
    (source_root / "tests" / "test_collection.py").write_text(
        "raise RuntimeError('SECRET_LOCKED_COLLECTION')\n\n"
        "def test_unreached():\n"
        "    pass\n",
        encoding="utf-8",
    )
    (source_root / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\naddopts = ''\n",
        encoding="utf-8",
    )
    repository.mkdir()
    for source in sorted(path for path in source_root.rglob("*") if path.is_file()):
        destination = repository / source.relative_to(source_root)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    git_environment = {
        key: value
        for key, value in os.environ.items()
        if not key.upper().startswith("GIT_")
    }
    for command in (
        ("git", "init", "-q"),
        ("git", "config", "user.email", "coverage@example.invalid"),
        ("git", "config", "user.name", "Coverage Contract"),
        ("git", "config", "core.autocrlf", "false"),
        ("git", "add", "."),
        ("git", "commit", "-q", "-m", "fixture"),
    ):
        subprocess.run(
            command,
            cwd=repository,
            env=git_environment,
            check=True,
            capture_output=True,
        )
    commit_oid = subprocess.run(
        ("git", "rev-parse", "HEAD"),
        cwd=repository,
        env=git_environment,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.strip()
    tree_oid = subprocess.run(
        ("git", "rev-parse", "HEAD^{tree}"),
        cwd=repository,
        env=git_environment,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.strip()
    inventory = tuple(
        (
            path.relative_to(source_root).as_posix(),
            hashlib.sha256(path.read_bytes()).hexdigest(),
            runner._runtime_git_mode(path.stat().st_mode) or "100644",
        )
        for path in sorted(path for path in source_root.rglob("*") if path.is_file())
    )
    binding = _test_coverage_runtime_binding(
        runner,
        repository=repository,
        source_root=source_root,
        build_backend_root=build_backend,
        source_inventory=inventory,
        commit_oid=commit_oid,
        tree_oid=tree_oid,
    )
    monkeypatch.setattr(runner, "ROOT", source_root.resolve(strict=True))

    with runner.isolated_coverage_environment(binding) as run:
        assert runner._PYTEST_IMPORT_INVENTORY not in run.environment
        assert runner._PYTEST_IMPORT_INVENTORY_SHA256 not in run.environment
        completed = subprocess.run(
            (
                str(run.locked_test_runtime.interpreter),
                "-m",
                "pytest",
                f"--rootdir={repository}",
                "-c",
                str(repository / "pyproject.toml"),
                "-p",
                "no:cacheprovider",
                "-p",
                "scripts.run_coverage_gate",
                f"{runner._PYTEST_FAILURE_SIDEBAND_OPTION}={run.failure_sideband}",
                str(repository / "tests" / "test_collection.py"),
                "-q",
            ),
            cwd=repository,
            env=run.environment,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=120,
        )
        report = runner._load_pytest_failure_sideband(
            run.run_root,
            run.failure_sideband,
            run.run_identity,
            run.failure_sideband_identity,
            allowed_identities=frozenset(
                {("tests/test_collection.py", None, "test_unreached")}
            ),
            allowed_collection_paths=frozenset({"tests/test_collection.py"}),
        )

    assert completed.returncode == 2
    assert report.status is runner._PytestFailureSidebandStatus.VALID
    assert report.identities == ("tests/test_collection.py phase=collection",)
    assert "SECRET_LOCKED_COLLECTION" not in run.failure_sideband.name


def test_post_configure_rmtree_replacement_fails_closed(
    tmp_path: Path,
) -> None:
    """Catches replacement of the exact session-bound cleanup callable."""
    runner = importlib.import_module("scripts.run_coverage_gate")
    run_root = tmp_path / "run"
    repository = run_root / "repository"
    tests_root = repository / "tests"
    tests_root.mkdir(parents=True)
    (tests_root / "test_replace.py").write_text(
        "def test_replace():\n"
        "    import _pytest.tmpdir\n"
        "    _pytest.tmpdir.rmtree = lambda *args, **kwargs: None\n"
        "    assert True\n",
        encoding="utf-8",
    )
    sideband = run_root / runner.PYTEST_FAILURE_SIDEBAND_NAME
    sideband.touch()
    sideband_identity = (sideband.stat().st_dev, sideband.stat().st_ino)
    run_identity = runner._coverage_directory_identity(run_root)
    command, environment = _failure_plugin_command(runner, repository, sideband)

    completed = subprocess.run(
        command,
        cwd=repository,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    report = runner._load_pytest_failure_sideband(
        run_root,
        sideband,
        run_identity,
        sideband_identity,
        allowed_identities=frozenset(
            {("tests/test_replace.py", None, "test_replace")}
        ),
    )

    assert completed.returncode == 2
    assert report.status is runner._PytestFailureSidebandStatus.RECORDER_UNAVAILABLE
    assert "lambda" not in sideband.read_text(encoding="utf-8")


def test_post_configure_rmtree_replacement_is_never_invoked(
    tmp_path: Path,
) -> None:
    """Catches Pytest builtin cleanup calling foreign code before postcheck."""
    runner = importlib.import_module("scripts.run_coverage_gate")
    run_root = tmp_path / "run"
    repository = run_root / "repository"
    tests_root = repository / "tests"
    tests_root.mkdir(parents=True)
    invocation_count = run_root / "foreign-rmtree-count.txt"
    invocation_count.write_text("0", encoding="ascii")
    (tests_root / "test_replace.py").write_text(
        "import os\n"
        "from pathlib import Path\n\n"
        "def test_replace(tmp_path):\n"
        "    import _pytest.tmpdir\n"
        "    count = Path(os.environ['HSCONFIG_FOREIGN_RMTREE_COUNT'])\n"
        "    def foreign(*args, **kwargs):\n"
        "        del args, kwargs\n"
        "        count.write_text(str(int(count.read_text()) + 1))\n"
        "    _pytest.tmpdir.rmtree = foreign\n"
        "    (tmp_path / 'owned.txt').write_text('owned')\n"
        "    assert True\n",
        encoding="utf-8",
    )
    sideband = run_root / runner.PYTEST_FAILURE_SIDEBAND_NAME
    sideband.touch()
    sideband_identity = (sideband.stat().st_dev, sideband.stat().st_ino)
    run_identity = runner._coverage_directory_identity(run_root)
    pytest_temp_parent = run_root / "pytest-temp"
    pytest_temp_parent.mkdir()
    command, environment = _failure_plugin_command(
        runner,
        repository,
        sideband,
        "-o",
        "tmp_path_retention_policy=failed",
    )
    environment["PYTEST_DEBUG_TEMPROOT"] = str(pytest_temp_parent)
    environment["HSCONFIG_FOREIGN_RMTREE_COUNT"] = str(invocation_count)

    completed = subprocess.run(
        command,
        cwd=repository,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    report = runner._load_pytest_failure_sideband(
        run_root,
        sideband,
        run_identity,
        sideband_identity,
        allowed_identities=frozenset(
            {("tests/test_replace.py", None, "test_replace")}
        ),
    )

    assert completed.returncode == 2
    assert invocation_count.read_text(encoding="ascii") == "0"
    assert report.status is runner._PytestFailureSidebandStatus.RECORDER_UNAVAILABLE
    assert all(
        child.is_dir() and not any(child.iterdir())
        for child in pytest_temp_parent.iterdir()
    )


def test_pytest_unconfigure_uses_config_state_when_module_global_is_shadowed(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """Catches unconfigure losing cleanup authority with the diagnostic global."""
    runner = importlib.import_module("scripts.run_coverage_gate")
    restored = object()
    temporary_module = SimpleNamespace()
    state = runner._PytestFailureState(
        repository_root=tmp_path.resolve(strict=True),
        sideband=tmp_path / runner.PYTEST_FAILURE_SIDEBAND_NAME,
        pytest_tmpdir_module=temporary_module,
        original_pytest_rmtree=restored,
    )
    bound = runner._BoundPytestSecureRmtree(state)
    state.bound_pytest_rmtree = bound
    temporary_module.rmtree = bound
    stash = {runner._PYTEST_FAILURE_STATE_KEY: state}
    config = SimpleNamespace(stash=stash)
    monkeypatch.setattr(runner, "_ACTIVE_PYTEST_FAILURE_STATE", None)

    runner.pytest_unconfigure(config)

    assert temporary_module.rmtree is restored
    assert runner._PYTEST_FAILURE_STATE_KEY not in stash


def test_pytest_cleanup_binding_uses_interpreter_sys_after_runner_sys_shadowing(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """Catches the reporter crashing when Windows identity tests shadow runner.sys."""
    import _pytest.tmpdir as pytest_tmpdir

    runner = importlib.import_module("scripts.run_coverage_gate")
    state = runner._PytestFailureState(
        repository_root=tmp_path.resolve(strict=True),
        sideband=tmp_path / runner.PYTEST_FAILURE_SIDEBAND_NAME,
        pytest_tmpdir_module=pytest_tmpdir,
        original_pytest_rmtree=pytest_tmpdir.rmtree,
    )
    bound = runner._BoundPytestSecureRmtree(state)
    state.bound_pytest_rmtree = bound
    class VersionedSys:
        version_info = (3, 11)

    # Restore both mutable module authorities before the outer reporter's call hook.
    with monkeypatch.context() as scoped:
        scoped.setattr(pytest_tmpdir, "rmtree", bound)
        scoped.setattr(runner, "sys", VersionedSys())

        assert runner._pytest_cleanup_binding_intact(state) is True
        assert runner._bind_pytest_cleanup_for_hook_chain(state) is True


def test_pytest_unconfigure_does_not_clobber_foreign_cleanup_callable(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """Catches unconfigure hiding a post-configure cleanup replacement."""
    runner = importlib.import_module("scripts.run_coverage_gate")
    restored = object()
    foreign = object()
    temporary_module = SimpleNamespace(rmtree=foreign)
    sideband = tmp_path / runner.PYTEST_FAILURE_SIDEBAND_NAME
    sideband.touch()
    state = runner._PytestFailureState(
        repository_root=tmp_path.resolve(strict=True),
        sideband=sideband,
        pytest_tmpdir_module=temporary_module,
        original_pytest_rmtree=restored,
    )
    state.bound_pytest_rmtree = runner._BoundPytestSecureRmtree(state)
    stash = {runner._PYTEST_FAILURE_STATE_KEY: state}
    config = SimpleNamespace(
        stash=stash,
        pluginmanager=SimpleNamespace(unregister=lambda plugin: None),
    )
    monkeypatch.setattr(runner, "_ACTIVE_PYTEST_FAILURE_STATE", None)

    runner.pytest_unconfigure(config)

    assert temporary_module.rmtree is foreign
    assert state.unavailable is True
    assert b'"recorder_status":"unavailable"' in sideband.read_bytes()
    assert runner._PYTEST_FAILURE_STATE_KEY not in stash


@pytest.mark.parametrize(
    ("kind", "expected_status", "expected_stderr"),
    (
        (
            "valid-empty",
            "VALID",
            "pytest failure identity: session-level failure; no node identities\n",
        ),
        ("missing", "MISSING", "pytest failure sideband missing\n"),
        ("invalid", "INVALID_SCHEMA", "pytest failure sideband schema invalid\n"),
    ),
)
def test_pytest_failure_sideband_distinguishes_empty_missing_and_invalid(
    tmp_path: Path,
    capsys,
    kind: str,
    expected_status: str,
    expected_stderr: str,
) -> None:
    """Catches valid empty evidence collapsing into missing or malformed evidence."""
    runner = importlib.import_module("scripts.run_coverage_gate")
    run_root = tmp_path / kind
    run_root.mkdir()
    sideband = run_root / runner.PYTEST_FAILURE_SIDEBAND_NAME
    sideband.touch()
    sideband_identity = (sideband.stat().st_dev, sideband.stat().st_ino)
    run_identity = runner._coverage_directory_identity(run_root)
    if kind == "valid-empty":
        sideband.write_bytes(
            b'{"failures":[],"recorder_status":"available",'
            b'"schema_version":1,"truncated":false}\n'
        )
    elif kind == "missing":
        sideband.unlink()
    else:
        sideband.write_bytes(b"{\n")

    report = runner._load_pytest_failure_sideband(
        run_root,
        sideband,
        run_identity,
        sideband_identity,
        allowed_identities=frozenset(),
    )
    runner._emit_pytest_failure_identities(report)

    assert report.status.name == expected_status
    assert report.identities == ()
    assert report.truncated is False
    assert capsys.readouterr().err == expected_stderr


def test_pytest_failure_sideband_reports_bound_file_read_failure(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    capsys,
) -> None:
    """Catches a post-binding IO failure being mislabeled as schema or binding."""
    runner = importlib.import_module("scripts.run_coverage_gate")
    run_root = tmp_path / "run"
    run_root.mkdir()
    sideband = run_root / runner.PYTEST_FAILURE_SIDEBAND_NAME
    sideband.touch()
    sideband_identity = (sideband.stat().st_dev, sideband.stat().st_ino)
    run_identity = runner._coverage_directory_identity(run_root)

    def fail_read(*args: object, **kwargs: object):
        del args, kwargs
        raise OSError("private read detail")

    monkeypatch.setattr(runner, "_read_bound_regular_file", fail_read)
    report = runner._load_pytest_failure_sideband(
        run_root,
        sideband,
        run_identity,
        sideband_identity,
        allowed_identities=frozenset(),
    )
    runner._emit_pytest_failure_identities(report)

    assert report.status is runner._PytestFailureSidebandStatus.IO_ERROR
    captured = capsys.readouterr()
    assert captured.err == "pytest failure sideband read failed\n"
    assert "private" not in captured.err


@pytest.mark.parametrize(
    ("path", "function"),
    (
        ("tests/test_LEAKEDSECRET.py", "test_LEAKEDSECRET"),
        ("tests/test_public.py", "test_LEAKEDSECRET"),
    ),
)
def test_pytest_failure_sideband_rejects_uncommitted_safe_identifiers(
    tmp_path: Path,
    path: str,
    function: str,
) -> None:
    """Catches safe-looking but non-source-backed diagnostic identities."""
    runner = importlib.import_module("scripts.run_coverage_gate")
    run_root = tmp_path / "run"
    run_root.mkdir()
    sideband = run_root / runner.PYTEST_FAILURE_SIDEBAND_NAME
    sideband.touch()
    sideband_identity = (sideband.stat().st_dev, sideband.stat().st_ino)
    run_identity = runner._coverage_directory_identity(run_root)
    document = {
        "schema_version": 1,
        "recorder_status": "available",
        "failures": [
            {
                "path": path,
                "class": None,
                "function": function,
                "parameter": None,
                "phase": "call",
            }
        ],
        "truncated": False,
    }
    sideband.write_bytes((json.dumps(document) + "\n").encode())

    report = _call_failure_sideband_loader(
        runner,
        run_root,
        sideband,
        run_identity,
        sideband_identity,
        frozenset({("tests/test_public.py", None, "test_public")}),
    )

    assert report.status is runner._PytestFailureSidebandStatus.INVALID_SCHEMA


def test_pytest_failure_sideband_treats_excessive_json_depth_as_unavailable(
    tmp_path: Path,
) -> None:
    """Catches RecursionError escaping the bounded Sideband loader."""
    runner = importlib.import_module("scripts.run_coverage_gate")
    run_root = tmp_path / "run"
    run_root.mkdir()
    sideband = run_root / runner.PYTEST_FAILURE_SIDEBAND_NAME
    sideband.touch()
    sideband_identity = (sideband.stat().st_dev, sideband.stat().st_ino)
    run_identity = runner._coverage_directory_identity(run_root)
    depth = sys.getrecursionlimit() + 100
    source = (
        b'{"schema_version":1,"failures":'
        + b"[" * depth
        + b"0"
        + b"]" * depth
        + b',"truncated":false}\n'
    )
    assert len(source) < runner.MAX_PYTEST_FAILURE_SIDEBAND_BYTES
    sideband.write_bytes(source)

    try:
        report = _call_failure_sideband_loader(
            runner,
            run_root,
            sideband,
            run_identity,
            sideband_identity,
            frozenset(),
        )
    except RecursionError:
        report = "recursion escaped"

    assert report.status is runner._PytestFailureSidebandStatus.INVALID_SCHEMA


def test_coverage_runner_fails_closed_for_excessive_sideband_depth(
    monkeypatch: MonkeyPatch,
    capsys,
) -> None:
    """Catches invalid diagnostic JSON being accepted as authoritative evidence."""
    runner = importlib.import_module("scripts.run_coverage_gate")
    monkeypatch.setattr(runner, "_assert_runtime_matches_lock", lambda lock: None)
    depth = sys.getrecursionlimit() + 100
    source = (
        b'{"schema_version":1,"failures":'
        + b"[" * depth
        + b"0"
        + b"]" * depth
        + b',"truncated":false}\n'
    )

    def fake_run(command: tuple[str, ...], **kwargs: object) -> runner._PytestResult:
        del kwargs
        sideband = Path(
            next(
                argument
                for argument in command
                if argument.startswith("--hsconfig-failure-sideband=")
            ).removeprefix("--hsconfig-failure-sideband=")
        )
        sideband.write_bytes(source)
        return runner._PytestResult(returncode=1, timed_out=False)

    monkeypatch.setattr(runner, "_run_pytest_bounded", fake_run)

    assert _run_unit_coverage_main(runner) == 2
    captured = capsys.readouterr()
    assert captured.err == "pytest failure sideband schema invalid\n"
    assert captured.out.count("\n") == 1
    assert json.loads(captured.out) == {
        "critical_modules": [],
        "errors": ["pytest coverage execution failed"],
        "global_branch_percent": None,
        "global_covered_branches": None,
        "global_num_branches": None,
        "global_minimum": 89.0,
        "passed": False,
        "returncode": 2,
        "target_met": False,
    }


def test_pytest_failure_sideband_reports_only_safe_exact_identities(
    tmp_path: Path,
) -> None:
    """Catches raw failure text, parameter IDs, or incorrect pytest phases."""
    runner = importlib.import_module("scripts.run_coverage_gate")
    run_root = tmp_path / "run"
    repository = run_root / "repository"
    tests_root = repository / "tests"
    tests_root.mkdir(parents=True)
    (tests_root / "test_failures.py").write_text(
        """
import pytest

def test_plain():
    assert False, "SECRET_PLAIN C:" + "/private/assertion.txt"

class TestCases:
    @pytest.mark.parametrize("value", [0, 1, 2], ids=["safe", "SECRET_ID", "tail"])
    def test_param(self, value):
        assert value != 1, "TOKEN=raw-parameter C:" + "/private/parameter.txt"

@pytest.fixture
def setup_failure():
    raise RuntimeError("SECRET_SETUP C:" + "/private/setup.txt")

def test_setup(setup_failure):
    pass

@pytest.fixture
def teardown_failure():
    yield
    raise RuntimeError("SECRET_TEARDOWN C:" + "/private/teardown.txt")

def test_teardown(teardown_failure):
    pass
""".lstrip(),
        encoding="utf-8",
    )
    sideband = run_root / runner.PYTEST_FAILURE_SIDEBAND_NAME
    sideband.touch()
    sideband_identity = (sideband.stat().st_dev, sideband.stat().st_ino)
    run_identity = runner._coverage_directory_identity(run_root)
    command, environment = _failure_plugin_command(runner, repository, sideband)

    completed = subprocess.run(
        command,
        cwd=repository,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    report = runner._load_pytest_failure_sideband(
        run_root,
        sideband,
        run_identity,
        sideband_identity,
        allowed_identities=runner._pytest_test_identity_allowlist(
            repository,
            source_inventory=_test_python_source_inventory(runner, repository),
        ),
    )

    assert completed.returncode == 1
    assert report is not None
    assert report.identities == (
        "tests/test_failures.py::test_plain phase=call",
        "tests/test_failures.py::TestCases::test_param parameter=2/3 phase=call",
        "tests/test_failures.py::test_setup phase=setup",
        "tests/test_failures.py::test_teardown phase=teardown",
    )
    assert report.truncated is False
    source = sideband.read_text(encoding="utf-8")
    assert "SECRET" not in source
    assert "TOKEN" not in source
    assert "assertion" not in source
    assert str(tmp_path) not in source


@pytest.mark.parametrize(
    "kind",
    (
        "missing",
        "malformed",
        "duplicate-key",
        "oversize",
        "extra-key",
        "wrong-type",
        "too-many",
        "unsafe-path",
        "unsafe-identifier",
        "unsafe-parameter",
        "duplicate-record",
        "forged-path",
        "replaced",
        "linked",
    ),
)
def test_pytest_failure_sideband_rejects_unavailable_or_unsafe_evidence(
    tmp_path: Path,
    kind: str,
    capsys,
) -> None:
    """Catches trust in malformed, escaped, or non-single-link sidebands."""
    runner = importlib.import_module("scripts.run_coverage_gate")
    run_root = tmp_path / "run"
    run_root.mkdir()
    expected = run_root / runner.PYTEST_FAILURE_SIDEBAND_NAME
    expected.touch()
    sideband_identity = (expected.stat().st_dev, expected.stat().st_ino)
    candidate = expected
    document = _valid_failure_sideband_document()
    if kind == "missing":
        expected.unlink()
    elif kind == "malformed":
        expected.write_bytes(b"{\n")
    elif kind == "duplicate-key":
        expected.write_bytes(
            b'{"schema_version":1,"schema_version":1,'
            b'"failures":[],"truncated":false}\n'
        )
    elif kind == "oversize":
        expected.write_bytes(b"x" * (runner.MAX_PYTEST_FAILURE_SIDEBAND_BYTES + 1))
    elif kind == "extra-key":
        document["extra"] = False
        expected.write_bytes((json.dumps(document) + "\n").encode())
    elif kind == "wrong-type":
        document["truncated"] = 0
        expected.write_bytes((json.dumps(document) + "\n").encode())
    elif kind == "too-many":
        document = _valid_failure_sideband_document(
            count=runner.MAX_PYTEST_FAILURE_IDENTITIES + 1,
            truncated=True,
        )
        expected.write_bytes((json.dumps(document) + "\n").encode())
    elif kind == "unsafe-path":
        document["failures"][0]["path"] = "C:" + "/private/SECRET.py"
        expected.write_bytes((json.dumps(document) + "\n").encode())
    elif kind == "unsafe-identifier":
        document["failures"][0]["function"] = "test_failure[SECRET]"
        expected.write_bytes((json.dumps(document) + "\n").encode())
    elif kind == "unsafe-parameter":
        document["failures"][0]["parameter"] = {"ordinal": 0, "total": 1}
        expected.write_bytes((json.dumps(document) + "\n").encode())
    elif kind == "duplicate-record":
        document["failures"].append(dict(document["failures"][0]))
        expected.write_bytes((json.dumps(document) + "\n").encode())
    elif kind == "forged-path":
        candidate = run_root / "forged.json"
        candidate.write_bytes((json.dumps(document) + "\n").encode())
        sideband_identity = (candidate.stat().st_dev, candidate.stat().st_ino)
    elif kind == "replaced":
        expected.unlink()
        expected.write_bytes((json.dumps(document) + "\n").encode())
    elif kind == "linked":
        expected.unlink()
        target = run_root / "target.json"
        target.write_bytes((json.dumps(document) + "\n").encode())
        os.link(target, expected)
        sideband_identity = (expected.stat().st_dev, expected.stat().st_ino)
    run_identity = runner._coverage_directory_identity(run_root)

    report = runner._load_pytest_failure_sideband(
        run_root,
        candidate,
        run_identity,
        sideband_identity,
        allowed_identities=frozenset(
            {
                (
                    "tests/test_coverage_contract.py",
                    None,
                    "test_coverage_runner_propagates_failure_and_cleans_temp_directory",
                )
            }
        ),
    )
    runner._emit_pytest_failure_identities(report)

    binding_kinds = {"oversize", "forged-path", "replaced", "linked"}
    expected_status = (
        runner._PytestFailureSidebandStatus.MISSING
        if kind == "missing"
        else (
            runner._PytestFailureSidebandStatus.INVALID_BINDING
            if kind in binding_kinds
            else runner._PytestFailureSidebandStatus.INVALID_SCHEMA
        )
    )
    assert report.status is expected_status
    captured = capsys.readouterr()
    assert captured.out == ""
    expected_message = {
        runner._PytestFailureSidebandStatus.MISSING: "pytest failure sideband missing\n",
        runner._PytestFailureSidebandStatus.INVALID_BINDING: (
            "pytest failure sideband binding invalid\n"
        ),
        runner._PytestFailureSidebandStatus.INVALID_SCHEMA: (
            "pytest failure sideband schema invalid\n"
        ),
    }[expected_status]
    assert captured.err == expected_message


def test_pytest_failure_sideband_survives_large_redacted_transport(
    tmp_path: Path,
    capsys,
) -> None:
    """Catches loss of safe identity when prior pytest stdout exceeds 64 KiB."""
    runner = importlib.import_module("scripts.run_coverage_gate")
    run_root = tmp_path / "run"
    repository = run_root / "repository"
    tests_root = repository / "tests"
    tests_root.mkdir(parents=True)
    (tests_root / "test_large.py").write_text(
        "def test_large():\n"
        "    print('SECRET_OUTPUT C:' + '/private/' + 'x' * 70000)\n"
        "    assert False, 'SECRET_ASSERTION'\n",
        encoding="utf-8",
    )
    sideband = run_root / runner.PYTEST_FAILURE_SIDEBAND_NAME
    sideband.touch()
    sideband_identity = (sideband.stat().st_dev, sideband.stat().st_ino)
    run_identity = runner._coverage_directory_identity(run_root)
    command, environment = _failure_plugin_command(
        runner,
        repository,
        sideband,
        "-s",
    )

    result = runner._run_pytest_bounded(command, cwd=repository, env=environment)
    report = runner._load_pytest_failure_sideband(
        run_root,
        sideband,
        run_identity,
        sideband_identity,
        allowed_identities=runner._pytest_test_identity_allowlist(
            repository,
            source_inventory=_test_python_source_inventory(runner, repository),
        ),
    )

    assert result.returncode == 1
    assert result.timed_out is False
    assert report is not None
    assert report.identities == ("tests/test_large.py::test_large phase=call",)
    captured = capsys.readouterr()
    assert "SECRET" not in captured.err
    assert str(tmp_path) not in captured.err
    assert "pytest stdout diagnostic bytes=" in captured.err
    assert "truncated=true" in captured.err
    assert captured.out == ""


def test_pytest_failure_sideband_caps_many_failures(
    tmp_path: Path,
) -> None:
    """Catches unbounded failure identity collection or raw parameter IDs."""
    runner = importlib.import_module("scripts.run_coverage_gate")
    run_root = tmp_path / "run"
    repository = run_root / "repository"
    tests_root = repository / "tests"
    tests_root.mkdir(parents=True)
    failure_count = runner.MAX_PYTEST_FAILURE_IDENTITIES + 7
    (tests_root / "test_many.py").write_text(
        "import pytest\n"
        f"@pytest.mark.parametrize('value', range({failure_count}))\n"
        "def test_many(value):\n"
        "    assert False, f'SECRET-{value}'\n",
        encoding="utf-8",
    )
    sideband = run_root / runner.PYTEST_FAILURE_SIDEBAND_NAME
    sideband.touch()
    sideband_identity = (sideband.stat().st_dev, sideband.stat().st_ino)
    run_identity = runner._coverage_directory_identity(run_root)
    command, environment = _failure_plugin_command(runner, repository, sideband)

    completed = subprocess.run(
        command,
        cwd=repository,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    report = runner._load_pytest_failure_sideband(
        run_root,
        sideband,
        run_identity,
        sideband_identity,
        allowed_identities=runner._pytest_test_identity_allowlist(
            repository,
            source_inventory=_test_python_source_inventory(runner, repository),
        ),
    )

    assert completed.returncode == 1
    assert report is not None
    assert len(report.identities) == runner.MAX_PYTEST_FAILURE_IDENTITIES
    assert report.truncated is True
    assert all("SECRET" not in identity for identity in report.identities)


def test_coverage_runner_uses_unique_temp_directories_and_exact_gate(
    monkeypatch: MonkeyPatch,
    capsys,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    calls: list[dict[str, object]] = []
    checker_commands: list[tuple[str, ...]] = []
    monkeypatch.setenv(
        "PYTEST_ADDOPTS",
        "--no-cov --cov-fail-under=0 --cov-config=other.toml",
    )
    monkeypatch.setattr(runner, "_assert_runtime_matches_lock", lambda lock: None)

    def fake_run(command: tuple[str, ...], **kwargs: object) -> runner._PytestResult:
        assert command[1:3] == ("-m", "pytest")
        environment = kwargs["env"]
        assert isinstance(environment, dict)
        coverage_file = Path(str(environment["COVERAGE_FILE"]))
        report_argument = next(
            argument for argument in command if argument.startswith("--cov-report=json:")
        )
        coverage_json = Path(report_argument.removeprefix("--cov-report=json:"))
        coverage_json.write_text("{}", encoding="utf-8")
        calls.append(
            {
                "command": command,
                "cwd": kwargs["cwd"],
                "coverage_file": coverage_file,
                "coverage_json": coverage_json,
                "directory_existed": coverage_file.parent.is_dir(),
                "pytest_addopts_present": "PYTEST_ADDOPTS" in environment,
            }
        )
        return runner._PytestResult(returncode=0, timed_out=False)

    def fake_checker(
        command: tuple[str, ...], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        checker_commands.append(command)
        assert kwargs["input_bytes"] == b"{}"
        return subprocess.CompletedProcess(command, 0, stdout=json.dumps(_checker_document()), stderr="")

    monkeypatch.setattr(runner, "_run_pytest_bounded", fake_run)
    monkeypatch.setattr(runner, "_run_checker_bounded", fake_checker)

    for _ in range(2):
        assert _run_unit_coverage_main(runner) == 0
    capsys.readouterr()

    assert len(checker_commands) == 2
    assert all(call["cwd"] == ROOT for call in calls)
    coverage_files = [call["coverage_file"] for call in calls]
    coverage_jsons = [call["coverage_json"] for call in calls]
    assert coverage_files[0] != coverage_files[1]
    assert coverage_jsons[0] != coverage_jsons[1]
    assert all(path.is_absolute() for path in coverage_files)
    assert all(ROOT not in path.parents for path in coverage_files)
    assert all(ROOT not in path.parents for path in coverage_jsons)
    assert all(data.parent == report.parent for data, report in zip(
        coverage_files, coverage_jsons, strict=True
    ))
    assert all(call["directory_existed"] is True for call in calls)
    assert all(call["pytest_addopts_present"] is False for call in calls)
    assert all(not path.parent.exists() for path in coverage_files)
    assert all(command[1:3] == ("-c", runner.CHECKER_BRIDGE) for command in checker_commands)
    assert not (ROOT / "coverage.json").exists()


def test_committed_coverage_runner_starts_pytest_in_exact_checkout(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    capsys,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    repository = tmp_path / "repository"
    committed_source = tmp_path / "bootstrap" / "committed-source"
    build_backend = tmp_path / "bootstrap" / "build-backend"
    repository.mkdir()
    committed_source.mkdir(parents=True)
    build_backend.mkdir()
    tests_root = committed_source / "tests"
    tests_root.mkdir()
    (tests_root / "test_probe.py").write_text(
        "def test_probe():\n    pass\n",
        encoding="utf-8",
    )
    repository_tests = repository / "tests"
    repository_tests.mkdir()
    (repository_tests / "test_probe.py").write_bytes(
        b"def test_probe():\r\n    pass\r\n"
    )
    binding = _test_coverage_runtime_binding(
        runner,
        repository=repository,
        source_root=committed_source,
        build_backend_root=build_backend,
        source_inventory=_test_python_source_inventory(runner, committed_source),
    )
    captured: dict[str, object] = {}
    allowlist_roots: list[Path] = []
    monkeypatch.setattr(runner, "ROOT", committed_source.resolve(strict=True))
    monkeypatch.setattr(runner, "_assert_runtime_matches_lock", lambda lock: binding)
    monkeypatch.setattr(runner, "_assert_locked_test_runtime", lambda locked: None)
    original_allowlist = runner._pytest_test_identity_allowlist

    def recording_allowlist(repository_root: Path, **kwargs: object):
        allowlist_roots.append(repository_root)
        return original_allowlist(repository_root, **kwargs)

    monkeypatch.setattr(runner, "_pytest_test_identity_allowlist", recording_allowlist)

    def fake_run(command: tuple[str, ...], **kwargs: object) -> runner._PytestResult:
        assert command[1:3] == ("-m", "pytest")
        captured["command"] = command
        captured.update(kwargs)
        return runner._PytestResult(returncode=7, timed_out=False)

    monkeypatch.setattr(runner, "_run_pytest_bounded", fake_run)

    assert runner.main() == 2
    capsys.readouterr()
    environment = captured["env"]
    assert isinstance(environment, dict)
    command = captured["command"]
    assert isinstance(command, tuple)
    assert allowlist_roots == [committed_source.resolve(strict=True)]
    assert captured["cwd"] == repository.resolve(strict=True)
    assert captured["locked_runtime"] is not None
    assert f"--rootdir={repository.resolve(strict=True)}" in command
    assert command[command.index("-c") + 1] == str(
        repository.resolve(strict=True) / "pyproject.toml"
    )
    assert command[-1] == str(
        repository.resolve(strict=True) / "tests" / "test_probe.py"
    )
    assert f"--cov={committed_source.resolve(strict=True) / 'src' / 'hsconfig'}" in command
    assert (
        f"--cov-config={committed_source.resolve(strict=True) / 'pyproject.toml'}"
        in command
    )
    assert environment["PYTHONPATH"].split(os.pathsep) == [
        str(committed_source.resolve(strict=True)),
        str(build_backend.resolve(strict=True)),
    ]
    repository_binding = json.loads(
        environment["HSCONFIG_COVERAGE_TEST_REPOSITORY_BINDING"]
    )
    assert repository_binding["repository"] == str(repository.resolve(strict=True))
    assert repository_binding["commit_oid"] == "a" * 40
    assert repository_binding["tree_oid"] == "b" * 40


def test_locked_coverage_environment_closes_path_to_bound_test_tools(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """Break caught: locked Pytest resolves literal python outside its venv."""
    runner = importlib.import_module("scripts.run_coverage_gate")
    source_root = tmp_path / "bootstrap" / "committed-source"
    build_backend = tmp_path / "bootstrap" / "build-backend"
    repository = tmp_path / "repository"
    source_root.mkdir(parents=True)
    build_backend.mkdir()
    repository.mkdir()
    original_path = os.environ["PATH"]
    ambient = tmp_path / "ambient-bin"
    ambient.mkdir()
    monkeypatch.setenv("PATH", str(ambient) + os.pathsep + original_path)
    binding = _test_coverage_runtime_binding(
        runner,
        repository=repository,
        source_root=source_root,
        build_backend_root=build_backend,
    )

    with runner.isolated_coverage_environment(binding) as run:
        closed_path = run.environment["PATH"].split(os.pathsep)
        locked_runtime = run.locked_test_runtime
        assert locked_runtime is not None
        resolved_python = shutil.which("python", path=run.environment["PATH"])
        assert resolved_python is not None
        assert Path(resolved_python).resolve(strict=True) == locked_runtime.interpreter
        resolved_pwsh = shutil.which("pwsh", path=run.environment["PATH"])
        assert resolved_pwsh is not None
        assert Path(resolved_pwsh).resolve(strict=True) == locked_runtime.pwsh_executable
        completed = subprocess.run(
            (
                str(locked_runtime.interpreter),
                "-c",
                "import sys; print(sys.executable)",
            ),
            cwd=source_root,
            env=run.environment,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        pwsh_completed = subprocess.run(
            (
                str(locked_runtime.pwsh_executable),
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                "[System.Environment]::ProcessPath",
            ),
            cwd=source_root,
            env=run.environment,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

    expected_path = [
        str(locked_runtime.interpreter.parent.resolve(strict=True)),
        str(locked_runtime.git_executable.parent.resolve(strict=True)),
        str(locked_runtime.pwsh_executable.parent.resolve(strict=True)),
    ]
    expected_path = list(dict.fromkeys(expected_path))
    assert closed_path == expected_path, (closed_path, expected_path)
    assert str(ambient) not in closed_path
    assert run.environment["VIRTUAL_ENV"] == str(locked_runtime.environment_root)
    assert run.environment["PYTHONSAFEPATH"] == "1"
    assert completed.returncode == 0, (completed.returncode, completed.stderr)
    observed_python = Path(completed.stdout.strip())
    assert observed_python.resolve(strict=True) == locked_runtime.interpreter, (
        observed_python.resolve(strict=True),
        locked_runtime.interpreter,
    )
    assert pwsh_completed.returncode == 0, (
        pwsh_completed.returncode,
        pwsh_completed.stderr,
    )
    observed_pwsh = Path(pwsh_completed.stdout.strip())
    assert observed_pwsh.resolve(strict=True) == locked_runtime.pwsh_executable, (
        observed_pwsh.resolve(strict=True),
        locked_runtime.pwsh_executable,
    )


def test_nested_coverage_isolation_rejects_environment_only_runtime_binding(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """Catches environment JSON self-authorizing an overlay without active state."""
    runner = importlib.import_module("scripts.run_coverage_gate")
    source_root = tmp_path / "bootstrap" / "committed-source"
    build_backend = tmp_path / "bootstrap" / "build-backend"
    repository = tmp_path / "repository"
    source_root.mkdir(parents=True)
    build_backend.mkdir()
    repository.mkdir()
    probe = build_backend / "locked_overlay_probe.py"
    probe.write_text("VALUE = 'bound-overlay'\n", encoding="utf-8")
    monkeypatch.setattr(runner, "ROOT", source_root.resolve(strict=True))
    binding = _test_coverage_runtime_binding(
        runner,
        repository=repository,
        source_root=source_root,
        build_backend_root=build_backend,
    )

    with runner.isolated_coverage_environment(binding) as outer:
        with monkeypatch.context() as nested_process:
            nested_process.setattr(runner, "_active_locked_test_runtime", lambda: None)
            for key in tuple(os.environ):
                nested_process.delenv(key, raising=False)
            for key, value in outer.environment.items():
                nested_process.setenv(key, value)
            with runner.isolated_coverage_environment() as nested:
                pass

    assert nested.locked_test_runtime is None
    assert "PYTHONPATH" not in nested.environment
    assert (
        "HSCONFIG_COVERAGE_LOCKED_TEST_RUNTIME_BINDING" not in nested.environment
    )


def test_explicit_coverage_binding_does_not_consult_outer_locked_runtime(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    source_root = tmp_path / "bootstrap" / "committed-source"
    build_backend = tmp_path / "bootstrap" / "build-backend"
    repository = tmp_path / "repository"
    source_root.mkdir(parents=True)
    build_backend.mkdir()
    repository.mkdir()
    binding = _test_coverage_runtime_binding(
        runner,
        repository=repository,
        source_root=source_root,
        build_backend_root=build_backend,
    )

    def reject_outer_state() -> None:
        raise AssertionError("explicit binding consulted outer locked runtime")

    monkeypatch.setattr(runner, "_active_locked_test_runtime", reject_outer_state)

    with runner.isolated_coverage_environment(binding) as run:
        assert run.locked_test_runtime is not None
        assert run.locked_test_runtime.repository_root == repository.resolve(
            strict=True
        )


def test_locked_runtime_rejects_overlay_changed_after_manifest_binding(
    tmp_path: Path,
) -> None:
    """Catches re-snapshotting a changed overlay as its own new authority."""
    runner = importlib.import_module("scripts.run_coverage_gate")
    source_root = tmp_path / "committed-source"
    build_backend = tmp_path / "build-backend"
    repository = tmp_path / "repository"
    source_root.mkdir()
    build_backend.mkdir()
    repository.mkdir()
    payload = build_backend / "coverage.py"
    payload.write_text("BOUND = True\n", encoding="utf-8")
    binding = _test_coverage_runtime_binding(
        runner,
        repository=repository,
        source_root=source_root,
        build_backend_root=build_backend,
    )
    payload.write_text("BOUND = False\n", encoding="utf-8")

    with pytest.raises(runner.CoverageGateError, match="overlay"):
        runner._locked_test_runtime_document(binding)


def test_locked_runtime_rejects_transport_document_digest_mismatch(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """Catches treating the runtime document and its authority as one value."""
    runner = importlib.import_module("scripts.run_coverage_gate")
    source_root = tmp_path / "committed-source"
    build_backend = tmp_path / "build-backend"
    repository = tmp_path / "repository"
    source_root.mkdir()
    build_backend.mkdir()
    repository.mkdir()
    binding = _test_coverage_runtime_binding(
        runner,
        repository=repository,
        source_root=source_root,
        build_backend_root=build_backend,
    )
    monkeypatch.setattr(runner, "ROOT", source_root.resolve(strict=True))
    document, _locked = runner._locked_test_runtime_document(binding)

    with pytest.raises(runner.CoverageGateError, match="binding is invalid"):
        runner._locked_test_runtime_binding(document, "0" * 64)


@pytest.mark.skipif(os.name != "nt", reason="Windows stat metadata contract")
def test_validated_runtime_file_accepts_only_stable_windows_312_metadata_skew() -> None:
    """Catches requiring deprecated Windows path/descriptor ``st_ctime_ns`` parity."""
    runner = importlib.import_module("scripts.run_coverage_gate")
    birthtime_ns = 1_785_424_132_318_810_300
    modified_ns = 1_785_424_132_319_811_200
    shared = {
        "st_dev": 1_321_366_511_338_633_693,
        "st_ino": 18_295_873_488_454_500,
        "st_size": 91_648,
        "st_mtime_ns": modified_ns,
        "st_birthtime_ns": birthtime_ns,
    }
    opened = SimpleNamespace(
        **shared,
        st_ctime_ns=modified_ns,
        st_mode=0o100666,
    )
    path_metadata = SimpleNamespace(
        **shared,
        st_ctime_ns=birthtime_ns,
        st_mode=0o100777,
    )

    assert runner._same_regular_file_identity(opened, path_metadata) is True
    for field in (
        "st_dev",
        "st_ino",
        "st_size",
        "st_mtime_ns",
        "st_birthtime_ns",
    ):
        changed = vars(opened).copy()
        changed[field] += 1
        assert (
            runner._same_regular_file_identity(
                SimpleNamespace(**changed),
                path_metadata,
            )
            is False
        )
    assert (
        runner._same_regular_file_identity(
            SimpleNamespace(**{**vars(opened), "st_mode": 0o040777}),
            path_metadata,
        )
        is False
    )
    assert (
        runner._same_regular_file_identity(
            opened,
            SimpleNamespace(**{**vars(path_metadata), "st_mode": 0o040777}),
        )
        is False
    )
    legacy_opened = vars(opened).copy()
    legacy_path = vars(path_metadata).copy()
    legacy_opened.pop("st_birthtime_ns")
    legacy_path.pop("st_birthtime_ns")
    assert (
        runner._same_regular_file_identity(
            SimpleNamespace(**legacy_opened),
            SimpleNamespace(**legacy_path),
        )
        is False
    )

    interpreter = Path(sys.executable).resolve(strict=True)
    resolved, identity, digest = runner._validated_runtime_file(
        interpreter,
        "python interpreter",
    )
    metadata = interpreter.lstat()
    assert resolved == interpreter
    assert (
        identity.device,
        identity.inode,
        identity.size,
        identity.modified_ns,
        identity.changed_ns,
        identity.mode,
    ) == (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
        metadata.st_mode,
    )
    assert digest == hashlib.sha256(interpreter.read_bytes()).hexdigest()


def test_locked_runtime_rejects_same_path_interpreter_replacement(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """Catches binding only the interpreter path without file identity."""
    runner = importlib.import_module("scripts.run_coverage_gate")
    source_root = tmp_path / "committed-source"
    build_backend = tmp_path / "build-backend"
    repository = tmp_path / "repository"
    interpreter_root = tmp_path / "interpreter"
    source_root.mkdir()
    build_backend.mkdir()
    repository.mkdir()
    interpreter_root.mkdir()
    interpreter = interpreter_root / ("python.exe" if os.name == "nt" else "python")
    shutil.copy2(sys.executable, interpreter)
    binding = _test_coverage_runtime_binding(
        runner,
        repository=repository,
        source_root=source_root,
        build_backend_root=build_backend,
    )
    monkeypatch.setattr(runner.sys, "executable", str(interpreter))

    with runner.isolated_coverage_environment(binding) as run:
        assert run.locked_test_runtime is not None
        original = interpreter.read_bytes()
        interpreter.unlink()
        interpreter.write_bytes(original)
        if os.name != "nt":
            interpreter.chmod(0o755)
        with pytest.raises(runner.CoverageGateError, match="tool binding"):
            runner._assert_locked_tool_binding(run.locked_test_runtime)


@pytest.mark.skipif(os.name == "nt", reason="POSIX executable symlink mechanics")
def test_validated_runtime_executable_accepts_bound_posix_symlink(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """Catches rejecting the normal /usr/bin/pwsh-style launcher symlink."""
    runner = importlib.import_module("scripts.run_coverage_gate")
    target_root = tmp_path / "opt" / "powershell"
    alias_root = tmp_path / "usr" / "bin"
    target_root.mkdir(parents=True)
    alias_root.mkdir(parents=True)
    target = target_root / "pwsh"
    target.write_bytes(b"#!/bin/sh\nexit 0\n")
    target.chmod(0o755)
    alias = alias_root / "pwsh"
    alias.symlink_to(target)
    monkeypatch.setenv("PATH", str(alias_root))

    executable, identity, digest = runner._validated_runtime_executable("pwsh")

    assert executable == target.resolve(strict=True)
    assert identity == runner._identity(target.lstat())
    assert digest == hashlib.sha256(target.read_bytes()).hexdigest()


@pytest.mark.skipif(os.name == "nt", reason="POSIX executable symlink mechanics")
def test_validated_runtime_executable_rejects_retargeted_posix_symlink(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """Catches accepting an alias retargeted during executable validation."""
    runner = importlib.import_module("scripts.run_coverage_gate")
    target_root = tmp_path / "opt" / "powershell"
    alias_root = tmp_path / "usr" / "bin"
    target_root.mkdir(parents=True)
    alias_root.mkdir(parents=True)
    target = target_root / "pwsh"
    replacement = target_root / "replacement-pwsh"
    for path in (target, replacement):
        path.write_bytes(b"#!/bin/sh\nexit 0\n")
        path.chmod(0o755)
    alias = alias_root / "pwsh"
    alias.symlink_to(target)
    monkeypatch.setenv("PATH", str(alias_root))
    original_read = runner._read_bound_regular_file

    def retargeting_read(path: Path, **kwargs):
        if Path(path).resolve(strict=True) == target.resolve(strict=True):
            alias.unlink()
            alias.symlink_to(replacement)
        return original_read(path, **kwargs)

    monkeypatch.setattr(runner, "_read_bound_regular_file", retargeting_read)

    with pytest.raises(runner.CoverageGateError, match="executable"):
        runner._validated_runtime_executable("pwsh")


@pytest.mark.skipif(os.name == "nt", reason="POSIX executable symlink mechanics")
def test_locked_launches_ignore_interpreter_alias_retarget_after_binding(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """Catches locked child and wrapper argv falling back to ``sys.executable``."""
    runner = importlib.import_module("scripts.run_coverage_gate")
    canonical = Path(sys.executable).resolve(strict=True)
    alias_root = tmp_path / "alias"
    source_root = tmp_path / "committed-source"
    build_backend = tmp_path / "build-backend"
    repository = tmp_path / "repository"
    outputs = tmp_path / "outputs"
    for directory in (
        alias_root,
        source_root,
        build_backend,
        repository,
        outputs,
    ):
        directory.mkdir()
    alias = alias_root / "python"
    alias.symlink_to(canonical)
    binding = _test_coverage_runtime_binding(
        runner,
        repository=repository,
        source_root=source_root,
        build_backend_root=build_backend,
    )
    monkeypatch.setattr(runner.sys, "executable", str(alias))

    with runner.isolated_coverage_environment(binding) as run:
        locked = run.locked_test_runtime
        assert locked is not None
        assert locked.interpreter == canonical
        alias.unlink()
        alias.symlink_to(Path("/bin/false"))

        runner._assert_locked_tool_binding(locked)
        pytest_command = runner._pytest_coverage_command(
            run.coverage_json,
            run.failure_sideband,
            interpreter=locked.interpreter,
            test_root=repository,
        )
        checker_command = runner._checker_command(interpreter=locked.interpreter)
        assert pytest_command[0] == str(canonical)
        assert checker_command[0] == str(canonical)

        actual_popen = subprocess.Popen
        started: list[tuple[str, ...]] = []

        def recording_popen(command, *args, **kwargs):
            started.append(tuple(command))
            return actual_popen(command, *args, **kwargs)

        monkeypatch.setattr(runner.subprocess, "Popen", recording_popen)
        bounded = runner._run_bounded_process(
            (str(canonical), "-c", "print('canonical-launch')"),
            cwd=tmp_path,
            env=os.environ.copy(),
            timeout=30,
            launcher=locked.interpreter,
            locked_runtime=locked,
        )
        assert bounded.completed.returncode == 0
        assert bounded.completed.stdout.strip() == "canonical-launch"
        assert started[0][0] == runner._process_tree_gate_interpreter(canonical)

        observed: dict[str, object] = {}

        def fake_bounded_process(command, **kwargs):
            observed["command"] = tuple(command)
            observed.update(kwargs)
            stdout = runner._BoundedCapture()
            stdout.drain(io.BytesIO(_bound_scan_result_bytes()))
            return runner._BoundedResult(
                completed=subprocess.CompletedProcess(
                    command,
                    0,
                    stdout=stdout.text(),
                    stderr="",
                ),
                timed_out=False,
                stdout=stdout,
                stderr=runner._BoundedCapture(),
            )

        monkeypatch.setattr(
            runner,
            "_active_locked_test_runtime",
            lambda: (locked, "{}", "0" * 64),
        )
        monkeypatch.setattr(runner, "_run_bounded_process", fake_bounded_process)
        runner._run_bound_coverage_scan(
            binding_json=_bound_scan_test_binding(runner, repository),
            outputs_root=outputs.resolve(strict=True),
            tree_mode="working-pre-cutover",
            build_distributions=False,
        )
        assert observed["command"][0] == str(canonical)
        assert observed["launcher"] == canonical


@pytest.mark.skipif(os.name != "nt", reason="Windows venv redirector semantics")
def test_windows_coverage_process_gate_uses_validated_base_interpreter(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    base_interpreter = tmp_path / "base-python.exe"
    base_interpreter.write_bytes(b"synthetic regular executable")
    redirector = tmp_path / "venv" / "Scripts" / "python.exe"
    monkeypatch.setattr(runner.sys, "_base_executable", str(base_interpreter))

    assert runner._process_tree_gate_interpreter(redirector) == str(
        base_interpreter.resolve(strict=True)
    )


@pytest.mark.skipif(os.name != "nt", reason="Windows venv redirector semantics")
@pytest.mark.parametrize("invalid_base", (None, "", "relative-python.exe"))
def test_windows_coverage_process_gate_rejects_unbound_base_interpreter(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    invalid_base: str | None,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    monkeypatch.setattr(runner.sys, "_base_executable", invalid_base)

    with pytest.raises(
        runner.CoverageGateError, match="process gate interpreter is invalid"
    ):
        runner._process_tree_gate_interpreter(tmp_path / "venv-python.exe")


def test_coverage_process_gate_uses_exact_isolated_interpreter_flags(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    observed: list[tuple[str, ...]] = []
    real_popen = runner.subprocess.Popen

    def observe_launcher(command: tuple[str, ...], **kwargs: object):
        observed.append(tuple(command))
        return real_popen(command, **kwargs)

    monkeypatch.setattr(runner.subprocess, "Popen", observe_launcher)
    bounded = runner._run_bounded_process(
        (sys.executable, "-I", "-S", "-B", "-c", "print('ok')"),
        cwd=tmp_path,
        env=os.environ.copy(),
        timeout=30,
    )

    assert bounded.completed.returncode == 0
    assert bounded.completed.stdout.strip() == "ok"
    assert observed == [
        (
            runner._process_tree_gate_interpreter(sys.executable),
            "-I",
            "-S",
            "-B",
            "-c",
            runner._GATED_LAUNCHER,
        )
    ]


def test_split_source_nested_pytest_removes_outer_bootstrap_authority(
    tmp_path: Path,
) -> None:
    """Catches a synthetic checkout inheriting the outer locked repository."""
    runner = importlib.import_module("scripts.run_coverage_gate")
    source_root = tmp_path / "committed-source"
    build_backend = tmp_path / "synthetic-build-backend"
    locked_backend = tmp_path / "locked-build-backend"
    for root in (source_root, build_backend, locked_backend):
        root.mkdir()
    safe_transport = {
        "COVERAGE_FILE": str(tmp_path / "coverage.json"),
        "HYPOTHESIS_STORAGE_DIRECTORY": str(tmp_path / "hypothesis"),
        "NEUTRAL_TOOL_VALUE": "preserved",
        "PATH": "closed-tool-path",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTEST_DEBUG_TEMPROOT": str(tmp_path / "pytest-temp"),
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        "PYTEST_PLUGINS": "pytest_cov.plugin,_hypothesis_pytestplugin",
        "PYTHONNOUSERSITE": "1",
        "PYTHONSAFEPATH": "1",
        "TEMP": str(tmp_path / "temp"),
        "TMP": str(tmp_path / "tmp"),
        "TMPDIR": str(tmp_path / "tmpdir"),
        "VIRTUAL_ENV": str(tmp_path / "locked-environment"),
    }
    authority_names = {
        name.upper() for name in runner._BOOTSTRAP_AUTHORITY_VARIABLES
    }
    outer_authority: dict[str, str] = {}
    for index, name in enumerate(sorted(authority_names), start=1):
        aliases = (name, name.lower(), name.title())
        assert len(set(aliases)) == 3
        for alias_index, alias in enumerate(aliases, start=1):
            outer_authority[alias] = f"outer-{index}-{alias_index}"
    pythonpath_aliases = {
        "PYTHONPATH": str(locked_backend.resolve(strict=True)),
        "pythonpath": str(tmp_path / "foreign-lower-pythonpath"),
        "PyThOnPaTh": str(tmp_path / "foreign-mixed-pythonpath"),
    }
    source_environment = {
        **safe_transport,
        **outer_authority,
        **pythonpath_aliases,
    }
    run = SimpleNamespace(
        environment=source_environment,
        locked_test_runtime=SimpleNamespace(
            build_backend_root=locked_backend.resolve(strict=True)
        ),
    )
    original_environment = json.dumps(
        source_environment,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    environment = _split_source_pytest_environment(
        runner,
        run,
        source_root,
        build_backend,
    )

    assert not [name for name in environment if name.upper() in authority_names]
    assert {name: environment[name] for name in safe_transport} == safe_transport
    assert [name for name in environment if name.upper() == "PYTHONPATH"] == [
        "PYTHONPATH"
    ]
    assert environment["PYTHONPATH"].split(os.pathsep) == [
        str(source_root.resolve(strict=True)),
        str(build_backend.resolve(strict=True)),
        str(locked_backend.resolve(strict=True)),
    ]
    assert json.dumps(
        run.environment,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8") == original_environment


@pytest.mark.parametrize("kind", ("locked", "mismatch", "missing", "unbound"))
def test_split_source_nested_pytest_closes_overlay_authority(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    kind: str,
) -> None:
    """Catches any nested dependency root not bound by ``CoverageRun``."""
    source_root = tmp_path / "committed-source"
    build_backend = tmp_path / "synthetic-build-backend"
    locked_backend = tmp_path / "locked-build-backend"
    foreign_backend = tmp_path / "foreign-build-backend"
    for root in (source_root, build_backend, locked_backend, foreign_backend):
        root.mkdir()
    selected_backend = tmp_path / "missing-build-backend" if kind == "missing" else (
        locked_backend.resolve(strict=True)
    )
    run = SimpleNamespace(
        environment={
            "PYTHONPATH": str(
                foreign_backend.resolve(strict=True)
                if kind in {"mismatch", "unbound"}
                else selected_backend
            )
        },
        locked_test_runtime=(
            None
            if kind == "unbound"
            else SimpleNamespace(build_backend_root=selected_backend)
        ),
    )
    monkeypatch.setenv("PYTHONPATH", str(foreign_backend.resolve(strict=True)))

    if kind != "locked":
        with pytest.raises(AssertionError, match="split-source coverage authority"):
            _split_source_pytest_pythonpath(run, source_root, build_backend)
        return

    assert _split_source_pytest_pythonpath(
        run, source_root, build_backend
    ).split(os.pathsep) == [
        str(source_root.resolve(strict=True)),
        str(build_backend.resolve(strict=True)),
        str(locked_backend.resolve(strict=True)),
    ]


def test_coverage_command_collects_checkout_tests_with_split_source_imports(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """Catches committed ``tests`` shadowing the bound checkout during collection."""
    runner = importlib.import_module("scripts.run_coverage_gate")
    source_root = tmp_path / "committed-source"
    repository = tmp_path / "repository"
    build_backend = tmp_path / "build-backend"
    (source_root / "scripts").mkdir(parents=True)
    (source_root / "src" / "hsconfig").mkdir(parents=True)
    (source_root / "tests").mkdir()
    build_backend.mkdir()
    (source_root / "scripts" / "__init__.py").write_text(
        "import tests\n",
        encoding="utf-8",
    )
    shutil.copy2(
        ROOT / "scripts" / "run_coverage_gate.py",
        source_root / "scripts" / "run_coverage_gate.py",
    )
    (source_root / "src" / "hsconfig" / "__init__.py").write_text(
        "SOURCE_MARKER = 'committed-source'\n",
        encoding="utf-8",
    )
    (source_root / "tests" / "__init__.py").write_text("\n", encoding="utf-8")
    (source_root / "tests" / "test_probe.py").write_text(
        "import os\n"
        "from pathlib import Path\n"
        "import hsconfig\n"
        "from scripts import run_coverage_gate as gate\n\n"
        "def test_checkout_module_uses_committed_product():\n"
        "    checkout = Path(os.environ['HSCONFIG_TEST_CHECKOUT']).resolve()\n"
        "    source = Path(os.environ['HSCONFIG_TEST_SOURCE']).resolve()\n"
        "    assert Path(__file__).resolve().is_relative_to(checkout)\n"
        "    assert Path(gate.__file__).resolve().is_relative_to(source)\n"
        "    assert Path(hsconfig.__file__).resolve().is_relative_to(source / 'src')\n"
        "    assert hsconfig.SOURCE_MARKER == 'committed-source'\n"
        "\n",
        encoding="utf-8",
    )
    (source_root / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\npythonpath = ['src']\naddopts = ''\n"
        "[tool.coverage.run]\nbranch = true\nsource = ['src/hsconfig']\n",
        encoding="utf-8",
    )
    shutil.copytree(source_root, repository)
    (repository / "src" / "hsconfig" / "__init__.py").write_text(
        "SOURCE_MARKER = 'checkout'\n",
        encoding="utf-8",
    )
    import_document, import_sha256 = runner._pytest_import_inventory_document(
        _test_pytest_import_inventory(runner, source_root, repository)
    )

    with runner.isolated_coverage_environment() as run, monkeypatch.context() as nested:
        nested.setattr(runner, "_ACTIVE_PYTEST_FAILURE_STATE", None)
        nested.setattr(runner, "ROOT", source_root.resolve(strict=True))
        environment = _split_source_pytest_environment(
            runner,
            run,
            source_root,
            build_backend,
        )
        environment["HSCONFIG_TEST_CHECKOUT"] = str(repository.resolve(strict=True))
        environment["HSCONFIG_TEST_SOURCE"] = str(source_root.resolve(strict=True))
        environment[runner._PYTEST_IMPORT_INVENTORY] = import_document
        environment[runner._PYTEST_IMPORT_INVENTORY_SHA256] = import_sha256
        completed = subprocess.run(
            runner._pytest_coverage_command(
                run.coverage_json,
                run.failure_sideband,
                interpreter=Path(sys.executable).resolve(strict=True),
                test_root=repository.resolve(strict=True),
            ),
            cwd=repository,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=120,
        )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "1 passed" in completed.stdout


def test_coverage_command_rebinds_preimported_test_module_to_checkout(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """Catches importlib reusing a committed ``tests.test_b`` module."""
    runner = importlib.import_module("scripts.run_coverage_gate")
    source_root = tmp_path / "committed-source"
    repository = tmp_path / "repository"
    build_backend = tmp_path / "build-backend"
    (source_root / "scripts").mkdir(parents=True)
    (source_root / "src" / "hsconfig").mkdir(parents=True)
    (source_root / "tests").mkdir()
    build_backend.mkdir()
    (source_root / "scripts" / "__init__.py").write_text(
        "import tests.test_b\n",
        encoding="utf-8",
    )
    shutil.copy2(
        ROOT / "scripts" / "run_coverage_gate.py",
        source_root / "scripts" / "run_coverage_gate.py",
    )
    (source_root / "src" / "hsconfig" / "__init__.py").write_text(
        "SOURCE_MARKER = 'committed-source'\n",
        encoding="utf-8",
    )
    (source_root / "tests" / "__init__.py").write_text("\n", encoding="utf-8")
    (source_root / "tests" / "test_a.py").write_text(
        "import os\n"
        "from pathlib import Path\n"
        "import hsconfig\n"
        "from scripts import run_coverage_gate as gate\n"
        "from tests import test_b\n\n"
        "def test_cross_import_uses_checkout_module():\n"
        "    checkout = Path(os.environ['HSCONFIG_TEST_CHECKOUT']).resolve()\n"
        "    source = Path(os.environ['HSCONFIG_TEST_SOURCE']).resolve()\n"
        "    assert Path(__file__).resolve().is_relative_to(checkout)\n"
        "    assert test_b.ORIGIN == 'checkout'\n"
        "    assert Path(test_b.__file__).resolve().is_relative_to(checkout)\n"
        "    assert Path(gate.__file__).resolve().is_relative_to(source)\n"
        "    assert hsconfig.SOURCE_MARKER == 'committed-source'\n"
        "    assert Path(hsconfig.__file__).resolve().is_relative_to(source / 'src')\n"
        "\n",
        encoding="utf-8",
    )
    (source_root / "tests" / "test_b.py").write_text(
        "import os\n"
        "from pathlib import Path\n\n"
        "ORIGIN = 'committed-source'\n\n"
        "def test_item_uses_checkout_module():\n"
        "    checkout = Path(os.environ['HSCONFIG_TEST_CHECKOUT']).resolve()\n"
        "    assert ORIGIN == 'checkout'\n"
        "    assert Path(__file__).resolve().is_relative_to(checkout)\n",
        encoding="utf-8",
    )
    (source_root / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\npythonpath = ['src']\naddopts = ''\n"
        "[tool.coverage.run]\nbranch = true\nsource = ['src/hsconfig']\n",
        encoding="utf-8",
    )
    shutil.copytree(source_root, repository)
    (repository / "src" / "hsconfig" / "__init__.py").write_text(
        "SOURCE_MARKER = 'checkout'\n",
        encoding="utf-8",
    )
    (repository / "tests" / "test_b.py").write_text(
        "import os\n"
        "from pathlib import Path\n\n"
        "ORIGIN = 'checkout'\n\n"
        "def test_item_uses_checkout_module():\n"
        "    checkout = Path(os.environ['HSCONFIG_TEST_CHECKOUT']).resolve()\n"
        "    assert ORIGIN == 'checkout'\n"
        "    assert Path(__file__).resolve().is_relative_to(checkout)\n",
        encoding="utf-8",
    )
    import_document, import_sha256 = runner._pytest_import_inventory_document(
        _test_pytest_import_inventory(runner, source_root, repository)
    )

    with runner.isolated_coverage_environment() as run, monkeypatch.context() as nested:
        nested.setattr(runner, "_ACTIVE_PYTEST_FAILURE_STATE", None)
        nested.setattr(runner, "ROOT", source_root.resolve(strict=True))
        environment = _split_source_pytest_environment(
            runner,
            run,
            source_root,
            build_backend,
        )
        environment["HSCONFIG_TEST_CHECKOUT"] = str(repository.resolve(strict=True))
        environment["HSCONFIG_TEST_SOURCE"] = str(source_root.resolve(strict=True))
        environment[runner._PYTEST_IMPORT_INVENTORY] = import_document
        environment[runner._PYTEST_IMPORT_INVENTORY_SHA256] = import_sha256
        completed = subprocess.run(
            runner._pytest_coverage_command(
                run.coverage_json,
                run.failure_sideband,
                interpreter=Path(sys.executable).resolve(strict=True),
                test_root=repository.resolve(strict=True),
            ),
            cwd=repository,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=120,
        )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "2 passed" in completed.stdout


def test_pytest_import_rebinding_cleans_partial_package_imports(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """Catches a failed package initialization leaving importable residue."""
    runner = importlib.import_module("scripts.run_coverage_gate")
    source_root = tmp_path / "committed-source"
    repository = tmp_path / "repository"
    product_root = source_root / "src" / "hsconfig"
    source_tests_root = source_root / "tests"
    tests_root = repository / "tests"
    product_root.mkdir(parents=True)
    source_tests_root.mkdir(parents=True)
    tests_root.mkdir(parents=True)
    (product_root / "__init__.py").write_text(
        "from hsconfig import partial\n",
        encoding="utf-8",
    )
    (product_root / "partial.py").write_text("VALUE = 'source'\n", encoding="utf-8")
    tests_initializer = "from tests import partial\nraise RuntimeError('partial tests package')\n"
    (source_tests_root / "__init__.py").write_text(
        tests_initializer,
        encoding="utf-8",
    )
    (tests_root / "__init__.py").write_text(
        tests_initializer,
        encoding="utf-8",
    )
    (tests_root / "partial.py").write_text("VALUE = 'checkout'\n", encoding="utf-8")
    monkeypatch.setattr(runner, "ROOT", source_root.resolve(strict=True))
    original = {
        name: module
        for name, module in sys.modules.items()
        if name == "tests"
        or name.startswith("tests.")
        or name == "hsconfig"
        or name.startswith("hsconfig.")
    }
    sentinels = {
        "tests.preexisting_sentinel": SimpleNamespace(origin="tests"),
        "hsconfig.preexisting_sentinel": SimpleNamespace(origin="hsconfig"),
    }
    sys.modules.update(sentinels)
    expected = {**original, **sentinels}

    try:
        with pytest.raises(RuntimeError, match="partial tests package"):
            runner._bind_pytest_import_roots(
                repository.resolve(strict=True),
                source_inventory=_test_pytest_import_inventory(
                    runner,
                    source_root,
                    repository,
                ),
            )
        observed = {
            name: module
            for name, module in sys.modules.items()
            if name == "tests"
            or name.startswith("tests.")
            or name == "hsconfig"
            or name.startswith("hsconfig.")
        }
        assert observed.keys() == expected.keys()
        assert all(observed[name] is module for name, module in expected.items())
    finally:
        for name in tuple(sys.modules):
            if (
                name == "tests"
                or name.startswith("tests.")
                or name == "hsconfig"
                or name.startswith("hsconfig.")
            ):
                del sys.modules[name]
        sys.modules.update(original)


def test_pytest_import_rebinding_executes_bound_bytes_after_path_swap(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """Catches package loaders reopening an initializer after its bound read."""
    runner = importlib.import_module("scripts.run_coverage_gate")
    source_root = tmp_path / "committed-source"
    repository = tmp_path / "repository"
    product_root = source_root / "src" / "hsconfig"
    source_tests_root = source_root / "tests"
    checkout_tests_root = repository / "tests"
    product_root.mkdir(parents=True)
    source_tests_root.mkdir(parents=True)
    checkout_tests_root.mkdir(parents=True)
    product_init = product_root / "__init__.py"
    source_tests_init = source_tests_root / "__init__.py"
    checkout_tests_init = checkout_tests_root / "__init__.py"
    product_init.write_text("ORIGIN = 'bound-source'\n", encoding="utf-8")
    source_tests_init.write_text("ORIGIN = 'bound-checkout'\n", encoding="utf-8")
    checkout_tests_init.write_bytes(source_tests_init.read_bytes())
    monkeypatch.setattr(runner, "ROOT", source_root.resolve(strict=True))
    import_inventory = _test_pytest_import_inventory(runner, source_root, repository)
    original_meta_path = tuple(sys.meta_path)
    original_modules = {
        name: module
        for name, module in sys.modules.items()
        if name == "tests"
        or name.startswith("tests.")
        or name == "hsconfig"
        or name.startswith("hsconfig.")
    }
    real_module_from_spec = importlib.util.module_from_spec
    real_compile = builtins.compile

    def swapping_module_from_spec(spec):
        module = real_module_from_spec(spec)
        if spec.name == "hsconfig":
            product_init.write_text("ORIGIN = 'transient-path'\n", encoding="utf-8")
        return module

    def swapping_compile(source, filename, mode, *args, **kwargs):
        if Path(filename) == product_init:
            product_init.write_text("ORIGIN = 'transient-path'\n", encoding="utf-8")
        return real_compile(source, filename, mode, *args, **kwargs)

    monkeypatch.setattr(importlib.util, "module_from_spec", swapping_module_from_spec)
    monkeypatch.setattr(builtins, "compile", swapping_compile)

    try:
        runner._bind_pytest_import_roots(
            repository.resolve(strict=True),
            source_inventory=import_inventory,
        )
        assert sys.modules["hsconfig"].ORIGIN == "bound-source"
        assert sys.modules["tests"].ORIGIN == "bound-checkout"
    finally:
        sys.meta_path[:] = original_meta_path
        for name in tuple(sys.modules):
            if (
                name == "tests"
                or name.startswith("tests.")
                or name == "hsconfig"
                or name.startswith("hsconfig.")
            ):
                del sys.modules[name]
        sys.modules.update(original_modules)


def test_pytest_import_rebinding_accepts_exact_windows_autocrlf_materialization(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """Catches a clean Windows checkout being rejected for CRLF translation only."""
    runner = importlib.import_module("scripts.run_coverage_gate")
    source_root = tmp_path / "committed-source"
    repository = tmp_path / "repository"
    product_root = source_root / "src" / "hsconfig"
    source_tests_root = source_root / "tests"
    checkout_tests_root = repository / "tests"
    product_root.mkdir(parents=True)
    source_tests_root.mkdir(parents=True)
    checkout_tests_root.mkdir(parents=True)
    (product_root / "__init__.py").write_bytes(b"ORIGIN = 'product'\n")
    (source_tests_root / "__init__.py").write_bytes(b"ORIGIN = 'tests'\n")
    (checkout_tests_root / "__init__.py").write_bytes(b"ORIGIN = 'tests'\r\n")
    monkeypatch.setattr(runner, "ROOT", source_root.resolve(strict=True))
    monkeypatch.setattr(runner, "_windows_host", lambda: True)
    import_inventory = _test_pytest_import_inventory(runner, source_root)
    authority = runner._BoundPytestImportAuthority(
        product_root=product_root.resolve(strict=True),
        tests_root=checkout_tests_root.resolve(strict=True),
        inventory=import_inventory,
    )
    tests_path, tests_source = authority.read("tests/__init__.py")
    assert tests_path == (checkout_tests_root / "__init__.py").resolve(strict=True)
    assert tests_source == b"ORIGIN = 'tests'\n"
    original_meta_path = tuple(sys.meta_path)
    original_modules = {
        name: module
        for name, module in sys.modules.items()
        if name == "tests"
        or name.startswith("tests.")
        or name == "hsconfig"
        or name.startswith("hsconfig.")
    }

    try:
        runner._bind_pytest_import_roots(
            repository.resolve(strict=True),
            source_inventory=import_inventory,
        )
        assert sys.modules["tests"].ORIGIN == "tests"
    finally:
        sys.meta_path[:] = original_meta_path
        for name in tuple(sys.modules):
            if (
                name == "tests"
                or name.startswith("tests.")
                or name == "hsconfig"
                or name.startswith("hsconfig.")
            ):
                del sys.modules[name]
        sys.modules.update(original_modules)


@pytest.mark.parametrize(
    ("windows_host", "checkout_source"),
    (
        (False, b"ORIGIN = 'tests'\r\n"),
        (True, b"ORIGIN = 'changed'\r\n"),
        (True, b"ORIGIN = 'tests'\r"),
        (True, b"ORIGIN = 'tests'\r\r\n"),
    ),
)
def test_pytest_import_rebinding_rejects_noncanonical_eol_or_bytes(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    windows_host: bool,
    checkout_source: bytes,
) -> None:
    """Keeps the Windows EOL exception exact, host-bound, and fail-closed."""
    runner = importlib.import_module("scripts.run_coverage_gate")
    source_root = tmp_path / "committed-source"
    repository = tmp_path / "repository"
    product_root = source_root / "src" / "hsconfig"
    source_tests_root = source_root / "tests"
    checkout_tests_root = repository / "tests"
    product_root.mkdir(parents=True)
    source_tests_root.mkdir(parents=True)
    checkout_tests_root.mkdir(parents=True)
    (product_root / "__init__.py").write_bytes(b"ORIGIN = 'product'\n")
    (source_tests_root / "__init__.py").write_bytes(b"ORIGIN = 'tests'\n")
    (checkout_tests_root / "__init__.py").write_bytes(checkout_source)
    monkeypatch.setattr(runner, "ROOT", source_root.resolve(strict=True))
    monkeypatch.setattr(runner, "_windows_host", lambda: windows_host)
    authority = runner._BoundPytestImportAuthority(
        product_root=product_root.resolve(strict=True),
        tests_root=checkout_tests_root.resolve(strict=True),
        inventory=_test_pytest_import_inventory(runner, source_root),
    )

    with pytest.raises(runner.CoverageGateError, match="import source differs"):
        authority.read("tests/__init__.py")


def test_pytest_import_rebinding_preserves_real_packaged_resource_loading(
    monkeypatch: MonkeyPatch,
) -> None:
    """Catches a synthetic package spec that degrades resources to OrphanPath."""
    runner = importlib.import_module("scripts.run_coverage_gate")
    original_modules = {
        name: module
        for name, module in sys.modules.items()
        if name == "tests"
        or name.startswith("tests.")
        or name == "hsconfig"
        or name.startswith("hsconfig.")
    }
    original_meta_path = tuple(sys.meta_path)
    monkeypatch.setattr(runner, "ROOT", ROOT.resolve(strict=True))

    try:
        runner._bind_pytest_import_roots(
            ROOT.resolve(strict=True),
            source_inventory=_test_pytest_import_inventory(runner, ROOT),
        )
        catalog = importlib.import_module("hsconfig.build_input_catalog")
        audited = catalog.load_packaged_audited_build_inputs()
        assert audited.builds
        resources = importlib.import_module("importlib.resources")
        resource = resources.files("hsconfig").joinpath(
            "resources/audited_build_inputs.json"
        )
        with pytest.raises(TypeError):
            resource.open("rb", "utf-8")
        with pytest.raises(TypeError):
            resource.open("rb", encoding="utf-8")
        with pytest.raises(TypeError):
            resource.open("rb", arbitrary=True)
    finally:
        sys.meta_path[:] = original_meta_path
        for name in tuple(sys.modules):
            if (
                name == "tests"
                or name.startswith("tests.")
                or name == "hsconfig"
                or name.startswith("hsconfig.")
            ):
                del sys.modules[name]
        sys.modules.update(original_modules)


def test_pytest_unconfigure_restores_exact_prior_package_modules(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """Catches successful teardown retaining rebound package-family modules."""
    runner = importlib.import_module("scripts.run_coverage_gate")
    source_root = tmp_path / "committed-source"
    repository = tmp_path / "repository"
    (source_root / "src" / "hsconfig").mkdir(parents=True)
    (repository / "tests").mkdir(parents=True)
    (source_root / "src" / "hsconfig" / "__init__.py").write_text(
        "ORIGIN = 'bound'\n",
        encoding="utf-8",
    )
    (repository / "tests" / "__init__.py").write_text("\n", encoding="utf-8")
    monkeypatch.setattr(runner, "ROOT", source_root.resolve(strict=True))
    original_modules = {
        name: module
        for name, module in sys.modules.items()
        if name == "tests"
        or name.startswith("tests.")
        or name == "hsconfig"
        or name.startswith("hsconfig.")
    }
    original_meta_path = tuple(sys.meta_path)
    prior = {
        "hsconfig": ModuleType("hsconfig"),
        "hsconfig.prior": ModuleType("hsconfig.prior"),
        "tests": ModuleType("tests"),
        "tests.prior": ModuleType("tests.prior"),
    }
    for name in tuple(original_modules):
        del sys.modules[name]
    sys.modules.update(prior)

    try:
        finder = runner._bind_pytest_import_roots(
            repository.resolve(strict=True),
            source_inventory=_test_pytest_import_inventory(
                runner,
                source_root,
                repository,
            ),
        )
        state = runner._PytestFailureState(
            repository_root=repository.resolve(strict=True),
            sideband=tmp_path / runner.PYTEST_FAILURE_SIDEBAND_NAME,
            import_finder=finder,
        )
        monkeypatch.setattr(runner, "_ACTIVE_PYTEST_FAILURE_STATE", state)
        runner.pytest_unconfigure(SimpleNamespace())
        observed = {
            name: module
            for name, module in sys.modules.items()
            if name == "tests"
            or name.startswith("tests.")
            or name == "hsconfig"
            or name.startswith("hsconfig.")
        }
        assert observed.keys() == prior.keys()
        assert all(observed[name] is module for name, module in prior.items())
    finally:
        sys.meta_path[:] = original_meta_path
        for name in tuple(sys.modules):
            if (
                name == "tests"
                or name.startswith("tests.")
                or name == "hsconfig"
                or name.startswith("hsconfig.")
            ):
                del sys.modules[name]
        sys.modules.update(original_modules)


def test_pytest_unconfigure_preserves_pythonpath_and_keeps_bound_authority(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """Catches owned-path deletion or post-unconfigure PathFinder fallback."""
    runner = importlib.import_module("scripts.run_coverage_gate")
    source_root = tmp_path / "committed-source"
    repository = tmp_path / "repository"
    product_root = source_root / "src" / "hsconfig"
    (product_root).mkdir(parents=True)
    (repository / "tests").mkdir(parents=True)
    (product_root / "__init__.py").write_text("\n", encoding="utf-8")
    (product_root / "attack.py").write_text("ORIGIN = 'bound'\n", encoding="utf-8")
    (repository / "tests" / "__init__.py").write_text("\n", encoding="utf-8")
    monkeypatch.setattr(runner, "ROOT", source_root.resolve(strict=True))
    original_modules = {
        name: module
        for name, module in sys.modules.items()
        if name == "tests"
        or name.startswith("tests.")
        or name == "hsconfig"
        or name.startswith("hsconfig.")
    }
    original_meta_path = tuple(sys.meta_path)
    original_sys_path = tuple(sys.path)
    for name in tuple(original_modules):
        del sys.modules[name]
    configured_path = str(source_root / "src")
    equivalent_path = str(source_root / "src" / ".." / "src")
    sys.path[:0] = [configured_path, configured_path, equivalent_path]

    class PassiveFinder:
        @staticmethod
        def find_spec(name, path=None, target=None):
            del name, path, target
            return None

    try:
        finder = runner._bind_pytest_import_roots(
            repository.resolve(strict=True),
            source_inventory=_test_pytest_import_inventory(
                runner,
                source_root,
                repository,
            ),
        )
        state = runner._PytestFailureState(
            repository_root=repository.resolve(strict=True),
            sideband=tmp_path / runner.PYTEST_FAILURE_SIDEBAND_NAME,
            import_finder=finder,
        )
        monkeypatch.setattr(runner, "_ACTIVE_PYTEST_FAILURE_STATE", state)
        passive_first = PassiveFinder()
        passive_last = PassiveFinder()
        sys.meta_path.insert(0, passive_first)
        sys.meta_path.append(passive_last)
        expected_meta_path = tuple(sys.meta_path)
        expected_sys_path = tuple(sys.path)
        runner.pytest_unconfigure(SimpleNamespace())
        assert tuple(sys.meta_path) == expected_meta_path
        assert tuple(sys.path) == expected_sys_path
        assert not any(
            name == "tests"
            or name.startswith("tests.")
            or name == "hsconfig"
            or name.startswith("hsconfig.")
            for name in sys.modules
        )
        sys.path.remove(configured_path)
        assert sys.path.count(configured_path) == 1
        assert equivalent_path in sys.path
        legitimate = importlib.import_module("hsconfig.attack")
        assert legitimate.ORIGIN == "bound"
        del sys.modules["hsconfig.attack"]
        del sys.modules["hsconfig"]
        product_root.rename(source_root / "src" / "hsconfig-bound")
        product_root.mkdir()
        (product_root / "__init__.py").write_text("\n", encoding="utf-8")
        (product_root / "attack.py").write_text(
            "ORIGIN = 'replacement'\n",
            encoding="utf-8",
        )
        importlib.invalidate_caches()
        with pytest.raises((ImportError, runner.CoverageGateError)):
            importlib.import_module("hsconfig.attack")
    finally:
        sys.path[:] = original_sys_path
        sys.meta_path[:] = original_meta_path
        for name in tuple(sys.modules):
            if (
                name == "tests"
                or name.startswith("tests.")
                or name == "hsconfig"
                or name.startswith("hsconfig.")
            ):
                del sys.modules[name]
        sys.modules.update(original_modules)


def test_pytest_import_rebinding_supports_bound_test_namespace_packages(
    monkeypatch: MonkeyPatch,
) -> None:
    """Catches inventory-backed ``tests.property`` being treated as absent."""
    runner = importlib.import_module("scripts.run_coverage_gate")
    original_modules = {
        name: module
        for name, module in sys.modules.items()
        if name == "tests"
        or name.startswith("tests.")
        or name == "hsconfig"
        or name.startswith("hsconfig.")
    }
    original_meta_path = tuple(sys.meta_path)
    monkeypatch.setattr(runner, "ROOT", ROOT.resolve(strict=True))

    try:
        runner._bind_pytest_import_roots(
            ROOT.resolve(strict=True),
            source_inventory=_test_pytest_import_inventory(runner, ROOT),
        )
        module = importlib.import_module("tests.property.test_ini_properties")
        assert Path(module.__file__).resolve() == (
            ROOT / "tests" / "property" / "test_ini_properties.py"
        ).resolve(strict=True)
    finally:
        sys.meta_path[:] = original_meta_path
        for name in tuple(sys.modules):
            if (
                name == "tests"
                or name.startswith("tests.")
                or name == "hsconfig"
                or name.startswith("hsconfig.")
            ):
                del sys.modules[name]
        sys.modules.update(original_modules)


def test_pytest_import_rebinding_rejects_later_package_directory_swap(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """Catches PathFinder importing replacement bytes from a swapped package root."""
    runner = importlib.import_module("scripts.run_coverage_gate")
    source_root = tmp_path / "committed-source"
    repository = tmp_path / "repository"
    product_root = source_root / "src" / "hsconfig"
    source_tests_root = source_root / "tests"
    checkout_tests_root = repository / "tests"
    product_root.mkdir(parents=True)
    source_tests_root.mkdir(parents=True)
    checkout_tests_root.mkdir(parents=True)
    (product_root / "__init__.py").write_text("ORIGIN = 'bound'\n", encoding="utf-8")
    (product_root / "attack.py").write_text("ORIGIN = 'bound'\n", encoding="utf-8")
    (source_tests_root / "__init__.py").write_text("\n", encoding="utf-8")
    (checkout_tests_root / "__init__.py").write_text("\n", encoding="utf-8")
    (checkout_tests_root / "attack.py").write_text(
        "ORIGIN = 'bound'\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(runner, "ROOT", source_root.resolve(strict=True))
    original_modules = {
        name: module
        for name, module in sys.modules.items()
        if name == "tests"
        or name.startswith("tests.")
        or name == "hsconfig"
        or name.startswith("hsconfig.")
    }
    original_meta_path = tuple(sys.meta_path)

    try:
        runner._bind_pytest_import_roots(
            repository.resolve(strict=True),
            source_inventory=_test_pytest_import_inventory(
                runner,
                source_root,
                repository,
            ),
        )
        product_root.rename(source_root / "src" / "hsconfig-bound")
        product_root.mkdir()
        (product_root / "__init__.py").write_text(
            "ORIGIN = 'replacement'\n",
            encoding="utf-8",
        )
        (product_root / "attack.py").write_text(
            "ORIGIN = 'replacement'\n",
            encoding="utf-8",
        )
        checkout_tests_root.rename(repository / "tests-bound")
        checkout_tests_root.mkdir()
        (checkout_tests_root / "__init__.py").write_text("\n", encoding="utf-8")
        (checkout_tests_root / "attack.py").write_text(
            "ORIGIN = 'replacement'\n",
            encoding="utf-8",
        )
        importlib.invalidate_caches()

        for name in ("hsconfig.attack", "tests.attack"):
            with pytest.raises((ImportError, runner.CoverageGateError)):
                importlib.import_module(name)
    finally:
        sys.meta_path[:] = original_meta_path
        for name in tuple(sys.modules):
            if (
                name == "tests"
                or name.startswith("tests.")
                or name == "hsconfig"
                or name.startswith("hsconfig.")
            ):
                del sys.modules[name]
        sys.modules.update(original_modules)


def test_pytest_import_inventory_binding_rejects_nonclosed_documents() -> None:
    """Covers duplicate keys, digest drift, ordering, and source cardinality."""
    runner = importlib.import_module("scripts.run_coverage_gate")
    source = {
        "path": "src/hsconfig/__init__.py",
        "sha256": "a" * 64,
        "git_mode": "100644",
    }
    tests = {
        "path": "tests/__init__.py",
        "sha256": "b" * 64,
        "git_mode": "100644",
    }

    def document(sources: list[dict[str, str]]) -> tuple[str, str]:
        raw = json.dumps(
            {"schema_version": 1, "sources": sources},
            sort_keys=True,
            separators=(",", ":"),
        )
        return raw, hashlib.sha256(raw.encode()).hexdigest()

    canonical, canonical_sha256 = document([source, tests])
    duplicate_key = canonical.replace(
        '"schema_version":1',
        '"schema_version":1,"schema_version":1',
    )
    invalid = [
        (duplicate_key, hashlib.sha256(duplicate_key.encode()).hexdigest()),
        (canonical, "0" * 64),
        document([tests, source]),
        document([source]),
        document([source, tests, tests]),
    ]

    for raw, digest in invalid:
        with pytest.raises(runner.CoverageGateError):
            runner._pytest_import_inventory_binding(raw, digest)
    assert canonical_sha256 != "0" * 64


def test_locked_pytest_session_collects_exact_checkout_then_restores_source(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """Catches checkout CWD starting only after real collection/import."""
    runner = importlib.import_module("scripts.run_coverage_gate")
    repository = tmp_path / "repository"
    source_root = tmp_path / "bootstrap" / "committed-source"
    build_backend = tmp_path / "bootstrap" / "build-backend"
    alternate_backend = tmp_path / "alternate-build-backend"
    restore_result = tmp_path / "restored-cwd.txt"
    (source_root / "scripts").mkdir(parents=True)
    (source_root / "src" / "hsconfig").mkdir(parents=True)
    (source_root / "tests").mkdir()
    build_backend.mkdir()
    alternate_backend.mkdir()
    (alternate_backend / "foreign_overlay.py").write_text(
        "FOREIGN = True\n",
        encoding="utf-8",
    )
    shutil.copy2(
        ROOT / "scripts" / "run_coverage_gate.py",
        source_root / "scripts" / "run_coverage_gate.py",
    )
    (source_root / "src" / "hsconfig" / "__init__.py").write_text(
        "SOURCE_MARKER = 'committed-source'\n",
        encoding="utf-8",
    )
    (source_root / "tests" / "__init__.py").write_text("\n", encoding="utf-8")
    (source_root / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\naddopts = ''\n",
        encoding="utf-8",
    )
    (source_root / "tests" / "conftest.py").write_text(
        "import os\n"
        "from pathlib import Path\n"
        "import pytest\n\n"
        "INITIAL_CWD = Path.cwd().resolve()\n\n"
        "@pytest.hookimpl(trylast=True)\n"
        "def pytest_sessionfinish(session, exitstatus):\n"
        "    del session, exitstatus\n"
        "    Path(os.environ['HSCONFIG_TEST_RESTORE_RESULT']).write_text(\n"
        "        str(Path.cwd().resolve()), encoding='utf-8'\n"
        "    )\n",
        encoding="utf-8",
    )
    (source_root / "tests" / "test_probe.py").write_text(
        "import hashlib\n"
        "import json\n"
        "import os\n"
        "from pathlib import Path\n"
        "import pytest\n"
        "from tests import conftest\n"
        "from scripts import run_coverage_gate as gate\n\n"
        "COLLECTION_CWD = Path.cwd().resolve()\n\n"
        "@pytest.mark.parametrize('parameter_cwd', [Path.cwd().resolve()])\n"
        "def test_collection_and_nested_binding(parameter_cwd, monkeypatch):\n"
        "    repository = Path(os.environ['HSCONFIG_TEST_REPOSITORY']).resolve()\n"
        "    source = Path(os.environ['HSCONFIG_TEST_SOURCE']).resolve()\n"
        "    overlay = Path(os.environ['HSCONFIG_TEST_OVERLAY']).resolve()\n"
        "    alternate = Path(os.environ['HSCONFIG_TEST_ALT_OVERLAY']).resolve()\n"
        "    assert conftest.INITIAL_CWD == repository\n"
        "    assert COLLECTION_CWD == repository\n"
        "    assert parameter_cwd == repository\n"
        "    assert Path.cwd().resolve() == repository\n"
        "    assert Path(__file__).resolve().is_relative_to(repository)\n"
        "    binding_name = 'HSCONFIG_COVERAGE_LOCKED_TEST_RUNTIME_BINDING'\n"
        "    binding_hash_name = 'HSCONFIG_COVERAGE_LOCKED_TEST_RUNTIME_SHA256'\n"
        "    original_document = os.environ[binding_name]\n"
        "    forged = json.loads(original_document)\n"
        "    identity, inventory_digest = gate._runtime_overlay_binding(alternate)\n"
        "    forged['build_backend_root'] = str(alternate)\n"
        "    forged['build_backend_identity'] = gate._identity_document(identity)\n"
        "    forged['build_backend_inventory_sha256'] = inventory_digest\n"
        "    forged_document = json.dumps(\n"
        "        forged, sort_keys=True, separators=(',', ':')\n"
        "    )\n"
        "    monkeypatch.setenv(binding_name, forged_document)\n"
        "    monkeypatch.setenv(\n"
        "        binding_hash_name, hashlib.sha256(forged_document.encode()).hexdigest()\n"
        "    )\n"
        "    with gate.isolated_coverage_environment() as nested:\n"
        "        document = nested.environment[binding_name]\n"
        "        digest = nested.environment[binding_hash_name]\n"
        "        assert document == original_document\n"
        "        assert document != forged_document\n"
        "        assert hashlib.sha256(document.encode()).hexdigest() == digest\n"
        "        assert nested.environment['PYTHONPATH'] == str(overlay)\n",
        encoding="utf-8",
    )
    repository.mkdir()
    for source in sorted(path for path in source_root.rglob("*") if path.is_file()):
        destination = repository / source.relative_to(source_root)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    git_environment = {
        key: value
        for key, value in os.environ.items()
        if not key.upper().startswith("GIT_")
    }
    for command in (
        ("git", "init", "-q"),
        ("git", "config", "user.email", "coverage@example.invalid"),
        ("git", "config", "user.name", "Coverage Contract"),
        ("git", "config", "core.autocrlf", "false"),
        ("git", "add", "."),
        ("git", "commit", "-q", "-m", "fixture"),
    ):
        subprocess.run(
            command,
            cwd=repository,
            env=git_environment,
            check=True,
            capture_output=True,
        )
    commit_oid = subprocess.run(
        ("git", "rev-parse", "HEAD"),
        cwd=repository,
        env=git_environment,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.strip()
    tree_oid = subprocess.run(
        ("git", "rev-parse", "HEAD^{tree}"),
        cwd=repository,
        env=git_environment,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.strip()
    inventory = tuple(
        (
            path.relative_to(source_root).as_posix(),
            hashlib.sha256(path.read_bytes()).hexdigest(),
            runner._runtime_git_mode(path.stat().st_mode) or "100644",
        )
        for path in sorted(path for path in source_root.rglob("*") if path.is_file())
    )
    binding = _test_coverage_runtime_binding(
        runner,
        repository=repository,
        source_root=source_root,
        build_backend_root=build_backend,
        source_inventory=inventory,
        commit_oid=commit_oid,
        tree_oid=tree_oid,
    )
    monkeypatch.setattr(runner, "_ACTIVE_PYTEST_FAILURE_STATE", None)
    monkeypatch.setattr(runner, "ROOT", source_root.resolve(strict=True))

    with runner.isolated_coverage_environment(binding) as run:
        environment = dict(run.environment)
        environment.update(
            {
                "HSCONFIG_TEST_REPOSITORY": str(repository.resolve(strict=True)),
                "HSCONFIG_TEST_SOURCE": str(source_root.resolve(strict=True)),
                "HSCONFIG_TEST_OVERLAY": str(build_backend.resolve(strict=True)),
                "HSCONFIG_TEST_ALT_OVERLAY": str(
                    alternate_backend.resolve(strict=True)
                ),
                "HSCONFIG_TEST_RESTORE_RESULT": str(restore_result),
            }
        )
        completed = subprocess.run(
            (
                str(run.locked_test_runtime.interpreter),
                "-m",
                "pytest",
                f"--rootdir={repository}",
                "-c",
                str(repository / "pyproject.toml"),
                "-p",
                "no:cacheprovider",
                "-p",
                "scripts.run_coverage_gate",
                f"{runner._PYTEST_FAILURE_SIDEBAND_OPTION}={run.failure_sideband}",
                str(repository / "tests" / "test_probe.py"),
                "-q",
            ),
            cwd=repository,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=120,
        )
        wrong_startup = subprocess.run(
            completed.args,
            cwd=source_root,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=120,
        )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert restore_result.read_text(encoding="utf-8") == str(
        source_root.resolve(strict=True)
    )

    assert wrong_startup.returncode != 0
    assert "locked pytest repository working directory differs" in (
        wrong_startup.stdout + wrong_startup.stderr
    )


def _bound_scan_test_binding(runner, repository: Path) -> str:
    metadata = repository.lstat()
    return json.dumps(
        {
            "schema_version": 1,
            "repository": str(repository.resolve(strict=True)),
            "commit_oid": "a" * 40,
            "tree_oid": "b" * 40,
            "root_identity": {
                "device": metadata.st_dev,
                "inode": metadata.st_ino,
                "size": metadata.st_size,
                "modified_ns": metadata.st_mtime_ns,
                "changed_ns": metadata.st_ctime_ns,
                "mode": metadata.st_mode,
            },
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def _bound_scan_result_bytes() -> bytes:
    return (
        json.dumps(
            {
                "schema_version": 1,
                "result": {
                    "passed": False,
                    "violations": ["public_placeholder:README.md:1"],
                    "tracked_files_scanned": 2,
                    "current_packages_scanned": 0,
                    "distribution_artifacts_scanned": 0,
                },
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        + b"\n"
    )


def test_bound_scan_parent_sends_only_closed_primitives_to_committed_child(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    repository = tmp_path / "repository"
    outputs = tmp_path / "outputs"
    repository.mkdir()
    outputs.mkdir()
    observed: dict[str, object] = {}
    interpreter = Path(sys.executable).resolve(strict=True)
    locked = SimpleNamespace(interpreter=interpreter)

    def fake_bounded_process(
        command: tuple[str, ...], **kwargs: object
    ) -> runner._BoundedResult:
        observed["command"] = command
        observed.update(kwargs)
        stdout = runner._BoundedCapture()
        stdout.drain(io.BytesIO(_bound_scan_result_bytes()))
        stderr = runner._BoundedCapture()
        return runner._BoundedResult(
            completed=subprocess.CompletedProcess(
                command,
                0,
                stdout=stdout.text(),
                stderr="",
            ),
            timed_out=False,
            stdout=stdout,
            stderr=stderr,
        )

    monkeypatch.setattr(runner, "_run_bounded_process", fake_bounded_process)

    monkeypatch.setattr(
        runner,
        "_active_locked_test_runtime",
        lambda: (locked, "{}", "0" * 64),
    )
    result = runner._run_bound_coverage_scan(
        binding_json=_bound_scan_test_binding(runner, repository),
        outputs_root=outputs.resolve(strict=True),
        tree_mode="working-pre-cutover",
        build_distributions=False,
    )

    command = observed["command"]
    assert isinstance(command, tuple)
    assert command == (
        str(interpreter),
        str(runner.ROOT / "scripts" / "run_coverage_gate.py"),
        "--coverage-bound-scan-child",
    )
    assert observed["launcher"] == interpreter
    request = json.loads(observed["stdin_data"])
    assert set(request) == {
        "schema_version",
        "source_root",
        "repository",
        "outputs_root",
        "commit_oid",
        "tree_oid",
        "root_identity",
        "tree_mode",
        "build_distributions",
    }
    assert all(
        isinstance(value, (str, int, bool, dict)) for value in request.values()
    )
    assert set(request["root_identity"]) == {
        "device",
        "inode",
        "size",
        "modified_ns",
        "changed_ns",
        "mode",
    }
    environment = observed["env"]
    assert isinstance(environment, dict)
    assert environment["PYTHONPATH"].split(os.pathsep) == [
        str(runner.ROOT / "src"),
        str(runner.ROOT),
    ]
    assert "HSCONFIG_COVERAGE_TEST_REPOSITORY_BINDING" not in environment
    assert result["violations"] == ["public_placeholder:README.md:1"]


@pytest.mark.parametrize(
    "kind",
    (
        "duplicate-key",
        "extra-key",
        "wrong-schema-type",
        "wrong-result-type",
        "invalid-utf8",
        "oversized",
        "stderr",
        "timeout",
        "abnormal-exit",
        "missing-newline",
    ),
)
def test_bound_scan_parent_rejects_nonclosed_child_transport(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    kind: str,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    repository = tmp_path / "repository"
    outputs = tmp_path / "outputs"
    repository.mkdir()
    outputs.mkdir()
    valid = _bound_scan_result_bytes()
    if kind == "duplicate-key":
        source = valid.replace(b'"schema_version":1', b'"schema_version":1,"schema_version":1')
    elif kind == "extra-key":
        source = valid.replace(b'{"result":', b'{"extra":0,"result":')
    elif kind == "wrong-schema-type":
        source = valid.replace(b'"schema_version":1', b'"schema_version":true')
    elif kind == "wrong-result-type":
        source = valid.replace(b'"tracked_files_scanned":2', b'"tracked_files_scanned":true')
    elif kind == "invalid-utf8":
        source = valid.replace(
            b"public_placeholder:README.md:1",
            b"bad-\xff-byte",
        )
    elif kind == "oversized":
        source = b"x" * (runner.MAX_BOUND_SCAN_RESPONSE_BYTES + 1)
    elif kind == "missing-newline":
        source = valid.rstrip(b"\n")
    else:
        source = valid

    def fake_bounded_process(
        command: tuple[str, ...], **kwargs: object
    ) -> runner._BoundedResult:
        del kwargs
        stdout = runner._BoundedCapture()
        stdout.drain(io.BytesIO(source))
        stderr = runner._BoundedCapture()
        if kind == "stderr":
            stderr.drain(io.BytesIO(b"private diagnostic"))
        return runner._BoundedResult(
            completed=subprocess.CompletedProcess(
                command,
                -9 if kind == "abnormal-exit" else 0,
                stdout=stdout.text(),
                stderr=stderr.text(),
            ),
            timed_out=kind == "timeout",
            stdout=stdout,
            stderr=stderr,
        )

    monkeypatch.setattr(runner, "_run_bounded_process", fake_bounded_process)

    with pytest.raises(AssertionError, match="coverage test repository binding"):
        runner._run_bound_coverage_scan(
            binding_json=_bound_scan_test_binding(runner, repository),
            outputs_root=outputs.resolve(strict=True),
            tree_mode="working-pre-cutover",
            build_distributions=False,
        )


@pytest.mark.parametrize(
    "kind",
    (
        "duplicate-key",
        "extra-key",
        "wrong-schema-type",
        "wrong-identity-type",
        "relative-path",
        "opaque-string",
        "oversized",
    ),
)
def test_bound_scan_parent_rejects_nonclosed_binding_before_launch(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    kind: str,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    repository = tmp_path / "repository"
    outputs = tmp_path / "outputs"
    repository.mkdir()
    outputs.mkdir()
    source = _bound_scan_test_binding(runner, repository)
    opaque_callback_invoked = False
    if kind == "duplicate-key":
        source = source.replace(
            '"schema_version":1',
            '"schema_version":1,"schema_version":1',
        )
    elif kind == "extra-key":
        source = source.replace("{", '{"extra":0,', 1)
    elif kind == "wrong-schema-type":
        source = source.replace('"schema_version":1', '"schema_version":true')
    elif kind == "wrong-identity-type":
        source = source.replace('"device":', '"device":true,"discarded":')
    elif kind == "relative-path":
        document = json.loads(source)
        document["repository"] = "relative"
        source = json.dumps(document, sort_keys=True, separators=(",", ":"))
    elif kind == "opaque-string":

        class OpaqueString(str):
            def encode(self, *args: object, **kwargs: object) -> bytes:
                nonlocal opaque_callback_invoked
                opaque_callback_invoked = True
                return super().encode(*args, **kwargs)

        source = OpaqueString(source)
    else:
        source = " " * (16 * 1024 + 1)
    launched = False

    def forbidden_launch(*args: object, **kwargs: object) -> None:
        nonlocal launched
        launched = True

    monkeypatch.setattr(runner, "_run_bounded_process", forbidden_launch)

    with pytest.raises(AssertionError, match="coverage test repository binding"):
        runner._run_bound_coverage_scan(
            binding_json=source,
            outputs_root=outputs.resolve(strict=True),
            tree_mode="working-pre-cutover",
            build_distributions=False,
        )

    assert launched is False
    assert opaque_callback_invoked is False


@pytest.mark.parametrize(
    "kind",
    (
        "duplicate-key",
        "extra-key",
        "wrong-type",
        "relative-source-root",
        "relative-outputs-root",
        "oversized",
    ),
)
def test_bound_scan_child_rejects_nonclosed_request_document(
    tmp_path: Path,
    kind: str,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    repository = tmp_path / "repository"
    outputs = tmp_path / "outputs"
    repository.mkdir()
    outputs.mkdir()
    request = json.loads(_bound_scan_test_binding(runner, repository))
    request.update(
        {
            "source_root": str(runner.ROOT.resolve(strict=True)),
            "outputs_root": str(outputs.resolve(strict=True)),
            "tree_mode": "working-pre-cutover",
            "build_distributions": False,
        }
    )
    source = json.dumps(request, sort_keys=True, separators=(",", ":"))
    if kind == "duplicate-key":
        source = source.replace(
            '"schema_version":1',
            '"schema_version":1,"schema_version":1',
        )
    elif kind == "extra-key":
        source = source.replace("{", '{"extra":0,', 1)
    elif kind == "wrong-type":
        source = source.replace(
            '"build_distributions":false',
            '"build_distributions":0',
        )
    elif kind == "relative-source-root":
        request["source_root"] = "relative-source"
        source = json.dumps(request, sort_keys=True, separators=(",", ":"))
    elif kind == "relative-outputs-root":
        request["outputs_root"] = "relative-outputs"
        source = json.dumps(request, sort_keys=True, separators=(",", ":"))
    else:
        source = " " * (runner.MAX_BOUND_SCAN_REQUEST_BYTES + 1)

    with pytest.raises(AssertionError, match="coverage test repository binding"):
        runner._coverage_scan_request_document(source.encode())


def test_coverage_runner_propagates_failure_and_cleans_temp_directory(
    monkeypatch: MonkeyPatch,
    capsys,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    captured: dict[str, object] = {}
    calls = 0
    monkeypatch.setattr(runner, "_assert_runtime_matches_lock", lambda lock: None)

    def fake_run(command: tuple[str, ...], **kwargs: object) -> runner._PytestResult:
        nonlocal calls
        calls += 1
        assert command[1:3] == ("-m", "pytest")
        environment = kwargs["env"]
        assert isinstance(environment, dict)
        captured["coverage_file"] = Path(str(environment["COVERAGE_FILE"]))
        captured["coverage_json"] = Path(
            next(
                argument for argument in command if argument.startswith("--cov-report=json:")
            ).removeprefix("--cov-report=json:")
        )
        captured["failure_sideband"] = Path(
            next(
                argument
                for argument in command
                if argument.startswith("--hsconfig-failure-sideband=")
            ).removeprefix("--hsconfig-failure-sideband=")
        )
        captured["coverage_json"].write_text("failed-run-report", encoding="utf-8")
        captured["failure_sideband"].write_bytes(
            (json.dumps(_valid_failure_sideband_document()) + "\n").encode()
        )
        return runner._PytestResult(returncode=1, timed_out=False)

    monkeypatch.setattr(runner, "_run_pytest_bounded", fake_run)

    assert _run_unit_coverage_main(runner) == 1
    emitted = capsys.readouterr()
    assert emitted.out.count("\n") == 1
    assert json.loads(emitted.out)["errors"] == ["pytest coverage execution failed"]
    assert json.loads(emitted.out)["returncode"] == 1
    assert emitted.err == (
        "pytest failure identity: tests/test_coverage_contract.py::"
        "test_coverage_runner_propagates_failure_and_cleans_temp_directory "
        "phase=call\n"
    )
    assert calls == 1
    coverage_file = captured["coverage_file"]
    assert isinstance(coverage_file, Path)
    assert not coverage_file.parent.exists()
    failure_sideband = captured["failure_sideband"]
    assert isinstance(failure_sideband, Path)
    assert not failure_sideband.parent.exists()
    assert not (ROOT / "coverage.json").exists()


def test_coverage_runner_reports_valid_empty_as_session_level_failure(
    monkeypatch: MonkeyPatch,
    capsys,
) -> None:
    """Catches rc1 with valid empty evidence being called unavailable."""
    runner = importlib.import_module("scripts.run_coverage_gate")
    monkeypatch.setattr(runner, "_assert_runtime_matches_lock", lambda lock: None)

    def fake_run(command: tuple[str, ...], **kwargs: object) -> runner._PytestResult:
        del kwargs
        sideband = Path(
            next(
                argument
                for argument in command
                if argument.startswith("--hsconfig-failure-sideband=")
            ).removeprefix("--hsconfig-failure-sideband=")
        )
        sideband.write_bytes(
            b'{"failures":[],"recorder_status":"available",'
            b'"schema_version":1,"truncated":false}\n'
        )
        return runner._PytestResult(returncode=1, timed_out=False)

    monkeypatch.setattr(runner, "_run_pytest_bounded", fake_run)

    assert _run_unit_coverage_main(runner) == 1
    captured = capsys.readouterr()
    assert json.loads(captured.out)["returncode"] == 1
    assert captured.err == (
        "pytest failure identity: session-level failure; no node identities\n"
    )


def test_coverage_runner_fails_closed_when_failure_recorder_is_unavailable(
    monkeypatch: MonkeyPatch,
    capsys,
) -> None:
    """Catches recorder failure being trusted as a legitimate empty session."""
    runner = importlib.import_module("scripts.run_coverage_gate")
    monkeypatch.setattr(runner, "_assert_runtime_matches_lock", lambda lock: None)

    def fake_run(command: tuple[str, ...], **kwargs: object) -> runner._PytestResult:
        del kwargs
        sideband = Path(
            next(
                argument
                for argument in command
                if argument.startswith("--hsconfig-failure-sideband=")
            ).removeprefix("--hsconfig-failure-sideband=")
        )
        sideband.write_bytes(
            b'{"failures":[],"recorder_status":"unavailable",'
            b'"schema_version":1,"truncated":false}\n'
        )
        return runner._PytestResult(returncode=1, timed_out=False)

    monkeypatch.setattr(runner, "_run_pytest_bounded", fake_run)

    assert _run_unit_coverage_main(runner) == 2
    captured = capsys.readouterr()
    assert json.loads(captured.out)["returncode"] == 2
    assert captured.err == "pytest failure recorder unavailable\n"


def test_coverage_runner_fails_closed_when_failure_sideband_is_missing(
    monkeypatch: MonkeyPatch,
    capsys,
) -> None:
    """Catches missing identity evidence preserving an ambiguous child rc1."""
    runner = importlib.import_module("scripts.run_coverage_gate")
    monkeypatch.setattr(runner, "_assert_runtime_matches_lock", lambda lock: None)

    def fake_run(command: tuple[str, ...], **kwargs: object) -> runner._PytestResult:
        del kwargs
        sideband = Path(
            next(
                argument
                for argument in command
                if argument.startswith("--hsconfig-failure-sideband=")
            ).removeprefix("--hsconfig-failure-sideband=")
        )
        sideband.unlink()
        return runner._PytestResult(returncode=1, timed_out=False)

    monkeypatch.setattr(runner, "_run_pytest_bounded", fake_run)

    assert _run_unit_coverage_main(runner) == 2
    captured = capsys.readouterr()
    assert json.loads(captured.out)["returncode"] == 2
    assert captured.err == "pytest failure sideband missing\n"


def test_coverage_runner_emits_one_failure_json_for_pytest_failure(
    monkeypatch: MonkeyPatch,
    capsys,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    monkeypatch.setattr(runner, "_assert_runtime_matches_lock", lambda lock: None)

    def fake_run(command: tuple[str, ...], **kwargs: object) -> runner._PytestResult:
        assert command[1:3] == ("-m", "pytest")
        return runner._PytestResult(returncode=7, timed_out=False)

    monkeypatch.setattr(runner, "_run_pytest_bounded", fake_run)

    assert _run_unit_coverage_main(runner) == 2
    captured = capsys.readouterr()
    assert captured.out.count("\n") == 1
    assert json.loads(captured.out) == {
        "critical_modules": [],
            "errors": ["pytest coverage execution failed"],
            "global_branch_percent": None,
            "global_covered_branches": None,
            "global_num_branches": None,
        "global_minimum": 89.0,
        "passed": False,
        "returncode": 2,
        "target_met": False,
    }
    assert captured.err == "pytest failure sideband binding invalid\n"


def test_coverage_runner_emits_distinct_portable_failure_json_for_pytest_timeout(
    monkeypatch: MonkeyPatch,
    capsys,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    monkeypatch.setattr(runner, "_assert_runtime_matches_lock", lambda lock: None)
    stdout = runner._BoundedCapture()
    stderr = runner._BoundedCapture()

    def fake_bounded_process(
        command: tuple[str, ...], **kwargs: object
    ) -> runner._BoundedResult:
        del kwargs
        return runner._BoundedResult(
            completed=subprocess.CompletedProcess(
                command,
                0,
                stdout="",
                stderr="",
            ),
            timed_out=True,
            stdout=stdout,
            stderr=stderr,
        )

    monkeypatch.setattr(runner, "_run_bounded_process", fake_bounded_process)

    assert _run_unit_coverage_main(runner) == 2
    captured = capsys.readouterr()
    assert captured.out.count("\n") == 1
    document = json.loads(captured.out)
    assert document["passed"] is False
    assert document["returncode"] == 2
    assert document["errors"] == ["pytest coverage execution timed out"]
    assert captured.err == "pytest failure sideband binding invalid\n"


def test_real_child_returncode_124_is_not_misclassified_as_pytest_timeout(
    monkeypatch: MonkeyPatch,
    capsys,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    monkeypatch.setattr(runner, "_assert_runtime_matches_lock", lambda lock: None)
    stdout = runner._BoundedCapture()
    stderr = runner._BoundedCapture()

    def fake_bounded_process(
        command: tuple[str, ...], **kwargs: object
    ) -> runner._BoundedResult:
        del kwargs
        return runner._BoundedResult(
            completed=subprocess.CompletedProcess(
                command,
                124,
                stdout="",
                stderr="",
            ),
            timed_out=False,
            stdout=stdout,
            stderr=stderr,
        )

    monkeypatch.setattr(runner, "_run_bounded_process", fake_bounded_process)

    assert _run_unit_coverage_main(runner) == 2
    captured = capsys.readouterr()
    assert captured.out.count("\n") == 1
    document = json.loads(captured.out)
    assert document["passed"] is False
    assert document["returncode"] == 2
    assert document["errors"] == ["pytest coverage execution failed"]
    assert captured.err == "pytest failure sideband binding invalid\n"


def test_coverage_runner_forwards_checker_failure_as_one_contradiction_free_json(
    monkeypatch: MonkeyPatch,
    capsys,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    checker_document = _checker_document(passed=False)
    monkeypatch.setattr(runner, "_assert_runtime_matches_lock", lambda lock: None)

    def fake_run(command: tuple[str, ...], **kwargs: object) -> runner._PytestResult:
        assert command[1:3] == ("-m", "pytest")
        report = Path(
            next(
                argument for argument in command if argument.startswith("--cov-report=json:")
            ).removeprefix("--cov-report=json:")
        )
        report.write_text("{}", encoding="utf-8")
        return runner._PytestResult(returncode=0, timed_out=False)

    def fake_checker(
        command: tuple[str, ...], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        del kwargs
        return subprocess.CompletedProcess(
            command,
            1,
            stdout=json.dumps(checker_document, sort_keys=True, separators=(",", ":")) + "\n",
            stderr="",
        )

    monkeypatch.setattr(runner, "_run_pytest_bounded", fake_run)
    monkeypatch.setattr(runner, "_run_checker_bounded", fake_checker)

    assert _run_unit_coverage_main(runner) == 1
    captured = capsys.readouterr()
    assert captured.out.count("\n") == 1
    expected = dict(checker_document)
    expected["returncode"] = 1
    assert json.loads(captured.out) == expected
    assert captured.err == ""


def test_coverage_runner_emits_one_failure_json_when_a_subprocess_cannot_start(
    monkeypatch: MonkeyPatch,
    capsys,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    monkeypatch.setattr(runner, "_assert_runtime_matches_lock", lambda lock: None)

    def fake_run(command: tuple[str, ...], **kwargs: object) -> runner._PytestResult:
        del command, kwargs
        raise OSError("local path must not leak")

    monkeypatch.setattr(runner, "_run_pytest_bounded", fake_run)

    assert _run_unit_coverage_main(runner) == 2
    captured = capsys.readouterr()
    assert captured.out.count("\n") == 1
    document = json.loads(captured.out)
    assert document["passed"] is False
    assert document["returncode"] == 2
    assert document["errors"] == ["coverage subprocess execution failed"]
    assert "local path must not leak" not in captured.out


def test_coverage_runner_rejects_duplicate_checker_json_keys(capsys) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    result = subprocess.CompletedProcess(
        ["checker"],
        0,
        stdout='{"passed":false,"passed":true}\n',
        stderr="",
    )

    assert runner._forward_checker_result(result) == 2
    captured = capsys.readouterr()
    assert captured.out.count("\n") == 1
    document = json.loads(captured.out)
    assert document["passed"] is False
    assert document["returncode"] == 2
    assert document["errors"] == ["coverage checker emitted invalid JSON"]


def test_forwarded_checker_diagnostic_is_digest_only(capsys) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    local_path = str(ROOT / "private-checker-detail")
    result = subprocess.CompletedProcess(
        ["checker"],
        0,
        stdout=json.dumps(_checker_document()) + "\n",
        stderr=local_path,
    )

    assert runner._forward_checker_result(result) == 0
    captured = capsys.readouterr()
    assert local_path not in captured.err
    assert "sha256=" in captured.err


@pytest.mark.parametrize("constant", ("NaN", "Infinity", "-Infinity"))
def test_coverage_runner_rejects_nonfinite_checker_json(
    constant: str, capsys
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    result = subprocess.CompletedProcess(
        ["checker"],
        0,
        stdout=f'{{"passed":true,"value":{constant}}}\n',
        stderr="",
    )

    assert runner._forward_checker_result(result) == 2
    document = json.loads(capsys.readouterr().out)
    assert document["returncode"] == 2
    assert document["errors"] == ["coverage checker emitted invalid JSON"]


def test_coverage_runner_rejects_runtime_lock_mismatch_before_pytest(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    capsys,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    lock = tmp_path / f"pylock.{sys.version_info.major}.{sys.version_info.minor}.toml"
    lock.write_text(_lock_text("pytest", "0.0"), encoding="utf-8")
    subprocess_called = False

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        nonlocal subprocess_called
        del args, kwargs
        subprocess_called = True
        raise AssertionError("pytest must not start after a runtime/lock mismatch")

    monkeypatch.setattr(runner, "LOCK_FILE", lock, raising=False)
    monkeypatch.setattr(runner, "_run_pytest_bounded", fake_run)

    assert runner.main() == 2
    document = json.loads(capsys.readouterr().out)
    assert document["passed"] is False
    assert document["returncode"] == 2
    assert document["errors"] == ["coverage runtime does not match project lock"]
    assert subprocess_called is False


@pytest.mark.parametrize(
    ("category", "expected"),
    (
        ("manifest_binding", "manifest_binding"),
        ("repository_binding", "repository_binding"),
        ("artifact_binding", "artifact_binding"),
        ("distribution_set", "distribution_set"),
        ("distribution_version", "distribution_version"),
        ("distribution_origin", "distribution_origin"),
        ("local_project_binding", "local_project_binding"),
        ("runtime_tree_closure", "runtime_tree_closure"),
        (None, "unknown"),
    ),
)
def test_runtime_lock_failure_emits_one_closed_sanitized_category_before_pytest(
    category: str | None,
    expected: str,
    monkeypatch: MonkeyPatch,
    capsys,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    private_path = "C:" + "/" + "/".join(("private", "runtime", "manifest.json"))
    private_detail = (
        private_path + " "
        "https://credentials.example.invalid/wheel?token=secret "
        "NaN Infinity payload-secret"
    )
    error = (
        runner.RuntimeLockError(private_detail)
        if category is None
        else runner.RuntimeLockError(
            private_detail,
            category=runner.RuntimeLockCategory(category),
        )
    )
    pytest_called = False

    def reject_runtime(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise error

    def reject_pytest(*args: object, **kwargs: object) -> None:
        nonlocal pytest_called
        del args, kwargs
        pytest_called = True
        raise AssertionError("pytest must not start after a runtime/lock mismatch")

    monkeypatch.setattr(runner, "_assert_runtime_matches_lock", reject_runtime)
    monkeypatch.setattr(runner, "_run_pytest_bounded", reject_pytest)

    assert runner.main() == 2
    captured = capsys.readouterr()
    assert captured.out.count("\n") == 1
    document = json.loads(
        captured.out,
        object_pairs_hook=runner._closed_object,
        parse_constant=runner._reject_constant,
    )
    assert document == {
        "critical_modules": [],
        "errors": ["coverage runtime does not match project lock"],
        "global_branch_percent": None,
        "global_covered_branches": None,
        "global_num_branches": None,
        "global_minimum": 89.0,
        "passed": False,
        "returncode": 2,
        "runtime_lock_category": expected,
        "target_met": False,
    }
    assert captured.err == "coverage gate runtime lock mismatch\n"
    assert private_detail not in captured.out
    assert private_detail not in captured.err
    assert "credentials.example.invalid" not in captured.out + captured.err
    assert "payload-secret" not in captured.out + captured.err
    assert pytest_called is False


_RUNTIME_REPOSITORY_BINDING_REASONS = (
    "git_head_unavailable",
    "git_tree_unavailable",
    "git_status_unavailable",
    "git_index_unavailable",
    "repository_lstat_unavailable",
    "commit_changed",
    "tree_changed",
    "dirty_status",
    "root_device_changed",
    "root_inode_changed",
    "root_size_changed",
    "root_mtime_changed",
    "root_ctime_changed",
    "root_mode_changed",
)


def test_runtime_lock_failure_emits_one_closed_sanitized_reason_before_pytest(
    monkeypatch: MonkeyPatch,
    capsys,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    private_path = "C:" + "/" + "/".join(("private", "runtime", "repository"))
    private_detail = (
        private_path + " "
        "https://credentials.example.invalid/repository?token=secret "
        "private-oid-value"
    )
    error = runner.RuntimeLockError(
        private_detail,
        category=runner.RuntimeLockCategory.REPOSITORY_BINDING,
        reason=runner.RuntimeLockReason.GIT_HEAD_UNAVAILABLE,
    )
    pytest_called = False

    def reject_runtime(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise error

    def reject_pytest(*args: object, **kwargs: object) -> None:
        nonlocal pytest_called
        del args, kwargs
        pytest_called = True
        raise AssertionError("pytest must not start after a runtime/lock mismatch")

    monkeypatch.setattr(runner, "_assert_runtime_matches_lock", reject_runtime)
    monkeypatch.setattr(runner, "_run_pytest_bounded", reject_pytest)

    assert _run_unit_coverage_main(runner) == 2
    captured = capsys.readouterr()
    document = json.loads(
        captured.out,
        object_pairs_hook=runner._closed_object,
        parse_constant=runner._reject_constant,
    )
    assert document["runtime_lock_category"] == "repository_binding"
    assert document["runtime_lock_reason"] == "git_head_unavailable"
    assert captured.err == "coverage gate runtime lock mismatch\n"
    assert private_detail not in captured.out + captured.err
    assert "credentials.example.invalid" not in captured.out + captured.err
    assert "private-oid-value" not in captured.out + captured.err
    assert pytest_called is False


def test_runtime_lock_failure_discards_unassigned_reason_at_public_boundary(
    monkeypatch: MonkeyPatch,
    capsys,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    private_path = "C:" + "/" + "/".join(("private", "runtime", "repository"))
    private_detail = (
        private_path + " "
        "https://credentials.example.invalid/repository?token=secret "
        "private-oid-value"
    )
    error = runner.RuntimeLockError(
        private_detail,
        reason=runner.RuntimeLockReason.GIT_HEAD_UNAVAILABLE,
    )
    pytest_called = False

    def reject_runtime(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise error

    def reject_pytest(*args: object, **kwargs: object) -> None:
        nonlocal pytest_called
        del args, kwargs
        pytest_called = True
        raise AssertionError("pytest must not start after a runtime/lock mismatch")

    monkeypatch.setattr(runner, "_assert_runtime_matches_lock", reject_runtime)
    monkeypatch.setattr(runner, "_run_pytest_bounded", reject_pytest)

    assert _run_unit_coverage_main(runner) == 2
    captured = capsys.readouterr()
    assert captured.out.count("\n") == 1
    document = json.loads(
        captured.out,
        object_pairs_hook=runner._closed_object,
        parse_constant=runner._reject_constant,
    )
    assert document == {
        "critical_modules": [],
        "errors": ["coverage runtime does not match project lock"],
        "global_branch_percent": None,
        "global_covered_branches": None,
        "global_num_branches": None,
        "global_minimum": 89.0,
        "passed": False,
        "returncode": 2,
        "runtime_lock_category": "unknown",
        "target_met": False,
    }
    assert captured.err == "coverage gate runtime lock mismatch\n"
    assert private_detail not in captured.out + captured.err
    assert "credentials.example.invalid" not in captured.out + captured.err
    assert "private-oid-value" not in captured.out + captured.err
    assert "Traceback" not in captured.out + captured.err
    assert pytest_called is False


@pytest.mark.parametrize(
    "reason",
    (
        "repository_binding",
        "git-head-unavailable",
        "private/path/value",
    ),
)
def test_runtime_lock_reason_enum_rejects_unrecognized_public_values(
    reason: str,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")

    with pytest.raises(ValueError):
        runner.RuntimeLockReason(reason)


def test_runtime_lock_error_rejects_nonrepository_category_with_reason() -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")

    with pytest.raises(ValueError, match="repository_binding"):
        runner.RuntimeLockError(
            "sanitized failure",
            category=runner.RuntimeLockCategory.MANIFEST_BINDING,
            reason=runner.RuntimeLockReason.GIT_HEAD_UNAVAILABLE,
        )


def test_runtime_lock_error_rejects_explicit_non_enum_category_with_reason() -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")

    with pytest.raises(TypeError, match="RuntimeLockCategory"):
        runner.RuntimeLockError(
            "sanitized failure",
            category="manifest_binding",
            reason=runner.RuntimeLockReason.GIT_HEAD_UNAVAILABLE,
        )


def test_failure_report_rejects_reason_without_runtime_lock_category() -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")

    with pytest.raises(ValueError, match="category"):
        runner._failure_report(
            "sanitized failure",
            2,
            runtime_lock_reason=runner.RuntimeLockReason.GIT_HEAD_UNAVAILABLE,
        )


@pytest.mark.parametrize("category", ("unknown", "manifest_binding"))
def test_failure_report_rejects_nonrepository_category_with_reason(
    category: str,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")

    with pytest.raises(ValueError, match="repository_binding"):
        runner._failure_report(
            "sanitized failure",
            2,
            runtime_lock_category=runner.RuntimeLockCategory(category),
            runtime_lock_reason=runner.RuntimeLockReason.GIT_HEAD_UNAVAILABLE,
        )


def test_failure_report_rejects_non_enum_runtime_lock_reason() -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")

    with pytest.raises(TypeError, match="RuntimeLockReason"):
        runner._failure_report(
            "sanitized failure",
            2,
            runtime_lock_category=runner.RuntimeLockCategory.REPOSITORY_BINDING,
            runtime_lock_reason="git_head_unavailable",
        )


@pytest.mark.parametrize(
    "category",
    (
        "manifest_binding",
        "repository_binding",
        "artifact_binding",
        "distribution_set",
        "distribution_version",
        "distribution_origin",
        "local_project_binding",
        "runtime_tree_closure",
    ),
)
def test_runtime_lock_phase_assigns_a_closed_category_without_leaking_detail(
    category: str,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    private_detail = "C:" + "/" + "/".join(
        ("private", "runtime", "payload-secret")
    )

    with pytest.raises(runner.RuntimeLockError) as caught:
        with runner._runtime_lock_phase(runner.RuntimeLockCategory(category)):
            raise runner.RuntimeLockError(private_detail)

    assert caught.value.category.value == category
    assert str(caught.value) == private_detail


def test_runtime_lock_phase_preserves_a_more_specific_inner_category() -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")

    with pytest.raises(runner.RuntimeLockError) as caught:
        with runner._runtime_lock_phase(
            runner.RuntimeLockCategory.MANIFEST_BINDING
        ):
            raise runner.RuntimeLockError(
                "private detail",
                category=runner.RuntimeLockCategory.REPOSITORY_BINDING,
            )

    assert caught.value.category is runner.RuntimeLockCategory.REPOSITORY_BINDING


def test_runtime_lock_phase_preserves_reason_while_assigning_category() -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")

    with pytest.raises(runner.RuntimeLockError) as caught:
        with runner._runtime_lock_phase(runner.RuntimeLockCategory.REPOSITORY_BINDING):
            raise runner.RuntimeLockError(
                "private detail",
                reason=runner.RuntimeLockReason.GIT_STATUS_UNAVAILABLE,
            )

    assert caught.value.category is runner.RuntimeLockCategory.REPOSITORY_BINDING
    assert caught.value.reason is runner.RuntimeLockReason.GIT_STATUS_UNAVAILABLE


def test_runtime_lock_phase_rejects_nonrepository_category_for_reason() -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")

    with pytest.raises(ValueError, match="repository_binding"):
        with runner._runtime_lock_phase(runner.RuntimeLockCategory.MANIFEST_BINDING):
            raise runner.RuntimeLockError(
                "private detail",
                reason=runner.RuntimeLockReason.GIT_STATUS_UNAVAILABLE,
            )


def test_runtime_lock_rejects_a_second_visible_distribution_of_a_locked_package(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    lock = tmp_path / "pylock.toml"
    lock.write_text(_lock_text(), encoding="utf-8")

    class Distribution:
        def __init__(self, version: str) -> None:
            self.metadata = {"Name": "locked-pkg"}
            self.version = version

    monkeypatch.setattr(
        runner.importlib_metadata,
        "distributions",
        lambda: (
            Distribution("1.0"),
            Distribution("1.0"),
            type(
                "LocalDistribution",
                (),
                {"metadata": {"Name": "hsconfig"}, "version": "1.0.0"},
            )(),
        ),
    )

    with pytest.raises(runner.RuntimeLockError, match="duplicate") as caught:
        runner._assert_runtime_matches_lock(lock)
    assert caught.value.category is runner.RuntimeLockCategory.DISTRIBUTION_SET


def test_runtime_lock_categorizes_a_locked_distribution_version_mismatch(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    lock = tmp_path / "pylock.toml"
    lock.write_text(_lock_text(), encoding="utf-8")

    class Distribution:
        def __init__(self, name: str, version: str) -> None:
            self.metadata = {"Name": name}
            self.version = version

    monkeypatch.setattr(
        runner.importlib_metadata,
        "distributions",
        lambda: (
            Distribution("locked-pkg", "2.0"),
            Distribution("hsconfig", "1.0.0"),
        ),
    )

    with pytest.raises(runner.RuntimeLockError, match="version") as caught:
        runner._assert_runtime_matches_lock(lock)
    assert caught.value.category is runner.RuntimeLockCategory.DISTRIBUTION_VERSION


def test_runtime_lock_categorizes_local_project_metadata_failure(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    lock = tmp_path / "pylock.toml"
    lock.write_text(_lock_text("", ""), encoding="utf-8")
    local = type(
        "LocalDistribution",
        (),
        {"metadata": {"Name": "hsconfig"}, "version": "1.0.0"},
    )()
    monkeypatch.setattr(runner, "_locked_versions", lambda lock_file: {})
    monkeypatch.setattr(runner, "_load_runtime_manifest", lambda *args: None)
    monkeypatch.setattr(runner.importlib_metadata, "distributions", lambda: (local,))

    def reject_metadata(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise runner.RuntimeLockError("private local metadata path")

    monkeypatch.setattr(runner, "_read_bound_regular_file", reject_metadata)

    with pytest.raises(runner.RuntimeLockError) as caught:
        runner._assert_runtime_matches_lock(lock)
    assert caught.value.category is runner.RuntimeLockCategory.LOCAL_PROJECT_BINDING


def test_runtime_lock_categorizes_closed_runtime_tree_failure(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    lock = tmp_path / "pylock.toml"
    lock.write_text(_lock_text("", ""), encoding="utf-8")
    local = type(
        "LocalDistribution",
        (),
        {"metadata": {"Name": "hsconfig"}, "version": "1.0.0"},
    )()
    monkeypatch.setattr(runner, "_locked_versions", lambda lock_file: {})
    monkeypatch.setattr(
        runner,
        "_load_runtime_manifest",
        lambda *args: {"hsconfig": {}},
    )
    monkeypatch.setattr(runner.importlib_metadata, "distributions", lambda: (local,))
    monkeypatch.setattr(runner, "_assert_distribution_origin", lambda *args, **kwargs: set())

    def reject_tree(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise runner.RuntimeLockError("private runtime tree path")

    monkeypatch.setattr(runner, "_assert_runtime_tree_closed", reject_tree)

    with pytest.raises(runner.RuntimeLockError) as caught:
        runner._assert_runtime_matches_lock(lock)
    assert caught.value.category is runner.RuntimeLockCategory.RUNTIME_TREE_CLOSURE


@pytest.mark.parametrize("kind", ("symlink", "hardlink"))
def test_runtime_lock_rejects_linked_lock_files(
    tmp_path: Path,
    kind: str,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    target = tmp_path / "target.toml"
    target.write_text(_lock_text("pytest"), encoding="utf-8")
    lock = tmp_path / "pylock.toml"
    if kind == "symlink":
        try:
            lock.symlink_to(target)
        except OSError:
            pytest.skip("symlinks unavailable")
    else:
        os.link(target, lock)

    with pytest.raises(runner.RuntimeLockError, match="unsafe"):
        runner._locked_versions(lock)


def test_runtime_lock_preserves_exact_selected_wheel_url_and_sha256(
    tmp_path: Path,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    lock = tmp_path / "pylock.toml"
    lock.write_text(_lock_text("locked-pkg", "1.0"), encoding="utf-8")

    assert runner._locked_wheels(lock) == {
        "locked-pkg": {
            ("https://example.invalid/locked-pkg-1.0-py3-none-any.whl", "0" * 64)
        }
    }


def test_runtime_wheel_inventory_rejects_link_members(tmp_path: Path) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    wheel = tmp_path / "linked.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        info = zipfile.ZipInfo("package/link")
        info.create_system = 3
        info.external_attr = (0o120777 << 16)
        archive.writestr(info, "outside")

    with pytest.raises(runner.RuntimeLockError, match="inventory"):
        runner._wheel_inventory(wheel.read_bytes())


@pytest.mark.parametrize(
    "relative",
    ("Lib/site-packages/extra.py", "Scripts/extra.exe", "Include/extra.h", "share/extra.dat"),
)
def test_runtime_tree_closure_rejects_unrecorded_payload_in_every_install_scheme(
    tmp_path: Path,
    relative: str,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    environment = tmp_path / "environment"
    payload = environment / Path(*relative.split("/"))
    payload.parent.mkdir(parents=True)
    payload.write_text("unrecorded", encoding="utf-8")

    with pytest.raises(runner.RuntimeLockError, match="unrecorded"):
        runner._assert_runtime_tree_closed(set(), environment)


@pytest.mark.skipif(
    sys.platform != "linux" or sys.maxsize <= 2**32,
    reason="canonical lib64 venv link is Linux 64-bit infrastructure",
)
def test_runtime_tree_closure_allows_only_exact_linux_lib64_to_lib_link(
    tmp_path: Path,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    environment = tmp_path / "environment"
    library = environment / "lib"
    library.mkdir(parents=True)
    payload = library / "claimed.py"
    payload.write_text("claimed", encoding="utf-8")
    (environment / "lib64").symlink_to("lib", target_is_directory=True)

    runner._assert_runtime_tree_closed({payload.resolve()}, environment)

    (environment / "lib64").unlink()
    outside = tmp_path / "outside"
    outside.mkdir()
    (environment / "lib64").symlink_to(outside, target_is_directory=True)
    with pytest.raises(runner.RuntimeLockError, match="linked"):
        runner._assert_runtime_tree_closed({payload.resolve()}, environment)


def test_distribution_record_rejects_original_symlink_before_resolution(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    environment = tmp_path / "environment"
    root = environment / "Lib" / "site-packages"
    dist_info = root / "example-1.0.dist-info"
    dist_info.mkdir(parents=True)
    target = environment / "target.py"
    target.write_text("payload", encoding="utf-8")
    linked = root / "example.py"
    try:
        linked.symlink_to(target)
    except OSError:
        pytest.skip("symlinks unavailable")
    digest = hashlib.sha256(target.read_bytes()).digest()
    encoded = base64.urlsafe_b64encode(digest).decode().rstrip("=")
    record = f"example.py,sha256={encoded},{target.stat().st_size}\nexample-1.0.dist-info/RECORD,,\n"

    class Distribution:
        def read_text(self, filename: str) -> str | None:
            return {
                "INSTALLER": "pip\n",
                "WHEEL": "Wheel-Version: 1.0\n",
                "RECORD": record,
                "direct_url.json": None,
            }.get(filename)

        def locate_file(self, filename: str) -> Path:
            del filename
            return root

    monkeypatch.setattr(
        runner.sysconfig,
        "get_paths",
        lambda: {"purelib": str(root), "platlib": str(root), "scripts": str(environment / "Scripts")},
    )
    monkeypatch.setattr(runner.sys, "prefix", str(environment))

    with pytest.raises(runner.RuntimeLockError, match="unverifiable"):
        runner._assert_distribution_origin(Distribution(), local_project=False)


def _bound_nonlocal_distribution(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    *,
    include_direct_url: bool = True,
    console_scripts: tuple[str, ...] = (),
    runtime_scripts: tuple[str, ...] = (),
) -> tuple[object, dict[str, object], str]:
    runner = importlib.import_module("scripts.run_coverage_gate")
    bootstrap = tmp_path / "bootstrap"
    environment = bootstrap / "environment"
    root = environment / "Lib" / "site-packages"
    dist_info = root / "pip-26.1.2.dist-info"
    dist_info.mkdir(parents=True)
    package_path = root / "pip.py"
    package_payload = b"VERSION = '26.1.2'\n"
    package_path.write_bytes(package_payload)
    wheel_payload = b"Wheel-Version: 1.0\n"
    (dist_info / "WHEEL").write_bytes(wheel_payload)
    (dist_info / "INSTALLER").write_bytes(b"pip\n")
    entry_points_payload = (
        "[console_scripts]\n"
        + "".join(
            f"{name}=pip._internal.cli.main:main\n" for name in console_scripts
        )
    ).encode("utf-8")
    if console_scripts:
        (dist_info / "entry_points.txt").write_bytes(entry_points_payload)

    wheel_path = bootstrap / "artifacts" / "pip-26.1.2-py3-none-any.whl"
    wheel_path.parent.mkdir()
    with zipfile.ZipFile(wheel_path, "w") as archive:
        archive.writestr("pip.py", package_payload)
        archive.writestr("pip-26.1.2.dist-info/WHEEL", wheel_payload)
        if console_scripts:
            archive.writestr(
                "pip-26.1.2.dist-info/entry_points.txt",
                entry_points_payload,
            )
        archive.writestr("pip-26.1.2.dist-info/RECORD", b"")
    wheel_source = wheel_path.read_bytes()
    digest = hashlib.sha256(wheel_source).hexdigest()
    direct_url = json.dumps(
        {
            "archive_info": {
                "hash": f"sha256={digest}",
                "hashes": {"sha256": digest},
            },
            "url": wheel_path.resolve(strict=True).as_uri(),
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    if include_direct_url:
        (dist_info / "direct_url.json").write_text(direct_url, encoding="utf-8")

    rows = [
        _runtime_record_row("pip.py", package_payload),
        _runtime_record_row("pip-26.1.2.dist-info/WHEEL", wheel_payload),
        _runtime_record_row("pip-26.1.2.dist-info/INSTALLER", b"pip\n"),
    ]
    if console_scripts:
        rows.append(
            _runtime_record_row(
                "pip-26.1.2.dist-info/entry_points.txt",
                entry_points_payload,
            )
        )
    scripts = environment / "Scripts"
    for relative_script in runtime_scripts:
        script_path = scripts / Path(*relative_script.split("/"))
        script_path.parent.mkdir(parents=True, exist_ok=True)
        script_payload = f"launcher:{relative_script}\n".encode("utf-8")
        script_path.write_bytes(script_payload)
        record_path = os.path.relpath(script_path, root).replace("\\", "/")
        rows.append(_runtime_record_row(record_path, script_payload))
    if include_direct_url:
        rows.append(
            _runtime_record_row(
                "pip-26.1.2.dist-info/direct_url.json",
                direct_url.encode("utf-8"),
            )
        )
    rows.append("pip-26.1.2.dist-info/RECORD,,")
    record = "\n".join(rows) + "\n"
    (dist_info / "RECORD").write_text(record, encoding="utf-8")

    class Distribution:
        def __init__(self) -> None:
            self.current_direct_url = direct_url if include_direct_url else None
            self.current_record = record
            self.root = root
            self.dist_info = dist_info
            self.on_direct_url_read = None

        def read_text(self, filename: str) -> str | None:
            value = {
                "INSTALLER": "pip\n",
                "WHEEL": wheel_payload.decode("utf-8"),
                "RECORD": self.current_record,
                "direct_url.json": self.current_direct_url,
            }.get(filename)
            if filename == "direct_url.json" and self.on_direct_url_read is not None:
                callback = self.on_direct_url_read
                self.on_direct_url_read = None
                callback()
            return value

        def locate_file(self, filename: str) -> Path:
            del filename
            return root

    monkeypatch.setattr(
        runner.sysconfig,
        "get_paths",
        lambda: {
            "purelib": str(root),
            "platlib": str(root),
            "scripts": str(environment / "Scripts"),
        },
    )
    monkeypatch.setattr(runner.sys, "prefix", str(environment))
    artifact: dict[str, object] = {
        "name": "pip",
        "version": "26.1.2",
        "url": "https://example.invalid/pip.whl",
        "wheel_path": str(wheel_path),
        "sha256": digest,
        "install": True,
        "allowed_startup_surfaces": [],
        "files": runner._wheel_inventory(wheel_source),
        "_wheel_source": wheel_source,
    }
    return Distribution(), artifact, direct_url


def _runtime_record_row(relative: str, payload: bytes) -> str:
    encoded = base64.urlsafe_b64encode(hashlib.sha256(payload).digest()).decode().rstrip("=")
    return f"{relative},sha256={encoded},{len(payload)}"


def _set_runtime_direct_url_payload(
    distribution: object,
    payload: str,
    *,
    write_payload: bool,
) -> None:
    relative = "pip-26.1.2.dist-info/direct_url.json"
    record = str(getattr(distribution, "current_record"))
    rows = [row for row in record.splitlines() if not row.startswith(relative + ",")]
    rows.insert(-1, _runtime_record_row(relative, payload.encode("utf-8")))
    updated = "\n".join(rows) + "\n"
    setattr(distribution, "current_record", updated)
    dist_info = Path(getattr(distribution, "dist_info"))
    (dist_info / "RECORD").write_text(updated, encoding="utf-8")
    if write_payload:
        (dist_info / "direct_url.json").write_bytes(payload.encode("utf-8"))


def test_distribution_origin_accepts_manifest_bound_pip_direct_url(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    distribution, artifact, _direct_url = _bound_nonlocal_distribution(
        tmp_path,
        monkeypatch,
    )

    runner._assert_distribution_origin(
        distribution,
        local_project=False,
        artifact=artifact,
    )


def test_distribution_origin_accepts_hash_bound_initial_pip_bootstrap_wheel(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    distribution, artifact, _direct_url = _bound_nonlocal_distribution(
        tmp_path,
        monkeypatch,
    )
    bootstrap = tmp_path / "bootstrap"
    wheel_name = "pip-26.1.2-py3-none-any.whl"
    initial_wheel = bootstrap / wheel_name
    initial_wheel.write_bytes(artifact["_wheel_source"])
    manifest_wheel = bootstrap / "dependency-wheels" / wheel_name
    manifest_wheel.parent.mkdir()
    manifest_wheel.write_bytes(artifact["_wheel_source"])
    artifact["wheel_path"] = str(manifest_wheel)
    direct_url = json.dumps(
        {
            "archive_info": {
                "hash": f"sha256={artifact['sha256']}",
                "hashes": {"sha256": artifact["sha256"]},
            },
            "url": initial_wheel.resolve(strict=True).as_uri(),
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    distribution.current_direct_url = direct_url
    _set_runtime_direct_url_payload(distribution, direct_url, write_payload=True)

    runner._assert_distribution_origin(
        distribution,
        local_project=False,
        artifact=artifact,
    )


def test_distribution_origin_preserves_index_install_without_direct_url(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    distribution, artifact, _direct_url = _bound_nonlocal_distribution(
        tmp_path,
        monkeypatch,
        include_direct_url=False,
    )

    runner._assert_distribution_origin(
        distribution,
        local_project=False,
        artifact=artifact,
    )


def test_distribution_origin_accepts_manifest_validated_raw_wheel_overlay(
    tmp_path: Path,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    root = tmp_path / "bootstrap" / "build-backend"
    dist_info = root / "coverage-7.15.2.dist-info"
    dist_info.mkdir(parents=True)
    package = root / "coverage.py"
    package.write_bytes(b"VERSION = '7.15.2'\n")
    (dist_info / "WHEEL").write_text("Wheel-Version: 1.0\n", encoding="utf-8")
    (dist_info / "RECORD").write_text("coverage.py,,\n", encoding="utf-8")

    class Distribution:
        def read_text(self, filename: str) -> str | None:
            return {
                "INSTALLER": None,
                "WHEEL": "Wheel-Version: 1.0\n",
                "RECORD": "coverage.py,,\n",
                "direct_url.json": None,
            }.get(filename)

        def locate_file(self, filename: str) -> Path:
            del filename
            return root

    artifact = {
        "name": "coverage",
        "version": "7.15.2",
        "install": False,
        "allowed_startup_surfaces": ["a1_coverage.pth"],
        "_runtime_root": root,
    }

    assert (
        runner._assert_distribution_origin(
            Distribution(),
            local_project=False,
            artifact=artifact,
        )
        == set()
    )


def test_distribution_origin_accepts_bound_pip_interpreter_versioned_launcher(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    launcher_suffix = ".exe" if os.name == "nt" else ""
    versioned_launcher = (
        f"pip{sys.version_info.major}.{sys.version_info.minor}{launcher_suffix}"
    )
    distribution, artifact, _direct_url = _bound_nonlocal_distribution(
        tmp_path,
        monkeypatch,
        console_scripts=("pip", "pip3"),
        runtime_scripts=(
            f"pip{launcher_suffix}",
            f"pip3{launcher_suffix}",
            versioned_launcher,
        ),
    )

    runner._assert_distribution_origin(
        distribution,
        local_project=False,
        artifact=artifact,
    )


def test_entry_point_paths_authorize_exact_posix_pip_interpreter_launcher(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    distribution, artifact, _direct_url = _bound_nonlocal_distribution(
        tmp_path,
        monkeypatch,
        console_scripts=("pip", "pip3"),
    )
    del distribution
    scripts = Path(runner.sysconfig.get_paths()["scripts"])
    root = tmp_path / "bootstrap" / "environment" / "Lib" / "site-packages"
    expected = os.path.relpath(
        scripts / f"pip{sys.version_info.major}.{sys.version_info.minor}",
        root,
    ).replace("\\", "/")
    platform_os = type("PlatformOS", (), {"name": "posix", "path": os.path})()
    monkeypatch.setattr(runner, "os", platform_os)

    assert expected in runner._entry_point_script_paths(artifact, root)


@pytest.mark.parametrize(
    "case",
    (
        "wrong-minor",
        "wrong-major",
        "pip3.10",
        "pip4",
        "foreign-name",
        "foreign-path",
        "missing-pip3-entry-point",
        "non-pip-artifact",
    ),
)
def test_distribution_origin_rejects_unbound_versioned_pip_launcher(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    case: str,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    major = sys.version_info.major
    minor = sys.version_info.minor
    launcher_suffix = ".exe" if os.name == "nt" else ""
    launcher = {
        "wrong-minor": f"pip{major}.{minor + 1}{launcher_suffix}",
        "wrong-major": f"pip{major + 1}.{minor}{launcher_suffix}",
        "pip3.10": (
            f"pip3.10{launcher_suffix}"
            if (major, minor) != (3, 10)
            else f"pip3.9{launcher_suffix}"
        ),
        "pip4": f"pip4{launcher_suffix}",
        "foreign-name": f"not-pip{major}.{minor}{launcher_suffix}",
        "foreign-path": f"../Foreign/pip{major}.{minor}{launcher_suffix}",
        "missing-pip3-entry-point": f"pip{major}.{minor}{launcher_suffix}",
        "non-pip-artifact": f"pip{major}.{minor}{launcher_suffix}",
    }[case]
    console_scripts = (
        ("pip",)
        if case == "missing-pip3-entry-point"
        else ("pip", "pip3")
    )
    distribution, artifact, _direct_url = _bound_nonlocal_distribution(
        tmp_path,
        monkeypatch,
        console_scripts=console_scripts,
        runtime_scripts=(
            f"pip{launcher_suffix}",
            f"pip3{launcher_suffix}",
            launcher,
        ),
    )
    if case == "non-pip-artifact":
        artifact["name"] = "setuptools"

    with pytest.raises(runner.RuntimeLockError, match="RECORD|origin"):
        runner._assert_distribution_origin(
            distribution,
            local_project=False,
            artifact=artifact,
        )


def _setuptools_entry_point_artifact(
    tmp_path: Path,
    *,
    include_own_root: bool = True,
    foreign_root: bool = False,
    case_alias: bool = False,
    traversal: bool = False,
    artifact_name: str = "setuptools",
    artifact_version: str = "83.0.0",
) -> dict[str, object]:
    runner = importlib.import_module("scripts.run_coverage_gate")
    wheel = tmp_path / "setuptools-83.0.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("setuptools/__init__.py", b"__version__ = '83.0.0'\n")
        if include_own_root:
            archive.writestr(
                "setuptools-83.0.0.dist-info/WHEEL",
                b"Wheel-Version: 1.0\n",
            )
            archive.writestr(
                "setuptools-83.0.0.dist-info/entry_points.txt",
                b"[console_scripts]\neasy_install=setuptools.command.easy_install:main\n",
            )
            archive.writestr("setuptools-83.0.0.dist-info/RECORD", b"")
        archive.writestr(
            "setuptools/_vendor/wheel-0.46.3.dist-info/entry_points.txt",
            b"[console_scripts]\nwheel=wheel.cli:main\n",
        )
        if foreign_root:
            archive.writestr(
                "foreign-1.0.dist-info/entry_points.txt",
                b"[console_scripts]\nforeign=foreign:main\n",
            )
        if case_alias:
            archive.writestr(
                "setuptools-83.0.0.dist-info/ENTRY_POINTS.TXT",
                b"[console_scripts]\ncase_alias=foreign:main\n",
            )
        if traversal:
            archive.writestr(
                "setuptools-83.0.0.dist-info/../foreign.py",
                b"raise SystemExit\n",
            )
    source = wheel.read_bytes()
    files: list[dict[str, object]] = []
    if not traversal:
        files = runner._wheel_inventory(source)
    return {
        "name": artifact_name,
        "version": artifact_version,
        "files": files,
        "_wheel_source": source,
    }


def test_entry_point_scripts_ignore_vendored_setuptools_metadata(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    root = tmp_path / "environment" / "Lib" / "site-packages"
    scripts = tmp_path / "environment" / "Scripts"
    monkeypatch.setattr(
        runner.sysconfig,
        "get_paths",
        lambda: {"scripts": str(scripts)},
    )
    artifact = _setuptools_entry_point_artifact(tmp_path)
    suffixes = (".exe", "-script.py") if os.name == "nt" else ("",)
    expected = {
        os.path.relpath(scripts / f"easy_install{suffix}", root).replace("\\", "/")
        for suffix in suffixes
    }

    assert runner._entry_point_script_paths(artifact, root) == expected


@pytest.mark.parametrize(
    "case",
    (
        "foreign-authority",
        "multiple-top-level-roots",
        "missing-top-level-root",
        "name-mismatch",
        "version-mismatch",
        "case-ambiguity",
        "traversal",
    ),
)
def test_entry_point_scripts_reject_unbound_top_level_authority(
    tmp_path: Path,
    case: str,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    artifact = _setuptools_entry_point_artifact(
        tmp_path,
        include_own_root=case not in {"foreign-authority", "missing-top-level-root"},
        foreign_root=case in {"foreign-authority", "multiple-top-level-roots"},
        case_alias=case == "case-ambiguity",
        traversal=case == "traversal",
        artifact_name="other" if case == "name-mismatch" else "setuptools",
        artifact_version="82.0.0" if case == "version-mismatch" else "83.0.0",
    )

    with pytest.raises(runner.RuntimeLockError, match="entry point|inventory"):
        runner._entry_point_script_paths(artifact, tmp_path / "site-packages")


def test_distribution_origin_rejects_bound_direct_url_for_non_pip_artifact(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    distribution, artifact, _direct_url = _bound_nonlocal_distribution(
        tmp_path,
        monkeypatch,
    )
    artifact["name"] = "setuptools"

    with pytest.raises(runner.RuntimeLockError, match="origin"):
        runner._assert_distribution_origin(
            distribution,
            local_project=False,
            artifact=artifact,
        )


def test_distribution_origin_rejects_foreign_direct_url_record_path(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    distribution, artifact, _direct_url = _bound_nonlocal_distribution(
        tmp_path,
        monkeypatch,
    )
    root = Path(getattr(distribution, "root"))
    source = root / "pip-26.1.2.dist-info" / "direct_url.json"
    foreign = root / "evil-1.0.dist-info" / "direct_url.json"
    foreign.parent.mkdir()
    source.replace(foreign)
    record = str(getattr(distribution, "current_record")).replace(
        "pip-26.1.2.dist-info/direct_url.json",
        "evil-1.0.dist-info/direct_url.json",
    )
    setattr(distribution, "current_record", record)
    (root / "pip-26.1.2.dist-info" / "RECORD").write_text(record, encoding="utf-8")

    with pytest.raises(runner.RuntimeLockError, match="RECORD|origin"):
        runner._assert_distribution_origin(
            distribution,
            local_project=False,
            artifact=artifact,
        )


def test_distribution_origin_rejects_read_text_disk_byte_mismatch(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    distribution, artifact, direct_url = _bound_nonlocal_distribution(
        tmp_path,
        monkeypatch,
    )
    reserialized = json.dumps(json.loads(direct_url), indent=2)
    assert reserialized != direct_url
    _set_runtime_direct_url_payload(distribution, reserialized, write_payload=True)

    with pytest.raises(runner.RuntimeLockError, match="origin"):
        runner._assert_distribution_origin(
            distribution,
            local_project=False,
            artifact=artifact,
        )


def test_distribution_origin_rejects_direct_url_metadata_to_record_toctou(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    distribution, artifact, direct_url = _bound_nonlocal_distribution(
        tmp_path,
        monkeypatch,
    )
    reserialized = json.dumps(json.loads(direct_url), indent=2)
    _set_runtime_direct_url_payload(distribution, reserialized, write_payload=False)
    direct_path = Path(getattr(distribution, "dist_info")) / "direct_url.json"
    distribution.on_direct_url_read = lambda: direct_path.write_bytes(
        reserialized.encode("utf-8")
    )

    with pytest.raises(runner.RuntimeLockError, match="origin"):
        runner._assert_distribution_origin(
            distribution,
            local_project=False,
            artifact=artifact,
        )


def _bound_local_distribution(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    *,
    committed_payload: bytes = b"VALUE = 1\n",
    installed_payload: bytes = b"VALUE = 1\r\n",
    installed_relative: str = "hsconfig/module.py",
    include_installed_package: bool = True,
    include_extra_committed_path: bool = False,
) -> tuple[object, dict[str, object], Path]:
    runner = importlib.import_module("scripts.run_coverage_gate")
    repository = tmp_path / "repository"
    source = repository / "src" / "hsconfig" / "module.py"
    source.parent.mkdir(parents=True)
    source.write_bytes(committed_payload)
    if include_extra_committed_path:
        (source.parent / "extra.py").write_bytes(b"EXTRA = True\n")
    subprocess.run(("git", "init", "-q", str(repository)), check=True)
    subprocess.run(
        ("git", "-C", str(repository), "config", "user.name", "Coverage Contract"),
        check=True,
    )
    subprocess.run(
        (
            "git",
            "-C",
            str(repository),
            "config",
            "user.email",
            "coverage-contract@example.invalid",
        ),
        check=True,
    )
    subprocess.run(
        ("git", "-C", str(repository), "config", "core.autocrlf", "false"),
        check=True,
    )
    subprocess.run(("git", "-C", str(repository), "add", "."), check=True)
    subprocess.run(
        ("git", "-C", str(repository), "commit", "-q", "-m", "fixture"),
        check=True,
    )
    commit_oid = subprocess.run(
        ("git", "-C", str(repository), "rev-parse", "HEAD"),
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.strip()
    tree_oid = subprocess.run(
        ("git", "-C", str(repository), "rev-parse", "HEAD^{tree}"),
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.strip()

    environment = tmp_path / "bootstrap" / "environment"
    root = environment / "Lib" / "site-packages"
    dist_info = root / "hsconfig-1.0.0.dist-info"
    package = root / Path(*installed_relative.split("/"))
    package.parent.mkdir(parents=True)
    dist_info.mkdir(parents=True)
    if include_installed_package:
        package.write_bytes(installed_payload)
    wheel_payload = b"Wheel-Version: 1.0\n"
    (dist_info / "WHEEL").write_bytes(wheel_payload)
    (dist_info / "INSTALLER").write_bytes(b"pip\n")

    wheel_path = tmp_path / "bootstrap" / "local-wheel" / "hsconfig.whl"
    wheel_path.parent.mkdir()
    with zipfile.ZipFile(wheel_path, "w") as archive:
        if include_installed_package:
            archive.writestr(installed_relative, installed_payload)
        archive.writestr("hsconfig-1.0.0.dist-info/WHEEL", wheel_payload)
        archive.writestr("hsconfig-1.0.0.dist-info/RECORD", b"")
    wheel_source = wheel_path.read_bytes()
    digest = hashlib.sha256(wheel_source).hexdigest()
    direct_url = json.dumps(
        {
            "archive_info": {
                "hash": f"sha256={digest}",
                "hashes": {"sha256": digest},
            },
            "url": wheel_path.resolve(strict=True).as_uri(),
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    (dist_info / "direct_url.json").write_bytes(direct_url.encode("utf-8"))
    rows = []
    if include_installed_package:
        rows.append(_runtime_record_row(installed_relative, installed_payload))
    rows.extend([
        _runtime_record_row("hsconfig-1.0.0.dist-info/WHEEL", wheel_payload),
        _runtime_record_row("hsconfig-1.0.0.dist-info/INSTALLER", b"pip\n"),
        _runtime_record_row(
            "hsconfig-1.0.0.dist-info/direct_url.json",
            direct_url.encode("utf-8"),
        ),
        "hsconfig-1.0.0.dist-info/RECORD,,",
    ])
    record = "\n".join(rows) + "\n"
    (dist_info / "RECORD").write_text(record, encoding="utf-8")

    class Distribution:
        def __init__(self) -> None:
            self.current_direct_url = direct_url
            self.current_record = record
            self.dist_info = dist_info
            self.on_direct_url_read = None

        def read_text(self, filename: str) -> str | None:
            value = {
                "INSTALLER": "pip\n",
                "WHEEL": wheel_payload.decode("utf-8"),
                "RECORD": self.current_record,
                "direct_url.json": self.current_direct_url,
            }.get(filename)
            if filename == "direct_url.json" and self.on_direct_url_read is not None:
                callback = self.on_direct_url_read
                self.on_direct_url_read = None
                callback()
            return value

        def locate_file(self, filename: str) -> Path:
            del filename
            return root

    monkeypatch.setattr(runner, "ROOT", repository)
    monkeypatch.setattr(
        runner.sysconfig,
        "get_paths",
        lambda: {
            "purelib": str(root),
            "platlib": str(root),
            "scripts": str(environment / "Scripts"),
        },
    )
    monkeypatch.setattr(runner.sys, "prefix", str(environment))
    artifact: dict[str, object] = {
        "name": "hsconfig",
        "version": "1.0.0",
        "wheel_path": str(wheel_path),
        "sha256": digest,
        "files": runner._wheel_inventory(wheel_source),
        "_wheel_source": wheel_source,
        "_commit_oid": commit_oid,
        "_tree_oid": tree_oid,
        "_repository_root": repository.resolve(strict=True),
    }
    return Distribution(), artifact, repository


def _set_local_direct_url_payload(
    distribution: object,
    payload: str,
    *,
    write_payload: bool,
) -> None:
    relative = "hsconfig-1.0.0.dist-info/direct_url.json"
    record = str(getattr(distribution, "current_record"))
    rows = [row for row in record.splitlines() if not row.startswith(relative + ",")]
    rows.insert(-1, _runtime_record_row(relative, payload.encode("utf-8")))
    updated = "\n".join(rows) + "\n"
    setattr(distribution, "current_record", updated)
    dist_info = Path(getattr(distribution, "dist_info"))
    (dist_info / "RECORD").write_text(updated, encoding="utf-8")
    if write_payload:
        (dist_info / "direct_url.json").write_bytes(payload.encode("utf-8"))


def _write_local_runtime_manifest(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    artifact: dict[str, object],
    repository: Path,
) -> Path:
    runner = importlib.import_module("scripts.run_coverage_gate")
    lock = tmp_path / "runtime-lock.toml"
    lock.write_text("packages = []\n", encoding="utf-8")
    monkeypatch.setattr(runner, "LOCK_FILE", lock)
    sentinel = "c" * 64
    bootstrap_root = tmp_path / "bootstrap"
    source_root = bootstrap_root / "committed-source"
    source_root.mkdir()
    listing = subprocess.run(
        ("git", "-C", str(repository), "ls-tree", "-rz", "--full-tree", "HEAD"),
        check=True,
        capture_output=True,
    ).stdout
    source_inventory: list[dict[str, str]] = []
    for record in listing[:-1].split(b"\0"):
        metadata, raw_path = record.split(b"\t", 1)
        mode, object_type, oid = metadata.split(b" ")
        assert object_type == b"blob"
        relative = raw_path.decode("utf-8")
        payload = subprocess.run(
            ("git", "-C", str(repository), "cat-file", "blob", oid.decode("ascii")),
            check=True,
            capture_output=True,
        ).stdout
        destination = source_root.joinpath(*relative.split("/"))
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
        source_inventory.append(
            {
                "path": relative,
                "sha256": hashlib.sha256(payload).hexdigest(),
                "git_mode": mode.decode("ascii"),
            }
        )
    source_inventory.sort(key=lambda row: row["path"])
    source_inventory_sha256 = hashlib.sha256(
        json.dumps(
            source_inventory,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
    ).hexdigest()
    build_backend_root = bootstrap_root / "build-backend"
    build_backend_root.mkdir()
    manifest = bootstrap_root / "runtime-manifest.json"
    document = {
        "schema_version": 1,
        "python_minor": f"{sys.version_info.major}.{sys.version_info.minor}",
        "repository": str(repository.resolve(strict=True)),
        "commit_oid": artifact["_commit_oid"],
        "tree_oid": artifact["_tree_oid"],
        "source_inventory": source_inventory,
        "source_inventory_sha256": source_inventory_sha256,
        "build_backend_root": str(build_backend_root),
        "environment_root": str(Path(sys.prefix).resolve(strict=True)),
        "lock_sha256": hashlib.sha256(lock.read_bytes()).hexdigest(),
        "sentinel_sha256": hashlib.sha256(sentinel.encode("ascii")).hexdigest(),
        "artifacts": [],
        "local_project": {
            key: artifact[key]
            for key in ("name", "version", "wheel_path", "sha256", "files")
        }
        | {"source_inventory_sha256": source_inventory_sha256},
    }
    source = json.dumps(document, separators=(",", ":"), sort_keys=True).encode("utf-8")
    manifest.write_bytes(source)
    monkeypatch.setenv("HSCONFIG_RELEASE_GATE_BOOTSTRAP_SENTINEL", sentinel)
    monkeypatch.setenv("HSCONFIG_RUNTIME_MANIFEST", str(manifest))
    monkeypatch.setenv("HSCONFIG_RUNTIME_MANIFEST_SHA256", hashlib.sha256(source).hexdigest())
    return lock


def _runtime_source_inventory_document(
    rows: list[dict[str, str]],
) -> dict[str, object]:
    digest = hashlib.sha256(
        json.dumps(
            rows,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
    ).hexdigest()
    return {
        "source_inventory": rows,
        "source_inventory_sha256": digest,
        "local_project": {"source_inventory_sha256": digest},
    }


def _create_directory_redirect(link: Path, target: Path) -> None:
    if os.name == "nt":
        environment = os.environ.copy()
        environment["HSCONFIG_TEST_LINK_PATH"] = str(link)
        environment["HSCONFIG_TEST_LINK_TARGET"] = str(target)
        subprocess.run(
            (
                "pwsh",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                "New-Item -ItemType Junction "
                "-Path $env:HSCONFIG_TEST_LINK_PATH "
                "-Target $env:HSCONFIG_TEST_LINK_TARGET | Out-Null",
            ),
            check=True,
            env=environment,
        )
        return
    link.symlink_to(target, target_is_directory=True)


@pytest.mark.skipif(os.name != "nt", reason="Windows junction regression")
def test_runtime_source_inventory_rejects_nested_junction(
    tmp_path: Path,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    manifest = tmp_path / "bootstrap" / "runtime-manifest.json"
    source_root = manifest.parent / "committed-source"
    real_root = source_root / "real"
    payload = b"VALUE = 1\n"
    (real_root / "nested").mkdir(parents=True)
    (real_root / "nested" / "module.py").write_bytes(payload)
    _create_directory_redirect(source_root / "alias", real_root)
    digest = hashlib.sha256(payload).hexdigest()
    rows = [
        {"path": relative, "sha256": digest, "git_mode": "100644"}
        for relative in ("alias/nested/module.py", "real/nested/module.py")
    ]

    with pytest.raises(runner.RuntimeLockError, match="runtime bootstrap.*unsafe"):
        runner._validate_runtime_source_inventory(
            _runtime_source_inventory_document(rows),
            manifest,
        )


@pytest.mark.skipif(os.name != "nt", reason="Windows junction regression")
def test_runtime_overlay_rejects_nested_junction(tmp_path: Path) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    build_backend_root = tmp_path / "build-backend"
    real_root = build_backend_root / "real"
    payload = b"VALUE = 1\n"
    real_root.mkdir(parents=True)
    (real_root / "module.py").write_bytes(payload)
    _create_directory_redirect(build_backend_root / "alias", real_root)
    digest = hashlib.sha256(payload).hexdigest()
    artifacts = [
        {
            "install": False,
            "allowed_startup_surfaces": [],
            "files": [
                {"path": relative, "size": len(payload), "sha256": digest}
                for relative in ("real/module.py",)
            ],
        }
    ]

    with pytest.raises(runner.RuntimeLockError, match="overlay"):
        runner._validate_runtime_overlay(artifacts, build_backend_root)


def test_runtime_overlay_rejects_unmanifested_file(tmp_path: Path) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    build_backend_root = tmp_path / "build-backend"
    build_backend_root.mkdir()
    (build_backend_root / "unbound.py").write_text("VALUE = 1\n", encoding="utf-8")
    artifacts = [
        {
            "install": False,
            "allowed_startup_surfaces": [],
            "files": [],
        }
    ]

    with pytest.raises(runner.RuntimeLockError, match="overlay inventory differs"):
        runner._validate_runtime_overlay(artifacts, build_backend_root)


def test_runtime_git_mode_maps_posix_execute_bits(
    monkeypatch: MonkeyPatch,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    monkeypatch.setattr(runner.sys, "platform", "linux")

    assert runner._runtime_git_mode(stat.S_IFREG | 0o644) == "100644"
    assert runner._runtime_git_mode(stat.S_IFREG | 0o755) == "100755"


@pytest.mark.parametrize("mode", (0o666, 0o744, 0o700))
def test_runtime_git_mode_rejects_noncanonical_posix_modes(
    monkeypatch: MonkeyPatch,
    mode: int,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    monkeypatch.setattr(runner.sys, "platform", "linux")

    with pytest.raises(runner.RuntimeLockError, match="mode"):
        runner._runtime_git_mode(stat.S_IFREG | mode)


@pytest.mark.skipif(os.name == "nt", reason="POSIX executable mode regression")
def test_runtime_source_inventory_rejects_git_mode_mismatch(
    tmp_path: Path,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    manifest = tmp_path / "bootstrap" / "runtime-manifest.json"
    source_root = manifest.parent / "committed-source"
    source_root.mkdir(parents=True)
    payload = b"VALUE = 1\n"
    source_file = source_root / "module.py"
    source_file.write_bytes(payload)
    source_file.chmod(0o644)
    rows = [
        {
            "path": "module.py",
            "sha256": hashlib.sha256(payload).hexdigest(),
            "git_mode": "100755",
        }
    ]

    with pytest.raises(runner.RuntimeLockError, match="source inventory differs"):
        runner._validate_runtime_source_inventory(
            _runtime_source_inventory_document(rows),
            manifest,
        )


def test_current_bootstrap_manifest_is_consumed_by_runtime_lock_check(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    distribution, artifact, repository = _bound_local_distribution(
        tmp_path,
        monkeypatch,
        installed_payload=b"VALUE = 1\n",
    )
    (repository / "pyproject.toml").write_text(
        '[project]\nname = "hsconfig"\ndynamic = ["version"]\n',
        encoding="utf-8",
    )
    (repository / "src" / "hsconfig" / "version.py").write_text(
        '__version__ = "1.0.0"\n',
        encoding="utf-8",
    )
    subprocess.run(("git", "-C", str(repository), "add", "."), check=True)
    subprocess.run(
        ("git", "-C", str(repository), "commit", "-q", "-m", "runtime manifest"),
        check=True,
    )
    artifact["_commit_oid"] = subprocess.run(
        ("git", "-C", str(repository), "rev-parse", "HEAD"),
        check=True,
        capture_output=True,
        text=True,
        encoding="ascii",
    ).stdout.strip()
    artifact["_tree_oid"] = subprocess.run(
        ("git", "-C", str(repository), "rev-parse", "HEAD^{tree}"),
        check=True,
        capture_output=True,
        text=True,
        encoding="ascii",
    ).stdout.strip()
    lock = _write_local_runtime_manifest(tmp_path, monkeypatch, artifact, repository)
    distribution.metadata = {"Name": "hsconfig"}
    distribution.version = "1.0.0"
    monkeypatch.setattr(runner.importlib_metadata, "distributions", lambda: (distribution,))
    monkeypatch.setattr(runner, "_locked_versions", lambda lock_file: {})
    monkeypatch.setattr(runner, "_locked_wheels", lambda lock_file: {})
    monkeypatch.setattr(runner, "_assert_distribution_origin", lambda *args, **kwargs: set())
    monkeypatch.setattr(runner, "_assert_runtime_tree_closed", lambda *args: None)

    binding = runner._assert_runtime_matches_lock(lock)

    assert binding is not None
    assert binding.repository_root == repository.resolve(strict=True)
    manifest = json.loads(Path(os.environ["HSCONFIG_RUNTIME_MANIFEST"]).read_text())
    assert binding.commit_oid == manifest["commit_oid"]
    assert binding.tree_oid == manifest["tree_oid"]
    assert binding.root_identity == runner._identity(repository.lstat())
    assert binding.pythonpath == (
        Path(os.environ["HSCONFIG_RUNTIME_MANIFEST"]).parent / "committed-source",
        Path(os.environ["HSCONFIG_RUNTIME_MANIFEST"]).parent / "build-backend",
    )
    with runner.isolated_coverage_environment(binding) as run:
        assert run.environment["PYTHONPATH"].split(os.pathsep) == [
            str(path) for path in binding.pythonpath
        ]
        repository_binding = json.loads(
            run.environment["HSCONFIG_COVERAGE_TEST_REPOSITORY_BINDING"]
        )
        assert repository_binding["repository"] == str(repository.resolve(strict=True))
        assert repository_binding["commit_oid"] == binding.commit_oid
        assert repository_binding["tree_oid"] == binding.tree_oid
        assert "HSCONFIG_RELEASE_GATE_BOOTSTRAP_SENTINEL" not in run.environment
        assert "HSCONFIG_RUNTIME_MANIFEST" not in run.environment
        assert "HSCONFIG_RUNTIME_MANIFEST_SHA256" not in run.environment


def test_runtime_manifest_digest_failure_is_categorized_as_manifest_binding(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    _distribution, artifact, repository = _bound_local_distribution(
        tmp_path,
        monkeypatch,
        installed_payload=b"VALUE = 1\n",
    )
    lock = _write_local_runtime_manifest(tmp_path, monkeypatch, artifact, repository)
    monkeypatch.setenv("HSCONFIG_RUNTIME_MANIFEST_SHA256", "0" * 64)

    with pytest.raises(runner.RuntimeLockError, match="manifest digest") as caught:
        runner._load_runtime_manifest(lock, {})

    assert caught.value.category is runner.RuntimeLockCategory.MANIFEST_BINDING


def test_runtime_manifest_wheel_failure_is_categorized_as_artifact_binding(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    _distribution, artifact, repository = _bound_local_distribution(
        tmp_path,
        monkeypatch,
        installed_payload=b"VALUE = 1\n",
    )
    lock = _write_local_runtime_manifest(tmp_path, monkeypatch, artifact, repository)
    Path(str(artifact["wheel_path"])).write_bytes(b"tampered wheel payload")

    with pytest.raises(runner.RuntimeLockError, match="wheel inventory") as caught:
        runner._load_runtime_manifest(lock, {})

    assert caught.value.category is runner.RuntimeLockCategory.ARTIFACT_BINDING


def _commit_repository_path(
    repository: Path,
    artifact: dict[str, object],
    relative: str,
) -> None:
    path = repository / Path(*relative.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("tracked authority\n", encoding="utf-8")
    subprocess.run(("git", "-C", str(repository), "add", relative), check=True)
    subprocess.run(
        ("git", "-C", str(repository), "commit", "-q", "-m", "add authority"),
        check=True,
    )
    artifact["_commit_oid"] = subprocess.run(
        ("git", "-C", str(repository), "rev-parse", "HEAD"),
        check=True,
        capture_output=True,
        text=True,
        encoding="ascii",
    ).stdout.strip()
    artifact["_tree_oid"] = subprocess.run(
        ("git", "-C", str(repository), "rev-parse", "HEAD^{tree}"),
        check=True,
        capture_output=True,
        text=True,
        encoding="ascii",
    ).stdout.strip()


def _set_index_flag(repository: Path, relative: str, flag: str) -> None:
    subprocess.run(
        ("git", "-C", str(repository), "update-index", f"--{flag}", relative),
        check=True,
    )


def test_local_distribution_accepts_only_bound_git_eol_materialization(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    distribution, artifact, _repository = _bound_local_distribution(
        tmp_path,
        monkeypatch,
    )

    runner._assert_distribution_origin(
        distribution,
        local_project=True,
        artifact=artifact,
    )


def test_materialized_git_payload_accepts_only_exact_crlf_normalization() -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    matcher = getattr(runner, "_matches_materialized_git_payload", None)
    committed = b"FIRST = 1\nSECOND = 2\nTHIRD = 3\n"
    materialized = b"FIRST = 1\r\nSECOND = 2\nTHIRD = 3\r\n"

    assert matcher is not None
    assert matcher(materialized, committed, "hsconfig/module.py") is True
    assert (
        runner._matches_committed_local_payload(
            materialized,
            committed,
            "hsconfig/module.py",
        )
        is False
    )


@pytest.mark.parametrize(
    "materialized",
    (
        b"FIRST = 1\r\nSECOND = 9\n",
        b"FIRST = 1\rSECOND = 2\n",
        b"FIRST = 1\r\nSECOND = 2\x00\n",
        b"FIRST = 1\r\nSECOND = \xff\n",
    ),
    ids=("content-drift", "bare-cr", "nul", "invalid-utf8"),
)
def test_materialized_git_payload_rejects_noncanonical_content(
    materialized: bytes,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    matcher = getattr(runner, "_matches_materialized_git_payload", None)

    assert matcher is not None
    assert (
        matcher(
            materialized,
            b"FIRST = 1\nSECOND = 2\n",
            "hsconfig/module.py",
        )
        is False
    )


def test_runtime_manifest_git_authority_uses_bound_transport(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    _distribution, artifact, repository = _bound_local_distribution(
        tmp_path,
        monkeypatch,
        installed_payload=b"VALUE = 1\n",
    )
    lock = _write_local_runtime_manifest(tmp_path, monkeypatch, artifact, repository)
    original_bound_git_output = runner._bound_git_output
    calls: list[tuple[str, ...]] = []

    def record_bound_git_output(
        *arguments: str,
        maximum_bytes: int,
        repository: Path | None = None,
    ) -> bytes:
        calls.append(arguments)
        return original_bound_git_output(
            *arguments,
            maximum_bytes=maximum_bytes,
            repository=repository,
        )

    def reject_legacy_git_run(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise AssertionError("legacy subprocess.run Git authority was used")

    monkeypatch.setattr(runner, "_bound_git_output", record_bound_git_output)
    monkeypatch.setattr(runner.subprocess, "run", reject_legacy_git_run)

    assert runner._load_runtime_manifest(lock, {}) is not None
    assert ("rev-parse", "HEAD") in calls
    assert ("rev-parse", "HEAD^{tree}") in calls
    assert (
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
    ) in calls
    assert ("ls-files", "-v", "-z", "--full-name") in calls


@pytest.mark.parametrize(
    ("case", "expected_reason"),
    tuple((reason, reason) for reason in _RUNTIME_REPOSITORY_BINDING_REASONS),
)
def test_runtime_manifest_repository_binding_emits_exact_closed_reason(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    case: str,
    expected_reason: str,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    _distribution, artifact, repository = _bound_local_distribution(
        tmp_path,
        monkeypatch,
        installed_payload=b"VALUE = 1\n",
    )
    lock = _write_local_runtime_manifest(tmp_path, monkeypatch, artifact, repository)
    private_detail = "C:" + "/" + "/".join(
        ("private", "repository", "secret-oid-and-path")
    )
    original_bound_git_oid = runner._bound_git_oid
    original_bound_git_output = runner._bound_git_output
    original_assert_default_git_index = runner._assert_default_git_index
    original_lstat = Path.lstat
    repository_key = os.path.normcase(os.fspath(repository))
    repository_lstat_calls = 0

    def controlled_bound_git_oid(
        revision: str,
        *,
        repository: Path | None = None,
    ) -> str:
        if case == "git_head_unavailable" and revision == "HEAD":
            raise runner.CoverageGateError(private_detail)
        if case == "git_tree_unavailable" and revision == "HEAD^{tree}":
            raise runner.CoverageGateError(private_detail)
        if case == "commit_changed" and revision == "HEAD":
            return "0" * 40
        if case == "tree_changed" and revision == "HEAD^{tree}":
            return "0" * 40
        return original_bound_git_oid(revision, repository=repository)

    def controlled_bound_git_output(
        *arguments: str,
        maximum_bytes: int,
        repository: Path | None = None,
    ) -> bytes:
        if arguments[:1] == ("status",):
            if case == "git_status_unavailable":
                raise OSError(private_detail)
            if case == "dirty_status":
                return b"?? private-secret-path\n"
        return original_bound_git_output(
            *arguments,
            maximum_bytes=maximum_bytes,
            repository=repository,
        )

    def controlled_assert_default_git_index(
        *,
        repository: Path | None = None,
    ) -> None:
        if case == "git_index_unavailable":
            raise runner.RuntimeLockError(private_detail)
        original_assert_default_git_index(repository=repository)

    def controlled_lstat(path: Path, *args: object, **kwargs: object) -> object:
        nonlocal repository_lstat_calls
        metadata = original_lstat(path, *args, **kwargs)
        if os.path.normcase(os.fspath(path)) != repository_key:
            return metadata
        repository_lstat_calls += 1
        if repository_lstat_calls != 2:
            return metadata
        if case == "repository_lstat_unavailable":
            raise OSError(private_detail)
        changed_field = {
            "root_device_changed": "st_dev",
            "root_inode_changed": "st_ino",
            "root_size_changed": "st_size",
            "root_mtime_changed": "st_mtime_ns",
            "root_ctime_changed": "st_ctime_ns",
            "root_mode_changed": "st_mode",
        }.get(case)
        if changed_field is None:
            return metadata
        values = {
            "st_dev": metadata.st_dev,
            "st_ino": metadata.st_ino,
            "st_size": metadata.st_size,
            "st_mtime_ns": metadata.st_mtime_ns,
            "st_ctime_ns": metadata.st_ctime_ns,
            "st_mode": metadata.st_mode,
        }
        values[changed_field] += 1
        return SimpleNamespace(**values)

    monkeypatch.setattr(runner, "_bound_git_oid", controlled_bound_git_oid)
    monkeypatch.setattr(runner, "_bound_git_output", controlled_bound_git_output)
    monkeypatch.setattr(
        runner,
        "_assert_default_git_index",
        controlled_assert_default_git_index,
    )
    monkeypatch.setattr(Path, "lstat", controlled_lstat)

    with pytest.raises(runner.RuntimeLockError) as caught:
        runner._load_runtime_manifest(lock, {})

    assert caught.value.category is runner.RuntimeLockCategory.REPOSITORY_BINDING
    assert caught.value.reason.value == expected_reason
    assert private_detail not in str(caught.value)


def test_committed_source_runner_uses_manifest_bound_git_repository(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """Break caught: a committed-source runner treats its Git-free root as the repo."""
    runner = importlib.import_module("scripts.run_coverage_gate")
    distribution, artifact, repository = _bound_local_distribution(
        tmp_path,
        monkeypatch,
        installed_payload=b"VALUE = 1\n",
    )
    lock = _write_local_runtime_manifest(tmp_path, monkeypatch, artifact, repository)
    manifest = Path(os.environ["HSCONFIG_RUNTIME_MANIFEST"])
    committed_source = manifest.parent / "committed-source"
    monkeypatch.setattr(runner, "ROOT", committed_source)

    bound = runner._load_runtime_manifest(lock, {})

    assert bound is not None
    runner._assert_distribution_origin(
        distribution,
        local_project=True,
        artifact=bound["hsconfig"],
    )


@pytest.mark.parametrize("flag", ("assume-unchanged", "skip-worktree"))
def test_runtime_manifest_rejects_nondefault_index_flags_outside_source(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    flag: str,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    _distribution, artifact, repository = _bound_local_distribution(
        tmp_path,
        monkeypatch,
        installed_payload=b"VALUE = 1\n",
    )
    relative = "docs/runtime-authority.txt"
    _commit_repository_path(repository, artifact, relative)
    lock = _write_local_runtime_manifest(tmp_path, monkeypatch, artifact, repository)
    _set_index_flag(repository, relative, flag)

    with pytest.raises(runner.RuntimeLockError, match="repository|index") as caught:
        runner._load_runtime_manifest(lock, {})
    assert caught.value.category is runner.RuntimeLockCategory.REPOSITORY_BINDING


@pytest.mark.parametrize("flag", ("assume-unchanged", "skip-worktree"))
def test_local_distribution_rejects_modified_flagged_materialized_source(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    flag: str,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    distribution, artifact, repository = _bound_local_distribution(
        tmp_path,
        monkeypatch,
        committed_payload=b"VALUE = 1\n",
        installed_payload=b"VALUE = 1\n",
    )
    relative = "src/hsconfig/module.py"
    _set_index_flag(repository, relative, flag)
    (repository / relative).write_bytes(b"VALUE = 2\n")
    assert (
        subprocess.run(
            (
                "git",
                "-C",
                str(repository),
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
            ),
            check=True,
            capture_output=True,
        ).stdout
        == b""
    )

    with pytest.raises(runner.RuntimeLockError, match="local project|repository|index"):
        runner._assert_distribution_origin(
            distribution,
            local_project=True,
            artifact=artifact,
        )


@pytest.mark.parametrize("flag", ("assume-unchanged", "skip-worktree"))
def test_terminal_repository_binding_rejects_nondefault_index_flags_outside_source(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    flag: str,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    _distribution, artifact, repository = _bound_local_distribution(
        tmp_path,
        monkeypatch,
        installed_payload=b"VALUE = 1\n",
    )
    relative = "tests/runtime-authority.txt"
    _commit_repository_path(repository, artifact, relative)
    _set_index_flag(repository, relative, flag)

    with pytest.raises(runner.RuntimeLockError, match="repository|index"):
        runner._assert_local_repository_binding(artifact)


@pytest.mark.parametrize(
    "case",
    (
        "content-change",
        "mixed-line-endings",
        "missing-commit-binding",
        "missing-blob",
        "repository-drift",
    ),
)
def test_local_distribution_rejects_unbound_committed_source(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    case: str,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    committed = b"FIRST = 1\nSECOND = 2\n"
    installed = {
        "content-change": b"FIRST = 1\r\nSECOND = 3\r\n",
        "mixed-line-endings": b"FIRST = 1\r\nSECOND = 2\n",
    }.get(case, committed)
    distribution, artifact, repository = _bound_local_distribution(
        tmp_path,
        monkeypatch,
        committed_payload=committed,
        installed_payload=installed,
    )
    if case == "missing-commit-binding":
        del artifact["_commit_oid"]
    elif case == "missing-blob":
        artifact["_commit_oid"] = "0" * 40
    elif case == "repository-drift":
        (repository / "untracked.txt").write_text("drift\n", encoding="utf-8")

    with pytest.raises(runner.RuntimeLockError, match="local project|repository"):
        runner._assert_distribution_origin(
            distribution,
            local_project=True,
            artifact=artifact,
        )


@pytest.mark.parametrize(
    "case",
    (
        "path-mismatch",
        "missing-installed-path",
        "extra-committed-path",
        "tree-drift",
        "wheel-source-tamper",
        "wheel-inventory-tamper",
    ),
)
def test_local_distribution_rejects_path_or_artifact_authority_drift(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    case: str,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    distribution, artifact, _repository = _bound_local_distribution(
        tmp_path,
        monkeypatch,
        committed_payload=b"VALUE = 1\n",
        installed_payload=b"VALUE = 1\n",
        installed_relative=(
            "hsconfig/other.py" if case == "path-mismatch" else "hsconfig/module.py"
        ),
        include_installed_package=case != "missing-installed-path",
        include_extra_committed_path=case == "extra-committed-path",
    )
    if case == "tree-drift":
        artifact["_tree_oid"] = "0" * 40
    elif case == "wheel-source-tamper":
        artifact["_wheel_source"] = b"not a bound wheel"
    elif case == "wheel-inventory-tamper":
        artifact["files"] = []

    with pytest.raises(runner.RuntimeLockError, match="local project|repository|wheel"):
        runner._assert_distribution_origin(
            distribution,
            local_project=True,
            artifact=artifact,
        )


def test_local_distribution_rejects_git_replace_object_authority(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    original = b"VALUE = 'original'\n"
    replacement = b"VALUE = 'replacement'\n"
    distribution, artifact, repository = _bound_local_distribution(
        tmp_path,
        monkeypatch,
        committed_payload=original,
        installed_payload=replacement,
    )
    original_oid = subprocess.run(
        (
            "git",
            "-C",
            str(repository),
            "rev-parse",
            "HEAD:src/hsconfig/module.py",
        ),
        check=True,
        capture_output=True,
        text=True,
        encoding="ascii",
    ).stdout.strip()
    replacement_oid = subprocess.run(
        ("git", "-C", str(repository), "hash-object", "-w", "--stdin"),
        input=replacement,
        check=True,
        capture_output=True,
    ).stdout.decode("ascii").strip()
    subprocess.run(
        ("git", "-C", str(repository), "replace", original_oid, replacement_oid),
        check=True,
    )

    with pytest.raises(runner.RuntimeLockError, match="local project|repository"):
        runner._assert_distribution_origin(
            distribution,
            local_project=True,
            artifact=artifact,
        )


def test_bound_git_output_rejects_limit_plus_one_without_full_capture(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    _distribution, _artifact, repository = _bound_local_distribution(
        tmp_path,
        monkeypatch,
        installed_payload=b"VALUE = 1\n",
    )
    payload = b"x" * 65
    blob_oid = subprocess.run(
        ("git", "-C", str(repository), "hash-object", "-w", "--stdin"),
        input=payload,
        check=True,
        capture_output=True,
    ).stdout.decode("ascii").strip()

    with pytest.raises(runner.RuntimeLockError, match="repository binding"):
        runner._bound_git_output(
            "cat-file",
            "blob",
            blob_oid,
            maximum_bytes=64,
        )


def test_bound_git_oid_retries_one_transient_transport_failure(
    monkeypatch: MonkeyPatch,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    expected = b"a" * 40 + b"\n"
    repository = Path("bound-repository")
    calls: list[tuple[tuple[str, ...], int, Path | None]] = []

    def transient_transport(
        *arguments: str,
        maximum_bytes: int,
        repository: Path | None = None,
    ) -> bytes:
        calls.append((arguments, maximum_bytes, repository))
        if len(calls) == 1:
            raise runner.RuntimeLockError(
                "local project repository binding is unavailable"
            )
        return expected

    monkeypatch.setattr(runner, "_bound_git_output", transient_transport)

    assert runner._bound_git_oid("HEAD", repository=repository) == "a" * 40
    assert calls == [(("rev-parse", "HEAD"), 64, repository)] * 2


def test_bound_git_oid_fails_after_two_transport_failures(
    monkeypatch: MonkeyPatch,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    calls = 0

    def unavailable_transport(
        *arguments: str,
        maximum_bytes: int,
        repository: Path | None = None,
    ) -> bytes:
        nonlocal calls
        del arguments, maximum_bytes, repository
        calls += 1
        raise runner.RuntimeLockError(
            "local project repository binding is unavailable"
        )

    monkeypatch.setattr(runner, "_bound_git_output", unavailable_transport)

    with pytest.raises(runner.RuntimeLockError, match="repository binding"):
        runner._bound_git_oid("HEAD")
    assert calls == 2


def test_bound_git_oid_does_not_retry_successful_transport(
    monkeypatch: MonkeyPatch,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    calls = 0

    def successful_transport(*args: object, **kwargs: object) -> bytes:
        nonlocal calls
        del args, kwargs
        calls += 1
        return b"b" * 40 + b"\n"

    monkeypatch.setattr(runner, "_bound_git_output", successful_transport)

    assert runner._bound_git_oid("HEAD") == "b" * 40
    assert calls == 1


def test_bound_git_oid_does_not_retry_invalid_identity(
    monkeypatch: MonkeyPatch,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    calls = 0

    def invalid_transport(*args: object, **kwargs: object) -> bytes:
        nonlocal calls
        del args, kwargs
        calls += 1
        return b"not-an-object-id\n"

    monkeypatch.setattr(runner, "_bound_git_output", invalid_transport)

    with pytest.raises(runner.RuntimeLockError, match="identity is invalid"):
        runner._bound_git_oid("HEAD")
    assert calls == 1


def test_local_distribution_rejects_swapped_bound_wheel_on_disk(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    distribution, artifact, _repository = _bound_local_distribution(
        tmp_path,
        monkeypatch,
        installed_payload=b"VALUE = 1\n",
    )
    Path(str(artifact["wheel_path"])).write_bytes(b"swapped wheel")

    with pytest.raises(runner.RuntimeLockError, match="wheel|artifact"):
        runner._assert_distribution_origin(
            distribution,
            local_project=True,
            artifact=artifact,
        )


@pytest.mark.parametrize("case", ("disk-mismatch", "metadata-to-record-toctou"))
def test_local_distribution_rejects_unbound_direct_url_bytes(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    case: str,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    distribution, artifact, _repository = _bound_local_distribution(
        tmp_path,
        monkeypatch,
        installed_payload=b"VALUE = 1\n",
    )
    direct_url = str(getattr(distribution, "current_direct_url"))
    reserialized = json.dumps(json.loads(direct_url), indent=2)
    _set_local_direct_url_payload(
        distribution,
        reserialized,
        write_payload=case == "disk-mismatch",
    )
    if case == "metadata-to-record-toctou":
        direct_path = Path(getattr(distribution, "dist_info")) / "direct_url.json"
        distribution.on_direct_url_read = lambda: direct_path.write_bytes(
            reserialized.encode("utf-8")
        )

    with pytest.raises(runner.RuntimeLockError, match="origin|artifact"):
        runner._assert_distribution_origin(
            distribution,
            local_project=True,
            artifact=artifact,
        )


def test_local_distribution_rejects_hardlinked_materialized_source(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    distribution, artifact, repository = _bound_local_distribution(
        tmp_path,
        monkeypatch,
        installed_payload=b"VALUE = 1\n",
    )
    source = repository / "src" / "hsconfig" / "module.py"
    external = tmp_path / "external-source.py"
    external.write_bytes(source.read_bytes())
    source.unlink()
    os.link(external, source)

    with pytest.raises(runner.RuntimeLockError, match="local project|repository"):
        runner._assert_distribution_origin(
            distribution,
            local_project=True,
            artifact=artifact,
        )


def test_local_distribution_rejects_linked_materialized_source_parent(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    distribution, artifact, repository = _bound_local_distribution(
        tmp_path,
        monkeypatch,
        installed_payload=b"VALUE = 1\n",
    )
    source_parent = repository / "src" / "hsconfig"
    backing = tmp_path / "source-backing"
    source_parent.replace(backing)
    try:
        source_parent.symlink_to(backing, target_is_directory=True)
    except OSError as exc:
        backing.replace(source_parent)
        pytest.skip(f"directory symlinks unavailable: {exc}")

    with pytest.raises(runner.RuntimeLockError, match="local project|repository"):
        runner._assert_distribution_origin(
            distribution,
            local_project=True,
            artifact=artifact,
        )


def test_local_distribution_rejects_missing_skip_worktree_source(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    distribution, artifact, repository = _bound_local_distribution(
        tmp_path,
        monkeypatch,
        installed_payload=b"VALUE = 1\n",
    )
    relative = "src/hsconfig/module.py"
    subprocess.run(
        ("git", "-C", str(repository), "update-index", "--skip-worktree", relative),
        check=True,
    )
    (repository / relative).unlink()
    assert (
        subprocess.run(
            (
                "git",
                "-C",
                str(repository),
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
            ),
            check=True,
            capture_output=True,
        ).stdout
        == b""
    )

    with pytest.raises(runner.RuntimeLockError, match="local project|repository"):
        runner._assert_distribution_origin(
            distribution,
            local_project=True,
            artifact=artifact,
        )


@pytest.mark.parametrize(
    "tree_output",
    (
        b"120000 blob " + b"1" * 40 + b"\tsrc/hsconfig/link.py\0",
        b"040000 tree " + b"1" * 40 + b"\tsrc/hsconfig/nested\0",
        b"100644 blob invalid\tsrc/hsconfig/module.py\0",
        b"100644 blob " + b"1" * 40 + b"\tsrc/hsconfig/../evil.py\0",
        b"100644 blob " + b"1" * 40 + b"\tforeign/module.py\0",
        b"100644 blob " + b"1" * 40 + b"\tsrc/hsconfig/trailing./module.py\0",
        b"100644 blob " + b"1" * 40 + b"\tsrc/hsconfig/trailing /module.py\0",
        b"100644 blob " + b"1" * 40 + b"\tsrc/hsconfig/stream:name.py\0",
        b"100644 blob " + b"1" * 40 + b"\tsrc/hsconfig/control\x01.py\0",
        b"100644 blob " + b"1" * 40 + b"\tsrc/hsconfig/CON.py\0",
        b"100644 blob " + b"1" * 40 + b"\tsrc/hsconfig/Lpt9.json\0",
        b"100644 blob " + b"1" * 40 + "\tsrc/hsconfig/CoM¹.Py\0".encode(),
        b"100644 blob " + b"1" * 40 + "\tsrc/hsconfig/cOm².json\0".encode(),
        b"100644 blob " + b"1" * 40 + "\tsrc/hsconfig/COM³.txt\0".encode(),
        b"100644 blob " + b"1" * 40 + "\tsrc/hsconfig/LpT¹.Py\0".encode(),
        b"100644 blob " + b"1" * 40 + "\tsrc/hsconfig/lPt².json\0".encode(),
        b"100644 blob " + b"1" * 40 + "\tsrc/hsconfig/LPT³.txt\0".encode(),
        (
            b"100644 blob "
            + b"1" * 40
            + b"\tsrc/hsconfig/Module.py\0"
            + b"100644 blob "
            + b"2" * 40
            + b"\tsrc/hsconfig/module.py\0"
        ),
        b"100644 blob " + b"1" * 40 + b"\tsrc/hsconfig/module.py",
    ),
)
def test_committed_local_tree_rejects_unclosed_git_inventory(
    monkeypatch: MonkeyPatch,
    tree_output: bytes,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    monkeypatch.setattr(runner, "_bound_git_output", lambda *args, **kwargs: tree_output)
    artifact = {
        "_commit_oid": "a" * 40,
        "_tree_oid": "b" * 40,
        "_repository_root": runner.ROOT.resolve(strict=True),
    }

    with pytest.raises(runner.RuntimeLockError, match="committed tree"):
        runner._committed_local_tree(artifact)


@pytest.mark.parametrize(
    "repository_path",
    (
        "src/hsconfig/CoM¹.Py",
        "src/hsconfig/cOm².json",
        "src/hsconfig/COM³.txt",
        "docs/LpT¹.Py",
        "tests/lPt².json",
        "scripts/LPT³.txt",
    ),
)
def test_default_git_index_rejects_superscript_windows_device_stems(
    monkeypatch: MonkeyPatch,
    repository_path: str,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    source = f"H {repository_path}\0".encode()
    monkeypatch.setattr(runner, "_bound_git_output", lambda *args, **kwargs: source)

    with pytest.raises(runner.RuntimeLockError, match="repository index"):
        runner._assert_default_git_index()


@pytest.mark.parametrize(
    "case",
    (
        "missing-artifact",
        "wrong-hash",
        "wrong-url",
        "extra-key",
        "missing-key",
        "duplicate-key",
        "invalid-json",
        "outside-artifact",
        "unbound-artifact",
    ),
)
def test_distribution_origin_rejects_unbound_or_malformed_direct_url(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    case: str,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    distribution, artifact, direct_url = _bound_nonlocal_distribution(
        tmp_path,
        monkeypatch,
    )
    document = json.loads(direct_url)
    selected: dict[str, object] | None = artifact
    if case == "missing-artifact":
        selected = None
    elif case == "wrong-hash":
        document["archive_info"]["hash"] = "sha256=" + "0" * 64
    elif case == "wrong-url":
        document["url"] = "https://example.invalid/pip.whl"
    elif case == "extra-key":
        document["extra"] = True
    elif case == "missing-key":
        del document["archive_info"]["hashes"]
    elif case == "duplicate-key":
        distribution.current_direct_url = direct_url[:-1] + f',"url":{json.dumps(document["url"])}}}'
    elif case == "invalid-json":
        distribution.current_direct_url = "{"
    elif case == "outside-artifact":
        outside = tmp_path / "outside.whl"
        outside.write_bytes(artifact["_wheel_source"])
        selected = dict(artifact)
        selected["wheel_path"] = str(outside)
        document["url"] = outside.as_uri()
    elif case == "unbound-artifact":
        selected = dict(artifact)
        del selected["_wheel_source"]
    if case not in {"duplicate-key", "invalid-json"}:
        distribution.current_direct_url = json.dumps(document, separators=(",", ":"))

    with pytest.raises(runner.RuntimeLockError, match="origin"):
        runner._assert_distribution_origin(
            distribution,
            local_project=False,
            artifact=selected,
        )


def test_bound_nonlocal_direct_url_accepts_installed_locked_dependency(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    bootstrap = tmp_path / "bootstrap"
    environment = bootstrap / "environment"
    environment.mkdir(parents=True)
    wheel_path = bootstrap / "dependency-wheels" / "boolean_py-5.0-py3-none-any.whl"
    wheel_path.parent.mkdir()
    with zipfile.ZipFile(wheel_path, "w") as archive:
        archive.writestr("boolean.py", b"VALUE = True\n")
        archive.writestr("boolean_py-5.0.dist-info/WHEEL", b"Wheel-Version: 1.0\n")
        archive.writestr("boolean_py-5.0.dist-info/RECORD", b"")
    wheel_source = wheel_path.read_bytes()
    digest = hashlib.sha256(wheel_source).hexdigest()
    direct_url = json.dumps(
        {
            "archive_info": {
                "hash": f"sha256={digest}",
                "hashes": {"sha256": digest},
            },
            "url": wheel_path.resolve(strict=True).as_uri(),
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    artifact: dict[str, object] = {
        "name": "boolean-py",
        "version": "5.0",
        "url": "https://example.invalid/boolean_py.whl",
        "wheel_path": str(wheel_path),
        "sha256": digest,
        "install": True,
        "allowed_startup_surfaces": [],
        "files": runner._wheel_inventory(wheel_source),
        "_wheel_source": wheel_source,
    }
    monkeypatch.setattr(runner.sys, "prefix", str(environment))

    assert runner._assert_bound_nonlocal_direct_url(direct_url, artifact) == (
        "boolean_py-5.0.dist-info/direct_url.json",
        direct_url.encode("utf-8"),
    )


def test_runtime_lock_detects_replacement_during_read(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    lock = tmp_path / "pylock.toml"
    lock.write_text(_lock_text("pytest"), encoding="utf-8")
    original_read = runner.os.read
    swapped = False

    def replacing_read(descriptor: int, size: int) -> bytes:
        nonlocal swapped
        if not swapped:
            swapped = True
            original = tmp_path / "original.toml"
            lock.rename(original)
            lock.write_text(_lock_text("pytest", "2.0"), encoding="utf-8")
            lock.unlink()
            original.rename(lock)
        return original_read(descriptor, size)

    monkeypatch.setattr(runner.os, "read", replacing_read)

    with pytest.raises(runner.RuntimeLockError, match="project lock"):
        runner._locked_versions(lock)


def test_coverage_run_uses_unique_external_paths_and_isolates_plugins() -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")

    with runner.isolated_coverage_environment() as first:
        with runner.isolated_coverage_environment() as second:
            assert first.run_root != second.run_root
            assert first.coverage_data == first.run_root / ".coverage"
            assert first.coverage_json == first.run_root / "coverage.json"
            assert second.coverage_data == second.run_root / ".coverage"
            assert second.coverage_json == second.run_root / "coverage.json"
            assert ROOT not in first.run_root.parents
            assert ROOT not in second.run_root.parents
            assert first.environment["PYTHONNOUSERSITE"] == "1"
            assert first.environment["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] == "1"
            assert first.environment["PYTEST_PLUGINS"] == (
                "pytest_cov.plugin,_hypothesis_pytestplugin"
            )
        assert not second.run_root.exists()
    assert not first.run_root.exists()


def test_windows_pytest_temp_uses_short_runner_root_and_cleans(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    runner_temp = tmp_path / "rt"
    fallback_temp = tmp_path / "fallback"
    runner_temp.mkdir()
    fallback_temp.mkdir()
    monkeypatch.setenv("RUNNER_TEMP", str(runner_temp))
    monkeypatch.setattr(runner.tempfile, "gettempdir", lambda: str(fallback_temp))

    assert hasattr(runner, "_windows_host")
    monkeypatch.setattr(runner, "_windows_host", lambda: True)
    monkeypatch.setattr(
        runner,
        "_windows_pytest_path_within_budget",
        lambda parent: parent == runner_temp.resolve(strict=True),
    )
    pytest_temp: Path | None = None
    run_root: Path | None = None
    with runner.isolated_coverage_environment() as run:
        pytest_temp = Path(run.environment["PYTEST_DEBUG_TEMPROOT"])
        run_root = run.run_root
        projected_fixture = (
            PureWindowsPath("D:" + chr(92), "a", "_temp")
            / f"{runner.PYTEST_TEMP_PREFIX}{'a' * 16}"
            / "pytest-of-runner"
            / "pytest-123"
            / "test_committed_source_install_e0"
            / "checkout"
            / "runner-temp"
            / "hsconfig-runtime-3.11"
            / "Lib"
            / "site-packages"
            / "hsconfig"
            / "resources"
            / "runtime-contract.json"
        )

        assert pytest_temp.parent == runner_temp.resolve(strict=True)
        assert pytest_temp.parent != run.run_root
        assert run.run_root not in pytest_temp.parents
        assert len(str(projected_fixture)) <= runner.MAX_WINDOWS_PYTEST_PATH
        assert pytest_temp.is_dir()

    assert pytest_temp is not None and not pytest_temp.exists()
    assert run_root is not None and not run_root.exists()


def test_windows_pytest_temp_falls_back_from_unsafe_runner_root(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    fallback_temp = tmp_path / "fallback"
    fallback_temp.mkdir()
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path / "missing-runner-temp"))
    monkeypatch.setattr(runner.tempfile, "gettempdir", lambda: str(fallback_temp))
    monkeypatch.setattr(runner, "_windows_host", lambda: True)
    monkeypatch.setattr(
        runner,
        "_windows_pytest_path_within_budget",
        lambda parent: parent == fallback_temp.resolve(strict=True),
    )

    with runner.isolated_coverage_environment() as run:
        pytest_temp = run.pytest_temp_root
        assert pytest_temp.parent == fallback_temp.resolve(strict=True)
        assert pytest_temp.is_dir()

    assert not pytest_temp.exists()


def test_windows_pytest_temp_rejects_checkout_and_long_runner_roots(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    checkout_child = checkout / "runner-temp"
    checkout_child.mkdir()
    fallback = tmp_path / "fallback"
    fallback.mkdir()
    long_runner = tmp_path
    for index in range(12):
        long_runner = long_runner / (f"long-runner-{index}-" + ("x" * 12))
    long_runner.mkdir(parents=True)
    monkeypatch.setattr(runner, "_windows_host", lambda: True)
    monkeypatch.setattr(
        runner,
        "_windows_pytest_path_within_budget",
        lambda parent: parent == fallback.resolve(strict=True),
    )

    for unsafe in (checkout, checkout_child, long_runner):
        monkeypatch.setenv("RUNNER_TEMP", str(unsafe))
        selected = runner._pytest_temporary_parent(
            fallback.resolve(strict=True),
            forbidden_roots=(checkout.resolve(strict=True),),
        )
        assert selected == fallback.resolve(strict=True)


def test_windows_pytest_path_budget_uses_selected_runtime_parent() -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")

    short_parent = PureWindowsPath("D:" + chr(92), "a", "_temp")
    long_parent = PureWindowsPath("D:" + chr(92)) / (
        "long-runner-root-" + ("x" * 220)
    )

    assert runner._windows_pytest_path_within_budget(short_parent) is True
    assert (
        runner._windows_pytest_path_within_budget(long_parent)
        is False
    )


def test_created_temp_root_never_owns_resolved_external_target(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    parent = tmp_path / "parent"
    parent.mkdir()
    external = tmp_path / "external"
    external.mkdir()
    marker = external / "marker.txt"
    marker.write_text("external authority", encoding="utf-8")
    real_resolve = Path.resolve

    def swapped_resolve(path: Path, *args: object, **kwargs: object) -> Path:
        if path.parent == parent and path.name.startswith("race-"):
            return external.resolve(strict=True)
        return real_resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", swapped_resolve)

    with pytest.raises(runner.CoverageGateError, match="escaped"):
        runner._create_owned_directory(
            parent.resolve(strict=True),
            prefix="race-",
            label="race probe",
        )

    assert marker.read_text(encoding="utf-8") == "external authority"
    assert list(parent.iterdir()) == []


def test_created_temp_root_never_claims_replacement_after_initial_lstat_failure(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    parent = tmp_path / "parent"
    parent.mkdir()
    real_lstat = Path.lstat
    failed = False
    original: Path | None = None
    replacement: Path | None = None

    def transient_lstat(path: Path, *args: object, **kwargs: object) -> os.stat_result:
        nonlocal failed, original, replacement
        if path.parent == parent and path.name.startswith("lstat-") and not failed:
            failed = True
            original = parent / "original-owned-directory"
            path.rename(original)
            path.mkdir()
            replacement = path
            (path / "external-marker.txt").write_text(
                "external authority",
                encoding="utf-8",
            )
            raise OSError("lstat-probe")
        return real_lstat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", transient_lstat)

    with pytest.raises(OSError, match="lstat-probe"):
        runner._create_owned_directory(
            parent.resolve(strict=True),
            prefix="lstat-",
            label="lstat probe",
        )

    assert failed is True
    assert original is not None and original.is_dir()
    assert replacement is not None
    assert (replacement / "external-marker.txt").read_text(encoding="utf-8") == (
        "external authority"
    )
    shutil.rmtree(original)
    shutil.rmtree(replacement)
    assert list(parent.iterdir()) == []


def test_coverage_cleanup_keeps_body_exception_primary(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    monkeypatch.setattr(runner.tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(runner, "_windows_host", lambda: False)

    def failing_cleanup(*args: object, **kwargs: object) -> None:
        raise runner.CoverageGateError("cleanup-probe")

    monkeypatch.setattr(runner, "_cleanup_owned_run_root", failing_cleanup)

    with pytest.raises(ValueError, match="body-probe") as raised:
        with runner.isolated_coverage_environment():
            raise ValueError("body-probe")

    notes = getattr(raised.value, "__notes__", [])
    assert len(notes) == 2
    assert all("cleanup-probe" in note for note in notes)


def test_pytest_temp_cleanup_preserves_replacement_and_removes_owned_root(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    monkeypatch.delenv("RUNNER_TEMP", raising=False)
    monkeypatch.setattr(runner.tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(runner, "_windows_pytest_path_within_budget", lambda path: True)
    replacement: Path | None = None
    stolen: Path | None = None
    run_root: Path | None = None

    with pytest.raises(runner.CoverageGateError, match="replaced"):
        with runner.isolated_coverage_environment() as run:
            run_root = run.run_root
            pytest_temp = Path(run.environment["PYTEST_DEBUG_TEMPROOT"])
            stolen = tmp_path / "stolen-owned-pytest-root"
            pytest_temp.rename(stolen)
            pytest_temp.mkdir()
            replacement = pytest_temp / "external-marker.txt"
            replacement.write_text("do not delete", encoding="utf-8")

    assert stolen is not None and not stolen.exists()
    assert replacement is not None
    assert replacement.read_text(encoding="utf-8") == "do not delete"
    assert run_root is not None and not run_root.exists()
    shutil.rmtree(replacement.parent)


@pytest.mark.skipif(os.name != "nt", reason="Windows cleanup authority semantics")
@pytest.mark.parametrize("replacement_kind", ("directory", "junction"))
def test_isolated_coverage_cleanup_revalidates_temporary_root_authority(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    replacement_kind: str,
) -> None:
    """Catches normal cleanup trusting a replaced or reparse temporary root."""
    runner = importlib.import_module("scripts.run_coverage_gate")
    backing = tmp_path.parent / f"{tmp_path.name}-authority-backing"
    redirect_target = tmp_path.parent / f"{tmp_path.name}-authority-target"
    monkeypatch.setattr(runner.tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    monkeypatch.setattr(runner, "_windows_pytest_path_within_budget", lambda path: True)
    moved_owned: Path | None = None
    external_marker: Path | None = None
    try:
        with pytest.raises(runner.CoverageGateError) as raised:
            with runner.isolated_coverage_environment() as run:
                owned_name = run.run_root.name
                owned_marker = run.run_root / "owned-marker.txt"
                owned_marker.write_text("owned", encoding="utf-8")
                tmp_path.rename(backing)
                if replacement_kind == "junction":
                    redirect_target.mkdir()
                    _create_directory_redirect(tmp_path, redirect_target)
                    replacement_root = redirect_target
                else:
                    tmp_path.mkdir()
                    replacement_root = tmp_path
                external_marker = replacement_root / "external-marker.txt"
                external_marker.write_text("external authority", encoding="utf-8")
                moved_owned = replacement_root / owned_name
                (backing / owned_name).rename(moved_owned)

        assert moved_owned is not None
        assert (moved_owned / "owned-marker.txt").read_text(encoding="utf-8") == "owned"
        assert external_marker is not None
        assert external_marker.read_text(encoding="utf-8") == "external authority"
        assert str(raised.value) == "coverage cleanup authority changed"
        assert not list(redirect_target.glob(".hsconfig-coverage-quarantine-*"))
        if replacement_kind == "directory":
            assert not list(tmp_path.glob(".hsconfig-coverage-quarantine-*"))
    finally:
        try:
            replacement_metadata = tmp_path.lstat()
        except FileNotFoundError:
            replacement_metadata = None
        if replacement_metadata is not None:
            if runner._is_reparse(replacement_metadata):
                tmp_path.rmdir()
            else:
                shutil.rmtree(tmp_path)
        if redirect_target.exists():
            shutil.rmtree(redirect_target)
        if backing.exists():
            backing.rename(tmp_path)


def test_coverage_environment_rejects_ambient_tool_authorities(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    external_debug = tmp_path / "ambient-coverage-debug.log"
    ambient = {
        "COVERAGE_DEBUG": "config",
        "COVERAGE_DEBUG_FILE": str(external_debug),
        "COVERAGE_PROCESS_START": str(tmp_path / "ambient-coveragerc"),
        "HSCONFIG_COVERAGE_TEST_REPOSITORY_ROOT": str(tmp_path / "forged-repository"),
        "HSCONFIG_COVERAGE_TEST_REPOSITORY_BINDING": "forged-binding",
        "HSCONFIG_COVERAGE_LOCKED_TEST_RUNTIME_BINDING": "forged-locked-runtime",
        "HSCONFIG_COVERAGE_LOCKED_TEST_RUNTIME_SHA256": "f" * 64,
        "HSCONFIG_RELEASE_GATE_BOOTSTRAP_SENTINEL": "forged-sentinel",
        "HSCONFIG_RUNTIME_MANIFEST": str(tmp_path / "forged-manifest.json"),
        "HSCONFIG_RUNTIME_MANIFEST_SHA256": "forged-digest",
        "HYPOTHESIS_PROFILE": "ambient-profile",
        "PYTEST_ADDOPTS": "--trace-config",
        "PYTEST_PLUGINS": "ambient.plugin",
        "PYTHONBREAKPOINT": "ambient.breakpoint",
        "PYTHONINSPECT": "1",
        "PYTHONPATH": str(tmp_path / "ambient-pythonpath"),
        "PYTHONSTARTUP": str(tmp_path / "ambient-startup.py"),
    }
    for key, value in ambient.items():
        monkeypatch.setenv(key, value)

    with runner.isolated_coverage_environment() as run:
        completed = subprocess.run(
            (
                sys.executable,
                "-c",
                "import coverage; c=coverage.Coverage(); c.start(); c.stop()",
            ),
            cwd=ROOT,
            env=run.environment,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        inherited = sorted(
            (set(ambient) & set(run.environment))
            - {
                "HSCONFIG_COVERAGE_TEST_REPOSITORY_BINDING",
                "HSCONFIG_COVERAGE_LOCKED_TEST_RUNTIME_BINDING",
                "HSCONFIG_COVERAGE_LOCKED_TEST_RUNTIME_SHA256",
            }
        )

    assert completed.returncode == 0, completed.stderr
    if run.locked_test_runtime is None:
        assert inherited == ["PYTEST_PLUGINS"]
        assert "PYTHONPATH" not in run.environment
        assert (
            "HSCONFIG_COVERAGE_LOCKED_TEST_RUNTIME_BINDING"
            not in run.environment
        )
        assert "HSCONFIG_COVERAGE_LOCKED_TEST_RUNTIME_SHA256" not in run.environment
    else:
        repository_binding = json.loads(
            run.environment["HSCONFIG_COVERAGE_TEST_REPOSITORY_BINDING"]
        )
        assert repository_binding != ambient[
            "HSCONFIG_COVERAGE_TEST_REPOSITORY_BINDING"
        ]
        assert repository_binding["repository"] == str(
            run.locked_test_runtime.repository_root
        )
        assert repository_binding["commit_oid"] == run.locked_test_runtime.commit_oid
        assert repository_binding["tree_oid"] == run.locked_test_runtime.tree_oid
        document = run.environment[
            "HSCONFIG_COVERAGE_LOCKED_TEST_RUNTIME_BINDING"
        ]
        digest = run.environment["HSCONFIG_COVERAGE_LOCKED_TEST_RUNTIME_SHA256"]
        assert document != ambient["HSCONFIG_COVERAGE_LOCKED_TEST_RUNTIME_BINDING"]
        assert hashlib.sha256(document.encode("utf-8")).hexdigest() == digest
        assert inherited == ["PYTEST_PLUGINS", "PYTHONPATH"]
        assert run.environment["PYTHONPATH"] == str(
            run.locked_test_runtime.build_backend_root
        )
        assert run.environment["PYTHONPATH"] != ambient["PYTHONPATH"]
    assert run.environment["PYTEST_PLUGINS"] == (
        "pytest_cov.plugin,_hypothesis_pytestplugin"
    )
    assert not external_debug.exists()


def test_coverage_environment_reconstructs_validated_runtime_pythonpath(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    source_root = tmp_path / "committed-source"
    build_backend_root = tmp_path / "build-backend"
    repository_root = tmp_path / "repository"
    source_root.mkdir()
    build_backend_root.mkdir()
    repository_root.mkdir()
    monkeypatch.setenv("PYTHONPATH", str(tmp_path / "ambient"))
    monkeypatch.setenv(
        "HSCONFIG_COVERAGE_TEST_REPOSITORY_ROOT",
        str(tmp_path / "forged-repository"),
    )
    monkeypatch.setenv(
        "HSCONFIG_COVERAGE_TEST_REPOSITORY_BINDING",
        "forged-binding",
    )

    with runner.isolated_coverage_environment(
        _test_coverage_runtime_binding(
            runner,
            repository=repository_root,
            source_root=source_root,
            build_backend_root=build_backend_root,
        )
    ) as run:
        assert run.environment["PYTHONPATH"].split(os.pathsep) == [
            str(source_root.resolve(strict=True)),
            str(build_backend_root.resolve(strict=True)),
        ]
        assert "HSCONFIG_COVERAGE_TEST_REPOSITORY_ROOT" not in run.environment
        repository_binding = json.loads(
            run.environment["HSCONFIG_COVERAGE_TEST_REPOSITORY_BINDING"]
        )
        assert repository_binding["repository"] == str(
            repository_root.resolve(strict=True)
        )
        assert repository_binding["commit_oid"] == "a" * 40
        assert repository_binding["tree_oid"] == "b" * 40


@pytest.mark.parametrize("kind", ("directory", "symlink", "hardlink"))
def test_coverage_report_validation_rejects_unsafe_file_types(
    tmp_path: Path,
    kind: str,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    run_root = tmp_path / "run"
    run_root.mkdir()
    report = run_root / "coverage.json"
    if kind == "directory":
        report.mkdir()
    elif kind == "symlink":
        target = run_root / "target.json"
        target.write_text("{}", encoding="utf-8")
        try:
            report.symlink_to(target)
        except OSError:
            pytest.skip("symlinks unavailable")
    else:
        target = run_root / "target.json"
        target.write_text("{}", encoding="utf-8")
        os.link(target, report)

    with pytest.raises(runner.CoverageGateError, match="coverage report"):
        runner._coverage_report_identity(run_root, report)


def test_coverage_report_identity_detects_replacement_race(tmp_path: Path) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    run_root = tmp_path / "run"
    run_root.mkdir()
    report = run_root / "coverage.json"
    report.write_text("{}", encoding="utf-8")
    identity = runner._coverage_report_identity(run_root, report)
    report.unlink()
    report.write_text('{"changed":true}', encoding="utf-8")

    with pytest.raises(runner.CoverageGateError, match="changed"):
        runner._assert_coverage_report_unchanged(run_root, report, identity)


def test_coverage_report_validation_rejects_run_directory_replacement(
    tmp_path: Path,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    run_root = tmp_path / "run"
    run_root.mkdir()
    root_identity = runner._coverage_directory_identity(run_root)
    original = tmp_path / "original"
    run_root.rename(original)
    run_root.mkdir()
    report = run_root / "coverage.json"
    report.write_text("{}", encoding="utf-8")

    with pytest.raises(runner.CoverageGateError, match="directory changed"):
        runner._coverage_report_identity(run_root, report, root_identity)


def test_checker_timeout_is_bounded_redacted_and_normalized(capsys) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    local_path = str(ROOT / "private-diagnostic")
    command = (
        sys.executable,
        "-c",
        "import sys,time; "
        f"sys.stderr.write({local_path!r}); sys.stderr.flush(); time.sleep(30)",
    )

    result = runner._run_checker_bounded(
        command,
        cwd=ROOT,
        env=os.environ,
        timeout=1,
    )

    assert result.returncode == 2
    assert json.loads(result.stdout)["returncode"] == 2
    diagnostic = capsys.readouterr().err
    assert local_path not in diagnostic
    assert "sha256=" in diagnostic

    assert runner._forward_checker_result(result) == 2
    forwarded = json.loads(capsys.readouterr().out)
    assert forwarded["errors"] == ["coverage checker timed out"]
    assert forwarded["returncode"] == 2


def test_checker_large_diagnostics_are_bounded_and_redacted(capsys) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    result = runner._run_checker_bounded(
        (
            sys.executable,
            "-c",
            "import json,sys; sys.stderr.write('x'*200000); "
            "print(json.dumps({'passed': True}))",
        ),
        cwd=ROOT,
        env=os.environ,
        timeout=30,
    )

    assert result.returncode == 0
    assert len(result.stdout) < 70_000
    diagnostic = capsys.readouterr().err
    assert "sha256=" in diagnostic
    assert len(diagnostic) < 500


def test_checker_oversized_stdout_becomes_one_portable_failure_json(capsys) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    result = runner._run_checker_bounded(
        (
            sys.executable,
            "-c",
            "import json; print('x'*200000, end=''); "
            "print(json.dumps({'passed': True}))",
        ),
        cwd=ROOT,
        env=os.environ,
        timeout=30,
    )

    assert result.returncode == 2
    assert runner._forward_checker_result(result) == 2
    output = capsys.readouterr().out
    assert output.count("\n") == 1
    document = json.loads(output)
    assert document["passed"] is False
    assert document["returncode"] == 2
    assert document["errors"] == ["coverage checker stdout exceeded limit"]


def test_checker_valid_success_followed_by_read_error_fails_closed(
    monkeypatch: MonkeyPatch,
    capsys,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")

    class Stream:
        def __init__(self) -> None:
            self.calls = 0

        def read(self, _size: int = -1) -> bytes:
            self.calls += 1
            if self.calls == 1:
                return (json.dumps(_checker_document(passed=True)) + "\n").encode()
            raise OSError("injected read failure")

    stdout = runner._BoundedCapture()
    stdout.drain(Stream())
    stderr = runner._BoundedCapture()
    bounded = runner._BoundedResult(
        completed=subprocess.CompletedProcess(
            (sys.executable,), 0, stdout=stdout.text(), stderr=""
        ),
        timed_out=False,
        stdout=stdout,
        stderr=stderr,
    )
    monkeypatch.setattr(runner, "_run_bounded_process", lambda *_a, **_k: bounded)

    result = runner._run_checker_bounded(
        (sys.executable,), cwd=ROOT, env=os.environ, timeout=30
    )

    assert stdout.error is not None
    assert result.returncode == 2
    assert runner._forward_checker_result(result) == 2
    document = json.loads(capsys.readouterr().out)
    assert document["errors"] == ["coverage checker stdout read failed"]
    assert document["returncode"] == 2


def test_pytest_capture_read_error_cannot_preserve_success_exit(
    monkeypatch: MonkeyPatch,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    stdout = runner._BoundedCapture()
    stdout.error = OSError("injected read failure")
    stderr = runner._BoundedCapture()
    bounded = runner._BoundedResult(
        completed=subprocess.CompletedProcess(
            (sys.executable,), 0, stdout="valid-looking success", stderr=""
        ),
        timed_out=False,
        stdout=stdout,
        stderr=stderr,
    )
    monkeypatch.setattr(runner, "_run_bounded_process", lambda *_a, **_k: bounded)

    result = runner._run_pytest_bounded(
        (sys.executable,), cwd=ROOT, env=os.environ
    )

    assert result.returncode == 2


def test_pytest_coverage_uses_realistic_strictly_bounded_timeout(
    monkeypatch: MonkeyPatch,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    observed_timeouts: list[int] = []
    stdout = runner._BoundedCapture()
    stderr = runner._BoundedCapture()

    def fake_bounded_process(
        command: tuple[str, ...], **kwargs: object
    ) -> runner._BoundedResult:
        timeout = kwargs["timeout"]
        assert isinstance(timeout, int)
        observed_timeouts.append(timeout)
        return runner._BoundedResult(
            completed=subprocess.CompletedProcess(
                command,
                0,
                stdout="",
                stderr="",
            ),
            timed_out=False,
            stdout=stdout,
            stderr=stderr,
        )

    monkeypatch.setattr(runner, "_run_bounded_process", fake_bounded_process)

    result = runner._run_pytest_bounded(
        (sys.executable,),
        cwd=ROOT,
        env=os.environ,
    )

    assert result.returncode == 0
    assert len(observed_timeouts) == 1
    assert 14_400 <= observed_timeouts[0] < 18_000


def test_canonical_coverage_timeout_hierarchy_preserves_cleanup_reserves() -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    bootstrap = importlib.import_module("scripts.check_release_gate")
    release_gate = importlib.import_module("hsconfig.release_gate")
    coverage_spec = next(
        spec
        for spec in release_gate._command_specs(
            ROOT,
            ROOT / "outputs",
            "working-pre-cutover",
        )
        if spec.name == "full_tests_and_coverage"
    )
    bootstrap_timeout = inspect.signature(bootstrap._run_bound_child).parameters[
        "timeout"
    ].default

    assert isinstance(bootstrap_timeout, int)
    assert bootstrap_timeout == getattr(
        bootstrap,
        "_BOOTSTRAP_CHILD_TIMEOUT_SECONDS",
        None,
    )
    assert coverage_spec.timeout - runner.PYTEST_TIMEOUT_SECONDS >= 3_600
    assert bootstrap_timeout - coverage_spec.timeout >= 3_600


@pytest.mark.parametrize(
    ("child_returncode", "child_passed", "wrapper_returncode"),
    [(0, True, 0), (1, False, 1), (9, False, 2), (-9, False, 2)],
)
def test_checker_exit_codes_are_normalized_with_matching_nested_returncode(
    child_returncode: int,
    child_passed: bool,
    wrapper_returncode: int,
    capsys,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    checker_payload = (
        _checker_document(passed=child_passed)
        if child_returncode in {0, 1}
        else {
            "passed": False,
            "global_branch_percent": None,
            "global_minimum": 89.0,
            "target_met": False,
            "critical_modules": [],
            "errors": ["execution failed"],
        }
    )
    result = subprocess.CompletedProcess(
        ["checker"],
        child_returncode,
        stdout=json.dumps(checker_payload) + "\n",
        stderr="",
    )

    assert runner._forward_checker_result(result) == wrapper_returncode
    output = capsys.readouterr().out
    assert output.count("\n") == 1
    document = json.loads(output)
    assert document["passed"] is (wrapper_returncode == 0)
    assert document["returncode"] == wrapper_returncode


def test_checker_capture_thread_baseexception_is_reraised_after_child_cleanup(
    monkeypatch: MonkeyPatch,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    real_thread = runner.threading.Thread
    created = 0

    def thread_factory(*args: object, **kwargs: object):
        nonlocal created
        created += 1
        thread = real_thread(*args, **kwargs)
        if created == 2:
            def interrupt() -> None:
                raise KeyboardInterrupt

            thread.start = interrupt
        return thread

    monkeypatch.setattr(runner.threading, "Thread", thread_factory)

    with pytest.raises(KeyboardInterrupt):
        runner._run_checker_bounded(
            (sys.executable, "-c", "import time; time.sleep(30)"),
            cwd=ROOT,
            env=os.environ,
            timeout=30,
        )


def test_checker_capture_is_read_only_after_drain_threads_finish(
    monkeypatch: MonkeyPatch,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    original_drain = runner._BoundedCapture.drain

    def delayed_drain(capture, stream) -> None:
        time.sleep(0.2)
        original_drain(capture, stream)

    monkeypatch.setattr(runner._BoundedCapture, "drain", delayed_drain)

    result = runner._run_checker_bounded(
        (
            sys.executable,
            "-c",
            "import json; print(json.dumps({'passed': True}))",
        ),
        cwd=ROOT,
        env=os.environ,
        timeout=30,
    )

    assert json.loads(result.stdout) == {"passed": True}


@pytest.mark.parametrize(
    "mutation",
    ("missing_key", "extra_key", "wrong_module", "wrong_threshold", "wrong_type"),
)
def test_forwarder_requires_the_closed_coverage_checker_schema(
    mutation: str,
    capsys,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    document = _checker_document()
    if mutation == "missing_key":
        document.pop("errors")
    elif mutation == "extra_key":
        document["unexpected"] = True
    elif mutation == "wrong_module":
        document["critical_modules"][0]["module"] = "src/hsconfig/not-critical.py"
    elif mutation == "wrong_threshold":
        document["global_minimum"] = 0.0
    else:
        document["critical_modules"][0]["statement_percent"] = "100"
    result = subprocess.CompletedProcess(
        ["checker"],
        0,
        stdout=json.dumps(document) + "\n",
        stderr="",
    )

    assert runner._forward_checker_result(result) == 2
    assert json.loads(capsys.readouterr().out)["returncode"] == 2


@pytest.mark.parametrize(
    ("percent", "returncode", "target_met"),
    (
        (88.99, 1, False),
        (89.0, 0, False),
        (94.99, 0, False),
        (95.0, 0, True),
        (100.0, 0, True),
    ),
)
def test_forwarder_enforces_coverage_threshold_boundaries(
    percent: float,
    returncode: int,
    target_met: bool,
    capsys,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    document = _checker_document_at(percent)
    result = subprocess.CompletedProcess(
        ["checker"],
        returncode,
        stdout=json.dumps(document) + "\n",
        stderr="",
    )

    assert runner._forward_checker_result(result) == returncode
    emitted = json.loads(capsys.readouterr().out)
    assert emitted["global_branch_percent"] == percent
    assert emitted["target_met"] is target_met


@pytest.mark.parametrize(
    "mutation",
    ("target", "passed", "errors", "row_percent", "null_row"),
)
def test_forwarder_rejects_semantically_contradictory_checker_documents(
    mutation: str,
    capsys,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    document = _checker_document_at(95.0)
    returncode = 0
    if mutation == "target":
        document["target_met"] = False
    elif mutation == "passed":
        document["passed"] = False
        returncode = 1
    elif mutation == "errors":
        document["errors"] = ["invented failure"]
    elif mutation == "row_percent":
        document["critical_modules"][0]["statement_percent"] = 99.0
    else:
        document["critical_modules"][0]["statement_percent"] = None
    result = subprocess.CompletedProcess(
        ["checker"],
        returncode,
        stdout=json.dumps(document) + "\n",
        stderr="",
    )

    assert runner._forward_checker_result(result) == 2
    assert json.loads(capsys.readouterr().out)["returncode"] == 2


def test_runtime_lock_rejects_every_unlocked_visible_distribution(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    lock = tmp_path / "pylock.toml"
    lock.write_text(_lock_text(), encoding="utf-8")

    class Distribution:
        def __init__(self, name: str) -> None:
            self.metadata = {"Name": name}
            self.version = "1.0"

    monkeypatch.setattr(
        runner.importlib_metadata,
        "distributions",
        lambda: (
            Distribution("locked-pkg"),
            Distribution("hsconfig"),
            Distribution("unlocked-extra"),
        ),
    )

    with pytest.raises(runner.RuntimeLockError, match="package set"):
        runner._assert_runtime_matches_lock(lock)


def test_runtime_lock_rejects_same_version_distribution_with_wrong_origin(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    lock = tmp_path / "pylock.toml"
    lock.write_text(_lock_text(), encoding="utf-8")

    class Distribution:
        version = "1.0"

        def __init__(self, name: str, direct_url: str | None = None) -> None:
            self.metadata = {"Name": name}
            self.direct_url = direct_url

        def read_text(self, filename: str) -> str | None:
            if filename == "INSTALLER":
                return "pip\n"
            if filename == "WHEEL":
                return "Wheel-Version: 1.0\n"
            if filename == "RECORD":
                return "package.py,,\n"
            if filename == "direct_url.json":
                return self.direct_url
            return None

        def locate_file(self, filename: str) -> Path:
            del filename
            return Path(sysconfig.get_paths()["purelib"])

    monkeypatch.setattr(
        runner.importlib_metadata,
        "distributions",
        lambda: (
            Distribution("locked-pkg", '{"url":"https://wrong.invalid/pkg.whl"}'),
            Distribution("hsconfig", json.dumps({"dir_info": {}, "url": ROOT.as_uri()})),
        ),
    )

    with pytest.raises(runner.RuntimeLockError, match="origin") as caught:
        runner._assert_runtime_matches_lock(lock)
    assert caught.value.category is runner.RuntimeLockCategory.DISTRIBUTION_ORIGIN


def test_checker_consumes_bound_coverage_bytes_and_detects_swap_restore(
    tmp_path: Path,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    run_root = tmp_path / "run"
    run_root.mkdir()
    report = _write_coverage(run_root, _coverage_payload())
    run_identity = runner._coverage_directory_identity(run_root)
    identity = runner._coverage_report_identity(run_root, report, run_identity)
    original = run_root / "original.json"
    report.rename(original)
    report.write_text(json.dumps({"forged": True}), encoding="utf-8")
    report.unlink()
    original.rename(report)

    result = runner._run_checker_bounded(
        runner._checker_command(
            interpreter=Path(sys.executable).resolve(strict=True)
        ),
        cwd=ROOT,
        env=os.environ,
        timeout=30,
        input_bytes=identity.content,
    )

    assert result.returncode == 0
    assert json.loads(result.stdout)["passed"] is True
    with pytest.raises(runner.CoverageGateError, match="changed"):
        runner._assert_coverage_report_unchanged(
            run_root,
            report,
            identity,
            run_identity,
        )


@pytest.mark.parametrize("parent_returncode", (0, 1))
def test_checker_kills_descendants_even_after_parent_exits(
    tmp_path: Path,
    parent_returncode: int,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    marker = tmp_path / f"descendant-{parent_returncode}.txt"
    child = (
        "import pathlib,time; time.sleep(2); "
        f"pathlib.Path({str(marker)!r}).write_text('escaped', encoding='utf-8')"
    )
    parent = (
        "import subprocess,sys; "
        f"subprocess.Popen([sys.executable,'-c',{child!r}]); "
        f"raise SystemExit({parent_returncode})"
    )

    result = runner._run_checker_bounded(
        (sys.executable, "-c", parent),
        cwd=ROOT,
        env=os.environ,
        timeout=10,
    )

    assert result.returncode == parent_returncode
    time.sleep(3)
    assert not marker.exists()


@pytest.mark.skipif(os.name == "nt", reason="POSIX signal return codes only")
def test_checker_kills_descendants_after_parent_signal(tmp_path: Path) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    marker = tmp_path / "signal-descendant.txt"
    child = (
        "import pathlib,time; time.sleep(2); "
        f"pathlib.Path({str(marker)!r}).write_text('escaped', encoding='utf-8')"
    )
    parent = (
        "import os,signal,subprocess,sys; "
        f"subprocess.Popen([sys.executable,'-c',{child!r}]); "
        "os.kill(os.getpid(), signal.SIGTERM)"
    )

    result = runner._run_checker_bounded(
        (sys.executable, "-c", parent),
        cwd=ROOT,
        env=os.environ,
        timeout=10,
    )

    assert result.returncode not in {0, 1}
    assert runner._portable_child_returncode(result.returncode) == 2
    time.sleep(3)
    assert not marker.exists()


def test_coverage_cleanup_preserves_replacement_and_removes_owned_root(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    monkeypatch.setattr(runner.tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(runner, "_windows_pytest_path_within_budget", lambda path: True)
    replacement: Path | None = None
    stolen: Path | None = None

    with pytest.raises(runner.CoverageGateError, match="replaced"):
        with runner.isolated_coverage_environment() as run:
            stolen = tmp_path / "stolen-owned-root"
            run.run_root.rename(stolen)
            run.run_root.mkdir()
            replacement = run.run_root / "external-marker.txt"
            replacement.write_text("do not delete", encoding="utf-8")

    assert stolen is not None and not stolen.exists()
    assert replacement is not None and replacement.read_text(encoding="utf-8") == "do not delete"
    shutil.rmtree(replacement.parent)


@pytest.mark.skipif(os.name != "nt", reason="Windows directory rename sharing semantics")
def test_coverage_cleanup_retries_transient_child_handle_rename_without_residue(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """Catches a transient child handle making the first quarantine rename fail."""
    runner = importlib.import_module("scripts.run_coverage_gate")
    run_root = tmp_path / "owned-run"
    run_root.mkdir()
    child = run_root / "open-child.txt"
    child.write_bytes(b"payload")
    run_identity = runner._coverage_directory_identity(run_root)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateFileW.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    )
    kernel32.CreateFileW.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL
    child_handle = kernel32.CreateFileW(
        str(child),
        0x80000000,
        0x00000001 | 0x00000002,
        None,
        3,
        0x00000080,
        None,
    )
    assert child_handle not in {0, -1, ctypes.c_void_p(-1).value}
    real_windll = ctypes.WinDLL
    real_kernel32 = real_windll("kernel32", use_last_error=True)
    rename_failures: list[int] = []

    class CallProxy:
        def __init__(self, function) -> None:
            self.function = function
            self.argtypes = None
            self.restype = None

        def __call__(
            self,
            *args,
        ):
            return self.function(*args)

    class SetFileInformationProxy(CallProxy):
        def __call__(self, handle, information_class, information, size):
            nonlocal child_handle
            result = self.function(
                handle,
                information_class,
                information,
                size,
            )
            if information_class in {3, 22} and not result and child_handle is not None:
                error_code = ctypes.get_last_error()
                rename_failures.append(error_code)
                assert kernel32.CloseHandle(child_handle)
                child_handle = None
                ctypes.set_last_error(error_code)
            return result

    class Kernel32Proxy:
        def __init__(self) -> None:
            self.CreateFileW = CallProxy(real_kernel32.CreateFileW)
            self.GetFileInformationByHandle = CallProxy(
                real_kernel32.GetFileInformationByHandle
            )
            self.GetFileInformationByHandleEx = CallProxy(
                real_kernel32.GetFileInformationByHandleEx
            )
            self.CloseHandle = CallProxy(real_kernel32.CloseHandle)
            self.SetFileInformationByHandle = SetFileInformationProxy(
                real_kernel32.SetFileInformationByHandle
            )

    monkeypatch.setattr(
        ctypes,
        "WinDLL",
        lambda name, **kwargs: (
            Kernel32Proxy()
            if name == "kernel32"
            else real_windll(name, **kwargs)
        ),
    )
    try:
        runner._cleanup_owned_run_root(tmp_path, run_root, run_identity)
    finally:
        monkeypatch.setattr(ctypes, "WinDLL", real_windll)
        if child_handle is not None:
            assert kernel32.CloseHandle(child_handle)

    assert rename_failures == [5]
    assert not run_root.exists()
    assert not list(tmp_path.glob(".hsconfig-coverage-quarantine-*"))


@pytest.mark.skipif(os.name != "nt", reason="Windows quarantine rename identity")
def test_windows_quarantine_retry_never_renames_validated_path_replacement(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """Catches a replacement swap after retry validation but before rename."""
    runner = importlib.import_module("scripts.run_coverage_gate")
    run_root = tmp_path / "owned-run"
    run_root.mkdir()
    (run_root / "owned-marker.txt").write_text("owned", encoding="utf-8")
    run_identity = runner._coverage_directory_identity(run_root)
    temporary_root_identity = runner._coverage_directory_identity(tmp_path)
    stolen = tmp_path / "stolen-owned-run"
    external_marker = run_root / "external-marker.txt"
    real_find_owned = runner._find_owned_directory
    find_calls = 0

    def swap_after_retry_validation(
        temporary_root: Path,
        requested_path: Path,
        expected_identity: tuple[int, int],
    ) -> Path | None:
        nonlocal find_calls
        owned = real_find_owned(
            temporary_root,
            requested_path,
            expected_identity,
        )
        find_calls += 1
        if find_calls == 2:
            assert owned == run_root
            owned.rename(stolen)
            run_root.mkdir()
            external_marker.write_text("external authority", encoding="utf-8")
        return owned

    real_windll = ctypes.WinDLL
    real_kernel32 = real_windll("kernel32", use_last_error=True)
    rename_information_calls = 0

    class CallProxy:
        def __init__(self, function, callback=None) -> None:
            self.function = function
            self.callback = callback
            self.argtypes = None
            self.restype = None

        def __call__(self, *args):
            if self.callback is not None:
                selected = self.callback(*args)
                if selected is not None:
                    return selected
            return self.function(*args)

    class Kernel32Proxy:
        def __init__(self) -> None:
            self.CreateFileW = CallProxy(real_kernel32.CreateFileW)
            self.GetFileInformationByHandle = CallProxy(
                real_kernel32.GetFileInformationByHandle
            )
            self.GetFileInformationByHandleEx = CallProxy(
                real_kernel32.GetFileInformationByHandleEx
            )
            self.CloseHandle = CallProxy(real_kernel32.CloseHandle)
            self.SetFileInformationByHandle = CallProxy(
                real_kernel32.SetFileInformationByHandle,
                self.fail_first_rename,
            )

        @staticmethod
        def fail_first_rename(
            handle,
            information_class: int,
            information,
            size: int,
        ):
            nonlocal rename_information_calls
            del handle, information, size
            if information_class not in {3, 22}:
                return None
            rename_information_calls += 1
            if rename_information_calls == 1:
                ctypes.set_last_error(5)
                return 0
            return None

    monkeypatch.setattr(runner, "_find_owned_directory", swap_after_retry_validation)
    monkeypatch.setattr(
        ctypes,
        "WinDLL",
        lambda name, **kwargs: (
            Kernel32Proxy()
            if name == "kernel32"
            else real_windll(name, **kwargs)
        ),
    )
    try:
        with pytest.raises(runner.CoverageGateError, match="identity|ownership"):
            runner._cleanup_owned_run_root(
                tmp_path,
                run_root,
                run_identity,
                expected_temporary_root_identity=temporary_root_identity,
            )

        assert find_calls == 2
        assert (stolen / "owned-marker.txt").read_text(encoding="utf-8") == "owned"
        assert external_marker.read_text(encoding="utf-8") == "external authority"
        assert not list(tmp_path.glob(".hsconfig-coverage-quarantine-*"))
    finally:
        monkeypatch.setattr(ctypes, "WinDLL", real_windll)
        for quarantine in tmp_path.glob(".hsconfig-coverage-quarantine-*"):
            shutil.rmtree(quarantine, ignore_errors=True)
        if run_root.exists():
            shutil.rmtree(run_root)
        if stolen.exists():
            shutil.rmtree(stolen)


def test_coverage_cleanup_starts_no_windows_retry_after_deadline(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """Catches validation or rename starting after the retry deadline."""
    runner = importlib.import_module("scripts.run_coverage_gate")
    run_root = tmp_path / "owned-run"
    run_root.mkdir()
    run_identity = runner._coverage_directory_identity(run_root)
    replace_attempts = 0
    validation_attempts = 0
    sleeps: list[float] = []
    times = iter((10.0, 10.0, 20.0))
    real_find_owned = runner._find_owned_directory

    def count_validation(
        temporary_root: Path,
        requested_path: Path,
        expected_identity: tuple[int, int],
    ) -> Path | None:
        nonlocal validation_attempts
        validation_attempts += 1
        return real_find_owned(
            temporary_root,
            requested_path,
            expected_identity,
        )

    def persistent_access_denied(*args: object) -> None:
        nonlocal replace_attempts
        del args
        replace_attempts += 1
        error = PermissionError("persistent access denied")
        error.winerror = 5
        raise error

    monkeypatch.setattr(runner, "_windows_host", lambda: True)
    monkeypatch.setattr(runner, "_find_owned_directory", count_validation)
    monkeypatch.setattr(
        runner,
        "_windows_quarantine_owned_run_root",
        persistent_access_denied,
    )
    monkeypatch.setattr(runner.time, "monotonic", lambda: next(times))
    monkeypatch.setattr(runner.time, "sleep", sleeps.append)

    with pytest.raises(
        runner.CoverageGateError,
        match="coverage run cleanup failed",
    ) as raised:
        runner._cleanup_owned_run_root(tmp_path, run_root, run_identity)

    assert isinstance(raised.value.__cause__, PermissionError)
    assert raised.value.__cause__.winerror == 5
    assert replace_attempts == 1
    assert validation_attempts == 1
    assert len(sleeps) == 1
    assert run_root.is_dir()
    assert not list(tmp_path.glob(".hsconfig-coverage-quarantine-*"))


@pytest.mark.skipif(os.name != "nt", reason="Windows readonly deletion semantics")
def test_coverage_cleanup_removes_nested_readonly_file_without_residue(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    monkeypatch.setattr(runner.tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    monkeypatch.setattr(runner, "_windows_pytest_path_within_budget", lambda path: True)
    run_root: Path | None = None
    try:
        with runner.isolated_coverage_environment() as run:
            run_root = run.run_root
            readonly = (
                run.pytest_temp_root
                / "git-repo"
                / ".git"
                / "objects"
                / "ab"
                / "object"
            )
            readonly.parent.mkdir(parents=True)
            readonly.write_bytes(b"git loose object")
            os.chmod(readonly, stat.S_IREAD)
            assert (
                getattr(readonly.lstat(), "st_file_attributes", 0)
                & getattr(stat, "FILE_ATTRIBUTE_READONLY", 0x1)
            )

        assert run_root is not None and not run_root.exists()
        assert not list(tmp_path.glob(".hsconfig-coverage-quarantine-*"))
    finally:
        for quarantine in tmp_path.glob(".hsconfig-coverage-quarantine-*"):
            for path in quarantine.rglob("*"):
                if path.is_file():
                    os.chmod(path, stat.S_IWRITE)
            shutil.rmtree(quarantine, ignore_errors=True)


@pytest.mark.skipif(os.name != "nt", reason="Windows readonly hardlink semantics")
def test_coverage_cleanup_unlinks_readonly_hardlink_without_external_mutation(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    monkeypatch.setattr(runner.tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    monkeypatch.setattr(runner, "_windows_pytest_path_within_budget", lambda path: True)
    external = tmp_path / "external-readonly.txt"
    external.write_bytes(b"external authority")
    os.chmod(external, stat.S_IREAD)
    external_identity = (external.lstat().st_dev, external.lstat().st_ino)
    external_digest = hashlib.sha256(external.read_bytes()).hexdigest()
    try:
        with runner.isolated_coverage_environment() as run:
            linked = run.pytest_temp_root / "nested" / "linked.txt"
            linked.parent.mkdir(parents=True)
            os.link(external, linked)
            assert (linked.lstat().st_dev, linked.lstat().st_ino) == external_identity
            assert external.lstat().st_nlink == 2

        assert not list(tmp_path.glob(".hsconfig-coverage-quarantine-*"))
        assert external.read_bytes() == b"external authority"
        assert (external.lstat().st_dev, external.lstat().st_ino) == external_identity
        assert hashlib.sha256(external.read_bytes()).hexdigest() == external_digest
        assert external.lstat().st_nlink == 1
        assert (
            getattr(external.lstat(), "st_file_attributes", 0)
            & getattr(stat, "FILE_ATTRIBUTE_READONLY", 0x1)
        )
    finally:
        os.chmod(external, stat.S_IWRITE)
        for quarantine in tmp_path.glob(".hsconfig-coverage-quarantine-*"):
            shutil.rmtree(quarantine, ignore_errors=True)


@pytest.mark.skipif(os.name != "nt", reason="Windows pytest hardlink cleanup semantics")
def test_pytest_retention_cleanup_preserves_external_readonly_hardlink(
    tmp_path: Path,
) -> None:
    """Catches pytest chmod mutating authority outside its owned temp root."""
    runner = importlib.import_module("scripts.run_coverage_gate")
    run_root = tmp_path / "run"
    repository = run_root / "repository"
    tests_root = repository / "tests"
    tests_root.mkdir(parents=True)
    (tests_root / "test_hardlink.py").write_text(
        "import os\n"
        "from pathlib import Path\n"
        "def test_hardlink(tmp_path):\n"
        "    authority = Path(os.environ['HSCONFIG_TEST_HARDLINK_AUTHORITY'])\n"
        "    linked = tmp_path / 'linked.txt'\n"
        "    os.link(authority, linked)\n"
        "    assert linked.read_bytes() == b'external authority'\n",
        encoding="utf-8",
    )
    sideband = run_root / runner.PYTEST_FAILURE_SIDEBAND_NAME
    sideband.touch()
    basetemp = tmp_path / "pytest-temp"
    authority = tmp_path / "external-readonly.txt"
    authority.write_bytes(b"external authority")
    os.chmod(authority, stat.S_IREAD)
    authority_identity = (authority.lstat().st_dev, authority.lstat().st_ino)
    authority_digest = hashlib.sha256(authority.read_bytes()).hexdigest()
    command, environment = _failure_plugin_command(
        runner,
        repository,
        sideband,
        "-o",
        "tmp_path_retention_policy=failed",
        f"--basetemp={basetemp}",
    )
    environment["HSCONFIG_TEST_HARDLINK_AUTHORITY"] = str(authority)
    try:
        completed = subprocess.run(
            command,
            cwd=repository,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

        assert completed.returncode == 0, completed.stderr
        assert basetemp.is_dir()
        assert not list(basetemp.iterdir())
        assert (authority.lstat().st_dev, authority.lstat().st_ino) == authority_identity
        assert authority.read_bytes() == b"external authority"
        assert hashlib.sha256(authority.read_bytes()).hexdigest() == authority_digest
        assert authority.lstat().st_nlink == 1
        assert (
            getattr(authority.lstat(), "st_file_attributes", 0)
            & getattr(stat, "FILE_ATTRIBUTE_READONLY", 0x1)
        )
    finally:
        os.chmod(authority, stat.S_IWRITE)


@pytest.mark.skipif(os.name != "nt", reason="Windows readonly hardlink race semantics")
def test_coverage_cleanup_disposes_readonly_link_without_mutating_raced_hardlink(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    monkeypatch.setattr(runner.tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    monkeypatch.setattr(runner, "_windows_pytest_path_within_budget", lambda path: True)
    real_windll = ctypes.WinDLL
    real_kernel32 = real_windll("kernel32", use_last_error=True)
    get_final_path = real_kernel32.GetFinalPathNameByHandleW
    get_final_path.argtypes = (
        wintypes.HANDLE,
        wintypes.LPWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
    )
    get_final_path.restype = wintypes.DWORD
    external = tmp_path / "external-raced-readonly.txt"
    disposition_classes: list[int] = []
    disposition_flags: list[int] = []

    class CallProxy:
        def __init__(self, function, callback=None) -> None:
            self.function = function
            self.callback = callback
            self.argtypes = None
            self.restype = None

        def __call__(self, *args):
            if self.callback is not None:
                selected = self.callback(*args)
                if selected is not None:
                    return selected
            return self.function(*args)

    class Kernel32Proxy:
        def __init__(self) -> None:
            self.CreateFileW = CallProxy(real_kernel32.CreateFileW)
            self.GetFileInformationByHandle = CallProxy(
                real_kernel32.GetFileInformationByHandle
            )
            self.GetFileInformationByHandleEx = CallProxy(
                real_kernel32.GetFileInformationByHandleEx
            )
            self.CloseHandle = CallProxy(real_kernel32.CloseHandle)
            self.SetFileInformationByHandle = CallProxy(
                real_kernel32.SetFileInformationByHandle,
                self.intercept_set_information,
            )

        def intercept_set_information(
            self,
            handle,
            information_class: int,
            information,
            size: int,
        ):
            del size
            if information_class in {4, 21}:
                candidates = list(
                    tmp_path.glob(
                        ".hsconfig-coverage-quarantine-*/readonly-race.txt"
                    )
                )
                buffer = ctypes.create_unicode_buffer(32768)
                path_length = get_final_path(handle, buffer, len(buffer), 0)
                handle_path = Path(buffer.value.removeprefix("\\\\?\\"))
                if (
                    candidates
                    and path_length
                    and handle_path == candidates[0]
                    and not external.exists()
                ):
                    os.link(candidates[0], external)
                    disposition_classes.append(information_class)
                    if information_class == 21:
                        disposition_flags.append(
                            ctypes.cast(
                                information,
                                ctypes.POINTER(wintypes.DWORD),
                            ).contents.value
                        )
            return None

    monkeypatch.setattr(
        ctypes,
        "WinDLL",
        lambda name, **kwargs: (
            Kernel32Proxy()
            if name == "kernel32"
            else real_windll(name, **kwargs)
        ),
    )
    try:
        with runner.isolated_coverage_environment() as run:
            readonly = run.pytest_temp_root / "readonly-race.txt"
            readonly.write_bytes(b"raced payload")
            os.chmod(readonly, stat.S_IREAD)

        assert disposition_classes == [21]
        assert disposition_flags == [0x00000001 | 0x00000002 | 0x00000010]
        assert not list(tmp_path.glob(".hsconfig-coverage-quarantine-*"))
        assert external.read_bytes() == b"raced payload"
        assert external.lstat().st_nlink == 1
        assert (
            getattr(external.lstat(), "st_file_attributes", 0)
            & getattr(stat, "FILE_ATTRIBUTE_READONLY", 0x1)
        )
    finally:
        monkeypatch.setattr(ctypes, "WinDLL", real_windll)
        if external.exists():
            os.chmod(external, stat.S_IWRITE)
        for quarantine in tmp_path.glob(".hsconfig-coverage-quarantine-*"):
            for path in quarantine.rglob("*"):
                if path.is_file():
                    os.chmod(path, stat.S_IWRITE)
            shutil.rmtree(quarantine, ignore_errors=True)


def test_windows_delete_completion_waits_for_transient_pending_path(
    monkeypatch: MonkeyPatch,
) -> None:
    """Catches successful handle disposition being rejected before it settles."""
    runner = importlib.import_module("scripts.run_coverage_gate")
    sleeps: list[float] = []
    metadata = SimpleNamespace(
        st_dev=7,
        st_ino=11,
        st_mode=stat.S_IFREG,
        st_file_attributes=0,
    )
    observations = iter((metadata, FileNotFoundError()))

    def lstat():
        observation = next(observations)
        if isinstance(observation, BaseException):
            raise observation
        return observation

    path = SimpleNamespace(lstat=lstat)
    times = iter((10.0, 10.1))
    monkeypatch.setattr(runner.time, "monotonic", lambda: next(times))
    monkeypatch.setattr(runner.time, "sleep", sleeps.append)

    runner._await_windows_delete_completion(path, metadata)

    assert sleeps == [runner.WINDOWS_DELETE_SETTLE_POLL_SECONDS]


def test_windows_delete_completion_rejects_persistent_path(
    monkeypatch: MonkeyPatch,
) -> None:
    """Catches a bounded settle wait turning permanent residue into success."""
    runner = importlib.import_module("scripts.run_coverage_gate")
    metadata = SimpleNamespace(
        st_dev=7,
        st_ino=11,
        st_mode=stat.S_IFREG,
        st_file_attributes=0,
    )
    path = SimpleNamespace(lstat=lambda: metadata)
    times = iter((10.0, 10.0 + runner.WINDOWS_DELETE_SETTLE_TIMEOUT_SECONDS))
    monkeypatch.setattr(runner.time, "monotonic", lambda: next(times))

    with pytest.raises(runner.CoverageGateError, match="cleanup left residue"):
        runner._await_windows_delete_completion(path, metadata)


def test_windows_delete_completion_rejects_identity_replacement() -> None:
    """Catches a replacement being accepted as the original delete-pending entry."""
    runner = importlib.import_module("scripts.run_coverage_gate")
    replacement = SimpleNamespace(
        st_dev=7,
        st_ino=12,
        st_mode=stat.S_IFREG,
        st_file_attributes=0,
    )
    path = SimpleNamespace(lstat=lambda: replacement)

    with pytest.raises(runner.CoverageGateError, match="identity changed"):
        runner._await_windows_delete_completion(path, SimpleNamespace(
            st_dev=7,
            st_ino=11,
            st_mode=stat.S_IFREG,
            st_file_attributes=0,
        ))


@pytest.mark.skipif(os.name != "nt", reason="Windows POSIX disposition semantics")
def test_windows_delete_removes_owned_name_while_shared_handle_remains_open(
    tmp_path: Path,
) -> None:
    """Catches non-POSIX delete-pending names blocking bounded cleanup."""
    runner = importlib.import_module("scripts.run_coverage_gate")
    target = tmp_path / "shared-delete.txt"
    target.write_bytes(b"payload")
    identity = (target.lstat().st_dev, target.lstat().st_ino)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateFileW.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    )
    kernel32.CreateFileW.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL
    shared_handle = kernel32.CreateFileW(
        str(target),
        0x80000000,
        0x00000001 | 0x00000002 | 0x00000004,
        None,
        3,
        0x00000080,
        None,
    )
    assert shared_handle not in {0, -1, ctypes.c_void_p(-1).value}
    try:
        runner._delete_windows_entry(target, identity)
        assert not target.exists()
    finally:
        assert kernel32.CloseHandle(shared_handle)


@pytest.mark.skipif(os.name != "nt", reason="Windows handle-close semantics")
def test_windows_delete_completion_requires_successful_handle_close(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """Catches polling after an unverified close of the disposition handle."""
    runner = importlib.import_module("scripts.run_coverage_gate")
    target = tmp_path / "close-failure.txt"
    target.write_bytes(b"payload")
    identity = (target.lstat().st_dev, target.lstat().st_ino)
    real_windll = ctypes.WinDLL
    real_kernel32 = real_windll("kernel32", use_last_error=True)
    settle_called = False

    class CallProxy:
        def __init__(self, function, callback=None) -> None:
            self.function = function
            self.callback = callback
            self.argtypes = None
            self.restype = None

        def __call__(self, *args):
            if self.callback is not None:
                selected = self.callback(*args)
                if selected is not None:
                    return selected
            return self.function(*args)

    class Kernel32Proxy:
        def __init__(self) -> None:
            self.CreateFileW = CallProxy(real_kernel32.CreateFileW)
            self.GetFileInformationByHandle = CallProxy(
                real_kernel32.GetFileInformationByHandle
            )
            self.GetFileInformationByHandleEx = CallProxy(
                real_kernel32.GetFileInformationByHandleEx
            )
            self.SetFileInformationByHandle = CallProxy(
                real_kernel32.SetFileInformationByHandle
            )
            self.CloseHandle = CallProxy(
                real_kernel32.CloseHandle,
                self.close_but_report_failure,
            )

        @staticmethod
        def close_but_report_failure(handle):
            assert real_kernel32.CloseHandle(handle)
            return 0

    def record_settle(*args: object) -> None:
        nonlocal settle_called
        del args
        settle_called = True

    monkeypatch.setattr(
        ctypes,
        "WinDLL",
        lambda name, **kwargs: (
            Kernel32Proxy()
            if name == "kernel32"
            else real_windll(name, **kwargs)
        ),
    )
    monkeypatch.setattr(runner, "_await_windows_delete_completion", record_settle)

    with pytest.raises(runner.CoverageGateError, match="handle cannot be closed"):
        runner._delete_windows_entry(target, identity)

    assert settle_called is False


@pytest.mark.skipif(os.name != "nt", reason="Windows handle-bound disposition semantics")
def test_coverage_cleanup_ex_failure_leaves_readonly_attribute_untouched(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    monkeypatch.setattr(runner.tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    monkeypatch.setattr(runner, "_windows_pytest_path_within_budget", lambda path: True)
    real_windll = ctypes.WinDLL
    real_kernel32 = real_windll("kernel32", use_last_error=True)
    get_final_path = real_kernel32.GetFinalPathNameByHandleW
    get_final_path.argtypes = (
        wintypes.HANDLE,
        wintypes.LPWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
    )
    get_final_path.restype = wintypes.DWORD
    information_classes: list[int] = []
    desired_accesses: list[int] = []

    class CallProxy:
        def __init__(self, function, callback=None) -> None:
            self.function = function
            self.callback = callback
            self.argtypes = None
            self.restype = None

        def __call__(self, *args):
            if self.callback is not None:
                selected = self.callback(*args)
                if selected is not None:
                    return selected
            return self.function(*args)

    class Kernel32Proxy:
        def __init__(self) -> None:
            self.CreateFileW = CallProxy(
                real_kernel32.CreateFileW,
                self.intercept_create_file,
            )
            self.GetFileInformationByHandle = CallProxy(
                real_kernel32.GetFileInformationByHandle
            )
            self.GetFileInformationByHandleEx = CallProxy(
                real_kernel32.GetFileInformationByHandleEx
            )
            self.CloseHandle = CallProxy(real_kernel32.CloseHandle)
            self.SetFileInformationByHandle = CallProxy(
                real_kernel32.SetFileInformationByHandle,
                self.intercept_set_information,
            )

        def intercept_create_file(
            self,
            file_name,
            desired_access: int,
            share_mode,
            security_attributes,
            creation_disposition,
            flags_and_attributes,
            template_file,
        ):
            del (
                share_mode,
                security_attributes,
                creation_disposition,
                flags_and_attributes,
                template_file,
            )
            if Path(file_name).name == "readonly.txt":
                desired_accesses.append(desired_access)
            return None

        def intercept_set_information(
            self,
            handle,
            information_class: int,
            information,
            size: int,
        ):
            del information, size
            buffer = ctypes.create_unicode_buffer(32768)
            path_length = get_final_path(handle, buffer, len(buffer), 0)
            handle_path = Path(buffer.value.removeprefix("\\\\?\\"))
            candidates = list(
                tmp_path.glob(
                    ".hsconfig-coverage-quarantine-*/readonly.txt"
                )
            )
            if (
                information_class in {4, 21}
                and candidates
                and path_length
                and handle_path == candidates[0]
            ):
                information_classes.append(information_class)
                ctypes.set_last_error(5)
                return 0
            return None

    monkeypatch.setattr(
        ctypes,
        "WinDLL",
        lambda name, **kwargs: (
            Kernel32Proxy()
            if name == "kernel32"
            else real_windll(name, **kwargs)
        ),
    )
    try:
        with pytest.raises(runner.CoverageGateError, match="delete disposition"):
            with runner.isolated_coverage_environment() as run:
                readonly = run.pytest_temp_root / "readonly.txt"
                readonly.write_bytes(b"payload")
                os.chmod(readonly, stat.S_IREAD)

        quarantines = list(tmp_path.glob(".hsconfig-coverage-quarantine-*"))
        assert len(quarantines) == 1
        preserved = quarantines[0] / "readonly.txt"
        assert preserved.read_bytes() == b"payload"
        assert (
            getattr(preserved.lstat(), "st_file_attributes", 0)
            & getattr(stat, "FILE_ATTRIBUTE_READONLY", 0x1)
        )
        assert information_classes == [21]
        assert desired_accesses == [
            0x00010000 | 0x00000100 | 0x00000080 | 0x00000001
        ]
    finally:
        monkeypatch.setattr(ctypes, "WinDLL", real_windll)
        for quarantine in tmp_path.glob(".hsconfig-coverage-quarantine-*"):
            preserved = quarantine / "readonly.txt"
            if preserved.exists():
                os.chmod(preserved, stat.S_IWRITE)
            shutil.rmtree(quarantine, ignore_errors=True)


@pytest.mark.skipif(os.name != "nt", reason="Windows FILE_ID_INFO ABI")
@pytest.mark.parametrize(
    (
        "python_version",
        "path_identity",
        "handle_file_ids",
        "legacy_identities",
        "should_delete",
    ),
    (
        pytest.param(
            (3, 11),
            (0xDEADBEEF, 0xFFFFFFFFFFFFFFFF),
            (
                0xA1B2C3D4E5F607181122334455667788,
                0xA1B2C3D4E5F607181122334455667788,
            ),
            (
                (0xDEADBEEF, 0xFFFFFFFFFFFFFFFF),
                (0xDEADBEEF, 0xFFFFFFFFFFFFFFFF),
            ),
            True,
            id="py311-refs-legacy-view-differs-from-full-low64",
        ),
        pytest.param(
            (3, 11),
            (0xDEADBEEF, 0xFFFFFFFFFFFFFFFF),
            (
                0xA1B2C3D4E5F607181122334455667788,
                0xB1B2C3D4E5F607181122334455667788,
            ),
            (
                (0xDEADBEEF, 0xFFFFFFFFFFFFFFFF),
                (0xDEADBEEF, 0xFFFFFFFFFFFFFFFF),
            ),
            False,
            id="py311-upper64-handle-change",
        ),
        pytest.param(
            (3, 11),
            (0xDEADBEEF, 0xFFFFFFFFFFFFFFFF),
            (
                0xA1B2C3D4E5F607181122334455667788,
                0xA1B2C3D4E5F607181122334455667788,
            ),
            (
                (0xDEADBEEF, 0xFFFFFFFFFFFFFFFF),
                (0xDEADBEEF, 0xEEEEEEEEEEEEEEEE),
            ),
            False,
            id="py311-legacy-handle-change",
        ),
        pytest.param(
            (3, 12),
            (
                0x12566FD7566FB9DD,
                0xA1B2C3D4E5F607181122334455667788,
            ),
            (
                0xA1B2C3D4E5F607181122334455667788,
                0xA1B2C3D4E5F607188877665544332211,
            ),
            (),
            False,
            id="py312-full128-handle-change",
        ),
        pytest.param(
            (3, 12),
            (
                0x12566FD7566FB9DD,
                0xA1B2C3D4E5F607181122334455667788,
            ),
            (
                0xA1B2C3D4E5F607181122334455667788,
                0xA1B2C3D4E5F607181122334455667788,
            ),
            (),
            True,
            id="py312-full128-stable",
        ),
    ),
)
def test_coverage_cleanup_uses_full_handle_and_compatible_path_identities(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    python_version: tuple[int, int],
    path_identity: tuple[int, int],
    handle_file_ids: tuple[int, int],
    legacy_identities: tuple[tuple[int, int], ...],
    should_delete: bool,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")

    class VersionedSys:
        version_info = python_version

    monkeypatch.setattr(runner, "sys", VersionedSys())
    target = tmp_path / "upper-file-id.txt"
    target.write_bytes(b"upper identity")
    volume_serial = 0x12566FD7566FB9DD
    real_lstat = type(target).lstat
    real_windll = ctypes.WinDLL
    real_kernel32 = real_windll("kernel32", use_last_error=True)
    get_final_path = real_kernel32.GetFinalPathNameByHandleW
    get_final_path.argtypes = (
        wintypes.HANDLE,
        wintypes.LPWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
    )
    get_final_path.restype = wintypes.DWORD
    observed_abi: list[tuple[int, int]] = []
    observed_legacy_abi: list[tuple[int, int]] = []

    class SyntheticStat:
        def __init__(self, metadata) -> None:
            self._metadata = metadata
            self.st_dev, self.st_ino = path_identity

        def __getattr__(self, name: str):
            return getattr(self._metadata, name)

    def synthetic_lstat(path, *args, **kwargs):
        metadata = real_lstat(path, *args, **kwargs)
        if path == target:
            return SyntheticStat(metadata)
        return metadata

    class CallProxy:
        def __init__(self, function, callback=None) -> None:
            self.function = function
            self.callback = callback
            self.argtypes = None
            self.restype = None

        def __call__(self, *args):
            if self.callback is not None:
                selected = self.callback(*args)
                if selected is not None:
                    return selected
            return self.function(*args)

    class Kernel32Proxy:
        def __init__(self) -> None:
            self.CreateFileW = CallProxy(real_kernel32.CreateFileW)
            self.GetFileInformationByHandle = CallProxy(
                real_kernel32.GetFileInformationByHandle,
                self.intercept_legacy_file_id,
            )
            self.GetFileInformationByHandleEx = CallProxy(
                real_kernel32.GetFileInformationByHandleEx,
                self.intercept_file_id,
            )
            self.SetFileInformationByHandle = CallProxy(
                real_kernel32.SetFileInformationByHandle
            )
            self.CloseHandle = CallProxy(real_kernel32.CloseHandle)

        def intercept_legacy_file_id(self, handle, information):
            buffer = ctypes.create_unicode_buffer(32768)
            path_length = get_final_path(handle, buffer, len(buffer), 0)
            if not path_length or Path(buffer.value.removeprefix("\\\\?\\")) != target:
                return None
            if not legacy_identities:
                raise AssertionError("legacy file identity queried on Python 3.12+")
            address = ctypes.cast(information, ctypes.c_void_p).value
            assert address is not None
            size = ctypes.sizeof(information._obj)
            observed_legacy_abi.append((size, address % 4))
            volume_serial, file_index = legacy_identities[
                min(len(observed_legacy_abi) - 1, 1)
            ]
            payload = bytearray(52)
            payload[28:32] = volume_serial.to_bytes(4, "little")
            payload[40:44] = (1).to_bytes(4, "little")
            payload[44:48] = (file_index >> 32).to_bytes(4, "little")
            payload[48:52] = (file_index & 0xFFFFFFFF).to_bytes(4, "little")
            ctypes.memmove(information, bytes(payload), len(payload))
            return 1

        def intercept_file_id(
            self,
            handle,
            information_class: int,
            information,
            size: int,
        ):
            if information_class != 18:
                return None
            buffer = ctypes.create_unicode_buffer(32768)
            path_length = get_final_path(handle, buffer, len(buffer), 0)
            if not path_length or Path(buffer.value.removeprefix("\\\\?\\")) != target:
                return None
            address = ctypes.cast(information, ctypes.c_void_p).value
            assert address is not None
            observed_abi.append((size, address % 8))
            file_id = handle_file_ids[min(len(observed_abi) - 1, 1)]
            payload = volume_serial.to_bytes(8, "little") + file_id.to_bytes(
                16,
                "little",
            )
            ctypes.memmove(information, payload, len(payload))
            return 1

    monkeypatch.setattr(type(target), "lstat", synthetic_lstat)
    monkeypatch.setattr(
        ctypes,
        "WinDLL",
        lambda name, **kwargs: (
            Kernel32Proxy()
            if name == "kernel32"
            else real_windll(name, **kwargs)
        ),
    )
    try:
        if should_delete:
            runner._delete_windows_entry(target, path_identity)
            assert not target.exists()
        else:
            with pytest.raises(runner.CoverageGateError, match="identity changed"):
                runner._delete_windows_entry(target, path_identity)
            assert target.exists()
        assert len(observed_abi) == 2
        assert set(observed_abi) == {(24, 0)}
        assert len(observed_legacy_abi) == (2 if python_version < (3, 12) else 0)
        assert set(observed_legacy_abi) <= {(52, 0)}
    finally:
        monkeypatch.setattr(ctypes, "WinDLL", real_windll)
        if target.exists():
            target.unlink()


@pytest.mark.skipif(os.name != "nt", reason="Windows FILE_ID_INFO identity")
def test_coverage_cleanup_real_file_and_directory_ids_match_lstat(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    root = tmp_path / "real-file-id-root"
    nested = root / "nested"
    nested.mkdir(parents=True)
    (nested / "payload.txt").write_bytes(b"identity")
    real_windll = ctypes.WinDLL
    real_kernel32 = real_windll("kernel32", use_last_error=True)
    get_legacy_file_id = real_kernel32.GetFileInformationByHandle
    get_legacy_file_id.argtypes = (
        wintypes.HANDLE,
        ctypes.c_void_p,
    )
    get_legacy_file_id.restype = wintypes.BOOL
    get_file_id = real_kernel32.GetFileInformationByHandleEx
    get_file_id.argtypes = (
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    )
    get_file_id.restype = wintypes.BOOL
    get_final_path = real_kernel32.GetFinalPathNameByHandleW
    get_final_path.argtypes = (
        wintypes.HANDLE,
        wintypes.LPWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
    )
    get_final_path.restype = wintypes.DWORD
    observed_full: list[tuple[str, bool]] = []
    observed_legacy: list[tuple[str, bool]] = []

    class CallProxy:
        def __init__(self, function, callback=None) -> None:
            self.function = function
            self.callback = callback
            self.argtypes = None
            self.restype = None

        def __call__(self, *args):
            if self.callback is not None:
                selected = self.callback(*args)
                if selected is not None:
                    return selected
            return self.function(*args)

    class Kernel32Proxy:
        def __init__(self) -> None:
            self.CreateFileW = CallProxy(real_kernel32.CreateFileW)
            self.GetFileInformationByHandle = CallProxy(
                get_legacy_file_id,
                self.observe_legacy_file_id,
            )
            self.GetFileInformationByHandleEx = CallProxy(
                get_file_id,
                self.observe_file_id,
            )
            self.SetFileInformationByHandle = CallProxy(
                real_kernel32.SetFileInformationByHandle
            )
            self.CloseHandle = CallProxy(real_kernel32.CloseHandle)

        def observe_legacy_file_id(self, handle, information):
            result = get_legacy_file_id(handle, information)
            if not result:
                return result
            buffer = ctypes.create_unicode_buffer(32768)
            path_length = get_final_path(handle, buffer, len(buffer), 0)
            assert path_length
            path = Path(buffer.value.removeprefix("\\\\?\\"))
            metadata = path.lstat()
            raw = ctypes.string_at(information, ctypes.sizeof(information._obj))
            volume_serial = int.from_bytes(raw[28:32], "little")
            file_index = (int.from_bytes(raw[44:48], "little") << 32) | int.from_bytes(
                raw[48:52],
                "little",
            )
            observed_legacy.append(
                (
                    "directory" if stat.S_ISDIR(metadata.st_mode) else "file",
                    (volume_serial, file_index)
                    == (metadata.st_dev, metadata.st_ino),
                )
            )
            return result

        def observe_file_id(
            self,
            handle,
            information_class: int,
            information,
            size: int,
        ):
            if information_class != 18:
                return None
            result = get_file_id(handle, information_class, information, size)
            if not result:
                return result
            buffer = ctypes.create_unicode_buffer(32768)
            path_length = get_final_path(handle, buffer, len(buffer), 0)
            assert path_length
            path = Path(buffer.value.removeprefix("\\\\?\\"))
            metadata = path.lstat()
            raw = ctypes.string_at(information, size)
            volume_serial = int.from_bytes(raw[:8], "little")
            file_id = int.from_bytes(raw[8:24], "little")
            observed_full.append(
                (
                    "directory" if stat.S_ISDIR(metadata.st_mode) else "file",
                    sys.version_info < (3, 12)
                    or (volume_serial, file_id)
                    == (metadata.st_dev, metadata.st_ino),
                )
            )
            return result

    monkeypatch.setattr(
        ctypes,
        "WinDLL",
        lambda name, **kwargs: (
            Kernel32Proxy()
            if name == "kernel32"
            else real_windll(name, **kwargs)
        ),
    )
    try:
        runner._delete_windows_entry(root, (root.lstat().st_dev, root.lstat().st_ino))
        assert not root.exists()
        assert {kind for kind, matched in observed_full if matched} == {
            "file",
            "directory",
        }
        assert all(matched for _, matched in observed_full)
        if sys.version_info < (3, 12):
            assert {kind for kind, matched in observed_legacy if matched} == {
                "file",
                "directory",
            }
            assert all(matched for _, matched in observed_legacy)
        else:
            assert not observed_legacy
    finally:
        monkeypatch.setattr(ctypes, "WinDLL", real_windll)
        if root.exists():
            shutil.rmtree(root)


def test_coverage_environment_setup_is_failure_atomic_for_baseexception(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    monkeypatch.setattr(runner.tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    monkeypatch.setattr(runner, "_windows_pytest_path_within_budget", lambda path: True)
    real_mkdtemp = runner.tempfile.mkdtemp
    real_mkdir = Path.mkdir
    created: list[Path] = []

    def recording_mkdtemp(*args: object, **kwargs: object) -> str:
        path = Path(real_mkdtemp(*args, **kwargs))
        created.append(path)
        return str(path)

    def interrupting_mkdir(path: Path, *args: object, **kwargs: object) -> None:
        if path.name == "hypothesis":
            raise KeyboardInterrupt
        real_mkdir(path, *args, **kwargs)

    monkeypatch.setattr(runner.tempfile, "mkdtemp", recording_mkdtemp)
    monkeypatch.setattr(Path, "mkdir", interrupting_mkdir)

    with pytest.raises(KeyboardInterrupt):
        with runner.isolated_coverage_environment():
            raise AssertionError("setup must not yield")

    assert len(created) == 2
    assert all(not path.exists() for path in created)


def test_pytest_transport_redacts_and_bounds_all_output(capsys) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    local_path = str(ROOT / "private-pytest-diagnostic")

    result = runner._run_pytest_bounded(
        (
            sys.executable,
            "-c",
            "import sys; "
            f"sys.stdout.write({local_path!r} + 'x'*200000); "
            f"sys.stderr.write({local_path!r} + 'y'*200000)",
        ),
        cwd=ROOT,
        env=os.environ,
    )

    assert result.returncode == 0
    captured = capsys.readouterr()
    assert local_path not in captured.err
    assert captured.out == ""
    assert captured.err.count("sha256=") == 2
    assert len(captured.err) < 600


def test_coverage_runner_cleans_temp_directory_when_interrupted(
    monkeypatch: MonkeyPatch,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    captured: dict[str, Path] = {}
    monkeypatch.setattr(runner, "_assert_runtime_matches_lock", lambda lock: None)

    def fake_run(command: tuple[str, ...], **kwargs: object) -> subprocess.CompletedProcess[str]:
        del command
        environment = kwargs["env"]
        assert isinstance(environment, dict)
        captured["coverage_file"] = Path(str(environment["COVERAGE_FILE"]))
        raise KeyboardInterrupt

    monkeypatch.setattr(runner, "_run_pytest_bounded", fake_run)

    try:
        try:
            _run_unit_coverage_main(runner)
        except KeyboardInterrupt:
            pass
        else:
            raise AssertionError("KeyboardInterrupt was not propagated")
    finally:
        pass
    assert not captured["coverage_file"].parent.exists()


def test_coverage_runner_propagates_checker_failure_and_cleans_report(
    monkeypatch: MonkeyPatch,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    coverage_file: Path | None = None
    coverage_json: Path | None = None
    monkeypatch.setattr(runner, "_assert_runtime_matches_lock", lambda lock: None)

    def fake_run(command: tuple[str, ...], **kwargs: object) -> runner._PytestResult:
        nonlocal coverage_file
        nonlocal coverage_json
        environment = kwargs["env"]
        assert isinstance(environment, dict)
        coverage_file = Path(str(environment["COVERAGE_FILE"]))
        coverage_json = Path(
            next(
                argument for argument in command if argument.startswith("--cov-report=json:")
            ).removeprefix("--cov-report=json:")
        )
        coverage_json.write_text("{}", encoding="utf-8")
        return runner._PytestResult(returncode=0, timed_out=False)

    def fake_checker(
        command: tuple[str, ...], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        del kwargs
        return subprocess.CompletedProcess(
            command,
            9,
            stdout='{"passed":false}\n',
            stderr="",
        )

    monkeypatch.setattr(runner, "_run_pytest_bounded", fake_run)
    monkeypatch.setattr(runner, "_run_checker_bounded", fake_checker)

    assert _run_unit_coverage_main(runner) == 2
    assert coverage_file is not None
    assert not coverage_file.parent.exists()
    assert coverage_json is not None
    assert not coverage_json.parent.exists()


def test_coverage_runner_rejects_temp_root_inside_repository_before_subprocess(
    monkeypatch: MonkeyPatch,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    subprocess_called = False
    monkeypatch.setattr(runner, "_assert_runtime_matches_lock", lambda lock: None)

    def fake_run(command: tuple[str, ...], **kwargs: object) -> subprocess.CompletedProcess[str]:
        nonlocal subprocess_called
        del command, kwargs
        subprocess_called = True
        raise AssertionError("subprocess must not run for an unsafe temp root")

    monkeypatch.setattr(runner.tempfile, "gettempdir", lambda: str(ROOT / "temp"))
    monkeypatch.setattr(runner, "_run_pytest_bounded", fake_run)

    assert _run_unit_coverage_main(runner) == 2
    assert subprocess_called is False
    assert not (ROOT / "coverage.json").exists()


def test_coverage_runner_environment_is_inherited_and_writable_without_temp_vars(
    monkeypatch: MonkeyPatch,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    for name in ("TEMP", "TMP", "TMPDIR", "RUNNER_TEMP", "COVERAGE_FILE"):
        monkeypatch.delenv(name, raising=False)
    repo_residue_before = sorted(ROOT.glob(".coverage*"))
    script = """
import json
import os
from pathlib import Path
from coverage import Coverage

coverage = Coverage()
coverage.start()
exec(
    compile(
        "probe_value = 1",
        str(Path.cwd() / "src" / "hsconfig" / "_coverage_probe.py"),
        "exec",
    ),
    {},
)
coverage.stop()
coverage.save()
configured = Path(coverage.config.data_file).resolve()
actual = Path(coverage.get_data().data_filename()).resolve()
evidence = {
    "environment": os.environ["COVERAGE_FILE"],
    "configured": str(configured),
    "actual": str(actual),
    "actual_exists_before_erase": actual.is_file(),
}
coverage.erase()
evidence["actual_exists_after_erase"] = actual.exists()
print(json.dumps(evidence, sort_keys=True))
"""

    with runner.isolated_coverage_environment() as run:
        coverage_file = Path(run.environment["COVERAGE_FILE"])
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=ROOT,
            env=run.environment,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        assert coverage_file.parent.is_dir()

    assert result.returncode == 0, result.stderr
    evidence = json.loads(result.stdout)
    assert Path(evidence["environment"]) == coverage_file
    assert Path(evidence["configured"]) == coverage_file
    assert Path(evidence["actual"]).parent == coverage_file.parent
    assert evidence["actual_exists_before_erase"] is True
    assert evidence["actual_exists_after_erase"] is False
    assert not coverage_file.parent.exists()
    assert ROOT not in coverage_file.parents
    assert sorted(ROOT.glob(".coverage*")) == repo_residue_before


def test_checker_emits_deterministic_success_json_and_exact_critical_order(
    tmp_path: Path,
) -> None:
    coverage_path = _write_coverage(tmp_path, _coverage_payload())

    first = _run_checker(coverage_path)
    second = _run_checker(coverage_path)

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert first.stdout == second.stdout
    assert first.stderr == second.stderr == ""
    report = _read_report(first)
    assert report["passed"] is True
    assert report["global_branch_percent"] == 96.0
    assert report["global_minimum"] == 89.0
    assert report["target_met"] is True
    rows = report["critical_modules"]
    assert [row["module"] for row in rows] == CRITICAL_MODULES
    assert all(row["statement_percent"] == 100.0 for row in rows)
    assert all(row["branch_percent"] == 100.0 for row in rows)
    assert all(row["missing_lines"] == [] for row in rows)
    assert all(row["missing_branches"] == [] for row in rows)
    assert report["errors"] == []


@pytest.mark.skipif(os.name != "nt", reason="Windows Coverage.py path regression")
def test_checker_rebases_bound_absolute_windows_coverage_paths(
    tmp_path: Path,
) -> None:
    payload = _coverage_payload()
    files = payload["files"]
    assert isinstance(files, dict)
    payload["files"] = {
        str((ROOT / module).resolve(strict=True)): row
        for module, row in files.items()
    }
    coverage_path = _write_coverage(tmp_path, payload)

    result = _run_checker(coverage_path)

    assert result.returncode == 0, result.stderr
    report = _read_report(result)
    assert report["passed"] is True
    assert [row["module"] for row in report["critical_modules"]] == CRITICAL_MODULES


def test_checker_rejects_absolute_coverage_path_outside_bound_source(
    tmp_path: Path,
) -> None:
    payload = _coverage_payload()
    files = payload["files"]
    assert isinstance(files, dict)
    module, row = next(iter(files.items()))
    del files[module]
    foreign = tmp_path / "foreign.py"
    foreign.write_text("pass\n", encoding="utf-8")
    files[str(foreign.resolve(strict=True))] = row
    coverage_path = _write_coverage(tmp_path, payload)

    result = _run_checker(coverage_path)

    assert result.returncode == 2
    assert _read_report(result)["errors"] == [
        "malformed coverage data: production module inventory differs"
    ]


@pytest.mark.skipif(os.name != "nt", reason="Windows Coverage.py path regression")
def test_checker_rejects_relative_and_absolute_coverage_path_collision(
    tmp_path: Path,
) -> None:
    payload = _coverage_payload()
    files = payload["files"]
    assert isinstance(files, dict)
    module = next(iter(files))
    files[str((ROOT / module).resolve(strict=True))] = files[module]
    coverage_path = _write_coverage(tmp_path, payload)

    result = _run_checker(coverage_path)

    assert result.returncode == 2
    assert _read_report(result)["errors"] == [
        "malformed coverage data: production module inventory differs"
    ]


@pytest.mark.skipif(os.name != "nt", reason="Windows junction regression")
def test_checker_rejects_external_junction_alias_to_bound_source(
    tmp_path: Path,
) -> None:
    payload = _coverage_payload()
    files = payload["files"]
    assert isinstance(files, dict)
    module, row = next(iter(files.items()))
    del files[module]
    alias = tmp_path / "source-alias"
    _create_directory_redirect(alias, ROOT / "src" / "hsconfig")
    files[str(alias / Path(module).name)] = row
    coverage_path = _write_coverage(tmp_path, payload)

    result = _run_checker(coverage_path)

    assert result.returncode == 2
    assert _read_report(result)["errors"] == [
        "malformed coverage data: production module inventory differs"
    ]


def test_checker_rejects_foreign_absolute_path_without_filesystem_access(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    checker = importlib.import_module("scripts.check_coverage_contract")

    def forbidden(*_args, **_kwargs):
        raise AssertionError("foreign coverage path was accessed")

    monkeypatch.setattr(Path, "lstat", forbidden)
    monkeypatch.setattr(Path, "resolve", forbidden)

    with pytest.raises(
        checker.CoverageDataError,
        match="production module inventory differs",
    ):
        checker._normalized_coverage_module(str(tmp_path / "foreign.py"))


def test_checker_fails_closed_for_missing_input(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing.json"

    result = _run_checker(missing_path)

    assert result.returncode != 0
    report = _read_report(result)
    assert report["passed"] is False
    assert report["errors"] == [f"coverage file does not exist: {missing_path}"]


def test_checker_fails_closed_for_malformed_json(tmp_path: Path) -> None:
    coverage_path = tmp_path / "coverage.json"
    coverage_path.write_text("{not-json", encoding="utf-8")

    result = _run_checker(coverage_path)

    assert result.returncode != 0
    report = _read_report(result)
    assert report["passed"] is False
    assert len(report["errors"]) == 1
    assert report["errors"][0].startswith("malformed coverage JSON:")


def test_checker_fails_closed_for_malformed_coverage_schema(tmp_path: Path) -> None:
    coverage_path = _write_coverage(tmp_path, {"files": []})

    result = _run_checker(coverage_path)

    assert result.returncode != 0
    report = _read_report(result)
    assert report["passed"] is False
    assert report["errors"] == [
        "malformed coverage data: meta must be an object"
    ]


def test_checker_fails_closed_when_a_critical_module_is_missing(
    tmp_path: Path,
) -> None:
    payload = _coverage_payload()
    del payload["files"][CRITICAL_MODULES[0]]
    coverage_path = _write_coverage(tmp_path, payload)

    result = _run_checker(coverage_path)

    assert result.returncode != 0
    report = _read_report(result)
    assert report["passed"] is False
    assert report["errors"] == [
        "malformed coverage data: production module inventory differs"
    ]


def test_checker_fails_closed_when_any_production_module_is_missing(
    tmp_path: Path,
) -> None:
    payload = _coverage_payload()
    module = next(
        path for path in PRODUCTION_MODULES if path not in CRITICAL_MODULES
    )
    del payload["files"][module]
    coverage_path = _write_coverage(tmp_path, payload)

    result = _run_checker(coverage_path)

    assert result.returncode == 2
    report = _read_report(result)
    assert report["passed"] is False
    assert report["errors"] == [
        "malformed coverage data: production module inventory differs"
    ]


def test_checker_fails_closed_when_global_totals_do_not_match_file_summaries(
    tmp_path: Path,
) -> None:
    payload = _coverage_payload()
    payload["totals"]["num_branches"] += 2
    payload["totals"]["missing_branches"] += 2
    coverage_path = _write_coverage(tmp_path, payload)

    result = _run_checker(coverage_path)

    assert result.returncode == 2
    report = _read_report(result)
    assert report["passed"] is False
    assert report["errors"] == [
        "malformed coverage data: totals do not match production file summaries"
    ]


def test_checker_rejects_global_branch_coverage_below_minimum(
    tmp_path: Path,
) -> None:
    coverage_path = _write_coverage(
        tmp_path,
        _coverage_payload(global_covered_branches=8899, global_num_branches=10000),
    )

    result = _run_checker(coverage_path)

    assert result.returncode != 0
    report = _read_report(result)
    assert report["global_branch_percent"] == 88.99
    assert report["passed"] is False
    assert report["errors"] == [
        "global branch coverage 88.99% is below required 89.00%"
    ]


def test_checker_compares_unrounded_global_branch_coverage_to_minimum(
    tmp_path: Path,
) -> None:
    coverage_path = _write_coverage(
        tmp_path,
        _coverage_payload(global_covered_branches=17799, global_num_branches=20000),
    )

    result = _run_checker(coverage_path)

    assert result.returncode != 0
    report = _read_report(result)
    assert report["global_branch_percent"] == 89.0
    assert report["passed"] is False
    assert report["errors"] == [
        "global branch coverage 89.00% is below required 89.00%"
    ]


def test_checker_rejects_incomplete_critical_statements(tmp_path: Path) -> None:
    payload = _coverage_payload()
    module = CRITICAL_MODULES[3]
    payload["files"][module] = _file_coverage(
        covered_lines=1,
        num_statements=2,
        missing_lines=[17],
    )
    _refresh_coverage_totals(payload)
    coverage_path = _write_coverage(tmp_path, payload)

    result = _run_checker(coverage_path)

    assert result.returncode != 0
    report = _read_report(result)
    row = report["critical_modules"][3]
    assert row["statement_percent"] == 50.0
    assert row["missing_lines"] == [17]
    assert report["errors"] == [
        f"critical module {module} statement coverage 50.00%; missing lines: [17]"
    ]


def test_checker_rejects_incomplete_critical_branches(tmp_path: Path) -> None:
    payload = _coverage_payload()
    module = CRITICAL_MODULES[5]
    payload["files"][module] = _file_coverage(
        covered_branches=1,
        num_branches=2,
        missing_branches=[[23, 27]],
    )
    _refresh_coverage_totals(payload)
    coverage_path = _write_coverage(tmp_path, payload)

    result = _run_checker(coverage_path)

    assert result.returncode != 0
    report = _read_report(result)
    row = report["critical_modules"][5]
    assert row["branch_percent"] == 50.0
    assert row["missing_branches"] == [[23, 27]]
    assert report["errors"] == [
        f"critical module {module} branch coverage 50.00%; "
        "missing branches: [[23, 27]]"
    ]


def test_checker_rejects_incomplete_statements_that_display_as_100_percent(
    tmp_path: Path,
) -> None:
    payload = _coverage_payload()
    module = CRITICAL_MODULES[0]
    payload["files"][module] = _file_coverage(
        covered_lines=19999,
        num_statements=20000,
        missing_lines=[17],
    )
    _refresh_coverage_totals(payload)
    coverage_path = _write_coverage(tmp_path, payload)

    result = _run_checker(coverage_path)

    assert result.returncode != 0
    report = _read_report(result)
    row = report["critical_modules"][0]
    assert row["statement_percent"] == 100.0
    assert report["errors"] == [
        f"critical module {module} statement coverage 100.00%; missing lines: [17]"
    ]


def test_checker_rejects_incomplete_branches_that_display_as_100_percent(
    tmp_path: Path,
) -> None:
    payload = _coverage_payload()
    module = CRITICAL_MODULES[1]
    payload["files"][module] = _file_coverage(
        covered_branches=19999,
        num_branches=20000,
        missing_branches=[[23, 27]],
    )
    _refresh_coverage_totals(payload)
    coverage_path = _write_coverage(tmp_path, payload)

    result = _run_checker(coverage_path)

    assert result.returncode != 0
    report = _read_report(result)
    row = report["critical_modules"][1]
    assert row["branch_percent"] == 100.0
    assert report["errors"] == [
        f"critical module {module} branch coverage 100.00%; "
        "missing branches: [[23, 27]]"
    ]


def test_checker_rejects_complete_counts_with_nonempty_missing_evidence(
    tmp_path: Path,
) -> None:
    payload = _coverage_payload()
    module = CRITICAL_MODULES[2]
    payload["files"][module] = _file_coverage(
        missing_lines=[17],
        missing_branches=[[23, 27]],
    )
    coverage_path = _write_coverage(tmp_path, payload)

    result = _run_checker(coverage_path)

    assert result.returncode != 0
    report = _read_report(result)
    assert report["critical_modules"] == []
    assert report["errors"] == [
        "malformed coverage data: "
        f"files[{module}].missing_lines count does not match summary.missing_lines"
    ]


def test_checker_rejects_incomplete_counts_without_missing_evidence(
    tmp_path: Path,
) -> None:
    payload = _coverage_payload()
    module = CRITICAL_MODULES[4]
    payload["files"][module] = _file_coverage(
        covered_lines=1,
        num_statements=2,
    )
    coverage_path = _write_coverage(tmp_path, payload)

    result = _run_checker(coverage_path)

    assert result.returncode != 0
    report = _read_report(result)
    assert report["critical_modules"] == []
    assert report["errors"] == [
        "malformed coverage data: "
        f"files[{module}].missing_lines count does not match summary.missing_lines"
    ]


def test_checker_rejects_inconsistent_global_missing_branch_total(
    tmp_path: Path,
) -> None:
    payload = _coverage_payload(global_covered_branches=96, global_num_branches=100)
    payload["totals"]["missing_branches"] = 3
    coverage_path = _write_coverage(tmp_path, payload)

    result = _run_checker(coverage_path)

    assert result.returncode != 0
    report = _read_report(result)
    assert report["critical_modules"] == []
    assert report["errors"] == [
        "malformed coverage data: "
        "totals.missing_branches is inconsistent with branch counts"
    ]


def test_checker_rejects_duplicate_critical_missing_lines(tmp_path: Path) -> None:
    payload = _coverage_payload()
    module = CRITICAL_MODULES[6]
    payload["files"][module] = _file_coverage(
        covered_lines=0,
        num_statements=2,
        missing_lines=[17, 17],
    )
    coverage_path = _write_coverage(tmp_path, payload)

    result = _run_checker(coverage_path)

    assert result.returncode != 0
    report = _read_report(result)
    assert report["critical_modules"] == []
    assert report["errors"] == [
        "malformed coverage data: "
        f"files[{module}].missing_lines must not contain duplicates"
    ]


def test_checker_rejects_duplicate_critical_missing_branches(tmp_path: Path) -> None:
    payload = _coverage_payload()
    module = CRITICAL_MODULES[7]
    payload["files"][module] = _file_coverage(
        covered_branches=0,
        num_branches=2,
        missing_branches=[[23, 27], [23, 27]],
    )
    coverage_path = _write_coverage(tmp_path, payload)

    result = _run_checker(coverage_path)

    assert result.returncode != 0
    report = _read_report(result)
    assert report["critical_modules"] == []
    assert report["errors"] == [
        "malformed coverage data: "
        f"files[{module}].missing_branches must not contain duplicate pairs"
    ]


def test_checker_reports_95_percent_target_honestly_without_failing(
    tmp_path: Path,
) -> None:
    coverage_path = _write_coverage(
        tmp_path,
        _coverage_payload(global_covered_branches=94, global_num_branches=100),
    )

    result = _run_checker(coverage_path)

    assert result.returncode == 0, result.stderr
    report = _read_report(result)
    assert report["passed"] is True
    assert report["global_branch_percent"] == 94.0
    assert report["global_minimum"] == 89.0
    assert report["target_met"] is False


def test_checker_compares_unrounded_global_branch_coverage_to_target(
    tmp_path: Path,
) -> None:
    coverage_path = _write_coverage(
        tmp_path,
        _coverage_payload(global_covered_branches=18999, global_num_branches=20000),
    )

    result = _run_checker(coverage_path)

    assert result.returncode == 0, result.stderr
    report = _read_report(result)
    assert report["global_branch_percent"] == 95.0
    assert report["passed"] is True
    assert report["target_met"] is False

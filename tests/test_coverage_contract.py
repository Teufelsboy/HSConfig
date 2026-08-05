from __future__ import annotations

import importlib
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import sysconfig
import time
import tomllib
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
    return {
        "meta": {
            "format": 3,
            "version": "7.10.0",
            "branch_coverage": True,
            "show_contexts": False,
        },
        "files": {module: _file_coverage() for module in CRITICAL_MODULES},
        "totals": {
            "covered_lines": 100,
            "num_statements": 100,
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


def _checker_document(*, passed: bool = True) -> dict[str, object]:
    percent = 96.0 if passed else 89.0
    return {
        "passed": passed,
        "global_branch_percent": percent,
        "global_covered_branches": 96 if passed else 89,
        "global_num_branches": 100,
        "global_minimum": 90.0,
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
    passed = percent >= 90.0
    document = _checker_document(passed=passed)
    document["global_branch_percent"] = percent
    document["global_covered_branches"] = round(percent * 100)
    document["global_num_branches"] = 10_000
    document["target_met"] = percent >= 95.0
    return document


@pytest.mark.parametrize(
    ("covered", "total", "returncode", "passed", "target_met"),
    ((17999, 20000, 1, False, False), (18999, 20000, 0, True, False)),
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
    assert config["tool"]["coverage"]["report"]["fail_under"] == 90


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

    def fake_run(command: tuple[str, ...], **kwargs: object) -> subprocess.CompletedProcess[str]:
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
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    def fake_checker(
        command: tuple[str, ...], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        checker_commands.append(command)
        assert kwargs["input_bytes"] == b"{}"
        return subprocess.CompletedProcess(command, 0, stdout=json.dumps(_checker_document()), stderr="")

    monkeypatch.setattr(runner, "_run_pytest_bounded", fake_run)
    monkeypatch.setattr(runner, "_run_checker_bounded", fake_checker)

    for _ in range(2):
        assert runner.main() == 0
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


def test_coverage_runner_propagates_failure_and_cleans_temp_directory(
    monkeypatch: MonkeyPatch,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    captured: dict[str, object] = {}
    calls = 0
    monkeypatch.setattr(runner, "_assert_runtime_matches_lock", lambda lock: None)

    def fake_run(command: tuple[str, ...], **kwargs: object) -> subprocess.CompletedProcess[str]:
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
        captured["coverage_json"].write_text("failed-run-report", encoding="utf-8")
        return subprocess.CompletedProcess(command, 7, stdout="", stderr="")

    monkeypatch.setattr(runner, "_run_pytest_bounded", fake_run)

    assert runner.main() == 2
    assert calls == 1
    coverage_file = captured["coverage_file"]
    assert isinstance(coverage_file, Path)
    assert not coverage_file.parent.exists()
    assert not (ROOT / "coverage.json").exists()


def test_coverage_runner_emits_one_failure_json_for_pytest_failure(
    monkeypatch: MonkeyPatch,
    capsys,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    monkeypatch.setattr(runner, "_assert_runtime_matches_lock", lambda lock: None)

    def fake_run(command: tuple[str, ...], **kwargs: object) -> subprocess.CompletedProcess[str]:
        assert command[1:3] == ("-m", "pytest")
        return subprocess.CompletedProcess(command, 7, stdout="", stderr="")

    monkeypatch.setattr(runner, "_run_pytest_bounded", fake_run)

    assert runner.main() == 2
    captured = capsys.readouterr()
    assert captured.out.count("\n") == 1
    assert json.loads(captured.out) == {
        "critical_modules": [],
            "errors": ["pytest coverage execution failed"],
            "global_branch_percent": None,
            "global_covered_branches": None,
            "global_num_branches": None,
        "global_minimum": 90.0,
        "passed": False,
        "returncode": 2,
        "target_met": False,
    }
    assert captured.err == ""


def test_coverage_runner_forwards_checker_failure_as_one_contradiction_free_json(
    monkeypatch: MonkeyPatch,
    capsys,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    checker_document = _checker_document(passed=False)
    monkeypatch.setattr(runner, "_assert_runtime_matches_lock", lambda lock: None)

    def fake_run(command: tuple[str, ...], **kwargs: object) -> subprocess.CompletedProcess[str]:
        assert command[1:3] == ("-m", "pytest")
        report = Path(
            next(
                argument for argument in command if argument.startswith("--cov-report=json:")
            ).removeprefix("--cov-report=json:")
        )
        report.write_text("{}", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

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

    assert runner.main() == 1
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

    def fake_run(command: tuple[str, ...], **kwargs: object) -> subprocess.CompletedProcess[str]:
        del command, kwargs
        raise OSError("local path must not leak")

    monkeypatch.setattr(runner, "_run_pytest_bounded", fake_run)

    assert runner.main() == 2
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

    with pytest.raises(runner.RuntimeLockError, match="duplicate"):
        runner._assert_runtime_matches_lock(lock)


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


@pytest.mark.skipif(os.name != "nt", reason="Windows pip launcher contract")
def test_distribution_origin_accepts_bound_pip_interpreter_versioned_launcher(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    versioned_launcher = (
        f"pip{sys.version_info.major}.{sys.version_info.minor}.exe"
    )
    distribution, artifact, _direct_url = _bound_nonlocal_distribution(
        tmp_path,
        monkeypatch,
        console_scripts=("pip", "pip3"),
        runtime_scripts=("pip.exe", "pip3.exe", versioned_launcher),
    )

    runner._assert_distribution_origin(
        distribution,
        local_project=False,
        artifact=artifact,
    )


@pytest.mark.skipif(os.name != "nt", reason="Windows pip launcher contract")
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
    launcher = {
        "wrong-minor": f"pip{major}.{minor + 1}.exe",
        "wrong-major": f"pip{major + 1}.{minor}.exe",
        "pip3.10": "pip3.10.exe" if (major, minor) != (3, 10) else "pip3.9.exe",
        "pip4": "pip4.exe",
        "foreign-name": f"not-pip{major}.{minor}.exe",
        "foreign-path": f"../Foreign/pip{major}.{minor}.exe",
        "missing-pip3-entry-point": f"pip{major}.{minor}.exe",
        "non-pip-artifact": f"pip{major}.{minor}.exe",
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
        runtime_scripts=("pip.exe", "pip3.exe", launcher),
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
    manifest = tmp_path / "bootstrap" / "manifest.json"
    document = {
        "schema_version": 1,
        "python_minor": f"{sys.version_info.major}.{sys.version_info.minor}",
        "repository": str(repository.resolve(strict=True)),
        "commit_oid": artifact["_commit_oid"],
        "tree_oid": artifact["_tree_oid"],
        "environment_root": str(Path(sys.prefix).resolve(strict=True)),
        "lock_sha256": hashlib.sha256(lock.read_bytes()).hexdigest(),
        "sentinel_sha256": hashlib.sha256(sentinel.encode("ascii")).hexdigest(),
        "artifacts": [],
        "local_project": {
            key: artifact[key]
            for key in ("name", "version", "wheel_path", "sha256", "files")
        },
    }
    source = json.dumps(document, separators=(",", ":"), sort_keys=True).encode("utf-8")
    manifest.write_bytes(source)
    monkeypatch.setenv("HSCONFIG_RELEASE_GATE_BOOTSTRAP_SENTINEL", sentinel)
    monkeypatch.setenv("HSCONFIG_RUNTIME_MANIFEST", str(manifest))
    monkeypatch.setenv("HSCONFIG_RUNTIME_MANIFEST_SHA256", hashlib.sha256(source).hexdigest())
    return lock


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

    def record_bound_git_output(*arguments: str, maximum_bytes: int) -> bytes:
        calls.append(arguments)
        return original_bound_git_output(*arguments, maximum_bytes=maximum_bytes)

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

    with pytest.raises(runner.RuntimeLockError, match="repository|index"):
        runner._load_runtime_manifest(lock, {})


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
    artifact = {"_commit_oid": "a" * 40, "_tree_oid": "b" * 40}

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
            "global_minimum": 90.0,
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
        (89.99, 1, False),
        (90.0, 0, False),
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

    with pytest.raises(runner.RuntimeLockError, match="origin"):
        runner._assert_runtime_matches_lock(lock)


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
        runner._checker_command(),
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

    assert result.returncode < 0
    time.sleep(3)
    assert not marker.exists()


def test_coverage_cleanup_preserves_replacement_and_removes_owned_root(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    monkeypatch.setattr(runner.tempfile, "gettempdir", lambda: str(tmp_path))
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


def test_coverage_environment_setup_is_failure_atomic_for_baseexception(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    monkeypatch.setattr(runner.tempfile, "gettempdir", lambda: str(tmp_path))
    real_mkdtemp = runner.tempfile.mkdtemp
    real_mkdir = Path.mkdir
    created: Path | None = None

    def recording_mkdtemp(*args: object, **kwargs: object) -> str:
        nonlocal created
        created = Path(real_mkdtemp(*args, **kwargs))
        return str(created)

    def interrupting_mkdir(path: Path, *args: object, **kwargs: object) -> None:
        if path.name == "pytest-temp":
            raise KeyboardInterrupt
        real_mkdir(path, *args, **kwargs)

    monkeypatch.setattr(runner.tempfile, "mkdtemp", recording_mkdtemp)
    monkeypatch.setattr(Path, "mkdir", interrupting_mkdir)

    with pytest.raises(KeyboardInterrupt):
        with runner.isolated_coverage_environment():
            raise AssertionError("setup must not yield")

    assert created is not None and not created.exists()


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
            runner.main()
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

    def fake_run(command: tuple[str, ...], **kwargs: object) -> subprocess.CompletedProcess[str]:
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
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

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

    assert runner.main() == 2
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

    assert runner.main() == 2
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
    assert report["global_minimum"] == 90.0
    assert report["target_met"] is True
    rows = report["critical_modules"]
    assert [row["module"] for row in rows] == CRITICAL_MODULES
    assert all(row["statement_percent"] == 100.0 for row in rows)
    assert all(row["branch_percent"] == 100.0 for row in rows)
    assert all(row["missing_lines"] == [] for row in rows)
    assert all(row["missing_branches"] == [] for row in rows)
    assert report["errors"] == []


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
        f"critical module missing from coverage data: {CRITICAL_MODULES[0]}"
    ]


def test_checker_rejects_global_branch_coverage_below_minimum(
    tmp_path: Path,
) -> None:
    coverage_path = _write_coverage(
        tmp_path,
        _coverage_payload(global_covered_branches=8999, global_num_branches=10000),
    )

    result = _run_checker(coverage_path)

    assert result.returncode != 0
    report = _read_report(result)
    assert report["global_branch_percent"] == 89.99
    assert report["passed"] is False
    assert report["errors"] == [
        "global branch coverage 89.99% is below required 90.00%"
    ]


def test_checker_compares_unrounded_global_branch_coverage_to_minimum(
    tmp_path: Path,
) -> None:
    coverage_path = _write_coverage(
        tmp_path,
        _coverage_payload(global_covered_branches=17999, global_num_branches=20000),
    )

    result = _run_checker(coverage_path)

    assert result.returncode != 0
    report = _read_report(result)
    assert report["global_branch_percent"] == 90.0
    assert report["passed"] is False
    assert report["errors"] == [
        "global branch coverage 90.00% is below required 90.00%"
    ]


def test_checker_rejects_incomplete_critical_statements(tmp_path: Path) -> None:
    payload = _coverage_payload()
    module = CRITICAL_MODULES[3]
    payload["files"][module] = _file_coverage(
        covered_lines=1,
        num_statements=2,
        missing_lines=[17],
    )
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
    assert report["global_minimum"] == 90.0
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

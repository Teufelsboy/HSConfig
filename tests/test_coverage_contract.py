from __future__ import annotations

import importlib
import json
from pathlib import Path
import subprocess
import sys
import tomllib

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
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    calls: list[dict[str, object]] = []
    checker_commands: list[list[str]] = []
    coverage_json = ROOT / "coverage.json"
    monkeypatch.setenv(
        "PYTEST_ADDOPTS",
        "--no-cov --cov-fail-under=0 --cov-config=other.toml",
    )

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if command[1:3] != ["-m", "pytest"]:
            checker_commands.append(command)
            return subprocess.CompletedProcess(command, 0)
        environment = kwargs["env"]
        assert isinstance(environment, dict)
        coverage_file = Path(str(environment["COVERAGE_FILE"]))
        assert not coverage_json.exists()
        coverage_json.write_text("fresh", encoding="utf-8")
        calls.append(
            {
                "command": command,
                "cwd": kwargs["cwd"],
                "coverage_file": coverage_file,
                "directory_existed": coverage_file.parent.is_dir(),
                "pytest_addopts_present": "PYTEST_ADDOPTS" in environment,
            }
        )
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    try:
        for _ in range(2):
            coverage_json.write_text("stale", encoding="utf-8")
            assert runner.main() == 0
            assert not coverage_json.exists()
    finally:
        coverage_json.unlink(missing_ok=True)

    expected_command = [
        sys.executable,
        "-m",
        "pytest",
        "--cov=src/hsconfig",
        "--cov-branch",
        "--cov-config=pyproject.toml",
        "--cov-fail-under=90",
        "--cov-report=json:coverage.json",
        "--cov-report=term-missing",
        "-p",
        "no:cacheprovider",
    ]
    assert [call["command"] for call in calls] == [expected_command, expected_command]
    expected_checker = [
        sys.executable,
        str(ROOT / "scripts" / "check_coverage_contract.py"),
        str(coverage_json),
    ]
    assert checker_commands == [expected_checker, expected_checker]
    assert all(call["cwd"] == ROOT for call in calls)
    coverage_files = [call["coverage_file"] for call in calls]
    assert coverage_files[0] != coverage_files[1]
    assert all(path.is_absolute() for path in coverage_files)
    assert all(ROOT not in path.parents for path in coverage_files)
    assert all(call["directory_existed"] is True for call in calls)
    assert all(call["pytest_addopts_present"] is False for call in calls)
    assert all(not path.parent.exists() for path in coverage_files)


def test_coverage_runner_propagates_failure_and_cleans_temp_directory(
    monkeypatch: MonkeyPatch,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    captured: dict[str, object] = {}
    coverage_json = ROOT / "coverage.json"
    calls = 0

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        nonlocal calls
        calls += 1
        assert command[1:3] == ["-m", "pytest"]
        assert not coverage_json.exists()
        environment = kwargs["env"]
        assert isinstance(environment, dict)
        captured["coverage_file"] = Path(str(environment["COVERAGE_FILE"]))
        coverage_json.write_text("failed-run-report", encoding="utf-8")
        return subprocess.CompletedProcess(command, 7)

    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    try:
        coverage_json.write_text("stale", encoding="utf-8")
        assert runner.main() == 7
        assert not coverage_json.exists()
    finally:
        coverage_json.unlink(missing_ok=True)
    assert calls == 1
    coverage_file = captured["coverage_file"]
    assert isinstance(coverage_file, Path)
    assert not coverage_file.parent.exists()


def test_coverage_runner_cleans_temp_directory_when_interrupted(
    monkeypatch: MonkeyPatch,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    captured: dict[str, Path] = {}
    coverage_json = ROOT / "coverage.json"

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        del command
        environment = kwargs["env"]
        assert isinstance(environment, dict)
        captured["coverage_file"] = Path(str(environment["COVERAGE_FILE"]))
        coverage_json.write_text("partial-report", encoding="utf-8")
        raise KeyboardInterrupt

    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    try:
        try:
            runner.main()
        except KeyboardInterrupt:
            pass
        else:
            raise AssertionError("KeyboardInterrupt was not propagated")
        assert not coverage_json.exists()
    finally:
        coverage_json.unlink(missing_ok=True)
    assert not captured["coverage_file"].parent.exists()


def test_coverage_runner_propagates_checker_failure_and_cleans_report(
    monkeypatch: MonkeyPatch,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    coverage_json = ROOT / "coverage.json"
    commands: list[list[str]] = []
    coverage_file: Path | None = None

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        nonlocal coverage_file
        commands.append(command)
        if command[1:3] == ["-m", "pytest"]:
            environment = kwargs["env"]
            assert isinstance(environment, dict)
            coverage_file = Path(str(environment["COVERAGE_FILE"]))
            coverage_json.write_text("fresh", encoding="utf-8")
            return subprocess.CompletedProcess(command, 0)
        assert coverage_json.is_file()
        return subprocess.CompletedProcess(command, 9)

    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    try:
        assert runner.main() == 9
        assert not coverage_json.exists()
    finally:
        coverage_json.unlink(missing_ok=True)
    assert len(commands) == 2
    assert coverage_file is not None
    assert not coverage_file.parent.exists()


def test_coverage_runner_rejects_temp_root_inside_repository_before_subprocess(
    monkeypatch: MonkeyPatch,
) -> None:
    runner = importlib.import_module("scripts.run_coverage_gate")
    coverage_json = ROOT / "coverage.json"
    subprocess_called = False

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        nonlocal subprocess_called
        del command, kwargs
        subprocess_called = True
        raise AssertionError("subprocess must not run for an unsafe temp root")

    monkeypatch.setattr(runner.tempfile, "gettempdir", lambda: str(ROOT / "temp"))
    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    try:
        coverage_json.write_text("stale", encoding="utf-8")
        assert runner.main() == 2
        assert not coverage_json.exists()
    finally:
        coverage_json.unlink(missing_ok=True)
    assert subprocess_called is False


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

    with runner.isolated_coverage_environment() as environment:
        coverage_file = Path(environment["COVERAGE_FILE"])
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=ROOT,
            env=environment,
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

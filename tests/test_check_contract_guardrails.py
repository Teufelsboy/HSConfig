from __future__ import annotations

import subprocess
import sys

from scripts.check_contract_guardrails import guardrail_commands, run_guardrails


def test_guardrail_commands_include_skill_sync_sentinel_and_boundary_suite(tmp_path):
    repo_root = tmp_path
    skill_root = tmp_path / "skills"

    commands = guardrail_commands(repo_root, skill_root)
    names = [command.name for command in commands]

    assert names == [
        "installed skill sync",
        "contract spine sentinel",
        "focused contract boundary tests",
    ]
    assert commands[0].argv == (
        sys.executable,
        str(repo_root / "scripts" / "sync_installed_skill.py"),
        "--check",
        "--install-root",
        str(skill_root),
    )
    assert commands[1].argv == (
        sys.executable,
        "-m",
        "hsconfig.cli",
        "contract-spine-sentinel",
        "--json",
    )
    assert commands[2].argv[:3] == (sys.executable, "-m", "pytest")
    assert "tests/test_apply_authority_boundary.py" in commands[2].argv
    assert "tests/test_source_claim_family_registry.py" in commands[2].argv


def test_run_guardrails_stops_at_first_failure(tmp_path, capsys):
    repo_root = tmp_path
    skill_root = tmp_path / "skills"
    calls: list[tuple[str, ...]] = []

    def fake_runner(argv, **kwargs):
        calls.append(tuple(argv))
        return subprocess.CompletedProcess(argv, 7)

    exit_code = run_guardrails(repo_root, skill_root, runner=fake_runner)

    assert exit_code == 7
    assert len(calls) == 1
    captured = capsys.readouterr()
    assert "FAILED: installed skill sync" in captured.err


def test_run_guardrails_runs_all_commands_when_successful(tmp_path, capsys):
    repo_root = tmp_path
    skill_root = tmp_path / "skills"
    calls: list[tuple[str, ...]] = []

    def fake_runner(argv, **kwargs):
        calls.append(tuple(argv))
        return subprocess.CompletedProcess(argv, 0)

    exit_code = run_guardrails(repo_root, skill_root, runner=fake_runner)

    assert exit_code == 0
    assert len(calls) == 3
    captured = capsys.readouterr()
    assert "OK: installed skill sync" in captured.out
    assert "OK: contract spine sentinel" in captured.out
    assert "OK: focused contract boundary tests" in captured.out

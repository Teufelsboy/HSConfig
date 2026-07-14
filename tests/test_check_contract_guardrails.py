from __future__ import annotations

import subprocess
import sys

from scripts.check_contract_guardrails import guardrail_commands, run_guardrails


def test_guardrail_runner_includes_source_contract_v2_boundary_tests():
    from scripts.check_contract_guardrails import FOCUSED_CONTRACT_TESTS

    expected = {
        "tests/test_source_claim_family_registry.py",
        "tests/test_contract_spine_sentinel.py",
        "tests/test_contract_spine_sentinel_cli.py",
        "tests/test_contract_spine_sentinel_docs.py",
        "tests/test_apply_authority_boundary.py",
        "tests/test_no_second_gate_contract.py",
        "tests/test_semantic_runtime_negative_boundaries.py",
        "tests/test_universal_wild_no_block_matrix.py",
        "tests/test_operator_docs_contract_policy.py",
        "tests/test_docs_active_path.py",
        "tests/test_claim_kind_runtime_contract.py",
        "tests/test_card_behavior_router.py",
        "tests/test_mechanic_support.py",
        "tests/test_source_contract_conformance.py",
    }

    assert expected <= set(FOCUSED_CONTRACT_TESTS)


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

from __future__ import annotations

import subprocess
import sys

from scripts.check_contract_guardrails import guardrail_commands, run_guardrails


def test_focused_guardrail_tests_are_unique_and_present() -> None:
    from scripts.check_contract_guardrails import FOCUSED_CONTRACT_TESTS, REPO_ROOT

    assert len(FOCUSED_CONTRACT_TESTS) == len(set(FOCUSED_CONTRACT_TESTS))
    assert [
        relative
        for relative in FOCUSED_CONTRACT_TESTS
        if not REPO_ROOT.joinpath(relative).is_file()
    ] == []


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
        "tests/test_source_to_runtime_explainability.py",
        "tests/test_research_result_contract_sentinel.py",
    }

    assert expected <= set(FOCUSED_CONTRACT_TESTS)


def test_guardrail_runner_includes_contract_invariant_closure_tests():
    from scripts.check_contract_guardrails import FOCUSED_CONTRACT_TESTS

    required = {
        "tests/test_config_usefulness.py",
        "tests/test_operator_summary.py",
        "tests/test_no_default_only_semantic_archetype_matrix.py",
        "tests/test_shadowpriest_fresh_closure_proof.py",
        "tests/test_external_skill_bundle.py",
    }

    assert required <= set(FOCUSED_CONTRACT_TESTS)


def test_guardrail_runner_includes_direct_validate_and_apply_boundaries():
    from scripts.check_contract_guardrails import FOCUSED_CONTRACT_TESTS

    required = {
        "tests/test_validate_package.py",
        "tests/test_apply_gate.py",
        "tests/test_runtime_apply.py",
    }

    assert required <= set(FOCUSED_CONTRACT_TESTS)


def test_guardrail_commands_include_sentinel_and_boundary_suite(tmp_path):
    repo_root = tmp_path

    commands = guardrail_commands(repo_root)
    names = [command.name for command in commands]

    assert names == [
        "contract spine sentinel",
        "focused contract boundary tests",
    ]
    assert commands[0].argv == (
        sys.executable,
        "-m",
        "hsconfig.cli",
        "contract-spine-sentinel",
        "--repo-root",
        str(repo_root),
        "--json",
    )
    assert commands[1].argv[:3] == (sys.executable, "-m", "pytest")
    assert "tests/test_apply_authority_boundary.py" in commands[1].argv
    assert "tests/test_source_claim_family_registry.py" in commands[1].argv
    assert "tests/test_source_to_runtime_explainability.py" in commands[1].argv
    assert "tests/test_research_result_contract_sentinel.py" in commands[1].argv
    assert "tests/test_external_skill_bundle.py" in commands[1].argv
    assert "tests/test_validate_package.py" in commands[1].argv
    assert "tests/test_apply_gate.py" in commands[1].argv
    assert "tests/test_runtime_apply.py" in commands[1].argv


def test_focused_guardrail_pytest_disables_checkout_cacheprovider(tmp_path):
    commands = guardrail_commands(tmp_path)

    assert commands[1].argv[:6] == (
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "-p",
        "no:cacheprovider",
    )


def test_run_guardrails_stops_at_first_failure(tmp_path, capsys):
    repo_root = tmp_path
    calls: list[tuple[str, ...]] = []

    def fake_runner(argv, **kwargs):
        calls.append(tuple(argv))
        return subprocess.CompletedProcess(argv, 7)

    exit_code = run_guardrails(repo_root, runner=fake_runner)

    assert exit_code == 7
    assert len(calls) == 1
    captured = capsys.readouterr()
    assert "FAILED: contract spine sentinel" in captured.err


def test_run_guardrails_rejects_production_assert_before_commands(tmp_path, capsys):
    production_root = tmp_path / "src" / "hsconfig"
    production_root.mkdir(parents=True)
    invalid_module = production_root / "invalid_contract.py"
    invalid_module.write_text(
        "def validate_contract(value):\n"
        "    assert value\n",
        encoding="utf-8",
    )
    calls: list[tuple[str, ...]] = []

    def fake_runner(argv, **kwargs):
        calls.append(tuple(argv))
        return subprocess.CompletedProcess(argv, 0)

    exit_code = run_guardrails(
        tmp_path,
        runner=fake_runner,
    )

    assert exit_code != 0
    assert calls == []
    captured = capsys.readouterr()
    assert "FAILED: production assert guardrail" in captured.err
    assert "src/hsconfig/invalid_contract.py:2" in captured.err.replace("\\", "/")


def test_run_guardrails_runs_all_commands_when_successful(tmp_path, capsys):
    repo_root = tmp_path
    calls: list[tuple[str, ...]] = []

    def fake_runner(argv, **kwargs):
        calls.append(tuple(argv))
        return subprocess.CompletedProcess(argv, 0)

    exit_code = run_guardrails(repo_root, runner=fake_runner)

    assert exit_code == 0
    assert len(calls) == 2
    captured = capsys.readouterr()
    assert "OK: contract spine sentinel" in captured.out
    assert "OK: focused contract boundary tests" in captured.out

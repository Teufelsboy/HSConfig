from __future__ import annotations

from pathlib import Path
import subprocess

import pytest

import scripts.run_contract_mutations as mutation_runner
from scripts.run_contract_mutations import MutationSpec, _exit_code, run_mutations


_CONTROLLED_FILES = (
    "src/hsconfig/__init__.py",
    "src/hsconfig/configuration_mode.py",
    "src/hsconfig/globalvalues_baseline.py",
    "src/hsconfig/io.py",
    "src/hsconfig/package_domain.py",
    "src/hsconfig/runtime_entity_owner.py",
    "src/hsconfig/version.py",
    "src/hsconfig/visionai_registry.py",
    "tests/__init__.py",
    "tests/mutation/test_apply_authority_mutations.py",
    "tests/mutation/test_owner_policy_mutations.py",
    "tests/mutation/test_runtime_surface_mutations.py",
)


def _write_controlled_source(
    root: Path,
    *,
    source: str = 'VALUE = "original"\n',
    apply_test: str = (
        "from hsconfig.visionai_registry import VALUE\n\n"
        "def test_value():\n"
        '    assert VALUE == "original"\n'
    ),
) -> None:
    for relative_path in _CONTROLLED_FILES:
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        content = ""
        if relative_path == "src/hsconfig/visionai_registry.py":
            content = source
        elif relative_path == "tests/mutation/test_apply_authority_mutations.py":
            content = apply_test
        path.write_text(content, encoding="utf-8")


def _value_mutation(
    name: str = "value_change",
    *,
    killing_tests: tuple[str, ...] = (
        "tests/mutation/test_apply_authority_mutations.py",
    ),
    replacement: str = 'VALUE = "mutated"',
) -> MutationSpec:
    return MutationSpec(
        name=name,
        target="src/hsconfig/visionai_registry.py",
        original='VALUE = "original"',
        replacement=replacement,
        killing_tests=killing_tests,
    )


def test_default_contract_mutations_are_causally_killed() -> None:
    """Break caught: the isolated runner imports omitted source from elsewhere."""
    results = run_mutations()

    assert len(results) == 3
    assert [result.status for result in results] == ["killed", "killed", "killed"]
    assert _exit_code(results) == 0


def test_preexisting_assertion_failure_blocks_every_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Break caught: a red baseline is misreported as mutation kills."""
    _write_controlled_source(
        tmp_path,
        apply_test=(
            "from hsconfig.visionai_registry import VALUE\n\n"
            "def test_value():\n"
            '    assert VALUE == "expected-before-mutation"\n'
        ),
    )

    def reject_mutation(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("mutation applied before a green baseline")

    monkeypatch.setattr(mutation_runner, "_apply_mutation", reject_mutation)
    mutations = (_value_mutation("first"), _value_mutation("second"))

    results = run_mutations(mutations, source_root=tmp_path)

    assert [result.name for result in results] == ["first", "second"]
    assert [result.status for result in results] == ["error", "error"]
    assert [result.returncode for result in results] == [1, 1]
    assert [result.detail for result in results] == [
        "baseline_failed",
        "baseline_failed",
    ]
    assert all("1 failed" in result.stdout for result in results)
    assert _exit_code(results) == 1


def test_unexecutable_killing_test_is_an_error_and_makes_runner_nonzero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Break caught: a pytest collection or usage error is reported as a kill."""
    mutation = MutationSpec(
        name="missing_killing_test",
        target="src/hsconfig/visionai_registry.py",
        original='NORMAL_APPLY_AUTHORITY = "reports/operator_summary.json"',
        replacement='NORMAL_APPLY_AUTHORITY = "reports/source_bundle.json"',
        killing_tests=("tests/mutation/test_missing_contract.py",),
    )

    def reject_mutation(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("mutation applied before executable baseline")

    monkeypatch.setattr(mutation_runner, "_apply_mutation", reject_mutation)

    results = run_mutations((mutation,))

    assert len(results) == 1
    assert results[0].status == "error"
    assert results[0].returncode == 4
    assert results[0].detail == "baseline_unexecutable"
    assert "file or directory not found" in results[0].stderr
    assert _exit_code(results) == 1


def test_baseline_timeout_blocks_mutation_and_has_stable_detail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Break caught: a baseline timeout is applied or leaks exception text."""
    _write_controlled_source(tmp_path)

    def timeout(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(
            cmd=["pytest"], timeout=120, output="baseline out", stderr="baseline err"
        )

    def reject_mutation(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("mutation applied after baseline timeout")

    monkeypatch.setattr(mutation_runner, "_run_killing_tests", timeout)
    monkeypatch.setattr(mutation_runner, "_apply_mutation", reject_mutation)

    results = run_mutations((_value_mutation(),), source_root=tmp_path)

    assert results[0].status == "error"
    assert results[0].returncode is None
    assert results[0].detail == "baseline_timeout"
    assert results[0].stdout == "baseline out"
    assert results[0].stderr == "baseline err"


def test_baseline_setup_error_blocks_mutation_and_has_stable_detail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Break caught: a baseline setup error is mistaken for a mutant error."""

    def fail_copy(*_args: object, **_kwargs: object) -> None:
        raise ValueError("controlled copy failure")

    def reject_mutation(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("mutation applied after baseline setup error")

    monkeypatch.setattr(mutation_runner, "_copy_isolated_tree", fail_copy)
    monkeypatch.setattr(mutation_runner, "_apply_mutation", reject_mutation)

    results = run_mutations((_value_mutation(),), source_root=tmp_path)

    assert results[0].status == "error"
    assert results[0].returncode is None
    assert results[0].detail == "baseline_error"
    assert results[0].stdout == ""
    assert results[0].stderr == "controlled copy failure"


def test_post_baseline_timeout_is_a_mutation_error_with_stable_detail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Break caught: a mutant timeout escapes or is counted as killed."""
    _write_controlled_source(tmp_path)
    calls = 0

    def baseline_then_timeout(
        *_args: object, **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        nonlocal calls
        calls += 1
        if calls == 1:
            return subprocess.CompletedProcess(["pytest"], 0, "baseline ok", "")
        raise subprocess.TimeoutExpired(
            cmd=["pytest"], timeout=120, output="mutant out", stderr="mutant err"
        )

    monkeypatch.setattr(
        mutation_runner, "_run_killing_tests", baseline_then_timeout
    )

    results = run_mutations((_value_mutation(),), source_root=tmp_path)

    assert calls == 2
    assert results[0].status == "error"
    assert results[0].returncode is None
    assert results[0].detail == "mutation_timeout"
    assert results[0].stdout == "mutant out"
    assert results[0].stderr == "mutant err"
    assert "TimeoutExpired" not in results[0].detail


def test_no_op_mutation_survives_after_green_baseline(tmp_path: Path) -> None:
    """Break caught: a passing no-op mutant is labelled killed."""
    _write_controlled_source(tmp_path)

    results = run_mutations(
        (_value_mutation(replacement='VALUE = "original"'),),
        source_root=tmp_path,
    )

    assert results[0].status == "survived"
    assert results[0].returncode == 0
    assert results[0].detail == "selected_tests_passed"
    assert _exit_code(results) == 1


def test_baseline_deduplicates_tests_and_each_mutant_uses_a_fresh_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Break caught: tests repeat or mutations share contaminated copies."""
    _write_controlled_source(tmp_path)
    owner_test = "tests/mutation/test_owner_policy_mutations.py"
    apply_test = "tests/mutation/test_apply_authority_mutations.py"
    calls: list[tuple[tuple[str, ...], Path, str, int]] = []

    def observe_run(
        command: list[str], *, cwd: Path, **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        target_root = Path(cwd)
        selected_tests = tuple(
            item for item in command if item.startswith("tests/mutation/")
        )
        source = (target_root / "src/hsconfig/visionai_registry.py").read_text(
            encoding="utf-8"
        )
        calls.append(
            (selected_tests, target_root, source, int(_kwargs["timeout"]))
        )
        return subprocess.CompletedProcess(command, 0 if len(calls) == 1 else 1, "", "")

    monkeypatch.setattr(mutation_runner.subprocess, "run", observe_run)
    mutations = (
        _value_mutation(
            "first", killing_tests=(owner_test, apply_test, owner_test)
        ),
        _value_mutation("second", killing_tests=(apply_test, owner_test)),
    )

    results = run_mutations(mutations, source_root=tmp_path)

    assert [result.status for result in results] == ["killed", "killed"]
    assert len(calls) == 3
    assert calls[0][0] == (owner_test, apply_test)
    assert calls[1][0] == (owner_test, apply_test, owner_test)
    assert calls[2][0] == (apply_test, owner_test)
    assert len({target_root for _, target_root, _, _ in calls}) == 3
    assert [timeout for _, _, _, timeout in calls] == [120, 120, 120]
    assert calls[0][2] == 'VALUE = "original"\n'
    assert calls[1][2] == 'VALUE = "mutated"\n'
    assert calls[2][2] == 'VALUE = "mutated"\n'


def test_empty_mutation_input_stays_empty_and_nonzero(tmp_path: Path) -> None:
    """Break caught: the baseline gate invents a result for no mutations."""
    results = run_mutations((), source_root=tmp_path / "missing")

    assert results == ()
    assert _exit_code(results) == 1

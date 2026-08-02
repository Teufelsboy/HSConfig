from __future__ import annotations

from scripts.run_contract_mutations import MutationSpec, _exit_code, run_mutations


def test_unexecutable_killing_test_is_an_error_and_makes_runner_nonzero() -> None:
    """Break caught: a pytest collection or usage error is reported as a kill."""
    mutation = MutationSpec(
        name="missing_killing_test",
        target="src/hsconfig/visionai_registry.py",
        original='NORMAL_APPLY_AUTHORITY = "reports/operator_summary.json"',
        replacement='NORMAL_APPLY_AUTHORITY = "reports/source_bundle.json"',
        killing_tests=("tests/mutation/test_missing_contract.py",),
    )

    results = run_mutations((mutation,))

    assert results[0].status == "error"
    assert results[0].returncode == 4
    assert "file or directory not found" in results[0].stderr
    assert _exit_code(results) == 1

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def test_contract_spine_rows_are_not_consumed_by_apply_or_runtime_write_paths():
    guarded_paths = [
        "src/hsconfig/apply_gate.py",
        "src/hsconfig/runtime_apply.py",
        "src/hsconfig/commands/apply.py",
        "src/hsconfig/operator_summary.py",
    ]

    for relative_path in guarded_paths:
        assert "contract_spine_rows" not in _read(relative_path), relative_path


def test_source_contract_audit_is_summary_only_not_apply_gate_input():
    assert "source_contract_audit" not in _read("src/hsconfig/apply_gate.py")
    assert "source_contract_audit" not in _read("src/hsconfig/runtime_apply.py")
    assert "source_contract_audit" not in _read("src/hsconfig/commands/apply.py")

    operator_summary = _read("src/hsconfig/operator_summary.py")
    assert "source_contract_audit_report" in operator_summary
    assert "_source_contract_audit_summary" in operator_summary
    assert "source_contract_audit_summary" in operator_summary
    assert "runtime_apply_allowed" in operator_summary


def test_source_to_runtime_explainability_is_summary_only_not_apply_gate_input():
    assert "source_to_runtime_explainability" not in _read("src/hsconfig/apply_gate.py")
    assert "source_to_runtime_explainability" not in _read("src/hsconfig/runtime_apply.py")
    assert "source_to_runtime_explainability" not in _read("src/hsconfig/commands/apply.py")

    operator_summary = _read("src/hsconfig/operator_summary.py")
    assert "source_to_runtime_explainability_report" in operator_summary
    assert "_source_to_runtime_explainability_summary" in operator_summary
    assert "source_to_runtime_explainability_summary" in operator_summary
    assert "runtime_apply_allowed" in operator_summary


def test_surface_intent_projection_is_summary_only_not_apply_gate_input():
    guarded_paths = [
        "src/hsconfig/apply_gate.py",
        "src/hsconfig/runtime_apply.py",
        "src/hsconfig/commands/apply.py",
        "src/hsconfig/operator_summary.py",
    ]

    for relative_path in guarded_paths:
        assert "surface_intent_projection" not in _read(relative_path), relative_path
        assert "surface_intent_status" not in _read(relative_path), relative_path
        assert "surface_intent_present" not in _read(relative_path), relative_path


def test_contract_preflight_may_surface_intent_but_not_apply_authority():
    preflight = _read("src/hsconfig/contract_preflight.py")
    guarded_paths = [
        "src/hsconfig/apply_gate.py",
        "src/hsconfig/runtime_apply.py",
        "src/hsconfig/commands/apply.py",
        "src/hsconfig/operator_summary.py",
    ]

    assert "surface_intent_status" in preflight
    assert "surface_intent_present" in preflight
    for relative_path in guarded_paths:
        assert "surface_intent" not in _read(relative_path), relative_path

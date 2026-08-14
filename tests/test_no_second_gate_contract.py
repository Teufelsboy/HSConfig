from pathlib import Path

import pytest

from hsconfig.apply_gate import evaluate_apply_gate
from hsconfig.io import read_json, write_json
from hsconfig.operator_summary import build_operator_summary
from tests.helpers.current_apply_eligible_package import (
    write_current_apply_eligible_package,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def test_contract_spine_rows_are_not_consumed_by_apply_or_runtime_write_paths():
    guarded_paths = [
        "src/hsconfig/apply_gate.py",
        "src/hsconfig/runtime_apply.py",
        "src/hsconfig/commands/apply.py",
        "src/hsconfig/operator_summary_evaluator.py",
    ]

    for relative_path in guarded_paths:
        assert "contract_spine_rows" not in _read(relative_path), relative_path


def test_pre_run_closure_diagnostics_do_not_change_apply_facts_or_decision(
    monkeypatch: pytest.MonkeyPatch,
):
    import hsconfig.operator_summary_evaluator as operator_summary_evaluator

    def reject_live_apply_decision(_facts):
        raise AssertionError("live apply decision alias reused")

    monkeypatch.setattr(
        operator_summary_evaluator,
        "build_apply_decision",
        reject_live_apply_decision,
    )

    def summary(status: str) -> dict:
        return build_operator_summary(
            deck_name="Pre Run Diagnostic",
            deck_code="AAE=",
            technical_validation={"status": "passed", "errors": []},
            pre_run_closure_report={
                "pre_run_contract_status": status,
                "strategy_authority_status": "partial",
                "exact_guide_authority": False,
                "layered_pre_run_source_coverage": {
                    "numerator": 0,
                    "denominator": 0,
                    "fraction": "0/0",
                    "value": 1.0,
                    "vacuous": True,
                },
            },
        )

    complete = summary("complete")
    incomplete = summary("incomplete")

    assert complete["pre_run_contract_status"] == "complete"
    assert incomplete["pre_run_contract_status"] == "incomplete"
    for field in (
        "runtime_apply_allowed",
        "runtime_apply_mode",
        "runtime_apply_reason",
        "apply_policy",
        "technical_status",
    ):
        assert complete[field] == incomplete[field]

    apply_paths = (
        "src/hsconfig/apply_gate.py",
        "src/hsconfig/runtime_apply.py",
        "src/hsconfig/commands/apply.py",
    )
    for relative_path in apply_paths:
        assert "pre_run_metrics" not in _read(relative_path)
        assert "pre_run_closure" not in _read(relative_path)

    operator_source = _read("src/hsconfig/operator_summary_evaluator.py")
    apply_facts_body = operator_source[
        operator_source.index("def _operator_apply_facts(") :
    ]
    apply_facts_body = apply_facts_body[
        : apply_facts_body.index("\ndef ", 1)
    ]
    assert "pre_run" not in apply_facts_body


def test_source_contract_audit_is_summary_only_not_apply_gate_input():
    assert "source_contract_audit" not in _read("src/hsconfig/apply_gate.py")
    assert "source_contract_audit" not in _read("src/hsconfig/runtime_apply.py")
    assert "source_contract_audit" not in _read("src/hsconfig/commands/apply.py")

    operator_summary = _read("src/hsconfig/operator_summary_evaluator.py")
    assert "source_contract_audit_report" in operator_summary
    assert "_source_contract_audit_summary" in operator_summary
    assert "source_contract_audit_summary" in operator_summary
    assert "runtime_apply_allowed" in operator_summary


def test_source_to_runtime_explainability_is_summary_only_not_apply_gate_input():
    assert "source_to_runtime_explainability" not in _read("src/hsconfig/apply_gate.py")
    assert "source_to_runtime_explainability" not in _read("src/hsconfig/runtime_apply.py")
    assert "source_to_runtime_explainability" not in _read("src/hsconfig/commands/apply.py")

    operator_summary = _read("src/hsconfig/operator_summary_evaluator.py")
    assert "source_to_runtime_explainability_report" in operator_summary
    assert "_source_to_runtime_explainability_summary" in operator_summary
    assert "source_to_runtime_explainability_summary" in operator_summary
    assert "runtime_apply_allowed" in operator_summary


def test_surface_intent_projection_is_summary_only_not_apply_gate_input():
    guarded_paths = [
        "src/hsconfig/apply_gate.py",
        "src/hsconfig/runtime_apply.py",
        "src/hsconfig/commands/apply.py",
        "src/hsconfig/operator_summary_evaluator.py",
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
        "src/hsconfig/operator_summary_evaluator.py",
    ]

    assert "surface_intent_status" in preflight
    assert "surface_intent_present" in preflight
    for relative_path in guarded_paths:
        assert "surface_intent" not in _read(relative_path), relative_path


@pytest.mark.parametrize("allow_source_informed", [False, True])
def test_deprecated_source_flag_cannot_bypass_core_decision_parity(
    tmp_path: Path,
    allow_source_informed: bool,
) -> None:
    package = write_current_apply_eligible_package(
        tmp_path / "package",
        operator_summary={
            "runtime_apply_allowed": True,
            "runtime_apply_mode": "load_safe_apply",
            "runtime_apply_reason": "runtime_load_safe_package",
        },
    )
    summary_path = package / "reports" / "operator_summary.json"
    summary = read_json(summary_path)
    summary["runtime_apply_allowed"] = False
    write_json(summary_path, summary)

    gate = evaluate_apply_gate(
        package,
        allow_source_informed=allow_source_informed,
    )

    assert gate["allowed"] is False
    assert gate["mode"] == "blocked"
    assert gate["reasons"][0]["reason"] == (
        "operator_summary_apply_decision_mismatch"
    )

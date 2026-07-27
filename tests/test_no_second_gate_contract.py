from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SHADOWPRIEST_ACTIVE_PLAN = (
    REPO_ROOT / "docs/superpowers/plans/2026-07-27-shadowpriest-live-config-apply.md"
)
SHADOWPRIEST_ACTIVE_SPEC = (
    REPO_ROOT
    / "docs/superpowers/specs/2026-07-27-shadowpriest-live-config-apply-design.md"
)


def _read(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def _plan_step(text: str, heading: str) -> str:
    start = text.index(heading)
    next_step = text.find("\n- [ ] **Step ", start + len(heading))
    next_task = text.find("\n---", start + len(heading))
    candidates = [index for index in (next_step, next_task) if index != -1]
    end = min(candidates) if candidates else len(text)
    return text[start:end]


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


def test_active_shadowpriest_plan_does_not_require_nonempty_canonical_receipts():
    text = SHADOWPRIEST_ACTIVE_PLAN.read_text(encoding="utf-8")

    assert 'assert claims["canonical_source_receipts"]' not in text
    assert 'assert operator["source_apply_eligible"]' not in text
    assert 'assert verdict["package"]["source_apply_eligible"]' not in text


def test_active_shadowpriest_source_diagnostics_cannot_control_apply_actions():
    plan = SHADOWPRIEST_ACTIVE_PLAN.read_text(encoding="utf-8")
    spec = SHADOWPRIEST_ACTIVE_SPEC.read_text(encoding="utf-8")
    acquisition = _plan_step(
        plan, "- [ ] **Step 4: Record live-source acquisition diagnostics**"
    ).lower()
    package_authority = _plan_step(
        plan, "- [ ] **Step 3: Verify exact deck, package receipt, and operator authority**"
    ).lower()
    final_review = _plan_step(
        plan, "- [ ] **Step 3: Final independent review**"
    ).lower()

    assert "live_http" in acquisition and "live_verified" in acquisition
    assert "test-path" in acquisition
    for action_control in ("throw", "stop", "must agree", "must confirm", "required"):
        assert action_control not in acquisition

    assert "canonical_source_receipts" in package_authority
    assert "live_http" in package_authority and "live_verified" in package_authority
    assert "source authority" not in package_authority
    package_source_diagnostics = package_authority[
        package_authority.index("canonical_receipts =") :
        package_authority.index('assert operator["technical_status"]')
    ]
    for action_control in ("assert", "throw", "stop", "must confirm", "required"):
        assert action_control not in package_source_diagnostics
    assert 'claims["canonical_source_receipts"]' not in package_source_diagnostics
    assert 'row["acquisition_provenance"]' not in package_source_diagnostics

    assert "live_http/live_verified" in final_review
    assert "canonical receipt count" in final_review
    assert "exact-source closure" in final_review
    assert "non-authoritative" in final_review
    diagnostic_start = final_review.index("non-authoritative source diagnostics")
    confirmation_items = final_review[:diagnostic_start]
    source_diagnostics = final_review[diagnostic_start:]
    assert "live_http/live_verified" not in confirmation_items
    assert "canonical receipt count" not in confirmation_items
    assert "exact-source closure" not in confirmation_items
    for action_control in ("assert", "throw", "stop", "must confirm", "required"):
        assert action_control not in source_diagnostics

    source_boundary = spec[spec.index("Canonical receipt count") :]
    source_boundary = source_boundary[: source_boundary.index("### Phase 2")].lower()
    assert "diagnostics" in source_boundary
    assert "second apply" in source_boundary
    for action_control in ("assert", "throw", "stop", "must confirm", "required"):
        assert action_control not in source_boundary

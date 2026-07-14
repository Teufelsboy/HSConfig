# HSConfig Contract Invariant Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the current HSConfig source-contract architecture hard to regress: one apply authority, no silent default-only success, strict claim-kind surface routing, and an effect-not-mulligan canary.

**Architecture:** Keep the existing normal path unchanged: `hsconfig configure` / `hsconfig prepare` build packages, `reports/operator_summary.json` remains the only normal apply authority, and diagnostic reports stay diagnostic. Add a compact invariant summary to the existing contract-spine sentinel and promote the existing no-default-only and ShadowPriest closure proofs into the guardrail runner. Do not add a new runtime surface, operator report, or pipeline.

**Tech Stack:** Python 3, pytest, existing HSConfig modules in `src/hsconfig`, existing guardrail runner in `scripts/check_contract_guardrails.py`, existing docs and installed skill sync.

## Global Constraints

- Do not add a new CLI command, pipeline, runtime surface, dependency, or operator apply gate.
- `reports/operator_summary.json` remains the only normal runtime apply authority.
- `source_contract_audit.json`, `source_to_runtime_explainability.json`, `contract_spine_rows`, and `default_only_runtime_surface_details` remain diagnostic-only.
- A valid load-safe package must not be blocked because guide evidence is thin, a mechanic is unsupported, or a claim is report-only.
- A default-only or thin runtime surface must never be silent or presented as fully source-backed.
- Darkbishop Benedictus / `SW_448` remains the regression canary: preserve hero-power-transform CardID behavior, but do not emit an opening-hand Mulligan keep unless an explicit Mulligan source claim exists.
- `Presume.json`, `Concede.json`, and aggregate `CardBehavior.json` remain outside the normal HSConfig output path.
- Keep implementation small and local. Prefer extending existing sentinel, tests, docs, and guardrails over creating new reports.

---

## File Structure

- Modify `src/hsconfig/contract_spine_sentinel.py`
  - Add `contract_invariants` to the existing diagnostic sentinel payload.
  - Reuse existing checks and problems. Do not read generated packages and do not create runtime authority.

- Modify `tests/test_contract_spine_sentinel.py`
  - Assert the new invariant summary is clean and diagnostic-only.
  - Assert drift in existing checks maps to invariant failure.

- Modify `scripts/check_contract_guardrails.py`
  - Add the existing no-default-only, config-usefulness, ShadowPriest closure, and skill tests to `FOCUSED_CONTRACT_TESTS`.

- Modify `tests/test_check_contract_guardrails.py`
  - Assert the guardrail runner includes the promoted proof tests.

- Modify `docs/operator/README.md`
  - Add a short section naming the invariant closure and clarifying that it is diagnostic proof, not another apply gate.

- Modify `.agents/skills/hsconfig/SKILL.md`
  - Add the same short invariant closure sentence so the installed skill stays aligned after sync.

- Do not modify `src/hsconfig/apply_gate.py`, `src/hsconfig/runtime_apply.py`, or `src/hsconfig/commands/apply.py` unless a failing test proves a real second-gate regression. This plan should not require those changes.

---

### Task 1: Add Contract Invariant Summary To Existing Sentinel

**Files:**
- Modify: `src/hsconfig/contract_spine_sentinel.py`
- Test: `tests/test_contract_spine_sentinel.py`

**Interfaces:**
- Consumes: existing `checks: dict[str, Any]` and `problems: list[dict[str, object]]` inside `build_contract_spine_sentinel_report(...)`.
- Produces: top-level `contract_invariants: dict[str, dict[str, object]]`.
- Produces helper: `_contract_invariants(checks: dict[str, Any], problems: list[dict[str, object]]) -> dict[str, dict[str, object]]`.

- [ ] **Step 1: Write failing test for clean invariant summary**

Append this test to `tests/test_contract_spine_sentinel.py`:

```python
def test_contract_spine_sentinel_exposes_clean_contract_invariants():
    report = build_contract_spine_sentinel_report()

    assert report["status"] == "clean"
    assert report["authority"] == "diagnostic_only"
    assert report["apply_blocking"] is False

    invariants = report["contract_invariants"]
    assert set(invariants) == {
        "single_apply_authority",
        "diagnostics_are_non_authoritative",
        "claim_kind_surface_policy_complete",
        "effect_not_mulligan",
        "no_forbidden_legacy_runtime_surfaces",
        "skill_and_docs_guardrail_ready",
    }
    assert all(row["status"] == "clean" for row in invariants.values())
    assert all(row["authority"] == "diagnostic_only" for row in invariants.values())
    assert all(row["apply_blocking"] is False for row in invariants.values())
    assert invariants["single_apply_authority"]["evidence"] == [
        "report_ownership_gate_files",
        "active_apply_diagnostic_consumers",
        "lifecycle_gate_files",
    ]
    assert invariants["effect_not_mulligan"]["evidence"] == [
        "start_of_game_mulligan_suppression",
        "critical_boundary_rows",
    ]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest tests/test_contract_spine_sentinel.py::test_contract_spine_sentinel_exposes_clean_contract_invariants -q
```

Expected: fail with `KeyError: 'contract_invariants'`.

- [ ] **Step 3: Implement minimal invariant summary**

Modify `src/hsconfig/contract_spine_sentinel.py`.

Inside `build_contract_spine_sentinel_report(...)`, after `problems = _problems(checks)`, return the new top-level key:

```python
    problems = _problems(checks)
    return {
        "schema_version": 1,
        "status": "clean" if not problems else "drift_detected",
        "authority": "diagnostic_only",
        "operator_gate_impact": "diagnostic_only",
        "apply_blocking": False,
        "checks": checks,
        "contract_invariants": _contract_invariants(checks, problems),
        "problems": problems,
    }
```

Add this helper near `_problems(...)`:

```python
INVARIANT_EVIDENCE = {
    "single_apply_authority": (
        "report_ownership_gate_files",
        "active_apply_diagnostic_consumers",
        "lifecycle_gate_files",
    ),
    "diagnostics_are_non_authoritative": (
        "non_diagnostic_policy_claim_kinds",
        "spine_rows_with_apply_authority_fields",
        "conformance_apply_authority_fields_present",
    ),
    "claim_kind_surface_policy_complete": (
        "policy_missing_claim_kinds",
        "policy_extra_claim_kinds",
        "spine_missing_claim_kinds",
        "spine_extra_claim_kinds",
        "claim_family_registry",
    ),
    "effect_not_mulligan": (
        "start_of_game_mulligan_suppression",
        "critical_boundary_rows",
    ),
    "no_forbidden_legacy_runtime_surfaces": (
        "legacy_surface_normal_routing",
        "output_ownership_forbidden_legacy_surfaces",
    ),
    "skill_and_docs_guardrail_ready": (
        "report_ownership_unclassified_files",
        "output_ownership_unclassified_files",
    ),
}


def _contract_invariants(
    checks: dict[str, Any],
    problems: list[dict[str, object]],
) -> dict[str, dict[str, object]]:
    problem_checks = {
        str(problem.get("check"))
        for problem in problems
        if isinstance(problem, dict)
    }
    invariants: dict[str, dict[str, object]] = {}
    for name, evidence_keys in INVARIANT_EVIDENCE.items():
        failing = [key for key in evidence_keys if key in problem_checks]
        invariants[name] = {
            "status": "clean" if not failing else "drift_detected",
            "authority": "diagnostic_only",
            "apply_blocking": False,
            "evidence": list(evidence_keys),
            "failing_checks": failing,
        }

    suppression = checks.get("start_of_game_mulligan_suppression", {})
    if not isinstance(suppression, dict) or suppression.get("decision") != "rejected":
        row = invariants["effect_not_mulligan"]
        row["status"] = "drift_detected"
        row["failing_checks"] = sorted(
            {*row["failing_checks"], "start_of_game_mulligan_suppression"}
        )

    if checks.get("report_ownership_gate_files") != ["reports/operator_summary.json"]:
        row = invariants["single_apply_authority"]
        row["status"] = "drift_detected"
        row["failing_checks"] = sorted(
            {*row["failing_checks"], "report_ownership_gate_files"}
        )

    return invariants
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
python -m pytest tests/test_contract_spine_sentinel.py::test_contract_spine_sentinel_exposes_clean_contract_invariants -q
```

Expected: pass.

- [ ] **Step 5: Commit Task 1**

```powershell
git add src/hsconfig/contract_spine_sentinel.py tests/test_contract_spine_sentinel.py
git commit -m "feat: expose contract invariant summary"
```

---

### Task 2: Prove Invariants Fail When Authority Or Effect Boundary Drifts

**Files:**
- Modify: `tests/test_contract_spine_sentinel.py`

**Interfaces:**
- Consumes: `build_contract_spine_sentinel_report()`.
- Produces: regression tests proving `contract_invariants` is not decorative; it fails when existing sentinel checks drift.

- [ ] **Step 1: Write failing test for diagnostic report promoted to gate**

Append this test to `tests/test_contract_spine_sentinel.py`:

```python
def test_contract_invariants_flag_second_apply_authority(monkeypatch):
    from hsconfig import contract_spine_sentinel as sentinel

    original = sentinel.build_report_ownership

    def drifted_report_ownership():
        rows = []
        for row in original():
            if row.get("file") == "reports/source_contract_audit.json":
                rows.append({**row, "classification": "gate"})
            else:
                rows.append(row)
        return rows

    monkeypatch.setattr(sentinel, "build_report_ownership", drifted_report_ownership)

    report = build_contract_spine_sentinel_report()
    invariant = report["contract_invariants"]["single_apply_authority"]

    assert report["status"] == "drift_detected"
    assert invariant["status"] == "drift_detected"
    assert invariant["authority"] == "diagnostic_only"
    assert invariant["apply_blocking"] is False
    assert "lifecycle_gate_files" in invariant["failing_checks"]
```

- [ ] **Step 2: Write failing test for effect-not-mulligan drift**

Append this test to `tests/test_contract_spine_sentinel.py`:

```python
def test_contract_invariants_flag_missing_effect_not_mulligan_boundary(monkeypatch):
    from hsconfig import contract_spine_sentinel as sentinel

    original = sentinel.build_source_contract_conformance_snapshot

    def drifted_conformance():
        snapshot = original()
        snapshot["start_of_game_mulligan_suppression"] = {
            "claim_kind": "mulligan_keep",
            "decision": "allowed",
            "reason": "drifted",
            "surface": "mulligan",
        }
        return snapshot

    monkeypatch.setattr(
        sentinel,
        "build_source_contract_conformance_snapshot",
        drifted_conformance,
    )

    report = build_contract_spine_sentinel_report()
    invariant = report["contract_invariants"]["effect_not_mulligan"]

    assert report["status"] == "drift_detected"
    assert invariant["status"] == "drift_detected"
    assert invariant["authority"] == "diagnostic_only"
    assert invariant["apply_blocking"] is False
    assert "start_of_game_mulligan_suppression" in invariant["failing_checks"]
```

- [ ] **Step 3: Run tests to verify failure before implementation**

If Task 1 has not yet added `_contract_invariants`, both tests fail with missing `contract_invariants`. If Task 1 is complete, these should already pass because the invariant summary reads `problems`.

Run:

```powershell
python -m pytest tests/test_contract_spine_sentinel.py::test_contract_invariants_flag_second_apply_authority tests/test_contract_spine_sentinel.py::test_contract_invariants_flag_missing_effect_not_mulligan_boundary -q
```

Expected after Task 1: pass.

- [ ] **Step 4: Commit Task 2**

```powershell
git add tests/test_contract_spine_sentinel.py
git commit -m "test: prove contract invariant drift detection"
```

---

### Task 3: Promote Existing No-Default-Only Proofs Into Guardrail Runner

**Files:**
- Modify: `scripts/check_contract_guardrails.py`
- Modify: `tests/test_check_contract_guardrails.py`

**Interfaces:**
- Consumes: `FOCUSED_CONTRACT_TESTS: tuple[str, ...]`.
- Produces: guardrail runner coverage that includes no-default-only, config-usefulness, and fresh ShadowPriest closure proof.

- [ ] **Step 1: Write failing test for guardrail test list**

Append this test to `tests/test_check_contract_guardrails.py`:

```python
def test_guardrail_runner_includes_contract_invariant_closure_tests():
    from scripts.check_contract_guardrails import FOCUSED_CONTRACT_TESTS

    required = {
        "tests/test_config_usefulness.py",
        "tests/test_operator_summary.py",
        "tests/test_no_default_only_semantic_archetype_matrix.py",
        "tests/test_shadowpriest_fresh_closure_proof.py",
        "tests/test_skill_sync.py",
        "tests/test_skill_files.py",
    }

    assert required <= set(FOCUSED_CONTRACT_TESTS)
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest tests/test_check_contract_guardrails.py::test_guardrail_runner_includes_contract_invariant_closure_tests -q
```

Expected: fail showing at least one missing path.

- [ ] **Step 3: Update guardrail runner**

Modify `FOCUSED_CONTRACT_TESTS` in `scripts/check_contract_guardrails.py` so it includes these paths exactly once:

```python
    "tests/test_config_usefulness.py",
    "tests/test_operator_summary.py",
    "tests/test_no_default_only_semantic_archetype_matrix.py",
    "tests/test_shadowpriest_fresh_closure_proof.py",
    "tests/test_skill_sync.py",
    "tests/test_skill_files.py",
```

Keep the existing contract-spine, apply-authority, no-block, docs, claim-kind, and source-to-runtime tests.

- [ ] **Step 4: Run focused test**

Run:

```powershell
python -m pytest tests/test_check_contract_guardrails.py::test_guardrail_runner_includes_contract_invariant_closure_tests -q
```

Expected: pass.

- [ ] **Step 5: Run guardrail script**

Run:

```powershell
python scripts/check_contract_guardrails.py
```

Expected:

```text
OK: installed skill sync
OK: contract spine sentinel
OK: focused contract boundary tests
```

- [ ] **Step 6: Commit Task 3**

```powershell
git add scripts/check_contract_guardrails.py tests/test_check_contract_guardrails.py
git commit -m "test: promote invariant proofs into guardrails"
```

---

### Task 4: Document Invariant Closure Without Adding Operator Complexity

**Files:**
- Modify: `docs/operator/README.md`
- Modify: `.agents/skills/hsconfig/SKILL.md`
- Test: `tests/test_skill_files.py`

**Interfaces:**
- Consumes: existing operator docs and skill wording.
- Produces: one shared invariant-closure statement in docs and skill.

- [ ] **Step 1: Write failing docs/skill test**

Append this test to `tests/test_skill_files.py`:

```python
def test_docs_and_skill_explain_contract_invariant_closure_without_new_gate():
    operator_docs = Path("docs/operator/README.md").read_text(encoding="utf-8")
    skill = Path(".agents/skills/hsconfig/SKILL.md").read_text(encoding="utf-8")
    combined = operator_docs + "\n" + skill

    required = (
        "Contract invariant closure means: single apply authority, no silent "
        "default-only success, claim-kind surface discipline, and effect-not-mulligan "
        "canary coverage. It is diagnostic proof, not another runtime apply gate."
    )

    assert required in operator_docs
    assert required in skill
    assert "another runtime apply gate" in combined
    assert "operator_summary.json remains the only normal apply authority" in combined
```

If `Path` is not imported near the top of `tests/test_skill_files.py`, add:

```python
from pathlib import Path
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest tests/test_skill_files.py::test_docs_and_skill_explain_contract_invariant_closure_without_new_gate -q
```

Expected: fail because the exact invariant closure sentence is absent.

- [ ] **Step 3: Add the same compact sentence to docs**

In `docs/operator/README.md`, add this paragraph near the existing no-silent-default-only policy:

```markdown
Contract invariant closure means: single apply authority, no silent default-only success, claim-kind surface discipline, and effect-not-mulligan canary coverage. It is diagnostic proof, not another runtime apply gate. `operator_summary.json remains the only normal apply authority`.
```

- [ ] **Step 4: Add the same compact sentence to skill**

In `.agents/skills/hsconfig/SKILL.md`, add the same bullet near the source-contract boundary bullets:

```markdown
- Contract invariant closure means: single apply authority, no silent default-only success, claim-kind surface discipline, and effect-not-mulligan canary coverage. It is diagnostic proof, not another runtime apply gate. `operator_summary.json remains the only normal apply authority`.
```

- [ ] **Step 5: Sync installed skill**

Run:

```powershell
python scripts/sync_installed_skill.py
```

Expected: installed skill at `C:\Users\darbo\.codex\skills\hsconfig` is updated.

- [ ] **Step 6: Run docs/skill tests**

Run:

```powershell
python -m pytest tests/test_skill_files.py::test_docs_and_skill_explain_contract_invariant_closure_without_new_gate tests/test_skill_sync.py -q
```

Expected: pass.

- [ ] **Step 7: Commit Task 4**

```powershell
git add docs/operator/README.md .agents/skills/hsconfig/SKILL.md tests/test_skill_files.py
git commit -m "docs: define contract invariant closure"
```

---

### Task 5: Final Verification And Review

**Files:**
- Verify only. Do not modify files unless a verification failure identifies a specific regression.

**Interfaces:**
- Consumes: all previous task outputs.
- Produces: clean verification state and final implementation summary.

- [ ] **Step 1: Run sentinel tests**

```powershell
python -m pytest tests/test_contract_spine_sentinel.py tests/test_contract_spine_sentinel_cli.py tests/test_contract_spine_sentinel_docs.py -q
```

Expected: all pass.

- [ ] **Step 2: Run focused invariant/default-only tests**

```powershell
python -m pytest tests/test_apply_authority_boundary.py tests/test_no_second_gate_contract.py tests/test_config_usefulness.py tests/test_operator_summary.py tests/test_no_default_only_semantic_archetype_matrix.py tests/test_shadowpriest_fresh_closure_proof.py -q
```

Expected: all pass.

- [ ] **Step 3: Run guardrail script**

```powershell
python scripts/check_contract_guardrails.py
```

Expected:

```text
OK: installed skill sync
OK: contract spine sentinel
OK: focused contract boundary tests
```

- [ ] **Step 4: Run broader safety suite**

```powershell
python -m pytest tests/test_universal_wild_no_block_matrix.py tests/test_shadowpriest_depth_e2e.py tests/test_claim_kind_runtime_contract.py tests/test_source_contract_conformance.py tests/test_source_contract_audit.py tests/test_source_to_runtime_explainability.py -q
```

Expected: all pass.

- [ ] **Step 5: Run full suite if time permits**

```powershell
python -m pytest
```

Expected: all tests pass. If runtime exceeds local patience but targeted suites passed, report that the full suite was not completed and include the exact stopping point.

- [ ] **Step 6: Inspect diff**

```powershell
git diff --stat HEAD
git diff --check
git status --short --branch
```

Expected: `git diff --check` prints no whitespace errors.

- [ ] **Step 7: Final review checklist**

Confirm these statements before completion:

- `reports/operator_summary.json` remains the only normal apply authority.
- No diagnostic report grants or denies runtime apply.
- `contract_invariants` is diagnostic-only and `apply_blocking=False`.
- No new operator report, CLI command, dependency, runtime surface, `Presume.json`, or `Concede.json` output path was added.
- Default-only surfaces are visible quality debt, not hidden success and not a runtime apply blocker.
- Darkbishop / `SW_448` still preserves hero-power-transform behavior without Mulligan keep.
- Installed skill sync is green.

- [ ] **Step 8: Final commit if verification changes were needed**

If Task 5 required small fixes, commit them:

```powershell
git add <specific changed files from Task 5>
git commit -m "fix: close contract invariant verification gaps"
```

If no files changed during Task 5, do not create an empty commit.

---

## Execution Notes

- Recommended execution mode: Subagent-Driven.
- Use one implementation worker for Tasks 1-2, one worker for Task 3, one worker for Task 4, and one final reviewer for Task 5.
- Only one worker should edit `src/hsconfig/contract_spine_sentinel.py` and `tests/test_contract_spine_sentinel.py`.
- Do not let a docs worker change runtime code.
- Do not let a runtime worker change operator docs except through Task 4.

## Self-Review

- Spec coverage: covered single apply authority, no silent default-only, claim-kind surface discipline, effect-not-mulligan canary, any-deck no-block behavior through promoted guardrails, and docs/skill sync.
- Red-flag scan: no vague implementation markers remain.
- Type consistency: new helper signature is `_contract_invariants(checks: dict[str, Any], problems: list[dict[str, object]]) -> dict[str, dict[str, object]]`; tests reference top-level `report["contract_invariants"]`.
- Scope check: this plan does not add a pipeline, report, gate, dependency, runtime surface, or broad mechanic expansion.

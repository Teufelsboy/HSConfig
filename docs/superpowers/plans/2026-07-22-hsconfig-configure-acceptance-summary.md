# HSConfig Configure Acceptance Summary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a compact, diagnostic-only `acceptance_summary` to `configure_summary.json` so a normal HSConfig operator can immediately see whether the generated package is usable now, without creating a second apply gate or a new report.

**Architecture:** Keep `reports/operator_summary.json` as the only normal apply authority. Build `acceptance_summary` inside `hsconfig.commands.configure` from the already-loaded `operator_summary`, validation status, apply status, and diagnostic `config_quality_summary`; write it only into the top-level `configure_summary.json`. Do not add gameplay logic, log analysis, HSTuner integration, new runtime surfaces, or SOURCE_BACKED_STRONG-as-gate behavior.

**Tech Stack:** Python 3, existing HSConfig CLI, existing JSON helpers in `hsconfig.io`, existing pytest tests.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig`.
- Start execution with `git fetch --all --prune --tags` and verify a clean worktree.
- Finish execution with a clean worktree after commit; no backups or temporary artifacts left behind.
- Do not use HSTuner.
- Do not inspect gameplay logs for this change.
- Do not change HearthRanger runtime generation behavior.
- Do not add dependencies.
- Do not create a new report file for this feature.
- Do not modify `reports/operator_summary.json` schema for this feature.
- `reports/operator_summary.json` remains the only normal apply authority.
- `SOURCE_BACKED_STRONG` remains an evidence-quality label, not an apply gate.
- `source_status_apply_blocking` remains non-blocking and must be surfaced as `false` when the operator summary says so.
- `default_only_runtime_surfaces` remains visible and diagnostic; its presence must not override runtime apply permission.
- `config_quality_summary` remains diagnostic-only and must not block configure apply.
- Normal runtime surfaces remain `GlobalValues.json`, `Mulligan.json`, per-card `<CARDID>.json`, and `Combo.json` only when source-backed combo rows exist.

---

## File Structure

- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\commands\configure.py`
  - Add a private helper `_build_acceptance_summary(...)`.
  - Call it immediately before `_finish(..., "OK", ...)`.
  - Keep helper local to `configure.py` because this is a configure-output projection, not a reusable package acceptance engine.
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_configure_cli.py`
  - Add focused unit tests for `_build_acceptance_summary`.
  - Extend the existing configure CLI diagnostic tests to assert the field is written and remains outside `operator_summary.json`.
- No new production file.
- No new report file.
- No docs update unless implementation reveals a naming conflict.

---

### Task 1: Add Unit Tests For The Acceptance Projection

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_configure_cli.py`
- Modify later in Task 2: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\commands\configure.py`

**Interfaces:**
- Consumes: planned private function `hsconfig.commands.configure._build_acceptance_summary`
- Produces: test-defined contract for the function return shape:
  - `schema_version: int`
  - `use_config_now: bool`
  - `normal_apply_authority: str`
  - `runtime_apply_allowed: bool`
  - `runtime_apply_mode: str`
  - `technical_status: str`
  - `source_strength: str`
  - `source_gaps_apply_blocking: bool`
  - `default_only_clean: bool`
  - `default_only_runtime_surfaces: list[str]`
  - `config_quality_status: str`
  - `config_quality_problem_checks: list[str]`
  - `first_missing_source_action: str | None`
  - `next_report_to_open: str`
  - `interpretation: str`

- [ ] **Step 1: Import the helper in the test file**

Change the import near the top of `tests/test_configure_cli.py` from:

```python
from hsconfig.commands.configure import _compact_config_quality_summary
```

to:

```python
from hsconfig.commands.configure import (
    _build_acceptance_summary,
    _compact_config_quality_summary,
)
```

- [ ] **Step 2: Add the passing load-safe test before `test_compact_config_quality_summary_reports_clean_status`**

Add this test above the existing compact quality summary tests:

```python
def test_build_acceptance_summary_marks_load_safe_package_usable() -> None:
    operator_summary = {
        "technical_status": "VALID_PACKAGE",
        "runtime_apply_allowed": True,
        "runtime_apply_mode": "load_safe_apply",
        "runtime_apply_contract": {
            "apply_authority": "reports/operator_summary.json",
        },
        "source_backed_status": "SOURCE_BACKED_PARTIAL",
        "source_status_apply_blocking": False,
        "first_missing_source_action": "prove_current_or_evergreen_and_package_source_closure",
        "default_only_runtime_surfaces": [],
    }
    config_quality_summary = {
        "status": "clean",
        "authority": "diagnostic_only",
        "apply_blocking": False,
        "runtime_write_performed": False,
        "problem_count": 0,
        "problem_checks": [],
    }

    assert _build_acceptance_summary(
        operator_summary=operator_summary,
        validate_status=0,
        apply_requested=False,
        apply_status=None,
        config_quality_summary=config_quality_summary,
    ) == {
        "schema_version": 1,
        "use_config_now": True,
        "normal_apply_authority": "reports/operator_summary.json",
        "runtime_apply_allowed": True,
        "runtime_apply_mode": "load_safe_apply",
        "technical_status": "VALID_PACKAGE",
        "validation_status": "passed",
        "apply_requested": False,
        "apply_status": None,
        "source_strength": "SOURCE_BACKED_PARTIAL",
        "source_gaps_apply_blocking": False,
        "default_only_clean": True,
        "default_only_runtime_surfaces": [],
        "config_quality_status": "clean",
        "config_quality_problem_checks": [],
        "first_missing_source_action": "prove_current_or_evergreen_and_package_source_closure",
        "next_report_to_open": "reports/operator_summary.json",
        "interpretation": (
            "Package is usable now according to reports/operator_summary.json; "
            "source and config-quality details remain diagnostic."
        ),
    }
```

- [ ] **Step 3: Add the diagnostic-gap test**

Add this test immediately after the passing load-safe test:

```python
def test_build_acceptance_summary_surfaces_diagnostics_without_blocking() -> None:
    operator_summary = {
        "technical_status": "VALID_PACKAGE",
        "runtime_apply_allowed": True,
        "runtime_apply_mode": "load_safe_apply",
        "runtime_apply_contract": {
            "apply_authority": "reports/operator_summary.json",
        },
        "source_backed_status": "SOURCE_BACKED_PARTIAL",
        "source_status_apply_blocking": False,
        "first_missing_source_action": "add_source_claim_for_mulligan_keep",
        "default_only_runtime_surfaces": ["Mulligan.json"],
    }
    config_quality_summary = {
        "status": "attention",
        "authority": "diagnostic_only",
        "apply_blocking": False,
        "runtime_write_performed": False,
        "problem_count": 2,
        "problem_checks": [
            "operator_default_only_runtime_surfaces",
            "source_to_runtime_closure_rows_missing",
        ],
        "next_action": "run_contract_doctor_for_details",
    }

    summary = _build_acceptance_summary(
        operator_summary=operator_summary,
        validate_status=0,
        apply_requested=True,
        apply_status=0,
        config_quality_summary=config_quality_summary,
    )

    assert summary["use_config_now"] is True
    assert summary["source_gaps_apply_blocking"] is False
    assert summary["default_only_clean"] is False
    assert summary["default_only_runtime_surfaces"] == ["Mulligan.json"]
    assert summary["config_quality_problem_checks"] == [
        "operator_default_only_runtime_surfaces",
        "source_to_runtime_closure_rows_missing",
    ]
    assert summary["next_report_to_open"] == "reports/contract_doctor.json"
    assert summary["interpretation"] == (
        "Package is usable now according to reports/operator_summary.json; "
        "source and config-quality details remain diagnostic."
    )
```

- [ ] **Step 4: Add the technical-block test**

Add this test after the diagnostic-gap test:

```python
def test_build_acceptance_summary_marks_non_load_safe_package_unusable() -> None:
    operator_summary = {
        "technical_status": "INVALID_PACKAGE",
        "runtime_apply_allowed": False,
        "runtime_apply_mode": "blocked",
        "source_backed_status": "SOURCE_BACKED_PARTIAL",
        "source_status_apply_blocking": False,
        "default_only_runtime_surfaces": [],
    }
    config_quality_summary = {
        "status": "attention",
        "authority": "diagnostic_only",
        "apply_blocking": False,
        "runtime_write_performed": False,
        "problem_count": 1,
        "problem_checks": ["operator_summary_missing_or_invalid"],
    }

    summary = _build_acceptance_summary(
        operator_summary=operator_summary,
        validate_status=1,
        apply_requested=False,
        apply_status=None,
        config_quality_summary=config_quality_summary,
    )

    assert summary["use_config_now"] is False
    assert summary["normal_apply_authority"] == "reports/operator_summary.json"
    assert summary["runtime_apply_allowed"] is False
    assert summary["runtime_apply_mode"] == "blocked"
    assert summary["validation_status"] == "failed"
    assert summary["next_report_to_open"] == "reports/operator_summary.json"
    assert summary["interpretation"] == (
        "Package is not usable now; inspect reports/operator_summary.json first."
    )
```

- [ ] **Step 5: Run the targeted tests and confirm failure**

Run:

```powershell
pytest tests\test_configure_cli.py::test_build_acceptance_summary_marks_load_safe_package_usable tests\test_configure_cli.py::test_build_acceptance_summary_surfaces_diagnostics_without_blocking tests\test_configure_cli.py::test_build_acceptance_summary_marks_non_load_safe_package_unusable -q
```

Expected: FAIL during collection with an import error similar to:

```text
ImportError: cannot import name '_build_acceptance_summary'
```

Do not implement anything before seeing the expected failure.

---

### Task 2: Implement The Configure Acceptance Summary Helper

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\commands\configure.py`
- Test: `C:\Users\darbo\Documents\HSConfig\tests\test_configure_cli.py`

**Interfaces:**
- Consumes:
  - `operator_summary: Mapping[str, Any]`
  - `validate_status: int`
  - `apply_requested: bool`
  - `apply_status: int | None`
  - `config_quality_summary: Mapping[str, Any]`
- Produces:
  - `_build_acceptance_summary(...) -> dict[str, Any]`
  - A compact dictionary for `configure_summary.json`; it does not write files and does not mutate inputs.

- [ ] **Step 1: Add the helper below `_build_config_quality_summary` in `configure.py`**

Insert this function after `_build_config_quality_summary` and before `_first_source_status_reason`:

```python
def _build_acceptance_summary(
    *,
    operator_summary: Mapping[str, Any],
    validate_status: int,
    apply_requested: bool,
    apply_status: int | None,
    config_quality_summary: Mapping[str, Any],
) -> dict[str, Any]:
    runtime_contract = operator_summary.get("runtime_apply_contract", {})
    if not isinstance(runtime_contract, Mapping):
        runtime_contract = {}

    normal_apply_authority = str(
        runtime_contract.get("apply_authority") or "reports/operator_summary.json"
    )
    runtime_apply_allowed = bool(operator_summary.get("runtime_apply_allowed", False))
    runtime_apply_mode = str(operator_summary.get("runtime_apply_mode", ""))
    technical_status = str(operator_summary.get("technical_status", ""))
    source_status_apply_blocking = bool(
        operator_summary.get("source_status_apply_blocking", False)
    )
    default_only_runtime_surfaces = [
        str(surface)
        for surface in operator_summary.get("default_only_runtime_surfaces", [])
        if str(surface)
    ]
    problem_checks = [
        str(check)
        for check in config_quality_summary.get("problem_checks", [])
        if str(check)
    ]

    validation_passed = validate_status == 0
    apply_passed = (not apply_requested) or apply_status == 0
    use_config_now = (
        technical_status == "VALID_PACKAGE"
        and runtime_apply_allowed
        and runtime_apply_mode == "load_safe_apply"
        and validation_passed
        and apply_passed
    )

    if not use_config_now:
        next_report_to_open = "reports/operator_summary.json"
        interpretation = (
            "Package is not usable now; inspect reports/operator_summary.json first."
        )
    elif problem_checks or default_only_runtime_surfaces:
        next_report_to_open = "reports/contract_doctor.json"
        interpretation = (
            "Package is usable now according to reports/operator_summary.json; "
            "source and config-quality details remain diagnostic."
        )
    else:
        next_report_to_open = normal_apply_authority
        interpretation = (
            "Package is usable now according to reports/operator_summary.json; "
            "source and config-quality details remain diagnostic."
        )

    return {
        "schema_version": 1,
        "use_config_now": use_config_now,
        "normal_apply_authority": normal_apply_authority,
        "runtime_apply_allowed": runtime_apply_allowed,
        "runtime_apply_mode": runtime_apply_mode,
        "technical_status": technical_status,
        "validation_status": "passed" if validation_passed else "failed",
        "apply_requested": apply_requested,
        "apply_status": apply_status,
        "source_strength": str(operator_summary.get("source_backed_status", "")),
        "source_gaps_apply_blocking": source_status_apply_blocking,
        "default_only_clean": not default_only_runtime_surfaces,
        "default_only_runtime_surfaces": default_only_runtime_surfaces,
        "config_quality_status": str(config_quality_summary.get("status", "")),
        "config_quality_problem_checks": problem_checks,
        "first_missing_source_action": operator_summary.get("first_missing_source_action"),
        "next_report_to_open": next_report_to_open,
        "interpretation": interpretation,
    }
```

- [ ] **Step 2: Run the targeted unit tests**

Run:

```powershell
pytest tests\test_configure_cli.py::test_build_acceptance_summary_marks_load_safe_package_usable tests\test_configure_cli.py::test_build_acceptance_summary_surfaces_diagnostics_without_blocking tests\test_configure_cli.py::test_build_acceptance_summary_marks_non_load_safe_package_unusable -q
```

Expected:

```text
3 passed
```

- [ ] **Step 3: Commit Task 1 and Task 2 together**

Run:

```powershell
git add src\hsconfig\commands\configure.py tests\test_configure_cli.py
git commit -m "feat: add configure acceptance summary helper"
```

Expected: commit succeeds.

---

### Task 3: Write The Acceptance Summary Into `configure_summary.json`

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\commands\configure.py`
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_configure_cli.py`

**Interfaces:**
- Consumes: `_build_acceptance_summary(...)` from Task 2.
- Produces: top-level `configure_summary.json["acceptance_summary"]`.

- [ ] **Step 1: Extend the existing configure CLI clean-summary test**

In `test_configure_writes_diagnostic_config_quality_summary`, after the existing `assert summary["config_quality_summary"] == {...}` block and before `assert "config_quality_summary" not in operator_summary`, add:

```python
    assert summary["acceptance_summary"] == {
        "schema_version": 1,
        "use_config_now": True,
        "normal_apply_authority": "reports/operator_summary.json",
        "runtime_apply_allowed": True,
        "runtime_apply_mode": "load_safe_apply",
        "technical_status": "VALID_PACKAGE",
        "validation_status": "passed",
        "apply_requested": False,
        "apply_status": None,
        "source_strength": operator_summary["source_backed_status"],
        "source_gaps_apply_blocking": False,
        "default_only_clean": True,
        "default_only_runtime_surfaces": [],
        "config_quality_status": "clean",
        "config_quality_problem_checks": [],
        "first_missing_source_action": operator_summary["first_missing_source_action"],
        "next_report_to_open": "reports/operator_summary.json",
        "interpretation": (
            "Package is usable now according to reports/operator_summary.json; "
            "source and config-quality details remain diagnostic."
        ),
    }
    assert "acceptance_summary" not in operator_summary
```

- [ ] **Step 2: Extend the diagnostic failure-stays-nonblocking test**

In `test_configure_quality_summary_failure_stays_diagnostic_only`, after the existing `assert summary["config_quality_summary"] == {...}` block and before `assert len(apply_calls) == 1`, add:

```python
    assert summary["acceptance_summary"]["use_config_now"] is True
    assert summary["acceptance_summary"]["source_gaps_apply_blocking"] is False
    assert summary["acceptance_summary"]["config_quality_status"] == "attention"
    assert summary["acceptance_summary"]["config_quality_problem_checks"] == [
        "config_quality_summary_failed"
    ]
    assert summary["acceptance_summary"]["next_report_to_open"] == (
        "reports/contract_doctor.json"
    )
    assert summary["acceptance_summary"]["interpretation"] == (
        "Package is usable now according to reports/operator_summary.json; "
        "source and config-quality details remain diagnostic."
    )
```

- [ ] **Step 3: Run the two integration tests and confirm failure**

Run:

```powershell
pytest tests\test_configure_cli.py::test_configure_writes_diagnostic_config_quality_summary tests\test_configure_cli.py::test_configure_quality_summary_failure_stays_diagnostic_only -q
```

Expected: FAIL with `KeyError: 'acceptance_summary'`.

- [ ] **Step 4: Add `acceptance_summary` to the final `_finish` payload**

In `configure_payload`, immediately after:

```python
    config_quality_summary = _build_config_quality_summary(package_dir)
```

keep the existing validation and apply blocks unchanged. Then, in the final `_finish(..., "OK", {...})` payload, add this field after `"config_quality_summary": config_quality_summary,`:

```python
            "acceptance_summary": _build_acceptance_summary(
                operator_summary=operator_summary,
                validate_status=validate_status,
                apply_requested=bool(getattr(args, "apply", False)),
                apply_status=apply_status,
                config_quality_summary=config_quality_summary,
            ),
```

The surrounding payload should keep these existing fields unchanged:

```python
            "config_quality_summary": config_quality_summary,
            "acceptance_summary": _build_acceptance_summary(
                operator_summary=operator_summary,
                validate_status=validate_status,
                apply_requested=bool(getattr(args, "apply", False)),
                apply_status=apply_status,
                config_quality_summary=config_quality_summary,
            ),
            "apply_performed": bool(getattr(args, "apply", False)),
            "apply_status": apply_status,
```

- [ ] **Step 5: Run the two integration tests**

Run:

```powershell
pytest tests\test_configure_cli.py::test_configure_writes_diagnostic_config_quality_summary tests\test_configure_cli.py::test_configure_quality_summary_failure_stays_diagnostic_only -q
```

Expected:

```text
2 passed
```

- [ ] **Step 6: Commit Task 3**

Run:

```powershell
git add src\hsconfig\commands\configure.py tests\test_configure_cli.py
git commit -m "feat: expose configure acceptance summary"
```

Expected: commit succeeds.

---

### Task 4: Add A Boundary Sentinel So Acceptance Summary Cannot Become A Gate

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_configure_cli.py`

**Interfaces:**
- Consumes: `configure.py` source text.
- Produces: a regression test proving the acceptance helper remains a configure-output projection and is not imported by apply, package builder, or acceptance matrix code.

- [ ] **Step 1: Add the source-boundary test near the helper tests**

Add this test near the other acceptance-summary tests:

```python
def test_acceptance_summary_helper_stays_configure_local_projection() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    configure_source = (
        repo_root / "src" / "hsconfig" / "commands" / "configure.py"
    ).read_text(encoding="utf-8")
    apply_source = (
        repo_root / "src" / "hsconfig" / "commands" / "apply.py"
    ).read_text(encoding="utf-8")
    apply_gate_source = (
        repo_root / "src" / "hsconfig" / "apply_gate.py"
    ).read_text(encoding="utf-8")
    acceptance_matrix_source = (
        repo_root / "src" / "hsconfig" / "acceptance_matrix.py"
    ).read_text(encoding="utf-8")

    assert "def _build_acceptance_summary(" in configure_source
    assert "_build_acceptance_summary" not in apply_source
    assert "_build_acceptance_summary" not in apply_gate_source
    assert "_build_acceptance_summary" not in acceptance_matrix_source
```

- [ ] **Step 2: Run the boundary test**

Run:

```powershell
pytest tests\test_configure_cli.py::test_acceptance_summary_helper_stays_configure_local_projection -q
```

Expected:

```text
1 passed
```

- [ ] **Step 3: Commit Task 4**

Run:

```powershell
git add tests\test_configure_cli.py
git commit -m "test: guard configure acceptance summary boundary"
```

Expected: commit succeeds.

---

### Task 5: Run Focused And Full Verification

**Files:**
- No source changes expected.
- Verification only.

**Interfaces:**
- Consumes: all changes from Tasks 1-4.
- Produces: evidence that Configure behavior is correct and worktree remains clean after commits.

- [ ] **Step 1: Run focused configure tests**

Run:

```powershell
pytest tests\test_configure_cli.py -q
```

Expected:

```text
passed
```

The exact test count may vary; there must be no failures.

- [ ] **Step 2: Run acceptance and apply boundary tests**

Run:

```powershell
pytest tests\test_acceptance_matrix.py tests\test_apply_authority_boundary.py tests\test_apply_gate.py -q
```

Expected:

```text
passed
```

The exact test count may vary; there must be no failures.

- [ ] **Step 3: Run the universal Wild no-block regression**

Run:

```powershell
pytest tests\test_universal_wild_no_block_matrix.py -q
```

Expected:

```text
passed
```

The exact test count may vary; there must be no failures.

- [ ] **Step 4: Run the contract preflight regression**

Run:

```powershell
pytest tests\test_contract_preflight.py -q
```

Expected:

```text
passed
```

The exact test count may vary; there must be no failures.

- [ ] **Step 5: Run the full test suite if focused tests are clean**

Run:

```powershell
pytest -q
```

Expected:

```text
passed
```

The exact test count may vary; there must be no failures.

- [ ] **Step 6: Verify currentness and clean worktree**

Run:

```powershell
git fetch --all --prune --tags
python scripts\check_hsconfig_currentness.py --cwd . --json
git status --short --branch
```

Expected currentness JSON contains:

```json
{
  "dirty": false,
  "behind_origin_main": 0,
  "clean_for_runtime_work": true
}
```

Expected `git status --short --branch` shows the branch header only, with no changed or untracked files.

---

## Self-Review

**Spec coverage:** This plan implements only the approved brainstorm recommendation: a compact Configure acceptance projection. It does not introduce gameplay logic, log analysis, HSTuner, a new report, a new runtime surface, or a new apply gate.

**Placeholder scan:** The plan avoids placeholder wording and vague test instructions. Each code-editing step includes concrete code.

**Type consistency:** `_build_acceptance_summary(...)` is defined with the same parameters used by the tests and the final `configure_payload` call. The returned field names are consistent across all planned assertions.

**Risk check:** The main technical risk is conflating this with existing `acceptance_matrix.py`. The plan avoids that by keeping the helper private to `configure.py`, writing only to top-level `configure_summary.json`, and adding a boundary sentinel that the helper is not used by apply-gate or acceptance-matrix code.

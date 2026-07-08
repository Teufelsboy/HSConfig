# HSConfig Runtime Apply Mode Clarity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `reports/operator_summary.json` impossible to misread by adding an explicit runtime apply mode that distinguishes normal apply, source-informed apply with `--allow-source-informed`, and blocked packages.

**Architecture:** Keep the existing HSConfig gate model unchanged: `operator_summary.json` remains the single operator gate, `evaluate_apply_gate()` remains authoritative before writes, and `apply_package()` continues to re-evaluate the gate before runtime mutation. Add read-facing clarity to `operator_summary.json`, docs, and tests without broadening runtime surfaces or changing source-depth promotion rules.

**Tech Stack:** Python 3, pytest, existing HSConfig package modules under `src/hsconfig`, existing Markdown operator/skill docs.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig`.
- Keep HSConfig pre-run only: no replay parsing, no winrate analysis, no HSTuner post-run logic.
- Do not add dependencies.
- Do not add normal-path `Presume.json` or `Concede.json`.
- Do not widen the 11-deck representative matrix in this plan.
- Do not relax `SOURCE_BACKED_STRONG` or `SOURCE_INFORMED_APPLY_READY` gates.
- Boarlock closure is the next fachliche wave after this plan; this plan only creates the clearer apply-mode contract it will rely on.

---

## File Structure

- `src/hsconfig/operator_summary.py`: source of `runtime_apply_mode`, `runtime_apply_allowed`, and `runtime_apply_requires_flag`.
- `src/hsconfig/operator_guidance.py`: mirrors the same mode in the nested `operator_guidance` object so human-facing next steps match the summary fields.
- `src/hsconfig/apply_gate.py`: must not trust the new read-facing fields; it continues to derive allow/block status from technical status, semantic status, next action, apply policy, readiness, generated files, and actual package files.
- `tests/test_operator_summary.py`: unit tests for the new summary fields across source-backed, source-informed, warnings, invalid, and research-required states.
- `tests/test_operator_guidance.py`: guidance tests proving safe-to-apply and required flag semantics remain aligned.
- `tests/test_apply_gate.py`: regression tests proving forged `runtime_apply_allowed=true` does not bypass the existing gate.
- `tests/test_runtime_apply.py`: direct writer tests proving `apply_package()` still rejects forged/stale gates despite the new read-facing fields.
- `docs/operator/README.md`: operator-facing explanation of the new fields.
- `.agents/skills/hsconfig/SKILL.md` and `.agents/skills/hsconfig/references/workflow.md`: installed-skill source guidance.
- `C:\Users\darbo\.codex\skills\hsconfig`: synced installed skill copy after docs change.

---

### Task 1: Add Runtime Apply Mode To Operator Summary

**Files:**
- Modify: `src/hsconfig/operator_summary.py`
- Test: `tests/test_operator_summary.py`

**Interfaces:**
- Consumes: existing `next_action`, `apply_policy`, and `source_informed_apply_readiness`.
- Produces:
  - `operator_summary["runtime_apply_mode"] -> str`
  - `operator_summary["runtime_apply_allowed"] -> bool`
  - `operator_summary["runtime_apply_requires_flag"] -> str | None`

- [ ] **Step 1: Write failing tests for all runtime apply modes**

Add or extend tests in `tests/test_operator_summary.py`:

```python
def test_operator_summary_source_backed_exposes_normal_runtime_apply_mode():
    summary = build_operator_summary(
        deck_name="StrongDeck",
        deck_code="AAE=",
        technical_validation={"status": "passed", "errors": []},
        guide_source_depth={
            "source_depth_status": "source_backed",
            "source_count": 1,
            "claim_count": 1,
            "source_evidence": {"warnings_count": 0},
        },
        unsupported_conditions=[],
        globalvalue_authority={"blocked_until_runtime_evidence": []},
        generated_files=[
            "CustomConfig/strongdeck/GlobalValues.json",
            "CustomConfig/strongdeck/Mulligan.json",
            "CustomConfig/strongdeck/EX1_001.json",
        ],
        claim_coverage_report={
            "summary": {
                "guide_backed": 1,
                "static_semantics_backfilled": 0,
                "uncovered_low_confidence": 0,
            },
            "uncovered_cards": [],
        },
        config_readiness_summary={
            "total_cards": 1,
            "runtime_emitted": 1,
            "generic_low_confidence": 0,
            "cards_needing_guide_claims": 0,
            "cards_needing_runtime_surface": 0,
            "cards_needing_mulligan_claims": 0,
            "cards_needing_combo_sequence": 0,
            "cards_needing_condition_lowering": 0,
            "cards_needing_mechanic_lowering": 0,
        },
        claim_conflict_report={"conflict_count": 0, "conflicts": []},
    )

    assert summary["semantic_status"] == "SOURCE_BACKED_STRONG"
    assert summary["next_action"] == "READY_TO_APPLY_OR_HANDOFF"
    assert summary["apply_policy"] == "ALLOWED"
    assert summary["runtime_apply_mode"] == "normal_apply"
    assert summary["runtime_apply_allowed"] is True
    assert summary["runtime_apply_requires_flag"] is None
```

Add assertions to the existing source-informed tests:

```python
assert summary["runtime_apply_mode"] == "source_informed_apply_requires_flag"
assert summary["runtime_apply_allowed"] is True
assert summary["runtime_apply_requires_flag"] == "--allow-source-informed"
```

Add assertions to existing `ALLOWED_WITH_WARNINGS`, invalid, and research-required tests:

```python
assert summary["runtime_apply_mode"] == "blocked"
assert summary["runtime_apply_allowed"] is False
assert summary["runtime_apply_requires_flag"] is None
```

- [ ] **Step 2: Run operator summary tests and verify failure**

Run:

```powershell
python -m pytest tests\test_operator_summary.py -q
```

Expected: FAIL because the new fields are not present.

- [ ] **Step 3: Implement the helper in `operator_summary.py`**

Add a helper near `_next_action_and_policy`:

```python
def _runtime_apply_contract(
    *,
    next_action: str,
    apply_policy: str,
    source_informed_apply_readiness: dict[str, Any],
) -> tuple[str, bool, str | None]:
    if next_action == "READY_TO_APPLY_OR_HANDOFF" and apply_policy == "ALLOWED":
        return "normal_apply", True, None
    if (
        next_action == "SOURCE_INFORMED_APPLY_READY"
        and apply_policy == "ALLOWED_SOURCE_INFORMED"
        and source_informed_apply_readiness.get("status") == "ready"
    ):
        return "source_informed_apply_requires_flag", True, "--allow-source-informed"
    return "blocked", False, None
```

Call it after `_next_action_and_policy(...)`:

```python
runtime_apply_mode, runtime_apply_allowed, runtime_apply_requires_flag = (
    _runtime_apply_contract(
        next_action=next_action,
        apply_policy=apply_policy,
        source_informed_apply_readiness=source_informed_apply_readiness,
    )
)
```

Add these fields to `summary` immediately after `apply_policy`:

```python
"runtime_apply_mode": runtime_apply_mode,
"runtime_apply_allowed": runtime_apply_allowed,
"runtime_apply_requires_flag": runtime_apply_requires_flag,
```

- [ ] **Step 4: Run operator summary tests and verify pass**

Run:

```powershell
python -m pytest tests\test_operator_summary.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 1**

```powershell
git add src\hsconfig\operator_summary.py tests\test_operator_summary.py
git commit -m "feat: expose runtime apply mode in operator summary"
```

---

### Task 2: Align Operator Guidance Without Weakening Apply Gate

**Files:**
- Modify: `src/hsconfig/operator_guidance.py`
- Modify: `src/hsconfig/apply_gate.py` only if test fixtures need returned gate diagnostics; do not use `runtime_apply_allowed` as a gate input.
- Test: `tests/test_operator_guidance.py`
- Test: `tests/test_apply_gate.py`
- Test: `tests/test_runtime_apply.py`

**Interfaces:**
- Consumes: `runtime_apply_mode`, `runtime_apply_allowed`, `runtime_apply_requires_flag`.
- Produces: `operator_guidance["runtime_apply_mode"]`, `operator_guidance["runtime_apply_allowed"]`, `operator_guidance["runtime_apply_requires_flag"]`.

- [ ] **Step 1: Write failing operator guidance tests**

Extend `tests/test_operator_guidance.py` with assertions in source-backed, source-informed, and warning cases:

```python
assert guidance["runtime_apply_mode"] == "normal_apply"
assert guidance["runtime_apply_allowed"] is True
assert guidance["runtime_apply_requires_flag"] is None
```

For source-informed:

```python
assert guidance["runtime_apply_mode"] == "source_informed_apply_requires_flag"
assert guidance["runtime_apply_allowed"] is True
assert guidance["runtime_apply_requires_flag"] == "--allow-source-informed"
```

For warning/blocked cases:

```python
assert guidance["runtime_apply_mode"] == "blocked"
assert guidance["runtime_apply_allowed"] is False
assert guidance["runtime_apply_requires_flag"] is None
```

- [ ] **Step 2: Write a gate-forgery regression test**

Add to `tests/test_apply_gate.py`:

```python
def test_apply_gate_ignores_forged_runtime_apply_allowed_field(tmp_path: Path):
    package = tmp_path / "package"
    deck = package / "CustomConfig" / "deck"
    deck.mkdir(parents=True)
    write_json(deck / "GlobalValues.json", {"GameCardId": "GlobalValues"})
    write_json(deck / "Mulligan.json", {"GameCardId": "Mulligan", "Mulligan": {"values": []}})
    write_json(deck / "EX1_001.json", {"GameCardId": "EX1_001"})
    _write_operator_summary(
        package,
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "VALID_BUT_NOT_GUIDE_STRONG",
            "next_action": "IMPROVE_GUIDE_SOURCES_BEFORE_STRONG_APPLY",
            "apply_policy": "ALLOWED_WITH_WARNINGS",
            "runtime_apply_mode": "normal_apply",
            "runtime_apply_allowed": True,
            "runtime_apply_requires_flag": None,
            "semantic_blockers": [{"reason": "cards_need_guide_claims"}],
            "generated_files": [
                "CustomConfig\\deck\\GlobalValues.json",
                "CustomConfig\\deck\\Mulligan.json",
                "CustomConfig\\deck\\EX1_001.json",
            ],
        },
    )

    gate = evaluate_apply_gate(package)

    assert gate["allowed"] is False
    assert gate["reasons"][0]["reason"] == "operator_summary_not_ready_to_apply"
```

- [ ] **Step 3: Run tests and verify failure**

Run:

```powershell
python -m pytest tests\test_operator_guidance.py tests\test_apply_gate.py::test_apply_gate_ignores_forged_runtime_apply_allowed_field -q
```

Expected: guidance tests FAIL until guidance includes the new fields; gate-forgery test should PASS if the new field is not mistakenly used.

- [ ] **Step 4: Implement guidance mirroring**

Add this helper in `src/hsconfig/operator_guidance.py`:

```python
def _runtime_apply_fields(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "runtime_apply_mode": summary.get("runtime_apply_mode", "blocked"),
        "runtime_apply_allowed": bool(summary.get("runtime_apply_allowed", False)),
        "runtime_apply_requires_flag": summary.get("runtime_apply_requires_flag"),
    }
```

Merge it into every returned dict:

```python
return {
    "first_report_to_open": "reports/operator_summary.json",
    ...
    **_runtime_apply_fields(summary),
}
```

Do not modify `evaluate_apply_gate()` to trust `runtime_apply_allowed`.

- [ ] **Step 5: Run focused tests**

Run:

```powershell
python -m pytest tests\test_operator_guidance.py tests\test_apply_gate.py tests\test_runtime_apply.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 2**

```powershell
git add src\hsconfig\operator_guidance.py tests\test_operator_guidance.py tests\test_apply_gate.py tests\test_runtime_apply.py
git commit -m "test: keep runtime apply mode read-only for gates"
```

---

### Task 3: Update Operator Docs And Installed Skill Guidance

**Files:**
- Modify: `docs/operator/README.md`
- Modify: `.agents/skills/hsconfig/SKILL.md`
- Modify: `.agents/skills/hsconfig/references/workflow.md`
- Potentially modify: `tests/test_skill_files.py`, `tests/test_docs_active_path.py`
- Run: `scripts/sync_installed_skill.py`

**Interfaces:**
- Consumes: summary fields from Task 1.
- Produces: operator-facing wording that `runtime_apply_mode` is descriptive and `apply_gate` remains authoritative.

- [ ] **Step 1: Write or update docs tests first**

Extend `tests/test_skill_files.py` or `tests/test_docs_active_path.py` with assertions:

```python
assert "runtime_apply_mode" in operator_docs
assert "runtime_apply_allowed" in operator_docs
assert "ALLOWED_WITH_WARNINGS is not runtime write permission" in operator_docs
```

Use the exact casing chosen in docs.

- [ ] **Step 2: Run docs tests and verify failure**

Run:

```powershell
python -m pytest tests\test_skill_files.py tests\test_docs_active_path.py -q
```

Expected: FAIL until docs mention the new fields.

- [ ] **Step 3: Update `docs/operator/README.md`**

Add under `## Single Gate`:

```markdown
Runtime apply readability fields:

- `runtime_apply_mode=normal_apply` means normal `hsconfig apply --json` is allowed.
- `runtime_apply_mode=source_informed_apply_requires_flag` means runtime apply is allowed only with `--allow-source-informed`.
- `runtime_apply_mode=blocked` means no runtime write should happen.
- `runtime_apply_allowed=true` is descriptive; the CLI and `apply_package()` still re-evaluate the gate before writing.
- `apply_policy=ALLOWED_WITH_WARNINGS` is not runtime write permission.
```

- [ ] **Step 4: Update skill guidance**

In `.agents/skills/hsconfig/SKILL.md`, add one concise rule:

```markdown
- Read `runtime_apply_mode`, `runtime_apply_allowed`, and `runtime_apply_requires_flag` in `operator_summary.json`; never treat `ALLOWED_WITH_WARNINGS` as runtime write permission.
```

In `.agents/skills/hsconfig/references/workflow.md`, add the same concept near readiness interpretation:

```markdown
`runtime_apply_mode` is the human-readable write mode. It is descriptive; `hsconfig apply` and `apply_package()` still re-evaluate the operator gate before writing.
```

- [ ] **Step 5: Sync installed skill**

Run:

```powershell
python scripts\sync_installed_skill.py
python scripts\sync_installed_skill.py --check
```

Expected: second command prints `HSConfig skill is in sync: C:\Users\darbo\.codex\skills\hsconfig`.

- [ ] **Step 6: Run docs and skill tests**

Run:

```powershell
python -m pytest tests\test_skill_files.py tests\test_docs_active_path.py tests\test_cli_help.py tests\test_scope_boundaries.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit Task 3**

```powershell
git add docs\operator\README.md .agents\skills\hsconfig tests\test_skill_files.py tests\test_docs_active_path.py C:\Users\darbo\.codex\skills\hsconfig
git commit -m "docs: clarify runtime apply mode for operators"
```

Note: if Git refuses staging outside the repo for `C:\Users\darbo\.codex\skills\hsconfig`, do not force it. The installed skill is a local sync target, not a repo artifact. Commit only repo files and report the installed-skill sync check.

---

### Task 4: Final Verification And Boarlock Handoff

**Files:**
- Read: `docs/operator/source-backed-strong-closure.md`
- Read: `docs/operator/archetype-fixture-matrix.json`
- No Boarlock source fixture edits in this plan.

**Interfaces:**
- Consumes: all fields and docs from Tasks 1-3.
- Produces: verified repo state and a concrete next implementation target.

- [ ] **Step 1: Run focused verification**

Run:

```powershell
python -m pytest tests\test_operator_summary.py tests\test_operator_guidance.py tests\test_apply_gate.py tests\test_runtime_apply.py tests\test_skill_files.py tests\test_docs_active_path.py -q
```

Expected: PASS.

- [ ] **Step 2: Run matrix and closure verification**

Run:

```powershell
python -m pytest tests\test_matrix_current_truth.py tests\test_matrix_visibility.py tests\test_fixture_source_depth_closure.py tests\test_source_informed_closure_contract.py -q
```

Expected: PASS.

- [ ] **Step 3: Run full test suite if focused tests pass**

Run:

```powershell
python -m pytest -q
```

Expected: PASS. If runtime exceeds local limits, record the exact timeout and preserve focused test evidence.

- [ ] **Step 4: Verify installed skill and Git state**

Run:

```powershell
python scripts\sync_installed_skill.py --check
git status --short --branch
```

Expected:

```text
HSConfig skill is in sync: C:\Users\darbo\.codex\skills\hsconfig
## main...origin/main
```

or a clean branch ahead of `origin/main` if the implementation has not yet been pushed.

- [ ] **Step 5: Commit final verification adjustments if needed**

Only if Task 4 required test/doc edits:

```powershell
git add <changed-files>
git commit -m "chore: verify runtime apply mode contract"
```

- [ ] **Step 6: Record the next implementation target**

The next implementation plan after this wave should be Boarlock closure:

```text
Target: Boarlock source-depth closure.
First missing chain: WW_092 Fracking -> needs_mulligan_claim -> add_mulligan_keep_or_discard_claim.
Do not force a weak Fracking claim.
Keep Combo.json exact-sequence-only.
If exact Boarlock Fracking mulligan evidence remains unavailable, preserve Boarlock as a durable source-informed control and move the next closure slot to Kingslayer.
```

Do not edit Boarlock fixture files in this runtime-apply-mode plan.

---

## Self-Review

- Spec coverage: The plan implements the recommended small Apply/Operator clarity fix and leaves Boarlock as the next fachliche wave.
- Placeholder scan: No placeholder steps are intentionally left; each task includes exact files, commands, and expected outcomes.
- Type consistency: `runtime_apply_mode`, `runtime_apply_allowed`, and `runtime_apply_requires_flag` are introduced in Task 1, mirrored in Task 2, documented in Task 3, and verified in Task 4.
- Scope check: The plan does not broaden runtime surfaces, does not alter source-depth promotion thresholds, does not widen the deck matrix, and does not pull HSTuner concerns into HSConfig.

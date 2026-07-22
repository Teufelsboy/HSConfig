# HSConfig Slim Config Signal Hygiene Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tighten the HSConfig-only normal path by fixing the fresh-config command guidance, surfacing semantic-intent diagnostics in the first-read acceptance summary, and removing small drift hazards without changing runtime generation semantics.

**Architecture:** Keep `hsconfig configure` as the normal operator entry point and keep `reports/operator_summary.json` as the single runtime apply authority. The changes are documentation-and-projection polish plus behavior-neutral registry/helper hardening; they do not add runtime surfaces, source gates, log analysis, HSTuner, or gameplay tuning.

**Tech Stack:** Python 3, pytest, Markdown skill/operator docs, existing HSConfig CLI modules under `src/hsconfig`.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig`.
- Before implementation, run `git fetch --all --prune --tags`, `git remote prune origin`, and `python scripts/check_hsconfig_currentness.py --cwd . --json`.
- Start and finish from a clean worktree; do not leave uncommitted changes.
- Do not add replay parsing, HDT parsing, winrate validation, candidate promotion, or post-run tuning.
- Do not invoke or propose HSTuner.
- Do not add new runtime surfaces; normal HSConfig runtime output remains `GlobalValues.json`, `Mulligan.json`, per-card `<CARDID>.json`, and `Combo.json` only for complete source-backed combo claims.
- `reports/operator_summary.json` remains the only normal runtime apply authority.
- `SOURCE_BACKED_STRONG`, source status, config quality, mechanic visibility, and semantic-intent fields remain diagnostic labels, not apply gates.
- `source_status_apply_blocking` must remain `false` for source-quality work.
- Keep generated runtime packages under ignored `outputs/`; do not commit generated packages, logs, replay files, HDT files, runtime evidence, caches, or backups.

---

## File Structure

- Modify `C:\Users\darbo\Documents\HSConfig\.agents\skills\hsconfig\SKILL.md`: correct the recommended fresh source-backed configure command so it includes the required `--runtime-root`, `--out`, and `--json` arguments.
- Modify `C:\Users\darbo\Documents\HSConfig\.agents\skills\hsconfig\references\workflow.md`: keep the workflow reference command identical to the skill command.
- Modify `C:\Users\darbo\Documents\HSConfig\tests\test_skill_files.py`: add a documentation contract test for the complete fresh configure command.
- Modify `C:\Users\darbo\Documents\HSConfig\src\hsconfig\commands\configure.py`: project existing semantic-intent diagnostic fields from `config_quality_summary` into `acceptance_summary` when present.
- Modify `C:\Users\darbo\Documents\HSConfig\tests\test_configure_cli.py`: add/adjust acceptance-summary tests for the semantic-intent projection.
- Modify `C:\Users\darbo\Documents\HSConfig\src\hsconfig\mechanic_support.py`: return defensive copies from `support_for_roles()`.
- Modify `C:\Users\darbo\Documents\HSConfig\tests\test_mechanic_support.py`: add mutation-safety coverage for registered mechanic support rows.
- Modify `C:\Users\darbo\Documents\HSConfig\src\hsconfig\operator_summary.py`: remove the earlier duplicate `_string_list()` helper and keep the later broader implementation.
- Modify `C:\Users\darbo\Documents\HSConfig\tests\test_operator_summary.py`: add a source-shape regression test that permits only one `_string_list()` helper definition.

---

### Task 1: Fix Fresh Configure Command Guidance

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\.agents\skills\hsconfig\SKILL.md`
- Modify: `C:\Users\darbo\Documents\HSConfig\.agents\skills\hsconfig\references\workflow.md`
- Test: `C:\Users\darbo\Documents\HSConfig\tests\test_skill_files.py`

**Interfaces:**
- Consumes: existing skill text read by `tests/test_skill_files.py`.
- Produces: a single complete recommended command string protected by tests:
  `hsconfig configure --deck-name "<DeckName>" --deck-code "<DeckCode>" --runtime-root "<HearthRangerRoot>" --out "outputs/<DeckName>" --online-source --auto-source --apply --json`

- [ ] **Step 1: Write the failing documentation contract test**

Append this test near the other configure workflow tests in `C:\Users\darbo\Documents\HSConfig\tests\test_skill_files.py`:

```python
def test_skill_and_workflow_show_complete_fresh_configure_command() -> None:
    skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    workflow = (SKILL_ROOT / "references" / "workflow.md").read_text(
        encoding="utf-8"
    )
    expected_command = (
        'hsconfig configure --deck-name "<DeckName>" '
        '--deck-code "<DeckCode>" --runtime-root "<HearthRangerRoot>" '
        '--out "outputs/<DeckName>" --online-source --auto-source --apply --json'
    )
    incomplete_command = (
        'hsconfig configure --deck-name "<DeckName>" '
        '--deck-code "<DeckCode>" --online-source --auto-source --apply'
    )

    for text in (skill, workflow):
        assert expected_command in text
        assert incomplete_command not in text
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run:

```powershell
python -m pytest tests\test_skill_files.py::test_skill_and_workflow_show_complete_fresh_configure_command -q
```

Expected: FAIL because the complete command is not present in both skill workflow files.

- [ ] **Step 3: Update the skill command**

In `C:\Users\darbo\Documents\HSConfig\.agents\skills\hsconfig\SKILL.md`, replace the current fresh-config sentence with this exact sentence:

```markdown
For an optimal fresh deck config, prefer the source-backed path: `hsconfig configure --deck-name "<DeckName>" --deck-code "<DeckCode>" --runtime-root "<HearthRangerRoot>" --out "outputs/<DeckName>" --online-source --auto-source --apply --json`.
```

- [ ] **Step 4: Update the workflow reference command**

In `C:\Users\darbo\Documents\HSConfig\.agents\skills\hsconfig\references\workflow.md`, replace the current `Recommended fresh deck command:` line with this exact line:

```markdown
Recommended fresh deck command: `hsconfig configure --deck-name "<DeckName>" --deck-code "<DeckCode>" --runtime-root "<HearthRangerRoot>" --out "outputs/<DeckName>" --online-source --auto-source --apply --json`.
```

- [ ] **Step 5: Run the focused docs test and verify it passes**

Run:

```powershell
python -m pytest tests\test_skill_files.py::test_skill_and_workflow_show_complete_fresh_configure_command -q
```

Expected: PASS.

- [ ] **Step 6: Run the full skill-file test module**

Run:

```powershell
python -m pytest tests\test_skill_files.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit Task 1**

Run:

```powershell
git add .agents\skills\hsconfig\SKILL.md .agents\skills\hsconfig\references\workflow.md tests\test_skill_files.py
git commit -m "docs: fix hsconfig fresh configure command"
```

Expected: commit succeeds and `git status --short` is clean.

---

### Task 2: Surface Semantic Intent In Acceptance Summary

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\commands\configure.py`
- Test: `C:\Users\darbo\Documents\HSConfig\tests\test_configure_cli.py`

**Interfaces:**
- Consumes: `config_quality_summary["semantic_intent_status"]` and `config_quality_summary["semantic_intent_first_attention"]`, already produced by `_compact_config_quality_summary()`.
- Produces: optional `acceptance_summary["semantic_intent_status"]` and `acceptance_summary["semantic_intent_first_attention"]`.
- Guarantees: semantic-intent fields stay diagnostic-only and do not affect `use_config_now`, `runtime_apply_allowed`, `normal_apply_authority`, or `next_report_to_open`.

- [ ] **Step 1: Write the failing acceptance-summary test**

In `C:\Users\darbo\Documents\HSConfig\tests\test_configure_cli.py`, update `test_build_acceptance_summary_surfaces_diagnostics_without_blocking()` so `config_quality_summary` contains semantic intent fields:

```python
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
        "semantic_intent_status": "attention",
        "semantic_intent_first_attention": "card_behavior_runtime_row_missing_trace",
        "next_action": "run_contract_doctor_for_details",
    }
```

Add these assertions after the existing `config_quality_problem_checks` assertion:

```python
    assert summary["semantic_intent_status"] == "attention"
    assert summary["semantic_intent_first_attention"] == (
        "card_behavior_runtime_row_missing_trace"
    )
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run:

```powershell
python -m pytest tests\test_configure_cli.py::test_build_acceptance_summary_surfaces_diagnostics_without_blocking -q
```

Expected: FAIL with a missing `semantic_intent_status` key.

- [ ] **Step 3: Implement optional semantic-intent projection**

In `C:\Users\darbo\Documents\HSConfig\src\hsconfig\commands\configure.py`, inside `_build_acceptance_summary()`, add these local variables after `problem_checks`:

```python
    semantic_intent_status = str(
        config_quality_summary.get("semantic_intent_status") or ""
    )
    semantic_intent_first_attention = config_quality_summary.get(
        "semantic_intent_first_attention"
    )
```

Replace the direct `return { ... }` at the end of `_build_acceptance_summary()` with a local `summary` dictionary plus optional fields:

```python
    summary = {
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
    if semantic_intent_status:
        summary["semantic_intent_status"] = semantic_intent_status
    if semantic_intent_first_attention is not None:
        summary["semantic_intent_first_attention"] = str(
            semantic_intent_first_attention
        )
    return summary
```

- [ ] **Step 4: Run the focused acceptance-summary test**

Run:

```powershell
python -m pytest tests\test_configure_cli.py::test_build_acceptance_summary_surfaces_diagnostics_without_blocking -q
```

Expected: PASS.

- [ ] **Step 5: Run configure CLI tests**

Run:

```powershell
python -m pytest tests\test_configure_cli.py -q
```

Expected: PASS. Existing exact-dict tests remain valid because the new fields appear only when `config_quality_summary` includes semantic-intent values.

- [ ] **Step 6: Commit Task 2**

Run:

```powershell
git add src\hsconfig\commands\configure.py tests\test_configure_cli.py
git commit -m "feat: surface semantic intent in configure acceptance"
```

Expected: commit succeeds and `git status --short` is clean.

---

### Task 3: Return Defensive Mechanic Support Rows

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\mechanic_support.py`
- Test: `C:\Users\darbo\Documents\HSConfig\tests\test_mechanic_support.py`

**Interfaces:**
- Consumes: `support_for_roles(roles: Iterable[str]) -> list[dict[str, Any]]`.
- Produces: the same public return shape, but returned rows and nested `normal_path_surfaces` / `lowering` values are detached copies.
- Guarantees: no caller can mutate `MECHANIC_SUPPORT` through a row returned by `support_for_roles()`.

- [ ] **Step 1: Write the failing mutation-safety test**

Append this test near the existing `support_for_roles()` tests in `C:\Users\darbo\Documents\HSConfig\tests\test_mechanic_support.py`:

```python
def test_support_for_roles_returns_defensive_copies_for_registered_specs():
    first = support_for_roles(["battlecry"])
    first[0]["normal_path_surfaces"].append("MUTATED_SURFACE")
    first[0]["lowering"]["policy"] = "mutated_policy"

    second = support_for_roles(["battlecry"])

    assert "MUTATED_SURFACE" not in second[0]["normal_path_surfaces"]
    assert second[0]["lowering"]["policy"] == MECHANIC_SUPPORT["battlecry"][
        "lowering"
    ]["policy"]
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run:

```powershell
python -m pytest tests\test_mechanic_support.py::test_support_for_roles_returns_defensive_copies_for_registered_specs -q
```

Expected: FAIL because the returned nested list/dict can currently mutate registry-backed values.

- [ ] **Step 3: Add defensive copying**

In `C:\Users\darbo\Documents\HSConfig\src\hsconfig\mechanic_support.py`, add the import near the top:

```python
from copy import deepcopy
```

Then replace the unknown-mechanic `rows.append({...})` block with a `deepcopy()` wrapped append:

```python
            rows.append(
                deepcopy(
                    {
                        "mechanic": mechanic,
                        "support_level": "warning_only",
                        "normal_path_surfaces": ["report-only"],
                        "warning_boundary": (
                            "No registered VisionAI normal-path surface exists for role "
                            f"'{mechanic}'; keep it visible as warning-only until mapped."
                        ),
                        "lowering": mechanic_lowering_policy(mechanic),
                        "registered": False,
                    }
                )
            )
```

Replace the registered-mechanic append with:

```python
        rows.append({"mechanic": mechanic, **deepcopy(spec)})
```

- [ ] **Step 4: Run the focused mutation-safety test**

Run:

```powershell
python -m pytest tests\test_mechanic_support.py::test_support_for_roles_returns_defensive_copies_for_registered_specs -q
```

Expected: PASS.

- [ ] **Step 5: Run mechanic support tests**

Run:

```powershell
python -m pytest tests\test_mechanic_support.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 3**

Run:

```powershell
git add src\hsconfig\mechanic_support.py tests\test_mechanic_support.py
git commit -m "fix: copy mechanic support rows"
```

Expected: commit succeeds and `git status --short` is clean.

---

### Task 4: Remove Duplicate Operator Summary Helper

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\operator_summary.py`
- Test: `C:\Users\darbo\Documents\HSConfig\tests\test_operator_summary.py`

**Interfaces:**
- Consumes: the existing `_string_list(value: Any) -> list[str]` helper.
- Produces: exactly one `_string_list()` definition in `operator_summary.py`, keeping the later broader implementation that accepts strings and list-like containers.

- [ ] **Step 1: Write the failing source-shape test**

Append this test near the other operator summary tests in `C:\Users\darbo\Documents\HSConfig\tests\test_operator_summary.py`:

```python
def test_operator_summary_has_single_string_list_helper() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "hsconfig"
        / "operator_summary.py"
    ).read_text(encoding="utf-8")

    assert source.count("def _string_list(") == 1
```

If `Path` is not already imported in `tests/test_operator_summary.py`, add:

```python
from pathlib import Path
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run:

```powershell
python -m pytest tests\test_operator_summary.py::test_operator_summary_has_single_string_list_helper -q
```

Expected: FAIL because `operator_summary.py` currently defines `_string_list()` twice.

- [ ] **Step 3: Remove the earlier duplicate helper**

In `C:\Users\darbo\Documents\HSConfig\src\hsconfig\operator_summary.py`, delete this earlier helper block:

```python
def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item)]
```

Keep the later implementation:

```python
def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, list | tuple | set):
        return [str(item) for item in value if str(item)]
    return []
```

- [ ] **Step 4: Run the focused helper-shape test**

Run:

```powershell
python -m pytest tests\test_operator_summary.py::test_operator_summary_has_single_string_list_helper -q
```

Expected: PASS.

- [ ] **Step 5: Run operator summary tests**

Run:

```powershell
python -m pytest tests\test_operator_summary.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 4**

Run:

```powershell
git add src\hsconfig\operator_summary.py tests\test_operator_summary.py
git commit -m "refactor: keep one operator summary string helper"
```

Expected: commit succeeds and `git status --short` is clean.

---

### Task 5: Final Contract And Currentness Verification

**Files:**
- No source files changed in this task.
- Verification-only task for `C:\Users\darbo\Documents\HSConfig`.

**Interfaces:**
- Consumes: commits from Tasks 1-4.
- Produces: final evidence that the repo is current, contract-preflight passes, and the worktree is clean.

- [ ] **Step 1: Run the targeted regression suite**

Run:

```powershell
python -m pytest tests\test_skill_files.py tests\test_configure_cli.py tests\test_mechanic_support.py tests\test_operator_summary.py tests\test_config_quality_contract.py tests\test_semantic_intent_score.py tests\test_contract_preflight.py -q
```

Expected: PASS.

- [ ] **Step 2: Run currentness check**

Run:

```powershell
python scripts\check_hsconfig_currentness.py --cwd . --json
```

Expected JSON fields:

```json
{
  "dirty": false,
  "behind_origin_main": 0,
  "clean_for_runtime_work": true
}
```

- [ ] **Step 3: Run contract preflight**

Run:

```powershell
python -m hsconfig.cli contract-preflight --json
```

Expected JSON fields:

```json
{
  "status": "PASS",
  "source_status_apply_blocking": false,
  "runtime_apply_authority": "reports/operator_summary.json"
}
```

- [ ] **Step 4: Verify clean git state**

Run:

```powershell
git status --short --branch
```

Expected: branch line only, no dirty file entries.

- [ ] **Step 5: Push only when the execution request requires remote currentness**

When the execution turn explicitly asks for remote currentness, run:

```powershell
git push origin codex/hsconfig-semantic-intent-scoring
```

Expected: push succeeds as a fast-forward update for the current branch.

When the execution turn does not ask for remote currentness, do not push; report the local commit hashes and the clean worktree state.

---

## Self-Review

- Spec coverage: The plan covers the four recommended improvements from the brainstorm: complete skill command, semantic-intent acceptance projection, mechanic-support defensive copies, and duplicate helper cleanup. It explicitly excludes logs, HSTuner, new runtime surfaces, and gameplay tuning.
- Placeholder scan: The plan contains no deferred implementation markers. The angle-bracket values in the command are intentional documentation syntax already used by HSConfig docs.
- Type consistency: `semantic_intent_status` and `semantic_intent_first_attention` are read from `Mapping[str, Any]` and written to a `dict[str, Any]` only when present. `support_for_roles()` keeps its existing return type `list[dict[str, Any]]`. `_string_list(value: Any) -> list[str]` keeps the broader later helper signature.

# HSConfig No-Block Contract Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make HSConfig's no-block contract internally consistent: a valid minimal load-safe package can be applied without per-card CardID files, while normal deck preparation still emits per-card CardID coverage whenever deck cards are known.

**Architecture:** Keep the existing single-gate architecture. `apply_gate.py` and `validate_package.py` already define the minimal load-safe runtime package as `GlobalValues.json` plus `Mulligan.json`; this plan aligns `runtime_apply.py` with that contract and documents the distinction between minimal load safety and richer normal prepare output. No new pipeline, no replay analysis, no winrate analysis, and no broad refactor.

**Tech Stack:** Python package under `src/hsconfig`, pytest, existing JSON helper functions in `hsconfig.io`, existing operator docs and installed-skill sync script.

## Global Constraints

- Work only in `C:\Users\darbo\Documents\HSConfig` for the `Teufelsboy/HSConfig` repository.
- HSConfig stays pre-run only: no replay parsing, winrate analysis, runtime log analysis, candidate promotion, or HSTuner behavior.
- `reports/operator_summary.json` remains the single normal runtime-apply gate.
- `technical_status=VALID_PACKAGE` plus structurally safe files means load-safe apply, even with semantic warnings.
- Minimal load-safe runtime files are `GlobalValues.json` and `Mulligan.json`.
- Per-card `<CARDID>.json` files remain expected rich output from normal `prepare`, but must not be a hard runtime-apply prerequisite for a valid minimal package.
- `Combo.json` remains optional and emitted only when concrete combo rows exist.
- `Presume.json` and `Concede.json` remain blocked normal-path surfaces.
- Warning-only and partial mechanics are descriptive and non-blocking.
- No new dependencies.
- Do not commit private HearthRanger runtime logs, HDT files, replay files, or local runtime evidence.

---

## File Structure

- Modify `C:\Users\darbo\Documents\HSConfig\tests\test_runtime_apply.py`
  - Add a minimal package fixture that intentionally has no per-card CardID files.
  - Prove direct `apply_package()` and CLI `hsconfig apply` accept it when the operator gate allows `load_safe_apply`.
  - Keep existing incomplete-package tests hard for missing `Mulligan.json`, missing validation reports, forged gates, stale receipts, invalid JSON, and runtime drift.

- Modify `C:\Users\darbo\Documents\HSConfig\src\hsconfig\runtime_apply.py`
  - Update `_validate_complete_source_dir()` so it requires only `GlobalValues.json` and `Mulligan.json`.
  - Do not remove validation of the full package; `validate_config_package(..., require_complete_package=True)` still runs before source copy.

- Modify `C:\Users\darbo\Documents\HSConfig\docs\operator\README.md`
  - Add a precise note under "Load Safety vs. Config Richness" explaining minimal load safety versus normal prepare richness.

- Modify `C:\Users\darbo\Documents\HSConfig\docs\operator\universal-wild-no-block-contract.md`
  - Add the same distinction in the durable no-block contract.

- Modify `C:\Users\darbo\Documents\HSConfig\.agents\skills\hsconfig\SKILL.md`
  - Add a concise rule: CardID files are rich normal output, not the minimal load-safe apply requirement.

- Run `C:\Users\darbo\Documents\HSConfig\scripts\sync_installed_skill.py`
  - Sync the installed skill at `C:\Users\darbo\.codex\skills\hsconfig\SKILL.md` so byte-level drift is removed.

---

### Task 1: Runtime-Apply Minimal Package TDD

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_runtime_apply.py`

**Interfaces:**
- Consumes: `apply_package(package_root: Path, runtime_root: Path, ...) -> dict`
- Consumes: existing helper `_write_validation_reports(package: Path, globalvalues: dict) -> None`
- Produces: Regression tests proving runtime apply no longer requires per-card CardID files for minimal load-safe packages.

- [ ] **Step 1: Add a minimal package helper without CardID files**

Add this helper after `_complete_package(...)`:

```python
def _minimal_load_safe_package_without_cardid(tmp_path: Path) -> Path:
    package = tmp_path / "minimal-package"
    deck = package / "CustomConfig" / "deck"
    globalvalues = {"GameCardId": "GlobalValues", "ConfigComment": "minimal"}
    write_json(deck / "GlobalValues.json", globalvalues)
    write_json(
        deck / "Mulligan.json",
        {
            "GameCardId": "Mulligan",
            "ConfigComment": "minimal",
            "Mulligan": {"values": []},
        },
    )
    _write_validation_reports(package, globalvalues)
    write_json(
        package / "reports" / "input_manifest.json",
        {"deck_name": "Minimal Deck", "deck_code": "fixture", "runtime_root": "unused"},
    )
    write_json(
        package / "reports" / "operator_summary.json",
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "VALID_BUT_NOT_GUIDE_STRONG",
            "next_action": "READY_TO_APPLY_WITH_WARNINGS",
            "apply_policy": "ALLOWED_WITH_WARNINGS",
            "runtime_apply_mode": "load_safe_apply",
            "runtime_apply_allowed": True,
            "runtime_apply_requires_flag": None,
            "semantic_blockers": [{"reason": "load_safe_but_thin"}],
            "generated_files": [
                "CustomConfig\\deck\\GlobalValues.json",
                "CustomConfig\\deck\\Mulligan.json",
            ],
            "config_usefulness": {
                "status": "load_safe_but_thin",
                "runtime_permission_impact": "none",
            },
        },
    )
    return package
```

- [ ] **Step 2: Add direct runtime-apply test**

Add this test after `test_apply_package_applies_valid_warning_package_without_source_informed_flag(...)`:

```python
def test_apply_package_applies_minimal_load_safe_package_without_cardid(
    tmp_path: Path,
):
    package = _minimal_load_safe_package_without_cardid(tmp_path)
    runtime = tmp_path / "runtime"

    receipt = apply_package(package_root=package, runtime_root=runtime)

    assert receipt["status"] == "applied"
    assert receipt["runtime_write_performed"] is True
    assert receipt["apply_gate"]["mode"] == "load_safe_apply"
    assert receipt["copied_files"] == ["GlobalValues.json", "Mulligan.json"]
    assert (runtime / "CustomConfig" / "deck" / "GlobalValues.json").exists()
    assert (runtime / "CustomConfig" / "deck" / "Mulligan.json").exists()
    assert not (runtime / "CustomConfig" / "deck" / "EX1_001.json").exists()
```

- [ ] **Step 3: Add CLI runtime-apply test**

Add this test after `test_apply_cli_applies_valid_warning_package_without_source_informed_flag(...)`:

```python
def test_apply_cli_applies_minimal_load_safe_package_without_cardid(
    tmp_path: Path,
    capsys,
):
    from hsconfig.cli import main

    package = _minimal_load_safe_package_without_cardid(tmp_path)
    runtime = tmp_path / "runtime"

    code = main(
        [
            "apply",
            "--package",
            str(package),
            "--runtime-root",
            str(runtime),
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload["status"] == "applied"
    assert payload["apply_gate"]["mode"] == "load_safe_apply"
    assert payload["copied_files"] == ["GlobalValues.json", "Mulligan.json"]
    assert (runtime / "CustomConfig" / "deck" / "GlobalValues.json").exists()
    assert (runtime / "CustomConfig" / "deck" / "Mulligan.json").exists()
```

- [ ] **Step 4: Run tests and verify they fail for the right reason**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_runtime_apply.py::test_apply_package_applies_minimal_load_safe_package_without_cardid tests/test_runtime_apply.py::test_apply_cli_applies_minimal_load_safe_package_without_cardid -q
```

Expected before implementation: both tests fail with a runtime apply validation error that mentions the package is incomplete or missing `<CardID>.json`.

- [ ] **Step 5: Commit failing tests only if using checkpoint commits**

If the executor is using red/green commits, commit now:

```powershell
git add tests/test_runtime_apply.py
git commit -m "test: cover minimal load-safe runtime apply"
```

If the executor prefers one commit for the full task, skip this commit and continue.

---

### Task 2: Align Runtime Apply With Minimal Load-Safe Contract

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\runtime_apply.py`

**Interfaces:**
- Consumes: `_validate_complete_source_dir(source_dir: Path) -> None`
- Produces: Runtime apply source validation that matches `apply_gate.REQUIRED_RUNTIME_FILES`.

- [ ] **Step 1: Replace CardID hard requirement**

In `src/hsconfig/runtime_apply.py`, replace `_validate_complete_source_dir(...)` with:

```python
def _validate_complete_source_dir(source_dir: Path) -> None:
    missing = []
    if not (source_dir / "GlobalValues.json").is_file():
        missing.append("GlobalValues.json")
    if not (source_dir / "Mulligan.json").is_file():
        missing.append("Mulligan.json")
    if missing:
        raise ValueError(
            f"Incomplete package deck config {source_dir}: missing {', '.join(missing)}"
        )
```

Do not add new CardID validation here. CardID richness is covered by normal `prepare` and matrix tests, not this minimal source-dir guard.

- [ ] **Step 2: Run new targeted tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_runtime_apply.py::test_apply_package_applies_minimal_load_safe_package_without_cardid tests/test_runtime_apply.py::test_apply_cli_applies_minimal_load_safe_package_without_cardid -q
```

Expected: `2 passed`.

- [ ] **Step 3: Run runtime apply regression file**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_runtime_apply.py -q
```

Expected: all tests in `tests/test_runtime_apply.py` pass. Existing incomplete-source tests must still fail safely when `Mulligan.json`, validation reports, operator summary, fake receipt, or runtime state are invalid.

- [ ] **Step 4: Commit runtime contract fix**

```powershell
git add src/hsconfig/runtime_apply.py tests/test_runtime_apply.py
git commit -m "fix: allow minimal load-safe runtime apply"
```

---

### Task 3: Preserve Normal Prepare CardID Richness

**Files:**
- Inspect: `C:\Users\darbo\Documents\HSConfig\tests\test_universal_wild_no_block_matrix.py`
- Inspect: `C:\Users\darbo\Documents\HSConfig\tests\test_validate_package.py`
- No code change expected unless tests reveal a regression.

**Interfaces:**
- Consumes: normal `hsconfig prepare` test path.
- Produces: Evidence that minimal apply did not weaken normal deck output.

- [ ] **Step 1: Verify strict validator still accepts minimal load-safe package**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_validate_package.py::test_validate_package_strict_mode_accepts_minimal_load_safe_package_without_cardid tests/test_validate_package.py::test_validate_package_strict_mode_rejects_incomplete_package -q
```

Expected: `2 passed`.

- [ ] **Step 2: Verify apply gate already allows minimal package**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_apply_gate.py::test_apply_gate_ignores_config_usefulness_when_package_is_load_safe -q
```

Expected: `1 passed`.

- [ ] **Step 3: Verify normal Wild prepare still emits per-card CardID files**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_universal_wild_no_block_matrix.py -q
```

Expected: all tests pass. These tests must continue to assert exact per-deck CardID coverage for the supplied Wild deck matrix.

- [ ] **Step 4: No-op commit if no files changed**

If this task changes no files, do not create a commit. Record the passing commands in the task handoff.

---

### Task 4: Document Minimal Load Safety vs. Rich Prepare Output

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\docs\operator\README.md`
- Modify: `C:\Users\darbo\Documents\HSConfig\docs\operator\universal-wild-no-block-contract.md`
- Modify: `C:\Users\darbo\Documents\HSConfig\.agents\skills\hsconfig\SKILL.md`

**Interfaces:**
- Consumes: No-block contract from Tasks 1-3.
- Produces: Operator-facing docs and installed-skill source that explain the exact runtime rule.

- [ ] **Step 1: Update operator README**

In `docs/operator/README.md`, under `## Load Safety vs. Config Richness`, after the existing bullet for `technical_status`, add:

```markdown
- Minimal load-safe apply requires `GlobalValues.json` and `Mulligan.json`. Normal `prepare` packages should still emit per-card `<CARDID>.json` files when deck-card identity is known, but those rich CardID files are not the minimal runtime-apply gate.
```

- [ ] **Step 2: Update durable no-block contract**

In `docs/operator/universal-wild-no-block-contract.md`, near the section that defines no-block behavior, add:

```markdown
Minimal load-safe runtime apply is deliberately narrower than normal prepare richness. `GlobalValues.json` and `Mulligan.json` are the required runtime files. Per-card `<CARDID>.json` files, `Combo.json`, and identity-gated option files make the package more useful, and normal deck preparation should emit them when the deck and evidence support them, but their absence alone must not block a package that is otherwise `technical_status=VALID_PACKAGE` and `runtime_apply_mode=load_safe_apply`.
```

- [ ] **Step 3: Update HSConfig skill source**

In `.agents/skills/hsconfig/SKILL.md`, after the rule that starts with `Read runtime_load_safe`, add:

```markdown
- Minimal load-safe apply requires `GlobalValues.json` and `Mulligan.json`. Per-card `<CARDID>.json` files are normal rich output from `prepare`, but they are not the minimal runtime-write gate when `technical_status=VALID_PACKAGE` and `runtime_apply_mode=load_safe_apply`.
```

- [ ] **Step 4: Run docs and skill tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_skill_files.py tests/test_docs_active_path.py tests/test_scope_boundaries.py -q
```

Expected: all selected tests pass. If a docs test asserts exact wording, update it narrowly to include the new minimal/rich distinction.

- [ ] **Step 5: Commit documentation alignment**

```powershell
git add docs/operator/README.md docs/operator/universal-wild-no-block-contract.md .agents/skills/hsconfig/SKILL.md tests/test_skill_files.py tests/test_docs_active_path.py tests/test_scope_boundaries.py
git commit -m "docs: clarify minimal load-safe apply contract"
```

If no tests were modified, omit the test paths from `git add`.

---

### Task 5: Sync Installed Skill And Verify Drift Is Gone

**Files:**
- Update generated installed copy: `C:\Users\darbo\.codex\skills\hsconfig\SKILL.md`
- No tracked repo file should change except the source skill file changed in Task 4.

**Interfaces:**
- Consumes: `.agents/skills/hsconfig/SKILL.md`
- Produces: byte-matched installed skill.

- [ ] **Step 1: Sync installed skill**

Run:

```powershell
python scripts/sync_installed_skill.py
```

Expected: script completes successfully and writes the installed skill if needed.

- [ ] **Step 2: Check sync state**

Run:

```powershell
python scripts/sync_installed_skill.py --check
```

Expected:

```text
HSConfig skill is in sync
```

If the exact success string differs, the important result is exit code `0` and no drift report.

- [ ] **Step 3: Run skill sync test**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_skill_sync.py -q
```

Expected: all tests pass.

- [ ] **Step 4: Commit only tracked repo changes**

If Task 4 already committed `.agents/skills/hsconfig/SKILL.md`, no new repo commit is needed for the installed copy because it is outside the repo. If a tracked sync fixture changed, commit it:

```powershell
git status --short
git add <tracked-sync-file>
git commit -m "chore: sync installed hsconfig skill"
```

Do not commit files under `C:\Users\darbo\.codex\skills\`.

---

### Task 6: Final Regression And Plan Evidence

**Files:**
- No planned code edits.
- Inspect git status and test outputs.

**Interfaces:**
- Consumes: completed Tasks 1-5.
- Produces: final evidence that the no-block contract is closed.

- [ ] **Step 1: Run focused no-block contract suite**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_runtime_apply.py tests/test_apply_gate.py tests/test_validate_package.py tests/test_universal_wild_no_block_matrix.py tests/test_skill_sync.py tests/test_skill_files.py tests/test_docs_active_path.py tests/test_scope_boundaries.py -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run broader package suite if focused suite passes**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest -q
```

Expected: full suite passes. If it is too slow or fails outside this change scope, capture the failing test names and error summaries before deciding whether the failure is related.

- [ ] **Step 3: Check repo state**

Run:

```powershell
git status --short --branch
```

Expected: branch is clean except intentionally untracked historical research directories if the repo already had them before this plan. Do not add private runtime evidence or generated local caches.

- [ ] **Step 4: Push only after green verification when requested**

If the user asks to keep GitHub current, run:

```powershell
git push origin main
```

Expected: push succeeds.

---

## Self-Review

- **Spec coverage:** The plan covers the identified contract drift, keeps normal CardID-rich prepare output, documents minimal load-safety semantics, syncs the installed skill, and verifies the no-block Wild matrix.
- **Scope control:** The plan does not add new mechanic lowering, new dependencies, HSTuner behavior, replay analysis, or winrate logic.
- **Type consistency:** The plan uses existing names only: `apply_package`, `_validate_complete_source_dir`, `evaluate_apply_gate`, `technical_status`, `runtime_apply_mode`, `runtime_apply_allowed`, `GlobalValues.json`, `Mulligan.json`, and per-card `<CARDID>.json`.
- **No placeholders:** Every task has concrete file paths, exact snippets, commands, and expected outcomes.

## Execution Recommendation

Use Subagent-Driven execution. Recommended workers:

1. Runtime Contract Worker: Tasks 1-2.
2. Prepare Richness Reviewer: Task 3.
3. Docs/Skill Worker: Task 4.
4. Sync/QA Worker: Tasks 5-6.

The main agent should review diffs between workers and only integrate changes that preserve the no-block contract and the pre-run-only HSConfig boundary.

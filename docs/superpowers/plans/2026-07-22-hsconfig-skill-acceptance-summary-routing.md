# HSConfig Skill Acceptance Summary Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route HSConfig operators and the installed `$hsconfig` skill through `<out>/configure_summary.json.acceptance_summary` immediately after `hsconfig configure`, while preserving `reports/operator_summary.json` as the only normal runtime apply authority.

**Architecture:** This is a documentation, skill, and contract-test update only. `src/hsconfig/commands/configure.py` already emits `acceptance_summary`; this plan updates the canonical operator guide, repo skill, workflow reference, installed skill sync, and tests so the normal read order is acceptance projection first, apply authority second. `config_quality_summary` and `contract-doctor` remain diagnostic attention paths, not gates.

**Tech Stack:** Markdown, existing HSConfig pytest suite, `scripts/sync_installed_skill.py`, existing currentness script, Git.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig`.
- Start execution with `git fetch --all --prune --tags`, `python scripts\check_hsconfig_currentness.py --cwd . --json`, and `git status --short --branch`.
- Finish with a clean worktree after a real commit; no backups, temp outputs, runtime logs, or untracked artifacts.
- Do not inspect gameplay logs for this change.
- Do not use HSTuner.
- Do not change HearthRanger runtime generation behavior.
- Do not change `src\hsconfig\commands\configure.py` unless a verification step proves the current emitted `acceptance_summary` contract is missing or broken.
- Do not add dependencies, new runtime surfaces, or a new apply gate.
- `reports/operator_summary.json` remains the only normal runtime apply authority.
- `<out>/configure_summary.json.acceptance_summary` is an operator projection and first-read convenience after `configure`; it does not grant apply permission independently.
- `<out>/configure_summary.json.config_quality_summary` remains diagnostic-only and non-blocking.
- `contract-doctor` remains optional runtime-read-only diagnostics.
- `SOURCE_BACKED_STRONG` remains an evidence-quality label, not a generation or runtime-write gate.
- Default-only runtime surfaces remain visible quality debt and must not become hidden success or a hard apply blocker by themselves.
- Keep `.agents\skills\hsconfig\SKILL.md` and `.agents\skills\hsconfig\references\workflow.md` compact enough for the existing `< 80` newline tests.
- Do not edit `C:\Users\darbo\.codex\skills\hsconfig` manually; sync it from the repo skill with `scripts\sync_installed_skill.py`.

---

## Current State

- `python scripts\check_hsconfig_currentness.py --cwd . --json` currently reports `behind_origin_main=0`, `dirty=false`, and `clean_for_runtime_work=true`.
- `src\hsconfig\commands\configure.py` already writes top-level `configure_summary.json["acceptance_summary"]`.
- `tests\test_configure_cli.py` already verifies `_build_acceptance_summary(...)` and confirms `acceptance_summary` stays out of `operator_summary.json`.
- `.agents\skills\hsconfig\SKILL.md` still says to open `reports/operator_summary.json` first and to read `config_quality_summary` after `configure`.
- `.agents\skills\hsconfig\references\workflow.md` still routes normal workflow directly to `reports/operator_summary.json`.
- `docs\operator\README.md` still presents `config_quality_summary` as the post-configure quick visibility field.

---

## File Structure

- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_skill_files.py`
  - Update canonical skill/operator assertions so `acceptance_summary` is the first post-`configure` read.
  - Preserve existing `config_quality_summary` diagnostic-only assertions.
- Modify: `C:\Users\darbo\Documents\HSConfig\docs\operator\README.md`
  - Update Quick Start, Normal Operator Path, Real-Deck Usage Loop, and Optional Contract Doctor text.
- Modify: `C:\Users\darbo\Documents\HSConfig\.agents\skills\hsconfig\SKILL.md`
  - Update normal workflow step 3.
  - Replace the post-`configure` `config_quality_summary` bullet with the acceptance-first routing rule.
- Modify: `C:\Users\darbo\Documents\HSConfig\.agents\skills\hsconfig\references\workflow.md`
  - Mirror the same acceptance-first routing in the normal workflow and gate/readiness prose.
- Sync generated/install copy:
  - `C:\Users\darbo\.codex\skills\hsconfig\...` via `python scripts\sync_installed_skill.py`.
- Do not modify:
  - `C:\Users\darbo\Documents\HSConfig\src\hsconfig\commands\configure.py`
  - Runtime output files
  - HearthRanger `CustomConfig`

---

## Subagent-Driven Execution Shape

- [ ] **Explorer subagent, read-only:** Confirm the current `acceptance_summary` fields in `src\hsconfig\commands\configure.py` and `tests\test_configure_cli.py`; report whether any production change is required.
- [ ] **Worker subagent, narrow write scope:** Patch only `tests\test_skill_files.py`, `docs\operator\README.md`, `.agents\skills\hsconfig\SKILL.md`, and `.agents\skills\hsconfig\references\workflow.md`.
- [ ] **Reviewer subagent, read-only:** Inspect the diff for accidental new apply authority, HSTuner/log wording, SOURCE_BACKED_STRONG gating, default-only blocking, or production-code changes.
- [ ] **Main agent:** Run sync, tests, currentness, diff review, commit, and final clean status.

No subagent may edit the installed skill copy directly. Only the main agent syncs it from the repo.

---

## Task 1: Preflight And Currentness

**Files:** none.

- [ ] Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
git fetch --all --prune --tags
python scripts\check_hsconfig_currentness.py --cwd . --json
git status --short --branch
```

- [ ] Confirm:
  - `behind_origin_main` is `0`.
  - `dirty` is `false` before edits.
  - The branch is not stale relative to its upstream.

- [ ] If the worktree is dirty before edits, stop and inspect with:

```powershell
git diff --name-only
git status --short
```

Do not overwrite unrelated user changes.

---

## Task 2: Write Failing Contract Tests First

**Files:**
- `C:\Users\darbo\Documents\HSConfig\tests\test_skill_files.py`

### Step 2.1: Update the normal workflow assertion

- [ ] In `test_skill_names_configure_normal_workflow`, replace the old step 3 assertion:

```python
assert "3. Open `reports/operator_summary.json` first." in text
```

with:

```python
assert (
    "3. After `configure`, read `<out>/configure_summary.json.acceptance_summary` "
    "first; use `reports/operator_summary.json` as the apply authority."
) in text
```

Keep the source-autopilot assertions unchanged.

### Step 2.2: Strengthen the config-quality diagnostic test

- [ ] In `test_docs_and_skill_keep_config_quality_summary_diagnostic_only`, keep the existing split logic and extend the loop assertions to require acceptance-first routing:

```python
    for text in (operator_fragment, skill_fragment):
        assert "<out>/configure_summary.json.acceptance_summary" in text
        assert "acceptance_summary" in text
        assert "use_config_now" in text
        assert "next_report_to_open" in text
        assert "<out>/configure_summary.json.config_quality_summary" in text
        assert "config_quality_summary" in text
        assert "diagnostic-only" in text
        assert "non-blocking" in text
        assert "contract-doctor" in text
        assert "operator_summary.json" in text
        assert "normal apply authority" in text
```

### Step 2.3: Add workflow-reference coverage

- [ ] Add this focused test directly after `test_docs_and_skill_keep_config_quality_summary_diagnostic_only`:

```python
def test_docs_skill_and_workflow_route_configure_acceptance_summary_first() -> None:
    operator_docs = (REPO_ROOT / "docs" / "operator" / "README.md").read_text(
        encoding="utf-8"
    )
    skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    workflow = (SKILL_ROOT / "references" / "workflow.md").read_text(
        encoding="utf-8"
    )

    for text in (operator_docs, skill, workflow):
        assert "<out>/configure_summary.json.acceptance_summary" in text
        assert "use_config_now" in text
        assert "next_report_to_open" in text
        assert "operator projection" in text
        assert "operator_summary.json" in text
        assert "apply authority" in text
```

### Step 2.4: Run the focused tests and confirm the expected failure

- [ ] Run:

```powershell
pytest tests\test_skill_files.py::test_skill_names_configure_normal_workflow tests\test_skill_files.py::test_docs_and_skill_keep_config_quality_summary_diagnostic_only tests\test_skill_files.py::test_docs_skill_and_workflow_route_configure_acceptance_summary_first -q
```

- [ ] Expected before implementation:
  - Failure due to missing `<out>/configure_summary.json.acceptance_summary` wording in docs/skill/workflow.

Do not proceed unless the failure matches the intended contract gap.

---

## Task 3: Patch Operator Docs And Skill Routing

### Step 3.1: Patch `docs\operator\README.md`

**File:**
- `C:\Users\darbo\Documents\HSConfig\docs\operator\README.md`

- [ ] In Quick Start, replace:

```markdown
- Open `reports/operator_summary.json` first.
```

with:

```markdown
- After `configure`, read `<out>/configure_summary.json.acceptance_summary` first; it is an operator projection. Use `reports/operator_summary.json` as the apply authority.
```

- [ ] In Normal Operator Path, replace steps 2-3 with:

```markdown
2. Read `outputs/<DeckName>/configure_summary.json.acceptance_summary`.
3. Use `outputs/<DeckName>/04_package/reports/operator_summary.json` as the apply authority.
4. Apply only through `hsconfig apply` or `hsconfig configure --apply`.
```

- [ ] Immediately after the Normal Operator Path steps, keep or update the authority sentence to:

```markdown
reports/operator_summary.json remains the only normal apply authority.
```

- [ ] In Real-Deck Usage Loop, replace step 2 with:

```markdown
2. Read `<out>/configure_summary.json.acceptance_summary` first; `use_config_now` and `next_report_to_open` are compact operator projection fields, not a second apply gate.
```

- [ ] Replace the Optional Contract Doctor paragraph that currently starts with:

```markdown
`<out>/configure_summary.json.config_quality_summary` is a compact diagnostic-only, non-blocking mirror
```

with:

```markdown
`<out>/configure_summary.json.acceptance_summary` is the first post-`configure` read. It is a compact operator projection with `use_config_now`, `technical_status`, `runtime_apply_allowed`, `source_strength`, `default_only_clean`, and `next_report_to_open`; it does not replace `reports/operator_summary.json`, which remains the normal apply authority.

`<out>/configure_summary.json.config_quality_summary` remains a compact diagnostic-only, non-blocking mirror of the existing config-quality contract. It is for quick quality visibility after `hsconfig configure` or when `acceptance_summary.next_report_to_open` points to `reports/contract_doctor.json`. If `status` is `attention`, run `hsconfig contract-doctor --package <package>` for details. The normal apply authority remains `reports/operator_summary.json`.
```

### Step 3.2: Patch `.agents\skills\hsconfig\SKILL.md`

**File:**
- `C:\Users\darbo\Documents\HSConfig\.agents\skills\hsconfig\SKILL.md`

- [ ] Replace normal workflow step 3:

```markdown
3. Open `reports/operator_summary.json` first. Contract compiler checklist: `references/contract-compiler-checklist.md`.
```

with:

```markdown
3. After `configure`, read `<out>/configure_summary.json.acceptance_summary` first; use `reports/operator_summary.json` as the apply authority. Contract compiler checklist: `references/contract-compiler-checklist.md`.
```

- [ ] Replace the existing post-`configure` `config_quality_summary` bullet:

```markdown
- After `configure`, read `<out>/configure_summary.json.config_quality_summary` for quick diagnostic quality status. It is diagnostic-only and non-blocking; use `contract-doctor` for details. `reports/operator_summary.json` remains the normal apply authority.
```

with this single compact bullet:

```markdown
- After `configure`, read `<out>/configure_summary.json.acceptance_summary` first: `use_config_now`, `technical_status`, `runtime_apply_allowed`, `source_strength`, `default_only_clean`, and `next_report_to_open` are the compact operator projection. Then read `<out>/configure_summary.json.config_quality_summary` only for diagnostic-only, non-blocking quality visibility or when `acceptance_summary.next_report_to_open` points to `reports/contract_doctor.json`; use `contract-doctor` for details. `reports/operator_summary.json` remains the normal apply authority.
```

Do not add new lines elsewhere unless needed; the compactness test is strict.

### Step 3.3: Patch `.agents\skills\hsconfig\references\workflow.md`

**File:**
- `C:\Users\darbo\Documents\HSConfig\.agents\skills\hsconfig\references\workflow.md`

- [ ] Replace the normal workflow line:

```markdown
Normal workflow: prefer `hsconfig configure ...`; use lower-level commands only when inspecting a stage (`source-manifest -> source-autopilot or draft-source-documents -> research-deck -> prepare -> validate -> apply`); open `reports/operator_summary.json` first.
```

with:

```markdown
Normal workflow: prefer `hsconfig configure ...`; read `<out>/configure_summary.json.acceptance_summary` first after configure; use lower-level commands only when inspecting a stage (`source-manifest -> source-autopilot or draft-source-documents -> research-deck -> prepare -> validate -> apply`); use `reports/operator_summary.json` as the apply authority.
```

- [ ] Add one compact sentence in `## Gate And Readiness`, before the existing `reports/operator_summary.json` gate paragraph:

```markdown
After `configure`, `<out>/configure_summary.json.acceptance_summary` is the first-read operator projection: `use_config_now`, `technical_status`, `runtime_apply_allowed`, `source_strength`, `default_only_clean`, and `next_report_to_open` summarize the package; it does not replace `reports/operator_summary.json` as apply authority. `<out>/configure_summary.json.config_quality_summary` remains diagnostic-only and non-blocking, and `contract-doctor` provides details when attention is needed.
```

---

## Task 4: Re-run Skill Tests And Sync Installed Skill

- [ ] Run the focused tests:

```powershell
pytest tests\test_skill_files.py::test_skill_names_configure_normal_workflow tests\test_skill_files.py::test_docs_and_skill_keep_config_quality_summary_diagnostic_only tests\test_skill_files.py::test_docs_skill_and_workflow_route_configure_acceptance_summary_first -q
```

- [ ] Run compactness and sync-related tests:

```powershell
pytest tests\test_skill_files.py::test_skill_and_workflow_stay_compact_and_canonical tests\test_skill_sync.py -q
```

- [ ] If `tests\test_skill_sync.py` fails because the installed copy is stale, sync from repo:

```powershell
python scripts\sync_installed_skill.py
python scripts\sync_installed_skill.py --check
```

- [ ] Re-run:

```powershell
pytest tests\test_skill_sync.py -q
```

---

## Task 5: Verify Existing Configure Acceptance Contract Stayed Intact

**Purpose:** Prove this plan did not accidentally change production acceptance behavior.

- [ ] Run:

```powershell
pytest tests\test_configure_cli.py::test_build_acceptance_summary_marks_load_safe_package_usable tests\test_configure_cli.py::test_build_acceptance_summary_surfaces_diagnostics_without_blocking tests\test_configure_cli.py::test_acceptance_summary_helper_stays_configure_local_projection tests\test_configure_cli.py::test_configure_writes_diagnostic_config_quality_summary tests\test_configure_cli.py::test_configure_quality_summary_failure_stays_diagnostic_only -q
```

- [ ] Run:

```powershell
python -m hsconfig.cli contract-preflight --json
```

Acceptance criteria:
- `acceptance_summary` tests pass unchanged.
- `acceptance_summary` remains absent from `operator_summary.json`.
- `contract-preflight` succeeds.
- No production Python diff exists unless separately justified by a failing test.

---

## Task 6: Diff Review And Guardrails

- [ ] Run:

```powershell
git diff --check
git diff --name-only
```

- [ ] Confirm the changed file list is limited to:

```text
.agents/skills/hsconfig/SKILL.md
.agents/skills/hsconfig/references/workflow.md
docs/operator/README.md
tests/test_skill_files.py
C:\Users\darbo\.codex\skills\hsconfig\SKILL.md
C:\Users\darbo\.codex\skills\hsconfig\references\workflow.md
```

Note: the installed skill copy may appear outside repo Git tracking. It still must be synced and checked by `scripts\sync_installed_skill.py --check`.

- [ ] Inspect the repo diff manually:

```powershell
git diff -- .agents\skills\hsconfig\SKILL.md .agents\skills\hsconfig\references\workflow.md docs\operator\README.md tests\test_skill_files.py
```

- [ ] Verify these strings exist in the diff:
  - `<out>/configure_summary.json.acceptance_summary`
  - `use_config_now`
  - `next_report_to_open`
  - `operator projection`
  - `diagnostic-only`
  - `normal apply authority`

- [ ] Verify these undesired changes do not appear:
  - HSTuner as required workflow
  - gameplay log parsing
  - `SOURCE_BACKED_STRONG` as apply gate
  - default-only as hard apply blocker
  - new runtime surface
  - production code change

---

## Task 7: Final Verification, Commit, Clean Status

- [ ] Run the complete relevant verification set:

```powershell
pytest tests\test_skill_files.py tests\test_skill_sync.py tests\test_configure_cli.py::test_build_acceptance_summary_marks_load_safe_package_usable tests\test_configure_cli.py::test_build_acceptance_summary_surfaces_diagnostics_without_blocking tests\test_configure_cli.py::test_acceptance_summary_helper_stays_configure_local_projection tests\test_configure_cli.py::test_configure_writes_diagnostic_config_quality_summary tests\test_configure_cli.py::test_configure_quality_summary_failure_stays_diagnostic_only -q
python scripts\sync_installed_skill.py --check
python scripts\check_hsconfig_currentness.py --cwd . --json
git status --short --branch
```

- [ ] Stage only intended repo files:

```powershell
git add .agents\skills\hsconfig\SKILL.md .agents\skills\hsconfig\references\workflow.md docs\operator\README.md tests\test_skill_files.py docs\superpowers\plans\2026-07-22-hsconfig-skill-acceptance-summary-routing.md
```

- [ ] Commit:

```powershell
git commit -m "Route HSConfig skill through configure acceptance summary"
```

- [ ] Confirm final clean status:

```powershell
git status --short --branch
python scripts\check_hsconfig_currentness.py --cwd . --json
```

Acceptance criteria:
- Repo worktree is clean after commit.
- Installed skill is in sync with repo skill.
- Currentness still reports not behind `origin/main`.
- No backups or untracked temp artifacts remain.
- Final answer reports the commit hash and verification commands.

---

## Rollback Plan

If any verification fails after the docs/tests patch:

1. Inspect the exact failing assertion.
2. Keep the acceptance-first contract if the failure is only wording drift.
3. If compactness fails, shorten skill/workflow wording without removing:
   - `<out>/configure_summary.json.acceptance_summary`
   - `use_config_now`
   - `next_report_to_open`
   - `config_quality_summary`
   - `diagnostic-only`
   - `operator_summary.json`
4. If sync fails, re-run `python scripts\sync_installed_skill.py` and then `python scripts\sync_installed_skill.py --check`.
5. If any production Python file is changed by mistake, restore that file before commit:

```powershell
git restore -- src\hsconfig\commands\configure.py
```

Do not use `git reset --hard`.

---

## Final Human Summary Template

Use this shape after implementation:

```text
Umgesetzt: Der HSConfig-Skill und die Operator-Doku lesen nach `hsconfig configure` nun zuerst `configure_summary.json.acceptance_summary`; `operator_summary.json` bleibt die einzige normale Apply-Autorität.

Geprüft:
- pytest ...
- python scripts\sync_installed_skill.py --check
- python scripts\check_hsconfig_currentness.py --cwd . --json

Commit: <hash>
Worktree: clean
```

# HSConfig Main Sync Provenance Index Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the current verified HSConfig hardening branch authoritative on `main` and add the smallest documentation provenance index needed to keep old Superpowers plans from being mistaken for operator guidance.

**Architecture:** This is a governance and documentation closure wave, not a core HSConfig feature wave. Keep the existing compiler, apply gate, skill files, runtime surfaces, and operator path unchanged; add only a tiny Superpowers provenance index plus a doc regression test, then fast-forward `main` and push it.

**Tech Stack:** Git, PowerShell, Python, pytest, existing HSConfig CLI and docs.

## Global Constraints

- Work only in `C:\Users\darbo\Documents\HSConfig` for `Teufelsboy/HSConfig`.
- Keep HSConfig separate from HSTuner: no replay parsing, HDT parsing, winrate validation, candidate promotion, or post-run tuning.
- Keep HSConfig pre-run only: deck input to HearthRanger VisionAI `CustomConfig` package.
- Do not change runtime generation behavior in `src/hsconfig` unless a verification command exposes a concrete defect; this plan expects no source-code changes.
- Do not change the normal output boundary for `Presume.json` or `Concede.json`; normal HSConfig does not emit them.
- Do not weaken the guarded apply gate; `reports/operator_summary.json` remains the single normal operator gate.
- Do not commit `.superpowers/` research outputs; `.superpowers/` remains ignored.
- Prefer fast-forward integration to `main`; do not create a merge commit if `--ff-only` succeeds.
- Keep the installed skill synchronized; because this plan does not edit `.agents/skills/hsconfig`, `python scripts/sync_installed_skill.py --check` should pass without copying.

---

## File Structure

- Create: `docs/superpowers/README.md`
  - Responsibility: mark `docs/superpowers/` as historical planning provenance and route current operation to `docs/operator/README.md`.
- Create: `docs/superpowers/plans/README.md`
  - Responsibility: mark dated implementation plans as historical audit trail, not the normal command path.
- Modify: `tests/test_docs_active_path.py`
  - Responsibility: add one regression test proving Superpowers planning folders are explicitly non-operator guidance.
- No changes expected: `src/hsconfig/**`, `.agents/skills/hsconfig/**`, runtime package outputs, generated `outputs/**`.

---

### Task 1: Preflight Current Branch And Scope

**Files:**
- No file edits.

**Interfaces:**
- Consumes: current branch `codex/hsconfig-lean-contract-hardening`, existing `main`, existing `origin/main`.
- Produces: verified preflight state for later docs patch and fast-forward.

- [ ] **Step 1: Confirm workspace and branch**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
git status --short --branch
git rev-list --left-right --count main...HEAD
git rev-list --left-right --count origin/main...HEAD
```

Expected:

```text
## codex/hsconfig-lean-contract-hardening...origin/codex/hsconfig-lean-contract-hardening
0	14
0	14
```

If the commit count differs because this plan file was committed before execution, accept `0	15` or another `0	N` where `N` is positive and `git status` is clean. Stop only if the left side is non-zero, because that means `main` or `origin/main` contains commits not in the working branch.

- [ ] **Step 2: Fetch and re-check remote reality**

Run:

```powershell
git fetch origin --prune
git status --short --branch
git rev-list --left-right --count origin/main...HEAD
```

Expected:

```text
## codex/hsconfig-lean-contract-hardening...origin/codex/hsconfig-lean-contract-hardening
0	N
```

`N` must be positive. If the first number is not `0`, stop and inspect the remote commits before merging.

- [ ] **Step 3: Confirm installed skill sync before touching docs**

Run:

```powershell
python scripts\sync_installed_skill.py --check
```

Expected:

```text
HSConfig skill is in sync: C:\Users\darbo\.codex\skills\hsconfig
```

- [ ] **Step 4: Confirm no scope-expanding work is needed**

Run:

```powershell
python -m pytest tests\test_scope_boundaries.py tests\test_skill_files.py tests\test_skill_sync.py -q
```

Expected:

```text
pytest exits with code 0 and reports all selected tests as passed.
```

The exact count may vary after nearby test additions. Any failure in these files must be fixed before proceeding, because the branch would no longer prove the lean HSConfig boundary.

---

### Task 2: Add Superpowers Provenance Index

**Files:**
- Create: `docs/superpowers/README.md`
- Create: `docs/superpowers/plans/README.md`
- Modify: `tests/test_docs_active_path.py`

**Interfaces:**
- Consumes: active operator path `docs/operator/README.md` and active evidence index `docs/research/current-truth.md`.
- Produces: explicit historical-provenance labels for Superpowers folders.

- [ ] **Step 1: Write the failing doc regression test**

Append this test to `tests/test_docs_active_path.py`:

```python
def test_superpowers_artifacts_are_historical_not_operator_guidance():
    root = Path("docs/superpowers/README.md").read_text(encoding="utf-8")
    plans = Path("docs/superpowers/plans/README.md").read_text(encoding="utf-8")
    combined = f"{root}\n{plans}"

    assert "Historical planning artifacts" in root
    assert "not operator instructions" in combined
    assert "docs/operator/README.md" in combined
    assert "docs/research/current-truth.md" in combined
    assert "Do not use old Superpowers plans as the normal command path." in plans
    assert "normal command path is `hsconfig configure`" in plans
```

- [ ] **Step 2: Run the focused test and verify it fails for missing files**

Run:

```powershell
python -m pytest tests\test_docs_active_path.py::test_superpowers_artifacts_are_historical_not_operator_guidance -q
```

Expected:

```text
FAILED tests/test_docs_active_path.py::test_superpowers_artifacts_are_historical_not_operator_guidance
FileNotFoundError
```

- [ ] **Step 3: Create `docs/superpowers/README.md`**

Create `docs/superpowers/README.md` with exactly this content:

```markdown
# Superpowers Planning Artifacts

Historical planning artifacts live here.

This folder is not operator instructions. It preserves design specs, implementation plans, and agentic planning evidence so past decisions remain auditable.

For normal HSConfig operation, start at `docs/operator/README.md`.

For the current evidence index, read `docs/research/current-truth.md`.

When an older Superpowers artifact conflicts with active operator docs, the active operator docs and `.agents/skills/hsconfig/SKILL.md` win.
```

- [ ] **Step 4: Create `docs/superpowers/plans/README.md`**

Create `docs/superpowers/plans/README.md` with exactly this content:

```markdown
# Historical Implementation Plans

This folder contains dated implementation plans for previous HSConfig work.

Do not use old Superpowers plans as the normal command path.

The normal command path is `hsconfig configure`, documented in `docs/operator/README.md`.

Use `docs/research/current-truth.md` to see which research packages are current evidence. Use dated plans only to understand why a previous change was made.
```

- [ ] **Step 5: Run the focused test and verify it passes**

Run:

```powershell
python -m pytest tests\test_docs_active_path.py::test_superpowers_artifacts_are_historical_not_operator_guidance -q
```

Expected:

```text
1 passed
```

- [ ] **Step 6: Run active-docs regression tests**

Run:

```powershell
python -m pytest tests\test_docs_active_path.py tests\test_skill_files.py -q
```

Expected:

```text
pytest exits with code 0 and reports all selected tests as passed.
```

- [ ] **Step 7: Commit the provenance index**

Run:

```powershell
git status --short
git add docs\superpowers\README.md docs\superpowers\plans\README.md tests\test_docs_active_path.py
git commit -m "docs: mark superpowers artifacts as historical"
```

Expected:

```text
[codex/hsconfig-lean-contract-hardening <hash>] docs: mark superpowers artifacts as historical
```

---

### Task 3: Verification Sweep Before Main Sync

**Files:**
- No planned edits.

**Interfaces:**
- Consumes: committed provenance index from Task 2.
- Produces: proof that docs, skill sync, and HSConfig tests remain valid before pushing to `main`.

- [ ] **Step 1: Run installed-skill sync check**

Run:

```powershell
python scripts\sync_installed_skill.py --check
```

Expected:

```text
HSConfig skill is in sync: C:\Users\darbo\.codex\skills\hsconfig
```

- [ ] **Step 2: Run focused governance and boundary tests**

Run:

```powershell
python -m pytest tests\test_docs_active_path.py tests\test_skill_files.py tests\test_skill_sync.py tests\test_scope_boundaries.py tests\test_apply_gate.py -q
```

Expected:

```text
pytest exits with code 0 and reports all selected tests as passed.
```

- [ ] **Step 3: Run the full test suite**

Run:

```powershell
python -m pytest -q
```

Expected:

```text
pytest exits with code 0 and reports the full suite as passed, with skipped tests allowed.
```

The previously observed healthy full-suite shape was `820 passed, 2 skipped`. Accept a higher passed count if Task 2 added a test. Do not proceed with the fast-forward if any test fails.

- [ ] **Step 4: Check for whitespace and accidental generated artifacts**

Run:

```powershell
git diff --check
git status --short --branch
```

Expected after Task 2 commit:

```text
## codex/hsconfig-lean-contract-hardening...origin/codex/hsconfig-lean-contract-hardening [ahead N]
```

No untracked or modified tracked files should be listed. Ignored `.superpowers/` research outputs must remain uncommitted.

---

### Task 4: Fast-Forward Main And Push

**Files:**
- No file edits.

**Interfaces:**
- Consumes: clean, tested `codex/hsconfig-lean-contract-hardening` branch.
- Produces: `main` and `origin/main` updated to the verified branch tip.

- [ ] **Step 1: Push the current branch for backup**

Run:

```powershell
git push origin codex/hsconfig-lean-contract-hardening
```

Expected:

```text
codex/hsconfig-lean-contract-hardening -> codex/hsconfig-lean-contract-hardening
```

If Git reports `Everything up-to-date`, that is also acceptable.

- [ ] **Step 2: Switch to `main`**

Run:

```powershell
git switch main
git status --short --branch
```

Expected:

```text
## main...origin/main
```

No modified or untracked tracked files should appear.

- [ ] **Step 3: Fast-forward `main`**

Run:

```powershell
git merge --ff-only codex/hsconfig-lean-contract-hardening
```

Expected:

```text
Updating <old>..<new>
Fast-forward
```

If `--ff-only` fails, stop. Do not create a merge commit. Inspect `git log --oneline --left-right main...codex/hsconfig-lean-contract-hardening` and resolve why `main` is no longer an ancestor.

- [ ] **Step 4: Smoke-test `main` after fast-forward**

Run:

```powershell
python scripts\sync_installed_skill.py --check
python -m pytest tests\test_docs_active_path.py tests\test_skill_files.py tests\test_skill_sync.py -q
```

Expected:

```text
HSConfig skill is in sync: C:\Users\darbo\.codex\skills\hsconfig
pytest exits with code 0 and reports all selected tests as passed.
```

- [ ] **Step 5: Push `main`**

Run:

```powershell
git push origin main
```

Expected:

```text
main -> main
```

- [ ] **Step 6: Confirm local and remote main alignment**

Run:

```powershell
git status --short --branch
git rev-list --left-right --count origin/main...main
git log --oneline --decorate -5
```

Expected:

```text
## main...origin/main
0	0
```

The latest commit should be the Task 2 provenance commit if Task 2 was executed. If Task 2 was intentionally skipped by a later approved revision, the latest commit should be the previous hardening branch tip.

---

### Task 5: Final Operator Handoff

**Files:**
- No planned edits.

**Interfaces:**
- Consumes: pushed `main`.
- Produces: concise final status that names the active branch, pushed branch, tests, and remaining recommendation.

- [ ] **Step 1: Capture final state**

Run:

```powershell
git branch --show-current
git status --short --branch
git rev-parse --short HEAD
git rev-parse --short origin/main
python -m hsconfig --help
```

Expected:

```text
main
## main...origin/main
<same-short-hash>
<same-short-hash>
usage: hsconfig
```

- [ ] **Step 2: Confirm no HSConfig scope drift appeared**

Run:

```powershell
rg -n "HDT|Power\\.log|winrate|candidate promotion|post-run tuning|normal output includes Presume|normal output includes Concede" README.md docs\operator .agents\skills\hsconfig src tests
```

Expected:

```text
```

No matches should appear for new scope-expanding wording. Existing negative-scope phrases that say HSConfig does not parse replays, inspect winrate, or tune after games are acceptable if the command is refined to inspect context. If the raw command returns such negative-scope matches, verify they are negative-boundary statements and do not edit them.

- [ ] **Step 3: Report completion**

Final answer should include:

```text
main is updated and pushed.
Installed hsconfig skill sync check passed.
Focused docs/skill tests passed.
Full suite passed before main sync.
No HSConfig core behavior was changed.
Next practical step: use hsconfig configure for the next real deck; only open a new implementation wave for a concrete deck failure or a clearly outdated Hearthstone mechanic mapping.
```

---

## Self-Review

- Spec coverage: The plan implements the recommendation by making the tested branch current on `main`, keeping HSConfig narrow, and adding only a minimal provenance index for old Superpowers artifacts.
- Placeholder scan: No step relies on missing future detail. Commands, files, test names, and expected outputs are explicit.
- Type consistency: No new runtime API or data model is introduced. The only new test reads two markdown files and checks fixed strings.
- Scope check: The plan avoids replay parsing, winrate, HSTuner, candidate promotion, apply-gate changes, source compiler changes, and runtime output expansion.

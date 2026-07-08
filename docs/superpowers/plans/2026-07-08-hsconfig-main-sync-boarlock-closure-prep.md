# HSConfig Main Sync And Boarlock Closure Prep Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Put the current HSConfig runtime-apply-mode work and current skill audit evidence onto a clean, GitHub-current `main`, then prepare the next narrow source-depth closure target without widening the product architecture.

**Architecture:** Keep HSConfig as a pre-run CustomConfig compiler. Treat `operator_summary.json` as the single operator gate, keep `runtime_apply_mode` read-facing only, preserve the 11-deck representative matrix, and use the current audit package as evidence for a small cleanup-plus-closure wave. Do not add new runtime surfaces or post-run/HSTuner behavior.

**Tech Stack:** Python 3.11+, pytest, existing HSConfig package under `src/hsconfig`, existing Markdown/JSON operator and research docs, Git.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig`.
- Preserve HSConfig as pre-run only: no replay parsing, no winrate analysis, no HSTuner post-run logic.
- Do not add dependencies.
- Do not add normal-path `Presume.json` or `Concede.json`.
- Do not widen the representative matrix beyond the current 11 decks.
- Keep `CuteWarrior` supplemental unless a later explicit matrix-review plan promotes it.
- Do not relax `SOURCE_BACKED_STRONG`, `SOURCE_INFORMED_APPLY_READY`, or guarded apply gates.
- `runtime_apply_mode`, `runtime_apply_allowed`, and `runtime_apply_requires_flag` are descriptive/read-facing only; `evaluate_apply_gate()` and `apply_package()` remain authoritative.
- Do not force weak Boarlock `Fracking` or Kingslayer `Quick Pick` mulligan claims.
- Raw HearthRanger/HDT/runtime logs are not part of HSConfig and must not be committed.

---

## File Structure

- `docs/research/2026-07-08-hsconfig-current-skill-lean-audit/**`: current source-backed audit evidence package. Task 1 decides and records whether it is committed.
- `docs/research/README.md`: research index. Task 1 may add a one-line pointer to the current audit package if the package is committed.
- `docs/operator/source-backed-strong-closure.md`: active source-depth closure truth for Kingslayer and Boarlock.
- `docs/operator/archetype-fixture-matrix.json`: representative 11-deck matrix; must not gain CuteWarrior in this plan.
- `docs/operator/supplemental-proof-decks.json`: CuteWarrior stays supplemental.
- `tests/test_research_audit_schema.py`: validates research audit package structure or index language if committed.
- `tests/test_matrix_visibility.py`, `tests/test_source_informed_closure_contract.py`, `tests/test_matrix_governance.py`: matrix-governance protection.
- `docs/superpowers/plans/2026-07-08-hsconfig-main-sync-boarlock-closure-prep.md`: this implementation plan.

---

### Task 1: Freeze Current Branch And Audit Evidence

**Files:**
- Create/Modify: `docs/research/README.md`
- Keep/Commit: `docs/research/2026-07-08-hsconfig-current-skill-lean-audit/**`
- Test: `tests/test_research_audit_schema.py`

**Interfaces:**
- Consumes: current branch `codex/hsconfig-runtime-apply-mode-clarity`, untracked audit directory, existing research validation script.
- Produces: committed audit package or a clean explicit decision to remove it before merge.

- [ ] **Step 1: Inspect current branch and dirty state**

Run:

```powershell
git status --short --branch
git branch --show-current
git log --oneline -8
```

Expected current branch before cleanup:

```text
codex/hsconfig-runtime-apply-mode-clarity
```

If `docs/research/2026-07-08-hsconfig-current-skill-lean-audit/` is untracked, continue with Step 2. If it is already committed or absent, record that in the task report and skip to Step 5.

- [ ] **Step 2: Validate the audit package before deciding to keep it**

Run:

```powershell
python C:\Users\darbo\.codex\skills\research\validate_json.py `
  -f docs\research\2026-07-08-hsconfig-current-skill-lean-audit\fields.yaml `
  -d docs\research\2026-07-08-hsconfig-current-skill-lean-audit\results
```

Expected:

```text
Validation passed: 5/5
Average coverage: 100.0%
```

- [ ] **Step 3: Add a research-index test for the current audit package**

Open `tests/test_research_audit_schema.py`. If no test mentions `2026-07-08-hsconfig-current-skill-lean-audit`, add this test:

```python
from pathlib import Path


def test_current_skill_lean_audit_package_is_indexed_as_evidence():
    readme = Path("docs/research/README.md").read_text(encoding="utf-8")
    audit_root = Path("docs/research/2026-07-08-hsconfig-current-skill-lean-audit")

    assert "2026-07-08-hsconfig-current-skill-lean-audit" in readme
    assert "current skill lean audit" in readme.lower()
    assert "evidence, not operator instructions" in readme.lower()
    assert (audit_root / "fields.yaml").exists()
    assert (audit_root / "outline.yaml").exists()
    assert len(list((audit_root / "results").glob("*.json"))) == 5
```

If the file already imports `Path`, do not duplicate the import; append only the test function.

- [ ] **Step 4: Add a short index entry to `docs/research/README.md`**

Add one compact bullet under the active research packages or evidence section:

```markdown
- `2026-07-08-hsconfig-current-skill-lean-audit/`: current skill lean audit evidence for operator boundary, VisionAI surface, every-card source-depth model, deck matrix truth, and repo slimness. Evidence only; normal operation still starts at `docs/operator/README.md`.
```

Do not make this README a second operator guide.

- [ ] **Step 5: Run research/index tests**

Run:

```powershell
python -m pytest tests\test_research_audit_schema.py tests\test_docs_active_path.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 1**

Run:

```powershell
git add docs\research\README.md docs\research\2026-07-08-hsconfig-current-skill-lean-audit tests\test_research_audit_schema.py
git commit -m "docs: add current hsconfig skill lean audit"
```

If the audit package should not be retained, delete only `docs/research/2026-07-08-hsconfig-current-skill-lean-audit/`, run `git status --short --branch`, and commit only the plan file in Task 4. Do not leave the workspace dirty.

---

### Task 2: Verify Runtime Apply Mode Contract Before Merge

**Files:**
- Read: `src/hsconfig/operator_summary.py`
- Read: `src/hsconfig/operator_guidance.py`
- Read: `src/hsconfig/apply_gate.py`
- Read: `src/hsconfig/runtime_apply.py`
- Test: `tests/test_operator_summary.py`
- Test: `tests/test_operator_guidance.py`
- Test: `tests/test_apply_gate.py`
- Test: `tests/test_runtime_apply.py`
- Test: `tests/test_skill_files.py`
- Test: `tests/test_docs_active_path.py`

**Interfaces:**
- Consumes: branch commits from runtime-apply-mode clarity work.
- Produces: verified gate contract ready for `main`.

- [ ] **Step 1: Check read-facing field locations**

Run:

```powershell
rg -n "runtime_apply_mode|runtime_apply_allowed|runtime_apply_requires_flag" src tests docs .agents
```

Expected facts:

- `src/hsconfig/operator_summary.py` emits the fields.
- `src/hsconfig/operator_guidance.py` mirrors the fields.
- `tests/test_apply_gate.py` contains a forged `runtime_apply_allowed=True` regression.
- `tests/test_runtime_apply.py` contains a forged/stale gate rejection case.
- `docs/operator/README.md` and `.agents/skills/hsconfig/SKILL.md` document the fields as descriptive.

- [ ] **Step 2: Run focused runtime apply tests**

Run:

```powershell
python -m pytest tests\test_operator_summary.py tests\test_operator_guidance.py tests\test_apply_gate.py tests\test_runtime_apply.py tests\test_skill_files.py tests\test_docs_active_path.py -q
```

Expected: PASS. Current known good baseline is `127 passed`.

- [ ] **Step 3: Run skill sync check**

Run:

```powershell
python scripts\sync_installed_skill.py --check
```

Expected:

```text
HSConfig skill is in sync: C:\Users\darbo\.codex\skills\hsconfig
```

- [ ] **Step 4: Inspect for scope drift**

Run:

```powershell
rg -n "Power.log|HDT|winrate|replay|candidate promotion|Presume.json|Concede.json" README.md docs\operator .agents\skills\hsconfig src tests
```

Expected:

- `replay` and `winrate` only appear in negative pre-run boundary statements.
- `Presume.json` and `Concede.json` only appear as not-normal-path or legacy/gated surfaces.
- No HSTuner post-run logic appears in `src/hsconfig`.

If a positive normal-path claim appears, fix docs/tests before merge.

- [ ] **Step 5: Commit only if fixes were needed**

If Step 4 required edits, run:

```powershell
git add <changed-files>
git commit -m "docs: preserve hsconfig pre-run apply boundary"
```

If no edits were needed, do not create an empty commit.

---

### Task 3: Lock Matrix Governance And Next Closure Target

**Files:**
- Modify: `docs/operator/source-backed-strong-closure.md`
- Modify: `docs/operator/archetype-fixture-matrix.json` only if wording is stale; do not add decks.
- Modify: `docs/operator/supplemental-proof-decks.json` only if CuteWarrior supplemental policy is stale.
- Test: `tests/test_matrix_visibility.py`
- Test: `tests/test_source_informed_closure_contract.py`
- Test: `tests/test_matrix_governance.py`
- Test: `tests/test_source_depth_closure_index.py`

**Interfaces:**
- Consumes: current matrix truth from the audit package.
- Produces: one clear next target: Boarlock first, Kingslayer second, CuteWarrior supplemental.

- [ ] **Step 1: Write or confirm governance tests**

Open `tests/test_matrix_governance.py` or `tests/test_source_informed_closure_contract.py`. Ensure tests assert these facts:

```python
def test_cute_warrior_stays_supplemental_until_source_informed_rows_are_reviewed():
    matrix = json.loads(Path("docs/operator/archetype-fixture-matrix.json").read_text(encoding="utf-8"))
    supplemental = json.loads(Path("docs/operator/supplemental-proof-decks.json").read_text(encoding="utf-8"))

    matrix_names = {deck["deck_name"] for deck in matrix["decks"]}
    supplemental_names = {deck["deck_name"] for deck in supplemental["decks"]}

    assert "CuteWarrior" not in matrix_names
    assert "CuteWarrior" in supplemental_names
    assert len(matrix["decks"]) == 11
```

If this exact coverage already exists, do not duplicate it.

- [ ] **Step 2: Confirm Boarlock and Kingslayer first missing links**

Run:

```powershell
rg -n "Fracking|Quick Pick|Boarlock|Kingslayer|needs_mulligan_claim|source_informed" docs\operator tests
```

Expected facts:

- Boarlock first missing chain: `WW_092` / `Fracking` -> `needs_mulligan_claim`.
- Kingslayer first missing chain: `DEEP_014` / `Quick Pick` -> `needs_mulligan_claim`.
- CuteWarrior is supplemental and does not close either gap.

- [ ] **Step 3: Update closure doc only if needed**

If `docs/operator/source-backed-strong-closure.md` does not already state the next target clearly, add this under the source-informed closure section:

```markdown
Next closure order:

1. `Boarlock`: close `WW_092` / `Fracking` -> `needs_mulligan_claim` only with exact Boarlock-relevant source evidence. Do not force a weak Fracking keep/discard claim.
2. `Kingslayer`: close `DEEP_014` / `Quick Pick` -> `needs_mulligan_claim` only with exact list-relevant source evidence.
3. `CuteWarrior`: keep supplemental until both source-informed rows are closed or explicitly reviewed as durable source-informed controls.
```

- [ ] **Step 4: Run matrix tests**

Run:

```powershell
python -m pytest tests\test_matrix_visibility.py tests\test_source_informed_closure_contract.py tests\test_matrix_governance.py tests\test_source_depth_closure_index.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 3 if docs/tests changed**

Run only if files changed:

```powershell
git add docs\operator\source-backed-strong-closure.md docs\operator\archetype-fixture-matrix.json docs\operator\supplemental-proof-decks.json tests\test_matrix_visibility.py tests\test_source_informed_closure_contract.py tests\test_matrix_governance.py tests\test_source_depth_closure_index.py
git commit -m "docs: lock boarlock closure order"
```

Do not commit if inspection shows the current docs and tests already state this.

---

### Task 4: Merge Runtime Apply Mode Branch To Main And Push

**Files:**
- No product files expected.
- Git refs: `codex/hsconfig-runtime-apply-mode-clarity`, `main`, `origin/main`.

**Interfaces:**
- Consumes: clean verified feature branch.
- Produces: `main` and `origin/main` containing the current runtime apply mode and audit evidence work.

- [ ] **Step 1: Verify feature branch is clean**

Run:

```powershell
git status --short --branch
git branch --show-current
```

Expected:

```text
## codex/hsconfig-runtime-apply-mode-clarity
codex/hsconfig-runtime-apply-mode-clarity
```

No untracked or modified files should remain.

- [ ] **Step 2: Run final pre-merge tests**

Run:

```powershell
python -m pytest -q
python scripts\sync_installed_skill.py --check
git diff --check
```

Expected:

- Full suite passes. Current known good baseline is `574 passed, 2 skipped`.
- Skill sync prints `HSConfig skill is in sync`.
- `git diff --check` prints no output.

- [ ] **Step 3: Fetch and inspect main**

Run:

```powershell
git fetch origin
git status --short --branch
git log --oneline --decorate --max-count=5 main
git log --oneline --decorate --max-count=5 origin/main
```

Expected: no local dirty files. If `main` has diverged from `origin/main`, stop and inspect before merging.

- [ ] **Step 4: Fast-forward or no-ff merge to main**

Prefer fast-forward when possible:

```powershell
git switch main
git pull --ff-only origin main
git merge --ff-only codex/hsconfig-runtime-apply-mode-clarity
```

If `--ff-only` is not possible but the divergence is only local feature commits, use:

```powershell
git merge --no-ff codex/hsconfig-runtime-apply-mode-clarity -m "merge: runtime apply mode clarity"
```

Do not use `git reset --hard`.

- [ ] **Step 5: Verify tests on main**

Run:

```powershell
python -m pytest tests\test_operator_summary.py tests\test_operator_guidance.py tests\test_apply_gate.py tests\test_runtime_apply.py tests\test_skill_files.py tests\test_docs_active_path.py -q
python -m pytest tests\test_matrix_visibility.py tests\test_source_informed_closure_contract.py tests\test_matrix_governance.py tests\test_source_depth_closure_index.py -q
python scripts\sync_installed_skill.py --check
git status --short --branch
```

Expected:

- Focused runtime/docs suite passes.
- Matrix governance suite passes.
- Skill sync is clean.
- `main` is clean and ahead of `origin/main`.

- [ ] **Step 6: Push main**

Run:

```powershell
git push origin main
```

Expected: push succeeds.

- [ ] **Step 7: Record final Git state**

Run:

```powershell
git status --short --branch
git log --oneline --decorate --max-count=8
```

Expected:

- `main` is clean and aligned with `origin/main`.
- Latest commits include runtime apply mode clarity and any audit evidence commit.

---

### Task 5: Prepare The Next Boarlock Closure Plan Stub

**Files:**
- Create: `docs/superpowers/plans/2026-07-08-hsconfig-boarlock-fracking-source-closure.md`
- Read: `docs/operator/source-backed-strong-closure.md`
- Read: `docs/research/2026-07-08-hsconfig-kingslayer-boarlock-mulligan-closure/results/Boarlock_Fracking_Mulligan_Closure.json`
- Read: `tests/fixtures/source_documents_boarlock_strong.json`

**Interfaces:**
- Consumes: merged main and current source-informed closure docs.
- Produces: a narrow future implementation plan for Boarlock only. This task writes the stub plan but does not implement Boarlock fixture changes.

- [ ] **Step 1: Inspect existing Boarlock evidence**

Run:

```powershell
Get-Content -Raw docs\research\2026-07-08-hsconfig-kingslayer-boarlock-mulligan-closure\results\Boarlock_Fracking_Mulligan_Closure.json
Get-Content -Raw tests\fixtures\source_documents_boarlock_strong.json
rg -n "WW_092|Fracking|needs_mulligan_claim|Boarlock" docs tests src
```

Expected: current evidence should show whether exact Fracking mulligan evidence exists. If evidence remains unavailable, the future plan must preserve Boarlock as source-informed rather than inventing a claim.

- [ ] **Step 2: Create a future Boarlock plan stub**

Create `docs/superpowers/plans/2026-07-08-hsconfig-boarlock-fracking-source-closure.md` with this minimum content:

```markdown
# HSConfig Boarlock Fracking Source Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Decide and implement the honest Boarlock `WW_092` / `Fracking` closure path without forcing weak source claims.

**Architecture:** Keep Boarlock in the existing 11-deck matrix. Add or update source documents only if exact Boarlock-relevant Fracking mulligan evidence exists; otherwise preserve the row as source-informed with an explicit stop condition and move the next closure slot to Kingslayer.

**Tech Stack:** Python 3.11+, pytest, existing HSConfig source document fixtures and source-depth reports.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig`.
- Do not add dependencies.
- Do not widen the representative matrix.
- Do not promote CuteWarrior into the representative matrix.
- Do not invent a Fracking mulligan claim.
- Do not relax `SOURCE_BACKED_STRONG` promotion gates.
- Do not add post-run or HSTuner logic.

---

## First Decision

Before any fixture edit, verify whether exact Boarlock-relevant Fracking mulligan evidence exists.

- If exact evidence exists: add the atomic mulligan claim to Boarlock source documents and run source-depth closure tests.
- If exact evidence does not exist: preserve Boarlock as source-informed with explicit stop condition and prepare Kingslayer Quick Pick as the next closure candidate.
```

Do not write the full Boarlock implementation yet in this plan. This task only creates the stub to prevent the next session from broadening scope accidentally.

- [ ] **Step 3: Validate the stub is discoverable**

Run:

```powershell
rg -n "Boarlock Fracking Source Closure|WW_092|Do not invent a Fracking mulligan claim|Kingslayer Quick Pick" docs\superpowers\plans\2026-07-08-hsconfig-boarlock-fracking-source-closure.md
```

Expected: all four phrases are found.

- [ ] **Step 4: Commit Task 5**

Run:

```powershell
git add docs\superpowers\plans\2026-07-08-hsconfig-boarlock-fracking-source-closure.md
git commit -m "docs: plan boarlock fracking source closure"
```

If this task is executed after pushing main in Task 4, commit on a new branch named `codex/hsconfig-boarlock-fracking-source-closure-plan` instead of directly on `main`.

---

### Task 6: Final Verification And Handoff

**Files:**
- Read: `README.md`
- Read: `docs/operator/README.md`
- Read: `.agents/skills/hsconfig/SKILL.md`
- Read: `docs/operator/source-backed-strong-closure.md`
- Read: `docs/operator/archetype-fixture-matrix.json`
- Read: `docs/operator/supplemental-proof-decks.json`

**Interfaces:**
- Consumes: all prior tasks.
- Produces: final verified state and one clear next step.

- [ ] **Step 1: Run final targeted verification**

Run:

```powershell
python -m pytest tests\test_skill_files.py tests\test_docs_active_path.py tests\test_scope_boundaries.py tests\test_operator_summary.py tests\test_apply_gate.py tests\test_runtime_apply.py tests\test_matrix_visibility.py tests\test_source_informed_closure_contract.py tests\test_matrix_governance.py tests\test_source_depth_closure_index.py -q
```

Expected: PASS.

- [ ] **Step 2: Run full suite**

Run:

```powershell
python -m pytest -q
```

Expected: PASS. Current known good baseline is `574 passed, 2 skipped`.

- [ ] **Step 3: Verify installed skill**

Run:

```powershell
python scripts\sync_installed_skill.py --check
```

Expected:

```text
HSConfig skill is in sync: C:\Users\darbo\.codex\skills\hsconfig
```

- [ ] **Step 4: Verify repo state**

Run:

```powershell
git status --short --branch
git log --oneline --decorate --max-count=10
```

Expected:

- Clean working tree.
- Branch state matches the execution choice from Task 4/5.

- [ ] **Step 5: Write final handoff note**

Final response must state:

- whether `main` was pushed
- whether the current audit package was committed or removed
- test results
- installed skill sync result
- exact next recommended task: Boarlock Fracking source closure first, Kingslayer Quick Pick second if Fracking evidence remains unavailable

Do not claim Boarlock is source-backed strong unless tests and reports prove it.

---

## Self-Review

- Spec coverage: This plan covers the recommendation: sync current branch/main, preserve or remove audit evidence cleanly, avoid matrix widening, keep CuteWarrior supplemental, and prepare Boarlock/Kingslayer source-depth closure.
- Placeholder scan: No placeholder tokens or unspecified implementation steps remain.
- Type consistency: The plan uses existing paths and status names: `runtime_apply_mode`, `SOURCE_BACKED_STRONG`, `SOURCE_INFORMED_APPLY_READY`, `WW_092`, `DEEP_014`, `Fracking`, and `Quick Pick`.
- Scope check: The plan intentionally avoids new runtime surfaces, broad CLI refactors, post-run logic, and a twelfth representative deck.

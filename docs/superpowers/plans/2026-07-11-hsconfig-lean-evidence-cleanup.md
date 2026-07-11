# HSConfig Lean Evidence Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce active-doc and historical-evidence ambiguity without changing HSConfig's lean runtime behavior. After this wave, old Superpowers/research material can still explain past decisions, but it must not suggest that HSConfig normally emits `Presume.json`, `Concede.json`, HSTuner-style replay analysis, winrate gates, or post-run candidate promotion.

**Architecture:** Documentation and tests only. Keep `hsconfig configure` as the product path. Strengthen the historical/superseded warnings in the old design spec, make `docs/research/current-truth.md` the explicit active evidence index, and add regression tests that prevent superseded research from becoming operator guidance again.

**Tech Stack:** Python, pytest, Markdown docs, existing HSConfig CLI, existing installed-skill sync script.

## Global Constraints

- Work only in `C:\Users\darbo\Documents\HSConfig`.
- Do not modify HSranger or HSTuner code, docs, runtime outputs, or logs.
- Do not change core generation behavior in `src/hsconfig/**` unless a test reveals a concrete defect.
- Keep normal output restricted to `GlobalValues.json`, `Mulligan.json`, per-card `<CARDID>.json`, and optional `Combo.json` when evidence supports combos.
- Do not make `Presume.json` or `Concede.json` normal output. They may remain historical/known surfaces only.
- Do not add replay parsing, HDT/Power.log analysis, winrate validation, candidate promotion, or apply/rollback loops to HSConfig.
- Active contract priority is:
  1. `docs/operator/README.md`
  2. `.agents/skills/hsconfig/SKILL.md`
  3. `docs/operator/universal-wild-no-block-contract.md`
  4. `docs/research/current-truth.md`
  5. Historical Superpowers/research artifacts
- `.superpowers/` remains ignored.
- Do not commit generated runtime packages, HearthRanger logs, HDT logs, Power.log files, `.hsreplay`, or private run evidence.

## File Structure

Modify:

- `docs/superpowers/specs/2026-07-05-hsconfig-design.md`
  - Add a strong superseded normal-path warning near the top.
  - State that later `Presume.json` / `Concede.json` references are historical design exploration.

- `docs/research/current-truth.md`
  - Add a compact "How To Read Historical Evidence" section.
  - State that active docs win over historical evidence.
  - State that new implementation work should be triggered by real deck output or live mechanic drift, not stale research alone.

- `docs/research/README.md`
  - Make `docs/research/current-truth.md` the only active evidence index.
  - Clarify that older research folders are historical evidence, not operator guidance.

- `tests/test_docs_active_path.py`
  - Add guard tests for the superseded spec warning, current-truth authority, and research README wording.

Do not modify:

- `src/hsconfig/**`
- `.agents/skills/hsconfig/**`
- `outputs/**`
- `artifacts/**`
- Runtime HearthRanger `CustomConfig` folders

## Tasks

### 1. Preflight Scope Guard

- [ ] Switch to `C:\Users\darbo\Documents\HSConfig`.
- [ ] Confirm branch and sync state:

```powershell
git status --short --branch
git rev-parse --short HEAD
git rev-parse --short origin/main
```

- [ ] Confirm the installed skill is already in sync before touching docs:

```powershell
python scripts\sync_installed_skill.py --check
```

- [ ] Run the focused current guard suite to ensure the baseline is green:

```powershell
python -m pytest tests\test_docs_active_path.py tests\test_skill_files.py tests\test_scope_boundaries.py -q
```

Expected result: tests pass before edits. If a baseline test fails, stop and diagnose the existing failure before changing docs.

### 2. Add Failing Doc-Contract Tests First

- [ ] Open `tests/test_docs_active_path.py`.
- [ ] Add these tests, adjusting only import style if the file already has helper functions:

```python
def test_historical_design_spec_carries_strong_superseded_warning():
    text = Path("docs/superpowers/specs/2026-07-05-hsconfig-design.md").read_text(
        encoding="utf-8"
    )

    assert "Superseded normal-path warning" in text
    assert (
        "Later references to optional `Presume.json` or `Concede.json` are historical"
        in text
    )
    assert "normal HSConfig output must not emit `Presume.json` or `Concede.json`" in text
    assert "docs/operator/README.md" in text
    assert ".agents/skills/hsconfig/SKILL.md" in text


def test_current_truth_prevents_old_evidence_from_overriding_operator_path():
    text = Path("docs/research/current-truth.md").read_text(encoding="utf-8")

    assert "Active docs win over historical evidence" in text
    assert "Do not start a new architecture wave from superseded research alone." in text
    assert (
        "Use real deck output or live mechanic drift as the trigger for new implementation work."
        in text
    )


def test_research_readme_names_current_truth_as_only_active_evidence_index():
    text = Path("docs/research/README.md").read_text(encoding="utf-8")

    assert "only active evidence index" in text
    assert "older research folders are historical evidence" in text
```

- [ ] Run only the three new tests and confirm they fail for missing wording:

```powershell
python -m pytest tests\test_docs_active_path.py::test_historical_design_spec_carries_strong_superseded_warning tests\test_docs_active_path.py::test_current_truth_prevents_old_evidence_from_overriding_operator_path tests\test_docs_active_path.py::test_research_readme_names_current_truth_as_only_active_evidence_index -q
```

Expected result: assertion failures from missing text. If they pass before implementation, inspect whether the repo already contains equivalent wording and simplify the planned edits.

### 3. Tighten The Historical Design Spec

- [ ] Open `docs/superpowers/specs/2026-07-05-hsconfig-design.md`.
- [ ] Immediately after the existing historical/superseded note near the top, add this block:

```markdown
> **Superseded normal-path warning:** Later references to optional `Presume.json` or `Concede.json` are historical design exploration. The live normal path is `hsconfig configure`, and normal HSConfig output must not emit `Presume.json` or `Concede.json`. Use `docs/operator/README.md`, `.agents/skills/hsconfig/SKILL.md`, and `docs/operator/universal-wild-no-block-contract.md` as the active contract.
```

- [ ] Do not rewrite the rest of the historical spec.
- [ ] Do not delete old sections unless a test or exact operator ambiguity requires it.

Rationale: the spec is useful as historical design context, but repeated old `Presume.json` / `Concede.json` references are search-noise. A strong top-level warning is lower-risk than editing many historical sections.

### 4. Make Current Truth The Evidence Authority

- [ ] Open `docs/research/current-truth.md`.
- [ ] Add a short section after the opening status/summary section:

```markdown
## How To Read Historical Evidence

Active docs win over historical evidence. Do not start a new architecture wave from superseded research alone. Use real deck output or live mechanic drift as the trigger for new implementation work.

Older research packages can explain why a decision happened, but they do not override the operator path, installed skill, or universal Wild no-block contract. If old evidence mentions normal `Presume.json`, `Concede.json`, replay tuning, winrate gates, or candidate promotion, treat that as historical context unless the active docs explicitly reintroduce it.
```

- [ ] Keep this section compact. This document should remain an index, not a new plan.
- [ ] Do not add a new research package for this cleanup unless implementation discovers a genuinely unknown current fact.

### 5. Clarify Research README

- [ ] Open `docs/research/README.md`.
- [ ] Add or update one short paragraph so it contains both exact phrases required by the tests:

```markdown
`docs/research/current-truth.md` is the only active evidence index. The older research folders are historical evidence and should be read through that index before influencing implementation or operator guidance.
```

- [ ] Keep the README short.
- [ ] Do not duplicate the full current-truth content here.

### 6. Verify Focused Tests

- [ ] Run the three new tests:

```powershell
python -m pytest tests\test_docs_active_path.py::test_historical_design_spec_carries_strong_superseded_warning tests\test_docs_active_path.py::test_current_truth_prevents_old_evidence_from_overriding_operator_path tests\test_docs_active_path.py::test_research_readme_names_current_truth_as_only_active_evidence_index -q
```

- [ ] Run the focused docs/skill/scope suite:

```powershell
python -m pytest tests\test_docs_active_path.py tests\test_skill_files.py tests\test_scope_boundaries.py -q
```

- [ ] Confirm installed skill sync remains unchanged:

```powershell
python scripts\sync_installed_skill.py --check
```

Expected result: all pass. If sync check fails, do not blindly sync; inspect whether `.agents/skills/hsconfig/SKILL.md` was accidentally changed.

### 7. Wider Regression And Diff Review

- [ ] Run the full suite:

```powershell
python -m pytest -q
```

- [ ] Run diff whitespace check:

```powershell
git diff --check
```

- [ ] Review the full diff:

```powershell
git diff -- docs/superpowers/specs/2026-07-05-hsconfig-design.md docs/research/current-truth.md docs/research/README.md tests/test_docs_active_path.py
```

- [ ] Confirm there are no changes under runtime outputs or core source:

```powershell
git status --short
```

Expected changed files:

- `docs/superpowers/specs/2026-07-05-hsconfig-design.md`
- `docs/research/current-truth.md`
- `docs/research/README.md`
- `tests/test_docs_active_path.py`
- `docs/superpowers/plans/2026-07-11-hsconfig-lean-evidence-cleanup.md`

### 8. Commit Boundary

- [ ] Stage only the expected files:

```powershell
git add docs/superpowers/specs/2026-07-05-hsconfig-design.md docs/research/current-truth.md docs/research/README.md tests/test_docs_active_path.py docs/superpowers/plans/2026-07-11-hsconfig-lean-evidence-cleanup.md
```

- [ ] Commit:

```powershell
git commit -m "docs: tighten historical evidence guidance"
```

- [ ] Push only after the full verification above passes:

```powershell
git push origin main
```

## Acceptance Criteria

- The old design spec clearly warns that later `Presume.json` / `Concede.json` references are historical and not normal output guidance.
- `docs/research/current-truth.md` explicitly states that active docs win over historical evidence.
- `docs/research/README.md` points readers to `current-truth.md` as the only active evidence index.
- Historical replay tuning, winrate gates, and candidate promotion references are explicitly quarantined unless active docs reintroduce them.
- No HSConfig core behavior changes.
- No installed skill changes.
- No runtime artifacts are created or committed.
- Focused tests pass.
- Full test suite passes.
- `git status --short --branch` is clean after push.

## Self-Review Checklist

- [ ] Did this wave reduce ambiguity without adding architecture?
- [ ] Are the active operator path and installed skill still the only normal user-facing workflow?
- [ ] Are `Presume.json` and `Concede.json` still treated as non-normal historical/known surfaces?
- [ ] Did the tests guard the actual risk instead of testing incidental wording too broadly?
- [ ] Did the implementation avoid HSTuner concepts such as replay tuning, winrate gates, and candidate promotion?
- [ ] Is the final diff small enough that future agents can understand it quickly?

## Expected Final Report

Report only:

- Plan implemented as docs/test cleanup.
- Files changed.
- Verification commands and results.
- Git commit and push status.
- Any residual risk, especially if full pytest was skipped or timed out.

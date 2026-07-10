# HSConfig Lean No-Block Mechanic Visibility Polish

> **For agentic workers:** Execute this plan step by step. Keep changes small, test-first where code behavior changes, and do not widen HSConfig into HSTuner/post-run analysis. HSConfig's job remains: given a valid deck, produce a load-safe, guide-aligned HearthRanger CustomConfig package without blocking on unknown or newly released mechanics.

## Objective

Make the current HSConfig skill slightly more future-proof without bloating it:

- Add explicit, non-blocking visibility for current modern mechanics found during the latest audit: `rewind`, `herald`, and `shatter`.
- Keep the universal no-block contract precise: valid exact deck input must compile and apply load-safe packages; this does not guarantee perfect source-backed gameplay for every possible deck.
- Clarify that `Concede.json` and `Presume.json` are HearthRanger-documented surfaces but intentionally outside HSConfig's normal package path.
- Guard active docs and skill files against stale historical matrix-count wording.
- Include the latest research package in the active evidence trail.

## Non-Goals

- Do not add HSTuner, replay, winrate, post-game tuning, or runtime-log analysis logic.
- Do not add new representative decks to the validation matrix for this wave.
- Do not make `rewind`, `herald`, or `shatter` runtime-lowerable. They are warning-only/report-only unless future public VisionAI evidence proves a safe direct patch surface.
- Do not change the apply gate semantics.
- Do not emit `Concede.json` or `Presume.json` in normal HSConfig output.

## Current Evidence

Latest research package:

- `docs/research/2026-07-10-hsconfig-no-block-universal-skill-audit-v4/outline.yaml`
- `docs/research/2026-07-10-hsconfig-no-block-universal-skill-audit-v4/fields.yaml`
- `docs/research/2026-07-10-hsconfig-no-block-universal-skill-audit-v4/results/HSConfig_Current_Repo_No_Block_Workflow_Audit.json`
- `docs/research/2026-07-10-hsconfig-no-block-universal-skill-audit-v4/results/Modern_Hearthstone_Mechanics_And_Wild_Deck_Coverage_Audit.json`
- `docs/research/2026-07-10-hsconfig-no-block-universal-skill-audit-v4/results/Universal_Any_Deck_No_Block_Proof_Strategy.json`
- `docs/research/2026-07-10-hsconfig-no-block-universal-skill-audit-v4/results/HearthRanger_VisionAI_Public_Surface_Audit.json`

Validation already observed before this plan:

```powershell
python C:\Users\darbo\.codex\skills\research\validate_json.py -f docs\research\2026-07-10-hsconfig-no-block-universal-skill-audit-v4\fields.yaml -d docs\research\2026-07-10-hsconfig-no-block-universal-skill-audit-v4\results
```

Expected output:

```text
Validation passed: 4/4
Average coverage: 100.0%
```

## Task 1: Add Non-Blocking 2026 Mechanic Registry And Drift Coverage

**Goal:** `rewind`, `herald`, and `shatter` are explicitly visible as warning-only mechanics instead of falling through as anonymous unknowns.

### 1.1 Write failing mechanic-support test

- Edit `tests/test_mechanic_support.py`.
- In `test_current_modern_wild_mechanics_are_registered_without_blocking`, extend the expected mechanics to include:

```python
"rewind": "warning_only",
"herald": "warning_only",
"shatter": "warning_only",
```

- For each of these mechanics, assert:

```python
assert summary.registered is True
assert summary.support_level == "warning_only"
assert summary.normal_path_surfaces == ["report-only"]
assert operator_visibility_bucket(summary) == "warning_only"
```

Run:

```powershell
python -m pytest tests\test_mechanic_support.py -q
```

Expected before implementation:

```text
FAILED ... test_current_modern_wild_mechanics_are_registered_without_blocking
```

The failure should be caused by missing explicit registration for at least one of the three new mechanics.

### 1.2 Write failing mechanic-drift test

- Edit `tests/test_mechanic_drift.py`.
- In `test_mechanic_drift_detects_modern_text_only_mechanics_without_blocking`, add sample cards:

```python
{"id": "REWIND_001", "type": "SPELL", "mechanics": [], "referencedTags": [], "text": "Rewind: Repeat your last spell."},
{"id": "HERALD_001", "type": "MINION", "mechanics": [], "referencedTags": [], "text": "Herald: Draw a minion."},
{"id": "SHATTER_001", "type": "SPELL", "mechanics": [], "referencedTags": [], "text": "Shatter a Frozen minion."},
```

- Add `rewind`, `herald`, and `shatter` to the expected `text_only_mechanics` set.
- Assert each reported support level is `warning_only`.

Run:

```powershell
python -m pytest tests\test_mechanic_drift.py -q
```

Expected before implementation:

```text
FAILED ... test_mechanic_drift_detects_modern_text_only_mechanics_without_blocking
```

The failure should show that the text-only mechanics are not yet detected.

### 1.3 Implement registry rows

- Edit `src/hsconfig/mechanic_support.py`.
- Add three `MechanicSupport` entries to `MECHANIC_SUPPORT`.
- Use `warning_only`, `report-only`, and clear boundaries.

Required semantics:

```python
"rewind": MechanicSupport(
    mechanic="rewind",
    support_level="warning_only",
    normal_path_surfaces=("report-only",),
    proof_basis="text drift visibility only; no documented VisionAI temporal prior-state surface in the normal package",
    never_autopatch_reason="Do not lower temporal replay/prior-state effects into card values without exact public VisionAI support.",
),
"herald": MechanicSupport(
    mechanic="herald",
    support_level="warning_only",
    normal_path_surfaces=("report-only",),
    proof_basis="text drift visibility only; no documented normal-path runtime action surface",
    never_autopatch_reason="Do not infer a generic card-value action from a keyword whose concrete effect is card-specific.",
),
"shatter": MechanicSupport(
    mechanic="shatter",
    support_level="warning_only",
    normal_path_surfaces=("report-only",),
    proof_basis="text drift visibility only; conditional frozen/minion state must stay review-visible unless exact card behavior is known",
    never_autopatch_reason="Do not auto-patch conditional destroy/damage targeting without exact target and board-state semantics.",
),
```

If the local `MechanicSupport` constructor uses different field names, preserve the existing local shape and encode the same meaning in the available fields.

### 1.4 Implement drift patterns

- Edit `src/hsconfig/mechanic_drift.py`.
- Add to `TEXT_MECHANIC_PATTERNS`:

```python
"rewind": ("rewind",),
"herald": ("herald",),
"shatter": ("shatter",),
```

### 1.5 Verify Task 1

Run:

```powershell
python -m pytest tests\test_mechanic_support.py tests\test_mechanic_drift.py -q
```

Expected output:

```text
passed
```

Commit after Task 1:

```powershell
git add src\hsconfig\mechanic_support.py src\hsconfig\mechanic_drift.py tests\test_mechanic_support.py tests\test_mechanic_drift.py
git commit -m "feat: name current mechanics as non-blocking warnings"
```

## Task 2: Clarify Active Operator And Skill Wording

**Goal:** The normal docs and installed skill explain the current no-block posture without overstating optimization guarantees.

### 2.1 Write failing docs/skill test

- Edit `tests/test_skill_files.py`.
- In the existing modern-mechanic visibility test, require active docs/skill text to include:

```python
"`rewind`",
"`herald`",
"`shatter`",
```

- Add or extend a test so active operator docs and skill docs contain all of:

```python
"Concede.json"
"Presume.json"
"documented"
"normal HSConfig"
"does not emit"
```

- Scope the assertion to active files only:
  - `docs/operator/README.md`
  - `docs/operator/universal-wild-no-block-contract.md`
  - `.agents/skills/hsconfig/SKILL.md`
  - `.agents/skills/hsconfig/references/workflow.md`
  - `.agents/skills/hsconfig/references/visionai-surfaces.md`

Run:

```powershell
python -m pytest tests\test_skill_files.py -q
```

Expected before implementation:

```text
FAILED
```

The failure should point to missing mechanics or missing `Concede.json`/`Presume.json` boundary wording.

### 2.2 Update operator docs

- Edit `docs/operator/README.md`.
- Wherever the active modern-mechanic list appears, include:

```markdown
`rewind`, `herald`, `shatter`
```

- Add this concise boundary wording near the normal output surface explanation:

```markdown
`Concede.json` and `Presume.json` are HearthRanger-documented VisionAI surfaces, but normal HSConfig does not emit them. Their absence is not a block for a load-safe deck package.
```

- Edit `docs/operator/universal-wild-no-block-contract.md`.
- Add the same three mechanics to the non-blocking modern-mechanic visibility section.
- Add the same `Concede.json`/`Presume.json` boundary, preserving the current meaning that normal HSConfig output is limited to load-safe core surfaces.

### 2.3 Update skill source

- Edit `.agents/skills/hsconfig/SKILL.md`.
- Add `rewind`, `herald`, and `shatter` to the modern mechanics list.
- Add:

```markdown
`Concede.json` and `Presume.json` are documented HearthRanger surfaces, but normal HSConfig does not emit them; absence never blocks a valid load-safe package.
```

- Edit `.agents/skills/hsconfig/references/workflow.md`.
- Add the same mechanics and surface boundary in the normal workflow section.
- Edit `.agents/skills/hsconfig/references/visionai-surfaces.md` only if it does not already clearly say that `Concede.json` and `Presume.json` are documented but outside the normal HSConfig path.

### 2.4 Verify and sync installed skill

Run:

```powershell
python -m pytest tests\test_skill_files.py -q
python scripts\sync_installed_skill.py
python scripts\sync_installed_skill.py --check
```

Expected output:

```text
passed
HSConfig skill is in sync: C:\Users\darbo\.codex\skills\hsconfig
```

Commit after Task 2:

```powershell
git add docs\operator\README.md docs\operator\universal-wild-no-block-contract.md .agents\skills\hsconfig C:\Users\darbo\.codex\skills\hsconfig tests\test_skill_files.py
git commit -m "docs: clarify no-block mechanic and legacy surface wording"
```

If Git refuses the installed skill path because it is outside the repository, commit only repository files and keep the installed skill synchronized on disk.

## Task 3: Guard Active Docs Against Stale Historical Claims

**Goal:** Historical research can remain in the repo, but active docs must not reintroduce outdated matrix-count or closure-target claims.

### 3.1 Write active-doc stale-claim guard

- Edit `tests/test_docs_active_path.py`.
- Add a test named:

```python
def test_active_docs_do_not_reintroduce_stale_matrix_counts_or_closure_targets():
```

- Scan only active files:

```python
active_files = [
    "README.md",
    "docs/operator/README.md",
    "docs/operator/universal-wild-no-block-contract.md",
    "docs/operator/source-backed-strong-closure.md",
    ".agents/skills/hsconfig/SKILL.md",
    ".agents/skills/hsconfig/references/workflow.md",
    "docs/research/current-truth.md",
]
```

- Forbid:

```python
forbidden = [
    "four core_source_backed_fixture rows",
    "4 core_source_backed_fixture rows",
    "seven source_informed_valid_fixture rows",
    "7 source_informed_valid_fixture rows",
    "Next actionable closure target after durable Boarlock preservation",
    "Close the current Kingslayer and Boarlock",
]
```

- Require:

```python
"After durable Boarlock and Kingslayer preservation, there is no current actionable source-informed closure target."
"Research artifacts are evidence, not operator instructions."
```

Run:

```powershell
python -m pytest tests\test_docs_active_path.py -q
```

Expected before docs update:

```text
FAILED
```

The failure should indicate either stale active text or missing current-truth wording.

### 3.2 Update current truth

- Edit `docs/research/current-truth.md`.
- Add the latest research package as active evidence:

```markdown
## 2026-07-10 No-Block Universal Skill Audit V4

- Path: `docs/research/2026-07-10-hsconfig-no-block-universal-skill-audit-v4/`
- Role: active evidence for no-block universal skill posture, modern mechanic visibility, and public VisionAI surface boundaries.
- Operator implication: add visibility-only warning rows for `rewind`, `herald`, and `shatter`; keep the normal package path limited to load-safe HSConfig surfaces.
- Boundary: research artifacts are evidence, not operator instructions.
```

- Ensure the file contains:

```markdown
After durable Boarlock and Kingslayer preservation, there is no current actionable source-informed closure target.
```

### 3.3 Verify research package

Run:

```powershell
python C:\Users\darbo\.codex\skills\research\validate_json.py -f docs\research\2026-07-10-hsconfig-no-block-universal-skill-audit-v4\fields.yaml -d docs\research\2026-07-10-hsconfig-no-block-universal-skill-audit-v4\results
python -m pytest tests\test_docs_active_path.py -q
```

Expected output:

```text
Validation passed: 4/4
Average coverage: 100.0%
passed
```

Commit after Task 3:

```powershell
git add docs\research\current-truth.md docs\research\2026-07-10-hsconfig-no-block-universal-skill-audit-v4 tests\test_docs_active_path.py
git commit -m "test: guard active docs against stale no-block claims"
```

## Task 4: Final Verification And GitHub Update

**Goal:** Leave the repo current, tested, and pushed.

### 4.1 Run focused verification

Run:

```powershell
python -m pytest tests\test_mechanic_support.py tests\test_mechanic_drift.py tests\test_skill_files.py tests\test_docs_active_path.py tests\test_universal_wild_no_block_matrix.py tests\test_supplemental_cute_warrior_load_safe.py -q
python scripts\sync_installed_skill.py --check
python C:\Users\darbo\.codex\skills\research\validate_json.py -f docs\research\2026-07-10-hsconfig-no-block-universal-skill-audit-v4\fields.yaml -d docs\research\2026-07-10-hsconfig-no-block-universal-skill-audit-v4\results
```

Expected output:

```text
passed
HSConfig skill is in sync: C:\Users\darbo\.codex\skills\hsconfig
Validation passed: 4/4
Average coverage: 100.0%
```

### 4.2 Run full suite

Run:

```powershell
python -m pytest -q
```

Expected output:

```text
passed
```

If the full suite takes longer than expected, keep it running to completion. Do not claim completion from focused tests alone.

### 4.3 Review diff and status

Run:

```powershell
git status --short --branch
git diff --stat HEAD
git log --oneline -5
```

Expected:

- Branch is `main`.
- No unstaged changes after final commit.
- New commits are present locally.
- The latest research package is either committed or intentionally left out with a documented reason. Preferred for this plan: commit it.

### 4.4 Push

Run:

```powershell
git push origin main
```

Expected output:

```text
main -> main
```

## Acceptance Criteria

- `rewind`, `herald`, and `shatter` are explicit `warning_only` mechanics.
- Mechanic drift reports those mechanics when card text exposes them.
- The no-block contract still compiles valid deck packages without adding hard blocks for unsupported mechanics.
- Active docs and skill files mention the three mechanics and the `Concede.json`/`Presume.json` normal-path boundary.
- Active docs are guarded against stale matrix-count and stale closure-target phrases.
- Installed HSConfig skill is synchronized.
- Research package validates at 100 percent coverage.
- Focused tests and full test suite pass.
- Repo is pushed to `origin/main`.

## Self-Review Checklist

- [ ] Did we avoid adding HSTuner/post-run scope?
- [ ] Did we avoid adding new representative deck fixtures?
- [ ] Did we avoid pretending `rewind`, `herald`, or `shatter` are runtime-lowerable?
- [ ] Did we preserve the meaning of "nothing is blocked" as load-safe package generation for valid exact deck input?
- [ ] Did we keep `Concede.json` and `Presume.json` documented but outside the normal HSConfig output path?
- [ ] Did we sync the installed skill after editing `.agents/skills/hsconfig`?
- [ ] Did we commit the latest research package or document why it was not committed?
- [ ] Did full verification run before pushing?

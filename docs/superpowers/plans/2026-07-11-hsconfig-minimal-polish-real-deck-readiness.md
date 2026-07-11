# HSConfig Minimal Polish And Real-Deck Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Correct the small Presume documentation drift, keep HSConfig lean, make the operator path faster to read, preserve the new audit as evidence, and leave the skill ready for real deck usage.

**Architecture:** This is a documentation-and-contract polish wave, not a new runtime feature. The normal product boundary stays unchanged: HSConfig is pre-run only, `hsconfig configure` remains the normal command, `reports/operator_summary.json` remains the single gate, and HSTuner owns post-run evaluation and tuning.

**Tech Stack:** Python, pytest, Markdown docs, installed Codex skill sync script, HearthRanger VisionAI CustomConfig docs, existing HSConfig CLI/test suite.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig`.
- Do not add dependencies.
- Do not broaden HSConfig into replay parsing, winrate inspection, runtime log analysis, candidate promotion, or after-game tuning.
- Do not change normal runtime output policy: `GlobalValues.json`, `Mulligan.json`, per-card `<CARDID>.json`, and `Combo.json` when concrete valid combos exist.
- Do not emit `Presume.json` or `Concede.json` in the normal HSConfig path.
- Keep semantic, guide-depth, and warning-only mechanic gaps non-blocking for load-safe packages.
- Keep real technical defects blocking: invalid JSON, missing required runtime files, unsupported normal-path surfaces, stale or forged apply evidence, malformed package structure.
- Research folders are evidence, not operator instructions. Normal operation starts at `README.md` and `docs/operator/README.md`.
- Preserve the installed skill sync contract: `.agents/skills/hsconfig` and `C:\Users\darbo\.codex\skills\hsconfig` must match after implementation.

---

## File Structure

- Modify `tests/test_skill_files.py`: update active documentation assertions so Presume is recognized as a documented AOE play-around surface while still forbidden as normal output.
- Modify `README.md`: keep the root README short and align the normal-path wording with the corrected Presume/Concede contract.
- Modify `docs/operator/README.md`: add a compact Quick Start and correct the Presume paragraph.
- Modify `docs/operator/universal-wild-no-block-contract.md`: correct Presume wording in the durable no-block contract.
- Modify `.agents/skills/hsconfig/SKILL.md`: correct the compact skill rule.
- Modify `.agents/skills/hsconfig/references/workflow.md`: correct workflow reference wording.
- Modify `.agents/skills/hsconfig/references/visionai-surfaces.md`: correct runtime surface reference wording.
- Modify `docs/research/current-truth.md`: add the post-hardening audit package as active evidence.
- Add `docs/research/2026-07-11-hsconfig-post-hardening-skill-audit/README.md`: mark the new audit package as evidence only.
- Keep existing untracked research files under `docs/research/2026-07-11-hsconfig-post-hardening-skill-audit/`: `outline.yaml`, `fields.yaml`, and five result JSON files.
- Add `docs/superpowers/plans/2026-07-11-hsconfig-minimal-polish-real-deck-readiness.md`: keep this implementation plan as the execution record.

---

### Task 1: Update Presume/Concede Documentation Contract Tests

**Files:**
- Modify: `tests/test_skill_files.py`

**Interfaces:**
- Consumes: Active docs and skill files as plain UTF-8 text.
- Produces: A failing test that requires the corrected Presume AOE wording and still proves normal HSConfig output does not include Presume or Concede.

- [ ] **Step 1: Replace the stale overclaim test with a current truth test**

In `tests/test_skill_files.py`, replace the full `test_active_docs_do_not_overclaim_presume_first_party_documentation` function with:

```python
def test_active_docs_document_presume_aoe_surface_without_normal_output():
    active_files = [
        Path("docs/operator/README.md"),
        Path("docs/operator/universal-wild-no-block-contract.md"),
        SKILL_ROOT / "SKILL.md",
        SKILL_ROOT / "references" / "workflow.md",
        SKILL_ROOT / "references" / "visionai-surfaces.md",
    ]
    required = [
        "`Concede.json` is publicly documented",
        "`Presume.json` is publicly documented on HearthRanger's AOE play-around page",
        "normal HSConfig does not emit `Presume.json` or `Concede.json`",
        "absence never blocks a valid load-safe package",
    ]
    forbidden = [
        "without a current verified first-party help-page citation",
        "does not currently verify a current first-party help-page citation",
        "lacks a current verified first-party help-page citation",
        "Presume/Concede are documented normal outputs",
    ]

    for path in active_files:
        text = path.read_text(encoding="utf-8")
        for phrase in required:
            assert phrase in text, f"{path}: {phrase}"
        for phrase in forbidden:
            assert phrase not in text, f"{path}: {phrase}"
```

- [ ] **Step 2: Run the new test and verify it fails before docs change**

Run:

```powershell
python -m pytest tests\test_skill_files.py::test_active_docs_document_presume_aoe_surface_without_normal_output -q
```

Expected: FAIL because the active docs still contain the stale "without a current verified first-party help-page citation" wording.

- [ ] **Step 3: Keep the normal-output guard unchanged**

Do not weaken `test_skill_docs_keep_presume_concede_out_of_normal_path`.

Run:

```powershell
python -m pytest tests\test_skill_files.py::test_skill_docs_keep_presume_concede_out_of_normal_path -q
```

Expected before Task 2: PASS.

- [ ] **Step 4: Commit the failing test only if using strict TDD checkpoints**

If checkpoint commits are used, commit only the test edit:

```powershell
git add tests\test_skill_files.py
git commit -m "test: require current Presume surface wording"
```

If the execution agent keeps one final commit, skip this checkpoint commit and continue to Task 2.

---

### Task 2: Correct Presume Runtime-Surface Wording In Active Docs And Skill

**Files:**
- Modify: `README.md`
- Modify: `docs/operator/README.md`
- Modify: `docs/operator/universal-wild-no-block-contract.md`
- Modify: `.agents/skills/hsconfig/SKILL.md`
- Modify: `.agents/skills/hsconfig/references/workflow.md`
- Modify: `.agents/skills/hsconfig/references/visionai-surfaces.md`

**Interfaces:**
- Consumes: HearthRanger public docs truth that `Presume.json` is documented on the AOE play-around page.
- Produces: Consistent active wording: `Presume.json` is documented, remains non-normal output, and its absence never blocks a valid load-safe package.

- [ ] **Step 1: Replace the stale short-form sentence everywhere it appears**

Replace this sentence wherever it appears:

```text
`Concede.json` is publicly documented; `Presume.json` is legacy/public compatibility without a current verified first-party help-page citation, and normal HSConfig does not emit `Presume.json` or `Concede.json`; absence never blocks a valid load-safe package.
```

with:

```text
`Concede.json` is publicly documented; `Presume.json` is publicly documented on HearthRanger's AOE play-around page, and normal HSConfig does not emit `Presume.json` or `Concede.json`; absence never blocks a valid load-safe package.
```

Apply this replacement in:

- `.agents/skills/hsconfig/references/workflow.md`
- `.agents/skills/hsconfig/references/visionai-surfaces.md`

- [ ] **Step 2: Replace the skill bullet**

In `.agents/skills/hsconfig/SKILL.md`, replace:

```text
- `Concede.json` is documented. `Presume.json` is legacy/public compatibility without a current verified first-party help-page citation. Normal HSConfig does not emit `Presume.json` or `Concede.json`; absence never blocks a valid load-safe package.
```

with:

```text
- `Concede.json` is publicly documented. `Presume.json` is publicly documented on HearthRanger's AOE play-around page. Normal HSConfig does not emit `Presume.json` or `Concede.json`; absence never blocks a valid load-safe package.
```

- [ ] **Step 3: Replace the operator guide bullet**

In `docs/operator/README.md`, replace:

```text
- `Concede.json` is a publicly documented HearthRanger VisionAI surface. `Presume.json` is treated as known legacy/public compatibility; this repo does not currently verify a current first-party help-page citation for it, and normal HSConfig does not emit either surface. Their absence is not a block for a load-safe deck package.
```

with:

```text
- `Concede.json` is a publicly documented HearthRanger VisionAI surface. `Presume.json` is publicly documented on HearthRanger's AOE play-around page for opponent hand-card assumptions. Normal HSConfig does not emit `Presume.json` or `Concede.json`; absence never blocks a valid load-safe package.
```

- [ ] **Step 4: Replace the no-block contract paragraph**

In `docs/operator/universal-wild-no-block-contract.md`, replace:

```text
`Concede.json` is a publicly documented HearthRanger VisionAI surface. `Presume.json` is treated as known legacy/public compatibility; this repo does not currently verify a current first-party help-page citation for it, and normal HSConfig does not emit either surface. Their absence is not a block for a load-safe deck package.
```

with:

```text
`Concede.json` is a publicly documented HearthRanger VisionAI surface. `Presume.json` is publicly documented on HearthRanger's AOE play-around page for opponent hand-card assumptions. Normal HSConfig does not emit `Presume.json` or `Concede.json`; absence never blocks a valid load-safe package.
```

- [ ] **Step 5: Make the root README explicit without making it longer**

In `README.md`, replace:

```text
HSConfig is pre-run only. It does not parse replays, inspect winrate, analyze runtime logs, promote candidates, or tune after games. Those are HSTuner concerns. `Presume.json` and `Concede.json` are not emitted in the normal path.
```

with:

```text
HSConfig is pre-run only. It does not parse replays, inspect winrate, analyze runtime logs, promote candidates, or tune after games. Those are HSTuner concerns. `Presume.json` and `Concede.json` are documented HearthRanger surfaces, but HSConfig does not emit them in the normal path.
```

- [ ] **Step 6: Run the Presume contract tests**

Run:

```powershell
python -m pytest tests\test_skill_files.py::test_active_docs_document_presume_aoe_surface_without_normal_output tests\test_skill_files.py::test_skill_docs_keep_presume_concede_out_of_normal_path -q
```

Expected: PASS.

- [ ] **Step 7: Run the compact skill tests**

Run:

```powershell
python -m pytest tests\test_skill_files.py::test_skill_and_workflow_stay_compact_and_canonical tests\test_skill_files.py::test_skill_docs_preserve_hsconfig_boundaries_without_verbatim_duplication -q
```

Expected: PASS. If the compactness test fails because the skill or workflow exceeds the line limit, shorten prose without changing the contract.

---

### Task 3: Add A Compact Operator Quick Start

**Files:**
- Modify: `tests/test_operator_guidance.py`
- Modify: `docs/operator/README.md`

**Interfaces:**
- Consumes: Existing `docs/operator/README.md` as the canonical operator entry point.
- Produces: A short top-of-file Quick Start that lets the user run the normal path without reading the full expert guide.

- [ ] **Step 1: Add a failing quick-start test**

Append this test to `tests/test_operator_guidance.py`:

```python
def test_operator_readme_has_compact_quick_start_before_details():
    text = Path("docs/operator/README.md").read_text(encoding="utf-8")

    quick_start_index = text.index("## Quick Start")
    preferred_path_index = text.index("## Preferred Normal Path")
    expert_path_index = text.index("## Expert Paths")

    assert quick_start_index < preferred_path_index < expert_path_index
    quick_start = text[quick_start_index:preferred_path_index]

    assert "Run `hsconfig configure` for normal operation." in quick_start
    assert "Open `reports/operator_summary.json` first." in quick_start
    assert "`technical_status=VALID_PACKAGE` plus `runtime_apply_mode=load_safe_apply` means runtime apply is allowed." in quick_start
    assert "Warnings are follow-up work, not a second apply gate." in quick_start
    assert "HSTuner owns post-run evaluation and tuning." in quick_start
    assert len([line for line in quick_start.splitlines() if line.strip().startswith("- ")]) <= 6
```

- [ ] **Step 2: Run the new quick-start test and verify it fails**

Run:

```powershell
python -m pytest tests\test_operator_guidance.py::test_operator_readme_has_compact_quick_start_before_details -q
```

Expected: FAIL because `## Quick Start` is not present yet.

- [ ] **Step 3: Insert the Quick Start section**

In `docs/operator/README.md`, insert this section after the opening research-artifacts paragraph and before `## Preferred Normal Path`:

```markdown
## Quick Start

- Run `hsconfig configure` for normal operation.
- Open `reports/operator_summary.json` first.
- `technical_status=VALID_PACKAGE` plus `runtime_apply_mode=load_safe_apply` means runtime apply is allowed.
- Warnings are follow-up work, not a second apply gate.
- HSTuner owns post-run evaluation and tuning.
```

- [ ] **Step 4: Run operator guidance tests**

Run:

```powershell
python -m pytest tests\test_operator_guidance.py::test_operator_docs_point_to_research_index_without_making_it_operator_path tests\test_operator_guidance.py::test_operator_readme_has_compact_quick_start_before_details -q
```

Expected: PASS.

- [ ] **Step 5: Run active-path docs tests**

Run:

```powershell
python -m pytest tests\test_docs_active_path.py tests\test_operator_guidance.py -q
```

Expected: PASS.

---

### Task 4: Index The New Audit As Evidence, Not Guidance

**Files:**
- Create: `docs/research/2026-07-11-hsconfig-post-hardening-skill-audit/README.md`
- Modify: `docs/research/current-truth.md`
- Test: `tests/test_research_audit_schema.py`

**Interfaces:**
- Consumes: Existing untracked audit package under `docs/research/2026-07-11-hsconfig-post-hardening-skill-audit/`.
- Produces: Current-truth entry and README boundary so the audit is discoverable without becoming operator guidance.

- [ ] **Step 1: Add a failing current-truth test**

Append this test to `tests/test_research_audit_schema.py`:

```python
def test_post_hardening_skill_audit_is_indexed_as_evidence_only():
    root = Path("docs/research/2026-07-11-hsconfig-post-hardening-skill-audit")
    readme = (root / "README.md").read_text(encoding="utf-8")
    current_truth = Path("docs/research/current-truth.md").read_text(encoding="utf-8")

    assert "Research artifacts are evidence, not operator instructions." in readme
    assert "Normal operation starts at `README.md` and `docs/operator/README.md`." in readme
    assert "post-hardening skill audit evidence" in current_truth
    assert "2026-07-11-hsconfig-post-hardening-skill-audit" in current_truth
```

- [ ] **Step 2: Run the new research-index test and verify it fails**

Run:

```powershell
python -m pytest tests\test_research_audit_schema.py::test_post_hardening_skill_audit_is_indexed_as_evidence_only -q
```

Expected: FAIL because the README and current-truth entry are not present yet.

- [ ] **Step 3: Create the audit README**

Create `docs/research/2026-07-11-hsconfig-post-hardening-skill-audit/README.md` with:

```markdown
# HSConfig Post-Hardening Skill Audit

Research artifacts are evidence, not operator instructions.

Normal operation starts at `README.md` and `docs/operator/README.md`.

This package records the 2026-07-11 post-hardening audit of HSConfig skill slimness, no-block apply behavior, VisionAI runtime surface correctness, Hearthstone semantic coverage, and representative proof posture.

Use this folder only when auditing why the current active docs keep HSConfig narrow and why the next recommended move is real-deck usage plus targeted defects instead of another broad implementation wave.
```

- [ ] **Step 4: Add the current-truth entry**

In `docs/research/current-truth.md`, add this row at the top of the `Current Active Evidence` table:

```markdown
| `docs/research/2026-07-11-hsconfig-post-hardening-skill-audit/` | Post-hardening skill audit evidence | Keep the current lean HSConfig boundary, correct Presume surface wording, preserve no-block apply behavior, and use real decks for targeted defects instead of another broad architecture wave. |
```

- [ ] **Step 5: Run research schema and docs-path tests**

Run:

```powershell
python -m pytest tests\test_research_audit_schema.py tests\test_docs_active_path.py -q
```

Expected: PASS.

---

### Task 5: Sync Installed Skill And Verify The Whole Contract

**Files:**
- Runtime/generated sync target: `C:\Users\darbo\.codex\skills\hsconfig`
- Verify: no code edits beyond previous tasks.

**Interfaces:**
- Consumes: Updated `.agents/skills/hsconfig` source skill.
- Produces: Installed skill synchronized and full test proof.

- [ ] **Step 1: Check installed skill sync before copying**

Run:

```powershell
python scripts\sync_installed_skill.py --check
```

Expected: FAIL if `.agents/skills/hsconfig` changed and the installed skill is stale.

- [ ] **Step 2: Synchronize installed skill**

Run:

```powershell
python scripts\sync_installed_skill.py
```

Expected: output states that the HSConfig skill was synchronized to `C:\Users\darbo\.codex\skills\hsconfig`.

- [ ] **Step 3: Re-check installed skill sync**

Run:

```powershell
python scripts\sync_installed_skill.py --check
```

Expected:

```text
HSConfig skill is in sync: C:\Users\darbo\.codex\skills\hsconfig
```

- [ ] **Step 4: Validate the retained research audit JSONs**

Run:

```powershell
python C:\Users\darbo\.codex\skills\research\validate_json.py --fields docs\research\2026-07-11-hsconfig-post-hardening-skill-audit\fields.yaml --json docs\research\2026-07-11-hsconfig-post-hardening-skill-audit\results\Skill_Slimness_And_Operator_Usability.json docs\research\2026-07-11-hsconfig-post-hardening-skill-audit\results\Apply_Gate_And_No_Block_Contract.json docs\research\2026-07-11-hsconfig-post-hardening-skill-audit\results\VisionAI_Runtime_Surface_Correctness.json docs\research\2026-07-11-hsconfig-post-hardening-skill-audit\results\Hearthstone_Semantics_And_Wild_Coverage.json docs\research\2026-07-11-hsconfig-post-hardening-skill-audit\results\Representative_Proof_And_Next_Recommendation.json
```

Expected:

```text
Validation passed: 5/5
Average coverage: 100.0%
```

- [ ] **Step 5: Run focused skill, docs, and operator tests**

Run:

```powershell
python -m pytest tests\test_skill_files.py tests\test_operator_guidance.py tests\test_docs_active_path.py tests\test_research_audit_schema.py -q
```

Expected: PASS.

- [ ] **Step 6: Run the no-block and apply-gate suite**

Run:

```powershell
python -m pytest tests\test_property_no_block_apply_gate.py tests\test_apply_gate.py tests\test_universal_wild_no_block_matrix.py -q
```

Expected: PASS.

- [ ] **Step 7: Run the full suite**

Run:

```powershell
python -m pytest -q
```

Expected: PASS. The last verified baseline was `810 passed, 2 skipped`; the exact count may increase by the new tests.

- [ ] **Step 8: Inspect active docs for stale Presume wording**

Run:

```powershell
rg -n "without a current verified first-party|does not currently verify a current first-party|lacks a current verified first-party|Presume/Concede are documented normal outputs" README.md docs\operator .agents\skills\hsconfig
```

Expected: no output.

- [ ] **Step 9: Inspect active docs for normal-path scope drift**

Run:

```powershell
rg -n "parse replays|inspect winrate|analyze runtime logs|promote candidates|tune after games" README.md docs\operator .agents\skills\hsconfig
```

Expected: only boundary statements that say HSConfig does not do those tasks and HSTuner owns them.

- [ ] **Step 10: Review git status**

Run:

```powershell
git status --short --branch
```

Expected: changed docs/tests, the new research README, retained research audit files, and installed skill sync changes if the installed skill is tracked outside this repo by the local environment. No runtime CustomConfig, logs, replays, caches, or private HearthRanger evidence should appear.

---

### Task 6: Commit And Push The Minimal Polish

**Files:**
- Stage all intentional repo changes from Tasks 1-5.

**Interfaces:**
- Consumes: Passing verification from Task 5.
- Produces: One clean commit on the current branch and push to the configured remote branch, unless the execution mode explicitly chooses a PR instead.

- [ ] **Step 1: Stage intentional files only**

Run:

```powershell
git add README.md docs\operator\README.md docs\operator\universal-wild-no-block-contract.md .agents\skills\hsconfig\SKILL.md .agents\skills\hsconfig\references\workflow.md .agents\skills\hsconfig\references\visionai-surfaces.md docs\research\current-truth.md docs\research\2026-07-11-hsconfig-post-hardening-skill-audit docs\superpowers\plans\2026-07-11-hsconfig-minimal-polish-real-deck-readiness.md tests\test_skill_files.py tests\test_operator_guidance.py tests\test_research_audit_schema.py
```

Expected: command succeeds.

- [ ] **Step 2: Review staged diff**

Run:

```powershell
git diff --cached --stat
git diff --cached -- README.md docs\operator\README.md docs\operator\universal-wild-no-block-contract.md .agents\skills\hsconfig\SKILL.md .agents\skills\hsconfig\references\workflow.md .agents\skills\hsconfig\references\visionai-surfaces.md tests\test_skill_files.py tests\test_operator_guidance.py tests\test_research_audit_schema.py
```

Expected: diff only shows the small Presume wording correction, Quick Start, research evidence index, and related tests.

- [ ] **Step 3: Commit**

Run:

```powershell
git commit -m "docs: polish hsconfig runtime surface guidance"
```

Expected: commit succeeds.

- [ ] **Step 4: Push**

Run:

```powershell
git push
```

Expected: branch pushes successfully. If the branch has no upstream, run:

```powershell
git push -u origin codex/hsconfig-lean-contract-hardening
```

- [ ] **Step 5: Final status**

Run:

```powershell
git status --short --branch
```

Expected: clean working tree on the pushed branch.

---

## Self-Review

- Spec coverage: The plan covers the audit recommendation: correct Presume public-doc drift, keep Presume/Concede out of normal output, add a compact operator quick start, index the audit as evidence, sync the installed skill, verify tests, and push.
- Placeholder scan: No task uses unresolved placeholder wording. Each code/doc change includes exact text or exact test code.
- Type and name consistency: Test names, paths, command names, status labels, and runtime file names match the current repo vocabulary.
- Scope check: The plan intentionally avoids HSTuner, replay parsing, winrate analysis, candidate promotion, new dependencies, and runtime behavior changes.

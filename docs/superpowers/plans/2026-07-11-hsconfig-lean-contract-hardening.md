# HSConfig Lean Contract Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make HSConfig's current "any valid deck should produce a load-safe config" promise more provable, while keeping the skill slim. The implementation must harden the no-block apply gate with property-style tests, reduce duplicated active docs, correct Presume/Concede wording, and keep the normal runtime surface unchanged.

**Architecture:** Keep the existing single product path:

`deck input -> hsconfig configure -> reports/operator_summary.json -> VALID_PACKAGE + load_safe_apply -> runtime package`

No new orchestration layer, no replay analysis, no tuning loop, no HSTuner scope. The work is a contract-hardening and documentation-slimming pass around the existing HSConfig generator and gate.

**Tech Stack:** Python, pytest, existing `hsconfig` package, existing `scripts/sync_installed_skill.py`, existing repository docs under `docs/`, installed skill source under `.agents/skills/hsconfig/`.

## Global Constraints

- Keep HSConfig pre-run only. Do not add log/replay parsing, winrate validation, post-run tuning, or HSTuner-style patch apply loops.
- Keep the normal emitted runtime surface limited to:
  - `GlobalValues.json`
  - `Mulligan.json`
  - per-card `<CARDID>.json`
  - `Combo.json` only when exact sequence evidence exists
- Do not emit `Presume.json` or `Concede.json` in the normal path.
- Do not make semantic warnings hard-block runtime package generation.
- Do not weaken structural/runtime safety blocks. Invalid JSON, missing required runtime files, path traversal, undeclared runtime files, or unsupported runtime surfaces must still block.
- Keep docs lean. The canonical operator manual is `docs/operator/README.md`; skill files should point to it instead of duplicating it.
- Commit research artifacts only as evidence, not as operator guidance.
- Do not introduce new dependencies.
- Use TDD: add or adjust tests first, observe failure where practical, then patch implementation/docs.

---

## Task 1: Baseline And Scope Lock

**Objective:** Record the current repo state and make the implementation scope explicit before touching tests or docs.

**Files to inspect:**

- `README.md`
- `docs/operator/README.md`
- `.agents/skills/hsconfig/SKILL.md`
- `.agents/skills/hsconfig/references/workflow.md`
- `.agents/skills/hsconfig/references/visionai-surfaces.md`
- `src/hsconfig/apply_gate.py`
- `src/hsconfig/operator_summary.py`
- `tests/test_apply_gate.py`
- `tests/test_universal_wild_no_block_matrix.py`
- `tests/test_docs_active_path.py`
- `tests/test_skill_files.py`
- `tests/test_skill_sync.py`
- `scripts/sync_installed_skill.py`
- `docs/research/2026-07-11-hsconfig-current-skill-audit/`

**Steps:**

- [ ] Run:

  ```powershell
  git status --short --branch
  python -m pytest tests/test_apply_gate.py tests/test_universal_wild_no_block_matrix.py tests/test_docs_active_path.py tests/test_skill_files.py tests/test_skill_sync.py -q
  python scripts/sync_installed_skill.py --check
  ```

- [ ] Confirm the only expected untracked path before implementation is the latest audit package:

  ```text
  docs/research/2026-07-11-hsconfig-current-skill-audit/
  ```

- [ ] If unrelated user changes exist, do not revert them. Work around them and include them in the final status.

**Expected baseline:**

- The targeted tests pass before changes.
- The installed `hsconfig` skill is in sync before changes.
- The audit package may be untracked and should be handled in Task 5.

---

## Task 2: Add Property-Style No-Block Apply Gate Proof

**Objective:** Convert the broad "any valid deck works" claim into a stronger executable contract. The test should prove that semantic/source-confidence warnings do not block runtime apply when the package is structurally valid, while structural defects still block.

**Primary files:**

- Add `tests/test_property_no_block_apply_gate.py`
- Patch `src/hsconfig/apply_gate.py` only if the new tests expose an actual production bug.

**Test design:**

Add a focused test module that builds temporary package directories and calls the existing apply gate entrypoint. Reuse existing public functions from `src/hsconfig/apply_gate.py`; do not duplicate production gate logic in assertions.

The helper should create a minimal runtime package like:

```text
<tmp>/package/
  CustomConfig/
    DeckName/
      GlobalValues.json
      Mulligan.json
      CARD_001.json
  reports/
    input_manifest.json
    operator_summary.json
```

The helper must support:

- changing `technical_status`
- changing semantic/source confidence labels
- omitting required runtime files
- adding unsupported runtime surfaces
- creating undeclared actual files
- creating declared-but-missing files
- creating nested/path-traversal file names if the existing gate validates them

**Required tests:**

- [ ] `test_valid_package_variants_remain_load_safe_apply`

  Build multiple valid package variants with different non-structural statuses:

  ```python
  semantic_statuses = [
      "SOURCE_BACKED_STRONG",
      "STATIC_SEMANTICS_USABLE",
      "VALID_BUT_NOT_GUIDE_STRONG",
      "NEEDS_MORE_RESEARCH",
      "LOW_CONFIDENCE_BUT_STRUCTURALLY_VALID",
  ]
  ```

  For every case, assert the apply gate returns the repository's allowed/load-safe result and does not produce a hard-block reason.

- [ ] `test_valid_minimal_package_without_cardid_or_combo_is_allowed`

  Prove `GlobalValues.json` + `Mulligan.json` is enough for a valid package. A deck should not be blocked because no per-card file or `Combo.json` was generated.

- [ ] `test_structural_hard_blocks_are_still_blocked`

  Use parametrized cases for:

  - missing `operator_summary.json`
  - missing `input_manifest.json`
  - missing `GlobalValues.json`
  - missing `Mulligan.json`
  - invalid JSON
  - unsupported `Presume.json`
  - unsupported `Concede.json`
  - undeclared runtime file
  - declared runtime file missing from disk

  Assert each case blocks and the reason is specific enough for an operator or worker to understand.

- [ ] `test_summary_runtime_file_drift_blocks`

  Assert drift between `operator_summary.json` generated-file claims and the actual runtime package blocks.

**Implementation guidance:**

- Prefer adding tests only. If all new tests pass against current production code, do not patch `src/hsconfig/apply_gate.py`.
- If production code fails because semantic warnings block apply, patch the gate narrowly so the decision depends on structural validity and runtime-surface safety, not source confidence.
- If production code fails because reason strings are too vague, patch the reason classification only enough to make diagnostics useful.

**Verification:**

```powershell
python -m pytest tests/test_property_no_block_apply_gate.py -q
python -m pytest tests/test_property_no_block_apply_gate.py tests/test_apply_gate.py tests/test_universal_wild_no_block_matrix.py -q
```

---

## Task 3: Correct Presume/Concede Surface Wording

**Objective:** Remove over-strong public-documentation claims. Preserve the actual runtime policy: HSConfig does not emit `Presume.json` or `Concede.json` in the normal path.

**Primary files:**

- `docs/operator/README.md`
- `docs/operator/universal-wild-no-block-contract.md`
- `.agents/skills/hsconfig/SKILL.md`
- `.agents/skills/hsconfig/references/visionai-surfaces.md`
- `tests/test_docs_active_path.py`
- `tests/test_skill_files.py`

**Required wording contract:**

Use wording equivalent to this:

```text
Concede.json is a publicly documented HearthRanger VisionAI surface. Presume.json is treated as a known legacy/public compatibility surface, but this repository does not currently verify a current first-party help-page citation for it. HSConfig does not emit either surface in the normal path.
```

Shorter wording is acceptable in the skill file:

```text
Normal HSConfig output does not emit Presume.json or Concede.json. Concede is publicly documented; Presume is treated as legacy/public compatibility, not as a normal output surface.
```

**Steps:**

- [ ] Add a failing docs test that rejects phrases implying both `Presume.json` and `Concede.json` are first-party documented surfaces.

  Suggested patterns to forbid in active docs and skill files:

  ```text
  Presume.json and Concede.json are HearthRanger-documented
  Presume.json and Concede.json are publicly documented
  Presume/Concede are documented normal outputs
  ```

- [ ] Patch the docs and skill references with the required wording contract.
- [ ] Ensure all normal-path docs still say both files are not emitted by HSConfig.
- [ ] Do not add new Presume/Concede runtime logic.

**Verification:**

```powershell
python -m pytest tests/test_docs_active_path.py tests/test_skill_files.py -q
rg -n "Presume\.json and Concede\.json are|Presume/Concede are documented|documented normal outputs" README.md docs .agents/skills/hsconfig
```

Expected `rg` result: no matches for the forbidden over-strong wording.

---

## Task 4: Slim The Active Skill And Workflow Docs

**Objective:** Make the active skill easier for Codex to use. The detailed policy should live in `docs/operator/README.md`; the skill file and its workflow reference should be short routing instructions.

**Primary files:**

- `.agents/skills/hsconfig/SKILL.md`
- `.agents/skills/hsconfig/references/workflow.md`
- `.agents/skills/hsconfig/references/visionai-surfaces.md`
- `docs/operator/README.md`
- `tests/test_skill_files.py`
- `tests/test_scope_boundaries.py`
- `tests/test_docs_active_path.py`
- `tests/test_skill_sync.py`

**Skill file target shape:**

The active skill should contain only:

- when to use HSConfig
- preferred command: `hsconfig configure`
- where to inspect output: `reports/operator_summary.json`
- apply gate: `technical_status=VALID_PACKAGE` plus `runtime_apply_mode=load_safe_apply`
- hard boundary: pre-run config generation only, no replay/log/winrate tuning
- normal runtime surface list
- note that normal output does not emit `Presume.json` or `Concede.json`
- link to `docs/operator/README.md` as canonical manual
- sync instruction: use `scripts/sync_installed_skill.py --check`

**Workflow reference target shape:**

`references/workflow.md` should be a compact operational sequence:

```text
1. Confirm deck name and deck code.
2. Run hsconfig configure.
3. Inspect reports/operator_summary.json.
4. If technical_status=VALID_PACKAGE and runtime_apply_mode=load_safe_apply, the package is load-safe.
5. If the user asks to apply/copy runtime files, use the repo's normal command/path and preserve structural gate checks.
```

It should not duplicate the full operator policy or large examples.

**Test changes:**

- [ ] Update tests that currently assert long duplicated wording. Replace them with assertions for:

  - canonical operator README link
  - preferred command
  - `VALID_PACKAGE`
  - `load_safe_apply`
  - no replay/log/winrate scope
  - normal runtime surface list
  - no normal Presume/Concede output

- [ ] Add a test that the skill/workflow reference stays below a practical size.

  Suggested thresholds:

  ```python
  assert skill_path.read_text(encoding="utf-8").count("\n") < 120
  assert workflow_path.read_text(encoding="utf-8").count("\n") < 160
  ```

  Adjust thresholds only if current repository style needs a small margin. Do not set them so high that they stop catching duplication.

- [ ] Patch `.agents/skills/hsconfig/` docs to pass the new tests.
- [ ] Run the existing sync script in the mode supported by current `scripts/sync_installed_skill.py`.

  First inspect the script help:

  ```powershell
  python scripts/sync_installed_skill.py --help
  ```

  Then use the current repo-supported command to sync or check. If the script only supports `--check`, do not invent a new CLI. Patch source skill files only and keep the check green.

**Verification:**

```powershell
python -m pytest tests/test_skill_files.py tests/test_scope_boundaries.py tests/test_docs_active_path.py tests/test_skill_sync.py -q
python scripts/sync_installed_skill.py --check
```

---

## Task 5: Handle The Current Research Package As Evidence

**Objective:** Keep the latest `research-deep` audit available as evidence without turning it into another active operator manual.

**Primary files:**

- `docs/research/2026-07-11-hsconfig-current-skill-audit/outline.yaml`
- `docs/research/2026-07-11-hsconfig-current-skill-audit/fields.yaml`
- `docs/research/2026-07-11-hsconfig-current-skill-audit/results/*.json`
- Optional: `docs/research/2026-07-11-hsconfig-current-skill-audit/README.md`
- Optional: existing research index file if one already exists

**Steps:**

- [ ] Validate all new research JSON result files:

  ```powershell
  python C:\Users\darbo\.codex\skills\research\validate_json.py docs/research/2026-07-11-hsconfig-current-skill-audit/results/Current_Skill_Contract_And_No_Block_Gate.json
  python C:\Users\darbo\.codex\skills\research\validate_json.py docs/research/2026-07-11-hsconfig-current-skill-audit/results/VisionAI_Runtime_Surface_Correctness.json
  python C:\Users\darbo\.codex\skills\research\validate_json.py docs/research/2026-07-11-hsconfig-current-skill-audit/results/Hearthstone_Semantics_And_Wild_Mechanic_Coverage.json
  python C:\Users\darbo\.codex\skills\research\validate_json.py docs/research/2026-07-11-hsconfig-current-skill-audit/results/Representative_Deck_Proof_And_Output_Competence.json
  python C:\Users\darbo\.codex\skills\research\validate_json.py docs/research/2026-07-11-hsconfig-current-skill-audit/results/Slimness_Efficiency_And_Next_Recommendation.json
  ```

- [ ] If no README exists for this package, add a short `README.md` with:

  - purpose: evidence for the July 11, 2026 skill audit
  - status: research evidence, not operator guidance
  - key implication: small contract hardening and doc slimming, not a rewrite
  - pointer to `docs/operator/README.md` for active use

- [ ] Do not link this research package from the root README as a normal user path.
- [ ] If there is an existing research index, add one concise entry. If there is no existing index pattern, do not create a new index just for this package.

**Verification:**

```powershell
rg -n "not operator guidance|research evidence|docs/operator/README.md" docs/research/2026-07-11-hsconfig-current-skill-audit
```

---

## Task 6: Full Test And Regression Sweep

**Objective:** Prove the hardened contract did not alter the normal runtime output surface or make the skill harder to use.

**Targeted tests:**

```powershell
python -m pytest tests/test_property_no_block_apply_gate.py tests/test_apply_gate.py tests/test_operator_summary.py tests/test_universal_wild_no_block_matrix.py -q
python -m pytest tests/test_docs_active_path.py tests/test_skill_files.py tests/test_scope_boundaries.py tests/test_cli_help.py tests/test_skill_sync.py -q
python scripts/sync_installed_skill.py --check
```

**Representative end-to-end smoke tests:**

Run the existing representative deck tests, not a new live HearthRanger run. Use whichever test file currently owns the multi-deck matrix. Likely candidates:

```powershell
python -m pytest tests/test_representative_decks.py tests/test_deck_matrix.py -q
```

If one of these files does not exist, run:

```powershell
rg -n "ShadowPriest|CtAPaladin|PirateRogue|BigShaman|Discolock|TreantDruid|ImbueMage|MechPala|Kingslayer|Boarlock|PirateDH|CuteWarrior" tests
```

Then run the actual discovered representative-deck test file(s).

**Full suite:**

```powershell
python -m pytest -q
```

**Expected result:**

- Full suite passes.
- No installed-skill drift.
- No normal-path docs claim Presume is currently verified by a first-party help-page citation.
- No new dependency.
- No runtime output surface expansion.

---

## Task 7: Final Diff Review And Commit

**Objective:** Keep the repository clean and make the final change easy to review.

**Review commands:**

```powershell
git diff --stat
git diff -- tests/test_property_no_block_apply_gate.py src/hsconfig/apply_gate.py docs/operator .agents/skills/hsconfig
git status --short --branch
```

**Review checklist:**

- [ ] The change is contract-hardening and doc-slimming only.
- [ ] No runtime package examples or private configs were added.
- [ ] No raw logs, HDT files, HSReplay files, or local runtime evidence were added.
- [ ] No unrelated HSranger/HSTuner files were edited.
- [ ] The installed skill is in sync or the sync check explains exactly why it is intentionally source-only.
- [ ] The research package is included only as evidence, not normal operator guidance.

**Commit:**

```powershell
git add tests src docs .agents scripts README.md
git status --short
git commit -m "test: harden hsconfig no-block contract"
```

Only include files that actually changed. If `src/` or `scripts/` were not changed, do not stage them.

**Post-commit verification:**

```powershell
git status --short --branch
```

If the user asked to keep GitHub current in the same execution turn, then push:

```powershell
git push origin main
```

Otherwise stop after commit and report the branch status.

---

## Completion Criteria

The implementation is complete when all of these are true:

- A property-style test proves valid packages with low-confidence semantics still get `load_safe_apply`.
- Structural defects still block with specific reasons.
- Active docs and skill files no longer over-claim Presume first-party documentation.
- Skill and workflow references are materially slimmer and point to `docs/operator/README.md`.
- The latest audit research package is either committed as evidence or explicitly removed if the worker decides it is not needed; it must not remain accidentally untracked.
- `python -m pytest -q` passes.
- `python scripts/sync_installed_skill.py --check` passes.
- `git status --short --branch` is clean or contains only intentional user-owned changes clearly reported.


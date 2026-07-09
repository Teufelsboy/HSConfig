# HSConfig Validate-Step And Supplemental Policy Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align the active HSConfig operator path, CLI help, tests, and CuteWarrior supplemental governance with the current post-Kingslayer truth: normal apply follows `prepare -> validate -> apply`, and CuteWarrior remains supplemental until a future matrix review proves a real missing family.

**Architecture:** Keep this as a narrow truth-alignment wave. Do not add new runtime surfaces, deck fixtures, replay parsing, post-run tuning, or source-depth promotion logic. The implementation changes only active operator text, CLI help text, and the tests that encode those public contracts.

**Tech Stack:** Python 3, `pytest`, stdlib `argparse`, JSON operator documents, existing HSConfig CLI/package layout.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig` for `Teufelsboy/HSConfig`.
- HSConfig remains a lean deck-to-HearthRanger pre-run CustomConfig generator.
- Do not add replay parsing, HDT parsing, winrate validation, candidate promotion, or post-run tuning.
- Generated runtime packages stay under `outputs/` and must remain ignored by git.
- Preserve exact deck and CardID identity, full `GlobalValues.json` key profiling, every-card gameplan contract, strict JSON validation, and row-level provenance.
- Do not widen the representative fixture matrix beyond the existing 11 rows.
- Boarlock and Kingslayer remain durable source-informed controls with explicit stop conditions.
- CuteWarrior remains supplemental and must not become a twelfth representative matrix row in this wave.
- `reports/operator_summary.json` remains the single apply gate.

---

## File Structure

- Modify `tests/test_cli_help.py`: encode the correct normal public path with `validate` before `apply`.
- Modify `src/hsconfig/cli_parser.py`: update root CLI epilog from `prepare -> apply` to `prepare -> validate -> apply`.
- Modify `docs/operator/README.md`: update the normal path sentence and numbered operator steps to include explicit validation before opening/applying the package.
- Modify `docs/operator/supplemental-proof-decks.json`: replace the stale CuteWarrior policy label with a future-review policy that no longer references Kingslayer/Boarlock closure.
- Modify `tests/test_matrix_governance.py`: assert the updated CuteWarrior supplemental policy.
- Check `.agents/skills/hsconfig/references/workflow.md`: no change expected unless implementation review finds stale `prepare -> apply` wording there.
- Run `scripts/sync_installed_skill.py --check`: this wave should not require skill sync changes unless active skill files are edited.

## Out Of Scope

- No new deck source research.
- No new source-informed promotion.
- No new `Combo.json`, `Presume.json`, or `Concede.json` policy.
- No black-box CLI proof in this wave. That is the next separate implementation plan after this alignment is green.
- No cleanup of historical plan or research archives.

---

### Task 1: Make The Normal Public Path Include Validate

**Files:**
- Modify: `tests/test_cli_help.py`
- Modify: `src/hsconfig/cli_parser.py`
- Modify: `docs/operator/README.md`

**Interfaces:**
- Consumes: `hsconfig.cli_parser.build_parser() -> argparse.ArgumentParser`
- Consumes: `hsconfig.cli._build_parser() -> argparse.ArgumentParser`
- Produces: root help containing exact normal path string `source-manifest -> draft-source-documents -> research-deck -> prepare -> validate -> apply`
- Produces: operator docs that route users through `hsconfig validate --package ... --json` before `hsconfig apply`

- [ ] **Step 1: Write the failing CLI help contract**

  In `tests/test_cli_help.py`, add a module-level constant below the imports:

  ```python
  NORMAL_PATH = (
      "source-manifest -> draft-source-documents -> research-deck -> "
      "prepare -> validate -> apply"
  )
  ```

  Then replace both existing old-path assertions with:

  ```python
  assert NORMAL_PATH in help_text
  ```

  The affected tests are:

  ```python
  def test_cli_parser_module_builds_same_root_help():
      help_text = build_parser().format_help()

      assert "HSConfig builds lean HearthRanger VisionAI CustomConfig packages" in help_text
      assert "docs/operator/README.md" in help_text
      assert NORMAL_PATH in help_text


  def test_root_help_names_normal_and_expert_paths():
      help_text = _build_parser().format_help()

      assert "Normal path:" in help_text
      assert NORMAL_PATH in help_text
      assert "Expert and legacy path:" in help_text
      assert "build, --claims-json, --cards-json, --plan-reports-dir" in help_text
  ```

- [ ] **Step 2: Run the focused failing test**

  Run:

  ```powershell
  python -m pytest tests\test_cli_help.py::test_cli_parser_module_builds_same_root_help tests\test_cli_help.py::test_root_help_names_normal_and_expert_paths -q
  ```

  Expected before implementation: both tests fail because root CLI help still says `prepare -> apply`.

- [ ] **Step 3: Update the root CLI epilog**

  In `src/hsconfig/cli_parser.py`, replace:

  ```python
              "Normal path: source-manifest -> draft-source-documents -> research-deck -> "
              f"prepare -> apply. {NEGATIVE_SCOPE_TEXT}\n"
  ```

  with:

  ```python
              "Normal path: source-manifest -> draft-source-documents -> research-deck -> "
              f"prepare -> validate -> apply. {NEGATIVE_SCOPE_TEXT}\n"
  ```

- [ ] **Step 4: Update the operator guide path sentence and numbered steps**

  In `docs/operator/README.md`, replace:

  ```markdown
  The normal path is: source-manifest -> draft-source-documents -> research-deck -> prepare -> apply.
  ```

  with:

  ```markdown
  The normal path is: source-manifest -> draft-source-documents -> research-deck -> prepare -> validate -> apply.
  ```

  Then replace the current steps 5-7:

  ```markdown
  5. Run `hsconfig prepare --guide-sources-json ...` to compile and validate the package.
  6. Open `reports/operator_summary.json` first.
  7. Run `hsconfig apply` only when the operator summary allows it.
  ```

  with:

  ```markdown
  5. Run `hsconfig prepare --guide-sources-json ...` to compile the pre-run package and reports.
  6. Run `hsconfig validate --package <package> --json` before handoff or runtime apply.
  7. Open `reports/operator_summary.json` first.
  8. Run `hsconfig apply` only when the operator summary allows it.
  ```

- [ ] **Step 5: Verify the CLI and doc contract**

  Run:

  ```powershell
  python -m pytest tests\test_cli_help.py -q
  rg -n "source-manifest -> draft-source-documents -> research-deck -> prepare -> apply" src docs .agents tests -g "!docs/research/**" -g "!docs/superpowers/plans/**"
  ```

  Expected:

  - `tests/test_cli_help.py` passes.
  - `rg` returns no active non-archived occurrences of the old normal path.

- [ ] **Step 6: Commit Task 1**

  ```powershell
  git add tests\test_cli_help.py src\hsconfig\cli_parser.py docs\operator\README.md
  git commit -m "docs: show validate in normal operator path"
  ```

---

### Task 2: Neutralize The CuteWarrior Supplemental Policy

**Files:**
- Modify: `tests/test_matrix_governance.py`
- Modify: `docs/operator/supplemental-proof-decks.json`

**Interfaces:**
- Consumes: JSON document `docs/operator/supplemental-proof-decks.json`
- Produces: CuteWarrior row with `matrix_policy=not_representative_until_future_matrix_review_proves_missing_family`
- Produces: governance test proving CuteWarrior remains supplemental and not representative

- [ ] **Step 1: Write the failing matrix-governance assertion**

  In `tests/test_matrix_governance.py`, replace:

  ```python
  assert cute["matrix_policy"] == "not_representative_until_kingslayer_boarlock_closure_review"
  ```

  with:

  ```python
  assert (
      cute["matrix_policy"]
      == "not_representative_until_future_matrix_review_proves_missing_family"
  )
  ```

- [ ] **Step 2: Run the focused failing test**

  Run:

  ```powershell
  python -m pytest tests\test_matrix_governance.py::test_supplemental_proof_decks_are_not_representative_matrix_rows -q
  ```

  Expected before implementation: the test fails because the JSON still contains the stale Kingslayer/Boarlock-specific policy.

- [ ] **Step 3: Update CuteWarrior policy JSON**

  In `docs/operator/supplemental-proof-decks.json`, replace:

  ```json
  "matrix_policy": "not_representative_until_kingslayer_boarlock_closure_review",
  ```

  with:

  ```json
  "matrix_policy": "not_representative_until_future_matrix_review_proves_missing_family",
  ```

  Keep these limits unchanged:

  ```json
  "known_limits": [
    "does_not_change_representative_matrix_count",
    "does_not_close_kingslayer_quick_pick_gap",
    "does_not_close_boarlock_fracking_gap"
  ]
  ```

  Rationale: those limits are still true; only the gating label was stale.

- [ ] **Step 4: Verify the supplemental policy**

  Run:

  ```powershell
  python -m pytest tests\test_matrix_governance.py -q
  python -m json.tool docs\operator\supplemental-proof-decks.json > $null
  ```

  Expected:

  - Matrix governance tests pass.
  - JSON syntax validates.
  - Representative matrix remains 11 rows.

- [ ] **Step 5: Commit Task 2**

  ```powershell
  git add tests\test_matrix_governance.py docs\operator\supplemental-proof-decks.json
  git commit -m "docs: neutralize supplemental deck policy"
  ```

---

### Task 3: Cross-Check Active Skill And Operator Surfaces

**Files:**
- Check: `.agents/skills/hsconfig/references/workflow.md`
- Check: `.agents/skills/hsconfig/SKILL.md`
- Check: `docs/operator/README.md`
- Check: `src/hsconfig/cli_parser.py`
- Check: `tests/test_operator_guidance.py`
- Optional modify: `tests/test_operator_guidance.py` only if it asserts the old normal path

**Interfaces:**
- Consumes: installed skill workflow text and active operator docs
- Produces: no stale active guidance saying `prepare -> apply` as the normal chain

- [ ] **Step 1: Scan active guidance for the old chain**

  Run:

  ```powershell
  rg -n "source-manifest -> draft-source-documents -> research-deck -> prepare -> apply|prepare -> apply" src docs .agents tests -g "!docs/research/**" -g "!docs/superpowers/plans/**"
  ```

  Expected:

  - No active root/operator/skill/CLI surface presents `prepare -> apply` as the full normal path.
  - Historical plan files under `docs/superpowers/plans/**` are intentionally excluded.

- [ ] **Step 2: Check operator guidance test expectations**

  Open `tests/test_operator_guidance.py`. If it contains:

  ```python
  "source-manifest -> draft-source-documents -> research-deck -> prepare -> apply"
  ```

  replace it with:

  ```python
  "source-manifest -> draft-source-documents -> research-deck -> prepare -> validate -> apply"
  ```

  If the file only validates lower-level next commands such as `hsconfig validate --package <package> --json`, leave it unchanged.

- [ ] **Step 3: Run active guidance tests**

  Run:

  ```powershell
  python -m pytest tests\test_cli_help.py tests\test_operator_guidance.py tests\test_skill_files.py tests\test_scope_boundaries.py -q
  ```

  Expected: all selected tests pass.

- [ ] **Step 4: Check installed skill sync**

  Run:

  ```powershell
  python scripts\sync_installed_skill.py --check
  ```

  Expected: clean check. If it fails because active skill docs were intentionally edited during this task, run the project-standard sync command shown by the script, then rerun `--check`.

- [ ] **Step 5: Commit Task 3 only if files changed**

  If Task 3 changed any file, run:

  ```powershell
  git add tests\test_operator_guidance.py .agents\skills\hsconfig\references\workflow.md .agents\skills\hsconfig\SKILL.md
  git commit -m "docs: align active hsconfig guidance"
  ```

  If no files changed, do not create an empty commit.

---

### Task 4: Final Verification And Handoff

**Files:**
- Check: full working tree
- Check: plan implementation diffs
- No expected source modifications in this task

**Interfaces:**
- Consumes: Tasks 1-3
- Produces: verified repo state ready for the next separate black-box CLI proof wave

- [ ] **Step 1: Run focused verification**

  Run:

  ```powershell
  python -m pytest tests\test_cli_help.py tests\test_matrix_governance.py tests\test_operator_guidance.py tests\test_skill_files.py tests\test_scope_boundaries.py -q
  ```

  Expected: all selected tests pass.

- [ ] **Step 2: Run package/application smoke tests**

  Run:

  ```powershell
  python -m pytest tests\test_autonomous_guide_workflow_e2e.py tests\test_full_chain_cli_integration.py tests\test_runtime_apply.py tests\test_apply_gate.py -q
  ```

  Expected: all selected tests pass.

- [ ] **Step 3: Run the final active-surface scans**

  Run:

  ```powershell
  rg -n "source-manifest -> draft-source-documents -> research-deck -> prepare -> apply" src docs .agents tests -g "!docs/research/**" -g "!docs/superpowers/plans/**"
  rg -n "not_representative_until_kingslayer_boarlock_closure_review" docs tests src .agents -g "!docs/research/**" -g "!docs/superpowers/plans/**"
  ```

  Expected: both commands return no active matches.

- [ ] **Step 4: Run the full suite if focused verification is green**

  Run:

  ```powershell
  python -m pytest -q
  ```

  Expected: suite passes with the existing project skip count only.

- [ ] **Step 5: Inspect the diff**

  Run:

  ```powershell
  git diff -- docs\operator\README.md docs\operator\supplemental-proof-decks.json src\hsconfig\cli_parser.py tests\test_cli_help.py tests\test_matrix_governance.py tests\test_operator_guidance.py .agents\skills\hsconfig\references\workflow.md .agents\skills\hsconfig\SKILL.md
  git status --short --branch
  ```

  Expected:

  - Only the narrow public-path and supplemental-policy alignment files are changed by this plan.
  - Pre-existing untracked research directories may remain untouched unless the operator explicitly chooses to commit them.

- [ ] **Step 6: Push the branch after all verification passes**

  Run:

  ```powershell
  git push origin HEAD
  ```

  Expected: current branch is pushed.

---

## Next Separate Plan After This Wave

After this plan is green, create a separate black-box CLI proof plan. That plan should execute the public path through subprocess-style tests:

```text
source-manifest -> draft-source-documents -> research-deck -> prepare -> validate -> apply --fake -> apply --from-fake-receipt
```

It should assert fake receipt binding, no runtime writes in fake mode, runtime writes only after receipt-bound apply, and `operator_summary.json` as the single gate. Keep that proof separate so this alignment wave stays small and reviewable.

## Self-Review

- Spec coverage: The plan covers the two confirmed active gaps: missing `validate` in operator/CLI path, and stale CuteWarrior supplemental policy wording.
- Placeholder scan: No task uses TBD/TODO/fill-in placeholders. Optional branches are explicitly bounded by scans and expected outputs.
- Type consistency: The only code interface changed is root parser help text. JSON policy fields retain existing schema shape and update only one string value.
- Scope check: The plan does not add decks, replay parsing, post-run tuning, runtime surfaces, or broad cleanup.

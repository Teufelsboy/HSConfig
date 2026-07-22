# HSConfig Acceptance Projection Final Guardrail Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finalize the brainstorm recommendation by proving the existing HSConfig acceptance and config-quality projection is already the slim correct implementation, and by preventing unnecessary duplicate runtime, apply, source, or gameplay logic.

**Architecture:** This is a verification-first guardrail plan. `hsconfig configure` already writes `<out>/configure_summary.json.acceptance_summary`, `config_quality_summary` already mirrors diagnostic-only quality status, and `reports/operator_summary.json` remains the only normal apply authority; the implementation work is to verify those contracts and stop unless a real regression is found. No HearthRanger gameplay behavior, logs, HSTuner flow, runtime surface, or source promotion rule is changed by this plan.

**Tech Stack:** Python 3, pytest, existing HSConfig CLI, existing Superpowers plan workflow, existing Git/currentness scripts.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig`.
- Start with `git fetch --all --prune --tags`.
- Finish with `git status --short --branch` showing only the branch header and no changed or untracked files.
- Do not inspect gameplay logs.
- Do not use HSTuner.
- Do not add a new runtime surface.
- Do not add a new report file.
- Do not add a new source-strength promotion path.
- Do not make `SOURCE_BACKED_STRONG` an apply gate.
- Do not make source-depth gaps apply-blocking.
- Do not make default-only runtime surfaces silent success.
- Do not add gameplay sequencing logic to HSConfig.
- Do not change HearthRanger runtime execution assumptions.
- `reports/operator_summary.json` remains the only normal apply authority.
- `<out>/configure_summary.json.acceptance_summary` remains an operator projection, not an apply gate.
- `<out>/configure_summary.json.config_quality_summary` remains diagnostic-only and non-blocking.
- If any verification fails, stop this no-change plan and create a separate defect-specific plan before editing production code.

---

## Current State To Preserve

- `src\hsconfig\commands\configure.py` already defines `_build_acceptance_summary(...)`.
- `configure_summary.json["acceptance_summary"]` already includes compact operator fields such as `use_config_now`, `normal_apply_authority`, `runtime_apply_allowed`, `runtime_apply_mode`, `technical_status`, `source_strength`, `source_gaps_apply_blocking`, `default_only_clean`, `config_quality_status`, `config_quality_problem_checks`, `first_missing_source_action`, and `next_report_to_open`.
- `src\hsconfig\config_quality_contract.py` already builds a diagnostic-only `semantic_intent_coverage` rollup.
- `src\hsconfig\contract_spine_sentinel.py` already proves single apply authority, non-authoritative diagnostics, claim-kind surface policy completeness, effect-not-mulligan, no forbidden legacy runtime surfaces, and skill/docs guardrails.
- `.agents\skills\hsconfig\SKILL.md`, `.agents\skills\hsconfig\references\workflow.md`, and `docs\operator\README.md` already route operators through `acceptance_summary` first and `operator_summary.json` as apply authority.

---

## File Structure

- Inspect only: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\commands\configure.py`
  - Owns configure-time `acceptance_summary` projection.
- Inspect only: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\config_quality_contract.py`
  - Owns diagnostic-only config-quality and semantic-intent checks.
- Inspect only: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\contract_spine_sentinel.py`
  - Owns source-contract spine drift diagnostics.
- Inspect only: `C:\Users\darbo\Documents\HSConfig\tests\test_configure_cli.py`
  - Proves `acceptance_summary` is emitted, useful, and outside `operator_summary.json`.
- Inspect only: `C:\Users\darbo\Documents\HSConfig\tests\test_config_quality_contract.py`
  - Proves config quality remains diagnostic-only and catches default-only, trace, semantic, and runtime JSON drift.
- Inspect only: `C:\Users\darbo\Documents\HSConfig\tests\test_contract_spine_sentinel.py`
  - Proves the source-contract spine remains clean.
- Inspect only: `C:\Users\darbo\Documents\HSConfig\.agents\skills\hsconfig\SKILL.md`
  - Repo skill source.
- Inspect only: `C:\Users\darbo\.codex\skills\hsconfig\SKILL.md`
  - Installed skill copy, checked by sync script only.
- Do not modify production files under `src\`.
- Do not modify tests unless a real regression is discovered and a new defect-specific plan is written first.
- Do not modify runtime output, generated package output, logs, or HearthRanger `CustomConfig` files.

---

## Subagent-Driven Execution Shape

- [ ] **Explorer subagent, read-only:** Verify that the existing acceptance projection and config-quality projection match the required contract. Report file paths, function names, and exact fields found.
- [ ] **Reviewer subagent, read-only:** Verify no second apply gate, no HSTuner/log dependency, no default-only silent success, no `SOURCE_BACKED_STRONG` apply gate, and no new runtime surfaces.
- [ ] **Main agent:** Run currentness checks, sync checks, sentinel, tests, final worktree verification, and decide whether the plan is complete without code changes.

No subagent may write files for this plan. If a subagent finds a defect, the main agent stops and writes a separate implementation plan for that exact defect.

---

### Task 1: Preflight Currentness And Clean Base

**Files:**
- Inspect: `C:\Users\darbo\Documents\HSConfig`

**Interfaces:**
- Consumes: Git repository state.
- Produces: Evidence that implementation starts from a current, clean base.

- [ ] **Step 1: Fetch current refs**

```powershell
cd C:\Users\darbo\Documents\HSConfig
git fetch --all --prune --tags
```

Expected:

```text
```

The command should exit with status `0`.

- [ ] **Step 2: Verify currentness**

```powershell
python scripts\check_hsconfig_currentness.py --cwd . --json
```

Expected JSON fields:

```json
{
  "behind_origin_main": 0,
  "dirty": false,
  "clean_for_runtime_work": true
}
```

- [ ] **Step 3: Verify clean worktree**

```powershell
git status --short --branch
```

Expected shape:

```text
## codex/hsconfig-semantic-intent-scoring...origin/codex/hsconfig-semantic-intent-scoring
```

No changed or untracked files should appear below the branch line.

---

### Task 2: Verify Configure Acceptance Projection Exists And Is Local

**Files:**
- Inspect: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\commands\configure.py`
- Test: `C:\Users\darbo\Documents\HSConfig\tests\test_configure_cli.py`

**Interfaces:**
- Consumes: `_build_acceptance_summary(...)`.
- Produces: Evidence that `acceptance_summary` is a configure-output projection only.

- [ ] **Step 1: Locate the helper and required fields**

```powershell
rg -n "def _build_acceptance_summary|use_config_now|normal_apply_authority|runtime_apply_allowed|runtime_apply_mode|source_gaps_apply_blocking|default_only_clean|next_report_to_open" src\hsconfig\commands\configure.py
```

Expected: Matches for all listed field names inside `src\hsconfig\commands\configure.py`.

- [ ] **Step 2: Verify acceptance summary tests**

```powershell
pytest tests\test_configure_cli.py::test_build_acceptance_summary_marks_load_safe_package_usable tests\test_configure_cli.py::test_build_acceptance_summary_surfaces_diagnostics_without_blocking tests\test_configure_cli.py::test_acceptance_summary_helper_stays_configure_local_projection tests\test_configure_cli.py::test_configure_writes_diagnostic_config_quality_summary tests\test_configure_cli.py::test_configure_quality_summary_failure_stays_diagnostic_only -q
```

Expected:

```text
5 passed
```

- [ ] **Step 3: Confirm no production edit is required**

```powershell
git diff -- src\hsconfig\commands\configure.py tests\test_configure_cli.py
```

Expected:

```text
```

The diff must be empty. If it is not empty, stop and inspect why this no-change plan created a modification.

---

### Task 3: Verify Config Quality And Semantic Intent Coverage

**Files:**
- Inspect: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\config_quality_contract.py`
- Test: `C:\Users\darbo\Documents\HSConfig\tests\test_config_quality_contract.py`

**Interfaces:**
- Consumes: `build_config_quality_report(package: str | Path) -> dict[str, Any]`.
- Produces: Evidence that config quality is diagnostic-only and already covers source-to-runtime trace, default-only visibility, semantic default rows, report-only mechanic runtime drift, legacy surfaces, and Darkbishop boundary.

- [ ] **Step 1: Locate diagnostic-only quality fields**

```powershell
rg -n "semantic_intent_coverage|authority.: .diagnostic_only|apply_blocking.: False|runtime_write_performed.: False|default_only_runtime_surfaces|darkbishop_boundary|report_only_mechanic" src\hsconfig\config_quality_contract.py
```

Expected: Matches proving the quality report is diagnostic-only and covers the listed risk families.

- [ ] **Step 2: Run focused config-quality tests**

```powershell
pytest tests\test_config_quality_contract.py -q
```

Expected:

```text
passed
```

The exact count may vary, but there must be no failures.

- [ ] **Step 3: Confirm no source edit is required**

```powershell
git diff -- src\hsconfig\config_quality_contract.py tests\test_config_quality_contract.py
```

Expected:

```text
```

The diff must be empty.

---

### Task 4: Verify Source-Contract Spine And No Second Gate

**Files:**
- Inspect: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\contract_spine_sentinel.py`
- Test: `C:\Users\darbo\Documents\HSConfig\tests\test_contract_spine_sentinel.py`
- Test: `C:\Users\darbo\Documents\HSConfig\tests\test_apply_authority_boundary.py`

**Interfaces:**
- Consumes: `python -m hsconfig.cli contract-spine-sentinel --json`.
- Produces: Evidence that diagnostics cannot become apply authority.

- [ ] **Step 1: Run the contract spine sentinel**

```powershell
python -m hsconfig.cli contract-spine-sentinel --json
```

Expected JSON fields:

```json
{
  "status": "clean",
  "authority": "diagnostic_only",
  "apply_blocking": false,
  "problems": []
}
```

Expected invariant statuses:

```json
{
  "single_apply_authority": "clean",
  "diagnostics_are_non_authoritative": "clean",
  "claim_kind_surface_policy_complete": "clean",
  "effect_not_mulligan": "clean",
  "no_forbidden_legacy_runtime_surfaces": "clean",
  "skill_and_docs_guardrail_ready": "clean"
}
```

- [ ] **Step 2: Run focused boundary tests**

```powershell
pytest tests\test_contract_spine_sentinel.py tests\test_apply_authority_boundary.py -q
```

Expected:

```text
passed
```

The exact count may vary, but there must be no failures.

- [ ] **Step 3: Run contract preflight**

```powershell
python -m hsconfig.cli contract-preflight --json
```

Expected:

```json
{
  "status": "clean"
}
```

If the payload uses `attention` or includes failures, stop and inspect the named checks before editing any file.

---

### Task 5: Verify Skill And Operator Routing

**Files:**
- Inspect: `C:\Users\darbo\Documents\HSConfig\docs\operator\README.md`
- Inspect: `C:\Users\darbo\Documents\HSConfig\.agents\skills\hsconfig\SKILL.md`
- Inspect: `C:\Users\darbo\Documents\HSConfig\.agents\skills\hsconfig\references\workflow.md`
- Inspect: `C:\Users\darbo\.codex\skills\hsconfig\SKILL.md`

**Interfaces:**
- Consumes: `scripts\sync_installed_skill.py --check`.
- Produces: Evidence that the installed skill and repo skill route operators through `acceptance_summary` first while preserving `operator_summary.json` authority.

- [ ] **Step 1: Verify installed skill sync**

```powershell
python scripts\sync_installed_skill.py --check
```

Expected:

```text
HSConfig skill is in sync: C:\Users\darbo\.codex\skills\hsconfig
```

- [ ] **Step 2: Verify routing phrases**

```powershell
rg -n "acceptance_summary|use_config_now|next_report_to_open|operator projection|operator_summary.json.*apply authority|normal apply authority" docs\operator\README.md .agents\skills\hsconfig\SKILL.md .agents\skills\hsconfig\references\workflow.md
```

Expected: Matches in all three files.

- [ ] **Step 3: Run skill and docs tests**

```powershell
pytest tests\test_skill_files.py tests\test_skill_sync.py tests\test_docs_active_path.py -q
```

Expected:

```text
passed
```

The exact count may vary, but there must be no failures.

---

### Task 6: Verify Universal No-Block And Runtime Surface Boundaries

**Files:**
- Test: `C:\Users\darbo\Documents\HSConfig\tests\test_universal_wild_no_block_matrix.py`
- Test: `C:\Users\darbo\Documents\HSConfig\tests\test_no_default_only_runtime_surfaces.py`
- Test: `C:\Users\darbo\Documents\HSConfig\tests\test_source_status_resolver.py`

**Interfaces:**
- Consumes: existing package-building tests and source-status resolver tests.
- Produces: Evidence that valid Wild decks remain load-safe and source/default-only quality signals remain non-blocking diagnostics.

- [ ] **Step 1: Run no-block and source-status tests**

```powershell
pytest tests\test_universal_wild_no_block_matrix.py tests\test_no_default_only_runtime_surfaces.py tests\test_source_status_resolver.py -q
```

Expected:

```text
passed
```

The exact count may vary, but there must be no failures.

- [ ] **Step 2: Verify forbidden runtime surfaces are not normal output**

```powershell
rg -n "Presume.json|Concede.json|CardBehavior.json" src tests docs\operator .agents\skills\hsconfig -g "*.py" -g "*.md"
```

Expected: Matches may exist only in negative-scope, forbidden-surface, diagnostic, or documentation text. There must be no normal package builder path that emits these files.

---

### Task 7: Final No-Change Decision And Clean Worktree

**Files:** none.

**Interfaces:**
- Consumes: all verification from Tasks 1-6.
- Produces: final decision that no implementation change is currently justified.

- [ ] **Step 1: Review the full diff**

```powershell
git diff --check
git diff --name-only
```

Expected:

```text
```

Both commands should produce no file changes. `git diff --check` may produce no output and exit `0`.

- [ ] **Step 2: Verify final currentness**

```powershell
git fetch --all --prune --tags
python scripts\check_hsconfig_currentness.py --cwd . --json
git status --short --branch
```

Expected currentness fields:

```json
{
  "behind_origin_main": 0,
  "dirty": false,
  "clean_for_runtime_work": true
}
```

Expected `git status --short --branch` output:

```text
## codex/hsconfig-semantic-intent-scoring...origin/codex/hsconfig-semantic-intent-scoring
```

- [ ] **Step 3: Record final decision in the implementation report**

Use this exact final decision language:

```text
No production implementation change is currently justified. The recommended slim Acceptance/Quality projection already exists, is diagnostic-only, keeps operator_summary.json as the only apply authority, exposes default-only and source gaps without blocking, and passes the focused guardrails.
```

---

## Self-Review

**Spec coverage:** The plan covers the user requirement to improve only where technically meaningful, stay slim, keep all source/contract logic correct, avoid default-only success, avoid HSTuner/log dependency, and keep the worktree clean.

**Placeholder scan:** The plan contains no implementation placeholders. Every command and expected outcome is explicit. A failing verification is handled by stopping and creating a separate defect-specific plan instead of making ad hoc edits.

**Type consistency:** The named fields match the existing configure acceptance projection and config-quality contracts: `use_config_now`, `normal_apply_authority`, `runtime_apply_allowed`, `runtime_apply_mode`, `source_gaps_apply_blocking`, `default_only_clean`, `config_quality_status`, `config_quality_problem_checks`, `semantic_intent_coverage`, and `next_report_to_open`.

**Risk check:** The main risk is inventing duplicate logic for a problem already solved. This plan explicitly prevents that by requiring read-only verification, no production edits, no new reports, no new gates, and no gameplay simulation inside HSConfig.

## Execution Handoff

Plan complete. Execute with `superpowers:subagent-driven-development` only as a verification-and-guardrail implementation:

1. Explorer subagent verifies acceptance/config-quality source and tests.
2. Reviewer subagent verifies no second gate, no HSTuner/log coupling, no default-only silent success, and no new runtime surfaces.
3. Main agent runs the commands, consolidates evidence, and keeps the worktree clean.

If every check passes, the correct implementation result is no source-code change.

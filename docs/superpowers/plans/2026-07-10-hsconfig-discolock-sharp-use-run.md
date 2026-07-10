# Discolock Sharp HSConfig Use Run Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run the existing HSConfig workflow sharply for Discolock, producing and applying a load-safe HearthRanger pre-run `CustomConfig` package without adding new architecture or broadening HSConfig scope.

**Architecture:** Keep HSConfig as a narrow pre-run generator: deck input becomes source evidence, normalized guide sources, a validated package, a fake apply receipt, then a real runtime apply only when `reports/operator_summary.json` allows `load_safe_apply`. The run is evidence-backed but not over-conservative: semantic warnings, weak guide depth, warning-only mechanics, and combo uncertainty stay visible without blocking a technically valid package.

**Tech Stack:** Python package `hsconfig`, HearthRanger VisionAI `CustomConfig`, Hearthstone deckstring decode, HearthstoneJSON/static semantics, PowerShell on Windows, local repo `C:\Users\darbo\Documents\HSConfig`.

## Global Constraints

- Work only in `C:\Users\darbo\Documents\HSConfig` for `Teufelsboy/HSConfig`.
- Keep HSConfig separate from HSTuner; do not add replay parsing, HDT parsing, winrate validation, candidate promotion, or post-run tuning.
- This plan uses Discolock as the sharp test deck:
  - `deck_name`: `Discolock`
  - `deck_code`: `AAEBAf0GBM4Hj4ID8aEG9qEGDbW5A9XRA9DhA5iSBauSBZXKBteXB4SZB6StB8ayB9a+B9m+B8+/BwAA`
  - `hs_id`: `2740357533`
  - `hdt_deck_id`: `55241397-ac74-4d46-a662-089e5858839c`
- Use `C:\Users\darbo\Desktop\HS` as the expected HearthRanger runtime root, but verify it before writing.
- Generated run artifacts stay under `outputs/` and are ignored by git.
- Do not reuse old HSranger/HSTuner Discolock runtime patches as source authority. Current guide/card/source evidence must drive HSConfig.
- Normal HSConfig output must not emit `Presume.json` or `Concede.json`.
- Runtime apply is allowed only when `operator_summary.json` says `technical_status=VALID_PACKAGE`, `runtime_load_safe=true`, and `runtime_apply_mode=load_safe_apply`.
- `SOURCE_BACKED_STRONG` is a confidence label, not the runtime write gate.
- If a real technical hard block appears, fix the narrow defect; do not weaken `apply_gate.py`.

---

## File Structure

This plan should not modify source code unless a verified technical defect is discovered during the run.

- Create runtime/run artifacts under `C:\Users\darbo\Documents\HSConfig\outputs\discolock-<timestamp>\`.
- Create source manifest output under `outputs\discolock-<timestamp>\01_source_manifest\`.
- Create manual evidence rows under `outputs\discolock-<timestamp>\02_source_evidence\source_evidence.json`.
- Create drafted source documents under `outputs\discolock-<timestamp>\03_source_documents\`.
- Create normalized research under `outputs\discolock-<timestamp>\04_research_deck\`.
- Create final package under `outputs\discolock-<timestamp>\05_package\`.
- Create apply receipts under `outputs\discolock-<timestamp>\06_apply\`.
- Runtime write target is owned by `hsconfig apply` under `C:\Users\darbo\Desktop\HS\CustomConfig\...` and `deck_config.ini`.

---

### Task 1: Preflight And Run Folder

**Files:**
- Create: `C:\Users\darbo\Documents\HSConfig\outputs\discolock-<timestamp>\`
- Read: `C:\Users\darbo\Documents\HSConfig\docs\operator\README.md`
- Read: `C:\Users\darbo\Documents\HSConfig\docs\operator\universal-wild-no-block-contract.md`
- Read: `C:\Users\darbo\.codex\skills\hsconfig\SKILL.md`

**Interfaces:**
- Consumes: Current repo, installed `hsconfig` command, expected runtime root.
- Produces: `$RunRoot`, `$RuntimeRoot`, `$DeckName`, `$DeckCode` variables used by later tasks.

- [ ] **Step 1: Set variables in PowerShell**

```powershell
$Repo = "C:\Users\darbo\Documents\HSConfig"
$RuntimeRoot = "C:\Users\darbo\Desktop\HS"
$DeckName = "Discolock"
$DeckCode = "AAEBAf0GBM4Hj4ID8aEG9qEGDbW5A9XRA9DhA5iSBauSBZXKBteXB4SZB6StB8ayB9a+B9m+B8+/BwAA"
$HsId = "2740357533"
$HdtDeckId = "55241397-ac74-4d46-a662-089e5858839c"
$RunRoot = Join-Path $Repo ("outputs\discolock-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
Set-Location $Repo
New-Item -ItemType Directory -Force -Path $RunRoot | Out-Null
```

- [ ] **Step 2: Verify repo and installed skill state**

Run:

```powershell
git status --short --branch
git rev-parse --short HEAD
git rev-parse --short origin/main
python scripts\sync_installed_skill.py --check
python -m hsconfig --help
```

Expected:

- `git status --short --branch` shows `## main...origin/main`.
- `HEAD` and `origin/main` hashes match.
- Skill sync reports `HSConfig skill is in sync`.
- `python -m hsconfig --help` lists `source-manifest`, `draft-source-documents`, `research-deck`, `prepare`, `validate`, and `apply`.

- [ ] **Step 3: Verify runtime root shape before any write**

Run:

```powershell
Test-Path $RuntimeRoot
Test-Path (Join-Path $RuntimeRoot "CustomConfig")
Get-ChildItem (Join-Path $RuntimeRoot "CustomConfig") -Directory | Select-Object -First 10 Name
```

Expected:

- First two commands return `True`.
- The third command lists HearthRanger config folders.

If the runtime root is missing, stop the runtime-write part of this plan and run package generation only. Do not guess another runtime path.

- [ ] **Step 4: Commit**

No commit is expected for Task 1. Generated `outputs/` content is ignored by git.

---

### Task 2: Source Manifest And Current Evidence Collection

**Files:**
- Create: `outputs\discolock-<timestamp>\01_source_manifest\source_research_manifest.json`
- Create: `outputs\discolock-<timestamp>\02_source_evidence\source_evidence.json`

**Interfaces:**
- Consumes: `$DeckName`, `$DeckCode`, `$RunRoot`.
- Produces: `source_evidence.json` for `draft-source-documents`.

- [ ] **Step 1: Generate the source manifest**

Run:

```powershell
$ManifestOut = Join-Path $RunRoot "01_source_manifest"
New-Item -ItemType Directory -Force -Path $ManifestOut | Out-Null
python -m hsconfig source-manifest `
  --deck-name $DeckName `
  --deck-code $DeckCode `
  --out $ManifestOut `
  --json | Tee-Object (Join-Path $ManifestOut "source_manifest_cli.json")
```

Expected:

- CLI JSON has `"status": "OK"`.
- `source_research_manifest.json` exists.
- Manifest contains deck aliases, card targets, and research questions.

- [ ] **Step 2: Research current source evidence**

Use the manifest to collect short source rows from current sources. Prefer current deck guides, mulligan guides, card text, HearthstoneJSON metadata, and card-specific gameplay discussion.

Evidence must cover these Discolock families where sources allow it:

- overall archetype and gameplan posture
- mulligan keeps and discards
- discard payoff and discard-risk cards
- self-damage or hand-management cards
- target rules for destroy/discard/silence/transform-style effects if present
- combo or sequence claims only when order and timing are explicit
- known bad patterns only when source text names the problem

Do not write vague tier-list blurbs as evidence. Do not infer a discard selector from absent keep text.

- [ ] **Step 3: Write `source_evidence.json` with strict rows**

Create `outputs\discolock-<timestamp>\02_source_evidence\source_evidence.json` with this exact top-level shape:

```json
{
  "evidence_rows": [
    {
      "source_url": "https://source.example/discolock-guide",
      "source_title": "Human Readable Source Title",
      "source_family": "guide",
      "retrieved_at": "2026-07-10T12:00:00Z",
      "archetype": "discard_aggro",
      "claim_kind": "gameplan_posture",
      "card_mentions": [],
      "stance": "discard_aggro_pressure",
      "evidence_text_short": "Short paraphrase of the source claim.",
      "source_confidence": "high"
    }
  ]
}
```

Rules for the final file:

- Replace the example row with real rows only.
- Use `retrieved_at` in ISO format for the current run.
- Use concrete `card_mentions` whenever a claim is about a card.
- Use supported `claim_kind` values: `archetype`, `mulligan_keep`, `mulligan_discard`, `card_role`, `targeting_rule`, `combo_sequence`, `gameplan_posture`, `hero_power_transform`, `mechanic_usage`, `known_bad_pattern`, `tech_slot`, `replacement_option`.
- Include `runtime_block` and `runtime_value` only when the source and documented CardID surface justify it.

- [ ] **Step 4: Commit**

No commit is expected for Task 2. Evidence rows are run artifacts under ignored `outputs/`.

---

### Task 3: Draft And Verify Source Documents

**Files:**
- Read: `outputs\discolock-<timestamp>\02_source_evidence\source_evidence.json`
- Create: `outputs\discolock-<timestamp>\03_source_documents\source_documents.json`
- Create: `outputs\discolock-<timestamp>\03_source_documents\source_document_draft_report.json`

**Interfaces:**
- Consumes: `source_evidence.json`.
- Produces: strict `source_documents.json` for `research-deck` and `prepare`.

- [ ] **Step 1: Draft source documents**

Run:

```powershell
$SourceEvidence = Join-Path $RunRoot "02_source_evidence\source_evidence.json"
$SourceDocsOut = Join-Path $RunRoot "03_source_documents"
New-Item -ItemType Directory -Force -Path $SourceDocsOut | Out-Null
python -m hsconfig draft-source-documents `
  --deck-name $DeckName `
  --deck-code $DeckCode `
  --source-evidence-json $SourceEvidence `
  --out $SourceDocsOut `
  --json | Tee-Object (Join-Path $SourceDocsOut "draft_source_documents_cli.json")
```

Expected:

- CLI JSON has `"status": "OK"`.
- `source_documents.json` exists.
- `source_document_draft_report.json` exists.

- [ ] **Step 2: Inspect unresolved mentions and dropped claims**

Run:

```powershell
$DraftReport = Get-Content -Raw (Join-Path $SourceDocsOut "source_document_draft_report.json") | ConvertFrom-Json
$DraftReport.draft_summary
$DraftReport.unresolved_mentions
```

Expected:

- `unresolved_mentions` is empty for source rows intended to support strong card claims.
- If a row is dropped, fix `card_mentions` in `source_evidence.json` and rerun Step 1.
- If a source claim is inherently broad and cannot resolve to a card, keep it only if it is deck-level posture or archetype evidence.

- [ ] **Step 3: Commit**

No commit is expected for Task 3. Drafted documents are run artifacts under ignored `outputs/`.

---

### Task 4: Normalize Research Deck Inputs

**Files:**
- Read: `outputs\discolock-<timestamp>\03_source_documents\source_documents.json`
- Create: `outputs\discolock-<timestamp>\04_research_deck\guide_sources.json`
- Create: `outputs\discolock-<timestamp>\04_research_deck\deck_fingerprint.json`
- Create: `outputs\discolock-<timestamp>\04_research_deck\candidate_archetypes.json`
- Create: `outputs\discolock-<timestamp>\04_research_deck\source_evidence_verification_report.json`

**Interfaces:**
- Consumes: strict source documents.
- Produces: normalized `guide_sources.json` for package preparation.

- [ ] **Step 1: Run `research-deck` with source documents**

Run:

```powershell
$ResearchOut = Join-Path $RunRoot "04_research_deck"
New-Item -ItemType Directory -Force -Path $ResearchOut | Out-Null
python -m hsconfig research-deck `
  --deck-name $DeckName `
  --deck-code $DeckCode `
  --source-documents-json (Join-Path $SourceDocsOut "source_documents.json") `
  --out $ResearchOut `
  --json | Tee-Object (Join-Path $ResearchOut "research_deck_cli.json")
```

Expected:

- CLI JSON has `"status": "OK"`.
- `guide_sources.json` exists.
- `source_evidence_verification_report.json` exists.

- [ ] **Step 2: Inspect source depth and verification status**

Run:

```powershell
$ResearchCli = Get-Content -Raw (Join-Path $ResearchOut "research_deck_cli.json") | ConvertFrom-Json
$Verification = Get-Content -Raw (Join-Path $ResearchOut "source_evidence_verification_report.json") | ConvertFrom-Json
$ResearchCli.source_depth_status
$Verification.status
$Verification.warnings
```

Expected:

- Prefer `source_depth_status=source_backed`.
- `source_depth_status=static_semantics_only` is allowed but should be reported as a weaker run.
- `warnings` should be empty for rows meant to support strong guide-backed claims.

- [ ] **Step 3: Commit**

No commit is expected for Task 4. Normalized research is a run artifact under ignored `outputs/`.

---

### Task 5: Prepare The Discolock Package

**Files:**
- Read: `outputs\discolock-<timestamp>\04_research_deck\guide_sources.json`
- Read: `outputs\discolock-<timestamp>\03_source_documents\source_documents.json`
- Create: `outputs\discolock-<timestamp>\05_package\CustomConfig\...`
- Create: `outputs\discolock-<timestamp>\05_package\reports\operator_summary.json`

**Interfaces:**
- Consumes: normalized guide sources and runtime root.
- Produces: validated package candidate.

- [ ] **Step 1: Prepare the package**

Run:

```powershell
$PackageOut = Join-Path $RunRoot "05_package"
New-Item -ItemType Directory -Force -Path $PackageOut | Out-Null
python -m hsconfig prepare `
  --deck-name $DeckName `
  --deck-code $DeckCode `
  --runtime-root $RuntimeRoot `
  --guide-sources-json (Join-Path $ResearchOut "guide_sources.json") `
  --source-documents-json (Join-Path $SourceDocsOut "source_documents.json") `
  --out $PackageOut `
  --json | Tee-Object (Join-Path $PackageOut "prepare_cli.json")
```

Expected:

- CLI JSON has `"status": "passed"`.
- `CustomConfig` folder exists inside `$PackageOut`.
- `reports\operator_summary.json` exists.

- [ ] **Step 2: Check the operator gate**

Run:

```powershell
$Operator = Get-Content -Raw (Join-Path $PackageOut "reports\operator_summary.json") | ConvertFrom-Json
$Operator.technical_status
$Operator.runtime_load_safe
$Operator.runtime_apply_mode
$Operator.runtime_apply_allowed
$Operator.next_action
$Operator.apply_policy
$Operator.no_block_failure_mode_summary.overall
$Operator.no_block_failure_mode_summary.categories.technical_hard_block
```

Expected:

- `technical_status` is `VALID_PACKAGE`.
- `runtime_load_safe` is `True`.
- `runtime_apply_mode` is `load_safe_apply`.
- `runtime_apply_allowed` is `True`.
- `technical_hard_block` is empty.

If these expectations fail, stop before runtime apply and inspect `primary_blockers`. Fix only the narrow package defect.

- [ ] **Step 3: Check runtime file shape**

Run:

```powershell
$DeckDirs = Get-ChildItem (Join-Path $PackageOut "CustomConfig") -Directory
$DeckDir = $DeckDirs[0].FullName
Get-ChildItem $DeckDir -File | Select-Object Name
Test-Path (Join-Path $DeckDir "GlobalValues.json")
Test-Path (Join-Path $DeckDir "Mulligan.json")
Test-Path (Join-Path $DeckDir "Presume.json")
Test-Path (Join-Path $DeckDir "Concede.json")
```

Expected:

- Exactly one deck runtime directory exists.
- `GlobalValues.json` returns `True`.
- `Mulligan.json` returns `True`.
- `Presume.json` returns `False`.
- `Concede.json` returns `False`.
- Per-card `<CARDID>.json` files are present for deck cards when identity is known.
- `Combo.json` may exist only if exact sequence evidence was available.

- [ ] **Step 4: Commit**

No commit is expected for Task 5 unless a code defect was fixed. Generated packages are ignored by git.

---

### Task 6: Validate And Fake Apply

**Files:**
- Read: `outputs\discolock-<timestamp>\05_package\`
- Create: `outputs\discolock-<timestamp>\06_apply\validate_cli.json`
- Create: `outputs\discolock-<timestamp>\06_apply\fake_apply_cli.json`

**Interfaces:**
- Consumes: prepared package.
- Produces: receipt-bound fake apply proof.

- [ ] **Step 1: Validate the package**

Run:

```powershell
$ApplyOut = Join-Path $RunRoot "06_apply"
New-Item -ItemType Directory -Force -Path $ApplyOut | Out-Null
python -m hsconfig validate `
  --package $PackageOut `
  --json | Tee-Object (Join-Path $ApplyOut "validate_cli.json")
```

Expected:

- CLI JSON has `"status": "passed"`.

- [ ] **Step 2: Run fake apply**

Run:

```powershell
python -m hsconfig apply `
  --package $PackageOut `
  --runtime-root $RuntimeRoot `
  --fake `
  --json | Tee-Object (Join-Path $ApplyOut "fake_apply_cli.json")
```

Expected:

- CLI JSON reports fake apply success.
- No HearthRanger runtime files are mutated by this step.
- Fake receipt references the same package path and runtime root.

- [ ] **Step 3: Commit**

No commit is expected for Task 6. Fake apply receipts are run artifacts under ignored `outputs/`.

---

### Task 7: Runtime Apply And User Handoff

**Files:**
- Read: `outputs\discolock-<timestamp>\05_package\reports\operator_summary.json`
- Create: `outputs\discolock-<timestamp>\06_apply\apply_cli.json`
- Runtime write: `C:\Users\darbo\Desktop\HS\CustomConfig\...`
- Runtime write: `C:\Users\darbo\Desktop\HS\CustomConfig\deck_config.ini`

**Interfaces:**
- Consumes: validated package and fake apply proof.
- Produces: live HearthRanger CustomConfig mapping for Discolock.

- [ ] **Step 1: Re-check gate immediately before real apply**

Run:

```powershell
$Operator = Get-Content -Raw (Join-Path $PackageOut "reports\operator_summary.json") | ConvertFrom-Json
if ($Operator.technical_status -ne "VALID_PACKAGE") { throw "Not a valid package" }
if ($Operator.runtime_load_safe -ne $true) { throw "Package is not runtime load-safe" }
if ($Operator.runtime_apply_mode -ne "load_safe_apply") { throw "Package is not load_safe_apply" }
if ($Operator.runtime_apply_allowed -ne $true) { throw "Runtime apply is not allowed" }
```

Expected:

- No exception is thrown.

- [ ] **Step 2: Apply the package to HearthRanger runtime**

Run:

```powershell
python -m hsconfig apply `
  --package $PackageOut `
  --runtime-root $RuntimeRoot `
  --json | Tee-Object (Join-Path $ApplyOut "apply_cli.json")
```

Expected:

- CLI JSON reports runtime apply success.
- HearthRanger runtime contains a Discolock mapping in `deck_config.ini`.
- The runtime deck folder contains at least `GlobalValues.json` and `Mulligan.json`.

- [ ] **Step 3: Produce the user handoff summary**

Report these exact fields to the user:

- run root path
- package path
- runtime root path
- `technical_status`
- `semantic_status`
- `runtime_apply_mode`
- `next_action`
- `config_usefulness.status`
- first `no_block_failure_mode_summary.first_non_blocking_followup`, if any
- whether `Combo.json` was emitted
- explicit instruction: restart or reload HearthRanger and run fresh Discolock games

- [ ] **Step 4: Commit**

No commit is expected for Task 7 unless the executor fixed code or docs. Runtime writes are not git artifacts.

---

### Task 8: Narrow Defect Path Only If The Sharp Run Fails

**Files:**
- Modify only the smallest affected source/test files if a verified defect appears.
- Likely source files, depending on the defect:
  - `src\hsconfig\apply_gate.py`
  - `src\hsconfig\operator_summary.py`
  - `src\hsconfig\compile_globalvalues.py`
  - `src\hsconfig\compile_mulligan.py`
  - `src\hsconfig\compile_cardid.py`
  - `src\hsconfig\compile_combo.py`
  - `src\hsconfig\mechanic_support.py`
  - `src\hsconfig\mechanic_drift.py`
- Add or modify the matching focused test under `tests\`.

**Interfaces:**
- Consumes: failing command output from Tasks 5-7.
- Produces: one minimal fix and a regression test.

- [ ] **Step 1: Classify the failure**

Use this classification:

- `technical_hard_block`: package cannot load safely; fix required before apply.
- `source_depth_warning`: warning only; do not block apply.
- `warning_only_mechanic`: warning only; do not block apply.
- `future_mechanic_drift`: warning only; do not block apply.
- `guide_strength_gap`: warning only for runtime apply; do not call it strong.
- `combo_uncertainty`: suppress `Combo.json` or keep report visible; do not block base package.
- `runtime_evidence_only_tuning`: outside HSConfig; do not implement HSTuner behavior here.

- [ ] **Step 2: Write the smallest failing regression test**

Run a test that reproduces the exact failure. Example for an apply-gate regression:

```powershell
python -m pytest tests\test_apply_gate.py -q
```

Expected before the fix:

- The new or existing focused test fails for the exact technical reason.

- [ ] **Step 3: Implement only the minimal fix**

Rules:

- Do not add replay/HDT/winrate/candidate-promotion code.
- Do not broaden normal output to `Presume.json` or `Concede.json`.
- Do not weaken `apply_gate.py` to allow invalid packages.
- Do not add a representative deck unless the failure proves a new family that no existing row can exercise.

- [ ] **Step 4: Verify the focused suite**

Run:

```powershell
python -m pytest tests\test_universal_wild_no_block_matrix.py tests\test_apply_gate.py tests\test_mechanic_support.py tests\test_mechanic_drift.py tests\test_operator_summary.py tests\test_docs_active_path.py tests\test_skill_files.py -q
python scripts\sync_installed_skill.py --check
```

Expected:

- Focused tests pass.
- Installed skill sync passes.

- [ ] **Step 5: Commit only if code or docs changed**

Run:

```powershell
git status --short
git add <changed-source-and-test-files>
git commit -m "fix: keep discolock sharp run load-safe"
```

Expected:

- Commit includes only the narrow fix and its test.
- Generated `outputs/` artifacts remain untracked.

---

## Final Verification

Run after Task 7, or after Task 8 if a fix was required:

```powershell
git status --short --branch
python C:\Users\darbo\.codex\skills\research\validate_json.py -f docs\research\2026-07-10-hsconfig-any-deck-no-block-skill-audit-v6\fields.yaml -d docs\research\2026-07-10-hsconfig-any-deck-no-block-skill-audit-v6\results
python scripts\sync_installed_skill.py --check
python -m pytest tests\test_universal_wild_no_block_matrix.py tests\test_apply_gate.py tests\test_mechanic_support.py tests\test_mechanic_drift.py tests\test_operator_summary.py tests\test_docs_active_path.py tests\test_skill_files.py -q
```

Expected:

- Git is clean except ignored `outputs/`.
- Research validation reports `Validation passed: 5/5`.
- Installed skill sync passes.
- Focused tests pass.

## Success Criteria

- Discolock produces a package with `technical_status=VALID_PACKAGE`.
- `runtime_load_safe=true`.
- `runtime_apply_mode=load_safe_apply`.
- `GlobalValues.json` exists.
- `Mulligan.json` exists.
- Per-card `<CARDID>.json` files exist for known deck cards.
- `Presume.json` and `Concede.json` are absent.
- `Combo.json` exists only when exact sequence evidence supports it.
- Real runtime apply succeeds when the gate allows it.
- User receives a clear handoff to reload HearthRanger and play fresh games.

## Out Of Scope

- Replay parsing.
- HDT parsing.
- Winrate review.
- Candidate promotion.
- Post-run tuning.
- Broad repo cleanup.
- Expanding `Presume.json` or `Concede.json` into the normal path.

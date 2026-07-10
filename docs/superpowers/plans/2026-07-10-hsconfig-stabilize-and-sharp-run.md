# HSConfig Stabilize And Sharp Run Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the current HSConfig no-block/mechanic-visibility work cleanly, prove the narrow skill path with one fresh deck run, and avoid adding broad new architecture unless a real failure appears.

**Architecture:** HSConfig stays a pre-run HearthRanger VisionAI CustomConfig generator. The implementation path preserves the current single gate (`reports/operator_summary.json`), keeps warning-only mechanics non-blocking, and uses a real generated package as the product proof instead of adding more speculative framework code.

**Tech Stack:** Python package in `src/hsconfig`, pytest tests in `tests`, Markdown operator docs, local installed skill sync via `scripts/sync_installed_skill.py`, Git branch `codex/hsconfig-mechanic-lowering-parity`.

## Global Constraints

- Work only in `C:\Users\darbo\Documents\HSConfig` for `Teufelsboy/HSConfig`.
- Keep HSConfig separate from HSTuner: no replay parsing, HDT parsing, winrate validation, candidate promotion, or post-run tuning.
- Do not add new dependencies.
- Do not widen normal runtime output beyond `GlobalValues.json`, `Mulligan.json`, per-card `<CARDID>.json`, and exact-evidence `Combo.json`.
- Keep `Concede.json` and `Presume.json` outside the normal HSConfig output path.
- Preserve exact deck and CardID identity, full `GlobalValues.json` key profiling, every-card gameplan coverage, strict JSON validation, and row-level provenance.
- Treat warning-only mechanics and source-depth gaps as visible non-blocking guidance. Only `technical_hard_block` stops apply.
- Do not commit generated runtime packages under `outputs/`; they are ignored runtime artifacts.

---

## File Structure

- `docs/superpowers/plans/2026-07-10-hsconfig-mechanic-lowering-parity-wave.md`: existing prior implementation plan to inspect, not rewrite unless a stale claim is found.
- `docs/operator/README.md`: operator entrypoint; only adjust if the sharp run reveals wording that contradicts current behavior.
- `docs/operator/universal-wild-no-block-contract.md`: no-block contract; only adjust if a real gate mismatch is discovered.
- `.agents/skills/hsconfig/SKILL.md`: source skill; must remain synced to `C:\Users\darbo\.codex\skills\hsconfig\SKILL.md`.
- `src/hsconfig/mechanic_support.py`: mechanic visibility registry; only touch if a sharp run or drift probe proves a missing current mechanic.
- `src/hsconfig/mechanic_drift.py`: current/future mechanic drift detection; only touch with a failing test.
- `tests/test_*`: use existing targeted tests first; add tests only for a real failure.
- `outputs/<deck>/`: generated proof package from the sharp run; ignored by git and not committed.

---

### Task 1: Baseline And Diff Review

**Files:**
- Inspect: `C:\Users\darbo\Documents\HSConfig\docs\superpowers\plans\2026-07-10-hsconfig-mechanic-lowering-parity-wave.md`
- Inspect: current git diff across modified repo files
- No code changes expected

**Interfaces:**
- Consumes: existing uncommitted branch state on `codex/hsconfig-mechanic-lowering-parity`.
- Produces: clear decision whether the current branch is ready for verification or contains stale/unrelated changes.

- [ ] **Step 1: Confirm workspace and branch**

Run:

```powershell
Set-Location C:\Users\darbo\Documents\HSConfig
git status --short --branch
```

Expected: branch is `codex/hsconfig-mechanic-lowering-parity`; modified files match HSConfig mechanic/no-block work and do not include generated runtime outputs.

- [ ] **Step 2: Review the current diff summary**

Run:

```powershell
git diff --stat
git diff -- .agents/skills/hsconfig/SKILL.md docs/operator/README.md docs/operator/universal-wild-no-block-contract.md src/hsconfig/mechanic_support.py src/hsconfig/mechanic_drift.py tests/test_mechanic_support.py tests/test_mechanic_drift.py tests/test_universal_wild_no_block_matrix.py
```

Expected: changes reinforce the narrow HSConfig contract; no HSTuner, replay, HDT, winrate, candidate-promotion, or post-run tuning scope appears.

- [ ] **Step 3: Scan for forbidden scope creep**

Run:

```powershell
rg "Power\.log|HDT|hdtreplay|winrate|candidate promotion|post-run|replay parsing|runtime log" src docs/operator .agents/skills/hsconfig tests
```

Expected: either no hits or hits only in explicit “not HSConfig scope” wording.

- [ ] **Step 4: Decide if cleanup is needed**

If generated runtime artifacts are staged or tracked, remove them from git tracking before continuing:

```powershell
git status --short
```

Expected: no `outputs/`, `Power.log`, `.hdtreplay`, `.hsreplay`, HearthRanger logs, or private runtime evidence appear as tracked changes.

---

### Task 2: Re-Verify No-Block And Mechanic Contract

**Files:**
- Test: `tests/test_universal_wild_no_block_matrix.py`
- Test: `tests/test_mechanic_support.py`
- Test: `tests/test_mechanic_drift.py`
- Test: `tests/test_apply_gate.py`
- Test: `tests/test_scope_boundaries.py`
- Test: `tests/test_skill_sync.py`
- Test: `tests/test_static_semantics.py`
- Test: `tests/test_semantic_enrichment.py`
- Modify only if a test fails and the failure proves a real mismatch

**Interfaces:**
- Consumes: current source and docs.
- Produces: passing focused verification for the recommendation baseline.

- [ ] **Step 1: Validate the active research package**

Run:

```powershell
$fields='docs\research\2026-07-10-hsconfig-any-deck-no-block-skill-audit-v6\fields.yaml'
Get-ChildItem 'docs\research\2026-07-10-hsconfig-any-deck-no-block-skill-audit-v6\results\*.json' | ForEach-Object {
  python 'C:\Users\darbo\.codex\skills\research\validate_json.py' -f $fields -j $_.FullName
}
```

Expected: each result file reports `[PASS]` and `Coverage: 100.0%`.

- [ ] **Step 2: Verify installed skill sync**

Run:

```powershell
python scripts/sync_installed_skill.py --check
```

Expected: `HSConfig skill is in sync: C:\Users\darbo\.codex\skills\hsconfig`.

- [ ] **Step 3: Run the focused no-block/mechanic suite**

Run:

```powershell
python -m pytest tests/test_universal_wild_no_block_matrix.py tests/test_mechanic_support.py tests/test_mechanic_drift.py tests/test_apply_gate.py tests/test_scope_boundaries.py tests/test_skill_sync.py tests/test_static_semantics.py tests/test_semantic_enrichment.py -q
```

Expected: all tests pass. Current baseline expectation is `85 passed`.

- [ ] **Step 4: Run the wider smoke suite if the focused suite passes**

Run:

```powershell
python -m pytest tests/test_operator_guidance.py tests/test_docs_active_path.py tests/test_runtime_apply.py tests/test_full_chain_cli_integration.py tests/test_prepare_cli.py -q
```

Expected: all selected tests pass. If a test fails, fix only the failing contract mismatch and rerun the exact failing test before rerunning the batch.

---

### Task 3: Sharp Deck Run Proof

**Files:**
- Runtime output only: `outputs/<deck-slug>/`
- Inspect: generated `reports/operator_summary.json`
- Inspect: generated `CustomConfig/<deck-folder>/GlobalValues.json`
- Inspect: generated `CustomConfig/<deck-folder>/Mulligan.json`
- Inspect: generated per-card `<CARDID>.json`
- Do not commit generated output

**Interfaces:**
- Consumes: verified HSConfig CLI and installed skill.
- Produces: one real deck package proving the product path still works after the mechanic/no-block cleanup.

- [ ] **Step 1: Choose the proof deck**

Use one fresh deck that is not already the main active runtime target. Recommended proof deck from the provided set:

```text
Deckname: Discolock
Deckcode: AAEBAf0GBM4Hj4ID8aEG9qEGDbW5A9XRA9DhA5iSBauSBZXKBteXB4SZB6StB8ayB9a+B9m+B8+/BwAA
HSid: 2740357533
HDT-DeckId: 55241397-ac74-4d46-a662-089e5858839c
```

Reason: Discolock exercises discard and hand-resource semantics without pulling HSConfig into post-run analysis.

- [ ] **Step 2: Generate the source manifest**

Run:

```powershell
python -m hsconfig.cli source-manifest `
  --deck-name Discolock `
  --deck-code "AAEBAf0GBM4Hj4ID8aEG9qEGDbW5A9XRA9DhA5iSBauSBZXKBteXB4SZB6StB8ayB9a+B9m+B8+/BwAA" `
  --hs-id 2740357533 `
  --hdt-deck-id 55241397-ac74-4d46-a662-089e5858839c `
  --output-dir outputs\discolock-sharp-run `
  --json
```

Expected: `outputs\discolock-sharp-run\source_manifest.json` exists and card targets resolve.

- [ ] **Step 3: Draft source documents from existing source evidence path**

If current workflow already has a prepared evidence-row input format, use that format and run:

```powershell
python -m hsconfig.cli draft-source-documents `
  --source-manifest outputs\discolock-sharp-run\source_manifest.json `
  --source-evidence-json outputs\discolock-sharp-run\source_evidence.json `
  --output-dir outputs\discolock-sharp-run `
  --json
```

Expected: `outputs\discolock-sharp-run\source_documents.json` exists and unresolved card mentions are reported explicitly. If no evidence rows are available for this proof, create a small local evidence file with card-text/static-semantics evidence only, not invented guide claims.

- [ ] **Step 4: Normalize guide sources**

Run:

```powershell
python -m hsconfig.cli research-deck `
  --deck-name Discolock `
  --deck-code "AAEBAf0GBM4Hj4ID8aEG9qEGDbW5A9XRA9DhA5iSBauSBZXKBteXB4SZB6StB8ayB9a+B9m+B8+/BwAA" `
  --source-documents-json outputs\discolock-sharp-run\source_documents.json `
  --output-dir outputs\discolock-sharp-run `
  --json
```

Expected: `outputs\discolock-sharp-run\guide_sources.json`, `deck_fingerprint.json`, and identity reports exist.

- [ ] **Step 5: Prepare the runtime package**

Run:

```powershell
python -m hsconfig.cli prepare `
  --deck-name Discolock `
  --deck-code "AAEBAf0GBM4Hj4ID8aEG9qEGDbW5A9XRA9DhA5iSBauSBZXKBteXB4SZB6StB8ayB9a+B9m+B8+/BwAA" `
  --guide-sources-json outputs\discolock-sharp-run\guide_sources.json `
  --output-dir outputs\discolock-sharp-run `
  --json
```

Expected: `outputs\discolock-sharp-run\reports\operator_summary.json` reports `technical_status=VALID_PACKAGE`, `runtime_load_safe=true`, and `runtime_apply_mode=load_safe_apply`.

- [ ] **Step 6: Validate the package**

Run:

```powershell
python -m hsconfig.cli validate --package outputs\discolock-sharp-run --json
```

Expected: validation succeeds; required runtime files include `GlobalValues.json` and `Mulligan.json`; normal output does not include `Presume.json` or `Concede.json`.

- [ ] **Step 7: Inspect the operator summary**

Run:

```powershell
Get-Content -Raw outputs\discolock-sharp-run\reports\operator_summary.json | python -m json.tool
```

Expected:

```text
technical_status: VALID_PACKAGE
runtime_load_safe: true
runtime_apply_mode: load_safe_apply
no_block_failure_mode_summary.categories.technical_hard_block: []
```

Warnings are acceptable if they are source-depth, config-richness, warning-only mechanic, or static-semantics limits.

---

### Task 4: Drift Watch Without Scope Creep

**Files:**
- Modify only if missing current mechanic coverage is proven:
  - `src/hsconfig/mechanic_support.py`
  - `src/hsconfig/mechanic_drift.py`
  - `src/hsconfig/static_semantics.py`
  - `tests/test_mechanic_support.py`
  - `tests/test_mechanic_drift.py`
  - `tests/test_static_semantic_micro_fixtures.py`
- No change expected if current probe matches the audit baseline

**Interfaces:**
- Consumes: live HearthstoneJSON current card data.
- Produces: either no-op confirmation or a minimal warning-only registration for a proven new mechanic.

- [ ] **Step 1: Run live keyword probe**

Run:

```powershell
python -c @'
import json, re, urllib.request
from collections import Counter
url='https://api.hearthstonejson.com/v1/latest/enUS/cards.collectible.json'
req=urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0 HSConfig drift watch'})
with urllib.request.urlopen(req, timeout=30) as r:
    cards=json.load(r)
keys=['BATTLECRY','DEATHRATTLE','DISCOVER','DREDGE','TRADEABLE','OVERLOAD','FREEZE','LIFESTEAL','TAUNT','RUSH','CHARGE','SECRET','CHOOSE_ONE','KINDRED','TOURIST','STARSHIP','IMBUE','REWIND','HERALD','SHATTER']
mechanics=Counter(); texts=Counter()
for c in cards:
    blob=' '.join(str(c.get(k,'')) for k in ('text','name'))
    m=set(c.get('mechanics') or []) | set(c.get('referencedTags') or [])
    for key in keys:
        if key in m: mechanics[key]+=1
        if re.search(r'\b'+re.escape(key.replace('_',' '))+r'\b', blob, re.I): texts[key]+=1
print(json.dumps({'collectible_count':len(cards),'mechanics_hits':dict(mechanics),'text_hits':dict(texts)}, indent=2, sort_keys=True))
'@
```

Expected: known mechanics appear; no unregistered new mechanic requires immediate support.

- [ ] **Step 2: If a new mechanic appears, add it warning-only first**

Only if the probe or a failing test proves a new current mechanic, add a minimal registry row:

```python
"new_mechanic_slug": {
    "support_level": "warning_only",
    "normal_path_surfaces": ["report-only"],
    "risk": "current_or_future_mechanic_has_no_documented_hsconfig_lowering",
},
```

Expected: no new runtime surface is introduced until documented lowering exists.

- [ ] **Step 3: Add a focused test for the new mechanic only when needed**

If Step 2 happened, add an assertion to `tests/test_mechanic_drift.py` proving the new mechanic is named and non-blocking:

```python
def test_mechanic_drift_keeps_new_current_mechanic_warning_only():
    report = build_mechanic_drift_report(
        [
            {
                "id": "NEW_001",
                "name": "New Mechanic Example",
                "text": "<b>New Mechanic:</b> Example text.",
                "mechanics": [],
                "referencedTags": [],
                "type": "SPELL",
            }
        ]
    )
    assert report["support_by_mechanic"]["new_mechanic_slug"]["support_level"] == "warning_only"
```

Run:

```powershell
python -m pytest tests/test_mechanic_drift.py::test_mechanic_drift_keeps_new_current_mechanic_warning_only -q
```

Expected: pass.

---

### Task 5: Commit And Push Clean State

**Files:**
- Stage: all intended source, docs, tests, and plan files
- Do not stage: `outputs/`, runtime logs, replay files, private evidence, caches

**Interfaces:**
- Consumes: passing verification and reviewed diff.
- Produces: pushed branch with plan and implementation state ready for main/PR handling.

- [ ] **Step 1: Final status and diff check**

Run:

```powershell
git status --short --branch
git diff --stat
```

Expected: only intended HSConfig source/docs/tests/plans are modified or untracked.

- [ ] **Step 2: Run final targeted verification**

Run:

```powershell
python -m pytest tests/test_universal_wild_no_block_matrix.py tests/test_mechanic_support.py tests/test_mechanic_drift.py tests/test_apply_gate.py tests/test_scope_boundaries.py tests/test_skill_sync.py tests/test_static_semantics.py tests/test_semantic_enrichment.py -q
python scripts/sync_installed_skill.py --check
```

Expected: tests pass and installed skill is in sync.

- [ ] **Step 3: Stage intended files**

Run:

```powershell
git add .agents/skills/hsconfig/SKILL.md .agents/skills/hsconfig/references/workflow.md docs/operator/README.md docs/operator/archetype-fixture-matrix.json docs/operator/universal-wild-no-block-contract.md docs/research/current-truth.md src/hsconfig/card_behavior_surface_router.py src/hsconfig/compile_cardid.py src/hsconfig/config_readiness.py src/hsconfig/guide_claim_builder.py src/hsconfig/guide_source_depth.py src/hsconfig/mechanic_support.py src/hsconfig/static_semantics.py tests/test_archetype_fixture_e2e.py tests/test_boarlock_closure_wave.py tests/test_card_behavior_router.py tests/test_compile_cardid.py tests/test_config_readiness.py tests/test_depth_matrix_e2e.py tests/test_docs_active_path.py tests/test_guide_claim_builder.py tests/test_guide_source_depth.py tests/test_matrix_current_truth.py tests/test_matrix_visibility.py tests/test_mechanic_support.py tests/test_multideck_source_backed_e2e.py tests/test_prepare_cli.py tests/test_shadowpriest_depth_e2e.py tests/test_shadowpriest_e2e.py tests/test_skill_files.py tests/test_source_depth_closure_index.py tests/test_static_semantic_micro_fixtures.py tests/test_mechanic_lowering_parity.py docs/superpowers/plans/2026-07-10-hsconfig-mechanic-lowering-parity-wave.md docs/superpowers/plans/2026-07-10-hsconfig-stabilize-and-sharp-run.md
```

Expected: staged files are intentional; generated `outputs/` stays untracked/ignored.

- [ ] **Step 4: Commit**

Run:

```powershell
git commit -m "chore: stabilize hsconfig no-block mechanic path"
```

Expected: commit succeeds.

- [ ] **Step 5: Push**

Run:

```powershell
git push origin codex/hsconfig-mechanic-lowering-parity
```

Expected: branch push succeeds.

---

## Self-Review

- Spec coverage: The plan covers the recommendation to avoid a large new feature wave, keep HSConfig narrow, verify no-block/mechanic behavior, run one sharp deck proof, and only add drift handling when a real missing mechanic appears.
- Placeholder scan: No `TBD`, `TODO`, or vague “handle edge cases” tasks remain.
- Scope check: The plan explicitly avoids replay parsing, HDT parsing, winrate validation, candidate promotion, and post-run tuning.
- Type and command consistency: Commands use the current `hsconfig` CLI surfaces and the current branch/files observed in the workspace.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-10-hsconfig-stabilize-and-sharp-run.md`.

Two execution options:

1. **Subagent-Driven (recommended)** - Dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints.


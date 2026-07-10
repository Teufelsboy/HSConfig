# HSConfig Mulligan Source Richness Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make HSConfig produce richer, source-backed `Mulligan.json` output whenever guide/source evidence exists, while preserving the current no-block runtime model: a technically valid package remains applyable even when Mulligan evidence is thin.

**Architecture:** Improve the existing pre-run pipeline only. The chain stays `source-manifest -> draft-source-documents -> research-deck -> prepare -> validate -> apply`. `operator_summary.json` remains the single operator gate, `config_usefulness` remains advisory, and `load_safe_apply` remains controlled by VisionAI-load-safe runtime artifacts rather than by Mulligan richness.

**Tech Stack:** Python 3.11, pytest, HSConfig CLI, HearthRanger VisionAI CustomConfig JSON, existing source-document and operator-summary modules. No new dependencies.

## Global Constraints

- Work only in `C:\Users\darbo\Documents\HSConfig`.
- Keep HSConfig pre-run only: no Power.log, HDT, HSReplay, replay parsing, winrate analysis, HSTuner session logic, or post-game tuning in this wave.
- Preserve the operator contract: `operator_summary.json` is the single gate and status authority.
- Preserve the apply contract: `runtime_apply_allowed`, `runtime_apply_mode`, and `runtime_load_safe` must not become stricter because Mulligan is thin.
- Preserve the usefulness contract: `config_usefulness` can recommend more source work, but cannot block apply.
- Do not emit or reintroduce `Presume.json` or `Concede.json`.
- Do not make unsupported/warning-only Hearthstone mechanics fatal. They must surface as actionable diagnostics.
- Do not add dependencies.
- Do not commit generated `.superpowers` research result files unless a later task explicitly promotes a small, curated doc into `docs/`.
- Keep the representative deck matrix stable. This wave improves Mulligan source-to-runtime lowering; it does not broaden the matrix.
- Keep output deck-neutral. ShadowPriest is a regression driver, not a hardcoded implementation target.

---

## File Structure

### Modify

- `src/hsconfig/source_research_manifest.py`
  - Expand the generated Mulligan research questions so the source pass asks for concrete keep/discard rules instead of one generic prompt.
  - Keep `mulligan_guide` as a required source family.

- `src/hsconfig/source_document_builder.py`
  - Preserve and normalize Mulligan selector and condition fields already supported by downstream modules.
  - Add focused diagnostics for Mulligan claims that are present but cannot lower to runtime.

- `src/hsconfig/mulligan_plan.py`
  - Strengthen quality metadata and suppression reasons.
  - Keep current selector/condition lowering model, but make the first missing link obvious.

- `src/hsconfig/config_usefulness.py`
  - Surface Mulligan thinness with machine-readable reasons.
  - Keep `mulligan_gap` advisory and non-blocking.

- `src/hsconfig/operator_summary.py`
  - Surface Mulligan richness and first missing link in the operator summary without changing apply status.

- `docs/operator/README.md`
  - Clarify that a thin `Mulligan.json` is a usefulness gap, not a runtime-load blocker.

- `docs/operator/source-builder-workflow.md`
  - Document the expected source-document shape for source-backed Mulligan rules.

- `C:\Users\darbo\.codex\skills\hsconfig\SKILL.md`
  - Update only if behavior or command guidance changes. Keep the skill lean.

### Tests

- `tests/test_source_research_manifest.py`
- `tests/test_source_document_builder.py`
- `tests/test_mulligan_plan.py`
- `tests/test_compile_mulligan.py`
- `tests/test_config_usefulness.py`
- `tests/test_prepare_cli.py`
- Add `tests/test_mulligan_richness_e2e.py` if an isolated end-to-end fixture test is cleaner than extending existing files.

---

## Task 1: Expand Mulligan Research Manifest Questions

**Purpose:** Make the source collection phase ask for the exact information needed to build a rich `Mulligan.json`.

- [ ] Add failing tests in `tests/test_source_research_manifest.py`.

Test expectations:

```python
questions = manifest["research_questions"]
assert any("always keep" in q.lower() for q in questions)
assert any("coin" in q.lower() and "mulligan" in q.lower() for q in questions)
assert any("opponent class" in q.lower() for q in questions)
assert any("hand partner" in q.lower() or "with another card" in q.lower() for q in questions)
assert any("throw" in q.lower() or "discard" in q.lower() for q in questions)
```

- [ ] Update `_research_questions()` in `src/hsconfig/source_research_manifest.py`.

Required question categories:

- Always-keep cards.
- Conditional keep cards with Coin and without Coin.
- Conditional keep cards by opponent class or matchup speed.
- Keep cards only with a second card already present in hand.
- Explicit mulligan-away cards.
- Early curve and one-drop anchor cards.
- Source confidence and whether the claim comes from a guide, archetype analysis, or static card semantics.

- [ ] Keep the manifest schema backwards compatible.
- [ ] Run targeted test:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python -m pytest tests/test_source_research_manifest.py -q
```

Expected result:

```text
passed
```

**Commit message:** `clarify mulligan research questions`

---

## Task 2: Preserve Source-Backed Mulligan Claim Specificity

**Purpose:** Ensure the source document path does not flatten the exact selector and condition information needed by `mulligan_plan.py`.

- [ ] Add failing tests in `tests/test_source_document_builder.py`.

Required fixture claims:

```json
{
  "kind": "mulligan_keep",
  "card_id": "TEST_001",
  "selector_kind": "card",
  "selector": "TEST_001",
  "condition": {"coin": true},
  "source_family": "mulligan_guide",
  "confidence": "source_backed_static_semantics"
}
```

```json
{
  "kind": "mulligan_keep",
  "selector": "TEST_001+TEST_002",
  "condition": {"hand_contains": "TEST_002"},
  "source_family": "mulligan_guide",
  "confidence": "source_backed_static_semantics"
}
```

```json
{
  "kind": "mulligan_discard",
  "selector": "DROP1",
  "source_family": "mulligan_guide",
  "confidence": "source_backed_static_semantics"
}
```

Test expectations:

- `selector_kind`, `selector`, `condition`, and `conditions` survive normalization.
- Supported `mulligan_keep` and `mulligan_discard` claims remain runtime-lowerable when confidence and source family allow it.
- Low-confidence or report-only claims stay visible but not runtime-lowerable.
- Keep/discard conflicts still appear in the claim conflict report.

- [ ] Update `src/hsconfig/source_document_builder.py` only where normalization or diagnostics lose useful Mulligan detail.
- [ ] Do not introduce new selector grammar unless the current grammar cannot express the fixture cases.
- [ ] Run targeted tests:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python -m pytest tests/test_source_document_builder.py tests/test_source_claim_gap_report.py -q
```

Expected result:

```text
passed
```

**Commit message:** `preserve mulligan claim specificity`

---

## Task 3: Harden Mulligan Plan Quality Metadata

**Purpose:** A thin `Mulligan.json` should never be silent. Every suppressed or missing source-backed rule needs a clear first missing link.

- [ ] Add failing tests in `tests/test_mulligan_plan.py`.

Required cases:

- Source-backed card keep lowers into a hold rule.
- Source-backed card keep with `{"coin": true}` lowers into a conditional hold rule.
- Source-backed card keep with `{"opponent_class": "mage"}` lowers into a conditional hold rule.
- Source-backed `A+B` or `hand_contains` claim lowers into a combo/hand-partner hold rule when current selector/condition helpers support it.
- Source-backed discard claim lowers into a discard rule.
- When at least one concrete hold exists, wildcard discard fallback is added.
- Lone wildcard discard remains suppressed by `compile_mulligan.py`.
- Unsupported selector produces `unsupported_mulligan_selector`.
- Unsupported condition produces `unsupported_mulligan_condition`.
- Non-lowerable claim produces `claim_not_runtime_lowerable`.
- No lowerable keeps produces `no_source_backed_mulligan_keeps`, but not a failed package.

- [ ] Update `src/hsconfig/mulligan_plan.py`.

Required metadata additions:

```json
{
  "status": "thin|rich",
  "first_gap_reason": "no_source_backed_mulligan_keeps|unsupported_mulligan_selector|unsupported_mulligan_condition|claim_not_runtime_lowerable|none",
  "source_backed_rule_count": 0,
  "suppressed_rule_count": 0,
  "suppressed_reasons": {}
}
```

Acceptable implementation detail:

- If the module already has equivalent fields, extend them instead of renaming everything.
- Keep backwards-compatible aliases for existing tests and artifacts.

- [ ] Run targeted tests:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python -m pytest tests/test_mulligan_plan.py tests/test_compile_mulligan.py -q
```

Expected result:

```text
passed
```

**Commit message:** `explain mulligan plan gaps`

---

## Task 4: Make Mulligan Usefulness Gaps Actionable

**Purpose:** The operator should see why Mulligan is thin and what source information would improve it, while still receiving `READY_TO_APPLY_OR_HANDOFF` when the package is load-safe.

- [ ] Add failing tests in `tests/test_config_usefulness.py`.

Required assertions:

```python
assert usefulness["surfaces"]["mulligan"]["status"] in {"thin", "rich"}
assert usefulness["surfaces"]["mulligan"]["first_gap_reason"]
assert usefulness["first_usefulness_gap"] == "mulligan_gap"
assert usefulness["blocking"] is False
```

- [ ] Update `src/hsconfig/config_usefulness.py`.

Required behavior:

- If Mulligan has no source-backed rules, keep `first_usefulness_gap = "mulligan_gap"`.
- Include `first_gap_reason` from the Mulligan plan quality metadata.
- Include a compact `next_source_need` such as `source_backed_mulligan_keeps`.
- Do not change `runtime_load_safe`, `runtime_apply_allowed`, or `runtime_apply_mode`.

- [ ] Add or extend operator summary tests in `tests/test_prepare_cli.py` or a focused summary test.

Required assertions:

```python
assert summary["technical_status"] == "VALID_PACKAGE"
assert summary["runtime_apply_mode"] == "load_safe_apply"
assert summary["next_action"] in {"READY_TO_APPLY_OR_HANDOFF", "READY_FOR_USER_RUN"}
assert summary["config_usefulness"]["first_usefulness_gap"] == "mulligan_gap"
```

- [ ] Run targeted tests:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python -m pytest tests/test_config_usefulness.py tests/test_prepare_cli.py -q
```

Expected result:

```text
passed
```

**Commit message:** `surface mulligan usefulness gaps`

---

## Task 5: Add Rich And Thin Mulligan End-To-End Fixtures

**Purpose:** Prove both paths: rich Mulligan evidence produces runtime rules, while thin evidence stays applyable and clearly diagnosed.

- [ ] Add a small rich source-document fixture.

Suggested path:

```text
tests/fixtures/source_documents_mulligan_rich.json
```

Fixture requirements:

- At least one `mulligan_keep` with `selector_kind = "card"`.
- At least one conditional keep using Coin or opponent class.
- At least one hand-partner or combo keep if current selector support covers it.
- At least one explicit `mulligan_discard`.
- Every runtime-lowerable claim uses `source_family = "mulligan_guide"` and `confidence = "source_backed_static_semantics"`.

- [ ] Add or reuse a thin source-document fixture with no runtime-lowerable Mulligan claims.

Suggested path:

```text
tests/fixtures/source_documents_mulligan_thin.json
```

- [ ] Add `tests/test_mulligan_richness_e2e.py`.

Required rich-path assertions:

```python
assert prepare_result["status"] == "passed"
assert operator_summary["technical_status"] == "VALID_PACKAGE"
assert operator_summary["runtime_apply_mode"] == "load_safe_apply"
assert operator_summary["config_usefulness"]["surfaces"]["mulligan"]["status"] == "rich"
assert mulligan_json_has_rules is True
```

Required thin-path assertions:

```python
assert prepare_result["status"] == "passed"
assert operator_summary["technical_status"] == "VALID_PACKAGE"
assert operator_summary["runtime_apply_mode"] == "load_safe_apply"
assert operator_summary["config_usefulness"]["surfaces"]["mulligan"]["status"] == "thin"
assert operator_summary["config_usefulness"]["first_usefulness_gap"] == "mulligan_gap"
```

- [ ] Keep the fixture generic. Do not hardcode ShadowPriest-only behavior unless the fixture explicitly names ShadowPriest as an example.
- [ ] Run targeted tests:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python -m pytest tests/test_mulligan_richness_e2e.py -q
```

Expected result:

```text
passed
```

**Commit message:** `add mulligan richness e2e coverage`

---

## Task 6: Update Operator Docs And Skill Guidance

**Purpose:** Keep the human/operator path clear without bloating the repo or turning advisory usefulness into a hard gate.

- [ ] Update `docs/operator/README.md`.

Required wording:

- `GlobalValues.json` and `Mulligan.json` are the minimum load-safe runtime artifacts.
- A thin `Mulligan.json` is a usefulness gap, not a load failure.
- `operator_summary.json` is the normal file to open first.
- `config_usefulness.first_usefulness_gap = mulligan_gap` means "better source-backed Mulligan evidence would improve the config", not "do not apply".

- [ ] Update `docs/operator/source-builder-workflow.md`.

Required example:

```json
{
  "kind": "mulligan_keep",
  "selector": "CARD_ID",
  "condition": {"coin": true},
  "source_family": "mulligan_guide",
  "confidence": "source_backed_static_semantics"
}
```

- [ ] Update `C:\Users\darbo\.codex\skills\hsconfig\SKILL.md` only if the operator command wording changed.

Required skill boundaries:

- HSConfig remains pre-run only.
- No `Presume.json` or `Concede.json`.
- `config_usefulness` remains non-blocking.
- Thin Mulligan should be reported, not blocked.

- [ ] If there is a repo script for syncing the skill from the repo to `C:\Users\darbo\.codex\skills\hsconfig`, use it. Otherwise update the installed skill directly and note the direct update in the final implementation summary.

- [ ] Run doc-focused checks:

```powershell
cd C:\Users\darbo\Documents\HSConfig
rg -n "Presume|Concede|HSTuner|Power\.log|HSReplay|winrate" docs README.md src tests
```

Expected result:

- No active-doc claim that HSConfig performs post-game tuning.
- No active-doc instruction to emit `Presume.json` or `Concede.json`.

**Commit message:** `document mulligan usefulness boundary`

---

## Task 7: Run ShadowPriest Smoke Proof

**Purpose:** Confirm the current known ShadowPriest behavior remains load-safe, while the new diagnostics explain why Mulligan is thin if the provided source fixture lacks Mulligan claims.

- [ ] Run the current ShadowPriest fixture smoke:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python -m hsconfig prepare `
  --deck-name ShadowPriest `
  --deck-code AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA= `
  --hs-id 2737726722 `
  --hdt-deck-id c4c8b6b9-1d8e-4c07-a6cd-1c0de84f7602 `
  --source-documents-json tests\fixtures\source_documents_shadowpriest_strong.json `
  --json
```

Expected result:

```text
status=passed
technical_status=VALID_PACKAGE
runtime_apply_mode=load_safe_apply
next_action=READY_TO_APPLY_OR_HANDOFF
```

Expected diagnostic if the fixture still lacks source-backed Mulligan rules:

```text
first_usefulness_gap=mulligan_gap
mulligan_status=thin
first_gap_reason=no_source_backed_mulligan_keeps
```

- [ ] Do not reinterpret this smoke as proof of gameplay quality.
- [ ] Do not write runtime files during this smoke.

**Commit message:** Include this smoke in the final implementation commit only if it required fixture or code changes. Otherwise mention it in the final implementation summary.

---

## Task 8: Full Verification

- [ ] Run targeted tests:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python -m pytest tests/test_source_research_manifest.py tests/test_source_document_builder.py tests/test_source_claim_gap_report.py tests/test_mulligan_plan.py tests/test_compile_mulligan.py tests/test_config_usefulness.py tests/test_prepare_cli.py tests/test_mulligan_richness_e2e.py -q
```

Expected result:

```text
passed
```

- [ ] Run full test suite:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python -m pytest -q
```

Expected result:

```text
passed
```

- [ ] Run package-level CLI sanity:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python -m hsconfig --help
python -m hsconfig prepare --help
```

Expected result:

```text
commands render without traceback
```

- [ ] Check active docs for boundary drift:

```powershell
cd C:\Users\darbo\Documents\HSConfig
rg -n "Power\.log|HSReplay|HDT replay|winrate|post-game|postgame|Presume\.json|Concede\.json" README.md docs src tests
```

Expected result:

- Any matches are either explicit "not part of HSConfig" boundary wording or test names that guard the boundary.

- [ ] Inspect diff:

```powershell
cd C:\Users\darbo\Documents\HSConfig
git diff --stat
git diff -- src/hsconfig/source_research_manifest.py src/hsconfig/source_document_builder.py src/hsconfig/mulligan_plan.py src/hsconfig/config_usefulness.py src/hsconfig/operator_summary.py
git diff -- docs/operator/README.md docs/operator/source-builder-workflow.md
```

- [ ] Confirm no accidental generated artifacts:

```powershell
cd C:\Users\darbo\Documents\HSConfig
git status --short
```

Expected result:

- Only intended source, test, doc, fixture, and skill files are modified.
- No runtime deck config folders, private logs, generated `.superpowers` outputs, or temporary files are tracked.

---

## Final Review Checklist

- [ ] The plan improves Mulligan richness without changing runtime-load safety.
- [ ] `config_usefulness` remains non-blocking.
- [ ] Thin Mulligan has a concrete first missing link.
- [ ] Rich source-backed Mulligan evidence produces actual runtime rules.
- [ ] Unsupported claims are visible and actionable, not fatal.
- [ ] No `Presume.json` or `Concede.json` output was reintroduced.
- [ ] No HSTuner, replay, winrate, or post-game logic was added.
- [ ] Existing representative deck behavior remains stable.
- [ ] Docs and installed skill guidance match the implementation.
- [ ] Full tests pass.

---

## Rollback Plan

If this wave produces incorrect runtime Mulligan output:

1. Revert only the changes from this plan.
2. Keep existing load-safe apply behavior intact.
3. Restore previous Mulligan thin-gap reporting.
4. Re-run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python -m pytest tests/test_mulligan_plan.py tests/test_compile_mulligan.py tests/test_config_usefulness.py -q
```

Expected rollback result:

```text
passed
```

---

## Implementation Completion Criteria

Implementation is complete only when:

- Rich Mulligan source claims lower into `Mulligan.json`.
- Thin Mulligan source evidence remains a non-blocking `mulligan_gap`.
- `operator_summary.json` explains the first missing Mulligan link.
- ShadowPriest smoke still reports a valid load-safe package.
- Full test suite passes.
- `git status --short` contains only intentional tracked changes before commit.


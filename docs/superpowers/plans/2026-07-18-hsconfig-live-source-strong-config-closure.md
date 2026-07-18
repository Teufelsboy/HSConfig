# HSConfig Live Source Strong Config Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the remaining gap between seed-only online research and honest `SOURCE_BACKED_STRONG` / `SOURCE_BACKED_PARTIAL` CustomConfig packages for ShadowPriest and the 12-deck Wild proof matrix. ShadowPriest should become strong only when fetched full-text source documents produce lowerable runtime claims; decklist-only, stats-only, snippet-only, or seed-only inputs must stay diagnostic/contextual and must never masquerade as strong.

**Architecture:** Keep `hsconfig configure` as the only package builder and `reports/operator_summary.json` as the only normal apply authority. Add narrow validation and extraction improvements around the existing source pipeline: `source_acquisition`, `source_text_claim_extractor`, `source_candidate_registry`, `research_status_sync`, and the configure CLI summary. Runtime lowering still flows through the existing source document model and surface gates; this plan improves the quality, honesty, and visibility of source-backed inputs without adding a second config builder.

**Tech Stack:** Python stdlib, pytest, existing HSConfig CLI/modules, existing `docs/operator` source inputs, fixture-backed tests for deterministic CI, live online source fetches only as operator verification. No new dependency is required.

## Global Constraints

- Work only in `C:\Users\darbo\Documents\HSConfig` for this implementation.
- Start execution with a repository refresh:
  ```powershell
  git fetch --all --prune --tags
  git status --short --branch
  git rev-list --left-right --count HEAD...origin/main
  ```
- Baseline at plan creation was branch `codex/hsconfig-canonical-source-status-sync`, clean before this plan file, and `git rev-list --left-right --count HEAD...origin/main` returned `10 0`.
- Do not push unless the user explicitly asks.
- Do not run `--apply` or write live HearthRanger runtime files in this plan. Package generation and validation are allowed; live runtime apply is out of scope.
- Preserve `reports/operator_summary.json` as the only normal apply authority.
- Treat `SOURCE_BACKED_STRONG` as an evidence label, not as an apply gate.
- Keep `source_status_apply_blocking=false`; missing or partial source evidence must request follow-up research, not block generation.
- No hidden `default only` success: default-only runtime surfaces must be reported and must not be relabeled as strong.
- Public URLs in candidate registries are acquisition seeds until fetched, normalized, classified, and converted into claim records.
- Decklist/stat pages can support currentness and archetype context, but they cannot by themselves prove mulligan, combo, targeting, or per-card runtime claims.
- Historical `$research-deep` snapshots are diagnostic only; they cannot promote or downgrade canonical package status.
- ShadowPriest `Darkbishop Benedictus` must preserve the start-of-game shadow hero power effect contract while staying absent from opening-hand keep logic.
- Tests must use deterministic local fixtures. Live web checks belong in operator verification and docs, not required CI.
- Keep edits narrow; avoid broad rewrites, new architecture layers, or duplicated builders.

---

## Task 1: Reconfirm Baseline and Existing Contracts

**Purpose:** Ensure implementation starts from a current, clean, known state and does not regress existing source/contract behavior.

- [ ] Run repository refresh and status checks:
  ```powershell
  cd C:\Users\darbo\Documents\HSConfig
  git fetch --all --prune --tags
  git status --short --branch
  git rev-list --left-right --count HEAD...origin/main
  ```
  Expected:
  - Branch is `codex/hsconfig-canonical-source-status-sync`.
  - No unrelated dirty files.
  - Ahead/behind is recorded in the implementation notes.

- [ ] Run focused baseline tests:
  ```powershell
  python -m pytest tests\test_research_status_sync.py tests\test_source_status_resolver.py tests\test_source_acquisition.py tests\test_source_text_claim_extractor.py tests\test_universal_wild_no_block_matrix.py -q -p no:cacheprovider
  ```
  Expected:
  - Existing tests pass before changing implementation.
  - Any failure is investigated before editing source files.

- [ ] Inspect these files before edits:
  - `src/hsconfig/source_document_model.py`
  - `src/hsconfig/source_acquisition.py`
  - `src/hsconfig/source_text_claim_extractor.py`
  - `src/hsconfig/research_status_sync.py`
  - `src/hsconfig/source_status_resolver.py`
  - `src/hsconfig/commands/configure.py`
  - `src/hsconfig/commands/source_workflow.py`
  - `src/hsconfig/source_candidate_registry.py`
  - `docs/operator/source-candidate-proof-decks.json`
  - `tests/test_universal_wild_no_block_matrix.py`

Implementation note:
- This task is read-only except for normal pytest cache creation. Remove generated cache artifacts before final status if they appear.

---

## Task 2: Add a Strict Research Result Contract Classifier

**Purpose:** Make the diagnostic boundary explicit: seed-only research and partial snapshots are useful for follow-up, but they cannot silently become canonical source-backed proof.

### Files

- Create: `src/hsconfig/research_result_contract.py`
- Create: `tests/test_research_result_contract.py`
- Modify: `src/hsconfig/research_status_sync.py`
- Modify: `tests/test_research_status_sync.py`

### Behavior

Add a small pure-Python classifier:

```python
from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def classify_research_result_contract(payload: Mapping[str, Any]) -> dict[str, Any]:
    ...
```

Required normalized return fields:

- `contract_valid: bool`
- `snapshot_kind: str`
- `canonical_promotion_allowed: bool`
- `canonical_downgrade_allowed: bool`
- `source_status_apply_blocking: bool`
- `errors: list[str]`
- `warnings: list[str]`
- `lowerable_claim_kinds: list[str]`

Classification rules:

- Missing required identity fields (`deck_name`, `deck_code` or equivalent source row identity) return `contract_valid=false`, `snapshot_kind="invalid"`.
- Strengths in the existing seed set, including `unfetched_acquisition_seed`, return:
  - `snapshot_kind="seed_only"`
  - `canonical_promotion_allowed=false`
  - `canonical_downgrade_allowed=false`
  - `source_status_apply_blocking=false`
- Partial fetched or snippet-only evidence returns:
  - `snapshot_kind="partial"`
  - `canonical_promotion_allowed=false`
  - `canonical_downgrade_allowed=false`
  - `source_status_apply_blocking=false`
- Strong is allowed only when all are true:
  - Source status or source strength is `SOURCE_BACKED_STRONG` or equivalent internal strong marker.
  - `first_missing_source_action` is `none`.
  - There is at least one lowerable claim kind accepted by `source_document_model`.
  - The snapshot contains fetched full-text or explicit canonical evidence, not only URL seeds.
- No research snapshot can ever set `canonical_downgrade_allowed=true`.

Integrate into `research_status_sync._research_snapshot_row(...)` by appending diagnostic fields only:

- `research_contract_valid`
- `research_snapshot_kind`
- `research_canonical_promotion_allowed`
- `research_canonical_downgrade_allowed`
- `research_contract_errors`

Do not change canonical package status resolution in this task.

### Tests

`tests/test_research_result_contract.py` must cover:

- Seed-only payload stays diagnostic and non-promoting.
- Strong payload with lowerable claim kinds is valid and promotion-eligible as an input signal.
- Strong-looking payload without lowerable claim kinds is partial/non-promoting.
- Missing identity is invalid and non-blocking.
- No payload can request canonical downgrade.

Add regression in `tests/test_research_status_sync.py`:

- `build_research_status_sync_report(...)` includes contract fields.
- Seed-only sync does not downgrade an existing package that is already `SOURCE_BACKED_STRONG`.
- Invalid research payload appears as diagnostic row with errors and does not block.

### Verification

```powershell
python -m pytest tests\test_research_result_contract.py tests\test_research_status_sync.py -q -p no:cacheprovider
```

Expected output:
- All tests pass.
- No runtime package or operator summary is written by research status sync.

---

## Task 3: Improve Full-Text Claim Extraction for ShadowPriest Without False Keeps

**Purpose:** Convert fetched full-text ShadowPriest guide evidence into useful lowerable claims while preserving the Darkbishop effect-vs-card distinction.

### Files

- Modify: `src/hsconfig/source_text_claim_extractor.py`
- Modify: `tests/test_source_text_claim_extractor.py`

### Behavior

Keep the existing rule that only full-text strong guide records produce runtime claims.

Add narrow extraction for these claim kinds:

- `mulligan_keep`
- `mulligan_discard`
- `gameplan_posture`
- `hero_power_transform`

Add helper functions with deterministic string matching:

```python
def _extract_listed_keep_claims(
    *,
    cards_by_name: Mapping[str, Mapping[str, Any]],
    text: str,
    source_record: Mapping[str, Any],
) -> list[dict[str, Any]]:
    ...


def _extract_gameplan_posture_claims(
    *,
    text: str,
    source_record: Mapping[str, Any],
) -> list[dict[str, Any]]:
    ...
```

`_extract_listed_keep_claims` must support source text patterns equivalent to:

- `Keep A, B, C`
- `Keep A, B and C`
- `Mulligan Tips: Keep A, B, C`
- direct existing forms already supported, such as `keep A`

It must not interpret these as keeps:

- `Don't keep A`
- `Do not keep A`
- `Don't keep 4 cost or higher cards`
- `Do not keep 4-cost or higher`
- card names that only appear in decklist sections with no keep cue

`_extract_gameplan_posture_claims` should emit deck-level posture evidence when fetched full-text guide text contains clear aggro/burn/hero-power strategy cues. The value should be conservative, for example:

```json
{
  "claim_kind": "gameplan_posture",
  "value": "aggressive_burn_shadow_hero_power",
  "surface": "GlobalValues",
  "source_strength": "SOURCE_BACKED_STRONG"
}
```

Preserve existing cost-discard extraction:

- Text equivalent to `Don't keep any 4-cost or higher cards` emits a `mulligan_discard` policy for expensive cards.
- This discard policy must not create a keep for `Darkbishop Benedictus`.

Preserve ShadowPriest effect handling:

- A full-text source indicating shadow hero power / start-of-game shadowform can emit `hero_power_transform`.
- `Darkbishop Benedictus` may remain in per-card effect output, such as `SW_448.json`, but must not be put into `Mulligan.json` as a keep unless a source explicitly says to keep the physical card in opening hand.

### Tests

Extend `tests/test_source_text_claim_extractor.py` with fixtures that include synthetic but representative source text:

```text
This is an aggressive Shadow Priest guide. Use the shadow hero power to pressure face.
Mulligan Tips: Keep Papercraft Angel, Shadowcloth Needle, and Twilight Deceptor.
Don't keep any 4-cost or higher cards.
Darkbishop Benedictus changes the starting hero power.
```

Assert:

- Keep claims are emitted for `Papercraft Angel`, `Shadowcloth Needle`, and `Twilight Deceptor`.
- No keep claim is emitted for `Darkbishop Benedictus`.
- A `mulligan_discard` policy exists for expensive cards.
- A `hero_power_transform` claim exists.
- A `gameplan_posture` claim exists.
- Decklist-only source records still emit no runtime claims.
- Snippet-only or currentness-only records still emit no runtime claims.

### Verification

```powershell
python -m pytest tests\test_source_text_claim_extractor.py -q -p no:cacheprovider
```

Expected:
- The test file passes.
- ShadowPriest gains stronger claims only from full-text guide evidence.

---

## Task 4: Refresh Candidate Registry Boundaries for Current Wild Sources

**Purpose:** Keep online source discovery current while preventing current decklist pages from being treated as strong runtime proof.

### Files

- Modify: `src/hsconfig/source_candidate_registry.py`
- Modify: `tests/test_source_candidate_registry.py`
- Modify: `docs/operator/source-candidate-proof-decks.json`

### Source Policy

Use the registry as a seed list only. Store source candidates with explicit ceilings:

- Full-text guide candidates may have `expected_strength="candidate_strong"` and `strength_ceiling="runtime_claims_possible"`.
- Decklist/stat/meta pages must have `strength_ceiling="context_only"`.
- Decklist/stat/meta pages must have empty or non-runtime `expected_claim_kinds`.
- First missing source action for context-only pages should request a full-text guide or explicit mulligan/runtime source.

### Concrete Candidate Updates

Keep the ShadowPriest full-text guide candidate as the primary strong candidate:

- Deck: `ShadowPriest`
- Candidate URL: HearthPwn Wild Aggro Shadow Priest guide URL already present in the registry.
- Expected source family: guide.
- Expected claim kinds:
  - `archetype`
  - `mulligan_keep`
  - `mulligan_discard`
  - `gameplan_posture`
  - `hero_power_transform`

Add or refresh context-only current Wild index candidates where helpful:

- Warlock Wild page for Discolock/Boarlock currentness:
  - `https://hearthstone-decks.net/wild-decks/warlock-wild-decks/`
- Warrior Wild page for CuteWarrior currentness:
  - `https://hearthstone-decks.net/wild-decks/warrior-wild-decks/`

These pages must not be configured as strong runtime candidates unless the fetched page contains full-text guide sections with explicit lowerable claims. Their registry entries should make that boundary visible.

### Tests

`tests/test_source_candidate_registry.py` must assert:

- Every candidate includes `strength_ceiling`.
- Every context-only candidate has no lowerable runtime claim kinds.
- ShadowPriest guide candidate declares runtime-claim-capable expected kinds.
- Candidate URL rows are not treated as authority without acquisition.
- The 12 proof decks are represented without blocking config generation when strong sources are missing.

### Verification

```powershell
python -m pytest tests\test_source_candidate_registry.py -q -p no:cacheprovider
```

Expected:
- Candidate metadata is explicit about strength ceilings.
- No context-only URL can accidentally produce `SOURCE_BACKED_STRONG` by registry metadata alone.

---

## Task 5: Add ShadowPriest Source-Backed Acceptance Fixture

**Purpose:** Prove the full path from fetched source text to generated ShadowPriest package without depending on live web during CI.

### Files

- Create or modify: `tests/fixtures/source_pages/shadowpriest_current_guide.html`
- Create: `tests/test_shadowpriest_source_contract_acceptance.py`

### Fixture Requirements

The fixture should be synthetic and compact, not a copied external article. It must include the same claim patterns the extractor supports:

- Current year marker.
- ShadowPriest archetype/name.
- Aggro/burn gameplan language.
- Shadow hero power / start-of-game transform language.
- Explicit mulligan keep list.
- Explicit expensive-card discard rule.

Example fixture text body:

```html
<main>
  <h1>Wild Aggro Shadow Priest Guide 2026</h1>
  <p>This ShadowPriest deck is an aggressive burn deck. Use the shadow hero power to pressure face and close games quickly.</p>
  <section>
    <h2>Mulligan Tips</h2>
    <p>Keep Papercraft Angel, Shadowcloth Needle, and Twilight Deceptor.</p>
    <p>Do not keep any 4-cost or higher cards.</p>
  </section>
  <p>Darkbishop Benedictus changes the starting hero power; the effect matters, not keeping the card in the opening hand.</p>
</main>
```

### Test Flow

The acceptance test should run the same CLI surfaces an operator uses, with fixture URL mapping:

1. Build a temporary package/output root.
2. Run `hsconfig configure` for ShadowPriest with:
   - `--online-source`
   - `--auto-source`
   - `--source-url <ShadowPriest candidate URL>`
   - `--source-fixture-url-map-json <fixture map>`
   - `--current-date 2026-07-18`
3. Read generated package reports and runtime files.

Assertions:

- Configure command exits successfully.
- `reports/operator_summary.json` exists.
- `source_backed_status` is `SOURCE_BACKED_STRONG` only when lowerable full-text claims were accepted.
- `default_only_runtime_surfaces` is empty for the generated package.
- `source_status_apply_blocking` is false.
- `Mulligan.json` contains expected explicit keeps.
- `Mulligan.json` does not contain `Darkbishop Benedictus` as keep.
- `SW_448.json` or equivalent per-card effect output preserves the hero power transform effect if that is how the current generator lowers it.
- `first_missing_source_action` is `none` for ShadowPriest only when the accepted full-text source closes all configured required surfaces.

### Verification

```powershell
python -m pytest tests\test_shadowpriest_source_contract_acceptance.py -q -p no:cacheprovider
```

Expected:
- The deterministic fixture proves the strong path.
- No live network access is required for the test.

---

## Task 6: Expose Source Closure Status in Configure Output

**Purpose:** Make the operator-facing result honest and easy to inspect after generating a CustomConfig.

### Files

- Modify: `src/hsconfig/commands/configure.py`
- Modify: `tests/test_configure_online_source.py`

### Behavior

At the successful end of `configure_payload(...)`, include these fields in the returned payload if `operator_summary` is available:

- `source_backed_status`
- `source_status_reason`
- `source_status_apply_blocking`
- `first_missing_source_action`
- `default_only_runtime_surfaces`
- `source_bundle_path`
- `source_evidence_closure_path`

The fields must mirror the generated reports and must not independently recompute status.

Error behavior:

- If the reports are missing, return the existing configure success/failure behavior unchanged.
- Do not turn source partiality into command failure.
- Do not create a second authority.

### Tests

Extend `tests/test_configure_online_source.py`:

- Configure payload includes source status fields on success.
- Partial source evidence returns success with honest `SOURCE_BACKED_PARTIAL`.
- Strong fixture returns `SOURCE_BACKED_STRONG`.
- `source_status_apply_blocking` remains false in both partial and strong cases.
- `default_only_runtime_surfaces` are surfaced as data, not hidden.

### Verification

```powershell
python -m pytest tests\test_configure_online_source.py -q -p no:cacheprovider
```

Expected:
- CLI payload is transparent.
- Operator can immediately see whether the package is strong, partial, or default-only-affected.

---

## Task 7: Lock the Universal Wild No-Block Contract Against New Source Logic

**Purpose:** Ensure stronger ShadowPriest source logic does not reintroduce blocking behavior for the wider Wild proof deck set.

### Files

- Modify: `tests/test_universal_wild_no_block_matrix.py`
- Modify only if needed: `docs/operator/universal-wild-no-block-contract.md`

### Behavior

Preserve these invariants for all listed proof decks:

- Config generation must not block because a deck lacks strong source evidence.
- No generated package may include `Presume` / `Concede` decision logic.
- No generated package may hide default-only runtime surfaces.
- Source status can be partial, but apply blocking must remain false.
- Seed-only source data must be diagnostic only.
- ShadowPriest must keep `Darkbishop Benedictus` effect semantics without opening-hand keep behavior.

Proof deck set:

- `ShadowPriest`
- `CtAPaladin`
- `PirateRogue`
- `BigShaman`
- `Discolock`
- `TreantDruid`
- `ImbueMage`
- `MechPala`
- `Kingslayer`
- `Boarlock`
- `PirateDH`
- `CuteWarrior`

### Tests

Add or preserve assertions:

- All proof decks produce an operator summary.
- `source_status_apply_blocking is False`.
- `default_only_runtime_surfaces == []` when the package claims no default-only surfaces; otherwise the exact surfaces are reported.
- No status resolver output treats `default only` as `SOURCE_BACKED_STRONG`.
- ShadowPriest has no Darkbishop opening-hand keep.

### Verification

```powershell
python -m pytest tests\test_universal_wild_no_block_matrix.py -q -p no:cacheprovider
```

Expected:
- All proof decks remain non-blocking.
- ShadowPriest stronger extraction does not leak into unrelated decks.

---

## Task 8: Update Operator Docs and HSConfig Skill Guidance

**Purpose:** Keep the human workflow aligned with the code so future runs do not confuse source seeds, research snapshots, and source-backed package truth.

### Files

- Create or modify: `docs/operator/source-backed-strong-closure.md`
- Modify: `docs/research/current-truth.md`
- Modify: `docs/operator/universal-wild-no-block-contract.md`
- Modify: `.agents/skills/hsconfig/SKILL.md`
- Modify or create tests:
  - `tests/test_research_current_truth.py`
  - `tests/test_docs_active_path.py`
  - `tests/test_skill_sync.py`

### Required Documentation Points

Document the canonical source flow:

1. `docs/operator/source-candidate-proof-decks.json` contains seeds.
2. `source-acquire` fetches and classifies public source records.
3. `source_text_claim_extractor` converts full-text guide records into claims.
4. `source_document_model` decides what can lower into runtime surfaces.
5. `hsconfig configure` writes package reports and runtime config.
6. `reports/operator_summary.json` is the normal apply authority.
7. `research-status-sync` is diagnostic only.

Document the evidence labels:

- `SOURCE_BACKED_STRONG`: fetched source text produced accepted lowerable claims and closure has no missing required source action.
- `SOURCE_BACKED_PARTIAL`: source context exists but does not fully close required runtime claims.
- `default only`: generated runtime surface is still default-driven and must be reported; it must not be hidden.
- `seed only`: URL or research seed was found but not fetched and normalized into claims.

Document ShadowPriest-specific guardrail:

- `Darkbishop Benedictus` effect matters for the shadow hero power transform.
- The physical card should not be kept in opening hand unless explicit source text says to keep it.

### Tests

Documentation tests must assert:

- Docs mention `operator_summary.json` as the normal apply authority.
- Docs mention seed-only source data as non-promoting.
- Skill guidance tells operators to use `configure` rather than constructing package files manually.
- Skill guidance preserves the Darkbishop effect-vs-keep distinction.

### Verification

```powershell
python -m pytest tests\test_research_current_truth.py tests\test_docs_active_path.py tests\test_skill_sync.py -q -p no:cacheprovider
```

Expected:
- Documentation and skill guidance stay synchronized with implementation.

---

## Task 9: Run Live Operator Verification Without Making CI Depend on the Web

**Purpose:** Confirm current public sources are reachable and classified honestly on the operator machine while preserving deterministic tests.

### Commands

Run a live dry verification for ShadowPriest:

```powershell
python -m hsconfig source-acquire `
  --deck-name ShadowPriest `
  --deck-code "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=" `
  --source-url "<ShadowPriest HearthPwn guide candidate URL from source_candidate_registry.py>" `
  --current-date 2026-07-18
```

Then run package generation without live apply:

```powershell
python -m hsconfig configure `
  --deck-name ShadowPriest `
  --deck-code "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=" `
  --online-source `
  --auto-source `
  --current-date 2026-07-18
```

Expected:

- Command does not require `--apply`.
- Configure writes a package with reports.
- Returned payload includes source status fields from Task 6.
- If live source fetch succeeds and lowerable claims are accepted, ShadowPriest may report `SOURCE_BACKED_STRONG`.
- If live source fetch fails or the page changes, ShadowPriest reports `SOURCE_BACKED_PARTIAL` with `first_missing_source_action` explaining the missing evidence.
- Neither outcome blocks config generation.

Record live findings in:

- `docs/operator/source-backed-strong-closure.md`

Do not store raw fetched page HTML in the repository unless it is a compact synthetic fixture.

---

## Task 10: Final Verification and Cleanup

**Purpose:** Prove the implementation is complete, narrow, and clean.

### Focused Verification

Run:

```powershell
python -m pytest tests\test_research_result_contract.py tests\test_research_status_sync.py tests\test_source_text_claim_extractor.py tests\test_source_acquisition.py tests\test_source_candidate_registry.py tests\test_configure_online_source.py tests\test_shadowpriest_source_contract_acceptance.py tests\test_universal_wild_no_block_matrix.py tests\test_research_current_truth.py tests\test_docs_active_path.py tests\test_skill_sync.py -q -p no:cacheprovider
```

Expected:

- All focused tests pass.
- No test requires live network access.

### Full Verification

Run:

```powershell
python -m pytest -q -p no:cacheprovider
```

Expected:

- Full test suite passes.

### Git Review

Run:

```powershell
git status --short
git diff -- src tests docs .agents
```

Expected:

- Only intended files changed.
- No raw runtime evidence, logs, cache folders, private Hearthstone data, or live fetched HTML artifacts are present.
- The final diff shows a narrow extension of existing source/contract logic.

### Completion Criteria

This plan is complete when all are true:

- ShadowPriest can produce a source-backed package from deterministic full-text guide fixture evidence.
- `SOURCE_BACKED_STRONG` is emitted only from accepted fetched/full-text lowerable claims.
- Seed-only, decklist-only, stats-only, and snippet-only sources cannot produce strong status by themselves.
- The 12-deck Wild proof matrix remains non-blocking.
- `Darkbishop Benedictus` effect semantics remain present while opening-hand keep behavior remains absent.
- Configure output exposes source status and default-only surfaces honestly.
- Documentation and HSConfig skill guidance match the implementation.
- Worktree contains only intentional implementation changes before final handoff.

---

## Suggested Subagent Split

Use `superpowers:subagent-driven-development` for implementation. Recommended split:

- **Agent A - Contract Classifier Worker:** Task 2 only.
- **Agent B - Claim Extraction Worker:** Task 3 only.
- **Agent C - Candidate Registry and Docs Worker:** Tasks 4 and 8.
- **Agent D - Acceptance and Matrix Worker:** Tasks 5, 6, and 7.
- **Main Agent:** Task 1, integration decisions, Task 9 live verification, Task 10 final verification, final diff review.

Do not let multiple agents write the same file. If two tasks touch a shared file, the main agent serializes those edits after reading subagent output.

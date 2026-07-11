# HSConfig Claim-Kind Runtime Contract Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make HSConfig's source, contract, and runtime lowering logic unambiguous, slim, and deck-universal by using `claim_kind` as the explicit machine contract for runtime decisions. Broad guide text, legacy `claim_type`, and card static effects must never accidentally become Mulligan keeps. Darkbishop Benedictus-style start-of-game effects remain represented as effects, but are excluded from opening-hand keep logic unless an explicit mulligan source says to keep the card.

**Architecture:** Preserve the current pipeline and tighten the contract boundary:

`deck input -> source documents -> normalized claims -> research contract -> gameplan contract -> runtime surfaces`

Runtime lowering is controlled by a typed claim contract:

`claim_kind + claim_readiness + trust_ceiling + documented VisionAI surface`

Guide text and card metadata enrich card expectations. They do not directly write `Mulligan.json`, `GlobalValues.json`, `Combo.json`, or per-card `<CARDID>.json` unless the normalized claim has a runtime-safe `claim_kind`.

GlobalValues has one explicit curated-authority exception: raw `gameplan_posture` remains contract-only, but the existing GlobalValues authority may consume it through approved source-backed numeric/archetype baselines (`allowed_step1_overlays`). That lane is not free-text lowering and must stay separate from Mulligan, Combo, and per-card runtime decisions.

**Tech Stack:** Python package under `src/hsconfig`, pytest tests, existing HearthRanger VisionAI JSON writers, existing research artifacts under `docs/research`, no new dependencies.

## Global Constraints

- Keep HSConfig pre-run only. Do not add replay analysis, winrate evaluation, log parsing, HSTuner behavior, or post-run tuning to this plan.
- Do not block deck generation because a deck lacks perfect guide evidence. Unknown or weak evidence must produce lower confidence or review notes, not a failed config run.
- Block only technical invalidity: malformed deck input, invalid generated JSON, missing runtime directory for apply mode, schema breakage, or an exception that would produce corrupt output.
- `Mulligan.json` must be driven by explicit mulligan claims only: `claim_kind="mulligan_keep"` or `claim_kind="mulligan_discard"`, subject to readiness and trust rules.
- Do not infer a Mulligan keep from words like "core", "important", "always active", "gameplan", "effect", "start of game", or broad legacy `claim_type` values.
- Start-of-game deck-enabler cards can remain in source contracts, card-role maps, effect expectations, and per-card behavior reasoning. They must not become opening-hand keeps without explicit mulligan evidence.
- Preserve the current no-block behavior for arbitrary Wild decks. If a mechanism is unknown, emit a safe generic card expectation and continue.
- Keep the implementation narrow. Do not refactor unrelated orchestration, CLI layout, repository history, or old archived plans.
- Do not introduce new dependencies.
- Do not commit private runtime evidence, HearthRanger logs, HDT logs, Power.log, or game replays.

---

## Current Evidence Snapshot

### Known Failing Baseline

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python -m pytest tests\test_source_document_builder.py tests\test_research_contract.py tests\test_gameplan_contract.py tests\test_mulligan_plan.py tests\test_archetype_source_fixtures.py -q
```

Expected baseline before implementation:

```text
3 failed, 82 passed
```

The three failures are intentional legacy-contract drift:

- `tests/test_research_contract.py::test_research_contract_emits_all_operator_artifacts`
- `tests/test_gameplan_contract.py::test_gameplan_contract_covers_every_card_with_source_confidence`
- `tests/test_gameplan_contract.py::test_gameplan_contract_preserves_guide_backed_confidence_lane`

Reason: test fixtures use broad legacy `claim_type="mulligan_and_gameplan"` while expecting a runtime Mulligan hold. The new contract requires explicit `claim_kind="mulligan_keep"` for a hold.

### Research Package To Keep As Evidence

The current untracked research package is part of this implementation wave:

```text
docs/research/2026-07-11-hsconfig-source-contract-logic-audit/
  outline.yaml
  fields.yaml
  results/Autonomous_guide_claim_contract_quality_model.json
  results/HearthRanger_VisionAI_runtime_lowering_surfaces.json
  results/Hearthstone_start-of-game_and_mulligan_semantics.json
```

This package should remain evidence, not operator guidance. Add a small `README.md` to state that boundary.

---

## Desired Contract

### Claim Kinds

These claim kinds are runtime-relevant when readiness and trust allow it:

```python
RUNTIME_LOWERABLE_CLAIM_KINDS = {
    "mulligan_keep",
    "mulligan_discard",
    "targeting_rule",
    "combo_sequence",
    "hero_power_transform",
    "mechanic_usage",
    "known_bad_pattern",
    "discover_choice",
    "choose_one_choice",
}
```

These claim kinds can inform contracts, summaries, and review text, but do not directly write a runtime surface by themselves:

```python
CONTRACT_ONLY_CLAIM_KINDS = {
    "card_role",
    "gameplan_posture",
    "tech_slot",
    "replacement_option",
}
```

If the current project already has a broader constant in `src/hsconfig/source_document_model.py`, extend or reuse it instead of duplicating constants in multiple modules.

`gameplan_posture` is contract-only as a raw claim. It may still feed `GlobalValues.json` only through the dedicated GlobalValues authority when it maps to an approved source-backed numeric/archetype baseline. Do not let arbitrary posture prose write GlobalValues numbers directly.

### Runtime Claim Kind Helper

Add one shared helper in `src/hsconfig/source_document_model.py` so runtime decisions do not each invent their own fallback behavior:

```python
EXACT_LEGACY_RUNTIME_CLAIM_TYPES = frozenset({
    "mulligan_keep",
    "mulligan_discard",
    "targeting_rule",
    "combo_sequence",
    "hero_power_transform",
    "mechanic_usage",
    "known_bad_pattern",
    "discover_choice",
    "choose_one_choice",
})


def runtime_claim_kind(claim: Mapping[str, Any]) -> str:
    """Return the explicit runtime claim kind, with only exact legacy fallback."""
    explicit = str(claim.get("claim_kind", "")).strip().lower()
    if explicit:
        return explicit

    legacy = str(claim.get("claim_type", "")).strip().lower()
    if legacy in EXACT_LEGACY_RUNTIME_CLAIM_TYPES:
        return legacy

    return ""
```

Rules:

- `claim_kind` wins.
- A legacy `claim_type` is accepted only when it already equals an exact runtime-safe kind or an explicit compatibility alias.
- Broad legacy types such as `mulligan_and_gameplan`, `guide`, `gameplan`, or `effect` do not become runtime-safe kinds by text inference. Exact compatibility aliases such as `combo -> combo_sequence` and `bad_pattern -> known_bad_pattern` remain supported because they preserve existing explicit legacy input semantics without relying on free-text inference.

If the implementation finds existing broad legacy `claim_type` values that are still needed for current generated fixtures, keep them as contract-only roles and update tests to reflect that split.

---

## Implementation Tasks

### Task 1: Baseline And Contract Regression Tests

- [ ] Run the known failing baseline command from this plan and confirm the three legacy failures are still the only failures in that targeted group.
- [ ] Add a focused regression test file:

```text
tests/test_claim_kind_runtime_contract.py
```

- [ ] Add tests proving broad legacy text does not lower to runtime Mulligan:

```python
def test_broad_legacy_mulligan_claim_type_does_not_create_hold(tmp_path):
    source_claim = {
        "card_id": "SW_448",
        "card_name": "Darkbishop Benedictus",
        "claim_type": "mulligan_and_gameplan",
        "claim": "The effect enables Shadowform at game start.",
        "confidence": 0.95,
        "evidence": {"source": "fixture"},
    }

    bundle = build_research_contract_from_claims(
        deck_name="FixtureDeck",
        claims=[source_claim],
        output_dir=tmp_path,
    )

    assert bundle["mulligan_anchor_map"]["SW_448"]["intent"] != "hold"
```

- [ ] Add tests proving explicit claim kinds do lower:

```python
def test_explicit_mulligan_keep_claim_kind_creates_hold(tmp_path):
    source_claim = {
        "card_id": "EX1_001",
        "card_name": "Fixture One-Drop",
        "claim_kind": "mulligan_keep",
        "claim_readiness": "guide_backed",
        "trust_ceiling": "runtime_candidate",
        "claim": "Keep this one-drop in the mulligan.",
        "confidence": 0.95,
        "evidence": {"source": "fixture"},
    }

    bundle = build_research_contract_from_claims(
        deck_name="FixtureDeck",
        claims=[source_claim],
        output_dir=tmp_path,
    )

    assert bundle["mulligan_anchor_map"]["EX1_001"]["intent"] == "hold"
```

- [ ] Use the actual project helpers and function names. If the existing public helper differs, import the nearest existing contract builder and keep the assertion semantics above.
- [ ] Expected after adding tests but before source changes: at least one new failing assertion documents the undesired legacy behavior.

### Task 2: Align Legacy Test Fixtures With Explicit Claims

- [ ] Update `tests/test_research_contract.py`.
- [ ] Update `tests/test_gameplan_contract.py`.
- [ ] Replace fixtures that expect a hold with explicit `claim_kind="mulligan_keep"`.
- [ ] Preserve broad `claim_type="mulligan_and_gameplan"` only in tests that prove the old broad type is contract-only.
- [ ] For negative opening-hand guidance, use explicit `claim_kind="mulligan_discard"` when the test expects a discard/avoid lane.
- [ ] Do not change assertions to accept weaker behavior. The test should say exactly whether the card is a hold, discard, neutral, role-only, or review-only.

Example fixture conversion:

```python
{
    "card_id": "EX1_001",
    "card_name": "Fixture One-Drop",
    "claim_kind": "mulligan_keep",
    "claim_readiness": "guide_backed",
    "trust_ceiling": "runtime_candidate",
    "claim": "Always keep this one-drop.",
    "confidence": 0.95,
    "evidence": {"source": "fixture-guide"},
}
```

- [ ] Re-run:

```powershell
python -m pytest tests\test_research_contract.py tests\test_gameplan_contract.py -q
```

Expected before source changes: only failures that reveal source/contract logic, not fixture ambiguity.

### Task 3: Centralize Runtime Claim-Kind Resolution

- [ ] Modify `src/hsconfig/source_document_model.py`.
- [ ] Add or refine a single helper named `runtime_claim_kind`.
- [ ] Keep the helper side-effect free.
- [ ] Ensure it accepts `Mapping[str, Any]`.
- [ ] Use exact legacy fallback only, as shown in the helper contract above.
- [ ] Add direct unit tests for the helper:

```python
def test_runtime_claim_kind_prefers_explicit_claim_kind():
    claim = {"claim_kind": "mulligan_keep", "claim_type": "mulligan_and_gameplan"}
    assert runtime_claim_kind(claim) == "mulligan_keep"


def test_runtime_claim_kind_accepts_exact_legacy_kind_only():
    assert runtime_claim_kind({"claim_type": "mulligan_keep"}) == "mulligan_keep"
    assert runtime_claim_kind({"claim_type": "mulligan_and_gameplan"}) == ""
```

- [ ] Import and use this helper in:

```text
src/hsconfig/mulligan_plan.py
src/hsconfig/research_contract.py
src/hsconfig/gameplan_contract.py
```

- [ ] Search for ad-hoc runtime kind fallbacks:

```powershell
rg -n "claim_kind.*claim_type|claim_type.*claim_kind|get\(\"claim_type\"|mulligan_and_gameplan" src tests
```

- [ ] Replace runtime-sensitive fallbacks with `runtime_claim_kind`.
- [ ] Keep non-runtime reporting fields that still show legacy `claim_type`, but label them as legacy/report fields if documentation is touched.

### Task 4: Fix Mulligan Lowering And Start-Of-Game Suppression

- [ ] Modify `src/hsconfig/mulligan_plan.py`.
- [ ] The Mulligan planner must only process these runtime kinds:

```python
MULLIGAN_RUNTIME_KINDS = frozenset({"mulligan_keep", "mulligan_discard"})
```

- [ ] It must call `runtime_claim_kind(claim)`.
- [ ] It must still call the existing `claim_can_lower_to_runtime(claim)` gate.
- [ ] Preserve the current start-of-game suppression reason:

```text
start_of_game_effect_does_not_require_opening_hand
```

- [ ] Add or extend tests in `tests/test_mulligan_plan.py`:

```python
def test_start_of_game_transform_is_not_opening_hand_keep_without_mulligan_claim():
    claim = {
        "card_id": "SW_448",
        "claim_kind": "hero_power_transform",
        "claim_readiness": "source_backed_static_semantics",
        "trust_ceiling": "runtime_candidate",
        "mechanic_family": "start_of_game",
        "claim": "If the deck has only Shadow spells, the starting hero power becomes Mind Spike.",
        "confidence": 0.99,
    }

    plan = build_mulligan_plan_from_claims([claim])

    assert "SW_448" not in plan["holds"]
```

- [ ] Add a companion test where an explicit `mulligan_keep` on the same start-of-game card is suppressed unless the existing project policy says explicit guide-backed mulligan advice wins. Preferred HSConfig policy for this plan: start-of-game deck-enabler effects do not require keeping the card; keep suppression remains active.

Expected assertion:

```python
assert suppressed["reason"] == "start_of_game_effect_does_not_require_opening_hand"
```

### Task 5: Preserve Effect Rows In Contracts And Card Behavior

- [ ] Verify `src/hsconfig/research_contract.py` keeps effect-bearing claims even when they do not become Mulligan anchors.
- [ ] Verify `src/hsconfig/gameplan_contract.py` keeps card-role/effect expectations for cards such as `SW_448`.
- [ ] Add a regression in `tests/test_archetype_source_fixtures.py` or `tests/test_claim_kind_runtime_contract.py`:

```python
def test_darkbishop_effect_remains_even_when_mulligan_keep_is_removed():
    artifacts = build_fixture_artifacts_for_shadow_priest()

    assert "SW_448" in artifacts["card_role_map"]
    assert artifacts["card_role_map"]["SW_448"]["claim_kind"] == "hero_power_transform"
    assert artifacts["mulligan_anchor_map"]["SW_448"]["intent"] != "hold"
```

- [ ] Use the real project fixture builder instead of creating a second fake fixture builder.
- [ ] If `card_role_map` does not store one `claim_kind`, assert against the nearest existing field that represents hero-power transform or start-of-game effect.
- [ ] Ensure the runtime config can still include per-card or contract evidence for `SW_448` without adding a Mulligan hold.

### Task 6: Normalize Guide Research Output To Emit Explicit Claim Kinds

- [ ] Modify `src/hsconfig/guide_research.py`.
- [ ] When guide research generates a true mulligan recommendation, emit:

```json
{
  "claim_kind": "mulligan_keep",
  "claim_readiness": "guide_backed",
  "trust_ceiling": "runtime_candidate"
}
```

or:

```json
{
  "claim_kind": "mulligan_discard",
  "claim_readiness": "guide_backed",
  "trust_ceiling": "runtime_candidate"
}
```

- [ ] When guide research generates a general card role, effect, package role, or gameplay priority, emit the corresponding non-mulligan claim kind:

```json
{"claim_kind": "card_role"}
{"claim_kind": "hero_power_transform"}
{"claim_kind": "mechanic_usage"}
{"claim_kind": "combo_sequence"}
{"claim_kind": "known_bad_pattern"}
```

- [ ] Do not map a generic sentence containing "keep pressure", "core", "key", "important", or "gameplan" to `mulligan_keep`.
- [ ] Add tests showing guide output can contain both:

```json
{"claim_kind": "hero_power_transform", "card_id": "SW_448"}
{"claim_kind": "mulligan_keep", "card_id": "ONE_DROP_ID"}
```

and that only the second one reaches `Mulligan.json`.

### Task 7: Research Evidence Package Cleanup

- [ ] Add:

```text
docs/research/2026-07-11-hsconfig-source-contract-logic-audit/README.md
```

Content:

```markdown
# HSConfig Source Contract Logic Audit

This research package records source-backed implementation evidence for the 2026-07-11 claim-kind runtime contract closure.

It is not operator guidance and it is not a runtime artifact.

Key conclusions:

- HearthRanger `Mulligan.json` is an explicit opening-hand keep/discard surface.
- Start-of-game deck effects do not imply the physical card should be kept in the opening hand.
- HearthstoneJSON is useful for card identity and static semantics, not guide strategy.
- Runtime lowering must use typed `claim_kind` values rather than broad guide text.
```

- [ ] Validate the research files with the existing research validator if it is available:

```powershell
python C:\Users\darbo\.codex\skills\research\validate_json.py -f docs\research\2026-07-11-hsconfig-source-contract-logic-audit\fields.yaml -j docs\research\2026-07-11-hsconfig-source-contract-logic-audit\results\Autonomous_guide_claim_contract_quality_model.json
python C:\Users\darbo\.codex\skills\research\validate_json.py -f docs\research\2026-07-11-hsconfig-source-contract-logic-audit\fields.yaml -j docs\research\2026-07-11-hsconfig-source-contract-logic-audit\results\HearthRanger_VisionAI_runtime_lowering_surfaces.json
python C:\Users\darbo\.codex\skills\research\validate_json.py -f docs\research\2026-07-11-hsconfig-source-contract-logic-audit\fields.yaml -j docs\research\2026-07-11-hsconfig-source-contract-logic-audit\results\Hearthstone_start-of-game_and_mulligan_semantics.json
```

- [ ] If the validator reports `Total fields: 0`, inspect `fields.yaml` and align it with the validator's expected shape. Do not change research conclusions to satisfy the validator; only fix field declaration shape.
- [ ] Add a small test if the repository already has research artifact tests. If none exist, do not add a large research test framework; keep this as command-based verification.

### Task 8: Documentation And Skill Sync

- [ ] Search active docs and skill files for language that suggests free-text guide claims can directly lower to Mulligan:

```powershell
rg -n "mulligan_and_gameplan|effect.*mulligan|important.*mulligan|core.*mulligan|claim_type" README.md docs src C:\Users\darbo\.codex\skills\hsconfig\SKILL.md
```

- [ ] Update only active docs that are operator-facing or skill-facing:

```text
README.md
docs/operator/README.md
docs/design.md
C:\Users\darbo\.codex\skills\hsconfig\SKILL.md
```

Use the exact policy:

```markdown
Runtime Mulligan writes require explicit `claim_kind` values such as `mulligan_keep` or `mulligan_discard`. Card importance, start-of-game effects, and guide gameplan text remain contract evidence unless they are separately backed by explicit Mulligan guidance.
```

- [ ] If the installed skill is generated from the repository, use the repository's existing sync script instead of editing both copies manually.
- [ ] Run the sync check:

```powershell
python scripts\sync_installed_skill.py --check
```

- [ ] If the check reports drift, run the repository's documented sync command and then rerun the check. Do not leave installed skill drift unresolved.

### Task 9: End-To-End ShadowPriest Config Regression

- [ ] Build a fresh ShadowPriest package through the normal HSConfig command surface, using the existing project CLI command names.
- [ ] Use the known input:

```text
Deckname: ShadowPriest
Deckcode: AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=
HSid: 2737726722
HDT-DeckId: c4c8b6b9-1d8e-4c07-a6cd-1c0de84f7602
```

- [ ] Verify generated operator artifacts show:

```text
SW_448 / Darkbishop Benedictus:
  effect or hero-power-transform evidence present
  opening-hand hold absent
  suppression or non-mulligan reason visible
```

- [ ] Verify generated `Mulligan.json` does not keep `SW_448` unless a true explicit mulligan source is added later.
- [ ] Verify generated JSON validates with the repository's current validator.
- [ ] Do not apply runtime config to HearthRanger as part of this task unless the implementation worker is already in a safe fake/apply test path and the user explicitly asks for a runtime apply.

### Task 10: Verification Suite

- [ ] Run targeted tests first:

```powershell
python -m pytest tests\test_claim_kind_runtime_contract.py -q
python -m pytest tests\test_source_document_builder.py tests\test_research_contract.py tests\test_gameplan_contract.py tests\test_mulligan_plan.py tests\test_archetype_source_fixtures.py -q
```

Expected:

```text
all selected tests pass
```

- [ ] Run skill/docs tests:

```powershell
python -m pytest tests\test_skill_files.py tests\test_skill_sync.py -q
```

Expected:

```text
all selected tests pass
```

- [ ] Run full tests:

```powershell
python -m pytest -q
```

Expected:

```text
all tests pass
```

- [ ] Run targeted source scans:

```powershell
rg -n "mulligan_and_gameplan" src tests README.md docs
rg -n "claim_kind.*claim_type|claim_type.*claim_kind|get\(\"claim_type\"" src\hsconfig
rg -n "Darkbishop|SW_448|hero_power_transform|start_of_game_effect_does_not_require_opening_hand" src tests docs
```

Expected:

- Any `mulligan_and_gameplan` match is either a regression test for legacy non-lowering or a historical artifact outside active operator guidance.
- Runtime-sensitive modules use the shared helper instead of broad ad-hoc fallback.
- Darkbishop/start-of-game handling is visible in tests.

- [ ] Check git:

```powershell
git status --short --branch
git diff --stat
```

Expected:

- Only intentional source, test, doc, skill, plan, and research files are changed.
- No runtime logs, replays, caches, or generated private evidence are staged.

---

## Acceptance Criteria

- Explicit `claim_kind="mulligan_keep"` creates a hold when readiness and trust allow it.
- Explicit `claim_kind="mulligan_discard"` creates a discard/avoid lane when readiness and trust allow it.
- Broad legacy `claim_type="mulligan_and_gameplan"` does not create a hold.
- Free-text claims containing "core", "important", "effect", "start of game", or "gameplan" do not create holds without explicit `claim_kind`.
- Darkbishop Benedictus / `SW_448` remains represented as a start-of-game hero-power-transform effect.
- Darkbishop Benedictus / `SW_448` is not kept in `Mulligan.json` by default.
- ShadowPriest config generation remains successful and no-block.
- Arbitrary deck generation remains no-block when guide evidence is weak or missing.
- Active docs and installed skill explain the source/contract/runtime boundary.
- Research package is committed as evidence with a README boundary.
- Full pytest suite passes.

---

## Files Expected To Change

Primary source files:

```text
src/hsconfig/source_document_model.py
src/hsconfig/source_document_builder.py
src/hsconfig/guide_research.py
src/hsconfig/mulligan_plan.py
src/hsconfig/research_contract.py
src/hsconfig/gameplan_contract.py
```

Test files:

```text
tests/test_claim_kind_runtime_contract.py
tests/test_source_document_builder.py
tests/test_research_contract.py
tests/test_gameplan_contract.py
tests/test_mulligan_plan.py
tests/test_archetype_source_fixtures.py
```

Docs and research:

```text
README.md
docs/operator/README.md
docs/design.md
docs/research/2026-07-11-hsconfig-source-contract-logic-audit/README.md
docs/research/2026-07-11-hsconfig-source-contract-logic-audit/outline.yaml
docs/research/2026-07-11-hsconfig-source-contract-logic-audit/fields.yaml
docs/research/2026-07-11-hsconfig-source-contract-logic-audit/results/Autonomous_guide_claim_contract_quality_model.json
docs/research/2026-07-11-hsconfig-source-contract-logic-audit/results/HearthRanger_VisionAI_runtime_lowering_surfaces.json
docs/research/2026-07-11-hsconfig-source-contract-logic-audit/results/Hearthstone_start-of-game_and_mulligan_semantics.json
C:\Users\darbo\.codex\skills\hsconfig\SKILL.md
```

If the implementation finds that a listed file does not exist or is not active in this repository, skip that file and record the reason in the final implementation summary. Do not create extra documentation layers to compensate.

---

## Rollback Plan

If the implementation destabilizes config generation:

1. Keep the tests that prove the desired source/contract behavior.
2. Revert only source changes that broke generation.
3. Restore the last passing runtime writer behavior.
4. Keep the research README and plan file.
5. Re-run the targeted test group to confirm the old runtime behavior is isolated.

Do not roll back user-created deck files or private runtime config directories.

# HSConfig Mechanic Lowering Parity Wave Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make HSConfig's mechanic understanding executable and consistent: every registered non-warning mechanic must either lower into a meaningful documented `CARDID.json` runtime row, require exact identity before lowering, or emit a clear non-blocking suppression reason. The operator must still be able to generate and apply a load-safe package for any deck.

**Architecture:** Keep HSConfig as a pre-run config generator. Add one mechanic lowering authority in `mechanic_support.py`, have the guide claim builder, CardID surface router, CardID compiler, readiness report, and operator summaries consume that authority. Do not add post-run tuning, log parsing, HSTuner behavior, or new undocumented runtime surfaces.

**Tech Stack:** Python standard library, existing HSConfig package, `pytest`, HearthRanger VisionAI documented runtime surfaces already represented in `visionai_registry.py`.

## Global Constraints

- HSConfig remains pre-run only: no Power.log, HDT replay, HSReplay, winrate, HSTuner, or post-run tuning logic.
- Preserve the no-block operator contract: warnings and report-only mechanics must never block package generation or load-safe apply.
- Preserve runtime safety: only write documented normal-path files (`GlobalValues.json`, `Mulligan.json`, `Combo.json` when source-backed, and per-card `<CARDID>.json`).
- Do not emit `Concede.json` or `Presume.json` on the normal path.
- Do not widen the deck fixture matrix in this wave. Use focused micro-fixtures and current representative tests.
- Do not make `GlobalValues.json` or `Combo.json` the generic escape hatch for mechanics that do not have a documented card behavior surface.
- Keep `SOURCE_BACKED_STRONG` and static semantics as confidence/source labels, not hard write gates.
- Warning-only mechanics stay visible, actionable, and non-blocking, but they do not fake runtime rows.
- Prefer small registry-driven refactors over broad rewrites.

---

## Current Diagnosis

The current repo has a split-brain mechanic model:

- `src/hsconfig/mechanic_support.py` describes many mechanics and their operator-visible support levels.
- `src/hsconfig/card_behavior_surface_router.py` separately hardcodes executable lowering through `ROLE_BLOCKS`, `MECHANIC_ROLE_MAP`, and `EXPLICIT_MECHANIC_RUNTIME_BLOCKS`.
- `src/hsconfig/compile_cardid.py` has a third fallback `ROLE_BLOCKS` map, so a role can still create a runtime row even if mechanic support says `warning_only`.
- `src/hsconfig/guide_claim_builder.py` creates static `mechanic_usage` claims from `MECHANIC_TEXT_MARKERS`, but this marker set does not match the current mechanic support registry.
- `src/hsconfig/config_readiness.py` only treats a small hardcoded subset as `MECHANIC_LOWERING_ROLES`, so cards can be reported as needing runtime surface even when the registry says the mechanic is lowerable.

The fix is not "more blocking". The fix is one executable registry and precise reporting:

- lowerable mechanics produce meaningful `CARDID.json` rows;
- identity-gated mechanics lower only when exact linked identity is known;
- warning-only mechanics emit suppression rows and visibility reports;
- any deck still reaches a load-safe output package.

---

## Public Behavior After This Wave

### Expected Normal Outcome

For a deck with mixed mechanics:

- `Mulligan.json` and `GlobalValues.json` are still generated load-safe.
- Per-card `<CARDID>.json` is generated for every card as before.
- Cards with lowerable mechanics receive meaningful behavior rows such as:
  - `BeforePlayCardBonus`
  - `OnBoardBonus`
  - `BeforePhysicalAttackBonus`
  - `BeforeBattlecryTargetBonus`
  - `BeforeOverkilledBonus`
  - `BeforeUseHeroPowerBonus`
  - `OnDiscoverCardBonus`
  - `OnChooseOneCardBonus`
- Cards with warning-only mechanics still get a load-safe card file with baseline `InHandPlayPriority`, plus explicit operator-visible suppression/report rows explaining why there is no richer runtime row.
- `operator_summary.json` remains the single operator gate and must not say the package is blocked only because a modern or unknown mechanic is report-only.

### Examples Of Intended Mechanic Policy

- `deathrattle`, `summon`, `reborn`, `taunt`, `aura`, `divine_shield`: lower to deploy or board-value posture (`BeforePlayCardBonus`, `OnBoardBonus`).
- `rush`, `charge`, `poisonous`, `honorable_kill`, `weapon`: lower to attack/play posture (`BeforePhysicalAttackBonus`, `BeforePlayCardBonus`), not exact trade/lethal math.
- `spellburst`, `quickdraw`, `finale`, `manathirst`, `infuse`, `corrupt`, `overload`, `excavate`, `plague`, `invoke`, `jade`, `cthun_package`, `spell_school`: lower to timing/deck posture only where already documented by card behavior or existing global posture rules.
- `discover` and `choose_one`: generic mechanic usage may lower to a generic documented surface, but option-specific choice rows (`discover_choice`, `choose_one_choice`) require exact linked option identity.
- `dredge`, `tradeable`, `forge`, `outcast`, `titan`, `starship`, `rewind`, `herald`, `shatter`, `board_position`, `generic_spell_target`, `location_activation`, `secret_timing`, `generated_entity_random_pool`: stay report-only unless a source-backed explicit card behavior block exists.

---

## Task 1: Add Executable Mechanic Lowering Contract

**Files:**

- `src/hsconfig/mechanic_support.py`
- `tests/test_mechanic_support.py`

**TDD First:**

- [ ] Add tests before implementation:
  - `test_every_cardid_surface_mechanic_has_lowering_policy`
  - `test_warning_only_mechanics_have_report_only_policy`
  - `test_static_claim_allowed_only_for_executable_or_identity_gated_mechanics`
  - `test_runtime_block_allowlist_matches_documented_card_behavior_blocks`

**Implementation:**

- [ ] Add a registry field named `lowering` to every `MECHANIC_SUPPORT` entry.
- [ ] Use this shape:

```python
"lowering": {
    "policy": "lowerable" | "identity_gated" | "report_only",
    "static_claim_allowed": True | False,
    "default_block": "BeforePlayCardBonus" | None,
    "allowed_blocks": ["BeforePlayCardBonus", "OnBoardBonus"],
    "default_value": "6",
    "default_condition": "*",
    "default_intent": "use_deathrattle_according_to_card_text",
    "suppression_reason": "tradeable_has_no_documented_runtime_block",
}
```

- [ ] Add public helpers:

```python
def mechanic_lowering_policy(mechanic: str) -> dict[str, Any]:
    ...

def mechanic_static_claim_allowed(mechanic: str) -> bool:
    ...

def mechanic_allowed_runtime_blocks(mechanic: str) -> set[str]:
    ...

def mechanic_default_runtime_block(mechanic: str) -> str | None:
    ...

def mechanic_report_only_reason(mechanic: str) -> str:
    ...

def mechanics_with_executable_lowering() -> set[str]:
    ...
```

- [ ] Normalize aliases through `ROLE_ALIASES` before lookup.
- [ ] Unknown mechanics must return a `report_only` policy with `suppression_reason="unregistered_mechanic_runtime_surface"`.
- [ ] Ensure every `allowed_blocks` entry is in `CARD_BEHAVIOR_BLOCKS` from `visionai_registry.py`.
- [ ] Preserve current `support_for_roles()`, `summarize_mechanic_support()`, and `summarize_mechanic_visibility()` outputs, adding lowering data only as extra fields.

**Acceptance:**

- [ ] `python -m pytest tests/test_mechanic_support.py` passes.
- [ ] No warning-only mechanic has a `default_block`.
- [ ] No direct/partial mechanic has `normal_path_surfaces` claiming a `CARDID.json:*` surface without either a lowerable or identity-gated lowering policy.

---

## Task 2: Make The Surface Router Consume The Registry

**Files:**

- `src/hsconfig/card_behavior_surface_router.py`
- `src/hsconfig/card_behavior_router.py` if wrapper expectations need updates
- `tests/test_card_behavior_router.py`

**TDD First:**

- [ ] Update or add tests:
  - `test_deathrattle_static_mechanic_lowers_without_explicit_block`
  - `test_rush_static_mechanic_lowers_to_attack_posture_without_explicit_block`
  - `test_tradeable_static_mechanic_stays_report_only`
  - `test_dredge_static_mechanic_stays_report_only`
  - `test_warning_only_mechanic_with_explicit_supported_block_stays_suppressed_unless_policy_allows_explicit_override`
  - `test_discover_choice_still_requires_resolved_option_identity`
  - `test_generic_discover_mechanic_keeps_documented_generic_surface`

**Implementation:**

- [ ] Remove or stop using the duplicate mechanic maps in `card_behavior_surface_router.py`:
  - `ROLE_BLOCKS`
  - `MECHANIC_ROLE_MAP`
  - `EXPLICIT_MECHANIC_RUNTIME_BLOCKS`
- [ ] Keep `INTENT_BLOCKS` for non-mechanic claim kinds.
- [ ] For `claim_kind == "mechanic_usage"`:
  - normalize `mechanic`;
  - fetch `policy = mechanic_lowering_policy(mechanic)`;
  - if `policy["policy"] == "report_only"`, suppress with `policy["suppression_reason"]`;
  - if an explicit `runtime_block` exists and it is not in `mechanic_allowed_runtime_blocks(mechanic)`, suppress with `unsupported_mechanic_runtime_block`;
  - if an explicit allowed block exists, emit it;
  - else emit `mechanic_default_runtime_block(mechanic)` when non-null;
  - use `policy["default_intent"]` or `f"use_{mechanic}_according_to_card_text"`;
  - use `policy["default_value"]` and `policy["default_condition"]` as defaults.
- [ ] Preserve resolved Discover/Choose One option behavior:
  - `discover_choice` and `choose_one_choice` rows still require identity links;
  - unresolved option identity remains suppressed with `unresolved_option_identity`;
  - generic `mechanic_usage: discover` remains a separate documented generic surface unless covered by a resolved option-specific row.
- [ ] Preserve `covered_by_resolved_choice_surface` behavior for generic Discover when a resolved choice row already covers the same card.
- [ ] Add the policy name and mechanic to suppression rows for report-only mechanics:

```python
{
    "claim_id": "...",
    "claim_kind": "mechanic_usage",
    "cards": ["CARD_ID"],
    "reason": "tradeable_has_no_documented_runtime_block",
    "mechanic": "tradeable",
    "lowering_policy": "report_only",
}
```

**Acceptance:**

- [ ] `python -m pytest tests/test_card_behavior_router.py` passes.
- [ ] Old behavior that lowered `dredge` through Discover fallback is replaced by report-only suppression.
- [ ] Old behavior that lowered `tradeable` through `BeforePlayCardBonus` is replaced by report-only suppression.
- [ ] Deathrattle/reborn/summon/rush/charge style claims no longer need an explicit `runtime_block` to emit a meaningful CardID row.

---

## Task 3: Expand Static Semantics Through The Registry

**Files:**

- `src/hsconfig/guide_claim_builder.py`
- `src/hsconfig/static_semantics.py` if existing static family extraction should be reused
- `tests/test_guide_claim_builder.py`
- `tests/test_static_semantic_micro_fixtures.py`

**TDD First:**

- [ ] Add tests:
  - `test_static_semantics_emit_deathrattle_mechanic_usage`
  - `test_static_semantics_emit_rush_and_charge_mechanic_usage`
  - `test_static_semantics_emit_spellburst_quickdraw_finale_manathirst_infuse_corrupt`
  - `test_static_semantics_do_not_emit_runtime_lowering_claim_for_tradeable`
  - `test_static_semantics_do_not_emit_runtime_lowering_claim_for_forge_outcast_titan_starship`
  - `test_existing_guide_claim_prevents_duplicate_static_claim`

**Implementation:**

- [ ] Replace `MECHANIC_TEXT_MARKERS` as the source of truth with a registry-backed marker map or static semantic family extraction.
- [ ] Static claim generation must call `mechanic_static_claim_allowed(mechanic)` before creating a `mechanic_usage` claim.
- [ ] Keep source-backed guide claims stronger than static semantic backfills.
- [ ] Do not generate static `mechanic_usage` claims for warning-only mechanics. They remain visible through `mechanic_support` and reports.
- [ ] Preserve special `hero_power_transform` detection for card text such as "Hero Power becomes" and "enter Shadowform".
- [ ] Ensure claim IDs remain deterministic.
- [ ] Keep claim confidence fields unchanged for static backfills:
  - `confidence="source_backed_static_semantics"`
  - `claim_readiness="source_backed_static_semantics"`
  - `trust_ceiling="static_semantics"`

**Acceptance:**

- [ ] `python -m pytest tests/test_guide_claim_builder.py tests/test_static_semantic_micro_fixtures.py` passes.
- [ ] Static semantics create more actionable claims for lowerable mechanics, but no additional hard block condition is introduced.

---

## Task 4: Synchronize CardID Compiler Fallbacks With The Registry

**Files:**

- `src/hsconfig/compile_cardid.py`
- `tests/test_compile_cardid.py`

**TDD First:**

- [ ] Add tests:
  - `test_compile_cardid_does_not_emit_tradeable_fallback_from_roles`
  - `test_compile_cardid_does_not_emit_dredge_fallback_from_roles`
  - `test_compile_cardid_emits_behavior_rows_from_router_for_lowerable_mechanics`
  - `test_compile_cardid_keeps_inhand_priority_for_report_only_cards`

**Implementation:**

- [ ] Remove the independent `ROLE_BLOCKS` mechanic fallback map or replace it with registry-backed `mechanic_default_runtime_block()`.
- [ ] Do not emit a mechanic fallback row when `mechanic_lowering_policy(role)["policy"] == "report_only"`.
- [ ] Continue to emit baseline `InHandPlayPriority` for every card.
- [ ] Continue to prefer explicit `behavior_rows` from the router over role fallback rows.
- [ ] Ensure warning-only roles do not produce fake meaningful runtime rows through compile fallback.

**Acceptance:**

- [ ] `python -m pytest tests/test_compile_cardid.py` passes.
- [ ] Warning-only cards still have load-safe card files.
- [ ] Runtime usefulness is driven by meaningful router rows, not by stale compiler role maps.

---

## Task 5: Make Readiness And Usefulness Registry-Driven

**Files:**

- `src/hsconfig/config_readiness.py`
- `src/hsconfig/config_usefulness.py`
- `src/hsconfig/operator_summary.py` if summary language needs policy names
- `tests/test_config_readiness.py`
- `tests/test_config_usefulness.py`
- `tests/test_operator_summary.py`

**TDD First:**

- [ ] Add tests:
  - `test_readiness_needs_mechanic_lowering_uses_registry`
  - `test_warning_only_mechanic_reports_warning_not_block`
  - `test_runtime_emitted_card_has_none_missing_link_when_router_row_exists`
  - `test_operator_summary_mentions_report_only_mechanics_without_blocking_apply`

**Implementation:**

- [ ] Replace `MECHANIC_LOWERING_ROLES` with `mechanics_with_executable_lowering()` from `mechanic_support.py`.
- [ ] Add report-only mechanic counts to existing summaries if not already present, reusing `summarize_mechanic_visibility()`.
- [ ] Preserve current readiness lanes:
  - `runtime_emitted`
  - `mulligan_only`
  - `globalvalues_only`
  - `report_only_supported`
  - `archetype_inferred`
  - `generic_low_confidence`
- [ ] Preserve current missing links, but ensure `needs_mechanic_lowering` means "registry says executable but no meaningful row was emitted", not "mechanic exists".
- [ ] Add a non-blocking explanation for report-only mechanics:

```json
{
  "non_blocking": true,
  "reason": "mechanic_report_only_by_documented_surface_policy"
}
```

**Acceptance:**

- [ ] `python -m pytest tests/test_config_readiness.py tests/test_config_usefulness.py tests/test_operator_summary.py` passes.
- [ ] A deck with only report-only mechanics can still reach `VALID_PACKAGE` when JSON/schema/load-safe checks pass.

---

## Task 6: Add A Mechanic Lowering Parity Micro-Fixture

**Files:**

- `tests/test_mechanic_lowering_parity.py` (new)
- `tests/fixtures/` only if a tiny fixture file is cleaner than inline data

**TDD First And Implementation Together:**

- [ ] Create a tiny inline deck fixture with these fake cards:
  - `CARD_DEATHRATTLE`: text contains Deathrattle
  - `CARD_RUSH`: text contains Rush
  - `CARD_SPELLBURST`: text contains Spellburst
  - `CARD_TRADEABLE`: text contains Tradeable
  - `CARD_DREDGE`: text contains Dredge
  - `CARD_DISCOVER`: text contains Discover
  - `CARD_CHOOSE_ONE`: text contains Choose One
- [ ] Build claims with `build_guide_claim_bundle()`.
- [ ] Route behavior with `route_card_behavior_surfaces()`.
- [ ] Compile CardID files with `compile_cardid_behaviors()`.
- [ ] Build readiness report with `build_config_readiness_report()` using minimal required inputs.

**Assertions:**

- [ ] Deathrattle, Rush, and Spellburst produce `meaningful_runtime_surface=True`.
- [ ] Tradeable and Dredge produce suppression rows with registry reasons and do not produce meaningful runtime surfaces.
- [ ] Discover generic behavior still produces a documented generic row, unless a resolved option-specific row covers it.
- [ ] Choose One option-specific row stays unresolved without identity links.
- [ ] Every card still has a compiled `<CARDID>.json` object with `GameCardId` and `InHandPlayPriority`.
- [ ] Readiness has no package-level block caused by warning-only mechanics.

**Acceptance:**

- [ ] `python -m pytest tests/test_mechanic_lowering_parity.py` passes.

---

## Task 7: Update Active Operator Docs Without Expanding Scope

**Files:**

- `docs/operator/README.md`
- `docs/operator/universal-wild-no-block-contract.md`
- `docs/research/current-truth.md`
- `C:\Users\darbo\.codex\skills\hsconfig\SKILL.md` only if the runtime/operator instruction is currently stale
- `tests/test_docs_active_path.py`
- `tests/test_skill_files.py`
- `tests/test_skill_sync.py`

**TDD First:**

- [ ] Add or update doc tests to assert:
  - active docs describe warning-only mechanics as non-blocking;
  - active docs do not promise fake lowerings for Dredge/Tradeable/Forge/etc.;
  - active docs mention the mechanic lowering registry as the authority;
  - active docs preserve the pre-run-only boundary.

**Implementation:**

- [ ] Add a short "Mechanic Lowering Policy" section to `docs/operator/README.md`.
- [ ] Update `universal-wild-no-block-contract.md` so "any deck works" means:
  - package generation does not block;
  - warning-only mechanics are visible and load-safe;
  - only documented VisionAI surfaces are emitted.
- [ ] Update `docs/research/current-truth.md` with the current authority:
  - `mechanic_support.py` is descriptive and executable lowering authority;
  - router/compiler/readiness consume it;
  - warning-only mechanics are non-blocking.
- [ ] Keep docs short. Do not copy large mechanic tables into multiple places.
- [ ] If `C:\Users\darbo\.codex\skills\hsconfig\SKILL.md` needs a sync, update only the short operator guidance and keep the skill slim.

**Acceptance:**

- [ ] `python -m pytest tests/test_docs_active_path.py tests/test_skill_files.py tests/test_skill_sync.py` passes.
- [ ] `rg -n "tradeable.*BeforePlayCardBonus|dredge.*OnDiscoverCardBonus" docs src tests` only returns intentional historical tests or no active false claims.

---

## Task 8: Verify Representative Deck Outputs Do Not Regress

**Files:**

- Existing representative tests only. Do not add a new large deck matrix.

**Verification Commands:**

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_shadowpriest_e2e.py tests/test_archetype_source_fixtures.py tests/test_universal_wild_no_block_matrix.py
python -m pytest tests/test_output_competence_matrix.py tests/test_supplemental_cute_warrior_load_safe.py
```

**Acceptance:**

- [ ] Representative decks still produce load-safe packages.
- [ ] `operator_summary.json` remains the gate.
- [ ] Report-only mechanics do not become hard blockers.
- [ ] No new runtime evidence, logs, replays, or generated private packages are committed.

---

## Task 9: Final Verification And Cleanup

**Commands:**

```powershell
cd C:\Users\darbo\Documents\HSConfig
python -m pip install -e .
$env:PYTHONPATH='src'
python -m pytest tests/test_mechanic_support.py tests/test_card_behavior_router.py tests/test_guide_claim_builder.py tests/test_static_semantic_micro_fixtures.py
python -m pytest tests/test_compile_cardid.py tests/test_config_readiness.py tests/test_config_usefulness.py tests/test_operator_summary.py tests/test_mechanic_lowering_parity.py
python -m pytest tests/test_docs_active_path.py tests/test_skill_files.py tests/test_skill_sync.py
python -m pytest
git status --short --branch
```

**Cleanup Checks:**

- [ ] Remove generated temp/runtime artifacts that are not intentional fixtures.
- [ ] Review `git diff --stat`.
- [ ] Review `git diff -- src/hsconfig tests docs C:/Users/darbo/.codex/skills/hsconfig/SKILL.md` when the skill file was touched.
- [ ] Confirm no raw runtime evidence or private logs were staged.
- [ ] Commit and push only after tests are green.

---

## Implementation Notes For Subagents

- Use one worker for `mechanic_support.py` registry and tests.
- Use one worker for router/compiler alignment.
- Use one worker for static semantics and guide claim builder.
- Use one worker for readiness/operator summary/docs.
- Use one reviewer after integration to search for duplicated stale mechanic maps.
- Do not let multiple workers edit the same file concurrently.

---

## Success Criteria

- The repo has exactly one active mechanic lowering authority.
- Static semantics, router, compiler, readiness, docs, and operator summary agree on that authority.
- More lowerable mechanics receive useful CardID behavior rows without requiring hand-authored explicit runtime blocks.
- Warning-only mechanics are visible, useful for review, and non-blocking.
- "Any deck works" remains true as a load-safe package promise, not as a false claim that every Hearthstone mechanic has a documented VisionAI runtime block.
- The skill stays narrow: deck in, guide/static/source-informed config out, no post-run tuning.

# HSConfig Guide Claim Depth Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make HSConfig produce a deep, source-backed HearthRanger CustomConfig package from deck input plus online/guide research, without being conservative or generic: real mulligan rules, meaningful CardID behavior, safe Combo rows, differentiated GlobalValues posture, hero power semantics, and clear reports explaining every supported, unsupported, and suppressed claim.

**Architecture:** Keep the repository slim by separating live research from deterministic compilation. The Codex skill performs online guide research and writes structured `claims.json` or `guide_sources.json`; the Python package validates, normalizes, enriches, routes, compiles, and audits those claims. If guide claims are absent, HSConfig still produces a non-empty static semantics bundle from HearthstoneJSON and documented card metadata, but marks guide-depth as low-confidence. Runtime JSON files contain only HearthRanger-compatible fields; provenance, confidence, and suppression reasons live in sidecar reports.

**Tech Stack:** Python 3.11+, stdlib JSON/pathlib/dataclasses/urllib, existing `hearthstone>=9.0.0`, pytest. No database, no queue, no headless browser inside the package. Codex/web research remains outside the package and feeds structured claim inputs.

---

## Current Findings To Preserve

- [ ] Treat the research packet at `C:\Users\darbo\Documents\HSConfig\docs\research\2026-07-06-hsconfig-guide-claim-depth\` as implementation evidence. It already contains validated outputs for:
  - `Autonomous_Guide_Claim_Builder`
  - `Mulligan_Depth_Closure`
  - `CardID_Behavior_Surface_Router`
  - `Combo_And_Sequencing_Closure`
  - `GlobalValues_Authority_Matrix`
  - `ShadowPriest_Evidence_Mapping_Example`
- [ ] Do not add HSTuner-style postrun analysis, winrate logic, replay parsing, or guarded runtime patching to HSConfig. HSConfig is Step-1 only: build an opinionated initial CustomConfig from deck identity, card metadata, and source-backed guide claims.
- [ ] Preserve the existing CLI shape: `prepare`, `build`, `research-contract`, `validate`, `apply`. Add flags and outputs rather than replacing commands.

## Task 1: Baseline Contract Tests

Create failing tests first. These tests define the new behavior before changing implementation.

- [ ] Create `C:\Users\darbo\Documents\HSConfig\tests\test_guide_claim_builder.py`.

  Required test cases:

  ```python
  from hsconfig.guide_claim_builder import build_guide_claim_bundle


  def test_builds_atomic_claims_from_structured_sources():
      cards = {
          "SW_448": {"name": "Darkbishop Benedictus", "text": "At the start of the game, if the spells in your deck are all Shadow, enter Shadowform."},
          "SW_446": {"name": "Mind Spike", "text": "Hero Power: Deal 2 damage."},
          "CORE_CS2_235": {"name": "Shadowform", "text": "Your Hero Power becomes 'Deal 2 damage'."},
      }
      sources = [
          {
              "source_url": "https://example.invalid/shadow-priest-guide",
              "source_title": "Shadow Priest Guide",
              "source_family": "guide",
              "retrieved_at": "2026-07-06T12:00:00Z",
              "claims": [
                  {
                      "claim_kind": "mulligan_keep",
                      "cards": ["SW_448"],
                      "stance": "keep",
                      "evidence_text_short": "Keep Darkbishop Benedictus in every opener.",
                      "source_confidence": "high",
                  }
              ],
          }
      ]

      bundle = build_guide_claim_bundle(
          deck_identity={"deck_name": "ShadowPriest"},
          card_metadata=cards,
          source_documents=sources,
      )

      claims = bundle["claims"]
      assert any(c["claim_kind"] == "mulligan_keep" and c["cards"] == ["SW_448"] for c in claims)
      assert any(c["claim_kind"] == "hero_power_transform" for c in claims)
      assert bundle["coverage"]["total_cards"] == 3
      assert bundle["coverage"]["guide_backed_cards"] == 1
      assert bundle["coverage"]["static_semantic_cards"] >= 1
  ```

  ```python
  from hsconfig.guide_claim_builder import build_guide_claim_bundle


  def test_vague_source_text_is_reported_not_promoted():
      bundle = build_guide_claim_bundle(
          deck_identity={"deck_name": "AnyDeck"},
          card_metadata={"CARD_001": {"name": "Example Card", "text": "Battlecry: Deal 2 damage."}},
          source_documents=[
              {
                  "source_url": "https://example.invalid/guide",
                  "source_title": "Guide",
                  "source_family": "guide",
                  "retrieved_at": "2026-07-06T12:00:00Z",
                  "claims": [
                      {
                          "claim_kind": "generic_advice",
                          "cards": [],
                          "stance": "play well",
                          "evidence_text_short": "Use your cards wisely and pressure when possible.",
                          "source_confidence": "medium",
                      }
                  ],
              }
          ],
      )

      assert bundle["claims"] == []
      assert bundle["unsupported_claims"][0]["reason"] == "not_card_specific"
  ```

- [ ] Create `C:\Users\darbo\Documents\HSConfig\tests\test_mulligan_plan.py`.

  Required test cases:

  ```python
  from hsconfig.mulligan_plan import build_mulligan_plan


  def test_mulligan_plan_has_concrete_keeps_before_wildcard_discard():
      claims = [
          {"claim_kind": "mulligan_keep", "cards": ["SW_448"], "stance": "keep", "claim_confidence": "high"},
          {"claim_kind": "mulligan_keep", "cards": ["CARD_002"], "stance": "keep", "claim_confidence": "medium"},
      ]

      plan = build_mulligan_plan(deck_name="ShadowPriest", claims=claims, card_roles={})

      assert [row["card"] for row in plan["rules"][:2]] == ["SW_448", "CARD_002"]
      assert plan["rules"][-1] == {"card": "*", "action": "discard", "reason": "discard_unlisted_cards_after_source_backed_keeps"}
      assert plan["quality"]["has_concrete_keeps"] is True
  ```

  ```python
  from hsconfig.mulligan_plan import build_mulligan_plan


  def test_mulligan_plan_blocks_lone_wildcard_discard():
      plan = build_mulligan_plan(deck_name="UnknownDeck", claims=[], card_roles={})

      assert plan["rules"] == []
      assert plan["quality"]["blocked_reason"] == "no_source_backed_mulligan_keeps"
  ```

- [ ] Create `C:\Users\darbo\Documents\HSConfig\tests\test_card_behavior_router.py`.

  Required test cases:

  ```python
  from hsconfig.card_behavior_router import route_card_behavior_claims


  def test_routes_targeting_claim_to_cardid_surface():
      claims = [
          {
              "claim_kind": "targeting_rule",
              "cards": ["DMF_090"],
              "stance": "prefer_enemy_hero",
              "conditions": {"phase": "burn"},
              "claim_confidence": "high",
              "source_refs": ["guide:1"],
          }
      ]

      routed = route_card_behavior_claims(claims)

      assert routed["card_rows"]["DMF_090"]
      assert routed["card_rows"]["DMF_090"][0]["surface"] == "CardID.json"
      assert routed["card_rows"]["DMF_090"][0]["intent"] == "prefer_enemy_hero"
      assert routed["suppressed"] == []
  ```

  ```python
  from hsconfig.card_behavior_router import route_card_behavior_claims


  def test_blocks_unsupported_claim_from_runtime_rows():
      routed = route_card_behavior_claims([
          {
              "claim_kind": "global_gameplan_advice",
              "cards": ["CARD_001"],
              "stance": "be aggressive",
              "claim_confidence": "medium",
          }
      ])

      assert routed["card_rows"] == {}
      assert routed["suppressed"][0]["reason"] == "no_documented_card_behavior_surface"
  ```

- [ ] Create `C:\Users\darbo\Documents\HSConfig\tests\test_combo_plan.py`.

  Required test cases:

  ```python
  from hsconfig.combo_plan import build_combo_plan


  def test_exact_sequence_claim_becomes_combo_plan():
      plan = build_combo_plan(
          deck_cards={"CARD_A", "CARD_B"},
          claims=[
              {
                  "claim_kind": "combo_sequence",
                  "cards": ["CARD_A", "CARD_B"],
                  "stance": "play_CARD_A_before_CARD_B",
                  "sequence": ["CARD_A", "CARD_B"],
                  "claim_confidence": "high",
                  "source_refs": ["guide:combo"],
              }
          ],
      )

      assert plan["combos"][0]["combo"] == "CARD_A>>CARD_B"
      assert plan["combos"][0]["value"] > 0
      assert plan["suppressed"] == []
  ```

  ```python
  from hsconfig.combo_plan import build_combo_plan


  def test_missing_deck_card_sequence_is_suppressed():
      plan = build_combo_plan(
          deck_cards={"CARD_A"},
          claims=[
              {
                  "claim_kind": "combo_sequence",
                  "cards": ["CARD_A", "CARD_MISSING"],
                  "sequence": ["CARD_A", "CARD_MISSING"],
                  "claim_confidence": "high",
              }
          ],
      )

      assert plan["combos"] == []
      assert plan["suppressed"][0]["reason"] == "sequence_card_not_in_deck"
  ```

- [ ] Create `C:\Users\darbo\Documents\HSConfig\tests\test_globalvalues_authority.py`.

  Required test cases:

  ```python
  from hsconfig.globalvalues_authority import build_globalvalues_authority_matrix


  def test_aggressive_posture_allows_selected_step1_keys():
      matrix = build_globalvalues_authority_matrix(
          aggression_profile="aggressive",
          claims=[{"claim_kind": "gameplan_posture", "stance": "aggressive", "claim_confidence": "high"}],
      )

      allowed = {row["key"] for row in matrix["allowed_step1_overlays"]}
      blocked = {row["key"] for row in matrix["blocked_until_runtime_evidence"]}
      assert "FirstTurnValueWeight" in allowed
      assert "SecondTurnValueWeight" in allowed
      assert "LowHpBoardValuePenalty" in blocked
  ```

- [ ] Create `C:\Users\darbo\Documents\HSConfig\tests\test_shadowpriest_depth_e2e.py`.

  Required test behavior:
  - Run the normal build path with a ShadowPriest fixture source pack.
  - Assert `claims.json` or `guide_claim_bundle.json` is non-empty.
  - Assert `Mulligan.json` has at least two concrete card rows before any wildcard discard.
  - Assert `CardID.json` includes more than `InHandPlayPriority` for at least one source-backed behavior claim.
  - Assert `Combo.json`, when emitted, contains only HearthRanger runtime keys: `comment`, `condition`, `combo`, `value`.
  - Assert provenance exists in sidecars, not runtime rows.

  Suggested fixture location:

  `C:\Users\darbo\Documents\HSConfig\tests\fixtures\shadowpriest_guide_sources.json`

  Suggested fixture content:

  ```json
  [
    {
      "source_url": "https://example.invalid/shadow-priest-guide",
      "source_title": "Shadow Priest Guide Fixture",
      "source_family": "guide_fixture",
      "retrieved_at": "2026-07-06T12:00:00Z",
      "claims": [
        {
          "claim_kind": "mulligan_keep",
          "cards": ["SW_448"],
          "stance": "keep",
          "evidence_text_short": "Keep Darkbishop Benedictus because it enables the Shadow Priest hero power package.",
          "source_confidence": "high"
        },
        {
          "claim_kind": "mulligan_keep",
          "cards": ["BAR_311"],
          "stance": "keep",
          "evidence_text_short": "Keep early pressure one-drops in aggressive Shadow Priest mulligans.",
          "source_confidence": "medium"
        },
        {
          "claim_kind": "targeting_rule",
          "cards": ["SW_446"],
          "stance": "prefer_enemy_hero",
          "conditions": {"posture": "aggressive_burn"},
          "evidence_text_short": "Mind Spike is primarily face pressure in aggressive Shadow Priest unless board survival requires a trade.",
          "source_confidence": "medium"
        }
      ]
    }
  ]
  ```

## Task 2: Implement Guide Claim Builder

- [ ] Create `C:\Users\darbo\Documents\HSConfig\src\hsconfig\guide_claim_builder.py`.

  Required public API:

  ```python
  from __future__ import annotations

  from dataclasses import dataclass
  from hashlib import sha256
  from typing import Any


  SUPPORTED_CLAIM_KINDS = {
      "mulligan_keep",
      "mulligan_discard",
      "card_role",
      "targeting_rule",
      "combo_sequence",
      "gameplan_posture",
      "hero_power_transform",
      "mechanic_usage",
  }


  @dataclass(frozen=True)
  class ClaimBuildResult:
      claims: list[dict[str, Any]]
      unsupported_claims: list[dict[str, Any]]
      coverage: dict[str, Any]
      source_evidence_index: list[dict[str, Any]]


  def build_guide_claim_bundle(
      *,
      deck_identity: dict[str, Any],
      card_metadata: dict[str, dict[str, Any]],
      source_documents: list[dict[str, Any]] | None = None,
  ) -> dict[str, Any]:
      ...
  ```

  Required behavior:
  - Normalize every supported source claim into an atomic claim.
  - Reject non-card-specific runtime-affecting claims with `reason="not_card_specific"`.
  - Reject unsupported claim kinds with `reason="unsupported_claim_kind"`.
  - Add deterministic static semantic claims for:
    - hero power transform cards if card text contains "Hero Power becomes" or "enter Shadowform".
    - Battlecry, Deathrattle, Discover, Dredge, Tradeable, Overload, Freeze, Lifesteal, Taunt, Rush, Charge, Secret, Location, Weapon, Silence, Transform, Destroy, Discard when detectable in card text.
  - Mark static claims with `source_family="hearthstonejson_static_semantics"` and `claim_confidence="medium"` unless an exact source claim upgrades them.
  - Build `coverage` with:
    - `total_cards`
    - `guide_backed_cards`
    - `static_semantic_cards`
    - `uncovered_cards`
    - `claim_kinds`
  - Build `source_evidence_index` with `source_ref`, `source_url`, `source_title`, `source_family`, `retrieved_at`, and `claim_count`.
  - Include `evidence_hash=sha256(evidence_text_short.encode("utf-8")).hexdigest()[:16]` when evidence text exists.

- [ ] Modify `C:\Users\darbo\Documents\HSConfig\src\hsconfig\guide_research.py`.

  Required change:
  - Keep `normalize_source_claims` as a backwards-compatible wrapper.
  - Delegate structured claim construction to `guide_claim_builder.build_guide_claim_bundle`.
  - Do not perform live web search inside `guide_research.py`.

- [ ] Run:

  ```powershell
  Set-Location C:\Users\darbo\Documents\HSConfig
  $env:PYTHONPATH='src'
  python -m pytest tests/test_guide_claim_builder.py -q
  ```

  Expected result: all tests in `test_guide_claim_builder.py` pass.

- [ ] Commit after green:

  ```powershell
  git add src/hsconfig/guide_claim_builder.py src/hsconfig/guide_research.py tests/test_guide_claim_builder.py
  git commit -m "feat: add guide claim builder"
  ```

## Task 3: Integrate Claim Builder Into CLI Prepare

- [ ] Modify `C:\Users\darbo\Documents\HSConfig\src\hsconfig\cli.py`.

  Required CLI additions:
  - Add `--guide-sources-json` to `prepare`.
  - Preserve `--claims-json`.
  - If `--claims-json` is present, load it and normalize through the builder.
  - If `--guide-sources-json` is present, pass it to `build_guide_claim_bundle`.
  - If neither is present, call `build_guide_claim_bundle` with `source_documents=[]` so static semantics still exist.

  Required artifact additions under the prepared output folder:
  - `guide_claim_bundle.json`
  - `source_evidence_index.json`
  - `claim_coverage_report.json`
  - `unsupported_claims_report.json`

  Required command output additions:
  - JSON field `guide_claims_count`
  - JSON field `guide_backed_cards`
  - JSON field `uncovered_cards_count`

- [ ] Update `C:\Users\darbo\Documents\HSConfig\tests\test_prepare_cli.py`.

  Required tests:
  - `prepare --guide-sources-json tests/fixtures/shadowpriest_guide_sources.json` writes the four new artifacts.
  - `prepare` without guide sources still writes static semantic claims for ShadowPriest hero power transform when card metadata provides the relevant text.
  - Unsupported source claims are reported but do not fail the command.

- [ ] Run:

  ```powershell
  Set-Location C:\Users\darbo\Documents\HSConfig
  $env:PYTHONPATH='src'
  python -m pytest tests/test_prepare_cli.py tests/test_guide_claim_builder.py -q
  ```

  Expected result: prepare integration tests pass.

- [ ] Commit after green:

  ```powershell
  git add src/hsconfig/cli.py tests/test_prepare_cli.py tests/fixtures/shadowpriest_guide_sources.json
  git commit -m "feat: wire guide claims into prepare"
  ```

## Task 4: Add Mulligan Plan And Fix Lone Wildcard Discard

- [ ] Create `C:\Users\darbo\Documents\HSConfig\src\hsconfig\mulligan_plan.py`.

  Required public API:

  ```python
  from __future__ import annotations

  from typing import Any


  def build_mulligan_plan(
      *,
      deck_name: str,
      claims: list[dict[str, Any]],
      card_roles: dict[str, Any],
  ) -> dict[str, Any]:
      ...
  ```

  Required behavior:
  - Source-backed `mulligan_keep` claims create concrete `{"card": card_id, "action": "hold", "reason": ...}` rows.
  - `mulligan_discard` claims create concrete discard rows.
  - Role-based fallback may create low-confidence hold rows only for early-game anchors with explicit `role` in `{"one_drop", "early_pressure", "early_curve", "mulligan_anchor"}`.
  - Wildcard discard is appended only when at least one concrete hold row exists.
  - If no concrete holds exist, set `quality.blocked_reason="no_source_backed_mulligan_keeps"` and emit no wildcard discard.
  - De-duplicate by card id while preserving source-backed rows before role-fallback rows.

- [ ] Modify `C:\Users\darbo\Documents\HSConfig\src\hsconfig\compile_mulligan.py`.

  Required behavior:
  - Consume `mulligan_plan` when available.
  - Runtime `Mulligan.json` rows contain only HearthRanger-compatible action data.
  - Write sidecar `mulligan_plan_report.json` during build or prepare output.
  - Preserve existing behavior only when no `mulligan_plan` is supplied and there are existing anchors.
  - Remove the unconditional `* discard` append.

- [ ] Modify `C:\Users\darbo\Documents\HSConfig\src\hsconfig\validate_package.py`.

  Required validation:
  - Fail or warn with `lone_wildcard_discard` if `Mulligan.json` contains only wildcard discard.
  - Accept wildcard discard when at least one concrete hold appears before it.

- [ ] Run:

  ```powershell
  Set-Location C:\Users\darbo\Documents\HSConfig
  $env:PYTHONPATH='src'
  python -m pytest tests/test_mulligan_plan.py tests/test_compile_mulligan.py -q
  ```

  Expected result: mulligan plan tests pass and old unconditional wildcard behavior is gone.

- [ ] Commit after green:

  ```powershell
  git add src/hsconfig/mulligan_plan.py src/hsconfig/compile_mulligan.py src/hsconfig/validate_package.py tests/test_mulligan_plan.py tests/test_compile_mulligan.py
  git commit -m "feat: deepen mulligan planning"
  ```

## Task 5: Add Card Behavior Surface Router

- [ ] Create `C:\Users\darbo\Documents\HSConfig\src\hsconfig\card_behavior_router.py`.

  Required public API:

  ```python
  from __future__ import annotations

  from typing import Any


  def route_card_behavior_claims(claims: list[dict[str, Any]]) -> dict[str, Any]:
      ...
  ```

  Required routing table:
  - `targeting_rule` with `stance="prefer_enemy_hero"` routes to `CardID.json` intent `prefer_enemy_hero`.
  - `targeting_rule` with `stance="prefer_enemy_minion"` routes to `CardID.json` intent `prefer_enemy_minion`.
  - `mechanic_usage` with card-specific Battlecry/Deathrattle/Discover/Dredge/Tradeable/Overload/Freeze/Weapon/Secret/Location routes to reportable `CardID.json` candidate rows only if there is a documented and implemented local row builder.
  - `card_role` routes to low-confidence `InHandPlayPriority` only when no stronger card-specific row exists.
  - `global_gameplan_advice`, vague posture, and non-card-specific claims route to `suppressed` with `reason="no_documented_card_behavior_surface"`.

- [ ] Modify `C:\Users\darbo\Documents\HSConfig\src\hsconfig\compile_cardid.py`.

  Required behavior:
  - Prefer router output over role-only behavior.
  - Emit `CardID.json` rows from routed claims.
  - Keep existing role fallback, but mark it as fallback in `card_behavior_plan_report.json`.
  - Runtime rows must not include `source_refs`, `claim_confidence`, or evidence text.
  - Sidecar report must include `source_refs`, `claim_confidence`, `intent`, `surface`, `suppression_reason`.

- [ ] Modify `C:\Users\darbo\Documents\HSConfig\src\hsconfig\surface_intent.py` only if the current intent vocabulary cannot represent `prefer_enemy_hero`, `prefer_enemy_minion`, `prefer_friendly_minion`, `hold_for_combo`, and `avoid_play_without_target`.

- [ ] Run:

  ```powershell
  Set-Location C:\Users\darbo\Documents\HSConfig
  $env:PYTHONPATH='src'
  python -m pytest tests/test_card_behavior_router.py tests/test_compile_cardid.py -q
  ```

  Expected result: CardID router tests pass and runtime `CardID.json` contains meaningful rows beyond generic in-hand priority when claims support them.

- [ ] Commit after green:

  ```powershell
  git add src/hsconfig/card_behavior_router.py src/hsconfig/compile_cardid.py src/hsconfig/surface_intent.py tests/test_card_behavior_router.py tests/test_compile_cardid.py
  git commit -m "feat: route guide claims to card behavior surfaces"
  ```

## Task 6: Add Combo Sequence Contract

- [ ] Create `C:\Users\darbo\Documents\HSConfig\src\hsconfig\combo_plan.py`.

  Required public API:

  ```python
  from __future__ import annotations

  from typing import Any


  def build_combo_plan(
      *,
      deck_cards: set[str],
      claims: list[dict[str, Any]],
  ) -> dict[str, Any]:
      ...
  ```

  Required behavior:
  - Promote only `combo_sequence` claims with an explicit ordered `sequence`.
  - Suppress claims when any sequence card is missing from the current deck.
  - Suppress claims when sequence length is less than 2.
  - Suppress vague synergy claims with `reason="missing_ordered_sequence"`.
  - Convert `["CARD_A", "CARD_B"]` to `combo="CARD_A>>CARD_B"`.
  - Runtime combo rows contain only: `comment`, `condition`, `combo`, `value`.
  - Provenance and confidence go to `combo_plan_report.json`.

- [ ] Modify `C:\Users\darbo\Documents\HSConfig\src\hsconfig\compile_combo.py`.

  Required behavior:
  - Use `combo_plan` when available.
  - Remove provenance fields from runtime `Combo.json` rows.
  - Keep existing `>>` and `>->` support for runtime syntax.
  - Add validation that runtime combo rows do not contain unknown keys.

- [ ] Run:

  ```powershell
  Set-Location C:\Users\darbo\Documents\HSConfig
  $env:PYTHONPATH='src'
  python -m pytest tests/test_combo_plan.py tests/test_compile_combo.py -q
  ```

  Expected result: exact sequences compile; vague or missing-card claims are suppressed with explicit reasons.

- [ ] Commit after green:

  ```powershell
  git add src/hsconfig/combo_plan.py src/hsconfig/compile_combo.py tests/test_combo_plan.py tests/test_compile_combo.py
  git commit -m "feat: add source-backed combo planning"
  ```

## Task 7: Add GlobalValues Authority Matrix

- [ ] Create `C:\Users\darbo\Documents\HSConfig\src\hsconfig\globalvalues_authority.py`.

  Required public API:

  ```python
  from __future__ import annotations

  from typing import Any


  def build_globalvalues_authority_matrix(
      *,
      aggression_profile: str,
      claims: list[dict[str, Any]],
  ) -> dict[str, Any]:
      ...
  ```

  Required policy:
  - Step1 may adjust posture-level keys when source-backed:
    - `FirstTurnValueWeight`
    - `SecondTurnValueWeight`
    - early pressure or board pressure keys already present in the default config template
  - Step1 must not claim runtime evidence for:
    - low HP penalties
    - opponent-specific matchup tuning
    - post-apply regression tuning
    - exact numeric rollback or winrate decisions
  - Every changed GlobalValues key must have:
    - `authority="step1_source_backed_posture"` or `authority="baseline_default"`
    - `claim_refs`
    - `reason`
  - Runtime-only keys must be written to `global_values_blocked_changes.json`, not silently ignored.

- [ ] Modify `C:\Users\darbo\Documents\HSConfig\src\hsconfig\compile_globalvalues.py`.

  Required behavior:
  - Read the authority matrix.
  - Apply only allowed Step1 overlays.
  - Emit `global_values_authority_matrix.json`.
  - Emit `global_values_blocked_changes.json`.
  - Keep generated `GlobalValues.json` valid even when no guide-backed posture exists.

- [ ] Run:

  ```powershell
  Set-Location C:\Users\darbo\Documents\HSConfig
  $env:PYTHONPATH='src'
  python -m pytest tests/test_globalvalues_authority.py tests/test_compile_globalvalues.py -q
  ```

  Expected result: aggressive posture can change documented Step1 keys, while runtime-only numeric tuning is reported as blocked.

- [ ] Commit after green:

  ```powershell
  git add src/hsconfig/globalvalues_authority.py src/hsconfig/compile_globalvalues.py tests/test_globalvalues_authority.py tests/test_compile_globalvalues.py
  git commit -m "feat: add global values authority matrix"
  ```

## Task 8: Wire Plans Through Research And Gameplan Contracts

- [ ] Modify `C:\Users\darbo\Documents\HSConfig\src\hsconfig\research_contract.py`.

  Required additions:
  - Include `guide_claim_bundle`.
  - Include `mulligan_plan`.
  - Include `card_behavior_plan`.
  - Include `combo_plan`.
  - Include `global_values_authority_matrix`.
  - Preserve existing fields for backwards compatibility.

- [ ] Modify `C:\Users\darbo\Documents\HSConfig\src\hsconfig\gameplan_contract.py`.

  Required additions:
  - Add `card_expectations` keyed by card id.
  - Add `hero_power_expectations` for transformed hero powers such as Mind Spike.
  - Add `source_backed_actions` and `static_semantic_actions`.
  - Add `unsupported_or_review_only_claims`.
  - Keep low-confidence generic roles only as fallback, never as the only explanation when a guide claim exists.

- [ ] Modify `C:\Users\darbo\Documents\HSConfig\src\hsconfig\cli.py`.

  Required build order inside prepare/build:
  1. Load deck identity and card metadata.
  2. Build guide claim bundle.
  3. Build research contract.
  4. Build gameplan contract.
  5. Build mulligan plan.
  6. Build card behavior plan.
  7. Build combo plan.
  8. Build global values authority matrix.
  9. Compile runtime JSON files.
  10. Validate runtime package.
  11. Write reports.

- [ ] Add tests to `C:\Users\darbo\Documents\HSConfig\tests\test_cli.py`.

  Required assertions:
  - `prepare` produces all plan reports.
  - `build` consumes plan reports rather than rebuilding inconsistent defaults.
  - `validate` fails on malformed runtime rows but accepts valid report sidecars.

- [ ] Run:

  ```powershell
  Set-Location C:\Users\darbo\Documents\HSConfig
  $env:PYTHONPATH='src'
  python -m pytest tests/test_cli.py tests/test_prepare_cli.py tests/test_shadowpriest_depth_e2e.py -q
  ```

  Expected result: end-to-end contract wiring passes.

- [ ] Commit after green:

  ```powershell
  git add src/hsconfig/research_contract.py src/hsconfig/gameplan_contract.py src/hsconfig/cli.py tests/test_cli.py tests/test_prepare_cli.py tests/test_shadowpriest_depth_e2e.py
  git commit -m "feat: wire guide depth through config contracts"
  ```

## Task 9: Update HSConfig Skill Instructions

- [ ] Locate the installed HSConfig skill file. Expected locations to check:

  ```powershell
  Test-Path C:\Users\darbo\.codex\skills\hsconfig\SKILL.md
  Test-Path C:\Users\darbo\Documents\HSConfig\skills\hsconfig\SKILL.md
  rg --files C:\Users\darbo\Documents\HSConfig | rg "SKILL.md$"
  ```

- [ ] Modify the active HSConfig `SKILL.md`.

  Required workflow:
  - For every new deck, Codex must perform online guide research before invoking `hsconfig prepare`.
  - Codex writes a structured guide source file under the deck session output, not into runtime CustomConfig.
  - Codex passes that file via `--guide-sources-json`.
  - Codex must inspect generated reports before telling the user the config is ready.
  - Codex must call out when the package is static-semantics-only or guide-backed.

  Required wording:

  ```md
  Normal deck build flow:
  1. Resolve deck identity and card metadata.
  2. Research current guide/archetype/card-usage sources.
  3. Write structured guide sources with card-specific claims.
  4. Run `hsconfig prepare --guide-sources-json ...`.
  5. Verify `claim_coverage_report.json`, `mulligan_plan_report.json`, `card_behavior_plan_report.json`, `combo_plan_report.json`, and `global_values_authority_matrix.json`.
  6. Apply only after validation is green.
  ```

- [ ] Create or update `C:\Users\darbo\Documents\HSConfig\docs\operator\guide-research-policy.md`.

  Required sections:
  - Accepted source types: official card text, HearthstoneJSON metadata, archetype guide, matchup guide, mulligan guide, card-specific gameplay discussion.
  - Rejected source types: vague tier-list blurbs, non-card-specific advice, stale claims that contradict current card text.
  - How to write structured source claims.
  - How unsupported claims appear in reports.

- [ ] Update `C:\Users\darbo\Documents\HSConfig\README.md`.

  Required changes:
  - Keep README short.
  - State that live research is performed by Codex/skill and compiled by HSConfig.
  - Link to `docs/operator/guide-research-policy.md`.
  - Avoid claiming HSConfig proves gameplay improvement or winrate.

- [ ] Add or update tests:
  - `C:\Users\darbo\Documents\HSConfig\tests\test_skill_docs.py`
  - Assert the active docs mention `--guide-sources-json`.
  - Assert docs do not say HSConfig performs replay analysis, winrate proof, or postrun tuning.

- [ ] Run:

  ```powershell
  Set-Location C:\Users\darbo\Documents\HSConfig
  $env:PYTHONPATH='src'
  python -m pytest tests/test_skill_docs.py -q
  ```

  Expected result: skill/docs tests pass.

- [ ] Commit after green:

  ```powershell
  git add README.md docs/operator/guide-research-policy.md tests/test_skill_docs.py
  git add C:\Users\darbo\.codex\skills\hsconfig\SKILL.md
  git commit -m "docs: clarify guide-backed config workflow"
  ```

  If the active skill file is outside the repo and should not be committed, commit the repo docs only and mention the external skill path in the final verification.

## Task 10: Validate ShadowPriest Fresh Build

- [ ] Remove only the generated ShadowPriest output package in the HSConfig workspace. Do not delete source code, docs, tests, or unrelated runtime folders.

  Use `rg --files` first to locate generated package paths:

  ```powershell
  Set-Location C:\Users\darbo\Documents\HSConfig
  rg --files | rg "ShadowPriest|2737726722|c4c8b6b9"
  ```

- [ ] Build a fresh ShadowPriest guide source file for test validation under a generated session folder, using current online research if the executing agent has web access. If web access is unavailable, use `tests/fixtures/shadowpriest_guide_sources.json` and mark the session report as fixture-backed.

- [ ] Run the normal command with the provided deck identity:

  ```powershell
  Set-Location C:\Users\darbo\Documents\HSConfig
  $env:PYTHONPATH='src'
  python -m hsconfig prepare `
    --deck-name ShadowPriest `
    --deck-code "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=" `
    --hs-id 2737726722 `
    --hdt-deck-id c4c8b6b9-1d8e-4c07-a6cd-1c0de84f7602 `
    --guide-sources-json tests\fixtures\shadowpriest_guide_sources.json `
    --json
  ```

- [ ] Inspect the produced package:

  Required checks:
  - `guide_claim_bundle.json` has guide-backed claims.
  - `claim_coverage_report.json` reports no silent unknown state.
  - `Mulligan.json` has concrete holds before wildcard discard.
  - `CardID.json` has meaningful card-specific rows beyond only `InHandPlayPriority`.
  - `Combo.json` exists only when exact source-backed combo sequence exists.
  - `GlobalValues.json` reflects posture overlays and `global_values_authority_matrix.json` explains every changed key.
  - Runtime files do not contain provenance fields.

- [ ] Run package validation:

  ```powershell
  Set-Location C:\Users\darbo\Documents\HSConfig
  $env:PYTHONPATH='src'
  python -m hsconfig validate --deck-name ShadowPriest --json
  ```

  Expected result: validation succeeds, or reports only non-runtime-blocking guide coverage warnings.

- [ ] Commit fixture and generated-example changes only if they are intended repo artifacts. Do not commit local HearthRanger runtime files.

## Task 11: Full Verification

- [ ] Run focused tests:

  ```powershell
  Set-Location C:\Users\darbo\Documents\HSConfig
  $env:PYTHONPATH='src'
  python -m pytest `
    tests/test_guide_claim_builder.py `
    tests/test_mulligan_plan.py `
    tests/test_card_behavior_router.py `
    tests/test_combo_plan.py `
    tests/test_globalvalues_authority.py `
    tests/test_shadowpriest_depth_e2e.py `
    -q
  ```

  Expected result: all focused tests pass.

- [ ] Run full suite:

  ```powershell
  Set-Location C:\Users\darbo\Documents\HSConfig
  $env:PYTHONPATH='src'
  python -m pytest -q
  ```

  Expected result: all tests pass.

- [ ] Run docs/code scan over README, docs, source, and tests for stale capability claims and placeholder markers.

  Expected result:
  - No claims that HSConfig performs winrate proof, replay analysis, or postrun tuning.
  - No placeholder-marker comments in active docs/code.
  - Any mention of HSTuner is only a boundary statement saying HSConfig does not do HSTuner work.

- [ ] Review diff:

  ```powershell
  Set-Location C:\Users\darbo\Documents\HSConfig
  git diff --stat
  git diff -- src tests docs README.md
  git status --short --branch
  ```

  Expected result:
  - Changes are scoped to HSConfig guide depth.
  - No raw runtime evidence, logs, HearthRanger private files, or generated cache files are staged.

- [ ] Final commit if any uncommitted verified changes remain:

  ```powershell
  git add README.md docs src tests pyproject.toml
  git commit -m "feat: deepen guide-backed config generation"
  ```

- [ ] Push only after tests and diff review are green:

  ```powershell
  git push origin main
  ```

## Acceptance Criteria

- [ ] A deck build can start from deck identity plus structured guide research and produce a guide-backed config package.
- [ ] ShadowPriest no longer produces only shallow `InHandPlayPriority` plus default mulligan output when guide claims are available.
- [ ] `Mulligan.json` never contains a lone wildcard discard.
- [ ] `CardID.json` behavior is routed from claim intent, not only generic role fallback.
- [ ] `Combo.json` is emitted only for exact deck-present ordered sequences and contains only runtime-compatible keys.
- [ ] `GlobalValues.json` uses a documented authority matrix and does not pretend to have runtime evidence.
- [ ] Hero power transform semantics such as Darkbishop Benedictus / Mind Spike are represented in contracts and reports.
- [ ] Runtime JSON is clean; provenance and confidence are sidecars.
- [ ] Docs and skill instructions make Codex responsible for online research and HSConfig responsible for deterministic compilation.
- [ ] Full pytest suite passes.

## Plan Self-Review

- [ ] The plan covers every gap found in the guide-claim-depth research packet.
- [ ] The plan does not add replay parsing, postrun tuning, winrate validation, or HSTuner orchestration to HSConfig.
- [ ] The plan keeps live web research out of brittle package internals while still making the Codex skill perform guide research before compilation.
- [ ] The plan is aggressive enough for the user's goal because it requires all cards to receive either a guide-backed claim, static semantic claim, or explicit uncovered status.
- [ ] The plan is implementation-ready because every task names exact files, tests, commands, outputs, and commit boundaries.

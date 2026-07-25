# HSConfig ShadowPriest VisionAI Semantic Surface Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make HSConfig's generated HearthRanger VisionAI CustomConfig output semantically tight for ShadowPriest and future Wild decks: every emitted runtime key must be backed by the right source claim, non-runtime mechanics must stay diagnostic, no default-only runtime surface may survive, and the generated package must remain `SOURCE_BACKED_STRONG`.

**Architecture:** Keep the existing source-to-contract-to-runtime pipeline. Add narrow policy gates where the current pipeline over-lowers evidence into VisionAI runtime blocks: battlecry targeting, effect-only start-of-game cards, report-only combos, and static metadata mechanics. Do not add a new planner, tuner, or Hearthstone simulator.

**Tech Stack:** Python, pytest, existing HSConfig modules under `src/hsconfig`, existing generated package reports, existing operator summary contract.

## Global Constraints

- Work only in `C:\Users\darbo\Documents\HSConfig`.
- Start by making the repo current and confirming the branch state:
  ```powershell
  git fetch --all --prune --tags
  git status --short --branch
  python scripts/check_hsconfig_currentness.py --cwd . --json
  ```
- Keep the final worktree clean after implementation, verification, commit, and push if this is executed as a full development task.
- Do not use HSTuner for this change. HSConfig is the only operator workflow.
- Do not tune from game outcome logs in this plan. The premise is: HSConfig creates the best static config, and HearthRanger performs gameplay decisions.
- Do not add backups, generated temp artifacts, runtime logs, HDT exports, `Power.log`, `.hdtreplay`, `.hsreplay`, or private runtime evidence to git.
- Runtime writes remain gated through the existing HSConfig apply path only.
- `reports/operator_summary.json` remains the operator authority.
- `SOURCE_BACKED_STRONG` is the required source-backed status for a usable package.
- Do not invent unsupported HearthRanger VisionAI keys.
- Do not express exact in-turn sequencing, minion target selection, or location activation unless the existing VisionAI surface supports it directly and the source claim is specific enough.
- Keep the solution small: prefer role aliasing, surface gating, and report hygiene over broad rewrites.

---

## Desired Final Behavior

For the ShadowPriest deck:

```text
Deckname: ShadowPriest
Deckcode: AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=
HSid: 2737726722
HDT-DeckId: c4c8b6b9-1d8e-4c07-a6cd-1c0de84f7602
```

The generated package must satisfy:

- `operator_summary.json.semantic_status == "SOURCE_BACKED_STRONG"`.
- `operator_summary.json.source_backed_status == "SOURCE_BACKED_STRONG"`.
- `operator_summary.json.default_only_runtime_surfaces == []`.
- `operator_summary.json.runtime_apply_allowed == true`.
- `operator_summary.json.source_status_apply_blocking == false`.
- `SW_448` Darkbishop Benedictus is treated as an effect/enabler card, not a card-body keep or card-body play priority. Its start-of-game/Shadowform value must not create generic `InHandPlayPriority` or generic `BeforePlayCardBonus`.
- `GVG_009` Shadowbomber and `SW_444` Twilight Deceptor must not get `BeforeBattlecryTargetBonus` from generic non-targeted Battlecry evidence.
- `NX2_019` Mind Sear may receive play/burn priority, but must not invent an unsupported exact minion targeting rule.
- `REV_290` Cathedral of Atonement may receive a play/tempo priority, while activation/targeting remains report-only unless a supported VisionAI surface is explicitly available.
- `SW_446` Voidtouched Attendant remains high priority as a board aura/damage amplifier.
- Untimed or suppressed combo claims do not create expected `Combo.json` rows, card-level runtime gaps, or `combo_gap` as the first usefulness gap.
- Internal/static tags such as `deckbuilding_modifier`, `start_of_game_keyword`, `start_of_game_modifier`, `passive_start_effect`, `shadowform`, and `trigger_visual` do not appear as warning-only unsupported mechanics.

---

## Task 1: Add Regression Tests For VisionAI Surface Semantics

- [ ] Create `tests/test_shadowpriest_visionai_semantic_surface_contract.py`.
- [ ] Add shared constants:
  ```python
  SHADOWPRIEST_DECK_CODE = (
      "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/"
      "KgG17oG1cEGAAA="
  )
  SHADOWPRIEST_DECK_NAME = "ShadowPriest"
  ```
- [ ] Add a helper that generates a fresh package in `tmp_path` using the existing CLI/generator path used by current package tests. Reuse existing test helpers if a package generation helper already exists in the suite. The helper must return:
  - package root
  - `reports/operator_summary.json`
  - `reports/card_behavior_plan_report.json`
  - `reports/semantic_enrichment_report.json`
  - `reports/source_to_runtime_explainability.json`
- [ ] Add this exact package-level assertion test:
  ```python
  def test_shadowpriest_package_is_source_backed_strong_without_default_only_surfaces(shadowpriest_package):
      package_root, reports = shadowpriest_package
      operator = reports["operator_summary"]

      assert operator["technical_status"] == "VALID_PACKAGE"
      assert operator["semantic_status"] == "SOURCE_BACKED_STRONG"
      assert operator["source_backed_status"] == "SOURCE_BACKED_STRONG"
      assert operator["runtime_apply_allowed"] is True
      assert operator["source_status_apply_blocking"] is False
      assert operator["default_only_runtime_surfaces"] == []
      assert operator["source_backed_strong_closure"]["status"] == "ready"
  ```
- [ ] Add this exact semantic-runtime assertion test:
  ```python
  def test_shadowpriest_runtime_rows_match_card_semantics(shadowpriest_package):
      package_root, reports = shadowpriest_package

      shadowbomber = read_card_json(package_root, "GVG_009")
      twilight_deceptor = read_card_json(package_root, "SW_444")
      darkbishop = read_card_json(package_root, "SW_448")
      mind_sear = read_card_json(package_root, "NX2_019")
      cathedral = read_card_json(package_root, "REV_290")
      voidtouched = read_card_json(package_root, "SW_446")

      assert "BeforeBattlecryTargetBonus" not in shadowbomber
      assert "BeforeBattlecryTargetBonus" not in twilight_deceptor

      assert "BeforeUseHeroPowerBonus" in darkbishop
      assert "InHandPlayPriority" not in darkbishop
      assert "BeforePlayCardBonus" not in darkbishop

      assert "BeforePlayCardBonus" in mind_sear
      assert "BeforeBattlecryTargetBonus" not in mind_sear

      assert "BeforePlayCardBonus" in cathedral
      assert "BeforeBattlecryTargetBonus" not in cathedral
      assert "BeforeUseHeroPowerBonus" not in cathedral

      assert "OnBoardBoardBonus" in voidtouched
      assert "BeforePlayCardBonus" in voidtouched
  ```
- [ ] Add this exact report hygiene assertion test:
  ```python
  def test_shadowpriest_report_only_claims_do_not_create_runtime_gaps(shadowpriest_package):
      package_root, reports = shadowpriest_package
      operator = reports["operator_summary"]

      usefulness = operator["config_usefulness"]
      explainability = operator["source_to_runtime_explainability_summary"]
      mechanic_visibility = operator["mechanic_visibility_summary"]

      assert usefulness["first_usefulness_gap"] != "combo_gap"
      assert usefulness["combo_expected"] is False
      assert usefulness["combo_row_count"] == 0
      assert explainability["cards_with_first_missing_link"] == 0

      warning_only = set(mechanic_visibility["warning_only_mechanics"])
      assert "location_activation" in warning_only
      assert "deckbuilding_modifier" not in warning_only
      assert "passive_start_effect" not in warning_only
      assert "shadowform" not in warning_only
      assert "start_of_game_keyword" not in warning_only
      assert "start_of_game_modifier" not in warning_only
      assert "trigger_visual" not in warning_only
  ```
- [ ] Add `read_card_json(package_root, card_id)` inside the test file:
  ```python
  def read_card_json(package_root, card_id):
      path = package_root / "CardID" / f"{card_id}.json"
      with path.open("r", encoding="utf-8") as handle:
          return json.load(handle)
  ```

Run:

```powershell
pytest tests/test_shadowpriest_visionai_semantic_surface_contract.py -q
```

Expected result before implementation: at least one failure for generic Battlecry target rows, Darkbishop generic body priority, combo/report-only gap hygiene, or static mechanic warning noise.

---

## Task 2: Stop Generic Battlecry From Lowering To Target Bonus

- [ ] Modify `src/hsconfig/mechanic_support.py`.
- [ ] Change the `battlecry` mechanic support policy so the normal default runtime surface is `BeforePlayCardBonus`, not `BeforeBattlecryTargetBonus`.
- [ ] Keep `BeforeBattlecryTargetBonus` in the allowed/normal path list only for explicit target-backed claims or explicitly requested behavior rows.
- [ ] Add or update a unit test in `tests/test_card_behavior_surface_router.py`:
  ```python
  def test_non_targeted_battlecry_routes_to_play_bonus_not_target_bonus():
      claim = {
          "claim_id": "c-battlecry-non-targeted",
          "claim_kind": "mechanic_usage",
          "card_ids": ["GVG_009"],
          "mechanic": "battlecry",
          "evidence_text_short": "Battlecry: Deal 3 damage to each hero.",
          "source_refs": ["fixture://shadowbomber"],
      }

      report = route_card_behavior_surfaces([claim])
      rows = report["rows"]

      assert len(rows) == 1
      assert rows[0]["card_id"] == "GVG_009"
      assert rows[0]["behavior_block"] == "BeforePlayCardBonus"
  ```
- [ ] Add or update a second unit test:
  ```python
  def test_explicit_targeted_battlecry_can_still_route_to_target_bonus():
      claim = {
          "claim_id": "c-battlecry-targeted",
          "claim_kind": "card_behavior",
          "card_ids": ["CARD_TARGETED"],
          "intent": "prefer_enemy_minion_target",
          "runtime_block": "BeforeBattlecryTargetBonus",
          "evidence_text_short": "Battlecry: Deal damage to a minion.",
          "source_refs": ["fixture://targeted"],
      }

      report = route_card_behavior_surfaces([claim])
      rows = report["rows"]

      assert len(rows) == 1
      assert rows[0]["card_id"] == "CARD_TARGETED"
      assert rows[0]["behavior_block"] == "BeforeBattlecryTargetBonus"
  ```

Run:

```powershell
pytest tests/test_card_behavior_surface_router.py -q
pytest tests/test_shadowpriest_visionai_semantic_surface_contract.py -q
```

---

## Task 3: Split Effect-Only Start-Of-Game Value From Physical Card Priority

- [ ] Modify `src/hsconfig/compile_cardid.py`.
- [ ] Add this helper near existing role and fallback helpers:
  ```python
  EFFECT_ONLY_START_OF_GAME_ROLES = {
      "deckbuilding_modifier",
      "hero_power_transform",
      "passive_start_effect",
      "shadowform",
      "start_of_game",
      "start_of_game_keyword",
      "start_of_game_modifier",
  }

  BODY_AUTHORITY_ROLES = {
      "body_pressure",
      "board_tempo",
      "mulligan_anchor",
      "playable_body",
      "tempo_body",
  }

  def _is_effect_only_start_of_game_card(roles: Iterable[str]) -> bool:
      role_set = {str(role) for role in roles if role}
      if not role_set.intersection(EFFECT_ONLY_START_OF_GAME_ROLES):
          return False
      if role_set.intersection(BODY_AUTHORITY_ROLES):
          return False
      return "hero_power_transform" in role_set or "shadowform" in role_set
  ```
- [ ] Apply the helper only to automatic generic rows:
  - Skip automatic `InHandPlayPriority` for effect-only start-of-game cards.
  - Skip automatic generic `BeforePlayCardBonus` from pressure/combo roles for effect-only start-of-game cards.
  - Do not suppress explicit behavior rows already supplied by source claims.
  - Do not suppress `BeforeUseHeroPowerBonus`.
- [ ] Add or update a unit test in `tests/test_compile_cardid.py`:
  ```python
  def test_effect_only_darkbishop_keeps_hero_power_bonus_without_body_priority():
      contract = {
          "deck_name": "ShadowPriest",
          "cards": {
              "SW_448": {
                  "name": "Darkbishop Benedictus",
                  "roles": [
                      "deckbuilding_modifier",
                      "hero_power_transform",
                      "passive_start_effect",
                      "pressure",
                      "shadowform",
                      "start_of_game_keyword",
                  ],
                  "source_claim_ids": ["claim-darkbishop-effect"],
                  "confidence": "source_backed",
                  "behavior_rows": [
                      {
                          "behavior_block": "BeforeUseHeroPowerBonus",
                          "condition": "*",
                          "value": "10",
                          "comment": "ShadowPriest: SW_448_enable_shadow_hero_power",
                          "source_claim_ids": ["claim-darkbishop-effect"],
                      }
                  ],
              }
          },
      }

      card_files = compile_cardid_behaviors(contract)
      darkbishop = card_files["SW_448"]

      assert "BeforeUseHeroPowerBonus" in darkbishop
      assert "InHandPlayPriority" not in darkbishop
      assert "BeforePlayCardBonus" not in darkbishop
  ```
- [ ] Add a guard test proving explicit body evidence is preserved:
  ```python
  def test_explicit_body_behavior_row_is_not_removed_for_effect_only_card():
      contract = {
          "deck_name": "ShadowPriest",
          "cards": {
              "SW_448": {
                  "name": "Darkbishop Benedictus",
                  "roles": ["hero_power_transform", "shadowform"],
                  "source_claim_ids": ["claim-effect", "claim-body"],
                  "behavior_rows": [
                      {
                          "behavior_block": "BeforePlayCardBonus",
                          "condition": "*",
                          "value": "4",
                          "comment": "ShadowPriest: explicit_body_source",
                          "source_claim_ids": ["claim-body"],
                      }
                  ],
              }
          },
      }

      card_files = compile_cardid_behaviors(contract)

      assert "BeforePlayCardBonus" in card_files["SW_448"]
  ```

Run:

```powershell
pytest tests/test_compile_cardid.py -q
pytest tests/test_shadowpriest_visionai_semantic_surface_contract.py -q
```

---

## Task 4: Make Untimed Combo Claims Report-Only, Not Runtime-Expected

- [ ] Modify `src/hsconfig/surface_intent.py`.
- [ ] Replace the current truthy `contract.get("combos")` optional `Combo.json` behavior with a lowerability helper:
  ```python
  def _combo_claim_is_runtime_lowerable(combo: Mapping[str, Any]) -> bool:
      if combo.get("suppressed_reason"):
          return False
      if combo.get("runtime_lowering_status") in {"emitted", "runtime_lowered"}:
          return True
      if combo.get("runtime_surface") == "Combo.json":
          return True
      timing = str(combo.get("timing") or combo.get("sequence_timing") or "").strip()
      cards = combo.get("cards") or combo.get("card_ids") or []
      return timing in {"same_turn", "ordered", "exact_order"} and len(cards) >= 2
  ```
- [ ] Only add `Combo.json` as an optional runtime surface when at least one combo satisfies `_combo_claim_is_runtime_lowerable`.
- [ ] Modify `src/hsconfig/source_to_runtime_explainability.py` so suppressed or non-lowerable combo claims do not create card-level `runtime_surface` missing links.
- [ ] Modify `src/hsconfig/config_usefulness.py` so:
  - `combo_expected` means at least one runtime-lowerable combo is expected.
  - `combo_row_count` remains the number of emitted runtime combo rows.
  - `suppressed_combo_claim_count` remains diagnostic.
  - `first_usefulness_gap` is not `combo_gap` when all combo claims are report-only or suppressed for missing timing.
- [ ] Add or update `tests/test_surface_intent.py`:
  ```python
  def test_report_only_combo_does_not_make_combo_surface_expected():
      contract = {
          "deck_name": "ShadowPriest",
          "cards": {},
          "combos": [
              {
                  "claim_id": "combo-report-only",
                  "cards": ["DS1_233", "VAC_419"],
                  "suppressed_reason": "missing_timing",
              }
          ],
      }

      intent = build_surface_intent(contract)

      assert "Combo.json" not in intent.get("required_surfaces", [])
      assert "Combo.json" not in intent.get("optional_surfaces", [])
  ```
- [ ] Add or update `tests/test_config_usefulness.py`:
  ```python
  def test_report_only_combo_claim_is_diagnostic_not_usefulness_gap():
      report = build_config_usefulness_report(
          expected_combo_count=0,
          emitted_combo_count=0,
          suppressed_combo_claim_count=1,
          missing_runtime_links=[],
      )

      assert report["combo_expected"] is False
      assert report["combo_row_count"] == 0
      assert report["suppressed_combo_claim_count"] == 1
      assert report["first_usefulness_gap"] != "combo_gap"
  ```

Run:

```powershell
pytest tests/test_surface_intent.py tests/test_source_to_runtime_explainability.py tests/test_config_usefulness.py -q
pytest tests/test_shadowpriest_visionai_semantic_surface_contract.py -q
```

---

## Task 5: Normalize Static Metadata Mechanics Out Of Warning-Only Buckets

- [ ] Modify `src/hsconfig/mechanic_support.py`.
- [ ] Add these role aliases:
  ```python
  ROLE_ALIASES.update(
      {
          "deckbuilding_modifier": "start_of_game",
          "passive_start_effect": "start_of_game",
          "shadowform": "hero_power_transform",
          "start_of_game_keyword": "start_of_game",
          "start_of_game_modifier": "start_of_game",
      }
  )
  ```
- [ ] Add `trigger_visual` to the existing diagnostic/non-mechanic role skip set. It is static display metadata, not a runtime mechanic.
- [ ] Keep `location_activation` warning-only unless a supported VisionAI activation surface exists in the project.
- [ ] Add or update `tests/test_mechanic_support.py`:
  ```python
  def test_static_metadata_roles_do_not_create_warning_only_noise():
      roles = [
          "deckbuilding_modifier",
          "passive_start_effect",
          "shadowform",
          "start_of_game_keyword",
          "start_of_game_modifier",
          "trigger_visual",
          "location_activation",
      ]

      rows = support_for_roles(roles)
      by_role = {row["role"]: row for row in rows}

      assert by_role["deckbuilding_modifier"]["support_bucket"] != "warning_only"
      assert by_role["passive_start_effect"]["support_bucket"] != "warning_only"
      assert by_role["shadowform"]["support_bucket"] != "warning_only"
      assert by_role["start_of_game_keyword"]["support_bucket"] != "warning_only"
      assert by_role["start_of_game_modifier"]["support_bucket"] != "warning_only"
      assert "trigger_visual" not in by_role
      assert by_role["location_activation"]["support_bucket"] == "warning_only"
  ```

Run:

```powershell
pytest tests/test_mechanic_support.py -q
pytest tests/test_shadowpriest_visionai_semantic_surface_contract.py -q
```

---

## Task 6: Add A Package-Level VisionAI Semantic Surface Audit

- [ ] Modify `src/hsconfig/config_quality_contract.py`.
- [ ] Add a quality check named `visionai_semantic_surface`.
- [ ] The check must inspect generated `CardID/*.json`, `reports/card_behavior_plan_report.json`, and source-backed contract metadata.
- [ ] The check must return this shape:
  ```json
  {
    "status": "clean",
    "non_targeted_battlecry_target_rows": [],
    "effect_only_body_rows": [],
    "unsupported_report_only_runtime_rows": [],
    "semantic_default_runtime_rows": []
  }
  ```
- [ ] The check fails with `status: "failed"` when:
  - `BeforeBattlecryTargetBonus` is emitted for a row whose evidence is only non-targeted Battlecry.
  - An effect-only start-of-game card receives generated `InHandPlayPriority` or generated generic `BeforePlayCardBonus`.
  - A report-only mechanic such as location activation receives a made-up runtime block.
  - A runtime row has only `semantic_default` as its reason while a card-specific source classification exists.
- [ ] Add `visionai_semantic_surface` to the existing quality report summary consumed by `operator_summary.json`.
- [ ] Add this assertion to the ShadowPriest package test:
  ```python
  def test_shadowpriest_quality_report_has_clean_visionai_semantic_surface_check(shadowpriest_package):
      package_root, reports = shadowpriest_package
      quality = reports["operator_summary"]["config_quality"]
      check = quality["checks"]["visionai_semantic_surface"]

      assert check["status"] == "clean"
      assert check["non_targeted_battlecry_target_rows"] == []
      assert check["effect_only_body_rows"] == []
      assert check["unsupported_report_only_runtime_rows"] == []
      assert check["semantic_default_runtime_rows"] == []
  ```

Run:

```powershell
pytest tests/test_shadowpriest_visionai_semantic_surface_contract.py -q
pytest tests/test_config_quality_contract.py -q
```

---

## Task 7: Update Operator Documentation And Skill Contract

- [ ] Modify `docs/operator/universal-wild-no-block-contract.md`.
- [ ] Add a short section named `VisionAI Semantic Surface Rules`:
  ```md
  ## VisionAI Semantic Surface Rules

  HSConfig only emits runtime keys that are both source-backed and semantically compatible with the HearthRanger VisionAI surface.

  - Non-targeted Battlecry evidence lowers to play timing, not target bonus.
  - Target bonus surfaces require explicit target evidence.
  - Start-of-game and deckbuilding effects are effect value, not automatic hand/body priority.
  - Report-only mechanics remain diagnostic and do not create missing runtime gaps.
  - Locations may receive play priority, while activation semantics stay warning-only until a supported runtime surface exists.
  ```
- [ ] Modify `C:\Users\darbo\.codex\skills\hsconfig\SKILL.md`.
- [ ] Add a compact operator rule under the generation workflow:
  ```md
  - Treat `SOURCE_BACKED_STRONG` as necessary but not sufficient: the generated package must also pass the VisionAI semantic surface audit. Do not emit target, combo, location, or hand-priority keys from source text that does not semantically support that runtime surface.
  ```
- [ ] Do not add generated package artifacts to docs.

Run:

```powershell
pytest tests/test_shadowpriest_visionai_semantic_surface_contract.py -q
```

---

## Task 8: Regenerate ShadowPriest And Verify The Full Contract

- [ ] Regenerate the ShadowPriest package using the normal HSConfig command path. Use the existing documented command in `C:\Users\darbo\.codex\skills\hsconfig\SKILL.md` and target a disposable output directory under the repo test/output area that is already gitignored.
- [ ] Inspect the generated runtime JSON:
  ```powershell
  Get-Content .\outputs\<shadowpriest-output>\04_package\CardID\SW_448.json
  Get-Content .\outputs\<shadowpriest-output>\04_package\CardID\GVG_009.json
  Get-Content .\outputs\<shadowpriest-output>\04_package\CardID\SW_444.json
  Get-Content .\outputs\<shadowpriest-output>\04_package\CardID\NX2_019.json
  Get-Content .\outputs\<shadowpriest-output>\04_package\CardID\REV_290.json
  Get-Content .\outputs\<shadowpriest-output>\04_package\CardID\SW_446.json
  ```
- [ ] Inspect the summary:
  ```powershell
  Get-Content .\outputs\<shadowpriest-output>\04_package\reports\operator_summary.json
  ```
- [ ] Confirm:
  - `SW_448` has `BeforeUseHeroPowerBonus`.
  - `SW_448` does not have automatic `InHandPlayPriority`.
  - `SW_448` does not have automatic generic `BeforePlayCardBonus`.
  - `GVG_009` does not have `BeforeBattlecryTargetBonus`.
  - `SW_444` does not have `BeforeBattlecryTargetBonus`.
  - `NX2_019` keeps `BeforePlayCardBonus`.
  - `REV_290` keeps `BeforePlayCardBonus` and has no invented activation block.
  - `SW_446` keeps aura/play pressure rows.
  - `operator_summary.json` is `SOURCE_BACKED_STRONG`.
  - `default_only_runtime_surfaces` is empty.
  - `config_quality.checks.visionai_semantic_surface.status` is `clean`.

Run the focused verification:

```powershell
pytest tests/test_card_behavior_surface_router.py tests/test_compile_cardid.py tests/test_surface_intent.py tests/test_mechanic_support.py tests/test_shadowpriest_visionai_semantic_surface_contract.py -q
```

Run the full project verification:

```powershell
pytest -q
python scripts/check_hsconfig_currentness.py --cwd . --json
git status --short --branch
```

The final `git status --short --branch` must show a clean worktree after commit/push if the implementation is completed in the same execution task.

---

## Acceptance Criteria

- [ ] ShadowPriest package generation succeeds.
- [ ] Package technical status is `VALID_PACKAGE`.
- [ ] Package semantic/source-backed status is `SOURCE_BACKED_STRONG`.
- [ ] No default-only runtime surfaces exist.
- [ ] Non-targeted Battlecry cards do not receive target-bonus keys.
- [ ] Darkbishop Benedictus is represented as effect/hero-power value, not a card-body keep or generic body play priority.
- [ ] Report-only combos do not create expected `Combo.json` gaps.
- [ ] Static metadata mechanics are not warning-only noise.
- [ ] Real unsupported action mechanics, such as location activation, remain visible as warning-only/report-only.
- [ ] VisionAI semantic surface audit exists and passes.
- [ ] Documentation and hsconfig skill instructions reflect the new contract.
- [ ] Focused tests pass.
- [ ] Full test suite passes.
- [ ] Repo is current and clean after the implementation is committed.

---

## Rollback Plan

- Revert only the implementation commit if the new policy causes a broader regression.
- The rollback must remove:
  - battlecry default surface change
  - effect-only start-of-game automatic row suppression
  - report-only combo gap hygiene
  - mechanic alias/static metadata warning cleanup
  - visionai semantic surface quality check
  - associated tests and docs
- Do not revert unrelated HSConfig changes or generated runtime evidence.

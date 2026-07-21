# HSConfig Semantic Intent Scoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve HSConfig's generated CardID behavior rows by adding a deterministic semantic intent scorer that assigns stronger, card-specific runtime values from source-backed claim content, while preserving existing source/contract authority, no-default-only guarantees, and lean runtime JSON output.

**Architecture:** Add one pure scoring module used by `card_behavior_surface_router.py` after a claim has already been accepted for a meaningful CardID runtime surface. The scorer only chooses a bounded value and report metadata. It does not decide source status, does not unlock suppressed mechanics, does not parse logs, and does not change apply authority. Explicit `runtime_value` or `value` from source/guide claims remains authoritative and always wins. Runtime `CARDID.json` files remain clean because `compile_cardid.py` already renders only `comment`, `condition`, and `value`.

**Tech Stack:** Python 3.11, Python stdlib, existing HSConfig package, pytest, existing JSON package reports. No new dependencies.

## Global Constraints

- Work only in `C:\Users\darbo\Documents\HSConfig`.
- Start by refreshing repository state:
  ```powershell
  cd C:\Users\darbo\Documents\HSConfig
  git fetch --all --prune --tags
  python scripts\check_hsconfig_currentness.py --cwd . --json
  git status --short --branch
  git log -1 --oneline
  ```
- Expected currentness before edits:
  ```json
  {
    "ahead_origin_main": 0,
    "behind_origin_main": 0,
    "branch": "main",
    "clean_for_runtime_work": true,
    "dirty": false,
    "upstream": "origin/main"
  }
  ```
- Do not use HSTuner.
- Do not parse HearthRanger logs, Hearthstone logs, HDT files, winrate output, replay output, or runtime evidence for this implementation.
- Do not add post-game tuning, candidate promotion, runtime patching, or log-derived values to HSConfig.
- Do not write to `C:\Users\darbo\Desktop\HS` in this plan.
- Do not add new normal runtime surfaces. Normal HSConfig output remains `GlobalValues.json`, `Mulligan.json`, per-card `<CARDID>.json`, and `Combo.json` only when exact source-backed combo timing exists.
- Do not create `Presume.json` or `Concede.json` in normal packages.
- Do not add `Darkbishop Benedictus` (`SW_448`) as a Mulligan keep unless a future explicit opening-hand source claim says to keep the card. Its current value is the start-of-game hero power transform effect, not the physical card in hand.
- Preserve `SOURCE_BACKED_STRONG` as an evidence-quality label, not a package generation or apply gate.
- Preserve `reports/operator_summary.json` as the normal apply authority.
- Preserve no-default-only guarantees: a package must not be promoted as strong by generic defaults alone.
- Runtime rows must stay lean: every emitted runtime value row contains only `comment`, `condition`, and `value`.
- Scoring metadata is diagnostic-only and belongs in reports such as `reports/card_behavior_plan_report.json`.
- If code changes pass verification, commit them so the final worktree is clean.

---

## File Structure

- Create: `src/hsconfig/semantic_intent_score.py`
  - Responsibility: pure deterministic scoring from an already accepted behavior claim to a bounded value and explanation metadata.
- Create: `tests/test_semantic_intent_score.py`
  - Responsibility: unit coverage for explicit value authority, ShadowPriest-style damage patterns, location tempo, hero power transform, and fallback behavior.
- Modify: `src/hsconfig/card_behavior_surface_router.py`
  - Responsibility: call the scorer while attaching behavior fields to accepted CardID rows.
- Modify: `tests/test_card_behavior_router.py`
  - Responsibility: router integration coverage that score metadata appears in plan rows and explicit values remain unchanged.
- Modify: `tests/test_compile_cardid.py`
  - Responsibility: guard that diagnostic scoring fields do not leak into runtime JSON rows.
- Modify: `tests/test_shadowpriest_e2e.py`
  - Responsibility: ShadowPriest package proof that `SW_448` remains effect-only, Mind Sear and source-backed behavior rows remain present, and package reports carry scoring metadata.
- Modify: `tests/test_universal_wild_no_block_matrix.py`
  - Responsibility: representative Wild matrix remains non-blocking and default-only clean after scoring is introduced.
- Read-only verification: `src/hsconfig/source_document_model.py`
  - Responsibility: source status and claim-kind runtime contract stay authoritative and unchanged.
- Read-only verification: `src/hsconfig/compile_cardid.py`
  - Responsibility: runtime writer continues to strip all row metadata except `comment`, `condition`, and `value`.

---

### Task 1: Add Semantic Intent Scorer Unit Tests

**Files:**
- Create: `tests/test_semantic_intent_score.py`

**Interfaces:**
- Imports: `score_card_behavior_claim`, `SemanticIntentScore`
- Consumes: accepted claim dictionaries, target behavior block, intent, roles, default value.
- Produces: value strings and diagnostic metadata only.

- [ ] **Step 1: Create `tests/test_semantic_intent_score.py` with focused red tests**

  ```python
  from hsconfig.semantic_intent_score import SemanticIntentScore, score_card_behavior_claim


  def test_explicit_runtime_value_is_authoritative():
      claim = {
          "claim_kind": "targeting_rule",
          "cards": ["NX2_019"],
          "runtime_value": "8",
          "stance": "prefer_enemy_minion",
          "evidence_text_short": (
              "Mind Sear deals 2 damage to a minion and deals 3 damage "
              "to the enemy hero if it dies."
          ),
      }

      score = score_card_behavior_claim(
          claim,
          behavior_block="BeforeBattlecryTargetBonus",
          intent="prefer_enemy_minion",
          roles=["prefer_enemy_minion"],
          value_default="6",
      )

      assert isinstance(score, SemanticIntentScore)
      assert score.value == "8"
      assert score.band == "explicit"
      assert score.reason == "explicit_runtime_value"
      assert score.profile == "source_claim"


  def test_conditional_minion_death_burn_scores_above_generic_default():
      claim = {
          "claim_kind": "targeting_rule",
          "cards": ["NX2_019"],
          "stance": "prefer_enemy_minion",
          "evidence_text_short": (
              "Mind Sear deals 2 damage to a minion and deals 3 damage "
              "to the enemy hero if it dies."
          ),
      }

      score = score_card_behavior_claim(
          claim,
          behavior_block="BeforeBattlecryTargetBonus",
          intent="prefer_enemy_minion",
          roles=["prefer_enemy_minion"],
          value_default="6",
      )

      assert score.value == "10"
      assert score.band == "high"
      assert score.reason == "conditional_minion_death_burn"
      assert "enemy_hero_damage" in score.matched_signals
      assert "death_condition" in score.matched_signals


  def test_hero_power_transform_scores_as_critical_engine_effect():
      claim = {
          "claim_kind": "hero_power_transform",
          "cards": ["SW_448"],
          "stance": "shadowform_engine",
          "evidence_text_short": (
              "Darkbishop Benedictus changes the starting hero power to Mind Spike."
          ),
      }

      score = score_card_behavior_claim(
          claim,
          behavior_block="BeforeUseHeroPowerBonus",
          intent="hero_power_transform",
          roles=["hero_power", "shadowform_engine"],
          value_default="6",
      )

      assert score.value == "10"
      assert score.band == "critical"
      assert score.reason == "hero_power_transform"
      assert "hero_power" in score.matched_signals


  def test_location_claim_scores_as_tempo_not_as_blocker():
      claim = {
          "claim_kind": "card_role",
          "cards": ["REV_248"],
          "mechanic": "location",
          "semantic_families": ["location"],
          "evidence_text_short": "Cathedral of Atonement is a Location that gives tempo.",
      }

      score = score_card_behavior_claim(
          claim,
          behavior_block="BeforePlayCardBonus",
          intent="location_tempo",
          roles=["location"],
          value_default="6",
      )

      assert score.value == "8"
      assert score.band == "medium"
      assert score.reason == "location_tempo"
      assert "location" in score.matched_signals


  def test_unrecognized_claim_keeps_default_value_with_report_reason():
      claim = {
          "claim_kind": "card_role",
          "cards": ["GENERIC_CARD"],
          "semantic_families": ["tradeable"],
          "evidence_text_short": "The card has Tradeable.",
      }

      score = score_card_behavior_claim(
          claim,
          behavior_block="BeforePlayCardBonus",
          intent="tradeable",
          roles=["tradeable"],
          value_default="6",
      )

      assert score.value == "6"
      assert score.band == "default"
      assert score.reason == "semantic_default"
  ```

- [ ] **Step 2: Run the new test file and confirm it fails for the expected missing module**

  ```powershell
  cd C:\Users\darbo\Documents\HSConfig
  python -m pytest tests\test_semantic_intent_score.py -q -p no:cacheprovider
  ```

  Expected failure:

  ```text
  ModuleNotFoundError: No module named 'hsconfig.semantic_intent_score'
  ```

---

### Task 2: Implement The Pure Semantic Intent Scorer

**Files:**
- Create: `src/hsconfig/semantic_intent_score.py`

**Interfaces:**
- Public dataclass: `SemanticIntentScore`
- Public function:
  ```python
  def score_card_behavior_claim(
      claim: Mapping[str, Any],
      *,
      behavior_block: str,
      intent: str,
      roles: Sequence[str],
      value_default: str = "6",
  ) -> SemanticIntentScore:
  ```

- [ ] **Step 1: Implement a pure module with no I/O and no project-cycle imports**

  Use this shape:

  ```python
  from __future__ import annotations

  from dataclasses import dataclass
  from typing import Any, Mapping, Sequence


  @dataclass(frozen=True)
  class SemanticIntentScore:
      value: str
      band: str
      reason: str
      profile: str
      matched_signals: tuple[str, ...] = ()
  ```

- [ ] **Step 2: Add explicit value handling before semantic rules**

  Implement helper behavior:

  ```python
  explicit = claim.get("runtime_value", claim.get("value"))
  if explicit is not None and str(explicit).strip():
      return SemanticIntentScore(
          value=str(explicit),
          band="explicit",
          reason="explicit_runtime_value",
          profile="source_claim",
          matched_signals=("explicit_value",),
      )
  ```

- [ ] **Step 3: Build normalized text from stable claim fields only**

  Include these fields in the normalized text:

  ```python
  (
      claim.get("claim_kind"),
      claim.get("stance"),
      claim.get("intent"),
      claim.get("mechanic"),
      claim.get("evidence_text_short"),
      claim.get("source_title"),
      behavior_block,
      intent,
      " ".join(str(role) for role in roles),
      " ".join(str(family) for family in claim.get("semantic_families", [])),
  )
  ```

  Rules:
  - Convert to lowercase.
  - Ignore missing values.
  - Do not inspect external card databases in this scorer.
  - Do not import `card_behavior_surface_router.py`.

- [ ] **Step 4: Implement deterministic scoring bands**

  Use this precedence order:

  | Reason | Signals | Value | Band |
  | --- | --- | --- | --- |
  | `hero_power_transform` | `hero_power_transform`, `shadowform`, `mind spike`, or `hero power` plus transform/start language | `10` | `critical` |
  | `damage_aura_amplifier` | `extra damage`, `all sources`, `both heroes take`, `voidtouched`, or `attendant` | `10` | `critical` |
  | `conditional_minion_death_burn` | `enemy hero` plus `if it dies` or `dies` plus minion targeting | `10` | `high` |
  | `direct_enemy_hero_burn` | `prefer_enemy_hero`, `enemy hero`, `face`, or `hero damage` with damage wording | `12` | `critical` |
  | `location_tempo` | `location`, `cathedral`, or `atonement` | `8` | `medium` |
  | `draw_cycle` | `draw`, `cycle`, `discover`, `generate`, or `copy` | `8` | `medium` |
  | `board_tempo` | `summon`, `pirate`, `treant`, `mech`, `board`, or `on_board` | `8` | `medium` |
  | `semantic_default` | no semantic rule matches | `value_default` | `default` |

  Keep every value as a string and do not emit values outside `4` through `12`.

- [ ] **Step 5: Run scorer tests**

  ```powershell
  cd C:\Users\darbo\Documents\HSConfig
  python -m pytest tests\test_semantic_intent_score.py -q -p no:cacheprovider
  ```

  Expected result:

  ```text
  5 passed
  ```

---

### Task 3: Integrate Scoring Into Card Behavior Routing

**Files:**
- Modify: `src/hsconfig/card_behavior_surface_router.py`
- Modify: `tests/test_card_behavior_router.py`

**Interfaces:**
- Existing public function remains unchanged:
  ```python
  def route_card_behavior_surfaces(claims, identity_links=None) -> dict[str, Any]:
  ```

- [ ] **Step 1: Add integration tests before changing router code**

  In `tests/test_card_behavior_router.py`, add tests covering:
  - A behavior row without explicit `runtime_value` receives semantic `value`.
  - A behavior row with explicit `runtime_value` keeps that exact value.
  - Scoring metadata appears in the plan row.
  - Suppressed rows stay suppressed and are not scored.

  Use claim examples:

  ```python
  mind_sear_claim = {
      "claim_kind": "targeting_rule",
      "cards": ["NX2_019"],
      "stance": "prefer_enemy_minion",
      "evidence_text_short": (
          "Mind Sear deals 2 damage to a minion and deals 3 damage "
          "to the enemy hero if it dies."
      ),
      "source_claim_ids": ["mind_sear_source"],
  }
  ```

  Expected row assertions:

  ```python
  assert row["behavior_block"] == "BeforeBattlecryTargetBonus"
  assert row["value"] == "10"
  assert row["semantic_score"]["reason"] == "conditional_minion_death_burn"
  assert row["semantic_score"]["band"] == "high"
  ```

  Explicit override assertion:

  ```python
  assert explicit_row["value"] == "8"
  assert explicit_row["semantic_score"]["reason"] == "explicit_runtime_value"
  ```

- [ ] **Step 2: Run the targeted router tests and confirm the new assertions fail**

  ```powershell
  cd C:\Users\darbo\Documents\HSConfig
  python -m pytest tests\test_card_behavior_router.py -q -p no:cacheprovider
  ```

- [ ] **Step 3: Import and call the scorer inside `_attach_behavior_fields()`**

  Implement this behavior in `card_behavior_surface_router.py`:

  ```python
  from hsconfig.semantic_intent_score import score_card_behavior_claim
  ```

  After the router has selected `behavior_block`, `intent`, `roles`, `rule_id_suffix`, and `condition`, call:

  ```python
  semantic_score = score_card_behavior_claim(
      claim,
      behavior_block=str(row["behavior_block"]),
      intent=str(row.get("intent", "")),
      roles=[str(role) for role in row.get("roles", [])],
      value_default=value_default,
  )
  row["value"] = semantic_score.value
  row["semantic_score"] = {
      "band": semantic_score.band,
      "reason": semantic_score.reason,
      "profile": semantic_score.profile,
      "matched_signals": list(semantic_score.matched_signals),
  }
  ```

  Existing behavior to preserve:
  - `_runtime_value()` must no longer be the final row-value decision for accepted CardID behavior rows.
  - Source-supplied explicit values still win through the scorer.
  - Suppressed rows must not receive `semantic_score`.

- [ ] **Step 4: Run scorer and router tests**

  ```powershell
  cd C:\Users\darbo\Documents\HSConfig
  python -m pytest tests\test_semantic_intent_score.py tests\test_card_behavior_router.py -q -p no:cacheprovider
  ```

---

### Task 4: Guard Runtime JSON Cleanliness

**Files:**
- Modify: `tests/test_compile_cardid.py`

**Interfaces:**
- Existing public function:
  ```python
  compile_cardid_behaviors(contract: dict[str, Any] | None = None, *, deck_name: str | None = None, rows: list[dict[str, Any]] | None = None) -> dict[str, dict[str, Any]]
  ```

- [ ] **Step 1: Add a compiler regression test for diagnostic-only score metadata**

  Add a test with a behavior row containing:

  ```python
  "semantic_score": {
      "band": "high",
      "reason": "conditional_minion_death_burn",
      "profile": "source_claim",
      "matched_signals": ["enemy_hero_damage", "death_condition"],
  }
  ```

  Expected assertion:

  ```python
  value_row = files["NX2_019.json"]["BeforeBattlecryTargetBonus"]["values"][0]
  assert value_row == {
      "comment": "Fixture: NX2_019_prefer_enemy_minion",
      "condition": "*",
      "value": "10",
  }
  assert "semantic_score" not in value_row
  ```

- [ ] **Step 2: Run compiler tests**

  ```powershell
  cd C:\Users\darbo\Documents\HSConfig
  python -m pytest tests\test_compile_cardid.py -q -p no:cacheprovider
  ```

  Expected result: all tests pass without changing `compile_cardid.py` unless the regression exposes leakage.

---

### Task 5: Add ShadowPriest And Wild Matrix Regression Coverage

**Files:**
- Modify: `tests/test_shadowpriest_e2e.py`
- Modify: `tests/test_universal_wild_no_block_matrix.py`

**Interfaces:**
- Uses existing `ShadowPriest` deck code:
  ```text
  AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=
  ```
- Uses existing fixture:
  ```text
  tests\fixtures\source_documents_shadowpriest_strong.json
  ```

- [ ] **Step 1: Extend ShadowPriest E2E with report-level scoring assertions**

  Add assertions after the existing source-backed strong prepare flow:

  ```python
  behavior_report = json.loads(
      (out / "reports" / "card_behavior_plan_report.json").read_text(encoding="utf-8")
  )
  scored_rows = [
      row
      for row in behavior_report["rows"]
      if row.get("semantic_score") and row.get("card_id") == "NX2_019"
  ]
  assert scored_rows
  assert all(row["value"] for row in scored_rows)
  assert {row["semantic_score"]["reason"] for row in scored_rows}
  ```

  Preserve the existing Darkbishop assertion:

  ```python
  assert "SW_448" not in mulligan_keep_cards
  assert "BeforeUseHeroPowerBonus" in darkbishop_file
  ```

- [ ] **Step 2: Add a universal Wild matrix assertion that accepted behavior rows carry bounded values**

  In `tests/test_universal_wild_no_block_matrix.py`, add a helper assertion:

  ```python
  for row in behavior_plan["rows"]:
      if row.get("surface_family") == "CARDID.json" and row.get("behavior_block"):
          assert str(row["value"]).isdigit()
          assert 4 <= int(row["value"]) <= 12
  ```

  Keep existing assertions that no package blocks just because it is not strong and that `default_only` remains empty for generated operator summaries.

- [ ] **Step 3: Run focused regression tests**

  ```powershell
  cd C:\Users\darbo\Documents\HSConfig
  python -m pytest tests\test_shadowpriest_e2e.py tests\test_universal_wild_no_block_matrix.py -q -p no:cacheprovider
  ```

---

### Task 6: Temporary Package Smoke Check Without Runtime Apply

**Files:**
- No persistent files.
- Use `%TEMP%` only and remove it at the end.

- [ ] **Step 1: Build and validate a temporary ShadowPriest package**

  ```powershell
  cd C:\Users\darbo\Documents\HSConfig
  $tmp = Join-Path $env:TEMP "hsconfig-semantic-intent-shadowpriest"
  Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
  python -m hsconfig.cli prepare --deck-name ShadowPriest --deck-code "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=" --runtime-root (Join-Path $tmp "runtime") --out (Join-Path $tmp "pkg") --source-documents-json tests\fixtures\source_documents_shadowpriest_strong.json --json
  python -m hsconfig.cli validate --package (Join-Path $tmp "pkg") --json
  python -m hsconfig.cli contract-doctor --package (Join-Path $tmp "pkg") --json
  ```

- [ ] **Step 2: Inspect the temporary reports for the intended properties**

  ```powershell
  $pkg = Join-Path $env:TEMP "hsconfig-semantic-intent-shadowpriest\pkg"
  $summary = Get-Content (Join-Path $pkg "reports\operator_summary.json") -Raw | ConvertFrom-Json
  $behavior = Get-Content (Join-Path $pkg "reports\card_behavior_plan_report.json") -Raw | ConvertFrom-Json
  $mindSearRows = @($behavior.rows | Where-Object { $_.card_id -eq "NX2_019" -and $_.semantic_score })
  $summary.runtime_package_usable
  $summary.source_status
  $mindSearRows.Count
  $mindSearRows | Select-Object card_id,behavior_block,value,@{Name="reason";Expression={$_.semantic_score.reason}}
  ```

  Expected properties:
  - `runtime_package_usable` is `True`.
  - `source_status` remains whatever the canonical package computes from source quality; it is not overridden by this scorer.
  - At least one Mind Sear row has scoring metadata.
  - Runtime JSON value rows still contain only `comment`, `condition`, and `value`.

- [ ] **Step 3: Remove the temporary package**

  ```powershell
  Remove-Item -LiteralPath (Join-Path $env:TEMP "hsconfig-semantic-intent-shadowpriest") -Recurse -Force -ErrorAction SilentlyContinue
  ```

---

### Task 7: Full Verification And Clean Finish

**Files:**
- All changed files.

- [ ] **Step 1: Run focused tests**

  ```powershell
  cd C:\Users\darbo\Documents\HSConfig
  python -m pytest tests\test_semantic_intent_score.py tests\test_card_behavior_router.py tests\test_compile_cardid.py tests\test_shadowpriest_e2e.py tests\test_universal_wild_no_block_matrix.py -q -p no:cacheprovider
  ```

- [ ] **Step 2: Run the full test suite**

  ```powershell
  cd C:\Users\darbo\Documents\HSConfig
  python -m pytest -q -p no:cacheprovider
  ```

- [ ] **Step 3: Check formatting, diff, and generated artifacts**

  ```powershell
  cd C:\Users\darbo\Documents\HSConfig
  git diff --check
  git status --short
  ```

  Expected tracked changes:

  ```text
  M src/hsconfig/card_behavior_surface_router.py
  A src/hsconfig/semantic_intent_score.py
  M tests/test_card_behavior_router.py
  M tests/test_compile_cardid.py
  A tests/test_semantic_intent_score.py
  M tests/test_shadowpriest_e2e.py
  M tests/test_universal_wild_no_block_matrix.py
  ```

  If `.pytest_cache`, `tmp`, `outputs`, or package smoke artifacts appear, remove only those generated artifacts:

  ```powershell
  Remove-Item -LiteralPath .pytest_cache -Recurse -Force -ErrorAction SilentlyContinue
  Remove-Item -LiteralPath tmp\verify-semantic-intent -Recurse -Force -ErrorAction SilentlyContinue
  ```

- [ ] **Step 4: Commit after successful verification**

  ```powershell
  cd C:\Users\darbo\Documents\HSConfig
  git add src\hsconfig\card_behavior_surface_router.py src\hsconfig\semantic_intent_score.py tests\test_card_behavior_router.py tests\test_compile_cardid.py tests\test_semantic_intent_score.py tests\test_shadowpriest_e2e.py tests\test_universal_wild_no_block_matrix.py
  git commit -m "feat: score card behavior intent semantically"
  git status --short --branch
  ```

  Expected final state:

  ```text
  ## main...origin/main [ahead N]
  ```

  `N` is the number of local implementation commits not yet pushed. The worktree must have no uncommitted changes.

---

## Subagent Split

- **Explorer Agent:** read-only check of `card_behavior_surface_router.py`, `source_document_model.py`, `static_semantics.py`, and `mechanic_support.py`; confirm there is exactly one accepted-row integration point and no source-status gate should move.
- **Worker Agent:** implement `semantic_intent_score.py` and `tests/test_semantic_intent_score.py` only.
- **Integration Agent:** update router tests and router integration only.
- **Regression Agent:** update ShadowPriest, compile, and universal matrix tests only.
- **Main Agent:** reconcile diffs, run full verification, remove generated artifacts, commit, and report final evidence.

No two agents should write the same file. The main agent owns final conflict resolution and verification.

---

## Acceptance Criteria

- `score_card_behavior_claim()` is deterministic, pure, and has no filesystem, web, runtime, or HearthRanger dependencies.
- Explicit source/guide `runtime_value` and `value` always override semantic scoring.
- Accepted behavior rows in `card_behavior_plan_report.json` include diagnostic `semantic_score` metadata.
- Runtime per-card JSON files still emit only `comment`, `condition`, and `value` for each rule row.
- `SW_448` remains absent from ShadowPriest Mulligan keeps while its hero power transform effect remains represented through CardID behavior.
- Mind Sear-style conditional minion death burn is recognized as stronger than a generic default when no explicit value is provided.
- Location claims such as Cathedral of Atonement are recognized as tempo behavior, not as blockers or unsupported fatal conditions.
- Representative Wild deck matrix remains no-block and no-default-only clean.
- `python -m pytest -q -p no:cacheprovider` passes.
- Final repository state has no uncommitted changes after implementation.

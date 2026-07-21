# HSConfig Mulligan Semantic Dedupe Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Merge semantically identical Mulligan rules before runtime JSON generation, while preserving all source provenance and keeping ShadowPriest `SOURCE_BACKED_STRONG`.

**Architecture:** Keep the fix in the plan layer: `build_mulligan_plan()` should dedupe runtime-equivalent rows by card, selector, action, condition, and source lane, then merge source metadata into the retained row. `compile_mulligan.py` remains a simple renderer of an already-clean plan; `package_builder.py` continues to use the same semantic key when filtering rows for lifecycle-visible runtime output.

**Tech Stack:** Python stdlib, existing HSConfig CLI, pytest, existing JSON package reports. No new dependencies.

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
- Do not use HSTuner, replay parsing, winrate tuning, candidate promotion, or post-run patch logic.
- Do not add runtime log analysis to HSConfig.
- Do not tune `GlobalValues.json` from play results.
- Do not add `Combo.json` without exact source-backed timing.
- Do not add `Darkbishop Benedictus` (`SW_448`) as a Mulligan keep without explicit opening-hand keep evidence.
- Preserve `reports/operator_summary.json` as the normal apply authority.
- Preserve `SOURCE_BACKED_STRONG` as an evidence-quality label, not as a generation or apply gate.
- Preserve no-default-only guarantees: dedupe must not remove the last concrete keep row or silently broaden to default-only.
- Do not run live runtime apply. Do not write to `C:\Users\darbo\Desktop\HS` in this plan.
- Keep final HSConfig worktree clean. If code changes are made and tests pass, commit them.

---

## File Structure

- Modify: `tests/test_mulligan_plan.py`
  - Responsibility: unit coverage for exact semantic duplicate merge, provenance retention, and non-merge boundaries.
- Modify: `src/hsconfig/mulligan_plan.py`
  - Responsibility: build source-backed Mulligan plan rows; own semantic dedupe and provenance merge before compile.
- Modify: `tests/test_shadowpriest_e2e.py`
  - Responsibility: package-level ShadowPriest guard that generated `Mulligan.json` has no exact duplicate runtime rows and still omits `SW_448`.
- Read-only verification: `src/hsconfig/package_builder.py`
  - Responsibility: lifecycle filtering uses `mulligan_rule_key()`; should keep working once the key becomes semantic.
- Read-only verification: `src/hsconfig/compile_mulligan.py`
  - Responsibility: render plan rows to runtime JSON without needing its own dedupe layer.

---

### Task 1: Add Unit Tests For Semantic Mulligan Dedupe

**Files:**
- Modify: `tests/test_mulligan_plan.py`

**Interfaces:**
- Consumes: `build_mulligan_plan(deck_name: str, claims: list[dict[str, Any]], card_roles: dict[str, Any], ...) -> dict[str, Any]`
- Produces: failing tests that require exact duplicate `mulligan_keep` rows to merge while retaining source provenance.

- [ ] **Step 1: Insert the duplicate-merge test after `test_mulligan_plan_preserves_multiple_conditions_for_same_card`**

  Add this exact test:

  ```python
  def test_mulligan_plan_merges_runtime_duplicate_source_keeps_preserving_provenance():
      claims = [
          {
              "claim_kind": "mulligan_keep",
              "cards": ["SW_444"],
              "conditions": "*",
              "claim_id": "keep_twilight_guide_a",
              "source_claim_ids": ["raw_keep_twilight_a"],
              "evidence_text_short": "Keep Twilight Deceptor",
          },
          {
              "claim_kind": "mulligan_keep",
              "cards": ["SW_444"],
              "conditions": "*",
              "claim_id": "keep_twilight_guide_b",
              "source_claim_ids": ["raw_keep_twilight_b"],
              "evidence_text_short": "Twilight Deceptor is a keep",
          },
      ]

      plan = build_mulligan_plan(deck_name="ShadowPriest", claims=claims, card_roles={})

      sw444_rules = [
          row
          for row in plan["rules"]
          if row["card"] == "SW_444" and row["action"] == "hold"
      ]
      assert len(sw444_rules) == 1
      assert sw444_rules[0]["condition"] == "*"
      assert sw444_rules[0]["source_claim_ids"] == [
          "raw_keep_twilight_a",
          "raw_keep_twilight_b",
      ]
      assert sw444_rules[0]["merged_claim_ids"] == [
          "keep_twilight_guide_a",
          "keep_twilight_guide_b",
      ]
      assert sw444_rules[0]["merged_reasons"] == [
          "Keep Twilight Deceptor",
          "Twilight Deceptor is a keep",
      ]
      assert plan["quality"]["source_backed_keep_rule_count"] == 1
      assert plan["quality"]["merged_duplicate_rule_count"] == 1
      assert plan["quality"]["default_only"] is False
  ```

- [ ] **Step 2: Insert the boundary test immediately after the duplicate-merge test**

  Add this exact test:

  ```python
  def test_mulligan_plan_does_not_merge_same_card_with_different_condition_or_action():
      claims = [
          {
              "claim_kind": "mulligan_keep",
              "cards": ["SW_444"],
              "conditions": {"coin": True},
              "claim_id": "keep_coin",
          },
          {
              "claim_kind": "mulligan_keep",
              "cards": ["SW_444"],
              "conditions": {"nocoin": True},
              "claim_id": "keep_no_coin",
          },
          {
              "claim_kind": "mulligan_discard",
              "cards": ["SW_444"],
              "conditions": {"coin": True},
              "claim_id": "discard_coin",
          },
      ]

      plan = build_mulligan_plan(deck_name="ShadowPriest", claims=claims, card_roles={})

      sw444_rules = [
          (row["action"], row["condition"])
          for row in plan["rules"]
          if row["card"] == "SW_444"
      ]
      assert sw444_rules == [
          ("discard", "coin"),
          ("hold", "coin"),
          ("hold", "nocoin"),
      ]
      assert plan["quality"]["source_backed_keep_rule_count"] == 2
      assert plan["quality"]["merged_duplicate_rule_count"] == 0
  ```

- [ ] **Step 3: Run the new focused tests and confirm the expected failure**

  Run:

  ```powershell
  python -m pytest tests\test_mulligan_plan.py::test_mulligan_plan_merges_runtime_duplicate_source_keeps_preserving_provenance tests\test_mulligan_plan.py::test_mulligan_plan_does_not_merge_same_card_with_different_condition_or_action -q -p no:cacheprovider
  ```

  Expected before implementation:

  ```text
  FAILED tests/test_mulligan_plan.py::test_mulligan_plan_merges_runtime_duplicate_source_keeps_preserving_provenance
  ```

  The boundary test may pass before implementation; the duplicate-merge test must fail because current dedupe includes `source_claim_ids`.

---

### Task 2: Implement Semantic Dedupe In The Mulligan Plan Layer

**Files:**
- Modify: `src/hsconfig/mulligan_plan.py`

**Interfaces:**
- Consumes: source-backed and policy-backed rule dicts with `card`, `selector_kind`, `selector`, `selector_cards`, `action`, `condition`, `source_type`, `source_claim_ids`, `claim_id`, and `reason`.
- Produces:
  - `mulligan_rule_key(rule: dict[str, Any]) -> tuple[Any, ...]` excluding provenance-only fields.
  - `_add_or_merge_mulligan_rule(rules: list[dict[str, Any]], rules_by_key: dict[tuple[Any, ...], dict[str, Any]], rule: dict[str, Any]) -> bool`
  - `quality["merged_duplicate_rule_count"]`

- [ ] **Step 1: Replace `seen_rule_keys` with a key-to-rule map**

  In `build_mulligan_plan()`, replace:

  ```python
      seen_rule_keys: set[tuple[Any, ...]] = set()
  ```

  with:

  ```python
      rules_by_key: dict[tuple[Any, ...], dict[str, Any]] = {}
      merged_duplicate_rule_count = 0
  ```

- [ ] **Step 2: Replace source-claim append logic with merge logic**

  Replace this block:

  ```python
              key = mulligan_rule_key(rule)
              if key in seen_rule_keys:
                  continue
              seen_rule_keys.add(key)
              rules.append(rule)
  ```

  with:

  ```python
              if _add_or_merge_mulligan_rule(rules, rules_by_key, rule):
                  merged_duplicate_rule_count += 1
  ```

- [ ] **Step 3: Replace policy-backed append logic with the same merge helper**

  Replace this block:

  ```python
          for row in policy_result["rules"]:
              key = mulligan_rule_key(row)
              if key in seen_rule_keys:
                  continue
              seen_rule_keys.add(key)
              rules.append(row)
  ```

  with:

  ```python
          for row in policy_result["rules"]:
              if _add_or_merge_mulligan_rule(rules, rules_by_key, row):
                  merged_duplicate_rule_count += 1
  ```

- [ ] **Step 4: Add merged duplicate count to the quality report**

  In the `quality` dict, add this exact row after `suppressed_reasons`:

  ```python
          "merged_duplicate_rule_count": merged_duplicate_rule_count,
  ```

- [ ] **Step 5: Make `mulligan_rule_key()` semantic**

  Replace the current function with:

  ```python
  def mulligan_rule_key(rule: dict[str, Any]) -> tuple[Any, ...]:
      return (
          rule.get("card"),
          rule.get("selector_kind"),
          rule.get("selector"),
          tuple(str(item) for item in rule.get("selector_cards", [])),
          rule.get("action"),
          rule.get("condition", "*"),
          rule.get("source_type", ""),
      )
  ```

  This intentionally excludes `source_claim_ids`, `claim_id`, and `reason`, because those fields are provenance, not runtime behavior.

- [ ] **Step 6: Add helper functions below `mulligan_rule_key()`**

  Add:

  ```python
  def _add_or_merge_mulligan_rule(
      rules: list[dict[str, Any]],
      rules_by_key: dict[tuple[Any, ...], dict[str, Any]],
      rule: dict[str, Any],
  ) -> bool:
      key = mulligan_rule_key(rule)
      existing = rules_by_key.get(key)
      if existing is None:
          rules_by_key[key] = rule
          rules.append(rule)
          return False

      _merge_unique_list(existing, "source_claim_ids", rule.get("source_claim_ids", []))
      _merge_unique_list(
          existing,
          "merged_claim_ids",
          [
              existing.get("claim_id"),
              *existing.get("merged_claim_ids", []),
              rule.get("claim_id"),
              *rule.get("merged_claim_ids", []),
          ],
      )
      _merge_unique_list(
          existing,
          "merged_reasons",
          [
              existing.get("reason"),
              *existing.get("merged_reasons", []),
              rule.get("reason"),
              *rule.get("merged_reasons", []),
          ],
      )
      return True


  def _merge_unique_list(
      target: dict[str, Any],
      key: str,
      values: list[Any],
  ) -> None:
      merged: list[str] = []
      seen: set[str] = set()
      for value in [*target.get(key, []), *values]:
          text = str(value).strip()
          if not text or text in seen:
              continue
          seen.add(text)
          merged.append(text)
      if merged:
          target[key] = merged
  ```

- [ ] **Step 7: Run the focused Mulligan tests**

  Run:

  ```powershell
  python -m pytest tests\test_mulligan_plan.py::test_mulligan_plan_merges_runtime_duplicate_source_keeps_preserving_provenance tests\test_mulligan_plan.py::test_mulligan_plan_does_not_merge_same_card_with_different_condition_or_action tests\test_mulligan_plan.py::test_mulligan_plan_orders_conflicting_exact_rules_by_precedence tests\test_mulligan_plan.py::test_mulligan_plan_preserves_multiple_conditions_for_same_card -q -p no:cacheprovider
  ```

  Expected:

  ```text
  4 passed
  ```

---

### Task 3: Add ShadowPriest Runtime Package Guard

**Files:**
- Modify: `tests/test_shadowpriest_e2e.py`

**Interfaces:**
- Consumes: `main(["prepare", ...])` and the strong fixture `tests/fixtures/source_documents_shadowpriest_strong.json`.
- Produces: package-level proof that strong ShadowPriest runtime `Mulligan.json` has no exact duplicate runtime rows and still excludes `SW_448` from holds.

- [ ] **Step 1: Add the package-level test after `test_source_backed_strong_shadowpriest_keeps_benedictus_effect_not_opening_hand`**

  Add:

  ```python
  def test_source_backed_strong_shadowpriest_mulligan_runtime_rows_are_semantic_unique(
      tmp_path: Path, monkeypatch
  ):
      monkeypatch.setattr("hsconfig.package_builder.fetch_latest_cards", lambda timeout=10.0: [])
      out = tmp_path / "pkg"
      code = main(
          [
              "prepare",
              "--deck-name",
              "ShadowPriest",
              "--deck-code",
              SHADOWPRIEST_CODE,
              "--runtime-root",
              str(tmp_path / "runtime"),
              "--out",
              str(out),
              "--source-documents-json",
              "tests/fixtures/source_documents_shadowpriest_strong.json",
          ]
      )

      deck_dir = out / "CustomConfig" / "shadowpriest"
      reports = out / "reports"
      mulligan = json.loads((deck_dir / "Mulligan.json").read_text(encoding="utf-8"))
      plan_report = json.loads(
          (reports / "mulligan_plan_report.json").read_text(encoding="utf-8")
      )
      runtime_rows = mulligan["Mulligan"]["values"]
      runtime_keys = [
          (row.get("mulligan"), row.get("condition", "*"), row.get("value"))
          for row in runtime_rows
      ]

      assert code == 0
      assert runtime_keys == [
          ("SW_444", "*", "hold"),
          ("TOY_381", "*", "hold"),
          ("*", "*", "discard"),
      ]
      assert len(runtime_keys) == len(set(runtime_keys))
      assert not any(
          row.get("mulligan") == "SW_448" and row.get("value") == "hold"
          for row in runtime_rows
      )
      assert plan_report["quality"]["merged_duplicate_rule_count"] == 2
      assert plan_report["quality"]["source_backed_keep_rule_count"] == 2
      assert plan_report["quality"]["default_only"] is False
  ```

- [ ] **Step 2: Run the new ShadowPriest test**

  Run:

  ```powershell
  python -m pytest tests\test_shadowpriest_e2e.py::test_source_backed_strong_shadowpriest_mulligan_runtime_rows_are_semantic_unique -q -p no:cacheprovider
  ```

  Expected:

  ```text
  1 passed
  ```

---

### Task 4: Regression And Contract Verification

**Files:**
- Read: `outputs\ShadowPriest\04_package\reports\operator_summary.json`
- Read: `outputs\ShadowPriest\04_package\reports\mulligan_plan_report.json`
- Read: `outputs\ShadowPriest\04_package\CustomConfig\shadowpriest\Mulligan.json`

**Interfaces:**
- Consumes: completed Tasks 1-3.
- Produces: verified implementation with no dirty uncommitted changes after commit.

- [ ] **Step 1: Run focused regression tests**

  Run:

  ```powershell
  python -m pytest tests\test_mulligan_plan.py tests\test_claim_kind_runtime_contract.py tests\test_shadowpriest_e2e.py -q -p no:cacheprovider
  ```

  Expected:

  ```text
  all selected tests passed
  ```

  If the exact count differs from previous runs, accept the count only when every selected test passes.

- [ ] **Step 2: Run contract spine sentinel**

  Run:

  ```powershell
  python -m hsconfig.cli contract-spine-sentinel --json
  ```

  Expected:

  ```json
  {
    "status": "clean",
    "apply_blocking": false
  }
  ```

  Additional diagnostic arrays may be present, but there must be no `problems`.

- [ ] **Step 3: Rebuild a temporary strong ShadowPriest package without touching live runtime**

  Run:

  ```powershell
  $tmp = Join-Path $env:TEMP "hsconfig-shadowpriest-dedupe-check"
  Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
  python -m hsconfig.cli prepare --deck-name ShadowPriest --deck-code "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=" --runtime-root (Join-Path $tmp "runtime") --out (Join-Path $tmp "pkg") --source-documents-json tests\fixtures\source_documents_shadowpriest_strong.json --json
  python -m hsconfig.cli validate --package (Join-Path $tmp "pkg") --json
  python -m hsconfig.cli contract-doctor --package (Join-Path $tmp "pkg") --json
  ```

  Expected:

  ```text
  prepare exits 0
  validate status passed
  contract-doctor status ok
  operator semantic_status SOURCE_BACKED_STRONG
  ```

- [ ] **Step 4: Inspect the temporary runtime Mulligan rows**

  Run:

  ```powershell
  $mulliganPath = Join-Path $env:TEMP "hsconfig-shadowpriest-dedupe-check\pkg\CustomConfig\shadowpriest\Mulligan.json"
  Get-Content -Raw $mulliganPath
  ```

  Expected `Mulligan.values` entries:

  ```json
  [
    {
      "comment": "ShadowPriest: SW_444_mulligan_1",
      "condition": "*",
      "mulligan": "SW_444",
      "value": "hold"
    },
    {
      "comment": "ShadowPriest: TOY_381_mulligan_2",
      "condition": "*",
      "mulligan": "TOY_381",
      "value": "hold"
    },
    {
      "comment": "ShadowPriest: *_mulligan_3",
      "condition": "*",
      "mulligan": "*",
      "value": "discard"
    }
  ]
  ```

- [ ] **Step 5: Remove temporary verification output**

  Run:

  ```powershell
  Remove-Item -LiteralPath (Join-Path $env:TEMP "hsconfig-shadowpriest-dedupe-check") -Recurse -Force -ErrorAction SilentlyContinue
  ```

  Expected:

  ```text
  command exits 0
  ```

- [ ] **Step 6: Check final diff**

  Run:

  ```powershell
  git diff -- src\hsconfig\mulligan_plan.py tests\test_mulligan_plan.py tests\test_shadowpriest_e2e.py
  git status --short --branch
  ```

  Expected changed files before commit:

  ```text
  ## main...origin/main
   M src/hsconfig/mulligan_plan.py
   M tests/test_mulligan_plan.py
   M tests/test_shadowpriest_e2e.py
  ```

- [ ] **Step 7: Commit implementation**

  Run:

  ```powershell
  git add src\hsconfig\mulligan_plan.py tests\test_mulligan_plan.py tests\test_shadowpriest_e2e.py
  git commit -m "fix: dedupe semantic mulligan rules"
  git status --short --branch
  ```

  Expected final status:

  ```text
  ## main...origin/main [ahead 1]
  ```

  Do not push unless the user explicitly asks.

---

## Self-Review

- Spec coverage: The plan implements only the recommended slim technical improvement: semantic Mulligan dedupe with provenance preservation. It does not add gameplay tuning, HSTuner logic, runtime log parsing, `Combo.json`, or `Darkbishop Benedictus` keep logic.
- Placeholder scan: No placeholder markers or unspecified test steps remain.
- Type consistency: `mulligan_rule_key(rule: dict[str, Any]) -> tuple[Any, ...]`, `_add_or_merge_mulligan_rule(...) -> bool`, and `_merge_unique_list(...) -> None` are defined before being relied on by tests and package-builder filtering.
- Runtime safety: Live `C:\Users\darbo\Desktop\HS` is never written in this plan; verification uses `%TEMP%`.

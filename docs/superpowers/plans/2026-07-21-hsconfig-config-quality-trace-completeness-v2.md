# HSConfig Config Quality Trace Completeness v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the existing diagnostic-only `config_quality` contract so every generated package can prove runtime-row traceability, closure freshness, no hidden default-only output, and report-only mechanic discipline before an operator treats a config as high-quality.

**Architecture:** Keep the current single module `src/hsconfig/config_quality_contract.py` as the quality sentinel and add small, pure read-only checks inside it. The sentinel will read only prepared package files under `<package>/reports` and `<package>/CustomConfig`, reuse existing report shapes, and surface all new findings through `contract-doctor` as `attention` diagnostics without changing `operator_summary.json`, runtime apply permission, source status, or generated HearthRanger runtime files.

**Tech Stack:** Python 3.11, Python stdlib, existing HSConfig package, pytest, prepared package JSON reports. No new dependencies.

## Global Constraints

- Work only in `C:\Users\darbo\Documents\HSConfig`.
- Start implementation by refreshing repository state:
  ```powershell
  cd C:\Users\darbo\Documents\HSConfig
  git fetch --all --prune --tags
  python scripts\check_hsconfig_currentness.py --cwd . --json
  git status --short --branch
  ```
- Runtime-facing verification may start only when the worktree is clean and the branch is not behind its upstream.
- Feature branches may be ahead of `origin/main`; do not switch branches unless the user explicitly requests it.
- Do not use HSTuner.
- Do not parse HearthRanger logs, Hearthstone logs, HDT files, replays, winrate, or post-game runtime evidence.
- Do not write to `C:\Users\darbo\Desktop\HS`.
- Do not add a new operator command when `config_quality` plus `contract-doctor` can carry the diagnostic.
- Do not add a new apply gate, readiness gate, promotion gate, or source-status override.
- Preserve `reports/operator_summary.json` as the only normal apply authority.
- Preserve `SOURCE_BACKED_STRONG` as an evidence-quality label, not a package generation or apply gate.
- Preserve no-block behavior: a valid package must not be blocked because source depth is partial, a mechanic is report-only, or a config-quality issue is diagnostic-only.
- Preserve no-default-only visibility: default-only runtime surfaces must be reported as quality debt and must not be hidden behind `SOURCE_BACKED_STRONG`.
- Preserve runtime JSON leanness: per-card runtime value rows contain only `comment`, `condition`, and `value`.
- Do not emit normal-package `Presume.json`, `Concede.json`, or aggregate `CardBehavior.json`.
- Preserve the Darkbishop boundary: `SW_448` may retain start-of-game / hero-power-transform behavior, but must not become a Mulligan keep without explicit opening-hand source text.
- End implementation with a clean worktree. If code changes pass verification, commit them.

---

## File Structure

- Modify: `src/hsconfig/config_quality_contract.py`
  - Responsibility: existing diagnostic-only package-quality sentinel. Add trace completeness, closure freshness, stray CardID runtime file, and report-only mechanic runtime checks.
- Modify: `tests/test_config_quality_contract.py`
  - Responsibility: focused unit tests for the new diagnostic checks and non-blocking guarantees.
- Modify: `src/hsconfig/contract_doctor.py`
  - Responsibility: render compact counts for the new `config_quality` sections without changing top-level doctor status.
- Modify: `tests/test_contract_doctor.py`
  - Responsibility: prove `contract-doctor` exposes the new diagnostics and stays diagnostic-only.
- Modify: `docs/operator/README.md`
  - Responsibility: document the v2 quality trace checklist in one compact operator note.
- Modify: `.agents/skills/hsconfig/SKILL.md`
  - Responsibility: keep the repo-local skill mirror aligned with the diagnostic contract.
- Read-only: `src/hsconfig/operator_summary.py`
  - Responsibility: existing source-to-runtime closure summary shape; no change expected.
- Read-only: `src/hsconfig/source_to_runtime_explainability.py`
  - Responsibility: existing card-readable closure and evidence-chain report shape; no change expected.
- Read-only: `src/hsconfig/mechanic_support.py`
  - Responsibility: existing executable mechanic lowering policy authority; import only if needed.
- Read-only: `src/hsconfig/mechanic_drift.py`
  - Responsibility: existing mechanic drift report shape; no change expected.

---

### Task 1: Add Config Quality Trace Completeness Tests

**Files:**
- Modify: `tests/test_config_quality_contract.py`

**Interfaces:**
- Consumes:
  ```python
  build_config_quality_report(package: str | pathlib.Path) -> dict[str, typing.Any]
  ```
- Produces new report section:
  ```python
  report["checks"]["trace_completeness"] == {
      "runtime_rows_missing_trace": list[dict[str, str]],
      "traced_card_ids": list[str],
      "runtime_card_ids": list[str],
  }
  ```
- Produces new problem:
  ```python
  {"check": "card_behavior_runtime_row_missing_trace", "value": [...]}
  ```

- [ ] **Step 1: Extend the clean package fixture with source trace data**

  In `tests/test_config_quality_contract.py`, update `minimal_clean_package()` so the existing `source_to_runtime_explainability.json` write has a real evidence chain:

  ```python
  write_json(
      package / "reports" / "source_to_runtime_explainability.json",
      {
          "default_only_runtime_surfaces": [],
          "summary": {
              "cards_total": 1,
              "claims_total": 1,
              "runtime_lowered_claims": 1,
              "next_report_to_open": "reports/source_to_runtime_explainability.json",
          },
          "claim_rows": [
              {
                  "claim_id": "claim_mind_sear_effect",
                  "claim_kind": "targeting_rule",
                  "builder_or_router_decision": "emitted",
                  "emitted_runtime_files": ["NX2_019.json"],
                  "first_missing_link": None,
              }
          ],
          "card_rows": [
              {
                  "card_id": "NX2_019",
                  "first_missing_link": None,
                  "source_lane": "runtime_lowered",
                  "emitted_runtime_files": ["NX2_019.json"],
                  "runtime_surfaces": ["cardid"],
                  "closure": {
                      "lane": "source_backed_runtime_lowered",
                      "runtime_surfaces": ["NX2_019.json"],
                      "default_only_risk": False,
                  },
                  "evidence_chain": [
                      {
                          "claim_id": "claim_mind_sear_effect",
                          "claim_kind": "targeting_rule",
                          "source_lane": "runtime_lowered",
                          "source_type": "deck_matched_public_guide",
                          "runtime_files": ["NX2_019.json"],
                          "resolution_reason": "emitted",
                      }
                  ],
              }
          ],
      },
  )
  ```

- [ ] **Step 2: Add the clean trace assertion to the baseline test**

  In `test_config_quality_report_is_clean_for_source_backed_runtime_lean_package()`, add:

  ```python
  assert report["checks"]["trace_completeness"] == {
      "runtime_rows_missing_trace": [],
      "traced_card_ids": ["NX2_019"],
      "runtime_card_ids": ["NX2_019"],
  }
  ```

- [ ] **Step 3: Add a red test for a runtime CardID row with no source trace**

  Add this test:

  ```python
  def test_config_quality_flags_cardid_runtime_rows_without_source_trace(
      tmp_path: Path,
  ):
      package = minimal_clean_package(tmp_path)
      write_json(
          package / "reports" / "source_to_runtime_explainability.json",
          {
              "default_only_runtime_surfaces": [],
              "summary": {
                  "cards_total": 1,
                  "claims_total": 0,
                  "runtime_lowered_claims": 0,
                  "next_report_to_open": "reports/source_to_runtime_explainability.json",
              },
              "claim_rows": [],
              "card_rows": [
                  {
                      "card_id": "NX2_019",
                      "first_missing_link": None,
                      "source_lane": "report_only",
                      "emitted_runtime_files": [],
                      "runtime_surfaces": [],
                      "closure": {
                          "lane": "baseline_only_visible",
                          "runtime_surfaces": [],
                          "default_only_risk": True,
                      },
                      "evidence_chain": [],
                  }
              ],
          },
      )

      report = build_config_quality_report(package)

      assert report["status"] == "attention"
      assert report["checks"]["trace_completeness"]["runtime_rows_missing_trace"] == [
          {
              "card_id": "NX2_019",
              "behavior_block": "BeforeBattlecryTargetBonus",
              "value": "10",
          }
      ]
      assert {
          "check": "card_behavior_runtime_row_missing_trace",
          "value": [
              {
                  "card_id": "NX2_019",
                  "behavior_block": "BeforeBattlecryTargetBonus",
                  "value": "10",
              }
          ],
      } in report["problems"]
      assert report["apply_blocking"] is False
  ```

- [ ] **Step 4: Add a red test proving static effect semantics can satisfy trace**

  Add this test:

  ```python
  def test_config_quality_accepts_official_static_semantics_runtime_trace(
      tmp_path: Path,
  ):
      package = minimal_clean_package(tmp_path)
      write_json(
          package / "reports" / "source_to_runtime_explainability.json",
          {
              "default_only_runtime_surfaces": [],
              "summary": {
                  "cards_total": 1,
                  "claims_total": 1,
                  "runtime_lowered_claims": 1,
                  "next_report_to_open": "reports/source_to_runtime_explainability.json",
              },
              "claim_rows": [
                  {
                      "claim_id": "claim_static_mind_sear",
                      "claim_kind": "targeting_rule",
                      "builder_or_router_decision": "emitted",
                      "emitted_runtime_files": ["NX2_019.json"],
                      "first_missing_link": None,
                  }
              ],
              "card_rows": [
                  {
                      "card_id": "NX2_019",
                      "first_missing_link": None,
                      "source_lane": "official_static_semantics",
                      "emitted_runtime_files": ["NX2_019.json"],
                      "closure": {
                          "lane": "source_backed_runtime_lowered",
                          "runtime_surfaces": ["NX2_019.json"],
                          "default_only_risk": False,
                      },
                      "evidence_chain": [
                          {
                              "claim_id": "claim_static_mind_sear",
                              "claim_kind": "targeting_rule",
                              "source_lane": "official_static_semantics",
                              "source_type": "official_static_semantics",
                              "runtime_files": ["NX2_019.json"],
                              "resolution_reason": "emitted",
                          }
                      ],
                  }
              ],
          },
      )

      report = build_config_quality_report(package)

      assert report["checks"]["trace_completeness"]["runtime_rows_missing_trace"] == []
      assert report["status"] == "clean"
  ```

- [ ] **Step 5: Run red trace tests**

  ```powershell
  cd C:\Users\darbo\Documents\HSConfig
  python -m pytest tests\test_config_quality_contract.py::test_config_quality_report_is_clean_for_source_backed_runtime_lean_package tests\test_config_quality_contract.py::test_config_quality_flags_cardid_runtime_rows_without_source_trace tests\test_config_quality_contract.py::test_config_quality_accepts_official_static_semantics_runtime_trace -q -p no:cacheprovider
  ```

  Expected result before implementation:

  ```text
  FAILED ... KeyError: 'trace_completeness'
  ```

---

### Task 2: Implement Trace Completeness In The Existing Sentinel

**Files:**
- Modify: `src/hsconfig/config_quality_contract.py`

**Interfaces:**
- Add internal helpers:
  ```python
  SOURCE_TRACE_LANES: set[str]
  SOURCE_TRACE_TYPES: set[str]
  def _trace_completeness_check(
      card_behavior: collections.abc.Mapping[str, typing.Any],
      explainability: collections.abc.Mapping[str, typing.Any],
  ) -> dict[str, typing.Any]
  def _traced_card_ids(explainability: collections.abc.Mapping[str, typing.Any]) -> set[str]
  def _row_card_id(row: collections.abc.Mapping[str, typing.Any]) -> str
  def _file_card_id(value: object) -> str
  ```

- [ ] **Step 1: Add source-trace constants**

  Near existing constants in `src/hsconfig/config_quality_contract.py`, add:

  ```python
  SOURCE_TRACE_LANES = {
      "runtime_lowered",
      "runtime_lowerable",
      "deck_matched_public_guide",
      "archetype_matched_public_guide",
      "evergreen_wild_archetype",
      "official_static_semantics",
      "source_backed_static_semantics",
  }

  SOURCE_TRACE_TYPES = {
      "deck_matched_public_guide",
      "archetype_matched_public_guide",
      "evergreen_wild_archetype",
      "official_static_semantics",
      "static_semantics",
  }
  ```

- [ ] **Step 2: Wire the check into `build_config_quality_report()`**

  In the `checks = { ... }` block, add the new section after `source_to_runtime_explainability`:

  ```python
  "trace_completeness": _trace_completeness_check(card_behavior, explainability),
  ```

- [ ] **Step 3: Implement trace completeness**

  Add these helpers before `_runtime_json_check()`:

  ```python
  def _trace_completeness_check(
      card_behavior: Mapping[str, Any],
      explainability: Mapping[str, Any],
  ) -> dict[str, Any]:
      runtime_rows = _meaningful_cardid_rows(card_behavior)
      traced = _traced_card_ids(explainability)
      missing = [
          _compact_behavior_row(row)
          for row in runtime_rows
          if _row_card_id(row) not in traced
      ]
      return {
          "runtime_rows_missing_trace": missing,
          "traced_card_ids": sorted(traced),
          "runtime_card_ids": sorted({_row_card_id(row) for row in runtime_rows}),
      }


  def _meaningful_cardid_rows(card_behavior: Mapping[str, Any]) -> list[Mapping[str, Any]]:
      rows = card_behavior.get("rows", [])
      if not isinstance(rows, list):
          return []
      return [
          row
          for row in rows
          if isinstance(row, Mapping) and _is_meaningful_cardid_row(row)
      ]


  def _compact_behavior_row(row: Mapping[str, Any]) -> dict[str, str]:
      return {
          "card_id": _row_card_id(row),
          "behavior_block": str(row.get("behavior_block", "")),
          "value": str(row.get("value", "")),
      }


  def _traced_card_ids(explainability: Mapping[str, Any]) -> set[str]:
      traced: set[str] = set()

      claim_rows = explainability.get("claim_rows", [])
      if isinstance(claim_rows, list):
          for row in claim_rows:
              if not isinstance(row, Mapping):
                  continue
              if str(row.get("builder_or_router_decision", "")) != "emitted":
                  continue
              for emitted_file in _string_list(row.get("emitted_runtime_files")):
                  card_id = _file_card_id(emitted_file)
                  if card_id:
                      traced.add(card_id)

      card_rows = explainability.get("card_rows", [])
      if isinstance(card_rows, list):
          for row in card_rows:
              if not isinstance(row, Mapping):
                  continue
              if not _card_row_has_source_trace(row):
                  continue
              card_id = _row_card_id(row)
              if card_id:
                  traced.add(card_id)
              for emitted_file in _string_list(row.get("emitted_runtime_files")):
                  file_card_id = _file_card_id(emitted_file)
                  if file_card_id:
                      traced.add(file_card_id)

      return traced


  def _card_row_has_source_trace(row: Mapping[str, Any]) -> bool:
      if _source_trace_value(row.get("source_lane")):
          return True
      closure = row.get("closure")
      if isinstance(closure, Mapping) and _source_trace_value(closure.get("lane")):
          return True
      evidence_chain = row.get("evidence_chain", [])
      if not isinstance(evidence_chain, list):
          return False
      return any(
          isinstance(item, Mapping)
          and (
              _source_trace_value(item.get("source_lane"))
              or _source_trace_type(item.get("source_type"))
              or str(item.get("resolution_reason", "")) == "emitted"
          )
          and _string_list(item.get("runtime_files"))
          for item in evidence_chain
      )


  def _source_trace_value(value: Any) -> bool:
      return str(value or "") in SOURCE_TRACE_LANES


  def _source_trace_type(value: Any) -> bool:
      return str(value or "") in SOURCE_TRACE_TYPES


  def _row_card_id(row: Mapping[str, Any]) -> str:
      return str(row.get("card_id", "") or row.get("card", "")).strip()


  def _file_card_id(value: Any) -> str:
      name = Path(str(value or "")).name
      if not name.endswith(".json") or name in SPECIAL_RUNTIME_FILES:
          return ""
      return name[:-5]
  ```

- [ ] **Step 4: Add a local `_string_list()` helper**

  Add before `_read_json()`:

  ```python
  def _string_list(value: Any) -> list[str]:
      if isinstance(value, str):
          return [value] if value else []
      if not isinstance(value, list):
          return []
      return [str(item) for item in value if str(item)]
  ```

- [ ] **Step 5: Deduplicate existing compact row construction**

  In `_card_behavior_check()`, replace the inline `compact = {...}` block with:

  ```python
  compact = _compact_behavior_row(row)
  ```

  Do not change existing value-range or semantic-score behavior.

- [ ] **Step 6: Add trace problem emission**

  In `_problems()`, after explainability problems and before card behavior semantic-score problems, add:

  ```python
  trace = checks["trace_completeness"]
  if trace["runtime_rows_missing_trace"]:
      problems.append(
          {
              "check": "card_behavior_runtime_row_missing_trace",
              "value": trace["runtime_rows_missing_trace"],
          }
      )
  ```

- [ ] **Step 7: Run trace tests**

  ```powershell
  cd C:\Users\darbo\Documents\HSConfig
  python -m pytest tests\test_config_quality_contract.py::test_config_quality_report_is_clean_for_source_backed_runtime_lean_package tests\test_config_quality_contract.py::test_config_quality_flags_cardid_runtime_rows_without_source_trace tests\test_config_quality_contract.py::test_config_quality_accepts_official_static_semantics_runtime_trace -q -p no:cacheprovider
  ```

  Expected result:

  ```text
  3 passed
  ```

---

### Task 3: Add Closure Freshness Diagnostics

**Files:**
- Modify: `tests/test_config_quality_contract.py`
- Modify: `src/hsconfig/config_quality_contract.py`

**Interfaces:**
- Consumes:
  ```python
  operator_summary["source_to_runtime_explainability_summary"]
  ```
- Produces:
  ```python
  report["checks"]["closure_freshness"] == {
      "present": bool,
      "closure_schema_current": bool,
      "cards_missing_closure": int,
      "cards_total": int,
      "cards_with_closure": int,
  }
  ```
- Produces problems:
  ```python
  {"check": "source_to_runtime_closure_summary_missing", "value": "operator_summary.json"}
  {"check": "source_to_runtime_closure_not_current", "value": False}
  {"check": "source_to_runtime_closure_rows_missing", "value": int}
  ```

- [ ] **Step 1: Add closure summary to the clean package fixture**

  In `minimal_clean_package()`, add this to the fixture `operator_summary.json` payload:

  ```python
  "source_to_runtime_explainability_summary": {
      "non_blocking": True,
      "cards_total": 1,
      "claims_total": 1,
      "runtime_lowered_claims": 1,
      "closure_lane_counts": {"source_backed_runtime_lowered": 1},
      "cards_with_closure": 1,
      "cards_missing_closure": 0,
      "closure_schema_current": True,
      "next_report_to_open": "reports/source_to_runtime_explainability.json",
  },
  ```

- [ ] **Step 2: Add baseline closure assertion**

  In the clean baseline test, add:

  ```python
  assert report["checks"]["closure_freshness"] == {
      "present": True,
      "closure_schema_current": True,
      "cards_missing_closure": 0,
      "cards_total": 1,
      "cards_with_closure": 1,
  }
  ```

- [ ] **Step 3: Add stale-closure red test**

  Add:

  ```python
  def test_config_quality_flags_stale_source_to_runtime_closure_summary(
      tmp_path: Path,
  ):
      package = minimal_clean_package(tmp_path)
      operator = json.loads(
          (package / "reports" / "operator_summary.json").read_text(encoding="utf-8")
      )
      operator["source_to_runtime_explainability_summary"] = {
          "non_blocking": True,
          "cards_total": 2,
          "cards_with_closure": 1,
          "cards_missing_closure": 1,
          "closure_schema_current": False,
          "next_report_to_open": "reports/source_to_runtime_explainability.json",
      }
      write_json(package / "reports" / "operator_summary.json", operator)

      report = build_config_quality_report(package)

      assert report["status"] == "attention"
      assert report["checks"]["closure_freshness"] == {
          "present": True,
          "closure_schema_current": False,
          "cards_missing_closure": 1,
          "cards_total": 2,
          "cards_with_closure": 1,
      }
      assert {
          "check": "source_to_runtime_closure_not_current",
          "value": False,
      } in report["problems"]
      assert {
          "check": "source_to_runtime_closure_rows_missing",
          "value": 1,
      } in report["problems"]
      assert report["apply_blocking"] is False
  ```

- [ ] **Step 4: Add missing-summary red test**

  Add:

  ```python
  def test_config_quality_flags_missing_source_to_runtime_closure_summary(
      tmp_path: Path,
  ):
      package = minimal_clean_package(tmp_path)
      operator = json.loads(
          (package / "reports" / "operator_summary.json").read_text(encoding="utf-8")
      )
      operator.pop("source_to_runtime_explainability_summary")
      write_json(package / "reports" / "operator_summary.json", operator)

      report = build_config_quality_report(package)

      assert report["status"] == "attention"
      assert report["checks"]["closure_freshness"] == {
          "present": False,
          "closure_schema_current": False,
          "cards_missing_closure": 0,
          "cards_total": 0,
          "cards_with_closure": 0,
      }
      assert {
          "check": "source_to_runtime_closure_summary_missing",
          "value": "operator_summary.json",
      } in report["problems"]
      assert report["apply_blocking"] is False
  ```

- [ ] **Step 5: Implement `_closure_freshness_check()`**

  In `build_config_quality_report()`, add the check:

  ```python
  "closure_freshness": _closure_freshness_check(operator),
  ```

  Add helper:

  ```python
  def _closure_freshness_check(operator: Mapping[str, Any]) -> dict[str, Any]:
      summary = operator.get("source_to_runtime_explainability_summary")
      if not isinstance(summary, Mapping):
          return {
              "present": False,
              "closure_schema_current": False,
              "cards_missing_closure": 0,
              "cards_total": 0,
              "cards_with_closure": 0,
          }
      return {
          "present": True,
          "closure_schema_current": bool(summary.get("closure_schema_current", False)),
          "cards_missing_closure": _int_value(summary.get("cards_missing_closure", 0)),
          "cards_total": _int_value(summary.get("cards_total", 0)),
          "cards_with_closure": _int_value(summary.get("cards_with_closure", 0)),
      }
  ```

  Add integer helper near `_string_list()`:

  ```python
  def _int_value(value: Any) -> int:
      try:
          return int(value)
      except (TypeError, ValueError):
          return 0
  ```

- [ ] **Step 6: Emit closure problems**

  In `_problems()`, after the operator default-only checks, add:

  ```python
  closure = checks["closure_freshness"]
  if not closure["present"]:
      problems.append(
          {
              "check": "source_to_runtime_closure_summary_missing",
              "value": "operator_summary.json",
          }
      )
  elif not closure["closure_schema_current"]:
      problems.append(
          {
              "check": "source_to_runtime_closure_not_current",
              "value": False,
          }
      )
  if closure["cards_missing_closure"]:
      problems.append(
          {
              "check": "source_to_runtime_closure_rows_missing",
              "value": closure["cards_missing_closure"],
          }
      )
  ```

- [ ] **Step 7: Run closure tests**

  ```powershell
  cd C:\Users\darbo\Documents\HSConfig
  python -m pytest tests\test_config_quality_contract.py::test_config_quality_report_is_clean_for_source_backed_runtime_lean_package tests\test_config_quality_contract.py::test_config_quality_flags_stale_source_to_runtime_closure_summary tests\test_config_quality_contract.py::test_config_quality_flags_missing_source_to_runtime_closure_summary -q -p no:cacheprovider
  ```

  Expected result:

  ```text
  3 passed
  ```

---

### Task 4: Add Stray CardID Runtime File Detection

**Files:**
- Modify: `tests/test_config_quality_contract.py`
- Modify: `src/hsconfig/config_quality_contract.py`

**Interfaces:**
- Produces:
  ```python
  report["checks"]["runtime_json"]["stray_cardid_files"] == list[str]
  ```
- Produces problem:
  ```python
  {"check": "stray_cardid_runtime_files", "value": [...]}
  ```

- [ ] **Step 1: Add red test for stray per-card runtime file**

  Add:

  ```python
  def test_config_quality_flags_stray_cardid_runtime_file_without_report_trace(
      tmp_path: Path,
  ):
      package = minimal_clean_package(tmp_path)
      write_json(
          package / "CustomConfig" / DECK_SLUG / "STRAY_001.json",
          {
              "GameCardId": "STRAY_001",
              "BeforePlayCardBonus": {
                  "values": [
                      {
                          "comment": "unexpected stale card runtime",
                          "condition": "*",
                          "value": "6",
                      }
                  ]
              },
          },
      )

      report = build_config_quality_report(package)

      assert report["status"] == "attention"
      assert report["checks"]["runtime_json"]["stray_cardid_files"] == [
          "CustomConfig/shadowpriest/STRAY_001.json"
      ]
      assert {
          "check": "stray_cardid_runtime_files",
          "value": ["CustomConfig/shadowpriest/STRAY_001.json"],
      } in report["problems"]
      assert report["apply_blocking"] is False
  ```

- [ ] **Step 2: Change `_runtime_json_check()` signature**

  Replace:

  ```python
  def _runtime_json_check(package: Path) -> dict[str, Any]:
  ```

  with:

  ```python
  def _runtime_json_check(
      package: Path,
      card_behavior: Mapping[str, Any],
      explainability: Mapping[str, Any],
  ) -> dict[str, Any]:
  ```

  Update the call site in `build_config_quality_report()`:

  ```python
  "runtime_json": _runtime_json_check(package, card_behavior, explainability),
  ```

- [ ] **Step 3: Add expected CardID set helper**

  Add before `_runtime_json_check()`:

  ```python
  def _expected_cardid_runtime_files(
      card_behavior: Mapping[str, Any],
      explainability: Mapping[str, Any],
  ) -> set[str]:
      expected = {_row_card_id(row) for row in _meaningful_cardid_rows(card_behavior)}
      expected.update(_traced_card_ids(explainability))
      return {card_id for card_id in expected if card_id}
  ```

- [ ] **Step 4: Extend `_runtime_json_check()`**

  Inside `_runtime_json_check()`, before iterating deck directories, add:

  ```python
  expected_card_ids = _expected_cardid_runtime_files(card_behavior, explainability)
  stray_cardid_files: list[str] = []
  ```

  Inside the per-file loop after the special/forbidden skips and after reading `payload`, add:

  ```python
  runtime_card_id = str(payload.get("GameCardId") or path.stem).strip()
  if runtime_card_id and runtime_card_id not in expected_card_ids:
      stray_cardid_files.append(_relative(path, package))
  ```

  Extend the return object:

  ```python
  return {
      "deck_dir_present": bool(deck_dirs),
      "metadata_leaks": metadata_leaks,
      "stray_cardid_files": sorted(stray_cardid_files),
  }
  ```

- [ ] **Step 5: Emit stray-file problem**

  In `_problems()`, after metadata-leak handling, add:

  ```python
  if runtime_json["stray_cardid_files"]:
      problems.append(
          {
              "check": "stray_cardid_runtime_files",
              "value": runtime_json["stray_cardid_files"],
          }
      )
  ```

- [ ] **Step 6: Run runtime JSON tests**

  ```powershell
  cd C:\Users\darbo\Documents\HSConfig
  python -m pytest tests\test_config_quality_contract.py::test_config_quality_report_is_clean_for_source_backed_runtime_lean_package tests\test_config_quality_contract.py::test_config_quality_flags_stray_cardid_runtime_file_without_report_trace tests\test_config_quality_contract.py::test_config_quality_flags_diagnostic_metadata_leaking_into_runtime_json -q -p no:cacheprovider
  ```

  Expected result:

  ```text
  3 passed
  ```

---

### Task 5: Add Report-Only Mechanic Runtime Discipline

**Files:**
- Modify: `tests/test_config_quality_contract.py`
- Modify: `src/hsconfig/config_quality_contract.py`

**Interfaces:**
- Imports:
  ```python
  from hsconfig.mechanic_support import mechanic_lowering_policy
  ```
- Produces:
  ```python
  report["checks"]["mechanic_runtime_discipline"] == {
      "report_only_runtime_rows": list[dict[str, str]],
      "unregistered_mechanics": list[str],
  }
  ```
- Produces problem:
  ```python
  {"check": "report_only_mechanic_emitted_runtime", "value": [...]}
  ```

- [ ] **Step 1: Add red test for report-only mechanic emitted as runtime**

  Add:

  ```python
  def test_config_quality_flags_report_only_mechanic_runtime_emission(
      tmp_path: Path,
  ):
      package = minimal_clean_package(tmp_path)
      write_json(
          package / "reports" / "card_behavior_plan_report.json",
          {
              "rows": [
                  {
                      "card_id": "TRADEABLE_001",
                      "surface_family": "CARDID.json",
                      "behavior_block": "BeforePlayCardBonus",
                      "value": "6",
                      "meaningful_runtime_surface": True,
                      "mechanic": "tradeable",
                      "semantic_score": {
                          "band": "default",
                          "reason": "semantic_default",
                          "profile": "semantic_intent",
                      },
                  }
              ]
          },
      )
      write_json(
          package / "reports" / "source_to_runtime_explainability.json",
          {
              "default_only_runtime_surfaces": [],
              "summary": {
                  "cards_total": 1,
                  "claims_total": 1,
                  "runtime_lowered_claims": 1,
                  "next_report_to_open": "reports/source_to_runtime_explainability.json",
              },
              "claim_rows": [
                  {
                      "claim_id": "claim_tradeable",
                      "claim_kind": "mechanic_usage",
                      "builder_or_router_decision": "emitted",
                      "emitted_runtime_files": ["TRADEABLE_001.json"],
                      "first_missing_link": None,
                  }
              ],
              "card_rows": [
                  {
                      "card_id": "TRADEABLE_001",
                      "source_lane": "runtime_lowered",
                      "emitted_runtime_files": ["TRADEABLE_001.json"],
                      "closure": {
                          "lane": "source_backed_runtime_lowered",
                          "runtime_surfaces": ["TRADEABLE_001.json"],
                      },
                      "evidence_chain": [
                          {
                              "claim_id": "claim_tradeable",
                              "claim_kind": "mechanic_usage",
                              "source_lane": "runtime_lowered",
                              "runtime_files": ["TRADEABLE_001.json"],
                              "resolution_reason": "emitted",
                          }
                      ],
                  }
              ],
          },
      )
      write_json(
          package / "CustomConfig" / DECK_SLUG / "TRADEABLE_001.json",
          {
              "GameCardId": "TRADEABLE_001",
              "BeforePlayCardBonus": {
                  "values": [
                      {
                          "comment": "should not lower tradeable generically",
                          "condition": "*",
                          "value": "6",
                      }
                  ]
              },
          },
      )

      report = build_config_quality_report(package)

      assert report["status"] == "attention"
      assert report["checks"]["mechanic_runtime_discipline"][
          "report_only_runtime_rows"
      ] == [
          {
              "card_id": "TRADEABLE_001",
              "mechanic": "tradeable",
              "behavior_block": "BeforePlayCardBonus",
              "value": "6",
          }
      ]
      assert {
          "check": "report_only_mechanic_emitted_runtime",
          "value": [
              {
                  "card_id": "TRADEABLE_001",
                  "mechanic": "tradeable",
                  "behavior_block": "BeforePlayCardBonus",
                  "value": "6",
              }
          ],
      } in report["problems"]
      assert report["apply_blocking"] is False
  ```

- [ ] **Step 2: Import mechanic policy**

  In `src/hsconfig/config_quality_contract.py`, add:

  ```python
  from hsconfig.mechanic_support import mechanic_lowering_policy
  ```

- [ ] **Step 3: Wire the discipline check**

  In `build_config_quality_report()`, add:

  ```python
  "mechanic_runtime_discipline": _mechanic_runtime_discipline_check(card_behavior),
  ```

- [ ] **Step 4: Implement mechanic runtime discipline**

  Add before `_runtime_json_check()`:

  ```python
  def _mechanic_runtime_discipline_check(
      card_behavior: Mapping[str, Any],
  ) -> dict[str, Any]:
      rows = _meaningful_cardid_rows(card_behavior)
      report_only_rows: list[dict[str, str]] = []
      unregistered: set[str] = set()

      for row in rows:
          mechanic = str(row.get("mechanic", "") or "").strip()
          if not mechanic:
              continue
          policy = mechanic_lowering_policy(mechanic)
          if policy.get("suppression_reason") == "unregistered_mechanic_runtime_surface":
              unregistered.add(mechanic)
          if policy.get("policy") != "report_only":
              continue
          report_only_rows.append(
              {
                  "card_id": _row_card_id(row),
                  "mechanic": mechanic,
                  "behavior_block": str(row.get("behavior_block", "")),
                  "value": str(row.get("value", "")),
              }
          )

      return {
          "report_only_runtime_rows": report_only_rows,
          "unregistered_mechanics": sorted(unregistered),
      }
  ```

- [ ] **Step 5: Emit mechanic discipline problems**

  In `_problems()`, before `return problems`, add:

  ```python
  mechanic = checks["mechanic_runtime_discipline"]
  if mechanic["report_only_runtime_rows"]:
      problems.append(
          {
              "check": "report_only_mechanic_emitted_runtime",
              "value": mechanic["report_only_runtime_rows"],
          }
      )
  ```

  Do not emit a problem only for `unregistered_mechanics`. Unregistered future mechanics are visible diagnostics and no-block unless they produce runtime rows.

- [ ] **Step 6: Run mechanic discipline tests**

  ```powershell
  cd C:\Users\darbo\Documents\HSConfig
  python -m pytest tests\test_config_quality_contract.py::test_config_quality_report_is_clean_for_source_backed_runtime_lean_package tests\test_config_quality_contract.py::test_config_quality_flags_report_only_mechanic_runtime_emission tests\test_mechanic_support.py tests\test_mechanic_lowering_parity.py -q -p no:cacheprovider
  ```

  Expected result:

  ```text
  all selected tests pass
  ```

---

### Task 6: Compact Contract Doctor Rendering And Tests

**Files:**
- Modify: `tests/test_contract_doctor.py`
- Modify: `src/hsconfig/contract_doctor.py`

**Interfaces:**
- Existing public functions remain unchanged:
  ```python
  def build_contract_doctor_report(package: pathlib.Path) -> dict[str, typing.Any]:
  def render_contract_doctor_markdown(report: collections.abc.Mapping[str, typing.Any]) -> str:
  ```

- [ ] **Step 1: Extend the Markdown test**

  In `test_contract_doctor_markdown_includes_config_quality_section()`, add:

  ```python
  assert "Trace rows missing source: " in markdown
  assert "Closure current: " in markdown
  assert "Stray CardID files: " in markdown
  assert "Report-only mechanic runtime rows: " in markdown
  ```

- [ ] **Step 2: Add small renderer helpers**

  In `src/hsconfig/contract_doctor.py`, add near `_int_value()`:

  ```python
  def _count(value: Any) -> int:
      if isinstance(value, list):
          return len(value)
      if isinstance(value, Mapping):
          return len(value)
      return 0
  ```

- [ ] **Step 3: Render compact v2 fields**

  In `render_contract_doctor_markdown()`, after:

  ```python
  config_quality = _mapping(report.get("config_quality"))
  ```

  add:

  ```python
  config_quality_checks = _mapping(config_quality.get("checks"))
  trace_quality = _mapping(config_quality_checks.get("trace_completeness"))
  closure_quality = _mapping(config_quality_checks.get("closure_freshness"))
  runtime_quality = _mapping(config_quality_checks.get("runtime_json"))
  mechanic_quality = _mapping(
      config_quality_checks.get("mechanic_runtime_discipline")
  )
  ```

  In the `## Config Quality` section, after `Problems`, add:

  ```python
  f"- Trace rows missing source: {_count(trace_quality.get('runtime_rows_missing_trace'))}",
  f"- Closure current: {closure_quality.get('closure_schema_current', False)}",
  f"- Closure rows missing: {closure_quality.get('cards_missing_closure', 0)}",
  f"- Stray CardID files: {_count(runtime_quality.get('stray_cardid_files'))}",
  f"- Report-only mechanic runtime rows: {_count(mechanic_quality.get('report_only_runtime_rows'))}",
  ```

  Keep the existing top-level doctor status behavior unchanged.

- [ ] **Step 4: Run doctor tests**

  ```powershell
  cd C:\Users\darbo\Documents\HSConfig
  python -m pytest tests\test_contract_doctor.py tests\test_config_quality_contract.py -q -p no:cacheprovider
  ```

  Expected result:

  ```text
  all selected tests pass
  ```

---

### Task 7: Add ShadowPriest And Universal Wild Regression Assertions

**Files:**
- Modify: `tests/test_shadowpriest_e2e.py`
- Modify: `tests/test_universal_wild_no_block_matrix.py`

**Interfaces:**
- Reuses existing imported `build_config_quality_report()`.
- Adds assertions against:
  ```python
  quality["checks"]["trace_completeness"]
  quality["checks"]["closure_freshness"]
  quality["checks"]["runtime_json"]["stray_cardid_files"]
  quality["checks"]["mechanic_runtime_discipline"]["report_only_runtime_rows"]
  ```

- [ ] **Step 1: Inspect existing package-root variables**

  ```powershell
  cd C:\Users\darbo\Documents\HSConfig
  rg -n "quality = build_config_quality_report|04_package|source_to_runtime_explainability_summary|runtime_json|mechanic_runtime" tests\test_shadowpriest_e2e.py tests\test_universal_wild_no_block_matrix.py
  ```

- [ ] **Step 2: Extend ShadowPriest assertions**

  In the existing ShadowPriest test that already builds `quality`, add:

  ```python
  assert quality["checks"]["trace_completeness"]["runtime_rows_missing_trace"] == []
  assert quality["checks"]["closure_freshness"]["closure_schema_current"] is True
  assert quality["checks"]["closure_freshness"]["cards_missing_closure"] == 0
  assert quality["checks"]["runtime_json"]["stray_cardid_files"] == []
  assert quality["checks"]["mechanic_runtime_discipline"][
      "report_only_runtime_rows"
  ] == []
  ```

- [ ] **Step 3: Extend Universal Wild no-block matrix assertions**

  Inside the existing matrix loop after `quality = build_config_quality_report(...)`, add:

  ```python
  assert quality["apply_blocking"] is False
  assert quality["runtime_write_performed"] is False
  assert quality["checks"]["runtime_json"]["stray_cardid_files"] == []
  assert quality["checks"]["mechanic_runtime_discipline"][
      "report_only_runtime_rows"
  ] == []
  ```

  Do not require every representative deck to be `SOURCE_BACKED_STRONG`; this remains source-depth visibility, not a no-block requirement.

- [ ] **Step 4: Run representative regressions**

  ```powershell
  cd C:\Users\darbo\Documents\HSConfig
  python -m pytest tests\test_shadowpriest_e2e.py tests\test_universal_wild_no_block_matrix.py -q -p no:cacheprovider
  ```

  Expected result:

  ```text
  all selected tests pass
  ```

---

### Task 8: Update Operator And Skill Documentation

**Files:**
- Modify: `docs/operator/README.md`
- Modify: `.agents/skills/hsconfig/SKILL.md`

**Interfaces:**
- No runtime code interfaces.
- Documentation must preserve:
  ```text
  operator_summary.json remains the only normal apply authority.
  contract-doctor is diagnostic-only.
  config-quality warnings are visible quality debt, not apply blockers.
  ```

- [ ] **Step 1: Update operator README**

  In `docs/operator/README.md`, in the existing `config_quality` paragraph, replace the current two-sentence description with:

  ```markdown
  `hsconfig contract-doctor --package <04_package> --json` includes a diagnostic-only
  `config_quality` section. It checks no-default-only visibility, CardID semantic
  score coverage, runtime JSON leanness, forbidden legacy surfaces, the Darkbishop
  effect-not-mulligan boundary, source-to-runtime trace completeness, closure
  freshness, stray CardID runtime files, and report-only mechanic runtime drift. It
  does not replace `reports/operator_summary.json`, does not apply runtime files,
  and does not block a technically valid package.
  ```

- [ ] **Step 2: Update repo-local hsconfig skill mirror**

  In `.agents/skills/hsconfig/SKILL.md`, extend the current `contract-doctor` sentence to:

  ```markdown
  Optional diagnostic: `hsconfig contract-doctor --package <package> --json` may expose
  `config_quality` for no-default-only visibility, source-to-runtime trace completeness,
  closure freshness, runtime JSON leanness, report-only mechanic drift, and
  effect-not-mulligan canaries; operator_summary.json remains the only normal apply
  authority.
  ```

- [ ] **Step 3: Run docs-sensitive tests**

  ```powershell
  cd C:\Users\darbo\Documents\HSConfig
  python -m pytest tests\test_operator_docs_contract_policy.py tests\test_skill_files.py tests\test_contract_doctor.py -q -p no:cacheprovider
  ```

  Expected result:

  ```text
  all selected tests pass
  ```

---

### Task 9: Full Verification, Currentness, And Commit

**Files:**
- All changed files.

- [ ] **Step 1: Run focused quality and contract tests**

  ```powershell
  cd C:\Users\darbo\Documents\HSConfig
  python -m pytest tests\test_config_quality_contract.py tests\test_contract_doctor.py tests\test_shadowpriest_e2e.py tests\test_universal_wild_no_block_matrix.py tests\test_mechanic_support.py tests\test_mechanic_lowering_parity.py -q -p no:cacheprovider
  ```

  Expected result:

  ```text
  all selected tests pass
  ```

- [ ] **Step 2: Run source/contract spine guardrails**

  ```powershell
  cd C:\Users\darbo\Documents\HSConfig
  python scripts\check_contract_guardrails.py
  python -m hsconfig.cli contract-spine-sentinel --json
  ```

  Expected properties:

  ```text
  contract-spine-sentinel status remains clean
  operator_gate_impact remains diagnostic_only
  apply_blocking remains false
  report_ownership_gate_files remains ["reports/operator_summary.json"]
  ```

- [ ] **Step 3: Run the no-second-gate and no-default-only contracts**

  ```powershell
  cd C:\Users\darbo\Documents\HSConfig
  python -m pytest tests\test_no_second_gate_contract.py tests\test_no_default_only_semantic_archetype_matrix.py tests\test_source_contract_conformance.py tests\test_source_to_runtime_explainability.py tests\test_source_contract_audit.py tests\test_source_contract_spine_freeze.py -q -p no:cacheprovider
  ```

  Expected result:

  ```text
  all selected tests pass
  ```

- [ ] **Step 4: Run full test suite**

  ```powershell
  cd C:\Users\darbo\Documents\HSConfig
  python -m pytest -q -p no:cacheprovider
  ```

  Expected result:

  ```text
  full suite passes
  ```

- [ ] **Step 5: Verify currentness and clean artifacts**

  ```powershell
  cd C:\Users\darbo\Documents\HSConfig
  python scripts\check_hsconfig_currentness.py --cwd . --json
  git diff --check
  git status --short --branch
  ```

  Expected currentness properties:

  ```text
  behind_count is 0
  working_tree_dirty is false after commit
  ```

  If test cache or temporary verification output appears, remove generated-only artifacts:

  ```powershell
  Remove-Item -LiteralPath .pytest_cache -Recurse -Force -ErrorAction SilentlyContinue
  Remove-Item -LiteralPath tmp\verify-config-quality-trace-v2 -Recurse -Force -ErrorAction SilentlyContinue
  git status --short
  ```

- [ ] **Step 6: Commit verified implementation**

  ```powershell
  cd C:\Users\darbo\Documents\HSConfig
  git add src\hsconfig\config_quality_contract.py src\hsconfig\contract_doctor.py tests\test_config_quality_contract.py tests\test_contract_doctor.py tests\test_shadowpriest_e2e.py tests\test_universal_wild_no_block_matrix.py docs\operator\README.md .agents\skills\hsconfig\SKILL.md
  git commit -m "feat: add config quality trace completeness diagnostics"
  git status --short --branch
  ```

  Expected final state:

  ```text
  ## codex/hsconfig-semantic-intent-scoring...origin/codex/hsconfig-semantic-intent-scoring [ahead N]
  ```

  The worktree must have no uncommitted changes.

---

## Subagent Split

- **Explorer Agent:** Read-only check of current `config_quality_contract.py`, `source_to_runtime_explainability.py`, `operator_summary.py`, `mechanic_support.py`, and package report shapes. Output exact field names only.
- **Trace Worker Agent:** Implement Tasks 1-2 only. Writes `tests/test_config_quality_contract.py` and `src/hsconfig/config_quality_contract.py`.
- **Closure/Runtime Worker Agent:** Implement Tasks 3-4 only. Writes the same two files after Trace Worker completes; no parallel write to those files.
- **Mechanic Worker Agent:** Implement Task 5 only after Closure/Runtime Worker completes. Writes the same two files; uses `mechanic_support.py` read-only.
- **Doctor/Docs Agent:** Implement Tasks 6 and 8. Writes `contract_doctor.py`, `test_contract_doctor.py`, `docs/operator/README.md`, and `.agents/skills/hsconfig/SKILL.md`.
- **Regression Agent:** Implement Task 7 after the config-quality API is stable. Writes only ShadowPriest and Universal Wild tests.
- **Final Reviewer Agent:** Read-only diff review for second-gate risk, default-only visibility, report-only mechanic discipline, and worktree cleanliness.
- **Main Agent:** Owns sequencing, conflict resolution, full verification, artifact cleanup, and the final commit.

No two subagents write the same file concurrently. The main agent resolves integration issues and must not delegate final success claims.

---

## Acceptance Criteria

- `build_config_quality_report()` remains deterministic and read-only.
- `config_quality.authority == "diagnostic_only"` for every readable package.
- `config_quality.apply_blocking is False` for every readable package.
- `config_quality.runtime_write_performed is False` for every readable package.
- `reports/operator_summary.json` remains the only normal apply authority.
- `SOURCE_BACKED_STRONG` remains an evidence-quality label and is not used as a runtime-write gate.
- Meaningful CardID runtime rows without source-to-runtime trace appear as `card_behavior_runtime_row_missing_trace`.
- Official/static effect semantics can satisfy trace only when they are surfaced in the explainability evidence chain or source lane for the matching card/runtime file.
- Missing or stale `source_to_runtime_explainability_summary` appears as visible config-quality debt.
- Per-card runtime JSON files with no report trace appear as `stray_cardid_runtime_files`.
- Report-only mechanics such as `tradeable`, `dredge`, `imbue`, `forge`, `excavate`, `titan`, `tourist`, and unknown future mechanics do not emit runtime rows merely because they were detected.
- Unregistered mechanics are visible diagnostics but do not block valid package generation or apply.
- Runtime per-card JSON value rows still allow only `comment`, `condition`, and `value`.
- Normal packages still do not emit `Presume.json`, `Concede.json`, or aggregate `CardBehavior.json`.
- ShadowPriest keeps `SW_448` out of Mulligan unless explicit opening-hand source text exists.
- Representative Wild decks remain no-block and runtime-lean.
- `contract-doctor` renders compact v2 config-quality counters.
- Documentation says the v2 checks are diagnostic-only and not apply authority.
- Focused tests pass:
  ```powershell
  python -m pytest tests\test_config_quality_contract.py tests\test_contract_doctor.py tests\test_shadowpriest_e2e.py tests\test_universal_wild_no_block_matrix.py tests\test_mechanic_support.py tests\test_mechanic_lowering_parity.py -q -p no:cacheprovider
  ```
- Guardrails pass:
  ```powershell
  python scripts\check_contract_guardrails.py
  python -m hsconfig.cli contract-spine-sentinel --json
  ```
- Full suite passes:
  ```powershell
  python -m pytest -q -p no:cacheprovider
  ```
- Final worktree has no uncommitted changes.

---

## Self-Review Checklist

- [ ] Plan extends the already implemented Config Quality Sentinel; it does not recreate it.
- [ ] Plan changes diagnostics only and adds no runtime writer.
- [ ] Plan does not use logs, HSTuner, winrate, replay, or post-game evidence.
- [ ] Plan keeps `operator_summary.json` as the normal apply authority.
- [ ] Plan keeps `SOURCE_BACKED_STRONG` honest and source-backed.
- [ ] Plan keeps default-only and stale-closure debt visible.
- [ ] Plan keeps runtime JSON lean.
- [ ] Plan includes runtime-row trace coverage and stray file detection.
- [ ] Plan includes report-only mechanic discipline.
- [ ] Plan preserves Darkbishop effect-not-mulligan canary coverage.
- [ ] Plan has concrete test code, implementation snippets, exact commands, and expected outcomes.
- [ ] Plan has no placeholder markers or deferred-detail steps.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-21-hsconfig-config-quality-trace-completeness-v2.md`. Two execution options:

**1. Subagent-Driven (recommended)** - dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** - execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?

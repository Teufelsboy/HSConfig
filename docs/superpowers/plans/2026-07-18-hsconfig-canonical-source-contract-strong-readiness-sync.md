# HSConfig Canonical Source Contract Strong Readiness Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make HSConfig source/contract readiness self-checking across generated packages, research-deep result snapshots, source-closure diagnostics, and the representative Wild deck matrix so `SOURCE_BACKED_STRONG` is only reported when fully source-backed, no default-only runtime surface is hidden, and valid packages remain load-safe and non-blocked even when source evidence is partial.

**Architecture:** Keep `reports/operator_summary.json` as the only normal apply authority. Extend the existing diagnostic-only layer instead of adding a second apply gate: `research-status-sync` remains the canonical package vs research snapshot comparator, `source-closure-optimizer` becomes the compact multi-package status view that also embeds research snapshot relation and refresh action, and `research_result_validator` keeps strict source-result and `fields.yaml` shape checks. Add narrow tests around the exact failure modes: stale research snapshot, false Strong promotion, default-only Strong blocker, source-status non-blocking, ShadowPriest effect-only semantics, and clean 12-deck matrix readiness.

**Tech Stack:** Python 3.11+, pytest, existing HSConfig CLI, existing JSON helpers, PowerShell verification commands, no new runtime writer, no new dependency.

## Global Constraints

- Do not add a new runtime-write or apply gate. `reports/operator_summary.json` remains the only normal apply authority.
- `SOURCE_BACKED_STRONG` is an evidence-quality label. It must not be used as a required precondition for load-safe package generation or runtime apply.
- Default-only runtime surfaces must never be hidden. They block Strong promotion, not package generation.
- Research-deep result snapshots are diagnostic inputs. They can recommend refresh or repair, but cannot promote or downgrade the canonical package status by themselves.
- Candidate URLs, snippets, decklists, static metadata without supported effect semantics, and aggregate stats cannot prove `SOURCE_BACKED_STRONG`.
- ShadowPriest remains the canary for the Darkbishop Benedictus distinction: the start-of-game / hero-power transform effect stays encoded, but the card itself is not an opening-hand mulligan keep unless explicit source text supports that claim.
- All CLI output added here is diagnostic-only and must reject runtime output paths such as `CustomConfig`, `Mulligan.json`, `GlobalValues.json`, `Combo.json`, numeric per-card JSON files, `deck_config.ini`, and `operator_summary.json`.
- Keep the repo current before implementation and clean after implementation. Do not leave generated reports, temporary outputs, cache folders, or uncommitted files behind.

---

## Phase 0: Currentness, Baseline, and Worktree Gate

- [ ] **Step 0.1: Refresh repository state**

  Run from `C:\Users\darbo\Documents\HSConfig`:

  ```powershell
  git fetch --all --prune --tags
  git status --short --branch
  python scripts\check_hsconfig_currentness.py --cwd . --json
  ```

  Expected:

  - `git status --short --branch` shows the active working branch and no changed files.
  - `check_hsconfig_currentness.py` reports `"dirty": false`.
  - `check_hsconfig_currentness.py` reports `"clean_for_runtime_work": true`.
  - If the branch is behind a matching upstream, fast-forward before editing. If it cannot fast-forward cleanly, stop implementation and report the exact branch divergence.

- [ ] **Step 0.2: Run the focused baseline**

  ```powershell
  python -m pytest `
    tests\test_research_result_validator.py `
    tests\test_research_status_sync.py `
    tests\test_research_status_sync_cli.py `
    tests\test_source_closure_optimizer.py `
    tests\test_source_closure_optimizer_cli.py `
    tests\test_source_closure_priority_queue.py `
    tests\test_source_status_resolver.py `
    tests\test_claim_kind_runtime_contract.py `
    tests\test_universal_wild_no_block_matrix.py `
    -q
  ```

  Expected:

  - Existing tests pass before changes.
  - If a test fails before changes, capture the failing test name and error and diagnose it before modifying code.

---

## Phase 1: Research Contract Shape Stays Explicit

- [ ] **Step 1.1: Add an acceptance-loop fields contract regression test**

  Modify `tests/test_research_result_validator.py`.

  Add imports:

  ```python
  from pathlib import Path

  import yaml
  ```

  Add this test:

  ```python
  def test_source_contract_acceptance_loop_fields_cover_status_sync_contract() -> None:
      fields_path = Path(
          "docs/research/2026-07-17-hsconfig-source-contract-acceptance-loop/fields.yaml"
      )
      payload = yaml.safe_load(fields_path.read_text(encoding="utf-8"))

      result = validate_fields_yaml_payload(payload)

      assert result["valid"] is True
      assert result["source_status_apply_blocking"] is False
      assert result["field_count"] >= len(result["required_fields"])
      fields = payload["fields"]
      assert "full_text_claim_sources" in fields
      assert "promotion_boundary" in fields
      assert "source_status_apply_blocking_expected" in fields
      assert "default_only_runtime_surfaces_expected" in fields
  ```

  Run:

  ```powershell
  python -m pytest tests\test_research_result_validator.py -q
  ```

  Expected:

  - The test passes with the current `fields.yaml`.
  - If it fails, update only `docs/research/2026-07-17-hsconfig-source-contract-acceptance-loop/fields.yaml` to include the missing explicit fields. Do not alter research conclusions to satisfy the test.

- [ ] **Step 1.2: Add source-result validation for source-status booleans**

  Modify `src/hsconfig/research_result_validator.py` and `tests/test_research_result_validator.py`.

  Add two optional result-field checks:

  - If `source_status_apply_blocking_expected` exists, it must be boolean.
  - If `default_only_runtime_surfaces_expected` exists, it must be either `"none"` or a non-empty explanatory string.

  Add tests:

  ```python
  def test_research_result_validator_accepts_source_contract_status_fields() -> None:
      result = validate_research_result_payload(
          {
              "deck_name": "PirateDH",
              "archetype": "Wild Pirate Demon Hunter",
              "current_deck_sources": [],
              "guide_sources": [],
              "source_strength": "decklist_or_stats_only",
              "lowerable_claim_kinds": [],
              "non_promoting_support": [],
              "first_missing_source_action": "add_card_specific_source_claim",
              "source_status_apply_blocking_expected": False,
              "default_only_runtime_surfaces_expected": "none",
              "notes": "Source gaps are diagnostic only.",
          }
      )

      assert result["valid"] is True
      assert result["source_status_apply_blocking"] is False
  ```

  ```python
  def test_research_result_validator_rejects_malformed_source_contract_status_fields() -> None:
      result = validate_research_result_payload(
          {
              "deck_name": "PirateDH",
              "archetype": "Wild Pirate Demon Hunter",
              "current_deck_sources": [],
              "guide_sources": [],
              "source_strength": "decklist_or_stats_only",
              "lowerable_claim_kinds": [],
              "non_promoting_support": [],
              "first_missing_source_action": "add_card_specific_source_claim",
              "source_status_apply_blocking_expected": "false",
              "default_only_runtime_surfaces_expected": "",
              "notes": "Malformed source contract status fields.",
          }
      )

      assert result["valid"] is False
      assert "source_status_apply_blocking_expected_must_be_boolean" in result["errors"]
      assert "default_only_runtime_surfaces_expected_must_name_status" in result["errors"]
      assert result["source_status_apply_blocking"] is False
  ```

  Implementation detail:

  ```python
  def _source_contract_status_field_errors(payload: Mapping[str, Any]) -> list[str]:
      errors: list[str] = []
      if (
          "source_status_apply_blocking_expected" in payload
          and not isinstance(payload["source_status_apply_blocking_expected"], bool)
      ):
          errors.append("source_status_apply_blocking_expected_must_be_boolean")
      if "default_only_runtime_surfaces_expected" in payload:
          value = payload["default_only_runtime_surfaces_expected"]
          if not isinstance(value, str) or not value.strip():
              errors.append("default_only_runtime_surfaces_expected_must_name_status")
      return errors
  ```

  Call `_source_contract_status_field_errors(payload)` inside `validate_research_result_payload`.

  Run:

  ```powershell
  python -m pytest tests\test_research_result_validator.py -q
  ```

  Expected:

  - Both new tests pass.
  - Existing Strong/default-only validator behavior remains unchanged.

---

## Phase 2: Embed Research Snapshot Relation in Source Closure Optimizer

- [ ] **Step 2.1: Add failing optimizer tests for research sync fields**

  Modify `tests/test_source_closure_optimizer.py`.

  Add helper:

  ```python
  def _write_research_result(tmp_path: Path, deck_name: str, payload: dict) -> Path:
      result = tmp_path / "research" / f"{deck_name}.json"
      result.parent.mkdir(parents=True, exist_ok=True)
      result.write_text(json.dumps(payload, indent=2), encoding="utf-8")
      return result
  ```

  Add test:

  ```python
  def test_optimizer_exposes_stale_research_relation_without_changing_strong_decision(
      tmp_path: Path,
  ) -> None:
      package = _write_package(tmp_path, _operator())
      stale = _write_research_result(
          tmp_path,
          "ShadowPriest",
          {
              "deck_name": "ShadowPriest",
              "deck_code": "AAEBAa0GExample",
              "source_strength": "unfetched_acquisition_seed",
              "first_missing_source_action": "fetch_and_normalize_candidate_full_text_claims",
              "lowerable_claim_kinds": [],
              "archetype": "Wild Shadow Priest",
              "current_deck_sources": [],
              "guide_sources": [],
              "non_promoting_support": [],
              "notes": "Complete seed snapshot.",
          },
      )

      report = build_source_closure_optimizer_report(
          package,
          research_result_paths=[stale],
      )

      assert report["decision"] == "strong"
      assert report["source_status_apply_blocking"] is False
      assert report["research_result_found"] is True
      assert report["research_snapshot_relation"] == "stale_or_seed_only"
      assert report["research_recommended_refresh_action"] == (
          "refresh_research_snapshot_from_canonical_package"
      )
      assert report["research_canonical_promotion_allowed"] is False
      assert report["research_canonical_downgrade_allowed"] is False
  ```

  Add test:

  ```python
  def test_optimizer_reports_missing_research_snapshot_without_apply_blocking(
      tmp_path: Path,
  ) -> None:
      package = _write_package(tmp_path, _operator())

      report = build_source_closure_optimizer_report(
          package,
          research_result_paths=[],
      )

      assert report["decision"] == "strong"
      assert report["research_result_found"] is False
      assert report["research_snapshot_relation"] == "missing"
      assert report["research_recommended_refresh_action"] == (
          "refresh_research_snapshot_from_canonical_package"
      )
      assert report["source_status_apply_blocking"] is False
  ```

  Run:

  ```powershell
  python -m pytest tests\test_source_closure_optimizer.py -q
  ```

  Expected before implementation:

  - The new tests fail with `TypeError: build_source_closure_optimizer_report() got an unexpected keyword argument 'research_result_paths'` or missing research fields.

- [ ] **Step 2.2: Implement compact research sync embedding**

  Modify `src/hsconfig/source_closure_optimizer.py`.

  Add import:

  ```python
  from collections.abc import Sequence

  from hsconfig.research_status_sync import build_research_status_sync_report
  ```

  Update signature:

  ```python
  def build_source_closure_optimizer_report(
      package_dir: str | Path,
      *,
      candidate_proof_path: str | Path | None = None,
      dossier: Mapping[str, Any] | None = None,
      research_result_paths: Sequence[str | Path] | None = None,
  ) -> dict[str, Any]:
  ```

  Inside the function, after `research_dossier` is set:

  ```python
  research_sync = _research_sync_payload(package_path, research_result_paths)
  research_sync_summary = dict(research_sync.get("summary") or {}) if research_sync else {}
  research_primary = _primary_research_sync_row(research_sync)
  ```

  Add these keys to the returned dict:

  ```python
  "research_result_found": bool(research_dossier) or bool(research_primary),
  "research_snapshot_relation": _research_snapshot_relation(
      research_sync_summary,
      research_primary,
      research_result_paths,
  ),
  "research_recommended_refresh_action": _research_refresh_action(
      research_sync_summary,
      research_primary,
      research_result_paths,
  ),
  "research_contract_valid": (
      research_primary.get("research_contract_valid") if research_primary else None
  ),
  "strict_research_result_valid": (
      research_primary.get("strict_research_result_valid") if research_primary else None
  ),
  "research_canonical_promotion_allowed": False,
  "research_canonical_downgrade_allowed": False,
  "research_sync_summary": research_sync_summary,
  ```

  Replace the existing duplicate `"research_result_found"` key if present.

  Add helpers:

  ```python
  def _research_sync_payload(
      package_path: Path,
      research_result_paths: Sequence[str | Path] | None,
  ) -> dict[str, Any]:
      if research_result_paths is None:
          return {}
      return build_research_status_sync_report(package_path, research_result_paths)
  ```

  ```python
  def _primary_research_sync_row(
      research_sync: Mapping[str, Any],
  ) -> dict[str, Any]:
      rows = research_sync.get("research_snapshot_rows") if research_sync else []
      if not isinstance(rows, list):
          return {}
      matching = [
          row
          for row in rows
          if isinstance(row, Mapping)
          and row.get("snapshot_relation") != "different_deck_snapshot"
      ]
      if not matching:
          return {}
      return dict(matching[0])
  ```

  ```python
  def _research_snapshot_relation(
      summary: Mapping[str, Any],
      primary: Mapping[str, Any],
      research_result_paths: Sequence[str | Path] | None,
  ) -> str:
      if research_result_paths is None:
          return "not_evaluated"
      if primary:
          return str(primary.get("snapshot_relation") or "unknown")
      if summary.get("missing_research_snapshot") is True:
          return "missing"
      return "missing"
  ```

  ```python
  def _research_refresh_action(
      summary: Mapping[str, Any],
      primary: Mapping[str, Any],
      research_result_paths: Sequence[str | Path] | None,
  ) -> str:
      if research_result_paths is None:
          return "not_evaluated"
      if primary:
          return str(primary.get("recommended_refresh_action") or "inspect_research_snapshot")
      if summary.get("missing_research_snapshot") is True:
          return "refresh_research_snapshot_from_canonical_package"
      return "inspect_research_snapshot"
  ```

  Keep the old `research_source_strength` and `research_first_missing_source_action` fields sourced from `dossier` for compatibility.

  Run:

  ```powershell
  python -m pytest tests\test_source_closure_optimizer.py -q
  ```

  Expected:

  - All optimizer unit tests pass.
  - Existing callers still pass because `research_result_paths` defaults to `None`.

---

## Phase 3: Wire Research Results into the CLI Optimizer

- [ ] **Step 3.1: Add CLI parser support**

  Modify `src/hsconfig/cli_parser.py`.

  Add to the `source-closure-optimizer` parser:

  ```python
  source_closure_optimizer.add_argument(
      "--research-results-dir",
      help=(
          "Optional directory or JSON file with research-deep result snapshots. "
          "Used only for diagnostic freshness and refresh-action fields."
      ),
  )
  ```

- [ ] **Step 3.2: Pass research result paths through the command**

  Modify `src/hsconfig/commands/source_workflow.py`.

  In `run_source_closure_optimizer_command`, compute:

  ```python
  research_result_paths = (
      _research_result_paths(Path(args.research_results_dir))
      if getattr(args, "research_results_dir", None)
      else None
  )
  ```

  Then pass it:

  ```python
  build_source_closure_optimizer_report(
      package_dir=package,
      candidate_proof_path=args.candidate_proof_json,
      research_result_paths=research_result_paths,
  )
  ```

  Do not write back into research result files or package files.

- [ ] **Step 3.3: Extend optimizer Markdown output**

  Modify `_format_source_closure_optimizer_markdown` in `src/hsconfig/commands/source_workflow.py`.

  Replace the table header with:

  ```python
  "| Deck | Decision | Runtime usable | First missing source action | Default-only surfaces | Research relation | Research refresh action |",
  "| --- | --- | --- | --- | --- | --- | --- |",
  ```

  Replace the row format with:

  ```python
  "| {deck} | `{decision}` | `{usable}` | `{action}` | `{default_only}` | `{research_relation}` | `{research_action}` |".format(
      deck=report["deck_name"],
      decision=report["decision"],
      usable=report["runtime_package_usable"],
      action=report["first_missing_source_action"],
      default_only=default_only,
      research_relation=report.get("research_snapshot_relation", "not_evaluated"),
      research_action=report.get("research_recommended_refresh_action", "not_evaluated"),
  )
  ```

- [ ] **Step 3.4: Add CLI regression tests**

  Modify `tests/test_source_closure_optimizer_cli.py`.

  Add test:

  ```python
  def test_source_closure_optimizer_cli_includes_research_snapshot_relation(
      tmp_path: Path,
  ) -> None:
      package = _write_package(tmp_path, "ShadowPriest")
      research = tmp_path / "research"
      research.mkdir()
      (research / "ShadowPriest.json").write_text(
          json.dumps(
              {
                  "deck_name": "ShadowPriest",
                  "deck_code": "AAEBAa0GExample",
                  "archetype": "Wild Shadow Priest",
                  "current_deck_sources": [],
                  "guide_sources": [],
                  "source_strength": "unfetched_acquisition_seed",
                  "lowerable_claim_kinds": [],
                  "non_promoting_support": [],
                  "first_missing_source_action": (
                      "fetch_and_normalize_candidate_full_text_claims"
                  ),
                  "notes": "Seed-only snapshot.",
              },
              indent=2,
          ),
          encoding="utf-8",
      )
      out_json = tmp_path / "diagnostics" / "source_closure_optimizer.json"
      out_md = tmp_path / "diagnostics" / "source_closure_optimizer.md"

      exit_code = main(
          [
              "source-closure-optimizer",
              "--package",
              str(package),
              "--research-results-dir",
              str(research),
              "--out",
              str(out_json),
              "--markdown-out",
              str(out_md),
          ]
      )

      assert exit_code == 0
      payload = json.loads(out_json.read_text(encoding="utf-8"))
      report = payload["reports"][0]
      assert report["decision"] == "strong"
      assert report["source_status_apply_blocking"] is False
      assert report["research_snapshot_relation"] == "stale_or_seed_only"
      assert report["research_recommended_refresh_action"] == (
          "refresh_research_snapshot_from_canonical_package"
      )
      assert "Research relation" in out_md.read_text(encoding="utf-8")
  ```

  Run:

  ```powershell
  python -m pytest tests\test_source_closure_optimizer_cli.py -q
  ```

  Expected:

  - The new CLI test passes.
  - Existing unsafe-output tests still pass.

---

## Phase 4: Matrix Invariants for Any Valid Wild Deck

- [ ] **Step 4.1: Extend priority queue summary counts**

  Modify `src/hsconfig/source_closure_optimizer.py`.

  In `build_source_closure_priority_queue`, add summary fields:

  ```python
  "research_missing_count": sum(
      1 for row in records if row.get("research_snapshot_relation") == "missing"
  ),
  "research_stale_or_seed_count": sum(
      1 for row in records if row.get("research_snapshot_relation") == "stale_or_seed_only"
  ),
  "research_conflict_count": sum(
      1 for row in records if row.get("research_snapshot_relation") == "conflicts_with_canonical"
  ),
  "research_repair_count": sum(
      1 for row in records if row.get("research_snapshot_relation") == "requires_research_result_repair"
  ),
  ```

  Update `tests/test_source_closure_priority_queue.py`:

  ```python
  def test_priority_queue_counts_research_refresh_actions_without_apply_blocking(
      tmp_path: Path,
  ) -> None:
      package = _package(
          tmp_path,
          "ShadowPriest",
          {
              "source_backed_status": "SOURCE_BACKED_STRONG",
              "semantic_status": "SOURCE_BACKED_STRONG",
              "first_missing_source_action": "none",
              "source_backed_strong_closure": {
                  "status": "ready",
                  "promotion_ready": True,
                  "first_missing_source_action": "none",
                  "diagnostic_only": True,
                  "closure_profile_closed": True,
              },
          },
      )
      research = tmp_path / "research-results"
      research.mkdir()
      (research / "ShadowPriest.json").write_text(
          json.dumps(
              {
                  "deck_name": "ShadowPriest",
                  "deck_code": "AAEBAa0GExample",
                  "archetype": "Wild Shadow Priest",
                  "current_deck_sources": [],
                  "guide_sources": [],
                  "source_strength": "unfetched_acquisition_seed",
                  "lowerable_claim_kinds": [],
                  "non_promoting_support": [],
                  "first_missing_source_action": (
                      "fetch_and_normalize_candidate_full_text_claims"
                  ),
                  "notes": "Seed-only snapshot.",
              },
              indent=2,
          ),
          encoding="utf-8",
      )

      report = build_source_closure_priority_queue(
          [package],
          research_results_dir=research,
      )

      assert report["summary"]["strong_count"] == 1
      assert report["summary"]["apply_blocker_count"] == 0
      assert report["summary"]["research_stale_or_seed_count"] == 1
      assert report["summary"]["research_conflict_count"] == 0
      assert report["records"][0]["research_canonical_promotion_allowed"] is False
      assert report["records"][0]["research_canonical_downgrade_allowed"] is False
  ```

  Implement by passing `research_result_paths` from the priority queue builder into each optimizer report. Preserve existing `dossier` compatibility only for legacy `research_source_strength` fields.

  Run:

  ```powershell
  python -m pytest tests\test_source_closure_priority_queue.py -q
  ```

  Expected:

  - Summary counts show research freshness debt without treating it as apply blocking.

- [ ] **Step 4.2: Add a ShadowPriest effect-only guard to the verification set**

  Run the existing claim-kind tests:

  ```powershell
  python -m pytest tests\test_claim_kind_runtime_contract.py -q
  ```

  If no test explicitly checks Darkbishop Benedictus effect-vs-keep, add one in `tests/test_claim_kind_runtime_contract.py` using the existing local helpers in that file.

  Required assertions:

  - Darkbishop Benedictus effect/hero-power transform semantics remain present in the runtime-facing per-card behavior or GlobalValues effect surface.
  - Darkbishop Benedictus is not emitted as an unconditional Mulligan keep.
  - The source claim kind for the effect is not normalized into `mulligan_keep`.

  Run:

  ```powershell
  python -m pytest tests\test_claim_kind_runtime_contract.py -q
  ```

  Expected:

  - ShadowPriest still preserves the effect while avoiding the mistaken opening-hand keep.

- [ ] **Step 4.3: Run no-block matrix after source-status changes**

  ```powershell
  python -m pytest `
    tests\test_source_status_resolver.py `
    tests\test_universal_wild_no_block_matrix.py `
    -q
  ```

  Expected:

  - All representative decks remain technically valid or diagnostically explain invalidity according to the existing matrix fixtures.
  - `default_only_runtime_surfaces` is empty for the generated representative packages in the load-safe matrix.
  - `source_status_apply_blocking` remains `false` for valid packages.
  - `SOURCE_BACKED_STRONG` appears only when the package has closed evidence and no default-only surfaces.

---

## Phase 5: Operator Documentation, Lean and Precise

- [ ] **Step 5.1: Update source-backed Strong documentation**

  Modify `docs/operator/source-backed-strong-closure.md`.

  Add a short subsection under the existing `research-status-sync` / `source-closure-optimizer` text:

  ```md
  ### Optimizer Research Snapshot Fields

  `source-closure-optimizer --research-results-dir ...` embeds compact research
  freshness diagnostics for each package:

  - `research_snapshot_relation` explains whether the matching research result
    is current, stale/seed-only, missing, conflicting, or requires repair.
  - `research_recommended_refresh_action` names the next diagnostic source sync
    action.
  - `research_canonical_promotion_allowed=false` and
    `research_canonical_downgrade_allowed=false` are intentional: research
    snapshots never promote or downgrade the canonical package.

  These fields are diagnostic-only. They do not replace
  `reports/operator_summary.json`, do not create an apply gate, and do not write
  runtime files.
  ```

- [ ] **Step 5.2: Update operator README command example**

  Modify `docs/operator/README.md`.

  Add a compact example near the existing source-closure optimizer section:

  ```powershell
  python -m hsconfig.cli source-closure-optimizer `
    --package outputs\latest\ShadowPriest\04_package `
    --research-results-dir docs\research\2026-07-17-hsconfig-source-contract-acceptance-loop\results `
    --out outputs\diagnostics\source_closure_optimizer.json `
    --markdown-out outputs\diagnostics\source_closure_optimizer.md
  ```

  Add one sentence:

  ```md
  Use the research relation fields to refresh stale research snapshots; do not
  use them to override `operator_summary.json` or to block a valid load-safe
  package.
  ```

  Keep the docs short. Do not restate the whole source contract.

- [ ] **Step 5.3: Run docs and CLI contract tests**

  ```powershell
  python -m pytest `
    tests\test_operator_docs_contract_policy.py `
    tests\test_research_result_validator.py `
    tests\test_research_status_sync.py `
    tests\test_research_status_sync_cli.py `
    tests\test_source_closure_optimizer.py `
    tests\test_source_closure_optimizer_cli.py `
    tests\test_source_closure_priority_queue.py `
    -q
  ```

  Expected:

  - Docs policy tests pass.
  - Diagnostic-only CLI guards still reject unsafe output paths.

---

## Phase 6: End-to-End Verification

- [ ] **Step 6.1: Run focused contract verification**

  ```powershell
  python -m pytest `
    tests\test_research_result_validator.py `
    tests\test_research_result_contract.py `
    tests\test_research_status_sync.py `
    tests\test_research_status_sync_cli.py `
    tests\test_source_closure_optimizer.py `
    tests\test_source_closure_optimizer_cli.py `
    tests\test_source_closure_priority_queue.py `
    tests\test_source_status_resolver.py `
    tests\test_claim_kind_runtime_contract.py `
    tests\test_universal_wild_no_block_matrix.py `
    -q
  ```

  Expected:

  - All selected tests pass.
  - No source-status diagnostic becomes apply blocking.
  - Default-only surfaces block Strong but not valid load-safe generation.

- [ ] **Step 6.2: Run full test suite if focused tests pass**

  ```powershell
  python -m pytest -q
  ```

  Expected:

  - Full suite passes.
  - If full suite is too slow or fails for unrelated pre-existing reasons, record the exact command, failure, and why it is unrelated before committing.

- [ ] **Step 6.3: Run one read-only diagnostic report without committing generated output**

  Use a temporary output path under `outputs\_tmp_source_contract_sync`:

  ```powershell
  New-Item -ItemType Directory -Force outputs\_tmp_source_contract_sync | Out-Null
  python -m hsconfig.cli source-closure-optimizer `
    --package outputs\2026-07-18-source-closure-strong-promotion-r4\ShadowPriest\04_package `
    --research-results-dir docs\research\2026-07-17-hsconfig-source-contract-acceptance-loop\results `
    --out outputs\_tmp_source_contract_sync\source_closure_optimizer.json `
    --markdown-out outputs\_tmp_source_contract_sync\source_closure_optimizer.md
  ```

  Inspect:

  ```powershell
  python - <<'PY'
  import json
  from pathlib import Path
  path = Path("outputs/_tmp_source_contract_sync/source_closure_optimizer.json")
  data = json.loads(path.read_text(encoding="utf-8"))
  report = data["reports"][0]
  print(report["deck_name"])
  print(report["decision"])
  print(report["source_status_apply_blocking"])
  print(report["research_snapshot_relation"])
  print(report["research_recommended_refresh_action"])
  print(report["research_canonical_promotion_allowed"])
  print(report["research_canonical_downgrade_allowed"])
  PY
  ```

  Expected:

  ```text
  ShadowPriest
  strong
  False
  stale_or_seed_only
  refresh_research_snapshot_from_canonical_package
  False
  False
  ```

  Remove the temporary output before commit:

  ```powershell
  Remove-Item -Recurse -Force outputs\_tmp_source_contract_sync
  ```

  Run:

  ```powershell
  git status --short
  ```

  Expected:

  - No generated diagnostic output remains.
  - Only intended source, tests, and docs files are changed.

---

## Phase 7: Commit and Clean-Worktree Completion

- [ ] **Step 7.1: Review the diff**

  ```powershell
  git diff -- src\hsconfig\research_result_validator.py `
    src\hsconfig\source_closure_optimizer.py `
    src\hsconfig\commands\source_workflow.py `
    src\hsconfig\cli_parser.py `
    tests\test_research_result_validator.py `
    tests\test_source_closure_optimizer.py `
    tests\test_source_closure_optimizer_cli.py `
    tests\test_source_closure_priority_queue.py `
    tests\test_claim_kind_runtime_contract.py `
    docs\operator\source-backed-strong-closure.md `
    docs\operator\README.md
  ```

  Confirm:

  - Changes are limited to the planned files.
  - No generated package, runtime, cache, or private evidence file is staged.
  - No code path writes to HearthRanger runtime from these diagnostics.
  - No path named `operator_summary.json` can be overwritten by diagnostic output.

- [ ] **Step 7.2: Run final status and tests**

  ```powershell
  python -m pytest -q
  git status --short --branch
  ```

  Expected:

  - Tests pass or any unrelated failure is documented with exact evidence.
  - Worktree shows only files intended for this implementation.

- [ ] **Step 7.3: Commit implementation**

  ```powershell
  git add `
    src\hsconfig\research_result_validator.py `
    src\hsconfig\source_closure_optimizer.py `
    src\hsconfig\commands\source_workflow.py `
    src\hsconfig\cli_parser.py `
    tests\test_research_result_validator.py `
    tests\test_source_closure_optimizer.py `
    tests\test_source_closure_optimizer_cli.py `
    tests\test_source_closure_priority_queue.py `
    tests\test_claim_kind_runtime_contract.py `
    docs\operator\source-backed-strong-closure.md `
    docs\operator\README.md
  git commit -m "feat: sync source closure diagnostics with research snapshots"
  git status --short --branch
  ```

  Expected:

  - Commit succeeds.
  - Final `git status --short --branch` is clean except for branch/ahead metadata.

---

## Success Criteria

- `source-closure-optimizer` can optionally consume research result snapshots and expose research freshness, repair, and refresh actions in both JSON and Markdown.
- Research snapshots remain diagnostic-only and cannot promote, downgrade, or block canonical package status.
- `SOURCE_BACKED_STRONG` still requires closed source evidence, no default-only surfaces, and `first_missing_source_action=none`.
- Default-only runtime surfaces remain visible Strong blockers, not hidden successes and not source-status apply blockers.
- ShadowPriest remains the canary for effect-vs-opening-hand semantics: Darkbishop Benedictus effect behavior stays encoded while the card itself is not kept as a mulligan card without explicit opening-hand source evidence.
- Focused tests and full suite pass, or any unrelated full-suite failure is captured with exact evidence.
- No runtime files, generated outputs, logs, caches, or private evidence are committed.
- Worktree is clean at completion.


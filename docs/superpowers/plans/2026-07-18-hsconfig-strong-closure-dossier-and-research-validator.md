# HSConfig Strong Closure Dossier And Research Validator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a thin diagnostic `strong-closure-dossier` layer and strict HSConfig research-result validation so optimal configs keep building for every deck while `SOURCE_BACKED_STRONG` remains honest, non-default-only, and evidence-backed.

**Architecture:** Do not replace the existing source contract spine. Reuse `reports/operator_summary.json`, `source_claim_gap_report.json`, `source_autopilot_report.json`, `strong_promotion_report.py`, and `research_result_contract.py`; add one read-only dossier builder plus one strict validator that summarizes why a deck is Strong, Partial, Seed-only, or invalid. The dossier and validator are diagnostic-only and never grant apply authority.

**Tech Stack:** Python stdlib, existing HSConfig CLI/parser pattern, existing JSON IO helpers, pytest. No new dependency is allowed.

## Global Constraints

- Work only in `C:\Users\darbo\Documents\HSConfig`.
- Start every execution session with:
  ```powershell
  cd C:\Users\darbo\Documents\HSConfig
  git fetch --all --prune --tags
  git status --short --branch
  git rev-list --left-right --count HEAD...origin/main
  git log -1 --oneline
  ```
- Do not push unless the user explicitly asks.
- Do not run live runtime apply. Do not use `--apply`.
- Keep the final worktree clean. If implementation changes are made, commit them only after tests pass.
- `reports/operator_summary.json` remains the only normal runtime apply authority.
- `SOURCE_BACKED_STRONG` remains an evidence-quality label, not a generation or apply gate.
- `source_status_apply_blocking` must stay `false` for Strong, Partial, seed-only, and context-only source states.
- Candidate URLs, decklists, stats pages, and snippets are acquisition/context only until fetched, deck-matched, claim-kind-normalized, current-or-evergreen, and surface-gated.
- No default-only success is allowed: `default_only_runtime_surfaces` must prevent Strong and must remain visible in diagnostics.
- Darkbishop Benedictus must preserve start-of-game / hero-power-transform semantics, but must not become an opening-hand mulligan keep without explicit keep text.
- Live online checks are operator verification, not CI requirements. Unit tests must use deterministic local JSON/fixture payloads.
- Do not commit raw fetched pages, Hearthstone logs, HearthRanger runtime evidence, HDT exports, pytest cache, or private runtime data.

---

## File Structure

- Create: `src/hsconfig/strong_closure_dossier.py`
  - Responsibility: read prepared package diagnostics and optional research snapshots; emit one compact diagnostic-only source-closure dossier.
- Modify: `src/hsconfig/commands/source_workflow.py`
  - Responsibility: add `strong_closure_dossier_payload()` and safe `--out` writing for the new diagnostic command.
- Modify: `src/hsconfig/cli.py`
  - Responsibility: route `strong-closure-dossier`.
- Modify: `src/hsconfig/cli_parser.py`
  - Responsibility: expose `hsconfig strong-closure-dossier`.
- Create: `src/hsconfig/research_result_validator.py`
  - Responsibility: strict HSConfig-specific validation for `research-deep` JSON result files and `fields.yaml`.
- Modify: `src/hsconfig/research_status_sync.py`
  - Responsibility: include strict research validation in snapshot rows without changing canonical package authority.
- Test: `tests/test_strong_closure_dossier.py`
  - Responsibility: pure builder tests for Strong, Partial, default-only, and seed-only research states.
- Test: `tests/test_strong_closure_dossier_cli.py`
  - Responsibility: CLI output and safe output-path tests.
- Test: `tests/test_research_result_validator.py`
  - Responsibility: strict field/schema checks and weak-validator regression coverage.
- Modify: `tests/test_research_status_sync.py`
  - Responsibility: prove strict validation appears in sync output and remains diagnostic-only.
- Modify: `docs/operator/source-backed-strong-closure.md`
  - Responsibility: document the new dossier command as diagnostic-only.
- Modify: `.agents/skills/hsconfig/SKILL.md`
  - Responsibility: mention the dossier and strict research validation in the operator workflow.

---

### Task 1: Add Pure Strong Closure Dossier Builder

**Files:**
- Create: `src/hsconfig/strong_closure_dossier.py`
- Test: `tests/test_strong_closure_dossier.py`

**Interfaces:**
- Consumes:
  - `build_strong_closure_dossier(package_dir: str | Path, research_result_paths: Sequence[str | Path] = (), source_autopilot_report_path: str | Path | None = None) -> dict[str, Any]`
- Produces:
  - Diagnostic JSON with `authority="diagnostic_only"`, `normal_apply_authority="reports/operator_summary.json"`, `source_status_apply_blocking=false`, `promotion_verdict`, `strong_contract_closed`, and `first_missing_source_action`.

- [ ] **Step 1: Write failing tests for Strong, Partial, and default-only dossiers**

  Add `tests/test_strong_closure_dossier.py`:
  ```python
  from __future__ import annotations

  from pathlib import Path

  from hsconfig.io import write_json
  from hsconfig.strong_closure_dossier import build_strong_closure_dossier


  def _package(
      tmp_path: Path,
      *,
      deck_name: str = "ShadowPriest",
      source_status: str = "SOURCE_BACKED_STRONG",
      source_strong_ready: bool = True,
      first_missing_source_action: str = "none",
      default_only_runtime_surfaces: list[str] | None = None,
  ) -> Path:
      package_dir = tmp_path / "04_package"
      write_json(
          package_dir / "reports" / "operator_summary.json",
          {
              "deck": {"name": deck_name},
              "technical_status": "VALID_PACKAGE",
              "semantic_status": source_status,
              "source_backed_status": source_status,
              "source_strong_ready": source_strong_ready,
              "first_missing_source_action": first_missing_source_action,
              "source_status_apply_blocking": False,
              "source_status_diagnostic_only": True,
              "default_only_runtime_surfaces": default_only_runtime_surfaces or [],
              "no_default_only_runtime_status": (
                  "blocked"
                  if default_only_runtime_surfaces
                  else "clean"
              ),
              "runtime_apply_allowed": True,
              "runtime_apply_mode": "load_safe_apply",
              "next_action": (
                  "READY_TO_APPLY_OR_HANDOFF"
                  if source_status == "SOURCE_BACKED_STRONG"
                  else "READY_TO_APPLY_WITH_WARNINGS"
              ),
          },
      )
      write_json(
          package_dir / "reports" / "source_claim_gap_report.json",
          {
              "summary": {
                  "blocked_cards": 0 if source_status == "SOURCE_BACKED_STRONG" else 1,
                  "first_missing_chain": (
                      None
                      if source_status == "SOURCE_BACKED_STRONG"
                      else {
                          "card_id": "CARD_A",
                          "first_missing_link": "needs_guide_claim",
                          "recommended_source_claim_kind": "card_role",
                          "next_action": first_missing_source_action,
                      }
                  ),
              },
              "cards": {},
          },
      )
      return package_dir


  def test_dossier_confirms_strong_without_becoming_apply_authority(tmp_path: Path) -> None:
      package_dir = _package(tmp_path)

      report = build_strong_closure_dossier(package_dir)

      assert report["authority"] == "diagnostic_only"
      assert report["operator_gate_impact"] == "diagnostic_only"
      assert report["normal_apply_authority"] == "reports/operator_summary.json"
      assert report["deck_name"] == "ShadowPriest"
      assert report["promotion_verdict"] == "SOURCE_BACKED_STRONG_CONFIRMED"
      assert report["strong_contract_closed"] is True
      assert report["source_status_apply_blocking"] is False
      assert report["first_missing_source_action"] == "none"
      assert report["default_only_runtime_surfaces"] == []
      assert report["runtime_apply_mode"] == "load_safe_apply"


  def test_dossier_keeps_partial_load_safe_and_actionable(tmp_path: Path) -> None:
      package_dir = _package(
          tmp_path,
          deck_name="PirateDH",
          source_status="SOURCE_BACKED_PARTIAL",
          source_strong_ready=False,
          first_missing_source_action="add_card_specific_source_claim",
      )

      report = build_strong_closure_dossier(package_dir)

      assert report["deck_name"] == "PirateDH"
      assert report["promotion_verdict"] == "PROMOTION_BLOCKED"
      assert report["source_backed_status"] == "SOURCE_BACKED_PARTIAL"
      assert report["strong_contract_closed"] is False
      assert report["runtime_package_usable"] is True
      assert report["source_status_apply_blocking"] is False
      assert report["first_missing_source_action"] == "add_card_specific_source_claim"
      assert report["first_missing_chain"]["card_id"] == "CARD_A"


  def test_dossier_blocks_strong_when_default_only_surface_is_present(tmp_path: Path) -> None:
      package_dir = _package(
          tmp_path,
          source_status="SOURCE_BACKED_STRONG",
          source_strong_ready=True,
          default_only_runtime_surfaces=["mulligan"],
      )

      report = build_strong_closure_dossier(package_dir)

      assert report["promotion_verdict"] == "PROMOTION_BLOCKED"
      assert report["source_backed_status"] == "SOURCE_BACKED_PARTIAL"
      assert report["strong_contract_closed"] is False
      assert report["default_only_runtime_surfaces"] == ["mulligan"]
      assert report["source_status_apply_blocking"] is False
      assert report["first_missing_source_action"] == (
          "replace_default_only_runtime_surface_with_source_or_policy_claim"
      )
  ```

- [ ] **Step 2: Run tests to verify they fail**

  Run:
  ```powershell
  python -m pytest tests\test_strong_closure_dossier.py -q -p no:cacheprovider
  ```

  Expected:
  ```text
  ModuleNotFoundError: No module named 'hsconfig.strong_closure_dossier'
  ```

- [ ] **Step 3: Implement the pure dossier builder**

  Create `src/hsconfig/strong_closure_dossier.py`:
  ```python
  from __future__ import annotations

  from collections.abc import Sequence
  from pathlib import Path
  from typing import Any

  from hsconfig.io import read_json
  from hsconfig.research_result_contract import classify_research_result_contract
  from hsconfig.strong_promotion_report import build_strong_promotion_report

  NORMAL_APPLY_AUTHORITY = "reports/operator_summary.json"
  DIAGNOSTIC_AUTHORITY = "diagnostic_only"


  def build_strong_closure_dossier(
      package_dir: str | Path,
      research_result_paths: Sequence[str | Path] = (),
      source_autopilot_report_path: str | Path | None = None,
  ) -> dict[str, Any]:
      package_path = Path(package_dir)
      operator_summary = _read_required_json(package_path / NORMAL_APPLY_AUTHORITY)
      source_claim_gap_report = _read_optional_json(
          package_path / "reports" / "source_claim_gap_report.json",
          default={"summary": {"blocked_cards": 0}, "cards": {}},
      )
      promotion_report = build_strong_promotion_report(
          deck_name=_deck_name(operator_summary),
          fixture_stage=_fixture_stage(operator_summary),
          operator_summary=operator_summary,
          source_claim_gap_report=source_claim_gap_report,
      )
      research_rows = [
          _research_row(Path(path))
          for path in sorted(research_result_paths, key=lambda item: str(item))
      ]
      autopilot_report = (
          _read_required_json(source_autopilot_report_path)
          if source_autopilot_report_path is not None
          else None
      )
      source_backed_status = str(promotion_report["source_backed_status"])
      return {
          "schema_version": 1,
          "authority": DIAGNOSTIC_AUTHORITY,
          "operator_gate_impact": DIAGNOSTIC_AUTHORITY,
          "normal_apply_authority": NORMAL_APPLY_AUTHORITY,
          "package": str(package_path),
          "deck_name": _deck_name(operator_summary),
          "technical_status": operator_summary.get("technical_status"),
          "semantic_status": operator_summary.get("semantic_status"),
          "source_backed_status": source_backed_status,
          "source_strong_ready": bool(promotion_report["source_strong_ready"]),
          "strong_contract_closed": bool(promotion_report["promotion_ready"]),
          "promotion_verdict": promotion_report["verdict"],
          "runtime_package_usable": _runtime_package_usable(operator_summary),
          "runtime_apply_mode": operator_summary.get("runtime_apply_mode"),
          "runtime_apply_allowed": operator_summary.get("runtime_apply_allowed"),
          "source_status_apply_blocking": False,
          "source_status_diagnostic_only": True,
          "default_only_runtime_surfaces": list(
              promotion_report["default_only_runtime_surfaces"]
          ),
          "first_missing_source_action": promotion_report[
              "first_missing_source_action"
          ],
          "first_missing_chain": promotion_report["first_missing_chain"],
          "source_status_reasons": promotion_report["source_status_reasons"],
          "source_missing_source_actions": promotion_report[
              "source_missing_source_actions"
          ],
          "autopilot_preflight": _autopilot_summary(autopilot_report),
          "research_snapshot_rows": research_rows,
          "summary": _summary(
              source_backed_status=source_backed_status,
              promotion_ready=bool(promotion_report["promotion_ready"]),
              runtime_package_usable=_runtime_package_usable(operator_summary),
              default_only_runtime_surfaces=list(
                  promotion_report["default_only_runtime_surfaces"]
              ),
              research_rows=research_rows,
          ),
      }


  def _read_required_json(path: str | Path) -> dict[str, Any]:
      data = read_json(path)
      if not isinstance(data, dict):
          raise ValueError(f"{path} must contain a JSON object")
      return data


  def _read_optional_json(path: Path, *, default: dict[str, Any]) -> dict[str, Any]:
      if not path.exists():
          return default
      return _read_required_json(path)


  def _deck_name(operator_summary: dict[str, Any]) -> str:
      deck = operator_summary.get("deck", {})
      if isinstance(deck, dict):
          return str(deck.get("name") or "")
      return ""


  def _fixture_stage(operator_summary: dict[str, Any]) -> str:
      return (
          "core_source_backed_fixture"
          if operator_summary.get("source_backed_status") == "SOURCE_BACKED_STRONG"
          else "source_informed_valid_fixture"
      )


  def _runtime_package_usable(operator_summary: dict[str, Any]) -> bool:
      return (
          operator_summary.get("technical_status") == "VALID_PACKAGE"
          and bool(operator_summary.get("runtime_apply_allowed", False)) is True
          and str(operator_summary.get("runtime_apply_mode") or "")
          == "load_safe_apply"
      )


  def _autopilot_summary(report: dict[str, Any] | None) -> dict[str, Any]:
      if report is None:
          return {"status": "not_provided"}
      return {
          "status": "provided",
          "strong_candidate": bool(report.get("strong_candidate", False)),
          "default_only_runtime_surfaces": list(
              report.get("default_only_runtime_surfaces") or []
          ),
          "first_missing_source_action_by_card": dict(
              report.get("first_missing_source_action_by_card") or {}
          ),
          "first_missing_source_action_by_surface": dict(
              report.get("first_missing_source_action_by_surface") or {}
          ),
      }


  def _research_row(path: Path) -> dict[str, Any]:
      data = _read_required_json(path)
      contract = classify_research_result_contract(data)
      return {
          "path": str(path),
          "deck_name": str(data.get("deck_name") or ""),
          "source_strength": str(data.get("source_strength") or ""),
          "snapshot_kind": contract["snapshot_kind"],
          "contract_valid": contract["contract_valid"],
          "canonical_promotion_allowed": contract[
              "canonical_promotion_allowed"
          ],
          "canonical_downgrade_allowed": False,
          "source_status_apply_blocking": False,
          "errors": contract["errors"],
          "warnings": contract["warnings"],
          "lowerable_claim_kinds": contract["lowerable_claim_kinds"],
          "first_missing_source_action": str(
              data.get("first_missing_source_action") or ""
          ),
      }


  def _summary(
      *,
      source_backed_status: str,
      promotion_ready: bool,
      runtime_package_usable: bool,
      default_only_runtime_surfaces: Sequence[str],
      research_rows: Sequence[dict[str, Any]],
  ) -> dict[str, Any]:
      return {
          "source_backed_status": source_backed_status,
          "strong_contract_closed": promotion_ready,
          "runtime_package_usable": runtime_package_usable,
          "default_only_runtime_surface_count": len(default_only_runtime_surfaces),
          "research_snapshot_count": len(research_rows),
          "research_promoting_snapshot_count": sum(
              1 for row in research_rows if row["canonical_promotion_allowed"]
          ),
          "source_status_apply_blocking": False,
          "operator_action": (
              "ready"
              if promotion_ready
              else "use_package_and_close_first_missing_source_action"
          ),
      }
  ```

- [ ] **Step 4: Run pure builder tests**

  Run:
  ```powershell
  python -m pytest tests\test_strong_closure_dossier.py -q -p no:cacheprovider
  ```

  Expected:
  ```text
  3 passed
  ```

- [ ] **Step 5: Commit Task 1**

  Run:
  ```powershell
  git add src\hsconfig\strong_closure_dossier.py tests\test_strong_closure_dossier.py
  git commit -m "feat: add strong closure dossier builder"
  ```

---

### Task 2: Expose Dossier As Read-Only CLI Command

**Files:**
- Modify: `src/hsconfig/commands/source_workflow.py`
- Modify: `src/hsconfig/cli.py`
- Modify: `src/hsconfig/cli_parser.py`
- Test: `tests/test_strong_closure_dossier_cli.py`

**Interfaces:**
- Consumes:
  - `hsconfig strong-closure-dossier --package <package> [--research-results-dir <dir>] [--source-autopilot-report-json <path>] [--out <json>] [--json]`
- Produces:
  - Diagnostic JSON only. Safe `--out` may not target runtime files or package `operator_summary.json`.

- [ ] **Step 1: Write failing CLI tests**

  Add `tests/test_strong_closure_dossier_cli.py`:
  ```python
  from __future__ import annotations

  import json
  from pathlib import Path

  from hsconfig.cli import main
  from hsconfig.io import write_json


  def _package(tmp_path: Path) -> Path:
      package_dir = tmp_path / "04_package"
      write_json(
          package_dir / "reports" / "operator_summary.json",
          {
              "deck": {"name": "ShadowPriest"},
              "technical_status": "VALID_PACKAGE",
              "semantic_status": "SOURCE_BACKED_STRONG",
              "source_backed_status": "SOURCE_BACKED_STRONG",
              "source_strong_ready": True,
              "first_missing_source_action": "none",
              "source_status_apply_blocking": False,
              "source_status_diagnostic_only": True,
              "default_only_runtime_surfaces": [],
              "no_default_only_runtime_status": "clean",
              "runtime_apply_allowed": True,
              "runtime_apply_mode": "load_safe_apply",
              "next_action": "READY_TO_APPLY_OR_HANDOFF",
          },
      )
      write_json(
          package_dir / "reports" / "source_claim_gap_report.json",
          {"summary": {"blocked_cards": 0}, "cards": {}},
      )
      return package_dir


  def test_strong_closure_dossier_cli_writes_diagnostic_report(
      tmp_path: Path,
      capsys,
  ) -> None:
      package_dir = _package(tmp_path)
      research_dir = tmp_path / "research"
      write_json(
          research_dir / "shadowpriest.json",
          {
              "deck_name": "ShadowPriest",
              "source_strength": "exact_full_text_guide",
              "source_visibility": "full_text",
              "freshness_status": "current",
              "lowerable_claim_kinds": ["mulligan_keep"],
              "first_missing_source_action": "none",
          },
      )
      out = tmp_path / "strong_closure_dossier.json"

      exit_code = main(
          [
              "strong-closure-dossier",
              "--package",
              str(package_dir),
              "--research-results-dir",
              str(research_dir),
              "--out",
              str(out),
              "--json",
          ]
      )
      emitted = json.loads(capsys.readouterr().out)
      written = json.loads(out.read_text(encoding="utf-8"))

      assert exit_code == 0
      assert emitted == written
      assert emitted["authority"] == "diagnostic_only"
      assert emitted["operator_gate_impact"] == "diagnostic_only"
      assert emitted["normal_apply_authority"] == "reports/operator_summary.json"
      assert emitted["promotion_verdict"] == "SOURCE_BACKED_STRONG_CONFIRMED"
      assert emitted["summary"]["source_status_apply_blocking"] is False
      assert emitted["research_snapshot_rows"][0]["canonical_promotion_allowed"] is True


  def test_strong_closure_dossier_cli_rejects_runtime_output_path(
      tmp_path: Path,
      capsys,
  ) -> None:
      package_dir = _package(tmp_path)
      out = tmp_path / "CustomConfig" / "ShadowPriest" / "Mulligan.json"

      exit_code = main(
          [
              "strong-closure-dossier",
              "--package",
              str(package_dir),
              "--out",
              str(out),
              "--json",
          ]
      )
      emitted = json.loads(capsys.readouterr().out)

      assert exit_code == 1
      assert emitted["status"] == "failed"
      assert "must not target HearthRanger runtime files" in emitted["errors"][0]
      assert not out.exists()


  def test_strong_closure_dossier_cli_rejects_operator_summary_output_path(
      tmp_path: Path,
      capsys,
  ) -> None:
      package_dir = _package(tmp_path)
      out = package_dir / "reports" / "operator_summary.json"
      original = out.read_text(encoding="utf-8")

      exit_code = main(
          [
              "strong-closure-dossier",
              "--package",
              str(package_dir),
              "--out",
              str(out),
              "--json",
          ]
      )
      emitted = json.loads(capsys.readouterr().out)

      assert exit_code == 1
      assert emitted["status"] == "failed"
      assert "must not target package operator_summary.json" in emitted["errors"][0]
      assert out.read_text(encoding="utf-8") == original
  ```

- [ ] **Step 2: Run tests to verify they fail**

  Run:
  ```powershell
  python -m pytest tests\test_strong_closure_dossier_cli.py -q -p no:cacheprovider
  ```

  Expected:
  ```text
  argument command: invalid choice: 'strong-closure-dossier'
  ```

- [ ] **Step 3: Add command payload and safe output guard**

  Modify `src/hsconfig/commands/source_workflow.py`:
  ```python
  from hsconfig.strong_closure_dossier import build_strong_closure_dossier
  ```

  Add near the other command runners:
  ```python
  def run_strong_closure_dossier_command(args: argparse.Namespace) -> int:
      return run_payload_command(args, strong_closure_dossier_payload)
  ```

  Add after `research_status_sync_payload()`:
  ```python
  def strong_closure_dossier_payload(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
      package_dir = Path(args.package)
      report = build_strong_closure_dossier(
          package_dir=package_dir,
          research_result_paths=_research_result_paths(
              Path(args.research_results_dir)
          )
          if getattr(args, "research_results_dir", None)
          else [],
          source_autopilot_report_path=getattr(
              args, "source_autopilot_report_json", None
          ),
      )
      if getattr(args, "out", None):
          out = Path(args.out)
          _assert_safe_strong_closure_dossier_output(
              out,
              package_dir=package_dir,
          )
          write_json(out, report)
      return report, 0


  def _assert_safe_strong_closure_dossier_output(
      path: Path,
      *,
      package_dir: Path,
  ) -> None:
      parts = {part.lower() for part in path.parts}
      runtime_file_names = {
          "combo.json",
          "concede.json",
          "deck_config.ini",
          "globalvalues.json",
          "mulligan.json",
          "presume.json",
      }
      if path.suffix.lower() != ".json":
          raise ValueError(
              "strong-closure-dossier --out must be a .json diagnostic report path"
          )
      operator_summary_path = package_dir / "reports" / "operator_summary.json"
      if path.resolve() == operator_summary_path.resolve():
          raise ValueError(
              "strong-closure-dossier --out must not target package operator_summary.json"
          )
      if "customconfig" in parts or path.name.lower() in runtime_file_names:
          raise ValueError(
              "strong-closure-dossier --out must not target HearthRanger runtime files"
          )
  ```

- [ ] **Step 4: Wire CLI routing**

  Modify `src/hsconfig/cli.py` imports:
  ```python
  from hsconfig.commands.source_workflow import (
      run_draft_source_documents_command,
      run_research_deck_command,
      run_research_status_sync_command,
      run_source_acquire_command,
      run_source_autopilot_command,
      run_source_manifest_command,
      run_strong_closure_dossier_command,
  )
  ```

  Add before `research-status-sync` routing:
  ```python
      if args.command == "strong-closure-dossier":
          return run_strong_closure_dossier_command(args)
  ```

- [ ] **Step 5: Add parser entry**

  Modify `src/hsconfig/cli_parser.py` after `research_status_sync` parser:
  ```python
      strong_closure_dossier = subparsers.add_parser(
          "strong-closure-dossier",
          help="diagnostic source-backed strong closure dossier",
          description=(
              "Read a prepared package plus optional source autopilot and research "
              "snapshots, then explain why SOURCE_BACKED_STRONG is confirmed or "
              "which first source action remains. This command is diagnostic only "
              "and never writes runtime files."
          ),
      )
      strong_closure_dossier.add_argument("--package", required=True)
      strong_closure_dossier.add_argument("--research-results-dir")
      strong_closure_dossier.add_argument("--source-autopilot-report-json")
      strong_closure_dossier.add_argument("--out", help="Optional JSON output path.")
      strong_closure_dossier.add_argument("--json", action="store_true")
  ```

- [ ] **Step 6: Run CLI tests**

  Run:
  ```powershell
  python -m pytest tests\test_strong_closure_dossier_cli.py tests\test_strong_closure_dossier.py -q -p no:cacheprovider
  ```

  Expected:
  ```text
  6 passed
  ```

- [ ] **Step 7: Commit Task 2**

  Run:
  ```powershell
  git add src\hsconfig\commands\source_workflow.py src\hsconfig\cli.py src\hsconfig\cli_parser.py tests\test_strong_closure_dossier_cli.py
  git commit -m "feat: expose strong closure dossier cli"
  ```

---

### Task 3: Add Strict HSConfig Research Result Validator

**Files:**
- Create: `src/hsconfig/research_result_validator.py`
- Test: `tests/test_research_result_validator.py`
- Modify: `src/hsconfig/research_status_sync.py`
- Modify: `tests/test_research_status_sync.py`

**Interfaces:**
- Consumes:
  - `validate_research_result_payload(payload: Mapping[str, Any]) -> dict[str, Any]`
  - `validate_fields_yaml_payload(payload: Mapping[str, Any]) -> dict[str, Any]`
- Produces:
  - Strict validation status, errors, warnings, and field count that catch malformed or weak `research-deep` schemas.

- [ ] **Step 1: Write failing validator tests**

  Add `tests/test_research_result_validator.py`:
  ```python
  from __future__ import annotations

  from hsconfig.research_result_validator import (
      validate_fields_yaml_payload,
      validate_research_result_payload,
  )


  def test_research_result_validator_accepts_complete_partial_result() -> None:
      result = validate_research_result_payload(
          {
              "deck_name": "PirateDH",
              "archetype": "Wild Pirate Demon Hunter",
              "current_deck_sources": [
                  {
                      "url": "https://hearthstone-decks.net/example",
                      "source_family": "decklist_or_stats_only",
                      "promotes_strong": False,
                  }
              ],
              "guide_sources": [],
              "source_strength": "decklist_or_stats_only",
              "lowerable_claim_kinds": [],
              "non_promoting_support": [
                  "current list context exists but no full-text mulligan claim"
              ],
              "first_missing_source_action": "add_card_specific_source_claim",
              "notes": "Keep partial until exact guide text exists.",
          }
      )

      assert result["valid"] is True
      assert result["errors"] == []
      assert result["source_status_apply_blocking"] is False


  def test_research_result_validator_rejects_unknown_source_strength() -> None:
      result = validate_research_result_payload(
          {
              "deck_name": "PirateDH",
              "archetype": "Wild Pirate Demon Hunter",
              "current_deck_sources": [],
              "guide_sources": [],
              "source_strength": "strong_enough_because_current",
              "lowerable_claim_kinds": [],
              "non_promoting_support": [],
              "first_missing_source_action": "none",
              "notes": "Invalid strength.",
          }
      )

      assert result["valid"] is False
      assert "invalid_source_strength" in result["errors"]
      assert result["source_status_apply_blocking"] is False


  def test_research_result_validator_rejects_strong_without_lowerable_claims() -> None:
      result = validate_research_result_payload(
          {
              "deck_name": "ShadowPriest",
              "archetype": "Wild Shadow Priest",
              "current_deck_sources": [],
              "guide_sources": [
                  {
                      "url": "https://example.test/shadow",
                      "source_family": "exact_full_text_guide",
                      "promotes_strong": True,
                  }
              ],
              "source_strength": "exact_full_text_guide",
              "source_visibility": "full_text",
              "freshness_status": "current",
              "lowerable_claim_kinds": [],
              "non_promoting_support": [],
              "first_missing_source_action": "none",
              "notes": "Missing lowerable claims.",
          }
      )

      assert result["valid"] is False
      assert "strong_requires_lowerable_claim_kinds" in result["errors"]


  def test_fields_yaml_validator_catches_empty_or_malformed_field_map() -> None:
      result = validate_fields_yaml_payload({"fields": []})

      assert result["valid"] is False
      assert result["field_count"] == 0
      assert "fields_must_be_mapping" in result["errors"]


  def test_fields_yaml_validator_accepts_hsconfig_field_contract() -> None:
      result = validate_fields_yaml_payload(
          {
              "fields": {
                  "deck_name": {"type": "string"},
                  "archetype": {"type": "string"},
                  "current_deck_sources": {"type": "array"},
                  "guide_sources": {"type": "array"},
                  "source_strength": {"type": "string"},
                  "lowerable_claim_kinds": {"type": "array"},
                  "non_promoting_support": {"type": "array"},
                  "first_missing_source_action": {"type": "string"},
                  "notes": {"type": "string"},
              }
          }
      )

      assert result["valid"] is True
      assert result["field_count"] == 9
      assert result["errors"] == []
  ```

- [ ] **Step 2: Run tests to verify they fail**

  Run:
  ```powershell
  python -m pytest tests\test_research_result_validator.py -q -p no:cacheprovider
  ```

  Expected:
  ```text
  ModuleNotFoundError: No module named 'hsconfig.research_result_validator'
  ```

- [ ] **Step 3: Implement strict validator**

  Create `src/hsconfig/research_result_validator.py`:
  ```python
  from __future__ import annotations

  from collections.abc import Mapping
  from typing import Any

  REQUIRED_RESULT_FIELDS = {
      "deck_name",
      "archetype",
      "current_deck_sources",
      "guide_sources",
      "source_strength",
      "lowerable_claim_kinds",
      "non_promoting_support",
      "first_missing_source_action",
      "notes",
  }
  ALLOWED_SOURCE_STRENGTHS = {
      "SOURCE_BACKED_STRONG",
      "archetype_full_text_guide",
      "decklist_or_stats_only",
      "exact_full_text_guide",
      "missing",
      "static_semantics_only",
      "unfetched_acquisition_seed",
  }
  STRONG_STRENGTHS = {
      "SOURCE_BACKED_STRONG",
      "archetype_full_text_guide",
      "exact_full_text_guide",
  }
  LOWERABLE_CLAIM_KINDS = {
      "card_role",
      "choose_one_choice",
      "combo_sequence",
      "discover_choice",
      "gameplan_posture",
      "hero_power_transform",
      "known_bad_pattern",
      "mechanic_usage",
      "mulligan_discard",
      "mulligan_keep",
      "targeting_rule",
  }


  def validate_research_result_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
      errors: list[str] = []
      warnings: list[str] = []
      missing = sorted(REQUIRED_RESULT_FIELDS - set(payload))
      errors.extend(f"missing_field:{field}" for field in missing)

      source_strength = str(payload.get("source_strength") or "")
      if source_strength not in ALLOWED_SOURCE_STRENGTHS:
          errors.append("invalid_source_strength")

      list_field_errors = _list_field_errors(payload)
      errors.extend(list_field_errors)

      lowerable_claim_kinds = [
          str(kind)
          for kind in payload.get("lowerable_claim_kinds", [])
          if str(kind) in LOWERABLE_CLAIM_KINDS
      ]
      if source_strength in STRONG_STRENGTHS and not lowerable_claim_kinds:
          errors.append("strong_requires_lowerable_claim_kinds")
      if source_strength in STRONG_STRENGTHS:
          if str(payload.get("source_visibility") or "") != "full_text":
              errors.append("strong_requires_full_text_visibility")
          if str(payload.get("first_missing_source_action") or "") != "none":
              errors.append("strong_requires_first_missing_source_action_none")
          freshness = str(payload.get("freshness_status") or "")
          if freshness not in {"current", "evergreen"}:
              errors.append("strong_requires_current_or_evergreen_freshness")
      if (
          source_strength in {"decklist_or_stats_only", "unfetched_acquisition_seed"}
          and str(payload.get("first_missing_source_action") or "") == "none"
      ):
          warnings.append("seed_only_snapshot_should_name_next_source_action")

      return {
          "schema_version": 1,
          "valid": not errors,
          "errors": errors,
          "warnings": warnings,
          "source_status_apply_blocking": False,
          "field_count": len([field for field in REQUIRED_RESULT_FIELDS if field in payload]),
          "lowerable_claim_kinds": sorted(set(lowerable_claim_kinds)),
      }


  def validate_fields_yaml_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
      errors: list[str] = []
      fields = payload.get("fields")
      if not isinstance(fields, Mapping):
          fields = {}
          errors.append("fields_must_be_mapping")
      missing = sorted(REQUIRED_RESULT_FIELDS - set(fields))
      errors.extend(f"missing_field_definition:{field}" for field in missing)
      return {
          "schema_version": 1,
          "valid": not errors,
          "errors": errors,
          "warnings": [],
          "field_count": len(fields),
          "required_fields": sorted(REQUIRED_RESULT_FIELDS),
          "source_status_apply_blocking": False,
      }


  def _list_field_errors(payload: Mapping[str, Any]) -> list[str]:
      errors: list[str] = []
      for field in (
          "current_deck_sources",
          "guide_sources",
          "lowerable_claim_kinds",
          "non_promoting_support",
      ):
          if field in payload and not isinstance(payload[field], list):
              errors.append(f"{field}_must_be_list")
      return errors
  ```

- [ ] **Step 4: Add validator to research status sync rows**

  Modify `src/hsconfig/research_status_sync.py`:
  ```python
  from hsconfig.research_result_validator import validate_research_result_payload
  ```

  In `_research_snapshot_row()`, after `contract = classify_research_result_contract(data)`, add:
  ```python
      strict_validation = validate_research_result_payload(data)
  ```

  Add these keys to the returned row:
  ```python
          "strict_research_result_valid": strict_validation["valid"],
          "strict_research_result_errors": strict_validation["errors"],
          "strict_research_result_warnings": strict_validation["warnings"],
          "strict_research_result_field_count": strict_validation["field_count"],
  ```

- [ ] **Step 5: Extend existing sync tests**

  Modify `tests/test_research_status_sync.py` by adding one assertion to an existing row test or adding this test:
  ```python
  def test_research_status_sync_includes_strict_validation_without_blocking(tmp_path: Path) -> None:
      package_dir = _package(tmp_path, deck_name="ShadowPriest")
      research_path = tmp_path / "shadowpriest.json"
      write_json(
          research_path,
          {
              "deck_name": "ShadowPriest",
              "source_strength": "decklist_or_stats_only",
              "first_missing_source_action": "add_explicit_mulligan_source",
          },
      )

      report = build_research_status_sync_report(package_dir, [research_path])
      row = report["research_snapshot_rows"][0]

      assert row["strict_research_result_valid"] is False
      assert "missing_field:archetype" in row["strict_research_result_errors"]
      assert row["source_status_apply_blocking"] is False
      assert report["summary"]["source_status_apply_blocking"] is False
  ```

- [ ] **Step 6: Run validator and sync tests**

  Run:
  ```powershell
  python -m pytest tests\test_research_result_validator.py tests\test_research_result_contract.py tests\test_research_status_sync.py tests\test_research_status_sync_cli.py -q -p no:cacheprovider
  ```

  Expected:
  ```text
  27 passed
  ```

- [ ] **Step 7: Commit Task 3**

  Run:
  ```powershell
  git add src\hsconfig\research_result_validator.py src\hsconfig\research_status_sync.py tests\test_research_result_validator.py tests\test_research_status_sync.py
  git commit -m "feat: validate hsconfig research result snapshots"
  ```

---

### Task 4: Document Diagnostic Boundaries And Skill Usage

**Files:**
- Modify: `docs/operator/source-backed-strong-closure.md`
- Modify: `.agents/skills/hsconfig/SKILL.md`
- Test: `tests/test_operator_docs_contract_policy.py`

**Interfaces:**
- Consumes:
  - `hsconfig strong-closure-dossier`
  - strict research validation fields from Task 3
- Produces:
  - Operator-visible wording that prevents misuse of the dossier as apply authority.

- [ ] **Step 1: Add docs-policy failing assertion**

  Modify `tests/test_operator_docs_contract_policy.py` with:
  ```python
  def test_operator_docs_name_strong_closure_dossier_as_diagnostic_only() -> None:
      text = Path("docs/operator/source-backed-strong-closure.md").read_text(
          encoding="utf-8"
      )

      assert "hsconfig strong-closure-dossier" in text
      assert "strong-closure-dossier is diagnostic-only" in text
      assert "operator_summary.json remains the only normal apply authority" in text
  ```

  Ensure `Path` is already imported; if not, add:
  ```python
  from pathlib import Path
  ```

- [ ] **Step 2: Run docs test to verify it fails**

  Run:
  ```powershell
  python -m pytest tests\test_operator_docs_contract_policy.py::test_operator_docs_name_strong_closure_dossier_as_diagnostic_only -q -p no:cacheprovider
  ```

  Expected:
  ```text
  FAILED
  ```

- [ ] **Step 3: Update operator docs**

  Add this paragraph to `docs/operator/source-backed-strong-closure.md` after the `source_autopilot_report.json` diagnostic paragraph:
  ```markdown
  `hsconfig strong-closure-dossier` is diagnostic-only. It reads
  `reports/operator_summary.json`, `reports/source_claim_gap_report.json`, optional
  source-autopilot output, and optional `research-deep` snapshots to explain why
  `SOURCE_BACKED_STRONG` is confirmed or which source action remains. It never
  writes runtime files, never promotes a deck by itself, and never replaces the
  rule that operator_summary.json remains the only normal apply authority.
  ```

- [ ] **Step 4: Update skill guidance**

  In `.agents/skills/hsconfig/SKILL.md`, add this concise rule near the source-contract workflow guidance:
  ```markdown
  When source strength is in question, use `hsconfig strong-closure-dossier`
  after a no-apply `configure` package. Treat the dossier as diagnostic-only:
  `reports/operator_summary.json` remains the only normal apply authority,
  `SOURCE_BACKED_STRONG` remains an evidence-quality label, and Partial must not
  block a load-safe package.
  ```

- [ ] **Step 5: Run docs and skill sync checks**

  Run:
  ```powershell
  python -m pytest tests\test_operator_docs_contract_policy.py -q -p no:cacheprovider
  python scripts\sync_installed_skill.py --check
  ```

  Expected:
  ```text
  104 passed
  HSConfig skill is in sync: C:\Users\darbo\.codex\skills\hsconfig
  ```

  If the sync check fails because `.agents/skills/hsconfig/SKILL.md` changed, run the repo's established skill sync command, then rerun `python scripts\sync_installed_skill.py --check`.

- [ ] **Step 6: Commit Task 4**

  Run:
  ```powershell
  git add docs\operator\source-backed-strong-closure.md .agents\skills\hsconfig\SKILL.md tests\test_operator_docs_contract_policy.py
  git commit -m "docs: document strong closure dossier boundary"
  ```

---

### Task 5: End-To-End No-Apply Verification Matrix

**Files:**
- Read: `docs/operator/source-candidate-proof-decks.json`
- Read: `docs/research/2026-07-17-hsconfig-source-contract-acceptance-loop/results/*.json`
- No source files should be modified in this task.

**Interfaces:**
- Consumes:
  - `hsconfig configure --online-source --auto-source --current-date 2026-07-18`
  - `hsconfig strong-closure-dossier`
  - `hsconfig acceptance-matrix`
- Produces:
  - Local verification evidence only; commit source changes from prior tasks before this task.

- [ ] **Step 1: Run focused unit suite**

  Run:
  ```powershell
  python -m pytest tests\test_strong_closure_dossier.py tests\test_strong_closure_dossier_cli.py tests\test_research_result_validator.py tests\test_research_result_contract.py tests\test_research_status_sync.py tests\test_research_status_sync_cli.py tests\test_source_status_resolver.py tests\test_config_usefulness.py tests\test_operator_docs_contract_policy.py -q -p no:cacheprovider
  ```

  Expected:
  ```text
  100+ passed
  ```

  Use the exact pass count from the run in the final implementation report.

- [ ] **Step 2: Run full suite**

  Run:
  ```powershell
  python -m pytest -q -p no:cacheprovider
  ```

  Expected:
  ```text
  1567+ passed, 11 skipped
  ```

  The exact pass count may increase due to new tests. Any failure must be fixed before completion.

- [ ] **Step 3: Build no-apply package and dossier for ShadowPriest control**

  Run:
  ```powershell
  $out = "tmp\verify-strong-dossier-shadowpriest"
  Remove-Item -Recurse -Force $out -ErrorAction SilentlyContinue
  python -m hsconfig configure `
    --deck-name ShadowPriest `
    --deck-code "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=" `
    --out $out `
    --runtime-root "C:\Users\darbo\Desktop\HS" `
    --online-source `
    --auto-source `
    --current-date 2026-07-18 `
    --json
  python -m hsconfig strong-closure-dossier `
    --package "$out\04_package" `
    --research-results-dir docs\research\2026-07-17-hsconfig-source-contract-acceptance-loop\results `
    --source-autopilot-report-json "$out\03_source_autopilot\source_autopilot_report.json" `
    --out "$out\strong_closure_dossier.json" `
    --json
  ```

  Expected dossier facts:
  ```text
  authority=diagnostic_only
  normal_apply_authority=reports/operator_summary.json
  deck_name=ShadowPriest
  source_status_apply_blocking=false
  default_only_runtime_surfaces=[]
  ```

- [ ] **Step 4: Build no-apply package and dossier for a Partial control**

  Run:
  ```powershell
  $out = "tmp\verify-strong-dossier-piratedh"
  Remove-Item -Recurse -Force $out -ErrorAction SilentlyContinue
  python -m hsconfig configure `
    --deck-name PirateDH `
    --deck-code "AAEBAea5AwaRvALUyAP51QOHiwTh+AX8wAYM+w/psAPyyQPltgSl4gSr4gSVqgX8qAbYwAb2wAatxQax6wYAAA==" `
    --out $out `
    --runtime-root "C:\Users\darbo\Desktop\HS" `
    --online-source `
    --auto-source `
    --current-date 2026-07-18 `
    --json
  python -m hsconfig strong-closure-dossier `
    --package "$out\04_package" `
    --research-results-dir docs\research\2026-07-17-hsconfig-source-contract-acceptance-loop\results `
    --source-autopilot-report-json "$out\03_source_autopilot\source_autopilot_report.json" `
    --out "$out\strong_closure_dossier.json" `
    --json
  ```

  Expected dossier facts:
  ```text
  authority=diagnostic_only
  runtime_package_usable=true
  source_status_apply_blocking=false
  default_only_runtime_surfaces=[]
  promotion_verdict is either SOURCE_BACKED_STRONG_CONFIRMED or PROMOTION_BLOCKED based on strict evidence
  ```

- [ ] **Step 5: Remove temporary verification artifacts**

  Run:
  ```powershell
  Remove-Item -Recurse -Force tmp\verify-strong-dossier-shadowpriest,tmp\verify-strong-dossier-piratedh -ErrorAction SilentlyContinue
  ```

  Expected:
  ```text
  No output
  ```

- [ ] **Step 6: Confirm clean worktree**

  Run:
  ```powershell
  git status --short --branch
  ```

  Expected:
  ```text
  ## codex/hsconfig-canonical-source-status-sync
  ```

  If there are tracked changes from Tasks 1-4, commit them. If there are generated temp files, remove them.

- [ ] **Step 7: Final commit if any changes remain staged**

  Run:
  ```powershell
  git status --short
  ```

  If files are modified and tests have passed, commit:
  ```powershell
  git add src\hsconfig tests docs\operator .agents\skills\hsconfig
  git commit -m "feat: add strong closure dossier diagnostics"
  ```

---

## Self-Review Checklist

- Spec coverage:
  - Source-/Contract-Logik remains separated from apply authority.
  - `SOURCE_BACKED_STRONG` stays strict and evidence-backed.
  - Partial remains non-blocking and usable.
  - Default-only surfaces prevent Strong.
  - Darkbishop effect-versus-mulligan boundary remains explicit.
  - Research-deep JSON validation becomes HSConfig-specific and strict.
  - Worktree cleanliness is verified.
- Placeholder scan:
  - No broad rewrite or hidden future work is required.
- Type consistency:
  - `build_strong_closure_dossier()` returns a plain `dict[str, Any]`.
  - CLI follows existing `run_payload_command()` convention.
  - Validator functions return diagnostic dictionaries with `source_status_apply_blocking=false`.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-18-hsconfig-strong-closure-dossier-and-research-validator.md`. Two execution options:

**1. Subagent-Driven (recommended)** - Dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** - Execute tasks in this session using `superpowers:executing-plans`, batch execution with checkpoints.

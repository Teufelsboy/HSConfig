# HSConfig Source Contract Audit Authority Metadata Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `reports/source_contract_audit.json` explicitly self-identify as diagnostic-only, non-apply-blocking metadata so HSConfig keeps one clear runtime apply authority while staying machine-readable for autonomous agents.

**Architecture:** This is a narrow report-shape hardening. Add the same top-level diagnostic authority fields already used by `source_to_runtime_explainability.json` to `source_contract_audit.json`, then pin the shape with tests and single-gate guardrails. Do not change claim lowering, runtime files, apply gate behavior, source promotion, or generated CustomConfig semantics.

**Tech Stack:** Python 3.11, existing HSConfig package, pytest, stdlib JSON structures. No new dependencies.

## Global Constraints

- Work only in `C:\Users\darbo\Documents\HSConfig`.
- Start by refreshing and proving the repo is safe to work in:
  ```powershell
  cd C:\Users\darbo\Documents\HSConfig
  git fetch --all --prune --tags
  python scripts\check_hsconfig_currentness.py --cwd . --json
  git status --short --branch
  ```
- Do not proceed with implementation if the worktree is dirty or the branch is behind its upstream.
- Keep `reports/operator_summary.json` as the only normal apply authority.
- Keep `SOURCE_BACKED_STRONG` as an evidence-quality label, not a runtime apply gate.
- Keep `source_status_apply_blocking=false`; source depth must not block valid package generation.
- Keep all source-contract, explainability, closure, doctor, quality, research, and matrix reports diagnostic-only.
- Do not use HSTuner.
- Do not parse HearthRanger logs, Hearthstone logs, HDT files, replays, winrate, or post-game runtime evidence.
- Do not create a new CLI command for this change.
- Do not add new runtime surfaces.
- Do not emit normal-package `Presume.json`, `Concede.json`, or aggregate `CardBehavior.json`.
- Preserve no-default-only visibility: default-only runtime surfaces must remain visible quality debt and must not promote `SOURCE_BACKED_STRONG`.
- Preserve the Darkbishop boundary: start-of-game / hero-power-transform semantics may exist, but they must not create a Mulligan keep without explicit opening-hand source text.
- End with a clean worktree. If implementation succeeds, commit the code changes.

---

## File Structure

- Modify: `src/hsconfig/source_contract_audit.py`
  - Responsibility: build the diagnostic source-contract audit report.
  - Change: add top-level authority metadata to the returned report.
- Modify: `tests/test_source_contract_audit.py`
  - Responsibility: prove the audit report explains source-to-runtime decisions.
  - Change: assert the top-level diagnostic authority fields in an existing focused test.
- Modify: `tests/test_contract_spine_sentinel.py`
  - Responsibility: prove source-contract diagnostics cannot become apply gates.
  - Change: add a narrow guard that `source_contract_audit.json` metadata remains diagnostic-only.
- Read-only verify: `src/hsconfig/source_to_runtime_explainability.py`
  - Responsibility: existing report pattern to mirror.
- Read-only verify: `src/hsconfig/apply_gate.py`
  - Responsibility: active apply authority must remain `operator_summary.json` and package structure only.
- Read-only verify: `src/hsconfig/runtime_apply.py`
  - Responsibility: runtime write path must not consume diagnostic reports.
- Read-only verify: `tests/test_apply_authority_boundary.py`
  - Responsibility: import boundary against diagnostic reports entering active apply paths.

---

### Task 1: Pin Source Contract Audit Authority Metadata

**Files:**
- Modify: `tests/test_source_contract_audit.py`
- Modify: `src/hsconfig/source_contract_audit.py`

**Interfaces:**
- Consumes:
  ```python
  build_source_contract_audit(
      *,
      deck_name: str,
      deck_identity: Mapping[str, Any] | None = None,
      guide_claim_bundle: Mapping[str, Any] | None = None,
      mulligan_plan: Mapping[str, Any] | None = None,
      card_behavior_plan: Mapping[str, Any] | None = None,
      combo_plan: Mapping[str, Any] | None = None,
      global_values_authority_matrix: Mapping[str, Any] | None = None,
      config_readiness_report: Mapping[str, Any] | None = None,
      runtime_emission_index: Mapping[str, Mapping[str, Any]] | None = None,
      initial_lifecycle_rows: Sequence[Mapping[str, Any]] | None = None,
  ) -> dict[str, Any]
  ```
- Produces:
  ```python
  {
      "schema_version": 1,
      "authority": "diagnostic_only",
      "operator_gate_impact": "diagnostic_only",
      "apply_blocking": False,
      "normal_apply_authority": "reports/operator_summary.json",
      "deck_name": deck_name,
      "summary": summary,
      "claim_rows": claim_rows,
      "claim_lifecycle_rows": claim_lifecycle_rows,
      "card_rows": card_rows,
  }
  ```

- [ ] **Step 1: Add failing assertions to the existing source-contract audit test**

  In `tests/test_source_contract_audit.py`, update `test_source_contract_audit_explains_surface_gate_lanes()` immediately after:

  ```python
      assert report["schema_version"] == 1
  ```

  Add these assertions:

  ```python
      assert report["authority"] == "diagnostic_only"
      assert report["operator_gate_impact"] == "diagnostic_only"
      assert report["apply_blocking"] is False
      assert report["normal_apply_authority"] == "reports/operator_summary.json"
  ```

- [ ] **Step 2: Run the focused test and verify it fails for the missing fields**

  Run:

  ```powershell
  python -m pytest tests\test_source_contract_audit.py::test_source_contract_audit_explains_surface_gate_lanes -q -p no:cacheprovider
  ```

  Expected result before implementation:

  ```text
  FAILED tests/test_source_contract_audit.py::test_source_contract_audit_explains_surface_gate_lanes
  KeyError: 'authority'
  ```

- [ ] **Step 3: Add the minimal report metadata implementation**

  In `src/hsconfig/source_contract_audit.py`, replace the final return block in `build_source_contract_audit()`:

  ```python
      return {
          "schema_version": 1,
          "deck_name": deck_name,
          "summary": summary,
          "claim_rows": claim_rows,
          "claim_lifecycle_rows": claim_lifecycle_rows,
          "card_rows": card_rows,
      }
  ```

  with:

  ```python
      return {
          "schema_version": 1,
          "authority": _DIAGNOSTIC_OPERATOR_IMPACT,
          "operator_gate_impact": _DIAGNOSTIC_OPERATOR_IMPACT,
          "apply_blocking": False,
          "normal_apply_authority": "reports/operator_summary.json",
          "deck_name": deck_name,
          "summary": summary,
          "claim_rows": claim_rows,
          "claim_lifecycle_rows": claim_lifecycle_rows,
          "card_rows": card_rows,
      }
  ```

- [ ] **Step 4: Run the focused test and verify it passes**

  Run:

  ```powershell
  python -m pytest tests\test_source_contract_audit.py::test_source_contract_audit_explains_surface_gate_lanes -q -p no:cacheprovider
  ```

  Expected result:

  ```text
  1 passed
  ```

- [ ] **Step 5: Run the full source-contract audit test file**

  Run:

  ```powershell
  python -m pytest tests\test_source_contract_audit.py -q -p no:cacheprovider
  ```

  Expected result:

  ```text
  passed
  ```

---

### Task 2: Add a Contract-Spine Guard for Diagnostic Metadata

**Files:**
- Modify: `tests/test_contract_spine_sentinel.py`

**Interfaces:**
- Consumes:
  ```python
  from hsconfig.source_contract_audit import build_source_contract_audit
  ```
- Produces: a regression test proving `source_contract_audit.json` carries diagnostic-only metadata and does not look like a gate.

- [ ] **Step 1: Add the import**

  In `tests/test_contract_spine_sentinel.py`, after:

  ```python
  from hsconfig.source_document_model import SUPPORTED_ATOMIC_CLAIM_KINDS
  ```

  add:

  ```python
  from hsconfig.source_contract_audit import build_source_contract_audit
  ```

- [ ] **Step 2: Add the failing guard test**

  In `tests/test_contract_spine_sentinel.py`, after `test_contract_spine_sentinel_report_is_clean_for_current_repo()`, add:

  ```python
  def test_source_contract_audit_report_declares_diagnostic_only_authority():
      report = build_source_contract_audit(
          deck_name="FixtureDeck",
          deck_identity={
              "deck_name": "FixtureDeck",
              "cards": [{"card_id": "CARD_KEEP", "name": "Keep Card", "count": 1}],
          },
          guide_claim_bundle={
              "claims": [
                  {
                      "claim_id": "keep_claim",
                      "claim_kind": "mulligan_keep",
                      "claim_readiness": "guide_backed",
                      "trust_ceiling": "runtime_candidate",
                      "cards": ["CARD_KEEP"],
                      "source_title": "Fixture Guide",
                      "evidence_text_short": "Keep CARD_KEEP.",
                  }
              ]
          },
          mulligan_plan={
              "rules": [
                  {
                      "card": "CARD_KEEP",
                      "action": "hold",
                      "source_claim_ids": ["keep_claim"],
                  }
              ],
              "suppressed_rules": [],
          },
          card_behavior_plan={"rows": [], "suppressed": []},
          combo_plan={"combos": [], "suppressed": []},
          global_values_authority_matrix={
              "allowed_step1_overlays": [],
              "blocked_until_runtime_evidence": [],
          },
          config_readiness_report={
              "cards": {
                  "CARD_KEEP": {
                      "name": "Keep Card",
                      "roles": ["mulligan_anchor"],
                      "runtime_surfaces": ["Mulligan.json"],
                      "readiness_lane": "mulligan_only",
                      "first_missing_link": "none",
                  }
              }
          },
      )

      assert report["authority"] == "diagnostic_only"
      assert report["operator_gate_impact"] == "diagnostic_only"
      assert report["apply_blocking"] is False
      assert report["normal_apply_authority"] == "reports/operator_summary.json"
      assert "runtime_apply_allowed" not in report
      assert "runtime_apply_mode" not in report
      assert "apply_policy" not in report
  ```

- [ ] **Step 3: Run the new guard test**

  Run:

  ```powershell
  python -m pytest tests\test_contract_spine_sentinel.py::test_source_contract_audit_report_declares_diagnostic_only_authority -q -p no:cacheprovider
  ```

  Expected result after Task 1 implementation:

  ```text
  1 passed
  ```

- [ ] **Step 4: Run the full contract-spine sentinel file**

  Run:

  ```powershell
  python -m pytest tests\test_contract_spine_sentinel.py -q -p no:cacheprovider
  ```

  Expected result:

  ```text
  passed
  ```

---

### Task 3: Verify No Second Gate and No Default-Only Drift

**Files:**
- Read-only: `tests/test_apply_authority_boundary.py`
- Read-only: `tests/test_no_second_gate_contract.py`
- Read-only: `tests/test_report_ownership.py`
- Read-only: `tests/test_source_to_runtime_explainability.py`
- Read-only: `tests/test_no_default_only_semantic_archetype_matrix.py`

**Interfaces:**
- Consumes: metadata added in Task 1.
- Produces: verification evidence that the metadata remains diagnostic-only and does not alter runtime write authority.

- [ ] **Step 1: Run the apply-authority and report-ownership tests**

  Run:

  ```powershell
  python -m pytest tests\test_apply_authority_boundary.py tests\test_no_second_gate_contract.py tests\test_report_ownership.py -q -p no:cacheprovider
  ```

  Expected result:

  ```text
  passed
  ```

- [ ] **Step 2: Run source explainability and default-only contracts**

  Run:

  ```powershell
  python -m pytest tests\test_source_contract_audit.py tests\test_source_to_runtime_explainability.py tests\test_no_default_only_semantic_archetype_matrix.py -q -p no:cacheprovider
  ```

  Expected result:

  ```text
  passed
  ```

- [ ] **Step 3: Run contract preflight**

  Run:

  ```powershell
  python -m hsconfig.cli contract-preflight --repo-root . --json
  ```

  Expected JSON fields:

  ```json
  {
    "status": "PASS",
    "failures": [],
    "runtime_apply_authority": "reports/operator_summary.json",
    "source_status_apply_blocking": false,
    "diagnostic_only": true
  }
  ```

- [ ] **Step 4: Verify installed skill sync**

  Run:

  ```powershell
  python scripts\sync_installed_skill.py --check
  ```

  Expected result:

  ```text
  HSConfig skill is in sync: C:\Users\darbo\.codex\skills\hsconfig
  ```

---

### Task 4: Final Cleanliness, Commit, and Handoff

**Files:**
- Commit:
  - `src/hsconfig/source_contract_audit.py`
  - `tests/test_source_contract_audit.py`
  - `tests/test_contract_spine_sentinel.py`

**Interfaces:**
- Consumes: passing verification from Tasks 1-3.
- Produces: one committed, clean implementation branch ready for the next HSConfig generation run.

- [ ] **Step 1: Inspect the diff**

  Run:

  ```powershell
  git diff -- src\hsconfig\source_contract_audit.py tests\test_source_contract_audit.py tests\test_contract_spine_sentinel.py
  ```

  Expected review points:

  ```text
  source_contract_audit.py adds only top-level diagnostic metadata.
  tests assert diagnostic-only metadata.
  no apply gate, runtime apply, source status, or runtime output code changed.
  ```

- [ ] **Step 2: Run final status check**

  Run:

  ```powershell
  git status --short --branch
  ```

  Expected result before commit:

  ```text
  ## codex/hsconfig-semantic-intent-scoring...origin/codex/hsconfig-semantic-intent-scoring
   M src/hsconfig/source_contract_audit.py
   M tests/test_source_contract_audit.py
   M tests/test_contract_spine_sentinel.py
  ```

- [ ] **Step 3: Stage implementation files**

  Run:

  ```powershell
  git add src\hsconfig\source_contract_audit.py tests\test_source_contract_audit.py tests\test_contract_spine_sentinel.py
  ```

- [ ] **Step 4: Commit the implementation**

  Run:

  ```powershell
  git commit -m "test: mark source contract audit diagnostic authority"
  ```

- [ ] **Step 5: Push the branch**

  Run:

  ```powershell
  git push
  ```

- [ ] **Step 6: Verify clean final state**

  Run:

  ```powershell
  git status --short --branch
  python scripts\check_hsconfig_currentness.py --cwd . --json
  ```

  Expected result:

  ```text
  git status shows no modified or untracked files.
  currentness JSON has "dirty": false and "clean_for_runtime_work": true.
  ```

---

## Self-Review

- Spec coverage: This plan implements the recommended slim improvement only: diagnostic authority metadata for `source_contract_audit.json`. It does not touch logs, HSTuner, source promotion, apply gates, runtime surfaces, or gameplay behavior.
- Placeholder scan: No placeholders are present. Every changed code/test step includes the exact code to add or the exact command to run.
- Type consistency: Added fields are plain JSON-compatible values: `str`, `str`, `bool`, `str`. They mirror `source_to_runtime_explainability.json` naming and do not conflict with existing `summary`, `claim_rows`, `claim_lifecycle_rows`, or `card_rows`.
- Risk check: The only behavioral output change is extra metadata in one diagnostic report. Active runtime apply remains anchored to `reports/operator_summary.json`.

Plan complete. Recommended execution mode: Subagent-Driven, one worker for Task 1, one read-only reviewer for Tasks 2-3, final integration by the main agent.

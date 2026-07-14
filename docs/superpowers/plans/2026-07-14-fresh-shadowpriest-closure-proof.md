# Fresh ShadowPriest Closure Proof Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove that a freshly generated ShadowPriest package exposes every card through source-to-runtime closure diagnostics, with no silent default-only surface and no false Darkbishop Benedictus mulligan keep.

**Architecture:** Keep `reports/operator_summary.json` as the only normal apply authority. Add only compact diagnostic freshness fields to the existing source-to-runtime summary, then prove the fresh package path through tests and one ignored local output run. Do not add a second gate, new runtime surface, or broader source-confidence model.

**Tech Stack:** Python 3.11+, pytest, existing `hsconfig` CLI, existing HSConfig reports, no new dependencies.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig`.
- Keep `main` synchronized with `origin/main` before starting implementation.
- Do not commit generated `outputs/`, runtime logs, HearthRanger evidence, `.hsreplay`, `.hdtreplay`, or `Power.log`.
- `operator_summary.json` remains the only normal runtime apply authority.
- `source_to_runtime_explainability.json`, `source_contract_audit.json`, and closure fields are diagnostic-only.
- A valid package remains applyable with warnings; source-depth or default-only diagnostics must not become runtime apply blockers.
- Effect semantics are not opening-hand mulligan keeps. Darkbishop Benedictus `SW_448` may preserve hero-power-transform behavior, but must not appear in `Mulligan.json` unless explicit source text says to keep it.
- Normal HSConfig output stays limited to `GlobalValues.json`, `Mulligan.json`, per-card `<CARDID>.json`, and exact `Combo.json`.
- Keep the skill compact; `.agents/skills/hsconfig/SKILL.md` must stay under the existing compactness test limit.

---

## File Structure

- Modify: `src/hsconfig/operator_summary.py`
  - Add compact source-to-runtime closure freshness counters to `_source_to_runtime_explainability_summary()`.
  - Keep fields non-blocking and diagnostic-only.
- Modify: `tests/test_operator_summary.py`
  - Freeze the new diagnostic summary fields.
  - Prove missing closure rows are visible but not apply-blocking.
- Create: `tests/test_shadowpriest_fresh_closure_proof.py`
  - Generate a fresh ShadowPriest package in `tmp_path`.
  - Assert every card row has `closure`.
  - Assert no silent default-only condition exists.
  - Assert Darkbishop remains out of `Mulligan.json` while `SW_448.json` preserves effect behavior.
- Modify: `docs/operator/README.md`
  - Add a short fresh-proof read path.
- Modify: `docs/operator/guide-research-policy.md`
  - Clarify closure freshness and default-only diagnostics.
- Modify: `.agents/skills/hsconfig/SKILL.md`
  - Keep the operator instruction aligned with closure freshness without making the skill verbose.
- Modify: `tests/test_operator_docs_contract_policy.py`
  - Freeze active-doc wording around closure freshness and single apply authority.

---

### Task 1: Add Operator Summary Closure Freshness Diagnostics

**Files:**
- Modify: `src/hsconfig/operator_summary.py`
- Modify: `tests/test_operator_summary.py`

**Interfaces:**
- Consumes: `source_to_runtime_explainability_report["card_rows"][*]["closure"]`
- Produces: `operator_summary["source_to_runtime_explainability_summary"]["closure_lane_counts"]`
- Produces: `operator_summary["source_to_runtime_explainability_summary"]["cards_with_closure"]`
- Produces: `operator_summary["source_to_runtime_explainability_summary"]["cards_missing_closure"]`
- Produces: `operator_summary["source_to_runtime_explainability_summary"]["closure_schema_current"]`

- [ ] **Step 1: Add the failing unit test for closure counters**

Add this test near `test_operator_summary_exposes_source_to_runtime_explainability_without_blocking_apply` in `tests/test_operator_summary.py`:

```python
def test_operator_summary_counts_closure_lanes_without_apply_authority():
    summary = build_operator_summary(
        deck_name="Closure Deck",
        deck_code="AAEBAQAAAA==",
        technical_validation={"status": "passed"},
        guide_source_depth={
            "source_depth_status": "source_backed",
            "claim_count": 2,
            "source_evidence": {"warnings_count": 0},
        },
        source_to_runtime_explainability_report={
            "authority": "diagnostic_only",
            "operator_gate_impact": "diagnostic_only",
            "apply_blocking": False,
            "summary": {
                "cards_total": 3,
                "claims_total": 4,
                "runtime_lowered_claims": 2,
                "claims_with_first_missing_link": 1,
                "cards_with_first_missing_link": 1,
                "next_report_to_open": "reports/source_to_runtime_explainability.json",
            },
            "card_rows": [
                {
                    "card_id": "CARD_RUNTIME",
                    "name": "Runtime Card",
                    "closure": {
                        "lane": "runtime_backed",
                        "default_only_risk": False,
                    },
                },
                {
                    "card_id": "CARD_GAP",
                    "name": "Gap Card",
                    "closure": {
                        "lane": "source_action_needed",
                        "default_only_risk": False,
                    },
                },
                {
                    "card_id": "CARD_BASELINE",
                    "name": "Baseline Card",
                    "closure": {
                        "lane": "baseline_only_visible",
                        "default_only_risk": True,
                    },
                },
            ],
        },
        generated_files=[
            "CustomConfig/closuredeck/GlobalValues.json",
            "CustomConfig/closuredeck/Mulligan.json",
        ],
    )

    explainability = summary["source_to_runtime_explainability_summary"]

    assert summary["runtime_apply_allowed"] is True
    assert explainability["non_blocking"] is True
    assert explainability["closure_lane_counts"] == {
        "baseline_only_visible": 1,
        "runtime_backed": 1,
        "source_action_needed": 1,
    }
    assert explainability["cards_with_closure"] == 3
    assert explainability["cards_missing_closure"] == 0
    assert explainability["closure_schema_current"] is True
```

- [ ] **Step 2: Add the failing unit test for stale or old explainability rows**

Add this test in `tests/test_operator_summary.py`:

```python
def test_operator_summary_marks_missing_closure_rows_as_non_blocking_diagnostic():
    summary = build_operator_summary(
        deck_name="Old Artifact Deck",
        deck_code="AAEBAQAAAA==",
        technical_validation={"status": "passed"},
        source_to_runtime_explainability_report={
            "authority": "diagnostic_only",
            "operator_gate_impact": "diagnostic_only",
            "apply_blocking": False,
            "summary": {
                "cards_total": 2,
                "claims_total": 1,
                "runtime_lowered_claims": 1,
                "claims_with_first_missing_link": 0,
                "cards_with_first_missing_link": 0,
            },
            "card_rows": [
                {"card_id": "CARD_OLD", "name": "Old Card"},
                {
                    "card_id": "CARD_RUNTIME",
                    "name": "Runtime Card",
                    "closure": {
                        "lane": "runtime_backed",
                        "default_only_risk": False,
                    },
                },
            ],
        },
        generated_files=[
            "CustomConfig/oldartifactdeck/GlobalValues.json",
            "CustomConfig/oldartifactdeck/Mulligan.json",
        ],
    )

    explainability = summary["source_to_runtime_explainability_summary"]

    assert summary["runtime_apply_allowed"] is True
    assert explainability["non_blocking"] is True
    assert explainability["cards_with_closure"] == 1
    assert explainability["cards_missing_closure"] == 1
    assert explainability["closure_schema_current"] is False
    assert explainability["next_report_to_open"] == (
        "reports/source_to_runtime_explainability.json"
    )
```

- [ ] **Step 3: Run the new tests and verify failure**

Run:

```powershell
python -m pytest tests\test_operator_summary.py::test_operator_summary_counts_closure_lanes_without_apply_authority tests\test_operator_summary.py::test_operator_summary_marks_missing_closure_rows_as_non_blocking_diagnostic -q
```

Expected: both tests fail because `closure_lane_counts`, `cards_with_closure`, `cards_missing_closure`, and `closure_schema_current` are not yet present.

- [ ] **Step 4: Implement minimal closure summary helpers**

In `src/hsconfig/operator_summary.py`, update `_source_to_runtime_explainability_summary()` so it derives card-row closure diagnostics. Use the existing `Counter` import already present at the top of the file.

Replace the current return block in `_source_to_runtime_explainability_summary()` with this shape, preserving the existing numeric fields:

```python
    card_rows = report.get("card_rows", [])
    if not isinstance(card_rows, list):
        card_rows = []
    closure_rows = [
        row
        for row in card_rows
        if isinstance(row, dict) and isinstance(row.get("closure"), dict)
    ]
    closure_lane_counts = Counter(
        str(row["closure"].get("lane", "unknown"))
        for row in closure_rows
        if str(row["closure"].get("lane", "")).strip()
    )
    cards_missing_closure = max(0, len(card_rows) - len(closure_rows))

    return {
        "non_blocking": True,
        "cards_total": _int_value(summary.get("cards_total", 0)),
        "claims_total": _int_value(summary.get("claims_total", 0)),
        "runtime_lowered_claims": _int_value(
            summary.get("runtime_lowered_claims", 0)
        ),
        "claims_with_first_missing_link": _int_value(
            summary.get("claims_with_first_missing_link", 0)
        ),
        "cards_with_first_missing_link": _int_value(
            summary.get("cards_with_first_missing_link", 0)
        ),
        "closure_lane_counts": dict(sorted(closure_lane_counts.items())),
        "cards_with_closure": len(closure_rows),
        "cards_missing_closure": cards_missing_closure,
        "closure_schema_current": bool(card_rows) and cards_missing_closure == 0,
        "next_report_to_open": next_report,
    }
```

Also update the `not isinstance(report, dict)` fallback return to include:

```python
            "closure_lane_counts": {},
            "cards_with_closure": 0,
            "cards_missing_closure": 0,
            "closure_schema_current": False,
```

- [ ] **Step 5: Update the existing exact expected summary test**

In `tests/test_operator_summary.py`, update the expected dict in `test_operator_summary_exposes_source_to_runtime_explainability_without_blocking_apply()` so it includes the new default fields for a report without card rows:

```python
        "closure_lane_counts": {},
        "cards_with_closure": 0,
        "cards_missing_closure": 0,
        "closure_schema_current": False,
```

- [ ] **Step 6: Run Task 1 tests**

Run:

```powershell
python -m pytest tests\test_operator_summary.py::test_operator_summary_exposes_source_to_runtime_explainability_without_blocking_apply tests\test_operator_summary.py::test_operator_summary_counts_closure_lanes_without_apply_authority tests\test_operator_summary.py::test_operator_summary_marks_missing_closure_rows_as_non_blocking_diagnostic -q
```

Expected: `3 passed`.

- [ ] **Step 7: Commit Task 1**

Run:

```powershell
git add src\hsconfig\operator_summary.py tests\test_operator_summary.py
git commit -m "test: expose source runtime closure freshness"
```

---

### Task 2: Add Fresh ShadowPriest Closure Proof

**Files:**
- Create: `tests/test_shadowpriest_fresh_closure_proof.py`

**Interfaces:**
- Consumes: `hsconfig.cli.main()`
- Consumes: `research-deck` output `guide_sources.json`
- Consumes: `prepare` output `reports/operator_summary.json`
- Consumes: `prepare` output `reports/source_to_runtime_explainability.json`
- Produces: pytest proof that fresh ShadowPriest output has current closure diagnostics and correct Darkbishop boundary.

- [ ] **Step 1: Create the failing proof test**

Create `tests/test_shadowpriest_fresh_closure_proof.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from hsconfig.cli import main


SHADOWPRIEST_DECK_NAME = "ShadowPriest"
SHADOWPRIEST_DECK_CODE = (
    "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/"
    "KgG17oG1cEGAAA="
)
DARKBISHOP_CARD_ID = "SW_448"


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_fresh_shadowpriest_package_exposes_per_card_closure_without_silent_default_only(
    tmp_path: Path,
    capsys,
):
    research = tmp_path / "shadowpriest_research"
    package = tmp_path / "shadowpriest_package"
    runtime = tmp_path / "runtime"

    research_code = main(
        [
            "research-deck",
            "--deck-name",
            SHADOWPRIEST_DECK_NAME,
            "--deck-code",
            SHADOWPRIEST_DECK_CODE,
            "--out",
            str(research),
            "--json",
        ]
    )
    research_payload = json.loads(capsys.readouterr().out)

    prepare_code = main(
        [
            "prepare",
            "--deck-name",
            SHADOWPRIEST_DECK_NAME,
            "--deck-code",
            SHADOWPRIEST_DECK_CODE,
            "--runtime-root",
            str(runtime),
            "--out",
            str(package),
            "--guide-sources-json",
            str(research / "guide_sources.json"),
            "--json",
        ]
    )
    prepare_payload = json.loads(capsys.readouterr().out)

    reports = package / "reports"
    operator = _json(reports / "operator_summary.json")
    explainability = _json(reports / "source_to_runtime_explainability.json")
    deck_slug = prepare_payload["deck_slug"]
    deck_dir = package / "CustomConfig" / deck_slug
    mulligan = _json(deck_dir / "Mulligan.json")
    darkbishop = _json(deck_dir / f"{DARKBISHOP_CARD_ID}.json")

    assert research_code == 0
    assert research_payload["status"] == "OK"
    assert prepare_code == 0
    assert operator["technical_status"] == "VALID_PACKAGE"
    assert operator["runtime_apply_mode"] == "load_safe_apply"
    assert operator["runtime_apply_allowed"] is True

    explainability_summary = operator["source_to_runtime_explainability_summary"]
    assert explainability["authority"] == "diagnostic_only"
    assert explainability["apply_blocking"] is False
    assert explainability_summary["non_blocking"] is True
    assert explainability_summary["cards_missing_closure"] == 0
    assert explainability_summary["closure_schema_current"] is True

    card_rows = explainability["card_rows"]
    assert card_rows
    assert len(card_rows) == explainability["summary"]["cards_total"]
    assert all(isinstance(row.get("closure"), dict) for row in card_rows)
    assert {
        row["closure"]["lane"]
        for row in card_rows
    } <= {
        "runtime_backed",
        "source_action_needed",
        "diagnostic_only",
        "baseline_only_visible",
    }
    assert not [
        row["card_id"]
        for row in card_rows
        if row["closure"]["lane"] == "baseline_only_visible"
        and row["closure"]["default_only_risk"] is not True
    ]

    assert operator["default_only_runtime_surfaces"] == []
    assert operator["default_only_runtime_surface_details"] == []

    mulligan_text = json.dumps(mulligan, sort_keys=True)
    assert DARKBISHOP_CARD_ID not in mulligan_text
    assert darkbishop["GameCardId"] == DARKBISHOP_CARD_ID
    darkbishop_text = json.dumps(darkbishop, sort_keys=True)
    assert "BeforeUseHeroPowerBonus" in darkbishop_text
    assert "hero_power" in darkbishop_text.lower()
```

- [ ] **Step 2: Run the proof test**

Run:

```powershell
python -m pytest tests\test_shadowpriest_fresh_closure_proof.py -q
```

Expected after Task 1: `1 passed`.

If this fails because `operator_summary["default_only_runtime_surfaces"]` is missing rather than `[]`, normalize the operator-summary default-only helpers to return an empty list for no default-only surfaces and rerun this test.

- [ ] **Step 3: Commit Task 2**

Run:

```powershell
git add tests\test_shadowpriest_fresh_closure_proof.py
git commit -m "test: prove fresh shadowpriest closure output"
```

---

### Task 3: Align Operator Docs And Skill Wording

**Files:**
- Modify: `docs/operator/README.md`
- Modify: `docs/operator/guide-research-policy.md`
- Modify: `.agents/skills/hsconfig/SKILL.md`
- Modify: `tests/test_operator_docs_contract_policy.py`

**Interfaces:**
- Consumes: operator-facing fields from Tasks 1 and 2.
- Produces: docs contract saying closure freshness is diagnostic-only and no default-only state may be silent.

- [ ] **Step 1: Add the failing docs test**

In `tests/test_operator_docs_contract_policy.py`, add:

```python
def test_active_docs_describe_fresh_closure_proof_without_new_apply_gate():
    operator = Path("docs/operator/README.md").read_text(encoding="utf-8")
    policy = Path("docs/operator/guide-research-policy.md").read_text(
        encoding="utf-8"
    )
    skill = Path(".agents/skills/hsconfig/SKILL.md").read_text(encoding="utf-8")
    active_docs = "\n".join([operator, policy, skill])

    assert "closure_schema_current" in active_docs
    assert "cards_missing_closure" in active_docs
    assert "default_only_runtime_surface_details" in active_docs
    assert "operator_summary.json remains the only normal apply authority" in active_docs
    assert "diagnostic-only" in active_docs or "diagnostic only" in active_docs
```

- [ ] **Step 2: Run the docs test and verify failure**

Run:

```powershell
python -m pytest tests\test_operator_docs_contract_policy.py::test_active_docs_describe_fresh_closure_proof_without_new_apply_gate -q
```

Expected: FAIL until docs and skill wording mention the new fields.

- [ ] **Step 3: Update `docs/operator/README.md`**

Add this compact paragraph in the source-to-runtime/read-reports area:

```markdown
Fresh package proof should show `reports/operator_summary.json.source_to_runtime_explainability_summary.closure_schema_current=true` and `cards_missing_closure=0`. If closure rows are missing, treat the package as stale or diagnostically incomplete and regenerate it; this is not a runtime apply gate. Default-only surfaces must not be silent: open `default_only_runtime_surface_details` and `reports/source_to_runtime_explainability.json` before reading a package as qualitatively complete.
```

- [ ] **Step 4: Update `docs/operator/guide-research-policy.md`**

Add this paragraph in the single-apply-authority or source-to-runtime section:

```markdown
Closure freshness is diagnostic-only. `operator_summary.json remains the only normal apply authority`; `closure_schema_current`, `cards_missing_closure`, `closure_lane_counts`, and `default_only_runtime_surface_details` explain whether a freshly generated package exposes every card's source-to-runtime state. They must not become a second runtime-write gate.
```

- [ ] **Step 5: Update `.agents/skills/hsconfig/SKILL.md` without making it verbose**

Replace the existing source-to-runtime bullet with a compact version that includes the new fields:

```markdown
- `reports/source_to_runtime_explainability.json` is the card-readable diagnostic projection with per-card closure rows, emitted/missing runtime files, first missing links, and next source actions. In `operator_summary.json`, `closure_schema_current`, `cards_missing_closure`, and `default_only_runtime_surface_details` are diagnostic-only freshness/usefulness signals; `operator_summary.json remains the only normal apply authority`.
```

After editing, verify the skill line count remains below the current test threshold.

- [ ] **Step 6: Run docs and skill tests**

Run:

```powershell
python -m pytest tests\test_operator_docs_contract_policy.py::test_active_docs_describe_fresh_closure_proof_without_new_apply_gate tests\test_skill_files.py::test_skill_and_workflow_stay_compact_and_canonical -q
```

Expected: `2 passed`.

- [ ] **Step 7: Commit Task 3**

Run:

```powershell
git add docs\operator\README.md docs\operator\guide-research-policy.md .agents\skills\hsconfig\SKILL.md tests\test_operator_docs_contract_policy.py
git commit -m "docs: document fresh closure diagnostics"
```

---

### Task 4: Run Fresh Local ShadowPriest Proof And Full Verification

**Files:**
- Do not commit: `outputs/ShadowPriest/**`
- Verify: generated local package only

**Interfaces:**
- Consumes: `hsconfig configure`
- Produces: ignored local `outputs/ShadowPriest/04_package/**`
- Produces: final proof that current code emits current closure fields in real output.

- [ ] **Step 1: Remove only ignored ShadowPriest output**

Run:

```powershell
if (Test-Path outputs\ShadowPriest) { Remove-Item -Recurse -Force outputs\ShadowPriest }
```

Expected: no tracked file changes. Verify:

```powershell
git status --short --branch
```

Expected: only source/doc/test changes from committed tasks, or clean if every task commit succeeded.

- [ ] **Step 2: Generate a fresh package without runtime apply**

Run:

```powershell
python -m hsconfig.cli configure --deck-name "ShadowPriest" --deck-code "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=" --runtime-root "C:\Users\darbo\Desktop\HS" --out "outputs\ShadowPriest" --json
```

Expected:

- command exits `0`
- no runtime apply happens because `--apply` is not passed
- package exists under `outputs\ShadowPriest\04_package`

- [ ] **Step 3: Inspect the fresh operator summary**

Run:

```powershell
$operator = Get-Content -Raw outputs\ShadowPriest\04_package\reports\operator_summary.json | ConvertFrom-Json
$operator.technical_status
$operator.runtime_apply_mode
$operator.runtime_apply_allowed
$operator.source_to_runtime_explainability_summary
$operator.default_only_runtime_surfaces
$operator.default_only_runtime_surface_details
```

Expected:

- `VALID_PACKAGE`
- `load_safe_apply`
- `True`
- `source_to_runtime_explainability_summary.closure_schema_current` is `True`
- `source_to_runtime_explainability_summary.cards_missing_closure` is `0`
- `default_only_runtime_surfaces` is `[]`
- `default_only_runtime_surface_details` is `[]`

- [ ] **Step 4: Inspect the fresh per-card closure and Darkbishop boundary**

Run:

```powershell
$explain = Get-Content -Raw outputs\ShadowPriest\04_package\reports\source_to_runtime_explainability.json | ConvertFrom-Json
($explain.card_rows | Where-Object { -not $_.closure }).Count
($explain.card_rows | Group-Object { $_.closure.lane } | Select-Object Name,Count)
Select-String -Path outputs\ShadowPriest\04_package\CustomConfig\shadowpriest\Mulligan.json -Pattern "SW_448" -Quiet
Get-Content -Raw outputs\ShadowPriest\04_package\CustomConfig\shadowpriest\SW_448.json
```

Expected:

- missing closure count is `0`
- closure lanes are only `runtime_backed`, `source_action_needed`, `diagnostic_only`, or `baseline_only_visible`
- `Select-String ... "SW_448"` returns `False`
- `SW_448.json` contains hero-power or before-use-hero-power behavior

- [ ] **Step 5: Run targeted tests**

Run:

```powershell
python -m pytest tests\test_operator_summary.py tests\test_source_to_runtime_explainability.py tests\test_shadowpriest_fresh_closure_proof.py tests\test_operator_docs_contract_policy.py tests\test_skill_files.py -q
```

Expected: all selected tests pass.

- [ ] **Step 6: Run source-contract guard tests**

Run:

```powershell
python -m pytest tests\test_source_contract_closure_wave.py tests\test_claim_kind_runtime_contract.py tests\test_surface_authority_split.py tests\test_autonomous_mulligan_policy.py tests\test_universal_wild_no_block_matrix.py -q
```

Expected: all selected tests pass.

- [ ] **Step 7: Run the full suite**

Run:

```powershell
python -m pytest -q
```

Expected: full suite passes.

- [ ] **Step 8: Confirm ignored outputs were not staged**

Run:

```powershell
git status --short --branch
git diff --check
```

Expected:

- no generated `outputs/` files appear
- no whitespace errors

- [ ] **Step 9: Push all commits**

Run:

```powershell
git push origin main
git status --short --branch
```

Expected:

- push succeeds
- `## main...origin/main`
- no uncommitted tracked changes

---

## Final Review Checklist

- [ ] `operator_summary.json` still remains the only normal apply authority.
- [ ] `closure_schema_current` and `cards_missing_closure` are diagnostic-only.
- [ ] No new runtime-write gate was added.
- [ ] No new dependency was added.
- [ ] Fresh ShadowPriest proof uses `tmp_path` in tests and ignored `outputs/` locally.
- [ ] `SW_448` does not appear in `Mulligan.json`.
- [ ] `SW_448.json` still preserves hero-power-transform behavior.
- [ ] Default-only states are never silent.
- [ ] Valid packages remain `load_safe_apply` with warnings instead of blocked by source-depth diagnostics.
- [ ] Full pytest suite passes before push.

## Execution Handoff

Plan complete. Recommended execution mode: **Subagent-Driven**.

Suggested subagents:

- Worker 1: Task 1 operator summary diagnostics and unit tests.
- Worker 2: Task 2 fresh ShadowPriest proof test.
- Worker 3: Task 3 docs and skill wording.
- Final Reviewer: Task 4 verification, generated-output audit, git status, push.


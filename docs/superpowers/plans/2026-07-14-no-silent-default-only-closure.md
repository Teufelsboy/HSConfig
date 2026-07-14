# No-Silent-Default-Only Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make HSConfig's no-default-only contract explicit and testable without adding a new apply gate: valid deck packages stay autonomous/load-safe, but default-only or thin runtime surfaces can never be silent.

**Architecture:** Keep the existing architecture intact. `reports/operator_summary.json` remains the only normal runtime apply authority; `source_contract_audit.json`, `source_to_runtime_explainability.json`, config usefulness, and closure reports remain diagnostic-only. Add compact operator-facing verdict/detail fields plus regression tests and docs that prove default-only risk is visible but non-blocking.

**Tech Stack:** Python 3, pytest, existing HSConfig modules under `src/hsconfig`, existing CLI/report tests under `tests`, Markdown operator docs.

## Global Constraints

- Do not add a new CLI command, pipeline, dependency, apply gate, or runtime surface.
- Do not change `src/hsconfig/apply_gate.py` unless a test proves an accidental second gate exists; this wave should preserve the current single-gate model.
- `reports/operator_summary.json` remains the only normal runtime apply authority.
- `source_contract_audit.json` and `source_to_runtime_explainability.json` remain diagnostic-only and must not grant or deny runtime writes.
- Valid packages must remain apply-eligible even when source depth is thin, unless the technical package itself is invalid.
- Default-only/thin surfaces must be visible in operator-facing reports.
- `Presume.json` and `Concede.json` remain outside the normal output path.
- Darkbishop Benedictus / `SW_448` must preserve hero-power-transform behavior while not becoming a Mulligan keep unless explicit opening-hand source text exists.
- Keep changes narrow and repo-local; no broad refactor.

---

## File Structure

- Modify `src/hsconfig/operator_summary.py`
  - Add the compact `no_default_only_verdict` field.
  - Enrich `default_only_runtime_surface_details` with first missing link and next source action.
  - Keep helper functions local to this module; do not move apply logic.

- Modify `src/hsconfig/source_to_runtime_explainability.py`
  - Add small, explicit closure metadata to operator attention rows if needed by the enriched summary.
  - Preserve `authority="diagnostic_only"`, `operator_gate_impact="diagnostic_only"`, and `apply_blocking=False`.

- Modify `tests/test_operator_summary.py`
  - Add unit coverage for the new no-default-only verdict in three states: none detected, visible warning, not applicable.
  - Add a focused test that a default-only Mulligan remains non-blocking and points to the first missing source/runtime link.

- Modify `tests/test_source_to_runtime_explainability.py`
  - Add/adjust assertions so card-level closure rows expose enough information for operator summary details.

- Modify `tests/test_shadowpriest_depth_e2e.py` or `tests/test_shadowpriest_fresh_closure_proof.py`
  - Add the Darkbishop regression anchor if the existing test does not already assert both sides in one place.

- Modify `docs/operator/README.md`
  - Add a short operator explanation: default-only warnings are visible quality debt, not apply blockers.

- Modify `docs/operator/guide-research-policy.md`
  - Add one sentence under source-to-runtime policy explaining the no-silent-default-only contract.

---

### Task 1: Add Compact No-Default-Only Verdict To Operator Summary

**Files:**
- Modify: `src/hsconfig/operator_summary.py`
- Test: `tests/test_operator_summary.py`

**Interfaces:**
- Consumes: `technical_status: str`, `config_usefulness: dict[str, Any]`
- Produces: `_no_default_only_verdict(technical_status: str, config_usefulness: dict[str, Any]) -> dict[str, Any]`
- Produces in `build_operator_summary(...)`: top-level `no_default_only_verdict: dict[str, Any]`

- [ ] **Step 1: Write failing tests for verdict states**

Append these tests to `tests/test_operator_summary.py`:

```python
def test_operator_summary_no_default_only_verdict_none_detected():
    summary = build_operator_summary(
        deck_name="Clean Deck",
        deck_code="AAEBAQAAAA==",
        technical_validation={"status": "passed", "errors": []},
        guide_source_depth={"source_depth_status": "static_semantics_only", "claim_count": 0},
        mulligan_plan_report={
            "rules": [
                {
                    "card": "CARD_A",
                    "selector_kind": "card",
                    "action": "hold",
                    "source_type": "policy_backed_autonomous_mulligan",
                }
            ],
            "quality": {
                "status": "policy_backed",
                "has_concrete_keeps": True,
                "policy_backed_rule_count": 1,
                "policy_backed_keep_rule_count": 1,
            },
        },
        card_behavior_plan_report={"rows": []},
        combo_plan_report={"combos": [], "suppressed": []},
        globalvalues_profile_report={
            "changed_keys": ["FirstTurnValueWeight"],
            "unchanged_keys": [],
        },
        generated_files=[
            "CustomConfig/cleandeck/GlobalValues.json",
            "CustomConfig/cleandeck/Mulligan.json",
        ],
    )

    assert summary["runtime_apply_allowed"] is True
    assert summary["default_only_runtime_surfaces"] == []
    assert summary["no_default_only_verdict"] == {
        "status": "none_detected",
        "default_only_runtime_surface_count": 0,
        "runtime_permission_impact": "none",
        "blocking": False,
        "next_report_to_open": "reports/operator_summary.json",
    }


def test_operator_summary_no_default_only_verdict_visible_warning():
    summary = build_operator_summary(
        deck_name="Thin Deck",
        deck_code="AAEBAQAAAA==",
        technical_validation={"status": "passed", "errors": []},
        guide_source_depth={"source_depth_status": "static_semantics_only", "claim_count": 0},
        config_readiness_summary={
            "total_cards": 3,
            "runtime_emitted": 1,
            "report_only_supported": 1,
            "generic_low_confidence": 0,
            "cards_needing_guide_claims": 0,
            "cards_needing_runtime_surface": 0,
            "cards_needing_mulligan_claims": 0,
            "cards_needing_combo_sequence": 0,
            "cards_needing_condition_lowering": 0,
            "cards_needing_mechanic_lowering": 0,
        },
        mulligan_plan_report={
            "rules": [],
            "suppressed_rules": [],
            "quality": {
                "status": "thin",
                "has_concrete_keeps": False,
                "first_gap_reason": "no_source_backed_or_policy_backed_mulligan_keeps",
            },
        },
        card_behavior_plan_report={
            "rows": [
                {
                    "card_id": "CARD_A",
                    "meaningful_runtime_surface": True,
                    "behavior_block": {"BeforePlayCardBonus": {"values": []}},
                }
            ]
        },
        combo_plan_report={"combos": [], "suppressed": []},
        globalvalues_profile_report={"changed_keys": ["FirstTurnValueWeight"]},
        generated_files=[
            "CustomConfig/thindeck/GlobalValues.json",
            "CustomConfig/thindeck/Mulligan.json",
            "CustomConfig/thindeck/CARD_A.json",
        ],
    )

    assert summary["runtime_apply_allowed"] is True
    assert summary["default_only_runtime_surfaces"] == ["mulligan"]
    assert summary["no_default_only_verdict"] == {
        "status": "visible_warning",
        "default_only_runtime_surface_count": 1,
        "runtime_permission_impact": "none",
        "blocking": False,
        "next_report_to_open": "reports/operator_summary.json",
    }


def test_operator_summary_no_default_only_verdict_not_applicable_for_invalid_package():
    summary = build_operator_summary(
        deck_name="Invalid Deck",
        deck_code="AAEBAQAAAA==",
        technical_validation={"status": "failed", "errors": ["bad json"]},
        guide_source_depth={"source_depth_status": "static_semantics_only", "claim_count": 0},
        generated_files=[],
    )

    assert summary["runtime_apply_allowed"] is False
    assert summary["no_default_only_verdict"] == {
        "status": "not_applicable",
        "default_only_runtime_surface_count": 0,
        "runtime_permission_impact": "none",
        "blocking": False,
        "next_report_to_open": "reports/validation_report.json",
    }
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_operator_summary.py -q
```

Expected: fail with `KeyError: 'no_default_only_verdict'`.

- [ ] **Step 3: Implement minimal verdict helper**

In `src/hsconfig/operator_summary.py`, add this helper near `_default_only_runtime_surfaces`:

```python
def _no_default_only_verdict(
    technical_status: str,
    config_usefulness: dict[str, Any],
) -> dict[str, Any]:
    surfaces = _default_only_runtime_surfaces(config_usefulness)
    if technical_status != "VALID_PACKAGE":
        return {
            "status": "not_applicable",
            "default_only_runtime_surface_count": 0,
            "runtime_permission_impact": "none",
            "blocking": False,
            "next_report_to_open": "reports/validation_report.json",
        }
    if not surfaces:
        return {
            "status": "none_detected",
            "default_only_runtime_surface_count": 0,
            "runtime_permission_impact": "none",
            "blocking": False,
            "next_report_to_open": "reports/operator_summary.json",
        }
    return {
        "status": "visible_warning",
        "default_only_runtime_surface_count": len(surfaces),
        "runtime_permission_impact": "none",
        "blocking": False,
        "next_report_to_open": "reports/operator_summary.json",
    }
```

Then add this top-level field in the `summary = { ... }` dict in `build_operator_summary(...)`, immediately after `default_only_runtime_surfaces`:

```python
        "no_default_only_verdict": _no_default_only_verdict(
            technical_status,
            config_usefulness,
        ),
```

- [ ] **Step 4: Run tests to verify pass**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_operator_summary.py -q
```

Expected: pass.

- [ ] **Step 5: Commit task**

Run:

```powershell
git add src/hsconfig/operator_summary.py tests/test_operator_summary.py
git commit -m "feat: expose no default-only verdict"
```

---

### Task 2: Enrich Default-Only Surface Details With First Missing Link

**Files:**
- Modify: `src/hsconfig/operator_summary.py`
- Test: `tests/test_operator_summary.py`

**Interfaces:**
- Consumes: `source_to_runtime_explainability_report["card_rows"][].closure`
- Produces: `_default_only_risk_card_details(report: dict[str, Any]) -> list[dict[str, Any]]`
- Extends: `default_only_runtime_surface_details[]` rows with `first_missing_link`, `next_source_action`, `example_card_details`

- [ ] **Step 1: Write failing test for detail enrichment**

Append this test to `tests/test_operator_summary.py`:

```python
def test_default_only_surface_details_include_missing_link_and_card_details():
    summary = build_operator_summary(
        deck_name="Thin Deck",
        deck_code="AAEBAQAAAA==",
        technical_validation={"status": "passed", "errors": []},
        guide_source_depth={"source_depth_status": "static_semantics_only", "claim_count": 0},
        mulligan_plan_report={
            "rules": [],
            "suppressed_rules": [],
            "quality": {
                "status": "thin",
                "has_concrete_keeps": False,
                "first_gap_reason": "no_source_backed_or_policy_backed_mulligan_keeps",
            },
        },
        card_behavior_plan_report={
            "rows": [
                {
                    "card_id": "CARD_A",
                    "meaningful_runtime_surface": True,
                    "behavior_block": {"BeforePlayCardBonus": {"values": []}},
                }
            ]
        },
        combo_plan_report={"combos": [], "suppressed": []},
        globalvalues_profile_report={"changed_keys": ["FirstTurnValueWeight"]},
        source_to_runtime_explainability_report={
            "card_rows": [
                {
                    "card_id": "CARD_MISSING",
                    "name": "Missing Keep",
                    "closure": {
                        "lane": "baseline_only_visible",
                        "default_only_risk": True,
                        "first_missing_link": "opening_hand_mulligan_intent",
                        "next_source_action": "add_explicit_opening_hand_mulligan_source",
                    },
                }
            ]
        },
    )

    assert summary["default_only_runtime_surface_details"] == [
        {
            "surface": "mulligan",
            "status": "default_only",
            "card_count_with_default_only_risk": 1,
            "example_cards": ["CARD_MISSING Missing Keep"],
            "example_card_details": [
                {
                    "card_id": "CARD_MISSING",
                    "name": "Missing Keep",
                    "closure_lane": "baseline_only_visible",
                    "first_missing_link": "opening_hand_mulligan_intent",
                    "next_source_action": "add_explicit_opening_hand_mulligan_source",
                }
            ],
            "first_missing_link": "opening_hand_mulligan_intent",
            "next_source_action": "add_explicit_opening_hand_mulligan_source",
            "operator_impact": "diagnostic_only",
            "apply_blocking": False,
        }
    ]
```

- [ ] **Step 2: Run test to verify failure**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_operator_summary.py::test_default_only_surface_details_include_missing_link_and_card_details -q
```

Expected: fail because `example_card_details`, `first_missing_link`, or `next_source_action` is absent.

- [ ] **Step 3: Implement detail helper**

In `src/hsconfig/operator_summary.py`, replace `_default_only_risk_cards(...)` with a detail-producing helper and keep a compatibility projection:

```python
def _default_only_risk_card_details(report: dict[str, Any]) -> list[dict[str, Any]]:
    rows = report.get("card_rows", []) if isinstance(report, dict) else []
    if not isinstance(rows, list):
        return []

    result: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        closure = row.get("closure", {})
        if not isinstance(closure, dict) or closure.get("default_only_risk") is not True:
            continue
        card_id = str(row.get("card_id", "")).strip()
        name = str(row.get("name", "")).strip()
        result.append(
            {
                "card_id": card_id,
                "name": name,
                "closure_lane": str(closure.get("lane", "")),
                "first_missing_link": closure.get("first_missing_link"),
                "next_source_action": closure.get("next_source_action"),
            }
        )
    return sorted(result, key=lambda item: (str(item["card_id"]), str(item["name"])))


def _default_only_risk_cards(report: dict[str, Any]) -> list[str]:
    return [
        f'{row["card_id"]} {row["name"]}'.strip()
        for row in _default_only_risk_card_details(report)
    ]
```

Then update `_default_only_runtime_surface_details(...)`:

```python
    risky_card_details = _default_only_risk_card_details(
        source_to_runtime_explainability_report
    )
    risky_cards = [
        f'{row["card_id"]} {row["name"]}'.strip()
        for row in risky_card_details
    ]
    first_detail = risky_card_details[0] if risky_card_details else {}
```

Inside the appended detail dict, add these fields before `operator_impact`:

```python
                "example_card_details": risky_card_details[:5],
                "first_missing_link": first_detail.get("first_missing_link"),
                "next_source_action": first_detail.get("next_source_action"),
```

- [ ] **Step 4: Run targeted test**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_operator_summary.py::test_default_only_surface_details_include_missing_link_and_card_details -q
```

Expected: pass.

- [ ] **Step 5: Run operator summary suite**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_operator_summary.py -q
```

Expected: pass.

- [ ] **Step 6: Commit task**

Run:

```powershell
git add src/hsconfig/operator_summary.py tests/test_operator_summary.py
git commit -m "feat: explain default-only surface gaps"
```

---

### Task 3: Lock Source-To-Runtime Closure Vocabulary

**Files:**
- Modify: `src/hsconfig/source_to_runtime_explainability.py`
- Test: `tests/test_source_to_runtime_explainability.py`

**Interfaces:**
- Consumes: existing `card_rows[].closure.lane`
- Produces in `operator_attention[]`: `closure_lane: str`, `default_only_risk: bool`
- Preserves: `authority="diagnostic_only"`, `operator_gate_impact="diagnostic_only"`, `apply_blocking=False`

- [ ] **Step 1: Write failing assertion for closure metadata in operator attention**

In `tests/test_source_to_runtime_explainability.py`, update `test_explainability_operator_attention_marks_no_missing_link_without_runtime_files` expected row to include:

```python
            "closure_lane": "diagnostic_only",
            "default_only_risk": False,
```

Also add this test:

```python
def test_explainability_operator_attention_exposes_baseline_default_only_risk():
    audit = {
        "schema_version": 1,
        "deck_name": "FixtureDeck",
        "claim_rows": {},
        "claim_lifecycle_rows": [],
        "card_rows": {
            "CARD_BASE": {
                "name": "Baseline Card",
                "readiness_lane": "generic_low_confidence",
                "first_missing_link": "none",
                "runtime_surfaces": [],
                "claim_lanes": {},
            }
        },
    }

    report = build_source_to_runtime_explainability_report(audit)

    assert report["apply_blocking"] is False
    assert report["operator_attention"] == [
        {
            "card_id": "CARD_BASE",
            "name": "Baseline Card",
            "status": "baseline_only_visible",
            "closure_lane": "baseline_only_visible",
            "default_only_risk": True,
            "first_missing_link": None,
            "next_source_action": "none",
            "strongest_claim_id": None,
            "strongest_claim_kind": None,
            "emitted_runtime_files": [],
            "not_emitted_runtime_files": [],
        }
    ]
```

- [ ] **Step 2: Run targeted tests to verify failure**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_source_to_runtime_explainability.py -q
```

Expected: fail because `closure_lane` and `default_only_risk` are absent from `operator_attention`.

- [ ] **Step 3: Add closure metadata to operator attention rows**

In `src/hsconfig/source_to_runtime_explainability.py`, update `_operator_attention_rows(...)` so it reads the closure row:

```python
        closure = row.get("closure", {})
        closure_lane = (
            str(closure.get("lane", status))
            if isinstance(closure, dict)
            else status
        )
        default_only_risk = (
            bool(closure.get("default_only_risk"))
            if isinstance(closure, dict)
            else False
        )
```

Add these keys to the dict appended to `rows`:

```python
                "closure_lane": closure_lane,
                "default_only_risk": default_only_risk,
```

- [ ] **Step 4: Run source-to-runtime explainability tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_source_to_runtime_explainability.py -q
```

Expected: pass after updating expected rows that now include `closure_lane` and `default_only_risk`.

- [ ] **Step 5: Run closure-adjacent tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_source_to_runtime_explainability.py tests/test_source_contract_audit.py tests/test_source_contract_conformance.py -q
```

Expected: pass.

- [ ] **Step 6: Commit task**

Run:

```powershell
git add src/hsconfig/source_to_runtime_explainability.py tests/test_source_to_runtime_explainability.py
git commit -m "feat: expose closure lanes in explainability"
```

---

### Task 4: Add Darkbishop Regression Anchor To The No-Silent-Default-Only Contract

**Files:**
- Modify: `tests/test_shadowpriest_depth_e2e.py`

**Interfaces:**
- Consumes: existing `main(["prepare", ...])` CLI path
- Produces: regression proof that `SW_448` is not a Mulligan keep but remains in CardID/runtime behavior output

- [ ] **Step 1: Add focused regression test**

Append this test to `tests/test_shadowpriest_depth_e2e.py`:

```python
def test_shadowpriest_darkbishop_effect_visible_without_mulligan_keep(tmp_path: Path, capsys):
    out = tmp_path / "shadowpriest_darkbishop"

    result = main(
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
            "--guide-sources-json",
            "tests/fixtures/shadowpriest_guide_sources.json",
            "--json",
        ]
    )
    capsys.readouterr()

    deck_dir = out / "CustomConfig" / "shadowpriest"
    reports = out / "reports"
    mulligan = json.loads((deck_dir / "Mulligan.json").read_text(encoding="utf-8"))
    darkbishop = json.loads((deck_dir / "SW_448.json").read_text(encoding="utf-8"))
    explainability = json.loads(
        (reports / "source_to_runtime_explainability.json").read_text(encoding="utf-8")
    )

    concrete_keeps = [
        row["mulligan"]
        for row in mulligan["Mulligan"]["values"]
        if row["value"] == "hold" and row["mulligan"] != "*"
    ]
    darkbishop_attention = [
        row for row in explainability["operator_attention"] if row["card_id"] == "SW_448"
    ]

    assert result == 0
    assert "SW_448" not in concrete_keeps
    assert darkbishop
    assert any("Bonus" in key or "HeroPower" in key for key in darkbishop)
    assert darkbishop_attention
    assert darkbishop_attention[0]["status"] in {
        "runtime_backed",
        "diagnostic_only",
        "baseline_only_visible",
    }
    assert darkbishop_attention[0]["default_only_risk"] is False
```

- [ ] **Step 2: Run test**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_shadowpriest_depth_e2e.py::test_shadowpriest_darkbishop_effect_visible_without_mulligan_keep -q
```

Expected: pass. If it fails because the exact CardID behavior keys differ, inspect `SW_448.json` and assert the real key that represents hero-power-transform behavior. Do not re-add `SW_448` to `Mulligan.json`.

- [ ] **Step 3: Run ShadowPriest focused suite**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_shadowpriest_depth_e2e.py tests/test_shadowpriest_fresh_closure_proof.py tests/test_shadowpriest_e2e.py -q
```

Expected: pass.

- [ ] **Step 4: Commit task**

Run:

```powershell
git add tests/test_shadowpriest_depth_e2e.py
git commit -m "test: lock Darkbishop effect without mulligan keep"
```

---

### Task 5: Update Operator Docs With No-Silent-Default-Only Policy

**Files:**
- Modify: `docs/operator/README.md`
- Modify: `docs/operator/guide-research-policy.md`
- Test: `tests/test_operator_docs_contract_policy.py`

**Interfaces:**
- Consumes: current docs wording around `default_only_runtime_surfaces`, `operator_summary.json`, source-to-runtime explainability.
- Produces: docs that state default-only warnings are visible and non-blocking, not a second gate.

- [ ] **Step 1: Add docs regression test**

Open `tests/test_operator_docs_contract_policy.py` and add this test:

```python
from pathlib import Path


def test_operator_docs_state_no_silent_default_only_without_second_gate():
    docs = "\n".join(
        [
            Path("docs/operator/README.md").read_text(encoding="utf-8"),
            Path("docs/operator/guide-research-policy.md").read_text(encoding="utf-8"),
        ]
    )

    assert "no-silent-default-only" in docs.lower()
    assert "visible quality" in docs.lower()
    assert "not an apply blocker" in docs.lower()
    assert "operator_summary.json remains the only normal apply authority" in docs
```

If the file already imports `Path`, do not duplicate the import.

- [ ] **Step 2: Run docs test to verify failure**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_operator_docs_contract_policy.py -q
```

Expected: fail until docs include the exact policy language.

- [ ] **Step 3: Patch `docs/operator/README.md`**

Add this short paragraph near the current `default_only_runtime_surfaces` guidance:

```markdown
No-silent-default-only policy: default-only or thin runtime surfaces are visible quality debt, not an apply blocker. `operator_summary.json` remains the only normal apply authority. When `default_only_runtime_surfaces` is non-empty, open `default_only_runtime_surface_details` and `reports/source_to_runtime_explainability.json` to see the first missing source-to-runtime link before improving guide claims or policy-backed defaults.
```

- [ ] **Step 4: Patch `docs/operator/guide-research-policy.md`**

Add this short paragraph near the source-to-runtime / apply authority section:

```markdown
No-silent-default-only contract: a valid package must not hide baseline-only runtime behavior. Default-only surfaces are reported as visible quality debt through `operator_summary.json`, `default_only_runtime_surface_details`, and `source_to_runtime_explainability.json`; they are not an apply blocker unless the technical package is invalid. operator_summary.json remains the only normal apply authority.
```

- [ ] **Step 5: Run docs test**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_operator_docs_contract_policy.py -q
```

Expected: pass.

- [ ] **Step 6: Commit task**

Run:

```powershell
git add docs/operator/README.md docs/operator/guide-research-policy.md tests/test_operator_docs_contract_policy.py
git commit -m "docs: define no-silent-default-only policy"
```

---

### Task 6: Final Verification And Guardrail Scan

**Files:**
- No source files should be edited in this task.
- Verify: all files modified by Tasks 1-5.

**Interfaces:**
- Consumes: all prior task outputs.
- Produces: verified working tree ready for normal branch completion.

- [ ] **Step 1: Run focused no-default-only closure suite**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_operator_summary.py tests/test_config_usefulness.py tests/test_source_to_runtime_explainability.py tests/test_shadowpriest_depth_e2e.py tests/test_operator_docs_contract_policy.py -q
```

Expected: pass.

- [ ] **Step 2: Run apply-boundary guardrail suite**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_apply_gate.py tests/test_apply_authority_boundary.py tests/test_no_second_gate_contract.py tests/test_source_contract_audit.py tests/test_source_contract_conformance.py -q
```

Expected: pass.

- [ ] **Step 3: Run representative Wild/no-block matrix**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_universal_wild_no_block_matrix.py tests/test_no_default_only_semantic_archetype_matrix.py tests/test_real_deck_usage_loop.py -q
```

Expected: pass.

- [ ] **Step 4: Run contract guardrail script if present**

Run:

```powershell
if (Test-Path scripts/check_contract_guardrails.py) { $env:PYTHONPATH='src'; python scripts/check_contract_guardrails.py }
```

Expected: command exits with code 0, or no output if the script is absent.

- [ ] **Step 5: Validate the current research JSON package**

Run:

```powershell
python C:\Users\darbo\.codex\skills\research\validate_json.py -f docs\research\2026-07-14-hsconfig-source-contract-autonomy-current-audit\fields.yaml -d docs\research\2026-07-14-hsconfig-source-contract-autonomy-current-audit\results -q
```

Expected:

```text
Validation passed: 4/4
Average coverage: 100.0%
```

- [ ] **Step 6: Run full test suite if focused suites are green**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest -q
```

Expected: pass. If this is slow, keep the command running until completion rather than replacing it with a smaller suite.

- [ ] **Step 7: Inspect status and diff**

Run:

```powershell
git status --short --branch
git diff --stat
git diff -- src/hsconfig/operator_summary.py src/hsconfig/source_to_runtime_explainability.py tests/test_operator_summary.py tests/test_source_to_runtime_explainability.py tests/test_shadowpriest_depth_e2e.py tests/test_operator_docs_contract_policy.py docs/operator/README.md docs/operator/guide-research-policy.md
```

Expected:

- Only planned source, test, docs, and accepted research/plan files are changed.
- No runtime evidence, HearthRanger logs, Power.log, HDT replay, or private game data is staged.
- `apply_gate.py` is unchanged unless a guardrail test explicitly forced a narrow fix.

- [ ] **Step 8: Final commit if any verification-only docs or tests were adjusted**

Run only if Task 6 changed files:

```powershell
git add <changed-files>
git commit -m "test: verify no-silent-default-only closure"
```

---

## Self-Review

- Spec coverage: The plan covers the recommendation: no new gate, one normal apply authority, visible default-only warnings, source-to-runtime closure detail, Darkbishop effect-vs-Mulligan boundary, and docs clarity.
- Placeholder scan: No placeholder tokens or vague implementation-only steps remain. Each code-changing task includes concrete test snippets, implementation snippets, commands, and expected results.
- Type consistency: The new helper signatures use existing `dict[str, Any]` style from `operator_summary.py`; new JSON keys use snake_case matching existing report fields.
- Scope check: The plan is intentionally a micro-hardening wave. It does not add HSTuner behavior, replay parsing, winrate analysis, new dependencies, or a new runtime surface.
- Risk: Some existing expected dictionaries in `tests/test_source_to_runtime_explainability.py` may need mechanical updates after adding `closure_lane` and `default_only_risk` to operator attention rows. That is expected in Task 3 and should remain limited to that test file.

# HSConfig Claim Lifecycle Closure And No-Block Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the remaining HSConfig source-contract gap so every source claim has a visible lifecycle end state while every technically valid deck package remains non-blocking and load-safe.

**Architecture:** Build on the existing `claim_lifecycle_rows` trace in `source_contract_audit.json`. Add small contract tests and summary fields around allowed-but-unseen claims, diagnostic-only leakage, and Darkbishop-style start-of-game effects. Keep `operator_summary.json` as the only normal apply/readiness authority and keep `source_contract_audit.json` diagnostic-only.

**Tech Stack:** Python 3, existing HSConfig modules under `src/hsconfig`, existing `pytest` suite, existing CLI/package-builder flow, no new dependencies.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig`.
- Do not create a new architecture, new CLI, new dependency, or new runtime writer.
- Do not block valid package generation because a source claim cannot lower to runtime.
- Do not treat guide-depth weakness, missing exact mulligan claims, unsupported runtime surfaces, or low confidence as technical hard blocks.
- Preserve hard blocks only for technical invalidity: bad deckcode, invalid JSON, unsupported filenames/blocks, missing required runtime files, forged/stale apply gates, or malformed package structure.
- Keep `operator_summary.json` small and authoritative for normal operator decisions.
- Keep `source_contract_audit.json.claim_lifecycle_rows` diagnostic-only.
- Preserve the ShadowPriest/Darkbishop split: `SW_448` can encode start-of-game Hero Power transformation behavior, but must not be emitted as an opening-hand Mulligan keep unless a separate explicit mulligan-anchor source exists.
- Do not commit raw runtime evidence, HDT files, HSReplay files, Power.log files, or private logs.

---

## File Structure

Modify only these files unless a failing test proves a narrow adjacent edit is needed:

- `C:\Users\darbo\Documents\HSConfig\src\hsconfig\source_contract_audit.py`
  - Owns lifecycle trace rows, missing-link labels, diagnostic summary counts, and markdown rendering.
- `C:\Users\darbo\Documents\HSConfig\src\hsconfig\operator_summary.py`
  - Owns normal operator summary and must not embed full lifecycle rows.
- `C:\Users\darbo\Documents\HSConfig\tests\test_source_contract_audit.py`
  - Unit-level lifecycle and missing-link contract tests.
- `C:\Users\darbo\Documents\HSConfig\tests\test_prepare_cli.py`
  - Package-level proof that source audit remains diagnostic and operator summary remains the gate.
- `C:\Users\darbo\Documents\HSConfig\tests\test_shadowpriest_e2e.py`
  - Darkbishop regression: effect survives, mulligan keep does not.
- `C:\Users\darbo\Documents\HSConfig\docs\operator\guide-research-policy.md`
  - Concise operator-facing explanation of lifecycle end states.
- `C:\Users\darbo\Documents\HSConfig\.agents\skills\hsconfig\SKILL.md`
  - Compact skill instruction update only if docs wording needs to be discoverable by the skill.

Do not edit generated config packages for this plan.

---

### Task 1: Lifecycle End-State Vocabulary

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\source_contract_audit.py`
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_source_contract_audit.py`

**Interfaces:**
- Consumes: `build_source_contract_audit(...)`
- Produces: `source_contract_audit["summary"]["claim_lifecycle_decision_counts"]`
- Produces: lifecycle row `builder_or_router_decision` values constrained to:
  - `emitted`
  - `suppressed`
  - `not_seen_by_builder`

- [ ] **Step 1: Add the failing unit test for allowed-but-unseen claims**

Append this test to `tests/test_source_contract_audit.py`:

```python
def test_claim_lifecycle_marks_allowed_claim_without_builder_emission_as_not_seen_by_builder():
    report = build_source_contract_audit(
        deck_name="FixtureDeck",
        deck_identity={"deck_name": "FixtureDeck", "cards": []},
        guide_claim_bundle={
            "claims": [
                {
                    "claim_id": "posture_claim",
                    "claim_kind": "gameplan_posture",
                    "claim_readiness": "guide_backed",
                    "trust_ceiling": "runtime_candidate",
                    "cards": [],
                    "source_title": "Fixture Guide",
                    "evidence_text_short": "Use a more aggressive posture.",
                }
            ]
        },
        mulligan_plan={"rules": [], "suppressed_rules": []},
        card_behavior_plan={"rows": [], "suppressed": []},
        combo_plan={"combos": [], "suppressed": []},
        global_values_authority_matrix={
            "allowed_step1_overlays": [],
            "blocked_until_runtime_evidence": [],
        },
        config_readiness_report={"cards": {}},
    )

    row = report["claim_lifecycle_rows"][0]

    assert row["claim_id"] == "posture_claim"
    assert row["claim_kind"] == "gameplan_posture"
    assert row["surface_gate_decision"] == "allowed"
    assert row["surface_gate_reason"] == "allowed"
    assert row["builder_or_router_decision"] == "not_seen_by_builder"
    assert row["suppressed_reason"] == "builder_or_router_missing"
    assert row["first_missing_link"] == "builder_or_router"
    assert row["operator_impact"] == "diagnostic_only"
```

- [ ] **Step 2: Add the failing unit test for lifecycle decision counts**

Append this test to `tests/test_source_contract_audit.py`:

```python
def test_source_contract_audit_summarizes_claim_lifecycle_decisions():
    report = build_source_contract_audit(
        deck_name="FixtureDeck",
        deck_identity={
            "deck_name": "FixtureDeck",
            "cards": [{"card_id": "CARD_KEEP", "name": "Keep Card", "count": 2}],
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
                },
                {
                    "claim_id": "posture_claim",
                    "claim_kind": "gameplan_posture",
                    "claim_readiness": "guide_backed",
                    "trust_ceiling": "runtime_candidate",
                    "cards": [],
                    "source_title": "Fixture Guide",
                    "evidence_text_short": "Use a more aggressive posture.",
                },
                {
                    "claim_id": "numeric_claim",
                    "claim_kind": "globalvalue_numeric_tuning",
                    "claim_readiness": "guide_backed",
                    "trust_ceiling": "runtime_candidate",
                    "cards": [],
                    "source_title": "Fixture Guide",
                    "evidence_text_short": "Tune a numeric GlobalValues key only after games.",
                },
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
            "blocked_until_runtime_evidence": [
                {
                    "key": "LowHpBoardValuePenalty",
                    "claim_id": "numeric_claim",
                    "reason": "runtime_evidence_required",
                }
            ],
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

    assert report["summary"]["claim_lifecycle_decision_counts"] == {
        "emitted": 1,
        "not_seen_by_builder": 1,
        "suppressed": 1,
    }
```

- [ ] **Step 3: Run the focused tests and verify failure**

```powershell
cd C:\Users\darbo\Documents\HSConfig
$env:PYTHONPATH='src'
pytest -q tests/test_source_contract_audit.py -k "not_seen_by_builder or lifecycle_decisions"
```

Expected before implementation: the first test may already pass if the existing fallback is correct; the second test should fail because `claim_lifecycle_decision_counts` is not yet in `summary`.

- [ ] **Step 4: Add the minimal implementation**

In `src/hsconfig/source_contract_audit.py`, after `claim_lifecycle_rows = _build_claim_lifecycle_rows(...)`, inject decision counts into the existing `summary` dict:

```python
    claim_lifecycle_rows = _build_claim_lifecycle_rows(
        list(claim_rows.values()),
        runtime_emission_index=runtime_emission_index,
    )
    summary["claim_lifecycle_decision_counts"] = _claim_lifecycle_decision_counts(
        claim_lifecycle_rows
    )
```

Add this helper near the other lifecycle helpers:

```python
def _claim_lifecycle_decision_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts = Counter(str(row.get("builder_or_router_decision", "")) for row in rows)
    return {
        decision: counts[decision]
        for decision in ("emitted", "not_seen_by_builder", "suppressed")
        if counts[decision]
    }
```

- [ ] **Step 5: Run the focused tests and verify pass**

```powershell
$env:PYTHONPATH='src'
pytest -q tests/test_source_contract_audit.py -k "not_seen_by_builder or lifecycle_decisions"
```

Expected: PASS.

---

### Task 2: Operator Summary Must Stay Small And Non-Gating

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_prepare_cli.py`
- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\operator_summary.py` only if the test fails

**Interfaces:**
- Consumes: generated `reports/source_contract_audit.json`
- Consumes: generated `reports/operator_summary.json`
- Produces: operator summary that has only compact source-audit summary fields, never full lifecycle rows.

- [ ] **Step 1: Tighten the package-level regression**

In `tests/test_prepare_cli.py`, find the existing test that asserts:

```python
assert "claim_lifecycle_rows" not in operator_summary
```

Extend that assertion block with:

```python
    assert "claim_rows" not in operator_summary
    assert "card_rows" not in operator_summary
    assert "claim_lifecycle_decision_counts" in audit["summary"]
    assert "claim_lifecycle_decision_counts" in operator_summary["source_contract_audit_summary"]
    assert operator_summary["source_contract_audit_summary"]["non_blocking"] is True
```

- [ ] **Step 2: Run the specific CLI test**

```powershell
$env:PYTHONPATH='src'
pytest -q tests/test_prepare_cli.py -k "source_contract_audit"
```

Expected before implementation: fail only if `source_contract_audit_summary` does not surface compact lifecycle decision counts.

- [ ] **Step 3: Add compact summary forwarding only if needed**

If the test fails because `operator_summary["source_contract_audit_summary"]` lacks the counts, update the existing `_source_contract_audit_summary(...)` helper in `src/hsconfig/operator_summary.py` so it returns:

```python
"claim_lifecycle_decision_counts": dict(
    summary.get("claim_lifecycle_decision_counts", {})
),
```

Do not forward `claim_lifecycle_rows`, `claim_rows`, or `card_rows`.

- [ ] **Step 4: Re-run the specific CLI test**

```powershell
$env:PYTHONPATH='src'
pytest -q tests/test_prepare_cli.py -k "source_contract_audit"
```

Expected: PASS.

---

### Task 3: ShadowPriest/Darkbishop Effect-Versus-Mulligan Regression

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_shadowpriest_e2e.py`
- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\source_document_model.py` only if the test fails
- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\source_contract_audit.py` only if the test fails

**Interfaces:**
- Consumes: ShadowPriest fixture E2E flow in `tests/test_shadowpriest_e2e.py`
- Produces: explicit proof that `SW_448` can be CardID/Hero Power runtime behavior without being a Mulligan keep.

- [ ] **Step 1: Tighten the ShadowPriest lifecycle assertions**

In `tests/test_shadowpriest_e2e.py`, replace any permissive check that accepts legacy `"lowered"` lifecycle decisions for `SW_448` with the canonical decision vocabulary:

```python
    assert any(
        row["claim_kind"] == "hero_power_transform"
        and row["builder_or_router_decision"] == "emitted"
        and (
            row["runtime_surface"] in {"SW_448.json", "<CARDID>.json", "CARDID.json"}
            or "SW_448.json" in row["emitted_files"]
        )
        for row in darkbishop_lifecycle_rows
    )
    assert not any(
        row["claim_kind"] == "mulligan_keep"
        and row["builder_or_router_decision"] == "emitted"
        for row in darkbishop_lifecycle_rows
    )
```

- [ ] **Step 2: Run the ShadowPriest E2E test**

```powershell
$env:PYTHONPATH='src'
pytest -q tests/test_shadowpriest_e2e.py
```

Expected before implementation: fail only if the lifecycle vocabulary still emits or tolerates a legacy `"lowered"` state.

- [ ] **Step 3: Normalize lifecycle decision vocabulary if needed**

If a lifecycle row still reports `"lowered"`, update `src/hsconfig/source_contract_audit.py` where emission decisions are collected so any legacy `"lowered"` input is normalized to `"emitted"` before rows are returned:

```python
def _normalized_lifecycle_decision(value: Any) -> str:
    decision = str(value or "")
    if decision == "lowered":
        return "emitted"
    if decision in {"emitted", "suppressed", "not_seen_by_builder"}:
        return decision
    return ""
```

Use it inside `_build_claim_lifecycle_rows(...)`:

```python
        decision = _normalized_lifecycle_decision(emission.get("decision", ""))
```

- [ ] **Step 4: Re-run the ShadowPriest E2E test**

```powershell
$env:PYTHONPATH='src'
pytest -q tests/test_shadowpriest_e2e.py
```

Expected: PASS.

---

### Task 4: No-Block Semantics For Valid Packages With Warning Debt

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_prepare_cli.py`
- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\operator_summary.py` only if the test fails

**Interfaces:**
- Consumes: existing package validation and operator summary behavior.
- Produces: explicit proof that source-depth debt remains a warning, not a runtime apply hard block.

- [ ] **Step 1: Add or extend a CLI/package test for warning-only debt**

Add this assertion to the existing source-audit prepare test after `operator_summary` is read:

```python
    assert operator_summary["technical_status"] == "VALID_PACKAGE"
    assert operator_summary["runtime_apply_allowed"] is True
    assert operator_summary["runtime_apply_mode"] == "load_safe_apply"
    assert operator_summary["source_contract_audit_summary"]["non_blocking"] is True
```

- [ ] **Step 2: Run the relevant tests**

```powershell
$env:PYTHONPATH='src'
pytest -q tests/test_prepare_cli.py -k "source_contract_audit or warnings"
```

Expected: PASS. If it fails because semantic debt blocks `runtime_apply_allowed`, fix only the semantic-vs-technical gate split. Do not weaken technical validation.

---

### Task 5: Operator Docs And Skill Wording

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\docs\operator\guide-research-policy.md`
- Modify: `C:\Users\darbo\Documents\HSConfig\.agents\skills\hsconfig\SKILL.md` only if the skill does not already say this clearly

**Interfaces:**
- Consumes: lifecycle decisions and no-block semantics from Tasks 1-4.
- Produces: concise docs that explain the workflow without making operators read internal code.

- [ ] **Step 1: Update guide research policy wording**

In `docs/operator/guide-research-policy.md`, ensure there is a concise section with this content:

```markdown
### Claim Lifecycle End States

`source_contract_audit.json.claim_lifecycle_rows` is diagnostic-only. Each source
claim should end in one visible state:

- `emitted`: a source claim reached a runtime file.
- `suppressed`: a source claim was intentionally not emitted because the source,
  confidence, runtime evidence, or VisionAI surface did not allow it.
- `not_seen_by_builder`: the source and surface gate allowed a claim, but no
  builder/router emitted it. Treat this as implementation debt, not an operator
  apply block.

Use `operator_summary.json` for normal readiness and apply decisions. Do not use
`source_contract_audit.json` as an apply gate.
```

- [ ] **Step 2: Update skill wording only if missing**

In `.agents/skills/hsconfig/SKILL.md`, ensure the normal guidance says:

```markdown
When a package is technically valid but source depth is weak, continue and report
the debt. Do not block valid deck packages because a claim is low confidence,
report-only, unsupported by a runtime surface, or visible only in
`source_contract_audit.json`.
```

- [ ] **Step 3: Run doc/skill checks**

```powershell
$env:PYTHONPATH='src'
pytest -q tests/test_skill_files.py -k "claim_lifecycle or no_block or operator"
```

Expected: PASS.

---

### Task 6: Final Verification

**Files:**
- No code changes unless a verification failure identifies a narrow bug.

- [ ] **Step 1: Run focused source-contract tests**

```powershell
cd C:\Users\darbo\Documents\HSConfig
$env:PYTHONPATH='src'
pytest -q tests/test_source_contract_audit.py tests/test_claim_kind_runtime_contract.py
```

Expected: PASS.

- [ ] **Step 2: Run package/operator tests**

```powershell
$env:PYTHONPATH='src'
pytest -q tests/test_prepare_cli.py tests/test_operator_summary.py tests/test_skill_files.py
```

Expected: PASS.

- [ ] **Step 3: Run ShadowPriest regression**

```powershell
$env:PYTHONPATH='src'
pytest -q tests/test_shadowpriest_e2e.py
```

Expected: PASS.

- [ ] **Step 4: Run the broader suite if focused tests pass**

```powershell
$env:PYTHONPATH='src'
pytest -q
```

Expected: PASS or only known unrelated failures. Any failure in source-contract, package build, operator summary, apply gate, or ShadowPriest tests must be fixed before completion.

- [ ] **Step 5: Inspect diff**

```powershell
git status --short --branch
git diff -- src tests docs .agents
```

Expected: only the files listed in this plan changed.

---

## Subagent-Driven Execution Map

- [ ] **Subagent 1 - Test Worker:** Add Task 1 and Task 2 tests only. No implementation edits.
- [ ] **Subagent 2 - Source Contract Worker:** Implement only `source_contract_audit.py` changes needed by Task 1 and Task 3.
- [ ] **Subagent 3 - Operator Worker:** Implement only compact forwarding in `operator_summary.py` if Task 2 or Task 4 fails.
- [ ] **Subagent 4 - Docs Worker:** Update docs/skill wording after tests define final language.
- [ ] **Main Agent - Integrator:** Run focused tests after each subagent, resolve conflicts, run final verification, then commit.

Review gate after each subagent:

```powershell
git diff --stat
$env:PYTHONPATH='src'
pytest -q tests/test_source_contract_audit.py tests/test_prepare_cli.py tests/test_shadowpriest_e2e.py -q
```

---

## Self-Review

- Spec coverage: This plan covers the recommended Claim Lifecycle Closure Mini-Wave, no-block semantics, Darkbishop effect-versus-mulligan regression, operator-summary non-leakage, and concise docs.
- Placeholder scan: No banned placeholder phrases or unspecified implementation blocks are used.
- Type consistency: The plan uses existing public functions: `build_source_contract_audit(...)`, `surface_gate_decision(...)`, and existing JSON fields in `source_contract_audit.json` / `operator_summary.json`.
- Scope discipline: No new dependency, CLI, runtime writer, or new architecture is introduced.

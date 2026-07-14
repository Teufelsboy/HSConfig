# Surface Status Ledger No-Silent-Default-Only Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one compact operator-facing `surface_status_ledger` to `reports/operator_summary.json` so every runtime surface exposes whether it is source-backed, policy-backed, static-semantics-backed, warning-only, suppressed, or default-only without creating another apply gate.

**Architecture:** Keep the existing HSConfig pipeline and apply authority. `config_usefulness` remains the source of surface-richness rows, `operator_summary.json` remains the only normal apply authority, and the new ledger is a diagnostic projection beside `default_only_runtime_surfaces` and `default_only_runtime_surface_details`.

**Tech Stack:** Python 3, existing HSConfig package modules under `src/hsconfig`, pytest, existing contract guardrail script `python scripts/check_contract_guardrails.py`.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig`.
- Do not create a second apply gate.
- Do not let diagnostic reports grant or block runtime apply.
- Keep `reports/operator_summary.json` as the only normal apply authority.
- Keep `source_contract_audit.json`, `source_to_runtime_explainability.json`, `config_usefulness`, and `contract-spine-sentinel` diagnostic-only.
- Default-only runtime surfaces must be visible, not silent.
- Weak source quality, warning-only mechanics, unresolved option identity, and source-depth gaps must remain non-blocking when the package is technically valid.
- Do not add new runtime surfaces such as `Presume.json`, `Concede.json`, or aggregate `CardBehavior.json`.
- Preserve the Darkbishop boundary: effect / hero-power-transform behavior may lower to CardID behavior; it must not become a Mulligan keep without explicit opening-hand evidence.
- No new dependency.

---

## File Structure

- Modify `src/hsconfig/operator_summary.py`
  - Add `_surface_status_ledger(config_usefulness, source_to_runtime_explainability_report)`.
  - Add `"surface_status_ledger"` to the summary object.
  - Keep the helper local to avoid a new module for a projection that belongs to operator summary.
- Modify `tests/test_operator_summary.py`
  - Add focused tests for policy-backed, default-only, invalid-package, and warning-only ledger rows.
  - Extend existing default-only tests so old fields and new ledger stay aligned.
- Modify `tests/test_no_default_only_semantic_archetype_matrix.py`
  - Assert generated representative packages have no default-only ledger rows.
- Modify `tests/test_shadowpriest_fresh_closure_proof.py`
  - Assert ShadowPriest has `surface_status_ledger` rows, no `default_only`, and Darkbishop remains effect-not-mulligan through existing checks.
- Modify `tests/test_contract_spine_sentinel.py`
  - Add one invariant test that the ledger is diagnostic-only and not a gate file.
- Modify `docs/operator/README.md`
  - Add the ledger as the first compact surface-health table inside `operator_summary.json`.
- Modify `docs/operator/guide-research-policy.md`
  - Add the ledger semantics to the no-silent-default-only policy.
- Modify `.agents/skills/hsconfig/SKILL.md`
  - Tell the skill to read `surface_status_ledger` before deeper reports.
- Sync installed skill copy at `C:\Users\darbo\.codex\skills\hsconfig\SKILL.md`
  - Use `python scripts/sync_installed_skill.py`; do not add this out-of-repo file to the HSConfig commit.

---

### Task 1: Lock the Operator Summary Ledger Contract

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_operator_summary.py`
- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\operator_summary.py`

**Interfaces:**
- Consumes: `build_operator_summary(...) -> dict[str, Any]`.
- Produces: `summary["surface_status_ledger"] -> list[dict[str, Any]]`.
- Ledger row shape:
  - `surface: str`
  - `status: str`
  - `default_only: bool`
  - `apply_blocking: bool`
  - `operator_impact: "diagnostic_only"`
  - `runtime_permission_impact: "none"`
  - `first_missing_link: str | None`
  - `next_source_action: str | None`
  - `next_report_to_open: str`

- [ ] **Step 1: Add failing policy-backed ledger test**

Append this test near the existing policy-backed Mulligan tests in `tests/test_operator_summary.py`:

```python
def test_operator_summary_surface_status_ledger_marks_policy_backed_mulligan():
    summary = build_operator_summary(
        deck_name="PirateRogue",
        deck_code="AAE=",
        technical_validation={"status": "passed", "errors": []},
        guide_source_depth={"source_depth_status": "static_semantics_only", "claim_count": 0},
        generated_files=[
            "CustomConfig/piraterogue/GlobalValues.json",
            "CustomConfig/piraterogue/Mulligan.json",
        ],
        mulligan_plan_report={
            "rules": [
                {
                    "card": "PIRATE",
                    "selector_kind": "card",
                    "action": "hold",
                    "source_type": "policy_backed_autonomous_mulligan",
                    "policy_lane": "aggro",
                    "policy_reason": "pirate_pressure",
                }
            ],
            "quality": {
                "status": "policy_backed",
                "has_concrete_keeps": True,
                "default_only": False,
                "policy_backed_rule_count": 1,
                "policy_backed_keep_rule_count": 1,
                "policy_lanes": ["aggro"],
                "policy_reasons": ["pirate_pressure"],
            },
        },
    )

    rows = {row["surface"]: row for row in summary["surface_status_ledger"]}
    assert rows["mulligan"] == {
        "surface": "mulligan",
        "status": "policy_backed",
        "default_only": False,
        "apply_blocking": False,
        "operator_impact": "diagnostic_only",
        "runtime_permission_impact": "none",
        "first_missing_link": "none",
        "next_source_action": "none",
        "next_report_to_open": "reports/operator_summary.json",
    }
```

- [ ] **Step 2: Add failing default-only ledger test**

Append this test near `test_operator_summary_explains_default_only_surfaces_without_blocking_apply`:

```python
def test_operator_summary_surface_status_ledger_marks_default_only_mulligan():
    summary = build_operator_summary(
        deck_name="DefaultOnlyFixture",
        deck_code="fixture",
        technical_validation={"status": "passed"},
        mulligan_plan_report={
            "rules": [],
            "suppressed_rules": [],
            "quality": {
                "status": "thin",
                "has_concrete_keeps": False,
                "first_gap_reason": "no_source_backed_or_policy_backed_mulligan_keeps",
            },
        },
        source_to_runtime_explainability_report={
            "authority": "diagnostic_only",
            "operator_gate_impact": "diagnostic_only",
            "apply_blocking": False,
            "card_rows": [
                {
                    "card_id": "CARD_001",
                    "name": "Fixture Card",
                    "closure": {
                        "lane": "baseline_only_visible",
                        "default_only_risk": True,
                        "first_missing_link": "needs_source_claim",
                        "next_source_action": "add_mulligan_keep_or_discard_claim",
                    },
                }
            ],
        },
    )

    rows = {row["surface"]: row for row in summary["surface_status_ledger"]}
    assert rows["mulligan"] == {
        "surface": "mulligan",
        "status": "default_only",
        "default_only": True,
        "apply_blocking": False,
        "operator_impact": "diagnostic_only",
        "runtime_permission_impact": "none",
        "first_missing_link": "no_source_backed_or_policy_backed_mulligan_keeps",
        "next_source_action": "source_backed_or_policy_backed_mulligan_keeps",
        "next_report_to_open": "reports/operator_summary.json",
    }
    assert summary["runtime_apply_allowed"] is True
```

- [ ] **Step 3: Add failing invalid-package ledger test**

Append this test near `test_operator_summary_no_default_only_verdict_not_applicable_for_invalid_package`:

```python
def test_operator_summary_surface_status_ledger_is_empty_for_invalid_package():
    summary = build_operator_summary(
        deck_name="Invalid Deck",
        deck_code="AAEBAQAAAA==",
        technical_validation={"status": "failed", "errors": ["bad json"]},
        guide_source_depth={"source_depth_status": "static_semantics_only", "claim_count": 0},
        generated_files=[],
    )

    assert summary["surface_status_ledger"] == []
    assert summary["runtime_apply_allowed"] is False
```

- [ ] **Step 4: Run the new tests and confirm failure**

Run:

```powershell
python -m pytest tests/test_operator_summary.py -k "surface_status_ledger" -q
```

Expected result before implementation:

```text
FAILED
KeyError: 'surface_status_ledger'
```

- [ ] **Step 5: Implement `_surface_status_ledger` minimally**

In `src/hsconfig/operator_summary.py`, add `"surface_status_ledger"` directly after `"default_only_runtime_surface_details"` in the returned summary:

```python
        "surface_status_ledger": _surface_status_ledger(
            config_usefulness,
            source_to_runtime_explainability_report or {},
        ),
```

Add this helper below `_default_only_runtime_surface_details`:

```python
def _surface_status_ledger(
    config_usefulness: dict[str, Any],
    source_to_runtime_explainability_report: dict[str, Any],
) -> list[dict[str, Any]]:
    surfaces = (
        config_usefulness.get("surfaces", {})
        if isinstance(config_usefulness, dict)
        else {}
    )
    if not isinstance(surfaces, dict):
        return []

    risky_details = _default_only_risk_card_details(
        source_to_runtime_explainability_report
    )
    first_risky = risky_details[0] if risky_details else {}

    rows: list[dict[str, Any]] = []
    for surface, row in sorted(surfaces.items()):
        if not isinstance(row, dict):
            continue
        status = _surface_ledger_status(row)
        first_missing_link = row.get("first_gap_reason") or first_risky.get(
            "first_missing_link"
        )
        next_source_action = row.get("next_source_need") or first_risky.get(
            "next_source_action"
        )
        if status in {"source_backed", "policy_backed", "static_semantics_backed"}:
            first_missing_link = "none"
            next_source_action = "none"
        rows.append(
            {
                "surface": str(surface),
                "status": status,
                "default_only": bool(row.get("default_only") is True),
                "apply_blocking": False,
                "operator_impact": "diagnostic_only",
                "runtime_permission_impact": "none",
                "first_missing_link": first_missing_link,
                "next_source_action": next_source_action,
                "next_report_to_open": _surface_ledger_next_report(surface, status),
            }
        )
    return rows


def _surface_ledger_status(row: dict[str, Any]) -> str:
    if row.get("default_only") is True:
        return "default_only"
    status = str(row.get("status", "unknown"))
    if status == "policy_backed" or _int_value(row.get("policy_backed_rule_count", 0)):
        return "policy_backed"
    if _int_value(row.get("source_backed_rule_count", 0)):
        return "source_backed"
    if status == "rich":
        return "static_semantics_backed"
    if status == "report_only":
        return "suppressed_with_reason"
    if status == "thin":
        return "warning_only"
    return "warning_only"


def _surface_ledger_next_report(surface: object, status: str) -> str:
    if status in {
        "source_backed",
        "policy_backed",
        "static_semantics_backed",
        "default_only",
    }:
        return "reports/operator_summary.json"
    if surface == "mulligan":
        return "reports/mulligan_plan_report.json"
    if surface == "globalvalues":
        return "reports/global_values_key_profile_report.json"
    if surface == "cardid_behavior":
        return "reports/card_behavior_plan_report.json"
    if surface == "combo":
        return "reports/combo_plan_report.json"
    return "reports/operator_summary.json"
```

- [ ] **Step 6: Run focused tests and confirm pass**

Run:

```powershell
python -m pytest tests/test_operator_summary.py -k "surface_status_ledger or default_only" -q
```

Expected result:

```text
passed
```

- [ ] **Step 7: Commit Task 1**

Run:

```powershell
git add src/hsconfig/operator_summary.py tests/test_operator_summary.py
git commit -m "feat: add operator surface status ledger"
```

---

### Task 2: Keep Representative Deck Proofs No-Default-Only

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_no_default_only_semantic_archetype_matrix.py`
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_shadowpriest_fresh_closure_proof.py`

**Interfaces:**
- Consumes: generated `operator_summary.json`.
- Produces: proof that representative packages have no `surface_status_ledger` row with `status == "default_only"`.

- [ ] **Step 1: Add semantic archetype matrix assertion**

In `tests/test_no_default_only_semantic_archetype_matrix.py`, after the existing assertion:

```python
    assert operator["default_only_runtime_surfaces"] == []
```

add:

```python
    assert all(
        row["status"] != "default_only"
        for row in operator["surface_status_ledger"]
    )
    assert all(
        row["apply_blocking"] is False
        for row in operator["surface_status_ledger"]
    )
```

- [ ] **Step 2: Add ShadowPriest fresh closure assertion**

In `tests/test_shadowpriest_fresh_closure_proof.py`, after the existing assertion:

```python
    assert operator["default_only_runtime_surfaces"] == []
```

add:

```python
    surface_rows = {row["surface"]: row for row in operator["surface_status_ledger"]}
    assert surface_rows["mulligan"]["status"] in {
        "source_backed",
        "policy_backed",
        "static_semantics_backed",
    }
    assert all(
        row["status"] != "default_only"
        for row in operator["surface_status_ledger"]
    )
    assert all(
        row["operator_impact"] == "diagnostic_only"
        for row in operator["surface_status_ledger"]
    )
```

- [ ] **Step 3: Run representative proof tests**

Run:

```powershell
python -m pytest tests/test_no_default_only_semantic_archetype_matrix.py tests/test_shadowpriest_fresh_closure_proof.py -q
```

Expected result:

```text
passed
```

- [ ] **Step 4: Commit Task 2**

Run:

```powershell
git add tests/test_no_default_only_semantic_archetype_matrix.py tests/test_shadowpriest_fresh_closure_proof.py
git commit -m "test: prove surface ledger stays non-default for representative decks"
```

---

### Task 3: Protect the Ledger as Diagnostic-Only Contract Surface

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_contract_spine_sentinel.py`
- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\contract_spine_sentinel.py`

**Interfaces:**
- Consumes: `contract_spine_sentinel.build_contract_spine_sentinel_report() -> dict[str, Any]`.
- Produces: sentinel evidence that the ledger is diagnostic-only and does not become a report gate.

- [ ] **Step 1: Add failing sentinel test**

Append to `tests/test_contract_spine_sentinel.py`:

```python
def test_contract_invariants_note_surface_status_ledger_is_diagnostic_only():
    report = build_contract_spine_sentinel_report()
    invariant = report["contract_invariants"]["diagnostics_are_non_authoritative"]

    assert invariant["status"] == "clean"
    assert invariant["authority"] == "diagnostic_only"
    assert invariant["apply_blocking"] is False
    assert "surface_status_ledger" in invariant["evidence"]
    assert report["checks"]["report_ownership_gate_files"] == [
        "reports/operator_summary.json"
    ]
```

- [ ] **Step 2: Run test and confirm failure**

Run:

```powershell
python -m pytest tests/test_contract_spine_sentinel.py -k "surface_status_ledger" -q
```

Expected result before implementation:

```text
FAILED
AssertionError: assert 'surface_status_ledger' in ...
```

- [ ] **Step 3: Add sentinel evidence string**

In `src/hsconfig/contract_spine_sentinel.py`, update the evidence for `diagnostics_are_non_authoritative` inside `_contract_invariants(...)` so it includes exactly:

```python
"surface_status_ledger"
```

Do not add `surface_status_ledger` to any gate-file list. It lives inside `reports/operator_summary.json` and remains a diagnostic projection.

- [ ] **Step 4: Run sentinel tests**

Run:

```powershell
python -m pytest tests/test_contract_spine_sentinel.py tests/test_contract_spine_sentinel_docs.py -q
```

Expected result:

```text
passed
```

- [ ] **Step 5: Commit Task 3**

Run:

```powershell
git add src/hsconfig/contract_spine_sentinel.py tests/test_contract_spine_sentinel.py
git commit -m "test: guard surface ledger as diagnostic only"
```

---

### Task 4: Update Operator Docs and Installed Skill Guidance

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\docs\operator\README.md`
- Modify: `C:\Users\darbo\Documents\HSConfig\docs\operator\guide-research-policy.md`
- Modify: `C:\Users\darbo\Documents\HSConfig\.agents\skills\hsconfig\SKILL.md`
- Sync through `python scripts/sync_installed_skill.py`: `C:\Users\darbo\.codex\skills\hsconfig\SKILL.md`
- Test: `C:\Users\darbo\Documents\HSConfig\tests\test_skill_sync.py`
- Test: `C:\Users\darbo\Documents\HSConfig\tests\test_skill_files.py`

**Interfaces:**
- Consumes: `surface_status_ledger` field from `operator_summary.json`.
- Produces: docs and installed skill guidance that route normal operators to the ledger without creating another gate.

- [ ] **Step 1: Update operator README**

In `docs/operator/README.md`, in the section that tells the operator to open `reports/operator_summary.json`, add this paragraph:

```markdown
`surface_status_ledger` is the compact per-surface health view. It lists `mulligan`, `globalvalues`, `cardid_behavior`, and `combo` with one status each: `source_backed`, `policy_backed`, `static_semantics_backed`, `warning_only`, `suppressed_with_reason`, or `default_only`. This ledger is diagnostic-only. Runtime apply still depends on `operator_summary.json` technical validity and the guarded apply gate, not source strength. A `default_only` row means visible quality debt, not a hidden success and not an apply blocker by itself.
```

- [ ] **Step 2: Update guide research policy**

In `docs/operator/guide-research-policy.md`, in the no-silent-default-only section, add:

```markdown
The first compact check is `operator_summary.json.surface_status_ledger`. Every listed surface must expose whether it is source-backed, policy-backed, static-semantics-backed, warning-only, suppressed, or default-only. `default_only_runtime_surfaces` remains the compatibility list, but the ledger is the preferred operator view because it shows every surface, including non-default surfaces. Ledger rows are diagnostic-only and must keep `apply_blocking=false`.
```

- [ ] **Step 3: Update source skill compactly**

In `.agents/skills/hsconfig/SKILL.md`, merge `surface_status_ledger` into the existing `operator_summary.json.default_only_runtime_surfaces` instruction instead of adding a separate bullet, so the compactness guard in `tests/test_skill_files.py` remains meaningful:

```markdown
- Open `operator_summary.json.mulligan_policy_status` and `surface_status_ledger` before deeper reports. `default_only_runtime_surfaces` must normally be empty; if not, inspect `default_only_runtime_surface_details` and `source_to_runtime_explainability.json` per-card closure rows first. The ledger is diagnostic-only: `default_only` is visible quality debt, not an apply blocker or replacement for `operator_summary.json` apply authority.
```

- [ ] **Step 4: Sync installed skill**

Run:

```powershell
python scripts/sync_installed_skill.py
```

Expected result:

```text
synced
```

If the script prints a different success line, keep the generated installed skill change and verify with the check command in the next step.

- [ ] **Step 5: Run docs and skill tests**

Run:

```powershell
python -m pytest tests/test_skill_sync.py tests/test_skill_files.py tests/test_docs_active_path.py -q
python scripts/sync_installed_skill.py --check
```

Expected result:

```text
passed
```

and the sync check exits with code 0.

- [ ] **Step 6: Commit Task 4**

Run:

```powershell
git add docs/operator/README.md docs/operator/guide-research-policy.md .agents/skills/hsconfig/SKILL.md docs/superpowers/plans/2026-07-14-surface-status-ledger-no-silent-default-only.md
git commit -m "docs: document surface status ledger"
```

---

### Task 5: Final Guardrail and Full Verification

**Files:**
- No source files modified unless verification reveals a concrete regression from Tasks 1-4.

**Interfaces:**
- Consumes: all changes from prior tasks.
- Produces: verified branch with ledger, no second apply gate, and no silent default-only regression.

- [ ] **Step 1: Run focused ledger tests**

Run:

```powershell
python -m pytest tests/test_operator_summary.py tests/test_config_usefulness.py -q
```

Expected result:

```text
passed
```

- [ ] **Step 2: Run no-default-only and Darkbishop proof tests**

Run:

```powershell
python -m pytest tests/test_no_default_only_semantic_archetype_matrix.py tests/test_shadowpriest_fresh_closure_proof.py tests/test_claim_kind_runtime_contract.py tests/test_shadowpriest_e2e.py -q
```

Expected result:

```text
passed
```

- [ ] **Step 3: Run contract guardrails**

Run:

```powershell
python -m pytest tests/test_contract_spine_sentinel.py tests/test_contract_spine_sentinel_cli.py tests/test_contract_spine_sentinel_docs.py -q
python scripts/check_contract_guardrails.py
```

Expected result:

```text
passed
```

and `check_contract_guardrails.py` exits with code 0.

- [ ] **Step 4: Run full test suite**

Run:

```powershell
python -m pytest
```

Expected result:

```text
passed
```

- [ ] **Step 5: Check diff hygiene**

Run:

```powershell
git diff --check
git status --short --branch
```

Expected result:

```text
git diff --check exits with code 0
```

`git status --short --branch` may show committed branch ahead of its upstream; it must not show unintended untracked runtime artifacts.

- [ ] **Step 6: Commit verification-only fixes if needed**

If any verification step reveals a concrete regression caused by Tasks 1-4, fix only that regression and commit:

```powershell
git add <changed-files>
git commit -m "fix: stabilize surface ledger guardrails"
```

If no regression appears, skip this step.

- [ ] **Step 7: Final review summary**

Record these points in the final response:

```text
- surface_status_ledger added to operator_summary.json
- default_only_runtime_surfaces remains compatibility summary
- ledger rows are diagnostic_only and apply_blocking=false
- operator_summary.json remains the only normal apply authority
- representative no-default-only and ShadowPriest effect-not-mulligan proofs pass
- full pytest result
- branch and git status
```

---

## Self-Review

- Spec coverage: The plan implements the recommendation by adding a compact surface ledger, preserving single apply authority, keeping default-only visible, and avoiding new runtime surfaces.
- Placeholder scan: No placeholder sections, no unspecified test commands, no undefined field names.
- Type consistency: `surface_status_ledger` is consistently a list of dictionaries. Ledger row keys are the same in tests, docs, and implementation.
- Scope check: The plan changes only operator summary projection, focused tests, docs, skill text, and guardrail evidence. It does not alter runtime apply decisions, source acquisition, replay tuning, or HearthRanger runtime surfaces.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-14-surface-status-ledger-no-silent-default-only.md`.

Two execution options:

1. **Subagent-Driven (recommended)** - dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** - execute tasks in this session using executing-plans, batch execution with checkpoints.

Recommended execution mode: **Subagent-Driven**.

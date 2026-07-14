# HSConfig Contract Spine Micro-Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden HSConfig's source/contract/runtime spine so every deck still produces a load-safe package while source quality, report-only mechanics, and card-level missing links stay visible and non-blocking.

**Architecture:** Keep the current narrow pipeline: source claims route through `claim_kind`, policy gates, runtime-surface routers, diagnostics, and operator summary without adding a second apply gate. Add regression tests around report-only runtime-block injection, create a small machine-readable current-truth index, and make source-to-runtime explainability easier to consume at card level. The implementation must not introduce new runtime surfaces, new operator commands, or HSTuner-style post-game tuning.

**Tech Stack:** Python 3, pytest, stdlib `json`/`pathlib`, existing HSConfig modules under `src/hsconfig`, existing docs under `docs/operator` and `docs/research`.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig` for `Teufelsboy/HSConfig`.
- Keep HSConfig narrow: deck input to guide-aligned HearthRanger CustomConfig package only.
- Normal runtime surfaces remain `Mulligan.json`, `GlobalValues.json`, `Combo.json`, and per-card `CARDID.json`.
- Do not reintroduce normal `Concede.json` or `Presume.json` generation.
- Do not block valid deck generation for weak, missing, or report-only source evidence.
- Only technical load-safety failures may prevent apply.
- Source-contract, mechanic, and explainability reports are diagnostic only and must not grant runtime apply authority.
- Darkbishop Benedictus style start-of-game effects may remain runtime behavior rows while being absent from opening-hand mulligan keeps unless an explicit `mulligan_keep` claim exists.
- No new dependencies.
- No raw Hearthstone logs, private runtime evidence, or generated user run evidence in commits.

---

## File Structure

- Modify `tests/test_card_behavior_router.py`: add regression coverage that report-only modern mechanics stay suppressed even when a source claim tries to provide a supported CardID runtime block.
- Create `docs/research/current-truth-index.json`: small machine-readable evidence index mirroring the active current-truth boundary without becoming an operator authority.
- Modify `docs/research/README.md`: point readers to both the Markdown current-truth index and the JSON sibling.
- Create `tests/test_research_current_truth_index.py`: validate the JSON index shape and diagnostic-only authority.
- Modify `src/hsconfig/source_to_runtime_explainability.py`: add compact card-level operator attention rows built from existing explainability rows.
- Modify `tests/test_source_to_runtime_explainability.py`: lock card-level operator attention semantics.
- Modify `scripts/check_contract_guardrails.py`: include the new current-truth and explainability tests in focused contract guardrails.
- Modify `tests/test_check_contract_guardrails.py`: lock the guardrail runner's focused suite membership.

---

### Task 1: Guard Report-Only Mechanics Against Runtime Block Hints

**Files:**
- Modify: `tests/test_card_behavior_router.py`
- Production fallback if needed: `src/hsconfig/card_behavior_surface_router.py`
- Production fallback if needed: `src/hsconfig/mechanic_support.py`

**Interfaces:**
- Consumes: `route_card_behavior_claims(claims: list[dict[str, Any]]) -> dict[str, Any]`
- Produces: a regression test proving report-only mechanics never emit CardID rows solely because a claim supplied `runtime_block`.

- [ ] **Step 1: Add the regression test**

Add this test near `test_warning_only_mechanic_with_explicit_supported_block_stays_suppressed_unless_policy_allows_explicit_override`:

```python
def test_report_only_modern_mechanics_ignore_explicit_runtime_block_hints():
    routed = route_card_behavior_claims(
        [
            {
                "claim_id": f"claim_{mechanic}_explicit",
                "claim_kind": "mechanic_usage",
                "cards": [f"CARD_{mechanic.upper()}"],
                "mechanic": mechanic,
                "runtime_block": "BeforePlayCardBonus",
                "claim_confidence": "high",
            }
            for mechanic in ("imbue", "forge", "excavate")
        ]
    )

    assert routed["card_rows"] == {}
    assert {
        (row["claim_id"], row["mechanic"], row["lowering_policy"], row["reason"])
        for row in routed["suppressed"]
    } == {
        (
            f"claim_{mechanic}_explicit",
            mechanic,
            "report_only",
            f"{mechanic}_has_no_documented_runtime_block",
        )
        for mechanic in ("imbue", "forge", "excavate")
    }
    assert all("runtime_block" not in row for row in routed["suppressed"])
```

- [ ] **Step 2: Run the focused test**

Run:

```powershell
python -m pytest -q tests/test_card_behavior_router.py::test_report_only_modern_mechanics_ignore_explicit_runtime_block_hints
```

Expected acceptable outcomes:

```text
1 passed
```

or:

```text
FAILED tests/test_card_behavior_router.py::test_report_only_modern_mechanics_ignore_explicit_runtime_block_hints
```

If it passes immediately, keep it as characterization coverage and do not change production code in this task. If it fails because CardID rows are emitted or suppressed rows contain `runtime_block`, continue to Step 3.

- [ ] **Step 3: Write the minimal production fix only if Step 2 failed**

In `src/hsconfig/card_behavior_surface_router.py`, keep the existing `policy_name == "report_only"` branch before any explicit block lowering path for `mechanic_usage`. The branch should suppress with only diagnostic fields:

```python
if policy_name == "report_only":
    reason = (
        "requires_supported_cardid_surface"
        if mechanic == "generated_entity_random_pool"
        else str(policy["suppression_reason"])
    )
    suppressed.append(
        {
            **_suppressed_row(
                claim,
                claim_kind,
                cards,
                reason,
            ),
            "mechanic": mechanic,
            "lowering_policy": policy_name,
        }
    )
    continue
```

Do not add `runtime_block` to this suppressed row. Do not move explicit-block lowering ahead of the report-only branch.

- [ ] **Step 4: Run the focused router tests**

Run:

```powershell
python -m pytest -q tests/test_card_behavior_router.py
```

Expected:

```text
passed
```

- [ ] **Step 5: Commit**

Run:

```powershell
git add tests/test_card_behavior_router.py src/hsconfig/card_behavior_surface_router.py src/hsconfig/mechanic_support.py
git commit -m "test: guard report-only mechanics against runtime block hints"
```

If neither production fallback file changed, stage only `tests/test_card_behavior_router.py`.

---

### Task 2: Add Machine-Readable Current-Truth Index

**Files:**
- Create: `docs/research/current-truth-index.json`
- Modify: `docs/research/README.md`
- Test: `tests/test_research_current_truth_index.py`

**Interfaces:**
- Consumes: existing `docs/research/current-truth.md`
- Produces: `docs/research/current-truth-index.json` as evidence-only JSON for tools and tests.

- [ ] **Step 1: Write the failing test**

Create `tests/test_research_current_truth_index.py`:

```python
from __future__ import annotations

import json
from pathlib import Path


def test_current_truth_index_is_machine_readable_and_diagnostic_only():
    data = json.loads(Path("docs/research/current-truth-index.json").read_text(encoding="utf-8"))

    assert data["schema_version"] == 1
    assert data["authority"] == "evidence_index_only"
    assert data["operator_gate_impact"] == "diagnostic_only"
    assert data["normal_operator_path"] == "docs/operator/README.md"
    assert data["normal_apply_authority"] == "reports/operator_summary.json"
    assert data["active_runtime_surfaces"] == [
        "Mulligan.json",
        "GlobalValues.json",
        "Combo.json",
        "CARDID.json",
    ]
    assert data["excluded_normal_surfaces"] == ["Concede.json", "Presume.json"]
    assert data["warning_only_runtime_policy"] == (
        "report_visible_no_runtime_rows_without_documented_surface"
    )
    assert (
        "docs/research/2026-07-14-hsconfig-source-contract-logic-guardrail-audit/"
        in {item["path"] for item in data["active_research_packages"]}
    )


def test_current_truth_index_does_not_claim_apply_authority():
    raw = Path("docs/research/current-truth-index.json").read_text(encoding="utf-8")
    forbidden = {
        "runtime_apply_authorized",
        "apply_gate_authority",
        "operator_summary_replacement",
    }

    assert not any(token in raw for token in forbidden)
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest -q tests/test_research_current_truth_index.py
```

Expected:

```text
FAILED tests/test_research_current_truth_index.py::test_current_truth_index_is_machine_readable_and_diagnostic_only
```

The expected failure is `FileNotFoundError` for `docs/research/current-truth-index.json`.

- [ ] **Step 3: Create the JSON index**

Create `docs/research/current-truth-index.json`:

```json
{
  "schema_version": 1,
  "authority": "evidence_index_only",
  "operator_gate_impact": "diagnostic_only",
  "normal_operator_path": "docs/operator/README.md",
  "normal_apply_authority": "reports/operator_summary.json",
  "active_runtime_surfaces": [
    "Mulligan.json",
    "GlobalValues.json",
    "Combo.json",
    "CARDID.json"
  ],
  "excluded_normal_surfaces": [
    "Concede.json",
    "Presume.json"
  ],
  "warning_only_runtime_policy": "report_visible_no_runtime_rows_without_documented_surface",
  "active_research_packages": [
    {
      "path": "docs/research/2026-07-14-hsconfig-source-contract-logic-guardrail-audit/",
      "role": "current source-contract guardrail evidence",
      "current_implication": "technical load safety decides normal apply; source-contract, source-to-runtime, and mechanic warnings stay diagnostic and non-blocking"
    },
    {
      "path": "docs/research/2026-07-12-hsconfig-source-contract-slim-autonomy-brainstorm/",
      "role": "source-contract spine evidence",
      "current_implication": "claim_kind routes through policy, surface gates, builder/router decisions, and diagnostics before runtime package consideration"
    },
    {
      "path": "docs/research/2026-07-11-hsconfig-source-contract-logic-audit/",
      "role": "source and runtime contract evidence",
      "current_implication": "start-of-game effects must not become mulligan keeps without explicit mulligan claims"
    }
  ]
}
```

- [ ] **Step 4: Update research README**

In `docs/research/README.md`, replace the current truth paragraph with:

```markdown
Current truth index: `docs/research/current-truth.md`.

Machine-readable sibling: `docs/research/current-truth-index.json`.

Use the Markdown file for human research orientation and the JSON file for tests or tools that need the active evidence packages. Both files are evidence-only. They do not replace `docs/operator/README.md` and they do not grant runtime apply permission.
```

Keep the existing historical evidence examples below that section.

- [ ] **Step 5: Run the current-truth tests**

Run:

```powershell
python -m pytest -q tests/test_research_current_truth_index.py
```

Expected:

```text
2 passed
```

- [ ] **Step 6: Commit**

Run:

```powershell
git add docs/research/current-truth-index.json docs/research/README.md tests/test_research_current_truth_index.py
git commit -m "docs: add machine-readable current truth index"
```

---

### Task 3: Add Compact Card-Level Operator Attention Rows

**Files:**
- Modify: `src/hsconfig/source_to_runtime_explainability.py`
- Modify: `tests/test_source_to_runtime_explainability.py`

**Interfaces:**
- Consumes: `build_source_to_runtime_explainability_report(audit: dict) -> dict`
- Produces: top-level `operator_attention` list in the explainability report.

- [ ] **Step 1: Write the failing test**

Add this test to `tests/test_source_to_runtime_explainability.py` after `test_explainability_card_rows_pick_strongest_claim_and_next_action`:

```python
def test_explainability_operator_attention_rows_prioritize_missing_links():
    report = build_source_to_runtime_explainability_report(_fixture_audit())

    assert report["operator_attention"] == [
        {
            "card_id": "CARD_NUM",
            "name": "Numeric Card",
            "status": "source_action_needed",
            "first_missing_link": "runtime_evidence",
            "next_source_action": "collect_runtime_evidence",
            "strongest_claim_id": "numeric_claim",
            "strongest_claim_kind": "globalvalue_numeric_tuning",
            "emitted_runtime_files": [],
            "not_emitted_runtime_files": ["GlobalValues.json"],
        },
        {
            "card_id": "CARD_KEEP",
            "name": "Keep Card",
            "status": "runtime_backed",
            "first_missing_link": None,
            "next_source_action": "none",
            "strongest_claim_id": "keep_claim",
            "strongest_claim_kind": "mulligan_keep",
            "emitted_runtime_files": ["Mulligan.json"],
            "not_emitted_runtime_files": [],
        },
    ]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest -q tests/test_source_to_runtime_explainability.py::test_explainability_operator_attention_rows_prioritize_missing_links
```

Expected:

```text
FAILED tests/test_source_to_runtime_explainability.py::test_explainability_operator_attention_rows_prioritize_missing_links
```

The expected failure is `KeyError: 'operator_attention'`.

- [ ] **Step 3: Add the helper and wire it into the report**

In `src/hsconfig/source_to_runtime_explainability.py`, add this helper after the existing card-row helper functions:

```python
def _operator_attention_rows(card_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for row in card_rows:
        first_missing_link = row.get("first_missing_link")
        rows.append(
            {
                "card_id": row["card_id"],
                "name": row.get("name"),
                "status": "runtime_backed" if first_missing_link is None else "source_action_needed",
                "first_missing_link": first_missing_link,
                "next_source_action": row.get("next_source_action"),
                "strongest_claim_id": row.get("strongest_claim_id"),
                "strongest_claim_kind": row.get("strongest_claim_kind"),
                "emitted_runtime_files": row.get("emitted_runtime_files", []),
                "not_emitted_runtime_files": row.get("not_emitted_runtime_files", []),
            }
        )
    return sorted(
        rows,
        key=lambda row: (
            row["first_missing_link"] is None,
            str(row["card_id"]),
        ),
    )
```

In `build_source_to_runtime_explainability_report`, store the existing card rows in a variable and include `operator_attention`:

```python
card_rows = _card_rows(audit, claim_rows)
return {
    "schema_version": 1,
    "authority": "diagnostic_only",
    "operator_gate_impact": "diagnostic_only",
    "apply_blocking": False,
    "summary": _summary(audit, claim_rows, card_rows),
    "claim_rows": claim_rows,
    "card_rows": card_rows,
    "operator_attention": _operator_attention_rows(card_rows),
}
```

Adapt this exact block to the existing return shape without renaming existing keys.

- [ ] **Step 4: Run explainability tests**

Run:

```powershell
python -m pytest -q tests/test_source_to_runtime_explainability.py
```

Expected:

```text
passed
```

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/hsconfig/source_to_runtime_explainability.py tests/test_source_to_runtime_explainability.py
git commit -m "feat: add source runtime operator attention rows"
```

---

### Task 4: Include New Guardrails in Focused Contract Runner

**Files:**
- Modify: `scripts/check_contract_guardrails.py`
- Modify: `tests/test_check_contract_guardrails.py`

**Interfaces:**
- Consumes: `FOCUSED_CONTRACT_TESTS: tuple[str, ...]`
- Produces: guardrail runner that exercises the new current-truth and explainability contracts.

- [ ] **Step 1: Write the failing test expectation**

In `tests/test_check_contract_guardrails.py`, add these paths to the `expected` set in `test_guardrail_runner_includes_source_contract_v2_boundary_tests`:

```python
"tests/test_source_to_runtime_explainability.py",
"tests/test_research_current_truth_index.py",
```

Also add these assertions in `test_guardrail_commands_include_skill_sync_sentinel_and_boundary_suite`:

```python
assert "tests/test_source_to_runtime_explainability.py" in commands[2].argv
assert "tests/test_research_current_truth_index.py" in commands[2].argv
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest -q tests/test_check_contract_guardrails.py
```

Expected:

```text
FAILED tests/test_check_contract_guardrails.py::test_guardrail_runner_includes_source_contract_v2_boundary_tests
```

- [ ] **Step 3: Add focused tests to the runner**

In `scripts/check_contract_guardrails.py`, add these entries to `FOCUSED_CONTRACT_TESTS`:

```python
"tests/test_source_to_runtime_explainability.py",
"tests/test_research_current_truth_index.py",
```

Place them near `tests/test_source_contract_conformance.py` so source-contract diagnostics stay grouped.

- [ ] **Step 4: Run guardrail runner tests**

Run:

```powershell
python -m pytest -q tests/test_check_contract_guardrails.py
```

Expected:

```text
4 passed
```

- [ ] **Step 5: Commit**

Run:

```powershell
git add scripts/check_contract_guardrails.py tests/test_check_contract_guardrails.py
git commit -m "test: include current truth explainability guardrails"
```

---

### Task 5: Final Verification and Push

**Files:**
- No new files unless previous tasks changed them.

**Interfaces:**
- Consumes: completed Tasks 1-4.
- Produces: verified branch with focused and full test evidence.

- [ ] **Step 1: Run skill sync check**

Run:

```powershell
python scripts\sync_installed_skill.py --check
```

Expected:

```text
installed skill is in sync
```

If the actual script uses a different success message, the command must still exit `0`.

- [ ] **Step 2: Run focused task tests**

Run:

```powershell
python -m pytest -q tests/test_card_behavior_router.py tests/test_source_to_runtime_explainability.py tests/test_research_current_truth_index.py tests/test_check_contract_guardrails.py
```

Expected:

```text
passed
```

- [ ] **Step 3: Run the contract guardrail script**

Run:

```powershell
python scripts\check_contract_guardrails.py
```

Expected:

```text
OK: installed skill sync
OK: contract spine sentinel
OK: focused contract boundary tests
```

- [ ] **Step 4: Run the full test suite**

Run:

```powershell
python -m pytest -q
```

Expected:

```text
passed
```

- [ ] **Step 5: Inspect diff and status**

Run:

```powershell
git diff --check
git status --short --branch
```

Expected:

```text
## codex/hsconfig-contract-spine-guard-wave...origin/codex/hsconfig-contract-spine-guard-wave [ahead 4]
```

The exact ahead count may differ if commits were squashed, but there must be no unstaged source or test changes.

- [ ] **Step 6: Push**

Run:

```powershell
git push origin codex/hsconfig-contract-spine-guard-wave
```

Expected:

```text
To github.com:Teufelsboy/HSConfig.git
```

---

## Implementation Notes

- This plan intentionally does not add a new CLI command.
- This plan intentionally does not alter `hsconfig configure` output semantics except for a potential bugfix if Task 1 exposes one.
- This plan intentionally keeps source and mechanic debt visible but non-blocking.
- `operator_attention` is a report convenience only; it must not be consumed as apply authority.
- If any test reveals that `operator_summary.json` authority is being bypassed, stop after the failing evidence and fix that boundary before continuing.

## Self-Review

- Spec coverage: The plan covers source/contract correctness, report-only mechanic suppression, current research truth, card-level missing-link visibility, and guardrail execution.
- Scope containment: No new runtime surfaces, no new dependencies, no HSTuner/post-game logic, no apply-gate expansion.
- Placeholder scan: The plan contains concrete file paths, test code, commands, expected outputs, and commit messages.
- Type consistency: The plan uses existing `route_card_behavior_claims`, `route_card_behavior_surfaces`, `build_source_to_runtime_explainability_report`, and `FOCUSED_CONTRACT_TESTS` names from the current repository.

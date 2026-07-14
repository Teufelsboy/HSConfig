# HSConfig Source Contract Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden HSConfig so every valid Hearthstone deck still produces a load-safe non-blocking CustomConfig package, while no default-only surface, false Mulligan lowering, or source-to-runtime gap stays silent.

**Architecture:** Keep the existing compact source-contract spine. `source_document_model.py` defines claim kinds and surface gates, `source_contract_matrix.py` defines the policy vocabulary, `source_contract_audit.py` records the lifecycle, `source_to_runtime_explainability.py` projects operator diagnostics, and `operator_summary.json` remains the only normal apply authority.

**Tech Stack:** Python 3.11+, pytest, HSConfig CLI, HearthRanger VisionAI runtime JSON surfaces (`Mulligan.json`, `GlobalValues.json`, `Combo.json`, per-card `CARDID.json`).

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig`.
- Do not add new runtime surfaces to the normal path.
- Normal runtime surfaces remain only `Mulligan.json`, `GlobalValues.json`, `Combo.json`, and per-card `CARDID.json`.
- `Presume.json`, `Concede.json`, and aggregate `CardBehavior.json` remain outside the normal HSConfig path.
- `reports/operator_summary.json` remains the only normal apply authority.
- Source quality, warning-only mechanics, missing guide depth, unresolved option identity, report-only claims, and runtime-evidence-only numeric tuning must not block load-safe apply.
- Invalid JSON, invalid package structure, unsupported normal-path runtime filenames, missing required runtime files, and stale or inconsistent operator summary remain technical hard blockers.
- Keep changes small and local. No broad refactor, no new dependency, no speculative Hearthstone AI engine.

---

## File Structure

- Modify: `src/hsconfig/source_contract_matrix.py`
  - Add one small exported vocabulary helper that projects the existing policy rows into a stable diagnostic contract table.
- Modify: `src/hsconfig/source_to_runtime_explainability.py`
  - Make card attention statuses distinguish runtime-backed, source-action-needed, diagnostic-only, and baseline-only-visible cases.
- Modify: `scripts/check_contract_guardrails.py`
  - Add the new closure test file to the focused guardrail suite.
- Modify: `docs/operator/guide-research-policy.md`
  - State the single-gate rule and no-default-only visibility rule in the operator guide.
- Modify: `.agents/skills/hsconfig/SKILL.md`
  - Mirror the operator wording in the repo-local skill.
- Create: `tests/test_source_contract_closure_wave.py`
  - Centralized regression tests for contract vocabulary, no-default-only visibility, false Mulligan lowering, and any-deck no-block behavior.
- Modify if needed: `tests/test_source_to_runtime_explainability.py`
  - Update expected statuses after the explainability status vocabulary changes.
- Do not modify generated runtime packages or private HearthRanger/HDT/Power.log artifacts.

---

### Task 1: Freeze The Contract Vocabulary As A Single Projection

**Files:**
- Modify: `src/hsconfig/source_contract_matrix.py`
- Create: `tests/test_source_contract_closure_wave.py`

**Interfaces:**
- Consumes: `source_contract_policy_by_claim_kind() -> dict[str, dict[str, object]]`
- Produces: `source_contract_vocabulary_rows() -> tuple[dict[str, object], ...]`

- [ ] **Step 1: Write the failing vocabulary test**

Append this test to the new file `tests/test_source_contract_closure_wave.py`:

```python
from __future__ import annotations

from hsconfig.source_contract_matrix import source_contract_vocabulary_rows
from hsconfig.source_document_model import SUPPORTED_ATOMIC_CLAIM_KINDS


NORMAL_RUNTIME_SURFACES = {"mulligan", "globalvalues", "combo", "cardid"}


def test_contract_vocabulary_covers_every_claim_kind_without_apply_authority():
    rows = source_contract_vocabulary_rows()
    rows_by_kind = {row["claim_kind"]: row for row in rows}

    assert set(rows_by_kind) == set(SUPPORTED_ATOMIC_CLAIM_KINDS)
    assert all(row["operator_gate_impact"] == "diagnostic_only" for row in rows)
    assert all(
        set(row["allowed_surfaces"]).issubset(NORMAL_RUNTIME_SURFACES)
        for row in rows
    )
    assert all("Presume.json" not in row["runtime_files"] for row in rows)
    assert all("Concede.json" not in row["runtime_files"] for row in rows)
    assert all("CardBehavior.json" not in row["runtime_files"] for row in rows)

    assert rows_by_kind["mulligan_keep"]["runtime_files"] == ("Mulligan.json",)
    assert rows_by_kind["hero_power_transform"]["runtime_files"] == ("CARDID.json",)
    assert rows_by_kind["globalvalue_numeric_tuning"]["runtime_files"] == ()
    assert rows_by_kind["globalvalue_numeric_tuning"]["default_suppression_reason"] == (
        "requires_runtime_evidence"
    )
```

- [ ] **Step 2: Run the failing test**

Run:

```powershell
python -m pytest tests/test_source_contract_closure_wave.py::test_contract_vocabulary_covers_every_claim_kind_without_apply_authority -q
```

Expected: FAIL with `ImportError` or `AttributeError` because `source_contract_vocabulary_rows` does not exist yet.

- [ ] **Step 3: Add the minimal vocabulary helper**

Append this code to `src/hsconfig/source_contract_matrix.py`:

```python
_RUNTIME_FILE_BY_SURFACE = {
    "mulligan": "Mulligan.json",
    "globalvalues": "GlobalValues.json",
    "combo": "Combo.json",
    "cardid": "CARDID.json",
}


def source_contract_vocabulary_rows() -> tuple[dict[str, object], ...]:
    """Return a stable diagnostic projection of the source-contract policy."""
    rows: list[dict[str, object]] = []
    for claim_kind, policy in source_contract_policy_by_claim_kind().items():
        allowed_surfaces = tuple(str(surface) for surface in policy["allowed_surfaces"])
        rows.append(
            {
                "claim_kind": claim_kind,
                "semantic_lane": str(policy["semantic_lane"]),
                "allowed_surfaces": allowed_surfaces,
                "runtime_files": tuple(
                    _RUNTIME_FILE_BY_SURFACE[surface]
                    for surface in allowed_surfaces
                    if surface in _RUNTIME_FILE_BY_SURFACE
                ),
                "runtime_lowerable": bool(policy["runtime_lowerable"]),
                "default_suppression_reason": str(policy["default_suppression_reason"]),
                "operator_gate_impact": str(policy["operator_gate_impact"]),
                "semantic_qualifier_usage": str(policy["semantic_qualifier_usage"]),
            }
        )
    return tuple(rows)
```

- [ ] **Step 4: Run the test again**

Run:

```powershell
python -m pytest tests/test_source_contract_closure_wave.py::test_contract_vocabulary_covers_every_claim_kind_without_apply_authority -q
```

Expected: PASS.

- [ ] **Step 5: Commit this task**

Run:

```powershell
git add src/hsconfig/source_contract_matrix.py tests/test_source_contract_closure_wave.py
git commit -m "test: freeze source contract vocabulary"
```

---

### Task 2: Make No-Default-Only Visibility Explicit In Explainability

**Files:**
- Modify: `src/hsconfig/source_to_runtime_explainability.py`
- Modify: `tests/test_source_to_runtime_explainability.py`
- Modify: `tests/test_source_contract_closure_wave.py`

**Interfaces:**
- Consumes: card rows from `build_source_to_runtime_explainability_report(...)`
- Produces: `operator_attention[*]["status"]` values:
  - `source_action_needed`
  - `runtime_backed`
  - `diagnostic_only`
  - `baseline_only_visible`

- [ ] **Step 1: Write the failing no-default-only visibility test**

Append this test to `tests/test_source_contract_closure_wave.py`:

```python
from hsconfig.source_to_runtime_explainability import (
    build_source_to_runtime_explainability_report,
)


def test_report_only_card_is_visible_but_not_treated_as_default_only_success():
    audit = {
        "schema_version": 1,
        "deck_name": "ReportOnlyFixture",
        "claim_rows": {
            "report_claim": {
                "claim_id": "report_claim",
                "claim_kind": "tech_slot",
                "lane": "report_only",
                "policy_lane": "report_only",
                "cards": ["CARD_REPORT"],
            }
        },
        "claim_lifecycle_rows": [
            {
                "claim_id": "report_claim",
                "claim_kind": "tech_slot",
                "policy_lane": "report_only",
                "surface_gate_decision": "rejected",
                "surface_gate_reason": "report_only",
                "builder_or_router_decision": "not_seen_by_builder",
                "runtime_surface": None,
                "emitted_files": [],
                "suppressed_reason": "claim_kind_policy",
                "first_missing_link": "claim_kind_policy",
                "operator_impact": "diagnostic_only",
            }
        ],
        "card_rows": {
            "CARD_REPORT": {
                "name": "Report Card",
                "readiness_lane": "report_only_supported",
                "first_missing_link": "claim_kind_policy",
                "runtime_surfaces": [],
                "claim_lanes": {"report_only": 1},
            }
        },
    }

    report = build_source_to_runtime_explainability_report(audit)
    attention = report["operator_attention"][0]

    assert report["apply_blocking"] is False
    assert attention["status"] == "source_action_needed"
    assert attention["first_missing_link"] == "claim_kind_policy"
    assert attention["next_source_action"] == "map_claim_kind_or_keep_report_only"
```

- [ ] **Step 2: Run the failing test**

Run:

```powershell
python -m pytest tests/test_source_contract_closure_wave.py::test_report_only_card_is_visible_but_not_treated_as_default_only_success -q
```

Expected: FAIL only if current status vocabulary hides this as `no_missing_link` or equivalent.

- [ ] **Step 3: Add a small status helper**

In `src/hsconfig/source_to_runtime_explainability.py`, replace the status assignment inside `_operator_attention_rows` with this helper call:

```python
        status = _operator_attention_status(row)
```

Add this helper below `_operator_attention_rows`:

```python
def _operator_attention_status(row: dict[str, object]) -> str:
    first_missing_link = row.get("first_missing_link")
    emitted_runtime_files = row.get("emitted_runtime_files", [])
    best_source_lane = str(row.get("best_source_lane", ""))
    why_not_emitted = row.get("why_not_emitted")

    if first_missing_link is not None:
        return "source_action_needed"
    if emitted_runtime_files:
        return "runtime_backed"
    if best_source_lane == "report_only" or why_not_emitted in {
        "claim_kind_policy",
        "report_only",
    }:
        return "diagnostic_only"
    return "baseline_only_visible"
```

- [ ] **Step 4: Update existing explainability expectation**

In `tests/test_source_to_runtime_explainability.py`, change the status expectation in `test_explainability_operator_attention_marks_no_missing_link_without_runtime_files` from:

```python
"status": "no_missing_link",
```

to:

```python
"status": "diagnostic_only",
```

- [ ] **Step 5: Run explainability tests**

Run:

```powershell
python -m pytest tests/test_source_to_runtime_explainability.py tests/test_source_contract_closure_wave.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit this task**

Run:

```powershell
git add src/hsconfig/source_to_runtime_explainability.py tests/test_source_to_runtime_explainability.py tests/test_source_contract_closure_wave.py
git commit -m "test: make source runtime visibility explicit"
```

---

### Task 3: Add A False-Mulligan-Lowering Canary

**Files:**
- Modify: `tests/test_source_contract_closure_wave.py`

**Interfaces:**
- Consumes: `prepare_fixture_deck_with_source_claim(...)` from `tests/test_universal_wild_no_block_matrix.py`
- Produces: Regression coverage proving effect-only start-of-game and hero-power-transform claims do not enter `Mulligan.json`.

- [ ] **Step 1: Write the false-lowering test**

Append this import and test to `tests/test_source_contract_closure_wave.py`:

```python
import json

from tests.test_universal_wild_no_block_matrix import (
    prepare_fixture_deck_with_source_claim,
)


def test_start_of_game_hero_power_transform_preserves_effect_without_mulligan_keep(tmp_path):
    result = prepare_fixture_deck_with_source_claim(
        tmp_path,
        deck_name="StartOfGameEffectCanary",
        claim={
            "claim_id": "effect_only",
            "claim_kind": "hero_power_transform",
            "cards": ["CARD_001"],
            "evidence_text_short": "Keep the deck all shadow so the hero power transforms.",
            "source_confidence": "guide_backed",
            "semantic_qualifiers": {
                "timing": ["start_of_game"],
                "state_requirements": ["hero_power_transform"],
            },
        },
    )

    deck_dir = next((result["package"] / "CustomConfig").iterdir())
    mulligan = json.loads((deck_dir / "Mulligan.json").read_text(encoding="utf-8"))
    card_behavior = json.loads((deck_dir / "CARD_001.json").read_text(encoding="utf-8"))

    assert result["exit_code"] == 0
    assert result["operator_summary"]["runtime_apply_allowed"] is True
    assert not any(
        row.get("mulligan") == "CARD_001"
        for row in mulligan["Mulligan"]["values"]
    )
    assert card_behavior["BeforeUseHeroPowerBonus"]["values"]
```

- [ ] **Step 2: Run the false-lowering test**

Run:

```powershell
python -m pytest tests/test_source_contract_closure_wave.py::test_start_of_game_hero_power_transform_preserves_effect_without_mulligan_keep -q
```

Expected: PASS if the current Darkbishop-style guardrail is still intact. If it fails, fix `can_lower_to_mulligan(...)` in `src/hsconfig/source_document_model.py` by preserving the existing `start_of_game_effect_does_not_require_opening_hand` suppression behavior.

- [ ] **Step 3: Commit this task**

Run:

```powershell
git add tests/test_source_contract_closure_wave.py src/hsconfig/source_document_model.py
git commit -m "test: guard effect-only claims from mulligan lowering"
```

---

### Task 4: Prove Any-Deck No-Block Still Works With Closure Diagnostics

**Files:**
- Modify: `tests/test_source_contract_closure_wave.py`

**Interfaces:**
- Consumes: `DECKS` matrix and `main(...)` CLI prepare path from existing tests.
- Produces: A focused canary that checks load-safe apply, no legacy runtime files, and source-to-runtime diagnostics together.

- [ ] **Step 1: Add the matrix smoke test**

Append this test to `tests/test_source_contract_closure_wave.py`:

```python
from pathlib import Path

from hsconfig.cli import main
from tests.test_universal_wild_no_block_matrix import DECKS


def test_any_deck_matrix_has_load_safe_apply_and_no_legacy_runtime_surfaces(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        "hsconfig.package_builder.fetch_latest_cards",
        lambda timeout=10.0: [],
    )

    for deck_name, deck_code in DECKS:
        out = tmp_path / deck_name
        assert main(
            [
                "prepare",
                "--deck-name",
                deck_name,
                "--deck-code",
                deck_code,
                "--runtime-root",
                str(tmp_path / "runtime"),
                "--out",
                str(out),
                "--json",
            ]
        ) == 0

        reports = out / "reports"
        operator = json.loads(
            (reports / "operator_summary.json").read_text(encoding="utf-8")
        )
        explainability = json.loads(
            (reports / "source_to_runtime_explainability.json").read_text(
                encoding="utf-8"
            )
        )
        deck_dir = next((out / "CustomConfig").iterdir())

        assert operator["technical_status"] == "VALID_PACKAGE"
        assert operator["runtime_apply_allowed"] is True
        assert operator["runtime_apply_contract"]["apply_authority"] == (
            "reports/operator_summary.json"
        )
        assert explainability["apply_blocking"] is False
        assert explainability["operator_gate_impact"] == "diagnostic_only"
        assert explainability["operator_attention"]
        assert not (deck_dir / "Presume.json").exists()
        assert not (deck_dir / "Concede.json").exists()
        assert not (deck_dir / "CardBehavior.json").exists()
```

- [ ] **Step 2: Run the matrix smoke test**

Run:

```powershell
python -m pytest tests/test_source_contract_closure_wave.py::test_any_deck_matrix_has_load_safe_apply_and_no_legacy_runtime_surfaces -q
```

Expected: PASS.

- [ ] **Step 3: Commit this task**

Run:

```powershell
git add tests/test_source_contract_closure_wave.py
git commit -m "test: prove any deck source contract closure"
```

---

### Task 5: Lock The Operator And Skill Wording To One Gate

**Files:**
- Modify: `docs/operator/guide-research-policy.md`
- Modify: `.agents/skills/hsconfig/SKILL.md`
- Create or Modify: `tests/test_operator_docs_contract_policy.py`

**Interfaces:**
- Consumes: active operator docs and repo-local skill.
- Produces: Text contract that diagnostics never become apply gates.

- [ ] **Step 1: Add failing docs assertions**

Add these assertions to `tests/test_operator_docs_contract_policy.py` or create the file if it does not exist:

```python
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_operator_docs_keep_single_apply_authority_and_no_default_only_visibility():
    guide = _read("docs/operator/guide-research-policy.md")
    skill = _read(".agents/skills/hsconfig/SKILL.md")
    combined = f"{guide}\n{skill}"

    assert "reports/operator_summary.json remains the only normal apply authority" in combined
    assert "diagnostic reports must not become apply gates" in combined
    assert "default-only runtime surfaces must be visible, not silent" in combined
    assert "Presume.json" in combined
    assert "Concede.json" in combined
    assert "outside the normal HSConfig path" in combined
```

- [ ] **Step 2: Run the docs test**

Run:

```powershell
python -m pytest tests/test_operator_docs_contract_policy.py::test_operator_docs_keep_single_apply_authority_and_no_default_only_visibility -q
```

Expected: FAIL until docs contain the exact wording.

- [ ] **Step 3: Patch the operator guide**

Add this compact paragraph to `docs/operator/guide-research-policy.md` near the source-contract or apply-policy section:

```markdown
## Single Apply Authority

`reports/operator_summary.json` remains the only normal apply authority. Diagnostic reports must not become apply gates: `source_contract_audit.json`, `source_to_runtime_explainability.json`, mechanic visibility reports, source quality reports, and claim lifecycle projections explain what happened but do not allow or block runtime writes. Default-only runtime surfaces must be visible, not silent: a valid load-safe package may proceed with warnings, but the reports must show whether a card is runtime-backed, source-action-needed, diagnostic-only, or baseline-only-visible.

`Presume.json`, `Concede.json`, and aggregate `CardBehavior.json` stay outside the normal HSConfig path. The normal runtime path remains `Mulligan.json`, `GlobalValues.json`, `Combo.json`, and per-card `CARDID.json`.
```

- [ ] **Step 4: Patch the repo-local skill**

Add the same policy summary, shortened if needed, to `.agents/skills/hsconfig/SKILL.md` in the operator boundaries section:

```markdown
- `reports/operator_summary.json` remains the only normal apply authority.
- Diagnostic reports must not become apply gates.
- Default-only runtime surfaces must be visible, not silent.
- `Presume.json`, `Concede.json`, and aggregate `CardBehavior.json` stay outside the normal HSConfig path.
```

- [ ] **Step 5: Run docs tests**

Run:

```powershell
python -m pytest tests/test_operator_docs_contract_policy.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit this task**

Run:

```powershell
git add docs/operator/guide-research-policy.md .agents/skills/hsconfig/SKILL.md tests/test_operator_docs_contract_policy.py
git commit -m "docs: lock source contract apply authority"
```

---

### Task 6: Add The Closure Wave To Focused Guardrails

**Files:**
- Modify: `scripts/check_contract_guardrails.py`

**Interfaces:**
- Consumes: `FOCUSED_CONTRACT_TESTS`
- Produces: `tests/test_source_contract_closure_wave.py` included in `python scripts/check_contract_guardrails.py`

- [ ] **Step 1: Add the failing guardrail expectation**

Run:

```powershell
python - <<'PY'
from scripts.check_contract_guardrails import FOCUSED_CONTRACT_TESTS
assert "tests/test_source_contract_closure_wave.py" in FOCUSED_CONTRACT_TESTS
PY
```

Expected: FAIL until the file is added.

If PowerShell rejects heredoc syntax, run:

```powershell
python -c "from scripts.check_contract_guardrails import FOCUSED_CONTRACT_TESTS; assert 'tests/test_source_contract_closure_wave.py' in FOCUSED_CONTRACT_TESTS"
```

- [ ] **Step 2: Add the closure test file to the guardrail tuple**

In `scripts/check_contract_guardrails.py`, add this entry to `FOCUSED_CONTRACT_TESTS`:

```python
    "tests/test_source_contract_closure_wave.py",
```

Place it next to the other source-contract tests.

- [ ] **Step 3: Run focused guardrails**

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

- [ ] **Step 4: Commit this task**

Run:

```powershell
git add scripts/check_contract_guardrails.py
git commit -m "test: include closure wave in guardrails"
```

---

### Task 7: Final Verification And Push Readiness

**Files:**
- No new files unless tests reveal a narrow fix.

**Interfaces:**
- Consumes: all tasks above.
- Produces: verified local branch ready for push.

- [ ] **Step 1: Run targeted tests**

Run:

```powershell
python -m pytest tests/test_source_contract_closure_wave.py tests/test_source_to_runtime_explainability.py tests/test_operator_docs_contract_policy.py -q
```

Expected: PASS.

- [ ] **Step 2: Run focused contract guardrails**

Run:

```powershell
python scripts\check_contract_guardrails.py
```

Expected: all three guardrail checks print `OK`.

- [ ] **Step 3: Run full tests**

Run:

```powershell
python -m pytest -q
```

Expected: PASS. Current known baseline before this plan was `1179 passed, 2 skipped`; the exact number may increase after adding tests.

- [ ] **Step 4: Check diff and status**

Run:

```powershell
git diff --stat
git status --short --branch
```

Expected: only the files listed in this plan changed.

- [ ] **Step 5: Final commit if any task commits were intentionally squashed**

If prior task commits were not made, create one final commit:

```powershell
git add src/hsconfig/source_contract_matrix.py src/hsconfig/source_to_runtime_explainability.py scripts/check_contract_guardrails.py docs/operator/guide-research-policy.md .agents/skills/hsconfig/SKILL.md tests/test_source_contract_closure_wave.py tests/test_source_to_runtime_explainability.py tests/test_operator_docs_contract_policy.py
git commit -m "test: close hsconfig source contract guardrails"
```

- [ ] **Step 6: Push**

Run:

```powershell
git push origin main
```

Expected: push succeeds and `main` remains up to date with `origin/main`.

---

## Self-Review

- Spec coverage: The plan covers the recommended source-contract micro-hardening, no-default-only visibility, false Mulligan lowering protection, any-deck no-block behavior, single operator apply authority, and focused guardrail inclusion.
- Placeholder scan: No `TBD`, `TODO`, vague error handling, or unspecified test commands remain.
- Type consistency: `source_contract_vocabulary_rows()` returns `tuple[dict[str, object], ...]`; tests consume that exact function name. Explainability statuses are explicit string values and all expected values are defined in Task 2.
- Scope control: No new runtime surfaces, no new dependencies, no broad refactor, no private runtime evidence.

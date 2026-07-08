# HSConfig Kingslayer Quick Pick Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the current Kingslayer `DEEP_014` / `Quick Pick` source-informed gap honestly by either proving exact source-backed mulligan evidence or preserving Kingslayer with an explicit stop condition when exact evidence remains unavailable.

**Architecture:** Keep HSConfig a lean pre-run HearthRanger VisionAI CustomConfig generator. This wave changes only source-depth truth, matrix visibility, operator docs, and focused regression tests; it must not add replay analysis, post-run tuning, winrate logic, candidate promotion, or new runtime surfaces. Based on the latest validated research audit, the expected path is preservation, not promotion, unless a new exact deck-specific Quick Pick keep/discard source is found during Task 1.

**Tech Stack:** Python 3, pytest, strict JSON fixtures, existing HSConfig CLI/report modules, Markdown operator docs.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig` for `Teufelsboy/HSConfig`.
- Preserve HSConfig's narrow pre-run scope: no replay parsing, HDT parsing, Power.log parsing, winrate validation, candidate promotion, or HSTuner logic.
- Do not widen the representative matrix beyond the existing 11 rows.
- `CuteWarrior` remains supplemental and must not become a twelfth representative row.
- Preserve exact deck and CardID identity.
- Preserve full `GlobalValues.json` key profiling.
- Preserve every-card coverage in the gameplan contract.
- Preserve strict JSON validation.
- Preserve row-level provenance for generated config rows.
- Do not promote Kingslayer to `core_source_backed_fixture` unless all six source-backed strong checks pass.
- Do not treat adjacent weapon rogue, generic card-draw advice, or non-Kingslayer Quick Pick advice as source-backed strong evidence for this Kingslayer row.

---

## File Structure

- Modify `docs/operator/archetype-fixture-matrix.json`
  - Responsibility: source of truth for the 11 representative deck rows, fixture stages, strongness visibility, stop conditions, and coverage limits.
- Modify `src/hsconfig/source_depth_closure_index.py`
  - Responsibility: summarize closure order, preserved source-informed targets, and next actionable closure target.
  - Expected change: sort preserved targets by closure priority, not matrix order, so `["Boarlock", "Kingslayer"]` is stable when both rows are preserved.
- Modify `tests/test_boarlock_closure_wave.py`
  - Responsibility: preserve current Boarlock truth while updating the expected post-Kingslayer actionable target state.
- Modify `tests/test_archetype_fixture_matrix.py`
  - Responsibility: enforce Kingslayer's explicit stop condition and keep representative matrix count unchanged.
- Create `tests/test_kingslayer_quick_pick_source_decision.py`
  - Responsibility: lock the Kingslayer Quick Pick decision doc and matrix stop condition.
- Create `docs/operator/kingslayer-quick-pick-source-decision.md`
  - Responsibility: operator-facing explanation of why Kingslayer is preserved instead of promoted until exact Quick Pick mulligan evidence exists.
- Modify `docs/operator/source-backed-strong-closure.md`
  - Responsibility: update current closure target tables, blocker snapshot, and next actionable target text.
- Modify `docs/operator/README.md`
  - Responsibility: keep the normal operator path aligned with the updated closure truth.
- Optional modify `docs/operator/boarlock-fracking-source-decision.md`
  - Responsibility: remove stale wording that says Kingslayer is still the next actionable target after Kingslayer has been preserved.

---

### Task 1: Reconfirm Kingslayer Evidence Boundary

**Files:**
- Read: `docs/research/2026-07-09-hsconfig-post-boarlock-truth-skill-audit/results/Deck_Matrix_Truth_And_Every_Card_Lane.json`
- Read: `docs/operator/source-backed-strong-closure.md`
- Read: `tests/fixtures/source_documents_kingslayer_strong.json`
- Modify only if new exact evidence is found: `tests/fixtures/source_documents_kingslayer_strong.json`

**Interfaces:**
- Consumes: current matrix row for `Kingslayer`, card ID `DEEP_014`, card name `Quick Pick`.
- Produces: a concrete implementation path:
  - `preserve_kingslayer_source_informed` when exact deck-specific Quick Pick mulligan evidence is still unavailable.
  - `promote_kingslayer_source_backed_strong` only when exact keep/discard evidence is source-backed and all six strong checks pass.

- [ ] **Step 1: Inspect current evidence statements**

Run:

```powershell
Get-Content -Raw docs\operator\source-backed-strong-closure.md
Get-Content -Raw tests\fixtures\source_documents_kingslayer_strong.json
Get-Content -Raw docs\research\2026-07-09-hsconfig-post-boarlock-truth-skill-audit\results\Deck_Matrix_Truth_And_Every_Card_Lane.json
```

Expected: the files state that Kingslayer is blocked by `DEEP_014` / `Quick Pick` needing an explicit mulligan keep/discard claim.

- [ ] **Step 2: Apply the decision rule**

Use this exact rule:

```text
If a source explicitly says whether DEEP_014 / Quick Pick is kept or discarded in the mulligan for the provided Kingslayer deck or a directly matching Kingslayer/Kingsbane weapon rogue list that includes Quick Pick, then continue with promotion validation.

Otherwise, implement the preservation path with:
operator_action=preserve_source_informed_with_explicit_stop_condition
stop_condition=exact_kingslayer_quick_pick_mulligan_source_unavailable
```

Expected for this plan: preservation path. The latest audit already found that the exact provided deck page lists Quick Pick but does not expose a card-level mulligan instruction, and that adjacent Quick Pick advice is not strong evidence for this row.

- [ ] **Step 3: Do not update source fixture unless exact evidence exists**

If exact evidence is still unavailable, do not edit `tests/fixtures/source_documents_kingslayer_strong.json` in this task.

Expected: no fixture claim is added for `DEEP_014` merely to satisfy the gap.

- [ ] **Step 4: Commit boundary decision only after Task 2 docs/tests exist**

Do not commit after Task 1 alone. The evidence decision needs the test/doc lock from Task 2.

---

### Task 2: Add Kingslayer Decision Tests And Doc

**Files:**
- Create: `tests/test_kingslayer_quick_pick_source_decision.py`
- Create: `docs/operator/kingslayer-quick-pick-source-decision.md`

**Interfaces:**
- Consumes: `docs/operator/archetype-fixture-matrix.json` row for `Kingslayer`.
- Produces: regression tests that require a durable Kingslayer stop condition before this wave can pass.

- [ ] **Step 1: Write failing doc/matrix test**

Create `tests/test_kingslayer_quick_pick_source_decision.py` with:

```python
import json
from pathlib import Path


MATRIX_PATH = Path("docs/operator/archetype-fixture-matrix.json")
DOC_PATH = Path("docs/operator/kingslayer-quick-pick-source-decision.md")


def _kingslayer_row() -> dict:
    matrix = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    return next(row for row in matrix["decks"] if row["deck_name"] == "Kingslayer")


def test_kingslayer_quick_pick_decision_doc_records_stop_condition():
    text = DOC_PATH.read_text(encoding="utf-8")

    assert "# Kingslayer Quick Pick Source Decision" in text
    assert "`DEEP_014` / `Quick Pick`" in text
    assert "Do not promote Kingslayer to `core_source_backed_fixture`" in text
    assert "exact_kingslayer_quick_pick_mulligan_source_unavailable" in text
    assert "Adjacent archetype advice is not source-backed evidence" in text


def test_kingslayer_matrix_row_preserves_source_informed_until_exact_source_exists():
    row = _kingslayer_row()
    visibility = row["strongness_visibility"]

    assert row["fixture_stage"] == "source_informed_valid_fixture"
    assert visibility["first_strongness_gap"] == "needs_mulligan_claim_for_quick_pick"
    assert visibility["operator_action"] == (
        "preserve_source_informed_with_explicit_stop_condition"
    )
    assert visibility["stop_condition"] == (
        "exact_kingslayer_quick_pick_mulligan_source_unavailable"
    )
    assert visibility["source_informed_blocking_reasons"] == [
        "unsupported_conditions_present"
    ]
```

- [ ] **Step 2: Run the new test and verify it fails**

Run:

```powershell
python -m pytest tests\test_kingslayer_quick_pick_source_decision.py -q
```

Expected: FAIL because `docs/operator/kingslayer-quick-pick-source-decision.md` does not exist yet and/or the matrix row still uses `close_existing_source_informed_fixture`.

- [ ] **Step 3: Create the Kingslayer decision doc**

Create `docs/operator/kingslayer-quick-pick-source-decision.md` with:

```markdown
# Kingslayer Quick Pick Source Decision

This page records the current HSConfig decision for `Kingslayer` and `DEEP_014` / `Quick Pick`.

## Decision

Keep `Kingslayer` as `source_informed_valid_fixture`.

Do not promote Kingslayer to `core_source_backed_fixture` unless an exact source explicitly says whether `DEEP_014` / `Quick Pick` should be kept or discarded in the mulligan for the provided Kingslayer deck, or for a directly matching Kingslayer/Kingsbane weapon rogue list that includes `DEEP_014` / `Quick Pick`.

## Stop Condition

`exact_kingslayer_quick_pick_mulligan_source_unavailable`

## Why

The current Kingslayer fixture can produce a valid source-informed package, but `DEEP_014` / `Quick Pick` is still the first missing source-depth chain.

The checked Kingslayer deck context publicly lists `Quick Pick`, but does not expose an explicit card-level mulligan keep/discard instruction. Adjacent archetype advice is not source-backed evidence for this representative row unless it is directly about a matching Kingslayer/Kingsbane weapon rogue list that includes `Quick Pick`.

## Source-Backed Strong Promotion Rule

Kingslayer can move to `core_source_backed_fixture` only when a fixture prepare run proves all six checks:

- `technical_status=VALID_PACKAGE`
- `semantic_status=SOURCE_BACKED_STRONG`
- `next_action=READY_TO_APPLY_OR_HANDOFF`
- zero semantic blockers
- zero blocked cards in `source_claim_gap_report.json`
- no generated `Presume.json` or `Concede.json`

## Current Operator Action

Preserve this row as a visible source-informed control until exact Quick Pick mulligan evidence exists.

Do not widen the matrix to a twelfth representative deck to avoid this row.
```

- [ ] **Step 4: Run the new test again**

Run:

```powershell
python -m pytest tests\test_kingslayer_quick_pick_source_decision.py -q
```

Expected: still FAIL until Task 3 updates the matrix row.

---

### Task 3: Preserve Kingslayer In Matrix And Closure Index

**Files:**
- Modify: `docs/operator/archetype-fixture-matrix.json`
- Modify: `src/hsconfig/source_depth_closure_index.py`
- Modify: `tests/test_boarlock_closure_wave.py`
- Modify: `tests/test_archetype_fixture_matrix.py`

**Interfaces:**
- Consumes: Kingslayer stop condition from Task 2.
- Produces:
  - `strongness_visibility.operator_action="preserve_source_informed_with_explicit_stop_condition"` for Kingslayer.
  - `strongness_visibility.stop_condition="exact_kingslayer_quick_pick_mulligan_source_unavailable"` for Kingslayer.
  - closure index summary with both source-informed rows preserved.

- [ ] **Step 1: Update the Kingslayer matrix row**

In `docs/operator/archetype-fixture-matrix.json`, update only the `Kingslayer` row's `strongness_visibility` block:

```json
"strongness_visibility": {
  "current_stage": "source_informed_valid_fixture",
  "first_strongness_gap": "needs_mulligan_claim_for_quick_pick",
  "source_informed_apply_readiness": "blocked",
  "source_informed_blocking_reasons": ["unsupported_conditions_present"],
  "closure_state": "source_informed_blocked",
  "closure_priority": 2,
  "operator_action": "preserve_source_informed_with_explicit_stop_condition",
  "stop_condition": "exact_kingslayer_quick_pick_mulligan_source_unavailable"
}
```

Do not change `deck_code`, `hs_id`, `hdt_deck_id`, `expected_runtime_surfaces`, `decision_families_proven`, or `known_coverage_limits`.

- [ ] **Step 2: Sort preserved targets by closure priority**

Modify `_preserved_source_informed_targets()` in `src/hsconfig/source_depth_closure_index.py` so preserved rows are sorted by `_closure_priority(row)` and then `deck_name`.

Use this implementation:

```python
def _preserved_source_informed_targets(rows: list[dict[str, Any]]) -> list[str]:
    preserved = [
        row
        for row in rows
        if isinstance(row, dict)
        and row.get("fixture_stage") == "source_informed_valid_fixture"
        and _has_durable_preservation_stop(row)
    ]
    preserved.sort(key=lambda row: (_closure_priority(row), str(row.get("deck_name", ""))))
    return [str(row["deck_name"]) for row in preserved if row.get("deck_name")]
```

- [ ] **Step 3: Update the matrix strongness visibility test**

In `tests/test_archetype_fixture_matrix.py`, change the source-informed branch so Kingslayer and Boarlock both require explicit preservation:

```python
        elif deck_name == "Boarlock":
            assert visibility["operator_action"] == (
                "preserve_source_informed_with_explicit_stop_condition"
            )
            assert visibility["stop_condition"] == (
                "exact_boarlock_fracking_mulligan_source_unavailable"
            )
        elif deck_name == "Kingslayer":
            assert visibility["operator_action"] == (
                "preserve_source_informed_with_explicit_stop_condition"
            )
            assert visibility["stop_condition"] == (
                "exact_kingslayer_quick_pick_mulligan_source_unavailable"
            )
        else:
            assert visibility["operator_action"] == "close_existing_source_informed_fixture"
            assert visibility.get("stop_condition") is None
```

- [ ] **Step 4: Update closure-index expectations**

In `tests/test_boarlock_closure_wave.py`, update `test_boarlock_source_informed_row_exposes_explicit_stop_condition()` so the synthetic Kingslayer row also has the explicit stop condition:

```python
                    "operator_action": "preserve_source_informed_with_explicit_stop_condition",
                    "stop_condition": "exact_kingslayer_quick_pick_mulligan_source_unavailable",
```

Then change the assertions:

```python
    assert report["summary"]["preserved_source_informed_targets"] == [
        "Boarlock",
        "Kingslayer",
    ]
    assert report["summary"]["next_actionable_closure_target"] is None
```

And change the Kingslayer expectation:

```python
    kingslayer = report["decks"]["Kingslayer"]
    assert kingslayer["closure_decision"] == "preserve_source_informed_until_blockers_close"
    assert kingslayer["stop_condition"] == (
        "exact_kingslayer_quick_pick_mulligan_source_unavailable"
    )
    assert kingslayer["recommended_next_target"] is None
```

- [ ] **Step 5: Run focused tests**

Run:

```powershell
python -m pytest tests\test_kingslayer_quick_pick_source_decision.py tests\test_boarlock_closure_wave.py tests\test_archetype_fixture_matrix.py tests\test_source_depth_closure_index.py -q
```

Expected: PASS.

---

### Task 4: Update Operator Docs And Active Path Wording

**Files:**
- Modify: `docs/operator/source-backed-strong-closure.md`
- Modify: `docs/operator/README.md`
- Modify: `docs/operator/boarlock-fracking-source-decision.md`

**Interfaces:**
- Consumes: preserved Kingslayer stop condition from Task 3.
- Produces: operator docs that no longer claim Kingslayer is currently actionable after the wave.

- [ ] **Step 1: Update `source-backed-strong-closure.md` Kingslayer row**

Replace the Kingslayer row's required-work text with:

```markdown
| Kingslayer | `source_informed_valid_fixture` | Preserved blocked with explicit stop condition: exact Kingslayer Quick Pick mulligan evidence remains unavailable. Preserve this row as the weapon-sequence source-informed control until an exact Kingslayer/Kingsbane Quick Pick keep-or-discard source exists. |
```

- [ ] **Step 2: Update current closure bullet list**

Replace the current Kingslayer bullet with:

```markdown
- `Kingslayer` remains source-informed with explicit stop condition `exact_kingslayer_quick_pick_mulligan_source_unavailable` unless an exact Kingslayer/Kingsbane `DEEP_014` / `Quick Pick` mulligan source is added.
```

Replace the next-actionable text with:

```markdown
After durable Boarlock and Kingslayer preservation, there is no current actionable source-informed closure target. The next closure target appears only when new exact source evidence is added for either preserved row or a future matrix row exposes a new first missing chain.
```

- [ ] **Step 3: Update current source-informed closure decisions table**

Change the Kingslayer row to:

```markdown
| Kingslayer | Preserve as source-informed until exact source exists | `DEEP_014` / Quick Pick needs explicit mulligan claim | `unsupported_conditions_present`; stop condition `exact_kingslayer_quick_pick_mulligan_source_unavailable` |
```

- [ ] **Step 4: Update operator README**

In `docs/operator/README.md`, replace stale wording that says Kingslayer is the next actionable closure target with:

```markdown
Boarlock and Kingslayer are both durable source-informed controls with explicit stop conditions. Do not widen the representative matrix to a twelfth deck to avoid these rows. Add or promote only when exact source evidence closes a preserved stop condition.
```

- [ ] **Step 5: Update Boarlock decision doc**

In `docs/operator/boarlock-fracking-source-decision.md`, replace:

```markdown
Next actionable closure target: `Kingslayer`
```

with:

```markdown
Kingslayer is the next closure row in priority order, but it is also preserved until exact Quick Pick mulligan evidence exists.
```

- [ ] **Step 6: Run docs tests**

Run:

```powershell
python -m pytest tests\test_docs_active_path.py tests\test_skill_files.py tests\test_kingslayer_quick_pick_source_decision.py -q
```

Expected: PASS.

---

### Task 5: Verify Prepare Reports Still Preserve Runtime Boundaries

**Files:**
- Test only: `tests/test_archetype_fixture_e2e.py`
- Test only: `tests/test_source_informed_closure_contract.py`
- Test only: `tests/test_strong_promotion_report.py`
- Test only: `tests/test_matrix_current_truth.py`

**Interfaces:**
- Consumes: updated matrix/doc truth from Tasks 2-4.
- Produces: confidence that no runtime surface or post-run scope was widened.

- [ ] **Step 1: Run source-informed closure tests**

Run:

```powershell
python -m pytest tests\test_source_informed_closure_contract.py tests\test_matrix_current_truth.py tests\test_strong_promotion_report.py -q
```

Expected: PASS. Expected semantic truth:

```text
Kingslayer remains source_informed_valid_fixture unless all strong checks pass.
Boarlock remains source_informed_valid_fixture.
Representative matrix count remains 11.
CuteWarrior remains supplemental.
```

- [ ] **Step 2: Run fixture prepare smoke tests**

Run:

```powershell
python -m pytest tests\test_archetype_fixture_e2e.py tests\test_depth_matrix_e2e.py -q
```

Expected: PASS.

- [ ] **Step 3: Confirm no banned scope was introduced**

Run:

```powershell
rg -n "Power\\.log|HDT|hsreplay|winrate|candidate promotion|post-run|post run|replay parsing" src tests docs\operator docs\skills README.md
```

Expected: either no matches, or only existing boundary text that says HSConfig does not do those things. No new implementation files should mention these as active behavior.

---

### Task 6: Final Verification And Git Handoff

**Files:**
- All modified files from Tasks 2-4.

**Interfaces:**
- Consumes: complete Kingslayer preservation implementation.
- Produces: a tested branch ready for commit/push.

- [ ] **Step 1: Run full test suite**

Run:

```powershell
python -m pytest -q
```

Expected: all tests pass. Current baseline before this plan was `585 passed, 2 skipped`; an increased pass count is expected if new tests are added.

- [ ] **Step 2: Check installed skill sync**

Run:

```powershell
python scripts\sync_installed_skill.py --check
```

Expected:

```text
HSConfig skill is in sync: C:\Users\darbo\.codex\skills\hsconfig
```

- [ ] **Step 3: Inspect diff**

Run:

```powershell
git diff -- docs\operator\archetype-fixture-matrix.json src\hsconfig\source_depth_closure_index.py tests\test_boarlock_closure_wave.py tests\test_archetype_fixture_matrix.py tests\test_kingslayer_quick_pick_source_decision.py docs\operator\kingslayer-quick-pick-source-decision.md docs\operator\source-backed-strong-closure.md docs\operator\README.md docs\operator\boarlock-fracking-source-decision.md
git status --short --branch
```

Expected: only planned files changed, plus this plan file if it has not already been committed.

- [ ] **Step 4: Commit**

Run:

```powershell
git add docs\superpowers\plans\2026-07-09-hsconfig-kingslayer-quick-pick-closure.md docs\operator\archetype-fixture-matrix.json src\hsconfig\source_depth_closure_index.py tests\test_boarlock_closure_wave.py tests\test_archetype_fixture_matrix.py tests\test_kingslayer_quick_pick_source_decision.py docs\operator\kingslayer-quick-pick-source-decision.md docs\operator\source-backed-strong-closure.md docs\operator\README.md docs\operator\boarlock-fracking-source-decision.md
git commit -m "docs: preserve kingslayer quick pick closure truth"
```

Expected: commit succeeds.

- [ ] **Step 5: Push**

Run:

```powershell
git push
```

Expected: current branch pushes to its tracked remote.

---

## Out Of Scope For This Plan

- Black-box full-chain CLI proof. That is the next best follow-up after this closure truth wave.
- Broad docs cleanup or archive restructuring.
- New representative decks.
- New VisionAI runtime surfaces.
- Any HSTuner, replay, HDT, Power.log, winrate, or post-run logic.

## Self-Review

- Spec coverage: The plan implements the recommended Kingslayer Quick Pick closure/preservation wave, keeps the 11-row matrix, preserves Boarlock, and keeps HSConfig lean.
- Placeholder scan: No forbidden placeholder patterns or undefined function names are used in task steps.
- Type consistency: The plan uses existing `build_source_depth_closure_index(matrix, deck_reports) -> dict[str, Any]`, existing matrix `strongness_visibility` fields, and existing pytest/module layout.
- Risk: If a new exact Kingslayer Quick Pick mulligan source is found during Task 1, pause this preservation plan and replace Tasks 2-4 with a promotion-specific plan that adds the exact source claim and proves all six source-backed strong checks.

# HSConfig Boarlock Closure Wave Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the existing Boarlock source-informed matrix row by either promoting it with exact source-backed evidence or preserving it with an explicit stop condition that explains why promotion is not honest.

**Architecture:** Keep HSConfig as a narrow pre-run CustomConfig generator. The work adds a small fixture-closure decision layer around existing `prepare` reports, then uses it to drive the Boarlock closure outcome without broadening runtime surfaces or adding new representative decks.

**Tech Stack:** Python 3.11+, `pytest`, existing `hsconfig` package, existing Hearthstone deckstring dependency, JSON fixtures and operator docs.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig` on `main`.
- Keep HSConfig pre-run only: no replay parsing, no winrate, no HSTuner, no post-game tuning.
- Normal runtime output remains only `GlobalValues.json`, `Mulligan.json`, per-card CardID JSON, and exact justified `Combo.json`.
- Do not emit `Presume.json` or `Concede.json` in the normal path.
- Do not add more representative decks before Boarlock and Kingslayer have a clean closure or explicit preserved stop condition.
- Keep `reports/operator_summary.json` as the single normal operator gate.
- Boarlock must remain the first closure target. Kingslayer is regression/control only in this wave.
- If exact deck-specific Fracking mulligan evidence is not found, preserve Boarlock as blocked with a clear stop condition instead of forcing promotion.

---

## File Structure

- Modify: `src/hsconfig/source_depth_closure_index.py`
  - Add explicit closure outcome fields for source-informed rows: `stop_condition`, `stop_condition_reason`, `closure_blocker_stack`, and `recommended_next_target`.
- Create: `tests/test_boarlock_closure_wave.py`
  - New focused tests for Boarlock-first closure, explicit stop condition, no matrix broadening, and no runtime-surface widening.
- Modify: `tests/fixtures/source_documents_boarlock_strong.json`
  - Only if exact deck-specific Fracking evidence is found. If not found, leave this source bundle unchanged.
- Modify: `docs/operator/archetype-fixture-matrix.json`
  - Update only Boarlock `strongness_visibility` after fresh evidence determines the outcome.
- Modify: `docs/operator/source-backed-strong-closure.md`
  - Record the Boarlock closure decision and the exact reason for promotion or preservation.
- Modify: `docs/operator/README.md`
  - Add one sentence pointing operators to the closure decision when a source-informed fixture is intentionally preserved.

---

### Task 1: Add Explicit Source-Informed Closure Decisions

**Files:**
- Modify: `src/hsconfig/source_depth_closure_index.py`
- Test: `tests/test_boarlock_closure_wave.py`

**Interfaces:**
- Consumes: `build_source_depth_closure_index(matrix: dict[str, Any], deck_reports: dict[str, dict[str, Any]]) -> dict[str, Any]`
- Produces: existing return shape plus per-deck fields:
  - `closure_blocker_stack: list[str]`
  - `stop_condition: str | None`
  - `stop_condition_reason: str | None`
  - `recommended_next_target: str | None`

- [ ] **Step 1: Write the failing test for Boarlock explicit stop decision**

Create `tests/test_boarlock_closure_wave.py` with:

```python
from __future__ import annotations

from hsconfig.source_depth_closure_index import build_source_depth_closure_index


def test_boarlock_source_informed_row_exposes_explicit_stop_condition():
    matrix = {
        "decks": [
            {
                "deck_name": "Boarlock",
                "fixture_stage": "source_informed_valid_fixture",
                "strongness_visibility": {
                    "first_strongness_gap": "needs_mulligan_claim_for_fracking",
                    "source_informed_apply_readiness": "blocked",
                    "source_informed_blocking_reasons": [
                        "cards_need_runtime_surface",
                        "generic_low_confidence_cards",
                        "uncovered_cards",
                        "unsupported_conditions_present",
                    ],
                    "closure_state": "source_informed_blocked",
                    "closure_priority": 1,
                    "operator_action": "close_existing_source_informed_fixture",
                },
            },
            {
                "deck_name": "Kingslayer",
                "fixture_stage": "source_informed_valid_fixture",
                "strongness_visibility": {
                    "first_strongness_gap": "needs_mulligan_claim_for_quick_pick",
                    "source_informed_apply_readiness": "blocked",
                    "source_informed_blocking_reasons": [
                        "unsupported_conditions_present",
                    ],
                    "closure_state": "source_informed_blocked",
                    "closure_priority": 2,
                    "operator_action": "close_existing_source_informed_fixture",
                },
            },
        ]
    }

    report = build_source_depth_closure_index(matrix, {})

    boarlock = report["decks"]["Boarlock"]
    assert boarlock["closure_decision"] == "preserve_source_informed_until_blockers_close"
    assert boarlock["closure_blocker_stack"] == [
        "cards_need_runtime_surface",
        "generic_low_confidence_cards",
        "uncovered_cards",
        "unsupported_conditions_present",
    ]
    assert boarlock["stop_condition"] == "exact_source_or_lowering_gap_still_open"
    assert boarlock["stop_condition_reason"] == (
        "source-informed row has hard blockers and cannot be promoted or applied as strong"
    )
    assert boarlock["recommended_next_target"] == "Boarlock"

    kingslayer = report["decks"]["Kingslayer"]
    assert kingslayer["recommended_next_target"] is None
```

- [ ] **Step 2: Run the new test to verify it fails**

Run:

```powershell
python -m pytest tests\test_boarlock_closure_wave.py::test_boarlock_source_informed_row_exposes_explicit_stop_condition -q
```

Expected: FAIL with `KeyError: 'closure_blocker_stack'` or `KeyError: 'stop_condition'`.

- [ ] **Step 3: Implement minimal closure decision fields**

Modify `src/hsconfig/source_depth_closure_index.py` inside the per-deck dictionary returned in `build_source_depth_closure_index`:

```python
        decks[deck_name] = {
            "deck_name": deck_name,
            "fixture_stage": fixture_stage,
            "report_status": report_status,
            "technical_status": operator.get("technical_status"),
            "semantic_status": operator.get("semantic_status"),
            "first_matrix_gap": str(visibility.get("first_strongness_gap", "")),
            "source_informed_blocking_reasons": blocking_reasons,
            "closure_blocker_stack": blocking_reasons,
            "first_blocking_reason": blocking_reasons[0] if blocking_reasons else None,
            "promotion_ready": promotion_ready,
            "first_missing_chain": first_missing_chain,
            "closure_decision": closure_decision,
            "preserve_reason": _preserve_reason(closure_decision),
            "stop_condition": _stop_condition(
                closure_decision=closure_decision,
                blocking_reasons=blocking_reasons,
            ),
            "stop_condition_reason": _preserve_reason(closure_decision),
            "recommended_next_target": _recommended_next_target(
                deck_name=deck_name,
                fixture_stage=fixture_stage,
                blocking_reasons=blocking_reasons,
                visibility=visibility,
            ),
            "next_action": _next_action(
                fixture_stage=fixture_stage,
                report_status=report_status,
                promotion_ready=promotion_ready,
                first_missing_chain=first_missing_chain,
            ),
        }
```

Add these helper functions near `_preserve_reason`:

```python
def _stop_condition(
    *,
    closure_decision: str,
    blocking_reasons: list[str],
) -> str | None:
    if closure_decision != "preserve_source_informed_until_blockers_close":
        return None
    if blocking_reasons:
        return "exact_source_or_lowering_gap_still_open"
    return "first_missing_chain_still_open"


def _recommended_next_target(
    *,
    deck_name: str,
    fixture_stage: str,
    blocking_reasons: list[str],
    visibility: dict[str, Any],
) -> str | None:
    if fixture_stage != "source_informed_valid_fixture" or not blocking_reasons:
        return None
    try:
        priority = int(visibility.get("closure_priority", 0))
    except (TypeError, ValueError):
        priority = 0
    return deck_name if priority == 1 else None
```

- [ ] **Step 4: Run the focused test**

Run:

```powershell
python -m pytest tests\test_boarlock_closure_wave.py::test_boarlock_source_informed_row_exposes_explicit_stop_condition -q
```

Expected: PASS.

- [ ] **Step 5: Run existing closure tests**

Run:

```powershell
python -m pytest tests\test_fixture_source_depth_closure.py tests\test_matrix_visibility.py tests\test_source_depth_closure_index.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add src\hsconfig\source_depth_closure_index.py tests\test_boarlock_closure_wave.py
git commit -m "feat: expose source-informed closure decisions"
```

---

### Task 2: Prove Current Boarlock Blocker Stack With Fresh Prepare Reports

**Files:**
- Modify: `tests/test_boarlock_closure_wave.py`
- Read: `tests/helpers/fixture_prepare.py`
- Read: `tests/fixtures/source_documents_boarlock_strong.json`

**Interfaces:**
- Consumes: `tests.helpers.fixture_prepare.prepare_fixture_deck(tmp_path: Path, deck: dict[str, Any]) -> dict[str, Any]`
- Produces: test coverage proving current Boarlock closure blockers stay visible until exact evidence or lowering is added.

- [ ] **Step 1: Add the fresh prepare regression test**

Append to `tests/test_boarlock_closure_wave.py`:

```python
from tests.helpers.fixture_prepare import load_archetype_matrix, prepare_fixture_deck


def test_boarlock_prepare_keeps_full_blocker_stack_visible(tmp_path, monkeypatch):
    monkeypatch.setattr("hsconfig.cli.fetch_latest_cards", lambda timeout=10.0: [])
    deck = next(
        row for row in load_archetype_matrix() if row["deck_name"] == "Boarlock"
    )

    result = prepare_fixture_deck(tmp_path, deck)

    operator = result["operator"]
    gap_report = result["source_claim_gap_report"]
    promotion = result["strong_promotion_report"]
    readiness = result["readiness"]

    assert result["exit_code"] == 0
    assert operator["technical_status"] == "VALID_PACKAGE"
    assert operator["semantic_status"] == "VALID_BUT_NOT_GUIDE_STRONG"
    assert operator["next_action"] == "IMPROVE_GUIDE_SOURCES_BEFORE_STRONG_APPLY"
    assert operator["source_informed_apply_readiness"]["status"] == "blocked"
    assert operator["source_informed_apply_readiness"]["blocking_reasons"] == [
        "cards_need_runtime_surface",
        "generic_low_confidence_cards",
        "uncovered_cards",
        "unsupported_conditions_present",
    ]

    assert promotion["promotion_ready"] is False
    assert promotion["next_action"] == "close_first_missing_chain"
    assert "Combo.json" in result["generated_files"]
    assert "Presume.json" not in result["generated_files"]
    assert "Concede.json" not in result["generated_files"]

    first_chain = gap_report["summary"]["first_missing_chain"]
    assert first_chain == {
        "card_id": "WW_092",
        "name": "Fracking",
        "first_missing_link": "needs_mulligan_claim",
        "recommended_source_claim_kind": "mulligan_keep",
        "next_action": "add_mulligan_keep_or_discard_claim",
        "priority_score": 95,
        "priority_reason": "missing_link:needs_mulligan_claim, report_only_supported:+5",
    }

    summary = readiness["summary"]
    assert summary["cards_needing_mulligan_claims"] >= 1
    assert summary["cards_needing_runtime_surface"] >= 1
    assert summary["generic_low_confidence"] >= 1
```

- [ ] **Step 2: Run the test**

Run:

```powershell
python -m pytest tests\test_boarlock_closure_wave.py::test_boarlock_prepare_keeps_full_blocker_stack_visible -q
```

Expected: PASS. If the exact `priority_score` changes because upstream priority logic has changed, stop and inspect `reports/source_claim_gap_report.json`; do not rewrite the expected output until the reason is understood.

- [ ] **Step 3: Commit**

```powershell
git add tests\test_boarlock_closure_wave.py
git commit -m "test: pin boarlock closure blockers"
```

---

### Task 3: Decide Fracking Evidence Outcome Without Forcing Promotion

**Files:**
- Modify: `tests/fixtures/source_documents_boarlock_strong.json`
- Modify: `docs/operator/source-backed-strong-closure.md`
- Test: `tests/test_boarlock_closure_wave.py`

**Interfaces:**
- Consumes: existing source document JSON shape under `source_documents`.
- Produces: one of two explicit outcomes:
  - Promotion path: exact source-backed `mulligan_keep` or `mulligan_discard` claim for `WW_092`.
  - Preserve path: no fixture source mutation, and docs state the exact source gap remains open.

- [ ] **Step 1: Research exact Fracking mulligan evidence**

Use only deck-specific Boarlock evidence for this exact deck family. Acceptable evidence must name `Fracking` or the exact card ID `WW_092` in a Boarlock, Elwynn Boar Warlock, or exact provided-deck context and must state keep, discard, or situational mulligan intent.

Reject these as promotion evidence:

```text
generic draw advice without Fracking
Sludgelock Fracking mulligan advice
Warlock draw advice without the Boarlock deck plan
source text that lists Fracking in the deck but gives no mulligan instruction
```

- [ ] **Step 2A: If exact Fracking evidence is found, add the source claim**

Modify `tests/fixtures/source_documents_boarlock_strong.json` by adding one atomic claim to the most specific Boarlock mulligan source document:

```json
{
  "claim_kind": "mulligan_keep",
  "cards": ["WW_092"],
  "selector": "WW_092",
  "selector_kind": "card",
  "stance": "keep",
  "evidence_text_short": "Exact source text must state that Boarlock keeps Fracking or keeps it under the named condition.",
  "source_confidence": "medium"
}
```

If the source states discard instead, use:

```json
{
  "claim_kind": "mulligan_discard",
  "cards": ["WW_092"],
  "selector": "WW_092",
  "selector_kind": "card",
  "stance": "discard",
  "evidence_text_short": "Exact source text must state that Boarlock discards Fracking or throws it under the named condition.",
  "source_confidence": "medium"
}
```

The implementer must replace `evidence_text_short` with the exact short source-backed paraphrase before committing. Do not commit the template text above.

- [ ] **Step 2B: If exact Fracking evidence is not found, keep the fixture unchanged**

Leave `tests/fixtures/source_documents_boarlock_strong.json` unchanged. Update `docs/operator/source-backed-strong-closure.md` to keep Boarlock in `source_informed_valid_fixture` and preserve this explicit reason:

```markdown
| Boarlock | `source_informed_valid_fixture` | Preserved blocked: exact deck-specific Fracking mulligan evidence remains unavailable. The fixture still proves valid Combo.json generation, but it cannot be promoted while WW_092 lacks a keep/discard claim and runtime-surface blockers remain. |
```

- [ ] **Step 3: Add outcome-specific tests**

Append this helper and test to `tests/test_boarlock_closure_wave.py`:

```python
def test_boarlock_closure_outcome_is_either_strong_or_explicitly_preserved(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr("hsconfig.cli.fetch_latest_cards", lambda timeout=10.0: [])
    deck = next(
        row for row in load_archetype_matrix() if row["deck_name"] == "Boarlock"
    )

    result = prepare_fixture_deck(tmp_path, deck)
    operator = result["operator"]
    gap_report = result["source_claim_gap_report"]
    promotion = result["strong_promotion_report"]

    if promotion["promotion_ready"]:
        assert operator["semantic_status"] == "SOURCE_BACKED_STRONG"
        assert operator["next_action"] == "READY_TO_APPLY_OR_HANDOFF"
        assert gap_report["summary"]["blocked_cards"] == 0
        assert gap_report["summary"]["first_missing_chain"] is None
    else:
        assert operator["semantic_status"] == "VALID_BUT_NOT_GUIDE_STRONG"
        assert operator["source_informed_apply_readiness"]["status"] == "blocked"
        assert gap_report["summary"]["first_missing_chain"]["card_id"] == "WW_092"
        assert promotion["next_action"] == "close_first_missing_chain"
```

- [ ] **Step 4: Run Boarlock focused tests**

Run:

```powershell
python -m pytest tests\test_boarlock_closure_wave.py tests\test_archetype_source_fixtures.py::test_boarlock_fixture_has_exact_runtime_lowerable_combo_sequence -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Promotion path:

```powershell
git add tests\fixtures\source_documents_boarlock_strong.json tests\test_boarlock_closure_wave.py
git commit -m "test: close boarlock fracking evidence path"
```

Preserve path:

```powershell
git add docs\operator\source-backed-strong-closure.md tests\test_boarlock_closure_wave.py
git commit -m "docs: preserve boarlock closure stop condition"
```

---

### Task 4: Update Matrix Truth From Fresh Boarlock Evidence

**Files:**
- Modify: `docs/operator/archetype-fixture-matrix.json`
- Modify: `docs/operator/source-backed-strong-closure.md`
- Modify: `tests/test_matrix_visibility.py`
- Modify: `tests/test_fixture_source_depth_closure.py`

**Interfaces:**
- Consumes: Boarlock fresh prepare result from Task 3.
- Produces: matrix state that exactly matches Boarlock evidence outcome.

- [ ] **Step 1: If Boarlock promotes, update matrix row**

Only if a fresh prepare run proves `promotion_ready=true`, update the Boarlock row in `docs/operator/archetype-fixture-matrix.json`:

```json
"fixture_stage": "core_source_backed_fixture",
"strongness_visibility": {
  "current_stage": "core_source_backed_fixture",
  "first_strongness_gap": "none",
  "operator_action": "keep_as_core_control_fixture"
}
```

Keep these fields unchanged:

```json
"expected_runtime_surfaces": ["GlobalValues.json", "Mulligan.json", "<CARDID>.json", "Combo.json"],
"decision_families_proven": ["combo_control", "resource_setup"]
```

- [ ] **Step 2: If Boarlock remains blocked, update matrix row with explicit stop condition**

Only if Boarlock remains blocked, keep `fixture_stage` as `source_informed_valid_fixture` and update `strongness_visibility`:

```json
"strongness_visibility": {
  "current_stage": "source_informed_valid_fixture",
  "first_strongness_gap": "needs_mulligan_claim_for_fracking",
  "source_informed_apply_readiness": "blocked",
  "source_informed_blocking_reasons": [
    "cards_need_runtime_surface",
    "generic_low_confidence_cards",
    "uncovered_cards",
    "unsupported_conditions_present"
  ],
  "closure_state": "source_informed_blocked",
  "closure_priority": 1,
  "operator_action": "preserve_source_informed_with_explicit_stop_condition",
  "stop_condition": "exact_boarlock_fracking_mulligan_source_unavailable"
}
```

- [ ] **Step 3: Update matrix tests for the chosen outcome**

If Boarlock promotes, change `tests/test_matrix_visibility.py` expectations:

```python
assert report["core_source_backed_fixture_count"] == 10
assert report["source_informed_valid_fixture_count"] == 1
```

and remove Boarlock from the source-informed blocker assertions.

If Boarlock remains blocked, keep the counts at 9 and 2, and add:

```python
assert by_name["Boarlock"]["operator_action"] == (
    "preserve_source_informed_with_explicit_stop_condition"
)
```

If `build_matrix_visibility()` does not expose `operator_action`, add that field to `src/hsconfig/matrix_visibility.py` in the per-row visibility output.

- [ ] **Step 4: Run matrix and closure tests**

Run:

```powershell
python -m pytest tests\test_matrix_visibility.py tests\test_fixture_source_depth_closure.py tests\test_matrix_current_truth.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Promotion path:

```powershell
git add docs\operator\archetype-fixture-matrix.json docs\operator\source-backed-strong-closure.md tests\test_matrix_visibility.py tests\test_fixture_source_depth_closure.py
git commit -m "docs: promote boarlock fixture closure"
```

Preserve path:

```powershell
git add docs\operator\archetype-fixture-matrix.json docs\operator\source-backed-strong-closure.md tests\test_matrix_visibility.py tests\test_fixture_source_depth_closure.py src\hsconfig\matrix_visibility.py
git commit -m "docs: record boarlock closure stop condition"
```

---

### Task 5: Guard Against Runtime Surface Creep

**Files:**
- Modify: `tests/test_boarlock_closure_wave.py`
- Read: `docs/operator/archetype-fixture-matrix.json`

**Interfaces:**
- Consumes: Boarlock prepare output.
- Produces: regression test proving Boarlock closure did not add normal-path surfaces.

- [ ] **Step 1: Add runtime-surface guard test**

Append to `tests/test_boarlock_closure_wave.py`:

```python
def test_boarlock_closure_does_not_widen_runtime_surfaces(tmp_path, monkeypatch):
    monkeypatch.setattr("hsconfig.cli.fetch_latest_cards", lambda timeout=10.0: [])
    deck = next(
        row for row in load_archetype_matrix() if row["deck_name"] == "Boarlock"
    )

    result = prepare_fixture_deck(tmp_path, deck)
    generated = set(result["generated_files"])

    assert "GlobalValues.json" in generated
    assert "Mulligan.json" in generated
    assert "Combo.json" in generated
    assert "Presume.json" not in generated
    assert "Concede.json" not in generated

    unexpected = {
        name
        for name in generated
        if name.endswith(".json")
        and name not in {"GlobalValues.json", "Mulligan.json", "Combo.json"}
        and not name.startswith("SW_")
        and not name.startswith("UNG_")
        and not name.startswith("DINO_")
        and not name.startswith("ULD_")
        and not name.startswith("WW_")
        and not name.startswith("YOG_")
        and not name.startswith("EDR_")
        and not name.startswith("TOY_")
        and not name.startswith("TLC_")
        and not name.startswith("VAC_")
        and not name.startswith("EX1_")
    }
    assert unexpected == set()
```

- [ ] **Step 2: Run the runtime-surface guard**

Run:

```powershell
python -m pytest tests\test_boarlock_closure_wave.py::test_boarlock_closure_does_not_widen_runtime_surfaces -q
```

Expected: PASS.

- [ ] **Step 3: Commit**

```powershell
git add tests\test_boarlock_closure_wave.py
git commit -m "test: guard boarlock runtime surfaces"
```

---

### Task 6: Final Verification And Operator Handoff

**Files:**
- Modify: `docs/operator/README.md`
- Modify: `docs/operator/source-backed-strong-closure.md`
- Read: `docs/research/2026-07-08-hsconfig-next-recommendation/README.md`

**Interfaces:**
- Consumes: all prior task outcomes.
- Produces: final docs and verified repo state.

- [ ] **Step 1: Add concise operator guidance**

In `docs/operator/README.md`, under `Fixture Matrix`, add this sentence:

```markdown
When a source-informed row cannot be promoted honestly, keep it visible with an explicit stop condition instead of widening the matrix or forcing a weak source claim.
```

- [ ] **Step 2: Ensure closure doc matches final Boarlock state**

In `docs/operator/source-backed-strong-closure.md`, ensure the Boarlock row says exactly one of:

Promotion path:

```markdown
| Boarlock | `core_source_backed_fixture` | Promotion proven. Preserve as the combo-control and exact `Combo.json` control fixture. |
```

Preserve path:

```markdown
| Boarlock | `source_informed_valid_fixture` | Preserved blocked with explicit stop condition: exact Boarlock Fracking mulligan evidence remains unavailable or unresolved lowering blockers remain. Preserve this row as the combo-control source-informed control until those blockers close. |
```

- [ ] **Step 3: Run targeted tests**

Run:

```powershell
python -m pytest tests\test_boarlock_closure_wave.py tests\test_archetype_source_fixtures.py tests\test_fixture_source_depth_closure.py tests\test_matrix_visibility.py tests\test_matrix_current_truth.py tests\test_source_depth_closure_index.py tests\test_cli_help.py -q
```

Expected: PASS.

- [ ] **Step 4: Run full test suite**

Run:

```powershell
python -m pytest -q
```

Expected: PASS with no unexpected failures. Skips are acceptable only if they match the current baseline.

- [ ] **Step 5: Check installed skill sync**

Run:

```powershell
python scripts\sync_installed_skill.py --check
```

Expected:

```text
HSConfig skill is in sync: C:\Users\darbo\.codex\skills\hsconfig
```

- [ ] **Step 6: Commit docs and final state**

```powershell
git add docs\operator\README.md docs\operator\source-backed-strong-closure.md
git commit -m "docs: finalize boarlock closure guidance"
```

- [ ] **Step 7: Push**

```powershell
git status --short --branch
git push origin main
git status --short --branch
```

Expected final status:

```text
## main...origin/main
```

---

## Self-Review Checklist

- [ ] Spec coverage: Boarlock is first, Kingslayer is second, no matrix broadening, no runtime-surface widening.
- [ ] Evidence gate coverage: exact Fracking source can promote; missing exact source preserves a documented stop condition.
- [ ] Type consistency: new `source_depth_closure_index` fields are strings, lists, or `None` as specified.
- [ ] Boundary coverage: no replay, winrate, HSTuner, `Presume.json`, or `Concede.json` work enters HSConfig.
- [ ] Test coverage: new Boarlock tests plus existing matrix, fixture, closure, combo, and full suite.

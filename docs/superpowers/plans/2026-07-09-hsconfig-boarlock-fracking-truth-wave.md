# HSConfig Boarlock Fracking Truth Wave Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve Boarlock as an honest source-informed `Combo.json` control when exact `WW_092` / `Fracking` mulligan evidence is unavailable, and expose Kingslayer as the next actionable closure target.

**Architecture:** Keep HSConfig as a lean pre-run HearthRanger VisionAI CustomConfig generator. Do not widen the representative matrix and do not force weak source claims into `SOURCE_BACKED_STRONG`; instead add an explicit Boarlock source-decision artifact, keep the existing first missing chain visible, and add a separate actionable closure pointer that skips durably preserved stop-condition rows. Boarlock remains first in closure truth because it is the combo-control row; Kingslayer becomes the next actionable row after Boarlock preservation.

**Tech Stack:** Python 3.11+, pytest, existing HSConfig CLI/report builders, existing source-depth closure index, existing representative fixture matrix, Markdown operator docs, installed HSConfig skill sync script.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig`.
- Do not add dependencies.
- Do not add replay, HDT, Power.log, winrate, candidate-promotion, or HSTuner behavior to HSConfig.
- Do not add normal-path `Presume.json` or `Concede.json`.
- Do not widen `docs/operator/archetype-fixture-matrix.json`.
- Keep `CuteWarrior` in `docs/operator/supplemental-proof-decks.json`; do not promote it into the representative matrix.
- Do not invent an exact Boarlock `Fracking` mulligan claim.
- Treat low-confidence or adjacent-archetype Fracking advice as insufficient for `SOURCE_BACKED_STRONG`.
- Keep runtime apply guarded by `reports/operator_summary.json`.
- Keep source-informed apply weaker than `SOURCE_BACKED_STRONG`.
- If implementation finds a new exact high-confidence Boarlock-relevant Fracking mulligan source, stop this preservation path and report the source before changing source documents.

---

## File Structure

- Create `docs/operator/boarlock-fracking-source-decision.md`
  - Human-readable evidence decision for why Boarlock stays source-informed.
  - Names accepted and rejected evidence types.

- Modify `src/hsconfig/source_depth_closure_index.py`
  - Add `next_actionable_closure_target`.
  - Keep `next_closure_target` and `closure_sequence` backwards compatible.

- Modify tests:
  - `tests/test_boarlock_closure_wave.py`
  - `tests/test_source_depth_closure_index.py`
  - `tests/test_matrix_current_truth.py`
  - Add `tests/test_boarlock_fracking_source_decision.py`

- Modify docs:
  - `docs/operator/README.md`
  - `docs/operator/source-backed-strong-closure.md`

- Modify repo-side skill guidance:
  - `.agents/skills/hsconfig/SKILL.md`
  - `.agents/skills/hsconfig/references/workflow.md`

- Sync installed skill after repo-side skill guidance changes:
  - `python scripts/sync_installed_skill.py`
  - `python scripts/sync_installed_skill.py --check`

---

### Task 1: Boarlock Fracking Decision Artifact

**Files:**
- Create: `docs/operator/boarlock-fracking-source-decision.md`
- Create: `tests/test_boarlock_fracking_source_decision.py`

**Interfaces:**
- Consumes: current matrix row for `Boarlock`, current fixture `tests/fixtures/source_documents_boarlock_strong.json`
- Produces: a stable operator artifact that says Boarlock is durably preserved unless exact Fracking mulligan evidence appears

- [ ] **Step 1: Write the failing decision-artifact test**

Create `tests/test_boarlock_fracking_source_decision.py`:

```python
from __future__ import annotations

import json
from pathlib import Path


DECISION_DOC = Path("docs/operator/boarlock-fracking-source-decision.md")
BOARLOCK_FIXTURE = Path("tests/fixtures/source_documents_boarlock_strong.json")


def test_boarlock_fracking_decision_artifact_exists_and_sets_boundary():
    text = DECISION_DOC.read_text(encoding="utf-8")

    assert "# Boarlock Fracking Source Decision" in text
    assert "`WW_092` / `Fracking`" in text
    assert "`exact_boarlock_fracking_mulligan_source_unavailable`" in text
    assert "Low-confidence generic card-draw advice is not enough" in text
    assert "Adjacent archetype advice is not enough" in text
    assert "Do not promote Boarlock to `core_source_backed_fixture`" in text
    assert "Next actionable closure target: `Kingslayer`" in text


def test_existing_fracking_mulligan_claim_is_low_confidence_only():
    payload = json.loads(BOARLOCK_FIXTURE.read_text(encoding="utf-8"))
    claims = [
        claim
        for source in payload["source_documents"]
        for claim in source["claims"]
        if claim.get("claim_kind") == "mulligan_keep"
        and "WW_092" in claim.get("cards", [])
    ]

    assert len(claims) == 1
    assert claims[0]["source_confidence"] == "low"
    assert "card draw" in claims[0]["evidence_text_short"].lower()
```

- [ ] **Step 2: Run the decision-artifact test to verify it fails**

Run:

```powershell
python -m pytest tests/test_boarlock_fracking_source_decision.py -q
```

Expected: FAIL because `docs/operator/boarlock-fracking-source-decision.md` does not exist.

- [ ] **Step 3: Create the decision artifact**

Create `docs/operator/boarlock-fracking-source-decision.md` with this content:

```markdown
# Boarlock Fracking Source Decision

This page records the current HSConfig decision for `Boarlock` and `WW_092` / `Fracking`.

## Decision

Keep `Boarlock` as `source_informed_valid_fixture`.

Do not promote Boarlock to `core_source_backed_fixture` unless an exact Boarlock-relevant source explicitly says whether `WW_092` / `Fracking` should be kept or discarded in the mulligan.

Current stop condition:

`exact_boarlock_fracking_mulligan_source_unavailable`

## Why

The current Boarlock fixture contains a low-confidence mulligan row for `WW_092` / `Fracking`, but the evidence is generic card-draw advice rather than an exact Fracking keep-or-discard instruction.

Low-confidence generic card-draw advice is not enough for `SOURCE_BACKED_STRONG`.

Adjacent archetype advice is not enough for `SOURCE_BACKED_STRONG`.

The row must keep exposing:

- `technical_status=VALID_PACKAGE`
- `semantic_status=VALID_BUT_NOT_GUIDE_STRONG`
- `first_missing_chain.card_id=WW_092`
- `first_missing_chain.name=Fracking`
- `first_missing_chain.first_missing_link=needs_mulligan_claim`
- `source_depth_lane=mulligan_claim_gap`

## Closure Routing

Boarlock remains the first closure-truth row because it is the representative `Combo.json` control.

After this explicit preservation decision, the next actionable closure target is:

`Kingslayer`

Next actionable closure target: `Kingslayer`

## Accepted Evidence

Accepted evidence for changing this decision must be all of:

- Boarlock-relevant.
- About the provided Boarlock-style combo/control shell.
- Explicit about `Fracking`.
- Explicit about mulligan keep or discard.
- Current enough to not contradict live Hearthstone card text or HearthstoneJSON metadata.

## Rejected Evidence

Rejected evidence:

- Generic "mulligan for card draw" statements.
- Adjacent archetype advice.
- Deck pages that list `Fracking` without mulligan instruction.
- Low-confidence source rows.
- Runtime logs, winrate, replay evidence, HDT evidence, or HSTuner output, because HSConfig is pre-run only.
```

- [ ] **Step 4: Run the decision-artifact test**

Run:

```powershell
python -m pytest tests/test_boarlock_fracking_source_decision.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 1**

```powershell
git add docs/operator/boarlock-fracking-source-decision.md tests/test_boarlock_fracking_source_decision.py
git commit -m "docs: record boarlock fracking source decision"
```

---

### Task 2: Next Actionable Closure Target

**Files:**
- Modify: `src/hsconfig/source_depth_closure_index.py`
- Modify: `tests/test_source_depth_closure_index.py`
- Modify: `tests/test_boarlock_closure_wave.py`

**Interfaces:**
- Consumes: `build_source_depth_closure_index(matrix: dict[str, Any], deck_reports: dict[str, dict[str, Any]]) -> dict[str, Any]`
- Produces: `report["summary"]["next_actionable_closure_target"]`

- [ ] **Step 1: Write the failing closure-index test**

Add this test to `tests/test_source_depth_closure_index.py`:

```python
def test_index_skips_durably_preserved_rows_for_next_actionable_target():
    matrix = {
        "decks": [
            {
                "deck_name": "Boarlock",
                "fixture_stage": "source_informed_valid_fixture",
                "strongness_visibility": {
                    "closure_priority": 1,
                    "operator_action": "preserve_source_informed_with_explicit_stop_condition",
                    "stop_condition": "exact_boarlock_fracking_mulligan_source_unavailable",
                    "source_informed_blocking_reasons": [
                        "cards_need_runtime_surface",
                        "generic_low_confidence_cards",
                    ],
                },
            },
            {
                "deck_name": "Kingslayer",
                "fixture_stage": "source_informed_valid_fixture",
                "strongness_visibility": {
                    "closure_priority": 2,
                    "operator_action": "close_existing_source_informed_fixture",
                    "source_informed_blocking_reasons": ["unsupported_conditions_present"],
                },
            },
        ]
    }

    report = build_source_depth_closure_index(matrix, {})

    assert report["summary"]["next_closure_target"] == "Boarlock"
    assert report["summary"]["closure_sequence"] == ["Boarlock", "Kingslayer"]
    assert report["summary"]["preserved_source_informed_targets"] == ["Boarlock"]
    assert report["summary"]["next_actionable_closure_target"] == "Kingslayer"
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```powershell
python -m pytest tests/test_source_depth_closure_index.py::test_index_skips_durably_preserved_rows_for_next_actionable_target -q
```

Expected: FAIL because `next_actionable_closure_target` does not exist.

- [ ] **Step 3: Implement actionable target helper**

In `src/hsconfig/source_depth_closure_index.py`, add:

```python
def _next_actionable_closure_target(rows: list[dict[str, Any]]) -> str | None:
    for row in sorted(rows, key=lambda item: (_closure_priority(item), str(item.get("deck_name", "")))):
        if not isinstance(row, dict):
            continue
        if row.get("fixture_stage") != "source_informed_valid_fixture":
            continue
        if _closure_priority(row) <= 0:
            continue
        visibility = row.get("strongness_visibility", {})
        if not isinstance(visibility, dict):
            continue
        is_durably_preserved = (
            visibility.get("operator_action")
            == "preserve_source_informed_with_explicit_stop_condition"
            and isinstance(visibility.get("stop_condition"), str)
            and bool(visibility.get("stop_condition"))
        )
        if is_durably_preserved:
            continue
        deck_name = row.get("deck_name")
        if deck_name:
            return str(deck_name)
    return None
```

Then add this near the existing `closure_sequence` assignment:

```python
next_actionable_target = _next_actionable_closure_target(rows)
```

Add this to the returned summary:

```python
"next_actionable_closure_target": next_actionable_target,
```

- [ ] **Step 4: Add Boarlock wave assertion**

In `tests/test_boarlock_closure_wave.py`, extend `test_boarlock_source_informed_row_exposes_explicit_stop_condition`:

```python
assert report["summary"]["next_actionable_closure_target"] == "Kingslayer"
```

- [ ] **Step 5: Run closure-index tests**

Run:

```powershell
python -m pytest tests/test_source_depth_closure_index.py tests/test_boarlock_closure_wave.py tests/test_matrix_visibility.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 2**

```powershell
git add src/hsconfig/source_depth_closure_index.py tests/test_source_depth_closure_index.py tests/test_boarlock_closure_wave.py
git commit -m "feat: expose next actionable closure target"
```

---

### Task 3: Operator Docs And Matrix Truth Wording

**Files:**
- Modify: `docs/operator/README.md`
- Modify: `docs/operator/source-backed-strong-closure.md`
- Modify: `tests/test_matrix_current_truth.py`
- Modify: `tests/test_operator_guidance.py` only if existing operator-doc wording tests need the new phrase

**Interfaces:**
- Consumes: `next_actionable_closure_target`
- Produces: human-facing documentation that explains Boarlock truth versus next actionable work

- [ ] **Step 1: Write failing docs-truth assertions**

Add this test to `tests/test_matrix_current_truth.py`:

```python
def test_operator_docs_name_boarlock_preservation_and_next_actionable_target():
    operator_text = OPERATOR_README.read_text(encoding="utf-8")
    closure_text = Path("docs/operator/source-backed-strong-closure.md").read_text(
        encoding="utf-8"
    )

    expected = "Next actionable closure target after durable Boarlock preservation: `Kingslayer`."
    assert expected in operator_text
    assert expected in closure_text
    assert "Do not treat Boarlock's low-confidence Fracking row as SOURCE_BACKED_STRONG." in closure_text
```

- [ ] **Step 2: Run the docs-truth test to verify it fails**

Run:

```powershell
python -m pytest tests/test_matrix_current_truth.py::test_operator_docs_name_boarlock_preservation_and_next_actionable_target -q
```

Expected: FAIL because the new wording is not present.

- [ ] **Step 3: Update operator README**

In `docs/operator/README.md`, under `Fixture Matrix`, add:

```markdown
Boarlock remains the first closure-truth row because it is the representative
`Combo.json` control. Its current Fracking row is durably preserved as
source-informed until exact Boarlock-relevant Fracking mulligan evidence exists.
Next actionable closure target after durable Boarlock preservation: `Kingslayer`.
```

- [ ] **Step 4: Update source-backed closure doc**

In `docs/operator/source-backed-strong-closure.md`, after the current closure-order paragraph, add:

```markdown
Boarlock's current low-confidence `WW_092` / `Fracking` mulligan row documents
generic card-draw advice only. Do not treat Boarlock's low-confidence Fracking row as SOURCE_BACKED_STRONG.

Next actionable closure target after durable Boarlock preservation: `Kingslayer`.
```

- [ ] **Step 5: Run docs tests**

Run:

```powershell
python -m pytest tests/test_matrix_current_truth.py tests/test_docs_active_path.py tests/test_operator_guidance.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 3**

```powershell
git add docs/operator/README.md docs/operator/source-backed-strong-closure.md tests/test_matrix_current_truth.py tests/test_operator_guidance.py
git commit -m "docs: clarify boarlock preservation handoff"
```

If `tests/test_operator_guidance.py` is unchanged, do not stage it.

---

### Task 4: Low-Confidence Fracking Guard

**Files:**
- Modify: `tests/test_boarlock_closure_wave.py`
- No production code should change unless this test exposes a real promotion-gate bug.

**Interfaces:**
- Consumes: `prepare_fixture_deck(tmp_path, deck) -> dict[str, Any]`
- Produces: regression coverage that low-confidence Fracking advice cannot satisfy the missing mulligan claim

- [ ] **Step 1: Add the regression test**

Add this test to `tests/test_boarlock_closure_wave.py`:

```python
def test_low_confidence_fracking_mulligan_row_does_not_satisfy_missing_chain(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        "hsconfig.package_builder.fetch_latest_cards", lambda timeout=10.0: []
    )
    deck = next(
        row for row in load_archetype_matrix() if row["deck_name"] == "Boarlock"
    )

    fixture = json.loads(
        open("tests/fixtures/source_documents_boarlock_strong.json", encoding="utf-8").read()
    )
    fracking_mulligan_claims = [
        claim
        for source in fixture["source_documents"]
        for claim in source["claims"]
        if claim.get("claim_kind") == "mulligan_keep"
        and "WW_092" in claim.get("cards", [])
    ]
    assert len(fracking_mulligan_claims) == 1
    assert fracking_mulligan_claims[0]["source_confidence"] == "low"

    result = prepare_fixture_deck(tmp_path, deck)
    operator = result["operator"]
    gap_report = result["source_claim_gap_report"]

    assert operator["semantic_status"] == "VALID_BUT_NOT_GUIDE_STRONG"
    assert operator["source_informed_apply_readiness"]["status"] == "blocked"
    assert gap_report["summary"]["first_missing_chain"]["card_id"] == "WW_092"
    assert gap_report["summary"]["first_missing_chain"]["first_missing_link"] == (
        "needs_mulligan_claim"
    )
```

- [ ] **Step 2: Run the test**

Run:

```powershell
python -m pytest tests/test_boarlock_closure_wave.py::test_low_confidence_fracking_mulligan_row_does_not_satisfy_missing_chain -q
```

Expected: PASS. If it fails because Boarlock promotes, inspect the promotion path and restore the rule that low-confidence generic card-draw advice cannot satisfy an exact Fracking mulligan claim.

- [ ] **Step 3: Run Boarlock closure suite**

Run:

```powershell
python -m pytest tests/test_boarlock_closure_wave.py tests/test_source_informed_closure_contract.py tests/test_strong_promotion_report.py -q
```

Expected: PASS.

- [ ] **Step 4: Commit Task 4**

```powershell
git add tests/test_boarlock_closure_wave.py
git commit -m "test: guard boarlock fracking source confidence"
```

---

### Task 5: Skill Guidance Sync

**Files:**
- Modify: `.agents/skills/hsconfig/SKILL.md`
- Modify: `.agents/skills/hsconfig/references/workflow.md`
- Sync generated installed files under `C:\Users\darbo\.codex\skills\hsconfig\`
- Modify: `tests/test_skill_files.py`

**Interfaces:**
- Consumes: source-depth closure wording
- Produces: installed skill guidance that matches operator docs

- [ ] **Step 1: Add failing skill guidance assertions**

Add this test to `tests/test_skill_files.py`:

```python
def test_skill_names_boarlock_preservation_and_next_actionable_target():
    skill = Path(".agents/skills/hsconfig/SKILL.md").read_text(encoding="utf-8")
    workflow = Path(".agents/skills/hsconfig/references/workflow.md").read_text(
        encoding="utf-8"
    )

    expected = "Next actionable closure target after durable Boarlock preservation: `Kingslayer`."
    assert expected in skill
    assert expected in workflow
```

- [ ] **Step 2: Run the skill assertion to verify it fails**

Run:

```powershell
python -m pytest tests/test_skill_files.py::test_skill_names_boarlock_preservation_and_next_actionable_target -q
```

Expected: FAIL because skill guidance does not yet include the new phrase.

- [ ] **Step 3: Update repo-side skill guidance**

In `.agents/skills/hsconfig/SKILL.md`, replace the current closure-order paragraph with:

```markdown
Current closure truth is Boarlock first, Kingslayer second. Boarlock stays first
because it is the only representative `Combo.json` control row, but its current
Fracking source is durably preserved as source-informed unless exact
Boarlock-relevant Fracking mulligan evidence appears.
Next actionable closure target after durable Boarlock preservation: `Kingslayer`.
```

In `.agents/skills/hsconfig/references/workflow.md`, replace the matching closure-order paragraph with the same text.

- [ ] **Step 4: Sync installed skill**

Run:

```powershell
python scripts/sync_installed_skill.py
python scripts/sync_installed_skill.py --check
```

Expected:

```text
HSConfig skill is in sync: C:\Users\darbo\.codex\skills\hsconfig
```

- [ ] **Step 5: Run skill/docs tests**

Run:

```powershell
python -m pytest tests/test_skill_files.py tests/test_docs_active_path.py tests/test_report_ownership.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 5**

```powershell
git add .agents/skills/hsconfig/SKILL.md .agents/skills/hsconfig/references/workflow.md tests/test_skill_files.py
git commit -m "docs: sync boarlock closure skill guidance"
```

Do not attempt to `git add` installed files under `C:\Users\darbo\.codex\skills\hsconfig\`; they are outside this repository. The sync check is the verification.

---

### Task 6: Final Verification And Branch State

**Files:**
- No production edits unless previous tasks exposed a real defect.

**Interfaces:**
- Consumes: all prior task outputs
- Produces: verified branch ready for final review or merge

- [ ] **Step 1: Run focused closure suite**

Run:

```powershell
python -m pytest tests/test_boarlock_fracking_source_decision.py tests/test_boarlock_closure_wave.py tests/test_source_depth_closure_index.py tests/test_source_informed_closure_contract.py tests/test_matrix_current_truth.py -q
```

Expected: PASS.

- [ ] **Step 2: Run skill and operator suite**

Run:

```powershell
python -m pytest tests/test_skill_files.py tests/test_docs_active_path.py tests/test_operator_guidance.py tests/test_report_ownership.py -q
```

Expected: PASS.

- [ ] **Step 3: Run full test suite**

Run:

```powershell
python -m pytest -q
```

Expected: PASS with only the existing skipped tests.

- [ ] **Step 4: Verify installed skill sync**

Run:

```powershell
python scripts/sync_installed_skill.py --check
```

Expected:

```text
HSConfig skill is in sync: C:\Users\darbo\.codex\skills\hsconfig
```

- [ ] **Step 5: Inspect diff and status**

Run:

```powershell
git diff --stat
git status --short --branch
```

Expected:

- Only intended docs, tests, source-depth closure index, and repo-side skill files are changed.
- No raw runtime evidence is tracked.
- `docs/research/2026-07-08-hsconfig-skill-optimality-audit-v2/` and `docs/research/2026-07-09-hsconfig-skill-optimality-audit/` may remain untracked unless the user explicitly asks to commit audit research.

- [ ] **Step 6: Final commit if needed**

If Task 6 required a tiny cleanup, stage only the concrete changed files shown by `git status --short`:

```powershell
git status --short
git add <exact-file-1> <exact-file-2>
git commit -m "chore: verify boarlock closure truth wave"
```

Do not use wildcard staging. Do not commit private runtime evidence.

---

## Self-Review

- Spec coverage: The plan covers Boarlock source preservation, the low-confidence Fracking row, Kingslayer handoff, docs, skill sync, tests, and final verification.
- Scope check: The plan stays inside HSConfig pre-run behavior. It does not add HSTuner, replay, winrate, post-run tuning, Presume, or Concede behavior.
- Placeholder scan: The plan contains no open source-claim placeholder. It implements the current audited truth: exact Boarlock Fracking mulligan evidence is unavailable, so Boarlock is durably preserved.
- Type consistency: `next_actionable_closure_target` is a nullable string under `report["summary"]`; existing `next_closure_target`, `closure_sequence`, and `preserved_source_informed_targets` remain unchanged.
- Testability: Every task has targeted pytest commands and expected outcomes.

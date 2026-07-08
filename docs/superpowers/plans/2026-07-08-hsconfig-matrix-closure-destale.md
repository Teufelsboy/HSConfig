# HSConfig Matrix Closure And De-Stale Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the remaining HSConfig 11-deck source-depth gaps or document why they remain blocked, and remove stale "seven source-informed rows" guidance from the active operator path.

**Architecture:** Keep HSConfig pre-run only. Do not add replay parsing, winrate, post-run tuning, candidate promotion, or new normal runtime surfaces. Use a small research-backed closure pass for Kingslayer and Boarlock, then update matrix truth, active docs, and tests so the repo has one current source of truth.

**Tech Stack:** Python 3.11, pytest, setuptools editable install, Hearthstone deck metadata via the existing `hearthstone` dependency, HSConfig source-document fixtures, HearthRanger VisionAI JSON surfaces.

## Global Constraints

- Work only in `C:\Users\darbo\Documents\HSConfig`.
- Normal operator path remains `README.md` -> `docs/operator/README.md`.
- HSConfig is pre-run only: no replay parsing, winrate inspection, runtime log analysis, candidate promotion, or after-game tuning.
- Normal runtime outputs remain `GlobalValues.json`, `Mulligan.json`, per-card `<CARDID>.json`, and `Combo.json` only when exact valid sequence data exists.
- Do not emit `Presume.json` or `Concede.json` in the normal path.
- Do not promote a fixture by raising confidence without source evidence. If public source evidence does not support a Mulligan claim, keep the row source-informed and document the block.
- `reports/operator_summary.json` remains the single normal operator gate.
- Keep implementation small: prefer tests, fixture/source updates, docs, and existing helpers over new modules.

---

## File Structure

- Modify `docs/operator/README.md` to replace stale "seven source-informed rows" guidance with the current explicit Kingslayer/Boarlock closure target.
- Modify `docs/operator/source-backed-strong-closure.md` after fixture truth is proven.
- Modify `docs/operator/archetype-fixture-matrix.json` only after prepare runs prove promotion readiness.
- Create `docs/research/2026-07-08-hsconfig-kingslayer-boarlock-mulligan-closure/outline.yaml` and `fields.yaml` for the source-backed Mulligan closure research.
- Add research result JSON files under `docs/research/2026-07-08-hsconfig-kingslayer-boarlock-mulligan-closure/results/` if research-deep produces validated public-source summaries.
- Modify `tests/fixtures/source_documents_kingslayer_strong.json` only if the research output supports a concrete Quick Pick Mulligan keep/discard claim.
- Modify `tests/fixtures/source_documents_boarlock_strong.json` only if the research output supports a concrete Fracking Mulligan keep/discard claim.
- Modify `tests/test_fixture_source_depth_closure.py` to derive source-informed rows from the live matrix instead of a stale hard-coded seven-deck set.
- Create `tests/test_matrix_current_truth.py` for active-doc and matrix truth guardrails.
- Adjust `tests/test_matrix_visibility.py`, `tests/test_source_depth_closure_index.py`, and related matrix tests only when the matrix counts change.

---

### Task 1: Add Current-Truth Guardrails And Fix Active Operator Wording

**Files:**
- Create: `tests/test_matrix_current_truth.py`
- Modify: `docs/operator/README.md`
- Test: `tests/test_matrix_current_truth.py`

**Interfaces:**
- Consumes: `docs/operator/archetype-fixture-matrix.json` live fixture rows.
- Produces: A failing-then-passing guard that prevents active docs from drifting back to stale "seven source-informed rows" wording.

- [ ] **Step 1: Write the failing current-truth tests**

Create `tests/test_matrix_current_truth.py`:

```python
import json
from pathlib import Path


MATRIX_PATH = Path("docs/operator/archetype-fixture-matrix.json")
OPERATOR_README = Path("docs/operator/README.md")


def _matrix_rows():
    return json.loads(MATRIX_PATH.read_text(encoding="utf-8"))["decks"]


def test_active_matrix_has_only_kingslayer_and_boarlock_source_informed():
    source_informed = {
        row["deck_name"]
        for row in _matrix_rows()
        if row["fixture_stage"] == "source_informed_valid_fixture"
    }

    assert source_informed == {"Kingslayer", "Boarlock"}


def test_active_operator_docs_do_not_claim_seven_source_informed_rows():
    text = OPERATOR_README.read_text(encoding="utf-8")

    assert "seven `source_informed_valid_fixture` rows" not in text
    assert "Kingslayer" in text
    assert "Boarlock" in text
```

- [ ] **Step 2: Run the new test and verify it fails**

Run:

```powershell
python -m pytest tests/test_matrix_current_truth.py -q
```

Expected before the doc edit: one failure from stale `docs/operator/README.md` wording.

- [ ] **Step 3: Update the active operator wording**

In `docs/operator/README.md`, replace:

```markdown
Do not add a new representative deck when an existing row can exercise the same source-depth or runtime-surface family. Improve the seven `source_informed_valid_fixture` rows before widening the matrix.
```

with:

```markdown
Do not add a new representative deck when an existing row can exercise the same source-depth or runtime-surface family. Close the current Kingslayer and Boarlock `source_informed_valid_fixture` rows before widening the matrix.
```

- [ ] **Step 4: Run the guardrail test again**

Run:

```powershell
python -m pytest tests/test_matrix_current_truth.py -q
```

Expected: `2 passed`.

- [ ] **Step 5: Commit Task 1**

```powershell
git add docs/operator/README.md tests/test_matrix_current_truth.py
git commit -m "docs: align HSConfig matrix closure guidance"
```

---

### Task 2: Add A Focused Research-Deep Package For The Two Mulligan Gaps

**Files:**
- Create: `docs/research/2026-07-08-hsconfig-kingslayer-boarlock-mulligan-closure/fields.yaml`
- Create: `docs/research/2026-07-08-hsconfig-kingslayer-boarlock-mulligan-closure/outline.yaml`
- Create: `docs/research/2026-07-08-hsconfig-kingslayer-boarlock-mulligan-closure/results/*.json` through research-deep execution
- Test: `python C:\Users\darbo\.codex\skills\research\validate_json.py ...`

**Interfaces:**
- Consumes: Current matrix gaps from `docs/operator/source-backed-strong-closure.md`.
- Produces: Validated JSON research outputs that either allow or block source-backed promotion for `DEEP_014` Quick Pick and `WW_092` Fracking.

- [ ] **Step 1: Create the research fields file**

Create `docs/research/2026-07-08-hsconfig-kingslayer-boarlock-mulligan-closure/fields.yaml`:

```yaml
source_urls:
  type: list
  description: Public URLs checked for this Mulligan claim.
deck_name:
  type: string
  description: HSConfig fixture deck name.
target_card_id:
  type: string
  description: Hearthstone card ID that currently blocks source-backed promotion.
target_card_name:
  type: string
  description: Human-readable card name for the blocking card.
claim_kind:
  type: string
  description: Expected HSConfig claim kind, usually mulligan_keep or mulligan_discard.
recommended_claim:
  type: object
  description: Concrete claim fields to copy into source_documents when promotion is source-backed.
evidence_text_short:
  type: string
  description: Short source-backed evidence sentence, not a paraphrase invented from deck intuition.
source_confidence:
  type: string
  description: high, medium, low, or blocked.
promotion_allowed:
  type: boolean
  description: True only when source evidence explicitly supports a keep or discard claim for the target card.
block_reason:
  type: string
  description: Reason promotion is blocked when promotion_allowed is false.
uncertain:
  type: list
  description: Field names whose values remain uncertain.
```

- [ ] **Step 2: Create the research outline**

Create `docs/research/2026-07-08-hsconfig-kingslayer-boarlock-mulligan-closure/outline.yaml`:

```yaml
topic: hsconfig-kingslayer-boarlock-mulligan-closure-2026-07-08
execution:
  output_dir: C:\Users\darbo\Documents\HSConfig\docs\research\2026-07-08-hsconfig-kingslayer-boarlock-mulligan-closure\results
  batch_size: 2
  items_per_agent: 1
items:
  - name: Kingslayer Quick Pick Mulligan Closure
    category: HSConfig source-depth closure
    description: >
      Research whether current public Kingsbane/Kingslayer Rogue guide, deck, mulligan,
      or matchup sources explicitly support keeping or discarding Quick Pick (DEEP_014)
      in the Mulligan for the provided Kingslayer deck. Promotion is allowed only if a
      source explicitly supports the card-level Mulligan choice.
  - name: Boarlock Fracking Mulligan Closure
    category: HSConfig source-depth closure
    description: >
      Research whether current public Boarlock, Elwynn Boar Warlock, combo Warlock,
      or mulligan sources explicitly support keeping or discarding Fracking (WW_092)
      in the Mulligan for the provided Boarlock deck. Promotion is allowed only if a
      source explicitly supports the card-level Mulligan choice.
```

- [ ] **Step 3: Run research-deep**

Use the `research-deep` skill from `C:\Users\darbo\Documents\HSConfig` with the new outline as the active outline. Ensure both output JSON files exist under:

```text
docs/research/2026-07-08-hsconfig-kingslayer-boarlock-mulligan-closure/results/
```

Each JSON must validate with:

```powershell
python C:\Users\darbo\.codex\skills\research\validate_json.py `
  -f docs\research\2026-07-08-hsconfig-kingslayer-boarlock-mulligan-closure\fields.yaml `
  -j docs\research\2026-07-08-hsconfig-kingslayer-boarlock-mulligan-closure\results\Kingslayer_Quick_Pick_Mulligan_Closure.json

python C:\Users\darbo\.codex\skills\research\validate_json.py `
  -f docs\research\2026-07-08-hsconfig-kingslayer-boarlock-mulligan-closure\fields.yaml `
  -j docs\research\2026-07-08-hsconfig-kingslayer-boarlock-mulligan-closure\results\Boarlock_Fracking_Mulligan_Closure.json
```

Expected: both validations pass.

- [ ] **Step 4: Commit Task 2**

```powershell
git add docs/research/2026-07-08-hsconfig-kingslayer-boarlock-mulligan-closure
git commit -m "docs: research remaining HSConfig mulligan closure gaps"
```

---

### Task 3: Close Or Explicitly Preserve The Kingslayer Quick Pick Gap

**Files:**
- Modify: `tests/fixtures/source_documents_kingslayer_strong.json`
- Modify: `tests/test_fixture_source_depth_closure.py`
- Modify: `tests/test_matrix_visibility.py` later only if promotion succeeds
- Test: `tests/test_fixture_source_depth_closure.py`, `tests/test_strong_fixture_closure.py`

**Interfaces:**
- Consumes: `docs/research/2026-07-08-hsconfig-kingslayer-boarlock-mulligan-closure/results/Kingslayer_Quick_Pick_Mulligan_Closure.json`.
- Produces: Either a promoted Kingslayer fixture or a deliberately preserved source-informed row with a stronger block reason.

- [ ] **Step 1: Make source-informed row testing matrix-derived**

In `tests/test_fixture_source_depth_closure.py`, replace the hard-coded `SOURCE_INFORMED_DECKS` set and parametrization with matrix-derived rows:

```python
def _source_informed_rows():
    return [
        row
        for row in load_archetype_matrix()
        if row["fixture_stage"] == "source_informed_valid_fixture"
    ]


@pytest.mark.parametrize(
    "deck",
    _source_informed_rows(),
    ids=lambda row: row["deck_name"],
)
def test_source_informed_rows_have_actionable_closure_chain(tmp_path, monkeypatch, deck):
    monkeypatch.setattr("hsconfig.cli.fetch_latest_cards", lambda timeout=10.0: [])

    result = prepare_fixture_deck(tmp_path, deck)
    operator = result["operator"]
    gap_report = result["source_claim_gap_report"]
    promotion = result["strong_promotion_report"]

    assert result["exit_code"] == 0
    assert operator["technical_status"] == "VALID_PACKAGE"
    assert "Presume.json" not in result["generated_files"]
    assert "Concede.json" not in result["generated_files"]

    if promotion["promotion_ready"]:
        assert operator["semantic_status"] == "SOURCE_BACKED_STRONG"
        assert operator["next_action"] == "READY_TO_APPLY_OR_HANDOFF"
        assert gap_report["summary"]["blocked_cards"] == 0
        assert gap_report["summary"]["first_missing_chain"] is None
    else:
        chain = gap_report["summary"]["first_missing_chain"]
        assert operator["semantic_status"] == "VALID_BUT_NOT_GUIDE_STRONG"
        assert gap_report["summary"]["blocked_cards"] > 0
        assert isinstance(chain, dict)
        assert chain["card_id"]
        assert chain["first_missing_link"] in {
            "needs_guide_claim",
            "needs_runtime_surface",
            "needs_mulligan_claim",
            "needs_combo_sequence",
            "needs_condition_lowering",
            "needs_mechanic_lowering",
        }
        assert chain["next_action"]
```

Keep the existing specific strong-regression tests for decks that are already proven strong.

- [ ] **Step 2: Run current fixture tests**

Run:

```powershell
python -m pytest tests/test_fixture_source_depth_closure.py -q
```

Expected before source update: current behavior still passes because Kingslayer and Boarlock remain actionable source-informed rows.

- [ ] **Step 3: If research allows promotion, update the Quick Pick claim**

Open `docs/research/2026-07-08-hsconfig-kingslayer-boarlock-mulligan-closure/results/Kingslayer_Quick_Pick_Mulligan_Closure.json`.

If and only if `promotion_allowed` is `true` and `source_confidence` is `medium` or `high`, update the existing `mulligan_keep` claim for `DEEP_014` in `tests/fixtures/source_documents_kingslayer_strong.json` with the exact `recommended_claim` object from the validated research JSON. Use this merge shape:

```python
from pathlib import Path
import json

research_path = Path(
    "docs/research/2026-07-08-hsconfig-kingslayer-boarlock-mulligan-closure/results/"
    "Kingslayer_Quick_Pick_Mulligan_Closure.json"
)
fixture_path = Path("tests/fixtures/source_documents_kingslayer_strong.json")

research = json.loads(research_path.read_text(encoding="utf-8"))
assert research["promotion_allowed"] is True
assert research["source_confidence"] in {"medium", "high"}
recommended = research["recommended_claim"]
assert recommended["claim_kind"] in {"mulligan_keep", "mulligan_discard"}
assert recommended["cards"] == ["DEEP_014"]
assert recommended["selector"] == "DEEP_014"
assert recommended["selector_kind"] == "card"
assert recommended["source_confidence"] in {"medium", "high"}
assert recommended["evidence_text_short"]
assert recommended["source_refs"]

data = json.loads(fixture_path.read_text(encoding="utf-8"))
for document in data["source_documents"]:
    for index, claim in enumerate(document.get("claims", [])):
        if claim.get("claim_kind") == "mulligan_keep" and claim.get("cards") == ["DEEP_014"]:
            document["claims"][index] = recommended
            fixture_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            raise SystemExit(0)
raise SystemExit("DEEP_014 mulligan claim not found")
```

If `promotion_allowed` is `false`, do not edit the fixture claim to appear stronger. Leave Kingslayer source-informed and update only the closure docs in Task 5 with the validated `block_reason`.

- [ ] **Step 4: Run Kingslayer prepare proof**

Run:

```powershell
python -m pytest tests/test_fixture_source_depth_closure.py tests/test_strong_fixture_closure.py -k Kingslayer -q
```

Expected if research allowed promotion and the fixture update is correct: Kingslayer can be moved to core in Task 5. Expected if research blocked promotion: Kingslayer remains `VALID_BUT_NOT_GUIDE_STRONG` with the same first missing chain.

- [ ] **Step 5: Commit Task 3**

If Kingslayer fixture changed:

```powershell
git add tests/fixtures/source_documents_kingslayer_strong.json tests/test_fixture_source_depth_closure.py
git commit -m "test: close Kingslayer mulligan source gap"
```

If only matrix-derived test cleanup changed:

```powershell
git add tests/test_fixture_source_depth_closure.py
git commit -m "test: derive source-informed fixtures from matrix"
```

---

### Task 4: Close Or Explicitly Preserve The Boarlock Fracking Gap

**Files:**
- Modify: `tests/fixtures/source_documents_boarlock_strong.json`
- Test: `tests/test_fixture_source_depth_closure.py`, `tests/test_strong_fixture_closure.py`

**Interfaces:**
- Consumes: `docs/research/2026-07-08-hsconfig-kingslayer-boarlock-mulligan-closure/results/Boarlock_Fracking_Mulligan_Closure.json`.
- Produces: Either a promoted Boarlock fixture or a deliberately preserved source-informed row with a stronger block reason.

- [ ] **Step 1: If research allows promotion, update the Fracking claim**

Open `docs/research/2026-07-08-hsconfig-kingslayer-boarlock-mulligan-closure/results/Boarlock_Fracking_Mulligan_Closure.json`.

If and only if `promotion_allowed` is `true` and `source_confidence` is `medium` or `high`, update the existing `mulligan_keep` claim for `WW_092` in `tests/fixtures/source_documents_boarlock_strong.json` with the exact `recommended_claim` object from the validated research JSON. Use this merge shape:

```python
from pathlib import Path
import json

research_path = Path(
    "docs/research/2026-07-08-hsconfig-kingslayer-boarlock-mulligan-closure/results/"
    "Boarlock_Fracking_Mulligan_Closure.json"
)
fixture_path = Path("tests/fixtures/source_documents_boarlock_strong.json")

research = json.loads(research_path.read_text(encoding="utf-8"))
assert research["promotion_allowed"] is True
assert research["source_confidence"] in {"medium", "high"}
recommended = research["recommended_claim"]
assert recommended["claim_kind"] in {"mulligan_keep", "mulligan_discard"}
assert recommended["cards"] == ["WW_092"]
assert recommended["selector"] == "WW_092"
assert recommended["selector_kind"] == "card"
assert recommended["source_confidence"] in {"medium", "high"}
assert recommended["evidence_text_short"]
assert recommended["source_refs"]

data = json.loads(fixture_path.read_text(encoding="utf-8"))
for document in data["source_documents"]:
    for index, claim in enumerate(document.get("claims", [])):
        if claim.get("claim_kind") == "mulligan_keep" and claim.get("cards") == ["WW_092"]:
            document["claims"][index] = recommended
            fixture_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            raise SystemExit(0)
raise SystemExit("WW_092 mulligan claim not found")
```

If `promotion_allowed` is `false`, do not edit the fixture claim to appear stronger. Leave Boarlock source-informed and update only the closure docs in Task 5 with the validated `block_reason`.

- [ ] **Step 2: Preserve the exact Combo.json boundary**

Verify that Boarlock remains the only matrix row with `Combo.json` in `expected_runtime_surfaces`.

Run:

```powershell
python - <<'PY'
import json
from pathlib import Path
matrix = json.loads(Path("docs/operator/archetype-fixture-matrix.json").read_text(encoding="utf-8"))
combo_decks = [row["deck_name"] for row in matrix["decks"] if "Combo.json" in row["expected_runtime_surfaces"]]
assert combo_decks == ["Boarlock"], combo_decks
print("combo surface boundary ok")
PY
```

Expected: `combo surface boundary ok`.

- [ ] **Step 3: Run Boarlock prepare proof**

Run:

```powershell
python -m pytest tests/test_fixture_source_depth_closure.py tests/test_strong_fixture_closure.py -k Boarlock -q
```

Expected if research allowed promotion and the fixture update is correct: Boarlock can be moved to core in Task 5. Expected if research blocked promotion: Boarlock remains `VALID_BUT_NOT_GUIDE_STRONG` with the same first missing chain.

- [ ] **Step 4: Commit Task 4**

If Boarlock fixture changed:

```powershell
git add tests/fixtures/source_documents_boarlock_strong.json
git commit -m "test: close Boarlock mulligan source gap"
```

If no fixture changed, skip this commit and preserve the research-result commit from Task 2 as the evidence.

---

### Task 5: Update Matrix Truth, Closure Docs, And Stale Research Warnings

**Files:**
- Modify: `docs/operator/archetype-fixture-matrix.json`
- Modify: `docs/operator/source-backed-strong-closure.md`
- Modify: `docs/operator/README.md`
- Create or modify: `docs/research/2026-07-08-hsconfig-skill-operability-audit/README.md`
- Modify tests that assert matrix counts if promotion succeeds.

**Interfaces:**
- Consumes: Results from Tasks 3 and 4.
- Produces: One active matrix truth and clear historical warning for stale research result files.

- [ ] **Step 1: Promote only fixtures that proved strong**

For each deck that now proves `SOURCE_BACKED_STRONG`, update `docs/operator/archetype-fixture-matrix.json`:

```json
"fixture_stage": "core_source_backed_fixture",
"strongness_visibility": {
  "current_stage": "core_source_backed_fixture",
  "first_strongness_gap": "none",
  "operator_action": "keep_as_core_control_fixture"
}
```

For Kingslayer, remove the `first_missing_chain:DEEP_014:Quick Pick:needs_mulligan_claim` known limit only if promotion succeeded. Preserve `does_not_cover_reactive_control`.

For Boarlock, remove the `first_missing_chain:WW_092:Fracking:needs_mulligan_claim` known limit only if promotion succeeded. Preserve `single_combo_fixture_only`.

- [ ] **Step 2: Update the closure tables**

In `docs/operator/source-backed-strong-closure.md`, update the two affected rows:

If both promoted, the Current Closure Targets rows become:

```markdown
| Kingslayer | `core_source_backed_fixture` | Promotion proven. Keep as a core control fixture for weapon sequencing and attack pressure. |
| Boarlock | `core_source_backed_fixture` | Promotion proven. Keep as the exact combo-control fixture with `Combo.json` coverage. |
```

If only one promoted, update only the promoted row and keep the other row source-informed with the validated `block_reason` from Task 2.

Update the Current Blocker Snapshot to match the proven prepare results.

- [ ] **Step 3: Update active operator next-action wording**

In `docs/operator/README.md`, if both decks promoted, replace the final Fixture Matrix paragraph with:

```markdown
Do not add a new representative deck when an existing row can exercise the same source-depth or runtime-surface family. The current 11-deck proof set is closed for HSConfig's pre-run scope; add a new representative deck only when it covers a genuinely missing family such as reactive control or a discover-heavy decision chain.
```

If one or both remain source-informed, name only the remaining deck names in that paragraph.

- [ ] **Step 4: Mark the old research audit as superseded where counts differ**

Create `docs/research/2026-07-08-hsconfig-skill-operability-audit/README.md`:

```markdown
# HSConfig Skill Operability Audit 2026-07-08

This research package is historical evidence for the HSConfig skill audit.

Authoritative current matrix state lives in:

- `docs/operator/archetype-fixture-matrix.json`
- `docs/operator/source-backed-strong-closure.md`

Some result files in this folder were generated before later matrix promotions.
When fixture counts differ, use the active operator files above as the current
truth and treat these result JSON files as superseded research snapshots.
```

- [ ] **Step 5: Update count assertions after promotion**

If all 11 decks are now core source-backed, update `tests/test_matrix_visibility.py`:

```python
assert report["core_source_backed_fixture_count"] == 11
assert report["source_informed_valid_fixture_count"] == 0
assert report["normal_next_action"] == "keep_closed_matrix_until_new_family_is_needed"
```

Then update `src/hsconfig/matrix_visibility.py` so `normal_next_action` returns:

```python
"keep_closed_matrix_until_new_family_is_needed"
```

when there are zero source-informed rows, and otherwise returns the existing:

```python
"close_existing_source_informed_rows_before_adding_more_decks"
```

If one or both decks remain source-informed, keep the current count assertions aligned with the live matrix.

- [ ] **Step 6: Run matrix/doc tests**

Run:

```powershell
python -m pytest `
  tests/test_matrix_current_truth.py `
  tests/test_matrix_visibility.py `
  tests/test_source_depth_closure_index.py `
  tests/test_fixture_source_depth_closure.py `
  tests/test_strong_fixture_closure.py `
  tests/test_skill_files.py `
  -q
```

Expected: all selected tests pass.

- [ ] **Step 7: Commit Task 5**

```powershell
git add docs/operator docs/research/2026-07-08-hsconfig-skill-operability-audit tests src/hsconfig
git commit -m "docs: refresh HSConfig matrix closure truth"
```

---

### Task 6: Final Verification, Skill Sync, And Git Hygiene

**Files:**
- Modify only if verification exposes a defect.
- Test: full repository verification.

**Interfaces:**
- Consumes: All prior task changes.
- Produces: A clean branch ready for push/merge with a verified HSConfig matrix truth.

- [ ] **Step 1: Run focused source-depth closure tests**

```powershell
python -m pytest `
  tests/test_fixture_source_depth_closure.py `
  tests/test_strong_fixture_closure.py `
  tests/test_archetype_fixture_matrix.py `
  tests/test_archetype_source_fixtures.py `
  tests/test_archetype_fixture_e2e.py `
  tests/test_matrix_visibility.py `
  tests/test_matrix_closure.py `
  tests/test_source_depth_closure_index.py `
  tests/test_matrix_current_truth.py `
  -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run scope and skill tests**

```powershell
python -m pytest `
  tests/test_scope_boundaries.py `
  tests/test_skill_files.py `
  tests/test_skill_sync.py `
  tests/test_cli_help.py `
  -q
```

Expected: all selected tests pass.

- [ ] **Step 3: Run full suite**

```powershell
python -m pytest -q
```

Expected: full suite passes.

- [ ] **Step 4: Sync installed skill if needed**

Run:

```powershell
python scripts\sync_installed_skill.py --check
```

If it reports drift, run:

```powershell
python scripts\sync_installed_skill.py
python scripts\sync_installed_skill.py --check
```

Expected: `HSConfig skill is in sync: C:\Users\darbo\.codex\skills\hsconfig`.

- [ ] **Step 5: Check for stale active wording**

Run:

```powershell
rg -n "seven `source_informed_valid_fixture` rows|4 core_source_backed_fixture|7 source_informed_valid_fixture" README.md docs\operator .agents\skills\hsconfig src tests
```

Expected: no matches in active operator docs, skill files, source, or tests. Matches under historical `docs/research` or `docs/superpowers/plans` are acceptable only when the file clearly marks itself as historical or superseded.

- [ ] **Step 6: Review git status**

```powershell
git status --short --branch
```

Expected: branch is ahead by the task commits, with no untracked temporary files.

- [ ] **Step 7: Final commit if verification changed anything**

If Step 1-5 required additional fixes:

```powershell
git add .
git commit -m "test: verify HSConfig matrix closure"
```

If no additional files changed, skip this commit.

---

## Acceptance Criteria

- Active docs no longer claim seven source-informed rows.
- Research-deep outputs explicitly support or block the two remaining Mulligan gaps.
- Kingslayer and Boarlock are promoted only if source evidence supports their blocking Mulligan claims.
- The fixture matrix, closure doc, operator README, and tests agree on the same current truth.
- `Presume.json` and `Concede.json` remain blocked in the normal path.
- HSConfig remains pre-run only and does not import HSTuner or HSranger Step-2 logic.
- Focused source-depth tests pass.
- Full `python -m pytest -q` passes.
- Installed HSConfig skill sync check passes.

## Self-Review

- Spec coverage: The plan covers Doku-De-Stale, research-deep hardening, Kingslayer closure, Boarlock closure, matrix truth, active docs, tests, skill sync, and full verification.
- Placeholder scan: The plan avoids open-ended implementation placeholders. Where research output is required, it defines exact validation gates and explicitly forbids invented evidence.
- Type consistency: The plan uses existing matrix fields: `fixture_stage`, `strongness_visibility.current_stage`, `strongness_visibility.first_strongness_gap`, `strongness_visibility.operator_action`, `semantic_status`, `next_action`, and `promotion_ready`.
- Scope check: The plan does not add replay parsing, winrate logic, post-run tuning, new normal runtime surfaces, or unrelated refactors.

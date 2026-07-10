# HSConfig Modern Wild Mechanic Visibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add explicit modern Hearthstone/Wild mechanic visibility for current keywords while preserving HSConfig's no-block load-safe pre-run workflow.

**Architecture:** Keep HSConfig narrow: static deck/card/guide semantics flow into `GlobalValues.json`, `Mulligan.json`, per-card `<CARDID>.json`, and optional `Combo.json`; mechanic gaps remain descriptive, not blocking. Extend the existing `mechanic_support.py` registry and `mechanic_drift.py` detector, then surface the result through `operator_summary.json`, report ownership, active docs, and the installed skill.

**Tech Stack:** Python package under `src/hsconfig`, pytest, HearthstoneJSON-style card metadata, HearthRanger VisionAI CustomConfig files.

## Global Constraints

- Do not add new commands, services, or dependencies.
- Do not add replay, winrate, HDT, HSTuner, candidate-promotion, or post-run tuning behavior to HSConfig.
- Do not emit `Presume.json` or `Concede.json` in the normal path.
- Do not change the runtime write gate: valid load-safe packages remain `runtime_apply_mode=load_safe_apply`.
- Unknown mechanics, text-only mechanics, and unknown card types stay non-blocking.
- New current mechanics must default to `warning_only` unless there is a safe existing VisionAI surface for a partial representation.
- Keep `reports/operator_summary.json` as the single operator gate.
- Keep the representative deck matrix unchanged unless a test proves a missing family that no current row covers.

---

## File Structure

- Modify `src/hsconfig/mechanic_support.py`
  - Owns mechanic support registry, role aliases, visibility buckets, and support summaries.
- Modify `src/hsconfig/mechanic_drift.py`
  - Owns deck-card scoped mechanic drift detection from HearthstoneJSON-style metadata and text patterns.
- Modify `src/hsconfig/operator_summary.py`
  - Owns operator-facing mechanic drift summary fields.
- Modify `src/hsconfig/report_ownership.py`
  - Owns machine-readable report ownership used by `operator_summary.json`.
- Modify `tests/test_mechanic_support.py`
  - Tests registry support and no-block visibility buckets.
- Modify `tests/test_mechanic_drift.py`
  - Tests text-only detection and unknown-card-type behavior.
- Modify `tests/test_operator_summary.py`
  - Tests `mechanic_drift_summary` operator fields.
- Modify `tests/test_report_ownership.py`
  - Tests the report ownership table includes current mechanic drift and semantic enrichment diagnostics.
- Modify `tests/test_skill_files.py`
  - Tests active docs and skill wording for the new visibility wave.
- Modify `docs/operator/README.md`
  - Keeps the normal operator path and report table aligned with code.
- Modify `docs/operator/universal-wild-no-block-contract.md`
  - Documents current modern mechanics as warning/partial visibility, not runtime blockers.
- Modify `.agents/skills/hsconfig/SKILL.md`
  - Keeps installed-skill source current.
- Modify `.agents/skills/hsconfig/references/workflow.md`
  - Keeps skill reference workflow aligned with the operator guide.
- Run `scripts/sync_installed_skill.py`
  - Copies the repo skill to `C:\Users\darbo\.codex\skills\hsconfig`.

---

### Task 1: Register Modern Wild Mechanics Without Adding Blockers

**Files:**
- Modify: `tests/test_mechanic_support.py`
- Modify: `src/hsconfig/mechanic_support.py`

**Interfaces:**
- Consumes: `support_for_roles(roles: Iterable[str]) -> list[dict[str, Any]]`
- Consumes: `operator_visibility_bucket(support: dict[str, Any]) -> str`
- Produces: registry entries for `kindred`, `tourist`, `starship`, `spellburst`, `miniaturize`, `quickdraw`, `honorable_kill`, `elusive`, `poisonous`, and `imbue`
- Produces: role aliases for common spelling variants such as `spell_burst`, `honorablekill`, `starship_piece`, `starship_launch`, and `hero_power_imbue`

- [ ] **Step 1: Write the failing registry test**

Add this test to `tests/test_mechanic_support.py`:

```python
def test_current_modern_wild_mechanics_are_registered_without_blocking():
    rows = support_for_roles(
        [
            "kindred",
            "tourist",
            "starship",
            "spellburst",
            "spell_burst",
            "miniaturize",
            "quickdraw",
            "honorable_kill",
            "honorablekill",
            "elusive",
            "poisonous",
            "imbue",
            "hero_power_imbue",
        ]
    )
    by_mechanic = {row["mechanic"]: row for row in rows}

    expected = {
        "kindred": "warning_only",
        "tourist": "warning_only",
        "starship": "warning_only",
        "spellburst": "partial",
        "miniaturize": "partial",
        "quickdraw": "partial",
        "honorable_kill": "partial",
        "elusive": "partial",
        "poisonous": "partial",
        "imbue": "partial",
    }

    assert set(by_mechanic) == set(expected)
    for mechanic, support_level in expected.items():
        assert by_mechanic[mechanic]["support_level"] == support_level
        assert by_mechanic[mechanic].get("registered", True) is True
        if support_level == "warning_only":
            assert by_mechanic[mechanic]["normal_path_surfaces"] == ["report-only"]
            assert operator_visibility_bucket(by_mechanic[mechanic]) == "warning_only"
```

- [ ] **Step 2: Run the failing test**

Run:

```powershell
python -m pytest tests/test_mechanic_support.py::test_current_modern_wild_mechanics_are_registered_without_blocking -q
```

Expected: FAIL because at least one of the new mechanics is missing or `registered=false`.

- [ ] **Step 3: Add registry entries**

In `src/hsconfig/mechanic_support.py`, add these entries inside `MECHANIC_SUPPORT` near the other future/current mechanics:

```python
    "kindred": {
        "support_level": "warning_only",
        "normal_path_surfaces": ["report-only"],
        "warning_boundary": "Kindred depends on prior card-type sequencing; no documented normal-path VisionAI state surface exists.",
    },
    "tourist": {
        "support_level": "warning_only",
        "normal_path_surfaces": ["report-only"],
        "warning_boundary": "Tourist is primarily deck-construction identity; it has no separate normal-path runtime action surface.",
    },
    "starship": {
        "support_level": "warning_only",
        "normal_path_surfaces": ["report-only"],
        "warning_boundary": "Starship build and launch choices have no documented normal-path VisionAI runtime block.",
    },
    "spellburst": {
        "support_level": "partial",
        "normal_path_surfaces": ["CARDID.json:BeforePlayCardBonus"],
        "warning_boundary": "Spellburst setup can be encouraged through timing; exact one-time trigger state remains broader bot evaluation.",
    },
    "miniaturize": {
        "support_level": "partial",
        "normal_path_surfaces": ["CARDID.json:BeforePlayCardBonus", "CARDID.json:resolved_identity"],
        "warning_boundary": "The original card timing can be encouraged; generated mini-copy sequencing remains source-dependent.",
    },
    "quickdraw": {
        "support_level": "partial",
        "normal_path_surfaces": ["CARDID.json:BeforePlayCardBonus"],
        "warning_boundary": "Quickdraw timing can be encouraged, but drawn-this-turn state is not a dedicated normal-path surface.",
    },
    "honorable_kill": {
        "support_level": "partial",
        "normal_path_surfaces": ["CARDID.json:BeforePhysicalAttackBonus", "CARDID.json:BeforePlayCardBonus"],
        "warning_boundary": "Honorable Kill can influence attack or play posture; exact lethal-damage equality remains broader bot evaluation.",
    },
    "elusive": {
        "support_level": "partial",
        "normal_path_surfaces": ["CARDID.json:OnBoardBonus", "GlobalValues.json:survivability_posture"],
        "warning_boundary": "Elusive is represented as board/survivability value, not as a dedicated targeting planner.",
    },
    "poisonous": {
        "support_level": "partial",
        "normal_path_surfaces": ["CARDID.json:BeforePhysicalAttackBonus", "CARDID.json:OnBoardBonus"],
        "warning_boundary": "Poisonous can affect attack posture; exact trade selection remains broader bot evaluation.",
    },
    "imbue": {
        "support_level": "partial",
        "normal_path_surfaces": ["GlobalValues.json:deck_posture", "CARDID.json:BeforeUseHeroPowerBonus"],
        "warning_boundary": "Imbue and upgraded Hero Power posture can be encouraged; exact upgrade state remains broader bot evaluation.",
    },
```

Also extend `ROLE_ALIASES` with:

```python
    "spell_burst": "spellburst",
    "honorablekill": "honorable_kill",
    "honorable_kill": "honorable_kill",
    "starship_piece": "starship",
    "starship_launch": "starship",
    "hero_power_imbue": "imbue",
```

- [ ] **Step 4: Run mechanic support tests**

Run:

```powershell
python -m pytest tests/test_mechanic_support.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit Task 1**

```powershell
git add src/hsconfig/mechanic_support.py tests/test_mechanic_support.py
git commit -m "feat: register modern wild mechanics as non-blocking"
```

---

### Task 2: Detect Modern Mechanics From HearthstoneJSON-Style Text And Metadata

**Files:**
- Modify: `tests/test_mechanic_drift.py`
- Modify: `src/hsconfig/mechanic_drift.py`

**Interfaces:**
- Consumes: `build_mechanic_drift_report(cards: Iterable[dict[str, Any]]) -> dict[str, Any]`
- Consumes: `TEXT_MECHANIC_PATTERNS`
- Produces: text-only detection for modern mechanics
- Produces: `starship` as a known current card type while preserving unknown-type warnings for future/mode-only types

- [ ] **Step 1: Write failing text-pattern test**

Add this test to `tests/test_mechanic_drift.py`:

```python
def test_mechanic_drift_detects_modern_text_only_mechanics_without_blocking():
    report = build_mechanic_drift_report(
        [
            {"id": "KINDRED_001", "type": "MINION", "mechanics": [], "referencedTags": [], "text": "Kindred: Deal 2 damage."},
            {"id": "TOURIST_001", "type": "MINION", "mechanics": [], "referencedTags": [], "text": "Tourist. Your deck can include Paladin cards."},
            {"id": "STARSHIP_001", "type": "STARSHIP", "mechanics": [], "referencedTags": [], "text": "Launch your Starship."},
            {"id": "SPELLBURST_001", "type": "MINION", "mechanics": [], "referencedTags": [], "text": "Spellburst: Summon a 1/1."},
            {"id": "MINI_001", "type": "MINION", "mechanics": [], "referencedTags": [], "text": "Miniaturize."},
            {"id": "QUICK_001", "type": "SPELL", "mechanics": [], "referencedTags": [], "text": "Quickdraw: Costs (1) less."},
            {"id": "HONOR_001", "type": "MINION", "mechanics": [], "referencedTags": [], "text": "Honorable Kill: Draw a card."},
            {"id": "ELUSIVE_001", "type": "MINION", "mechanics": [], "referencedTags": [], "text": "Elusive."},
            {"id": "POISON_001", "type": "MINION", "mechanics": [], "referencedTags": [], "text": "Poisonous."},
            {"id": "IMBUE_001", "type": "SPELL", "mechanics": [], "referencedTags": [], "text": "Imbue your Hero Power."},
        ]
    )

    assert report["non_blocking"] is True
    assert report["unknown_card_types"] == []
    assert report["unknown_mechanics"] == []
    assert report["text_only_mechanics"] == [
        "elusive",
        "honorable_kill",
        "imbue",
        "kindred",
        "miniaturize",
        "poisonous",
        "quickdraw",
        "spellburst",
        "starship",
        "tourist",
    ]
    assert report["support_by_mechanic"]["starship"]["support_level"] == "warning_only"
    assert report["support_by_mechanic"]["spellburst"]["support_level"] == "partial"
```

- [ ] **Step 2: Update unknown-card-type regression test**

In `tests/test_mechanic_drift.py`, change the future type in `test_mechanic_drift_reports_unknown_card_types_without_blocking` from `STARSHIP` to `LETTUCE_ABILITY`:

```python
{
    "id": "FUTURE_TYPE_001",
    "name": "Future Type Card",
    "type": "LETTUCE_ABILITY",
    "mechanics": [],
    "referencedTags": [],
    "text": "A future card type.",
}
```

Update expected assertions:

```python
assert report["card_types"] == ["lettuce_ability"]
assert report["unknown_card_types"] == ["lettuce_ability"]
```

- [ ] **Step 3: Run failing drift tests**

Run:

```powershell
python -m pytest tests/test_mechanic_drift.py -q
```

Expected: FAIL because the modern text patterns and `starship` card type are not registered yet.

- [ ] **Step 4: Add current card type and text patterns**

In `src/hsconfig/mechanic_drift.py`, add `starship` to `KNOWN_CARD_TYPES`:

```python
    "starship",
```

Add these entries to `TEXT_MECHANIC_PATTERNS`:

```python
    "kindred": ("kindred",),
    "tourist": ("tourist",),
    "starship": ("starship", "launch your starship"),
    "spellburst": ("spellburst",),
    "miniaturize": ("miniaturize", "miniaturized"),
    "quickdraw": ("quickdraw",),
    "honorable_kill": ("honorable kill",),
    "elusive": (
        "elusive",
        "can't be targeted by spells or hero powers",
        "cant be targeted by spells or hero powers",
    ),
    "poisonous": ("poisonous",),
    "imbue": ("imbue", "imbued"),
```

- [ ] **Step 5: Run mechanic drift tests**

Run:

```powershell
python -m pytest tests/test_mechanic_drift.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit Task 2**

```powershell
git add src/hsconfig/mechanic_drift.py tests/test_mechanic_drift.py
git commit -m "feat: detect modern mechanic drift without blocking"
```

---

### Task 3: Make Mechanic Drift More Actionable In Operator Summary And Report Ownership

**Files:**
- Modify: `tests/test_operator_summary.py`
- Modify: `tests/test_report_ownership.py`
- Modify: `src/hsconfig/operator_summary.py`
- Modify: `src/hsconfig/report_ownership.py`

**Interfaces:**
- Consumes: `build_operator_summary(...) -> dict[str, Any]`
- Consumes: `build_report_ownership() -> list[dict[str, Any]]`
- Produces: `mechanic_drift_summary.first_unknown_mechanic`
- Produces: `mechanic_drift_summary.first_text_only_mechanic`
- Produces: `mechanic_drift_summary.first_unknown_card_type`
- Produces: `mechanic_drift_summary.next_report_to_open`
- Produces: report ownership rows for both `mechanic_drift_report.json` and `semantic_enrichment_report.json`

- [ ] **Step 1: Write failing operator summary test**

Add this test to `tests/test_operator_summary.py`:

```python
from hsconfig.operator_summary import build_operator_summary


def test_operator_summary_names_first_mechanic_drift_followup():
    summary = build_operator_summary(
        deck_name="MechanicTest",
        deck_code="AAEBAfake",
        technical_validation={"status": "passed"},
        guide_source_depth={"source_depth_status": "static_semantics_only", "claim_count": 1},
        mechanic_drift_report={
            "non_blocking": True,
            "unknown_mechanics": ["future_keyword"],
            "text_only_mechanics": ["kindred", "starship"],
            "unknown_card_types": ["lettuce_ability"],
            "summary": {
                "mechanic_count": 3,
                "unknown_mechanic_count": 1,
                "text_only_mechanic_count": 2,
                "unknown_card_type_count": 1,
            },
        },
    )

    drift = summary["mechanic_drift_summary"]
    assert drift["non_blocking"] is True
    assert drift["first_unknown_mechanic"] == "future_keyword"
    assert drift["first_text_only_mechanic"] == "kindred"
    assert drift["first_unknown_card_type"] == "lettuce_ability"
    assert drift["next_report_to_open"] == "reports/mechanic_drift_report.json"
```

If `tests/test_operator_summary.py` already imports `build_operator_summary`, only add the test body.

- [ ] **Step 2: Write failing report ownership test**

Update `tests/test_report_ownership.py`:

```python
def test_report_ownership_includes_mechanic_diagnostics():
    rows = build_report_ownership()
    by_file = {row["file"]: row for row in rows}

    assert by_file["reports/mechanic_drift_report.json"]["authority"] == "non_blocking_mechanic_drift_visibility"
    assert by_file["reports/mechanic_drift_report.json"]["open_order"] == "7"
    assert by_file["reports/semantic_enrichment_report.json"]["authority"] == "semantic_mechanic_diagnostics"
    assert by_file["reports/semantic_enrichment_report.json"]["open_order"] == "8"
```

- [ ] **Step 3: Run failing tests**

Run:

```powershell
python -m pytest tests/test_operator_summary.py::test_operator_summary_names_first_mechanic_drift_followup tests/test_report_ownership.py::test_report_ownership_includes_mechanic_diagnostics -q
```

Expected: FAIL because the new summary fields and semantic enrichment ownership row do not exist yet.

- [ ] **Step 4: Extend `_mechanic_drift_summary`**

In `src/hsconfig/operator_summary.py`, replace `_mechanic_drift_summary` with this shape while preserving the existing count/list fields:

```python
def _mechanic_drift_summary(report: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(report, dict):
        return {
            "non_blocking": True,
            "mechanic_count": 0,
            "unknown_mechanic_count": 0,
            "text_only_mechanic_count": 0,
            "unknown_card_type_count": 0,
            "unknown_mechanics": [],
            "text_only_mechanics": [],
            "unknown_card_types": [],
            "first_unknown_mechanic": None,
            "first_text_only_mechanic": None,
            "first_unknown_card_type": None,
            "next_report_to_open": None,
        }
    summary = report.get("summary", {})
    if not isinstance(summary, dict):
        summary = {}
    unknown_mechanics = [str(item) for item in report.get("unknown_mechanics", [])]
    text_only_mechanics = [str(item) for item in report.get("text_only_mechanics", [])]
    unknown_card_types = [str(item) for item in report.get("unknown_card_types", [])]
    has_followup = bool(unknown_mechanics or text_only_mechanics or unknown_card_types)
    return {
        "non_blocking": bool(report.get("non_blocking", True)),
        "mechanic_count": _int_value(summary.get("mechanic_count", 0)),
        "unknown_mechanic_count": _int_value(summary.get("unknown_mechanic_count", 0)),
        "text_only_mechanic_count": _int_value(summary.get("text_only_mechanic_count", 0)),
        "unknown_card_type_count": _int_value(summary.get("unknown_card_type_count", 0)),
        "unknown_mechanics": unknown_mechanics,
        "text_only_mechanics": text_only_mechanics,
        "unknown_card_types": unknown_card_types,
        "first_unknown_mechanic": unknown_mechanics[0] if unknown_mechanics else None,
        "first_text_only_mechanic": text_only_mechanics[0] if text_only_mechanics else None,
        "first_unknown_card_type": unknown_card_types[0] if unknown_card_types else None,
        "next_report_to_open": "reports/mechanic_drift_report.json" if has_followup else None,
    }
```

- [ ] **Step 5: Extend report ownership**

In `src/hsconfig/report_ownership.py`, keep the existing `mechanic_drift_report.json` row and append this row after it:

```python
        {
            "file": "reports/semantic_enrichment_report.json",
            "producer": "prepare",
            "authority": "semantic_mechanic_diagnostics",
            "open_when": (
                "mechanic_visibility_summary or config_usefulness points to static, "
                "partial, or warning-only mechanic coverage"
            ),
            "open_order": "8",
        },
```

- [ ] **Step 6: Run targeted operator/report tests**

Run:

```powershell
python -m pytest tests/test_operator_summary.py tests/test_report_ownership.py -q
```

Expected: all tests pass.

- [ ] **Step 7: Commit Task 3**

```powershell
git add src/hsconfig/operator_summary.py src/hsconfig/report_ownership.py tests/test_operator_summary.py tests/test_report_ownership.py
git commit -m "feat: expose actionable mechanic drift followups"
```

---

### Task 4: Align Active Docs And Installed Skill With The New Visibility Contract

**Files:**
- Modify: `tests/test_skill_files.py`
- Modify: `docs/operator/README.md`
- Modify: `docs/operator/universal-wild-no-block-contract.md`
- Modify: `.agents/skills/hsconfig/SKILL.md`
- Modify: `.agents/skills/hsconfig/references/workflow.md`
- Modify: `C:\Users\darbo\.codex\skills\hsconfig\SKILL.md` through sync script only

**Interfaces:**
- Consumes: active docs and skill text
- Produces: one consistent normal path including `validate`
- Produces: one consistent report ownership list
- Produces: current mechanic visibility wording for `kindred`, `tourist`, `starship`, `spellburst`, `miniaturize`, `quickdraw`, `honorable_kill`, `elusive`, `poisonous`, and `imbue`

- [ ] **Step 1: Write failing docs/skill test**

Add this test to `tests/test_skill_files.py`:

```python
def test_docs_and_skill_explain_current_modern_mechanic_visibility_without_blocking():
    paths = [
        Path("docs/operator/README.md"),
        Path("docs/operator/universal-wild-no-block-contract.md"),
        Path(".agents/skills/hsconfig/SKILL.md"),
        Path(".agents/skills/hsconfig/references/workflow.md"),
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in paths)

    for mechanic in [
        "`kindred`",
        "`tourist`",
        "`starship`",
        "`spellburst`",
        "`miniaturize`",
        "`quickdraw`",
        "`honorable_kill`",
        "`elusive`",
        "`poisonous`",
        "`imbue`",
    ]:
        assert mechanic in combined

    assert "modern mechanic visibility is non-blocking" in combined.lower()
    assert "reports/mechanic_drift_report.json" in combined
    assert "reports/semantic_enrichment_report.json" in combined
    assert "source-manifest -> draft-source-documents -> research-deck -> prepare -> validate -> apply" in combined
```

- [ ] **Step 2: Run failing docs test**

Run:

```powershell
python -m pytest tests/test_skill_files.py::test_docs_and_skill_explain_current_modern_mechanic_visibility_without_blocking -q
```

Expected: FAIL because the new mechanic list and exact wording are not in all active docs yet.

- [ ] **Step 3: Update operator guide wording**

In `docs/operator/README.md`, under `Load Safety vs. Config Richness`, add this paragraph after the existing `mechanic_drift_report.json` paragraph:

```markdown
Modern mechanic visibility is non-blocking. HSConfig names current mechanics such as `kindred`, `tourist`, `starship`, `spellburst`, `miniaturize`, `quickdraw`, `honorable_kill`, `elusive`, `poisonous`, and `imbue` when card metadata or text exposes them. Mechanics without a documented normal-path VisionAI runtime surface stay visible as `warning_only` or `partial`; they must not block `load_safe_apply` for a technically valid package.
```

In the same file, update the report ownership table so it contains both rows:

```markdown
| `reports/mechanic_drift_report.json` | non-blocking mechanic drift visibility | which unknown, text-only, or current-card-type mechanics should be inspected next |
| `reports/semantic_enrichment_report.json` | semantic mechanic diagnostics | which static mechanics, linked entities, deckwide effects, and warning-only flags were inferred |
```

- [ ] **Step 4: Update universal no-block contract**

In `docs/operator/universal-wild-no-block-contract.md`, add a short current-mechanic paragraph near the mechanic drift rules:

```markdown
Modern mechanic visibility is non-blocking. `kindred`, `tourist`, `starship`, `spellburst`, `miniaturize`, `quickdraw`, `honorable_kill`, `elusive`, `poisonous`, and `imbue` are current/static mechanic visibility labels. They may lower as `partial` when HSConfig has a safe existing VisionAI posture surface, otherwise they stay `warning_only`. Neither state blocks `load_safe_apply` for a technically valid package.
```

- [ ] **Step 5: Update skill and workflow references**

In `.agents/skills/hsconfig/SKILL.md`, add this rule near the existing mechanic visibility rules:

```markdown
- Modern mechanic visibility is non-blocking. Current mechanics such as `kindred`, `tourist`, `starship`, `spellburst`, `miniaturize`, `quickdraw`, `honorable_kill`, `elusive`, `poisonous`, and `imbue` should be named in reports when detected, but they must not block load-safe apply unless the package is technically invalid.
```

In `.agents/skills/hsconfig/references/workflow.md`, add this sentence after the mechanic drift paragraph:

```markdown
Modern mechanic visibility is non-blocking: `kindred`, `tourist`, `starship`, `spellburst`, `miniaturize`, `quickdraw`, `honorable_kill`, `elusive`, `poisonous`, and `imbue` are surfaced as partial or warning-only visibility labels, not runtime write blockers.
```

- [ ] **Step 6: Sync installed skill**

Run:

```powershell
python scripts/sync_installed_skill.py
```

Expected output includes:

```text
HSConfig skill synced
```

Then run:

```powershell
python scripts/sync_installed_skill.py --check
```

Expected output includes:

```text
HSConfig skill is in sync
```

- [ ] **Step 7: Run docs and skill tests**

Run:

```powershell
python -m pytest tests/test_skill_files.py tests/test_docs_active_path.py tests/test_skill_sync.py -q
```

Expected: all tests pass.

- [ ] **Step 8: Commit Task 4**

```powershell
git add docs/operator/README.md docs/operator/universal-wild-no-block-contract.md .agents/skills/hsconfig/SKILL.md .agents/skills/hsconfig/references/workflow.md tests/test_skill_files.py C:/Users/darbo/.codex/skills/hsconfig
git commit -m "docs: document modern mechanic visibility contract"
```

If Git refuses the installed skill path because it is outside the repo, stage only repo files and keep the installed skill sync verified by `python scripts/sync_installed_skill.py --check`.

---

### Task 5: Final Regression And No-Block Proof

**Files:**
- Verify only; no planned source changes.

**Interfaces:**
- Consumes: Tasks 1-4 changes.
- Produces: verified no-block proof for modern mechanics and the existing deck matrix.

- [ ] **Step 1: Run focused mechanic tests**

Run:

```powershell
python -m pytest tests/test_mechanic_support.py tests/test_mechanic_drift.py tests/test_operator_summary.py tests/test_report_ownership.py -q
```

Expected: all tests pass.

- [ ] **Step 2: Run focused no-block matrix tests**

Run:

```powershell
python -m pytest tests/test_universal_wild_no_block_matrix.py tests/test_supplemental_cute_warrior_load_safe.py tests/test_prepare_cli.py tests/test_runtime_apply.py tests/test_apply_gate.py -q
```

Expected: all tests pass and the existing 12-deck load-safe proof remains valid.

- [ ] **Step 3: Run docs and skill sync tests**

Run:

```powershell
python -m pytest tests/test_skill_files.py tests/test_docs_active_path.py tests/test_skill_sync.py tests/test_operator_guidance.py -q
python scripts/sync_installed_skill.py --check
```

Expected: pytest passes and installed skill is in sync.

- [ ] **Step 4: Run full suite**

Run:

```powershell
python -m pytest -q
```

Expected: full suite passes.

- [ ] **Step 5: Inspect Git diff**

Run:

```powershell
git diff --stat
git diff -- src/hsconfig/mechanic_support.py src/hsconfig/mechanic_drift.py src/hsconfig/operator_summary.py src/hsconfig/report_ownership.py
git diff -- docs/operator/README.md docs/operator/universal-wild-no-block-contract.md .agents/skills/hsconfig/SKILL.md .agents/skills/hsconfig/references/workflow.md
```

Expected:
- No new commands.
- No new dependencies.
- No replay, winrate, HDT, HSTuner, or post-run tuning behavior.
- No `Presume.json` or `Concede.json` normal-path output.
- New mechanics are visible but non-blocking.

- [ ] **Step 6: Commit final verification note if needed**

If Task 5 required any small follow-up edits, commit them:

```powershell
git add .
git commit -m "test: verify modern mechanic no-block coverage"
```

If no edits were needed, skip this commit.

- [ ] **Step 7: Final status**

Run:

```powershell
git status --short --branch
```

Expected: clean working tree on the implementation branch before merge/push decision.

---

## Self-Review

- Spec coverage: The plan implements the recommended Option A by adding modern mechanic registry entries, text-pattern drift detection, operator summary follow-up fields, report ownership alignment, active docs, installed skill sync, and focused/full tests.
- Placeholder scan: No placeholder tokens or undefined implementation steps remain.
- Type consistency: All named functions already exist: `support_for_roles`, `operator_visibility_bucket`, `build_mechanic_drift_report`, `build_operator_summary`, and `build_report_ownership`.
- Scope check: The plan does not add commands, dependencies, runtime log parsing, winrate, HSTuner behavior, candidate promotion, or new runtime surfaces.
- No-block check: Every new mechanic is either `partial` or `warning_only`; none becomes a runtime apply blocker.

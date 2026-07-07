# HSConfig Source-Backed Archetype Fixture Wave Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn HSConfig's currently valid deck-to-config path into a source-backed archetype proof path for representative Hearthstone deck families, so a deck input can produce a strong initial HearthRanger CustomConfig when current guide/card-specific evidence exists.

**Architecture:** Keep HSConfig lean: pre-game source-backed CustomConfig generation only. Use the existing `research-deck -> prepare -> operator_summary` flow, add stricter research-audit validation, create a small archetype fixture matrix, and promote representative decks from name-level coverage to source-backed fixtures with E2E assertions. Do not add HSTuner, replay parsing, winrate analysis, post-run tuning, or normal-path `Presume.json` / `Concede.json`.

**Tech Stack:** Python 3.11+, `pytest`, `hearthstone>=9.0.0`, HearthSim deckstrings, HearthstoneJSON/card metadata, HearthRanger VisionAI JSON surfaces.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig` for `Teufelsboy/HSConfig`.
- Keep HSConfig separate from HSTuner.
- Do not add replay parsing, HDT parsing, winrate validation, candidate promotion, or post-run tuning to this repo.
- Generated runtime packages belong under `outputs/` and are ignored by git.
- Preserve exact deck and CardID identity.
- Preserve full `GlobalValues.json` key profiling.
- Preserve every card covered in the gameplan contract.
- Preserve strict JSON validation.
- Preserve row-level provenance for generated config rows.
- Normal runtime surfaces stay limited to `GlobalValues.json`, `Mulligan.json`, per-card `<CARDID>.json`, and `Combo.json` only when a concrete valid combo exists.
- `Presume.json` and `Concede.json` remain documented/gated surfaces, not normal HSConfig outputs.
- `operator_summary.json` remains the operator-facing readiness authority.
- `VALID_PACKAGE` means structurally valid and load-safe only.
- `SOURCE_BACKED_STRONG` means current guide-backed or source-backed static card coverage supports a strong initial config.
- `low`, `report_only`, `explicit_low_confidence`, `generic_low_confidence`, and `contract_gap` evidence must not lower into runtime rows.
- Do not commit `outputs/`, HearthRanger logs, HDT replays, `Power.log`, `.hsreplay`, or private runtime evidence.

---

## File Structure

Create or modify these files only:

- Modify `docs/research/2026-07-07-hsconfig-skill-audit/fields.yaml`: convert the audit schema to the `field_categories` format expected by `~/.codex/skills/research/validate_json.py`.
- Create `tests/test_research_audit_schema.py`: regression that the audit schema declares and validates the expected fields.
- Create `docs/operator/archetype-fixture-matrix.json`: deck-neutral target matrix for the 11 supplied representative decks.
- Create `tests/test_archetype_fixture_matrix.py`: validates the matrix shape, deck coverage, and archetype buckets.
- Create `tests/fixtures/source_documents_shadowpriest_strong.json`: source-backed ShadowPriest fixture.
- Create `tests/fixtures/source_documents_bigshaman_strong.json`: source-backed BigShaman fixture.
- Create `tests/fixtures/source_documents_discolock_strong.json`: source-backed Discolock fixture.
- Create `tests/fixtures/source_documents_kingslayer_strong.json`: source-backed Kingslayer fixture.
- Create `tests/fixtures/source_documents_imbuemage_strong.json`: source-backed ImbueMage fixture.
- Create `tests/test_archetype_source_fixtures.py`: validates source-document schema, readiness lanes, and runtime-lowering boundaries for the five fixture files.
- Create `tests/test_archetype_fixture_e2e.py`: runs `hsconfig prepare` against the five representative source-document fixtures and asserts the operator reports are meaningful.
- Modify `src/hsconfig/guide_source_depth.py`: distinguish lowerable source-backed claims from report-only source artifacts in depth reports.
- Modify `src/hsconfig/operator_summary.py`: surface the lowerable/report-only split in `guide_strength_summary` without changing the existing status contract.
- Modify `tests/test_guide_source_depth.py`: coverage for the lowerable/report-only source-depth split.
- Modify `tests/test_operator_summary.py`: coverage for the new `guide_strength_summary` fields.
- Modify `README.md`, `.agents/skills/hsconfig/SKILL.md`, `.agents/skills/hsconfig/references/workflow.md`, and `docs/operator/guide-research-policy.md`: minimal wording polish after behavior is tested.
- Modify `tests/test_skill_files.py`: check concepts rather than repeated full paragraphs where possible.

---

### Task 1: Fix Research Audit Schema Validation

**Files:**
- Modify: `docs/research/2026-07-07-hsconfig-skill-audit/fields.yaml`
- Create: `tests/test_research_audit_schema.py`

**Interfaces:**
- Consumes: `~/.codex/skills/research/validate_json.py`
- Produces: a research schema that declares `source_summary`, `current_truth`, `repo_alignment`, `gaps_or_risks`, `recommended_action`, `confidence`, `citations`, and `uncertain` as required fields.

- [ ] **Step 1: Write the failing schema test**

Create `tests/test_research_audit_schema.py`:

```python
import json
import subprocess
import sys
from pathlib import Path

import yaml


AUDIT_DIR = Path("docs/research/2026-07-07-hsconfig-skill-audit")
FIELDS = AUDIT_DIR / "fields.yaml"
RESULTS = AUDIT_DIR / "results"
EXPECTED_FIELDS = {
    "source_summary",
    "current_truth",
    "repo_alignment",
    "gaps_or_risks",
    "recommended_action",
    "confidence",
    "citations",
    "uncertain",
}


def test_skill_audit_fields_yaml_uses_research_validator_shape():
    payload = yaml.safe_load(FIELDS.read_text(encoding="utf-8"))
    categories = payload["field_categories"]
    names = {
        field["name"]
        for category in categories
        for field in category["fields"]
    }
    required = {
        field["name"]
        for category in categories
        for field in category["fields"]
        if field.get("required") is True
    }

    assert names == EXPECTED_FIELDS
    assert required == EXPECTED_FIELDS


def test_skill_audit_research_results_cover_all_required_fields():
    result_files = sorted(RESULTS.glob("*.json"))
    assert len(result_files) == 5
    for path in result_files:
        data = json.loads(path.read_text(encoding="utf-8"))
        assert EXPECTED_FIELDS <= set(data)
        assert isinstance(data["gaps_or_risks"], list)
        assert isinstance(data["citations"], list)
        assert isinstance(data["uncertain"], list)


def test_skill_audit_results_pass_existing_research_validator():
    command = [
        sys.executable,
        str(Path.home() / ".codex/skills/research/validate_json.py"),
        "-f",
        str(FIELDS),
        "-j",
        *[str(path) for path in sorted(RESULTS.glob("*.json"))],
    ]
    completed = subprocess.run(command, text=True, capture_output=True, check=False)

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "Total fields: 8" in completed.stdout
    assert "Validation passed: 5/5" in completed.stdout
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```powershell
python -m pytest tests/test_research_audit_schema.py -q
```

Expected before implementation:

```text
FAILED tests/test_research_audit_schema.py::test_skill_audit_fields_yaml_uses_research_validator_shape
```

- [ ] **Step 3: Replace `fields.yaml` with the validator-compatible shape**

Replace `docs/research/2026-07-07-hsconfig-skill-audit/fields.yaml` with:

```yaml
field_categories:
  - category: hsconfig_skill_audit
    fields:
      - name: source_summary
        required: true
        description: Concise source-backed summary of the researched area.
      - name: current_truth
        required: true
        description: What should be treated as currently true for HSConfig design decisions.
      - name: repo_alignment
        required: true
        description: How the current HSConfig repository aligns with the researched area.
      - name: gaps_or_risks
        required: true
        description: Concrete gaps, risks, or uncertain assumptions.
      - name: recommended_action
        required: true
        description: The most useful next action for a lean HSConfig workflow.
      - name: confidence
        required: true
        description: high, medium, low, or [uncertain].
      - name: citations
        required: true
        description: URLs or local source paths used.
      - name: uncertain
        required: true
        description: Field names whose values remain uncertain.
```

- [ ] **Step 4: Run the schema tests**

Run:

```powershell
python -m pytest tests/test_research_audit_schema.py -q
```

Expected:

```text
3 passed
```

- [ ] **Step 5: Commit**

```powershell
git add docs/research/2026-07-07-hsconfig-skill-audit/fields.yaml tests/test_research_audit_schema.py docs/research/2026-07-07-hsconfig-skill-audit/results
git commit -m "test: enforce HSConfig research audit schema"
```

---

### Task 2: Add Archetype Fixture Matrix

**Files:**
- Create: `docs/operator/archetype-fixture-matrix.json`
- Create: `tests/test_archetype_fixture_matrix.py`

**Interfaces:**
- Produces: `docs/operator/archetype-fixture-matrix.json`, consumed by later tests and docs.
- The JSON root has `schema_version`, `purpose`, and `decks`.
- Each deck has `deck_name`, `deck_code`, `hs_id`, `hdt_deck_id`, `archetype_bucket`, `primary_mechanics`, `expected_runtime_surfaces`, and `fixture_stage`.

- [ ] **Step 1: Write the failing matrix test**

Create `tests/test_archetype_fixture_matrix.py`:

```python
import json
from pathlib import Path


MATRIX_PATH = Path("docs/operator/archetype-fixture-matrix.json")
EXPECTED_DECKS = {
    "ShadowPriest",
    "CtAPaladin",
    "PirateRogue",
    "BigShaman",
    "Discolock",
    "TreantDruid",
    "ImbueMage",
    "MechPala",
    "Kingslayer",
    "Boarlock",
    "PirateDH",
}
CORE_FIXTURES = {"ShadowPriest", "BigShaman", "Discolock", "Kingslayer", "ImbueMage"}


def _matrix():
    return json.loads(MATRIX_PATH.read_text(encoding="utf-8"))


def test_archetype_fixture_matrix_covers_supplied_decks():
    matrix = _matrix()
    assert matrix["schema_version"] == 1
    decks = {row["deck_name"] for row in matrix["decks"]}
    assert decks == EXPECTED_DECKS


def test_archetype_fixture_matrix_has_actionable_rows():
    for row in _matrix()["decks"]:
        assert row["deck_code"]
        assert row["hs_id"]
        assert row["hdt_deck_id"]
        assert row["archetype_bucket"]
        assert row["primary_mechanics"]
        assert "GlobalValues.json" in row["expected_runtime_surfaces"]
        assert "Mulligan.json" in row["expected_runtime_surfaces"]
        assert "<CARDID>.json" in row["expected_runtime_surfaces"]
        assert row["fixture_stage"] in {
            "core_source_backed_fixture",
            "second_wave_source_fixture",
        }


def test_archetype_fixture_matrix_marks_core_wave():
    core = {
        row["deck_name"]
        for row in _matrix()["decks"]
        if row["fixture_stage"] == "core_source_backed_fixture"
    }
    assert core == CORE_FIXTURES
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```powershell
python -m pytest tests/test_archetype_fixture_matrix.py -q
```

Expected:

```text
FAILED tests/test_archetype_fixture_matrix.py::test_archetype_fixture_matrix_covers_supplied_decks
```

- [ ] **Step 3: Create the matrix JSON**

Create `docs/operator/archetype-fixture-matrix.json` with the 11 deck rows from the user input. Use these `archetype_bucket` values:

- `ShadowPriest`: `aggro_burn_hero_power_transform`
- `CtAPaladin`: `recruit_board_flood`
- `PirateRogue`: `pirate_tempo_weapon_pressure`
- `BigShaman`: `big_recruit_deathrattle_cheat`
- `Discolock`: `discard_hand_mutation`
- `TreantDruid`: `token_board_snowball`
- `ImbueMage`: `hero_power_spell_generation`
- `MechPala`: `mech_board_scaling`
- `Kingslayer`: `weapon_sequence_pressure`
- `Boarlock`: `combo_control_resource`
- `PirateDH`: `pirate_hero_attack_pressure`

Set `fixture_stage` to `core_source_backed_fixture` for `ShadowPriest`, `BigShaman`, `Discolock`, `Kingslayer`, and `ImbueMage`; set `second_wave_source_fixture` for the others.

- [ ] **Step 4: Run the matrix tests**

Run:

```powershell
python -m pytest tests/test_archetype_fixture_matrix.py -q
```

Expected:

```text
3 passed
```

- [ ] **Step 5: Commit**

```powershell
git add docs/operator/archetype-fixture-matrix.json tests/test_archetype_fixture_matrix.py
git commit -m "docs: add HSConfig archetype fixture matrix"
```

---

### Task 3: Add Source Fixture Contract Tests

**Files:**
- Create: `tests/test_archetype_source_fixtures.py`
- Create later tasks' fixture targets as empty failing references: no fixture files are created in this task.

**Interfaces:**
- Consumes: `tests/fixtures/source_documents_<deck>_strong.json`
- Produces: fixture contract tests that later source-document tasks must satisfy.

- [ ] **Step 1: Write the failing contract tests**

Create `tests/test_archetype_source_fixtures.py`:

```python
import json
from pathlib import Path


FIXTURES = {
    "ShadowPriest": Path("tests/fixtures/source_documents_shadowpriest_strong.json"),
    "BigShaman": Path("tests/fixtures/source_documents_bigshaman_strong.json"),
    "Discolock": Path("tests/fixtures/source_documents_discolock_strong.json"),
    "Kingslayer": Path("tests/fixtures/source_documents_kingslayer_strong.json"),
    "ImbueMage": Path("tests/fixtures/source_documents_imbuemage_strong.json"),
}
SUPPORTED_CLAIM_KINDS = {
    "mulligan_keep",
    "mulligan_discard",
    "card_role",
    "targeting_rule",
    "combo_sequence",
    "gameplan_posture",
    "hero_power_transform",
    "mechanic_usage",
    "known_bad_pattern",
    "discover_choice",
    "choose_one_choice",
}


def _documents(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload["source_documents"] if isinstance(payload, dict) else payload


def test_core_source_fixture_files_exist():
    for path in FIXTURES.values():
        assert path.exists(), path


def test_core_source_fixtures_have_required_source_fields():
    for deck_name, path in FIXTURES.items():
        documents = _documents(path)
        assert documents, deck_name
        for document in documents:
            assert document["source_url"]
            assert document["source_title"]
            assert document["source_family"] in {
                "guide",
                "mulligan_guide",
                "matchup_guide",
                "card_text",
                "metadata",
            }
            assert document["retrieved_at"]
            assert isinstance(document["claims"], list)
            assert document["claims"]


def test_core_source_fixtures_use_supported_atomic_claims():
    for deck_name, path in FIXTURES.items():
        claim_kinds = {
            claim["claim_kind"]
            for document in _documents(path)
            for claim in document["claims"]
        }
        assert claim_kinds <= SUPPORTED_CLAIM_KINDS
        assert "gameplan_posture" in claim_kinds
        assert {"mulligan_keep", "card_role"} & claim_kinds


def test_core_source_fixtures_do_not_mark_every_claim_low_confidence():
    for deck_name, path in FIXTURES.items():
        confidences = [
            claim["source_confidence"]
            for document in _documents(path)
            for claim in document["claims"]
        ]
        assert any(confidence in {"high", "medium"} for confidence in confidences), deck_name
```

- [ ] **Step 2: Run the contract tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_archetype_source_fixtures.py -q
```

Expected:

```text
FAILED tests/test_archetype_source_fixtures.py::test_core_source_fixture_files_exist
```

- [ ] **Step 3: Commit the failing contract tests**

```powershell
git add tests/test_archetype_source_fixtures.py
git commit -m "test: define HSConfig archetype source fixture contract"
```

---

### Task 4: Add ShadowPriest and BigShaman Source Fixtures

**Files:**
- Create: `tests/fixtures/source_documents_shadowpriest_strong.json`
- Create: `tests/fixtures/source_documents_bigshaman_strong.json`
- Modify: `tests/test_archetype_source_fixtures.py` if fixture-specific claim requirements need exact assertions.

**Interfaces:**
- Consumes: source-document contract from Task 3.
- Produces: two core source-backed fixtures for aggro hero-power transform and big/recruit/deathrattle-style cheat archetypes.

- [ ] **Step 1: Add fixture-specific failing assertions**

Append to `tests/test_archetype_source_fixtures.py`:

```python
def test_shadowpriest_fixture_covers_hero_power_and_face_pressure():
    claims = [
        claim
        for document in _documents(FIXTURES["ShadowPriest"])
        for claim in document["claims"]
    ]
    kinds = {claim["claim_kind"] for claim in claims}
    stances = {str(claim.get("stance", "")) for claim in claims}
    assert "hero_power_transform" in kinds
    assert "targeting_rule" in kinds
    assert "prefer_enemy_hero" in stances


def test_bigshaman_fixture_covers_big_cheat_and_bad_target_patterns():
    claims = [
        claim
        for document in _documents(FIXTURES["BigShaman"])
        for claim in document["claims"]
    ]
    text = " ".join(str(claim.get("evidence_text_short", "")) for claim in claims).lower()
    kinds = {claim["claim_kind"] for claim in claims}
    assert {"card_role", "known_bad_pattern"} & kinds
    assert any(marker in text for marker in ("recruit", "big", "deathrattle", "cheat"))
    assert any(marker in text for marker in ("friendly", "own minion", "not enemy"))
```

- [ ] **Step 2: Run the new assertions to verify they fail**

Run:

```powershell
python -m pytest tests/test_archetype_source_fixtures.py::test_shadowpriest_fixture_covers_hero_power_and_face_pressure tests/test_archetype_source_fixtures.py::test_bigshaman_fixture_covers_big_cheat_and_bad_target_patterns -q
```

Expected:

```text
FAILED tests/test_archetype_source_fixtures.py::test_shadowpriest_fixture_covers_hero_power_and_face_pressure
FAILED tests/test_archetype_source_fixtures.py::test_bigshaman_fixture_covers_big_cheat_and_bad_target_patterns
```

- [ ] **Step 3: Create the ShadowPriest fixture**

Create `tests/fixtures/source_documents_shadowpriest_strong.json` with at least:

- one `gameplan_posture` claim with `stance: aggro_burn`;
- one `hero_power_transform` claim for Darkbishop Benedictus / Shadowform / Mind Spike;
- one `mulligan_keep` claim for the deck's strongest guide-backed early plan card;
- one `targeting_rule` claim with `stance: prefer_enemy_hero`;
- one `mechanic_usage` or `card_role` claim for the burn/pressure plan.

Use current source URLs and `retrieved_at` from the implementation day. Set `source_confidence` to `high` or `medium` only when the source is card-specific enough; otherwise use `low`.

- [ ] **Step 4: Create the BigShaman fixture**

Create `tests/fixtures/source_documents_bigshaman_strong.json` with at least:

- one `gameplan_posture` claim with `stance: deathrattle_recruit` or `combo_setup`;
- one `mulligan_keep` claim for early enabler or survival/setup card;
- one `card_role` claim for the big/recruit/deathrattle payoff card class;
- one `targeting_rule` or `known_bad_pattern` claim that prevents beneficial effects being aimed at enemy minions when the source/card text implies friendly targets;
- one `combo_sequence` claim only if exact ordered CardIDs and timing are source-backed.

- [ ] **Step 5: Run source fixture tests**

Run:

```powershell
python -m pytest tests/test_archetype_source_fixtures.py -q
```

Expected:

```text
6 passed
```

- [ ] **Step 6: Commit**

```powershell
git add tests/fixtures/source_documents_shadowpriest_strong.json tests/fixtures/source_documents_bigshaman_strong.json tests/test_archetype_source_fixtures.py
git commit -m "test: add ShadowPriest and BigShaman source fixtures"
```

---

### Task 5: Add Discolock, Kingslayer, and ImbueMage Source Fixtures

**Files:**
- Create: `tests/fixtures/source_documents_discolock_strong.json`
- Create: `tests/fixtures/source_documents_kingslayer_strong.json`
- Create: `tests/fixtures/source_documents_imbuemage_strong.json`
- Modify: `tests/test_archetype_source_fixtures.py`

**Interfaces:**
- Consumes: source-document contract from Task 3.
- Produces: three additional core fixtures for discard, weapon sequencing, and hero-power/spell-generation complexity.

- [ ] **Step 1: Add fixture-specific failing assertions**

Append to `tests/test_archetype_source_fixtures.py`:

```python
def test_discolock_fixture_covers_discard_and_hand_mutation():
    claims = [
        claim
        for document in _documents(FIXTURES["Discolock"])
        for claim in document["claims"]
    ]
    text = " ".join(str(claim.get("evidence_text_short", "")) for claim in claims).lower()
    assert "discard" in text
    assert any(claim["claim_kind"] in {"mechanic_usage", "known_bad_pattern"} for claim in claims)


def test_kingslayer_fixture_covers_weapon_sequence_pressure():
    claims = [
        claim
        for document in _documents(FIXTURES["Kingslayer"])
        for claim in document["claims"]
    ]
    text = " ".join(str(claim.get("evidence_text_short", "")) for claim in claims).lower()
    assert any(marker in text for marker in ("weapon", "attack", "kingsbane", "kingslayer"))
    assert any(claim["claim_kind"] in {"targeting_rule", "mechanic_usage", "card_role"} for claim in claims)


def test_imbuemage_fixture_covers_hero_power_and_generation():
    claims = [
        claim
        for document in _documents(FIXTURES["ImbueMage"])
        for claim in document["claims"]
    ]
    text = " ".join(str(claim.get("evidence_text_short", "")) for claim in claims).lower()
    kinds = {claim["claim_kind"] for claim in claims}
    assert any(marker in text for marker in ("imbue", "hero power", "spell", "generate", "discover"))
    assert {"hero_power_transform", "mechanic_usage", "discover_choice"} & kinds
```

- [ ] **Step 2: Run the new assertions to verify they fail**

Run:

```powershell
python -m pytest tests/test_archetype_source_fixtures.py::test_discolock_fixture_covers_discard_and_hand_mutation tests/test_archetype_source_fixtures.py::test_kingslayer_fixture_covers_weapon_sequence_pressure tests/test_archetype_source_fixtures.py::test_imbuemage_fixture_covers_hero_power_and_generation -q
```

Expected:

```text
FAILED tests/test_archetype_source_fixtures.py::test_discolock_fixture_covers_discard_and_hand_mutation
FAILED tests/test_archetype_source_fixtures.py::test_kingslayer_fixture_covers_weapon_sequence_pressure
FAILED tests/test_archetype_source_fixtures.py::test_imbuemage_fixture_covers_hero_power_and_generation
```

- [ ] **Step 3: Create the Discolock fixture**

Create `tests/fixtures/source_documents_discolock_strong.json` with at least:

- one `gameplan_posture` claim with `stance: aggro` or `combo_setup`;
- one `mechanic_usage` claim with `mechanic: discard`;
- one `mulligan_keep` claim for source-backed early discard payoff or enabler;
- one `known_bad_pattern` claim for discard timing if source/card text makes the risk clear;
- one `card_role` claim for each important enabler/payoff category.

- [ ] **Step 4: Create the Kingslayer fixture**

Create `tests/fixtures/source_documents_kingslayer_strong.json` with at least:

- one `gameplan_posture` claim with `stance: weapon_pressure`;
- one `mechanic_usage` claim with `mechanic: weapon`;
- one `targeting_rule` or `attack_posture`-style claim using a supported `runtime_block` only when source-backed;
- one `mulligan_keep` claim for a source-backed weapon or weapon tutor/enable card;
- one `known_bad_pattern` claim for inefficient weapon sequencing if source-backed.

- [ ] **Step 5: Create the ImbueMage fixture**

Create `tests/fixtures/source_documents_imbuemage_strong.json` with at least:

- one `gameplan_posture` claim with `stance: hero_power_pressure` or `combo_setup`;
- one `mechanic_usage` claim for `imbue`, `discover`, or spell generation;
- one `hero_power_transform` claim when exact transformed Hero Power identity is source-backed;
- one `mulligan_keep` claim for source-backed engine/setup card;
- one `discover_choice` or report-visible generated-option claim only if exact option identity can be proven.

- [ ] **Step 6: Run source fixture tests**

Run:

```powershell
python -m pytest tests/test_archetype_source_fixtures.py -q
```

Expected:

```text
9 passed
```

- [ ] **Step 7: Commit**

```powershell
git add tests/fixtures/source_documents_discolock_strong.json tests/fixtures/source_documents_kingslayer_strong.json tests/fixtures/source_documents_imbuemage_strong.json tests/test_archetype_source_fixtures.py
git commit -m "test: add discard weapon and imbue source fixtures"
```

---

### Task 6: Add Source-Backed Archetype E2E Tests

**Files:**
- Create: `tests/test_archetype_fixture_e2e.py`

**Interfaces:**
- Consumes: fixture files from Tasks 4 and 5.
- Produces: E2E proof that representative source-backed fixtures compile through `hsconfig prepare` and produce meaningful reports.

- [ ] **Step 1: Write failing parameterized E2E tests**

Create `tests/test_archetype_fixture_e2e.py`:

```python
import json
from pathlib import Path

import pytest

from hsconfig.cli import main


DECKS = [
    (
        "ShadowPriest",
        "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=",
        Path("tests/fixtures/source_documents_shadowpriest_strong.json"),
    ),
    (
        "BigShaman",
        "AAEBAaoIBpQD5LcDv84E9qMGgbgGmvYGDM4P0hP2vQKPlAPW9QO8tgT08gXqmAbGpgakpwb44gas/QYAAA==",
        Path("tests/fixtures/source_documents_bigshaman_strong.json"),
    ),
    (
        "Discolock",
        "AAEBAf0GBM4Hj4ID8aEG9qEGDbW5A9XRA9DhA5iSBauSBZXKBteXB4SZB6StB8ayB9a+B9m+B8+/BwAA",
        Path("tests/fixtures/source_documents_discolock_strong.json"),
    ),
    (
        "Kingslayer",
        "AAEBAaIHBpG8ApKDB4aoB4eoB4ioB4jZBwyMAtQF6bAD1bYEiskE16MF7p4G/KUG/KgGs8EG6sQGrcUGAAA=",
        Path("tests/fixtures/source_documents_kingslayer_strong.json"),
    ),
    (
        "ImbueMage",
        "AAEBAf0EBIUXm80DvO0Egb8GDcAB9KsD0+wD1uwDr8QForMG1voG3PoG9PwG94EHs4cHwIcH7o0HAAA=",
        Path("tests/fixtures/source_documents_imbuemage_strong.json"),
    ),
]


@pytest.mark.parametrize("deck_name,deck_code,source_documents", DECKS)
def test_core_archetype_fixture_prepare_path_is_source_informed(
    tmp_path: Path,
    capsys,
    monkeypatch,
    deck_name: str,
    deck_code: str,
    source_documents: Path,
):
    monkeypatch.setattr("hsconfig.cli.fetch_latest_cards", lambda timeout=10.0: [])
    out = tmp_path / deck_name

    code = main(
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
            "--source-documents-json",
            str(source_documents),
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    reports = out / "reports"
    operator = json.loads((reports / "operator_summary.json").read_text(encoding="utf-8"))
    coverage = json.loads((reports / "claim_coverage_report.json").read_text(encoding="utf-8"))
    readiness = json.loads(
        (reports / "per_card_config_readiness_report.json").read_text(encoding="utf-8")
    )
    card_behavior = json.loads(
        (reports / "card_behavior_plan_report.json").read_text(encoding="utf-8")
    )
    mulligan = json.loads((reports / "mulligan_plan_report.json").read_text(encoding="utf-8"))
    globalvalues = json.loads(
        (reports / "global_values_authority_matrix.json").read_text(encoding="utf-8")
    )

    assert code == 0
    assert payload["status"] == "passed"
    assert operator["technical_status"] == "VALID_PACKAGE"
    assert operator["semantic_status"] in {"SOURCE_BACKED_STRONG", "VALID_BUT_NOT_GUIDE_STRONG"}
    assert coverage["summary"]["guide_backed"] > 0
    assert coverage["summary"]["guide_backed"] + coverage["summary"]["static_semantics_backfilled"] > 0
    assert readiness["summary"]["runtime_emitted"] + readiness["summary"]["mulligan_only"] > 0
    assert card_behavior["rows"] or mulligan["rules"]
    assert "allowed_step1_overlays" in globalvalues
    assert "blocked_until_runtime_evidence" in globalvalues
```

- [ ] **Step 2: Run the E2E test to verify it fails before all fixtures exist**

Run:

```powershell
python -m pytest tests/test_archetype_fixture_e2e.py -q
```

Expected:

```text
FAILED tests/test_archetype_fixture_e2e.py
```

- [ ] **Step 3: Adjust fixtures, not production code, until the E2E behavior is meaningful**

For each failing deck:

- If `coverage["summary"]["guide_backed"] == 0`, add a card-specific source claim.
- If no runtime/mulligan rows exist, add a lowerable `mulligan_keep`, `targeting_rule`, `mechanic_usage`, or exact `combo_sequence`.
- If a claim is suppressed, inspect `unsupported_claims_report.json`, `card_behavior_suppression_report.json`, `combo_suppression_report.json`, and change the source document to use supported claim kinds and documented runtime blocks.

- [ ] **Step 4: Run the E2E test**

Run:

```powershell
python -m pytest tests/test_archetype_fixture_e2e.py -q
```

Expected:

```text
5 passed
```

- [ ] **Step 5: Commit**

```powershell
git add tests/test_archetype_fixture_e2e.py tests/fixtures/source_documents_*_strong.json
git commit -m "test: prove source-backed archetype prepare path"
```

---

### Task 7: Improve Guide-Depth Reporting

**Files:**
- Modify: `src/hsconfig/guide_source_depth.py`
- Modify: `src/hsconfig/operator_summary.py`
- Modify: `tests/test_guide_source_depth.py`
- Modify: `tests/test_operator_summary.py`

**Interfaces:**
- Consumes: normalized claims with `claim_readiness` and `trust_ceiling`.
- Produces: explicit source-depth counts for lowerable and report-only claims.

- [ ] **Step 1: Add failing guide-depth test**

Append to `tests/test_guide_source_depth.py`:

```python
def test_depth_report_separates_lowerable_and_report_only_claims():
    report = build_guide_source_depth_report(
        guide_claim_bundle={
            "claims": [
                {
                    "claim_id": "claim_good",
                    "claim_kind": "targeting_rule",
                    "source_family": "guide",
                    "claim_readiness": "guide_backed",
                    "trust_ceiling": "guide",
                    "cards": ["CARD_A"],
                },
                {
                    "claim_id": "claim_low",
                    "claim_kind": "card_role",
                    "source_family": "guide",
                    "claim_readiness": "explicit_low_confidence",
                    "trust_ceiling": "report_only",
                    "cards": ["CARD_B"],
                },
            ],
            "unsupported_claims": [],
            "claim_coverage_report": {
                "total_cards": 2,
                "cards": {
                    "CARD_A": {"coverage_status": "guide_backed"},
                    "CARD_B": {"coverage_status": "uncovered_low_confidence"},
                },
                "summary": {
                    "guide_backed": 1,
                    "static_semantics_backfilled": 0,
                    "uncovered_low_confidence": 1,
                },
            },
        },
        config_readiness_report={
            "summary": {
                "cards_needing_guide_claims": 1,
            }
        },
    )

    assert report["summary"]["lowerable_claims"] == 1
    assert report["summary"]["report_only_claims"] == 1
```

- [ ] **Step 2: Add failing operator-summary test**

Append to `tests/test_operator_summary.py`:

```python
def test_operator_summary_exposes_lowerable_and_report_only_claim_counts():
    summary = build_operator_summary(
        deck_name="Fixture",
        deck_code="AAE=",
        technical_validation={"status": "passed", "errors": []},
        guide_source_depth={
            "source_depth_status": "source_backed",
            "claim_count": 2,
            "summary": {
                "lowerable_claims": 1,
                "report_only_claims": 1,
            },
        },
        unsupported_conditions=[],
        globalvalue_authority={"blocked_until_runtime_evidence": []},
        generated_files=[],
        claim_coverage_report={
            "summary": {
                "guide_backed": 1,
                "static_semantics_backfilled": 0,
                "uncovered_low_confidence": 1,
            },
            "uncovered_cards": ["CARD_B"],
        },
        config_readiness_summary={
            "total_cards": 2,
            "generic_low_confidence": 1,
            "cards_needing_guide_claims": 1,
            "cards_needing_runtime_surface": 0,
            "cards_needing_mulligan_claims": 0,
            "cards_needing_combo_sequence": 0,
            "cards_needing_condition_lowering": 0,
            "cards_needing_mechanic_lowering": 0,
        },
        claim_conflict_report={"conflict_count": 0, "conflicts": []},
    )

    assert summary["guide_strength_summary"]["lowerable_claims"] == 1
    assert summary["guide_strength_summary"]["report_only_claims"] == 1
    assert summary["semantic_status"] == "VALID_BUT_NOT_GUIDE_STRONG"
```

- [ ] **Step 3: Run tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_guide_source_depth.py::test_depth_report_separates_lowerable_and_report_only_claims tests/test_operator_summary.py::test_operator_summary_exposes_lowerable_and_report_only_claim_counts -q
```

Expected:

```text
FAILED tests/test_guide_source_depth.py::test_depth_report_separates_lowerable_and_report_only_claims
FAILED tests/test_operator_summary.py::test_operator_summary_exposes_lowerable_and_report_only_claim_counts
```

- [ ] **Step 4: Implement guide-depth counts**

In `src/hsconfig/guide_source_depth.py`, import `claim_can_lower_to_runtime` from `hsconfig.source_document_model` and add these counts to the report summary:

```python
lowerable_claims = sum(1 for claim in claims if claim_can_lower_to_runtime(claim))
report_only_claims = sum(
    1
    for claim in claims
    if str(claim.get("trust_ceiling", "")).lower() == "report_only"
    or str(claim.get("claim_readiness", "")).lower()
    in {"explicit_low_confidence", "generic_low_confidence", "contract_gap"}
)
```

Add:

```python
"lowerable_claims": lowerable_claims,
"report_only_claims": report_only_claims,
```

to the existing `summary` dictionary.

- [ ] **Step 5: Implement operator summary pass-through**

In `src/hsconfig/operator_summary.py`, inside `_guide_strength_summary`, read:

```python
depth_summary = guide_source_depth.get("summary", {})
if not isinstance(depth_summary, dict):
    depth_summary = {}
```

Add these fields to the returned dictionary:

```python
"lowerable_claims": _int_value(depth_summary.get("lowerable_claims", 0)),
"report_only_claims": _int_value(depth_summary.get("report_only_claims", 0)),
```

- [ ] **Step 6: Run guide-depth tests**

Run:

```powershell
python -m pytest tests/test_guide_source_depth.py tests/test_operator_summary.py -q
```

Expected:

```text
all tests pass
```

- [ ] **Step 7: Commit**

```powershell
git add src/hsconfig/guide_source_depth.py src/hsconfig/operator_summary.py tests/test_guide_source_depth.py tests/test_operator_summary.py
git commit -m "feat: report lowerable guide claim depth"
```

---

### Task 8: Minimal Docs And Skill Polish

**Files:**
- Modify: `README.md`
- Modify: `.agents/skills/hsconfig/SKILL.md`
- Modify: `.agents/skills/hsconfig/references/workflow.md`
- Modify: `docs/operator/guide-research-policy.md`
- Modify: `tests/test_skill_files.py`

**Interfaces:**
- Consumes: source-backed fixture wave behavior and operator summary fields.
- Produces: lean docs that point to one normal path and avoid duplicated paragraphs.

- [ ] **Step 1: Add failing docs concept test**

Modify `tests/test_skill_files.py` so it checks concepts instead of exact repeated paragraphs:

```python
def test_skill_docs_preserve_hsconfig_boundaries_without_verbatim_duplication():
    docs = [
        Path("README.md").read_text(encoding="utf-8"),
        Path(".agents/skills/hsconfig/SKILL.md").read_text(encoding="utf-8"),
        Path(".agents/skills/hsconfig/references/workflow.md").read_text(encoding="utf-8"),
    ]
    joined = "\n".join(docs)
    assert "research-deck" in joined
    assert "prepare" in joined
    assert "operator_summary.json" in joined
    assert "VALID_PACKAGE" in joined
    assert "SOURCE_BACKED_STRONG" in joined
    assert "HSTuner" in joined
    assert "Presume.json" in joined
    assert "Concede.json" in joined
```

Remove tests that require the exact repeated sentence:

```text
STATIC_SEMANTICS_USABLE and VALID_BUT_NOT_GUIDE_STRONG are safe handoff states, not optimized-config claims.
```

- [ ] **Step 2: Run docs tests to see current state**

Run:

```powershell
python -m pytest tests/test_skill_files.py -q
```

Expected:

```text
all tests pass or only the removed exact-phrase assertions fail
```

- [ ] **Step 3: Polish README**

Keep `README.md` focused on:

- one-sentence purpose;
- normal command path: `research-deck -> prepare -> operator_summary -> apply when requested`;
- status table;
- key reports list;
- statement that HSConfig does not do post-game tuning.

Remove repeated prose that appears in `workflow.md` unless `tests/test_skill_files.py` requires the concept.

- [ ] **Step 4: Polish skill files**

Keep `.agents/skills/hsconfig/SKILL.md` short:

- when to use HSConfig;
- inputs;
- normal workflow;
- status meaning;
- hard boundaries.

Keep `.agents/skills/hsconfig/references/workflow.md` as the detailed flow. Do not duplicate all README examples.

- [ ] **Step 5: Polish guide research policy**

Update `docs/operator/guide-research-policy.md` to mention the new fixture matrix:

```markdown
For representative archetype breadth, use `docs/operator/archetype-fixture-matrix.json`.
Core source-backed fixtures should cover ShadowPriest, BigShaman, Discolock, Kingslayer, and ImbueMage before broadening to the second-wave decks.
```

- [ ] **Step 6: Run docs tests**

Run:

```powershell
python -m pytest tests/test_skill_files.py -q
```

Expected:

```text
all tests pass
```

- [ ] **Step 7: Commit**

```powershell
git add README.md .agents/skills/hsconfig/SKILL.md .agents/skills/hsconfig/references/workflow.md docs/operator/guide-research-policy.md tests/test_skill_files.py
git commit -m "docs: streamline HSConfig operator guidance"
```

---

### Task 9: Final Verification And Integration

**Files:**
- No planned source changes.

**Interfaces:**
- Consumes all previous tasks.
- Produces final confidence that the fixture wave is green and GitHub-ready.

- [ ] **Step 1: Run targeted tests**

Run:

```powershell
python -m pytest tests/test_research_audit_schema.py tests/test_archetype_fixture_matrix.py tests/test_archetype_source_fixtures.py tests/test_archetype_fixture_e2e.py -q
```

Expected:

```text
all tests pass
```

- [ ] **Step 2: Run adjacent workflow tests**

Run:

```powershell
python -m pytest tests/test_prepare_cli.py tests/test_operator_summary.py tests/test_source_document_builder.py tests/test_guide_claim_builder.py tests/test_guide_source_depth.py tests/test_skill_files.py -q
```

Expected:

```text
all tests pass
```

- [ ] **Step 3: Run full suite**

Run:

```powershell
python -m pytest -q
```

Expected:

```text
all tests pass
```

- [ ] **Step 4: Run a no-commit output check**

Run:

```powershell
git status --short --branch
git ls-files outputs
git ls-files .superpowers
```

Expected:

```text
## <branch-name>
```

and no tracked `outputs` or `.superpowers` files.

- [ ] **Step 5: Inspect final diff**

Run:

```powershell
git diff --stat main..HEAD
git diff --check main..HEAD
```

Expected:

```text
git diff --check exits with code 0
```

- [ ] **Step 6: Final review**

Dispatch one read-only reviewer focused on:

- fixture claims do not invent runtime behavior;
- low-confidence/report-only claims remain non-lowerable;
- `SOURCE_BACKED_STRONG` is not weakened;
- docs remain lean;
- no HSTuner/replay/winrate scope entered HSConfig.

- [ ] **Step 7: Merge/push only after review is clean**

If the reviewer has no findings:

```powershell
git switch main
git pull --ff-only origin main
git merge --ff-only <feature-branch>
python -m pytest -q
git push origin main
```

Expected:

```text
main -> main
```

---

## Self-Review

**Spec coverage:** This plan covers the recommendation: research-validator hardening, archetype fixture matrix, core source-backed representative fixtures, E2E proof, guide-depth reporting, lean docs polish, and final verification. It intentionally excludes HSTuner, replay parsing, winrate validation, post-run tuning, and normal-path `Presume.json` / `Concede.json`.

**Placeholder scan:** The plan does not use deferred-work markers or undefined task names. Source fixture tasks require current source URLs and retrieved dates because those are research artifacts; the required claim kinds and runtime constraints are explicit.

**Type consistency:** The plan uses existing HSConfig concepts and files: `source_documents`, `claim_kind`, `source_confidence`, `claim_readiness`, `trust_ceiling`, `operator_summary`, `guide_strength_summary`, `semantic_blockers`, `GlobalValues.json`, `Mulligan.json`, CardID JSON, and `Combo.json`.

**Risk note:** The fixture JSONs must be created from current source-backed research. If a specific card cannot be source-backed, the correct behavior is to mark it low confidence or report-only and let `operator_summary` explain the remaining blocker; do not force `SOURCE_BACKED_STRONG` by weakening gates.

# HSConfig 11-Deck Source-Backed Strong Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make HSConfig's representative deck fixtures honest and strong: every fixture marked as `core_source_backed_fixture` must produce `operator_summary.semantic_status == "SOURCE_BACKED_STRONG"`, or it must be explicitly downgraded to a non-strong source-informed fixture with its blocker chain documented.

**Architecture:** Keep HSConfig a lean pre-game HearthRanger VisionAI CustomConfig compiler. Do not add HSTuner, replay parsing, HDT parsing, winrate validation, candidate promotion, or post-run tuning. Close source-backed strength through better source documents, deterministic static semantics, documented VisionAI runtime-surface lowering, and stricter operator tests.

**Tech Stack:** Python 3.11+, pytest, HearthSim `hearthstone.deckstrings`, HearthRanger VisionAI JSON surfaces, HearthstoneJSON/card metadata, structured `source_documents.json`, local `hsconfig` CLI.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig` for `Teufelsboy/HSConfig`.
- Keep HSConfig separate from HSTuner.
- Do not add replay parsing, HDT parsing, winrate validation, candidate promotion, runtime-log parsing, or post-run tuning.
- Normal runtime outputs are `GlobalValues.json`, `Mulligan.json`, per-card `<CARDID>.json`, and `Combo.json` only when a concrete exact combo sequence exists.
- Do not emit `Presume.json` or `Concede.json` in the normal path; they remain legacy/gated validator-supported surfaces only.
- `operator_summary.json` is the canonical operator gate.
- `SOURCE_BACKED_STRONG` must stay strict. Do not weaken the gate to make fixtures green.
- Use `claim_can_lower_to_runtime()` as the mandatory runtime-lowering gate for every compiler path.
- Every deck card must be represented in the gameplan contract and visible in per-card readiness.
- Fixture claims must use public HTTPS sources or source-backed static semantics; no private logs, replay evidence, fixture-only URLs, or local runtime evidence.
- Generated runtime packages belong under ignored `outputs/` or temp folders and must not be committed.
- Before final push, run full tests, skill-sync check, 11-deck prepare proof, and inspect `git status`.

---

## Current Baseline To Preserve

Research-deep validation already exists and must remain green:

```powershell
python C:\Users\darbo\.codex\skills\research\validate_json.py -f docs\research\2026-07-07-hsconfig-skill-audit\fields.yaml -j docs\research\2026-07-07-hsconfig-skill-audit\results\HearthRanger_VisionAI_Runtime_Surface_Contract.json docs\research\2026-07-07-hsconfig-skill-audit\results\Hearthstone_Card_Identity_And_Static_Semantics.json docs\research\2026-07-07-hsconfig-skill-audit\results\Source-Backed_Guide_Claim_Depth.json docs\research\2026-07-07-hsconfig-skill-audit\results\Multi-Archetype_Deck_Coverage_Matrix.json docs\research\2026-07-07-hsconfig-skill-audit\results\Lean_Skill_Boundary_And_Operator_UX.json
```

Expected:

```text
Validation passed: 5/5
Average coverage: 100.0%
```

Fresh pre-plan 11-deck audit showed:

| Deck | Current semantic status | Current blocker summary |
|---|---|---|
| ShadowPriest | `SOURCE_BACKED_STRONG` | none |
| CtAPaladin | `VALID_BUT_NOT_GUIDE_STRONG` | 4 guide-claim gaps, 4 runtime-surface gaps |
| PirateRogue | `VALID_BUT_NOT_GUIDE_STRONG` | 10 guide-claim gaps |
| BigShaman | `VALID_BUT_NOT_GUIDE_STRONG` | 2 guide-claim gaps, 6 runtime-surface gaps |
| Discolock | `VALID_BUT_NOT_GUIDE_STRONG` | 2 guide-claim gaps, 9 runtime-surface gaps, 2 mechanic-lowering gaps |
| TreantDruid | `VALID_BUT_NOT_GUIDE_STRONG` | 9 guide-claim gaps, 3 runtime-surface gaps |
| ImbueMage | `VALID_BUT_NOT_GUIDE_STRONG` | 3 guide-claim gaps, 3 runtime-surface gaps, 1 mechanic-lowering gap |
| MechPala | `VALID_BUT_NOT_GUIDE_STRONG` | 4 guide-claim gaps |
| Kingslayer | `VALID_BUT_NOT_GUIDE_STRONG` | 7 guide-claim gaps, 2 runtime-surface gaps, unsupported conditions |
| Boarlock | `VALID_BUT_NOT_GUIDE_STRONG` | 7 guide-claim gaps, 5 runtime-surface gaps, unsupported conditions |
| PirateDH | `VALID_BUT_NOT_GUIDE_STRONG` | 10 guide-claim gaps, 2 runtime-surface gaps |

The implementation must not hide this mismatch. It must either close it or make the matrix honest.

## File Structure

### New Or Updated Test Helpers

- Create: `tests/helpers/fixture_prepare.py`
  - Owns reusable 11-deck prepare helpers for tests.
  - Exposes `prepare_fixture_deck(tmp_path: Path, deck: dict[str, Any]) -> dict[str, Any]`.
  - Exposes `load_archetype_matrix() -> list[dict[str, Any]]`.
- Modify: `tests/test_archetype_fixture_e2e.py`
  - Splits source-informed validity tests from strong-fixture tests.
  - Strong fixtures must assert `SOURCE_BACKED_STRONG`.
- Modify: `tests/test_archetype_fixture_matrix.py`
  - Adds explicit fixture-stage semantics.
- Create: `tests/test_strong_fixture_closure.py`
  - Regression tests for strong fixture gates and blocker counts.

### Source Fixture Files

Modify existing fixture files as needed:

- `tests/fixtures/source_documents_ctapaladin_strong.json`
- `tests/fixtures/source_documents_piraterogue_strong.json`
- `tests/fixtures/source_documents_bigshaman_strong.json`
- `tests/fixtures/source_documents_discolock_strong.json`
- `tests/fixtures/source_documents_treantdruid_strong.json`
- `tests/fixtures/source_documents_imbuemage_strong.json`
- `tests/fixtures/source_documents_mechpala_strong.json`
- `tests/fixtures/source_documents_kingslayer_strong.json`
- `tests/fixtures/source_documents_boarlock_strong.json`
- `tests/fixtures/source_documents_piratedh_strong.json`
- Preserve: `tests/fixtures/source_documents_shadowpriest_strong.json`

### Runtime Lowering Modules

Modify only when a concrete blocker proves a documented VisionAI lowering gap:

- `src/hsconfig/card_behavior_surface_router.py`
- `src/hsconfig/config_readiness.py`
- `src/hsconfig/mulligan_plan.py`
- `src/hsconfig/combo_plan.py`
- `src/hsconfig/globalvalues_authority.py`
- `src/hsconfig/source_document_model.py`

### Docs And Skill

- Modify: `docs/operator/archetype-fixture-matrix.json`
- Modify: `README.md`
- Modify: `.agents/skills/hsconfig/SKILL.md`
- Modify: `.agents/skills/hsconfig/references/workflow.md`
- Modify: `.agents/skills/hsconfig/references/guide-research-policy.md`
- Modify: `.agents/skills/hsconfig/references/card-behavior-policy.md`
- Modify: `.agents/skills/hsconfig/references/visionai-surfaces.md`
- Modify: `tests/test_skill_files.py`

---

## Task 1: Strong Fixture Truth Gate

**Files:**

- Create: `tests/helpers/fixture_prepare.py`
- Modify: `tests/test_archetype_fixture_e2e.py`
- Modify: `tests/test_archetype_fixture_matrix.py`
- Create: `tests/test_strong_fixture_closure.py`

**Interfaces:**

- Consumes: `docs/operator/archetype-fixture-matrix.json`.
- Produces: `load_archetype_matrix() -> list[dict[str, Any]]`.
- Produces: `prepare_fixture_deck(tmp_path: Path, deck: dict[str, Any]) -> dict[str, Any]` returning `operator`, `readiness`, `coverage`, `generated_files`, and `out`.

- [ ] **Step 1: Write the helper file**

Create `tests/helpers/fixture_prepare.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from hsconfig.cli import main


MATRIX = Path("docs/operator/archetype-fixture-matrix.json")


def load_archetype_matrix() -> list[dict[str, Any]]:
    payload = json.loads(MATRIX.read_text(encoding="utf-8"))
    return list(payload["decks"])


def fixture_path_for(deck: dict[str, Any]) -> Path:
    deck_name = str(deck["deck_name"]).lower()
    return Path(f"tests/fixtures/source_documents_{deck_name}_strong.json")


def prepare_fixture_deck(tmp_path: Path, deck: dict[str, Any]) -> dict[str, Any]:
    out = tmp_path / str(deck["deck_name"])
    code = main(
        [
            "prepare",
            "--deck-name",
            str(deck["deck_name"]),
            "--deck-code",
            str(deck["deck_code"]),
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(out),
            "--source-documents-json",
            str(fixture_path_for(deck)),
            "--json",
        ]
    )

    reports = out / "reports"
    operator = json.loads((reports / "operator_summary.json").read_text(encoding="utf-8"))
    readiness = json.loads(
        (reports / "per_card_config_readiness_report.json").read_text(encoding="utf-8")
    )
    coverage = json.loads((reports / "claim_coverage_report.json").read_text(encoding="utf-8"))
    config_root = out / "CustomConfig"
    generated_files = sorted(path.name for path in config_root.rglob("*.json"))
    return {
        "exit_code": code,
        "out": out,
        "operator": operator,
        "readiness": readiness,
        "coverage": coverage,
        "generated_files": generated_files,
    }
```

- [ ] **Step 2: Add a failing test that exposes the current mismatch**

Create `tests/test_strong_fixture_closure.py`:

```python
from __future__ import annotations

import pytest

from tests.helpers.fixture_prepare import load_archetype_matrix, prepare_fixture_deck


@pytest.mark.parametrize("deck", load_archetype_matrix(), ids=lambda row: row["deck_name"])
def test_core_source_backed_fixture_stage_requires_source_backed_strong(tmp_path, monkeypatch, deck):
    monkeypatch.setattr("hsconfig.cli.fetch_latest_cards", lambda timeout=10.0: [])
    if deck["fixture_stage"] != "core_source_backed_fixture":
        pytest.skip(f"{deck['deck_name']} is not marked as a core source-backed fixture")

    result = prepare_fixture_deck(tmp_path, deck)

    assert result["exit_code"] == 0
    assert result["operator"]["technical_status"] == "VALID_PACKAGE"
    assert result["operator"]["semantic_status"] == "SOURCE_BACKED_STRONG"
    assert result["operator"]["next_action"] == "READY_TO_APPLY_OR_HANDOFF"
    assert result["operator"]["semantic_blockers"] == []
    assert result["readiness"]["summary"]["cards_needing_guide_claims"] == 0
    assert result["readiness"]["summary"]["cards_needing_runtime_surface"] == 0
    assert result["readiness"]["summary"]["cards_needing_combo_sequence"] == 0
    assert result["readiness"]["summary"]["cards_needing_condition_lowering"] == 0
    assert result["readiness"]["summary"]["cards_needing_mechanic_lowering"] == 0
    assert "Presume.json" not in result["generated_files"]
    assert "Concede.json" not in result["generated_files"]
```

- [ ] **Step 3: Run the failing test**

Run:

```powershell
python -m pytest tests/test_strong_fixture_closure.py -q
```

Expected now: failures for every deck currently marked `core_source_backed_fixture` but producing `VALID_BUT_NOT_GUIDE_STRONG`. ShadowPriest should pass.

- [ ] **Step 4: Refactor existing E2E test to separate source-informed from strong**

In `tests/test_archetype_fixture_e2e.py`, replace the broad semantic assertion:

```python
assert operator["semantic_status"] in {"SOURCE_BACKED_STRONG", "VALID_BUT_NOT_GUIDE_STRONG"}
```

with:

```python
assert operator["technical_status"] == "VALID_PACKAGE"
assert operator["semantic_status"] in {
    "SOURCE_BACKED_STRONG",
    "VALID_BUT_NOT_GUIDE_STRONG",
}
assert operator["next_action"] in {
    "READY_TO_APPLY_OR_HANDOFF",
    "IMPROVE_GUIDE_SOURCES_BEFORE_STRONG_APPLY",
}
```

Keep this as the source-informed smoke test. The strict strong assertion lives only in `tests/test_strong_fixture_closure.py`.

- [ ] **Step 5: Run focused tests**

Run:

```powershell
python -m pytest tests/test_archetype_fixture_e2e.py tests/test_archetype_fixture_matrix.py tests/test_strong_fixture_closure.py -q
```

Expected: `test_strong_fixture_closure.py` still fails until later tasks close or reclassify each deck.

- [ ] **Step 6: Commit**

```powershell
git add tests/helpers/fixture_prepare.py tests/test_archetype_fixture_e2e.py tests/test_archetype_fixture_matrix.py tests/test_strong_fixture_closure.py
git commit -m "test: require strong fixtures to be source backed strong"
```

---

## Task 2: Fixture Stage Semantics And Blocker Snapshot

**Files:**

- Modify: `docs/operator/archetype-fixture-matrix.json`
- Create: `tests/test_fixture_stage_semantics.py`
- Create: `docs/operator/source-backed-strong-closure.md`

**Interfaces:**

- Consumes: matrix rows with `fixture_stage`.
- Produces allowed stages:
  - `core_source_backed_fixture`: must be `SOURCE_BACKED_STRONG`.
  - `source_informed_valid_fixture`: must be `VALID_PACKAGE`, may be `VALID_BUT_NOT_GUIDE_STRONG`.
  - `future_fixture`: not in required 11-deck E2E gate.
- Produces a human blocker snapshot in `docs/operator/source-backed-strong-closure.md`.

- [ ] **Step 1: Add stage semantics test**

Create `tests/test_fixture_stage_semantics.py`:

```python
from __future__ import annotations

from tests.helpers.fixture_prepare import load_archetype_matrix


ALLOWED_FIXTURE_STAGES = {
    "core_source_backed_fixture",
    "source_informed_valid_fixture",
    "future_fixture",
}


def test_fixture_stage_values_are_explicit():
    decks = load_archetype_matrix()

    assert {deck["fixture_stage"] for deck in decks} <= ALLOWED_FIXTURE_STAGES


def test_shadowpriest_remains_core_source_backed_fixture():
    decks = {deck["deck_name"]: deck for deck in load_archetype_matrix()}

    assert decks["ShadowPriest"]["fixture_stage"] == "core_source_backed_fixture"
```

- [ ] **Step 2: Reclassify non-strong rows honestly**

In `docs/operator/archetype-fixture-matrix.json`, keep `ShadowPriest` as:

```json
"fixture_stage": "core_source_backed_fixture"
```

Temporarily set the 10 currently non-strong decks to:

```json
"fixture_stage": "source_informed_valid_fixture"
```

This makes the matrix honest before closing decks one by one. Later tasks promote rows back to `core_source_backed_fixture` only after the strict test passes.

- [ ] **Step 3: Add blocker snapshot doc**

Create `docs/operator/source-backed-strong-closure.md`:

```markdown
# Source-Backed Strong Closure

This file tracks which representative HSConfig deck fixtures are truly strong.

`core_source_backed_fixture` means the fixture must produce:

- `technical_status=VALID_PACKAGE`
- `semantic_status=SOURCE_BACKED_STRONG`
- `next_action=READY_TO_APPLY_OR_HANDOFF`
- no `semantic_blockers`
- no normal-path `Presume.json` or `Concede.json`

`source_informed_valid_fixture` means the fixture proves a valid source-informed package, but it still needs guide claims, runtime-surface lowering, condition lowering, mechanic lowering, or combo sequence detail before it can be called strong.

## Current Closure Targets

| Deck | Required work before promotion |
|---|---|
| ShadowPriest | Already strong. Preserve this as the control fixture. |
| MechPala | Close guide-claim gaps. |
| PirateRogue | Close guide-claim gaps. |
| CtAPaladin | Close guide-claim and recruit/board-flood runtime-surface gaps. |
| BigShaman | Close guide-claim and big/recruit/deathrattle runtime-surface gaps. |
| Discolock | Close guide-claim, discard runtime-surface, and mechanic-lowering gaps. |
| Kingslayer | Close guide-claim, weapon runtime-surface, and unsupported-condition gaps. |
| TreantDruid | Close guide-claim and token-board runtime-surface gaps. |
| ImbueMage | Close guide-claim, hero-power/spell-generation runtime-surface, and mechanic-lowering gaps. |
| Boarlock | Close guide-claim, combo/resource runtime-surface, and unsupported-condition gaps. |
| PirateDH | Close guide-claim and pirate/hero-attack runtime-surface gaps. |
```

- [ ] **Step 4: Run semantics tests**

Run:

```powershell
python -m pytest tests/test_fixture_stage_semantics.py tests/test_strong_fixture_closure.py -q
```

Expected: only ShadowPriest is required by `test_strong_fixture_closure.py`, and it passes.

- [ ] **Step 5: Commit**

```powershell
git add docs/operator/archetype-fixture-matrix.json docs/operator/source-backed-strong-closure.md tests/test_fixture_stage_semantics.py
git commit -m "docs: make source-backed fixture stages honest"
```

---

## Task 3: MechPala And PirateRogue Guide-Claim Closure

**Files:**

- Modify: `tests/fixtures/source_documents_mechpala_strong.json`
- Modify: `tests/fixtures/source_documents_piraterogue_strong.json`
- Modify: `docs/operator/archetype-fixture-matrix.json`
- Modify: `tests/test_archetype_source_fixtures.py`
- Modify: `docs/operator/source-backed-strong-closure.md`

**Interfaces:**

- Consumes: current blockers from `reports/operator_summary.json` and `reports/per_card_config_readiness_report.json`.
- Produces: `MechPala` and `PirateRogue` promoted to `core_source_backed_fixture`.

- [ ] **Step 1: Run deck-specific blocker proof**

Run:

```powershell
$root = Join-Path $env:TEMP 'hsconfig-strong-task3'
Remove-Item -LiteralPath $root -Recurse -Force -ErrorAction SilentlyContinue
foreach ($name in 'MechPala','PirateRogue') {
  $deck = (Get-Content docs\operator\archetype-fixture-matrix.json -Raw | ConvertFrom-Json).decks | Where-Object deck_name -eq $name
  python -m hsconfig prepare --deck-name $deck.deck_name --deck-code $deck.deck_code --runtime-root (Join-Path $root 'runtime') --out (Join-Path $root $name) --source-documents-json ("tests\fixtures\source_documents_" + $name.ToLower() + "_strong.json") --json | Out-Null
  Get-Content (Join-Path $root "$name\reports\operator_summary.json") -Raw | ConvertFrom-Json | Select-Object semantic_status,next_action,semantic_blockers
}
```

Expected before edits: both are `VALID_BUT_NOT_GUIDE_STRONG` with `cards_need_guide_claims`.

- [ ] **Step 2: Add focused source-fixture tests**

In `tests/test_strong_fixture_closure.py`, add:

```python
@pytest.mark.parametrize("deck_name", ["MechPala", "PirateRogue"])
def test_source_depth_only_targets_reach_strong_after_fixture_promotion(tmp_path, monkeypatch, deck_name):
    monkeypatch.setattr("hsconfig.cli.fetch_latest_cards", lambda timeout=10.0: [])
    deck = next(row for row in load_archetype_matrix() if row["deck_name"] == deck_name)

    result = prepare_fixture_deck(tmp_path, deck)

    assert result["exit_code"] == 0
    assert result["operator"]["technical_status"] == "VALID_PACKAGE"
    assert result["operator"]["semantic_status"] == "SOURCE_BACKED_STRONG"
    assert result["readiness"]["summary"]["cards_needing_guide_claims"] == 0
    assert result["readiness"]["summary"]["cards_needing_runtime_surface"] == 0
    assert result["readiness"]["summary"]["cards_needing_condition_lowering"] == 0
    assert result["readiness"]["summary"]["cards_needing_mechanic_lowering"] == 0
```

- [ ] **Step 3: Run tests to verify they fail or expose missing depth**

Run:

```powershell
python -m pytest tests/test_strong_fixture_closure.py::test_source_depth_only_targets_reach_strong_after_fixture_promotion -q
```

Expected: fail if fixture depth is insufficient.

- [ ] **Step 4: Research and update MechPala source documents**

Update `tests/fixtures/source_documents_mechpala_strong.json`.

Rules for each added claim:

```json
{
  "claim_kind": "card_role",
  "cards": ["CARD_ID"],
  "stance": "board_scaling",
  "evidence_text_short": "Short source-backed paraphrase from the cited public guide or card text.",
  "source_confidence": "high"
}
```

Use only public HTTPS source URLs in document metadata and claim `source_refs`.

Required MechPala closure:

- every card that was in `cards_needing_guide_claims` gets a card-specific claim
- at least one mulligan keep or discard claim remains
- at least one mech/magnetic/board-scaling claim remains
- no source evidence warnings are introduced

- [ ] **Step 5: Research and update PirateRogue source documents**

Update `tests/fixtures/source_documents_piraterogue_strong.json`.

Required PirateRogue closure:

- every card that was in `cards_needing_guide_claims` gets a card-specific claim
- at least one pirate-package claim exists
- at least one weapon/face/tempo pressure claim exists
- Patches-style forced-draw or discard expectations remain explicit where applicable
- no source evidence warnings are introduced

- [ ] **Step 6: Promote matrix rows only after proof**

After each deck reaches `SOURCE_BACKED_STRONG`, change its row in `docs/operator/archetype-fixture-matrix.json`:

```json
"fixture_stage": "core_source_backed_fixture"
```

- [ ] **Step 7: Run deck proof and tests**

Run:

```powershell
python -m pytest tests/test_archetype_source_fixtures.py tests/test_strong_fixture_closure.py -q
```

Expected: ShadowPriest, MechPala, and PirateRogue pass the strong fixture gate.

- [ ] **Step 8: Update closure doc**

In `docs/operator/source-backed-strong-closure.md`, mark MechPala and PirateRogue as promoted:

```markdown
| MechPala | Promoted to `SOURCE_BACKED_STRONG`; guide-claim gaps closed. |
| PirateRogue | Promoted to `SOURCE_BACKED_STRONG`; guide-claim gaps closed. |
```

- [ ] **Step 9: Commit**

```powershell
git add tests/fixtures/source_documents_mechpala_strong.json tests/fixtures/source_documents_piraterogue_strong.json docs/operator/archetype-fixture-matrix.json docs/operator/source-backed-strong-closure.md tests/test_archetype_source_fixtures.py
git commit -m "test: promote mechpala and piraterogue strong fixtures"
```

---

## Task 4: CtAPaladin And BigShaman Runtime-Surface Closure

**Files:**

- Modify: `tests/fixtures/source_documents_ctapaladin_strong.json`
- Modify: `tests/fixtures/source_documents_bigshaman_strong.json`
- Modify as needed: `src/hsconfig/card_behavior_surface_router.py`
- Modify as needed: `src/hsconfig/config_readiness.py`
- Modify: `tests/test_card_behavior_router.py`
- Modify: `tests/test_config_readiness.py`
- Modify: `docs/operator/archetype-fixture-matrix.json`
- Modify: `docs/operator/source-backed-strong-closure.md`

**Interfaces:**

- Consumes: `card_role`, `mechanic_usage`, and `targeting_rule` claims that pass `claim_can_lower_to_runtime()`.
- Produces: documented CardID rows for recruit/board-flood/big-minion/deathrattle-cheat expectations when VisionAI can express them.

- [ ] **Step 1: Add failing readiness regression for board-flood/recruit roles**

In `tests/test_config_readiness.py`, add:

```python
def test_recruit_and_board_flood_roles_need_runtime_surface_until_lowered():
    report = build_config_readiness_report(
        deck_identity={
            "deck_name": "CtAPaladin",
            "cards": [{"card_id": "CARD_RECRUIT", "name": "Recruit Card", "count": 2}],
        },
        claim_coverage={"uncovered_cards": []},
        gameplan_contract={
            "deck_name": "CtAPaladin",
            "cards": {
                "CARD_RECRUIT": {
                    "card_id": "CARD_RECRUIT",
                    "name": "Recruit Card",
                    "coverage_status": "guide_backed",
                    "roles": ["recruit", "board_flood"],
                    "source_claim_ids": ["claim-recruit"],
                }
            },
        },
        mulligan_plan={"rules": []},
        card_behavior_plan={"rows": [], "suppressed": []},
        combo_plan={"combos": []},
        global_values_authority_matrix={"allowed_step1_overlays": []},
        emitted_cardid_files=[],
    )

    row = report["cards"]["CARD_RECRUIT"]
    assert row["readiness_lane"] == "report_only_supported"
    assert row["first_missing_link"] == "needs_runtime_surface"
```

- [ ] **Step 2: Add router tests for documented lowering**

In `tests/test_card_behavior_router.py`, add:

```python
def test_recruit_board_flood_claim_can_lower_to_play_timing_bonus():
    claims = [
        {
            "claim_kind": "mechanic_usage",
            "cards": ["CARD_RECRUIT"],
            "runtime_block": "BeforePlayCardBonus",
            "runtime_value": "8",
            "condition": "*",
            "evidence_text_short": "Source says the card supports recruit board flood pressure.",
            "source_confidence": "high",
            "claim_readiness": "guide_backed",
            "trust_ceiling": "runtime_lowerable",
        }
    ]

    plan = route_card_behavior_surfaces(claims)

    assert plan["rows"][0]["card_id"] == "CARD_RECRUIT"
    assert plan["rows"][0]["behavior_block"] == "BeforePlayCardBonus"
    assert plan["rows"][0]["meaningful_runtime_surface"] is True
```

- [ ] **Step 3: Run tests**

Run:

```powershell
python -m pytest tests/test_card_behavior_router.py tests/test_config_readiness.py -q
```

Expected: fail if current router does not lower the documented claims.

- [ ] **Step 4: Implement only documented runtime lowering**

In `src/hsconfig/card_behavior_surface_router.py`, ensure `mechanic_usage` and `card_role` claims with supported `runtime_block` lower if all are true:

```python
claim_can_lower_to_runtime(claim) is True
str(claim.get("runtime_block")) in CARD_BEHAVIOR_BLOCKS
claim.get("runtime_value") is not None
```

Do not invent blocks for claims without `runtime_block`.

- [ ] **Step 5: Update CtAPaladin fixture**

Update `tests/fixtures/source_documents_ctapaladin_strong.json`.

Required closure:

- all remaining guide-claim gaps get card-specific claims
- recruit/board-flood claims that are runtime-lowerable specify:
  - `runtime_block`: `"BeforePlayCardBonus"` or another documented block already in the registry
  - `runtime_value`: numeric string
  - `condition`: `"*"` unless source supports a narrower condition
  - `source_confidence`: `"high"` or `"medium"`

- [ ] **Step 6: Update BigShaman fixture**

Update `tests/fixtures/source_documents_bigshaman_strong.json`.

Required closure:

- all remaining guide-claim gaps get card-specific claims
- big/recruit/deathrattle-cheat claims either lower to documented `BeforePlayCardBonus`, `OnBoardBonus`, or `InHandBonus`, or stay report-only with an explicit reason
- if any report-only rows remain, the deck cannot be promoted; keep it `source_informed_valid_fixture`

- [ ] **Step 7: Promote rows only when proof passes**

For each of CtAPaladin and BigShaman, promote to `core_source_backed_fixture` only after:

```powershell
python -m pytest tests/test_strong_fixture_closure.py -q
```

passes for that deck.

- [ ] **Step 8: Run focused tests**

Run:

```powershell
python -m pytest tests/test_card_behavior_router.py tests/test_config_readiness.py tests/test_strong_fixture_closure.py -q
```

- [ ] **Step 9: Commit**

```powershell
git add src/hsconfig/card_behavior_surface_router.py src/hsconfig/config_readiness.py tests/test_card_behavior_router.py tests/test_config_readiness.py tests/fixtures/source_documents_ctapaladin_strong.json tests/fixtures/source_documents_bigshaman_strong.json docs/operator/archetype-fixture-matrix.json docs/operator/source-backed-strong-closure.md
git commit -m "feat: close recruit and big-minion strong fixture surfaces"
```

---

## Task 5: Discolock And Kingslayer Mechanic Closure

**Files:**

- Modify: `tests/fixtures/source_documents_discolock_strong.json`
- Modify: `tests/fixtures/source_documents_kingslayer_strong.json`
- Modify as needed: `src/hsconfig/card_behavior_surface_router.py`
- Modify as needed: `src/hsconfig/config_readiness.py`
- Modify as needed: `src/hsconfig/mulligan_plan.py`
- Modify: `tests/test_card_behavior_router.py`
- Modify: `tests/test_config_readiness.py`
- Modify: `tests/test_mulligan_plan.py`
- Modify: `docs/operator/archetype-fixture-matrix.json`
- Modify: `docs/operator/source-backed-strong-closure.md`

**Interfaces:**

- Consumes: discard, weapon, attack-sequence, and condition-bearing claims.
- Produces: source-backed runtime lowering or explicit report-only blockers.

- [ ] **Step 1: Add discard and weapon router tests**

In `tests/test_card_behavior_router.py`, add:

```python
def test_discard_claim_with_supported_runtime_block_lowers_to_cardid_row():
    claims = [
        {
            "claim_kind": "mechanic_usage",
            "cards": ["DISCARD_PAYOFF"],
            "runtime_block": "BeforePlayCardBonus",
            "runtime_value": "10",
            "condition": "*",
            "evidence_text_short": "Source says this payoff should be played to convert discard pressure.",
            "source_confidence": "high",
            "claim_readiness": "guide_backed",
            "trust_ceiling": "runtime_lowerable",
        }
    ]

    plan = route_card_behavior_surfaces(claims)

    assert plan["rows"][0]["card_id"] == "DISCARD_PAYOFF"
    assert plan["rows"][0]["behavior_block"] == "BeforePlayCardBonus"


def test_weapon_attack_claim_with_supported_runtime_block_lowers_to_attack_bonus():
    claims = [
        {
            "claim_kind": "targeting_rule",
            "cards": ["WEAPON_CARD"],
            "runtime_block": "BeforePhysicalAttackBonus",
            "runtime_value": "12",
            "condition": "my_target(count(),hero=true) > 0",
            "evidence_text_short": "Source says the weapon plan is face pressure.",
            "source_confidence": "high",
            "claim_readiness": "guide_backed",
            "trust_ceiling": "runtime_lowerable",
        }
    ]

    plan = route_card_behavior_surfaces(claims)

    assert plan["rows"][0]["behavior_block"] == "BeforePhysicalAttackBonus"
    assert plan["rows"][0]["condition"] == "my_target(count(),hero=true) > 0"
```

- [ ] **Step 2: Add unsupported condition regression**

In `tests/test_mulligan_plan.py`, add:

```python
def test_unsupported_mulligan_condition_stays_report_visible():
    claims = [
        {
            "claim_kind": "mulligan_keep",
            "cards": ["CARD_A"],
            "selector": "CARD_A",
            "selector_kind": "card",
            "stance": "keep",
            "condition": "unsupported_custom_condition",
            "evidence_text_short": "Source says keep this card in a narrow setup.",
            "source_confidence": "high",
            "claim_readiness": "guide_backed",
            "trust_ceiling": "runtime_lowerable",
        }
    ]

    plan = compile_mulligan_plan(claims)

    assert plan["unsupported_conditions"]
    assert plan["unsupported_conditions"][0]["card"] == "CARD_A"
```

- [ ] **Step 3: Run failing/focused tests**

Run:

```powershell
python -m pytest tests/test_card_behavior_router.py tests/test_mulligan_plan.py tests/test_config_readiness.py -q
```

- [ ] **Step 4: Update Discolock source documents**

Update `tests/fixtures/source_documents_discolock_strong.json`.

Required closure:

- all remaining guide-claim gaps get card-specific claims
- discard payoff claims specify either documented CardID lowering or explicit report-only reason
- no unsupported conditions remain in runtime-lowerable claims
- if discard semantics cannot be expressed in VisionAI without overclaiming, keep Discolock `source_informed_valid_fixture` and document the exact reason

- [ ] **Step 5: Update Kingslayer source documents**

Update `tests/fixtures/source_documents_kingslayer_strong.json`.

Required closure:

- all remaining guide-claim gaps get card-specific claims
- weapon upkeep and face-pressure claims lower through documented CardID blocks where supported
- unsupported mulligan or behavior conditions are rewritten to documented VisionAI expressions or kept report-only

- [ ] **Step 6: Run strong proof**

Run:

```powershell
python -m pytest tests/test_strong_fixture_closure.py tests/test_archetype_source_fixtures.py -q
```

Promote only the deck rows that now pass.

- [ ] **Step 7: Commit**

```powershell
git add src/hsconfig/card_behavior_surface_router.py src/hsconfig/config_readiness.py src/hsconfig/mulligan_plan.py tests/test_card_behavior_router.py tests/test_config_readiness.py tests/test_mulligan_plan.py tests/fixtures/source_documents_discolock_strong.json tests/fixtures/source_documents_kingslayer_strong.json docs/operator/archetype-fixture-matrix.json docs/operator/source-backed-strong-closure.md
git commit -m "feat: close discard and weapon fixture blockers"
```

---

## Task 6: Remaining Deck Closure

**Files:**

- Modify: `tests/fixtures/source_documents_treantdruid_strong.json`
- Modify: `tests/fixtures/source_documents_imbuemage_strong.json`
- Modify: `tests/fixtures/source_documents_boarlock_strong.json`
- Modify: `tests/fixtures/source_documents_piratedh_strong.json`
- Modify as needed: runtime lowering modules and tests from earlier tasks
- Modify: `docs/operator/archetype-fixture-matrix.json`
- Modify: `docs/operator/source-backed-strong-closure.md`

**Interfaces:**

- Consumes: all runtime lowerers added in Tasks 4 and 5.
- Produces: final promoted strong rows or honest source-informed rows with documented non-closure reason.

- [ ] **Step 1: Run blocker extraction for remaining decks**

Run:

```powershell
$root = Join-Path $env:TEMP 'hsconfig-strong-task6'
Remove-Item -LiteralPath $root -Recurse -Force -ErrorAction SilentlyContinue
$matrix = Get-Content docs\operator\archetype-fixture-matrix.json -Raw | ConvertFrom-Json
foreach ($name in 'TreantDruid','ImbueMage','Boarlock','PirateDH') {
  $deck = $matrix.decks | Where-Object deck_name -eq $name
  python -m hsconfig prepare --deck-name $deck.deck_name --deck-code $deck.deck_code --runtime-root (Join-Path $root 'runtime') --out (Join-Path $root $name) --source-documents-json ("tests\fixtures\source_documents_" + $name.ToLower() + "_strong.json") --json | Out-Null
  $summary = Get-Content (Join-Path $root "$name\reports\operator_summary.json") -Raw | ConvertFrom-Json
  [pscustomobject]@{
    deck = $name
    semantic = $summary.semantic_status
    blockers = (($summary.semantic_blockers | ForEach-Object { $_.reason }) -join ',')
    guide = $summary.guide_strength_summary.cards_needing_guide_claims
    runtime = $summary.guide_strength_summary.cards_needing_runtime_surface
    mechanic = $summary.guide_strength_summary.cards_needing_mechanic_lowering
    combo = $summary.guide_strength_summary.cards_needing_combo_sequence
  }
}
```

- [ ] **Step 2: Close TreantDruid**

Update `tests/fixtures/source_documents_treantdruid_strong.json`.

Required closure:

- card-specific claims for missing guide cards
- token-board, treant, and board-buff claims lower to documented `OnBoardBonus`, `BeforePlayCardBonus`, or `InHandBonus` where supported
- unsupported claims remain report-only and block promotion if not lowerable

- [ ] **Step 3: Close ImbueMage**

Update `tests/fixtures/source_documents_imbuemage_strong.json`.

Required closure:

- card-specific claims for missing guide cards
- hero-power and spell-generation expectations either map to documented `BeforeUseHeroPowerBonus`, Discover/option blocks, or remain report-only
- no generated-entity CardID is invented without structured card metadata or source-backed static semantics

- [ ] **Step 4: Close Boarlock**

Update `tests/fixtures/source_documents_boarlock_strong.json`.

Required closure:

- card-specific claims for missing guide cards
- exact `combo_sequence` claims only when source supports ordered cards, `timing_kind`, `operator`, and `values`
- vague combo/control/resource claims remain report-only and block promotion if exact sequence is not available

- [ ] **Step 5: Close PirateDH**

Update `tests/fixtures/source_documents_piratedh_strong.json`.

Required closure:

- card-specific claims for missing guide cards
- pirate, hero-attack, and tempo-pressure claims lower through documented CardID blocks where supported
- Demon Hunter hero-attack posture must not be collapsed into generic PirateRogue weapon assumptions

- [ ] **Step 6: Promote or document each remaining deck**

For each deck:

If `test_strong_fixture_closure.py` passes, set:

```json
"fixture_stage": "core_source_backed_fixture"
```

If it cannot pass without unsupported or speculative lowering, keep:

```json
"fixture_stage": "source_informed_valid_fixture"
```

and write the exact reason in `docs/operator/source-backed-strong-closure.md`.

- [ ] **Step 7: Run tests**

Run:

```powershell
python -m pytest tests/test_strong_fixture_closure.py tests/test_archetype_fixture_e2e.py tests/test_archetype_source_fixtures.py -q
```

- [ ] **Step 8: Commit**

```powershell
git add tests/fixtures/source_documents_treantdruid_strong.json tests/fixtures/source_documents_imbuemage_strong.json tests/fixtures/source_documents_boarlock_strong.json tests/fixtures/source_documents_piratedh_strong.json docs/operator/archetype-fixture-matrix.json docs/operator/source-backed-strong-closure.md tests/test_strong_fixture_closure.py tests/test_archetype_source_fixtures.py
git diff --name-only
git commit -m "test: close remaining source-backed fixture targets"
```

After `git diff --name-only`, stage any runtime-lowering modules and focused tests that were actually modified in this task. Do not stage the entire `src/hsconfig` or `tests` trees without reviewing the changed file list.

---

## Task 7: Legacy Surface And Docs Polish

**Files:**

- Modify: `README.md`
- Modify: `.agents/skills/hsconfig/SKILL.md`
- Modify: `.agents/skills/hsconfig/references/workflow.md`
- Modify: `.agents/skills/hsconfig/references/visionai-surfaces.md`
- Modify: `.agents/skills/hsconfig/references/guide-research-policy.md`
- Modify: `.agents/skills/hsconfig/references/card-behavior-policy.md`
- Modify: `tests/test_skill_files.py`
- Optional modify/delete after usage check: `src/hsconfig/compile_optional_surfaces.py`
- Optional modify/delete after usage check: `tests/test_compile_optional_surfaces.py`

**Interfaces:**

- Consumes: final fixture stages and closure doc.
- Produces: active docs that explain the source-backed strong contract without duplicating stale optional-surface claims.

- [ ] **Step 1: Add docs tests for fixture-stage truth**

In `tests/test_skill_files.py`, add:

```python
def test_skill_docs_explain_strong_fixture_truth_contract():
    docs = "\n".join(
        [
            Path("README.md").read_text(encoding="utf-8"),
            Path(".agents/skills/hsconfig/SKILL.md").read_text(encoding="utf-8"),
            Path(".agents/skills/hsconfig/references/workflow.md").read_text(encoding="utf-8"),
        ]
    )

    assert "SOURCE_BACKED_STRONG" in docs
    assert "operator_summary.json" in docs
    assert "single operator gate" in docs.lower()
    assert "Presume.json" in docs
    assert "Concede.json" in docs
    assert "not emit" in docs.lower() or "not part of the normal path" in docs.lower()
```

- [ ] **Step 2: Search legacy optional-surface usage**

Run:

```powershell
rg -n "compile_optional_surfaces|compile_presume|compile_concede|Presume.json|Concede.json" src tests README.md .agents docs
```

Decision:

- If `compile_optional_surfaces.py` is only tested as gated legacy support and not used by normal CLI, keep it but mark it legacy in module docstring and tests.
- If it is unused and creates confusion, delete it and delete/replace tests that assert runtime support for Presume/Concede.
- Do not remove validator support if other tests intentionally require `supported_surface("Presume.json")` and `supported_surface("Concede.json")` as legacy-known surfaces.

- [ ] **Step 3: Update docs**

Docs must say:

```markdown
HSConfig normal output is limited to `GlobalValues.json`, `Mulligan.json`, per-card `<CARDID>.json`, and `Combo.json` only when an exact sequence is source-backed. `Presume.json` and `Concede.json` are documented HearthRanger surfaces, but HSConfig does not emit them in the normal path.
```

Docs must also say:

```markdown
`core_source_backed_fixture` means the fixture produces `SOURCE_BACKED_STRONG`. `source_informed_valid_fixture` means it produces a valid package but still has source-depth or lowering gaps.
```

- [ ] **Step 4: Sync installed skill**

Run:

```powershell
python scripts\sync_installed_skill.py
python scripts\sync_installed_skill.py --check
```

Expected:

```text
HSConfig skill is in sync
```

- [ ] **Step 5: Run docs tests**

Run:

```powershell
python -m pytest tests/test_skill_files.py -q
```

- [ ] **Step 6: Commit**

```powershell
git add README.md .agents/skills/hsconfig tests/test_skill_files.py src/hsconfig/compile_optional_surfaces.py tests/test_compile_optional_surfaces.py
git commit -m "docs: clarify strong fixture and legacy surface boundaries"
```

If `compile_optional_surfaces.py` was not modified, omit it from `git add`.

---

## Task 8: Final 11-Deck Proof And GitHub Update

**Files:**

- No planned source edits.
- Verify all touched files from prior tasks.

**Interfaces:**

- Consumes: final matrix, fixtures, docs, tests.
- Produces: green test evidence and synced `origin/main`.

- [ ] **Step 1: Run research validation**

Run:

```powershell
python C:\Users\darbo\.codex\skills\research\validate_json.py -f docs\research\2026-07-07-hsconfig-skill-audit\fields.yaml -j docs\research\2026-07-07-hsconfig-skill-audit\results\HearthRanger_VisionAI_Runtime_Surface_Contract.json docs\research\2026-07-07-hsconfig-skill-audit\results\Hearthstone_Card_Identity_And_Static_Semantics.json docs\research\2026-07-07-hsconfig-skill-audit\results\Source-Backed_Guide_Claim_Depth.json docs\research\2026-07-07-hsconfig-skill-audit\results\Multi-Archetype_Deck_Coverage_Matrix.json docs\research\2026-07-07-hsconfig-skill-audit\results\Lean_Skill_Boundary_And_Operator_UX.json
```

Expected:

```text
Validation passed: 5/5
Average coverage: 100.0%
```

- [ ] **Step 2: Run targeted suite**

Run:

```powershell
python -m pytest tests/test_strong_fixture_closure.py tests/test_fixture_stage_semantics.py tests/test_archetype_fixture_e2e.py tests/test_archetype_fixture_matrix.py tests/test_archetype_source_fixtures.py tests/test_card_behavior_router.py tests/test_config_readiness.py tests/test_mulligan_plan.py tests/test_operator_summary.py tests/test_skill_files.py -q
```

Expected: all pass.

- [ ] **Step 3: Run full suite**

Run:

```powershell
python -m pytest -q
```

Expected: all pass.

- [ ] **Step 4: Run explicit 11-deck prepare proof**

Run:

```powershell
$matrix = Get-Content docs\operator\archetype-fixture-matrix.json -Raw | ConvertFrom-Json
$root = Join-Path $env:TEMP 'hsconfig-final-11deck-proof'
$runtime = Join-Path $env:TEMP 'hsconfig-final-11deck-runtime'
Remove-Item -LiteralPath $root -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $runtime -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $root -Force | Out-Null
$rows = @()
foreach ($deck in $matrix.decks) {
  $fixture = "tests\fixtures\source_documents_$($deck.deck_name.ToLower())_strong.json"
  $out = Join-Path $root $deck.deck_name
  python -m hsconfig prepare --deck-name $deck.deck_name --deck-code $deck.deck_code --runtime-root $runtime --out $out --source-documents-json $fixture --json | Out-Null
  $summary = Get-Content (Join-Path $out 'reports\operator_summary.json') -Raw | ConvertFrom-Json
  $files = Get-ChildItem (Join-Path $out 'CustomConfig') -Recurse -File | Select-Object -ExpandProperty Name
  $rows += [pscustomobject]@{
    deck = $deck.deck_name
    fixture_stage = $deck.fixture_stage
    technical = $summary.technical_status
    semantic = $summary.semantic_status
    next_action = $summary.next_action
    blocker_count = @($summary.semantic_blockers).Count
    has_presume = [bool]($files -contains 'Presume.json')
    has_concede = [bool]($files -contains 'Concede.json')
  }
}
$rows | ConvertTo-Json
```

Expected:

- every row has `technical=VALID_PACKAGE`
- every `core_source_backed_fixture` row has `semantic=SOURCE_BACKED_STRONG`
- every `core_source_backed_fixture` row has `next_action=READY_TO_APPLY_OR_HANDOFF`
- no row has `has_presume=true`
- no row has `has_concede=true`

- [ ] **Step 5: Verify installed skill sync**

Run:

```powershell
python scripts\sync_installed_skill.py --check
```

Expected:

```text
HSConfig skill is in sync
```

- [ ] **Step 6: Inspect git state**

Run:

```powershell
git status --short --branch
git log --oneline -8
```

Expected: clean branch with task commits.

- [ ] **Step 7: Merge and push**

If working on a feature branch:

```powershell
git switch main
git pull --ff-only origin main
git merge --ff-only <feature-branch-name>
python -m pytest -q
python scripts\sync_installed_skill.py --check
git push origin main
```

If already on `main`, run:

```powershell
python -m pytest -q
python scripts\sync_installed_skill.py --check
git push origin main
```

Expected:

```text
main -> main
```

---

## Execution Notes

Recommended order:

1. Task 1: add hard truth gates.
2. Task 2: make the matrix honest before closing more decks.
3. Task 3: close the easiest source-depth-only decks, MechPala and PirateRogue.
4. Task 4: close recruit/big-minion runtime-surface decks.
5. Task 5: close discard and weapon mechanics.
6. Task 6: close remaining decks or document why a deck remains source-informed only.
7. Task 7: polish docs and legacy surface wording.
8. Task 8: final proof, merge, push.

Do not dispatch all deck fixture edits as parallel write tasks unless each worker owns exactly one fixture file and no shared tests or matrix edits. Shared files (`docs/operator/archetype-fixture-matrix.json`, test helpers, docs, lowering modules) need a single coordinator.

## Self-Review

Spec coverage:

- The plan preserves HSConfig's lean boundary and excludes HSTuner surfaces.
- The plan makes `core_source_backed_fixture` semantically honest.
- The plan keeps `SOURCE_BACKED_STRONG` strict.
- The plan routes source depth through structured source documents and `claim_can_lower_to_runtime()`.
- The plan covers all 11 user-provided decks.
- The plan includes Presume/Concede normal-path exclusion.
- The plan includes final full-suite, 11-deck proof, skill-sync, and git push gates.

Placeholder scan:

- No `TBD`, `TODO`, or undefined future task remains.
- Source claim authoring requires public-source research during implementation, but each required field, runtime-lowering rule, and pass/fail gate is explicit.
- Where a deck cannot honestly become strong, the plan explicitly keeps it `source_informed_valid_fixture` instead of weakening tests.

Type consistency:

- `load_archetype_matrix() -> list[dict[str, Any]]` and `prepare_fixture_deck(tmp_path: Path, deck: dict[str, Any]) -> dict[str, Any]` are introduced before later tests use them.
- Fixture-stage names are consistent across Task 2 and later tasks.
- Operator status values match existing HSConfig statuses: `VALID_PACKAGE`, `SOURCE_BACKED_STRONG`, `VALID_BUT_NOT_GUIDE_STRONG`, `READY_TO_APPLY_OR_HANDOFF`, and `IMPROVE_GUIDE_SOURCES_BEFORE_STRONG_APPLY`.

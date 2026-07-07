# HSConfig 7-Deck Source-Depth Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the seven remaining `source_informed_valid_fixture` rows so HSConfig either promotes them to `SOURCE_BACKED_STRONG` with evidence or exposes one exact missing source-to-runtime link per deck.

**Architecture:** Keep HSConfig as a lean pre-run CustomConfig generator. Add a small deck-matrix closure index over existing reports, then strengthen the seven existing source fixtures and runtime-lowering surfaces in place. Promote matrix rows only after `prepare_fixture_deck()` proves `VALID_PACKAGE`, `SOURCE_BACKED_STRONG`, no semantic blockers, no missing card links, and no blocked normal-path surfaces.

**Tech Stack:** Python 3.11+, pytest, argparse, existing `hearthstone>=9.0.0`, local JSON/Markdown fixtures, no new runtime dependencies.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig` for `Teufelsboy/HSConfig`.
- HSConfig is pre-run only: no replay parsing, no HDT parsing, no winrate validation, no candidate promotion, no runtime evidence analysis, and no post-run tuning.
- Normal generated runtime files remain `GlobalValues.json`, `Mulligan.json`, per-card `<CARDID>.json`, and `Combo.json` only when an exact valid combo sequence exists.
- Do not emit `Presume.json` or `Concede.json` in the normal path.
- Preserve exact deck identities, CardIDs, deck codes, HS IDs, and HDT deck IDs from `docs/operator/archetype-fixture-matrix.json`.
- Preserve full `GlobalValues.json` key profiling.
- Preserve every card covered in the gameplan contract.
- Preserve row-level provenance for generated config rows.
- `reports/operator_summary.json` remains the single normal operator gate.
- Lower-level reports explain the gate; they do not grant independent apply permission.
- Do not add new representative decks until the seven existing source-informed rows are either promoted or explicitly blocked with a first missing chain.
- Do not add runtime dependencies.
- Keep docs short: normal operator path starts at `README.md` -> `docs/operator/README.md`.

---

## File Structure

### Create

- `src/hsconfig/source_depth_closure_index.py`
  - Pure helper that summarizes matrix rows plus per-deck report facts into one deck-level closure table.
  - Does not run `prepare`; it only consumes already-built report dictionaries.

- `tests/test_source_depth_closure_index.py`
  - Unit tests for closure-index behavior.

- `tests/test_fixture_source_depth_closure.py`
  - Parametrized end-to-end tests for the seven source-informed matrix rows.
  - Starts permissive by asserting every row has a deterministic first missing link.
  - Becomes strict as each row is promoted.

### Modify

- `tests/helpers/fixture_prepare.py`
  - Ensure helper returns `operator_summary`, `source_claim_gap_report`, `strong_promotion_report`, `per_card_config_readiness_report`, generated files, and output paths for all matrix rows.

- `docs/operator/archetype-fixture-matrix.json`
  - Promote rows from `source_informed_valid_fixture` to `core_source_backed_fixture` only after tests prove strong readiness.
  - Update `strongness_visibility.first_strongness_gap` to `none` and `operator_action` to `keep_as_core_control_fixture` only for proven rows.

- `tests/test_archetype_fixture_matrix.py`
  - Update expected fixture stages only when the implementation proves promotion.

- `tests/fixtures/source_documents_ctapaladin_strong.json`
- `tests/fixtures/source_documents_discolock_strong.json`
- `tests/fixtures/source_documents_treantdruid_strong.json`
- `tests/fixtures/source_documents_imbuemage_strong.json`
- `tests/fixtures/source_documents_kingslayer_strong.json`
- `tests/fixtures/source_documents_boarlock_strong.json`
- `tests/fixtures/source_documents_piratedh_strong.json`
  - Strengthen source claims, source confidence, claim readiness, runtime blocks, runtime values, card references, and exact combo details where evidence supports runtime lowering.

- `src/hsconfig/config_readiness.py`
  - Add narrowly scoped readiness handling only when a source fixture proves the existing model cannot represent a valid Hearthstone mechanic.

- `src/hsconfig/source_claim_gap_report.py`
  - Add missing-link categories only if an existing category cannot express the first real blocker.

- `src/hsconfig/strong_promotion_report.py`
  - Preserve current gate; only add clearer deck-level fields if the closure index needs them.

- `docs/operator/source-backed-strong-closure.md`
  - Document the seven-row closure rules and when a row may be promoted.

---

### Task 1: Add Deck-Level Source-Depth Closure Index

**Files:**
- Create: `src/hsconfig/source_depth_closure_index.py`
- Create: `tests/test_source_depth_closure_index.py`

**Interfaces:**
- Consumes: `matrix: dict[str, Any]`
- Consumes: `deck_reports: dict[str, dict[str, Any]]` where each deck report may include `operator_summary`, `source_claim_gap_report`, `strong_promotion_report`, and `config_readiness_report`.
- Produces: `build_source_depth_closure_index(matrix: dict[str, Any], deck_reports: dict[str, dict[str, Any]]) -> dict[str, Any]`

- [ ] **Step 1: Write failing tests**

Create `tests/test_source_depth_closure_index.py`:

```python
from hsconfig.source_depth_closure_index import build_source_depth_closure_index


def test_index_reports_first_missing_link_for_source_informed_rows():
    matrix = {
        "decks": [
            {
                "deck_name": "CtAPaladin",
                "fixture_stage": "source_informed_valid_fixture",
                "strongness_visibility": {
                    "first_strongness_gap": "needs_recruit_aura_runtime_surface_closure",
                    "operator_action": "close_existing_source_informed_fixture",
                },
            },
            {
                "deck_name": "ShadowPriest",
                "fixture_stage": "core_source_backed_fixture",
                "strongness_visibility": {
                    "first_strongness_gap": "none",
                    "operator_action": "keep_as_core_control_fixture",
                },
            },
        ]
    }
    report = build_source_depth_closure_index(
        matrix,
        {
            "CtAPaladin": {
                "operator_summary": {
                    "technical_status": "VALID_PACKAGE",
                    "semantic_status": "VALID_BUT_NOT_GUIDE_STRONG",
                    "next_action": "IMPROVE_GUIDE_SOURCES_BEFORE_STRONG_APPLY",
                },
                "source_claim_gap_report": {
                    "summary": {
                        "blocked_cards": 2,
                        "first_missing_chain": {
                            "card_id": "AT_075",
                            "name": "Warhorse Trainer",
                            "first_missing_link": "needs_runtime_surface",
                            "next_action": "add_runtime_lowerable_claim_or_router_support",
                        },
                    }
                },
                "strong_promotion_report": {
                    "promotion_ready": False,
                    "verdict": "PROMOTION_BLOCKED",
                },
            },
            "ShadowPriest": {
                "operator_summary": {
                    "technical_status": "VALID_PACKAGE",
                    "semantic_status": "SOURCE_BACKED_STRONG",
                    "next_action": "READY_TO_APPLY_OR_HANDOFF",
                },
                "source_claim_gap_report": {
                    "summary": {
                        "blocked_cards": 0,
                        "first_missing_chain": None,
                    }
                },
                "strong_promotion_report": {
                    "promotion_ready": True,
                    "verdict": "SOURCE_BACKED_STRONG_CONFIRMED",
                },
            },
        },
    )

    assert report["summary"] == {
        "total_decks": 2,
        "core_source_backed_fixture": 1,
        "source_informed_valid_fixture": 1,
        "promotion_ready": 1,
        "promotion_blocked": 1,
    }
    cta = report["decks"]["CtAPaladin"]
    assert cta["first_missing_chain"]["card_id"] == "AT_075"
    assert cta["first_matrix_gap"] == "needs_recruit_aura_runtime_surface_closure"
    assert cta["next_action"] == "close_first_missing_chain"
    shadow = report["decks"]["ShadowPriest"]
    assert shadow["first_missing_chain"] is None
    assert shadow["next_action"] == "keep_as_core_control_fixture"


def test_index_uses_matrix_gap_when_reports_are_missing():
    matrix = {
        "decks": [
            {
                "deck_name": "PirateDH",
                "fixture_stage": "source_informed_valid_fixture",
                "strongness_visibility": {
                    "first_strongness_gap": "needs_hero_attack_runtime_surface_closure",
                    "operator_action": "close_existing_source_informed_fixture",
                },
            }
        ]
    }

    report = build_source_depth_closure_index(matrix, {})

    assert report["decks"]["PirateDH"]["report_status"] == "missing_reports"
    assert report["decks"]["PirateDH"]["first_matrix_gap"] == "needs_hero_attack_runtime_surface_closure"
    assert report["decks"]["PirateDH"]["next_action"] == "run_prepare_fixture_and_collect_reports"
```

- [ ] **Step 2: Run the failing test**

Run:

```powershell
python -m pytest tests/test_source_depth_closure_index.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'hsconfig.source_depth_closure_index'`.

- [ ] **Step 3: Implement the helper**

Create `src/hsconfig/source_depth_closure_index.py`:

```python
from __future__ import annotations

from collections import Counter
from typing import Any


def build_source_depth_closure_index(
    matrix: dict[str, Any],
    deck_reports: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    rows = matrix.get("decks", [])
    if not isinstance(rows, list):
        rows = []

    summary: Counter[str] = Counter()
    decks: dict[str, dict[str, Any]] = {}

    for row in rows:
        if not isinstance(row, dict):
            continue
        deck_name = str(row.get("deck_name", ""))
        fixture_stage = str(row.get("fixture_stage", ""))
        visibility = row.get("strongness_visibility", {})
        if not isinstance(visibility, dict):
            visibility = {}
        reports = deck_reports.get(deck_name, {})
        operator = reports.get("operator_summary", {})
        gap_report = reports.get("source_claim_gap_report", {})
        promotion = reports.get("strong_promotion_report", {})

        summary[fixture_stage] += 1
        first_chain = _first_missing_chain(gap_report)
        promotion_ready = bool(promotion.get("promotion_ready") is True)
        if promotion_ready:
            summary["promotion_ready"] += 1
        else:
            summary["promotion_blocked"] += 1

        report_status = "available" if reports else "missing_reports"
        decks[deck_name] = {
            "deck_name": deck_name,
            "fixture_stage": fixture_stage,
            "report_status": report_status,
            "technical_status": operator.get("technical_status"),
            "semantic_status": operator.get("semantic_status"),
            "first_matrix_gap": str(visibility.get("first_strongness_gap", "")),
            "promotion_ready": promotion_ready,
            "first_missing_chain": first_chain,
            "next_action": _next_action(
                fixture_stage=fixture_stage,
                report_status=report_status,
                promotion_ready=promotion_ready,
                first_missing_chain=first_chain,
            ),
        }

    return {
        "schema_version": 1,
        "summary": {
            "total_decks": len(decks),
            "core_source_backed_fixture": summary["core_source_backed_fixture"],
            "source_informed_valid_fixture": summary["source_informed_valid_fixture"],
            "promotion_ready": summary["promotion_ready"],
            "promotion_blocked": summary["promotion_blocked"],
        },
        "decks": decks,
    }


def _first_missing_chain(gap_report: Any) -> dict[str, Any] | None:
    if not isinstance(gap_report, dict):
        return None
    summary = gap_report.get("summary", {})
    if not isinstance(summary, dict):
        return None
    chain = summary.get("first_missing_chain")
    return chain if isinstance(chain, dict) else None


def _next_action(
    *,
    fixture_stage: str,
    report_status: str,
    promotion_ready: bool,
    first_missing_chain: dict[str, Any] | None,
) -> str:
    if report_status == "missing_reports":
        return "run_prepare_fixture_and_collect_reports"
    if promotion_ready and fixture_stage == "core_source_backed_fixture":
        return "keep_as_core_control_fixture"
    if promotion_ready:
        return "promote_fixture_row_to_core_source_backed"
    if first_missing_chain is not None:
        return "close_first_missing_chain"
    return "inspect_operator_summary_and_gap_reports"
```

- [ ] **Step 4: Run focused test**

Run:

```powershell
python -m pytest tests/test_source_depth_closure_index.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/hsconfig/source_depth_closure_index.py tests/test_source_depth_closure_index.py
git commit -m "feat: add source-depth closure index"
```

---

### Task 2: Add Seven-Deck Closure Fixture Test Harness

**Files:**
- Modify: `tests/helpers/fixture_prepare.py`
- Create: `tests/test_fixture_source_depth_closure.py`

**Interfaces:**
- Consumes: `load_archetype_matrix() -> list[dict[str, Any]]`
- Consumes: `prepare_fixture_deck(tmp_path: Path, deck: dict[str, Any]) -> dict[str, Any]`
- Produces: test evidence that each source-informed row either has `promotion_ready=True` or an exact first missing chain.

- [ ] **Step 1: Inspect current helper shape**

Run:

```powershell
Get-Content -Raw tests\helpers\fixture_prepare.py
```

Expected: helper returns report dictionaries for `operator`, `readiness`, and generated files. If it already returns `source_claim_gap_report` and `strong_promotion_report`, do not change it.

- [ ] **Step 2: Write failing harness test**

Create `tests/test_fixture_source_depth_closure.py`:

```python
from __future__ import annotations

import pytest

from tests.helpers.fixture_prepare import load_archetype_matrix, prepare_fixture_deck


SOURCE_INFORMED_DECKS = {
    "CtAPaladin",
    "Discolock",
    "TreantDruid",
    "ImbueMage",
    "Kingslayer",
    "Boarlock",
    "PirateDH",
}


@pytest.mark.parametrize(
    "deck",
    [row for row in load_archetype_matrix() if row["deck_name"] in SOURCE_INFORMED_DECKS],
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

- [ ] **Step 3: Run the failing test**

Run:

```powershell
python -m pytest tests/test_fixture_source_depth_closure.py -q
```

Expected: FAIL only if `prepare_fixture_deck()` does not return `source_claim_gap_report` or `strong_promotion_report`.

- [ ] **Step 4: Extend helper minimally if needed**

If needed, edit `tests/helpers/fixture_prepare.py` so `prepare_fixture_deck()` returns:

```python
        "source_claim_gap_report": read_json(out / "reports" / "source_claim_gap_report.json"),
        "strong_promotion_report": read_json(out / "reports" / "strong_promotion_report.json"),
```

Preserve all existing return keys.

- [ ] **Step 5: Run harness test**

Run:

```powershell
python -m pytest tests/test_fixture_source_depth_closure.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add tests/helpers/fixture_prepare.py tests/test_fixture_source_depth_closure.py
git commit -m "test: add source-informed fixture closure harness"
```

---

### Task 3: Close CtAPaladin And TreantDruid Board-Wide Runtime Surfaces

**Files:**
- Modify: `tests/fixtures/source_documents_ctapaladin_strong.json`
- Modify: `tests/fixtures/source_documents_treantdruid_strong.json`
- Modify: `src/hsconfig/config_readiness.py` only if existing readiness lanes cannot represent recruit, token-board, or aura/buff lowering.
- Modify: `tests/test_archetype_source_fixtures.py`
- Test: `tests/test_strong_fixture_closure.py`

**Interfaces:**
- Produces: CtAPaladin and TreantDruid prepare runs with zero `cards_needing_runtime_surface`, zero `cards_needing_mechanic_lowering`, and no semantic blockers.

- [ ] **Step 1: Add focused failing assertions**

Extend `tests/test_archetype_source_fixtures.py`:

```python
def test_ctapaladin_source_fixture_has_runtime_lowerable_recruit_and_aura_claims():
    claims = _claims("CtAPaladin")
    assert any(
        claim["claim_kind"] == "mechanic_usage"
        and claim.get("mechanic") == "recruit"
        and claim.get("runtime_block") == "BeforePlayCardBonus"
        and claim.get("runtime_value")
        for claim in claims
    )
    assert any(
        claim["claim_kind"] in {"mechanic_usage", "targeting_rule"}
        and str(claim.get("stance", "")).lower() in {"board_flood", "aura_pressure", "wide_board_pressure"}
        and claim.get("runtime_block") in {"BeforePlayCardBonus", "OnBoardBonus"}
        and claim.get("runtime_value")
        for claim in claims
    )


def test_treantdruid_source_fixture_has_runtime_lowerable_token_and_board_buff_claims():
    claims = _claims("TreantDruid")
    assert any(
        claim["claim_kind"] == "mechanic_usage"
        and claim.get("mechanic") in {"treant", "token_board"}
        and claim.get("runtime_block") == "BeforePlayCardBonus"
        and claim.get("runtime_value")
        for claim in claims
    )
    assert any(
        claim["claim_kind"] == "mechanic_usage"
        and claim.get("mechanic") == "board_buff"
        and claim.get("runtime_block") in {"BeforePlayCardBonus", "OnBoardBonus"}
        and claim.get("runtime_value")
        for claim in claims
    )
```

- [ ] **Step 2: Run focused tests**

Run:

```powershell
python -m pytest tests/test_archetype_source_fixtures.py::test_ctapaladin_source_fixture_has_runtime_lowerable_recruit_and_aura_claims tests/test_archetype_source_fixtures.py::test_treantdruid_source_fixture_has_runtime_lowerable_token_and_board_buff_claims -q
```

Expected: FAIL if source fixtures do not yet include runtime-lowerable claims.

- [ ] **Step 3: Strengthen source documents**

Edit the CtAPaladin and TreantDruid source fixtures. For each runtime-lowerable claim, include:

```json
{
  "claim_kind": "mechanic_usage",
  "cards": ["<real_card_id>"],
  "mechanic": "<recruit_or_board_buff_family>",
  "stance": "<deck_specific_stance>",
  "runtime_block": "BeforePlayCardBonus",
  "runtime_value": "7",
  "claim_readiness": "source_backed_static_semantics",
  "source_confidence": "medium",
  "evidence_text_short": "<short source-backed statement>",
  "source_refs": ["<public_https_source_url_or_document_ref>"]
}
```

Use only real CardIDs from the decoded deck and public HTTPS source refs already accepted by `tests/test_archetype_source_fixtures.py`.

- [ ] **Step 4: Add readiness support only if required**

If the prepare output still reports `needs_mechanic_lowering` for these claims, add the exact mechanic roles to `MECHANIC_LOWERING_ROLES` or to a smaller dedicated allowlist in `src/hsconfig/config_readiness.py`. The change must be backed by a failing test from this task and must not make report-only unsupported claims look runtime-safe.

- [ ] **Step 5: Run source and closure tests**

Run:

```powershell
python -m pytest tests/test_archetype_source_fixtures.py tests/test_fixture_source_depth_closure.py tests/test_strong_fixture_closure.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add tests/fixtures/source_documents_ctapaladin_strong.json tests/fixtures/source_documents_treantdruid_strong.json src/hsconfig/config_readiness.py tests/test_archetype_source_fixtures.py tests/test_fixture_source_depth_closure.py tests/test_strong_fixture_closure.py
git commit -m "feat: close board-wide source depth fixtures"
```

---

### Task 4: Close Kingslayer And PirateDH Attack-Pressure Runtime Surfaces

**Files:**
- Modify: `tests/fixtures/source_documents_kingslayer_strong.json`
- Modify: `tests/fixtures/source_documents_piratedh_strong.json`
- Modify: `src/hsconfig/config_readiness.py` only if existing attack/weapon roles cannot distinguish runtime-lowerable claims from report-only claims.
- Modify: `tests/test_archetype_source_fixtures.py`

**Interfaces:**
- Produces: weapon, physical attack, hero attack, and face-pressure claims that lower to documented normal CardID surfaces.

- [ ] **Step 1: Add focused failing assertions**

Add:

```python
def test_kingslayer_fixture_has_runtime_lowerable_weapon_sequence_claims():
    claims = _claims("Kingslayer")
    assert any(
        claim["claim_kind"] == "mechanic_usage"
        and claim.get("mechanic") == "weapon"
        and claim.get("runtime_block") in {"BeforePlayCardBonus", "BeforePhysicalAttackBonus"}
        and claim.get("runtime_value")
        for claim in claims
    )
    assert any(
        claim["claim_kind"] == "targeting_rule"
        and claim.get("stance") == "prefer_enemy_hero"
        and claim.get("runtime_block") == "BeforePhysicalAttackBonus"
        and claim.get("runtime_value")
        for claim in claims
    )


def test_piratedh_fixture_has_runtime_lowerable_hero_attack_claims():
    claims = _claims("PirateDH")
    assert any(
        claim["claim_kind"] == "mechanic_usage"
        and claim.get("mechanic") == "hero_attack"
        and claim.get("runtime_block") == "BeforePhysicalAttackBonus"
        and claim.get("runtime_value")
        for claim in claims
    )
    assert any(
        claim["claim_kind"] == "targeting_rule"
        and claim.get("stance") == "prefer_enemy_hero"
        and claim.get("runtime_block") == "BeforePhysicalAttackBonus"
        and claim.get("runtime_value")
        for claim in claims
    )
```

- [ ] **Step 2: Run focused tests**

Run:

```powershell
python -m pytest tests/test_archetype_source_fixtures.py::test_kingslayer_fixture_has_runtime_lowerable_weapon_sequence_claims tests/test_archetype_source_fixtures.py::test_piratedh_fixture_has_runtime_lowerable_hero_attack_claims -q
```

Expected: FAIL until fixture claims are complete.

- [ ] **Step 3: Strengthen attack-pressure fixtures**

Update the two source fixtures with runtime-lowerable `mechanic_usage` and `targeting_rule` claims. Use:

- `BeforePlayCardBonus` for playing weapon/attack enablers.
- `BeforePhysicalAttackBonus` for weapon or hero attack targeting.
- `stance=prefer_enemy_hero` only when the guide/card role is face-pressure.
- Keep unsupported or speculative mulligan claims `explicit_low_confidence` and report-only.

- [ ] **Step 4: Run focused closure tests**

Run:

```powershell
python -m pytest tests/test_archetype_source_fixtures.py tests/test_fixture_source_depth_closure.py tests/test_strong_fixture_closure.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add tests/fixtures/source_documents_kingslayer_strong.json tests/fixtures/source_documents_piratedh_strong.json src/hsconfig/config_readiness.py tests/test_archetype_source_fixtures.py
git commit -m "feat: close weapon and hero attack source depth fixtures"
```

---

### Task 5: Close Discolock And ImbueMage Mechanic-Specific Source Depth

**Files:**
- Modify: `tests/fixtures/source_documents_discolock_strong.json`
- Modify: `tests/fixtures/source_documents_imbuemage_strong.json`
- Modify: `src/hsconfig/config_readiness.py`
- Modify: `src/hsconfig/source_claim_gap_report.py` only if a new missing-link reason is required.
- Modify: `tests/test_archetype_source_fixtures.py`
- Modify: `tests/test_config_readiness.py`
- Modify: `tests/test_source_claim_gap_report.py`

**Interfaces:**
- Produces: Discolock discard/hand-mutation claims and ImbueMage hero-power/spell-generation claims that are either runtime-lowerable or explicitly report-only with a precise first missing link.

- [ ] **Step 1: Add focused source assertions**

Add:

```python
def test_discolock_fixture_marks_discard_runtime_and_never_autopatch_boundaries():
    claims = _claims("Discolock")
    assert any(
        claim["claim_kind"] == "mechanic_usage"
        and claim.get("mechanic") == "discard"
        and claim.get("runtime_block") == "BeforePlayCardBonus"
        and claim.get("runtime_value")
        for claim in claims
    )
    assert any(
        claim["claim_kind"] == "known_bad_pattern"
        and "discard" in str(claim.get("evidence_text_short", "")).lower()
        for claim in claims
    )


def test_imbuemage_fixture_marks_hero_power_and_generation_boundaries():
    claims = _claims("ImbueMage")
    assert any(
        claim["claim_kind"] == "hero_power_transform"
        and claim.get("runtime_block") in {"HeroPowerBonus", "BeforeHeroPowerBonus", "BeforePlayCardBonus"}
        and claim.get("runtime_value")
        for claim in claims
    )
    assert any(
        claim["claim_kind"] in {"mechanic_usage", "discover_choice"}
        and claim.get("mechanic") in {"spell_generation", "discover", "imbue"}
        for claim in claims
    )
```

- [ ] **Step 2: Run focused tests**

Run:

```powershell
python -m pytest tests/test_archetype_source_fixtures.py::test_discolock_fixture_marks_discard_runtime_and_never_autopatch_boundaries tests/test_archetype_source_fixtures.py::test_imbuemage_fixture_marks_hero_power_and_generation_boundaries -q
```

Expected: FAIL until fixture claims are complete.

- [ ] **Step 3: Strengthen fixtures without hiding unsafe uncertainty**

For Discolock:

- Runtime-lowerable discard payoff claims may use `mechanic_usage` and `BeforePlayCardBonus`.
- Hand randomness, unknown discard target, or unsafe hand mutation must stay `known_bad_pattern`, `explicit_low_confidence`, or report-only if it cannot be represented in VisionAI safely.

For ImbueMage:

- Hero-power transformation/enabling may lower through existing hero-power/global-values path if supported.
- Discover/spell-generation choice quality should remain report-only unless the repo already has documented VisionAI syntax for the exact choice surface.

- [ ] **Step 4: Add missing-link category only if existing terms are too broad**

If `needs_mechanic_lowering` hides the first actionable link for discover/spell-generation or discard randomness, add a specific missing link to both `MISSING_LINKS` and `RECOMMENDED_CLAIM_KIND_BY_MISSING_LINK`, with a failing unit test first. Example only if required:

```python
def test_report_explains_review_only_mechanic_boundary():
    assert RECOMMENDED_CLAIM_KIND_BY_MISSING_LINK["needs_review_only_boundary"] == "known_bad_pattern"
    assert NEXT_ACTION_BY_MISSING_LINK["needs_review_only_boundary"] == "keep_claim_report_only_or_add_documented_runtime_surface"
```

Do not add this category if existing `needs_mechanic_lowering` is sufficient.

- [ ] **Step 5: Run closure tests**

Run:

```powershell
python -m pytest tests/test_archetype_source_fixtures.py tests/test_config_readiness.py tests/test_source_claim_gap_report.py tests/test_fixture_source_depth_closure.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add tests/fixtures/source_documents_discolock_strong.json tests/fixtures/source_documents_imbuemage_strong.json src/hsconfig/config_readiness.py src/hsconfig/source_claim_gap_report.py tests/test_archetype_source_fixtures.py tests/test_config_readiness.py tests/test_source_claim_gap_report.py
git commit -m "feat: close discard and hero-power source depth fixtures"
```

---

### Task 6: Close Boarlock Exact Combo Sequence

**Files:**
- Modify: `tests/fixtures/source_documents_boarlock_strong.json`
- Modify: `tests/test_archetype_source_fixtures.py`
- Modify: `tests/test_combo_plan.py` or existing combo tests if present.
- Modify: `src/hsconfig/config_readiness.py` only if exact combo readiness remains incorrectly blocked.

**Interfaces:**
- Produces: Boarlock is the only matrix deck expecting `Combo.json`.
- Produces: exact combo claims with ordered cards, conditions, and runtime-safe combo output.

- [ ] **Step 1: Add failing exact-combo assertion**

Add:

```python
def test_boarlock_fixture_has_exact_combo_sequence_claims():
    claims = _claims("Boarlock")
    combo_claims = [claim for claim in claims if claim["claim_kind"] == "combo_sequence"]
    assert combo_claims
    assert any(
        claim.get("cards")
        and len(claim["cards"]) >= 2
        and claim.get("claim_readiness") == "source_backed_static_semantics"
        and claim.get("source_confidence") in {"medium", "high"}
        for claim in combo_claims
    )
```

- [ ] **Step 2: Run focused test**

Run:

```powershell
python -m pytest tests/test_archetype_source_fixtures.py::test_boarlock_fixture_has_exact_combo_sequence_claims -q
```

Expected: FAIL if Boarlock still lacks exact combo claims.

- [ ] **Step 3: Strengthen Boarlock source fixture**

Add `combo_sequence` claims only where source evidence supports sequence and card identity. Include:

```json
{
  "claim_kind": "combo_sequence",
  "cards": ["<card_id_1>", "<card_id_2>"],
  "stance": "resource_setup_combo",
  "claim_readiness": "source_backed_static_semantics",
  "source_confidence": "medium",
  "evidence_text_short": "<short source-backed combo sequence>",
  "source_refs": ["<public_https_source_url_or_document_ref>"]
}
```

Do not invent a complete lethal line if the source only supports a setup role. If exact output is not safe, the row must remain source-informed with first missing link `needs_exact_combo_sequence_closure`.

- [ ] **Step 4: Run combo and closure tests**

Run:

```powershell
python -m pytest tests/test_archetype_source_fixtures.py tests/test_fixture_source_depth_closure.py tests/test_strong_fixture_closure.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add tests/fixtures/source_documents_boarlock_strong.json src/hsconfig/config_readiness.py tests/test_archetype_source_fixtures.py tests/test_fixture_source_depth_closure.py tests/test_strong_fixture_closure.py
git commit -m "feat: close boarlock combo source depth"
```

---

### Task 7: Promote Proven Rows And Keep Blocked Rows Explicit

**Files:**
- Modify: `docs/operator/archetype-fixture-matrix.json`
- Modify: `tests/test_archetype_fixture_matrix.py`
- Modify: `docs/operator/source-backed-strong-closure.md`

**Interfaces:**
- Consumes: Passing `tests/test_strong_fixture_closure.py` for any promoted deck.
- Produces: Matrix rows that accurately reflect proven stage, not intent.

- [ ] **Step 1: Run proof tests before editing matrix**

Run:

```powershell
python -m pytest tests/test_strong_fixture_closure.py tests/test_fixture_source_depth_closure.py -q
```

Expected: PASS. Record which of the seven decks have `promotion_ready=True` in their generated reports.

- [ ] **Step 2: Update matrix rows only for proven decks**

For each proven deck, update its matrix row:

```json
"fixture_stage": "core_source_backed_fixture",
"strongness_visibility": {
  "current_stage": "core_source_backed_fixture",
  "first_strongness_gap": "none",
  "operator_action": "keep_as_core_control_fixture"
},
"known_coverage_limits": ["does_not_cover_reactive_control"]
```

Keep unproven decks as `source_informed_valid_fixture` with their existing specific gap.

- [ ] **Step 3: Update matrix tests**

Update `CORE_FIXTURES`, `SOURCE_INFORMED_VALID_FIXTURES`, and `EXPECTED_STRONGNESS_GAPS` in `tests/test_archetype_fixture_matrix.py` to match the proven matrix.

- [ ] **Step 4: Document promotion rule**

Add to `docs/operator/source-backed-strong-closure.md`:

```markdown
## Promotion Rule

A matrix row may move from `source_informed_valid_fixture` to `core_source_backed_fixture` only when a fixture prepare run proves:

- `technical_status=VALID_PACKAGE`
- `semantic_status=SOURCE_BACKED_STRONG`
- `next_action=READY_TO_APPLY_OR_HANDOFF`
- zero semantic blockers
- zero blocked cards in `source_claim_gap_report.json`
- no generated `Presume.json` or `Concede.json`

Rows that do not meet all six checks stay source-informed and must expose one specific first missing chain.
```

- [ ] **Step 5: Run matrix and closure tests**

Run:

```powershell
python -m pytest tests/test_archetype_fixture_matrix.py tests/test_matrix_visibility.py tests/test_fixture_source_depth_closure.py tests/test_strong_fixture_closure.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add docs/operator/archetype-fixture-matrix.json docs/operator/source-backed-strong-closure.md tests/test_archetype_fixture_matrix.py
git commit -m "docs: promote proven source-backed fixture rows"
```

---

### Task 8: Operator Docs And Skill Sync Polish

**Files:**
- Modify: `docs/operator/README.md`
- Modify: `.agents/skills/hsconfig/SKILL.md`
- Modify: `.agents/skills/hsconfig/references/workflow.md`
- Test: `tests/test_skill_sync.py`
- Test: `tests/test_skill_files.py`

**Interfaces:**
- Produces: One concise operator explanation of the matrix closure state.
- Preserves: installed skill sync.

- [ ] **Step 1: Add docs test**

Add to `tests/test_skill_files.py`:

```python
def test_operator_docs_explain_source_depth_closure_without_expanding_scope():
    operator = Path("docs/operator/README.md").read_text(encoding="utf-8")
    skill = Path(".agents/skills/hsconfig/SKILL.md").read_text(encoding="utf-8")

    assert "source-depth closure" in operator.lower()
    assert "docs/operator/archetype-fixture-matrix.json" in operator
    assert "pre-run only" in skill.lower()
    assert "replay" not in operator.lower()
    assert "winrate" not in operator.lower()
```

- [ ] **Step 2: Run failing docs test**

Run:

```powershell
python -m pytest tests/test_skill_files.py::test_operator_docs_explain_source_depth_closure_without_expanding_scope -q
```

Expected: FAIL until docs mention source-depth closure.

- [ ] **Step 3: Add concise docs paragraph**

Add to `docs/operator/README.md` under the fixture matrix section:

```markdown
Source-depth closure means every representative deck either proves `SOURCE_BACKED_STRONG` or exposes the first missing source-to-runtime link. Close existing matrix gaps before adding new representative decks.
```

Add the same concept in one sentence to `.agents/skills/hsconfig/SKILL.md` and `.agents/skills/hsconfig/references/workflow.md`.

- [ ] **Step 4: Sync installed skill**

Run:

```powershell
python scripts\sync_installed_skill.py
python scripts\sync_installed_skill.py --check
```

Expected: `HSConfig skill is in sync`.

- [ ] **Step 5: Run docs tests**

Run:

```powershell
python -m pytest tests/test_skill_files.py tests/test_skill_sync.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add docs/operator/README.md .agents/skills/hsconfig/SKILL.md .agents/skills/hsconfig/references/workflow.md tests/test_skill_files.py
git commit -m "docs: document source-depth closure workflow"
```

---

### Task 9: Final Verification And GitHub Sync

**Files:**
- No production changes unless a focused verification failure requires a narrowly scoped fix.

**Interfaces:**
- Produces: clean `main` pushed to `origin/main`.

- [ ] **Step 1: Run source-depth focused suite**

Run:

```powershell
python -m pytest tests/test_source_depth_closure_index.py tests/test_fixture_source_depth_closure.py tests/test_strong_fixture_closure.py tests/test_archetype_source_fixtures.py -q
```

Expected: PASS.

- [ ] **Step 2: Run operator and matrix suite**

Run:

```powershell
python -m pytest tests/test_archetype_fixture_matrix.py tests/test_matrix_visibility.py tests/test_source_claim_gap_report.py tests/test_config_readiness.py tests/test_strong_promotion_report.py tests/test_operator_summary.py tests/test_operator_guidance.py -q
```

Expected: PASS.

- [ ] **Step 3: Run CLI and skill suite**

Run:

```powershell
python -m pytest tests/test_cli_help.py tests/test_skill_files.py tests/test_scope_boundaries.py tests/test_skill_sync.py -q
```

Expected: PASS.

- [ ] **Step 4: Run full suite**

Run:

```powershell
python -m pytest -q
```

Expected: PASS.

- [ ] **Step 5: Verify installed skill sync**

Run:

```powershell
python scripts\sync_installed_skill.py --check
```

Expected:

```text
HSConfig skill is in sync: C:\Users\darbo\.codex\skills\hsconfig
```

- [ ] **Step 6: Verify active code scope remains lean**

Run:

```powershell
rg -n "Power\.log|hsreplay|HDT replay|winrate|candidate promotion|post-run tuning|analyze-step2" src\hsconfig .agents\skills\hsconfig docs\operator
```

Expected: no matches for `src\hsconfig` and no normal-path guidance that turns HSConfig into HSTuner. If docs contain boundary text such as "does not parse replays" or "does not inspect winrate", keep it only as negative scope.

- [ ] **Step 7: Verify no generated runtime packages are staged**

Run:

```powershell
git status --short
```

Expected: no `outputs/`, runtime package, cache, or private evidence files staged.

- [ ] **Step 8: Push main**

Run:

```powershell
git status --short --branch
git push origin main
```

Expected: `main -> main` and clean status afterwards.

---

## Self-Review Checklist

- [ ] The plan keeps HSConfig pre-run only.
- [ ] The plan does not add replay parsing, HDT parsing, winrate validation, candidate promotion, runtime evidence analysis, or post-run tuning.
- [ ] The plan adds no runtime dependency.
- [ ] The plan preserves `operator_summary.json` as the single normal operator gate.
- [ ] The plan preserves normal runtime files as `GlobalValues.json`, `Mulligan.json`, `<CARDID>.json`, and exact-sequence `Combo.json`.
- [ ] The plan uses existing eleven decks and does not add a new representative deck.
- [ ] The plan focuses on the seven source-informed rows: CtAPaladin, Discolock, TreantDruid, ImbueMage, Kingslayer, Boarlock, and PirateDH.
- [ ] The plan allows promotion only when tests prove `SOURCE_BACKED_STRONG`.
- [ ] The plan leaves unproven rows explicitly blocked with one first missing chain.
- [ ] The plan includes focused tests, full-suite verification, skill sync, and GitHub sync.

# HSConfig Guide Source Depth Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make HSConfig visibly deep enough that a deck-specific `guide_sources.json` drives every deck card into a clear config-readiness lane before `CustomConfig` is handed off or applied.

**Architecture:** Keep HSConfig lean: Codex still performs live online research and writes structured guide-source claims; HSConfig remains the deterministic compiler and validator. Add two small report builders, wire them into `prepare`/`build`, tighten docs/skill instructions, and prove the behavior with a richer ShadowPriest fixture.

**Tech Stack:** Python 3.11, `hearthstone` deckstring decode, pytest, existing `hsconfig` CLI, HearthRanger VisionAI JSON runtime files.

---

## Scope

This plan implements the next recommended wave only: Guide Source Depth Closure. It does not add replay parsing, winrate analysis, HSTuner sessions, autonomous web crawling inside the Python package, or post-run tuning.

The desired operator outcome is:

1. Codex receives a deck.
2. Codex researches current guide/card/archetype sources.
3. Codex writes a full structured `guide_sources.json`.
4. `hsconfig prepare --guide-sources-json ...` compiles and validates a package.
5. Reports show whether every card has enough source depth for meaningful config generation.

## File Structure

- Create `src/hsconfig/config_readiness.py`
  - Builds `per_card_config_readiness_report.json` from the deck identity, claim coverage, gameplan contract, mulligan plan, card behavior plan, combo plan, and GlobalValues authority matrix.
  - Gives every card one lane and the first missing link.
- Create `src/hsconfig/guide_source_depth.py`
  - Builds `guide_source_depth_report.json` from guide claims, source evidence, and per-card readiness.
  - Keeps strict quality visible without blocking valid package generation.
- Modify `src/hsconfig/cli.py`
  - Writes both new reports during `build` and `prepare`.
  - Adds summary counts to JSON output.
- Add `src/hsconfig/__main__.py`
  - Makes `python -m hsconfig` behave like `python -m hsconfig.cli`.
- Modify `docs/operator/guide-research-policy.md`
  - Documents required per-card guide-source depth.
- Modify `.agents/skills/hsconfig/SKILL.md`
  - Makes the skill require complete card-level guide-source authoring before normal prepare.
- Modify `.agents/skills/hsconfig/references/workflow.md`
  - Adds the readiness/depth reports to the normal workflow.
- Modify `.agents/skills/hsconfig/references/guide-research-policy.md`
  - Mirrors the operator policy for the installed skill source.
- Modify `README.md`
  - Adds the shortest possible note about the new reports.
- Modify `tests/fixtures/shadowpriest_guide_sources.json`
  - Expand the fixture into a high-depth source bundle for all ShadowPriest deck cards used by the E2E test.
- Create `tests/test_config_readiness.py`
  - Unit tests for readiness lanes and missing-link explanations.
- Create `tests/test_guide_source_depth.py`
  - Unit tests for source-depth scoring and warnings.
- Modify `tests/test_prepare_cli.py`
  - Asserts the new reports are written and summarized.
- Modify `tests/test_shadowpriest_depth_e2e.py`
  - Asserts the richer fixture produces stronger coverage and more concrete runtime behavior.
- Modify `tests/test_skill_files.py`
  - Asserts docs/skill mention the new normal-path reports and do not add HSTuner/replay scope.

## Readiness Lanes

Use these exact lane names:

- `runtime_emitted`: at least one concrete runtime row/file effect exists for the card.
- `mulligan_only`: the card has concrete mulligan behavior but no CardID/Combo behavior.
- `globalvalues_only`: the card only influences deck-level GlobalValues or hero-power posture.
- `report_only_supported`: the card has guide/static semantics, but no documented runtime surface was emitted.
- `archetype_inferred`: the card has inferred role/usage but no source-backed card-specific claim.
- `generic_low_confidence`: HSConfig only knows the card is in the deck.

Use these exact missing-link labels:

- `none`
- `needs_guide_claim`
- `needs_runtime_surface`
- `needs_mulligan_claim`
- `needs_combo_sequence`
- `needs_condition_lowering`
- `needs_mechanic_lowering`

---

### Task 1: Add Per-Card Config Readiness Report

**Files:**
- Create: `src/hsconfig/config_readiness.py`
- Test: `tests/test_config_readiness.py`

- [ ] **Step 1: Write failing tests for card readiness lanes**

Create `tests/test_config_readiness.py`:

```python
from hsconfig.config_readiness import build_config_readiness_report


def test_runtime_emitted_card_gets_runtime_lane():
    report = build_config_readiness_report(
        deck_identity={
            "deck_name": "Fixture",
            "deck_slug": "fixture",
            "cards": [{"card_id": "CARD_001", "name": "Burn Card", "count": 2}],
        },
        claim_coverage={
            "uncovered_cards": [],
            "guide_backed_cards": 1,
            "static_semantic_cards": 0,
            "total_cards": 1,
        },
        gameplan_contract={
            "cards": {
                "CARD_001": {
                    "card_id": "CARD_001",
                    "name": "Burn Card",
                    "coverage_status": "guide_backed",
                    "roles": ["pressure"],
                    "source_claim_ids": ["claim_1"],
                }
            },
            "hero_power_expectations": [],
        },
        mulligan_plan={"rules": []},
        card_behavior_plan={"rows": [{"card_id": "CARD_001", "intent": "prefer_enemy_hero"}]},
        combo_plan={"combos": [], "suppressed": []},
        global_values_authority_matrix={"allowed_step1_overlays": []},
    )

    assert report["summary"]["runtime_emitted"] == 1
    row = report["cards"]["CARD_001"]
    assert row["readiness_lane"] == "runtime_emitted"
    assert row["first_missing_link"] == "none"
    assert row["runtime_surfaces"] == ["CardID.json"]


def test_mulligan_only_card_gets_specific_lane():
    report = build_config_readiness_report(
        deck_identity={
            "deck_name": "Fixture",
            "deck_slug": "fixture",
            "cards": [{"card_id": "CARD_002", "name": "Keep Card", "count": 1}],
        },
        claim_coverage={"uncovered_cards": [], "total_cards": 1},
        gameplan_contract={
            "cards": {
                "CARD_002": {
                    "card_id": "CARD_002",
                    "name": "Keep Card",
                    "coverage_status": "guide_backed",
                    "roles": ["mulligan_anchor"],
                    "source_claim_ids": ["claim_keep"],
                }
            }
        },
        mulligan_plan={
            "rules": [{"card": "CARD_002", "action": "hold", "source_claim_ids": ["claim_keep"]}]
        },
        card_behavior_plan={"rows": []},
        combo_plan={"combos": [], "suppressed": []},
        global_values_authority_matrix={"allowed_step1_overlays": []},
    )

    row = report["cards"]["CARD_002"]
    assert row["readiness_lane"] == "mulligan_only"
    assert row["first_missing_link"] == "needs_runtime_surface"


def test_uncovered_card_gets_guide_claim_missing_link():
    report = build_config_readiness_report(
        deck_identity={
            "deck_name": "Fixture",
            "deck_slug": "fixture",
            "cards": [{"card_id": "CARD_003", "name": "Unknown Card", "count": 2}],
        },
        claim_coverage={"uncovered_cards": ["CARD_003"], "total_cards": 1},
        gameplan_contract={
            "cards": {
                "CARD_003": {
                    "card_id": "CARD_003",
                    "name": "Unknown Card",
                    "coverage_status": "generic_low_confidence",
                    "roles": ["deck_card"],
                    "source_claim_ids": [],
                }
            }
        },
        mulligan_plan={"rules": []},
        card_behavior_plan={"rows": []},
        combo_plan={"combos": [], "suppressed": []},
        global_values_authority_matrix={"allowed_step1_overlays": []},
    )

    row = report["cards"]["CARD_003"]
    assert row["readiness_lane"] == "generic_low_confidence"
    assert row["first_missing_link"] == "needs_guide_claim"
    assert report["summary"]["cards_needing_guide_claims"] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_config_readiness.py -q
```

Expected: fail with `ModuleNotFoundError: No module named 'hsconfig.config_readiness'`.

- [ ] **Step 3: Implement `config_readiness.py`**

Create `src/hsconfig/config_readiness.py`:

```python
from __future__ import annotations

from collections import Counter
from typing import Any


RUNTIME_SURFACE_CARDID = "CardID.json"
RUNTIME_SURFACE_MULLIGAN = "Mulligan.json"
RUNTIME_SURFACE_COMBO = "Combo.json"
RUNTIME_SURFACE_GLOBALVALUES = "GlobalValues.json"


def build_config_readiness_report(
    *,
    deck_identity: dict[str, Any],
    claim_coverage: dict[str, Any],
    gameplan_contract: dict[str, Any],
    mulligan_plan: dict[str, Any],
    card_behavior_plan: dict[str, Any],
    combo_plan: dict[str, Any],
    global_values_authority_matrix: dict[str, Any],
) -> dict[str, Any]:
    cards = _cards_from_deck(deck_identity, gameplan_contract)
    uncovered = {str(card) for card in claim_coverage.get("uncovered_cards", [])}
    cardid_cards = _cards_from_card_behavior(card_behavior_plan)
    mulligan_cards = _cards_from_mulligan(mulligan_plan)
    combo_cards = _cards_from_combos(combo_plan)
    globalvalue_cards = _cards_from_globalvalues(gameplan_contract, global_values_authority_matrix)

    rows: dict[str, dict[str, Any]] = {}
    counter: Counter[str] = Counter()
    missing_counter: Counter[str] = Counter()

    for card_id, card in sorted(cards.items()):
        runtime_surfaces = []
        if card_id in cardid_cards:
            runtime_surfaces.append(RUNTIME_SURFACE_CARDID)
        if card_id in mulligan_cards:
            runtime_surfaces.append(RUNTIME_SURFACE_MULLIGAN)
        if card_id in combo_cards:
            runtime_surfaces.append(RUNTIME_SURFACE_COMBO)
        if card_id in globalvalue_cards:
            runtime_surfaces.append(RUNTIME_SURFACE_GLOBALVALUES)

        lane, missing = _lane_and_missing_link(
            card_id=card_id,
            card=card,
            uncovered=uncovered,
            cardid_cards=cardid_cards,
            mulligan_cards=mulligan_cards,
            combo_cards=combo_cards,
            globalvalue_cards=globalvalue_cards,
        )
        counter[lane] += 1
        if missing != "none":
            missing_counter[missing] += 1
        rows[card_id] = {
            "card_id": card_id,
            "name": str(card.get("name", card_id)),
            "count": int(card.get("count", 1)),
            "coverage_status": str(card.get("coverage_status", card.get("confidence", ""))),
            "roles": [str(role) for role in card.get("roles", [])],
            "source_claim_ids": [str(item) for item in card.get("source_claim_ids", [])],
            "runtime_surfaces": runtime_surfaces,
            "readiness_lane": lane,
            "first_missing_link": missing,
        }

    summary = {
        "total_cards": len(rows),
        "runtime_emitted": counter["runtime_emitted"],
        "mulligan_only": counter["mulligan_only"],
        "globalvalues_only": counter["globalvalues_only"],
        "report_only_supported": counter["report_only_supported"],
        "archetype_inferred": counter["archetype_inferred"],
        "generic_low_confidence": counter["generic_low_confidence"],
        "cards_needing_guide_claims": missing_counter["needs_guide_claim"],
        "cards_needing_runtime_surface": missing_counter["needs_runtime_surface"],
        "cards_needing_mechanic_lowering": missing_counter["needs_mechanic_lowering"],
    }
    return {
        "deck_name": str(deck_identity.get("deck_name", gameplan_contract.get("deck_name", "Deck"))),
        "deck_slug": str(deck_identity.get("deck_slug", gameplan_contract.get("deck_slug", "deck"))),
        "summary": summary,
        "cards": rows,
    }


def _cards_from_deck(
    deck_identity: dict[str, Any],
    gameplan_contract: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    contract_cards = gameplan_contract.get("cards", {})
    if isinstance(contract_cards, dict) and contract_cards:
        return {str(card_id): dict(card) for card_id, card in contract_cards.items()}
    cards = {}
    for card in deck_identity.get("cards", []):
        card_id = str(card["card_id"])
        cards[card_id] = dict(card)
    return cards


def _cards_from_card_behavior(card_behavior_plan: dict[str, Any]) -> set[str]:
    return {
        str(row["card_id"])
        for row in card_behavior_plan.get("rows", [])
        if isinstance(row, dict) and row.get("card_id")
    }


def _cards_from_mulligan(mulligan_plan: dict[str, Any]) -> set[str]:
    return {
        str(row["card"])
        for row in mulligan_plan.get("rules", [])
        if isinstance(row, dict) and row.get("card") and str(row["card"]) != "*"
    }


def _cards_from_combos(combo_plan: dict[str, Any]) -> set[str]:
    cards: set[str] = set()
    for combo in combo_plan.get("combos", []):
        if not isinstance(combo, dict):
            continue
        cards.update(str(card) for card in combo.get("cards", []) if str(card))
    return cards


def _cards_from_globalvalues(
    gameplan_contract: dict[str, Any],
    global_values_authority_matrix: dict[str, Any],
) -> set[str]:
    if not global_values_authority_matrix.get("allowed_step1_overlays"):
        return set()
    cards: set[str] = set()
    for effect in gameplan_contract.get("deckwide_effects", []):
        if isinstance(effect, dict) and effect.get("source_card_id"):
            cards.add(str(effect["source_card_id"]))
    for expectation in gameplan_contract.get("hero_power_expectations", []):
        if isinstance(expectation, dict) and expectation.get("source_card_id"):
            cards.add(str(expectation["source_card_id"]))
    return cards


def _lane_and_missing_link(
    *,
    card_id: str,
    card: dict[str, Any],
    uncovered: set[str],
    cardid_cards: set[str],
    mulligan_cards: set[str],
    combo_cards: set[str],
    globalvalue_cards: set[str],
) -> tuple[str, str]:
    coverage = str(card.get("coverage_status", card.get("confidence", "")))
    roles = {str(role) for role in card.get("roles", [])}
    if card_id in cardid_cards or card_id in combo_cards:
        return "runtime_emitted", "none"
    if card_id in mulligan_cards:
        return "mulligan_only", "needs_runtime_surface"
    if card_id in globalvalue_cards:
        return "globalvalues_only", "needs_runtime_surface"
    if card_id in uncovered or coverage == "generic_low_confidence":
        return "generic_low_confidence", "needs_guide_claim"
    if coverage == "archetype_inferred":
        return "archetype_inferred", "needs_guide_claim"
    if roles & {"battlecry", "discover", "weapon", "location", "secret", "hero_power"}:
        return "report_only_supported", "needs_mechanic_lowering"
    return "report_only_supported", "needs_runtime_surface"
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```powershell
python -m pytest tests/test_config_readiness.py -q
```

Expected: `3 passed`.

- [ ] **Step 5: Commit Task 1**

```powershell
git add src/hsconfig/config_readiness.py tests/test_config_readiness.py
git commit -m "feat: add config readiness report"
```

---

### Task 2: Add Guide Source Depth Report

**Files:**
- Create: `src/hsconfig/guide_source_depth.py`
- Test: `tests/test_guide_source_depth.py`

- [ ] **Step 1: Write failing tests for source depth report**

Create `tests/test_guide_source_depth.py`:

```python
from hsconfig.guide_source_depth import build_guide_source_depth_report


def test_depth_report_counts_card_lanes_and_source_families():
    report = build_guide_source_depth_report(
        guide_claim_bundle={
            "claims": [
                {
                    "claim_id": "claim_keep",
                    "claim_kind": "mulligan_keep",
                    "cards": ["CARD_001"],
                    "source_family": "guide",
                },
                {
                    "claim_id": "claim_target",
                    "claim_kind": "targeting_rule",
                    "cards": ["CARD_001"],
                    "source_family": "guide",
                },
            ],
            "unsupported_claims": [],
            "source_evidence_index": [
                {"source_ref": "source:1", "source_family": "guide", "claim_count": 2}
            ],
        },
        config_readiness_report={
            "summary": {"total_cards": 1, "runtime_emitted": 1, "generic_low_confidence": 0},
            "cards": {
                "CARD_001": {
                    "readiness_lane": "runtime_emitted",
                    "first_missing_link": "none",
                    "source_claim_ids": ["claim_keep", "claim_target"],
                }
            },
        },
    )

    assert report["summary"]["claim_count"] == 2
    assert report["summary"]["supported_cards"] == 1
    assert report["source_families"] == {"guide": 2}
    assert report["depth_status"] == "usable"


def test_depth_report_warns_when_cards_need_guide_claims():
    report = build_guide_source_depth_report(
        guide_claim_bundle={
            "claims": [],
            "unsupported_claims": [],
            "source_evidence_index": [],
        },
        config_readiness_report={
            "summary": {"total_cards": 1, "runtime_emitted": 0, "generic_low_confidence": 1},
            "cards": {
                "CARD_002": {
                    "readiness_lane": "generic_low_confidence",
                    "first_missing_link": "needs_guide_claim",
                    "source_claim_ids": [],
                }
            },
        },
    )

    assert report["depth_status"] == "needs_more_research"
    assert report["warnings"] == [
        {
            "card_id": "CARD_002",
            "reason": "needs_guide_claim",
            "readiness_lane": "generic_low_confidence",
        }
    ]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_guide_source_depth.py -q
```

Expected: fail with `ModuleNotFoundError: No module named 'hsconfig.guide_source_depth'`.

- [ ] **Step 3: Implement `guide_source_depth.py`**

Create `src/hsconfig/guide_source_depth.py`:

```python
from __future__ import annotations

from collections import Counter
from typing import Any


def build_guide_source_depth_report(
    *,
    guide_claim_bundle: dict[str, Any],
    config_readiness_report: dict[str, Any],
) -> dict[str, Any]:
    claims = [claim for claim in guide_claim_bundle.get("claims", []) if isinstance(claim, dict)]
    unsupported = [
        claim for claim in guide_claim_bundle.get("unsupported_claims", []) if isinstance(claim, dict)
    ]
    source_families = Counter(str(claim.get("source_family", "unknown")) for claim in claims)
    claim_kinds = Counter(str(claim.get("claim_kind", claim.get("claim_type", "unknown"))) for claim in claims)

    cards = config_readiness_report.get("cards", {})
    warnings = []
    supported_cards = 0
    for card_id, row in sorted(cards.items()):
        lane = str(row.get("readiness_lane", "generic_low_confidence"))
        missing = str(row.get("first_missing_link", "needs_guide_claim"))
        if lane in {"runtime_emitted", "mulligan_only", "globalvalues_only", "report_only_supported"}:
            supported_cards += 1
        if missing != "none":
            warnings.append(
                {
                    "card_id": str(card_id),
                    "reason": missing,
                    "readiness_lane": lane,
                }
            )

    total_cards = int(config_readiness_report.get("summary", {}).get("total_cards", len(cards)))
    cards_needing_guide_claims = sum(
        1 for warning in warnings if warning["reason"] == "needs_guide_claim"
    )
    depth_status = "usable"
    if total_cards and cards_needing_guide_claims:
        depth_status = "needs_more_research"
    if total_cards and supported_cards == 0:
        depth_status = "insufficient"

    return {
        "depth_status": depth_status,
        "summary": {
            "claim_count": len(claims),
            "unsupported_claim_count": len(unsupported),
            "total_cards": total_cards,
            "supported_cards": supported_cards,
            "cards_needing_guide_claims": cards_needing_guide_claims,
            "warnings_count": len(warnings),
        },
        "source_families": dict(sorted(source_families.items())),
        "claim_kinds": dict(sorted(claim_kinds.items())),
        "warnings": warnings,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```powershell
python -m pytest tests/test_guide_source_depth.py -q
```

Expected: `2 passed`.

- [ ] **Step 5: Commit Task 2**

```powershell
git add src/hsconfig/guide_source_depth.py tests/test_guide_source_depth.py
git commit -m "feat: add guide source depth report"
```

---

### Task 3: Wire Reports Into `prepare` and `build`

**Files:**
- Modify: `src/hsconfig/cli.py`
- Test: `tests/test_prepare_cli.py`

- [ ] **Step 1: Write failing CLI report test**

Add this test to `tests/test_prepare_cli.py`:

```python
def test_prepare_writes_readiness_and_depth_reports(tmp_path):
    out = tmp_path / "shadowpriest"
    result = main(
        [
            "prepare",
            "--deck-name",
            "ShadowPriest",
            "--deck-code",
            "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=",
            "--runtime-root",
            str(tmp_path),
            "--out",
            str(out),
            "--guide-sources-json",
            "tests/fixtures/shadowpriest_guide_sources.json",
            "--json",
        ]
    )

    assert result == 0
    readiness = json.loads((out / "reports" / "per_card_config_readiness_report.json").read_text())
    depth = json.loads((out / "reports" / "guide_source_depth_report.json").read_text())
    assert readiness["summary"]["total_cards"] >= 1
    assert "depth_status" in depth
```

If `tests/test_prepare_cli.py` already imports `json` and `main`, do not duplicate imports. If not, add:

```python
import json
from hsconfig.cli import main
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest tests/test_prepare_cli.py::test_prepare_writes_readiness_and_depth_reports -q
```

Expected: fail because `per_card_config_readiness_report.json` is missing.

- [ ] **Step 3: Import builders in `cli.py`**

Add these imports near the other `hsconfig` imports:

```python
from hsconfig.config_readiness import build_config_readiness_report
from hsconfig.guide_source_depth import build_guide_source_depth_report
```

- [ ] **Step 4: Build and write reports inside `_build`**

In `src/hsconfig/cli.py`, after `global_values_authority_matrix` is finalized and before `gameplan_contract = { ... }`, keep the existing code unchanged.

After `gameplan_contract = { ... }` and before `surface_intent = build_surface_intent(gameplan_contract)`, add:

```python
    config_readiness_report = build_config_readiness_report(
        deck_identity=deck_identity,
        claim_coverage=guide_claim_bundle["coverage"],
        gameplan_contract=gameplan_contract,
        mulligan_plan=mulligan_plan,
        card_behavior_plan=card_behavior_plan,
        combo_plan=combo_plan,
        global_values_authority_matrix=global_values_authority_matrix,
    )
    guide_source_depth_report = build_guide_source_depth_report(
        guide_claim_bundle=guide_claim_bundle,
        config_readiness_report=config_readiness_report,
    )
```

After the existing `write_json(reports_dir / "global_values_authority_matrix.json", global_values_authority_matrix)` line, add:

```python
    write_json(reports_dir / "per_card_config_readiness_report.json", config_readiness_report)
    write_json(reports_dir / "guide_source_depth_report.json", guide_source_depth_report)
```

In the `_build` return payload, add these keys:

```python
            "config_readiness_summary": config_readiness_report["summary"],
            "guide_source_depth_status": guide_source_depth_report["depth_status"],
```

- [ ] **Step 5: Run targeted tests**

Run:

```powershell
python -m pytest tests/test_prepare_cli.py::test_prepare_writes_readiness_and_depth_reports -q
```

Expected: `1 passed`.

- [ ] **Step 6: Run related CLI tests**

Run:

```powershell
python -m pytest tests/test_prepare_cli.py tests/test_cli.py -q
```

Expected: all tests pass.

- [ ] **Step 7: Commit Task 3**

```powershell
git add src/hsconfig/cli.py tests/test_prepare_cli.py
git commit -m "feat: write guide depth reports during prepare"
```

---

### Task 4: Add `python -m hsconfig` Entry Point

**Files:**
- Create: `src/hsconfig/__main__.py`
- Test: `tests/test_package_import.py`

- [ ] **Step 1: Write failing test for module entry point**

Add this test to `tests/test_package_import.py`:

```python
import subprocess
import sys


def test_python_m_hsconfig_help_works():
    result = subprocess.run(
        [sys.executable, "-m", "hsconfig", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "usage: hsconfig" in result.stdout
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest tests/test_package_import.py::test_python_m_hsconfig_help_works -q
```

Expected: fail with `No module named hsconfig.__main__`.

- [ ] **Step 3: Add module entry point**

Create `src/hsconfig/__main__.py`:

```python
from __future__ import annotations

from hsconfig.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
python -m pytest tests/test_package_import.py::test_python_m_hsconfig_help_works -q
```

Expected: `1 passed`.

- [ ] **Step 5: Commit Task 4**

```powershell
git add src/hsconfig/__main__.py tests/test_package_import.py
git commit -m "fix: support python module entry point"
```

---

### Task 5: Expand ShadowPriest Fixture To Prove Depth

**Files:**
- Modify: `tests/fixtures/shadowpriest_guide_sources.json`
- Modify: `tests/test_shadowpriest_depth_e2e.py`

- [ ] **Step 1: Write stricter E2E assertions**

In `tests/test_shadowpriest_depth_e2e.py`, add assertions to the existing ShadowPriest depth test or create this test if no suitable test exists:

```python
def test_shadowpriest_depth_reports_show_broad_card_coverage(tmp_path):
    out = tmp_path / "shadowpriest_depth"
    result = main(
        [
            "prepare",
            "--deck-name",
            "ShadowPriest",
            "--deck-code",
            "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=",
            "--runtime-root",
            str(tmp_path),
            "--out",
            str(out),
            "--guide-sources-json",
            "tests/fixtures/shadowpriest_guide_sources.json",
            "--json",
        ]
    )

    assert result == 0
    reports = out / "reports"
    coverage = json.loads((reports / "claim_coverage_report.json").read_text())
    readiness = json.loads((reports / "per_card_config_readiness_report.json").read_text())
    depth = json.loads((reports / "guide_source_depth_report.json").read_text())
    mulligan = json.loads((out / "CustomConfig" / "shadowpriest" / "Mulligan.json").read_text())

    assert coverage["guide_backed_cards"] >= 8
    assert len(coverage["uncovered_cards"]) <= 4
    assert depth["depth_status"] == "usable"
    assert readiness["summary"]["generic_low_confidence"] <= 4
    assert readiness["summary"]["runtime_emitted"] >= 4
    assert len(mulligan["Mulligan"]["values"]) >= 4
```

Ensure imports include:

```python
import json
from hsconfig.cli import main
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest tests/test_shadowpriest_depth_e2e.py::test_shadowpriest_depth_reports_show_broad_card_coverage -q
```

Expected: fail because the fixture is currently too thin.

- [ ] **Step 3: Replace fixture with richer guide claims**

Replace `tests/fixtures/shadowpriest_guide_sources.json` with this content:

```json
[
  {
    "source_url": "https://example.invalid/shadow-priest-guide",
    "source_title": "Shadow Priest Guide Fixture",
    "source_family": "guide_fixture",
    "retrieved_at": "2026-07-06T12:00:00Z",
    "claims": [
      {
        "claim_kind": "mulligan_keep",
        "cards": ["SW_448"],
        "stance": "keep",
        "evidence_text_short": "Keep Darkbishop Benedictus because it enables the Shadow Priest hero power package.",
        "source_confidence": "high"
      },
      {
        "claim_kind": "mulligan_keep",
        "cards": ["SW_446"],
        "stance": "keep",
        "evidence_text_short": "Keep Voidtouched Attendant as an early pressure amplifier.",
        "source_confidence": "high"
      },
      {
        "claim_kind": "mulligan_keep",
        "cards": ["TOY_518"],
        "stance": "keep",
        "evidence_text_short": "Keep Treasure Distributor to start early board pressure.",
        "source_confidence": "medium"
      },
      {
        "claim_kind": "mulligan_keep",
        "cards": ["GVG_009"],
        "stance": "keep",
        "evidence_text_short": "Keep Shadowbomber in aggressive openers because it advances face damage.",
        "source_confidence": "medium"
      },
      {
        "claim_kind": "targeting_rule",
        "cards": ["SW_446"],
        "stance": "prefer_enemy_hero",
        "conditions": {"posture": "aggressive_burn"},
        "evidence_text_short": "Voidtouched Attendant supports face-pressure lines unless board survival requires a trade.",
        "source_confidence": "medium"
      },
      {
        "claim_kind": "targeting_rule",
        "cards": ["DS1_233"],
        "stance": "prefer_enemy_hero",
        "conditions": {"posture": "burn_reach"},
        "evidence_text_short": "Mind Blast is burn reach and should normally target the enemy hero.",
        "source_confidence": "high"
      },
      {
        "claim_kind": "targeting_rule",
        "cards": ["VAC_419"],
        "stance": "prefer_enemy_hero",
        "conditions": {"posture": "burn_reach"},
        "evidence_text_short": "Acupuncture is direct burn pressure in the Shadow Priest plan.",
        "source_confidence": "medium"
      },
      {
        "claim_kind": "card_role",
        "cards": ["CFM_637"],
        "stance": "early_pressure",
        "evidence_text_short": "Patches the Pirate supports early pressure when pulled by pirate synergy.",
        "source_confidence": "medium"
      },
      {
        "claim_kind": "card_role",
        "cards": ["DRG_056"],
        "stance": "early_pressure",
        "evidence_text_short": "Parachute Brigand supports early board pressure through pirate synergy.",
        "source_confidence": "medium"
      },
      {
        "claim_kind": "card_role",
        "cards": ["TOY_518"],
        "stance": "early_pressure",
        "evidence_text_short": "Treasure Distributor is an early board pressure card.",
        "source_confidence": "medium"
      },
      {
        "claim_kind": "card_role",
        "cards": ["WON_065"],
        "stance": "early_pressure",
        "evidence_text_short": "Ship's Chirurgeon supports early pressure and board refill.",
        "source_confidence": "medium"
      },
      {
        "claim_kind": "card_role",
        "cards": ["TOY_381"],
        "stance": "hero_power_support",
        "evidence_text_short": "Papercraft Angel supports repeated Hero Power pressure after Shadowform.",
        "source_confidence": "medium"
      },
      {
        "claim_kind": "card_role",
        "cards": ["REV_290"],
        "stance": "tempo_draw",
        "evidence_text_short": "Cathedral of Atonement converts board presence into draw and tempo.",
        "source_confidence": "medium"
      },
      {
        "claim_kind": "gameplan_posture",
        "cards": ["SW_448"],
        "stance": "aggressive",
        "evidence_text_short": "Shadow Priest uses early pressure, burn reach, and Mind Spike pressure.",
        "source_confidence": "high"
      }
    ]
  }
]
```

- [ ] **Step 4: Run E2E test to verify it passes**

Run:

```powershell
python -m pytest tests/test_shadowpriest_depth_e2e.py::test_shadowpriest_depth_reports_show_broad_card_coverage -q
```

Expected: `1 passed`.

- [ ] **Step 5: Run related package tests**

Run:

```powershell
python -m pytest tests/test_shadowpriest_e2e.py tests/test_shadowpriest_depth_e2e.py tests/test_prepare_cli.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit Task 5**

```powershell
git add tests/fixtures/shadowpriest_guide_sources.json tests/test_shadowpriest_depth_e2e.py
git commit -m "test: prove richer guide depth for shadowpriest"
```

---

### Task 6: Tighten Skill And Operator Documentation

**Files:**
- Modify: `README.md`
- Modify: `docs/operator/guide-research-policy.md`
- Modify: `.agents/skills/hsconfig/SKILL.md`
- Modify: `.agents/skills/hsconfig/references/workflow.md`
- Modify: `.agents/skills/hsconfig/references/guide-research-policy.md`
- Test: `tests/test_skill_files.py`

- [ ] **Step 1: Write failing docs tests**

Add this test to `tests/test_skill_files.py`:

```python
def test_skill_documents_guide_depth_closure_reports():
    skill = (REPO_ROOT / ".agents" / "skills" / "hsconfig" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    workflow = (
        REPO_ROOT / ".agents" / "skills" / "hsconfig" / "references" / "workflow.md"
    ).read_text(encoding="utf-8")
    policy = (
        REPO_ROOT / ".agents" / "skills" / "hsconfig" / "references" / "guide-research-policy.md"
    ).read_text(encoding="utf-8")

    for text in (skill, workflow, policy):
        assert "per_card_config_readiness_report.json" in text
        assert "guide_source_depth_report.json" in text
    assert "no replay analysis" in skill.lower()
    assert "winrate" in skill.lower()
```

If `REPO_ROOT` is not already defined in `tests/test_skill_files.py`, add:

```python
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest tests/test_skill_files.py::test_skill_documents_guide_depth_closure_reports -q
```

Expected: fail because the new report names are not yet in every file.

- [ ] **Step 3: Update `README.md`**

In the "Key reports" list, add:

```markdown
- `reports/per_card_config_readiness_report.json`
- `reports/guide_source_depth_report.json`
```

After the key reports list, add this paragraph:

```markdown
The readiness and depth reports are the normal quality check for guide-backed
config generation. A valid package may still contain `archetype_inferred` or
`generic_low_confidence` cards, but those lanes tell Codex to improve the
structured guide source before treating the package as deeply configured.
```

- [ ] **Step 4: Update `docs/operator/guide-research-policy.md`**

After "Structured Source Format", add:

```markdown
## Per-Card Depth Rule

Before normal `hsconfig prepare`, Codex should try to give every deck card at
least one structured expectation. The preferred order is card-specific guide
claim, current card text/static semantics, archetype-inferred role, then
`generic_low_confidence` as the last visible fallback.

For each card, prefer claims that answer at least one of these questions:

- keep, discard, or situational mulligan
- face, trade, friendly target, discover, weapon, location, or Hero Power usage
- combo sequence or synergy partner
- board-value posture or GlobalValues effect
- known bad pattern
```

In the Reports list, add:

```markdown
- `per_card_config_readiness_report.json`: card-level lane, runtime surfaces, and first missing link.
- `guide_source_depth_report.json`: source-depth status, source families, claim kinds, and research warnings.
```

- [ ] **Step 5: Update `.agents/skills/hsconfig/SKILL.md`**

In the workflow list, add a step after guide-source writing:

```markdown
4. Check that the structured guide sources give every deck card a card role,
   mulligan stance, usage expectation, mechanic expectation, combo relation, or
   explicit low-confidence fallback.
```

Renumber later steps if the file uses numbered Markdown.

Add these report names to the verification step:

```markdown
`per_card_config_readiness_report.json`, `guide_source_depth_report.json`
```

- [ ] **Step 6: Update `.agents/skills/hsconfig/references/workflow.md`**

Replace the normal flow sentence with:

```markdown
Normal flow: deck input -> guide research -> structured guide sources for every
deck card -> `hsconfig prepare --guide-sources-json ...` -> HearthSim deckstring
decode -> exact identity -> card metadata -> guide/static research contract ->
guide-backed gameplan -> plan reports -> readiness/depth reports -> compilers ->
validation -> optional runtime apply.
```

Add the two new reports to the report list in that file.

- [ ] **Step 7: Update `.agents/skills/hsconfig/references/guide-research-policy.md`**

Mirror the Per-Card Depth Rule and report bullets from `docs/operator/guide-research-policy.md`.

- [ ] **Step 8: Run docs tests**

Run:

```powershell
python -m pytest tests/test_skill_files.py -q
```

Expected: all tests pass.

- [ ] **Step 9: Commit Task 6**

```powershell
git add README.md docs/operator/guide-research-policy.md .agents/skills/hsconfig tests/test_skill_files.py
git commit -m "docs: define guide depth closure workflow"
```

---

### Task 7: Sync Installed Local Skill Copy

**Files:**
- Runtime copy target: `C:\Users\darbo\.codex\skills\hsconfig`
- Source: `.agents/skills/hsconfig`

- [ ] **Step 1: Copy repo skill source into installed skill path**

Run:

```powershell
$source = "C:\Users\darbo\Documents\HSConfig\.agents\skills\hsconfig"
$target = "C:\Users\darbo\.codex\skills\hsconfig"
if (Test-Path $target) { Remove-Item -Recurse -Force $target }
Copy-Item -Recurse -Force $source $target
```

Expected: command exits with code `0`.

- [ ] **Step 2: Verify installed skill contains new reports**

Run:

```powershell
rg -n "per_card_config_readiness_report|guide_source_depth_report" "C:\Users\darbo\.codex\skills\hsconfig"
```

Expected: matches in `SKILL.md`, `references/workflow.md`, and `references/guide-research-policy.md`.

- [ ] **Step 3: Verify source repo is unchanged by install sync**

Run:

```powershell
git status --short
```

Expected: no output.

Do not commit installed skill files because they are outside the repository.

---

### Task 8: Full Verification

**Files:**
- No source edits unless tests expose a defect.

- [ ] **Step 1: Run targeted report tests**

Run:

```powershell
python -m pytest tests/test_config_readiness.py tests/test_guide_source_depth.py tests/test_prepare_cli.py -q
```

Expected: all tests pass.

- [ ] **Step 2: Run E2E and skill docs tests**

Run:

```powershell
python -m pytest tests/test_shadowpriest_e2e.py tests/test_shadowpriest_depth_e2e.py tests/test_skill_files.py -q
```

Expected: all tests pass.

- [ ] **Step 3: Run full test suite**

Run:

```powershell
python -m pytest -q
```

Expected: all tests pass.

- [ ] **Step 4: Run live help smoke**

Run:

```powershell
hsconfig --help
python -m hsconfig --help
```

Expected: both commands print `usage: hsconfig`.

- [ ] **Step 5: Run guide-depth package smoke**

Run:

```powershell
$out = "C:\Users\darbo\Documents\HSConfig\tmp\shadowpriest_depth_smoke"
if (Test-Path $out) { Remove-Item -Recurse -Force $out }
hsconfig prepare --deck-name "ShadowPriest" --deck-code "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=" --runtime-root "C:\Users\darbo\Desktop\HS" --out $out --guide-sources-json "tests\fixtures\shadowpriest_guide_sources.json" --json
```

Expected: JSON output contains `"status": "passed"`, `"guide_source_depth_status": "usable"`, and a non-empty `"config_readiness_summary"`.

- [ ] **Step 6: Remove smoke output**

Run:

```powershell
if (Test-Path "C:\Users\darbo\Documents\HSConfig\tmp\shadowpriest_depth_smoke") {
  Remove-Item -Recurse -Force "C:\Users\darbo\Documents\HSConfig\tmp\shadowpriest_depth_smoke"
}
```

Expected: command exits with code `0`.

- [ ] **Step 7: Final git status**

Run:

```powershell
git status --short --branch
```

Expected: `## main...origin/main` or a clean feature branch with all intended commits present.

---

## Self-Review Checklist

- Spec coverage:
  - Direct config-only scope is preserved.
  - No replay/HDT/winrate/HSTuner functionality is added.
  - Every card gets a readiness lane.
  - Guide-source depth becomes visible before apply/handoff.
  - ShadowPriest fixture proves richer guide depth.
  - Installed skill copy is synced after repo source changes.
- Placeholder scan:
  - No task uses unresolved placeholders.
  - Every new function name is defined in a task before use.
  - Every command has an expected outcome.
- Type consistency:
  - Report builders accept plain dictionaries, matching existing HSConfig report style.
  - Lane names are stable strings.
  - CLI summary keys match report builder output.

## Completion Criteria

The plan is complete when:

- `per_card_config_readiness_report.json` is written by `prepare` and `build`.
- `guide_source_depth_report.json` is written by `prepare` and `build`.
- CLI JSON output includes `config_readiness_summary` and `guide_source_depth_status`.
- `python -m hsconfig --help` works.
- The richer ShadowPriest fixture produces broad guide coverage and multiple concrete runtime behavior rows.
- Repo tests pass.
- The installed local `hsconfig` skill copy contains the updated workflow instructions.

# HSConfig Universal Wild No-Block Proof Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Freeze the HSConfig promise that every valid deck can produce and apply a load-safe initial HearthRanger CustomConfig package, while Wild mechanics that cannot be honestly lowered remain explicit warnings instead of blockers.

**Architecture:** Add a small mechanic support registry as the single source of truth for `direct`, `partial`, and `warning_only` mechanic handling. Feed that registry into per-card readiness and operator summary reports, then prove the no-block contract with the provided 12 Wild decks. Keep HSConfig pre-run only: no replay parsing, no winrate, no HSTuner logic, and no post-game tuning.

**Tech Stack:** Python package under `src/hsconfig`, pytest test suite, existing HearthSim deckstring/card identity flow, HearthstoneJSON metadata enrichment, HearthRanger VisionAI JSON package generation.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig` for `Teufelsboy/HSConfig`.
- HSConfig stays a lean pre-run config generator; do not add replay parsing, HDT parsing, winrate validation, candidate promotion, or post-run tuning.
- A valid warning package must remain applyable: `technical_status=VALID_PACKAGE`, `runtime_load_safe=true`, `runtime_apply_mode=load_safe_apply`.
- `SOURCE_BACKED_STRONG` is a confidence label, not the runtime-write gate.
- Hard blocking remains only for malformed deck input, unresolved exact CardID identity, invalid JSON, unsupported runtime files or blocks, missing required runtime files, stale/forged apply evidence, nested files, or normal-path `Presume.json` / `Concede.json`.
- Normal runtime files remain `GlobalValues.json`, `Mulligan.json`, per-card `<CARDID>.json`, and `Combo.json` only for exact valid sequences.
- `Presume.json` and `Concede.json` stay out of the normal path.
- Preserve exact deck/CardID identity, full GlobalValues key profiling, every-card gameplan coverage, strict JSON validation, and row-level provenance.
- Do not commit raw runtime evidence or generated `outputs/` packages.
- Existing untracked research folders must not be blindly committed. Commit only the final, intentionally referenced research/docs artifacts for this wave.

---

## File Structure

- Create `src/hsconfig/mechanic_support.py`: central registry for mechanic support level, warning boundary, supported normal-path surfaces, and helper functions.
- Create `tests/test_mechanic_support.py`: focused registry tests for direct, partial, warning-only, and unknown role handling.
- Modify `src/hsconfig/config_readiness.py`: add mechanic support annotations to each card row and summary counts.
- Modify `tests/test_config_readiness.py`: prove readiness report exposes mechanic support and warning-only counts without affecting apply readiness.
- Modify `src/hsconfig/operator_summary.py`: expose a compact `mechanic_warning_summary` from the readiness report.
- Modify `src/hsconfig/operator_guidance.py`: include mechanic warning summary in warning-package guidance while keeping `safe_to_apply=true`.
- Modify `tests/test_operator_summary.py` and `tests/test_operator_guidance.py`: prove mechanic warnings are visible and non-blocking.
- Create `tests/test_universal_wild_no_block_matrix.py`: provided 12-deck matrix proof for load-safe package generation.
- Modify `docs/operator/README.md`: add a short no-block and mechanic-support reading section.
- Modify `docs/operator/source-builder-workflow.md`: align workflow wording with the new proof matrix.
- Create `docs/operator/universal-wild-no-block-contract.md`: human-readable contract for no-block apply, mechanic support levels, and proof matrix.
- Optionally commit `docs/research/2026-07-09-hsconfig-universal-wild-skill-audit/` after checking it is schema-valid and intentionally referenced.

---

### Task 1: Add Mechanic Support Registry

**Files:**
- Create: `src/hsconfig/mechanic_support.py`
- Create: `tests/test_mechanic_support.py`

**Interfaces:**
- Produces: `support_for_roles(roles: Iterable[str]) -> list[dict[str, Any]]`
- Produces: `summarize_mechanic_support(rows: Iterable[dict[str, Any]]) -> dict[str, Any]`
- Later tasks consume those helpers from `config_readiness.py`.

- [ ] **Step 1: Write the failing registry tests**

Create `tests/test_mechanic_support.py`:

```python
from hsconfig.mechanic_support import support_for_roles, summarize_mechanic_support


def test_support_for_roles_classifies_direct_partial_and_warning_only():
    rows = support_for_roles(["battlecry", "location", "dredge", "tradeable", "unknown_role"])

    by_mechanic = {row["mechanic"]: row for row in rows}
    assert by_mechanic["battlecry"]["support_level"] == "direct"
    assert by_mechanic["location"]["support_level"] == "partial"
    assert by_mechanic["dredge"]["support_level"] == "warning_only"
    assert by_mechanic["tradeable"]["support_level"] == "warning_only"
    assert "unknown_role" not in by_mechanic
    assert by_mechanic["dredge"]["normal_path_surfaces"] == ["report-only"]


def test_summarize_mechanic_support_counts_warning_only_cards():
    summary = summarize_mechanic_support(
        [
            {
                "card_id": "CARD_001",
                "mechanic_support": [
                    {"mechanic": "dredge", "support_level": "warning_only"},
                    {"mechanic": "battlecry", "support_level": "direct"},
                ],
            },
            {
                "card_id": "CARD_002",
                "mechanic_support": [
                    {"mechanic": "location", "support_level": "partial"},
                ],
            },
        ]
    )

    assert summary["support_level_counts"] == {
        "direct": 1,
        "partial": 1,
        "warning_only": 1,
    }
    assert summary["warning_only_mechanics"] == ["dredge"]
    assert summary["warning_only_card_count"] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest -q tests/test_mechanic_support.py
```

Expected: fail with `ModuleNotFoundError: No module named 'hsconfig.mechanic_support'`.

- [ ] **Step 3: Implement the registry**

Create `src/hsconfig/mechanic_support.py`:

```python
from __future__ import annotations

from collections import Counter
from typing import Any, Iterable


MECHANIC_SUPPORT: dict[str, dict[str, Any]] = {
    "battlecry": {
        "support_level": "direct",
        "normal_path_surfaces": [
            "CARDID.json:BeforeBattlecryTargetBonus",
            "CARDID.json:BeforePlayCardBonus",
            "Combo.json:exact_sequence",
        ],
        "warning_boundary": "Non-targeted battlecry value remains general card timing unless a source-backed target rule exists.",
    },
    "discover": {
        "support_level": "direct",
        "normal_path_surfaces": [
            "CARDID.json:OnDiscoverCardBonus",
            "CARDID.json:BeforePlayCardBonus",
        ],
        "warning_boundary": "Only source-resolved option identity lowers; unresolved options stay suppressed.",
    },
    "overload": {
        "support_level": "direct",
        "normal_path_surfaces": [
            "CARDID.json:BeforePlayCardBonus",
            "GlobalValues.json:deck_posture",
        ],
        "warning_boundary": "Exact future-mana planning is heuristic, not a dedicated overload planner.",
    },
    "weapon": {
        "support_level": "direct",
        "normal_path_surfaces": [
            "CARDID.json:BeforePhysicalAttackBonus",
            "CARDID.json:BeforePlayCardBonus",
            "Combo.json:exact_sequence",
        ],
        "warning_boundary": "Exact weapon combos still require explicit sequence evidence.",
    },
    "hero_power": {
        "support_level": "direct",
        "normal_path_surfaces": ["CARDID.json:BeforeUseHeroPowerBonus"],
        "warning_boundary": "Unresolved or random hero-power identity stays warning-only.",
    },
    "hero_power_transform": {
        "support_level": "direct",
        "normal_path_surfaces": ["CARDID.json:BeforeUseHeroPowerBonus", "GlobalValues.json:deck_posture"],
        "warning_boundary": "Only exact transformed hero-power identity lowers.",
    },
    "discard": {
        "support_level": "direct",
        "normal_path_surfaces": ["CARDID.json:BeforePlayCardBonus"],
        "warning_boundary": "Hidden hand-discard outcomes follow card rules; enabler timing is lowerable.",
    },
    "deathrattle": {
        "support_level": "partial",
        "normal_path_surfaces": ["CARDID.json:BeforePlayCardBonus", "CARDID.json:OnBoardBonus"],
        "warning_boundary": "Trigger ordering and resurrection quality are not dedicated normal-path surfaces.",
    },
    "reborn": {
        "support_level": "partial",
        "normal_path_surfaces": ["CARDID.json:BeforePlayCardBonus", "CARDID.json:OnBoardBonus"],
        "warning_boundary": "Respawn value is represented only through deploy or preserve posture.",
    },
    "recruit": {
        "support_level": "partial",
        "normal_path_surfaces": ["CARDID.json:BeforePlayCardBonus", "GlobalValues.json:board_pressure"],
        "warning_boundary": "HSConfig can time the recruiter, not choose the pulled card beyond deck construction.",
    },
    "freeze": {
        "support_level": "partial",
        "normal_path_surfaces": [
            "CARDID.json:BeforePlayCardBonus",
            "CARDID.json:BeforeBattlecryTargetBonus",
            "CARDID.json:BeforeUseHeroPowerBonus",
        ],
        "warning_boundary": "Generic spell-target freeze is not a dedicated normal-path target surface.",
    },
    "lifesteal": {
        "support_level": "partial",
        "normal_path_surfaces": [
            "CARDID.json:BeforePlayCardBonus",
            "CARDID.json:BeforePhysicalAttackBonus",
            "GlobalValues.json:survivability_posture",
        ],
        "warning_boundary": "Exact heal-threshold planning is not a dedicated normal-path surface.",
    },
    "taunt": {
        "support_level": "partial",
        "normal_path_surfaces": ["CARDID.json:OnBoardBonus", "CARDID.json:BeforePlayCardBonus"],
        "warning_boundary": "Taunt is mostly defensive board value, not a dedicated taunt planner.",
    },
    "rush": {
        "support_level": "partial",
        "normal_path_surfaces": ["CARDID.json:BeforePhysicalAttackBonus", "CARDID.json:BeforePlayCardBonus"],
        "warning_boundary": "Attack posture lowers; full trade selection remains broader bot evaluation.",
    },
    "charge": {
        "support_level": "partial",
        "normal_path_surfaces": ["CARDID.json:BeforePhysicalAttackBonus", "CARDID.json:BeforePlayCardBonus"],
        "warning_boundary": "Attack posture lowers; lethal math remains broader bot evaluation.",
    },
    "location": {
        "support_level": "partial",
        "normal_path_surfaces": ["CARDID.json:BeforePlayCardBonus"],
        "warning_boundary": "Repeated location activation and targeting are not first-class normal-path surfaces.",
    },
    "secret": {
        "support_level": "partial",
        "normal_path_surfaces": ["CARDID.json:BeforePlayCardBonus", "Mulligan.json:opening_hand"],
        "warning_boundary": "Secret ordering and hidden-information trap timing are not separate normal-path surfaces.",
    },
    "generated_entity": {
        "support_level": "partial",
        "normal_path_surfaces": ["CARDID.json:resolved_identity", "CARDID.json:OnDiscoverCardBonus"],
        "warning_boundary": "Random generation pools stay warning-only unless exact identity is source-backed.",
    },
    "aura": {
        "support_level": "partial",
        "normal_path_surfaces": ["CARDID.json:OnBoardBonus", "CARDID.json:BeforePlayCardBonus"],
        "warning_boundary": "Continuous aura math and stacked board effects are not dedicated normal-path surfaces.",
    },
    "destroy": {
        "support_level": "partial",
        "normal_path_surfaces": [
            "CARDID.json:BeforeBattlecryTargetBonus",
            "CARDID.json:BeforePhysicalAttackBonus",
            "CARDID.json:BeforePlayCardBonus",
        ],
        "warning_boundary": "Generic targeted destroy spells are only partially lowerable.",
    },
    "silence": {
        "support_level": "partial",
        "normal_path_surfaces": ["CARDID.json:BeforeBattlecryTargetBonus", "CARDID.json:BeforePlayCardBonus"],
        "warning_boundary": "Generic silence spell targeting is not a dedicated normal-path surface.",
    },
    "transform": {
        "support_level": "partial",
        "normal_path_surfaces": ["CARDID.json:BeforeBattlecryTargetBonus", "CARDID.json:BeforePlayCardBonus"],
        "warning_boundary": "Random transform outcomes and generic spell targets stay warning-only.",
    },
    "dredge": {
        "support_level": "warning_only",
        "normal_path_surfaces": ["report-only"],
        "warning_boundary": "Dredge option selection has no documented normal-path VisionAI choice surface.",
    },
    "tradeable": {
        "support_level": "warning_only",
        "normal_path_surfaces": ["report-only"],
        "warning_boundary": "Trade-now decisions have no documented normal-path VisionAI runtime block.",
    },
}


ROLE_ALIASES = {
    "shadow_hero_power": "hero_power_transform",
    "hero_attack": "weapon",
    "weapon_pressure": "weapon",
    "spell_generation": "generated_entity",
    "token_board": "aura",
    "board_buff": "aura",
    "board_scaling": "aura",
    "board_flood": "aura",
    "hand_mutation": "discard",
    "payoff_summon": "generated_entity",
    "magnetic": "aura",
    "treant": "aura",
}


def support_for_roles(roles: Iterable[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for role in roles:
        mechanic = ROLE_ALIASES.get(str(role).lower(), str(role).lower())
        spec = MECHANIC_SUPPORT.get(mechanic)
        if spec is None or mechanic in seen:
            continue
        seen.add(mechanic)
        rows.append({"mechanic": mechanic, **spec})
    return sorted(rows, key=lambda row: row["mechanic"])


def summarize_mechanic_support(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    level_counts: Counter[str] = Counter()
    warning_mechanics: set[str] = set()
    warning_cards: set[str] = set()
    for row in rows:
        card_id = str(row.get("card_id", ""))
        for support in row.get("mechanic_support", []):
            if not isinstance(support, dict):
                continue
            level = str(support.get("support_level", ""))
            mechanic = str(support.get("mechanic", ""))
            if not level:
                continue
            level_counts[level] += 1
            if level == "warning_only":
                warning_mechanics.add(mechanic)
                if card_id:
                    warning_cards.add(card_id)
    return {
        "support_level_counts": {
            "direct": level_counts["direct"],
            "partial": level_counts["partial"],
            "warning_only": level_counts["warning_only"],
        },
        "warning_only_mechanics": sorted(warning_mechanics),
        "warning_only_card_count": len(warning_cards),
    }
```

- [ ] **Step 4: Run registry tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest -q tests/test_mechanic_support.py
```

Expected: `2 passed`.

- [ ] **Step 5: Commit Task 1**

```powershell
git add src/hsconfig/mechanic_support.py tests/test_mechanic_support.py
git commit -m "feat: add mechanic support registry"
```

---

### Task 2: Add Mechanic Support To Per-Card Readiness

**Files:**
- Modify: `src/hsconfig/config_readiness.py`
- Modify: `tests/test_config_readiness.py`

**Interfaces:**
- Consumes: `support_for_roles(...)` and `summarize_mechanic_support(...)` from Task 1.
- Produces: `per_card_config_readiness_report["cards"][card_id]["mechanic_support"]`
- Produces: `per_card_config_readiness_report["summary"]["mechanic_support"]`

- [ ] **Step 1: Write failing readiness test**

Append to `tests/test_config_readiness.py`:

```python
def test_config_readiness_reports_mechanic_support_without_blocking_load_safe():
    report = build_config_readiness_report(
        deck_identity={
            "deck_name": "Mechanic Deck",
            "deck_slug": "mechanicdeck",
            "cards": [
                {"card_id": "DREDGE_001", "name": "Dredge Card", "roles": ["dredge"], "count": 1},
                {"card_id": "BATTLE_001", "name": "Battlecry Card", "roles": ["battlecry"], "count": 1},
            ],
        },
        claim_coverage={"uncovered_cards": []},
        gameplan_contract={
            "deck_name": "Mechanic Deck",
            "deck_slug": "mechanicdeck",
            "cards": {
                "DREDGE_001": {
                    "card_id": "DREDGE_001",
                    "name": "Dredge Card",
                    "roles": ["dredge"],
                    "coverage_status": "source_backed_static_semantics",
                },
                "BATTLE_001": {
                    "card_id": "BATTLE_001",
                    "name": "Battlecry Card",
                    "roles": ["battlecry"],
                    "coverage_status": "source_backed_static_semantics",
                },
            },
        },
        mulligan_plan={"rules": []},
        card_behavior_plan={"rows": [], "suppressed": []},
        combo_plan={"combos": []},
        global_values_authority_matrix={"allowed_step1_overlays": []},
        emitted_cardid_files=["DREDGE_001.json", "BATTLE_001.json"],
    )

    assert report["cards"]["DREDGE_001"]["mechanic_support"][0]["mechanic"] == "dredge"
    assert report["cards"]["DREDGE_001"]["mechanic_support"][0]["support_level"] == "warning_only"
    assert report["cards"]["BATTLE_001"]["mechanic_support"][0]["support_level"] == "direct"
    assert report["summary"]["mechanic_support"]["warning_only_mechanics"] == ["dredge"]
    assert report["summary"]["mechanic_support"]["support_level_counts"]["direct"] == 1
    assert report["summary"]["mechanic_support"]["support_level_counts"]["warning_only"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest -q tests/test_config_readiness.py::test_config_readiness_reports_mechanic_support_without_blocking_load_safe
```

Expected: fail because `mechanic_support` is not present.

- [ ] **Step 3: Implement readiness integration**

Modify `src/hsconfig/config_readiness.py`:

```python
from hsconfig.mechanic_support import support_for_roles, summarize_mechanic_support
```

Inside the card loop, before assigning `rows[card_id]`, add:

```python
        mechanic_support = support_for_roles(card.get("roles", []))
```

Add the field to each card row:

```python
            "mechanic_support": mechanic_support,
```

After building all rows, change the summary call to pass the rows:

```python
        "summary": _summary(
            total_cards=len(rows),
            lane_counter=lane_counter,
            missing_counter=missing_counter,
            rows=rows.values(),
        ),
```

Change `_summary` signature and body:

```python
def _summary(
    *,
    total_cards: int,
    lane_counter: Counter[str],
    missing_counter: Counter[str],
    rows: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "total_cards": total_cards,
        **{lane: lane_counter[lane] for lane in LANES},
        "cards_needing_guide_claims": missing_counter["needs_guide_claim"],
        "cards_needing_runtime_surface": missing_counter["needs_runtime_surface"],
        "cards_needing_mulligan_claims": missing_counter["needs_mulligan_claim"],
        "cards_needing_combo_sequence": missing_counter["needs_combo_sequence"],
        "cards_needing_condition_lowering": missing_counter["needs_condition_lowering"],
        "cards_needing_mechanic_lowering": missing_counter["needs_mechanic_lowering"],
        "mechanic_support": summarize_mechanic_support(rows),
    }
```

If `Iterable` is not already imported, change the import line:

```python
from typing import Any, Iterable
```

- [ ] **Step 4: Run readiness tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest -q tests/test_config_readiness.py tests/test_mechanic_support.py
```

Expected: all tests pass.

- [ ] **Step 5: Commit Task 2**

```powershell
git add src/hsconfig/config_readiness.py tests/test_config_readiness.py
git commit -m "feat: report mechanic support readiness"
```

---

### Task 3: Surface Mechanic Warnings In Operator Summary And Guidance

**Files:**
- Modify: `src/hsconfig/operator_summary.py`
- Modify: `src/hsconfig/operator_guidance.py`
- Modify: `tests/test_operator_summary.py`
- Modify: `tests/test_operator_guidance.py`

**Interfaces:**
- Consumes: `config_readiness_report["summary"]["mechanic_support"]` from Task 2.
- Produces: `operator_summary["mechanic_warning_summary"]`
- Produces: `operator_summary["operator_guidance"]["mechanic_warning_summary"]`

- [ ] **Step 1: Write failing operator summary test**

Append to `tests/test_operator_summary.py`:

```python
from hsconfig.operator_summary import build_operator_summary


def test_operator_summary_exposes_mechanic_warnings_without_blocking_apply():
    summary = build_operator_summary(
        deck_name="Warning Deck",
        deck_code="AAEBAQAAAA==",
        technical_validation={"status": "passed"},
        guide_source_depth={"source_depth_status": "static_semantics_only", "claim_count": 0},
        config_readiness_report={
            "summary": {
                "total_cards": 1,
                "generic_low_confidence": 0,
                "cards_needing_guide_claims": 0,
                "cards_needing_runtime_surface": 0,
                "cards_needing_mulligan_claims": 0,
                "cards_needing_combo_sequence": 0,
                "cards_needing_condition_lowering": 0,
                "cards_needing_mechanic_lowering": 0,
                "mechanic_support": {
                    "support_level_counts": {"direct": 0, "partial": 0, "warning_only": 1},
                    "warning_only_mechanics": ["dredge"],
                    "warning_only_card_count": 1,
                },
            },
            "cards": {},
        },
        generated_files=[
            "CustomConfig/warningdeck/GlobalValues.json",
            "CustomConfig/warningdeck/Mulligan.json",
            "CustomConfig/warningdeck/DREDGE_001.json",
        ],
    )

    assert summary["technical_status"] == "VALID_PACKAGE"
    assert summary["runtime_apply_mode"] == "load_safe_apply"
    assert summary["runtime_apply_allowed"] is True
    assert summary["mechanic_warning_summary"]["warning_only_mechanics"] == ["dredge"]
    assert summary["operator_guidance"]["safe_to_apply"] is True
```

- [ ] **Step 2: Write failing guidance test**

Append to `tests/test_operator_guidance.py`:

```python
def test_warning_guidance_carries_mechanic_warning_summary():
    guidance = build_operator_guidance(
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "VALID_BUT_NOT_GUIDE_STRONG",
            "apply_policy": "ALLOWED_WITH_WARNINGS",
            "runtime_apply_allowed": True,
            "runtime_apply_mode": "load_safe_apply",
            "mechanic_warning_summary": {
                "support_level_counts": {"direct": 0, "partial": 0, "warning_only": 1},
                "warning_only_mechanics": ["tradeable"],
                "warning_only_card_count": 1,
            },
            "semantic_blockers": [],
        }
    )

    assert guidance["safe_to_apply"] is True
    assert guidance["normal_next_step"] == "apply_with_warnings"
    assert guidance["mechanic_warning_summary"]["warning_only_mechanics"] == ["tradeable"]
```

- [ ] **Step 3: Run tests to verify they fail**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest -q tests/test_operator_summary.py::test_operator_summary_exposes_mechanic_warnings_without_blocking_apply tests/test_operator_guidance.py::test_warning_guidance_carries_mechanic_warning_summary
```

Expected: fail because `mechanic_warning_summary` is missing.

- [ ] **Step 4: Implement operator summary field**

In `src/hsconfig/operator_summary.py`, add helper:

```python
def _mechanic_warning_summary(config_readiness_report: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(config_readiness_report, dict):
        return {
            "support_level_counts": {"direct": 0, "partial": 0, "warning_only": 0},
            "warning_only_mechanics": [],
            "warning_only_card_count": 0,
        }
    summary = config_readiness_report.get("summary", {})
    if not isinstance(summary, dict):
        return {
            "support_level_counts": {"direct": 0, "partial": 0, "warning_only": 0},
            "warning_only_mechanics": [],
            "warning_only_card_count": 0,
        }
    mechanic_support = summary.get("mechanic_support", {})
    if not isinstance(mechanic_support, dict):
        return {
            "support_level_counts": {"direct": 0, "partial": 0, "warning_only": 0},
            "warning_only_mechanics": [],
            "warning_only_card_count": 0,
        }
    return {
        "support_level_counts": {
            "direct": _int_value(mechanic_support.get("support_level_counts", {}).get("direct", 0))
            if isinstance(mechanic_support.get("support_level_counts"), dict)
            else 0,
            "partial": _int_value(mechanic_support.get("support_level_counts", {}).get("partial", 0))
            if isinstance(mechanic_support.get("support_level_counts"), dict)
            else 0,
            "warning_only": _int_value(mechanic_support.get("support_level_counts", {}).get("warning_only", 0))
            if isinstance(mechanic_support.get("support_level_counts"), dict)
            else 0,
        },
        "warning_only_mechanics": [
            str(item) for item in mechanic_support.get("warning_only_mechanics", [])
        ]
        if isinstance(mechanic_support.get("warning_only_mechanics"), list)
        else [],
        "warning_only_card_count": _int_value(mechanic_support.get("warning_only_card_count", 0)),
    }
```

Inside `build_operator_summary`, before `summary = { ... }`, add:

```python
    mechanic_warning_summary = _mechanic_warning_summary(config_readiness_report)
```

Inside the summary dict, add:

```python
        "mechanic_warning_summary": mechanic_warning_summary,
```

- [ ] **Step 5: Implement operator guidance field**

In `src/hsconfig/operator_guidance.py`, add helper:

```python
def _mechanic_warning_fields(summary: dict[str, Any]) -> dict[str, Any]:
    mechanic_warning_summary = summary.get("mechanic_warning_summary")
    if isinstance(mechanic_warning_summary, dict):
        return {"mechanic_warning_summary": mechanic_warning_summary}
    return {
        "mechanic_warning_summary": {
            "support_level_counts": {"direct": 0, "partial": 0, "warning_only": 0},
            "warning_only_mechanics": [],
            "warning_only_card_count": 0,
        }
    }
```

Add `**_mechanic_warning_fields(summary),` to every return payload in `build_operator_guidance(...)`, next to `**_runtime_apply_fields(summary),`.

- [ ] **Step 6: Run operator tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest -q tests/test_operator_summary.py tests/test_operator_guidance.py
```

Expected: all tests pass.

- [ ] **Step 7: Commit Task 3**

```powershell
git add src/hsconfig/operator_summary.py src/hsconfig/operator_guidance.py tests/test_operator_summary.py tests/test_operator_guidance.py
git commit -m "feat: expose mechanic warnings in operator summary"
```

---

### Task 4: Prove 12-Deck Universal No-Block Matrix

**Files:**
- Create: `tests/test_universal_wild_no_block_matrix.py`

**Interfaces:**
- Consumes: normal `prepare` CLI path through `hsconfig.cli.main`.
- Produces: regression proof that the provided 12 decks produce load-safe packages without source-confidence blocking.

- [ ] **Step 1: Write the failing or initially passing matrix test**

Create `tests/test_universal_wild_no_block_matrix.py`:

```python
import json
from pathlib import Path

import pytest

from hsconfig.cli import main


DECKS = [
    ("ShadowPriest", "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA="),
    ("CtAPaladin", "AAEBAZ8FBowBwP0ChJYFzpwGprMGg8IHDIgO+NICg94DkeQDzusDyaAE4aQEwcQFhY4GmY4G9ZUGmvwHAAA="),
    ("PirateRogue", "AAEBAaIHApG8AuXRAg6MAtQF+w/psAPz3QOvoASKyQSa2wTXowW/9wXWngb8pQb8qAatxQYAAA=="),
    ("BigShaman", "AAEBAaoIBpQD5LcDv84E9qMGgbgGmvYGDM4P0hP2vQKPlAPW9QO8tgT08gXqmAbGpgakpwb44gas/QYAAA=="),
    ("Discolock", "AAEBAf0GBM4Hj4ID8aEG9qEGDbW5A9XRA9DhA5iSBauSBZXKBteXB4SZB6StB8ayB9a+B9m+B8+/BwAA"),
    ("TreantDruid", "AAEBAZICAt/7ApOyBw7NuwLB8wL8rQP/rQOV4APs9QOvgASuwASy3QTO5AWw+gXZ/wXJ0Aat4gYAAA=="),
    ("ImbueMage", "AAEBAf0EBIUXm80DvO0Egb8GDcAB9KsD0+wD1uwDr8QForMG1voG3PoG9PwG94EHs4cHwIcH7o0HAAA="),
    ("MechPala", "AAEBAZ8FAtS9BMekBg6f9QLW/gLX/gKHrgOStQThtQTa0wTZ0AW5/gWf4Qa08Qbi8Qa6lgea/AcAAQPzswbHpAb2swbHpAbu3gbHpAYAAA=="),
    ("Kingslayer", "AAEBAaIHBpG8ApKDB4aoB4eoB4ioB4jZBwyMAtQF6bAD1bYEiskE16MF7p4G/KUG/KgGs8EG6sQGrcUGAAA="),
    ("Boarlock", "AAEBAf0GBuAF054G7qEGxKIG0YIHqYgHDJDHAvLQAp2pA5vNA9P5A6bqBPTGBYSeBpWzBpTKBoSZB4adBwAA"),
    ("PirateDH", "AAEBAea5AwaRvALUyAP51QOHiwTh+AX8wAYM+w/psAPyyQPltgSl4gSr4gSVqgX8qAbYwAb2wAatxQax6wYAAA=="),
    ("CuteWarrior", "AAEBAQcEkbwCkdAD69YHstgHDY0Q6bADpLYDxN4D/9sEj5UFlaoFtNEF9PIFovoF/KgGltMGtI8HAAA="),
]


@pytest.mark.parametrize(("deck_name", "deck_code"), DECKS)
def test_valid_wild_deck_produces_load_safe_warning_apply_package(
    tmp_path: Path,
    capsys,
    monkeypatch,
    deck_name: str,
    deck_code: str,
):
    monkeypatch.setattr("hsconfig.package_builder.fetch_latest_cards", lambda timeout=10.0: [])
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
            "--json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    operator = json.loads((out / "reports" / "operator_summary.json").read_text(encoding="utf-8"))
    deck_identity = json.loads((out / "reports" / "deck_identity.json").read_text(encoding="utf-8"))
    deck_dirs = [path for path in (out / "CustomConfig").iterdir() if path.is_dir()]
    assert len(deck_dirs) == 1
    deck_dir = deck_dirs[0]
    special_files = {"GlobalValues.json", "Mulligan.json", "Combo.json", "Presume.json", "Concede.json"}
    card_files = {path.name.removesuffix(".json") for path in deck_dir.glob("*.json") if path.name not in special_files}
    deck_card_ids = {str(card["card_id"]) for card in deck_identity["cards"]}

    assert code == 0
    assert payload["status"] == "passed"
    assert operator["technical_status"] == "VALID_PACKAGE"
    assert operator["runtime_load_safe"] is True
    assert operator["runtime_apply_mode"] == "load_safe_apply"
    assert operator["runtime_apply_allowed"] is True
    assert operator["next_action"] in {"READY_TO_APPLY_OR_HANDOFF", "READY_TO_APPLY_WITH_WARNINGS"}
    assert (deck_dir / "GlobalValues.json").is_file()
    assert (deck_dir / "Mulligan.json").is_file()
    assert card_files == deck_card_ids
    assert not (deck_dir / "Presume.json").exists()
    assert not (deck_dir / "Concede.json").exists()
```

- [ ] **Step 2: Run matrix test**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest -q tests/test_universal_wild_no_block_matrix.py
```

Expected: pass. If it fails because full CardID coverage is not exact, inspect `compile_cardid.py` and `gameplan_contract.py`; do not weaken the expectation until a real impossible deck-identity case is proven.

- [ ] **Step 3: Commit Task 4**

```powershell
git add tests/test_universal_wild_no_block_matrix.py
git commit -m "test: prove universal wild no-block matrix"
```

---

### Task 5: Document The Contract Without Bloated Operator Paths

**Files:**
- Create: `docs/operator/universal-wild-no-block-contract.md`
- Modify: `docs/operator/README.md`
- Modify: `docs/operator/source-builder-workflow.md`

**Interfaces:**
- Consumes: mechanic support levels from Task 1 and matrix proof from Task 4.
- Produces: a single concise operator reference for no-block behavior and mechanic warnings.

- [ ] **Step 1: Add the contract document**

Create `docs/operator/universal-wild-no-block-contract.md`:

```markdown
# Universal Wild No-Block Contract

HSConfig must create a load-safe initial HearthRanger CustomConfig package for every valid deck input.

## Runtime Apply Promise

- `technical_status=VALID_PACKAGE` means the emitted package is structurally valid.
- `runtime_load_safe=true` means the package passed HSConfig's normal pre-run load-safety contract.
- `runtime_apply_mode=load_safe_apply` means normal `hsconfig apply --json` is allowed.
- `SOURCE_BACKED_STRONG` means strong source confidence. It is not the runtime-write gate.
- `READY_TO_APPLY_WITH_WARNINGS` is still a usable initial package.

## Hard Blocks

HSConfig still blocks when it cannot produce a correct runtime package:

- malformed or unsupported deckcode
- unresolved exact deck-card identity needed for `<CARDID>.json`
- invalid JSON
- unsupported VisionAI filename or block
- missing `GlobalValues.json`, `Mulligan.json`, or per-card CardID files
- undeclared runtime files
- nested runtime files
- normal-path `Presume.json` or `Concede.json`
- forged or stale apply evidence

## Non-Blocking Warnings

These must stay visible but must not block a valid package:

- missing guide claims
- generic-low-confidence cards
- runtime-surface gaps that stay report-only
- unsupported semantic claims that are suppressed instead of emitted
- partial mechanic support
- warning-only mechanics

## Mechanic Support Levels

`direct` means HSConfig can emit a documented normal-path runtime row for the mechanic when source/card identity is exact.

`partial` means HSConfig can emit only the parts that map to documented VisionAI blocks; the rest stays in warnings or suppression reports.

`warning_only` means HSConfig must not invent a runtime row for the mechanic's signature action.

Current warning-only mechanics:

- Dredge: no documented Dredge-choice equivalent to `OnDiscoverCardBonus`.
- Tradeable: no documented trade-now runtime block.

## Proof Matrix

The universal matrix test covers:

- ShadowPriest
- CtAPaladin
- PirateRogue
- BigShaman
- Discolock
- TreantDruid
- ImbueMage
- MechPala
- Kingslayer
- Boarlock
- PirateDH
- CuteWarrior

Each deck must produce `VALID_PACKAGE`, `runtime_load_safe=true`, `runtime_apply_mode=load_safe_apply`, `GlobalValues.json`, `Mulligan.json`, and one per-card JSON file for every unique deck CardID.
```

- [ ] **Step 2: Link from operator README**

In `docs/operator/README.md`, after the `Single Gate` section intro, add:

```markdown
For the durable no-block contract across valid Wild decks, see
`docs/operator/universal-wild-no-block-contract.md`.
```

In the `Fixture Matrix` section, add:

```markdown
The representative fixture matrix proves source-depth breadth. The universal
no-block matrix proves the separate runtime promise: every valid listed deck
still creates a load-safe initial package even when source confidence remains
warning-only.
```

- [ ] **Step 3: Align source-builder workflow wording**

In `docs/operator/source-builder-workflow.md`, add a short paragraph near the apply step:

```markdown
Guide strength is not the write gate. When `technical_status=VALID_PACKAGE` and
`runtime_apply_mode=load_safe_apply`, HSConfig may apply the initial package even
if `semantic_status=VALID_BUT_NOT_GUIDE_STRONG`. Use the warnings to improve
future source depth; do not treat them as load-safety blockers.
```

- [ ] **Step 4: Run docs checks**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest -q tests/test_docs_active_path.py tests/test_skill_files.py
rg -n "ALLOWED_WITH_WARNINGS is not runtime write permission|blocks by default unless the package is source-backed ready|source-backed.*required.*apply" README.md docs\operator src tests .agents C:\Users\darbo\.codex\skills\hsconfig
```

Expected:

- pytest passes.
- `rg` returns only negative-assertion tests, or returns no active doc/code hits.

- [ ] **Step 5: Commit Task 5**

```powershell
git add docs/operator/universal-wild-no-block-contract.md docs/operator/README.md docs/operator/source-builder-workflow.md
git commit -m "docs: document universal no-block contract"
```

---

### Task 6: Research Artifact Consolidation

**Files:**
- Optionally add: `docs/research/2026-07-09-hsconfig-universal-wild-skill-audit/`
- Modify: `docs/research/README.md`

**Interfaces:**
- Consumes: validated `docs/research/2026-07-09-hsconfig-universal-wild-skill-audit/results/*.json`.
- Produces: one active research pointer. Prevents old untracked audit folders from acting as hidden operator truth.

- [ ] **Step 1: Validate the intended research artifact**

Run:

```powershell
python C:\Users\darbo\.codex\skills\research\validate_json.py -f docs\research\2026-07-09-hsconfig-universal-wild-skill-audit\fields.yaml -j docs\research\2026-07-09-hsconfig-universal-wild-skill-audit\results\VisionAI_Runtime_Surface_And_Load_Safety_Contract.json
python C:\Users\darbo\.codex\skills\research\validate_json.py -f docs\research\2026-07-09-hsconfig-universal-wild-skill-audit\fields.yaml -j docs\research\2026-07-09-hsconfig-universal-wild-skill-audit\results\Wild_Mechanic_Stress_Matrix.json
python C:\Users\darbo\.codex\skills\research\validate_json.py -f docs\research\2026-07-09-hsconfig-universal-wild-skill-audit\fields.yaml -j docs\research\2026-07-09-hsconfig-universal-wild-skill-audit\results\Card_Identity_And_Metadata_Resilience.json
python C:\Users\darbo\.codex\skills\research\validate_json.py -f docs\research\2026-07-09-hsconfig-universal-wild-skill-audit\fields.yaml -j docs\research\2026-07-09-hsconfig-universal-wild-skill-audit\results\Lean_No-Blocking_Operator_UX.json
```

Expected: all four validate with `100.0%` coverage.

- [ ] **Step 2: Add research README pointer**

Modify `docs/research/README.md` to include:

```markdown
## Active Universal Wild No-Block Audit

Use `docs/research/2026-07-09-hsconfig-universal-wild-skill-audit/` as the
active research package for the universal no-block and Wild mechanic support
contract. Older audit folders are historical evidence and must not override the
live operator docs or current tests.
```

- [ ] **Step 3: Inspect untracked research folders before staging**

Run:

```powershell
git status --short -- docs\research
```

Decision:

- Stage `docs/research/2026-07-09-hsconfig-universal-wild-skill-audit/` only if all four JSONs validate.
- Do not stage older untracked research folders unless a reviewer explicitly chooses to preserve them.

- [ ] **Step 4: Commit Task 6**

```powershell
git add docs/research/README.md docs/research/2026-07-09-hsconfig-universal-wild-skill-audit
git commit -m "docs: add universal wild no-block research audit"
```

---

### Task 7: Final Verification And Push Preparation

**Files:**
- No product file changes unless verification exposes a bug.

**Interfaces:**
- Consumes: all prior task outputs.
- Produces: verified branch ready for push or merge.

- [ ] **Step 1: Run targeted tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest -q tests/test_mechanic_support.py tests/test_config_readiness.py tests/test_operator_summary.py tests/test_operator_guidance.py tests/test_universal_wild_no_block_matrix.py tests/test_apply_gate.py tests/test_validate_package.py
```

Expected: all tests pass.

- [ ] **Step 2: Run full suite**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest -q
```

Expected: full suite passes. Current baseline before this plan was `595 passed, 2 skipped`.

- [ ] **Step 3: Run stale wording scan**

Run:

```powershell
rg -n "ALLOWED_WITH_WARNINGS is not runtime write permission|blocks by default unless the package is source-backed ready|source-backed.*required.*apply|warning packages are blocked" README.md docs\operator src tests .agents C:\Users\darbo\.codex\skills\hsconfig
```

Expected: no active stale wording. Negative-assertion tests are acceptable.

- [ ] **Step 4: Sync installed skill if docs changed**

If `.agents/skills/hsconfig` or skill-facing references changed, run:

```powershell
python scripts\sync_installed_skill.py
```

Then run:

```powershell
$env:PYTHONPATH='src'; python -m pytest -q tests/test_skill_sync.py tests/test_skill_files.py
```

Expected: pass.

- [ ] **Step 5: Inspect git status**

Run:

```powershell
git status --short --branch
```

Expected:

- branch is current working branch
- only intentional files are staged or committed
- old unrelated untracked research folders are not accidentally staged

- [ ] **Step 6: Final commit if needed**

If Task 7 required fixes:

```powershell
git add <changed files>
git commit -m "test: verify universal wild no-block contract"
```

- [ ] **Step 7: Push current branch**

Run:

```powershell
git push origin HEAD
```

Expected: push succeeds.

---

## Self-Review

- **Spec coverage:** The plan covers the requested no-block behavior, Wild mechanic breadth, CardID identity resilience, operator wording, strict load safety, and lean HSConfig scope. It explicitly avoids replay parsing, HSTuner, winrate, post-run tuning, Presume, and Concede.
- **Placeholder scan:** Each implementation task has exact file paths, code snippets, commands, expected results, and no placeholder-only instructions.
- **Type consistency:** New functions are consistently named `support_for_roles`, `summarize_mechanic_support`, and `_mechanic_warning_summary`. New payload field is consistently named `mechanic_warning_summary`.
- **Risk note:** Task 3 test data uses a synthetic deck code hash path and direct `build_operator_summary`; if an existing test imports conflict with the added import, merge imports instead of duplicating them.
- **Execution recommendation:** Use subagent-driven execution. Assign one worker per task and keep write ownership disjoint: registry, readiness, operator summary/guidance, matrix test, docs, research consolidation, final verification.

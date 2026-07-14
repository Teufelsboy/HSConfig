# Archetype-Aware Autonomous Mulligan Policy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make HSConfig's `policy_backed_autonomous_mulligan` fallback archetype-aware so every valid deck gets a useful non-default Mulligan plan without inventing source-backed claims or holding effect-only cards such as Darkbishop Benedictus.

**Architecture:** Keep the existing single-gate architecture. `reports/operator_summary.json` remains the only normal apply authority; source/contract reports remain diagnostic. Add a small policy-classification layer used only by `autonomous_mulligan_policy.py`, then expose the chosen lane and veto reasons in existing reports.

**Tech Stack:** Python 3.11+, pytest, existing HSConfig modules under `src/hsconfig`, no new dependencies, no new runtime surfaces.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig`.
- Do not add a second runtime apply gate.
- Do not make `source_contract_audit.json`, `source_to_runtime_explainability.json`, `source_claim_gap_report.json`, `strong_promotion_report.json`, or `config_usefulness` an apply authority.
- Runtime apply permission must still come from `reports/operator_summary.json` through the existing apply gate.
- Normal HSConfig output must remain limited to `GlobalValues.json`, `Mulligan.json`, `Combo.json`, and per-card `<CARDID>.json`.
- Do not add normal-path `Presume.json` or `Concede.json`.
- Do not add replay, winrate, post-game tuning, or HSTuner behavior to HSConfig.
- Preserve the Darkbishop boundary: start-of-game / hero-power-transform effects may stay visible in CardID semantics, but the enabler card must not become an opening-hand keep unless an explicit `mulligan_keep` source claim exists.
- `policy_backed_autonomous_mulligan` is weaker than source-backed evidence and must never promote a package to `SOURCE_BACKED_STRONG` by itself.
- Source-backed Mulligan claims always override policy fallback.
- Explicit, suppressed, or quarantined Mulligan source intent vetoes policy-backed keeps for that card.
- Keep the implementation small: no new dependency, no broad refactor, no new architecture layer beyond a focused policy helper.

---

## File Structure

- Modify `src/hsconfig/autonomous_mulligan_policy.py`
  - Add archetype lane classification and score candidates by lane-specific preferences.
  - Keep all actual policy-backed rule creation in this file.
- Modify `src/hsconfig/mulligan_plan.py`
  - Preserve existing policy fallback call.
  - Include lane metadata from policy rows in plan quality without changing source-backed precedence.
- Modify `src/hsconfig/source_claim_gap_report.py`
  - Show policy-backed Mulligan as closed-but-not-source-backed and include lane reason where available.
- Modify `src/hsconfig/config_usefulness.py`
  - Surface `policy_lane` and `policy_reason` for operator clarity.
- Modify `src/hsconfig/operator_summary.py`
  - Add compact `mulligan_policy_status` and `default_only_runtime_surfaces` summary fields.
- Modify `tests/test_autonomous_mulligan_policy.py`
  - Add direct unit tests for archetype-aware lane selection and veto behavior.
- Modify `tests/test_mulligan_plan.py`
  - Add integration tests for policy lane metadata and source-backed override behavior.
- Modify `tests/test_source_claim_gap_report.py`
  - Add report tests proving policy-backed closes default-only gap without being source-backed.
- Modify `tests/test_config_usefulness.py`
  - Add usefulness tests for policy lane output.
- Modify `tests/test_operator_summary.py`
  - Add operator summary tests for no default-only surfaces and policy status.
- Modify representative e2e tests only as needed:
  - `tests/test_shadowpriest_e2e.py`
  - `tests/test_universal_wild_no_block_matrix.py`
- Modify docs only after code is green:
  - `README.md`
  - `docs/operator/README.md`
  - `docs/operator/universal-wild-no-block-contract.md`
  - `.agents/skills/hsconfig/SKILL.md`
- Run `python scripts\sync_installed_skill.py` after updating `.agents/skills/hsconfig/SKILL.md`.

---

### Task 1: Add Archetype Lane Classification To Policy Fallback

**Files:**
- Modify: `src/hsconfig/autonomous_mulligan_policy.py`
- Test: `tests/test_autonomous_mulligan_policy.py`

**Interfaces:**
- Consumes:
  - `build_policy_backed_mulligan_rules(deck_name: str, deck_cards: Mapping[str, Any] | list[dict[str, Any]], card_roles: Mapping[str, Any], excluded_card_ids: set[str] | None = None, excluded_card_reasons: Mapping[str, str] | None = None) -> dict[str, Any]`
- Produces:
  - Same function signature.
  - Returned `rules[*]` include new string fields:
    - `policy_lane`
    - `policy_reason`
  - Returned `suppressed[*]` include:
    - `policy_lane`
    - `reason`
  - No caller must pass new parameters.

- [ ] **Step 1: Write failing tests for lane-specific aggro and big-deck policy**

Add these tests to `tests/test_autonomous_mulligan_policy.py`:

```python
def test_policy_backed_aggro_lane_prioritizes_one_drops_pressure_and_draw():
    result = build_policy_backed_mulligan_rules(
        deck_name="PirateDH",
        deck_cards={
            "ONE_DROP": {"name": "One Drop", "cost": 1},
            "DRAW_TWO": {"name": "Draw Two", "cost": 2},
            "SLOW_PAYOFF": {"name": "Slow Payoff", "cost": 5},
        },
        card_roles={
            "ONE_DROP": {"roles": ["one_drop", "pirate_pressure"]},
            "DRAW_TWO": {"roles": ["tempo_draw"]},
            "SLOW_PAYOFF": {"roles": ["late_payoff"]},
        },
    )

    assert result["status"] == "applied"
    assert [row["card"] for row in result["rules"]] == ["ONE_DROP", "DRAW_TWO"]
    assert {row["policy_lane"] for row in result["rules"]} == {"aggro"}
    assert all(row["source_type"] == "policy_backed_autonomous_mulligan" for row in result["rules"])
    assert result["suppressed"][0]["card"] == "SLOW_PAYOFF"
    assert result["suppressed"][0]["reason"] == "excluded_policy_role"


def test_policy_backed_big_lane_prioritizes_ramp_cheat_and_defensive_setup():
    result = build_policy_backed_mulligan_rules(
        deck_name="BigShaman",
        deck_cards={
            "RAMP": {"name": "Ramp", "cost": 2},
            "CHEAT": {"name": "Cheat", "cost": 3},
            "BIG_MINION": {"name": "Big Minion", "cost": 8},
        },
        card_roles={
            "RAMP": {"roles": ["ramp", "mana_cheat_setup"]},
            "CHEAT": {"roles": ["summon_from_deck", "cheat"]},
            "BIG_MINION": {"roles": ["late_payoff"]},
        },
    )

    assert result["status"] == "applied"
    assert [row["card"] for row in result["rules"]] == ["RAMP", "CHEAT"]
    assert {row["policy_lane"] for row in result["rules"]} == {"big"}
    assert result["suppressed"][0]["card"] == "BIG_MINION"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest -q tests/test_autonomous_mulligan_policy.py::test_policy_backed_aggro_lane_prioritizes_one_drops_pressure_and_draw tests/test_autonomous_mulligan_policy.py::test_policy_backed_big_lane_prioritizes_ramp_cheat_and_defensive_setup
```

Expected: both tests fail because `policy_lane` and lane-specific ranking are not implemented.

- [ ] **Step 3: Implement lane constants and classification**

In `src/hsconfig/autonomous_mulligan_policy.py`, add these constants near the existing role constants:

```python
ARCHETYPE_LANE_ROLE_HINTS = {
    "aggro": {
        "one_drop",
        "early_pressure",
        "pressure",
        "damage",
        "burn_reach",
        "board_flood",
        "token_board",
        "pirate_pressure",
        "mech_curve",
        "self_damage_pressure",
    },
    "combo": {
        "combo_setup",
        "combo_enabler",
        "tutor",
        "draw",
        "tempo_draw",
        "cycle",
    },
    "big": {
        "ramp",
        "mana_cheat_setup",
        "cheat",
        "summon_from_deck",
        "recruit",
        "defensive_setup",
    },
    "weapon": {
        "weapon_setup",
        "weapon",
        "pirate_pressure",
        "tutor",
        "draw",
    },
    "discard": {
        "discard_setup",
        "discard_outlet",
        "discard_payoff",
        "draw",
    },
    "board": {
        "board_flood",
        "token_board",
        "mech_curve",
        "treant_board",
        "early_pressure",
    },
}

ARCHETYPE_LANE_ROLE_RANKS = {
    "aggro": (
        "one_drop",
        "early_pressure",
        "pirate_pressure",
        "mech_curve",
        "board_flood",
        "token_board",
        "tempo_draw",
        "damage",
        "burn_reach",
    ),
    "combo": (
        "tutor",
        "draw",
        "tempo_draw",
        "cycle",
        "combo_setup",
        "combo_enabler",
    ),
    "big": (
        "ramp",
        "mana_cheat_setup",
        "cheat",
        "summon_from_deck",
        "recruit",
        "defensive_setup",
    ),
    "weapon": (
        "weapon_setup",
        "weapon",
        "pirate_pressure",
        "tutor",
        "draw",
    ),
    "discard": (
        "discard_outlet",
        "discard_setup",
        "discard_payoff",
        "draw",
    ),
    "board": (
        "board_flood",
        "token_board",
        "treant_board",
        "mech_curve",
        "early_pressure",
    ),
    "generic": PREFERRED_KEEP_ROLES,
}
```

Add helper functions:

```python
def _policy_lane(deck_name: str, roles: set[str]) -> str:
    lowered_name = deck_name.lower()
    name_lane = _lane_from_deck_name(lowered_name)
    if name_lane != "generic":
        return name_lane
    best_lane = "generic"
    best_score = 0
    for lane, hints in ARCHETYPE_LANE_ROLE_HINTS.items():
        score = len(roles & hints)
        if score > best_score:
            best_lane = lane
            best_score = score
    return best_lane


def _lane_from_deck_name(lowered_name: str) -> str:
    if any(token in lowered_name for token in ("pirate", "shadow", "aggro")):
        return "aggro"
    if any(token in lowered_name for token in ("big", "recruit")):
        return "big"
    if any(token in lowered_name for token in ("kingslayer", "weapon")):
        return "weapon"
    if any(token in lowered_name for token in ("disco", "discard")):
        return "discard"
    if any(token in lowered_name for token in ("treant", "mech")):
        return "board"
    if any(token in lowered_name for token in ("combo", "boar")):
        return "combo"
    return "generic"


def _lane_role_reason(lane: str, roles: set[str]) -> str:
    for role in ARCHETYPE_LANE_ROLE_RANKS.get(lane, PREFERRED_KEEP_ROLES):
        if role in roles:
            return role
    return _preferred_role_reason(roles)


def _lane_role_rank(lane: str, reason: str) -> int:
    ranked_roles = ARCHETYPE_LANE_ROLE_RANKS.get(lane, PREFERRED_KEEP_ROLES)
    try:
        return list(ranked_roles).index(reason)
    except ValueError:
        return 99
```

Update the candidate creation call inside `build_policy_backed_mulligan_rules`:

```python
        lane = _policy_lane(deck_name, roles)
        role_reason = _lane_role_reason(lane, roles)
        if role_reason and _safe_cost(card) <= 3:
            candidates.append(
                _candidate(
                    card_id,
                    card,
                    role_reason,
                    role_rank=_lane_role_rank(lane, role_reason),
                    policy_lane=lane,
                )
            )
```

Update `_candidate` and `_rule_from_candidate`:

```python
def _candidate(
    card_id: str,
    card: Mapping[str, Any],
    reason: str,
    role_rank: int,
    policy_lane: str,
) -> dict[str, Any]:
    return {
        "card": card_id,
        "cost": _safe_cost(card),
        "reason": reason,
        "role_rank": role_rank,
        "policy_lane": policy_lane,
    }


def _rule_from_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    card_id = str(candidate["card"])
    policy_lane = str(candidate.get("policy_lane", "generic"))
    reason = str(candidate["reason"])
    return {
        "card": card_id,
        "selector_kind": "card",
        "selector": card_id,
        "action": "hold",
        "condition": "*",
        "reason": f"policy_backed_autonomous_mulligan:{reason}",
        "confidence": "policy_backed",
        "source_type": "policy_backed_autonomous_mulligan",
        "policy_lane": policy_lane,
        "policy_reason": reason,
        "source_claim_ids": [],
    }
```

Update `_lowest_curve_anchor` to pass a lane:

```python
        _candidate(card_id, card, "lowest_curve_anchor", role_rank=10, policy_lane="generic")
```

When appending suppressed rows, add:

```python
                    "policy_lane": _policy_lane(deck_name, roles),
```

For excluded source-intent rows where roles are not available, add:

```python
                    "policy_lane": "source_veto",
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```powershell
python -m pytest -q tests/test_autonomous_mulligan_policy.py
```

Expected: all tests in the file pass.

- [ ] **Step 5: Commit Task 1**

```powershell
git add src/hsconfig/autonomous_mulligan_policy.py tests/test_autonomous_mulligan_policy.py
git commit -m "feat: add archetype-aware mulligan policy lanes"
```

---

### Task 2: Preserve Policy Metadata Through Mulligan Plan And Precedence

**Files:**
- Modify: `src/hsconfig/mulligan_plan.py`
- Test: `tests/test_mulligan_plan.py`

**Interfaces:**
- Consumes:
  - Policy rows from `build_policy_backed_mulligan_rules`.
- Produces:
  - `plan["quality"]["policy_lanes"] -> list[str]`
  - `plan["quality"]["policy_reasons"] -> list[str]`
  - Existing `rules[*]["policy_lane"]` and `rules[*]["policy_reason"]` preserved.

- [ ] **Step 1: Write failing tests for policy metadata and source override**

Add these tests to `tests/test_mulligan_plan.py`:

```python
def test_mulligan_plan_preserves_policy_lane_metadata():
    plan = build_mulligan_plan(
        deck_name="PirateRogue",
        claims=[],
        card_roles={
            "PIRATE": {"roles": ["one_drop", "pirate_pressure"]},
        },
        deck_cards={
            "PIRATE": {"name": "Pirate", "cost": 1},
        },
        allow_policy_backed=True,
    )

    keep = next(row for row in plan["rules"] if row["action"] == "hold")
    assert keep["source_type"] == "policy_backed_autonomous_mulligan"
    assert keep["policy_lane"] == "aggro"
    assert keep["policy_reason"] in {"one_drop", "pirate_pressure"}
    assert plan["quality"]["policy_lanes"] == ["aggro"]
    assert plan["quality"]["policy_reasons"] == [keep["policy_reason"]]


def test_source_backed_keep_suppresses_policy_fallback_even_for_better_curve_card():
    plan = build_mulligan_plan(
        deck_name="PirateRogue",
        claims=[
            {
                "claim_id": "source-keep",
                "claim_kind": "mulligan_keep",
                "cards": ["SOURCE_KEEP"],
                "conditions": "*",
                "claim_confidence": "source_backed",
            }
        ],
        card_roles={
            "SOURCE_KEEP": {"roles": ["tempo_draw"]},
            "POLICY_ONE": {"roles": ["one_drop", "pirate_pressure"]},
        },
        deck_cards={
            "SOURCE_KEEP": {"name": "Source Keep", "cost": 2},
            "POLICY_ONE": {"name": "Policy One", "cost": 1},
        },
        allow_policy_backed=True,
    )

    holds = [row for row in plan["rules"] if row["action"] == "hold"]
    assert [row["card"] for row in holds] == ["SOURCE_KEEP"]
    assert all(row.get("source_type") == "source_claim" for row in holds)
    assert plan["quality"]["policy_backed_keep_rule_count"] == 0
    assert plan["quality"]["status"] == "rich"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest -q tests/test_mulligan_plan.py::test_mulligan_plan_preserves_policy_lane_metadata tests/test_mulligan_plan.py::test_source_backed_keep_suppresses_policy_fallback_even_for_better_curve_card
```

Expected: first test fails on missing `policy_lanes` / `policy_reasons`; second should pass or continue passing.

- [ ] **Step 3: Add metadata aggregation**

In `src/hsconfig/mulligan_plan.py`, after `policy_backed_keep_rule_count`, add:

```python
    policy_lanes = sorted(
        {
            str(row.get("policy_lane", "generic"))
            for row in rules
            if row.get("source_type") == "policy_backed_autonomous_mulligan"
            and row.get("selector_kind") != "wildcard"
        }
    )
    policy_reasons = sorted(
        {
            str(row.get("policy_reason", "")).strip()
            for row in rules
            if row.get("source_type") == "policy_backed_autonomous_mulligan"
            and str(row.get("policy_reason", "")).strip()
        }
    )
```

Add the fields to `quality`:

```python
        "policy_lanes": policy_lanes,
        "policy_reasons": policy_reasons,
```

- [ ] **Step 4: Run tests**

Run:

```powershell
python -m pytest -q tests/test_mulligan_plan.py
```

Expected: all tests in `tests/test_mulligan_plan.py` pass.

- [ ] **Step 5: Commit Task 2**

```powershell
git add src/hsconfig/mulligan_plan.py tests/test_mulligan_plan.py
git commit -m "feat: expose mulligan policy lane metadata"
```

---

### Task 3: Surface Policy Lane In Gap And Usefulness Reports

**Files:**
- Modify: `src/hsconfig/source_claim_gap_report.py`
- Modify: `src/hsconfig/config_usefulness.py`
- Test: `tests/test_source_claim_gap_report.py`
- Test: `tests/test_config_usefulness.py`

**Interfaces:**
- Consumes:
  - `mulligan_plan_report["quality"]["policy_lanes"]`
  - `mulligan_plan_report["quality"]["policy_reasons"]`
- Produces:
  - Source gap deck surface row includes `policy_lanes` and `policy_reasons`.
  - Config usefulness Mulligan surface includes `policy_lanes` and `policy_reasons`.

- [ ] **Step 1: Write failing report tests**

Add to `tests/test_source_claim_gap_report.py`:

```python
def test_gap_report_includes_policy_lane_for_policy_backed_mulligan_surface():
    report = build_source_claim_gap_report(
        deck_name="PirateRogue",
        card_ids=["PIRATE"],
        config_readiness_summary={},
        mulligan_plan_report={
            "rules": [
                {
                    "card": "PIRATE",
                    "selector_kind": "card",
                    "action": "hold",
                    "source_type": "policy_backed_autonomous_mulligan",
                    "policy_lane": "aggro",
                    "policy_reason": "pirate_pressure",
                }
            ],
            "quality": {
                "status": "policy_backed",
                "has_concrete_keeps": True,
                "default_only": False,
                "policy_backed_keep_rule_count": 1,
                "policy_lanes": ["aggro"],
                "policy_reasons": ["pirate_pressure"],
            },
        },
    )

    mulligan = report["deck_surfaces"]["mulligan"]
    assert mulligan["source_depth_lane"] == "policy_backed_autonomous_mulligan"
    assert mulligan["policy_lanes"] == ["aggro"]
    assert mulligan["policy_reasons"] == ["pirate_pressure"]
    assert report["summary"]["deck_surface_gap_count"] == 0
```

Add to `tests/test_config_usefulness.py`:

```python
def test_config_usefulness_reports_mulligan_policy_lane_metadata():
    payload = build_config_usefulness(
        technical_status="VALID_PACKAGE",
        semantic_status="VALID_BUT_NOT_GUIDE_STRONG",
        config_readiness_summary={},
        mulligan_plan_report={
            "rules": [
                {
                    "card": "PIRATE",
                    "selector_kind": "card",
                    "action": "hold",
                    "source_type": "policy_backed_autonomous_mulligan",
                    "policy_lane": "aggro",
                    "policy_reason": "pirate_pressure",
                }
            ],
            "quality": {
                "status": "policy_backed",
                "has_concrete_keeps": True,
                "default_only": False,
                "policy_backed_rule_count": 1,
                "policy_backed_keep_rule_count": 1,
                "policy_lanes": ["aggro"],
                "policy_reasons": ["pirate_pressure"],
            },
        },
    )

    mulligan = payload["surfaces"]["mulligan"]
    assert mulligan["status"] == "policy_backed"
    assert mulligan["default_only"] is False
    assert mulligan["policy_lanes"] == ["aggro"]
    assert mulligan["policy_reasons"] == ["pirate_pressure"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest -q tests/test_source_claim_gap_report.py::test_gap_report_includes_policy_lane_for_policy_backed_mulligan_surface tests/test_config_usefulness.py::test_config_usefulness_reports_mulligan_policy_lane_metadata
```

Expected: fail on missing `policy_lanes` and `policy_reasons` fields.

- [ ] **Step 3: Implement report fields**

In `src/hsconfig/source_claim_gap_report.py`, where the policy-backed Mulligan deck surface row is built, add:

```python
            "policy_lanes": _string_list(quality.get("policy_lanes")),
            "policy_reasons": _string_list(quality.get("policy_reasons")),
```

If `_string_list` does not exist, add:

```python
def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item)]
```

In `src/hsconfig/config_usefulness.py`, in `_mulligan_surface`, add:

```python
    policy_lanes = (
        _string_list(quality.get("policy_lanes"))
        if isinstance(quality, dict)
        else []
    )
    policy_reasons = (
        _string_list(quality.get("policy_reasons"))
        if isinstance(quality, dict)
        else []
    )
```

Return these fields:

```python
        "policy_lanes": policy_lanes,
        "policy_reasons": policy_reasons,
```

Add helper:

```python
def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item)]
```

- [ ] **Step 4: Run report tests**

Run:

```powershell
python -m pytest -q tests/test_source_claim_gap_report.py tests/test_config_usefulness.py
```

Expected: all tests pass.

- [ ] **Step 5: Commit Task 3**

```powershell
git add src/hsconfig/source_claim_gap_report.py src/hsconfig/config_usefulness.py tests/test_source_claim_gap_report.py tests/test_config_usefulness.py
git commit -m "feat: report mulligan policy lane metadata"
```

---

### Task 4: Add Operator Summary Default-Only And Policy Status Fields

**Files:**
- Modify: `src/hsconfig/operator_summary.py`
- Test: `tests/test_operator_summary.py`

**Interfaces:**
- Consumes:
  - `config_usefulness["surfaces"]["mulligan"]`
- Produces:
  - `operator_summary["mulligan_policy_status"] -> dict[str, Any]`
  - `operator_summary["default_only_runtime_surfaces"] -> list[str]`

- [ ] **Step 1: Write failing operator-summary tests**

Add to `tests/test_operator_summary.py`:

```python
def test_operator_summary_exposes_policy_backed_mulligan_status_without_default_only():
    summary = build_operator_summary(
        deck_name="PirateRogue",
        generated_files=["CustomConfig/PirateRogue/GlobalValues.json", "CustomConfig/PirateRogue/Mulligan.json"],
        validation_report={"status": "VALID_PACKAGE"},
        config_readiness_summary={},
        config_usefulness={
            "surfaces": {
                "mulligan": {
                    "status": "policy_backed",
                    "default_only": False,
                    "policy_lanes": ["aggro"],
                    "policy_reasons": ["pirate_pressure"],
                }
            }
        },
    )

    assert summary["mulligan_policy_status"] == {
        "status": "policy_backed",
        "default_only": False,
        "policy_lanes": ["aggro"],
        "policy_reasons": ["pirate_pressure"],
    }
    assert summary["default_only_runtime_surfaces"] == []
```

Also add:

```python
def test_operator_summary_names_default_only_mulligan_surface_when_present():
    summary = build_operator_summary(
        deck_name="ThinDeck",
        generated_files=["CustomConfig/ThinDeck/GlobalValues.json", "CustomConfig/ThinDeck/Mulligan.json"],
        validation_report={"status": "VALID_PACKAGE"},
        config_readiness_summary={},
        config_usefulness={
            "surfaces": {
                "mulligan": {
                    "status": "thin",
                    "default_only": True,
                    "policy_lanes": [],
                    "policy_reasons": [],
                }
            }
        },
    )

    assert summary["default_only_runtime_surfaces"] == ["mulligan"]
    assert summary["mulligan_policy_status"]["default_only"] is True
```

If the local helper signature differs, inspect existing tests in `tests/test_operator_summary.py` and adapt the fixture style without changing the field assertions.

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest -q tests/test_operator_summary.py::test_operator_summary_exposes_policy_backed_mulligan_status_without_default_only tests/test_operator_summary.py::test_operator_summary_names_default_only_mulligan_surface_when_present
```

Expected: fail on missing fields.

- [ ] **Step 3: Implement summary helper**

In `src/hsconfig/operator_summary.py`, add a helper near other summary helpers:

```python
def _mulligan_policy_status(config_usefulness: dict[str, Any]) -> dict[str, Any]:
    surfaces = config_usefulness.get("surfaces", {}) if isinstance(config_usefulness, dict) else {}
    mulligan = surfaces.get("mulligan", {}) if isinstance(surfaces, dict) else {}
    if not isinstance(mulligan, dict):
        mulligan = {}
    return {
        "status": str(mulligan.get("status", "unknown")),
        "default_only": bool(mulligan.get("default_only")),
        "policy_lanes": _string_list(mulligan.get("policy_lanes")),
        "policy_reasons": _string_list(mulligan.get("policy_reasons")),
    }


def _default_only_runtime_surfaces(config_usefulness: dict[str, Any]) -> list[str]:
    surfaces = config_usefulness.get("surfaces", {}) if isinstance(config_usefulness, dict) else {}
    if not isinstance(surfaces, dict):
        return []
    default_only: list[str] = []
    for name, row in sorted(surfaces.items()):
        if isinstance(row, dict) and row.get("default_only") is True:
            default_only.append(str(name))
    return default_only
```

If `_string_list` does not exist in `operator_summary.py`, add:

```python
def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item)]
```

Where the operator summary payload is assembled, add:

```python
        "mulligan_policy_status": _mulligan_policy_status(config_usefulness),
        "default_only_runtime_surfaces": _default_only_runtime_surfaces(config_usefulness),
```

- [ ] **Step 4: Run tests**

Run:

```powershell
python -m pytest -q tests/test_operator_summary.py
```

Expected: all tests pass.

- [ ] **Step 5: Commit Task 4**

```powershell
git add src/hsconfig/operator_summary.py tests/test_operator_summary.py
git commit -m "feat: summarize mulligan policy default-only status"
```

---

### Task 5: Add Representative Deck E2E Guardrails

**Files:**
- Modify: `tests/test_shadowpriest_e2e.py`
- Modify: `tests/test_universal_wild_no_block_matrix.py`

**Interfaces:**
- Consumes:
  - Existing configure/build fixture helpers.
  - Existing representative deck fixture rows.
- Produces:
  - Regression proof that policy-backed fallback improves output without false source-strong promotion.

- [ ] **Step 1: Add ShadowPriest boundary assertions**

In the existing ShadowPriest E2E test that reads the generated package/reports, add assertions equivalent to:

```python
    mulligan = operator_summary["config_usefulness"]["surfaces"]["mulligan"]
    assert mulligan["default_only"] is False
    assert operator_summary["default_only_runtime_surfaces"] == []
    assert operator_summary["mulligan_policy_status"]["default_only"] is False

    mulligan_rows = json.loads((runtime_dir / "Mulligan.json").read_text(encoding="utf-8"))["Mulligan"]["values"]
    assert all("SW_448" not in str(row.get("mulligan", "")) for row in mulligan_rows)

    card_files = {path.name for path in runtime_dir.glob("*.json")}
    assert "SW_448.json" in card_files
```

Use the actual local variable names for `operator_summary` and `runtime_dir` from the existing test.

- [ ] **Step 2: Add no-block matrix policy assertions**

In the universal Wild no-block matrix test loop, after loading `operator`, add:

```python
        assert operator["technical_status"] == "VALID_PACKAGE"
        assert operator["runtime_apply_mode"] == "load_safe_apply"
        assert operator.get("default_only_runtime_surfaces", []) == []
        mulligan_policy = operator.get("mulligan_policy_status", {})
        assert mulligan_policy.get("default_only") is False
```

For fixture rows that intentionally model thin/no-candidate Mulligan behavior, add an explicit allowlist named:

```python
ALLOWED_DEFAULT_ONLY_FIXTURES = set()
```

Keep it empty unless an existing fixture proves there is no safe policy candidate.

- [ ] **Step 3: Run targeted e2e tests**

Run:

```powershell
python -m pytest -q tests/test_shadowpriest_e2e.py tests/test_universal_wild_no_block_matrix.py
```

Expected: pass. If an existing fixture fails because it has genuinely no safe Mulligan candidate, keep the assertion strict and fix the fixture or policy; do not silently allow default-only unless the generated report proves `policy_result.status == no_safe_candidate`.

- [ ] **Step 4: Commit Task 5**

```powershell
git add tests/test_shadowpriest_e2e.py tests/test_universal_wild_no_block_matrix.py
git commit -m "test: guard representative decks against default-only mulligan"
```

---

### Task 6: Update Operator Docs And Installed Skill

**Files:**
- Modify: `README.md`
- Modify: `docs/operator/README.md`
- Modify: `docs/operator/universal-wild-no-block-contract.md`
- Modify: `.agents/skills/hsconfig/SKILL.md`
- Test: `tests/test_skill_files.py`
- Test: `tests/test_docs_active_path.py`
- Test: `tests/test_operator_docs_contract_policy.py`

**Interfaces:**
- Consumes:
  - New report fields from earlier tasks.
- Produces:
  - Operator docs describe source-backed vs policy-backed Mulligan precisely.
  - Installed skill sync stays clean.

- [ ] **Step 1: Update docs wording**

Use this exact wording in the operator-facing docs where Mulligan policy is described:

```markdown
If no source-backed Mulligan keep can be emitted, HSConfig may emit a
`policy_backed_autonomous_mulligan` keep set. This is an autonomous fallback,
not source proof. It is allowed to prevent default-only Mulligan output, but it
must not promote the deck to `SOURCE_BACKED_STRONG`, must not override explicit
or suppressed Mulligan source intent, and must not keep non-hand start-of-game
enablers such as Darkbishop Benedictus without explicit opening-hand source
text.
```

Also document the new operator fields:

```markdown
Open `reports/operator_summary.json` first. `mulligan_policy_status` tells
whether Mulligan used source-backed or policy-backed keeps. `default_only_runtime_surfaces`
must normally be empty for a valid generated package; if it is not empty, open
the named surface report first.
```

- [ ] **Step 2: Sync installed skill**

Run:

```powershell
python scripts\sync_installed_skill.py
```

Expected: copies `.agents/skills/hsconfig/SKILL.md` to `C:\Users\darbo\.codex\skills\hsconfig\SKILL.md`.

- [ ] **Step 3: Run docs and skill tests**

Run:

```powershell
python -m pytest -q tests/test_skill_files.py tests/test_docs_active_path.py tests/test_operator_docs_contract_policy.py tests/test_skill_sync.py
```

Expected: pass.

- [ ] **Step 4: Commit Task 6**

```powershell
git add README.md docs/operator/README.md docs/operator/universal-wild-no-block-contract.md .agents/skills/hsconfig/SKILL.md tests/test_skill_files.py tests/test_docs_active_path.py tests/test_operator_docs_contract_policy.py
git commit -m "docs: document archetype-aware mulligan policy fallback"
```

Do not stage `C:\Users\darbo\.codex\skills\hsconfig\SKILL.md`, because it is an installed copy outside the repository. Verify sync with `python scripts\sync_installed_skill.py --check` instead.

---

### Task 7: Final Verification And GitHub Sync

**Files:**
- No code files unless earlier tasks uncovered a targeted fix.

**Interfaces:**
- Consumes:
  - All previous task commits.
- Produces:
  - Clean local repo.
  - Pushed `main`.

- [ ] **Step 1: Run focused policy verification**

Run:

```powershell
python -m pytest -q tests/test_autonomous_mulligan_policy.py tests/test_mulligan_plan.py tests/test_config_usefulness.py tests/test_source_claim_gap_report.py tests/test_strong_promotion_report.py tests/test_shadowpriest_e2e.py tests/test_universal_wild_no_block_matrix.py
```

Expected: all pass.

- [ ] **Step 2: Run contract guardrails**

Run:

```powershell
python scripts\check_contract_guardrails.py
```

Expected:

```text
OK: installed skill sync
OK: contract spine sentinel
OK: focused contract boundary tests
```

- [ ] **Step 3: Run installed skill sync check**

Run:

```powershell
python scripts\sync_installed_skill.py --check
```

Expected:

```text
HSConfig skill is in sync: C:\Users\darbo\.codex\skills\hsconfig
```

- [ ] **Step 4: Run full test suite**

Run:

```powershell
python -m pytest -q
```

Expected: full suite passes. Current baseline before this plan was `1155 passed, 2 skipped`, but accept the updated total if all tests pass.

- [ ] **Step 5: Check diff hygiene**

Run:

```powershell
git diff --check
git status --short --branch
```

Expected: no whitespace errors except known CRLF warnings, and no unstaged changes.

- [ ] **Step 6: Push main**

Run:

```powershell
git push origin main
```

Expected: current `main` pushed to `origin/main`.

---

## Self-Review

**Spec coverage:**  
This plan implements the recommended Option A only: archetype-aware autonomous Mulligan fallback. It does not implement new runtime surfaces, post-game tuning, replay analysis, winrate handling, Presume/Concede support, or broad docs cleanup.

**Placeholder scan:**  
No task uses `TBD`, `TODO`, or unspecified “add tests” language. Every task names files, behavior, commands, expected outcomes, and concrete assertions or code.

**Type consistency:**  
The new fields are consistently named:
- `policy_lane`
- `policy_reason`
- `policy_lanes`
- `policy_reasons`
- `mulligan_policy_status`
- `default_only_runtime_surfaces`

**Boundary check:**  
The plan preserves the existing HSConfig architecture: technical load safety remains the only apply gate, `SOURCE_BACKED_STRONG` remains a source-confidence label, and policy-backed Mulligan remains a non-source-backed fallback.

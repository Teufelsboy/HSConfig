# Policy-Backed Autonomous Mulligan Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ensure normal HSConfig deck generation does not emit default-only Mulligan output while preserving strict source/contract false-lowering boundaries.

**Architecture:** Keep `claim_kind` and surface gates as the source-backed runtime authority. Add a deliberately named `policy_backed_autonomous_mulligan` lane that only fills Mulligan when source-backed keeps are absent, is visible in reports, and never pretends to be source-backed. Keep `operator_summary.json` as the only normal apply authority.

**Tech Stack:** Python package under `src/hsconfig`, pytest, JSON runtime reports, existing HearthRanger VisionAI JSON package compiler.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig`.
- Do not add Presume or Concede to the normal package path.
- Do not make `source_contract_audit.json`, `source_claim_gap_report.json`, `config_usefulness`, or strong promotion reports into apply gates.
- Do not change `claim_kind` surface gates so that `hero_power_transform`, `card_role`, start-of-game, or deckbuilding effects become source-backed Mulligan claims.
- Preserve the Darkbishop Benedictus boundary: `SW_448` may emit CardID/Hero Power behavior, but must not be held in `Mulligan.json` unless a source explicitly says opening-hand keep.
- Runtime apply remains allowed for valid load-safe packages; config richness warnings are diagnostic.
- Normal generated packages should avoid `Mulligan.json` default-only by using source-backed keeps first and policy-backed autonomous keeps second.
- No new dependency is required.

---

## File Structure

- Create `src/hsconfig/autonomous_mulligan_policy.py`: focused deterministic policy generator for policy-backed Mulligan keep rows.
- Modify `src/hsconfig/mulligan_plan.py`: integrate policy rows after source-backed claims are evaluated and only when no source-backed concrete keep exists.
- Modify `src/hsconfig/package_builder.py`: enable the autonomous policy for normal package generation and preserve policy rows in plan-report filtering.
- Modify `src/hsconfig/source_claim_gap_report.py`: add deck-level Mulligan surface visibility so default-only cannot look closed.
- Modify `src/hsconfig/config_usefulness.py`: report policy-backed Mulligan as non-default, non-blocking, and distinct from source-backed richness.
- Modify `tests/test_mulligan_plan.py`: unit coverage for policy integration and false-lowering suppression.
- Create `tests/test_autonomous_mulligan_policy.py`: unit coverage for policy row selection and exclusions.
- Modify `tests/test_source_claim_gap_report.py`: deck-level Mulligan surface gap and closure tests.
- Modify `tests/test_shadowpriest_e2e.py`: ensure generated ShadowPriest package has non-default Mulligan while excluding `SW_448`.
- Modify docs:
  - `README.md`
  - `.agents/skills/hsconfig/SKILL.md`
  - `docs/operator/guide-research-policy.md`
  - `docs/operator/universal-wild-no-block-contract.md`

---

### Task 1: Autonomous Mulligan Policy Module

**Files:**
- Create: `src/hsconfig/autonomous_mulligan_policy.py`
- Create: `tests/test_autonomous_mulligan_policy.py`

**Interfaces:**
- Produces:
  - `build_policy_backed_mulligan_rules(deck_name: str, deck_cards: Mapping[str, Any] | list[dict[str, Any]], card_roles: Mapping[str, Any]) -> dict[str, Any]`
  - Return object keys: `status`, `rules`, `suppressed`, `candidate_count`, `selected_count`, `excluded_count`.
- Consumes:
  - `hsconfig.role_tokens.START_OF_GAME_NON_HAND_EFFECT_ROLES`
  - card rows from `gameplan_contract["cards"]`
  - `runtime_research_bundle["card_role_map"]`

- [ ] **Step 1: Write failing tests for policy selection and exclusions**

Add `tests/test_autonomous_mulligan_policy.py`:

```python
from hsconfig.autonomous_mulligan_policy import build_policy_backed_mulligan_rules


def test_policy_selects_early_playable_pressure_cards():
    result = build_policy_backed_mulligan_rules(
        deck_name="CurveDeck",
        deck_cards={
            "CARD_1": {"name": "One Drop", "cost": 1},
            "CARD_5": {"name": "Five Drop", "cost": 5},
        },
        card_roles={
            "CARD_1": {"roles": ["early_pressure", "one_drop"]},
            "CARD_5": {"roles": ["late_payoff"]},
        },
    )

    assert result["status"] == "applied"
    assert result["rules"] == [
        {
            "card": "CARD_1",
            "selector_kind": "card",
            "selector": "CARD_1",
            "action": "hold",
            "condition": "*",
            "reason": "policy_backed_autonomous_mulligan:early_pressure",
            "confidence": "policy_backed",
            "source_type": "policy_backed_autonomous_mulligan",
            "source_claim_ids": [],
        }
    ]
    assert result["candidate_count"] == 1
    assert result["selected_count"] == 1


def test_policy_excludes_start_of_game_hero_power_transform_cards():
    result = build_policy_backed_mulligan_rules(
        deck_name="ShadowPriest",
        deck_cards={
            "SW_448": {"name": "Darkbishop Benedictus", "cost": 5},
            "SW_446": {"name": "Voidtouched Attendant", "cost": 1},
        },
        card_roles={
            "SW_448": {
                "roles": ["start_of_game", "hero_power_transform", "hero_power_pressure"],
                "semantic_families": ["start_of_game", "hero_power_transform"],
            },
            "SW_446": {"roles": ["early_pressure", "one_drop"]},
        },
    )

    assert [row["card"] for row in result["rules"]] == ["SW_446"]
    assert result["suppressed"] == [
        {
            "card": "SW_448",
            "reason": "excluded_non_hand_start_of_game_effect",
            "source_type": "policy_backed_autonomous_mulligan",
        }
    ]


def test_policy_uses_last_resort_curve_anchor_when_roles_are_unknown():
    result = build_policy_backed_mulligan_rules(
        deck_name="UnknownDeck",
        deck_cards={
            "CARD_2": {"name": "Two Drop", "cost": 2},
            "CARD_7": {"name": "Seven Drop", "cost": 7},
        },
        card_roles={},
    )

    assert result["status"] == "applied"
    assert [row["card"] for row in result["rules"]] == ["CARD_2"]
    assert result["rules"][0]["reason"] == "policy_backed_autonomous_mulligan:lowest_curve_anchor"
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_autonomous_mulligan_policy.py -q
```

Expected: fail with `ModuleNotFoundError: No module named 'hsconfig.autonomous_mulligan_policy'`.

- [ ] **Step 3: Implement the policy module**

Create `src/hsconfig/autonomous_mulligan_policy.py`:

```python
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from hsconfig.role_tokens import START_OF_GAME_NON_HAND_EFFECT_ROLES


PREFERRED_KEEP_ROLES = (
    "mulligan_anchor",
    "one_drop",
    "early_pressure",
    "tempo_draw",
    "self_damage_pressure",
    "burn_reach",
    "board_flood",
    "token_board",
    "pirate_pressure",
    "mech_curve",
    "weapon_setup",
    "discard_setup",
)

EXCLUDED_POLICY_ROLES = frozenset(
    {
        "start_of_game",
        "deckbuilding_modifier",
        "deck_state_modifier",
        "passive_start_effect",
        "hero_power_transform",
        "late_payoff",
        "combo_finisher",
        "generated_only",
        "tech_slot",
        *START_OF_GAME_NON_HAND_EFFECT_ROLES,
    }
)


def build_policy_backed_mulligan_rules(
    *,
    deck_name: str,
    deck_cards: Mapping[str, Any] | list[dict[str, Any]],
    card_roles: Mapping[str, Any],
) -> dict[str, Any]:
    cards = _normalise_deck_cards(deck_cards)
    candidates: list[dict[str, Any]] = []
    suppressed: list[dict[str, Any]] = []

    for card_id, card in sorted(cards.items()):
        roles = _role_tokens(card_roles.get(card_id, {}))
        exclusion_reason = _exclusion_reason(roles)
        if exclusion_reason:
            suppressed.append(
                {
                    "card": card_id,
                    "reason": exclusion_reason,
                    "source_type": "policy_backed_autonomous_mulligan",
                }
            )
            continue
        role_reason = _preferred_role_reason(roles)
        if role_reason:
            candidates.append(_candidate(card_id, card, role_reason, role_rank=0))

    if not candidates:
        fallback = _lowest_curve_anchor(cards, suppressed)
        if fallback is not None:
            candidates.append(fallback)

    selected = sorted(candidates, key=_candidate_sort_key)[:3]
    rules = [_rule_from_candidate(candidate) for candidate in selected]
    return {
        "deck_name": deck_name,
        "status": "applied" if rules else "no_safe_candidate",
        "rules": rules,
        "suppressed": suppressed,
        "candidate_count": len(candidates),
        "selected_count": len(rules),
        "excluded_count": len(suppressed),
    }


def _normalise_deck_cards(
    deck_cards: Mapping[str, Any] | list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    if isinstance(deck_cards, Mapping):
        return {
            str(card_id): dict(row) if isinstance(row, Mapping) else {"name": str(card_id)}
            for card_id, row in deck_cards.items()
        }
    cards: dict[str, dict[str, Any]] = {}
    for row in deck_cards:
        if not isinstance(row, Mapping):
            continue
        card_id = str(row.get("card_id", row.get("id", ""))).strip()
        if card_id:
            cards[card_id] = dict(row)
    return cards


def _role_tokens(row: Any) -> set[str]:
    if not isinstance(row, Mapping):
        return set()
    values: set[str] = set()
    for key in ("roles", "semantic_families"):
        raw = row.get(key, [])
        if isinstance(raw, str):
            raw = [raw]
        if isinstance(raw, list):
            values.update(str(item).strip() for item in raw if str(item).strip())
    return values


def _exclusion_reason(roles: set[str]) -> str:
    if roles & START_OF_GAME_NON_HAND_EFFECT_ROLES or (
        "start_of_game" in roles and "mulligan_anchor" not in roles
    ):
        return "excluded_non_hand_start_of_game_effect"
    if roles & EXCLUDED_POLICY_ROLES:
        return "excluded_policy_role"
    return ""


def _preferred_role_reason(roles: set[str]) -> str:
    for role in PREFERRED_KEEP_ROLES:
        if role in roles:
            return role
    return ""


def _lowest_curve_anchor(
    cards: dict[str, dict[str, Any]],
    suppressed: list[dict[str, Any]],
) -> dict[str, Any] | None:
    suppressed_cards = {row["card"] for row in suppressed}
    candidates = [
        _candidate(card_id, card, "lowest_curve_anchor", role_rank=10)
        for card_id, card in cards.items()
        if card_id not in suppressed_cards and _safe_cost(card) <= 3
    ]
    if not candidates:
        return None
    return sorted(candidates, key=_candidate_sort_key)[0]


def _candidate(card_id: str, card: Mapping[str, Any], reason: str, role_rank: int) -> dict[str, Any]:
    return {
        "card": card_id,
        "cost": _safe_cost(card),
        "reason": reason,
        "role_rank": role_rank,
    }


def _rule_from_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    card_id = str(candidate["card"])
    return {
        "card": card_id,
        "selector_kind": "card",
        "selector": card_id,
        "action": "hold",
        "condition": "*",
        "reason": f"policy_backed_autonomous_mulligan:{candidate['reason']}",
        "confidence": "policy_backed",
        "source_type": "policy_backed_autonomous_mulligan",
        "source_claim_ids": [],
    }


def _candidate_sort_key(candidate: dict[str, Any]) -> tuple[int, int, str]:
    return (int(candidate["role_rank"]), int(candidate["cost"]), str(candidate["card"]))


def _safe_cost(card: Mapping[str, Any]) -> int:
    try:
        return int(card.get("cost", 99))
    except (TypeError, ValueError):
        return 99
```

- [ ] **Step 4: Verify policy tests pass**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_autonomous_mulligan_policy.py -q
```

Expected: `3 passed`.

- [ ] **Step 5: Commit Task 1**

```powershell
git add src/hsconfig/autonomous_mulligan_policy.py tests/test_autonomous_mulligan_policy.py
git commit -m "feat: add autonomous mulligan policy"
```

---

### Task 2: Integrate Policy Rows Into Mulligan Plan

**Files:**
- Modify: `src/hsconfig/mulligan_plan.py`
- Modify: `tests/test_mulligan_plan.py`

**Interfaces:**
- Consumes: `build_policy_backed_mulligan_rules(...)` from Task 1.
- Produces: `build_mulligan_plan(..., allow_policy_backed: bool = False, deck_cards: Mapping[str, Any] | list[dict[str, Any]] | None = None) -> dict[str, Any]`.

- [ ] **Step 1: Add failing tests for policy-backed plan behavior**

Append to `tests/test_mulligan_plan.py`:

```python
def test_mulligan_plan_can_use_policy_backed_keeps_when_source_keeps_are_absent():
    plan = build_mulligan_plan(
        deck_name="CurveDeck",
        claims=[],
        card_roles={"CARD_001": {"roles": ["one_drop", "early_pressure"]}},
        deck_cards={"CARD_001": {"name": "One Drop", "cost": 1}},
        allow_policy_backed=True,
    )

    assert plan["rules"][0]["card"] == "CARD_001"
    assert plan["rules"][0]["source_type"] == "policy_backed_autonomous_mulligan"
    assert plan["rules"][-1]["selector_kind"] == "wildcard"
    assert plan["rules"][-1]["reason"] == "discard_unlisted_cards_after_policy_backed_keeps"
    assert plan["quality"]["status"] == "policy_backed"
    assert plan["quality"]["policy_backed_keep_rule_count"] == 1
    assert plan["quality"]["default_only"] is False


def test_mulligan_plan_policy_does_not_run_when_source_backed_keep_exists():
    plan = build_mulligan_plan(
        deck_name="CurveDeck",
        claims=[
            {
                "claim_kind": "mulligan_keep",
                "claim_readiness": "guide_backed",
                "cards": ["CARD_SOURCE"],
                "claim_id": "source_keep",
            }
        ],
        card_roles={"CARD_POLICY": {"roles": ["one_drop", "early_pressure"]}},
        deck_cards={"CARD_POLICY": {"name": "Policy Card", "cost": 1}},
        allow_policy_backed=True,
    )

    assert [row["card"] for row in plan["rules"] if row["action"] == "hold"] == ["CARD_SOURCE"]
    assert plan["quality"]["status"] == "rich"
    assert plan["quality"]["policy_backed_keep_rule_count"] == 0


def test_mulligan_plan_policy_keeps_darkbishop_out_of_mulligan():
    plan = build_mulligan_plan(
        deck_name="ShadowPriest",
        claims=[],
        card_roles={
            "SW_448": {"roles": ["start_of_game", "hero_power_transform"]},
            "SW_446": {"roles": ["one_drop", "early_pressure"]},
        },
        deck_cards={
            "SW_448": {"name": "Darkbishop Benedictus", "cost": 5},
            "SW_446": {"name": "Voidtouched Attendant", "cost": 1},
        },
        allow_policy_backed=True,
    )

    assert "SW_446" in {row["card"] for row in plan["rules"]}
    assert "SW_448" not in {row["card"] for row in plan["rules"]}
    assert any(
        row["card"] == "SW_448"
        and row["reason"] == "excluded_non_hand_start_of_game_effect"
        for row in plan["suppressed_rules"]
    )
```

- [ ] **Step 2: Run tests and verify they fail on the old signature**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_mulligan_plan.py -q
```

Expected: fail with `TypeError: build_mulligan_plan() got an unexpected keyword argument 'deck_cards'`.

- [ ] **Step 3: Modify `build_mulligan_plan` signature and policy merge**

In `src/hsconfig/mulligan_plan.py`, import the policy builder:

```python
from hsconfig.autonomous_mulligan_policy import build_policy_backed_mulligan_rules
```

Change the function signature:

```python
def build_mulligan_plan(
    *,
    deck_name: str,
    claims: list[dict[str, Any]],
    card_roles: dict[str, Any],
    deck_cards: dict[str, Any] | list[dict[str, Any]] | None = None,
    allow_policy_backed: bool = False,
) -> dict[str, Any]:
```

After source rules are de-duplicated and `_apply_mulligan_precedence(rules)` has run, insert:

```python
    policy_result = {
        "status": "not_needed",
        "rules": [],
        "suppressed": [],
        "candidate_count": 0,
        "selected_count": 0,
        "excluded_count": 0,
    }
    source_backed_keep_rule_count = sum(
        1
        for row in rules
        if row.get("source_type") == "source_claim"
        and row.get("selector_kind") != "wildcard"
        and row.get("action") == "hold"
    )
    if allow_policy_backed and source_backed_keep_rule_count == 0:
        policy_result = build_policy_backed_mulligan_rules(
            deck_name=deck_name,
            deck_cards=deck_cards or {},
            card_roles=card_roles,
        )
        for row in policy_result["rules"]:
            key = mulligan_rule_key(row)
            if key in seen_rule_keys:
                continue
            seen_rule_keys.add(key)
            rules.append(row)
        for row in policy_result["suppressed"]:
            suppressed_rules.append(row)
        rules = _apply_mulligan_precedence(rules)
```

Update quality calculation so it includes:

```python
    policy_backed_keep_rule_count = sum(
        1
        for row in rules
        if row.get("source_type") == "policy_backed_autonomous_mulligan"
        and row.get("selector_kind") != "wildcard"
        and row.get("action") == "hold"
    )
    has_policy_backed_keeps = policy_backed_keep_rule_count > 0
```

Set quality fields:

```python
        "status": (
            "rich"
            if has_source_backed_keeps
            else ("policy_backed" if has_policy_backed_keeps else "thin")
        ),
        "policy_backed_rule_count": sum(
            1
            for row in rules
            if row.get("source_type") == "policy_backed_autonomous_mulligan"
            and row.get("selector_kind") != "wildcard"
        ),
        "policy_backed_keep_rule_count": policy_backed_keep_rule_count,
        "policy_result": policy_result,
        "default_only": not rules and not suppressed_rules and not has_concrete_keeps,
```

Change wildcard insertion:

```python
    if has_concrete_keeps:
        rules.append(
            {
                "card": "*",
                "selector_kind": "wildcard",
                "selector": "*",
                "action": "discard",
                "condition": "*",
                "reason": (
                    "discard_unlisted_cards_after_source_backed_keeps"
                    if has_source_backed_keeps
                    else "discard_unlisted_cards_after_policy_backed_keeps"
                ),
            }
        )
```

Only set `blocked_reason` if no concrete keeps remain:

```python
    else:
        quality["blocked_reason"] = "no_source_backed_or_policy_backed_mulligan_keeps"
```

- [ ] **Step 4: Preserve old behavior when policy is disabled**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_mulligan_plan.py::test_mulligan_plan_does_not_create_holds_from_early_roles_without_source_claims -q
```

Expected: `1 passed`.

- [ ] **Step 5: Run full mulligan plan tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_mulligan_plan.py tests/test_autonomous_mulligan_policy.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit Task 2**

```powershell
git add src/hsconfig/mulligan_plan.py tests/test_mulligan_plan.py
git commit -m "feat: integrate policy backed mulligan plans"
```

---

### Task 3: Enable Policy in Normal Package Generation

**Files:**
- Modify: `src/hsconfig/package_builder.py`
- Modify: `tests/test_shadowpriest_e2e.py`

**Interfaces:**
- Consumes: new `build_mulligan_plan(... allow_policy_backed=True, deck_cards=...)`.
- Produces: normal `prepare`/`configure` packages with non-default Mulligan when source-backed keeps are absent.

- [ ] **Step 1: Add failing ShadowPriest E2E assertions**

In `tests/test_shadowpriest_e2e.py`, inside `test_shadowpriest_deckinput_only_build_validate_and_apply`, after `mulligan_values = mulligan["Mulligan"]["values"]`, add:

```python
    policy_hold_rows = [
        row for row in mulligan_values
        if row.get("value") == "hold" or row.get("action") == "hold"
    ]
    policy_hold_text = json.dumps(policy_hold_rows, sort_keys=True)
    config_usefulness = operator_summary["config_usefulness"]

    assert policy_hold_rows
    assert "SW_448" not in policy_hold_text
    assert config_usefulness["surfaces"]["mulligan"]["default_only"] is False
    assert config_usefulness["surfaces"]["mulligan"]["policy_backed_rule_count"] >= 1
```

- [ ] **Step 2: Run the E2E test and verify it fails**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_shadowpriest_e2e.py::test_shadowpriest_deckinput_only_build_validate_and_apply -q
```

Expected: fail because `policy_hold_rows` is empty or `policy_backed_rule_count` is missing.

- [ ] **Step 3: Pass deck cards and enable policy in `package_builder.py`**

In the `build_mulligan_plan(...)` call in `src/hsconfig/package_builder.py`, change to:

```python
    mulligan_plan = build_mulligan_plan(
        deck_name=args.deck_name,
        claims=mulligan_claims,
        card_roles=card_roles,
        deck_cards=gameplan_contract.get("cards", {}),
        allow_policy_backed=True,
    )
```

In `_filter_mulligan_plan`, preserve policy rows when `--plan-reports-dir` is used:

```python
    policy_rows = [
        row
        for row in plan.get("rules", [])
        if isinstance(row, dict)
        and row.get("source_type") == "policy_backed_autonomous_mulligan"
    ]
    filtered_rules = [
        *filtered_rules,
        *policy_rows,
    ]
```

Keep wildcard handling after this merge so the wildcard discard is retained when either source or policy concrete holds exist.

- [ ] **Step 4: Run focused E2E test**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_shadowpriest_e2e.py::test_shadowpriest_deckinput_only_build_validate_and_apply -q
```

Expected: `1 passed`.

- [ ] **Step 5: Run apply gate regression**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_apply_gate.py tests/test_shadowpriest_e2e.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit Task 3**

```powershell
git add src/hsconfig/package_builder.py tests/test_shadowpriest_e2e.py
git commit -m "feat: enable autonomous mulligan generation"
```

---

### Task 4: Report Deck-Level Mulligan Surface Closure

**Files:**
- Modify: `src/hsconfig/source_claim_gap_report.py`
- Modify: `tests/test_source_claim_gap_report.py`

**Interfaces:**
- Produces: `source_claim_gap_report["deck_surfaces"]["mulligan"]`.
- Consumers: operator review, future skill guidance, tests, `strong_promotion_report` if it reads the summary.

- [ ] **Step 1: Add failing tests for deck-level surface gap and policy closure**

Append to `tests/test_source_claim_gap_report.py`:

```python
def test_gap_report_includes_deck_level_mulligan_gap_when_default_only():
    report = build_source_claim_gap_report(
        deck_name="DefaultOnly",
        config_readiness_report={"cards": {}},
        claim_coverage_report={"cards": {}},
        mulligan_plan={
            "rules": [],
            "quality": {
                "status": "thin",
                "has_concrete_keeps": False,
                "source_backed_keep_rule_count": 0,
                "policy_backed_keep_rule_count": 0,
                "default_only": True,
            },
        },
        card_behavior_plan={"rows": []},
        combo_plan={"combos": []},
    )

    mulligan = report["deck_surfaces"]["mulligan"]
    assert mulligan["first_missing_link"] == "needs_mulligan_claim"
    assert mulligan["source_depth_lane"] == "mulligan_claim_gap"
    assert mulligan["recommended_next_claim_kinds"] == ["mulligan_keep", "mulligan_discard"]
    assert report["summary"]["deck_surface_gap_count"] == 1
    assert report["summary"]["first_missing_chain"]["surface"] == "mulligan"


def test_gap_report_marks_policy_backed_mulligan_as_closed_not_source_backed():
    report = build_source_claim_gap_report(
        deck_name="PolicyClosed",
        config_readiness_report={"cards": {}},
        claim_coverage_report={"cards": {}},
        mulligan_plan={
            "rules": [
                {
                    "card": "CARD_1",
                    "action": "hold",
                    "selector_kind": "card",
                    "source_type": "policy_backed_autonomous_mulligan",
                }
            ],
            "quality": {
                "status": "policy_backed",
                "has_concrete_keeps": True,
                "source_backed_keep_rule_count": 0,
                "policy_backed_keep_rule_count": 1,
                "default_only": False,
            },
        },
        card_behavior_plan={"rows": []},
        combo_plan={"combos": []},
    )

    mulligan = report["deck_surfaces"]["mulligan"]
    assert mulligan["first_missing_link"] == "none"
    assert mulligan["source_depth_lane"] == "policy_backed_autonomous_mulligan"
    assert mulligan["source_quality_lane"] == "policy_backed"
    assert report["summary"]["deck_surface_gap_count"] == 0
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_source_claim_gap_report.py -q
```

Expected: fail because `deck_surfaces` is missing.

- [ ] **Step 3: Add deck-level surface rows**

In `src/hsconfig/source_claim_gap_report.py`, add helper:

```python
def _mulligan_surface_row(mulligan_plan: dict[str, Any]) -> dict[str, Any]:
    quality = mulligan_plan.get("quality", {})
    if not isinstance(quality, dict):
        quality = {}
    rules = mulligan_plan.get("rules", [])
    if not isinstance(rules, list):
        rules = []
    policy_count = int(quality.get("policy_backed_keep_rule_count", 0) or 0)
    source_count = int(quality.get("source_backed_keep_rule_count", 0) or 0)
    has_keeps = bool(quality.get("has_concrete_keeps")) or any(
        isinstance(row, dict)
        and row.get("action") == "hold"
        and row.get("selector_kind") != "wildcard"
        for row in rules
    )
    if source_count:
        return {
            "surface": "mulligan",
            "first_missing_link": "none",
            "source_depth_lane": "source_backed_mulligan",
            "source_quality_lane": "guide_backed",
            "recommended_next_claim_kinds": [],
            "next_action": "mulligan_surface_closed",
        }
    if policy_count or has_keeps:
        return {
            "surface": "mulligan",
            "first_missing_link": "none",
            "source_depth_lane": "policy_backed_autonomous_mulligan",
            "source_quality_lane": "policy_backed",
            "recommended_next_claim_kinds": [],
            "next_action": "mulligan_surface_closed_by_policy",
        }
    return {
        "surface": "mulligan",
        "first_missing_link": "needs_mulligan_claim",
        "source_depth_lane": "mulligan_claim_gap",
        "source_quality_lane": "contract_gap",
        "recommended_next_claim_kinds": ["mulligan_keep", "mulligan_discard"],
        "next_action": "build_source_or_policy_backed_mulligan",
    }
```

In `build_source_claim_gap_report`, before return:

```python
    deck_surfaces = {"mulligan": _mulligan_surface_row(mulligan_plan)}
    deck_surface_gap_count = sum(
        1 for row in deck_surfaces.values() if row["first_missing_link"] != "none"
    )
    card_first_missing_chain = _first_missing_chain(rows)
    first_missing_chain = (
        {
            **deck_surfaces["mulligan"],
            "priority_score": 95,
            "priority_reason": "deck_surface:mulligan",
        }
        if deck_surfaces["mulligan"]["first_missing_link"] != "none"
        else card_first_missing_chain
    )
```

Return `deck_surfaces` and add `deck_surface_gap_count` to summary. Preserve `cards` and `card_rows` unchanged.

- [ ] **Step 4: Run gap report tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_source_claim_gap_report.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit Task 4**

```powershell
git add src/hsconfig/source_claim_gap_report.py tests/test_source_claim_gap_report.py
git commit -m "feat: report deck level mulligan closure"
```

---

### Task 5: Config Usefulness Policy Status

**Files:**
- Modify: `src/hsconfig/config_usefulness.py`
- Create or modify: `tests/test_config_usefulness.py`

**Interfaces:**
- Consumes: `mulligan_plan_report["quality"]["policy_backed_keep_rule_count"]`.
- Produces: `config_usefulness["surfaces"]["mulligan"]["status"]` in `rich`, `policy_backed`, `thin`, or `report_only`.

- [ ] **Step 1: Add focused tests**

If `tests/test_config_usefulness.py` does not exist, create it. Add:

```python
from hsconfig.config_usefulness import build_config_usefulness


def test_policy_backed_mulligan_is_not_default_only_or_blocking():
    result = build_config_usefulness(
        technical_status="VALID_PACKAGE",
        semantic_status="STATIC_SEMANTICS_USABLE",
        config_readiness_summary={},
        mulligan_plan_report={
            "rules": [
                {
                    "card": "CARD_1",
                    "action": "hold",
                    "selector_kind": "card",
                    "source_type": "policy_backed_autonomous_mulligan",
                }
            ],
            "quality": {
                "status": "policy_backed",
                "has_concrete_keeps": True,
                "source_backed_rule_count": 0,
                "source_backed_keep_rule_count": 0,
                "policy_backed_rule_count": 1,
                "policy_backed_keep_rule_count": 1,
                "first_gap_reason": "policy_backed_autonomous_mulligan",
            },
        },
        card_behavior_plan_report={"rows": []},
        combo_plan_report={"combos": []},
        globalvalues_profile_report={"changed_keys": [], "unchanged_keys": []},
    )

    mulligan = result["surfaces"]["mulligan"]
    assert mulligan["status"] == "policy_backed"
    assert mulligan["default_only"] is False
    assert mulligan["next_source_need"] == "none"
    assert mulligan["policy_backed_rule_count"] == 1
    assert result["blocking"] is False
```

- [ ] **Step 2: Run and verify failure**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_config_usefulness.py -q
```

Expected: fail because policy fields/status are not exposed.

- [ ] **Step 3: Update `_mulligan_surface`**

In `src/hsconfig/config_usefulness.py`, change accepted quality status:

```python
    if quality_status in {"rich", "policy_backed", "thin"}:
        status = quality_status
```

Add counts:

```python
    policy_backed_rule_count = (
        _int(quality.get("policy_backed_rule_count", 0))
        if isinstance(quality, dict)
        else 0
    )
    policy_backed_keep_rule_count = (
        _int(quality.get("policy_backed_keep_rule_count", 0))
        if isinstance(quality, dict)
        else 0
    )
```

Set `next_source_need`:

```python
        "next_source_need": (
            "none"
            if status in {"rich", "policy_backed"}
            else "source_backed_or_policy_backed_mulligan_keeps"
        ),
        "policy_backed_rule_count": policy_backed_rule_count,
        "policy_backed_keep_rule_count": policy_backed_keep_rule_count,
```

In `_first_gap`, ensure policy-backed is not treated as a Mulligan gap:

```python
    if _int(summary.get("cards_needing_mulligan_claims")) or mulligan["status"] in {"thin", "report_only"}:
        return "mulligan_gap"
```

- [ ] **Step 4: Run tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_config_usefulness.py tests/test_shadowpriest_e2e.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit Task 5**

```powershell
git add src/hsconfig/config_usefulness.py tests/test_config_usefulness.py tests/test_shadowpriest_e2e.py
git commit -m "feat: expose policy backed mulligan usefulness"
```

---

### Task 6: Docs and Skill Contract Update

**Files:**
- Modify: `README.md`
- Modify: `.agents/skills/hsconfig/SKILL.md`
- Modify: `docs/operator/guide-research-policy.md`
- Modify: `docs/operator/universal-wild-no-block-contract.md`

**Interfaces:**
- Produces operator-facing language that distinguishes source-backed claims from policy-backed autonomous runtime rows.

- [ ] **Step 1: Update README boundary paragraph**

In `README.md`, keep the existing claim-kind boundary and add this paragraph near the Mulligan/runtime explanation:

```markdown
When no explicit Mulligan source claim exists, HSConfig may emit a small
`policy_backed_autonomous_mulligan` keep set so normal packages are not
default-only. These rows are not source-backed claims. They are visible as
policy-backed runtime rows and still obey false-lowering exclusions for
start-of-game, deckbuilding, and hero-power-transform effect cards.
```

- [ ] **Step 2: Update skill instructions**

In `.agents/skills/hsconfig/SKILL.md`, add:

```markdown
- Normal deck generation should not leave `Mulligan.json` default-only when
  a safe autonomous keep policy can be produced. Prefer explicit
  `mulligan_keep` / `mulligan_discard` source claims. If none exist, use the
  `policy_backed_autonomous_mulligan` lane; never label those rows as
  source-backed and never use it to keep start-of-game or hero-power-transform
  effect-only cards such as Darkbishop Benedictus.
```

- [ ] **Step 3: Update operator docs**

In `docs/operator/guide-research-policy.md`, add a section:

```markdown
## Policy-Backed Mulligan Fallback

Source-backed Mulligan remains preferred. If no explicit Mulligan claims are
available, HSConfig can produce a small policy-backed keep set from card roles,
curve, and deck archetype signals. The fallback is intentionally labelled
`policy_backed_autonomous_mulligan`; it is runtime-lowerable for Mulligan but
does not count as source-backed guide evidence.

Policy rows must exclude start-of-game-only, deckbuilding-only, generated-only,
late-payoff, combo-finisher, and hero-power-transform effect cards unless a
separate explicit opening-hand claim exists.
```

In `docs/operator/universal-wild-no-block-contract.md`, add:

```markdown
Policy-backed Mulligan rows are compatible with the no-block contract. They
improve package usefulness without becoming a second apply gate or changing
the source-backed claim model.
```

- [ ] **Step 4: Scan docs for contradictory default-only language**

Run:

```powershell
rg -n "default-only|default_only|no_source_backed_mulligan|source_backed_mulligan_keeps|Darkbishop|policy_backed_autonomous_mulligan" README.md .agents\skills\hsconfig\SKILL.md docs\operator
```

Expected: no statement says default-only is the desired normal end state.

- [ ] **Step 5: Commit Task 6**

```powershell
git add README.md .agents/skills/hsconfig/SKILL.md docs/operator/guide-research-policy.md docs/operator/universal-wild-no-block-contract.md
git commit -m "docs: explain policy backed mulligan fallback"
```

---

### Task 7: Full Verification and Fresh ShadowPriest Package Check

**Files:**
- No code files created.
- Generated local package under `outputs/ShadowPriest` may be refreshed during verification.

**Interfaces:**
- Verifies normal CLI path:
  - `prepare`
  - `validate`
  - optional `apply --dry` if such mode exists; otherwise do not fake unimplemented commands.

- [ ] **Step 1: Run targeted tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_autonomous_mulligan_policy.py tests/test_mulligan_plan.py tests/test_source_claim_gap_report.py tests/test_config_usefulness.py tests/test_shadowpriest_e2e.py -q
```

Expected: all tests pass.

- [ ] **Step 2: Run source-contract guardrail tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_claim_kind_runtime_contract.py tests/test_surface_authority_split.py tests/test_source_contract_audit.py tests/test_source_to_runtime_explainability.py -q
```

Expected: all tests pass, especially Darkbishop/hero-power-transform boundaries.

- [ ] **Step 3: Run wider suite**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest -q
```

Expected: full suite passes.

- [ ] **Step 4: Rebuild ShadowPriest through normal CLI**

Run:

```powershell
Remove-Item -Recurse -Force outputs\ShadowPriest -ErrorAction SilentlyContinue
hsconfig prepare --deck-name "ShadowPriest" --deck-code "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=" --runtime-root "C:\Users\darbo\Desktop\HS" --out "outputs\ShadowPriest" --json
hsconfig validate --package "outputs\ShadowPriest" --json
```

Expected:
- prepare exits `0`
- validate exits `0`
- `outputs\ShadowPriest\CustomConfig\shadowpriest\Mulligan.json` contains at least one hold row
- no hold row contains `SW_448`
- `outputs\ShadowPriest\reports\operator_summary.json` has `technical_status=VALID_PACKAGE`
- `config_usefulness.surfaces.mulligan.default_only=false`

- [ ] **Step 5: Inspect generated reports**

Run:

```powershell
python -c "import json; from pathlib import Path; base=Path('outputs/ShadowPriest'); op=json.loads((base/'reports/operator_summary.json').read_text(encoding='utf-8')); gap=json.loads((base/'reports/source_claim_gap_report.json').read_text(encoding='utf-8')); mull=json.loads((base/'CustomConfig/shadowpriest/Mulligan.json').read_text(encoding='utf-8')); print(json.dumps({'technical_status': op['technical_status'], 'mulligan': op['config_usefulness']['surfaces']['mulligan'], 'deck_surface_mulligan': gap['deck_surfaces']['mulligan'], 'mulligan_values': mull['Mulligan']['values']}, indent=2))"
```

Expected:
- `mulligan.status` is `policy_backed` or `rich`
- `deck_surface_mulligan.first_missing_link` is `none`
- `mulligan_values` is not empty
- `SW_448` is absent from `mulligan_values`

- [ ] **Step 6: Check git status**

Run:

```powershell
git status --short --branch
```

Expected: clean after commits, branch still tracks `origin/main`.

- [ ] **Step 7: Leave verification outputs uncommitted unless they are intentional source changes**

Run:

```powershell
git status --short
```

Expected: no generated package, runtime backup, raw runtime log, HearthRanger log, HDT file, Power.log, `.hsreplay`, `.hdtreplay`, or private runtime evidence is staged. If `outputs\ShadowPriest` appears as untracked verification output, leave it untracked or remove it before final handoff.

---

## Self-Review

- Spec coverage: The plan covers no-default-only, Darkbishop false-lowering, source-backed versus policy-backed truth, deck-level gap visibility, operator usefulness, docs, tests, and verification.
- Placeholder scan: The plan contains no unfinished placeholder markers and no undefined handoff step. The implementation tasks list exact files and functions.
- Type consistency: `build_policy_backed_mulligan_rules(...)` returns policy rows consumed by `build_mulligan_plan(...)`. `build_mulligan_plan(...)` exposes `policy_backed_keep_rule_count`, which is consumed by `config_usefulness` and `source_claim_gap_report`.
- Risk check: The plan does not change the source-backed gate for `mulligan_keep`. Policy-backed rows are runtime rows, not source claims, and are labelled accordingly.

# HSConfig Surface Authority Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Separate "what a source claim means" from "which HearthRanger runtime surface may be written" so HSConfig stays autonomous and no-block, while preventing effects like Darkbishop Benedictus from becoming false Mulligan keeps.

**Architecture:** Keep the existing HSConfig pipeline and add a small source-contract authority layer in `source_document_model.py`. Existing compilers and routers should call surface-specific gates for `Mulligan.json`, `GlobalValues.json`, `Combo.json`, and per-card `<CARDID>.json`; every non-emitted claim remains visible through suppression/report rows.

**Tech Stack:** Python 3, existing `hsconfig` package, `pytest`, current HearthRanger VisionAI JSON surfaces only.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig` for `Teufelsboy/HSConfig`.
- Keep HSConfig separate from HSTuner.
- Do not add replay parsing, HDT parsing, winrate validation, candidate promotion, or post-run tuning.
- Generated runtime packages belong under `outputs/` and are ignored by git.
- Preserve exact deck and CardID identity.
- Preserve full `GlobalValues.json` key profiling.
- Preserve every-card coverage in the gameplan contract.
- Preserve strict JSON validation.
- Preserve row-level provenance for generated config rows.
- Do not block valid decks because evidence is weak; degrade to baseline, report-only, or suppressed rows with explicit reasons.
- Do not treat card importance, start-of-game effects, or generic guide text as `Mulligan.json` rules unless the claim is explicitly `mulligan_keep` or `mulligan_discard` and passes the Mulligan surface gate.

---

## File Structure

- Modify: `src/hsconfig/source_document_model.py`
  - Owns claim normalization, runtime-readiness gating, and surface-specific authority decisions.
  - Adds a small `SurfaceGateDecision` dataclass and four dedicated gates.
  - Keeps `runtime_claim_kind()` as a backwards-compatible wrapper.

- Modify: `src/hsconfig/mulligan_plan.py`
  - Replaces local runtime-kind/readiness checks with `can_lower_to_mulligan()`.
  - Keeps selector and condition validation local because they are Mulligan compiler details.

- Modify: `src/hsconfig/globalvalues_authority.py`
  - Filters posture claims through `can_lower_to_globalvalues()`.
  - Keeps existing curated `POSTURE_OVERLAYS` and runtime-evidence key blocking.

- Modify: `src/hsconfig/combo_plan.py`
  - Filters combo claims through `can_lower_to_combo()`.
  - Keeps existing exact sequence validation in `combo_sequence_contract.py`.

- Modify: `src/hsconfig/card_behavior_surface_router.py`
  - Filters CardID behavior rows through `can_lower_to_cardid()`.
  - Keeps option identity, mechanic policy, explicit runtime block validation, and documented behavior block routing local.

- Modify: `docs/operator/README.md`, `README.md`, `.agents/skills/hsconfig/SKILL.md`
  - Clarify source claim vs runtime surface authority in the active operator path and installed skill source.

- Test: `tests/test_surface_authority_split.py`
  - New contract tests for normalized claim kinds and surface gates.

- Modify: `tests/test_claim_kind_runtime_contract.py`, `tests/test_mulligan_plan.py`, `tests/test_globalvalues_authority.py`, `tests/test_combo_plan.py`, `tests/test_card_behavior_router.py`
  - Add targeted regression coverage around the new gate calls.

---

### Task 1: Add Surface Authority API

**Files:**
- Modify: `src/hsconfig/source_document_model.py`
- Create: `tests/test_surface_authority_split.py`

**Interfaces:**
- Consumes: existing `runtime_claim_kind(claim: Mapping[str, Any]) -> str` and `claim_can_lower_to_runtime(claim: dict) -> bool`.
- Produces:
  - `normalized_claim_kind(claim: Mapping[str, Any]) -> str`
  - `SurfaceGateDecision(allowed: bool, reason: str, claim_kind: str, surface: str)`
  - `surface_gate_decision(claim: Mapping[str, Any], surface: str, context: Mapping[str, Any] | None = None) -> SurfaceGateDecision`
  - `can_lower_to_mulligan(claim: Mapping[str, Any], *, card_roles: Mapping[str, Any] | None = None) -> SurfaceGateDecision`
  - `can_lower_to_globalvalues(claim: Mapping[str, Any]) -> SurfaceGateDecision`
  - `can_lower_to_combo(claim: Mapping[str, Any]) -> SurfaceGateDecision`
  - `can_lower_to_cardid(claim: Mapping[str, Any]) -> SurfaceGateDecision`

- [ ] **Step 1: Write failing tests for normalized claim kinds and surface gates**

Add `tests/test_surface_authority_split.py`:

```python
from hsconfig.source_document_model import (
    can_lower_to_cardid,
    can_lower_to_combo,
    can_lower_to_globalvalues,
    can_lower_to_mulligan,
    normalized_claim_kind,
    runtime_claim_kind,
)


def test_normalized_claim_kind_keeps_exact_legacy_compatibility():
    assert normalized_claim_kind({"claim_type": "combo"}) == "combo_sequence"
    assert normalized_claim_kind({"claim_type": "bad_pattern"}) == "known_bad_pattern"
    assert normalized_claim_kind({"claim_type": "mulligan_throw"}) == "mulligan_discard"
    assert normalized_claim_kind({"claim_type": "mulligan_and_gameplan"}) == ""
    assert runtime_claim_kind({"claim_type": "combo"}) == "combo_sequence"


def test_mulligan_surface_accepts_only_explicit_mulligan_claims():
    keep = {
        "claim_kind": "mulligan_keep",
        "claim_readiness": "guide_backed",
        "trust_ceiling": "runtime_candidate",
        "cards": ["CARD_001"],
    }
    effect = {
        "claim_kind": "hero_power_transform",
        "claim_readiness": "source_backed_static_semantics",
        "trust_ceiling": "runtime_candidate",
        "cards": ["SW_448"],
    }

    assert can_lower_to_mulligan(keep).allowed is True
    decision = can_lower_to_mulligan(effect)
    assert decision.allowed is False
    assert decision.reason == "claim_kind_not_mulligan_surface"


def test_start_of_game_transform_is_never_opening_hand_keep_even_when_claim_says_keep():
    claim = {
        "claim_kind": "mulligan_keep",
        "claim_readiness": "guide_backed",
        "trust_ceiling": "runtime_candidate",
        "cards": ["SW_448"],
    }
    decision = can_lower_to_mulligan(
        claim,
        card_roles={
            "SW_448": {
                "roles": ["start_of_game", "hero_power_transform"],
                "semantic_families": ["start_of_game", "hero_power_transform"],
            }
        },
    )

    assert decision.allowed is False
    assert decision.reason == "start_of_game_effect_does_not_require_opening_hand"


def test_globalvalues_surface_accepts_only_gameplan_posture_and_reports_numeric_runtime_tuning():
    posture = {
        "claim_kind": "gameplan_posture",
        "claim_readiness": "guide_backed",
        "trust_ceiling": "runtime_candidate",
        "stance": "aggro_burn",
    }
    tuning = {
        "claim_kind": "globalvalue_numeric_tuning",
        "claim_readiness": "guide_backed",
        "trust_ceiling": "runtime_candidate",
        "key": "LowHpBoardValuePenalty",
    }

    assert can_lower_to_globalvalues(posture).allowed is True
    decision = can_lower_to_globalvalues(tuning)
    assert decision.allowed is False
    assert decision.reason == "requires_runtime_evidence"


def test_combo_surface_accepts_only_combo_sequences():
    combo = {
        "claim_kind": "combo_sequence",
        "claim_readiness": "guide_backed",
        "trust_ceiling": "runtime_candidate",
        "cards": ["A", "B"],
    }
    card_role = {
        "claim_kind": "card_role",
        "claim_readiness": "guide_backed",
        "trust_ceiling": "runtime_candidate",
        "cards": ["A"],
    }

    assert can_lower_to_combo(combo).allowed is True
    decision = can_lower_to_combo(card_role)
    assert decision.allowed is False
    assert decision.reason == "claim_kind_not_combo_surface"


def test_cardid_surface_accepts_behavior_claims_but_not_mulligan_or_globalvalues():
    targeting = {
        "claim_kind": "targeting_rule",
        "claim_readiness": "guide_backed",
        "trust_ceiling": "runtime_candidate",
        "cards": ["CARD_001"],
    }
    mulligan = {
        "claim_kind": "mulligan_keep",
        "claim_readiness": "guide_backed",
        "trust_ceiling": "runtime_candidate",
        "cards": ["CARD_001"],
    }

    assert can_lower_to_cardid(targeting).allowed is True
    decision = can_lower_to_cardid(mulligan)
    assert decision.allowed is False
    assert decision.reason == "claim_kind_not_cardid_surface"
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_surface_authority_split.py -q
```

Expected: fails because `normalized_claim_kind`, `SurfaceGateDecision`, and surface gate helpers do not exist yet.

- [ ] **Step 3: Implement the minimal surface authority API**

Patch `src/hsconfig/source_document_model.py`:

```python
from dataclasses import dataclass
from typing import Any, Mapping
```

Add below the legacy alias constants:

```python
GLOBALVALUES_RUNTIME_EVIDENCE_CLAIM_KINDS = frozenset({"globalvalue_numeric_tuning"})
MULLIGAN_SURFACE_CLAIM_KINDS = frozenset({"mulligan_keep", "mulligan_discard"})
GLOBALVALUES_SURFACE_CLAIM_KINDS = frozenset({"gameplan_posture"})
COMBO_SURFACE_CLAIM_KINDS = frozenset({"combo_sequence"})
CARDID_SURFACE_CLAIM_KINDS = frozenset(
    {
        "card_role",
        "targeting_rule",
        "hero_power_transform",
        "mechanic_usage",
        "known_bad_pattern",
        "discover_choice",
        "choose_one_choice",
    }
)


@dataclass(frozen=True)
class SurfaceGateDecision:
    allowed: bool
    reason: str
    claim_kind: str
    surface: str
```

Replace the body of `runtime_claim_kind()` with a compatibility call and add `normalized_claim_kind()` above it:

```python
def normalized_claim_kind(claim: Mapping[str, Any]) -> str:
    """Return the semantic claim kind from explicit fields or exact legacy aliases."""
    explicit = str(claim.get("claim_kind", "")).strip().lower()
    if explicit:
        return explicit

    legacy = str(claim.get("claim_type", "")).strip().lower()
    if legacy in EXACT_LEGACY_RUNTIME_CLAIM_TYPE_ALIASES:
        return EXACT_LEGACY_RUNTIME_CLAIM_TYPE_ALIASES[legacy]
    if legacy in EXACT_LEGACY_RUNTIME_CLAIM_TYPES:
        return legacy

    return ""


def runtime_claim_kind(claim: Mapping[str, Any]) -> str:
    """Backward-compatible alias for normalized_claim_kind()."""
    return normalized_claim_kind(claim)
```

Add surface gates below `claim_can_lower_to_runtime()`:

```python
def surface_gate_decision(
    claim: Mapping[str, Any],
    surface: str,
    context: Mapping[str, Any] | None = None,
) -> SurfaceGateDecision:
    normalized_surface = surface.strip().lower()
    if normalized_surface == "mulligan":
        return can_lower_to_mulligan(claim, card_roles=(context or {}).get("card_roles"))
    if normalized_surface == "globalvalues":
        return can_lower_to_globalvalues(claim)
    if normalized_surface == "combo":
        return can_lower_to_combo(claim)
    if normalized_surface == "cardid":
        return can_lower_to_cardid(claim)
    return SurfaceGateDecision(False, "unknown_surface", normalized_claim_kind(claim), normalized_surface)


def can_lower_to_mulligan(
    claim: Mapping[str, Any],
    *,
    card_roles: Mapping[str, Any] | None = None,
) -> SurfaceGateDecision:
    claim_kind = normalized_claim_kind(claim)
    if claim_kind not in MULLIGAN_SURFACE_CLAIM_KINDS:
        return SurfaceGateDecision(False, "claim_kind_not_mulligan_surface", claim_kind, "mulligan")
    if not claim_can_lower_to_runtime(dict(claim)):
        return SurfaceGateDecision(False, "claim_not_runtime_lowerable", claim_kind, "mulligan")
    cards = _claim_cards_from_mapping(claim)
    if claim_kind == "mulligan_keep" and _contains_start_of_game_transform(cards, card_roles or {}):
        return SurfaceGateDecision(
            False,
            "start_of_game_effect_does_not_require_opening_hand",
            claim_kind,
            "mulligan",
        )
    return SurfaceGateDecision(True, "allowed", claim_kind, "mulligan")


def can_lower_to_globalvalues(claim: Mapping[str, Any]) -> SurfaceGateDecision:
    claim_kind = normalized_claim_kind(claim)
    if claim_kind in GLOBALVALUES_RUNTIME_EVIDENCE_CLAIM_KINDS:
        return SurfaceGateDecision(False, "requires_runtime_evidence", claim_kind, "globalvalues")
    if claim_kind not in GLOBALVALUES_SURFACE_CLAIM_KINDS:
        return SurfaceGateDecision(False, "claim_kind_not_globalvalues_surface", claim_kind, "globalvalues")
    if not claim_can_lower_to_runtime(dict(claim)):
        return SurfaceGateDecision(False, "claim_not_runtime_lowerable", claim_kind, "globalvalues")
    return SurfaceGateDecision(True, "allowed", claim_kind, "globalvalues")


def can_lower_to_combo(claim: Mapping[str, Any]) -> SurfaceGateDecision:
    claim_kind = normalized_claim_kind(claim)
    if claim_kind not in COMBO_SURFACE_CLAIM_KINDS:
        return SurfaceGateDecision(False, "claim_kind_not_combo_surface", claim_kind, "combo")
    if not claim_can_lower_to_runtime(dict(claim)):
        return SurfaceGateDecision(False, "claim_not_runtime_lowerable", claim_kind, "combo")
    return SurfaceGateDecision(True, "allowed", claim_kind, "combo")


def can_lower_to_cardid(claim: Mapping[str, Any]) -> SurfaceGateDecision:
    claim_kind = normalized_claim_kind(claim)
    if claim_kind not in CARDID_SURFACE_CLAIM_KINDS:
        return SurfaceGateDecision(False, "claim_kind_not_cardid_surface", claim_kind, "cardid")
    if not claim_can_lower_to_runtime(dict(claim)):
        return SurfaceGateDecision(False, "claim_not_runtime_lowerable", claim_kind, "cardid")
    return SurfaceGateDecision(True, "allowed", claim_kind, "cardid")


def _claim_cards_from_mapping(claim: Mapping[str, Any]) -> list[str]:
    cards = claim.get("cards", [])
    if isinstance(cards, str):
        cards = [cards]
    return [str(card) for card in cards if str(card)]


def _contains_start_of_game_transform(
    cards: list[str],
    card_roles: Mapping[str, Any],
) -> bool:
    for card_id in cards:
        role_row = card_roles.get(str(card_id), {})
        if not isinstance(role_row, Mapping):
            continue
        roles = {
            *[str(role) for role in role_row.get("roles", [])],
            *[str(role) for role in role_row.get("semantic_families", [])],
        }
        if {"start_of_game", "hero_power_transform"} <= roles:
            return True
    return False
```

- [ ] **Step 4: Run tests to verify the API passes**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_surface_authority_split.py tests/test_claim_kind_runtime_contract.py -q
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit Task 1**

```powershell
git add src/hsconfig/source_document_model.py tests/test_surface_authority_split.py tests/test_claim_kind_runtime_contract.py
git commit -m "feat: add source claim surface authority gates"
```

---

### Task 2: Route Mulligan Through The Mulligan Surface Gate

**Files:**
- Modify: `src/hsconfig/mulligan_plan.py`
- Modify: `tests/test_mulligan_plan.py`
- Modify: `tests/test_claim_kind_runtime_contract.py`

**Interfaces:**
- Consumes: `can_lower_to_mulligan(claim, card_roles=card_roles) -> SurfaceGateDecision`
- Produces: Mulligan planner whose runtime writes are authorized by the Mulligan surface gate, with unchanged `rules`, `suppressed_rules`, and `quality` output shape.

- [ ] **Step 1: Add failing test proving non-Mulligan claims stay visible when passed to Mulligan**

Append to `tests/test_mulligan_plan.py`:

```python
def test_mulligan_plan_reports_non_mulligan_claim_surface_rejection():
    plan = build_mulligan_plan(
        deck_name="ShadowPriest",
        claims=[
            {
                "claim_kind": "hero_power_transform",
                "claim_readiness": "source_backed_static_semantics",
                "trust_ceiling": "runtime_candidate",
                "cards": ["SW_448"],
                "claim_id": "darkbishop_transform",
            }
        ],
        card_roles={
            "SW_448": {
                "roles": ["start_of_game", "hero_power_transform"],
                "semantic_families": ["start_of_game", "hero_power_transform"],
            }
        },
    )

    assert plan["rules"] == []
    assert plan["suppressed_rules"][0]["reason"] == "claim_kind_not_mulligan_surface"
    assert plan["suppressed_rules"][0]["card"] == "SW_448"
```

- [ ] **Step 2: Run test to verify failure**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_mulligan_plan.py::test_mulligan_plan_reports_non_mulligan_claim_surface_rejection -q
```

Expected: fails because current Mulligan planner silently skips non-Mulligan claims instead of surfacing the first missing link.

- [ ] **Step 3: Implement Mulligan gate usage**

Patch imports in `src/hsconfig/mulligan_plan.py`:

```python
from hsconfig.source_document_model import can_lower_to_mulligan, normalized_claim_kind
```

Replace the opening of the claims loop with:

```python
    for claim in claims:
        claim_kind = normalized_claim_kind(claim)
        claim_cards = _claim_cards(claim)
        gate = can_lower_to_mulligan(claim, card_roles=card_roles)
        if not gate.allowed:
            if claim_cards:
                suppressed_rules.append(
                    {
                        "card": claim_cards[0],
                        "action": "hold" if claim_kind == "mulligan_keep" else "none",
                        "reason": gate.reason,
                        "source_claim_ids": _source_claim_ids(claim),
                    }
                )
            continue
        action = "hold" if claim_kind == "mulligan_keep" else "discard"
```

Remove the now-duplicated local block:

```python
            if action == "hold" and _is_start_of_game_transform_card(card_id, card_roles):
                ...
                continue
```

Remove `_is_start_of_game_transform_card()` if no longer used.

- [ ] **Step 4: Run Mulligan regression tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_mulligan_plan.py tests/test_claim_kind_runtime_contract.py tests/test_shadowpriest_e2e.py -q
```

Expected: all selected tests pass. ShadowPriest must still preserve the Darkbishop hero-power effect while keeping `SW_448` out of generated `Mulligan.json`.

- [ ] **Step 5: Commit Task 2**

```powershell
git add src/hsconfig/mulligan_plan.py tests/test_mulligan_plan.py tests/test_claim_kind_runtime_contract.py
git commit -m "fix: gate mulligan writes by explicit surface authority"
```

---

### Task 3: Route GlobalValues And Combo Through Dedicated Gates

**Files:**
- Modify: `src/hsconfig/globalvalues_authority.py`
- Modify: `src/hsconfig/combo_plan.py`
- Modify: `tests/test_globalvalues_authority.py`
- Modify: `tests/test_combo_plan.py`

**Interfaces:**
- Consumes:
  - `can_lower_to_globalvalues(claim) -> SurfaceGateDecision`
  - `can_lower_to_combo(claim) -> SurfaceGateDecision`
- Produces:
  - GlobalValues only considers authorized `gameplan_posture` claims and explicitly reports runtime-only numeric tuning.
  - Combo only considers authorized `combo_sequence` claims and suppresses rejected combo-like rows with clear reasons.

- [ ] **Step 1: Add GlobalValues test for ignored non-posture claim**

Append to `tests/test_globalvalues_authority.py`:

```python
def test_globalvalues_ignores_card_role_claims_even_when_source_backed():
    matrix = build_globalvalues_authority_matrix(
        aggression_profile="unknown",
        claims=[
            {
                "claim_kind": "card_role",
                "claim_readiness": "guide_backed",
                "trust_ceiling": "runtime_candidate",
                "stance": "aggro_burn",
                "cards": ["CARD_001"],
            }
        ],
    )

    assert matrix["posture"] == "baseline"
    assert matrix["allowed_step1_overlays"][0]["reason"] == "no_source_backed_posture_overlay"
```

- [ ] **Step 2: Add Combo test for non-combo suppression**

Append to `tests/test_combo_plan.py`:

```python
def test_combo_plan_reports_non_combo_claim_surface_rejection():
    plan = build_combo_plan(
        deck_cards={"A", "B"},
        claims=[
            {
                "claim_kind": "card_role",
                "claim_readiness": "guide_backed",
                "trust_ceiling": "runtime_candidate",
                "cards": ["A"],
                "claim_id": "not_combo",
            }
        ],
    )

    assert plan["combos"] == []
    assert plan["suppressed"][0]["reason"] == "claim_kind_not_combo_surface"
```

- [ ] **Step 3: Run tests to verify failure**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_globalvalues_authority.py::test_globalvalues_ignores_card_role_claims_even_when_source_backed tests/test_combo_plan.py::test_combo_plan_reports_non_combo_claim_surface_rejection -q
```

Expected: GlobalValues may already pass; Combo should fail if non-combo claims are silently skipped.

- [ ] **Step 4: Implement GlobalValues gate usage**

Patch imports in `src/hsconfig/globalvalues_authority.py`:

```python
from hsconfig.source_document_model import (
    can_lower_to_globalvalues,
    claim_can_lower_to_runtime,
    normalized_claim_kind,
)
```

Replace:

```python
    lowerable_claims = [claim for claim in claims if claim_can_lower_to_runtime(claim)]
```

with:

```python
    lowerable_claims = [
        claim for claim in claims if can_lower_to_globalvalues(claim).allowed
    ]
```

Replace `runtime_claim_kind(claim)` in `_resolve_posture()` with `normalized_claim_kind(claim)`.

Keep the `globalvalue_numeric_tuning` blocked reporting loop, but use `normalized_claim_kind(claim) == "globalvalue_numeric_tuning"`.

- [ ] **Step 5: Implement Combo gate usage**

Patch imports in `src/hsconfig/combo_plan.py`:

```python
from hsconfig.source_document_model import can_lower_to_combo, normalized_claim_kind
```

Replace the first lines of the claims loop with:

```python
    for claim in claims:
        claim_kind = normalized_claim_kind(claim)
        gate = can_lower_to_combo(claim)
        if not gate.allowed:
            if claim_kind:
                suppressed.append(
                    _suppression(
                        claim,
                        _claim_cards(claim),
                        gate.reason,
                    )
                )
            continue
```

Remove the old `if claim_kind != "combo_sequence": continue` and `claim_can_lower_to_runtime()` block.

- [ ] **Step 6: Run GlobalValues and Combo regression tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_globalvalues_authority.py tests/test_combo_plan.py tests/test_compile_globalvalues.py tests/test_compile_combo.py -q
```

Expected: all selected tests pass.

- [ ] **Step 7: Commit Task 3**

```powershell
git add src/hsconfig/globalvalues_authority.py src/hsconfig/combo_plan.py tests/test_globalvalues_authority.py tests/test_combo_plan.py
git commit -m "fix: gate globalvalues and combo lowering by surface authority"
```

---

### Task 4: Route CardID Behavior Through CardID Surface Gate

**Files:**
- Modify: `src/hsconfig/card_behavior_surface_router.py`
- Modify: `tests/test_card_behavior_router.py`
- Modify: `tests/test_surface_authority_split.py`

**Interfaces:**
- Consumes: `can_lower_to_cardid(claim) -> SurfaceGateDecision`
- Produces: CardID router only emits behavior rows for CardID-authorized claim kinds; rejected claims appear in `suppressed` with surface authority reasons.

- [ ] **Step 1: Add CardID rejection test**

Append to `tests/test_card_behavior_router.py`:

```python
from hsconfig.card_behavior_surface_router import route_card_behavior_surfaces


def test_cardid_router_reports_mulligan_claim_as_wrong_surface():
    routed = route_card_behavior_surfaces(
        [
            {
                "claim_kind": "mulligan_keep",
                "claim_readiness": "guide_backed",
                "trust_ceiling": "runtime_candidate",
                "cards": ["CARD_001"],
                "claim_id": "keep_card",
            }
        ]
    )

    assert routed["rows"] == []
    assert routed["suppressed"][0]["reason"] == "claim_kind_not_cardid_surface"
    assert routed["suppressed"][0]["claim_kind"] == "mulligan_keep"
```

- [ ] **Step 2: Run test to verify failure**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_card_behavior_router.py::test_cardid_router_reports_mulligan_claim_as_wrong_surface -q
```

Expected: fails if the router currently suppresses with a generic reason or silently handles the row differently.

- [ ] **Step 3: Implement CardID gate usage**

Patch imports in `src/hsconfig/card_behavior_surface_router.py`:

```python
from hsconfig.source_document_model import can_lower_to_cardid, normalized_claim_kind
```

Replace:

```python
        claim_kind = runtime_claim_kind(claim)
        cards = _claim_cards(claim)
        if not claim_can_lower_to_runtime(claim):
            suppressed.append(
                _suppressed_row(claim, claim_kind, cards, "claim_not_runtime_lowerable")
            )
            continue
```

with:

```python
        claim_kind = normalized_claim_kind(claim)
        cards = _claim_cards(claim)
        gate = can_lower_to_cardid(claim)
        if not gate.allowed:
            suppressed.append(_suppressed_row(claim, claim_kind, cards, gate.reason))
            continue
```

In `_resolved_choice_cards()`, replace `runtime_claim_kind(claim)` with `normalized_claim_kind(claim)` and replace the runtime-readiness check with:

```python
        if not can_lower_to_cardid(claim).allowed:
            continue
```

- [ ] **Step 4: Run CardID router regression tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_card_behavior_router.py tests/test_compile_cardid.py tests/test_mechanic_lowering_parity.py tests/test_mechanic_support.py -q
```

Expected: all selected tests pass. Existing meaningful CardID behavior rows for targeting, mechanics, discover, choose-one, and hero-power-transform remain intact.

- [ ] **Step 5: Commit Task 4**

```powershell
git add src/hsconfig/card_behavior_surface_router.py tests/test_card_behavior_router.py tests/test_surface_authority_split.py
git commit -m "fix: gate card behavior rows by cardid surface authority"
```

---

### Task 5: Update Operator Docs And Skill Contract

**Files:**
- Modify: `README.md`
- Modify: `docs/operator/README.md`
- Modify: `.agents/skills/hsconfig/SKILL.md`
- Modify: `docs/research/current-truth.md`

**Interfaces:**
- Consumes: surface gate vocabulary from Task 1.
- Produces: a consistent operator-facing rule: HSConfig never blocks valid decks for weak evidence, but each runtime file has its own authority gate.

- [ ] **Step 1: Update README active-path wording**

In `README.md`, keep the existing short intro and add this paragraph near the current Mulligan claim-kind paragraph:

```markdown
HSConfig separates source semantics from runtime authority. A claim such as
`hero_power_transform` or `card_role` can enrich the every-card contract and
per-card behavior reports without being allowed to write `Mulligan.json`,
`GlobalValues.json`, or `Combo.json`. Each runtime surface has its own gate, so
weak or wrong-surface claims remain visible instead of blocking the package.
```

- [ ] **Step 2: Update operator README**

In `docs/operator/README.md`, add a compact section after the current Mulligan note:

```markdown
### Source claim vs runtime surface

`claim_kind` describes what the source says. It does not by itself authorize a
runtime write. Runtime output is decided by surface-specific gates:

- `Mulligan.json`: only explicit `mulligan_keep` or `mulligan_discard` claims.
- `GlobalValues.json`: curated `gameplan_posture` overlays plus full baseline keys.
- `Combo.json`: exact `combo_sequence` claims with valid CardID sequences.
- `<CARDID>.json`: documented CardID behavior claims such as targeting,
  mechanic usage, hero-power transform, discover, choose-one, and known bad
  patterns.

Wrong-surface or low-confidence claims do not block deck generation. They are
reported as suppressed/report-only rows with explicit reasons.
```

- [ ] **Step 3: Update installed skill source**

In `.agents/skills/hsconfig/SKILL.md`, add the same operational rule in the workflow section:

```markdown
- Treat source claim kind and runtime surface authority as separate decisions.
  Generate the package for any valid deck, but only write a runtime row when
  the claim passes that surface's gate; otherwise keep the claim visible in
  reports.
```

- [ ] **Step 4: Update current truth**

In `docs/research/current-truth.md`, add a dated note:

```markdown
## 2026-07-11 Surface authority split

Current HSConfig truth: source claims are normalized first, then lowered through
surface-specific authority gates. This preserves no-block deck generation while
preventing source-backed effects such as Darkbishop Benedictus start-of-game
Hero Power transformation from becoming false opening-hand Mulligan keeps.
```

- [ ] **Step 5: Run docs/skill tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_docs_active_path.py tests/test_skill_files.py tests/test_skill_sync.py -q
```

Expected: all selected tests pass. If `tests/test_skill_sync.py` reports the installed skill is stale, run:

```powershell
python scripts/sync_installed_skill.py
$env:PYTHONPATH='src'; python -m pytest tests/test_skill_sync.py -q
```

- [ ] **Step 6: Commit Task 5**

```powershell
git add README.md docs/operator/README.md docs/research/current-truth.md .agents/skills/hsconfig/SKILL.md
git commit -m "docs: document source claim surface authority split"
```

---

### Task 6: End-To-End Regression And Cleanup

**Files:**
- No source files should be modified unless verification exposes a regression.
- Generated runtime outputs under `outputs/` must remain uncommitted.

**Interfaces:**
- Consumes: all previous tasks.
- Produces: verified, committed implementation with no generated runtime evidence committed.

- [ ] **Step 1: Run focused contract suite**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_surface_authority_split.py tests/test_claim_kind_runtime_contract.py tests/test_mulligan_plan.py tests/test_globalvalues_authority.py tests/test_combo_plan.py tests/test_card_behavior_router.py -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run ShadowPriest prepare regression**

Run:

```powershell
$env:PYTHONPATH='src'; python -m hsconfig prepare --deck-name ShadowPriest --deck-code "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=" --hs-id 2737726722 --hdt-deck-id "c4c8b6b9-1d8e-4c07-a6cd-1c0de84f7602" --json
```

Expected:
- command exits `0`
- output package is valid
- `SW_448` remains represented as hero-power/start-of-game contract behavior
- `SW_448` is not emitted as a Mulligan keep unless an explicit, non-start-of-game opening-hand source claim exists

- [ ] **Step 3: Run broad no-block and representative deck tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_universal_wild_no_block_matrix.py tests/test_multideck_source_backed_e2e.py tests/test_autonomous_guide_workflow_e2e.py tests/test_shadowpriest_e2e.py -q
```

Expected: all selected tests pass. Any failure must be fixed without adding HSTuner-style replay or post-run logic.

- [ ] **Step 4: Run full test suite**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest -q
```

Expected: full suite passes, allowing existing intentional skips only.

- [ ] **Step 5: Check generated artifacts and git state**

Run:

```powershell
git status --short --branch
git diff --stat
```

Expected:
- no raw runtime evidence, logs, HDT files, or `outputs/` runtime packages staged
- only intended source, tests, docs, and skill files are modified

- [ ] **Step 6: Final commit if Task 6 required fixes**

If Task 6 required code/doc fixes, commit them:

```powershell
git add <only-the-files-fixed-in-task-6>
git commit -m "test: verify surface authority split end to end"
```

If no files changed in Task 6, do not create an empty commit.

---

## Self-Review

**Spec coverage:** This plan covers the requested Source-/Contract-Logik hardening by adding semantic claim normalization, surface-specific runtime authority, no-block suppression reporting, Darkbishop/Mulligan protection, docs alignment, skill sync, and representative E2E verification.

**Placeholder scan:** No task contains TBD/TODO/fill-in placeholders. Each code-changing task includes exact files, test snippets, commands, expected outcomes, and commit commands.

**Type consistency:** The plan consistently uses `SurfaceGateDecision`, `normalized_claim_kind`, `can_lower_to_mulligan`, `can_lower_to_globalvalues`, `can_lower_to_combo`, and `can_lower_to_cardid`. Existing `runtime_claim_kind` remains available as a compatibility wrapper.

**Boundary check:** The plan does not add dependencies, replay parsing, HDT parsing, winrate validation, candidate promotion, Presume/Concede normal-path expansion, or HSTuner behavior.


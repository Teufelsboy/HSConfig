# HSConfig Source Contract Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden HSConfig's source-to-contract logic so start-of-game and deckbuilding effects stay runtime-visible without becoming false opening-hand mulligan keeps.

**Architecture:** Keep the existing single contract spine: source documents -> atomic `claim_kind` -> `source_contract_matrix` -> `surface_gate_decision` -> builder/router -> runtime package -> `reports/operator_summary.json` as the only apply authority. This plan makes the spine smaller and more deterministic by sharing role normalization, suppressing invalid mulligan anchors earlier, and broadening generic static semantics for Wild deckbuilding effects.

**Tech Stack:** Python 3.11+, pytest, existing HSConfig CLI and JSON report builders. No new runtime dependency.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig`.
- Do not create a second apply gate. `reports/operator_summary.json` remains the only normal runtime apply authority.
- Do not block arbitrary decks because source evidence is thin or unknown mechanics are present; use warnings and diagnostics.
- Normal runtime surfaces remain `Mulligan.json`, `GlobalValues.json`, per-card `<CARDID>.json`, and `Combo.json`.
- `Presume.json` and `Concede.json` stay outside the normal HSConfig path.
- Preserve the Darkbishop Benedictus split: keep `hero_power_transform` / Mind Spike behavior visible, but do not infer an opening-hand keep for the card itself.
- Research package used for this plan: `docs/research/2026-07-13-hsconfig-source-contract-logic-brainstorm-v4/`.
- Use TDD: write the focused failing test first, confirm it fails, then implement the minimum fix.
- Keep commits task-sized.

---

## File Structure

- Create `src/hsconfig/role_tokens.py`
  - Single owner for role, semantic-family, and mechanic-family token normalization.
  - Provides reusable helpers for source claims, card-role rows, and start-of-game non-hand detection.

- Modify `src/hsconfig/source_document_model.py`
  - Replace private `_role_tokens` usage with shared helpers.
  - Keep `START_OF_GAME_NON_HAND_EFFECT_ROLES` as the canonical role set unless Task 1 moves it into `role_tokens.py`.

- Modify `src/hsconfig/source_evidence_verifier.py`
  - Use the same role normalization as the surface gate.
  - Preserve warning-only behavior for suspicious `mulligan_keep` claims.

- Modify `src/hsconfig/research_contract.py`
  - Prevent `mulligan_anchor` and `mulligan_anchor_map.intent=hold` from being inferred for start-of-game non-hand enablers.

- Modify `src/hsconfig/gameplan_contract.py`
  - Prevent research-bundle or role-derived `mulligan_anchors` from reintroducing suppressed start-of-game non-hand holds.

- Modify `src/hsconfig/static_semantics.py`
  - Add generic deckbuilding/start-of-game family detection for odd/even, highlander, deck-size, starting-health, and in-deck requirements.

- Modify `src/hsconfig/report_ownership.py`
  - Add explicit ownership classifications while keeping `reports/operator_summary.json` as the only gate.

- Modify docs and skill text:
  - `docs/operator/guide-research-policy.md`
  - `docs/operator/README.md`
  - `.agents/skills/hsconfig/SKILL.md`

- Add or extend tests:
  - `tests/test_role_tokens.py`
  - `tests/test_source_evidence_verifier.py`
  - `tests/test_claim_kind_runtime_contract.py`
  - `tests/test_static_semantics.py`
  - `tests/test_report_ownership.py`
  - `tests/test_skill_files.py`

---

### Task 1: Shared Role Token Normalizer

**Files:**
- Create: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\role_tokens.py`
- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\source_document_model.py`
- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\source_evidence_verifier.py`
- Test: `C:\Users\darbo\Documents\HSConfig\tests\test_role_tokens.py`
- Test: `C:\Users\darbo\Documents\HSConfig\tests\test_source_evidence_verifier.py`

**Interfaces:**
- Produces: `role_tokens(value: Any) -> set[str]`
- Produces: `claim_role_tokens(claim: Mapping[str, Any], keys: Iterable[str] = ROLE_HINT_KEYS) -> set[str]`
- Produces: `card_role_tokens(card_role: Mapping[str, Any], claim: Mapping[str, Any] | None = None) -> set[str]`
- Produces: `has_start_of_game_non_hand_effect(roles: Iterable[str]) -> bool`
- Consumes: existing role-like fields `roles`, `semantic_families`, `mechanic_families`

- [ ] **Step 1: Write failing role normalizer tests**

Add `tests/test_role_tokens.py`:

```python
from hsconfig.role_tokens import (
    card_role_tokens,
    claim_role_tokens,
    has_start_of_game_non_hand_effect,
    role_tokens,
)


def test_role_tokens_normalizes_strings_iterables_and_ignores_empty_values():
    assert role_tokens(" Start_Of_Game ") == {"start_of_game"}
    assert role_tokens([" Pressure ", "", None, "Hero_Power_Transform"]) == {
        "pressure",
        "hero_power_transform",
    }
    assert role_tokens(("Highlander_Modifier", "Deck_Size_Modifier")) == {
        "highlander_modifier",
        "deck_size_modifier",
    }
    assert role_tokens({"Even_Odd_Modifier", "start_of_game"}) == {
        "even_odd_modifier",
        "start_of_game",
    }
    assert role_tokens({"nested": "ignored"}) == set()


def test_claim_role_tokens_merges_standard_role_family_keys():
    claim = {
        "roles": "start_of_game",
        "semantic_families": ("hero_power_transform",),
        "mechanic_families": {"shadowform"},
    }

    assert claim_role_tokens(claim) == {
        "start_of_game",
        "hero_power_transform",
        "shadowform",
    }


def test_card_role_tokens_merges_card_and_claim_context():
    card_role = {"roles": ["start_of_game"], "semantic_families": ["hero_power_transform"]}
    claim = {"mechanic_families": ["shadowform"]}

    assert card_role_tokens(card_role, claim) == {
        "start_of_game",
        "hero_power_transform",
        "shadowform",
    }


def test_has_start_of_game_non_hand_effect_requires_start_and_non_hand_family():
    assert has_start_of_game_non_hand_effect(["start_of_game", "hero_power_transform"]) is True
    assert has_start_of_game_non_hand_effect(["start_of_game", "mulligan_anchor"]) is False
    assert has_start_of_game_non_hand_effect(["hero_power_transform"]) is False
```

- [ ] **Step 2: Run the new tests and confirm failure**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_role_tokens.py -q
```

Expected: FAIL because `hsconfig.role_tokens` does not exist.

- [ ] **Step 3: Implement the shared helper**

Create `src/hsconfig/role_tokens.py`:

```python
from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


ROLE_HINT_KEYS = ("roles", "semantic_families", "mechanic_families")

START_OF_GAME_NON_HAND_EFFECT_ROLES = frozenset(
    {
        "deck_state_modifier",
        "deckbuilding_modifier",
        "deck_size_modifier",
        "even_odd_modifier",
        "highlander_modifier",
        "hero_power_transform",
        "passive_start_effect",
        "start_in_deck_requirement",
        "start_of_game_modifier",
    }
)


def role_tokens(value: Any) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, str):
        token = value.strip().lower()
        return {token} if token else set()
    if isinstance(value, (list, tuple, set, frozenset)):
        return {
            token
            for item in value
            if isinstance(item, str)
            for token in (item.strip().lower(),)
            if token
        }
    return set()


def claim_role_tokens(
    claim: Mapping[str, Any],
    keys: Iterable[str] = ROLE_HINT_KEYS,
) -> set[str]:
    roles: set[str] = set()
    for key in keys:
        roles.update(role_tokens(claim.get(key)))
    return roles


def card_role_tokens(
    card_role: Mapping[str, Any],
    claim: Mapping[str, Any] | None = None,
) -> set[str]:
    roles = claim_role_tokens(card_role, keys=("roles", "semantic_families"))
    if claim is not None:
        roles.update(claim_role_tokens(claim))
    return roles


def has_start_of_game_non_hand_effect(roles: Iterable[str]) -> bool:
    normalized = {
        token
        for role in roles
        for token in role_tokens(role)
    }
    return "start_of_game" in normalized and bool(
        normalized & START_OF_GAME_NON_HAND_EFFECT_ROLES
    )
```

- [ ] **Step 4: Wire `source_document_model.py` to the shared helper**

Change imports near the top:

```python
from hsconfig.role_tokens import (
    START_OF_GAME_NON_HAND_EFFECT_ROLES,
    card_role_tokens,
)
```

Remove the local `START_OF_GAME_NON_HAND_EFFECT_ROLES` definition and replace `_roles_for_card()` with:

```python
def _roles_for_card(
    card_id: str,
    card_roles: Mapping[str, Any],
    claim: Mapping[str, Any] | None,
) -> set[str]:
    role_row = card_roles.get(str(card_id), {})
    if not isinstance(role_row, Mapping):
        role_row = {}
    return card_role_tokens(role_row, claim)
```

Delete the private `_role_tokens()` function from `source_document_model.py`.

- [ ] **Step 5: Wire `source_evidence_verifier.py` to the shared helper**

Change imports:

```python
from hsconfig.role_tokens import START_OF_GAME_NON_HAND_EFFECT_ROLES, claim_role_tokens
from hsconfig.source_document_model import SUPPORTED_ATOMIC_CLAIM_KINDS, runtime_claim_kind
```

Replace `_claim_role_hints()` with:

```python
def _claim_role_hints(claim: dict[str, Any]) -> set[str]:
    return claim_role_tokens(claim, keys=SUSPICIOUS_KEEP_ROLE_KEYS)
```

- [ ] **Step 6: Add verifier parity test**

Append to `tests/test_source_evidence_verifier.py`:

```python
def test_verifier_warns_for_non_list_start_of_game_role_payloads():
    report = verify_source_documents(
        [
            _base_document(
                claims=[
                    {
                        "claim_kind": "mulligan_keep",
                        "cards": ["SW_448"],
                        "roles": "start_of_game",
                        "semantic_families": ("hero_power_transform",),
                        "evidence_text_short": "Darkbishop Benedictus starts the game with Mind Spike.",
                        "source_confidence": "high",
                    }
                ]
            )
        ]
    )

    assert "suspicious_mulligan_keep_non_hand_effect" in {
        warning["reason"] for warning in report["warnings"]
    }
```

- [ ] **Step 7: Run focused tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_role_tokens.py tests/test_source_evidence_verifier.py tests/test_claim_kind_runtime_contract.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit Task 1**

Run:

```powershell
git add src/hsconfig/role_tokens.py src/hsconfig/source_document_model.py src/hsconfig/source_evidence_verifier.py tests/test_role_tokens.py tests/test_source_evidence_verifier.py
git commit -m "refactor: share source role normalization"
```

---

### Task 2: Suppress False Mulligan Anchors In Research Contract

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\research_contract.py`
- Test: `C:\Users\darbo\Documents\HSConfig\tests\test_claim_kind_runtime_contract.py`

**Interfaces:**
- Consumes: `has_start_of_game_non_hand_effect(roles: Iterable[str]) -> bool`
- Produces: `build_research_contract_bundle(...).mulligan_anchor_map[card_id].intent != "hold"` for start-of-game non-hand effect cards.

- [ ] **Step 1: Add failing upstream research-contract test**

Append to `tests/test_claim_kind_runtime_contract.py`:

```python
def test_research_contract_does_not_infer_hold_for_start_of_game_non_hand_keep_claim():
    deck_identity = {
        "deck_name": "FixtureDeck",
        "cards": [{"card_id": "SW_448", "count": 1, "name": "Darkbishop Benedictus"}],
    }
    card_metadata = {
        "cards": [
            {
                "card_id": "SW_448",
                "name": "Darkbishop Benedictus",
                "semantic_families": ["start_of_game", "hero_power_transform"],
            }
        ]
    }
    source_claims = normalize_source_claims(
        [
            {
                "source": "fixture-guide",
                "claim_kind": "mulligan_keep",
                "claim_readiness": "guide_backed",
                "trust_ceiling": "runtime_candidate",
                "claim": "The effect starts the game in Shadowform.",
                "cards": ["SW_448"],
                "confidence": "guide_backed",
            }
        ]
    )

    bundle = build_research_contract_bundle(deck_identity, card_metadata, source_claims)

    assert "mulligan_anchor" not in bundle["card_role_map"]["SW_448"]["roles"]
    assert bundle["mulligan_anchor_map"]["SW_448"]["intent"] != "hold"
```

- [ ] **Step 2: Run test and confirm failure**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_claim_kind_runtime_contract.py::test_research_contract_does_not_infer_hold_for_start_of_game_non_hand_keep_claim -q
```

Expected: FAIL because `_roles_from_claims_and_semantics()` still adds `mulligan_anchor`.

- [ ] **Step 3: Implement minimal research-contract suppression**

In `src/hsconfig/research_contract.py`, add import:

```python
from hsconfig.role_tokens import has_start_of_game_non_hand_effect
```

Add helper near `_roles_from_claims_and_semantics()`:

```python
def _can_be_mulligan_anchor(roles: set[str]) -> bool:
    return not has_start_of_game_non_hand_effect(roles)
```

Replace the opening part of `_roles_from_claims_and_semantics()` with:

```python
def _roles_from_claims_and_semantics(
    semantic_families: list[str],
    claims: list[dict[str, Any]],
) -> list[str]:
    text = _claim_text(claims)
    claim_types = {str(claim.get("claim_type", "")).lower() for claim in claims}
    claim_kinds = {runtime_claim_kind(claim) for claim in claims}
    roles = set(semantic_families)
    if (
        "mulligan_keep" in claim_kinds
        and not _has_negative_keep(text)
        and _can_be_mulligan_anchor(roles)
    ):
        roles.add("mulligan_anchor")
```

Leave the existing pressure/combo logic below that block unchanged.

Change `_mulligan_intent()`:

```python
def _mulligan_intent(
    card_id: str,
    claims: list[dict[str, Any]],
    roles: list[str],
    confidence: str,
) -> dict[str, Any]:
    text = _claim_text(claims)
    role_set = set(roles)
    if _has_negative_keep(text):
        intent = "avoid"
    elif "mulligan_anchor" in role_set and _can_be_mulligan_anchor(role_set):
        intent = "hold"
    else:
        intent = "neutral"
    return {
        "card_id": card_id,
        "intent": intent,
        "condition": "*",
        "confidence": confidence,
        "source_claim_ids": [str(claim["claim_id"]) for claim in claims],
    }
```

- [ ] **Step 4: Run focused tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_claim_kind_runtime_contract.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 2**

Run:

```powershell
git add src/hsconfig/research_contract.py tests/test_claim_kind_runtime_contract.py
git commit -m "fix: suppress non-hand effect mulligan anchors"
```

---

### Task 3: Suppress False Mulligan Anchors In Gameplan Contract

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\gameplan_contract.py`
- Test: `C:\Users\darbo\Documents\HSConfig\tests\test_claim_kind_runtime_contract.py`

**Interfaces:**
- Consumes: `has_start_of_game_non_hand_effect(roles: Iterable[str]) -> bool`
- Produces: `build_gameplan_contract(...).mulligan_anchors == []` when research bundle tries to hold a start-of-game non-hand effect card.

- [ ] **Step 1: Add failing gameplan-contract regression**

Append to `tests/test_claim_kind_runtime_contract.py`:

```python
def test_gameplan_contract_rejects_research_bundle_hold_for_non_hand_start_effect():
    deck_identity = {
        "deck_name": "FixtureDeck",
        "cards": [{"card_id": "SW_448", "count": 1, "name": "Darkbishop Benedictus"}],
    }
    card_metadata = {
        "cards": [
            {
                "card_id": "SW_448",
                "name": "Darkbishop Benedictus",
                "semantic_families": ["start_of_game", "hero_power_transform"],
            }
        ]
    }
    source_claims = normalize_source_claims([])
    research_bundle = {
        "card_role_map": {
            "SW_448": {
                "roles": ["start_of_game", "hero_power_transform", "mulligan_anchor"],
                "confidence": "guide_backed",
                "source_claim_ids": ["fixture_claim"],
            }
        },
        "mulligan_anchor_map": {
            "SW_448": {
                "intent": "hold",
                "condition": "*",
                "confidence": "guide_backed",
                "source_claim_ids": ["fixture_claim"],
            }
        },
    }

    contract = build_gameplan_contract(
        deck_identity,
        card_metadata,
        source_claims,
        research_bundle=research_bundle,
    )

    assert contract["cards"]["SW_448"]["roles"].count("mulligan_anchor") == 0
    assert contract["mulligan_anchors"] == []
```

- [ ] **Step 2: Run test and confirm failure**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_claim_kind_runtime_contract.py::test_gameplan_contract_rejects_research_bundle_hold_for_non_hand_start_effect -q
```

Expected: FAIL because research bundle hold rows currently flow into `mulligan_anchors`.

- [ ] **Step 3: Implement minimal gameplan suppression**

In `src/hsconfig/gameplan_contract.py`, add import:

```python
from hsconfig.role_tokens import has_start_of_game_non_hand_effect
```

Add helper near `_merge_source_claim_ids()`:

```python
def _roles_allow_mulligan_anchor(roles: list[str]) -> bool:
    return not has_start_of_game_non_hand_effect(roles)
```

After the `roles = sorted({...})` block, add:

```python
        if not _roles_allow_mulligan_anchor(roles):
            roles = [role for role in roles if role != "mulligan_anchor"]
```

Replace the mulligan-anchor append condition block with:

```python
        research_mulligan_row = research_mulligan.get(card_id, {})
        if research_mulligan_row.get("intent") == "hold" and _roles_allow_mulligan_anchor(roles):
            mulligan_anchors.append(
                {
                    "card_id": card_id,
                    "intent": "hold",
                    "condition": research_mulligan_row.get("condition", "*"),
                    "confidence": research_mulligan_row.get("confidence", coverage_status),
                    "source_claim_ids": _merge_source_claim_ids(
                        source_claim_ids, research_mulligan_row.get("source_claim_ids", [])
                    ),
                }
            )
        elif "mulligan_anchor" in roles and _roles_allow_mulligan_anchor(roles):
            mulligan_anchors.append(
                {
                    "card_id": card_id,
                    "intent": "hold",
                    "condition": "*",
                    "confidence": coverage_status,
                    "source_claim_ids": source_claim_ids,
                }
            )
```

- [ ] **Step 4: Run focused tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_claim_kind_runtime_contract.py tests/test_mulligan_plan.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 3**

Run:

```powershell
git add src/hsconfig/gameplan_contract.py tests/test_claim_kind_runtime_contract.py
git commit -m "fix: keep gameplan mulligan anchors hand-bound"
```

---

### Task 4: Static Semantics For Deckbuilding And Start-Of-Game Families

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\static_semantics.py`
- Test: `C:\Users\darbo\Documents\HSConfig\tests\test_static_semantics.py`
- Test: `C:\Users\darbo\Documents\HSConfig\tests\test_static_semantic_micro_fixtures.py`

**Interfaces:**
- Produces: `infer_static_semantics(card)["families"]` includes generic non-hand families for common Wild deckbuilding effects.
- Consumes: card `name`, `text`, `mechanics`, `referenced_tags`, and type fields.

- [ ] **Step 1: Add static semantics regression tests**

Append to `tests/test_static_semantics.py`:

```python
def test_infers_odd_even_deckbuilding_start_of_game_modifiers():
    genn = {
        "id": "GIL_692",
        "type": "MINION",
        "text": "Start of Game: If your deck has only even-Cost cards, your starting Hero Power costs (1).",
    }
    baku = {
        "id": "GIL_826",
        "type": "MINION",
        "text": "Start of Game: If your deck has only odd-Cost cards, upgrade your Hero Power.",
    }

    assert {"start_of_game", "deckbuilding_modifier", "even_odd_modifier"} <= _families(genn)
    assert {"start_of_game", "deckbuilding_modifier", "even_odd_modifier"} <= _families(baku)


def test_infers_highlander_deckbuilding_modifier():
    card = {
        "id": "HIGHLANDER_FIXTURE",
        "type": "MINION",
        "text": "Battlecry: If your deck has no duplicates, deal 10 damage.",
    }

    assert {"deckbuilding_modifier", "highlander_modifier"} <= _families(card)


def test_infers_deck_size_and_starting_health_modifier():
    card = {
        "id": "REV_018",
        "type": "MINION",
        "text": "Your deck size and starting Health are 40.",
    }

    assert {"deckbuilding_modifier", "deck_size_modifier", "deck_state_modifier"} <= _families(card)


def test_infers_start_in_deck_requirement_without_mulligan_semantics():
    card = {
        "id": "START_DECK_FIXTURE",
        "type": "MINION",
        "text": "If this is in your deck at the start of the game, draw it later.",
    }

    assert {"start_of_game", "start_in_deck_requirement", "deckbuilding_modifier"} <= _families(card)
```

- [ ] **Step 2: Run tests and confirm failure**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_static_semantics.py -q
```

Expected: FAIL for the new family assertions.

- [ ] **Step 3: Implement generic static semantic rules**

In `src/hsconfig/static_semantics.py`, add helpers above `infer_static_semantics()`:

```python
def _has_deck_condition(lowered: str) -> bool:
    return " deck " in f" {lowered} " or "your deck" in lowered


def _has_even_odd_deck_condition(lowered: str) -> bool:
    return any(
        phrase in lowered
        for phrase in (
            "only even-cost",
            "only even cost",
            "only even-cost cards",
            "only odd-cost",
            "only odd cost",
            "only odd-cost cards",
        )
    )


def _has_highlander_condition(lowered: str) -> bool:
    return "no duplicates" in lowered or "no duplicate" in lowered


def _has_deck_size_or_starting_health_modifier(lowered: str) -> bool:
    return (
        "deck size" in lowered
        or "starting health" in lowered
        or "starting health are" in lowered
    )


def _has_start_in_deck_requirement(lowered: str) -> bool:
    return (
        "if this is in your deck" in lowered
        or "if this is in your starting deck" in lowered
        or "in your deck at the start of the game" in lowered
    )
```

Inside `infer_static_semantics()` after the existing `if "start of game" in lowered:` block, add:

```python
    if "start_of_game" in families:
        _add(families, evidence, "start_of_game_modifier", "text", "start of game")
        _add(families, evidence, "passive_start_effect", "text", "start of game")
    if _has_deck_condition(lowered):
        _add(families, evidence, "deckbuilding_modifier", "text", "deck condition")
    if _has_even_odd_deck_condition(lowered):
        _add(families, evidence, "deckbuilding_modifier", "text", "odd/even deck condition")
        _add(families, evidence, "even_odd_modifier", "text", "odd/even deck condition")
    if _has_highlander_condition(lowered):
        _add(families, evidence, "deckbuilding_modifier", "text", "no duplicates")
        _add(families, evidence, "highlander_modifier", "text", "no duplicates")
    if _has_deck_size_or_starting_health_modifier(lowered):
        _add(families, evidence, "deckbuilding_modifier", "text", "deck size or starting health")
        _add(families, evidence, "deck_size_modifier", "text", "deck size or starting health")
        _add(families, evidence, "deck_state_modifier", "text", "deck size or starting health")
    if _has_start_in_deck_requirement(lowered):
        _add(families, evidence, "deckbuilding_modifier", "text", "in deck at start")
        _add(families, evidence, "start_in_deck_requirement", "text", "in deck at start")
        _add(families, evidence, "start_of_game", "text", "in deck at start")
```

- [ ] **Step 4: Run static semantic tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_static_semantics.py tests/test_static_semantic_micro_fixtures.py -q
```

Expected: PASS.

- [ ] **Step 5: Run contract boundary tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_claim_kind_runtime_contract.py tests/test_source_claim_quality_autonomy.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 4**

Run:

```powershell
git add src/hsconfig/static_semantics.py tests/test_static_semantics.py
git commit -m "feat: classify deckbuilding start effects"
```

---

### Task 5: Ownership Manifest And Single Apply Authority Guard

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\report_ownership.py`
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_report_ownership.py`
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_apply_authority_boundary.py`

**Interfaces:**
- Produces: every ownership row has `classification` in `{"gate", "diagnostic", "mechanic_drift", "internal_reference"}`.
- Preserves: exactly one `classification == "gate"` row: `reports/operator_summary.json`.

- [ ] **Step 1: Add failing ownership classification test**

Append to `tests/test_report_ownership.py`:

```python
def test_report_ownership_classifies_every_operator_report_and_keeps_single_gate():
    rows = build_report_ownership()

    assert rows
    assert all(row.get("classification") for row in rows)
    gates = [row for row in rows if row["classification"] == "gate"]
    assert [row["file"] for row in gates] == ["reports/operator_summary.json"]
    assert all(
        row["classification"] != "gate" or row["authority"] == "normal_operator_gate"
        for row in rows
    )
```

- [ ] **Step 2: Run test and confirm failure**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_report_ownership.py::test_report_ownership_classifies_every_operator_report_and_keeps_single_gate -q
```

Expected: FAIL because existing rows do not all expose `classification`.

- [ ] **Step 3: Add classifications to report ownership rows**

In `src/hsconfig/report_ownership.py`, add this field to each row:

```python
"classification": "gate",
```

only for `reports/operator_summary.json`.

Use these classifications for existing rows:

```python
"classification": "diagnostic",
```

for source/runtime explainability, source contract audit, source claim gap, strong promotion, per-card readiness, guide source depth, global-values authority, semantic enrichment.

Use:

```python
"classification": "mechanic_drift",
```

for `reports/mechanic_drift_report.json`.

- [ ] **Step 4: Add explicit non-authority assertion**

Append to `tests/test_apply_authority_boundary.py`:

```python
def test_report_ownership_has_no_second_apply_gate():
    from hsconfig.report_ownership import build_report_ownership

    gate_rows = [row for row in build_report_ownership() if row.get("classification") == "gate"]

    assert [row["file"] for row in gate_rows] == ["reports/operator_summary.json"]
```

- [ ] **Step 5: Run focused authority tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_report_ownership.py tests/test_apply_authority_boundary.py tests/test_no_second_gate_contract.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 5**

Run:

```powershell
git add src/hsconfig/report_ownership.py tests/test_report_ownership.py tests/test_apply_authority_boundary.py
git commit -m "test: classify report ownership authority"
```

---

### Task 6: Operator Docs And Skill Sync

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\docs\operator\guide-research-policy.md`
- Modify: `C:\Users\darbo\Documents\HSConfig\docs\operator\README.md`
- Modify: `C:\Users\darbo\Documents\HSConfig\.agents\skills\hsconfig\SKILL.md`
- Test: `C:\Users\darbo\Documents\HSConfig\tests\test_skill_files.py`
- Test: `C:\Users\darbo\Documents\HSConfig\tests\test_docs_active_path.py`

**Interfaces:**
- Produces: docs state that effect semantics and mulligan keeps are separate.
- Produces: docs state diagnostics remain non-gating and `operator_summary.json` remains authority.

- [ ] **Step 1: Add docs/skill regression tests**

Append to `tests/test_docs_active_path.py`:

```python
def test_operator_docs_explain_effect_semantics_are_not_mulligan_keeps():
    text = (ROOT / "docs" / "operator" / "guide-research-policy.md").read_text(encoding="utf-8")

    assert "Effect semantics are not opening-hand mulligan keeps" in text
    assert "Start-of-game" in text
    assert "operator_summary.json remains the normal apply authority" in text
```

Append to `tests/test_skill_files.py`:

```python
def test_hsconfig_skill_explains_start_effect_mulligan_split():
    text = (ROOT / ".agents" / "skills" / "hsconfig" / "SKILL.md").read_text(encoding="utf-8")

    assert "Effect semantics are not opening-hand mulligan keeps" in text
    assert "Darkbishop Benedictus" in text
    assert "operator_summary.json remains the normal apply authority" in text
```

- [ ] **Step 2: Run tests and confirm failure**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_docs_active_path.py::test_operator_docs_explain_effect_semantics_are_not_mulligan_keeps tests/test_skill_files.py::test_hsconfig_skill_explains_start_effect_mulligan_split -q
```

Expected: FAIL until docs and skill are updated.

- [ ] **Step 3: Update operator policy doc**

Add this section to `docs/operator/guide-research-policy.md` near the mulligan policy section:

```markdown
### Effect Semantics Are Not Opening-Hand Mulligan Keeps

Start-of-game, deckbuilding, and hero-power-transform effects can be important
runtime semantics without being cards to keep in the opening hand. Darkbishop
Benedictus is the reference case: the Shadowform / Mind Spike behavior belongs
in card behavior semantics, but the card itself must not become a Mulligan.json
hold unless a source explicitly describes opening-hand mulligan intent.

This split also applies to odd/even, highlander, deck-size, starting-health,
and start-in-deck effects. These effects may create CardID behavior, source
diagnostics, or report-visible expectations. They do not create mulligan keeps
from generic card importance, start-of-game text, or deckbuilding text.

operator_summary.json remains the normal apply authority.
```

- [ ] **Step 4: Update operator README**

Add this short line near the normal surface explanation in `docs/operator/README.md`:

```markdown
Effect semantics are not opening-hand mulligan keeps: start-of-game and
deckbuilding cards can stay visible in card behavior or diagnostics while
remaining absent from `Mulligan.json`.
```

- [ ] **Step 5: Update repo skill**

Add the same operational rule to `.agents/skills/hsconfig/SKILL.md`:

```markdown
Effect semantics are not opening-hand mulligan keeps. Preserve start-of-game,
deckbuilding, and hero-power-transform behavior such as Darkbishop Benedictus
-> Mind Spike, but do not place the enabler card in `Mulligan.json` unless a
source explicitly describes opening-hand mulligan intent. `operator_summary.json`
remains the normal apply authority.
```

- [ ] **Step 6: Run docs/skill tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_docs_active_path.py tests/test_skill_files.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit Task 6**

Run:

```powershell
git add docs/operator/guide-research-policy.md docs/operator/README.md .agents/skills/hsconfig/SKILL.md tests/test_docs_active_path.py tests/test_skill_files.py
git commit -m "docs: document effect versus mulligan split"
```

---

### Task 7: Final Contract-Spine Verification

**Files:**
- No source edits unless verification finds a regression.
- Review: `C:\Users\darbo\Documents\HSConfig\docs\research\2026-07-13-hsconfig-source-contract-logic-brainstorm-v4\`
- Review: `C:\Users\darbo\Documents\HSConfig\docs\superpowers\plans\2026-07-13-hsconfig-source-contract-polish.md`

**Interfaces:**
- Consumes: all prior tasks.
- Produces: verified branch with no false second gate and no false start-effect mulligan leak.

- [ ] **Step 1: Validate research package**

Run:

```powershell
$dir='docs\research\2026-07-13-hsconfig-source-contract-logic-brainstorm-v4\results'
Get-ChildItem $dir -Filter *.json | ForEach-Object {
  python C:\Users\darbo\.codex\skills\research\validate_json.py `
    -f docs\research\2026-07-13-hsconfig-source-contract-logic-brainstorm-v4\fields.yaml `
    -j $_.FullName
}
```

Expected: each JSON prints `[PASS]` and `Coverage: 100.0% (10/10)`.

- [ ] **Step 2: Run contract-spine sentinel**

Run:

```powershell
$env:PYTHONPATH='src'; python -m hsconfig contract-spine-sentinel --json
```

Expected:

```json
{
  "status": "clean",
  "authority": "diagnostic_only",
  "operator_gate_impact": "diagnostic_only",
  "apply_blocking": false,
  "problems": []
}
```

- [ ] **Step 3: Run focused test suite**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest `
  tests/test_role_tokens.py `
  tests/test_claim_kind_runtime_contract.py `
  tests/test_source_evidence_verifier.py `
  tests/test_static_semantics.py `
  tests/test_static_semantic_micro_fixtures.py `
  tests/test_report_ownership.py `
  tests/test_apply_authority_boundary.py `
  tests/test_no_second_gate_contract.py `
  tests/test_docs_active_path.py `
  tests/test_skill_files.py `
  -q
```

Expected: PASS.

- [ ] **Step 4: Run representative package smoke tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest `
  tests/test_shadowpriest_depth_e2e.py `
  tests/test_archetype_fixture_e2e.py `
  tests/test_universal_wild_no_block_matrix.py `
  tests/test_supplemental_cute_warrior_load_safe.py `
  -q
```

Expected: PASS.

- [ ] **Step 5: Run wider suite if focused tests are green**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest -q
```

Expected: PASS. If it fails outside this plan's touched surfaces, capture the failing test names and determine whether they are caused by this branch before making any fix.

- [ ] **Step 6: Inspect git diff**

Run:

```powershell
git status --short --branch
git diff --stat
git diff -- src/hsconfig tests docs/operator .agents/skills/hsconfig docs/superpowers/plans
```

Expected: only this plan's intended files are modified or committed. No runtime evidence, logs, `.hdtreplay`, `.hsreplay`, `Power.log`, or private runtime files are present.

- [ ] **Step 7: Commit research and plan artifacts if still uncommitted**

Run:

```powershell
git add docs/research/2026-07-13-hsconfig-source-contract-logic-brainstorm-v4 docs/superpowers/plans/2026-07-13-hsconfig-source-contract-polish.md
git commit -m "docs: add source contract polish research plan"
```

Expected: commit succeeds if those files were not already committed by an earlier task.

- [ ] **Step 8: Push branch**

Run:

```powershell
git push origin codex/hsconfig-contract-spine-guard-wave
```

Expected: branch is up to date on GitHub.

---

## Self-Review

- Spec coverage: covered shared role normalization, early mulligan-anchor suppression, static deckbuilding semantics, diagnostic-only single authority, docs/skill sync, and final verification.
- Placeholder scan: no incomplete implementation placeholders are present; every code-changing step includes concrete code or exact insertion text.
- Type consistency: all new helpers use `Mapping[str, Any]`, `Iterable[str]`, and `set[str]`, matching existing Python 3.11 style in HSConfig.
- Scope check: this is one coherent contract-spine polish wave. It avoids broader guide acquisition, new runtime surfaces, and major package-builder refactors.

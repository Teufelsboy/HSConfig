# HSConfig Source-Backed Strong Closure Profiles v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `SOURCE_BACKED_STRONG` less falsely conservative by evaluating source closure through archetype-specific profiles, while preserving no-block config generation, no silent default-only output, and the Darkbishop effect-not-mulligan boundary.

**Architecture:** Add a small closure-profile layer between source/claim analysis and Strong promotion. Existing claim-kind gates remain the runtime authority; profiles only decide whether the relevant source-to-runtime lanes for an archetype are closed enough to label the package `SOURCE_BACKED_STRONG`. `operator_summary.json` remains the single normal apply authority.

**Tech Stack:** Python package under `src/hsconfig`, pytest, JSON fixtures, existing HSConfig CLI/reporting modules. No new runtime dependencies.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig`.
- Keep HSConfig pre-run only: no replay, winrate, HSTuner, or post-game tuning logic.
- `operator_summary.json` remains the only normal apply authority.
- `SOURCE_BACKED_STRONG` remains source-confidence, not a runtime apply gate.
- Any valid deck must still produce a load-safe package when package structure is valid.
- Do not promote `decklist_only`, statistical enrichment, snippets, `policy_fallback`, or `default_runtime` to `SOURCE_BACKED_STRONG`.
- No hidden default-only runtime: every expected surface must be emitted, explicitly suppressed, or reported as a visible gap/source action.
- Preserve Darkbishop Benedictus / `SW_448` as `hero_power_transform` / Mind Spike effect semantics, but do not emit opening-hand Mulligan keep without explicit source text.
- Normal HSConfig output must not emit `Presume.json`, `Concede.json`, or aggregate `CardBehavior.json`.
- Keep the change narrow: no broad docs cleanup, no new workflow layer, no source schema rewrite.

---

## File Structure

- Modify `src/hsconfig/strong_closure_profiles.py`
  - New focused module for archetype closure profiles and profile verdicts.
- Modify `src/hsconfig/operator_summary.py`
  - Use profile verdicts when computing Strong readiness and expose compact profile diagnostics.
- Modify `src/hsconfig/source_autopilot.py`
  - Replace the blanket "non-mulligan apply surface" requirement with profile-aware first-missing-link output.
- Modify `src/hsconfig/source_evidence_closure.py`
  - Include profile closure status in the compact diagnostic closure report.
- Modify `docs/operator/archetype-fixture-matrix.json`
  - Record expected closure profile and first profile gap per representative deck.
- Modify `.agents/skills/hsconfig/SKILL.md`
  - Keep installed skill guidance aligned if this repo-local skill source is used.
- Modify `C:\Users\darbo\.codex\skills\hsconfig\SKILL.md`
  - Sync the installed skill after repo-source updates.
- Test `tests/test_strong_closure_profiles.py`
  - New unit tests for profile selection and closure decisions.
- Modify `tests/test_source_backed_strong_harvester_closure.py`
  - Update existing behavior that currently proves the conservative blocker.
- Modify `tests/test_no_default_only_semantic_archetype_matrix.py`
  - Ensure profile Strong logic does not hide default-only runtime.
- Modify `tests/test_shadowpriest_e2e.py`
  - Preserve Darkbishop effect-not-mulligan canary after profile changes.
- Modify `tests/test_universal_wild_no_block_matrix.py`
  - Ensure valid deck generation remains no-block for all representative decks.
- Modify `tests/test_skill_sync.py`
  - Ensure installed and repo skill instructions stay in sync.

---

### Task 1: Add Closure Profile Model

**Files:**
- Create: `src/hsconfig/strong_closure_profiles.py`
- Test: `tests/test_strong_closure_profiles.py`

**Interfaces:**
- Produces:
  - `ClosureProfileRequirement = dataclass`
  - `ClosureProfileVerdict = dataclass`
  - `profile_for_archetype(archetype_bucket: str, mechanics: Iterable[str]) -> str`
  - `evaluate_closure_profile(*, archetype_bucket: str, primary_mechanics: Iterable[str], source_claim_kinds: Iterable[str], emitted_surfaces: Iterable[str], default_only_surfaces: Iterable[str], suppressed_claim_kinds: Iterable[str]) -> ClosureProfileVerdict`
- Consumes:
  - Existing claim kinds: `mulligan_keep`, `mulligan_discard`, `gameplan_posture`, `targeting_rule`, `hero_power_transform`, `mechanic_usage`, `combo_sequence`, `card_role`, `known_bad_pattern`.

- [ ] **Step 1: Write failing profile-selection tests**

Add `tests/test_strong_closure_profiles.py`:

```python
from hsconfig.strong_closure_profiles import evaluate_closure_profile, profile_for_archetype


def test_shadowpriest_uses_aggro_hero_power_profile():
    assert (
        profile_for_archetype(
            "aggro_burn_hero_power_transform",
            ["aggro", "burn", "shadow_hero_power"],
        )
        == "aggro_burn_hero_power"
    )


def test_weapon_deck_uses_weapon_pressure_profile():
    assert (
        profile_for_archetype(
            "weapon_sequence_pressure",
            ["weapon", "pirate", "attack_sequence"],
        )
        == "weapon_pressure"
    )


def test_unknown_deck_uses_generic_profile_without_blocking():
    assert profile_for_archetype("unknown_homebrew", ["future_mechanic"]) == "generic_no_block"


def test_aggro_burn_profile_closes_with_mulligan_posture_and_targeting():
    verdict = evaluate_closure_profile(
        archetype_bucket="aggro_burn_hero_power_transform",
        primary_mechanics=["aggro", "burn", "shadow_hero_power"],
        source_claim_kinds=[
            "gameplan_posture",
            "mulligan_keep",
            "mulligan_discard",
            "targeting_rule",
            "hero_power_transform",
        ],
        emitted_surfaces=["GlobalValues.json", "Mulligan.json", "SW_448.json"],
        default_only_surfaces=[],
        suppressed_claim_kinds=[],
    )

    assert verdict.profile_name == "aggro_burn_hero_power"
    assert verdict.closed is True
    assert verdict.first_missing_link == "none"
    assert verdict.strong_eligible is True


def test_default_only_surface_blocks_profile_strong_but_not_load_safe():
    verdict = evaluate_closure_profile(
        archetype_bucket="aggro_burn_hero_power_transform",
        primary_mechanics=["aggro", "burn", "shadow_hero_power"],
        source_claim_kinds=[
            "gameplan_posture",
            "mulligan_keep",
            "targeting_rule",
            "hero_power_transform",
        ],
        emitted_surfaces=["GlobalValues.json", "Mulligan.json"],
        default_only_surfaces=["Mulligan.json"],
        suppressed_claim_kinds=[],
    )

    assert verdict.closed is False
    assert verdict.strong_eligible is False
    assert verdict.first_missing_link == "default_only_surface:Mulligan.json"
    assert verdict.apply_blocking is False
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
python -m pytest tests/test_strong_closure_profiles.py -q
```

Expected: fail with `ModuleNotFoundError: No module named 'hsconfig.strong_closure_profiles'`.

- [ ] **Step 3: Implement minimal profile module**

Create `src/hsconfig/strong_closure_profiles.py`:

```python
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class ClosureProfileRequirement:
    profile_name: str
    required_any_claim_groups: tuple[tuple[str, ...], ...]
    required_surfaces: tuple[str, ...]


@dataclass(frozen=True)
class ClosureProfileVerdict:
    profile_name: str
    closed: bool
    strong_eligible: bool
    first_missing_link: str
    missing_claim_groups: tuple[str, ...]
    missing_surfaces: tuple[str, ...]
    apply_blocking: bool = False


PROFILE_REQUIREMENTS: dict[str, ClosureProfileRequirement] = {
    "aggro_burn_hero_power": ClosureProfileRequirement(
        profile_name="aggro_burn_hero_power",
        required_any_claim_groups=(
            ("gameplan_posture",),
            ("mulligan_keep", "mulligan_discard"),
            ("targeting_rule", "hero_power_transform", "card_role"),
        ),
        required_surfaces=("GlobalValues.json", "Mulligan.json"),
    ),
    "weapon_pressure": ClosureProfileRequirement(
        profile_name="weapon_pressure",
        required_any_claim_groups=(
            ("gameplan_posture",),
            ("mulligan_keep", "mulligan_discard", "card_role"),
            ("targeting_rule", "mechanic_usage", "card_role"),
        ),
        required_surfaces=("GlobalValues.json", "Mulligan.json"),
    ),
    "combo_setup": ClosureProfileRequirement(
        profile_name="combo_setup",
        required_any_claim_groups=(
            ("gameplan_posture",),
            ("combo_sequence", "card_role"),
            ("mulligan_keep", "mulligan_discard", "card_role"),
        ),
        required_surfaces=("GlobalValues.json", "Mulligan.json"),
    ),
    "board_flood_recruit": ClosureProfileRequirement(
        profile_name="board_flood_recruit",
        required_any_claim_groups=(
            ("gameplan_posture",),
            ("mulligan_keep", "mulligan_discard", "card_role"),
            ("mechanic_usage", "card_role"),
        ),
        required_surfaces=("GlobalValues.json", "Mulligan.json"),
    ),
    "generic_no_block": ClosureProfileRequirement(
        profile_name="generic_no_block",
        required_any_claim_groups=(("gameplan_posture", "card_role", "mechanic_usage"),),
        required_surfaces=("GlobalValues.json", "Mulligan.json"),
    ),
}


def profile_for_archetype(archetype_bucket: str, mechanics: Iterable[str]) -> str:
    bucket = archetype_bucket.lower()
    mechanic_set = {mechanic.lower() for mechanic in mechanics}

    if "hero_power" in bucket or "shadow_hero_power" in mechanic_set:
        return "aggro_burn_hero_power"
    if "weapon" in bucket or "weapon" in mechanic_set or "hero_attack" in mechanic_set:
        return "weapon_pressure"
    if "combo" in bucket or "combo" in mechanic_set:
        return "combo_setup"
    if "recruit" in bucket or "board_flood" in mechanic_set or "token_board" in mechanic_set:
        return "board_flood_recruit"
    if "aggro" in bucket or "burn" in mechanic_set or "pirate" in mechanic_set:
        return "aggro_burn_hero_power"
    return "generic_no_block"


def evaluate_closure_profile(
    *,
    archetype_bucket: str,
    primary_mechanics: Iterable[str],
    source_claim_kinds: Iterable[str],
    emitted_surfaces: Iterable[str],
    default_only_surfaces: Iterable[str],
    suppressed_claim_kinds: Iterable[str],
) -> ClosureProfileVerdict:
    profile_name = profile_for_archetype(archetype_bucket, primary_mechanics)
    requirement = PROFILE_REQUIREMENTS[profile_name]
    claims = {claim.lower() for claim in source_claim_kinds}
    emitted = set(emitted_surfaces)
    default_only = set(default_only_surfaces)
    suppressed = {claim.lower() for claim in suppressed_claim_kinds}

    if default_only:
        first = sorted(default_only)[0]
        return ClosureProfileVerdict(
            profile_name=profile_name,
            closed=False,
            strong_eligible=False,
            first_missing_link=f"default_only_surface:{first}",
            missing_claim_groups=(),
            missing_surfaces=(),
        )

    missing_groups: list[str] = []
    for group in requirement.required_any_claim_groups:
        if not any(claim in claims and claim not in suppressed for claim in group):
            missing_groups.append("|".join(group))

    missing_surfaces = tuple(
        surface for surface in requirement.required_surfaces if surface not in emitted
    )
    closed = not missing_groups and not missing_surfaces
    if closed:
        first_missing = "none"
    elif missing_groups:
        first_missing = f"missing_claim_group:{missing_groups[0]}"
    else:
        first_missing = f"missing_surface:{missing_surfaces[0]}"

    return ClosureProfileVerdict(
        profile_name=profile_name,
        closed=closed,
        strong_eligible=closed,
        first_missing_link=first_missing,
        missing_claim_groups=tuple(missing_groups),
        missing_surfaces=missing_surfaces,
    )
```

- [ ] **Step 4: Run profile tests**

Run:

```powershell
python -m pytest tests/test_strong_closure_profiles.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add src/hsconfig/strong_closure_profiles.py tests/test_strong_closure_profiles.py
git commit -m "feat: add source-backed closure profiles"
```

---

### Task 2: Wire Profiles Into Strong Promotion Summary

**Files:**
- Modify: `src/hsconfig/operator_summary.py`
- Test: `tests/test_source_backed_strong_harvester_closure.py`
- Test: `tests/test_operator_summary.py`

**Interfaces:**
- Consumes:
  - `evaluate_closure_profile(...) -> ClosureProfileVerdict`
- Produces:
  - `operator_summary.json["source_backed_strong_closure"]["closure_profile"]`
  - `operator_summary.json["source_backed_strong_closure"]["closure_profile_closed"]`
  - `operator_summary.json["source_backed_strong_closure"]["closure_profile_first_missing_link"]`

- [ ] **Step 1: Add failing operator summary test for Aggro profile closure**

Append to `tests/test_source_backed_strong_harvester_closure.py`:

```python
def test_current_shadowpriest_guide_can_close_aggro_profile_without_extra_apply_surface(tmp_path):
    package_dir = prepare_fixture_package(
        tmp_path,
        deck_name="ShadowPriest",
        source_documents_fixture="source_documents_shadowpriest_strong.json",
    )

    summary = read_json(package_dir / "reports" / "operator_summary.json")

    assert summary["semantic_status"] == "SOURCE_BACKED_STRONG"
    closure = summary["source_backed_strong_closure"]
    assert closure["closure_profile"] == "aggro_burn_hero_power"
    assert closure["closure_profile_closed"] is True
    assert closure["closure_profile_first_missing_link"] == "none"
    assert closure["default_only_runtime_surfaces"] == []
```

If the helper names differ in the file, reuse the existing fixture helper from that test file and keep the same assertions.

- [ ] **Step 2: Run test to verify current conservative failure**

Run:

```powershell
python -m pytest tests/test_source_backed_strong_harvester_closure.py::test_current_shadowpriest_guide_can_close_aggro_profile_without_extra_apply_surface -q
```

Expected: fail because the existing logic still reports `SOURCE_BACKED_PARTIAL` or `add_runtime_lowerable_apply_surface_source`.

- [ ] **Step 3: Add profile verdict to operator summary inputs**

In `src/hsconfig/operator_summary.py`, import:

```python
from hsconfig.strong_closure_profiles import evaluate_closure_profile
```

Near the source-backed closure summary builder, compute:

```python
profile_verdict = evaluate_closure_profile(
    archetype_bucket=str(gameplan.get("archetype_bucket") or gameplan.get("archetype") or ""),
    primary_mechanics=gameplan.get("primary_mechanics") or [],
    source_claim_kinds=[
        str(row.get("claim_kind") or "")
        for row in source_claim_rows
        if row.get("promotion_eligible") is True
    ],
    emitted_surfaces=runtime_files,
    default_only_surfaces=default_only_runtime_surfaces,
    suppressed_claim_kinds=[
        str(row.get("claim_kind") or "")
        for row in source_claim_rows
        if row.get("suppressed") is True or row.get("runtime_lowering") == "suppressed"
    ],
)
```

If local variable names differ, adapt the names to the existing summary structures without changing their meaning:

- `gameplan`: existing deck/gameplan summary dictionary.
- `source_claim_rows`: existing normalized claim/explainability rows.
- `runtime_files`: emitted runtime filenames.
- `default_only_runtime_surfaces`: existing default-only list.

- [ ] **Step 4: Merge profile verdict into `source_backed_strong_closure`**

In the existing `source_backed_strong_closure` dictionary, add:

```python
"closure_profile": profile_verdict.profile_name,
"closure_profile_closed": profile_verdict.closed,
"closure_profile_first_missing_link": profile_verdict.first_missing_link,
"closure_profile_missing_claim_groups": list(profile_verdict.missing_claim_groups),
"closure_profile_missing_surfaces": list(profile_verdict.missing_surfaces),
"closure_profile_apply_blocking": profile_verdict.apply_blocking,
```

- [ ] **Step 5: Use profile closure in semantic status without creating an apply gate**

Update the semantic status decision so `SOURCE_BACKED_STRONG` can be returned when all existing hard source quality conditions are satisfied and `profile_verdict.strong_eligible is True`.

Do not change `_runtime_apply_contract()` and do not add profile status to apply gating.

The decision must keep these exclusions:

```python
if default_only_runtime_surfaces:
    return "VALID_BUT_NOT_GUIDE_STRONG"
if source_depth_has_blocking_conflicts:
    return "VALID_BUT_NOT_GUIDE_STRONG"
if profile_verdict.strong_eligible:
    return "SOURCE_BACKED_STRONG"
return "VALID_BUT_NOT_GUIDE_STRONG"
```

Use the existing status names and existing helper flags in the file.

- [ ] **Step 6: Run focused tests**

Run:

```powershell
python -m pytest tests/test_source_backed_strong_harvester_closure.py tests/test_operator_summary.py -q
```

Expected: pass.

- [ ] **Step 7: Commit**

```powershell
git add src/hsconfig/operator_summary.py tests/test_source_backed_strong_harvester_closure.py tests/test_operator_summary.py
git commit -m "feat: use closure profiles for strong promotion"
```

---

### Task 3: Relax Source Autopilot First-Missing Link With Profiles

**Files:**
- Modify: `src/hsconfig/source_autopilot.py`
- Test: `tests/test_source_backed_strong_harvester_closure.py`
- Test: `tests/test_source_autopilot.py`

**Interfaces:**
- Consumes:
  - `evaluate_closure_profile(...)`
- Produces:
  - Profile-aware `first_missing_source_action`
  - No blanket `add_runtime_lowerable_apply_surface_source` for aggro decks whose profile is already closed by Mulligan, posture, targeting, and static effect semantics.

- [ ] **Step 1: Add failing source-autopilot test**

Append to `tests/test_source_autopilot.py`:

```python
def test_source_autopilot_does_not_require_extra_non_mulligan_surface_when_profile_closed():
    report = run_source_autopilot_fixture("source_search_shadowpriest_2026.json")

    assert report["semantic_status"] == "SOURCE_BACKED_STRONG"
    assert report["first_missing_source_action"] == "none"
    assert report["source_backed_strong_closure"]["closure_profile"] == "aggro_burn_hero_power"
    assert report["source_backed_strong_closure"]["closure_profile_closed"] is True
```

Use the existing fixture helper in `tests/test_source_autopilot.py`; if the helper returns `(source_documents, report)`, assert against the report object.

- [ ] **Step 2: Run test to verify failure**

Run:

```powershell
python -m pytest tests/test_source_autopilot.py::test_source_autopilot_does_not_require_extra_non_mulligan_surface_when_profile_closed -q
```

Expected: fail with current `add_runtime_lowerable_apply_surface_source` behavior.

- [ ] **Step 3: Replace blanket apply-surface check**

In `src/hsconfig/source_autopilot.py`, find the logic that excludes `mulligan_keep`, `mulligan_discard`, and `hero_power_transform` from the apply-surface test.

Replace the final missing-action decision with:

```python
profile_verdict = evaluate_closure_profile(
    archetype_bucket=archetype_bucket,
    primary_mechanics=primary_mechanics,
    source_claim_kinds=promotion_eligible_claim_kinds,
    emitted_surfaces=expected_emitted_surfaces,
    default_only_surfaces=default_only_runtime_surfaces,
    suppressed_claim_kinds=suppressed_claim_kinds,
)

if profile_verdict.closed:
    first_missing_source_action = "none"
else:
    first_missing_source_action = _action_from_profile_gap(profile_verdict.first_missing_link)
```

Add helper in the same file:

```python
def _action_from_profile_gap(first_missing_link: str) -> str:
    if first_missing_link == "none":
        return "none"
    if first_missing_link.startswith("default_only_surface:"):
        return "replace_default_only_surface_with_source_or_policy_row"
    if "mulligan_keep|mulligan_discard" in first_missing_link:
        return "add_current_mulligan_keep_or_discard_source"
    if "targeting_rule" in first_missing_link:
        return "add_current_targeting_or_card_behavior_source"
    if "combo_sequence" in first_missing_link:
        return "add_current_combo_sequence_source"
    if first_missing_link.startswith("missing_surface:"):
        return "emit_or_explain_missing_runtime_surface"
    return "add_current_card_specific_runtime_source"
```

Use existing variable names where available and keep old warning fields in the report for compatibility.

- [ ] **Step 4: Run focused source autopilot tests**

Run:

```powershell
python -m pytest tests/test_source_autopilot.py tests/test_source_backed_strong_harvester_closure.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```powershell
git add src/hsconfig/source_autopilot.py tests/test_source_autopilot.py tests/test_source_backed_strong_harvester_closure.py
git commit -m "fix: make source autopilot profile-aware"
```

---

### Task 4: Update 11-Deck Matrix Expectations

**Files:**
- Modify: `docs/operator/archetype-fixture-matrix.json`
- Modify: `tests/test_universal_wild_no_block_matrix.py`
- Modify: `tests/test_no_default_only_semantic_archetype_matrix.py`
- Test: existing 11-deck fixture tests

**Interfaces:**
- Consumes:
  - `closure_profile` values from Task 1.
- Produces:
  - Matrix entries with `closure_profile`, `closure_profile_required_claims`, and `closure_profile_first_missing_link`.

- [ ] **Step 1: Add failing matrix assertion**

In `tests/test_universal_wild_no_block_matrix.py`, add:

```python
def test_every_matrix_deck_declares_closure_profile():
    matrix = load_archetype_fixture_matrix()

    for deck in matrix["decks"]:
        assert deck["closure_profile"]
        assert "closure_profile_first_missing_link" in deck
        assert deck["runtime_apply_allowed"] is True
```

Use the existing matrix loader function in that file.

- [ ] **Step 2: Run matrix test to verify failure**

Run:

```powershell
python -m pytest tests/test_universal_wild_no_block_matrix.py::test_every_matrix_deck_declares_closure_profile -q
```

Expected: fail because current JSON does not yet expose closure profile fields for every deck.

- [ ] **Step 3: Update matrix JSON**

For each deck in `docs/operator/archetype-fixture-matrix.json`, add these fields:

```json
"closure_profile": "aggro_burn_hero_power",
"closure_profile_first_missing_link": "none"
```

Use this mapping:

- `ShadowPriest`: `aggro_burn_hero_power`, first missing `none`
- `CtAPaladin`: `board_flood_recruit`, first missing `missing_claim_group:mulligan_keep|mulligan_discard|card_role`
- `PirateRogue`: `weapon_pressure`, first missing `none`
- `BigShaman`: `board_flood_recruit`, first missing `none`
- `Discolock`: `combo_setup`, first missing `missing_claim_group:mulligan_keep|mulligan_discard|card_role`
- `TreantDruid`: `board_flood_recruit`, first missing `missing_claim_group:mulligan_keep|mulligan_discard|card_role`
- `ImbueMage`: `aggro_burn_hero_power`, first missing `none`
- `MechPala`: `board_flood_recruit`, first missing `none`
- `Kingslayer`: `weapon_pressure`, first missing `missing_claim_group:mulligan_keep|mulligan_discard|card_role`
- `Boarlock`: `combo_setup`, first missing `missing_claim_group:combo_sequence|card_role`
- `PirateDH`: `weapon_pressure`, first missing `missing_claim_group:mulligan_keep|mulligan_discard|card_role`

Keep existing `expected_semantic_status` values unless Task 3 changed a fixture's actual status through profile closure. If a deck remains partial, preserve the existing `first_missing_source_action`.

- [ ] **Step 4: Enforce no default-only with profile fields**

In `tests/test_no_default_only_semantic_archetype_matrix.py`, add:

```python
def test_profile_strong_rows_do_not_have_default_only_surfaces():
    matrix = load_archetype_fixture_matrix()

    for deck in matrix["decks"]:
        if deck.get("expected_semantic_status") == "SOURCE_BACKED_STRONG":
            assert deck.get("default_only_runtime_surfaces") == []
            assert deck.get("closure_profile_first_missing_link") == "none"
```

Use the existing matrix loader helper.

- [ ] **Step 5: Run matrix tests**

Run:

```powershell
python -m pytest tests/test_universal_wild_no_block_matrix.py tests/test_no_default_only_semantic_archetype_matrix.py -q
```

Expected: pass.

- [ ] **Step 6: Commit**

```powershell
git add docs/operator/archetype-fixture-matrix.json tests/test_universal_wild_no_block_matrix.py tests/test_no_default_only_semantic_archetype_matrix.py
git commit -m "docs: expose closure profiles in archetype matrix"
```

---

### Task 5: Preserve Darkbishop Effect-Not-Mulligan Canary

**Files:**
- Modify: `tests/test_shadowpriest_e2e.py`
- Modify: `tests/test_claim_kind_runtime_contract.py`
- Modify only if needed: `src/hsconfig/source_document_model.py`
- Modify only if needed: `src/hsconfig/autonomous_mulligan_policy.py`

**Interfaces:**
- Consumes:
  - Existing `can_lower_to_mulligan(...)`
  - Existing policy-backed Mulligan fallback
- Produces:
  - Regression proof that `SOURCE_BACKED_STRONG` does not make `SW_448` a Mulligan keep.

- [ ] **Step 1: Add failing/protective E2E assertion**

In `tests/test_shadowpriest_e2e.py`, add or tighten:

```python
def test_source_backed_strong_shadowpriest_keeps_benedictus_effect_not_opening_hand(tmp_path):
    package_dir = prepare_shadowpriest_fixture(tmp_path)

    mulligan = read_json(package_dir / "runtime" / "Mulligan.json")
    benedictus_behavior = read_json(package_dir / "runtime" / "SW_448.json")
    summary = read_json(package_dir / "reports" / "operator_summary.json")

    assert summary["semantic_status"] == "SOURCE_BACKED_STRONG"
    assert "SW_448" not in str(mulligan)
    assert "hero_power_transform" in str(benedictus_behavior) or "BeforeUseHeroPowerBonus" in str(benedictus_behavior)
```

Use the existing ShadowPriest fixture helper and exact runtime path names from that file.

- [ ] **Step 2: Run canary tests**

Run:

```powershell
python -m pytest tests/test_shadowpriest_e2e.py tests/test_claim_kind_runtime_contract.py -q
```

Expected: pass. If it fails because profile Strong promotion leaked `SW_448` into Mulligan, proceed to Step 3.

- [ ] **Step 3: Fix only if canary fails**

If needed, ensure `src/hsconfig/source_document_model.py` keeps this logic:

```python
if claim_kind in MULLIGAN_SURFACE_CLAIM_KINDS and _is_start_of_game_non_hand_effect(claim):
    if not has_explicit_opening_hand_mulligan_intent(claim):
        return SurfaceGateDecision(
            allowed=False,
            reason="start_of_game_effect_does_not_require_opening_hand",
            claim_kind=claim_kind,
            surface="Mulligan.json",
        )
```

If policy fallback is responsible, ensure `src/hsconfig/autonomous_mulligan_policy.py` excludes cards with `START_OF_GAME_NON_HAND_EFFECT_ROLES`.

- [ ] **Step 4: Re-run canary tests**

Run:

```powershell
python -m pytest tests/test_shadowpriest_e2e.py tests/test_claim_kind_runtime_contract.py tests/test_autonomous_mulligan_policy.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```powershell
git add tests/test_shadowpriest_e2e.py tests/test_claim_kind_runtime_contract.py src/hsconfig/source_document_model.py src/hsconfig/autonomous_mulligan_policy.py
git commit -m "test: preserve darkbishop effect not mulligan canary"
```

If no source files changed, only add the test files.

---

### Task 6: Surface Profile Closure In Reports And Skill Guidance

**Files:**
- Modify: `src/hsconfig/source_evidence_closure.py`
- Modify: `.agents/skills/hsconfig/SKILL.md`
- Modify: `C:\Users\darbo\.codex\skills\hsconfig\SKILL.md`
- Test: `tests/test_source_evidence_closure.py`
- Test: `tests/test_skill_sync.py`

**Interfaces:**
- Consumes:
  - `source_backed_strong_closure` from operator summary.
- Produces:
  - Compact report fields:
    - `closure_profile`
    - `closure_profile_closed`
    - `closure_profile_first_missing_link`

- [ ] **Step 1: Add failing report test**

In `tests/test_source_evidence_closure.py`, add:

```python
def test_source_evidence_closure_reports_profile_verdict(tmp_path):
    package_dir = prepare_fixture_package(
        tmp_path,
        deck_name="ShadowPriest",
        source_documents_fixture="source_documents_shadowpriest_strong.json",
    )

    report = read_json(package_dir / "reports" / "source_evidence_closure.json")

    assert report["closure_profile"] == "aggro_burn_hero_power"
    assert report["closure_profile_closed"] is True
    assert report["closure_profile_first_missing_link"] == "none"
```

Use local helper names already present in the test file.

- [ ] **Step 2: Run report test to verify failure**

Run:

```powershell
python -m pytest tests/test_source_evidence_closure.py::test_source_evidence_closure_reports_profile_verdict -q
```

Expected: fail because compact report does not expose profile fields yet.

- [ ] **Step 3: Add profile fields to compact closure report**

In `src/hsconfig/source_evidence_closure.py`, copy these fields from operator summary when available:

```python
strong_closure = operator_summary.get("source_backed_strong_closure") or {}
report["closure_profile"] = strong_closure.get("closure_profile", "unknown")
report["closure_profile_closed"] = bool(strong_closure.get("closure_profile_closed", False))
report["closure_profile_first_missing_link"] = strong_closure.get(
    "closure_profile_first_missing_link",
    "unknown",
)
```

- [ ] **Step 4: Update skill guidance**

In both `.agents/skills/hsconfig/SKILL.md` and `C:\Users\darbo\.codex\skills\hsconfig\SKILL.md`, add this concise rule near the Strong/source-depth section:

```markdown
- Strong closure is profile-aware: Aggro/Burn, Hero Power, Weapon, Combo, Board-Flood/Recruit, and generic decks close different source-to-runtime lanes. A profile can make explicit Mulligan plus posture plus supported CardID/static semantics sufficient for `SOURCE_BACKED_STRONG`; decklist-only, stats, policy fallback, default runtime, and unsupported runtime hints still cannot promote.
```

- [ ] **Step 5: Run report and skill sync tests**

Run:

```powershell
python -m pytest tests/test_source_evidence_closure.py tests/test_skill_sync.py -q
```

Expected: pass.

- [ ] **Step 6: Commit**

```powershell
git add src/hsconfig/source_evidence_closure.py .agents/skills/hsconfig/SKILL.md C:\Users\darbo\.codex\skills\hsconfig\SKILL.md tests/test_source_evidence_closure.py tests/test_skill_sync.py
git commit -m "docs: document profile-aware strong closure"
```

---

### Task 7: Final Verification And Sharp ShadowPriest Dry Run

**Files:**
- No source changes expected.
- Output artifacts may be generated under an ignored `outputs/` or temp test path only.

**Interfaces:**
- Consumes:
  - All previous tasks.
- Produces:
  - Verified plan completion.
  - Fresh ShadowPriest package proof without changing runtime unless explicitly passed `--apply`.

- [ ] **Step 1: Run focused suite**

Run:

```powershell
python -m pytest tests/test_strong_closure_profiles.py tests/test_source_backed_strong_harvester_closure.py tests/test_source_autopilot.py tests/test_no_default_only_semantic_archetype_matrix.py tests/test_universal_wild_no_block_matrix.py tests/test_claim_kind_runtime_contract.py tests/test_shadowpriest_e2e.py tests/test_source_evidence_closure.py -q
```

Expected: all pass.

- [ ] **Step 2: Run broader suite**

Run:

```powershell
python -m pytest -q
```

Expected: all pass.

- [ ] **Step 3: Run CLI help smoke test**

Run:

```powershell
python -m hsconfig --help
python -m hsconfig configure --help
```

Expected: both commands exit `0`; `configure` remains the preferred one-command path.

- [ ] **Step 4: Run ShadowPriest preview without runtime apply**

Run:

```powershell
$out = "outputs\shadowpriest-profile-closure-preview"
Remove-Item -Recurse -Force $out -ErrorAction SilentlyContinue
python -m hsconfig configure `
  --deck-name "ShadowPriest" `
  --deck-code "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=" `
  --out $out `
  --auto-source `
  --source-search-results-json "tests\fixtures\source_search_shadowpriest_2026.json" `
  --json
```

Expected:

- command exits `0`
- `$out\reports\operator_summary.json` exists
- `semantic_status` is `SOURCE_BACKED_STRONG`
- `source_backed_strong_closure.closure_profile` is `aggro_burn_hero_power`
- `source_backed_strong_closure.closure_profile_first_missing_link` is `none`
- `default_only_runtime_surfaces` is `[]`
- `Mulligan.json` does not keep `SW_448`
- `SW_448.json` exists and preserves hero-power/Mind Spike behavior

- [ ] **Step 5: Inspect generated reports**

Run:

```powershell
python - <<'PY'
import json
from pathlib import Path

out = Path("outputs/shadowpriest-profile-closure-preview")
summary = json.loads((out / "reports/operator_summary.json").read_text(encoding="utf-8"))
print(summary["technical_status"])
print(summary["semantic_status"])
print(summary["source_backed_strong_closure"]["closure_profile"])
print(summary["source_backed_strong_closure"]["closure_profile_first_missing_link"])
print(summary.get("default_only_runtime_surfaces"))
PY
```

Expected output lines:

```text
VALID_PACKAGE
SOURCE_BACKED_STRONG
aggro_burn_hero_power
none
[]
```

- [ ] **Step 6: Clean generated preview if not intended as fixture**

Run:

```powershell
Remove-Item -Recurse -Force "outputs\shadowpriest-profile-closure-preview"
```

Expected: working tree has no generated output artifacts.

- [ ] **Step 7: Final git status**

Run:

```powershell
git status --short --branch
```

Expected: branch is clean after commits, or only intended plan/task changes remain staged for final commit.

- [ ] **Step 8: Commit final verification notes only if docs changed**

If a docs note or test fixture update was added during final verification:

```powershell
git add <changed-files>
git commit -m "test: verify profile-aware strong closure"
```

Otherwise do not create an empty commit.

---

## Self-Review

- Spec coverage: This plan covers profile-aware Strong promotion, no default-only visibility, no-block valid packages, Darkbishop effect-not-mulligan, 11-deck matrix, compact operator/report visibility, and skill sync.
- Placeholder scan: No placeholder markers or unspecified "add tests" steps remain.
- Type consistency: The new public interface is limited to `ClosureProfileRequirement`, `ClosureProfileVerdict`, `profile_for_archetype`, and `evaluate_closure_profile`.
- Scope check: The plan intentionally excludes replay analysis, winrate, broad source scraping, browser automation, and HSTuner behavior.
- Risk: Some helper names in existing tests may differ; task steps explicitly require reusing existing local helpers while preserving the exact assertions.

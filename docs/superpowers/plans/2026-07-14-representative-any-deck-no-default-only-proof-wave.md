# Representative Any-Deck No-Default-Only Proof Wave Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove and harden that HSConfig can generate a load-safe, non-default-only HearthRanger CustomConfig package for representative Wild decks while preserving strict source/contract/runtime-surface boundaries.

**Architecture:** Keep the current two-lane design: technical load safety decides apply, while source/semantic richness stays diagnostic unless a claim is eligible for a documented runtime surface. This wave adds representative any-deck proof and micro-hardens boundary reports; it does not add HSTuner-style replay parsing, winrate validation, candidate promotion, or post-run tuning.

**Tech Stack:** Python 3, pytest, local HSConfig CLI, existing `hsconfig` package modules, JSON fixtures, HearthRanger VisionAI runtime JSON surfaces.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig` for `Teufelsboy/HSConfig`.
- Keep HSConfig separate from HSTuner; do not add replay parsing, HDT parsing, winrate validation, candidate promotion, or post-run tuning.
- Generated runtime packages stay under ignored `outputs/` or pytest `tmp_path`; do not commit generated package outputs.
- Preserve exact deck and CardID identity.
- Preserve full `GlobalValues.json` key profiling.
- Preserve every card covered in the gameplan contract.
- Preserve strict JSON validation.
- Preserve row-level provenance for generated config rows.
- Do not create a second apply gate; `reports/operator_summary.json` remains the only runtime-apply authority.
- Source richness, source gaps, weak semantics, unknown mechanics, report-only claims, and runtime-evidence-required claims must never hard-block a load-safe package.
- Normal HSConfig runtime surfaces remain narrow: `GlobalValues.json`, `Mulligan.json`, per-card `<CARDID>.json`, and `Combo.json` only for concrete valid sequences.
- Normal path must not emit `Presume.json` or `Concede.json`.
- `SOURCE_BACKED_STRONG` is a source-confidence label, not a runtime-apply gate.
- `policy_backed_autonomous_mulligan` may prevent default-only output, but must not be promoted to `SOURCE_BACKED_STRONG`.
- Start-of-game, deckbuilding, hero-power-transform, generated-random-pool, unresolved choice identity, and runtime-only numeric tuning must not be falsely lowered into the wrong runtime surface.

---

## File Structure

- Modify `tests/test_universal_wild_no_block_matrix.py`: expand the existing real-deck matrix and add stronger package invariants for default-only prevention and per-card coverage.
- Create `tests/test_no_default_only_semantic_archetype_matrix.py`: synthetic representative mechanic/archetype proof where exact deck strings are not required.
- Modify `tests/test_semantic_runtime_negative_boundaries.py`: add missing false-lowering boundary cases.
- Modify `tests/test_source_claim_gap_report.py`: assert first-missing-link precision for suppressed runtime claims.
- Modify `src/hsconfig/autonomous_mulligan_policy.py`: only if tests expose lane gaps; keep the change limited to lane token selection and exclusion reasons.
- Modify `src/hsconfig/source_document_model.py`: only if tests expose surface-gate gaps; keep the change limited to explicit `GateDecision` reasons.
- Modify `src/hsconfig/card_behavior_surface_router.py`: only if tests expose unsupported surface lowering; keep unsupported mechanics diagnostic-only.
- Modify `src/hsconfig/source_claim_gap_report.py`: only if first-missing-link rows are missing or too vague.
- Modify `src/hsconfig/operator_summary.py`: only if `default_only_runtime_surfaces` or `mulligan_policy_status` is missing from an operator-facing report.
- Modify `docs/operator/guide-research-policy.md`: update only the short active contract language.
- Modify `docs/operator/universal-wild-no-block-contract.md`: add the representative proof matrix and non-blocking semantics.
- Modify `.agents/skills/hsconfig/SKILL.md` and synced installed skill only if active operator wording is stale.

---

### Task 1: Expand Real-Deck No-Default-Only Matrix

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_universal_wild_no_block_matrix.py`

**Interfaces:**
- Consumes: `hsconfig.cli.main(argv: list[str]) -> int`
- Consumes: existing `DECKS: list[tuple[str, str]]`
- Produces: stronger test guarantees for `operator_summary.json`, `source_contract_audit.json`, `deck_identity.json`, and generated `CustomConfig/<DECK>/`

- [ ] **Step 1: Write the failing matrix expansion test**

Add helper assertions below `assert_load_safe_no_block_package`:

```python
def assert_no_default_only_runtime_surfaces(operator: dict) -> None:
    assert operator["default_only_runtime_surfaces"] == []
    mulligan_policy = operator["mulligan_policy_status"]
    assert mulligan_policy["default_only"] is False
    assert mulligan_policy["status"] in {"policy_backed", "source_backed", "source_and_policy_backed"}
    assert isinstance(mulligan_policy.get("policy_lanes", []), list)
    assert isinstance(mulligan_policy.get("policy_reasons", []), list)


def assert_runtime_surface_shape(deck_dir: Path, deck_card_ids: set[str]) -> None:
    special_files = {"Combo.json", "GlobalValues.json", "Mulligan.json"}
    card_files = {
        path.stem
        for path in deck_dir.glob("*.json")
        if path.name not in special_files
    }
    assert (deck_dir / "GlobalValues.json").is_file()
    assert (deck_dir / "Mulligan.json").is_file()
    assert card_files == deck_card_ids
    assert not (deck_dir / "Presume.json").exists()
    assert not (deck_dir / "Concede.json").exists()
```

Then replace duplicated inline assertions in `test_valid_wild_deck_produces_load_safe_warning_apply_package` with:

```python
assert_no_default_only_runtime_surfaces(operator)
assert_runtime_surface_shape(deck_dir, deck_card_ids)
```

- [ ] **Step 2: Run the focused test and verify the current behavior**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_universal_wild_no_block_matrix.py -q
```

Expected before implementation: either PASS if the current matrix already satisfies the stronger contract, or FAIL only on missing `mulligan_policy_status` detail such as `status`, `policy_lanes`, or `policy_reasons`.

- [ ] **Step 3: Implement the minimal report shaping if needed**

If the focused test fails because `mulligan_policy_status` is missing stable keys, modify only the operator-summary creation path in `C:\Users\darbo\Documents\HSConfig\src\hsconfig\operator_summary.py` so the emitted object always contains:

```python
{
    "default_only": False,
    "status": "policy_backed",
    "policy_lanes": [],
    "policy_reasons": [],
}
```

Use real values from the existing package reports where available. Do not infer `SOURCE_BACKED_STRONG` from policy fallback.

- [ ] **Step 4: Re-run the focused test**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_universal_wild_no_block_matrix.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit the matrix hardening**

Run:

```powershell
git add tests/test_universal_wild_no_block_matrix.py src/hsconfig/operator_summary.py
git commit -m "test: harden no-default-only real deck matrix"
```

If `src/hsconfig/operator_summary.py` was not changed, omit it from `git add`.

---

### Task 2: Add Synthetic Representative Semantic Archetype Matrix

**Files:**
- Create: `C:\Users\darbo\Documents\HSConfig\tests\test_no_default_only_semantic_archetype_matrix.py`

**Interfaces:**
- Consumes: `hsconfig.cli.main(argv: list[str]) -> int`
- Produces: a fast synthetic fixture matrix that covers representative Wild mechanics without depending on more public deckstrings

Synthetic CardIDs in this fixture contract must satisfy the runtime VisionAI
surface grammar: per-card JSON filenames must contain at least one digit. The
matrix therefore uses `SECRET_001`, `TEMPO_001`, `LOCATION_001`, and the other
digit-bearing IDs below. Do not weaken the validator to accept digitless
synthetic IDs.

- [ ] **Step 1: Create the failing synthetic matrix test**

Create `tests/test_no_default_only_semantic_archetype_matrix.py` with this content:

```python
import json
from pathlib import Path

import pytest

from hsconfig.cli import main


SEMANTIC_ARCHETYPE_FIXTURES = [
    {
        "deck_name": "SyntheticSecretHunter",
        "cards": [
            {"card_id": "SECRET_001", "name": "Secret Opener", "cost": 1, "type": "SPELL", "text": "Secret: fixture.", "mechanics": ["SECRET"]},
            {"card_id": "TEMPO_001", "name": "Tempo One", "cost": 1, "type": "MINION", "text": "Battlecry: deal damage.", "mechanics": ["BATTLECRY"]},
        ],
        "claims": [
            {"claim_id": "tempo_keep", "claim_kind": "mulligan_keep", "card_id": "TEMPO_001", "evidence_text_short": "Keep early pressure.", "source_confidence": "guide_backed"},
            {"claim_id": "secret_visible", "claim_kind": "mechanic_usage", "card_id": "SECRET_001", "mechanic": "secret", "evidence_text_short": "Secrets are part of the gameplan.", "source_confidence": "guide_backed"},
        ],
    },
    {
        "deck_name": "SyntheticLocationDruid",
        "cards": [
            {"card_id": "LOCATION_001", "name": "Location Fixture", "cost": 2, "type": "LOCATION", "text": "Summon two minions."},
            {"card_id": "BOARD_001", "name": "Board One", "cost": 1, "type": "MINION", "text": "Summon a Treant."},
        ],
        "claims": [
            {"claim_id": "board_keep", "claim_kind": "mulligan_keep", "card_id": "BOARD_001", "evidence_text_short": "Keep board opener.", "source_confidence": "guide_backed"},
            {"claim_id": "location_visible", "claim_kind": "mechanic_usage", "card_id": "LOCATION_001", "mechanic": "location", "evidence_text_short": "Location supports board plan.", "source_confidence": "guide_backed"},
        ],
    },
    {
        "deck_name": "SyntheticDiscoverMage",
        "cards": [
            {"card_id": "DISCOVER_001", "name": "Discover One", "cost": 2, "type": "SPELL", "text": "Discover a spell."},
            {"card_id": "BURN_001", "name": "Burn One", "cost": 1, "type": "SPELL", "text": "Deal damage."},
        ],
        "claims": [
            {"claim_id": "burn_keep", "claim_kind": "mulligan_keep", "card_id": "BURN_001", "evidence_text_short": "Keep cheap burn.", "source_confidence": "guide_backed"},
            {"claim_id": "discover_report_only", "claim_kind": "discover_choice", "card_id": "DISCOVER_001", "evidence_text_short": "Prefer damage from Discover.", "source_confidence": "guide_backed"},
        ],
    },
    {
        "deck_name": "SyntheticHighlanderPriest",
        "cards": [
            {"card_id": "HIGHLANDER_001", "name": "Highlander Effect", "cost": 5, "type": "MINION", "text": "Start of Game: if your deck has no duplicates, improve your hero power."},
            {"card_id": "LOW_CURVE_001", "name": "Low Curve One", "cost": 1, "type": "MINION", "text": "Battlecry: deal damage."},
        ],
        "claims": [
            {"claim_id": "highlander_effect", "claim_kind": "hero_power_transform", "card_id": "HIGHLANDER_001", "semantic_qualifiers": {"timing": "start_of_game", "zone_scope": "deck"}, "evidence_text_short": "The deckbuilding effect matters.", "source_confidence": "guide_backed"},
            {"claim_id": "curve_keep", "claim_kind": "mulligan_keep", "card_id": "LOW_CURVE_001", "evidence_text_short": "Keep the low curve opener.", "source_confidence": "guide_backed"},
        ],
    },
]


def _write_fixture(tmp_path: Path, fixture: dict) -> tuple[Path, Path]:
    cards_path = tmp_path / f"{fixture['deck_name']}_cards.json"
    cards_path.write_text(json.dumps({"cards": fixture["cards"]}), encoding="utf-8")
    sources_path = tmp_path / f"{fixture['deck_name']}_sources.json"
    sources_path.write_text(
        json.dumps(
            [
                {
                    "source_url": f"https://example.invalid/{fixture['deck_name']}",
                    "source_title": f"{fixture['deck_name']} Guide Fixture",
                    "source_family": "guide_fixture",
                    "retrieved_at": "2026-07-14T00:00:00Z",
                    "claims": fixture["claims"],
                }
            ]
        ),
        encoding="utf-8",
    )
    return cards_path, sources_path


@pytest.mark.parametrize("fixture", SEMANTIC_ARCHETYPE_FIXTURES, ids=lambda item: item["deck_name"])
def test_semantic_archetype_fixture_remains_load_safe_and_not_default_only(tmp_path, fixture):
    cards_path, sources_path = _write_fixture(tmp_path, fixture)
    out = tmp_path / fixture["deck_name"]
    exit_code = main(
        [
            "prepare",
            "--deck-name",
            fixture["deck_name"],
            "--deck-code",
            "synthetic-fixture-code",
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(out),
            "--cards-json",
            str(cards_path),
            "--guide-sources-json",
            str(sources_path),
            "--json",
        ]
    )

    reports = out / "reports"
    operator = json.loads((reports / "operator_summary.json").read_text(encoding="utf-8"))
    deck_dir = next((out / "CustomConfig").iterdir())
    mulligan = json.loads((deck_dir / "Mulligan.json").read_text(encoding="utf-8"))
    source_gap = json.loads((reports / "source_claim_gap_report.json").read_text(encoding="utf-8"))

    assert exit_code == 0
    assert operator["technical_status"] == "VALID_PACKAGE"
    assert operator["runtime_load_safe"] is True
    assert operator["runtime_apply_allowed"] is True
    assert operator["runtime_apply_mode"] == "load_safe_apply"
    assert operator["default_only_runtime_surfaces"] == []
    assert operator["mulligan_policy_status"]["default_only"] is False
    assert (deck_dir / "GlobalValues.json").is_file()
    assert (deck_dir / "Mulligan.json").is_file()
    assert not (deck_dir / "Presume.json").exists()
    assert not (deck_dir / "Concede.json").exists()
    assert mulligan["Mulligan"]["values"], "Mulligan output must not be default-only for representative archetypes"
    assert "claim_rows" in source_gap
```

- [ ] **Step 2: Run the new test to verify the current behavior**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_no_default_only_semantic_archetype_matrix.py -q
```

Expected before implementation: FAIL only if a representative fixture produces default-only runtime surfaces, empty mulligan output, or missing source-gap rows.

- [ ] **Step 3: Implement only the minimal failing branch**

If the test fails because source-backed or policy-backed mulligan rows are absent, modify `C:\Users\darbo\Documents\HSConfig\src\hsconfig\autonomous_mulligan_policy.py` only. Add role/lane support without broad behavior changes:

```python
ARCHETYPE_LANE_ROLE_HINTS["secret"] = {"secret", "tempo", "early_pressure", "damage"}
ARCHETYPE_LANE_ROLE_HINTS["location"] = {"location", "board_flood", "token_board", "early_pressure"}
ARCHETYPE_LANE_ROLE_HINTS["discover"] = {"discover", "burn_reach", "damage", "tempo_draw"}

ARCHETYPE_LANE_ROLE_RANKS["secret"] = ("early_pressure", "damage", "tempo_draw", "secret")
ARCHETYPE_LANE_ROLE_RANKS["location"] = ("early_pressure", "board_flood", "token_board", "location")
ARCHETYPE_LANE_ROLE_RANKS["discover"] = ("damage", "burn_reach", "tempo_draw", "discover")
```

If the test fails because start-of-game cards are selected, keep the existing exclusion behavior and add only the missing role token to `EXCLUDED_POLICY_ROLES`.

- [ ] **Step 4: Re-run the synthetic matrix**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_no_default_only_semantic_archetype_matrix.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit the synthetic proof matrix**

Run:

```powershell
git add tests/test_no_default_only_semantic_archetype_matrix.py src/hsconfig/autonomous_mulligan_policy.py
git commit -m "test: prove no-default-only semantic archetype fixtures"
```

If `src/hsconfig/autonomous_mulligan_policy.py` was not changed, omit it from `git add`.

---

### Task 3: Harden False-Lowering Boundaries

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_semantic_runtime_negative_boundaries.py`
- Modify if needed: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\source_document_model.py`
- Modify if needed: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\card_behavior_surface_router.py`

**Interfaces:**
- Consumes: `can_lower_to_mulligan(claim: dict, card_roles: Mapping[str, Any]) -> GateDecision`
- Consumes: `can_lower_to_globalvalues(claim: dict) -> GateDecision`
- Consumes: `surface_gate_decision(claim: dict, surface: str) -> GateDecision`
- Consumes: `route_card_behavior_surfaces(claims: list[dict], identity_links: dict) -> dict`
- Produces: explicit guardrails for semantic ambiguity and unsupported mechanics

- [ ] **Step 1: Add failing negative-boundary test cases**

Append these tests to `tests/test_semantic_runtime_negative_boundaries.py`:

```python
def test_deckbuilding_effect_without_hand_relevance_never_lowers_to_mulligan():
    claim = {
        "claim_id": "deckbuilding_only_keep_error",
        "claim_kind": "mulligan_keep",
        "claim_readiness": "guide_backed",
        "cards": ["DECKBUILDING_CARD"],
        "semantic_qualifiers": {
            "timing": "start_of_game",
            "zone_scope": "deck",
            "state_requirements": ["deckbuilding_effect"],
        },
    }

    decision = can_lower_to_mulligan(
        claim,
        card_roles={
            "DECKBUILDING_CARD": {
                "roles": ["deckbuilding_modifier", "start_of_game"],
                "semantic_families": ["deckbuilding_effect", "start_of_game"],
            }
        },
    )

    assert decision.allowed is False
    assert decision.reason == "start_of_game_effect_does_not_require_opening_hand"


def test_generated_random_pool_is_report_visible_not_cardid_behavior():
    claim = {
        "claim_id": "random_pool_lowering_error",
        "claim_kind": "mechanic_usage",
        "claim_readiness": "guide_backed",
        "cards": ["RANDOM_GENERATOR"],
        "mechanic": "generated_entity_random_pool",
        "evidence_text_short": "Generated random minions are valuable.",
    }

    result = route_card_behavior_surfaces([claim], identity_links={})

    assert result["rows"] == []
    assert result["suppressed"][0]["claim_id"] == "random_pool_lowering_error"
    assert result["suppressed"][0]["reason"] == "requires_supported_cardid_surface"
    assert result["suppressed"][0]["lowering_policy"] == "report_only"


def test_choice_claim_with_unresolved_option_identity_stays_diagnostic():
    claim = {
        "claim_id": "choose_option_without_identity",
        "claim_kind": "choose_one_choice",
        "claim_readiness": "guide_backed",
        "cards": ["CHOOSE_ONE_CARD"],
        "option_card_id": "UNRESOLVED_OPTION",
    }

    decision = surface_gate_decision(claim, "card_behavior")
    routed = route_card_behavior_surfaces([claim], identity_links={})

    assert decision.allowed is False
    assert decision.reason in {"requires_exact_option_identity", "unresolved_option_identity"}
    assert routed["rows"] == []
    assert routed["suppressed"][0]["claim_id"] == "choose_option_without_identity"
```

- [ ] **Step 2: Run the boundary test**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_semantic_runtime_negative_boundaries.py -q
```

Expected before implementation: FAIL only for missing explicit reason handling; PASS is acceptable if the current code already covers the boundary.

- [ ] **Step 3: Implement missing explicit gate reasons**

If needed, modify `src/hsconfig/source_document_model.py` so `surface_gate_decision()` rejects `discover_choice` and `choose_one_choice` on `card_behavior` unless option identity is resolved upstream. Use an explicit reason:

```python
return GateDecision(False, "requires_exact_option_identity")
```

If needed, modify `src/hsconfig/card_behavior_surface_router.py` so unsupported `mechanic_usage` claims return suppressed rows with:

```python
{
    "reason": "requires_supported_cardid_surface",
    "lowering_policy": "report_only",
}
```

- [ ] **Step 4: Re-run the boundary test**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_semantic_runtime_negative_boundaries.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit boundary hardening**

Run:

```powershell
git add tests/test_semantic_runtime_negative_boundaries.py src/hsconfig/source_document_model.py src/hsconfig/card_behavior_surface_router.py
git commit -m "test: harden semantic false-lowering boundaries"
```

Omit unchanged implementation files from `git add`.

---

### Task 4: Make First Missing Link Precise For Suppressed Claims

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_source_claim_gap_report.py`
- Modify if needed: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\source_claim_gap_report.py`

**Interfaces:**
- Consumes: source contract audit rows and guide claim rows
- Produces: `source_claim_gap_report.json` rows where every non-emitted claim has a precise first missing link

- [ ] **Step 1: Add failing first-missing-link assertions**

Add this test to `tests/test_source_claim_gap_report.py`:

```python
def test_suppressed_runtime_claims_report_first_missing_link():
    rows = [
        {
            "claim_id": "runtime_numeric",
            "claim_kind": "globalvalue_numeric_tuning",
            "builder_or_router_decision": "suppressed",
            "first_missing_link": "runtime_evidence",
            "operator_impact": "diagnostic_only",
        },
        {
            "claim_id": "unresolved_discover",
            "claim_kind": "discover_choice",
            "builder_or_router_decision": "suppressed",
            "first_missing_link": "option_identity",
            "operator_impact": "diagnostic_only",
        },
        {
            "claim_id": "future_mechanic",
            "claim_kind": "mechanic_usage",
            "builder_or_router_decision": "suppressed",
            "first_missing_link": "supported_cardid_surface",
            "operator_impact": "diagnostic_only",
        },
    ]

    for row in rows:
        assert row["builder_or_router_decision"] == "suppressed"
        assert row["first_missing_link"] in {
            "runtime_evidence",
            "option_identity",
            "supported_cardid_surface",
            "source_claim_conflict",
            "claim_kind_supported_surface",
        }
        assert row["operator_impact"] == "diagnostic_only"
```

If the existing test module already has a report builder helper, use that helper instead of this direct row assertion and assert against the built report.

- [ ] **Step 2: Run the source-gap focused test**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_source_claim_gap_report.py -q
```

Expected before implementation: FAIL only if first-missing-link values are blank, too generic, or missing for suppressed runtime claims.

- [ ] **Step 3: Implement missing-link normalization**

If needed, modify `src/hsconfig/source_claim_gap_report.py` with one small normalization helper:

```python
def normalize_first_missing_link(row: dict) -> str:
    reason = str(row.get("reason") or row.get("first_missing_link") or "")
    if reason in {"requires_runtime_evidence", "globalvalue_runtime_evidence_required"}:
        return "runtime_evidence"
    if reason in {"requires_exact_option_identity", "unresolved_option_identity"}:
        return "option_identity"
    if reason == "requires_supported_cardid_surface":
        return "supported_cardid_surface"
    if reason == "source_claim_conflict":
        return "source_claim_conflict"
    if reason:
        return reason
    return "claim_kind_supported_surface"
```

Use this only where rows are already being reported as suppressed/diagnostic. Do not change apply-gate behavior.

- [ ] **Step 4: Re-run the source-gap focused test**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_source_claim_gap_report.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit source-gap hardening**

Run:

```powershell
git add tests/test_source_claim_gap_report.py src/hsconfig/source_claim_gap_report.py
git commit -m "test: report precise first missing links"
```

Omit `src/hsconfig/source_claim_gap_report.py` if unchanged.

---

### Task 5: Refresh Active Operator Docs Without Expanding Scope

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\docs\operator\guide-research-policy.md`
- Modify: `C:\Users\darbo\Documents\HSConfig\docs\operator\universal-wild-no-block-contract.md`
- Modify if stale: `C:\Users\darbo\Documents\HSConfig\.agents\skills\hsconfig\SKILL.md`

**Interfaces:**
- Consumes: current source/contract/apply boundary
- Produces: concise active docs that match the hardened tests

- [ ] **Step 1: Add concise operator wording**

In `docs/operator/guide-research-policy.md`, ensure this exact policy is present once:

```markdown
## Source-To-Runtime Boundary

HSConfig separates technical load safety from source richness. A package may be
load-safe and apply-ready even when some guide claims remain diagnostic.
`reports/operator_summary.json` is the only apply authority.

`SOURCE_BACKED_STRONG` is a source-confidence label, not an apply gate.
`policy_backed_autonomous_mulligan` may prevent default-only output, but it does
not convert a claim into source-backed evidence.

Never lower these into runtime config unless the specific runtime surface is
documented and identity is resolved:

- start-of-game or deckbuilding effects as opening-hand mulligan keeps
- hero-power-transform effects as opening-hand mulligan keeps
- generated random pools as deterministic per-card behavior
- Discover or Choose One preference without exact option identity
- numeric GlobalValues tuning without runtime evidence
```

In `docs/operator/universal-wild-no-block-contract.md`, ensure this exact contract is present once:

```markdown
## Universal No-Block Contract

For any valid deck input, HSConfig should produce a load-safe package whenever
the runtime JSON package itself is valid. Weak source richness, unknown mechanics,
report-only claims, unresolved options, or runtime-evidence-only tuning are
operator-visible diagnostics, not hard blockers.

The package must not be default-only:

- `default_only_runtime_surfaces` is empty
- `mulligan_policy_status.default_only` is `false`
- `GlobalValues.json` exists
- `Mulligan.json` exists
- every known deck CardID gets a per-card JSON file
- normal path does not emit `Presume.json` or `Concede.json`
```

- [ ] **Step 2: Run docs scan tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_docs_active_path.py tests/test_operator_docs_contract_policy.py tests/test_skill_files.py tests/test_skill_sync.py -q
```

Expected before implementation: FAIL only if docs or installed skill wording are stale.

- [ ] **Step 3: Sync skill wording only if docs tests require it**

If `tests/test_skill_sync.py` fails, update `.agents/skills/hsconfig/SKILL.md` with the same concise source-to-runtime boundary wording and sync to the installed skill using the repo's existing skill sync script. Do not duplicate long docs in the skill.

- [ ] **Step 4: Re-run docs tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_docs_active_path.py tests/test_operator_docs_contract_policy.py tests/test_skill_files.py tests/test_skill_sync.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit docs updates**

Run:

```powershell
git add docs/operator/guide-research-policy.md docs/operator/universal-wild-no-block-contract.md .agents/skills/hsconfig/SKILL.md
git commit -m "docs: clarify source runtime boundary"
```

Omit `.agents/skills/hsconfig/SKILL.md` if unchanged.

---

### Task 6: Final Verification And Main Push

**Files:**
- No source files expected unless preceding tasks left required changes.

**Interfaces:**
- Consumes: all changes from Tasks 1-5
- Produces: verified branch state pushed to `origin/main`

- [ ] **Step 1: Run focused contract guardrails**

Run:

```powershell
python scripts\check_contract_guardrails.py
```

Expected: `OK` for installed skill sync, contract spine sentinel, and focused contract boundary tests.

- [ ] **Step 2: Run the focused HSConfig proof suite**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_universal_wild_no_block_matrix.py tests/test_no_default_only_semantic_archetype_matrix.py tests/test_semantic_runtime_negative_boundaries.py tests/test_source_claim_gap_report.py tests/test_shadowpriest_e2e.py tests/test_apply_authority_boundary.py tests/test_no_second_gate_contract.py -q
```

Expected: PASS.

- [ ] **Step 3: Run the full suite**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest -q
```

Expected: PASS.

- [ ] **Step 4: Check runtime-output cleanliness**

Run:

```powershell
git status --short --branch
```

Expected: only intentional source, test, doc, or plan files are modified before final commit; no generated package outputs under `outputs/`, `tmp/`, `.pytest_cache/`, or `__pycache__/`.

- [ ] **Step 5: Commit any remaining changes**

Run:

```powershell
git add docs/superpowers/plans/2026-07-14-representative-any-deck-no-default-only-proof-wave.md
git commit -m "docs: plan no-default-only proof wave"
```

If Tasks 1-5 were already committed separately, this commit should include only the plan file or be skipped if already committed.

- [ ] **Step 6: Push main**

Run:

```powershell
git push origin main
```

Expected: push succeeds and `git status --short --branch` returns `## main...origin/main`.

---

## Self-Review

- Spec coverage: The plan covers the recommendation: representative any-deck proof, no-default-only runtime surfaces, source/contract boundary hardening, false-lowering prevention, first-missing-link precision, lean docs, verification, and GitHub sync.
- Scope guard: The plan does not add replay parsing, HDT parsing, winrate validation, candidate promotion, post-run tuning, new normal runtime surfaces, or a second apply gate.
- Placeholder scan: No task contains unresolved placeholders or unspecified implementation work.
- Type consistency: All referenced modules and JSON keys exist in the current HSConfig architecture or are explicit test expectations to be implemented only if missing.
- Risk: Synthetic mechanic fixtures are intentionally small; they prove boundaries and no-default-only behavior, not gameplay quality. Gameplay quality remains out of HSConfig scope and belongs to HSTuner/runtime evidence.

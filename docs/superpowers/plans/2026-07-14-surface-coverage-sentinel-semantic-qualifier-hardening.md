# Surface Coverage Sentinel Semantic Qualifier Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden HSConfig so every supported runtime surface is visible in the operator ledger, every default-only detail is surface-specific, and Hearthstone effect semantics cannot become false runtime claims while valid decks remain non-blocking and apply-capable.

**Architecture:** Keep the current source-to-runtime spine: source claim -> normalized `claim_kind` -> semantic qualifiers -> lifecycle/conflict quarantine -> surface gate -> builder/router outcome -> emitted runtime row or suppression reason. `reports/operator_summary.json` remains the only normal apply authority; the new work is drift detection, diagnostic clarity, and false-lowering prevention. Do not add a new package report unless an existing report is replaced.

**Tech Stack:** Python 3, HSConfig modules under `src/hsconfig`, pytest, existing scripts `scripts/check_contract_guardrails.py` and `scripts/sync_installed_skill.py`.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig` for `Teufelsboy/HSConfig`.
- Keep HSConfig separate from HSTuner: no replay parsing, HDT parsing, winrate validation, candidate promotion, or post-run tuning.
- `outputs/` generated runtime packages stay ignored by git.
- Preserve exact deck and CardID identity.
- Preserve full `GlobalValues.json` key profiling.
- Preserve every card in the gameplan contract.
- Preserve strict JSON validation.
- Preserve row-level provenance for generated config rows.
- Keep `reports/operator_summary.json` as the only normal apply authority.
- Do not create a second apply gate.
- Do not let diagnostic reports grant or block runtime apply.
- Keep `source_contract_audit.json`, `source_to_runtime_explainability.json`, `source_claim_gap_report.json`, `contract-doctor`, `contract-spine-sentinel`, `surface_status_ledger`, and `config_usefulness` diagnostic-only.
- Default-only runtime surfaces must be visible, not silent.
- Default-only, source-depth, warning-only mechanic, closure freshness, unsupported mechanic, and weak guide evidence warnings must remain non-blocking when `technical_status=VALID_PACKAGE`.
- Do not add `Presume.json`, `Concede.json`, or aggregate `CardBehavior.json` to normal HSConfig output.
- Preserve the Darkbishop boundary generically: start-of-game, deckbuilding, and hero-power-transform effects may remain effect/CardID behavior, but they must not become `Mulligan.json` keeps without explicit opening-hand Mulligan evidence.
- No named-card exception lists.
- No new dependency.

---

## File Structure

- Modify `C:\Users\darbo\Documents\HSConfig\src\hsconfig\config_usefulness.py`
  - Add `EXPECTED_RUNTIME_SURFACES`.
  - Use it as the registry for surfaces expected in `config_usefulness["surfaces"]`.
- Modify `C:\Users\darbo\Documents\HSConfig\src\hsconfig\contract_spine_sentinel.py`
  - Add a runtime surface coverage check that compares the registry, `config_usefulness`, and `surface_status_ledger`.
  - Keep the sentinel diagnostic-only and non-blocking.
- Modify `C:\Users\darbo\Documents\HSConfig\src\hsconfig\operator_summary.py`
  - Make `default_only_runtime_surface_details` filter example cards by surface-specific runtime files.
  - Keep `surface_status_ledger` inside `operator_summary.json`; do not create `reports/surface_status_ledger.json`.
- Modify `C:\Users\darbo\Documents\HSConfig\src\hsconfig\source_semantic_qualifiers.py`
  - Extend qualifiers with `generation_scope` and `deck_evaluation`.
  - Add a helper that returns normalized qualifier values for scalar and list fields.
- Modify `C:\Users\darbo\Documents\HSConfig\src\hsconfig\source_document_model.py`
  - Use the expanded qualifiers to keep deckbuilding and generated-entity effects out of Mulligan keeps unless explicit opening-hand intent exists.
- Modify `C:\Users\darbo\Documents\HSConfig\tests\test_config_usefulness.py`
  - Add a registry-to-output surface coverage test.
- Modify `C:\Users\darbo\Documents\HSConfig\tests\test_contract_spine_sentinel.py`
  - Add clean and drift tests for runtime surface coverage.
- Modify `C:\Users\darbo\Documents\HSConfig\tests\test_operator_summary.py`
  - Add surface-specific default-only detail tests.
- Modify `C:\Users\darbo\Documents\HSConfig\tests\test_semantic_qualifiers.py`
  - Add generation/deck-evaluation qualifier normalization and false-Mulligan-lowering tests.
- Modify `C:\Users\darbo\Documents\HSConfig\tests\test_operator_docs_contract_policy.py`
  - Add a docs/skill contract test that keeps `source_to_runtime_explainability.json` as the primary card-readable repair map and `source_claim_gap_report.json` as secondary diagnostic evidence.
- Modify `C:\Users\darbo\Documents\HSConfig\docs\operator\README.md`
  - Clarify surface registry and default-only repair order.
- Modify `C:\Users\darbo\Documents\HSConfig\docs\operator\guide-research-policy.md`
  - Add the expanded semantic qualifier families and the source-to-runtime repair order.
- Modify `C:\Users\darbo\Documents\HSConfig\.agents\skills\hsconfig\SKILL.md`
  - Keep the normal path short and update qualifier wording.
  - Mark `source_claim_gap_report.json` as secondary, not the primary operator action surface.
- Modify `C:\Users\darbo\Documents\HSConfig\.agents\skills\hsconfig\references\guide-research-policy.md`
  - Keep the reference copy aligned with operator docs and avoid stale first-report guidance.
- Sync installed skill at `C:\Users\darbo\.codex\skills\hsconfig\SKILL.md`
  - Use `python scripts/sync_installed_skill.py`.
  - Do not stage the installed out-of-repo copy.

---

### Task 1: Add Runtime Surface Coverage Sentinel

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\config_usefulness.py`
- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\contract_spine_sentinel.py`
- Test: `C:\Users\darbo\Documents\HSConfig\tests\test_config_usefulness.py`
- Test: `C:\Users\darbo\Documents\HSConfig\tests\test_contract_spine_sentinel.py`

**Interfaces:**
- Consumes: `build_config_usefulness(...) -> dict[str, Any]`
- Consumes: `build_operator_summary(...) -> dict[str, Any]`
- Produces: `EXPECTED_RUNTIME_SURFACES: tuple[str, ...]`
- Produces: `report["checks"]["runtime_surface_coverage"] -> dict[str, Any]`
- Produces sentinel problem check name: `runtime_surface_coverage`

- [ ] **Step 1: Add failing config usefulness registry test**

Append this test to `tests/test_config_usefulness.py`:

```python
from hsconfig.config_usefulness import (
    EXPECTED_RUNTIME_SURFACES,
    build_config_usefulness,
)


def test_config_usefulness_surfaces_match_expected_runtime_surface_registry():
    usefulness = build_config_usefulness(
        technical_status="VALID_PACKAGE",
        semantic_status="STATIC_SEMANTICS_USABLE",
        config_readiness_summary={},
        mulligan_plan_report={
            "rules": [],
            "quality": {
                "status": "thin",
                "has_concrete_keeps": False,
            },
        },
        card_behavior_plan_report={"rows": []},
        combo_plan_report={"combos": [], "suppressed": []},
        globalvalues_profile_report={"changed_keys": [], "unchanged_keys": []},
    )

    assert tuple(sorted(usefulness["surfaces"])) == tuple(
        sorted(EXPECTED_RUNTIME_SURFACES)
    )
```

- [ ] **Step 2: Add failing sentinel clean coverage test**

Append this test to `tests/test_contract_spine_sentinel.py`:

```python
def test_contract_spine_sentinel_exposes_runtime_surface_coverage():
    report = build_contract_spine_sentinel_report()
    coverage = report["checks"]["runtime_surface_coverage"]

    assert coverage == {
        "expected_surfaces": ["cardid_behavior", "combo", "globalvalues", "mulligan"],
        "config_usefulness_surfaces": [
            "cardid_behavior",
            "combo",
            "globalvalues",
            "mulligan",
        ],
        "surface_status_ledger_surfaces": [
            "cardid_behavior",
            "combo",
            "globalvalues",
            "mulligan",
        ],
        "missing_from_config_usefulness": [],
        "missing_from_surface_status_ledger": [],
        "extra_in_config_usefulness": [],
        "extra_in_surface_status_ledger": [],
    }
    assert report["status"] == "clean"
    assert report["apply_blocking"] is False
```

- [ ] **Step 3: Add failing sentinel drift test**

Append this test to `tests/test_contract_spine_sentinel.py`:

```python
def test_contract_spine_sentinel_flags_runtime_surface_missing_from_operator_views(
    monkeypatch,
):
    from hsconfig import contract_spine_sentinel as sentinel

    monkeypatch.setattr(
        sentinel,
        "EXPECTED_RUNTIME_SURFACES",
        (*sentinel.EXPECTED_RUNTIME_SURFACES, "future_surface"),
    )

    report = sentinel.build_contract_spine_sentinel_report()

    assert report["status"] == "drift_detected"
    assert {
        "check": "runtime_surface_coverage",
        "value": {
            "missing_from_config_usefulness": ["future_surface"],
            "missing_from_surface_status_ledger": ["future_surface"],
            "extra_in_config_usefulness": [],
            "extra_in_surface_status_ledger": [],
        },
    } in report["problems"]
```

- [ ] **Step 4: Run tests and confirm they fail**

Run:

```powershell
python -m pytest tests/test_config_usefulness.py::test_config_usefulness_surfaces_match_expected_runtime_surface_registry tests/test_contract_spine_sentinel.py::test_contract_spine_sentinel_exposes_runtime_surface_coverage tests/test_contract_spine_sentinel.py::test_contract_spine_sentinel_flags_runtime_surface_missing_from_operator_views -q
```

Expected:

```text
FAILED
ImportError: cannot import name 'EXPECTED_RUNTIME_SURFACES'
```

- [ ] **Step 5: Add the runtime surface registry**

In `src/hsconfig/config_usefulness.py`, add this constant after imports:

```python
EXPECTED_RUNTIME_SURFACES = (
    "mulligan",
    "globalvalues",
    "cardid_behavior",
    "combo",
)
```

In `build_config_usefulness`, keep the current four surface builder calls and assign the returned surface mapping to a local variable before the return:

```python
    surfaces = {
        "mulligan": mulligan,
        "globalvalues": globalvalues,
        "cardid_behavior": cardid,
        "combo": combo,
    }
```

Replace the inline `"surfaces": {...}` value with:

```python
        "surfaces": surfaces,
```

- [ ] **Step 6: Add runtime coverage to the sentinel**

In `src/hsconfig/contract_spine_sentinel.py`, extend the existing import from `hsconfig.config_usefulness`:

```python
from hsconfig.config_usefulness import EXPECTED_RUNTIME_SURFACES
```

Add this import near the other HSConfig imports:

```python
from hsconfig.operator_summary import build_operator_summary
```

Add `"runtime_surface_coverage": _runtime_surface_coverage(),` to the `checks` dict inside `build_contract_spine_sentinel_report`.

Add `"runtime_surface_coverage"` to the evidence tuple for `diagnostics_are_non_authoritative` in `INVARIANT_EVIDENCE`:

```python
    "diagnostics_are_non_authoritative": (
        "non_diagnostic_policy_claim_kinds",
        "spine_rows_with_apply_authority_fields",
        "conformance_apply_authority_fields_present",
        "conformance_operator_gate_impact",
        "surface_status_ledger",
        "runtime_surface_coverage",
    ),
```

Add these helper functions before `_problems`:

```python
def _runtime_surface_coverage() -> dict[str, Any]:
    summary = build_operator_summary(
        deck_name="Surface Coverage Fixture",
        deck_code="AAEBAQAAAA==",
        technical_validation={"status": "passed", "errors": []},
        guide_source_depth={
            "source_depth_status": "static_semantics_only",
            "claim_count": 0,
        },
        mulligan_plan_report={
            "rules": [],
            "suppressed_rules": [],
            "quality": {
                "status": "thin",
                "has_concrete_keeps": False,
            },
        },
        card_behavior_plan_report={"rows": []},
        combo_plan_report={"combos": [], "suppressed": []},
        globalvalues_profile_report={"changed_keys": [], "unchanged_keys": []},
    )
    expected = sorted(EXPECTED_RUNTIME_SURFACES)
    config_surfaces = sorted(summary["config_usefulness"]["surfaces"])
    ledger_surfaces = sorted(row["surface"] for row in summary["surface_status_ledger"])
    return {
        "expected_surfaces": expected,
        "config_usefulness_surfaces": config_surfaces,
        "surface_status_ledger_surfaces": ledger_surfaces,
        "missing_from_config_usefulness": sorted(set(expected) - set(config_surfaces)),
        "missing_from_surface_status_ledger": sorted(
            set(expected) - set(ledger_surfaces)
        ),
        "extra_in_config_usefulness": sorted(set(config_surfaces) - set(expected)),
        "extra_in_surface_status_ledger": sorted(set(ledger_surfaces) - set(expected)),
    }


def _runtime_surface_coverage_problem_value(
    coverage: dict[str, Any],
) -> dict[str, list[str]]:
    return {
        "missing_from_config_usefulness": list(
            coverage.get("missing_from_config_usefulness", [])
        ),
        "missing_from_surface_status_ledger": list(
            coverage.get("missing_from_surface_status_ledger", [])
        ),
        "extra_in_config_usefulness": list(
            coverage.get("extra_in_config_usefulness", [])
        ),
        "extra_in_surface_status_ledger": list(
            coverage.get("extra_in_surface_status_ledger", [])
        ),
    }
```

In `_problems`, add this block before the final `return problems`:

```python
    coverage = checks.get("runtime_surface_coverage", {})
    if isinstance(coverage, dict):
        coverage_problem = _runtime_surface_coverage_problem_value(coverage)
        if any(coverage_problem.values()):
            problems.append(
                {"check": "runtime_surface_coverage", "value": coverage_problem}
            )
```

- [ ] **Step 7: Run task tests**

Run:

```powershell
python -m pytest tests/test_config_usefulness.py::test_config_usefulness_surfaces_match_expected_runtime_surface_registry tests/test_contract_spine_sentinel.py::test_contract_spine_sentinel_exposes_runtime_surface_coverage tests/test_contract_spine_sentinel.py::test_contract_spine_sentinel_flags_runtime_surface_missing_from_operator_views -q
```

Expected:

```text
3 passed
```

- [ ] **Step 8: Run focused sentinel suite**

Run:

```powershell
python -m pytest tests/test_contract_spine_sentinel.py tests/test_config_usefulness.py -q
```

Expected:

```text
passed
```

- [ ] **Step 9: Commit Task 1**

Run:

```powershell
git add src/hsconfig/config_usefulness.py src/hsconfig/contract_spine_sentinel.py tests/test_config_usefulness.py tests/test_contract_spine_sentinel.py
git commit -m "test: guard runtime surface ledger coverage"
```

---

### Task 2: Make Default-Only Details Surface-Specific

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\operator_summary.py`
- Test: `C:\Users\darbo\Documents\HSConfig\tests\test_operator_summary.py`

**Interfaces:**
- Consumes: `source_to_runtime_explainability_report["card_rows"]`
- Produces: `default_only_runtime_surface_details[*]["example_card_details"]` filtered to the affected surface.
- Surface-to-runtime file mapping:
  - `mulligan -> Mulligan.json`
  - `globalvalues -> GlobalValues.json`
  - `combo -> Combo.json`
  - `cardid_behavior -> any *.json except Mulligan.json, GlobalValues.json, Combo.json`

- [ ] **Step 1: Add failing surface-specific detail test**

Append this test to `tests/test_operator_summary.py` near `test_default_only_surface_details_include_missing_link_and_card_details`:

```python
def test_default_only_surface_details_filter_example_cards_to_runtime_surface():
    summary = build_operator_summary(
        deck_name="Thin Deck",
        deck_code="AAEBAQAAAA==",
        technical_validation={"status": "passed", "errors": []},
        mulligan_plan_report={
            "rules": [],
            "suppressed_rules": [],
            "quality": {
                "status": "thin",
                "has_concrete_keeps": False,
                "first_gap_reason": "no_source_backed_or_policy_backed_mulligan_keeps",
            },
        },
        source_to_runtime_explainability_report={
            "card_rows": [
                {
                    "card_id": "MULL_001",
                    "name": "Mulligan Missing Card",
                    "closure": {
                        "lane": "baseline_only_visible",
                        "runtime_surfaces": ["Mulligan.json"],
                        "default_only_risk": True,
                        "first_missing_link": "needs_mulligan_claim",
                        "next_source_action": "add_mulligan_keep_or_discard_claim",
                    },
                },
                {
                    "card_id": "CARDID_001",
                    "name": "CardID Missing Card",
                    "closure": {
                        "lane": "baseline_only_visible",
                        "runtime_surfaces": ["CARDID_001.json"],
                        "default_only_risk": True,
                        "first_missing_link": "needs_runtime_surface",
                        "next_source_action": "add_cardid_behavior_claim",
                    },
                },
            ]
        },
    )

    assert summary["default_only_runtime_surface_details"] == [
        {
            "surface": "mulligan",
            "status": "default_only",
            "card_count_with_default_only_risk": 1,
            "example_cards": ["MULL_001 Mulligan Missing Card"],
            "example_card_details": [
                {
                    "card_id": "MULL_001",
                    "name": "Mulligan Missing Card",
                    "closure_lane": "baseline_only_visible",
                    "first_missing_link": "needs_mulligan_claim",
                    "next_source_action": "add_mulligan_keep_or_discard_claim",
                }
            ],
            "first_missing_link": "no_source_backed_or_policy_backed_mulligan_keeps",
            "next_source_action": "source_backed_or_policy_backed_mulligan_keeps",
            "operator_impact": "diagnostic_only",
            "apply_blocking": False,
        }
    ]
```

- [ ] **Step 2: Run test and confirm failure**

Run:

```powershell
python -m pytest tests/test_operator_summary.py::test_default_only_surface_details_filter_example_cards_to_runtime_surface -q
```

Expected:

```text
FAILED
AssertionError
```

- [ ] **Step 3: Add surface-to-file helpers**

In `src/hsconfig/operator_summary.py`, add this constant near `SURFACE_REJECTION_REASONS`:

```python
SURFACE_RUNTIME_FILES = {
    "mulligan": {"Mulligan.json"},
    "globalvalues": {"GlobalValues.json"},
    "combo": {"Combo.json"},
}
CARDID_NON_SURFACE_FILES = {"Mulligan.json", "GlobalValues.json", "Combo.json"}
```

Add these helpers near `_default_only_runtime_surface_details`:

```python
def _runtime_surfaces_from_closure(row: dict[str, Any]) -> set[str]:
    closure = row.get("closure", {})
    if not isinstance(closure, dict):
        return set()
    value = closure.get("runtime_surfaces", [])
    if not isinstance(value, list):
        return set()
    return {str(item) for item in value if str(item)}


def _closure_matches_surface(row: dict[str, Any], surface: str) -> bool:
    runtime_files = _runtime_surfaces_from_closure(row)
    if not runtime_files:
        return True
    if surface == "cardid_behavior":
        return bool(runtime_files - CARDID_NON_SURFACE_FILES)
    expected_files = SURFACE_RUNTIME_FILES.get(surface, set())
    return bool(runtime_files.intersection(expected_files))
```

- [ ] **Step 4: Filter default-only risk card details by surface**

Change the signature of `_default_only_risk_card_details` from:

```python
def _default_only_risk_card_details(
    source_to_runtime_explainability_report: dict[str, Any],
) -> list[dict[str, Any]]:
```

to:

```python
def _default_only_risk_card_details(
    source_to_runtime_explainability_report: dict[str, Any],
    *,
    surface: str | None = None,
) -> list[dict[str, Any]]:
```

Inside the loop over `card_rows`, after confirming `closure` is a dict and before appending details, add:

```python
        if surface is not None and not _closure_matches_surface(row, surface):
            continue
```

In `_default_only_runtime_surface_details`, replace:

```python
    risky_card_details = _default_only_risk_card_details(
        source_to_runtime_explainability_report
    )
```

with:

```python
    all_risky_card_details = _default_only_risk_card_details(
        source_to_runtime_explainability_report
    )
```

Inside the surface loop, before building `risky_cards`, add:

```python
        risky_card_details = _default_only_risk_card_details(
            source_to_runtime_explainability_report,
            surface=str(name),
        )
        if not risky_card_details:
            risky_card_details = all_risky_card_details
```

- [ ] **Step 5: Run task test**

Run:

```powershell
python -m pytest tests/test_operator_summary.py::test_default_only_surface_details_filter_example_cards_to_runtime_surface -q
```

Expected:

```text
1 passed
```

- [ ] **Step 6: Run operator summary tests**

Run:

```powershell
python -m pytest tests/test_operator_summary.py -q
```

Expected:

```text
passed
```

- [ ] **Step 7: Commit Task 2**

Run:

```powershell
git add src/hsconfig/operator_summary.py tests/test_operator_summary.py
git commit -m "fix: make default-only details surface-specific"
```

---

### Task 3: Expand Semantic Qualifiers Without New Runtime Surfaces

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\source_semantic_qualifiers.py`
- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\source_document_model.py`
- Test: `C:\Users\darbo\Documents\HSConfig\tests\test_semantic_qualifiers.py`

**Interfaces:**
- Consumes: `semantic_qualifiers` dict in source claims.
- Produces: normalized qualifier keys `timing`, `zone_scope`, `target_scope`, `option_surface`, `state_requirements`, `generation_scope`, and `deck_evaluation`.
- Produces: `qualifier_values(claim: Mapping[str, Any], key: str) -> set[str]`.
- Preserves: `has_qualifier(claim, key, value) -> bool`.

- [ ] **Step 1: Add failing qualifier normalization test**

Append this test to `tests/test_semantic_qualifiers.py`:

```python
def test_normalize_semantic_qualifiers_accepts_generation_and_deck_evaluation():
    result = normalize_semantic_qualifiers(
        {
            "semantic_qualifiers": {
                "generation_scope": "Generated Card",
                "deck_evaluation": ["No Duplicates", "Odd Cost"],
            }
        }
    )

    assert result["generation_scope"] == "generated"
    assert result["deck_evaluation"] == ["highlander", "odd"]
```

- [ ] **Step 2: Add failing deck-evaluation false-lowering test**

Append this test to `tests/test_semantic_qualifiers.py`:

```python
def test_deck_evaluation_qualifier_blocks_mulligan_keep_without_opening_hand_text():
    claim = {
        "claim_kind": "mulligan_keep",
        "claim_readiness": "guide_backed",
        "trust_ceiling": "runtime_candidate",
        "cards": ["DECK_MODIFIER"],
        "evidence_text_short": "Core highlander payoff for this deck.",
        "semantic_qualifiers": {
            "deck_evaluation": "highlander",
        },
    }

    decision = can_lower_to_mulligan(claim)

    assert decision.allowed is False
    assert decision.reason == "start_of_game_effect_does_not_require_opening_hand"
```

- [ ] **Step 3: Add failing generated-entity false-lowering test**

Append this test to `tests/test_semantic_qualifiers.py`:

```python
def test_generated_qualifier_blocks_mulligan_keep_without_opening_hand_text():
    claim = {
        "claim_kind": "mulligan_keep",
        "claim_readiness": "guide_backed",
        "trust_ceiling": "runtime_candidate",
        "cards": ["GENERATED_OPTION"],
        "evidence_text_short": "Generated payoff card matters later.",
        "semantic_qualifiers": {
            "generation_scope": "generated",
        },
    }

    decision = can_lower_to_mulligan(claim)

    assert decision.allowed is False
    assert decision.reason == "start_of_game_effect_does_not_require_opening_hand"
```

- [ ] **Step 4: Add passing opening-hand override test**

Append this test to `tests/test_semantic_qualifiers.py`:

```python
def test_deck_evaluation_qualifier_allows_explicit_opening_hand_text():
    claim = {
        "claim_kind": "mulligan_keep",
        "claim_readiness": "guide_backed",
        "trust_ceiling": "runtime_candidate",
        "cards": ["DECK_MODIFIER"],
        "evidence_text_short": "Always keep DECK_MODIFIER in your opening hand.",
        "semantic_qualifiers": {
            "deck_evaluation": "highlander",
        },
    }

    decision = can_lower_to_mulligan(claim)

    assert decision.allowed is True
```

- [ ] **Step 5: Run tests and confirm failure**

Run:

```powershell
python -m pytest tests/test_semantic_qualifiers.py -q
```

Expected:

```text
FAILED
```

- [ ] **Step 6: Extend semantic qualifier keys and aliases**

In `src/hsconfig/source_semantic_qualifiers.py`, replace `QUALIFIER_KEYS` with:

```python
QUALIFIER_KEYS = (
    "timing",
    "zone_scope",
    "target_scope",
    "option_surface",
    "state_requirements",
    "generation_scope",
    "deck_evaluation",
)
```

Extend `ALIASES` with these rows:

```python
    "generated card": "generated",
    "generated cards": "generated",
    "random pool": "random_pool",
    "randomly generated": "generated",
    "discovered": "discovered",
    "copied": "copied",
    "transformed": "transformed",
    "shuffled": "shuffled",
    "no duplicates": "highlander",
    "singleton": "highlander",
    "highlander": "highlander",
    "odd cost": "odd",
    "odd": "odd",
    "even cost": "even",
    "even": "even",
    "deck size": "deck_size",
    "start in deck": "start_in_deck",
    "all shadow spells": "all_shadow_spells",
```

- [ ] **Step 7: Add `qualifier_values` helper**

In `src/hsconfig/source_semantic_qualifiers.py`, add this function after `has_qualifier`:

```python
def qualifier_values(claim: Mapping[str, Any], key: str) -> set[str]:
    qualifiers = claim.get("semantic_qualifiers", {})
    if not isinstance(qualifiers, Mapping):
        return set()
    current = qualifiers.get(key)
    if isinstance(current, list):
        return {str(item) for item in current if str(item)}
    if current is None:
        return set()
    return {str(current)}
```

- [ ] **Step 8: Keep scalar/list behavior correct in `_add_value`**

In `_add_value`, change the scalar branch:

```python
        if normalized:
            result[key] = [normalized] if key == "state_requirements" else normalized
```

to:

```python
        if normalized:
            result[key] = (
                [normalized]
                if key in {"state_requirements", "deck_evaluation"}
                else normalized
            )
```

This keeps `deck_evaluation` list-capable while preserving scalar `generation_scope`.

- [ ] **Step 9: Use the expanded qualifiers in Mulligan lowering**

In `src/hsconfig/source_document_model.py`, change the import:

```python
from hsconfig.source_semantic_qualifiers import has_qualifier
```

to:

```python
from hsconfig.source_semantic_qualifiers import has_qualifier, qualifier_values
```

Add these constants near `CARDID_SURFACE_CLAIM_KINDS`:

```python
DECK_EVALUATION_NON_HAND_EFFECTS = frozenset(
    {
        "highlander",
        "odd",
        "even",
        "deck_size",
        "start_in_deck",
        "all_shadow_spells",
    }
)

GENERATED_NON_OPENING_HAND_SCOPES = frozenset(
    {
        "generated",
        "random_pool",
        "discovered",
        "copied",
        "transformed",
        "shuffled",
    }
)
```

In `_contains_start_of_game_non_hand_effect`, before `qualifier_start_effect = (...)`, add:

```python
    deck_evaluation_effect = bool(
        qualifier_values(claim or {}, "deck_evaluation").intersection(
            DECK_EVALUATION_NON_HAND_EFFECTS
        )
    )
    generated_effect = bool(
        qualifier_values(claim or {}, "generation_scope").intersection(
            GENERATED_NON_OPENING_HAND_SCOPES
        )
    )
```

Extend `qualifier_start_effect`:

```python
        or has_qualifier(claim or {}, "state_requirements", "deckbuilding_effect")
        or deck_evaluation_effect
        or generated_effect
```

- [ ] **Step 10: Run semantic qualifier tests**

Run:

```powershell
python -m pytest tests/test_semantic_qualifiers.py -q
```

Expected:

```text
passed
```

- [ ] **Step 11: Run contract boundary tests**

Run:

```powershell
python -m pytest tests/test_claim_kind_runtime_contract.py tests/test_semantic_runtime_negative_boundaries.py tests/test_archetype_source_fixtures.py -q
```

Expected:

```text
passed
```

- [ ] **Step 12: Commit Task 3**

Run:

```powershell
git add src/hsconfig/source_semantic_qualifiers.py src/hsconfig/source_document_model.py tests/test_semantic_qualifiers.py
git commit -m "fix: harden semantic qualifiers against false mulligan lowering"
```

---

### Task 4: Slim the Operator Repair Order Without Removing Diagnostics

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\docs\operator\README.md`
- Modify: `C:\Users\darbo\Documents\HSConfig\docs\operator\guide-research-policy.md`
- Modify: `C:\Users\darbo\Documents\HSConfig\.agents\skills\hsconfig\SKILL.md`
- Modify: `C:\Users\darbo\Documents\HSConfig\.agents\skills\hsconfig\references\guide-research-policy.md`
- Test: `C:\Users\darbo\Documents\HSConfig\tests\test_operator_docs_contract_policy.py`
- Test: `C:\Users\darbo\Documents\HSConfig\tests\test_skill_sync.py`

**Interfaces:**
- Consumes: active operator docs and repo skill text.
- Produces: docs language where:
  - `operator_summary.json` remains first normal report and only apply authority.
  - `source_to_runtime_explainability.json` is the primary card-readable source-to-runtime repair map.
  - `source_claim_gap_report.json` remains secondary diagnostic evidence.
  - Default-only remains warning-only and non-blocking.

- [ ] **Step 1: Add failing docs policy test**

Append this test to `tests/test_operator_docs_contract_policy.py`:

```python
from pathlib import Path


def test_docs_keep_source_claim_gap_report_secondary_to_explainability():
    root = Path(__file__).resolve().parents[1]
    docs_text = (root / "docs/operator/README.md").read_text(encoding="utf-8")
    policy_text = (root / "docs/operator/guide-research-policy.md").read_text(
        encoding="utf-8"
    )
    skill_text = (root / ".agents/skills/hsconfig/SKILL.md").read_text(
        encoding="utf-8"
    )
    skill_policy_text = (
        root / ".agents/skills/hsconfig/references/guide-research-policy.md"
    ).read_text(encoding="utf-8")
    combined = "\n".join([docs_text, policy_text, skill_text, skill_policy_text])

    assert (
        "source_to_runtime_explainability.json is the primary card-readable repair map"
        in combined
    )
    assert "source_claim_gap_report.json is secondary diagnostic evidence" in combined
    assert "Use `source_claim_gap_report.json` to inspect the first missing source" not in combined
    assert "operator_summary.json remains the only normal apply authority" in combined
```

- [ ] **Step 2: Run test and confirm failure**

Run:

```powershell
python -m pytest tests/test_operator_docs_contract_policy.py::test_docs_keep_source_claim_gap_report_secondary_to_explainability -q
```

Expected:

```text
FAILED
```

- [ ] **Step 3: Update `docs/operator/README.md`**

In `docs/operator/README.md`, replace any operator wording that says to inspect `source_claim_gap_report.json` first with this wording:

```markdown
`source_to_runtime_explainability.json` is the primary card-readable repair map for source-to-runtime closure. It names emitted runtime files, missing runtime files, first missing links, closure lanes, and next source actions. `source_claim_gap_report.json` is secondary diagnostic evidence for older source-depth workflows; it must not become the first operator report and does not grant or deny apply permission.
```

Keep the existing table row for `reports/source_claim_gap_report.json`, but change its purpose text to:

```markdown
secondary diagnostic evidence for card/source gap history
```

- [ ] **Step 4: Update `docs/operator/guide-research-policy.md`**

Replace the depth-report wording that starts with `Use source_claim_gap_report.json` with:

```markdown
Use `source_to_runtime_explainability.json` as the primary card-readable repair map. It is the first place to inspect emitted runtime files, missing runtime files, first missing links, closure lanes, and next source actions. `source_claim_gap_report.json` is secondary diagnostic evidence for source-depth history and must not be treated as an apply gate.
```

Keep `source_claim_gap_report.json` in the report list, but describe it as:

```markdown
- `source_claim_gap_report.json`: secondary diagnostic evidence for card/source gap history.
```

- [ ] **Step 5: Update repo skill wording and reference policy**

In `.agents/skills/hsconfig/SKILL.md`, update the reports-to-open bullet so the first sentence is:

```markdown
- For source-depth work, open `source_to_runtime_explainability.json` first; it is the primary card-readable repair map. `source_claim_gap_report.json` is secondary diagnostic evidence for older source-depth gap history, not an apply gate and not the first normal operator report.
```

Keep the remaining report names in the same bullet after that sentence.

In `.agents/skills/hsconfig/references/guide-research-policy.md`, make the same depth-report replacement used in `docs/operator/guide-research-policy.md`:

```markdown
Use `source_to_runtime_explainability.json` as the primary card-readable repair map. It is the first place to inspect emitted runtime files, missing runtime files, first missing links, closure lanes, and next source actions. `source_claim_gap_report.json` is secondary diagnostic evidence for source-depth history and must not be treated as an apply gate.
```

Keep the reference report list entry aligned as:

```markdown
- `source_claim_gap_report.json`: secondary diagnostic evidence for card/source gap history.
```

- [ ] **Step 6: Sync installed skill**

Run:

```powershell
python scripts/sync_installed_skill.py
```

Expected:

```text
synced
```

If the script prints a different success word, keep the command output for the final task review and continue only if the exit code is 0.

- [ ] **Step 7: Run docs and skill tests**

Run:

```powershell
python -m pytest tests/test_operator_docs_contract_policy.py tests/test_skill_sync.py tests/test_docs_active_path.py -q
```

Expected:

```text
passed
```

- [ ] **Step 8: Commit Task 4**

Run:

```powershell
git add docs/operator/README.md docs/operator/guide-research-policy.md .agents/skills/hsconfig/SKILL.md .agents/skills/hsconfig/references/guide-research-policy.md tests/test_operator_docs_contract_policy.py
git commit -m "docs: make explainability the primary repair map"
```

Do not add `C:\Users\darbo\.codex\skills\hsconfig\SKILL.md`; it is outside the repo and should only be synchronized locally.

---

### Task 5: Final Verification and Cleanup

**Files:**
- Review: all files changed in Tasks 1-4.
- Review: `C:\Users\darbo\Documents\HSConfig\docs\research\2026-07-14-hsconfig-source-contract-ledger-brainstorm\`

**Interfaces:**
- Consumes: all task outputs.
- Produces: verified branch ready for the user's requested integration flow.

- [ ] **Step 1: Check working tree before verification**

Run:

```powershell
git status --short --branch
```

Expected:

```text
## codex/no-silent-default-only-closure
```

The research folder `docs/research/2026-07-14-hsconfig-source-contract-ledger-brainstorm/` may still be untracked if it was intentionally left as brainstorm evidence. Decide in this task whether to commit it with the implementation branch or keep it untracked. If it remains untracked, mention it explicitly in the final handoff.

- [ ] **Step 2: Run focused contract and surface suites**

Run:

```powershell
python -m pytest tests/test_config_usefulness.py tests/test_operator_summary.py tests/test_contract_spine_sentinel.py tests/test_semantic_qualifiers.py tests/test_claim_kind_runtime_contract.py tests/test_semantic_runtime_negative_boundaries.py tests/test_operator_docs_contract_policy.py tests/test_skill_sync.py -q
```

Expected:

```text
passed
```

- [ ] **Step 3: Run authority and no-second-gate suites**

Run:

```powershell
python -m pytest tests/test_apply_authority_boundary.py tests/test_no_second_gate_contract.py tests/test_report_ownership.py tests/test_output_ownership_manifest.py tests/test_contract_spine_sentinel_cli.py tests/test_contract_doctor.py -q
```

Expected:

```text
passed
```

- [ ] **Step 4: Run guardrail scripts**

Run:

```powershell
python scripts/check_contract_guardrails.py
python scripts/sync_installed_skill.py --check
```

Expected:

```text
exit code 0 for both commands
```

- [ ] **Step 5: Run full tests**

Run:

```powershell
python -m pytest
```

Expected:

```text
passed
```

The repository previously had more than 1200 tests. Do not claim full green unless the command exits with code 0.

- [ ] **Step 6: Inspect diff**

Run:

```powershell
git diff --check
git diff --stat
git diff -- src/hsconfig/config_usefulness.py src/hsconfig/operator_summary.py src/hsconfig/source_semantic_qualifiers.py src/hsconfig/source_document_model.py src/hsconfig/contract_spine_sentinel.py
```

Expected:

```text
git diff --check exits with code 0
```

Review that no diff adds:

```text
Presume.json
Concede.json
runtime apply gate in diagnostic reports
named-card exception list
manual approval requirement for default-only warnings
```

- [ ] **Step 7: Commit any final cleanup**

If Task 5 changed docs or test expectations, run:

```powershell
git add <changed repo files>
git commit -m "test: verify surface coverage contract hardening"
```

If no files changed in Task 5, do not create an empty commit.

- [ ] **Step 8: Final status**

Run:

```powershell
git status --short --branch
```

Expected if all implementation files are committed:

```text
## codex/no-silent-default-only-closure
```

If the research package remains intentionally untracked, expected status includes:

```text
?? docs/research/2026-07-14-hsconfig-source-contract-ledger-brainstorm/
```

The final response must state whether the research package was committed or left untracked.

---

## Self-Review Checklist

- Spec coverage:
  - Surface drift: Task 1.
  - Surface-specific default-only detail: Task 2.
  - Expanded Hearthstone qualifiers: Task 3.
  - No new apply gate: Tasks 1, 4, and 5.
  - Source-to-runtime repair order and report slimness: Task 4.
  - Full verification: Task 5.
- Placeholder scan:
  - No placeholder markers or unspecified implementation steps are intentionally left in this plan.
  - Every code-changing step names exact files and includes exact snippets.
- Type consistency:
  - `EXPECTED_RUNTIME_SURFACES` is a tuple of strings.
  - `qualifier_values(...)` returns `set[str]`.
  - `runtime_surface_coverage` sentinel values are lists of strings.
  - `default_only_runtime_surface_details` remains a list of dict rows and keeps existing non-blocking fields.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-14-surface-coverage-sentinel-semantic-qualifier-hardening.md`. Two execution options:

1. Subagent-Driven (recommended) - dispatch a fresh subagent per task, review between tasks, fast iteration.
2. Inline Execution - execute tasks in this session using executing-plans, batch execution with checkpoints.

Recommended choice: Subagent-Driven, because Task 1, Task 2, Task 3, and Task 4 touch independent surfaces and can be reviewed separately before final verification.

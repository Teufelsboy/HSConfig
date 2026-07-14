# HSConfig Source-To-Runtime Closure Wave Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make HSConfig's source-to-runtime chain fully explainable per card, with no silent default-only output and no false effect-to-mulligan lowering, while keeping the workflow autonomous and load-safe for any deck.

**Architecture:** Extend the existing diagnostic spine instead of creating a second pipeline. `source_contract_audit.json` remains diagnostic, `source_to_runtime_explainability.json` becomes the per-card closure report, and `operator_summary.json` remains the only normal apply authority.

**Tech Stack:** Python 3, pytest, existing HSConfig CLI/report builders, local `research-deep` outline/result convention, no new runtime dependencies.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig`.
- Do not create a new runtime apply gate; `reports/operator_summary.json` remains the only normal apply authority.
- Do not block valid load-safe packages because a source claim is low confidence, report-only, unsupported by a runtime surface, or diagnostic-only.
- Do not emit `Presume.json`, `Concede.json`, or aggregate `CardBehavior.json` in the normal HSConfig path.
- Effect semantics are not opening-hand mulligan keeps. Preserve hero-power-transform behavior, but do not place the enabler card in `Mulligan.json` unless the source explicitly describes opening-hand mulligan intent.
- Keep `source_contract_audit.json`, `source_to_runtime_explainability.json`, contract-spine rows, and source-depth reports diagnostic-only.
- Prefer narrow tests and minimal changes over structural rewrites.

---

## File Structure

- Create `docs/research/2026-07-14-hsconfig-source-to-runtime-closure-wave/outline.yaml`
  - Research-deep outline for source contract, no-default-only, false-mulligan, and any-deck autonomy validation.
- Create `docs/research/2026-07-14-hsconfig-source-to-runtime-closure-wave/fields.yaml`
  - Structured fields for research-deep JSON results.
- Modify `src/hsconfig/source_to_runtime_explainability.py`
  - Add per-card closure fields without changing the public function signature.
- Modify `src/hsconfig/operator_summary.py`
  - Add a compact `default_only_runtime_surface_details` projection sourced from `config_usefulness` and explainability rows.
- Modify `tests/test_source_to_runtime_explainability.py`
  - TDD coverage for per-card closure rows, default-only risk, suppressed reasons, and first missing link.
- Modify `tests/test_operator_summary.py`
  - TDD coverage for default-only details and no second apply authority.
- Modify `tests/test_universal_wild_no_block_matrix.py`
  - Ensure the deck matrix still produces load-safe packages and no silent default-only surfaces.
- Modify `tests/test_source_contract_closure_wave.py`
  - Add canaries for start-of-game/deckbuilding/hero-power-transform effects that must not become mulligan keeps.
- Modify `docs/operator/guide-research-policy.md`
  - Small operator-facing clarification only if the report shape changes.
- Modify `.agents/skills/hsconfig/SKILL.md`
  - Keep skill instructions aligned with the final report names and authority boundary.

---

### Task 1: Add Research-Deep Outline For The Closure Wave

**Files:**
- Create: `docs/research/2026-07-14-hsconfig-source-to-runtime-closure-wave/outline.yaml`
- Create: `docs/research/2026-07-14-hsconfig-source-to-runtime-closure-wave/fields.yaml`

**Interfaces:**
- Consumes: `research-deep` expects an `outline.yaml` and sibling `fields.yaml`.
- Produces: validated JSON result files under `docs/research/2026-07-14-hsconfig-source-to-runtime-closure-wave/results/`.

- [ ] **Step 1: Create the research field schema**

Create `docs/research/2026-07-14-hsconfig-source-to-runtime-closure-wave/fields.yaml`:

```yaml
fields:
  summary:
    type: string
    required: true
  source_backed_findings:
    type: list
    required: true
  current_repo_alignment:
    type: string
    required: true
  remaining_risks:
    type: list
    required: true
  implementation_implications:
    type: list
    required: true
  no_block_autonomy_implications:
    type: list
    required: true
  must_not_become_apply_gate:
    type: boolean
    required: true
  uncertain:
    type: list
    required: true
```

- [ ] **Step 2: Create the research outline**

Create `docs/research/2026-07-14-hsconfig-source-to-runtime-closure-wave/outline.yaml`:

```yaml
topic: hsconfig-source-to-runtime-closure-wave
execution:
  output_dir: ./results
  batch_size: 5
  items_per_agent: 1
items:
  - name: Current HSConfig source contract spine
    category: repo-contract
    description: Verify the current source claim -> claim_kind -> surface gate -> builder/router -> runtime row or suppression chain, including operator_summary.json as the only apply authority.
  - name: No default-only runtime surface policy
    category: repo-contract
    description: Verify that default-only Mulligan, GlobalValues, Combo, or CardID output is visible as a quality signal and not silently treated as success.
  - name: Effect versus opening-hand mulligan boundary
    category: hearthstone-semantics
    description: Verify that Start of Game, deckbuilding, hero-power-transform, Highlander, even/odd, quest, and transform effects are not inferred as opening-hand keeps without explicit mulligan intent.
  - name: Any-deck no-block autonomy
    category: workflow
    description: Verify that valid decks remain load-safe and applyable even when claims are report-only, low-confidence, runtime-evidence-required, or unsupported by a runtime surface.
  - name: Per-card closure report design
    category: operator-ux
    description: Verify which card-level fields best expose source-backed, policy-backed, static-semantic, report-only, suppressed, baseline-only, and first-missing-link states.
```

- [ ] **Step 3: Run research-deep**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
# Use the local research-deep skill workflow against the new outline.
```

Expected:

```text
results/Current_HSConfig_source_contract_spine.json
results/No_default-only_runtime_surface_policy.json
results/Effect_versus_opening-hand_mulligan_boundary.json
results/Any-deck_no-block_autonomy.json
results/Per-card_closure_report_design.json
```

- [ ] **Step 4: Validate research outputs**

Run:

```powershell
python C:\Users\darbo\.codex\skills\research\validate_json.py -f docs\research\2026-07-14-hsconfig-source-to-runtime-closure-wave\fields.yaml -j docs\research\2026-07-14-hsconfig-source-to-runtime-closure-wave\results\Current_HSConfig_source_contract_spine.json
python C:\Users\darbo\.codex\skills\research\validate_json.py -f docs\research\2026-07-14-hsconfig-source-to-runtime-closure-wave\fields.yaml -j docs\research\2026-07-14-hsconfig-source-to-runtime-closure-wave\results\No_default-only_runtime_surface_policy.json
python C:\Users\darbo\.codex\skills\research\validate_json.py -f docs\research\2026-07-14-hsconfig-source-to-runtime-closure-wave\fields.yaml -j docs\research\2026-07-14-hsconfig-source-to-runtime-closure-wave\results\Effect_versus_opening-hand_mulligan_boundary.json
python C:\Users\darbo\.codex\skills\research\validate_json.py -f docs\research\2026-07-14-hsconfig-source-to-runtime-closure-wave\fields.yaml -j docs\research\2026-07-14-hsconfig-source-to-runtime-closure-wave\results\Any-deck_no-block_autonomy.json
python C:\Users\darbo\.codex\skills\research\validate_json.py -f docs\research\2026-07-14-hsconfig-source-to-runtime-closure-wave\fields.yaml -j docs\research\2026-07-14-hsconfig-source-to-runtime-closure-wave\results\Per-card_closure_report_design.json
```

Expected: each command exits `0`.

- [ ] **Step 5: Commit**

```powershell
git add docs\research\2026-07-14-hsconfig-source-to-runtime-closure-wave
git commit -m "docs: add source runtime closure research outline"
```

---

### Task 2: Add Per-Card Closure Fields To Source-To-Runtime Explainability

**Files:**
- Modify: `tests/test_source_to_runtime_explainability.py`
- Modify: `src/hsconfig/source_to_runtime_explainability.py`

**Interfaces:**
- Consumes: `build_source_to_runtime_explainability_report(source_contract_audit_report: Mapping[str, Any] | None) -> dict[str, Any]`.
- Produces: `report["card_rows"][*]["closure"]` with fields `lane`, `claim_kinds`, `source_lanes`, `runtime_surfaces`, `default_only_risk`, `suppressed_reasons`, `first_missing_link`, `next_source_action`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_source_to_runtime_explainability.py`:

```python
def test_explainability_card_rows_include_compact_closure_lane():
    audit = _fixture_audit()
    audit["claim_rows"]["suppressed_start_effect"] = {
        "claim_id": "suppressed_start_effect",
        "claim_kind": "mulligan_keep",
        "lane": "suppressed_with_reason",
        "policy_lane": "runtime_lowerable",
        "lowered_surfaces": [],
        "first_reason": "start_of_game_effect_does_not_require_opening_hand",
        "cards": ["CARD_KEEP"],
    }
    audit["claim_lifecycle_rows"].append(
        {
            "claim_id": "suppressed_start_effect",
            "claim_kind": "mulligan_keep",
            "policy_lane": "runtime_lowerable",
            "surface_gate_decision": "rejected",
            "surface_gate_reason": "start_of_game_effect_does_not_require_opening_hand",
            "builder_or_router_decision": "suppressed",
            "runtime_surface": "Mulligan.json",
            "emitted_files": [],
            "suppressed_reason": "start_of_game_effect_does_not_require_opening_hand",
            "first_missing_link": "opening_hand_mulligan_intent",
            "operator_impact": "diagnostic_only",
        }
    )

    report = build_source_to_runtime_explainability_report(audit)
    rows = {row["card_id"]: row for row in report["card_rows"]}

    assert rows["CARD_KEEP"]["closure"] == {
        "lane": "source_action_needed",
        "claim_kinds": ["mulligan_keep"],
        "source_lanes": ["runtime_lowered", "suppressed_with_reason"],
        "runtime_surfaces": ["Mulligan.json"],
        "default_only_risk": False,
        "suppressed_reasons": [
            "start_of_game_effect_does_not_require_opening_hand"
        ],
        "first_missing_link": "opening_hand_mulligan_intent",
        "next_source_action": "add_explicit_opening_hand_mulligan_source",
    }
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```powershell
python -m pytest tests\test_source_to_runtime_explainability.py::test_explainability_card_rows_include_compact_closure_lane -q
```

Expected: FAIL because `closure` is not present.

- [ ] **Step 3: Implement closure projection**

In `src/hsconfig/source_to_runtime_explainability.py`, add this helper near `_operator_attention_status`:

```python
def _closure_row(
    *,
    row: Mapping[str, Any],
    related_claims: list[dict[str, Any]],
) -> dict[str, Any]:
    first_missing_link = row.get("first_missing_link")
    emitted_runtime_files = _string_list(row.get("emitted_runtime_files"))
    not_emitted_runtime_files = _string_list(row.get("not_emitted_runtime_files"))
    suppressed_reasons = sorted(
        {
            str(claim.get("why_not_emitted"))
            for claim in related_claims
            if claim.get("why_not_emitted")
        }
    )
    source_lanes = sorted(
        {
            str(claim.get("policy_lane") or claim.get("best_source_lane"))
            for claim in related_claims
            if claim.get("policy_lane") or claim.get("best_source_lane")
        }
    )
    claim_kinds = sorted(
        {
            str(claim.get("claim_kind"))
            for claim in related_claims
            if claim.get("claim_kind")
        }
    )
    lane = _operator_attention_status(dict(row))
    default_only_risk = (
        not emitted_runtime_files
        and not not_emitted_runtime_files
        and lane == "baseline_only_visible"
    )
    return {
        "lane": lane,
        "claim_kinds": claim_kinds,
        "source_lanes": source_lanes,
        "runtime_surfaces": emitted_runtime_files,
        "default_only_risk": default_only_risk,
        "suppressed_reasons": suppressed_reasons,
        "first_missing_link": first_missing_link,
        "next_source_action": row.get("next_source_action"),
    }
```

Then, in `_card_rows`, replace the direct `rows.append({...})` body with:

```python
        card_row = {
            "card_id": str(card_id),
            "name": str(raw_card.get("name", "")),
            "best_source_lane": best_source_lane,
            "strongest_claim_id": strongest_claim_id,
            "strongest_claim_kind": (
                strongest_claim.get("claim_kind") if strongest_claim else None
            ),
            "first_missing_link": first_missing_link,
            "emitted_runtime_files": emitted_files,
            "not_emitted_runtime_files": [
                path
                for path in sorted(set(expected_files) | set(not_emitted_files))
                if path not in set(emitted_files)
            ],
            "why_not_emitted": why_not_emitted,
            "apply_blocked": False,
            "next_source_action": _next_source_action(
                first_missing_link=first_missing_link,
                why_not_emitted=why_not_emitted,
                claim_kind=(
                    str(missing_claim.get("claim_kind"))
                    if missing_claim
                    else str(strongest_claim.get("claim_kind"))
                    if strongest_claim
                    else ""
                ),
            ),
        }
        card_row["closure"] = _closure_row(
            row=card_row,
            related_claims=related_claims,
        )
        rows.append(card_row)
```

- [ ] **Step 4: Add action mapping for opening-hand missing link**

If `_next_source_action()` does not already map `opening_hand_mulligan_intent`, add this branch:

```python
    if first_missing_link == "opening_hand_mulligan_intent":
        return "add_explicit_opening_hand_mulligan_source"
```

- [ ] **Step 5: Run targeted tests**

Run:

```powershell
python -m pytest tests\test_source_to_runtime_explainability.py -q
```

Expected: all tests in this file pass.

- [ ] **Step 6: Commit**

```powershell
git add src\hsconfig\source_to_runtime_explainability.py tests\test_source_to_runtime_explainability.py
git commit -m "feat: add per-card source runtime closure rows"
```

---

### Task 3: Surface Default-Only Details In Operator Summary Without Creating A Gate

**Files:**
- Modify: `tests/test_operator_summary.py`
- Modify: `src/hsconfig/operator_summary.py`

**Interfaces:**
- Consumes: `config_usefulness: dict[str, Any]` and optional `source_to_runtime_explainability_report`.
- Produces: `summary["default_only_runtime_surface_details"] -> list[dict[str, Any]]`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_operator_summary.py`:

```python
def test_operator_summary_explains_default_only_surfaces_without_blocking_apply():
    summary = build_operator_summary(
        deck_name="DefaultOnlyFixture",
        deck_code="fixture",
        technical_validation={"status": "passed"},
        config_readiness_report={"summary": {}},
        mulligan_plan_report={
            "status": "default_only",
            "default_only": True,
            "policy_lanes": [],
            "policy_reasons": [],
        },
        source_to_runtime_explainability_report={
            "authority": "diagnostic_only",
            "operator_gate_impact": "diagnostic_only",
            "apply_blocking": False,
            "summary": {
                "cards_total": 1,
                "claims_total": 0,
                "runtime_lowered_claims": 0,
                "claims_with_first_missing_link": 0,
                "cards_with_first_missing_link": 0,
            },
            "card_rows": [
                {
                    "card_id": "CARD_001",
                    "name": "Fixture Card",
                    "closure": {
                        "lane": "baseline_only_visible",
                        "claim_kinds": [],
                        "source_lanes": [],
                        "runtime_surfaces": [],
                        "default_only_risk": True,
                        "suppressed_reasons": [],
                        "first_missing_link": None,
                        "next_source_action": "none",
                    },
                }
            ],
        },
    )

    assert summary["default_only_runtime_surfaces"] == ["mulligan"]
    assert summary["default_only_runtime_surface_details"] == [
        {
            "surface": "mulligan",
            "status": "default_only",
            "card_count_with_default_only_risk": 1,
            "example_cards": ["CARD_001 Fixture Card"],
            "operator_impact": "diagnostic_only",
            "apply_blocking": False,
        }
    ]
    assert summary["runtime_apply_contract"]["apply_authority"] == (
        "reports/operator_summary.json"
    )
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```powershell
python -m pytest tests\test_operator_summary.py::test_operator_summary_explains_default_only_surfaces_without_blocking_apply -q
```

Expected: FAIL because `default_only_runtime_surface_details` is missing.

- [ ] **Step 3: Implement default-only detail projection**

In `src/hsconfig/operator_summary.py`, add to the summary dict directly after `default_only_runtime_surfaces`:

```python
        "default_only_runtime_surface_details": _default_only_runtime_surface_details(
            config_usefulness,
            source_to_runtime_explainability_report or {},
        ),
```

Add this helper after `_default_only_runtime_surfaces`:

```python
def _default_only_runtime_surface_details(
    config_usefulness: dict[str, Any],
    source_to_runtime_explainability_report: dict[str, Any],
) -> list[dict[str, Any]]:
    surfaces = (
        config_usefulness.get("surfaces", {})
        if isinstance(config_usefulness, dict)
        else {}
    )
    if not isinstance(surfaces, dict):
        return []
    risky_cards = _default_only_risk_cards(source_to_runtime_explainability_report)
    details: list[dict[str, Any]] = []
    for name, row in sorted(surfaces.items()):
        if not isinstance(row, dict) or row.get("default_only") is not True:
            continue
        details.append(
            {
                "surface": str(name),
                "status": str(row.get("status", "default_only")),
                "card_count_with_default_only_risk": len(risky_cards),
                "example_cards": risky_cards[:5],
                "operator_impact": "diagnostic_only",
                "apply_blocking": False,
            }
        )
    return details


def _default_only_risk_cards(report: dict[str, Any]) -> list[str]:
    rows = report.get("card_rows", []) if isinstance(report, dict) else []
    if not isinstance(rows, list):
        return []
    result: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        closure = row.get("closure", {})
        if not isinstance(closure, dict) or closure.get("default_only_risk") is not True:
            continue
        card_id = str(row.get("card_id", "")).strip()
        name = str(row.get("name", "")).strip()
        result.append(f"{card_id} {name}".strip())
    return sorted(result)
```

- [ ] **Step 4: Run targeted operator tests**

Run:

```powershell
python -m pytest tests\test_operator_summary.py::test_operator_summary_explains_default_only_surfaces_without_blocking_apply tests\test_operator_summary.py::test_operator_summary_reports_default_only_runtime_surfaces -q
```

Expected: both tests pass.

- [ ] **Step 5: Commit**

```powershell
git add src\hsconfig\operator_summary.py tests\test_operator_summary.py
git commit -m "feat: explain default only runtime surfaces"
```

---

### Task 4: Expand Start-Of-Game False-Mulligan Canaries

**Files:**
- Modify: `tests/test_source_contract_closure_wave.py`
- Modify: `src/hsconfig/source_document_model.py` only if a new canary fails.

**Interfaces:**
- Consumes: `can_lower_to_mulligan(claim, card_roles=...) -> SurfaceGateDecision`.
- Produces: regression coverage that Start of Game, deckbuilding, hero-power-transform, Highlander, even/odd, quest, and transform semantics do not become Mulligan keeps without explicit opening-hand intent.

- [ ] **Step 1: Write parametrized failing/safety test**

Append to `tests/test_source_contract_closure_wave.py`:

```python
import pytest

from hsconfig.source_document_model import can_lower_to_mulligan


@pytest.mark.parametrize(
    ("role", "qualifier"),
    [
        ("hero_power_transform", "hero_power_transform"),
        ("deckbuilding_modifier", "deckbuilding_effect"),
        ("highlander_modifier", "deckbuilding_effect"),
        ("even_odd_modifier", "deckbuilding_effect"),
        ("quest_reward", "deckbuilding_effect"),
        ("transform_effect", "deckbuilding_effect"),
    ],
)
def test_non_hand_start_effect_roles_do_not_become_mulligan_keeps(role, qualifier):
    claim = {
        "claim_kind": "mulligan_keep",
        "cards": ["CARD_EFFECT"],
        "source_confidence": "guide_backed",
        "semantic_qualifiers": {
            "timing": ["start_of_game"],
            "state_requirements": [qualifier],
        },
        "evidence_text_short": "This effect is important for the deck.",
    }

    decision = can_lower_to_mulligan(
        claim,
        card_roles={
            "CARD_EFFECT": {
                "roles": ["start_of_game", role],
                "semantic_families": ["start_of_game", role],
            }
        },
    )

    assert decision.allowed is False
    assert decision.reason == "start_of_game_effect_does_not_require_opening_hand"
```

- [ ] **Step 2: Run the test**

Run:

```powershell
python -m pytest tests\test_source_contract_closure_wave.py::test_non_hand_start_effect_roles_do_not_become_mulligan_keeps -q
```

Expected: PASS if current role-token coverage is complete; otherwise FAIL showing which role is missing.

- [ ] **Step 3: Implement only missing role-token coverage if needed**

If the test fails for a missing role, update the relevant role set in `src/hsconfig/role_tokens.py` or source role normalization, not the Mulligan gate itself. The added role must end up in `START_OF_GAME_NON_HAND_EFFECT_ROLES`.

Example expected shape in `src/hsconfig/role_tokens.py`:

```python
START_OF_GAME_NON_HAND_EFFECT_ROLES = frozenset(
    {
        "hero_power_transform",
        "deckbuilding_modifier",
        "deck_size_modifier",
        "even_odd_modifier",
        "highlander_modifier",
        "passive_start_effect",
        "quest_reward",
        "start_in_deck_requirement",
        "start_of_game_modifier",
        "transform_effect",
    }
)
```

- [ ] **Step 4: Run the closure and claim-kind tests**

Run:

```powershell
python -m pytest tests\test_source_contract_closure_wave.py tests\test_claim_kind_runtime_contract.py tests\test_surface_authority_split.py -q
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit**

```powershell
git add tests\test_source_contract_closure_wave.py src\hsconfig\role_tokens.py src\hsconfig\source_document_model.py
git commit -m "test: guard non hand effects from mulligan lowering"
```

If only tests changed, stage only `tests\test_source_contract_closure_wave.py`.

---

### Task 5: Prove Any-Deck No-Block Closure Across The Wild Matrix

**Files:**
- Modify: `tests/test_universal_wild_no_block_matrix.py`

**Interfaces:**
- Consumes: generated `reports/operator_summary.json` and `reports/source_to_runtime_explainability.json`.
- Produces: matrix-level assertion that every tested deck has operator-visible closure rows and no silent default-only surface.

- [ ] **Step 1: Extend the existing matrix assertions**

In `test_valid_wild_deck_produces_load_safe_warning_apply_package`, after reading `source_contract_audit`, also read explainability:

```python
    source_to_runtime = json.loads(
        (out / "reports" / "source_to_runtime_explainability.json").read_text(
            encoding="utf-8"
        )
    )
```

Add assertions:

```python
    assert source_to_runtime["authority"] == "diagnostic_only"
    assert source_to_runtime["apply_blocking"] is False
    assert source_to_runtime["summary"]["cards_total"] == len(deck_card_ids)
    assert source_to_runtime["operator_attention"]
    assert all("closure" in row for row in source_to_runtime["card_rows"])
    assert all(
        row["closure"]["lane"]
        in {
            "runtime_backed",
            "source_action_needed",
            "diagnostic_only",
            "baseline_only_visible",
        }
        for row in source_to_runtime["card_rows"]
    )
```

- [ ] **Step 2: Run the matrix test**

Run:

```powershell
python -m pytest tests\test_universal_wild_no_block_matrix.py::test_valid_wild_deck_produces_load_safe_warning_apply_package -q
```

Expected: all parametrized decks pass.

- [ ] **Step 3: If closure rows are missing for generated packages, wire the report writer**

If the test fails because `source_to_runtime_explainability.json` lacks `closure`, find the prepare path that writes the report. Ensure it calls the updated `build_source_to_runtime_explainability_report()` after `source_contract_audit_report` is built and before `build_operator_summary()` receives the explainability report.

Expected call order:

```python
source_contract_audit_report = build_source_contract_audit(...)
source_to_runtime_explainability_report = build_source_to_runtime_explainability_report(
    source_contract_audit_report
)
operator_summary = build_operator_summary(
    ...,
    source_contract_audit_report=source_contract_audit_report,
    source_to_runtime_explainability_report=source_to_runtime_explainability_report,
)
```

- [ ] **Step 4: Run configure path matrix**

Run:

```powershell
python -m pytest tests\test_universal_wild_no_block_matrix.py::test_configure_path_preserves_no_block_contract_for_matrix -q
```

Expected: all decks pass with `runtime_apply_allowed is True` and `default_only_runtime_surfaces == []`.

- [ ] **Step 5: Commit**

```powershell
git add tests\test_universal_wild_no_block_matrix.py src\hsconfig
git commit -m "test: prove per deck source runtime closure visibility"
```

---

### Task 6: Align Operator Docs And Skill Text

**Files:**
- Modify: `docs/operator/guide-research-policy.md`
- Modify: `docs/operator/README.md`
- Modify: `.agents/skills/hsconfig/SKILL.md`
- Test: `tests/test_operator_docs_contract_policy.py`
- Test: `tests/test_skill_files.py`

**Interfaces:**
- Consumes: final field names `closure`, `default_only_runtime_surface_details`, `default_only_runtime_surfaces`.
- Produces: active docs that say source-contract/explainability reports are diagnostic and default-only is visible, not blocking.

- [ ] **Step 1: Add docs test first**

Append to `tests/test_operator_docs_contract_policy.py`:

```python
def test_active_docs_describe_per_card_closure_without_second_gate():
    active_text = "\n".join(
        [
            Path("docs/operator/README.md").read_text(encoding="utf-8"),
            Path("docs/operator/guide-research-policy.md").read_text(encoding="utf-8"),
            Path(".agents/skills/hsconfig/SKILL.md").read_text(encoding="utf-8"),
        ]
    )

    assert "per-card closure" in active_text
    assert "default_only_runtime_surface_details" in active_text
    assert "operator_summary.json remains the only normal apply authority" in active_text
    assert "source_to_runtime_explainability.json" in active_text
```

- [ ] **Step 2: Run the docs test to verify it fails**

Run:

```powershell
python -m pytest tests\test_operator_docs_contract_policy.py::test_active_docs_describe_per_card_closure_without_second_gate -q
```

Expected: FAIL until docs mention the new fields.

- [ ] **Step 3: Update docs with exact short text**

Add this paragraph to `docs/operator/guide-research-policy.md` near the source-contract audit section:

```markdown
`source_to_runtime_explainability.json` includes per-card closure rows. Each row
shows whether the card is runtime-backed, source-action-needed,
diagnostic-only, or baseline-only-visible. `default_only_runtime_surface_details`
in `operator_summary.json` summarizes any default-only surface risk, but it is
diagnostic-only; `operator_summary.json remains the only normal apply authority`.
```

Add this bullet to `docs/operator/README.md` near the default-only section:

```markdown
- If `default_only_runtime_surfaces` is not empty, open
  `default_only_runtime_surface_details` and
  `reports/source_to_runtime_explainability.json`. The per-card closure rows
  show the first missing link without creating a second apply gate.
```

Add this bullet to `.agents/skills/hsconfig/SKILL.md` near the reports list:

```markdown
- Use `source_to_runtime_explainability.json` per-card closure rows to explain
  source-backed, policy-backed, diagnostic-only, baseline-only-visible, and
  first-missing-link states. `default_only_runtime_surface_details` is
  diagnostic; operator_summary.json remains the only normal apply authority.
```

- [ ] **Step 4: Run docs and skill tests**

Run:

```powershell
python -m pytest tests\test_operator_docs_contract_policy.py tests\test_skill_files.py::test_skill_and_workflow_stay_compact_and_canonical -q
```

Expected: all selected docs/skill tests pass.

- [ ] **Step 5: Commit**

```powershell
git add docs\operator\README.md docs\operator\guide-research-policy.md .agents\skills\hsconfig\SKILL.md tests\test_operator_docs_contract_policy.py
git commit -m "docs: explain per card source runtime closure"
```

---

### Task 7: Final Verification And GitHub Sync

**Files:**
- No implementation files unless previous tasks failed and required a fix.

**Interfaces:**
- Consumes: all tasks above.
- Produces: green targeted suite, clean git status, pushed `main`.

- [ ] **Step 1: Run targeted closure suite**

Run:

```powershell
python -m pytest tests\test_source_to_runtime_explainability.py tests\test_operator_summary.py tests\test_source_contract_closure_wave.py tests\test_universal_wild_no_block_matrix.py tests\test_operator_docs_contract_policy.py -q
```

Expected: all tests pass.

- [ ] **Step 2: Run broader guard suite**

Run:

```powershell
python -m pytest tests\test_claim_kind_runtime_contract.py tests\test_surface_authority_split.py tests\test_prepare_cli.py tests\test_shadowpriest_e2e.py tests\test_skill_files.py -q
```

Expected: all tests pass.

- [ ] **Step 3: Run full test suite**

Run:

```powershell
python -m pytest -q
```

Expected: full suite passes. If it exceeds normal runtime, capture the last completed test and rerun the failed/unfinished subset.

- [ ] **Step 4: Check git status**

Run:

```powershell
git status --short --branch
```

Expected:

```text
## main...origin/main [ahead N]
```

No unstaged files except intentionally ignored local caches.

- [ ] **Step 5: Push**

Run:

```powershell
git push origin main
```

Expected: push succeeds.

---

## Self-Review

- **Spec coverage:** The plan covers research-deep hardening, per-card source/runtime closure, no silent default-only details, false effect-to-mulligan canaries, any-deck no-block behavior, docs/skill alignment, and final verification.
- **Completion scan:** No incomplete markers or unspecified “add tests” steps remain. Every task lists files, interfaces, code snippets, commands, and expected outcomes.
- **Type consistency:** Public function signatures stay unchanged except the additive `default_only_runtime_surface_details` projection. `build_source_to_runtime_explainability_report(...)` remains the source of card closure rows. `operator_summary.json` remains the only normal apply authority.
- **Scope check:** This is one cohesive plan because every task improves the same source-to-runtime closure chain without introducing new runtime surfaces, dependencies, or gates.

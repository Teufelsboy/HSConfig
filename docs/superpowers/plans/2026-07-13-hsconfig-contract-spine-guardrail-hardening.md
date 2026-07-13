# HSConfig Contract Spine Guardrail Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep HSConfig autonomously usable for any valid deck while preventing false source-to-runtime lowering across Mulligan, GlobalValues, CardID, and Combo surfaces.

**Architecture:** Add a thin claim-family registry and sentinel checks over the existing source-contract spine instead of introducing a second runtime authority. Preserve the current subtractive flow: source claim -> lifecycle/conflict quarantine -> surface gate -> builder/router -> runtime file or diagnostic suppression. Runtime apply remains controlled only by `reports/operator_summary.json` and the guarded apply path.

**Tech Stack:** Python package under `src/hsconfig`, pytest, existing CLI module `hsconfig.cli`, existing Superpowers docs under `docs/superpowers`, optional GitHub Actions workflow.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig`.
- Do not create a new pipeline, runtime writer, or second apply gate.
- Normal runtime output remains `GlobalValues.json`, `Mulligan.json`, per-card `<CARDID>.json`, and `Combo.json` only when concrete ordered combo evidence exists.
- `Presume.json` and `Concede.json` remain known but non-normal surfaces; their absence never blocks a valid package and their presence in normal output is drift.
- `reports/operator_summary.json` remains the only normal apply authority.
- Diagnostics, source-contract reports, sentinels, explainability reports, and research artifacts must not grant or deny runtime writes.
- Any valid deck must still produce a load-safe package unless there is a technical hard block such as invalid JSON, missing required runtime files, nested runtime files, generated-file mismatch, or forbidden normal-path runtime surface.
- Start-of-game, deckbuilding, hero-power-transform, and card-importance facts must not become Mulligan keeps unless there is explicit opening-hand Mulligan evidence.
- `globalvalue_numeric_tuning` is visible evidence, but Step 1 must not lower it into numeric runtime tuning without runtime evidence.
- Keep changes small, source-backed, and test-first.

---

## File Structure

- Create `src/hsconfig/source_claim_family_registry.py`: derived registry for claim-kind family, conflict-family, negative-boundary, and normal runtime-surface expectations.
- Modify `src/hsconfig/contract_spine_sentinel.py`: include registry drift checks in the existing diagnostic-only sentinel report.
- Create `tests/test_source_claim_family_registry.py`: coverage for registry completeness and critical boundaries.
- Modify `tests/test_semantic_runtime_negative_boundaries.py`: add explicit false-lowering regression rows for start-of-game, Hero Power, Discover/Choose One identity, generated entities, vague Combo, and runtime-evidence-only GlobalValues.
- Modify `tests/test_universal_wild_no_block_matrix.py`: keep the any-deck no-block contract visible when warnings and suppressed rows exist.
- Create `.github/workflows/contract-spine.yml`: run the focused contract-spine guard suite in CI.
- Modify `docs/operator/README.md`: keep operator path short and point deep contract detail to `docs/operator/guide-research-policy.md`.
- Modify `docs/operator/guide-research-policy.md`: add the compact "claim family guardrail" rule and link it to the sentinel.
- Modify `tests/test_docs_active_path.py` and `tests/test_operator_docs_contract_policy.py`: lock the active docs to one normal gate and no normal `Presume.json`/`Concede.json`.

---

### Task 1: Add Claim Family Registry And Sentinel Drift Checks

**Files:**
- Create: `src/hsconfig/source_claim_family_registry.py`
- Modify: `src/hsconfig/contract_spine_sentinel.py`
- Test: `tests/test_source_claim_family_registry.py`
- Test: `tests/test_contract_spine_sentinel.py`
- Test: `tests/test_contract_spine_sentinel_cli.py`

**Interfaces:**
- Consumes: `source_contract_policy_by_claim_kind() -> dict[str, dict[str, object]]`
- Consumes: `SUPPORTED_ATOMIC_CLAIM_KINDS: frozenset[str]`
- Produces: `claim_family_registry() -> dict[str, dict[str, object]]`
- Produces: `build_claim_family_registry_report() -> dict[str, object]`
- Produces sentinel check key: `claim_family_registry`

- [ ] **Step 1: Write failing registry completeness tests**

Add this file:

```python
# tests/test_source_claim_family_registry.py
from hsconfig.source_claim_family_registry import (
    build_claim_family_registry_report,
    claim_family_registry,
)
from hsconfig.source_contract_matrix import source_contract_policy_by_claim_kind
from hsconfig.source_document_model import SUPPORTED_ATOMIC_CLAIM_KINDS


def test_claim_family_registry_covers_every_supported_claim_kind():
    registry = claim_family_registry()
    policy = source_contract_policy_by_claim_kind()

    assert set(registry) == set(SUPPORTED_ATOMIC_CLAIM_KINDS)
    assert set(registry) == set(policy)
    for claim_kind, row in registry.items():
        assert row["claim_kind"] == claim_kind
        assert row["policy_lane"] == policy[claim_kind]["lane"]
        assert row["allowed_surfaces"] == policy[claim_kind]["allowed_surfaces"]
        assert row["operator_gate_impact"] == "diagnostic_only"
        assert row["normal_apply_gate"] == "reports/operator_summary.json"


def test_critical_false_lowering_boundaries_are_named():
    registry = claim_family_registry()

    assert registry["hero_power_transform"]["negative_boundary"] == (
        "not_opening_hand_keep_without_explicit_mulligan_claim"
    )
    assert registry["globalvalue_numeric_tuning"]["negative_boundary"] == (
        "requires_runtime_evidence_before_numeric_write"
    )
    assert registry["discover_choice"]["negative_boundary"] == (
        "requires_exact_option_identity"
    )
    assert registry["choose_one_choice"]["negative_boundary"] == (
        "requires_exact_option_identity"
    )
    assert registry["combo_sequence"]["negative_boundary"] == (
        "requires_complete_ordered_sequence"
    )


def test_claim_family_registry_report_is_clean_for_current_contract():
    report = build_claim_family_registry_report()

    assert report["status"] == "clean"
    assert report["authority"] == "diagnostic_only"
    assert report["apply_blocking"] is False
    assert report["problems"] == []
```

- [ ] **Step 2: Run tests and verify they fail because the module does not exist**

Run:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_source_claim_family_registry.py -q
```

Expected:

```text
ModuleNotFoundError: No module named 'hsconfig.source_claim_family_registry'
```

- [ ] **Step 3: Create the thin registry module**

Create:

```python
# src/hsconfig/source_claim_family_registry.py
from __future__ import annotations

from typing import Any

from hsconfig.source_contract_matrix import source_contract_policy_by_claim_kind
from hsconfig.source_document_model import SUPPORTED_ATOMIC_CLAIM_KINDS


NORMAL_APPLY_GATE = "reports/operator_summary.json"
DIAGNOSTIC_AUTHORITY = "diagnostic_only"

_CONFLICT_FAMILY_BY_CLAIM_KIND = {
    "mulligan_keep": "mulligan",
    "mulligan_discard": "mulligan",
    "targeting_rule": "targeting",
    "combo_sequence": "combo_timing",
    "discover_choice": "option_choice",
    "choose_one_choice": "option_choice",
    "card_role": "role_vs_known_bad_pattern",
    "known_bad_pattern": "role_vs_known_bad_pattern",
}

_NEGATIVE_BOUNDARY_BY_CLAIM_KIND = {
    "archetype": "report_only_not_runtime_surface",
    "mulligan_keep": "requires_explicit_opening_hand_intent",
    "mulligan_discard": "requires_explicit_opening_hand_discard_intent",
    "card_role": "requires_supported_cardid_surface",
    "targeting_rule": "requires_supported_target_and_block_identity",
    "combo_sequence": "requires_complete_ordered_sequence",
    "gameplan_posture": "posture_only_not_numeric_tuning",
    "hero_power_transform": "not_opening_hand_keep_without_explicit_mulligan_claim",
    "mechanic_usage": "requires_documented_cardid_surface",
    "known_bad_pattern": "requires_supported_negative_behavior_row",
    "tech_slot": "report_only_deck_construction_advice",
    "replacement_option": "report_only_deck_construction_advice",
    "discover_choice": "requires_exact_option_identity",
    "choose_one_choice": "requires_exact_option_identity",
    "globalvalue_numeric_tuning": "requires_runtime_evidence_before_numeric_write",
}


def claim_family_registry() -> dict[str, dict[str, Any]]:
    """Return derived claim-family guardrails for the source-contract spine.

    This registry is diagnostic. It must not become an apply gate.
    Runtime writes remain controlled by reports/operator_summary.json.
    """
    policy = source_contract_policy_by_claim_kind()
    return {
        claim_kind: {
            "claim_kind": claim_kind,
            "policy_lane": row["lane"],
            "allowed_surfaces": tuple(row["allowed_surfaces"]),
            "conflict_family": _CONFLICT_FAMILY_BY_CLAIM_KIND.get(
                claim_kind,
                "none",
            ),
            "negative_boundary": _NEGATIVE_BOUNDARY_BY_CLAIM_KIND[claim_kind],
            "operator_gate_impact": DIAGNOSTIC_AUTHORITY,
            "normal_apply_gate": NORMAL_APPLY_GATE,
        }
        for claim_kind, row in sorted(policy.items())
    }


def build_claim_family_registry_report() -> dict[str, Any]:
    registry = claim_family_registry()
    problems = _registry_problems(registry)
    return {
        "schema_version": 1,
        "status": "clean" if not problems else "drift_detected",
        "authority": DIAGNOSTIC_AUTHORITY,
        "apply_blocking": False,
        "normal_apply_gate": NORMAL_APPLY_GATE,
        "registry": registry,
        "problems": problems,
    }


def _registry_problems(registry: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    problems: list[dict[str, Any]] = []
    expected = set(SUPPORTED_ATOMIC_CLAIM_KINDS)
    actual = set(registry)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing:
        problems.append({"check": "missing_claim_kinds", "value": missing})
    if extra:
        problems.append({"check": "extra_claim_kinds", "value": extra})

    for claim_kind, row in sorted(registry.items()):
        if row.get("operator_gate_impact") != DIAGNOSTIC_AUTHORITY:
            problems.append(
                {
                    "check": "non_diagnostic_operator_gate_impact",
                    "claim_kind": claim_kind,
                    "value": row.get("operator_gate_impact"),
                }
            )
        if row.get("normal_apply_gate") != NORMAL_APPLY_GATE:
            problems.append(
                {
                    "check": "wrong_normal_apply_gate",
                    "claim_kind": claim_kind,
                    "value": row.get("normal_apply_gate"),
                }
            )
        if not row.get("negative_boundary"):
            problems.append(
                {
                    "check": "missing_negative_boundary",
                    "claim_kind": claim_kind,
                }
            )
    return problems
```

- [ ] **Step 4: Add registry checks to the existing sentinel**

Modify `src/hsconfig/contract_spine_sentinel.py`:

```python
from hsconfig.source_claim_family_registry import build_claim_family_registry_report
```

Inside `build_contract_spine_sentinel_report()`, after `checks = { ... }` has been built, add:

```python
    family_registry_report = build_claim_family_registry_report()
    checks["claim_family_registry"] = {
        "status": family_registry_report["status"],
        "authority": family_registry_report["authority"],
        "apply_blocking": family_registry_report["apply_blocking"],
        "problem_count": len(family_registry_report["problems"]),
    }
```

Inside `_problems(checks: dict[str, Any])`, before `return problems`, add:

```python
    family_registry = checks.get("claim_family_registry", {})
    if family_registry.get("status") != "clean":
        problems.append(
            {
                "check": "claim_family_registry",
                "value": family_registry,
            }
        )
    if family_registry.get("authority") != "diagnostic_only":
        problems.append(
            {
                "check": "claim_family_registry_authority",
                "value": family_registry,
            }
        )
    if family_registry.get("apply_blocking") is not False:
        problems.append(
            {
                "check": "claim_family_registry_apply_blocking",
                "value": family_registry,
            }
        )
```

- [ ] **Step 5: Extend sentinel tests**

Modify `tests/test_contract_spine_sentinel.py` by adding:

```python
def test_contract_spine_sentinel_includes_claim_family_registry():
    report = build_contract_spine_sentinel_report()
    registry = report["checks"]["claim_family_registry"]

    assert registry == {
        "status": "clean",
        "authority": "diagnostic_only",
        "apply_blocking": False,
        "problem_count": 0,
    }
    assert report["apply_blocking"] is False
```

- [ ] **Step 6: Run focused tests**

Run:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_source_claim_family_registry.py tests/test_contract_spine_sentinel.py tests/test_contract_spine_sentinel_cli.py -q
```

Expected:

```text
passed
```

- [ ] **Step 7: Commit Task 1**

```powershell
git add src/hsconfig/source_claim_family_registry.py src/hsconfig/contract_spine_sentinel.py tests/test_source_claim_family_registry.py tests/test_contract_spine_sentinel.py
git commit -m "test: guard claim family contract spine"
```

---

### Task 2: Add Negative Runtime-Lowering Regression Matrix

**Files:**
- Modify: `tests/test_semantic_runtime_negative_boundaries.py`
- Modify only if tests fail: `src/hsconfig/source_document_model.py`
- Modify only if tests fail: `src/hsconfig/card_behavior_surface_router.py`
- Modify only if tests fail: `src/hsconfig/compile_combo.py`
- Modify only if tests fail: `src/hsconfig/globalvalues_authority.py`

**Interfaces:**
- Consumes: `surface_gate_decision(claim: Mapping[str, Any], surface: str, context: Mapping[str, Any] | None = None) -> SurfaceGateDecision`
- Consumes: `can_lower_to_mulligan()`, `can_lower_to_globalvalues()`, `can_lower_to_combo()`, `can_lower_to_cardid()`
- Produces: documented regression coverage for false source-to-runtime lowering.

- [ ] **Step 1: Add failing negative-boundary tests**

Append to `tests/test_semantic_runtime_negative_boundaries.py`:

```python
import pytest

from hsconfig.source_document_model import surface_gate_decision


@pytest.mark.parametrize(
    ("claim", "surface", "expected_reason"),
    [
        (
            {
                "claim_id": "darkbishop_effect_only",
                "claim_kind": "hero_power_transform",
                "claim_readiness": "guide_backed",
                "cards": ["SW_448"],
                "semantic_qualifiers": {
                    "timing": "start_of_game",
                    "state_requirements": "hero_power_transform",
                },
            },
            "mulligan",
            "claim_kind_not_mulligan_surface",
        ),
        (
            {
                "claim_id": "deck_effect_misread_as_keep",
                "claim_kind": "mulligan_keep",
                "claim_readiness": "guide_backed",
                "cards": ["SW_448"],
                "semantic_qualifiers": {
                    "timing": "start_of_game",
                    "zone_scope": "deck",
                },
            },
            "mulligan",
            "start_of_game_effect_does_not_require_opening_hand",
        ),
        (
            {
                "claim_id": "runtime_only_globalvalue",
                "claim_kind": "globalvalue_numeric_tuning",
                "claim_readiness": "guide_backed",
                "key": "FirstTurnValueWeight",
                "runtime_value": 1.2,
            },
            "globalvalues",
            "requires_runtime_evidence",
        ),
        (
            {
                "claim_id": "discover_without_option",
                "claim_kind": "discover_choice",
                "claim_readiness": "guide_backed",
                "cards": ["DISCOVER_TEST_CARD"],
            },
            "mulligan",
            "claim_kind_not_mulligan_surface",
        ),
        (
            {
                "claim_id": "vague_combo_not_mulligan",
                "claim_kind": "combo_sequence",
                "claim_readiness": "guide_backed",
                "cards": ["CARD_A"],
                "sequence": ["CARD_A"],
            },
            "mulligan",
            "claim_kind_not_mulligan_surface",
        ),
    ],
)
def test_false_runtime_lowering_boundaries_do_not_cross_surfaces(
    claim,
    surface,
    expected_reason,
):
    decision = surface_gate_decision(claim, surface)

    assert decision.allowed is False
    assert decision.reason == expected_reason
```

- [ ] **Step 2: Run the negative-boundary test**

Run:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_semantic_runtime_negative_boundaries.py -q
```

Expected:

```text
passed
```

If this fails, change only the specific gate or router named by the assertion. Do not relax the test by changing `expected_reason`.

- [ ] **Step 3: Add exact CardID and Combo suppression checks**

Append:

```python
from hsconfig.card_behavior_surface_router import route_card_behavior_claims
from hsconfig.compile_combo import build_combo_config


def test_discover_choice_without_option_identity_is_suppressed_not_lowered():
    claims = [
        {
            "claim_id": "discover_generic_burn",
            "claim_kind": "discover_choice",
            "claim_readiness": "guide_backed",
            "cards": ["DISCOVER_TEST_CARD"],
            "evidence_text_short": "Choose burn from Discover.",
        }
    ]

    routed = route_card_behavior_claims(claims, cards={"DISCOVER_TEST_CARD": {"name": "Discover Test"}})

    assert routed["runtime_rows"] == []
    assert routed["suppressed_rows"][0]["claim_id"] == "discover_generic_burn"
    assert routed["suppressed_rows"][0]["reason"] in {
        "requires_exact_option_identity",
        "unresolved_option_identity",
    }


def test_one_card_or_vague_combo_sequence_does_not_emit_combo_json_rows():
    contract = {
        "claims": [
            {
                "claim_id": "vague_combo",
                "claim_kind": "combo_sequence",
                "claim_readiness": "guide_backed",
                "cards": ["CARD_A"],
                "sequence": ["CARD_A"],
            }
        ]
    }

    combo = build_combo_config(contract)

    assert combo["combos"] == []
    assert combo["suppressed_rows"][0]["claim_id"] == "vague_combo"
    assert combo["suppressed_rows"][0]["reason"] == "sequence_too_short"
```

If signatures differ in the live modules, inspect the exact helper tests already in `tests/test_card_behavior_router.py` and `tests/test_compile_combo.py`, then adapt only the call shape while preserving the assertions and reasons.

- [ ] **Step 4: Run router/compiler tests**

Run:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_semantic_runtime_negative_boundaries.py tests/test_card_behavior_router.py tests/test_compile_combo.py -q
```

Expected:

```text
passed
```

- [ ] **Step 5: Commit Task 2**

```powershell
git add tests/test_semantic_runtime_negative_boundaries.py src/hsconfig/source_document_model.py src/hsconfig/card_behavior_surface_router.py src/hsconfig/compile_combo.py src/hsconfig/globalvalues_authority.py
git commit -m "test: lock false runtime lowering boundaries"
```

---

### Task 3: Keep Any-Deck No-Block Contract And Add CI Sentinel

**Files:**
- Modify: `tests/test_universal_wild_no_block_matrix.py`
- Create: `.github/workflows/contract-spine.yml`
- Test: `tests/test_apply_authority_boundary.py`
- Test: `tests/test_no_second_gate_contract.py`
- Test: `tests/test_universal_wild_no_block_matrix.py`

**Interfaces:**
- Consumes: existing helper `assert_load_safe_no_block_package(operator_summary: dict)`
- Produces: CI workflow that runs the focused guardrail suite.

- [ ] **Step 1: Add warning-bearing no-block package regression**

Append to `tests/test_universal_wild_no_block_matrix.py`:

```python
def test_warning_bearing_future_mechanic_package_still_load_safe(tmp_path):
    result = build_deck_package_for_matrix(
        tmp_path,
        deck_name="FutureMechanicNoBlock",
        deck_code=SHADOWPRIEST_DECK_CODE,
        source_claims=[
            {
                "claim_id": "future_keyword_visible",
                "claim_kind": "future_claim_kind",
                "claim_readiness": "contract_gap",
                "cards": ["FUTURE_001"],
                "mechanic": "future_keyword",
                "evidence_text_short": "Future keyword should be visible but not blocking.",
            },
            {
                "claim_id": "runtime_only_globalvalue_visible",
                "claim_kind": "globalvalue_numeric_tuning",
                "claim_readiness": "guide_backed",
                "key": "FirstTurnValueWeight",
                "runtime_value": 1.3,
                "evidence_text_short": "Runtime value request requires post-game evidence.",
            },
        ],
    )
    operator_summary = result["operator_summary"]

    assert_load_safe_no_block_package(operator_summary)
    assert operator_summary["runtime_apply_contract"]["apply_authority"] == (
        "reports/operator_summary.json"
    )
    assert operator_summary["no_block_failure_mode_summary"]["hard_block"] is False
```

If `build_deck_package_for_matrix` or `SHADOWPRIEST_DECK_CODE` has a different live name, reuse the existing helper and deck constant from the same file without changing the assertion intent.

- [ ] **Step 2: Run no-block and apply-authority tests**

Run:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_universal_wild_no_block_matrix.py tests/test_apply_authority_boundary.py tests/test_no_second_gate_contract.py -q
```

Expected:

```text
passed
```

- [ ] **Step 3: Create CI workflow**

Create `.github/workflows/contract-spine.yml`:

```yaml
name: contract-spine

on:
  push:
    branches: [main, "codex/**"]
  pull_request:
    branches: [main]

jobs:
  guardrails:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install package
        run: python -m pip install -e .
      - name: Run contract-spine guard suite
        env:
          PYTHONPATH: src
        run: >
          python -m pytest
          tests/test_source_claim_family_registry.py
          tests/test_claim_kind_runtime_contract.py
          tests/test_semantic_runtime_negative_boundaries.py
          tests/test_contract_spine_sentinel.py
          tests/test_contract_spine_sentinel_cli.py
          tests/test_apply_authority_boundary.py
          tests/test_no_second_gate_contract.py
          tests/test_universal_wild_no_block_matrix.py
          -q
      - name: Run contract-spine sentinel
        env:
          PYTHONPATH: src
        run: python -m hsconfig.cli contract-spine-sentinel --json
```

- [ ] **Step 4: Run the CI command locally**

Run:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_source_claim_family_registry.py tests/test_claim_kind_runtime_contract.py tests/test_semantic_runtime_negative_boundaries.py tests/test_contract_spine_sentinel.py tests/test_contract_spine_sentinel_cli.py tests/test_apply_authority_boundary.py tests/test_no_second_gate_contract.py tests/test_universal_wild_no_block_matrix.py -q
python -m hsconfig.cli contract-spine-sentinel --json
```

Expected:

```text
passed
"status": "clean"
"apply_blocking": false
```

- [ ] **Step 5: Commit Task 3**

```powershell
git add tests/test_universal_wild_no_block_matrix.py .github/workflows/contract-spine.yml
git commit -m "ci: enforce contract spine guardrails"
```

---

### Task 4: Slim Operator Docs Around One Gate And One Normal Path

**Files:**
- Modify: `docs/operator/README.md`
- Modify: `docs/operator/guide-research-policy.md`
- Modify: `tests/test_docs_active_path.py`
- Modify: `tests/test_operator_docs_contract_policy.py`

**Interfaces:**
- Consumes: active operator docs.
- Produces: a short operator path plus a deeper guardrail reference.

- [ ] **Step 1: Add docs tests first**

Append to `tests/test_operator_docs_contract_policy.py`:

```python
from pathlib import Path


def test_operator_docs_keep_one_apply_authority_and_no_second_gate_language():
    root = Path(__file__).resolve().parents[1]
    operator_readme = (root / "docs/operator/README.md").read_text(encoding="utf-8")
    guide_policy = (
        root / "docs/operator/guide-research-policy.md"
    ).read_text(encoding="utf-8")

    combined = operator_readme + "\n" + guide_policy

    assert "reports/operator_summary.json remains the only normal apply authority" in combined
    assert "source_contract_audit.json is diagnostic" in combined
    assert "Presume.json" in combined
    assert "Concede.json" in combined
    assert "normal-path Presume.json" not in combined
    assert "normal-path Concede.json" not in combined
```

Append to `tests/test_docs_active_path.py`:

```python
def test_operator_readme_starts_with_short_configure_path():
    text = Path("docs/operator/README.md").read_text(encoding="utf-8")
    first_120_lines = "\n".join(text.splitlines()[:120])

    assert "hsconfig configure" in first_120_lines
    assert "reports/operator_summary.json" in first_120_lines
    assert "contract-spine-sentinel" not in first_120_lines
```

- [ ] **Step 2: Run docs tests and verify current behavior**

Run:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_docs_active_path.py tests/test_operator_docs_contract_policy.py -q
```

Expected before doc slimming:

```text
failed
```

The expected failure is `contract-spine-sentinel` appearing too early in `docs/operator/README.md` or missing exact one-gate wording.

- [ ] **Step 3: Slim `docs/operator/README.md`**

Edit the first normal-operator section so it follows this structure:

```markdown
## Normal Path

1. Run `hsconfig configure`.
2. Open `outputs/<DeckName>/04_package/reports/operator_summary.json`.
3. Apply only through `hsconfig apply` or `hsconfig configure --apply`.

`reports/operator_summary.json` remains the only normal apply authority.
Other reports are diagnostic. They explain source quality, mechanic coverage,
ownership, and missing links; they do not grant apply permission.

Normal HSConfig output is limited to `GlobalValues.json`, `Mulligan.json`,
per-card `<CARDID>.json`, and `Combo.json` when exact ordered combo evidence
exists. `Presume.json` and `Concede.json` are known VisionAI surfaces, but they
are outside the normal output path.
```

Move deeper sentinel, matrix, mechanic visibility, and explainability detail below the first 120 lines or into links to `docs/operator/guide-research-policy.md`.

- [ ] **Step 4: Add compact guardrail rule to guide policy**

Add this section to `docs/operator/guide-research-policy.md` near the source-to-runtime policy section:

```markdown
## Claim Family Guardrail

Every supported `claim_kind` has exactly one policy lane, one allowed runtime
surface set, one negative-boundary rule, and one diagnostic conflict family.
Changing a claim kind means updating the claim-family registry, the source
contract matrix, the runtime surface gate, the builder/router tests, and the
contract-spine sentinel together.

The guardrail is diagnostic only. It protects the source-to-runtime contract,
but it does not create another apply gate. `reports/operator_summary.json`
remains the only normal apply authority.
```

- [ ] **Step 5: Run docs tests**

Run:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_docs_active_path.py tests/test_operator_docs_contract_policy.py -q
```

Expected:

```text
passed
```

- [ ] **Step 6: Commit Task 4**

```powershell
git add docs/operator/README.md docs/operator/guide-research-policy.md tests/test_docs_active_path.py tests/test_operator_docs_contract_policy.py
git commit -m "docs: keep contract spine operator path slim"
```

---

### Task 5: Final Verification And Research Artifact Decision

**Files:**
- Review: `docs/research/2026-07-13-hsconfig-source-contract-logic-brainstorm-v7/`
- Review: `docs/superpowers/plans/2026-07-13-hsconfig-contract-spine-guardrail-hardening.md`
- No production file changes unless a verification failure identifies a concrete defect.

**Interfaces:**
- Consumes: all changes from Tasks 1-4.
- Produces: verified branch ready for push or PR.

- [ ] **Step 1: Run focused guardrail suite**

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_source_claim_family_registry.py tests/test_claim_kind_runtime_contract.py tests/test_semantic_runtime_negative_boundaries.py tests/test_contract_spine_sentinel.py tests/test_contract_spine_sentinel_cli.py tests/test_apply_authority_boundary.py tests/test_no_second_gate_contract.py tests/test_universal_wild_no_block_matrix.py tests/test_docs_active_path.py tests/test_operator_docs_contract_policy.py -q
```

Expected:

```text
passed
```

- [ ] **Step 2: Run sentinel**

```powershell
$env:PYTHONPATH='src'
python -m hsconfig.cli contract-spine-sentinel --json
```

Expected JSON includes:

```json
{
  "status": "clean",
  "authority": "diagnostic_only",
  "apply_blocking": false
}
```

- [ ] **Step 3: Run broad suite**

```powershell
$env:PYTHONPATH='src'
python -m pytest -q
```

Expected:

```text
passed
```

- [ ] **Step 4: Validate Research-Deep artifacts**

```powershell
$fields = '.\docs\research\2026-07-13-hsconfig-source-contract-logic-brainstorm-v7\fields.yaml'
Get-ChildItem -File .\docs\research\2026-07-13-hsconfig-source-contract-logic-brainstorm-v7\results\*.json | ForEach-Object {
  python C:\Users\darbo\.codex\skills\research\validate_json.py -f $fields -j $_.FullName
}
```

Expected for every file:

```text
[PASS]
Coverage: 100.0% (10/10)
```

- [ ] **Step 5: Review git diff**

```powershell
git status --short --branch
git diff --stat
git diff -- . ':!docs/research/**/results/*.json'
```

Expected:

```text
Only planned files changed.
No raw runtime evidence, no replay files, no private logs.
```

- [ ] **Step 6: Commit plan and research artifacts if they are kept**

If the Research-Deep package is kept as source-backed rationale for this wave:

```powershell
git add docs/research/2026-07-13-hsconfig-source-contract-logic-brainstorm-v7 docs/superpowers/plans/2026-07-13-hsconfig-contract-spine-guardrail-hardening.md
git commit -m "docs: record contract spine guardrail plan"
```

If the Research-Deep package is considered temporary, remove only that untracked research folder and commit the plan alone:

```powershell
Remove-Item -Recurse -Force .\docs\research\2026-07-13-hsconfig-source-contract-logic-brainstorm-v7
git add docs/superpowers/plans/2026-07-13-hsconfig-contract-spine-guardrail-hardening.md
git commit -m "docs: plan contract spine guardrail hardening"
```

- [ ] **Step 7: Push branch**

```powershell
git push origin HEAD
```

Expected:

```text
Everything up-to-date
```

or a successful push of the current branch.

---

## Self-Review

- Spec coverage: The plan implements the recommended guardrail wave: claim-family registry, negative runtime-lowering tests, no-block protection, CI sentinel, and operator doc slimming.
- Placeholder scan: The plan contains no unfinished markers, unnamed files, or unspecified test commands.
- Type consistency: The plan uses existing live interfaces where available: `source_contract_policy_by_claim_kind`, `SUPPORTED_ATOMIC_CLAIM_KINDS`, `surface_gate_decision`, `build_contract_spine_sentinel_report`, and `reports/operator_summary.json`.
- Scope check: This is one cohesive guardrail-hardening wave. It does not add runtime surfaces, a second apply authority, new deck workflows, replay analysis, winrate analysis, or HSTuner behavior.

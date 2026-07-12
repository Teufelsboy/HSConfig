# HSConfig Contract-Spine Guardrail Wave Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Freeze the current HSConfig source-to-runtime contract spine so future changes stay autonomous and non-blocking without allowing false runtime claims.

**Architecture:** Keep the existing architecture intact: source claims normalize into atomic `claim_kind` values, surface gates decide whether each claim may lower into `Mulligan.json`, `GlobalValues.json`, per-card `<CARDID>.json`, or `Combo.json`, and `operator_summary.json` remains the only normal apply authority. Add guardrail tests and one compact operator checklist; do not introduce another gate, another pipeline, or new dependencies.

**Tech Stack:** Python 3, pytest, existing `hsconfig` modules under `src/hsconfig`, existing operator docs under `docs/operator`, existing skill docs under `.agents/skills/hsconfig`.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig`.
- Do not add dependencies.
- Do not change runtime apply authority away from `reports/operator_summary.json`.
- `source_contract_audit.json`, `claim_lifecycle_rows`, and `contract_spine_rows` remain diagnostic only.
- Keep normal runtime outputs limited to `GlobalValues.json`, `Mulligan.json`, per-card `<CARDID>.json`, and exact `Combo.json`.
- Do not add `Presume.json` or `Concede.json` to the default normal path.
- Do not turn card importance, start-of-game effects, deckbuilding effects, or hero-power-transform text into opening-hand keeps.
- Keep `globalvalue_numeric_tuning` report-visible and runtime-evidence-required in Step 1.
- Preserve no-block behavior: a technically valid, load-safe deck package must not fail only because source strength is thin.

---

## File Structure

- Modify `tests/test_source_contract_conformance.py`
  - Add critical contract-spine invariant tests around the existing `build_source_contract_conformance_snapshot()` output.
- Create `tests/test_apply_authority_boundary.py`
  - Add an active-path scan proving apply/runtime write paths do not import or consume source-contract diagnostic artifacts.
- Create `tests/test_semantic_runtime_negative_boundaries.py`
  - Add focused negative tests for start-of-game, numeric tuning, unresolved option identity, and vague combo/source claims.
- Modify `docs/operator/guide-research-policy.md`
  - Add a compact “Adding A New Claim Kind” checklist.
- Modify `.agents/skills/hsconfig/SKILL.md`
  - Add the same one-screen checklist summary for future agent runs.
- No production code should be changed unless a new test exposes an actual drift from the intended behavior.

---

### Task 1: Freeze Critical Contract-Spine Rows

**Files:**
- Modify: `tests/test_source_contract_conformance.py`
- Test: `tests/test_source_contract_conformance.py`

**Interfaces:**
- Consumes: `hsconfig.source_contract_conformance.build_source_contract_conformance_snapshot() -> dict`
- Produces: regression coverage that freezes the critical claim-kind lifecycle rows without introducing a static snapshot file.

- [ ] **Step 1: Add the failing invariant tests**

Append this test block to `tests/test_source_contract_conformance.py`:

```python
def _spine_row(snapshot: dict, claim_kind: str) -> dict:
    for row in snapshot["contract_spine_rows"]:
        if row["claim_kind"] == claim_kind:
            return row
    raise AssertionError(f"missing contract spine row for {claim_kind}")


def test_contract_spine_keeps_critical_runtime_boundaries_explicit():
    snapshot = build_source_contract_conformance_snapshot()

    assert snapshot["operator_gate_impact"] == "diagnostic_only"

    expectations = {
        "mulligan_keep": {
            "policy_lane": "runtime_lowerable",
            "allowed_surfaces": ["mulligan"],
            "surface_gate_status": "mulligan:allowed",
            "final_runtime_effect": "emits_mulligan_runtime_row",
        },
        "hero_power_transform": {
            "policy_lane": "suppressed_or_conditional",
            "allowed_surfaces": ["cardid"],
            "surface_gate_status": "cardid:allowed",
            "final_runtime_effect": "emits_cardid_runtime_row",
        },
        "globalvalue_numeric_tuning": {
            "policy_lane": "runtime_evidence_required",
            "allowed_surfaces": [],
            "surface_gate_status": "no_allowed_surface",
            "final_runtime_effect": "suppressed_until_runtime_evidence",
        },
        "combo_sequence": {
            "policy_lane": "runtime_lowerable",
            "allowed_surfaces": ["combo"],
            "surface_gate_status": "combo:allowed",
            "final_runtime_effect": "emits_when_builder_prerequisites_are_complete",
        },
        "archetype": {
            "policy_lane": "report_only",
            "allowed_surfaces": [],
            "surface_gate_status": "no_allowed_surface",
            "final_runtime_effect": "report_only_no_runtime_row",
        },
    }

    for claim_kind, expected in expectations.items():
        row = _spine_row(snapshot, claim_kind)
        for key, value in expected.items():
            assert row[key] == value, (claim_kind, key, row)
        assert row["operator_gate_impact"] == "diagnostic_only"


def test_contract_spine_start_of_game_boundary_is_not_a_mulligan_exception():
    snapshot = build_source_contract_conformance_snapshot()
    suppression = snapshot["start_of_game_mulligan_suppression"]

    assert suppression["decision"] == "rejected"
    assert suppression["reason"] == "start_of_game_effect_does_not_require_opening_hand"
    assert "do not become opening-hand keeps" in suppression["operator_meaning"]
```

- [ ] **Step 2: Run the new tests to verify current behavior**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_source_contract_conformance.py -q
```

Expected: all tests pass. If a row fails, inspect the failure before changing implementation; the correct fix is usually in policy/gate alignment, not in the test.

- [ ] **Step 3: Commit**

```powershell
git add tests/test_source_contract_conformance.py
git commit -m "test: freeze source contract spine guardrails"
```

---

### Task 2: Harden The Single Apply-Authority Boundary

**Files:**
- Create: `tests/test_apply_authority_boundary.py`
- Test: `tests/test_apply_authority_boundary.py`

**Interfaces:**
- Consumes: active apply/runtime files as text.
- Produces: regression coverage proving diagnostic artifacts cannot become a second apply gate by import, read, or direct string reference.

- [ ] **Step 1: Write the active-path scan test**

Create `tests/test_apply_authority_boundary.py` with:

```python
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]

ACTIVE_APPLY_PATHS = [
    "src/hsconfig/apply_gate.py",
    "src/hsconfig/runtime_apply.py",
    "src/hsconfig/commands/apply.py",
]

DIAGNOSTIC_ONLY_TOKENS = [
    "source_contract_audit",
    "contract_spine_rows",
    "claim_lifecycle_rows",
    "source_contract_conformance",
]


def _read(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def test_active_apply_paths_do_not_consume_source_contract_diagnostics():
    for relative_path in ACTIVE_APPLY_PATHS:
        content = _read(relative_path)
        for token in DIAGNOSTIC_ONLY_TOKENS:
            assert token not in content, (relative_path, token)


def test_apply_gate_uses_operator_summary_as_single_authority():
    content = _read("src/hsconfig/apply_gate.py")

    assert 'package / "reports" / "operator_summary.json"' in content
    assert "runtime_apply_allowed" in content
    assert "source_contract_audit" not in content
```

- [ ] **Step 2: Run the test and inspect failures**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_apply_authority_boundary.py -q
```

Expected: pass. If it fails because a diagnostic token is imported by an apply file, remove that dependency from the apply path and keep the diagnostic summary inside `operator_summary.py`.

- [ ] **Step 3: Run adjacent boundary tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_no_second_gate_contract.py tests/test_apply_authority_boundary.py -q
```

Expected: pass.

- [ ] **Step 4: Commit**

```powershell
git add tests/test_apply_authority_boundary.py
git commit -m "test: guard operator summary as apply authority"
```

---

### Task 3: Add Semantic Negative Boundary Fixtures

**Files:**
- Create: `tests/test_semantic_runtime_negative_boundaries.py`
- Test: `tests/test_semantic_runtime_negative_boundaries.py`

**Interfaces:**
- Consumes:
  - `hsconfig.source_document_model.can_lower_to_mulligan(claim, card_roles=...)`
  - `hsconfig.source_document_model.can_lower_to_globalvalues(claim)`
  - `hsconfig.card_behavior_surface_router.route_card_behavior_surfaces(claims, identity_links=...)`
  - `hsconfig.combo_plan.build_combo_plan(deck_cards, claims)`
- Produces: regression coverage for the exact over-inference cases this architecture is designed to prevent.

- [ ] **Step 1: Write negative fixture tests**

Create `tests/test_semantic_runtime_negative_boundaries.py` with:

```python
from hsconfig.card_behavior_surface_router import route_card_behavior_surfaces
from hsconfig.combo_plan import build_combo_plan
from hsconfig.source_document_model import (
    can_lower_to_globalvalues,
    can_lower_to_mulligan,
)


def test_start_of_game_hero_power_transform_does_not_lower_to_mulligan_keep():
    claim = {
        "claim_id": "darkbishop_wrong_keep",
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


def test_globalvalue_numeric_tuning_requires_runtime_evidence_in_step1():
    claim = {
        "claim_id": "numeric_tuning_from_guide",
        "claim_kind": "globalvalue_numeric_tuning",
        "claim_readiness": "guide_backed",
        "trust_ceiling": "runtime_candidate",
        "key": "LowHpBoardValuePenalty",
    }

    decision = can_lower_to_globalvalues(claim)

    assert decision.allowed is False
    assert decision.reason == "requires_runtime_evidence"


def test_unresolved_discover_choice_stays_suppressed_until_option_identity_is_linked():
    claim = {
        "claim_id": "discover_without_identity_link",
        "claim_kind": "discover_choice",
        "claim_readiness": "guide_backed",
        "trust_ceiling": "runtime_candidate",
        "cards": ["CARD_001"],
        "option_card_id": "OPTION_001",
    }

    result = route_card_behavior_surfaces([claim], identity_links={})

    assert result["rows"] == []
    assert result["suppressed"][0]["claim_id"] == "discover_without_identity_link"
    assert result["suppressed"][0]["reason"] == "unresolved_choice_option_identity"


def test_vague_combo_sequence_without_two_cards_stays_suppressed():
    claim = {
        "claim_id": "vague_combo",
        "claim_kind": "combo_sequence",
        "claim_readiness": "guide_backed",
        "trust_ceiling": "runtime_candidate",
        "cards": ["CARD_001"],
        "sequence": ["CARD_001"],
        "timing_kind": "same_turn",
        "operator": ">>",
        "values": ["6"],
    }

    result = build_combo_plan(deck_cards={"CARD_001"}, claims=[claim])

    assert result["combos"] == []
    assert result["suppressed"][0]["claim_id"] == "vague_combo"
    assert result["suppressed"][0]["reason"] == "combo_requires_at_least_two_cards"
```

- [ ] **Step 2: Run the test and fix only real drift**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_semantic_runtime_negative_boundaries.py -q
```

Expected: pass. If a reason string has legitimately changed, update the assertion only after checking the new reason still preserves the same product boundary.

- [ ] **Step 3: Run the nearby surface/router tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_surface_authority_split.py tests/test_card_behavior_router.py tests/test_combo_plan.py tests/test_globalvalues_authority.py tests/test_semantic_runtime_negative_boundaries.py -q
```

Expected: pass.

- [ ] **Step 4: Commit**

```powershell
git add tests/test_semantic_runtime_negative_boundaries.py
git commit -m "test: guard semantic runtime negative boundaries"
```

---

### Task 4: Document The Claim-Kind Extension Checklist

**Files:**
- Modify: `docs/operator/guide-research-policy.md`
- Modify: `.agents/skills/hsconfig/SKILL.md`
- Test: `tests/test_skill_docs.py` if present; otherwise use `rg` checks in this task.

**Interfaces:**
- Consumes: existing operator and skill docs.
- Produces: a short extension checklist that prevents future broad claim kinds, wrong-surface lowering, or second gates.

- [ ] **Step 1: Add the operator checklist**

In `docs/operator/guide-research-policy.md`, add this section after the existing source-contract diagnostic explanation:

```markdown
## Adding A New Claim Kind

New claim kinds must follow the same compact spine:

1. Add the atomic claim kind to `SUPPORTED_ATOMIC_CLAIM_KINDS`.
2. Add exactly one policy row in `source_contract_matrix.py`.
3. Decide the allowed surface: `mulligan`, `globalvalues`, `cardid`, `combo`, or none.
4. Add or update the matching surface-gate test.
5. Add builder/router coverage only when the VisionAI surface is documented and syntax-safe.
6. Keep report-only, runtime-evidence-required, unresolved-identity, and warning-only mechanics non-blocking.
7. Keep `operator_summary.json` as the only normal apply authority.

Do not add broad wildcard claim kinds such as `globalvalue_*` or prose-driven
claims that bypass the surface gates.
```

- [ ] **Step 2: Add the skill summary**

In `.agents/skills/hsconfig/SKILL.md`, add this compact bullet list under the current source-contract invariant bullets:

```markdown
- When adding a claim kind, update all four boundaries together:
  `SUPPORTED_ATOMIC_CLAIM_KINDS`, `source_contract_matrix.py`,
  the matching surface gate, and a builder/router or diagnostic test.
- New claim kinds must not create a second apply gate. `operator_summary.json`
  remains the only normal runtime-write authority.
- If the VisionAI surface or identity is unresolved, keep the claim visible in
  reports and do not emit runtime JSON from it.
```

- [ ] **Step 3: Run active-doc scans**

Run:

```powershell
rg -n "second apply gate|source_contract_audit.json.*apply authority|contract_spine_rows.*apply permission" docs/operator .agents/skills/hsconfig
rg -n "operator_summary.json remains the only normal|operator_summary.json.*single operator gate|operator_summary.json.*apply authority" docs/operator .agents/skills/hsconfig
```

Expected:
- First command returns no lines implying diagnostic artifacts are apply authorities.
- Second command returns the existing single-gate statements.

- [ ] **Step 4: Commit**

```powershell
git add docs/operator/guide-research-policy.md .agents/skills/hsconfig/SKILL.md
git commit -m "docs: document claim kind extension guardrails"
```

---

### Task 5: Final Verification And Push

**Files:**
- No code files should be modified in this task.
- Verify: full focused guardrail suite and git state.

**Interfaces:**
- Consumes: all previous task outputs.
- Produces: a verified branch ready for push or merge.

- [ ] **Step 1: Run focused guardrail suite**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_source_contract_conformance.py tests/test_source_contract_audit.py tests/test_surface_authority_split.py tests/test_claim_kind_runtime_contract.py tests/test_no_second_gate_contract.py tests/test_apply_authority_boundary.py tests/test_semantic_runtime_negative_boundaries.py tests/test_mulligan_plan.py tests/test_card_behavior_router.py tests/test_combo_plan.py tests/test_globalvalues_authority.py tests/test_apply_gate.py tests/test_operator_summary.py tests/test_shadowpriest_e2e.py -q
```

Expected: all tests pass.

- [ ] **Step 2: Run full suite if the focused suite is green**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest -q
```

Expected: all tests pass, with only known skips if the repo already has them.

- [ ] **Step 3: Check git status and diff**

Run:

```powershell
git status --short --branch
git diff --stat HEAD
```

Expected:
- Branch is based on `main`.
- Diff only includes tests and compact docs from this plan.

- [ ] **Step 4: Push when requested**

Run only if the user asks to keep GitHub current:

```powershell
git push origin main
```

Expected: push succeeds.

---

## Self-Review

- Spec coverage: The plan covers the recommendation: freeze current contract spine, avoid a second gate, preserve Darkbishop/start-of-game boundaries, keep numeric GlobalValues tuning out of Step 1 runtime, and document how to add new claim kinds without broadening the architecture.
- Placeholder scan: No open placeholder instructions remain.
- Type consistency: The plan uses existing functions and modules verified in the repository: `build_source_contract_conformance_snapshot`, `can_lower_to_mulligan`, `can_lower_to_globalvalues`, `route_card_behavior_surfaces`, and `build_combo_plan`.
- Scope check: This is intentionally a guardrail wave, not a production-code rewrite.

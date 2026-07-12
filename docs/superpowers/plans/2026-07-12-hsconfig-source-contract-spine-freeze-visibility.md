# HSConfig Source Contract Spine Freeze Visibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Freeze and expose the HSConfig source-to-runtime contract spine so autonomous deck config generation stays load-safe, non-blocking, and semantically correct without false runtime lowering.

**Architecture:** Keep the existing single-authority model: source claims are routed by `claim_kind`, surface gates decide whether a claim may lower into runtime JSON, diagnostics explain the chain, and `reports/operator_summary.json` remains the only normal apply authority. This plan adds a compact research-truth anchor, stronger invariant tests, better contract-doctor visibility, and operator docs that make clear that source truth is not runtime authority.

**Tech Stack:** Python, pytest, JSON diagnostics, local Markdown docs. No new dependencies.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig`.
- Do not add a second runtime-write gate.
- `reports/operator_summary.json` remains the only normal apply authority.
- Valid load-safe packages must not block because source depth is imperfect; warnings and source debt stay visible.
- Normal runtime surfaces are `GlobalValues.json`, `Mulligan.json`, per-card `<CARDID>.json`, and optional `Combo.json`.
- `Presume.json` and `Concede.json` stay outside the normal path.
- Start-of-game, deck-state, and hero-power-transform effects do not become opening-hand mulligan keeps unless a separate explicit mulligan claim exists.
- `globalvalue_numeric_tuning` stays runtime-evidence-required and must not lower during Step 1.
- Diagnostics such as `source_contract_audit.json`, `source_contract_conformance`, `contract_spine_rows`, and `contract_doctor` explain decisions only.

---

## File Structure

- Modify: `docs/research/current-truth.md`
  - Adds a compact active-truth pointer to the validated 2026-07-12 research package.
- Create: `tests/test_research_current_truth.py`
  - Guards that the active research pointer exists and does not redefine apply authority.
- Create: `tests/test_source_contract_spine_freeze.py`
  - Freezes supported claim kinds, policy lanes, allowed surfaces, and live surface-gate outcomes.
- Modify: `src/hsconfig/contract_doctor.py`
  - Adds a compact `contract_spine` section to the diagnostic report.
- Modify: `tests/test_contract_doctor.py`
  - Guards that contract-doctor exposes the spine while remaining diagnostic-only.
- Modify: `tests/test_apply_authority_boundary.py`
  - Hardens the single-authority guard against future imports or apply-path drift.
- Modify: `docs/operator/guide-research-policy.md`
  - Adds one explicit "source truth is not runtime authority" section.
- Create: `tests/test_operator_docs_contract_policy.py`
  - Guards the operator policy wording and examples.
- Modify: `tests/test_claim_kind_runtime_contract.py`
  - Adds one generic hero-power-transform/CardID-vs-mulligan regression beyond the ShadowPriest-specific case.

## Subagent Execution Map

- Task 1: Docs/Research worker.
- Task 2: Code/Schema test worker.
- Task 3: Contract Doctor worker.
- Task 4: Apply Authority reviewer.
- Task 5: Docs QA worker.
- Task 6: Hearthstone semantics regression worker.
- Task 7: Final reviewer.

Only one worker should write to each file listed above. All workers should run their task-local tests before handoff.

---

### Task 1: Anchor The Validated Research Package

**Files:**
- Modify: `docs/research/current-truth.md`
- Create: `tests/test_research_current_truth.py`

**Interfaces:**
- Consumes: validated research package at `docs/research/2026-07-12-hsconfig-source-contract-slim-autonomy-brainstorm/`
- Produces: active documentation pointer consumed by future docs and review work

- [ ] **Step 1: Write the failing test**

Create `tests/test_research_current_truth.py`:

```python
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_current_truth_links_source_contract_brainstorm_package():
    text = (ROOT / "docs" / "research" / "current-truth.md").read_text(
        encoding="utf-8"
    )

    assert "2026-07-12-hsconfig-source-contract-slim-autonomy-brainstorm" in text
    assert "source-contract spine" in text.lower()
    assert "operator_summary.json remains the only normal apply authority" in text


def test_current_truth_does_not_turn_research_into_apply_authority():
    text = (ROOT / "docs" / "research" / "current-truth.md").read_text(
        encoding="utf-8"
    )

    forbidden = [
        "source_contract_audit.json authorizes apply",
        "contract_doctor authorizes apply",
        "research authorizes runtime writes",
    ]
    for phrase in forbidden:
        assert phrase not in text.lower()
```

- [ ] **Step 2: Run the test to verify it fails or documents existing coverage**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_research_current_truth.py -q
```

Expected before the doc edit:

```text
FAILED tests/test_research_current_truth.py::test_current_truth_links_source_contract_brainstorm_package
```

If it already passes, inspect `docs/research/current-truth.md` and keep the implementation step to a no-op.

- [ ] **Step 3: Add the active-truth section**

Append this section to `docs/research/current-truth.md`:

```markdown
## 2026-07-12 Source-Contract Spine Truth

Active research package:
`docs/research/2026-07-12-hsconfig-source-contract-slim-autonomy-brainstorm/`.

This package is the current source-contract spine reference for HSConfig. It
confirms that source claims route through `claim_kind`, the policy matrix,
surface gates, builder/router decisions, and diagnostic reports before any
runtime package is considered. `operator_summary.json remains the only normal
apply authority`.

Research and diagnostics explain source quality and runtime-surface decisions;
they do not authorize runtime writes. A valid package may still be
`READY_TO_APPLY_WITH_WARNINGS` when source debt is visible but the runtime
package is load-safe.
```

- [ ] **Step 4: Validate research JSON results**

Run:

```powershell
$fields = 'docs\research\2026-07-12-hsconfig-source-contract-slim-autonomy-brainstorm\fields.yaml'
Get-ChildItem 'docs\research\2026-07-12-hsconfig-source-contract-slim-autonomy-brainstorm\results\*.json' | ForEach-Object {
  python "$env:USERPROFILE\.codex\skills\research\validate_json.py" -f $fields -j $_.FullName
}
```

Expected:

```text
PASS ... 100.0% coverage
PASS ... 100.0% coverage
PASS ... 100.0% coverage
PASS ... 100.0% coverage
```

- [ ] **Step 5: Run the task test**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_research_current_truth.py -q
```

Expected:

```text
2 passed
```

- [ ] **Step 6: Commit**

```powershell
git add docs/research/current-truth.md tests/test_research_current_truth.py docs/research/2026-07-12-hsconfig-source-contract-slim-autonomy-brainstorm
git commit -m "docs: anchor hsconfig source contract research"
```

---

### Task 2: Freeze Claim-Kind Policy And Surface Gates

**Files:**
- Create: `tests/test_source_contract_spine_freeze.py`
- Modify only if tests fail: `src/hsconfig/source_contract_matrix.py`
- Modify only if tests fail: `src/hsconfig/source_document_model.py`

**Interfaces:**
- Consumes: `SUPPORTED_ATOMIC_CLAIM_KINDS`, `source_contract_policy_by_claim_kind()`, `surface_gate_decision()`
- Produces: frozen source-contract mapping for future claim-kind additions

- [ ] **Step 1: Write the failing freeze tests**

Create `tests/test_source_contract_spine_freeze.py`:

```python
import pytest

from hsconfig.source_contract_matrix import source_contract_policy_by_claim_kind
from hsconfig.source_document_model import (
    SUPPORTED_ATOMIC_CLAIM_KINDS,
    surface_gate_decision,
)


EXPECTED_POLICY = {
    "archetype": ("report_only", ()),
    "mulligan_keep": ("runtime_lowerable", ("mulligan",)),
    "mulligan_discard": ("runtime_lowerable", ("mulligan",)),
    "card_role": ("suppressed_or_conditional", ("cardid",)),
    "targeting_rule": ("runtime_lowerable", ("cardid",)),
    "combo_sequence": ("runtime_lowerable", ("combo",)),
    "gameplan_posture": ("runtime_lowerable", ("globalvalues",)),
    "hero_power_transform": ("suppressed_or_conditional", ("cardid",)),
    "mechanic_usage": ("suppressed_or_conditional", ("cardid",)),
    "known_bad_pattern": ("suppressed_or_conditional", ("cardid",)),
    "tech_slot": ("report_only", ()),
    "replacement_option": ("report_only", ()),
    "discover_choice": ("suppressed_or_conditional", ("cardid",)),
    "choose_one_choice": ("suppressed_or_conditional", ("cardid",)),
    "globalvalue_numeric_tuning": ("runtime_evidence_required", ()),
}


def test_supported_claim_kinds_match_frozen_policy():
    policy = source_contract_policy_by_claim_kind()

    assert set(policy) == set(SUPPORTED_ATOMIC_CLAIM_KINDS)
    assert set(policy) == set(EXPECTED_POLICY)

    for claim_kind, (lane, surfaces) in EXPECTED_POLICY.items():
        row = policy[claim_kind]
        assert row["lane"] == lane
        assert tuple(row["allowed_surfaces"]) == surfaces


@pytest.mark.parametrize("claim_kind,expected", sorted(EXPECTED_POLICY.items()))
def test_surface_gate_matches_policy_matrix(claim_kind, expected):
    _, surfaces = expected
    claim = {
        "claim_kind": claim_kind,
        "claim_readiness": "guide_backed",
        "trust_ceiling": "runtime_candidate",
        "cards": ["CARD_001"],
    }
    context = {
        "card_roles": {
            "CARD_001": {
                "roles": ["mulligan_anchor"],
                "semantic_families": [],
            }
        }
    }

    for surface in ("mulligan", "globalvalues", "cardid", "combo"):
        decision = surface_gate_decision(claim, surface, context=context)
        if surface in surfaces:
            assert decision.allowed is True, (claim_kind, surface, decision.reason)
        else:
            assert decision.allowed is False, (claim_kind, surface)


def test_globalvalue_numeric_tuning_is_never_step1_lowerable():
    claim = {
        "claim_kind": "globalvalue_numeric_tuning",
        "claim_readiness": "guide_backed",
        "trust_ceiling": "runtime_candidate",
        "cards": [],
    }

    decision = surface_gate_decision(claim, "globalvalues")

    assert decision.allowed is False
    assert decision.reason == "requires_runtime_evidence"
```

- [ ] **Step 2: Run the freeze tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_source_contract_spine_freeze.py -q
```

Expected after current implementation:

```text
17 passed
```

If this fails, the failure is a real contract drift. Do not weaken the test unless the implementation plan is explicitly amended.

- [ ] **Step 3: Fix policy drift if needed**

If a claim kind is missing from `source_contract_matrix.py`, add one row to `_POLICY` with the exact lane and allowed surfaces from `EXPECTED_POLICY`.

Example row shape:

```python
"hero_power_transform": {
    "lane": "suppressed_or_conditional",
    "allowed_surfaces": ("cardid",),
    "operator_meaning": (
        "Preserve hero-power-transform semantics; it is not a mulligan keep by itself."
    ),
},
```

If a surface gate is wrong, update only the matching surface set in `src/hsconfig/source_document_model.py`:

```python
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
```

- [ ] **Step 4: Run the task tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_source_contract_spine_freeze.py tests/test_claim_kind_runtime_contract.py -q
```

Expected:

```text
all passed
```

- [ ] **Step 5: Commit**

```powershell
git add tests/test_source_contract_spine_freeze.py src/hsconfig/source_contract_matrix.py src/hsconfig/source_document_model.py
git commit -m "test: freeze hsconfig source contract spine"
```

---

### Task 3: Add Contract-Doctor Spine Visibility Without Apply Authority

**Files:**
- Modify: `src/hsconfig/contract_doctor.py`
- Modify: `tests/test_contract_doctor.py`

**Interfaces:**
- Consumes: `build_source_contract_conformance_snapshot()`
- Produces: `report["contract_spine"]` in contract-doctor diagnostics

- [ ] **Step 1: Write the failing test**

Append this test to `tests/test_contract_doctor.py`:

```python
def test_contract_doctor_exposes_spine_summary_without_apply_policy(tmp_path: Path):
    package = tmp_path / "package"
    write_json(
        package / "reports" / "operator_summary.json",
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "VALID_BUT_NOT_GUIDE_STRONG",
            "next_action": "READY_TO_APPLY_WITH_WARNINGS",
        },
    )

    report = build_contract_doctor_report(package)

    assert report["contract_spine"]["operator_gate_impact"] == "diagnostic_only"
    assert report["contract_spine"]["claim_kind_count"] >= 1
    assert "mulligan_keep" in report["contract_spine"]["claim_kinds"]
    assert "hero_power_transform" in report["contract_spine"]["claim_kinds"]
    assert report["contract_spine"]["unexpected_contract_drift_count"] == 0
    assert report["authority"]["apply_authority"] == "reports/operator_summary.json"

    serialized = json.dumps(report)
    assert '"apply_allowed"' not in serialized
    assert '"runtime_apply_allowed"' not in serialized
    assert '"runtime_apply_mode"' not in serialized
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_contract_doctor.py::test_contract_doctor_exposes_spine_summary_without_apply_policy -q
```

Expected:

```text
FAILED ... KeyError: 'contract_spine'
```

- [ ] **Step 3: Implement the compact spine summary**

In `src/hsconfig/contract_doctor.py`, add this helper near `_mapping`:

```python
def _contract_spine_summary(conformance: Mapping[str, Any]) -> dict[str, Any]:
    summary = _mapping(conformance.get("summary"))
    rows = conformance.get("contract_spine_rows", [])
    if not isinstance(rows, list):
        rows = []
    claim_kinds = [
        str(row.get("claim_kind", ""))
        for row in rows
        if isinstance(row, Mapping) and str(row.get("claim_kind", ""))
    ]
    return {
        "operator_gate_impact": str(
            conformance.get("operator_gate_impact", "diagnostic_only")
        ),
        "claim_kind_count": len(claim_kinds),
        "claim_kinds": sorted(claim_kinds),
        "policy_lane_counts": dict(summary.get("policy_lane_counts", {}))
        if isinstance(summary.get("policy_lane_counts"), Mapping)
        else {},
        "unexpected_contract_drift_count": int(
            summary.get("unexpected_contract_drift_count", 0)
        ),
        "builder_prerequisite_gap_count": int(
            summary.get("builder_prerequisite_gap_count", 0)
        ),
        "pipeline_attention_count": int(summary.get("pipeline_attention_count", 0)),
    }
```

In `build_contract_doctor_report()`, after `conformance = build_source_contract_conformance_snapshot()`, add:

```python
contract_spine = _contract_spine_summary(conformance)
```

Then include it in the returned dict:

```python
"contract_spine": contract_spine,
```

- [ ] **Step 4: Add markdown visibility**

In `render_contract_doctor_markdown()`, add:

```python
contract_spine = _mapping(report.get("contract_spine"))
```

Then add this section before `## Conformance`:

```python
        "## Contract Spine",
        "",
        f"- Operator gate impact: {contract_spine.get('operator_gate_impact', '')}",
        f"- Claim kinds: {contract_spine.get('claim_kind_count', 0)}",
        f"- Policy lanes: {contract_spine.get('policy_lane_counts', {})}",
        f"- Unexpected contract drift: {contract_spine.get('unexpected_contract_drift_count', 0)}",
        f"- Builder prerequisite gaps: {contract_spine.get('builder_prerequisite_gap_count', 0)}",
        "",
```

- [ ] **Step 5: Run contract-doctor tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_contract_doctor.py -q
```

Expected:

```text
all passed
```

- [ ] **Step 6: Commit**

```powershell
git add src/hsconfig/contract_doctor.py tests/test_contract_doctor.py
git commit -m "feat: expose diagnostic contract spine"
```

---

### Task 4: Harden Single Apply Authority Guard

**Files:**
- Modify: `tests/test_apply_authority_boundary.py`

**Interfaces:**
- Consumes: active apply files `src/hsconfig/apply_gate.py`, `src/hsconfig/runtime_apply.py`, `src/hsconfig/commands/apply.py`
- Produces: regression guard preventing diagnostics from entering apply authority

- [ ] **Step 1: Add the import-level guard test**

Append this test to `tests/test_apply_authority_boundary.py`:

```python
FORBIDDEN_DIAGNOSTIC_IMPORTS = [
    "from hsconfig.contract_doctor",
    "import hsconfig.contract_doctor",
    "from hsconfig.source_contract_audit",
    "import hsconfig.source_contract_audit",
    "from hsconfig.source_contract_conformance",
    "import hsconfig.source_contract_conformance",
]


def test_active_apply_paths_do_not_import_diagnostic_authorities():
    for relative_path in ACTIVE_APPLY_PATHS:
        content = _read(relative_path)
        for token in FORBIDDEN_DIAGNOSTIC_IMPORTS:
            assert token not in content, (relative_path, token)
```

- [ ] **Step 2: Run the apply authority tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_apply_authority_boundary.py -q
```

Expected:

```text
all passed
```

If this fails, remove the diagnostic import from the active apply path and route the needed information through `reports/operator_summary.json` instead.

- [ ] **Step 3: Commit**

```powershell
git add tests/test_apply_authority_boundary.py
git commit -m "test: guard hsconfig apply authority boundary"
```

---

### Task 5: Document Source Truth Versus Runtime Authority

**Files:**
- Modify: `docs/operator/guide-research-policy.md`
- Create: `tests/test_operator_docs_contract_policy.py`

**Interfaces:**
- Consumes: source-contract behavior from Tasks 1-4
- Produces: operator-facing invariant that source truth is not runtime authority

- [ ] **Step 1: Write the docs guard test**

Create `tests/test_operator_docs_contract_policy.py`:

```python
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_guide_research_policy_names_source_truth_boundary():
    text = (ROOT / "docs" / "operator" / "guide-research-policy.md").read_text(
        encoding="utf-8"
    )

    assert "Source Truth Is Not Runtime Authority" in text
    assert "`claim_kind` is the runtime-routing authority" in text
    assert "`operator_summary.json` remains the only normal apply authority" in text
    assert "Darkbishop Benedictus" in text
    assert "does not become a mulligan keep" in text
    assert "`globalvalue_numeric_tuning`" in text
    assert "requires runtime evidence" in text


def test_guide_research_policy_keeps_no_block_language():
    text = (ROOT / "docs" / "operator" / "guide-research-policy.md").read_text(
        encoding="utf-8"
    )

    assert "Warnings are follow-up work, not a runtime apply blocker." in text
    assert "Do not use `source_contract_audit.json` as an apply gate." in text
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_operator_docs_contract_policy.py -q
```

Expected before doc edit:

```text
FAILED tests/test_operator_docs_contract_policy.py::test_guide_research_policy_names_source_truth_boundary
```

- [ ] **Step 3: Add the compact operator section**

In `docs/operator/guide-research-policy.md`, after the `Structured Source Format` example and before `Accepted source document fields`, add:

```markdown
## Source Truth Is Not Runtime Authority

Source documents can be true and still not lower to runtime JSON. `claim_kind`
is the runtime-routing authority. The surface gate decides whether a claim may
lower to `Mulligan.json`, `GlobalValues.json`, per-card `<CARDID>.json`, or
`Combo.json`. `operator_summary.json` remains the only normal apply authority.

Examples:

- Darkbishop Benedictus can preserve the Shadowform / Mind Spike effect through
  `hero_power_transform` and CardID behavior, but this does not become a
  mulligan keep unless a separate current mulligan source explicitly says to
  keep the card in the opening hand.
- `globalvalue_numeric_tuning` is valid source evidence for future tuning, but
  Step 1 requires runtime evidence before numeric GlobalValues changes.
- Discover and Choose One claims require exact option identity before lowering.

Warnings are follow-up work, not a runtime apply blocker.
Do not use `source_contract_audit.json` as an apply gate.
```

- [ ] **Step 4: Run docs tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_operator_docs_contract_policy.py -q
```

Expected:

```text
2 passed
```

- [ ] **Step 5: Commit**

```powershell
git add docs/operator/guide-research-policy.md tests/test_operator_docs_contract_policy.py
git commit -m "docs: clarify source truth runtime authority"
```

---

### Task 6: Add Generic Hero-Power Transform Regression

**Files:**
- Modify: `tests/test_claim_kind_runtime_contract.py`

**Interfaces:**
- Consumes: `surface_gate_decision()` and `route_card_behavior_surfaces()`
- Produces: generic non-ShadowPriest regression for effect-visible but non-mulligan hero-power transforms

- [ ] **Step 1: Add the regression test**

Append this import to `tests/test_claim_kind_runtime_contract.py`:

```python
from hsconfig.card_behavior_surface_router import route_card_behavior_surfaces
```

Append this test:

```python
def test_hero_power_transform_can_emit_cardid_without_mulligan_keep():
    claim = {
        "claim_id": "hero_power_transform_fixture",
        "claim_kind": "hero_power_transform",
        "claim_readiness": "source_backed_static_semantics",
        "trust_ceiling": "runtime_candidate",
        "cards": ["CARD_HP"],
        "runtime_block": "BeforeUseHeroPowerBonus",
        "runtime_value": 25,
    }

    cardid_decision = surface_gate_decision(claim, "cardid")
    mulligan_decision = surface_gate_decision(claim, "mulligan")
    routed = route_card_behavior_surfaces([claim])

    assert cardid_decision.allowed is True
    assert mulligan_decision.allowed is False
    assert mulligan_decision.reason == "claim_kind_not_mulligan_surface"
    assert routed["rows"][0]["card_id"] == "CARD_HP"
    assert routed["rows"][0]["runtime_block"] == "BeforeUseHeroPowerBonus"
```

- [ ] **Step 2: Run the specific test**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_claim_kind_runtime_contract.py::test_hero_power_transform_can_emit_cardid_without_mulligan_keep -q
```

Expected:

```text
1 passed
```

If the router output shape differs, inspect `src/hsconfig/card_behavior_surface_router.py` and update the assertion to the actual emitted row field names without weakening the semantic assertions:

```python
assert cardid_decision.allowed is True
assert mulligan_decision.allowed is False
```

- [ ] **Step 3: Run the whole claim-kind contract suite**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_claim_kind_runtime_contract.py -q
```

Expected:

```text
all passed
```

- [ ] **Step 4: Commit**

```powershell
git add tests/test_claim_kind_runtime_contract.py
git commit -m "test: guard hero power transform lowering"
```

---

### Task 7: Final Verification And Review

**Files:**
- No new source files.
- Review all changed files from Tasks 1-6.

**Interfaces:**
- Consumes: all previous tasks.
- Produces: verified branch ready for push or merge.

- [ ] **Step 1: Run targeted test set**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest `
  tests/test_research_current_truth.py `
  tests/test_source_contract_spine_freeze.py `
  tests/test_contract_doctor.py `
  tests/test_apply_authority_boundary.py `
  tests/test_claim_kind_runtime_contract.py `
  tests/test_operator_docs_contract_policy.py `
  tests/test_source_contract_conformance.py `
  tests/test_source_contract_audit.py `
  tests/test_apply_gate.py `
  tests/test_shadowpriest_depth_e2e.py `
  -q
```

Expected:

```text
all passed
```

- [ ] **Step 2: Run the full suite**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest -q
```

Expected:

```text
all passed
```

- [ ] **Step 3: Validate the research package again**

Run:

```powershell
$fields = 'docs\research\2026-07-12-hsconfig-source-contract-slim-autonomy-brainstorm\fields.yaml'
Get-ChildItem 'docs\research\2026-07-12-hsconfig-source-contract-slim-autonomy-brainstorm\results\*.json' | ForEach-Object {
  python "$env:USERPROFILE\.codex\skills\research\validate_json.py" -f $fields -j $_.FullName
}
```

Expected:

```text
PASS ... 100.0% coverage
PASS ... 100.0% coverage
PASS ... 100.0% coverage
PASS ... 100.0% coverage
```

- [ ] **Step 4: Inspect diff**

Run:

```powershell
git diff --check
git diff --stat
git diff -- docs/research/current-truth.md docs/operator/guide-research-policy.md src/hsconfig/contract_doctor.py tests
```

Expected:

```text
git diff --check exits 0
```

Review expectations:

- No runtime files are added.
- No `Presume.json` or `Concede.json` normal-path support is introduced.
- No apply path imports diagnostic modules.
- `contract_doctor` remains diagnostic-only.
- Darkbishop-style effect semantics remain separate from mulligan keep logic.

- [ ] **Step 5: Check git status**

Run:

```powershell
git status --short --branch
```

Expected:

```text
## main...origin/main [ahead N]
```

or a feature branch with only the planned files changed.

- [ ] **Step 6: Final commit if previous tasks were not committed separately**

If the tasks were not committed individually, make one final commit:

```powershell
git add docs/research/current-truth.md docs/operator/guide-research-policy.md src/hsconfig/contract_doctor.py tests docs/research/2026-07-12-hsconfig-source-contract-slim-autonomy-brainstorm
git commit -m "test: freeze hsconfig source contract spine"
```

---

## Self-Review

- Spec coverage: The plan covers source-contract spine correctness, no-block autonomy, Darkbishop/effect-vs-mulligan behavior, `globalvalue_numeric_tuning`, diagnostics-only reports, single apply authority, research package anchoring, and operator docs.
- Placeholder scan: No placeholder markers or unspecified tests are used.
- Type consistency: All functions referenced exist in the current codebase: `source_contract_policy_by_claim_kind()`, `surface_gate_decision()`, `build_source_contract_conformance_snapshot()`, `build_contract_doctor_report()`, and `route_card_behavior_surfaces()`.
- Scope control: The plan does not add dependencies, does not introduce new runtime surfaces, and does not change the apply authority model.

# HSConfig Source Contract Spine Freeze And Evidence Index Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Freeze HSConfig's source-to-runtime contract spine as a diagnostic-only evidence chain and index the latest research package without creating a second apply gate.

**Architecture:** Keep `reports/operator_summary.json` as the only normal runtime/apply authority. Keep `reports/source_contract_audit.json`, `claim_lifecycle_rows`, and conformance `contract_spine_rows` as explanations of why a source claim did or did not lower to `Mulligan.json`, `GlobalValues.json`, `Combo.json`, or per-card `<CARDID>.json`. Add tests that lock the chain `source -> policy -> surface gate -> builder/router -> runtime effect -> operator gate impact` while preventing any source-audit artifact from becoming an apply decision input.

**Tech Stack:** Python 3.11+, pytest, existing `hsconfig` package, existing Markdown docs and skill files. No new dependencies.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig`.
- Do not move work into `C:\Users\darbo\Documents\HS`, temp checkouts, or shadow workspaces.
- Commit the new research package only as evidence, not as operator guidance.
- Do not add new normal runtime surfaces.
- Do not emit `Presume.json` or `Concede.json` in the normal HSConfig path.
- Do not make `source_contract_audit.json`, contract conformance, or `contract_spine_rows` an apply gate.
- `reports/operator_summary.json` remains the single normal operator/apply authority.
- Preserve no-block behavior: semantic weakness, low confidence, unsupported claims, report-only mechanics, and builder prerequisite gaps stay visible but do not block a technically valid load-safe package.
- Preserve Darkbishop Benedictus semantics: `hero_power_transform` stays effect/CardID-visible, but start-of-game Hero Power transformation does not become a false opening-hand Mulligan keep.
- Do not add dependencies.
- Do not write HearthRanger runtime files or generated deck outputs in this plan.

---

## File Structure

- Create `C:\Users\darbo\Documents\HSConfig\docs\research\2026-07-12-hsconfig-source-contract-spine-brainstorm\README.md`
  - Responsibility: mark the new research package as active evidence only, list the result files, and state the operator implication.
- Modify `C:\Users\darbo\Documents\HSConfig\docs\research\current-truth.md`
  - Responsibility: name the new research package in the active evidence index without turning it into operator instructions.
- Modify `C:\Users\darbo\Documents\HSConfig\tests\test_docs_active_path.py`
  - Responsibility: prove research docs remain evidence-only and the current-truth index names the active package.
- Modify `C:\Users\darbo\Documents\HSConfig\tests\test_source_contract_conformance.py`
  - Responsibility: lock `contract_spine_rows` as an exact lifecycle projection for every supported claim kind.
- Create `C:\Users\darbo\Documents\HSConfig\tests\test_no_second_gate_contract.py`
  - Responsibility: prove apply and runtime-write code does not consume `contract_spine_rows` or `source_contract_audit.json` as an apply gate.
- Modify `C:\Users\darbo\Documents\HSConfig\tests\test_shadowpriest_e2e.py`
  - Responsibility: keep the Darkbishop start-of-game effect boundary proven in a real prepare/validate/apply fixture.
- Modify active docs and skill references only if tests show wording drift:
  - `C:\Users\darbo\Documents\HSConfig\docs\operator\README.md`
  - `C:\Users\darbo\Documents\HSConfig\docs\operator\guide-research-policy.md`
  - `C:\Users\darbo\Documents\HSConfig\.agents\skills\hsconfig\SKILL.md`
  - `C:\Users\darbo\Documents\HSConfig\.agents\skills\hsconfig\references\workflow.md`

---

### Task 1: Index The New Research Package As Evidence

**Files:**
- Create: `C:\Users\darbo\Documents\HSConfig\docs\research\2026-07-12-hsconfig-source-contract-spine-brainstorm\README.md`
- Modify: `C:\Users\darbo\Documents\HSConfig\docs\research\current-truth.md`
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_docs_active_path.py`

**Interfaces:**
- Consumes: the existing research folder `docs/research/2026-07-12-hsconfig-source-contract-spine-brainstorm/`.
- Produces: active-evidence index entries that are explicitly non-operator, non-runtime, and non-apply-gate.

- [ ] **Step 1: Write the research index tests**

Add these tests to `C:\Users\darbo\Documents\HSConfig\tests\test_docs_active_path.py` near the existing current-truth tests:

```python
def test_current_truth_names_source_contract_spine_brainstorm_package():
    text = Path("docs/research/current-truth.md").read_text(encoding="utf-8")

    assert "2026-07-12-hsconfig-source-contract-spine-brainstorm" in text
    assert "Contract-spine freeze and no-second-gate evidence" in text
    assert "operator_summary.json remains the normal apply authority" in text
    assert "source_contract_audit.json remains diagnostic" in text


def test_source_contract_spine_brainstorm_readme_marks_evidence_only():
    root = Path("docs/research/2026-07-12-hsconfig-source-contract-spine-brainstorm")
    readme = (root / "README.md").read_text(encoding="utf-8")

    assert "Research evidence only" in readme
    assert "not operator instructions" in readme
    assert "not runtime input" in readme
    assert "does not grant runtime apply permission" in readme
    assert "operator_summary.json remains the normal apply authority" in readme
    assert "source_contract_audit.json remains diagnostic" in readme
    assert "contract_spine_rows remain diagnostic" in readme
    assert (root / "fields.yaml").exists()
    assert (root / "outline.yaml").exists()
    assert len(list((root / "results").glob("*.json"))) == 3
```

- [ ] **Step 2: Run the tests**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
$env:PYTHONPATH='src'
python -m pytest tests/test_docs_active_path.py::test_current_truth_names_source_contract_spine_brainstorm_package tests/test_docs_active_path.py::test_source_contract_spine_brainstorm_readme_marks_evidence_only -q
```

Expected: FAIL because the package README and current-truth entry are not yet present.

- [ ] **Step 3: Create the research package README**

Create `C:\Users\darbo\Documents\HSConfig\docs\research\2026-07-12-hsconfig-source-contract-spine-brainstorm\README.md` with exactly this content:

```markdown
# HSConfig Source Contract Spine Brainstorm

Research evidence only. This package is not operator instructions, not runtime input, and does not grant runtime apply permission.

Normal operator guidance remains `docs/operator/README.md`.

`operator_summary.json` remains the normal apply authority.
`source_contract_audit.json` remains diagnostic.
`contract_spine_rows` remain diagnostic.

## Evidence Files

- `results/HearthRanger_VisionAI_surface_authority_and_no-second-gate_boundary.json`
- `results/Hearthstone_semantics_that_must_not_become_false_runtime_claims.json`
- `results/HSConfig_repository_contract_spine_quality_and_autonomy_audit.json`

## Repo Implication

Freeze the diagnostic contract spine and keep it readable, but do not create a second apply gate. Source claims may be aggressive only when they map to a documented HSConfig-supported VisionAI runtime surface and the builder/router can emit the matching JSON. Otherwise, keep the claim visible as diagnostic or follow-up evidence.
```

- [ ] **Step 4: Add the package to current truth**

In `C:\Users\darbo\Documents\HSConfig\docs\research\current-truth.md`, add this row to the `Current Active Evidence` table:

```markdown
| `docs/research/2026-07-12-hsconfig-source-contract-spine-brainstorm/` | Contract-spine freeze and no-second-gate evidence | Keep `operator_summary.json` as the normal apply authority; `source_contract_audit.json` and `contract_spine_rows` remain diagnostic explanations of source -> policy -> surface gate -> builder/router -> runtime effect. |
```

Do not remove older rows. Do not mark the package as operator guidance.

- [ ] **Step 5: Run the research docs tests again**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
$env:PYTHONPATH='src'
python -m pytest tests/test_docs_active_path.py::test_current_truth_names_source_contract_spine_brainstorm_package tests/test_docs_active_path.py::test_source_contract_spine_brainstorm_readme_marks_evidence_only -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 1**

```powershell
cd C:\Users\darbo\Documents\HSConfig
git add docs/research/current-truth.md docs/research/2026-07-12-hsconfig-source-contract-spine-brainstorm tests/test_docs_active_path.py
git commit -m "docs: index contract spine research evidence"
```

---

### Task 2: Harden Contract-Spine Invariants

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_source_contract_conformance.py`
- Modify if needed: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\source_contract_conformance.py`

**Interfaces:**
- Consumes: `build_source_contract_conformance_snapshot() -> dict[str, Any]`.
- Produces: `snapshot["contract_spine_rows"] -> list[dict[str, Any]]`, an exact diagnostic projection of each claim-kind lifecycle.

- [ ] **Step 1: Write the exact projection test**

Add this test to `C:\Users\darbo\Documents\HSConfig\tests\test_source_contract_conformance.py` after `test_conformance_snapshot_exposes_flat_contract_spine_rows`:

```python
def test_contract_spine_rows_are_exact_lifecycle_projection():
    snapshot = build_source_contract_conformance_snapshot()
    claim_rows = snapshot["claim_kind_rows"]
    spine_rows = snapshot["contract_spine_rows"]
    expected_keys = {
        "claim_kind",
        "policy_lane",
        "allowed_surfaces",
        "surface_gate_status",
        "builder_status",
        "final_runtime_effect",
        "operator_gate_impact",
    }

    assert len(spine_rows) == len(SUPPORTED_ATOMIC_CLAIM_KINDS)
    assert [row["claim_kind"] for row in spine_rows] == sorted(SUPPORTED_ATOMIC_CLAIM_KINDS)

    for row in spine_rows:
        claim_kind = row["claim_kind"]
        lifecycle = claim_rows[claim_kind]["lifecycle"]

        assert set(row) == expected_keys
        assert row["policy_lane"] == lifecycle["policy_lane"]
        assert row["allowed_surfaces"] == lifecycle["allowed_surfaces"]
        assert row["surface_gate_status"] == lifecycle["surface_gate_status"]
        assert row["builder_status"] == lifecycle["builder_status"]
        assert row["final_runtime_effect"] == lifecycle["final_runtime_effect"]
        assert row["operator_gate_impact"] == "diagnostic_only"
```

- [ ] **Step 2: Write the no-apply-authority payload test**

Add this test to the same file:

```python
def test_contract_spine_rows_never_carry_apply_authority_fields():
    snapshot = build_source_contract_conformance_snapshot()
    forbidden_keys = {
        "apply_allowed",
        "apply_gate",
        "apply_policy",
        "next_action",
        "runtime_apply_allowed",
        "runtime_apply_mode",
        "technical_status",
    }

    for row in snapshot["contract_spine_rows"]:
        assert forbidden_keys.isdisjoint(row), row
        assert row["operator_gate_impact"] == "diagnostic_only"
```

- [ ] **Step 3: Run the invariant tests**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
$env:PYTHONPATH='src'
python -m pytest tests/test_source_contract_conformance.py::test_contract_spine_rows_are_exact_lifecycle_projection tests/test_source_contract_conformance.py::test_contract_spine_rows_never_carry_apply_authority_fields -q
```

Expected: PASS if the current branch already satisfies the freeze; FAIL only if the implementation drifted and needs the next step.

- [ ] **Step 4: Fix implementation only if the tests fail**

If the tests fail because `contract_spine_rows` contains extra fields or is not lifecycle-derived, replace `_contract_spine_rows()` in `C:\Users\darbo\Documents\HSConfig\src\hsconfig\source_contract_conformance.py` with:

```python
def _contract_spine_rows(rows: Mapping[str, Any]) -> list[dict[str, Any]]:
    spine: list[dict[str, Any]] = []
    for claim_kind, row in sorted(rows.items()):
        if not isinstance(row, Mapping):
            continue
        lifecycle = row.get("lifecycle", {})
        if not isinstance(lifecycle, Mapping):
            lifecycle = {}
        spine.append(
            {
                "claim_kind": str(claim_kind),
                "policy_lane": str(lifecycle.get("policy_lane", "")),
                "allowed_surfaces": [
                    str(surface) for surface in lifecycle.get("allowed_surfaces", [])
                ],
                "surface_gate_status": str(lifecycle.get("surface_gate_status", "")),
                "builder_status": str(lifecycle.get("builder_status", "")),
                "final_runtime_effect": str(lifecycle.get("final_runtime_effect", "")),
                "operator_gate_impact": OPERATOR_GATE_IMPACT,
            }
        )
    return spine
```

- [ ] **Step 5: Run the full conformance file**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
$env:PYTHONPATH='src'
python -m pytest tests/test_source_contract_conformance.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 2**

```powershell
cd C:\Users\darbo\Documents\HSConfig
git add tests/test_source_contract_conformance.py src/hsconfig/source_contract_conformance.py
git commit -m "test: harden contract spine invariants"
```

---

### Task 3: Add No-Second-Gate Source Guard

**Files:**
- Create: `C:\Users\darbo\Documents\HSConfig\tests\test_no_second_gate_contract.py`
- Modify only if the test fails: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\apply_gate.py`
- Modify only if the test fails: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\runtime_apply.py`
- Modify only if the test fails: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\commands\apply.py`
- Modify only if the test fails: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\operator_summary.py`

**Interfaces:**
- Consumes: active Python source files.
- Produces: a source-level guard proving diagnostics cannot silently become apply inputs.

- [ ] **Step 1: Create the guard test file**

Create `C:\Users\darbo\Documents\HSConfig\tests\test_no_second_gate_contract.py` with:

```python
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def test_contract_spine_rows_are_not_consumed_by_apply_or_runtime_write_paths():
    guarded_paths = [
        "src/hsconfig/apply_gate.py",
        "src/hsconfig/runtime_apply.py",
        "src/hsconfig/commands/apply.py",
        "src/hsconfig/operator_summary.py",
    ]

    for relative_path in guarded_paths:
        assert "contract_spine_rows" not in _read(relative_path), relative_path


def test_source_contract_audit_is_summary_only_not_apply_gate_input():
    assert "source_contract_audit" not in _read("src/hsconfig/apply_gate.py")
    assert "source_contract_audit" not in _read("src/hsconfig/runtime_apply.py")
    assert "source_contract_audit" not in _read("src/hsconfig/commands/apply.py")

    operator_summary = _read("src/hsconfig/operator_summary.py")
    assert "source_contract_audit_report" in operator_summary
    assert "_source_contract_audit_summary" in operator_summary
    assert "source_contract_audit_summary" in operator_summary
    assert "runtime_apply_allowed" in operator_summary
```

- [ ] **Step 2: Run the source guard**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
$env:PYTHONPATH='src'
python -m pytest tests/test_no_second_gate_contract.py -q
```

Expected: PASS if apply/runtime paths are clean; FAIL if diagnostics leaked into apply decision code.

- [ ] **Step 3: Fix only if the guard fails**

If `apply_gate.py`, `runtime_apply.py`, or `commands/apply.py` reads `source_contract_audit` or `contract_spine_rows`, remove that read and route the decision back through existing `operator_summary.json` validation. The apply path must continue to call the existing gate function, not a new audit gate:

```python
from hsconfig.apply_gate import evaluate_apply_gate

apply_gate = evaluate_apply_gate(package)
if not apply_gate.get("allowed"):
    return blocked_result
```

If `operator_summary.py` uses `source_contract_audit_report` for anything beyond summary fields, keep only summary rendering in `_source_contract_audit_summary(report)`.

- [ ] **Step 4: Run apply and operator tests**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
$env:PYTHONPATH='src'
python -m pytest tests/test_no_second_gate_contract.py tests/test_operator_summary.py tests/test_apply_gate.py tests/test_runtime_apply.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 3**

```powershell
cd C:\Users\darbo\Documents\HSConfig
git add tests/test_no_second_gate_contract.py src/hsconfig/apply_gate.py src/hsconfig/runtime_apply.py src/hsconfig/commands/apply.py src/hsconfig/operator_summary.py
git commit -m "test: guard source diagnostics from apply gate"
```

---

### Task 4: Reinforce Darkbishop Start-Of-Game Boundary

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_shadowpriest_e2e.py`
- Modify only if the test fails: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\mulligan_plan.py`
- Modify only if the test fails: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\card_behavior_surface_router.py`
- Modify only if the test fails: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\source_contract_audit.py`

**Interfaces:**
- Consumes: ShadowPriest prepare/validate/apply fixture.
- Produces: an end-to-end proof that start-of-game effect claims do not become opening-hand keeps while `hero_power_transform` remains visible on a CardID/effect surface.

- [ ] **Step 1: Add the explicit boundary assertions**

In `C:\Users\darbo\Documents\HSConfig\tests\test_shadowpriest_e2e.py`, after the existing `darkbishop_lifecycle_rows` block, add these assertions:

```python
    darkbishop_mulligan_lifecycle = [
        row
        for row in darkbishop_lifecycle_rows
        if row["claim_kind"] == "mulligan_keep"
    ]
    darkbishop_effect_lifecycle = [
        row
        for row in darkbishop_lifecycle_rows
        if row["claim_kind"] == "hero_power_transform"
    ]

    assert darkbishop_effect_lifecycle
    assert all(
        row["builder_or_router_decision"] == "emitted"
        for row in darkbishop_effect_lifecycle
    )
    assert all(
        row["runtime_surface"] in {"SW_448.json", "<CARDID>.json", "CARDID.json"}
        or "SW_448.json" in row["emitted_files"]
        for row in darkbishop_effect_lifecycle
    )
    assert darkbishop_mulligan_lifecycle == []
    assert "Darkbishop Benedictus" not in mulligan_text
    assert "Mind Spike" in semantic_audit
```

- [ ] **Step 2: Run the ShadowPriest E2E test**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
$env:PYTHONPATH='src'
python -m pytest tests/test_shadowpriest_e2e.py::test_shadowpriest_deckinput_only_build_validate_and_apply -q
```

Expected: PASS if the current boundary is correct; FAIL if start-of-game effect data is still producing a Mulligan keep.

- [ ] **Step 3: Fix only if the test fails**

If the test fails because Darkbishop appears in `Mulligan.json`, keep the effect source claim but reject the Mulligan lowering in the Mulligan surface gate. The rejection reason must remain:

```python
"start_of_game_effect_does_not_require_opening_hand"
```

The fix belongs in whichever current function is producing the false `mulligan_keep` row. Do not remove the `hero_power_transform` role, linked Mind Spike entity, or `SW_448.json` effect row.

- [ ] **Step 4: Run adjacent boundary tests**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
$env:PYTHONPATH='src'
python -m pytest tests/test_shadowpriest_e2e.py tests/test_surface_authority_split.py tests/test_source_contract_audit.py tests/test_mulligan_plan.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 4**

```powershell
cd C:\Users\darbo\Documents\HSConfig
git add tests/test_shadowpriest_e2e.py src/hsconfig/mulligan_plan.py src/hsconfig/card_behavior_surface_router.py src/hsconfig/source_contract_audit.py
git commit -m "test: lock darkbishop mulligan boundary"
```

---

### Task 5: Sync Minimal Operator And Skill Wording

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_skill_files.py`
- Modify if needed: `C:\Users\darbo\Documents\HSConfig\docs\operator\README.md`
- Modify if needed: `C:\Users\darbo\Documents\HSConfig\docs\operator\guide-research-policy.md`
- Modify if needed: `C:\Users\darbo\Documents\HSConfig\.agents\skills\hsconfig\SKILL.md`
- Modify if needed: `C:\Users\darbo\Documents\HSConfig\.agents\skills\hsconfig\references\workflow.md`

**Interfaces:**
- Consumes: active docs and skill text.
- Produces: one compact operator explanation of which file decides apply and which files explain source lowering.

- [ ] **Step 1: Add the wording guard**

Add this test to `C:\Users\darbo\Documents\HSConfig\tests\test_skill_files.py` near the current source-contract docs tests:

```python
def test_docs_explain_apply_authority_and_diagnostic_chain_in_one_place():
    paths = [
        Path("docs/operator/README.md"),
        Path("docs/operator/guide-research-policy.md"),
        Path(".agents/skills/hsconfig/SKILL.md"),
        Path(".agents/skills/hsconfig/references/workflow.md"),
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in paths)

    assert "`operator_summary.json` remains the only normal apply authority." in combined
    assert "`source_contract_audit.json` explains why each claim did or did not lower." in combined
    assert "`contract_spine_rows` show the compact source -> policy -> surface gate -> builder/router -> runtime effect chain." in combined
    assert "Warnings are follow-up work, not a runtime apply blocker." in combined
    assert "Do not use `source_contract_audit.json` as an apply gate." in combined
```

- [ ] **Step 2: Run the wording guard**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
$env:PYTHONPATH='src'
python -m pytest tests/test_skill_files.py::test_docs_explain_apply_authority_and_diagnostic_chain_in_one_place -q
```

Expected: FAIL if the exact compact wording is missing; PASS if current docs already contain it.

- [ ] **Step 3: Add compact wording only where missing**

Add this short block to the source-contract or readiness section of each missing active file:

```markdown
`operator_summary.json` remains the only normal apply authority.
`source_contract_audit.json` explains why each claim did or did not lower.
`contract_spine_rows` show the compact source -> policy -> surface gate -> builder/router -> runtime effect chain.
Warnings are follow-up work, not a runtime apply blocker.
Do not use `source_contract_audit.json` as an apply gate.
```

Keep the docs compact. Do not duplicate this block more than once per file.

- [ ] **Step 4: Run docs tests**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
$env:PYTHONPATH='src'
python -m pytest tests/test_skill_files.py tests/test_docs_active_path.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 5**

```powershell
cd C:\Users\darbo\Documents\HSConfig
git add tests/test_skill_files.py docs/operator/README.md docs/operator/guide-research-policy.md .agents/skills/hsconfig/SKILL.md .agents/skills/hsconfig/references/workflow.md
git commit -m "docs: clarify diagnostic source contract chain"
```

---

### Task 6: Verification, Full Suite, And GitHub State

**Files:**
- No planned source edits.
- Inspect: repository status and recent commits.

**Interfaces:**
- Consumes: Tasks 1-5.
- Produces: verified branch ready to push or merge.

- [ ] **Step 1: Run targeted contract and docs tests**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
$env:PYTHONPATH='src'
python -m pytest tests/test_source_contract_conformance.py tests/test_source_contract_audit.py tests/test_surface_authority_split.py tests/test_claim_kind_runtime_contract.py tests/test_no_second_gate_contract.py tests/test_skill_files.py tests/test_docs_active_path.py -q
```

Expected: PASS.

- [ ] **Step 2: Run representative runtime-safety tests**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
$env:PYTHONPATH='src'
python -m pytest tests/test_shadowpriest_e2e.py tests/test_universal_wild_no_block_matrix.py tests/test_operator_summary.py tests/test_apply_gate.py tests/test_runtime_apply.py -q
```

Expected: PASS.

- [ ] **Step 3: Run the full test suite**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
$env:PYTHONPATH='src'
python -m pytest -q
```

Expected: PASS.

- [ ] **Step 4: Run active-path wording scan**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
rg -n "contract_spine_rows are an apply gate|source_contract_audit\.json remains the normal apply authority|Presume\.json` is publicly documented|Concede\.json` is publicly documented|normal output includes Presume|normal output includes Concede" .agents docs/operator src tests
```

Expected: no matches.

- [ ] **Step 5: Confirm no generated runtime evidence is staged**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
git status --short --branch
git diff --stat
git log --oneline --decorate -8
```

Expected:

```text
No Power.log, .hdtreplay, .hsreplay, HearthRanger logs, generated runtime evidence, or private runtime folders are staged.
The branch contains only source, tests, docs, skill, and research evidence changes.
```

- [ ] **Step 6: Final review checklist**

Confirm all statements before reporting completion:

```text
operator_summary.json remains the only normal apply authority.
source_contract_audit.json remains diagnostic.
contract_spine_rows remain diagnostic.
No apply or runtime-write path consumes contract_spine_rows.
No apply or runtime-write path consumes source_contract_audit.json directly.
No new normal runtime surfaces were added.
Presume.json and Concede.json are not emitted in the normal HSConfig path.
Darkbishop/start-of-game effect semantics still stay out of Mulligan keeps.
The new research package is indexed as evidence only.
No HearthRanger runtime files were written by this plan.
```

If any statement is false, fix the smallest affected task and rerun Step 1 and Step 2 before continuing.

- [ ] **Step 7: Push after green verification**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
git push origin codex/claim-lifecycle-trace
```

Expected: push succeeds.

---

## Self-Review

- Spec coverage: covers research indexing, source-contract spine invariants, no-second-gate guard, Darkbishop effect-vs-Mulligan boundary, compact docs, and full verification.
- Placeholder scan: no deferred implementation placeholders are present; optional fix steps are conditional on explicit test failures and include exact expected remediation.
- Type consistency: `contract_spine_rows` is consistently treated as `list[dict[str, Any]]` with exact keys.
- Scope check: this is a freeze and guard-rail wave. It does not add runtime surfaces, replay analysis, winrate logic, HSTuner scope, or broad semantic expansion.

## Execution Handoff

Plan complete and saved to `C:\Users\darbo\Documents\HSConfig\docs\superpowers\plans\2026-07-12-hsconfig-source-contract-spine-freeze-evidence-index.md`.

Two execution options:

1. **Subagent-Driven (recommended)** - dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** - execute tasks in this session using executing-plans, batch execution with checkpoints.

Recommended execution: **Subagent-Driven**, because Task 1 and Task 5 are docs/evidence-heavy, Task 2 and Task 3 are contract/test-heavy, and Task 4 needs an isolated E2E boundary review.

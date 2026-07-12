# HSConfig Contract Spine Freeze Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Freeze HSConfig's source-to-runtime contract as a lean, no-block, diagnostic-only spine so future changes cannot turn source audits into a second apply gate.

**Architecture:** Keep `reports/operator_summary.json` as the only normal operator/apply authority. Reuse the existing conformance model and add only a compact `contract_spine_rows` projection for readability. Normalize active docs and skill wording so `Presume.json` and `Concede.json` are described as legacy/diagnostic surfaces outside the normal HSConfig output path, not as normal-path work.

**Tech Stack:** Python 3.11+, pytest, existing `hsconfig` package, existing Markdown docs and skill files. No new dependencies.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig`.
- Do not move work into `C:\Users\darbo\Documents\HS`, temp checkouts, or shadow workspaces.
- Do not add runtime surfaces.
- Do not emit `Presume.json` or `Concede.json` in the normal HSConfig path.
- Do not make `source_contract_audit.json`, contract conformance, or `contract_spine_rows` an apply gate.
- `reports/operator_summary.json` remains the single normal operator/apply authority.
- Preserve no-block behavior: semantic weakness, low confidence, unsupported claims, report-only mechanics, and builder prerequisite gaps stay visible but do not block a technically valid load-safe package.
- Do not add dependencies.
- Do not write HearthRanger runtime files or generated deck outputs in this plan.

---

## File Structure

- Modify `C:\Users\darbo\Documents\HSConfig\src\hsconfig\source_contract_conformance.py`
  - Responsibility: generate deck-neutral source-contract conformance data and Markdown.
  - Change: add a flat `contract_spine_rows` projection derived from existing lifecycle data.
- Modify `C:\Users\darbo\Documents\HSConfig\tests\test_source_contract_conformance.py`
  - Responsibility: lock the conformance contract and prove diagnostics cannot become apply authority.
  - Change: tests for `contract_spine_rows` and Markdown section.
- Modify `C:\Users\darbo\Documents\HSConfig\tests\test_skill_files.py`
  - Responsibility: lock active docs/skill wording and no-second-gate rules.
  - Change: tests that active docs use legacy/diagnostic wording for `Presume.json` / `Concede.json`.
- Modify active docs and skill references:
  - `C:\Users\darbo\Documents\HSConfig\.agents\skills\hsconfig\SKILL.md`
  - `C:\Users\darbo\Documents\HSConfig\.agents\skills\hsconfig\references\workflow.md`
  - `C:\Users\darbo\Documents\HSConfig\.agents\skills\hsconfig\references\visionai-surfaces.md`
  - `C:\Users\darbo\Documents\HSConfig\docs\operator\README.md`
  - `C:\Users\darbo\Documents\HSConfig\docs\operator\universal-wild-no-block-contract.md`
  - Responsibility: keep operator-facing source/contract language narrow and current.

---

### Task 1: Normalize Active Presume/Concede Wording

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_skill_files.py`
- Modify: `C:\Users\darbo\Documents\HSConfig\.agents\skills\hsconfig\SKILL.md`
- Modify: `C:\Users\darbo\Documents\HSConfig\.agents\skills\hsconfig\references\workflow.md`
- Modify: `C:\Users\darbo\Documents\HSConfig\.agents\skills\hsconfig\references\visionai-surfaces.md`
- Modify: `C:\Users\darbo\Documents\HSConfig\docs\operator\README.md`
- Modify: `C:\Users\darbo\Documents\HSConfig\docs\operator\universal-wild-no-block-contract.md`

**Interfaces:**
- Consumes: active skill and operator docs.
- Produces: a stable wording contract: `Presume.json` and `Concede.json` are legacy/diagnostic VisionAI surfaces outside normal HSConfig output; absence never blocks a valid load-safe package.

- [ ] **Step 1: Write the failing docs test**

Add this test to `C:\Users\darbo\Documents\HSConfig\tests\test_skill_files.py` near the existing source-contract/operator-summary tests:

```python
def test_active_docs_call_presume_concede_legacy_diagnostic_not_normal_path():
    active_paths = [
        ROOT / ".agents" / "skills" / "hsconfig" / "SKILL.md",
        ROOT / ".agents" / "skills" / "hsconfig" / "references" / "workflow.md",
        ROOT / ".agents" / "skills" / "hsconfig" / "references" / "visionai-surfaces.md",
        ROOT / "docs" / "operator" / "README.md",
        ROOT / "docs" / "operator" / "universal-wild-no-block-contract.md",
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in active_paths)

    required_sentence = (
        "`Presume.json` and `Concede.json` are legacy/diagnostic VisionAI surfaces "
        "outside the normal HSConfig output path; their absence never blocks a "
        "valid load-safe package."
    )
    for path in active_paths:
        text = path.read_text(encoding="utf-8")
        assert required_sentence in text, path

    forbidden_phrases = [
        "`Concede.json` is publicly documented",
        "`Presume.json` is publicly documented",
        "normal HSConfig does not emit `Presume.json` or `Concede.json`; absence",
    ]
    for phrase in forbidden_phrases:
        assert phrase not in combined
```

- [ ] **Step 2: Run the failing test**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
$env:PYTHONPATH='src'
python -m pytest tests/test_skill_files.py::test_active_docs_call_presume_concede_legacy_diagnostic_not_normal_path -q
```

Expected: FAIL because active docs still use older "publicly documented" wording.

- [ ] **Step 3: Update active docs and skill wording**

Replace active-path paragraphs that currently say `Concede.json` or `Presume.json` is publicly documented with this exact sentence:

```markdown
`Presume.json` and `Concede.json` are legacy/diagnostic VisionAI surfaces outside the normal HSConfig output path; their absence never blocks a valid load-safe package.
```

Do this only in the files listed for this task. Do not edit archived plans, research JSON, or historical specs in this task.

- [ ] **Step 4: Run the docs test again**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
$env:PYTHONPATH='src'
python -m pytest tests/test_skill_files.py::test_active_docs_call_presume_concede_legacy_diagnostic_not_normal_path -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 1**

```powershell
cd C:\Users\darbo\Documents\HSConfig
git add tests/test_skill_files.py .agents/skills/hsconfig/SKILL.md .agents/skills/hsconfig/references/workflow.md .agents/skills/hsconfig/references/visionai-surfaces.md docs/operator/README.md docs/operator/universal-wild-no-block-contract.md
git commit -m "docs: freeze legacy diagnostic surface wording"
```

---

### Task 2: Add Compact Contract Spine Rows

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_source_contract_conformance.py`
- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\source_contract_conformance.py`

**Interfaces:**
- Consumes: `build_source_contract_conformance_snapshot() -> dict[str, Any]`.
- Produces: `snapshot["contract_spine_rows"] -> list[dict[str, Any]]`.
- Each row has exactly these keys: `claim_kind`, `policy_lane`, `allowed_surfaces`, `surface_gate_status`, `builder_status`, `final_runtime_effect`, `operator_gate_impact`.

- [ ] **Step 1: Write the failing conformance test**

Add this test to `C:\Users\darbo\Documents\HSConfig\tests\test_source_contract_conformance.py` after `test_conformance_snapshot_exposes_claim_lifecycle_for_key_claims`:

```python
def test_conformance_snapshot_exposes_flat_contract_spine_rows():
    snapshot = build_source_contract_conformance_snapshot()
    spine_rows = snapshot["contract_spine_rows"]

    assert len(spine_rows) == len(SUPPORTED_ATOMIC_CLAIM_KINDS)
    assert {row["claim_kind"] for row in spine_rows} == set(SUPPORTED_ATOMIC_CLAIM_KINDS)

    hero_power = next(
        row for row in spine_rows if row["claim_kind"] == "hero_power_transform"
    )
    assert hero_power == {
        "claim_kind": "hero_power_transform",
        "policy_lane": "suppressed_or_conditional",
        "allowed_surfaces": ["cardid"],
        "surface_gate_status": "cardid:allowed",
        "builder_status": "route_card_behavior_surfaces:emitted",
        "final_runtime_effect": "emits_cardid_runtime_row",
        "operator_gate_impact": "diagnostic_only",
    }

    numeric = next(
        row for row in spine_rows if row["claim_kind"] == "globalvalue_numeric_tuning"
    )
    assert numeric["surface_gate_status"] == "no_allowed_surface"
    assert numeric["final_runtime_effect"] == "suppressed_until_runtime_evidence"
    assert numeric["operator_gate_impact"] == "diagnostic_only"
```

- [ ] **Step 2: Add the Markdown test**

Add this test to the same file after `test_conformance_markdown_uses_drift_and_prerequisite_language`:

```python
def test_conformance_markdown_renders_contract_spine_section():
    markdown = render_source_contract_conformance_markdown(
        build_source_contract_conformance_snapshot()
    )

    assert "## Contract Spine" in markdown
    assert (
        "| hero_power_transform | suppressed_or_conditional | cardid:allowed | "
        "route_card_behavior_surfaces:emitted | emits_cardid_runtime_row | "
        "diagnostic_only |"
    ) in markdown
    assert (
        "| globalvalue_numeric_tuning | runtime_evidence_required | "
        "no_allowed_surface | "
        "build_globalvalues_authority_matrix:suppressed:requires_runtime_evidence | "
        "suppressed_until_runtime_evidence | diagnostic_only |"
    ) in markdown
```

- [ ] **Step 3: Run the failing tests**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
$env:PYTHONPATH='src'
python -m pytest tests/test_source_contract_conformance.py::test_conformance_snapshot_exposes_flat_contract_spine_rows tests/test_source_contract_conformance.py::test_conformance_markdown_renders_contract_spine_section -q
```

Expected: FAIL because `contract_spine_rows` and the Markdown section do not exist yet.

- [ ] **Step 4: Implement `contract_spine_rows`**

In `build_source_contract_conformance_snapshot()`, add this key to the returned dict after `claim_kind_rows`:

```python
"contract_spine_rows": _contract_spine_rows(rows),
```

Add this helper below `_claim_lifecycle()`:

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

- [ ] **Step 5: Render the Markdown section**

In `render_source_contract_conformance_markdown()`, read the rows:

```python
spine_rows = snapshot.get("contract_spine_rows", [])
if not isinstance(spine_rows, list):
    spine_rows = []
```

Add this section after the Summary bullets and before the existing claim-kind table:

```python
lines.extend(
    [
        "",
        "## Contract Spine",
        "",
        "| Claim Kind | Policy Lane | Surface Gate | Builder Status | Final Runtime Effect | Operator Gate Impact |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
)
for row in spine_rows:
    if not isinstance(row, Mapping):
        continue
    lines.append(
        "| {claim} | {lane} | {gate} | {builder} | {effect} | {impact} |".format(
            claim=_escape_table(row.get("claim_kind", "")),
            lane=_escape_table(row.get("policy_lane", "")),
            gate=_escape_table(row.get("surface_gate_status", "")),
            builder=_escape_table(row.get("builder_status", "")),
            effect=_escape_table(row.get("final_runtime_effect", "")),
            impact=_escape_table(row.get("operator_gate_impact", "")),
        )
    )
lines.extend(
    [
        "",
        "## Claim Kind Surface Matrix",
        "",
        "| Claim Kind | Policy Lane | Allowed Surfaces | Gate Summary |",
        "| --- | --- | --- | --- |",
    ]
)
```

Then remove the duplicate original claim-kind table header block so the Markdown has one `## Claim Kind Surface Matrix` section and one table.

- [ ] **Step 6: Run conformance tests**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
$env:PYTHONPATH='src'
python -m pytest tests/test_source_contract_conformance.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit Task 2**

```powershell
cd C:\Users\darbo\Documents\HSConfig
git add src/hsconfig/source_contract_conformance.py tests/test_source_contract_conformance.py
git commit -m "feat: expose compact source contract spine"
```

---

### Task 3: Lock No-Second-Gate Documentation

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_skill_files.py`
- Modify: `C:\Users\darbo\Documents\HSConfig\docs\operator\guide-research-policy.md`
- Modify: `C:\Users\darbo\Documents\HSConfig\.agents\skills\hsconfig\references\workflow.md`
- Modify: `C:\Users\darbo\Documents\HSConfig\.agents\skills\hsconfig\SKILL.md`

**Interfaces:**
- Consumes: `contract_spine_rows` from Task 2 as diagnostic vocabulary.
- Produces: active docs that tell operators the read order is `operator_summary.json` first, then `source_contract_audit.json.claim_lifecycle_rows` or conformance `contract_spine_rows` for explanation.

- [ ] **Step 1: Write the failing docs test**

Add this test to `C:\Users\darbo\Documents\HSConfig\tests\test_skill_files.py` near the existing source-contract tests:

```python
def test_docs_explain_contract_spine_without_new_apply_gate():
    active_paths = [
        ROOT / ".agents" / "skills" / "hsconfig" / "SKILL.md",
        ROOT / ".agents" / "skills" / "hsconfig" / "references" / "workflow.md",
        ROOT / "docs" / "operator" / "guide-research-policy.md",
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in active_paths)

    assert "contract_spine_rows" in combined
    assert "source -> policy -> surface gate -> builder/router -> runtime effect" in combined
    assert "operator_summary.json remains the normal apply authority" in combined
    assert "contract_spine_rows are diagnostic" in combined
    assert "contract_spine_rows are an apply gate" not in combined
```

- [ ] **Step 2: Run the failing docs test**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
$env:PYTHONPATH='src'
python -m pytest tests/test_skill_files.py::test_docs_explain_contract_spine_without_new_apply_gate -q
```

Expected: FAIL because `contract_spine_rows` is not yet documented in all active references.

- [ ] **Step 3: Update active docs**

Add this exact paragraph to the source-contract sections of the three files listed for this task:

```markdown
`contract_spine_rows` are diagnostic. They provide the compact source -> policy -> surface gate -> builder/router -> runtime effect chain for each claim kind. They do not grant apply permission, and operator_summary.json remains the normal apply authority.
```

Use the paragraph once per file. Do not add a new workflow step, command, or gate.

- [ ] **Step 4: Run the docs test again**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
$env:PYTHONPATH='src'
python -m pytest tests/test_skill_files.py::test_docs_explain_contract_spine_without_new_apply_gate -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 3**

```powershell
cd C:\Users\darbo\Documents\HSConfig
git add tests/test_skill_files.py docs/operator/guide-research-policy.md .agents/skills/hsconfig/references/workflow.md .agents/skills/hsconfig/SKILL.md
git commit -m "docs: document diagnostic contract spine"
```

---

### Task 4: Verification And Final Review

**Files:**
- No planned source edits.
- Inspect: `C:\Users\darbo\Documents\HSConfig\git status`

**Interfaces:**
- Consumes: Tasks 1-3.
- Produces: verified branch ready for push or PR.

- [ ] **Step 1: Run targeted contract tests**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
$env:PYTHONPATH='src'
python -m pytest tests/test_source_contract_conformance.py tests/test_claim_kind_runtime_contract.py tests/test_source_contract_audit.py tests/test_skill_files.py -q
```

Expected: PASS.

- [ ] **Step 2: Run no-block and representative E2E tests**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
$env:PYTHONPATH='src'
python -m pytest tests/test_shadowpriest_e2e.py tests/test_universal_wild_no_block_matrix.py tests/test_apply_gate.py tests/test_visionai_registry.py -q
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

- [ ] **Step 4: Search for active wording regressions**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
rg -n "Presume\.json` is publicly documented|Concede\.json` is publicly documented|contract_spine_rows are an apply gate|source_contract_audit\.json remains the normal apply authority" .agents docs src tests
```

Expected: no matches.

- [ ] **Step 5: Inspect git state**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
git status --short --branch
git log --oneline --decorate -5
```

Expected: branch contains the three task commits and no untracked generated runtime outputs.

- [ ] **Step 6: Final review checklist**

Confirm these statements before reporting completion:

```text
operator_summary.json remains the only normal apply authority.
source_contract_audit.json remains diagnostic.
contract_spine_rows remain diagnostic.
No new runtime surfaces were added.
Presume.json and Concede.json are not emitted in the normal HSConfig path.
Darkbishop/start-of-game effect semantics still stay out of Mulligan keeps.
No HearthRanger runtime files were written by this plan.
```

If any statement is false, fix the smallest affected task and rerun the targeted tests from Step 1.

---

## Self-Review

- Spec coverage: covered the recommended Contract-Spine-Freeze, Presume/Concede wording, compact traceability, no-second-gate rule, no-block behavior, and verification.
- Placeholder scan: no deferred implementation placeholders are present.
- Type consistency: `contract_spine_rows` is defined as `list[dict[str, Any]]`, and every test uses the same field names.
- Scope check: this plan is a small freeze/polish wave, not a new runtime surface or semantic expansion.

## Execution Handoff

Plan complete and saved to `C:\Users\darbo\Documents\HSConfig\docs\superpowers\plans\2026-07-12-hsconfig-contract-spine-freeze.md`.

Two execution options:

1. **Subagent-Driven (recommended)** - dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** - execute tasks in this session using executing-plans, batch execution with checkpoints.

Recommended execution: **Subagent-Driven**, because Task 1 and Task 3 are docs-heavy while Task 2 is code/test-heavy and should be reviewed separately.

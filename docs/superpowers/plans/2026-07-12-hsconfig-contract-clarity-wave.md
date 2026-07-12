# HSConfig Contract Clarity Wave Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make HSConfig source-contract diagnostics distinguish true contract drift from expected builder prerequisites so autonomous deck generation stays no-block, narrow, and technically honest.

**Architecture:** Keep the current HSConfig pipeline. `source_document_model.py` remains the live runtime-surface gate, `source_contract_matrix.py` remains the static claim policy, and `source_contract_conformance.py` remains documentation-as-code. This wave changes naming, summary structure, lifecycle visibility, tests, and docs only; it does not add a second operator gate or any post-run tuning feature.

**Tech Stack:** Python 3, pytest, existing HSConfig modules, existing HearthRanger VisionAI runtime surfaces (`Mulligan.json`, `GlobalValues.json`, per-card `<CARDID>.json`, `Combo.json`).

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig`.
- Keep HSConfig separate from HSTuner and HSranger.
- Do not add replay parsing, HDT parsing, winrate validation, candidate promotion, or post-run tuning.
- Do not add dependencies.
- Generated runtime packages stay under `outputs/` and remain gitignored.
- `reports/operator_summary.json` remains the normal apply authority.
- Contract conformance remains diagnostic-only documentation-as-code.
- Every implementation change must preserve exact deck and CardID identity.
- Every implementation change must preserve full `GlobalValues.json` key profiling.
- Every implementation change must preserve every card covered in the gameplan contract.
- Every implementation change must preserve strict JSON validation.
- Every implementation change must preserve row-level provenance for generated config rows.
- Start-of-game, deckbuilding, deck-state, and hero-power-transform effects must not become automatic Mulligan keeps.
- `globalvalue_numeric_tuning` remains runtime-evidence-required in Step 1.

---

## File Structure

- Modify: `src/hsconfig/source_contract_conformance.py`
  - Split true drift from expected builder prerequisite gaps.
  - Keep backwards-compatible legacy summary keys for existing callers.
  - Add explicit claim lifecycle data per claim kind.
  - Update Markdown rendering to display the new meaning clearly.
- Modify: `tests/test_source_contract_conformance.py`
  - Add TDD coverage for drift/gap separation.
  - Add TDD coverage for claim lifecycle rows.
  - Update older assertions to prefer the new key names while keeping compatibility checks.
- Modify: `docs/operator/guide-research-policy.md`
  - Clarify the conformance snapshot as diagnostic-only and explain the difference between unexpected contract drift and expected builder prerequisite gaps.
- Modify: `.agents/skills/hsconfig/SKILL.md`
  - Add one concise skill rule for future Codex runs.
- Modify: `.agents/skills/hsconfig/references/workflow.md`
  - Mirror the same rule in the installed skill reference.
- Modify: `tests/test_skill_files.py`
  - Prove docs and skill text stay aligned.

---

### Task 1: Split Unexpected Drift From Expected Builder Prerequisite Gaps

**Files:**
- Modify: `tests/test_source_contract_conformance.py`
- Modify: `src/hsconfig/source_contract_conformance.py`

**Interfaces:**
- Consumes: `build_source_contract_conformance_snapshot() -> dict[str, Any]`
- Produces: summary keys:
  - `unexpected_contract_drift_count: int`
  - `unexpected_contract_drifts: list[dict[str, Any]]`
  - `builder_prerequisite_gap_count: int`
  - `builder_prerequisite_gaps: list[dict[str, Any]]`
  - `pipeline_attention_count: int`
  - backwards-compatible legacy keys `surface_gate_builder_mismatch_count`, `surface_gate_builder_mismatches`, and `pipeline_mismatch_count`

- [ ] **Step 1: Add failing test for the new summary semantics**

Append this test to `tests/test_source_contract_conformance.py`:

```python
def test_conformance_snapshot_distinguishes_drift_from_builder_prerequisites():
    summary = build_source_contract_conformance_snapshot()["summary"]

    assert summary["policy_gate_mismatch_count"] == 0
    assert summary["builder_router_expectation_mismatch_count"] == 0
    assert summary["unexpected_contract_drift_count"] == 0
    assert summary["unexpected_contract_drifts"] == []

    assert summary["builder_prerequisite_gap_count"] == 1
    assert summary["builder_prerequisite_gaps"] == [
        {
            "claim_kind": "combo_sequence",
            "surface": "combo",
            "builder_outcome": "suppressed",
            "reason": "sequence_too_short",
            "operator_meaning": (
                "Surface gate allows this claim kind, but the builder still needs "
                "a complete sequence before runtime JSON can be emitted."
            ),
        }
    ]
    assert summary["pipeline_attention_count"] == 1
```

- [ ] **Step 2: Add compatibility assertion for legacy keys**

Append this test to `tests/test_source_contract_conformance.py`:

```python
def test_conformance_snapshot_keeps_legacy_mismatch_keys_as_attention_aliases():
    summary = build_source_contract_conformance_snapshot()["summary"]

    assert summary["surface_gate_builder_mismatch_count"] == summary[
        "builder_prerequisite_gap_count"
    ]
    assert summary["surface_gate_builder_mismatches"] == summary[
        "builder_prerequisite_gaps"
    ]
    assert summary["pipeline_mismatch_count"] == summary["pipeline_attention_count"]
```

- [ ] **Step 3: Run tests to verify failure**

Run:

```powershell
python -m pytest tests\test_source_contract_conformance.py::test_conformance_snapshot_distinguishes_drift_from_builder_prerequisites tests\test_source_contract_conformance.py::test_conformance_snapshot_keeps_legacy_mismatch_keys_as_attention_aliases -q
```

Expected: FAIL with `KeyError` for `unexpected_contract_drift_count`.

- [ ] **Step 4: Replace prerequisite helper naming in implementation**

In `src/hsconfig/source_contract_conformance.py`, rename `_surface_gate_builder_mismatches()` to `_builder_prerequisite_gaps()` and change the appended row to include `operator_meaning`.

Use this implementation:

```python
def _builder_prerequisite_gaps(rows: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Expose expected builder prerequisites beyond an allowed surface gate."""
    gaps = []
    for claim_kind, row in sorted(rows.items()):
        if not isinstance(row, Mapping):
            continue
        builder_router = row.get("builder_router", {})
        if not isinstance(builder_router, Mapping):
            continue
        surface = builder_router.get("surface")
        gates = row.get("surface_gates", {})
        if not isinstance(surface, str) or not isinstance(gates, Mapping):
            continue
        gate = gates.get(surface, {})
        if not isinstance(gate, Mapping) or gate.get("decision") != "allowed":
            continue
        for exemplar_name in ("complete", "incomplete"):
            exemplar = builder_router.get(exemplar_name)
            if not isinstance(exemplar, Mapping):
                continue
            if exemplar.get("outcome") == "emitted":
                continue
            gaps.append(
                {
                    "claim_kind": claim_kind,
                    "surface": surface,
                    "builder_outcome": exemplar.get("outcome", ""),
                    "reason": exemplar.get("reason", ""),
                    "operator_meaning": (
                        "Surface gate allows this claim kind, but the builder still needs "
                        "a complete sequence before runtime JSON can be emitted."
                    ),
                }
            )
    return gaps
```

- [ ] **Step 5: Update summary construction**

In `build_source_contract_conformance_snapshot()`, replace the current `surface_gate_builder_mismatches` local variable and summary block with this exact shape:

```python
    builder_prerequisite_gaps = _builder_prerequisite_gaps(rows)
    unexpected_contract_drifts = [
        *policy_gate_mismatches,
        *builder_expectation_mismatches,
    ]
    pipeline_attention_count = len(unexpected_contract_drifts) + len(
        builder_prerequisite_gaps
    )
    return {
        "schema_version": 1,
        "operator_gate_impact": OPERATOR_GATE_IMPACT,
        "summary": {
            "claim_kinds_total": len(rows),
            "policy_lane_counts": dict(sorted(lane_counts.items())),
            "missing_claim_kinds": missing,
            "extra_claim_kinds": extra,
            "policy_gate_mismatch_count": len(policy_gate_mismatches),
            "policy_gate_mismatches": policy_gate_mismatches,
            "builder_router_expectation_mismatch_count": len(
                builder_expectation_mismatches
            ),
            "builder_router_expectation_mismatches": builder_expectation_mismatches,
            "unexpected_contract_drift_count": len(unexpected_contract_drifts),
            "unexpected_contract_drifts": unexpected_contract_drifts,
            "builder_prerequisite_gap_count": len(builder_prerequisite_gaps),
            "builder_prerequisite_gaps": builder_prerequisite_gaps,
            "pipeline_attention_count": pipeline_attention_count,
            "surface_gate_builder_mismatch_count": len(builder_prerequisite_gaps),
            "surface_gate_builder_mismatches": builder_prerequisite_gaps,
            "pipeline_mismatch_count": pipeline_attention_count,
        },
        "claim_kind_rows": rows,
        "start_of_game_mulligan_suppression": _start_of_game_suppression_row(),
    }
```

- [ ] **Step 6: Run focused tests**

Run:

```powershell
python -m pytest tests\test_source_contract_conformance.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

Run:

```powershell
git add src\hsconfig\source_contract_conformance.py tests\test_source_contract_conformance.py
git commit -m "Clarify contract conformance drift summary"
```

---

### Task 2: Add Claim Lifecycle Rows To The Conformance Snapshot

**Files:**
- Modify: `tests/test_source_contract_conformance.py`
- Modify: `src/hsconfig/source_contract_conformance.py`

**Interfaces:**
- Consumes: `claim_kind_rows[claim_kind]["surface_gates"]`
- Consumes: `claim_kind_rows[claim_kind]["builder_router"]`
- Produces: `claim_kind_rows[claim_kind]["lifecycle"] -> dict[str, str | list[str]]`

- [ ] **Step 1: Add failing lifecycle test**

Append this test to `tests/test_source_contract_conformance.py`:

```python
def test_conformance_snapshot_exposes_claim_lifecycle_for_key_claims():
    rows = build_source_contract_conformance_snapshot()["claim_kind_rows"]

    assert rows["hero_power_transform"]["lifecycle"] == {
        "policy_lane": "suppressed_or_conditional",
        "allowed_surfaces": ["cardid"],
        "surface_gate_status": "cardid:allowed",
        "builder_status": "route_card_behavior_surfaces:emitted",
        "final_runtime_effect": "emits_cardid_runtime_row",
        "operator_meaning": (
            "Preserve hero-power-transform semantics; it is not a mulligan keep by itself."
        ),
    }
    assert rows["globalvalue_numeric_tuning"]["lifecycle"] == {
        "policy_lane": "runtime_evidence_required",
        "allowed_surfaces": [],
        "surface_gate_status": "no_allowed_surface",
        "builder_status": "build_globalvalues_authority_matrix:suppressed:requires_runtime_evidence",
        "final_runtime_effect": "suppressed_until_runtime_evidence",
        "operator_meaning": (
            "Valid evidence, but Step 1 must wait for runtime evidence before numeric tuning."
        ),
    }
    assert rows["combo_sequence"]["lifecycle"] == {
        "policy_lane": "runtime_lowerable",
        "allowed_surfaces": ["combo"],
        "surface_gate_status": "combo:allowed",
        "builder_status": "build_combo_plan:emitted; incomplete:suppressed:sequence_too_short",
        "final_runtime_effect": "emits_when_builder_prerequisites_are_complete",
        "operator_meaning": "Can lower only as an explicit ordered Combo.json sequence.",
    }
```

- [ ] **Step 2: Run test to verify failure**

Run:

```powershell
python -m pytest tests\test_source_contract_conformance.py::test_conformance_snapshot_exposes_claim_lifecycle_for_key_claims -q
```

Expected: FAIL with `KeyError: 'lifecycle'`.

- [ ] **Step 3: Add lifecycle field to claim rows**

In `_claim_kind_row()` in `src/hsconfig/source_contract_conformance.py`, create the row first and then attach lifecycle:

```python
    row = {
        "claim_kind": claim_kind,
        "policy_lane": str(policy_row.get("lane", "")),
        "allowed_surfaces": list(policy_row.get("allowed_surfaces", ())),
        "operator_meaning": str(policy_row.get("operator_meaning", "")),
        "surface_gates": gates,
        "builder_router": _builder_router_expectation(claim_kind),
    }
    row["lifecycle"] = _claim_lifecycle(row)
    return row
```

- [ ] **Step 4: Add lifecycle helper functions**

Add these helper functions below `_claim_kind_row()`:

```python
def _claim_lifecycle(row: Mapping[str, Any]) -> dict[str, Any]:
    allowed_surfaces = [str(surface) for surface in row.get("allowed_surfaces", [])]
    return {
        "policy_lane": str(row.get("policy_lane", "")),
        "allowed_surfaces": allowed_surfaces,
        "surface_gate_status": _surface_gate_status(row),
        "builder_status": _builder_status(row.get("builder_router", {})),
        "final_runtime_effect": _final_runtime_effect(row),
        "operator_meaning": str(row.get("operator_meaning", "")),
    }


def _surface_gate_status(row: Mapping[str, Any]) -> str:
    allowed_surfaces = [str(surface) for surface in row.get("allowed_surfaces", [])]
    if not allowed_surfaces:
        return "no_allowed_surface"
    gates = row.get("surface_gates", {})
    if not isinstance(gates, Mapping):
        return "missing_surface_gates"
    statuses = []
    for surface in allowed_surfaces:
        gate = gates.get(surface, {})
        if not isinstance(gate, Mapping):
            statuses.append(f"{surface}:missing")
            continue
        statuses.append(f"{surface}:{gate.get('decision', '')}")
    return "; ".join(statuses)


def _builder_status(builder_router: Any) -> str:
    if not isinstance(builder_router, Mapping):
        return "no_builder_router"
    runner = str(builder_router.get("runner", ""))
    complete = builder_router.get("complete", {})
    if not isinstance(complete, Mapping):
        return f"{runner}:missing_complete_exemplar"
    status = f"{runner}:{complete.get('outcome', '')}"
    incomplete = builder_router.get("incomplete")
    if isinstance(incomplete, Mapping):
        status = (
            f"{status}; incomplete:{incomplete.get('outcome', '')}:"
            f"{incomplete.get('reason', '')}"
        )
    elif complete.get("reason") and complete.get("reason") != complete.get("outcome"):
        status = f"{status}:{complete.get('reason')}"
    return status


def _final_runtime_effect(row: Mapping[str, Any]) -> str:
    claim_kind = str(row.get("claim_kind", ""))
    builder_router = row.get("builder_router", {})
    if claim_kind == "globalvalue_numeric_tuning":
        return "suppressed_until_runtime_evidence"
    if claim_kind == "combo_sequence":
        return "emits_when_builder_prerequisites_are_complete"
    if claim_kind in {"archetype", "tech_slot", "replacement_option"}:
        return "report_only_no_runtime_row"
    if not isinstance(builder_router, Mapping):
        return "unknown_runtime_effect"
    surface = builder_router.get("surface")
    complete = builder_router.get("complete", {})
    if not isinstance(complete, Mapping):
        return "unknown_runtime_effect"
    if complete.get("outcome") != "emitted":
        return f"suppressed:{complete.get('reason', '')}"
    if surface == "mulligan":
        return "emits_mulligan_runtime_row"
    if surface == "globalvalues":
        return "emits_globalvalues_posture_overlay"
    if surface == "cardid":
        return "emits_cardid_runtime_row"
    if surface == "combo":
        return "emits_combo_runtime_row"
    return "report_only_no_runtime_row"
```

- [ ] **Step 5: Run focused tests**

Run:

```powershell
python -m pytest tests\test_source_contract_conformance.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```powershell
git add src\hsconfig\source_contract_conformance.py tests\test_source_contract_conformance.py
git commit -m "Expose source claim lifecycle in conformance"
```

---

### Task 3: Update Markdown Rendering And Documentation

**Files:**
- Modify: `tests/test_source_contract_conformance.py`
- Modify: `tests/test_skill_files.py`
- Modify: `src/hsconfig/source_contract_conformance.py`
- Modify: `docs/operator/guide-research-policy.md`
- Modify: `.agents/skills/hsconfig/SKILL.md`
- Modify: `.agents/skills/hsconfig/references/workflow.md`

**Interfaces:**
- Consumes: `render_source_contract_conformance_markdown(snapshot: Mapping[str, Any]) -> str`
- Produces: Markdown sections:
  - `## Summary`
  - `## Builder Prerequisite Gaps`
  - `## Claim Lifecycle`

- [ ] **Step 1: Add failing Markdown test**

Append this test to `tests/test_source_contract_conformance.py`:

```python
def test_conformance_markdown_uses_drift_and_prerequisite_language():
    markdown = render_source_contract_conformance_markdown(
        build_source_contract_conformance_snapshot()
    )

    assert "## Summary" in markdown
    assert "- Unexpected contract drift: 0" in markdown
    assert "- Builder prerequisite gaps: 1" in markdown
    assert "## Builder Prerequisite Gaps" in markdown
    assert (
        "| combo_sequence | combo | suppressed | sequence_too_short | "
        "Surface gate allows this claim kind, but the builder still needs a complete "
        "sequence before runtime JSON can be emitted. |"
    ) in markdown
    assert "## Claim Lifecycle" in markdown
    assert (
        "| hero_power_transform | suppressed_or_conditional | cardid:allowed | "
        "route_card_behavior_surfaces:emitted | emits_cardid_runtime_row |"
    ) in markdown
```

- [ ] **Step 2: Add failing docs/skill alignment test**

Append this test to `tests/test_skill_files.py`:

```python
def test_docs_and_skill_distinguish_contract_drift_from_builder_prerequisites():
    combined = (
        Path("docs/operator/guide-research-policy.md").read_text(encoding="utf-8")
        + "\n"
        + Path(".agents/skills/hsconfig/SKILL.md").read_text(encoding="utf-8")
        + "\n"
        + Path(".agents/skills/hsconfig/references/workflow.md").read_text(
            encoding="utf-8"
        )
    )

    assert "unexpected contract drift" in combined.lower()
    assert "builder prerequisite gap" in combined.lower()
    assert "no-block package generation" in combined.lower()
    assert "operator_summary.json remains the normal apply authority" in combined
```

If `tests/test_skill_files.py` does not already import `Path`, add:

```python
from pathlib import Path
```

- [ ] **Step 3: Run tests to verify failure**

Run:

```powershell
python -m pytest tests\test_source_contract_conformance.py::test_conformance_markdown_uses_drift_and_prerequisite_language tests\test_skill_files.py::test_docs_and_skill_distinguish_contract_drift_from_builder_prerequisites -q
```

Expected: FAIL until Markdown and docs text exist.

- [ ] **Step 4: Update Markdown renderer summary**

In `render_source_contract_conformance_markdown()`, insert this block after the opening diagnostic sentence:

```python
    summary = snapshot.get("summary", {})
    if not isinstance(summary, Mapping):
        summary = {}
    lines.extend(
        [
            "",
            "## Summary",
            "",
            "- Unexpected contract drift: {count}".format(
                count=summary.get("unexpected_contract_drift_count", 0)
            ),
            "- Builder prerequisite gaps: {count}".format(
                count=summary.get("builder_prerequisite_gap_count", 0)
            ),
            "- Pipeline attention rows: {count}".format(
                count=summary.get("pipeline_attention_count", 0)
            ),
            "",
        ]
    )
```

- [ ] **Step 5: Add Builder Prerequisite Gaps section**

In `render_source_contract_conformance_markdown()`, after the Builder/Router Outcomes table, add:

```python
    gaps = summary.get("builder_prerequisite_gaps", [])
    lines.extend(
        [
            "",
            "## Builder Prerequisite Gaps",
            "",
            "| Claim Kind | Surface | Builder Outcome | Reason | Operator Meaning |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    if isinstance(gaps, list) and gaps:
        for gap in gaps:
            if not isinstance(gap, Mapping):
                continue
            lines.append(
                "| {claim} | {surface} | {outcome} | {reason} | {meaning} |".format(
                    claim=_escape_table(gap.get("claim_kind", "")),
                    surface=_escape_table(gap.get("surface", "")),
                    outcome=_escape_table(gap.get("builder_outcome", "")),
                    reason=_escape_table(gap.get("reason", "")),
                    meaning=_escape_table(gap.get("operator_meaning", "")),
                )
            )
    else:
        lines.append("| none | none | none | none | none |")
```

- [ ] **Step 6: Add Claim Lifecycle section**

In `render_source_contract_conformance_markdown()`, after the prerequisite gap section, add:

```python
    lines.extend(
        [
            "",
            "## Claim Lifecycle",
            "",
            "| Claim Kind | Policy Lane | Surface Gate | Builder Status | Final Runtime Effect |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for claim_kind, row in sorted(rows.items()):
        if not isinstance(row, Mapping):
            continue
        lifecycle = row.get("lifecycle", {})
        if not isinstance(lifecycle, Mapping):
            continue
        lines.append(
            "| {claim} | {lane} | {gate} | {builder} | {effect} |".format(
                claim=_escape_table(claim_kind),
                lane=_escape_table(lifecycle.get("policy_lane", "")),
                gate=_escape_table(lifecycle.get("surface_gate_status", "")),
                builder=_escape_table(lifecycle.get("builder_status", "")),
                effect=_escape_table(lifecycle.get("final_runtime_effect", "")),
            )
        )
```

- [ ] **Step 7: Update operator docs**

In `docs/operator/guide-research-policy.md`, extend the existing `Contract Conformance Snapshot` section with:

```markdown
The snapshot separates unexpected contract drift from expected builder
prerequisite gaps. Unexpected contract drift means the policy matrix, surface
gate, or builder expectation disagrees and should be fixed. A builder
prerequisite gap means the surface is allowed, but the concrete row is still
missing required structure, such as a complete `Combo.json` sequence. These
gaps support no-block package generation by staying visible without becoming a
second apply gate.
```

- [ ] **Step 8: Update skill text**

In `.agents/skills/hsconfig/SKILL.md`, add this bullet near the contract conformance bullet:

```markdown
- Treat unexpected contract drift as an implementation defect, but treat builder prerequisite gaps as visible no-block diagnostics. A builder prerequisite gap means the surface is allowed but the concrete claim is missing required structure, such as a complete combo sequence.
```

- [ ] **Step 9: Update workflow reference**

In `.agents/skills/hsconfig/references/workflow.md`, add this paragraph near the contract conformance paragraph:

```markdown
Unexpected contract drift is a defect in the source-contract spine. A builder prerequisite gap is different: it means the surface is allowed, but the concrete claim still lacks required structure. Builder prerequisite gaps stay visible and support no-block package generation; they do not create a second operator gate.
```

- [ ] **Step 10: Run docs and Markdown tests**

Run:

```powershell
python -m pytest tests\test_source_contract_conformance.py tests\test_skill_files.py -q
```

Expected: PASS.

- [ ] **Step 11: Sync installed skill if needed**

Run:

```powershell
python scripts\sync_installed_skill.py --check
```

Expected: PASS.

If it fails because the installed skill copy is stale, run:

```powershell
python scripts\sync_installed_skill.py
python scripts\sync_installed_skill.py --check
```

Expected after sync: PASS.

- [ ] **Step 12: Commit**

Run:

```powershell
git add src\hsconfig\source_contract_conformance.py tests\test_source_contract_conformance.py tests\test_skill_files.py docs\operator\guide-research-policy.md .agents\skills\hsconfig\SKILL.md .agents\skills\hsconfig\references\workflow.md
git commit -m "Document contract prerequisite gaps"
```

---

### Task 4: Final Verification And Push

**Files:**
- No planned source modifications.

**Interfaces:**
- Consumes: all previous tasks.
- Produces: verified branch ready for merge or PR.

- [ ] **Step 1: Run focused conformance suite**

Run:

```powershell
python -m pytest tests\test_source_contract_conformance.py tests\test_claim_kind_runtime_contract.py -q
```

Expected: PASS.

- [ ] **Step 2: Run representative ShadowPriest/no-block suite**

Run:

```powershell
python -m pytest tests\test_shadowpriest_e2e.py tests\test_shadowpriest_depth_e2e.py tests\test_universal_wild_no_block_matrix.py -q
```

Expected: PASS.

- [ ] **Step 3: Run docs and skill checks**

Run:

```powershell
python -m pytest tests\test_skill_files.py tests\test_docs_active_path.py -q
python scripts\sync_installed_skill.py --check
```

Expected: PASS for both commands.

- [ ] **Step 4: Run full suite**

Run:

```powershell
python -m pytest -q
```

Expected: PASS. If the shell timeout is too short, rerun with a longer timeout and record the final pass count.

- [ ] **Step 5: Inspect diff hygiene**

Run:

```powershell
git diff --check
git status --short --branch
git log -5 --oneline --decorate
```

Expected:

- `git diff --check` prints no errors.
- `git status --short --branch` shows only committed branch state or intentional uncommitted plan execution changes before final commit.
- `git log -5 --oneline --decorate` shows the task commits in order.

- [ ] **Step 6: Push**

Run:

```powershell
git push
```

Expected: push succeeds to the current tracking branch.

---

## Self-Review

- Spec coverage: The plan implements the recommendation to split true contract drift from expected builder prerequisites, expose claim lifecycle, and keep the normal apply authority unchanged.
- Scope control: The plan does not add replay parsing, HDT parsing, winrate validation, candidate promotion, HSTuner logic, or new dependencies.
- No-block behavior: The plan keeps valid deck package generation separate from semantic warning and prerequisite diagnostics.
- Darkbishop boundary: The existing `hero_power_transform` and start-of-game Mulligan suppression tests remain in the focused verification path.
- Type consistency: New keys are named consistently across tests, implementation, Markdown, and docs: `unexpected_contract_drift`, `builder_prerequisite_gap`, and `pipeline_attention`.
- Backwards compatibility: Legacy keys remain as aliases so current consumers do not break while docs and tests prefer the clearer terms.
- Placeholder scan: No open placeholder markers or undefined follow-up placeholders remain.

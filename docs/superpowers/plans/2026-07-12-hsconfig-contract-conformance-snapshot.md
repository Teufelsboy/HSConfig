# HSConfig Contract Conformance Snapshot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a lean executable conformance snapshot proving that every HSConfig source claim kind has a stable policy lane, surface-gate outcome, builder/router expectation, and non-blocking operator impact.

**Architecture:** Keep the current HSConfig pipeline. `source_document_model.py` remains the runtime-surface gate, `source_contract_matrix.py` remains the static policy table, and `source_contract_audit.py` remains per-deck diagnostic output. The new conformance snapshot is documentation-as-code: it checks the global contract without creating a second operator gate or a new runtime writer.

**Tech Stack:** Python 3, pytest, existing HSConfig modules, existing HearthRanger VisionAI surfaces (`Mulligan.json`, `GlobalValues.json`, per-card `<CARDID>.json`, `Combo.json`).

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig`.
- Keep HSConfig separate from HSTuner and HSranger.
- Do not add replay parsing, HDT parsing, winrate validation, candidate promotion, or post-run tuning.
- Do not add dependencies.
- Generated runtime packages stay under `outputs/` and remain gitignored.
- `reports/operator_summary.json` remains the normal apply authority.
- `reports/source_contract_audit.json` remains diagnostic and non-blocking.
- Effect semantics are preserved on supported effect/CardID surfaces.
- Only exact runtime-surface claims lower into matching runtime JSON.
- Start-of-game, deckbuilding, deck-state, and hero-power-transform effects must not become automatic Mulligan keeps.
- `globalvalue_numeric_tuning` remains runtime-evidence-required in Step 1.

---

## Current Baseline

The repo already has most of the raw material:

- `src/hsconfig/source_document_model.py`
  - supported claim kinds
  - readiness gates
  - `surface_gate_decision()`
  - Darkbishop/start-of-game Mulligan suppression
- `src/hsconfig/source_contract_matrix.py`
  - static policy lanes per claim kind
  - allowed surfaces per claim kind
- `src/hsconfig/source_contract_audit.py`
  - per-deck claim rows
  - claim lifecycle rows
  - diagnostic-only operator impact
- Current focused tests already cover much of this:
  - `tests/test_claim_kind_runtime_contract.py`
  - `tests/test_surface_authority_split.py`
  - `tests/test_source_contract_audit.py`
  - `tests/test_universal_wild_no_block_matrix.py`

This plan does not replace those pieces. It adds one small global proof layer so future changes cannot silently drift.

## File Structure

- Create: `src/hsconfig/source_contract_conformance.py`
  - Builds a global, deck-neutral conformance snapshot from the policy matrix and live surface gates.
  - Renders a compact Markdown table for docs/review.
  - Does not read decks, write runtime files, or grant apply permission.
- Create: `tests/test_source_contract_conformance.py`
  - Proves every claim kind is represented.
  - Proves policy lanes and surface gates agree.
  - Proves Darkbishop-like start-of-game semantics are effect-visible but not Mulligan-held.
  - Proves `globalvalue_numeric_tuning` is runtime-evidence-required.
- Modify: `docs/operator/guide-research-policy.md`
  - Adds a short source-contract conformance section.
- Modify: `.agents/skills/hsconfig/SKILL.md`
  - Adds one skill bullet pointing future Codex sessions to the conformance rule.
- Modify: `.agents/skills/hsconfig/references/workflow.md`
  - Mirrors the same rule in the installed skill reference.
- Modify: `tests/test_skill_files.py`
  - Proves docs and skill text stay aligned.

---

### Task 1: Add the Global Conformance Snapshot Module

**Files:**
- Create: `src/hsconfig/source_contract_conformance.py`
- Create: `tests/test_source_contract_conformance.py`

**Interfaces:**
- Consumes: `source_contract_policy_by_claim_kind() -> dict[str, dict[str, object]]`
- Consumes: `SUPPORTED_ATOMIC_CLAIM_KINDS`
- Consumes: `surface_gate_decision(claim, surface, context=None)`
- Produces: `build_source_contract_conformance_snapshot() -> dict[str, Any]`
- Produces: `render_source_contract_conformance_markdown(snapshot: Mapping[str, Any]) -> str`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_source_contract_conformance.py`:

```python
from __future__ import annotations

from hsconfig.source_contract_conformance import (
    build_source_contract_conformance_snapshot,
    render_source_contract_conformance_markdown,
)
from hsconfig.source_document_model import SUPPORTED_ATOMIC_CLAIM_KINDS


def test_conformance_snapshot_covers_every_supported_claim_kind():
    snapshot = build_source_contract_conformance_snapshot()

    assert snapshot["schema_version"] == 1
    assert snapshot["operator_gate_impact"] == "diagnostic_only"
    assert set(snapshot["claim_kind_rows"]) == set(SUPPORTED_ATOMIC_CLAIM_KINDS)
    assert snapshot["summary"]["claim_kinds_total"] == len(SUPPORTED_ATOMIC_CLAIM_KINDS)
    assert snapshot["summary"]["missing_claim_kinds"] == []
    assert snapshot["summary"]["extra_claim_kinds"] == []


def test_conformance_snapshot_keeps_key_boundaries_explicit():
    rows = build_source_contract_conformance_snapshot()["claim_kind_rows"]

    assert rows["mulligan_keep"]["policy_lane"] == "runtime_lowerable"
    assert rows["mulligan_keep"]["surface_gates"]["mulligan"]["decision"] == "allowed"
    assert rows["mulligan_keep"]["surface_gates"]["cardid"]["decision"] == "rejected"

    assert rows["hero_power_transform"]["policy_lane"] == "suppressed_or_conditional"
    assert rows["hero_power_transform"]["surface_gates"]["cardid"]["decision"] == "allowed"
    assert rows["hero_power_transform"]["surface_gates"]["mulligan"]["decision"] == "rejected"

    assert rows["globalvalue_numeric_tuning"]["policy_lane"] == "runtime_evidence_required"
    assert rows["globalvalue_numeric_tuning"]["surface_gates"]["globalvalues"]["decision"] == "rejected"
    assert rows["globalvalue_numeric_tuning"]["surface_gates"]["globalvalues"]["reason"] == (
        "requires_runtime_evidence"
    )


def test_conformance_snapshot_proves_start_of_game_effect_is_not_hand_keep():
    snapshot = build_source_contract_conformance_snapshot()
    row = snapshot["start_of_game_mulligan_suppression"]

    assert row["claim_kind"] == "mulligan_keep"
    assert row["surface"] == "mulligan"
    assert row["decision"] == "rejected"
    assert row["reason"] == "start_of_game_effect_does_not_require_opening_hand"
    assert row["operator_meaning"] == (
        "Start-of-game effects remain effect-visible but do not become opening-hand keeps."
    )


def test_conformance_markdown_is_compact_and_diagnostic_only():
    markdown = render_source_contract_conformance_markdown(
        build_source_contract_conformance_snapshot()
    )

    assert "# Source Contract Conformance Snapshot" in markdown
    assert "Diagnostic only" in markdown
    assert "| mulligan_keep | runtime_lowerable | mulligan |" in markdown
    assert "| globalvalue_numeric_tuning | runtime_evidence_required | none |" in markdown
    assert "operator_summary.json remains the apply authority" in markdown
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest tests\test_source_contract_conformance.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'hsconfig.source_contract_conformance'`.

- [ ] **Step 3: Implement the module**

Create `src/hsconfig/source_contract_conformance.py`:

```python
from __future__ import annotations

from collections import Counter
from typing import Any, Mapping

from hsconfig.source_contract_matrix import source_contract_policy_by_claim_kind
from hsconfig.source_document_model import (
    SUPPORTED_ATOMIC_CLAIM_KINDS,
    surface_gate_decision,
)


SURFACES = ("mulligan", "globalvalues", "cardid", "combo")
OPERATOR_GATE_IMPACT = "diagnostic_only"


def build_source_contract_conformance_snapshot() -> dict[str, Any]:
    """Build a deck-neutral proof that policy lanes and live surface gates align."""
    policy = source_contract_policy_by_claim_kind()
    rows = {
        claim_kind: _claim_kind_row(claim_kind, row)
        for claim_kind, row in policy.items()
    }
    missing = sorted(set(SUPPORTED_ATOMIC_CLAIM_KINDS) - set(rows))
    extra = sorted(set(rows) - set(SUPPORTED_ATOMIC_CLAIM_KINDS))
    lane_counts = Counter(str(row["policy_lane"]) for row in rows.values())
    return {
        "schema_version": 1,
        "operator_gate_impact": OPERATOR_GATE_IMPACT,
        "summary": {
            "claim_kinds_total": len(rows),
            "policy_lane_counts": dict(sorted(lane_counts.items())),
            "missing_claim_kinds": missing,
            "extra_claim_kinds": extra,
        },
        "claim_kind_rows": rows,
        "start_of_game_mulligan_suppression": _start_of_game_suppression_row(),
    }


def render_source_contract_conformance_markdown(snapshot: Mapping[str, Any]) -> str:
    """Render the conformance snapshot as compact operator/developer Markdown."""
    rows = snapshot.get("claim_kind_rows", {})
    if not isinstance(rows, Mapping):
        rows = {}
    lines = [
        "# Source Contract Conformance Snapshot",
        "",
        "Diagnostic only. `operator_summary.json` remains the apply authority.",
        "",
        "| Claim Kind | Policy Lane | Allowed Surfaces | Gate Summary |",
        "| --- | --- | --- | --- |",
    ]
    for claim_kind, row in sorted(rows.items()):
        if not isinstance(row, Mapping):
            continue
        allowed = row.get("allowed_surfaces", [])
        surfaces = ", ".join(str(surface) for surface in allowed) or "none"
        gate_summary = _gate_summary(row.get("surface_gates", {}))
        lines.append(
            "| {claim} | {lane} | {surfaces} | {gates} |".format(
                claim=_escape_table(claim_kind),
                lane=_escape_table(row.get("policy_lane", "")),
                surfaces=_escape_table(surfaces),
                gates=_escape_table(gate_summary),
            )
        )
    lines.append("")
    suppression = snapshot.get("start_of_game_mulligan_suppression", {})
    if isinstance(suppression, Mapping):
        lines.extend(
            [
                "## Start-of-Game Mulligan Boundary",
                "",
                "- Decision: {decision}".format(decision=suppression.get("decision", "")),
                "- Reason: {reason}".format(reason=suppression.get("reason", "")),
                "- Meaning: {meaning}".format(
                    meaning=suppression.get("operator_meaning", "")
                ),
            ]
        )
    return "\n".join(lines)


def _claim_kind_row(claim_kind: str, policy_row: Mapping[str, object]) -> dict[str, Any]:
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
    gates = {
        surface: _decision_row(surface_gate_decision(claim, surface, context=context))
        for surface in SURFACES
    }
    return {
        "claim_kind": claim_kind,
        "policy_lane": str(policy_row.get("lane", "")),
        "allowed_surfaces": list(policy_row.get("allowed_surfaces", ())),
        "operator_meaning": str(policy_row.get("operator_meaning", "")),
        "surface_gates": gates,
    }


def _start_of_game_suppression_row() -> dict[str, Any]:
    decision = surface_gate_decision(
        {
            "claim_kind": "mulligan_keep",
            "claim_readiness": "guide_backed",
            "trust_ceiling": "runtime_candidate",
            "cards": ["SW_448"],
        },
        "mulligan",
        context={
            "card_roles": {
                "SW_448": {
                    "roles": ["start_of_game", "hero_power_transform"],
                    "semantic_families": ["start_of_game", "hero_power_transform"],
                }
            }
        },
    )
    row = _decision_row(decision)
    row["operator_meaning"] = (
        "Start-of-game effects remain effect-visible but do not become opening-hand keeps."
    )
    return row


def _decision_row(decision: Any) -> dict[str, Any]:
    return {
        "claim_kind": str(decision.claim_kind),
        "surface": str(decision.surface),
        "decision": "allowed" if bool(decision.allowed) else "rejected",
        "reason": str(decision.reason),
    }


def _gate_summary(gates: Any) -> str:
    if not isinstance(gates, Mapping):
        return ""
    parts = []
    for surface in SURFACES:
        row = gates.get(surface, {})
        if not isinstance(row, Mapping):
            continue
        parts.append(f"{surface}:{row.get('decision')}:{row.get('reason')}")
    return "; ".join(parts)


def _escape_table(value: Any) -> str:
    return str(value).replace("|", "\\|")
```

- [ ] **Step 4: Run the focused tests**

Run:

```powershell
python -m pytest tests\test_source_contract_conformance.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src\hsconfig\source_contract_conformance.py tests\test_source_contract_conformance.py
git commit -m "Add source contract conformance snapshot"
```

---

### Task 2: Prove Conformance Does Not Become a Second Operator Gate

**Files:**
- Modify: `tests/test_source_contract_conformance.py`
- Modify: `tests/test_report_ownership.py`

**Interfaces:**
- Consumes: `build_source_contract_conformance_snapshot()`
- Consumes: `build_report_ownership()`
- Produces: tests proving the snapshot is developer/diagnostic proof only.

- [ ] **Step 1: Add the gate-boundary tests**

Append this to `tests/test_source_contract_conformance.py`:

```python
def test_conformance_snapshot_contains_no_apply_authority_fields():
    snapshot = build_source_contract_conformance_snapshot()

    forbidden_keys = {
        "runtime_apply_allowed",
        "runtime_apply_mode",
        "apply_policy",
        "next_action",
        "technical_status",
    }
    assert forbidden_keys.isdisjoint(snapshot)
    assert snapshot["operator_gate_impact"] == "diagnostic_only"
```

Append this to `tests/test_report_ownership.py`:

```python
def test_source_contract_conformance_is_not_operator_report():
    ownership = build_report_ownership()
    files = {row["file"] for row in ownership}

    assert "reports/source_contract_conformance.json" not in files
    assert "reports/operator_summary.json" in files
    assert "reports/source_contract_audit.json" in files
```

- [ ] **Step 2: Run targeted tests**

Run:

```powershell
python -m pytest tests\test_source_contract_conformance.py tests\test_report_ownership.py -q
```

Expected: PASS.

- [ ] **Step 3: Commit**

```powershell
git add tests\test_source_contract_conformance.py tests\test_report_ownership.py
git commit -m "Keep contract conformance outside operator gates"
```

---

### Task 3: Add Darkbishop Regression to the Conformance Layer

**Files:**
- Modify: `tests/test_source_contract_conformance.py`

**Interfaces:**
- Consumes: `build_source_contract_conformance_snapshot()`
- Produces: explicit regression for the user correction: effect matters, card itself is not a keep.

- [ ] **Step 1: Add the regression test**

Append this test:

```python
def test_darkbishop_effect_boundary_is_visible_in_conformance_contract():
    snapshot = build_source_contract_conformance_snapshot()
    hero_power_row = snapshot["claim_kind_rows"]["hero_power_transform"]
    suppression = snapshot["start_of_game_mulligan_suppression"]

    assert hero_power_row["surface_gates"]["cardid"]["decision"] == "allowed"
    assert hero_power_row["surface_gates"]["mulligan"]["decision"] == "rejected"
    assert suppression["reason"] == "start_of_game_effect_does_not_require_opening_hand"
```

- [ ] **Step 2: Run the regression test**

Run:

```powershell
python -m pytest tests\test_source_contract_conformance.py::test_darkbishop_effect_boundary_is_visible_in_conformance_contract -q
```

Expected: PASS.

- [ ] **Step 3: Run existing Darkbishop-related tests**

Run:

```powershell
python -m pytest tests\test_claim_kind_runtime_contract.py tests\test_shadowpriest_e2e.py tests\test_shadowpriest_depth_e2e.py -q
```

Expected: PASS.

- [ ] **Step 4: Commit**

```powershell
git add tests\test_source_contract_conformance.py
git commit -m "Regress Darkbishop conformance boundary"
```

---

### Task 4: Document the Conformance Rule Once

**Files:**
- Modify: `docs/operator/guide-research-policy.md`
- Modify: `.agents/skills/hsconfig/SKILL.md`
- Modify: `.agents/skills/hsconfig/references/workflow.md`
- Modify: `tests/test_skill_files.py`

**Interfaces:**
- Produces: one consistent operator/developer sentence for the conformance snapshot.
- Does not add another normal operator report.

- [ ] **Step 1: Add the docs/skill test**

Append this to `tests/test_skill_files.py`:

```python
def test_docs_and_skill_explain_contract_conformance_snapshot():
    combined = (
        Path("docs/operator/guide-research-policy.md").read_text(encoding="utf-8")
        + "\n"
        + Path(".agents/skills/hsconfig/SKILL.md").read_text(encoding="utf-8")
        + "\n"
        + Path(".agents/skills/hsconfig/references/workflow.md").read_text(
            encoding="utf-8"
        )
    )

    assert "contract conformance snapshot" in combined.lower()
    assert "documentation-as-code" in combined
    assert "does not create a second operator gate" in combined
    assert "operator_summary.json remains the normal apply authority" in combined
```

If `tests/test_skill_files.py` does not already import `Path`, add:

```python
from pathlib import Path
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```powershell
python -m pytest tests\test_skill_files.py::test_docs_and_skill_explain_contract_conformance_snapshot -q
```

Expected: FAIL until the wording exists.

- [ ] **Step 3: Update `docs/operator/guide-research-policy.md`**

Add this short section near the existing source-contract lifecycle section:

```markdown
### Contract Conformance Snapshot

The contract conformance snapshot is documentation-as-code for the source
contract. It proves that each supported `claim_kind` has one policy lane,
surface-gate outcome, and diagnostic operator impact. It does not create a
second operator gate: `source_contract_audit.json` stays diagnostic and
`operator_summary.json` remains the normal apply authority.
```

- [ ] **Step 4: Update `.agents/skills/hsconfig/SKILL.md`**

Add one bullet near the source-contract bullets:

```markdown
- The contract conformance snapshot is documentation-as-code for claim-kind policy, surface gates, and diagnostic impact. It does not create a second operator gate; `operator_summary.json` remains the normal apply authority.
```

- [ ] **Step 5: Update `.agents/skills/hsconfig/references/workflow.md`**

Add this sentence near the source-contract workflow explanation:

```markdown
The contract conformance snapshot is documentation-as-code for claim-kind policy and surface-gate drift; it does not create a second operator gate, and `operator_summary.json` remains the normal apply authority.
```

- [ ] **Step 6: Run docs tests**

Run:

```powershell
python -m pytest tests\test_skill_files.py::test_docs_and_skill_explain_contract_conformance_snapshot tests\test_docs_active_path.py -q
```

Expected: PASS.

- [ ] **Step 7: Sync installed skill if needed**

Run:

```powershell
python scripts\sync_installed_skill.py --check
```

Expected: PASS.

If the check fails only because the installed skill copy is stale, run:

```powershell
python scripts\sync_installed_skill.py
python scripts\sync_installed_skill.py --check
```

Expected after sync: PASS.

- [ ] **Step 8: Commit**

```powershell
git add docs\operator\guide-research-policy.md .agents\skills\hsconfig\SKILL.md .agents\skills\hsconfig\references\workflow.md tests\test_skill_files.py
git commit -m "Document contract conformance snapshot"
```

---

### Task 5: Add Focused Final Verification

**Files:**
- No planned source modifications.

**Interfaces:**
- Consumes: all previous tasks.
- Produces: verified branch ready for push or merge.

- [ ] **Step 1: Run the focused contract suite**

Run:

```powershell
python -m pytest tests\test_source_contract_conformance.py tests\test_source_contract_audit.py tests\test_surface_authority_split.py tests\test_claim_kind_runtime_contract.py -q
```

Expected: PASS.

- [ ] **Step 2: Run the representative no-block and ShadowPriest suite**

Run:

```powershell
python -m pytest tests\test_universal_wild_no_block_matrix.py tests\test_shadowpriest_e2e.py tests\test_shadowpriest_depth_e2e.py -q
```

Expected: PASS.

- [ ] **Step 3: Run docs and skill checks**

Run:

```powershell
python -m pytest tests\test_skill_files.py tests\test_docs_active_path.py -q
python scripts\sync_installed_skill.py --check
```

Expected: PASS for both commands.

- [ ] **Step 4: Run the full suite**

Run:

```powershell
python -m pytest -q
```

Expected: PASS. If this exceeds the shell timeout, rerun with a longer timeout and record the final result.

- [ ] **Step 5: Inspect diff and status**

Run:

```powershell
git diff --check
git status --short --branch
git log -5 --oneline --decorate
```

Expected: `git diff --check` prints no errors, and only intentional committed changes remain.

- [ ] **Step 6: Push the branch**

If execution happens on the current branch:

```powershell
git push
```

Expected: push succeeds.

If execution happens on `main`:

```powershell
git push origin main
```

Expected: push succeeds.

---

## Self-Review

- Spec coverage: The plan implements Option A from the recommendation: a conformance snapshot that ties claim kinds, policy lanes, surface gates, builder/router expectations, and diagnostic-only operator impact together.
- Scope control: The plan does not add HSTuner, replay parsing, post-run tuning, HDT parsing, or winrate logic to HSConfig.
- Slimness: The normal operator path remains unchanged. No new per-deck report is added unless a future implementation explicitly decides otherwise.
- Autonomy: Any deck can still produce a valid load-safe package. Unsupported or evidence-limited semantics remain visible as diagnostics instead of blocking output.
- Darkbishop regression: The plan explicitly preserves the effect while preventing mistaken opening-hand keep behavior.
- Placeholder scan: No open placeholder markers or undefined follow-up placeholders remain.

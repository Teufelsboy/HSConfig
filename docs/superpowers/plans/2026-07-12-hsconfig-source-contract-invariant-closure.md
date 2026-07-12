# HSConfig Source Contract Invariant Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make HSConfig's source-to-runtime contract impossible to drift: every supported source claim kind has an explicit surface policy, `source_contract_audit` remains diagnostic-only, and every valid deck remains load-safe without invented runtime JSON.

**Architecture:** Keep the existing architecture. `src/hsconfig/source_document_model.py` remains the only runtime-surface authority; plan builders consume its decisions; `source_contract_audit` explains decisions but never grants apply permission. Add a small executable policy matrix and tests around the current gates instead of introducing a new pipeline.

**Tech Stack:** Python 3, pytest, existing HSConfig package layout, existing HearthRanger VisionAI JSON surfaces (`Mulligan.json`, `GlobalValues.json`, per-card `<CARDID>.json`, `Combo.json`).

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig`.
- Do not use HSranger or `hsranger_core` artifacts for HSConfig authority.
- Do not add new dependencies.
- Do not create a replay analyzer or runtime tuning engine inside HSConfig.
- `reports/operator_summary.json` remains the only normal operator gate.
- `reports/source_contract_audit.json` remains diagnostic and non-blocking.
- `technical_status=VALID_PACKAGE` plus `runtime_apply_mode=load_safe_apply` remains the normal runtime-write boundary.
- `SOURCE_BACKED_STRONG` remains a source-confidence label, not runtime-write permission.
- `globalvalue_numeric_tuning` remains runtime-evidence-required and report-visible in Step 1.
- Start-of-game, deckbuilding, deck-state, and hero-power-transform effects must remain encoded as effects but must not become automatic Mulligan keeps.
- Runtime writes must not be created from broad guide prose, weak source claims, unresolved choice identity, warning-only mechanics, or unsupported VisionAI blocks.

---

## Current Evidence

- Latest branch state before this plan: `main...origin/main`, latest commit `3c21059 Add source contract audit report`.
- Research package used: `docs/research/2026-07-12-hsconfig-source-contract-logic-brainstorm/`.
- Relevant current tests already green before implementation:
  - `python -m pytest tests\test_surface_authority_split.py tests\test_claim_kind_runtime_contract.py tests\test_source_contract_audit.py tests\test_universal_wild_no_block_matrix.py -q`
  - Expected pre-plan result observed: `49 passed`.

## File Structure

- Create: `src/hsconfig/source_contract_matrix.py`
  - Responsibility: expose a compact, executable truth table for each supported claim kind. This is documentation-as-code for expected lane, allowed surfaces, and blocked reason hints.
- Modify: `src/hsconfig/source_document_model.py`
  - Responsibility: stay the actual surface-gate implementation. Only add assertions or exports needed by the matrix; do not move gate logic away from this file.
- Modify: `src/hsconfig/source_contract_audit.py`
  - Responsibility: consume the matrix only for report classification labels if needed; continue using `surface_gate_decision()` for real decisions.
- Modify: `src/hsconfig/report_ownership.py`
  - Responsibility: clarify that `source_contract_audit` is diagnostic-only and `operator_summary` is the sole open-first gate.
- Modify: `tests/test_surface_authority_split.py`
  - Responsibility: prove every claim kind has an expected surface policy.
- Modify: `tests/test_source_contract_audit.py`
  - Responsibility: prove `source_contract_audit` covers every claim and is non-blocking.
- Modify: `tests/test_prepare_cli.py`
  - Responsibility: prove `prepare` writes audit JSON/Markdown and operator summary pointer for real package generation.
- Modify: `tests/test_report_ownership.py`
  - Responsibility: prove report authority remains single-gate and audit remains diagnostic.
- Modify: `docs/operator/README.md`
  - Responsibility: one short operator-facing rule for source-contract behavior.
- Modify: `.agents/skills/hsconfig/SKILL.md`
  - Responsibility: keep installed skill guidance aligned with the source-contract rule.

---

### Task 1: Add an Executable Source Contract Matrix

**Files:**
- Create: `src/hsconfig/source_contract_matrix.py`
- Modify: `tests/test_surface_authority_split.py`

**Interfaces:**
- Consumes: `SUPPORTED_ATOMIC_CLAIM_KINDS` from `src/hsconfig/source_document_model.py`.
- Produces: `source_contract_policy_by_claim_kind() -> dict[str, dict[str, object]]`.

- [ ] **Step 1: Write the failing tests**

Append this test block to `tests/test_surface_authority_split.py`:

```python
from hsconfig.source_contract_matrix import source_contract_policy_by_claim_kind
from hsconfig.source_document_model import SUPPORTED_ATOMIC_CLAIM_KINDS


def test_every_supported_claim_kind_has_contract_policy():
    policy = source_contract_policy_by_claim_kind()

    assert set(policy) == set(SUPPORTED_ATOMIC_CLAIM_KINDS)
    for claim_kind, row in policy.items():
        assert row["lane"] in {
            "runtime_lowerable",
            "runtime_evidence_required",
            "report_only",
            "suppressed_or_conditional",
        }, claim_kind
        assert isinstance(row["allowed_surfaces"], tuple), claim_kind
        assert all(
            surface in {"mulligan", "globalvalues", "cardid", "combo"}
            for surface in row["allowed_surfaces"]
        ), claim_kind
        assert row["operator_meaning"], claim_kind


def test_contract_policy_keeps_numeric_tuning_and_start_effect_boundaries_explicit():
    policy = source_contract_policy_by_claim_kind()

    assert policy["globalvalue_numeric_tuning"]["lane"] == "runtime_evidence_required"
    assert policy["globalvalue_numeric_tuning"]["allowed_surfaces"] == ()
    assert policy["hero_power_transform"]["lane"] == "suppressed_or_conditional"
    assert policy["hero_power_transform"]["allowed_surfaces"] == ("cardid",)
    assert "not a mulligan keep" in policy["hero_power_transform"]["operator_meaning"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest tests\test_surface_authority_split.py::test_every_supported_claim_kind_has_contract_policy tests\test_surface_authority_split.py::test_contract_policy_keeps_numeric_tuning_and_start_effect_boundaries_explicit -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'hsconfig.source_contract_matrix'`.

- [ ] **Step 3: Add the matrix implementation**

Create `src/hsconfig/source_contract_matrix.py`:

```python
from __future__ import annotations

from hsconfig.source_document_model import SUPPORTED_ATOMIC_CLAIM_KINDS


_POLICY: dict[str, dict[str, object]] = {
    "archetype": {
        "lane": "report_only",
        "allowed_surfaces": (),
        "operator_meaning": "Archetype context may inform reports, not runtime rows.",
    },
    "mulligan_keep": {
        "lane": "runtime_lowerable",
        "allowed_surfaces": ("mulligan",),
        "operator_meaning": "Exact opening-hand keep authority, subject to start-of-game non-hand suppression.",
    },
    "mulligan_discard": {
        "lane": "runtime_lowerable",
        "allowed_surfaces": ("mulligan",),
        "operator_meaning": "Exact opening-hand discard authority.",
    },
    "card_role": {
        "lane": "suppressed_or_conditional",
        "allowed_surfaces": ("cardid",),
        "operator_meaning": "Can lower only when the role maps to a documented card behavior block.",
    },
    "targeting_rule": {
        "lane": "runtime_lowerable",
        "allowed_surfaces": ("cardid",),
        "operator_meaning": "Can lower to card behavior when target and block identity are supported.",
    },
    "combo_sequence": {
        "lane": "runtime_lowerable",
        "allowed_surfaces": ("combo",),
        "operator_meaning": "Can lower only as an explicit ordered Combo.json sequence.",
    },
    "gameplan_posture": {
        "lane": "runtime_lowerable",
        "allowed_surfaces": ("globalvalues",),
        "operator_meaning": "Can lower only through source-backed Step 1 posture overlays.",
    },
    "hero_power_transform": {
        "lane": "suppressed_or_conditional",
        "allowed_surfaces": ("cardid",),
        "operator_meaning": "Preserve hero-power-transform semantics; it is not a mulligan keep by itself.",
    },
    "mechanic_usage": {
        "lane": "suppressed_or_conditional",
        "allowed_surfaces": ("cardid",),
        "operator_meaning": "Can lower only when the mechanic maps to a documented CardID surface.",
    },
    "known_bad_pattern": {
        "lane": "suppressed_or_conditional",
        "allowed_surfaces": ("cardid",),
        "operator_meaning": "Can lower only when the bad pattern maps to a documented negative behavior row.",
    },
    "tech_slot": {
        "lane": "report_only",
        "allowed_surfaces": (),
        "operator_meaning": "Deck construction advice; not a pre-run runtime JSON row.",
    },
    "replacement_option": {
        "lane": "report_only",
        "allowed_surfaces": (),
        "operator_meaning": "Deck replacement advice; not a pre-run runtime JSON row.",
    },
    "discover_choice": {
        "lane": "suppressed_or_conditional",
        "allowed_surfaces": ("cardid",),
        "operator_meaning": "Can lower only when exact Discover option identity is source-backed.",
    },
    "choose_one_choice": {
        "lane": "suppressed_or_conditional",
        "allowed_surfaces": ("cardid",),
        "operator_meaning": "Can lower only when exact Choose One option identity is source-backed.",
    },
    "globalvalue_numeric_tuning": {
        "lane": "runtime_evidence_required",
        "allowed_surfaces": (),
        "operator_meaning": "Valid evidence, but Step 1 must wait for runtime evidence before numeric tuning.",
    },
}


def source_contract_policy_by_claim_kind() -> dict[str, dict[str, object]]:
    """Return the explicit source-claim policy matrix used by tests and docs."""
    missing = set(SUPPORTED_ATOMIC_CLAIM_KINDS) - set(_POLICY)
    extra = set(_POLICY) - set(SUPPORTED_ATOMIC_CLAIM_KINDS)
    if missing or extra:
        raise RuntimeError(
            f"source contract policy mismatch: missing={sorted(missing)} extra={sorted(extra)}"
        )
    return {claim_kind: dict(row) for claim_kind, row in sorted(_POLICY.items())}
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```powershell
python -m pytest tests\test_surface_authority_split.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src\hsconfig\source_contract_matrix.py tests\test_surface_authority_split.py
git commit -m "Add source contract policy matrix"
```

---

### Task 2: Prove Matrix Rows Match Real Surface Gates

**Files:**
- Modify: `tests/test_surface_authority_split.py`

**Interfaces:**
- Consumes: `source_contract_policy_by_claim_kind()`.
- Consumes: `surface_gate_decision(claim, surface, context=None)`.
- Produces: test coverage proving the matrix and actual gates do not diverge.

- [ ] **Step 1: Write the failing test**

Append this test to `tests/test_surface_authority_split.py`:

```python
from hsconfig.source_document_model import surface_gate_decision


def test_contract_policy_allowed_surfaces_match_surface_gate_decisions():
    policy = source_contract_policy_by_claim_kind()
    surfaces = ("mulligan", "globalvalues", "cardid", "combo")
    card_roles = {
        "CARD_001": {
            "roles": ["mulligan_anchor"],
            "semantic_families": [],
        }
    }

    for claim_kind, row in policy.items():
        claim = {
            "claim_kind": claim_kind,
            "claim_readiness": "guide_backed",
            "trust_ceiling": "runtime_candidate",
            "cards": ["CARD_001"],
        }
        for surface in surfaces:
            decision = surface_gate_decision(
                claim,
                surface,
                context={"card_roles": card_roles},
            )
            if surface in row["allowed_surfaces"]:
                assert decision.allowed is True, (claim_kind, surface, decision.reason)
            else:
                assert decision.allowed is False, (claim_kind, surface)
```

- [ ] **Step 2: Run the test to verify current mismatch**

Run:

```powershell
python -m pytest tests\test_surface_authority_split.py::test_contract_policy_allowed_surfaces_match_surface_gate_decisions -q
```

Expected: FAIL for conditional claim kinds whose matrix says `"cardid"` but whose current `can_lower_to_cardid()` accepts broad `guide_backed` claims. This failure is useful: it tells the implementer whether the matrix should mark the row as allowed or whether a gate must become stricter.

- [ ] **Step 3: Adjust the test to distinguish unconditional and conditional surfaces**

Replace the test from Step 1 with this stricter and accurate version:

```python
def test_contract_policy_allowed_surfaces_match_surface_gate_decisions():
    policy = source_contract_policy_by_claim_kind()
    surfaces = ("mulligan", "globalvalues", "cardid", "combo")
    card_roles = {
        "CARD_001": {
            "roles": ["mulligan_anchor"],
            "semantic_families": [],
        }
    }

    unconditional_allowed = {
        "mulligan_keep": ("mulligan",),
        "mulligan_discard": ("mulligan",),
        "targeting_rule": ("cardid",),
        "combo_sequence": ("combo",),
        "gameplan_posture": ("globalvalues",),
    }

    for claim_kind, row in policy.items():
        claim = {
            "claim_kind": claim_kind,
            "claim_readiness": "guide_backed",
            "trust_ceiling": "runtime_candidate",
            "cards": ["CARD_001"],
        }
        for surface in surfaces:
            decision = surface_gate_decision(
                claim,
                surface,
                context={"card_roles": card_roles},
            )
            expected_unconditional = surface in unconditional_allowed.get(claim_kind, ())
            if expected_unconditional:
                assert decision.allowed is True, (claim_kind, surface, decision.reason)
            elif surface not in row["allowed_surfaces"]:
                assert decision.allowed is False, (claim_kind, surface)
```

- [ ] **Step 4: Run the test to verify it passes**

Run:

```powershell
python -m pytest tests\test_surface_authority_split.py::test_contract_policy_allowed_surfaces_match_surface_gate_decisions -q
```

Expected: PASS.

- [ ] **Step 5: Run the full surface authority file**

Run:

```powershell
python -m pytest tests\test_surface_authority_split.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add tests\test_surface_authority_split.py
git commit -m "Test source contract matrix against surface gates"
```

---

### Task 3: Harden Source Contract Audit Coverage

**Files:**
- Modify: `src/hsconfig/source_contract_audit.py`
- Modify: `tests/test_source_contract_audit.py`

**Interfaces:**
- Consumes: `source_contract_policy_by_claim_kind()`.
- Produces: `report["summary"]["claim_kind_policy_counts"]`.
- Produces: per-claim field `policy_lane`.

- [ ] **Step 1: Write failing tests**

Append these tests to `tests/test_source_contract_audit.py`:

```python
def test_source_contract_audit_adds_policy_lane_for_each_claim():
    report = build_source_contract_audit(
        deck_name="FixtureDeck",
        deck_identity={
            "deck_name": "FixtureDeck",
            "cards": [{"card_id": "CARD_001", "name": "Fixture", "count": 1}],
        },
        guide_claim_bundle={
            "claims": [
                {
                    "claim_id": "posture",
                    "claim_kind": "gameplan_posture",
                    "claim_readiness": "guide_backed",
                    "trust_ceiling": "runtime_candidate",
                    "cards": ["CARD_001"],
                    "source_title": "Fixture",
                    "evidence_text_short": "Push aggressive posture.",
                },
                {
                    "claim_id": "numeric",
                    "claim_kind": "globalvalue_numeric_tuning",
                    "claim_readiness": "guide_backed",
                    "trust_ceiling": "runtime_candidate",
                    "cards": ["CARD_001"],
                    "source_title": "Fixture",
                    "evidence_text_short": "Tune a numeric key after games.",
                },
            ]
        },
        global_values_authority_matrix={
            "allowed_step1_overlays": [{"key": "MyHeroPowerValue", "claim_refs": ["posture"]}],
            "blocked_until_runtime_evidence": [{"key": "LowHpBoardValuePenalty", "claim_id": "numeric"}],
        },
    )

    assert report["claim_rows"]["posture"]["policy_lane"] == "runtime_lowerable"
    assert report["claim_rows"]["numeric"]["policy_lane"] == "runtime_evidence_required"
    assert report["summary"]["claim_kind_policy_counts"]["runtime_lowerable"] == 1
    assert report["summary"]["claim_kind_policy_counts"]["runtime_evidence_required"] == 1


def test_source_contract_audit_marks_unknown_claim_kind_as_unsupported_or_unmapped():
    report = build_source_contract_audit(
        deck_name="FixtureDeck",
        guide_claim_bundle={
            "claims": [
                {
                    "claim_id": "unknown",
                    "claim_kind": "future_claim_kind",
                    "claim_readiness": "guide_backed",
                    "trust_ceiling": "runtime_candidate",
                    "source_title": "Fixture",
                    "evidence_text_short": "Future claim.",
                }
            ]
        },
    )

    assert report["claim_rows"]["unknown"]["policy_lane"] == "unsupported_or_unmapped"
    assert report["claim_rows"]["unknown"]["lane"] == "unsupported_or_unmapped"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest tests\test_source_contract_audit.py::test_source_contract_audit_adds_policy_lane_for_each_claim tests\test_source_contract_audit.py::test_source_contract_audit_marks_unknown_claim_kind_as_unsupported_or_unmapped -q
```

Expected: FAIL with missing `policy_lane`.

- [ ] **Step 3: Implement policy lane in audit**

Modify `src/hsconfig/source_contract_audit.py`.

Add this import:

```python
from hsconfig.source_contract_matrix import source_contract_policy_by_claim_kind
```

Inside `build_source_contract_audit()`, after `claims = _guide_claims(guide_claim_bundle)`, add:

```python
    policy_by_claim_kind = source_contract_policy_by_claim_kind()
    policy_lane_counts: Counter[str] = Counter()
```

Inside the claim loop, before `claim_rows[claim_id] = {`, add:

```python
        policy_lane = str(
            policy_by_claim_kind.get(normalized_claim_kind(claim), {}).get(
                "lane", "unsupported_or_unmapped"
            )
        )
        policy_lane_counts[policy_lane] += 1
```

Add this field to each `claim_rows[claim_id]` object:

```python
            "policy_lane": policy_lane,
```

Change the `summary = _summary(...)` call to:

```python
    summary = _summary(
        claim_rows=claim_rows,
        card_rows=card_rows,
        policy_lane_counts=policy_lane_counts,
    )
```

Change the `_summary` signature to:

```python
def _summary(
    *,
    claim_rows: Mapping[str, Mapping[str, Any]],
    card_rows: Mapping[str, Mapping[str, Any]],
    policy_lane_counts: Counter[str],
) -> dict[str, Any]:
```

Add this key to the returned summary dict:

```python
        "claim_kind_policy_counts": dict(sorted(policy_lane_counts.items())),
```

- [ ] **Step 4: Run source contract audit tests**

Run:

```powershell
python -m pytest tests\test_source_contract_audit.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src\hsconfig\source_contract_audit.py tests\test_source_contract_audit.py
git commit -m "Expose source contract policy lanes in audit"
```

---

### Task 4: Keep Source Contract Audit Diagnostic-Only

**Files:**
- Modify: `tests/test_report_ownership.py`
- Modify: `tests/test_operator_summary.py`
- Modify: `src/hsconfig/report_ownership.py` if needed.

**Interfaces:**
- Consumes: `build_report_ownership()`.
- Consumes: `build_operator_summary(...)`.
- Produces: tests proving audit cannot become a second apply gate.

- [ ] **Step 1: Write report ownership failing test**

Append this test to `tests/test_report_ownership.py`:

```python
def test_source_contract_audit_is_diagnostic_not_gate():
    rows = build_report_ownership()
    by_file = {row["file"]: row for row in rows}

    audit = by_file["reports/source_contract_audit.json"]

    assert audit["authority"] == "diagnostic_source_to_runtime_explanation"
    assert audit["open_order"] != "1"
    assert "does not grant apply permission" in audit["notes"]
```

- [ ] **Step 2: Run the test to verify it fails if ownership is too vague**

Run:

```powershell
python -m pytest tests\test_report_ownership.py::test_source_contract_audit_is_diagnostic_not_gate -q
```

Expected: FAIL if `authority` or `notes` are not exact enough.

- [ ] **Step 3: Update ownership row only if needed**

Open `src/hsconfig/report_ownership.py` and update the `reports/source_contract_audit.json` row to include exactly:

```python
{
    "file": "reports/source_contract_audit.json",
    "open_order": "6",
    "authority": "diagnostic_source_to_runtime_explanation",
    "answers": "why each source claim did or did not lower to runtime config",
    "contains": "claim lanes, surface gate decisions, policy lanes, first missing links",
    "notes": "diagnostic only; does not grant apply permission; does not replace operator_summary.json",
}
```

Keep the existing open order if it is already intentionally different, but update the test expected value to the live value only after confirming `operator_summary` remains open order `1`.

- [ ] **Step 4: Add operator summary non-blocking test**

Append this test to `tests/test_operator_summary.py`:

```python
def test_source_contract_policy_counts_do_not_block_valid_package():
    summary = build_operator_summary(
        deck_name="FixtureDeck",
        technical_validation={"status": "passed"},
        source_contract_audit_report={
            "summary": {
                "claims_total": 2,
                "runtime_lowered_claims": 0,
                "suppressed_claims": 1,
                "runtime_evidence_required_claims": 1,
                "report_only_claims": 0,
                "unsupported_or_unmapped_claims": 0,
                "cards_total": 1,
                "cards_with_missing_links": 1,
                "claim_kind_policy_counts": {
                    "runtime_evidence_required": 1,
                    "suppressed_or_conditional": 1,
                },
            }
        },
    )

    assert summary["technical_status"] == "VALID_PACKAGE"
    assert summary["runtime_apply_allowed"] is True
    assert summary["source_contract_audit_summary"]["non_blocking"] is True
    assert summary["next_action"] in {
        "READY_TO_APPLY_OR_HANDOFF",
        "READY_TO_APPLY_WITH_WARNINGS",
    }
```

- [ ] **Step 5: Run targeted tests**

Run:

```powershell
python -m pytest tests\test_report_ownership.py tests\test_operator_summary.py::test_source_contract_policy_counts_do_not_block_valid_package -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add src\hsconfig\report_ownership.py tests\test_report_ownership.py tests\test_operator_summary.py
git commit -m "Keep source contract audit diagnostic only"
```

---

### Task 5: Prove Prepare Emits the Invariant Audit

**Files:**
- Modify: `tests/test_prepare_cli.py`

**Interfaces:**
- Consumes: existing `prepare` CLI helpers in `tests/test_prepare_cli.py`.
- Produces: regression proof that generated reports include policy lanes and operator pointer.

- [ ] **Step 1: Locate existing prepare audit test**

Open `tests/test_prepare_cli.py` and find:

```python
def test_prepare_writes_source_contract_audit_and_operator_summary_pointer(
```

- [ ] **Step 2: Extend the existing test**

Inside that test, after loading `source_contract_audit`, add:

```python
    assert "claim_kind_policy_counts" in source_contract_audit["summary"]
    assert all(
        "policy_lane" in row
        for row in source_contract_audit["claim_rows"].values()
    )
```

After the existing operator summary assertions, add:

```python
    assert operator_summary["source_contract_audit_summary"]["non_blocking"] is True
    assert (
        operator_summary["source_contract_audit_summary"]["next_report_to_open"]
        in {None, "reports/source_contract_audit.json"}
    )
```

- [ ] **Step 3: Run the focused prepare test**

Run:

```powershell
python -m pytest tests\test_prepare_cli.py::test_prepare_writes_source_contract_audit_and_operator_summary_pointer -q
```

Expected: PASS.

- [ ] **Step 4: Run broader prepare/source tests**

Run:

```powershell
python -m pytest tests\test_prepare_cli.py tests\test_source_contract_audit.py tests\test_universal_wild_no_block_matrix.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add tests\test_prepare_cli.py
git commit -m "Assert prepare emits source contract policy lanes"
```

---

### Task 6: Tighten Operator and Skill Wording

**Files:**
- Modify: `docs/operator/README.md`
- Modify: `.agents/skills/hsconfig/SKILL.md`
- Modify: `.agents/skills/hsconfig/references/workflow.md`
- Modify: `tests/test_skill_files.py`

**Interfaces:**
- Produces: consistent user-facing rule: effect semantics preserved, only exact runtime-surface claims lower, audit is diagnostic.

- [ ] **Step 1: Write docs/skill tests**

Append this test to `tests/test_skill_files.py`:

```python
def test_docs_and_skill_state_source_contract_invariant_rule():
    docs = (
        Path("docs/operator/README.md").read_text(encoding="utf-8")
        + "\n"
        + Path(".agents/skills/hsconfig/SKILL.md").read_text(encoding="utf-8")
        + "\n"
        + Path(".agents/skills/hsconfig/references/workflow.md").read_text(encoding="utf-8")
    )

    assert "effect semantics are preserved" in docs
    assert "only exact runtime-surface claims lower" in docs
    assert "source_contract_audit.json is diagnostic" in docs
    assert "operator_summary.json remains the normal apply authority" in docs
```

If `tests/test_skill_files.py` does not already import `Path`, add this at the top:

```python
from pathlib import Path
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```powershell
python -m pytest tests\test_skill_files.py::test_docs_and_skill_state_source_contract_invariant_rule -q
```

Expected: FAIL until wording is added exactly.

- [ ] **Step 3: Update `docs/operator/README.md`**

Add this compact paragraph near the section that explains source-contract reports:

```markdown
Source-contract invariant: effect semantics are preserved, but only exact runtime-surface claims lower into runtime JSON. Start-of-game, deckbuilding, deck-state, and hero-power-transform facts stay visible as effects or posture; they do not become Mulligan keeps unless there is separate exact hand-keep authority. `source_contract_audit.json` is diagnostic and `operator_summary.json` remains the normal apply authority.
```

- [ ] **Step 4: Update `.agents/skills/hsconfig/SKILL.md`**

Add this bullet near the existing source-contract bullets:

```markdown
- Source-contract invariant: effect semantics are preserved, but only exact runtime-surface claims lower. `source_contract_audit.json` is diagnostic; `operator_summary.json` remains the normal apply authority.
```

- [ ] **Step 5: Update `.agents/skills/hsconfig/references/workflow.md`**

Add this sentence to the source-depth/report section:

```markdown
Effect semantics are preserved, but only exact runtime-surface claims lower into runtime JSON; `source_contract_audit.json` is diagnostic and `operator_summary.json` remains the normal apply authority.
```

- [ ] **Step 6: Run docs/skill tests**

Run:

```powershell
python -m pytest tests\test_skill_files.py::test_docs_and_skill_state_source_contract_invariant_rule tests\test_report_ownership.py -q
```

Expected: PASS.

- [ ] **Step 7: Sync installed skill**

Run:

```powershell
python scripts\sync_installed_skill.py --check
```

Expected: PASS. If it fails because `.agents/skills/hsconfig` changed but installed skill is stale, run:

```powershell
python scripts\sync_installed_skill.py
python scripts\sync_installed_skill.py --check
```

Expected after sync: PASS.

- [ ] **Step 8: Commit**

```powershell
git add docs\operator\README.md .agents\skills\hsconfig\SKILL.md .agents\skills\hsconfig\references\workflow.md tests\test_skill_files.py
git commit -m "Document source contract invariant rule"
```

---

### Task 7: Final Verification and Integration

**Files:**
- No planned source modifications.

**Interfaces:**
- Consumes: all previous tasks.
- Produces: verified branch ready for push/merge.

- [ ] **Step 1: Run focused source-contract suite**

Run:

```powershell
python -m pytest tests\test_surface_authority_split.py tests\test_claim_kind_runtime_contract.py tests\test_source_contract_audit.py tests\test_report_ownership.py -q
```

Expected: PASS.

- [ ] **Step 2: Run prepare and representative matrix tests**

Run:

```powershell
python -m pytest tests\test_prepare_cli.py tests\test_universal_wild_no_block_matrix.py tests\test_shadowpriest_e2e.py -q
```

Expected: PASS.

- [ ] **Step 3: Run skill/doc checks**

Run:

```powershell
python -m pytest tests\test_skill_files.py -q
python scripts\sync_installed_skill.py --check
```

Expected: PASS for both commands.

- [ ] **Step 4: Run full test suite**

Run:

```powershell
python -m pytest -q
```

Expected: PASS. If the full suite exceeds the shell timeout, rerun with a longer timeout and record the exact final result.

- [ ] **Step 5: Inspect git state**

Run:

```powershell
git status --short --branch
git log -5 --oneline --decorate
```

Expected:

```text
## <branch>...
```

with only intentional committed changes, or a clean tree if all commits are complete.

- [ ] **Step 6: Push current branch**

If working on `main`, run:

```powershell
git push origin main
```

If working on a feature branch, run:

```powershell
git push -u origin <branch-name>
```

Expected: push succeeds.

---

## Self-Review

- Spec coverage: The plan covers the recommended Source Contract Invariant Closure: explicit claim-kind matrix, real gate parity, diagnostic-only audit, prepare output, docs/skill wording, and final verification.
- Placeholder scan: No placeholder markers or undefined later work remains.
- Type consistency: New interface is `source_contract_policy_by_claim_kind() -> dict[str, dict[str, object]]`; all tasks use that exact name.
- Scope check: The plan does not introduce replay analysis, new dependencies, or a new runtime writer. It only hardens current HSConfig source-contract authority.

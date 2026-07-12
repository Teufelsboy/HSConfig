# HSConfig Contract Spine Lockdown And Explainability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make HSConfig's source-to-runtime contract chain executable, readable, non-blocking, and easy to audit for every valid deck without creating a second apply gate.

**Architecture:** Keep the existing HSConfig pipeline intact: source claims normalize into `claim_kind`, the policy matrix defines semantic lanes, surface gates decide whether claims may lower, builders/routers emit only supported runtime rows, and `reports/operator_summary.json` remains the only normal apply authority. Add missing policy metadata and one compact diagnostic report that explains, per claim and per card, what lowered, what did not lower, why, and what the next source action is. Do not broaden the runtime surface or make source weakness block a load-safe package.

**Tech Stack:** Python 3.11+, pytest, existing `hsconfig` package, existing Markdown docs and skill files. No new dependencies.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig`.
- Do not move work into `C:\Users\darbo\Documents\HS`, temp checkouts, or shadow workspaces.
- `operator_summary.json` remains the only normal runtime-write/apply authority.
- `source_contract_audit.json`, `contract_spine_rows`, `source_to_runtime_explainability.json`, and contract-doctor outputs are diagnostic only.
- A valid deck package must not be blocked by weak source depth, unsupported claims, report-only mechanics, missing guide claims, or runtime-evidence-only tuning.
- Only technical invalidity blocks apply: invalid JSON, missing required runtime files, invalid package hash, invalid fake receipt, unsupported runtime file, or explicit `technical_status != VALID_PACKAGE`.
- Runtime rows may be emitted only through documented HSConfig-supported surfaces: `Mulligan.json`, `GlobalValues.json`, per-card `<CARDID>.json`, and exact `Combo.json`.
- `Presume.json` and `Concede.json` stay outside the normal HSConfig path.
- Runtime Mulligan rows require explicit `mulligan_keep` or `mulligan_discard` claims.
- Start-of-game, deckbuilding, and hero-power-transform effects must remain visible as effect semantics but must not become opening-hand keep rules without separate explicit Mulligan evidence.
- Preserve the Darkbishop Benedictus boundary: hero-power-transform semantics may lower to supported CardID behavior, but Darkbishop itself must not be kept just because the start-of-game effect matters.
- Do not add dependencies.
- Do not commit generated runtime deck outputs or private HearthRanger/HDT evidence.

---

## Current State Summary

The repo already has the important primitives:

- `src/hsconfig/source_document_model.py` defines supported claim kinds and surface gates.
- `src/hsconfig/source_contract_matrix.py` defines the current policy matrix.
- `src/hsconfig/source_contract_conformance.py` builds `contract_spine_rows`.
- `src/hsconfig/source_contract_audit.py` explains claim lifecycle rows for generated packages.
- `src/hsconfig/operator_summary.py` keeps `operator_summary.json` as the operator gate.
- `src/hsconfig/report_ownership.py` defines which report to open first.
- `tests/test_apply_authority_boundary.py` already proves apply paths do not consume source-contract diagnostics.
- `tests/test_source_contract_conformance.py` already proves critical boundaries such as Darkbishop/start-of-game versus Mulligan.

The remaining gap is not another pipeline. The remaining gap is a small, stable "one report" layer and stronger policy metadata:

1. Policy rows should carry the complete contract metadata directly.
2. One package-local report should answer the operator question: "what exact chain exists or is missing for this deck/card/claim?"
3. Docs and tests should make it impossible to confuse that report with apply authority.

---

## File Structure

- Modify `C:\Users\darbo\Documents\HSConfig\src\hsconfig\source_contract_matrix.py`
  - Add explicit policy metadata: `semantic_lane`, `required_fields`, `runtime_lowerable`, `default_suppression_reason`, `operator_gate_impact`.
  - Keep `lane` and `allowed_surfaces` backward-compatible.
- Modify `C:\Users\darbo\Documents\HSConfig\src\hsconfig\source_contract_conformance.py`
  - Thread the new policy metadata into `claim_kind_rows` and `contract_spine_rows`.
  - Keep `operator_gate_impact="diagnostic_only"` for every row.
- Create `C:\Users\darbo\Documents\HSConfig\src\hsconfig\source_to_runtime_explainability.py`
  - Build a compact diagnostic report from existing source contract audit, readiness, and runtime plan outputs.
  - No new source parsing, no runtime writes, no apply decisions.
- Modify `C:\Users\darbo\Documents\HSConfig\src\hsconfig\package_builder.py`
  - Write `reports/source_to_runtime_explainability.json`.
  - Pass the report into `operator_summary` only as a non-blocking summary.
- Modify `C:\Users\darbo\Documents\HSConfig\src\hsconfig\operator_summary.py`
  - Add `source_to_runtime_explainability_summary` with counts and next report pointer.
  - Do not use it in `technical_status`, `runtime_apply_allowed`, `runtime_apply_mode`, `apply_policy`, or `primary_blockers`.
- Modify `C:\Users\darbo\Documents\HSConfig\src\hsconfig\report_ownership.py`
  - Add `reports/source_to_runtime_explainability.json` as diagnostic report order 2.
  - Keep `reports/operator_summary.json` as the only `normal_operator_gate`.
- Modify tests:
  - `C:\Users\darbo\Documents\HSConfig\tests\test_source_contract_conformance.py`
  - `C:\Users\darbo\Documents\HSConfig\tests\test_source_to_runtime_explainability.py`
  - `C:\Users\darbo\Documents\HSConfig\tests\test_prepare_cli.py`
  - `C:\Users\darbo\Documents\HSConfig\tests\test_operator_summary.py`
  - `C:\Users\darbo\Documents\HSConfig\tests\test_report_ownership.py`
  - `C:\Users\darbo\Documents\HSConfig\tests\test_apply_authority_boundary.py`
  - `C:\Users\darbo\Documents\HSConfig\tests\test_shadowpriest_e2e.py`
  - `C:\Users\darbo\Documents\HSConfig\tests\test_skill_files.py`
- Modify docs:
  - `C:\Users\darbo\Documents\HSConfig\docs\operator\README.md`
  - `C:\Users\darbo\Documents\HSConfig\docs\operator\guide-research-policy.md`
  - `C:\Users\darbo\Documents\HSConfig\docs\operator\universal-wild-no-block-contract.md`
  - `C:\Users\darbo\Documents\HSConfig\.agents\skills\hsconfig\SKILL.md`
  - `C:\Users\darbo\Documents\HSConfig\.agents\skills\hsconfig\references\workflow.md`

---

### Task 1: Freeze Full Policy Metadata In The Contract Matrix

**Files:**
- Modify: `src/hsconfig/source_contract_matrix.py`
- Modify: `src/hsconfig/source_contract_conformance.py`
- Modify: `tests/test_source_contract_conformance.py`

**Interfaces:**
- Consumes: `SUPPORTED_ATOMIC_CLAIM_KINDS`.
- Produces: `source_contract_policy_by_claim_kind() -> dict[str, dict[str, object]]` with backward-compatible keys and new explicit contract keys.
- Produces: `build_source_contract_conformance_snapshot()["contract_spine_rows"]` with exact source-to-runtime metadata.

- [ ] **Step 1: Add failing tests for the extended policy schema**

Append this to `tests/test_source_contract_conformance.py`:

```python
def test_source_contract_policy_rows_expose_complete_runtime_contract_metadata():
    from hsconfig.source_contract_matrix import source_contract_policy_by_claim_kind

    policy = source_contract_policy_by_claim_kind()
    required_keys = {
        "lane",
        "semantic_lane",
        "allowed_surfaces",
        "required_fields",
        "runtime_lowerable",
        "default_suppression_reason",
        "operator_meaning",
        "operator_gate_impact",
    }

    assert set(policy) == set(SUPPORTED_ATOMIC_CLAIM_KINDS)
    for claim_kind, row in policy.items():
        assert required_keys <= set(row), claim_kind
        assert row["semantic_lane"] == row["lane"]
        assert row["operator_gate_impact"] == "diagnostic_only"
        assert isinstance(row["required_fields"], tuple), claim_kind
        assert isinstance(row["runtime_lowerable"], bool), claim_kind

    assert policy["mulligan_keep"]["required_fields"] == (
        "claim_kind",
        "claim_readiness",
        "trust_ceiling",
        "cards",
    )
    assert policy["mulligan_keep"]["runtime_lowerable"] is True
    assert policy["hero_power_transform"]["runtime_lowerable"] is True
    assert policy["hero_power_transform"]["default_suppression_reason"] == (
        "requires_supported_cardid_surface"
    )
    assert policy["globalvalue_numeric_tuning"]["runtime_lowerable"] is False
    assert policy["globalvalue_numeric_tuning"]["default_suppression_reason"] == (
        "requires_runtime_evidence"
    )
    assert policy["archetype"]["runtime_lowerable"] is False
    assert policy["archetype"]["default_suppression_reason"] == "report_only"
```

Append this to the same file:

```python
def test_contract_spine_rows_include_policy_metadata_without_apply_authority():
    snapshot = build_source_contract_conformance_snapshot()
    rows_by_kind = {row["claim_kind"]: row for row in snapshot["contract_spine_rows"]}

    required_keys = {
        "claim_kind",
        "policy_lane",
        "semantic_lane",
        "allowed_surfaces",
        "required_fields",
        "runtime_lowerable",
        "surface_gate_status",
        "builder_status",
        "final_runtime_effect",
        "default_suppression_reason",
        "operator_gate_impact",
    }
    forbidden_keys = {
        "apply_allowed",
        "apply_gate",
        "apply_policy",
        "next_action",
        "runtime_apply_allowed",
        "runtime_apply_mode",
        "technical_status",
    }

    for row in rows_by_kind.values():
        assert set(row) == required_keys
        assert forbidden_keys.isdisjoint(row)
        assert row["operator_gate_impact"] == "diagnostic_only"

    assert rows_by_kind["hero_power_transform"]["runtime_lowerable"] is True
    assert rows_by_kind["hero_power_transform"]["default_suppression_reason"] == (
        "requires_supported_cardid_surface"
    )
    assert rows_by_kind["globalvalue_numeric_tuning"]["runtime_lowerable"] is False
    assert rows_by_kind["globalvalue_numeric_tuning"]["final_runtime_effect"] == (
        "suppressed_until_runtime_evidence"
    )
```

- [ ] **Step 2: Run the new tests and confirm failure**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
$env:PYTHONPATH='src'
python -m pytest tests/test_source_contract_conformance.py::test_source_contract_policy_rows_expose_complete_runtime_contract_metadata tests/test_source_contract_conformance.py::test_contract_spine_rows_include_policy_metadata_without_apply_authority -q
```

Expected: FAIL because policy rows and spine rows do not yet expose the new fields.

- [ ] **Step 3: Extend the policy matrix**

In `src/hsconfig/source_contract_matrix.py`, keep `_POLICY` as the single registry and add these fields to every row:

```python
"semantic_lane": str(row["lane"]),
"required_fields": details[0],
"runtime_lowerable": details[1],
"default_suppression_reason": details[2],
"operator_gate_impact": "diagnostic_only",
```

Use these concrete values:

```python
COMMON_CLAIM_FIELDS = ("claim_kind", "claim_readiness", "trust_ceiling")
CARD_CLAIM_FIELDS = (*COMMON_CLAIM_FIELDS, "cards")

MATRIX_DETAILS = {
    "archetype": (COMMON_CLAIM_FIELDS, False, "report_only"),
    "mulligan_keep": (CARD_CLAIM_FIELDS, True, "claim_kind_not_mulligan_surface"),
    "mulligan_discard": (CARD_CLAIM_FIELDS, True, "claim_kind_not_mulligan_surface"),
    "card_role": (CARD_CLAIM_FIELDS, True, "requires_supported_cardid_surface"),
    "targeting_rule": (CARD_CLAIM_FIELDS, True, "requires_supported_cardid_surface"),
    "combo_sequence": ((*CARD_CLAIM_FIELDS, "sequence"), True, "requires_complete_combo_sequence"),
    "gameplan_posture": (COMMON_CLAIM_FIELDS, True, "claim_kind_not_globalvalues_surface"),
    "hero_power_transform": (CARD_CLAIM_FIELDS, True, "requires_supported_cardid_surface"),
    "mechanic_usage": ((*CARD_CLAIM_FIELDS, "mechanic"), True, "requires_supported_cardid_surface"),
    "known_bad_pattern": (CARD_CLAIM_FIELDS, True, "requires_supported_cardid_surface"),
    "tech_slot": (CARD_CLAIM_FIELDS, False, "report_only"),
    "replacement_option": (CARD_CLAIM_FIELDS, False, "report_only"),
    "discover_choice": ((*CARD_CLAIM_FIELDS, "option_card_id"), True, "requires_exact_option_identity"),
    "choose_one_choice": ((*CARD_CLAIM_FIELDS, "option_card_id"), True, "requires_exact_option_identity"),
    "globalvalue_numeric_tuning": ((*COMMON_CLAIM_FIELDS, "key"), False, "requires_runtime_evidence"),
}
```

Implement the values directly in `_POLICY` or through a small local helper. Do not add another registry file.

- [ ] **Step 4: Thread metadata into conformance rows**

In `src/hsconfig/source_contract_conformance.py`:

1. Update `_claim_kind_row(...)` so the returned row includes:

```python
"semantic_lane": str(policy_row.get("semantic_lane", policy_row.get("lane", ""))),
"required_fields": list(policy_row.get("required_fields", ())),
"runtime_lowerable": bool(policy_row.get("runtime_lowerable", False)),
"default_suppression_reason": str(policy_row.get("default_suppression_reason", "")),
"operator_gate_impact": str(policy_row.get("operator_gate_impact", OPERATOR_GATE_IMPACT)),
```

2. Update `_contract_spine_rows(...)` so every spine row includes:

```python
"semantic_lane": str(row.get("semantic_lane", row.get("policy_lane", ""))),
"required_fields": [str(field) for field in row.get("required_fields", [])],
"runtime_lowerable": bool(row.get("runtime_lowerable", False)),
"default_suppression_reason": str(row.get("default_suppression_reason", "")),
```

3. Keep `operator_gate_impact` set to `diagnostic_only` and do not add apply fields.

- [ ] **Step 5: Run the focused tests**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
$env:PYTHONPATH='src'
python -m pytest tests/test_source_contract_conformance.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 1**

```powershell
cd C:\Users\darbo\Documents\HSConfig
git add src/hsconfig/source_contract_matrix.py src/hsconfig/source_contract_conformance.py tests/test_source_contract_conformance.py
git commit -m "feat: expose full source contract policy metadata"
```

---

### Task 2: Add Source-To-Runtime Explainability Report Builder

**Files:**
- Create: `src/hsconfig/source_to_runtime_explainability.py`
- Create: `tests/test_source_to_runtime_explainability.py`

**Interfaces:**
- Consumes: `source_contract_audit_report: Mapping[str, Any]`.
- Produces: `build_source_to_runtime_explainability_report(...) -> dict[str, Any]`.
- Does not consume or write runtime files.
- Does not produce apply permission.

- [ ] **Step 1: Write the failing unit tests**

Create `tests/test_source_to_runtime_explainability.py`:

```python
from __future__ import annotations

from hsconfig.source_to_runtime_explainability import (
    build_source_to_runtime_explainability_report,
)


def _fixture_audit() -> dict:
    return {
        "schema_version": 1,
        "deck_name": "FixtureDeck",
        "summary": {
            "claims_total": 3,
            "runtime_lowered_claims": 1,
            "suppressed_claims": 1,
            "runtime_evidence_required_claims": 1,
            "cards_total": 2,
            "cards_with_missing_links": 1,
        },
        "claim_rows": {
            "keep_claim": {
                "claim_id": "keep_claim",
                "claim_kind": "mulligan_keep",
                "lane": "runtime_lowered",
                "policy_lane": "runtime_lowerable",
                "lowered_surfaces": ["mulligan"],
                "first_reason": "allowed",
                "cards": ["CARD_KEEP"],
            },
            "numeric_claim": {
                "claim_id": "numeric_claim",
                "claim_kind": "globalvalue_numeric_tuning",
                "lane": "runtime_evidence_required",
                "policy_lane": "runtime_evidence_required",
                "lowered_surfaces": [],
                "first_reason": "requires_runtime_evidence",
                "cards": ["CARD_NUM"],
            },
            "unknown_claim": {
                "claim_id": "unknown_claim",
                "claim_kind": "future_claim_kind",
                "lane": "unsupported_or_unmapped",
                "policy_lane": "unsupported_or_unmapped",
                "lowered_surfaces": [],
                "first_reason": "unsupported_or_unmapped",
                "cards": ["CARD_NUM"],
            },
        },
        "claim_lifecycle_rows": [
            {
                "claim_id": "keep_claim",
                "claim_kind": "mulligan_keep",
                "policy_lane": "runtime_lowerable",
                "surface_gate_decision": "allowed",
                "surface_gate_reason": "allowed",
                "builder_or_router_decision": "emitted",
                "runtime_surface": "Mulligan.json",
                "emitted_files": ["Mulligan.json"],
                "suppressed_reason": None,
                "first_missing_link": None,
                "operator_impact": "diagnostic_only",
            },
            {
                "claim_id": "numeric_claim",
                "claim_kind": "globalvalue_numeric_tuning",
                "policy_lane": "runtime_evidence_required",
                "surface_gate_decision": "rejected",
                "surface_gate_reason": "requires_runtime_evidence",
                "builder_or_router_decision": "suppressed",
                "runtime_surface": None,
                "emitted_files": [],
                "suppressed_reason": "runtime_evidence_required",
                "first_missing_link": "runtime_evidence",
                "operator_impact": "diagnostic_only",
            },
            {
                "claim_id": "unknown_claim",
                "claim_kind": "future_claim_kind",
                "policy_lane": "unsupported_or_unmapped",
                "surface_gate_decision": "rejected",
                "surface_gate_reason": "unsupported_or_unmapped",
                "builder_or_router_decision": "suppressed",
                "runtime_surface": None,
                "emitted_files": [],
                "suppressed_reason": "unsupported_or_unmapped",
                "first_missing_link": "claim_kind_policy",
                "operator_impact": "diagnostic_only",
            },
        ],
        "card_rows": {
            "CARD_KEEP": {
                "name": "Keep Card",
                "readiness_lane": "mulligan_only",
                "first_missing_link": "none",
                "runtime_surfaces": ["Mulligan.json"],
                "claim_lanes": {"runtime_lowered": 1},
            },
            "CARD_NUM": {
                "name": "Numeric Card",
                "readiness_lane": "report_only_supported",
                "first_missing_link": "runtime_evidence",
                "runtime_surfaces": [],
                "claim_lanes": {
                    "runtime_evidence_required": 1,
                    "unsupported_or_unmapped": 1,
                },
            },
        },
    }


def test_explainability_report_summarizes_claim_chain_without_apply_authority():
    report = build_source_to_runtime_explainability_report(_fixture_audit())

    assert report["schema_version"] == 1
    assert report["authority"] == "diagnostic_only"
    assert report["operator_gate_impact"] == "diagnostic_only"
    assert report["apply_blocking"] is False
    assert report["summary"] == {
        "cards_total": 2,
        "claims_total": 3,
        "runtime_lowered_claims": 1,
        "claims_with_first_missing_link": 2,
        "cards_with_first_missing_link": 1,
        "apply_blocking": False,
        "next_report_to_open": "reports/source_to_runtime_explainability.json",
    }


def test_explainability_claim_rows_show_first_missing_link_and_runtime_files():
    report = build_source_to_runtime_explainability_report(_fixture_audit())
    rows = {row["claim_id"]: row for row in report["claim_rows"]}

    assert rows["keep_claim"] == {
        "claim_id": "keep_claim",
        "claim_kind": "mulligan_keep",
        "policy_lane": "runtime_lowerable",
        "surface_gate_decision": "allowed",
        "surface_gate_reason": "allowed",
        "builder_or_router_decision": "emitted",
        "emitted_runtime_files": ["Mulligan.json"],
        "not_emitted_runtime_files": [],
        "first_missing_link": None,
        "why_not_emitted": None,
        "apply_blocked": False,
        "next_source_action": "none",
    }
    assert rows["numeric_claim"]["first_missing_link"] == "runtime_evidence"
    assert rows["numeric_claim"]["why_not_emitted"] == "runtime_evidence_required"
    assert rows["numeric_claim"]["next_source_action"] == "collect_runtime_evidence"
    assert rows["unknown_claim"]["first_missing_link"] == "claim_kind_policy"
    assert rows["unknown_claim"]["next_source_action"] == "map_claim_kind_or_keep_report_only"


def test_explainability_card_rows_pick_strongest_claim_and_next_action():
    report = build_source_to_runtime_explainability_report(_fixture_audit())
    rows = {row["card_id"]: row for row in report["card_rows"]}

    assert rows["CARD_KEEP"] == {
        "card_id": "CARD_KEEP",
        "name": "Keep Card",
        "best_source_lane": "runtime_lowered",
        "strongest_claim_id": "keep_claim",
        "strongest_claim_kind": "mulligan_keep",
        "first_missing_link": None,
        "emitted_runtime_files": ["Mulligan.json"],
        "not_emitted_runtime_files": [],
        "why_not_emitted": None,
        "apply_blocked": False,
        "next_source_action": "none",
    }
    assert rows["CARD_NUM"]["best_source_lane"] == "runtime_evidence_required"
    assert rows["CARD_NUM"]["first_missing_link"] == "runtime_evidence"
    assert rows["CARD_NUM"]["why_not_emitted"] == "runtime_evidence_required"
    assert rows["CARD_NUM"]["apply_blocked"] is False
    assert rows["CARD_NUM"]["next_source_action"] == "collect_runtime_evidence"
```

- [ ] **Step 2: Run the new unit tests and confirm failure**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
$env:PYTHONPATH='src'
python -m pytest tests/test_source_to_runtime_explainability.py -q
```

Expected: FAIL because the module does not exist.

- [ ] **Step 3: Implement the report builder**

Create `src/hsconfig/source_to_runtime_explainability.py` with these public functions:

```python
from __future__ import annotations

from typing import Any, Mapping


LANE_RANK = {
    "runtime_lowered": 0,
    "runtime_evidence_required": 1,
    "suppressed_with_reason": 2,
    "unsupported_or_unmapped": 3,
    "report_only": 4,
}


def build_source_to_runtime_explainability_report(
    source_contract_audit_report: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Explain source -> policy -> surface -> builder -> runtime outcome.

    This report is diagnostic-only. It never grants or denies apply permission.
    """
    audit = source_contract_audit_report or {}
    claim_rows = _claim_rows(audit)
    card_rows = _card_rows(audit, claim_rows)
    summary = {
        "cards_total": len(card_rows),
        "claims_total": len(claim_rows),
        "runtime_lowered_claims": sum(
            1 for row in claim_rows if row["builder_or_router_decision"] == "emitted"
        ),
        "claims_with_first_missing_link": sum(
            1 for row in claim_rows if row["first_missing_link"] is not None
        ),
        "cards_with_first_missing_link": sum(
            1 for row in card_rows if row["first_missing_link"] is not None
        ),
        "apply_blocking": False,
        "next_report_to_open": "reports/source_to_runtime_explainability.json",
    }
    return {
        "schema_version": 1,
        "authority": "diagnostic_only",
        "operator_gate_impact": "diagnostic_only",
        "apply_blocking": False,
        "summary": summary,
        "claim_rows": claim_rows,
        "card_rows": card_rows,
    }
```

Add private helpers:

```python
def _claim_rows(audit: Mapping[str, Any]) -> list[dict[str, Any]]:
    lifecycle_rows = audit.get("claim_lifecycle_rows", [])
    if not isinstance(lifecycle_rows, list):
        lifecycle_rows = []
    rows: list[dict[str, Any]] = []
    for row in lifecycle_rows:
        if not isinstance(row, Mapping):
            continue
        emitted_files = [
            str(value)
            for value in row.get("emitted_files", [])
            if str(value).strip()
        ]
        why_not = row.get("suppressed_reason")
        first_missing = row.get("first_missing_link")
        rows.append(
            {
                "claim_id": str(row.get("claim_id", "")),
                "claim_kind": str(row.get("claim_kind", "")),
                "policy_lane": str(row.get("policy_lane", "")),
                "surface_gate_decision": str(row.get("surface_gate_decision", "")),
                "surface_gate_reason": str(row.get("surface_gate_reason", "")),
                "builder_or_router_decision": str(row.get("builder_or_router_decision", "")),
                "emitted_runtime_files": emitted_files,
                "not_emitted_runtime_files": [] if emitted_files else _expected_runtime_files(row),
                "first_missing_link": str(first_missing) if first_missing else None,
                "why_not_emitted": str(why_not) if why_not else None,
                "apply_blocked": False,
                "next_source_action": _next_source_action(first_missing, why_not),
            }
        )
    return rows
```

```python
def _card_rows(audit: Mapping[str, Any], claim_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    audit_card_rows = audit.get("card_rows", {})
    audit_claim_rows = audit.get("claim_rows", {})
    if not isinstance(audit_card_rows, Mapping):
        audit_card_rows = {}
    if not isinstance(audit_claim_rows, Mapping):
        audit_claim_rows = {}
    claim_by_id = {row["claim_id"]: row for row in claim_rows}
    claim_ids_by_card: dict[str, list[str]] = {}
    for claim_id, row in audit_claim_rows.items():
        if not isinstance(row, Mapping):
            continue
        for card_id in row.get("cards", []) or []:
            claim_ids_by_card.setdefault(str(card_id), []).append(str(claim_id))

    rows: list[dict[str, Any]] = []
    for card_id, card in sorted(audit_card_rows.items()):
        if not isinstance(card, Mapping):
            continue
        claim_ids = claim_ids_by_card.get(str(card_id), [])
        strongest_claim = _strongest_claim_for_card(claim_ids, audit_claim_rows, claim_by_id)
        emitted_files = sorted(
            {
                runtime_file
                for claim_id in claim_ids
                for runtime_file in claim_by_id.get(claim_id, {}).get("emitted_runtime_files", [])
            }
        )
        first_missing = _card_first_missing_link(card, strongest_claim)
        why_not = strongest_claim.get("why_not_emitted") if strongest_claim else None
        rows.append(
            {
                "card_id": str(card_id),
                "name": str(card.get("name", "")),
                "best_source_lane": _best_source_lane(claim_ids, audit_claim_rows),
                "strongest_claim_id": strongest_claim.get("claim_id") if strongest_claim else None,
                "strongest_claim_kind": strongest_claim.get("claim_kind") if strongest_claim else None,
                "first_missing_link": first_missing,
                "emitted_runtime_files": emitted_files,
                "not_emitted_runtime_files": [] if emitted_files else _card_expected_runtime_files(str(card_id), strongest_claim),
                "why_not_emitted": why_not,
                "apply_blocked": False,
                "next_source_action": _next_source_action(first_missing, why_not),
            }
        )
    return rows
```

Add the remaining helpers in the same module:

```python
def _expected_runtime_files(row: Mapping[str, Any]) -> list[str]:
    surface = row.get("runtime_surface")
    return [str(surface)] if surface else []


def _card_expected_runtime_files(card_id: str, strongest_claim: Mapping[str, Any] | None) -> list[str]:
    if not strongest_claim:
        return []
    claim_kind = str(strongest_claim.get("claim_kind", ""))
    if claim_kind in {"targeting_rule", "hero_power_transform", "mechanic_usage", "known_bad_pattern", "discover_choice", "choose_one_choice", "card_role"}:
        return [f"{card_id}.json"]
    if claim_kind in {"mulligan_keep", "mulligan_discard"}:
        return ["Mulligan.json"]
    if claim_kind == "combo_sequence":
        return ["Combo.json"]
    if claim_kind == "gameplan_posture":
        return ["GlobalValues.json"]
    return []


def _strongest_claim_for_card(
    claim_ids: list[str],
    audit_claim_rows: Mapping[str, Any],
    claim_by_id: Mapping[str, Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    candidates = []
    for claim_id in claim_ids:
        audit_claim = audit_claim_rows.get(claim_id, {})
        if not isinstance(audit_claim, Mapping):
            continue
        lane = str(audit_claim.get("lane", "report_only"))
        candidates.append((LANE_RANK.get(lane, 99), claim_id, claim_by_id.get(claim_id, {})))
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: (item[0], item[1]))[0][2]


def _best_source_lane(claim_ids: list[str], audit_claim_rows: Mapping[str, Any]) -> str:
    lanes = []
    for claim_id in claim_ids:
        row = audit_claim_rows.get(claim_id, {})
        if isinstance(row, Mapping):
            lanes.append(str(row.get("lane", "report_only")))
    if not lanes:
        return "no_claim"
    return sorted(lanes, key=lambda lane: LANE_RANK.get(lane, 99))[0]


def _card_first_missing_link(card: Mapping[str, Any], strongest_claim: Mapping[str, Any] | None) -> str | None:
    card_link = str(card.get("first_missing_link", ""))
    if card_link and card_link != "none":
        return card_link
    if strongest_claim and strongest_claim.get("first_missing_link"):
        return str(strongest_claim["first_missing_link"])
    return None


def _next_source_action(first_missing_link: Any, why_not_emitted: Any) -> str:
    first_missing = str(first_missing_link or "")
    reason = str(why_not_emitted or "")
    if not first_missing and not reason:
        return "none"
    if first_missing == "runtime_evidence" or reason == "runtime_evidence_required":
        return "collect_runtime_evidence"
    if first_missing == "claim_kind_policy" or reason == "unsupported_or_unmapped":
        return "map_claim_kind_or_keep_report_only"
    if first_missing in {"builder_or_router", "needs_runtime_surface"}:
        return "add_supported_runtime_surface_or_keep_report_only"
    if first_missing == "mulligan_source":
        return "add_explicit_mulligan_claim"
    return "improve_source_claim_or_keep_report_only"
```

- [ ] **Step 4: Run the new unit tests**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
$env:PYTHONPATH='src'
python -m pytest tests/test_source_to_runtime_explainability.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 2**

```powershell
cd C:\Users\darbo\Documents\HSConfig
git add src/hsconfig/source_to_runtime_explainability.py tests/test_source_to_runtime_explainability.py
git commit -m "feat: add source to runtime explainability report"
```

---

### Task 3: Integrate The Explainability Report Into Package Generation

**Files:**
- Modify: `src/hsconfig/package_builder.py`
- Modify: `src/hsconfig/operator_summary.py`
- Modify: `src/hsconfig/report_ownership.py`
- Modify: `tests/test_prepare_cli.py`
- Modify: `tests/test_operator_summary.py`
- Modify: `tests/test_report_ownership.py`

**Interfaces:**
- Consumes: `build_source_to_runtime_explainability_report(source_contract_audit_report)`.
- Produces: `reports/source_to_runtime_explainability.json`.
- Produces: `operator_summary["source_to_runtime_explainability_summary"]`.

- [ ] **Step 1: Write failing package-generation and summary tests**

Append to `tests/test_prepare_cli.py`:

```python
def test_prepare_writes_source_to_runtime_explainability_report(tmp_path):
    result = run_prepare(
        tmp_path,
        deck_name="ShadowPriest",
        deck_code="AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=",
    )

    package = Path(result["package_dir"])
    report_path = package / "reports" / "source_to_runtime_explainability.json"
    assert report_path.exists()

    report = json.loads(report_path.read_text(encoding="utf-8"))
    operator = json.loads(
        (package / "reports" / "operator_summary.json").read_text(encoding="utf-8")
    )

    assert report["authority"] == "diagnostic_only"
    assert report["apply_blocking"] is False
    assert "card_rows" in report
    assert "claim_rows" in report
    assert operator["source_to_runtime_explainability_summary"]["non_blocking"] is True
    assert operator["source_to_runtime_explainability_summary"]["next_report_to_open"] == (
        "reports/source_to_runtime_explainability.json"
    )
```

If `run_prepare` helper in this file uses a different helper name or return shape, adapt only the helper call to the local pattern. Keep the assertions identical.

Append to `tests/test_operator_summary.py`:

```python
def test_operator_summary_threads_explainability_without_gating_apply():
    summary = build_operator_summary(
        validation_report={"technical_status": "VALID_PACKAGE", "errors": []},
        source_to_runtime_explainability_report={
            "summary": {
                "cards_total": 2,
                "claims_total": 3,
                "runtime_lowered_claims": 1,
                "claims_with_first_missing_link": 2,
                "cards_with_first_missing_link": 1,
                "apply_blocking": False,
                "next_report_to_open": "reports/source_to_runtime_explainability.json",
            }
        },
    )

    assert summary["technical_status"] == "VALID_PACKAGE"
    assert summary["runtime_apply_allowed"] is True
    assert summary["source_to_runtime_explainability_summary"] == {
        "non_blocking": True,
        "cards_total": 2,
        "claims_total": 3,
        "runtime_lowered_claims": 1,
        "claims_with_first_missing_link": 2,
        "cards_with_first_missing_link": 1,
        "next_report_to_open": "reports/source_to_runtime_explainability.json",
    }
```

Append to `tests/test_report_ownership.py`:

```python
def test_report_ownership_includes_source_to_runtime_explainability_as_diagnostic():
    rows = build_report_ownership()
    by_file = {row["file"]: row for row in rows}

    assert by_file["reports/operator_summary.json"]["authority"] == "normal_operator_gate"
    assert by_file["reports/operator_summary.json"]["open_order"] == "1"
    assert by_file["reports/source_to_runtime_explainability.json"]["authority"] == (
        "diagnostic_source_to_runtime_chain"
    )
    assert by_file["reports/source_to_runtime_explainability.json"]["open_order"] == "2"
    assert "does not grant apply permission" in by_file[
        "reports/source_to_runtime_explainability.json"
    ]["notes"]
    assert [
        row for row in rows if row.get("authority") == "normal_operator_gate"
    ] == [by_file["reports/operator_summary.json"]]
```

- [ ] **Step 2: Run the focused tests and confirm failure**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
$env:PYTHONPATH='src'
python -m pytest tests/test_source_to_runtime_explainability.py tests/test_operator_summary.py::test_operator_summary_threads_explainability_without_gating_apply tests/test_report_ownership.py::test_report_ownership_includes_source_to_runtime_explainability_as_diagnostic -q
```

Expected: FAIL on missing operator summary parameter and report ownership entry.

- [ ] **Step 3: Write the report in `package_builder.py`**

In `src/hsconfig/package_builder.py`:

1. Import the builder:

```python
from hsconfig.source_to_runtime_explainability import (
    build_source_to_runtime_explainability_report,
)
```

2. Immediately after `source_contract_audit_report` is written, build and write the explainability report:

```python
source_to_runtime_explainability_report = build_source_to_runtime_explainability_report(
    source_contract_audit_report
)
write_json(
    reports_dir / "source_to_runtime_explainability.json",
    source_to_runtime_explainability_report,
)
```

3. Add the report into `operator_summary_kwargs`:

```python
"source_to_runtime_explainability_report": source_to_runtime_explainability_report,
```

4. Add the file to `_generated_package_files(...)`:

```python
reports_dir / "source_to_runtime_explainability.json",
```

- [ ] **Step 4: Add non-blocking operator summary**

In `src/hsconfig/operator_summary.py`:

1. Add optional parameter to `build_operator_summary(...)`:

```python
source_to_runtime_explainability_report: dict[str, Any] | None = None,
```

2. Compute:

```python
source_to_runtime_explainability_summary = _source_to_runtime_explainability_summary(
    source_to_runtime_explainability_report
)
```

3. Add to returned summary:

```python
"source_to_runtime_explainability_summary": source_to_runtime_explainability_summary,
```

4. Add helper:

```python
def _source_to_runtime_explainability_summary(report: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(report, dict):
        return {
            "non_blocking": True,
            "cards_total": 0,
            "claims_total": 0,
            "runtime_lowered_claims": 0,
            "claims_with_first_missing_link": 0,
            "cards_with_first_missing_link": 0,
            "next_report_to_open": None,
        }
    summary = report.get("summary", {})
    if not isinstance(summary, dict):
        summary = {}
    return {
        "non_blocking": True,
        "cards_total": _int_value(summary.get("cards_total", 0)),
        "claims_total": _int_value(summary.get("claims_total", 0)),
        "runtime_lowered_claims": _int_value(summary.get("runtime_lowered_claims", 0)),
        "claims_with_first_missing_link": _int_value(
            summary.get("claims_with_first_missing_link", 0)
        ),
        "cards_with_first_missing_link": _int_value(
            summary.get("cards_with_first_missing_link", 0)
        ),
        "next_report_to_open": summary.get("next_report_to_open")
        or "reports/source_to_runtime_explainability.json",
    }
```

Do not reference this summary from `_technical_status`, `_primary_blockers`, `_next_action_and_policy`, or `_runtime_apply_contract`.

- [ ] **Step 5: Update report ownership**

In `src/hsconfig/report_ownership.py`:

1. Insert this row immediately after `reports/operator_summary.json`:

```python
{
    "file": "reports/source_to_runtime_explainability.json",
    "authority": "diagnostic_source_to_runtime_chain",
    "answers": "which exact source-to-runtime link exists or is missing per card and claim",
    "contains": (
        "best source lane, strongest claim, emitted runtime files, first missing link, "
        "why not emitted, next source action"
    ),
    "notes": (
        "diagnostic only; does not grant apply permission; "
        "does not replace operator_summary.json"
    ),
    "open_order": "2",
},
```

2. Increment existing diagnostic open orders by one so source contract audit becomes `"3"`, source claim gap becomes `"4"`, and so on.

- [ ] **Step 6: Run integration tests**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
$env:PYTHONPATH='src'
python -m pytest tests/test_source_to_runtime_explainability.py tests/test_operator_summary.py tests/test_report_ownership.py tests/test_prepare_cli.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit Task 3**

```powershell
cd C:\Users\darbo\Documents\HSConfig
git add src/hsconfig/package_builder.py src/hsconfig/operator_summary.py src/hsconfig/report_ownership.py tests/test_prepare_cli.py tests/test_operator_summary.py tests/test_report_ownership.py
git commit -m "feat: integrate source to runtime explainability report"
```

---

### Task 4: Lock The Darkbishop / Start-Of-Game Mulligan Boundary In The New Report

**Files:**
- Modify: `tests/test_shadowpriest_e2e.py`
- Modify if needed: `src/hsconfig/source_to_runtime_explainability.py`

**Interfaces:**
- Consumes: generated ShadowPriest package reports.
- Produces: proof that Darkbishop Benedictus effect semantics remain visible while the card is not treated as a Mulligan keep just because the effect matters.

- [ ] **Step 1: Add the E2E assertion**

Append to `tests/test_shadowpriest_e2e.py` or extend the existing Darkbishop test:

```python
def test_shadowpriest_explainability_keeps_darkbishop_effect_not_mulligan_keep(tmp_path):
    result = run_prepare(
        tmp_path,
        deck_name="ShadowPriest",
        deck_code="AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=",
    )
    package = Path(result["package_dir"])
    mulligan = json.loads((package / "CustomConfig" / "ShadowPriest" / "Mulligan.json").read_text(encoding="utf-8"))
    explainability = json.loads(
        (package / "reports" / "source_to_runtime_explainability.json").read_text(
            encoding="utf-8"
        )
    )

    darkbishop_card_rows = [
        row for row in explainability["card_rows"] if row["card_id"] == "SW_448"
    ]
    assert darkbishop_card_rows
    assert darkbishop_card_rows[0]["apply_blocked"] is False

    mulligan_text = json.dumps(mulligan)
    assert "SW_448" not in mulligan_text

    darkbishop_claim_rows = [
        row
        for row in explainability["claim_rows"]
        if row["claim_kind"] in {"hero_power_transform", "mulligan_keep"}
        and ("SW_448.json" in row["emitted_runtime_files"] or row["why_not_emitted"])
    ]
    assert darkbishop_claim_rows
    assert any(
        row["claim_kind"] == "hero_power_transform"
        and "SW_448.json" in row["emitted_runtime_files"]
        for row in darkbishop_claim_rows
    )
    assert all(
        row["claim_kind"] != "mulligan_keep"
        or row["why_not_emitted"] == "start_of_game_effect_does_not_require_opening_hand"
        for row in darkbishop_claim_rows
    )
```

If this file uses a different prepare helper, adapt only the helper call. Keep the assertions and package-path checks.

- [ ] **Step 2: Run the focused E2E test**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
$env:PYTHONPATH='src'
python -m pytest tests/test_shadowpriest_e2e.py::test_shadowpriest_explainability_keeps_darkbishop_effect_not_mulligan_keep -q
```

Expected before implementation: fail only if report rows do not preserve the relevant card/claim mapping.

- [ ] **Step 3: Patch explainability only if the mapping is missing**

If the test fails because `claim_lifecycle_rows` do not include card IDs, update `build_source_to_runtime_explainability_report(...)` to accept the full audit `claim_rows` map and assign card IDs by `audit["claim_rows"][claim_id]["cards"]`. Do not infer Darkbishop behavior from card name text.

The helper already planned in Task 2 must be the only place that maps claims to cards:

```python
for claim_id, row in audit_claim_rows.items():
    if not isinstance(row, Mapping):
        continue
    for card_id in row.get("cards", []) or []:
        claim_ids_by_card.setdefault(str(card_id), []).append(str(claim_id))
```

- [ ] **Step 4: Run ShadowPriest and source tests**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
$env:PYTHONPATH='src'
python -m pytest tests/test_shadowpriest_e2e.py tests/test_source_to_runtime_explainability.py tests/test_source_contract_audit.py tests/test_source_contract_conformance.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 4**

```powershell
cd C:\Users\darbo\Documents\HSConfig
git add src/hsconfig/source_to_runtime_explainability.py tests/test_shadowpriest_e2e.py
git commit -m "test: prove darkbishop effect boundary in explainability"
```

---

### Task 5: Prove No Second Gate And Update Operator Docs

**Files:**
- Modify: `tests/test_apply_authority_boundary.py`
- Modify: `tests/test_skill_files.py`
- Modify: `docs/operator/README.md`
- Modify: `docs/operator/guide-research-policy.md`
- Modify: `docs/operator/universal-wild-no-block-contract.md`
- Modify: `.agents/skills/hsconfig/SKILL.md`
- Modify: `.agents/skills/hsconfig/references/workflow.md`

**Interfaces:**
- Consumes: report names and authority text.
- Produces: explicit docs and tests that the new report is diagnostic only.

- [ ] **Step 1: Extend apply-authority boundary tests**

In `tests/test_apply_authority_boundary.py`, add `"source_to_runtime_explainability"` to `DIAGNOSTIC_ONLY_TOKENS`:

```python
DIAGNOSTIC_ONLY_TOKENS = [
    "source_contract_audit",
    "contract_spine_rows",
    "claim_lifecycle_rows",
    "source_contract_conformance",
    "source_to_runtime_explainability",
]
```

Add this import token to `FORBIDDEN_DIAGNOSTIC_IMPORTS`:

```python
"from hsconfig.source_to_runtime_explainability",
"import hsconfig.source_to_runtime_explainability",
```

- [ ] **Step 2: Add skill/docs wording tests**

Append to `tests/test_skill_files.py`:

```python
def test_skill_and_operator_docs_explain_source_to_runtime_explainability_boundary():
    paths = [
        Path(".agents/skills/hsconfig/SKILL.md"),
        Path(".agents/skills/hsconfig/references/workflow.md"),
        Path("docs/operator/README.md"),
        Path("docs/operator/guide-research-policy.md"),
        Path("docs/operator/universal-wild-no-block-contract.md"),
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in paths)

    assert "reports/source_to_runtime_explainability.json" in combined
    assert "diagnostic only" in combined
    assert "operator_summary.json remains the only normal" in combined
    assert "source weakness is visible but non-blocking" in combined
    assert "Darkbishop Benedictus" in combined
    assert "does not become an opening-hand keep" in combined
```

- [ ] **Step 3: Run the docs/boundary tests and confirm failure**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
$env:PYTHONPATH='src'
python -m pytest tests/test_apply_authority_boundary.py tests/test_skill_files.py::test_skill_and_operator_docs_explain_source_to_runtime_explainability_boundary -q
```

Expected: FAIL until docs and boundary lists are updated.

- [ ] **Step 4: Update docs and skill text**

Use this exact policy paragraph in all five docs/skill files listed in Step 2, placing it near existing source-contract guidance:

```markdown
`reports/source_to_runtime_explainability.json` is diagnostic only. It shows the compact source -> policy -> surface gate -> builder/router -> runtime file chain for each card and claim, including the first missing link and the next source action. It does not grant apply permission and does not replace `reports/operator_summary.json`; `operator_summary.json` remains the only normal runtime-write/apply authority. Source weakness is visible but non-blocking for technically valid load-safe packages. Darkbishop Benedictus keeps its hero-power-transform effect semantics visible, but that effect does not become an opening-hand keep without separate explicit Mulligan evidence.
```

Do not add long workflow prose. Do not add another command path.

- [ ] **Step 5: Run docs/boundary tests**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
$env:PYTHONPATH='src'
python -m pytest tests/test_apply_authority_boundary.py tests/test_skill_files.py tests/test_operator_docs_contract_policy.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 5**

```powershell
cd C:\Users\darbo\Documents\HSConfig
git add tests/test_apply_authority_boundary.py tests/test_skill_files.py docs/operator/README.md docs/operator/guide-research-policy.md docs/operator/universal-wild-no-block-contract.md .agents/skills/hsconfig/SKILL.md .agents/skills/hsconfig/references/workflow.md
git commit -m "docs: explain source runtime diagnostics boundary"
```

---

### Task 6: Final Verification And Repo Hygiene

**Files:**
- No planned source modifications.
- Use only test commands and git inspection.

**Interfaces:**
- Consumes: all previous task commits.
- Produces: verified branch ready to push or merge.

- [ ] **Step 1: Run targeted contract tests**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
$env:PYTHONPATH='src'
python -m pytest tests/test_source_contract_conformance.py tests/test_source_contract_audit.py tests/test_source_to_runtime_explainability.py tests/test_operator_summary.py tests/test_report_ownership.py tests/test_apply_authority_boundary.py -q
```

Expected: PASS.

- [ ] **Step 2: Run E2E/operator tests**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
$env:PYTHONPATH='src'
python -m pytest tests/test_shadowpriest_e2e.py tests/test_prepare_cli.py tests/test_full_chain_cli_integration.py tests/test_skill_files.py tests/test_docs_active_path.py -q
```

Expected: PASS.

- [ ] **Step 3: Run the full suite**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
$env:PYTHONPATH='src'
python -m pytest -q
```

Expected: PASS.

- [ ] **Step 4: Run static scans for authority drift**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
rg -n "source_to_runtime_explainability|source_contract_audit|contract_spine_rows" src/hsconfig/apply_gate.py src/hsconfig/runtime_apply.py src/hsconfig/commands/apply.py
```

Expected: no output.

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
rg -n "operator_summary.json remains the only normal|source weakness is visible but non-blocking|reports/source_to_runtime_explainability.json" docs/operator .agents/skills/hsconfig
```

Expected: output in active operator docs and skill files.

- [ ] **Step 5: Review diff and generated files**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
git status --short --branch
git diff --check
git diff --stat HEAD
```

Expected:

- Branch is clean except intentional tracked changes before the final commit.
- `git diff --check` prints no whitespace errors.
- No generated deck packages, runtime outputs, or private logs are staged.

- [ ] **Step 6: Commit final verification notes only if files changed**

If Task 6 required small docs/test fixes, commit them:

```powershell
cd C:\Users\darbo\Documents\HSConfig
git add src/hsconfig/source_contract_matrix.py src/hsconfig/source_contract_conformance.py src/hsconfig/source_to_runtime_explainability.py src/hsconfig/package_builder.py src/hsconfig/operator_summary.py src/hsconfig/report_ownership.py tests/test_source_contract_conformance.py tests/test_source_to_runtime_explainability.py tests/test_prepare_cli.py tests/test_operator_summary.py tests/test_report_ownership.py tests/test_apply_authority_boundary.py tests/test_shadowpriest_e2e.py tests/test_skill_files.py docs/operator/README.md docs/operator/guide-research-policy.md docs/operator/universal-wild-no-block-contract.md .agents/skills/hsconfig/SKILL.md .agents/skills/hsconfig/references/workflow.md
git commit -m "test: verify source runtime explainability boundary"
```

If no files changed, do not create an empty commit.

---

## Self-Review

### Spec Coverage

- Source-/contract logic becomes stricter through explicit policy metadata in `source_contract_matrix.py`.
- The implementation remains narrow: one diagnostic report, no new pipeline, no new dependency, no new runtime surface.
- The system remains autonomous and no-block: valid decks still produce load-safe packages even with weak or unsupported source claims.
- Darkbishop Benedictus is covered explicitly: effect semantics visible, no false Mulligan keep.
- The one authority boundary is preserved: `operator_summary.json` remains the only apply authority.

### Placeholder Scan

This plan contains no placeholder work items and no unnamed generic error-handling buckets. Every task names files, functions, tests, commands, and expected outcomes.

### Type Consistency

The plan consistently uses:

- `source_contract_policy_by_claim_kind() -> dict[str, dict[str, object]]`
- `build_source_contract_conformance_snapshot() -> dict[str, Any]`
- `build_source_to_runtime_explainability_report(source_contract_audit_report) -> dict[str, Any]`
- `operator_summary["source_to_runtime_explainability_summary"]`
- `reports/source_to_runtime_explainability.json`

### Risk Notes

- Some local helper names in `tests/test_prepare_cli.py` and `tests/test_shadowpriest_e2e.py` may differ from the examples. When executing, adapt only the helper call to the existing local pattern and keep the report/assertion contract unchanged.
- If existing `operator_summary.build_operator_summary(...)` has many positional arguments, add the new parameter as keyword-only optional at the end to avoid breaking existing tests.
- Do not make explainability "more authoritative" because it is easier to read. It is intentionally diagnostic.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-13-hsconfig-contract-spine-lockdown-explainability.md`.

Two execution options:

1. **Subagent-Driven (recommended)** - dispatch a fresh subagent per task, review between tasks, fastest safe iteration.
2. **Inline Execution** - execute tasks in this session with checkpoint reviews.

Recommended choice: **Subagent-Driven**, because Tasks 1-5 are separable and each has its own focused test boundary.

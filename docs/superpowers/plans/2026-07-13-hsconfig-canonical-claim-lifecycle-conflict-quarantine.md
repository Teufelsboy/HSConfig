# HSConfig Canonical Claim Lifecycle & Conflict Quarantine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build one canonical Source -> Claim Lifecycle -> Surface Gate -> Builder/Router -> Runtime Effect chain so HSConfig stays aggressive for valid decks while preventing false runtime lowering.

**Architecture:** Create a single source-claim lifecycle module that normalizes claims once, applies conflict quarantine before builders run, and exposes filtered runtime-eligible claim views per VisionAI surface. Keep `operator_summary.json` as the only normal apply authority; diagnostics such as `source_contract_audit.json`, explainability, conflict reports, ownership manifests, and sentinels remain read-only projections.

**Tech Stack:** Python 3, existing `hsconfig` package, pytest, existing HearthRanger VisionAI JSON surface validators, existing `docs/research/2026-07-13-hsconfig-source-contract-logic-brainstorm-v6` evidence package.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig`.
- Do not add a second runtime apply gate. `reports/operator_summary.json` remains the only normal apply authority.
- Do not block load-safe valid decks because source evidence is thin, unknown, stale, future-mechanic, report-only, or unresolved.
- Do not put `Presume.json` or `Concede.json` into the normal package output path.
- Do not infer `mulligan_keep` from card importance, free-text "keep" wording, start-of-game effects, deckbuilding effects, or hero-power transforms.
- Preserve Darkbishop Benedictus / `SW_448` as effect-visible `hero_power_transform` CardID behavior while keeping it out of `Mulligan.json` unless a separate opening-hand source explicitly claims `mulligan_keep`.
- `GlobalValues.json` numeric tuning from runtime evidence remains outside static Step 1 lowering; static guide posture may remain visible or posture-lowerable only through existing allowed lanes.
- Keep unknown mechanics visible and non-blocking; suppress unsafe runtime rows instead of inventing VisionAI behavior.
- Use TDD: each task starts with a failing test and ends with targeted passing tests.
- Frequent commits: one commit per task after tests pass.

---

## File Structure

- Create `src/hsconfig/source_claim_lifecycle.py`
  - Owns canonical claim lifecycle rows.
  - Migrates legacy `claim_type` aliases to stored `claim_kind` once.
  - Adds source authority, freshness, trust ceiling, semantic qualifiers, conflict quarantine, surface gate outcome, builder status, and final runtime effect fields.
  - Exposes `runtime_claims_for_surface()` so builders receive only non-quarantined, non-report-only, surface-eligible claims.
- Modify `src/hsconfig/package_builder.py`
  - Builds the conflict report and initial lifecycle before runtime builders.
  - Passes filtered claim lists to `build_mulligan_plan()`, `build_combo_plan()`, `build_globalvalues_authority_matrix()`, and `route_card_behavior_surfaces()`.
  - Passes lifecycle rows into source contract audit so diagnostics derive from the same chain.
- Modify `src/hsconfig/source_contract_audit.py`
  - Accepts canonical lifecycle rows and overlays builder/router outcomes instead of recomputing lifecycle authority from raw claims.
  - Preserves output schema keys consumed by existing reports and tests.
- Modify `src/hsconfig/source_document_model.py`
  - Keeps legacy alias migration helper available only for lifecycle ingestion.
  - Adds a strict helper used by surface gates after lifecycle ingestion.
- Modify `src/hsconfig/source_contract_conformance.py` and `src/hsconfig/contract_spine_sentinel.py`
  - Verifies the lifecycle module is the single contract-spine source for runtime eligibility.
  - Keeps sentinel diagnostic-only.
- Modify docs:
  - `docs/operator/guide-research-policy.md`
  - `.agents/skills/hsconfig/SKILL.md`
  - Optionally `docs/superpowers/plans/README.md` if the plan index needs a pointer.
- Tests:
  - Create `tests/test_source_claim_lifecycle.py`.
  - Extend `tests/test_source_claim_conflicts.py`.
  - Extend `tests/test_source_contract_audit.py`.
  - Extend `tests/test_source_to_runtime_explainability.py` only if the report projection changes.
  - Extend `tests/test_contract_spine_sentinel.py`.
  - Extend `tests/test_universal_wild_no_block_matrix.py`.
  - Extend `tests/test_shadowpriest_e2e.py`.

---

### Task 1: Canonical Lifecycle Model And Ingestion Normalization

**Files:**
- Create: `src/hsconfig/source_claim_lifecycle.py`
- Modify: `src/hsconfig/source_document_model.py`
- Test: `tests/test_source_claim_lifecycle.py`

**Interfaces:**
- Consumes: raw source claims as `Sequence[Mapping[str, Any]]`.
- Produces:
  - `build_initial_lifecycle_rows(claims: Sequence[Mapping[str, Any]], *, conflict_report: Mapping[str, Any] | None = None) -> list[dict[str, Any]]`
  - `runtime_claims_for_surface(rows: Sequence[Mapping[str, Any]], surface: str) -> list[dict[str, Any]]`
  - `strict_claim_kind(claim_or_row: Mapping[str, Any]) -> str`

- [ ] **Step 1: Write failing lifecycle tests**

Add `tests/test_source_claim_lifecycle.py`:

```python
from hsconfig.source_claim_lifecycle import (
    build_initial_lifecycle_rows,
    runtime_claims_for_surface,
)
from hsconfig.source_document_model import strict_claim_kind


def test_lifecycle_migrates_legacy_claim_type_once_and_stores_claim_kind():
    rows = build_initial_lifecycle_rows(
        [
            {
                "claim_id": "legacy_combo",
                "claim_type": "combo",
                "cards": ["CARD_001", "CARD_002"],
                "combo": "CARD_001 >> CARD_002",
                "value": "20 >> 20",
                "source_confidence": "guide_backed",
            }
        ]
    )

    assert rows[0]["claim_id"] == "legacy_combo"
    assert rows[0]["claim_kind"] == "combo_sequence"
    assert rows[0]["legacy_claim_type"] == "combo"
    assert rows[0]["migration_status"] == "legacy_claim_type_migrated"
    assert "claim_type" not in runtime_claims_for_surface(rows, "combo")[0]


def test_strict_claim_kind_requires_stored_modern_claim_kind_after_ingestion():
    assert strict_claim_kind({"claim_kind": "mulligan_keep"}) == "mulligan_keep"
    assert strict_claim_kind({"claim_type": "mulligan"}) == ""


def test_runtime_claims_for_surface_excludes_quarantined_report_only_claims():
    rows = build_initial_lifecycle_rows(
        [
            {
                "claim_id": "keep_1",
                "claim_kind": "mulligan_keep",
                "card_id": "CARD_001",
                "source_confidence": "guide_backed",
            },
            {
                "claim_id": "keep_2",
                "claim_kind": "mulligan_keep",
                "card_id": "CARD_002",
                "source_confidence": "guide_backed",
            },
            {
                "claim_id": "role_1",
                "claim_kind": "card_role",
                "card_id": "CARD_003",
                "source_confidence": "report_only",
            },
        ],
        conflict_report={
            "conflicts": [
                {
                    "claim_ids": ["keep_2"],
                    "reason": "contradictory_mulligan_keep_discard",
                }
            ]
        },
    )

    runtime_claims = runtime_claims_for_surface(rows, "mulligan")
    assert [claim["claim_id"] for claim in runtime_claims] == ["keep_1"]
    by_id = {row["claim_id"]: row for row in rows}
    assert by_id["keep_2"]["quarantine_status"] == "quarantined"
    assert by_id["role_1"]["runtime_eligibility"] == "report_only"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest -q tests/test_source_claim_lifecycle.py
```

Expected: FAIL because `hsconfig.source_claim_lifecycle` and `strict_claim_kind` do not exist.

- [ ] **Step 3: Implement minimal lifecycle module**

Create `src/hsconfig/source_claim_lifecycle.py`:

```python
from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any

from hsconfig.source_contract_matrix import source_contract_policy_by_claim_kind
from hsconfig.source_document_model import normalized_claim_kind, surface_gate_decision


def build_initial_lifecycle_rows(
    claims: Sequence[Mapping[str, Any]],
    *,
    conflict_report: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    quarantined = _quarantined_claim_ids(conflict_report or {})
    rows: list[dict[str, Any]] = []
    for index, claim in enumerate(claims, start=1):
        original = dict(claim)
        claim_kind = normalized_claim_kind(original)
        migrated_claim = deepcopy(original)
        legacy_claim_type = migrated_claim.pop("claim_type", None)
        if claim_kind:
            migrated_claim["claim_kind"] = claim_kind
        claim_id = str(migrated_claim.get("claim_id") or f"claim_{index}")
        policy = source_contract_policy_by_claim_kind().get(claim_kind, {})
        source_confidence = str(migrated_claim.get("source_confidence") or migrated_claim.get("confidence") or "unknown")
        quarantine_reason = quarantined.get(claim_id)
        row = {
            "claim_id": claim_id,
            "claim_kind": claim_kind,
            "legacy_claim_type": legacy_claim_type,
            "migration_status": (
                "legacy_claim_type_migrated" if legacy_claim_type and claim_kind else "modern_claim_kind"
            ),
            "source_confidence": source_confidence,
            "policy_lane": policy.get("lane", "unknown"),
            "allowed_surfaces": list(policy.get("allowed_surfaces", ())),
            "semantic_qualifiers": migrated_claim.get("semantic_qualifiers", {}),
            "quarantine_status": "quarantined" if quarantine_reason else "clear",
            "quarantine_reason": quarantine_reason or "",
            "runtime_eligibility": _runtime_eligibility(source_confidence, quarantine_reason),
            "claim": migrated_claim,
        }
        rows.append(row)
    return rows


def runtime_claims_for_surface(
    rows: Sequence[Mapping[str, Any]],
    surface: str,
) -> list[dict[str, Any]]:
    runtime_claims: list[dict[str, Any]] = []
    for row in rows:
        if row.get("quarantine_status") == "quarantined":
            continue
        if row.get("runtime_eligibility") == "report_only":
            continue
        claim = dict(row.get("claim") or {})
        claim_kind = str(row.get("claim_kind") or "")
        if not claim_kind:
            continue
        decision = surface_gate_decision(claim, surface)
        if not decision.allowed:
            continue
        claim["claim_kind"] = claim_kind
        claim["_claim_lifecycle"] = {
            "claim_id": row.get("claim_id"),
            "surface": surface,
            "policy_lane": row.get("policy_lane"),
            "surface_gate_reason": decision.reason,
        }
        runtime_claims.append(claim)
    return runtime_claims


def _runtime_eligibility(source_confidence: str, quarantine_reason: str | None) -> str:
    if quarantine_reason:
        return "quarantined"
    if source_confidence in {"report_only", "unsupported", "unknown_future_mechanic"}:
        return "report_only"
    return "runtime_candidate"


def _quarantined_claim_ids(conflict_report: Mapping[str, Any]) -> dict[str, str]:
    quarantined: dict[str, str] = {}
    for conflict in conflict_report.get("conflicts", []) or []:
        reason = str(conflict.get("reason") or "source_claim_conflict")
        for claim_id in conflict.get("claim_ids", []) or []:
            quarantined[str(claim_id)] = reason
    return quarantined
```

Modify `src/hsconfig/source_document_model.py`:

```python
def strict_claim_kind(claim: Mapping[str, Any]) -> str:
    """Return the stored modern claim kind after lifecycle ingestion."""
    value = claim.get("claim_kind")
    if isinstance(value, str) and value in SUPPORTED_ATOMIC_CLAIM_KINDS:
        return value
    return ""
```

- [ ] **Step 4: Run lifecycle tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest -q tests/test_source_claim_lifecycle.py tests/test_surface_authority_split.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/hsconfig/source_claim_lifecycle.py src/hsconfig/source_document_model.py tests/test_source_claim_lifecycle.py
git commit -m "feat: add canonical source claim lifecycle"
```

---

### Task 2: Conflict Quarantine Before Runtime Builders

**Files:**
- Modify: `src/hsconfig/package_builder.py`
- Modify: `src/hsconfig/source_claim_conflicts.py` only if existing report rows lack stable `claim_ids`
- Test: `tests/test_source_claim_conflicts.py`
- Test: `tests/test_shadowpriest_e2e.py`

**Interfaces:**
- Consumes: `build_initial_lifecycle_rows()` and `runtime_claims_for_surface()`.
- Produces: runtime builders receive only lifecycle-filtered claims.

- [ ] **Step 1: Write failing package-level conflict test**

Add to `tests/test_source_claim_conflicts.py`:

```python
import json
from pathlib import Path

from hsconfig.cli import main


def test_conflicted_mulligan_claim_is_visible_but_not_lowered(tmp_path: Path):
    out = tmp_path / "pkg"
    cards_json = tmp_path / "cards.json"
    cards_json.write_text(
        json.dumps(
            {
                "cards": [
                    {
                        "card_id": "CARD_001",
                        "dbf_id": 1,
                        "count": 1,
                        "name": "Conflict Card",
                        "cost": 1,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    guide_sources_json = tmp_path / "guide_sources.json"
    guide_sources_json.write_text(
        json.dumps(
            [
                {
                    "source_url": "https://example.invalid/conflict",
                    "source_title": "Conflict Fixture",
                    "source_family": "guide_fixture",
                    "retrieved_at": "2026-07-13T00:00:00Z",
                    "claims": [
                        {
                            "claim_id": "keep_card",
                            "claim_kind": "mulligan_keep",
                            "cards": ["CARD_001"],
                            "source_confidence": "guide_backed",
                        },
                        {
                            "claim_id": "discard_card",
                            "claim_kind": "mulligan_discard",
                            "cards": ["CARD_001"],
                            "source_confidence": "guide_backed",
                        },
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )

    code = main(
        [
            "prepare",
            "--deck-name",
            "ConflictDeck",
            "--deck-code",
            "fixture-code",
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(out),
            "--cards-json",
            str(cards_json),
            "--guide-sources-json",
            str(guide_sources_json),
        ]
    )

    deck_dir = next((out / "CustomConfig").iterdir())
    mulligan = (deck_dir / "Mulligan.json").read_text(encoding="utf-8")
    audit = (out / "reports" / "source_contract_audit.json").read_text(encoding="utf-8")
    assert code == 0
    assert "CARD_001" not in mulligan
    assert "quarantined" in audit
    assert "mulligan" in audit
```

- [ ] **Step 2: Run conflict test to verify it fails**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest -q tests/test_source_claim_conflicts.py::test_conflicted_mulligan_claim_is_visible_but_not_lowered
```

Expected: FAIL because package builder still passes raw conflicting claims to builders.

- [ ] **Step 3: Wire lifecycle filtering into package builder**

In `src/hsconfig/package_builder.py`, add imports:

```python
from hsconfig.source_claim_lifecycle import (
    build_initial_lifecycle_rows,
    runtime_claims_for_surface,
)
```

After the existing claim-conflict report is built and before runtime builders run, add:

```python
initial_lifecycle_rows = build_initial_lifecycle_rows(
    claims,
    conflict_report=source_claim_conflict_report,
)
mulligan_claims = runtime_claims_for_surface(initial_lifecycle_rows, "mulligan")
combo_claims = runtime_claims_for_surface(initial_lifecycle_rows, "combo")
globalvalues_claims = runtime_claims_for_surface(initial_lifecycle_rows, "globalvalues")
cardid_claims = runtime_claims_for_surface(initial_lifecycle_rows, "cardid")
```

Replace builder inputs:

```python
mulligan_plan = build_mulligan_plan(
    deck_name=deck_name,
    claims=mulligan_claims,
    card_roles=card_roles,
)
combo_plan = build_combo_plan(deck_cards=deck_card_ids, claims=combo_claims)
global_values_authority_matrix = build_globalvalues_authority_matrix(
    claims=globalvalues_claims,
    runtime_evidence=runtime_evidence,
)
card_behavior_plan = route_card_behavior_surfaces(
    cardid_claims,
    identity_links=identity_links,
)
```

Keep raw `claims` for diagnostics that must show source debt. Do not use raw `claims` for runtime JSON builders.

- [ ] **Step 4: Run conflict and ShadowPriest regression tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest -q tests/test_source_claim_conflicts.py tests/test_shadowpriest_e2e.py
```

Expected: PASS. ShadowPriest must still keep `SW_448` effect behavior and keep it out of `Mulligan.json`.

- [ ] **Step 5: Commit**

```powershell
git add src/hsconfig/package_builder.py tests/test_source_claim_conflicts.py tests/test_shadowpriest_e2e.py
git commit -m "fix: quarantine conflicting claims before runtime builders"
```

---

### Task 3: Source Contract Audit Uses Lifecycle Rows As Canonical Input

**Files:**
- Modify: `src/hsconfig/source_contract_audit.py`
- Modify: `src/hsconfig/package_builder.py`
- Test: `tests/test_source_contract_audit.py`

**Interfaces:**
- Consumes: `initial_lifecycle_rows: Sequence[Mapping[str, Any]]`.
- Produces: existing `source_contract_audit.json.claim_lifecycle_rows` schema with added fields but no removed fields.

- [ ] **Step 1: Write failing audit test**

Add to `tests/test_source_contract_audit.py`:

```python
from hsconfig.source_claim_lifecycle import build_initial_lifecycle_rows
from hsconfig.source_contract_audit import build_source_contract_audit


def test_source_contract_audit_preserves_canonical_quarantine_row():
    lifecycle_rows = build_initial_lifecycle_rows(
        [
            {
                "claim_id": "discard_card",
                "claim_kind": "mulligan_discard",
                "card_id": "CARD_001",
                "source_confidence": "guide_backed",
            }
        ],
        conflict_report={
            "conflicts": [
                {
                    "claim_ids": ["discard_card"],
                    "reason": "contradictory_mulligan_keep_discard",
                }
            ]
        },
    )

    report = build_source_contract_audit(
        deck_name="ConflictDeck",
        claims=[],
        mulligan_plan={"entries": []},
        combo_plan={"entries": []},
        card_behavior_plan={"emitted": [], "suppressed": []},
        globalvalues_authority_matrix={"rows": []},
        initial_lifecycle_rows=lifecycle_rows,
    )

    row = report["claim_lifecycle_rows"][0]
    assert row["claim_id"] == "discard_card"
    assert row["quarantine_status"] == "quarantined"
    assert row["final_runtime_effect"] == "suppressed_quarantined_claim"
    assert report["summary"]["claim_lifecycle_decision_counts"]["suppressed_quarantined_claim"] == 1
```

- [ ] **Step 2: Run audit test to verify it fails**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest -q tests/test_source_contract_audit.py::test_source_contract_audit_preserves_canonical_quarantine_row
```

Expected: FAIL because `build_source_contract_audit()` does not accept `initial_lifecycle_rows`.

- [ ] **Step 3: Update audit builder**

Change `build_source_contract_audit()` signature to include:

```python
initial_lifecycle_rows: Sequence[Mapping[str, Any]] | None = None,
```

Inside the function, replace the raw-only lifecycle build with:

```python
if initial_lifecycle_rows is None:
    claim_lifecycle_rows = _build_claim_lifecycle_rows(
        guide_claim_bundle=guide_claim_bundle,
        mulligan_plan=mulligan_plan,
        card_behavior_plan=card_behavior_plan,
        combo_plan=combo_plan,
        global_values_authority_matrix=global_values_authority_matrix,
        config_readiness_report=config_readiness_report,
    )
else:
    claim_lifecycle_rows = _merge_builder_outcomes_into_lifecycle(
        [dict(row) for row in initial_lifecycle_rows],
        mulligan_plan=mulligan_plan,
        combo_plan=combo_plan,
        card_behavior_plan=card_behavior_plan,
        globalvalues_authority_matrix=globalvalues_authority_matrix,
    )
```

Then keep the existing summary assignment, using `claim_lifecycle_rows`:

```python
summary["claim_lifecycle_decision_counts"] = _claim_lifecycle_decision_counts(
    mulligan_plan=mulligan_plan,
    claim_lifecycle_rows=claim_lifecycle_rows,
)
```

Add helper:

```python
def _merge_builder_outcomes_into_lifecycle(
    rows: list[dict[str, Any]],
    *,
    mulligan_plan: Mapping[str, Any],
    combo_plan: Mapping[str, Any],
    card_behavior_plan: Mapping[str, Any],
    globalvalues_authority_matrix: Mapping[str, Any],
) -> list[dict[str, Any]]:
    emitted_claim_ids = _emitted_claim_ids(
        mulligan_plan,
        combo_plan,
        card_behavior_plan,
        globalvalues_authority_matrix,
    )
    merged: list[dict[str, Any]] = []
    for row in rows:
        claim_id = str(row.get("claim_id") or "")
        updated = dict(row)
        if updated.get("quarantine_status") == "quarantined":
            updated["builder_status"] = "suppressed:quarantined"
            updated["first_missing_link"] = "source_claim_conflict"
            updated["final_runtime_effect"] = "suppressed_quarantined_claim"
        elif claim_id in emitted_claim_ids:
            updated["builder_status"] = "emitted"
            updated["final_runtime_effect"] = "emitted_runtime_row"
        else:
            updated.setdefault("builder_status", "not_seen_by_builder")
            updated.setdefault("first_missing_link", "not_seen_by_builder")
            updated.setdefault("final_runtime_effect", "report_visible_no_runtime_row")
        merged.append(updated)
    return merged
```

Add `_emitted_claim_ids()` by reading `_claim_lifecycle.claim_id` from emitted builder rows. If a builder does not yet preserve `_claim_lifecycle`, add that preservation in Task 4.

- [ ] **Step 4: Pass lifecycle rows from package builder to audit**

In `src/hsconfig/package_builder.py`, update the audit call:

```python
source_contract_audit_report = build_source_contract_audit(
    deck_name=args.deck_name,
    deck_identity=deck_identity,
    guide_claim_bundle=guide_claim_bundle,
    mulligan_plan=mulligan_plan,
    card_behavior_plan=card_behavior_plan,
    combo_plan=combo_plan,
    global_values_authority_matrix=global_values_authority_matrix,
    config_readiness_report=config_readiness_report,
    initial_lifecycle_rows=initial_lifecycle_rows,
)
```

- [ ] **Step 5: Run audit tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest -q tests/test_source_contract_audit.py tests/test_prepare_cli.py::test_prepare_writes_source_contract_audit
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add src/hsconfig/source_contract_audit.py src/hsconfig/package_builder.py tests/test_source_contract_audit.py
git commit -m "refactor: derive source contract audit from claim lifecycle"
```

---

### Task 4: Preserve Lifecycle Provenance Through Runtime Builders

**Files:**
- Modify: `src/hsconfig/mulligan_plan.py`
- Modify: `src/hsconfig/combo_plan.py`
- Modify: `src/hsconfig/globalvalues_authority.py`
- Modify: `src/hsconfig/card_behavior_surface_router.py`
- Test: `tests/test_source_claim_lifecycle.py`
- Test: `tests/test_mulligan_plan.py`
- Test: `tests/test_combo_plan.py`
- Test: `tests/test_globalvalues_authority.py`
- Test: `tests/test_card_behavior_router.py`

**Interfaces:**
- Consumes: claim dicts containing `_claim_lifecycle`.
- Produces: every emitted or suppressed builder row carries `claim_id` or `_claim_lifecycle.claim_id`.

- [ ] **Step 1: Write failing builder provenance tests**

Add to `tests/test_source_claim_lifecycle.py`:

```python
from hsconfig.card_behavior_surface_router import route_card_behavior_surfaces
from hsconfig.combo_plan import build_combo_plan
from hsconfig.globalvalues_authority import build_globalvalues_authority_matrix
from hsconfig.mulligan_plan import build_mulligan_plan


def test_runtime_builders_preserve_lifecycle_claim_id():
    lifecycle = {"claim_id": "claim_keep", "surface": "mulligan"}
    mulligan = build_mulligan_plan(
        deck_name="Deck",
        claims=[
            {
                "claim_id": "claim_keep",
                "claim_kind": "mulligan_keep",
                "card_id": "CARD_001",
                "_claim_lifecycle": lifecycle,
            }
        ],
        card_roles={},
    )
    assert mulligan["entries"][0]["claim_id"] == "claim_keep"

    combo = build_combo_plan(
        deck_cards={"CARD_001", "CARD_002"},
        claims=[
            {
                "claim_id": "claim_combo",
                "claim_kind": "combo_sequence",
                "combo": "CARD_001 >> CARD_002",
                "value": "10 >> 20",
                "_claim_lifecycle": {"claim_id": "claim_combo", "surface": "combo"},
            }
        ],
    )
    assert combo["entries"][0]["claim_id"] == "claim_combo"

    globalvalues = build_globalvalues_authority_matrix(
        claims=[
            {
                "claim_id": "claim_posture",
                "claim_kind": "gameplan_posture",
                "posture": "aggro",
                "_claim_lifecycle": {"claim_id": "claim_posture", "surface": "globalvalues"},
            }
        ],
        runtime_evidence=None,
    )
    assert globalvalues["rows"][0]["claim_id"] == "claim_posture"

    cardid = route_card_behavior_surfaces(
        [
            {
                "claim_id": "claim_target",
                "claim_kind": "targeting_rule",
                "card_id": "CARD_003",
                "target": "enemy_hero",
                "_claim_lifecycle": {"claim_id": "claim_target", "surface": "cardid"},
            }
        ]
    )
    assert cardid["emitted"][0]["claim_id"] == "claim_target"
```

- [ ] **Step 2: Run provenance test to verify it fails**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest -q tests/test_source_claim_lifecycle.py::test_runtime_builders_preserve_lifecycle_claim_id
```

Expected: FAIL for builders that do not preserve `claim_id`.

- [ ] **Step 3: Add provenance helper locally or shared**

Create this local helper in each builder or add it once to `source_claim_lifecycle.py` and import it:

```python
def lifecycle_claim_id(claim: Mapping[str, Any]) -> str:
    lifecycle = claim.get("_claim_lifecycle")
    if isinstance(lifecycle, Mapping):
        value = lifecycle.get("claim_id")
        if value:
            return str(value)
    value = claim.get("claim_id")
    return str(value) if value else ""
```

When each builder creates an emitted or suppressed row, add:

```python
claim_id = lifecycle_claim_id(claim)
if claim_id:
    row["claim_id"] = claim_id
```

Do not write `_claim_lifecycle` into runtime JSON files. It is report metadata only.

- [ ] **Step 4: Run builder tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest -q tests/test_source_claim_lifecycle.py tests/test_mulligan_plan.py tests/test_combo_plan.py tests/test_globalvalues_authority.py tests/test_card_behavior_router.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/hsconfig/mulligan_plan.py src/hsconfig/combo_plan.py src/hsconfig/globalvalues_authority.py src/hsconfig/card_behavior_surface_router.py src/hsconfig/source_claim_lifecycle.py tests/test_source_claim_lifecycle.py
git commit -m "refactor: preserve claim lifecycle provenance through builders"
```

---

### Task 5: Enforce No-Second-Gate And Sentinel Coverage

**Files:**
- Modify: `src/hsconfig/contract_spine_sentinel.py`
- Modify: `src/hsconfig/source_contract_conformance.py`
- Test: `tests/test_contract_spine_sentinel.py`
- Test: `tests/test_source_contract_conformance.py`
- Test: `tests/test_apply_authority_boundary.py`

**Interfaces:**
- Consumes: lifecycle module API and current conformance snapshot.
- Produces: diagnostic-only sentinel failures for drift, never apply-blocking runtime behavior.

- [ ] **Step 1: Write failing sentinel tests**

Add to `tests/test_contract_spine_sentinel.py`:

```python
from hsconfig.contract_spine_sentinel import build_contract_spine_sentinel


def test_sentinel_knows_lifecycle_module_is_runtime_eligibility_owner():
    report = build_contract_spine_sentinel()
    checks = report["checks"]
    assert checks["claim_lifecycle_owner"] == "hsconfig.source_claim_lifecycle"
    assert report["authority"] == "diagnostic_only"
    assert report["apply_blocking"] is False


def test_sentinel_keeps_operator_summary_as_only_gate_after_lifecycle():
    report = build_contract_spine_sentinel()
    assert report["checks"]["report_ownership_gate_files"] == ["reports/operator_summary.json"]
    assert report["checks"]["lifecycle_gate_files"] == []
```

- [ ] **Step 2: Run sentinel tests to verify failure**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest -q tests/test_contract_spine_sentinel.py::test_sentinel_knows_lifecycle_module_is_runtime_eligibility_owner tests/test_contract_spine_sentinel.py::test_sentinel_keeps_operator_summary_as_only_gate_after_lifecycle
```

Expected: FAIL because sentinel does not expose lifecycle owner fields.

- [ ] **Step 3: Extend sentinel diagnostic**

In `src/hsconfig/contract_spine_sentinel.py`, add:

```python
checks["claim_lifecycle_owner"] = "hsconfig.source_claim_lifecycle"
checks["lifecycle_gate_files"] = []
```

Add a negative scan that fails only the sentinel diagnostic when active docs or report ownership classify lifecycle artifacts as apply gates:

```python
checks["lifecycle_gate_files"] = [
    row["file"]
    for row in report_ownership_rows
    if row.get("file") != "reports/operator_summary.json"
    and row.get("classification") == "operator_gate"
]
```

Keep top-level:

```python
report["authority"] = "diagnostic_only"
report["apply_blocking"] = False
```

- [ ] **Step 4: Run sentinel and authority tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest -q tests/test_contract_spine_sentinel.py tests/test_source_contract_conformance.py tests/test_apply_authority_boundary.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/hsconfig/contract_spine_sentinel.py src/hsconfig/source_contract_conformance.py tests/test_contract_spine_sentinel.py tests/test_source_contract_conformance.py tests/test_apply_authority_boundary.py
git commit -m "test: guard claim lifecycle authority boundary"
```

---

### Task 6: Any-Deck No-Block Regression Matrix

**Files:**
- Modify: `tests/test_universal_wild_no_block_matrix.py`
- Modify: `tests/test_shadowpriest_e2e.py`
- Modify: `tests/test_source_to_runtime_explainability.py` if first-missing-link output changes

**Interfaces:**
- Consumes: `hsconfig configure` or existing fixture builders.
- Produces: proof that valid packages still apply even when claims are thin, report-only, unresolved, future-mechanic, or quarantined.

- [ ] **Step 1: Add no-block lifecycle regression cases**

First add this exact helper to `tests/test_universal_wild_no_block_matrix.py` below `prepare_fixture_deck_with_source_claim()`:

```python
def prepare_fixture_deck_with_source_claims(tmp_path: Path, *, deck_name: str, claims: list[dict]):
    cards = tmp_path / f"{deck_name}_cards.json"
    cards.write_text(
        json.dumps(
            {
                "cards": [
                    {
                        "card_id": "CARD_001",
                        "dbf_id": 1,
                        "count": 1,
                        "name": "Fixture Card",
                        "text": "Fixture card text.",
                    },
                    {
                        "card_id": "CARD_777",
                        "dbf_id": 777,
                        "count": 1,
                        "name": "Future Fixture Card",
                        "text": "Future mechanic fixture card text.",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    sources = tmp_path / f"{deck_name}_sources.json"
    sources.write_text(
        json.dumps(
            [
                {
                    "source_url": f"https://example.invalid/{deck_name}",
                    "source_title": f"{deck_name} Fixture",
                    "source_family": "guide_fixture",
                    "retrieved_at": "2026-07-13T00:00:00Z",
                    "claims": claims,
                }
            ]
        ),
        encoding="utf-8",
    )
    out = tmp_path / f"{deck_name}_package"
    exit_code = main(
        [
            "prepare",
            "--deck-name",
            deck_name,
            "--deck-code",
            "fixture-code",
            "--runtime-root",
            str(tmp_path / f"{deck_name}_runtime"),
            "--out",
            str(out),
            "--cards-json",
            str(cards),
            "--guide-sources-json",
            str(sources),
        ]
    )
    reports = out / "reports"
    return {
        "exit_code": exit_code,
        "package": out,
        "operator_summary": json.loads(
            (reports / "operator_summary.json").read_text(encoding="utf-8")
        ),
        "source_contract_audit": json.loads(
            (reports / "source_contract_audit.json").read_text(encoding="utf-8")
        ),
    }
```

Then add these cases to `tests/test_universal_wild_no_block_matrix.py`:

```python
def test_quarantined_claims_do_not_block_valid_load_safe_package(tmp_path):
    result = prepare_fixture_deck_with_source_claims(
        tmp_path,
        deck_name="NoBlockConflictDeck",
        claims=[
            {
                "claim_id": "keep_card",
                "claim_kind": "mulligan_keep",
                "card_id": "CARD_001",
                "source_confidence": "guide_backed",
            },
            {
                "claim_id": "discard_card",
                "claim_kind": "mulligan_discard",
                "card_id": "CARD_001",
                "source_confidence": "guide_backed",
            },
        ],
    )

    operator_summary = result["operator_summary"]
    source_contract_audit = result["source_contract_audit"]
    assert operator_summary["technical_status"] == "VALID_PACKAGE"
    assert operator_summary["runtime_apply_allowed"] is True
    assert source_contract_audit["summary"]["claim_lifecycle_decision_counts"][
        "suppressed_quarantined_claim"
    ] >= 1


def test_unknown_future_mechanic_stays_report_visible_without_runtime_row(tmp_path):
    result = prepare_fixture_deck_with_source_claims(
        tmp_path,
        deck_name="FutureMechanicDeck",
        claims=[
            {
                "claim_id": "future_1",
                "claim_kind": "mechanic_usage",
                "card_id": "CARD_777",
                "mechanic": "future_keyword",
                "source_confidence": "unknown_future_mechanic",
            }
        ],
    )

    operator_summary = result["operator_summary"]
    assert operator_summary["technical_status"] == "VALID_PACKAGE"
    assert operator_summary["runtime_apply_allowed"] is True
    assert operator_summary["no_block_failure_mode_summary"]["hard_block"] is False
```

- [ ] **Step 2: Add ShadowPriest effect-vs-mulligan lifecycle assertion**

Extend `tests/test_shadowpriest_e2e.py`:

```python
def test_shadowpriest_darkbishop_effect_visible_but_not_mulligan_keep_after_lifecycle(tmp_path):
    result = _build_shadowpriest_fixture_package(tmp_path)
    mulligan_text = result["mulligan_json"].read_text(encoding="utf-8")
    darkbishop_text = result["card_json_by_id"]["SW_448"].read_text(encoding="utf-8")
    audit = result["source_contract_audit"]

    assert "SW_448" not in mulligan_text
    assert "BeforeUseHeroPowerBonus" in darkbishop_text
    rows = [row for row in audit["claim_lifecycle_rows"] if row.get("card_id") == "SW_448"]
    assert any(row["claim_kind"] == "hero_power_transform" for row in rows)
    assert all(row["claim_kind"] != "mulligan_keep" for row in rows)
```

Use the live helper names in `tests/test_shadowpriest_e2e.py`; do not create a duplicate fixture if an equivalent helper already exists.

- [ ] **Step 3: Run no-block and ShadowPriest tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest -q tests/test_universal_wild_no_block_matrix.py tests/test_shadowpriest_e2e.py tests/test_source_to_runtime_explainability.py
```

Expected: PASS.

- [ ] **Step 4: Commit**

```powershell
git add tests/test_universal_wild_no_block_matrix.py tests/test_shadowpriest_e2e.py tests/test_source_to_runtime_explainability.py
git commit -m "test: prove lifecycle no-block behavior across decks"
```

---

### Task 7: Operator Docs And Skill Contract Polish

**Files:**
- Modify: `docs/operator/guide-research-policy.md`
- Modify: `.agents/skills/hsconfig/SKILL.md`
- Test: `tests/test_skill_files.py`
- Test: `tests/test_operator_docs_contract_policy.py`

**Interfaces:**
- Consumes: lifecycle vocabulary from Tasks 1-6.
- Produces: one operator-visible explanation of source -> lifecycle -> runtime lowering.

- [ ] **Step 1: Write failing docs tests**

Add to `tests/test_operator_docs_contract_policy.py`:

```python
from pathlib import Path


def test_operator_docs_name_canonical_lifecycle_without_second_gate():
    text = Path("docs/operator/guide-research-policy.md").read_text(encoding="utf-8")
    assert "canonical claim lifecycle" in text.lower()
    assert "operator_summary.json remains the only normal apply authority" in text
    assert "source_contract_audit.json is diagnostic" in text


def test_skill_mentions_claim_lifecycle_and_no_block_contract():
    text = Path(".agents/skills/hsconfig/SKILL.md").read_text(encoding="utf-8")
    assert "canonical claim lifecycle" in text.lower()
    assert "quarantined claims suppress unsafe runtime rows" in text
    assert "do not block load-safe valid packages" in text
```

- [ ] **Step 2: Run docs tests to verify failure**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest -q tests/test_operator_docs_contract_policy.py::test_operator_docs_name_canonical_lifecycle_without_second_gate tests/test_operator_docs_contract_policy.py::test_skill_mentions_claim_lifecycle_and_no_block_contract
```

Expected: FAIL because docs do not yet include the exact lifecycle wording.

- [ ] **Step 3: Update operator docs**

Add this paragraph to `docs/operator/guide-research-policy.md` near the source-contract policy section:

```markdown
The canonical claim lifecycle is the single diagnostic chain from source evidence to runtime eligibility: source claim -> normalized `claim_kind` -> semantic qualifiers -> conflict quarantine -> surface gate -> builder/router outcome -> emitted runtime row or suppression reason. `source_contract_audit.json` is diagnostic; `operator_summary.json remains the only normal apply authority`. Quarantined claims suppress unsafe runtime rows, stay visible in reports, and do not block load-safe valid packages.
```

Add matching concise guidance to `.agents/skills/hsconfig/SKILL.md`:

```markdown
- Use the canonical claim lifecycle when explaining source-to-runtime behavior. It records source claim, normalized `claim_kind`, semantic qualifiers, conflict quarantine, surface gate, builder/router outcome, and runtime effect or suppression reason. Quarantined claims suppress unsafe runtime rows, stay visible in reports, and do not block load-safe valid packages. `operator_summary.json` remains the only normal apply authority.
```

- [ ] **Step 4: Run docs tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest -q tests/test_operator_docs_contract_policy.py tests/test_skill_files.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add docs/operator/guide-research-policy.md .agents/skills/hsconfig/SKILL.md tests/test_operator_docs_contract_policy.py tests/test_skill_files.py
git commit -m "docs: document canonical claim lifecycle contract"
```

---

### Task 8: Final Verification, Research Package, And Branch Handoff

**Files:**
- Keep: `docs/research/2026-07-13-hsconfig-source-contract-logic-brainstorm-v6/**`
- No code changes unless verification exposes a concrete failure.

**Interfaces:**
- Consumes: all previous commits.
- Produces: verified branch ready for push or merge.

- [ ] **Step 1: Validate research package files**

Run:

```powershell
$fields='docs/research/2026-07-13-hsconfig-source-contract-logic-brainstorm-v6/fields.yaml'
Get-ChildItem 'docs/research/2026-07-13-hsconfig-source-contract-logic-brainstorm-v6/results' -Filter *.json | ForEach-Object {
  python "$env:USERPROFILE\.codex\skills\research\validate_json.py" -f $fields -j $_.FullName
}
```

Expected: each result reports full field coverage and validation passed.

- [ ] **Step 2: Run focused contract suite**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest -q tests/test_source_claim_lifecycle.py tests/test_source_claim_conflicts.py tests/test_source_contract_audit.py tests/test_contract_spine_sentinel.py tests/test_apply_authority_boundary.py tests/test_universal_wild_no_block_matrix.py tests/test_shadowpriest_e2e.py
```

Expected: PASS.

- [ ] **Step 3: Run sentinel**

Run:

```powershell
$env:PYTHONPATH='src'; python -m hsconfig contract-spine-sentinel --json
```

Expected JSON fields:

```json
{
  "status": "clean",
  "apply_blocking": false,
  "operator_gate_impact": "diagnostic_only"
}
```

- [ ] **Step 4: Run full test suite**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest -q
```

Expected: PASS with the existing skipped count only.

- [ ] **Step 5: Run compile check**

Run:

```powershell
python -m compileall -q src tests
```

Expected: no output and exit code 0.

- [ ] **Step 6: Check diff hygiene**

Run:

```powershell
git diff --check
git status --short --branch
```

Expected: `git diff --check` exits 0. `git status` shows only intended files before staging.

- [ ] **Step 7: Commit research package and final plan if not already committed**

```powershell
git add docs/research/2026-07-13-hsconfig-source-contract-logic-brainstorm-v6 docs/superpowers/plans/2026-07-13-hsconfig-canonical-claim-lifecycle-conflict-quarantine.md
git commit -m "docs: add source contract lifecycle research and plan"
```

- [ ] **Step 8: Push branch**

```powershell
git push origin codex/hsconfig-contract-spine-guard-wave
```

Expected: push succeeds and remote branch is current.

---

## Self-Review

- Spec coverage: The plan covers canonical lifecycle, conflict quarantine, builder filtering, audit projection, sentinel protection, no-block autonomy, Darkbishop effect-vs-mulligan regression, docs, research validation, focused tests, and full verification.
- Placeholder scan: No unresolved placeholder markers or open-ended "handle edge cases" steps. Each implementation task includes concrete files, test intent, commands, and expected output.
- Type consistency: The central interfaces are `build_initial_lifecycle_rows()`, `runtime_claims_for_surface()`, `strict_claim_kind()`, and optional `initial_lifecycle_rows` on `build_source_contract_audit()`. Later tasks refer to those exact names.
- Scope check: This is one coherent implementation wave. It does not add post-run tuning, new runtime writers, new VisionAI surfaces, or a second apply gate.

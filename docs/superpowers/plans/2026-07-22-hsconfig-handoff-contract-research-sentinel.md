# HSConfig Handoff Contract And Research Sentinel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a compact, diagnostic-only proof layer that shows each generated HSConfig package is usable, non-default-only, source-status honest, and bound to the single normal apply authority without adding runtime logic or blocking valid decks.

**Architecture:** Keep `reports/operator_summary.json` as the only normal apply authority. Add a configure-local `handoff_contract` projection to `configure_summary.json`, and add a read-only research-result sentinel that validates HSConfig-specific research-deep outputs without promoting, downgrading, applying, or blocking runtime config.

**Tech Stack:** Python 3.11, pytest, pathlib/json/yaml, existing `hsconfig` package modules, existing `scripts/check_contract_guardrails.py`.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig`.
- Do not use HSTuner, runtime logs, replay analysis, winrate data, or post-game tuning.
- Do not write HearthRanger runtime files in this plan.
- Do not create new normal runtime surfaces.
- Normal runtime surfaces stay limited to `GlobalValues.json`, `Mulligan.json`, per-card `<CARDID>.json`, and conditional `Combo.json`.
- `Presume.json`, `Concede.json`, and aggregate `CardBehavior.json` remain outside the normal HSConfig path.
- `reports/operator_summary.json` remains the only normal apply authority.
- `SOURCE_BACKED_STRONG` remains an evidence-quality label, not an apply gate.
- Thin or partial sources must never block a valid load-safe deck package.
- `source_status_apply_blocking` must remain `false` for source-quality diagnostics.
- Darkbishop Benedictus effect semantics may be represented on the supported per-card surface, but the card must not become a Mulligan keep without explicit opening-hand evidence.
- Keep the worktree clean after implementation: no backups, no generated caches, no untracked runtime artifacts.

---

## File Structure

- Modify `src/hsconfig/commands/configure.py`
  - Owns configure-local operator projections.
  - Add `_build_handoff_contract(...)`.
  - Add `handoff_contract` to `configure_summary.json`.

- Create `src/hsconfig/research_result_contract_sentinel.py`
  - Owns read-only batch validation of HSConfig research-deep `fields.yaml` and `results/*.json`.
  - Consumes existing `validate_fields_yaml_payload`, `validate_research_result_payload`, and `classify_research_result_contract`.
  - Produces diagnostic-only summary and rows.

- Modify `src/hsconfig/contract_preflight.py`
  - Surface the latest research-result sentinel status inside `research_context`.
  - Keep top-level preflight status based on machinery/currentness, not on source strength.

- Modify `scripts/check_contract_guardrails.py`
  - Add the new focused sentinel and handoff tests to the contract guardrail suite.

- Create `tests/test_configure_handoff_contract.py`
  - Focused tests for `handoff_contract`, independent from the large configure CLI file.

- Create `tests/test_research_result_contract_sentinel.py`
  - Focused tests for batch validation and non-blocking semantics.

- Modify `tests/test_contract_preflight.py`
  - Assert research sentinel visibility is diagnostic-only and does not become an apply gate.

- Modify `.agents/skills/hsconfig/SKILL.md`
  - Document the new compact handoff projection and research-result sentinel boundary.

- Modify `.agents/skills/hsconfig/references/workflow.md`
  - Add the operator reading order: acceptance summary, handoff contract, operator summary.

- Modify `docs/operator/README.md`
  - Document the new diagnostic projection and no-block behavior.

- Modify `docs/operator/source-backed-strong-closure.md`
  - Document that research-result sentinel validation cannot promote or downgrade package status.

- Run `scripts/sync_installed_skill.py`
  - Sync the installed `$hsconfig` skill after repo skill docs change.

---

### Task 1: Configure Handoff Contract Projection

**Files:**
- Modify: `src/hsconfig/commands/configure.py`
- Create: `tests/test_configure_handoff_contract.py`

**Interfaces:**
- Consumes:
  - `operator_summary: Mapping[str, Any]`
  - `acceptance_summary: Mapping[str, Any]`
  - `config_proof_summary: Mapping[str, Any]`
  - `config_quality_summary: Mapping[str, Any]`
- Produces:
  - `_build_handoff_contract(...) -> dict[str, Any]`
  - `configure_summary.json["handoff_contract"]`

- [ ] **Step 1: Write failing helper tests**

Create `tests/test_configure_handoff_contract.py`:

```python
from __future__ import annotations

from hsconfig.commands.configure import _build_handoff_contract


def test_handoff_contract_reports_clean_single_authority_package() -> None:
    contract = _build_handoff_contract(
        operator_summary={
            "runtime_apply_contract": {
                "apply_authority": "reports/operator_summary.json",
            },
            "source_status_apply_blocking": False,
            "first_missing_source_action": "none",
        },
        acceptance_summary={
            "use_config_now": True,
            "normal_apply_authority": "reports/operator_summary.json",
            "runtime_apply_allowed": True,
            "runtime_apply_mode": "load_safe_apply",
            "technical_status": "VALID_PACKAGE",
            "source_strength": "SOURCE_BACKED_STRONG",
            "source_gaps_apply_blocking": False,
            "default_only_clean": True,
            "default_only_runtime_surfaces": [],
            "next_report_to_open": "reports/operator_summary.json",
        },
        config_proof_summary={
            "authority": "diagnostic_only",
            "apply_blocking": False,
            "normal_apply_authority": "reports/operator_summary.json",
            "no_default_only_clean": True,
            "default_only_runtime_surfaces": [],
            "forbidden_normal_surfaces_absent": True,
            "forbidden_normal_surfaces_status": "clean",
            "runtime_surface_boundary": [
                "GlobalValues.json",
                "Mulligan.json",
                "per-card <CARDID>.json",
                "Combo.json",
            ],
            "darkbishop_boundary_status": "effect_without_mulligan_keep",
            "source_to_runtime_status": "clean",
            "currentness_status": "clean",
            "closure_schema_current": True,
            "cards_missing_closure": 0,
            "semantic_intent_status": "clean",
            "runtime_json_status": "clean",
        },
        config_quality_summary={
            "status": "clean",
            "problem_checks": [],
            "mechanic_runtime_discipline_status": "clean",
        },
    )

    assert contract == {
        "schema_version": 1,
        "authority": "diagnostic_only",
        "apply_blocking": False,
        "runtime_write_performed": False,
        "status": "clean",
        "normal_apply_authority": "reports/operator_summary.json",
        "single_apply_authority_confirmed": True,
        "use_config_now": True,
        "runtime_apply_allowed": True,
        "runtime_apply_mode": "load_safe_apply",
        "technical_status": "VALID_PACKAGE",
        "source_strength": "SOURCE_BACKED_STRONG",
        "source_status_apply_blocking": False,
        "source_gaps_apply_blocking": False,
        "first_missing_source_action": "none",
        "default_only_clean": True,
        "default_only_runtime_surfaces": [],
        "forbidden_normal_surfaces_absent": True,
        "forbidden_normal_surfaces_status": "clean",
        "runtime_surface_boundary": [
            "GlobalValues.json",
            "Mulligan.json",
            "per-card <CARDID>.json",
            "Combo.json",
        ],
        "darkbishop_boundary_status": "effect_without_mulligan_keep",
        "runtime_json_status": "clean",
        "source_to_runtime_status": "clean",
        "currentness_status": "clean",
        "closure_schema_current": True,
        "cards_missing_closure": 0,
        "semantic_intent_status": "clean",
        "mechanic_runtime_discipline_status": "clean",
        "config_quality_status": "clean",
        "config_quality_problem_checks": [],
        "next_report_to_open": "reports/operator_summary.json",
    }


def test_handoff_contract_surfaces_attention_without_blocking_apply() -> None:
    contract = _build_handoff_contract(
        operator_summary={
            "runtime_apply_contract": {
                "apply_authority": "reports/operator_summary.json",
            },
            "source_status_apply_blocking": False,
            "first_missing_source_action": "fetch_and_normalize_candidate_full_text_claims",
        },
        acceptance_summary={
            "use_config_now": True,
            "normal_apply_authority": "reports/operator_summary.json",
            "runtime_apply_allowed": True,
            "runtime_apply_mode": "load_safe_apply",
            "technical_status": "VALID_PACKAGE",
            "source_strength": "SOURCE_BACKED_PARTIAL",
            "source_gaps_apply_blocking": False,
            "default_only_clean": False,
            "default_only_runtime_surfaces": ["Mulligan.json"],
            "next_report_to_open": "reports/contract_doctor.json",
        },
        config_proof_summary={
            "authority": "diagnostic_only",
            "apply_blocking": False,
            "normal_apply_authority": "reports/operator_summary.json",
            "no_default_only_clean": False,
            "default_only_runtime_surfaces": ["Mulligan.json"],
            "forbidden_normal_surfaces_absent": False,
            "forbidden_normal_surfaces_status": "attention",
            "runtime_surface_boundary": [
                "GlobalValues.json",
                "Mulligan.json",
                "per-card <CARDID>.json",
                "Combo.json",
            ],
            "darkbishop_boundary_status": "mulligan_keep_present",
            "source_to_runtime_status": "attention",
            "currentness_status": "attention",
            "closure_schema_current": False,
            "cards_missing_closure": 2,
            "semantic_intent_status": "attention",
            "runtime_json_status": "attention",
        },
        config_quality_summary={
            "status": "attention",
            "problem_checks": ["operator_default_only_runtime_surfaces"],
            "mechanic_runtime_discipline_status": "attention",
        },
    )

    assert contract["status"] == "attention"
    assert contract["apply_blocking"] is False
    assert contract["source_status_apply_blocking"] is False
    assert contract["single_apply_authority_confirmed"] is True
    assert contract["default_only_clean"] is False
    assert contract["default_only_runtime_surfaces"] == ["Mulligan.json"]
    assert contract["next_report_to_open"] == "reports/contract_doctor.json"
```

- [ ] **Step 2: Run the new tests and confirm they fail**

Run:

```powershell
python -m pytest -q tests/test_configure_handoff_contract.py
```

Expected: FAIL with `ImportError` or `AttributeError` because `_build_handoff_contract` does not exist yet.

- [ ] **Step 3: Implement the configure-local helper**

Modify `src/hsconfig/commands/configure.py`.

Add this helper after `_build_config_proof_summary(...)`:

```python
def _build_handoff_contract(
    *,
    operator_summary: Mapping[str, Any],
    acceptance_summary: Mapping[str, Any],
    config_proof_summary: Mapping[str, Any],
    config_quality_summary: Mapping[str, Any],
) -> dict[str, Any]:
    runtime_contract = operator_summary.get("runtime_apply_contract", {})
    if not isinstance(runtime_contract, Mapping):
        runtime_contract = {}

    normal_apply_authority = str(
        acceptance_summary.get("normal_apply_authority")
        or config_proof_summary.get("normal_apply_authority")
        or runtime_contract.get("apply_authority")
        or "reports/operator_summary.json"
    )
    default_only_runtime_surfaces = [
        str(surface)
        for surface in (
            acceptance_summary.get("default_only_runtime_surfaces")
            or config_proof_summary.get("default_only_runtime_surfaces")
            or []
        )
        if str(surface)
    ]
    problem_checks = [
        str(check)
        for check in config_quality_summary.get("problem_checks", [])
        if str(check)
    ]
    source_status_apply_blocking = bool(
        operator_summary.get(
            "source_status_apply_blocking",
            acceptance_summary.get("source_gaps_apply_blocking", False),
        )
    )
    source_gaps_apply_blocking = bool(
        acceptance_summary.get(
            "source_gaps_apply_blocking",
            source_status_apply_blocking,
        )
    )
    forbidden_normal_surfaces_absent = config_proof_summary.get(
        "forbidden_normal_surfaces_absent"
    )
    status = (
        "clean"
        if (
            bool(acceptance_summary.get("use_config_now"))
            and normal_apply_authority == "reports/operator_summary.json"
            and not source_status_apply_blocking
            and not source_gaps_apply_blocking
            and bool(acceptance_summary.get("default_only_clean"))
            and not default_only_runtime_surfaces
            and forbidden_normal_surfaces_absent is True
            and str(config_proof_summary.get("runtime_json_status") or "") == "clean"
            and str(config_proof_summary.get("source_to_runtime_status") or "")
            == "clean"
            and str(config_quality_summary.get("status") or "") == "clean"
            and not problem_checks
        )
        else "attention"
    )

    return {
        "schema_version": 1,
        "authority": "diagnostic_only",
        "apply_blocking": False,
        "runtime_write_performed": False,
        "status": status,
        "normal_apply_authority": normal_apply_authority,
        "single_apply_authority_confirmed": (
            normal_apply_authority == "reports/operator_summary.json"
        ),
        "use_config_now": bool(acceptance_summary.get("use_config_now")),
        "runtime_apply_allowed": bool(
            acceptance_summary.get("runtime_apply_allowed", False)
        ),
        "runtime_apply_mode": str(acceptance_summary.get("runtime_apply_mode", "")),
        "technical_status": str(acceptance_summary.get("technical_status", "")),
        "source_strength": str(acceptance_summary.get("source_strength", "")),
        "source_status_apply_blocking": source_status_apply_blocking,
        "source_gaps_apply_blocking": source_gaps_apply_blocking,
        "first_missing_source_action": (
            acceptance_summary.get("first_missing_source_action")
            or operator_summary.get("first_missing_source_action")
        ),
        "default_only_clean": bool(acceptance_summary.get("default_only_clean")),
        "default_only_runtime_surfaces": default_only_runtime_surfaces,
        "forbidden_normal_surfaces_absent": forbidden_normal_surfaces_absent,
        "forbidden_normal_surfaces_status": str(
            config_proof_summary.get("forbidden_normal_surfaces_status") or ""
        ),
        "runtime_surface_boundary": [
            str(surface)
            for surface in config_proof_summary.get("runtime_surface_boundary", [])
            if str(surface)
        ],
        "darkbishop_boundary_status": str(
            config_proof_summary.get("darkbishop_boundary_status") or ""
        ),
        "runtime_json_status": str(
            config_proof_summary.get("runtime_json_status") or ""
        ),
        "source_to_runtime_status": str(
            config_proof_summary.get("source_to_runtime_status") or ""
        ),
        "currentness_status": str(
            config_proof_summary.get("currentness_status") or ""
        ),
        "closure_schema_current": bool(
            config_proof_summary.get("closure_schema_current", False)
        ),
        "cards_missing_closure": int(
            config_proof_summary.get("cards_missing_closure") or 0
        ),
        "semantic_intent_status": str(
            config_proof_summary.get("semantic_intent_status") or ""
        ),
        "mechanic_runtime_discipline_status": str(
            config_quality_summary.get("mechanic_runtime_discipline_status") or ""
        ),
        "config_quality_status": str(config_quality_summary.get("status") or ""),
        "config_quality_problem_checks": problem_checks,
        "next_report_to_open": str(
            acceptance_summary.get("next_report_to_open")
            or config_proof_summary.get("next_report_to_open")
            or "reports/operator_summary.json"
        ),
    }
```

- [ ] **Step 4: Wire the helper into `configure_summary.json`**

In `run_configure_command(...)`, replace the inline acceptance/proof calls with local variables before the `_finish(...)` call:

```python
    acceptance_summary = _build_acceptance_summary(
        operator_summary=operator_summary,
        validate_status=validate_status,
        apply_requested=bool(getattr(args, "apply", False)),
        apply_status=apply_status,
        config_quality_summary=config_quality_summary,
    )
    config_proof_summary = _build_config_proof_summary(
        operator_summary=operator_summary,
        validate_status=validate_status,
        apply_requested=bool(getattr(args, "apply", False)),
        apply_status=apply_status,
        config_quality_summary=config_quality_summary,
    )
    handoff_contract = _build_handoff_contract(
        operator_summary=operator_summary,
        acceptance_summary=acceptance_summary,
        config_proof_summary=config_proof_summary,
        config_quality_summary=config_quality_summary,
    )
```

Then update the payload keys:

```python
            "config_quality_summary": config_quality_summary,
            "acceptance_summary": acceptance_summary,
            "config_proof_summary": config_proof_summary,
            "handoff_contract": handoff_contract,
```

- [ ] **Step 5: Run focused tests**

Run:

```powershell
python -m pytest -q tests/test_configure_handoff_contract.py tests/test_configure_cli.py::test_configure_writes_diagnostic_config_quality_summary
```

Expected: PASS.

- [ ] **Step 6: Commit Task 1**

```powershell
git add src/hsconfig/commands/configure.py tests/test_configure_handoff_contract.py
git commit -m "feat: add configure handoff contract"
```

---

### Task 2: Research Result Contract Sentinel

**Files:**
- Create: `src/hsconfig/research_result_contract_sentinel.py`
- Create: `tests/test_research_result_contract_sentinel.py`

**Interfaces:**
- Consumes:
  - `fields_path: str | Path`
  - `results_dir: str | Path`
  - Existing `validate_fields_yaml_payload(payload)`
  - Existing `validate_research_result_payload(payload)`
  - Existing `classify_research_result_contract(payload)`
- Produces:
  - `build_research_result_contract_sentinel(fields_path, results_dir) -> dict[str, Any]`

- [ ] **Step 1: Write failing sentinel tests**

Create `tests/test_research_result_contract_sentinel.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

import yaml

from hsconfig.research_result_contract_sentinel import (
    build_research_result_contract_sentinel,
)


FIELDS = {
    "fields": {
        "deck_name": {"type": "string"},
        "archetype": {"type": "string"},
        "current_deck_sources": {"type": "array"},
        "guide_sources": {"type": "array"},
        "source_strength": {"type": "string"},
        "lowerable_claim_kinds": {"type": "array"},
        "non_promoting_support": {"type": "array"},
        "first_missing_source_action": {"type": "string"},
        "notes": {"type": "string"},
    }
}


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_sentinel_reports_valid_partial_results_without_apply_blocking(
    tmp_path: Path,
) -> None:
    fields_path = tmp_path / "fields.yaml"
    fields_path.write_text(yaml.safe_dump(FIELDS), encoding="utf-8")
    results_dir = tmp_path / "results"
    _write_json(
        results_dir / "ShadowPriest.json",
        {
            "deck_name": "ShadowPriest",
            "archetype": "Wild Shadow Priest",
            "current_deck_sources": [],
            "guide_sources": [],
            "source_strength": "unfetched_acquisition_seed",
            "lowerable_claim_kinds": [],
            "non_promoting_support": [],
            "first_missing_source_action": "fetch_and_normalize_candidate_full_text_claims",
            "source_status_apply_blocking_expected": False,
            "default_only_runtime_surfaces_expected": "none",
            "notes": "Seed snapshots are diagnostic only.",
        },
    )

    report = build_research_result_contract_sentinel(fields_path, results_dir)

    assert report["authority"] == "diagnostic_only"
    assert report["operator_gate_impact"] == "diagnostic_only"
    assert report["normal_apply_authority"] == "reports/operator_summary.json"
    assert report["source_status_apply_blocking"] is False
    assert report["summary"] == {
        "status": "clean",
        "field_contract_valid": True,
        "result_count": 1,
        "strict_valid_count": 1,
        "strict_invalid_count": 0,
        "seed_only_count": 1,
        "strong_promoting_count": 0,
        "no_op_validation_risk": False,
        "source_status_apply_blocking": False,
    }
    assert report["result_rows"][0]["deck_name"] == "ShadowPriest"
    assert report["result_rows"][0]["snapshot_kind"] == "seed_only"
    assert report["result_rows"][0]["strict_research_result_valid"] is True


def test_sentinel_surfaces_invalid_strong_result_without_blocking(
    tmp_path: Path,
) -> None:
    fields_path = tmp_path / "fields.yaml"
    fields_path.write_text(yaml.safe_dump(FIELDS), encoding="utf-8")
    results_dir = tmp_path / "results"
    _write_json(
        results_dir / "CtAPaladin.json",
        {
            "deck_name": "CtAPaladin",
            "archetype": "Wild Call to Arms Paladin",
            "current_deck_sources": [],
            "guide_sources": [],
            "source_strength": "exact_full_text_guide",
            "source_visibility": "full_text",
            "lowerable_claim_kinds": ["mulligan_keep"],
            "non_promoting_support": [],
            "default_only_runtime_surfaces": [],
            "first_missing_source_action": "none",
            "notes": "Missing freshness metadata must remain visible.",
        },
    )

    report = build_research_result_contract_sentinel(fields_path, results_dir)

    assert report["summary"]["status"] == "attention"
    assert report["summary"]["strict_invalid_count"] == 1
    assert report["source_status_apply_blocking"] is False
    assert report["result_rows"][0]["strict_research_result_valid"] is False
    assert "strong_requires_current_or_evergreen_freshness" in report["result_rows"][0]["strict_research_result_errors"]


def test_sentinel_detects_no_op_validation_risk_when_fields_are_malformed(
    tmp_path: Path,
) -> None:
    fields_path = tmp_path / "fields.yaml"
    fields_path.write_text("fields: []\n", encoding="utf-8")
    results_dir = tmp_path / "results"
    _write_json(
        results_dir / "PirateDH.json",
        {
            "deck_name": "PirateDH",
            "source_strength": "decklist_or_stats_only",
            "first_missing_source_action": "add_card_specific_source_claim",
        },
    )

    report = build_research_result_contract_sentinel(fields_path, results_dir)

    assert report["summary"]["status"] == "attention"
    assert report["summary"]["field_contract_valid"] is False
    assert report["summary"]["no_op_validation_risk"] is True
    assert report["source_status_apply_blocking"] is False
```

- [ ] **Step 2: Run the new tests and confirm they fail**

Run:

```powershell
python -m pytest -q tests/test_research_result_contract_sentinel.py
```

Expected: FAIL with `ModuleNotFoundError` because `hsconfig.research_result_contract_sentinel` does not exist yet.

- [ ] **Step 3: Implement the sentinel module**

Create `src/hsconfig/research_result_contract_sentinel.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from hsconfig.io import read_json
from hsconfig.research_result_contract import classify_research_result_contract
from hsconfig.research_result_validator import (
    validate_fields_yaml_payload,
    validate_research_result_payload,
)

NORMAL_APPLY_AUTHORITY = "reports/operator_summary.json"
DIAGNOSTIC_AUTHORITY = "diagnostic_only"


def build_research_result_contract_sentinel(
    fields_path: str | Path,
    results_dir: str | Path,
) -> dict[str, Any]:
    fields_file = Path(fields_path)
    result_root = Path(results_dir)
    fields_payload = _read_yaml_mapping(fields_file)
    fields_contract = validate_fields_yaml_payload(fields_payload)
    rows = [_result_row(path) for path in sorted(result_root.glob("*.json"))]
    strict_invalid_count = sum(
        1 for row in rows if row["strict_research_result_valid"] is False
    )
    seed_only_count = sum(1 for row in rows if row["snapshot_kind"] == "seed_only")
    strong_promoting_count = sum(
        1 for row in rows if row["canonical_promotion_allowed"] is True
    )
    no_op_validation_risk = (
        fields_contract["valid"] is False
        or int(fields_contract.get("field_count") or 0) == 0
    )
    status = (
        "clean"
        if (
            fields_contract["valid"] is True
            and rows
            and strict_invalid_count == 0
            and no_op_validation_risk is False
        )
        else "attention"
    )
    return {
        "schema_version": 1,
        "authority": DIAGNOSTIC_AUTHORITY,
        "operator_gate_impact": DIAGNOSTIC_AUTHORITY,
        "normal_apply_authority": NORMAL_APPLY_AUTHORITY,
        "fields_path": str(fields_file),
        "results_dir": str(result_root),
        "fields_contract": fields_contract,
        "result_rows": rows,
        "summary": {
            "status": status,
            "field_contract_valid": bool(fields_contract["valid"]),
            "result_count": len(rows),
            "strict_valid_count": len(rows) - strict_invalid_count,
            "strict_invalid_count": strict_invalid_count,
            "seed_only_count": seed_only_count,
            "strong_promoting_count": strong_promoting_count,
            "no_op_validation_risk": no_op_validation_risk,
            "source_status_apply_blocking": False,
        },
        "source_status_apply_blocking": False,
    }


def _read_yaml_mapping(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _result_row(path: Path) -> dict[str, Any]:
    payload = read_json(path)
    if not isinstance(payload, dict):
        payload = {}
    strict = validate_research_result_payload(payload)
    contract = classify_research_result_contract(payload)
    return {
        "path": str(path),
        "deck_name": str(payload.get("deck_name") or ""),
        "source_strength": str(payload.get("source_strength") or ""),
        "first_missing_source_action": str(
            payload.get("first_missing_source_action") or ""
        ),
        "snapshot_kind": str(contract["snapshot_kind"]),
        "contract_valid": bool(contract["contract_valid"]),
        "canonical_promotion_allowed": bool(
            strict["valid"] and contract["canonical_promotion_allowed"]
        ),
        "canonical_downgrade_allowed": False,
        "strict_research_result_valid": bool(strict["valid"]),
        "strict_research_result_errors": list(strict["errors"]),
        "strict_research_result_warnings": list(strict["warnings"]),
        "strict_research_result_field_count": int(strict["field_count"]),
        "lowerable_claim_kinds": list(strict["lowerable_claim_kinds"]),
        "source_status_apply_blocking": False,
    }
```

- [ ] **Step 4: Run sentinel tests**

Run:

```powershell
python -m pytest -q tests/test_research_result_contract_sentinel.py tests/test_research_result_validator.py tests/test_research_result_contract.py
```

Expected: PASS.

- [ ] **Step 5: Commit Task 2**

```powershell
git add src/hsconfig/research_result_contract_sentinel.py tests/test_research_result_contract_sentinel.py
git commit -m "feat: add research result contract sentinel"
```

---

### Task 3: Preflight Visibility Without New Gates

**Files:**
- Modify: `src/hsconfig/contract_preflight.py`
- Modify: `tests/test_contract_preflight.py`

**Interfaces:**
- Consumes:
  - `build_research_result_contract_sentinel(fields_path, results_dir)`
  - Existing `ResearchContextPreflight`
- Produces:
  - New `ResearchContextPreflight` fields:
    - `latest_research_result_contract_status: str`
    - `latest_research_result_contract_path: str`
    - `latest_research_result_contract_result_count: int`
    - `latest_research_result_contract_invalid_count: int`
    - `latest_research_result_contract_no_op_validation_risk: bool`
  - New top-level check:
    - `research_result_contract_sentinel_visible: bool`

- [ ] **Step 1: Write failing preflight tests**

Append to `tests/test_contract_preflight.py`:

```python
def test_contract_preflight_exposes_research_result_contract_sentinel() -> None:
    payload = build_contract_preflight(Path("."), git=_clean_git())
    research_context = payload["research_context"]

    assert payload["checks"]["research_result_contract_sentinel_visible"] is True
    assert research_context["latest_research_result_contract_status"] in {
        "clean",
        "attention",
        "not_found",
    }
    assert research_context["latest_research_result_contract_path"].startswith(
        "docs/research/"
    )
    assert isinstance(
        research_context["latest_research_result_contract_result_count"],
        int,
    )
    assert isinstance(
        research_context["latest_research_result_contract_invalid_count"],
        int,
    )
    assert research_context["source_status_apply_blocking"] is False
    assert payload["runtime_apply_authority"] == "reports/operator_summary.json"


def test_contract_preflight_research_result_attention_is_not_apply_blocking(
    tmp_path: Path,
) -> None:
    source_docs = Path("docs")
    target_docs = tmp_path / "docs"
    shutil.copytree(source_docs, target_docs)
    skill_root = tmp_path / ".agents" / "skills" / "hsconfig"
    shutil.copytree(Path(".agents") / "skills" / "hsconfig", skill_root)

    latest = target_docs / "research" / "9999-invalid-research"
    (latest / "results").mkdir(parents=True)
    (latest / "fields.yaml").write_text("fields: []\n", encoding="utf-8")
    (latest / "results" / "ShadowPriest.json").write_text(
        json.dumps(
            {
                "deck_name": "ShadowPriest",
                "source_strength": "SOURCE_BACKED_STRONG",
                "first_missing_source_action": "none",
            }
        ),
        encoding="utf-8",
    )

    payload = build_contract_preflight(
        tmp_path,
        git=_clean_git(),
        skill_install_root=_synced_install_root(tmp_path),
    )

    research_context = payload["research_context"]
    assert payload["checks"]["research_result_contract_sentinel_visible"] is True
    assert research_context["latest_research_result_contract_status"] == "attention"
    assert research_context["latest_research_result_contract_no_op_validation_risk"] is True
    assert research_context["source_status_apply_blocking"] is False
    assert payload["source_status_apply_blocking"] is False
    assert payload["runtime_apply_authority"] == "reports/operator_summary.json"
```

- [ ] **Step 2: Run preflight tests and confirm they fail**

Run:

```powershell
python -m pytest -q tests/test_contract_preflight.py::test_contract_preflight_exposes_research_result_contract_sentinel tests/test_contract_preflight.py::test_contract_preflight_research_result_attention_is_not_apply_blocking
```

Expected: FAIL because the preflight payload does not expose the sentinel fields yet.

- [ ] **Step 3: Implement preflight sentinel discovery**

Modify `src/hsconfig/contract_preflight.py`.

Add import:

```python
from hsconfig.research_result_contract_sentinel import (
    build_research_result_contract_sentinel,
)
```

Extend `EXPECTED_CHECK_KEYS`:

```python
    "research_result_contract_sentinel_visible",
```

Extend `ResearchContextPreflight`:

```python
    latest_research_result_contract_status: str
    latest_research_result_contract_path: str
    latest_research_result_contract_result_count: int
    latest_research_result_contract_invalid_count: int
    latest_research_result_contract_no_op_validation_risk: bool
```

Add helper:

```python
def _latest_research_result_contract(root: Path) -> dict[str, object]:
    research_root = root / "docs" / "research"
    candidates = [
        path.parent
        for path in research_root.glob("*/fields.yaml")
        if path.parent.joinpath("results").is_dir()
    ]
    if not candidates:
        return {
            "status": "not_found",
            "path": "",
            "result_count": 0,
            "invalid_count": 0,
            "no_op_validation_risk": False,
        }
    latest = max(candidates, key=lambda path: path.stat().st_mtime)
    sentinel = build_research_result_contract_sentinel(
        latest / "fields.yaml",
        latest / "results",
    )
    summary = sentinel["summary"]
    return {
        "status": str(summary["status"]),
        "path": _relative_posix(root, latest),
        "result_count": int(summary["result_count"]),
        "invalid_count": int(summary["strict_invalid_count"]),
        "no_op_validation_risk": bool(summary["no_op_validation_risk"]),
    }
```

In `build_research_context_preflight(...)`, compute:

```python
    latest_research_contract = _latest_research_result_contract(root)
```

Add the new fields to the returned `ResearchContextPreflight`:

```python
        latest_research_result_contract_status=str(
            latest_research_contract["status"]
        ),
        latest_research_result_contract_path=str(latest_research_contract["path"]),
        latest_research_result_contract_result_count=int(
            latest_research_contract["result_count"]
        ),
        latest_research_result_contract_invalid_count=int(
            latest_research_contract["invalid_count"]
        ),
        latest_research_result_contract_no_op_validation_risk=bool(
            latest_research_contract["no_op_validation_risk"]
        ),
```

Add the check:

```python
        "research_result_contract_sentinel_visible": (
            research_context.latest_research_result_contract_status
            in {"clean", "attention", "not_found"}
            and research_context.source_status_apply_blocking is False
        ),
```

- [ ] **Step 4: Run preflight tests**

Run:

```powershell
python -m pytest -q tests/test_contract_preflight.py
```

Expected: PASS.

- [ ] **Step 5: Commit Task 3**

```powershell
git add src/hsconfig/contract_preflight.py tests/test_contract_preflight.py
git commit -m "feat: surface research result sentinel in preflight"
```

---

### Task 4: Documentation And Skill Sync

**Files:**
- Modify: `.agents/skills/hsconfig/SKILL.md`
- Modify: `.agents/skills/hsconfig/references/workflow.md`
- Modify: `docs/operator/README.md`
- Modify: `docs/operator/source-backed-strong-closure.md`
- Test: `tests/test_skill_files.py`
- Test: `tests/test_docs_active_path.py`
- Test: `tests/test_operator_docs_contract_policy.py`

**Interfaces:**
- Consumes:
  - `configure_summary.json.handoff_contract`
  - `contract-preflight.research_context.latest_research_result_contract_*`
- Produces:
  - Operator docs that explain the new diagnostic-only surfaces without changing normal apply authority.
  - Installed skill synchronized via `scripts/sync_installed_skill.py`.

- [ ] **Step 1: Write failing docs/skill tests**

Add to `tests/test_skill_files.py`:

```python
def test_hsconfig_skill_mentions_handoff_contract_and_research_sentinel() -> None:
    text = Path(".agents/skills/hsconfig/SKILL.md").read_text(encoding="utf-8")

    assert "configure_summary.json.handoff_contract" in text
    assert "research-result sentinel" in text
    assert "diagnostic-only" in text
    assert "operator_summary.json remains the only normal apply authority" in text
```

Add to `tests/test_docs_active_path.py`:

```python
def test_operator_docs_describe_handoff_contract_without_second_gate() -> None:
    text = Path("docs/operator/README.md").read_text(encoding="utf-8")

    assert "configure_summary.json.handoff_contract" in text
    assert "diagnostic-only handoff proof" in text
    assert "does not replace reports/operator_summary.json" in text
    assert "research-result sentinel" in text
```

Add to `tests/test_operator_docs_contract_policy.py`:

```python
def test_source_closure_docs_keep_research_sentinel_non_promoting() -> None:
    text = Path("docs/operator/source-backed-strong-closure.md").read_text(
        encoding="utf-8"
    )

    assert "research-result sentinel" in text
    assert "cannot promote or downgrade" in text
    assert "source_status_apply_blocking=false" in text
```

- [ ] **Step 2: Run docs tests and confirm they fail**

Run:

```powershell
python -m pytest -q tests/test_skill_files.py::test_hsconfig_skill_mentions_handoff_contract_and_research_sentinel tests/test_docs_active_path.py::test_operator_docs_describe_handoff_contract_without_second_gate tests/test_operator_docs_contract_policy.py::test_source_closure_docs_keep_research_sentinel_non_promoting
```

Expected: FAIL because the new wording does not exist yet.

- [ ] **Step 3: Patch skill and operator docs**

Add this concise rule to `.agents/skills/hsconfig/SKILL.md` near the configure-summary rules:

```markdown
- After `configure`, `configure_summary.json.handoff_contract` is the compact diagnostic-only handoff proof: it summarizes `use_config_now`, single apply authority, no-default-only status, forbidden-surface status, source-to-runtime trace status, Darkbishop boundary, mechanic discipline, and the next report to open. It does not replace reports/operator_summary.json, cannot apply runtime files, and cannot turn source gaps into blockers. operator_summary.json remains the only normal apply authority.
- `contract-preflight.research_context.latest_research_result_contract_*` exposes the latest research-result sentinel status. The research-result sentinel is diagnostic-only: it validates HSConfig research-deep fields/results for honest source closure, but cannot promote or downgrade package status and keeps `source_status_apply_blocking=false`.
```

Add this concise rule to `.agents/skills/hsconfig/references/workflow.md` in the normal configure reading order:

```markdown
Read `configure_summary.json.acceptance_summary` first, then `configure_summary.json.handoff_contract` for the compact diagnostic-only proof, then `reports/operator_summary.json` as the single normal apply authority. The handoff contract is an operator projection only; it does not write runtime files and does not create another gate.
```

Add this paragraph to `docs/operator/README.md` near the configure summary section:

```markdown
`configure_summary.json.handoff_contract` is a diagnostic-only handoff proof for normal generated packages. It compresses the already-generated acceptance, config-proof, and config-quality facts into one small object: single authority, no-default-only status, forbidden normal surfaces, source-to-runtime trace status, Darkbishop boundary status, mechanic discipline, and the next report to open. It does not replace reports/operator_summary.json and it cannot grant or deny runtime writes.

`contract-preflight.research_context.latest_research_result_contract_*` exposes whether the latest research-deep result batch has HSConfig-valid fields and result payloads. This research-result sentinel is source-quality visibility only; it cannot promote, downgrade, block, or apply a package.
```

Add this paragraph to `docs/operator/source-backed-strong-closure.md`:

```markdown
The research-result sentinel validates `fields.yaml` and `results/*.json` from the latest research-deep batch against the HSConfig result contract. It can mark stale, seed-only, malformed, or non-promoting research snapshots as attention, but it cannot promote or downgrade canonical package status, cannot replace `reports/operator_summary.json`, and keeps `source_status_apply_blocking=false`.
```

- [ ] **Step 4: Sync installed skill**

Run:

```powershell
python scripts\sync_installed_skill.py
```

Expected: exits `0`.

- [ ] **Step 5: Run docs and skill tests**

Run:

```powershell
python -m pytest -q tests/test_skill_files.py tests/test_docs_active_path.py tests/test_operator_docs_contract_policy.py
```

Expected: PASS.

- [ ] **Step 6: Commit Task 4**

```powershell
git add .agents/skills/hsconfig/SKILL.md .agents/skills/hsconfig/references/workflow.md docs/operator/README.md docs/operator/source-backed-strong-closure.md tests/test_skill_files.py tests/test_docs_active_path.py tests/test_operator_docs_contract_policy.py
git commit -m "docs: document handoff contract and research sentinel"
```

---

### Task 5: Guardrail Suite Integration

**Files:**
- Modify: `scripts/check_contract_guardrails.py`
- Create: `tests/test_contract_guardrail_script.py`
- Test: `scripts/check_contract_guardrails.py`

**Interfaces:**
- Consumes:
  - `tests/test_configure_handoff_contract.py`
  - `tests/test_research_result_contract_sentinel.py`
- Produces:
  - Guardrail script that fails if either new proof layer drifts.

- [ ] **Step 1: Write failing script expectation**

Create `tests/test_contract_guardrail_script.py`:

```python
from __future__ import annotations

from scripts.check_contract_guardrails import FOCUSED_CONTRACT_TESTS


def test_guardrail_suite_includes_handoff_and_research_sentinel_tests() -> None:
    assert "tests/test_configure_handoff_contract.py" in FOCUSED_CONTRACT_TESTS
    assert "tests/test_research_result_contract_sentinel.py" in FOCUSED_CONTRACT_TESTS
```

- [ ] **Step 2: Run the new script test and confirm it fails**

Run:

```powershell
python -m pytest -q tests/test_contract_guardrail_script.py
```

Expected: FAIL because the guardrail tuple does not include the two new files.

- [ ] **Step 3: Update focused guardrail tests**

Modify `scripts/check_contract_guardrails.py` and add the two tests to `FOCUSED_CONTRACT_TESTS`:

```python
    "tests/test_configure_handoff_contract.py",
    "tests/test_research_result_contract_sentinel.py",
```

- [ ] **Step 4: Run guardrail script test**

Run:

```powershell
python -m pytest -q tests/test_contract_guardrail_script.py
```

Expected: PASS.

- [ ] **Step 5: Run focused guardrails**

Run:

```powershell
python scripts\check_contract_guardrails.py
```

Expected:

```text
OK: installed skill sync
OK: contract spine sentinel
OK: focused contract boundary tests
```

- [ ] **Step 6: Commit Task 5**

```powershell
git add scripts/check_contract_guardrails.py tests/test_contract_guardrail_script.py
git commit -m "test: add handoff and research sentinel guardrails"
```

---

### Task 6: Final Verification And Clean Worktree

**Files:**
- Verify only.

**Interfaces:**
- Consumes:
  - All changes from Tasks 1-5.
- Produces:
  - Current, clean, verified branch.

- [ ] **Step 1: Run targeted suite**

Run:

```powershell
python -m pytest -q tests/test_configure_handoff_contract.py tests/test_research_result_contract_sentinel.py tests/test_contract_preflight.py tests/test_research_result_validator.py tests/test_research_result_contract.py tests/test_strong_closure_dossier.py
```

Expected: PASS.

- [ ] **Step 2: Run docs/skill suite**

Run:

```powershell
python -m pytest -q tests/test_skill_files.py tests/test_docs_active_path.py tests/test_operator_docs_contract_policy.py tests/test_skill_sync.py
```

Expected: PASS.

- [ ] **Step 3: Run contract preflight**

Run:

```powershell
python -m hsconfig.cli contract-preflight --repo-root . --json
```

Expected:

```json
{
  "runtime_apply_authority": "reports/operator_summary.json",
  "source_status_apply_blocking": false,
  "diagnostic_only": true
}
```

The top-level `status` may be `PASS` or `ATTENTION` depending on diagnostic research-result freshness, but it must not imply runtime apply blocking.

- [ ] **Step 4: Run full focused guardrail**

Run:

```powershell
python scripts\check_contract_guardrails.py
```

Expected:

```text
OK: installed skill sync
OK: contract spine sentinel
OK: focused contract boundary tests
```

- [ ] **Step 5: Check repository currentness**

Run:

```powershell
python scripts\check_hsconfig_currentness.py --cwd . --json
```

Expected:

```json
{
  "behind_origin_main": 0,
  "dirty": false,
  "clean_for_runtime_work": true
}
```

- [ ] **Step 6: Check git status**

Run:

```powershell
git status --short --branch
```

Expected: branch line only, no changed or untracked files.

---

## Self-Review

**Spec coverage:** The plan implements the two recommended improvements: compact configure handoff proof and strict research-result sentinel visibility. It preserves no-block generation, single apply authority, no default-only silence, Darkbishop boundary, and no HSTuner/log dependency.

**Placeholder scan:** No incomplete marker or unspecified test task remains. Each task names exact files, functions, commands, and expected results.

**Type consistency:** The new public helper signatures are stable:

```python
def _build_handoff_contract(
    *,
    operator_summary: Mapping[str, Any],
    acceptance_summary: Mapping[str, Any],
    config_proof_summary: Mapping[str, Any],
    config_quality_summary: Mapping[str, Any],
) -> dict[str, Any]:
    ...

def build_research_result_contract_sentinel(
    fields_path: str | Path,
    results_dir: str | Path,
) -> dict[str, Any]:
    ...
```

**Risk boundary:** The plan adds proof and diagnostics only. It does not alter runtime card heuristics, package validity, apply policy, or HearthRanger runtime output semantics.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-22-hsconfig-handoff-contract-research-sentinel.md`.

Two execution options:

1. **Subagent-Driven (recommended)** - Dispatch a fresh subagent per task, review between tasks, fast iteration.

2. **Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints.

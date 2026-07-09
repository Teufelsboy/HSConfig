# HSConfig Config Richness Output Competence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a non-blocking `config_usefulness` / output-competence layer so HSConfig shows whether a generated load-safe package is genuinely rich across Mulligan, GlobalValues, CardID behavior, and Combo.

**Architecture:** Keep `reports/operator_summary.json` as the only normal operator gate. Add a small helper that derives usefulness from existing prepare-time reports, then integrate it into `build_operator_summary()` without changing `technical_status`, `runtime_apply_mode`, `runtime_apply_allowed`, `next_action`, or apply-gate behavior.

**Tech Stack:** Python 3, existing `hsconfig` package, pytest, JSON report fixtures, no new runtime dependencies.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig` for `Teufelsboy/HSConfig`.
- Do not add HSTuner, replay parsing, winrate, HDT, Power.log, or post-run evidence to HSConfig.
- Do not add new normal-path runtime files such as `Presume.json` or `Concede.json`.
- Do not make richness a hard apply blocker. Only technical invalidity blocks.
- Keep `reports/operator_summary.json` the normal operator entrypoint.
- Keep packages valid and load-safe even when `config_usefulness.status` is `usable_with_targeted_gaps` or `load_safe_but_thin`.
- Use existing reports as data sources before adding new artifacts.

---

## File Structure

- Create `src/hsconfig/config_usefulness.py`
  - Owns all config-richness classification logic.
  - Produces one stable dictionary for `operator_summary.json`.
  - Does not import apply-gate, runtime apply, CLI, or package writer code.

- Modify `src/hsconfig/operator_summary.py`
  - Accepts optional pre-run report payloads.
  - Calls `build_config_usefulness()`.
  - Adds `summary["config_usefulness"]`.
  - Keeps all existing gate fields unchanged.

- Modify `src/hsconfig/package_builder.py`
  - Passes `mulligan_plan`, `card_behavior_plan`, `combo_plan`, and `globalvalues["profile"]` into `build_operator_summary()`.
  - Does not write a new normal report unless a later task proves it is needed.

- Modify `src/hsconfig/report_ownership.py`
  - Documents that `operator_summary.json` owns `config_usefulness`.

- Modify `docs/operator/README.md`
  - Adds a short explanation of load safety vs. config richness.

- Modify `docs/operator/universal-wild-no-block-contract.md`
  - States that richness is descriptive and non-blocking.

- Test `tests/test_config_usefulness.py`
  - Unit tests for the helper statuses and first-gap selection.

- Modify `tests/test_operator_summary.py`
  - Verifies `config_usefulness` is emitted and does not affect apply permission.

- Modify `tests/test_apply_gate.py`
  - Verifies apply-gate ignores `config_usefulness`.

- Create `tests/test_output_competence_matrix.py`
  - Uses the representative fixture matrix to assert that output-competence signals are visible.
  - Keeps `CuteWarrior` out of representative competence expectations.

- Modify `tests/test_skill_files.py`
  - Verifies docs explain `config_usefulness` without introducing HSTuner/replay scope.

---

### Task 1: Add Config Usefulness Helper

**Files:**
- Create: `src/hsconfig/config_usefulness.py`
- Create: `tests/test_config_usefulness.py`

**Interfaces:**
- Consumes:
  - `technical_status: str`
  - `semantic_status: str`
  - `config_readiness_summary: dict[str, Any] | None`
  - `config_readiness_report: dict[str, Any] | None`
  - `mulligan_plan_report: dict[str, Any] | None`
  - `card_behavior_plan_report: dict[str, Any] | None`
  - `combo_plan_report: dict[str, Any] | None`
  - `globalvalues_profile_report: dict[str, Any] | None`
- Produces:
  - `build_config_usefulness(...) -> dict[str, Any]`
  - Returned statuses: `guide_aligned`, `usable_with_targeted_gaps`, `load_safe_but_thin`, `invalid_package`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_config_usefulness.py`:

```python
from hsconfig.config_usefulness import build_config_usefulness


def test_config_usefulness_marks_rich_source_backed_package_guide_aligned():
    payload = build_config_usefulness(
        technical_status="VALID_PACKAGE",
        semantic_status="SOURCE_BACKED_STRONG",
        config_readiness_summary={
            "total_cards": 3,
            "runtime_emitted": 3,
            "mulligan_only": 0,
            "globalvalues_only": 0,
            "report_only_supported": 0,
            "generic_low_confidence": 0,
            "cards_needing_guide_claims": 0,
            "cards_needing_runtime_surface": 0,
            "cards_needing_mulligan_claims": 0,
            "cards_needing_combo_sequence": 0,
            "cards_needing_condition_lowering": 0,
            "cards_needing_mechanic_lowering": 0,
        },
        config_readiness_report={"cards": {}},
        mulligan_plan_report={
            "rules": [{"action": "keep", "card": "CARD_A"}],
            "suppressed_rules": [],
            "quality": {"has_concrete_keeps": True},
        },
        card_behavior_plan_report={
            "rows": [
                {
                    "card_id": "CARD_A",
                    "surface_family": "CARDID.json",
                    "meaningful_runtime_surface": True,
                    "behavior_block": {"BeforePlayCardBonus": {"values": []}},
                },
                {
                    "card_id": "CARD_B",
                    "surface_family": "CARDID.json",
                    "meaningful_runtime_surface": True,
                    "behavior_block": {"OnBoardBonus": {"values": []}},
                },
            ]
        },
        combo_plan_report={"combos": [{"cards": ["CARD_A", "CARD_B"]}], "suppressed": []},
        globalvalues_profile_report={
            "changed_keys": ["FirstTurnValueWeight", "SecondTurnValueWeight"],
            "unchanged_keys": ["EnemySecretValue"],
        },
    )

    assert payload["status"] == "guide_aligned"
    assert payload["runtime_permission_impact"] == "none"
    assert payload["surfaces"]["mulligan"]["status"] == "rich"
    assert payload["surfaces"]["cardid_behavior"]["meaningful_cardid_row_count"] == 2
    assert payload["surfaces"]["globalvalues"]["changed_key_count"] == 2
    assert payload["surfaces"]["combo"]["status"] == "rich"
    assert payload["first_usefulness_gap"] == "none"


def test_config_usefulness_marks_source_gap_package_usable_with_targeted_gaps():
    payload = build_config_usefulness(
        technical_status="VALID_PACKAGE",
        semantic_status="VALID_BUT_NOT_GUIDE_STRONG",
        config_readiness_summary={
            "total_cards": 10,
            "runtime_emitted": 8,
            "mulligan_only": 1,
            "globalvalues_only": 0,
            "report_only_supported": 1,
            "generic_low_confidence": 0,
            "cards_needing_guide_claims": 0,
            "cards_needing_runtime_surface": 0,
            "cards_needing_mulligan_claims": 1,
            "cards_needing_combo_sequence": 0,
            "cards_needing_condition_lowering": 0,
            "cards_needing_mechanic_lowering": 0,
        },
        config_readiness_report={"cards": {}},
        mulligan_plan_report={
            "rules": [{"action": "keep", "card": "CARD_A"}],
            "suppressed_rules": [{"card_id": "CARD_B", "reason": "claim_not_runtime_lowerable"}],
            "quality": {"has_concrete_keeps": True},
        },
        card_behavior_plan_report={"rows": []},
        combo_plan_report={"combos": [], "suppressed": []},
        globalvalues_profile_report={"changed_keys": ["FirstTurnValueWeight"]},
    )

    assert payload["status"] == "usable_with_targeted_gaps"
    assert payload["first_usefulness_gap"] == "mulligan_gap"
    assert payload["next_report_to_open"] == "reports/mulligan_plan_report.json"


def test_config_usefulness_marks_valid_sparse_package_load_safe_but_thin():
    payload = build_config_usefulness(
        technical_status="VALID_PACKAGE",
        semantic_status="STATIC_SEMANTICS_USABLE",
        config_readiness_summary={
            "total_cards": 10,
            "runtime_emitted": 1,
            "mulligan_only": 0,
            "globalvalues_only": 0,
            "report_only_supported": 8,
            "generic_low_confidence": 1,
            "cards_needing_guide_claims": 1,
            "cards_needing_runtime_surface": 5,
            "cards_needing_mulligan_claims": 0,
            "cards_needing_combo_sequence": 0,
            "cards_needing_condition_lowering": 0,
            "cards_needing_mechanic_lowering": 0,
        },
        config_readiness_report={"cards": {}},
        mulligan_plan_report={"rules": [], "suppressed_rules": [], "quality": {"has_concrete_keeps": False}},
        card_behavior_plan_report={"rows": []},
        combo_plan_report={"combos": [], "suppressed": []},
        globalvalues_profile_report={"changed_keys": [], "unchanged_keys": ["EnemySecretValue"]},
    )

    assert payload["status"] == "load_safe_but_thin"
    assert payload["surfaces"]["mulligan"]["default_only"] is True
    assert payload["surfaces"]["globalvalues"]["status"] == "thin"
    assert payload["surfaces"]["cardid_behavior"]["status"] == "thin"
    assert payload["first_usefulness_gap"] == "runtime_surface_gap"


def test_config_usefulness_marks_invalid_package_without_affecting_gate_fields():
    payload = build_config_usefulness(
        technical_status="INVALID_PACKAGE",
        semantic_status="INVALID_PACKAGE",
        config_readiness_summary={},
        config_readiness_report={},
        mulligan_plan_report={},
        card_behavior_plan_report={},
        combo_plan_report={},
        globalvalues_profile_report={},
    )

    assert payload["status"] == "invalid_package"
    assert payload["headline"] == "Package is technically invalid; config richness is not evaluated."
    assert payload["runtime_permission_impact"] == "none"
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_config_usefulness.py -q
```

Expected: fail during import with `ModuleNotFoundError: No module named 'hsconfig.config_usefulness'`.

- [ ] **Step 3: Implement `src/hsconfig/config_usefulness.py`**

Create `src/hsconfig/config_usefulness.py`:

```python
from __future__ import annotations

from typing import Any


GAP_REPORTS = {
    "mulligan_gap": "reports/mulligan_plan_report.json",
    "runtime_surface_gap": "reports/per_card_config_readiness_report.json",
    "combo_gap": "reports/combo_plan_report.json",
    "condition_gap": "reports/per_card_config_readiness_report.json",
    "mechanic_gap": "reports/per_card_config_readiness_report.json",
    "guide_claim_gap": "reports/source_claim_gap_report.json",
    "globalvalues_thin": "reports/global_values_key_profile_report.json",
    "cardid_thin": "reports/card_behavior_plan_report.json",
}


def build_config_usefulness(
    *,
    technical_status: str,
    semantic_status: str,
    config_readiness_summary: dict[str, Any] | None,
    config_readiness_report: dict[str, Any] | None = None,
    mulligan_plan_report: dict[str, Any] | None = None,
    card_behavior_plan_report: dict[str, Any] | None = None,
    combo_plan_report: dict[str, Any] | None = None,
    globalvalues_profile_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    summary = config_readiness_summary or {}
    if technical_status != "VALID_PACKAGE":
        return {
            "schema_version": 1,
            "status": "invalid_package",
            "headline": "Package is technically invalid; config richness is not evaluated.",
            "runtime_permission_impact": "none",
            "surfaces": {},
            "first_usefulness_gap": "technical_invalid",
            "next_report_to_open": "reports/validation_report.json",
        }

    mulligan = _mulligan_surface(mulligan_plan_report or {})
    cardid = _cardid_surface(card_behavior_plan_report or {}, summary)
    combo = _combo_surface(combo_plan_report or {}, summary)
    globalvalues = _globalvalues_surface(globalvalues_profile_report or {})
    first_gap = _first_gap(summary, mulligan, cardid, combo, globalvalues)
    status = _overall_status(
        semantic_status=semantic_status,
        first_gap=first_gap,
        summary=summary,
        mulligan=mulligan,
        cardid=cardid,
        combo=combo,
        globalvalues=globalvalues,
    )

    return {
        "schema_version": 1,
        "status": status,
        "headline": _headline(status, first_gap),
        "runtime_permission_impact": "none",
        "surfaces": {
            "mulligan": mulligan,
            "globalvalues": globalvalues,
            "cardid_behavior": cardid,
            "combo": combo,
        },
        "first_usefulness_gap": first_gap,
        "next_report_to_open": GAP_REPORTS.get(first_gap, "reports/operator_summary.json"),
    }


def _mulligan_surface(report: dict[str, Any]) -> dict[str, Any]:
    rules = _list(report.get("rules"))
    suppressed = _list(report.get("suppressed_rules"))
    quality = report.get("quality", {})
    has_concrete_keeps = bool(quality.get("has_concrete_keeps")) if isinstance(quality, dict) else False
    default_only = not rules and not suppressed and not has_concrete_keeps
    if has_concrete_keeps or rules:
        status = "rich"
    elif suppressed:
        status = "report_only"
    else:
        status = "thin"
    return {
        "status": status,
        "rule_count": len(rules),
        "suppressed_rule_count": len(suppressed),
        "has_concrete_keeps": has_concrete_keeps,
        "default_only": default_only,
    }


def _cardid_surface(report: dict[str, Any], summary: dict[str, Any]) -> dict[str, Any]:
    rows = _list(report.get("rows"))
    meaningful_rows = [
        row
        for row in rows
        if isinstance(row, dict)
        and row.get("meaningful_runtime_surface") is True
        and bool(row.get("behavior_block"))
    ]
    cards = sorted({str(row.get("card_id")) for row in meaningful_rows if row.get("card_id")})
    report_only_supported = _int(summary.get("report_only_supported"))
    runtime_emitted = _int(summary.get("runtime_emitted"))
    status = "rich" if meaningful_rows else "thin"
    if not meaningful_rows and report_only_supported > 0:
        status = "report_only"
    return {
        "status": status,
        "meaningful_cardid_row_count": len(meaningful_rows),
        "cards_with_meaningful_cardid_rows": len(cards),
        "runtime_emitted_card_count": runtime_emitted,
        "report_only_supported_count": report_only_supported,
    }


def _combo_surface(report: dict[str, Any], summary: dict[str, Any]) -> dict[str, Any]:
    combos = _list(report.get("combos"))
    suppressed = _list(report.get("suppressed"))
    gap_count = _int(summary.get("cards_needing_combo_sequence"))
    combo_expected = bool(combos or suppressed or gap_count)
    if combos:
        status = "rich"
    elif not combo_expected:
        status = "not_expected"
    elif suppressed:
        status = "report_only"
    else:
        status = "thin"
    return {
        "status": status,
        "combo_expected": combo_expected,
        "combo_row_count": len(combos),
        "suppressed_combo_claim_count": len(suppressed),
    }


def _globalvalues_surface(report: dict[str, Any]) -> dict[str, Any]:
    changed_keys = _list(report.get("changed_keys"))
    unchanged_keys = _list(report.get("unchanged_keys"))
    profiled_key_count = len(changed_keys) + len(unchanged_keys)
    return {
        "status": "rich" if changed_keys else "thin",
        "changed_key_count": len(changed_keys),
        "unchanged_key_count": len(unchanged_keys),
        "profiled_key_count": profiled_key_count,
    }


def _first_gap(
    summary: dict[str, Any],
    mulligan: dict[str, Any],
    cardid: dict[str, Any],
    combo: dict[str, Any],
    globalvalues: dict[str, Any],
) -> str:
    if _int(summary.get("cards_needing_runtime_surface")):
        return "runtime_surface_gap"
    if _int(summary.get("cards_needing_combo_sequence")) or combo["status"] in {"thin", "report_only"} and combo["combo_expected"]:
        return "combo_gap"
    if _int(summary.get("cards_needing_condition_lowering")):
        return "condition_gap"
    if _int(summary.get("cards_needing_mechanic_lowering")):
        return "mechanic_gap"
    if _int(summary.get("cards_needing_mulligan_claims")) or mulligan["status"] in {"thin", "report_only"}:
        return "mulligan_gap"
    if _int(summary.get("cards_needing_guide_claims")) or _int(summary.get("generic_low_confidence")):
        return "guide_claim_gap"
    if cardid["status"] in {"thin", "report_only"} and _int(summary.get("runtime_emitted")) == 0:
        return "cardid_thin"
    if globalvalues["status"] == "thin":
        return "globalvalues_thin"
    return "none"


def _overall_status(
    *,
    semantic_status: str,
    first_gap: str,
    summary: dict[str, Any],
    mulligan: dict[str, Any],
    cardid: dict[str, Any],
    combo: dict[str, Any],
    globalvalues: dict[str, Any],
) -> str:
    if first_gap == "none" and semantic_status == "SOURCE_BACKED_STRONG":
        return "guide_aligned"
    severe_sparse = (
        _int(summary.get("runtime_emitted")) <= 1
        and mulligan["status"] == "thin"
        and cardid["status"] in {"thin", "report_only"}
        and globalvalues["status"] == "thin"
    )
    if severe_sparse:
        return "load_safe_but_thin"
    return "usable_with_targeted_gaps"


def _headline(status: str, first_gap: str) -> str:
    if status == "guide_aligned":
        return "Package is load-safe and config-rich across the visible pre-run surfaces."
    if status == "usable_with_targeted_gaps":
        return f"Package is load-safe and usable, with the first usefulness gap at {first_gap}."
    if status == "load_safe_but_thin":
        return f"Package is load-safe, but config richness is thin; first gap is {first_gap}."
    return "Package richness status is unavailable."


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
```

- [ ] **Step 4: Run helper tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_config_usefulness.py -q
```

Expected: `4 passed`.

- [ ] **Step 5: Commit**

```powershell
git add src/hsconfig/config_usefulness.py tests/test_config_usefulness.py
git commit -m "feat: add config usefulness summary helper"
```

---

### Task 2: Integrate Config Usefulness Into Operator Summary

**Files:**
- Modify: `src/hsconfig/operator_summary.py`
- Modify: `src/hsconfig/package_builder.py`
- Modify: `tests/test_operator_summary.py`
- Modify: `tests/test_apply_gate.py`

**Interfaces:**
- Consumes:
  - `build_config_usefulness()` from Task 1.
  - Existing prepare reports created in `build_package_payload()`.
- Produces:
  - `operator_summary["config_usefulness"]`.
  - No apply-gate field changes.

- [ ] **Step 1: Add failing operator-summary tests**

Append to `tests/test_operator_summary.py`:

```python
def test_operator_summary_includes_nonblocking_config_usefulness():
    summary = build_operator_summary(
        deck_name="UsefulDeck",
        deck_code="AAE=",
        technical_validation={"status": "passed", "errors": []},
        guide_source_depth={
            "source_depth_status": "source_backed",
            "claim_count": 3,
            "source_evidence": {"warnings_count": 0},
        },
        unsupported_conditions=[],
        globalvalue_authority={"blocked_until_runtime_evidence": []},
        generated_files=[
            "CustomConfig/usefuldeck/GlobalValues.json",
            "CustomConfig/usefuldeck/Mulligan.json",
            "CustomConfig/usefuldeck/CARD_A.json",
        ],
        claim_coverage_report={
            "summary": {"guide_backed": 1, "static_semantics_backfilled": 0, "uncovered_low_confidence": 0},
            "uncovered_cards": [],
        },
        config_readiness_summary={
            "total_cards": 1,
            "runtime_emitted": 1,
            "mulligan_only": 0,
            "globalvalues_only": 0,
            "report_only_supported": 0,
            "generic_low_confidence": 0,
            "cards_needing_guide_claims": 0,
            "cards_needing_runtime_surface": 0,
            "cards_needing_mulligan_claims": 0,
            "cards_needing_combo_sequence": 0,
            "cards_needing_condition_lowering": 0,
            "cards_needing_mechanic_lowering": 0,
        },
        claim_conflict_report={"conflict_count": 0, "conflicts": []},
        mulligan_plan_report={
            "rules": [{"action": "keep", "card": "CARD_A"}],
            "suppressed_rules": [],
            "quality": {"has_concrete_keeps": True},
        },
        card_behavior_plan_report={
            "rows": [
                {
                    "card_id": "CARD_A",
                    "surface_family": "CARDID.json",
                    "meaningful_runtime_surface": True,
                    "behavior_block": {"BeforePlayCardBonus": {"values": []}},
                }
            ]
        },
        combo_plan_report={"combos": [], "suppressed": []},
        globalvalues_profile_report={"changed_keys": ["FirstTurnValueWeight"]},
    )

    assert summary["config_usefulness"]["status"] == "guide_aligned"
    assert summary["config_usefulness"]["runtime_permission_impact"] == "none"
    assert summary["technical_status"] == "VALID_PACKAGE"
    assert summary["runtime_apply_mode"] == "load_safe_apply"
    assert summary["runtime_apply_allowed"] is True


def test_operator_summary_thin_usefulness_does_not_block_apply():
    summary = build_operator_summary(
        deck_name="ThinDeck",
        deck_code="AAE=",
        technical_validation={"status": "passed", "errors": []},
        guide_source_depth={"source_depth_status": "static_semantics_only", "claim_count": 0},
        unsupported_conditions=[],
        globalvalue_authority={"blocked_until_runtime_evidence": []},
        generated_files=["CustomConfig/thindeck/GlobalValues.json", "CustomConfig/thindeck/Mulligan.json"],
        config_readiness_summary={
            "total_cards": 10,
            "runtime_emitted": 1,
            "mulligan_only": 0,
            "globalvalues_only": 0,
            "report_only_supported": 8,
            "generic_low_confidence": 1,
            "cards_needing_guide_claims": 1,
            "cards_needing_runtime_surface": 5,
            "cards_needing_mulligan_claims": 0,
            "cards_needing_combo_sequence": 0,
            "cards_needing_condition_lowering": 0,
            "cards_needing_mechanic_lowering": 0,
        },
        mulligan_plan_report={"rules": [], "suppressed_rules": [], "quality": {"has_concrete_keeps": False}},
        card_behavior_plan_report={"rows": []},
        combo_plan_report={"combos": [], "suppressed": []},
        globalvalues_profile_report={"changed_keys": []},
    )

    assert summary["config_usefulness"]["status"] == "load_safe_but_thin"
    assert summary["next_action"] == "READY_TO_APPLY_WITH_WARNINGS"
    assert summary["apply_policy"] == "ALLOWED_WITH_WARNINGS"
    assert summary["runtime_apply_allowed"] is True
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_operator_summary.py::test_operator_summary_includes_nonblocking_config_usefulness tests/test_operator_summary.py::test_operator_summary_thin_usefulness_does_not_block_apply -q
```

Expected: fail with `TypeError: build_operator_summary() got an unexpected keyword argument 'mulligan_plan_report'` or missing `config_usefulness`.

- [ ] **Step 3: Modify `src/hsconfig/operator_summary.py`**

Add the import near the top:

```python
from hsconfig.config_usefulness import build_config_usefulness
```

Extend `build_operator_summary()` parameters:

```python
    mulligan_plan_report: dict[str, Any] | None = None,
    card_behavior_plan_report: dict[str, Any] | None = None,
    combo_plan_report: dict[str, Any] | None = None,
    globalvalues_profile_report: dict[str, Any] | None = None,
```

After `semantic_blockers = _semantic_blockers(...)`, add:

```python
    config_usefulness = build_config_usefulness(
        technical_status=technical_status,
        semantic_status=semantic_status,
        config_readiness_summary=effective_config_readiness_summary,
        config_readiness_report=config_readiness_report or {},
        mulligan_plan_report=mulligan_plan_report or {},
        card_behavior_plan_report=card_behavior_plan_report or {},
        combo_plan_report=combo_plan_report or {},
        globalvalues_profile_report=globalvalues_profile_report or {},
    )
```

Add to the `summary` dict after `semantic_blockers`:

```python
        "config_usefulness": config_usefulness,
```

- [ ] **Step 4: Modify `src/hsconfig/package_builder.py`**

In `operator_summary_kwargs`, add:

```python
        "mulligan_plan_report": mulligan_plan,
        "card_behavior_plan_report": card_behavior_plan,
        "combo_plan_report": combo_plan,
        "globalvalues_profile_report": globalvalues["profile"],
```

- [ ] **Step 5: Add apply-gate regression test**

Append to `tests/test_apply_gate.py`:

```python
def test_apply_gate_ignores_config_usefulness_when_package_is_load_safe(tmp_path: Path):
    package = tmp_path / "package"
    deck_dir = package / "CustomConfig" / "deck"
    deck_dir.mkdir(parents=True)
    (deck_dir / "GlobalValues.json").write_text("{}", encoding="utf-8")
    (deck_dir / "Mulligan.json").write_text("{}", encoding="utf-8")
    _write_operator_summary(
        package,
        {
            "technical_status": "VALID_PACKAGE",
            "runtime_apply_mode": "load_safe_apply",
            "runtime_apply_allowed": True,
            "runtime_apply_requires_flag": None,
            "generated_files": [
                "CustomConfig/deck/GlobalValues.json",
                "CustomConfig/deck/Mulligan.json",
            ],
            "config_usefulness": {
                "status": "load_safe_but_thin",
                "runtime_permission_impact": "none",
            },
        },
    )

    gate = evaluate_apply_gate(package)

    assert gate["allowed"] is True
    assert gate["reasons"] == []
```

Use the existing helper/import names in `tests/test_apply_gate.py`; if the file imports `evaluate_apply_gate` under a different name, use the existing name rather than adding a duplicate import.

- [ ] **Step 6: Run focused tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_config_usefulness.py tests/test_operator_summary.py tests/test_apply_gate.py -q
```

Expected: all selected tests pass.

- [ ] **Step 7: Commit**

```powershell
git add src/hsconfig/operator_summary.py src/hsconfig/package_builder.py tests/test_operator_summary.py tests/test_apply_gate.py
git commit -m "feat: expose config usefulness in operator summary"
```

---

### Task 3: Add Output Competence Matrix Proof

**Files:**
- Create: `tests/test_output_competence_matrix.py`
- Modify: `docs/operator/archetype-fixture-matrix.json`
- Modify: `docs/operator/supplemental-proof-decks.json`

**Interfaces:**
- Consumes:
  - CLI `main(["prepare", ...])`
  - `docs/operator/archetype-fixture-matrix.json`
  - source document fixtures under `tests/fixtures/source_documents_*_strong.json`
- Produces:
  - A representative matrix test that proves `config_usefulness` visibility for the 11 representative decks.
  - Explicit supplemental treatment for `CuteWarrior`.

- [ ] **Step 1: Write the failing matrix test**

Create `tests/test_output_competence_matrix.py`:

```python
import json
from pathlib import Path

import pytest

from hsconfig.cli import main


SOURCE_DOCS = {
    "ShadowPriest": "tests/fixtures/source_documents_shadowpriest_strong.json",
    "CtAPaladin": "tests/fixtures/source_documents_ctapaladin_strong.json",
    "PirateRogue": "tests/fixtures/source_documents_piraterogue_strong.json",
    "BigShaman": "tests/fixtures/source_documents_bigshaman_strong.json",
    "Discolock": "tests/fixtures/source_documents_discolock_strong.json",
    "TreantDruid": "tests/fixtures/source_documents_treantdruid_strong.json",
    "Kingslayer": "tests/fixtures/source_documents_kingslayer_strong.json",
    "ImbueMage": "tests/fixtures/source_documents_imbuemage_strong.json",
    "MechPala": "tests/fixtures/source_documents_mechpala_strong.json",
    "Boarlock": "tests/fixtures/source_documents_boarlock_strong.json",
    "PirateDH": "tests/fixtures/source_documents_piratedh_strong.json",
}


def _representative_decks() -> list[dict]:
    matrix = json.loads(
        Path("docs/operator/archetype-fixture-matrix.json").read_text(encoding="utf-8")
    )
    return [
        row
        for row in matrix["decks"]
        if row["fixture_stage"] in {"core_source_backed_fixture", "source_informed_valid_fixture"}
    ]


@pytest.mark.parametrize("deck", _representative_decks(), ids=lambda row: row["deck_name"])
def test_representative_decks_expose_output_competence_summary(
    tmp_path: Path,
    capsys,
    monkeypatch,
    deck: dict,
):
    monkeypatch.setattr("hsconfig.package_builder.fetch_latest_cards", lambda timeout=10.0: [])
    out = tmp_path / deck["deck_name"]
    args = [
        "prepare",
        "--deck-name",
        deck["deck_name"],
        "--deck-code",
        deck["deck_code"],
        "--runtime-root",
        str(tmp_path / "runtime"),
        "--out",
        str(out),
        "--source-documents-json",
        SOURCE_DOCS[deck["deck_name"]],
        "--json",
    ]

    code = main(args)
    capsys.readouterr()
    operator = json.loads((out / "reports" / "operator_summary.json").read_text(encoding="utf-8"))
    usefulness = operator["config_usefulness"]

    assert code == 0
    assert operator["technical_status"] == "VALID_PACKAGE"
    assert operator["runtime_apply_allowed"] is True
    assert usefulness["runtime_permission_impact"] == "none"
    assert usefulness["status"] in {
        "guide_aligned",
        "usable_with_targeted_gaps",
        "load_safe_but_thin",
    }
    assert usefulness["surfaces"]["mulligan"]["status"] in {"rich", "thin", "report_only"}
    assert "changed_key_count" in usefulness["surfaces"]["globalvalues"]
    assert "meaningful_cardid_row_count" in usefulness["surfaces"]["cardid_behavior"]
    assert "combo_row_count" in usefulness["surfaces"]["combo"]

    if "Combo.json" in deck["expected_runtime_surfaces"]:
        assert usefulness["surfaces"]["combo"]["combo_expected"] is True


def test_cute_warrior_remains_supplemental_load_safe_only():
    supplemental = json.loads(
        Path("docs/operator/supplemental-proof-decks.json").read_text(encoding="utf-8")
    )
    cute = next(row for row in supplemental["decks"] if row["deck_name"] == "CuteWarrior")

    assert cute["proof_scope"] == "supplemental_load_safe_only"
    assert cute["representative_output_competence"] is False
```

- [ ] **Step 2: Run test and verify failure**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_output_competence_matrix.py -q
```

Expected: fail until `config_usefulness` is available in generated `operator_summary.json` and supplemental metadata has the expected fields.

- [ ] **Step 3: Update `docs/operator/supplemental-proof-decks.json`**

For the `CuteWarrior` row, ensure these exact fields exist:

```json
{
  "proof_scope": "supplemental_load_safe_only",
  "representative_output_competence": false
}
```

Preserve existing deck name, deck code, HS id, and HDT deck id fields.

- [ ] **Step 4: Run matrix test**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_output_competence_matrix.py -q
```

Expected: pass for all representative decks and the supplemental CuteWarrior check.

- [ ] **Step 5: Run related fixture tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_archetype_fixture_e2e.py tests/test_universal_wild_no_block_matrix.py tests/test_supplemental_cute_warrior_load_safe.py tests/test_output_competence_matrix.py -q
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit**

```powershell
git add tests/test_output_competence_matrix.py docs/operator/supplemental-proof-decks.json
git commit -m "test: prove output competence visibility"
```

---

### Task 4: Promote Useful Counts Into Operator Guidance and Ownership

**Files:**
- Modify: `src/hsconfig/operator_guidance.py`
- Modify: `src/hsconfig/report_ownership.py`
- Modify: `tests/test_operator_guidance.py`
- Modify: `tests/test_report_ownership.py`

**Interfaces:**
- Consumes:
  - `summary["config_usefulness"]`
- Produces:
  - Operator guidance line points to usefulness status.
  - Report ownership documents `config_usefulness`.

- [ ] **Step 1: Add failing operator-guidance test**

Append to `tests/test_operator_guidance.py`:

```python
def test_operator_guidance_mentions_config_usefulness_when_load_safe_but_thin():
    guidance = build_operator_guidance(
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "STATIC_SEMANTICS_USABLE",
            "next_action": "READY_TO_APPLY_WITH_WARNINGS",
            "runtime_apply_mode": "load_safe_apply",
            "runtime_apply_allowed": True,
            "primary_blockers": [],
            "semantic_blockers": [],
            "config_usefulness": {
                "status": "load_safe_but_thin",
                "headline": "Package is load-safe, but config richness is thin; first gap is runtime_surface_gap.",
                "first_usefulness_gap": "runtime_surface_gap",
                "next_report_to_open": "reports/per_card_config_readiness_report.json",
            },
        }
    )

    assert guidance["safe_to_apply"] is True
    assert guidance["config_usefulness_status"] == "load_safe_but_thin"
    assert guidance["config_usefulness_next_report"] == "reports/per_card_config_readiness_report.json"
```

- [ ] **Step 2: Add failing report ownership test**

Append to `tests/test_report_ownership.py`:

```python
def test_operator_summary_owns_config_usefulness_signal():
    ownership = build_report_ownership()
    operator = next(row for row in ownership if row["file"] == "reports/operator_summary.json")

    assert "config_usefulness" in operator["contains"]
    assert operator["authority"] == "normal_operator_gate"
```

- [ ] **Step 3: Run tests and verify failure**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_operator_guidance.py::test_operator_guidance_mentions_config_usefulness_when_load_safe_but_thin tests/test_report_ownership.py::test_operator_summary_owns_config_usefulness_signal -q
```

Expected: fail because the new guidance fields and ownership entry are absent.

- [ ] **Step 4: Modify `src/hsconfig/operator_guidance.py`**

In the returned guidance object, add these fields for every valid-package branch:

```python
        "config_usefulness_status": str(
            summary.get("config_usefulness", {}).get("status", "unknown")
        ),
        "config_usefulness_next_report": str(
            summary.get("config_usefulness", {}).get(
                "next_report_to_open",
                "reports/operator_summary.json",
            )
        ),
```

Keep existing `safe_to_apply`, `normal_next_step`, and `normal_next_command` values unchanged.

- [ ] **Step 5: Modify `src/hsconfig/report_ownership.py`**

For the `reports/operator_summary.json` row, add `config_usefulness` to the `contains` list. The row should continue to use:

```python
"authority": "normal_operator_gate"
```

- [ ] **Step 6: Run focused tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_operator_guidance.py tests/test_report_ownership.py tests/test_operator_summary.py -q
```

Expected: all selected tests pass.

- [ ] **Step 7: Commit**

```powershell
git add src/hsconfig/operator_guidance.py src/hsconfig/report_ownership.py tests/test_operator_guidance.py tests/test_report_ownership.py
git commit -m "docs: route config usefulness through operator guidance"
```

---

### Task 5: Update Operator Docs and Skill Contract

**Files:**
- Modify: `docs/operator/README.md`
- Modify: `docs/operator/universal-wild-no-block-contract.md`
- Modify: `C:\Users\darbo\.codex\skills\hsconfig\SKILL.md`
- Modify: `tests/test_skill_files.py`

**Interfaces:**
- Consumes:
  - `operator_summary["config_usefulness"]`
- Produces:
  - Human-facing guidance that load safety and config richness are separate.
  - Skill instructions that tell future agents to inspect `config_usefulness` after prepare.

- [ ] **Step 1: Add failing docs test**

Append to `tests/test_skill_files.py`:

```python
def test_docs_explain_config_usefulness_without_making_it_a_blocker():
    operator_readme = Path("docs/operator/README.md").read_text(encoding="utf-8")
    no_block_contract = Path("docs/operator/universal-wild-no-block-contract.md").read_text(
        encoding="utf-8"
    )
    skill = Path(r"C:\Users\darbo\.codex\skills\hsconfig\SKILL.md").read_text(
        encoding="utf-8"
    )
    combined = "\n".join([operator_readme, no_block_contract, skill])

    assert "config_usefulness" in combined
    assert "load-safe" in combined
    assert "non-blocking" in combined
    assert "HSTuner" in combined
    assert "replay" not in operator_readme.lower()
```

- [ ] **Step 2: Run docs test and verify failure**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_skill_files.py::test_docs_explain_config_usefulness_without_making_it_a_blocker -q
```

Expected: fail until docs and skill mention `config_usefulness`.

- [ ] **Step 3: Update `docs/operator/README.md`**

Add this section near the normal operator path:

```markdown
## Load Safety vs. Config Richness

Open `reports/operator_summary.json` first.

- `technical_status`, `runtime_apply_mode`, and `runtime_apply_allowed` decide whether the package is structurally safe to apply.
- `config_usefulness` is non-blocking. It explains whether the load-safe package is guide-aligned, usable with targeted gaps, or load-safe but thin.
- A thin package may still be applied. Thin means the operator should inspect the named `next_report_to_open`, not that HSConfig should stop.
- HSConfig stays pre-run only. Replay analysis, winrate validation, and post-game tuning belong outside this skill.
```

- [ ] **Step 4: Update `docs/operator/universal-wild-no-block-contract.md`**

Add this section:

```markdown
## Non-Blocking Config Usefulness

`config_usefulness` is descriptive. It must not change the no-block contract:

- `VALID_PACKAGE` remains the technical load-safety truth.
- `load_safe_apply` remains allowed when the apply gate is structurally valid.
- `config_usefulness.status=load_safe_but_thin` is a warning surface, not an apply blocker.
- `config_usefulness.next_report_to_open` tells the operator which pre-run report explains the first usefulness gap.
```

- [ ] **Step 5: Update `C:\Users\darbo\.codex\skills\hsconfig\SKILL.md`**

Add this operational rule to the skill’s normal prepare/check path:

```markdown
- After prepare, open `reports/operator_summary.json` first and inspect `config_usefulness`.
- Treat `config_usefulness` as non-blocking: it describes richness across Mulligan, GlobalValues, CardID behavior, and Combo, but it must not prevent load-safe apply.
- If `config_usefulness.status` is `load_safe_but_thin` or `usable_with_targeted_gaps`, report the first gap and the `next_report_to_open`; do not switch to HSTuner or replay analysis inside HSConfig.
```

- [ ] **Step 6: Run docs tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_skill_files.py -q
```

Expected: all skill/doc tests pass.

- [ ] **Step 7: Commit**

```powershell
git add docs/operator/README.md docs/operator/universal-wild-no-block-contract.md tests/test_skill_files.py
git add C:\Users\darbo\.codex\skills\hsconfig\SKILL.md
git commit -m "docs: document nonblocking config usefulness"
```

---

### Task 6: Final Verification and GitHub Sync

**Files:**
- Verify all modified files.
- No new code files beyond earlier tasks.

**Interfaces:**
- Consumes:
  - All task outputs.
- Produces:
  - Green verification.
  - Clean `main` pushed to `origin/main`.

- [ ] **Step 1: Run targeted test suite**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_config_usefulness.py tests/test_operator_summary.py tests/test_operator_guidance.py tests/test_apply_gate.py tests/test_report_ownership.py tests/test_output_competence_matrix.py tests/test_archetype_fixture_e2e.py tests/test_universal_wild_no_block_matrix.py tests/test_supplemental_cute_warrior_load_safe.py tests/test_skill_files.py -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run full test suite**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest -q
```

Expected: full suite passes. If the full suite is slow, keep the command running until completion instead of replacing it with a narrower proof.

- [ ] **Step 3: Check that old scopes were not introduced**

Run:

```powershell
rg -n "Power\\.log|HDT|hsreplay|winrate|Presume\\.json|Concede\\.json" src tests docs/operator C:\Users\darbo\.codex\skills\hsconfig\SKILL.md
```

Expected: no new normal-path claim that HSConfig uses replay, HDT, Power.log, winrate, `Presume.json`, or `Concede.json`. Existing explicit boundary text that says these are out of scope is allowed.

- [ ] **Step 4: Inspect diff**

Run:

```powershell
git diff --stat
git diff -- src/hsconfig/config_usefulness.py src/hsconfig/operator_summary.py src/hsconfig/package_builder.py
```

Expected: changes are limited to config-usefulness reporting, operator-summary integration, docs, and tests.

- [ ] **Step 5: Commit any remaining verification/doc changes**

Run:

```powershell
git status --short
```

If files remain unstaged from verification or doc adjustments, commit them:

```powershell
git add <remaining-files>
git commit -m "chore: finalize config usefulness competence wave"
```

- [ ] **Step 6: Push main**

Run:

```powershell
git status --short --branch
git push origin main
```

Expected: `main` is up to date with `origin/main`.

---

## Self-Review

**Spec coverage:**

- Non-blocking richness visibility: Task 1 and Task 2.
- Mulligan richness: Task 1 helper fields and Task 3 matrix proof.
- GlobalValues richness: Task 1 helper fields and Task 3 matrix proof.
- CardID meaningful runtime rows: Task 1 helper fields and Task 3 matrix proof.
- Combo expected/not expected/report-only distinction: Task 1 helper fields and Task 3 matrix proof.
- Operator single gate preserved: Task 2 and Task 4.
- Apply behavior unchanged: Task 2 apply-gate regression and Task 6 full verification.
- Docs/skill updated: Task 5.
- No HSTuner/replay/winrate scope creep: Global constraints and Task 6 scope scan.

**Placeholder scan:**

- The plan contains exact file paths, function names, statuses, commands, and expected outcomes.
- No task depends on an undefined command or invented CLI.
- No implementation task asks the worker to decide a missing schema shape.

**Type consistency:**

- `build_config_usefulness()` returns a dictionary consumed by `build_operator_summary()`.
- `operator_summary["config_usefulness"]` is consumed by `build_operator_guidance()`.
- `runtime_permission_impact` is always the literal string `none`.
- Status values are stable across helper, operator summary, docs, and tests.

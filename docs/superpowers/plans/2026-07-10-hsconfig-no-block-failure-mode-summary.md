# HSConfig No-Block Failure Mode Summary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a compact operator-facing `no_block_failure_mode_summary` that makes it impossible to confuse load-safe warnings with real technical blocks.

**Architecture:** Keep HSConfig's current apply gate unchanged: `technical_status=VALID_PACKAGE` plus `runtime_apply_mode=load_safe_apply` remains the write boundary. Add a small pure summary builder used by `build_operator_summary()` to categorize existing data into hard blocks and non-blocking warning families. Add one modern-mechanic sentinel test to preserve visibility without widening the representative deck matrix.

**Tech Stack:** Python package under `src/hsconfig`, pytest tests under `tests`, markdown operator docs, installed skill sync via `scripts/sync_installed_skill.py`.

## Global Constraints

- HSConfig remains pre-run only; do not add replay, winrate, HSTuner, runtime-log, candidate-promotion, or post-game tuning scope.
- Do not broaden runtime surfaces: normal package family remains `GlobalValues.json`, `Mulligan.json`, per-card `<CARDID>.json`, and exact `Combo.json`.
- Do not emit `Presume.json` or `Concede.json` in the normal path; their absence must not block valid load-safe packages.
- Do not add representative decks. Keep the 11-deck representative matrix plus supplemental `CuteWarrior`.
- Warning-only and partial mechanics must stay visible but must not block `load_safe_apply` for technically valid packages.
- Technical invalidity must still block runtime writes: malformed package, invalid JSON, missing required runtime files, undeclared runtime files, nested runtime files, stale/forged apply evidence, and normal-path legacy surfaces.
- Generated research artifacts under `docs/research/2026-07-10-hsconfig-universal-no-block-skill-audit-v5/` are evidence for this plan; they are not normal operator instructions.

---

## File Structure

- Create `src/hsconfig/no_block_failure_modes.py`
  - Responsibility: pure classification helper for operator summary inputs. No filesystem reads, no runtime writes, no CLI parsing.
- Modify `src/hsconfig/operator_summary.py`
  - Responsibility: call the helper after existing `next_action`, `apply_policy`, and runtime apply contract are computed; expose `no_block_failure_mode_summary`.
- Optionally modify `src/hsconfig/operator_guidance.py`
  - Responsibility: surface the summary in guidance only if current guidance intentionally mirrors operator summary sections. Do not create a second gate.
- Modify `tests/test_operator_summary.py`
  - Responsibility: unit-level TDD for summary categories and no-block semantics.
- Modify `tests/test_mechanic_drift.py` or `tests/test_mechanic_support.py`
  - Responsibility: compact sentinel for modern/future text-only mechanics remaining visible and non-blocking.
- Modify `tests/test_universal_wild_no_block_matrix.py`
  - Responsibility: verify every provided deck gets the new summary and remains `load_safe_apply`.
- Modify `docs/operator/README.md`
  - Responsibility: explain how to read `no_block_failure_mode_summary`.
- Modify `docs/operator/universal-wild-no-block-contract.md`
  - Responsibility: define the summary as explanatory, not a gate.
- Modify `.agents/skills/hsconfig/SKILL.md` and `.agents/skills/hsconfig/references/workflow.md`
  - Responsibility: keep installed skill operator instructions aligned.
- Run `python scripts/sync_installed_skill.py` after repo skill docs change.

---

### Task 1: Add Pure Failure-Mode Classifier

**Files:**
- Create: `src/hsconfig/no_block_failure_modes.py`
- Test: `tests/test_operator_summary.py`

**Interfaces:**
- Consumes:
  - `technical_status: str`
  - `runtime_apply_mode: str`
  - `runtime_apply_allowed: bool`
  - `next_action: str`
  - `apply_policy: str`
  - `primary_blockers: list[dict[str, Any]]`
  - `warnings: list[dict[str, Any]]`
  - `semantic_status: str`
  - `semantic_blockers: list[dict[str, Any]]`
  - `guide_strength_summary: dict[str, Any]`
  - `config_usefulness: dict[str, Any]`
  - `mechanic_visibility_summary: dict[str, Any]`
  - `mechanic_drift_summary: dict[str, Any]`
  - `source_informed_apply_readiness: dict[str, Any]`
- Produces:
  - `build_no_block_failure_mode_summary(...) -> dict[str, Any]`
  - Returned keys:
    - `schema_version: int`
    - `overall: str`
    - `hard_block: bool`
    - `runtime_apply_allowed: bool`
    - `operator_message: str`
    - `categories: dict[str, list[dict[str, Any]]]`
    - `first_non_blocking_followup: dict[str, Any] | None`

- [ ] **Step 1: Add failing tests for allowed warning categories**

Append this test to `tests/test_operator_summary.py`:

```python
def test_no_block_failure_mode_summary_keeps_valid_warning_package_applyable():
    summary = build_operator_summary(
        deck_name="Warning Deck",
        deck_code="AAEBAQAAAA==",
        technical_validation={"status": "passed", "errors": []},
        guide_source_depth={"source_depth_status": "static_semantics_only", "claim_count": 0},
        claim_coverage_report={
            "summary": {
                "guide_backed": 1,
                "static_semantics_backfilled": 1,
                "uncovered_low_confidence": 2,
            },
            "uncovered_cards": ["CARD_A", "CARD_B"],
        },
        config_readiness_summary={
            "total_cards": 3,
            "generic_low_confidence": 2,
            "cards_needing_guide_claims": 2,
            "cards_needing_runtime_surface": 1,
            "cards_needing_mulligan_claims": 1,
            "cards_needing_combo_sequence": 1,
            "cards_needing_condition_lowering": 0,
            "cards_needing_mechanic_lowering": 1,
        },
        config_readiness_report={
            "summary": {
                "mechanic_visibility": {
                    "non_blocking": True,
                    "bucket_counts": {
                        "direct": 1,
                        "identity_gated_direct": 0,
                        "partial": 1,
                        "warning_only": 2,
                    },
                    "mechanics_by_bucket": {
                        "direct": ["battlecry"],
                        "identity_gated_direct": [],
                        "partial": ["generated_entity"],
                        "warning_only": ["dredge", "tradeable"],
                    },
                    "warning_only_card_count": 2,
                    "first_warning_boundary": {
                        "mechanic": "dredge",
                        "warning_boundary": "Dredge option selection has no documented normal-path VisionAI choice surface.",
                    },
                    "warning_boundaries": [
                        {
                            "mechanic": "dredge",
                            "warning_boundary": "Dredge option selection has no documented normal-path VisionAI choice surface.",
                        },
                        {
                            "mechanic": "tradeable",
                            "warning_boundary": "Trade-now decisions have no documented normal-path VisionAI runtime block.",
                        },
                    ],
                }
            },
            "cards": {
                "CARD_A": {
                    "name": "Card A",
                    "first_missing_link": "needs_guide_claim",
                },
                "CARD_B": {
                    "name": "Card B",
                    "first_missing_link": "needs_runtime_surface",
                },
                "CARD_C": {
                    "name": "Card C",
                    "first_missing_link": "needs_combo_sequence",
                },
            },
        },
        mechanic_drift_report={
            "non_blocking": True,
            "unknown_mechanics": ["future_keyword"],
            "text_only_mechanics": ["rewind"],
            "unknown_card_types": ["future_type"],
            "summary": {
                "mechanic_count": 2,
                "unknown_mechanic_count": 1,
                "text_only_mechanic_count": 1,
                "unknown_card_type_count": 1,
            },
        },
        combo_plan_report={
            "summary": {
                "combo_count": 0,
                "cards_needing_combo_sequence": 1,
            }
        },
        generated_files=[
            "CustomConfig/warningdeck/GlobalValues.json",
            "CustomConfig/warningdeck/Mulligan.json",
            "CustomConfig/warningdeck/CARD_A.json",
            "CustomConfig/warningdeck/CARD_B.json",
            "CustomConfig/warningdeck/CARD_C.json",
        ],
    )

    no_block = summary["no_block_failure_mode_summary"]

    assert summary["technical_status"] == "VALID_PACKAGE"
    assert summary["runtime_apply_mode"] == "load_safe_apply"
    assert summary["runtime_apply_allowed"] is True
    assert no_block["overall"] == "load_safe_apply_allowed_with_warnings"
    assert no_block["hard_block"] is False
    assert no_block["runtime_apply_allowed"] is True
    assert no_block["operator_message"] == (
        "Package is load-safe. Listed warnings explain source or mechanic limits; "
        "they do not block hsconfig apply."
    )
    assert no_block["categories"]["technical_hard_block"] == []
    assert {row["reason"] for row in no_block["categories"]["source_depth_warning"]} >= {
        "cards_need_guide_claims",
        "cards_need_runtime_surface",
        "cards_need_mulligan_claims",
        "cards_need_combo_sequence",
        "cards_need_mechanic_lowering",
    }
    assert no_block["categories"]["warning_only_mechanic"] == [
        {"mechanic": "dredge"},
        {"mechanic": "tradeable"},
    ]
    assert no_block["categories"]["future_mechanic_drift"] == [
        {"kind": "unknown_mechanic", "value": "future_keyword"},
        {"kind": "text_only_mechanic", "value": "rewind"},
        {"kind": "unknown_card_type", "value": "future_type"},
    ]
    assert any(
        row["reason"] == "generic_low_confidence_cards"
        for row in no_block["categories"]["guide_strength_gap"]
    )
    assert no_block["categories"]["combo_uncertainty"] == [
        {"reason": "cards_need_combo_sequence", "count": 1}
    ]
    assert no_block["categories"]["runtime_evidence_only_tuning"] == []
    assert no_block["first_non_blocking_followup"]["category"] == "source_depth_warning"
```

- [ ] **Step 2: Add failing test for technical hard block**

Append this test to `tests/test_operator_summary.py`:

```python
def test_no_block_failure_mode_summary_marks_invalid_package_as_hard_block():
    summary = build_operator_summary(
        deck_name="Broken Deck",
        deck_code="bad-code",
        technical_validation={
            "status": "failed",
            "errors": ["missing_required_runtime_file"],
        },
        generated_files=[],
    )

    no_block = summary["no_block_failure_mode_summary"]

    assert summary["technical_status"] == "INVALID_PACKAGE"
    assert summary["runtime_apply_mode"] == "blocked"
    assert summary["runtime_apply_allowed"] is False
    assert no_block["overall"] == "technical_hard_block"
    assert no_block["hard_block"] is True
    assert no_block["runtime_apply_allowed"] is False
    assert no_block["categories"]["technical_hard_block"] == [
        {"reason": "missing_required_runtime_file"}
    ]
    assert no_block["operator_message"] == (
        "Package is not load-safe. Fix technical_hard_block items before hsconfig apply."
    )
```

- [ ] **Step 3: Run tests to verify they fail**

Run:

```powershell
python -m pytest tests\test_operator_summary.py::test_no_block_failure_mode_summary_keeps_valid_warning_package_applyable tests\test_operator_summary.py::test_no_block_failure_mode_summary_marks_invalid_package_as_hard_block -q
```

Expected: FAIL with `KeyError: 'no_block_failure_mode_summary'`.

- [ ] **Step 4: Implement the helper**

Create `src/hsconfig/no_block_failure_modes.py`:

```python
from __future__ import annotations

from typing import Any


def build_no_block_failure_mode_summary(
    *,
    technical_status: str,
    runtime_apply_mode: str,
    runtime_apply_allowed: bool,
    next_action: str,
    apply_policy: str,
    primary_blockers: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    semantic_status: str,
    source_depth_status: str,
    semantic_blockers: list[dict[str, Any]],
    guide_strength_summary: dict[str, Any],
    config_usefulness: dict[str, Any],
    mechanic_visibility_summary: dict[str, Any],
    mechanic_drift_summary: dict[str, Any],
    source_informed_apply_readiness: dict[str, Any],
) -> dict[str, Any]:
    categories = {
        "technical_hard_block": _technical_hard_blocks(primary_blockers),
        "source_depth_warning": _source_depth_warnings(
            warnings,
            source_depth_status=source_depth_status,
        ),
        "warning_only_mechanic": _warning_only_mechanics(mechanic_visibility_summary),
        "future_mechanic_drift": _future_mechanic_drift(mechanic_drift_summary),
        "guide_strength_gap": _guide_strength_gaps(
            semantic_status=semantic_status,
            semantic_blockers=semantic_blockers,
            guide_strength_summary=guide_strength_summary,
            warnings=warnings,
            config_usefulness=config_usefulness,
            source_informed_apply_readiness=source_informed_apply_readiness,
        ),
        "combo_uncertainty": _combo_uncertainty(semantic_blockers),
        "runtime_evidence_only_tuning": _runtime_evidence_warnings(warnings),
    }
    hard_block = bool(categories["technical_hard_block"]) or technical_status != "VALID_PACKAGE"
    if hard_block:
        for category in categories:
            if category != "technical_hard_block":
                categories[category] = []
        overall = "technical_hard_block"
        operator_message = (
            "Package is not load-safe. Fix technical_hard_block items before hsconfig apply."
        )
    elif runtime_apply_allowed and runtime_apply_mode == "load_safe_apply":
        has_warnings = any(categories[name] for name in categories if name != "technical_hard_block")
        overall = "load_safe_apply_allowed_with_warnings" if has_warnings else "load_safe_apply_allowed"
        operator_message = (
            "Package is load-safe. Listed warnings explain source or mechanic limits; "
            "they do not block hsconfig apply."
        )
    else:
        overall = "runtime_apply_not_allowed"
        operator_message = "Package is not currently allowed to write runtime files."

    return {
        "schema_version": 1,
        "overall": overall,
        "hard_block": hard_block,
        "runtime_apply_allowed": bool(runtime_apply_allowed),
        "runtime_apply_mode": runtime_apply_mode,
        "next_action": next_action,
        "apply_policy": apply_policy,
        "operator_message": operator_message,
        "categories": categories,
        "first_non_blocking_followup": (
            None if hard_block else _first_non_blocking_followup(categories)
        ),
    }


def _technical_hard_blocks(primary_blockers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for blocker in primary_blockers:
        if not isinstance(blocker, dict):
            continue
        reason = str(blocker.get("reason", "")).strip()
        if reason:
            rows.append({"reason": reason})
    return rows


def _source_depth_warnings(
    warnings: list[dict[str, Any]],
    *,
    source_depth_status: str,
) -> list[dict[str, Any]]:
    rows = []
    if source_depth_status == "static_semantics_only":
        rows.append({"reason": "static_semantics_only"})
    elif source_depth_status == "needs_more_research":
        rows.append({"reason": "needs_more_research"})
    for warning in warnings:
        if not isinstance(warning, dict):
            continue
        if str(warning.get("reason", "")) not in SOURCE_DEPTH_WARNING_REASONS:
            continue
        rows.append(dict(warning))
    return _dedupe_rows(rows)


def _warning_only_mechanics(mechanic_visibility_summary: dict[str, Any]) -> list[dict[str, Any]]:
    mechanics_by_bucket = mechanic_visibility_summary.get("mechanics_by_bucket", {})
    if not isinstance(mechanics_by_bucket, dict):
        return []
    warning_only = mechanics_by_bucket.get("warning_only", [])
    if not isinstance(warning_only, list):
        return []
    return [{"mechanic": str(mechanic)} for mechanic in warning_only]


def _future_mechanic_drift(mechanic_drift_summary: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for key, kind in (
        ("unknown_mechanics", "unknown_mechanic"),
        ("text_only_mechanics", "text_only_mechanic"),
        ("unknown_card_types", "unknown_card_type"),
    ):
        values = mechanic_drift_summary.get(key, [])
        if not isinstance(values, list):
            continue
        rows.extend({"kind": kind, "value": str(value)} for value in values)
    return rows


def _guide_strength_gaps(
    *,
    semantic_status: str,
    semantic_blockers: list[dict[str, Any]],
    guide_strength_summary: dict[str, Any],
    warnings: list[dict[str, Any]],
    config_usefulness: dict[str, Any],
    source_informed_apply_readiness: dict[str, Any],
) -> list[dict[str, Any]]:
    rows = []
    if semantic_status == "VALID_BUT_NOT_GUIDE_STRONG":
        rows.append({"reason": semantic_status.lower()})
    for key in (
        "generic_low_confidence_cards",
        "uncovered_cards",
        "claim_conflicts",
    ):
        count = _int_value(guide_strength_summary.get(key, 0))
        if count:
            rows.append({"reason": key, "count": count})
    status = str(config_usefulness.get("status", ""))
    if status in {"load_safe_but_thin", "usable_with_targeted_gaps"}:
        rows.append(
            {
                "reason": "config_usefulness_gap",
                "status": status,
                "first_usefulness_gap": str(config_usefulness.get("first_usefulness_gap", "")),
                "next_report_to_open": str(config_usefulness.get("next_report_to_open", "")),
            }
        )
    for blocker in semantic_blockers:
        if not isinstance(blocker, dict):
            continue
        if str(blocker.get("reason", "")) not in GUIDE_STRENGTH_BLOCKER_REASONS:
            continue
        rows.append({
            "reason": str(blocker["reason"]),
            "count": _int_value(blocker.get("count", 0)),
            "report": str(blocker.get("report", "")),
        })
    blocking_reasons = source_informed_apply_readiness.get("blocking_reasons", [])
    if isinstance(blocking_reasons, list):
        source_informed_reasons = list(
            dict.fromkeys(
                str(reason)
                for reason in blocking_reasons
                if str(reason) != "cards_need_combo_sequence"
            )
        )
        if source_informed_reasons:
            rows.append(
                {
                    "reason": "source_informed_apply_gap",
                    "values": source_informed_reasons,
                }
            )
    for warning in warnings:
        if not isinstance(warning, dict):
            continue
        reason = str(warning.get("reason", ""))
        if reason in {"valid_but_not_guide_strong", "cards_still_low_confidence"}:
            rows.append({"reason": reason, "count": _int_value(warning.get("card_count", 0))})
    return _dedupe_rows(rows)


def _combo_uncertainty(semantic_blockers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for blocker in semantic_blockers:
        if not isinstance(blocker, dict):
            continue
        if str(blocker.get("reason", "")) != "cards_need_combo_sequence":
            continue
        rows.append({"reason": "cards_need_combo_sequence", "count": _int_value(blocker.get("count", 0))})
    return rows


def _runtime_evidence_warnings(warnings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for warning in warnings:
        if not isinstance(warning, dict):
            continue
        if str(warning.get("reason", "")) != "globalvalue_runtime_evidence_required":
            continue
        rows.append(
            {
                "reason": "globalvalue_runtime_evidence_required",
                "key": str(warning.get("key", "")),
            }
        )
    return rows


def _first_non_blocking_followup(categories: dict[str, list[dict[str, Any]]]) -> dict[str, Any] | None:
    for category in (
        "source_depth_warning",
        "warning_only_mechanic",
        "future_mechanic_drift",
        "guide_strength_gap",
        "combo_uncertainty",
        "runtime_evidence_only_tuning",
    ):
        rows = categories.get(category, [])
        if rows:
            return {"category": category, "item": rows[0]}
    return None


def _dedupe_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    positions = {}
    result = []
    for row in rows:
        reason = str(row.get("reason", "")).strip()
        if not reason:
            result.append(row)
            continue
        position = positions.get(reason)
        if position is None:
            positions[reason] = len(result)
            result.append(row)
        elif _row_count(row) > _row_count(result[position]):
            result[position] = row
    return result


def _row_count(row: dict[str, Any]) -> int:
    return max(
        _int_value(row.get(key, 0))
        for key in ("count", "card_count", "conflict_count")
    )


def _int_value(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
```

- [ ] **Step 5: Integrate helper into operator summary**

Modify `src/hsconfig/operator_summary.py` imports:

```python
from hsconfig.no_block_failure_modes import build_no_block_failure_mode_summary
```

Inside `build_operator_summary()`, after `runtime_apply_mode, runtime_apply_allowed, runtime_apply_requires_flag = _runtime_apply_contract(...)`, create:

```python
    source_depth_status = _source_depth_status(guide_source_depth or {})
    no_block_failure_mode_summary = build_no_block_failure_mode_summary(
        technical_status=technical_status,
        runtime_apply_mode=runtime_apply_mode,
        runtime_apply_allowed=runtime_apply_allowed,
        next_action=next_action,
        apply_policy=apply_policy,
        primary_blockers=primary_blockers,
        warnings=warnings,
        semantic_status=semantic_status,
        source_depth_status=source_depth_status,
        semantic_blockers=semantic_blockers,
        guide_strength_summary=guide_strength_summary,
        config_usefulness=config_usefulness,
        mechanic_visibility_summary=mechanic_visibility_summary,
        mechanic_drift_summary=_mechanic_drift_summary(mechanic_drift_report),
        source_informed_apply_readiness=source_informed_apply_readiness,
    )
```

Then add this key to the `summary` dict near `config_usefulness`:

```python
        "no_block_failure_mode_summary": no_block_failure_mode_summary,
```

If the implementation currently calls `_mechanic_drift_summary(mechanic_drift_report)` inline in the summary dict, store it in a local variable first to avoid calling it twice:

```python
    mechanic_drift_summary = _mechanic_drift_summary(mechanic_drift_report)
```

Then pass `mechanic_drift_summary=mechanic_drift_summary` and set:

```python
        "mechanic_drift_summary": mechanic_drift_summary,
```

- [ ] **Step 6: Run targeted tests**

Run:

```powershell
python -m pytest tests\test_operator_summary.py::test_no_block_failure_mode_summary_keeps_valid_warning_package_applyable tests\test_operator_summary.py::test_no_block_failure_mode_summary_marks_invalid_package_as_hard_block -q
```

Expected: `2 passed`.

- [ ] **Step 7: Commit Task 1**

Run:

```powershell
git add src\hsconfig\no_block_failure_modes.py src\hsconfig\operator_summary.py tests\test_operator_summary.py
git commit -m "feat: summarize no-block failure modes"
```

Expected: commit succeeds.

---

### Task 2: Thread Summary Through Universal Deck Matrix

**Files:**
- Modify: `tests/test_universal_wild_no_block_matrix.py`

**Interfaces:**
- Consumes: `operator_summary.json["no_block_failure_mode_summary"]`
- Produces: regression proof that all current valid Wild proof decks keep `load_safe_apply` and get a readable summary.

- [ ] **Step 1: Extend the universal matrix test**

In `tests/test_universal_wild_no_block_matrix.py`, inside `test_valid_wild_deck_produces_load_safe_warning_apply_package()`, after:

```python
    assert operator["runtime_apply_allowed"] is True
```

add:

```python
    no_block = operator["no_block_failure_mode_summary"]
    assert no_block["hard_block"] is False
    assert no_block["runtime_apply_allowed"] is True
    assert no_block["runtime_apply_mode"] == "load_safe_apply"
    assert no_block["overall"] in {
        "load_safe_apply_allowed",
        "load_safe_apply_allowed_with_warnings",
    }
    assert no_block["categories"]["technical_hard_block"] == []
    assert no_block["operator_message"].startswith("Package is load-safe.")
```

- [ ] **Step 2: Run the matrix test**

Run:

```powershell
python -m pytest tests\test_universal_wild_no_block_matrix.py -q
```

Expected: `12 passed`.

- [ ] **Step 3: Commit Task 2**

Run:

```powershell
git add tests\test_universal_wild_no_block_matrix.py
git commit -m "test: require no-block summary for proof decks"
```

Expected: commit succeeds.

---

### Task 3: Add Compact Modern-Mechanic Sentinel

**Files:**
- Modify: `tests/test_mechanic_drift.py`
- Modify: `tests/test_operator_summary.py`

**Interfaces:**
- Consumes:
  - `build_mechanic_drift_report(cards: Iterable[dict[str, Any]]) -> dict[str, Any]`
  - `build_operator_summary(...) -> dict[str, Any]`
- Produces:
  - Proof that text-only current/future mechanics stay visible.
  - Proof that those mechanics do not alter `load_safe_apply`.

- [ ] **Step 1: Strengthen existing text-only mechanic drift test**

In `tests/test_mechanic_drift.py`, update `test_mechanic_drift_detects_modern_text_only_mechanics_without_blocking()` after the existing `for mechanic in ["rewind", "herald", "shatter"]` block with:

```python
    for mechanic in ["kindred", "tourist", "rewind", "herald", "shatter"]:
        assert mechanic in report["text_only_mechanics"]
        assert report["support_by_mechanic"][mechanic]["normal_path_surfaces"] == [
            "report-only"
        ]
        assert report["support_by_mechanic"][mechanic]["support_level"] == "warning_only"
```

- [ ] **Step 2: Add operator summary sentinel**

Append this test to `tests/test_operator_summary.py`:

```python
def test_no_block_summary_surfaces_future_mechanic_drift_without_blocking_apply():
    summary = build_operator_summary(
        deck_name="FutureMechanicDeck",
        deck_code="AAEBAQAAAA==",
        technical_validation={"status": "passed"},
        guide_source_depth={"source_depth_status": "static_semantics_only", "claim_count": 0},
        mechanic_drift_report={
            "non_blocking": True,
            "unknown_mechanics": [],
            "text_only_mechanics": ["herald", "kindred", "rewind", "shatter", "tourist"],
            "unknown_card_types": [],
            "summary": {
                "mechanic_count": 5,
                "unknown_mechanic_count": 0,
                "text_only_mechanic_count": 5,
                "unknown_card_type_count": 0,
            },
        },
        generated_files=[
            "CustomConfig/futuremechanicdeck/GlobalValues.json",
            "CustomConfig/futuremechanicdeck/Mulligan.json",
        ],
    )

    no_block = summary["no_block_failure_mode_summary"]

    assert summary["runtime_apply_mode"] == "load_safe_apply"
    assert summary["runtime_apply_allowed"] is True
    assert no_block["hard_block"] is False
    assert no_block["categories"]["future_mechanic_drift"] == [
        {"kind": "text_only_mechanic", "value": "herald"},
        {"kind": "text_only_mechanic", "value": "kindred"},
        {"kind": "text_only_mechanic", "value": "rewind"},
        {"kind": "text_only_mechanic", "value": "shatter"},
        {"kind": "text_only_mechanic", "value": "tourist"},
    ]
```

- [ ] **Step 3: Run targeted tests**

Run:

```powershell
python -m pytest tests\test_mechanic_drift.py::test_mechanic_drift_detects_modern_text_only_mechanics_without_blocking tests\test_operator_summary.py::test_no_block_summary_surfaces_future_mechanic_drift_without_blocking_apply -q
```

Expected: `2 passed`.

- [ ] **Step 4: Commit Task 3**

Run:

```powershell
git add tests\test_mechanic_drift.py tests\test_operator_summary.py
git commit -m "test: keep modern mechanics non-blocking"
```

Expected: commit succeeds.

---

### Task 4: Document Operator Meaning And Sync Skill

**Files:**
- Modify: `docs/operator/README.md`
- Modify: `docs/operator/universal-wild-no-block-contract.md`
- Modify: `.agents/skills/hsconfig/SKILL.md`
- Modify: `.agents/skills/hsconfig/references/workflow.md`
- Test: `tests/test_docs_active_path.py`
- Test: `tests/test_skill_files.py`

**Interfaces:**
- Consumes: `no_block_failure_mode_summary` emitted by `operator_summary.json`
- Produces: operator docs and installed skill instructions that describe the summary as explanatory and non-gating.

- [ ] **Step 1: Add failing doc tests**

Append this test to `tests/test_docs_active_path.py`:

```python
def test_operator_docs_explain_no_block_failure_mode_summary():
    docs = "\n".join(
        [
            Path("docs/operator/README.md").read_text(encoding="utf-8"),
            Path("docs/operator/universal-wild-no-block-contract.md").read_text(
                encoding="utf-8"
            ),
        ]
    )

    assert "no_block_failure_mode_summary" in docs
    assert "technical_hard_block" in docs
    assert "source_depth_warning" in docs
    assert "warning_only_mechanic" in docs
    assert "future_mechanic_drift" in docs
    assert "guide_strength_gap" in docs
    assert "combo_uncertainty" in docs
    assert "runtime_evidence_only_tuning" in docs
    assert "It does not create a second apply gate." in docs
```

Append this test to `tests/test_skill_files.py`:

```python
def test_skill_explains_no_block_failure_mode_summary():
    skill = Path(".agents/skills/hsconfig/SKILL.md").read_text(encoding="utf-8")
    workflow = Path(".agents/skills/hsconfig/references/workflow.md").read_text(
        encoding="utf-8"
    )
    combined = f"{skill}\n{workflow}"

    assert "no_block_failure_mode_summary" in combined
    assert "technical_hard_block" in combined
    assert "warning_only_mechanic" in combined
    assert "future_mechanic_drift" in combined
    assert "does not create a second apply gate" in combined
```

- [ ] **Step 2: Run doc tests to verify they fail**

Run:

```powershell
python -m pytest tests\test_docs_active_path.py::test_operator_docs_explain_no_block_failure_mode_summary tests\test_skill_files.py::test_skill_explains_no_block_failure_mode_summary -q
```

Expected: FAIL because the new wording is missing.

- [ ] **Step 3: Update operator docs**

In `docs/operator/README.md`, under `## Single Gate`, after the paragraph that starts with `Use reports/operator_summary.json as the normal operator gate.`, add:

```markdown
`no_block_failure_mode_summary` is the fastest way to read why a package did
or did not stop. `technical_hard_block` is the only hard stop category. The
other categories, `source_depth_warning`, `warning_only_mechanic`,
`future_mechanic_drift`, `guide_strength_gap`, `combo_uncertainty`, and
`runtime_evidence_only_tuning`, explain source or semantic limits while
`load_safe_apply` can still proceed for `technical_status=VALID_PACKAGE`.
It does not create a second apply gate.
```

In `docs/operator/universal-wild-no-block-contract.md`, after `## Non-Blocking Warnings`, add:

```markdown
## Failure Mode Summary

`reports/operator_summary.json` includes `no_block_failure_mode_summary`.
This is an explanatory summary, not a new permission model. It groups real
technical stops under `technical_hard_block` and non-blocking follow-up work
under `source_depth_warning`, `warning_only_mechanic`,
`future_mechanic_drift`, `guide_strength_gap`, `combo_uncertainty`, and
`runtime_evidence_only_tuning`. It does not create a second apply gate.
```

- [ ] **Step 4: Update repo skill docs**

In `.agents/skills/hsconfig/SKILL.md`, under the rules section after the `config_usefulness` bullets, add:

```markdown
- Inspect `no_block_failure_mode_summary` when a package has warnings. Only
  `technical_hard_block` stops `hsconfig apply`; `source_depth_warning`,
  `warning_only_mechanic`, `future_mechanic_drift`, `guide_strength_gap`,
  `combo_uncertainty`, and `runtime_evidence_only_tuning` explain follow-up work.
  The summary does not create a second apply gate.
```

In `.agents/skills/hsconfig/references/workflow.md`, under `## Readiness Interpretation`, add:

```markdown
Use `no_block_failure_mode_summary` to separate hard stops from warning work.
`technical_hard_block` means fix the package before apply. Other categories
are explanatory and do not create a second apply gate when the package is
`technical_status=VALID_PACKAGE`.
```

- [ ] **Step 5: Sync installed skill**

Run:

```powershell
python scripts\sync_installed_skill.py
python scripts\sync_installed_skill.py --check
```

Expected:

```text
HSConfig skill is in sync: C:\Users\darbo\.codex\skills\hsconfig
```

- [ ] **Step 6: Run docs tests**

Run:

```powershell
python -m pytest tests\test_docs_active_path.py::test_operator_docs_explain_no_block_failure_mode_summary tests\test_skill_files.py::test_skill_explains_no_block_failure_mode_summary -q
```

Expected: `2 passed`.

- [ ] **Step 7: Commit Task 4**

Run:

```powershell
git add docs\operator\README.md docs\operator\universal-wild-no-block-contract.md .agents\skills\hsconfig\SKILL.md .agents\skills\hsconfig\references\workflow.md tests\test_docs_active_path.py tests\test_skill_files.py C:\Users\darbo\.codex\skills\hsconfig\SKILL.md C:\Users\darbo\.codex\skills\hsconfig\references\workflow.md
git commit -m "docs: explain no-block failure modes"
```

Expected: commit succeeds. If Git refuses to add files outside the repository, stage only repo files and keep the installed skill synced but untracked by this repo.

---

### Task 5: Final Verification And Research Index

**Files:**
- Modify: `docs/research/current-truth.md`
- Test: `tests/test_docs_active_path.py`

**Interfaces:**
- Consumes:
  - `docs/research/2026-07-10-hsconfig-universal-no-block-skill-audit-v5/results/*.json`
  - New `no_block_failure_mode_summary` docs
- Produces:
  - Current-truth pointer to the v5 audit.
  - Final verification evidence.

- [ ] **Step 1: Add failing current-truth test**

Append this test to `tests/test_docs_active_path.py`:

```python
def test_current_truth_names_no_block_failure_mode_audit_v5():
    text = Path("docs/research/current-truth.md").read_text(encoding="utf-8")

    assert "2026-07-10-hsconfig-universal-no-block-skill-audit-v5" in text
    assert "No-block failure-mode summary evidence" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest tests\test_docs_active_path.py::test_current_truth_names_no_block_failure_mode_audit_v5 -q
```

Expected: FAIL because the v5 package is not listed yet.

- [ ] **Step 3: Update current truth index**

In `docs/research/current-truth.md`, add one concise active evidence bullet:

```markdown
- `2026-07-10-hsconfig-universal-no-block-skill-audit-v5` - No-block
  failure-mode summary evidence. Confirms that the next narrow improvement is
  an operator-facing `no_block_failure_mode_summary`, not a broader apply gate,
  new representative decks, or post-run HSTuner scope.
```

- [ ] **Step 4: Run current-truth test**

Run:

```powershell
python -m pytest tests\test_docs_active_path.py::test_current_truth_names_no_block_failure_mode_audit_v5 -q
```

Expected: `1 passed`.

- [ ] **Step 5: Run focused verification**

Run:

```powershell
python -m pytest tests\test_operator_summary.py tests\test_mechanic_drift.py tests\test_mechanic_support.py tests\test_universal_wild_no_block_matrix.py tests\test_docs_active_path.py tests\test_skill_files.py -q
```

Expected: all selected tests pass.

- [ ] **Step 6: Validate research artifacts**

Run:

```powershell
python C:\Users\darbo\.codex\skills\research\validate_json.py -f docs\research\2026-07-10-hsconfig-universal-no-block-skill-audit-v5\fields.yaml -d docs\research\2026-07-10-hsconfig-universal-no-block-skill-audit-v5\results
```

Expected:

```text
Validation passed: 5/5
Average coverage: 100.0%
```

- [ ] **Step 7: Run installed skill sync check**

Run:

```powershell
python scripts\sync_installed_skill.py --check
```

Expected:

```text
HSConfig skill is in sync: C:\Users\darbo\.codex\skills\hsconfig
```

- [ ] **Step 8: Run full suite if time allows**

Run:

```powershell
python -m pytest -q
```

Expected: all tests pass. If the full suite is skipped for time, record the focused test commands that passed and the reason full suite was not run.

- [ ] **Step 9: Check git status**

Run:

```powershell
git status --short --branch
```

Expected: only intentional files changed. No temp outputs, caches, or runtime configs should be staged.

- [ ] **Step 10: Commit Task 5**

Run:

```powershell
git add docs\research\current-truth.md docs\research\2026-07-10-hsconfig-universal-no-block-skill-audit-v5 docs\superpowers\plans\2026-07-10-hsconfig-no-block-failure-mode-summary.md tests\test_docs_active_path.py
git commit -m "docs: add no-block failure-mode plan and evidence"
```

Expected: commit succeeds.

---

## Final Acceptance Checklist

- [ ] `operator_summary.json` includes `no_block_failure_mode_summary`.
- [ ] `technical_hard_block` is the only hard-stop category in the new summary.
- [ ] Valid packages with semantic/source/mechanic warnings still report `runtime_apply_mode=load_safe_apply`.
- [ ] Invalid packages still report `runtime_apply_mode=blocked`.
- [ ] Modern/future mechanics remain visible and non-blocking.
- [ ] No representative deck was added.
- [ ] No replay, winrate, HSTuner, runtime-log, or post-game tuning scope was added.
- [ ] `Presume.json` and `Concede.json` remain outside the normal path.
- [ ] Installed skill is synced.
- [ ] Focused tests pass.
- [ ] Research validation passes.
- [ ] Final `git status --short --branch` contains only intended work before commit, then is clean or only expected local files after commit.

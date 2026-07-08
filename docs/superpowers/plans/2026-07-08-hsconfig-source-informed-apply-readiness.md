# HSConfig Source-Informed Apply Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make HSConfig less conservative by adding an explicit source-informed apply-ready lane for technically valid packages that are not `SOURCE_BACKED_STRONG` only because deck-specific guide claims are missing.

**Architecture:** Keep `semantic_status` honest: `SOURCE_BACKED_STRONG` still means fully source-backed, while `VALID_BUT_NOT_GUIDE_STRONG` can now expose a separate `source_informed_apply_readiness` decision. Runtime apply remains gated by `reports/operator_summary.json`; source-informed runtime writes still require the existing explicit `--allow-source-informed` flag.

**Tech Stack:** Python 3.11, pytest, existing HSConfig CLI modules under `src/hsconfig`, existing skill docs under `.agents/skills/hsconfig`, and operator docs under `docs/operator`.

## Global Constraints

- HSConfig remains pre-run only; do not add replay parsing, winrate analysis, runtime log analysis, candidate promotion, or post-game tuning.
- Normal runtime output remains limited to `GlobalValues.json`, `Mulligan.json`, per-card `<CARDID>.json`, and `Combo.json` only when a concrete valid combo exists.
- Do not emit `Presume.json` or `Concede.json` in the normal path.
- Do not weaken `SOURCE_BACKED_STRONG`; promotion still requires zero semantic blockers and zero blocked cards in `source_claim_gap_report.json`.
- Do not call a source-informed package optimized, proven, or source-backed strong.
- Runtime writes remain possible only through `hsconfig apply`.
- Source-informed runtime writes still require the explicit `--allow-source-informed` flag.
- Kingslayer and Boarlock remain the current source-informed control cases unless new deck-specific source evidence is added.
- Keep the implementation narrow; no new dependency is needed.

---

## File Structure

- Modify `src/hsconfig/operator_summary.py`: derive a new `source_informed_apply_readiness` block and set `next_action=SOURCE_INFORMED_APPLY_READY`, `apply_policy=ALLOWED_SOURCE_INFORMED` only when all source-informed apply criteria are met.
- Modify `src/hsconfig/operator_guidance.py`: surface source-informed apply as an intentional command path using `--allow-source-informed`.
- Modify `src/hsconfig/apply_gate.py`: allow source-informed packages only when the new readiness block is present, ready, and the caller passes `allow_source_informed=True`.
- Modify `src/hsconfig/strong_promotion_report.py`: keep strong promotion blocked for source-informed packages, but expose the source-informed readiness state for operator clarity.
- Modify `docs/operator/README.md`: add a compact decision table for strong, source-informed, and blocked packages.
- Modify `.agents/skills/hsconfig/SKILL.md` and `.agents/skills/hsconfig/references/workflow.md`: document the source-informed apply-ready lane without broadening HSConfig scope.
- Modify tests:
  - `tests/test_operator_summary.py`
  - `tests/test_operator_guidance.py`
  - `tests/test_apply_gate.py`
  - `tests/test_strong_promotion_report.py`
  - `tests/test_skill_files.py`

## Source-Informed Apply Criteria

The new lane is intentionally narrow.

Ready criteria:

- `technical_status == "VALID_PACKAGE"`
- `semantic_status == "VALID_BUT_NOT_GUIDE_STRONG"`
- `claim_conflicts == 0`
- `generic_low_confidence_cards == 0`
- `uncovered_cards == 0`
- `source_evidence_warnings == 0`
- all `semantic_blockers[*].reason` are in:
  - `cards_need_guide_claims`
  - `cards_need_mulligan_claims`

Hard blockers:

- `claim_conflicts_present`
- `unsupported_conditions_present`
- `cards_need_runtime_surface`
- `cards_need_combo_sequence`
- `cards_need_condition_lowering`
- `cards_need_mechanic_lowering`
- any optional normal-path surface such as `Presume.json` or `Concede.json`
- missing package structure, missing required runtime files, missing input manifest, stale `generated_files`

New operator summary shape:

```json
{
  "semantic_status": "VALID_BUT_NOT_GUIDE_STRONG",
  "next_action": "SOURCE_INFORMED_APPLY_READY",
  "apply_policy": "ALLOWED_SOURCE_INFORMED",
  "source_informed_apply_readiness": {
    "status": "ready",
    "requires_flag": "--allow-source-informed",
    "allowed_blocker_reasons": [
      "cards_need_guide_claims",
      "cards_need_mulligan_claims"
    ],
    "blocking_reasons": [],
    "source_gap_count": 1
  }
}
```

---

### Task 1: Operator Summary Readiness Lane

**Files:**
- Modify: `src/hsconfig/operator_summary.py`
- Test: `tests/test_operator_summary.py`

**Interfaces:**
- Consumes: `build_operator_summary(...) -> dict[str, Any]`
- Produces: `summary["source_informed_apply_readiness"]`, `next_action=SOURCE_INFORMED_APPLY_READY`, and `apply_policy=ALLOWED_SOURCE_INFORMED`

- [ ] **Step 1: Add failing tests for source-informed readiness**

Append these tests to `tests/test_operator_summary.py`:

```python
def test_operator_summary_marks_mulligan_only_gap_source_informed_apply_ready():
    summary = build_operator_summary(
        deck_name="Kingslayer",
        deck_code="AAE=",
        technical_validation={"status": "passed", "errors": []},
        guide_source_depth={
            "source_depth_status": "source_backed",
            "claim_count": 12,
            "source_evidence": {"warnings_count": 0},
        },
        unsupported_conditions=[],
        globalvalue_authority={"blocked_until_runtime_evidence": []},
        generated_files=["CustomConfig/kingslayer/GlobalValues.json"],
        claim_coverage_report={
            "summary": {
                "guide_backed": 10,
                "static_semantics_backfilled": 0,
                "uncovered_low_confidence": 0,
            },
            "uncovered_cards": [],
        },
        config_readiness_summary={
            "total_cards": 10,
            "runtime_emitted": 9,
            "generic_low_confidence": 0,
            "cards_needing_guide_claims": 0,
            "cards_needing_runtime_surface": 0,
            "cards_needing_mulligan_claims": 1,
            "cards_needing_combo_sequence": 0,
            "cards_needing_condition_lowering": 0,
            "cards_needing_mechanic_lowering": 0,
        },
        config_readiness_report={
            "cards": {
                "DEEP_014": {
                    "name": "Quick Pick",
                    "readiness_lane": "report_only_supported",
                    "first_missing_link": "needs_mulligan_claim",
                }
            }
        },
        claim_conflict_report={"conflict_count": 0, "conflicts": []},
    )

    assert summary["semantic_status"] == "VALID_BUT_NOT_GUIDE_STRONG"
    assert summary["next_action"] == "SOURCE_INFORMED_APPLY_READY"
    assert summary["apply_policy"] == "ALLOWED_SOURCE_INFORMED"
    assert summary["source_informed_apply_readiness"] == {
        "status": "ready",
        "requires_flag": "--allow-source-informed",
        "allowed_blocker_reasons": [
            "cards_need_guide_claims",
            "cards_need_mulligan_claims",
        ],
        "blocking_reasons": [],
        "source_gap_count": 1,
    }


def test_operator_summary_blocks_source_informed_apply_when_runtime_surface_gap_exists():
    summary = build_operator_summary(
        deck_name="Fixture",
        deck_code="AAE=",
        technical_validation={"status": "passed", "errors": []},
        guide_source_depth={
            "source_depth_status": "source_backed",
            "claim_count": 12,
            "source_evidence": {"warnings_count": 0},
        },
        unsupported_conditions=[],
        globalvalue_authority={"blocked_until_runtime_evidence": []},
        generated_files=["CustomConfig/fixture/GlobalValues.json"],
        claim_coverage_report={
            "summary": {
                "guide_backed": 10,
                "static_semantics_backfilled": 0,
                "uncovered_low_confidence": 0,
            },
            "uncovered_cards": [],
        },
        config_readiness_summary={
            "total_cards": 10,
            "generic_low_confidence": 0,
            "cards_needing_guide_claims": 0,
            "cards_needing_runtime_surface": 1,
            "cards_needing_mulligan_claims": 0,
            "cards_needing_combo_sequence": 0,
            "cards_needing_condition_lowering": 0,
            "cards_needing_mechanic_lowering": 0,
        },
        config_readiness_report={
            "cards": {
                "CARD_A": {
                    "name": "Needs Runtime Surface",
                    "readiness_lane": "report_only_supported",
                    "first_missing_link": "needs_runtime_surface",
                }
            }
        },
        claim_conflict_report={"conflict_count": 0, "conflicts": []},
    )

    assert summary["semantic_status"] == "VALID_BUT_NOT_GUIDE_STRONG"
    assert summary["next_action"] == "IMPROVE_GUIDE_SOURCES_BEFORE_STRONG_APPLY"
    assert summary["apply_policy"] == "ALLOWED_WITH_WARNINGS"
    assert summary["source_informed_apply_readiness"]["status"] == "blocked"
    assert summary["source_informed_apply_readiness"]["blocking_reasons"] == [
        "cards_need_runtime_surface"
    ]
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
python -m pytest tests/test_operator_summary.py::test_operator_summary_marks_mulligan_only_gap_source_informed_apply_ready tests/test_operator_summary.py::test_operator_summary_blocks_source_informed_apply_when_runtime_surface_gap_exists -q
```

Expected: both tests fail because `source_informed_apply_readiness`, `SOURCE_INFORMED_APPLY_READY`, and `ALLOWED_SOURCE_INFORMED` do not exist yet.

- [ ] **Step 3: Implement readiness helper**

In `src/hsconfig/operator_summary.py`, add these constants near `READINESS_GAP_SUMMARY_KEYS`:

```python
SOURCE_INFORMED_ALLOWED_BLOCKER_REASONS = [
    "cards_need_guide_claims",
    "cards_need_mulligan_claims",
]
SOURCE_INFORMED_BLOCKING_REASONS = {
    "cards_need_runtime_surface",
    "cards_need_combo_sequence",
    "cards_need_condition_lowering",
    "cards_need_mechanic_lowering",
    "claim_conflicts_present",
    "unsupported_conditions_present",
}
```

Add this helper below `_semantic_blockers(...)`:

```python
def _source_informed_apply_readiness(
    *,
    technical_status: str,
    semantic_status: str,
    guide_strength_summary: dict[str, Any],
    semantic_blockers: list[dict[str, Any]],
) -> dict[str, Any]:
    allowed_reasons = list(SOURCE_INFORMED_ALLOWED_BLOCKER_REASONS)
    if technical_status != "VALID_PACKAGE":
        return {
            "status": "not_applicable",
            "requires_flag": "--allow-source-informed",
            "allowed_blocker_reasons": allowed_reasons,
            "blocking_reasons": ["invalid_package"],
            "source_gap_count": 0,
        }
    if semantic_status != "VALID_BUT_NOT_GUIDE_STRONG":
        return {
            "status": "not_applicable",
            "requires_flag": "--allow-source-informed",
            "allowed_blocker_reasons": allowed_reasons,
            "blocking_reasons": [],
            "source_gap_count": 0,
        }

    blocker_reasons = [
        str(blocker.get("reason", ""))
        for blocker in semantic_blockers
        if isinstance(blocker, dict)
    ]
    hard_reasons = sorted(
        {
            reason
            for reason in blocker_reasons
            if reason not in SOURCE_INFORMED_ALLOWED_BLOCKER_REASONS
        }
    )
    if _int_value(guide_strength_summary.get("generic_low_confidence_cards", 0)) > 0:
        hard_reasons.append("generic_low_confidence_cards")
    if _int_value(guide_strength_summary.get("uncovered_cards", 0)) > 0:
        hard_reasons.append("uncovered_cards")
    if _int_value(guide_strength_summary.get("claim_conflicts", 0)) > 0:
        hard_reasons.append("claim_conflicts_present")
    if _int_value(guide_strength_summary.get("source_evidence_warnings", 0)) > 0:
        hard_reasons.append("source_evidence_warnings")

    source_gap_count = sum(
        int(blocker.get("count", 0))
        for blocker in semantic_blockers
        if isinstance(blocker, dict)
        and str(blocker.get("reason", "")) in SOURCE_INFORMED_ALLOWED_BLOCKER_REASONS
    )
    return {
        "status": "blocked" if hard_reasons else "ready",
        "requires_flag": "--allow-source-informed",
        "allowed_blocker_reasons": allowed_reasons,
        "blocking_reasons": sorted(set(hard_reasons)),
        "source_gap_count": source_gap_count,
    }
```

- [ ] **Step 4: Wire readiness into `build_operator_summary`**

In `build_operator_summary`, move the call to `_next_action_and_policy(...)` after `guide_strength_summary` and `semantic_blockers` are computed. Then add:

```python
    source_informed_apply_readiness = _source_informed_apply_readiness(
        technical_status=technical_status,
        semantic_status=semantic_status,
        guide_strength_summary=guide_strength_summary,
        semantic_blockers=semantic_blockers,
    )
    next_action, apply_policy = _next_action_and_policy(
        technical_status=technical_status,
        semantic_status=semantic_status,
        primary_blockers=primary_blockers,
        source_informed_apply_ready=source_informed_apply_readiness["status"] == "ready",
    )
```

Add this field to `summary`:

```python
        "source_informed_apply_readiness": source_informed_apply_readiness,
```

Change `_next_action_and_policy` signature and body:

```python
def _next_action_and_policy(
    *,
    technical_status: str,
    semantic_status: str,
    primary_blockers: list[dict[str, str]],
    source_informed_apply_ready: bool = False,
) -> tuple[str, str]:
    if technical_status == "INVALID_PACKAGE" or primary_blockers:
        return "FIX_PACKAGE_BEFORE_APPLY", "BLOCKED"
    if semantic_status == "SOURCE_BACKED_STRONG":
        return "READY_TO_APPLY_OR_HANDOFF", "ALLOWED"
    if source_informed_apply_ready:
        return "SOURCE_INFORMED_APPLY_READY", "ALLOWED_SOURCE_INFORMED"
    if semantic_status == "STATIC_SEMANTICS_USABLE":
        return "READY_WITH_WARNINGS", "ALLOWED_WITH_WARNINGS"
    if semantic_status == "VALID_BUT_NOT_GUIDE_STRONG":
        return "IMPROVE_GUIDE_SOURCES_BEFORE_STRONG_APPLY", "ALLOWED_WITH_WARNINGS"
    return "RESEARCH_REQUIRED_BEFORE_STRONG_CONFIG", "ALLOWED_WITH_WARNINGS"
```

- [ ] **Step 5: Run operator summary tests**

Run:

```powershell
python -m pytest tests/test_operator_summary.py -q
```

Expected: all operator summary tests pass.

- [ ] **Step 6: Commit Task 1**

```powershell
git add src\hsconfig\operator_summary.py tests\test_operator_summary.py
git commit -m "feat: add source-informed apply readiness"
```

---

### Task 2: Operator Guidance For Explicit Source-Informed Apply

**Files:**
- Modify: `src/hsconfig/operator_guidance.py`
- Test: `tests/test_operator_guidance.py`

**Interfaces:**
- Consumes: `summary["apply_policy"] == "ALLOWED_SOURCE_INFORMED"`
- Produces: `operator_guidance.normal_next_step == "apply_source_informed"` and `normal_next_command` containing `--allow-source-informed`

- [ ] **Step 1: Add failing guidance test**

Append this test to `tests/test_operator_guidance.py`:

```python
def test_operator_guidance_routes_source_informed_apply_ready_to_explicit_flag():
    guidance = build_operator_guidance(
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "VALID_BUT_NOT_GUIDE_STRONG",
            "next_action": "SOURCE_INFORMED_APPLY_READY",
            "apply_policy": "ALLOWED_SOURCE_INFORMED",
            "source_informed_apply_readiness": {
                "status": "ready",
                "requires_flag": "--allow-source-informed",
            },
            "semantic_blockers": [
                {
                    "reason": "cards_need_mulligan_claims",
                    "report": "reports/per_card_config_readiness_report.json",
                }
            ],
        }
    )

    assert guidance == {
        "first_report_to_open": "reports/operator_summary.json",
        "next_report_to_open": "reports/per_card_config_readiness_report.json",
        "normal_next_step": "apply_source_informed",
        "normal_next_command": (
            "hsconfig apply --package <package> --runtime-root <runtime-root> "
            "--allow-source-informed --json"
        ),
        "safe_to_apply": True,
        "requires_expert_flag": True,
    }
```

- [ ] **Step 2: Run guidance test and verify it fails**

Run:

```powershell
python -m pytest tests/test_operator_guidance.py::test_operator_guidance_routes_source_informed_apply_ready_to_explicit_flag -q
```

Expected: fail because `ALLOWED_SOURCE_INFORMED` is not handled yet.

- [ ] **Step 3: Implement guidance branch**

In `src/hsconfig/operator_guidance.py`, add this branch after the source-backed-strong branch and before the `VALID_BUT_NOT_GUIDE_STRONG` improve-sources branch:

```python
    if (
        semantic_status == "VALID_BUT_NOT_GUIDE_STRONG"
        and apply_policy == "ALLOWED_SOURCE_INFORMED"
        and summary.get("source_informed_apply_readiness", {}).get("status") == "ready"
    ):
        return {
            "first_report_to_open": "reports/operator_summary.json",
            "next_report_to_open": _first_semantic_blocker_report(summary)
            or "reports/source_claim_gap_report.json",
            "normal_next_step": "apply_source_informed",
            "normal_next_command": (
                "hsconfig apply --package <package> --runtime-root <runtime-root> "
                "--allow-source-informed --json"
            ),
            "safe_to_apply": True,
            "requires_expert_flag": True,
        }
```

- [ ] **Step 4: Run guidance tests**

Run:

```powershell
python -m pytest tests/test_operator_guidance.py tests/test_operator_summary.py -q
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit Task 2**

```powershell
git add src\hsconfig\operator_guidance.py tests\test_operator_guidance.py
git commit -m "feat: guide source-informed apply handoff"
```

---

### Task 3: Apply Gate Uses New Readiness Contract

**Files:**
- Modify: `src/hsconfig/apply_gate.py`
- Test: `tests/test_apply_gate.py`
- Test: `tests/test_runtime_apply.py`

**Interfaces:**
- Consumes: `operator_summary.json` with `apply_policy=ALLOWED_SOURCE_INFORMED`
- Produces: `evaluate_apply_gate(..., allow_source_informed=True)["mode"] == "source_informed_apply_ready"`

- [ ] **Step 1: Add failing apply-gate tests**

In `tests/test_apply_gate.py`, add this test after `test_apply_gate_blocks_valid_but_not_guide_strong_by_default`:

```python
def test_apply_gate_allows_source_informed_apply_ready_only_with_flag(tmp_path: Path):
    package = tmp_path / "package"
    _write_minimal_runtime_package(package)
    _write_operator_summary(
        package,
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "VALID_BUT_NOT_GUIDE_STRONG",
            "next_action": "SOURCE_INFORMED_APPLY_READY",
            "apply_policy": "ALLOWED_SOURCE_INFORMED",
            "semantic_blockers": [{"reason": "cards_need_mulligan_claims", "count": 1}],
            "source_informed_apply_readiness": {
                "status": "ready",
                "requires_flag": "--allow-source-informed",
                "allowed_blocker_reasons": [
                    "cards_need_guide_claims",
                    "cards_need_mulligan_claims",
                ],
                "blocking_reasons": [],
                "source_gap_count": 1,
            },
            "generated_files": [
                "CustomConfig\\deck\\GlobalValues.json",
                "CustomConfig\\deck\\Mulligan.json",
                "CustomConfig\\deck\\EX1_001.json",
            ],
        },
    )

    blocked = evaluate_apply_gate(package)
    allowed = evaluate_apply_gate(package, allow_source_informed=True)

    assert blocked["status"] == "blocked"
    assert blocked["reasons"][0]["reason"] == "operator_summary_not_ready_to_apply"
    assert allowed == {
        "status": "allowed",
        "operator_summary_path": str(package / "reports" / "operator_summary.json"),
        "mode": "source_informed_apply_ready",
        "reasons": [
            {
                "reason": "source_informed_apply_profile_used",
                "semantic_status": "VALID_BUT_NOT_GUIDE_STRONG",
                "next_action": "SOURCE_INFORMED_APPLY_READY",
                "apply_policy": "ALLOWED_SOURCE_INFORMED",
                "source_gap_count": 1,
            }
        ],
    }


def test_apply_gate_blocks_source_informed_policy_when_readiness_is_not_ready(tmp_path: Path):
    package = tmp_path / "package"
    _write_minimal_runtime_package(package)
    _write_operator_summary(
        package,
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "VALID_BUT_NOT_GUIDE_STRONG",
            "next_action": "SOURCE_INFORMED_APPLY_READY",
            "apply_policy": "ALLOWED_SOURCE_INFORMED",
            "semantic_blockers": [{"reason": "cards_need_runtime_surface", "count": 1}],
            "source_informed_apply_readiness": {
                "status": "blocked",
                "requires_flag": "--allow-source-informed",
                "allowed_blocker_reasons": [
                    "cards_need_guide_claims",
                    "cards_need_mulligan_claims",
                ],
                "blocking_reasons": ["cards_need_runtime_surface"],
                "source_gap_count": 0,
            },
            "generated_files": [
                "CustomConfig\\deck\\GlobalValues.json",
                "CustomConfig\\deck\\Mulligan.json",
                "CustomConfig\\deck\\EX1_001.json",
            ],
        },
    )

    gate = evaluate_apply_gate(package, allow_source_informed=True)

    assert gate["status"] == "blocked"
    assert gate["reasons"][0] == {
        "reason": "operator_summary_not_ready_to_apply",
        "technical_status": "VALID_PACKAGE",
        "semantic_status": "VALID_BUT_NOT_GUIDE_STRONG",
        "next_action": "SOURCE_INFORMED_APPLY_READY",
        "apply_policy": "ALLOWED_SOURCE_INFORMED",
    }
```

- [ ] **Step 2: Run apply-gate tests and verify they fail**

Run:

```powershell
python -m pytest tests/test_apply_gate.py::test_apply_gate_allows_source_informed_apply_ready_only_with_flag tests/test_apply_gate.py::test_apply_gate_blocks_source_informed_policy_when_readiness_is_not_ready -q
```

Expected: first test fails because `ALLOWED_SOURCE_INFORMED` is not accepted yet.

- [ ] **Step 3: Implement new apply-gate branch**

In `src/hsconfig/apply_gate.py`, replace the existing source-informed branch:

```python
    if (
        allow_source_informed
        and semantic_status in {"VALID_BUT_NOT_GUIDE_STRONG", "STATIC_SEMANTICS_USABLE"}
        and apply_policy == "ALLOWED_WITH_WARNINGS"
        and next_action
        in {
            "IMPROVE_GUIDE_SOURCES_BEFORE_STRONG_APPLY",
            "READY_WITH_WARNINGS",
            "RESEARCH_REQUIRED_BEFORE_STRONG_CONFIG",
        }
    ):
```

with:

```python
    source_informed_readiness = summary.get("source_informed_apply_readiness", {})
    if (
        allow_source_informed
        and semantic_status == "VALID_BUT_NOT_GUIDE_STRONG"
        and next_action == "SOURCE_INFORMED_APPLY_READY"
        and apply_policy == "ALLOWED_SOURCE_INFORMED"
        and isinstance(source_informed_readiness, dict)
        and source_informed_readiness.get("status") == "ready"
    ):
        return _allowed(
            operator_path,
            mode="source_informed_apply_ready",
            reasons=[
                {
                    "reason": "source_informed_apply_profile_used",
                    "semantic_status": semantic_status,
                    "next_action": next_action,
                    "apply_policy": apply_policy,
                    "source_gap_count": int(
                        source_informed_readiness.get("source_gap_count", 0)
                    ),
                }
            ],
        )
```

Keep the final `_blocked(...)` fallback unchanged so source-informed packages remain blocked without the explicit flag.

- [ ] **Step 4: Update existing legacy source-informed test expectations**

In `tests/test_apply_gate.py`, update `test_apply_gate_allows_valid_source_informed_package_only_with_explicit_escape_hatch` so it uses the new operator summary shape:

```python
            "next_action": "SOURCE_INFORMED_APPLY_READY",
            "apply_policy": "ALLOWED_SOURCE_INFORMED",
            "source_informed_apply_readiness": {
                "status": "ready",
                "requires_flag": "--allow-source-informed",
                "allowed_blocker_reasons": [
                    "cards_need_guide_claims",
                    "cards_need_mulligan_claims",
                ],
                "blocking_reasons": [],
                "source_gap_count": 1,
            },
```

Change the expected mode and reason:

```python
    assert gate["mode"] == "source_informed_apply_ready"
    assert gate["reasons"][0]["reason"] == "source_informed_apply_profile_used"
```

- [ ] **Step 5: Update runtime apply tests**

Run the current runtime apply tests:

```powershell
python -m pytest tests/test_runtime_apply.py -q
```

If tests fail only because they still expect `source_informed_with_warnings`, update their expected mode to `source_informed_apply_ready` and use the same source-informed readiness payload from Step 4.

- [ ] **Step 6: Run apply/runtime tests**

Run:

```powershell
python -m pytest tests/test_apply_gate.py tests/test_runtime_apply.py -q
```

Expected: all selected tests pass.

- [ ] **Step 7: Commit Task 3**

```powershell
git add src\hsconfig\apply_gate.py tests\test_apply_gate.py tests\test_runtime_apply.py
git commit -m "feat: enforce source-informed apply readiness"
```

---

### Task 4: Strong Promotion Report Remains Strict

**Files:**
- Modify: `src/hsconfig/strong_promotion_report.py`
- Test: `tests/test_strong_promotion_report.py`

**Interfaces:**
- Consumes: `operator_summary["source_informed_apply_readiness"]`
- Produces: `strong_promotion_report["source_informed_apply_readiness"]`

- [ ] **Step 1: Add failing strict-promotion test**

Append this test to `tests/test_strong_promotion_report.py`:

```python
def test_strong_promotion_report_exposes_source_informed_ready_without_promoting():
    report = build_strong_promotion_report(
        deck_name="Kingslayer",
        fixture_stage="source_informed_valid_fixture",
        operator_summary={
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "VALID_BUT_NOT_GUIDE_STRONG",
            "next_action": "SOURCE_INFORMED_APPLY_READY",
            "apply_policy": "ALLOWED_SOURCE_INFORMED",
            "semantic_blockers": [{"reason": "cards_need_mulligan_claims", "count": 1}],
            "source_informed_apply_readiness": {
                "status": "ready",
                "requires_flag": "--allow-source-informed",
                "source_gap_count": 1,
            },
        },
        source_claim_gap_report={
            "summary": {"blocked_cards": 1},
            "cards": {
                "DEEP_014": {
                    "first_missing_link": "needs_mulligan_claim",
                    "recommended_source_claim_kind": "mulligan_keep",
                    "next_action": "add_mulligan_keep_or_discard_claim",
                }
            },
        },
    )

    assert report["promotion_ready"] is False
    assert report["verdict"] == "PROMOTION_BLOCKED"
    assert report["next_action"] == "source_informed_apply_ready_but_not_strong"
    assert report["source_informed_apply_readiness"]["status"] == "ready"
```

- [ ] **Step 2: Run strict-promotion test and verify it fails**

Run:

```powershell
python -m pytest tests/test_strong_promotion_report.py::test_strong_promotion_report_exposes_source_informed_ready_without_promoting -q
```

Expected: fail because the report does not expose source-informed readiness and returns `close_first_missing_chain`.

- [ ] **Step 3: Implement strict-promotion visibility**

In `src/hsconfig/strong_promotion_report.py`, add this field to the returned dict:

```python
        "source_informed_apply_readiness": operator_summary.get(
            "source_informed_apply_readiness",
            {"status": "not_applicable"},
        ),
```

Change `_report_next_action(...)`:

```python
def _report_next_action(
    *,
    promotion_ready: bool,
    operator_summary: dict[str, Any],
    first_missing_chain: dict[str, str] | None,
) -> str:
    if promotion_ready:
        return "fixture_can_be_core_source_backed"
    if operator_summary.get("technical_status") != "VALID_PACKAGE":
        return str(operator_summary.get("next_action", ""))
    if (
        operator_summary.get("next_action") == "SOURCE_INFORMED_APPLY_READY"
        and operator_summary.get("source_informed_apply_readiness", {}).get("status")
        == "ready"
    ):
        return "source_informed_apply_ready_but_not_strong"
    return "close_first_missing_chain"
```

- [ ] **Step 4: Run promotion tests**

Run:

```powershell
python -m pytest tests/test_strong_promotion_report.py tests/test_matrix_current_truth.py -q
```

Expected: all selected tests pass. Kingslayer and Boarlock remain source-informed, not strong.

- [ ] **Step 5: Commit Task 4**

```powershell
git add src\hsconfig\strong_promotion_report.py tests\test_strong_promotion_report.py
git commit -m "feat: expose source-informed readiness in promotion report"
```

---

### Task 5: Operator And Skill Docs

**Files:**
- Modify: `docs/operator/README.md`
- Modify: `.agents/skills/hsconfig/SKILL.md`
- Modify: `.agents/skills/hsconfig/references/workflow.md`
- Test: `tests/test_skill_files.py`

**Interfaces:**
- Consumes: new readiness field and apply policy from Tasks 1-4
- Produces: docs that tell operators exactly when to apply strong, apply source-informed, or block

- [ ] **Step 1: Add failing docs tests**

Append this test to `tests/test_skill_files.py`:

```python
def test_docs_explain_source_informed_apply_ready_lane():
    docs = "\n".join(
        [
            Path("docs/operator/README.md").read_text(encoding="utf-8"),
            Path(".agents/skills/hsconfig/SKILL.md").read_text(encoding="utf-8"),
            Path(".agents/skills/hsconfig/references/workflow.md").read_text(
                encoding="utf-8"
            ),
        ]
    )

    assert "SOURCE_INFORMED_APPLY_READY" in docs
    assert "ALLOWED_SOURCE_INFORMED" in docs
    assert "--allow-source-informed" in docs
    assert "does not mean `SOURCE_BACKED_STRONG`" in docs
    assert "cards_need_runtime_surface" in docs
    assert "cards_need_mulligan_claims" in docs
```

- [ ] **Step 2: Run docs test and verify it fails**

Run:

```powershell
python -m pytest tests/test_skill_files.py::test_docs_explain_source_informed_apply_ready_lane -q
```

Expected: fail because the new lane is not documented yet.

- [ ] **Step 3: Update operator README**

In `docs/operator/README.md`, add this section after `## Single Gate`:

```markdown
## Apply Decision Table

| Operator summary state | Meaning | Normal command |
|---|---|---|
| `semantic_status=SOURCE_BACKED_STRONG`, `next_action=READY_TO_APPLY_OR_HANDOFF`, `apply_policy=ALLOWED` | Strong source-backed package. | `hsconfig apply --package <package> --runtime-root <runtime-root> --json` |
| `semantic_status=VALID_BUT_NOT_GUIDE_STRONG`, `next_action=SOURCE_INFORMED_APPLY_READY`, `apply_policy=ALLOWED_SOURCE_INFORMED` | Valid aggressive source-informed package. It does not mean `SOURCE_BACKED_STRONG`; open `source_informed_apply_readiness` and the first blocker report before applying. | `hsconfig apply --package <package> --runtime-root <runtime-root> --allow-source-informed --json` |
| `apply_policy=BLOCKED` or `source_informed_apply_readiness.status=blocked` | Do not apply. Fix package structure, conflicts, unsupported conditions, or lowering gaps first. | Run `hsconfig validate --package <package> --json` and follow `reports/operator_summary.json`. |

Source-informed apply is allowed only for visible source gaps such as `cards_need_guide_claims` or `cards_need_mulligan_claims`. It is blocked for `cards_need_runtime_surface`, `cards_need_combo_sequence`, `cards_need_condition_lowering`, `cards_need_mechanic_lowering`, claim conflicts, unsupported conditions, and normal-path optional surfaces.
```

- [ ] **Step 4: Update skill entrypoint**

In `.agents/skills/hsconfig/SKILL.md`, add this paragraph under Status meaning:

```markdown
- `SOURCE_INFORMED_APPLY_READY` is a `next_action`, not a strong semantic status. It means the package is technically valid and source-informed apply can be intentional with `--allow-source-informed`, but it does not mean `SOURCE_BACKED_STRONG`.
- `ALLOWED_SOURCE_INFORMED` requires `source_informed_apply_readiness.status=ready` and an explicit apply flag. It is meant for aggressive initial configs where only guide or mulligan source-depth gaps remain.
```

- [ ] **Step 5: Update workflow reference**

In `.agents/skills/hsconfig/references/workflow.md`, add this paragraph under Readiness Interpretation:

```markdown
`SOURCE_INFORMED_APPLY_READY` is the aggressive valid-but-not-strong lane. It appears only when the package is technically valid, source-informed gaps are limited to guide or mulligan source-depth, and no hard blockers remain. Apply still requires `hsconfig apply --allow-source-informed`; the package remains `VALID_BUT_NOT_GUIDE_STRONG`, not `SOURCE_BACKED_STRONG`.
```

- [ ] **Step 6: Run docs tests and sync check**

Run:

```powershell
python -m pytest tests/test_skill_files.py tests/test_scope_boundaries.py -q
python scripts\sync_installed_skill.py --check
```

Expected: tests pass; sync check fails if `.agents/skills/hsconfig` changed but installed skill was not synced.

- [ ] **Step 7: Sync installed skill if needed**

If the sync check fails, run:

```powershell
python scripts\sync_installed_skill.py
python scripts\sync_installed_skill.py --check
```

Expected: final sync check prints `HSConfig skill is in sync`.

- [ ] **Step 8: Commit Task 5**

```powershell
git add docs\operator\README.md .agents\skills\hsconfig\SKILL.md .agents\skills\hsconfig\references\workflow.md tests\test_skill_files.py
git add C:\Users\darbo\.codex\skills\hsconfig
git commit -m "docs: document source-informed apply readiness"
```

---

### Task 6: End-To-End Fixture Proof For Kingslayer And Boarlock

**Files:**
- Modify: `tests/test_fixture_source_depth_closure.py`
- Modify: `tests/test_matrix_current_truth.py`

**Interfaces:**
- Consumes: source-informed apply readiness from generated operator summaries
- Produces: regression coverage proving Kingslayer and Boarlock are apply-ready source-informed, but not strong

- [ ] **Step 1: Add matrix proof test**

Append this test to `tests/test_matrix_current_truth.py`:

```python
def test_source_informed_rows_are_expected_current_apply_ready_candidates():
    matrix = json.loads(Path("docs/operator/archetype-fixture-matrix.json").read_text())
    source_informed = {
        row["deck_name"]: row["strongness_visibility"]["first_strongness_gap"]
        for row in matrix["decks"]
        if row["fixture_stage"] == "source_informed_valid_fixture"
    }

    assert source_informed == {
        "Kingslayer": "needs_mulligan_claim_for_quick_pick",
        "Boarlock": "needs_mulligan_claim_for_fracking",
    }
```

- [ ] **Step 2: Extend source-depth closure fixture test**

In `tests/test_fixture_source_depth_closure.py`, extend the source-informed row assertion so it checks:

```python
    assert operator_summary["semantic_status"] == "VALID_BUT_NOT_GUIDE_STRONG"
    assert operator_summary["next_action"] == "SOURCE_INFORMED_APPLY_READY"
    assert operator_summary["apply_policy"] == "ALLOWED_SOURCE_INFORMED"
    assert operator_summary["source_informed_apply_readiness"]["status"] == "ready"
```

Keep existing assertions that these rows do not become `SOURCE_BACKED_STRONG`.

- [ ] **Step 3: Run targeted fixture tests**

Run:

```powershell
python -m pytest tests/test_fixture_source_depth_closure.py tests/test_matrix_current_truth.py -q
```

Expected: tests pass after Tasks 1-5. If either deck has a hard blocker beyond mulligan/guide source depth, the test should fail and the implementer must inspect `reports/source_claim_gap_report.json` and `reports/per_card_config_readiness_report.json` from that fixture run.

- [ ] **Step 4: Commit Task 6**

```powershell
git add tests\test_fixture_source_depth_closure.py tests\test_matrix_current_truth.py
git commit -m "test: prove source-informed fixture apply readiness"
```

---

### Task 7: Final Verification And GitHub Hygiene

**Files:**
- Verify all touched files
- No implementation file should remain unstaged after commit

**Interfaces:**
- Consumes: all prior tasks
- Produces: green suite, synced installed skill, clean branch ready to push

- [ ] **Step 1: Run focused regression tests**

Run:

```powershell
python -m pytest tests/test_operator_summary.py tests/test_operator_guidance.py tests/test_apply_gate.py tests/test_runtime_apply.py tests/test_strong_promotion_report.py tests/test_fixture_source_depth_closure.py tests/test_matrix_current_truth.py tests/test_skill_files.py -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run full test suite**

Run:

```powershell
python -m pytest -q
```

Expected: full suite passes with only the existing intentional skips.

- [ ] **Step 3: Run installed skill sync check**

Run:

```powershell
python scripts\sync_installed_skill.py --check
```

Expected:

```text
HSConfig skill is in sync: C:\Users\darbo\.codex\skills\hsconfig
```

- [ ] **Step 4: Run active-doc stale language scan**

Run:

```powershell
rg -n "seven `source_informed_valid_fixture` rows|4 core_source_backed_fixture|7 source_informed_valid_fixture|source_informed_with_warnings" README.md docs\operator .agents\skills\hsconfig src tests
```

Expected: no active-doc/code hits for stale row counts or the old source-informed mode. Historical plan or research files under `docs/superpowers/plans` and `docs/research` may still contain old wording and are not active operator guidance.

- [ ] **Step 5: Inspect git status**

Run:

```powershell
git status --short --branch
```

Expected: branch is ahead of `origin/main` by the task commits and has no unstaged changes.

- [ ] **Step 6: Push**

Run:

```powershell
git push origin main
```

Expected: push succeeds.

---

## Self-Review

- Spec coverage: The plan implements the recommended source-informed apply lane, keeps strong promotion strict, preserves explicit `--allow-source-informed`, updates operator guidance, updates docs, and proves Kingslayer/Boarlock as source-informed controls.
- Placeholder scan: No task uses forbidden placeholder wording or unspecified test instructions.
- Type consistency: `source_informed_apply_readiness` is a dict stored in `operator_summary.json`; `apply_policy` uses `ALLOWED_SOURCE_INFORMED`; `next_action` uses `SOURCE_INFORMED_APPLY_READY`; `evaluate_apply_gate(package_root: str | Path, *, allow_source_informed: bool = False) -> dict[str, Any]` stays unchanged.
- Scope check: The plan does not add replay parsing, HSTuner logic, winrate validation, new dependencies, or extra runtime surfaces.
- Risk note: If current Kingslayer or Boarlock fixture preparation exposes a hard blocker beyond guide/mulligan source depth, Task 6 must keep that deck blocked and update the matrix proof to show the exact hard blocker instead of forcing source-informed apply readiness.

# HSConfig Surface Intent Summary Projection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Project the already-generated `reports/surface_intent.json` into existing config-quality, proof, and handoff summaries without creating a new runtime gate or gameplay policy layer.

**Architecture:** Keep `surface_intent.json` as the source artifact already produced by package generation. Add a read-only diagnostic check in `config_quality_contract.py`, then expose a compact subset through existing `configure.py` summary builders. Do not feed this projection into apply, runtime writes, HearthRanger play sequencing, or operator authority decisions.

**Tech Stack:** Python 3, pytest, existing `hsconfig` package, existing JSON package reports.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig`.
- Keep the change narrow: no new dependency, no new CLI command, no new report file, no new apply gate.
- `reports/operator_summary.json` remains the single normal apply authority.
- `surface_intent_projection` is diagnostic-only: `apply_blocking=False` and `runtime_write_performed=False`.
- Missing `reports/surface_intent.json` must not make an otherwise usable package unusable.
- Do not introduce HSTuner, log parsing, HearthRanger play-order rules, or gameplay simulation.
- Keep `Presume.json` and `Concede.json` forbidden as normal runtime surfaces.
- Finish with a clean worktree after commit.

---

## File Structure

- Modify `src/hsconfig/config_quality_contract.py`
  - Read `reports/surface_intent.json`.
  - Add `_surface_intent_projection_check(surface_intent: Mapping[str, Any]) -> dict[str, Any]`.
  - Add the check under `checks["surface_intent_projection"]`.
  - Do not add this check to `_problems()`.
- Modify `src/hsconfig/commands/configure.py`
  - Add compact summary fields in `_compact_config_quality_summary()`.
  - Carry the same fields through `_build_config_proof_summary()`.
  - Carry the same fields through `_build_handoff_contract()`.
- Modify `tests/test_config_quality_contract.py`
  - Extend the minimal test package with `reports/surface_intent.json`.
  - Add clean and attention-path assertions for the new diagnostic projection.
- Modify `tests/test_configure_handoff_contract.py`
  - Assert that proof/handoff summaries preserve the new fields.
- Modify `tests/test_no_second_gate_contract.py`
  - Assert the new projection is not consumed by apply or runtime-write paths.

---

### Task 1: Add Read-Only Surface Intent Projection Check

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\config_quality_contract.py`
- Test: `C:\Users\darbo\Documents\HSConfig\tests\test_config_quality_contract.py`

**Interfaces:**
- Consumes: existing `_read_json(path: Path) -> Any`, `_list_of_mappings(value: Any) -> list[dict[str, Any]]`, `_int_value(value: Any) -> int`.
- Produces: `_surface_intent_projection_check(surface_intent: Mapping[str, Any]) -> dict[str, Any]`.
- Produces: `report["checks"]["surface_intent_projection"]`.

- [ ] **Step 1: Write the clean-path failing test**

In `tests/test_config_quality_contract.py`, add this `surface_intent.json` fixture write near the end of `minimal_clean_package()` before `return package`:

```python
    write_json(
        package / "reports" / "surface_intent.json",
        {
            "rows": [
                {
                    "rule_id": "globalvalues_full_key_profile",
                    "card_id": None,
                    "surface": "GlobalValues.json",
                    "intent": "profile_and_overlay_full_global_values",
                    "source_claim_ids": ["claim_mind_sear_effect"],
                },
                {
                    "rule_id": "NX2_019_card_behavior",
                    "card_id": "NX2_019",
                    "surface": "NX2_019.json",
                    "surface_family": "CARDID.json",
                    "intent": "conditional_minion_death_burn",
                    "intent_source": "card_intent_taxonomy",
                    "source_claim_ids": ["claim_mind_sear_effect"],
                },
            ],
            "required_surfaces": [
                "GlobalValues.json",
                "Mulligan.json",
                "NX2_019.json",
            ],
            "optional_surfaces": [],
            "minimum_required_runtime_surfaces": [
                "GlobalValues.json",
                "Mulligan.json",
            ],
            "rich_optional_runtime_surfaces": ["NX2_019.json"],
            "surface_count": 3,
        },
    )
```

In `test_config_quality_report_is_clean_for_source_backed_runtime_lean_package()`, add these assertions after the `semantic_intent_coverage` assertion:

```python
    assert report["checks"]["surface_intent_projection"] == {
        "authority": "diagnostic_only",
        "apply_blocking": False,
        "runtime_write_performed": False,
        "present": True,
        "status": "clean",
        "surface_count": 3,
        "row_count": 2,
        "required_surfaces": [
            "GlobalValues.json",
            "Mulligan.json",
            "NX2_019.json",
        ],
        "optional_surfaces": [],
        "rich_optional_runtime_surfaces": ["NX2_019.json"],
        "fallback_intent_rows": [],
        "legacy_policy_surface_rows": [],
        "attention": [],
        "first_attention": None,
    }
    compact = _compact_config_quality_summary(report)
    assert compact["surface_intent_status"] == "clean"
    assert compact["surface_intent_present"] is True
    assert compact["surface_intent_surface_count"] == 3
    assert compact["surface_intent_fallback_intent_rows"] == 0
    assert compact["surface_intent_legacy_policy_surface_rows"] == []
```

- [ ] **Step 2: Run the clean-path test to verify it fails**

Run:

```powershell
pytest tests/test_config_quality_contract.py::test_config_quality_report_is_clean_for_source_backed_runtime_lean_package -q
```

Expected: FAIL with `KeyError: 'surface_intent_projection'`.

- [ ] **Step 3: Add the diagnostic projection implementation**

In `src/hsconfig/config_quality_contract.py`, add this read after `semantic_enrichment` is normalized in `build_config_quality_report()`:

```python
    surface_intent = _read_json(package / "reports" / "surface_intent.json")
    if not isinstance(surface_intent, Mapping):
        surface_intent = {}
```

In the `checks = { ... }` literal, add this entry after `config_intent_self_audit`:

```python
        "surface_intent_projection": _surface_intent_projection_check(
            surface_intent
        ),
```

Add this helper near `_semantic_intent_coverage_check()`:

```python
def _surface_intent_projection_check(
    surface_intent: Mapping[str, Any],
) -> dict[str, Any]:
    if not surface_intent:
        return {
            "authority": "diagnostic_only",
            "apply_blocking": False,
            "runtime_write_performed": False,
            "present": False,
            "status": "missing",
            "surface_count": 0,
            "row_count": 0,
            "required_surfaces": [],
            "optional_surfaces": [],
            "rich_optional_runtime_surfaces": [],
            "fallback_intent_rows": [],
            "legacy_policy_surface_rows": [],
            "attention": [],
            "first_attention": None,
        }

    rows = _list_of_mappings(surface_intent.get("rows"))
    fallback_rows = [
        {
            "card_id": str(row.get("card_id") or ""),
            "surface": str(row.get("surface") or ""),
            "intent": str(row.get("intent") or ""),
        }
        for row in rows
        if str(row.get("intent_source") or "") == "fallback"
    ]
    legacy_policy_rows = [
        {
            "card_id": str(row.get("card_id") or ""),
            "surface": str(row.get("surface") or ""),
            "intent": str(row.get("intent") or ""),
        }
        for row in rows
        if str(row.get("surface") or "") in {"Presume.json", "Concede.json"}
    ]

    attention: list[dict[str, Any]] = []
    if fallback_rows:
        attention.append(
            {
                "check": "surface_intent_fallback_visible",
                "count": len(fallback_rows),
            }
        )
    if legacy_policy_rows:
        attention.append(
            {
                "check": "surface_intent_legacy_policy_surface_visible",
                "count": len(legacy_policy_rows),
            }
        )

    return {
        "authority": "diagnostic_only",
        "apply_blocking": False,
        "runtime_write_performed": False,
        "present": True,
        "status": "clean" if not attention else "attention",
        "surface_count": _int_value(surface_intent.get("surface_count")),
        "row_count": len(rows),
        "required_surfaces": _string_list(surface_intent.get("required_surfaces")),
        "optional_surfaces": _string_list(surface_intent.get("optional_surfaces")),
        "rich_optional_runtime_surfaces": _string_list(
            surface_intent.get("rich_optional_runtime_surfaces")
        ),
        "fallback_intent_rows": fallback_rows,
        "legacy_policy_surface_rows": legacy_policy_rows,
        "attention": attention,
        "first_attention": attention[0]["check"] if attention else None,
    }
```

- [ ] **Step 4: Run the clean-path test to verify it passes**

Run:

```powershell
pytest tests/test_config_quality_contract.py::test_config_quality_report_is_clean_for_source_backed_runtime_lean_package -q
```

Expected: PASS.

- [ ] **Step 5: Write the attention-path failing test**

In `tests/test_config_quality_contract.py`, add this test after `test_config_quality_summarizes_semantic_taxonomy_reasons()`:

```python
def test_config_quality_surfaces_surface_intent_attention_without_new_problem(
    tmp_path: Path,
):
    package = minimal_clean_package(tmp_path)
    write_json(
        package / "reports" / "surface_intent.json",
        {
            "rows": [
                {
                    "rule_id": "fallback_card_behavior",
                    "card_id": "GENERIC_001",
                    "surface": "GENERIC_001.json",
                    "surface_family": "CARDID.json",
                    "intent": "aggressive_card_behavior",
                    "intent_source": "fallback",
                    "source_claim_ids": [],
                },
                {
                    "rule_id": "legacy_presume",
                    "card_id": None,
                    "surface": "Presume.json",
                    "intent": "legacy_policy_surface",
                    "source_claim_ids": [],
                },
            ],
            "required_surfaces": [
                "GlobalValues.json",
                "Mulligan.json",
                "GENERIC_001.json",
            ],
            "optional_surfaces": ["Presume.json"],
            "minimum_required_runtime_surfaces": [
                "GlobalValues.json",
                "Mulligan.json",
            ],
            "rich_optional_runtime_surfaces": ["GENERIC_001.json"],
            "surface_count": 4,
        },
    )

    report = build_config_quality_report(package)

    surface_intent = report["checks"]["surface_intent_projection"]
    assert surface_intent["authority"] == "diagnostic_only"
    assert surface_intent["apply_blocking"] is False
    assert surface_intent["runtime_write_performed"] is False
    assert surface_intent["status"] == "attention"
    assert surface_intent["first_attention"] == "surface_intent_fallback_visible"
    assert surface_intent["fallback_intent_rows"] == [
        {
            "card_id": "GENERIC_001",
            "surface": "GENERIC_001.json",
            "intent": "aggressive_card_behavior",
        }
    ]
    assert surface_intent["legacy_policy_surface_rows"] == [
        {
            "card_id": "",
            "surface": "Presume.json",
            "intent": "legacy_policy_surface",
        }
    ]
    assert report["apply_blocking"] is False
    assert not any(
        problem["check"].startswith("surface_intent_")
        for problem in report["problems"]
    )
```

- [ ] **Step 6: Run the attention-path test to verify it passes**

Run:

```powershell
pytest tests/test_config_quality_contract.py::test_config_quality_surfaces_surface_intent_attention_without_new_problem -q
```

Expected: PASS.

- [ ] **Step 7: Commit Task 1**

Run:

```powershell
git add src/hsconfig/config_quality_contract.py tests/test_config_quality_contract.py
git commit -m "feat: project surface intent into config quality"
```

Expected: commit succeeds.

---

### Task 2: Carry Projection Through Configure Summaries

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\commands\configure.py`
- Test: `C:\Users\darbo\Documents\HSConfig\tests\test_config_quality_contract.py`
- Test: `C:\Users\darbo\Documents\HSConfig\tests\test_configure_handoff_contract.py`

**Interfaces:**
- Consumes: `config_quality_summary["surface_intent_status"]`, `surface_intent_present`, `surface_intent_surface_count`, `surface_intent_fallback_intent_rows`, `surface_intent_legacy_policy_surface_rows`, `surface_intent_first_attention`.
- Produces: the same fields in `config_proof_summary`.
- Produces: the same fields in `handoff_contract`.

- [ ] **Step 1: Write failing compact-summary assertions**

In `tests/test_config_quality_contract.py`, in `test_config_quality_surfaces_surface_intent_attention_without_new_problem()`, append:

```python
    compact = _compact_config_quality_summary(report)
    assert compact["surface_intent_status"] == "attention"
    assert compact["surface_intent_present"] is True
    assert compact["surface_intent_surface_count"] == 4
    assert compact["surface_intent_fallback_intent_rows"] == 1
    assert compact["surface_intent_legacy_policy_surface_rows"] == ["Presume.json"]
    assert compact["surface_intent_first_attention"] == "surface_intent_fallback_visible"
```

- [ ] **Step 2: Run compact-summary test to verify it fails**

Run:

```powershell
pytest tests/test_config_quality_contract.py::test_config_quality_surfaces_surface_intent_attention_without_new_problem -q
```

Expected: FAIL with `KeyError: 'surface_intent_status'`.

- [ ] **Step 3: Implement compact-summary projection**

In `src/hsconfig/commands/configure.py`, inside `_compact_config_quality_summary()` after the `config_intent` block, add:

```python
        surface_intent = checks.get("surface_intent_projection")
        if isinstance(surface_intent, Mapping):
            summary["surface_intent_status"] = str(
                surface_intent.get("status") or ""
            )
            summary["surface_intent_present"] = bool(
                surface_intent.get("present", False)
            )
            summary["surface_intent_surface_count"] = int(
                surface_intent.get("surface_count") or 0
            )
            summary["surface_intent_fallback_intent_rows"] = len(
                [
                    item
                    for item in surface_intent.get("fallback_intent_rows", [])
                    if isinstance(item, Mapping)
                ]
            )
            summary["surface_intent_legacy_policy_surface_rows"] = [
                str(item.get("surface"))
                for item in surface_intent.get("legacy_policy_surface_rows", [])
                if isinstance(item, Mapping) and str(item.get("surface") or "")
            ]
            first_attention = surface_intent.get("first_attention")
            if first_attention is not None:
                summary["surface_intent_first_attention"] = str(first_attention)
```

- [ ] **Step 4: Run compact-summary test to verify it passes**

Run:

```powershell
pytest tests/test_config_quality_contract.py::test_config_quality_surfaces_surface_intent_attention_without_new_problem -q
```

Expected: PASS.

- [ ] **Step 5: Write failing handoff-contract assertions**

In `tests/test_configure_handoff_contract.py`, update `config_proof_summary` in `test_handoff_contract_reports_clean_single_authority_package()` with:

```python
            "surface_intent_status": "clean",
            "surface_intent_present": True,
            "surface_intent_surface_count": 3,
            "surface_intent_fallback_intent_rows": 0,
            "surface_intent_legacy_policy_surface_rows": [],
            "surface_intent_first_attention": None,
```

Add the same expected fields to the expected returned contract:

```python
        "surface_intent_status": "clean",
        "surface_intent_present": True,
        "surface_intent_surface_count": 3,
        "surface_intent_fallback_intent_rows": 0,
        "surface_intent_legacy_policy_surface_rows": [],
        "surface_intent_first_attention": None,
```

In `test_handoff_contract_surfaces_attention_without_blocking_apply()`, add these fields to `config_proof_summary`:

```python
            "surface_intent_status": "attention",
            "surface_intent_present": True,
            "surface_intent_surface_count": 4,
            "surface_intent_fallback_intent_rows": 1,
            "surface_intent_legacy_policy_surface_rows": ["Presume.json"],
            "surface_intent_first_attention": "surface_intent_fallback_visible",
```

Append these assertions to the test:

```python
    assert contract["surface_intent_status"] == "attention"
    assert contract["surface_intent_present"] is True
    assert contract["surface_intent_surface_count"] == 4
    assert contract["surface_intent_fallback_intent_rows"] == 1
    assert contract["surface_intent_legacy_policy_surface_rows"] == ["Presume.json"]
    assert contract["surface_intent_first_attention"] == "surface_intent_fallback_visible"
```

- [ ] **Step 6: Run handoff tests to verify they fail**

Run:

```powershell
pytest tests/test_configure_handoff_contract.py -q
```

Expected: FAIL because returned handoff contracts do not include `surface_intent_*` fields.

- [ ] **Step 7: Implement proof and handoff projection**

In `src/hsconfig/commands/configure.py`, add these keys to the returned dict in `_build_config_proof_summary()` after `semantic_intent_status`:

```python
        "surface_intent_status": str(
            config_quality_summary.get("surface_intent_status", "")
        ),
        "surface_intent_present": bool(
            config_quality_summary.get("surface_intent_present", False)
        ),
        "surface_intent_surface_count": int(
            config_quality_summary.get("surface_intent_surface_count") or 0
        ),
        "surface_intent_fallback_intent_rows": int(
            config_quality_summary.get("surface_intent_fallback_intent_rows") or 0
        ),
        "surface_intent_legacy_policy_surface_rows": [
            str(surface)
            for surface in config_quality_summary.get(
                "surface_intent_legacy_policy_surface_rows", []
            )
            if str(surface)
        ],
        "surface_intent_first_attention": (
            str(config_quality_summary.get("surface_intent_first_attention"))
            if config_quality_summary.get("surface_intent_first_attention") is not None
            else None
        ),
```

In `_build_handoff_contract()`, add these keys after `semantic_intent_status`:

```python
        "surface_intent_status": str(
            config_proof_summary.get("surface_intent_status") or ""
        ),
        "surface_intent_present": bool(
            config_proof_summary.get("surface_intent_present", False)
        ),
        "surface_intent_surface_count": int(
            config_proof_summary.get("surface_intent_surface_count") or 0
        ),
        "surface_intent_fallback_intent_rows": int(
            config_proof_summary.get("surface_intent_fallback_intent_rows") or 0
        ),
        "surface_intent_legacy_policy_surface_rows": [
            str(surface)
            for surface in config_proof_summary.get(
                "surface_intent_legacy_policy_surface_rows", []
            )
            if str(surface)
        ],
        "surface_intent_first_attention": (
            str(config_proof_summary.get("surface_intent_first_attention"))
            if config_proof_summary.get("surface_intent_first_attention") is not None
            else None
        ),
```

- [ ] **Step 8: Run Task 2 tests**

Run:

```powershell
pytest tests/test_config_quality_contract.py::test_config_quality_surfaces_surface_intent_attention_without_new_problem tests/test_configure_handoff_contract.py -q
```

Expected: PASS.

- [ ] **Step 9: Commit Task 2**

Run:

```powershell
git add src/hsconfig/commands/configure.py tests/test_config_quality_contract.py tests/test_configure_handoff_contract.py
git commit -m "feat: expose surface intent in configure summaries"
```

Expected: commit succeeds.

---

### Task 3: Guard Against Second-Gate Drift And Verify

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_no_second_gate_contract.py`
- Verify: repository test and contract commands.

**Interfaces:**
- Consumes: literal string `surface_intent_projection`.
- Produces: regression coverage that the new projection remains outside apply/runtime-write code paths.

- [ ] **Step 1: Write the no-second-gate test**

In `tests/test_no_second_gate_contract.py`, add:

```python
def test_surface_intent_projection_is_summary_only_not_apply_gate_input():
    guarded_paths = [
        "src/hsconfig/apply_gate.py",
        "src/hsconfig/runtime_apply.py",
        "src/hsconfig/commands/apply.py",
        "src/hsconfig/operator_summary.py",
    ]

    for relative_path in guarded_paths:
        assert "surface_intent_projection" not in _read(relative_path), relative_path
```

- [ ] **Step 2: Run no-second-gate test**

Run:

```powershell
pytest tests/test_no_second_gate_contract.py -q
```

Expected: PASS.

- [ ] **Step 3: Run focused regression tests**

Run:

```powershell
pytest tests/test_surface_intent.py tests/test_config_quality_contract.py tests/test_configure_handoff_contract.py tests/test_no_second_gate_contract.py -q
```

Expected: PASS.

- [ ] **Step 4: Run contract preflight**

Run:

```powershell
python -m hsconfig.cli contract-preflight --repo-root . --json
```

Expected:

```text
"status": "PASS"
"dirty": false
"repo_current": true
"installed_skill_sync_current": true
"no_default_only_visible": true
"source_status_apply_blocking": false
```

The command may print these fields inside JSON. Treat the run as failed if `status` is not `PASS`.

- [ ] **Step 5: Run currentness check**

Run:

```powershell
python scripts/check_hsconfig_currentness.py --cwd . --json
```

Expected:

```text
"dirty": false
"clean_for_runtime_work": true
"behind_origin_main": 0
```

- [ ] **Step 6: Commit Task 3**

Run:

```powershell
git add tests/test_no_second_gate_contract.py
git commit -m "test: keep surface intent diagnostic only"
```

Expected: commit succeeds.

- [ ] **Step 7: Final cleanliness check**

Run:

```powershell
git status --short --branch
```

Expected: branch line only, no modified or untracked files.

---

## Self-Review Checklist

- Spec coverage: The plan implements only the recommended tiny projection; it does not add gameplay, log parsing, HSTuner, runtime writes, or a new apply authority.
- Placeholder scan: The plan contains no deferred implementation markers; every code-changing step has concrete snippets and exact tests.
- Type consistency: The new public internal check name is consistently `surface_intent_projection`, and summary fields consistently use the `surface_intent_*` prefix.
- Risk boundary: Missing `surface_intent.json` returns `status="missing"` inside the diagnostic check but does not add a config-quality problem or block apply.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-24-hsconfig-surface-intent-summary-projection.md`. Two execution options:

1. **Subagent-Driven (recommended)** - dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** - execute tasks in this session using executing-plans, batch execution with checkpoints.

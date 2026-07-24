# HSConfig Package Surface Intent Preflight Receipt Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a read-only `surface_intent` receipt to package-mode `contract-preflight` so generated packages expose the same compact surface-intent proof already shown by `configure`, without creating a new gate.

**Architecture:** Reuse the existing `config_quality_contract.build_config_quality_report()` package checks. `contract_preflight.build_package_contract_preflight()` will project `checks.surface_intent_projection` into compact package-contract fields, while leaving `operator_summary.json` as the only normal apply authority.

**Tech Stack:** Python 3, pytest, existing HSConfig CLI and JSON package reports.

## Global Constraints

- HSConfig is pre-run only; do not add replay, winrate, runtime-log, or HSTuner tuning logic.
- `reports/operator_summary.json` remains the only normal apply authority.
- `SOURCE_BACKED_STRONG` remains an evidence-quality label, not a generation or apply gate.
- `source_status_apply_blocking` must remain `false` for source-quality and package-preflight diagnostics.
- The new receipt is diagnostic-only: `authority="diagnostic_only"`, `apply_blocking=false`, `runtime_write_performed=false`.
- Do not add new Runtime surfaces, card sequencing logic, gameplay heuristics, or special handling for individual cards.
- Do not make missing or attention-level `surface_intent` block `package_contract_current`.
- Keep the worktree clean before and after implementation; no backups, generated logs, or temporary package artifacts remain.

---

## File Structure

- Modify: `src/hsconfig/contract_preflight.py`
  - Owns the package-mode preflight dataclass and payload construction.
  - Add compact `surface_intent_*` fields sourced from `config_quality_contract`.

- Modify: `src/hsconfig/commands/contract_preflight.py`
  - Owns CLI fallback payload when package preflight raises.
  - Keep fallback schema aligned with `PackageContractPreflight`.

- Modify: `tests/test_contract_preflight.py`
  - Owns package-mode preflight contract tests and CLI fallback schema tests.
  - Extend the existing package helper with `reports/surface_intent.json`.

- Modify: `tests/test_no_second_gate_contract.py`
  - Owns sentinel tests proving diagnostic summaries do not feed apply/runtime-write paths.
  - Add package-preflight-specific allowance while still forbidding apply authority consumption.

- Modify: `docs/operator/README.md`
  - Add one operator-facing sentence that package preflight now mirrors surface-intent diagnostics.

---

### Task 1: Add Failing Package-Preflight Surface-Intent Tests

**Files:**
- Modify: `tests/test_contract_preflight.py`

**Interfaces:**
- Consumes: `build_contract_preflight(repo_root, git, skill_install_root, package) -> dict`
- Consumes: `build_package_contract_preflight(package) -> dict`
- Produces: Expected package-contract keys:
  - `surface_intent_status: str`
  - `surface_intent_present: bool`
  - `surface_intent_surface_count: int`
  - `surface_intent_fallback_intent_rows: int`
  - `surface_intent_legacy_policy_surface_rows: list[str]`
  - `surface_intent_first_attention: str | None`

- [ ] **Step 1: Write the failing clean-package receipt test**

In `tests/test_contract_preflight.py`, update `_contract_preflight_clean_package()` after the `source_to_runtime_explainability.json` write and before runtime files are written:

```python
    _write_json(
        reports / "surface_intent.json",
        {
            "authority": "diagnostic_only",
            "apply_blocking": False,
            "runtime_write_performed": False,
            "surface_count": 3,
            "required_surfaces": ["GlobalValues.json", "Mulligan.json"],
            "optional_surfaces": ["NX2_019.json"],
            "rich_optional_runtime_surfaces": ["NX2_019.json"],
            "rows": [
                {
                    "card_id": "GlobalValues",
                    "surface": "GlobalValues.json",
                    "intent": "global_values",
                    "intent_source": "contract",
                },
                {
                    "card_id": "Mulligan",
                    "surface": "Mulligan.json",
                    "intent": "mulligan_policy",
                    "intent_source": "contract",
                },
                {
                    "card_id": "NX2_019",
                    "surface": "NX2_019.json",
                    "intent": "cardid_behavior",
                    "intent_source": "contract",
                },
            ],
        },
    )
```

Then extend `test_contract_preflight_package_mode_aggregates_runtime_and_quality()` after the existing `config_intent_self_audit_status` assertion:

```python
    assert contract["surface_intent_status"] == "clean"
    assert contract["surface_intent_present"] is True
    assert contract["surface_intent_surface_count"] == 3
    assert contract["surface_intent_fallback_intent_rows"] == 0
    assert contract["surface_intent_legacy_policy_surface_rows"] == []
    assert contract["surface_intent_first_attention"] is None
```

- [ ] **Step 2: Write the missing-surface-intent non-gate test**

Add this test near `test_contract_preflight_package_mode_aggregates_runtime_and_quality()`:

```python
def test_contract_preflight_package_mode_surfaces_missing_surface_intent_without_gate(
    tmp_path: Path,
) -> None:
    package = _contract_preflight_clean_package(tmp_path)
    (package / "reports" / "surface_intent.json").unlink()

    payload = build_contract_preflight(
        Path("."),
        git=_clean_git(),
        skill_install_root=_synced_install_root(tmp_path),
        package=package,
    )

    assert payload["status"] == "PASS"
    assert payload["checks"]["package_contract_current"] is True
    contract = payload["package_contract"]
    assert contract["package_contract_current"] is True
    assert contract["surface_intent_status"] == "missing"
    assert contract["surface_intent_present"] is False
    assert contract["surface_intent_surface_count"] == 0
    assert contract["surface_intent_fallback_intent_rows"] == 0
    assert contract["surface_intent_legacy_policy_surface_rows"] == []
    assert contract["surface_intent_first_attention"] is None
    assert all("surface_intent" not in failure for failure in contract["failures"])
```

- [ ] **Step 3: Extend CLI fallback schema test**

In `test_contract_preflight_cli_package_fallback_preserves_package_contract_schema()`, after `payload["source_status_apply_blocking"] is False`, add:

```python
    fallback_contract = payload["package_contract"]
    assert set(fallback_contract) == schema_keys
    assert fallback_contract["surface_intent_status"] == "attention"
    assert fallback_contract["surface_intent_present"] is False
    assert fallback_contract["surface_intent_surface_count"] == 0
    assert fallback_contract["surface_intent_fallback_intent_rows"] == 0
    assert fallback_contract["surface_intent_legacy_policy_surface_rows"] == []
    assert fallback_contract["surface_intent_first_attention"] == (
        "contract_preflight_exception"
    )
```

- [ ] **Step 4: Run tests and verify failure**

Run:

```powershell
python -m pytest tests/test_contract_preflight.py::test_contract_preflight_package_mode_aggregates_runtime_and_quality tests/test_contract_preflight.py::test_contract_preflight_package_mode_surfaces_missing_surface_intent_without_gate tests/test_contract_preflight.py::test_contract_preflight_cli_package_fallback_preserves_package_contract_schema -q
```

Expected before implementation: FAIL with missing `surface_intent_*` keys in `package_contract`.

- [ ] **Step 5: Commit only after Task 2 passes**

Do not commit after the failing tests. These tests are completed by Task 2.

---

### Task 2: Implement Compact Surface-Intent Receipt in Package Preflight

**Files:**
- Modify: `src/hsconfig/contract_preflight.py`
- Modify: `src/hsconfig/commands/contract_preflight.py`
- Test: `tests/test_contract_preflight.py`

**Interfaces:**
- Consumes: `quality_checks["surface_intent_projection"]` from `build_config_quality_report(package)`.
- Produces: package-contract fields listed in Task 1.

- [ ] **Step 1: Extend `PackageContractPreflight`**

In `src/hsconfig/contract_preflight.py`, add these fields after `config_intent_first_attention`:

```python
    surface_intent_status: str
    surface_intent_present: bool
    surface_intent_surface_count: int
    surface_intent_fallback_intent_rows: int
    surface_intent_legacy_policy_surface_rows: list[str]
    surface_intent_first_attention: str | None
```

- [ ] **Step 2: Add a compact projection helper**

In `src/hsconfig/contract_preflight.py`, add this helper near `_first_problem()` or near other package-contract helpers:

```python
def _surface_intent_contract_receipt(
    surface_intent: Mapping[str, Any],
) -> dict[str, Any]:
    fallback_rows = [
        row
        for row in surface_intent.get("fallback_intent_rows", [])
        if isinstance(row, Mapping)
    ]
    legacy_policy_rows = [
        row
        for row in surface_intent.get("legacy_policy_surface_rows", [])
        if isinstance(row, Mapping)
    ]
    first_attention_value = surface_intent.get("first_attention")
    return {
        "surface_intent_status": str(surface_intent.get("status") or "missing"),
        "surface_intent_present": bool(surface_intent.get("present", False)),
        "surface_intent_surface_count": _int_value(
            surface_intent.get("surface_count", 0)
        ),
        "surface_intent_fallback_intent_rows": len(fallback_rows),
        "surface_intent_legacy_policy_surface_rows": [
            str(row.get("surface"))
            for row in legacy_policy_rows
            if str(row.get("surface") or "")
        ],
        "surface_intent_first_attention": (
            str(first_attention_value) if first_attention_value else None
        ),
    }
```

- [ ] **Step 3: Populate defaults for missing package branch**

In the `not package_path.is_dir()` branch inside `build_package_contract_preflight()`, add these constructor arguments:

```python
                surface_intent_status="missing",
                surface_intent_present=False,
                surface_intent_surface_count=0,
                surface_intent_fallback_intent_rows=0,
                surface_intent_legacy_policy_surface_rows=[],
                surface_intent_first_attention="package_missing",
```

- [ ] **Step 4: Populate fields from `config_quality_contract` in package branch**

After the existing line:

```python
    config_intent = _as_mapping(quality_checks.get("config_intent_self_audit"))
```

add:

```python
    surface_intent_receipt = _surface_intent_contract_receipt(
        _as_mapping(quality_checks.get("surface_intent_projection"))
    )
```

Then add the following constructor arguments after `config_intent_first_attention=config_intent_first_attention,`:

```python
            surface_intent_status=surface_intent_receipt["surface_intent_status"],
            surface_intent_present=surface_intent_receipt["surface_intent_present"],
            surface_intent_surface_count=surface_intent_receipt[
                "surface_intent_surface_count"
            ],
            surface_intent_fallback_intent_rows=surface_intent_receipt[
                "surface_intent_fallback_intent_rows"
            ],
            surface_intent_legacy_policy_surface_rows=surface_intent_receipt[
                "surface_intent_legacy_policy_surface_rows"
            ],
            surface_intent_first_attention=surface_intent_receipt[
                "surface_intent_first_attention"
            ],
```

Do not add `surface_intent_*` to `failures`.

- [ ] **Step 5: Align CLI fallback schema**

In `src/hsconfig/commands/contract_preflight.py`, inside the fallback `payload["package_contract"]` dictionary, add these keys after `config_intent_first_attention`:

```python
                "surface_intent_status": "attention",
                "surface_intent_present": False,
                "surface_intent_surface_count": 0,
                "surface_intent_fallback_intent_rows": 0,
                "surface_intent_legacy_policy_surface_rows": [],
                "surface_intent_first_attention": "contract_preflight_exception",
```

- [ ] **Step 6: Run focused package preflight tests**

Run:

```powershell
python -m pytest tests/test_contract_preflight.py::test_contract_preflight_package_mode_aggregates_runtime_and_quality tests/test_contract_preflight.py::test_contract_preflight_package_mode_surfaces_missing_surface_intent_without_gate tests/test_contract_preflight.py::test_contract_preflight_cli_package_fallback_preserves_package_contract_schema -q
```

Expected: PASS.

- [ ] **Step 7: Run broader contract-preflight tests**

Run:

```powershell
python -m pytest tests/test_contract_preflight.py tests/test_config_quality_contract.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit Task 1 and Task 2 together**

Run:

```powershell
git add src/hsconfig/contract_preflight.py src/hsconfig/commands/contract_preflight.py tests/test_contract_preflight.py
git commit -m "feat: expose package surface intent receipt"
```

---

### Task 3: Guard Diagnostic-Only Boundary and Document Operator Surface

**Files:**
- Modify: `tests/test_no_second_gate_contract.py`
- Modify: `docs/operator/README.md`
- Test: `tests/test_no_second_gate_contract.py`

**Interfaces:**
- Consumes: package receipt fields from Task 2.
- Produces: documented and tested guarantee that surface-intent package preflight does not affect apply/runtime-write paths.

- [ ] **Step 1: Extend no-second-gate sentinel**

In `tests/test_no_second_gate_contract.py`, replace `test_surface_intent_projection_is_summary_only_not_apply_gate_input()` with:

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
        assert "surface_intent_status" not in _read(relative_path), relative_path
        assert "surface_intent_present" not in _read(relative_path), relative_path
```

Add this new test below it:

```python
def test_contract_preflight_may_surface_intent_but_not_apply_authority():
    preflight = _read("src/hsconfig/contract_preflight.py")

    assert "surface_intent_status" in preflight
    assert "surface_intent_present" in preflight
    assert "surface_intent" not in _read("src/hsconfig/apply_gate.py")
    assert "surface_intent" not in _read("src/hsconfig/runtime_apply.py")
```

- [ ] **Step 2: Run sentinel test and verify failure or pass**

Run:

```powershell
python -m pytest tests/test_no_second_gate_contract.py -q
```

Expected after Task 2: PASS. If it fails, the failure must be a true boundary issue; remove any accidental apply/runtime consumption rather than weakening the sentinel.

- [ ] **Step 3: Add a short operator documentation line**

In `docs/operator/README.md`, find the package-mode `contract-preflight` description. Add this sentence to the same paragraph:

```markdown
Package mode also mirrors the generated `surface_intent` receipt as diagnostic-only fields, so operators can see required/rich/legacy surface intent without changing apply authority.
```

Do not claim gameplay improvement, log analysis, or `SOURCE_BACKED_STRONG` blocking.

- [ ] **Step 4: Run docs/sentinel focused verification**

Run:

```powershell
python -m pytest tests/test_no_second_gate_contract.py tests/test_contract_preflight.py::test_contract_preflight_package_mode_aggregates_runtime_and_quality -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 3**

Run:

```powershell
git add tests/test_no_second_gate_contract.py docs/operator/README.md
git commit -m "docs: document package surface intent diagnostics"
```

---

### Task 4: Final Verification and Clean-Current Proof

**Files:**
- No code changes.
- Verify complete repository state.

**Interfaces:**
- Consumes: all changes from Tasks 1-3.
- Produces: evidence that package preflight remains read-only, tests pass, repo is current, and worktree is clean.

- [ ] **Step 1: Run focused test suite**

Run:

```powershell
python -m pytest tests/test_contract_preflight.py tests/test_config_quality_contract.py tests/test_no_second_gate_contract.py -q
```

Expected: PASS.

- [ ] **Step 2: Run full test suite**

Run:

```powershell
python -m pytest -q
```

Expected: PASS with the existing skip count accepted.

- [ ] **Step 3: Run repository currentness check**

Run:

```powershell
git fetch --all --prune --tags
python scripts/check_hsconfig_currentness.py --cwd . --json
```

Expected JSON fields:

```json
{
  "dirty": false,
  "clean_for_runtime_work": true,
  "behind_origin_main": 0
}
```

`ahead_origin_main` may be greater than `0` on a feature branch.

- [ ] **Step 4: Run contract preflight**

Run:

```powershell
python -m hsconfig.cli contract-preflight --json
```

Expected: JSON `status` is `PASS` or only existing non-runtime informational attention remains. `source_status_apply_blocking` must be `false`.

- [ ] **Step 5: Inspect diff**

Run:

```powershell
git diff --stat HEAD~2..HEAD
git diff HEAD~2..HEAD -- src/hsconfig/contract_preflight.py src/hsconfig/commands/contract_preflight.py tests/test_contract_preflight.py tests/test_no_second_gate_contract.py docs/operator/README.md
```

Expected:
- Only package-preflight receipt, tests, and operator docs changed.
- No apply gate, runtime apply, card sequencing, HSTuner, or log-analysis behavior changed.

- [ ] **Step 6: Push branch**

Run:

```powershell
git push
```

Expected: push succeeds to the branch upstream.

- [ ] **Step 7: Confirm final worktree**

Run:

```powershell
git status --short --branch
python scripts/check_hsconfig_currentness.py --cwd . --json
```

Expected:
- `git status --short --branch` shows no modified or untracked files.
- Currentness JSON shows `dirty=false`, `clean_for_runtime_work=true`, `behind_origin_main=0`.

---

## Self-Review

**Spec coverage:** This plan adds exactly one narrow read-only diagnostic surface to package preflight. It does not inspect logs, tune gameplay, add HSTuner, or create a new apply gate.

**Placeholder scan:** No unresolved placeholder text, broad unspecified steps, or vague test instructions remain. Each task has concrete files, test snippets, implementation snippets, and commands.

**Type consistency:** Field names are consistent across tests, dataclass, fallback payload, and docs:
- `surface_intent_status`
- `surface_intent_present`
- `surface_intent_surface_count`
- `surface_intent_fallback_intent_rows`
- `surface_intent_legacy_policy_surface_rows`
- `surface_intent_first_attention`

**Boundary check:** The only production consumer is package-mode `contract_preflight`. Apply gate, runtime apply, apply command, and operator summary remain free of new `surface_intent_*` apply-authority inputs.

# HSConfig Subtractive Contract Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make HSConfig slimmer and harder to drift by reducing legacy runtime surface plumbing, making `reports/operator_summary.json` the only executable apply authority, and classifying every emitted artifact.

**Architecture:** Keep the existing source-contract spine. Do not add a new orchestration layer. Tighten the current path: source claims remain diagnostic unless lowered by an approved runtime builder, normal VisionAI output stays limited to `GlobalValues.json`, `Mulligan.json`, per-card `<CARDID>.json`, and exact `Combo.json`, and runtime apply continues to read only `reports/operator_summary.json`.

**Tech Stack:** Python 3, pytest, local `hsconfig` package, HearthRanger VisionAI JSON package format.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig`.
- Do not commit raw HearthRanger logs, HDT replays, HSReplay files, Power.log, runtime evidence, or private runtime outputs.
- Preserve the no-block-any-deck contract: thin source evidence, static-only mechanics, unsupported mechanic richness, and guide gaps must not block a load-safe package.
- Runtime writes remain allowed only through guarded `hsconfig apply` / `hsconfig configure --apply`.
- `reports/operator_summary.json` remains the only normal runtime-write/apply authority.
- Diagnostic reports must never grant apply permission.
- Effect semantics are not opening-hand mulligan keeps. Start-of-game, deckbuilding, and hero-power-transform behavior such as Darkbishop Benedictus -> Mind Spike must be preserved without placing the enabler card in `Mulligan.json` unless a source explicitly claims opening-hand mulligan intent.
- Normal HSConfig output must not emit `Presume.json` or `Concede.json`.
- Keep compatibility readable but not active in the normal operator path.
- Do not add new third-party dependencies.

---

## File Structure

Modify:

- `src/hsconfig/surface_intent.py`  
  Remove normal routing from `legacy_policy_surfaces_enabled`; preserve normal surfaces and Combo only.

- `src/hsconfig/apply_gate.py`  
  Keep `allow_source_informed` as a backward-compatible no-op parameter or remove internal branching if no caller needs it; ensure the gate result depends only on package files and `reports/operator_summary.json`.

- `src/hsconfig/runtime_apply.py`  
  Stop threading `allow_source_informed` into real apply decisions beyond compatibility signatures.

- `src/hsconfig/commands/apply.py`  
  Keep CLI compatibility if existing users pass `--allow-source-informed`, but mark it legacy/no-op and do not create a second apply path.

- `src/hsconfig/report_ownership.py`  
  Upgrade from a report-only list to the canonical ownership registry for operator reports.

- `src/hsconfig/operator_summary.py`  
  Include the ownership data and any new output manifest reference without adding another apply gate.

- `src/hsconfig/package_builder.py`  
  Build `operator_summary` exactly once in the package flow.

- `src/hsconfig/contract_spine_sentinel.py`  
  Add drift checks for legacy surface routing, unclassified emitted reports, and active apply diagnostic consumers.

- `docs/operator/README.md`  
  Shorten/align the normal operator statement around single apply authority and legacy/no-op flags.

- `docs/operator/guide-research-policy.md`  
  Align source-contract wording with the no-second-gate policy.

- `.agents/skills/hsconfig/SKILL.md`  
  Keep the runtime path concise and operator-facing.

Create:

- `src/hsconfig/output_ownership_manifest.py`  
  Build a machine-readable artifact ownership manifest for emitted runtime files and reports.

- `tests/test_subtractive_contract_polish.py`  
  High-signal tests for legacy-surface quarantine, no-op source-informed compatibility, full output ownership, single-pass summary, and sentinel drift detection.

Optional if test readability requires it:

- `tests/helpers/package_factory.py`  
  Only create if the new tests repeat more than two package fixtures. Reuse existing helpers first.

---

### Task 1: Freeze Legacy Surface Quarantine With Failing Tests

**Files:**
- Create: `tests/test_subtractive_contract_polish.py`
- Modify: none in this task
- Test: `tests/test_subtractive_contract_polish.py`

**Interfaces:**
- Consumes: `hsconfig.surface_intent.build_surface_intent(contract: dict[str, Any]) -> dict[str, Any]`
- Produces: Failing tests that define the new normal-path boundary for `Presume.json` and `Concede.json`.

- [ ] **Step 1: Add failing tests for legacy surface quarantine**

Add this file:

```python
from __future__ import annotations

from hsconfig.surface_intent import build_surface_intent


LEGACY_SURFACES = {"Presume.json", "Concede.json"}


def test_surface_intent_ignores_legacy_policy_surfaces_in_normal_path():
    contract = {
        "cards": {},
        "mulligan_anchors": [],
        "combos": [],
        "legacy_policy_surfaces_enabled": True,
        "policies": {
            "presume": [{"source_claim_ids": ["claim-presume"]}],
            "concede": [{"source_claim_ids": ["claim-concede"]}],
        },
    }

    intent = build_surface_intent(contract)

    assert set(intent["optional_surfaces"]).isdisjoint(LEGACY_SURFACES)
    assert all(row["surface"] not in LEGACY_SURFACES for row in intent["rows"])
    assert set(intent["required_surfaces"]) == {"GlobalValues.json", "Mulligan.json"}
```

- [ ] **Step 2: Run the targeted test and verify it fails**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_subtractive_contract_polish.py::test_surface_intent_ignores_legacy_policy_surfaces_in_normal_path -q
```

Expected: FAIL because `build_surface_intent()` currently routes `Presume.json` and `Concede.json` when `legacy_policy_surfaces_enabled` is true.

- [ ] **Step 3: Commit the failing test**

```powershell
git add tests/test_subtractive_contract_polish.py
git commit -m "test: freeze legacy surface quarantine"
```

---

### Task 2: Remove Normal Routing For Legacy Policy Surfaces

**Files:**
- Modify: `src/hsconfig/surface_intent.py`
- Modify: `tests/test_surface_intent.py`
- Test: `tests/test_subtractive_contract_polish.py`, `tests/test_surface_intent.py`

**Interfaces:**
- Consumes: failing test from Task 1.
- Produces: `build_surface_intent()` always excludes `Presume.json` and `Concede.json` from normal output.

- [ ] **Step 1: Remove legacy policy routing from `build_surface_intent()`**

In `src/hsconfig/surface_intent.py`, delete the `policies = ...` block that adds `Presume.json` and `Concede.json`. The end of the function should keep only required surfaces and optional `Combo.json`:

```python
    if contract.get("combos"):
        optional_surfaces.add("Combo.json")
        rows.append(
            {
                "rule_id": "combo_sequences",
                "card_id": None,
                "surface": "Combo.json",
                "intent": "same_turn_combo_sequences",
                "source_claim_ids": _combo_claim_ids(contract),
            }
        )

    return {
        "rows": rows,
        "required_surfaces": sorted(required_surfaces),
        "optional_surfaces": sorted(optional_surfaces),
        "surface_count": len(required_surfaces) + len(optional_surfaces),
    }
```

Keep `_policy_claim_ids()` only if another active module imports it. If no active import remains, remove it from this file.

- [ ] **Step 2: Update the legacy surface intent test**

In `tests/test_surface_intent.py`, update the test that currently expects legacy surfaces when `legacy_policy_surfaces_enabled` is true. Replace its assertions with:

```python
    assert (None, "Presume.json") not in surfaces
    assert (None, "Concede.json") not in surfaces
    assert "Presume.json" not in intent["optional_surfaces"]
    assert "Concede.json" not in intent["optional_surfaces"]
```

Rename the test to:

```python
def test_surface_intent_does_not_route_legacy_policy_surfaces_even_when_flagged():
```

- [ ] **Step 3: Run focused tests**

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_subtractive_contract_polish.py::test_surface_intent_ignores_legacy_policy_surfaces_in_normal_path tests/test_surface_intent.py -q
```

Expected: PASS.

- [ ] **Step 4: Run no-block representative tests**

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_universal_wild_no_block_matrix.py tests/test_shadowpriest_e2e.py -q
```

Expected: PASS. ShadowPriest still preserves `hero_power_transform` while excluding Darkbishop from opening-hand keeps.

- [ ] **Step 5: Commit**

```powershell
git add src/hsconfig/surface_intent.py tests/test_surface_intent.py tests/test_subtractive_contract_polish.py
git commit -m "fix: quarantine legacy policy surfaces"
```

---

### Task 3: Make Source-Informed Apply Compatibility A No-Op

**Files:**
- Modify: `src/hsconfig/apply_gate.py`
- Modify: `src/hsconfig/runtime_apply.py`
- Modify: `src/hsconfig/commands/apply.py`
- Modify: `tests/test_apply_gate.py`
- Modify: `tests/test_cli_help.py`
- Test: `tests/test_subtractive_contract_polish.py`, `tests/test_apply_gate.py`, `tests/test_runtime_apply.py`, `tests/test_cli_help.py`

**Interfaces:**
- Consumes: `evaluate_apply_gate(package_root, allow_source_informed=False) -> dict[str, Any]`
- Produces: `allow_source_informed` compatibility that cannot change an apply decision.

- [ ] **Step 1: Add no-op parity tests**

Append to `tests/test_subtractive_contract_polish.py`:

```python
from pathlib import Path

from hsconfig.apply_gate import evaluate_apply_gate
from hsconfig.io import write_json


def _write_minimal_package(package: Path, *, technical_status: str = "VALID_PACKAGE") -> None:
    deck_dir = package / "CustomConfig" / "deck"
    reports = package / "reports"
    deck_dir.mkdir(parents=True)
    reports.mkdir(parents=True)
    write_json(deck_dir / "GlobalValues.json", {})
    write_json(deck_dir / "Mulligan.json", {"mulligan": []})
    write_json(reports / "input_manifest.json", {"deck_name": "deck"})
    write_json(
        reports / "operator_summary.json",
        {
            "technical_status": technical_status,
            "semantic_status": "VALID_BUT_NOT_GUIDE_STRONG",
            "next_action": "READY_TO_APPLY_WITH_WARNINGS",
            "apply_policy": "ALLOWED_WITH_WARNINGS",
            "generated_files": [
                "CustomConfig/deck/GlobalValues.json",
                "CustomConfig/deck/Mulligan.json",
            ],
        },
    )


def test_allow_source_informed_does_not_change_apply_gate(tmp_path):
    package = tmp_path / "package"
    _write_minimal_package(package)

    normal = evaluate_apply_gate(package)
    legacy_flag = evaluate_apply_gate(package, allow_source_informed=True)

    assert legacy_flag == normal
    assert normal["status"] == "allowed"
```

- [ ] **Step 2: Run parity test before code changes**

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_subtractive_contract_polish.py::test_allow_source_informed_does_not_change_apply_gate -q
```

Expected: PASS if the parameter is already behaviorally inert. If it fails, continue and make the implementation minimal.

- [ ] **Step 3: Make the parameter explicitly unused**

In `src/hsconfig/apply_gate.py`, keep the public parameter for compatibility but make the intent explicit:

```python
def evaluate_apply_gate(
    package_root: str | Path,
    *,
    allow_source_informed: bool = False,
) -> dict[str, Any]:
    del allow_source_informed  # Backward-compatible no-op; operator_summary is the gate.
    package = Path(package_root)
```

- [ ] **Step 4: Stop forwarding the flag in runtime internals**

In `src/hsconfig/runtime_apply.py`, keep `allow_source_informed` in `apply_package()` and `_resolve_allowed_apply_gate()` signatures for compatibility. Add `del allow_source_informed` at the top of `_resolve_allowed_apply_gate()` and call `evaluate_apply_gate(package)` without the flag:

```python
def _resolve_allowed_apply_gate(
    *,
    package: Path,
    apply_gate: dict[str, Any] | None,
    allow_source_informed: bool,
) -> dict[str, Any]:
    del allow_source_informed  # Legacy CLI compatibility; no second apply path.
    evaluated = evaluate_apply_gate(package)
```

- [ ] **Step 5: Keep CLI wording legacy/no-op**

In `src/hsconfig/commands/apply.py`, leave argument parsing behavior intact if the flag already exists in the CLI registration. In `apply_payload()`, call:

```python
    apply_gate = evaluate_apply_gate(package)
```

and:

```python
    receipt = apply_package(
        package_root=package,
        runtime_root=args.runtime_root,
        fake_receipt=fake_receipt,
        apply_gate=apply_gate,
    )
```

- [ ] **Step 6: Update CLI help tests**

In `tests/test_cli_help.py`, keep the test name `test_apply_help_marks_allow_source_informed_as_legacy_diagnostic_flag` and assert the help text contains all of:

```python
assert "--allow-source-informed" in output
assert "legacy" in output.lower()
assert "no-op" in output.lower()
```

- [ ] **Step 7: Run apply boundary tests**

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_subtractive_contract_polish.py::test_allow_source_informed_does_not_change_apply_gate tests/test_apply_gate.py tests/test_runtime_apply.py tests/test_cli_help.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```powershell
git add src/hsconfig/apply_gate.py src/hsconfig/runtime_apply.py src/hsconfig/commands/apply.py tests/test_subtractive_contract_polish.py tests/test_apply_gate.py tests/test_runtime_apply.py tests/test_cli_help.py
git commit -m "fix: make source-informed apply flag no-op"
```

---

### Task 4: Add A Complete Output Ownership Manifest

**Files:**
- Create: `src/hsconfig/output_ownership_manifest.py`
- Modify: `src/hsconfig/report_ownership.py`
- Modify: `src/hsconfig/operator_summary.py`
- Modify: `src/hsconfig/package_builder.py`
- Modify: `tests/test_report_ownership.py`
- Modify: `tests/test_subtractive_contract_polish.py`
- Test: `tests/test_report_ownership.py`, `tests/test_subtractive_contract_polish.py`, `tests/test_apply_authority_boundary.py`

**Interfaces:**
- Consumes: `build_report_ownership() -> list[dict[str, Any]]`
- Produces: `build_output_ownership_manifest(generated_files: Sequence[str]) -> dict[str, Any]`

- [ ] **Step 1: Add failing manifest tests**

Append to `tests/test_subtractive_contract_polish.py`:

```python
from hsconfig.output_ownership_manifest import build_output_ownership_manifest


def test_output_ownership_manifest_classifies_every_generated_file():
    generated_files = [
        "CustomConfig/deck/GlobalValues.json",
        "CustomConfig/deck/Mulligan.json",
        "CustomConfig/deck/SW_448.json",
        "CustomConfig/deck/Combo.json",
        "reports/operator_summary.json",
        "reports/source_contract_audit.json",
        "reports/source_to_runtime_explainability.json",
        "reports/mechanic_drift_report.json",
    ]

    manifest = build_output_ownership_manifest(generated_files)

    assert manifest["summary"]["generated_file_count"] == len(generated_files)
    assert manifest["summary"]["unclassified_file_count"] == 0
    gate_rows = [row for row in manifest["files"] if row["classification"] == "gate"]
    assert [row["file"] for row in gate_rows] == ["reports/operator_summary.json"]
    runtime_rows = {
        row["file"]: row for row in manifest["files"] if row["file"].startswith("CustomConfig/")
    }
    assert runtime_rows["CustomConfig/deck/GlobalValues.json"]["runtime_surface"] == "GlobalValues.json"
    assert runtime_rows["CustomConfig/deck/Mulligan.json"]["runtime_surface"] == "Mulligan.json"
    assert runtime_rows["CustomConfig/deck/SW_448.json"]["runtime_surface"] == "CARDID.json"
    assert runtime_rows["CustomConfig/deck/Combo.json"]["runtime_surface"] == "Combo.json"
```

- [ ] **Step 2: Run the new test and verify it fails**

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_subtractive_contract_polish.py::test_output_ownership_manifest_classifies_every_generated_file -q
```

Expected: FAIL because `hsconfig.output_ownership_manifest` does not exist yet.

- [ ] **Step 3: Implement `output_ownership_manifest.py`**

Create `src/hsconfig/output_ownership_manifest.py`:

```python
from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from hsconfig.report_ownership import build_report_ownership


def build_output_ownership_manifest(generated_files: Sequence[str]) -> dict[str, Any]:
    report_rows = {row["file"]: dict(row) for row in build_report_ownership()}
    files = [_classify_file(str(path).replace("\\", "/"), report_rows) for path in sorted(set(generated_files))]
    unclassified = [row for row in files if row["classification"] == "unclassified"]
    gates = [row for row in files if row["classification"] == "gate"]
    return {
        "schema_version": 1,
        "authority": "diagnostic_manifest",
        "operator_gate": "reports/operator_summary.json",
        "summary": {
            "generated_file_count": len(files),
            "unclassified_file_count": len(unclassified),
            "gate_count": len(gates),
            "runtime_surface_count": sum(1 for row in files if row["runtime_surface"]),
        },
        "files": files,
    }


def _classify_file(path: str, report_rows: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if path in report_rows:
        row = dict(report_rows[path])
        return {
            "file": path,
            "producer": row.get("producer", "prepare"),
            "classification": row.get("classification", "diagnostic"),
            "authority": row.get("authority", "diagnostic"),
            "can_block_apply": row.get("classification") == "gate",
            "runtime_surface": None,
            "diagnostic_only": row.get("classification") != "gate",
        }
    runtime_surface = _runtime_surface(path)
    if runtime_surface:
        return {
            "file": path,
            "producer": "prepare",
            "classification": "runtime_surface",
            "authority": "operator_summary_listed_runtime_file",
            "can_block_apply": False,
            "runtime_surface": runtime_surface,
            "diagnostic_only": False,
        }
    return {
        "file": path,
        "producer": "unknown",
        "classification": "unclassified",
        "authority": "unknown",
        "can_block_apply": False,
        "runtime_surface": None,
        "diagnostic_only": True,
    }


def _runtime_surface(path: str) -> str | None:
    if not path.startswith("CustomConfig/") or not path.endswith(".json"):
        return None
    filename = path.rsplit("/", 1)[-1]
    if filename in {"GlobalValues.json", "Mulligan.json", "Combo.json"}:
        return filename
    if filename in {"Presume.json", "Concede.json"}:
        return "legacy_non_normal_surface"
    return "CARDID.json"
```

- [ ] **Step 4: Register manifest report ownership**

In `src/hsconfig/report_ownership.py`, add this row after `operator_summary.json`:

```python
        {
            "file": "reports/output_ownership_manifest.json",
            "producer": "prepare",
            "authority": "diagnostic_artifact_ownership",
            "classification": "diagnostic",
            "answers": "which generated artifact owns which responsibility",
            "open_order": "11",
            "notes": "diagnostic only; does not replace operator_summary.json",
        },
```

- [ ] **Step 5: Write the manifest in package build**

In `src/hsconfig/package_builder.py`, import:

```python
from hsconfig.output_ownership_manifest import build_output_ownership_manifest
```

After final `generated_files` is known and before writing `operator_summary.json`, write:

```python
    output_ownership_manifest = build_output_ownership_manifest(generated_files)
    write_json(reports_dir / "output_ownership_manifest.json", output_ownership_manifest)
    generated_files = _generated_package_files(out, deck_dir, reports_dir)
```

Then pass the refreshed `generated_files` to `build_operator_summary()`.

- [ ] **Step 6: Include manifest summary in operator summary**

In `src/hsconfig/operator_summary.py`, add an optional parameter:

```python
    output_ownership_manifest: dict[str, Any] | None = None,
```

and add this field to the returned summary:

```python
        "output_ownership_summary": _output_ownership_summary(output_ownership_manifest),
```

Add helper:

```python
def _output_ownership_summary(report: dict[str, Any] | None) -> dict[str, Any]:
    summary = report.get("summary", {}) if isinstance(report, dict) else {}
    return {
        "non_blocking": True,
        "generated_file_count": _int_value(summary.get("generated_file_count", 0)),
        "unclassified_file_count": _int_value(summary.get("unclassified_file_count", 0)),
        "gate_count": _int_value(summary.get("gate_count", 0)),
    }
```

- [ ] **Step 7: Run manifest tests**

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_subtractive_contract_polish.py::test_output_ownership_manifest_classifies_every_generated_file tests/test_report_ownership.py tests/test_apply_authority_boundary.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```powershell
git add src/hsconfig/output_ownership_manifest.py src/hsconfig/report_ownership.py src/hsconfig/operator_summary.py src/hsconfig/package_builder.py tests/test_subtractive_contract_polish.py tests/test_report_ownership.py tests/test_apply_authority_boundary.py
git commit -m "feat: classify generated output ownership"
```

---

### Task 5: Build Operator Summary Once In Package Builder

**Files:**
- Modify: `src/hsconfig/package_builder.py`
- Modify: `tests/test_subtractive_contract_polish.py`
- Test: `tests/test_subtractive_contract_polish.py`, `tests/test_configure_cli.py`, `tests/test_shadowpriest_e2e.py`

**Interfaces:**
- Consumes: `build_operator_summary(...) -> dict[str, Any]`
- Produces: package build flow that calls `build_operator_summary()` once.

- [ ] **Step 1: Add a call-count regression test**

Append to `tests/test_subtractive_contract_polish.py`:

```python
import inspect

import hsconfig.package_builder as package_builder


def test_package_builder_calls_build_operator_summary_once_in_prepare_flow():
    source = inspect.getsource(package_builder.prepare_payload)
    assert source.count("build_operator_summary(") == 1
```

This is intentionally a structural drift test. It protects the single-gate summary flow from regressing back into draft/final double-build behavior.

- [ ] **Step 2: Run and verify failure**

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_subtractive_contract_polish.py::test_package_builder_calls_build_operator_summary_once_in_prepare_flow -q
```

Expected: FAIL because `prepare_payload()` currently calls `build_operator_summary()` twice.

- [ ] **Step 3: Refactor `prepare_payload()`**

In `src/hsconfig/package_builder.py`, remove the first `operator_summary = build_operator_summary(...)` call before `build_strong_promotion_report()`.

Build `strong_promotion_report` from a compact provisional dict derived from known validation inputs:

```python
    generated_files = _generated_package_files(
        out,
        deck_dir,
        reports_dir,
        expected_report_files=("operator_summary.json", "strong_promotion_report.json", "output_ownership_manifest.json"),
    )
    output_ownership_manifest = build_output_ownership_manifest(generated_files)
    write_json(reports_dir / "output_ownership_manifest.json", output_ownership_manifest)
    generated_files = _generated_package_files(
        out,
        deck_dir,
        reports_dir,
        expected_report_files=("operator_summary.json", "strong_promotion_report.json"),
    )
    operator_summary = build_operator_summary(
        generated_files=generated_files,
        output_ownership_manifest=output_ownership_manifest,
        **operator_summary_kwargs,
    )
```

Then build `strong_promotion_report` after `operator_summary` and write it:

```python
    strong_promotion_report = build_strong_promotion_report(
        deck_name=args.deck_name,
        fixture_stage="runtime_prepare",
        operator_summary=operator_summary,
        source_claim_gap_report=source_claim_gap_report,
    )
    write_json(reports_dir / "strong_promotion_report.json", strong_promotion_report)
    write_json(reports_dir / "operator_summary.json", operator_summary)
```

Update `_generated_package_files()` signature:

```python
def _generated_package_files(
    out: Path,
    deck_dir: Path,
    reports_dir: Path,
    *,
    expected_report_files: tuple[str, ...] = ("operator_summary.json",),
) -> list[str]:
    files = [
        *sorted(deck_dir.glob("*.json")),
        *sorted(path for path in reports_dir.rglob("*") if path.is_file()),
        *(reports_dir / filename for filename in expected_report_files),
    ]
    return sorted({str(path.relative_to(out)) for path in files})
```

- [ ] **Step 4: Run focused package tests**

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_subtractive_contract_polish.py::test_package_builder_calls_build_operator_summary_once_in_prepare_flow tests/test_configure_cli.py tests/test_shadowpriest_e2e.py -q
```

Expected: PASS. If `operator_summary.generated_files` misses `strong_promotion_report.json` or `output_ownership_manifest.json`, adjust `expected_report_files` and rerun.

- [ ] **Step 5: Commit**

```powershell
git add src/hsconfig/package_builder.py tests/test_subtractive_contract_polish.py
git commit -m "refactor: build operator summary once"
```

---

### Task 6: Harden Contract Spine Sentinel

**Files:**
- Modify: `src/hsconfig/contract_spine_sentinel.py`
- Modify: `tests/test_contract_spine_sentinel.py`
- Modify: `tests/test_subtractive_contract_polish.py`
- Test: `tests/test_contract_spine_sentinel.py`, `tests/test_subtractive_contract_polish.py`

**Interfaces:**
- Consumes: `build_contract_spine_sentinel_report(repo_root: str | Path | None = None) -> dict[str, Any]`
- Produces: sentinel checks for no legacy normal routing, no unclassified generated reports, and no second apply authority.

- [ ] **Step 1: Add sentinel expectation test**

Append to `tests/test_subtractive_contract_polish.py`:

```python
from hsconfig.contract_spine_sentinel import build_contract_spine_sentinel_report


def test_contract_spine_sentinel_covers_subtractive_contract_polish():
    report = build_contract_spine_sentinel_report()
    checks = report["checks"]

    assert "legacy_surface_normal_routing" in checks
    assert "source_informed_apply_flag_policy" in checks
    assert "report_ownership_gate_files" in checks
    assert "report_ownership_unclassified_files" in checks
    assert checks["legacy_surface_normal_routing"] == []
    assert checks["source_informed_apply_flag_policy"]["behavior"] == "legacy_no_op"
    assert checks["report_ownership_gate_files"] == ["reports/operator_summary.json"]
```

- [ ] **Step 2: Run and verify failure**

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_subtractive_contract_polish.py::test_contract_spine_sentinel_covers_subtractive_contract_polish -q
```

Expected: FAIL because the new sentinel keys do not exist yet.

- [ ] **Step 3: Add sentinel checks**

In `src/hsconfig/contract_spine_sentinel.py`, import:

```python
from hsconfig.report_ownership import build_report_ownership
```

Add to `checks`:

```python
        "legacy_surface_normal_routing": _legacy_surface_normal_routing(root),
        "source_informed_apply_flag_policy": _source_informed_apply_flag_policy(root),
        "report_ownership_gate_files": _report_ownership_gate_files(),
        "report_ownership_unclassified_files": _report_ownership_unclassified_files(),
```

Add helpers:

```python
def _legacy_surface_normal_routing(root: Path) -> list[dict[str, str]]:
    path = root / "src/hsconfig/surface_intent.py"
    if not path.exists():
        return [{"path": "src/hsconfig/surface_intent.py", "reason": "missing"}]
    content = path.read_text(encoding="utf-8")
    flagged = []
    for token in ("legacy_policy_surfaces_enabled", 'optional_surfaces.add("Presume.json")', 'optional_surfaces.add("Concede.json")'):
        if token in content:
            flagged.append({"path": "src/hsconfig/surface_intent.py", "token": token})
    return flagged


def _source_informed_apply_flag_policy(root: Path) -> dict[str, str]:
    apply_gate = root / "src/hsconfig/apply_gate.py"
    content = apply_gate.read_text(encoding="utf-8") if apply_gate.exists() else ""
    if "del allow_source_informed" in content:
        return {"behavior": "legacy_no_op"}
    return {"behavior": "drift_detected"}


def _report_ownership_gate_files() -> list[str]:
    return sorted(
        row["file"]
        for row in build_report_ownership()
        if row.get("classification") == "gate"
    )


def _report_ownership_unclassified_files() -> list[str]:
    return sorted(
        row.get("file", "")
        for row in build_report_ownership()
        if not row.get("classification")
    )
```

Add these keys to `list_checks` inside `_problems()`:

```python
        "legacy_surface_normal_routing",
        "report_ownership_unclassified_files",
```

Add explicit problem checks:

```python
    if checks.get("source_informed_apply_flag_policy", {}).get("behavior") != "legacy_no_op":
        problems.append(
            {
                "check": "source_informed_apply_flag_policy",
                "value": checks.get("source_informed_apply_flag_policy"),
            }
        )

    if checks.get("report_ownership_gate_files") != ["reports/operator_summary.json"]:
        problems.append(
            {
                "check": "report_ownership_gate_files",
                "value": checks.get("report_ownership_gate_files"),
            }
        )
```

- [ ] **Step 4: Run sentinel tests**

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_subtractive_contract_polish.py::test_contract_spine_sentinel_covers_subtractive_contract_polish tests/test_contract_spine_sentinel.py -q
```

Expected: PASS.

- [ ] **Step 5: Run the sentinel command**

```powershell
$env:PYTHONPATH='src'; python -m hsconfig contract-spine-sentinel --json
```

Expected JSON fields:

```json
{
  "status": "clean",
  "apply_blocking": false,
  "problems": []
}
```

- [ ] **Step 6: Commit**

```powershell
git add src/hsconfig/contract_spine_sentinel.py tests/test_contract_spine_sentinel.py tests/test_subtractive_contract_polish.py
git commit -m "test: harden contract spine sentinel"
```

---

### Task 7: Align Operator Docs And Skill Text

**Files:**
- Modify: `docs/operator/README.md`
- Modify: `docs/operator/guide-research-policy.md`
- Modify: `docs/operator/universal-wild-no-block-contract.md`
- Modify: `.agents/skills/hsconfig/SKILL.md`
- Modify: `.agents/skills/hsconfig/references/workflow.md`
- Modify: `.agents/skills/hsconfig/references/visionai-surfaces.md`
- Modify: `tests/test_skill_files.py`
- Modify: `tests/test_docs_active_path.py`
- Test: `tests/test_skill_files.py`, `tests/test_docs_active_path.py`

**Interfaces:**
- Consumes: existing operator docs and skill reference tests.
- Produces: one consistent active path: configure -> inspect `operator_summary.json` -> guarded apply.

- [ ] **Step 1: Add doc-scan test for no active legacy confusion**

Append to `tests/test_subtractive_contract_polish.py`:

```python
from pathlib import Path


ACTIVE_DOC_PATHS = [
    Path("docs/operator/README.md"),
    Path("docs/operator/guide-research-policy.md"),
    Path("docs/operator/universal-wild-no-block-contract.md"),
    Path(".agents/skills/hsconfig/SKILL.md"),
    Path(".agents/skills/hsconfig/references/workflow.md"),
    Path(".agents/skills/hsconfig/references/visionai-surfaces.md"),
]


def test_active_docs_describe_legacy_surfaces_as_non_normal_only():
    for path in ACTIVE_DOC_PATHS:
        text = path.read_text(encoding="utf-8")
        assert "operator_summary.json" in text
        assert "legacy/diagnostic" in text or "outside the normal HSConfig output path" in text
        assert "emit Presume.json" not in text
        assert "emit Concede.json" not in text
        assert "second apply gate" not in text.lower()
```

- [ ] **Step 2: Run doc test and capture current failures**

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_subtractive_contract_polish.py::test_active_docs_describe_legacy_surfaces_as_non_normal_only -q
```

Expected: FAIL if any active doc still says to emit legacy surfaces or uses confusing public-doc wording.

- [ ] **Step 3: Patch docs to the single active wording**

Use this exact wording where docs mention `Presume.json` or `Concede.json`:

```markdown
`Presume.json` and `Concede.json` are legacy/diagnostic VisionAI surfaces outside the normal HSConfig output path. Their absence never blocks a valid load-safe package, and their presence in a normal package is treated as drift.
```

Use this exact wording where docs mention `--allow-source-informed`:

```markdown
`--allow-source-informed` is a backward-compatible legacy no-op. It does not create a second apply path. Runtime apply decisions come from `reports/operator_summary.json`.
```

Use this exact wording for report authority:

```markdown
Open `reports/operator_summary.json` first. Other reports explain source quality, mechanic coverage, ownership, and missing links. They do not grant apply permission.
```

- [ ] **Step 4: Update existing doc tests**

Where `tests/test_skill_files.py` or `tests/test_docs_active_path.py` expects old wording such as `publicly documented` or `emit Presume.json`, replace the expectation with the wording from Step 3.

- [ ] **Step 5: Run doc tests**

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_subtractive_contract_polish.py::test_active_docs_describe_legacy_surfaces_as_non_normal_only tests/test_skill_files.py tests/test_docs_active_path.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add docs/operator/README.md docs/operator/guide-research-policy.md docs/operator/universal-wild-no-block-contract.md .agents/skills/hsconfig/SKILL.md .agents/skills/hsconfig/references/workflow.md .agents/skills/hsconfig/references/visionai-surfaces.md tests/test_skill_files.py tests/test_docs_active_path.py tests/test_subtractive_contract_polish.py
git commit -m "docs: align contract polish operator path"
```

---

### Task 8: Final Verification And Push

**Files:**
- Modify: none unless tests expose a defect
- Test: full targeted and full suite

**Interfaces:**
- Consumes: all previous tasks.
- Produces: clean branch ready for merge or direct push workflow.

- [ ] **Step 1: Run focused contract-polish suite**

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_subtractive_contract_polish.py tests/test_surface_intent.py tests/test_apply_gate.py tests/test_runtime_apply.py tests/test_report_ownership.py tests/test_apply_authority_boundary.py tests/test_contract_spine_sentinel.py tests/test_skill_files.py tests/test_docs_active_path.py -q
```

Expected: all tests PASS.

- [ ] **Step 2: Run representative E2E and no-block suites**

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_shadowpriest_e2e.py tests/test_shadowpriest_depth_e2e.py tests/test_universal_wild_no_block_matrix.py tests/test_supplemental_visibility_decks.py tests/test_supplemental_cute_warrior_load_safe.py -q
```

Expected: all tests PASS.

- [ ] **Step 3: Run contract spine sentinel**

```powershell
$env:PYTHONPATH='src'; python -m hsconfig contract-spine-sentinel --json
```

Expected:

```json
{
  "status": "clean",
  "apply_blocking": false,
  "problems": []
}
```

- [ ] **Step 4: Validate the research package used for this plan**

```powershell
python 'C:\Users\darbo\.codex\skills\research\validate_json.py' --fields 'docs\research\2026-07-13-hsconfig-source-contract-logic-brainstorm-v4\fields.yaml' --dir 'docs\research\2026-07-13-hsconfig-source-contract-logic-brainstorm-v4\results'
```

Expected:

```text
Validation passed: 5/5
Average coverage: 100.0%
```

- [ ] **Step 5: Run full test suite**

```powershell
$env:PYTHONPATH='src'; python -m pytest -q
```

Expected: all tests PASS. The previous baseline before this plan was `1029 passed, 2 skipped`; the exact count may increase because this plan adds tests.

- [ ] **Step 6: Check generated or accidental files**

```powershell
git status --short --branch
```

Expected: only intentional source, test, docs, and plan changes are present. No raw runtime evidence, logs, caches, or private runtime files.

- [ ] **Step 7: Commit final verification fixes if needed**

If Step 1-6 required small fixes:

```powershell
git add src tests docs .agents
git commit -m "test: verify subtractive contract polish"
```

If no fixes were needed, skip this commit.

- [ ] **Step 8: Push branch**

```powershell
git push origin HEAD
```

Expected: branch updates on GitHub.

---

## Self-Review

**Spec coverage:**  
The plan covers legacy surface quarantine, source-informed apply no-op behavior, full output ownership, single-pass `operator_summary`, contract-spine sentinel hardening, active docs, targeted verification, and full-suite verification.

**Placeholder scan:**  
No placeholder requirements are intentionally left. Each task names exact files, exact tests, and expected command outcomes.

**Type consistency:**  
The new interface is `build_output_ownership_manifest(generated_files: Sequence[str]) -> dict[str, Any]`. Existing interfaces keep compatibility signatures where needed: `evaluate_apply_gate(..., allow_source_informed=False)` and `apply_package(..., allow_source_informed=False)`.

**Scope check:**  
This is one coherent polish wave. It does not implement new Hearthstone semantics, new guide research, new runtime surfaces, or HSTuner-style post-game tuning.


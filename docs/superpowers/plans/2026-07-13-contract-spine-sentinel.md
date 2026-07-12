# Contract Spine Sentinel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a small CI-friendly sentinel that prevents HSConfig source-contract drift while preserving `operator_summary.json` as the sole runtime apply authority.

**Architecture:** Keep the existing source-contract spine as the source of truth. Add one read-only sentinel module that projects current policy, conformance, diagnostic-only, and apply-boundary invariants into a compact report, plus tests and a diagnostic CLI command. Do not add new runtime surfaces, new package states, or a new apply gate.

**Tech Stack:** Python standard library, existing `hsconfig` package, `pytest`, current CLI parser/command pattern, current source-contract modules.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig`.
- Keep HSConfig pre-run only: no replay parsing, no winrate analysis, no post-game tuning logic.
- `reports/operator_summary.json` remains the only normal runtime apply authority.
- `source_contract_audit.json`, `source_to_runtime_explainability.json`, `source_contract_conformance`, and `contract_spine_rows` remain diagnostic-only.
- A valid load-safe package must not be blocked by source thinness, report-only claims, unsupported runtime surfaces, or low confidence.
- Technical invalidity still blocks: malformed JSON, missing `GlobalValues.json`, missing `Mulligan.json`, undeclared runtime files, nested runtime files, or forbidden normal-path `Presume.json` / `Concede.json`.
- Preserve the Darkbishop boundary: `hero_power_transform` can emit card/effect semantics, but must not become an opening-hand `mulligan_keep` without explicit hand-required evidence.
- No new dependency.
- No broad refactor.
- No raw runtime evidence or HearthRanger logs.

---

## File Structure

- Create `src/hsconfig/contract_spine_sentinel.py`
  - Responsibility: build a read-only report that checks claim-kind coverage, diagnostic-only invariants, apply-boundary isolation, and known critical lifecycle rows.
- Create `src/hsconfig/commands/contract_spine_sentinel.py`
  - Responsibility: expose the sentinel report as a diagnostic CLI command with optional JSON output file.
- Modify `src/hsconfig/cli_parser.py`
  - Responsibility: register `contract-spine-sentinel`.
- Modify `src/hsconfig/cli.py`
  - Responsibility: dispatch `contract-spine-sentinel`.
- Create `tests/test_contract_spine_sentinel.py`
  - Responsibility: test the sentinel report directly.
- Modify `tests/test_cli_help.py`
  - Responsibility: verify the diagnostic command appears in CLI help and is not described as a normal operator path.
- Create `tests/test_contract_spine_sentinel_cli.py`
  - Responsibility: verify command JSON output and exit status.
- Modify `.agents/skills/hsconfig/SKILL.md`
  - Responsibility: mention the sentinel as a developer diagnostic, not as an operator gate.
- Modify `docs/operator/README.md`
  - Responsibility: add one short developer diagnostic pointer without changing the normal operator path.

---

### Task 1: Add The Read-Only Contract Spine Sentinel Core

**Files:**
- Create: `src/hsconfig/contract_spine_sentinel.py`
- Create: `tests/test_contract_spine_sentinel.py`

**Interfaces:**
- Consumes:
  - `hsconfig.source_document_model.SUPPORTED_ATOMIC_CLAIM_KINDS`
  - `hsconfig.source_contract_matrix.source_contract_policy_by_claim_kind() -> dict[str, dict[str, object]]`
  - `hsconfig.source_contract_conformance.build_source_contract_conformance_snapshot() -> dict`
- Produces:
  - `build_contract_spine_sentinel_report(repo_root: str | Path | None = None) -> dict[str, object]`
  - Report shape:
    - `schema_version: 1`
    - `status: "clean" | "drift_detected"`
    - `operator_gate_impact: "diagnostic_only"`
    - `apply_blocking: False`
    - `checks: dict[str, object]`
    - `problems: list[dict[str, object]]`

- [ ] **Step 1: Write failing tests for a clean sentinel report**

Add `tests/test_contract_spine_sentinel.py`:

```python
from __future__ import annotations

from hsconfig.contract_spine_sentinel import build_contract_spine_sentinel_report
from hsconfig.source_document_model import SUPPORTED_ATOMIC_CLAIM_KINDS


def test_contract_spine_sentinel_report_is_clean_for_current_repo():
    report = build_contract_spine_sentinel_report()

    assert report["schema_version"] == 1
    assert report["status"] == "clean"
    assert report["operator_gate_impact"] == "diagnostic_only"
    assert report["apply_blocking"] is False
    assert report["problems"] == []


def test_contract_spine_sentinel_covers_every_supported_claim_kind():
    report = build_contract_spine_sentinel_report()
    checks = report["checks"]

    assert set(checks["supported_claim_kinds"]) == set(SUPPORTED_ATOMIC_CLAIM_KINDS)
    assert checks["policy_missing_claim_kinds"] == []
    assert checks["policy_extra_claim_kinds"] == []
    assert checks["spine_missing_claim_kinds"] == []
    assert checks["spine_extra_claim_kinds"] == []


def test_contract_spine_sentinel_preserves_diagnostic_only_boundary():
    report = build_contract_spine_sentinel_report()
    checks = report["checks"]

    assert checks["non_diagnostic_policy_claim_kinds"] == []
    assert checks["spine_rows_with_apply_authority_fields"] == []
    assert checks["conformance_operator_gate_impact"] == "diagnostic_only"
    assert checks["conformance_apply_authority_fields_present"] == []


def test_contract_spine_sentinel_keeps_critical_runtime_boundaries_visible():
    report = build_contract_spine_sentinel_report()
    critical = report["checks"]["critical_boundary_rows"]

    assert critical["mulligan_keep"]["allowed_surfaces"] == ["mulligan"]
    assert critical["mulligan_keep"]["final_runtime_effect"] == "emits_mulligan_runtime_row"

    assert critical["hero_power_transform"]["allowed_surfaces"] == ["cardid"]
    assert critical["hero_power_transform"]["final_runtime_effect"] == "emits_cardid_runtime_row"

    assert critical["globalvalue_numeric_tuning"]["allowed_surfaces"] == []
    assert critical["globalvalue_numeric_tuning"]["final_runtime_effect"] == (
        "suppressed_until_runtime_evidence"
    )


def test_contract_spine_sentinel_keeps_start_of_game_out_of_mulligan_keep():
    report = build_contract_spine_sentinel_report()
    suppression = report["checks"]["start_of_game_mulligan_suppression"]

    assert suppression["decision"] == "rejected"
    assert suppression["reason"] == "start_of_game_effect_does_not_require_opening_hand"
    assert "do not become opening-hand keeps" in suppression["operator_meaning"]
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_contract_spine_sentinel.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'hsconfig.contract_spine_sentinel'`.

- [ ] **Step 3: Implement the sentinel module**

Create `src/hsconfig/contract_spine_sentinel.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any

from hsconfig.source_contract_conformance import build_source_contract_conformance_snapshot
from hsconfig.source_contract_matrix import source_contract_policy_by_claim_kind
from hsconfig.source_document_model import SUPPORTED_ATOMIC_CLAIM_KINDS


FORBIDDEN_APPLY_AUTHORITY_FIELDS = {
    "apply_allowed",
    "apply_gate",
    "apply_policy",
    "next_action",
    "runtime_apply_allowed",
    "runtime_apply_mode",
    "technical_status",
}

ACTIVE_APPLY_PATHS = (
    "src/hsconfig/apply_gate.py",
    "src/hsconfig/runtime_apply.py",
    "src/hsconfig/commands/apply.py",
)

DIAGNOSTIC_ONLY_TOKENS = (
    "source_contract_audit",
    "source_to_runtime_explainability",
    "source_contract_conformance",
    "contract_spine_rows",
    "claim_lifecycle_rows",
)

CRITICAL_CLAIM_KINDS = (
    "mulligan_keep",
    "hero_power_transform",
    "globalvalue_numeric_tuning",
    "combo_sequence",
    "archetype",
)


def build_contract_spine_sentinel_report(
    repo_root: str | Path | None = None,
) -> dict[str, Any]:
    """Return a read-only drift report for the source-contract spine.

    The sentinel is a developer diagnostic. It never grants or denies runtime
    apply permission; `reports/operator_summary.json` remains the apply authority.
    """
    root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[2]
    policy = source_contract_policy_by_claim_kind()
    conformance = build_source_contract_conformance_snapshot()
    spine_rows = conformance.get("contract_spine_rows", [])

    checks = {
        "supported_claim_kinds": sorted(SUPPORTED_ATOMIC_CLAIM_KINDS),
        "policy_missing_claim_kinds": _missing(SUPPORTED_ATOMIC_CLAIM_KINDS, policy),
        "policy_extra_claim_kinds": _extra(SUPPORTED_ATOMIC_CLAIM_KINDS, policy),
        "spine_missing_claim_kinds": _missing(
            SUPPORTED_ATOMIC_CLAIM_KINDS,
            {str(row.get("claim_kind")): row for row in spine_rows if isinstance(row, dict)},
        ),
        "spine_extra_claim_kinds": _extra(
            SUPPORTED_ATOMIC_CLAIM_KINDS,
            {str(row.get("claim_kind")): row for row in spine_rows if isinstance(row, dict)},
        ),
        "non_diagnostic_policy_claim_kinds": _non_diagnostic_policy_claim_kinds(policy),
        "spine_rows_with_apply_authority_fields": _spine_rows_with_apply_fields(spine_rows),
        "conformance_operator_gate_impact": conformance.get("operator_gate_impact"),
        "conformance_apply_authority_fields_present": sorted(
            FORBIDDEN_APPLY_AUTHORITY_FIELDS.intersection(conformance)
        ),
        "critical_boundary_rows": _critical_boundary_rows(spine_rows),
        "start_of_game_mulligan_suppression": conformance.get(
            "start_of_game_mulligan_suppression",
            {},
        ),
        "active_apply_diagnostic_consumers": _active_apply_diagnostic_consumers(root),
    }
    problems = _problems(checks)
    return {
        "schema_version": 1,
        "status": "clean" if not problems else "drift_detected",
        "authority": "diagnostic_only",
        "operator_gate_impact": "diagnostic_only",
        "apply_blocking": False,
        "checks": checks,
        "problems": problems,
    }


def _missing(expected: tuple[str, ...], actual: dict[str, object]) -> list[str]:
    return sorted(set(expected) - set(actual))


def _extra(expected: tuple[str, ...], actual: dict[str, object]) -> list[str]:
    return sorted(set(actual) - set(expected))


def _non_diagnostic_policy_claim_kinds(policy: dict[str, dict[str, Any]]) -> list[str]:
    return sorted(
        claim_kind
        for claim_kind, row in policy.items()
        if row.get("operator_gate_impact") != "diagnostic_only"
    )


def _spine_rows_with_apply_fields(spine_rows: object) -> list[dict[str, object]]:
    if not isinstance(spine_rows, list):
        return [{"claim_kind": "__invalid_spine_rows__", "fields": ["not_a_list"]}]
    flagged: list[dict[str, object]] = []
    for row in spine_rows:
        if not isinstance(row, dict):
            flagged.append({"claim_kind": "__invalid_row__", "fields": ["not_a_dict"]})
            continue
        fields = sorted(FORBIDDEN_APPLY_AUTHORITY_FIELDS.intersection(row))
        if fields:
            flagged.append({"claim_kind": row.get("claim_kind", ""), "fields": fields})
    return flagged


def _critical_boundary_rows(spine_rows: object) -> dict[str, dict[str, object]]:
    rows_by_kind = {
        str(row.get("claim_kind")): row
        for row in spine_rows
        if isinstance(row, dict)
    }
    return {
        claim_kind: {
            "policy_lane": rows_by_kind.get(claim_kind, {}).get("policy_lane"),
            "allowed_surfaces": rows_by_kind.get(claim_kind, {}).get("allowed_surfaces"),
            "surface_gate_status": rows_by_kind.get(claim_kind, {}).get("surface_gate_status"),
            "builder_status": rows_by_kind.get(claim_kind, {}).get("builder_status"),
            "final_runtime_effect": rows_by_kind.get(claim_kind, {}).get("final_runtime_effect"),
            "operator_gate_impact": rows_by_kind.get(claim_kind, {}).get("operator_gate_impact"),
        }
        for claim_kind in CRITICAL_CLAIM_KINDS
    }


def _active_apply_diagnostic_consumers(root: Path) -> list[dict[str, str]]:
    consumers: list[dict[str, str]] = []
    for relative_path in ACTIVE_APPLY_PATHS:
        path = root / relative_path
        content = path.read_text(encoding="utf-8")
        for token in DIAGNOSTIC_ONLY_TOKENS:
            if token in content:
                consumers.append({"path": relative_path, "token": token})
    return consumers


def _problems(checks: dict[str, Any]) -> list[dict[str, object]]:
    problems: list[dict[str, object]] = []
    list_checks = (
        "policy_missing_claim_kinds",
        "policy_extra_claim_kinds",
        "spine_missing_claim_kinds",
        "spine_extra_claim_kinds",
        "non_diagnostic_policy_claim_kinds",
        "spine_rows_with_apply_authority_fields",
        "conformance_apply_authority_fields_present",
        "active_apply_diagnostic_consumers",
    )
    for key in list_checks:
        value = checks.get(key, [])
        if value:
            problems.append({"check": key, "value": value})

    if checks.get("conformance_operator_gate_impact") != "diagnostic_only":
        problems.append(
            {
                "check": "conformance_operator_gate_impact",
                "value": checks.get("conformance_operator_gate_impact"),
            }
        )

    suppression = checks.get("start_of_game_mulligan_suppression", {})
    if not isinstance(suppression, dict) or suppression.get("decision") != "rejected":
        problems.append(
            {
                "check": "start_of_game_mulligan_suppression",
                "value": suppression,
            }
        )
    return problems
```

- [ ] **Step 4: Run sentinel tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_contract_spine_sentinel.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 1**

```powershell
git add src/hsconfig/contract_spine_sentinel.py tests/test_contract_spine_sentinel.py
git commit -m "test: add contract spine sentinel core"
```

---

### Task 2: Add A Diagnostic CLI Command

**Files:**
- Create: `src/hsconfig/commands/contract_spine_sentinel.py`
- Modify: `src/hsconfig/cli_parser.py`
- Modify: `src/hsconfig/cli.py`
- Create: `tests/test_contract_spine_sentinel_cli.py`
- Modify: `tests/test_cli_help.py`

**Interfaces:**
- Consumes:
  - `build_contract_spine_sentinel_report(repo_root: str | Path | None = None) -> dict`
  - existing `run_payload_command(args, payload)`
- Produces:
  - CLI command: `hsconfig contract-spine-sentinel --json`
  - Optional output: `hsconfig contract-spine-sentinel --out reports/contract_spine_sentinel.json --json`
  - Exit code `0` when sentinel status is `clean`, `1` when status is `drift_detected`.

- [ ] **Step 1: Write failing CLI tests**

Create `tests/test_contract_spine_sentinel_cli.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from hsconfig.cli import main


def test_contract_spine_sentinel_cli_returns_clean_json(capsys):
    exit_code = main(["contract-spine-sentinel", "--json"])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["status"] == "clean"
    assert output["operator_gate_impact"] == "diagnostic_only"
    assert output["apply_blocking"] is False
    assert output["problems"] == []


def test_contract_spine_sentinel_cli_can_write_json_report(tmp_path: Path, capsys):
    out = tmp_path / "contract_spine_sentinel.json"

    exit_code = main(["contract-spine-sentinel", "--out", str(out), "--json"])
    output = json.loads(capsys.readouterr().out)
    written = json.loads(out.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert output["written_report"] == str(out)
    assert written["status"] == "clean"
    assert written["operator_gate_impact"] == "diagnostic_only"
```

Modify `tests/test_cli_help.py` with:

```python
def test_contract_spine_sentinel_help_is_diagnostic_only(capsys):
    help_text = _subcommand_help("contract-spine-sentinel", capsys)

    assert "read-only contract-spine drift diagnostic" in help_text
    assert "does not grant apply permission" in help_text
    assert "--out" in help_text
    assert "--json" in help_text
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_contract_spine_sentinel_cli.py tests/test_cli_help.py::test_contract_spine_sentinel_help_is_diagnostic_only -q
```

Expected: FAIL with invalid choice `contract-spine-sentinel`.

- [ ] **Step 3: Implement command wrapper**

Create `src/hsconfig/commands/contract_spine_sentinel.py`:

```python
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from hsconfig.commands.common import run_payload_command
from hsconfig.contract_spine_sentinel import build_contract_spine_sentinel_report
from hsconfig.io import write_json


def run_contract_spine_sentinel_command(args: argparse.Namespace) -> int:
    return run_payload_command(args, contract_spine_sentinel_payload)


def contract_spine_sentinel_payload(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    report = build_contract_spine_sentinel_report()
    if getattr(args, "out", None):
        out = Path(args.out)
        _assert_safe_json_output(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        write_json(out, report)
        report = {**report, "written_report": str(out)}
    return report, 0 if report.get("status") == "clean" else 1


def _assert_safe_json_output(path: Path) -> None:
    parts = {part.lower() for part in path.parts}
    runtime_file_names = {
        "deck_config.ini",
        "globalvalues.json",
        "mulligan.json",
        "combo.json",
        "concede.json",
        "presume.json",
    }
    name = path.name.lower()
    if path.suffix.lower() != ".json":
        raise ValueError("contract-spine-sentinel --out must be a .json diagnostic report path")
    if "customconfig" in parts or name in runtime_file_names:
        raise ValueError(
            "contract-spine-sentinel --out must not target HearthRanger runtime files"
        )
```

- [ ] **Step 4: Register parser entry**

Modify `src/hsconfig/cli_parser.py` after the `contract-doctor` parser:

```python
    contract_spine_sentinel = subparsers.add_parser(
        "contract-spine-sentinel",
        help="read-only contract-spine drift diagnostic",
        description=(
            "Read the current source-contract policy, conformance snapshot, "
            "diagnostic-only reports, and apply-boundary files to detect drift. "
            "This command does not grant apply permission and never writes runtime files."
        ),
    )
    contract_spine_sentinel.add_argument("--out", help="Optional JSON output path.")
    contract_spine_sentinel.add_argument("--json", action="store_true")
```

- [ ] **Step 5: Register CLI dispatch**

Modify `src/hsconfig/cli.py` imports:

```python
from hsconfig.commands.contract_spine_sentinel import (
    run_contract_spine_sentinel_command,
)
```

Add dispatch after `contract-doctor`:

```python
    if args.command == "contract-spine-sentinel":
        return run_contract_spine_sentinel_command(args)
```

- [ ] **Step 6: Run CLI tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_contract_spine_sentinel_cli.py tests/test_cli_help.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit Task 2**

```powershell
git add src/hsconfig/commands/contract_spine_sentinel.py src/hsconfig/cli_parser.py src/hsconfig/cli.py tests/test_contract_spine_sentinel_cli.py tests/test_cli_help.py
git commit -m "feat: expose contract spine sentinel diagnostic"
```

---

### Task 3: Add Drift Simulation Tests

**Files:**
- Modify: `tests/test_contract_spine_sentinel.py`

**Interfaces:**
- Consumes:
  - `build_contract_spine_sentinel_report(repo_root=None)`
- Produces:
  - Regression tests proving the sentinel detects drift instead of silently staying clean.

- [ ] **Step 1: Add tests that simulate policy and apply-boundary drift**

Append to `tests/test_contract_spine_sentinel.py`:

```python
def test_contract_spine_sentinel_flags_non_diagnostic_policy(monkeypatch):
    from hsconfig import contract_spine_sentinel as sentinel

    original = sentinel.source_contract_policy_by_claim_kind

    def drifted_policy():
        policy = original()
        policy["mulligan_keep"] = {
            **policy["mulligan_keep"],
            "operator_gate_impact": "apply_gate",
        }
        return policy

    monkeypatch.setattr(sentinel, "source_contract_policy_by_claim_kind", drifted_policy)

    report = build_contract_spine_sentinel_report()

    assert report["status"] == "drift_detected"
    assert {
        "check": "non_diagnostic_policy_claim_kinds",
        "value": ["mulligan_keep"],
    } in report["problems"]


def test_contract_spine_sentinel_flags_apply_authority_fields(monkeypatch):
    from hsconfig import contract_spine_sentinel as sentinel

    original = sentinel.build_source_contract_conformance_snapshot

    def drifted_snapshot():
        snapshot = original()
        snapshot["runtime_apply_allowed"] = True
        snapshot["contract_spine_rows"] = [
            {**snapshot["contract_spine_rows"][0], "apply_policy": "fake_gate"},
            *snapshot["contract_spine_rows"][1:],
        ]
        return snapshot

    monkeypatch.setattr(sentinel, "build_source_contract_conformance_snapshot", drifted_snapshot)

    report = build_contract_spine_sentinel_report()

    assert report["status"] == "drift_detected"
    assert {
        "check": "conformance_apply_authority_fields_present",
        "value": ["runtime_apply_allowed"],
    } in report["problems"]
    assert report["checks"]["spine_rows_with_apply_authority_fields"][0]["fields"] == [
        "apply_policy"
    ]
```

- [ ] **Step 2: Run drift tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_contract_spine_sentinel.py -q
```

Expected: PASS.

- [ ] **Step 3: Commit Task 3**

```powershell
git add tests/test_contract_spine_sentinel.py
git commit -m "test: prove contract spine sentinel catches drift"
```

---

### Task 4: Document The Sentinel Without Expanding Operator Burden

**Files:**
- Modify: `.agents/skills/hsconfig/SKILL.md`
- Modify: `docs/operator/README.md`

**Interfaces:**
- Consumes:
  - CLI command `hsconfig contract-spine-sentinel --json`
- Produces:
  - One skill note and one operator doc note that classify the command as developer diagnostic only.

- [ ] **Step 1: Add focused docs test**

Create or modify `tests/test_contract_spine_sentinel_docs.py`:

```python
from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def test_contract_spine_sentinel_is_documented_as_diagnostic_only():
    skill = _read(".agents/skills/hsconfig/SKILL.md")
    operator = _read("docs/operator/README.md")

    for content in (skill, operator):
        assert "contract-spine-sentinel" in content
        assert "diagnostic" in content.lower()
        assert "operator_summary.json" in content


def test_docs_do_not_make_sentinel_the_normal_operator_path():
    operator = _read("docs/operator/README.md")

    assert "Preferred normal path" in operator or "configure" in operator
    assert "contract-spine-sentinel -> apply" not in operator
    assert "contract-spine-sentinel --apply" not in operator
```

- [ ] **Step 2: Run docs test to verify failure**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_contract_spine_sentinel_docs.py -q
```

Expected: FAIL because the new command is not documented yet.

- [ ] **Step 3: Update skill note**

In `.agents/skills/hsconfig/SKILL.md`, add one bullet near the existing source-contract diagnostic bullets:

```markdown
- Developer diagnostic: `hsconfig contract-spine-sentinel --json` checks that claim-kind policy, conformance, diagnostic-only reports, and apply-boundary files still form one contract spine. It is not an operator gate; `operator_summary.json` remains the normal apply authority.
```

- [ ] **Step 4: Update operator docs**

In `docs/operator/README.md`, add one compact note near diagnostic commands:

```markdown
Developer drift check: `hsconfig contract-spine-sentinel --json` verifies that source-contract diagnostics have not become a second apply gate. Normal deck configuration still starts with `hsconfig configure`, and `reports/operator_summary.json` remains the apply authority.
```

- [ ] **Step 5: Run docs tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_contract_spine_sentinel_docs.py tests/test_skill_files.py tests/test_operator_guidance.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 4**

```powershell
git add .agents/skills/hsconfig/SKILL.md docs/operator/README.md tests/test_contract_spine_sentinel_docs.py
git commit -m "docs: document contract spine sentinel boundary"
```

---

### Task 5: Final Verification And GitHub Update

**Files:**
- Verify only unless failures require a narrow fix.

**Interfaces:**
- Consumes:
  - all previous tasks
- Produces:
  - green focused suite
  - clean git status
  - pushed `main`

- [ ] **Step 1: Run focused sentinel suite**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_contract_spine_sentinel.py tests/test_contract_spine_sentinel_cli.py tests/test_contract_spine_sentinel_docs.py -q
```

Expected: PASS.

- [ ] **Step 2: Run source-contract and apply-boundary suite**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_source_contract_conformance.py tests/test_source_contract_spine_freeze.py tests/test_source_contract_audit.py tests/test_source_to_runtime_explainability.py tests/test_no_second_gate_contract.py tests/test_apply_authority_boundary.py tests/test_apply_gate.py -q
```

Expected: PASS.

- [ ] **Step 3: Run CLI/docs sanity suite**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_cli_help.py tests/test_skill_files.py tests/test_operator_guidance.py -q
```

Expected: PASS.

- [ ] **Step 4: Run the new command manually**

Run:

```powershell
$env:PYTHONPATH='src'; python -m hsconfig contract-spine-sentinel --json
```

Expected JSON properties:

```json
{
  "status": "clean",
  "operator_gate_impact": "diagnostic_only",
  "apply_blocking": false,
  "problems": []
}
```

- [ ] **Step 5: Check git status**

Run:

```powershell
git status --short --branch
```

Expected: clean working tree on `main`.

- [ ] **Step 6: Push**

Run:

```powershell
git push origin main
```

Expected: `main -> main` or `Everything up-to-date`.

---

## Self-Review

- Spec coverage: The plan covers the recommended Contract-Spine Sentinel, no-second-gate protection, Darkbishop/start-of-game boundary, apply-authority boundary, CLI visibility, docs, and verification.
- Placeholder scan: No placeholder markers, unspecified tests, or deferred error handling remain.
- Type consistency: The produced interface is consistently `build_contract_spine_sentinel_report(repo_root: str | Path | None = None) -> dict[str, object]`; CLI command name is consistently `contract-spine-sentinel`.
- Scope check: The plan does not add runtime surfaces, does not broaden normal apply, and does not change deck-building behavior.

Plan complete and saved to `docs/superpowers/plans/2026-07-13-contract-spine-sentinel.md`. Two execution options:

1. Subagent-Driven (recommended) - dispatch a fresh subagent per task, review between tasks, fast iteration.
2. Inline Execution - execute tasks in this session using executing-plans, batch execution with checkpoints.

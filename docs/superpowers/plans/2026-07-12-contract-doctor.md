# Contract Doctor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a read-only `hsconfig contract-doctor` command that explains the existing source -> claim_kind -> surface gate -> builder/router -> runtime effect chain for a prepared package without creating a second apply gate.

**Architecture:** Reuse existing `reports/operator_summary.json`, `reports/source_contract_audit.json`, and the deck-neutral `source_contract_conformance` snapshot. The command produces a compact JSON/Markdown diagnostic that names the first missing link per claim/card and explicitly states that `operator_summary.json` remains the only normal apply authority.

**Tech Stack:** Python 3, argparse CLI, existing HSConfig report JSON files, pytest.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig`.
- Do not change runtime apply behavior.
- Do not make `source_contract_audit.json`, `contract_spine_rows`, or `claim_lifecycle_rows` an apply authority.
- `reports/operator_summary.json` remains the only normal runtime-write/apply authority.
- The doctor is read-only. It must never write HearthRanger runtime files.
- Unknown or weak source evidence remains non-blocking; the command explains it.
- Preserve the Darkbishop boundary: `hero_power_transform` may lower to CardID behavior, but does not become `mulligan_keep`.

---

## File Structure

- Create `src/hsconfig/contract_doctor.py`
  - Pure read/compose logic.
  - Public interface: `build_contract_doctor_report(package: Path) -> dict[str, Any]` and `render_contract_doctor_markdown(report: Mapping[str, Any]) -> str`.
- Create `src/hsconfig/commands/contract_doctor.py`
  - CLI payload wrapper using existing `run_payload_command` style.
- Modify `src/hsconfig/cli_parser.py`
  - Add `contract-doctor --package --out --json`.
- Modify `src/hsconfig/cli.py`
  - Dispatch `contract-doctor`.
- Create `tests/test_contract_doctor.py`
  - Unit and fixture tests for package report reading, missing files, no apply authority, and Darkbishop boundary visibility.
- Modify `tests/test_cli.py`
  - Add dispatch/shape test for `contract-doctor`.
- Modify `docs/operator/README.md`
  - Add a short diagnostic-only note.
- Modify `.agents/skills/hsconfig/SKILL.md`
  - Add one line naming `contract-doctor` as optional diagnostics, after `operator_summary.json`.
- Modify `tests/test_skill_files.py`
  - Guard docs/skill wording.

---

### Task 1: Contract Doctor Core

**Files:**
- Create: `src/hsconfig/contract_doctor.py`
- Test: `tests/test_contract_doctor.py`

**Interfaces:**
- Consumes: `package / "reports" / "operator_summary.json"`, optional `source_contract_audit.json`, optional conformance snapshot from `build_source_contract_conformance_snapshot()`.
- Produces:
  - `build_contract_doctor_report(package: Path) -> dict[str, Any]`
  - `render_contract_doctor_markdown(report: Mapping[str, Any]) -> str`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_contract_doctor.py`:

```python
import json
from pathlib import Path

from hsconfig.contract_doctor import (
    build_contract_doctor_report,
    render_contract_doctor_markdown,
)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_contract_doctor_summarizes_operator_and_audit_without_gate(tmp_path: Path):
    package = tmp_path / "package"
    reports = package / "reports"
    write_json(
        reports / "operator_summary.json",
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "SOURCE_BACKED_STRONG",
            "source_contract_audit_summary": {
                "non_blocking": True,
                "next_report_to_open": "reports/source_contract_audit.json",
                "runtime_lowered_claims": 2,
            },
        },
    )
    write_json(
        reports / "source_contract_audit.json",
        {
            "schema_version": 1,
            "summary": {
                "claims_total": 3,
                "runtime_lowered_claims": 2,
                "suppressed_claims": 1,
                "runtime_evidence_required_claims": 0,
            },
            "claim_lifecycle_rows": [
                {
                    "claim_id": "claim_1",
                    "claim_kind": "mulligan_keep",
                    "policy_lane": "runtime_lowerable",
                    "surface_gate_decision": "allowed",
                    "surface_gate_reason": "runtime_surface_claim",
                    "builder_or_router_decision": "emitted",
                    "runtime_surface": "mulligan",
                    "first_missing_link": "none",
                },
                {
                    "claim_id": "claim_2",
                    "claim_kind": "globalvalue_numeric_tuning",
                    "policy_lane": "runtime_evidence_required",
                    "surface_gate_decision": "rejected",
                    "surface_gate_reason": "runtime_evidence_required",
                    "builder_or_router_decision": "suppressed",
                    "runtime_surface": "none",
                    "first_missing_link": "runtime_evidence_required",
                },
            ],
            "card_rows": {},
        },
    )

    report = build_contract_doctor_report(package)

    assert report["status"] == "ok"
    assert report["authority"]["apply_authority"] == "reports/operator_summary.json"
    assert report["authority"]["diagnostic_only"] is True
    assert report["operator"]["technical_status"] == "VALID_PACKAGE"
    assert report["claim_lifecycle"]["total"] == 2
    assert report["claim_lifecycle"]["first_missing_links"]["runtime_evidence_required"] == 1
    assert "apply_allowed" not in json.dumps(report)


def test_contract_doctor_fails_when_operator_summary_is_missing(tmp_path: Path):
    report = build_contract_doctor_report(tmp_path / "missing-package")

    assert report["status"] == "failed"
    assert report["errors"] == ["missing reports/operator_summary.json"]
    assert report["authority"]["apply_authority"] == "reports/operator_summary.json"
    assert report["authority"]["diagnostic_only"] is True


def test_contract_doctor_markdown_states_diagnostic_only(tmp_path: Path):
    package = tmp_path / "package"
    write_json(
        package / "reports" / "operator_summary.json",
        {"technical_status": "VALID_PACKAGE", "semantic_status": "STATIC_SEMANTICS_USABLE"},
    )

    markdown = render_contract_doctor_markdown(build_contract_doctor_report(package))

    assert "Diagnostic only" in markdown
    assert "operator_summary.json remains the only normal apply authority" in markdown
```

- [ ] **Step 2: Run tests and confirm failure**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_contract_doctor.py -q
```

Expected: import failure for `hsconfig.contract_doctor`.

- [ ] **Step 3: Implement the core module**

Create `src/hsconfig/contract_doctor.py` with:

```python
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

from hsconfig.source_contract_conformance import build_source_contract_conformance_snapshot


def build_contract_doctor_report(package: Path) -> dict[str, Any]:
    """Build a read-only source-contract diagnostic for a prepared package."""
    package = Path(package)
    operator_path = package / "reports" / "operator_summary.json"
    authority = {
        "apply_authority": "reports/operator_summary.json",
        "diagnostic_only": True,
        "runtime_write_performed": False,
        "note": "contract-doctor explains existing reports; it does not grant apply permission",
    }
    if not operator_path.is_file():
        return {
            "schema_version": 1,
            "status": "failed",
            "errors": ["missing reports/operator_summary.json"],
            "package": str(package),
            "authority": authority,
        }

    operator = _read_json(operator_path)
    if not isinstance(operator, Mapping):
        return {
            "schema_version": 1,
            "status": "failed",
            "errors": ["invalid reports/operator_summary.json"],
            "package": str(package),
            "authority": authority,
        }

    audit_path = package / "reports" / "source_contract_audit.json"
    audit = _read_json(audit_path) if audit_path.is_file() else {}
    if not isinstance(audit, Mapping):
        audit = {}

    lifecycle_rows = audit.get("claim_lifecycle_rows", [])
    if not isinstance(lifecycle_rows, list):
        lifecycle_rows = []
    missing_links = Counter(
        str(row.get("first_missing_link", "unknown"))
        for row in lifecycle_rows
        if isinstance(row, Mapping)
    )
    runtime_surfaces = Counter(
        str(row.get("runtime_surface", "none"))
        for row in lifecycle_rows
        if isinstance(row, Mapping)
    )

    conformance = build_source_contract_conformance_snapshot()
    summary = conformance.get("summary", {}) if isinstance(conformance, Mapping) else {}

    return {
        "schema_version": 1,
        "status": "ok",
        "errors": [],
        "package": str(package),
        "authority": authority,
        "operator": {
            "technical_status": operator.get("technical_status"),
            "semantic_status": operator.get("semantic_status"),
            "first_report_to_open": "reports/operator_summary.json",
        },
        "source_contract_audit": {
            "present": bool(audit),
            "summary": audit.get("summary", {}),
            "next_report_to_open": "reports/source_contract_audit.json" if audit else None,
        },
        "claim_lifecycle": {
            "total": len(lifecycle_rows),
            "first_missing_links": dict(sorted(missing_links.items())),
            "runtime_surfaces": dict(sorted(runtime_surfaces.items())),
        },
        "conformance": {
            "operator_gate_impact": conformance.get("operator_gate_impact"),
            "unexpected_contract_drift_count": summary.get("unexpected_contract_drift_count"),
            "builder_prerequisite_gap_count": summary.get("builder_prerequisite_gap_count"),
            "pipeline_attention_count": summary.get("pipeline_attention_count"),
        },
    }


def render_contract_doctor_markdown(report: Mapping[str, Any]) -> str:
    """Render the contract-doctor result as compact operator-readable Markdown."""
    authority = report.get("authority", {})
    operator = report.get("operator", {})
    lifecycle = report.get("claim_lifecycle", {})
    conformance = report.get("conformance", {})
    lines = [
        "# Contract Doctor",
        "",
        "Diagnostic only. operator_summary.json remains the only normal apply authority.",
        "",
        "## Status",
        "",
        f"- Status: {report.get('status', '')}",
        f"- Package: {report.get('package', '')}",
        f"- Apply authority: {authority.get('apply_authority', '')}",
        f"- Runtime write performed: {authority.get('runtime_write_performed', False)}",
        "",
        "## Operator Summary",
        "",
        f"- Technical status: {operator.get('technical_status', '')}",
        f"- Semantic status: {operator.get('semantic_status', '')}",
        "",
        "## Claim Lifecycle",
        "",
        f"- Rows: {lifecycle.get('total', 0)}",
        f"- First missing links: {lifecycle.get('first_missing_links', {})}",
        f"- Runtime surfaces: {lifecycle.get('runtime_surfaces', {})}",
        "",
        "## Conformance",
        "",
        f"- Operator gate impact: {conformance.get('operator_gate_impact', '')}",
        f"- Unexpected contract drift: {conformance.get('unexpected_contract_drift_count', '')}",
        f"- Builder prerequisite gaps: {conformance.get('builder_prerequisite_gap_count', '')}",
    ]
    return "\n".join(lines)


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
```

- [ ] **Step 4: Run tests and confirm pass**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_contract_doctor.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit task**

```powershell
git add src/hsconfig/contract_doctor.py tests/test_contract_doctor.py
git commit -m "feat: add contract doctor diagnostics"
```

---

### Task 2: CLI Command

**Files:**
- Create: `src/hsconfig/commands/contract_doctor.py`
- Modify: `src/hsconfig/cli_parser.py`
- Modify: `src/hsconfig/cli.py`
- Test: `tests/test_cli.py`
- Test: `tests/test_contract_doctor.py`

**Interfaces:**
- Consumes: `build_contract_doctor_report(package: Path)`.
- Produces: CLI command `hsconfig contract-doctor --package <dir> [--out report.md] [--json]`.

- [ ] **Step 1: Write failing CLI tests**

Append to `tests/test_cli.py`:

```python
def test_cli_main_dispatches_contract_doctor_without_apply_authority(tmp_path: Path, monkeypatch):
    package = tmp_path / "package"
    package.mkdir()
    captured = {}

    def fake_run_contract_doctor_command(args):
        captured["package"] = args.package
        captured["out"] = args.out
        captured["json"] = args.json
        return 0

    monkeypatch.setattr(
        "hsconfig.cli.run_contract_doctor_command",
        fake_run_contract_doctor_command,
    )

    assert main(["contract-doctor", "--package", str(package), "--json"]) == 0
    assert captured == {"package": str(package), "out": None, "json": True}
```

Append to `tests/test_contract_doctor.py`:

```python
from argparse import Namespace

from hsconfig.commands.contract_doctor import contract_doctor_payload


def test_contract_doctor_payload_can_write_markdown_report(tmp_path: Path):
    package = tmp_path / "package"
    out = tmp_path / "doctor.md"
    write_json(
        package / "reports" / "operator_summary.json",
        {"technical_status": "VALID_PACKAGE", "semantic_status": "STATIC_SEMANTICS_USABLE"},
    )

    payload, code = contract_doctor_payload(
        Namespace(package=str(package), out=str(out), json=False)
    )

    assert code == 0
    assert payload["status"] == "ok"
    assert out.is_file()
    assert "Diagnostic only" in out.read_text(encoding="utf-8")
```

- [ ] **Step 2: Run tests and confirm failure**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_cli.py::test_cli_main_dispatches_contract_doctor_without_apply_authority tests/test_contract_doctor.py::test_contract_doctor_payload_can_write_markdown_report -q
```

Expected: import/attribute failure for the missing command.

- [ ] **Step 3: Implement command wrapper**

Create `src/hsconfig/commands/contract_doctor.py`:

```python
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from hsconfig.commands.common import run_payload_command
from hsconfig.contract_doctor import (
    build_contract_doctor_report,
    render_contract_doctor_markdown,
)


def run_contract_doctor_command(args: argparse.Namespace) -> int:
    return run_payload_command(args, contract_doctor_payload)


def contract_doctor_payload(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    report = build_contract_doctor_report(Path(args.package))
    if getattr(args, "out", None):
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(render_contract_doctor_markdown(report), encoding="utf-8")
        report = {**report, "written_report": str(out)}
    return report, 0 if report.get("status") == "ok" else 1
```

- [ ] **Step 4: Wire parser and dispatcher**

In `src/hsconfig/cli_parser.py`, add before `validate = subparsers.add_parser("validate")`:

```python
    contract_doctor = subparsers.add_parser(
        "contract-doctor",
        help="read-only source-contract diagnostic for prepared packages",
        description=(
            "Read a prepared package and explain source -> claim_kind -> surface "
            "gate -> builder/router -> runtime effect diagnostics. This command "
            "does not grant apply permission and never writes runtime files."
        ),
    )
    contract_doctor.add_argument("--package", required=True)
    contract_doctor.add_argument("--out", help="Optional Markdown output path.")
    contract_doctor.add_argument("--json", action="store_true")
```

In `src/hsconfig/cli.py`, add import:

```python
from hsconfig.commands.contract_doctor import run_contract_doctor_command
```

Add dispatch before `validate`:

```python
    if args.command == "contract-doctor":
        return run_contract_doctor_command(args)
```

- [ ] **Step 5: Run CLI tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_cli.py::test_cli_main_dispatches_contract_doctor_without_apply_authority tests/test_contract_doctor.py -q
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit task**

```powershell
git add src/hsconfig/commands/contract_doctor.py src/hsconfig/cli_parser.py src/hsconfig/cli.py tests/test_cli.py tests/test_contract_doctor.py
git commit -m "feat: expose contract doctor command"
```

---

### Task 3: Docs And Skill Surface

**Files:**
- Modify: `docs/operator/README.md`
- Modify: `.agents/skills/hsconfig/SKILL.md`
- Modify: `.agents/skills/hsconfig/references/workflow.md`
- Test: `tests/test_skill_files.py`

**Interfaces:**
- Consumes: CLI command from Task 2.
- Produces: One documented optional diagnostic path.

- [ ] **Step 1: Write failing docs test**

Append to `tests/test_skill_files.py`:

```python
def test_docs_and_skill_describe_contract_doctor_as_diagnostic_only():
    operator = Path("docs/operator/README.md").read_text(encoding="utf-8")
    skill = Path(".agents/skills/hsconfig/SKILL.md").read_text(encoding="utf-8")
    workflow = Path(".agents/skills/hsconfig/references/workflow.md").read_text(
        encoding="utf-8"
    )
    combined = "\n".join([operator, skill, workflow])

    assert "hsconfig contract-doctor" in combined
    assert "diagnostic" in combined.lower()
    assert "operator_summary.json remains the only normal apply authority" in combined
    assert "contract-doctor is an apply gate" not in combined
```

- [ ] **Step 2: Run test and confirm failure**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_skill_files.py::test_docs_and_skill_describe_contract_doctor_as_diagnostic_only -q
```

Expected: missing text assertion failure.

- [ ] **Step 3: Update operator docs**

Add a short section near the existing source-contract audit explanation in `docs/operator/README.md`:

```markdown
### Optional contract doctor

Use `hsconfig contract-doctor --package <package> --json` when a prepared package
is valid but you want a compact explanation of source -> claim_kind -> surface
gate -> builder/router -> runtime effect diagnostics. This is read-only and
diagnostic. `operator_summary.json` remains the only normal apply authority.
```

- [ ] **Step 4: Update skill docs**

Add one bullet to `.agents/skills/hsconfig/SKILL.md` near the source-contract invariant section:

```markdown
- Optional diagnostic: `hsconfig contract-doctor --package <package> --json`
  summarizes source-contract lifecycle rows and first missing links. It is
  read-only; operator_summary.json remains the only normal apply authority.
```

Add one sentence to `.agents/skills/hsconfig/references/workflow.md`:

```markdown
`hsconfig contract-doctor --package <package> --json` is optional diagnostics for
the source-contract chain. It is not an apply gate; operator_summary.json remains
the only normal apply authority.
```

- [ ] **Step 5: Run docs test**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_skill_files.py::test_docs_and_skill_describe_contract_doctor_as_diagnostic_only -q
```

Expected: pass.

- [ ] **Step 6: Commit task**

```powershell
git add docs/operator/README.md .agents/skills/hsconfig/SKILL.md .agents/skills/hsconfig/references/workflow.md tests/test_skill_files.py
git commit -m "docs: document contract doctor diagnostics"
```

---

### Task 4: End-To-End Guardrails And Verification

**Files:**
- Modify if needed: `tests/test_contract_doctor.py`
- No production changes unless tests expose a defect.

**Interfaces:**
- Consumes: Tasks 1-3.
- Produces: verified no-second-gate behavior.

- [ ] **Step 1: Add boundary regression tests**

Add to `tests/test_contract_doctor.py`:

```python
def test_contract_doctor_keeps_darkbishop_boundary_visible(tmp_path: Path):
    package = tmp_path / "shadowpriest"
    write_json(
        package / "reports" / "operator_summary.json",
        {"technical_status": "VALID_PACKAGE", "semantic_status": "SOURCE_BACKED_STRONG"},
    )
    write_json(
        package / "reports" / "source_contract_audit.json",
        {
            "summary": {"claims_total": 1, "runtime_lowered_claims": 1},
            "claim_lifecycle_rows": [
                {
                    "claim_id": "darkbishop_effect",
                    "claim_kind": "hero_power_transform",
                    "policy_lane": "suppressed_or_conditional",
                    "surface_gate_decision": "allowed",
                    "surface_gate_reason": "cardid_behavior_surface",
                    "builder_or_router_decision": "emitted",
                    "runtime_surface": "cardid",
                    "first_missing_link": "none",
                }
            ],
            "card_rows": {
                "SW_448": {
                    "runtime_surfaces": ["cardid"],
                    "claim_lanes": {"runtime_lowered": 1},
                    "first_missing_link": "none",
                }
            },
        },
    )

    report = build_contract_doctor_report(package)

    assert report["claim_lifecycle"]["runtime_surfaces"]["cardid"] == 1
    assert "mulligan" not in report["claim_lifecycle"]["runtime_surfaces"]
    assert report["authority"]["diagnostic_only"] is True
```

- [ ] **Step 2: Run focused guardrail suite**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_contract_doctor.py tests/test_source_contract_conformance.py tests/test_source_contract_audit.py tests/test_apply_authority_boundary.py tests/test_semantic_runtime_negative_boundaries.py tests/test_skill_files.py -q
```

Expected: all pass.

- [ ] **Step 3: Run CLI smoke**

Run against any existing generated package fixture if present, otherwise use a temp package from tests:

```powershell
$env:PYTHONPATH='src'; python -m hsconfig.cli contract-doctor --package outputs/ShadowPriest/04_package --json
```

Expected when package exists: JSON with `status=ok`, `authority.diagnostic_only=true`, and `authority.apply_authority=reports/operator_summary.json`.

Expected when package does not exist: documented failure with `missing reports/operator_summary.json`.

- [ ] **Step 4: Run broad tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest -q
```

Expected: full suite passes.

- [ ] **Step 5: Final git check**

Run:

```powershell
git status --short --branch
```

Expected: branch ahead only by the planned commits, no untracked temp files.

- [ ] **Step 6: Commit any final test-only adjustments**

Only if Step 2-4 required extra changes:

```powershell
git add tests/test_contract_doctor.py
git commit -m "test: guard contract doctor authority boundaries"
```

---

## Self-Review

- Spec coverage: The plan implements the recommended small `contract-doctor` only. It does not change source inference, runtime apply, package building, or HearthRanger runtime writes.
- Authority boundary: Every task repeats that `operator_summary.json` remains the only normal apply authority.
- Darkbishop boundary: Task 4 explicitly verifies `hero_power_transform` stays CardID/effect-side and does not become Mulligan.
- No-block behavior: Missing audit is handled as diagnostic absence, while missing `operator_summary.json` returns a read-only failed report.
- Placeholder scan: No task uses TBD/TODO/fill-later wording.
- Type consistency: Public functions are `build_contract_doctor_report(package: Path) -> dict[str, Any]` and `render_contract_doctor_markdown(report: Mapping[str, Any]) -> str`.

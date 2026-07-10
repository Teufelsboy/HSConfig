# HSConfig Main Sync And Acceptance Matrix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the verified HSConfig no-block branch the official `main` state, then add a small read-only acceptance matrix so any-deck load-safety is visible without adding post-run tuning scope.

**Architecture:** First fast-forward `main` to the already verified `codex/hsconfig-mechanic-lowering-parity` branch. Then add one focused read-only matrix builder that summarizes existing prepared packages by reading `reports/operator_summary.json` and `CustomConfig` files; expose it through a narrow CLI command and document it as an optional audit surface, not an apply gate.

**Tech Stack:** Python 3, stdlib `argparse`/`json`/`pathlib`, existing HSConfig CLI command pattern, pytest, Git/GitHub.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig` for `Teufelsboy/HSConfig`.
- Keep HSConfig separate from HSTuner.
- Do not add replay parsing, HDT parsing, winrate validation, candidate promotion, or post-run tuning.
- Generated runtime packages stay under `outputs/` and remain ignored by git.
- Preserve exact deck and CardID identity.
- Preserve full `GlobalValues.json` key profiling.
- Preserve every-card gameplan contract coverage.
- Preserve strict JSON validation.
- Preserve row-level provenance for generated config rows.
- `reports/operator_summary.json` remains the single operator gate.
- The new acceptance matrix is read-only diagnostics. It must not grant apply permission, mutate runtime files, or create a second gate.
- Valid packages with semantic warnings remain visible but non-blocking.

---

## File Structure

- Modify: `src/hsconfig/cli.py`
  - Dispatch the new `acceptance-matrix` command to the command module.
- Modify: `src/hsconfig/cli_parser.py`
  - Register the new read-only command and arguments.
- Create: `src/hsconfig/acceptance_matrix.py`
  - Build a compact matrix from one or more already prepared package directories.
- Create: `src/hsconfig/commands/acceptance_matrix.py`
  - CLI wrapper around the matrix builder.
- Create: `tests/test_acceptance_matrix.py`
  - Unit and CLI tests for matrix output.
- Modify: `docs/operator/README.md`
  - Add the optional matrix command as an audit view after normal package creation.
- Modify: `docs/operator/universal-wild-no-block-contract.md`
  - State that the matrix summarizes the no-block proof but does not change the gate.
- Modify: `README.md`
  - Add a short pointer only if the current root README already lists operator commands.

---

### Task 1: Promote Verified Branch To Main

**Files:**
- Modify: none
- Test: existing focused test suite

**Interfaces:**
- Consumes: current branch `codex/hsconfig-mechanic-lowering-parity`
- Produces: `main` fast-forwarded to the verified no-block branch and pushed to `origin/main`

- [ ] **Step 1: Confirm the starting branch and clean state**

Run:

```powershell
git status --short --branch
git log -3 --oneline --decorate
```

Expected:

```text
## codex/hsconfig-mechanic-lowering-parity
cba0348 ... chore: trim hsconfig plan whitespace
d618534 ... chore: stabilize hsconfig no-block mechanic path
5ba2874 ... docs: plan discolock sharp hsconfig run
```

- [ ] **Step 2: Verify the focused no-block suite before promotion**

Run:

```powershell
python -m pytest tests/test_universal_wild_no_block_matrix.py tests/test_mechanic_support.py tests/test_mechanic_drift.py tests/test_scope_boundaries.py tests/test_skill_sync.py -q
```

Expected:

```text
42 passed
```

- [ ] **Step 3: Fast-forward main**

Run:

```powershell
git fetch origin
git checkout main
git merge --ff-only codex/hsconfig-mechanic-lowering-parity
```

Expected:

```text
Updating 5ba2874..cba0348
Fast-forward
```

- [ ] **Step 4: Re-run focused verification on main**

Run:

```powershell
python -m pytest tests/test_universal_wild_no_block_matrix.py tests/test_mechanic_support.py tests/test_mechanic_drift.py tests/test_scope_boundaries.py tests/test_skill_sync.py -q
```

Expected:

```text
42 passed
```

- [ ] **Step 5: Push main**

Run:

```powershell
git push origin main
```

Expected:

```text
main -> main
```

- [ ] **Step 6: Create the implementation branch for the acceptance matrix**

Run:

```powershell
git checkout -b codex/hsconfig-acceptance-matrix
```

Expected:

```text
Switched to a new branch 'codex/hsconfig-acceptance-matrix'
```

---

### Task 2: Add Read-Only Acceptance Matrix Builder

**Files:**
- Create: `src/hsconfig/acceptance_matrix.py`
- Create: `tests/test_acceptance_matrix.py`

**Interfaces:**
- Consumes: `build_acceptance_matrix(package_paths: Sequence[str | Path]) -> dict[str, Any]`
- Produces: acceptance matrix payload with `schema_version`, `status`, `summary`, and `packages`

- [ ] **Step 1: Write the failing unit test**

Create `tests/test_acceptance_matrix.py` with this initial content:

```python
from __future__ import annotations

import json
from pathlib import Path

from hsconfig.acceptance_matrix import build_acceptance_matrix
from hsconfig.cli import main


SHADOWPRIEST_CODE = (
    "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/"
    "KgG17oG1cEGAAA="
)
BIGSHAMAN_CODE = (
    "AAEBAaoIBpQD5LcDv84E9qMGgbgGmvYGDM4P0hP2vQKPlAPW9QO8tgT08gXqmAbGpgakpwb44gas/QYAAA=="
)


def _prepare_package(tmp_path: Path, deck_name: str, deck_code: str) -> Path:
    out = tmp_path / deck_name
    assert main(
        [
            "prepare",
            "--deck-name",
            deck_name,
            "--deck-code",
            deck_code,
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(out),
            "--json",
        ]
    ) == 0
    return out


def test_build_acceptance_matrix_summarizes_load_safe_packages(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("hsconfig.package_builder.fetch_latest_cards", lambda timeout=10.0: [])

    shadow = _prepare_package(tmp_path, "ShadowPriest", SHADOWPRIEST_CODE)
    shaman = _prepare_package(tmp_path, "BigShaman", BIGSHAMAN_CODE)

    matrix = build_acceptance_matrix([shadow, shaman])

    assert matrix["schema_version"] == 1
    assert matrix["status"] == "passed"
    assert matrix["summary"]["package_count"] == 2
    assert matrix["summary"]["valid_package_count"] == 2
    assert matrix["summary"]["load_safe_apply_count"] == 2
    assert matrix["summary"]["technical_hard_block_count"] == 0
    assert {row["deck_name"] for row in matrix["packages"]} == {"ShadowPriest", "BigShaman"}
    for row in matrix["packages"]:
        assert row["technical_status"] == "VALID_PACKAGE"
        assert row["runtime_apply_mode"] == "load_safe_apply"
        assert row["runtime_apply_allowed"] is True
        assert row["has_globalvalues"] is True
        assert row["has_mulligan"] is True
        assert row["has_presume"] is False
        assert row["has_concede"] is False
        assert row["cardid_file_count"] > 0
        assert isinstance(row["warning_boundaries"], list)


def test_build_acceptance_matrix_reports_missing_operator_summary(tmp_path: Path):
    package = tmp_path / "broken-package"
    package.mkdir()

    matrix = build_acceptance_matrix([package])

    assert matrix["status"] == "failed"
    assert matrix["summary"]["package_count"] == 1
    assert matrix["summary"]["technical_hard_block_count"] == 1
    assert matrix["packages"][0]["inspection_status"] == "missing_operator_summary"
    assert matrix["packages"][0]["technical_status"] == "INVALID_PACKAGE"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest tests/test_acceptance_matrix.py -q
```

Expected:

```text
ModuleNotFoundError: No module named 'hsconfig.acceptance_matrix'
```

- [ ] **Step 3: Add the builder implementation**

Create `src/hsconfig/acceptance_matrix.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence


SPECIAL_RUNTIME_FILES = {
    "Combo.json",
    "GlobalValues.json",
    "Mulligan.json",
    "Presume.json",
    "Concede.json",
}


def build_acceptance_matrix(package_paths: Sequence[str | Path]) -> dict[str, Any]:
    rows = [_inspect_package(Path(package_path)) for package_path in package_paths]
    hard_block_count = sum(int(row.get("technical_hard_block_count", 0)) for row in rows)
    valid_count = sum(1 for row in rows if row.get("technical_status") == "VALID_PACKAGE")
    load_safe_count = sum(1 for row in rows if row.get("runtime_apply_mode") == "load_safe_apply")
    warning_count = sum(1 for row in rows if row.get("warning_boundary_count", 0) > 0)
    status = "passed" if hard_block_count == 0 and len(rows) == valid_count else "failed"
    return {
        "schema_version": 1,
        "status": status,
        "summary": {
            "package_count": len(rows),
            "valid_package_count": valid_count,
            "load_safe_apply_count": load_safe_count,
            "technical_hard_block_count": hard_block_count,
            "warning_package_count": warning_count,
        },
        "packages": rows,
    }


def _inspect_package(package: Path) -> dict[str, Any]:
    operator_path = package / "reports" / "operator_summary.json"
    if not operator_path.is_file():
        return _missing_operator_summary_row(package, operator_path)

    operator = _read_json(operator_path)
    deck_dir = _single_deck_dir(package / "CustomConfig")
    runtime_files = _runtime_files(deck_dir)
    warning_boundaries = _warning_boundaries(operator)
    no_block = operator.get("no_block_failure_mode_summary", {})
    categories = no_block.get("categories", {}) if isinstance(no_block, dict) else {}
    technical_hard_blocks = categories.get("technical_hard_block", [])
    if not isinstance(technical_hard_blocks, list):
        technical_hard_blocks = []

    return {
        "package": str(package),
        "inspection_status": "inspected",
        "deck_name": str(operator.get("deck", {}).get("name", "")),
        "technical_status": str(operator.get("technical_status", "")),
        "semantic_status": str(operator.get("semantic_status", "")),
        "next_action": str(operator.get("next_action", "")),
        "runtime_apply_mode": str(operator.get("runtime_apply_mode", "")),
        "runtime_apply_allowed": bool(operator.get("runtime_apply_allowed", False)),
        "technical_hard_block_count": len(technical_hard_blocks),
        "config_usefulness_status": str(
            operator.get("config_usefulness", {}).get("status", "")
        ),
        "first_warning_boundary": operator.get("mechanic_visibility_summary", {}).get(
            "first_warning_boundary"
        ),
        "warning_boundaries": warning_boundaries,
        "warning_boundary_count": len(warning_boundaries),
        "runtime_file_count": len(runtime_files),
        "cardid_file_count": _cardid_file_count(runtime_files),
        "has_globalvalues": "GlobalValues.json" in runtime_files,
        "has_mulligan": "Mulligan.json" in runtime_files,
        "has_combo": "Combo.json" in runtime_files,
        "has_presume": "Presume.json" in runtime_files,
        "has_concede": "Concede.json" in runtime_files,
    }


def _missing_operator_summary_row(package: Path, operator_path: Path) -> dict[str, Any]:
    return {
        "package": str(package),
        "inspection_status": "missing_operator_summary",
        "missing_path": str(operator_path),
        "deck_name": "",
        "technical_status": "INVALID_PACKAGE",
        "semantic_status": "INVALID_PACKAGE",
        "next_action": "FIX_PACKAGE_BEFORE_APPLY",
        "runtime_apply_mode": "blocked",
        "runtime_apply_allowed": False,
        "technical_hard_block_count": 1,
        "config_usefulness_status": "",
        "first_warning_boundary": None,
        "warning_boundaries": [],
        "warning_boundary_count": 0,
        "runtime_file_count": 0,
        "cardid_file_count": 0,
        "has_globalvalues": False,
        "has_mulligan": False,
        "has_combo": False,
        "has_presume": False,
        "has_concede": False,
    }


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _single_deck_dir(custom_config_root: Path) -> Path | None:
    if not custom_config_root.is_dir():
        return None
    deck_dirs = [path for path in custom_config_root.iterdir() if path.is_dir()]
    return deck_dirs[0] if len(deck_dirs) == 1 else None


def _runtime_files(deck_dir: Path | None) -> set[str]:
    if deck_dir is None:
        return set()
    return {path.name for path in deck_dir.glob("*.json")}


def _cardid_file_count(runtime_files: set[str]) -> int:
    return len([filename for filename in runtime_files if filename not in SPECIAL_RUNTIME_FILES])


def _warning_boundaries(operator: dict[str, Any]) -> list[str]:
    visibility = operator.get("mechanic_visibility_summary", {})
    if not isinstance(visibility, dict):
        return []
    boundaries = visibility.get("warning_boundaries", [])
    if not isinstance(boundaries, list):
        return []
    return [str(boundary) for boundary in boundaries]
```

- [ ] **Step 4: Run tests to verify builder passes**

Run:

```powershell
python -m pytest tests/test_acceptance_matrix.py -q
```

Expected:

```text
2 passed
```

- [ ] **Step 5: Commit builder**

Run:

```powershell
git add src/hsconfig/acceptance_matrix.py tests/test_acceptance_matrix.py
git commit -m "feat: add hsconfig acceptance matrix builder"
```

Expected:

```text
[codex/hsconfig-acceptance-matrix ...] feat: add hsconfig acceptance matrix builder
```

---

### Task 3: Expose Acceptance Matrix Through CLI

**Files:**
- Modify: `src/hsconfig/cli.py`
- Modify: `src/hsconfig/cli_parser.py`
- Create: `src/hsconfig/commands/acceptance_matrix.py`
- Modify: `tests/test_acceptance_matrix.py`

**Interfaces:**
- Consumes: `build_acceptance_matrix(package_paths)`
- Produces: `hsconfig acceptance-matrix --package <path> [--package <path>] --json`

- [ ] **Step 1: Add failing CLI test**

Append this test to `tests/test_acceptance_matrix.py`:

```python
def test_acceptance_matrix_cli_outputs_json_and_optional_file(tmp_path: Path, capsys, monkeypatch):
    monkeypatch.setattr("hsconfig.package_builder.fetch_latest_cards", lambda timeout=10.0: [])
    package = _prepare_package(tmp_path, "ShadowPriest", SHADOWPRIEST_CODE)
    out_file = tmp_path / "acceptance_matrix.json"

    code = main(
        [
            "acceptance-matrix",
            "--package",
            str(package),
            "--out",
            str(out_file),
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    written = json.loads(out_file.read_text(encoding="utf-8"))

    assert code == 0
    assert payload["status"] == "passed"
    assert payload == written
    assert payload["summary"]["package_count"] == 1
    assert payload["packages"][0]["deck_name"] == "ShadowPriest"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest tests/test_acceptance_matrix.py::test_acceptance_matrix_cli_outputs_json_and_optional_file -q
```

Expected:

```text
SystemExit: 2
```

- [ ] **Step 3: Add CLI parser entry**

Modify `src/hsconfig/cli_parser.py` immediately before the `validate = subparsers.add_parser("validate")` block:

```python
    acceptance_matrix = subparsers.add_parser(
        "acceptance-matrix",
        help="read-only package acceptance matrix",
        description=(
            "Read one or more prepared HSConfig packages and summarize load-safe "
            "status, runtime files, warning boundaries, and no-block hard stops. "
            "This command is diagnostic only and never writes runtime files."
        ),
    )
    acceptance_matrix.add_argument(
        "--package",
        action="append",
        required=True,
        help="Prepared package directory. Repeat for multiple packages.",
    )
    acceptance_matrix.add_argument("--out", help="Optional JSON output path.")
    acceptance_matrix.add_argument("--json", action="store_true")
```

- [ ] **Step 4: Add command wrapper**

Create `src/hsconfig/commands/acceptance_matrix.py`:

```python
from __future__ import annotations

import argparse
import json
from pathlib import Path

from hsconfig.acceptance_matrix import build_acceptance_matrix
from hsconfig.commands.common import emit_result


def run_acceptance_matrix_command(args: argparse.Namespace) -> int:
    payload = build_acceptance_matrix([Path(package) for package in args.package])
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    code = 0 if payload.get("status") == "passed" else 1
    return emit_result(payload, bool(getattr(args, "json", False)), code)
```

- [ ] **Step 5: Wire command dispatch**

Modify `src/hsconfig/cli.py` imports:

```python
from hsconfig.commands.acceptance_matrix import run_acceptance_matrix_command
```

Add this dispatch block before `if args.command == "apply":`:

```python
    if args.command == "acceptance-matrix":
        return run_acceptance_matrix_command(args)
```

- [ ] **Step 6: Run CLI test**

Run:

```powershell
python -m pytest tests/test_acceptance_matrix.py::test_acceptance_matrix_cli_outputs_json_and_optional_file -q
```

Expected:

```text
1 passed
```

- [ ] **Step 7: Run all acceptance matrix tests**

Run:

```powershell
python -m pytest tests/test_acceptance_matrix.py -q
```

Expected:

```text
3 passed
```

- [ ] **Step 8: Commit CLI integration**

Run:

```powershell
git add src/hsconfig/cli.py src/hsconfig/cli_parser.py src/hsconfig/commands/acceptance_matrix.py tests/test_acceptance_matrix.py
git commit -m "feat: expose hsconfig acceptance matrix cli"
```

Expected:

```text
[codex/hsconfig-acceptance-matrix ...] feat: expose hsconfig acceptance matrix cli
```

---

### Task 4: Document Optional Acceptance Matrix

**Files:**
- Modify: `docs/operator/README.md`
- Modify: `docs/operator/universal-wild-no-block-contract.md`
- Test: `tests/test_docs_active_path.py`

**Interfaces:**
- Consumes: CLI command `hsconfig acceptance-matrix`
- Produces: operator documentation that names the command as diagnostic-only

- [ ] **Step 1: Add failing docs test**

Append this test to `tests/test_docs_active_path.py`:

```python
def test_acceptance_matrix_is_documented_as_diagnostic_only():
    operator = Path("docs/operator/README.md").read_text(encoding="utf-8")
    contract = Path("docs/operator/universal-wild-no-block-contract.md").read_text(
        encoding="utf-8"
    )

    assert "hsconfig acceptance-matrix" in operator
    assert "diagnostic only" in operator
    assert "does not change the apply gate" in contract
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest tests/test_docs_active_path.py::test_acceptance_matrix_is_documented_as_diagnostic_only -q
```

Expected:

```text
FAILED
```

- [ ] **Step 3: Update operator README**

Add this section to `docs/operator/README.md` after the `## Report Ownership` table:

````markdown
## Optional Acceptance Matrix

Use `hsconfig acceptance-matrix` after one or more packages have already been
prepared when you want a compact read-only proof view.

```powershell
hsconfig acceptance-matrix --package outputs/ShadowPriest --package outputs/BigShaman --json
```

The matrix summarizes `technical_status`, `runtime_apply_mode`, runtime file
coverage, CardID file count, `config_usefulness`, and warning boundaries across
packages. It is diagnostic only. It does not write runtime files, does not parse
replays, and does not replace `reports/operator_summary.json` as the single
operator gate.
````

- [ ] **Step 4: Update no-block contract**

Add this paragraph to `docs/operator/universal-wild-no-block-contract.md` after the `## Proof Matrix` section:

```markdown
## Acceptance Matrix Diagnostic

`hsconfig acceptance-matrix` may summarize prepared packages across the proof
set. This command is a read-only diagnostic surface for package status,
runtime-file coverage, CardID file counts, and warning boundaries. It does not
change the apply gate. Runtime permission still comes only from
`reports/operator_summary.json` and the guarded `hsconfig apply` path.
```

- [ ] **Step 5: Run docs test**

Run:

```powershell
python -m pytest tests/test_docs_active_path.py::test_acceptance_matrix_is_documented_as_diagnostic_only -q
```

Expected:

```text
1 passed
```

- [ ] **Step 6: Commit docs**

Run:

```powershell
git add docs/operator/README.md docs/operator/universal-wild-no-block-contract.md tests/test_docs_active_path.py
git commit -m "docs: document hsconfig acceptance matrix"
```

Expected:

```text
[codex/hsconfig-acceptance-matrix ...] docs: document hsconfig acceptance matrix
```

---

### Task 5: Final Verification And GitHub Push

**Files:**
- Modify: none expected
- Test: full relevant verification

**Interfaces:**
- Consumes: completed acceptance matrix branch
- Produces: pushed implementation branch or merged `main`, depending on operator choice during execution

- [ ] **Step 1: Run focused acceptance tests**

Run:

```powershell
python -m pytest tests/test_acceptance_matrix.py tests/test_docs_active_path.py -q
```

Expected:

```text
passed
```

- [ ] **Step 2: Run no-block and scope suite**

Run:

```powershell
python -m pytest tests/test_universal_wild_no_block_matrix.py tests/test_mechanic_support.py tests/test_mechanic_drift.py tests/test_scope_boundaries.py tests/test_skill_sync.py -q
```

Expected:

```text
42 passed
```

- [ ] **Step 3: Run smoke integration suite**

Run:

```powershell
python -m pytest tests/test_full_chain_cli_integration.py tests/test_autonomous_guide_workflow_e2e.py tests/test_apply_gate.py -q
```

Expected:

```text
passed
```

- [ ] **Step 4: Inspect git diff**

Run:

```powershell
git status --short --branch
git diff --stat main...HEAD
```

Expected:

```text
## codex/hsconfig-acceptance-matrix
```

The diff contains only the acceptance matrix builder, command, tests, and docs.

- [ ] **Step 5: Push implementation branch**

Run:

```powershell
git push -u origin codex/hsconfig-acceptance-matrix
```

Expected:

```text
branch 'codex/hsconfig-acceptance-matrix' set up to track 'origin/codex/hsconfig-acceptance-matrix'
```

- [ ] **Step 6: Merge to main after review or direct approval**

If the user asks for direct main update after tests pass, run:

```powershell
git checkout main
git merge --ff-only codex/hsconfig-acceptance-matrix
git push origin main
```

Expected:

```text
Fast-forward
main -> main
```

---

## Self-Review

- Spec coverage: The plan implements the recommendation by first making the verified branch official, then adding only a small read-only acceptance matrix.
- Scope check: The plan does not add HSTuner, replay parsing, HDT parsing, winrate, candidate promotion, or after-game tuning.
- Gate check: `reports/operator_summary.json` remains the only apply gate. The new matrix is diagnostic-only.
- Test check: Each implementation task starts with a failing test and ends with targeted verification.
- Placeholder scan: No placeholder markers or unspecified implementation remains.
- Type consistency: `build_acceptance_matrix(package_paths: Sequence[str | Path]) -> dict[str, Any]` is the only new core interface and is used by the CLI wrapper.

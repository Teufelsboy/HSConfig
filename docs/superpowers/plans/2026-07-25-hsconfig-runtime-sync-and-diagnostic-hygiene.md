# HSConfig Runtime Sync And Diagnostic Hygiene Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the HSConfig package-to-runtime handoff provably synchronized after every guarded runtime apply, while keeping source/semantic diagnostics narrow, non-blocking, and easy to read. A generated package can only be reported as applied when the runtime deck folder semantically matches the validated package that was copied.

**Architecture:** Keep `reports/operator_summary.json` and `evaluate_apply_gate` as the only normal apply authority. Add one read-only semantic runtime match layer that compares the package `CustomConfig/<config_dir>` with the active runtime `CustomConfig/<config_dir>` after writes. Wire that report into apply receipts and `configure --apply` summaries. Then clean two diagnostic-only report surfaces: source-to-runtime explainability should not promote a claim-level "not seen by builder" row into a card-level gap when the card is already emitted, and `global_values_key_profile_report.json` should expose an explicit status/summary for full-key baseline profiles.

**Tech Stack:** Python, pytest, existing HSConfig CLI, existing runtime apply receipt model, existing package validation, existing operator summary/apply gate, existing JSON IO helpers.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig`.
- Do not create a shadow checkout, temp clone, or backup workspace.
- Keep the git worktree clean after the implementation is either committed or intentionally left ready for review.
- Before code changes, run:

```powershell
git fetch --all --prune --tags
python scripts/check_hsconfig_currentness.py --cwd . --json
git status --short --branch
```

- Runtime writes remain allowed only through:
  - `python -m hsconfig.cli apply --package <package> --runtime-root <runtime-root>`
  - `python -m hsconfig.cli configure --deck-name <deck-name> --deck-code <deck-code> --out <package> --runtime-root <runtime-root> --apply`
- Do not introduce a new semantic/source apply gate.
- `SOURCE_BACKED_STRONG` remains an evidence label, not a runtime write requirement.
- `config_usefulness`, `source_to_runtime_explainability`, GlobalValues profile richness, and runtime-match diagnostics must not grant apply permission.
- A post-copy runtime mismatch is a technical write failure because the requested package was not installed as validated. It must rollback through the existing apply rollback boundary.
- Keep normal runtime output surfaces limited to:
  - `GlobalValues.json`
  - `Mulligan.json`
  - per-card `<CARDID>.json`
  - `Combo.json` only when exact combo evidence exists
- Do not emit `Presume.json`, `Concede.json`, or aggregate `CardBehavior.json`.
- Preserve Darkbishop Benedictus as an effect/setup boundary, not a Mulligan keep rule unless explicit source text supports keeping the physical card.

---

## Task 1: Add A Read-Only Runtime Package Match Model

**Files**

- Create: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\runtime_package_match.py`
- Create: `C:\Users\darbo\Documents\HSConfig\tests\test_runtime_package_match.py`

**Intent**

Build a deterministic JSON-semantic comparator for package vs runtime deck config folders. This is not a source-strength checker and not an apply gate. It answers one operational question: "Does the active runtime folder now contain the same generated config package?"

**Public API**

Implement this module:

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


class RuntimePackageMismatchError(RuntimeError):
    def __init__(self, report: dict[str, Any]) -> None:
        self.report = report
        super().__init__(_format_mismatch_message(report))


def assert_runtime_matches_package(
    *,
    package_root: str | Path,
    runtime_root: str | Path,
    config_dir: str | None = None,
) -> dict[str, Any]:
    report = build_runtime_package_match_report(
        package_root=package_root,
        runtime_root=runtime_root,
        config_dir=config_dir,
    )
    if report["status"] != "matched":
        raise RuntimePackageMismatchError(report)
    return report
```

Add `build_runtime_package_match_report` above `assert_runtime_matches_package` with this exact signature:

```python
def build_runtime_package_match_report(
    *,
    package_root: str | Path,
    runtime_root: str | Path,
    config_dir: str | None = None,
) -> dict[str, Any]:
```

The body is defined by the resolution, comparison, and report-shape rules below.

**Resolution Rules**

- `config_dir` resolution order:
  1. Explicit `config_dir`.
  2. Existing single package config directory under `package_root / "CustomConfig"`.
  3. Error if there are zero or multiple package config directories.
- Package deck dir: `package_root / "CustomConfig" / config_dir`.
- Runtime deck dir: `runtime_root / "CustomConfig" / config_dir`.
- Deck mapping file: `runtime_root / "CustomConfig" / "deck_config.ini"`.
- Read JSON via existing `hsconfig.io.read_json` if it supports BOM-safe parsing. If it does not, add a private helper using `encoding="utf-8-sig"`.
- Compare JSON values after parsing, not raw bytes.
- Include only `.json` files from the deck config folder. Ignore `deck_config.ini`, `hsconfig_write_history.jsonl`, fake receipts, and package reports.

**Report Shape**

Return this exact shape:

```python
{
    "schema_version": 1,
    "status": "matched" | "mismatch",
    "runtime_write_performed": False,
    "runtime_permission_impact": "none",
    "package_root": str(package),
    "runtime_root": str(runtime),
    "config_dir": config_dir,
    "package_config_path": str(package_dir),
    "runtime_config_path": str(runtime_dir),
    "package_config_exists": True | False,
    "runtime_config_exists": True | False,
    "package_file_count": 0,
    "runtime_file_count": 0,
    "missing_in_runtime": [],
    "extra_in_runtime": [],
    "semantic_mismatch_count": 0,
    "semantic_mismatches": [
        {
            "file": "NX2_019.json",
            "missing_keys_in_runtime": ["BeforeBattlecryTargetBonus"],
            "extra_keys_in_runtime": [],
            "changed_common_keys": [],
        }
    ],
    "deck_config_ini": {
        "path": str(deck_config_ini),
        "exists": True | False,
        "mentions_config_dir": True | False,
        "matched_lines": [],
    },
}
```

Notes:

- `semantic_mismatches` should be sorted by file name.
- For JSON objects, compare top-level keys and then compare common key values.
- For non-object JSON roots, put `"__root__"` into `changed_common_keys` when the values differ.
- `deck_config_ini.mentions_config_dir` is diagnostic only. A missing or stale line must set `status="mismatch"` after apply, because the active mapping would not point at the installed config.

**Tests**

Add these tests:

```python
from pathlib import Path

import pytest

from hsconfig.io import write_json
from hsconfig.runtime_package_match import (
    RuntimePackageMismatchError,
    assert_runtime_matches_package,
    build_runtime_package_match_report,
)


def _write_deck(root: Path, config_dir: str, files: dict[str, dict]) -> None:
    target = root / "CustomConfig" / config_dir
    target.mkdir(parents=True)
    for name, payload in files.items():
        write_json(target / name, payload)


def test_runtime_package_match_accepts_semantically_equal_json(tmp_path: Path):
    package = tmp_path / "package"
    runtime = tmp_path / "runtime"
    files = {
        "GlobalValues.json": {"GameCardId": "GlobalValues", "Face": {"values": [{"condition": "*", "value": "1"}]}},
        "Mulligan.json": {"Mulligan": {"values": []}},
        "NX2_019.json": {"GameCardId": "NX2_019", "BeforeBattlecryTargetBonus": {"values": []}},
    }
    _write_deck(package, "shadowpriest", files)
    _write_deck(runtime, "shadowpriest", files)
    deck_config = runtime / "CustomConfig" / "deck_config.ini"
    deck_config.write_text("ShadowPriest=shadowpriest\n", encoding="utf-8")

    report = build_runtime_package_match_report(
        package_root=package,
        runtime_root=runtime,
        config_dir="shadowpriest",
    )

    assert report["status"] == "matched"
    assert report["runtime_write_performed"] is False
    assert report["runtime_permission_impact"] == "none"
    assert report["semantic_mismatch_count"] == 0
    assert report["deck_config_ini"]["mentions_config_dir"] is True


def test_runtime_package_match_reports_missing_and_changed_json_keys(tmp_path: Path):
    package = tmp_path / "package"
    runtime = tmp_path / "runtime"
    _write_deck(
        package,
        "shadowpriest",
        {
            "GlobalValues.json": {"GameCardId": "GlobalValues"},
            "NX2_019.json": {"GameCardId": "NX2_019", "BeforeBattlecryTargetBonus": {"values": []}},
        },
    )
    _write_deck(
        runtime,
        "shadowpriest",
        {
            "GlobalValues.json": {"GameCardId": "GlobalValues"},
            "NX2_019.json": {"GameCardId": "NX2_019", "BeforePlayCardBonus": {"values": []}},
            "OLD.json": {"GameCardId": "OLD"},
        },
    )
    (runtime / "CustomConfig" / "deck_config.ini").write_text("", encoding="utf-8")

    report = build_runtime_package_match_report(
        package_root=package,
        runtime_root=runtime,
        config_dir="shadowpriest",
    )

    assert report["status"] == "mismatch"
    assert report["extra_in_runtime"] == ["OLD.json"]
    assert report["semantic_mismatch_count"] == 1
    assert report["semantic_mismatches"][0]["file"] == "NX2_019.json"
    assert report["semantic_mismatches"][0]["missing_keys_in_runtime"] == ["BeforeBattlecryTargetBonus"]
    assert report["semantic_mismatches"][0]["extra_keys_in_runtime"] == ["BeforePlayCardBonus"]
    assert report["deck_config_ini"]["mentions_config_dir"] is False
    with pytest.raises(RuntimePackageMismatchError):
        assert_runtime_matches_package(
            package_root=package,
            runtime_root=runtime,
            config_dir="shadowpriest",
        )
```

**Verification**

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_runtime_package_match.py -q
```

Expected: both tests pass.

---

## Task 2: Enforce Post-Copy Runtime Match Inside Guarded Apply

**Files**

- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\runtime_apply.py`
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_runtime_apply.py`

**Intent**

The current apply path validates the package, verifies fake receipt state, copies files, updates `deck_config.ini`, writes a receipt, and supports rollback on exceptions. Add a post-copy semantic match before returning success. If copied runtime differs from package, rollback and fail.

**Implementation**

In `runtime_apply.py`, import:

```python
from hsconfig.runtime_package_match import assert_runtime_matches_package
```

Inside `apply_package`, after `_update_deck_config_ini` and before building/writing the final receipt, add:

```python
runtime_package_match = assert_runtime_matches_package(
    package_root=package,
    runtime_root=runtime,
    config_dir=deck_dir_name,
)
```

Add this field to the final receipt:

```python
"runtime_package_match": runtime_package_match,
```

Add this compact duplicate at top level for operator logs:

```python
"runtime_package_match_status": runtime_package_match["status"],
```

The call must remain inside the existing `try:` block so any mismatch triggers `_restore_runtime_target_snapshot`.

**Tests**

Append to `tests/test_runtime_apply.py`:

```python
def test_apply_package_receipt_includes_runtime_package_match(tmp_path: Path):
    package = _valid_apply_package(tmp_path / "package")
    runtime = tmp_path / "runtime"

    receipt = apply_package(package_root=package, runtime_root=runtime)

    assert receipt["status"] == "applied"
    assert receipt["runtime_package_match_status"] == "matched"
    assert receipt["runtime_package_match"]["status"] == "matched"
    assert receipt["runtime_package_match"]["runtime_write_performed"] is False
    assert receipt["runtime_package_match"]["runtime_permission_impact"] == "none"


def test_apply_package_rolls_back_when_runtime_package_match_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    package = _valid_apply_package(tmp_path / "package")
    runtime = tmp_path / "runtime"
    _write_existing_runtime_config(runtime, "shadowpriest", marker="before")

    def fail_match(**_: object) -> dict[str, object]:
        raise RuntimePackageMismatchError(
            {
                "status": "mismatch",
                "config_dir": "shadowpriest",
                "missing_in_runtime": ["NX2_019.json"],
                "semantic_mismatches": [],
            }
        )

    monkeypatch.setattr("hsconfig.runtime_apply.assert_runtime_matches_package", fail_match)

    with pytest.raises(RuntimePackageMismatchError):
        apply_package(package_root=package, runtime_root=runtime)

    marker = runtime / "CustomConfig" / "shadowpriest" / "marker.txt"
    assert marker.read_text(encoding="utf-8") == "before"
```

Use existing helpers if their names differ. Do not duplicate large fixture builders if equivalent helpers already exist in the file.

**Verification**

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_runtime_apply.py tests/test_runtime_package_match.py -q
```

Expected: all selected tests pass.

---

## Task 3: Add A Read-Only Runtime-Match CLI Command

**Files**

- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\cli_parser.py`
- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\cli.py`
- Create: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\commands\runtime_match.py`
- Create: `C:\Users\darbo\Documents\HSConfig\tests\test_runtime_match_cli.py`

**Intent**

Operators need one explicit command to answer: "Does my active HearthRanger runtime folder match this generated package?" The command is read-only and cannot grant apply permission.

**Parser**

In `cli_parser.py`, add near `apply`:

```python
runtime_match = subparsers.add_parser(
    "runtime-match",
    help=(
        "Read-only package-to-runtime semantic match check. "
        "Does not grant apply permission and never writes runtime files."
    ),
)
runtime_match.add_argument("--package", required=True)
runtime_match.add_argument("--runtime-root", required=True)
runtime_match.add_argument("--config-dir")
runtime_match.add_argument("--json", action="store_true")
```

**Command Module**

Create `commands/runtime_match.py`:

```python
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from hsconfig.commands.common import run_payload_command
from hsconfig.runtime_package_match import build_runtime_package_match_report


def run_runtime_match_command(args: argparse.Namespace) -> int:
    return run_payload_command(args, runtime_match_payload)


def runtime_match_payload(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    package = Path(args.package)
    runtime = Path(args.runtime_root)
    if not package.exists():
        return {"status": "failed", "errors": [f"Package not found: {package}"]}, 1
    report = build_runtime_package_match_report(
        package_root=package,
        runtime_root=runtime,
        config_dir=getattr(args, "config_dir", None),
    )
    return report, 0 if report["status"] == "matched" else 1
```

Wire in `cli.py`:

```python
from hsconfig.commands.runtime_match import run_runtime_match_command

# Add next to the existing command dispatch branches.
if args.command == "runtime-match":
    return run_runtime_match_command(args)
```

**Tests**

Add:

```python
import json
from pathlib import Path

from hsconfig.cli import main
from hsconfig.io import write_json


def test_runtime_match_cli_reports_matched_package(tmp_path: Path, capsys):
    package = tmp_path / "package"
    runtime = tmp_path / "runtime"
    for root in (package, runtime):
        deck = root / "CustomConfig" / "shadowpriest"
        deck.mkdir(parents=True)
        write_json(deck / "GlobalValues.json", {"GameCardId": "GlobalValues"})
        write_json(deck / "Mulligan.json", {"Mulligan": {"values": []}})
    (runtime / "CustomConfig" / "deck_config.ini").write_text(
        "ShadowPriest=shadowpriest\n",
        encoding="utf-8",
    )

    code = main([
        "runtime-match",
        "--package",
        str(package),
        "--runtime-root",
        str(runtime),
        "--json",
    ])

    out = json.loads(capsys.readouterr().out)
    assert code == 0
    assert out["status"] == "matched"
    assert out["runtime_write_performed"] is False


def test_runtime_match_cli_returns_nonzero_for_mismatch(tmp_path: Path, capsys):
    package = tmp_path / "package"
    runtime = tmp_path / "runtime"
    (package / "CustomConfig" / "shadowpriest").mkdir(parents=True)
    (runtime / "CustomConfig" / "shadowpriest").mkdir(parents=True)
    write_json(package / "CustomConfig" / "shadowpriest" / "GlobalValues.json", {"GameCardId": "GlobalValues"})
    write_json(runtime / "CustomConfig" / "shadowpriest" / "GlobalValues.json", {"GameCardId": "Other"})

    code = main([
        "runtime-match",
        "--package",
        str(package),
        "--runtime-root",
        str(runtime),
        "--config-dir",
        "shadowpriest",
        "--json",
    ])

    out = json.loads(capsys.readouterr().out)
    assert code == 1
    assert out["status"] == "mismatch"
```

**Verification**

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_runtime_match_cli.py tests/test_runtime_package_match.py -q
```

Expected: all selected tests pass.

---

## Task 4: Surface Runtime Match In Configure Apply Summaries

**Files**

- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\commands\configure.py`
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_configure_cli.py`

**Intent**

When the user runs the normal all-in-one command with `--apply`, the returned JSON and `reports/configure_summary.json` should say whether the runtime now matches the package. This prevents future "package is valid but runtime is stale" confusion.

**Implementation**

Find the branch in `configure.py` where `apply_payload` is called for `--apply`. Extract:

```python
runtime_package_match = (
    apply_result.get("receipt", {}).get("runtime_package_match")
    if isinstance(apply_result, dict)
    else None
)
runtime_package_match_status = (
    runtime_package_match.get("status")
    if isinstance(runtime_package_match, dict)
    else "not_checked"
)
```

Add these fields to the configure result and persisted summary:

```python
"runtime_package_match_status": runtime_package_match_status,
"runtime_package_match": runtime_package_match,
```

For `configure` without `--apply`, include:

```python
"runtime_package_match_status": "not_checked",
"runtime_package_match": None,
```

Do not add this to `evaluate_apply_gate`, and do not make it part of `runtime_apply_allowed`.

**Tests**

Add or update tests:

```python
def test_configure_apply_summary_includes_runtime_package_match(tmp_path: Path):
    result = _run_configure_for_shadowpriest(tmp_path, apply=True)

    assert result["status"] == "configured"
    assert result["apply"]["status"] == "applied"
    assert result["runtime_package_match_status"] == "matched"
    assert result["runtime_package_match"]["status"] == "matched"

    summary = read_json(Path(result["out"]) / "reports" / "configure_summary.json")
    assert summary["runtime_package_match_status"] == "matched"


def test_configure_without_apply_marks_runtime_match_not_checked(tmp_path: Path):
    result = _run_configure_for_shadowpriest(tmp_path, apply=False)

    assert result["runtime_package_match_status"] == "not_checked"
    assert result["runtime_package_match"] is None
```

Use existing configure helpers instead of creating new large fixtures.

**Verification**

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_configure_cli.py tests/test_runtime_apply.py tests/test_runtime_match_cli.py -q
```

Expected: all selected tests pass.

---

## Task 5: Suppress Misleading Card-Level Explainability Gaps

**Files**

- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\source_to_runtime_explainability.py`
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_source_to_runtime_explainability.py`

**Intent**

The ShadowPriest package had a non-blocking `builder_or_router` first missing link on `NX2_019` even though Mind Sear runtime behavior was emitted through other valid claims. That is correct at the claim row level, but misleading as a card-level gap. Keep claim-level diagnostics. Suppress only the aggregate card-level "first missing link" when the card already has emitted runtime surfaces and no missing expected surfaces.

**Implementation Rule**

In the per-card aggregation logic, after claim rows are evaluated, add a helper:

```python
def _card_level_first_missing_link(
    *,
    emitted_surfaces: list[str],
    missing_runtime_surfaces: list[str],
    claim_missing_links: list[str],
) -> str | None:
    if emitted_surfaces and not missing_runtime_surfaces:
        return None
    return claim_missing_links[0] if claim_missing_links else None
```

Use it only for card-level summary fields such as:

- `first_missing_link`
- summary count of cards with missing link
- operator-facing first missing link

Do not remove claim-level rows, claim-level missing links, or raw claim diagnostics.

**Tests**

Add:

```python
def test_explainability_keeps_claim_gap_but_not_card_gap_when_runtime_is_emitted(tmp_path: Path):
    report = _build_explainability_report(
        tmp_path,
        card_id="NX2_019",
        emitted_surfaces=["NX2_019.json:BeforeBattlecryTargetBonus"],
        missing_runtime_surfaces=[],
        claims=[
            {
                "claim_id": "claim_runtime",
                "runtime_surface": "NX2_019.json",
                "builder_or_router_decision": "emitted",
            },
            {
                "claim_id": "claim_role",
                "claim_kind": "card_role",
                "runtime_surface": "NX2_019.json",
                "builder_or_router_decision": "not_seen_by_builder",
            },
        ],
    )

    card = report["cards"]["NX2_019"]
    assert card.get("first_missing_link") is None
    assert report["summary"]["cards_with_first_missing_link"] == 0
    role_claim = next(row for row in report["claim_rows"] if row["claim_id"] == "claim_role")
    assert role_claim["first_missing_link"] == "builder_or_router"
```

Adapt helper names to the existing fixture style in `tests/test_source_to_runtime_explainability.py`.

**Verification**

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_source_to_runtime_explainability.py tests/test_contract_doctor.py tests/test_contract_preflight.py -q
```

Expected: explainability tests pass, doctor/preflight still report no apply-permission change.

---

## Task 6: Add Status And Summary To GlobalValues Key Profile Report

**Files**

- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\compile_globalvalues.py`
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_prepare_cli.py`
- Modify if needed: `C:\Users\darbo\Documents\HSConfig\tests\test_config_quality_contract.py`
- Modify if needed: `C:\Users\darbo\Documents\HSConfig\tests\test_operator_summary.py`

**Intent**

`global_values_key_profile_report.json` already contains the full key profile, changed keys, unchanged keys, expected overlays, and generated overlays. It should also tell the operator whether that profile is intentionally baseline-held or overlay-changed. This removes the "thin GlobalValues" ambiguity without changing runtime permission.

**Implementation**

In `compile_globalvalues`, build the profile like this:

```python
status = "overlay_changed" if changed_keys else "baseline_confirmed"
summary = {
    "status": status,
    "runtime_permission_impact": "none",
    "key_count": len(profile_keys),
    "changed_key_count": len(changed_keys),
    "unchanged_key_count": len(unchanged_keys),
    "expected_overlay_key_count": len(expected_overlay_keys),
    "generated_overlay_key_count": len(generated_overlay_keys),
    "all_baseline_keys_accounted_for": True,
}
```

Return profile:

```python
"profile": {
    "schema_version": 1,
    "status": status,
    "runtime_permission_impact": "none",
    "summary": summary,
    "key_count": len(profile_keys),
    "generated_overlay_keys": generated_overlay_keys,
    "expected_overlay_keys": expected_overlay_keys,
    "changed_keys": changed_keys,
    "unchanged_keys": unchanged_keys,
    "keys": key_profiles,
}
```

Keep existing top-level fields for backward compatibility.

**Tests**

In `tests/test_prepare_cli.py`, extend the existing profile test around `global_values_key_profile_report.json`:

```python
profile = json.loads((reports / "global_values_key_profile_report.json").read_text(encoding="utf-8"))
assert profile["schema_version"] == 1
assert profile["status"] in {"baseline_confirmed", "overlay_changed"}
assert profile["runtime_permission_impact"] == "none"
assert profile["summary"]["key_count"] == profile["key_count"]
assert profile["summary"]["changed_key_count"] == len(profile["changed_keys"])
assert profile["summary"]["unchanged_key_count"] == len(profile["unchanged_keys"])
```

If `config_quality_contract` currently flags unknown top-level report keys, update the allowlist for this report only. Do not weaken JSON validation globally.

**Verification**

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_prepare_cli.py tests/test_config_quality_contract.py tests/test_operator_summary.py -q
```

Expected: all selected tests pass.

---

## Task 7: Update Operator And Skill Documentation

**Files**

- Modify: `C:\Users\darbo\Documents\HSConfig\docs\operator\README.md`
- Modify: `C:\Users\darbo\Documents\HSConfig\.agents\skills\hsconfig\SKILL.md`
- Modify if present and still synced: `C:\Users\darbo\.codex\skills\hsconfig\SKILL.md`
- Modify: `C:\Users\darbo\.codex\skills\hsconfig\references\workflow.md`

**Intent**

Document the new runtime-match check in the normal operator path and keep installed skill guidance synced. It must be clear that runtime-match is a post-apply installation integrity check, not a semantic/source-strength gate.

**Documentation Text**

Add a short section to `docs/operator/README.md` near runtime apply:

```markdown
### Runtime package match

After `apply` or `configure --apply`, HSConfig verifies that the active
`CustomConfig/<config_dir>` folder semantically matches the validated package
that was copied. This is a technical install-integrity check: if the runtime
folder differs, the apply is rolled back and the command fails.

For read-only audits, run:

```powershell
python -m hsconfig.cli runtime-match --package <package> --runtime-root C:\Users\darbo\Desktop\HS --json
```

`runtime-match` does not grant apply permission and never writes runtime files.
Apply permission still comes only from `reports/operator_summary.json`.
```

In both skill files, add one compact workflow bullet:

```markdown
- After runtime apply, inspect `receipt.runtime_package_match.status`. It must be
  `matched` for a successful install. For read-only checks use
  `python -m hsconfig.cli runtime-match --package <package> --runtime-root <runtime> --json`.
  This is an install-integrity check, not a source/semantic apply gate.
```

**Tests**

Update docs tests if needed:

- `tests/test_skill_files.py`
- `tests/test_operator_docs_contract_policy.py`
- `tests/test_skill_contract_entrypoint.py`

**Verification**

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_skill_files.py tests/test_operator_docs_contract_policy.py tests/test_skill_contract_entrypoint.py -q
```

Expected: all selected tests pass.

---

## Task 8: End-To-End Runtime Sync Proof With ShadowPriest

**Files**

- No code files unless earlier tasks require final adjustments.
- Use a temp runtime root under `C:\Users\darbo\AppData\Local\Temp` or pytest `tmp_path`.
- Do not write to real `C:\Users\darbo\Desktop\HS` during automated tests.

**Command Sequence**

Run from `C:\Users\darbo\Documents\HSConfig`:

```powershell
$env:PYTHONPATH='src'
python -m hsconfig.cli configure `
  --deck-name ShadowPriest `
  --deck-code AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA= `
  --out outputs/verification-shadowpriest-runtime-sync `
  --runtime-root "$env:TEMP\hsconfig-runtime-sync-shadowpriest" `
  --auto-source `
  --apply `
  --json

python -m hsconfig.cli validate --package outputs/verification-shadowpriest-runtime-sync --json

python -m hsconfig.cli contract-preflight --package outputs/verification-shadowpriest-runtime-sync --json

python -m hsconfig.cli contract-doctor --package outputs/verification-shadowpriest-runtime-sync --json

python -m hsconfig.cli runtime-match `
  --package outputs/verification-shadowpriest-runtime-sync `
  --runtime-root "$env:TEMP\hsconfig-runtime-sync-shadowpriest" `
  --json
```

**Expected Output Conditions**

- `configure`: status is `configured`; apply status is `applied`; `runtime_package_match_status="matched"`.
- `validate`: `status="passed"`.
- `contract-preflight`: `status="PASS"`; `technical_status="VALID_PACKAGE"`; `runtime_apply_allowed=true`.
- `contract-doctor`: `status="ok"` and no errors.
- `runtime-match`: `status="matched"` and `runtime_write_performed=false`.

Then run:

```powershell
git status --short --branch
```

Expected: no generated runtime artifacts are left in the repo except intentional source/test/doc changes.

---

## Final Verification Matrix

Run the narrow suite first:

```powershell
$env:PYTHONPATH='src'
python -m pytest `
  tests/test_runtime_package_match.py `
  tests/test_runtime_match_cli.py `
  tests/test_runtime_apply.py `
  tests/test_configure_cli.py `
  tests/test_source_to_runtime_explainability.py `
  tests/test_prepare_cli.py `
  tests/test_contract_doctor.py `
  tests/test_contract_preflight.py `
  tests/test_skill_files.py `
  tests/test_operator_docs_contract_policy.py `
  tests/test_skill_contract_entrypoint.py `
  -q
```

Then run the full suite:

```powershell
$env:PYTHONPATH='src'
python -m pytest -q
```

If the full suite is too slow for one pass, do not claim full completion. Report the narrow suite plus the exact unrun residual risk.

---

## Self-Review Checklist

- [ ] Runtime match is JSON-semantic, not raw byte comparison.
- [ ] Runtime match ignores package reports and runtime history files.
- [ ] Runtime match detects missing files, extra files, semantic JSON differences, and missing `deck_config.ini` config-dir reference.
- [ ] `apply_package` rolls back when post-copy runtime match fails.
- [ ] Apply receipt includes `runtime_package_match_status` and full `runtime_package_match`.
- [ ] `configure --apply` returns and persists runtime match status.
- [ ] `runtime-match` CLI is read-only and returns nonzero on mismatch.
- [ ] No second source/semantic apply gate was introduced.
- [ ] Source-to-runtime explainability still exposes claim-level gaps but no longer falsely promotes emitted-card claim noise into a card-level gap.
- [ ] GlobalValues profile has explicit status/summary and remains backward compatible.
- [ ] Operator docs and installed skill docs describe runtime-match as install integrity only.
- [ ] ShadowPriest temp-runtime proof passes.
- [ ] Git worktree has only intended source/test/doc changes.

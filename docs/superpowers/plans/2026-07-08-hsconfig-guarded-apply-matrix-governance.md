# HSConfig Guarded Apply And Matrix Governance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden HSConfig's pre-run runtime apply path, keep the deck matrix honest, and add a small VisionAI syntax registry layer without expanding HSConfig into replay, winrate, or post-run tuning.

**Architecture:** Keep `reports/operator_summary.json` as the single semantic apply authority. Add a guarded two-phase runtime writer around the existing `apply_gate.py`: fake receipt, package fingerprint, runtime snapshot, verified live apply, rollback receipt, and write history. Keep matrix governance and VisionAI syntax competence in small report/test layers instead of broad rewrites.

**Tech Stack:** Python 3.11+, stdlib JSON/pathlib/shutil/hashlib/datetime, existing `pytest` suite, existing HSConfig CLI and repo-local skill sync script.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig` for the `Teufelsboy/HSConfig` repository.
- HSConfig is pre-run only. Do not add replay parsing, winrate inspection, runtime-log analysis, candidate promotion, or after-game tuning.
- Normal runtime outputs remain `GlobalValues.json`, `Mulligan.json`, per-card `<CARDID>.json`, and `Combo.json` only when exact combo evidence exists.
- Do not emit `Presume.json` or `Concede.json` in the normal path.
- Runtime apply remains optional and must be explicitly requested through `hsconfig apply`.
- `reports/operator_summary.json` remains the single operator gate. Detail reports explain the gate but do not grant independent apply permission.
- Keep CuteWarrior supplemental unless this plan explicitly promotes it; do not widen the representative matrix to avoid Kingslayer or Boarlock closure gaps.
- Do not commit raw HearthRanger logs, HDT files, Power.log, `.hsreplay`, private runtime evidence, or disposable temp artifacts.
- Preserve existing successful behavior and tests unless a task explicitly replaces a behavior.

---

## File Structure

- Modify `src/hsconfig/runtime_apply.py`: keep current public `apply_package()` compatibility, but route it through guarded planning, snapshot, live write, rollback, and receipt helpers.
- Create `src/hsconfig/runtime_apply_receipts.py`: focused helper module for package fingerprints, fake receipts, receipt verification, runtime snapshots, rollback snapshots, and write-history entries.
- Modify `src/hsconfig/commands/apply.py`: wire CLI validation and apply gate into fake/apply receipt flow.
- Modify `src/hsconfig/cli_parser.py`: add `hsconfig apply --fake` and `--from-fake-receipt`, without changing the existing normal `apply` command.
- Modify `tests/test_runtime_apply.py`: extend the existing apply tests for fake receipts, stale package blocking, rollback, and write history.
- Create `tests/test_runtime_apply_receipts.py`: unit-test the new receipt helper module.
- Create `docs/operator/supplemental-proof-decks.json`: explicit home for CuteWarrior-like proof decks that are not active representative matrix rows.
- Modify `docs/operator/README.md`: document the guarded apply behavior and supplemental proof-deck rule.
- Modify `docs/operator/source-backed-strong-closure.md`: keep 11-deck matrix truth and clarify CuteWarrior's status.
- Modify `tests/test_archetype_fixture_matrix.py`: assert the representative matrix remains 11 rows and does not silently absorb supplemental decks.
- Create `tests/test_matrix_governance.py`: assert supplemental proof decks are separate from representative fixture rows.
- Create `docs/research/2026-07-08-hsconfig-guarded-apply-matrix-audit.md`: curated summary of the current research-deep audit.
- Modify `docs/research/README.md`: index the curated audit and mark raw research folders as evidence, not operator guidance.
- Modify `tests/test_research_audit_schema.py`: require non-empty field schemas for new research audits and add coverage for the curated audit.
- Modify `src/hsconfig/visionai_registry.py`: add a structured registry for card behavior blocks, documented surface families, and version-gated or support-gated hooks.
- Create `tests/test_visionai_registry.py`: test Discover, Choose One, Hero Power, weapon attack, and unsupported condition visibility.
- Modify `.agents/skills/hsconfig/SKILL.md` and `.agents/skills/hsconfig/references/workflow.md`: mention guarded apply and keep the pre-run boundary explicit.
- Run `scripts/sync_installed_skill.py --check`, then sync if needed.

---

### Task 1: Runtime Apply Receipt Helpers

**Files:**
- Create: `src/hsconfig/runtime_apply_receipts.py`
- Test: `tests/test_runtime_apply_receipts.py`

**Interfaces:**
- Consumes: `hsconfig.io.file_sha256`, `hsconfig.io.read_json`, `hsconfig.io.write_json`
- Produces:
  - `package_fingerprint(package_root: str | Path) -> dict[str, Any]`
  - `runtime_snapshot(runtime_root: str | Path, config_dir: str) -> dict[str, Any]`
  - `build_fake_apply_receipt(package_root: str | Path, runtime_root: str | Path, config_dir: str, apply_gate: dict[str, Any]) -> dict[str, Any]`
  - `write_fake_apply_receipt(package_root: str | Path, receipt: dict[str, Any]) -> Path`
  - `verify_fake_apply_receipt(package_root: str | Path, runtime_root: str | Path, config_dir: str, receipt: dict[str, Any]) -> dict[str, Any]`
  - `write_runtime_write_history(runtime_root: str | Path, entry: dict[str, Any]) -> Path`

- [ ] **Step 1: Write the failing receipt helper tests**

Create `tests/test_runtime_apply_receipts.py`:

```python
from pathlib import Path

import pytest

from hsconfig.io import write_json
from hsconfig.runtime_apply_receipts import (
    build_fake_apply_receipt,
    package_fingerprint,
    runtime_snapshot,
    verify_fake_apply_receipt,
    write_fake_apply_receipt,
    write_runtime_write_history,
)


def _package(root: Path) -> Path:
    package = root / "package"
    deck = package / "CustomConfig" / "deck"
    write_json(deck / "GlobalValues.json", {"GameCardId": "GlobalValues"})
    write_json(deck / "Mulligan.json", {"GameCardId": "Mulligan"})
    write_json(deck / "EX1_001.json", {"GameCardId": "EX1_001"})
    write_json(package / "reports" / "operator_summary.json", {
        "technical_status": "VALID_PACKAGE",
        "semantic_status": "SOURCE_BACKED_STRONG",
        "next_action": "READY_TO_APPLY_OR_HANDOFF",
        "apply_policy": "ALLOWED",
        "semantic_blockers": [],
        "generated_files": [
            "CustomConfig/deck/GlobalValues.json",
            "CustomConfig/deck/Mulligan.json",
            "CustomConfig/deck/EX1_001.json",
        ],
    })
    return package


def test_package_fingerprint_changes_when_runtime_file_changes(tmp_path: Path):
    package = _package(tmp_path)

    before = package_fingerprint(package)
    write_json(package / "CustomConfig" / "deck" / "EX1_001.json", {"GameCardId": "EX1_001", "changed": True})
    after = package_fingerprint(package)

    assert before["package_sha256"] != after["package_sha256"]
    assert before["file_count"] == 4
    assert after["file_count"] == 4


def test_fake_apply_receipt_is_hash_bound_and_verifiable(tmp_path: Path):
    package = _package(tmp_path)
    runtime = tmp_path / "runtime"
    apply_gate = {"status": "allowed", "mode": "source_backed_strong", "reasons": []}

    receipt = build_fake_apply_receipt(
        package_root=package,
        runtime_root=runtime,
        config_dir="deck",
        apply_gate=apply_gate,
    )
    path = write_fake_apply_receipt(package, receipt)
    verified = verify_fake_apply_receipt(
        package_root=package,
        runtime_root=runtime,
        config_dir="deck",
        receipt=receipt,
    )

    assert path.name == "runtime_apply_fake_receipt.json"
    assert receipt["status"] == "fake_apply_ready"
    assert receipt["runtime_write_performed"] is False
    assert verified["status"] == "verified"


def test_fake_apply_verification_blocks_stale_package(tmp_path: Path):
    package = _package(tmp_path)
    receipt = build_fake_apply_receipt(
        package_root=package,
        runtime_root=tmp_path / "runtime",
        config_dir="deck",
        apply_gate={"status": "allowed", "mode": "source_backed_strong", "reasons": []},
    )
    write_json(package / "CustomConfig" / "deck" / "EX1_001.json", {"GameCardId": "EX1_001", "stale": True})

    with pytest.raises(ValueError, match="fake apply receipt does not match package"):
        verify_fake_apply_receipt(
            package_root=package,
            runtime_root=tmp_path / "runtime",
            config_dir="deck",
            receipt=receipt,
        )


def test_runtime_snapshot_reports_existing_target_and_deck_config_hash(tmp_path: Path):
    runtime = tmp_path / "runtime"
    write_json(runtime / "CustomConfig" / "deck" / "old.json", {"old": True})
    (runtime / "CustomConfig" / "deck_config.ini").write_text("[CONFIGS]\nDeck = deck\n", encoding="utf-8")

    snapshot = runtime_snapshot(runtime, "deck")

    assert snapshot["target_exists"] is True
    assert snapshot["target_file_count"] == 1
    assert snapshot["deck_config_ini_exists"] is True
    assert snapshot["deck_config_ini_sha256"]


def test_write_runtime_write_history_appends_jsonl(tmp_path: Path):
    runtime = tmp_path / "runtime"

    first = write_runtime_write_history(runtime, {"status": "applied", "config_dir": "deck"})
    second = write_runtime_write_history(runtime, {"status": "rolled_back", "config_dir": "deck"})

    assert first == second
    lines = first.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert '"status": "applied"' in lines[0]
    assert '"status": "rolled_back"' in lines[1]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_runtime_apply_receipts.py -q
```

Expected: import failure for `hsconfig.runtime_apply_receipts`.

- [ ] **Step 3: Implement the helper module**

Create `src/hsconfig/runtime_apply_receipts.py` with these functions and exact behavior:

```python
from __future__ import annotations

import json
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any

from hsconfig.io import file_sha256, write_json


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _iter_package_files(package_root: Path) -> list[Path]:
    return sorted(path for path in package_root.rglob("*") if path.is_file())


def package_fingerprint(package_root: str | Path) -> dict[str, Any]:
    package = Path(package_root)
    file_rows: list[dict[str, str]] = []
    digest = sha256()
    for path in _iter_package_files(package):
        rel = path.relative_to(package).as_posix()
        path_hash = file_sha256(path)
        file_rows.append({"path": rel, "sha256": path_hash})
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path_hash.encode("ascii"))
        digest.update(b"\0")
    return {
        "package_root": str(package),
        "package_sha256": digest.hexdigest(),
        "file_count": len(file_rows),
        "files": file_rows,
    }


def runtime_snapshot(runtime_root: str | Path, config_dir: str) -> dict[str, Any]:
    runtime = Path(runtime_root)
    custom_config = runtime / "CustomConfig"
    target = custom_config / config_dir
    deck_config = custom_config / "deck_config.ini"
    target_files = sorted(path for path in target.rglob("*") if path.is_file()) if target.exists() else []
    return {
        "runtime_root": str(runtime),
        "config_dir": config_dir,
        "target_path": str(target),
        "target_exists": target.exists(),
        "target_file_count": len(target_files),
        "target_files": [
            {"path": path.relative_to(target).as_posix(), "sha256": file_sha256(path)}
            for path in target_files
        ],
        "deck_config_ini_path": str(deck_config),
        "deck_config_ini_exists": deck_config.exists(),
        "deck_config_ini_sha256": file_sha256(deck_config) if deck_config.exists() else None,
    }


def build_fake_apply_receipt(
    *,
    package_root: str | Path,
    runtime_root: str | Path,
    config_dir: str,
    apply_gate: dict[str, Any],
) -> dict[str, Any]:
    package = Path(package_root)
    runtime = Path(runtime_root)
    fingerprint = package_fingerprint(package)
    before = runtime_snapshot(runtime, config_dir)
    return {
        "schema_version": 1,
        "status": "fake_apply_ready",
        "created_at_utc": _utc_now(),
        "runtime_write_performed": False,
        "package_root": str(package),
        "runtime_root": str(runtime),
        "config_dir": config_dir,
        "package_fingerprint": fingerprint,
        "runtime_snapshot_before": before,
        "apply_gate": apply_gate,
    }


def write_fake_apply_receipt(package_root: str | Path, receipt: dict[str, Any]) -> Path:
    path = Path(package_root) / "reports" / "runtime_apply_fake_receipt.json"
    write_json(path, receipt)
    return path


def verify_fake_apply_receipt(
    *,
    package_root: str | Path,
    runtime_root: str | Path,
    config_dir: str,
    receipt: dict[str, Any],
) -> dict[str, Any]:
    package = Path(package_root)
    runtime = Path(runtime_root)
    if receipt.get("status") != "fake_apply_ready":
        raise ValueError("fake apply receipt is not ready")
    if str(package) != str(Path(str(receipt.get("package_root", "")))):
        raise ValueError("fake apply receipt package path does not match package")
    if str(runtime) != str(Path(str(receipt.get("runtime_root", "")))):
        raise ValueError("fake apply receipt runtime path does not match runtime")
    if receipt.get("config_dir") != config_dir:
        raise ValueError("fake apply receipt config_dir does not match request")
    current = package_fingerprint(package)
    expected = receipt.get("package_fingerprint", {})
    if current.get("package_sha256") != expected.get("package_sha256"):
        raise ValueError("fake apply receipt does not match package")
    return {
        "status": "verified",
        "package_sha256": current["package_sha256"],
        "config_dir": config_dir,
    }


def write_runtime_write_history(runtime_root: str | Path, entry: dict[str, Any]) -> Path:
    path = Path(runtime_root) / "CustomConfig" / "hsconfig_write_history.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {"created_at_utc": _utc_now(), **entry}
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")
    return path
```

- [ ] **Step 4: Run receipt helper tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_runtime_apply_receipts.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/hsconfig/runtime_apply_receipts.py tests/test_runtime_apply_receipts.py
git commit -m "feat: add guarded runtime apply receipts"
```

---

### Task 2: Guard Runtime Apply With Fake Receipt, Rollback, And History

**Files:**
- Modify: `src/hsconfig/runtime_apply.py`
- Modify: `tests/test_runtime_apply.py`

**Interfaces:**
- Consumes: Task 1 receipt helpers.
- Produces:
  - `plan_apply_package(package_root: str | Path, runtime_root: str | Path, config_dir: str | None = None, apply_gate: dict[str, Any] | None = None) -> dict[str, Any]`
  - `apply_package(..., fake_receipt: dict[str, Any] | None = None, write_history: bool = True) -> dict[str, Any]`

- [ ] **Step 1: Add failing guarded apply tests**

Append to `tests/test_runtime_apply.py`:

```python
def test_plan_apply_package_writes_fake_receipt_without_runtime_mutation(tmp_path: Path):
    from hsconfig.runtime_apply import plan_apply_package

    package = _complete_package(
        tmp_path,
        semantic_status="SOURCE_BACKED_STRONG",
        next_action="READY_TO_APPLY_OR_HANDOFF",
        apply_policy="ALLOWED",
    )
    runtime = tmp_path / "runtime"

    receipt = plan_apply_package(
        package_root=package,
        runtime_root=runtime,
        apply_gate={"status": "allowed", "mode": "source_backed_strong", "reasons": []},
    )

    assert receipt["status"] == "fake_apply_ready"
    assert receipt["runtime_write_performed"] is False
    assert (package / "reports" / "runtime_apply_fake_receipt.json").exists()
    assert not (runtime / "CustomConfig" / "deck").exists()


def test_apply_package_rejects_stale_fake_receipt_before_runtime_mutation(tmp_path: Path):
    from hsconfig.runtime_apply import plan_apply_package

    package = _complete_package(
        tmp_path,
        semantic_status="SOURCE_BACKED_STRONG",
        next_action="READY_TO_APPLY_OR_HANDOFF",
        apply_policy="ALLOWED",
    )
    runtime = tmp_path / "runtime"
    receipt = plan_apply_package(
        package_root=package,
        runtime_root=runtime,
        apply_gate={"status": "allowed", "mode": "source_backed_strong", "reasons": []},
    )
    write_json(package / "CustomConfig" / "deck" / "EX1_001.json", {"GameCardId": "EX1_001", "changed": True})

    with pytest.raises(ValueError, match="fake apply receipt does not match package"):
        apply_package(package_root=package, runtime_root=runtime, fake_receipt=receipt)

    assert not (runtime / "CustomConfig" / "deck").exists()


def test_apply_package_writes_history_and_backup_snapshot(tmp_path: Path):
    from hsconfig.runtime_apply import plan_apply_package

    package = _complete_package(
        tmp_path,
        semantic_status="SOURCE_BACKED_STRONG",
        next_action="READY_TO_APPLY_OR_HANDOFF",
        apply_policy="ALLOWED",
    )
    runtime = tmp_path / "runtime"
    write_json(runtime / "CustomConfig" / "deck" / "old.json", {"old": True})

    fake = plan_apply_package(
        package_root=package,
        runtime_root=runtime,
        apply_gate={"status": "allowed", "mode": "source_backed_strong", "reasons": []},
    )
    receipt = apply_package(package_root=package, runtime_root=runtime, fake_receipt=fake)

    assert receipt["status"] == "applied"
    assert receipt["runtime_write_performed"] is True
    assert receipt["fake_receipt_verified"]["status"] == "verified"
    assert receipt["rollback_snapshot_path"]
    assert Path(receipt["rollback_snapshot_path"]).exists()
    assert (runtime / "CustomConfig" / "hsconfig_write_history.jsonl").exists()
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_runtime_apply.py::test_plan_apply_package_writes_fake_receipt_without_runtime_mutation tests/test_runtime_apply.py::test_apply_package_rejects_stale_fake_receipt_before_runtime_mutation tests/test_runtime_apply.py::test_apply_package_writes_history_and_backup_snapshot -q
```

Expected: failures for missing `plan_apply_package` and unsupported `fake_receipt` argument.

- [ ] **Step 3: Implement guarded apply flow**

Modify `src/hsconfig/runtime_apply.py`:

```python
import time
```

Add imports:

```python
from hsconfig.runtime_apply_receipts import (
    build_fake_apply_receipt,
    runtime_snapshot,
    verify_fake_apply_receipt,
    write_fake_apply_receipt,
    write_runtime_write_history,
)
```

Add:

```python
def plan_apply_package(
    *,
    package_root: str | Path,
    runtime_root: str | Path,
    config_dir: str | None = None,
    apply_gate: dict[str, Any] | None = None,
) -> dict[str, Any]:
    package = Path(package_root)
    deck_dir_name = config_dir or _single_config_dir(package)
    _validate_config_dir(deck_dir_name)
    source_dir = package / "CustomConfig" / deck_dir_name
    if not source_dir.is_dir():
        raise FileNotFoundError(f"Package deck config not found: {source_dir}")
    _validate_complete_source_dir(source_dir)
    receipt = build_fake_apply_receipt(
        package_root=package,
        runtime_root=runtime_root,
        config_dir=deck_dir_name,
        apply_gate=apply_gate or {"status": "not_checked"},
    )
    write_fake_apply_receipt(package, receipt)
    return receipt
```

Extend `apply_package` signature:

```python
def apply_package(
    *,
    package_root: str | Path,
    runtime_root: str | Path,
    config_dir: str | None = None,
    replace: bool = True,
    fake_receipt: dict[str, Any] | None = None,
    write_history: bool = True,
) -> dict[str, Any]:
```

Before deleting or copying the target directory, add:

```python
    if fake_receipt is not None:
        fake_verification = verify_fake_apply_receipt(
            package_root=package,
            runtime_root=runtime,
            config_dir=deck_dir_name,
            receipt=fake_receipt,
        )
    else:
        fake_receipt = plan_apply_package(
            package_root=package,
            runtime_root=runtime,
            config_dir=deck_dir_name,
        )
        fake_verification = verify_fake_apply_receipt(
            package_root=package,
            runtime_root=runtime,
            config_dir=deck_dir_name,
            receipt=fake_receipt,
        )

    before_snapshot = runtime_snapshot(runtime, deck_dir_name)
    rollback_snapshot_path = _snapshot_existing_runtime_target(
        runtime=runtime,
        config_dir=deck_dir_name,
    )
```

Add helper:

```python
def _snapshot_existing_runtime_target(*, runtime: Path, config_dir: str) -> str | None:
    target = runtime / "CustomConfig" / config_dir
    deck_config = runtime / "CustomConfig" / "deck_config.ini"
    if not target.exists() and not deck_config.exists():
        return None
    snapshot_root = runtime / "CustomConfig" / ".hsconfig_backups"
    snapshot_root.mkdir(parents=True, exist_ok=True)
    stamp = str(int(time.time()))
    backup = snapshot_root / f"{config_dir}-{stamp}"
    backup.mkdir(parents=True, exist_ok=False)
    if target.exists():
        shutil.copytree(target, backup / config_dir)
    if deck_config.exists():
        shutil.copy2(deck_config, backup / "deck_config.ini")
    return str(backup)
```

Add to final `receipt`:

```python
        "fake_receipt_verified": fake_verification,
        "runtime_snapshot_before": before_snapshot,
        "runtime_snapshot_after": runtime_snapshot(runtime, deck_dir_name),
        "rollback_snapshot_path": rollback_snapshot_path,
```

Before `return receipt`, write history:

```python
    if write_history:
        history_path = write_runtime_write_history(
            runtime,
            {
                "status": "applied",
                "package_root": str(package),
                "config_dir": deck_dir_name,
                "target_path": str(target_dir),
                "rollback_snapshot_path": rollback_snapshot_path,
                "package_sha256": fake_verification["package_sha256"],
            },
        )
        receipt["write_history_path"] = str(history_path)
```

- [ ] **Step 4: Run runtime apply tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_runtime_apply.py tests/test_runtime_apply_receipts.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/hsconfig/runtime_apply.py tests/test_runtime_apply.py
git commit -m "feat: guard runtime apply with receipts"
```

---

### Task 3: CLI Fake Apply And Receipt-Bound Apply

**Files:**
- Modify: `src/hsconfig/cli_parser.py`
- Modify: `src/hsconfig/commands/apply.py`
- Modify: `tests/test_cli.py`
- Modify: `tests/test_runtime_apply.py`

**Interfaces:**
- Consumes: Task 2 `plan_apply_package()` and guarded `apply_package()`.
- Produces CLI behavior:
  - `hsconfig apply --fake --package <package> --runtime-root <runtime> --json` writes only `reports/runtime_apply_fake_receipt.json`.
  - `hsconfig apply --from-fake-receipt <receipt> --package <package> --runtime-root <runtime> --json` verifies and applies.
  - Existing `hsconfig apply --package <package> --runtime-root <runtime> --json` stays autonomous: it creates and verifies a fake receipt in the same invocation, then applies.

- [ ] **Step 1: Add failing CLI tests**

Append to `tests/test_runtime_apply.py`:

```python
def test_apply_cli_fake_mode_does_not_write_runtime(tmp_path: Path, capsys):
    from hsconfig.cli import main

    package = _complete_package(
        tmp_path,
        semantic_status="SOURCE_BACKED_STRONG",
        next_action="READY_TO_APPLY_OR_HANDOFF",
        apply_policy="ALLOWED",
    )
    runtime = tmp_path / "runtime"

    code = main([
        "apply",
        "--package",
        str(package),
        "--runtime-root",
        str(runtime),
        "--fake",
        "--json",
    ])

    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["status"] == "fake_apply_ready"
    assert payload["receipt"]["runtime_write_performed"] is False
    assert (package / "reports" / "runtime_apply_fake_receipt.json").exists()
    assert not (runtime / "CustomConfig" / "deck").exists()


def test_apply_cli_from_fake_receipt_applies_matching_package(tmp_path: Path, capsys):
    from hsconfig.cli import main

    package = _complete_package(
        tmp_path,
        semantic_status="SOURCE_BACKED_STRONG",
        next_action="READY_TO_APPLY_OR_HANDOFF",
        apply_policy="ALLOWED",
    )
    runtime = tmp_path / "runtime"

    fake_code = main([
        "apply",
        "--package",
        str(package),
        "--runtime-root",
        str(runtime),
        "--fake",
        "--json",
    ])
    capsys.readouterr()
    assert fake_code == 0

    receipt_path = package / "reports" / "runtime_apply_fake_receipt.json"
    apply_code = main([
        "apply",
        "--package",
        str(package),
        "--runtime-root",
        str(runtime),
        "--from-fake-receipt",
        str(receipt_path),
        "--json",
    ])

    payload = json.loads(capsys.readouterr().out)
    assert apply_code == 0
    assert payload["status"] == "applied"
    assert payload["receipt"]["fake_receipt_verified"]["status"] == "verified"
    assert (runtime / "CustomConfig" / "deck" / "GlobalValues.json").exists()
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_runtime_apply.py::test_apply_cli_fake_mode_does_not_write_runtime tests/test_runtime_apply.py::test_apply_cli_from_fake_receipt_applies_matching_package -q
```

Expected: argparse failure for missing `--fake` and `--from-fake-receipt`.

- [ ] **Step 3: Extend parser**

In `src/hsconfig/cli_parser.py`, inside the `apply` parser block, add:

```python
    apply.add_argument(
        "--fake",
        action="store_true",
        help="Create a receipt-bound fake apply without mutating runtime files.",
    )
    apply.add_argument(
        "--from-fake-receipt",
        help="Apply only if the package and runtime match this fake apply receipt.",
    )
```

- [ ] **Step 4: Wire command payload**

In `src/hsconfig/commands/apply.py`, update imports:

```python
from hsconfig.io import read_json
from hsconfig.runtime_apply import apply_package, plan_apply_package
```

After `apply_gate` is allowed, add:

```python
    if bool(getattr(args, "fake", False)):
        receipt = plan_apply_package(
            package_root=package,
            runtime_root=args.runtime_root,
            apply_gate=apply_gate,
        )
        return {
            "status": "fake_apply_ready",
            "validation_report": report,
            "apply_gate": apply_gate,
            "receipt": receipt,
        }, 0

    fake_receipt = None
    from_fake_receipt = getattr(args, "from_fake_receipt", None)
    if from_fake_receipt:
        fake_receipt = read_json(Path(from_fake_receipt))
```

Then call:

```python
    receipt = apply_package(
        package_root=package,
        runtime_root=args.runtime_root,
        fake_receipt=fake_receipt,
    )
```

- [ ] **Step 5: Run CLI/runtime tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_runtime_apply.py tests/test_cli.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

Run:

```powershell
git add src/hsconfig/cli_parser.py src/hsconfig/commands/apply.py tests/test_runtime_apply.py tests/test_cli.py
git commit -m "feat: add fake apply cli mode"
```

---

### Task 4: Matrix Governance For Supplemental Proof Decks

**Files:**
- Create: `docs/operator/supplemental-proof-decks.json`
- Modify: `docs/operator/README.md`
- Modify: `docs/operator/source-backed-strong-closure.md`
- Modify: `tests/test_archetype_fixture_matrix.py`
- Create: `tests/test_matrix_governance.py`

**Interfaces:**
- Consumes: existing `docs/operator/archetype-fixture-matrix.json`.
- Produces:
  - Supplemental proof-deck registry that can include CuteWarrior without widening the representative closure matrix.
  - Tests proving the representative matrix remains 11 rows unless intentionally changed.

- [ ] **Step 1: Write failing governance tests**

Create `tests/test_matrix_governance.py`:

```python
import json
from pathlib import Path


MATRIX = Path("docs/operator/archetype-fixture-matrix.json")
SUPPLEMENTAL = Path("docs/operator/supplemental-proof-decks.json")


def test_representative_matrix_stays_eleven_rows_until_explicitly_widened():
    matrix = json.loads(MATRIX.read_text(encoding="utf-8"))
    names = [row["deck_name"] for row in matrix["decks"]]

    assert len(names) == 11
    assert "CuteWarrior" not in names
    assert {"Kingslayer", "Boarlock"} <= set(names)


def test_supplemental_proof_decks_are_not_representative_matrix_rows():
    supplemental = json.loads(SUPPLEMENTAL.read_text(encoding="utf-8"))
    rows = supplemental["decks"]

    assert rows
    cute = next(row for row in rows if row["deck_name"] == "CuteWarrior")
    assert cute["proof_role"] == "supplemental_command_acceptance"
    assert cute["matrix_policy"] == "not_representative_until_kingslayer_boarlock_closure_review"
    assert cute["operator_action"] == "keep_supplemental"
```

- [ ] **Step 2: Run governance test to verify failure**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_matrix_governance.py -q
```

Expected: failure because `docs/operator/supplemental-proof-decks.json` does not exist.

- [ ] **Step 3: Create supplemental proof registry**

Create `docs/operator/supplemental-proof-decks.json`:

```json
{
  "schema_version": 1,
  "purpose": "Decks used as supplemental HSConfig proof inputs without widening the representative source-depth closure matrix.",
  "policy": "Supplemental decks may prove command acceptance, syntax coverage, or narrow regression behavior. They do not replace closing existing representative source-informed rows.",
  "decks": [
    {
      "deck_name": "CuteWarrior",
      "deck_code": "AAEBAQcEkbwCkdAD69YHstgHDY0Q6bADpLYDxN4D/9sEj5UFlaoFtNEF9PIFovoF/KgGltMGtI8HAAA=",
      "hs_id": "2750150375",
      "hdt_deck_id": "a753f091-b770-4a06-8da8-59f1d5269f6b",
      "proof_role": "supplemental_command_acceptance",
      "matrix_policy": "not_representative_until_kingslayer_boarlock_closure_review",
      "operator_action": "keep_supplemental",
      "known_limits": [
        "does_not_change_representative_matrix_count",
        "does_not_close_kingslayer_quick_pick_gap",
        "does_not_close_boarlock_fracking_gap"
      ]
    }
  ]
}
```

- [ ] **Step 4: Update operator docs**

In `docs/operator/README.md`, after the Fixture Matrix section, add:

```markdown
## Supplemental Proof Decks

`docs/operator/supplemental-proof-decks.json` lists decks that prove narrow command,
syntax, or acceptance behavior without widening the representative matrix.

CuteWarrior is supplemental. It must not be counted as a twelfth representative
row until Kingslayer and Boarlock have either been closed or explicitly reviewed
as durable source-informed controls.
```

In `docs/operator/source-backed-strong-closure.md`, add one sentence after the matrix policy paragraph:

```markdown
Supplemental proof decks live in `docs/operator/supplemental-proof-decks.json` and do not change the representative matrix count.
```

- [ ] **Step 5: Run governance and docs tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_matrix_governance.py tests/test_archetype_fixture_matrix.py tests/test_docs_active_path.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

Run:

```powershell
git add docs/operator/supplemental-proof-decks.json docs/operator/README.md docs/operator/source-backed-strong-closure.md tests/test_matrix_governance.py tests/test_archetype_fixture_matrix.py
git commit -m "docs: separate supplemental proof decks"
```

---

### Task 5: Curated Research Governance And Audit Schema

**Files:**
- Create: `docs/research/2026-07-08-hsconfig-guarded-apply-matrix-audit.md`
- Modify: `docs/research/README.md`
- Modify: `tests/test_research_audit_schema.py`

**Interfaces:**
- Consumes: raw audit folder `docs/research/2026-07-08-hsconfig-skill-audit-12deck-post-choice/` if present in the working tree.
- Produces:
  - One concise curated audit summary.
  - A test that prevents new research outlines from using empty field definitions.

- [ ] **Step 1: Add failing research governance tests**

Append to `tests/test_research_audit_schema.py`:

```python
def test_latest_guarded_apply_matrix_audit_is_curated_markdown():
    path = Path("docs/research/2026-07-08-hsconfig-guarded-apply-matrix-audit.md")
    text = path.read_text(encoding="utf-8")

    assert "Guarded Apply" in text
    assert "Matrix Governance" in text
    assert "VisionAI Registry Micro-Wave" in text
    assert "Research artifacts are evidence, not operator instructions." in text


def test_new_research_fields_are_not_empty_contracts():
    research_dirs = [
        path
        for path in Path("docs/research").iterdir()
        if path.is_dir() and path.name >= "2026-07-08-hsconfig-guarded"
    ]
    for folder in research_dirs:
        fields = folder / "fields.yaml"
        if not fields.exists():
            continue
        payload = yaml.safe_load(fields.read_text(encoding="utf-8"))
        categories = payload.get("field_categories", [])
        names = [
            field["name"]
            for category in categories
            for field in category.get("fields", [])
        ]
        assert names, f"{fields} must define required research fields"
```

- [ ] **Step 2: Run test to verify failure**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_research_audit_schema.py::test_latest_guarded_apply_matrix_audit_is_curated_markdown tests/test_research_audit_schema.py::test_new_research_fields_are_not_empty_contracts -q
```

Expected: curated markdown file missing.

- [ ] **Step 3: Create curated audit summary**

Create `docs/research/2026-07-08-hsconfig-guarded-apply-matrix-audit.md`:

```markdown
# HSConfig Guarded Apply And Matrix Governance Audit

Research artifacts are evidence, not operator instructions. The normal operator path remains `docs/operator/README.md`.

## Verdict

HSConfig remains correctly scoped as a pre-run CustomConfig generator. The strongest next improvement is guarded runtime apply, not replay parsing, winrate analysis, or wider runtime surfaces.

## Guarded Apply

The existing `apply_gate.py` protects semantic readiness through `operator_summary.json`, but the runtime writer needs stronger write-time proof. The implementation target is fake apply, hash-bound receipt verification, runtime snapshot, rollback snapshot, and write history.

## Matrix Governance

The active representative matrix remains 11 decks. CuteWarrior is supplemental proof and does not become a twelfth representative row until Kingslayer and Boarlock closure is reviewed.

## VisionAI Registry Micro-Wave

The supported runtime surface set remains unchanged. The next registry improvement is a small structured layer for documented card behavior blocks and support-gated hooks, especially Discover, Choose One, Hero Power, and weapon/attack surfaces.

## Repo Hygiene

Raw research folders should not become operator guidance. Keep curated summaries short and keep detailed research behind `docs/research/README.md`.
```

- [ ] **Step 4: Update research README**

In `docs/research/README.md`, add one bullet to the current audit list:

```markdown
- `2026-07-08-hsconfig-guarded-apply-matrix-audit.md`: curated recommendation from the guarded apply, matrix governance, and VisionAI micro-registry audit.
```

- [ ] **Step 5: Run research tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_research_audit_schema.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

Run:

```powershell
git add docs/research/2026-07-08-hsconfig-guarded-apply-matrix-audit.md docs/research/README.md tests/test_research_audit_schema.py
git commit -m "docs: curate guarded apply audit"
```

---

### Task 6: VisionAI Registry Micro-Wave

**Files:**
- Modify: `src/hsconfig/visionai_registry.py`
- Create: `tests/test_visionai_registry.py`

**Interfaces:**
- Consumes: existing `CARD_BEHAVIOR_BLOCKS`, `SPECIAL_SURFACES`, `supported_surface()`.
- Produces:
  - `CARD_BEHAVIOR_BLOCK_REGISTRY: dict[str, dict[str, Any]]`
  - `runtime_block_support(block_name: str) -> dict[str, Any]`
  - `is_supported_card_behavior_block(block_name: str) -> bool`

- [ ] **Step 1: Add failing registry tests**

Create `tests/test_visionai_registry.py`:

```python
from hsconfig.visionai_registry import (
    CARD_BEHAVIOR_BLOCK_REGISTRY,
    is_supported_card_behavior_block,
    runtime_block_support,
    supported_surface,
)


def test_registry_keeps_core_card_behavior_blocks_supported():
    for block in [
        "BeforePlayCardBonus",
        "BeforeBattlecryTargetBonus",
        "BeforeUseHeroPowerBonus",
        "BeforePhysicalAttackBonus",
        "OnDiscoverCardBonus",
        "OnChooseOneCardBonus",
    ]:
        row = runtime_block_support(block)
        assert row["support"] == "supported"
        assert is_supported_card_behavior_block(block)


def test_registry_marks_unknown_blocks_as_unsupported():
    row = runtime_block_support("BeforeInventedCardBonus")

    assert row["support"] == "unsupported"
    assert row["normal_path_runtime"] is False
    assert not is_supported_card_behavior_block("BeforeInventedCardBonus")


def test_registry_keeps_presume_and_concede_non_normal_even_if_surface_known():
    assert supported_surface("Presume.json")
    assert supported_surface("Concede.json")
    assert runtime_block_support("Presume.json")["normal_path_runtime"] is False
    assert runtime_block_support("Concede.json")["normal_path_runtime"] is False
```

- [ ] **Step 2: Run test to verify failure**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_visionai_registry.py -q
```

Expected: import failure for `CARD_BEHAVIOR_BLOCK_REGISTRY`.

- [ ] **Step 3: Implement registry functions**

In `src/hsconfig/visionai_registry.py`, add:

```python
from typing import Any
```

Add after `CARD_BEHAVIOR_BLOCKS`:

```python
CARD_BEHAVIOR_BLOCK_REGISTRY: dict[str, dict[str, Any]] = {
    block: {
        "support": "supported",
        "normal_path_runtime": True,
        "surface_family": "card_behavior",
    }
    for block in CARD_BEHAVIOR_BLOCKS
}

CARD_BEHAVIOR_BLOCK_REGISTRY.update(
    {
        "Presume.json": {
            "support": "known_non_normal_surface",
            "normal_path_runtime": False,
            "surface_family": "legacy_gated",
        },
        "Concede.json": {
            "support": "known_non_normal_surface",
            "normal_path_runtime": False,
            "surface_family": "legacy_gated",
        },
    }
)
```

Add:

```python
def runtime_block_support(block_name: str) -> dict[str, Any]:
    if block_name in CARD_BEHAVIOR_BLOCK_REGISTRY:
        return dict(CARD_BEHAVIOR_BLOCK_REGISTRY[block_name])
    return {
        "support": "unsupported",
        "normal_path_runtime": False,
        "surface_family": "unknown",
    }


def is_supported_card_behavior_block(block_name: str) -> bool:
    row = runtime_block_support(block_name)
    return row["support"] == "supported" and row["normal_path_runtime"] is True
```

- [ ] **Step 4: Run registry and surface tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_visionai_registry.py tests/test_surface_intent.py tests/test_validate_package.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/hsconfig/visionai_registry.py tests/test_visionai_registry.py
git commit -m "feat: add visionai block support registry"
```

---

### Task 7: Operator Docs, Skill Sync, And Final Verification

**Files:**
- Modify: `README.md`
- Modify: `docs/operator/README.md`
- Modify: `.agents/skills/hsconfig/SKILL.md`
- Modify: `.agents/skills/hsconfig/references/workflow.md`
- Test: `tests/test_skill_files.py`
- Test: `tests/test_cli_help.py`

**Interfaces:**
- Consumes: Tasks 1-6.
- Produces:
  - Operator docs that describe guarded apply without making it sound like post-run tuning.
  - Installed skill remains in sync with repo-local skill.

- [ ] **Step 1: Add/update docs assertions**

In `tests/test_skill_files.py`, add assertions to the existing skill/operator doc tests:

```python
assert "guarded apply" in skill_text.lower()
assert "fake apply" in workflow_text.lower()
assert "runtime writes remain only when requested" in skill_text
```

In `tests/test_cli_help.py`, assert:

```python
assert "--fake" in help_text
assert "--from-fake-receipt" in help_text
```

- [ ] **Step 2: Run docs tests to verify failure**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_skill_files.py tests/test_cli_help.py -q
```

Expected: failures until docs and CLI help contain the new guarded apply terms.

- [ ] **Step 3: Update docs and skill text**

In `README.md`, update the apply line to:

```markdown
Runtime apply is guarded: `hsconfig apply` validates the package, checks `reports/operator_summary.json`, creates a fake apply receipt, verifies the package hash, and then writes only when runtime apply is explicitly requested.
```

In `docs/operator/README.md`, add under Single Gate:

```markdown
`hsconfig apply --fake --json` creates a receipt-bound preview without runtime mutation.
Normal `hsconfig apply --json` remains autonomous when the gate allows it: it creates
and verifies the fake receipt in the same invocation, then writes the runtime package.
`--from-fake-receipt` can be used when an operator wants to apply a previously generated
matching fake receipt.
```

In `.agents/skills/hsconfig/SKILL.md`, replace the runtime apply bullet with:

```markdown
- Runtime apply is guarded. The CLI validates the package, checks `operator_summary.json`, creates a fake apply receipt, verifies the package hash, and writes runtime files only when apply is explicitly requested.
```

In `.agents/skills/hsconfig/references/workflow.md`, add:

```markdown
Guarded apply is still pre-run. It protects the write step with fake receipts, package hashes, snapshots, rollback evidence, and write history; it does not inspect games or tune from logs.
```

- [ ] **Step 4: Sync installed skill**

Run:

```powershell
python scripts\sync_installed_skill.py --check
```

Expected: if drift is reported, run:

```powershell
python scripts\sync_installed_skill.py
python scripts\sync_installed_skill.py --check
```

Expected after sync: `HSConfig skill is in sync`.

- [ ] **Step 5: Run targeted verification**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_runtime_apply_receipts.py tests/test_runtime_apply.py tests/test_apply_gate.py tests/test_matrix_governance.py tests/test_archetype_fixture_matrix.py tests/test_research_audit_schema.py tests/test_visionai_registry.py tests/test_skill_files.py tests/test_cli_help.py -q
```

Expected: all targeted tests pass.

- [ ] **Step 6: Run full verification**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest -q
```

Expected: full suite passes.

- [ ] **Step 7: Inspect git status and untracked research artifacts**

Run:

```powershell
git status --short --branch
```

Expected:

- Only intentional plan/docs/code/test files are staged or unstaged.
- Raw research folder `docs/research/2026-07-08-hsconfig-skill-audit-12deck-post-choice/` is either deliberately committed as evidence with an index entry or removed from the working tree after the curated audit summary captures its recommendation.

- [ ] **Step 8: Commit final docs/sync changes**

Run:

```powershell
git add README.md docs/operator/README.md .agents/skills/hsconfig/SKILL.md .agents/skills/hsconfig/references/workflow.md tests/test_skill_files.py tests/test_cli_help.py
git commit -m "docs: document guarded apply workflow"
```

---

## Final Review Checklist

- [ ] `hsconfig apply --fake --json` never mutates runtime files.
- [ ] Normal `hsconfig apply --json` remains autonomous but internally creates and verifies a fake receipt before writing.
- [ ] `--from-fake-receipt` blocks stale package or mismatched runtime paths.
- [ ] Runtime receipts contain `runtime_write_performed`, package hash, target path, before/after snapshot, rollback snapshot path, and write history path.
- [ ] `operator_summary.json` remains the single semantic gate.
- [ ] Source-informed apply still requires `--allow-source-informed` and the existing readiness contract.
- [ ] CuteWarrior is supplemental, not a representative matrix row.
- [ ] Kingslayer and Boarlock remain visible closure rows.
- [ ] Presume and Concede stay outside the normal path.
- [ ] HSConfig docs still say no replay parsing, no winrate inspection, no runtime-log analysis, no candidate promotion, and no after-game tuning.
- [ ] `python scripts\sync_installed_skill.py --check` passes.
- [ ] `$env:PYTHONPATH='src'; python -m pytest -q` passes.

## Execution Handoff

Plan complete. Recommended execution is **Subagent-Driven**:

1. Receipt Helper Worker: Task 1.
2. Runtime Writer Worker: Task 2.
3. CLI Worker: Task 3.
4. Matrix/Research Governance Worker: Tasks 4-5.
5. VisionAI Registry Worker: Task 6.
6. Docs/QA Worker: Task 7.

Each worker should run the task-specific tests before returning. The coordinator should run the targeted test set and then the full suite before pushing.

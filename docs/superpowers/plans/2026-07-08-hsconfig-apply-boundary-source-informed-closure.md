# HSConfig Apply Boundary And Source-Informed Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make HSConfig runtime apply impossible to bypass outside the operator gate, then prove the current Boarlock and Kingslayer source-informed rows remain either honestly promotable or explicitly blocked without widening the normal runtime surface.

**Architecture:** Keep HSConfig as a pre-run CustomConfig generator. Centralize runtime-write authorization around `reports/operator_summary.json` and `evaluate_apply_gate()`, then use the existing representative fixture matrix to prove Boarlock and Kingslayer closure state. Do not add a new deck, a new normal runtime file type, or post-run tuning behavior.

**Tech Stack:** Python 3, pytest, HearthRanger VisionAI JSON packages, existing `hsconfig` CLI and package modules.

## Global Constraints

- Work only in `C:\Users\darbo\Documents\HSConfig`.
- Keep HSConfig pre-run only; do not add replay parsing, winrate validation, HSTuner candidate promotion, or post-run tuning.
- Normal runtime package surfaces stay limited to `GlobalValues.json`, `Mulligan.json`, per-card `<CARDID>.json`, and exact-evidence `Combo.json`.
- Do not emit normal-path `Presume.json` or `Concede.json`.
- Do not add a twelfth representative matrix deck.
- Do not force weak mulligan claims for Boarlock `Fracking` or Kingslayer `Quick Pick`.
- Runtime writes must be allowed only by `reports/operator_summary.json` through `evaluate_apply_gate()`.
- Keep generated raw runtime evidence out of git.

---

## File Structure

- Modify `C:\Users\darbo\Documents\HSConfig\src\hsconfig\runtime_apply.py`
  - Responsibility: fail-closed runtime mutation boundary. Public `apply_package()` must resolve or validate an allowed apply gate before any fake receipt verification, backup, delete, copy, or `deck_config.ini` write.
- Modify `C:\Users\darbo\Documents\HSConfig\src\hsconfig\commands\apply.py`
  - Responsibility: keep CLI behavior unchanged while passing the real `evaluate_apply_gate()` result into runtime apply.
- Modify `C:\Users\darbo\Documents\HSConfig\tests\test_runtime_apply.py`
  - Responsibility: prove direct API calls cannot bypass the operator gate and preserve existing runtime rollback behavior.
- Create `C:\Users\darbo\Documents\HSConfig\tests\test_source_informed_closure_contract.py`
  - Responsibility: one focused contract test for Boarlock and Kingslayer closure state, generated surfaces, first missing chains, and no matrix widening.
- Modify `C:\Users\darbo\Documents\HSConfig\docs\operator\README.md`
  - Responsibility: document that CLI and direct API runtime writes are governed by the same operator gate.
- Modify `C:\Users\darbo\Documents\HSConfig\docs\operator\source-backed-strong-closure.md`
  - Responsibility: document that Boarlock remains priority 1 and Kingslayer priority 2 unless fresh exact source evidence closes their first missing chains.
- Modify `C:\Users\darbo\Documents\HSConfig\.agents\skills\hsconfig\SKILL.md`
  - Responsibility: keep installed-skill operator guidance aligned after runtime apply boundary changes.

## Task 1: Runtime Apply Public API Fail-Closed

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\runtime_apply.py`
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_runtime_apply.py`

**Interfaces:**
- Consumes: `hsconfig.apply_gate.evaluate_apply_gate(package_root: str | Path, *, allow_source_informed: bool = False) -> dict[str, Any]`
- Produces: `apply_package(..., allow_source_informed: bool = False, apply_gate: dict[str, Any] | None = None) -> dict[str, Any]`
- Produces: `_resolve_allowed_apply_gate(package: Path, apply_gate: dict[str, Any] | None, allow_source_informed: bool) -> dict[str, Any]`

- [ ] **Step 1: Write failing direct-bypass tests**

Add these tests near the top of `C:\Users\darbo\Documents\HSConfig\tests\test_runtime_apply.py`, after `_complete_package()`:

```python
def _raw_complete_package_without_operator_summary(tmp_path: Path) -> Path:
    package = tmp_path / "raw-package"
    deck = package / "CustomConfig" / "deck"
    write_json(deck / "GlobalValues.json", {"GameCardId": "GlobalValues"})
    write_json(
        deck / "Mulligan.json",
        {"GameCardId": "Mulligan", "Mulligan": {"values": []}},
    )
    write_json(
        deck / "EX1_001.json",
        {"GameCardId": "EX1_001", "InHandPlayPriority": {"values": []}},
    )
    write_json(
        package / "reports" / "input_manifest.json",
        {"deck_name": "Gate Deck", "deck_code": "fixture", "runtime_root": "unused"},
    )
    return package


def test_apply_package_blocks_direct_write_without_operator_summary(tmp_path: Path):
    package = _raw_complete_package_without_operator_summary(tmp_path)
    runtime = tmp_path / "runtime"

    with pytest.raises(ValueError, match="Runtime apply requires an allowed apply gate"):
        apply_package(package_root=package, runtime_root=runtime)

    assert not (runtime / "CustomConfig" / "deck").exists()


def test_apply_package_rejects_forged_allowed_gate_without_operator_summary_path(
    tmp_path: Path,
):
    package = _complete_package(
        tmp_path,
        semantic_status="SOURCE_BACKED_STRONG",
        next_action="READY_TO_APPLY_OR_HANDOFF",
        apply_policy="ALLOWED",
    )
    runtime = tmp_path / "runtime"

    with pytest.raises(ValueError, match="Runtime apply requires an allowed apply gate"):
        apply_package(
            package_root=package,
            runtime_root=runtime,
            apply_gate={"status": "allowed", "mode": "source_backed_strong"},
        )

    assert not (runtime / "CustomConfig" / "deck").exists()


def test_apply_package_direct_source_informed_requires_explicit_flag(tmp_path: Path):
    package = _complete_package(
        tmp_path,
        semantic_status="VALID_BUT_NOT_GUIDE_STRONG",
        next_action="SOURCE_INFORMED_APPLY_READY",
        apply_policy="ALLOWED_SOURCE_INFORMED",
        source_informed_apply_readiness={
            "status": "ready",
            "requires_flag": "--allow-source-informed",
            "source_gap_count": 1,
        },
    )
    runtime = tmp_path / "runtime"

    with pytest.raises(ValueError, match="Runtime apply requires an allowed apply gate"):
        apply_package(package_root=package, runtime_root=runtime)

    receipt = apply_package(
        package_root=package,
        runtime_root=runtime,
        allow_source_informed=True,
    )

    assert receipt["status"] == "applied"
    assert receipt["apply_gate"]["mode"] == "source_informed_apply_ready"
    assert (runtime / "CustomConfig" / "deck" / "GlobalValues.json").exists()
```

- [ ] **Step 2: Run tests and verify the new tests fail**

Run:

```powershell
python -m pytest tests\test_runtime_apply.py::test_apply_package_blocks_direct_write_without_operator_summary tests\test_runtime_apply.py::test_apply_package_rejects_forged_allowed_gate_without_operator_summary_path tests\test_runtime_apply.py::test_apply_package_direct_source_informed_requires_explicit_flag -q
```

Expected: at least the first two tests fail because `apply_package()` currently writes without resolving the operator gate and accepts a forged gate dictionary.

- [ ] **Step 3: Implement gate resolution in `runtime_apply.py`**

Modify the imports at the top of `C:\Users\darbo\Documents\HSConfig\src\hsconfig\runtime_apply.py`:

```python
from hsconfig.apply_gate import evaluate_apply_gate
```

Modify the `apply_package()` signature:

```python
def apply_package(
    *,
    package_root: str | Path,
    runtime_root: str | Path,
    config_dir: str | None = None,
    replace: bool = True,
    fake_receipt: dict[str, Any] | None = None,
    apply_gate: dict[str, Any] | None = None,
    allow_source_informed: bool = False,
    write_history: bool = True,
) -> dict[str, Any]:
```

Immediately after `package = Path(package_root)` and `runtime = Path(runtime_root)`, add:

```python
    resolved_apply_gate = _resolve_allowed_apply_gate(
        package=package,
        apply_gate=apply_gate,
        allow_source_informed=allow_source_informed,
    )
```

In the generated fake receipt branch, replace:

```python
            apply_gate=apply_gate,
```

with:

```python
            apply_gate=resolved_apply_gate,
```

Before `write_json(package / "reports" / "runtime_apply_receipt.json", receipt)`, add:

```python
        receipt["apply_gate"] = resolved_apply_gate
```

Add these helpers above `_snapshot_existing_runtime_target()`:

```python
def _resolve_allowed_apply_gate(
    *,
    package: Path,
    apply_gate: dict[str, Any] | None,
    allow_source_informed: bool,
) -> dict[str, Any]:
    resolved = apply_gate
    if resolved is None:
        resolved = evaluate_apply_gate(
            package,
            allow_source_informed=allow_source_informed,
        )
    if not _is_allowed_gate_for_package(package=package, apply_gate=resolved):
        reason = _first_gate_reason(resolved)
        raise ValueError(
            "Runtime apply requires an allowed apply gate from "
            f"reports/operator_summary.json; got {reason}"
        )
    return resolved


def _is_allowed_gate_for_package(
    *,
    package: Path,
    apply_gate: dict[str, Any] | None,
) -> bool:
    if not isinstance(apply_gate, dict):
        return False
    if apply_gate.get("status") != "allowed":
        return False
    operator_summary_path = apply_gate.get("operator_summary_path")
    if not operator_summary_path:
        return False
    expected = package / "reports" / "operator_summary.json"
    try:
        return Path(str(operator_summary_path)).resolve() == expected.resolve()
    except OSError:
        return False


def _first_gate_reason(apply_gate: dict[str, Any] | None) -> str:
    if not isinstance(apply_gate, dict):
        return "missing_apply_gate"
    reasons = apply_gate.get("reasons")
    if isinstance(reasons, list) and reasons:
        first = reasons[0]
        if isinstance(first, dict):
            return str(first.get("reason", "blocked"))
        return str(first)
    status = apply_gate.get("status", "missing_apply_gate")
    mode = apply_gate.get("mode", "")
    return f"{status}:{mode}" if mode else str(status)
```

- [ ] **Step 4: Update existing direct-runtime tests to pass through the real gate**

For tests in `C:\Users\darbo\Documents\HSConfig\tests\test_runtime_apply.py` that call `apply_package()` with packages created by `_complete_package()`, no change is needed when the package is `SOURCE_BACKED_STRONG`; `apply_package()` now evaluates the gate itself.

For tests that call `apply_package()` on hand-built packages without `reports/operator_summary.json`, either convert them to use `_complete_package()` or add the exact required reports. For `test_apply_package_replaces_only_target_deck_folder`, replace the manual package setup with:

```python
    package = _complete_package(
        tmp_path,
        semantic_status="SOURCE_BACKED_STRONG",
        next_action="READY_TO_APPLY_OR_HANDOFF",
        apply_policy="ALLOWED",
    )
```

Then keep the existing runtime setup and assertions.

For `test_apply_package_updates_bom_deck_config_without_duplicate_configs_section`, keep the custom `shadowpriest` deck folder but add these reports before calling `apply_package()`:

```python
    write_json(
        package / "reports" / "operator_summary.json",
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "SOURCE_BACKED_STRONG",
            "next_action": "READY_TO_APPLY_OR_HANDOFF",
            "apply_policy": "ALLOWED",
            "semantic_blockers": [],
            "generated_files": [
                "CustomConfig\\shadowpriest\\GlobalValues.json",
                "CustomConfig\\shadowpriest\\Mulligan.json",
                "CustomConfig\\shadowpriest\\EX1_001.json",
            ],
        },
    )
```

For `test_apply_package_rejects_manifest_deck_name_that_breaks_ini_mapping`, add an allowed operator summary before the `with pytest.raises(...)` block so the test continues to validate the unsafe deck name rather than the missing gate.

- [ ] **Step 5: Run the focused runtime apply suite**

Run:

```powershell
python -m pytest tests\test_runtime_apply.py tests\test_runtime_apply_receipts.py tests\test_apply_gate.py -q
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit Task 1**

Run:

```powershell
git add src\hsconfig\runtime_apply.py tests\test_runtime_apply.py
git commit -m "fix: gate direct runtime apply writes"
```

## Task 2: Preserve CLI Behavior With Real Gate Payloads

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\commands\apply.py`
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_runtime_apply.py`

**Interfaces:**
- Consumes: `apply_package(..., apply_gate=apply_gate, allow_source_informed=False) -> dict[str, Any]`
- Produces: unchanged CLI JSON statuses: `fake_apply_ready`, `blocked`, `applied`

- [ ] **Step 1: Add a regression test that CLI source-informed apply carries the evaluated gate into the final receipt**

Add to `C:\Users\darbo\Documents\HSConfig\tests\test_runtime_apply.py` after `test_apply_cli_allows_source_informed_apply_ready_only_with_explicit_escape_hatch`:

```python
def test_apply_cli_source_informed_receipt_contains_real_operator_gate(
    tmp_path: Path,
    capsys,
):
    from hsconfig.cli import main

    package = _complete_package(
        tmp_path,
        semantic_status="VALID_BUT_NOT_GUIDE_STRONG",
        next_action="SOURCE_INFORMED_APPLY_READY",
        apply_policy="ALLOWED_SOURCE_INFORMED",
        source_informed_apply_readiness={
            "status": "ready",
            "requires_flag": "--allow-source-informed",
            "source_gap_count": 1,
        },
    )
    runtime = tmp_path / "runtime"

    code = main(
        [
            "apply",
            "--package",
            str(package),
            "--runtime-root",
            str(runtime),
            "--allow-source-informed",
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    receipt = json.loads(
        (package / "reports" / "runtime_apply_receipt.json").read_text(
            encoding="utf-8"
        )
    )

    assert code == 0
    assert payload["status"] == "applied"
    assert payload["apply_gate"]["mode"] == "source_informed_apply_ready"
    assert receipt["apply_gate"] == payload["apply_gate"]
    assert receipt["apply_gate"]["operator_summary_path"].endswith(
        "reports\\operator_summary.json"
    ) or receipt["apply_gate"]["operator_summary_path"].endswith(
        "reports/operator_summary.json"
    )
```

- [ ] **Step 2: Run test before implementation**

Run:

```powershell
python -m pytest tests\test_runtime_apply.py::test_apply_cli_source_informed_receipt_contains_real_operator_gate -q
```

Expected: fail until Task 1's receipt stores `apply_gate`, or pass if Task 1 already stores it. A pass here means this task only verifies CLI preservation.

- [ ] **Step 3: Keep `commands/apply.py` unchanged unless the test shows a real mismatch**

If the test fails because `apply_payload()` does not pass the evaluated gate to `apply_package()`, ensure this call remains:

```python
    receipt = apply_package(
        package_root=package,
        runtime_root=args.runtime_root,
        fake_receipt=fake_receipt,
        apply_gate=apply_gate,
    )
```

If the call already matches this shape, do not edit `commands/apply.py`.

- [ ] **Step 4: Run CLI apply tests**

Run:

```powershell
python -m pytest tests\test_runtime_apply.py::test_apply_cli_blocks_valid_but_not_guide_strong_package_by_default tests\test_runtime_apply.py::test_apply_cli_allows_source_informed_apply_ready_only_with_explicit_escape_hatch tests\test_runtime_apply.py::test_apply_cli_source_informed_receipt_contains_real_operator_gate -q
```

Expected: all three tests pass.

- [ ] **Step 5: Commit Task 2**

Run:

```powershell
git add src\hsconfig\commands\apply.py tests\test_runtime_apply.py
git commit -m "test: preserve cli apply gate receipts"
```

If `src\hsconfig\commands\apply.py` did not change, omit it from `git add`.

## Task 3: Source-Informed Closure Contract For Boarlock And Kingslayer

**Files:**
- Create: `C:\Users\darbo\Documents\HSConfig\tests\test_source_informed_closure_contract.py`
- No production file should be modified unless this test exposes a stale matrix or report contract.

**Interfaces:**
- Consumes: `tests.helpers.fixture_prepare.load_archetype_matrix() -> list[dict[str, Any]]`
- Consumes: `tests.helpers.fixture_prepare.prepare_fixture_deck(tmp_path: Path, deck: dict[str, Any]) -> dict[str, Any]`
- Produces: a single fixture-level proof that Boarlock and Kingslayer stay visible and do not widen the matrix.

- [ ] **Step 1: Create the closure contract test**

Create `C:\Users\darbo\Documents\HSConfig\tests\test_source_informed_closure_contract.py`:

```python
from __future__ import annotations

import json

import pytest

from tests.helpers.fixture_prepare import load_archetype_matrix, prepare_fixture_deck


TARGETS = {
    "Boarlock": {
        "first_card_id": "WW_092",
        "first_card_name": "Fracking",
        "expected_runtime_surfaces": {
            "GlobalValues.json",
            "Mulligan.json",
            "Combo.json",
        },
        "forbidden_surfaces": {"Presume.json", "Concede.json"},
    },
    "Kingslayer": {
        "first_card_id": "DEEP_014",
        "first_card_name": "Quick Pick",
        "expected_runtime_surfaces": {
            "GlobalValues.json",
            "Mulligan.json",
        },
        "forbidden_surfaces": {"Presume.json", "Concede.json", "Combo.json"},
    },
}


@pytest.mark.parametrize("deck_name", ["Boarlock", "Kingslayer"])
def test_source_informed_rows_expose_first_missing_chain_without_apply_ready(
    tmp_path,
    monkeypatch,
    deck_name: str,
):
    monkeypatch.setattr(
        "hsconfig.package_builder.fetch_latest_cards", lambda timeout=10.0: []
    )
    deck = next(row for row in load_archetype_matrix() if row["deck_name"] == deck_name)

    result = prepare_fixture_deck(tmp_path, deck)
    operator = result["operator"]
    gap_report = result["source_claim_gap_report"]
    promotion = result["strong_promotion_report"]
    deck_identity = json.loads(
        (result["out"] / "reports" / "deck_identity.json").read_text(encoding="utf-8")
    )
    generated = set(result["generated_files"])
    target = TARGETS[deck_name]

    assert result["exit_code"] == 0
    assert operator["technical_status"] == "VALID_PACKAGE"
    assert operator["semantic_status"] == "VALID_BUT_NOT_GUIDE_STRONG"
    assert operator["next_action"] == "IMPROVE_GUIDE_SOURCES_BEFORE_STRONG_APPLY"
    assert operator["source_informed_apply_readiness"]["status"] == "blocked"
    assert promotion["promotion_ready"] is False

    first_chain = gap_report["summary"]["first_missing_chain"]
    assert first_chain["card_id"] == target["first_card_id"]
    assert first_chain["name"] == target["first_card_name"]
    assert first_chain["first_missing_link"] == "needs_mulligan_claim"
    assert first_chain["next_action"] == "add_mulligan_keep_or_discard_claim"

    card_surfaces = {f"{card['card_id']}.json" for card in deck_identity["cards"]}
    assert target["expected_runtime_surfaces"] <= generated
    assert generated <= card_surfaces | target["expected_runtime_surfaces"]
    assert not (target["forbidden_surfaces"] & generated)


def test_representative_matrix_remains_eleven_rows():
    matrix = load_archetype_matrix()
    names = [row["deck_name"] for row in matrix]

    assert len(matrix) == 11
    assert names.count("Boarlock") == 1
    assert names.count("Kingslayer") == 1
    assert names.count("CuteWarrior") == 0
```

- [ ] **Step 2: Run the new contract test**

Run:

```powershell
python -m pytest tests\test_source_informed_closure_contract.py -q
```

Expected: pass if the current matrix and reports are aligned. If it fails, only fix the stale field that the assertion names; do not add new decks or weaken the first-missing-chain assertions.

- [ ] **Step 3: Run the existing matrix and closure tests**

Run:

```powershell
python -m pytest tests\test_archetype_fixture_matrix.py tests\test_matrix_visibility.py tests\test_matrix_current_truth.py tests\test_boarlock_closure_wave.py tests\test_source_depth_closure_index.py tests\test_source_informed_closure_contract.py -q
```

Expected: all selected tests pass.

- [ ] **Step 4: Commit Task 3**

Run:

```powershell
git add tests\test_source_informed_closure_contract.py
git commit -m "test: prove source informed closure targets"
```

## Task 4: Operator Docs And Skill Guidance Alignment

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\docs\operator\README.md`
- Modify: `C:\Users\darbo\Documents\HSConfig\docs\operator\source-backed-strong-closure.md`
- Modify: `C:\Users\darbo\Documents\HSConfig\.agents\skills\hsconfig\SKILL.md`

**Interfaces:**
- Consumes: Task 1 `apply_package()` fail-closed behavior.
- Produces: operator documentation that says the CLI and public Python API share the same gate.

- [ ] **Step 1: Update the operator guide Single Gate section**

In `C:\Users\darbo\Documents\HSConfig\docs\operator\README.md`, under `## Single Gate`, insert this paragraph after `Lower-level reports explain the gate. They do not grant independent apply permission.`:

```markdown
Direct Python runtime writes use the same gate. `hsconfig.runtime_apply.apply_package()` resolves `reports/operator_summary.json` through `evaluate_apply_gate()` before any runtime mutation and rejects forged or missing gate dictionaries. Use the CLI for normal operation; direct imports are test and integration surfaces, not a second permission model.
```

- [ ] **Step 2: Update source-backed closure wording**

In `C:\Users\darbo\Documents\HSConfig\docs\operator\source-backed-strong-closure.md`, under `## Current Source-Informed Closure Decisions`, add this sentence after the table:

```markdown
The next closure implementation target remains Boarlock because it is the only current representative row that proves exact `Combo.json` emission; Kingslayer remains the second source-informed closure target because its blocker stack is narrower.
```

- [ ] **Step 3: Update installed skill source guidance**

In `C:\Users\darbo\Documents\HSConfig\.agents\skills\hsconfig\SKILL.md`, find the runtime apply guidance and make sure it contains this exact rule:

```markdown
- Runtime apply is always governed by `reports/operator_summary.json`; `apply_package()` and `hsconfig apply` must reject missing, blocked, or forged apply gates before writing HearthRanger runtime files.
```

If there is no runtime apply guidance block, add the rule to the operator workflow section that mentions `operator_summary.json`.

- [ ] **Step 4: Run docs and skill tests**

Run:

```powershell
python -m pytest tests\test_skill_files.py tests\test_report_ownership.py tests\test_operator_guidance.py -q
```

Expected: all selected tests pass. If `tests\test_skill_files.py` expects exact text, update the assertion to include the new fail-closed gate rule.

- [ ] **Step 5: Sync installed skill**

Run:

```powershell
python scripts\sync_installed_skill.py
python scripts\sync_installed_skill.py --check
```

Expected: the second command prints that the installed HSConfig skill is in sync.

- [ ] **Step 6: Commit Task 4**

Run:

```powershell
git add docs\operator\README.md docs\operator\source-backed-strong-closure.md .agents\skills\hsconfig\SKILL.md C:\Users\darbo\.codex\skills\hsconfig\SKILL.md
git commit -m "docs: align apply gate operator guidance"
```

If the sync script changes additional installed-skill files, include them in the same commit.

## Task 5: Final Verification And Main Push

**Files:**
- No planned source edits.
- May modify only if verification exposes a concrete regression from Tasks 1-4.

**Interfaces:**
- Consumes: all previous task outputs.
- Produces: verified, committed, pushed `main`.

- [ ] **Step 1: Run focused gate and source-informed tests**

Run:

```powershell
python -m pytest tests\test_runtime_apply.py tests\test_runtime_apply_receipts.py tests\test_apply_gate.py tests\test_source_informed_closure_contract.py tests\test_boarlock_closure_wave.py tests\test_archetype_fixture_matrix.py tests\test_matrix_visibility.py tests\test_matrix_current_truth.py -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run full suite**

Run:

```powershell
python -m pytest -q
```

Expected: all tests pass with the existing skipped tests unchanged.

- [ ] **Step 3: Verify installed skill sync**

Run:

```powershell
python scripts\sync_installed_skill.py --check
```

Expected: installed skill is in sync.

- [ ] **Step 4: Verify old surface boundaries are still intact**

Run:

```powershell
rg -n "normal output includes Presume|normal output includes Concede|emit Presume.json|emit Concede.json" README.md docs .agents src tests
```

Expected: no active operator guidance claims that normal output includes or emits `Presume.json` or `Concede.json`. Test strings that assert forbidden phrases are acceptable only inside tests.

- [ ] **Step 5: Review git diff**

Run:

```powershell
git status --short --branch
git diff --stat
git diff -- src\hsconfig\runtime_apply.py src\hsconfig\commands\apply.py tests\test_runtime_apply.py tests\test_source_informed_closure_contract.py docs\operator\README.md docs\operator\source-backed-strong-closure.md .agents\skills\hsconfig\SKILL.md
```

Expected: only the planned files changed.

- [ ] **Step 6: Commit any final verification fixes**

If Task 5 produced fixes, run:

```powershell
git add <changed-files>
git commit -m "test: verify apply boundary closure"
```

If there are no final fixes, do not create an empty commit.

- [ ] **Step 7: Push `main`**

Run:

```powershell
git status --short --branch
git push origin main
```

Expected: local `main` is pushed to `origin/main`.

## Self-Review

- Spec coverage: The plan implements the recommended Option A: fail-closed runtime apply boundary, Boarlock/Kingslayer source-informed proof, no runtime-surface widening, no matrix widening, and docs/skill alignment.
- Placeholder scan: The plan contains no deferred placeholder instructions and no open-ended validation steps.
- Type consistency: New runtime helper signatures use `Path`, `dict[str, Any] | None`, and `bool`, matching existing module style. Tests call existing `apply_package()` and fixture helpers with the updated `allow_source_informed` parameter.
- Risk boundary: The plan does not force weak `Fracking` or `Quick Pick` claims; it preserves explicit stop conditions unless exact source evidence and lowering support close the chain.

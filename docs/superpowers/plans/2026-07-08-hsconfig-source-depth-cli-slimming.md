# HSConfig Source Depth Closure And CLI Slimming Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close or explicitly stabilize the remaining source-informed HSConfig fixture edges, then reduce CLI and research-documentation pressure without widening the pre-run CustomConfig skill.

**Architecture:** Keep HSConfig as a lean pre-run generator whose normal gate is `reports/operator_summary.json`. The implementation preserves the current VisionAI runtime surface set and 11-deck matrix, makes source-informed readiness more explicit, and turns existing command shim modules into real command owners so `hsconfig.cli` stops collecting unrelated behavior.

**Tech Stack:** Python 3.11, pytest, existing `hsconfig` package under `src/hsconfig`, HearthRanger VisionAI JSON surfaces, operator docs under `docs/operator`, Superpowers plans under `docs/superpowers/plans`, research evidence under `docs/research`.

## Global Constraints

- HSConfig remains pre-run only; do not add replay parsing, winrate analysis, runtime log analysis, candidate promotion, or post-game tuning.
- Normal runtime output remains limited to `GlobalValues.json`, `Mulligan.json`, per-card `<CARDID>.json`, and `Combo.json` only when a concrete valid combo exists.
- Do not emit `Presume.json` or `Concede.json` in the normal path.
- Do not widen `docs/operator/archetype-fixture-matrix.json` beyond the current 11 decks in this wave.
- Do not call `Kingslayer` or `Boarlock` `SOURCE_BACKED_STRONG` unless their generated `operator_summary.json`, `source_claim_gap_report.json`, and `strong_promotion_report.json` are all strong without hard blockers.
- Keep `--allow-source-informed` explicit; do not make source-informed apply the default.
- Preserve `reports/operator_summary.json` as the single normal apply gate.
- Keep generated runtime packages under `outputs/`, temporary test directories, or ignored local paths; do not commit generated runtime configs.
- No new runtime dependency is allowed in this wave.
- Public CLI command names and arguments must remain backward compatible.

---

## File Structure

- Create or modify `docs/research/README.md`: document that research folders are evidence, not operator instructions, and index the 2026-07-08 audit package.
- Preserve `docs/research/2026-07-08-hsconfig-final-skill-audit/`: commit the completed audit package or move it under the documented research index; do not leave it as untracked ambiguity.
- Modify `docs/operator/archetype-fixture-matrix.json`: keep 11 decks, make Kingslayer and Boarlock closure state explicit, and do not add new fixture rows.
- Modify `docs/operator/source-backed-strong-closure.md`: document the current source-informed closure decisions and the first missing link for Kingslayer and Boarlock.
- Modify `docs/operator/README.md`: keep the normal operator path short and point advanced readers to the closure doc and research index.
- Modify `tests/test_matrix_current_truth.py`: lock 11 rows, 9 core source-backed rows, 2 source-informed rows, stop-condition visibility, and no-widening guidance.
- Modify `tests/test_fixture_source_depth_closure.py`: verify source-informed rows expose either a ready source-informed path or a documented stop condition.
- Modify `tests/test_apply_gate.py`: keep source-informed apply blocked unless `SOURCE_INFORMED_APPLY_READY`, `ALLOWED_SOURCE_INFORMED`, and explicit `--allow-source-informed` agree.
- Modify `tests/test_operator_summary.py`: add a synthetic source-informed-ready summary case so the exception lane has a representative operator proof without widening the real matrix.
- Create `src/hsconfig/commands/common.py`: shared `emit_result` and `run_payload_command` helpers for command modules.
- Modify `src/hsconfig/commands/apply.py`: own apply and validate command execution instead of delegating to `hsconfig.cli`.
- Modify `src/hsconfig/commands/source_workflow.py`: own `source-manifest`, `draft-source-documents`, and `research-deck` command execution instead of delegating to `hsconfig.cli`.
- Modify `src/hsconfig/commands/prepare.py`: own `prepare` and `build` command execution by delegating to a package-builder module, not back to `hsconfig.cli`.
- Create `src/hsconfig/input_loading.py`: move card, claim, source-document, source-evidence, and fixture-row loaders out of `hsconfig.cli`.
- Create `src/hsconfig/package_builder.py`: move package construction and preconfig-context orchestration out of `hsconfig.cli`.
- Modify `src/hsconfig/cli.py`: keep only parser construction, top-level dispatch, and legacy import-compatible wrappers if tests still need them.
- Modify `tests/test_cli.py` and `tests/test_cli_help.py`: lock public behavior and assert command modules no longer import from `hsconfig.cli`.
- Modify `C:\Users\darbo\.codex\skills\hsconfig\SKILL.md` via the repo sync flow only if operator docs or workflow references change; do not hand-edit the installed skill without syncing from repo source.

---

## Task 1: Research Audit Ownership And Index

**Files:**
- Create: `docs/research/README.md`
- Modify: `tests/test_research_audit_schema.py`
- Keep: `docs/research/2026-07-08-hsconfig-final-skill-audit/fields.yaml`
- Keep: `docs/research/2026-07-08-hsconfig-final-skill-audit/outline.yaml`
- Keep: `docs/research/2026-07-08-hsconfig-final-skill-audit/results/*.json`

**Interfaces:**
- Consumes: completed audit JSON files in `docs/research/2026-07-08-hsconfig-final-skill-audit/results/`
- Produces: a documented research evidence index that operators know not to treat as command instructions

- [ ] **Step 1: Add failing research index test**

Append this test to `tests/test_research_audit_schema.py`:

```python
from pathlib import Path


def test_research_index_marks_research_as_evidence_not_operator_guidance():
    text = Path("docs/research/README.md").read_text(encoding="utf-8")

    assert "Research artifacts are evidence, not operator instructions." in text
    assert "2026-07-08-hsconfig-final-skill-audit" in text
    assert "docs/operator/README.md remains the normal operator entrypoint." in text
```

- [ ] **Step 2: Run the focused failing test**

Run:

```powershell
python -m pytest tests/test_research_audit_schema.py::test_research_index_marks_research_as_evidence_not_operator_guidance -q
```

Expected: FAIL because `docs/research/README.md` does not exist yet or does not contain the required wording.

- [ ] **Step 3: Create the research index**

Create `docs/research/README.md` with:

```markdown
# HSConfig Research Evidence

Research artifacts are evidence, not operator instructions.

The normal operator entrypoint is `docs/operator/README.md`. Research folders explain why a workflow, matrix row, or source-depth decision exists; they do not grant runtime apply permission and they do not replace `reports/operator_summary.json`.

## Active Research Packages

| Package | Purpose | Operator Implication |
| --- | --- | --- |
| `2026-07-08-hsconfig-final-skill-audit` | Audits lean operator scope, 11-deck source-depth truth, VisionAI runtime surfaces, every-card contract visibility, apply-gate safety, and maintainability. | Keep HSConfig pre-run only, close Kingslayer and Boarlock before widening the matrix, and slim `hsconfig.cli` without changing public CLI behavior. |
```

- [ ] **Step 4: Validate the audit JSON files**

Run:

```powershell
Get-ChildItem docs\research\2026-07-08-hsconfig-final-skill-audit\results -Filter *.json | ForEach-Object {
  python "$env:USERPROFILE\.codex\skills\research\validate_json.py" `
    -f docs\research\2026-07-08-hsconfig-final-skill-audit\fields.yaml `
    -j $_.FullName
}
```

Expected: each file reports `Validation passed`.

- [ ] **Step 5: Run the focused test**

Run:

```powershell
python -m pytest tests/test_research_audit_schema.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add docs/research/README.md docs/research/2026-07-08-hsconfig-final-skill-audit tests/test_research_audit_schema.py
git commit -m "docs: index hsconfig research audit evidence"
```

---

## Task 2: Source-Informed Matrix Closure Truth

**Files:**
- Modify: `docs/operator/archetype-fixture-matrix.json`
- Modify: `docs/operator/source-backed-strong-closure.md`
- Modify: `tests/test_matrix_current_truth.py`

**Interfaces:**
- Consumes: `strongness_visibility` entries in the 11-deck matrix
- Produces: stable current truth that Kingslayer and Boarlock are the only source-informed rows and that each row has a clear closure decision

- [ ] **Step 1: Add failing tests for exact matrix size and closure decisions**

Append these tests to `tests/test_matrix_current_truth.py`:

```python
def test_active_matrix_stays_at_eleven_representative_decks():
    rows = _matrix_rows()

    assert len(rows) == 11
    assert sum(row["fixture_stage"] == "core_source_backed_fixture" for row in rows) == 9
    assert sum(row["fixture_stage"] == "source_informed_valid_fixture" for row in rows) == 2


def test_source_informed_rows_have_explicit_closure_decisions():
    by_name = {row["deck_name"]: row for row in _matrix_rows()}

    kingslayer = by_name["Kingslayer"]["strongness_visibility"]
    assert kingslayer["first_strongness_gap"] == "needs_mulligan_claim_for_quick_pick"
    assert kingslayer["source_informed_apply_readiness"] == "blocked"
    assert kingslayer["operator_action"] in {
        "close_existing_source_informed_fixture",
        "preserve_source_informed_with_explicit_stop_condition",
    }

    boarlock = by_name["Boarlock"]["strongness_visibility"]
    assert boarlock["first_strongness_gap"] == "needs_mulligan_claim_for_fracking"
    assert boarlock["source_informed_apply_readiness"] == "blocked"
    assert boarlock["operator_action"] == "preserve_source_informed_with_explicit_stop_condition"
    assert boarlock["stop_condition"] == "exact_boarlock_fracking_mulligan_source_unavailable"
```

- [ ] **Step 2: Run the focused test**

Run:

```powershell
python -m pytest tests/test_matrix_current_truth.py -q
```

Expected: FAIL only if Kingslayer or Boarlock closure fields are missing, stale, or inconsistent.

- [ ] **Step 3: Update the matrix only if the tests expose a missing explicit field**

If `Kingslayer` is missing a closure decision, update only its `strongness_visibility` object in `docs/operator/archetype-fixture-matrix.json` to:

```json
"strongness_visibility": {
  "current_stage": "source_informed_valid_fixture",
  "first_strongness_gap": "needs_mulligan_claim_for_quick_pick",
  "source_informed_apply_readiness": "blocked",
  "source_informed_blocking_reasons": ["unsupported_conditions_present"],
  "closure_state": "source_informed_blocked",
  "closure_priority": 2,
  "operator_action": "close_existing_source_informed_fixture"
}
```

Do not add a `stop_condition` for Kingslayer in this task unless the source-research closure task below proves the exact Quick Pick mulligan source is unavailable.

- [ ] **Step 4: Update closure documentation**

In `docs/operator/source-backed-strong-closure.md`, ensure the current state contains these exact bullets:

```markdown
- `Kingslayer` remains a source-informed closure target. The first missing link is `DEEP_014:Quick Pick:needs_mulligan_claim`; it must either receive an exact mulligan source claim or be preserved with an explicit stop condition in a later closure pass.
- `Boarlock` remains source-informed with an explicit stop condition: `exact_boarlock_fracking_mulligan_source_unavailable`. Do not force a weak `Fracking` mulligan claim.
```

- [ ] **Step 5: Run matrix and closure tests**

Run:

```powershell
python -m pytest tests/test_matrix_current_truth.py tests/test_fixture_source_depth_closure.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add docs/operator/archetype-fixture-matrix.json docs/operator/source-backed-strong-closure.md tests/test_matrix_current_truth.py
git commit -m "docs: lock source-informed matrix closure truth"
```

---

## Task 3: Source-Informed Ready Lane Proof Without Matrix Widening

**Files:**
- Modify: `tests/test_operator_summary.py`
- Modify: `tests/test_apply_gate.py`
- Modify: `src/hsconfig/operator_summary.py` only if the new test exposes a behavior gap
- Modify: `src/hsconfig/apply_gate.py` only if the new test exposes a behavior gap

**Interfaces:**
- Consumes: `build_operator_summary(...)` and `evaluate_apply_gate(package, allow_source_informed: bool = False)`
- Produces: a synthetic proof that source-informed apply can be ready only for guide/mulligan source-depth gaps and only with the explicit flag

- [ ] **Step 1: Add synthetic operator summary readiness test**

Append this test to `tests/test_operator_summary.py`:

```python
def test_operator_summary_can_mark_source_informed_ready_for_source_depth_only_gap():
    summary = build_operator_summary(
        validation_report={"status": "passed", "errors": []},
        config_readiness_report={
            "summary": {
                "cards_need_guide_claims": 1,
                "cards_need_mulligan_claims": 1,
                "cards_need_runtime_surface": 0,
                "generic_low_confidence_cards": 0,
                "uncovered_cards": 0,
                "unsupported_conditions_present": 0,
                "combo_blockers": 0,
                "mechanic_blockers": 0,
                "conflict_blockers": 0,
            },
            "cards": [],
        },
        guide_source_depth_report={"depth_status": "source_informed"},
        source_claim_gap_report={
            "summary": {
                "blocked_cards": 2,
                "first_missing_chain": {
                    "card_id": "EXAMPLE_001",
                    "card_name": "Example Card",
                    "first_missing_link": "needs_mulligan_claim",
                    "next_action": "add_exact_mulligan_claim",
                },
            }
        },
        strong_promotion_report={"promotion_ready": False},
        generated_files=[
            "CustomConfig\\deck\\GlobalValues.json",
            "CustomConfig\\deck\\Mulligan.json",
            "CustomConfig\\deck\\EXAMPLE_001.json",
        ],
    )

    assert summary["technical_status"] == "VALID_PACKAGE"
    assert summary["semantic_status"] == "VALID_BUT_NOT_GUIDE_STRONG"
    assert summary["next_action"] == "SOURCE_INFORMED_APPLY_READY"
    assert summary["apply_policy"] == "ALLOWED_SOURCE_INFORMED"
    assert summary["source_informed_apply_readiness"]["status"] == "ready"
    assert summary["source_informed_apply_readiness"]["blocking_reasons"] == []
```

- [ ] **Step 2: Run the focused failing test**

Run:

```powershell
python -m pytest tests/test_operator_summary.py::test_operator_summary_can_mark_source_informed_ready_for_source_depth_only_gap -q
```

Expected: PASS if the path already works; otherwise FAIL on the precise summary field that needs alignment.

- [ ] **Step 3: If needed, align operator summary source-informed readiness**

If the test fails, update `src/hsconfig/operator_summary.py` so `SOURCE_INFORMED_APPLY_READY` is only emitted when all of these are true:

```python
allowed_source_depth_reasons = {
    "cards_need_guide_claims",
    "cards_need_mulligan_claims",
}
hard_blocker_reasons = {
    "cards_need_runtime_surface",
    "generic_low_confidence_cards",
    "uncovered_cards",
    "unsupported_conditions_present",
    "combo_blockers",
    "mechanic_blockers",
    "conflict_blockers",
}
```

The ready state must have:

```python
{
    "status": "ready",
    "requires_flag": "--allow-source-informed",
    "blocking_reasons": [],
}
```

The blocked state must include `blocking_reasons` derived from hard blockers.

- [ ] **Step 4: Keep apply gate explicit**

Run the existing apply-gate proof:

```powershell
python -m pytest tests/test_apply_gate.py::test_apply_gate_allows_source_informed_apply_ready_only_with_flag tests/test_apply_gate.py::test_apply_gate_blocks_source_informed_policy_when_readiness_is_not_ready -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add tests/test_operator_summary.py tests/test_apply_gate.py src/hsconfig/operator_summary.py src/hsconfig/apply_gate.py
git commit -m "test: prove source-informed apply readiness lane"
```

---

## Task 4: Common Command Execution Helper

**Files:**
- Create: `src/hsconfig/commands/common.py`
- Modify: `tests/test_cli.py`

**Interfaces:**
- Produces: `emit_result(payload: dict[str, Any], as_json: bool, code: int) -> int`
- Produces: `run_payload_command(args: argparse.Namespace, worker: Callable[[argparse.Namespace], tuple[dict[str, Any], int]]) -> int`
- Consumes: command worker functions returning `(payload, exit_code)`

- [ ] **Step 1: Add failing helper tests**

Append these tests to `tests/test_cli.py`:

```python
import argparse
import json

from hsconfig.commands.common import emit_result, run_payload_command


def test_command_common_emit_result_prints_json(capsys):
    code = emit_result({"status": "OK", "deck": "ShadowPriest"}, as_json=True, code=0)

    assert code == 0
    assert json.loads(capsys.readouterr().out) == {"deck": "ShadowPriest", "status": "OK"}


def test_command_common_run_payload_command_wraps_exceptions(capsys):
    def boom(args):
        raise ValueError("broken command")

    code = run_payload_command(argparse.Namespace(json=True), boom)

    assert code == 1
    assert json.loads(capsys.readouterr().out) == {
        "errors": ["broken command"],
        "status": "failed",
    }
```

- [ ] **Step 2: Run the focused failing tests**

Run:

```powershell
python -m pytest tests/test_cli.py::test_command_common_emit_result_prints_json tests/test_cli.py::test_command_common_run_payload_command_wraps_exceptions -q
```

Expected: FAIL because `hsconfig.commands.common` does not exist.

- [ ] **Step 3: Implement command helper**

Create `src/hsconfig/commands/common.py`:

```python
from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from typing import Any


PayloadWorker = Callable[[argparse.Namespace], tuple[dict[str, Any], int]]


def emit_result(payload: dict[str, Any], as_json: bool, code: int) -> int:
    if as_json:
        print(json.dumps(payload, sort_keys=True))
    else:
        print(json.dumps(payload, indent=2, sort_keys=True))
    return code


def run_payload_command(args: argparse.Namespace, worker: PayloadWorker) -> int:
    try:
        payload, code = worker(args)
    except Exception as exc:
        payload, code = {"status": "failed", "errors": [str(exc)]}, 1
    return emit_result(payload, bool(getattr(args, "json", False)), code)
```

- [ ] **Step 4: Run the helper tests**

Run:

```powershell
python -m pytest tests/test_cli.py::test_command_common_emit_result_prints_json tests/test_cli.py::test_command_common_run_payload_command_wraps_exceptions -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/hsconfig/commands/common.py tests/test_cli.py
git commit -m "refactor: add common command execution helper"
```

---

## Task 5: Apply And Validate Command Ownership

**Files:**
- Modify: `src/hsconfig/commands/apply.py`
- Create: `src/hsconfig/package_io.py`
- Modify: `src/hsconfig/cli.py`
- Modify: `tests/test_cli.py`
- Modify: `tests/test_apply_gate.py`

**Interfaces:**
- Produces: `read_optional_profile(package: Path) -> dict[str, Any] | None`
- Produces: `read_required_baseline(package: Path) -> dict[str, Any]`
- Produces: `validate_payload(args: argparse.Namespace) -> tuple[dict[str, Any], int]`
- Produces: `apply_payload(args: argparse.Namespace) -> tuple[dict[str, Any], int]`
- Keeps: `run_apply_command(args: argparse.Namespace) -> int`

- [ ] **Step 1: Add failing import-boundary test**

Append this test to `tests/test_cli.py`:

```python
from pathlib import Path


def test_apply_command_module_no_longer_imports_hsconfig_cli():
    text = Path("src/hsconfig/commands/apply.py").read_text(encoding="utf-8")

    assert "from hsconfig.cli import" not in text
```

- [ ] **Step 2: Run the focused failing test**

Run:

```powershell
python -m pytest tests/test_cli.py::test_apply_command_module_no_longer_imports_hsconfig_cli -q
```

Expected: FAIL because `commands/apply.py` currently delegates back to `hsconfig.cli`.

- [ ] **Step 3: Move package readers**

Create `src/hsconfig/package_io.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any

from hsconfig.io import read_json


def read_optional_profile(package: Path) -> dict[str, Any] | None:
    profile_path = package / "reports" / "globalvalues_profile.json"
    if not profile_path.exists():
        return None
    profile = read_json(profile_path)
    if not isinstance(profile, dict):
        raise ValueError(f"GlobalValues profile must be an object: {profile_path}")
    return profile


def read_required_baseline(package: Path) -> dict[str, Any]:
    baseline_path = package / "reports" / "globalvalues_baseline.json"
    if not baseline_path.exists():
        raise ValueError(f"Missing GlobalValues baseline report: {baseline_path}")
    baseline = read_json(baseline_path)
    if not isinstance(baseline, dict):
        raise ValueError(f"GlobalValues baseline must be an object: {baseline_path}")
    return baseline
```

- [ ] **Step 4: Implement apply command ownership**

Replace `src/hsconfig/commands/apply.py` with:

```python
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from hsconfig.apply_gate import evaluate_apply_gate
from hsconfig.commands.common import run_payload_command
from hsconfig.package_io import read_optional_profile, read_required_baseline
from hsconfig.runtime_apply import apply_package
from hsconfig.validate_package import validate_config_package


def run_apply_command(args: argparse.Namespace) -> int:
    return run_payload_command(args, apply_payload)


def run_validate_command(args: argparse.Namespace) -> int:
    return run_payload_command(args, validate_payload)


def validate_payload(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    package = Path(args.package)
    if not package.exists():
        return {"status": "failed", "errors": [f"Package not found: {package}"], "checked_files": 0}, 1
    baseline = read_required_baseline(package)
    profile = read_optional_profile(package)
    report = validate_config_package(
        package,
        globalvalues_baseline=baseline,
        globalvalues_profile=profile,
        require_complete_package=True,
        require_globalvalues_profile=True,
    )
    return report, 0 if report["status"] == "passed" else 1


def apply_payload(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    package = Path(args.package)
    if not package.exists():
        return {"status": "failed", "errors": [f"Package not found: {package}"]}, 1

    baseline = read_required_baseline(package)
    profile = read_optional_profile(package)
    report = validate_config_package(
        package,
        globalvalues_baseline=baseline,
        globalvalues_profile=profile,
        require_complete_package=True,
        require_globalvalues_profile=True,
    )
    if report["status"] != "passed":
        return {"status": "failed", "errors": report["errors"], "validation_report": report}, 1

    apply_gate = evaluate_apply_gate(
        package,
        allow_source_informed=bool(getattr(args, "allow_source_informed", False)),
    )
    if apply_gate["status"] != "allowed":
        return {
            "status": "blocked",
            "errors": ["Operator summary does not allow runtime apply."],
            "validation_report": report,
            "apply_gate": apply_gate,
        }, 1

    receipt = apply_package(package_root=package, runtime_root=args.runtime_root)
    return {"status": "applied", "apply_gate": apply_gate, "receipt": receipt}, 0
```

- [ ] **Step 5: Update CLI dispatch**

In `src/hsconfig/cli.py`, import `run_validate_command`:

```python
from hsconfig.commands.apply import run_apply_command, run_validate_command
```

Then update `main` so validate uses the command module:

```python
    if args.command == "validate":
        return run_validate_command(args)
```

Remove `_validate`, `_apply`, `_read_optional_profile`, and `_read_required_baseline` from `src/hsconfig/cli.py` after the imports are updated. Keep public behavior unchanged.

- [ ] **Step 6: Run apply/validate tests**

Run:

```powershell
python -m pytest tests/test_apply_gate.py tests/test_runtime_apply.py tests/test_cli.py::test_apply_command_module_no_longer_imports_hsconfig_cli -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add src/hsconfig/commands/apply.py src/hsconfig/package_io.py src/hsconfig/cli.py tests/test_cli.py tests/test_apply_gate.py
git commit -m "refactor: move apply and validate command ownership"
```

---

## Task 6: Shared Input Loading Extraction

**Files:**
- Create: `src/hsconfig/input_loading.py`
- Modify: `src/hsconfig/cli.py`
- Modify: `tests/test_cli.py`

**Interfaces:**
- Produces: `load_cards(cards_json: str | None, *, deck_name: str, deck_code: str, allow_placeholder: bool = False) -> dict[str, Any]`
- Produces: `load_claims(claims_json: str | None) -> list[dict[str, Any]]`
- Produces: `load_guide_sources(guide_sources_json: str | None) -> list[dict[str, Any]]`
- Produces: `load_source_documents(source_documents_json: str | None) -> list[dict[str, Any]]`
- Produces: `load_source_evidence(source_evidence_json: str | None) -> list[dict[str, Any]]`
- Produces: `fixture_row_for(deck_name: str) -> dict[str, Any] | None`
- Produces: `source_records_from_cards(cards: list[dict[str, Any]]) -> dict[str, dict[str, Any]]`

- [ ] **Step 1: Add failing boundary test**

Append this test to `tests/test_cli.py`:

```python
def test_cli_no_longer_owns_input_loading_helpers():
    text = Path("src/hsconfig/cli.py").read_text(encoding="utf-8")

    assert "def _load_cards(" not in text
    assert "def _load_claims(" not in text
    assert "def _load_guide_sources(" not in text
    assert "def _load_source_documents(" not in text
    assert "def _load_source_evidence(" not in text
    assert "def _fixture_row_for(" not in text
```

- [ ] **Step 2: Run the focused failing test**

Run:

```powershell
python -m pytest tests/test_cli.py::test_cli_no_longer_owns_input_loading_helpers -q
```

Expected: FAIL because these helpers still live in `hsconfig.cli`.

- [ ] **Step 3: Create input loading module**

Move the existing helper bodies from `src/hsconfig/cli.py` into `src/hsconfig/input_loading.py` and rename them without leading underscores. The top of the new module must be:

```python
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from hsconfig.deckstring_decode import decode_deck_code
from hsconfig.io import read_json

LEGACY_CLAIMS_RETRIEVED_AT = "1970-01-01T00:00:00Z"
```

The moved functions must be named:

```python
load_cards
load_claims
load_guide_sources
load_source_documents
load_source_evidence
fixture_row_for
guide_documents_from_legacy_claims
source_records_from_cards
```

Private helper names may remain private inside `input_loading.py`:

```python
_placeholder_cards
_normalize_card_input
_legacy_claim_retrieved_at
_legacy_claim_to_guide_claim
_legacy_claim_confidence
_legacy_stance
```

- [ ] **Step 4: Update imports and call sites**

In `src/hsconfig/cli.py`, replace calls:

```python
_load_cards -> load_cards
_load_claims -> load_claims
_load_guide_sources -> load_guide_sources
_load_source_documents -> load_source_documents
_load_source_evidence -> load_source_evidence
_fixture_row_for -> fixture_row_for
_guide_documents_from_legacy_claims -> guide_documents_from_legacy_claims
_source_records_from_cards -> source_records_from_cards
```

Import these functions from `hsconfig.input_loading`.

- [ ] **Step 5: Run input and CLI tests**

Run:

```powershell
python -m pytest tests/test_cli.py tests/test_source_manifest_cli.py tests/test_draft_source_documents_cli.py tests/test_research_deck_cli.py tests/test_prepare_cli.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add src/hsconfig/input_loading.py src/hsconfig/cli.py tests/test_cli.py
git commit -m "refactor: extract CLI input loading helpers"
```

---

## Task 7: Source Workflow Command Ownership

**Files:**
- Modify: `src/hsconfig/commands/source_workflow.py`
- Modify: `src/hsconfig/cli.py`
- Modify: `tests/test_cli.py`
- Modify: `tests/test_source_manifest_cli.py`
- Modify: `tests/test_draft_source_documents_cli.py`
- Modify: `tests/test_research_deck_cli.py`

**Interfaces:**
- Keeps: `run_source_manifest_command(args: argparse.Namespace) -> int`
- Keeps: `run_draft_source_documents_command(args: argparse.Namespace) -> int`
- Keeps: `run_research_deck_command(args: argparse.Namespace) -> int`
- Produces: `prepare_research_output_dir(out: Path) -> None`

- [ ] **Step 1: Add failing command-boundary test**

Append this test to `tests/test_cli.py`:

```python
def test_source_workflow_command_module_no_longer_imports_hsconfig_cli():
    text = Path("src/hsconfig/commands/source_workflow.py").read_text(encoding="utf-8")

    assert "from hsconfig.cli import" not in text
```

- [ ] **Step 2: Run the focused failing test**

Run:

```powershell
python -m pytest tests/test_cli.py::test_source_workflow_command_module_no_longer_imports_hsconfig_cli -q
```

Expected: FAIL because `commands/source_workflow.py` currently delegates back to `hsconfig.cli`.

- [ ] **Step 3: Move source workflow payload functions**

Move these existing payload functions from `src/hsconfig/cli.py` into `src/hsconfig/commands/source_workflow.py`:

```python
_source_manifest
_draft_source_documents
_research_deck
_prepare_research_output_dir
```

Rename them in the command module to:

```python
source_manifest_payload
draft_source_documents_payload
research_deck_payload
prepare_research_output_dir
```

`source_workflow.py` must use `run_payload_command` from `hsconfig.commands.common`.

- [ ] **Step 4: Keep wrapper functions stable**

Ensure `src/hsconfig/commands/source_workflow.py` exposes:

```python
def run_source_manifest_command(args: argparse.Namespace) -> int:
    return run_payload_command(args, source_manifest_payload)


def run_draft_source_documents_command(args: argparse.Namespace) -> int:
    return run_payload_command(args, draft_source_documents_payload)


def run_research_deck_command(args: argparse.Namespace) -> int:
    return run_payload_command(args, research_deck_payload)
```

- [ ] **Step 5: Remove moved functions from CLI**

Delete `_source_manifest`, `_draft_source_documents`, `_research_deck`, and `_prepare_research_output_dir` from `src/hsconfig/cli.py`.

- [ ] **Step 6: Run source workflow tests**

Run:

```powershell
python -m pytest tests/test_source_manifest_cli.py tests/test_draft_source_documents_cli.py tests/test_research_deck_cli.py tests/test_cli.py::test_source_workflow_command_module_no_longer_imports_hsconfig_cli -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add src/hsconfig/commands/source_workflow.py src/hsconfig/cli.py tests/test_cli.py tests/test_source_manifest_cli.py tests/test_draft_source_documents_cli.py tests/test_research_deck_cli.py
git commit -m "refactor: move source workflow command ownership"
```

---

## Task 8: Prepare And Build Ownership

**Files:**
- Create: `src/hsconfig/package_builder.py`
- Modify: `src/hsconfig/commands/prepare.py`
- Modify: `src/hsconfig/cli.py`
- Modify: `tests/test_cli.py`
- Modify: `tests/test_prepare_cli.py`
- Modify: `tests/test_archetype_fixture_e2e.py`

**Interfaces:**
- Produces: `build_preconfig_context(args: argparse.Namespace) -> dict[str, Any]`
- Produces: `build_package_payload(args: argparse.Namespace) -> tuple[dict[str, Any], int]`
- Produces: `prepare_package_payload(args: argparse.Namespace) -> tuple[dict[str, Any], int]`
- Keeps: `run_prepare_command(args: argparse.Namespace, *, expert_mode: bool) -> int`

- [ ] **Step 1: Add failing prepare boundary test**

Append this test to `tests/test_cli.py`:

```python
def test_prepare_command_module_no_longer_imports_hsconfig_cli():
    text = Path("src/hsconfig/commands/prepare.py").read_text(encoding="utf-8")

    assert "from hsconfig.cli import" not in text


def test_cli_no_longer_owns_package_builder():
    text = Path("src/hsconfig/cli.py").read_text(encoding="utf-8")

    assert "def _build_preconfig_context(" not in text
    assert "def _prepare(" not in text
    assert "def _build(" not in text
```

- [ ] **Step 2: Run the focused failing tests**

Run:

```powershell
python -m pytest tests/test_cli.py::test_prepare_command_module_no_longer_imports_hsconfig_cli tests/test_cli.py::test_cli_no_longer_owns_package_builder -q
```

Expected: FAIL because `prepare.py` delegates back to `hsconfig.cli` and `cli.py` still owns package building.

- [ ] **Step 3: Create package builder module**

Move these existing functions from `src/hsconfig/cli.py` into `src/hsconfig/package_builder.py`:

```python
_build_preconfig_context
_prepare
_build
_research_required_guide_sources
_generated_package_files
_reset_generated_package_dirs
_research_contract
_card_behavior_identity_links
_read_plan_report
```

Rename the public payload functions to:

```python
build_preconfig_context
prepare_package_payload
build_package_payload
research_contract_payload
```

Keep these helper names private in `package_builder.py`:

```python
_research_required_guide_sources
_generated_package_files
_reset_generated_package_dirs
_card_behavior_identity_links
_read_plan_report
```

- [ ] **Step 4: Update prepare command module**

Replace `src/hsconfig/commands/prepare.py` with:

```python
from __future__ import annotations

import argparse

from hsconfig.commands.common import run_payload_command
from hsconfig.package_builder import build_package_payload, prepare_package_payload


def run_prepare_command(args: argparse.Namespace, *, expert_mode: bool) -> int:
    worker = build_package_payload if expert_mode else prepare_package_payload
    return run_payload_command(args, worker)
```

- [ ] **Step 5: Update CLI research-contract dispatch**

In `src/hsconfig/cli.py`, import:

```python
from hsconfig.package_builder import research_contract_payload
from hsconfig.commands.common import run_payload_command
```

Then change `main` for `research-contract`:

```python
    if args.command == "research-contract":
        return run_payload_command(args, research_contract_payload)
```

Remove moved package-building functions from `src/hsconfig/cli.py`.

- [ ] **Step 6: Run package build tests**

Run:

```powershell
python -m pytest tests/test_prepare_cli.py tests/test_research_contract.py tests/test_archetype_fixture_e2e.py tests/test_multideck_source_backed_e2e.py -q
```

Expected: PASS.

- [ ] **Step 7: Run CLI size sanity check**

Run:

```powershell
(Get-Content src\hsconfig\cli.py | Measure-Object -Line).Lines
```

Expected: below `450`. If the count is above `450`, inspect remaining helper functions and move only helpers that are directly used by extracted command modules. Do not move parser construction out of `cli.py`.

- [ ] **Step 8: Commit**

```powershell
git add src/hsconfig/package_builder.py src/hsconfig/commands/prepare.py src/hsconfig/cli.py tests/test_cli.py tests/test_prepare_cli.py tests/test_archetype_fixture_e2e.py
git commit -m "refactor: move prepare and build package ownership"
```

---

## Task 9: Operator Docs And Skill Sync

**Files:**
- Modify: `docs/operator/README.md`
- Modify: `C:\Users\darbo\.codex\skills\hsconfig\SKILL.md` only through sync output if repo skill source changed
- Modify: `tests/test_operator_guidance.py`
- Modify: `tests/test_cli_help.py`

**Interfaces:**
- Consumes: current operator path and source-informed apply wording
- Produces: concise operator docs that keep normal path obvious and expert paths bounded

- [ ] **Step 1: Add operator guidance test**

Append this test to `tests/test_operator_guidance.py`:

```python
def test_operator_docs_point_to_research_index_without_making_it_operator_path():
    text = Path("docs/operator/README.md").read_text(encoding="utf-8")

    assert "Research artifacts are evidence, not operator instructions." in text
    assert "docs/research/README.md" in text
    assert "source-manifest -> draft-source-documents -> research-deck -> prepare -> apply" in text
```

- [ ] **Step 2: Run the focused failing test**

Run:

```powershell
python -m pytest tests/test_operator_guidance.py::test_operator_docs_point_to_research_index_without_making_it_operator_path -q
```

Expected: FAIL if the operator guide does not mention the research index yet.

- [ ] **Step 3: Update operator README**

Add this paragraph under the opening scope section in `docs/operator/README.md`:

```markdown
Research artifacts are evidence, not operator instructions. Use `docs/research/README.md` when auditing why a source-depth or fixture decision exists; return to this guide for the normal command path.
```

Do not add new normal commands.

- [ ] **Step 4: Confirm CLI help still names the same normal path**

Run:

```powershell
python -m pytest tests/test_cli_help.py tests/test_operator_guidance.py -q
```

Expected: PASS.

- [ ] **Step 5: Sync installed skill only if needed**

Run:

```powershell
python scripts\sync_installed_skill.py --check
```

Expected: `HSConfig skill is in sync`. If it fails because repo skill docs changed, run the repo's documented sync command, then re-run `--check`.

- [ ] **Step 6: Commit**

```powershell
git add docs/operator/README.md tests/test_operator_guidance.py tests/test_cli_help.py
git commit -m "docs: keep operator path concise after research audit"
```

---

## Task 10: Final Verification And Cleanup

**Files:**
- Verify all files changed by Tasks 1-9
- No new source file unless prior task requires it

**Interfaces:**
- Consumes: all previous task outputs
- Produces: a clean branch ready for push or merge

- [ ] **Step 1: Run focused source-depth and command tests**

Run:

```powershell
python -m pytest tests/test_matrix_current_truth.py tests/test_fixture_source_depth_closure.py tests/test_apply_gate.py tests/test_operator_summary.py tests/test_cli.py tests/test_cli_help.py -q
```

Expected: PASS.

- [ ] **Step 2: Run workflow tests**

Run:

```powershell
python -m pytest tests/test_source_manifest_cli.py tests/test_draft_source_documents_cli.py tests/test_research_deck_cli.py tests/test_prepare_cli.py tests/test_runtime_apply.py -q
```

Expected: PASS.

- [ ] **Step 3: Run fixture tests**

Run:

```powershell
python -m pytest tests/test_archetype_fixture_e2e.py tests/test_multideck_source_backed_e2e.py tests/test_boarlock_closure_wave.py tests/test_fixture_source_depth_closure.py -q
```

Expected: PASS.

- [ ] **Step 4: Run full test suite**

Run:

```powershell
python -m pytest -q
```

Expected: all tests pass. The current baseline is `498 passed, 2 skipped`; the final count may increase because this plan adds tests.

- [ ] **Step 5: Check installed skill sync**

Run:

```powershell
python scripts\sync_installed_skill.py --check
```

Expected: `HSConfig skill is in sync`.

- [ ] **Step 6: Check old scope terms stay bounded**

Run:

```powershell
rg -n "replay|winrate|post-game|Presume\\.json|Concede\\.json" README.md docs src tests
```

Expected: matches are limited to negative-scope statements, tests that block optional surfaces, or docs explaining that those concerns are outside HSConfig normal path.

- [ ] **Step 7: Check CLI size reduction**

Run:

```powershell
(Get-Content src\hsconfig\cli.py | Measure-Object -Line).Lines
```

Expected: below `450`.

- [ ] **Step 8: Check git status**

Run:

```powershell
git status --short --branch
```

Expected: branch is ahead of `origin/main` only by intentional commits and has no unstaged changes.

- [ ] **Step 9: Final commit if any verification-only files changed**

If only verification documentation changed after previous commits:

```powershell
git add docs tests src
git commit -m "test: verify hsconfig closure and cli slimming"
```

Skip this commit if `git status --short` is clean.

---

## Self-Review Checklist

- [ ] The plan keeps HSConfig pre-run only.
- [ ] The plan does not add replay, winrate, log parsing, candidate promotion, or post-game tuning.
- [ ] The plan does not add new decks to the 11-deck matrix.
- [ ] The plan does not emit `Presume.json` or `Concede.json`.
- [ ] The plan keeps `operator_summary.json` as the normal apply gate.
- [ ] The plan keeps source-informed apply behind `--allow-source-informed`.
- [ ] The plan closes or stabilizes Kingslayer and Boarlock without pretending weak claims are strong.
- [ ] The plan reduces `hsconfig.cli` responsibility without changing public CLI behavior.
- [ ] Every task has a focused test command and expected result.
- [ ] The final verification includes full tests, skill sync, CLI size, scope-term scan, and git status.

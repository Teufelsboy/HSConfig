# HSConfig Closure Lean Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close or explicitly stabilize the two remaining source-informed matrix rows, then reduce HSConfig's CLI and documentation pressure without widening the pre-run skill scope.

**Architecture:** Reuse the existing HSConfig control plane: `archetype-fixture-matrix.json`, `matrix_visibility`, `source_depth_closure_index`, `operator_summary.json`, and `apply_gate.py` remain the authorities. The implementation adds clearer blocker ownership, report ownership, and smaller command-handler boundaries while keeping runtime output limited to the current supported HearthRanger VisionAI files.

**Tech Stack:** Python 3.11, pytest, existing `hsconfig` package under `src/hsconfig`, operator docs under `docs/operator`, installed skill source under `.agents/skills/hsconfig`.

## Global Constraints

- HSConfig remains pre-run only; do not add replay parsing, winrate analysis, runtime log analysis, candidate promotion, or post-game tuning.
- Normal runtime output remains limited to `GlobalValues.json`, `Mulligan.json`, per-card `<CARDID>.json`, and `Combo.json` only when a concrete valid combo exists.
- Do not emit `Presume.json` or `Concede.json` in the normal path.
- Do not widen the representative matrix beyond the current 11 decks in this wave.
- Do not call `Kingslayer` or `Boarlock` `SOURCE_BACKED_STRONG` unless their own operator summaries, source gap reports, and promotion reports become strong without hard blockers.
- Keep `--allow-source-informed` explicit; do not make source-informed apply the default.
- Preserve `operator_summary.json` as the single normal apply gate.
- Keep all generated runtime packages under `outputs/` or temporary test directories; do not commit generated runtime configs.
- No new runtime dependency is needed.

---

## File Structure

- Modify `docs/operator/archetype-fixture-matrix.json`: clarify the remaining `Kingslayer` and `Boarlock` blocker ownership without changing deck count.
- Modify `src/hsconfig/matrix_visibility.py`: expose source-informed blocking reasons and closure priority from the matrix.
- Modify `tests/test_matrix_visibility.py`: lock current 9 core / 2 source-informed truth, blocker reasons, and no-widening guidance.
- Modify `src/hsconfig/source_depth_closure_index.py`: expose whether a source-informed row is a closure target or a preserved control when reports are blocked.
- Modify `tests/test_source_depth_closure_index.py`: verify closure-target and preserved-control reporting.
- Modify `docs/operator/source-backed-strong-closure.md`: document the current `Kingslayer` and `Boarlock` closure decisions and the first missing link.
- Create `src/hsconfig/report_ownership.py`: central mapping of report files to the question each answers.
- Create `tests/test_report_ownership.py`: verify the ownership map covers every important operator report.
- Modify `docs/operator/README.md`: replace loose important-report bullets with the ownership map.
- Modify `src/hsconfig/operator_summary.py`: optionally embed a compact `report_ownership` block or `open_first` guidance sourced from `report_ownership.py`.
- Modify `src/hsconfig/cli_parser.py`: add one negative-scope sentence to root/apply help.
- Create `src/hsconfig/commands/` command handlers for the largest CLI branches.
- Modify `src/hsconfig/cli.py`: delegate to command handlers without changing public CLI behavior.
- Modify `tests/test_cli.py` and `tests/test_cli_help.py`: lock command behavior and help wording.
- Modify `.agents/skills/hsconfig/SKILL.md` and `.agents/skills/hsconfig/references/workflow.md`: keep installed skill aligned with the operator path after docs changes.
- Run `scripts/sync_installed_skill.py` after skill edits.

---

## Task 1: Matrix Closure Visibility

**Files:**
- Modify: `src/hsconfig/matrix_visibility.py`
- Modify: `tests/test_matrix_visibility.py`
- Modify: `docs/operator/archetype-fixture-matrix.json`

**Interfaces:**
- Consumes: `build_matrix_visibility(matrix: dict[str, Any]) -> dict[str, Any]`
- Produces: `deck_visibility[*].source_informed_blocking_reasons`, `deck_visibility[*].closure_priority`, and `deck_visibility[*].closure_state`

- [ ] **Step 1: Add failing test for source-informed blocker visibility**

Append this test to `tests/test_matrix_visibility.py`:

```python
def test_matrix_visibility_exposes_source_informed_blockers_and_priority():
    matrix = json.loads(Path("docs/operator/archetype-fixture-matrix.json").read_text(encoding="utf-8"))
    report = build_matrix_visibility(matrix)

    by_name = {row["deck_name"]: row for row in report["deck_visibility"]}

    assert by_name["Kingslayer"]["closure_state"] == "source_informed_blocked"
    assert by_name["Kingslayer"]["source_informed_blocking_reasons"] == [
        "unsupported_conditions_present"
    ]
    assert by_name["Kingslayer"]["closure_priority"] == 2

    assert by_name["Boarlock"]["closure_state"] == "source_informed_blocked"
    assert by_name["Boarlock"]["source_informed_blocking_reasons"] == [
        "cards_need_runtime_surface",
        "generic_low_confidence_cards",
        "uncovered_cards",
        "unsupported_conditions_present",
    ]
    assert by_name["Boarlock"]["closure_priority"] == 1
```

- [ ] **Step 2: Run the focused failing test**

Run:

```powershell
python -m pytest tests/test_matrix_visibility.py::test_matrix_visibility_exposes_source_informed_blockers_and_priority -q
```

Expected: FAIL because `closure_state`, `source_informed_blocking_reasons`, and `closure_priority` are not exposed yet.

- [ ] **Step 3: Implement matrix visibility fields**

Replace `_deck_visibility` in `src/hsconfig/matrix_visibility.py` with:

```python
def _deck_visibility(row: dict[str, Any]) -> dict[str, Any]:
    visibility = row.get("strongness_visibility", {})
    if not isinstance(visibility, dict):
        visibility = {}

    fixture_stage = str(row.get("fixture_stage", ""))
    blocking_reasons = visibility.get("source_informed_blocking_reasons", [])
    if not isinstance(blocking_reasons, list):
        blocking_reasons = []
    blocking_reasons = [str(reason) for reason in blocking_reasons]

    first_gap = str(
        visibility.get("first_strongness_gap", "missing_strongness_visibility")
    )
    operator_action = str(
        visibility.get("operator_action", "add_strongness_visibility")
    )

    closure_state = "core_strong"
    if fixture_stage == "source_informed_valid_fixture":
        closure_state = "source_informed_blocked" if blocking_reasons else "source_informed_gap_only"

    closure_priority = 0
    if closure_state == "source_informed_blocked":
        closure_priority = 1 if len(blocking_reasons) > 1 else 2

    return {
        "deck_name": str(row.get("deck_name", "")),
        "fixture_stage": fixture_stage,
        "first_strongness_gap": first_gap,
        "operator_action": operator_action,
        "closure_state": closure_state,
        "source_informed_blocking_reasons": blocking_reasons,
        "closure_priority": closure_priority,
    }
```

- [ ] **Step 4: Run matrix visibility tests**

Run:

```powershell
python -m pytest tests/test_matrix_visibility.py tests/test_archetype_fixture_matrix.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/hsconfig/matrix_visibility.py tests/test_matrix_visibility.py docs/operator/archetype-fixture-matrix.json
git commit -m "test: expose source-informed matrix blockers"
```

---

## Task 2: Kingslayer And Boarlock Closure Decisions

**Files:**
- Modify: `tests/test_fixture_source_depth_closure.py`
- Modify: `src/hsconfig/source_depth_closure_index.py`
- Modify: `docs/operator/source-backed-strong-closure.md`
- Modify: `docs/operator/archetype-fixture-matrix.json`

**Interfaces:**
- Consumes: `build_source_depth_closure_index(matrix, deck_reports) -> dict[str, Any]`
- Produces: deck-level `closure_decision`, `first_blocking_reason`, and `preserve_reason` for source-informed rows.

- [ ] **Step 1: Add failing test for preserved blocked source-informed rows**

Append this test to `tests/test_fixture_source_depth_closure.py`:

```python
def test_source_informed_rows_explain_blocked_closure_decision_without_promotion():
    matrix = {
        "decks": [
            {
                "deck_name": "Boarlock",
                "fixture_stage": "source_informed_valid_fixture",
                "strongness_visibility": {
                    "first_strongness_gap": "needs_mulligan_claim_for_fracking",
                    "source_informed_apply_readiness": "blocked",
                    "source_informed_blocking_reasons": [
                        "cards_need_runtime_surface",
                        "generic_low_confidence_cards",
                    ],
                    "operator_action": "close_existing_source_informed_fixture",
                },
            }
        ]
    }

    report = build_source_depth_closure_index(matrix, {})

    boarlock = report["decks"]["Boarlock"]
    assert boarlock["next_action"] == "run_prepare_fixture_and_collect_reports"
    assert boarlock["closure_decision"] == "preserve_source_informed_until_blockers_close"
    assert boarlock["first_blocking_reason"] == "cards_need_runtime_surface"
    assert boarlock["preserve_reason"] == (
        "source-informed row has hard blockers and cannot be promoted or applied as strong"
    )
```

- [ ] **Step 2: Run the focused failing test**

Run:

```powershell
python -m pytest tests/test_fixture_source_depth_closure.py::test_source_informed_rows_explain_blocked_closure_decision_without_promotion -q
```

Expected: FAIL because `closure_decision`, `first_blocking_reason`, and `preserve_reason` do not exist yet.

- [ ] **Step 3: Implement closure decision fields**

In `src/hsconfig/source_depth_closure_index.py`, read `source_informed_blocking_reasons` from `strongness_visibility` and add these fields to each deck row:

```python
blocking_reasons = visibility.get("source_informed_blocking_reasons", [])
if not isinstance(blocking_reasons, list):
    blocking_reasons = []
blocking_reasons = [str(reason) for reason in blocking_reasons]
closure_decision = _closure_decision(
    fixture_stage=fixture_stage,
    promotion_ready=promotion_ready,
    blocking_reasons=blocking_reasons,
)
```

Add these keys inside `decks[deck_name]`:

```python
"source_informed_blocking_reasons": blocking_reasons,
"first_blocking_reason": blocking_reasons[0] if blocking_reasons else None,
"closure_decision": closure_decision,
"preserve_reason": _preserve_reason(closure_decision),
```

Add helper functions:

```python
def _closure_decision(
    *,
    fixture_stage: str,
    promotion_ready: bool,
    blocking_reasons: list[str],
) -> str:
    if promotion_ready:
        return "promote_or_keep_core"
    if fixture_stage == "source_informed_valid_fixture" and blocking_reasons:
        return "preserve_source_informed_until_blockers_close"
    if fixture_stage == "source_informed_valid_fixture":
        return "close_first_missing_chain"
    return "inspect_reports"


def _preserve_reason(closure_decision: str) -> str | None:
    if closure_decision == "preserve_source_informed_until_blockers_close":
        return "source-informed row has hard blockers and cannot be promoted or applied as strong"
    return None
```

- [ ] **Step 4: Update closure docs with stable current decisions**

In `docs/operator/source-backed-strong-closure.md`, add a compact section:

```markdown
## Current Source-Informed Closure Decisions

| Deck | Current decision | First missing link | Hard blocker reason |
| --- | --- | --- | --- |
| Kingslayer | Preserve as source-informed until blockers close | `DEEP_014` / Quick Pick needs explicit mulligan claim | `unsupported_conditions_present` |
| Boarlock | Preserve as source-informed until blockers close | `WW_092` / Fracking needs explicit mulligan claim | `cards_need_runtime_surface`, `generic_low_confidence_cards`, `uncovered_cards`, `unsupported_conditions_present` |

Do not widen the matrix to a twelfth deck to avoid these rows. Either close the first missing chain with deck-specific source evidence and runtime-surface lowering, or preserve the row as a visible source-informed control.
```

- [ ] **Step 5: Run closure tests**

Run:

```powershell
python -m pytest tests/test_fixture_source_depth_closure.py tests/test_source_depth_closure_index.py tests/test_matrix_current_truth.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add src/hsconfig/source_depth_closure_index.py tests/test_fixture_source_depth_closure.py docs/operator/source-backed-strong-closure.md docs/operator/archetype-fixture-matrix.json
git commit -m "docs: stabilize source-informed closure decisions"
```

---

## Task 3: Report Ownership Map

**Files:**
- Create: `src/hsconfig/report_ownership.py`
- Create: `tests/test_report_ownership.py`
- Modify: `src/hsconfig/operator_summary.py`
- Modify: `docs/operator/README.md`

**Interfaces:**
- Produces: `build_report_ownership() -> list[dict[str, str]]`
- Produces: `summary["report_ownership"]` with compact operator ownership rows.

- [ ] **Step 1: Add failing ownership tests**

Create `tests/test_report_ownership.py`:

```python
from hsconfig.report_ownership import build_report_ownership


def test_report_ownership_covers_operator_reports():
    rows = build_report_ownership()
    by_file = {row["file"]: row for row in rows}

    assert by_file["reports/operator_summary.json"]["authority"] == "normal_operator_gate"
    assert by_file["reports/source_claim_gap_report.json"]["answers"] == "which card link is missing first"
    assert by_file["reports/strong_promotion_report.json"]["answers"] == "whether the package can be called source-backed strong"
    assert by_file["reports/per_card_config_readiness_report.json"]["answers"] == "which lane each card occupies"
    assert by_file["reports/guide_source_depth_report.json"]["answers"] == "how strong the guide and source coverage is"
    assert by_file["reports/global_values_authority_matrix.json"]["answers"] == "which GlobalValues keys are source-backed or archetype-inferred"


def test_report_ownership_has_single_open_first_report():
    rows = build_report_ownership()

    open_first = [row for row in rows if row["open_order"] == "1"]

    assert [row["file"] for row in open_first] == ["reports/operator_summary.json"]
```

- [ ] **Step 2: Run the failing tests**

Run:

```powershell
python -m pytest tests/test_report_ownership.py -q
```

Expected: FAIL because `hsconfig.report_ownership` does not exist.

- [ ] **Step 3: Implement ownership map**

Create `src/hsconfig/report_ownership.py`:

```python
from __future__ import annotations


def build_report_ownership() -> list[dict[str, str]]:
    return [
        {
            "file": "reports/operator_summary.json",
            "authority": "normal_operator_gate",
            "answers": "what to do next",
            "open_order": "1",
        },
        {
            "file": "reports/source_claim_gap_report.json",
            "authority": "repair_contract",
            "answers": "which card link is missing first",
            "open_order": "2",
        },
        {
            "file": "reports/strong_promotion_report.json",
            "authority": "promotion_confirmation",
            "answers": "whether the package can be called source-backed strong",
            "open_order": "3",
        },
        {
            "file": "reports/per_card_config_readiness_report.json",
            "authority": "card_lane_diagnostics",
            "answers": "which lane each card occupies",
            "open_order": "4",
        },
        {
            "file": "reports/guide_source_depth_report.json",
            "authority": "source_depth_diagnostics",
            "answers": "how strong the guide and source coverage is",
            "open_order": "5",
        },
        {
            "file": "reports/global_values_authority_matrix.json",
            "authority": "globalvalues_diagnostics",
            "answers": "which GlobalValues keys are source-backed or archetype-inferred",
            "open_order": "6",
        },
    ]
```

- [ ] **Step 4: Embed compact ownership in operator summary**

In `src/hsconfig/operator_summary.py`, import and include:

```python
from hsconfig.report_ownership import build_report_ownership
```

Inside the final summary dict, add:

```python
"report_ownership": build_report_ownership(),
```

- [ ] **Step 5: Update operator docs**

Replace the loose `## Important Reports` list in `docs/operator/README.md` with:

```markdown
## Report Ownership

Open `reports/operator_summary.json` first. Lower-level reports explain the gate; they do not grant independent apply permission.

| File | Authority | Answers |
| --- | --- | --- |
| `reports/operator_summary.json` | normal operator gate | what to do next |
| `reports/source_claim_gap_report.json` | repair contract | which card link is missing first |
| `reports/strong_promotion_report.json` | promotion confirmation | whether the package can be called source-backed strong |
| `reports/per_card_config_readiness_report.json` | card lane diagnostics | which lane each card occupies |
| `reports/guide_source_depth_report.json` | source-depth diagnostics | how strong the guide and source coverage is |
| `reports/global_values_authority_matrix.json` | GlobalValues diagnostics | which GlobalValues keys are source-backed or archetype-inferred |
```

- [ ] **Step 6: Run ownership and operator summary tests**

Run:

```powershell
python -m pytest tests/test_report_ownership.py tests/test_operator_summary.py tests/test_operator_guidance.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add src/hsconfig/report_ownership.py tests/test_report_ownership.py src/hsconfig/operator_summary.py docs/operator/README.md
git commit -m "docs: add report ownership map"
```

---

## Task 4: CLI Handler Split

**Files:**
- Create: `src/hsconfig/commands/__init__.py`
- Create: `src/hsconfig/commands/apply.py`
- Create: `src/hsconfig/commands/prepare.py`
- Create: `src/hsconfig/commands/source_workflow.py`
- Modify: `src/hsconfig/cli.py`
- Test: `tests/test_cli.py`
- Test: `tests/test_prepare_cli.py`
- Test: `tests/test_research_deck_cli.py`

**Interfaces:**
- Produces: `run_apply_command(args: argparse.Namespace) -> int`
- Produces: `run_prepare_command(args: argparse.Namespace, *, expert_mode: bool) -> int`
- Produces: `run_source_manifest_command(args: argparse.Namespace) -> int`
- Produces: `run_draft_source_documents_command(args: argparse.Namespace) -> int`
- Produces: `run_research_deck_command(args: argparse.Namespace) -> int`
- `hsconfig.cli.main(argv)` remains the public entrypoint.

- [ ] **Step 1: Add behavioral lock test before refactor**

Add this test to `tests/test_cli.py`:

```python
def test_cli_main_dispatches_apply_without_changing_public_command_shape(tmp_path, monkeypatch):
    package = tmp_path / "package"
    runtime = tmp_path / "runtime"
    package.mkdir()
    runtime.mkdir()

    captured = {}

    def fake_run_apply_command(args):
        captured["package"] = args.package
        captured["runtime_root"] = args.runtime_root
        captured["json"] = args.json
        return 0

    monkeypatch.setattr("hsconfig.cli.run_apply_command", fake_run_apply_command)

    assert main([
        "apply",
        "--package",
        str(package),
        "--runtime-root",
        str(runtime),
        "--json",
    ]) == 0
    assert captured == {
        "package": str(package),
        "runtime_root": str(runtime),
        "json": True,
    }
```

- [ ] **Step 2: Run the lock test**

Run:

```powershell
python -m pytest tests/test_cli.py::test_cli_main_dispatches_apply_without_changing_public_command_shape -q
```

Expected before refactor: FAIL if `run_apply_command` is not patchable from `hsconfig.cli`.

- [ ] **Step 3: Create command package**

Create `src/hsconfig/commands/__init__.py`:

```python
"""Command handlers for the hsconfig CLI."""
```

Create `src/hsconfig/commands/apply.py` and move the apply branch logic from `src/hsconfig/cli.py` into:

```python
from __future__ import annotations

import argparse


def run_apply_command(args: argparse.Namespace) -> int:
    from hsconfig.cli import _run_apply_command

    return _run_apply_command(args)
```

Create `src/hsconfig/commands/prepare.py` and move prepare/build branch logic behind:

```python
from __future__ import annotations

import argparse


def run_prepare_command(args: argparse.Namespace, *, expert_mode: bool) -> int:
    from hsconfig.cli import _run_prepare_command

    return _run_prepare_command(args, expert_mode=expert_mode)
```

Create `src/hsconfig/commands/source_workflow.py` and move source-workflow branches behind:

```python
from __future__ import annotations

import argparse


def run_source_manifest_command(args: argparse.Namespace) -> int:
    from hsconfig.cli import _run_source_manifest_command

    return _run_source_manifest_command(args)


def run_draft_source_documents_command(args: argparse.Namespace) -> int:
    from hsconfig.cli import _run_draft_source_documents_command

    return _run_draft_source_documents_command(args)


def run_research_deck_command(args: argparse.Namespace) -> int:
    from hsconfig.cli import _run_research_deck_command

    return _run_research_deck_command(args)
```

This first split may wrap private helpers instead of moving every import. The goal is to create stable handler boundaries before deeper CLI extraction.

- [ ] **Step 4: Modify CLI dispatch imports**

At the top of `src/hsconfig/cli.py`, add:

```python
from hsconfig.commands.apply import run_apply_command
from hsconfig.commands.prepare import run_prepare_command
from hsconfig.commands.source_workflow import (
    run_draft_source_documents_command,
    run_research_deck_command,
    run_source_manifest_command,
)
```

In `main`, replace direct branch bodies with calls:

```python
if args.command == "apply":
    return run_apply_command(args)
if args.command == "build":
    return run_prepare_command(args, expert_mode=True)
if args.command == "prepare":
    return run_prepare_command(args, expert_mode=False)
if args.command == "source-manifest":
    return run_source_manifest_command(args)
if args.command == "draft-source-documents":
    return run_draft_source_documents_command(args)
if args.command == "research-deck":
    return run_research_deck_command(args)
```

If the current CLI has branch-local code instead of private helpers, first rename those blocks into private helpers in the same file:

```python
def _run_apply_command(args: argparse.Namespace) -> int:
    ...
```

Then let the command package delegate to those helpers.

- [ ] **Step 5: Run CLI regression tests**

Run:

```powershell
python -m pytest tests/test_cli.py tests/test_prepare_cli.py tests/test_research_deck_cli.py tests/test_apply_cli.py -q
```

Expected: PASS. If `tests/test_apply_cli.py` does not exist, run:

```powershell
python -m pytest tests/test_cli.py tests/test_prepare_cli.py tests/test_research_deck_cli.py tests/test_apply_gate.py -q
```

- [ ] **Step 6: Commit**

```powershell
git add src/hsconfig/commands src/hsconfig/cli.py tests/test_cli.py
git commit -m "refactor: split cli command handlers"
```

---

## Task 5: Negative Scope Help And Skill Sync

**Files:**
- Modify: `src/hsconfig/cli_parser.py`
- Modify: `tests/test_cli_help.py`
- Modify: `.agents/skills/hsconfig/SKILL.md`
- Modify: `.agents/skills/hsconfig/references/workflow.md`
- Run: `scripts/sync_installed_skill.py`

**Interfaces:**
- Public CLI help keeps the same commands.
- Root help and apply help explicitly say HSConfig remains pre-run only.

- [ ] **Step 1: Add failing help tests**

Append to `tests/test_cli_help.py`:

```python
from hsconfig.cli_parser import build_parser


def test_root_help_states_negative_scope():
    help_text = build_parser().format_help()

    assert "pre-run only" in help_text
    assert "does not parse replays, inspect winrate, or tune after games" in help_text


def test_apply_help_keeps_source_informed_pre_run_scope():
    parser = build_parser()
    apply_parser = parser._subparsers._actions[1].choices["apply"]
    help_text = apply_parser.format_help()

    assert "--allow-source-informed" in help_text
    assert "source-informed apply remains pre-run only" in help_text
```

- [ ] **Step 2: Run failing help tests**

Run:

```powershell
python -m pytest tests/test_cli_help.py::test_root_help_states_negative_scope tests/test_cli_help.py::test_apply_help_keeps_source_informed_pre_run_scope -q
```

Expected: FAIL because the exact negative-scope copy is not in help yet.

- [ ] **Step 3: Update CLI parser copy**

In `src/hsconfig/cli_parser.py`, change the root parser epilog to include:

```python
"HSConfig is pre-run only: it does not parse replays, inspect winrate, or tune after games.\n"
```

Change apply parser creation to:

```python
apply = subparsers.add_parser(
    "apply",
    description=(
        "Apply a validated pre-run CustomConfig package. "
        "source-informed apply remains pre-run only and still requires "
        "reports/operator_summary.json to allow it."
    ),
)
```

- [ ] **Step 4: Update skill workflow wording**

In `.agents/skills/hsconfig/SKILL.md`, ensure the scope section contains:

```markdown
HSConfig is pre-run only. It does not parse replays, inspect winrate, analyze runtime logs, promote candidates, or tune after games.
```

In `.agents/skills/hsconfig/references/workflow.md`, ensure the apply section contains:

```markdown
Source-informed apply remains pre-run only. It is not replay analysis, winrate validation, HSTuner candidate promotion, or post-run tuning.
```

- [ ] **Step 5: Sync installed skill**

Run:

```powershell
python scripts\sync_installed_skill.py
python scripts\sync_installed_skill.py --check
```

Expected:

```text
HSConfig skill is in sync: C:\Users\darbo\.codex\skills\hsconfig
```

- [ ] **Step 6: Run help and skill tests**

Run:

```powershell
python -m pytest tests/test_cli_help.py tests/test_skill_sync.py tests/test_skill_files.py tests/test_scope_boundaries.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add src/hsconfig/cli_parser.py tests/test_cli_help.py .agents/skills/hsconfig C:\Users\darbo\.codex\skills\hsconfig
git commit -m "docs: clarify hsconfig pre-run scope"
```

If Git refuses the installed skill path because it is outside the repo, commit only repo files:

```powershell
git add src/hsconfig/cli_parser.py tests/test_cli_help.py .agents/skills/hsconfig
git commit -m "docs: clarify hsconfig pre-run scope"
```

---

## Task 6: Research Docs Index And Active-Path Cleanup

**Files:**
- Create or modify: `docs/research/README.md`
- Modify: `README.md`
- Modify: `docs/operator/README.md`
- Test: `tests/test_operator_guidance.py` or create `tests/test_docs_active_path.py`

**Interfaces:**
- Produces one active research index that says research artifacts are evidence, not operator instructions.
- Keeps normal path `README.md -> docs/operator/README.md`.

- [ ] **Step 1: Add failing docs test**

Create `tests/test_docs_active_path.py`:

```python
from pathlib import Path


def test_research_docs_are_marked_as_evidence_not_operator_path():
    text = Path("docs/research/README.md").read_text(encoding="utf-8")

    assert "Research artifacts are evidence, not operator instructions." in text
    assert "Normal operator path starts at docs/operator/README.md." in text


def test_root_readme_points_to_operator_path_not_research_history():
    text = Path("README.md").read_text(encoding="utf-8")

    assert "docs/operator/README.md" in text
    assert "docs/research/" not in text
```

- [ ] **Step 2: Run failing docs test**

Run:

```powershell
python -m pytest tests/test_docs_active_path.py -q
```

Expected: FAIL if `docs/research/README.md` is missing or active path wording is absent.

- [ ] **Step 3: Create research index**

Create `docs/research/README.md`:

```markdown
# HSConfig Research Artifacts

Research artifacts are evidence, not operator instructions. Normal operator path starts at `docs/operator/README.md`.

Use research folders to understand why a design or gate exists. Do not use an older research result as a newer runtime, matrix, or apply authority.

Current high-signal audit:

- `2026-07-08-hsconfig-current-skill-post-gate-audit/`

Historical research folders may contain superseded matrix counts, older source-informed policy, or pre-closure assumptions. Prefer live code, tests, `docs/operator/archetype-fixture-matrix.json`, and `reports/operator_summary.json` over historical research text.
```

- [ ] **Step 4: Keep root README short**

Ensure `README.md` has only a short purpose, bootstrap command, and pointer to `docs/operator/README.md`. If it already does, do not rewrite it.

- [ ] **Step 5: Run docs tests**

Run:

```powershell
python -m pytest tests/test_docs_active_path.py tests/test_operator_guidance.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add docs/research/README.md README.md docs/operator/README.md tests/test_docs_active_path.py
git commit -m "docs: index research evidence separately"
```

---

## Task 7: Final Verification And Push

**Files:**
- No planned source changes. This task verifies and publishes the integrated branch.

**Interfaces:**
- Produces a green local verification record and clean `main`.

- [ ] **Step 1: Run focused closure and docs suite**

Run:

```powershell
python -m pytest tests/test_matrix_visibility.py tests/test_fixture_source_depth_closure.py tests/test_source_depth_closure_index.py tests/test_report_ownership.py tests/test_cli_help.py tests/test_skill_sync.py tests/test_skill_files.py tests/test_docs_active_path.py -q
```

Expected: PASS.

- [ ] **Step 2: Run broad suite**

Run:

```powershell
python -m pytest -q
```

Expected: PASS with all existing tests green. The current baseline before this plan was `484 passed, 2 skipped`.

- [ ] **Step 3: Confirm skill sync**

Run:

```powershell
python scripts\sync_installed_skill.py --check
```

Expected:

```text
HSConfig skill is in sync: C:\Users\darbo\.codex\skills\hsconfig
```

- [ ] **Step 4: Check status**

Run:

```powershell
git status --short --branch
```

Expected:

```text
## main...origin/main
```

or a clean feature branch if implemented in a worktree.

- [ ] **Step 5: Push**

Run:

```powershell
git push origin main
```

Expected: push succeeds.

---

## Self-Review

- Spec coverage: The plan covers the recommendation: close or preserve `Kingslayer` and `Boarlock`, split CLI pressure, add report ownership, clarify negative scope, and reduce research-doc confusion.
- Language scan: No unresolved vague language or unspecified future implementation remains.
- Scope check: The plan does not add new deck rows, runtime surfaces, replay parsing, winrate analysis, post-run tuning, or HSTuner behavior.
- Type consistency: New planned functions are explicitly named: `build_report_ownership`, `run_apply_command`, `run_prepare_command`, `run_source_manifest_command`, `run_draft_source_documents_command`, and `run_research_deck_command`.
- Execution model: Tasks are separable for subagent-driven execution. Task 4 is the only broad refactor and should run after Tasks 1-3 to avoid mixing behavioral closure with CLI movement.

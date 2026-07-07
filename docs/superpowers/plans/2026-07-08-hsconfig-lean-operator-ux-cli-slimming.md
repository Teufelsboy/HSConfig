# HSConfig Lean Operator UX And CLI Slimming Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make HSConfig easier to operate from deck input to pre-run CustomConfig readiness while keeping the repo lean, pre-run only, and separate from HSTuner.

**Architecture:** Keep the existing source-backed pipeline and `operator_summary.json` as the single operator gate. Add a small operator guidance layer, consolidate the normal docs path, make the 11-deck fixture matrix expose first missing strongness links, and split CLI construction into focused modules without changing runtime behavior.

**Tech Stack:** Python 3.11+, argparse, pytest, existing `hearthstone>=9.0.0`, local markdown/json docs, no new runtime dependencies.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig` for `Teufelsboy/HSConfig`.
- HSConfig is a lean deck-to-HearthRanger-config generator. Keep it separate from HSTuner.
- Do not add replay parsing, HDT parsing, winrate validation, candidate promotion, runtime evidence analysis, or post-run tuning to this repo.
- Do not add new runtime dependencies.
- Generated runtime packages belong under `outputs/` and are ignored by git.
- Preserve exact deck and CardID identity.
- Preserve full `GlobalValues.json` key profiling.
- Preserve every card covered in the gameplan contract.
- Preserve strict JSON validation.
- Preserve row-level provenance for generated config rows.
- Normal runtime output remains `GlobalValues.json`, `Mulligan.json`, per-card `<CARDID>.json`, and `Combo.json` only when an exact valid combo exists.
- Do not emit `Presume.json` or `Concede.json` in the normal path.
- `reports/operator_summary.json` remains the single normal operator gate.
- Lower-level reports explain the gate; they must not become independent apply permissions.
- Existing research audit artifacts under `docs/research/2026-07-07-hsconfig-current-skill-audit/` are evidence, not operator instructions.

---

## File Structure

### Create

- `docs/operator/README.md`
  - Single normal operator entry point.
  - Links to detailed policy docs without duplicating all content.

- `docs/research/2026-07-07-hsconfig-current-skill-audit/README.md`
  - Explains that the research JSON files are source-backed audit evidence, not runtime inputs.

- `src/hsconfig/operator_guidance.py`
  - Pure helper that converts an `operator_summary.json` dict into one compact next-action guidance dict.

- `src/hsconfig/cli_parser.py`
  - Owns argparse parser construction.
  - Keeps `src/hsconfig/cli.py` responsible for dispatch and command handlers during this wave.

- `src/hsconfig/matrix_visibility.py`
  - Pure helper that summarizes the 11-deck fixture matrix and first strongness links.

- `tests/test_operator_guidance.py`
  - Unit tests for guidance fields emitted from summary states.

- `tests/test_matrix_visibility.py`
  - Unit tests for fixture matrix visibility and first missing link fields.

### Modify

- `README.md`
  - Shorten to purpose, install, quickstart, normal operator link, and HSTuner boundary.

- `docs/operator/source-builder-workflow.md`
  - Make it the detailed workflow page beneath `docs/operator/README.md`.

- `docs/operator/guide-research-policy.md`
  - Link to the operator entry and clarify that evidence rows are source inputs, not runtime claims by themselves.

- `docs/operator/archetype-fixture-matrix.json`
  - Add per-deck `strongness_visibility` blocks.

- `.agents/skills/hsconfig/SKILL.md`
  - Point operators to `docs/operator/README.md` as the normal path.

- `.agents/skills/hsconfig/references/workflow.md`
  - Keep the skill workflow aligned with the new operator entry.

- `src/hsconfig/operator_summary.py`
  - Add `operator_guidance` to the returned summary by calling `build_operator_guidance(summary)`.

- `src/hsconfig/cli.py`
  - Replace parser construction with a compatibility wrapper that delegates to `src/hsconfig/cli_parser.py`.
  - Keep `_build_parser()` for existing tests and import compatibility.

- `tests/test_cli_help.py`
  - Verify root help points to the normal operator docs and keeps expert commands clearly marked.

- `tests/test_skill_files.py`
  - Verify docs and skill reference the new operator entry and keep forbidden post-run scope out.

- `scripts/sync_installed_skill.py`
  - No code change expected; run after skill doc changes.

---

### Task 1: Preserve Research Audit As Evidence

**Files:**
- Create: `docs/research/2026-07-07-hsconfig-current-skill-audit/README.md`
- Modify: `docs/research/2026-07-07-hsconfig-current-skill-audit/fields.yaml`
- Test: `tests/test_skill_files.py`

**Interfaces:**
- Consumes: Existing audit JSON files in `docs/research/2026-07-07-hsconfig-current-skill-audit/results/`.
- Produces: A stable README stating the audit is evidence for planning, not normal operator guidance.

- [ ] **Step 1: Write the failing docs test**

Add this test to `tests/test_skill_files.py`:

```python
def test_current_skill_audit_is_marked_as_research_evidence():
    root = Path("docs/research/2026-07-07-hsconfig-current-skill-audit")
    readme = (root / "README.md").read_text(encoding="utf-8")

    assert "research evidence" in readme
    assert "not operator guidance" in readme
    assert "not runtime input" in readme
    assert (root / "fields.yaml").exists()
    assert len(list((root / "results").glob("*.json"))) == 5
```

- [ ] **Step 2: Run the failing test**

Run:

```powershell
python -m pytest tests/test_skill_files.py::test_current_skill_audit_is_marked_as_research_evidence -q
```

Expected: FAIL because `docs/research/2026-07-07-hsconfig-current-skill-audit/README.md` does not exist.

- [ ] **Step 3: Add the audit README**

Create `docs/research/2026-07-07-hsconfig-current-skill-audit/README.md`:

```markdown
# HSConfig Current Skill Audit

This folder contains research evidence for the HSConfig lean operator UX and CLI-slimming work.

It is not operator guidance, not runtime input, and not a CustomConfig package. Normal HSConfig operation starts at `README.md` and `docs/operator/README.md`.

The JSON files in `results/` summarize source-backed audit findings for:

- HearthRanger VisionAI runtime surfaces
- Hearthstone deck and card identity
- guide-claim depth and every-card contract coverage
- the 11-deck archetype fixture matrix
- the lean HSConfig boundary and operator UX

Use this folder to justify design decisions. Do not copy these files into generated runtime packages.
```

- [ ] **Step 4: Verify all research JSON files validate**

Run:

```powershell
python C:\Users\darbo\.codex\skills\research\validate_json.py -f docs\research\2026-07-07-hsconfig-current-skill-audit\fields.yaml -j docs\research\2026-07-07-hsconfig-current-skill-audit\results\HearthRanger_VisionAI_Runtime_Surface_Audit.json docs\research\2026-07-07-hsconfig-current-skill-audit\results\Hearthstone_Data_And_Card_Identity_Audit.json docs\research\2026-07-07-hsconfig-current-skill-audit\results\Guide-Claim_Depth_And_Every-Card_Contract_Audit.json docs\research\2026-07-07-hsconfig-current-skill-audit\results\Eleven-Deck_Archetype_Breadth_Audit.json docs\research\2026-07-07-hsconfig-current-skill-audit\results\Lean_Boundary_And_Operator_UX_Audit.json
```

Expected: PASS with `Validation passed: 5/5` and `Average coverage: 100.0%`.

- [ ] **Step 5: Run focused docs test**

Run:

```powershell
python -m pytest tests/test_skill_files.py::test_current_skill_audit_is_marked_as_research_evidence -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add docs/research/2026-07-07-hsconfig-current-skill-audit tests/test_skill_files.py
git commit -m "docs: preserve hsconfig skill audit evidence"
```

---

### Task 2: Add Single Operator Entry Point

**Files:**
- Create: `docs/operator/README.md`
- Modify: `README.md`
- Modify: `docs/operator/source-builder-workflow.md`
- Modify: `docs/operator/guide-research-policy.md`
- Modify: `.agents/skills/hsconfig/SKILL.md`
- Modify: `.agents/skills/hsconfig/references/workflow.md`
- Test: `tests/test_skill_files.py`
- Test: `tests/test_cli_help.py`

**Interfaces:**
- Consumes: Existing normal path commands and existing operator docs.
- Produces: `docs/operator/README.md` as the single normal operator entry point.

- [ ] **Step 1: Write failing docs tests**

Add these tests to `tests/test_skill_files.py`:

```python
def test_operator_readme_is_single_normal_entry_point():
    readme = Path("docs/operator/README.md").read_text(encoding="utf-8")
    root = Path("README.md").read_text(encoding="utf-8")
    skill = Path(".agents/skills/hsconfig/SKILL.md").read_text(encoding="utf-8")
    workflow = Path(".agents/skills/hsconfig/references/workflow.md").read_text(encoding="utf-8")

    assert "Normal Operator Path" in readme
    assert "reports/operator_summary.json" in readme
    assert "source-manifest" in readme
    assert "draft-source-documents" in readme
    assert "research-deck" in readme
    assert "prepare" in readme
    assert "apply" in readme
    assert "HSTuner" in readme
    assert "docs/operator/README.md" in root
    assert "docs/operator/README.md" in skill
    assert "docs/operator/README.md" in workflow
```

Add this test to `tests/test_cli_help.py`:

```python
def test_root_help_points_to_operator_docs():
    help_text = _build_parser().format_help()

    assert "docs/operator/README.md" in help_text
    assert "Normal path:" in help_text
    assert "Expert and legacy path:" in help_text
```

- [ ] **Step 2: Run the failing tests**

Run:

```powershell
python -m pytest tests/test_skill_files.py::test_operator_readme_is_single_normal_entry_point tests/test_cli_help.py::test_root_help_points_to_operator_docs -q
```

Expected: FAIL because `docs/operator/README.md` does not exist and root help does not point to it.

- [ ] **Step 3: Create the operator README**

Create `docs/operator/README.md`:

```markdown
# HSConfig Operator Guide

HSConfig creates pre-game HearthRanger VisionAI `CustomConfig` packages from a deck name, deck code, and source-backed guide evidence.

HSConfig does not parse replays, inspect winrate, analyze runtime logs, promote post-run candidates, or tune after games. Those tasks belong to HSTuner.

## Normal Operator Path

1. Run `hsconfig source-manifest` to get aliases, card targets, and research questions.
2. Write short source evidence rows from current guide, archetype, mulligan, card-text, and metadata sources.
3. Run `hsconfig draft-source-documents` to turn evidence rows into strict `source_documents.json`.
4. Run `hsconfig research-deck --source-documents-json ...` to normalize guide sources.
5. Run `hsconfig prepare --guide-sources-json ...` to compile and validate the package.
6. Open `reports/operator_summary.json` first.
7. Run `hsconfig apply` only when the operator summary allows it.

## Single Gate

Use `reports/operator_summary.json` as the normal operator gate.

- `technical_status=VALID_PACKAGE` means the runtime JSON shape is load-safe.
- `semantic_status=SOURCE_BACKED_STRONG` means source coverage and per-card closure are strong enough for normal apply or handoff.
- `semantic_status=VALID_BUT_NOT_GUIDE_STRONG` means the package is valid but source depth, runtime surfaces, combo detail, conditions, mechanics, or conflicts still need work.
- `apply_policy=ALLOWED` is required for normal apply.

Lower-level reports explain the gate. They do not grant independent apply permission.

## Important Reports

- `reports/operator_summary.json`
- `reports/source_claim_gap_report.json`
- `reports/strong_promotion_report.json`
- `reports/per_card_config_readiness_report.json`
- `reports/guide_source_depth_report.json`
- `reports/global_values_authority_matrix.json`

## Expert Paths

Use `hsconfig build`, `hsconfig research-contract`, `--cards-json`, `--claims-json`, `--plan-reports-dir`, and `--allow-placeholder` only for fixtures, diagnostics, or inspected expert inputs.

Use `--allow-source-informed` only when intentionally applying a technically valid package before it reaches `SOURCE_BACKED_STRONG`.
```

- [ ] **Step 4: Shorten root README**

Edit `README.md` so the top-level file keeps only:

```markdown
# HSConfig

HSConfig builds guide-aligned HearthRanger VisionAI `CustomConfig` packages from a Hearthstone deck name and deck code.

HSConfig is a direct pre-game config authoring tool. It does not parse replays, evaluate winrate, inspect post-game evidence, or tune from runtime logs. Those are HSTuner concerns. `Presume.json` and `Concede.json` are not emitted in the normal path.

## Normal Operator Path

Start with `docs/operator/README.md`.

Normal command path: `hsconfig source-manifest ...` -> write short evidence rows -> `hsconfig draft-source-documents ...` -> `hsconfig research-deck --source-documents-json ...` -> `hsconfig prepare --guide-sources-json ...` -> inspect `reports/operator_summary.json` -> `hsconfig apply ...` only when requested.

## Install And Verify

```powershell
python -m pip install -e .
python -m pytest -q
python scripts\sync_installed_skill.py --check
```

## Maintainer Sync

After changing `.agents/skills/hsconfig`, run `python scripts\sync_installed_skill.py --check`; if drift is expected, run `python scripts\sync_installed_skill.py`.
```

- [ ] **Step 5: Add operator README links to detailed docs and skill**

Update these files so each contains `docs/operator/README.md`:

```text
docs/operator/source-builder-workflow.md
docs/operator/guide-research-policy.md
.agents/skills/hsconfig/SKILL.md
.agents/skills/hsconfig/references/workflow.md
```

Use this exact sentence where it fits:

```markdown
For the normal operator entry point, start at `docs/operator/README.md`.
```

- [ ] **Step 6: Update CLI root help**

In `src/hsconfig/cli.py`, update the root parser description or epilog so `format_help()` includes:

```text
Normal operator docs: docs/operator/README.md
```

- [ ] **Step 7: Sync installed skill**

Run:

```powershell
python scripts\sync_installed_skill.py
python scripts\sync_installed_skill.py --check
```

Expected: `HSConfig skill is in sync`.

- [ ] **Step 8: Run focused docs tests**

Run:

```powershell
python -m pytest tests/test_skill_files.py tests/test_cli_help.py -q
```

Expected: PASS.

- [ ] **Step 9: Commit**

```powershell
git add README.md docs/operator/README.md docs/operator/source-builder-workflow.md docs/operator/guide-research-policy.md .agents/skills/hsconfig/SKILL.md .agents/skills/hsconfig/references/workflow.md src/hsconfig/cli.py tests/test_skill_files.py tests/test_cli_help.py
git commit -m "docs: add hsconfig operator entry point"
```

---

### Task 3: Add Operator Guidance To Operator Summary

**Files:**
- Create: `src/hsconfig/operator_guidance.py`
- Modify: `src/hsconfig/operator_summary.py`
- Test: `tests/test_operator_guidance.py`
- Test: `tests/test_operator_summary.py`

**Interfaces:**
- Consumes: `operator_summary` dict containing `technical_status`, `semantic_status`, `next_action`, `apply_policy`, and `semantic_blockers`.
- Produces: `build_operator_guidance(summary: dict[str, Any]) -> dict[str, Any]`.
- Produces in `operator_summary.json`: `operator_guidance`.

- [ ] **Step 1: Write failing guidance unit tests**

Create `tests/test_operator_guidance.py`:

```python
from hsconfig.operator_guidance import build_operator_guidance


def test_guidance_for_source_backed_strong_package():
    guidance = build_operator_guidance(
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "SOURCE_BACKED_STRONG",
            "next_action": "READY_TO_APPLY_OR_HANDOFF",
            "apply_policy": "ALLOWED",
            "semantic_blockers": [],
        }
    )

    assert guidance == {
        "first_report_to_open": "reports/operator_summary.json",
        "next_report_to_open": None,
        "normal_next_step": "apply_or_handoff",
        "normal_next_command": "hsconfig apply --package <package> --runtime-root <runtime-root> --json",
        "safe_to_apply": True,
        "requires_expert_flag": False,
    }


def test_guidance_for_valid_but_not_guide_strong_package():
    guidance = build_operator_guidance(
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "VALID_BUT_NOT_GUIDE_STRONG",
            "next_action": "IMPROVE_GUIDE_SOURCES_BEFORE_STRONG_APPLY",
            "apply_policy": "ALLOWED_WITH_WARNINGS",
            "semantic_blockers": [{"reason": "cards_need_guide_claims", "count": 2}],
        }
    )

    assert guidance["first_report_to_open"] == "reports/operator_summary.json"
    assert guidance["next_report_to_open"] == "reports/source_claim_gap_report.json"
    assert guidance["normal_next_step"] == "improve_sources"
    assert guidance["normal_next_command"] == "update source_documents.json, rerun hsconfig research-deck, then rerun hsconfig prepare"
    assert guidance["safe_to_apply"] is False
    assert guidance["requires_expert_flag"] is True


def test_guidance_for_invalid_package():
    guidance = build_operator_guidance(
        {
            "technical_status": "INVALID_PACKAGE",
            "semantic_status": "INVALID_PACKAGE",
            "next_action": "FIX_PACKAGE_BEFORE_APPLY",
            "apply_policy": "BLOCKED",
            "semantic_blockers": [],
        }
    )

    assert guidance["next_report_to_open"] == "reports/validation_report.json"
    assert guidance["normal_next_step"] == "fix_package"
    assert guidance["safe_to_apply"] is False
    assert guidance["requires_expert_flag"] is False
```

Add this assertion to `tests/test_operator_summary.py::test_source_backed_valid_package_is_ready_to_apply`:

```python
    assert summary["operator_guidance"]["safe_to_apply"] is True
    assert summary["operator_guidance"]["normal_next_step"] == "apply_or_handoff"
```

- [ ] **Step 2: Run failing tests**

Run:

```powershell
python -m pytest tests/test_operator_guidance.py tests/test_operator_summary.py::test_source_backed_valid_package_is_ready_to_apply -q
```

Expected: FAIL because `hsconfig.operator_guidance` does not exist.

- [ ] **Step 3: Implement `operator_guidance.py`**

Create `src/hsconfig/operator_guidance.py`:

```python
from __future__ import annotations

from typing import Any


def build_operator_guidance(summary: dict[str, Any]) -> dict[str, Any]:
    technical_status = str(summary.get("technical_status", ""))
    semantic_status = str(summary.get("semantic_status", ""))
    apply_policy = str(summary.get("apply_policy", ""))

    if technical_status == "INVALID_PACKAGE" or apply_policy == "BLOCKED":
        return {
            "first_report_to_open": "reports/operator_summary.json",
            "next_report_to_open": "reports/validation_report.json",
            "normal_next_step": "fix_package",
            "normal_next_command": "run hsconfig validate --package <package> --json and fix reported JSON/package errors",
            "safe_to_apply": False,
            "requires_expert_flag": False,
        }

    if semantic_status == "SOURCE_BACKED_STRONG" and apply_policy == "ALLOWED":
        return {
            "first_report_to_open": "reports/operator_summary.json",
            "next_report_to_open": None,
            "normal_next_step": "apply_or_handoff",
            "normal_next_command": "hsconfig apply --package <package> --runtime-root <runtime-root> --json",
            "safe_to_apply": True,
            "requires_expert_flag": False,
        }

    if semantic_status == "VALID_BUT_NOT_GUIDE_STRONG":
        return {
            "first_report_to_open": "reports/operator_summary.json",
            "next_report_to_open": "reports/source_claim_gap_report.json",
            "normal_next_step": "improve_sources",
            "normal_next_command": "update source_documents.json, rerun hsconfig research-deck, then rerun hsconfig prepare",
            "safe_to_apply": False,
            "requires_expert_flag": True,
        }

    return {
        "first_report_to_open": "reports/operator_summary.json",
        "next_report_to_open": "reports/guide_source_depth_report.json",
        "normal_next_step": "inspect_operator_summary",
        "normal_next_command": "read reports/operator_summary.json and follow next_action",
        "safe_to_apply": False,
        "requires_expert_flag": apply_policy == "ALLOWED_WITH_WARNINGS",
    }
```

- [ ] **Step 4: Thread guidance into `operator_summary.py`**

At the top of `src/hsconfig/operator_summary.py`, add:

```python
from hsconfig.operator_guidance import build_operator_guidance
```

In `build_operator_summary`, replace the direct `return { ... }` with:

```python
    summary = {
        "schema_version": 1,
        "deck_name": deck_name,
        "deck_code": deck_code,
        "technical_status": technical_status,
        "semantic_status": semantic_status,
        "next_action": next_action,
        "apply_policy": apply_policy,
        "primary_blockers": primary_blockers,
        "warnings": warnings,
        "guide_strength_summary": guide_strength_summary,
        "semantic_blockers": semantic_blockers,
        "generated_files": list(generated_files or []),
    }
    summary["operator_guidance"] = build_operator_guidance(summary)
    return summary
```

Preserve any existing keys in the current summary; do not remove fields.

- [ ] **Step 5: Run focused tests**

Run:

```powershell
python -m pytest tests/test_operator_guidance.py tests/test_operator_summary.py -q
```

Expected: PASS.

- [ ] **Step 6: Run prepare regression**

Run:

```powershell
python -m pytest tests/test_prepare_cli.py tests/test_apply_gate.py tests/test_runtime_apply.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add src/hsconfig/operator_guidance.py src/hsconfig/operator_summary.py tests/test_operator_guidance.py tests/test_operator_summary.py
git commit -m "feat: add operator guidance summary"
```

---

### Task 4: Extract CLI Parser Construction

**Files:**
- Create: `src/hsconfig/cli_parser.py`
- Modify: `src/hsconfig/cli.py`
- Modify: `tests/test_cli_help.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: Existing `_build_parser()` behavior.
- Produces: `build_parser() -> argparse.ArgumentParser` in `src/hsconfig/cli_parser.py`.
- Preserves: `hsconfig.cli._build_parser()` as a compatibility wrapper.

- [ ] **Step 1: Write failing parser module test**

Modify `tests/test_cli_help.py`:

```python
from hsconfig.cli_parser import build_parser


def test_cli_parser_module_builds_same_root_help():
    help_text = build_parser().format_help()

    assert "HSConfig builds lean HearthRanger VisionAI CustomConfig packages" in help_text
    assert "docs/operator/README.md" in help_text
    assert "source-manifest -> draft-source-documents -> research-deck -> prepare -> apply" in help_text
```

- [ ] **Step 2: Run failing test**

Run:

```powershell
python -m pytest tests/test_cli_help.py::test_cli_parser_module_builds_same_root_help -q
```

Expected: FAIL because `hsconfig.cli_parser` does not exist.

- [ ] **Step 3: Create `cli_parser.py`**

Move parser construction from `src/hsconfig/cli.py::_build_parser()` into `src/hsconfig/cli_parser.py` as:

```python
from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hsconfig",
        description="HSConfig builds lean HearthRanger VisionAI CustomConfig packages before games are played.",
        epilog=(
            "Normal path: source-manifest -> draft-source-documents -> research-deck -> "
            "prepare -> apply. Expert and legacy path: build, --claims-json, "
            "--cards-json, --plan-reports-dir. Normal operator docs: "
            "docs/operator/README.md"
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    # Move the existing subparser definitions here without changing argument names.
    return parser
```

Move the full existing subparser definitions into this function. Do not rename commands, flags, help strings, or defaults except for the root epilog addition from Task 2.

- [ ] **Step 4: Keep compatibility wrapper in `cli.py`**

In `src/hsconfig/cli.py`, import and wrap:

```python
from hsconfig.cli_parser import build_parser


def _build_parser() -> argparse.ArgumentParser:
    return build_parser()
```

Keep `main()` dispatch unchanged:

```python
def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    ...
```

- [ ] **Step 5: Run focused CLI help tests**

Run:

```powershell
python -m pytest tests/test_cli_help.py -q
```

Expected: PASS.

- [ ] **Step 6: Run CLI behavior tests**

Run:

```powershell
python -m pytest tests/test_cli.py tests/test_prepare_cli.py tests/test_runtime_apply.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add src/hsconfig/cli.py src/hsconfig/cli_parser.py tests/test_cli_help.py
git commit -m "refactor: extract hsconfig cli parser"
```

---

### Task 5: Add Matrix Strongness Visibility

**Files:**
- Create: `src/hsconfig/matrix_visibility.py`
- Modify: `docs/operator/archetype-fixture-matrix.json`
- Modify: `docs/operator/README.md`
- Test: `tests/test_matrix_visibility.py`
- Test: `tests/test_archetype_fixture_matrix.py`

**Interfaces:**
- Consumes: Matrix JSON with deck rows.
- Produces: `build_matrix_visibility(matrix: dict[str, Any]) -> dict[str, Any]`.
- Adds each row field: `strongness_visibility`.

- [ ] **Step 1: Write failing matrix visibility tests**

Create `tests/test_matrix_visibility.py`:

```python
import json
from pathlib import Path

from hsconfig.matrix_visibility import build_matrix_visibility


def test_matrix_visibility_summarizes_core_and_source_informed_rows():
    matrix = json.loads(Path("docs/operator/archetype-fixture-matrix.json").read_text(encoding="utf-8"))
    report = build_matrix_visibility(matrix)

    assert report["total_decks"] == 11
    assert report["core_source_backed_fixture_count"] == 4
    assert report["source_informed_valid_fixture_count"] == 7
    assert report["normal_next_action"] == "close_existing_source_informed_rows_before_adding_more_decks"


def test_each_matrix_row_exposes_first_strongness_link():
    matrix = json.loads(Path("docs/operator/archetype-fixture-matrix.json").read_text(encoding="utf-8"))

    for row in matrix["decks"]:
        visibility = row["strongness_visibility"]
        assert visibility["current_stage"] == row["fixture_stage"]
        assert visibility["first_strongness_gap"]
        assert visibility["operator_action"]
        if row["fixture_stage"] == "core_source_backed_fixture":
            assert visibility["first_strongness_gap"] == "none"
            assert visibility["operator_action"] == "keep_as_core_control_fixture"
        else:
            assert visibility["first_strongness_gap"] != "none"
            assert visibility["operator_action"].startswith("close_existing_")
```

- [ ] **Step 2: Run failing tests**

Run:

```powershell
python -m pytest tests/test_matrix_visibility.py -q
```

Expected: FAIL because `hsconfig.matrix_visibility` and `strongness_visibility` fields do not exist.

- [ ] **Step 3: Add `strongness_visibility` to matrix rows**

Update each row in `docs/operator/archetype-fixture-matrix.json`.

For core fixtures use:

```json
"strongness_visibility": {
  "current_stage": "core_source_backed_fixture",
  "first_strongness_gap": "none",
  "operator_action": "keep_as_core_control_fixture"
}
```

For source-informed rows use values matching the deck family:

```json
"strongness_visibility": {
  "current_stage": "source_informed_valid_fixture",
  "first_strongness_gap": "needs_source_depth_or_runtime_surface_closure",
  "operator_action": "close_existing_source_informed_fixture"
}
```

Use a more specific `first_strongness_gap` when the row already documents it:

- CtAPaladin: `needs_recruit_aura_runtime_surface_closure`
- Discolock: `needs_discard_hand_mutation_runtime_surface_closure`
- TreantDruid: `needs_token_board_buff_runtime_surface_closure`
- ImbueMage: `needs_hero_power_spell_generation_runtime_surface_closure`
- Kingslayer: `needs_weapon_sequence_runtime_surface_closure`
- Boarlock: `needs_exact_combo_sequence_closure`
- PirateDH: `needs_hero_attack_runtime_surface_closure`

- [ ] **Step 4: Implement `matrix_visibility.py`**

Create `src/hsconfig/matrix_visibility.py`:

```python
from __future__ import annotations

from typing import Any


def build_matrix_visibility(matrix: dict[str, Any]) -> dict[str, Any]:
    rows = list(matrix.get("decks", []))
    core = [row for row in rows if row.get("fixture_stage") == "core_source_backed_fixture"]
    source_informed = [
        row for row in rows if row.get("fixture_stage") == "source_informed_valid_fixture"
    ]
    missing_visibility = [
        row.get("deck_name", "")
        for row in rows
        if not isinstance(row.get("strongness_visibility"), dict)
    ]

    return {
        "schema_version": 1,
        "total_decks": len(rows),
        "core_source_backed_fixture_count": len(core),
        "source_informed_valid_fixture_count": len(source_informed),
        "decks_missing_visibility": missing_visibility,
        "normal_next_action": "close_existing_source_informed_rows_before_adding_more_decks",
    }
```

- [ ] **Step 5: Document matrix visibility**

Add this section to `docs/operator/README.md`:

```markdown
## Fixture Matrix

`docs/operator/archetype-fixture-matrix.json` is the representative 11-deck HSConfig proof set.

Do not add a new representative deck when an existing row can exercise the same source-depth or runtime-surface family. Improve the seven `source_informed_valid_fixture` rows before widening the matrix.
```

- [ ] **Step 6: Run matrix tests**

Run:

```powershell
python -m pytest tests/test_matrix_visibility.py tests/test_archetype_fixture_matrix.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add src/hsconfig/matrix_visibility.py docs/operator/archetype-fixture-matrix.json docs/operator/README.md tests/test_matrix_visibility.py tests/test_archetype_fixture_matrix.py
git commit -m "feat: expose fixture matrix strongness visibility"
```

---

### Task 6: Keep Expert Paths Out Of The Normal Path

**Files:**
- Modify: `docs/operator/README.md`
- Modify: `README.md`
- Modify: `.agents/skills/hsconfig/SKILL.md`
- Modify: `.agents/skills/hsconfig/references/workflow.md`
- Modify: `tests/test_skill_files.py`
- Modify: `tests/test_scope_boundaries.py`

**Interfaces:**
- Consumes: Existing docs and skill text.
- Produces: Tests that prevent expert paths and post-run concepts from competing with normal operator guidance.

- [ ] **Step 1: Write failing scope tests**

Add to `tests/test_skill_files.py`:

```python
def test_normal_docs_keep_expert_paths_in_expert_sections():
    operator = Path("docs/operator/README.md").read_text(encoding="utf-8")
    expert_index = operator.index("## Expert Paths")
    normal_index = operator.index("## Normal Operator Path")

    assert normal_index < expert_index
    for token in ("--cards-json", "--claims-json", "--plan-reports-dir", "--allow-placeholder"):
        assert operator.index(token) > expert_index
```

Add to `tests/test_scope_boundaries.py`:

```python
def test_active_docs_keep_hstuner_scope_as_negative_boundary():
    active_docs = [
        Path("README.md"),
        Path("docs/operator/README.md"),
        Path(".agents/skills/hsconfig/SKILL.md"),
        Path(".agents/skills/hsconfig/references/workflow.md"),
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in active_docs)

    assert "does not parse replays" in combined
    assert "HSTuner" in combined
    assert "candidate promotion" not in Path("docs/operator/README.md").read_text(encoding="utf-8").lower()
```

- [ ] **Step 2: Run failing or focused tests**

Run:

```powershell
python -m pytest tests/test_skill_files.py::test_normal_docs_keep_expert_paths_in_expert_sections tests/test_scope_boundaries.py::test_active_docs_keep_hstuner_scope_as_negative_boundary -q
```

Expected: PASS only if Task 2 already placed expert paths correctly. If it fails, edit docs as described below.

- [ ] **Step 3: Tighten docs wording**

Ensure the normal sections in `README.md`, `docs/operator/README.md`, `.agents/skills/hsconfig/SKILL.md`, and `.agents/skills/hsconfig/references/workflow.md` use this boundary wording:

```markdown
HSConfig is pre-run only. It does not parse replays, inspect winrate, analyze runtime logs, promote candidates, or tune after games.
```

Ensure expert paths are only described under headings containing `Expert`.

- [ ] **Step 4: Sync installed skill**

Run:

```powershell
python scripts\sync_installed_skill.py
python scripts\sync_installed_skill.py --check
```

Expected: `HSConfig skill is in sync`.

- [ ] **Step 5: Run docs and scope tests**

Run:

```powershell
python -m pytest tests/test_skill_files.py tests/test_scope_boundaries.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add README.md docs/operator/README.md .agents/skills/hsconfig/SKILL.md .agents/skills/hsconfig/references/workflow.md tests/test_skill_files.py tests/test_scope_boundaries.py
git commit -m "docs: keep expert paths out of normal hsconfig flow"
```

---

### Task 7: End-To-End Verification And GitHub Sync

**Files:**
- No production files unless earlier tasks reveal a narrowly scoped defect.
- Test: full suite and workflow checks.

**Interfaces:**
- Consumes: All previous task commits.
- Produces: Verified `main` branch pushed to `origin/main`.

- [ ] **Step 1: Run focused operator UX tests**

Run:

```powershell
python -m pytest tests/test_cli_help.py tests/test_skill_files.py tests/test_scope_boundaries.py tests/test_operator_guidance.py tests/test_matrix_visibility.py -q
```

Expected: PASS.

- [ ] **Step 2: Run package workflow tests**

Run:

```powershell
python -m pytest tests/test_prepare_cli.py tests/test_apply_gate.py tests/test_runtime_apply.py tests/test_operator_summary.py tests/test_archetype_fixture_matrix.py tests/test_multideck_source_backed_e2e.py -q
```

Expected: PASS.

- [ ] **Step 3: Run full test suite**

Run:

```powershell
python -m pytest -q
```

Expected: PASS with no failures.

- [ ] **Step 4: Verify installed skill sync**

Run:

```powershell
python scripts\sync_installed_skill.py --check
```

Expected:

```text
HSConfig skill is in sync: C:\Users\darbo\.codex\skills\hsconfig
```

- [ ] **Step 5: Verify forbidden active scope terms**

Run:

```powershell
rg -n "Power\.log|hsreplay|HDT replay|winrate|candidate promotion|post-run tuning|analyze-step2" src\hsconfig
```

Expected: no matches and exit code `1`.

- [ ] **Step 6: Verify git status**

Run:

```powershell
git status --short --branch
```

Expected before final commit/push: either clean on the feature branch or only intentional plan/research/doc changes staged for commit.

- [ ] **Step 7: Confirm no verification-only files changed**

Task 7 should not change files. Run:

```powershell
git status --short
```

Expected: no unstaged or untracked files beyond intentional commits from Tasks 1-6. If verification created cache files, remove those cache files before continuing. If a source, test, or docs file changed during verification, stop and review that change before merging.

- [ ] **Step 8: Merge or fast-forward to main**

If implementing on a feature branch:

```powershell
git switch main
git merge --ff-only codex/hsconfig-lean-operator-ux-cli-slimming
python -m pytest -q
python scripts\sync_installed_skill.py --check
```

Expected: fast-forward succeeds, full suite passes, skill is in sync.

- [ ] **Step 9: Push main**

Run:

```powershell
git push origin main
```

Expected: `main -> main`.

---

## Self-Review Checklist

- [ ] The plan keeps HSConfig pre-run only.
- [ ] The plan does not add replay parsing, HDT parsing, winrate validation, candidate promotion, runtime evidence analysis, or post-run tuning.
- [ ] The plan adds no runtime dependency.
- [ ] The plan preserves `operator_summary.json` as the single normal operator gate.
- [ ] The plan preserves normal runtime files as `GlobalValues.json`, `Mulligan.json`, `<CARDID>.json`, and exact-sequence `Combo.json`.
- [ ] The plan adds one operator entry point instead of adding more competing docs.
- [ ] The plan improves `cli.py` maintainability by extracting parser construction only.
- [ ] The plan exposes 11-deck strongness visibility without adding new representative decks.
- [ ] The plan includes focused tests and full-suite verification.
- [ ] The plan includes skill sync verification.

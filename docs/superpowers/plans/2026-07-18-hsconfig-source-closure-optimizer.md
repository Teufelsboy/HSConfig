# HSConfig Source Closure Optimizer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a small diagnostic-only "source closure optimizer" layer that proves the best possible current source/contract status for freshly generated HSConfig packages, keeps `SOURCE_BACKED_STRONG` honest, prevents hidden `default_only` runtime output, and never blocks a technically valid load-safe deck package because public Wild guide coverage is partial.

**Architecture:** Reuse existing package authority and reports. `reports/operator_summary.json` stays the single normal apply authority. New code reads existing package summaries plus the source-candidate proof manifest and produces a compact closure decision report. The report classifies each deck as `strong`, `partial_source_action_needed`, `preserved_partial_stop_condition`, `context_only_load_safe`, or `invalid_package`. It is diagnostic-only and has no runtime write path.

**Tech Stack:** Python package `hsconfig`, existing argparse CLI, JSON diagnostics, Markdown report generation, pytest, existing files under `docs/operator/`, `.agents/skills/hsconfig/`, and `docs/superpowers/plans/`.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig`.
- Before implementation, run:
  - `git fetch --all --prune --tags`
  - `git status --short --branch`
- Do not start code changes if the worktree is dirty with unrelated user work.
- Do not create shadow workspaces.
- Do not write HearthRanger runtime files during this implementation.
- Do not call `hsconfig apply`, `hsconfig configure --apply`, or lower-level runtime write helpers during tests unless a test uses an isolated temporary directory and never targets the real runtime.
- `reports/operator_summary.json` remains the only normal apply authority.
- `SOURCE_BACKED_STRONG` remains a source-confidence/evidence-quality label, not an apply or generation gate.
- Candidate registries are source acquisition seeds only. They must not promote `SOURCE_BACKED_STRONG` without fetched, deck-matched, claim-kind-normalized, surface-gated evidence.
- `default_only_runtime_surfaces != []` must prevent `SOURCE_BACKED_STRONG`, but must not invalidate or block an otherwise load-safe package.
- `source_status_apply_blocking` must stay `false` for source-depth gaps.
- Darkbishop Benedictus handling remains split:
  - preserve start-of-game / hero-power-transform runtime semantics,
  - do not emit opening-hand keep behavior unless a source explicitly says to keep it.
- Keep the solution lean: one pure module, one CLI command, focused docs, focused tests.
- End with a clean worktree. Commit the completed plan or implementation artifacts when the user requested no dirty worktree.

---

## Task 1: Add Pure Closure Optimizer Module

**Files:**

- Create `src/hsconfig/source_closure_optimizer.py`
- Create `tests/test_source_closure_optimizer.py`

**Intent:** Make source status explicit and machine-checkable without touching package generation or runtime apply logic.

### Tests First

Add `tests/test_source_closure_optimizer.py` with these tests:

```python
from __future__ import annotations

import json
from pathlib import Path

from hsconfig.source_closure_optimizer import build_source_closure_optimizer_report


def _write_package(tmp_path: Path, operator: dict) -> Path:
    package = tmp_path / "04_package"
    reports = package / "reports"
    reports.mkdir(parents=True)
    (reports / "operator_summary.json").write_text(
        json.dumps(operator, indent=2),
        encoding="utf-8",
    )
    return package


def _operator(**overrides: object) -> dict:
    payload = {
        "deck_name": "ShadowPriest",
        "technical_status": "VALID_PACKAGE",
        "runtime_load_safe": True,
        "source_status_apply_blocking": False,
        "source_backed_status": "SOURCE_BACKED_STRONG",
        "semantic_status": "SOURCE_BACKED_STRONG",
        "default_only_runtime_surfaces": [],
        "default_only_runtime_surface_details": [],
        "no_default_only_runtime_status": "clean",
        "source_backed_strong_closure": {
            "closed": True,
            "first_missing_source_action": "none",
        },
    }
    payload.update(overrides)
    return payload


def test_shadowpriest_strong_when_operator_closure_is_clean(tmp_path: Path) -> None:
    package = _write_package(tmp_path, _operator())

    report = build_source_closure_optimizer_report(package)

    assert report["decision"] == "strong"
    assert report["source_status_apply_blocking"] is False
    assert report["runtime_package_usable"] is True
    assert report["default_only_blocks_strong"] is False
    assert report["first_missing_source_action"] == "none"


def test_default_only_never_promotes_to_strong(tmp_path: Path) -> None:
    package = _write_package(
        tmp_path,
        _operator(
            source_backed_status="SOURCE_BACKED_STRONG",
            semantic_status="SOURCE_BACKED_STRONG",
            default_only_runtime_surfaces=["Mulligan.json"],
            default_only_runtime_surface_details=[
                {
                    "surface": "Mulligan.json",
                    "reason": "default_only_surface_not_strong_evidence",
                }
            ],
            no_default_only_runtime_status="blocked",
        ),
    )

    report = build_source_closure_optimizer_report(package)

    assert report["decision"] == "partial_source_action_needed"
    assert report["source_status_apply_blocking"] is False
    assert report["runtime_package_usable"] is True
    assert report["default_only_blocks_strong"] is True
    assert report["blocking_reasons"] == ["default_only_runtime_surfaces_present"]


def test_preserves_known_partial_stop_conditions(tmp_path: Path) -> None:
    package = _write_package(
        tmp_path,
        _operator(
            deck_name="Kingslayer",
            source_backed_status="SOURCE_BACKED_PARTIAL",
            semantic_status="VALID_BUT_NOT_GUIDE_STRONG",
            source_backed_strong_closure={
                "closed": False,
                "first_missing_source_action": "add_kingslayer_quick_pick_mulligan_source",
            },
        ),
    )

    report = build_source_closure_optimizer_report(package)

    assert report["decision"] == "preserved_partial_stop_condition"
    assert report["first_missing_source_action"] == "add_kingslayer_quick_pick_mulligan_source"
    assert report["source_status_apply_blocking"] is False
    assert report["runtime_package_usable"] is True


def test_context_only_candidate_is_load_safe_not_strong(tmp_path: Path) -> None:
    package = _write_package(
        tmp_path,
        _operator(
            deck_name="SyntheticContextOnly",
            source_backed_status="STATIC_SEMANTICS_USABLE",
            semantic_status="VALID_BUT_NOT_GUIDE_STRONG",
            source_backed_strong_closure={
                "closed": False,
                "first_missing_source_action": "fetch_runtime_lowerable_public_guide",
            },
        ),
    )
    manifest = tmp_path / "source-candidate-proof-decks.json"
    manifest.write_text(
        json.dumps(
            {
                "decks": [
                    {
                        "deck_name": "SyntheticContextOnly",
                        "expected_strength_ceiling": "context_only",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    report = build_source_closure_optimizer_report(
        package,
        candidate_proof_path=manifest,
    )

    assert report["decision"] == "context_only_load_safe"
    assert report["runtime_package_usable"] is True
    assert report["source_status_apply_blocking"] is False


def test_invalid_package_is_invalid_even_if_source_fields_are_present(tmp_path: Path) -> None:
    package = _write_package(
        tmp_path,
        _operator(
            technical_status="INVALID_PACKAGE",
            runtime_load_safe=False,
        ),
    )

    report = build_source_closure_optimizer_report(package)

    assert report["decision"] == "invalid_package"
    assert report["runtime_package_usable"] is False
```

Run the new tests and confirm they fail before implementation:

```powershell
python -m pytest tests/test_source_closure_optimizer.py -q
```

### Implementation

Create `src/hsconfig/source_closure_optimizer.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


OPERATOR_SUMMARY_RELATIVE_PATH = Path("reports") / "operator_summary.json"

PARTIAL_STOP_CONDITIONS = {
    "Boarlock": {
        "allowed_actions": {"add_boarlock_fracking_mulligan_source"},
        "reason": "checked public context does not expose explicit Fracking keep/discard text",
    },
    "Kingslayer": {
        "allowed_actions": {"add_kingslayer_quick_pick_mulligan_source"},
        "reason": "checked public context does not expose explicit Quick Pick mulligan text",
    },
}


def build_source_closure_optimizer_report(
    package_dir: str | Path,
    *,
    candidate_proof_path: str | Path | None = None,
    dossier: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    package_path = Path(package_dir)
    operator_summary = _read_json(package_path / OPERATOR_SUMMARY_RELATIVE_PATH)
    deck_name = _deck_name(operator_summary, package_path)
    candidate_row = _candidate_row(deck_name, candidate_proof_path)
    decision_payload = _classify(
        deck_name=deck_name,
        operator_summary=operator_summary,
        candidate_row=candidate_row,
        dossier=dict(dossier or {}),
    )

    runtime_package_usable = (
        operator_summary.get("technical_status") == "VALID_PACKAGE"
        and operator_summary.get("runtime_load_safe") is not False
    )
    closure = operator_summary.get("source_backed_strong_closure") or {}

    return {
        "schema_version": 1,
        "authority": "diagnostic_only",
        "normal_apply_authority": str(OPERATOR_SUMMARY_RELATIVE_PATH),
        "deck_name": deck_name,
        "package_dir": str(package_path),
        "decision": decision_payload["decision"],
        "decision_reason": decision_payload["reason"],
        "recommended_operator_action": decision_payload["action"],
        "technical_status": operator_summary.get("technical_status"),
        "runtime_package_usable": runtime_package_usable,
        "source_status_apply_blocking": bool(
            operator_summary.get("source_status_apply_blocking", False)
        ),
        "source_backed_status": operator_summary.get("source_backed_status"),
        "semantic_status": operator_summary.get("semantic_status"),
        "source_backed_strong_closed": bool(closure.get("closed", False)),
        "first_missing_source_action": closure.get("first_missing_source_action", "unknown"),
        "default_only_runtime_surfaces": list(
            operator_summary.get("default_only_runtime_surfaces") or []
        ),
        "default_only_blocks_strong": decision_payload["default_only_blocks_strong"],
        "blocking_reasons": decision_payload["blocking_reasons"],
        "candidate_strength_ceiling": candidate_row.get("expected_strength_ceiling"),
        "candidate_manifest_row_found": bool(candidate_row),
    }


def _classify(
    *,
    deck_name: str,
    operator_summary: Mapping[str, Any],
    candidate_row: Mapping[str, Any],
    dossier: Mapping[str, Any],
) -> dict[str, Any]:
    default_only_surfaces = list(operator_summary.get("default_only_runtime_surfaces") or [])
    closure = operator_summary.get("source_backed_strong_closure") or {}
    first_action = str(closure.get("first_missing_source_action") or "unknown")
    candidate_ceiling = str(candidate_row.get("expected_strength_ceiling") or "")

    if operator_summary.get("technical_status") != "VALID_PACKAGE":
        return _decision(
            "invalid_package",
            "technical package status is not VALID_PACKAGE",
            "fix package validity before source-depth closure",
        )

    if default_only_surfaces:
        return _decision(
            "partial_source_action_needed",
            "default-only runtime surfaces are visible and cannot prove Strong",
            "replace default-only runtime surfaces with source-backed, policy-backed, or static-semantics-backed rows",
            default_only_blocks_strong=True,
            blocking_reasons=["default_only_runtime_surfaces_present"],
        )

    if (
        operator_summary.get("source_backed_status") == "SOURCE_BACKED_STRONG"
        and operator_summary.get("semantic_status") == "SOURCE_BACKED_STRONG"
        and closure.get("closed") is True
        and first_action == "none"
        and not _dossier_reports_open_action(dossier)
    ):
        return _decision(
            "strong",
            "operator summary closes Strong without default-only runtime surfaces",
            "none",
        )

    stop_condition = PARTIAL_STOP_CONDITIONS.get(deck_name)
    if stop_condition and first_action in stop_condition["allowed_actions"]:
        return _decision(
            "preserved_partial_stop_condition",
            stop_condition["reason"],
            first_action,
        )

    if candidate_ceiling == "context_only":
        return _decision(
            "context_only_load_safe",
            "candidate manifest exposes context only and cannot close runtime surfaces",
            first_action,
        )

    return _decision(
        "partial_source_action_needed",
        "source-depth closure still has an explicit missing source action",
        first_action,
    )


def _decision(
    decision: str,
    reason: str,
    action: str,
    *,
    default_only_blocks_strong: bool = False,
    blocking_reasons: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "decision": decision,
        "reason": reason,
        "action": action,
        "default_only_blocks_strong": default_only_blocks_strong,
        "blocking_reasons": list(blocking_reasons or []),
    }


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _deck_name(operator_summary: Mapping[str, Any], package_path: Path) -> str:
    value = operator_summary.get("deck_name") or operator_summary.get("deck")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return package_path.parent.name or package_path.name


def _candidate_row(
    deck_name: str,
    candidate_proof_path: str | Path | None,
) -> dict[str, Any]:
    if candidate_proof_path is None:
        return {}
    payload = _read_json(Path(candidate_proof_path))
    for row in payload.get("decks", []):
        if row.get("deck_name") == deck_name:
            return dict(row)
    return {}


def _dossier_reports_open_action(dossier: Mapping[str, Any]) -> bool:
    if not dossier:
        return False
    action = dossier.get("first_missing_source_action")
    return bool(action and action != "none")
```

Implementation notes:

- Keep all functions pure except JSON file reads.
- Do not import runtime writer modules.
- Do not mutate `operator_summary.json`.
- Do not infer Strong from candidate rows.
- The classifier trusts `operator_summary.json` only for current package state, then uses the candidate manifest only to explain expected source-ceiling context.

Run:

```powershell
python -m pytest tests/test_source_closure_optimizer.py -q
```

---

## Task 2: Add CLI Command For Batch Diagnostics

**Files:**

- Modify `src/hsconfig/cli_parser.py`
- Modify `src/hsconfig/cli.py`
- Modify `src/hsconfig/commands/source_workflow.py`
- Create `tests/test_source_closure_optimizer_cli.py`

**Intent:** Operators and subagents need one command that audits one or more prepared packages without creating runtime writes or pretending source gaps block config generation.

### Parser

Add a parser in `src/hsconfig/cli_parser.py`:

```python
    source_closure_optimizer = subparsers.add_parser(
        "source-closure-optimizer",
        help="Write diagnostic-only source closure decisions for prepared packages.",
    )
    source_closure_optimizer.add_argument(
        "--package",
        action="append",
        required=True,
        help="Path to a prepared 04_package directory. Can be passed more than once.",
    )
    source_closure_optimizer.add_argument(
        "--candidate-proof-json",
        default="docs/operator/source-candidate-proof-decks.json",
        help="Source candidate proof manifest used for source-ceiling context.",
    )
    source_closure_optimizer.add_argument(
        "--out",
        required=True,
        help="Diagnostic JSON output path. Must not be inside a package reports directory.",
    )
    source_closure_optimizer.add_argument(
        "--markdown-out",
        help="Optional diagnostic Markdown summary output path.",
    )
```

### CLI Dispatch

In `src/hsconfig/cli.py`, dispatch:

```python
    if args.command == "source-closure-optimizer":
        return run_source_closure_optimizer_command(args)
```

Use the same import pattern as existing source workflow commands.

### Command Implementation

In `src/hsconfig/commands/source_workflow.py`, add:

```python
from hsconfig.source_closure_optimizer import build_source_closure_optimizer_report


def run_source_closure_optimizer_command(args: argparse.Namespace) -> int:
    reports = [
        build_source_closure_optimizer_report(
            package_dir=package,
            candidate_proof_path=args.candidate_proof_json,
        )
        for package in args.package
    ]
    payload = {
        "schema_version": 1,
        "authority": "diagnostic_only",
        "source_status_apply_blocking": False,
        "package_count": len(reports),
        "reports": reports,
    }
    out_path = Path(args.out)
    _assert_safe_closure_optimizer_output(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if args.markdown_out:
        md_path = Path(args.markdown_out)
        _assert_safe_closure_optimizer_output(md_path)
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(_format_source_closure_optimizer_markdown(payload), encoding="utf-8")

    print(f"Wrote source closure optimizer report: {out_path}")
    return 0
```

Add the safety helper near existing diagnostic output guards:

```python
def _assert_safe_closure_optimizer_output(path: Path) -> None:
    lowered_parts = {part.lower() for part in path.parts}
    if "reports" in lowered_parts and path.name == "operator_summary.json":
        raise ValueError("source-closure-optimizer must not overwrite operator_summary.json")
    if path.name in {"Mulligan.json", "GlobalValues.json", "Combo.json"}:
        raise ValueError("source-closure-optimizer output must be diagnostic only")
```

Add Markdown formatter:

```python
def _format_source_closure_optimizer_markdown(payload: Mapping[str, Any]) -> str:
    lines = [
        "# HSConfig Source Closure Optimizer",
        "",
        f"- Authority: `{payload['authority']}`",
        f"- Source status apply blocking: `{payload['source_status_apply_blocking']}`",
        f"- Package count: `{payload['package_count']}`",
        "",
        "| Deck | Decision | Runtime usable | First missing source action | Default-only surfaces |",
        "| --- | --- | --- | --- | --- |",
    ]
    for report in payload["reports"]:
        default_only = ", ".join(report["default_only_runtime_surfaces"]) or "none"
        lines.append(
            "| {deck} | `{decision}` | `{usable}` | `{action}` | `{default_only}` |".format(
                deck=report["deck_name"],
                decision=report["decision"],
                usable=report["runtime_package_usable"],
                action=report["first_missing_source_action"],
                default_only=default_only,
            )
        )
    lines.append("")
    return "\n".join(lines)
```

### CLI Tests

Create `tests/test_source_closure_optimizer_cli.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from hsconfig.cli import main


def _write_package(root: Path, deck_name: str) -> Path:
    package = root / deck_name / "04_package"
    reports = package / "reports"
    reports.mkdir(parents=True)
    (reports / "operator_summary.json").write_text(
        json.dumps(
            {
                "deck_name": deck_name,
                "technical_status": "VALID_PACKAGE",
                "runtime_load_safe": True,
                "source_status_apply_blocking": False,
                "source_backed_status": "SOURCE_BACKED_STRONG",
                "semantic_status": "SOURCE_BACKED_STRONG",
                "default_only_runtime_surfaces": [],
                "source_backed_strong_closure": {
                    "closed": True,
                    "first_missing_source_action": "none",
                },
            }
        ),
        encoding="utf-8",
    )
    return package


def test_source_closure_optimizer_writes_batch_json_and_markdown(tmp_path: Path) -> None:
    package = _write_package(tmp_path, "ShadowPriest")
    out_json = tmp_path / "diagnostics" / "source_closure_optimizer.json"
    out_md = tmp_path / "diagnostics" / "source_closure_optimizer.md"

    exit_code = main(
        [
            "source-closure-optimizer",
            "--package",
            str(package),
            "--out",
            str(out_json),
            "--markdown-out",
            str(out_md),
        ]
    )

    assert exit_code == 0
    payload = json.loads(out_json.read_text(encoding="utf-8"))
    assert payload["authority"] == "diagnostic_only"
    assert payload["source_status_apply_blocking"] is False
    assert payload["reports"][0]["decision"] == "strong"
    assert "ShadowPriest" in out_md.read_text(encoding="utf-8")


def test_source_closure_optimizer_rejects_operator_summary_overwrite(tmp_path: Path) -> None:
    package = _write_package(tmp_path, "ShadowPriest")
    unsafe = package / "reports" / "operator_summary.json"

    try:
        main(
            [
                "source-closure-optimizer",
                "--package",
                str(package),
                "--out",
                str(unsafe),
            ]
        )
    except ValueError as exc:
        assert "operator_summary.json" in str(exc)
    else:
        raise AssertionError("expected diagnostic overwrite guard")
```

Run:

```powershell
python -m pytest tests/test_source_closure_optimizer.py tests/test_source_closure_optimizer_cli.py -q
```

---

## Task 3: Wire Matrix Coverage Without Expanding Runtime Scope

**Files:**

- Modify `tests/test_universal_wild_no_block_matrix.py`
- Create `tests/test_source_closure_optimizer_matrix.py`
- Use existing `docs/operator/source-candidate-proof-decks.json`
- Use existing `docs/research/current-truth-index.json`

**Intent:** The representative Wild deck set must stay load-safe, source-honest, and non-blocking. ShadowPriest should prove Strong when the source contract is actually closed. Kingslayer and Boarlock should preserve their known partial stop conditions instead of silently inventing keeps.

### Add Matrix Test

Create `tests/test_source_closure_optimizer_matrix.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from hsconfig.source_closure_optimizer import build_source_closure_optimizer_report


DECKS = {
    "ShadowPriest": {
        "status": "SOURCE_BACKED_STRONG",
        "semantic": "SOURCE_BACKED_STRONG",
        "closed": True,
        "action": "none",
        "decision": "strong",
    },
    "Kingslayer": {
        "status": "SOURCE_BACKED_PARTIAL",
        "semantic": "VALID_BUT_NOT_GUIDE_STRONG",
        "closed": False,
        "action": "add_kingslayer_quick_pick_mulligan_source",
        "decision": "preserved_partial_stop_condition",
    },
    "Boarlock": {
        "status": "SOURCE_BACKED_PARTIAL",
        "semantic": "VALID_BUT_NOT_GUIDE_STRONG",
        "closed": False,
        "action": "add_boarlock_fracking_mulligan_source",
        "decision": "preserved_partial_stop_condition",
    },
    "MechPala": {
        "status": "SOURCE_BACKED_PARTIAL",
        "semantic": "VALID_BUT_NOT_GUIDE_STRONG",
        "closed": False,
        "action": "fetch_runtime_lowerable_public_guide",
        "decision": "partial_source_action_needed",
    },
}


def _write_package(tmp_path: Path, deck_name: str, row: dict[str, object]) -> Path:
    package = tmp_path / deck_name / "04_package"
    reports = package / "reports"
    reports.mkdir(parents=True)
    (reports / "operator_summary.json").write_text(
        json.dumps(
            {
                "deck_name": deck_name,
                "technical_status": "VALID_PACKAGE",
                "runtime_load_safe": True,
                "source_status_apply_blocking": False,
                "source_backed_status": row["status"],
                "semantic_status": row["semantic"],
                "default_only_runtime_surfaces": [],
                "default_only_runtime_surface_details": [],
                "no_default_only_runtime_status": "clean",
                "source_backed_strong_closure": {
                    "closed": row["closed"],
                    "first_missing_source_action": row["action"],
                },
            }
        ),
        encoding="utf-8",
    )
    return package


def test_source_closure_optimizer_preserves_representative_deck_contracts(tmp_path: Path) -> None:
    proof_manifest = Path("docs/operator/source-candidate-proof-decks.json")
    assert proof_manifest.exists()

    for deck_name, row in DECKS.items():
        package = _write_package(tmp_path, deck_name, row)
        report = build_source_closure_optimizer_report(
            package,
            candidate_proof_path=proof_manifest,
        )

        assert report["deck_name"] == deck_name
        assert report["decision"] == row["decision"]
        assert report["source_status_apply_blocking"] is False
        assert report["runtime_package_usable"] is True
        assert report["default_only_runtime_surfaces"] == []
```

### Tighten Existing Universal No-Block Matrix

In `tests/test_universal_wild_no_block_matrix.py`, add or preserve assertions:

```python
assert operator["source_status_apply_blocking"] is False
assert operator["default_only_runtime_surfaces"] == []
assert operator["default_only_runtime_surface_details"] == []
assert operator["no_default_only_runtime_status"] == "clean"
```

For ShadowPriest Darkbishop, keep the existing boundary:

```python
assert not any(
    row.get("mulligan") == "SW_448" or row.get("card_id") == "SW_448"
    for row in mulligan_rows
)
assert (deck_dir / "SW_448.json").exists()
```

Run:

```powershell
python -m pytest tests/test_source_closure_optimizer_matrix.py tests/test_universal_wild_no_block_matrix.py -q
```

---

## Task 4: Update Operator Docs And Skill Contract

**Files:**

- Modify `docs/operator/source-backed-strong-closure.md`
- Modify `docs/operator/guide-research-policy.md`
- Modify `.agents/skills/hsconfig/SKILL.md`
- Modify `.agents/skills/hsconfig/references/workflow.md`
- Modify `tests/test_skill_files.py`

**Intent:** The operator and skill text should say exactly how to interpret the new diagnostic report. It must not imply a second apply authority.

### Documentation Patch

Add this section to `docs/operator/source-backed-strong-closure.md`:

```markdown
## Source Closure Optimizer

`hsconfig source-closure-optimizer` is a diagnostic-only batch report for
freshly prepared packages. It reads `reports/operator_summary.json`, optional
source-candidate proof context, and closure summaries. It does not write runtime
files and does not replace `operator_summary.json`.

The command may classify a package as:

- `strong`: `SOURCE_BACKED_STRONG` is closed, no default-only runtime surfaces
  are visible, and `first_missing_source_action=none`.
- `partial_source_action_needed`: the package is load-safe, but at least one
  source-to-runtime link remains open.
- `preserved_partial_stop_condition`: the package is load-safe and the current
  missing action is an intentional, documented stop condition such as
  Kingslayer Quick Pick mulligan evidence or Boarlock Fracking mulligan
  evidence.
- `context_only_load_safe`: public candidate material is useful for navigation
  or archetype context, but it cannot close runtime surfaces.
- `invalid_package`: the package is technically invalid and must be fixed before
  source closure matters.

`default_only_runtime_surfaces` prevents `strong`, but it must not turn source
depth into a runtime apply block. `source_status_apply_blocking` remains false
for source-depth gaps.
```

Add this compact note to `.agents/skills/hsconfig/SKILL.md` and `.agents/skills/hsconfig/references/workflow.md`:

```markdown
Use `hsconfig source-closure-optimizer` only as a diagnostic closure view. It
does not apply runtime files, does not promote candidate URLs to
`SOURCE_BACKED_STRONG`, and does not replace `reports/operator_summary.json`.
```

### Skill File Tests

In `tests/test_skill_files.py`, add:

```python
def test_hsconfig_skill_documents_source_closure_optimizer_boundary() -> None:
    skill = Path(".agents/skills/hsconfig/SKILL.md").read_text(encoding="utf-8")
    workflow = Path(".agents/skills/hsconfig/references/workflow.md").read_text(
        encoding="utf-8"
    )

    for text in (skill, workflow):
        assert "source-closure-optimizer" in text
        assert "diagnostic" in text.lower()
        assert "does not replace `reports/operator_summary.json`" in text
```

Run:

```powershell
python -m pytest tests/test_skill_files.py -q
```

---

## Task 5: Verify Against Current Source Candidate Deck Set

**Files:**

- No committed generated package outputs.
- Use ignored diagnostic outputs under `tmp/source-closure-optimizer/`.

**Intent:** The implementation should support the current representative decks without blocking any valid config and without hidden default-only output.

### Deck Matrix

Use the existing manifest as the source of deck names and deck codes:

```text
docs/operator/source-candidate-proof-decks.json
```

It must cover at least:

- `ShadowPriest`
- `CtAPaladin`
- `PirateRogue`
- `BigShaman`
- `Discolock`
- `TreantDruid`
- `ImbueMage`
- `MechPala`
- `Kingslayer`
- `Boarlock`
- `PirateDH`
- `CuteWarrior`

### Optional Fresh Online Package Check

Only run this if online source refresh is required during implementation review. Keep outputs ignored:

```powershell
$outRoot = "tmp/source-closure-optimizer/packages"
New-Item -ItemType Directory -Force -Path $outRoot | Out-Null
python -m hsconfig source-refresh-proof-decks `
  --proof-json docs/operator/source-candidate-proof-decks.json `
  --out-dir $outRoot `
  --online-source `
  --auto-source
```

If that helper command does not exist, do not invent one. Use the currently supported `hsconfig configure --online-source --auto-source --out-dir ...` command for each row in `docs/operator/source-candidate-proof-decks.json`.

Then run the new diagnostic command over generated `04_package` directories:

```powershell
$packages = Get-ChildItem -Path "tmp/source-closure-optimizer/packages" -Recurse -Directory -Filter "04_package" |
  ForEach-Object { "--package `"$($_.FullName)`"" }
python -m hsconfig source-closure-optimizer `
  $packages `
  --candidate-proof-json docs/operator/source-candidate-proof-decks.json `
  --out tmp/source-closure-optimizer/source_closure_optimizer.json `
  --markdown-out tmp/source-closure-optimizer/source_closure_optimizer.md
```

Manual acceptance for the diagnostic payload:

- `authority == "diagnostic_only"`
- top-level `source_status_apply_blocking == false`
- every report with `technical_status == "VALID_PACKAGE"` has `runtime_package_usable == true`
- no report with `default_only_runtime_surfaces != []` has `decision == "strong"`
- `ShadowPriest` is `strong` only when `first_missing_source_action == "none"`
- `Kingslayer` may be `preserved_partial_stop_condition` with `add_kingslayer_quick_pick_mulligan_source`
- `Boarlock` may be `preserved_partial_stop_condition` with `add_boarlock_fracking_mulligan_source`
- no diagnostic output is written into a runtime package file or real HearthRanger runtime directory

---

## Task 6: Full Verification And Review

Run focused tests:

```powershell
python -m pytest `
  tests/test_source_closure_optimizer.py `
  tests/test_source_closure_optimizer_cli.py `
  tests/test_source_closure_optimizer_matrix.py `
  tests/test_universal_wild_no_block_matrix.py `
  tests/test_source_candidate_registry_matrix.py `
  tests/test_strong_closure_dossier.py `
  tests/test_strong_promotion_report.py `
  tests/test_skill_files.py `
  -q
```

Run full test suite unless it is prohibitively slow:

```powershell
python -m pytest -q
```

Check formatting and accidental runtime artifacts:

```powershell
git diff --check
git status --short --branch
git diff --stat
```

Search for forbidden behavior:

```powershell
rg -n "source_status_apply_blocking.*true|candidate.*SOURCE_BACKED_STRONG|default_only.*decision.*strong" src tests docs .agents
```

The search may find tests that assert forbidden behavior is rejected. It must not find implementation code that enables the forbidden behavior.

---

## Task 7: Self-Review Checklist

- [ ] The new classifier is pure and does not import runtime writer modules.
- [ ] The CLI writes diagnostic JSON/Markdown only.
- [ ] `operator_summary.json` remains the normal apply authority.
- [ ] `SOURCE_BACKED_STRONG` is not inferred from candidate URLs or decklists.
- [ ] `default_only_runtime_surfaces` prevents `strong`.
- [ ] Source-depth gaps do not block load-safe valid packages.
- [ ] Darkbishop Benedictus effect semantics remain separate from opening-hand keep logic.
- [ ] Representative deck matrix includes ShadowPriest, Kingslayer, Boarlock, and at least one partial non-stop deck.
- [ ] Docs and skill text mention the new command without expanding scope.
- [ ] Temporary online verification outputs stay under ignored `tmp/`.
- [ ] Worktree is clean after commit.

---

## Execution Handoff

Use `superpowers:subagent-driven-development` for implementation:

- Agent A: implement Task 1 tests and pure module only.
- Agent B: implement Task 2 CLI and CLI tests only.
- Agent C: implement Task 3 matrix tests and Task 4 docs/skill text only.
- Agent D: read-only review of default-only, apply-authority, Darkbishop, and source-candidate promotion boundaries.

Rules for subagents:

- Exactly one agent writes each file area.
- No subagent writes runtime artifacts.
- No subagent applies HearthRanger runtime config.
- Main agent consolidates results, runs verification, reviews diff, and commits.

Recommended commits:

```powershell
git add src/hsconfig/source_closure_optimizer.py tests/test_source_closure_optimizer.py
git commit -m "feat: add source closure optimizer diagnostic"

git add src/hsconfig/cli.py src/hsconfig/cli_parser.py src/hsconfig/commands/source_workflow.py tests/test_source_closure_optimizer_cli.py
git commit -m "feat: expose source closure optimizer cli"

git add docs/operator/source-backed-strong-closure.md docs/operator/guide-research-policy.md .agents/skills/hsconfig/SKILL.md .agents/skills/hsconfig/references/workflow.md tests/test_skill_files.py tests/test_source_closure_optimizer_matrix.py tests/test_universal_wild_no_block_matrix.py
git commit -m "docs: document source closure optimizer contract"
```

If the user asks for one atomic commit instead, stage all implementation files and commit:

```powershell
git add src/hsconfig/source_closure_optimizer.py src/hsconfig/cli.py src/hsconfig/cli_parser.py src/hsconfig/commands/source_workflow.py tests/test_source_closure_optimizer.py tests/test_source_closure_optimizer_cli.py tests/test_source_closure_optimizer_matrix.py tests/test_universal_wild_no_block_matrix.py tests/test_skill_files.py docs/operator/source-backed-strong-closure.md docs/operator/guide-research-policy.md .agents/skills/hsconfig/SKILL.md .agents/skills/hsconfig/references/workflow.md
git commit -m "feat: add source closure optimizer"
```

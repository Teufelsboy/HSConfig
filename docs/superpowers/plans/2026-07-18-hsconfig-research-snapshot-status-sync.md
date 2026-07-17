# HSConfig Research Snapshot Status Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a narrow diagnostic sync layer that compares historical `research-deep` result snapshots with the canonical prepared package status so stale or seed-only research cannot downgrade, promote, or confuse `SOURCE_BACKED_STRONG` package truth.

**Architecture:** Keep `reports/operator_summary.json` as the only normal apply authority and keep the already implemented `source_status_resolver` as the canonical source-status logic. Add a read-only `research_status_sync` diagnostic module plus an optional CLI command that labels research result JSONs as `current_with_canonical`, `stale_or_seed_only`, `conflicts_with_canonical`, or `missing`, without changing package generation or runtime apply behavior.

**Tech Stack:** Python 3.11, pytest, existing HSConfig CLI patterns, existing JSON report conventions, existing docs/skill sync flow.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig`.
- Refresh repository state before implementation with `git fetch --all --prune --tags`.
- Keep the worktree clean at handoff; commit the plan or implementation locally when the user has asked for no dirty worktree.
- Do not push unless explicitly requested.
- Do not modify generated runtime outputs, live HearthRanger runtime files, replays, logs, or private evidence.
- `operator_summary.json` remains the only normal apply authority.
- `SOURCE_BACKED_STRONG` is an evidence-quality label, not a runtime apply gate.
- `source_status_apply_blocking` must remain `false` for source-depth and research-snapshot drift.
- Research artifacts are evidence snapshots only. They do not authorize runtime writes, and they do not override active operator docs, installed skill text, or `operator_summary.json`.
- Decklists, snippets, candidate URLs, HSGuru/HSReplay aggregate stats, and `research-deep` `unfetched_acquisition_seed` rows are acquisition/support signals only and cannot promote `SOURCE_BACKED_STRONG`.
- Default-only runtime surfaces must prevent `SOURCE_BACKED_STRONG`, but default-only visibility is diagnostic unless the package is structurally invalid.
- ShadowPriest must preserve Darkbishop Benedictus `SW_448` effect semantics while avoiding automatic opening-hand Mulligan keep behavior.

---

## File Structure

- Create `src/hsconfig/research_status_sync.py`: pure read/compare logic for package operator summary plus research result JSON rows.
- Create `tests/test_research_status_sync.py`: unit tests for stale/seed snapshots, matching strong snapshots, conflicting research snapshots, missing research rows, and no-apply-authority guarantees.
- Modify `src/hsconfig/commands/source_workflow.py`: add a read-only payload wrapper for the sync report.
- Modify `src/hsconfig/cli_parser.py`: add `research-status-sync` command arguments.
- Modify `src/hsconfig/cli.py`: route `research-status-sync` to the command wrapper.
- Create `tests/test_research_status_sync_cli.py`: CLI smoke tests that prove the command reads package/research files, writes optional JSON, and stays diagnostic-only.
- Modify `docs/research/current-truth.md`: document that stale `research-deep` snapshots can be superseded by canonical package reports.
- Modify `docs/research/current-truth-index.json`: add a machine-readable note for `research_snapshot_sync_policy`.
- Modify `docs/operator/source-backed-strong-closure.md`: add one short operator paragraph explaining the sync diagnostic.
- Modify `.agents/skills/hsconfig/SKILL.md`: add one compact skill rule for package-vs-research status conflicts.
- Modify `tests/test_research_current_truth.py` or `tests/test_docs_active_path.py`: lock the new documentation boundary.

---

### Task 1: Refresh And Confirm Baseline

**Files:**
- Read-only: git metadata
- Read-only: `src/hsconfig/source_status_resolver.py`
- Read-only: `docs/superpowers/plans/2026-07-17-hsconfig-canonical-source-status-sync.md`

**Interfaces:**
- Consumes: current branch, upstream state, existing resolver implementation, clean/dirty worktree status.
- Produces: confirmed baseline that this plan is a follow-up, not a duplicate resolver rewrite.

- [ ] **Step 1: Refresh remotes**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
git fetch --all --prune --tags
```

Expected: exit code `0`.

- [ ] **Step 2: Inspect branch and dirty state**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
git status --short --branch
git rev-list --left-right --count HEAD...origin/main
```

Expected: current branch is visible; worktree is clean before implementation. If the branch is ahead of `origin/main`, keep the local commits and do not reset or push.

- [ ] **Step 3: Verify canonical resolver already exists**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python -m pytest tests/test_source_status_resolver.py -q
```

Expected: resolver tests pass. This confirms the new work should compare research snapshots against the existing canonical status, not recreate status resolution.

---

### Task 2: Add Pure Research Snapshot Status Sync Logic

**Files:**
- Create: `src/hsconfig/research_status_sync.py`
- Create: `tests/test_research_status_sync.py`

**Interfaces:**
- Consumes:
  - `package_dir: str | Path`
  - `research_result_paths: Sequence[str | Path]`
  - `reports/operator_summary.json`
  - `research-deep` result fields: `deck_name`, `source_strength`, `source_backed_status`, `source_strength`, `first_missing_source_action`, `first_missing_source_action`, `notes`
- Produces:
  - `build_research_status_sync_report(package_dir, research_result_paths) -> dict[str, Any]`
  - rows with `snapshot_relation`, `research_snapshot_kind`, `canonical_downgrade_allowed=false`, `canonical_promotion_allowed=false`, and `recommended_refresh_action`

- [ ] **Step 1: Write failing unit tests**

Create `tests/test_research_status_sync.py` with:

```python
from __future__ import annotations

import json
from pathlib import Path

from hsconfig.research_status_sync import build_research_status_sync_report


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _strong_package(tmp_path: Path, deck_name: str = "ShadowPriest") -> Path:
    package = tmp_path / "04_package"
    _write_json(
        package / "reports" / "operator_summary.json",
        {
            "deck": {"name": deck_name},
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "SOURCE_BACKED_STRONG",
            "source_backed_status": "SOURCE_BACKED_STRONG",
            "source_strong_ready": True,
            "first_missing_source_action": "none",
            "source_status_apply_blocking": False,
            "source_status_diagnostic_only": True,
            "default_only_runtime_surfaces": [],
            "no_default_only_runtime_status": "clean",
        },
    )
    return package


def test_seed_only_research_snapshot_cannot_downgrade_strong_package(tmp_path: Path) -> None:
    package = _strong_package(tmp_path)
    research = tmp_path / "research" / "ShadowPriest.json"
    _write_json(
        research,
        {
            "deck_name": "ShadowPriest",
            "source_strength": "unfetched_acquisition_seed",
            "first_missing_source_action": "fetch_and_normalize_candidate_full_text_claims",
        },
    )

    report = build_research_status_sync_report(package, [research])

    assert report["authority"] == "diagnostic_only"
    assert report["normal_apply_authority"] == "reports/operator_summary.json"
    assert report["summary"]["canonical_source_backed_status"] == "SOURCE_BACKED_STRONG"
    assert report["summary"]["stale_or_seed_snapshot_count"] == 1
    assert report["summary"]["canonical_downgrade_allowed"] is False
    assert report["summary"]["source_status_apply_blocking"] is False
    row = report["research_snapshot_rows"][0]
    assert row["snapshot_relation"] == "stale_or_seed_only"
    assert row["research_snapshot_kind"] == "seed_only"
    assert row["canonical_downgrade_allowed"] is False
    assert row["recommended_refresh_action"] == "refresh_research_snapshot_from_canonical_package"


def test_matching_strong_research_snapshot_is_current_with_canonical(tmp_path: Path) -> None:
    package = _strong_package(tmp_path)
    research = tmp_path / "research" / "ShadowPriest.json"
    _write_json(
        research,
        {
            "deck_name": "ShadowPriest",
            "source_backed_status": "SOURCE_BACKED_STRONG",
            "source_strength": "SOURCE_BACKED_STRONG",
            "first_missing_source_action": "none",
        },
    )

    report = build_research_status_sync_report(package, [research])

    assert report["summary"]["stale_or_seed_snapshot_count"] == 0
    assert report["summary"]["status_mismatch_count"] == 0
    assert report["research_snapshot_rows"][0]["snapshot_relation"] == "current_with_canonical"


def test_research_snapshot_cannot_promote_partial_package(tmp_path: Path) -> None:
    package = tmp_path / "04_package"
    _write_json(
        package / "reports" / "operator_summary.json",
        {
            "deck": {"name": "CtAPaladin"},
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "VALID_BUT_NOT_GUIDE_STRONG",
            "source_backed_status": "SOURCE_BACKED_PARTIAL",
            "source_strong_ready": False,
            "first_missing_source_action": "add_current_cta_paladin_mulligan_keep_source",
            "source_status_apply_blocking": False,
            "source_status_diagnostic_only": True,
            "default_only_runtime_surfaces": [],
        },
    )
    research = tmp_path / "research" / "CtAPaladin.json"
    _write_json(
        research,
        {
            "deck_name": "CtAPaladin",
            "source_backed_status": "SOURCE_BACKED_STRONG",
            "source_strength": "SOURCE_BACKED_STRONG",
            "first_missing_source_action": "none",
        },
    )

    report = build_research_status_sync_report(package, [research])

    row = report["research_snapshot_rows"][0]
    assert row["snapshot_relation"] == "conflicts_with_canonical"
    assert row["canonical_promotion_allowed"] is False
    assert report["summary"]["canonical_source_backed_status"] == "SOURCE_BACKED_PARTIAL"
    assert report["summary"]["source_status_apply_blocking"] is False


def test_missing_research_snapshot_is_visible_but_not_apply_blocking(tmp_path: Path) -> None:
    package = _strong_package(tmp_path)

    report = build_research_status_sync_report(package, [])

    assert report["research_snapshot_rows"] == []
    assert report["summary"]["missing_research_snapshot"] is True
    assert report["summary"]["source_status_apply_blocking"] is False
```

- [ ] **Step 2: Run tests and confirm failure**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python -m pytest tests/test_research_status_sync.py -q
```

Expected: fails because `hsconfig.research_status_sync` does not exist.

- [ ] **Step 3: Implement `research_status_sync.py`**

Create `src/hsconfig/research_status_sync.py`:

```python
from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any


NORMAL_APPLY_AUTHORITY = "reports/operator_summary.json"
DIAGNOSTIC_AUTHORITY = "diagnostic_only"
STRONG_STATUS = "SOURCE_BACKED_STRONG"
PARTIAL_STATUS = "SOURCE_BACKED_PARTIAL"
SEED_STRENGTHS = {
    "unfetched_acquisition_seed",
    "decklist_only",
    "snippet_only",
    "stats_only",
    "candidate_url_only",
}


def build_research_status_sync_report(
    package_dir: str | Path,
    research_result_paths: Sequence[str | Path],
) -> dict[str, Any]:
    package_path = Path(package_dir)
    operator_summary = _read_json(package_path / NORMAL_APPLY_AUTHORITY)
    canonical = _canonical_status(operator_summary)
    rows = [
        _research_snapshot_row(canonical, Path(path))
        for path in sorted((Path(path) for path in research_result_paths), key=str)
    ]
    return {
        "schema_version": 1,
        "authority": DIAGNOSTIC_AUTHORITY,
        "operator_gate_impact": DIAGNOSTIC_AUTHORITY,
        "normal_apply_authority": NORMAL_APPLY_AUTHORITY,
        "package": str(package_path),
        "canonical_package_status": canonical,
        "research_snapshot_rows": rows,
        "summary": _summary(canonical, rows),
    }
```

Add helpers:

```python
def _read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def _canonical_status(operator_summary: dict[str, Any]) -> dict[str, Any]:
    deck = operator_summary.get("deck", {})
    deck_name = deck.get("name", "") if isinstance(deck, dict) else ""
    return {
        "deck_name": str(deck_name),
        "technical_status": str(operator_summary.get("technical_status") or ""),
        "semantic_status": str(operator_summary.get("semantic_status") or ""),
        "source_backed_status": str(operator_summary.get("source_backed_status") or ""),
        "source_strong_ready": bool(operator_summary.get("source_strong_ready", False)),
        "first_missing_source_action": str(
            operator_summary.get("first_missing_source_action") or ""
        ),
        "source_status_apply_blocking": bool(
            operator_summary.get("source_status_apply_blocking", False)
        ),
        "source_status_diagnostic_only": bool(
            operator_summary.get("source_status_diagnostic_only", True)
        ),
        "default_only_runtime_surfaces": list(
            operator_summary.get("default_only_runtime_surfaces") or []
        ),
        "no_default_only_runtime_status": str(
            operator_summary.get("no_default_only_runtime_status") or ""
        ),
    }


def _research_snapshot_row(canonical: dict[str, Any], path: Path) -> dict[str, Any]:
    data = _read_json(path)
    research_status = _research_status(data)
    research_strength = str(data.get("source_strength") or research_status or "")
    research_kind = _research_snapshot_kind(research_strength)
    relation = _snapshot_relation(
        canonical_status=str(canonical["source_backed_status"]),
        research_status=research_status,
        research_kind=research_kind,
    )
    return {
        "path": str(path),
        "deck_name": str(data.get("deck_name") or ""),
        "canonical_deck_name": canonical["deck_name"],
        "research_source_backed_status": research_status,
        "research_source_strength": research_strength,
        "research_snapshot_kind": research_kind,
        "research_first_missing_source_action": str(
            data.get("first_missing_source_action") or ""
        ),
        "canonical_source_backed_status": canonical["source_backed_status"],
        "canonical_first_missing_source_action": canonical["first_missing_source_action"],
        "snapshot_relation": relation,
        "canonical_downgrade_allowed": False,
        "canonical_promotion_allowed": False,
        "source_status_apply_blocking": False,
        "recommended_refresh_action": _recommended_refresh_action(relation),
    }
```

Add the remaining helpers:

```python
def _research_status(data: dict[str, Any]) -> str:
    explicit = str(data.get("source_backed_status") or "").strip()
    if explicit:
        return explicit
    strength = str(data.get("source_strength") or "").strip()
    if strength == STRONG_STATUS:
        return STRONG_STATUS
    if strength in SEED_STRENGTHS:
        return PARTIAL_STATUS
    return strength or "unknown"


def _research_snapshot_kind(source_strength: str) -> str:
    normalized = source_strength.strip()
    if normalized in SEED_STRENGTHS:
        return "seed_only"
    if normalized == STRONG_STATUS:
        return "canonical_like"
    if not normalized:
        return "unknown"
    return "status_snapshot"


def _snapshot_relation(
    *,
    canonical_status: str,
    research_status: str,
    research_kind: str,
) -> str:
    if research_kind == "seed_only" and canonical_status == STRONG_STATUS:
        return "stale_or_seed_only"
    if canonical_status == research_status:
        return "current_with_canonical"
    if canonical_status == STRONG_STATUS and research_status != STRONG_STATUS:
        return "stale_or_seed_only"
    if canonical_status != research_status:
        return "conflicts_with_canonical"
    return "current_with_canonical"


def _recommended_refresh_action(relation: str) -> str:
    if relation == "current_with_canonical":
        return "none"
    if relation == "stale_or_seed_only":
        return "refresh_research_snapshot_from_canonical_package"
    if relation == "conflicts_with_canonical":
        return "inspect_package_and_research_snapshot_before_updating_docs"
    return "inspect_research_snapshot"


def _summary(canonical: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    stale_or_seed_count = sum(
        1 for row in rows if row["snapshot_relation"] == "stale_or_seed_only"
    )
    mismatch_count = sum(
        1 for row in rows if row["snapshot_relation"] == "conflicts_with_canonical"
    )
    refresh_actions = sorted(
        {
            str(row["recommended_refresh_action"])
            for row in rows
            if row["recommended_refresh_action"] != "none"
        }
    )
    return {
        "canonical_deck_name": canonical["deck_name"],
        "canonical_source_backed_status": canonical["source_backed_status"],
        "canonical_source_strong_ready": canonical["source_strong_ready"],
        "canonical_first_missing_source_action": canonical["first_missing_source_action"],
        "missing_research_snapshot": not rows,
        "research_snapshot_count": len(rows),
        "stale_or_seed_snapshot_count": stale_or_seed_count,
        "status_mismatch_count": mismatch_count,
        "canonical_downgrade_allowed": False,
        "canonical_promotion_allowed": False,
        "source_status_apply_blocking": False,
        "recommended_refresh_actions": refresh_actions,
    }
```

- [ ] **Step 4: Run unit tests**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python -m pytest tests/test_research_status_sync.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Check pure-module boundary**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
rg -n "requests|http|subprocess|apply_package|runtime_root|write_text|source_status_apply_blocking.*True" src\hsconfig\research_status_sync.py
```

Expected: no output. The module must be read-only and cannot create a gate.

---

### Task 3: Add Read-Only CLI Command

**Files:**
- Modify: `src/hsconfig/commands/source_workflow.py`
- Modify: `src/hsconfig/cli_parser.py`
- Modify: `src/hsconfig/cli.py`
- Create: `tests/test_research_status_sync_cli.py`

**Interfaces:**
- Consumes:
  - `hsconfig research-status-sync --package <package> --research-results-dir <dir> [--out <path>] [--json]`
- Produces:
  - JSON payload from `build_research_status_sync_report`
  - optional report file when `--out` is supplied
  - no runtime writes

- [ ] **Step 1: Write failing CLI tests**

Create `tests/test_research_status_sync_cli.py` with:

```python
from __future__ import annotations

import json
from pathlib import Path

from hsconfig.cli import main


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def test_research_status_sync_cli_writes_optional_report(tmp_path: Path) -> None:
    package = tmp_path / "04_package"
    research_dir = tmp_path / "research" / "results"
    out = tmp_path / "sync_report.json"
    _write_json(
        package / "reports" / "operator_summary.json",
        {
            "deck": {"name": "ShadowPriest"},
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "SOURCE_BACKED_STRONG",
            "source_backed_status": "SOURCE_BACKED_STRONG",
            "source_strong_ready": True,
            "first_missing_source_action": "none",
            "source_status_apply_blocking": False,
            "default_only_runtime_surfaces": [],
        },
    )
    _write_json(
        research_dir / "ShadowPriest.json",
        {
            "deck_name": "ShadowPriest",
            "source_strength": "unfetched_acquisition_seed",
            "first_missing_source_action": "fetch_and_normalize_candidate_full_text_claims",
        },
    )

    code = main(
        [
            "research-status-sync",
            "--package",
            str(package),
            "--research-results-dir",
            str(research_dir),
            "--out",
            str(out),
            "--json",
        ]
    )

    assert code == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["authority"] == "diagnostic_only"
    assert payload["summary"]["stale_or_seed_snapshot_count"] == 1
    assert payload["summary"]["source_status_apply_blocking"] is False
```

- [ ] **Step 2: Run CLI test and confirm failure**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python -m pytest tests/test_research_status_sync_cli.py -q
```

Expected: fails because the command is not registered.

- [ ] **Step 3: Add command payload**

In `src/hsconfig/commands/source_workflow.py`, import:

```python
from hsconfig.research_status_sync import build_research_status_sync_report
```

Add:

```python
def run_research_status_sync_command(args: argparse.Namespace) -> int:
    return run_payload_command(args, research_status_sync_payload)


def research_status_sync_payload(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    research_dir = Path(args.research_results_dir)
    research_paths = sorted(research_dir.glob("*.json")) if research_dir.exists() else []
    report = build_research_status_sync_report(
        package_dir=Path(args.package),
        research_result_paths=research_paths,
    )
    if getattr(args, "out", None):
        write_json(Path(args.out), report)
    return report, 0
```

- [ ] **Step 4: Register parser command**

In `src/hsconfig/cli_parser.py`, add before `validate`:

```python
    research_status_sync = subparsers.add_parser(
        "research-status-sync",
        help="read-only diagnostic comparing research snapshots with canonical package status",
        description=(
            "Read a prepared package and research-deep result JSONs, then report "
            "whether research snapshots are current, stale/seed-only, conflicting, "
            "or missing. This command is diagnostic only and never writes runtime files."
        ),
    )
    research_status_sync.add_argument("--package", required=True)
    research_status_sync.add_argument("--research-results-dir", required=True)
    research_status_sync.add_argument("--out")
    research_status_sync.add_argument("--json", action="store_true")
```

- [ ] **Step 5: Route CLI command**

In `src/hsconfig/cli.py`, import:

```python
    run_research_status_sync_command,
```

from `hsconfig.commands.source_workflow`, then add in `main`:

```python
    if args.command == "research-status-sync":
        return run_research_status_sync_command(args)
```

- [ ] **Step 6: Run CLI tests**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python -m pytest tests/test_research_status_sync_cli.py -q
```

Expected: pass.

---

### Task 4: Lock Active Docs And Skill Wording

**Files:**
- Modify: `docs/research/current-truth.md`
- Modify: `docs/research/current-truth-index.json`
- Modify: `docs/operator/source-backed-strong-closure.md`
- Modify: `.agents/skills/hsconfig/SKILL.md`
- Modify: `tests/test_research_current_truth.py`
- Modify: `tests/test_docs_active_path.py`

**Interfaces:**
- Consumes: new `research-status-sync` command and diagnostic report semantics.
- Produces: active docs that tell agents and operators how to read stale `research-deep` outputs.

- [ ] **Step 1: Add failing docs tests**

Append to `tests/test_research_current_truth.py`:

```python
def test_current_truth_documents_research_snapshot_status_sync():
    text = (ROOT / "docs" / "research" / "current-truth.md").read_text(
        encoding="utf-8"
    )

    assert "research-status-sync" in text
    assert "research snapshots can be stale or seed-only" in text
    assert "research snapshots do not downgrade canonical package status" in text
    assert "operator_summary.json remains the only normal apply authority" in text
```

Append to `tests/test_docs_active_path.py`:

```python
def test_operator_docs_name_research_status_sync_as_diagnostic_only():
    docs = "\n".join(
        [
            Path("docs/operator/source-backed-strong-closure.md").read_text(
                encoding="utf-8"
            ),
            Path(".agents/skills/hsconfig/SKILL.md").read_text(encoding="utf-8"),
        ]
    )

    assert "research-status-sync" in docs
    assert "diagnostic only" in docs
    assert "must not downgrade `SOURCE_BACKED_STRONG`" in docs
    assert "does not create apply authority" in docs
```

- [ ] **Step 2: Run docs tests and confirm failure**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python -m pytest tests/test_research_current_truth.py tests/test_docs_active_path.py -q
```

Expected: fails until docs/skill are updated.

- [ ] **Step 3: Update current truth Markdown**

Add this section to `docs/research/current-truth.md` near “How To Read Historical Evidence”:

```markdown
## Research Snapshot Status Sync

Use `hsconfig research-status-sync --package <04_package> --research-results-dir <results>`
when `research-deep` JSON files appear to disagree with a prepared package.
Research snapshots can be stale or seed-only; they are evidence history, not
operator instructions. They can recommend a refresh action, but research
snapshots do not downgrade canonical package status, do not promote partial
packages, and do not create apply authority. `operator_summary.json remains the
only normal apply authority`.
```

- [ ] **Step 4: Update current truth JSON**

Add this object to `docs/research/current-truth-index.json`:

```json
"research_snapshot_sync_policy": {
  "command": "hsconfig research-status-sync",
  "authority": "diagnostic_only",
  "normal_apply_authority": "reports/operator_summary.json",
  "research_snapshots_can_be": ["current_with_canonical", "stale_or_seed_only", "conflicts_with_canonical", "missing"],
  "canonical_downgrade_allowed": false,
  "canonical_promotion_allowed": false,
  "source_status_apply_blocking": false
}
```

Place it as a top-level property after `normal_apply_authority`.

- [ ] **Step 5: Update operator closure docs**

Add this paragraph to `docs/operator/source-backed-strong-closure.md`:

```markdown
`hsconfig research-status-sync` is a read-only diagnostic for historical
`research-deep` JSON files. It compares research snapshots with the canonical
prepared package status in `reports/operator_summary.json`. A stale or seed-only
research snapshot must not downgrade `SOURCE_BACKED_STRONG`, must not promote a
partial package, and does not create apply authority.
```

- [ ] **Step 6: Update repo-local HSConfig skill**

Add this compact rule to `.agents/skills/hsconfig/SKILL.md`:

```markdown
- When `research-deep` result JSONs disagree with a prepared package, use
  `hsconfig research-status-sync` as diagnostic only. Historical research
  snapshots can be stale or seed-only; they must not downgrade
  `SOURCE_BACKED_STRONG`, must not promote partial packages, and do not create
  apply authority. `operator_summary.json` remains the only normal apply
  authority.
```

- [ ] **Step 7: Run docs tests**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python -m pytest tests/test_research_current_truth.py tests/test_docs_active_path.py -q
```

Expected: pass.

---

### Task 5: Sync Installed Skill And Run Focused Verification

**Files:**
- Verify: `C:\Users\darbo\.codex\skills\hsconfig\SKILL.md`
- Verify all files modified by Tasks 2-4.

**Interfaces:**
- Consumes: implementation and docs changes.
- Produces: checked local branch with repo-local and installed skill aligned.

- [ ] **Step 1: Sync installed HSConfig skill**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python scripts/sync_installed_skill.py
python scripts/sync_installed_skill.py --check
```

Expected: both commands exit `0`; the installed skill is in sync.

- [ ] **Step 2: Run focused tests**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python -m pytest tests/test_research_status_sync.py tests/test_research_status_sync_cli.py tests/test_research_current_truth.py tests/test_docs_active_path.py tests/test_source_status_resolver.py tests/test_operator_summary.py tests/test_universal_wild_no_block_matrix.py -q
```

Expected: all tests pass. This proves the new sync layer is diagnostic-only and does not regress resolver, operator summary, or universal Wild no-block behavior.

- [ ] **Step 3: Run broader source-contract smoke suite**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python -m pytest tests/test_source_status_resolver.py tests/test_strong_promotion_report.py tests/test_source_evidence_closure.py tests/test_no_second_gate_contract.py tests/test_apply_authority_boundary.py tests/test_contract_spine_sentinel.py -q
```

Expected: all tests pass. This proves the new diagnostic command did not become a second gate.

- [ ] **Step 4: Verify static forbidden terms**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
rg -n "hsreplay|winrate|replay|source_status_apply_blocking.*True|research.*authorizes|research.*apply authority" src tests docs .agents
```

Expected: no runtime-facing source code introduces post-run or winrate logic. Existing docs may mention forbidden concepts only as negative boundary text; if the command flags active wording that sounds authoritative, revise the wording.

- [ ] **Step 5: Verify diff hygiene**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
git diff --check
git status --short --branch
```

Expected: `git diff --check` exits `0`; `git status` shows only intended source, tests, docs, skill, and plan changes before commit.

- [ ] **Step 6: Commit local implementation when clean**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
git add src/hsconfig/research_status_sync.py `
  src/hsconfig/commands/source_workflow.py `
  src/hsconfig/cli_parser.py `
  src/hsconfig/cli.py `
  tests/test_research_status_sync.py `
  tests/test_research_status_sync_cli.py `
  tests/test_research_current_truth.py `
  tests/test_docs_active_path.py `
  docs/research/current-truth.md `
  docs/research/current-truth-index.json `
  docs/operator/source-backed-strong-closure.md `
  .agents/skills/hsconfig/SKILL.md `
  docs/superpowers/plans/2026-07-18-hsconfig-research-snapshot-status-sync.md
git commit -m "Add research snapshot status sync diagnostic"
```

Expected: commit succeeds locally. Do not push unless the user explicitly asks.

---

## Acceptance Criteria

- [ ] `hsconfig research-status-sync` exists and is read-only.
- [ ] The sync report labels stale/seed-only `research-deep` rows without downgrading a canonical `SOURCE_BACKED_STRONG` package.
- [ ] The sync report refuses research-driven promotion of a canonical partial package.
- [ ] The sync report exposes `canonical_downgrade_allowed=false`, `canonical_promotion_allowed=false`, and `source_status_apply_blocking=false`.
- [ ] `operator_summary.json` remains the only normal apply authority.
- [ ] `source_status_resolver` remains the only source-status resolver; the new module only compares canonical status with research snapshots.
- [ ] ShadowPriest remains protected by existing Darkbishop tests: `SW_448` effect semantics preserved, no automatic Mulligan keep.
- [ ] HSGuru/HSReplay/decklist/candidate/research-seed sources remain non-promoting support/acquisition evidence.
- [ ] Docs and repo-local/installed skill explain how to handle research snapshot drift.
- [ ] Focused tests pass.
- [ ] Worktree is clean after local commit.

## Subagent-Driven Execution Strategy

- **Explorer subagent, read-only:** confirm the existing resolver and report call graph; verify no duplicate source-status resolver should be added.
- **Implementation worker:** write `research_status_sync.py`, CLI wiring, and focused tests.
- **Docs worker:** update current-truth, operator docs, and skill wording only after the CLI/report contract is stable.
- **Reviewer subagent, read-only:** inspect the diff for second-gate risk, stale wording, forbidden post-run terms, and ShadowPriest/Darkbishop regression risk.
- **Main agent:** run verification, resolve reviewer findings, sync installed skill, commit locally, and keep the worktree clean.

## Self-Review

- Spec coverage: The plan covers canonical package authority, stale research snapshots, no default-only promotion, no source apply blocking, docs/skill synchronization, and clean-worktree handoff.
- Placeholder scan: The plan contains no deferred-work markers or vague test instructions.
- Type consistency: `build_research_status_sync_report(package_dir, research_result_paths)` is defined once and consumed by CLI/tests with the same names and return shape.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-18-hsconfig-research-snapshot-status-sync.md`. Two execution options:

**1. Subagent-Driven (recommended)** - Dispatch a fresh subagent per task, review between tasks, and keep implementation narrow.

**2. Inline Execution** - Execute tasks in this session with checkpointed review.

Recommended next command: `Setze den Plan SubAgent Driven um`.

# HSConfig Contract Preflight And Skill Router Slimming Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a small read-only HSConfig contract preflight and tighten the skill router so agents can verify source/status/default-only/runtime-boundary invariants before config work without changing HearthRanger runtime behavior.

**Architecture:** Add one pure diagnostic module, one CLI command wrapper, and a tiny skill-reference patch. The command reads repo docs and skill files, checks existing contract invariants, and reports `PASS` or `ATTENTION`; it is never invoked by `configure`, `prepare`, `apply`, or runtime writers, so it cannot become a second apply gate.

**Tech Stack:** Python stdlib only (`argparse`, `dataclasses`, `json`, `pathlib`, `subprocess`), existing `hsconfig` CLI command pattern, `pytest`, existing skill sync/currentness scripts.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig`.
- Before implementation and before final verification, run `git fetch --all --prune --tags`, `python scripts/check_hsconfig_currentness.py --cwd . --json`, and `git status --short --branch`.
- Keep the worktree clean at the end: commit the implementation and sync the installed skill if `.agents/skills/hsconfig` changes.
- Do not add dependencies.
- Do not parse replays, inspect winrate, analyze runtime logs, promote after-game candidates, or use HSTuner.
- Do not add gameplay sequencing logic; HearthRanger remains responsible for playing correctly.
- Do not add `Presume.json`, `Concede.json`, or aggregate `CardBehavior.json` to the normal HSConfig output path.
- `reports/operator_summary.json` remains the only normal runtime apply authority.
- `SOURCE_BACKED_STRONG` remains an evidence-quality label, not a generation or apply gate.
- Weak source coverage must stay visible and non-blocking for technically valid packages.
- No silent default-only success: every expected runtime surface must be emitted, explicitly suppressed, or reported as a visible source/action gap.

---

## File Structure

- Create `src/hsconfig/contract_preflight.py`
  - Owns the read-only diagnostic model and file-content checks.
  - Exposes `GitPreflight`, `build_git_preflight()`, and `build_contract_preflight()`.
  - Does not import from `scripts/` and does not write files.
- Create `src/hsconfig/commands/contract_preflight.py`
  - Thin CLI command handler that calls `build_contract_preflight()`.
  - Uses existing `emit_result()` behavior.
- Modify `src/hsconfig/cli_parser.py`
  - Adds `hsconfig contract-preflight --repo-root . --json`.
- Modify `src/hsconfig/cli.py`
  - Dispatches the new command.
- Modify `.agents/skills/hsconfig/SKILL.md`
  - Add `references/contract-compiler-checklist.md` to the final `## References:` line.
  - Keep the skill under the existing compactness limit.
- Modify `tests/test_skill_files.py`
  - Assert the final `## References:` line includes `references/contract-compiler-checklist.md`.
- Modify `tests/test_skill_sync.py`
  - Assert synced installed skills preserve the checklist reference.
- Create `tests/test_contract_preflight.py`
  - Unit-test the preflight payload, non-blocking source-status contract, no-default-only visibility, and CLI JSON behavior.
- Modify `docs/operator/README.md`
  - Add a short optional diagnostic note for `hsconfig contract-preflight --json`.
  - State explicitly that it is diagnostic-only and does not replace `operator_summary.json`.

---

### Task 1: Add Pure Contract Preflight Diagnostic

**Files:**
- Create: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\contract_preflight.py`
- Test: `C:\Users\darbo\Documents\HSConfig\tests\test_contract_preflight.py`

**Interfaces:**
- Consumes: repo root path containing `.agents/skills/hsconfig/SKILL.md`, `.agents/skills/hsconfig/references/contract-compiler-checklist.md`, and `docs/operator/README.md`.
- Produces:
  - `GitPreflight` dataclass.
  - `build_git_preflight(repo_root: str | Path) -> GitPreflight`.
  - `build_contract_preflight(repo_root: str | Path = ".", git: GitPreflight | None = None) -> dict[str, object]`.
  - Payload shape used by CLI and tests:
    - `status: "PASS" | "ATTENTION"`
    - `repo_root: str`
    - `git: dict[str, object]`
    - `checks: dict[str, bool]`
    - `failures: list[str]`
    - `runtime_apply_authority: "reports/operator_summary.json"`
    - `source_status_apply_blocking: false`
    - `diagnostic_only: true`

- [ ] **Step 1: Write failing tests for the preflight module**

Append this new file:

```python
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from hsconfig.contract_preflight import GitPreflight, build_contract_preflight


def _clean_git() -> GitPreflight:
    return GitPreflight(
        branch="codex/test",
        upstream="origin/codex/test",
        dirty=False,
        ahead_origin_main=1,
        behind_origin_main=0,
        clean_for_runtime_work=True,
        ahead_upstream=0,
        behind_upstream=0,
    )


def test_contract_preflight_passes_for_repo_contract_with_clean_git_snapshot() -> None:
    payload = build_contract_preflight(Path("."), git=_clean_git())

    assert payload["status"] == "PASS"
    assert payload["runtime_apply_authority"] == "reports/operator_summary.json"
    assert payload["source_status_apply_blocking"] is False
    assert payload["diagnostic_only"] is True
    assert payload["failures"] == []
    assert payload["checks"]["repo_current"] is True
    assert payload["checks"]["checklist_listed_in_references"] is True
    assert payload["checks"]["no_default_only_visible"] is True
    assert payload["checks"]["source_status_nonblocking_visible"] is True
    assert payload["checks"]["runtime_surface_boundary_visible"] is True
    assert payload["checks"]["negative_scope_visible"] is True


def test_contract_preflight_reports_attention_when_git_is_dirty() -> None:
    dirty_git = GitPreflight(
        branch="codex/test",
        upstream="origin/codex/test",
        dirty=True,
        ahead_origin_main=1,
        behind_origin_main=0,
        clean_for_runtime_work=False,
        ahead_upstream=0,
        behind_upstream=0,
    )

    payload = build_contract_preflight(Path("."), git=dirty_git)

    assert payload["status"] == "ATTENTION"
    assert "repo_current" in payload["failures"]
    assert payload["source_status_apply_blocking"] is False
    assert payload["runtime_apply_authority"] == "reports/operator_summary.json"


def test_contract_preflight_cli_emits_json_without_writing_files(tmp_path: Path) -> None:
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    before = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        text=True,
        capture_output=True,
        check=True,
    ).stdout
    result = subprocess.run(
        [sys.executable, "-m", "hsconfig.cli", "contract-preflight", "--repo-root", ".", "--json"],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )
    after = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        text=True,
        capture_output=True,
        check=True,
    ).stdout

    assert result.returncode in (0, 1)
    payload = json.loads(result.stdout)
    assert payload["diagnostic_only"] is True
    assert payload["runtime_apply_authority"] == "reports/operator_summary.json"
    assert before == after
```

- [ ] **Step 2: Run tests and confirm the expected failure**

Run:

```powershell
python -m pytest tests/test_contract_preflight.py -q
```

Expected: FAIL because `hsconfig.contract_preflight` does not exist.

- [ ] **Step 3: Implement the minimal preflight module**

Create `src/hsconfig/contract_preflight.py`:

```python
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import subprocess


REQUIRED_REFERENCE_FILES = (
    "references/workflow.md",
    "references/visionai-surfaces.md",
    "references/guide-research-policy.md",
    "references/globalvalues-policy.md",
    "references/card-behavior-policy.md",
    "references/contract-compiler-checklist.md",
)


@dataclass(frozen=True)
class GitPreflight:
    branch: str
    upstream: str | None
    dirty: bool
    ahead_origin_main: int
    behind_origin_main: int
    clean_for_runtime_work: bool
    ahead_upstream: int | None = None
    behind_upstream: int | None = None


def _run_git(repo_root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=check,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _parse_counts(text: str) -> tuple[int, int]:
    parts = text.replace("\t", " ").split()
    if len(parts) < 2:
        return 0, 0
    return int(parts[0]), int(parts[1])


def _parse_status(text: str) -> tuple[str, bool]:
    lines = [line for line in text.splitlines() if line.strip()]
    branch_line = lines[0] if lines else "## unknown"
    branch = branch_line.removeprefix("## ").split("...")[0].strip()
    dirty = any(not line.startswith("## ") for line in lines)
    return branch, dirty


def build_git_preflight(repo_root: str | Path) -> GitPreflight:
    root = Path(repo_root)
    status = _run_git(root, "status", "--short", "--branch").stdout
    branch, dirty = _parse_status(status)
    upstream_result = _run_git(
        root,
        "rev-parse",
        "--abbrev-ref",
        "--symbolic-full-name",
        "@{u}",
        check=False,
    )
    upstream = upstream_result.stdout.strip() or None
    ahead_origin_main, behind_origin_main = _parse_counts(
        _run_git(root, "rev-list", "--left-right", "--count", "HEAD...origin/main").stdout
    )
    ahead_upstream: int | None = None
    behind_upstream: int | None = None
    if upstream:
        ahead_upstream, behind_upstream = _parse_counts(
            _run_git(root, "rev-list", "--left-right", "--count", f"HEAD...{upstream}").stdout
        )
    return GitPreflight(
        branch=branch,
        upstream=upstream,
        dirty=dirty,
        ahead_origin_main=ahead_origin_main,
        behind_origin_main=behind_origin_main,
        clean_for_runtime_work=(not dirty and behind_origin_main == 0),
        ahead_upstream=ahead_upstream,
        behind_upstream=behind_upstream,
    )


def _read(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _references_line(skill_text: str) -> str:
    for line in skill_text.splitlines():
        if line.startswith("## References:"):
            return line
    return ""


def build_contract_preflight(
    repo_root: str | Path = ".",
    *,
    git: GitPreflight | None = None,
) -> dict[str, object]:
    root = Path(repo_root).resolve()
    skill_root = root / ".agents" / "skills" / "hsconfig"
    skill_text = _read(skill_root / "SKILL.md")
    workflow_text = _read(skill_root / "references" / "workflow.md")
    checklist_text = _read(skill_root / "references" / "contract-compiler-checklist.md")
    operator_text = _read(root / "docs" / "operator" / "README.md")
    combined = "\n".join([skill_text, workflow_text, checklist_text, operator_text])
    references_line = _references_line(skill_text)
    git_snapshot = git or build_git_preflight(root)

    checks = {
        "repo_current": git_snapshot.clean_for_runtime_work and git_snapshot.behind_origin_main == 0,
        "skill_root_present": skill_root.exists(),
        "reference_files_present": all((skill_root / rel).exists() for rel in REQUIRED_REFERENCE_FILES),
        "checklist_referenced_by_normal_workflow": (
            "Contract compiler checklist: `references/contract-compiler-checklist.md`." in skill_text
            and "Contract compiler checklist: `references/contract-compiler-checklist.md`." in workflow_text
        ),
        "checklist_listed_in_references": "references/contract-compiler-checklist.md" in references_line,
        "operator_summary_single_authority_visible": (
            "operator_summary.json remains the only normal apply authority" in combined
            or "operator_summary.json` remains the only normal apply authority" in combined
        ),
        "source_status_nonblocking_visible": (
            "source_status_apply_blocking" in combined
            and "must remain `false`" in combined
            and "SOURCE_BACKED_STRONG is an evidence-quality label" in combined
        ),
        "no_default_only_visible": (
            "No hidden default-only runtime" in combined
            and "default_only_runtime_surfaces=[]" in combined
        ),
        "runtime_surface_boundary_visible": all(
            term in combined
            for term in (
                "`GlobalValues.json`",
                "`Mulligan.json`",
                "`per-card <CARDID>.json`",
                "`Combo.json`",
                "`Presume.json`",
                "`Concede.json`",
                "outside the normal HSConfig output path",
            )
        ),
        "darkbishop_effect_not_mulligan_visible": (
            "Darkbishop" in combined
            and "hero-power-transform" in combined
            and "do not emit a Mulligan keep without explicit opening-hand source text" in combined
        ),
        "negative_scope_visible": all(
            term in combined
            for term in (
                "does not parse replays",
                "inspect winrate",
                "analyze runtime logs",
                "tune after games",
            )
        ),
        "diagnostic_only_visible": (
            "diagnostic-only" in combined
            and "not another operator gate" in checklist_text
            and "not another runtime apply gate" in combined
        ),
    }
    failures = [name for name, ok in checks.items() if not ok]
    return {
        "status": "PASS" if not failures else "ATTENTION",
        "repo_root": str(root),
        "git": asdict(git_snapshot),
        "checks": checks,
        "failures": failures,
        "runtime_apply_authority": "reports/operator_summary.json",
        "source_status_apply_blocking": False,
        "diagnostic_only": True,
    }
```

- [ ] **Step 4: Run the module tests again**

Run:

```powershell
python -m pytest tests/test_contract_preflight.py -q
```

Expected: the dirty-git test passes; the repo-contract test may still fail on `checklist_listed_in_references` until Task 3 updates `SKILL.md`.

---

### Task 2: Add CLI Command Without Runtime Integration

**Files:**
- Create: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\commands\contract_preflight.py`
- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\cli_parser.py`
- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\cli.py`
- Test: `C:\Users\darbo\Documents\HSConfig\tests\test_contract_preflight.py`

**Interfaces:**
- Consumes: `build_contract_preflight(repo_root)`.
- Produces: CLI command `hsconfig contract-preflight --repo-root . --json`.
- Explicit non-interface: `configure`, `prepare`, `validate`, and `apply` must not call this command.

- [ ] **Step 1: Write the CLI test**

Add this test to `tests/test_contract_preflight.py`:

```python
def test_contract_preflight_is_registered_but_not_part_of_configure_path() -> None:
    parser_help = subprocess.run(
        [sys.executable, "-m", "hsconfig.cli", "--help"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert parser_help.returncode == 0
    assert "contract-preflight" in parser_help.stdout

    configure_help = subprocess.run(
        [sys.executable, "-m", "hsconfig.cli", "configure", "--help"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert configure_help.returncode == 0
    assert "contract-preflight" not in configure_help.stdout
```

- [ ] **Step 2: Run the CLI test and confirm the expected failure**

Run:

```powershell
python -m pytest tests/test_contract_preflight.py::test_contract_preflight_is_registered_but_not_part_of_configure_path -q
```

Expected: FAIL because `contract-preflight` is not registered yet.

- [ ] **Step 3: Add the command handler**

Create `src/hsconfig/commands/contract_preflight.py`:

```python
from __future__ import annotations

from hsconfig.commands.common import emit_result
from hsconfig.contract_preflight import build_contract_preflight


def run_contract_preflight_command(args) -> int:
    payload = build_contract_preflight(getattr(args, "repo_root", "."))
    return emit_result(payload, bool(getattr(args, "json", False)), 0 if payload["status"] == "PASS" else 1)
```

- [ ] **Step 4: Register the parser command**

In `src/hsconfig/cli_parser.py`, add this parser block after `contract-spine-sentinel`:

```python
    contract_preflight = subparsers.add_parser(
        "contract-preflight",
        help="read-only repo and skill contract preflight",
        description=(
            "Read-only repo and skill contract preflight. Checks currentness, "
            "skill/reference routing, source-status non-blocking policy, no-default-only "
            "visibility, runtime surface boundary, and negative scope wording. "
            "This command does not grant apply permission and never writes runtime files."
        ),
    )
    contract_preflight.add_argument("--repo-root", default=".")
    contract_preflight.add_argument("--json", action="store_true")
```

- [ ] **Step 5: Wire the dispatcher**

In `src/hsconfig/cli.py`, add the import:

```python
from hsconfig.commands.contract_preflight import run_contract_preflight_command
```

Then add the dispatch branch after `contract-spine-sentinel`:

```python
    if args.command == "contract-preflight":
        return run_contract_preflight_command(args)
```

- [ ] **Step 6: Run the CLI tests**

Run:

```powershell
python -m pytest tests/test_contract_preflight.py -q
```

Expected: all tests pass except any still depending on the skill reference list fixed in Task 3.

---

### Task 3: Slim The Skill Router Reference Surface

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\.agents\skills\hsconfig\SKILL.md`
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_skill_files.py`
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_skill_sync.py`
- Modify: `C:\Users\darbo\Documents\HSConfig\docs\operator\README.md`

**Interfaces:**
- Consumes: existing `contract-compiler-checklist.md`.
- Produces: a repo skill whose final `## References:` line includes the checklist and whose installed copy sync check preserves it.

- [ ] **Step 1: Write the failing reference-list test**

In `tests/test_skill_files.py`, inside `test_skill_and_workflow_stay_compact_and_canonical()`, add:

```python
    reference_line = next(
        line for line in skill.splitlines() if line.startswith("## References:")
    )
    assert "references/contract-compiler-checklist.md" in reference_line
```

Run:

```powershell
python -m pytest tests/test_skill_files.py::test_skill_and_workflow_stay_compact_and_canonical -q
```

Expected: FAIL until `SKILL.md` final reference line is updated.

- [ ] **Step 2: Patch only the final reference line**

Replace the final reference line in `.agents/skills/hsconfig/SKILL.md` with:

```markdown
## References: `references/workflow.md`; `references/visionai-surfaces.md`; `references/contract-compiler-checklist.md`; `references/guide-research-policy.md`; `references/globalvalues-policy.md`; `references/card-behavior-policy.md`
```

Do not add more prose to `SKILL.md`. This keeps the entrypoint compact and moves detailed contract reasoning to the reference checklist.

- [ ] **Step 3: Add skill-sync preservation coverage**

In `tests/test_skill_sync.py`, inside `test_skill_sync_propagates_source_backed_closure_guidance()`, add:

```python
    reference_line = next(
        line for line in skill_text.splitlines() if line.startswith("## References:")
    )
    assert "references/contract-compiler-checklist.md" in reference_line
```

- [ ] **Step 4: Document the optional diagnostic in operator docs**

In `docs/operator/README.md`, add a short subsection near the currentness/checklist or diagnostic-tool area:

```markdown
### Optional Contract Preflight

Use `hsconfig contract-preflight --json` for a read-only repo and skill contract check before source refresh, package generation, or runtime-facing apply review. It checks currentness, skill reference routing, source-status non-blocking policy, no-default-only visibility, supported runtime surfaces, and negative-scope boundaries. It is diagnostic-only and does not replace `reports/operator_summary.json`.
```

- [ ] **Step 5: Run focused docs/skill tests**

Run:

```powershell
python -m pytest tests/test_skill_files.py tests/test_skill_sync.py -q
```

Expected: PASS.

---

### Task 4: Final Verification, Skill Sync, And Clean Handoff

**Files:**
- Modify external installed skill only through `scripts/sync_installed_skill.py` if `.agents/skills/hsconfig` changed.
- No additional source files beyond Tasks 1-3.

**Interfaces:**
- Consumes: all tasks.
- Produces: clean git state, synced installed skill, verified command outputs.

- [ ] **Step 1: Run focused contract tests**

Run:

```powershell
python -m pytest tests/test_contract_preflight.py tests/test_skill_files.py tests/test_skill_sync.py tests/test_currentness_check_script.py -q
```

Expected: PASS.

- [ ] **Step 2: Run guardrail smoke tests**

Run:

```powershell
python scripts/check_contract_guardrails.py
python -m hsconfig.cli contract-spine-sentinel --json
python -m hsconfig.cli contract-preflight --repo-root . --json
```

Expected:
- `check_contract_guardrails.py` exits 0.
- `contract-spine-sentinel` exits 0 and reports no contract drift.
- `contract-preflight` may exit 1 while implementation files are still uncommitted, but the only expected failure is `repo_current`; it must still report `"diagnostic_only": true`, `"source_status_apply_blocking": false`, and `"runtime_apply_authority": "reports/operator_summary.json"`.

- [ ] **Step 3: Sync installed skill**

Run:

```powershell
python scripts/sync_installed_skill.py
python scripts/sync_installed_skill.py --check
```

Expected:
- First command reports the installed skill was synced.
- Second command reports `HSConfig skill is in sync`.

- [ ] **Step 4: Verify currentness and cleanliness**

Run:

```powershell
git fetch --all --prune --tags
python scripts/check_hsconfig_currentness.py --cwd . --json
git status --short --branch
```

Expected:
- `behind_origin_main` is `0`.
- `dirty` is `false`.
- `clean_for_runtime_work` is `true`.
- `git status --short --branch` has no modified/untracked file rows.

- [ ] **Step 5: Commit the implementation**

Run:

```powershell
git add src/hsconfig/contract_preflight.py src/hsconfig/commands/contract_preflight.py src/hsconfig/cli_parser.py src/hsconfig/cli.py tests/test_contract_preflight.py tests/test_skill_files.py tests/test_skill_sync.py docs/operator/README.md .agents/skills/hsconfig/SKILL.md
git commit -m "feat: add hsconfig contract preflight"
git status --short --branch
```

Expected:
- Commit succeeds.
- Worktree is clean after commit.

- [ ] **Step 6: Run final post-commit preflight**

Run:

```powershell
python -m hsconfig.cli contract-preflight --repo-root . --json
python scripts/check_hsconfig_currentness.py --cwd . --json
git status --short --branch
```

Expected:
- `contract-preflight` exits 0 with `"status": "PASS"`.
- `check_hsconfig_currentness.py` reports `"behind_origin_main": 0`, `"dirty": false`, and `"clean_for_runtime_work": true`.
- Worktree remains clean.

---

## Self-Review

Spec coverage:
- General technical improvement without logs: covered by a read-only preflight and no gameplay logic.
- Perfect HearthRanger assumption: covered by explicit non-goal against gameplay sequencing and simulator logic.
- Source/contract correctness: covered by source-status, claim/surface, operator authority, and strong-label checks.
- No default-only: covered by explicit preflight check and skill/doc tests.
- Slim/robust/autonomous: one small module, one CLI command, no dependencies, no runtime writes.
- Always current and clean: covered by currentness checks, skill sync, commit, and final status verification.

Placeholder scan:
- No unresolved placeholder markers.
- Every changed code path has a concrete file, function, test, and command.

Type consistency:
- `GitPreflight` and `build_contract_preflight()` are defined in Task 1 and consumed by Task 2.
- CLI command name is consistently `contract-preflight`.
- Runtime authority remains `reports/operator_summary.json` throughout.

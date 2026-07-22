# HSConfig Installed Skill Contract Drift Sentinel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a small read-only installed-skill drift sentinel to `hsconfig contract-preflight --json` so the active Codex HSConfig skill, repo skill, and source/runtime contract stay visibly synchronized before config work.

**Architecture:** Extract the existing installed-skill folder comparison into a tiny reusable package module, keep `scripts/sync_installed_skill.py` as the only write-capable sync path, and project the same sync status through `contract-preflight`. The new preflight field is diagnostic-only, may return `ATTENTION` on drift, and never changes `configure`, `prepare`, `apply`, HearthRanger runtime files, or `reports/operator_summary.json` authority.

**Tech Stack:** Python stdlib only (`dataclasses`, `json`, `pathlib`, `shutil`, `subprocess`, `sys`), existing `hsconfig` CLI parser/command pattern, `pytest`, existing `scripts/sync_installed_skill.py`.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig`.
- Before implementation and before final verification, run `git fetch --all --prune --tags`, `python scripts\check_hsconfig_currentness.py --cwd . --json`, and `git status --short --branch`.
- Keep the worktree clean at the end; stage/commit the implementation and re-run `git status --short --branch`.
- Do not add dependencies.
- Do not parse replays, inspect winrate, analyze runtime logs, promote after-game candidates, or use HSTuner.
- Do not add gameplay sequencing logic; HearthRanger remains responsible for playing correctly.
- Do not add `Presume.json`, `Concede.json`, or aggregate `CardBehavior.json` to the normal HSConfig output path.
- `reports/operator_summary.json` remains the only normal runtime apply authority.
- `SOURCE_BACKED_STRONG` remains an evidence-quality label, not a generation or apply gate.
- Weak source coverage must stay visible and non-blocking for technically valid packages.
- No silent default-only success: every expected runtime surface must be emitted, explicitly suppressed, or reported as a visible source/action gap.
- Installed skill drift is a developer/operator attention signal only; it must not become a runtime apply gate.

---

## File Structure

- Create `C:\Users\darbo\Documents\HSConfig\src\hsconfig\skill_sync_status.py`
  - Owns reusable folder-diff and installed-skill sync-status logic.
  - Produces JSON-safe diagnostic payloads.
  - Does not write files.
- Modify `C:\Users\darbo\Documents\HSConfig\scripts\sync_installed_skill.py`
  - Reuse `hsconfig.skill_sync_status.folder_diff()` instead of maintaining a second diff implementation.
  - Keep `sync_skill()` as the only write path.
- Modify `C:\Users\darbo\Documents\HSConfig\src\hsconfig\contract_preflight.py`
  - Add `installed_skill_sync_current` to the check list.
  - Add `installed_skill_sync` to the payload.
  - Accept an optional `skill_install_root` for deterministic tests and CLI override.
- Modify `C:\Users\darbo\Documents\HSConfig\src\hsconfig\commands\contract_preflight.py`
  - Pass the optional CLI `--skill-install-root` through to `build_contract_preflight()`.
  - Include a safe installed-skill fallback in exception payloads.
- Modify `C:\Users\darbo\Documents\HSConfig\src\hsconfig\cli_parser.py`
  - Add `--skill-install-root`.
  - Update help text so installed-skill sync is part of the preflight wording.
- Modify `C:\Users\darbo\Documents\HSConfig\tests\test_skill_sync.py`
  - Assert the shared status helper agrees with the sync script.
- Modify `C:\Users\darbo\Documents\HSConfig\tests\test_contract_preflight.py`
  - Make PASS tests use a temporary synced install root.
  - Add a drift test proving `contract-preflight` returns `ATTENTION` when installed skill bytes differ.
  - Add a CLI test proving `--skill-install-root` works without writes.
- Modify `C:\Users\darbo\Documents\HSConfig\tests\test_skill_files.py`
  - Update/read existing docs assertions only if the operator docs wording changes.
- Modify `C:\Users\darbo\Documents\HSConfig\docs\operator\README.md`
  - Document that `contract-preflight` includes installed-skill sync and remains diagnostic-only.
- Modify `C:\Users\darbo\Documents\HSConfig\.agents\skills\hsconfig\SKILL.md`
  - Add one compact sentence in the expert/developer path only if needed to route operators to `contract-preflight --skill-install-root`.

---

### Task 1: Extract Reusable Installed Skill Sync Status

**Files:**
- Create: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\skill_sync_status.py`
- Modify: `C:\Users\darbo\Documents\HSConfig\scripts\sync_installed_skill.py`
- Test: `C:\Users\darbo\Documents\HSConfig\tests\test_skill_sync.py`

**Interfaces:**
- Consumes: source skill folder `repo_root / ".agents" / "skills" / "hsconfig"` and install root `Path.home() / ".codex" / "skills"` or a test override.
- Produces:
  - `DEFAULT_INSTALL_ROOT: Path`
  - `folder_diff(left: Path, right: Path) -> dict[str, object]`
  - `build_installed_skill_sync_status(repo_root: str | Path, install_root: str | Path | None = None) -> dict[str, object]`
  - Payload keys: `status`, `source_skill_path`, `installed_skill_path`, `installed_skill_present`, `matches_repo_skill`, `reason`, `diffs`, `recommended_action`, `diagnostic_only`, `runtime_apply_authority`.

- [ ] **Step 1: Write the failing shared-status test**

Append to `tests/test_skill_sync.py`:

```python
from hsconfig.skill_sync_status import build_installed_skill_sync_status


def test_shared_skill_sync_status_reports_in_sync_after_script_sync(tmp_path: Path):
    install_root = tmp_path / "codex" / "skills"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--install-root",
            str(install_root),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    status = build_installed_skill_sync_status(Path("."), install_root)

    assert status["status"] == "in_sync"
    assert status["installed_skill_present"] is True
    assert status["matches_repo_skill"] is True
    assert status["reason"] == "in_sync"
    assert status["diffs"] == []
    assert status["recommended_action"] == "none"
    assert status["diagnostic_only"] is True
    assert status["runtime_apply_authority"] == "reports/operator_summary.json"


def test_shared_skill_sync_status_reports_attention_on_drift(tmp_path: Path):
    install_root = tmp_path / "codex" / "skills"
    subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--install-root",
            str(install_root),
        ],
        text=True,
        capture_output=True,
        check=True,
    )
    installed_skill = install_root / "hsconfig" / "SKILL.md"
    installed_skill.write_text(
        installed_skill.read_text(encoding="utf-8") + "\n# drift\n",
        encoding="utf-8",
    )

    status = build_installed_skill_sync_status(Path("."), install_root)

    assert status["status"] == "attention"
    assert status["installed_skill_present"] is True
    assert status["matches_repo_skill"] is False
    assert status["reason"] == "diffs_found"
    assert status["recommended_action"] == "python scripts\\sync_installed_skill.py"
    assert status["diagnostic_only"] is True
    assert any(item["path"] == "SKILL.md" for item in status["diffs"])
```

- [ ] **Step 2: Run the failing test**

Run:

```powershell
python -m pytest tests/test_skill_sync.py::test_shared_skill_sync_status_reports_in_sync_after_script_sync tests/test_skill_sync.py::test_shared_skill_sync_status_reports_attention_on_drift -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'hsconfig.skill_sync_status'`.

- [ ] **Step 3: Create the reusable status module**

Create `src/hsconfig/skill_sync_status.py`:

```python
from __future__ import annotations

from pathlib import Path


DEFAULT_INSTALL_ROOT = Path.home() / ".codex" / "skills"
TEXT_LIKE_SUFFIXES = {".md", ".txt", ".json", ".yaml", ".yml", ".toml"}


def _iter_files(root: Path) -> list[Path]:
    return sorted(path.relative_to(root) for path in root.rglob("*") if path.is_file())


def _normalized_text_equal(left_bytes: bytes, right_bytes: bytes) -> bool:
    return left_bytes.replace(b"\r\n", b"\n") == right_bytes.replace(b"\r\n", b"\n")


def folder_diff(left: Path, right: Path) -> dict[str, object]:
    if not left.exists() or not right.exists():
        return {
            "matches": False,
            "reason": "missing_folder",
            "left_exists": left.exists(),
            "right_exists": right.exists(),
            "diffs": [],
        }

    left_files = _iter_files(left)
    right_files = _iter_files(right)
    diffs: list[dict[str, object]] = []
    if left_files != right_files:
        left_set = set(left_files)
        right_set = set(right_files)
        for rel in sorted(left_set - right_set):
            diffs.append({"path": rel.as_posix(), "kind": "missing_installed_file"})
        for rel in sorted(right_set - left_set):
            diffs.append({"path": rel.as_posix(), "kind": "unexpected_installed_file"})

    for rel in left_files:
        if rel not in right_files:
            continue
        left_bytes = (left / rel).read_bytes()
        right_bytes = (right / rel).read_bytes()
        if left_bytes == right_bytes:
            continue
        entry: dict[str, object] = {"path": rel.as_posix(), "kind": "bytes_differ"}
        if rel.suffix.lower() in TEXT_LIKE_SUFFIXES:
            entry["normalized_text_equal"] = _normalized_text_equal(
                left_bytes, right_bytes
            )
        diffs.append(entry)

    return {
        "matches": not diffs,
        "reason": "diffs_found" if diffs else "in_sync",
        "diffs": diffs,
    }


def build_installed_skill_sync_status(
    repo_root: str | Path,
    install_root: str | Path | None = None,
) -> dict[str, object]:
    root = Path(repo_root).resolve()
    source_skill = root / ".agents" / "skills" / "hsconfig"
    resolved_install_root = Path(install_root).expanduser() if install_root else DEFAULT_INSTALL_ROOT
    installed_skill = resolved_install_root / "hsconfig"
    diff = folder_diff(source_skill, installed_skill)
    matches = bool(diff.get("matches"))

    return {
        "status": "in_sync" if matches else "attention",
        "source_skill_path": str(source_skill),
        "installed_skill_path": str(installed_skill),
        "installed_skill_present": installed_skill.exists(),
        "matches_repo_skill": matches,
        "reason": str(diff.get("reason") or "unknown"),
        "diffs": list(diff.get("diffs", [])),
        "recommended_action": "none"
        if matches
        else "python scripts\\sync_installed_skill.py",
        "diagnostic_only": True,
        "runtime_apply_authority": "reports/operator_summary.json",
    }
```

- [ ] **Step 4: Reuse the shared diff in the sync script**

Modify the top of `scripts/sync_installed_skill.py`:

```python
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from hsconfig.skill_sync_status import DEFAULT_INSTALL_ROOT, folder_diff


SOURCE_SKILL = REPO_ROOT / ".agents" / "skills" / "hsconfig"
```

Then remove these now-duplicated definitions from `scripts/sync_installed_skill.py`:

```python
DEFAULT_INSTALL_ROOT = Path.home() / ".codex" / "skills"


def _iter_files(root: Path) -> list[Path]:
    return sorted(path.relative_to(root) for path in root.rglob("*") if path.is_file())


TEXT_LIKE_SUFFIXES = {".md", ".txt", ".json", ".yaml", ".yml", ".toml"}


def _normalized_text_equal(left_bytes: bytes, right_bytes: bytes) -> bool:
    return left_bytes.replace(b"\r\n", b"\n") == right_bytes.replace(b"\r\n", b"\n")


```

Keep `folders_match()`, `sync_skill()`, and `main()` unchanged except that they now call the imported `folder_diff()`.

- [ ] **Step 5: Run Task 1 tests**

Run:

```powershell
python -m pytest tests/test_skill_sync.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 1**

Run:

```powershell
git add src/hsconfig/skill_sync_status.py scripts/sync_installed_skill.py tests/test_skill_sync.py
git commit -m "feat: share installed skill sync status"
```

---

### Task 2: Project Installed Skill Sync Through Contract Preflight

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\contract_preflight.py`
- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\commands\contract_preflight.py`
- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\cli_parser.py`
- Test: `C:\Users\darbo\Documents\HSConfig\tests\test_contract_preflight.py`

**Interfaces:**
- Consumes: `build_installed_skill_sync_status(repo_root, install_root)`.
- Produces:
  - `build_contract_preflight(repo_root=".", git=None, skill_install_root=None) -> dict[str, object]`
  - payload key `installed_skill_sync: dict[str, object]`
  - check key `installed_skill_sync_current: bool`
  - CLI flag `hsconfig contract-preflight --skill-install-root <path> --json`

- [ ] **Step 1: Add failing contract-preflight tests**

Add imports at the top of `tests/test_contract_preflight.py`:

```python
from scripts.sync_installed_skill import sync_skill
```

Add this helper after `_clean_git()`:

```python
def _synced_install_root(tmp_path: Path) -> Path:
    install_root = tmp_path / "codex" / "skills"
    sync_skill(install_root)
    return install_root
```

Add these tests:

```python
def test_contract_preflight_reports_installed_skill_sync_when_clean(
    tmp_path: Path,
) -> None:
    install_root = _synced_install_root(tmp_path)

    payload = build_contract_preflight(
        Path("."),
        git=_clean_git(),
        skill_install_root=install_root,
    )

    assert payload["status"] == "PASS"
    assert payload["checks"]["installed_skill_sync_current"] is True
    assert "installed_skill_sync_current" not in payload["failures"]
    assert payload["installed_skill_sync"]["status"] == "in_sync"
    assert payload["installed_skill_sync"]["matches_repo_skill"] is True
    assert payload["installed_skill_sync"]["diagnostic_only"] is True
    assert (
        payload["installed_skill_sync"]["runtime_apply_authority"]
        == "reports/operator_summary.json"
    )


def test_contract_preflight_reports_attention_when_installed_skill_drifts(
    tmp_path: Path,
) -> None:
    install_root = _synced_install_root(tmp_path)
    installed_skill = install_root / "hsconfig" / "SKILL.md"
    installed_skill.write_text(
        installed_skill.read_text(encoding="utf-8") + "\n# drift\n",
        encoding="utf-8",
    )

    payload = build_contract_preflight(
        Path("."),
        git=_clean_git(),
        skill_install_root=install_root,
    )

    assert payload["status"] == "ATTENTION"
    assert payload["checks"]["installed_skill_sync_current"] is False
    assert "installed_skill_sync_current" in payload["failures"]
    assert payload["installed_skill_sync"]["status"] == "attention"
    assert payload["installed_skill_sync"]["recommended_action"] == (
        "python scripts\\sync_installed_skill.py"
    )
    assert payload["diagnostic_only"] is True
    assert payload["runtime_apply_authority"] == "reports/operator_summary.json"
    assert payload["source_status_apply_blocking"] is False
```

Update `test_contract_preflight_passes_for_repo_contract_with_clean_git_snapshot()`:

```python
def test_contract_preflight_passes_for_repo_contract_with_clean_git_snapshot(
    tmp_path: Path,
) -> None:
    payload = build_contract_preflight(
        Path("."),
        git=_clean_git(),
        skill_install_root=_synced_install_root(tmp_path),
    )
```

Update `test_contract_preflight_checks_configure_acceptance_route_contract()` the same way:

```python
def test_contract_preflight_checks_configure_acceptance_route_contract(
    tmp_path: Path,
) -> None:
    payload = build_contract_preflight(
        Path("."),
        git=_clean_git(),
        skill_install_root=_synced_install_root(tmp_path),
    )
```

- [ ] **Step 2: Run the failing tests**

Run:

```powershell
python -m pytest tests/test_contract_preflight.py::test_contract_preflight_reports_installed_skill_sync_when_clean tests/test_contract_preflight.py::test_contract_preflight_reports_attention_when_installed_skill_drifts -q
```

Expected: FAIL because `build_contract_preflight()` does not accept `skill_install_root` and the payload does not include `installed_skill_sync`.

- [ ] **Step 3: Extend `contract_preflight.py`**

Add this import near the existing imports:

```python
from hsconfig.skill_sync_status import build_installed_skill_sync_status
```

Add this key to `EXPECTED_CHECK_KEYS`:

```python
    "installed_skill_sync_current",
```

Change the function signature:

```python
def build_contract_preflight(
    repo_root: str | Path = ".",
    *,
    git: GitPreflight | None = None,
    skill_install_root: str | Path | None = None,
) -> dict[str, object]:
```

After `research_context = build_research_context_preflight(root)`, add:

```python
    installed_skill_sync = build_installed_skill_sync_status(
        root,
        skill_install_root,
    )
```

Add this check to the `checks` dictionary directly after `skill_root_present`:

```python
        "installed_skill_sync_current": (
            installed_skill_sync.get("matches_repo_skill") is True
            and installed_skill_sync.get("diagnostic_only") is True
            and installed_skill_sync.get("runtime_apply_authority")
            == "reports/operator_summary.json"
        ),
```

Add this payload entry after `"research_context": asdict(research_context),`:

```python
        "installed_skill_sync": installed_skill_sync,
```

- [ ] **Step 4: Add CLI parser flag**

In `src/hsconfig/cli_parser.py`, update the `contract-preflight` description to include installed skill sync:

```python
            "Read-only repo and skill contract preflight. Checks currentness, "
            "installed-skill sync, skill/reference routing, source-status "
            "non-blocking policy, no-default-only visibility, runtime surface "
            "boundary, and negative scope wording. This command does not grant "
            "apply permission and never writes runtime files."
```

After `contract_preflight.add_argument("--repo-root", default=".")`, add:

```python
    contract_preflight.add_argument(
        "--skill-install-root",
        default=None,
        help="Root directory that contains installed Codex skills.",
    )
```

- [ ] **Step 5: Pass the flag in the command wrapper**

In `src/hsconfig/commands/contract_preflight.py`, import the status helper:

```python
from hsconfig.skill_sync_status import build_installed_skill_sync_status
```

Change the normal call:

```python
        payload = build_contract_preflight(
            repo_root,
            skill_install_root=getattr(args, "skill_install_root", None),
        )
```

In the exception payload, add this key after `"research_context"` if the fallback currently lacks it, or after `"failures"` if no research fallback exists:

```python
            "installed_skill_sync": build_installed_skill_sync_status(
                repo_root,
                getattr(args, "skill_install_root", None),
            ),
```

If `repo_root` can be invalid in the exception path, wrap the helper in a small local fallback:

```python
def _unavailable_installed_skill_payload(repo_root: str, install_root: object) -> dict[str, object]:
    try:
        return build_installed_skill_sync_status(repo_root, install_root)
    except Exception as exc:
        return {
            "status": "attention",
            "source_skill_path": str(Path(repo_root).resolve() / ".agents" / "skills" / "hsconfig"),
            "installed_skill_path": str(Path.home() / ".codex" / "skills" / "hsconfig"),
            "installed_skill_present": False,
            "matches_repo_skill": False,
            "reason": type(exc).__name__,
            "diffs": [],
            "recommended_action": "python scripts\\sync_installed_skill.py",
            "diagnostic_only": True,
            "runtime_apply_authority": "reports/operator_summary.json",
        }
```

Then use:

```python
            "installed_skill_sync": _unavailable_installed_skill_payload(
                repo_root,
                getattr(args, "skill_install_root", None),
            ),
```

- [ ] **Step 6: Add CLI no-write test for install-root override**

Append to `tests/test_contract_preflight.py`:

```python
def test_contract_preflight_cli_reports_installed_skill_sync_without_writes(
    tmp_path: Path,
) -> None:
    install_root = _synced_install_root(tmp_path)
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    before = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        text=True,
        capture_output=True,
        check=True,
    ).stdout

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "hsconfig.cli",
            "contract-preflight",
            "--repo-root",
            ".",
            "--skill-install-root",
            str(install_root),
            "--json",
        ],
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
    payload = json.loads(result.stdout)

    assert result.returncode == 0
    assert payload["checks"]["installed_skill_sync_current"] is True
    assert payload["installed_skill_sync"]["matches_repo_skill"] is True
    assert payload["installed_skill_sync"]["diagnostic_only"] is True
    assert before == after
```

- [ ] **Step 7: Run Task 2 tests**

Run:

```powershell
python -m pytest tests/test_contract_preflight.py tests/test_skill_sync.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit Task 2**

Run:

```powershell
git add src/hsconfig/contract_preflight.py src/hsconfig/commands/contract_preflight.py src/hsconfig/cli_parser.py tests/test_contract_preflight.py tests/test_skill_sync.py
git commit -m "feat: expose installed skill sync in contract preflight"
```

---

### Task 3: Update Operator Docs And Skill Routing

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\docs\operator\README.md`
- Modify: `C:\Users\darbo\Documents\HSConfig\.agents\skills\hsconfig\SKILL.md`
- Test: `C:\Users\darbo\Documents\HSConfig\tests\test_skill_files.py`
- Test: `C:\Users\darbo\Documents\HSConfig\tests\test_operator_docs_contract_policy.py`

**Interfaces:**
- Consumes: `hsconfig contract-preflight --json` and optional `--skill-install-root`.
- Produces: operator-facing text saying installed-skill sync is read-only and diagnostic-only.

- [ ] **Step 1: Add failing docs test**

Append to `tests/test_skill_files.py`:

```python
def test_docs_and_skill_route_installed_skill_sync_through_contract_preflight():
    operator = Path("docs/operator/README.md").read_text(encoding="utf-8")
    skill = Path(".agents/skills/hsconfig/SKILL.md").read_text(encoding="utf-8")
    combined = f"{operator}\n{skill}"

    assert "installed-skill sync" in operator
    assert "hsconfig contract-preflight --json" in combined
    assert "--skill-install-root" in operator
    assert "diagnostic-only" in combined
    assert "does not replace `reports/operator_summary.json`" in combined
```

- [ ] **Step 2: Run failing docs test**

Run:

```powershell
python -m pytest tests/test_skill_files.py::test_docs_and_skill_route_installed_skill_sync_through_contract_preflight -q
```

Expected: FAIL because the new installed-skill preflight wording is not fully documented.

- [ ] **Step 3: Patch `docs/operator/README.md`**

In the `contract-preflight` paragraph near the top, replace the sentence with:

```markdown
Use `hsconfig contract-preflight --json` for a read-only repo and skill contract
check before source refresh, package generation, or runtime-facing apply review.
It checks currentness, installed-skill sync, skill reference routing,
source-status non-blocking policy, no-default-only visibility, supported runtime
surfaces, negative-scope boundaries, and the research-context lock around
`docs/research/current-truth.md`. Use `--skill-install-root <path>` only when
testing or checking a non-default Codex skill root. This preflight is
diagnostic-only and does not replace `reports/operator_summary.json`.
```

Keep the existing Developer Guardrail section, but add this sentence after line 336:

```markdown
The lower-level `hsconfig contract-preflight --json` exposes the same
installed-skill sync class in its JSON payload for quick operator checks.
```

- [ ] **Step 4: Patch `.agents/skills/hsconfig/SKILL.md` only in the expert path**

Add one compact bullet under `## Expert Paths`:

```markdown
- Drift check: `hsconfig contract-preflight --json` verifies repo currentness, installed-skill sync, and source/runtime contract wording as diagnostic-only; use `--skill-install-root` only for non-default skill roots.
```

Do not add this to the normal configure path.

- [ ] **Step 5: Run docs and skill tests**

Run:

```powershell
python -m pytest tests/test_skill_files.py tests/test_operator_docs_contract_policy.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 3**

Run:

```powershell
git add docs/operator/README.md .agents/skills/hsconfig/SKILL.md tests/test_skill_files.py tests/test_operator_docs_contract_policy.py
git commit -m "docs: route installed skill sync through preflight"
```

---

### Task 4: Final Verification, Installed Skill Sync, And Clean Worktree

**Files:**
- May modify through sync: files under `C:\Users\darbo\.codex\skills\hsconfig`
- No repo source files should be changed after verification starts unless a test fails and a focused fix is needed.

**Interfaces:**
- Consumes: committed implementation from Tasks 1-3.
- Produces: clean/current repo and installed skill in sync.

- [ ] **Step 1: Refresh repository state**

Run:

```powershell
git fetch --all --prune --tags
python scripts\check_hsconfig_currentness.py --cwd . --json
git status --short --branch
```

Expected:

```json
"dirty": false
"clean_for_runtime_work": true
"behind_origin_main": 0
```

- [ ] **Step 2: Sync installed HSConfig skill**

Run:

```powershell
python scripts\sync_installed_skill.py
python scripts\sync_installed_skill.py --check
```

Expected:

```text
Synced HSConfig skill to C:\Users\darbo\.codex\skills\hsconfig
HSConfig skill is in sync: C:\Users\darbo\.codex\skills\hsconfig
```

- [ ] **Step 3: Run the direct preflight**

Run:

```powershell
python -m hsconfig.cli contract-preflight --repo-root . --json
```

Expected:

```json
"status": "PASS"
"installed_skill_sync": {
  "status": "in_sync",
  "matches_repo_skill": true
}
"runtime_apply_authority": "reports/operator_summary.json"
"source_status_apply_blocking": false
"diagnostic_only": true
```

- [ ] **Step 4: Run focused tests**

Run:

```powershell
python -m pytest tests/test_contract_preflight.py tests/test_skill_sync.py tests/test_skill_files.py tests/test_operator_docs_contract_policy.py -q
```

Expected: PASS.

- [ ] **Step 5: Run developer guardrails**

Run:

```powershell
python scripts\check_contract_guardrails.py
```

Expected:

```text
OK: installed skill sync
OK: contract spine sentinel
OK: focused contract boundary tests
```

- [ ] **Step 6: Final clean/current check**

Run:

```powershell
python scripts\check_hsconfig_currentness.py --cwd . --json
git status --short --branch
```

Expected:

```json
"dirty": false
"clean_for_runtime_work": true
```

- [ ] **Step 7: Commit any verification-driven docs/test fix**

If Step 4 or Step 5 required a focused fix, run:

```powershell
git add src/hsconfig/skill_sync_status.py scripts/sync_installed_skill.py src/hsconfig/contract_preflight.py src/hsconfig/commands/contract_preflight.py src/hsconfig/cli_parser.py tests/test_contract_preflight.py tests/test_skill_sync.py tests/test_skill_files.py tests/test_operator_docs_contract_policy.py docs/operator/README.md .agents/skills/hsconfig/SKILL.md
git commit -m "test: verify installed skill preflight guardrail"
```

If no fix was needed, do not create an empty commit.

---

## Self-Review

**Spec coverage:** The plan implements the recommended single high-value improvement: installed skill / repo skill / operator contract drift visibility through the existing read-only preflight. It preserves HSConfig-only operation, no HSTuner, no log-driven tuning, no gameplay sequencing, no new runtime surfaces, and no second apply authority.

**Placeholder scan:** The plan contains no red-flag placeholder terms and no vague test-writing steps. Every code-changing task includes exact snippets and exact commands.

**Type consistency:** The new shared function name is `build_installed_skill_sync_status(repo_root, install_root=None)` throughout. The preflight key is consistently `installed_skill_sync`, and the boolean check is consistently `installed_skill_sync_current`.

**Execution choice:** This plan is ready for `superpowers:subagent-driven-development`. Use one worker for Task 1, one worker for Task 2, one worker for Task 3, and reserve Task 4 for the main agent final verification because it touches the real installed skill root.

# HSConfig Research Context Preflight Lock Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a small diagnostic-only research-context lock to `hsconfig contract-preflight` so historical `research-deep` folders and multiple `outline.yaml` files can never be mistaken for current operator or apply authority.

**Architecture:** Extend the existing read-only `contract-preflight` module with one focused dataclass and helper that reads `docs/research/current-truth-index.json`, checks the human current-truth file, counts historical research outlines, and emits diagnostic payload fields. The helper does not write files, does not run research, does not change `configure`, and does not affect runtime apply permission.

**Tech Stack:** Python standard library only, existing `pytest` tests, existing `hsconfig contract-preflight --json` CLI.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig`.
- Start execution with `git fetch --all --prune --tags`, `git status --short --branch`, and `python scripts\check_hsconfig_currentness.py --cwd . --json`.
- Keep the worktree clean at the end; no backups, no generated cache artifacts committed.
- `reports/operator_summary.json` remains the only normal runtime apply authority.
- `SOURCE_BACKED_STRONG` remains an evidence-quality label, not an apply gate.
- `source_status_apply_blocking` must remain `false`.
- `contract-preflight` remains read-only and diagnostic-only.
- Do not add runtime surfaces; normal HSConfig output remains `GlobalValues.json`, `Mulligan.json`, per-card `<CARDID>.json`, and `Combo.json` only when exact source-backed combo evidence exists.
- Do not use HSTuner, replay parsing, winrate analysis, or post-game tuning.
- Do not run or create a new `research-deep` outline for this change; this change only prevents old research folders from being misread.

---

## File Structure

- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\contract_preflight.py`
  - Add `ResearchContextPreflight`.
  - Add `build_research_context_preflight(repo_root: str | Path) -> ResearchContextPreflight`.
  - Add research-context checks and payload fields to `build_contract_preflight()`.
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_contract_preflight.py`
  - Add focused tests for current-truth presence, historical outline visibility, diagnostic-only authority, CLI JSON shape, and read-only behavior.
- Modify: `C:\Users\darbo\Documents\HSConfig\docs\operator\README.md`
  - Add one sentence to the existing `contract-preflight` note so operators know the research-context result is orientation only.
- Optional only if sync tests require it: `C:\Users\darbo\Documents\HSConfig\.agents\skills\hsconfig\SKILL.md`
  - Mirror one concise sentence that `contract-preflight` checks current research evidence routing as diagnostic-only.

---

### Task 1: Failing Contract Tests For Research Context Visibility

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_contract_preflight.py`

**Interfaces:**
- Consumes: existing `build_contract_preflight(repo_root: str | Path = ".", git: GitPreflight | None = None) -> dict[str, object]`.
- Produces: tests that define the expected new payload keys before implementation:
  - `payload["research_context"]`
  - `payload["checks"]["research_current_truth_index_visible"]`
  - `payload["checks"]["historical_research_outlines_diagnostic_only"]`

- [ ] **Step 1: Add failing tests**

Append these imports and tests to `tests/test_contract_preflight.py`. If `shutil` is not already imported, add it beside the current imports.

```python
import shutil
```

Append these tests at the end of the file:

```python
def test_contract_preflight_reports_research_context_as_diagnostic_only() -> None:
    payload = build_contract_preflight(Path("."), git=_clean_git())

    research_context = payload["research_context"]

    assert payload["checks"]["research_current_truth_index_visible"] is True
    assert payload["checks"]["historical_research_outlines_diagnostic_only"] is True
    assert research_context["status"] == "current"
    assert research_context["active_evidence_index_present"] is True
    assert research_context["active_evidence_index_path"] == "docs/research/current-truth.md"
    assert research_context["machine_evidence_index_path"] == "docs/research/current-truth-index.json"
    assert research_context["authority"] == "evidence_index_only"
    assert research_context["operator_gate_impact"] == "diagnostic_only"
    assert research_context["normal_apply_authority"] == "reports/operator_summary.json"
    assert research_context["historical_outlines_apply_authority"] is False
    assert research_context["recommended_research_entrypoint"] == "docs/research/current-truth.md"
    assert research_context["historical_outline_count"] > 0
    assert "docs/research/current-truth.md" not in research_context["historical_outline_paths"]


def test_contract_preflight_research_context_attention_when_current_truth_missing(
    tmp_path: Path,
) -> None:
    source_docs = Path("docs")
    target_docs = tmp_path / "docs"
    shutil.copytree(source_docs, target_docs)
    shutil.rmtree(target_docs / "research")
    (target_docs / "research").mkdir(parents=True)
    (target_docs / "research" / "historical-audit").mkdir()
    (target_docs / "research" / "historical-audit" / "outline.yaml").write_text(
        "items: []\n",
        encoding="utf-8",
    )

    skill_root = tmp_path / ".agents" / "skills" / "hsconfig"
    shutil.copytree(Path(".agents") / "skills" / "hsconfig", skill_root)

    payload = build_contract_preflight(tmp_path, git=_clean_git())
    research_context = payload["research_context"]

    assert payload["status"] == "ATTENTION"
    assert "research_current_truth_index_visible" in payload["failures"]
    assert payload["checks"]["research_current_truth_index_visible"] is False
    assert payload["checks"]["historical_research_outlines_diagnostic_only"] is True
    assert research_context["status"] == "attention"
    assert research_context["active_evidence_index_present"] is False
    assert research_context["historical_outline_count"] == 1
    assert research_context["historical_outlines_apply_authority"] is False
    assert payload["diagnostic_only"] is True
    assert payload["runtime_apply_authority"] == "reports/operator_summary.json"
    assert payload["source_status_apply_blocking"] is False


def test_contract_preflight_cli_includes_research_context_without_writing_files() -> None:
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

    assert result.returncode in (0, 1)
    assert "research_context" in payload
    assert payload["research_context"]["operator_gate_impact"] == "diagnostic_only"
    assert payload["research_context"]["normal_apply_authority"] == "reports/operator_summary.json"
    assert payload["research_context"]["historical_outlines_apply_authority"] is False
    assert payload["diagnostic_only"] is True
    assert before == after
```

- [ ] **Step 2: Run tests to verify they fail for the expected reason**

Run:

```powershell
python -m pytest tests\test_contract_preflight.py::test_contract_preflight_reports_research_context_as_diagnostic_only tests\test_contract_preflight.py::test_contract_preflight_research_context_attention_when_current_truth_missing tests\test_contract_preflight.py::test_contract_preflight_cli_includes_research_context_without_writing_files -q
```

Expected: FAIL because `research_context` and the two new check keys do not exist yet.

- [ ] **Step 3: Commit the red tests**

```powershell
git add tests\test_contract_preflight.py
git commit -m "test: define research context preflight lock"
```

---

### Task 2: Implement Diagnostic-Only Research Context Preflight

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\contract_preflight.py`
- Test: `C:\Users\darbo\Documents\HSConfig\tests\test_contract_preflight.py`

**Interfaces:**
- Consumes: local repo docs at `docs/research/current-truth.md`, `docs/research/current-truth-index.json`, and historical `docs/research/*/outline.yaml`.
- Produces:
  - `ResearchContextPreflight` dataclass.
  - `build_research_context_preflight(repo_root: str | Path) -> ResearchContextPreflight`.
  - `build_contract_preflight(...).research_context`.
  - Two new checks:
    - `research_current_truth_index_visible`
    - `historical_research_outlines_diagnostic_only`

- [ ] **Step 1: Add imports and expected check keys**

In `src/hsconfig/contract_preflight.py`, add `import json` after the future import block and append the two check names to `EXPECTED_CHECK_KEYS`.

```python
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import subprocess
```

Update `EXPECTED_CHECK_KEYS` to include the new keys at the end:

```python
EXPECTED_CHECK_KEYS = (
    "repo_current",
    "skill_root_present",
    "reference_files_present",
    "checklist_referenced_by_normal_workflow",
    "checklist_listed_in_references",
    "operator_summary_single_authority_visible",
    "source_status_nonblocking_visible",
    "no_default_only_visible",
    "runtime_surface_boundary_visible",
    "darkbishop_effect_not_mulligan_visible",
    "negative_scope_visible",
    "diagnostic_only_visible",
    "research_current_truth_index_visible",
    "historical_research_outlines_diagnostic_only",
)
```

- [ ] **Step 2: Add the dataclass and helpers**

Place this code after `GitPreflight`:

```python
@dataclass(frozen=True)
class ResearchContextPreflight:
    status: str
    active_evidence_index_present: bool
    active_evidence_index_path: str
    machine_evidence_index_present: bool
    machine_evidence_index_path: str
    authority: str
    operator_gate_impact: str
    normal_apply_authority: str
    recommended_research_entrypoint: str
    historical_outline_count: int
    historical_outline_paths: tuple[str, ...]
    historical_outlines_apply_authority: bool
    source_status_apply_blocking: bool
    notes: tuple[str, ...]
```

Place this helper near `_read()`:

```python
def _relative_posix(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()
```

Place this function after `_references_line()`:

```python
def build_research_context_preflight(repo_root: str | Path) -> ResearchContextPreflight:
    root = Path(repo_root).resolve()
    current_truth_path = root / "docs" / "research" / "current-truth.md"
    current_truth_index_path = root / "docs" / "research" / "current-truth-index.json"
    current_truth_text = _read(current_truth_path)
    index_text = _read(current_truth_index_path)
    index_payload: dict[str, object] = {}
    if index_text:
        try:
            parsed = json.loads(index_text)
        except json.JSONDecodeError:
            parsed = {}
        if isinstance(parsed, dict):
            index_payload = parsed

    research_root = root / "docs" / "research"
    historical_outline_paths: tuple[str, ...] = ()
    if research_root.exists():
        historical_outline_paths = tuple(
            sorted(
                _relative_posix(root, path)
                for path in research_root.glob("*/outline.yaml")
                if path.is_file()
            )
        )

    active_evidence_index_present = (
        current_truth_path.exists()
        and "docs/research/current-truth.md" in current_truth_text
        and "only active evidence index" in current_truth_text
    )
    machine_evidence_index_present = (
        current_truth_index_path.exists()
        and index_payload.get("authority") == "evidence_index_only"
        and index_payload.get("operator_gate_impact") == "diagnostic_only"
        and index_payload.get("normal_apply_authority") == "reports/operator_summary.json"
    )
    historical_outlines_apply_authority = False
    source_status_apply_blocking = bool(
        index_payload.get("research_snapshot_sync_policy", {}).get(
            "source_status_apply_blocking",
            False,
        )
        if isinstance(index_payload.get("research_snapshot_sync_policy"), dict)
        else False
    )
    status = (
        "current"
        if active_evidence_index_present
        and machine_evidence_index_present
        and not historical_outlines_apply_authority
        and not source_status_apply_blocking
        else "attention"
    )

    return ResearchContextPreflight(
        status=status,
        active_evidence_index_present=active_evidence_index_present,
        active_evidence_index_path="docs/research/current-truth.md",
        machine_evidence_index_present=machine_evidence_index_present,
        machine_evidence_index_path="docs/research/current-truth-index.json",
        authority=str(index_payload.get("authority") or "missing"),
        operator_gate_impact=str(index_payload.get("operator_gate_impact") or "missing"),
        normal_apply_authority=str(
            index_payload.get("normal_apply_authority") or "reports/operator_summary.json"
        ),
        recommended_research_entrypoint="docs/research/current-truth.md",
        historical_outline_count=len(historical_outline_paths),
        historical_outline_paths=historical_outline_paths,
        historical_outlines_apply_authority=historical_outlines_apply_authority,
        source_status_apply_blocking=source_status_apply_blocking,
        notes=(
            "Historical research outline files are evidence only.",
            "Use docs/research/current-truth.md before opening dated research folders.",
            "Research context diagnostics do not replace reports/operator_summary.json.",
        ),
    )
```

- [ ] **Step 3: Wire the helper into `build_contract_preflight()`**

Inside `build_contract_preflight()`, after `git_snapshot = git or build_git_preflight(root)`, add:

```python
    research_context = build_research_context_preflight(root)
```

Then add these checks to the `checks` dict:

```python
        "research_current_truth_index_visible": (
            research_context.status == "current"
            and research_context.active_evidence_index_present
            and research_context.machine_evidence_index_present
            and research_context.authority == "evidence_index_only"
            and research_context.operator_gate_impact == "diagnostic_only"
            and research_context.normal_apply_authority == "reports/operator_summary.json"
            and research_context.source_status_apply_blocking is False
        ),
        "historical_research_outlines_diagnostic_only": (
            research_context.historical_outlines_apply_authority is False
        ),
```

Finally, add `research_context` to the returned payload:

```python
        "research_context": asdict(research_context),
```

The final return object should still keep these existing authority fields unchanged:

```python
        "runtime_apply_authority": "reports/operator_summary.json",
        "source_status_apply_blocking": False,
        "diagnostic_only": True,
```

- [ ] **Step 4: Run focused tests**

Run:

```powershell
python -m pytest tests\test_contract_preflight.py -q
```

Expected: all `tests/test_contract_preflight.py` tests PASS.

- [ ] **Step 5: Run the CLI preflight**

Run:

```powershell
python -m hsconfig.cli contract-preflight --repo-root . --json
```

Expected:

- Exit code `0`.
- JSON includes `"status": "PASS"`.
- JSON includes `"diagnostic_only": true`.
- JSON includes `"runtime_apply_authority": "reports/operator_summary.json"`.
- JSON includes `"source_status_apply_blocking": false`.
- JSON includes `"research_context": { ... "status": "current" ... }`.

- [ ] **Step 6: Commit implementation**

```powershell
git add src\hsconfig\contract_preflight.py tests\test_contract_preflight.py
git commit -m "feat: add research context preflight lock"
```

---

### Task 3: Document The Research Context Diagnostic Boundary

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\docs\operator\README.md`
- Optional if tests require skill mirror: `C:\Users\darbo\Documents\HSConfig\.agents\skills\hsconfig\SKILL.md`
- Test: `C:\Users\darbo\Documents\HSConfig\tests\test_docs_active_path.py`

**Interfaces:**
- Consumes: the new `research_context` payload from `contract-preflight`.
- Produces: concise operator wording that tells future users and agents which research entrypoint is active and that historical outlines are diagnostic only.

- [ ] **Step 1: Add a docs test**

Append this test to `tests/test_docs_active_path.py`:

```python
def test_operator_readme_documents_contract_preflight_research_context_lock():
    text = Path("docs/operator/README.md").read_text(encoding="utf-8")

    assert "contract-preflight" in text
    assert "docs/research/current-truth.md" in text
    assert "historical research outline" in text
    assert "diagnostic-only" in text
    assert "operator_summary.json" in text
```

- [ ] **Step 2: Run the docs test and confirm it fails**

Run:

```powershell
python -m pytest tests\test_docs_active_path.py::test_operator_readme_documents_contract_preflight_research_context_lock -q
```

Expected: FAIL because the operator README does not yet name the new research-context lock wording.

- [ ] **Step 3: Update `docs/operator/README.md`**

Find the existing paragraph that starts with:

```markdown
Use `hsconfig contract-preflight --json` for a read-only repo and skill contract check
```

Replace that paragraph with:

```markdown
Use `hsconfig contract-preflight --json` for a read-only repo and skill contract check before source refresh, package generation, or runtime-facing apply review. It checks currentness, skill reference routing, source-status non-blocking policy, no-default-only visibility, supported runtime surfaces, negative-scope boundaries, and the research-context lock around `docs/research/current-truth.md`. Historical research outline files remain diagnostic-only evidence and do not replace `reports/operator_summary.json`.
```

- [ ] **Step 4: Update skill mirror only if required**

Run:

```powershell
python -m pytest tests\test_skill_sync.py tests\test_skill_files.py -q
```

Expected: PASS without modifying `.agents/skills/hsconfig/SKILL.md`. If this fails because the operator wording must be mirrored, add this sentence near the existing `contract-preflight` paragraph in `.agents/skills/hsconfig/SKILL.md`:

```markdown
`contract-preflight` also reports the research-context lock: `docs/research/current-truth.md` is the active evidence entrypoint, historical research outline files are diagnostic-only, and `reports/operator_summary.json` remains the normal apply authority.
```

- [ ] **Step 5: Run docs and skill tests**

Run:

```powershell
python -m pytest tests\test_docs_active_path.py::test_operator_readme_documents_contract_preflight_research_context_lock tests\test_skill_sync.py tests\test_skill_files.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit docs**

If only docs and tests changed:

```powershell
git add docs\operator\README.md tests\test_docs_active_path.py
git commit -m "docs: document research context preflight lock"
```

If `.agents/skills/hsconfig/SKILL.md` was also needed:

```powershell
git add docs\operator\README.md tests\test_docs_active_path.py .agents\skills\hsconfig\SKILL.md
git commit -m "docs: document research context preflight lock"
```

---

### Task 4: Boundary Verification And Clean Finish

**Files:**
- No new source files.
- Verify all files touched by Tasks 1-3.

**Interfaces:**
- Consumes: all changes from Tasks 1-3.
- Produces: a clean, pushed branch where the preflight lock is diagnostic-only and the worktree is clean.

- [ ] **Step 1: Run focused contract and docs tests**

Run:

```powershell
python -m pytest tests\test_contract_preflight.py tests\test_docs_active_path.py tests\test_skill_sync.py tests\test_skill_files.py -q
```

Expected: PASS.

- [ ] **Step 2: Run guardrail script**

Run:

```powershell
python scripts\check_contract_guardrails.py
```

Expected:

- Skill sync passes.
- Contract-spine sentinel passes.
- Focused contract boundary tests pass.
- Output still shows `apply_blocking=false`.

- [ ] **Step 3: Run CLI preflight**

Run:

```powershell
python -m hsconfig.cli contract-preflight --repo-root . --json
```

Expected:

- Exit code `0`.
- `"status": "PASS"`.
- `"diagnostic_only": true`.
- `"runtime_apply_authority": "reports/operator_summary.json"`.
- `"source_status_apply_blocking": false`.
- `"research_context": {"status": "current", ...}`.

- [ ] **Step 4: Confirm currentness and clean worktree**

Run:

```powershell
git fetch --all --prune --tags
git status --short --branch
python scripts\check_hsconfig_currentness.py --cwd . --json
```

Expected:

- Branch is not behind `origin/main`.
- `"dirty": false`.
- `"clean_for_runtime_work": true`.

- [ ] **Step 5: Push the branch**

Run:

```powershell
git push
```

Expected: current branch pushes successfully to its upstream.

---

## Self-Review

**Spec coverage:** The plan implements the recommended `Research-/Evidence-Context-Lock` in `contract-preflight`, keeps it diagnostic-only, preserves `operator_summary.json` authority, avoids runtime changes, avoids HSTuner/log analysis, and keeps worktree/currentness checks in the execution path.

**Placeholder scan:** The document contains no unresolved placeholder markers or deferred implementation notes. Each task has concrete file paths, code snippets, commands, and expected outcomes.

**Type consistency:** `ResearchContextPreflight`, `build_research_context_preflight()`, `research_context`, `research_current_truth_index_visible`, and `historical_research_outlines_diagnostic_only` are named consistently across tests, implementation, CLI payload, and docs.

**Execution choice:** This plan is suitable for Subagent-Driven execution. Use one worker for Task 1, one worker for Task 2, one worker for Task 3, and a final reviewer for Task 4. Only the Task 2 worker should modify `src/hsconfig/contract_preflight.py`; docs and tests are isolated by task.

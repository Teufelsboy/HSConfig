# HSConfig Acceptance Route Coherence Preflight Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a narrow `contract-preflight` coherence guard proving that the `configure_summary.acceptance_summary` operator route, diagnostic-only `config_quality_summary`, and single `operator_summary.json` apply authority remain aligned.

**Architecture:** Extend the existing read-only `hsconfig.contract_preflight` checks instead of adding a new command or runtime path. The new checks inspect existing repo skill/docs/operator text and fail preflight only when those contracts drift; they do not inspect logs, write runtime files, promote source strength, or create another apply gate.

**Tech Stack:** Python 3.11, pytest, existing `hsconfig` CLI, existing `.agents/skills/hsconfig` markdown docs.

## Global Constraints

- Keep HSConfig pre-run only: no replay parsing, runtime log analysis, winrate inspection, HSTuner dependency, or after-game tuning.
- Keep `reports/operator_summary.json` as the only normal runtime apply authority.
- Keep `<out>/configure_summary.json.acceptance_summary` as a compact operator projection, not a second apply gate.
- Keep `<out>/configure_summary.json.config_quality_summary` diagnostic-only and non-blocking.
- Keep `SOURCE_BACKED_STRONG` as an evidence-quality label, not a generation or apply blocker.
- Keep default-only runtime surfaces visible; do not allow silent default-only success.
- Keep valid decks load-safe and non-blocking even when source depth is partial.
- Do not add new dependencies or new CLI commands.
- Preserve clean currentness: finish with no dirty worktree.

---

## File Structure

- Modify `src/hsconfig/contract_preflight.py`
  - Owns read-only repo contract checks for currentness, skill/doc routing, diagnostic-only source status, no-default-only visibility, and the new configure acceptance route coherence.
- Modify `tests/test_contract_preflight.py`
  - Adds focused positive and negative tests for the new check keys.
- No change to `src/hsconfig/commands/configure.py`
  - `acceptance_summary` already exists and remains configure-local.
- No change to `.agents/skills/hsconfig/SKILL.md`, `.agents/skills/hsconfig/references/workflow.md`, or `docs/operator/README.md`
  - These already contain the desired route text; the preflight check should verify them, not rewrite them.

---

### Task 1: Add Failing Tests For Configure Acceptance Route Coherence

**Files:**
- Modify: `tests/test_contract_preflight.py`

**Interfaces:**
- Consumes: `build_contract_preflight(repo_root: str | Path, *, git: GitPreflight | None = None) -> dict[str, object]`
- Consumes: `_clean_git() -> GitPreflight`
- Produces: Tests that require these future check keys:
  - `configure_acceptance_route_visible`
  - `configure_acceptance_projection_not_gate_visible`
  - `config_quality_summary_diagnostic_only_visible`

- [ ] **Step 1: Add the positive failing test**

Add this test after `test_contract_preflight_passes_for_repo_contract_with_clean_git_snapshot` in `tests/test_contract_preflight.py`:

```python
def test_contract_preflight_checks_configure_acceptance_route_contract() -> None:
    payload = build_contract_preflight(Path("."), git=_clean_git())

    assert payload["status"] == "PASS"
    assert payload["checks"]["configure_acceptance_route_visible"] is True
    assert payload["checks"]["configure_acceptance_projection_not_gate_visible"] is True
    assert payload["checks"]["config_quality_summary_diagnostic_only_visible"] is True
    assert "configure_acceptance_route_visible" not in payload["failures"]
    assert "configure_acceptance_projection_not_gate_visible" not in payload["failures"]
    assert "config_quality_summary_diagnostic_only_visible" not in payload["failures"]
```

- [ ] **Step 2: Add the negative failing test**

Add this test near `test_contract_preflight_research_context_attention_when_current_truth_missing` in `tests/test_contract_preflight.py`:

```python
def test_contract_preflight_reports_attention_when_configure_acceptance_route_drifts(
    tmp_path: Path,
) -> None:
    skill_root = tmp_path / ".agents" / "skills" / "hsconfig"
    shutil.copytree(Path(".agents") / "skills" / "hsconfig", skill_root)

    operator_root = tmp_path / "docs" / "operator"
    operator_root.mkdir(parents=True)
    shutil.copy2(Path("docs") / "operator" / "README.md", operator_root / "README.md")

    research_root = tmp_path / "docs" / "research"
    research_root.mkdir(parents=True)
    for filename in ("current-truth.md", "current-truth-index.json"):
        shutil.copy2(Path("docs") / "research" / filename, research_root / filename)

    for path in (
        skill_root / "SKILL.md",
        skill_root / "references" / "workflow.md",
        operator_root / "README.md",
    ):
        text = path.read_text(encoding="utf-8")
        text = text.replace(
            "<out>/configure_summary.json.acceptance_summary",
            "<out>/configure_summary.json",
        )
        text = text.replace("use_config_now", "use_now")
        text = text.replace("next_report_to_open", "next_report")
        text = text.replace("diagnostic-only", "diagnostic")
        path.write_text(text, encoding="utf-8")

    payload = build_contract_preflight(tmp_path, git=_clean_git())

    assert payload["status"] == "ATTENTION"
    assert payload["checks"]["configure_acceptance_route_visible"] is False
    assert payload["checks"]["config_quality_summary_diagnostic_only_visible"] is False
    assert "configure_acceptance_route_visible" in payload["failures"]
    assert "config_quality_summary_diagnostic_only_visible" in payload["failures"]
    assert payload["runtime_apply_authority"] == "reports/operator_summary.json"
    assert payload["source_status_apply_blocking"] is False
    assert payload["diagnostic_only"] is True
```

- [ ] **Step 3: Run the new tests and verify they fail**

Run:

```powershell
python -m pytest tests/test_contract_preflight.py::test_contract_preflight_checks_configure_acceptance_route_contract tests/test_contract_preflight.py::test_contract_preflight_reports_attention_when_configure_acceptance_route_drifts -q
```

Expected: both tests fail with missing check keys such as `KeyError: 'configure_acceptance_route_visible'`.

---

### Task 2: Implement Acceptance Route Coherence Checks In Contract Preflight

**Files:**
- Modify: `src/hsconfig/contract_preflight.py`

**Interfaces:**
- Consumes: `combined: str`, the existing joined text of repo skill, workflow, checklist, and operator README.
- Produces: Three boolean entries in `payload["checks"]`:
  - `configure_acceptance_route_visible`
  - `configure_acceptance_projection_not_gate_visible`
  - `config_quality_summary_diagnostic_only_visible`

- [ ] **Step 1: Add new expected check keys**

In `src/hsconfig/contract_preflight.py`, extend `EXPECTED_CHECK_KEYS` with the new entries after `checklist_listed_in_references`:

```python
EXPECTED_CHECK_KEYS = (
    "repo_current",
    "skill_root_present",
    "reference_files_present",
    "checklist_referenced_by_normal_workflow",
    "checklist_listed_in_references",
    "configure_acceptance_route_visible",
    "configure_acceptance_projection_not_gate_visible",
    "config_quality_summary_diagnostic_only_visible",
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

- [ ] **Step 2: Add tiny helper functions**

Add these helpers after `_references_line`:

```python
def _has_any(text: str, phrases: tuple[str, ...]) -> bool:
    return any(phrase in text for phrase in phrases)


def _configure_acceptance_route_visible(combined: str) -> bool:
    return all(
        term in combined
        for term in (
            "<out>/configure_summary.json.acceptance_summary",
            "acceptance_summary",
            "use_config_now",
            "technical_status",
            "runtime_apply_allowed",
            "source_strength",
            "default_only_clean",
            "next_report_to_open",
            "<out>/configure_summary.json.config_quality_summary",
            "config_quality_summary",
            "reports/operator_summary.json",
        )
    )


def _configure_acceptance_projection_not_gate_visible(combined: str) -> bool:
    return (
        "operator projection" in combined
        and _has_any(
            combined,
            (
                "does not replace `reports/operator_summary.json` as apply authority",
                "does not replace `reports/operator_summary.json`",
                "does not replace `operator_summary.json`",
            ),
        )
        and _has_any(
            combined,
            (
                "operator_summary.json remains the only normal apply authority",
                "operator_summary.json` remains the only normal apply authority",
                "operator_summary.json` remains the normal apply authority",
                "reports/operator_summary.json` as the apply authority",
            ),
        )
    )


def _config_quality_summary_diagnostic_only_visible(combined: str) -> bool:
    return (
        "<out>/configure_summary.json.config_quality_summary" in combined
        and "config_quality_summary" in combined
        and "diagnostic-only" in combined
        and "non-blocking" in combined
        and "contract-doctor" in combined
        and _has_any(
            combined,
            (
                "operator_summary.json remains the only normal apply authority",
                "operator_summary.json` remains the only normal apply authority",
                "operator_summary.json` remains the normal apply authority",
            ),
        )
    )
```

- [ ] **Step 3: Wire the helpers into the checks map**

In `build_contract_preflight`, insert these entries in the `checks = { ... }` dict after `checklist_listed_in_references`:

```python
        "configure_acceptance_route_visible": _configure_acceptance_route_visible(
            combined
        ),
        "configure_acceptance_projection_not_gate_visible": (
            _configure_acceptance_projection_not_gate_visible(combined)
        ),
        "config_quality_summary_diagnostic_only_visible": (
            _config_quality_summary_diagnostic_only_visible(combined)
        ),
```

- [ ] **Step 4: Run the targeted tests and verify they pass**

Run:

```powershell
python -m pytest tests/test_contract_preflight.py::test_contract_preflight_checks_configure_acceptance_route_contract tests/test_contract_preflight.py::test_contract_preflight_reports_attention_when_configure_acceptance_route_drifts -q
```

Expected: `2 passed`.

---

### Task 3: Verify Existing Contract Preflight Behavior Remains Stable

**Files:**
- Test: `tests/test_contract_preflight.py`
- Test: `tests/test_skill_files.py`

**Interfaces:**
- Consumes: The new `EXPECTED_CHECK_KEYS` tuple.
- Produces: Stable CLI fallback payloads and no-write contract for `contract-preflight`.

- [ ] **Step 1: Run all contract preflight tests**

Run:

```powershell
python -m pytest tests/test_contract_preflight.py -q
```

Expected: all tests pass. The invalid-repo-root test must still confirm that `payload["checks"]` contains the same keys as a normal payload.

- [ ] **Step 2: Run skill routing tests**

Run:

```powershell
python -m pytest tests/test_skill_files.py::test_docs_and_skill_keep_config_quality_summary_diagnostic_only tests/test_skill_files.py::test_docs_skill_and_workflow_route_configure_acceptance_summary_first tests/test_skill_files.py::test_skill_and_workflow_stay_compact_and_canonical -q
```

Expected: `3 passed`.

- [ ] **Step 3: Run contract preflight from the CLI**

Run:

```powershell
python -m hsconfig.cli contract-preflight --json
```

Expected JSON includes:

```json
{
  "status": "PASS",
  "checks": {
    "configure_acceptance_route_visible": true,
    "configure_acceptance_projection_not_gate_visible": true,
    "config_quality_summary_diagnostic_only_visible": true,
    "operator_summary_single_authority_visible": true
  },
  "runtime_apply_authority": "reports/operator_summary.json",
  "source_status_apply_blocking": false,
  "diagnostic_only": true
}
```

---

### Task 4: Final Cleanliness, Skill Sync, And Commit

**Files:**
- Verify: `.agents/skills/hsconfig/SKILL.md`
- Verify: `C:\Users\darbo\.codex\skills\hsconfig`
- Commit: `src/hsconfig/contract_preflight.py`
- Commit: `tests/test_contract_preflight.py`

**Interfaces:**
- Consumes: Existing `scripts/sync_installed_skill.py --check`.
- Produces: Clean working tree and pushed branch.

- [ ] **Step 1: Verify installed skill is still in sync**

Run:

```powershell
python scripts\sync_installed_skill.py --check
```

Expected:

```text
HSConfig skill is in sync: C:\Users\darbo\.codex\skills\hsconfig
```

- [ ] **Step 2: Verify repo currentness and no dirty worktree before commit**

Run:

```powershell
python scripts\check_hsconfig_currentness.py --cwd . --json
git status --short --branch
```

Expected:

```json
{
  "behind_origin_main": 0,
  "dirty": false
}
```

`git status --short --branch` should show only the current branch line before code changes are staged. After implementation, it should show the two modified files until they are committed.

- [ ] **Step 3: Stage and commit implementation**

Run:

```powershell
git add src\hsconfig\contract_preflight.py tests\test_contract_preflight.py
git commit -m "test: guard configure acceptance route preflight"
```

Expected: commit succeeds with exactly those two files.

- [ ] **Step 4: Push the branch**

Run:

```powershell
git push
```

Expected: current branch pushes to its configured upstream.

- [ ] **Step 5: Verify clean final state**

Run:

```powershell
python scripts\check_hsconfig_currentness.py --cwd . --json
git status --short --branch
```

Expected:

```json
{
  "behind_origin_main": 0,
  "dirty": false
}
```

`git status --short --branch` should show only the branch line.

---

## Self-Review

- Spec coverage: The plan improves HSConfig technically without logs, HSTuner, gameplay heuristics, new runtime outputs, or new apply gates. It keeps the solution small by extending only the existing preflight surface and tests.
- Placeholder scan: The plan contains concrete filenames, functions, test bodies, implementation snippets, commands, and expected outputs.
- Type consistency: New checks are strings in `EXPECTED_CHECK_KEYS`, booleans in `payload["checks"]`, and entries in `payload["failures"]` when false. Existing CLI fallback remains covered through `EXPECTED_CHECK_KEYS`.

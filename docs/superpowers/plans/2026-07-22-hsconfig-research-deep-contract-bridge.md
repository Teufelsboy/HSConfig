# HSConfig Research-Deep Contract Bridge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make HSConfig's `contract-preflight` expose the actionable research-deep contract state directly, so generic 0/0 research validation cannot hide the first source action needed before honest `SOURCE_BACKED_STRONG` closure.

**Architecture:** Reuse the existing diagnostic-only research-result sentinel and existing `contract-preflight` payload. Add only a compact first non-promoting projection and separated strict/contract counters; do not create a new runtime gate, gameplay planner, log parser, or config writer path.

**Tech Stack:** Python 3, pytest, existing HSConfig CLI modules, existing `yaml` dependency, local Codex skill sync script.

## Global Constraints

- Target repo: `C:\Users\darbo\Documents\HSConfig`.
- Keep HSConfig pre-run only: no replay parsing, winrate analysis, runtime log analysis, HSTuner coupling, or after-game tuning.
- `reports/operator_summary.json` remains the only normal runtime apply authority.
- `SOURCE_BACKED_STRONG` remains an evidence-quality label, not an apply gate.
- `source_status_apply_blocking` must remain `false` for source-quality diagnostics.
- Do not block valid load-safe deck packages because research evidence is partial, stale, seed-only, or thin.
- Do not emit or normalize gameplay sequencing rules; HearthRanger owns play ordering.
- Do not add runtime surfaces outside the normal HSConfig path: `GlobalValues.json`, `Mulligan.json`, per-card `<CARDID>.json`, and conditional `Combo.json`.
- Do not introduce new dependencies.
- Keep `.agents/skills/hsconfig/SKILL.md` and `.agents/skills/hsconfig/references/workflow.md` compact enough for existing skill-file tests.
- End with a clean, current worktree and synced installed `hsconfig` skill.

---

## File Structure

- Modify `src/hsconfig/research_result_contract_sentinel.py`
  - Responsibility: compute diagnostic-only research batch summary from `fields.yaml` and `results/*.json`.
  - Add first non-promoting row projection and separated promotion counters.

- Modify `src/hsconfig/contract_preflight.py`
  - Responsibility: repo, skill, docs, and research contract preflight payload.
  - Propagate the new sentinel summary fields into `research_context`.

- Modify `src/hsconfig/commands/contract_preflight.py`
  - Responsibility: CLI fallback payload when preflight building raises.
  - Keep fallback schema aligned with `ResearchContextPreflight`.

- Modify `tests/test_research_result_contract_sentinel.py`
  - Responsibility: unit coverage for the sentinel summary.
  - Add a deterministic first non-promoting row test and update exact summary assertions.

- Modify `tests/test_contract_preflight.py`
  - Responsibility: preflight schema and CLI stability tests.
  - Add a deterministic temp-repo research batch test for projected first non-promoting fields.

- Modify `tests/test_skill_files.py`
  - Responsibility: docs and skill contract wording tests.
  - Add compact wording coverage for the research-deep bridge.

- Modify `.agents/skills/hsconfig/SKILL.md`
  - Responsibility: installed skill source of truth inside the repo.
  - Add one compact operator note for the first non-promoting research-deep projection.

- Modify `.agents/skills/hsconfig/references/workflow.md`
  - Responsibility: normal HSConfig workflow reference.
  - Add the same concise bridge semantics without expanding the workflow.

- Modify `docs/operator/README.md`
  - Responsibility: normal operator entry point.
  - Add a short explanation of the research-deep bridge fields.

- Sync `C:\Users\darbo\.codex\skills\hsconfig`
  - Responsibility: active installed skill mirrors the repo skill.

## Non-Goals

- Do not add a new CLI command.
- Do not modify `src/hsconfig/commands/configure.py`.
- Do not put repo-wide research-deep batch state into deck-specific `configure_summary.json`.
- Do not make preflight failures block `hsconfig configure`, `hsconfig apply`, or package generation.
- Do not add web research, deck crawling, or online source acquisition in this task.
- Do not change ShadowPriest, Darkbishop, mulligan, or per-card runtime behavior.

### Task 1: Currentness And Clean Base

**Files:**
- Read: `C:\Users\darbo\Documents\HSConfig`

**Interfaces:**
- Consumes: Git remotes and current branch state.
- Produces: verified clean/current starting point for implementation.

- [ ] **Step 1: Refresh remotes**

```powershell
git fetch --all --prune --tags
```

Expected: command exits `0`.

- [ ] **Step 2: Verify HSConfig currentness**

```powershell
python scripts\check_hsconfig_currentness.py --cwd . --json
```

Expected JSON contains:

```json
{
  "behind_origin_main": 0,
  "dirty": false,
  "clean_for_runtime_work": true
}
```

- [ ] **Step 3: Verify clean worktree**

```powershell
git status --short --branch
```

Expected: only the branch line is printed.

### Task 2: Add Sentinel First Non-Promoting Projection

**Files:**
- Modify: `tests/test_research_result_contract_sentinel.py`
- Modify: `src/hsconfig/research_result_contract_sentinel.py`

**Interfaces:**
- Consumes: `build_research_result_contract_sentinel(fields_path, results_dir) -> dict[str, Any]`.
- Produces: sentinel summary fields:
  - `promotion_ready_deck_count: int`
  - `non_promoting_count: int`
  - `first_non_promoting_result: str`
  - `first_non_promoting_action: str`
  - `first_non_promoting_reason: str`

- [ ] **Step 1: Write the failing sentinel test**

Append this test to `tests/test_research_result_contract_sentinel.py`:

```python
def test_sentinel_summary_names_first_non_promoting_result_and_action(
    tmp_path: Path,
) -> None:
    fields_path = tmp_path / "fields.yaml"
    fields_path.write_text(yaml.safe_dump(FIELDS), encoding="utf-8")
    results_dir = tmp_path / "results"
    _write_json(
        results_dir / "01StrongPriest.json",
        {
            "deck_name": "StrongPriest",
            "deck_code": "AAEBAa0GAAAA",
            "archetype": "Wild Shadow Priest",
            "current_deck_sources": [],
            "guide_sources": [
                {
                    "url": "https://example.test/strong-priest-guide",
                    "source_visibility": "full_text",
                    "freshness_status": "current",
                }
            ],
            "source_strength": "exact_full_text_guide",
            "source_visibility": "full_text",
            "current_or_evergreen": True,
            "lowerable_claim_kinds": ["mulligan_keep"],
            "non_promoting_support": [],
            "default_only_runtime_surfaces": [],
            "first_missing_source_action": "none",
            "notes": "Strong control row.",
        },
    )
    _write_json(
        results_dir / "02PirateDH.json",
        {
            "deck_name": "PirateDH",
            "archetype": "Wild Pirate Demon Hunter",
            "current_deck_sources": [],
            "guide_sources": [],
            "source_strength": "unfetched_acquisition_seed",
            "lowerable_claim_kinds": [],
            "non_promoting_support": [],
            "first_missing_source_action": (
                "fetch_and_normalize_candidate_full_text_claims"
            ),
            "notes": "Seed row still needs full-text claims.",
        },
    )

    report = build_research_result_contract_sentinel(fields_path, results_dir)
    summary = report["summary"]

    assert summary["status"] == "clean"
    assert summary["strong_promoting_count"] == 1
    assert summary["promotion_ready_deck_count"] == 1
    assert summary["non_promoting_count"] == 1
    assert summary["first_non_promoting_result"] == "PirateDH"
    assert (
        summary["first_non_promoting_action"]
        == "fetch_and_normalize_candidate_full_text_claims"
    )
    assert summary["first_non_promoting_reason"] == "seed_only"
    assert summary["source_status_apply_blocking"] is False
```

- [ ] **Step 2: Run the focused failing test**

```powershell
python -m pytest tests\test_research_result_contract_sentinel.py::test_sentinel_summary_names_first_non_promoting_result_and_action -q
```

Expected: FAIL with a missing key such as `promotion_ready_deck_count` or `first_non_promoting_result`.

- [ ] **Step 3: Update the existing exact summary assertion**

In `test_sentinel_reports_valid_partial_results_without_apply_blocking`, extend the expected `report["summary"]` dict with:

```python
        "promotion_ready_deck_count": 0,
        "non_promoting_count": 1,
        "first_non_promoting_result": "ShadowPriest",
        "first_non_promoting_action": (
            "fetch_and_normalize_candidate_full_text_claims"
        ),
        "first_non_promoting_reason": "seed_only",
```

- [ ] **Step 4: Implement the sentinel projection**

Modify imports in `src/hsconfig/research_result_contract_sentinel.py`:

```python
from collections.abc import Mapping
from pathlib import Path
from typing import Any
```

In `build_research_result_contract_sentinel`, after `current_or_evergreen_count` is computed, add:

```python
    first_non_promoting = _first_non_promoting_row(rows)
```

In the returned `summary` dict, after `strong_promoting_count`, add:

```python
            "promotion_ready_deck_count": strong_promoting_count,
            "non_promoting_count": len(rows) - strong_promoting_count,
            "first_non_promoting_result": _row_identity(first_non_promoting),
            "first_non_promoting_action": _row_action(first_non_promoting),
            "first_non_promoting_reason": _row_reason(first_non_promoting),
```

Add these helper functions below `_read_yaml_mapping`:

```python
def _first_non_promoting_row(
    rows: list[dict[str, Any]],
) -> dict[str, Any] | None:
    for row in rows:
        if row["canonical_promotion_allowed"] is False:
            return row
    return None


def _row_identity(row: Mapping[str, Any] | None) -> str:
    if row is None:
        return ""
    deck_name = str(row.get("deck_name") or "").strip()
    if deck_name:
        return deck_name
    path = str(row.get("path") or "").strip()
    return Path(path).stem if path else ""


def _row_action(row: Mapping[str, Any] | None) -> str:
    if row is None:
        return "none"
    action = str(row.get("first_missing_source_action") or "").strip()
    if action:
        return action
    errors = row.get("strict_research_result_errors")
    if isinstance(errors, list) and errors:
        return str(errors[0])
    if row.get("contract_valid") is False:
        return "close_research_result_contract"
    return "none"


def _row_reason(row: Mapping[str, Any] | None) -> str:
    if row is None:
        return "none"
    errors = row.get("strict_research_result_errors")
    if isinstance(errors, list) and errors:
        return str(errors[0])
    if row.get("contract_valid") is False:
        return "contract_invalid"
    return str(row.get("snapshot_kind") or "not_source_backed_strong")
```

- [ ] **Step 5: Run sentinel tests**

```powershell
python -m pytest tests\test_research_result_contract_sentinel.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 2**

```powershell
git add src\hsconfig\research_result_contract_sentinel.py tests\test_research_result_contract_sentinel.py
git commit -m "feat: expose research contract first non-promoting result"
```

Expected: commit succeeds.

### Task 3: Project Research Bridge Fields Into Contract Preflight

**Files:**
- Modify: `tests/test_contract_preflight.py`
- Modify: `src/hsconfig/contract_preflight.py`
- Modify: `src/hsconfig/commands/contract_preflight.py`

**Interfaces:**
- Consumes: sentinel summary fields from Task 2.
- Produces: `contract-preflight.research_context.latest_research_result_contract_*` fields:
  - `latest_research_result_contract_strict_invalid_count: int`
  - `latest_research_result_contract_contract_invalid_count: int`
  - `latest_research_result_contract_seed_only_count: int`
  - `latest_research_result_contract_strong_promoting_count: int`
  - `latest_research_result_contract_promotion_ready_deck_count: int`
  - `latest_research_result_contract_non_promoting_count: int`
  - `latest_research_result_contract_first_non_promoting_result: str`
  - `latest_research_result_contract_first_non_promoting_action: str`
  - `latest_research_result_contract_first_non_promoting_reason: str`

- [ ] **Step 1: Write the failing contract-preflight projection test**

Append this test to `tests/test_contract_preflight.py` near the existing research-context tests:

```python
def test_contract_preflight_projects_research_contract_first_non_promoting_result(
    tmp_path: Path,
) -> None:
    source_docs = Path("docs")
    target_docs = tmp_path / "docs"
    shutil.copytree(source_docs, target_docs)
    skill_root = tmp_path / ".agents" / "skills" / "hsconfig"
    shutil.copytree(Path(".agents") / "skills" / "hsconfig", skill_root)

    latest = target_docs / "research" / "9999-bridge-research"
    (latest / "results").mkdir(parents=True)
    shutil.copy2(
        Path("docs")
        / "research"
        / "2026-07-17-hsconfig-source-contract-acceptance-loop"
        / "fields.yaml",
        latest / "fields.yaml",
    )
    (latest / "results" / "PirateDH.json").write_text(
        json.dumps(
            {
                "deck_name": "PirateDH",
                "archetype": "Wild Pirate Demon Hunter",
                "current_deck_sources": [],
                "guide_sources": [],
                "source_strength": "unfetched_acquisition_seed",
                "lowerable_claim_kinds": [],
                "non_promoting_support": [],
                "first_missing_source_action": (
                    "fetch_and_normalize_candidate_full_text_claims"
                ),
                "notes": "Seed row still needs full-text claims.",
            }
        ),
        encoding="utf-8",
    )

    payload = build_contract_preflight(
        tmp_path,
        git=_clean_git(),
        skill_install_root=_synced_install_root(tmp_path),
    )
    research_context = payload["research_context"]

    assert payload["checks"]["research_result_contract_sentinel_visible"] is True
    assert research_context["latest_research_result_contract_status"] == "clean"
    assert research_context["latest_research_result_contract_result_count"] == 1
    assert research_context["latest_research_result_contract_invalid_count"] == 0
    assert research_context["latest_research_result_contract_strict_invalid_count"] == 0
    assert research_context["latest_research_result_contract_contract_invalid_count"] == 0
    assert research_context["latest_research_result_contract_seed_only_count"] == 1
    assert research_context["latest_research_result_contract_strong_promoting_count"] == 0
    assert (
        research_context[
            "latest_research_result_contract_promotion_ready_deck_count"
        ]
        == 0
    )
    assert research_context["latest_research_result_contract_non_promoting_count"] == 1
    assert (
        research_context[
            "latest_research_result_contract_first_non_promoting_result"
        ]
        == "PirateDH"
    )
    assert (
        research_context[
            "latest_research_result_contract_first_non_promoting_action"
        ]
        == "fetch_and_normalize_candidate_full_text_claims"
    )
    assert (
        research_context[
            "latest_research_result_contract_first_non_promoting_reason"
        ]
        == "seed_only"
    )
    assert research_context["source_status_apply_blocking"] is False
```

- [ ] **Step 2: Run the focused failing test**

```powershell
python -m pytest tests\test_contract_preflight.py::test_contract_preflight_projects_research_contract_first_non_promoting_result -q
```

Expected: FAIL with a missing `latest_research_result_contract_*` field.

- [ ] **Step 3: Extend the dataclass**

In `src/hsconfig/contract_preflight.py`, add these fields to `ResearchContextPreflight` after `latest_research_result_contract_invalid_count`:

```python
    latest_research_result_contract_strict_invalid_count: int
    latest_research_result_contract_contract_invalid_count: int
    latest_research_result_contract_seed_only_count: int
    latest_research_result_contract_strong_promoting_count: int
    latest_research_result_contract_promotion_ready_deck_count: int
    latest_research_result_contract_non_promoting_count: int
    latest_research_result_contract_first_non_promoting_result: str
    latest_research_result_contract_first_non_promoting_action: str
    latest_research_result_contract_first_non_promoting_reason: str
```

- [ ] **Step 4: Add default research-contract payload fields**

In each early return inside `_latest_research_result_contract`, include these key/value pairs:

```python
            "strict_invalid_count": 0,
            "contract_invalid_count": 0,
            "seed_only_count": 0,
            "strong_promoting_count": 0,
            "promotion_ready_deck_count": 0,
            "non_promoting_count": 0,
            "first_non_promoting_result": "",
            "first_non_promoting_action": "none",
            "first_non_promoting_reason": "none",
```

Keep the existing values for `status`, `path`, `result_count`, `invalid_count`, `freshness_missing_count`, and `no_op_validation_risk`.

- [ ] **Step 5: Project fields from the sentinel summary**

Replace the final return in `_latest_research_result_contract` with this shape:

```python
    strict_invalid_count = int(summary.get("strict_invalid_count") or 0)
    contract_invalid_count = int(summary.get("contract_invalid_count") or 0)
    return {
        "status": str(summary["status"]),
        "path": _relative_posix(root, latest),
        "result_count": int(summary["result_count"]),
        "invalid_count": strict_invalid_count + contract_invalid_count,
        "strict_invalid_count": strict_invalid_count,
        "contract_invalid_count": contract_invalid_count,
        "seed_only_count": int(summary.get("seed_only_count") or 0),
        "strong_promoting_count": int(summary.get("strong_promoting_count") or 0),
        "promotion_ready_deck_count": int(
            summary.get("promotion_ready_deck_count")
            or summary.get("strong_promoting_count")
            or 0
        ),
        "non_promoting_count": int(summary.get("non_promoting_count") or 0),
        "first_non_promoting_result": str(
            summary.get("first_non_promoting_result") or ""
        ),
        "first_non_promoting_action": str(
            summary.get("first_non_promoting_action") or "none"
        ),
        "first_non_promoting_reason": str(
            summary.get("first_non_promoting_reason") or "none"
        ),
        "freshness_missing_count": int(summary.get("freshness_missing_count") or 0),
        "no_op_validation_risk": bool(summary["no_op_validation_risk"]),
    }
```

- [ ] **Step 6: Wire fields into `build_research_context_preflight`**

In the `ResearchContextPreflight(...)` construction, add:

```python
        latest_research_result_contract_strict_invalid_count=int(
            latest_research_contract["strict_invalid_count"]
        ),
        latest_research_result_contract_contract_invalid_count=int(
            latest_research_contract["contract_invalid_count"]
        ),
        latest_research_result_contract_seed_only_count=int(
            latest_research_contract["seed_only_count"]
        ),
        latest_research_result_contract_strong_promoting_count=int(
            latest_research_contract["strong_promoting_count"]
        ),
        latest_research_result_contract_promotion_ready_deck_count=int(
            latest_research_contract["promotion_ready_deck_count"]
        ),
        latest_research_result_contract_non_promoting_count=int(
            latest_research_contract["non_promoting_count"]
        ),
        latest_research_result_contract_first_non_promoting_result=str(
            latest_research_contract["first_non_promoting_result"]
        ),
        latest_research_result_contract_first_non_promoting_action=str(
            latest_research_contract["first_non_promoting_action"]
        ),
        latest_research_result_contract_first_non_promoting_reason=str(
            latest_research_contract["first_non_promoting_reason"]
        ),
```

- [ ] **Step 7: Update CLI fallback schema**

In `src/hsconfig/commands/contract_preflight.py`, add these fields to `_unavailable_research_context_payload` after `latest_research_result_contract_invalid_count`:

```python
            "latest_research_result_contract_strict_invalid_count": 0,
            "latest_research_result_contract_contract_invalid_count": 0,
            "latest_research_result_contract_seed_only_count": 0,
            "latest_research_result_contract_strong_promoting_count": 0,
            "latest_research_result_contract_promotion_ready_deck_count": 0,
            "latest_research_result_contract_non_promoting_count": 0,
            "latest_research_result_contract_first_non_promoting_result": "",
            "latest_research_result_contract_first_non_promoting_action": "none",
            "latest_research_result_contract_first_non_promoting_reason": "none",
```

- [ ] **Step 8: Run preflight tests**

```powershell
python -m pytest tests\test_contract_preflight.py -q
```

Expected: PASS.

- [ ] **Step 9: Commit Task 3**

```powershell
git add src\hsconfig\contract_preflight.py src\hsconfig\commands\contract_preflight.py tests\test_contract_preflight.py
git commit -m "feat: project research contract preflight details"
```

Expected: commit succeeds.

### Task 4: Document The Research-Deep Contract Bridge

**Files:**
- Modify: `tests/test_skill_files.py`
- Modify: `.agents/skills/hsconfig/SKILL.md`
- Modify: `.agents/skills/hsconfig/references/workflow.md`
- Modify: `docs/operator/README.md`
- Sync: `C:\Users\darbo\.codex\skills\hsconfig`

**Interfaces:**
- Consumes: `contract-preflight.research_context.latest_research_result_contract_first_non_promoting_*`.
- Produces: concise operator wording that this projection is diagnostic-only and cannot promote, downgrade, block, apply, or tune a package.

- [ ] **Step 1: Write the failing docs/skill wording test**

Append this test to `tests/test_skill_files.py`:

```python
def test_skill_and_operator_docs_explain_research_deep_contract_bridge() -> None:
    paths = [
        REPO_ROOT / ".agents" / "skills" / "hsconfig" / "SKILL.md",
        REPO_ROOT
        / ".agents"
        / "skills"
        / "hsconfig"
        / "references"
        / "workflow.md",
        REPO_ROOT / "docs" / "operator" / "README.md",
    ]
    required = [
        "latest_research_result_contract_first_non_promoting_*",
        "first source action needed for Strong closure",
        "diagnostic-only",
        "cannot block or promote a package",
        "operator_summary.json remains the only normal apply authority",
    ]

    for path in paths:
        text = path.read_text(encoding="utf-8")
        for phrase in required:
            assert phrase in text, f"{path}: {phrase}"
```

- [ ] **Step 2: Run the focused failing docs test**

```powershell
python -m pytest tests\test_skill_files.py::test_skill_and_operator_docs_explain_research_deep_contract_bridge -q
```

Expected: FAIL until the wording is added to all three docs/skill files.

- [ ] **Step 3: Update the repo skill**

In `.agents/skills/hsconfig/SKILL.md`, add this exact sentence to the existing research-status-sync / `contract-preflight.research_context.latest_research_result_contract_*` bullet:

```text
`latest_research_result_contract_first_non_promoting_*` names the first source action needed for Strong closure; it is diagnostic-only, cannot block or promote a package, and operator_summary.json remains the only normal apply authority.
```

- [ ] **Step 4: Update the workflow reference**

In `.agents/skills/hsconfig/references/workflow.md`, extend the `Source-Depth And Diagnostics` section with this exact sentence:

```text
`contract-preflight.research_context.latest_research_result_contract_first_non_promoting_*` names the first source action needed for Strong closure; it is diagnostic-only, cannot block or promote a package, and operator_summary.json remains the only normal apply authority.
```

- [ ] **Step 5: Update operator docs**

In `docs/operator/README.md`, extend the paragraph that starts with `` `contract-preflight.research_context.latest_research_result_contract_*` `` with this exact sentence:

```text
`latest_research_result_contract_first_non_promoting_*` names the first source action needed for Strong closure; it is diagnostic-only, cannot block or promote a package, and operator_summary.json remains the only normal apply authority.
```

- [ ] **Step 6: Sync the installed skill**

```powershell
python scripts\sync_installed_skill.py --install-root C:\Users\darbo\.codex\skills
```

Expected: installed `C:\Users\darbo\.codex\skills\hsconfig\SKILL.md` matches `.agents\skills\hsconfig\SKILL.md`.

- [ ] **Step 7: Run docs/skill tests**

```powershell
python -m pytest tests\test_skill_files.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit Task 4**

```powershell
git add tests\test_skill_files.py .agents\skills\hsconfig\SKILL.md .agents\skills\hsconfig\references\workflow.md docs\operator\README.md
git commit -m "docs: explain research-deep contract bridge"
```

Expected: commit succeeds.

### Task 5: Final Verification And Push

**Files:**
- Read: all modified files and repo status.

**Interfaces:**
- Consumes: all changes from Tasks 2 through 4.
- Produces: verified, pushed, clean branch.

- [ ] **Step 1: Run focused contract verification**

```powershell
python -m pytest tests\test_research_result_contract_sentinel.py tests\test_contract_preflight.py tests\test_skill_files.py -q
```

Expected: PASS.

- [ ] **Step 2: Run guardrails**

```powershell
python scripts\check_contract_guardrails.py
```

Expected: PASS. The output must not report installed skill drift.

- [ ] **Step 3: Run contract preflight**

```powershell
python -m hsconfig.cli contract-preflight --json
```

Expected JSON contains:

```json
{
  "status": "PASS",
  "runtime_apply_authority": "reports/operator_summary.json",
  "source_status_apply_blocking": false,
  "diagnostic_only": true
}
```

Also verify the JSON includes:

```json
{
  "research_context": {
    "latest_research_result_contract_strict_invalid_count": 0,
    "latest_research_result_contract_contract_invalid_count": 0,
    "latest_research_result_contract_first_non_promoting_action": "..."
  }
}
```

The exact current counts may reflect the latest checked-in research batch. Do not rewrite historical research result JSONs in this task.

- [ ] **Step 4: Check formatting and status**

```powershell
git diff --check
git status --short --branch
python scripts\check_hsconfig_currentness.py --cwd . --json
```

Expected:

- `git diff --check` exits `0`.
- Branch is not behind `origin/main`.
- Worktree is clean after the final commit.

- [ ] **Step 5: Push**

```powershell
git push
```

Expected: branch pushes to its configured upstream.

## Subagent Split

- **Explorer:** read-only confirmation of current sentinel, preflight, CLI fallback, and docs insertion points.
- **Worker 1:** implement Task 2 only.
- **Reviewer 1:** review Task 2 diff for diagnostic-only behavior and exact summary compatibility.
- **Worker 2:** implement Task 3 only.
- **Reviewer 2:** review Task 3 diff for schema compatibility and fallback alignment.
- **Worker 3:** implement Task 4 only.
- **Final Reviewer:** run Task 5 and inspect the final diff for scope drift.

Only one worker writes a given file in a given task. Reviewers are read-only.

## Acceptance Criteria

- `build_research_result_contract_sentinel(...)` reports first non-promoting research result details.
- `contract-preflight.research_context` exposes separated strict/contract invalid counts.
- `contract-preflight.research_context` exposes first non-promoting result, action, and reason.
- Existing combined `latest_research_result_contract_invalid_count` remains for compatibility.
- `source_status_apply_blocking` remains `false` in all new payload paths.
- `runtime_apply_authority` remains `reports/operator_summary.json`.
- `contract-preflight` remains diagnostic-only.
- No new CLI command is added.
- `configure_summary.json` is not changed.
- No runtime config JSON generation behavior changes.
- Docs and repo skill explain the bridge in one compact diagnostic-only sentence.
- Installed `hsconfig` skill is synced.
- Tests and guardrails pass.
- Branch is pushed and the worktree is clean.

## Self-Review

- Spec coverage: the plan covers the research-deep no-op visibility issue, the first missing Strong-closure action, non-blocking source status, no-default-only discipline, currentness, and clean worktree requirements.
- Placeholder scan: the plan contains concrete file paths, exact field names, exact test code, exact implementation snippets, and exact verification commands.
- Type consistency: all new preflight fields use the `latest_research_result_contract_*` prefix and map from sentinel summary fields with stable `int` or `str` values.

## Execution Handoff

Plan complete. Recommended execution mode: Subagent-Driven. Use `superpowers:subagent-driven-development`, `superpowers:test-driven-development`, and `superpowers:verification-before-completion`.

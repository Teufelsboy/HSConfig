# HSConfig Configure Quality Summary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface the existing diagnostic `config_quality` contract directly in `configure_summary.json` as a compact, non-blocking `config_quality_summary`, so normal `hsconfig configure` output immediately shows whether the generated package is clean or needs diagnostic attention.

**Architecture:** Reuse `build_config_quality_report(package_dir)` from `src/hsconfig/config_quality_contract.py`. Add a tiny summarizer in `src/hsconfig/commands/configure.py`, call it after package/operator-summary generation, and include the result only in the top-level configure output `<out>/configure_summary.json`. Keep detailed diagnostics in `contract-doctor`. Keep `operator_summary.json` as the only normal apply authority.

**Tech Stack:** Python 3, pytest, existing HSConfig CLI modules, existing JSON/report helpers, no new runtime dependency.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig`.
- Before implementation work, refresh and verify repo currency:
  - `git fetch --all --prune --tags`
  - `python scripts\check_hsconfig_currentness.py --cwd . --json`
- Keep the final worktree clean. Commit the implementation if requested by the execution mode or user workflow.
- Do not use HSTuner.
- Do not read or tune from runtime logs for this change.
- Do not add gameplay ordering logic, card-effect logic, HearthRanger action sequencing, or mulligan strategy changes.
- Do not create a new report file. The only new normal output is one field in the top-level configure output `<out>/configure_summary.json`.
- Do not write `config_quality` or `config_quality_summary` into `reports/operator_summary.json`.
- Do not make `SOURCE_BACKED_STRONG` an apply gate.
- Do not make config quality apply-blocking. It is diagnostic-only:
  - `authority == "diagnostic_only"`
  - `apply_blocking == false`
  - `runtime_write_performed == false`
- Do not reintroduce default-only success. Defaults may exist as a diagnostic finding, but they must be visible and must not masquerade as source-backed quality.
- Do not add dependencies.

---

## Subagent Breakdown

- **Worker A:** Add focused tests for the compact summary helper and configure-summary output.
- **Worker B:** Implement the helper and configure integration in `src/hsconfig/commands/configure.py`.
- **Worker C:** Update operator docs and the HSConfig skill text so operators know where to look and what remains authoritative.
- **Final Reviewer:** Run focused and regression verification, inspect the diff, and confirm the worktree state.

Only Worker B changes production Python. Worker C changes docs/skill text. Workers must not edit the same file concurrently.

---

## Task 1: Add Tests For Compact Config Quality Summary

**Files:**

- `tests/test_configure_cli.py`
- `src/hsconfig/commands/configure.py`

**Target Interface:**

```python
def _compact_config_quality_summary(report: Mapping[str, Any]) -> dict[str, Any]:
    ...
```

**Expected Summary Shape:**

```json
{
  "status": "clean",
  "authority": "diagnostic_only",
  "apply_blocking": false,
  "runtime_write_performed": false,
  "problem_count": 0,
  "problem_checks": []
}
```

When there are problems:

```json
{
  "status": "attention",
  "authority": "diagnostic_only",
  "apply_blocking": false,
  "runtime_write_performed": false,
  "problem_count": 3,
  "problem_checks": [
    "card_behavior_semantic_default_visible",
    "source_to_runtime_closure_rows_missing"
  ],
  "next_action": "run_contract_doctor_for_details"
}
```

**Steps:**

- [ ] In `tests/test_configure_cli.py`, import the helper from the configure command module:

```python
from hsconfig.commands.configure import _compact_config_quality_summary
```

- [ ] Add a clean-summary unit test:

```python
def test_compact_config_quality_summary_reports_clean_status() -> None:
    report = {
        "status": "clean",
        "authority": "diagnostic_only",
        "apply_blocking": False,
        "runtime_write_performed": False,
        "problems": [],
    }

    assert _compact_config_quality_summary(report) == {
        "status": "clean",
        "authority": "diagnostic_only",
        "apply_blocking": False,
        "runtime_write_performed": False,
        "problem_count": 0,
        "problem_checks": [],
    }
```

- [ ] Add an attention-summary unit test that deduplicates checks in first-seen order:

```python
def test_compact_config_quality_summary_reports_attention_checks() -> None:
    report = {
        "status": "attention",
        "authority": "diagnostic_only",
        "apply_blocking": False,
        "runtime_write_performed": False,
        "problems": [
            {"check": "card_behavior_semantic_default_visible", "value": ["CS2_235"]},
            {"check": "source_to_runtime_closure_rows_missing", "value": 1},
            {"check": "card_behavior_semantic_default_visible", "value": ["CS2_235"]},
        ],
    }

    assert _compact_config_quality_summary(report) == {
        "status": "attention",
        "authority": "diagnostic_only",
        "apply_blocking": False,
        "runtime_write_performed": False,
        "problem_count": 3,
        "problem_checks": [
            "card_behavior_semantic_default_visible",
            "source_to_runtime_closure_rows_missing",
        ],
        "next_action": "run_contract_doctor_for_details",
    }
```

- [ ] Run the focused tests and confirm they fail because the helper does not exist yet:

```powershell
python -m pytest tests\test_configure_cli.py::test_compact_config_quality_summary_reports_clean_status tests\test_configure_cli.py::test_compact_config_quality_summary_reports_attention_checks -q -p no:cacheprovider
```

**Expected initial failure:**

```text
ImportError: cannot import name '_compact_config_quality_summary'
```

---

## Task 2: Implement Compact Summary Helper

**Files:**

- `src/hsconfig/commands/configure.py`
- `tests/test_configure_cli.py`

**Steps:**

- [ ] In `src/hsconfig/commands/configure.py`, extend imports near the top:

```python
from collections.abc import Mapping
```

- [ ] Import the existing config-quality contract:

```python
from hsconfig.config_quality_contract import build_config_quality_report
```

- [ ] Add this helper near the other private configure helpers:

```python
def _compact_config_quality_summary(report: Mapping[str, Any]) -> dict[str, Any]:
    problems_raw = report.get("problems", [])
    problems = problems_raw if isinstance(problems_raw, list) else []

    problem_checks: list[str] = []
    for problem in problems:
        if not isinstance(problem, Mapping):
            continue
        check = str(problem.get("check", "")).strip()
        if check and check not in problem_checks:
            problem_checks.append(check)

    summary: dict[str, Any] = {
        "status": str(report.get("status") or "attention"),
        "authority": "diagnostic_only",
        "apply_blocking": False,
        "runtime_write_performed": False,
        "problem_count": len(problems),
        "problem_checks": problem_checks,
    }
    if problem_checks:
        summary["next_action"] = "run_contract_doctor_for_details"
    return summary
```

- [ ] Add a non-blocking wrapper so diagnostic failures are visible but never prevent a valid package from being generated:

```python
def _build_config_quality_summary(package_dir: Path) -> dict[str, Any]:
    try:
        return _compact_config_quality_summary(build_config_quality_report(package_dir))
    except Exception as exc:
        return {
            "status": "attention",
            "authority": "diagnostic_only",
            "apply_blocking": False,
            "runtime_write_performed": False,
            "problem_count": 1,
            "problem_checks": ["config_quality_summary_failed"],
            "next_action": "run_contract_doctor_for_details",
            "error": f"{type(exc).__name__}: {exc}",
        }
```

- [ ] Run the helper tests again:

```powershell
python -m pytest tests\test_configure_cli.py::test_compact_config_quality_summary_reports_clean_status tests\test_configure_cli.py::test_compact_config_quality_summary_reports_attention_checks -q -p no:cacheprovider
```

**Expected output:**

```text
2 passed
```

---

## Task 3: Add Configure-Summary Integration

**Files:**

- `src/hsconfig/commands/configure.py`
- `tests/test_configure_cli.py`

**Steps:**

- [ ] Add a configure CLI test that confirms `configure_summary.json` contains the compact diagnostic summary. Use an existing successful configure test fixture pattern from `tests/test_configure_cli.py`.

Core assertion:

```python
summary = json.loads((out_dir / "configure_summary.json").read_text(encoding="utf-8"))

assert summary["config_quality_summary"]["authority"] == "diagnostic_only"
assert summary["config_quality_summary"]["apply_blocking"] is False
assert summary["config_quality_summary"]["runtime_write_performed"] is False
assert summary["config_quality_summary"]["problem_count"] == 0
assert summary["config_quality_summary"]["problem_checks"] == []
```

- [ ] Add a regression test proving a config-quality diagnostic crash does not block configure:

```python
def test_configure_quality_summary_failure_stays_diagnostic_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_report(_package_dir: Path) -> dict[str, Any]:
        raise RuntimeError("quality unavailable")

    monkeypatch.setattr(
        "hsconfig.commands.configure.build_config_quality_report",
        raise_report,
    )
    out_dir = tmp_path / "out"

    result = runner.invoke(
        app,
        [
            "configure",
            "--deck-name",
            "ShadowPriest",
            "--deck-code",
            "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=",
            "--out",
            str(out_dir),
            "--source-mode",
            "skip",
        ],
    )

    assert result.exit_code == 0
    summary = json.loads(
        (out_dir / "configure_summary.json").read_text(encoding="utf-8")
    )
    assert summary["config_quality_summary"]["authority"] == "diagnostic_only"
    assert summary["config_quality_summary"]["apply_blocking"] is False
    assert summary["config_quality_summary"]["runtime_write_performed"] is False
    assert summary["config_quality_summary"]["problem_checks"] == ["config_quality_summary_failed"]
```

- [ ] If `tests/test_configure_cli.py` uses a different CLI runner variable name, follow the existing local name exactly.

- [ ] Run the new configure-summary tests and confirm they fail before integration because `config_quality_summary` is absent:

```powershell
python -m pytest tests\test_configure_cli.py -q -p no:cacheprovider
```

- [ ] In `src/hsconfig/commands/configure.py`, compute the summary after `operator_summary.json` has been written and after generated file accounting is refreshed:

```python
config_quality_summary = _build_config_quality_summary(package_dir)
```

- [ ] Add this field to the `configure_summary` payload written to the top-level configure output `out_dir / "configure_summary.json"`:

```python
"config_quality_summary": config_quality_summary,
```

- [ ] Do not add this field to `operator_summary`.

- [ ] Run the configure CLI tests again:

```powershell
python -m pytest tests\test_configure_cli.py -q -p no:cacheprovider
```

**Expected output:**

```text
passed
```

---

## Task 4: Update Operator Docs And Skill Text

**Files:**

- `docs/operator/README.md`
- `.agents/skills/hsconfig/SKILL.md`
- `C:\Users\darbo\.codex\skills\hsconfig\SKILL.md` via the existing sync script

**Steps:**

- [ ] In `docs/operator/README.md`, update the contract-doctor/operator-summary section to state:

```markdown
`<out>/configure_summary.json` also contains `config_quality_summary`, a compact diagnostic-only mirror of the existing config-quality contract. It is for quick operator visibility after `hsconfig configure`. If `status` is `attention`, run `hsconfig contract-doctor --package <package>` for details. The normal apply authority remains `reports/operator_summary.json`.
```

- [ ] In `.agents/skills/hsconfig/SKILL.md`, add one compact bullet near the existing contract-doctor guidance:

```markdown
- After `configure`, read `<out>/configure_summary.json.config_quality_summary` for quick diagnostic quality status. It is diagnostic-only and non-blocking; use `contract-doctor` for details. `reports/operator_summary.json` remains the normal apply authority.
```

- [ ] Run the existing skill sync command so the installed skill stays current:

```powershell
python scripts\sync_installed_skill.py
```

- [ ] Run the skill sync check:

```powershell
python scripts\sync_installed_skill.py --check
```

**Expected output:**

```text
installed skill is in sync
```

- [ ] If an existing docs/skill test asserts wording around contract-doctor, extend it to cover `configure_summary.json.config_quality_summary` as diagnostic-only and `operator_summary.json` as the apply authority.

---

## Task 5: Regression Verification

**Files:**

- No production edits in this task.

**Steps:**

- [ ] Run focused quality/configure coverage:

```powershell
python -m pytest tests\test_configure_cli.py tests\test_contract_doctor.py tests\test_config_quality_contract.py -q -p no:cacheprovider
```

**Expected output:**

```text
passed
```

- [ ] Run the source/contract regression set that protects the no-default-only and Wild no-block boundaries:

```powershell
python -m pytest tests\test_configure_auto_source.py tests\test_configure_online_source.py tests\test_shadowpriest_e2e.py tests\test_universal_wild_no_block_matrix.py -q -p no:cacheprovider
```

**Expected output:**

```text
passed
```

- [ ] Run guardrails:

```powershell
python scripts\check_contract_guardrails.py
```

**Expected output:**

```text
OK
```

- [ ] Re-run currentness check:

```powershell
python scripts\check_hsconfig_currentness.py --cwd . --json
```

**Expected required fields:**

```json
{
  "behind_origin_main": 0,
  "dirty": false
}
```

If the implementation is not committed yet, `dirty` will be `true`; commit or intentionally leave it only if the user requested an uncommitted plan.

---

## Task 6: Final Diff Review And Commit

**Files:**

- `src/hsconfig/commands/configure.py`
- `tests/test_configure_cli.py`
- `docs/operator/README.md`
- `.agents/skills/hsconfig/SKILL.md`
- `C:\Users\darbo\.codex\skills\hsconfig\SKILL.md`

**Steps:**

- [ ] Inspect the exact diff:

```powershell
git diff -- src\hsconfig\commands\configure.py tests\test_configure_cli.py docs\operator\README.md .agents\skills\hsconfig\SKILL.md
```

- [ ] Confirm no runtime JSON templates, generated CustomConfigs, log files, backup files, or HSTuner artifacts are modified.

- [ ] Confirm `operator_summary.json` logic is unchanged except for any unrelated pre-existing diff. Expected result for this task: no edit to operator-summary generation semantics.

- [ ] Confirm there is no `SOURCE_BACKED_STRONG` gating change:

```powershell
git diff -- src\hsconfig\commands\configure.py | Select-String -Pattern "SOURCE_BACKED_STRONG|apply_blocking|operator_summary"
```

- [ ] Confirm repo worktree contents:

```powershell
git status --short
```

- [ ] Stage only intended repo files:

```powershell
git add src\hsconfig\commands\configure.py tests\test_configure_cli.py docs\operator\README.md .agents\skills\hsconfig\SKILL.md
```

- [ ] Commit:

```powershell
git commit -m "feat: summarize config quality in configure output"
```

- [ ] Push current branch:

```powershell
git push
```

- [ ] Confirm clean worktree:

```powershell
git status --short --branch
```

**Expected final status:**

```text
## codex/hsconfig-semantic-intent-scoring...origin/codex/hsconfig-semantic-intent-scoring
```

No additional tracked or untracked files should appear.

---

## Acceptance Criteria

- `hsconfig configure` writes `<out>/configure_summary.json.config_quality_summary`.
- The new summary is compact and deterministic:
  - `status`
  - `authority`
  - `apply_blocking`
  - `runtime_write_performed`
  - `problem_count`
  - `problem_checks`
  - `next_action` only when problems exist
- `config_quality_summary` is diagnostic-only and cannot block package generation.
- `operator_summary.json` remains the normal apply authority and is not expanded with config quality.
- No gameplay, mulligan, runtime-write, HSTuner, or log-analysis behavior changes are introduced.
- Existing contract-doctor detail reporting remains the detailed diagnostic path.
- Tests cover clean summary, attention summary, configure-summary output, and diagnostic failure non-blocking behavior.
- Source/contract guardrails and ShadowPriest/Wild no-block regression tests pass.
- Repo is current and the final worktree is clean.

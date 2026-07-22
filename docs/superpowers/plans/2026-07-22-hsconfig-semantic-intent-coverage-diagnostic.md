# HSConfig Semantic Intent Coverage Diagnostic Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` to implement this plan task-by-task. Keep each task independently reviewable and update the checkboxes as work completes.

**Goal:** Add a small diagnostic-only semantic-intent coverage rollup to HSConfig so the operator can see whether meaningful per-card runtime intent is traced, semantically scored, not default-only, and not leaking report-only mechanics into runtime. This must improve visibility only; it must never block CustomConfig creation or runtime apply.

**Architecture:** Extend the existing `config_quality_contract` report with one derived `semantic_intent_coverage` check that rolls up already-computed facts from card behavior, trace completeness, mechanic runtime discipline, and optional semantic enrichment. Mirror the check into the compact configure summary and contract-doctor Markdown. Do not add a new command, new runtime surface, new apply gate, or new data source dependency.

**Tech Stack:** Python standard library only, existing `pytest` suite, existing `hsconfig configure`, existing `hsconfig contract-doctor`, existing currentness script.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig`.
- Start with:
  - `git fetch --all --prune --tags`
  - `git status --short --branch`
  - `python scripts\check_hsconfig_currentness.py --cwd . --json`
- End with a clean worktree. No backups, no temporary artifacts, no generated caches committed.
- Keep all changes committed and pushed to the current feature branch when verification passes.
- `reports/operator_summary.json` remains the only normal runtime apply authority.
- `SOURCE_BACKED_STRONG` remains an evidence-quality label, not an apply gate.
- `source_status_apply_blocking` must remain `false`.
- `config_quality_contract`, `contract-doctor`, and the new semantic-intent rollup remain diagnostic-only:
  - `authority = "diagnostic_only"`
  - `apply_blocking = False`
  - `runtime_write_performed = False`
- Do not add new runtime files or new runtime JSON keys.
- Do not add legacy runtime surfaces such as `CardBehavior.json`, `Concede.json`, or `Presume.json`.
- Do not introduce HSTuner, replay parsing, winrate logic, or post-game tuning.
- Do not fetch or write new `research-deep` outputs as part of this implementation.
- Keep the implementation narrow: reuse existing report facts instead of creating a second semantic truth system.

---

## File Structure

- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\config_quality_contract.py`
  - Read optional `reports/semantic_enrichment_report.json`.
  - Add `_semantic_intent_coverage_check(...)`.
  - Add small helper functions for list/mapping normalization and warning-only semantic summary.
  - Add the new check into `checks["semantic_intent_coverage"]`.
  - Do not add new independent problem checks unless an existing problem check is already emitted by another check.
- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\commands\configure.py`
  - Add semantic-intent status and first-attention fields to `_compact_config_quality_summary()` when the check is present.
- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\contract_doctor.py`
  - Render semantic-intent status and first attention in the existing Config Quality section.
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_config_quality_contract.py`
  - Add/extend focused tests for clean coverage and attention rollups.
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_configure_cli.py`
  - Add focused compact-summary test for semantic-intent fields.
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_contract_doctor.py`
  - Extend Markdown rendering test for semantic-intent lines.
- Modify: `C:\Users\darbo\Documents\HSConfig\docs\operator\README.md`
  - Add one concise operator note explaining the rollup.
- Optional only if an existing sync/drift test requires it: `C:\Users\darbo\Documents\HSConfig\.agents\skills\hsconfig\SKILL.md`
  - Mirror one concise note that semantic-intent coverage is diagnostic-only and not an apply gate.

---

## Task 0: Preflight Currentness And Clean Base

**Files:** none.

- [ ] **Step 0.1: Fetch and verify the branch**

Run:

```powershell
git fetch --all --prune --tags
git status --short --branch
python scripts\check_hsconfig_currentness.py --cwd . --json
```

Expected:

```text
## codex/hsconfig-semantic-intent-scoring...origin/codex/hsconfig-semantic-intent-scoring
```

The currentness JSON must include:

```json
{
  "behind_origin_main": 0,
  "dirty": false,
  "clean_for_runtime_work": true
}
```

If the branch is behind `origin/main`, update it before coding. If the worktree is dirty, inspect the diff and preserve unrelated user work; do not overwrite unknown changes.

---

## Task 1: Failing Tests For Semantic Intent Coverage

**Files:**
- `C:\Users\darbo\Documents\HSConfig\tests\test_config_quality_contract.py`

**Intent:** Define the new report contract before implementation. The new check is a visibility rollup, not a new gate.

- [ ] **Step 1.1: Extend the clean package test**

In `test_config_quality_report_is_clean_for_source_backed_runtime_lean_package`, add this assertion after the existing `trace_completeness` assertion:

```python
    assert report["checks"]["semantic_intent_coverage"] == {
        "authority": "diagnostic_only",
        "apply_blocking": False,
        "runtime_write_performed": False,
        "status": "clean",
        "meaningful_cardid_runtime_rows": 1,
        "runtime_rows_missing_trace": [],
        "semantic_score_missing_rows": [],
        "semantic_default_rows": [],
        "report_only_runtime_rows": [],
        "warning_only_card_count": 0,
        "warning_only_mechanics": [],
        "attention": [],
        "first_attention": None,
    }
```

- [ ] **Step 1.2: Extend the missing-trace test**

In `test_config_quality_flags_cardid_runtime_rows_without_source_trace`, add:

```python
    semantic_intent = report["checks"]["semantic_intent_coverage"]

    assert semantic_intent["status"] == "attention"
    assert semantic_intent["authority"] == "diagnostic_only"
    assert semantic_intent["apply_blocking"] is False
    assert semantic_intent["runtime_write_performed"] is False
    assert semantic_intent["first_attention"] == "card_behavior_runtime_row_missing_trace"
    assert {
        "check": "card_behavior_runtime_row_missing_trace",
        "count": 1,
    } in semantic_intent["attention"]
```

- [ ] **Step 1.3: Extend the semantic-default test**

In `test_config_quality_flags_semantic_default_rows`, add:

```python
    semantic_intent = report["checks"]["semantic_intent_coverage"]

    assert semantic_intent["status"] == "attention"
    assert {
        "check": "card_behavior_semantic_default_visible",
        "count": 1,
    } in semantic_intent["attention"]
    assert semantic_intent["semantic_default_rows"] == [
        {
            "card_id": "CARD_DEFAULT",
            "behavior_block": "BeforePlayCardBonus",
            "value": "6",
            "reason": "semantic_default",
        }
    ]
```

- [ ] **Step 1.4: Extend the report-only mechanic test**

In `test_config_quality_flags_report_only_mechanic_runtime_emission`, add:

```python
    semantic_intent = report["checks"]["semantic_intent_coverage"]

    assert semantic_intent["status"] == "attention"
    assert {
        "check": "report_only_mechanic_emitted_runtime",
        "count": 1,
    } in semantic_intent["attention"]
    assert semantic_intent["report_only_runtime_rows"] == [
        {
            "card_id": "TRADEABLE_001",
            "mechanic": "tradeable",
            "behavior_block": "BeforePlayCardBonus",
            "value": "6",
        }
    ]
```

- [ ] **Step 1.5: Add optional semantic-enrichment warning-only visibility test**

Append this test near the other config-quality tests:

```python
def test_config_quality_semantic_intent_coverage_counts_warning_only_semantics(
    tmp_path: Path,
):
    package = minimal_clean_package(tmp_path)
    write_json(
        package / "reports" / "semantic_enrichment_report.json",
        {
            "cards": {
                "BAR_880": {
                    "card_id": "BAR_880",
                    "name": "Tradeable Test Card",
                    "warning_only_mechanics": ["tradeable"],
                },
                "LOC_001": {
                    "card_id": "LOC_001",
                    "name": "Location Test Card",
                    "warning_only_mechanics": ["location_activation"],
                },
            }
        },
    )

    report = build_config_quality_report(package)

    assert report["status"] == "clean"
    assert report["checks"]["semantic_intent_coverage"]["warning_only_card_count"] == 2
    assert report["checks"]["semantic_intent_coverage"]["warning_only_mechanics"] == [
        "location_activation",
        "tradeable",
    ]
    assert report["checks"]["semantic_intent_coverage"]["attention"] == []
```

- [ ] **Step 1.6: Run the failing tests**

Run:

```powershell
python -m pytest tests\test_config_quality_contract.py -q
```

Expected before implementation:

```text
FAILED tests/test_config_quality_contract.py::test_config_quality_report_is_clean_for_source_backed_runtime_lean_package
```

The failure should be a missing `semantic_intent_coverage` key or equivalent.

---

## Task 2: Implement Semantic Intent Coverage In Config Quality

**Files:**
- `C:\Users\darbo\Documents\HSConfig\src\hsconfig\config_quality_contract.py`

**Intent:** Add one derived report check. The check must only summarize existing diagnostic facts and optional warning-only semantic metadata.

- [ ] **Step 2.1: Read optional semantic enrichment report**

In `build_config_quality_report`, after `deck_identity` is read, add:

```python
    semantic_enrichment = _read_json(
        package / "reports" / "semantic_enrichment_report.json"
    )
    if not isinstance(semantic_enrichment, Mapping):
        semantic_enrichment = {}
```

- [ ] **Step 2.2: Wire the check after existing base checks**

Replace the current single `checks = { ... }` assignment with a base-check pattern:

```python
    checks = {
        "operator_summary": _operator_summary_check(operator),
        "card_behavior": _card_behavior_check(card_behavior),
        "source_to_runtime_explainability": _explainability_check(explainability),
        "trace_completeness": _trace_completeness_check(card_behavior, explainability),
        "closure_freshness": _closure_freshness_check(operator),
        "mechanic_runtime_discipline": _mechanic_runtime_discipline_check(
            card_behavior
        ),
        "runtime_json": _runtime_json_check(
            package,
            deck_identity,
            card_behavior,
            explainability,
        ),
        "legacy_surfaces": _legacy_surface_check(package),
        "darkbishop_boundary": _darkbishop_boundary_check(package),
    }
    checks["semantic_intent_coverage"] = _semantic_intent_coverage_check(
        card_behavior_check=checks["card_behavior"],
        trace_check=checks["trace_completeness"],
        mechanic_check=checks["mechanic_runtime_discipline"],
        semantic_enrichment=semantic_enrichment,
    )
```

Do not change `_problems(checks)` except if a test demonstrates an actual missing existing problem. The rollup must not duplicate problem entries.

- [ ] **Step 2.3: Add the helper functions**

Insert these helpers after `_mechanic_runtime_discipline_check` and before `_runtime_json_check`:

```python
def _semantic_intent_coverage_check(
    *,
    card_behavior_check: Mapping[str, Any],
    trace_check: Mapping[str, Any],
    mechanic_check: Mapping[str, Any],
    semantic_enrichment: Mapping[str, Any],
) -> dict[str, Any]:
    runtime_rows_missing_trace = _list_of_mappings(
        trace_check.get("runtime_rows_missing_trace")
    )
    semantic_score_missing_rows = _list_of_mappings(
        card_behavior_check.get("semantic_score_missing_rows")
    )
    semantic_default_rows = _list_of_mappings(
        card_behavior_check.get("semantic_default_rows")
    )
    report_only_runtime_rows = _list_of_mappings(
        mechanic_check.get("report_only_runtime_rows")
    )
    warning_only = _semantic_warning_only_summary(semantic_enrichment)

    attention: list[dict[str, Any]] = []
    if runtime_rows_missing_trace:
        attention.append(
            {
                "check": "card_behavior_runtime_row_missing_trace",
                "count": len(runtime_rows_missing_trace),
            }
        )
    if semantic_score_missing_rows:
        attention.append(
            {
                "check": "card_behavior_semantic_score_missing",
                "count": len(semantic_score_missing_rows),
            }
        )
    if semantic_default_rows:
        attention.append(
            {
                "check": "card_behavior_semantic_default_visible",
                "count": len(semantic_default_rows),
            }
        )
    if report_only_runtime_rows:
        attention.append(
            {
                "check": "report_only_mechanic_emitted_runtime",
                "count": len(report_only_runtime_rows),
            }
        )

    return {
        "authority": "diagnostic_only",
        "apply_blocking": False,
        "runtime_write_performed": False,
        "status": "clean" if not attention else "attention",
        "meaningful_cardid_runtime_rows": _int_value(
            card_behavior_check.get("accepted_cardid_runtime_rows", 0)
        ),
        "runtime_rows_missing_trace": runtime_rows_missing_trace,
        "semantic_score_missing_rows": semantic_score_missing_rows,
        "semantic_default_rows": semantic_default_rows,
        "report_only_runtime_rows": report_only_runtime_rows,
        "warning_only_card_count": warning_only["card_count"],
        "warning_only_mechanics": warning_only["mechanics"],
        "attention": attention,
        "first_attention": attention[0]["check"] if attention else None,
    }


def _semantic_warning_only_summary(
    semantic_enrichment: Mapping[str, Any],
) -> dict[str, Any]:
    cards = semantic_enrichment.get("cards", {})
    if isinstance(cards, Mapping):
        rows = list(cards.values())
    elif isinstance(cards, list):
        rows = cards
    else:
        rows = []

    card_count = 0
    mechanics: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        row_mechanics = _string_list(row.get("warning_only_mechanics"))
        row_mechanics.extend(_string_list(row.get("warning_only")))
        normalized = sorted({mechanic.strip() for mechanic in row_mechanics if mechanic.strip()})
        if not normalized:
            continue
        card_count += 1
        mechanics.update(normalized)

    return {
        "card_count": card_count,
        "mechanics": sorted(mechanics),
    }


def _list_of_mappings(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]
```

If the line with `normalized = ...` exceeds the formatter expectation, format it as:

```python
        normalized = sorted(
            {mechanic.strip() for mechanic in row_mechanics if mechanic.strip()}
        )
```

- [ ] **Step 2.4: Run focused tests**

Run:

```powershell
python -m pytest tests\test_config_quality_contract.py -q
```

Expected:

```text
... passed
```

If another existing test fails because it compares the complete `checks` dictionary, update that assertion to include `semantic_intent_coverage` rather than loosening the assertion.

---

## Task 3: Surface The Rollup To Operators

### Task 3A: Compact Configure Summary

**Files:**
- `C:\Users\darbo\Documents\HSConfig\src\hsconfig\commands\configure.py`
- `C:\Users\darbo\Documents\HSConfig\tests\test_configure_cli.py`

- [ ] **Step 3.1: Add a compact-summary test**

Append this test near the existing `_compact_config_quality_summary` tests:

```python
def test_compact_config_quality_summary_includes_semantic_intent_when_present() -> None:
    report = {
        "status": "attention",
        "authority": "diagnostic_only",
        "apply_blocking": False,
        "runtime_write_performed": False,
        "problems": [],
        "checks": {
            "semantic_intent_coverage": {
                "status": "attention",
                "first_attention": "card_behavior_runtime_row_missing_trace",
            }
        },
    }

    assert _compact_config_quality_summary(report) == {
        "status": "attention",
        "authority": "diagnostic_only",
        "apply_blocking": False,
        "runtime_write_performed": False,
        "problem_count": 0,
        "problem_checks": [],
        "semantic_intent_status": "attention",
        "semantic_intent_first_attention": "card_behavior_runtime_row_missing_trace",
    }
```

- [ ] **Step 3.2: Implement compact summary fields**

In `_compact_config_quality_summary`, after the base `summary` dict is created and before `if problem_checks`, add:

```python
    checks = report.get("checks", {})
    if isinstance(checks, Mapping):
        semantic_intent = checks.get("semantic_intent_coverage")
        if isinstance(semantic_intent, Mapping):
            summary["semantic_intent_status"] = str(
                semantic_intent.get("status") or ""
            )
            first_attention = semantic_intent.get("first_attention")
            if first_attention is not None:
                summary["semantic_intent_first_attention"] = str(first_attention)
```

Do not alter the fallback exception summary. If config quality generation fails, the summary should still report only `config_quality_summary_failed`.

- [ ] **Step 3.3: Run configure summary tests**

Run:

```powershell
python -m pytest tests\test_configure_cli.py -q
```

Expected:

```text
... passed
```

### Task 3B: Contract Doctor Markdown

**Files:**
- `C:\Users\darbo\Documents\HSConfig\src\hsconfig\contract_doctor.py`
- `C:\Users\darbo\Documents\HSConfig\tests\test_contract_doctor.py`

- [ ] **Step 3.4: Extend the Markdown rendering test**

In `test_contract_doctor_markdown_includes_config_quality_section`, add this check payload beside the existing `mechanic_runtime_discipline` check:

```python
                "semantic_intent_coverage": {
                    "status": "attention",
                    "first_attention": "card_behavior_runtime_row_missing_trace",
                },
```

Then add these assertions after the existing Config Quality line assertions:

```python
    assert "- Semantic intent status: attention" in lines
    assert (
        "- Semantic intent first attention: card_behavior_runtime_row_missing_trace"
        in lines
    )
```

- [ ] **Step 3.5: Render the semantic-intent lines**

In `render_contract_doctor_markdown`, after `mechanic_quality` is assigned, add:

```python
    semantic_intent_quality = _mapping(
        config_quality_checks.get("semantic_intent_coverage")
    )
```

In the `## Config Quality` block, after the report-only mechanic runtime row line, add:

```python
        f"- Semantic intent status: {semantic_intent_quality.get('status', 'unknown')}",
        f"- Semantic intent first attention: {semantic_intent_quality.get('first_attention') or 'none'}",
```

If formatting wraps the second line, keep the rendered string exactly:

```text
- Semantic intent first attention: <value-or-none>
```

- [ ] **Step 3.6: Run contract-doctor tests**

Run:

```powershell
python -m pytest tests\test_contract_doctor.py -q
```

Expected:

```text
... passed
```

---

## Task 4: Operator Documentation

**Files:**
- `C:\Users\darbo\Documents\HSConfig\docs\operator\README.md`
- Optional sync target if required: `C:\Users\darbo\Documents\HSConfig\.agents\skills\hsconfig\SKILL.md`

- [ ] **Step 4.1: Update operator docs**

Add one short note to the section that explains config quality or contract doctor. Use this exact wording unless surrounding text needs minor grammar adjustment:

```markdown
`config_quality.checks.semantic_intent_coverage` is a diagnostic-only rollup: it shows traced per-card intent, missing semantic scores, semantic-default rows, report-only mechanic runtime leaks, and warning-only mechanics, but it does not change `reports/operator_summary.json` apply authority.
```

- [ ] **Step 4.2: Run docs/sync checks**

Run the focused doc tests that exist in this repo:

```powershell
python -m pytest tests\test_docs_active_path.py tests\test_skill_sync.py -q
```

Expected:

```text
... passed
```

If `tests\test_skill_sync.py` reports that `.agents\skills\hsconfig\SKILL.md` must mirror the doc note, add the same concise diagnostic-only sentence there and rerun the same command.

---

## Task 5: Full Verification

**Files:** all changed files.

- [ ] **Step 5.1: Run focused regression suite**

Run:

```powershell
python -m pytest `
  tests\test_config_quality_contract.py `
  tests\test_configure_cli.py `
  tests\test_contract_doctor.py `
  tests\test_docs_active_path.py `
  tests\test_skill_sync.py `
  -q
```

Expected:

```text
... passed
```

- [ ] **Step 5.2: Run currentness and guardrails**

Run:

```powershell
python scripts\check_hsconfig_currentness.py --cwd . --json
python -m pytest tests\test_no_default_only_runtime_surfaces.py tests\test_source_contract_conformance.py -q
```

Expected currentness fields:

```json
{
  "dirty": true,
  "behind_origin_main": 0
}
```

`dirty` may be `true` at this step because the implementation is not committed yet. It must be `false` after commit/push.

Expected tests:

```text
... passed
```

- [ ] **Step 5.3: Run full tests**

Run:

```powershell
python -m pytest -q
```

Expected:

```text
... passed
```

If the full suite is too slow but focused tests pass, do not claim full verification. Report exactly which tests ran.

- [ ] **Step 5.4: Review diff**

Run:

```powershell
git diff -- src\hsconfig\config_quality_contract.py src\hsconfig\commands\configure.py src\hsconfig\contract_doctor.py tests\test_config_quality_contract.py tests\test_configure_cli.py tests\test_contract_doctor.py docs\operator\README.md .agents\skills\hsconfig\SKILL.md
git status --short --branch
```

Check:

- No runtime JSON files are changed.
- No generated package files are changed.
- No `reports/`, `Power.log`, `.hsreplay`, `.hdtreplay`, cache, or backup artifacts are staged.
- No apply authority changes were introduced.
- No duplicate problem entries were introduced solely by `semantic_intent_coverage`.

- [ ] **Step 5.5: Commit and push**

Run:

```powershell
git add src\hsconfig\config_quality_contract.py src\hsconfig\commands\configure.py src\hsconfig\contract_doctor.py tests\test_config_quality_contract.py tests\test_configure_cli.py tests\test_contract_doctor.py docs\operator\README.md
git add .agents\skills\hsconfig\SKILL.md
git diff --cached --stat
git commit -m "Add semantic intent coverage diagnostic"
git push
git status --short --branch
python scripts\check_hsconfig_currentness.py --cwd . --json
```

If `.agents\skills\hsconfig\SKILL.md` was not changed, `git add` for that path may print no change; that is fine.

Expected final status:

```text
## codex/hsconfig-semantic-intent-scoring...origin/codex/hsconfig-semantic-intent-scoring
```

No files should appear below the branch line.

Expected currentness fields:

```json
{
  "behind_origin_main": 0,
  "dirty": false,
  "clean_for_runtime_work": true
}
```

---

## Self-Review Checklist

- [ ] The new check is named exactly `semantic_intent_coverage`.
- [ ] The new check includes `authority`, `apply_blocking`, and `runtime_write_performed`.
- [ ] The new check is diagnostic-only and does not affect `runtime_apply_allowed`.
- [ ] The new check does not create new runtime surfaces.
- [ ] The new check does not duplicate problem entries already emitted by existing checks.
- [ ] Missing trace, missing semantic score, semantic default, and report-only mechanic runtime leaks are visible from one place.
- [ ] Warning-only mechanics from `semantic_enrichment_report.json` are visible when present.
- [ ] Contract Doctor shows the rollup in Markdown.
- [ ] Configure summary mirrors the rollup only when present.
- [ ] All touched tests pass.
- [ ] Worktree is clean after commit and push.

---

## Execution Handoff

Implement this plan with `superpowers:subagent-driven-development`.

Recommended subagent split:

- Worker A: `config_quality_contract.py` plus `tests/test_config_quality_contract.py`.
- Worker B: `configure.py`, `contract_doctor.py`, and their tests.
- Worker C: docs and final diff review.

Only one worker may write each file area. Main agent owns final consolidation, verification, commit, push, and clean-worktree proof.

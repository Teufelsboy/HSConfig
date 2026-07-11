# HSConfig Narrow Polish And Real-Deck Usage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep HSConfig lean and ready for real deck usage by tightening wording, preserving current audit evidence, and adding compact guard tests without widening the runtime surface.

**Architecture:** HSConfig remains a pre-run CustomConfig generator. The normal path stays `hsconfig configure`, the single gate stays `reports/operator_summary.json`, and runtime writes stay behind the existing guarded apply path. This plan only changes documentation, CLI wording, and regression tests; it does not add new post-run tuning, replay parsing, winrate analysis, or normal-path `Presume.json` / `Concede.json` output.

**Tech Stack:** Python 3, pytest, argparse, local HSConfig CLI, repository skill files under `.agents/skills/hsconfig`, installed skill sync via `scripts/sync_installed_skill.py`.

## Global Constraints

- Work only in `C:\Users\darbo\Documents\HSConfig`.
- Do not widen HSConfig into HSTuner behavior: no replay parsing, no winrate inspection, no runtime-log tuning, no candidate promotion.
- Preferred normal path is `hsconfig configure`.
- Lower-level stage commands are inspected or advanced stages, not the default operator path.
- Normal runtime surfaces remain `GlobalValues.json`, `Mulligan.json`, per-card `<CARDID>.json`, and `Combo.json` when supported.
- Normal HSConfig must not emit `Presume.json` or `Concede.json`; their absence must not block a valid load-safe package.
- Valid packages with semantic/source warnings must remain allowed through `runtime_apply_mode=load_safe_apply`.
- Hard blocks remain only technical load-safety failures: invalid JSON, unsafe runtime path, missing required files, stale or mismatched generated files, optional legacy surfaces in the normal path, nested runtime files, missing manifest, or invalid operator summary.
- Do not add new dependencies for this wave.
- Keep documentation short in the normal path; move detail behind clearly named evidence or advanced sections only when needed.

---

## File Structure

- Modify: `README.md`
  - Clarify runtime-write wording: `hsconfig apply` or `hsconfig configure --apply`.
  - Keep root README short and operator-directed.
- Modify: `docs/operator/README.md`
  - Keep Quick Start and Preferred Normal Path.
  - Avoid calling lower-level stages a second normal path.
  - Keep warning-only mechanic language non-blocking.
- Modify: `src/hsconfig/cli_parser.py`
  - Change root help and lower-level subcommand help from "normal path" wording to "inspected" or "advanced" wording.
- Modify: `.agents/skills/hsconfig/SKILL.md`
  - Mirror the clarified normal path and guarded runtime write wording.
- Modify: `.agents/skills/hsconfig/references/workflow.md`
  - Mirror the same normal path and lower-level inspected wording.
- Modify: `docs/research/current-truth.md`
  - Add the 2026-07-11 live skill audit as current evidence.
  - Mark any stale Presume/Concede citation narrative as superseded by active operator docs and the runtime-surface audit.
- Create: `docs/research/2026-07-11-hsconfig-live-skill-audit/README.md`
  - Mark the package as research evidence, not operator instructions or runtime input.
- Modify: `tests/test_cli_help.py`
  - Assert preferred path and inspected lower-level wording.
- Modify: `tests/test_docs_active_path.py`
  - Assert root/operator docs use the same runtime-write wording and avoid lower-level "normal path" drift.
- Modify: `tests/test_skill_files.py`
  - Assert skill and workflow references stay compact and use the clarified wording.
- Modify: `tests/test_property_no_block_apply_gate.py`
  - Add compact deterministic matrix rows for clean, warning, and technical-hard-block gate cases.
- Modify: `tests/test_mechanic_support.py`
  - Add one mixed-mechanic visibility regression that proves the no-widening boundary for identity-gated, partial, and warning-only mechanics.

---

### Task 1: Preserve Current Audit Evidence Without Turning It Into Operator Guidance

**Files:**
- Create: `docs/research/2026-07-11-hsconfig-live-skill-audit/README.md`
- Modify: `docs/research/current-truth.md`
- Test: `tests/test_docs_active_path.py`

**Interfaces:**
- Consumes: existing audit JSON files in `docs/research/2026-07-11-hsconfig-live-skill-audit/results/*.json`.
- Produces: a current-truth entry that later documentation tests can assert.

- [ ] **Step 1: Write the failing docs test**

Add this test to `tests/test_docs_active_path.py`:

```python
def test_current_truth_names_live_skill_audit_without_operator_drift():
    current_truth = Path("docs/research/current-truth.md").read_text(encoding="utf-8")
    audit_readme = Path(
        "docs/research/2026-07-11-hsconfig-live-skill-audit/README.md"
    ).read_text(encoding="utf-8")

    assert "2026-07-11-hsconfig-live-skill-audit" in current_truth
    assert "Live skill audit evidence" in current_truth
    assert "Research evidence only" in audit_readme
    assert "not operator instructions" in audit_readme
    assert "not runtime input" in audit_readme
    assert "Presume/Concede stale citation notes are superseded" in current_truth
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```powershell
python -m pytest tests\test_docs_active_path.py::test_current_truth_names_live_skill_audit_without_operator_drift -q
```

Expected before implementation:

```text
FAILED
```

- [ ] **Step 3: Create the audit README**

Create `docs/research/2026-07-11-hsconfig-live-skill-audit/README.md` with exactly this content:

```markdown
# HSConfig Live Skill Audit, 2026-07-11

Research evidence only.

This package records the live HSConfig skill audit used to decide the narrow
polish path after the no-block and runtime-surface hardening work.

It is not operator instructions, not runtime input, and not a replacement for
`docs/operator/README.md`.

Use the JSON files in `results/` to inspect why the current recommendation is
"narrow polish plus real-deck usage" instead of another broad implementation
wave.
```

- [ ] **Step 4: Add the current-truth entry**

Append this bullet to the active evidence section of `docs/research/current-truth.md`:

```markdown
- `2026-07-11-hsconfig-live-skill-audit`: Live skill audit evidence. Confirms HSConfig is ready for real-deck usage with narrow polish only: normal runtime surface unchanged, `hsconfig configure` preferred, warning-only mechanics remain non-blocking, and Presume/Concede stale citation notes are superseded by the active operator docs and runtime-surface audit.
```

If `docs/research/current-truth.md` has a dated ordering convention, place the bullet with the other 2026-07-11 entries while preserving existing text.

- [ ] **Step 5: Run the docs test**

Run:

```powershell
python -m pytest tests\test_docs_active_path.py::test_current_truth_names_live_skill_audit_without_operator_drift -q
```

Expected:

```text
1 passed
```

- [ ] **Step 6: Commit**

Run:

```powershell
git add docs\research\2026-07-11-hsconfig-live-skill-audit\README.md docs\research\current-truth.md tests\test_docs_active_path.py
git commit -m "docs: index live hsconfig skill audit"
```

---

### Task 2: Clarify Normal Path And Runtime-Write Wording

**Files:**
- Modify: `README.md`
- Modify: `docs/operator/README.md`
- Modify: `.agents/skills/hsconfig/SKILL.md`
- Modify: `.agents/skills/hsconfig/references/workflow.md`
- Test: `tests/test_docs_active_path.py`
- Test: `tests/test_skill_files.py`

**Interfaces:**
- Consumes: existing operator wording and skill sync script.
- Produces: one consistent operator statement: `hsconfig configure` is preferred, lower-level commands are inspected stages, runtime writes happen through `hsconfig apply` or `hsconfig configure --apply`.

- [ ] **Step 1: Write failing docs assertions**

Update `tests/test_docs_active_path.py` by changing `test_preferred_path_docs_use_single_lower_level_chain_label` to require inspected wording:

```python
def test_preferred_path_docs_use_single_lower_level_chain_label():
    exact_chain = (
        "source-manifest -> draft-source-documents -> research-deck -> "
        "prepare -> validate -> apply"
    )
    root_readme = Path("README.md").read_text(encoding="utf-8")
    operator_readme = Path("docs/operator/README.md").read_text(encoding="utf-8")

    assert root_readme.count(exact_chain) == 1
    assert operator_readme.count(exact_chain) == 1
    assert "Lower-level inspected path:" in root_readme
    assert "## Lower-Level Inspected Path" in operator_readme
    assert "Lower-level normal path:" not in root_readme
    assert "Lower-level normal path:" not in operator_readme
    assert "The lower-level normal path remains available for inspected work:" not in root_readme
    assert (
        "The lower-level normal path remains available for inspected work:"
        not in operator_readme
    )
```

Add this test to `tests/test_docs_active_path.py`:

```python
def test_runtime_write_wording_names_apply_and_configure_apply():
    root_readme = Path("README.md").read_text(encoding="utf-8")
    operator_readme = Path("docs/operator/README.md").read_text(encoding="utf-8")

    expected = "Runtime writes happen only through `hsconfig apply` or `hsconfig configure --apply`."
    assert expected in root_readme
    assert expected in operator_readme
    assert "Runtime writes remain only when requested through `hsconfig apply`." not in root_readme
```

Update `tests/test_skill_files.py` in `test_active_docs_show_normal_source_document_operator_path` so the root README assertion expects the exact runtime-write sentence:

```python
assert "Runtime writes happen only through `hsconfig apply` or `hsconfig configure --apply`." in root_readme
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```powershell
python -m pytest tests\test_docs_active_path.py::test_preferred_path_docs_use_single_lower_level_chain_label tests\test_docs_active_path.py::test_runtime_write_wording_names_apply_and_configure_apply tests\test_skill_files.py::test_active_docs_show_normal_source_document_operator_path -q
```

Expected before implementation:

```text
FAILED
```

- [ ] **Step 3: Update root README wording**

In `README.md`, replace:

```markdown
Runtime writes remain only when requested through `hsconfig apply`.
```

with:

```markdown
Runtime writes happen only through `hsconfig apply` or `hsconfig configure --apply`.
```

Do not expand the root README beyond this wording fix.

- [ ] **Step 4: Update operator guide wording**

In `docs/operator/README.md`, ensure the Preferred Normal Path keeps:

```markdown
Preferred normal path: `hsconfig configure`.
```

Ensure the Lower-Level section keeps:

```markdown
Lower-level inspected path: `source-manifest -> draft-source-documents -> research-deck -> prepare -> validate -> apply`.
```

Add this sentence under the Normal Operator Path list:

```markdown
Runtime writes happen only through `hsconfig apply` or `hsconfig configure --apply`.
```

Do not remove the existing HSTuner boundary sentence.

- [ ] **Step 5: Update skill source wording**

In `.agents/skills/hsconfig/SKILL.md` and `.agents/skills/hsconfig/references/workflow.md`, keep the normal workflow as:

```markdown
1. Prefer `hsconfig configure ...` for normal operation.
2. Use lower-level commands only when inspecting a stage:
   `source-manifest -> draft-source-documents -> research-deck -> prepare -> validate -> apply`.
3. Open `reports/operator_summary.json` first.
```

Ensure both files include:

```markdown
Runtime writes happen only through `hsconfig apply` or `hsconfig configure --apply`.
```

- [ ] **Step 6: Sync installed skill**

Run:

```powershell
python scripts\sync_installed_skill.py
python scripts\sync_installed_skill.py --check
```

Expected:

```text
HSConfig skill is in sync: C:\Users\darbo\.codex\skills\hsconfig
```

- [ ] **Step 7: Run focused docs and skill tests**

Run:

```powershell
python -m pytest tests\test_docs_active_path.py tests\test_skill_files.py tests\test_skill_sync.py -q
```

Expected:

```text
passed
```

- [ ] **Step 8: Commit**

Run:

```powershell
git add README.md docs\operator\README.md .agents\skills\hsconfig\SKILL.md .agents\skills\hsconfig\references\workflow.md tests\test_docs_active_path.py tests\test_skill_files.py
git commit -m "docs: clarify hsconfig normal path wording"
```

Do not stage `C:\Users\darbo\.codex\skills\hsconfig`; that installed copy is verified with `scripts\sync_installed_skill.py --check` and is not part of the Git repository.

---

### Task 3: Rename CLI Help From Lower-Level Normal To Inspected Stages

**Files:**
- Modify: `src/hsconfig/cli_parser.py`
- Test: `tests/test_cli_help.py`

**Interfaces:**
- Consumes: `build_parser() -> argparse.ArgumentParser`.
- Produces: CLI help that distinguishes `configure` from inspected lower-level stages.

- [ ] **Step 1: Update the failing CLI tests**

In `tests/test_cli_help.py`, replace `NORMAL_PATH` with:

```python
INSPECTED_PATH = (
    "source-manifest -> draft-source-documents -> research-deck -> "
    "prepare -> validate -> apply"
)
```

Update the root help tests to assert:

```python
assert "Preferred normal path: configure" in help_text
assert "Lower-level inspected path:" in help_text
assert INSPECTED_PATH in help_text
assert "Lower-level normal path:" not in help_text
```

Rename `test_prepare_help_is_marked_normal_path` to:

```python
def test_prepare_help_is_marked_inspected_package_stage(capsys):
    help_text = _subcommand_help("prepare", capsys)

    assert "Inspected package creation stage" in help_text
    assert "Normal package creation path" not in help_text
```

Add this subcommand help test:

```python
def test_source_stage_help_is_marked_inspected_not_normal(capsys):
    for command in ("source-manifest", "draft-source-documents", "research-deck"):
        help_text = _subcommand_help(command, capsys)
        assert "inspected" in help_text.lower()
        assert "normal path" not in help_text.lower()
```

- [ ] **Step 2: Run CLI tests to verify failure**

Run:

```powershell
python -m pytest tests\test_cli_help.py -q
```

Expected before implementation:

```text
FAILED
```

- [ ] **Step 3: Update parser epilog**

In `src/hsconfig/cli_parser.py`, change:

```python
"Lower-level normal path: source-manifest -> draft-source-documents -> research-deck -> "
```

to:

```python
"Lower-level inspected path: source-manifest -> draft-source-documents -> research-deck -> "
```

- [ ] **Step 4: Update prepare help**

In `src/hsconfig/cli_parser.py`, change the `prepare` parser from:

```python
help="normal package creation path",
description=(
    "Normal package creation path. Use deck identity, source-backed guide "
    "documents, and a runtime root to compile a pre-run CustomConfig package."
),
```

to:

```python
help="inspected package creation stage",
description=(
    "Inspected package creation stage. Use deck identity, source-backed guide "
    "documents, and a runtime root to compile a pre-run CustomConfig package."
),
```

Change the argument groups:

```python
prepare_normal = prepare.add_argument_group("normal required inputs")
prepare_source = prepare.add_argument_group("normal source inputs")
```

to:

```python
prepare_normal = prepare.add_argument_group("required package inputs")
prepare_source = prepare.add_argument_group("source inputs")
```

- [ ] **Step 5: Update source-stage help labels**

In `src/hsconfig/cli_parser.py`, change:

```python
help="normal path source research manifest"
help="normal path source document drafting"
help="normal path source document normalization"
```

to:

```python
help="inspected source research manifest stage"
help="inspected source document drafting stage"
help="inspected source document normalization stage"
```

- [ ] **Step 6: Update group-name tests**

In `tests/test_cli_help.py`, update `test_prepare_help_groups_normal_inputs_before_expert_fixture_inputs`:

```python
def test_prepare_help_groups_required_inputs_before_expert_fixture_inputs(capsys):
    help_text = _subcommand_help("prepare", capsys)

    assert "required package inputs" in help_text.lower()
    assert "expert/fixture inputs" in help_text.lower()
    assert help_text.lower().index("required package inputs") < help_text.lower().index(
        "expert/fixture inputs"
    )
    assert "--deck-name" in help_text
    assert "--deck-code" in help_text
    assert "--guide-sources-json" in help_text
    assert "--cards-json" in help_text
    assert "--claims-json" in help_text
```

- [ ] **Step 7: Run CLI tests**

Run:

```powershell
python -m pytest tests\test_cli_help.py -q
```

Expected:

```text
passed
```

- [ ] **Step 8: Commit**

Run:

```powershell
git add src\hsconfig\cli_parser.py tests\test_cli_help.py
git commit -m "docs: mark lower-level cli stages as inspected"
```

---

### Task 4: Add Compact Apply-Gate Contract Matrix

**Files:**
- Modify: `tests/test_property_no_block_apply_gate.py`
- No production code change expected unless a test exposes a genuine gate defect.

**Interfaces:**
- Consumes: `evaluate_apply_gate(package_root: str | Path, *, allow_source_informed: bool = False) -> dict[str, Any]`.
- Produces: deterministic coverage for clean, warning, and hard-block apply-gate cases.

- [ ] **Step 1: Add the matrix test**

Append this test to `tests/test_property_no_block_apply_gate.py`:

```python
@pytest.mark.parametrize(
    "case",
    [
        {
            "name": "clean_source_backed",
            "summary_payload": {
                "technical_status": "VALID_PACKAGE",
                "semantic_status": "SOURCE_BACKED_STRONG",
                "next_action": "READY_TO_APPLY_OR_HANDOFF",
                "apply_policy": "ALLOWED",
                "semantic_blockers": [],
            },
            "mutate": None,
            "expected_status": "allowed",
            "expected_reason": "runtime_load_safe_package",
        },
        {
            "name": "valid_with_warning_only_mechanics",
            "summary_payload": {
                "technical_status": "VALID_PACKAGE",
                "semantic_status": "VALID_BUT_NOT_GUIDE_STRONG",
                "next_action": "READY_TO_APPLY_WITH_WARNINGS",
                "apply_policy": "ALLOWED_WITH_WARNINGS",
                "semantic_blockers": [
                    {"reason": "warning_only_mechanic", "mechanic": "secret_timing"},
                    {"reason": "future_mechanic_drift", "mechanic": "rewind"},
                ],
            },
            "mutate": None,
            "expected_status": "allowed",
            "expected_reason": "runtime_load_safe_package",
        },
        {
            "name": "stale_summary_missing_actual_cardid",
            "summary_payload": {
                "technical_status": "VALID_PACKAGE",
                "semantic_status": "SOURCE_BACKED_STRONG",
                "next_action": "READY_TO_APPLY_OR_HANDOFF",
                "apply_policy": "ALLOWED",
                "semantic_blockers": [],
                "generated_files": [
                    "CustomConfig/deck/GlobalValues.json",
                    "CustomConfig/deck/Mulligan.json",
                ],
            },
            "mutate": lambda package: write_json(
                package / "CustomConfig" / "deck" / "EX1_777.json",
                {"GameCardId": "EX1_777"},
            ),
            "expected_status": "blocked",
            "expected_reason": "actual_runtime_file_not_in_operator_summary",
        },
        {
            "name": "legacy_optional_surface",
            "summary_payload": {
                "technical_status": "VALID_PACKAGE",
                "semantic_status": "SOURCE_BACKED_STRONG",
                "next_action": "READY_TO_APPLY_OR_HANDOFF",
                "apply_policy": "ALLOWED",
                "semantic_blockers": [],
            },
            "mutate": lambda package: write_json(
                package / "CustomConfig" / "deck" / "Presume.json",
                {},
            ),
            "expected_status": "blocked",
            "expected_reason": "normal_path_optional_surface_present",
        },
    ],
    ids=lambda case: case["name"],
)
def test_apply_gate_contract_matrix_keeps_warnings_open_and_technical_blocks_closed(
    tmp_path: Path,
    case: dict[str, Any],
):
    package = _write_package(
        tmp_path / "package",
        summary_payload=case["summary_payload"],
    )
    if case["mutate"] is not None:
        case["mutate"](package)

    gate = evaluate_apply_gate(package)

    assert gate["status"] == case["expected_status"]
    assert gate["reasons"][0]["reason"] == case["expected_reason"]
```

- [ ] **Step 2: Run the matrix test**

Run:

```powershell
python -m pytest tests\test_property_no_block_apply_gate.py::test_apply_gate_contract_matrix_keeps_warnings_open_and_technical_blocks_closed -q
```

Expected:

```text
4 passed
```

If a warning-only case blocks, inspect `src/hsconfig/apply_gate.py` and keep the fix limited to preserving `technical_status=VALID_PACKAGE` as the apply permission.

- [ ] **Step 3: Run focused apply-gate tests**

Run:

```powershell
python -m pytest tests\test_apply_gate.py tests\test_property_no_block_apply_gate.py tests\test_runtime_apply.py tests\test_runtime_apply_receipts.py -q
```

Expected:

```text
passed
```

- [ ] **Step 4: Commit**

Run:

```powershell
git add tests\test_property_no_block_apply_gate.py src\hsconfig\apply_gate.py
git commit -m "test: cover hsconfig apply gate warning matrix"
```

If `src\hsconfig\apply_gate.py` has no diff, use:

```powershell
git add tests\test_property_no_block_apply_gate.py
git commit -m "test: cover hsconfig apply gate warning matrix"
```

---

### Task 5: Add One Mixed-Mechanic Visibility Regression Without Widening Runtime Lowering

**Files:**
- Modify: `tests/test_mechanic_support.py`
- No production code change expected unless a classification is already wrong.

**Interfaces:**
- Consumes:
  - `support_for_roles(roles: list[str]) -> list[dict]`
  - `operator_visibility_bucket(row: dict) -> str`
  - `summarize_mechanic_visibility(rows: list[dict]) -> dict`
- Produces: a compact regression proving identity-gated direct, partial, and warning-only mechanics can coexist without blocking load-safe apply.

- [ ] **Step 1: Add the regression test**

Append this test to `tests/test_mechanic_support.py`:

```python
def test_mixed_mechanic_visibility_fixture_keeps_runtime_surface_narrow():
    rows = support_for_roles(
        [
            "discover",
            "choose_one",
            "hero_power_transform",
            "generated_entity",
            "secret_timing",
            "location_activation",
            "kindred",
            "rewind",
        ]
    )
    by_mechanic = {row["mechanic"]: row for row in rows}

    for mechanic in ["discover", "choose_one", "hero_power_transform"]:
        assert operator_visibility_bucket(by_mechanic[mechanic]) == "identity_gated_direct"
        assert by_mechanic[mechanic]["support_level"] == "direct"

    assert operator_visibility_bucket(by_mechanic["generated_entity"]) == "partial"
    assert by_mechanic["generated_entity"]["support_level"] == "partial"

    for mechanic in ["secret_timing", "location_activation", "kindred", "rewind"]:
        assert operator_visibility_bucket(by_mechanic[mechanic]) == "warning_only"
        assert by_mechanic[mechanic]["support_level"] == "warning_only"
        assert by_mechanic[mechanic]["normal_path_surfaces"] == ["report-only"]

    summary = summarize_mechanic_visibility(
        [
            {"card_id": "DISCOVER_CARD", "mechanic_support": support_for_roles(["discover"])},
            {"card_id": "CHOOSE_CARD", "mechanic_support": support_for_roles(["choose_one"])},
            {
                "card_id": "TRANSFORM_CARD",
                "mechanic_support": support_for_roles(["hero_power_transform"]),
            },
            {
                "card_id": "GENERATED_CARD",
                "mechanic_support": support_for_roles(["generated_entity"]),
            },
            {
                "card_id": "WARNING_CARD",
                "mechanic_support": support_for_roles(
                    ["secret_timing", "location_activation", "kindred", "rewind"]
                ),
            },
        ]
    )

    assert summary["non_blocking"] is True
    assert summary["bucket_counts"]["identity_gated_direct"] == 3
    assert summary["bucket_counts"]["partial"] == 1
    assert summary["bucket_counts"]["warning_only"] == 4
    assert summary["mechanics_by_bucket"]["warning_only"] == [
        "kindred",
        "location_activation",
        "rewind",
        "secret_timing",
    ]
```

- [ ] **Step 2: Run the new test**

Run:

```powershell
python -m pytest tests\test_mechanic_support.py::test_mixed_mechanic_visibility_fixture_keeps_runtime_surface_narrow -q
```

Expected:

```text
1 passed
```

If the test fails only because ordering differs, update the expected sorted order to match `summarize_mechanic_visibility()` behavior after confirming it is deterministic. Do not add runtime lowering for `secret_timing`, `location_activation`, `kindred`, or `rewind`.

- [ ] **Step 3: Run mechanic tests**

Run:

```powershell
python -m pytest tests\test_mechanic_support.py tests\test_mechanic_lowering_parity.py tests\test_mechanic_drift.py -q
```

Expected:

```text
passed
```

- [ ] **Step 4: Commit**

Run:

```powershell
git add tests\test_mechanic_support.py
git commit -m "test: cover mixed mechanic visibility boundary"
```

---

### Task 6: Final Verification And Repository State

**Files:**
- No source files expected beyond prior tasks.

**Interfaces:**
- Consumes: all prior task changes.
- Produces: verified narrow-polish branch ready for user review or merge.

- [ ] **Step 1: Check installed skill sync**

Run:

```powershell
python scripts\sync_installed_skill.py --check
```

Expected:

```text
HSConfig skill is in sync: C:\Users\darbo\.codex\skills\hsconfig
```

- [ ] **Step 2: Validate research JSONs**

Run:

```powershell
python C:\Users\darbo\.codex\skills\research\validate_json.py -f docs\research\2026-07-11-hsconfig-live-skill-audit\fields.yaml -j docs\research\2026-07-11-hsconfig-live-skill-audit\results\Skill_Slimness_And_Operator_UX.json docs\research\2026-07-11-hsconfig-live-skill-audit\results\Runtime_Surface_And_VisionAI_Correctness.json docs\research\2026-07-11-hsconfig-live-skill-audit\results\No_Block_Apply_Gate_And_Tests.json docs\research\2026-07-11-hsconfig-live-skill-audit\results\Hearthstone_Semantic_Coverage.json docs\research\2026-07-11-hsconfig-live-skill-audit\results\Real_Deck_Readiness_And_Next_Action.json
```

Expected:

```text
Validation passed: 5/5
Average coverage: 100.0%
```

- [ ] **Step 3: Run focused verification**

Run:

```powershell
python -m pytest tests\test_cli_help.py tests\test_docs_active_path.py tests\test_skill_files.py tests\test_skill_sync.py tests\test_apply_gate.py tests\test_property_no_block_apply_gate.py tests\test_runtime_apply.py tests\test_runtime_apply_receipts.py tests\test_mechanic_support.py tests\test_mechanic_lowering_parity.py tests\test_mechanic_drift.py -q
```

Expected:

```text
passed
```

- [ ] **Step 4: Run full test suite**

Run:

```powershell
python -m pytest -q
```

Expected:

```text
812 passed, 2 skipped
```

The exact duration can vary. The pass and skip counts should stay stable unless prior tasks intentionally add tests; if tests were added, the pass count should increase by the number of new tests.

- [ ] **Step 5: Scan for wording drift in active paths**

Run:

```powershell
rg -n "Lower-level normal path|Runtime writes remain only when requested through `hsconfig apply`|Presume/Concede are documented normal outputs|parse replays, inspect winrate, analyze runtime logs, promote candidates, or tune after games" README.md docs\operator .agents\skills\hsconfig src tests
```

Expected:

```text
No matches for "Lower-level normal path"
No matches for "Runtime writes remain only when requested through `hsconfig apply`"
No matches for "Presume/Concede are documented normal outputs"
Only negative-scope matches for "parse replays, inspect winrate, analyze runtime logs, promote candidates, or tune after games"
```

- [ ] **Step 6: Check diff and status**

Run:

```powershell
git diff --check
git status --short --branch
```

Expected:

```text
git diff --check exits 0
branch is codex/hsconfig-lean-contract-hardening or the active implementation branch
only intentional files are modified before final commit
```

- [ ] **Step 7: Final commit if prior tasks were squashed locally**

If prior task commits were not created, create one final commit:

```powershell
git add README.md docs\operator\README.md docs\research\current-truth.md docs\research\2026-07-11-hsconfig-live-skill-audit .agents\skills\hsconfig src\hsconfig\cli_parser.py tests\test_cli_help.py tests\test_docs_active_path.py tests\test_skill_files.py tests\test_property_no_block_apply_gate.py tests\test_mechanic_support.py
git commit -m "chore: finish hsconfig narrow polish"
```

- [ ] **Step 8: Push**

Run:

```powershell
git push origin HEAD
```

Expected:

```text
branch pushed to origin
```

---

## Self-Review

- Spec coverage: The plan implements the chosen recommendation: narrow wording polish, current audit evidence retention, no-block gate regression, mixed-mechanic visibility regression, installed skill sync, and full verification.
- Scope control: The plan does not add HSTuner behavior, replay parsing, winrate logic, new runtime surfaces, or broader semantic lowering.
- File boundaries: Documentation, CLI help, apply-gate tests, and mechanic tests are separated by responsibility.
- Testability: Every task has a focused test command and a final verification command.
- Placeholder scan: The plan contains no unresolved placeholder markers and no unspecified implementation steps.

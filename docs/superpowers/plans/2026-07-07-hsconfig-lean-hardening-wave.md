# HSConfig Lean Hardening Wave Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden the existing HSConfig pre-game workflow so `prepare -> operator_summary -> apply` is clean, non-stale, strongly gated, documented, and still lean.

**Architecture:** Keep HSConfig as a deterministic deck-to-HearthRanger CustomConfig generator. Do not add a new pipeline; close the current small gaps in output cleanup, apply gating, documented condition syntax, GlobalValues validation, CLI guidance, and scope boundaries.

**Tech Stack:** Python 3.11+, stdlib `argparse`/`pathlib`/`json`/`re`, pytest, existing `hsconfig` package modules, existing local skill sync script.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig` for `Teufelsboy/HSConfig`.
- Keep HSConfig separate from HSTuner.
- Do not add replay parsing, HDT parsing, Power.log parsing, winrate validation, candidate promotion, or post-run tuning to this repo.
- Generated runtime packages belong under `outputs/` and are ignored by git.
- Preserve exact deck and CardID identity.
- Preserve full `GlobalValues.json` key profiling.
- Preserve every card covered in the gameplan contract.
- Preserve strict JSON validation.
- Preserve row-level provenance for generated config rows.
- Normal runtime output remains `GlobalValues.json`, `Mulligan.json`, per-card `<CARDID>.json`, and `Combo.json` only when a concrete exact sequence exists.
- `Presume.json` and `Concede.json` remain outside the normal HSConfig path.
- No new dependencies.
- Tests must not require network access.

---

## File Structure

- `src/hsconfig/cli.py`: Owns normal CLI routing, package preparation, report writing, and generated-file enumeration.
- `src/hsconfig/apply_gate.py`: Owns the policy gate before runtime apply.
- `src/hsconfig/condition_format.py`: Owns supported runtime condition strings and structured condition lowering.
- `src/hsconfig/validate_package.py`: Owns package shape and runtime JSON validation.
- `docs/operator/source-builder-workflow.md`: Operator-facing normal workflow and identity boundary.
- `.agents/skills/hsconfig/references/workflow.md`: Installed-skill workflow reference, kept in sync with operator docs.
- `tests/test_prepare_cli.py`: CLI package creation and reports tests.
- `tests/test_apply_gate.py`: Apply gate policy tests.
- `tests/test_condition_format.py`: Runtime condition syntax tests.
- `tests/test_compile_globalvalues.py`: GlobalValues compile and validation tests.
- `tests/test_cli_help.py`: New CLI help/UX contract tests.
- `tests/test_scope_boundaries.py`: New repository scope guard tests.

## Task 1: Make `prepare` Output Run-Clean

**Files:**
- Modify: `src/hsconfig/cli.py`
- Test: `tests/test_prepare_cli.py`

**Interfaces:**
- Consumes: existing `_build(args: argparse.Namespace) -> tuple[dict[str, Any], int]`
- Produces: new helper `_reset_generated_package_dirs(deck_dir: Path, reports_dir: Path) -> None`

- [ ] **Step 1: Write the failing stale-report test**

Append this test to `tests/test_prepare_cli.py`:

```python
def test_prepare_clears_stale_reports_before_operator_summary_generated_files(
    tmp_path: Path, capsys, monkeypatch
):
    monkeypatch.setattr("hsconfig.cli.fetch_latest_cards", lambda timeout=10.0: [])
    package = tmp_path / "package"
    reports = package / "reports"
    reports.mkdir(parents=True)
    stale_report = reports / "stale_report.json"
    stale_report.write_text('{"stale": true}', encoding="utf-8")

    code = main(
        [
            "prepare",
            "--deck-name",
            "ShadowPriest",
            "--deck-code",
            SHADOWPRIEST_CODE,
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(package),
            "--source-documents-json",
            "tests/fixtures/source_documents_shadowpriest_strong.json",
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    operator_summary = json.loads(
        (reports / "operator_summary.json").read_text(encoding="utf-8")
    )
    generated = {path.replace("\\", "/") for path in operator_summary["generated_files"]}

    assert code == 0
    assert payload["status"] == "passed"
    assert not stale_report.exists()
    assert "reports/stale_report.json" not in generated
```

- [ ] **Step 2: Run the failing test**

Run:

```powershell
python -m pytest tests/test_prepare_cli.py::test_prepare_clears_stale_reports_before_operator_summary_generated_files -q
```

Expected: FAIL because `stale_report.json` still exists or appears in `operator_summary.generated_files`.

- [ ] **Step 3: Implement output cleanup**

In `src/hsconfig/cli.py`, add this helper near `_generated_package_files`:

```python
def _reset_generated_package_dirs(deck_dir: Path, reports_dir: Path) -> None:
    for target in (deck_dir, reports_dir):
        if target.exists():
            shutil.rmtree(target)
```

In `_build`, replace the current deck-only cleanup:

```python
    if deck_dir.exists():
        shutil.rmtree(deck_dir)
```

with:

```python
    _reset_generated_package_dirs(deck_dir, reports_dir)
```

Keep the call immediately before the first runtime or report write, after `globalvalues = compile_globalvalues(...)`.

- [ ] **Step 4: Run focused tests**

Run:

```powershell
python -m pytest tests/test_prepare_cli.py::test_prepare_clears_stale_reports_before_operator_summary_generated_files tests/test_prepare_cli.py::test_prepare_builds_valid_package_with_research_artifacts -q
```

Expected: both tests pass.

- [ ] **Step 5: Commit**

```powershell
git add src/hsconfig/cli.py tests/test_prepare_cli.py
git commit -m "fix: clear stale prepare outputs"
```

## Task 2: Harden Apply Gate Against Summary-Only Packages

**Files:**
- Modify: `src/hsconfig/apply_gate.py`
- Test: `tests/test_apply_gate.py`

**Interfaces:**
- Consumes: `evaluate_apply_gate(package_root: str | Path, *, allow_source_informed: bool = False) -> dict[str, Any]`
- Produces: `_required_package_structure_reasons(package: Path, summary: dict[str, Any]) -> list[dict[str, str]]`

- [ ] **Step 1: Add package-writing test helpers**

At the top of `tests/test_apply_gate.py`, below `_write_operator_summary`, add:

```python
def _write_minimal_runtime_package(package: Path) -> None:
    write_json(
        package / "CustomConfig" / "deck" / "GlobalValues.json",
        {"GameCardId": "GlobalValues", "ConfigComment": "new"},
    )
    write_json(
        package / "CustomConfig" / "deck" / "Mulligan.json",
        {"GameCardId": "Mulligan", "ConfigComment": "new", "Mulligan": {"values": []}},
    )
    write_json(
        package / "CustomConfig" / "deck" / "EX1_001.json",
        {"GameCardId": "EX1_001", "ConfigComment": "new", "InHandPlayPriority": {"values": []}},
    )
    write_json(
        package / "reports" / "input_manifest.json",
        {"deck_name": "deck", "deck_code": "fixture", "runtime_root": "unused"},
    )
```

- [ ] **Step 2: Update the allowed-package test to use real files**

In `test_apply_gate_allows_source_backed_ready_package`, add this line before `_write_operator_summary(...)`:

```python
    _write_minimal_runtime_package(package)
```

- [ ] **Step 3: Write the failing summary-only block test**

Append this test to `tests/test_apply_gate.py`:

```python
def test_apply_gate_blocks_summary_only_ready_package(tmp_path: Path):
    package = tmp_path / "package"
    _write_operator_summary(
        package,
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "SOURCE_BACKED_STRONG",
            "next_action": "READY_TO_APPLY_OR_HANDOFF",
            "apply_policy": "ALLOWED",
            "semantic_blockers": [],
            "generated_files": [
                "CustomConfig\\deck\\GlobalValues.json",
                "CustomConfig\\deck\\Mulligan.json",
                "CustomConfig\\deck\\EX1_001.json",
            ],
        },
    )

    gate = evaluate_apply_gate(package)

    assert gate["status"] == "blocked"
    assert gate["reasons"][0] == {
        "reason": "missing_custom_config_directory",
        "path": str(package / "CustomConfig"),
    }
```

- [ ] **Step 4: Write the failing input-manifest block test**

Append this test to `tests/test_apply_gate.py`:

```python
def test_apply_gate_blocks_package_without_input_manifest(tmp_path: Path):
    package = tmp_path / "package"
    write_json(
        package / "CustomConfig" / "deck" / "GlobalValues.json",
        {"GameCardId": "GlobalValues", "ConfigComment": "new"},
    )
    write_json(
        package / "CustomConfig" / "deck" / "Mulligan.json",
        {"GameCardId": "Mulligan", "ConfigComment": "new", "Mulligan": {"values": []}},
    )
    write_json(
        package / "CustomConfig" / "deck" / "EX1_001.json",
        {"GameCardId": "EX1_001", "ConfigComment": "new", "InHandPlayPriority": {"values": []}},
    )
    _write_operator_summary(
        package,
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "SOURCE_BACKED_STRONG",
            "next_action": "READY_TO_APPLY_OR_HANDOFF",
            "apply_policy": "ALLOWED",
            "semantic_blockers": [],
            "generated_files": [
                "CustomConfig\\deck\\GlobalValues.json",
                "CustomConfig\\deck\\Mulligan.json",
                "CustomConfig\\deck\\EX1_001.json",
            ],
        },
    )

    gate = evaluate_apply_gate(package)

    assert gate["status"] == "blocked"
    assert gate["reasons"][0] == {
        "reason": "missing_input_manifest",
        "path": str(package / "reports" / "input_manifest.json"),
    }
```

- [ ] **Step 5: Run the failing tests**

Run:

```powershell
python -m pytest tests/test_apply_gate.py::test_apply_gate_blocks_summary_only_ready_package tests/test_apply_gate.py::test_apply_gate_blocks_package_without_input_manifest -q
```

Expected: both tests fail because the current gate trusts `operator_summary.json` too much.

- [ ] **Step 6: Implement structure checks**

In `src/hsconfig/apply_gate.py`, add this constant near `OPTIONAL_NORMAL_PATH_SURFACES`:

```python
REQUIRED_RUNTIME_FILES = ("GlobalValues.json", "Mulligan.json")
```

In `evaluate_apply_gate`, after validating `summary` is a dict and before optional-surface checks, add:

```python
    structure_reasons = _required_package_structure_reasons(package, summary)
    if structure_reasons:
        return _blocked(operator_path, *structure_reasons)
```

Add this helper above `_summary_optional_surface_reasons`:

```python
def _required_package_structure_reasons(
    package: Path, summary: dict[str, Any]
) -> list[dict[str, str]]:
    custom_config = package / "CustomConfig"
    if not custom_config.is_dir():
        return [
            {
                "reason": "missing_custom_config_directory",
                "path": str(custom_config),
            }
        ]

    manifest = package / "reports" / "input_manifest.json"
    if not manifest.is_file():
        return [
            {
                "reason": "missing_input_manifest",
                "path": str(manifest),
            }
        ]

    deck_dirs = sorted(path for path in custom_config.iterdir() if path.is_dir())
    if not deck_dirs:
        return [
            {
                "reason": "missing_deck_runtime_directory",
                "path": str(custom_config),
            }
        ]
    if len(deck_dirs) > 1:
        return [
            {
                "reason": "multiple_deck_runtime_directories",
                "path": str(custom_config),
            }
        ]

    deck_dir = deck_dirs[0]
    for filename in REQUIRED_RUNTIME_FILES:
        required = deck_dir / filename
        if not required.is_file():
            return [
                {
                    "reason": "missing_required_runtime_file",
                    "path": str(required),
                }
            ]

    card_files = [
        path
        for path in sorted(deck_dir.glob("*.json"))
        if path.name
        not in {
            "Combo.json",
            "Concede.json",
            "GlobalValues.json",
            "Mulligan.json",
            "Presume.json",
        }
    ]
    if not card_files:
        return [
            {
                "reason": "missing_cardid_runtime_file",
                "path": str(deck_dir),
            }
        ]

    summary_files = _summary_generated_file_set(summary)
    for filename in REQUIRED_RUNTIME_FILES:
        key = _normalize_generated_file_path((deck_dir / filename).relative_to(package))
        if key not in summary_files:
            return [
                {
                    "reason": "required_runtime_file_not_in_operator_summary",
                    "generated_file": key,
                }
            ]
    return []
```

Do not require package-local `CustomConfig/deck_config.ini`. In HSConfig, `runtime_apply.py` owns the runtime `deck_config.ini` update, and `reports/input_manifest.json` is the package proof that the apply step has a safe visible deck name.

- [ ] **Step 7: Run apply gate tests**

Run:

```powershell
python -m pytest tests/test_apply_gate.py tests/test_runtime_apply.py -q
```

Expected: all tests pass.

- [ ] **Step 8: Commit**

```powershell
git add src/hsconfig/apply_gate.py tests/test_apply_gate.py
git commit -m "fix: require real package files before apply"
```

## Task 3: Expand Documented Runtime Condition Support

**Files:**
- Modify: `src/hsconfig/condition_format.py`
- Test: `tests/test_condition_format.py`

**Interfaces:**
- Consumes: `classify_runtime_condition(value: Any) -> LoweredCondition`
- Consumes: `lower_runtime_condition(value: Any) -> tuple[str, str | None]`
- Produces: support for documented class-list hero conditions and structured `opponent_classes`

- [ ] **Step 1: Write failing condition tests**

Append these tests to `tests/test_condition_format.py`:

```python
def test_allows_documented_opponent_hero_class_list_condition():
    condition = "opp_hero(count(), hero_class=warrior | rogue | paladin ) > 0"

    lowered = classify_runtime_condition(condition)

    assert lowered.status == "runtime_safe"
    assert lower_runtime_condition(condition) == (condition, None)


def test_structured_opponent_classes_lower_to_documented_runtime_condition():
    assert lower_runtime_condition({"opponent_classes": ["warrior", "rogue", "paladin"]}) == (
        "opp_hero(count(), hero_class=warrior | rogue | paladin ) > 0",
        None,
    )
```

- [ ] **Step 2: Run the failing tests**

Run:

```powershell
python -m pytest tests/test_condition_format.py::test_allows_documented_opponent_hero_class_list_condition tests/test_condition_format.py::test_structured_opponent_classes_lower_to_documented_runtime_condition -q
```

Expected: both tests fail because the current parser rejects pipe characters outside `AND`/`OR` atom splitting and does not know `opponent_classes`.

- [ ] **Step 3: Implement class-list condition syntax**

In `src/hsconfig/condition_format.py`, change the constants to include class lists:

```python
STRUCTURED_RUNTIME_CONDITION_KEYS = {
    "coin",
    "nocoin",
    "opponent_class",
    "opponent_classes",
    "hand_contains",
    "hand_contains_any",
    "combo_partner",
}
CARD_ID_PATTERN = r"[A-Za-z0-9_]+"
CLASS_PATTERN = r"[a-z]+"
CLASS_LIST_PATTERN = rf"{CLASS_PATTERN}(?:\s*\|\s*{CLASS_PATTERN})*"
```

Add this pattern to `ALLOWED_ATOM_PATTERNS` after the existing single-class `opp_hero` pattern:

```python
    re.compile(
        rf"^opp_hero\(count\(\),\s*hero_class\s*=\s*{CLASS_LIST_PATTERN}\s*\)\s*>\s*0$"
    ),
```

In `_atoms_from_structured_condition`, after `opponent_class`, add:

```python
    if value.get("opponent_classes"):
        raw_classes = value["opponent_classes"]
        classes = [raw_classes] if isinstance(raw_classes, str) else list(raw_classes)
        clean_classes = [str(hero_class).lower() for hero_class in classes]
        atoms.append(
            "opp_hero(count(), hero_class="
            + " | ".join(clean_classes)
            + " ) > 0"
        )
```

In `_is_runtime_safe`, replace:

```python
    if "|" in condition:
        return False
```

with:

```python
    if "|" in condition:
        return _is_atom_safe(condition)
```

- [ ] **Step 4: Preserve unsupported pipe behavior**

Keep `test_rejects_unknown_strings_and_top_level_pipe` unchanged. It must still prove that `coin | nocoin` is unsupported.

- [ ] **Step 5: Run condition tests**

Run:

```powershell
python -m pytest tests/test_condition_format.py tests/test_mulligan_plan.py tests/test_card_behavior_router.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```powershell
git add src/hsconfig/condition_format.py tests/test_condition_format.py
git commit -m "feat: support documented hero class conditions"
```

## Task 4: Require `condition` And `value` On GlobalValues Rows

**Files:**
- Modify: `src/hsconfig/validate_package.py`
- Test: `tests/test_compile_globalvalues.py`

**Interfaces:**
- Consumes: `validate_config_package(package_root, *, globalvalues_baseline=None, globalvalues_profile=None, require_complete_package=False, require_globalvalues_profile=False) -> dict[str, Any]`
- Produces: GlobalValues row validation for missing `condition` and missing `value`

- [ ] **Step 1: Write the failing validation test**

Append this test to `tests/test_compile_globalvalues.py`:

```python
def test_validate_package_rejects_globalvalues_rows_missing_condition_or_value(tmp_path: Path):
    deck_dir = tmp_path / "CustomConfig" / "deck"
    payload = {
        "GameCardId": "GlobalValues",
        "ConfigComment": "Fixture",
        "FirstTurnValueWeight": {"values": [{"value": "1.00"}]},
        "SecondTurnValueWeight": {"values": [{"condition": "*"}]},
    }
    write_json(deck_dir / "GlobalValues.json", payload)

    report = validate_config_package(tmp_path)

    assert report["status"] == "failed"
    assert any(
        "GlobalValues block FirstTurnValueWeight row 0 missing condition" in error
        for error in report["errors"]
    )
    assert any(
        "GlobalValues block SecondTurnValueWeight row 0 missing value" in error
        for error in report["errors"]
    )
```

- [ ] **Step 2: Run the failing test**

Run:

```powershell
python -m pytest tests/test_compile_globalvalues.py::test_validate_package_rejects_globalvalues_rows_missing_condition_or_value -q
```

Expected: FAIL because current validation only verifies `values` arrays exist.

- [ ] **Step 3: Implement GlobalValues row validation**

In `src/hsconfig/validate_package.py`, add this helper below `_validate_values_blocks`:

```python
def _validate_globalvalues_rows(path: Path, data: dict[str, Any]) -> list[str]:
    errors = []
    for key, block in data.items():
        if key in {"GameCardId", "ConfigComment"}:
            continue
        if not isinstance(block, dict):
            continue
        values = block.get("values")
        if not isinstance(values, list):
            continue
        for index, row in enumerate(values):
            if not isinstance(row, dict):
                errors.append(f"{path}: GlobalValues block {key} row {index} must be an object")
                continue
            if "condition" not in row:
                errors.append(
                    f"{path}: GlobalValues block {key} row {index} missing condition"
                )
            if "value" not in row:
                errors.append(f"{path}: GlobalValues block {key} row {index} missing value")
    return errors
```

In `_validate_globalvalues`, replace:

```python
    errors = _validate_values_blocks(path, data)
```

with:

```python
    errors = _validate_values_blocks(path, data)
    errors.extend(_validate_globalvalues_rows(path, data))
```

- [ ] **Step 4: Run GlobalValues tests**

Run:

```powershell
python -m pytest tests/test_compile_globalvalues.py tests/test_validate_package.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add src/hsconfig/validate_package.py tests/test_compile_globalvalues.py
git commit -m "fix: validate globalvalues row shape"
```

## Task 5: Make CLI Help Show Normal And Expert Paths

**Files:**
- Modify: `src/hsconfig/cli.py`
- Create: `tests/test_cli_help.py`

**Interfaces:**
- Consumes: `_build_parser() -> argparse.ArgumentParser`
- Produces: root and subcommand help text that labels normal path and expert path

- [ ] **Step 1: Create the failing help tests**

Create `tests/test_cli_help.py`:

```python
import pytest

from hsconfig.cli import _build_parser


def test_root_help_names_normal_and_expert_paths():
    help_text = _build_parser().format_help()

    assert "Normal path:" in help_text
    assert "source-manifest -> draft-source-documents -> research-deck -> prepare -> apply" in help_text
    assert "Expert and legacy path:" in help_text
    assert "build, --claims-json, --cards-json, --plan-reports-dir" in help_text


def _subcommand_help(command: str, capsys) -> str:
    parser = _build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([command, "--help"])
    return capsys.readouterr().out


def test_prepare_help_is_marked_normal_path(capsys):
    help_text = _subcommand_help("prepare", capsys)

    assert "Normal package creation path" in help_text


def test_build_help_is_marked_expert_path(capsys):
    help_text = _subcommand_help("build", capsys)

    assert "Expert lower-level package builder" in help_text
```

- [ ] **Step 2: Run the failing tests**

Run:

```powershell
python -m pytest tests/test_cli_help.py -q
```

Expected: FAIL because the parser currently has no operator path description.

- [ ] **Step 3: Update parser descriptions**

In `src/hsconfig/cli.py`, replace:

```python
    parser = argparse.ArgumentParser(prog="hsconfig")
```

with:

```python
    parser = argparse.ArgumentParser(
        prog="hsconfig",
        description="HSConfig builds lean HearthRanger VisionAI CustomConfig packages before games are played.",
        epilog=(
            "Normal path: source-manifest -> draft-source-documents -> research-deck -> "
            "prepare -> apply. Expert and legacy path: build, --claims-json, "
            "--cards-json, --plan-reports-dir."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
```

Change the subparser declarations for the normal path:

```python
    build = subparsers.add_parser(
        "build",
        help="expert lower-level package builder",
        description="Expert lower-level package builder.",
    )
```

```python
    prepare = subparsers.add_parser(
        "prepare",
        help="normal package creation path",
        description="Normal package creation path.",
    )
```

```python
    source_manifest = subparsers.add_parser(
        "source-manifest",
        help="normal path source research manifest",
    )
```

```python
    draft_source_documents = subparsers.add_parser(
        "draft-source-documents",
        help="normal path source document drafting",
    )
```

```python
    research_deck = subparsers.add_parser(
        "research-deck",
        help="normal path source document normalization",
    )
```

Keep existing command names and options unchanged.

- [ ] **Step 4: Run CLI tests**

Run:

```powershell
python -m pytest tests/test_cli_help.py tests/test_cli.py tests/test_prepare_cli.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add src/hsconfig/cli.py tests/test_cli_help.py
git commit -m "docs: clarify hsconfig cli paths"
```

## Task 6: Document Identity-Only HDT Fields And Guard Scope

**Files:**
- Modify: `docs/operator/source-builder-workflow.md`
- Modify: `.agents/skills/hsconfig/references/workflow.md`
- Create: `tests/test_scope_boundaries.py`
- Test: `tests/test_skill_files.py`

**Interfaces:**
- Produces: repo-level guard that HSConfig does not import post-run parser concepts
- Produces: operator docs that explain `hdt_deck_id` as identity-only metadata

- [ ] **Step 1: Create the scope guard tests**

Create `tests/test_scope_boundaries.py`:

```python
from pathlib import Path


FORBIDDEN_SRC_TERMS = {
    "power.log",
    "hsreplay",
    "hdt replay",
    "winrate",
    "candidate promotion",
    "post-run tuning",
    "analyze-step2",
}


def test_hsconfig_src_does_not_absorb_post_run_scope():
    offenders = []
    for path in sorted(Path("src/hsconfig").glob("*.py")):
        text = path.read_text(encoding="utf-8").lower()
        for term in FORBIDDEN_SRC_TERMS:
            if term in text:
                offenders.append(f"{path}:{term}")

    assert offenders == []


def test_operator_docs_explain_hdt_as_identity_only():
    docs = (
        Path("docs/operator/source-builder-workflow.md").read_text(encoding="utf-8")
        + "\n"
        + Path(".agents/skills/hsconfig/references/workflow.md").read_text(encoding="utf-8")
    )

    assert "hdt_deck_id is identity-only metadata" in docs
    assert "not replay evidence" in docs
```

- [ ] **Step 2: Run the failing docs test**

Run:

```powershell
python -m pytest tests/test_scope_boundaries.py -q
```

Expected: the second test fails until docs state the identity boundary.

- [ ] **Step 3: Update operator workflow docs**

In `docs/operator/source-builder-workflow.md`, add this paragraph after the opening workflow paragraph:

```markdown
Identity fields such as `hs_id` and `hdt_deck_id` are identity-only metadata in HSConfig. `hdt_deck_id` is identity-only metadata, not replay evidence, not HDT parsing input, and not a post-run tuning source. HSConfig uses these identifiers to keep deck rows and examples unambiguous before games are played.
```

In `.agents/skills/hsconfig/references/workflow.md`, add the same paragraph after the opening workflow paragraph.

- [ ] **Step 4: Run docs and skill tests**

Run:

```powershell
python -m pytest tests/test_scope_boundaries.py tests/test_skill_files.py -q
python scripts/sync_installed_skill.py --check
```

Expected: pytest passes and skill sync reports no drift. If skill sync reports drift because `.agents/skills/hsconfig/references/workflow.md` changed, run the repository's documented sync command:

```powershell
python scripts/sync_installed_skill.py
python scripts/sync_installed_skill.py --check
```

Expected after sync: no drift.

- [ ] **Step 5: Commit**

```powershell
git add docs/operator/source-builder-workflow.md .agents/skills/hsconfig/references/workflow.md tests/test_scope_boundaries.py
git commit -m "docs: state hsconfig identity boundary"
```

## Task 7: Final Verification And GitHub Update

**Files:**
- No planned code changes.
- Validate all files changed by Tasks 1-6.

**Interfaces:**
- Consumes: all task-level changes.
- Produces: verified branch ready for `origin/main`.

- [ ] **Step 1: Run focused regression tests**

Run:

```powershell
python -m pytest tests/test_prepare_cli.py tests/test_apply_gate.py tests/test_runtime_apply.py tests/test_condition_format.py tests/test_compile_globalvalues.py tests/test_validate_package.py tests/test_cli_help.py tests/test_scope_boundaries.py tests/test_skill_files.py -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run the full test suite**

Run:

```powershell
python -m pytest -q
```

Expected: full suite passes. The current known healthy baseline is hundreds of passing tests with several intentional skips; do not accept new failures.

- [ ] **Step 3: Run skill sync check**

Run:

```powershell
python scripts/sync_installed_skill.py --check
```

Expected: no installed-skill drift.

- [ ] **Step 4: Run scope and stale-language scans**

Run:

```powershell
rg -n "Power\\.log|hsreplay|HDT replay|winrate|candidate promotion|post-run tuning|analyze-step2" src/hsconfig
rg -n "Presume\\.json|Concede\\.json" README.md docs/operator .agents/skills/hsconfig
```

Expected:

- First command returns no matches.
- Second command may mention Presume/Concede only as documented-but-not-normal surfaces.

- [ ] **Step 5: Inspect git state and final diff**

Run:

```powershell
git status --short --branch
git diff --stat HEAD
git diff HEAD -- src/hsconfig/cli.py src/hsconfig/apply_gate.py src/hsconfig/condition_format.py src/hsconfig/validate_package.py docs/operator/source-builder-workflow.md .agents/skills/hsconfig/references/workflow.md tests/test_prepare_cli.py tests/test_apply_gate.py tests/test_condition_format.py tests/test_compile_globalvalues.py tests/test_cli_help.py tests/test_scope_boundaries.py
```

Expected: diff contains only the hardening changes described in this plan.

- [ ] **Step 6: Commit any verification-only doc adjustments**

If Step 5 reveals a small wording or formatting fix made during verification, commit it:

```powershell
git add <changed-files>
git commit -m "chore: polish hsconfig hardening docs"
```

Expected: this command is skipped when there are no verification-only edits.

- [ ] **Step 7: Push to GitHub**

Run:

```powershell
git status --short --branch
git push origin main
```

Expected: local `main` is pushed to `origin/main`.

## Self-Review

Spec coverage:

- Run-clean `prepare`: Task 1.
- Stronger apply gate without adding a new pipeline: Task 2.
- Documented Mulligan and runtime condition support: Task 3.
- GlobalValues validation consistency: Task 4.
- Clear normal/expert CLI path: Task 5.
- HDT identity-only wording and no post-run scope creep: Task 6.
- Focused and full verification with GitHub update: Task 7.

Placeholder scan:

- No task contains placeholder markers or unspecified future work.
- Each code-changing task includes failing tests, implementation snippets, focused commands, and commit commands.

Type consistency:

- `Path`, `Any`, `argparse.ArgumentParser`, `evaluate_apply_gate`, `validate_config_package`, `classify_runtime_condition`, and `lower_runtime_condition` match the current codebase.
- The new helpers are file-local private functions and do not create public API churn.

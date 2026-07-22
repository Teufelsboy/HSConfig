# HSConfig Config Proof Bundle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a compact diagnostic-only config proof summary to `hsconfig configure` so operators can verify the package is current, load-safe, no-default-only, source-contract disciplined, and not a hidden gameplay engine.

**Architecture:** Keep the existing single-apply-authority model unchanged: `reports/operator_summary.json` remains the only normal runtime apply authority. Add only a local `configure_summary.json.config_proof_summary` projection that compacts already-produced `operator_summary.json` and `config_quality_contract` evidence; it must not be read by `hsconfig apply`, `apply_gate`, or runtime writers.

**Tech Stack:** Python stdlib, existing `hsconfig` package, `pytest`, existing JSON report helpers, existing docs/skill sync tests.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig`.
- Run `git fetch --all --prune --tags` and `python scripts\check_hsconfig_currentness.py --cwd . --json` before runtime-facing work.
- Finish with a clean worktree; no backups, no generated runtime evidence committed.
- Do not use HSTuner, replay analysis, winrate analysis, runtime logs, or post-game tuning.
- Do not create another apply gate. `reports/operator_summary.json` remains the only normal apply authority.
- `SOURCE_BACKED_STRONG` is an evidence-quality label, not a generation or apply blocker.
- No hidden default-only runtime success: default-only runtime surfaces must be visible diagnostics.
- Normal HSConfig output stays limited to `GlobalValues.json`, `Mulligan.json`, per-card `<CARDID>.json`, and `Combo.json` only when a complete source-backed combo exists.
- `Presume.json`, `Concede.json`, and aggregate `CardBehavior.json` stay outside the normal HSConfig output path.
- Effect semantics are not opening-hand mulligan keeps; Darkbishop-style start-of-game effects must not become `Mulligan.json` keeps without explicit opening-hand source text.

---

## File Structure

- Modify `src/hsconfig/commands/configure.py`
  - Add `_build_config_proof_summary(...)`.
  - Add `config_proof_summary` to the existing `configure_summary.json` payload.
  - Keep this helper configure-local; no apply/import dependency.
- Modify `src/hsconfig/commands/configure.py`
  - Extend `_compact_config_quality_summary(...)` with selected existing check statuses needed by the proof summary.
- Modify `tests/test_configure_cli.py`
  - Add unit tests for clean proof summary, attention proof summary, and configure output.
  - Add boundary test proving `_build_config_proof_summary` is not imported by apply paths.
- Modify `src/hsconfig/contract_preflight.py`
  - Add docs/skill visibility check for `config_proof_summary`.
- Modify `tests/test_contract_preflight.py`
  - Add preflight expectation for proof summary visibility.
- Modify `docs/operator/README.md`
  - Tell operators to read `configure_summary.json.acceptance_summary` first, then `config_proof_summary` for diagnostic proof.
- Modify `.agents/skills/hsconfig/SKILL.md`
  - Sync the same operator rule into the installed skill.
- Optional if present in repo flow: run the existing skill sync/check script instead of manually duplicating text, but only if it preserves exact current wording.

---

### Task 1: Add Compact Quality Fields For Proof Projection

**Files:**
- Modify: `src/hsconfig/commands/configure.py`
- Test: `tests/test_configure_cli.py`

**Interfaces:**
- Consumes: `build_config_quality_report(package_dir: Path) -> dict[str, Any]`
- Produces: `_compact_config_quality_summary(report: Mapping[str, Any]) -> dict[str, Any]` with existing fields plus compact check status fields.

- [ ] **Step 1: Write the failing test for compact proof-ready quality fields**

Add this test near the existing `_compact_config_quality_summary` tests in `tests/test_configure_cli.py`:

```python
def test_compact_config_quality_summary_includes_proof_fields() -> None:
    report = {
        "status": "clean",
        "authority": "diagnostic_only",
        "apply_blocking": False,
        "runtime_write_performed": False,
        "problems": [],
        "checks": {
            "legacy_surfaces": {"present": []},
            "darkbishop_boundary": {
                "seen": True,
                "mulligan_keep_present": False,
                "effect_runtime_present": True,
            },
            "runtime_json": {
                "deck_dir_present": True,
                "metadata_leaks": [],
                "stray_cardid_files": [],
            },
            "source_to_runtime_explainability": {
                "present": True,
                "authority": "diagnostic_only",
                "apply_blocking": False,
            },
            "mechanic_runtime_discipline": {
                "status": "clean",
                "report_only_runtime_rows": [],
            },
            "semantic_intent_coverage": {
                "status": "clean",
                "first_attention": None,
            },
        },
    }

    assert _compact_config_quality_summary(report) == {
        "status": "clean",
        "authority": "diagnostic_only",
        "apply_blocking": False,
        "runtime_write_performed": False,
        "problem_count": 0,
        "problem_checks": [],
        "legacy_surfaces_present": [],
        "forbidden_normal_surfaces_absent": True,
        "darkbishop_boundary_status": "effect_without_mulligan_keep",
        "runtime_json_status": "clean",
        "source_to_runtime_status": "diagnostic_only",
        "mechanic_runtime_discipline_status": "clean",
        "semantic_intent_status": "clean",
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
pytest tests/test_configure_cli.py::test_compact_config_quality_summary_includes_proof_fields -q
```

Expected: FAIL because the new compact fields are missing.

- [ ] **Step 3: Implement minimal compact field extraction**

In `src/hsconfig/commands/configure.py`, update `_compact_config_quality_summary(...)` after the current semantic intent block:

```python
    checks = report.get("checks", {})
    if isinstance(checks, Mapping):
        legacy_surfaces = checks.get("legacy_surfaces")
        if isinstance(legacy_surfaces, Mapping):
            legacy_present = [
                str(surface)
                for surface in legacy_surfaces.get("present", [])
                if str(surface)
            ]
            summary["legacy_surfaces_present"] = legacy_present
            summary["forbidden_normal_surfaces_absent"] = not legacy_present

        darkbishop = checks.get("darkbishop_boundary")
        if isinstance(darkbishop, Mapping):
            mulligan_keep_present = bool(darkbishop.get("mulligan_keep_present"))
            effect_runtime_present = bool(darkbishop.get("effect_runtime_present"))
            if mulligan_keep_present:
                status = "mulligan_keep_present"
            elif effect_runtime_present:
                status = "effect_without_mulligan_keep"
            else:
                status = "not_seen"
            summary["darkbishop_boundary_status"] = status

        runtime_json = checks.get("runtime_json")
        if isinstance(runtime_json, Mapping):
            metadata_leaks = runtime_json.get("metadata_leaks", [])
            stray_cardid_files = runtime_json.get("stray_cardid_files", [])
            summary["runtime_json_status"] = (
                "clean" if not metadata_leaks and not stray_cardid_files else "attention"
            )

        explainability = checks.get("source_to_runtime_explainability")
        if isinstance(explainability, Mapping):
            if bool(explainability.get("present")):
                authority = str(explainability.get("authority") or "diagnostic_only")
                apply_blocking = bool(explainability.get("apply_blocking", False))
                summary["source_to_runtime_status"] = (
                    "diagnostic_only"
                    if authority == "diagnostic_only" and not apply_blocking
                    else "attention"
                )
            else:
                summary["source_to_runtime_status"] = "missing"

        mechanic = checks.get("mechanic_runtime_discipline")
        if isinstance(mechanic, Mapping):
            summary["mechanic_runtime_discipline_status"] = str(
                mechanic.get("status") or ""
            )
```

Keep the existing semantic intent extraction in the same `if isinstance(checks, Mapping):` block. Do not remove existing returned keys.

- [ ] **Step 4: Run focused tests**

Run:

```powershell
pytest tests/test_configure_cli.py::test_compact_config_quality_summary_includes_proof_fields tests/test_configure_cli.py::test_compact_config_quality_summary_includes_semantic_intent_when_present -q
```

Expected: both PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/hsconfig/commands/configure.py tests/test_configure_cli.py
git commit -m "feat: compact config quality proof fields"
```

---

### Task 2: Add Configure-Local Config Proof Summary

**Files:**
- Modify: `src/hsconfig/commands/configure.py`
- Test: `tests/test_configure_cli.py`

**Interfaces:**
- Consumes: `_compact_config_quality_summary(...)` output from Task 1.
- Produces: `_build_config_proof_summary(operator_summary: Mapping[str, Any], validate_status: int, apply_requested: bool, apply_status: int | None, config_quality_summary: Mapping[str, Any]) -> dict[str, Any]`
- Produces `configure_summary.json.config_proof_summary`.

- [ ] **Step 1: Write failing unit tests for clean and attention proof summaries**

Add these tests near the existing `_build_acceptance_summary` tests in `tests/test_configure_cli.py`:

```python
def test_build_config_proof_summary_reports_clean_diagnostic_proof() -> None:
    operator_summary = {
        "technical_status": "VALID_PACKAGE",
        "runtime_load_safe": True,
        "runtime_apply_allowed": True,
        "runtime_apply_mode": "load_safe_apply",
        "runtime_apply_contract": {
            "apply_authority": "reports/operator_summary.json",
        },
        "source_backed_status": "SOURCE_BACKED_STRONG",
        "source_status_apply_blocking": False,
        "first_missing_source_action": "none",
        "default_only_runtime_surfaces": [],
        "mechanic_visibility_summary": {
            "non_blocking": True,
            "first_warning_boundary": None,
        },
    }
    config_quality_summary = {
        "status": "clean",
        "authority": "diagnostic_only",
        "apply_blocking": False,
        "runtime_write_performed": False,
        "problem_count": 0,
        "problem_checks": [],
        "forbidden_normal_surfaces_absent": True,
        "legacy_surfaces_present": [],
        "darkbishop_boundary_status": "effect_without_mulligan_keep",
        "runtime_json_status": "clean",
        "source_to_runtime_status": "diagnostic_only",
        "mechanic_runtime_discipline_status": "clean",
        "semantic_intent_status": "clean",
    }

    assert _build_config_proof_summary(
        operator_summary=operator_summary,
        validate_status=0,
        apply_requested=False,
        apply_status=None,
        config_quality_summary=config_quality_summary,
    ) == {
        "schema_version": 1,
        "authority": "diagnostic_only",
        "apply_blocking": False,
        "runtime_write_performed": False,
        "normal_apply_authority": "reports/operator_summary.json",
        "technical_load_safe": True,
        "technical_status": "VALID_PACKAGE",
        "validation_status": "passed",
        "apply_requested": False,
        "apply_status": None,
        "source_strength": "SOURCE_BACKED_STRONG",
        "source_status_apply_blocking": False,
        "first_missing_source_action": "none",
        "no_default_only_clean": True,
        "default_only_runtime_surfaces": [],
        "forbidden_normal_surfaces_absent": True,
        "forbidden_normal_surfaces_present": [],
        "runtime_surface_boundary": [
            "GlobalValues.json",
            "Mulligan.json",
            "per-card <CARDID>.json",
            "Combo.json",
        ],
        "darkbishop_boundary_status": "effect_without_mulligan_keep",
        "mechanic_visibility_non_blocking": True,
        "first_warning_boundary": None,
        "runtime_json_status": "clean",
        "source_to_runtime_status": "diagnostic_only",
        "semantic_intent_status": "clean",
        "config_quality_status": "clean",
        "config_quality_problem_checks": [],
        "next_report_to_open": "reports/operator_summary.json",
    }


def test_build_config_proof_summary_surfaces_attention_without_blocking() -> None:
    operator_summary = {
        "technical_status": "VALID_PACKAGE",
        "runtime_load_safe": True,
        "runtime_apply_allowed": True,
        "runtime_apply_mode": "load_safe_apply",
        "runtime_apply_contract": {
            "apply_authority": "reports/operator_summary.json",
        },
        "source_backed_status": "SOURCE_BACKED_PARTIAL",
        "source_status_apply_blocking": False,
        "first_missing_source_action": "fetch_and_normalize_candidate_full_text_claims",
        "default_only_runtime_surfaces": ["Mulligan.json"],
        "mechanic_visibility_summary": {
            "non_blocking": True,
            "first_warning_boundary": {
                "mechanic": "location_activation",
                "boundary": "warning_only",
            },
        },
    }
    config_quality_summary = {
        "status": "attention",
        "authority": "diagnostic_only",
        "apply_blocking": False,
        "runtime_write_performed": False,
        "problem_count": 2,
        "problem_checks": [
            "operator_default_only_runtime_surfaces",
            "source_to_runtime_closure_rows_missing",
        ],
        "forbidden_normal_surfaces_absent": False,
        "legacy_surfaces_present": ["CustomConfig/deck/Presume.json"],
        "darkbishop_boundary_status": "mulligan_keep_present",
        "runtime_json_status": "attention",
        "source_to_runtime_status": "diagnostic_only",
        "mechanic_runtime_discipline_status": "attention",
        "semantic_intent_status": "attention",
    }

    summary = _build_config_proof_summary(
        operator_summary=operator_summary,
        validate_status=0,
        apply_requested=True,
        apply_status=0,
        config_quality_summary=config_quality_summary,
    )

    assert summary["apply_blocking"] is False
    assert summary["source_status_apply_blocking"] is False
    assert summary["no_default_only_clean"] is False
    assert summary["forbidden_normal_surfaces_absent"] is False
    assert summary["forbidden_normal_surfaces_present"] == [
        "CustomConfig/deck/Presume.json"
    ]
    assert summary["first_warning_boundary"] == {
        "mechanic": "location_activation",
        "boundary": "warning_only",
    }
    assert summary["next_report_to_open"] == "reports/contract_doctor.json"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
pytest tests/test_configure_cli.py::test_build_config_proof_summary_reports_clean_diagnostic_proof tests/test_configure_cli.py::test_build_config_proof_summary_surfaces_attention_without_blocking -q
```

Expected: FAIL because `_build_config_proof_summary` is not defined.

- [ ] **Step 3: Implement `_build_config_proof_summary`**

Add this helper below `_build_acceptance_summary(...)` in `src/hsconfig/commands/configure.py`:

```python
def _build_config_proof_summary(
    *,
    operator_summary: Mapping[str, Any],
    validate_status: int,
    apply_requested: bool,
    apply_status: int | None,
    config_quality_summary: Mapping[str, Any],
) -> dict[str, Any]:
    runtime_contract = operator_summary.get("runtime_apply_contract", {})
    if not isinstance(runtime_contract, Mapping):
        runtime_contract = {}

    mechanic_visibility = operator_summary.get("mechanic_visibility_summary", {})
    if not isinstance(mechanic_visibility, Mapping):
        mechanic_visibility = {}

    default_only_runtime_surfaces = [
        str(surface)
        for surface in operator_summary.get("default_only_runtime_surfaces", [])
        if str(surface)
    ]
    forbidden_surfaces = [
        str(surface)
        for surface in config_quality_summary.get("legacy_surfaces_present", [])
        if str(surface)
    ]
    problem_checks = [
        str(check)
        for check in config_quality_summary.get("problem_checks", [])
        if str(check)
    ]

    has_attention = bool(
        problem_checks
        or default_only_runtime_surfaces
        or forbidden_surfaces
        or str(config_quality_summary.get("status", "")) == "attention"
    )

    return {
        "schema_version": 1,
        "authority": "diagnostic_only",
        "apply_blocking": False,
        "runtime_write_performed": False,
        "normal_apply_authority": str(
            runtime_contract.get("apply_authority") or "reports/operator_summary.json"
        ),
        "technical_load_safe": bool(
            operator_summary.get("runtime_load_safe")
            or operator_summary.get("runtime_apply_allowed")
        ),
        "technical_status": str(operator_summary.get("technical_status", "")),
        "validation_status": "passed" if validate_status == 0 else "failed",
        "apply_requested": apply_requested,
        "apply_status": apply_status,
        "source_strength": str(operator_summary.get("source_backed_status", "")),
        "source_status_apply_blocking": bool(
            operator_summary.get("source_status_apply_blocking", False)
        ),
        "first_missing_source_action": operator_summary.get(
            "first_missing_source_action"
        ),
        "no_default_only_clean": not default_only_runtime_surfaces,
        "default_only_runtime_surfaces": default_only_runtime_surfaces,
        "forbidden_normal_surfaces_absent": not forbidden_surfaces,
        "forbidden_normal_surfaces_present": forbidden_surfaces,
        "runtime_surface_boundary": [
            "GlobalValues.json",
            "Mulligan.json",
            "per-card <CARDID>.json",
            "Combo.json",
        ],
        "darkbishop_boundary_status": str(
            config_quality_summary.get("darkbishop_boundary_status", "")
        ),
        "mechanic_visibility_non_blocking": bool(
            mechanic_visibility.get("non_blocking", True)
        ),
        "first_warning_boundary": mechanic_visibility.get("first_warning_boundary"),
        "runtime_json_status": str(config_quality_summary.get("runtime_json_status", "")),
        "source_to_runtime_status": str(
            config_quality_summary.get("source_to_runtime_status", "")
        ),
        "semantic_intent_status": str(
            config_quality_summary.get("semantic_intent_status", "")
        ),
        "config_quality_status": str(config_quality_summary.get("status", "")),
        "config_quality_problem_checks": problem_checks,
        "next_report_to_open": (
            "reports/contract_doctor.json"
            if has_attention
            else str(
                runtime_contract.get("apply_authority")
                or "reports/operator_summary.json"
            )
        ),
    }
```

- [ ] **Step 4: Add the new field to `configure_summary.json`**

In the `_finish(..., "OK", {...})` payload inside `run_configure_command(...)`, compute the acceptance summary once and add `config_proof_summary`:

```python
            "config_quality_summary": config_quality_summary,
            "acceptance_summary": _build_acceptance_summary(
                operator_summary=operator_summary,
                validate_status=validate_status,
                apply_requested=bool(getattr(args, "apply", False)),
                apply_status=apply_status,
                config_quality_summary=config_quality_summary,
            ),
            "config_proof_summary": _build_config_proof_summary(
                operator_summary=operator_summary,
                validate_status=validate_status,
                apply_requested=bool(getattr(args, "apply", False)),
                apply_status=apply_status,
                config_quality_summary=config_quality_summary,
            ),
```

If the surrounding dictionary already contains these keys, replace only that small block.

- [ ] **Step 5: Add configure output test**

Extend `test_configure_writes_diagnostic_config_quality_summary` in `tests/test_configure_cli.py` after the existing `acceptance_summary` assertions:

```python
    proof = summary["config_proof_summary"]
    assert proof["authority"] == "diagnostic_only"
    assert proof["apply_blocking"] is False
    assert proof["runtime_write_performed"] is False
    assert proof["normal_apply_authority"] == "reports/operator_summary.json"
    assert proof["technical_load_safe"] is True
    assert proof["no_default_only_clean"] is True
    assert proof["forbidden_normal_surfaces_absent"] is True
    assert proof["runtime_surface_boundary"] == [
        "GlobalValues.json",
        "Mulligan.json",
        "per-card <CARDID>.json",
        "Combo.json",
    ]
    assert "config_proof_summary" not in operator_summary
```

- [ ] **Step 6: Add boundary test that proof summary is configure-local**

Add this test next to `test_acceptance_summary_helper_stays_configure_local_projection`:

```python
def test_config_proof_summary_helper_stays_configure_local_projection() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    configure_source = (
        repo_root / "src" / "hsconfig" / "commands" / "configure.py"
    ).read_text(encoding="utf-8")
    apply_source = (
        repo_root / "src" / "hsconfig" / "commands" / "apply.py"
    ).read_text(encoding="utf-8")
    apply_gate_source = (
        repo_root / "src" / "hsconfig" / "apply_gate.py"
    ).read_text(encoding="utf-8")

    assert "def _build_config_proof_summary(" in configure_source
    assert "_build_config_proof_summary" not in apply_source
    assert "_build_config_proof_summary" not in apply_gate_source
```

- [ ] **Step 7: Run focused tests**

Run:

```powershell
pytest tests/test_configure_cli.py::test_build_config_proof_summary_reports_clean_diagnostic_proof tests/test_configure_cli.py::test_build_config_proof_summary_surfaces_attention_without_blocking tests/test_configure_cli.py::test_configure_writes_diagnostic_config_quality_summary tests/test_configure_cli.py::test_config_proof_summary_helper_stays_configure_local_projection -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```powershell
git add src/hsconfig/commands/configure.py tests/test_configure_cli.py
git commit -m "feat: add configure config proof summary"
```

---

### Task 3: Make Proof Summary Visible In Contract Preflight

**Files:**
- Modify: `src/hsconfig/contract_preflight.py`
- Test: `tests/test_contract_preflight.py`

**Interfaces:**
- Consumes: repository docs and installed skill text through existing `build_contract_preflight(repo_root: Path, git: GitPreflight | None = None) -> dict[str, Any]`.
- Produces: new `checks["config_proof_summary_visible"] -> bool`.

- [ ] **Step 1: Write failing preflight test**

Add to `test_contract_preflight_checks_configure_acceptance_route_contract` in `tests/test_contract_preflight.py`:

```python
    assert payload["checks"]["config_proof_summary_visible"] is True
    assert "config_proof_summary_visible" not in payload["failures"]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
pytest tests/test_contract_preflight.py::test_contract_preflight_checks_configure_acceptance_route_contract -q
```

Expected: FAIL because the check is not present or false.

- [ ] **Step 3: Add the preflight check**

In `src/hsconfig/contract_preflight.py`, add this helper near the other text-check helpers:

```python
def _config_proof_summary_visible(combined: str) -> bool:
    return (
        "config_proof_summary" in combined
        and "diagnostic-only config proof" in combined
        and "not another apply gate" in combined
    )
```

Then add this key inside the `checks = { ... }` mapping in `build_contract_preflight(...)`:

```python
        "config_proof_summary_visible": _config_proof_summary_visible(combined),
```

Do not add any runtime apply effect. This check is repository documentation/skill visibility only.

- [ ] **Step 4: Run focused preflight test**

Run:

```powershell
pytest tests/test_contract_preflight.py::test_contract_preflight_checks_configure_acceptance_route_contract -q
```

Expected: FAIL until Task 4 updates docs and skill text.

- [ ] **Step 5: Commit after Task 4**

Do not commit yet if the test is still failing. Commit this task together with Task 4 after docs make the check pass.

---

### Task 4: Update Operator Docs And Skill Wording

**Files:**
- Modify: `docs/operator/README.md`
- Modify: `.agents/skills/hsconfig/SKILL.md`
- Test: `tests/test_contract_preflight.py`
- Optional Test: `tests/test_skill_files.py`

**Interfaces:**
- Consumes: `configure_summary.json.acceptance_summary`
- Produces: documented operator rule for `configure_summary.json.config_proof_summary`

- [ ] **Step 1: Patch operator README wording**

In `docs/operator/README.md`, find the paragraph that tells operators to read `<out>/configure_summary.json.acceptance_summary` first. Extend it with this exact sentence:

```markdown
Then read `<out>/configure_summary.json.config_proof_summary` only as a diagnostic-only config proof: it compacts currentness, no-default-only visibility, source-to-runtime trace health, runtime-surface boundaries, warning-only mechanic visibility, and effect-not-mulligan canaries; it is not another apply gate and does not replace `reports/operator_summary.json`.
```

- [ ] **Step 2: Patch installed skill wording**

In `.agents/skills/hsconfig/SKILL.md`, find the same acceptance-summary operator rule. Extend it with this exact sentence:

```markdown
Then read `<out>/configure_summary.json.config_proof_summary` only as a diagnostic-only config proof: it compacts currentness, no-default-only visibility, source-to-runtime trace health, runtime-surface boundaries, warning-only mechanic visibility, and effect-not-mulligan canaries; it is not another apply gate and does not replace `reports/operator_summary.json`.
```

- [ ] **Step 3: Add docs/skill regression test if no existing one covers it**

If `tests/test_skill_files.py` has a combined docs/skill wording test near the acceptance-summary tests, add:

```python
def test_docs_and_skill_route_config_proof_summary_as_diagnostic_only() -> None:
    combined = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            Path("docs/operator/README.md"),
            Path(".agents/skills/hsconfig/SKILL.md"),
        )
    )

    assert "<out>/configure_summary.json.config_proof_summary" in combined
    assert "diagnostic-only config proof" in combined
    assert "not another apply gate" in combined
    assert "does not replace `reports/operator_summary.json`" in combined
```

If an equivalent docs/skill test already exists, extend it instead of adding a duplicate.

- [ ] **Step 4: Run focused docs/preflight tests**

Run:

```powershell
pytest tests/test_contract_preflight.py::test_contract_preflight_checks_configure_acceptance_route_contract tests/test_skill_files.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Tasks 3 and 4 together**

```powershell
git add src/hsconfig/contract_preflight.py tests/test_contract_preflight.py tests/test_skill_files.py docs/operator/README.md .agents/skills/hsconfig/SKILL.md
git commit -m "docs: surface config proof summary contract"
```

---

### Task 5: Final Verification And Clean Worktree

**Files:**
- No code changes expected in this task.
- Verify all files touched by Tasks 1-4.

**Interfaces:**
- Consumes: implementation commits from Tasks 1-4.
- Produces: verified clean repo state.

- [ ] **Step 1: Run currentness check**

Run:

```powershell
git fetch --all --prune --tags
python scripts\check_hsconfig_currentness.py --cwd . --json
```

Expected JSON must include:

```json
{
  "behind_origin_main": 0,
  "dirty": false,
  "clean_for_runtime_work": true
}
```

If `dirty` is true because Task 5 runs before commits, continue after tests and verify clean again after committing.

- [ ] **Step 2: Run targeted tests**

Run:

```powershell
pytest tests/test_configure_cli.py tests/test_contract_preflight.py tests/test_config_quality_contract.py tests/test_apply_authority_boundary.py tests/test_universal_wild_no_block_matrix.py -q
```

Expected: PASS.

- [ ] **Step 3: Run contract diagnostics**

Run:

```powershell
python -m hsconfig.cli contract-preflight --repo . --json
python -m hsconfig.cli contract-spine-sentinel --json
```

Expected:

```text
contract-preflight: status PASS
contract-spine-sentinel: status PASS
```

Exact JSON formatting may differ; verify both commands return exit code `0` and no failure list.

- [ ] **Step 4: Verify no apply-boundary regression**

Run:

```powershell
rg -n "_build_config_proof_summary|config_proof_summary" src\hsconfig\commands\apply.py src\hsconfig\apply_gate.py
```

Expected: no matches.

Run:

```powershell
rg -n "config_proof_summary" src\hsconfig\commands\configure.py docs\operator\README.md .agents\skills\hsconfig\SKILL.md tests
```

Expected: matches only in configure, docs/skill wording, and tests.

- [ ] **Step 5: Final git status**

Run:

```powershell
git status --short --branch
```

Expected:

```text
## codex/hsconfig-semantic-intent-scoring...origin/codex/hsconfig-semantic-intent-scoring
```

No uncommitted files should appear.

---

## Self-Review

- Spec coverage: The plan implements only a compact diagnostic proof projection. It does not add gameplay sequencing, HSTuner, logs, replay tuning, second apply gates, or new runtime surfaces.
- Placeholder scan: No placeholder markers or unspecified implementation steps are present.
- Type consistency: The new helper consumes `Mapping[str, Any]` like `_build_acceptance_summary`; it returns a plain `dict[str, Any]` and remains local to `configure.py`.
- Risk: The only schema expansion is additive under `configure_summary.json.config_proof_summary`. Existing `operator_summary.json` and runtime apply paths remain unchanged.

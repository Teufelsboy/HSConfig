# HSConfig Config Intent Self Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a small diagnostic-only self-audit that proves each generated HSConfig runtime file is intentionally explained by source, contract, deck identity, or an explicit suppression/default-visible reason.

**Architecture:** Extend the existing `config_quality_contract` diagnostic path with a `config_intent_self_audit` check, then project the compact result into `configure_summary.json` through the existing `config_quality_summary`, `config_proof_summary`, and `handoff_contract` helpers. Keep `reports/operator_summary.json` as the only normal runtime apply authority; the new audit never blocks valid package generation or runtime apply.

**Tech Stack:** Python 3.11+, pytest, existing HSConfig JSON report helpers, existing `hsconfig configure` and `contract-doctor` commands.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig`.
- Run `git fetch --all --prune --tags` and `python scripts\check_hsconfig_currentness.py --cwd . --json` before runtime-facing implementation work.
- End with a clean git worktree; no backups, temp copies, runtime logs, or generated output folders committed.
- Do not inspect gameplay logs for this task.
- Do not use or propose HSTuner.
- Do not add a gameplay sequencing engine.
- Do not add a second apply gate.
- Do not change `hsconfig apply`, `apply_gate.py`, `runtime_apply.py`, or runtime receipt semantics.
- `reports/operator_summary.json` remains the only normal runtime apply authority.
- `SOURCE_BACKED_STRONG` remains an evidence-quality label, not a runtime generation or apply gate.
- `source_status_apply_blocking` must remain `false` for source-quality gaps.
- Normal runtime surfaces remain `GlobalValues.json`, `Mulligan.json`, per-card `<CARDID>.json`, and `Combo.json` only for a complete source-backed combo.
- `Presume.json`, `Concede.json`, and aggregate `CardBehavior.json` stay outside the normal HSConfig output path.
- Darkbishop Benedictus effect semantics must not imply opening-hand Mulligan keep without explicit opening-hand source evidence.

---

## File Structure

- Modify: `src/hsconfig/config_quality_contract.py`
  - Add the detailed `config_intent_self_audit` diagnostic check.
  - Reuse existing readers, runtime-file scanners, deck identity, explainability, and operator summary data.
  - Add problems only as non-blocking diagnostic quality problems.

- Modify: `src/hsconfig/commands/configure.py`
  - Extend compact summary projections with `config_intent_self_audit_status` and first attention fields.
  - Keep the helper local to configure summary projection.

- Modify: `tests/test_config_quality_contract.py`
  - Add focused unit coverage for clean and attention self-audit cases.

- Modify: `tests/test_configure_cli.py`
  - Add compact summary, config proof, and configure output assertions for the new self-audit projection.

- Modify: `tests/test_contract_doctor.py`
  - Add markdown coverage so `contract-doctor` exposes the new diagnostic in the existing Config Quality section.

- Modify: `docs/operator/README.md`
  - Document the operator interpretation of `config_intent_self_audit`.

- Modify: `.agents/skills/hsconfig/SKILL.md`
  - Update the source skill instructions so future Codex runs know where to read the new diagnostic.

- Modify: `.agents/skills/hsconfig/references/workflow.md`
  - Add one line to the normal workflow reference.

- Modify: `tests/test_skill_sync.py`
  - Extend the sync test to confirm installed skill copies include the new guidance.

---

### Task 1: Detailed Config Intent Self-Audit Report

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_config_quality_contract.py`
- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\config_quality_contract.py`

**Interfaces:**
- Consumes: `build_config_quality_report(package: str | Path) -> dict[str, Any]`
- Produces: `report["checks"]["config_intent_self_audit"]`
- Produces helper: `_config_intent_self_audit_check(package: Path, operator: Mapping[str, Any], deck_identity: Mapping[str, Any], card_behavior: Mapping[str, Any], explainability: Mapping[str, Any]) -> dict[str, Any]`

- [ ] **Step 1: Write failing clean self-audit test**

Append this test to `tests/test_config_quality_contract.py`:

```python
def test_config_quality_exposes_clean_config_intent_self_audit(tmp_path: Path):
    package = minimal_clean_package(tmp_path)

    report = build_config_quality_report(package)

    audit = report["checks"]["config_intent_self_audit"]
    assert audit["schema_version"] == 1
    assert audit["authority"] == "diagnostic_only"
    assert audit["apply_blocking"] is False
    assert audit["runtime_write_performed"] is False
    assert audit["status"] == "clean"
    assert audit["normal_apply_authority"] == "reports/operator_summary.json"
    assert audit["runtime_surface_boundary"] == [
        "GlobalValues.json",
        "Mulligan.json",
        "per-card <CARDID>.json",
        "Combo.json",
    ]
    assert audit["runtime_files_total"] == 3
    assert audit["runtime_files_without_intent"] == []
    assert audit["unsupported_runtime_files"] == []
    assert audit["default_only_runtime_surfaces"] == []
    assert audit["source_status_apply_blocking"] is False
    assert audit["attention"] == []
    assert audit["first_attention"] is None
```

- [ ] **Step 2: Write failing attention self-audit test**

Append this test to `tests/test_config_quality_contract.py`:

```python
def test_config_quality_flags_runtime_file_without_intent_in_self_audit(
    tmp_path: Path,
):
    package = minimal_clean_package(tmp_path)
    write_json(
        package / "CustomConfig" / DECK_SLUG / "UNTRACED_001.json",
        {
            "GameCardId": "UNTRACED_001",
            "BeforePlayCardBonus": {
                "values": [
                    {
                        "comment": "unexpected untraced runtime file",
                        "condition": "*",
                        "value": "6",
                    }
                ]
            },
        },
    )

    report = build_config_quality_report(package)

    audit = report["checks"]["config_intent_self_audit"]
    assert audit["status"] == "attention"
    assert audit["runtime_files_total"] == 4
    assert audit["runtime_files_without_intent"] == [
        "CustomConfig/shadowpriest/UNTRACED_001.json"
    ]
    assert audit["unsupported_runtime_files"] == []
    assert audit["first_attention"] == "runtime_file_without_intent"
    assert {
        "check": "runtime_file_without_intent",
        "count": 1,
    } in audit["attention"]
    assert {
        "check": "config_intent_runtime_file_without_intent",
        "value": ["CustomConfig/shadowpriest/UNTRACED_001.json"],
    } in report["problems"]
    assert report["apply_blocking"] is False
```

- [ ] **Step 3: Run focused tests and confirm they fail**

Run:

```powershell
python -m pytest tests\test_config_quality_contract.py::test_config_quality_exposes_clean_config_intent_self_audit tests\test_config_quality_contract.py::test_config_quality_flags_runtime_file_without_intent_in_self_audit -q -p no:cacheprovider
```

Expected: both tests fail with `KeyError: 'config_intent_self_audit'`.

- [ ] **Step 4: Add constants and wire the check**

In `src/hsconfig/config_quality_contract.py`, add these constants near `SPECIAL_RUNTIME_FILES`:

```python
NORMAL_RUNTIME_SURFACE_BOUNDARY = [
    "GlobalValues.json",
    "Mulligan.json",
    "per-card <CARDID>.json",
    "Combo.json",
]
STANDARD_SURFACE_ALIASES = {
    "globalvalues": "GlobalValues.json",
    "global_values": "GlobalValues.json",
    "GlobalValues.json": "GlobalValues.json",
    "mulligan": "Mulligan.json",
    "Mulligan.json": "Mulligan.json",
    "combo": "Combo.json",
    "Combo.json": "Combo.json",
    "cardid": "per-card <CARDID>.json",
    "cardid_behavior": "per-card <CARDID>.json",
    "CARDID.json": "per-card <CARDID>.json",
}
```

Then extend the `checks = { ... }` block in `build_config_quality_report()` after `darkbishop_boundary`:

```python
        "config_intent_self_audit": _config_intent_self_audit_check(
            package=package,
            operator=operator,
            deck_identity=deck_identity,
            card_behavior=card_behavior,
            explainability=explainability,
        ),
```

- [ ] **Step 5: Add helper functions**

Add these helpers in `src/hsconfig/config_quality_contract.py` before `_problems()`:

```python
def _config_intent_self_audit_check(
    *,
    package: Path,
    operator: Mapping[str, Any],
    deck_identity: Mapping[str, Any],
    card_behavior: Mapping[str, Any],
    explainability: Mapping[str, Any],
) -> dict[str, Any]:
    runtime_files = _runtime_files_from_custom_config(package)
    explained_files = _explained_runtime_files_from_reports(
        operator=operator,
        card_behavior=card_behavior,
        explainability=explainability,
    )
    deck_card_ids = _deck_identity_card_ids(deck_identity)
    default_only_runtime_surfaces = [
        str(surface)
        for surface in operator.get("default_only_runtime_surfaces", [])
        if str(surface)
    ]
    unsupported_runtime_files = [
        item
        for item in runtime_files
        if Path(item).name in FORBIDDEN_LEGACY_RUNTIME_SURFACES
    ]

    runtime_files_without_intent: list[str] = []
    for runtime_file in runtime_files:
        basename = Path(runtime_file).name
        card_id = _file_card_id(basename)
        if basename in {"GlobalValues.json", "Mulligan.json"}:
            if basename in explained_files:
                continue
        elif basename == "Combo.json":
            if basename in explained_files:
                continue
        elif card_id and (basename in explained_files or card_id in deck_card_ids):
            continue
        runtime_files_without_intent.append(runtime_file)

    attention: list[dict[str, Any]] = []
    if runtime_files_without_intent:
        attention.append(
            {
                "check": "runtime_file_without_intent",
                "count": len(runtime_files_without_intent),
            }
        )
    if unsupported_runtime_files:
        attention.append(
            {
                "check": "unsupported_runtime_file",
                "count": len(unsupported_runtime_files),
            }
        )
    if default_only_runtime_surfaces:
        attention.append(
            {
                "check": "default_only_runtime_surface",
                "count": len(default_only_runtime_surfaces),
            }
        )
    if bool(operator.get("source_status_apply_blocking", False)):
        attention.append(
            {
                "check": "source_status_apply_blocking",
                "count": 1,
            }
        )

    return {
        "schema_version": 1,
        "authority": "diagnostic_only",
        "apply_blocking": False,
        "runtime_write_performed": False,
        "status": "clean" if not attention else "attention",
        "normal_apply_authority": _normal_apply_authority(operator),
        "runtime_surface_boundary": NORMAL_RUNTIME_SURFACE_BOUNDARY,
        "runtime_files_total": len(runtime_files),
        "runtime_files_without_intent": runtime_files_without_intent,
        "unsupported_runtime_files": unsupported_runtime_files,
        "default_only_runtime_surfaces": default_only_runtime_surfaces,
        "source_status_apply_blocking": bool(
            operator.get("source_status_apply_blocking", False)
        ),
        "attention": attention,
        "first_attention": attention[0]["check"] if attention else None,
    }


def _normal_apply_authority(operator: Mapping[str, Any]) -> str:
    contract = operator.get("runtime_apply_contract", {})
    if isinstance(contract, Mapping):
        authority = str(contract.get("apply_authority", "")).strip()
        if authority:
            return authority
    return "reports/operator_summary.json"


def _runtime_files_from_custom_config(package: Path) -> list[str]:
    files: list[str] = []
    custom_config = package / "CustomConfig"
    if not custom_config.is_dir():
        return files
    for path in sorted(custom_config.rglob("*.json")):
        files.append(_relative(path, package))
    return files


def _explained_runtime_files_from_reports(
    *,
    operator: Mapping[str, Any],
    card_behavior: Mapping[str, Any],
    explainability: Mapping[str, Any],
) -> set[str]:
    explained: set[str] = set()

    for row in _report_rows(explainability, ("claim_rows", "card_rows")):
        explained.update(Path(item).name for item in _string_list(row.get("emitted_runtime_files")))
        explained.update(Path(item).name for item in _string_list(row.get("runtime_surfaces")))
        closure = row.get("closure")
        if isinstance(closure, Mapping):
            explained.update(
                Path(item).name for item in _string_list(closure.get("runtime_surfaces"))
            )
        evidence_chain = row.get("evidence_chain", [])
        if isinstance(evidence_chain, list):
            for item in evidence_chain:
                if not isinstance(item, Mapping):
                    continue
                explained.update(
                    Path(value).name for value in _string_list(item.get("runtime_files"))
                )

    for row in _meaningful_cardid_rows(card_behavior):
        card_id = _row_card_id(row)
        if card_id:
            explained.add(f"{card_id}.json")

    surface_rows = operator.get("surface_status_ledger", [])
    if isinstance(surface_rows, list):
        for row in surface_rows:
            if not isinstance(row, Mapping):
                continue
            status = str(row.get("status", "")).strip()
            if status not in {"emitted", "source_backed", "policy_backed", "static_semantics"}:
                continue
            surface = _standard_surface_name(row.get("surface"))
            if surface == "per-card <CARDID>.json":
                explained.add(surface)
            elif surface:
                explained.add(surface)

    return explained


def _standard_surface_name(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return STANDARD_SURFACE_ALIASES.get(text, text)
```

- [ ] **Step 6: Add non-blocking problems**

In `_problems(checks: dict[str, Any])`, after the `legacy` check and before `darkbishop`, add:

```python
    config_intent = checks["config_intent_self_audit"]
    if config_intent["runtime_files_without_intent"]:
        problems.append(
            {
                "check": "config_intent_runtime_file_without_intent",
                "value": config_intent["runtime_files_without_intent"],
            }
        )
    if config_intent["unsupported_runtime_files"]:
        problems.append(
            {
                "check": "config_intent_unsupported_runtime_files",
                "value": config_intent["unsupported_runtime_files"],
            }
        )
```

- [ ] **Step 7: Run focused tests and confirm they pass**

Run:

```powershell
python -m pytest tests\test_config_quality_contract.py::test_config_quality_exposes_clean_config_intent_self_audit tests\test_config_quality_contract.py::test_config_quality_flags_runtime_file_without_intent_in_self_audit -q -p no:cacheprovider
```

Expected: `2 passed`.

- [ ] **Step 8: Run existing config-quality suite**

Run:

```powershell
python -m pytest tests\test_config_quality_contract.py -q -p no:cacheprovider
```

Expected: all tests in `tests/test_config_quality_contract.py` pass.

- [ ] **Step 9: Commit Task 1**

Run:

```powershell
git add src\hsconfig\config_quality_contract.py tests\test_config_quality_contract.py
git commit -m "feat: add config intent self audit"
```

Expected: commit succeeds and includes only these two files.

---

### Task 2: Configure Summary Projection

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_configure_cli.py`
- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\commands\configure.py`

**Interfaces:**
- Consumes: `_compact_config_quality_summary(report: Mapping[str, Any]) -> dict[str, Any]`
- Consumes: `_build_config_proof_summary(...) -> dict[str, Any]`
- Consumes: `_build_handoff_contract(...) -> dict[str, Any]`
- Produces: `configure_summary.json.config_quality_summary.config_intent_self_audit_status`
- Produces: `configure_summary.json.config_proof_summary.config_intent_self_audit_status`
- Produces: `configure_summary.json.handoff_contract.config_intent_self_audit_status`

- [ ] **Step 1: Write compact summary test**

Append this test near the other `_compact_config_quality_summary` tests in `tests/test_configure_cli.py`:

```python
def test_compact_config_quality_summary_includes_config_intent_self_audit() -> None:
    report = {
        "status": "attention",
        "authority": "diagnostic_only",
        "apply_blocking": False,
        "runtime_write_performed": False,
        "problems": [],
        "checks": {
            "config_intent_self_audit": {
                "status": "attention",
                "first_attention": "runtime_file_without_intent",
                "runtime_files_total": 4,
                "runtime_files_without_intent": [
                    "CustomConfig/shadowpriest/UNTRACED_001.json"
                ],
                "unsupported_runtime_files": [],
                "default_only_runtime_surfaces": [],
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
        "config_intent_self_audit_status": "attention",
        "config_intent_first_attention": "runtime_file_without_intent",
        "config_intent_runtime_files_total": 4,
        "config_intent_runtime_files_without_intent": 1,
        "config_intent_unsupported_runtime_files": [],
        "config_intent_default_only_runtime_surfaces": [],
    }
```

- [ ] **Step 2: Write config proof projection assertions**

In `test_build_config_proof_summary_reports_clean_diagnostic_proof()`, add this to `config_quality_summary`:

```python
        "config_intent_self_audit_status": "clean",
        "config_intent_first_attention": None,
        "config_intent_runtime_files_total": 3,
        "config_intent_runtime_files_without_intent": 0,
```

Then add these assertions after the existing `semantic_intent_status` assertion:

```python
    assert summary["config_intent_self_audit_status"] == "clean"
    assert summary["config_intent_first_attention"] is None
    assert summary["config_intent_runtime_files_without_intent"] == 0
```

In `test_build_config_proof_summary_surfaces_attention_without_blocking()`, add this to `config_quality_summary`:

```python
        "config_intent_self_audit_status": "attention",
        "config_intent_first_attention": "runtime_file_without_intent",
        "config_intent_runtime_files_total": 4,
        "config_intent_runtime_files_without_intent": 1,
```

Then add these assertions:

```python
    assert summary["config_intent_self_audit_status"] == "attention"
    assert summary["config_intent_first_attention"] == "runtime_file_without_intent"
    assert summary["config_intent_runtime_files_without_intent"] == 1
```

- [ ] **Step 3: Write handoff projection assertion**

In `test_configure_writes_diagnostic_config_quality_summary()`, extend the mocked `clean_report()` return value to include:

```python
        "checks": {
            "config_intent_self_audit": {
                "status": "clean",
                "first_attention": None,
                "runtime_files_total": 3,
                "runtime_files_without_intent": [],
                "unsupported_runtime_files": [],
                "default_only_runtime_surfaces": [],
            }
        },
```

Then extend the expected `summary["config_quality_summary"]` dict with:

```python
        "config_intent_self_audit_status": "clean",
        "config_intent_runtime_files_total": 3,
        "config_intent_runtime_files_without_intent": 0,
        "config_intent_unsupported_runtime_files": [],
        "config_intent_default_only_runtime_surfaces": [],
```

Then add:

```python
    assert proof["config_intent_self_audit_status"] == "clean"
    assert proof["config_intent_runtime_files_without_intent"] == 0
    assert handoff["config_intent_self_audit_status"] == "clean"
    assert handoff["config_intent_runtime_files_without_intent"] == 0
```

- [ ] **Step 4: Run projection tests and confirm they fail**

Run:

```powershell
python -m pytest tests\test_configure_cli.py::test_compact_config_quality_summary_includes_config_intent_self_audit tests\test_configure_cli.py::test_build_config_proof_summary_reports_clean_diagnostic_proof tests\test_configure_cli.py::test_build_config_proof_summary_surfaces_attention_without_blocking tests\test_configure_cli.py::test_configure_writes_diagnostic_config_quality_summary -q -p no:cacheprovider
```

Expected: at least the new compact summary test fails because the projection keys are absent.

- [ ] **Step 5: Extend `_compact_config_quality_summary()`**

In `src/hsconfig/commands/configure.py`, inside `_compact_config_quality_summary()` under `if isinstance(checks, Mapping):`, add this block after the `semantic_intent` block:

```python
        config_intent = checks.get("config_intent_self_audit")
        if isinstance(config_intent, Mapping):
            summary["config_intent_self_audit_status"] = str(
                config_intent.get("status") or ""
            )
            first_attention = config_intent.get("first_attention")
            if first_attention is not None:
                summary["config_intent_first_attention"] = str(first_attention)
            summary["config_intent_runtime_files_total"] = int(
                config_intent.get("runtime_files_total") or 0
            )
            summary["config_intent_runtime_files_without_intent"] = len(
                [
                    item
                    for item in config_intent.get("runtime_files_without_intent", [])
                    if str(item)
                ]
            )
            summary["config_intent_unsupported_runtime_files"] = [
                str(item)
                for item in config_intent.get("unsupported_runtime_files", [])
                if str(item)
            ]
            summary["config_intent_default_only_runtime_surfaces"] = [
                str(item)
                for item in config_intent.get("default_only_runtime_surfaces", [])
                if str(item)
            ]
```

- [ ] **Step 6: Extend `_build_config_proof_summary()`**

In `_build_config_proof_summary()`, add these keys to the returned dict near `semantic_intent_status`:

```python
        "config_intent_self_audit_status": str(
            config_quality_summary.get("config_intent_self_audit_status", "")
        ),
        "config_intent_first_attention": (
            str(config_quality_summary.get("config_intent_first_attention"))
            if config_quality_summary.get("config_intent_first_attention") is not None
            else None
        ),
        "config_intent_runtime_files_without_intent": int(
            config_quality_summary.get("config_intent_runtime_files_without_intent") or 0
        ),
```

Then update `has_attention = bool(...)` to include:

```python
        or str(config_quality_summary.get("config_intent_self_audit_status", ""))
        == "attention"
```

- [ ] **Step 7: Extend `_build_handoff_contract()`**

In `_build_handoff_contract()`, add these keys to the returned dict near `semantic_intent_status`:

```python
        "config_intent_self_audit_status": str(
            config_proof_summary.get("config_intent_self_audit_status") or ""
        ),
        "config_intent_first_attention": (
            str(config_proof_summary.get("config_intent_first_attention"))
            if config_proof_summary.get("config_intent_first_attention") is not None
            else None
        ),
        "config_intent_runtime_files_without_intent": int(
            config_proof_summary.get("config_intent_runtime_files_without_intent") or 0
        ),
```

Also add this condition to the `status = "clean" if (...) else "attention"` expression:

```python
            and str(config_proof_summary.get("config_intent_self_audit_status") or "")
            in {"", "clean"}
            and int(config_proof_summary.get("config_intent_runtime_files_without_intent") or 0)
            == 0
```

- [ ] **Step 8: Run projection tests and confirm they pass**

Run:

```powershell
python -m pytest tests\test_configure_cli.py::test_compact_config_quality_summary_includes_config_intent_self_audit tests\test_configure_cli.py::test_build_config_proof_summary_reports_clean_diagnostic_proof tests\test_configure_cli.py::test_build_config_proof_summary_surfaces_attention_without_blocking tests\test_configure_cli.py::test_configure_writes_diagnostic_config_quality_summary -q -p no:cacheprovider
```

Expected: selected tests pass.

- [ ] **Step 9: Run configure CLI suite**

Run:

```powershell
python -m pytest tests\test_configure_cli.py tests\test_configure_handoff_contract.py -q -p no:cacheprovider
```

Expected: both test files pass.

- [ ] **Step 10: Commit Task 2**

Run:

```powershell
git add src\hsconfig\commands\configure.py tests\test_configure_cli.py
git commit -m "feat: project config intent audit in configure summary"
```

Expected: commit succeeds and does not stage unrelated files.

---

### Task 3: Contract Doctor and Operator Documentation

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_contract_doctor.py`
- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\contract_doctor.py`
- Modify: `C:\Users\darbo\Documents\HSConfig\docs\operator\README.md`
- Modify: `C:\Users\darbo\Documents\HSConfig\.agents\skills\hsconfig\SKILL.md`
- Modify: `C:\Users\darbo\Documents\HSConfig\.agents\skills\hsconfig\references\workflow.md`
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_skill_sync.py`

**Interfaces:**
- Consumes: `build_contract_doctor_report(package: Path) -> dict[str, Any]`
- Consumes: `render_contract_doctor_markdown(report: Mapping[str, Any]) -> str`
- Produces markdown lines in `## Config Quality` for the self-audit.

- [ ] **Step 1: Write contract-doctor markdown test**

In `tests/test_contract_doctor.py`, extend `test_contract_doctor_markdown_includes_config_quality_section()` by adding this to `report["config_quality"]["checks"]`:

```python
                "config_intent_self_audit": {
                    "status": "attention",
                    "first_attention": "runtime_file_without_intent",
                    "runtime_files_total": 4,
                    "runtime_files_without_intent": [
                        "CustomConfig/shadowpriest/UNTRACED_001.json"
                    ],
                    "unsupported_runtime_files": [],
                    "default_only_runtime_surfaces": [],
                },
```

Then add these assertions:

```python
    assert "- Config intent self-audit: attention" in lines
    assert "- Config intent first attention: runtime_file_without_intent" in lines
    assert "- Config intent runtime files without intent: 1" in lines
```

- [ ] **Step 2: Run contract-doctor markdown test and confirm it fails**

Run:

```powershell
python -m pytest tests\test_contract_doctor.py::test_contract_doctor_markdown_includes_config_quality_section -q -p no:cacheprovider
```

Expected: fail because the new markdown lines are absent.

- [ ] **Step 3: Extend contract-doctor markdown rendering**

In `src/hsconfig/contract_doctor.py`, find the `## Config Quality` render block and add:

```python
    config_intent = checks.get("config_intent_self_audit", {})
    if isinstance(config_intent, Mapping):
        lines.append(
            f"- Config intent self-audit: {config_intent.get('status', '')}"
        )
        first_attention = config_intent.get("first_attention")
        if first_attention is not None:
            lines.append(
                f"- Config intent first attention: {first_attention}"
            )
        runtime_files_without_intent = config_intent.get(
            "runtime_files_without_intent", []
        )
        runtime_files_without_intent_count = (
            len(runtime_files_without_intent)
            if isinstance(runtime_files_without_intent, list)
            else 0
        )
        lines.append(
            "- Config intent runtime files without intent: "
            f"{runtime_files_without_intent_count}"
        )
```

Keep this inside the diagnostic-only Config Quality section; do not add apply permission language.

- [ ] **Step 4: Run contract-doctor tests**

Run:

```powershell
python -m pytest tests\test_contract_doctor.py -q -p no:cacheprovider
```

Expected: all `contract_doctor` tests pass.

- [ ] **Step 5: Update operator docs**

In `docs/operator/README.md`, after the paragraph that starts with `` `<out>/configure_summary.json.config_quality_summary` remains``, add:

```markdown
`config_intent_self_audit` is a diagnostic-only proof that generated runtime files are intentionally explained by `operator_summary.json`, source-to-runtime explainability, deck identity, or explicit non-blocking default/suppression visibility. If its status is `attention`, the package can still be technically usable through `reports/operator_summary.json`, but inspect `reports/contract_doctor.json` or run `hsconfig contract-doctor --package <04_package> --json` before calling the config qualitatively complete.
```

- [ ] **Step 6: Update repo skill guidance**

In `.agents/skills/hsconfig/SKILL.md`, extend the existing config-quality sentence with this exact sentence:

```markdown
`config_intent_self_audit` is diagnostic-only proof that runtime files are explained by source/contract, deck identity, or visible suppression/default status; it must not replace `operator_summary.json` or block valid load-safe packages.
```

In `.agents/skills/hsconfig/references/workflow.md`, add this sentence after the current configure-summary paragraph:

```markdown
`config_intent_self_audit` is part of the config-quality diagnostic path and verifies runtime-file intent without creating a gameplay sequencing engine or a second runtime apply authority.
```

- [ ] **Step 7: Update skill sync test**

In `tests/test_skill_sync.py`, inside `test_skill_sync_propagates_source_backed_closure_guidance()`, add:

```python
    assert "config_intent_self_audit" in skill_text
    assert "runtime-file intent" in (
        installed_root / "references" / "workflow.md"
    ).read_text(encoding="utf-8")
```

- [ ] **Step 8: Run docs and skill sync tests**

Run:

```powershell
python -m pytest tests\test_contract_doctor.py tests\test_docs_active_path.py tests\test_skill_sync.py -q -p no:cacheprovider
```

Expected: all selected tests pass.

- [ ] **Step 9: Sync installed skill**

Run:

```powershell
python scripts\sync_installed_skill.py --install-root "C:\Users\darbo\.codex\skills"
python scripts\sync_installed_skill.py --check --install-root "C:\Users\darbo\.codex\skills"
```

Expected:

```text
HSConfig skill is in sync: C:\Users\darbo\.codex\skills\hsconfig
```

- [ ] **Step 10: Commit Task 3**

Run:

```powershell
git add src\hsconfig\contract_doctor.py tests\test_contract_doctor.py docs\operator\README.md .agents\skills\hsconfig\SKILL.md .agents\skills\hsconfig\references\workflow.md tests\test_skill_sync.py
git commit -m "docs: document config intent self audit"
```

Expected: commit succeeds and does not include installed skill files from `C:\Users\darbo\.codex\skills`.

---

### Task 4: End-to-End Verification and Cleanliness

**Files:**
- No code files modified in this task.

**Interfaces:**
- Consumes: all changes from Tasks 1-3.
- Produces: verified clean branch with tests passing and currentness report clean.

- [ ] **Step 1: Run focused regression suite**

Run:

```powershell
python -m pytest tests\test_config_quality_contract.py tests\test_configure_cli.py tests\test_configure_handoff_contract.py tests\test_contract_doctor.py tests\test_skill_sync.py -q -p no:cacheprovider
```

Expected: all selected tests pass.

- [ ] **Step 2: Run contract boundary regression suite**

Run:

```powershell
python -m pytest tests\test_claim_kind_runtime_contract.py tests\test_no_second_gate_contract.py tests\test_source_to_runtime_explainability.py tests\test_shadowpriest_fresh_closure_proof.py tests\test_universal_wild_no_block_matrix.py -q -p no:cacheprovider
```

Expected: all selected tests pass; no test asserts `config_intent_self_audit` as an apply gate.

- [ ] **Step 3: Run static currentness and contract preflight**

Run:

```powershell
python scripts\check_hsconfig_currentness.py --cwd . --json
python -m hsconfig contract-preflight --json
```

Expected:

```json
"behind_origin_main": 0
"dirty": false
"clean_for_runtime_work": true
```

Expected from `contract-preflight`: status is diagnostic-only and does not report installed skill drift after the sync in Task 3.

- [ ] **Step 4: Confirm no forbidden files are tracked**

Run:

```powershell
git status --short --branch
git diff --name-only HEAD
git ls-files | Select-String -Pattern "Power\.log|\.hdtreplay|\.hsreplay|BotPlayHistory\.log|CustomConfig\\\\.*runtime|outputs\\\\"
```

Expected:

```text
## codex/hsconfig-semantic-intent-scoring...origin/codex/hsconfig-semantic-intent-scoring
```

Expected: `git diff --name-only HEAD` prints nothing after the final commit. The `git ls-files` command prints no private runtime evidence files.

- [ ] **Step 5: Final commit if Task 4 found small doc/test drift**

If Task 4 required no edits, skip this step. If Task 4 required a narrow correction, run this exact scoped staging command:

```powershell
git add src\hsconfig\config_quality_contract.py src\hsconfig\commands\configure.py src\hsconfig\contract_doctor.py tests\test_config_quality_contract.py tests\test_configure_cli.py tests\test_configure_handoff_contract.py tests\test_contract_doctor.py tests\test_skill_sync.py docs\operator\README.md .agents\skills\hsconfig\SKILL.md .agents\skills\hsconfig\references\workflow.md
git commit -m "test: verify config intent self audit"
```

Expected: final commit succeeds if any listed tracked files changed. If Git prints `nothing to commit, working tree clean`, leave the branch as-is and continue to the final status check.

---

## Self-Review

- Spec coverage: The plan adds one narrow diagnostic-only `config_intent_self_audit`, projects it into existing configure summary surfaces, documents it, syncs the local skill, and preserves single apply authority.
- Placeholder scan: No unresolved placeholder markers or unspecified implementation steps are present.
- Type consistency: The produced check is always `report["checks"]["config_intent_self_audit"]`; compact projections use `config_intent_self_audit_status`, `config_intent_first_attention`, and `config_intent_runtime_files_without_intent`.
- Boundary review: No task edits apply gates, runtime writers, HSTuner paths, gameplay logs, or gameplay sequencing.
- Cleanliness review: The execution plan commits each logical task and ends with currentness plus clean worktree checks.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-22-hsconfig-config-intent-self-audit.md`.

Two execution options:

1. **Subagent-Driven (recommended)** - Dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints.

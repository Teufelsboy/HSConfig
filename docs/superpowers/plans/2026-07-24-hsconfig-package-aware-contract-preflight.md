# HSConfig Package-Aware Contract Preflight Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend `hsconfig contract-preflight` with an optional `--package <04_package>` read-only diagnostic so an operator can check repo currentness, installed-skill sync, source/runtime contract visibility, package runtime validity, no-default-only state, and config-quality readiness in one command before using a generated CustomConfig.

**Architecture:** Keep `contract-preflight` as the narrow central pre-run diagnostic. Add one package-aware helper that reuses existing package contracts (`validate_config_package` and `build_config_quality_report`) and projects only compact readiness signals. Do not create a new apply gate, do not duplicate `contract-doctor`, and do not change `configure`, package generation, runtime apply, source research, or HearthRanger behavior.

**Tech Stack:** Python 3, argparse, pathlib/json, dataclasses, pytest, existing HSConfig CLI, existing `hsconfig.validate_package`, existing `hsconfig.config_quality_contract`, existing operator docs and installed-skill sync tooling.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig`.
- Start by refreshing repository state: `git fetch --all --prune --tags`.
- Verify currentness before and after implementation with `python scripts\check_hsconfig_currentness.py --cwd . --json`.
- Finish with a clean worktree and no untracked generated files.
- No backup files.
- Do not use HSTuner, replay parsing, HDT parsing, HearthRanger logs, Power.log parsing, winrate analysis, or post-game tuning in this task.
- Do not encode gameplay sequencing assumptions. HearthRanger remains the runtime actor.
- Do not add dependencies.
- Do not add a new runtime surface.
- Do not add a new apply authority.
- `reports/operator_summary.json` remains the only normal runtime apply authority.
- `contract-preflight` remains read-only and diagnostic-only.
- `contract-preflight --package` must not write reports, runtime files, cache files, package files, or skill files.
- `contract-preflight --package` must not accept an `--out` flag.
- `SOURCE_BACKED_STRONG` remains a quality target and diagnostic state, not an apply-hardblock.
- Source quality, source closure, research freshness, config quality, and default-only visibility must not change runtime apply permission.
- `source_status_apply_blocking` at the command/preflight level must remain `false`.
- If a generated package contains default-only runtime surfaces, report attention clearly; do not hide it and do not convert it into a runtime block.
- Normal HSConfig output remains `GlobalValues.json`, `Mulligan.json`, per-card `<CARDID>.json`, and `Combo.json` only when exact ordered combo evidence exists.
- `Presume.json`, `Concede.json`, and aggregate `CardBehavior.json` remain outside the normal output path.
- `contract-doctor` remains the detailed per-package explainer; `contract-preflight --package` only projects compact pass/attention signals and points to the next report.

---

## File Structure

- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\contract_preflight.py`
  - Add `PackageContractPreflight`.
  - Add `build_package_contract_preflight(package)`.
  - Add optional `package=None` parameter to `build_contract_preflight(repo_root, *, git, skill_install_root, package)`.
  - Include package checks only when `--package` is provided.
- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\commands\contract_preflight.py`
  - Pass `args.package` into `build_contract_preflight`.
  - Preserve a stable diagnostic fallback payload on exceptions.
- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\cli_parser.py`
  - Add `--package <04_package>` to `contract-preflight`.
  - Keep help text explicit that it is optional and read-only.
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_contract_preflight.py`
  - Add focused package-aware preflight tests.
  - Add CLI no-write coverage for `--package`.
- Modify: `C:\Users\darbo\Documents\HSConfig\docs\operator\README.md`
  - Document the optional package-aware preflight use.
- Modify: `C:\Users\darbo\Documents\HSConfig\.agents\skills\hsconfig\SKILL.md`
  - Add one expert-path sentence for `contract-preflight --package`.
- Run existing guardrail tests that protect operator wording and skill sync.

---

## Subagent Execution Map

- Agent A: Tests and contract shape. Owns `tests/test_contract_preflight.py`.
- Agent B: Core implementation. Owns `src/hsconfig/contract_preflight.py`.
- Agent C: CLI and docs. Owns `src/hsconfig/commands/contract_preflight.py`, `src/hsconfig/cli_parser.py`, `docs/operator/README.md`, and `.agents/skills/hsconfig/SKILL.md`.
- Main agent: Consolidates patches, resolves conflicts, runs verification, syncs installed skill if docs/skill text changed, commits, pushes, and confirms clean worktree.

Only one agent writes each file area. No agent writes runtime package outputs.

---

### Task 1: Add Package-Aware Failing Tests

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_contract_preflight.py`

**Purpose:** Lock the desired behavior before implementation.

- [ ] **Step 1: Add a local package fixture helper**

Add this helper near the existing helpers in `tests/test_contract_preflight.py`:

```python
def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _contract_preflight_clean_package(tmp_path: Path) -> Path:
    package = tmp_path / "04_package"
    deck = package / "CustomConfig" / "shadowpriest"
    reports = package / "reports"
    _write_json(
        reports / "operator_summary.json",
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "SOURCE_BACKED_STRONG",
            "next_action": "READY_TO_APPLY_OR_HANDOFF",
            "runtime_load_safe": True,
            "runtime_apply_allowed": True,
            "runtime_apply_mode": "load_safe_apply",
            "runtime_apply_contract": {
                "apply_authority": "reports/operator_summary.json",
            },
            "source_status_diagnostic_only": True,
            "source_status_apply_blocking": False,
            "default_only_runtime_surfaces": [],
            "default_only_runtime_surface_details": [],
            "no_default_only_runtime_status": {
                "status": "clean",
                "default_only_runtime_surfaces": [],
            },
            "source_to_runtime_explainability_summary": {
                "non_blocking": True,
                "cards_total": 1,
                "claims_total": 1,
                "runtime_lowered_claims": 1,
                "closure_lane_counts": {"source_backed_runtime_lowered": 1},
                "cards_with_closure": 1,
                "cards_missing_closure": 0,
                "closure_schema_current": True,
                "next_report_to_open": "reports/source_to_runtime_explainability.json",
            },
            "surface_status_ledger": [
                {"surface": "cardid_behavior", "status": "emitted"},
                {"surface": "globalvalues", "status": "emitted"},
                {"surface": "mulligan", "status": "emitted"},
                {"surface": "combo", "status": "not_applicable"},
            ],
        },
    )
    _write_json(
        reports / "deck_identity.json",
        {
            "deck_name": "ShadowPriest",
            "cards": [{"card_id": "NX2_019", "name": "Mind Sear"}],
        },
    )
    _write_json(
        reports / "card_behavior_plan_report.json",
        {
            "rows": [
                {
                    "card_id": "NX2_019",
                    "surface_family": "CARDID.json",
                    "behavior_block": "BeforeBattlecryTargetBonus",
                    "value": "10",
                    "meaningful_runtime_surface": True,
                    "semantic_score": {
                        "band": "high",
                        "reason": "conditional_minion_death_burn",
                        "profile": "semantic_intent",
                        "matched_signals": ["enemy_hero_damage", "death_condition"],
                    },
                }
            ]
        },
    )
    _write_json(
        reports / "source_to_runtime_explainability.json",
        {
            "default_only_runtime_surfaces": [],
            "summary": {
                "cards_total": 1,
                "claims_total": 1,
                "runtime_lowered_claims": 1,
                "next_report_to_open": "reports/source_to_runtime_explainability.json",
            },
            "claim_rows": [
                {
                    "claim_id": "claim_mind_sear_effect",
                    "claim_kind": "targeting_rule",
                    "builder_or_router_decision": "emitted",
                    "emitted_runtime_files": ["NX2_019.json"],
                    "first_missing_link": None,
                }
            ],
            "card_rows": [
                {
                    "card_id": "NX2_019",
                    "first_missing_link": None,
                    "source_lane": "runtime_lowered",
                    "emitted_runtime_files": ["NX2_019.json"],
                    "runtime_surfaces": ["cardid"],
                    "closure": {
                        "lane": "source_backed_runtime_lowered",
                        "runtime_surfaces": ["NX2_019.json"],
                        "default_only_risk": False,
                    },
                    "evidence_chain": [
                        {
                            "claim_id": "claim_mind_sear_effect",
                            "claim_kind": "targeting_rule",
                            "source_lane": "runtime_lowered",
                            "source_type": "deck_matched_public_guide",
                            "runtime_files": ["NX2_019.json"],
                            "resolution_reason": "emitted",
                        }
                    ],
                }
            ],
        },
    )
    _write_json(
        deck / "NX2_019.json",
        {
            "GameCardId": "NX2_019",
            "ConfigComment": "ShadowPriest: generated behavior for NX2_019",
            "BeforeBattlecryTargetBonus": {
                "values": [
                    {
                        "comment": "ShadowPriest: Mind Sear source-backed target preference",
                        "condition": "*",
                        "value": "10",
                    }
                ]
            },
        },
    )
    _write_json(
        deck / "GlobalValues.json",
        {"GameCardId": "GlobalValues", "ConfigComment": "ShadowPriest global values"},
    )
    _write_json(
        deck / "Mulligan.json",
        {
            "GameCardId": "Mulligan",
            "ConfigComment": "ShadowPriest mulligan",
            "Mulligan": {"values": []},
        },
    )
    return package
```

- [ ] **Step 2: Add the clean package aggregation test**

Add this test after the existing research/context preflight tests:

```python
def test_contract_preflight_package_mode_aggregates_runtime_and_quality(
    tmp_path: Path,
) -> None:
    package = _contract_preflight_clean_package(tmp_path)

    payload = build_contract_preflight(
        Path("."),
        git=_clean_git(),
        skill_install_root=_synced_install_root(tmp_path),
        package=package,
    )

    contract = payload["package_contract"]

    assert payload["status"] == "PASS"
    assert payload["checks"]["package_contract_current"] is True
    assert "package_contract_current" not in payload["failures"]
    assert contract["status"] == "clean"
    assert contract["package_contract_current"] is True
    assert contract["authority"] == "diagnostic_only"
    assert contract["runtime_write_performed"] is False
    assert contract["apply_blocking"] is False
    assert contract["runtime_apply_authority"] == "reports/operator_summary.json"
    assert contract["ready_to_use_from_operator_summary"] is True
    assert contract["technical_status"] == "VALID_PACKAGE"
    assert contract["runtime_apply_mode"] == "load_safe_apply"
    assert contract["runtime_apply_allowed"] is True
    assert contract["source_status_apply_blocking"] is False
    assert contract["observed_operator_source_status_apply_blocking"] is False
    assert contract["default_only_runtime_surfaces"] == []
    assert contract["validate_config_package_status"] == "passed"
    assert contract["config_quality_status"] == "clean"
    assert contract["config_quality_problem_count"] == 0
    assert contract["config_intent_self_audit_status"] == "clean"
    assert contract["closure_schema_current"] is True
    assert contract["cards_missing_closure"] == 0
    assert contract["next_report_to_open"] == "reports/operator_summary.json"
```

- [ ] **Step 3: Add the default-only attention test**

Add this test:

```python
def test_contract_preflight_package_mode_exposes_default_only_attention_without_blocking(
    tmp_path: Path,
) -> None:
    package = _contract_preflight_clean_package(tmp_path)
    operator_path = package / "reports" / "operator_summary.json"
    operator = json.loads(operator_path.read_text(encoding="utf-8"))
    operator["semantic_status"] = "VALID_BUT_NOT_GUIDE_STRONG"
    operator["default_only_runtime_surfaces"] = ["Mulligan.json"]
    operator["no_default_only_runtime_status"] = {
        "status": "attention",
        "default_only_runtime_surfaces": ["Mulligan.json"],
    }
    operator_path.write_text(json.dumps(operator, indent=2), encoding="utf-8")

    payload = build_contract_preflight(
        Path("."),
        git=_clean_git(),
        skill_install_root=_synced_install_root(tmp_path),
        package=package,
    )

    contract = payload["package_contract"]

    assert payload["status"] == "ATTENTION"
    assert payload["checks"]["package_contract_current"] is False
    assert "package_contract_current" in payload["failures"]
    assert contract["status"] == "attention"
    assert contract["package_contract_current"] is False
    assert contract["authority"] == "diagnostic_only"
    assert contract["apply_blocking"] is False
    assert contract["runtime_write_performed"] is False
    assert contract["source_status_apply_blocking"] is False
    assert contract["observed_operator_source_status_apply_blocking"] is False
    assert contract["runtime_apply_allowed"] is True
    assert contract["ready_to_use_from_operator_summary"] is True
    assert contract["default_only_runtime_surfaces"] == ["Mulligan.json"]
    assert "default_only_runtime_surfaces_present" in contract["failures"]
    assert contract["next_report_to_open"] == "reports/contract_doctor.json"
```

- [ ] **Step 4: Add the package validation failure test**

Add this test:

```python
def test_contract_preflight_package_mode_exposes_runtime_json_validation_failure(
    tmp_path: Path,
) -> None:
    package = _contract_preflight_clean_package(tmp_path)
    (package / "CustomConfig" / "shadowpriest" / "Mulligan.json").unlink()

    payload = build_contract_preflight(
        Path("."),
        git=_clean_git(),
        skill_install_root=_synced_install_root(tmp_path),
        package=package,
    )

    contract = payload["package_contract"]

    assert payload["status"] == "ATTENTION"
    assert payload["checks"]["package_contract_current"] is False
    assert contract["validate_config_package_status"] == "failed"
    assert contract["apply_blocking"] is False
    assert contract["runtime_write_performed"] is False
    assert contract["source_status_apply_blocking"] is False
    assert "validate_config_package_failed" in contract["failures"]
```

- [ ] **Step 5: Add CLI no-write coverage**

Add this test near the existing CLI no-write test:

```python
def test_contract_preflight_cli_package_mode_does_not_write_files(
    tmp_path: Path,
) -> None:
    package = _contract_preflight_clean_package(tmp_path)
    before = sorted(path.relative_to(package).as_posix() for path in package.rglob("*"))
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "hsconfig.cli",
            "contract-preflight",
            "--repo-root",
            ".",
            "--package",
            str(package),
            "--json",
        ],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )

    after = sorted(path.relative_to(package).as_posix() for path in package.rglob("*"))
    payload = json.loads(result.stdout)

    assert result.returncode in (0, 1)
    assert payload["package_contract"]["runtime_write_performed"] is False
    assert payload["package_contract"]["authority"] == "diagnostic_only"
    assert before == after
```

- [ ] **Step 6: Add parser/help assertion**

Extend the existing parser help test so it asserts:

```python
assert "--package" in parser_help.stdout
```

Expected result before implementation:

```powershell
python -m pytest tests\test_contract_preflight.py -q
```

Expected failure:

- `TypeError: build_contract_preflight() got an unexpected keyword argument 'package'`
- Or parser output does not contain `--package`.

---

### Task 2: Implement the Package Contract Helper

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\contract_preflight.py`

**Purpose:** Reuse existing package validation and quality contracts, then expose a compact diagnostic result.

- [ ] **Step 1: Add imports**

At the top of `contract_preflight.py`, import `Any` if not already available and keep package-specific imports lazy inside the helper:

```python
from typing import Any
```

Do not import `hsconfig.config_quality_contract` or `hsconfig.validate_package` at module import time unless current import order is already safe. Prefer local imports in `build_package_contract_preflight()`.

- [ ] **Step 2: Add the dataclass**

Add this dataclass after `ResearchContextPreflight`:

```python
@dataclass(frozen=True)
class PackageContractPreflight:
    status: str
    package: str
    present: bool
    authority: str
    apply_blocking: bool
    runtime_write_performed: bool
    runtime_apply_authority: str
    source_status_apply_blocking: bool
    observed_operator_source_status_apply_blocking: bool
    technical_status: str
    semantic_status: str
    runtime_apply_mode: str
    runtime_apply_allowed: bool
    default_only_runtime_surfaces: list[str]
    validate_config_package_status: str
    validate_config_package_errors: list[str]
    checked_runtime_files: int
    config_quality_status: str
    config_quality_problem_count: int
    config_quality_first_problem: dict[str, Any] | None
    config_intent_self_audit_status: str
    config_intent_first_attention: str | None
    closure_schema_current: bool
    cards_missing_closure: int
    ready_to_use_from_operator_summary: bool
    package_contract_current: bool
    next_report_to_open: str
    failures: list[str]
```

- [ ] **Step 3: Add small extraction helpers**

Add these helpers near the existing internal helpers:

```python
def _as_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _string_items(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _first_problem(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, list) or not value:
        return None
    first = value[0]
    return dict(first) if isinstance(first, Mapping) else {"value": str(first)}
```

If identical helpers already exist in the module, reuse them instead of adding duplicates.

- [ ] **Step 4: Add `build_package_contract_preflight()`**

Add this function:

```python
def build_package_contract_preflight(package: str | Path | None) -> dict[str, Any] | None:
    if package is None:
        return None

    package_path = Path(package)
    base = {
        "package": str(package_path),
        "authority": "diagnostic_only",
        "apply_blocking": False,
        "runtime_write_performed": False,
        "runtime_apply_authority": "reports/operator_summary.json",
        "source_status_apply_blocking": False,
    }
    if not package_path.is_dir():
        return {
            **base,
            "status": "attention",
            "present": False,
            "observed_operator_source_status_apply_blocking": False,
            "technical_status": "",
            "semantic_status": "",
            "runtime_apply_mode": "",
            "runtime_apply_allowed": False,
            "default_only_runtime_surfaces": [],
            "validate_config_package_status": "failed",
            "validate_config_package_errors": [f"{package_path}: package directory not found"],
            "checked_runtime_files": 0,
            "config_quality_status": "attention",
            "config_quality_problem_count": 1,
            "config_quality_first_problem": {
                "check": "package_missing",
                "value": str(package_path),
            },
            "config_intent_self_audit_status": "missing",
            "config_intent_first_attention": "package_missing",
            "closure_schema_current": False,
            "cards_missing_closure": 0,
            "ready_to_use_from_operator_summary": False,
            "package_contract_current": False,
            "next_report_to_open": "reports/operator_summary.json",
            "failures": ["package_missing"],
        }

    from hsconfig.config_quality_contract import build_config_quality_report
    from hsconfig.validate_package import validate_config_package

    operator = _read_json(package_path / "reports" / "operator_summary.json")
    operator = _as_mapping(operator)
    validation = validate_config_package(package_path, require_complete_package=True)
    quality = build_config_quality_report(package_path)
    quality_checks = _as_mapping(quality.get("checks"))
    operator_quality = _as_mapping(quality_checks.get("operator_summary"))
    closure = _as_mapping(quality_checks.get("closure_freshness"))
    config_intent = _as_mapping(quality_checks.get("config_intent_self_audit"))
    quality_problems = quality.get("problems", [])

    default_only = _string_items(operator_quality.get("default_only_runtime_surfaces"))
    observed_source_blocking = bool(
        operator_quality.get("source_status_apply_blocking", False)
    )
    runtime_contract = _as_mapping(operator.get("runtime_apply_contract"))
    runtime_apply_authority = str(
        runtime_contract.get("apply_authority") or "reports/operator_summary.json"
    )
    runtime_apply_allowed = bool(operator.get("runtime_apply_allowed", False))
    runtime_apply_mode = str(operator.get("runtime_apply_mode", ""))
    technical_status = str(operator.get("technical_status", ""))
    semantic_status = str(operator.get("semantic_status", ""))
    validate_status = str(validation.get("status", "failed"))
    validate_errors = _string_items(validation.get("errors", []))
    config_quality_status = str(quality.get("status", "attention"))
    config_intent_status = str(config_intent.get("status", "missing"))
    closure_schema_current = bool(closure.get("closure_schema_current", False))
    cards_missing_closure = int(closure.get("cards_missing_closure", 0) or 0)

    failures: list[str] = []
    if technical_status != "VALID_PACKAGE":
        failures.append("technical_status_not_valid_package")
    if runtime_apply_mode != "load_safe_apply":
        failures.append("runtime_apply_mode_not_load_safe_apply")
    if runtime_apply_allowed is not True:
        failures.append("runtime_apply_allowed_not_true")
    if runtime_apply_authority != "reports/operator_summary.json":
        failures.append("runtime_apply_authority_not_operator_summary")
    if observed_source_blocking:
        failures.append("observed_operator_source_status_apply_blocking_true")
    if default_only:
        failures.append("default_only_runtime_surfaces_present")
    if validate_status != "passed":
        failures.append("validate_config_package_failed")
    if config_quality_status != "clean":
        failures.append("config_quality_attention")
    if config_intent_status != "clean":
        failures.append("config_intent_self_audit_attention")
    if closure_schema_current is not True:
        failures.append("closure_schema_not_current")
    if cards_missing_closure:
        failures.append("cards_missing_closure")

    ready_to_use = (
        technical_status == "VALID_PACKAGE"
        and runtime_apply_mode == "load_safe_apply"
        and runtime_apply_allowed is True
        and runtime_apply_authority == "reports/operator_summary.json"
    )
    package_contract_current = not failures
    next_report = (
        "reports/operator_summary.json"
        if package_contract_current
        else "reports/contract_doctor.json"
    )

    return {
        **base,
        "status": "clean" if package_contract_current else "attention",
        "present": True,
        "runtime_apply_authority": runtime_apply_authority,
        "observed_operator_source_status_apply_blocking": observed_source_blocking,
        "technical_status": technical_status,
        "semantic_status": semantic_status,
        "runtime_apply_mode": runtime_apply_mode,
        "runtime_apply_allowed": runtime_apply_allowed,
        "default_only_runtime_surfaces": default_only,
        "validate_config_package_status": validate_status,
        "validate_config_package_errors": validate_errors,
        "checked_runtime_files": int(validation.get("checked_files", 0) or 0),
        "config_quality_status": config_quality_status,
        "config_quality_problem_count": len(quality_problems)
        if isinstance(quality_problems, list)
        else 0,
        "config_quality_first_problem": _first_problem(quality_problems),
        "config_intent_self_audit_status": config_intent_status,
        "config_intent_first_attention": config_intent.get("first_attention"),
        "closure_schema_current": closure_schema_current,
        "cards_missing_closure": cards_missing_closure,
        "ready_to_use_from_operator_summary": ready_to_use,
        "package_contract_current": package_contract_current,
        "next_report_to_open": next_report,
        "failures": failures,
    }
```

Implementation notes:

- Keep `source_status_apply_blocking` in this payload fixed to `False` to describe preflight gate impact.
- Use `observed_operator_source_status_apply_blocking` for the observed package field.
- `ready_to_use_from_operator_summary` is allowed to be `True` even when `package_contract_current` is `False`; that means the package is technically load-safe while quality diagnostics need attention.
- The helper must never write files.

---

### Task 3: Wire Package Mode into `build_contract_preflight`

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\contract_preflight.py`

- [ ] **Step 1: Extend the function signature**

Change:

```python
def build_contract_preflight(
    repo_root: str | Path = ".",
    *,
    git: GitPreflight | None = None,
    skill_install_root: str | Path | None = None,
) -> dict[str, object]:
```

To:

```python
def build_contract_preflight(
    repo_root: str | Path = ".",
    *,
    git: GitPreflight | None = None,
    skill_install_root: str | Path | None = None,
    package: str | Path | None = None,
) -> dict[str, object]:
```

- [ ] **Step 2: Add package checks only when requested**

After the normal `checks` object and before final status/failures are returned:

```python
    package_contract = build_package_contract_preflight(package)
    if package_contract is not None:
        checks["package_contract_current"] = bool(
            package_contract.get("package_contract_current", False)
        )
```

Build failures like this:

```python
    failures = [key for key in EXPECTED_CHECK_KEYS if not checks[key]]
    if package_contract is not None and not checks["package_contract_current"]:
        failures.append("package_contract_current")
```

Then include the package payload only when requested:

```python
    payload = {
        "status": "PASS" if not failures else "ATTENTION",
        "repo_root": str(root),
        "git": git_payload,
        "checks": checks,
        "failures": failures,
        "research_context": research_context.as_payload(),
        "installed_skill_sync": installed_skill_sync,
        "source_candidate_plan_contract": source_candidate_plan_contract,
        "runtime_apply_authority": "reports/operator_summary.json",
        "source_status_apply_blocking": False,
        "diagnostic_only": True,
    }
    if package_contract is not None:
        payload["package_contract"] = package_contract
    return payload
```

Do not add `package_contract_current` to `EXPECTED_CHECK_KEYS`, because no-package preflight must keep the existing repo/skill contract behavior.

- [ ] **Step 3: Preserve top-level invariants**

Ensure the final top-level payload still contains:

```python
"runtime_apply_authority": "reports/operator_summary.json",
"source_status_apply_blocking": False,
"diagnostic_only": True,
```

Package attention must affect only `status` and `failures`, not runtime permission.

---

### Task 4: Wire the CLI Argument and Fallback Payload

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\cli_parser.py`
- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\commands\contract_preflight.py`

- [ ] **Step 1: Add the parser argument**

In the `contract-preflight` parser block in `cli_parser.py`, add:

```python
contract_preflight.add_argument(
    "--package",
    help=(
        "Optional path to a prepared 04_package directory. When provided, "
        "contract-preflight also reports package runtime validity and "
        "config-quality readiness as diagnostic-only JSON."
    ),
)
```

- [ ] **Step 2: Pass `args.package` through**

In `run_contract_preflight_command(args)`, change the normal build call to:

```python
payload = build_contract_preflight(
    repo_root,
    skill_install_root=getattr(args, "skill_install_root", None),
    package=getattr(args, "package", None),
)
```

- [ ] **Step 3: Preserve exception fallback shape**

In the exception fallback branch, keep the existing payload fields and add a package fallback only if a package was requested:

```python
package = getattr(args, "package", None)
if package:
    payload["checks"]["package_contract_current"] = False
    payload["package_contract"] = {
        "status": "attention",
        "package": str(package),
        "present": Path(package).is_dir(),
        "authority": "diagnostic_only",
        "apply_blocking": False,
        "runtime_write_performed": False,
        "runtime_apply_authority": "reports/operator_summary.json",
        "source_status_apply_blocking": False,
        "observed_operator_source_status_apply_blocking": False,
        "technical_status": "",
        "semantic_status": "",
        "runtime_apply_mode": "",
        "runtime_apply_allowed": False,
        "default_only_runtime_surfaces": [],
        "validate_config_package_status": "failed",
        "validate_config_package_errors": [],
        "checked_runtime_files": 0,
        "config_quality_status": "attention",
        "config_quality_problem_count": 1,
        "config_quality_first_problem": {
            "check": "contract_preflight_exception",
            "value": str(exc),
        },
        "config_intent_self_audit_status": "attention",
        "config_intent_first_attention": "contract_preflight_exception",
        "closure_schema_current": False,
        "cards_missing_closure": 0,
        "ready_to_use_from_operator_summary": False,
        "package_contract_current": False,
        "next_report_to_open": "reports/operator_summary.json",
        "failures": ["contract_preflight_exception"],
    }
    if "package_contract_current" not in payload["failures"]:
        payload["failures"].append("package_contract_current")
```

Keep exit behavior unchanged:

- Exit `0` only when payload status is `PASS`.
- Exit `1` when package mode reports attention.

---

### Task 5: Update Operator Docs and Skill Router

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\docs\operator\README.md`
- Modify: `C:\Users\darbo\Documents\HSConfig\.agents\skills\hsconfig\SKILL.md`

- [ ] **Step 1: Update Optional Contract Preflight docs**

In `docs/operator/README.md`, extend the Optional Contract Preflight section with:

```markdown
When a package already exists, use `hsconfig contract-preflight --package <04_package> --json` for a single read-only readiness view. It combines the repo/skill preflight with package runtime validation and compact config-quality signals. If `package_contract.status=attention`, inspect `reports/operator_summary.json` first and then run `hsconfig contract-doctor --package <04_package> --json` for details. Package-mode preflight is diagnostic-only; it does not write files, does not replace `reports/operator_summary.json`, and does not block a technically load-safe package.
```

- [ ] **Step 2: Update the installed skill router text**

In `.agents/skills/hsconfig/SKILL.md`, under `## Expert Paths`, replace:

```markdown
- Drift check: `hsconfig contract-preflight --json` verifies currentness, installed-skill sync, and source/runtime wording.
```

With:

```markdown
- Drift check: `hsconfig contract-preflight --json` verifies currentness, installed-skill sync, and source/runtime wording; add `--package <04_package>` for read-only package runtime/config-quality readiness.
```

- [ ] **Step 3: Sync installed skill if tests require it**

If `tests/test_skill_files.py` or `contract-preflight` reports installed-skill drift after editing `.agents/skills/hsconfig/SKILL.md`, run:

```powershell
python scripts\sync_installed_skill.py --repo-root . --install-root C:\Users\darbo\.codex\skills\hsconfig
```

This writes only the installed HSConfig skill copy. It is expected and should be committed only if the installed skill path is inside the repository; otherwise it remains outside git and must still be reflected by `contract-preflight`.

---

### Task 6: Verification

Run these commands from `C:\Users\darbo\Documents\HSConfig`:

```powershell
git fetch --all --prune --tags
python -m pytest tests\test_contract_preflight.py -q
python -m pytest tests\test_contract_doctor.py tests\test_config_quality_contract.py -q
python -m pytest tests\test_skill_files.py tests\test_docs_active_path.py tests\test_contract_guardrail_script.py -q
python scripts\check_contract_guardrails.py
python -m hsconfig.cli contract-preflight --repo-root . --json
python scripts\check_hsconfig_currentness.py --cwd . --json
git status --short --branch --untracked-files=all
```

Expected:

- Focused pytest commands pass.
- `check_contract_guardrails.py` exits `0`.
- `contract-preflight --repo-root . --json` exits `0` with `"status": "PASS"` after the implementation branch is committed and skill sync is current.
- The normal no-package payload remains backward-compatible and diagnostic-only.
- `contract-preflight --package <clean-package> --json` exits `0` only when repo/skill checks and package contract checks are clean.
- `contract-preflight --package <attention-package> --json` exits `1`, reports `package_contract.status="attention"`, and still reports diagnostic-only/non-blocking flags.
- `git status --short --branch --untracked-files=all` shows a clean worktree.

If the full suite is practical in the session, also run:

```powershell
python -m pytest
```

---

### Task 7: Completion Criteria

- [ ] `hsconfig contract-preflight --json` still works exactly as the repo/skill preflight when no package is provided.
- [ ] `hsconfig contract-preflight --package <04_package> --json` is available.
- [ ] Package-mode preflight reuses `validate_config_package()` and `build_config_quality_report()`.
- [ ] Package-mode preflight reports `ready_to_use_from_operator_summary`.
- [ ] Package-mode preflight reports default-only surfaces as attention, not hidden success.
- [ ] Package-mode preflight reports config-quality attention compactly and points to `reports/contract_doctor.json`.
- [ ] Package-mode preflight reports `observed_operator_source_status_apply_blocking` without setting command-level `source_status_apply_blocking` to true.
- [ ] Package-mode preflight never writes package files or runtime files.
- [ ] `reports/operator_summary.json` remains the only normal apply authority.
- [ ] No HSTuner/log-based logic is introduced.
- [ ] No new dependencies are introduced.
- [ ] Tests, guardrails, currentness check, and clean worktree verification are complete.

---

## Notes for the Implementing Agent

- This plan intentionally does not modify ShadowPriest card heuristics, card ordering, location handling, or mechanics lowering. It improves the technical pre-run safety/quality signal for any generated package.
- Do not add a second report writer. If an operator needs details, use the existing `contract-doctor`.
- Do not use `SOURCE_BACKED_STRONG` as the only definition of usable config. A technically valid load-safe package can remain usable while package contract diagnostics show attention.
- Do not make package mode required for existing flows. It is optional and additive.
- Keep the implementation small: one helper, one CLI flag, focused tests, one docs sentence, one skill-router sentence.

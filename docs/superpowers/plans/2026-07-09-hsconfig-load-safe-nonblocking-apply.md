# HSConfig Load-Safe Nonblocking Apply Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make HSConfig apply any technically valid, load-safe initial HearthRanger CustomConfig package without blocking on guide/source-confidence gaps.

**Architecture:** Keep the existing compiler, source lowering, suppression, validation, and report generation strict. Split runtime load safety from semantic confidence: `VALID_PACKAGE` plus required runtime structure becomes the write gate, while `SOURCE_BACKED_STRONG`, source-informed readiness, low-confidence lanes, and missing source links remain visible diagnostics and promotion guidance.

**Tech Stack:** Python package `hsconfig`, pytest, JSON report artifacts, local installed Codex skill docs under `C:\Users\darbo\.codex\skills\hsconfig`.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig` for `Teufelsboy/HSConfig`.
- HSConfig is a lean deck-to-HearthRanger-config generator. Keep it separate from HSTuner.
- Do not add replay parsing, HDT parsing, winrate validation, candidate promotion, or post-run tuning to this repo.
- Generated runtime packages belong under `outputs/` and are ignored by git.
- Preserve exact deck and CardID identity.
- Preserve full `GlobalValues.json` key profiling.
- Preserve every-card gameplan contract coverage.
- Preserve strict JSON validation.
- Preserve row-level provenance for generated config rows.
- Do not make weak confidence lanes runtime-authoritative. `archetype_inferred`, `explicit_low_confidence`, `generic_low_confidence`, unresolved choice identity, unsupported conditions, and unsupported runtime surfaces stay report-only or baseline-safe.
- Keep `Combo.json` optional and exact-only.
- Keep `Presume.json` and `Concede.json` out of the normal path.
- The no-blocking promise means no semantic/source-confidence blocking. It does not mean writing invalid JSON or load-unsafe packages.

---

## File Structure

- Modify `C:\Users\darbo\Documents\HSConfig\src\hsconfig\apply_gate.py`
  - Responsibility: derive the real runtime-write gate from package structure and `operator_summary.json`.
  - Change: allow any `technical_status=VALID_PACKAGE` package with required structure and no forbidden runtime surfaces.

- Modify `C:\Users\darbo\Documents\HSConfig\src\hsconfig\operator_summary.py`
  - Responsibility: describe package validity, semantic confidence, next action, apply policy, and runtime apply contract.
  - Change: add explicit `runtime_load_safe`; report `runtime_apply_mode=load_safe_apply` for valid packages; switch valid weak packages to a runtime-ready-with-warnings next action.

- Modify `C:\Users\darbo\Documents\HSConfig\src\hsconfig\operator_guidance.py`
  - Responsibility: turn `operator_summary.json` into operator-facing next command guidance.
  - Change: guide valid weak packages toward normal `hsconfig apply` with warnings, not source improvement as a pre-apply blocker.

- Keep `C:\Users\darbo\Documents\HSConfig\src\hsconfig\commands\apply.py` and `C:\Users\darbo\Documents\HSConfig\src\hsconfig\runtime_apply.py` mostly unchanged.
  - Responsibility: validate packages and perform fake/apply runtime writes.
  - Change only if tests show CLI output/help still names the old source-informed flag as the normal weak-package route.

- Modify tests:
  - `C:\Users\darbo\Documents\HSConfig\tests\test_apply_gate.py`
  - `C:\Users\darbo\Documents\HSConfig\tests\test_operator_summary.py`
  - `C:\Users\darbo\Documents\HSConfig\tests\test_operator_guidance.py`
  - `C:\Users\darbo\Documents\HSConfig\tests\test_runtime_apply.py`
  - `C:\Users\darbo\Documents\HSConfig\tests\test_shadowpriest_e2e.py`
  - `C:\Users\darbo\Documents\HSConfig\tests\test_docs_active_path.py`
  - `C:\Users\darbo\Documents\HSConfig\tests\test_skill_files.py`
  - Add `C:\Users\darbo\Documents\HSConfig\tests\test_supplemental_cute_warrior_load_safe.py`

- Modify docs:
  - `C:\Users\darbo\Documents\HSConfig\docs\operator\README.md`
  - `C:\Users\darbo\Documents\HSConfig\docs\operator\source-backed-strong-closure.md`
  - `C:\Users\darbo\Documents\HSConfig\docs\operator\supplemental-proof-decks.json`
  - Local installed skill docs:
    - `C:\Users\darbo\.codex\skills\hsconfig\SKILL.md`
    - `C:\Users\darbo\.codex\skills\hsconfig\references\workflow.md`
    - `C:\Users\darbo\.codex\skills\hsconfig\references\guide-research-policy.md`

---

### Task 1: Convert Apply Gate To Load-Safe Runtime Permission

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_apply_gate.py`
- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\apply_gate.py`

**Interfaces:**
- Consumes: `evaluate_apply_gate(package_root: str | Path, *, allow_source_informed: bool = False) -> dict[str, Any]`
- Produces: allowed gate payload with `mode="load_safe_apply"` for every load-safe `VALID_PACKAGE`
- Produces: hard block payloads unchanged for missing summaries, invalid summaries, missing required runtime files, forbidden surfaces, undeclared runtime files, and `technical_status != "VALID_PACKAGE"`

- [ ] **Step 1: Replace the warning-package blocked test with a load-safe allowed test**

  In `tests\test_apply_gate.py`, replace `test_apply_gate_blocks_valid_but_not_guide_strong_by_default` with:

```python
def test_apply_gate_allows_valid_but_not_guide_strong_as_load_safe_apply(tmp_path: Path):
    package = tmp_path / "package"
    _write_minimal_runtime_package(package)
    _write_operator_summary(
        package,
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "VALID_BUT_NOT_GUIDE_STRONG",
            "next_action": "READY_TO_APPLY_WITH_WARNINGS",
            "apply_policy": "ALLOWED_WITH_WARNINGS",
            "semantic_blockers": [{"reason": "cards_need_guide_claims", "count": 3}],
            "generated_files": [
                "CustomConfig\\deck\\GlobalValues.json",
                "CustomConfig\\deck\\Mulligan.json",
                "CustomConfig\\deck\\EX1_001.json",
            ],
        },
    )

    gate = evaluate_apply_gate(package)

    assert gate == {
        "status": "allowed",
        "allowed": True,
        "operator_summary_path": str(package / "reports" / "operator_summary.json"),
        "mode": "load_safe_apply",
        "reasons": [
            {
                "reason": "runtime_load_safe_package",
                "technical_status": "VALID_PACKAGE",
                "semantic_status": "VALID_BUT_NOT_GUIDE_STRONG",
                "next_action": "READY_TO_APPLY_WITH_WARNINGS",
                "apply_policy": "ALLOWED_WITH_WARNINGS",
                "semantic_blocker_count": 1,
            }
        ],
    }
```

- [ ] **Step 2: Replace the old escape-hatch test with a semantic-gap-is-not-a-gate test**

  In `tests\test_apply_gate.py`, replace `test_apply_gate_blocks_old_warning_escape_hatch_even_with_source_informed_flag` with:

```python
def test_apply_gate_allows_valid_runtime_surface_gap_as_load_safe_warning(
    tmp_path: Path,
):
    package = tmp_path / "package"
    _write_minimal_runtime_package(package)
    _write_operator_summary(
        package,
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "VALID_BUT_NOT_GUIDE_STRONG",
            "next_action": "READY_TO_APPLY_WITH_WARNINGS",
            "apply_policy": "ALLOWED_WITH_WARNINGS",
            "semantic_blockers": [{"reason": "cards_need_runtime_surface", "count": 2}],
            "generated_files": [
                "CustomConfig\\deck\\GlobalValues.json",
                "CustomConfig\\deck\\Mulligan.json",
                "CustomConfig\\deck\\EX1_001.json",
            ],
        },
    )

    gate = evaluate_apply_gate(package, allow_source_informed=True)

    assert gate["status"] == "allowed"
    assert gate["allowed"] is True
    assert gate["mode"] == "load_safe_apply"
    assert gate["reasons"][0]["reason"] == "runtime_load_safe_package"
    assert gate["reasons"][0]["semantic_blocker_count"] == 1
```

- [ ] **Step 3: Update the source-informed flag test to prove the flag is harmless compatibility**

  In `tests\test_apply_gate.py`, replace `test_apply_gate_allows_source_informed_apply_ready_only_with_flag` with:

```python
def test_apply_gate_allows_source_informed_apply_ready_without_flag(tmp_path: Path):
    package = tmp_path / "package"
    _write_minimal_runtime_package(package)
    _write_operator_summary(
        package,
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "VALID_BUT_NOT_GUIDE_STRONG",
            "next_action": "READY_TO_APPLY_WITH_WARNINGS",
            "apply_policy": "ALLOWED_WITH_WARNINGS",
            "source_informed_apply_readiness": {
                "status": "ready",
                "requires_flag": None,
                "source_gap_count": 2,
            },
            "semantic_blockers": [{"reason": "cards_need_guide_claims", "count": 2}],
            "generated_files": [
                "CustomConfig\\deck\\GlobalValues.json",
                "CustomConfig\\deck\\Mulligan.json",
                "CustomConfig\\deck\\EX1_001.json",
            ],
        },
    )

    default_gate = evaluate_apply_gate(package)
    compatibility_gate = evaluate_apply_gate(package, allow_source_informed=True)

    assert default_gate["status"] == "allowed"
    assert default_gate["mode"] == "load_safe_apply"
    assert compatibility_gate["status"] == "allowed"
    assert compatibility_gate["mode"] == "load_safe_apply"
```

- [ ] **Step 4: Update forged-summary test to prove forged runtime booleans are still ignored**

  In `tests\test_apply_gate.py`, replace `test_apply_gate_ignores_forged_runtime_apply_allowed_field` with:

```python
def test_apply_gate_ignores_forged_runtime_apply_fields_but_allows_valid_structure(
    tmp_path: Path,
):
    package = tmp_path / "package"
    _write_minimal_runtime_package(package)
    _write_operator_summary(
        package,
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "VALID_BUT_NOT_GUIDE_STRONG",
            "next_action": "IMPROVE_GUIDE_SOURCES_BEFORE_STRONG_APPLY",
            "apply_policy": "ALLOWED_WITH_WARNINGS",
            "runtime_apply_mode": "normal_apply",
            "runtime_apply_allowed": True,
            "runtime_apply_requires_flag": None,
            "semantic_blockers": [{"reason": "cards_need_guide_claims", "count": 3}],
            "generated_files": [
                "CustomConfig\\deck\\GlobalValues.json",
                "CustomConfig\\deck\\Mulligan.json",
                "CustomConfig\\deck\\EX1_001.json",
            ],
        },
    )

    gate = evaluate_apply_gate(package)

    assert gate["allowed"] is True
    assert gate["mode"] == "load_safe_apply"
    assert gate["reasons"][0]["reason"] == "runtime_load_safe_package"
```

- [ ] **Step 5: Run the failing apply-gate slice**

```powershell
$env:PYTHONPATH='src'
python -m pytest tests\test_apply_gate.py -q
```

  Expected before implementation: tests from Steps 1-4 fail because the gate still blocks valid warning packages and still uses old modes.

- [ ] **Step 6: Implement the load-safe allow path**

  In `src\hsconfig\apply_gate.py`, replace the source-backed/source-informed semantic allow checks and the final `operator_summary_not_ready_to_apply` block with:

```python
    if technical_status == "VALID_PACKAGE":
        return _allowed(
            operator_path,
            mode="load_safe_apply",
            reasons=[
                {
                    "reason": "runtime_load_safe_package",
                    "technical_status": technical_status,
                    "semantic_status": semantic_status,
                    "next_action": next_action,
                    "apply_policy": apply_policy,
                    "semantic_blocker_count": _list_count(
                        summary.get("semantic_blockers", [])
                    ),
                }
            ],
        )

    return _blocked(
        operator_path,
        {
            "reason": "operator_summary_not_valid_package",
            "technical_status": technical_status,
            "semantic_status": semantic_status,
            "next_action": next_action,
            "apply_policy": apply_policy,
        },
    )
```

  Add this helper near `_int_value` or the existing small helpers:

```python
def _list_count(value: Any) -> int:
    return len(value) if isinstance(value, list) else 0
```

  Keep all structure and optional-surface checks above this block unchanged.

- [ ] **Step 7: Keep invalid-package and load-unsafe tests green**

```powershell
$env:PYTHONPATH='src'
python -m pytest tests\test_apply_gate.py -q
```

  Expected after implementation: all apply-gate tests pass. If any old test still asserts `operator_summary_not_ready_to_apply` for `VALID_PACKAGE`, update it to expect `load_safe_apply`. If a test asserts missing files or `INVALID_PACKAGE`, keep it blocked.

- [ ] **Step 8: Commit Task 1**

```powershell
git add src\hsconfig\apply_gate.py tests\test_apply_gate.py
git commit -m "feat: allow load-safe valid packages through apply gate"
```

---

### Task 2: Split Operator Summary Runtime Readiness From Semantic Confidence

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_operator_summary.py`
- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\operator_summary.py`

**Interfaces:**
- Consumes: `build_operator_summary(...) -> dict[str, Any]`
- Produces: `runtime_load_safe: bool`
- Produces: `runtime_apply_mode: "load_safe_apply" | "blocked"`
- Produces: `runtime_apply_allowed: bool`
- Produces: `runtime_apply_requires_flag: None`
- Produces: `next_action="READY_TO_APPLY_WITH_WARNINGS"` for technically valid non-strong packages
- Preserves: `semantic_status`, `semantic_blockers`, `source_informed_apply_readiness`, `guide_strength_summary`, source gap reports

- [ ] **Step 1: Update strong-package operator-summary expectations**

  In `tests\test_operator_summary.py`, update `test_source_backed_valid_package_is_ready_to_apply` assertions:

```python
    assert summary["runtime_load_safe"] is True
    assert summary["runtime_apply_mode"] == "load_safe_apply"
    assert summary["runtime_apply_allowed"] is True
    assert summary["runtime_apply_requires_flag"] is None
    assert summary["operator_guidance"]["safe_to_apply"] is True
    assert summary["operator_guidance"]["normal_next_step"] == "apply_or_handoff"
```

  Keep these existing assertions unchanged:

```python
    assert summary["semantic_status"] == "SOURCE_BACKED_STRONG"
    assert summary["next_action"] == "READY_TO_APPLY_OR_HANDOFF"
    assert summary["apply_policy"] == "ALLOWED"
```

- [ ] **Step 2: Update static semantics package expectations**

  In `tests\test_operator_summary.py`, update `test_static_semantics_valid_package_is_ready_with_warnings`:

```python
    assert summary["technical_status"] == "VALID_PACKAGE"
    assert summary["semantic_status"] == "STATIC_SEMANTICS_USABLE"
    assert summary["next_action"] == "READY_TO_APPLY_WITH_WARNINGS"
    assert summary["apply_policy"] == "ALLOWED_WITH_WARNINGS"
    assert summary["runtime_load_safe"] is True
    assert summary["runtime_apply_mode"] == "load_safe_apply"
    assert summary["runtime_apply_allowed"] is True
    assert summary["runtime_apply_requires_flag"] is None
```

- [ ] **Step 3: Update missing-guide-depth package expectations**

  In `tests\test_operator_summary.py`, update `test_missing_guide_depth_requests_more_research_without_invalidating_package`:

```python
    assert summary["technical_status"] == "VALID_PACKAGE"
    assert summary["semantic_status"] == "NEEDS_MORE_RESEARCH"
    assert summary["next_action"] == "READY_TO_APPLY_WITH_WARNINGS"
    assert summary["apply_policy"] == "ALLOWED_WITH_WARNINGS"
    assert summary["runtime_load_safe"] is True
    assert summary["runtime_apply_mode"] == "load_safe_apply"
    assert summary["runtime_apply_allowed"] is True
```

- [ ] **Step 4: Add a dedicated confidence-warning test**

  Add this test near the existing warning tests:

```python
def test_valid_but_not_guide_strong_is_load_safe_but_not_semantically_strong():
    summary = build_operator_summary(
        deck_name="ShadowPriest",
        deck_code="deck-code",
        technical_validation={"status": "passed", "errors": []},
        guide_source_depth={
            "source_depth_status": "source_backed",
            "source_count": 1,
            "claim_count": 1,
            "warnings": [{"reason": "cards_need_guide_claims", "count": 2}],
        },
        unsupported_conditions=[],
        globalvalue_authority={"blocked_until_runtime_evidence": []},
        generated_files=["CustomConfig/shadowpriest/GlobalValues.json"],
        config_readiness_summary={
            "total_cards": 3,
            "generic_low_confidence": 1,
            "cards_needing_guide_claims": 2,
            "cards_needing_runtime_surface": 0,
            "cards_needing_mulligan_claims": 0,
            "cards_needing_combo_sequence": 0,
            "cards_needing_condition_lowering": 0,
            "cards_needing_mechanic_lowering": 0,
        },
        claim_conflict_report={"conflict_count": 0, "conflicts": []},
    )

    assert summary["technical_status"] == "VALID_PACKAGE"
    assert summary["semantic_status"] == "VALID_BUT_NOT_GUIDE_STRONG"
    assert summary["next_action"] == "READY_TO_APPLY_WITH_WARNINGS"
    assert summary["apply_policy"] == "ALLOWED_WITH_WARNINGS"
    assert summary["runtime_load_safe"] is True
    assert summary["runtime_apply_mode"] == "load_safe_apply"
    assert summary["runtime_apply_allowed"] is True
    assert summary["source_informed_apply_readiness"]["status"] == "blocked"
    assert summary["semantic_blockers"]
```

- [ ] **Step 5: Run the failing operator-summary tests**

```powershell
$env:PYTHONPATH='src'
python -m pytest tests\test_operator_summary.py -q
```

  Expected before implementation: tests fail because valid weak packages still report `runtime_apply_mode=blocked` or `source_informed_apply_requires_flag`, and because `runtime_load_safe` does not exist.

- [ ] **Step 6: Add `runtime_load_safe` to the summary payload**

  In `src\hsconfig\operator_summary.py`, find the existing call to `_runtime_apply_contract(...)`. Change it to pass `technical_status`:

```python
    runtime_apply_mode, runtime_apply_allowed, runtime_apply_requires_flag = (
        _runtime_apply_contract(
            technical_status=technical_status,
            next_action=next_action,
            apply_policy=apply_policy,
            source_informed_apply_readiness=source_informed_apply_readiness,
        )
    )
```

  Add this field to the returned summary dict next to `runtime_apply_mode`:

```python
        "runtime_load_safe": technical_status == "VALID_PACKAGE",
```

- [ ] **Step 7: Change weak valid next action to runtime-ready with warnings**

  In `src\hsconfig\operator_summary.py`, update `_next_action_and_policy(...)`:

```python
def _next_action_and_policy(
    *,
    technical_status: str,
    semantic_status: str,
    primary_blockers: list[dict[str, str]],
    source_informed_apply_ready: bool = False,
) -> tuple[str, str]:
    if technical_status == "INVALID_PACKAGE" or primary_blockers:
        return "FIX_PACKAGE_BEFORE_APPLY", "BLOCKED"
    if semantic_status == "SOURCE_BACKED_STRONG":
        return "READY_TO_APPLY_OR_HANDOFF", "ALLOWED"
    return "READY_TO_APPLY_WITH_WARNINGS", "ALLOWED_WITH_WARNINGS"
```

  Keep `_source_informed_apply_readiness(...)` unchanged. It remains a confidence diagnostic, not a write gate.

- [ ] **Step 8: Change runtime apply contract**

  In `src\hsconfig\operator_summary.py`, update `_runtime_apply_contract(...)`:

```python
def _runtime_apply_contract(
    *,
    technical_status: str,
    next_action: str,
    apply_policy: str,
    source_informed_apply_readiness: dict[str, Any],
) -> tuple[str, bool, str | None]:
    if technical_status == "VALID_PACKAGE" and apply_policy != "BLOCKED":
        return "load_safe_apply", True, None
    return "blocked", False, None
```

  `next_action` and `source_informed_apply_readiness` stay in the signature only if other call sites still need the same function shape during this task. If lint or tests show they are unused, remove the unused parameters and update the call site in the same commit.

- [ ] **Step 9: Run operator-summary tests again**

```powershell
$env:PYTHONPATH='src'
python -m pytest tests\test_operator_summary.py -q
```

  Expected after implementation: tests pass after updating old assertions that expected `runtime_apply_mode=blocked` for valid packages. Do not change invalid-package tests; they must keep `runtime_apply_mode=blocked`.

- [ ] **Step 10: Commit Task 2**

```powershell
git add src\hsconfig\operator_summary.py tests\test_operator_summary.py
git commit -m "feat: separate load-safe apply from semantic confidence"
```

---

### Task 3: Align Operator Guidance And Runtime Apply Behavior

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_operator_guidance.py`
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_runtime_apply.py`
- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\operator_guidance.py`
- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\commands\apply.py` only if CLI help or output still presents `--allow-source-informed` as required for valid warning packages
- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\runtime_apply.py` only if tests show it special-cases source-informed apply modes

**Interfaces:**
- Consumes: operator summary fields from Task 2
- Produces: operator guidance with `safe_to_apply=True` for load-safe valid packages
- Produces: normal apply command without `--allow-source-informed` for valid warning packages
- Preserves: invalid packages still return `safe_to_apply=False`

- [ ] **Step 1: Update guidance tests for warning packages**

  In `tests\test_operator_guidance.py`, replace assertions that expect `safe_to_apply=False` for `VALID_BUT_NOT_GUIDE_STRONG` plus `ALLOWED_WITH_WARNINGS` with:

```python
def test_guidance_for_load_safe_warning_package():
    guidance = build_operator_guidance(
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "VALID_BUT_NOT_GUIDE_STRONG",
            "next_action": "READY_TO_APPLY_WITH_WARNINGS",
            "apply_policy": "ALLOWED_WITH_WARNINGS",
            "runtime_load_safe": True,
            "runtime_apply_mode": "load_safe_apply",
            "runtime_apply_allowed": True,
            "runtime_apply_requires_flag": None,
            "semantic_blockers": [
                {"reason": "cards_need_guide_claims", "report": "reports/source_claim_gap_report.json"}
            ],
        }
    )

    assert guidance["normal_next_step"] == "apply_with_warnings"
    assert guidance["normal_next_command"] == (
        "hsconfig apply --package <package> --runtime-root <runtime-root> --json"
    )
    assert guidance["safe_to_apply"] is True
    assert guidance["requires_expert_flag"] is False
    assert guidance["next_report_to_open"] == "reports/source_claim_gap_report.json"
    assert guidance["runtime_apply_mode"] == "load_safe_apply"
```

- [ ] **Step 2: Update runtime apply tests for source-informed valid packages**

  In `tests\test_runtime_apply.py`, update source-informed apply tests so normal apply succeeds without `--allow-source-informed` when the package is otherwise valid:

```python
def test_apply_cli_applies_valid_warning_package_without_source_informed_flag(
    tmp_path: Path,
    capsys,
):
    package = _write_package(
        tmp_path,
        next_action="READY_TO_APPLY_WITH_WARNINGS",
        semantic_status="VALID_BUT_NOT_GUIDE_STRONG",
        apply_policy="ALLOWED_WITH_WARNINGS",
        source_informed_apply_readiness={
            "status": "blocked",
            "blocking_reasons": ["cards_need_runtime_surface"],
        },
    )
    runtime_root = tmp_path / "runtime"

    code = main(
        [
            "apply",
            "--package",
            str(package),
            "--runtime-root",
            str(runtime_root),
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["status"] == "applied"
    assert payload["apply_gate"]["mode"] == "load_safe_apply"
```

  Use the existing `_write_package` or equivalent helper already present in `tests\test_runtime_apply.py`. If the helper requires different keyword names, keep its existing signature and only change the operator summary values.

- [ ] **Step 3: Run focused failing guidance/runtime tests**

```powershell
$env:PYTHONPATH='src'
python -m pytest tests\test_operator_guidance.py tests\test_runtime_apply.py -q
```

  Expected before implementation: warning-package guidance or runtime apply tests still expect blocked/source-informed-flag behavior.

- [ ] **Step 4: Implement guidance for load-safe warning packages**

  In `src\hsconfig\operator_guidance.py`, after the invalid-package branch, add a runtime-load-safe branch before the `SOURCE_BACKED_STRONG` branch:

```python
    if bool(summary.get("runtime_apply_allowed")) and str(
        summary.get("runtime_apply_mode", "")
    ) == "load_safe_apply":
        if semantic_status == "SOURCE_BACKED_STRONG" and apply_policy == "ALLOWED":
            return {
                "first_report_to_open": "reports/operator_summary.json",
                "next_report_to_open": None,
                "normal_next_step": "apply_or_handoff",
                "normal_next_command": "hsconfig apply --package <package> --runtime-root <runtime-root> --json",
                "safe_to_apply": True,
                "requires_expert_flag": False,
                **_runtime_apply_fields(summary),
            }
        return {
            "first_report_to_open": "reports/operator_summary.json",
            "next_report_to_open": _first_semantic_blocker_report(summary)
            or "reports/source_claim_gap_report.json",
            "normal_next_step": "apply_with_warnings",
            "normal_next_command": "hsconfig apply --package <package> --runtime-root <runtime-root> --json",
            "safe_to_apply": True,
            "requires_expert_flag": False,
            **_runtime_apply_fields(summary),
        }
```

  Remove or bypass the old branch that made `VALID_BUT_NOT_GUIDE_STRONG` return `normal_next_step="improve_sources"` with `safe_to_apply=False`. Keep `_first_semantic_blocker_report(...)` because warnings should still point to the first confidence report.

- [ ] **Step 5: Keep apply command compatibility**

  Run:

```powershell
$env:PYTHONPATH='src'
python -m hsconfig apply --help
```

  Expected: help may still include `--allow-source-informed` as a backward-compatible option, but it must not say the flag is required for valid warning packages. If help text still says it is required, update the help string in `src\hsconfig\cli_parser.py` or the current parser module to:

```python
"Backward-compatible source-informed apply flag. Normal load-safe packages do not require this flag."
```

- [ ] **Step 6: Run focused tests again**

```powershell
$env:PYTHONPATH='src'
python -m pytest tests\test_operator_guidance.py tests\test_runtime_apply.py -q
```

  Expected after implementation: all focused tests pass.

- [ ] **Step 7: Commit Task 3**

```powershell
git add src\hsconfig\operator_guidance.py src\hsconfig\commands\apply.py src\hsconfig\runtime_apply.py src\hsconfig\cli_parser.py tests\test_operator_guidance.py tests\test_runtime_apply.py
git commit -m "feat: guide valid warning packages to normal apply"
```

  If `commands\apply.py`, `runtime_apply.py`, or `cli_parser.py` did not change, omit them from `git add`.

---

### Task 4: Add CuteWarrior Load-Safe Supplemental Proof

**Files:**
- Create: `C:\Users\darbo\Documents\HSConfig\tests\test_supplemental_cute_warrior_load_safe.py`
- Modify: `C:\Users\darbo\Documents\HSConfig\docs\operator\supplemental-proof-decks.json`

**Interfaces:**
- Consumes: CLI `hsconfig prepare`
- Produces: executable proof that CuteWarrior can produce `technical_status=VALID_PACKAGE`
- Produces: proof that CuteWarrior remains supplemental and does not widen the representative 11-deck matrix

- [ ] **Step 1: Add the CuteWarrior prepare-path test**

  Create `tests\test_supplemental_cute_warrior_load_safe.py`:

```python
import json
from pathlib import Path

from hsconfig.cli import main


def test_cute_warrior_supplemental_prepare_path_is_load_safe(
    tmp_path: Path,
    capsys,
    monkeypatch,
):
    monkeypatch.setattr("hsconfig.package_builder.fetch_latest_cards", lambda timeout=10.0: [])
    out = tmp_path / "CuteWarrior"

    code = main(
        [
            "prepare",
            "--deck-name",
            "CuteWarrior",
            "--deck-code",
            "AAEBAQcEkbwCkdAD69YHstgHDY0Q6bADpLYDxN4D/9sEj5UFlaoFtNEF9PIFovoF/KgGltMGtI8HAAA=",
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(out),
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    operator = json.loads((out / "reports" / "operator_summary.json").read_text(encoding="utf-8"))
    custom_config_dirs = list((out / "CustomConfig").iterdir())
    deck_dir = custom_config_dirs[0]
    card_files = [
        path
        for path in deck_dir.glob("*.json")
        if path.name not in {"Combo.json", "GlobalValues.json", "Mulligan.json"}
    ]

    assert code == 0
    assert payload["status"] == "passed"
    assert operator["technical_status"] == "VALID_PACKAGE"
    assert operator["runtime_load_safe"] is True
    assert operator["runtime_apply_mode"] == "load_safe_apply"
    assert operator["runtime_apply_allowed"] is True
    assert (deck_dir / "GlobalValues.json").is_file()
    assert (deck_dir / "Mulligan.json").is_file()
    assert card_files
```

- [ ] **Step 2: Run the new test and confirm the current gap**

```powershell
$env:PYTHONPATH='src'
python -m pytest tests\test_supplemental_cute_warrior_load_safe.py -q
```

  Expected before Tasks 1-3 are fully integrated: the test fails on missing `runtime_load_safe` or old `runtime_apply_mode`. If prepare itself fails, inspect the validation report and fix the package-builder path only if the failure is a real technical package bug.

- [ ] **Step 3: Keep CuteWarrior supplemental but update proof role wording**

  In `docs\operator\supplemental-proof-decks.json`, change CuteWarrior's `proof_role` from:

```json
"supplemental_command_acceptance"
```

  to:

```json
"supplemental_load_safe_prepare_proof"
```

  Keep this unchanged:

```json
"matrix_policy": "not_representative_until_future_matrix_review_proves_missing_family",
"operator_action": "keep_supplemental"
```

- [ ] **Step 4: Update matrix governance test for the new role**

  In `tests\test_matrix_governance.py`, update the CuteWarrior role assertion:

```python
    assert cute["proof_role"] == "supplemental_load_safe_prepare_proof"
```

  Keep the assertions that CuteWarrior is absent from the representative matrix and that `operator_action == "keep_supplemental"`.

- [ ] **Step 5: Verify supplemental proof and governance**

```powershell
$env:PYTHONPATH='src'
python -m pytest tests\test_supplemental_cute_warrior_load_safe.py tests\test_matrix_governance.py -q
python -m json.tool docs\operator\supplemental-proof-decks.json > $null
```

  Expected after implementation: tests pass and JSON formatting is valid.

- [ ] **Step 6: Commit Task 4**

```powershell
git add tests\test_supplemental_cute_warrior_load_safe.py tests\test_matrix_governance.py docs\operator\supplemental-proof-decks.json
git commit -m "test: prove CuteWarrior load-safe supplemental prepare path"
```

---

### Task 5: Update Operator Docs And Installed Skill Docs

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\docs\operator\README.md`
- Modify: `C:\Users\darbo\Documents\HSConfig\docs\operator\source-backed-strong-closure.md`
- Modify: `C:\Users\darbo\.codex\skills\hsconfig\SKILL.md`
- Modify: `C:\Users\darbo\.codex\skills\hsconfig\references\workflow.md`
- Modify: `C:\Users\darbo\.codex\skills\hsconfig\references\guide-research-policy.md`
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_docs_active_path.py`
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_skill_files.py`

**Interfaces:**
- Consumes: new fields and modes from Tasks 1-4
- Produces: docs that say valid load-safe packages apply by default
- Produces: docs that keep semantic confidence honest

- [ ] **Step 1: Update doc tests first**

  In `tests\test_docs_active_path.py`, replace the assertion that expects old non-write language:

```python
    assert "ALLOWED_WITH_WARNINGS is not runtime write permission" in operator_docs
```

  with:

```python
    assert "runtime_load_safe" in operator_docs
    assert "load_safe_apply" in operator_docs
    assert "ALLOWED_WITH_WARNINGS can still be runtime-write permission when technical_status=VALID_PACKAGE" in operator_docs
    assert "ALLOWED_WITH_WARNINGS is not runtime write permission" not in operator_docs
```

  In `tests\test_skill_files.py`, replace the assertion:

```python
    assert "ALLOWED_WITH_WARNINGS as runtime write permission" not in skill
```

  with:

```python
    assert "runtime_load_safe" in skill
    assert "load_safe_apply" in skill
    assert "ALLOWED_WITH_WARNINGS can still be runtime-write permission when technical_status=VALID_PACKAGE" in skill
```

- [ ] **Step 2: Run docs tests and confirm they fail**

```powershell
$env:PYTHONPATH='src'
python -m pytest tests\test_docs_active_path.py tests\test_skill_files.py -q
```

  Expected before doc edits: tests fail because docs still teach the old blocked warning policy.

- [ ] **Step 3: Update operator README status definitions**

  In `docs\operator\README.md`, replace the runtime-apply status block with:

```markdown
- `technical_status=VALID_PACKAGE` means the runtime JSON shape is structurally valid and load-safe.
- `runtime_load_safe=true` means the package passed the normal pre-run load-safety contract.
- `runtime_apply_mode=load_safe_apply` means normal `hsconfig apply --json` is allowed.
- `runtime_apply_mode=blocked` means no runtime write should happen because the package is invalid or load-unsafe.
- `runtime_apply_allowed=true` is descriptive; the CLI and `apply_package()` still re-evaluate the gate before writing.
- `ALLOWED_WITH_WARNINGS` can still be runtime-write permission when `technical_status=VALID_PACKAGE`; warnings describe semantic/source confidence debt, not a write blocker.
```

  Replace the source-informed flag paragraph with:

```markdown
`--allow-source-informed` is backward-compatible. It is no longer required for a load-safe valid package. Use `reports/operator_summary.json` to distinguish load safety from semantic strength: `SOURCE_BACKED_STRONG` means high-confidence source-backed handoff, while `READY_TO_APPLY_WITH_WARNINGS` means the package is usable but still has documented confidence gaps.
```

- [ ] **Step 4: Update source-backed closure docs**

  In `docs\operator\source-backed-strong-closure.md`, add this paragraph after the representative matrix explanation:

```markdown
Runtime apply no longer requires every package to be `SOURCE_BACKED_STRONG`. The representative matrix still preserves source-strength truth, but `VALID_PACKAGE` plus `runtime_load_safe=true` is enough for an initial load-safe runtime write. Source-informed rows remain valuable because they expose confidence debt, not because they should block usable package handoff.
```

- [ ] **Step 5: Update installed skill main instructions**

  In `C:\Users\darbo\.codex\skills\hsconfig\SKILL.md`, replace the old `--allow-source-informed` normal-path guidance with:

```markdown
8. Run `hsconfig apply ...` only when runtime writes are intended. Guarded apply stays pre-run: runtime writes remain only when requested through `hsconfig apply`. A package with `technical_status=VALID_PACKAGE`, `runtime_load_safe=true`, and `runtime_apply_mode=load_safe_apply` can be applied with `hsconfig apply --package <package> --runtime-root <runtime-root> --json`. `SOURCE_BACKED_STRONG` is a confidence label, not the default runtime-write gate.
```

  Replace the old warning bullet with:

```markdown
- Read `runtime_load_safe`, `runtime_apply_mode`, `runtime_apply_allowed`, and `runtime_apply_requires_flag` in `operator_summary.json`. `ALLOWED_WITH_WARNINGS` can still be runtime-write permission when `technical_status=VALID_PACKAGE`; warnings describe semantic/source confidence debt.
```

- [ ] **Step 6: Update installed skill workflow reference**

  In `C:\Users\darbo\.codex\skills\hsconfig\references\workflow.md`, replace old source-informed apply text with:

```markdown
`technical_status=VALID_PACKAGE` plus `runtime_load_safe=true` is the normal initial write boundary. `runtime_apply_mode=load_safe_apply` means `hsconfig apply --package <package> --runtime-root <runtime-root> --json` is allowed. `SOURCE_BACKED_STRONG` remains the high-confidence source-backed handoff label. Lower confidence lanes remain visible in reports, but they do not block a load-safe initial package.
```

- [ ] **Step 7: Update installed guide policy reference**

  In `C:\Users\darbo\.codex\skills\hsconfig\references\guide-research-policy.md`, replace the sentence that says non-strong packages require `--allow-source-informed` with:

```markdown
`hsconfig apply` enforces load safety, not source strength. A valid load-safe package may apply even when guide depth is weak; source-depth gaps remain visible in `operator_summary.json`, `source_claim_gap_report.json`, and `strong_promotion_report.json`.
```

- [ ] **Step 8: Run docs tests again**

```powershell
$env:PYTHONPATH='src'
python -m pytest tests\test_docs_active_path.py tests\test_skill_files.py -q
```

  Expected after doc edits: tests pass.

- [ ] **Step 9: Commit Task 5**

```powershell
git add docs\operator\README.md docs\operator\source-backed-strong-closure.md tests\test_docs_active_path.py tests\test_skill_files.py
git commit -m "docs: document load-safe apply policy"
```

  Then commit the installed skill docs separately because they live outside the repo:

```powershell
git status --short
```

  The installed skill files are not in this repo. If the implementation worker also maintains a repo-local skill source later, update that source in a separate follow-up. For this plan, verify the installed skill files directly with the tests above.

---

### Task 6: Full Verification And Research Artifact Decision

**Files:**
- Read: `C:\Users\darbo\Documents\HSConfig\docs\research\2026-07-09-hsconfig-no-blocking-skill-audit\results\*.json`
- Maybe add: `C:\Users\darbo\Documents\HSConfig\docs\research\2026-07-09-hsconfig-no-blocking-skill-audit\`
- No code edits unless verification reveals a regression caused by Tasks 1-5

**Interfaces:**
- Consumes: all changes from Tasks 1-5
- Produces: verified repo with passing focused tests and updated Git state

- [ ] **Step 1: Validate the research JSONs**

```powershell
$fields='docs\research\2026-07-09-hsconfig-no-blocking-skill-audit\fields.yaml'
Get-ChildItem 'docs\research\2026-07-09-hsconfig-no-blocking-skill-audit\results\*.json' | ForEach-Object {
  python 'C:\Users\darbo\.codex\skills\research\validate_json.py' -f $fields -j $_.FullName
}
```

  Expected: every file reports `[PASS]` and `Coverage: 100.0%`.

- [ ] **Step 2: Run focused policy tests**

```powershell
$env:PYTHONPATH='src'
python -m pytest tests\test_apply_gate.py tests\test_operator_summary.py tests\test_operator_guidance.py tests\test_runtime_apply.py -q
```

  Expected: all tests pass.

- [ ] **Step 3: Run package/deck proof tests**

```powershell
$env:PYTHONPATH='src'
python -m pytest tests\test_archetype_fixture_e2e.py tests\test_supplemental_cute_warrior_load_safe.py tests\test_matrix_governance.py tests\test_source_informed_closure_contract.py -q
```

  Expected: all tests pass. Representative matrix remains 11 rows. CuteWarrior remains supplemental but has a load-safe prepare proof.

- [ ] **Step 4: Run docs and skill tests**

```powershell
$env:PYTHONPATH='src'
python -m pytest tests\test_docs_active_path.py tests\test_skill_files.py tests\test_cli_help.py -q
```

  Expected: docs no longer contain the old warning-policy claim. CLI help remains accurate.

- [ ] **Step 5: Run the wider test suite**

```powershell
$env:PYTHONPATH='src'
python -m pytest -q
```

  Expected: full suite passes. If the suite is too slow, capture the timeout and rerun the changed areas plus existing fixture matrix suites before stopping.

- [ ] **Step 6: Scan for stale active policy wording**

```powershell
rg -n "ALLOWED_WITH_WARNINGS is not runtime write permission|only valid source-informed apply lane|requires the explicit --allow-source-informed flag|blocks by default unless the package is source-backed ready" docs src tests 'C:\Users\darbo\.codex\skills\hsconfig'
```

  Expected: no active matches. Historical research/plans may mention old policy; if the command matches only old archived/research files, do not rewrite history. If it matches active operator docs, skill docs, source, or tests, update those files.

- [ ] **Step 7: Decide whether to commit the new research audit**

  If the research audit should become durable evidence for this policy wave, stage it:

```powershell
git add docs\research\2026-07-09-hsconfig-no-blocking-skill-audit
git commit -m "docs: add no-blocking apply policy research audit"
```

  If the repo policy prefers not to commit research artifacts, leave the directory untracked and mention it in the final response. Do not delete it unless the user explicitly asks.

- [ ] **Step 8: Commit remaining tracked changes if any are unstaged**

```powershell
git status --short
```

  If tracked implementation files remain modified:

```powershell
git add src tests docs
git commit -m "feat: make valid HSConfig packages load-safe applyable"
```

- [ ] **Step 9: Final git status**

```powershell
git status --short --branch
```

  Expected: branch is clean except for intentionally untracked research artifacts if Step 7 chose not to commit them.

---

## Self-Review

- Spec coverage: This plan covers the recommendation from the no-blocking audit: load-safe valid packages apply by default, semantic/source confidence becomes warning/reporting, invalid/load-unsafe packages still block, CuteWarrior gains a prepare-path proof, and docs plus installed skill wording are aligned.
- Scope check: The plan does not add replay parsing, HDT parsing, winrate validation, candidate promotion, post-run tuning, Presume, Concede, or new dependencies.
- Placeholder scan: The plan contains no placeholder tasks. Each task has concrete files, commands, expected outcomes, and code snippets.
- Type consistency: New terms are consistent across tasks: `runtime_load_safe`, `runtime_apply_mode=load_safe_apply`, `READY_TO_APPLY_WITH_WARNINGS`, and `ALLOWED_WITH_WARNINGS` as warning-bearing runtime permission for `VALID_PACKAGE`.
- Risk note: Task 5 edits installed skill files outside the repo. The repo tests must still verify those files so the deployed skill matches the code. If a future repo-local skill source is introduced, migrate those docs into repo tracking in a separate plan.

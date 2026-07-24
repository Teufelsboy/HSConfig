# HSConfig Source Candidate Contract Preflight Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one narrow contract-preflight visibility check for `source_candidate_plan.json` so HSConfig can prove the source-candidate plan remains diagnostic-only, non-promoting, non-blocking, and subordinate to `reports/operator_summary.json`.

**Architecture:** Extend the existing read-only `contract-preflight` payload instead of adding a runtime path, gameplay planner, log analyzer, or source-strength gate. The check reads existing operator documentation and `src/hsconfig/source_candidate_plan.py`, then reports a compact `source_candidate_plan_contract` object plus a boolean check key. The normal config path and apply authority stay unchanged.

**Tech Stack:** Python, pytest, existing HSConfig CLI, existing `contract_preflight` module, existing operator docs, JSON preflight payload.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig`.
- Refresh repository state before implementation: `git fetch --all --prune --tags`, then `python scripts\check_hsconfig_currentness.py --cwd . --json`.
- Keep the worktree clean at completion; no backup files, no generated runtime evidence, no uncommitted outputs.
- Keep HSConfig pre-run only.
- Do not add HSTuner, replay parsing, HDT parsing, Power.log parsing, winrate analysis, post-game tuning, or gameplay improvement claims.
- Do not encode HearthRanger play sequencing or assume HearthRanger misplays. HearthRanger remains the runtime actor.
- Do not create a new runtime apply authority. `reports/operator_summary.json` remains the only normal apply authority.
- Do not turn source quality, `SOURCE_BACKED_STRONG`, source-candidate planning, default-only visibility, source closure, or research status into apply blockers.
- `source_status_apply_blocking` must remain `false`.
- No hidden default-only success: default-only runtime surfaces remain visible diagnostic quality debt.
- Normal runtime output remains `GlobalValues.json`, `Mulligan.json`, per-card `<CARDID>.json`, and `Combo.json` only for exact source-backed combo sequence evidence.
- `Presume.json`, `Concede.json`, and aggregate `CardBehavior.json` stay outside the normal HSConfig path.
- Source candidate plans are acquisition guidance only: they may suggest URLs and queries, but they cannot promote, block, validate, apply, or write runtime config.
- Do not implement `source-find` in this plan. This plan only adds contract visibility for the already implemented source-candidate plan.

---

## File Structure

- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\contract_preflight.py`
  - Responsibility: expose a read-only `source_candidate_plan_visible` check and `source_candidate_plan_contract` payload.
- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\commands\contract_preflight.py`
  - Responsibility: preserve the new payload key in the CLI exception fallback schema.
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_contract_preflight.py`
  - Responsibility: prove the new preflight key, diagnostic-only payload, drift behavior, fallback schema, and no-write CLI behavior.
- Modify: `C:\Users\darbo\Documents\HSConfig\docs\operator\README.md`
  - Responsibility: document that optional contract preflight also checks source-candidate plan visibility without becoming an apply gate.

---

### Task 1: Add Failing Contract-Preflight Tests

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_contract_preflight.py`

**Interfaces:**
- Consumes: `build_contract_preflight(repo_root, git, skill_install_root) -> dict[str, object]`.
- Produces: assertions for `payload["checks"]["source_candidate_plan_visible"]` and `payload["source_candidate_plan_contract"]`.

- [ ] **Step 1: Add the source-candidate visibility success test**

Add this test after `test_contract_preflight_checks_configure_acceptance_route_contract`:

```python
def test_contract_preflight_checks_source_candidate_plan_visibility(
    tmp_path: Path,
) -> None:
    payload = build_contract_preflight(
        Path("."),
        git=_clean_git(),
        skill_install_root=_synced_install_root(tmp_path),
    )

    contract = payload["source_candidate_plan_contract"]

    assert payload["status"] == "PASS"
    assert payload["checks"]["source_candidate_plan_visible"] is True
    assert "source_candidate_plan_visible" not in payload["failures"]
    assert contract == {
        "status": "visible",
        "authority": "diagnostic_source_candidate_plan",
        "documentation_path": "docs/operator/source-builder-workflow.md",
        "operator_entrypoint_path": "docs/operator/README.md",
        "implementation_path": "src/hsconfig/source_candidate_plan.py",
        "runtime_apply_authority": "reports/operator_summary.json",
        "source_status_apply_blocking": False,
        "apply_blocking": False,
        "runtime_write_performed": False,
        "candidate_plan_can_promote": False,
        "candidate_plan_can_block_apply": False,
        "normal_path": (
            "source-manifest -> configure --online-source -> "
            "source-acquire/source-autopilot -> prepare"
        ),
        "notes": [
            "source_candidate_plan.json is acquisition guidance only.",
            "Candidate plans cannot promote or block runtime apply.",
            "reports/operator_summary.json remains the only normal apply authority.",
        ],
    }
```

- [ ] **Step 2: Add the source-candidate drift test**

Add this test after the success test:

```python
def test_contract_preflight_reports_attention_when_source_candidate_plan_visibility_drifts(
    tmp_path: Path,
) -> None:
    source_docs = Path("docs")
    target_docs = tmp_path / "docs"
    shutil.copytree(source_docs, target_docs)

    skill_root = tmp_path / ".agents" / "skills" / "hsconfig"
    shutil.copytree(Path(".agents") / "skills" / "hsconfig", skill_root)

    source_root = tmp_path / "src" / "hsconfig"
    source_root.mkdir(parents=True)
    shutil.copy2(
        Path("src") / "hsconfig" / "source_candidate_plan.py",
        source_root / "source_candidate_plan.py",
    )

    workflow_path = target_docs / "operator" / "source-builder-workflow.md"
    workflow_path.write_text(
        workflow_path.read_text(encoding="utf-8").replace(
            "The plan cannot promote, block apply, write runtime config, or replace `reports/operator_summary.json`.",
            "The plan can decide source status.",
        ),
        encoding="utf-8",
    )

    payload = build_contract_preflight(
        tmp_path,
        git=_clean_git(),
        skill_install_root=_synced_install_root(tmp_path),
    )

    assert payload["status"] == "ATTENTION"
    assert payload["checks"]["source_candidate_plan_visible"] is False
    assert "source_candidate_plan_visible" in payload["failures"]
    assert payload["source_candidate_plan_contract"]["status"] == "attention"
    assert payload["source_candidate_plan_contract"]["runtime_apply_authority"] == (
        "reports/operator_summary.json"
    )
    assert payload["source_candidate_plan_contract"]["source_status_apply_blocking"] is False
    assert payload["source_status_apply_blocking"] is False
    assert payload["diagnostic_only"] is True
```

- [ ] **Step 3: Add the CLI fallback schema assertion**

In `test_contract_preflight_runtime_error_fallback_preserves_normal_payload_schema`, add these assertions after `payload = json.loads(captured.out)`:

```python
    assert payload["source_candidate_plan_contract"] == {
        "status": "attention",
        "authority": "diagnostic_source_candidate_plan",
        "documentation_path": "docs/operator/source-builder-workflow.md",
        "operator_entrypoint_path": "docs/operator/README.md",
        "implementation_path": "src/hsconfig/source_candidate_plan.py",
        "runtime_apply_authority": "reports/operator_summary.json",
        "source_status_apply_blocking": False,
        "apply_blocking": False,
        "runtime_write_performed": False,
        "candidate_plan_can_promote": False,
        "candidate_plan_can_block_apply": False,
        "normal_path": (
            "source-manifest -> configure --online-source -> "
            "source-acquire/source-autopilot -> prepare"
        ),
        "notes": [
            "source candidate plan contract preflight unavailable",
            "reports/operator_summary.json remains the only normal apply authority.",
        ],
    }
```

- [ ] **Step 4: Run the new tests and verify they fail for the expected reason**

Run:

```powershell
python -m pytest -p no:cacheprovider tests\test_contract_preflight.py::test_contract_preflight_checks_source_candidate_plan_visibility tests\test_contract_preflight.py::test_contract_preflight_reports_attention_when_source_candidate_plan_visibility_drifts tests\test_contract_preflight.py::test_contract_preflight_runtime_error_fallback_preserves_normal_payload_schema -q
```

Expected: FAIL because `source_candidate_plan_visible` and `source_candidate_plan_contract` do not exist yet.

---

### Task 2: Implement Source-Candidate Contract Visibility

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\contract_preflight.py`
- Modify: `C:\Users\darbo\Documents\HSConfig\docs\operator\README.md`

**Interfaces:**
- Consumes: existing `_read(path: Path) -> str` and `build_contract_preflight(...)`.
- Produces: `payload["checks"]["source_candidate_plan_visible"] -> bool`.
- Produces: `payload["source_candidate_plan_contract"] -> dict[str, object]`.

- [ ] **Step 1: Extend `EXPECTED_CHECK_KEYS`**

In `C:\Users\darbo\Documents\HSConfig\src\hsconfig\contract_preflight.py`, add this key immediately after `"source_status_nonblocking_visible"`:

```python
    "source_candidate_plan_visible",
```

- [ ] **Step 2: Add the source-candidate plan helper functions**

Add these helpers after `_config_proof_summary_visible`:

```python
def _source_candidate_plan_contract_visible(
    operator_text: str,
    source_builder_workflow_text: str,
    source_candidate_plan_text: str,
) -> bool:
    operator_terms = (
        "source-candidate plan visibility",
        "source_candidate_plan.json",
        "does not replace `reports/operator_summary.json`",
    )
    workflow_terms = (
        "source_candidate_plan.json is deterministic pre-acquisition guidance",
        "Queries are for Codex/operator research only",
        "The plan cannot promote, block apply, write runtime config, or replace `reports/operator_summary.json`.",
    )
    implementation_terms = (
        '"authority": "diagnostic_source_candidate_plan"',
        '"apply_blocking": False',
        '"runtime_write_performed": False',
        '"source_status_apply_blocking": False',
        '"candidate_plan_can_promote": False',
        '"candidate_plan_can_block_apply": False',
        '"normal_apply_authority": _NORMAL_APPLY_AUTHORITY',
    )
    return (
        all(term in operator_text for term in operator_terms)
        and all(term in source_builder_workflow_text for term in workflow_terms)
        and all(term in source_candidate_plan_text for term in implementation_terms)
    )


def _source_candidate_plan_contract_payload(visible: bool) -> dict[str, object]:
    return {
        "status": "visible" if visible else "attention",
        "authority": "diagnostic_source_candidate_plan",
        "documentation_path": "docs/operator/source-builder-workflow.md",
        "operator_entrypoint_path": "docs/operator/README.md",
        "implementation_path": "src/hsconfig/source_candidate_plan.py",
        "runtime_apply_authority": "reports/operator_summary.json",
        "source_status_apply_blocking": False,
        "apply_blocking": False,
        "runtime_write_performed": False,
        "candidate_plan_can_promote": False,
        "candidate_plan_can_block_apply": False,
        "normal_path": (
            "source-manifest -> configure --online-source -> "
            "source-acquire/source-autopilot -> prepare"
        ),
        "notes": [
            "source_candidate_plan.json is acquisition guidance only.",
            "Candidate plans cannot promote or block runtime apply.",
            "reports/operator_summary.json remains the only normal apply authority.",
        ],
    }
```

- [ ] **Step 3: Read the source-candidate plan docs and code in `build_contract_preflight`**

In `build_contract_preflight`, replace the current operator text block:

```python
    operator_text = _read(root / "docs" / "operator" / "README.md")
    combined = "\n".join([skill_text, workflow_text, checklist_text, operator_text])
```

with:

```python
    operator_text = _read(root / "docs" / "operator" / "README.md")
    source_builder_workflow_text = _read(
        root / "docs" / "operator" / "source-builder-workflow.md"
    )
    source_candidate_plan_text = _read(
        root / "src" / "hsconfig" / "source_candidate_plan.py"
    )
    combined = "\n".join(
        [
            skill_text,
            workflow_text,
            checklist_text,
            operator_text,
            source_builder_workflow_text,
            source_candidate_plan_text,
        ]
    )
```

- [ ] **Step 4: Add the check and payload**

Before the `checks = { ... }` literal in `build_contract_preflight`, add:

```python
    source_candidate_plan_visible = _source_candidate_plan_contract_visible(
        operator_text,
        source_builder_workflow_text,
        source_candidate_plan_text,
    )
```

Inside the `checks` dictionary, add this entry immediately after `"source_status_nonblocking_visible"`:

```python
        "source_candidate_plan_visible": source_candidate_plan_visible,
```

Inside the final `payload` dictionary, add this entry immediately after `"installed_skill_sync": installed_skill_sync,`:

```python
        "source_candidate_plan_contract": _source_candidate_plan_contract_payload(
            source_candidate_plan_visible
        ),
```

- [ ] **Step 5: Update operator documentation**

In `C:\Users\darbo\Documents\HSConfig\docs\operator\README.md`, replace the Optional Contract Preflight paragraph:

```markdown
It checks currentness, installed-skill sync, skill reference routing,
source-status non-blocking policy, no-default-only visibility, supported runtime
surfaces, negative-scope boundaries, and the research-context lock around
`docs/research/current-truth.md`. The historical research outline files remain
```

with:

```markdown
It checks currentness, installed-skill sync, skill reference routing,
source-status non-blocking policy, source-candidate plan visibility,
no-default-only visibility, supported runtime surfaces, negative-scope
boundaries, and the research-context lock around `docs/research/current-truth.md`.
The `source_candidate_plan.json` check is diagnostic-only and does not replace
`reports/operator_summary.json`. The historical research outline files remain
```

- [ ] **Step 6: Run the focused tests**

Run:

```powershell
python -m pytest -p no:cacheprovider tests\test_contract_preflight.py::test_contract_preflight_checks_source_candidate_plan_visibility tests\test_contract_preflight.py::test_contract_preflight_reports_attention_when_source_candidate_plan_visibility_drifts -q
```

Expected: PASS.

- [ ] **Step 7: Commit Task 2**

Run:

```powershell
git add src\hsconfig\contract_preflight.py docs\operator\README.md tests\test_contract_preflight.py
git commit -m "test: expose source candidate plan preflight contract"
```

---

### Task 3: Preserve CLI Error Fallback Schema

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\commands\contract_preflight.py`
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_contract_preflight.py`

**Interfaces:**
- Consumes: `EXPECTED_CHECK_KEYS`.
- Produces: fallback JSON that includes `source_candidate_plan_contract` when `build_contract_preflight()` raises.

- [ ] **Step 1: Add the CLI fallback helper**

In `C:\Users\darbo\Documents\HSConfig\src\hsconfig\commands\contract_preflight.py`, add this helper after `_unavailable_research_context_payload`:

```python
def _unavailable_source_candidate_plan_contract_payload() -> dict[str, object]:
    return {
        "status": "attention",
        "authority": "diagnostic_source_candidate_plan",
        "documentation_path": "docs/operator/source-builder-workflow.md",
        "operator_entrypoint_path": "docs/operator/README.md",
        "implementation_path": "src/hsconfig/source_candidate_plan.py",
        "runtime_apply_authority": "reports/operator_summary.json",
        "source_status_apply_blocking": False,
        "apply_blocking": False,
        "runtime_write_performed": False,
        "candidate_plan_can_promote": False,
        "candidate_plan_can_block_apply": False,
        "normal_path": (
            "source-manifest -> configure --online-source -> "
            "source-acquire/source-autopilot -> prepare"
        ),
        "notes": [
            "source candidate plan contract preflight unavailable",
            "reports/operator_summary.json remains the only normal apply authority.",
        ],
    }
```

- [ ] **Step 2: Add the fallback payload key**

In the `except Exception as exc:` fallback payload inside `run_contract_preflight_command`, add this key immediately after `"installed_skill_sync": _unavailable_installed_skill_payload(...),`:

```python
            "source_candidate_plan_contract": (
                _unavailable_source_candidate_plan_contract_payload()
            ),
```

- [ ] **Step 3: Run the fallback test**

Run:

```powershell
python -m pytest -p no:cacheprovider tests\test_contract_preflight.py::test_contract_preflight_runtime_error_fallback_preserves_normal_payload_schema -q
```

Expected: PASS.

- [ ] **Step 4: Run all contract-preflight tests**

Run:

```powershell
python -m pytest -p no:cacheprovider tests\test_contract_preflight.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 3**

Run:

```powershell
git add src\hsconfig\commands\contract_preflight.py tests\test_contract_preflight.py
git commit -m "fix: preserve source candidate preflight fallback"
```

---

### Task 4: Run Guardrails and Finish Clean

**Files:**
- Verify only: `C:\Users\darbo\Documents\HSConfig`

**Interfaces:**
- Consumes: existing HSConfig guardrail commands.
- Produces: clean current branch with no uncommitted files.

- [ ] **Step 1: Run contract preflight JSON**

Run:

```powershell
python -m hsconfig.cli contract-preflight --repo-root . --json
```

Expected:

```json
{
  "status": "PASS",
  "failures": [],
  "runtime_apply_authority": "reports/operator_summary.json",
  "source_status_apply_blocking": false,
  "diagnostic_only": true
}
```

Also verify these fields in the emitted JSON:

```json
{
  "checks": {
    "source_candidate_plan_visible": true
  },
  "source_candidate_plan_contract": {
    "status": "visible",
    "authority": "diagnostic_source_candidate_plan",
    "runtime_apply_authority": "reports/operator_summary.json",
    "source_status_apply_blocking": false,
    "apply_blocking": false,
    "runtime_write_performed": false,
    "candidate_plan_can_promote": false,
    "candidate_plan_can_block_apply": false
  }
}
```

- [ ] **Step 2: Run focused source-candidate and configure regression tests**

Run:

```powershell
python -m pytest -p no:cacheprovider tests\test_contract_preflight.py tests\test_source_candidate_plan.py tests\test_source_manifest_cli.py tests\test_configure_online_source.py tests\test_configure_auto_source.py -q
```

Expected: PASS.

- [ ] **Step 3: Run the project guardrail**

Run:

```powershell
python scripts\check_contract_guardrails.py
```

Expected: PASS with no source-status apply blocker and installed skill sync still current.

- [ ] **Step 4: Confirm no generated dirty files**

Run:

```powershell
git status --short --branch --untracked-files=all
```

Expected: only the branch line, with no modified or untracked files.

- [ ] **Step 5: Push the completed branch**

Run:

```powershell
git push
```

Expected: push succeeds and the branch remains clean against its upstream.

---

## Self-Review Checklist

- Spec coverage: The plan implements only the narrow source-candidate contract-preflight visibility improvement. It does not implement `source-find`, gameplay sequencing, log parsing, HSTuner, or another source/apply gate.
- Placeholder scan: The plan contains no deferred implementation slots; every code step includes concrete code.
- Type consistency: `source_candidate_plan_contract` is always a `dict[str, object]`; `source_candidate_plan_visible` is always a boolean under `payload["checks"]`; CLI fallback preserves the same top-level schema as the normal payload.
- Authority check: `reports/operator_summary.json` remains the only normal apply authority in every new payload and test.
- Non-blocking check: `source_status_apply_blocking` remains `False`; `apply_blocking` remains `False`; `runtime_write_performed` remains `False`.
- Worktree check: Implementation must finish with `git status --short --branch --untracked-files=all` showing no dirty files.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-24-hsconfig-source-candidate-contract-preflight.md`. Two execution options:

**1. Subagent-Driven (recommended)** - dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** - execute tasks in this session using executing-plans, batch execution with checkpoints.

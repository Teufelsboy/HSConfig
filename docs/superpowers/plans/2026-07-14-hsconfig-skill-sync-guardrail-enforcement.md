# HSConfig Skill Sync Guardrail Enforcement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep the installed HSConfig skill, source-contract sentinel, and no-second-gate contract synchronized so the repo and Codex runtime use the same source/runtime authority rules.

**Architecture:** Do not change the HSConfig runtime architecture. Add a small local guardrail runner, CI coverage, one structured drift-reporting hardening, and concise operator documentation. `reports/operator_summary.json` remains the only normal apply authority; source-contract diagnostics remain diagnostic-only.

**Tech Stack:** Python 3, pytest, existing `hsconfig` package, existing `scripts/sync_installed_skill.py`, GitHub Actions YAML.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig`.
- Do not add a new runtime writer, apply gate, source-strength permission layer, or normal operator command.
- Keep `reports/operator_summary.json` as the only normal apply authority.
- Keep `source_contract_audit.json`, `source_to_runtime_explainability.json`, `contract_spine_rows`, and `source_advisory_gate` diagnostic-only.
- Keep `Presume.json` and `Concede.json` outside the normal HSConfig output path.
- Keep warning-only mechanics, thin guide evidence, unresolved option identities, and source-depth gaps non-blocking for valid load-safe packages.
- Keep Darkbishop-style start-of-game and `hero_power_transform` semantics out of `Mulligan.json` unless an explicit opening-hand mulligan claim exists.
- Do not introduce new dependencies.

---

## File Structure

- Create `scripts/check_contract_guardrails.py`
  - Runs the local installed-skill sync check, contract-spine sentinel, and focused pytest boundary suite.
  - Accepts `--skill-install-root` so CI can use a temporary install root while local developers use `C:\Users\darbo\.codex\skills`.
- Create `tests/test_check_contract_guardrails.py`
  - Tests the guardrail command list and failure handling without running the expensive real commands.
- Modify `tests/test_source_claim_family_registry.py`
  - Add a regression that a new policy claim kind without a negative boundary reports structured drift instead of raising `KeyError`.
- Modify `src/hsconfig/source_claim_family_registry.py`
  - Replace direct negative-boundary indexing with structured missing-boundary reporting.
- Create `.github/workflows/contract-guardrails.yml`
  - CI proof for sync script, sentinel, and focused boundary tests.
- Modify `README.md`
  - Add one short guardrail command line.
- Modify `docs/operator/README.md`
  - Add one short developer guardrail section. Do not widen normal operator path.

---

### Task 1: Add A Local Contract Guardrail Runner

**Files:**
- Create: `scripts/check_contract_guardrails.py`
- Create: `tests/test_check_contract_guardrails.py`

**Interfaces:**
- Consumes:
  - `scripts/sync_installed_skill.py --check --install-root <path>`
  - `python -m hsconfig.cli contract-spine-sentinel --json`
  - `python -m pytest ...focused tests...`
- Produces:
  - CLI command: `python scripts/check_contract_guardrails.py [--skill-install-root <path>]`
  - Function: `guardrail_commands(repo_root: Path, skill_install_root: Path) -> tuple[GuardrailCommand, ...]`
  - Function: `run_guardrails(repo_root: Path, skill_install_root: Path, runner: Callable[..., subprocess.CompletedProcess[str]]) -> int`

- [ ] **Step 1: Write failing tests**

Create `tests/test_check_contract_guardrails.py`:

```python
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from scripts.check_contract_guardrails import (
    GuardrailCommand,
    guardrail_commands,
    run_guardrails,
)


def test_guardrail_commands_include_skill_sync_sentinel_and_boundary_suite(tmp_path):
    repo_root = tmp_path
    skill_root = tmp_path / "skills"

    commands = guardrail_commands(repo_root, skill_root)
    names = [command.name for command in commands]

    assert names == [
        "installed skill sync",
        "contract spine sentinel",
        "focused contract boundary tests",
    ]
    assert commands[0].argv == (
        sys.executable,
        str(repo_root / "scripts" / "sync_installed_skill.py"),
        "--check",
        "--install-root",
        str(skill_root),
    )
    assert commands[1].argv == (
        sys.executable,
        "-m",
        "hsconfig.cli",
        "contract-spine-sentinel",
        "--json",
    )
    assert commands[2].argv[:3] == (sys.executable, "-m", "pytest")
    assert "tests/test_apply_authority_boundary.py" in commands[2].argv
    assert "tests/test_source_claim_family_registry.py" in commands[2].argv


def test_run_guardrails_stops_at_first_failure(tmp_path, capsys):
    repo_root = tmp_path
    skill_root = tmp_path / "skills"
    calls: list[tuple[str, ...]] = []

    def fake_runner(argv, **kwargs):
        calls.append(tuple(argv))
        return subprocess.CompletedProcess(argv, 7)

    exit_code = run_guardrails(repo_root, skill_root, runner=fake_runner)

    assert exit_code == 7
    assert len(calls) == 1
    captured = capsys.readouterr()
    assert "FAILED: installed skill sync" in captured.err


def test_run_guardrails_runs_all_commands_when_successful(tmp_path, capsys):
    repo_root = tmp_path
    skill_root = tmp_path / "skills"
    calls: list[tuple[str, ...]] = []

    def fake_runner(argv, **kwargs):
        calls.append(tuple(argv))
        return subprocess.CompletedProcess(argv, 0)

    exit_code = run_guardrails(repo_root, skill_root, runner=fake_runner)

    assert exit_code == 0
    assert len(calls) == 3
    captured = capsys.readouterr()
    assert "OK: installed skill sync" in captured.out
    assert "OK: contract spine sentinel" in captured.out
    assert "OK: focused contract boundary tests" in captured.out
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest -q tests/test_check_contract_guardrails.py
```

Expected:

```text
ModuleNotFoundError: No module named 'scripts.check_contract_guardrails'
```

- [ ] **Step 3: Write minimal implementation**

Create `scripts/check_contract_guardrails.py`:

```python
from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SKILL_INSTALL_ROOT = Path.home() / ".codex" / "skills"

FOCUSED_CONTRACT_TESTS = (
    "tests/test_source_claim_family_registry.py",
    "tests/test_contract_spine_sentinel.py",
    "tests/test_contract_spine_sentinel_cli.py",
    "tests/test_contract_spine_sentinel_docs.py",
    "tests/test_apply_authority_boundary.py",
    "tests/test_no_second_gate_contract.py",
    "tests/test_semantic_runtime_negative_boundaries.py",
    "tests/test_universal_wild_no_block_matrix.py",
    "tests/test_operator_docs_contract_policy.py",
    "tests/test_docs_active_path.py",
    "tests/test_claim_kind_runtime_contract.py",
    "tests/test_card_behavior_router.py",
    "tests/test_mechanic_support.py",
)


@dataclass(frozen=True)
class GuardrailCommand:
    name: str
    argv: tuple[str, ...]


def guardrail_commands(
    repo_root: Path,
    skill_install_root: Path,
) -> tuple[GuardrailCommand, ...]:
    return (
        GuardrailCommand(
            "installed skill sync",
            (
                sys.executable,
                str(repo_root / "scripts" / "sync_installed_skill.py"),
                "--check",
                "--install-root",
                str(skill_install_root),
            ),
        ),
        GuardrailCommand(
            "contract spine sentinel",
            (
                sys.executable,
                "-m",
                "hsconfig.cli",
                "contract-spine-sentinel",
                "--json",
            ),
        ),
        GuardrailCommand(
            "focused contract boundary tests",
            (
                sys.executable,
                "-m",
                "pytest",
                "-q",
                *FOCUSED_CONTRACT_TESTS,
            ),
        ),
    )


def run_guardrails(
    repo_root: Path,
    skill_install_root: Path,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> int:
    for command in guardrail_commands(repo_root, skill_install_root):
        result = runner(command.argv, cwd=repo_root)
        if result.returncode != 0:
            print(
                f"FAILED: {command.name} (exit {result.returncode})",
                file=sys.stderr,
            )
            return int(result.returncode)
        print(f"OK: {command.name}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run HSConfig skill-sync and contract-spine guardrails."
    )
    parser.add_argument(
        "--skill-install-root",
        type=Path,
        default=DEFAULT_SKILL_INSTALL_ROOT,
        help="Root directory that contains installed skills.",
    )
    args = parser.parse_args(argv)

    return run_guardrails(REPO_ROOT, args.skill_install_root)


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```powershell
python -m pytest -q tests/test_check_contract_guardrails.py
```

Expected:

```text
3 passed
```

- [ ] **Step 5: Commit**

```powershell
git add scripts/check_contract_guardrails.py tests/test_check_contract_guardrails.py
git commit -m "ci: add contract guardrail runner"
```

---

### Task 2: Harden Missing Negative-Boundary Drift Reporting

**Files:**
- Modify: `tests/test_source_claim_family_registry.py`
- Modify: `src/hsconfig/source_claim_family_registry.py`

**Interfaces:**
- Consumes:
  - `source_contract_policy_by_claim_kind() -> dict[str, dict[str, object]]`
- Produces:
  - `build_claim_family_registry_report()["problems"]` contains `{"check": "missing_negative_boundary", "claim_kind": "<kind>"}` when a policy claim kind has no negative boundary.

- [ ] **Step 1: Write the failing regression test**

Append to `tests/test_source_claim_family_registry.py`:

```python
def test_claim_family_registry_reports_missing_negative_boundary_as_drift(monkeypatch):
    from hsconfig import source_claim_family_registry as registry_mod

    original = registry_mod.source_contract_policy_by_claim_kind

    def policy_with_new_claim_kind():
        policy = original()
        policy["new_future_claim_kind"] = {
            "lane": "report_only",
            "allowed_surfaces": (),
            "operator_meaning": "Future source claim without a runtime surface.",
        }
        return policy

    monkeypatch.setattr(
        registry_mod,
        "source_contract_policy_by_claim_kind",
        policy_with_new_claim_kind,
    )

    report = registry_mod.build_claim_family_registry_report()

    assert report["status"] == "drift_detected"
    assert {
        "check": "missing_negative_boundary",
        "claim_kind": "new_future_claim_kind",
    } in report["problems"]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest -q tests/test_source_claim_family_registry.py::test_claim_family_registry_reports_missing_negative_boundary_as_drift
```

Expected:

```text
KeyError: 'new_future_claim_kind'
```

- [ ] **Step 3: Write minimal implementation**

Modify `src/hsconfig/source_claim_family_registry.py` inside `claim_family_registry()`:

```python
def claim_family_registry() -> dict[str, dict[str, Any]]:
    """Return diagnostic guardrails derived from the source-contract policy."""
    policy = source_contract_policy_by_claim_kind()
    return {
        claim_kind: {
            "claim_kind": claim_kind,
            "policy_lane": row["lane"],
            "allowed_surfaces": tuple(row["allowed_surfaces"]),
            "conflict_family": _CONFLICT_FAMILY_BY_CLAIM_KIND.get(claim_kind, "none"),
            "negative_boundary": _NEGATIVE_BOUNDARY_BY_CLAIM_KIND.get(claim_kind, ""),
            "operator_gate_impact": DIAGNOSTIC_AUTHORITY,
            "normal_apply_gate": NORMAL_APPLY_GATE,
        }
        for claim_kind, row in sorted(policy.items())
    }
```

- [ ] **Step 4: Run targeted tests**

Run:

```powershell
python -m pytest -q tests/test_source_claim_family_registry.py
```

Expected:

```text
4 passed
```

- [ ] **Step 5: Commit**

```powershell
git add src/hsconfig/source_claim_family_registry.py tests/test_source_claim_family_registry.py
git commit -m "test: report missing claim negative boundaries"
```

---

### Task 3: Add Repo-Native Contract Guardrail CI

**Files:**
- Create: `.github/workflows/contract-guardrails.yml`

**Interfaces:**
- Consumes:
  - `scripts/sync_installed_skill.py`
  - `scripts/check_contract_guardrails.py`
  - pytest boundary suite
- Produces:
  - GitHub Actions workflow named `contract-guardrails`

- [ ] **Step 1: Create workflow**

Create `.github/workflows/contract-guardrails.yml`:

```yaml
name: contract-guardrails

on:
  pull_request:
  push:
    branches:
      - main
      - "codex/**"

jobs:
  contract-guardrails:
    runs-on: windows-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install package
        run: python -m pip install -e .

      - name: Seed temporary installed skill
        run: python scripts\sync_installed_skill.py --install-root .guardrail-skills

      - name: Run contract guardrails
        run: python scripts\check_contract_guardrails.py --skill-install-root .guardrail-skills
```

- [ ] **Step 2: Run a local YAML presence check**

Run:

```powershell
Test-Path .github\workflows\contract-guardrails.yml
```

Expected:

```text
True
```

- [ ] **Step 3: Run the workflow command sequence locally**

Run:

```powershell
Remove-Item -Recurse -Force .guardrail-skills -ErrorAction SilentlyContinue
python scripts\sync_installed_skill.py --install-root .guardrail-skills
python scripts\check_contract_guardrails.py --skill-install-root .guardrail-skills
Remove-Item -Recurse -Force .guardrail-skills
```

Expected:

```text
Synced HSConfig skill to .guardrail-skills\hsconfig
OK: installed skill sync
OK: contract spine sentinel
OK: focused contract boundary tests
```

- [ ] **Step 4: Commit**

```powershell
git add .github/workflows/contract-guardrails.yml
git commit -m "ci: enforce hsconfig contract guardrails"
```

---

### Task 4: Document The Guardrail Without Widening Operator Flow

**Files:**
- Modify: `README.md`
- Modify: `docs/operator/README.md`

**Interfaces:**
- Consumes:
  - `python scripts\check_contract_guardrails.py`
  - `python scripts\sync_installed_skill.py`
- Produces:
  - One short developer guardrail section.
  - No new normal operator step for deck users.

- [ ] **Step 1: Update README**

Add after the existing skill sync sentence in `README.md`:

~~~markdown
Developer contract guardrail:

```powershell
python scripts\check_contract_guardrails.py
```

This checks installed-skill sync, the contract-spine sentinel, and the focused boundary suite. It is a developer drift check, not a second operator gate.
~~~

- [ ] **Step 2: Update operator docs**

Add this short section near the existing developer drift check in `docs/operator/README.md`:

~~~markdown
## Developer Guardrail

Run this after changing source-contract, skill, apply, report ownership, or mechanic-lowering code:

```powershell
python scripts\check_contract_guardrails.py
```

The command checks installed-skill sync, `hsconfig contract-spine-sentinel --json`, and the focused boundary tests. It is diagnostic only. Normal deck configuration still starts with `hsconfig configure`, and `reports/operator_summary.json` remains the only normal apply authority.
~~~

- [ ] **Step 3: Run docs policy tests**

Run:

```powershell
python -m pytest -q tests/test_docs_active_path.py tests/test_operator_docs_contract_policy.py
```

Expected:

```text
all tests pass
```

- [ ] **Step 4: Commit**

```powershell
git add README.md docs/operator/README.md
git commit -m "docs: document contract guardrail check"
```

---

### Task 5: Sync The Installed Skill And Run Final Verification

**Files:**
- External local write: `C:\Users\darbo\.codex\skills\hsconfig`
- No tracked repo file should change in this task.

**Interfaces:**
- Consumes:
  - Repo skill source at `.agents/skills/hsconfig`
  - `scripts/sync_installed_skill.py`
  - `scripts/check_contract_guardrails.py`
- Produces:
  - Installed HSConfig skill in sync with repo.
  - Clean final verification.

- [ ] **Step 1: Sync installed skill**

Run:

```powershell
python scripts\sync_installed_skill.py
```

Expected:

```text
Synced HSConfig skill to C:\Users\darbo\.codex\skills\hsconfig
```

- [ ] **Step 2: Verify installed skill sync**

Run:

```powershell
python scripts\sync_installed_skill.py --check
```

Expected:

```text
HSConfig skill is in sync: C:\Users\darbo\.codex\skills\hsconfig
```

- [ ] **Step 3: Run the new guardrail command**

Run:

```powershell
python scripts\check_contract_guardrails.py
```

Expected:

```text
OK: installed skill sync
OK: contract spine sentinel
OK: focused contract boundary tests
```

- [ ] **Step 4: Run focused verification directly**

Run:

```powershell
python -m hsconfig.cli contract-spine-sentinel --json
python -m pytest -q tests/test_check_contract_guardrails.py tests/test_source_claim_family_registry.py tests/test_contract_spine_sentinel.py tests/test_contract_spine_sentinel_cli.py tests/test_contract_spine_sentinel_docs.py tests/test_apply_authority_boundary.py tests/test_no_second_gate_contract.py tests/test_semantic_runtime_negative_boundaries.py tests/test_universal_wild_no_block_matrix.py tests/test_operator_docs_contract_policy.py tests/test_docs_active_path.py tests/test_claim_kind_runtime_contract.py tests/test_card_behavior_router.py tests/test_mechanic_support.py
```

Expected:

```text
contract-spine-sentinel status is clean
all listed pytest tests pass
```

- [ ] **Step 5: Check repository status**

Run:

```powershell
git status --short --branch
```

Expected:

```text
## <branch>...origin/<branch>
```

No untracked `.guardrail-skills` directory should remain.

- [ ] **Step 6: Final commit if verification required follow-up edits**

If Task 5 reveals small follow-up edits:

```powershell
git add <changed files>
git commit -m "ci: finalize hsconfig guardrails"
```

If no follow-up edits were needed, do not create an empty commit.

---

## Self-Review

- Spec coverage:
  - Skill sync drift is covered by Tasks 1, 3, and 5.
  - Contract-spine sentinel enforcement is covered by Tasks 1, 3, and 5.
  - Missing negative-boundary structured drift is covered by Task 2.
  - Operator docs stay narrow and single-gate in Task 4.
  - No new runtime writer, no new apply gate, no new source-strength permission layer.
- Placeholder scan:
  - No unfinished-marker or unresolved placeholder steps.
  - Every code-changing step includes exact code or exact command.
- Type consistency:
  - `GuardrailCommand`, `guardrail_commands`, and `run_guardrails` are introduced in Task 1 and used only by Task 1 tests.
  - `source_claim_family_registry.claim_family_registry()` still returns the existing registry shape.
  - `build_claim_family_registry_report()` continues to use `_registry_problems()`.

## Execution Handoff

Plan complete. Recommended execution mode: **Subagent-Driven**.

Reason: the tasks are independent enough for a worker/reviewer rhythm:

1. Guardrail runner and tests.
2. Negative-boundary drift hardening.
3. CI workflow.
4. Docs.
5. Local skill sync and verification.

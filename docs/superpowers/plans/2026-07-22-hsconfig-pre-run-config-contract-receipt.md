# HSConfig Pre-Run Config Contract Receipt Implementation Plan

> **For:** HSConfig source/contract logic hardening, no-default-only visibility, and slim autonomous config-generation assurance.
> **Target repo:** `C:\Users\darbo\Documents\HSConfig`
> **Execution mode:** Subagent-driven, with one implementation writer and read-only review agents.
> **Created:** 2026-07-22

This plan is intentionally narrow. It does not add gameplay tuning, log analysis, HSTuner coupling, online-source promotion logic, or a new runtime gate. It makes the already existing configure handoff objectively visible as a small pre-run receipt, then guards that wording and contract surface with tests.

## Goal

After `hsconfig configure`, an operator should have one compact place to confirm that the generated package is usable without guessing:

- `acceptance_summary` says whether the config can be used now.
- `handoff_contract` is explicitly named and documented as the **pre-run config contract receipt**.
- `operator_summary.json` remains the only normal apply/runtime authority.
- no default-only runtime success can be silent.
- forbidden normal surfaces such as `Presume.json` and `Concede.json` remain drift.
- source-to-runtime trace health stays diagnostic and non-blocking.
- effect-only cards such as Darkbishop Benedictus cannot become mulligan keeps without explicit opening-hand source text.

The result should be a better operator and skill contract, not a broader system.

## Current Observations

- `.agents/skills/hsconfig/SKILL.md` already routes normal work through `hsconfig configure`.
- The skill already tells the operator to inspect `<out>/configure_summary.json.acceptance_summary`, `<out>/configure_summary.json.handoff_contract`, `<out>/configure_summary.json.config_proof_summary`, and `<out>/configure_summary.json.config_quality_summary`.
- `tests/test_skill_files.py` enforces compact skill/workflow files with `< 80` lines, so implementation must replace wording in-place rather than add long new sections.
- `src/hsconfig/contract_preflight.py` already checks the important source/contract invariants, including:
  - single operator authority
  - source status non-blocking
  - no-default-only visibility
  - runtime surface boundary
  - Darkbishop effect-not-mulligan boundary
  - diagnostic-only research status
- The missing slim improvement is that `contract-preflight` does not yet verify the explicit operator concept: `configure_summary.json.handoff_contract` as the **pre-run config contract receipt**.

## Non-Goals

- Do not inspect runtime logs.
- Do not use HSTuner.
- Do not add winrate, replay, or gameplay-order inference.
- Do not change generated runtime JSON semantics unless an existing test exposes drift.
- Do not make `SOURCE_BACKED_STRONG` an apply gate.
- Do not treat missing source coverage as a blocker for valid load-safe deck packages.
- Do not add backup files, generated scratch files, or long historical docs.
- Do not create another operator gate beside `reports/operator_summary.json`.

## Implementation Strategy

Use tests-first and keep the implementation small:

1. Add a failing docs/skill test for the new receipt wording.
2. Add a failing `contract-preflight` test/key for receipt visibility.
3. Update only the compact wording in skill/operator docs and workflow references.
4. Add one small helper in `contract_preflight.py`.
5. Sync the installed `hsconfig` skill.
6. Run focused verification.
7. Commit the plan/implementation so the worktree is clean.

## Tasks

### Task 1: Preflight Currentness And Clean Base

Run from `C:\Users\darbo\Documents\HSConfig`:

```powershell
git fetch --all --prune --tags
python scripts\check_hsconfig_currentness.py --cwd . --json
git status --short --branch
```

Acceptance:

- Worktree is clean before implementation.
- Branch is not behind `origin/main`.
- No untracked generated artifacts are present.

### Task 2: Add Failing Skill/Docs Receipt Test

Edit `tests/test_skill_files.py`.

Add one focused test near the existing configure-summary tests:

```python
def test_skill_and_operator_docs_name_pre_run_config_contract_receipt() -> None:
    active_paths = [
        REPO_ROOT / ".agents" / "skills" / "hsconfig" / "SKILL.md",
        REPO_ROOT
        / ".agents"
        / "skills"
        / "hsconfig"
        / "references"
        / "workflow.md",
        REPO_ROOT / "docs" / "operator" / "README.md",
    ]

    required = [
        "pre-run config contract receipt",
        "configure_summary.json.handoff_contract",
        "diagnostic-only handoff proof",
        "single authority",
        "no-default-only status",
        "Darkbishop boundary",
        "does not replace `reports/operator_summary.json`",
    ]

    for path in active_paths:
        text = path.read_text(encoding="utf-8")
        for phrase in required:
            assert phrase in text, f"{path}: {phrase}"
```

Expected first result:

```powershell
python -m pytest tests\test_skill_files.py -k pre_run_config_contract_receipt
```

This should fail until the wording is added.

### Task 3: Add Failing Contract-Preflight Receipt Test

Edit `tests/test_contract_preflight.py`.

Add one compact test near `test_contract_preflight_checks_configure_acceptance_route_contract`:

```python
def test_contract_preflight_checks_pre_run_config_contract_receipt_visibility(
    tmp_path: Path,
) -> None:
    payload = build_contract_preflight(
        Path("."),
        git=_clean_git(),
        skill_install_root=_synced_install_root(tmp_path),
    )

    assert payload["status"] == "PASS"
    assert payload["checks"]["pre_run_config_contract_receipt_visible"] is True
    assert "pre_run_config_contract_receipt_visible" not in payload["failures"]
```

Expected first result:

```powershell
python -m pytest tests\test_contract_preflight.py -k pre_run_config_contract_receipt
```

This should fail until `contract_preflight.py` exposes the new key.

### Task 4: Add Compact Receipt Wording

Update wording in these files only:

- `.agents/skills/hsconfig/SKILL.md`
- `.agents/skills/hsconfig/references/workflow.md`
- `docs/operator/README.md`

Replace the existing `handoff_contract` explanation in-place with wording equivalent to:

```text
Then read `<out>/configure_summary.json.handoff_contract` as the pre-run config contract receipt: compact diagnostic-only handoff proof for use_config_now, single authority, no-default-only status, forbidden-surface status, source-to-runtime trace status, Darkbishop boundary, mechanic discipline, and the next report; it does not replace `reports/operator_summary.json`, cannot apply runtime files, cannot turn source gaps into blockers, and operator_summary.json remains the only normal apply authority.
```

Constraints:

- Preserve the existing `< 80` line limits for `SKILL.md` and `references/workflow.md`.
- Do not add a new section unless a replacement would be less clear.
- Keep `reports/operator_summary.json` as the repeated authority anchor.
- Keep `SOURCE_BACKED_STRONG` diagnostic-only.
- Keep `source_status_apply_blocking=false` semantics untouched.

### Task 5: Add Contract-Preflight Drift Check

Edit `src/hsconfig/contract_preflight.py`.

Add the new key to `EXPECTED_CHECK_KEYS`:

```python
"pre_run_config_contract_receipt_visible",
```

Add a small helper beside the other visibility helpers:

```python
def _pre_run_config_contract_receipt_visible(combined: str) -> bool:
    return all(
        term in combined
        for term in (
            "pre-run config contract receipt",
            "configure_summary.json.handoff_contract",
            "diagnostic-only handoff proof",
            "single authority",
            "no-default-only status",
            "forbidden-surface status",
            "source-to-runtime trace status",
            "Darkbishop boundary",
            "does not replace `reports/operator_summary.json`",
            "operator_summary.json remains the only normal apply authority",
        )
    )
```

Wire it into the `checks` dict inside `build_contract_preflight`:

```python
"pre_run_config_contract_receipt_visible": (
    _pre_run_config_contract_receipt_visible(combined)
),
```

Do not change status policy. Missing receipt wording may make `contract-preflight` return `ATTENTION`, but it must remain diagnostic-only and must not change runtime apply behavior.

### Task 6: Sync Installed Skill

After editing `.agents/skills/hsconfig`, sync the installed user skill:

```powershell
python scripts\sync_installed_skill.py --install-root C:\Users\darbo\.codex\skills
```

Acceptance:

- `C:\Users\darbo\.codex\skills\hsconfig\SKILL.md` matches the repo skill.
- No unrelated installed skills are changed.

### Task 7: Focused Verification

Run:

```powershell
python -m pytest tests\test_skill_files.py tests\test_contract_preflight.py
python scripts\check_contract_guardrails.py
python -m hsconfig.cli contract-preflight --json
python scripts\check_hsconfig_currentness.py --cwd . --json
git diff --check
git status --short --branch
```

Expected:

- Tests pass.
- `contract-preflight` includes `pre_run_config_contract_receipt_visible: true`.
- `source_status_apply_blocking` remains `false`.
- `runtime_apply_authority` remains `reports/operator_summary.json`.
- `diagnostic_only` remains `true`.
- Worktree is clean after commit.

### Task 8: Commit And Keep Worktree Clean

Stage only intended files:

```powershell
git add tests\test_skill_files.py tests\test_contract_preflight.py src\hsconfig\contract_preflight.py .agents\skills\hsconfig\SKILL.md .agents\skills\hsconfig\references\workflow.md docs\operator\README.md C:\Users\darbo\.codex\skills\hsconfig
```

If the installed skill lives outside the Git repo, it must be synced locally but not staged in the repo.

Commit message:

```text
docs: guard pre-run config contract receipt
```

Final check:

```powershell
git status --short --branch
python scripts\check_hsconfig_currentness.py --cwd . --json
```

## Subagent Split

Use subagents for read-heavy independent checks only:

- **Explorer:** read `contract_preflight.py`, `tests/test_contract_preflight.py`, `tests/test_skill_files.py`, and docs to identify exact insertion points.
- **Contract Reviewer:** verify the plan preserves single authority, no-default-only visibility, and non-blocking source-status behavior.
- **Worker:** implement the narrow code/docs/test changes. Only one writer.
- **Final Reviewer:** review diff and verification output for accidental broadening, line-count drift, or new gates.

No subagent should write to the same file region concurrently.

## Acceptance Criteria

- The plan is implemented with a small diff.
- `contract-preflight` has exactly one new check key for pre-run receipt visibility.
- The docs and skill call `configure_summary.json.handoff_contract` the pre-run config contract receipt.
- The receipt is documented as diagnostic-only and non-blocking.
- `reports/operator_summary.json` remains the only normal apply authority.
- No default-only runtime success is allowed to be silent.
- Darkbishop Benedictus remains an effect/start-of-game semantics case, not a mulligan keep, unless explicit opening-hand source text exists.
- `SOURCE_BACKED_STRONG` remains an evidence-quality label, not an apply gate.
- Installed `hsconfig` skill is synced.
- No dirty worktree remains.

## Execution Handoff

To execute this plan, use the `superpowers:subagent-driven-development`, `superpowers:test-driven-development`, and `superpowers:verification-before-completion` skills.

Recommended next command from the user:

```text
Subagent Driven umsetzen
```

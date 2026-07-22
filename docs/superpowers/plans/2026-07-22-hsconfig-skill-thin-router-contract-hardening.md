# HSConfig Skill Thin Router Contract Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the HSConfig Codex skill a compact, tested entrypoint router while preserving the current no-block, no-HSTuner, source-contract, and single-apply-authority behavior.

**Architecture:** Keep runtime/config generation code unchanged. Move duplicated operator detail out of the skill entrypoint and into the existing reference documents, then update tests so the skill entrypoint owns only routing and non-negotiable invariants while reference files own detailed policy. Use the existing installed-skill sync and contract-preflight surfaces as the final guardrails.

**Tech Stack:** Python, pytest, pathlib, existing `scripts/sync_installed_skill.py`, existing `hsconfig contract-preflight --json`, Markdown skill/reference files.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig`.
- Refresh repository state before implementation: `git fetch --all --prune --tags`, `git remote prune origin`, then inspect branch/currentness.
- Keep HSConfig separate from HSTuner.
- Do not add replay parsing, HDT parsing, winrate validation, candidate promotion, post-run tuning, or HearthRanger gameplay sequencing logic.
- Do not change runtime apply authority: `reports/operator_summary.json` remains the only normal apply authority.
- Do not turn `SOURCE_BACKED_STRONG`, source-depth diagnostics, default-only diagnostics, research snapshots, or source-closure receipts into apply blockers.
- `source_status_apply_blocking` must remain `false` for source-quality work.
- No hidden default-only success: default-only runtime surfaces remain visible quality debt.
- Normal runtime output remains `GlobalValues.json`, `Mulligan.json`, per-card `<CARDID>.json`, and `Combo.json` only for complete source-backed combo evidence.
- `Presume.json`, `Concede.json`, and aggregate `CardBehavior.json` stay outside the normal HSConfig path.
- Darkbishop Benedictus / `SW_448` remains the effect-not-mulligan canary: preserve start-of-game and hero-power-transform semantics, but do not emit a Mulligan keep without explicit opening-hand source text.
- End with a clean worktree unless the user explicitly asks to stop before cleanup.

---

## File Structure

- Modify: `C:\Users\darbo\Documents\HSConfig\.agents\skills\hsconfig\SKILL.md`
  - Responsibility: compact Codex skill entrypoint, normal route, hard boundaries, and reference routing.
- Modify: `C:\Users\darbo\Documents\HSConfig\.agents\skills\hsconfig\references\workflow.md`
  - Responsibility: detailed workflow wording that should not live in the entrypoint.
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_skill_files.py`
  - Responsibility: split entrypoint-specific assertions from active-doc/reference assertions.
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_skill_contract_entrypoint.py`
  - Responsibility: enforce contract-compiler checklist routing and canonical boundaries.
- Create: `C:\Users\darbo\Documents\HSConfig\tests\test_skill_thin_router_contract.py`
  - Responsibility: fail when the skill entrypoint becomes bloated, long-line dense, or a second authority.
- Modify only if needed: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\contract_preflight.py`
  - Responsibility: expose a diagnostic check if the existing preflight does not already detect the compact router contract.
- Modify only if needed: `C:\Users\darbo\Documents\HSConfig\tests\test_contract_preflight.py`
  - Responsibility: pin any new preflight field as diagnostic-only.

---

### Task 1: Add A Failing Thin-Router Test

**Files:**
- Create: `C:\Users\darbo\Documents\HSConfig\tests\test_skill_thin_router_contract.py`

**Interfaces:**
- Consumes: repo skill at `.agents/skills/hsconfig/SKILL.md`.
- Produces: pytest coverage that later tasks must satisfy with no runtime code changes.

- [ ] **Step 1: Create the failing test file**

Add this complete file:

```python
from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = REPO_ROOT / ".agents" / "skills" / "hsconfig"
SKILL = SKILL_ROOT / "SKILL.md"
REFERENCES = [
    SKILL_ROOT / "references" / "workflow.md",
    SKILL_ROOT / "references" / "visionai-surfaces.md",
    SKILL_ROOT / "references" / "contract-compiler-checklist.md",
    SKILL_ROOT / "references" / "guide-research-policy.md",
    SKILL_ROOT / "references" / "globalvalues-policy.md",
    SKILL_ROOT / "references" / "card-behavior-policy.md",
]


def _skill_text() -> str:
    return SKILL.read_text(encoding="utf-8")


def _active_reference_text() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in REFERENCES)


def test_hsconfig_skill_entrypoint_is_a_thin_router() -> None:
    text = _skill_text()
    lines = [line.rstrip() for line in text.splitlines()]
    non_empty_lines = [line for line in lines if line.strip()]
    long_lines = [line for line in non_empty_lines if len(line) > 220]

    assert len(non_empty_lines) <= 70
    assert long_lines == []
    assert text.count("## References:") == 1
    assert "docs/operator/README.md" in text
    assert "references/workflow.md" in text
    assert "references/contract-compiler-checklist.md" in text
    assert "references/guide-research-policy.md" in text


def test_hsconfig_skill_entrypoint_keeps_only_hard_runtime_boundaries() -> None:
    text = _skill_text()
    required_entrypoint_phrases = [
        "HSConfig is pre-run only.",
        "Preferred normal path: `hsconfig configure`.",
        "`reports/operator_summary.json` remains the only normal apply authority.",
        "`SOURCE_BACKED_STRONG` is an evidence-quality label, not a generation or apply gate.",
        "`source_status_apply_blocking` must remain `false` for source-quality work.",
        "No hidden default-only runtime success.",
        "Effect semantics are not opening-hand mulligan keeps.",
        "Card-intent taxonomy is diagnostic-only.",
        "Do no replay analysis, winrate analysis, HSTuner follow-up, or after-game tuning.",
    ]

    for phrase in required_entrypoint_phrases:
        assert phrase in text


def test_hsconfig_detailed_policy_lives_in_references_not_entrypoint() -> None:
    skill = _skill_text()
    references = _active_reference_text()

    detailed_reference_phrases = [
        "source claim -> normalized `claim_kind` -> semantic qualifiers",
        "source_closure_intake_receipt.json",
        "latest_research_result_contract_first_non_promoting_*",
        "mechanic lowering registry",
        "warning_boundaries",
        "globalvalue_numeric_tuning",
        "per_card_config_readiness_report.json",
    ]

    for phrase in detailed_reference_phrases:
        assert phrase in references

    for phrase in [
        "### Claim Lifecycle End States",
        "## Package Preparation",
        "## Fixture Stage Semantics",
        "## Diagnostic And Expert Paths",
    ]:
        assert phrase not in skill


def test_hsconfig_skill_entrypoint_does_not_create_forbidden_scope() -> None:
    text = _skill_text().lower()
    forbidden_phrases = [
        "runtime logs to tune",
        "hdt parsing",
        "winrate validation",
        "candidate promotion",
        "post-run tuning",
        "source status blocks apply",
        "source_closure_receipt applies runtime",
        "source_closure_receipt blocks apply",
        "source_autopilot_report.json remains the normal apply authority",
        "presume.json is normal output",
        "concede.json is normal output",
        "cardbehavior.json is normal output",
    ]

    for phrase in forbidden_phrases:
        assert phrase not in text
```

- [ ] **Step 2: Run the new test and confirm it fails on the current dense skill**

Run:

```powershell
python -m pytest tests\test_skill_thin_router_contract.py -q
```

Expected: FAIL because `.agents\skills\hsconfig\SKILL.md` currently contains long dense policy lines and detailed policy wording in the entrypoint.

- [ ] **Step 3: Commit the failing test only if the team workflow allows red commits; otherwise keep it unstaged until Task 2**

Preferred for this repo: do not commit a red state. Keep the file unstaged until Task 2 passes.

---

### Task 2: Replace The Skill Entrypoint With A Compact Router

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\.agents\skills\hsconfig\SKILL.md`
- Modify: `C:\Users\darbo\Documents\HSConfig\.agents\skills\hsconfig\references\workflow.md`

**Interfaces:**
- Consumes: active operator truth from `docs/operator/README.md` and `docs/research/current-truth.md`.
- Produces: a compact skill entrypoint that still routes normal operations and preserves hard boundaries.

- [ ] **Step 1: Replace `.agents\skills\hsconfig\SKILL.md` with this compact content**

```markdown
---
name: hsconfig
description: Generate guide-aligned HearthRanger VisionAI CustomConfig packages from a Hearthstone deck name and deck code. Use when Codex must build or validate direct Mulligan, GlobalValues, `per-card <CARDID>.json`, or Combo runtime config before games are played.
---

# HSConfig

Use this skill when Codex must create or validate a pre-game HearthRanger VisionAI `CustomConfig` package from a deck name, deck code, and current guide-backed research. HSConfig is pre-run only. It does not parse replays, inspect winrate, analyze runtime logs, promote candidates, or tune after games. Those tasks belong to HSTuner. Do no replay analysis, winrate analysis, HSTuner follow-up, or after-game tuning.

## Normal Operator Route

For the normal operator entry point, start at `docs/operator/README.md`.
Preferred normal path: `hsconfig configure`.
Lower-level inspected path: `source-manifest -> source-autopilot or draft-source-documents -> research-deck -> prepare -> validate -> apply`.

Normal workflow:
1. Prefer `hsconfig configure ...` for normal operation.
2. Use lower-level commands only when inspecting a stage:
   `source-manifest -> source-autopilot or draft-source-documents -> research-deck -> prepare -> validate -> apply`.
3. After `configure`, read `<out>/configure_summary.json.acceptance_summary` first; use `reports/operator_summary.json` as the apply authority.

Read `<out>/configure_summary.json.handoff_contract` next as the diagnostic-only pre-run config contract receipt. Read `<out>/configure_summary.json.source_closure_receipt` only when source depth is the question. Read `<out>/configure_summary.json.config_proof_summary` and `<out>/configure_summary.json.config_quality_summary` only as diagnostic proof. These summaries do not replace `reports/operator_summary.json`, cannot apply runtime files, and cannot turn source gaps into blockers.

For an optimal fresh deck config, prefer:
`hsconfig configure --deck-name "<DeckName>" --deck-code "<DeckCode>" --runtime-root "<HearthRangerRoot>" --out "outputs/<DeckName>" --online-source --auto-source --apply --json`

Before source refresh, deck package generation, or runtime-facing apply work, run `git fetch --all --prune --tags`, then `python scripts/check_hsconfig_currentness.py --cwd . --json`; feature branches may be ahead of `origin/main`, but must not be behind, and runtime-facing verification starts from a clean worktree.

## Hard Boundaries

- Decode the deck code first, then resolve exact CardID identity before writing config.
- Runtime writes happen only through `hsconfig apply` or `hsconfig configure --apply`.
- `reports/operator_summary.json` remains the only normal apply authority.
- Runtime apply is guarded: validate `operator_summary.json`, package structure, fake receipts, and package hashes before writing.
- `SOURCE_BACKED_STRONG` is an evidence-quality label, not a generation or apply gate.
- `source_status_apply_blocking` must remain `false` for source-quality work.
- No hidden default-only runtime success. Every expected surface must be emitted, explicitly suppressed, or reported as a visible source/action gap.
- Normal output remains `GlobalValues.json`, `Mulligan.json`, per-card `<CARDID>.json`, and `Combo.json` only for exact ordered combo evidence.
- `Presume.json`, `Concede.json`, and aggregate `CardBehavior.json` are outside the normal HSConfig output path.
- Effect semantics are not opening-hand mulligan keeps. Preserve Darkbishop Benedictus / `SW_448` hero-power-transform semantics, but do not emit a Mulligan keep without explicit opening-hand source text.
- Card-intent taxonomy is diagnostic-only; it explains per-card config signals but does not encode HearthRanger gameplay sequencing or create another apply gate.

## Source Contract

- Candidate registries, `source_closure_intake_receipt.json`, and `source-autopilot` are acquisition input or source-strength preflight only.
- Source evidence must lower through `claim_kind`, surface gates, builder/router outcomes, and visible diagnostics before runtime rows are emitted.
- Static semantics are surface-scoped. They may support deterministic CardID/effect rows such as `hero_power_transform`, but they do not prove Mulligan, combo, targeting, or gameplan posture without matching source claims.
- When source coverage is weak, still build a technically valid load-safe package and report `first_missing_source_action` instead of blocking the deck.
- Contract compiler checklist: `references/contract-compiler-checklist.md`.

## Expert Paths

- Drift check: `hsconfig contract-preflight --json` verifies repo currentness, installed-skill sync, and source/runtime contract wording as diagnostic-only; use `--skill-install-root` only for non-default skill roots.
Use optional expert `--cards-json`, legacy `--claims-json`, or inspected `--plan-reports-dir` only for fixtures, diagnostics, or inspected expert inputs. Use `--allow-placeholder` only for deterministic fixture or preview tests.

## References: `references/workflow.md`; `references/visionai-surfaces.md`; `references/contract-compiler-checklist.md`; `references/guide-research-policy.md`; `references/globalvalues-policy.md`; `references/card-behavior-policy.md`
```

- [ ] **Step 2: Ensure moved details remain available in workflow/reference text**

Open `.agents\skills\hsconfig\references\workflow.md`. If any of these phrases are missing, add a short "Detailed Source Contract Pointers" section near the existing diagnostic/expert path section:

```markdown
## Detailed Source Contract Pointers

- Use the canonical claim lifecycle for source-to-runtime explanations: source claim -> normalized `claim_kind` -> semantic qualifiers -> conflict quarantine -> surface gate -> builder/router outcome -> emitted runtime row or suppression reason.
- `source_closure_intake_receipt.json` is acquisition input only; it cannot promote, block, write runtime config, or replace `operator_summary.json`.
- `latest_research_result_contract_first_non_promoting_*` names the first source action needed for Strong closure; it is diagnostic-only, cannot block or promote a package, and `operator_summary.json` remains the only normal apply authority.
- The mechanic lowering registry is the executable authority behind `needs_mechanic_lowering`; warning-only mechanics remain visible diagnostics and must not block load-safe apply.
- Use `warning_boundaries` and `first_warning_boundary` to inspect report-only mechanics without widening runtime output.
- `globalvalue_numeric_tuning` is report-visible and runtime-evidence-required; use `gameplan_posture` for Step1 GlobalValues posture that may lower to `GlobalValues.json`.
- `per_card_config_readiness_report.json`, `source_to_runtime_explainability.json`, and `source_evidence_closure.json` explain source depth and CardID coverage; they do not replace `operator_summary.json`.
```

- [ ] **Step 3: Run the new test**

Run:

```powershell
python -m pytest tests\test_skill_thin_router_contract.py -q
```

Expected: PASS.

---

### Task 3: Refactor Existing Skill Tests From Entrypoint-Pinning To Active-Docs-Pinning

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_skill_files.py`
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_skill_contract_entrypoint.py`

**Interfaces:**
- Consumes: compact `SKILL.md` from Task 2 and existing references.
- Produces: tests that enforce both slim entrypoint and complete active policy coverage.

- [ ] **Step 1: Add shared active-doc helper functions near the top of `tests\test_skill_files.py`**

Insert after the existing constants:

```python
ACTIVE_SKILL_REFERENCE_FILES = [
    SKILL_ROOT / "SKILL.md",
    SKILL_ROOT / "references" / "workflow.md",
    SKILL_ROOT / "references" / "visionai-surfaces.md",
    SKILL_ROOT / "references" / "contract-compiler-checklist.md",
    SKILL_ROOT / "references" / "guide-research-policy.md",
    SKILL_ROOT / "references" / "globalvalues-policy.md",
    SKILL_ROOT / "references" / "card-behavior-policy.md",
]


def _skill_entrypoint_text() -> str:
    return (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")


def _active_skill_docs_text() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in ACTIVE_SKILL_REFERENCE_FILES)
```

- [ ] **Step 2: Update entrypoint-only expectations in `tests\test_skill_files.py`**

For tests that verify the entrypoint itself, use `_skill_entrypoint_text()`. Keep these checks in the entrypoint:

```python
entrypoint_required = [
    "HSConfig is pre-run only.",
    "Preferred normal path: `hsconfig configure`.",
    "`reports/operator_summary.json` remains the only normal apply authority.",
    "`SOURCE_BACKED_STRONG` is an evidence-quality label, not a generation or apply gate.",
    "Do no replay analysis, winrate analysis, HSTuner follow-up, or after-game tuning.",
    "Runtime writes happen only through `hsconfig apply` or `hsconfig configure --apply`.",
    "Effect semantics are not opening-hand mulligan keeps.",
    "Card-intent taxonomy is diagnostic-only;",
]
```

For tests that verify detailed policy vocabulary, use `_active_skill_docs_text()` instead of only `SKILL.md`. These phrases may live in references:

```python
active_docs_required = [
    "source_closure_intake_receipt.json",
    "latest_research_result_contract_first_non_promoting_*",
    "source claim -> normalized `claim_kind` -> semantic qualifiers",
    "mechanic lowering registry",
    "warning_boundaries",
    "globalvalue_numeric_tuning",
    "per_card_config_readiness_report.json",
    "source_to_runtime_explainability.json",
    "source_evidence_closure.json",
]
```

- [ ] **Step 3: Update `tests\test_skill_contract_entrypoint.py` to pin routing, not bulk detail**

Keep `ENTRYPOINT_LINK` exactly as-is. Add this test:

```python
def test_skill_entrypoint_routes_to_references_without_owning_bulk_policy() -> None:
    skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    references = "\n".join(
        (SKILL_ROOT / "references" / name).read_text(encoding="utf-8")
        for name in [
            "workflow.md",
            "visionai-surfaces.md",
            "contract-compiler-checklist.md",
            "guide-research-policy.md",
            "globalvalues-policy.md",
            "card-behavior-policy.md",
        ]
    )

    assert "## References:" in skill
    assert ENTRYPOINT_LINK in skill
    assert "operator_summary.json" in skill
    assert "SOURCE_BACKED_STRONG" in skill
    assert "source_closure_intake_receipt.json" in references
    assert "source claim -> normalized `claim_kind` -> semantic qualifiers" in references
    assert "mechanic lowering registry" in references
```

- [ ] **Step 4: Run focused skill tests and fix only assertion ownership issues**

Run:

```powershell
python -m pytest tests\test_skill_thin_router_contract.py tests\test_skill_files.py tests\test_skill_contract_entrypoint.py -q
```

Expected: PASS.

If a failure says a phrase is missing entirely, add the phrase to the correct reference file. If a failure says a phrase is no longer in `SKILL.md`, move that assertion to active-doc coverage unless it is one of the hard entrypoint boundaries listed in Step 2.

---

### Task 4: Extend Contract Preflight Only If The Router Contract Is Invisible There

**Files:**
- Modify only if needed: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\contract_preflight.py`
- Modify only if needed: `C:\Users\darbo\Documents\HSConfig\tests\test_contract_preflight.py`

**Interfaces:**
- Consumes: existing `build_contract_preflight()` payload.
- Produces: optional diagnostic-only check for the compact skill router.

- [ ] **Step 1: Inspect current preflight output**

Run:

```powershell
python -m hsconfig.cli contract-preflight --json
```

Expected: JSON parses. `runtime_apply_authority` is `reports/operator_summary.json`, `source_status_apply_blocking` is `false`, and installed skill sync is visible.

- [ ] **Step 2: Add this test only if no existing check covers thin router routing**

Append to `tests\test_contract_preflight.py`:

```python
def test_contract_preflight_exposes_skill_thin_router_contract(tmp_path: Path) -> None:
    payload = build_contract_preflight(
        Path("."),
        git=_clean_git(),
        skill_install_root=_synced_install_root(tmp_path),
    )

    assert payload["checks"]["skill_thin_router_visible"] is True
    assert "skill_thin_router_visible" not in payload["failures"]
    assert payload["diagnostic_only"] is True
    assert payload["runtime_apply_authority"] == "reports/operator_summary.json"
    assert payload["source_status_apply_blocking"] is False
```

- [ ] **Step 3: Add minimal preflight implementation only if Step 2 was needed**

In `src\hsconfig\contract_preflight.py`, add the check alongside existing skill/reference routing checks:

```python
def _skill_thin_router_visible(repo_root: Path) -> bool:
    skill_path = repo_root / ".agents" / "skills" / "hsconfig" / "SKILL.md"
    if not skill_path.exists():
        return False
    text = skill_path.read_text(encoding="utf-8")
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    return (
        len(lines) <= 70
        and all(len(line) <= 220 for line in lines)
        and "## References:" in text
        and "docs/operator/README.md" in text
        and "references/contract-compiler-checklist.md" in text
        and "`reports/operator_summary.json` remains the only normal apply authority." in text
        and "`source_status_apply_blocking` must remain `false`" in text
    )
```

Then add:

```python
checks["skill_thin_router_visible"] = _skill_thin_router_visible(repo_root)
```

Use the existing failure collection pattern in the same file so a false value becomes diagnostic `ATTENTION`, not a runtime apply blocker.

- [ ] **Step 4: Run preflight tests**

Run:

```powershell
python -m pytest tests\test_contract_preflight.py -q
```

Expected: PASS.

---

### Task 5: Sync Installed Skill And Verify Guardrails

**Files:**
- Runtime/generated outputs: none.
- Installed skill target: `C:\Users\darbo\.codex\skills\hsconfig`

**Interfaces:**
- Consumes: repo skill source under `.agents\skills\hsconfig`.
- Produces: synchronized installed Codex skill and clean verification.

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

- [ ] **Step 3: Run focused tests**

Run:

```powershell
python -m pytest tests\test_skill_thin_router_contract.py tests\test_skill_files.py tests\test_skill_contract_entrypoint.py tests\test_skill_sync.py tests\test_contract_preflight.py -q
```

Expected: PASS.

- [ ] **Step 4: Run contract guardrails**

Run:

```powershell
python scripts\check_contract_guardrails.py
```

Expected: PASS / zero return code. The output must keep installed skill sync, contract-spine sentinel, and focused boundary tests green.

- [ ] **Step 5: Run full test suite if focused tests pass**

Run:

```powershell
python -m pytest -q
```

Expected: PASS.

- [ ] **Step 6: Verify currentness and clean worktree**

Run:

```powershell
python scripts\check_hsconfig_currentness.py --cwd . --json
git status --short --branch
```

Expected:

- currentness JSON has `dirty=false`, `clean_for_runtime_work=true`, and no behind status.
- `git status --short --branch` shows only the branch line after all intended files are committed or explicitly left for review.

---

### Task 6: Commit The Thin Router Hardening

**Files:**
- Commit all files changed by Tasks 1-5.

**Interfaces:**
- Consumes: passing focused tests, guardrails, and clean currentness.
- Produces: one intentional commit on the current branch.

- [ ] **Step 1: Inspect diff**

Run:

```powershell
git diff -- .agents\skills\hsconfig\SKILL.md .agents\skills\hsconfig\references\workflow.md tests\test_skill_thin_router_contract.py tests\test_skill_files.py tests\test_skill_contract_entrypoint.py tests\test_contract_preflight.py src\hsconfig\contract_preflight.py
```

Expected: diff contains only skill-router docs/tests and optional preflight diagnostic code. It must not contain runtime generation changes, deck output files, logs, or HSTuner scope.

- [ ] **Step 2: Stage intentional files**

Run:

```powershell
git add .agents\skills\hsconfig\SKILL.md .agents\skills\hsconfig\references\workflow.md tests\test_skill_thin_router_contract.py tests\test_skill_files.py tests\test_skill_contract_entrypoint.py tests\test_contract_preflight.py src\hsconfig\contract_preflight.py
```

If `src\hsconfig\contract_preflight.py` or `tests\test_contract_preflight.py` were not modified, omit those paths from `git add`.

- [ ] **Step 3: Commit**

Run:

```powershell
git commit -m "test: harden hsconfig skill thin router contract"
```

Expected: commit succeeds.

- [ ] **Step 4: Push only if the remote can fast-forward cleanly**

Run:

```powershell
git status --short --branch
git push
```

Expected: push succeeds and the branch has no uncommitted changes.

---

## Self-Review Checklist

- Spec coverage: The plan keeps HSConfig pre-run only, preserves `operator_summary.json` as the sole apply authority, keeps `SOURCE_BACKED_STRONG` non-blocking, keeps source diagnostics non-blocking, preserves no-default-only visibility, and keeps Darkbishop effect-not-mulligan canary coverage.
- Scope check: No runtime package generation logic, source promotion logic, HSTuner integration, log parsing, replay parsing, or HearthRanger gameplay sequencing is added.
- Placeholder scan: No placeholder markers or unspecified tests are used.
- Type consistency: New tests use `Path`, `str`, and existing repo paths only.
- Verification: Focused tests, contract guardrails, installed skill sync, optional full pytest, currentness check, and clean worktree are required before completion.

# HSConfig Pre-Run Near-100 Master Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the approved HSConfig `v1.0.0` pre-run contract at an evidence-backed 98-99/100, with complete semantic disposition, deterministic packages, crash-safe activation, reproducible CI, a curated proprietary repository, and no gameplay-quality claim.

**Architecture:** Preserve the existing fail-closed contract core, then replace its boundaries in dependency order: semantic closure, single registry and immutable package model, transactional output/runtime publication, release verification, and finally the curated root-history cutover. Each subplan leaves `main` working and independently reviewable; destructive history and GitHub changes occur only after every code and local release gate is green.

**Tech Stack:** Python 3.11/3.12, frozen dataclasses, JSON, SHA-256 manifests, `os.replace`, Windows/POSIX file locks, pytest, pytest-cov, Ruff, pip-audit, pip `pylock.toml`, GitHub Actions, GitHub CLI, PowerShell, Git.

## Global Constraints

- Work only in `C:\Users\darbo\Documents\HSConfig`.
- Use only local and remote branch `main`; create no additional local or remote branch and no pull request.
- Keep `reports/operator_summary.json` as the only normal apply authority.
- Keep gameplay quality `OUT_OF_SCOPE_ASSUMED_EXTERNAL`; do not use HSTuner, replay analysis, runtime-game sampling, or win-rate tuning.
- Never invent VisionAI keys, conditions, owners, targets, timing, Combo order, or numeric tuning.
- Normal runtime surfaces remain `GlobalValues.json`, `Mulligan.json`, per-card CardID JSON, and `Combo.json` only when fully authorized.
- Never normally emit `Presume.json`, `Concede.json`, or aggregate `CardBehavior.json`.
- Write behavior changes test-first and confirm RED before implementation.
- Before every commit run focused GREEN tests, Ruff on changed Python surfaces, and `git diff --check`.
- Push each approved phase commit directly to `main`, wait for its GitHub CI result, and keep `HEAD == origin/main`.
- Generated Config packages remain ignored and untracked.
- Keep exactly one current output generation for each of the twelve audited decks.
- Do not persist Config backups or attach Config packages to GitHub Releases.
- Do not mutate immutable packages during apply.
- Do not perform the history rewrite until Plans 01-04 and Plan 05 Tasks 1-5, including the candidate-tree/local release gate, pass; Plan 05 Tasks 6-9 are the cutover itself and therefore cannot be prerequisites to it.
- Use an OID-bound `--force-with-lease` exactly once for the curated-root cutover; never use unbound `--force`.
- The temporary Git bundle is rollback protection for the destructive source-history operation, not a Config backup; delete it only after remote, CI, tag, release, ruleset, settings, final score, hygiene, and inventory verification plus the durable cutover commit decision.
- Final visible release is `v1.0.0`, publicly visible and explicitly proprietary.

---

## Execution Sequence

Execute the plan tasks in this dependency order:

1. [Contract Closure Plan, Task 1](2026-07-28-hsconfig-pre-run-near-100-01-contract-closure-plan.md): freeze score and semantic fixtures without changing behavior.
2. [Transactional Publication Plan, Task 1](2026-07-28-hsconfig-pre-run-near-100-03-transactional-publication-plan.md): establish atomic I/O, locks, and fault hooks.
3. [Package Architecture Plan, Tasks 1-4](2026-07-28-hsconfig-pre-run-near-100-02-package-architecture-plan.md): single VisionAI registry, optimized-mode safety, canonical build-input schema, immutable package/configure-run models.
4. [Contract Closure Plan, Tasks 2-7](2026-07-28-hsconfig-pre-run-near-100-01-contract-closure-plan.md): implement evidence, acquisition, dispositions, Mulligan delegation, GlobalValues decisions, and dual closure.
5. [Package Architecture Plan, Tasks 5-10](2026-07-28-hsconfig-pre-run-near-100-02-package-architecture-plan.md): resolve/freeze the twelve content-bearing build contexts, extract pure quality/status/compiler/configure boundaries, and remove aliases.
6. [Transactional Publication Plan, Tasks 2-8](2026-07-28-hsconfig-pre-run-near-100-03-transactional-publication-plan.md): publish full configure revisions and activate runtime transactionally.
7. [Verification and CI Plan](2026-07-28-hsconfig-pre-run-near-100-04-verification-ci-plan.md): prove coverage, score, reproducibility, packages, and CI.
8. [Repository and v1.0.0 Cutover Plan](2026-07-28-hsconfig-pre-run-near-100-05-repository-v1-cutover-plan.md): curate and publish v1.0.0 only after all prior gates pass.

## Shared Interface Spine

The subplans must use these exact cross-plan interfaces:

```python
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol


@dataclass(frozen=True, slots=True)
class PackageArtifact:
    relative_path: str
    content: bytes
    size: int
    sha256: str


@dataclass(frozen=True, slots=True)
class PackageModel:
    deck_name: str
    deck_fingerprint: str
    mulligan_plan: MulliganPlanModel
    globalvalues_ledger: GlobalValuesDecisionLedger
    disposition_ledger: DispositionLedger
    evidence_contract: LayeredEvidenceContract
    runtime_surface_plan: RuntimeSurfacePlan


@dataclass(frozen=True, slots=True)
class RenderedPackage:
    model: PackageModel
    artifacts: tuple[PackageArtifact, ...]
    content_root_sha256: str


@dataclass(frozen=True, slots=True)
class ConfigureRunModel:
    deck_name: str
    deck_fingerprint: str
    package: PackageModel
    stage_artifacts: tuple[PackageArtifact, ...]


@dataclass(frozen=True, slots=True)
class RenderedConfigureRun:
    model: ConfigureRunModel
    artifacts: tuple[PackageArtifact, ...]
    content_root_sha256: str


class PackageView(Protocol):
    def file_names(self) -> tuple[str, ...]: ...
    def read_bytes(self, relative_path: str) -> bytes: ...
    def read_json(self, relative_path: str) -> Any: ...
    def exists(self, relative_path: str) -> bool: ...


@dataclass(frozen=True, slots=True)
class PublishedOutput:
    output_root: Path
    revision_root: Path
    package_root: Path
    content_root_sha256: str
    reused_existing_revision: bool


def resolve_current_package(output_root: Path) -> Path: ...
```

Every content root is SHA-256 over ordered UTF-8 records
`relative_path + NUL + decimal_size + NUL + file_sha256 + LF`. The manifest
file itself is excluded from those records, so the digest is non-circular.
Semantic reports feed typed `PackageModel`; renderers derive runtime and report
bytes together as `RenderedPackage`. A complete configure run embeds that
package at `04_package/` in `ConfigureRunModel`; the publisher accepts only a
validated `RenderedConfigureRun`; the runtime installer accepts only a
manifest-verified current revision and its `04_package` view.

## Task 0: Freeze Program Entry Conditions

**Files:**
- Read: `docs/superpowers/specs/2026-07-28-hsconfig-pre-run-near-100-design.md`
- Read: `docs/operator/audited-deck-catalog.json`
- Read: `AGENTS.md`
- Modify: none

**Interfaces:**
- Consumes: current `main`, audited twelve-deck catalog, approved design.
- Produces: an evidence-only entry receipt in the task report; no repository file.

- [ ] **Step 1: Verify the sole-main and clean-worktree entry gate**

Run:

```powershell
git fetch origin main --prune
git status --short --branch
git rev-parse HEAD
git rev-parse origin/main
git branch --format="%(refname:short)"
git ls-remote --heads origin
gh pr list --repo Teufelsboy/HSConfig --state open --json number
```

Expected: clean worktree, local and remote OIDs equal, local and remote branch inventories contain only `main`, and the PR list is empty.

- [ ] **Step 2: Verify the design and catalog are present**

Run:

```powershell
Test-Path docs/superpowers/specs/2026-07-28-hsconfig-pre-run-near-100-design.md
python -c "import json,pathlib; p=json.loads(pathlib.Path('docs/operator/audited-deck-catalog.json').read_text(encoding='utf-8')); assert len(p['decks']) == 12"
```

Expected: `True` and exit code 0.

- [ ] **Step 3: Run the pre-change contract baseline**

Run:

```powershell
python -m ruff check --no-cache src tests scripts
python -m pytest tests/test_audited_deck_set_acceptance.py -q -p no:cacheprovider
python -m hsconfig.cli contract-spine-sentinel --json
python -m pip_audit .
```

Expected: Ruff clean, audited deck acceptance green, sentinel `status=clean`, and no known project dependency vulnerability.

- [ ] **Step 4: Record but do not clean the current artifact inventory**

Run:

```powershell
python scripts/report_output_inventory.py outputs
Get-ChildItem -Force .pytest_cache,.ruff_cache,build,.codex-qa-round5,.superpowers -ErrorAction SilentlyContinue
```

Expected: read-only evidence of the current multi-output and cache state. Do not delete anything in Task 0.

## Phase Gates

After each execution-sequence phase:

- [ ] Run its focused tests and all listed regressions.
- [ ] Run `python -m ruff check --no-cache src tests scripts`.
- [ ] Run `git diff --check`.
- [ ] Request a two-stage review: specification compliance first, code quality second.
- [ ] Commit only that subplan's approved scope.
- [ ] Push directly to `origin/main`.
- [ ] Confirm local `HEAD == origin/main`.
- [ ] Confirm every CI job for that OID is terminal and successful.
- [ ] Confirm the worktree is clean before starting the next subplan.

Milestone OIDs for the later curated-history graph:

- [ ] After Execution Sequence step 5, record clean `HEAD` as `engine_milestone_oid`.
- [ ] After Plan 04 and exact-OID CI, record clean `HEAD` as `hardening_milestone_oid`.
- [ ] After Plan 05 Task 4 is committed and green, record clean `HEAD` as `governance_milestone_oid`.
- [ ] Do not create refs, tags, or branches for these milestones; store the OIDs only in the execution transcript.

## Final Program Gate

Run only after all five subplans:

```powershell
python scripts/check_release_gate.py --repo . --outputs outputs --json
python -m ruff check --no-cache src tests scripts
python -m pytest -p no:cacheprovider
python -O -m hsconfig.cli contract-spine-sentinel --json
python -m pip_audit .
git status --porcelain
git branch --format="%(refname:short)"
git ls-remote --heads origin
git tag --list
gh pr list --repo Teufelsboy/HSConfig --state open --json number
gh release view v1.0.0 --repo Teufelsboy/HSConfig --json assets,tagName,isDraft,isPrerelease
```

Expected:

- release gate `passed=true`;
- full suite green;
- optimized-mode sentinel clean;
- no dependency vulnerability;
- clean worktree;
- only `main` locally and remotely;
- no open PR;
- exactly one `v1.0.0` tag;
- one non-draft, non-prerelease release with no custom assets;
- exactly twelve current outputs and one revision per deck;
- no cache, backup, staging, obsolete output, or local Superpowers residue.

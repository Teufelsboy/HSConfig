# HSConfig Canonical Source Status Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Use one writer for each file area, keep review agents read-only, and update the checklist as work completes.

**Goal:** Make HSConfig's Source/Contract logic canonical, narrow, and auditable so `SOURCE_BACKED_STRONG` has exactly one resolver, no default-only runtime surface can count as strong, valid Wild decks never get blocked by source-depth gaps, and ShadowPriest keeps Darkbishop Benedictus effect semantics without incorrectly keeping `SW_448` in mulligan.

**Architecture:** Add or finalize a side-effect-free `source_status_resolver` module and make operator summary, strong promotion, and source evidence closure consume it. Keep `operator_summary.json` as the only normal apply authority; all source-closure reports remain diagnostic. Back the contract with focused resolver/report tests, docs/skill drift tests, and the universal Wild no-block matrix.

**Tech Stack:** Python, pytest, existing HSConfig report builders, existing source autopilot/source-claim reports, existing `scripts/sync_installed_skill.py` skill sync flow.

**Execution Status (2026-07-17):** Completed Subagent Driven. The existing partial implementation was verified, three read-only subagent review gaps were fixed, the repo-local and installed HSConfig skill were synchronized, and final focused verification passed with `185 passed`. `git diff --check` exited `0` with only LF/CRLF conversion warnings.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig`.
- Refresh repository state before runtime-facing changes: `git fetch --all --prune`, then compare `HEAD...origin/main`.
- Do not run destructive git cleanup. Preserve existing user or agent changes unless this plan explicitly owns the file.
- `SOURCE_BACKED_STRONG` is a source-confidence label, not a generation or runtime apply gate.
- `operator_summary.json` remains the normal apply authority.
- `source_evidence_closure.json`, `strong_promotion_report.json`, source-candidate proof decks, HSGuru/Hearthstone-Decks URLs, and online meta pages are diagnostic/provenance artifacts only.
- Candidate URLs and decklists are acquisition seeds only. They do not promote strong status without fetched full text, deck/archetype match, claim-kind normalization, and runtime-surface gates.
- No default-only runtime surface may silently count as complete. It must be visible and must prevent `SOURCE_BACKED_STRONG`.
- Source gaps must not block valid Wild deck package generation. `source_status_apply_blocking` must stay `false`.
- Darkbishop Benedictus / `SW_448` must preserve start-of-game hero-power-transform semantics, but must not be emitted as a mulligan keep unless explicit source evidence supports opening-hand keep behavior.

---

## File Structure

- Create or finalize `src/hsconfig/source_status_resolver.py`: canonical pure resolver for source-depth status, first missing action, diagnostic/apply-blocking flags, and default-only visibility.
- Create or finalize `tests/test_source_status_resolver.py`: resolver unit tests for strong, partial, default-only, claim-gap, semantic-blocker, invalid-package, and diagnostic-only behavior.
- Modify `src/hsconfig/operator_summary.py`: consume resolver once and expose additive JSON-safe fields in `operator_summary.json`.
- Modify `tests/test_operator_summary.py`: assert operator summary exposes resolver fields and never source-blocks valid decks.
- Modify `src/hsconfig/strong_promotion_report.py`: consume resolver instead of duplicating strong-readiness logic.
- Modify `tests/test_strong_promotion_report.py`: assert promotion report mirrors resolver status and keeps source failures diagnostic.
- Modify `src/hsconfig/source_evidence_closure.py`: consume resolver and expose the same status/action fields in the diagnostic closure report.
- Modify `tests/test_source_evidence_closure.py`: assert closure report recomputes status from operator/source-gap data and remains non-apply-blocking.
- Modify `.agents/skills/hsconfig/SKILL.md`: document the canonical resolver and no-block/default-only contract.
- Modify `docs/operator/source-backed-strong-closure.md`: document resolver fields, promotion requirements, and diagnostic-only closure.
- Modify `docs/operator/universal-wild-no-block-contract.md`: document valid-deck no-block behavior and current Wild matrix expectations.
- Modify `tests/test_operator_docs_contract_policy.py`: prevent stale contract terms and require docs/skill wording to match implementation.
- Modify `tests/test_universal_wild_no_block_matrix.py`: assert ShadowPriest/Darkbishop and all listed Wild decks remain load-safe, non-default-only, and source-status diagnostic-only.
- Verify installed global skill with `scripts/sync_installed_skill.py --check`.

---

### Task 1: Refresh And Classify The Current Worktree

**Files:**
- Read-only: repository metadata
- Read-only: `docs/superpowers/plans/2026-07-17-hsconfig-canonical-source-status-sync.md`

**Interfaces:**
- Consumes: current git branch, upstream state, existing local diff.
- Produces: a known-safe baseline for implementation, with no destructive cleanup.

- [ ] **Step 1: Refresh remotes**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
git fetch --all --prune
```

Expected: command exits 0. Network messages are acceptable.

- [ ] **Step 2: Verify upstream sync**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
git rev-list --left-right --count HEAD...origin/main
```

Expected: `0 0` when the current branch is fully synced with `origin/main`. If not `0 0`, stop and inspect before changing files.

- [ ] **Step 3: Inspect dirty worktree**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
git status --short --branch
```

Expected: either clean, or only files owned by this plan. Do not reset, checkout, clean, or remove files.

- [ ] **Step 4: Confirm the current plan remains the only plan source**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
Test-Path .\docs\superpowers\plans\2026-07-17-hsconfig-canonical-source-status-sync.md
```

Expected: `True`.

---

### Task 2: Add Canonical Source Status Resolver

**Files:**
- Create or finalize: `src/hsconfig/source_status_resolver.py`
- Create or finalize: `tests/test_source_status_resolver.py`

**Interfaces:**
- Consumes:
  - `technical_status: str`
  - `semantic_status: str`
  - `next_action: str`
  - `semantic_blockers: Sequence[object]`
  - `default_only_runtime_surfaces: Sequence[str]`
  - `source_claim_gap_report: Mapping[str, object] | None`
  - `closure_profile_closed: bool`
  - `closure_profile_first_missing_link: str`
- Produces:
  - `SourceStatusResolution`
  - `resolve_source_status(...) -> SourceStatusResolution`
  - `first_missing_chain_from_report(report) -> dict[str, object] | None`

- [ ] **Step 1: Write or verify the resolver tests**

Ensure `tests/test_source_status_resolver.py` covers these exact cases:

```python
from hsconfig.source_status_resolver import (
    DEFAULT_ONLY_SOURCE_ACTION,
    NO_MISSING_SOURCE_ACTION,
    PARTIAL_SOURCE_STATUS,
    READY_ACTION,
    STRONG_SOURCE_STATUS,
    resolve_source_status,
)


def test_strong_ready_path_exposes_operator_fields() -> None:
    resolution = resolve_source_status(
        technical_status="VALID_PACKAGE",
        semantic_status=STRONG_SOURCE_STATUS,
        next_action=READY_ACTION,
        semantic_blockers=[],
        default_only_runtime_surfaces=[],
        source_claim_gap_report=None,
        closure_profile_closed=True,
    )

    assert resolution.source_backed_status == STRONG_SOURCE_STATUS
    assert resolution.strong_ready is True
    assert resolution.first_missing_source_action == NO_MISSING_SOURCE_ACTION
    assert resolution.apply_blocking is False
    assert resolution.diagnostic_only is True
    assert resolution.as_operator_fields()["source_status_apply_blocking"] is False


def test_default_only_surface_prevents_strong_status_without_blocking_apply() -> None:
    resolution = resolve_source_status(
        technical_status="VALID_PACKAGE",
        semantic_status=STRONG_SOURCE_STATUS,
        next_action=READY_ACTION,
        semantic_blockers=[],
        default_only_runtime_surfaces=["Mulligan.json"],
        source_claim_gap_report=None,
        closure_profile_closed=True,
    )

    assert resolution.source_backed_status == PARTIAL_SOURCE_STATUS
    assert resolution.strong_ready is False
    assert resolution.first_missing_source_action == DEFAULT_ONLY_SOURCE_ACTION
    assert resolution.default_only_runtime_surfaces == ("Mulligan.json",)
    assert resolution.apply_blocking is False


def test_first_missing_chain_prevents_strong_and_preserves_action() -> None:
    resolution = resolve_source_status(
        technical_status="VALID_PACKAGE",
        semantic_status=STRONG_SOURCE_STATUS,
        next_action=READY_ACTION,
        semantic_blockers=[],
        default_only_runtime_surfaces=[],
        source_claim_gap_report={
            "summary": {
                "first_missing_chain": {
                    "card_id": "SW_448",
                    "first_missing_link": "needs_mulligan_claim",
                    "next_action": "add_explicit_mulligan_source",
                }
            }
        },
        closure_profile_closed=True,
    )

    assert resolution.source_backed_status == PARTIAL_SOURCE_STATUS
    assert resolution.first_missing_source_action == "add_explicit_mulligan_source"
    assert resolution.apply_blocking is False


def test_source_failures_are_diagnostic_only() -> None:
    resolution = resolve_source_status(
        technical_status="VALID_PACKAGE",
        semantic_status=STRONG_SOURCE_STATUS,
        next_action=READY_ACTION,
        semantic_blockers=[{"code": "cards_need_runtime_surface"}],
        default_only_runtime_surfaces=[],
        source_claim_gap_report=None,
        closure_profile_closed=True,
    )

    assert resolution.source_backed_status == PARTIAL_SOURCE_STATUS
    assert resolution.first_missing_source_action == "add_runtime_lowerable_claim_or_router_support"
    assert resolution.diagnostic_only is True
    assert resolution.apply_blocking is False
```

- [ ] **Step 2: Run resolver tests and verify failure if resolver is missing**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python -m pytest tests/test_source_status_resolver.py -q
```

Expected before implementation: fails with import or assertion errors. Expected after implementation: all tests pass.

- [ ] **Step 3: Implement the pure resolver**

Ensure `src/hsconfig/source_status_resolver.py` contains:

```python
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


VALID_TECHNICAL_STATUS = "VALID_PACKAGE"
STRONG_SOURCE_STATUS = "SOURCE_BACKED_STRONG"
PARTIAL_SOURCE_STATUS = "SOURCE_BACKED_PARTIAL"
INVALID_SOURCE_STATUS = "INVALID_PACKAGE"
READY_ACTION = "READY_TO_APPLY_OR_HANDOFF"
NO_MISSING_SOURCE_ACTION = "none"
DEFAULT_ONLY_SOURCE_ACTION = "replace_default_only_runtime_surface_with_source_or_policy_claim"
FALLBACK_SOURCE_ACTION = "close_first_missing_chain"


@dataclass(frozen=True)
class SourceStatusResolution:
    source_backed_status: str
    strong_ready: bool
    first_missing_source_action: str
    default_only_runtime_surfaces: tuple[str, ...]
    missing_source_actions: tuple[str, ...]
    reasons: tuple[str, ...]
    diagnostic_only: bool = True
    apply_blocking: bool = False

    def as_operator_fields(self) -> dict[str, object]:
        return {
            "source_backed_status": self.source_backed_status,
            "source_strong_ready": self.strong_ready,
            "first_missing_source_action": self.first_missing_source_action,
            "source_missing_source_actions": self.missing_source_actions,
            "source_status_reasons": self.reasons,
            "source_status_diagnostic_only": self.diagnostic_only,
            "source_status_apply_blocking": self.apply_blocking,
        }
```

Then implement `resolve_source_status(...)` with this decision order:

```python
def resolve_source_status(
    *,
    technical_status: str,
    semantic_status: str,
    next_action: str,
    semantic_blockers: Sequence[object],
    default_only_runtime_surfaces: Sequence[str],
    source_claim_gap_report: Mapping[str, object] | None,
    closure_profile_closed: bool,
    closure_profile_first_missing_link: str = "",
) -> SourceStatusResolution:
    default_only_surfaces = _string_tuple(default_only_runtime_surfaces)
    first_missing_chain = _first_missing_chain(source_claim_gap_report)

    if technical_status != VALID_TECHNICAL_STATUS:
        return _resolution(
            source_backed_status=semantic_status or INVALID_SOURCE_STATUS,
            action=next_action or semantic_status or FALLBACK_SOURCE_ACTION,
            default_only_runtime_surfaces=default_only_surfaces,
            reasons=("technical_status_not_valid",),
        )

    if default_only_surfaces:
        return _resolution(
            source_backed_status=PARTIAL_SOURCE_STATUS,
            action=DEFAULT_ONLY_SOURCE_ACTION,
            default_only_runtime_surfaces=default_only_surfaces,
            reasons=("default_only_runtime_surface",),
        )

    if first_missing_chain is not None:
        return _resolution(
            source_backed_status=PARTIAL_SOURCE_STATUS,
            action=_report_next_action(source_claim_gap_report)
            or str(first_missing_chain.get("next_action") or "")
            or _source_action_for_missing_link(first_missing_chain),
            default_only_runtime_surfaces=default_only_surfaces,
            reasons=("first_missing_claim_chain",),
        )

    if semantic_blockers:
        return _resolution(
            source_backed_status=PARTIAL_SOURCE_STATUS,
            action=_action_from_semantic_blockers(semantic_blockers)
            or next_action
            or FALLBACK_SOURCE_ACTION,
            default_only_runtime_surfaces=default_only_surfaces,
            reasons=("semantic_blocker",),
        )

    if _has_unclosed_source_gap_summary(source_claim_gap_report):
        return _resolution(
            source_backed_status=PARTIAL_SOURCE_STATUS,
            action=_report_next_action(source_claim_gap_report) or FALLBACK_SOURCE_ACTION,
            default_only_runtime_surfaces=default_only_surfaces,
            reasons=("source_claim_gap_summary_not_closed",),
        )

    if closure_profile_closed and semantic_status == STRONG_SOURCE_STATUS and next_action == READY_ACTION:
        return SourceStatusResolution(
            source_backed_status=STRONG_SOURCE_STATUS,
            strong_ready=True,
            first_missing_source_action=NO_MISSING_SOURCE_ACTION,
            default_only_runtime_surfaces=default_only_surfaces,
            missing_source_actions=(),
            reasons=("source_backed_strong_ready",),
        )

    if not closure_profile_closed:
        return _resolution(
            source_backed_status=PARTIAL_SOURCE_STATUS,
            action=_source_action_for_profile_miss(closure_profile_first_missing_link)
            or FALLBACK_SOURCE_ACTION,
            default_only_runtime_surfaces=default_only_surfaces,
            reasons=("closure_profile_not_closed",),
        )

    return _resolution(
        source_backed_status=PARTIAL_SOURCE_STATUS,
        action=next_action or semantic_status or FALLBACK_SOURCE_ACTION,
        default_only_runtime_surfaces=default_only_surfaces,
        reasons=("semantic_status_not_strong",),
    )
```

Add private helpers for `_resolution`, `_first_missing_chain`, `_report_next_action`, `_source_action_for_missing_link`, `_action_from_semantic_blockers`, `_source_action_for_profile_miss`, `_has_unclosed_source_gap_summary`, `_string_tuple`, and `_int_value`. Keep all helpers pure.

- [ ] **Step 4: Run resolver tests**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python -m pytest tests/test_source_status_resolver.py -q
```

Expected: all resolver tests pass.

- [ ] **Step 5: Review resolver for forbidden behavior**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
rg -n "open\(|Path\(|requests|http|subprocess|write_text|apply_blocking=True" src\hsconfig\source_status_resolver.py
```

Expected: no output. The resolver must not read files, write files, call network, spawn processes, or set `apply_blocking=True`.

---

### Task 3: Make Operator Summary Consume The Resolver

**Files:**
- Modify: `src/hsconfig/operator_summary.py`
- Modify: `tests/test_operator_summary.py`

**Interfaces:**
- Consumes: `resolve_source_status(...) -> SourceStatusResolution`.
- Produces: additive operator fields:
  - `source_backed_status`
  - `source_strong_ready`
  - `first_missing_source_action`
  - `source_missing_source_actions`
  - `source_status_reasons`
  - `source_status_diagnostic_only`
  - `source_status_apply_blocking`

- [ ] **Step 1: Add failing operator-summary tests**

Add or verify tests asserting:

```python
def test_operator_summary_exposes_canonical_source_status_fields():
    summary = build_operator_summary(...)

    assert "source_backed_status" in summary
    assert "source_strong_ready" in summary
    assert "source_missing_source_actions" in summary
    assert "source_status_reasons" in summary
    assert summary["source_status_diagnostic_only"] is True
    assert summary["source_status_apply_blocking"] is False


def test_operator_summary_default_only_prevents_strong_without_blocking_apply():
    summary = build_operator_summary(...)

    assert summary["source_backed_status"] == "SOURCE_BACKED_PARTIAL"
    assert summary["first_missing_source_action"] == (
        "replace_default_only_runtime_surface_with_source_or_policy_claim"
    )
    assert summary["source_status_apply_blocking"] is False
```

Use existing test fixtures and builders in `tests/test_operator_summary.py`; do not create a second operator-summary builder.

- [ ] **Step 2: Run operator-summary tests**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python -m pytest tests/test_operator_summary.py -q
```

Expected before refactor: fails on missing fields or duplicated logic. Expected after refactor: passes.

- [ ] **Step 3: Refactor `build_operator_summary`**

In `src/hsconfig/operator_summary.py`, import the resolver:

```python
from hsconfig.source_status_resolver import SourceStatusResolution, resolve_source_status
```

Compute the resolution once after `default_only_runtime_surfaces` and closure profile are known:

```python
source_status_resolution = resolve_source_status(
    technical_status=technical_status,
    semantic_status=semantic_status,
    next_action=next_action,
    semantic_blockers=semantic_blockers,
    default_only_runtime_surfaces=default_only_runtime_surfaces,
    source_claim_gap_report=source_claim_gap_report,
    closure_profile_closed=closure_profile_verdict.strong_eligible,
    closure_profile_first_missing_link=closure_profile_verdict.first_missing_link,
)
```

Expose additive fields in the returned summary:

```python
"source_backed_status": source_status_resolution.source_backed_status,
"source_strong_ready": source_status_resolution.strong_ready,
"first_missing_source_action": source_status_resolution.first_missing_source_action,
"source_missing_source_actions": list(source_status_resolution.missing_source_actions),
"source_status_reasons": list(source_status_resolution.reasons),
"source_status_diagnostic_only": source_status_resolution.diagnostic_only,
"source_status_apply_blocking": source_status_resolution.apply_blocking,
```

Update `_source_backed_strong_closure(...)` so it accepts `source_status_resolution: SourceStatusResolution` and uses `source_status_resolution.strong_ready` plus `source_status_resolution.first_missing_source_action`.

- [ ] **Step 4: Remove duplicate local source-status helpers**

Delete local copies that duplicate resolver behavior:

```text
_source_claim_gaps_closed
_derived_first_missing_source_action
_first_missing_chain
_source_action_for_blocker
_source_action_for_missing_link
_source_action_for_profile_miss
```

Keep unrelated helpers intact.

- [ ] **Step 5: Run operator-summary tests again**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python -m pytest tests/test_operator_summary.py -q
```

Expected: pass.

---

### Task 4: Make Strong Promotion And Source Evidence Closure Consume The Resolver

**Files:**
- Modify: `src/hsconfig/strong_promotion_report.py`
- Modify: `src/hsconfig/source_evidence_closure.py`
- Modify: `tests/test_strong_promotion_report.py`
- Modify: `tests/test_source_evidence_closure.py`

**Interfaces:**
- Consumes: `resolve_source_status(...)`.
- Produces: matching source status/action fields across both diagnostic reports.

- [ ] **Step 1: Add failing strong-promotion tests**

Add or verify tests in `tests/test_strong_promotion_report.py`:

```python
def test_report_confirms_strong_when_resolver_is_strong_ready():
    report = build_strong_promotion_report(...)

    assert report["promotion_ready"] is True
    assert report["source_backed_status"] == "SOURCE_BACKED_STRONG"
    assert report["source_status_reasons"] == ["source_backed_strong_ready"]
    assert report["source_status_apply_blocking"] is False


def test_report_blocks_default_only_from_strong_but_not_apply():
    report = build_strong_promotion_report(...)

    assert report["promotion_ready"] is False
    assert report["source_backed_status"] == "SOURCE_BACKED_PARTIAL"
    assert report["first_missing_source_action"] == (
        "replace_default_only_runtime_surface_with_source_or_policy_claim"
    )
    assert report["source_status_apply_blocking"] is False
```

- [ ] **Step 2: Add failing source-evidence-closure tests**

Add or verify tests in `tests/test_source_evidence_closure.py`:

```python
def test_source_evidence_closure_exposes_resolver_fields():
    report = build_source_evidence_closure_report(...)

    assert "source_backed_status" in report
    assert "source_strong_ready" in report
    assert "source_status_reasons" in report
    assert report["source_status_diagnostic_only"] is True
    assert report["source_status_apply_blocking"] is False
    assert report["apply_blocking"] is False


def test_source_evidence_closure_recomputes_source_status_from_gap_report():
    report = build_source_evidence_closure_report(...)

    assert report["source_backed_status"] == "SOURCE_BACKED_PARTIAL"
    assert report["source_status_reasons"] == ["first_missing_claim_chain"]
    assert report["source_status_apply_blocking"] is False
```

- [ ] **Step 3: Run report tests**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python -m pytest tests/test_strong_promotion_report.py tests/test_source_evidence_closure.py -q
```

Expected before refactor: fails on missing or inconsistent resolver fields. Expected after refactor: passes.

- [ ] **Step 4: Refactor `strong_promotion_report.py`**

Import:

```python
from hsconfig.source_status_resolver import (
    first_missing_chain_from_report,
    resolve_source_status,
)
```

Replace local promotion-readiness calculations with:

```python
default_only_runtime_surfaces = _default_only_runtime_surfaces(operator_summary)
source_status_resolution = resolve_source_status(
    technical_status=str(operator_summary.get("technical_status") or ""),
    semantic_status=str(operator_summary.get("semantic_status") or ""),
    next_action=str(operator_summary.get("next_action") or ""),
    semantic_blockers=semantic_blockers,
    default_only_runtime_surfaces=default_only_runtime_surfaces,
    source_claim_gap_report=source_claim_gap_report,
    closure_profile_closed=_closure_profile_closed(operator_summary),
    closure_profile_first_missing_link=_closure_profile_first_missing_link(operator_summary),
)
promotion_ready = source_status_resolution.strong_ready
```

Return additive fields:

```python
"source_backed_status": source_status_resolution.source_backed_status,
"source_strong_ready": source_status_resolution.strong_ready,
"source_missing_source_actions": list(source_status_resolution.missing_source_actions),
"source_status_reasons": list(source_status_resolution.reasons),
"source_status_diagnostic_only": source_status_resolution.diagnostic_only,
"source_status_apply_blocking": source_status_resolution.apply_blocking,
"default_only_runtime_surfaces": default_only_runtime_surfaces,
"static_contract_status": source_status_resolution.source_backed_status,
```

Delete duplicate helpers that compute first missing action or first missing chain locally unless they are unrelated compatibility wrappers.

- [ ] **Step 5: Refactor `source_evidence_closure.py`**

Import:

```python
from hsconfig.source_status_resolver import resolve_source_status
```

Call `resolve_source_status(...)` from `build_source_evidence_closure_report(...)` using operator-summary status, semantic blockers, default-only surfaces, source claim gap report, and strong closure profile fields.

Return these fields:

```python
"source_backed_status": source_status_resolution.source_backed_status,
"source_strong_ready": source_status_resolution.strong_ready,
"first_missing_source_action": source_status_resolution.first_missing_source_action,
"source_missing_source_actions": list(source_status_resolution.missing_source_actions),
"source_status_reasons": list(source_status_resolution.reasons),
"source_status_diagnostic_only": source_status_resolution.diagnostic_only,
"source_status_apply_blocking": source_status_resolution.apply_blocking,
```

Keep:

```python
"authority": "diagnostic_only",
"classification": "diagnostic",
"apply_blocking": False,
"normal_apply_authority": "reports/operator_summary.json",
```

- [ ] **Step 6: Run report tests again**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python -m pytest tests/test_strong_promotion_report.py tests/test_source_evidence_closure.py -q
```

Expected: pass.

---

### Task 5: Sync Docs And Installed Skill Contract

**Files:**
- Modify: `.agents/skills/hsconfig/SKILL.md`
- Modify: `docs/operator/source-backed-strong-closure.md`
- Modify: `docs/operator/universal-wild-no-block-contract.md`
- Modify: `tests/test_operator_docs_contract_policy.py`
- Verify: `C:\Users\darbo\.codex\skills\hsconfig\SKILL.md`

**Interfaces:**
- Consumes: resolver fields and no-block/default-only contract.
- Produces: repo-local and installed skill text aligned with implementation.

- [ ] **Step 1: Add or tighten docs-policy tests**

Ensure `tests/test_operator_docs_contract_policy.py` rejects stale terms:

```python
STALE_SKILL_TERMS = (
    "source_closure_contract_proof",
    "strong_receipt",
    "source_class_max_ceiling",
    "effective_source_status",
    "promotion_blocker_reason",
)
```

Ensure the test checks repo-local and installed skill text when installed skill exists:

```python
def test_hsconfig_skill_does_not_reference_stale_source_contract_terms():
    texts = [
        Path(".agents/skills/hsconfig/SKILL.md").read_text(encoding="utf-8"),
    ]
    installed = Path.home() / ".codex" / "skills" / "hsconfig" / "SKILL.md"
    if installed.exists():
        texts.append(installed.read_text(encoding="utf-8"))

    for text in texts:
        for term in STALE_SKILL_TERMS:
            assert term not in text
```

- [ ] **Step 2: Run docs-policy tests and confirm failure before doc update**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python -m pytest tests/test_operator_docs_contract_policy.py -q
```

Expected before docs update: fails if stale terms or missing canonical resolver wording remain. Expected after docs update: passes.

- [ ] **Step 3: Update repo-local skill wording**

In `.agents/skills/hsconfig/SKILL.md`, include these exact facts in concise operator language:

```markdown
- Canonical source closure status comes from `src/hsconfig/source_status_resolver.py`: `source_backed_status`, `source_strong_ready`, `first_missing_source_action`, `source_missing_source_actions`, `source_status_reasons`, `source_status_diagnostic_only`, and `source_status_apply_blocking`.
- `operator_summary.json` remains the only normal apply authority.
- Source closure reports, source-candidate URLs, decklist pages, and online meta pages are diagnostic/source-acquisition artifacts only.
- `SOURCE_BACKED_STRONG` is an evidence-quality label, not a valid-deck generation or apply gate.
- `default_only_runtime_surfaces` must be visible and must prevent `SOURCE_BACKED_STRONG`; they must not set `source_status_apply_blocking=True`.
- Preserve Darkbishop Benedictus start-of-game/hero-power-transform runtime semantics, but do not infer opening-hand mulligan keep behavior without explicit keep-source evidence.
```

- [ ] **Step 4: Update operator docs**

In `docs/operator/source-backed-strong-closure.md`, document:

```markdown
`src/hsconfig/source_status_resolver.py` is the canonical source-status resolver.
`SOURCE_BACKED_STRONG` is emitted only when the technical package is valid, semantic status is strong, next action is ready, no default-only surfaces exist, source claim gaps are closed, and the closure profile is closed.
```

In `docs/operator/universal-wild-no-block-contract.md`, document:

```markdown
Valid Wild decks must still build load-safe packages when source evidence is partial.
Source-depth gaps are diagnostics and must keep `source_status_apply_blocking=false`.
Default-only runtime surfaces are visible quality debt and prevent strong status, but they are not a runtime apply blocker by themselves.
```

- [ ] **Step 5: Sync installed skill**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python scripts/sync_installed_skill.py
python scripts/sync_installed_skill.py --check
```

Expected: sync command exits 0 and check prints that `C:\Users\darbo\.codex\skills\hsconfig` is in sync.

- [ ] **Step 6: Run docs-policy tests again**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python -m pytest tests/test_operator_docs_contract_policy.py -q
```

Expected: pass.

---

### Task 6: Preserve ShadowPriest And Universal Wild No-Block Behavior

**Files:**
- Modify: `tests/test_universal_wild_no_block_matrix.py`
- Verify existing: `docs/operator/source-candidate-proof-decks.json`
- Verify generated runtime surfaces through existing test helpers

**Interfaces:**
- Consumes: configured Wild deck matrix.
- Produces: regression coverage for no-block, no-default-only, ShadowPriest/Darkbishop semantics, and source-status diagnostic-only behavior.

- [ ] **Step 1: Ensure the Wild matrix contains all requested decks**

Confirm the test matrix includes:

```python
USER_WILD_DECKS = (
    "ShadowPriest",
    "CtAPaladin",
    "PirateRogue",
    "BigShaman",
    "Discolock",
    "TreantDruid",
    "ImbueMage",
    "MechPala",
    "Kingslayer",
    "Boarlock",
    "PirateDH",
    "CuteWarrior",
)
```

- [ ] **Step 2: Add or verify no-block assertions**

In `tests/test_universal_wild_no_block_matrix.py`, each valid generated deck must satisfy:

```python
assert operator_summary["source_status_diagnostic_only"] is True
assert operator_summary["source_status_apply_blocking"] is False
assert source_to_runtime["apply_blocking"] is False
assert operator_summary["default_only_runtime_surfaces"] == []
assert operator_summary["default_only_runtime_surface_details"] == []
assert operator_summary["no_default_only_runtime_status"] == "clean"
```

- [ ] **Step 3: Add or verify ShadowPriest Darkbishop assertions**

For ShadowPriest:

```python
darkbishop_path = deck_dir / "SW_448.json"
assert darkbishop_path.exists()

mulligan_rows = _load_json(deck_dir / "Mulligan.json")
assert not any(
    row.get("mulligan") == "SW_448" or row.get("card_id") == "SW_448"
    for row in mulligan_rows
)

darkbishop_rows = _load_json(darkbishop_path)
assert any(
    "hero_power" in str(row).lower() or "shadow" in str(row).lower()
    for row in darkbishop_rows
)
```

The exact helper names may differ; use the helpers already present in `tests/test_universal_wild_no_block_matrix.py`.

- [ ] **Step 4: Run Wild matrix tests**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python -m pytest tests/test_universal_wild_no_block_matrix.py -q
```

Expected: pass.

---

### Task 7: Full Focused Verification And Handoff

**Files:**
- Verify all files modified by Tasks 2-6.

**Interfaces:**
- Consumes: full local diff.
- Produces: final evidence that the implementation is complete, current, narrow, and ready for commit or user review.

- [ ] **Step 1: Run the focused suite**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python -m pytest tests/test_source_status_resolver.py tests/test_operator_summary.py tests/test_strong_promotion_report.py tests/test_source_evidence_closure.py tests/test_operator_docs_contract_policy.py tests/test_universal_wild_no_block_matrix.py -q
```

Expected: all tests pass.

- [ ] **Step 2: Verify installed skill sync**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python scripts/sync_installed_skill.py --check
```

Expected: installed skill is in sync.

- [ ] **Step 3: Verify diff hygiene**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
git diff --check
```

Expected: exit code 0. Windows LF/CRLF warnings are acceptable if no whitespace errors are reported.

- [ ] **Step 4: Verify upstream state and local status**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
git rev-list --left-right --count HEAD...origin/main
git status --short --branch
```

Expected:

```text
0 0
```

and only intended plan/source-contract files modified or untracked.

- [ ] **Step 5: Review final diff scope**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
git diff --stat
```

Expected: changes are limited to resolver, operator/source reports, tests, docs, and skill sync. No generated runtime evidence, logs, replay files, or unrelated branches/files are included.

---

## Acceptance Criteria

- [x] `src/hsconfig/source_status_resolver.py` exists and is used by operator summary, strong promotion report, and source evidence closure.
- [x] No report has independent duplicate readiness logic that can drift from the resolver.
- [x] `SOURCE_BACKED_STRONG` is emitted only through resolver-compatible conditions.
- [x] `default_only_runtime_surfaces` are exposed and prevent strong status.
- [x] Source partial/missing status never sets `source_status_apply_blocking=True`.
- [x] Valid Wild decks still build load-safe packages even with partial source evidence.
- [x] ShadowPriest preserves Darkbishop `SW_448` effect semantics but does not keep `SW_448` in mulligan by default.
- [x] `.agents/skills/hsconfig/SKILL.md` and the installed global skill are synchronized.
- [x] Focused tests pass.
- [x] `git diff --check` passes.

## Subagent-Driven Execution Strategy

- **Explorer subagent, read-only:** map current call points in `operator_summary.py`, `strong_promotion_report.py`, and `source_evidence_closure.py`; confirm no duplicate source-status logic remains.
- **Contract reviewer subagent, read-only:** inspect docs and skill text for stale artifact names or wording that makes source closure an apply authority.
- **Wild matrix reviewer subagent, read-only:** confirm ShadowPriest/Darkbishop and the 12-deck Wild matrix assertions match the no-block/default-only contract.
- **Main writer:** implement Tasks 2-6 in order, run Task 7 verification, and consolidate all subagent findings.

No subagent should write files unless explicitly assigned one isolated file area by the main writer.

## Recommended Execution Command

After this plan is accepted, execute it with:

```text
Setze den Plan SubAgent Driven um
```

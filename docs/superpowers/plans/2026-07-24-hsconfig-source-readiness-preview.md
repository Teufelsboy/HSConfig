# HSConfig Source Readiness Preview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a compact diagnostic source-readiness preview that shows whether the generated package is source-backed strong, which source gap remains first, and that normal apply authority is still only `reports/operator_summary.json`.

**Architecture:** Keep the feature as a pure Python projection over existing artifacts: `source_candidate_plan.json`, `source_autopilot_report.json`, and `operator_summary.json`. The preview is diagnostic only, embedded into existing report surfaces, and verified by contract preflight so it cannot become a second apply gate.

**Tech Stack:** Python stdlib only, pytest, existing HSConfig CLI, existing `scripts/sync_installed_skill.py`, existing `scripts/check_hsconfig_currentness.py`.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig`.
- Do not use HSTuner.
- Do not parse gameplay logs, replays, HearthRanger logs, Hearthstone logs, HDT files, or private runtime evidence for this feature.
- Assume HearthRanger makes correct in-game decisions from valid HSConfig output; improve only HSConfig compile-time diagnostics.
- Do not add a new runtime apply gate.
- Do not add a second normal apply authority.
- `reports/operator_summary.json` remains the only normal apply authority.
- `source_status_apply_blocking` must remain `false`.
- `SOURCE_BACKED_STRONG` is an evidence-quality label, not an apply requirement.
- Unknown, thin, or partial-source decks must still produce load-safe packages.
- No silent default-only runtime surfaces may be hidden; expose `default_only_runtime_surfaces=[]` when clean.
- Darkbishop Benedictus effect semantics are allowed as hero-power-transform semantics; do not emit a mulligan keep for Darkbishop without explicit opening-hand source text.
- Keep the installed `hsconfig` skill synchronized after repo skill docs change.
- End with `git status --short --branch --untracked-files=all` showing no uncommitted changes.

---

## File Structure

- Create `src/hsconfig/source_readiness_preview.py`
  - Pure helper that accepts existing dictionaries and returns a stable diagnostic payload.
  - Owns all source-readiness projection field names.
  - Does not read files, write files, fetch network sources, or inspect runtime logs.
- Create `tests/test_source_readiness_preview.py`
  - Unit coverage for strong, partial, candidate-only, and missing-input projections.
- Modify `src/hsconfig/source_autopilot.py`
  - Embed `source_readiness_preview` inside `source_autopilot_report`.
- Modify `src/hsconfig/commands/configure.py`
  - Embed `source_readiness_preview` inside `configure_summary.json`.
- Modify `src/hsconfig/contract_preflight.py`
  - Add a visibility check and diagnostic contract payload for the preview.
- Modify `tests/test_source_autopilot.py`
  - Assert the autopilot report contains the preview and keeps it non-blocking.
- Modify `tests/test_configure_online_source.py`
  - Assert configure summaries expose the preview and preserve existing source/apply boundaries.
- Modify `tests/test_contract_preflight.py`
  - Assert preflight verifies preview visibility and reports a non-blocking diagnostic contract.
- Modify `docs/operator/source-builder-workflow.md`
  - Document the preview as diagnostic-only source readiness, not apply authority.
- Modify `.agents/skills/hsconfig/references/workflow.md`
  - Add the same operator-visible route in the thin skill workflow reference.
- Run `python scripts\sync_installed_skill.py`
  - Synchronize the installed skill from the repo skill copy.

---

### Task 1: Add Source Readiness Preview Helper

**Files:**
- Create: `src/hsconfig/source_readiness_preview.py`
- Create: `tests/test_source_readiness_preview.py`

**Interfaces:**
- Consumes:
  - `source_candidate_plan: Mapping[str, Any] | None`
  - `source_autopilot_report: Mapping[str, Any] | None`
  - `operator_summary: Mapping[str, Any] | None`
- Produces:
  - `build_source_readiness_preview(*, source_candidate_plan: Mapping[str, Any] | None = None, source_autopilot_report: Mapping[str, Any] | None = None, operator_summary: Mapping[str, Any] | None = None) -> dict[str, Any]`
  - Payload field `authority="diagnostic_source_readiness_preview"`.

- [ ] **Step 1: Write the failing helper tests**

Create `tests/test_source_readiness_preview.py` with this content:

```python
from __future__ import annotations

from hsconfig.source_readiness_preview import build_source_readiness_preview


def test_preview_reports_source_backed_strong_without_creating_apply_gate() -> None:
    preview = build_source_readiness_preview(
        source_candidate_plan={
            "authority": "diagnostic_source_candidate_plan",
            "source_urls": ["https://example.test/shadowpriest-guide"],
            "target_summary": {
                "card_targets": 3,
                "mulligan_keep_source_targets": 2,
                "effect_semantics_not_mulligan_keep_targets": 1,
            },
            "first_missing_source_action": "none",
        },
        source_autopilot_report={
            "semantic_status": "SOURCE_BACKED_STRONG",
            "strong_candidate": True,
            "strong_closure_summary": {
                "source_backed_strong_ready": True,
                "strong_evidence_row_count": 8,
                "first_missing_source_action": "none",
            },
            "source_backed_strong_closure": {
                "promotion_ready": True,
                "first_missing_source_action": "none",
            },
            "card_rows": [
                {"card_id": "SW_446", "lane": "lowered"},
                {"card_id": "NX2_019", "lane": "lowered"},
            ],
            "surface_rows": [
                {"surface": "Mulligan.json", "lane": "emitted"},
                {"surface": "NX2_019.json", "lane": "emitted"},
            ],
        },
        operator_summary={
            "semantic_status": "SOURCE_BACKED_STRONG",
            "source_backed_status": "SOURCE_BACKED_STRONG",
            "runtime_apply_allowed": True,
            "runtime_apply_mode": "load_safe_apply",
            "default_only_runtime_surfaces": [],
            "source_status_apply_blocking": False,
            "runtime_apply_contract": {
                "apply_authority": "reports/operator_summary.json",
            },
        },
    )

    assert preview == {
        "schema_version": 1,
        "authority": "diagnostic_source_readiness_preview",
        "diagnostic_only": True,
        "runtime_apply_authority": "reports/operator_summary.json",
        "apply_blocking": False,
        "runtime_write_performed": False,
        "source_status_apply_blocking": False,
        "source_candidate_plan_present": True,
        "source_autopilot_report_present": True,
        "operator_summary_present": True,
        "semantic_status": "SOURCE_BACKED_STRONG",
        "source_backed_strong_ready": True,
        "strong_candidate": True,
        "readiness_lane": "source_backed_strong_ready",
        "first_missing_source_action": "none",
        "recommended_next_source_action": "none",
        "candidate_source_url_count": 1,
        "strong_evidence_row_count": 8,
        "card_target_count": 3,
        "mulligan_keep_source_target_count": 2,
        "effect_semantics_not_mulligan_keep_target_count": 1,
        "card_source_gap_count": 0,
        "surface_source_gap_count": 0,
        "default_only_clean": True,
        "default_only_runtime_surfaces": [],
        "runtime_apply_allowed": True,
        "runtime_apply_mode": "load_safe_apply",
        "readiness_summary": "source-backed strong; no source action required",
    }


def test_preview_reports_partial_source_gap_without_blocking_apply() -> None:
    preview = build_source_readiness_preview(
        source_candidate_plan={
            "source_urls": ["https://example.test/thin-guide"],
            "target_summary": {
                "card_targets": 2,
                "mulligan_keep_source_targets": 1,
            },
            "first_missing_source_action": "fetch_and_normalize_candidate_full_text_claims",
        },
        source_autopilot_report={
            "semantic_status": "SOURCE_BACKED_PARTIAL",
            "strong_candidate": False,
            "strong_closure_summary": {
                "source_backed_strong_ready": False,
                "strong_evidence_row_count": 0,
                "first_missing_source_action": "add_current_card_specific_runtime_source",
            },
            "card_rows": [
                {"card_id": "CARD_001", "lane": "source_gap"},
                {"card_id": "CARD_002", "lane": "static_only"},
            ],
            "surface_rows": [
                {"surface": "Mulligan.json", "lane": "source_gap"},
            ],
        },
        operator_summary={
            "runtime_apply_allowed": True,
            "runtime_apply_mode": "load_safe_apply",
            "source_status_apply_blocking": False,
            "default_only_runtime_surfaces": [],
        },
    )

    assert preview["authority"] == "diagnostic_source_readiness_preview"
    assert preview["diagnostic_only"] is True
    assert preview["apply_blocking"] is False
    assert preview["source_status_apply_blocking"] is False
    assert preview["semantic_status"] == "SOURCE_BACKED_PARTIAL"
    assert preview["source_backed_strong_ready"] is False
    assert preview["readiness_lane"] == "source_partial_no_block"
    assert preview["first_missing_source_action"] == "add_current_card_specific_runtime_source"
    assert preview["recommended_next_source_action"] == "add_current_card_specific_runtime_source"
    assert preview["card_source_gap_count"] == 1
    assert preview["surface_source_gap_count"] == 1
    assert preview["default_only_clean"] is True
    assert preview["runtime_apply_allowed"] is True


def test_preview_uses_candidate_plan_when_autopilot_is_not_available() -> None:
    preview = build_source_readiness_preview(
        source_candidate_plan={
            "source_urls": ["https://example.test/guide"],
            "target_summary": {"card_targets": 1},
            "first_missing_source_action": "fetch_and_validate_explicit_source_urls",
        }
    )

    assert preview["source_candidate_plan_present"] is True
    assert preview["source_autopilot_report_present"] is False
    assert preview["operator_summary_present"] is False
    assert preview["readiness_lane"] == "acquisition_plan_ready_no_block"
    assert preview["first_missing_source_action"] == "fetch_and_validate_explicit_source_urls"
    assert preview["source_status_apply_blocking"] is False


def test_preview_handles_missing_inputs_without_runtime_write_or_block() -> None:
    preview = build_source_readiness_preview()

    assert preview["source_candidate_plan_present"] is False
    assert preview["source_autopilot_report_present"] is False
    assert preview["operator_summary_present"] is False
    assert preview["readiness_lane"] == "source_context_missing_no_block"
    assert preview["first_missing_source_action"] == "add_public_guide_url_or_use_static_semantics"
    assert preview["apply_blocking"] is False
    assert preview["runtime_write_performed"] is False
    assert preview["source_status_apply_blocking"] is False
```

- [ ] **Step 2: Run the new tests and confirm they fail for the missing module**

Run:

```powershell
pytest tests/test_source_readiness_preview.py -q
```

Expected output:

```text
ModuleNotFoundError: No module named 'hsconfig.source_readiness_preview'
```

- [ ] **Step 3: Implement the pure helper**

Create `src/hsconfig/source_readiness_preview.py` with this content:

```python
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

_AUTHORITY = "diagnostic_source_readiness_preview"
_NORMAL_APPLY_AUTHORITY = "reports/operator_summary.json"


def build_source_readiness_preview(
    *,
    source_candidate_plan: Mapping[str, Any] | None = None,
    source_autopilot_report: Mapping[str, Any] | None = None,
    operator_summary: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    candidate = _mapping(source_candidate_plan)
    autopilot = _mapping(source_autopilot_report)
    operator = _mapping(operator_summary)
    strong_summary = _mapping(autopilot.get("strong_closure_summary"))
    strong_closure = _mapping(autopilot.get("source_backed_strong_closure"))
    target_summary = _mapping(candidate.get("target_summary"))
    runtime_contract = _mapping(operator.get("runtime_apply_contract"))

    semantic_status = _text(
        operator.get("semantic_status")
        or operator.get("source_backed_status")
        or autopilot.get("semantic_status")
        or strong_summary.get("semantic_status")
    )
    source_backed_strong_ready = bool(
        strong_summary.get("source_backed_strong_ready")
        or strong_closure.get("promotion_ready")
        or semantic_status == "SOURCE_BACKED_STRONG"
    )
    strong_candidate = bool(
        autopilot.get("strong_candidate")
        or strong_summary.get("strong_candidate")
        or source_backed_strong_ready
    )
    first_missing_source_action = _first_action(
        operator,
        strong_summary,
        strong_closure,
        autopilot,
        candidate,
        source_backed_strong_ready=source_backed_strong_ready,
    )
    card_rows = _mapping_rows(autopilot.get("card_rows"))
    surface_rows = _mapping_rows(autopilot.get("surface_rows"))
    default_only_runtime_surfaces = _text_list(
        operator.get("default_only_runtime_surfaces")
    )
    readiness_lane = _readiness_lane(
        source_backed_strong_ready=source_backed_strong_ready,
        autopilot_present=bool(autopilot),
        candidate_present=bool(candidate),
    )

    return {
        "schema_version": 1,
        "authority": _AUTHORITY,
        "diagnostic_only": True,
        "runtime_apply_authority": _text(
            runtime_contract.get("apply_authority") or _NORMAL_APPLY_AUTHORITY
        ),
        "apply_blocking": False,
        "runtime_write_performed": False,
        "source_status_apply_blocking": False,
        "source_candidate_plan_present": bool(candidate),
        "source_autopilot_report_present": bool(autopilot),
        "operator_summary_present": bool(operator),
        "semantic_status": semantic_status,
        "source_backed_strong_ready": source_backed_strong_ready,
        "strong_candidate": strong_candidate,
        "readiness_lane": readiness_lane,
        "first_missing_source_action": first_missing_source_action,
        "recommended_next_source_action": first_missing_source_action,
        "candidate_source_url_count": len(_text_list(candidate.get("source_urls"))),
        "strong_evidence_row_count": _int(
            strong_summary.get("strong_evidence_row_count")
        ),
        "card_target_count": _int(target_summary.get("card_targets")),
        "mulligan_keep_source_target_count": _int(
            target_summary.get("mulligan_keep_source_targets")
        ),
        "effect_semantics_not_mulligan_keep_target_count": _int(
            target_summary.get("effect_semantics_not_mulligan_keep_targets")
        ),
        "card_source_gap_count": _lane_count(card_rows, "source_gap"),
        "surface_source_gap_count": _lane_count(surface_rows, "source_gap"),
        "default_only_clean": not default_only_runtime_surfaces,
        "default_only_runtime_surfaces": default_only_runtime_surfaces,
        "runtime_apply_allowed": bool(operator.get("runtime_apply_allowed", False)),
        "runtime_apply_mode": _text(operator.get("runtime_apply_mode")),
        "readiness_summary": _readiness_summary(
            readiness_lane,
            first_missing_source_action,
        ),
    }


def _first_action(
    *sources: Mapping[str, Any],
    source_backed_strong_ready: bool,
) -> str:
    if source_backed_strong_ready:
        return "none"
    for source in sources:
        value = _text(source.get("first_missing_source_action"))
        if value and value != "none":
            return value
    return "add_public_guide_url_or_use_static_semantics"


def _readiness_lane(
    *,
    source_backed_strong_ready: bool,
    autopilot_present: bool,
    candidate_present: bool,
) -> str:
    if source_backed_strong_ready:
        return "source_backed_strong_ready"
    if autopilot_present:
        return "source_partial_no_block"
    if candidate_present:
        return "acquisition_plan_ready_no_block"
    return "source_context_missing_no_block"


def _readiness_summary(readiness_lane: str, first_missing_source_action: str) -> str:
    if readiness_lane == "source_backed_strong_ready":
        return "source-backed strong; no source action required"
    return f"{readiness_lane}; next source action: {first_missing_source_action}"


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _mapping_rows(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    return [dict(row) for row in value if isinstance(row, Mapping)]


def _text_list(value: Any) -> list[str]:
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if not isinstance(value, Sequence):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _lane_count(rows: Sequence[Mapping[str, Any]], lane: str) -> int:
    return sum(1 for row in rows if _text(row.get("lane")) == lane)


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return str(value or "").strip()
```

- [ ] **Step 4: Run the helper tests and confirm they pass**

Run:

```powershell
pytest tests/test_source_readiness_preview.py -q
```

Expected output:

```text
4 passed
```

- [ ] **Step 5: Commit Task 1**

Run:

```powershell
git add src/hsconfig/source_readiness_preview.py tests/test_source_readiness_preview.py
git commit -m "feat: add source readiness preview helper"
```

Expected output:

```text
[codex/hsconfig-semantic-intent-scoring <hash>] feat: add source readiness preview helper
```

---

### Task 2: Embed Preview In Autopilot And Configure Summaries

**Files:**
- Modify: `src/hsconfig/source_autopilot.py`
- Modify: `src/hsconfig/commands/configure.py`
- Modify: `tests/test_source_autopilot.py`
- Modify: `tests/test_configure_online_source.py`

**Interfaces:**
- Consumes:
  - `build_source_readiness_preview(...)` from Task 1.
  - Existing `source_autopilot_report.json` payload.
  - Existing `configure_summary.json` payload.
- Produces:
  - `source_autopilot_report["source_readiness_preview"]`
  - `configure_summary["source_readiness_preview"]`

- [ ] **Step 1: Add failing autopilot report test assertions**

In `tests/test_source_autopilot.py`, extend the existing source-autopilot report test that calls `build_source_autopilot_bundle(...)`. Add these assertions after the report is built:

```python
    report = bundle["source_autopilot_report"]
    preview = report["source_readiness_preview"]

    assert preview["authority"] == "diagnostic_source_readiness_preview"
    assert preview["diagnostic_only"] is True
    assert preview["runtime_apply_authority"] == "reports/operator_summary.json"
    assert preview["apply_blocking"] is False
    assert preview["runtime_write_performed"] is False
    assert preview["source_status_apply_blocking"] is False
    assert preview["source_autopilot_report_present"] is True
    assert preview["operator_summary_present"] is False
    assert preview["semantic_status"] == report["semantic_status"]
    assert preview["source_backed_strong_ready"] == report[
        "strong_closure_summary"
    ]["source_backed_strong_ready"]
    assert preview["first_missing_source_action"] == report[
        "first_missing_source_action"
    ]
```

- [ ] **Step 2: Add failing configure summary test assertions**

In `tests/test_configure_online_source.py`, extend `test_configure_online_source_builds_source_backed_shadowpriest_package(...)` after `operator` is loaded:

```python
    preview = summary["source_readiness_preview"]
    autopilot_preview = autopilot["source_readiness_preview"]

    assert preview["authority"] == "diagnostic_source_readiness_preview"
    assert preview["diagnostic_only"] is True
    assert preview["runtime_apply_authority"] == "reports/operator_summary.json"
    assert preview["apply_blocking"] is False
    assert preview["runtime_write_performed"] is False
    assert preview["source_status_apply_blocking"] is False
    assert preview["source_candidate_plan_present"] is True
    assert preview["source_autopilot_report_present"] is True
    assert preview["operator_summary_present"] is True
    assert preview["semantic_status"] == operator["semantic_status"]
    assert preview["default_only_runtime_surfaces"] == []
    assert preview["default_only_clean"] is True
    assert preview["runtime_apply_allowed"] is True
    assert preview["runtime_apply_mode"] == "load_safe_apply"
    assert autopilot_preview["authority"] == "diagnostic_source_readiness_preview"
```

Also extend `test_configure_online_source_without_usable_guide_stays_load_safe_non_strong(...)` after `operator` is loaded:

```python
    summary = _read_json(out / "configure_summary.json")
    preview = summary["source_readiness_preview"]

    assert preview["authority"] == "diagnostic_source_readiness_preview"
    assert preview["diagnostic_only"] is True
    assert preview["readiness_lane"] in {
        "source_partial_no_block",
        "acquisition_plan_ready_no_block",
    }
    assert preview["source_status_apply_blocking"] is False
    assert preview["runtime_apply_allowed"] is True
    assert operator["semantic_status"] != "SOURCE_BACKED_STRONG"
```

- [ ] **Step 3: Run targeted tests and confirm they fail for missing preview fields**

Run:

```powershell
pytest tests/test_source_autopilot.py tests/test_configure_online_source.py -q
```

Expected output:

```text
KeyError: 'source_readiness_preview'
```

- [ ] **Step 4: Embed the preview in source autopilot**

In `src/hsconfig/source_autopilot.py`, add this import near the existing imports:

```python
from hsconfig.source_readiness_preview import build_source_readiness_preview
```

In `_build_report(...)`, replace the current direct `return { ... }` with a `report` variable using the existing payload unchanged, then add the preview:

```python
    report = {
        "schema_version": 1,
        "deck_name": deck_name,
        "status": "OK",
        "semantic_status": strong_closure_summary["semantic_status"],
        "runtime_apply_authority": "reports/operator_summary.json",
        "default_only_runtime_surfaces": [],
        "default_only_runtime_surface_status": "not_evaluated_in_source_preflight",
        "default_only_runtime_surfaces_scope": "source_preflight_not_runtime_proof",
        "source_rank_summary": dict(sorted(lane_counts.items())),
        "claim_kind_counts": dict(sorted(claim_counts.items())),
        "runtime_contract_candidate_count": len(lowerable_guide_rows),
        "card_specific_runtime_contract_candidate_count": len(
            card_specific_lowerable_guide_rows
        ),
        "strong_candidate": strong_candidate,
        "strong_candidate_blockers": blockers,
        "strong_closure_summary": strong_closure_summary,
        "source_backed_strong_closure": _source_backed_strong_closure(
            strong_closure_summary,
            profile_verdict,
        ),
        "first_missing_source_action": strong_closure_summary[
            "first_missing_source_action"
        ],
        "first_missing_source_action_by_card": _first_missing_source_action_by_card(
            deck_name,
            deck_identity,
            evidence_rows,
            current_date=current_date,
            profile_first_missing=profile_verdict.first_missing_link,
        ),
        "first_missing_source_action_by_surface": _first_missing_source_action_by_surface(
            evidence_rows,
            current_date=current_date,
            summary=strong_closure_summary,
        ),
        "card_rows": card_rows,
        "surface_rows": surface_rows,
        "card_closure_lanes": {
            row["card_id"]: row["lane"] for row in card_rows if row.get("card_id")
        },
        "surface_closure_lanes": {
            row["surface"]: row["lane"] for row in surface_rows if row.get("surface")
        },
        "non_promoting_claim_count": _non_promoting_claim_count(evidence_rows),
        "draft_summary": draft["draft_summary"],
        "verification_summary": {
            "status": verification.get("status"),
            "warning_count": len(warnings) if isinstance(warnings, list) else 0,
        },
    }
    report["source_readiness_preview"] = build_source_readiness_preview(
        source_autopilot_report=report,
    )
    return report
```

- [ ] **Step 5: Embed the preview in configure summary**

In `src/hsconfig/commands/configure.py`, add this import near the existing source imports:

```python
from hsconfig.source_readiness_preview import build_source_readiness_preview
```

Immediately before the final `_finish(...)` call that writes `configure_summary.json`, add:

```python
    source_autopilot_report = (
        _read_optional_json(source_autopilot_path / "source_autopilot_report.json")
        if source_autopilot_path
        else None
    )
    source_readiness_preview = build_source_readiness_preview(
        source_candidate_plan=source_candidate_plan,
        source_autopilot_report=source_autopilot_report,
        operator_summary=operator_summary,
    )
```

Then add this field to the `_finish(...)` payload:

```python
            "source_readiness_preview": source_readiness_preview,
```

- [ ] **Step 6: Run targeted tests and confirm they pass**

Run:

```powershell
pytest tests/test_source_readiness_preview.py tests/test_source_autopilot.py tests/test_configure_online_source.py -q
```

Expected output:

```text
passed
```

- [ ] **Step 7: Commit Task 2**

Run:

```powershell
git add src/hsconfig/source_autopilot.py src/hsconfig/commands/configure.py tests/test_source_autopilot.py tests/test_configure_online_source.py
git commit -m "feat: expose source readiness preview"
```

Expected output:

```text
[codex/hsconfig-semantic-intent-scoring <hash>] feat: expose source readiness preview
```

---

### Task 3: Add Contract Preflight And Operator Documentation

**Files:**
- Modify: `src/hsconfig/contract_preflight.py`
- Modify: `tests/test_contract_preflight.py`
- Modify: `docs/operator/source-builder-workflow.md`
- Modify: `.agents/skills/hsconfig/references/workflow.md`

**Interfaces:**
- Consumes:
  - `source_readiness_preview.py` implementation text.
  - `configure.py` implementation text.
  - `source_autopilot.py` implementation text.
  - Operator docs and skill workflow text.
- Produces:
  - `checks["source_readiness_preview_visible"]`
  - `payload["source_readiness_preview_contract"]`

- [ ] **Step 1: Add failing contract preflight tests**

In `tests/test_contract_preflight.py`, add:

```python
def test_contract_preflight_checks_source_readiness_preview_visibility(
    tmp_path: Path,
) -> None:
    payload = build_contract_preflight(
        Path("."),
        git=_clean_git(),
        skill_install_root=_synced_install_root(tmp_path),
    )

    contract = payload["source_readiness_preview_contract"]

    assert payload["status"] == "PASS"
    assert payload["checks"]["source_readiness_preview_visible"] is True
    assert "source_readiness_preview_visible" not in payload["failures"]
    assert contract == {
        "status": "visible",
        "authority": "diagnostic_source_readiness_preview",
        "implementation_path": "src/hsconfig/source_readiness_preview.py",
        "configure_summary_field": "source_readiness_preview",
        "autopilot_report_field": "source_readiness_preview",
        "runtime_apply_authority": "reports/operator_summary.json",
        "source_status_apply_blocking": False,
        "apply_blocking": False,
        "runtime_write_performed": False,
        "notes": [
            "Source readiness preview is diagnostic only.",
            "Preview cannot promote or block runtime apply.",
            "reports/operator_summary.json remains the only normal apply authority.",
        ],
    }


def test_contract_preflight_reports_attention_when_source_readiness_preview_drifts(
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
        Path("src") / "hsconfig" / "source_readiness_preview.py",
        source_root / "source_readiness_preview.py",
    )
    shutil.copy2(
        Path("src") / "hsconfig" / "source_autopilot.py",
        source_root / "source_autopilot.py",
    )
    command_root = source_root / "commands"
    command_root.mkdir(parents=True)
    shutil.copy2(
        Path("src") / "hsconfig" / "commands" / "configure.py",
        command_root / "configure.py",
    )

    preview_path = source_root / "source_readiness_preview.py"
    preview_path.write_text(
        preview_path.read_text(encoding="utf-8").replace(
            '"apply_blocking": False',
            '"apply_blocking": True',
        ),
        encoding="utf-8",
    )

    payload = build_contract_preflight(
        tmp_path,
        git=_clean_git(),
        skill_install_root=_synced_install_root(tmp_path),
    )

    assert payload["status"] == "ATTENTION"
    assert payload["checks"]["source_readiness_preview_visible"] is False
    assert "source_readiness_preview_visible" in payload["failures"]
    assert payload["source_readiness_preview_contract"]["status"] == "attention"
    assert payload["source_readiness_preview_contract"]["runtime_apply_authority"] == (
        "reports/operator_summary.json"
    )
    assert payload["source_readiness_preview_contract"][
        "source_status_apply_blocking"
    ] is False
```

- [ ] **Step 2: Run the contract tests and confirm they fail for the missing preflight field**

Run:

```powershell
pytest tests/test_contract_preflight.py::test_contract_preflight_checks_source_readiness_preview_visibility tests/test_contract_preflight.py::test_contract_preflight_reports_attention_when_source_readiness_preview_drifts -q
```

Expected output:

```text
KeyError: 'source_readiness_preview_contract'
```

- [ ] **Step 3: Implement the preflight contract**

In `src/hsconfig/contract_preflight.py`, add `"source_readiness_preview_visible"` to `EXPECTED_CHECK_KEYS` after `"source_candidate_plan_visible"`.

Add this helper near `_source_candidate_plan_contract_payload(...)`:

```python
def _source_readiness_preview_visible(
    source_readiness_preview_text: str,
    configure_text: str,
    source_autopilot_text: str,
    operator_text: str,
    workflow_text: str,
) -> bool:
    implementation_terms = (
        '_AUTHORITY = "diagnostic_source_readiness_preview"',
        '"authority": _AUTHORITY',
        '"diagnostic_only": True',
        '"runtime_apply_authority": _text(',
        '"apply_blocking": False',
        '"runtime_write_performed": False',
        '"source_status_apply_blocking": False',
        '"readiness_lane": readiness_lane',
    )
    configure_terms = (
        "build_source_readiness_preview",
        '"source_readiness_preview": source_readiness_preview',
    )
    autopilot_terms = (
        "build_source_readiness_preview",
        'report["source_readiness_preview"]',
    )
    docs_terms = (
        "source_readiness_preview",
        "diagnostic-only",
        "does not replace `reports/operator_summary.json`",
    )
    return (
        all(term in source_readiness_preview_text for term in implementation_terms)
        and all(term in configure_text for term in configure_terms)
        and all(term in source_autopilot_text for term in autopilot_terms)
        and all(term in operator_text for term in docs_terms)
        and all(term in workflow_text for term in docs_terms)
    )


def _source_readiness_preview_contract_payload(visible: bool) -> dict[str, object]:
    return {
        "status": "visible" if visible else "attention",
        "authority": "diagnostic_source_readiness_preview",
        "implementation_path": "src/hsconfig/source_readiness_preview.py",
        "configure_summary_field": "source_readiness_preview",
        "autopilot_report_field": "source_readiness_preview",
        "runtime_apply_authority": "reports/operator_summary.json",
        "source_status_apply_blocking": False,
        "apply_blocking": False,
        "runtime_write_performed": False,
        "notes": [
            "Source readiness preview is diagnostic only.",
            "Preview cannot promote or block runtime apply.",
            "reports/operator_summary.json remains the only normal apply authority.",
        ],
    }
```

In `build_contract_preflight(...)`, read the new files:

```python
    configure_text = _read(root / "src" / "hsconfig" / "commands" / "configure.py")
    source_autopilot_text = _read(root / "src" / "hsconfig" / "source_autopilot.py")
    source_readiness_preview_text = _read(
        root / "src" / "hsconfig" / "source_readiness_preview.py"
    )
```

Include those texts in `combined`:

```python
            configure_text,
            source_autopilot_text,
            source_readiness_preview_text,
```

Compute the boolean:

```python
    source_readiness_preview_visible = _source_readiness_preview_visible(
        source_readiness_preview_text,
        configure_text,
        source_autopilot_text,
        operator_text,
        workflow_text,
    )
```

Add the check:

```python
        "source_readiness_preview_visible": source_readiness_preview_visible,
```

Add the payload field:

```python
        "source_readiness_preview_contract": _source_readiness_preview_contract_payload(
            source_readiness_preview_visible
        ),
```

- [ ] **Step 4: Add operator and skill workflow documentation**

In `docs/operator/source-builder-workflow.md`, add this compact section near the existing source-candidate plan documentation:

```markdown
## Source Readiness Preview

`source_readiness_preview` is a diagnostic-only projection in `source_autopilot_report.json` and `configure_summary.json`.
It summarizes current source strength, first missing source action, card and surface source gaps, and default-only cleanliness.
It does not replace `reports/operator_summary.json`, cannot promote a package, cannot block apply, and keeps `source_status_apply_blocking=false`.
```

In `.agents/skills/hsconfig/references/workflow.md`, add the same section near the current source/configure route:

```markdown
## Source Readiness Preview

`source_readiness_preview` is a diagnostic-only projection in `source_autopilot_report.json` and `configure_summary.json`.
It summarizes current source strength, first missing source action, card and surface source gaps, and default-only cleanliness.
It does not replace `reports/operator_summary.json`, cannot promote a package, cannot block apply, and keeps `source_status_apply_blocking=false`.
```

- [ ] **Step 5: Run and pass preflight tests**

Run:

```powershell
pytest tests/test_contract_preflight.py -q
```

Expected output:

```text
passed
```

- [ ] **Step 6: Commit Task 3**

Run:

```powershell
git add src/hsconfig/contract_preflight.py tests/test_contract_preflight.py docs/operator/source-builder-workflow.md .agents/skills/hsconfig/references/workflow.md
git commit -m "test: guard source readiness preview contract"
```

Expected output:

```text
[codex/hsconfig-semantic-intent-scoring <hash>] test: guard source readiness preview contract
```

---

### Task 4: Synchronize Skill And Verify The Full Contract

**Files:**
- Modify by script: installed skill under `C:\Users\darbo\.codex\skills\hsconfig`
- Read-only verification: repository files and generated temporary pytest data

**Interfaces:**
- Consumes:
  - Repo skill under `.agents/skills/hsconfig`.
  - `scripts/sync_installed_skill.py`.
  - `scripts/check_hsconfig_currentness.py`.
- Produces:
  - Installed skill synchronized with repo skill.
  - Clean final git status after committing all tracked implementation changes.

- [ ] **Step 1: Synchronize the installed hsconfig skill**

Run:

```powershell
python scripts\sync_installed_skill.py
```

Expected output contains:

```text
synced
```

- [ ] **Step 2: Run focused feature tests**

Run:

```powershell
pytest tests/test_source_readiness_preview.py tests/test_source_autopilot.py tests/test_configure_online_source.py tests/test_contract_preflight.py -q
```

Expected output:

```text
passed
```

- [ ] **Step 3: Run full test suite**

Run:

```powershell
pytest -q
```

Expected output:

```text
passed
```

- [ ] **Step 4: Run repo currentness check**

Run:

```powershell
python scripts\check_hsconfig_currentness.py --cwd . --json
```

Expected JSON fields:

```json
{
  "dirty": false,
  "behind_origin_main": 0,
  "clean_for_runtime_work": true
}
```

- [ ] **Step 5: Run contract preflight**

Run:

```powershell
python -m hsconfig.cli contract-preflight --repo-root . --json
```

Expected JSON fields:

```json
{
  "source_status_apply_blocking": false,
  "diagnostic_only": true,
  "runtime_apply_authority": "reports/operator_summary.json"
}
```

Also confirm:

```json
{
  "checks": {
    "source_readiness_preview_visible": true,
    "source_candidate_plan_visible": true,
    "no_default_only_visible": true
  }
}
```

- [ ] **Step 6: Confirm the worktree is clean**

Run:

```powershell
git status --short --branch --untracked-files=all
```

Expected output has only the branch line:

```text
## codex/hsconfig-semantic-intent-scoring...origin/codex/hsconfig-semantic-intent-scoring
```

- [ ] **Step 7: If sync changed the installed skill only, do not commit installed-user files**

Run:

```powershell
git status --porcelain --untracked-files=all
```

Expected output:

```text

```

If this output is empty, the repo is clean. The installed skill path is outside this repository and is not committed from this repo.

---

## Self-Review

**Spec coverage:**
- Source/contract logic remains a pure diagnostic projection; Task 1 builds the helper and Task 3 guards it in preflight.
- No default-only hiding remains protected; Task 1 exposes `default_only_runtime_surfaces`, Task 2 projects it into configure output, and Task 3 keeps the existing no-default-only preflight check intact.
- No HSTuner or gameplay logs are used; this is covered by Global Constraints and the implementation only consumes existing compile-time dictionaries.
- The solution is narrow and robust; it adds one pure helper, two report embeddings, one preflight visibility check, and documentation.
- `SOURCE_BACKED_STRONG` remains evidence quality only; the preview reports readiness but always returns `apply_blocking=False` and `source_status_apply_blocking=False`.
- Darkbishop remains effect semantics only unless an explicit mulligan source exists; Task 1 exposes effect-semantics target counts and does not create mulligan rules.
- Current and clean completion is covered by Task 4 currentness, preflight, tests, and clean git status.

**Forbidden-token scan:**
- The plan avoids unfinished implementation markers and uses concrete file paths, concrete commands, expected outputs, and exact interface names.

**Type consistency:**
- `build_source_readiness_preview(...)` returns `dict[str, Any]` in Task 1 and is consumed with the same signature in Tasks 2 and 3.
- Field names are consistent across tasks: `source_readiness_preview`, `diagnostic_source_readiness_preview`, `source_status_apply_blocking`, `runtime_apply_authority`, `readiness_lane`, and `first_missing_source_action`.
- The preflight contract field name is `source_readiness_preview_contract` in both implementation and tests.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-24-hsconfig-source-readiness-preview.md`. Two execution options:

**1. Subagent-Driven (recommended)** - dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** - execute tasks in this session using executing-plans, batch execution with checkpoints.

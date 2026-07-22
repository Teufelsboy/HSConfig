# HSConfig Configure Source Closure Receipt Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one compact diagnostic-only `configure_summary.json.source_closure_receipt` so every `hsconfig configure` run shows source strength, no-default-only status, acquisition/claim counts, and the next source action without creating a second apply gate.

**Architecture:** Keep `reports/operator_summary.json` as the only normal apply authority. Add a pure receipt builder in a focused module, call it once from `configure_payload`, and expose the result only in `configure_summary.json`. The receipt reuses existing operator summary, source bundle, source documents, and source intake data; it does not fetch sources, write runtime config, tune gameplay, or inspect logs.

**Tech Stack:** Python 3.11+, stdlib `json`/`pathlib`/`collections`, existing `hsconfig` modules, pytest, existing installed-skill sync script.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig`.
- Do not use HSTuner, replay parsing, runtime logs, winrate analysis, or post-game tuning for this feature.
- Do not add new dependencies.
- Do not add new runtime output surfaces.
- Normal runtime output remains `GlobalValues.json`, `Mulligan.json`, per-card `<CARDID>.json`, and `Combo.json` only for exact ordered combo evidence.
- `reports/operator_summary.json` remains the only normal apply authority.
- `SOURCE_BACKED_STRONG` remains an evidence-quality label, not a generation or apply gate.
- `source_status_apply_blocking` must remain `false` for source-quality gaps.
- Default-only runtime surfaces must be visible, not silent, and must prevent `SOURCE_BACKED_STRONG` closure.
- Candidate registry URLs and `source_closure_intake_receipt.json` are acquisition input only; they cannot promote, block, write runtime config, or replace `reports/operator_summary.json`.
- Darkbishop Benedictus effect semantics stay effect/CardID semantics and must not become a Mulligan keep without explicit opening-hand source text.
- Keep the worktree clean at the end: commit or otherwise finish with `git status --short --branch` showing no modified or untracked files.

---

## File Structure

- Create: `src/hsconfig/configure_source_closure_receipt.py`
  - Pure builder for the new compact configure receipt.
  - Consumes already-generated configure/package data.
  - Produces diagnostic-only JSON-safe fields.
- Create: `tests/test_configure_source_closure_receipt.py`
  - Unit tests for strong, partial, and default-only receipt logic.
- Modify: `src/hsconfig/commands/configure.py`
  - Import the builder.
  - Read `source_documents_json` once when available.
  - Add `source_closure_receipt` to `configure_summary.json`.
- Modify: `tests/test_configure_auto_source.py`
  - Assert auto-source configure summaries include the receipt for strong and non-strong paths.
- Modify: `tests/test_configure_online_source.py`
  - Assert online-source configure summaries include acquisition counts and keep source gaps non-blocking.
- Modify: `docs/operator/README.md`
  - Document the new top-level configure receipt as the compact source-closure view after `acceptance_summary` and `handoff_contract`.
- Modify: `.agents/skills/hsconfig/SKILL.md`
  - Route Codex operators to the receipt without changing the single apply authority.
- Modify: `.agents/skills/hsconfig/references/workflow.md`
  - Mirror the operator workflow wording.
- Modify: `tests/test_operator_docs_contract_policy.py`
  - Pin the new docs/skill wording and no-second-gate boundary.
- Run: `scripts/sync_installed_skill.py`
  - Synchronize the repo skill to `C:\Users\darbo\.codex\skills\hsconfig`.

---

### Task 1: Add Pure Configure Source Closure Receipt Builder

**Files:**
- Create: `src/hsconfig/configure_source_closure_receipt.py`
- Create: `tests/test_configure_source_closure_receipt.py`

**Interfaces:**
- Consumes:
  - `operator_summary: Mapping[str, Any]`
  - `acceptance_summary: Mapping[str, Any]`
  - `guide_claim_bundle: Mapping[str, Any] | None`
  - `source_documents_payload: Mapping[str, Any] | None`
  - `source_candidate_urls: Sequence[str]`
  - `source_urls: Sequence[str]`
  - `source_closure_intake_receipt: Mapping[str, Any] | None`
- Produces:
  - `build_configure_source_closure_receipt(...) -> dict[str, Any]`
  - JSON-safe diagnostic receipt with no runtime apply authority.

- [ ] **Step 1: Write the failing unit tests**

Create `tests/test_configure_source_closure_receipt.py`:

```python
from __future__ import annotations

from hsconfig.configure_source_closure_receipt import (
    build_configure_source_closure_receipt,
)


def test_configure_source_closure_receipt_reports_strong_clean_source_closure():
    receipt = build_configure_source_closure_receipt(
        operator_summary={
            "runtime_apply_contract": {
                "apply_authority": "reports/operator_summary.json",
            },
            "technical_status": "VALID_PACKAGE",
            "runtime_apply_allowed": True,
            "runtime_apply_mode": "load_safe_apply",
            "source_backed_status": "SOURCE_BACKED_STRONG",
            "source_strong_ready": True,
            "source_status_apply_blocking": False,
            "source_status_diagnostic_only": True,
            "source_status_reasons": ["source_backed_strong_ready"],
            "first_missing_source_action": "none",
            "default_only_runtime_surfaces": [],
        },
        acceptance_summary={
            "use_config_now": True,
            "normal_apply_authority": "reports/operator_summary.json",
            "next_report_to_open": "reports/operator_summary.json",
        },
        guide_claim_bundle={
            "claims": [
                {"claim_kind": "gameplan_posture"},
                {"claim_kind": "mulligan_keep"},
                {"claim_kind": "hero_power_transform"},
                {"claim_kind": "archetype"},
            ],
        },
        source_documents_payload={
            "source_documents": [
                {"claims": [{"claim_kind": "mulligan_keep"}]},
                {"claims": [{"claim_kind": "targeting_rule"}]},
            ],
        },
        source_candidate_urls=["https://example.test/seed"],
        source_urls=["https://example.test/seed"],
        source_closure_intake_receipt={
            "candidate_count": 1,
            "fetched_record_count": 1,
            "promotion_eligible_seed_count": 1,
            "first_missing_source_action": "none",
        },
    )

    assert receipt == {
        "schema_version": 1,
        "authority": "diagnostic_only",
        "classification": "diagnostic",
        "apply_blocking": False,
        "runtime_write_performed": False,
        "operator_gate": "reports/operator_summary.json",
        "normal_apply_authority": "reports/operator_summary.json",
        "use_config_now": True,
        "technical_status": "VALID_PACKAGE",
        "runtime_apply_allowed": True,
        "runtime_apply_mode": "load_safe_apply",
        "source_backed_status": "SOURCE_BACKED_STRONG",
        "source_strong_ready": True,
        "source_status_diagnostic_only": True,
        "source_status_apply_blocking": False,
        "source_status_reasons": ["source_backed_strong_ready"],
        "first_missing_source_action": "none",
        "source_closure_lane": "strong",
        "default_only_clean": True,
        "default_only_runtime_surfaces": [],
        "source_candidate_url_count": 1,
        "source_url_count": 1,
        "source_intake_candidate_count": 1,
        "source_intake_promotion_eligible_seed_count": 1,
        "fetched_record_count": 1,
        "source_documents_count": 2,
        "compiled_claim_count": 4,
        "compiled_claim_kind_counts": {
            "archetype": 1,
            "gameplan_posture": 1,
            "hero_power_transform": 1,
            "mulligan_keep": 1,
        },
        "runtime_lowerable_claim_count": 3,
        "runtime_lowerable_claim_kind_count": 3,
        "next_report_to_open": "reports/operator_summary.json",
    }


def test_configure_source_closure_receipt_names_runtime_lowerable_claim_gap():
    receipt = build_configure_source_closure_receipt(
        operator_summary={
            "runtime_apply_contract": {
                "apply_authority": "reports/operator_summary.json",
            },
            "technical_status": "VALID_PACKAGE",
            "runtime_apply_allowed": True,
            "runtime_apply_mode": "load_safe_apply",
            "source_backed_status": "SOURCE_BACKED_PARTIAL",
            "source_strong_ready": False,
            "source_status_apply_blocking": False,
            "source_status_diagnostic_only": True,
            "source_status_reasons": ["semantic_blocker"],
            "first_missing_source_action": "add_card_specific_source_claim",
            "default_only_runtime_surfaces": [],
        },
        acceptance_summary={
            "use_config_now": True,
            "normal_apply_authority": "reports/operator_summary.json",
            "next_report_to_open": "reports/operator_summary.json",
        },
        guide_claim_bundle={
            "claims": [
                {"claim_kind": "archetype"},
                {"claim_kind": "tech_slot"},
            ],
        },
        source_documents_payload={
            "source_documents": [
                {"claims": [{"claim_kind": "archetype"}]},
            ],
        },
        source_candidate_urls=[],
        source_urls=["https://example.test/decklist"],
        source_closure_intake_receipt={
            "candidate_count": 0,
            "fetched_record_count": 1,
            "promotion_eligible_seed_count": 0,
            "first_missing_source_action": "add_card_specific_source_claim",
        },
    )

    assert receipt["authority"] == "diagnostic_only"
    assert receipt["apply_blocking"] is False
    assert receipt["source_status_apply_blocking"] is False
    assert receipt["source_backed_status"] == "SOURCE_BACKED_PARTIAL"
    assert receipt["source_strong_ready"] is False
    assert receipt["source_closure_lane"] == "runtime_lowerable_claim_needed"
    assert receipt["runtime_lowerable_claim_count"] == 0
    assert receipt["first_missing_source_action"] == "add_card_specific_source_claim"
    assert receipt["next_report_to_open"] == "reports/source_to_runtime_explainability.json"


def test_configure_source_closure_receipt_default_only_overrides_strong_claim():
    receipt = build_configure_source_closure_receipt(
        operator_summary={
            "runtime_apply_contract": {
                "apply_authority": "reports/operator_summary.json",
            },
            "technical_status": "VALID_PACKAGE",
            "runtime_apply_allowed": True,
            "runtime_apply_mode": "load_safe_apply",
            "source_backed_status": "SOURCE_BACKED_STRONG",
            "source_strong_ready": True,
            "source_status_apply_blocking": False,
            "source_status_diagnostic_only": True,
            "source_status_reasons": ["default_only_runtime_surface"],
            "first_missing_source_action": (
                "replace_default_only_runtime_surface_with_source_or_policy_claim"
            ),
            "default_only_runtime_surfaces": ["Mulligan.json"],
        },
        acceptance_summary={
            "use_config_now": True,
            "normal_apply_authority": "reports/operator_summary.json",
            "next_report_to_open": "reports/contract_doctor.json",
        },
        guide_claim_bundle={"claims": [{"claim_kind": "mulligan_keep"}]},
        source_documents_payload=None,
        source_candidate_urls=[],
        source_urls=[],
        source_closure_intake_receipt=None,
    )

    assert receipt["source_backed_status"] == "SOURCE_BACKED_STRONG"
    assert receipt["source_strong_ready"] is False
    assert receipt["default_only_clean"] is False
    assert receipt["default_only_runtime_surfaces"] == ["Mulligan.json"]
    assert receipt["source_closure_lane"] == "default_only_runtime_surface"
    assert receipt["next_report_to_open"] == "reports/contract_doctor.json"
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_configure_source_closure_receipt.py -q
```

Expected: FAIL with an import error for `hsconfig.configure_source_closure_receipt`.

- [ ] **Step 3: Implement the pure builder**

Create `src/hsconfig/configure_source_closure_receipt.py`:

```python
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from hsconfig.source_contract_matrix import source_contract_policy_by_claim_kind


NO_MISSING_SOURCE_ACTION = "none"
OPERATOR_GATE = "reports/operator_summary.json"


def build_configure_source_closure_receipt(
    *,
    operator_summary: Mapping[str, Any],
    acceptance_summary: Mapping[str, Any],
    guide_claim_bundle: Mapping[str, Any] | None,
    source_documents_payload: Mapping[str, Any] | None,
    source_candidate_urls: Sequence[str],
    source_urls: Sequence[str],
    source_closure_intake_receipt: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Return a compact diagnostic-only source closure receipt for configure."""

    normal_apply_authority = _normal_apply_authority(
        operator_summary,
        acceptance_summary,
    )
    default_only_runtime_surfaces = _string_list(
        operator_summary.get("default_only_runtime_surfaces")
    )
    first_missing_source_action = str(
        operator_summary.get("first_missing_source_action")
        or acceptance_summary.get("first_missing_source_action")
        or NO_MISSING_SOURCE_ACTION
    )
    source_backed_status = str(
        operator_summary.get("source_backed_status")
        or acceptance_summary.get("source_strength")
        or ""
    )
    source_status_apply_blocking = bool(
        operator_summary.get("source_status_apply_blocking", False)
    )
    source_status_reasons = _string_list(operator_summary.get("source_status_reasons"))
    source_intake = source_closure_intake_receipt or {}
    claims = _claim_rows(guide_claim_bundle, source_documents_payload)
    claim_kind_counts = Counter(
        str(claim.get("claim_kind") or "")
        for claim in claims
        if str(claim.get("claim_kind") or "")
    )
    lowerable_claim_kinds = _runtime_lowerable_claim_kinds()
    lowerable_claim_count = sum(
        1
        for claim in claims
        if str(claim.get("claim_kind") or "") in lowerable_claim_kinds
    )
    lowerable_claim_kind_count = len(
        {
            str(claim.get("claim_kind") or "")
            for claim in claims
            if str(claim.get("claim_kind") or "") in lowerable_claim_kinds
        }
    )
    source_documents_count = _source_documents_count(source_documents_payload)
    fetched_record_count = _int_value(source_intake.get("fetched_record_count"))
    source_strong_ready = (
        bool(operator_summary.get("source_strong_ready", False))
        and not source_status_apply_blocking
        and not default_only_runtime_surfaces
        and first_missing_source_action == NO_MISSING_SOURCE_ACTION
    )
    next_report_to_open = _next_report_to_open(
        first_missing_source_action=first_missing_source_action,
        default_only_runtime_surfaces=default_only_runtime_surfaces,
        acceptance_summary=acceptance_summary,
    )

    return {
        "schema_version": 1,
        "authority": "diagnostic_only",
        "classification": "diagnostic",
        "apply_blocking": False,
        "runtime_write_performed": False,
        "operator_gate": OPERATOR_GATE,
        "normal_apply_authority": normal_apply_authority,
        "use_config_now": bool(acceptance_summary.get("use_config_now", False)),
        "technical_status": str(operator_summary.get("technical_status") or ""),
        "runtime_apply_allowed": bool(
            operator_summary.get("runtime_apply_allowed", False)
        ),
        "runtime_apply_mode": str(operator_summary.get("runtime_apply_mode") or ""),
        "source_backed_status": source_backed_status,
        "source_strong_ready": source_strong_ready,
        "source_status_diagnostic_only": bool(
            operator_summary.get("source_status_diagnostic_only", True)
        ),
        "source_status_apply_blocking": source_status_apply_blocking,
        "source_status_reasons": source_status_reasons,
        "first_missing_source_action": first_missing_source_action,
        "source_closure_lane": _source_closure_lane(
            source_strong_ready=source_strong_ready,
            default_only_runtime_surfaces=default_only_runtime_surfaces,
            first_missing_source_action=first_missing_source_action,
            source_url_count=len(_string_list(source_urls)),
            fetched_record_count=fetched_record_count,
            source_documents_count=source_documents_count,
            lowerable_claim_count=lowerable_claim_count,
        ),
        "default_only_clean": not default_only_runtime_surfaces,
        "default_only_runtime_surfaces": default_only_runtime_surfaces,
        "source_candidate_url_count": len(_string_list(source_candidate_urls)),
        "source_url_count": len(_string_list(source_urls)),
        "source_intake_candidate_count": _int_value(source_intake.get("candidate_count")),
        "source_intake_promotion_eligible_seed_count": _int_value(
            source_intake.get("promotion_eligible_seed_count")
        ),
        "fetched_record_count": fetched_record_count,
        "source_documents_count": source_documents_count,
        "compiled_claim_count": len(claims),
        "compiled_claim_kind_counts": dict(sorted(claim_kind_counts.items())),
        "runtime_lowerable_claim_count": lowerable_claim_count,
        "runtime_lowerable_claim_kind_count": lowerable_claim_kind_count,
        "next_report_to_open": next_report_to_open,
    }


def _normal_apply_authority(
    operator_summary: Mapping[str, Any],
    acceptance_summary: Mapping[str, Any],
) -> str:
    runtime_contract = operator_summary.get("runtime_apply_contract")
    if isinstance(runtime_contract, Mapping):
        authority = str(runtime_contract.get("apply_authority") or "")
        if authority:
            return authority
    authority = str(acceptance_summary.get("normal_apply_authority") or "")
    return authority or OPERATOR_GATE


def _claim_rows(
    guide_claim_bundle: Mapping[str, Any] | None,
    source_documents_payload: Mapping[str, Any] | None,
) -> list[Mapping[str, Any]]:
    bundle_claims = _list_of_mappings(
        guide_claim_bundle.get("claims") if isinstance(guide_claim_bundle, Mapping) else []
    )
    if bundle_claims:
        return bundle_claims

    result: list[Mapping[str, Any]] = []
    for document in _source_documents(source_documents_payload):
        result.extend(_list_of_mappings(document.get("claims")))
    return result


def _source_documents_count(payload: Mapping[str, Any] | None) -> int:
    return len(_source_documents(payload))


def _source_documents(payload: Mapping[str, Any] | None) -> list[Mapping[str, Any]]:
    if not isinstance(payload, Mapping):
        return []
    return _list_of_mappings(payload.get("source_documents"))


def _runtime_lowerable_claim_kinds() -> set[str]:
    return {
        claim_kind
        for claim_kind, policy in source_contract_policy_by_claim_kind().items()
        if bool(policy.get("runtime_lowerable", False))
    }


def _source_closure_lane(
    *,
    source_strong_ready: bool,
    default_only_runtime_surfaces: Sequence[str],
    first_missing_source_action: str,
    source_url_count: int,
    fetched_record_count: int,
    source_documents_count: int,
    lowerable_claim_count: int,
) -> str:
    if source_strong_ready:
        return "strong"
    if default_only_runtime_surfaces:
        return "default_only_runtime_surface"
    if source_url_count and fetched_record_count == 0:
        return "fetch_needed"
    if fetched_record_count and source_documents_count == 0:
        return "claim_normalization_needed"
    if lowerable_claim_count == 0:
        return "runtime_lowerable_claim_needed"
    if first_missing_source_action in {
        "add_explicit_mulligan_source",
        "build_source_or_policy_backed_mulligan",
    }:
        return "mulligan_claim_needed"
    if first_missing_source_action in {
        "add_runtime_lowerable_claim_or_router_support",
        "add_runtime_source_claim",
        "replace_default_only_runtime_surface_with_source_or_policy_claim",
    }:
        return "runtime_surface_needed"
    if first_missing_source_action == NO_MISSING_SOURCE_ACTION:
        return "closed_without_strong"
    return "source_action_needed"


def _next_report_to_open(
    *,
    first_missing_source_action: str,
    default_only_runtime_surfaces: Sequence[str],
    acceptance_summary: Mapping[str, Any],
) -> str:
    if default_only_runtime_surfaces:
        return "reports/contract_doctor.json"
    if first_missing_source_action != NO_MISSING_SOURCE_ACTION:
        return "reports/source_to_runtime_explainability.json"
    return str(acceptance_summary.get("next_report_to_open") or OPERATOR_GATE)


def _list_of_mappings(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value else []
    if not isinstance(value, Sequence):
        return []
    return [str(item) for item in value if str(item)]


def _int_value(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
```

- [ ] **Step 4: Run the unit tests**

Run:

```powershell
python -m pytest tests/test_configure_source_closure_receipt.py -q
```

Expected: `3 passed`.

- [ ] **Step 5: Commit Task 1**

```powershell
git add src/hsconfig/configure_source_closure_receipt.py tests/test_configure_source_closure_receipt.py
git commit -m "feat: add configure source closure receipt builder"
```

---

### Task 2: Wire Receipt Into `hsconfig configure`

**Files:**
- Modify: `src/hsconfig/commands/configure.py`
- Modify: `tests/test_configure_auto_source.py`
- Modify: `tests/test_configure_online_source.py`

**Interfaces:**
- Consumes:
  - `build_configure_source_closure_receipt(...)` from Task 1.
  - Existing local `read_json(path)` helper.
- Produces:
  - Top-level `configure_summary.json["source_closure_receipt"]`.

- [ ] **Step 1: Write failing configure assertions**

In `tests/test_configure_auto_source.py`, extend `test_configure_auto_source_builds_load_safe_package_without_darkbishop_mulligan` after `summary = _read_json(...)`:

```python
    source_closure_receipt = summary["source_closure_receipt"]
    assert source_closure_receipt["authority"] == "diagnostic_only"
    assert source_closure_receipt["operator_gate"] == "reports/operator_summary.json"
    assert source_closure_receipt["normal_apply_authority"] == "reports/operator_summary.json"
    assert source_closure_receipt["apply_blocking"] is False
    assert source_closure_receipt["runtime_write_performed"] is False
    assert source_closure_receipt["source_backed_status"] == operator["source_backed_status"]
    assert source_closure_receipt["source_status_apply_blocking"] is False
    assert source_closure_receipt["first_missing_source_action"] == "none"
    assert source_closure_receipt["default_only_clean"] is True
    assert source_closure_receipt["default_only_runtime_surfaces"] == []
    assert source_closure_receipt["source_closure_lane"] == "strong"
    assert source_closure_receipt["compiled_claim_count"] >= 1
    assert source_closure_receipt["runtime_lowerable_claim_count"] >= 1
```

In `tests/test_configure_auto_source.py`, extend `test_configure_auto_source_keeps_decklist_only_non_strong_but_load_safe` after `operator = _read_json(...)`:

```python
    source_closure_receipt = _read_json(out / "configure_summary.json")[
        "source_closure_receipt"
    ]
    assert source_closure_receipt["authority"] == "diagnostic_only"
    assert source_closure_receipt["apply_blocking"] is False
    assert source_closure_receipt["source_status_apply_blocking"] is False
    assert source_closure_receipt["source_backed_status"] == operator["source_backed_status"]
    assert source_closure_receipt["source_strong_ready"] is False
    assert source_closure_receipt["source_closure_lane"] in {
        "runtime_lowerable_claim_needed",
        "source_action_needed",
    }
    assert source_closure_receipt["next_report_to_open"] == (
        "reports/source_to_runtime_explainability.json"
    )
```

In `tests/test_configure_online_source.py`, extend `test_configure_writes_source_bundle_for_online_source` after `receipt = _read_json(receipt_path)`:

```python
    source_closure_receipt = result["source_closure_receipt"]
    assert source_closure_receipt["authority"] == "diagnostic_only"
    assert source_closure_receipt["source_candidate_url_count"] == len(
        result["source_candidate_urls"]
    )
    assert source_closure_receipt["source_url_count"] == len(result["source_urls"])
    assert source_closure_receipt["source_intake_candidate_count"] == receipt[
        "candidate_count"
    ]
    assert source_closure_receipt["fetched_record_count"] == receipt[
        "fetched_record_count"
    ]
    assert source_closure_receipt["source_status_apply_blocking"] is False
    assert source_closure_receipt["normal_apply_authority"] == (
        "reports/operator_summary.json"
    )
```

- [ ] **Step 2: Run configure tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_configure_auto_source.py tests/test_configure_online_source.py -q
```

Expected: FAIL because `configure_summary.json` has no `source_closure_receipt`.

- [ ] **Step 3: Wire the builder into `configure.py`**

Modify `src/hsconfig/commands/configure.py` imports:

```python
from hsconfig.configure_source_closure_receipt import (
    build_configure_source_closure_receipt,
)
```

Add this helper near `_first_source_status_reason`:

```python
def _read_optional_json(path: str | Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    try:
        payload = read_json(Path(path))
    except FileNotFoundError:
        return None
    return payload if isinstance(payload, dict) else None
```

In `configure_payload`, after `handoff_contract = _build_handoff_contract(...)`, add:

```python
    source_closure_receipt = build_configure_source_closure_receipt(
        operator_summary=operator_summary,
        acceptance_summary=acceptance_summary,
        guide_claim_bundle=guide_claim_bundle,
        source_documents_payload=_read_optional_json(source_documents_json),
        source_candidate_urls=source_candidate_urls,
        source_urls=source_urls,
        source_closure_intake_receipt=source_closure_intake_receipt,
    )
```

In the final `_finish(...)` payload, add this field beside the existing compact summaries:

```python
            "source_closure_receipt": source_closure_receipt,
```

- [ ] **Step 4: Run configure tests**

Run:

```powershell
python -m pytest tests/test_configure_source_closure_receipt.py tests/test_configure_auto_source.py tests/test_configure_online_source.py -q
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit Task 2**

```powershell
git add src/hsconfig/commands/configure.py tests/test_configure_auto_source.py tests/test_configure_online_source.py
git commit -m "feat: expose source closure receipt in configure summary"
```

---

### Task 3: Document The New Receipt Without Changing Apply Authority

**Files:**
- Modify: `docs/operator/README.md`
- Modify: `.agents/skills/hsconfig/SKILL.md`
- Modify: `.agents/skills/hsconfig/references/workflow.md`
- Modify: `tests/test_operator_docs_contract_policy.py`
- Runtime sync: `C:\Users\darbo\.codex\skills\hsconfig`

**Interfaces:**
- Consumes:
  - Existing installed skill sync command `python scripts\sync_installed_skill.py`.
- Produces:
  - Active operator docs and installed skill mention `configure_summary.json.source_closure_receipt`.
  - No wording makes the receipt an apply gate.

- [ ] **Step 1: Add failing docs policy test**

Append this test to `tests/test_operator_docs_contract_policy.py`:

```python
def test_docs_and_skill_route_configure_source_closure_receipt_without_second_gate():
    active_text = "\n".join(
        [
            (ROOT / "docs/operator/README.md").read_text(encoding="utf-8"),
            (ROOT / ".agents/skills/hsconfig/SKILL.md").read_text(encoding="utf-8"),
            (
                ROOT / ".agents/skills/hsconfig/references/workflow.md"
            ).read_text(encoding="utf-8"),
        ]
    )

    assert "configure_summary.json.source_closure_receipt" in active_text
    assert "compact diagnostic-only source-closure receipt" in active_text
    assert "does not replace `reports/operator_summary.json`" in active_text
    assert "cannot promote, block, apply, or write runtime files" in active_text
    assert "source_status_apply_blocking=false" in active_text
    assert "default-only runtime surfaces remain visible quality debt" in active_text
    assert "source_closure_receipt remains the normal apply authority" not in active_text.lower()
```

- [ ] **Step 2: Run docs policy test to verify it fails**

Run:

```powershell
python -m pytest tests/test_operator_docs_contract_policy.py::test_docs_and_skill_route_configure_source_closure_receipt_without_second_gate -q
```

Expected: FAIL because the new wording is not present.

- [ ] **Step 3: Update operator docs**

In `docs/operator/README.md`, update the "Quick Start" and "Normal Operator Path" wording so it includes:

```markdown
- After `configure`, read `<out>/configure_summary.json.acceptance_summary`
  first, then `<out>/configure_summary.json.handoff_contract`, then
  `<out>/configure_summary.json.source_closure_receipt` when source depth is
  the question. `source_closure_receipt` is a compact diagnostic-only
  source-closure receipt. It does not replace `reports/operator_summary.json`,
  cannot promote, block, apply, or write runtime files, and keeps
  source_status_apply_blocking=false.
```

Add this short paragraph near the existing configure summary explanation:

```markdown
`configure_summary.json.source_closure_receipt` is the compact diagnostic-only
source-closure receipt for normal generated packages. It mirrors the canonical
source status, no-default-only status, source acquisition counts, source
document counts, runtime-lowerable claim counts, and the first missing source
action. It does not replace `reports/operator_summary.json`, cannot promote,
block, apply, or write runtime files, and default-only runtime surfaces remain
visible quality debt rather than hidden success.
```

- [ ] **Step 4: Update repo skill instructions**

In `.agents/skills/hsconfig/SKILL.md`, update the configure summary paragraph to include:

```markdown
Then read `<out>/configure_summary.json.source_closure_receipt` when source
depth is the question. It is a compact diagnostic-only source-closure receipt
for `source_backed_status`, `source_strong_ready`, no-default-only visibility,
acquisition/source-document/claim counts, and `first_missing_source_action`.
It does not replace `reports/operator_summary.json`, cannot promote, block,
apply, or write runtime files, and keeps source_status_apply_blocking=false.
Default-only runtime surfaces remain visible quality debt.
```

- [ ] **Step 5: Update workflow reference**

In `.agents/skills/hsconfig/references/workflow.md`, update the "Gate And Readiness" section to include:

```markdown
`configure_summary.json.source_closure_receipt` is the compact diagnostic-only
source-closure receipt for source-depth questions after `acceptance_summary`
and `handoff_contract`. It shows canonical source status, no-default-only
visibility, acquisition/source-document/claim counts, runtime-lowerable claim
counts, and `first_missing_source_action`. It does not replace
`reports/operator_summary.json`, cannot promote, block, apply, or write runtime
files, and keeps source_status_apply_blocking=false. Default-only runtime
surfaces remain visible quality debt.
```

- [ ] **Step 6: Sync installed skill**

Run:

```powershell
python scripts\sync_installed_skill.py
python scripts\sync_installed_skill.py --check
```

Expected:

```text
HSConfig skill is in sync: C:\Users\darbo\.codex\skills\hsconfig
```

- [ ] **Step 7: Run docs and skill tests**

Run:

```powershell
python -m pytest tests/test_operator_docs_contract_policy.py tests/test_skill_contract_entrypoint.py tests/test_skill_sync.py tests/test_skill_files.py -q
```

Expected: all selected tests pass.

- [ ] **Step 8: Commit Task 3**

```powershell
git add docs/operator/README.md .agents/skills/hsconfig/SKILL.md .agents/skills/hsconfig/references/workflow.md tests/test_operator_docs_contract_policy.py
git commit -m "docs: route configure source closure receipt"
```

Do not stage `C:\Users\darbo\.codex\skills\hsconfig`; it is outside the repository. The sync check is the required evidence for the installed copy.

---

### Task 4: Final Contract Verification And Clean Handoff

**Files:**
- Verify only; no new source files.

**Interfaces:**
- Consumes:
  - Builder, configure summary integration, docs/skill updates from Tasks 1 to 3.
- Produces:
  - Green focused verification.
  - Clean worktree.
  - Pushed branch when remote access succeeds.

- [ ] **Step 1: Run focused implementation tests**

Run:

```powershell
python -m pytest tests/test_configure_source_closure_receipt.py tests/test_configure_auto_source.py tests/test_configure_online_source.py tests/test_configure_handoff_contract.py -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run docs and skill verification**

Run:

```powershell
python scripts\sync_installed_skill.py --check
python -m pytest tests/test_operator_docs_contract_policy.py tests/test_skill_contract_entrypoint.py tests/test_skill_sync.py tests/test_skill_files.py -q
```

Expected:

```text
HSConfig skill is in sync: C:\Users\darbo\.codex\skills\hsconfig
```

and all selected tests pass.

- [ ] **Step 3: Run contract preflight**

Run:

```powershell
python -m hsconfig.cli contract-preflight --json
```

Expected:

```json
{
  "status": "PASS",
  "diagnostic_only": true,
  "runtime_apply_authority": "reports/operator_summary.json",
  "source_status_apply_blocking": false
}
```

Extra fields may be present. Confirm that any research-context attention remains diagnostic-only and does not change `source_status_apply_blocking=false`.

- [ ] **Step 4: Run currentness and worktree checks**

Run:

```powershell
git fetch --all --prune --tags
python scripts\check_hsconfig_currentness.py --cwd . --json
git status --short --branch
```

Expected:

```json
{
  "dirty": false,
  "behind_origin_main": 0,
  "clean_for_runtime_work": true
}
```

and `git status --short --branch` shows no modified or untracked files.

- [ ] **Step 5: Push the implementation branch**

Run:

```powershell
git push
```

Expected: remote branch receives the implementation commits, and a final `git status --short --branch` shows the branch synchronized with its upstream.

---

## Self-Review

**Spec coverage:** This plan implements the recommended narrow improvement: a configure-level source closure receipt. It preserves HSConfig-only operation, no HSTuner, no runtime logs, no gameplay sequencing engine, no new runtime surfaces, no second apply authority, no source-quality apply blocker, and no silent default-only success.

**Placeholder scan:** The plan contains concrete file paths, function names, test code, implementation code, commands, and expected outcomes. It does not use placeholder instructions.

**Type consistency:** The shared function is consistently named `build_configure_source_closure_receipt(...)`. The configure summary key is consistently `source_closure_receipt`. The receipt fields are consistently diagnostic-only and keep `normal_apply_authority` and `operator_gate` pinned to `reports/operator_summary.json`.

**Execution choice:** This plan is ready for `superpowers:subagent-driven-development`. Use one worker for Task 1, one worker for Task 2, one worker for Task 3, and reserve Task 4 for the main agent final verification and clean handoff.

# HSConfig Source Contract Reconciliation And CardID Baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make HSConfig source closure honest and uniform across all package-producing paths, while making per-card baseline-only output visible so valid decks always build but never look `SOURCE_BACKED_STRONG` or no-default-only unless the runtime surfaces are actually closed.

**Architecture:** Add one small post-package reconciliation module that runs the existing canonical resolver and rewrites only diagnostic source-status fields in `operator_summary.json` and `source_quality_receipt.json`. Extend existing config-usefulness and operator-summary ledger logic so per-card `<CARDID>.json` files that contain only baseline priority are visible as baseline-only/default-only quality debt with a concrete next source action, without creating another apply gate.

**Tech Stack:** Python, pytest, existing HSConfig JSON report builders, existing `source_status_resolver`, existing `source_evidence_closure`, existing `operator_summary` and `config_usefulness`.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig`.
- Do not revert unrelated dirty worktree changes.
- `reports/operator_summary.json` remains the only normal runtime apply authority.
- `SOURCE_BACKED_STRONG` remains an evidence-quality label, not an apply gate.
- Valid decks must still build load-safe when source depth is partial or unavailable.
- Candidate URLs, decklists, stats pages, policy fallback rows, runtime examples, snippets, and default runtime rows must not promote `SOURCE_BACKED_STRONG`.
- Static card semantics can support CardID/effect surfaces only when the claim kind matches the runtime surface.
- Darkbishop Benedictus and other start-of-game non-hand effects must preserve effect/runtime semantics but must not become `mulligan_keep` without explicit opening-hand mulligan evidence.
- Normal HSConfig output must not emit `Presume.json`, `Concede.json`, or aggregate `CardBehavior.json`.

---

## File Structure

- Create: `src/hsconfig/source_artifact_reconciliation.py`
  - One responsibility: run canonical source-status reconciliation after package artifacts exist, then keep `operator_summary`, `source_quality_receipt`, `strong_receipt`, and `source_closure_contract_proof` aligned.
- Create: `tests/test_source_artifact_reconciliation.py`
  - Unit proof for false-strong downgrade, receipt sync, proof rebuild, default-only downgrade, and diagnostic-only apply boundary.
- Modify: `src/hsconfig/commands/configure.py`
  - Replace the inline resolver/receipt sync block with the new helper.
- Modify: `src/hsconfig/package_builder.py`
  - Run the same helper in the direct package/prepare path before the final `operator_summary.json` write.
- Modify: `src/hsconfig/config_usefulness.py`
  - Make CardID baseline-only state explicit.
- Modify: `src/hsconfig/operator_summary.py`
  - Carry `first_missing_link` and `next_source_action` from CardID baseline/missing state into `surface_status_ledger`.
- Modify: `tests/test_configure_auto_source.py` or `tests/test_configure_online_source_pack.py`
  - Assert configure output still has synced source status and diagnostic-only proof.
- Modify: `tests/test_operator_summary.py`
  - Assert ledger exposes CardID baseline-only and missing-surface repair fields.
- Modify: `tests/test_claim_kind_runtime_contract.py`
  - Add a generalized start-of-game non-hand effect canary, not only Darkbishop.
- Modify: `tests/test_no_default_only_adversarial_corpus.py`
  - Add an end-to-end proof that baseline-only CardID cannot hide as clean no-default-only closure.

---

### Task 1: Central Source Artifact Reconciliation

**Files:**
- Create: `src/hsconfig/source_artifact_reconciliation.py`
- Create: `tests/test_source_artifact_reconciliation.py`

**Interfaces:**
- Consumes:
  - `resolve_source_status(operator_summary, source_pack, source_quality_receipt, matrix_row=None) -> CanonicalSourceStatus`
  - `sync_compact_strong_receipt(receipt: dict[str, Any]) -> dict[str, Any]`
  - `build_source_closure_contract_proof(operator_summary, source_to_runtime=None, source_quality_receipt=None) -> dict[str, Any]`
- Produces:
  - `reconcile_source_artifacts(*, operator_summary: dict[str, Any], source_pack: Mapping[str, Any] | None, source_quality_receipt: dict[str, Any], source_to_runtime_explainability: Mapping[str, Any] | None = None, matrix_row: Mapping[str, Any] | None = None) -> tuple[dict[str, Any], dict[str, Any]]`

- [ ] **Step 1: Write failing tests for canonical source artifact reconciliation**

Create `tests/test_source_artifact_reconciliation.py`:

```python
from __future__ import annotations

from hsconfig.source_artifact_reconciliation import reconcile_source_artifacts


def test_reconcile_downgrades_false_strong_and_syncs_receipt_and_proof():
    operator_summary = {
        "technical_status": "VALID_PACKAGE",
        "semantic_status": "SOURCE_BACKED_STRONG",
        "runtime_apply_allowed": True,
        "default_only_runtime_surfaces": [],
        "no_default_only_runtime_status": "clean",
        "first_missing_source_action": "none",
        "source_backed_strong_closure": {
            "diagnostic_only": True,
            "first_missing_source_action": "none",
        },
    }
    source_pack = {
        "quality_summary": {
            "source_backed_status": "SOURCE_BACKED_STRONG",
            "has_full_text_guide": False,
            "has_deck_matched_guide": True,
            "has_mulligan_language": True,
            "has_card_role_language": True,
            "default_only_config": False,
        }
    }
    receipt = {
        "source_backed_status": "SOURCE_BACKED_STRONG",
        "first_missing_source_action": "none",
        "default_only_runtime_surfaces": [],
        "surface_status_counts": {},
        "strong_receipt": {
            "source_status": "SOURCE_BACKED_STRONG",
            "first_missing_source_action": "none",
            "strong_blockers": [],
            "no_default_only": True,
        },
    }

    reconciled_operator, reconciled_receipt = reconcile_source_artifacts(
        operator_summary=operator_summary,
        source_pack=source_pack,
        source_quality_receipt=receipt,
        source_to_runtime_explainability={
            "authority": "diagnostic_only",
            "apply_blocking": False,
        },
    )

    assert reconciled_operator["semantic_status"] == "SOURCE_BACKED_PARTIAL"
    assert reconciled_operator["source_backed_status"] == "SOURCE_BACKED_PARTIAL"
    assert reconciled_operator["first_missing_source_action"] == "guide_fulltext_missing"
    assert reconciled_operator["runtime_apply_allowed"] is True
    assert reconciled_operator["source_quality"]["blocking"] is False
    assert reconciled_receipt["source_backed_status"] == "SOURCE_BACKED_PARTIAL"
    assert reconciled_receipt["strong_receipt"]["source_status"] == "SOURCE_BACKED_PARTIAL"
    assert reconciled_receipt["strong_receipt"]["first_missing_source_action"] == "guide_fulltext_missing"
    assert "first_missing_source_action_present" in reconciled_receipt["strong_blockers"]
    assert reconciled_operator["source_closure_contract_proof"]["authority"] == "diagnostic_only"
    assert reconciled_operator["source_closure_contract_proof"]["apply_blocking"] is False
    assert (
        reconciled_operator["source_closure_contract_proof"]["normal_apply_authority"]
        == "reports/operator_summary.json"
    )


def test_reconcile_keeps_default_only_visible_without_blocking_apply():
    operator_summary = {
        "technical_status": "VALID_PACKAGE",
        "semantic_status": "SOURCE_BACKED_STRONG",
        "runtime_apply_allowed": True,
        "default_only_runtime_surfaces": ["cardid_behavior"],
        "no_default_only_runtime_status": "default_only",
        "first_missing_source_action": "none",
    }
    receipt = {
        "source_backed_status": "SOURCE_BACKED_STRONG",
        "first_missing_source_action": "none",
        "default_only_runtime_surfaces": ["cardid_behavior"],
        "surface_status_counts": {"default_only": 1},
        "strong_receipt": {
            "source_status": "SOURCE_BACKED_STRONG",
            "first_missing_source_action": "none",
            "strong_blockers": [],
            "no_default_only": True,
        },
    }

    reconciled_operator, reconciled_receipt = reconcile_source_artifacts(
        operator_summary=operator_summary,
        source_pack=None,
        source_quality_receipt=receipt,
    )

    assert reconciled_operator["semantic_status"] == "SOURCE_BACKED_PARTIAL"
    assert reconciled_operator["runtime_apply_allowed"] is True
    assert reconciled_operator["default_only_runtime_surfaces"] == ["cardid_behavior"]
    assert reconciled_operator["first_missing_source_action"] == (
        "replace_default_only_runtime_surface_with_source_or_policy_claim"
    )
    assert reconciled_receipt["strong_receipt"]["no_default_only"] is False
    assert "default_only_runtime_surfaces" in reconciled_receipt["strong_blockers"]
```

- [ ] **Step 2: Run the new tests and confirm failure**

Run:

```powershell
python -m pytest tests/test_source_artifact_reconciliation.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'hsconfig.source_artifact_reconciliation'`.

- [ ] **Step 3: Add the reconciliation helper**

Create `src/hsconfig/source_artifact_reconciliation.py`:

```python
from __future__ import annotations

from typing import Any, Mapping

from hsconfig.source_closure_proof import build_source_closure_contract_proof
from hsconfig.source_evidence_closure import sync_compact_strong_receipt
from hsconfig.source_status_resolver import resolve_source_status


def reconcile_source_artifacts(
    *,
    operator_summary: dict[str, Any],
    source_pack: Mapping[str, Any] | None,
    source_quality_receipt: dict[str, Any],
    source_to_runtime_explainability: Mapping[str, Any] | None = None,
    matrix_row: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Synchronize source-status diagnostics after package reports exist."""

    resolved = resolve_source_status(
        operator_summary=operator_summary,
        source_pack=source_pack,
        source_quality_receipt=source_quality_receipt,
        matrix_row=matrix_row,
    )
    quality = dict(_mapping(operator_summary.get("source_quality")))
    quality.update(resolved.as_quality_dict())
    operator_summary["source_quality"] = quality
    operator_summary["semantic_status"] = resolved.semantic_status
    operator_summary["source_backed_status"] = resolved.source_backed_status
    operator_summary["first_missing_source_action"] = (
        resolved.first_missing_source_action
    )
    operator_summary["default_only_runtime_surfaces"] = (
        resolved.default_only_runtime_surfaces
    )

    closure = dict(_mapping(operator_summary.get("source_backed_strong_closure")))
    closure.update(
        {
            "diagnostic_only": True,
            "apply_blocking": False,
            "source_backed_status": resolved.source_backed_status,
            "status": "ready" if resolved.strong_ready else "needs_source_closure",
            "strong_ready": resolved.strong_ready,
            "first_missing_source_action": resolved.first_missing_source_action,
            "default_only_runtime_surfaces": resolved.default_only_runtime_surfaces,
            "missing_source_actions": resolved.actions,
            "reasons": resolved.reasons,
        }
    )
    operator_summary["source_backed_strong_closure"] = closure

    source_quality_receipt.update(resolved.as_quality_dict())
    sync_compact_strong_receipt(source_quality_receipt)
    operator_summary["source_closure_contract_proof"] = (
        build_source_closure_contract_proof(
            operator_summary,
            source_to_runtime=source_to_runtime_explainability,
            source_quality_receipt=source_quality_receipt,
        )
    )
    return operator_summary, source_quality_receipt


def _mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}
```

- [ ] **Step 4: Run the task tests**

Run:

```powershell
python -m pytest tests/test_source_artifact_reconciliation.py -q
```

Expected: PASS.

- [ ] **Step 5: Run resolver regression tests**

Run:

```powershell
python -m pytest tests/test_source_status_resolver.py tests/test_source_evidence_closure.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit this task**

```powershell
git add src/hsconfig/source_artifact_reconciliation.py tests/test_source_artifact_reconciliation.py
git commit -m "test: add canonical source artifact reconciliation"
```

---

### Task 2: Use Reconciliation In Configure And Prepare Paths

**Files:**
- Modify: `src/hsconfig/commands/configure.py`
- Modify: `src/hsconfig/package_builder.py`
- Modify: `tests/test_configure_auto_source.py`
- Modify: `tests/test_no_default_only_adversarial_corpus.py`

**Interfaces:**
- Consumes: `reconcile_source_artifacts(...)` from Task 1.
- Produces: configure and direct package/prepare paths both emit synchronized `operator_summary.json`, `source_quality_receipt.json`, and `source_closure_contract_proof`.

- [ ] **Step 1: Add configure-path assertions before touching code**

In `tests/test_configure_auto_source.py`, extend the existing auto-source package test with these assertions after loading `operator` and `source_quality_receipt`:

```python
    assert operator["source_backed_status"] == source_quality_receipt["source_backed_status"]
    assert (
        operator["first_missing_source_action"]
        == source_quality_receipt["first_missing_source_action"]
    )
    assert (
        operator["source_closure_contract_proof"]["first_missing_source_action"]
        == operator["first_missing_source_action"]
    )
    assert (
        operator["source_closure_contract_proof"]["normal_apply_authority"]
        == "reports/operator_summary.json"
    )
    assert operator["source_closure_contract_proof"]["apply_blocking"] is False
```

- [ ] **Step 2: Add prepare/direct package-path assertions**

In `tests/test_no_default_only_adversarial_corpus.py`, extend `_assert_no_default_only_package()` after loading `operator` and `source_quality_receipt`:

```python
    assert operator["source_backed_status"] == source_quality_receipt["source_backed_status"]
    assert (
        operator["first_missing_source_action"]
        == source_quality_receipt["first_missing_source_action"]
    )
    assert (
        operator["source_closure_contract_proof"]["first_missing_source_action"]
        == operator["first_missing_source_action"]
    )
    assert (
        operator["source_closure_contract_proof"]["candidate_registry_url_count"]
        == source_quality_receipt.get("candidate_registry_url_count", 0)
    )
```

- [ ] **Step 3: Run the assertions and confirm the direct path fails first**

Run:

```powershell
python -m pytest tests/test_configure_auto_source.py tests/test_no_default_only_adversarial_corpus.py -q
```

Expected: FAIL only where direct package/prepare output has not been reconciled yet, or where `operator_summary` lacks the synced source status fields.

- [ ] **Step 4: Replace configure inline sync with helper**

In `src/hsconfig/commands/configure.py`, add:

```python
from hsconfig.source_artifact_reconciliation import reconcile_source_artifacts
```

Replace the inline `resolve_source_status(...)`, `source_quality_receipt.update(...)`, `sync_compact_strong_receipt(...)`, and proof rebuild section with:

```python
        operator_summary, source_quality_receipt = reconcile_source_artifacts(
            operator_summary=operator_summary,
            source_pack=source_pack,
            source_quality_receipt=source_quality_receipt,
            source_to_runtime_explainability=source_to_runtime_explainability_report,
        )
```

Keep the existing `write_json(reports_dir / "source_quality_receipt.json", source_quality_receipt)` and final `operator_summary.json` writes.

- [ ] **Step 5: Add helper to package builder path**

In `src/hsconfig/package_builder.py`, add:

```python
from hsconfig.source_artifact_reconciliation import reconcile_source_artifacts
```

After `source_quality_receipt = build_source_quality_receipt(...)` and before writing `source_quality_receipt.json`, call:

```python
    operator_summary, source_quality_receipt = reconcile_source_artifacts(
        operator_summary=operator_summary,
        source_pack=None,
        source_quality_receipt=source_quality_receipt,
        source_to_runtime_explainability=source_to_runtime_explainability_report,
    )
```

Keep:

```python
    write_json(reports_dir / "source_quality_receipt.json", source_quality_receipt)
    operator_summary["source_quality_receipt_path"] = "reports/source_quality_receipt.json"
    write_json(reports_dir / "operator_summary.json", operator_summary)
```

- [ ] **Step 6: Run integration tests**

Run:

```powershell
python -m pytest tests/test_configure_auto_source.py tests/test_no_default_only_adversarial_corpus.py tests/test_configure_online_source_pack.py -q
```

Expected: PASS.

- [ ] **Step 7: Run source-status and no-second-gate tests**

Run:

```powershell
python -m pytest tests/test_source_status_resolver.py tests/test_no_second_gate_contract.py tests/test_output_ownership_manifest.py tests/test_report_ownership.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit this task**

```powershell
git add src/hsconfig/commands/configure.py src/hsconfig/package_builder.py tests/test_configure_auto_source.py tests/test_no_default_only_adversarial_corpus.py
git commit -m "fix: reconcile source status across package paths"
```

---

### Task 3: CardID Baseline-Only Runtime Visibility

**Files:**
- Modify: `src/hsconfig/config_usefulness.py`
- Modify: `tests/test_config_usefulness.py` if it exists
- If `tests/test_config_usefulness.py` does not exist, create it.

**Interfaces:**
- Consumes: existing `build_config_usefulness(...)`.
- Produces: `config_usefulness["surfaces"]["cardid_behavior"]` with `baseline_only`, `first_gap_reason`, `next_source_need`, and `runtime_emitted_card_count`.

- [ ] **Step 1: Add failing CardID baseline-only tests**

Create `tests/test_config_usefulness.py` if it is absent. Add:

```python
from __future__ import annotations

from hsconfig.config_usefulness import build_config_usefulness


def test_cardid_surface_marks_baseline_only_as_visible_default_only():
    result = build_config_usefulness(
        technical_status="VALID_PACKAGE",
        semantic_status="SOURCE_BACKED_PARTIAL",
        config_readiness_summary={
            "runtime_emitted": 2,
            "report_only_supported": 0,
            "cards_needing_runtime_surface": 0,
        },
        card_behavior_plan_report={
            "rows": [
                {
                    "card_id": "EX1_001",
                    "meaningful_runtime_surface": False,
                    "behavior_block": "",
                },
                {
                    "card_id": "EX1_002",
                    "meaningful_runtime_surface": False,
                    "behavior_block": "",
                },
            ]
        },
    )

    cardid = result["surfaces"]["cardid_behavior"]
    assert cardid["status"] == "baseline_only"
    assert cardid["default_only"] is True
    assert cardid["baseline_only"] is True
    assert cardid["baseline_only_card_count"] == 2
    assert cardid["first_gap_reason"] == "cardid_baseline_only"
    assert (
        cardid["next_source_need"]
        == "source_backed_cardid_behavior_or_explicit_suppression"
    )


def test_cardid_surface_rich_when_meaningful_behavior_exists():
    result = build_config_usefulness(
        technical_status="VALID_PACKAGE",
        semantic_status="SOURCE_BACKED_STRONG",
        config_readiness_summary={
            "runtime_emitted": 2,
            "report_only_supported": 0,
            "cards_needing_runtime_surface": 0,
        },
        card_behavior_plan_report={
            "rows": [
                {
                    "card_id": "EX1_001",
                    "meaningful_runtime_surface": True,
                    "behavior_block": "BeforePlayCardBonus",
                },
                {
                    "card_id": "EX1_002",
                    "meaningful_runtime_surface": False,
                    "behavior_block": "",
                },
            ]
        },
    )

    cardid = result["surfaces"]["cardid_behavior"]
    assert cardid["status"] == "rich"
    assert cardid["default_only"] is False
    assert cardid["baseline_only"] is False
    assert cardid["meaningful_cardid_row_count"] == 1
```

- [ ] **Step 2: Run the new tests and confirm failure**

Run:

```powershell
python -m pytest tests/test_config_usefulness.py -q
```

Expected: FAIL because `baseline_only`, `baseline_only_card_count`, `first_gap_reason`, and `next_source_need` are not present or status is still `thin`.

- [ ] **Step 3: Patch `_cardid_surface`**

In `src/hsconfig/config_usefulness.py`, replace `_cardid_surface()` with:

```python
def _cardid_surface(report: dict[str, Any], summary: dict[str, Any]) -> dict[str, Any]:
    rows = _list(report.get("rows"))
    meaningful_rows = [
        row
        for row in rows
        if isinstance(row, dict)
        and row.get("meaningful_runtime_surface") is True
        and bool(row.get("behavior_block"))
    ]
    baseline_only_rows = [
        row
        for row in rows
        if isinstance(row, dict)
        and row not in meaningful_rows
    ]
    cards = sorted({str(row.get("card_id")) for row in meaningful_rows if row.get("card_id")})
    baseline_cards = sorted(
        {str(row.get("card_id")) for row in baseline_only_rows if row.get("card_id")}
    )
    report_only_supported = _int(summary.get("report_only_supported"))
    runtime_emitted = _int(summary.get("runtime_emitted"))
    missing_runtime_surface = _int(summary.get("cards_needing_runtime_surface"))

    if meaningful_rows:
        status = "rich"
        first_gap_reason = "none"
        next_source_need = "none"
    elif report_only_supported > 0:
        status = "report_only"
        first_gap_reason = "cardid_report_only"
        next_source_need = "source_backed_cardid_runtime_lowering"
    elif rows:
        status = "baseline_only"
        first_gap_reason = "cardid_baseline_only"
        next_source_need = "source_backed_cardid_behavior_or_explicit_suppression"
    elif missing_runtime_surface:
        status = "thin"
        first_gap_reason = "needs_runtime_surface"
        next_source_need = "source_backed_cardid_behavior_or_explicit_suppression"
    else:
        status = "not_expected"
        first_gap_reason = "none"
        next_source_need = "none"

    baseline_only = bool(rows) and not meaningful_rows
    return {
        "status": status,
        "default_only": baseline_only or bool(missing_runtime_surface),
        "baseline_only": baseline_only,
        "baseline_only_card_count": len(baseline_cards),
        "meaningful_cardid_row_count": len(meaningful_rows),
        "cards_with_meaningful_cardid_rows": len(cards),
        "runtime_emitted_card_count": runtime_emitted,
        "report_only_supported_count": report_only_supported,
        "first_gap_reason": first_gap_reason,
        "next_source_need": next_source_need,
    }
```

- [ ] **Step 4: Run CardID tests**

Run:

```powershell
python -m pytest tests/test_config_usefulness.py tests/test_compile_cardid.py tests/test_card_behavior_router.py -q
```

Expected: PASS.

- [ ] **Step 5: Run no-default-only corpus tests**

Run:

```powershell
python -m pytest tests/test_no_default_only_adversarial_corpus.py tests/test_strong_evidence_12_deck_matrix.py -q
```

Expected: PASS or FAIL only where an existing test expected CardID baseline-only to remain invisible. If that failure occurs, update the expectation to assert visible `baseline_only` diagnostics while keeping `runtime_apply_allowed is True`.

- [ ] **Step 6: Commit this task**

```powershell
git add src/hsconfig/config_usefulness.py tests/test_config_usefulness.py tests/test_no_default_only_adversarial_corpus.py tests/test_strong_evidence_12_deck_matrix.py
git commit -m "fix: expose cardid baseline-only runtime surfaces"
```

---

### Task 4: Surface Ledger First-Missing Links For CardID Gaps

**Files:**
- Modify: `src/hsconfig/operator_summary.py`
- Modify: `tests/test_operator_summary.py`

**Interfaces:**
- Consumes: CardID fields from Task 3:
  - `status`
  - `default_only`
  - `first_gap_reason`
  - `next_source_need`
- Produces: `operator_summary["surface_status_ledger"]` rows where `cardid_behavior` has an explicit `first_missing_link` and `next_source_action`.

- [ ] **Step 1: Add failing ledger test**

In `tests/test_operator_summary.py`, add:

```python
from hsconfig.operator_summary import _surface_status_ledger


def test_surface_status_ledger_carries_cardid_baseline_missing_link():
    ledger = _surface_status_ledger(
        {
            "surfaces": {
                "cardid_behavior": {
                    "status": "baseline_only",
                    "default_only": True,
                    "baseline_only": True,
                    "first_gap_reason": "cardid_baseline_only",
                    "next_source_need": (
                        "source_backed_cardid_behavior_or_explicit_suppression"
                    ),
                }
            }
        },
        {"card_rows": []},
    )

    assert ledger == [
        {
            "surface": "cardid_behavior",
            "status": "default_only",
            "default_only": True,
            "apply_blocking": False,
            "operator_impact": "diagnostic_only",
            "runtime_permission_impact": "none",
            "first_missing_link": "cardid_baseline_only",
            "next_source_action": (
                "source_backed_cardid_behavior_or_explicit_suppression"
            ),
            "next_report_to_open": "reports/card_behavior_plan_report.json",
        }
    ]
```

- [ ] **Step 2: Run the ledger test and confirm failure**

Run:

```powershell
python -m pytest tests/test_operator_summary.py::test_surface_status_ledger_carries_cardid_baseline_missing_link -q
```

Expected: FAIL if `first_missing_link`, `next_source_action`, or `next_report_to_open` does not match.

- [ ] **Step 3: Patch ledger next-report routing**

In `src/hsconfig/operator_summary.py`, update `_surface_ledger_next_report()` so CardID default-only and baseline-only rows point to `card_behavior_plan_report.json`:

```python
def _surface_ledger_next_report(surface: str, status: str) -> str:
    normalized_surface = str(surface)
    if normalized_surface == "cardid_behavior":
        return "reports/card_behavior_plan_report.json"
    if normalized_surface == "mulligan":
        return "reports/mulligan_plan_report.json"
    if normalized_surface == "combo":
        return "reports/combo_plan_report.json"
    if normalized_surface == "globalvalues":
        return "reports/global_values_key_profile_report.json"
    return "reports/operator_summary.json"
```

If `_surface_ledger_next_report()` already exists, keep its existing non-CardID behavior and add only the CardID branch.

- [ ] **Step 4: Preserve first-gap and next-source fields**

In `_surface_status_ledger()`, keep this field order for each row:

```python
        first_missing_link = row.get("first_gap_reason") or first_risky.get(
            "first_missing_link"
        )
        next_source_action = row.get("next_source_need") or first_risky.get(
            "next_source_action"
        )
```

If later code clears those fields for `default_only`, remove that clearing. Only clear both fields when `status in {"source_backed", "policy_backed", "static_semantics_backed"}`.

- [ ] **Step 5: Run operator-summary tests**

Run:

```powershell
python -m pytest tests/test_operator_summary.py -q
```

Expected: PASS.

- [ ] **Step 6: Run no-default-only and source proof tests**

Run:

```powershell
python -m pytest tests/test_no_default_only_adversarial_corpus.py tests/test_source_evidence_closure.py tests/test_skill_contract_docs.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit this task**

```powershell
git add src/hsconfig/operator_summary.py tests/test_operator_summary.py
git commit -m "fix: expose cardid ledger repair actions"
```

---

### Task 5: General Start-Of-Game Non-Hand Mulligan Canary

**Files:**
- Modify: `tests/test_claim_kind_runtime_contract.py`
- Modify only if test fails for the wrong reason: `src/hsconfig/source_document_model.py`

**Interfaces:**
- Consumes: `surface_gate_decision(claim, "mulligan", context={"card_roles": ...})`.
- Produces: generalized proof that start-of-game non-hand effects cannot lower into `Mulligan.json` without explicit opening-hand evidence.

- [ ] **Step 1: Add failing or passing canary test**

In `tests/test_claim_kind_runtime_contract.py`, add:

```python
from hsconfig.source_document_model import surface_gate_decision


def test_start_of_game_hero_power_effect_does_not_lower_to_mulligan_keep():
    decision = surface_gate_decision(
        {
            "claim_kind": "mulligan_keep",
            "claim_readiness": "guide_backed",
            "cards": ["TEST_HERO_POWER_START_EFFECT"],
            "evidence_text_short": (
                "This card changes the hero power at the start of the game."
            ),
        },
        "mulligan",
        context={
            "card_roles": {
                "TEST_HERO_POWER_START_EFFECT": {
                    "roles": ["start_of_game", "hero_power_transform"]
                }
            }
        },
    )

    assert decision.allowed is False
    assert decision.reason == "start_of_game_effect_does_not_require_opening_hand"


def test_start_of_game_effect_can_lower_to_mulligan_only_with_opening_hand_evidence():
    decision = surface_gate_decision(
        {
            "claim_kind": "mulligan_keep",
            "claim_readiness": "guide_backed",
            "cards": ["TEST_START_EFFECT_WITH_OPENING_HAND_SOURCE"],
            "evidence_text_short": (
                "Always keep this card in the mulligan opening hand."
            ),
        },
        "mulligan",
        context={
            "card_roles": {
                "TEST_START_EFFECT_WITH_OPENING_HAND_SOURCE": {
                    "roles": ["start_of_game", "hero_power_transform"]
                }
            }
        },
    )

    assert decision.allowed is True
    assert decision.reason == "allowed"
```

- [ ] **Step 2: Run the canary**

Run:

```powershell
python -m pytest tests/test_claim_kind_runtime_contract.py::test_start_of_game_hero_power_effect_does_not_lower_to_mulligan_keep tests/test_claim_kind_runtime_contract.py::test_start_of_game_effect_can_lower_to_mulligan_only_with_opening_hand_evidence -q
```

Expected: PASS. If the first test fails, patch `src/hsconfig/source_document_model.py` so `_contains_start_of_game_non_hand_effect()` treats `hero_power_transform` plus `start_of_game` as a non-hand effect unless `has_explicit_opening_hand_mulligan_intent()` returns true.

- [ ] **Step 3: Patch only if the first canary fails**

If needed, in `src/hsconfig/source_document_model.py`, ensure this condition remains active:

```python
        if roles & START_OF_GAME_NON_HAND_EFFECT_ROLES:
            return not has_opening_hand_intent
```

Do not add a Darkbishop-specific branch. The rule must remain generic.

- [ ] **Step 4: Run ShadowPriest E2E**

Run:

```powershell
python -m pytest tests/test_claim_kind_runtime_contract.py tests/test_shadowpriest_e2e.py tests/test_shadowpriest_depth_e2e.py -q
```

Expected: PASS. ShadowPriest must still write Darkbishop effect/CardID behavior and must not put `SW_448` in `Mulligan.json`.

- [ ] **Step 5: Commit this task**

```powershell
git add tests/test_claim_kind_runtime_contract.py src/hsconfig/source_document_model.py
git commit -m "test: guard start-of-game effects from mulligan keeps"
```

---

### Task 6: Full Regression Matrix And Operator Contract Proof

**Files:**
- Modify: none unless a test exposes a real contract mismatch.

**Interfaces:**
- Consumes all tasks above.
- Produces a verified branch with no hidden default-only runtime surfaces and no false `SOURCE_BACKED_STRONG` promotion.

- [ ] **Step 1: Run focused source-contract regression**

Run:

```powershell
python -m pytest tests/test_source_artifact_reconciliation.py tests/test_source_status_resolver.py tests/test_source_evidence_closure.py tests/test_strong_evidence_source_policy.py tests/test_no_second_gate_contract.py -q
```

Expected: PASS.

- [ ] **Step 2: Run no-default-only and CardID regression**

Run:

```powershell
python -m pytest tests/test_config_usefulness.py tests/test_operator_summary.py tests/test_no_default_only_adversarial_corpus.py tests/test_whole_deck_cardid_closure.py tests/test_compile_cardid.py -q
```

Expected: PASS.

- [ ] **Step 3: Run 12-deck and online-source proof**

Run:

```powershell
python -m pytest tests/test_strong_evidence_12_deck_matrix.py tests/test_universal_wild_no_block_matrix.py tests/test_configure_online_source_pack.py tests/test_source_harvester_12_deck_canary.py -q
```

Expected: PASS.

- [ ] **Step 4: Run ShadowPriest canary regression**

Run:

```powershell
python -m pytest tests/test_claim_kind_runtime_contract.py tests/test_shadowpriest_e2e.py tests/test_shadowpriest_depth_e2e.py -q
```

Expected: PASS.

- [ ] **Step 5: Run docs and skill contract regression**

Run:

```powershell
python -m pytest tests/test_skill_contract_docs.py tests/test_operator_docs_contract_policy.py tests/test_output_ownership_manifest.py tests/test_report_ownership.py -q
```

Expected: PASS.

- [ ] **Step 6: Run placeholder scan on touched plan/docs/tests**

Run:

```powershell
$patterns = @(
    ('T' + 'BD'),
    ('TO' + 'DO'),
    ('implement ' + 'later'),
    ('fill in ' + 'details'),
    ('appropriate error ' + 'handling'),
    ('Write tests for ' + 'the above'),
    ('Similar to ' + 'Task')
)
rg -n ($patterns -join '|') docs/superpowers/plans/2026-07-17-hsconfig-source-contract-reconciliation-cardid-baseline.md src/hsconfig tests
```

Expected: no matches introduced by this work.

- [ ] **Step 7: Inspect diff**

Run:

```powershell
git diff -- src/hsconfig/source_artifact_reconciliation.py src/hsconfig/commands/configure.py src/hsconfig/package_builder.py src/hsconfig/config_usefulness.py src/hsconfig/operator_summary.py src/hsconfig/source_document_model.py tests/test_source_artifact_reconciliation.py tests/test_config_usefulness.py tests/test_configure_auto_source.py tests/test_no_default_only_adversarial_corpus.py tests/test_operator_summary.py tests/test_claim_kind_runtime_contract.py
```

Expected:
- No source report becomes an apply gate.
- No valid deck is blocked by source-depth weakness.
- `SOURCE_BACKED_STRONG` is downgraded when missing actions or default-only/baseline-only surfaces are present.
- CardID baseline-only state is visible in summaries and ledger.
- Darkbishop/start-of-game effects remain effect semantics, not default Mulligan keeps.

- [ ] **Step 8: Commit final verification updates**

```powershell
git add src/hsconfig tests docs/superpowers/plans/2026-07-17-hsconfig-source-contract-reconciliation-cardid-baseline.md
git commit -m "test: prove source contract reconciliation and cardid baseline visibility"
```

---

## Self-Review

- Spec coverage: The plan covers shared source-status reconciliation, no hidden default-only/baseline-only CardID output, ledger repair links, start-of-game effect-not-mulligan protection, and 12-deck no-block regression.
- Placeholder scan: The plan contains concrete filenames, function signatures, test code, code snippets, commands, and expected outcomes.
- Type consistency: The central interface is `reconcile_source_artifacts(...) -> tuple[dict[str, Any], dict[str, Any]]`; all integration steps consume that exact function.
- Boundary check: Source reports remain diagnostic-only; `operator_summary.json` remains the only normal apply authority; no task adds another runtime-write gate.

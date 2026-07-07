# HSConfig Source-Depth Strong Promotion Wave Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Promote the next representative HSConfig decks from valid source-informed packages to genuinely source-backed strong packages without widening HSConfig beyond pre-game HearthRanger CustomConfig generation.

**Architecture:** Keep `operator_summary.json` as the single gate. Add clearer card-level source-gap and strong-promotion reports, then promote MechPala, PirateRogue, and BigShaman only when the generated package actually reaches `SOURCE_BACKED_STRONG`. Expand CardID mechanic lowering only for documented VisionAI blocks needed by those decks.

**Tech Stack:** Python 3.11, pytest, existing `hsconfig` package, HearthSim deckstrings, HearthstoneJSON/cardxml metadata, HearthRanger VisionAI JSON surfaces.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig` for `Teufelsboy/HSConfig`.
- Keep HSConfig separate from HSTuner.
- Do not add replay parsing, HDT parsing, winrate validation, candidate promotion, or post-run tuning to this repo.
- Normal runtime output remains limited to `GlobalValues.json`, `Mulligan.json`, per-card `<CARDID>.json`, and `Combo.json` only when a concrete exact sequence exists.
- Do not emit `Presume.json` or `Concede.json` in the normal HSConfig path.
- Preserve exact deck and CardID identity.
- Preserve full `GlobalValues.json` key profiling.
- Every deck card must remain covered in the gameplan contract.
- Strict JSON validation must remain mandatory before runtime apply.
- Row-level provenance for generated config rows must remain visible.
- `operator_summary.json` remains the single operator-facing gate.
- Do not mark a deck fixture `core_source_backed_fixture` unless its generated `operator_summary.json` has `technical_status=VALID_PACKAGE`, `semantic_status=SOURCE_BACKED_STRONG`, `next_action=READY_TO_APPLY_OR_HANDOFF`, no `semantic_blockers`, and no normal-path `Presume.json` or `Concede.json`.

---

## File Structure

- Create `src/hsconfig/source_claim_gap_report.py`: builds a card-level report that explains the first missing link for every non-strong card.
- Create `src/hsconfig/strong_promotion_report.py`: converts `operator_summary.json`, readiness, coverage, and source-depth data into an explicit promotion verdict.
- Modify `src/hsconfig/cli.py`: write `reports/source_claim_gap_report.json` and `reports/strong_promotion_report.json` during `prepare`.
- Modify `src/hsconfig/guide_source_depth.py`: make the report distinguish lowerable strong claims from report-only or low-confidence claims more explicitly.
- Modify `src/hsconfig/card_behavior_surface_router.py`: add only the mechanic lowering needed for promoted decks and only through documented VisionAI behavior blocks.
- Modify `tests/fixtures/source_documents_mechpala_strong.json`: close MechPala source depth with card-specific claims.
- Modify `tests/fixtures/source_documents_piraterogue_strong.json`: close PirateRogue source depth with card-specific claims.
- Modify `tests/fixtures/source_documents_bigshaman_strong.json`: close BigShaman guide claims and any runtime-surface lowering gaps needed for strong status.
- Modify `docs/operator/archetype-fixture-matrix.json`: promote only fixtures that pass the strict strong gate.
- Modify `docs/operator/source-backed-strong-closure.md`: update the blocker snapshot after fresh local prepare runs.
- Modify `README.md`, `.agents/skills/hsconfig/SKILL.md`, and `.agents/skills/hsconfig/references/workflow.md`: document the two new reports without duplicating long prose.
- Modify or create tests under `tests/` alongside the modules they validate.

---

### Task 1: Card-Level Source Gap Report

**Files:**
- Create: `src/hsconfig/source_claim_gap_report.py`
- Create: `tests/test_source_claim_gap_report.py`

**Interfaces:**
- Consumes: `config_readiness_report: dict`, `claim_coverage_report: dict`, `card_behavior_plan: dict`, `mulligan_plan: dict`, `combo_plan: dict`
- Produces: `build_source_claim_gap_report(...) -> dict`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_source_claim_gap_report.py`:

```python
from hsconfig.source_claim_gap_report import build_source_claim_gap_report


def test_report_explains_each_first_missing_link():
    report = build_source_claim_gap_report(
        deck_name="Example",
        config_readiness_report={
            "summary": {
                "total_cards": 3,
                "cards_needing_guide_claims": 1,
                "cards_needing_runtime_surface": 1,
                "cards_needing_combo_sequence": 1,
            },
            "cards": {
                "CARD_A": {
                    "card_id": "CARD_A",
                    "name": "Needs Guide",
                    "readiness_lane": "generic_low_confidence",
                    "first_missing_link": "needs_guide_claim",
                    "runtime_surfaces": [],
                },
                "CARD_B": {
                    "card_id": "CARD_B",
                    "name": "Needs Runtime",
                    "readiness_lane": "report_only_supported",
                    "first_missing_link": "needs_runtime_surface",
                    "runtime_surfaces": ["Mulligan.json"],
                },
                "CARD_C": {
                    "card_id": "CARD_C",
                    "name": "Needs Combo",
                    "readiness_lane": "report_only_supported",
                    "first_missing_link": "needs_combo_sequence",
                    "runtime_surfaces": [],
                },
            },
        },
        claim_coverage_report={
            "cards": {
                "CARD_A": {"coverage_status": "uncovered_low_confidence", "source_claim_ids": []},
                "CARD_B": {"coverage_status": "guide_backed", "source_claim_ids": ["claim_b"]},
                "CARD_C": {"coverage_status": "guide_backed", "source_claim_ids": ["claim_c"]},
            }
        },
        card_behavior_plan={"rows": [], "suppressed": []},
        mulligan_plan={"rules": []},
        combo_plan={"combos": []},
    )

    assert report["deck_name"] == "Example"
    assert report["summary"] == {
        "total_cards": 3,
        "blocked_cards": 3,
        "needs_guide_claim": 1,
        "needs_runtime_surface": 1,
        "needs_combo_sequence": 1,
        "needs_mulligan_claim": 0,
        "needs_condition_lowering": 0,
        "needs_mechanic_lowering": 0,
    }
    assert report["cards"]["CARD_A"]["recommended_source_claim_kind"] == "card_role"
    assert report["cards"]["CARD_B"]["recommended_source_claim_kind"] == "targeting_rule"
    assert report["cards"]["CARD_C"]["recommended_source_claim_kind"] == "combo_sequence"


def test_report_uses_none_when_card_is_ready():
    report = build_source_claim_gap_report(
        deck_name="Example",
        config_readiness_report={
            "summary": {"total_cards": 1},
            "cards": {
                "CARD_READY": {
                    "card_id": "CARD_READY",
                    "name": "Ready",
                    "readiness_lane": "runtime_emitted",
                    "first_missing_link": "none",
                    "runtime_surfaces": ["CARD_READY.json"],
                }
            },
        },
        claim_coverage_report={"cards": {"CARD_READY": {"coverage_status": "guide_backed"}}},
        card_behavior_plan={"rows": [], "suppressed": []},
        mulligan_plan={"rules": []},
        combo_plan={"combos": []},
    )

    assert report["summary"]["blocked_cards"] == 0
    assert report["cards"]["CARD_READY"]["recommended_source_claim_kind"] == "none"
    assert report["cards"]["CARD_READY"]["next_action"] == "card_ready_for_strong_gate"
```

- [ ] **Step 2: Run the focused tests to verify failure**

Run:

```powershell
python -m pytest tests/test_source_claim_gap_report.py -q
```

Expected: failure because `hsconfig.source_claim_gap_report` does not exist.

- [ ] **Step 3: Implement the report builder**

Create `src/hsconfig/source_claim_gap_report.py`:

```python
from __future__ import annotations

from collections import Counter
from typing import Any


RECOMMENDED_CLAIM_KIND_BY_MISSING_LINK = {
    "none": "none",
    "needs_guide_claim": "card_role",
    "needs_runtime_surface": "targeting_rule",
    "needs_mulligan_claim": "mulligan_keep",
    "needs_combo_sequence": "combo_sequence",
    "needs_condition_lowering": "targeting_rule",
    "needs_mechanic_lowering": "mechanic_usage",
}

NEXT_ACTION_BY_MISSING_LINK = {
    "none": "card_ready_for_strong_gate",
    "needs_guide_claim": "add_card_specific_source_claim",
    "needs_runtime_surface": "add_runtime_lowerable_claim_or_router_support",
    "needs_mulligan_claim": "add_mulligan_keep_or_discard_claim",
    "needs_combo_sequence": "add_exact_combo_sequence_claim",
    "needs_condition_lowering": "rewrite_condition_to_supported_visionai_syntax",
    "needs_mechanic_lowering": "add_documented_mechanic_runtime_lowering",
}


def build_source_claim_gap_report(
    *,
    deck_name: str,
    config_readiness_report: dict[str, Any],
    claim_coverage_report: dict[str, Any],
    card_behavior_plan: dict[str, Any],
    mulligan_plan: dict[str, Any],
    combo_plan: dict[str, Any],
) -> dict[str, Any]:
    cards = config_readiness_report.get("cards", {})
    if not isinstance(cards, dict):
        cards = {}
    coverage_cards = claim_coverage_report.get("cards", {})
    if not isinstance(coverage_cards, dict):
        coverage_cards = {}

    counts: Counter[str] = Counter()
    rows: dict[str, dict[str, Any]] = {}
    for card_id, row in sorted(cards.items()):
        if not isinstance(row, dict):
            continue
        missing_link = str(row.get("first_missing_link", "needs_guide_claim"))
        counts[missing_link] += 1
        coverage = coverage_cards.get(card_id, {})
        if not isinstance(coverage, dict):
            coverage = {}
        rows[str(card_id)] = {
            "card_id": str(card_id),
            "name": str(row.get("name", card_id)),
            "readiness_lane": str(row.get("readiness_lane", "")),
            "first_missing_link": missing_link,
            "coverage_status": str(coverage.get("coverage_status", row.get("coverage_status", ""))),
            "source_claim_ids": [str(item) for item in coverage.get("source_claim_ids", row.get("source_claim_ids", []))],
            "runtime_surfaces": [str(item) for item in row.get("runtime_surfaces", [])],
            "recommended_source_claim_kind": RECOMMENDED_CLAIM_KIND_BY_MISSING_LINK.get(missing_link, "card_role"),
            "next_action": NEXT_ACTION_BY_MISSING_LINK.get(missing_link, "inspect_card_gap"),
        }

    blocked_cards = sum(count for key, count in counts.items() if key != "none")
    return {
        "schema_version": 1,
        "deck_name": deck_name,
        "summary": {
            "total_cards": len(rows),
            "blocked_cards": blocked_cards,
            "needs_guide_claim": counts["needs_guide_claim"],
            "needs_runtime_surface": counts["needs_runtime_surface"],
            "needs_combo_sequence": counts["needs_combo_sequence"],
            "needs_mulligan_claim": counts["needs_mulligan_claim"],
            "needs_condition_lowering": counts["needs_condition_lowering"],
            "needs_mechanic_lowering": counts["needs_mechanic_lowering"],
        },
        "cards": rows,
        "inputs": {
            "card_behavior_rows": len(card_behavior_plan.get("rows", [])),
            "mulligan_rules": len(mulligan_plan.get("rules", [])),
            "combo_count": len(combo_plan.get("combos", [])),
        },
    }
```

- [ ] **Step 4: Run the tests to verify pass**

Run:

```powershell
python -m pytest tests/test_source_claim_gap_report.py -q
```

Expected: `2 passed`.

- [ ] **Step 5: Commit**

```powershell
git add src/hsconfig/source_claim_gap_report.py tests/test_source_claim_gap_report.py
git commit -m "feat: add source claim gap report"
```

---

### Task 2: Strong Promotion Report

**Files:**
- Create: `src/hsconfig/strong_promotion_report.py`
- Create: `tests/test_strong_promotion_report.py`

**Interfaces:**
- Consumes: `operator_summary: dict`, `source_claim_gap_report: dict`
- Produces: `build_strong_promotion_report(...) -> dict`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_strong_promotion_report.py`:

```python
from hsconfig.strong_promotion_report import build_strong_promotion_report


def test_report_marks_source_backed_strong_as_promotable():
    report = build_strong_promotion_report(
        deck_name="ShadowPriest",
        fixture_stage="core_source_backed_fixture",
        operator_summary={
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "SOURCE_BACKED_STRONG",
            "next_action": "READY_TO_APPLY_OR_HANDOFF",
            "semantic_blockers": [],
            "guide_strength_summary": {"generic_low_confidence_cards": 0},
        },
        source_claim_gap_report={"summary": {"blocked_cards": 0}, "cards": {}},
    )

    assert report["promotion_ready"] is True
    assert report["verdict"] == "SOURCE_BACKED_STRONG_CONFIRMED"
    assert report["next_action"] == "fixture_can_be_core_source_backed"


def test_report_explains_first_missing_chain_for_non_strong_deck():
    report = build_strong_promotion_report(
        deck_name="MechPala",
        fixture_stage="source_informed_valid_fixture",
        operator_summary={
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "VALID_BUT_NOT_GUIDE_STRONG",
            "next_action": "IMPROVE_GUIDE_SOURCES_BEFORE_STRONG_APPLY",
            "semantic_blockers": [{"reason": "cards_need_guide_claims", "count": 4}],
            "guide_strength_summary": {"generic_low_confidence_cards": 4},
        },
        source_claim_gap_report={
            "summary": {"blocked_cards": 4},
            "cards": {
                "CARD_A": {
                    "first_missing_link": "needs_guide_claim",
                    "recommended_source_claim_kind": "card_role",
                    "next_action": "add_card_specific_source_claim",
                }
            },
        },
    )

    assert report["promotion_ready"] is False
    assert report["verdict"] == "PROMOTION_BLOCKED"
    assert report["first_missing_chain"] == {
        "card_id": "CARD_A",
        "first_missing_link": "needs_guide_claim",
        "recommended_source_claim_kind": "card_role",
        "next_action": "add_card_specific_source_claim",
    }
```

- [ ] **Step 2: Run the focused tests to verify failure**

```powershell
python -m pytest tests/test_strong_promotion_report.py -q
```

Expected: failure because `hsconfig.strong_promotion_report` does not exist.

- [ ] **Step 3: Implement the report builder**

Create `src/hsconfig/strong_promotion_report.py`:

```python
from __future__ import annotations

from typing import Any


def build_strong_promotion_report(
    *,
    deck_name: str,
    fixture_stage: str,
    operator_summary: dict[str, Any],
    source_claim_gap_report: dict[str, Any],
) -> dict[str, Any]:
    promotion_ready = (
        operator_summary.get("technical_status") == "VALID_PACKAGE"
        and operator_summary.get("semantic_status") == "SOURCE_BACKED_STRONG"
        and operator_summary.get("next_action") == "READY_TO_APPLY_OR_HANDOFF"
        and not operator_summary.get("semantic_blockers")
        and int(source_claim_gap_report.get("summary", {}).get("blocked_cards", 0)) == 0
    )
    first_missing_chain = _first_missing_chain(source_claim_gap_report)
    return {
        "schema_version": 1,
        "deck_name": deck_name,
        "fixture_stage": fixture_stage,
        "promotion_ready": promotion_ready,
        "verdict": "SOURCE_BACKED_STRONG_CONFIRMED" if promotion_ready else "PROMOTION_BLOCKED",
        "next_action": "fixture_can_be_core_source_backed" if promotion_ready else "close_first_missing_chain",
        "operator_status": {
            "technical_status": operator_summary.get("technical_status"),
            "semantic_status": operator_summary.get("semantic_status"),
            "operator_next_action": operator_summary.get("next_action"),
        },
        "semantic_blockers": operator_summary.get("semantic_blockers", []),
        "first_missing_chain": first_missing_chain,
    }


def _first_missing_chain(source_claim_gap_report: dict[str, Any]) -> dict[str, str] | None:
    cards = source_claim_gap_report.get("cards", {})
    if not isinstance(cards, dict):
        return None
    for card_id, row in sorted(cards.items()):
        if not isinstance(row, dict):
            continue
        if row.get("first_missing_link") == "none":
            continue
        return {
            "card_id": str(card_id),
            "first_missing_link": str(row.get("first_missing_link", "")),
            "recommended_source_claim_kind": str(row.get("recommended_source_claim_kind", "")),
            "next_action": str(row.get("next_action", "")),
        }
    return None
```

- [ ] **Step 4: Run tests**

```powershell
python -m pytest tests/test_strong_promotion_report.py -q
```

Expected: `2 passed`.

- [ ] **Step 5: Commit**

```powershell
git add src/hsconfig/strong_promotion_report.py tests/test_strong_promotion_report.py
git commit -m "feat: add strong promotion report"
```

---

### Task 3: Wire New Reports Into `prepare`

**Files:**
- Modify: `src/hsconfig/cli.py`
- Modify: `tests/test_prepare_cli.py`

**Interfaces:**
- Consumes: `build_source_claim_gap_report(...)`, `build_strong_promotion_report(...)`
- Produces: `reports/source_claim_gap_report.json`, `reports/strong_promotion_report.json`

- [ ] **Step 1: Write a failing CLI test**

Append to `tests/test_prepare_cli.py`:

```python
def test_prepare_writes_source_gap_and_promotion_reports(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr("hsconfig.cli.fetch_latest_cards", lambda timeout=10.0: [])
    out = tmp_path / "ShadowPriest"
    code = main(
        [
            "prepare",
            "--deck-name",
            "ShadowPriest",
            "--deck-code",
            "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=",
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(out),
            "--source-documents-json",
            "tests/fixtures/source_documents_shadowpriest_strong.json",
            "--json",
        ]
    )

    assert code == 0
    source_gap = json.loads((out / "reports" / "source_claim_gap_report.json").read_text(encoding="utf-8"))
    promotion = json.loads((out / "reports" / "strong_promotion_report.json").read_text(encoding="utf-8"))
    assert source_gap["summary"]["blocked_cards"] == 0
    assert promotion["promotion_ready"] is True
    assert promotion["verdict"] == "SOURCE_BACKED_STRONG_CONFIRMED"
```

- [ ] **Step 2: Run the single test to verify failure**

```powershell
python -m pytest tests/test_prepare_cli.py::test_prepare_writes_source_gap_and_promotion_reports -q
```

Expected: failure because reports are not written.

- [ ] **Step 3: Import and write the new reports in `src/hsconfig/cli.py`**

Add imports near existing report imports:

```python
from hsconfig.source_claim_gap_report import build_source_claim_gap_report
from hsconfig.strong_promotion_report import build_strong_promotion_report
```

After `per_card_config_readiness_report.json` and `operator_summary.json` are built, add:

```python
    source_claim_gap_report = build_source_claim_gap_report(
        deck_name=deck_name,
        config_readiness_report=config_readiness_report,
        claim_coverage_report=guide_claim_bundle.get("claim_coverage_report", {}),
        card_behavior_plan=card_behavior_plan,
        mulligan_plan=mulligan_plan,
        combo_plan=combo_plan,
    )
    strong_promotion_report = build_strong_promotion_report(
        deck_name=deck_name,
        fixture_stage="runtime_prepare",
        operator_summary=operator_summary,
        source_claim_gap_report=source_claim_gap_report,
    )
    write_json(reports_dir / "source_claim_gap_report.json", source_claim_gap_report)
    write_json(reports_dir / "strong_promotion_report.json", strong_promotion_report)
```

Also include report paths in any generated report manifest if `cli.py` has a central list.

- [ ] **Step 4: Run the focused CLI test**

```powershell
python -m pytest tests/test_prepare_cli.py::test_prepare_writes_source_gap_and_promotion_reports -q
```

Expected: `1 passed`.

- [ ] **Step 5: Run adjacent report tests**

```powershell
python -m pytest tests/test_prepare_cli.py tests/test_operator_summary.py tests/test_guide_source_depth.py -q
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit**

```powershell
git add src/hsconfig/cli.py tests/test_prepare_cli.py
git commit -m "feat: write source gap and promotion reports"
```

---

### Task 4: Tighten Guide Source Depth Truthfulness

**Files:**
- Modify: `src/hsconfig/guide_source_depth.py`
- Modify: `tests/test_guide_source_depth.py`

**Interfaces:**
- Consumes: existing `build_guide_source_depth_report(...)`
- Produces: additional `summary` fields: `strong_lowerable_claims`, `blocked_runtime_claims`, `report_only_claims`

- [ ] **Step 1: Add failing tests for report-only versus strong lowerable claims**

Append to `tests/test_guide_source_depth.py`:

```python
def test_guide_source_depth_separates_strong_lowerable_from_report_only():
    report = build_guide_source_depth_report(
        guide_claim_bundle={
            "claims": [
                {
                    "claim_kind": "card_role",
                    "claim_readiness": "guide_backed",
                    "trust_ceiling": "guide",
                    "cards": ["CARD_A"],
                    "source_family": "guide",
                },
                {
                    "claim_kind": "card_role",
                    "claim_readiness": "explicit_low_confidence",
                    "trust_ceiling": "report_only",
                    "cards": ["CARD_B"],
                    "source_family": "guide",
                },
            ],
            "unsupported_claims": [],
            "claim_coverage_report": {"cards": {}},
        },
        config_readiness_report={
            "summary": {"total_cards": 2},
            "cards": {
                "CARD_A": {"readiness_lane": "runtime_emitted", "first_missing_link": "none"},
                "CARD_B": {"readiness_lane": "generic_low_confidence", "first_missing_link": "needs_guide_claim"},
            },
        },
    )

    assert report["summary"]["strong_lowerable_claims"] == 1
    assert report["summary"]["report_only_claims"] == 1
    assert report["summary"]["blocked_runtime_claims"] == 1
    assert report["source_depth_status"] == "needs_more_research"
```

- [ ] **Step 2: Run the focused test to verify failure**

```powershell
python -m pytest tests/test_guide_source_depth.py::test_guide_source_depth_separates_strong_lowerable_from_report_only -q
```

Expected: failure because the new summary keys do not exist.

- [ ] **Step 3: Add explicit summary fields**

In `src/hsconfig/guide_source_depth.py`, compute:

```python
    strong_lowerable_claims = sum(
        1
        for claim in claims
        if claim_can_lower_to_runtime(claim)
        and str(claim.get("claim_readiness", "")).lower()
        in {"guide_backed", "source_backed_static_semantics"}
    )
    blocked_runtime_claims = sum(
        1 for claim in claims if not claim_can_lower_to_runtime(claim)
    )
```

Add to `summary`:

```python
            "strong_lowerable_claims": strong_lowerable_claims,
            "blocked_runtime_claims": blocked_runtime_claims,
```

Keep existing fields for backwards compatibility.

- [ ] **Step 4: Run guide-depth tests**

```powershell
python -m pytest tests/test_guide_source_depth.py -q
```

Expected: all guide-depth tests pass.

- [ ] **Step 5: Commit**

```powershell
git add src/hsconfig/guide_source_depth.py tests/test_guide_source_depth.py
git commit -m "fix: distinguish strong and report-only guide claims"
```

---

### Task 5: Promote MechPala To Source-Backed Strong

**Files:**
- Modify: `tests/fixtures/source_documents_mechpala_strong.json`
- Modify: `docs/operator/archetype-fixture-matrix.json`
- Modify: `docs/operator/source-backed-strong-closure.md`
- Modify: `tests/test_strong_fixture_closure.py` only if assertions need clearer failure output

**Interfaces:**
- Consumes: `reports/source_claim_gap_report.json`, `reports/strong_promotion_report.json`
- Produces: MechPala fixture with `semantic_status=SOURCE_BACKED_STRONG`

- [ ] **Step 1: Generate MechPala blocker evidence**

Run:

```powershell
$env:PYTHONPATH='src'
python -m hsconfig prepare --deck-name "MechPala" --deck-code "AAEBAZ8FAtS9BMekBg6f9QLW/gLX/gKHrgOStQThtQTa0wTZ0AW5/gWf4Qa08Qbi8Qa6lgea/AcAAQPzswbHpAb2swbHpAbu3gbHpAYAAA==" --runtime-root "$env:TEMP\\hsconfig-mechpala-runtime" --out "$env:TEMP\\hsconfig-mechpala-proof" --source-documents-json "tests\\fixtures\\source_documents_mechpala_strong.json" --json
```

Expected before fixture work: `technical_status=VALID_PACKAGE`, `semantic_status=VALID_BUT_NOT_GUIDE_STRONG`, with guide gaps visible in `reports/source_claim_gap_report.json`.

- [ ] **Step 2: Add only source-backed MechPala claims**

Edit `tests/fixtures/source_documents_mechpala_strong.json` so every MechPala deck card has at least one card-specific `guide_backed` or `source_backed_static_semantics` claim. Use these claim kinds only where they match source evidence:

```json
{
  "claim_kind": "mulligan_keep",
  "cards": ["CARD_ID"],
  "selector": "CARD_ID",
  "selector_kind": "card",
  "stance": "keep",
  "evidence_text_short": "Source-backed reason for keeping this card in MechPala.",
  "source_confidence": "high"
}
```

```json
{
  "claim_kind": "card_role",
  "cards": ["CARD_ID"],
  "stance": "mech_board_pressure",
  "evidence_text_short": "Source-backed reason for the card's MechPala role.",
  "source_confidence": "high",
  "runtime_block": "BeforePlayCardBonus",
  "runtime_value": "8",
  "condition": "*"
}
```

Do not invent sources. If a card cannot be source-backed, leave MechPala unpromoted and record the exact card in `docs/operator/source-backed-strong-closure.md`.

- [ ] **Step 3: Run the MechPala proof**

Run the command from Step 1 again.

Expected after fixture work:

```text
technical_status=VALID_PACKAGE
semantic_status=SOURCE_BACKED_STRONG
next_action=READY_TO_APPLY_OR_HANDOFF
```

Also verify:

```powershell
Get-Content "$env:TEMP\\hsconfig-mechpala-proof\\reports\\operator_summary.json"
Get-Content "$env:TEMP\\hsconfig-mechpala-proof\\reports\\strong_promotion_report.json"
```

Expected: `semantic_blockers` is `[]`, `promotion_ready` is `true`.

- [ ] **Step 4: Promote the matrix row only after proof**

In `docs/operator/archetype-fixture-matrix.json`, change only MechPala:

```json
"fixture_stage": "core_source_backed_fixture"
```

- [ ] **Step 5: Run strict fixture tests**

```powershell
python -m pytest tests/test_strong_fixture_closure.py tests/test_archetype_fixture_matrix.py tests/test_archetype_fixture_e2e.py -q
```

Expected: MechPala is no longer skipped in `test_strong_fixture_closure.py`, and all selected tests pass.

- [ ] **Step 6: Update closure docs**

Update `docs/operator/source-backed-strong-closure.md`:

- Move MechPala to already strong.
- Set MechPala blocker counts to zero in the snapshot.
- Keep other decks unchanged.

- [ ] **Step 7: Commit**

```powershell
git add tests/fixtures/source_documents_mechpala_strong.json docs/operator/archetype-fixture-matrix.json docs/operator/source-backed-strong-closure.md tests/test_strong_fixture_closure.py
git commit -m "test: promote MechPala source-backed fixture"
```

---

### Task 6: Promote PirateRogue To Source-Backed Strong

**Files:**
- Modify: `tests/fixtures/source_documents_piraterogue_strong.json`
- Modify: `docs/operator/archetype-fixture-matrix.json`
- Modify: `docs/operator/source-backed-strong-closure.md`

**Interfaces:**
- Consumes: source gap and promotion reports from Tasks 1-3
- Produces: PirateRogue fixture with `semantic_status=SOURCE_BACKED_STRONG`

- [ ] **Step 1: Generate PirateRogue blocker evidence**

```powershell
$env:PYTHONPATH='src'
python -m hsconfig prepare --deck-name "PirateRogue" --deck-code "AAEBAaIHApG8AuXRAg6MAtQF+w/psAPz3QOvoASKyQSa2wTXowW/9wXWngb8pQb8qAatxQYAAA==" --runtime-root "$env:TEMP\\hsconfig-piraterogue-runtime" --out "$env:TEMP\\hsconfig-piraterogue-proof" --source-documents-json "tests\\fixtures\\source_documents_piraterogue_strong.json" --json
```

Expected before fixture work: guide gaps are visible and runtime-surface gaps are zero or already explainable.

- [ ] **Step 2: Add PirateRogue card-specific claims**

Edit `tests/fixtures/source_documents_piraterogue_strong.json` so the remaining cards have source-backed claims. Use PirateRogue claim shapes matching the card role:

```json
{
  "claim_kind": "gameplan_posture",
  "scope": "deck",
  "stance": "weapon_pressure",
  "evidence_text_short": "Source-backed PirateRogue posture: early pressure and weapon or pirate tempo.",
  "source_confidence": "high"
}
```

```json
{
  "claim_kind": "mechanic_usage",
  "cards": ["CARD_ID"],
  "mechanic": "weapon",
  "stance": "weapon_pressure",
  "evidence_text_short": "Source-backed weapon-pressure role for this PirateRogue card.",
  "source_confidence": "high",
  "runtime_block": "BeforePhysicalAttackBonus",
  "runtime_value": "8",
  "condition": "*"
}
```

Use `mulligan_keep`, `mulligan_discard`, or `card_role` claims for non-weapon cards where source evidence supports those claims.

- [ ] **Step 3: Run the PirateRogue proof**

Run the command from Step 1 again.

Expected:

```text
technical_status=VALID_PACKAGE
semantic_status=SOURCE_BACKED_STRONG
next_action=READY_TO_APPLY_OR_HANDOFF
```

- [ ] **Step 4: Promote matrix row only after proof**

Change PirateRogue `fixture_stage` in `docs/operator/archetype-fixture-matrix.json` to:

```json
"fixture_stage": "core_source_backed_fixture"
```

- [ ] **Step 5: Run strict fixture tests**

```powershell
python -m pytest tests/test_strong_fixture_closure.py tests/test_archetype_fixture_matrix.py tests/test_archetype_fixture_e2e.py -q
```

Expected: PirateRogue is no longer skipped in strict closure tests.

- [ ] **Step 6: Update closure docs**

Update `docs/operator/source-backed-strong-closure.md` so PirateRogue is listed as already strong with zero blocker counts.

- [ ] **Step 7: Commit**

```powershell
git add tests/fixtures/source_documents_piraterogue_strong.json docs/operator/archetype-fixture-matrix.json docs/operator/source-backed-strong-closure.md
git commit -m "test: promote PirateRogue source-backed fixture"
```

---

### Task 7: BigShaman Recruit/Deathrattle Runtime-Lowering Closure

**Files:**
- Modify: `src/hsconfig/card_behavior_surface_router.py` only if BigShaman proof shows missing runtime-surface lowering after source claims are complete.
- Modify: `tests/test_card_behavior_router.py`
- Modify: `tests/fixtures/source_documents_bigshaman_strong.json`
- Modify: `docs/operator/archetype-fixture-matrix.json`
- Modify: `docs/operator/source-backed-strong-closure.md`

**Interfaces:**
- Consumes: `mechanic_usage` claims with `mechanic` values `recruit` or `deathrattle`
- Produces: runtime rows using documented blocks: `BeforePlayCardBonus` or `OnBoardBonus`

- [ ] **Step 1: Add failing router tests for explicit BigShaman mechanics**

Append to `tests/test_card_behavior_router.py`:

```python
def test_recruit_claim_can_lower_to_before_play_when_explicit_block_is_supported():
    result = route_card_behavior_surfaces(
        [
            {
                "claim_id": "claim_recruit",
                "claim_kind": "mechanic_usage",
                "claim_readiness": "guide_backed",
                "trust_ceiling": "guide",
                "cards": ["CARD_RECRUIT"],
                "mechanic": "recruit",
                "runtime_block": "BeforePlayCardBonus",
                "runtime_value": "9",
                "condition": "*",
                "source_claim_ids": ["claim_recruit"],
            }
        ]
    )

    assert result["suppressed"] == []
    assert result["rows"][0]["card_id"] == "CARD_RECRUIT"
    assert result["rows"][0]["behavior_block"] == "BeforePlayCardBonus"
    assert result["rows"][0]["meaningful_runtime_surface"] is True


def test_deathrattle_claim_can_lower_to_on_board_when_explicit_block_is_supported():
    result = route_card_behavior_surfaces(
        [
            {
                "claim_id": "claim_deathrattle",
                "claim_kind": "mechanic_usage",
                "claim_readiness": "guide_backed",
                "trust_ceiling": "guide",
                "cards": ["CARD_DEATHRATTLE"],
                "mechanic": "deathrattle",
                "runtime_block": "OnBoardBonus",
                "runtime_value": "7",
                "condition": "*",
                "source_claim_ids": ["claim_deathrattle"],
            }
        ]
    )

    assert result["suppressed"] == []
    assert result["rows"][0]["card_id"] == "CARD_DEATHRATTLE"
    assert result["rows"][0]["behavior_block"] == "OnBoardBonus"
```

- [ ] **Step 2: Run focused router tests**

```powershell
python -m pytest tests/test_card_behavior_router.py::test_recruit_claim_can_lower_to_before_play_when_explicit_block_is_supported tests/test_card_behavior_router.py::test_deathrattle_claim_can_lower_to_on_board_when_explicit_block_is_supported -q
```

Expected: If current router already supports these paths, tests pass. If they fail, implement Step 3.

- [ ] **Step 3: Add only missing explicit mechanic support**

If the tests fail because explicit mechanic blocks are not allowed, update `EXPLICIT_MECHANIC_RUNTIME_BLOCKS` in `src/hsconfig/card_behavior_surface_router.py`:

```python
EXPLICIT_MECHANIC_RUNTIME_BLOCKS = {
    "discard": {"BeforePlayCardBonus"},
    "recruit": {"BeforePlayCardBonus", "OnBoardBonus"},
    "deathrattle": {"BeforePlayCardBonus", "OnBoardBonus"},
    "treant": {"BeforePlayCardBonus", "OnBoardBonus"},
    "hero_attack": {"BeforePhysicalAttackBonus"},
}
```

Do not add undocumented blocks.

- [ ] **Step 4: Run BigShaman proof**

```powershell
$env:PYTHONPATH='src'
python -m hsconfig prepare --deck-name "BigShaman" --deck-code "AAEBAaoIBpQD5LcDv84E9qMGgbgGmvYGDM4P0hP2vQKPlAPW9QO8tgT08gXqmAbGpgakpwb44gas/QYAAA==" --runtime-root "$env:TEMP\\hsconfig-bigshaman-runtime" --out "$env:TEMP\\hsconfig-bigshaman-proof" --source-documents-json "tests\\fixtures\\source_documents_bigshaman_strong.json" --json
```

Use `reports/source_claim_gap_report.json` to identify remaining gaps.

- [ ] **Step 5: Add BigShaman source-backed claims**

Edit `tests/fixtures/source_documents_bigshaman_strong.json` with card-specific claims. For big/recruit/deathrattle cards, use:

```json
{
  "claim_kind": "mechanic_usage",
  "cards": ["CARD_ID"],
  "mechanic": "recruit",
  "stance": "cheat_big_minion",
  "evidence_text_short": "Source-backed BigShaman recruit or cheat role for this card.",
  "source_confidence": "high",
  "runtime_block": "BeforePlayCardBonus",
  "runtime_value": "9",
  "condition": "*"
}
```

```json
{
  "claim_kind": "mechanic_usage",
  "cards": ["CARD_ID"],
  "mechanic": "deathrattle",
  "stance": "preserve_deathrattle_body",
  "evidence_text_short": "Source-backed BigShaman deathrattle role for this card.",
  "source_confidence": "high",
  "runtime_block": "OnBoardBonus",
  "runtime_value": "7",
  "condition": "*"
}
```

- [ ] **Step 6: Promote only after strong proof**

Run the BigShaman proof again.

Expected:

```text
technical_status=VALID_PACKAGE
semantic_status=SOURCE_BACKED_STRONG
next_action=READY_TO_APPLY_OR_HANDOFF
```

If BigShaman still has unclosed gaps, do not promote the matrix row. Commit only the report/router improvements and document the remaining exact cards.

- [ ] **Step 7: Run tests**

```powershell
python -m pytest tests/test_card_behavior_router.py tests/test_strong_fixture_closure.py tests/test_archetype_fixture_e2e.py -q
```

Expected: all selected tests pass.

- [ ] **Step 8: Commit**

```powershell
git add src/hsconfig/card_behavior_surface_router.py tests/test_card_behavior_router.py tests/fixtures/source_documents_bigshaman_strong.json docs/operator/archetype-fixture-matrix.json docs/operator/source-backed-strong-closure.md
git commit -m "test: promote BigShaman source-backed fixture"
```

If BigShaman is not promoted, use:

```powershell
git add src/hsconfig/card_behavior_surface_router.py tests/test_card_behavior_router.py tests/fixtures/source_documents_bigshaman_strong.json docs/operator/source-backed-strong-closure.md
git commit -m "feat: improve BigShaman source-depth diagnostics"
```

---

### Task 8: Operator Documentation And Skill Sync

**Files:**
- Modify: `README.md`
- Modify: `docs/operator/guide-research-policy.md`
- Modify: `docs/operator/source-backed-strong-closure.md`
- Modify: `.agents/skills/hsconfig/SKILL.md`
- Modify: `.agents/skills/hsconfig/references/workflow.md`
- Run: `scripts/sync_installed_skill.py`

**Interfaces:**
- Consumes: new reports from Tasks 1-3
- Produces: updated operator path and installed skill copy

- [ ] **Step 1: Update README key reports**

In `README.md`, add these two bullets under `## Key Reports`:

```markdown
- `reports/source_claim_gap_report.json`
- `reports/strong_promotion_report.json`
```

Add one short sentence after the list:

```markdown
Use `source_claim_gap_report.json` and `strong_promotion_report.json` to see the first concrete source or lowering link that prevents a valid package from becoming `SOURCE_BACKED_STRONG`.
```

- [ ] **Step 2: Update skill workflow reference**

In `.agents/skills/hsconfig/references/workflow.md`, add the two reports to the important outputs list and add:

```markdown
For source-informed packages, open `source_claim_gap_report.json` first to see the card-level missing link, then open `strong_promotion_report.json` for the promotion verdict.
```

- [ ] **Step 3: Update installed skill source**

Run:

```powershell
python scripts\sync_installed_skill.py
python scripts\sync_installed_skill.py --check
```

Expected:

```text
HSConfig skill is in sync: C:\Users\darbo\.codex\skills\hsconfig
```

- [ ] **Step 4: Run docs and skill tests**

```powershell
python -m pytest tests/test_skill_files.py tests/test_skill_sync.py -q
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit**

```powershell
git add README.md docs/operator/guide-research-policy.md docs/operator/source-backed-strong-closure.md .agents/skills/hsconfig/SKILL.md .agents/skills/hsconfig/references/workflow.md C:\Users\darbo\.codex\skills\hsconfig
git commit -m "docs: document strong promotion reports"
```

If Git refuses to stage the installed skill path because it is outside the repository, stage only repo files and confirm `scripts\sync_installed_skill.py --check` passed.

---

### Task 9: Final Verification And Push

**Files:**
- No planned source edits.
- Verify full repository state.

**Interfaces:**
- Consumes: all previous task commits
- Produces: clean `main` pushed to `origin/main`

- [ ] **Step 1: Run targeted test matrix**

```powershell
python -m pytest tests/test_source_claim_gap_report.py tests/test_strong_promotion_report.py tests/test_guide_source_depth.py tests/test_prepare_cli.py tests/test_card_behavior_router.py tests/test_strong_fixture_closure.py tests/test_archetype_fixture_matrix.py tests/test_archetype_fixture_e2e.py tests/test_skill_files.py tests/test_skill_sync.py -q
```

Expected: all selected tests pass; any skipped fixture must be a deck still marked `source_informed_valid_fixture`.

- [ ] **Step 2: Run full suite**

```powershell
python -m pytest -q
```

Expected: full test suite passes.

- [ ] **Step 3: Run skill sync check**

```powershell
python scripts\sync_installed_skill.py --check
```

Expected:

```text
HSConfig skill is in sync: C:\Users\darbo\.codex\skills\hsconfig
```

- [ ] **Step 4: Check Git state**

```powershell
git status --short --branch
git log -5 --oneline --decorate
```

Expected: branch is `main`, local branch is ahead of or equal to `origin/main`, and only intentional files are modified before the final commit.

- [ ] **Step 5: Commit any remaining documentation snapshot**

If `git status --short` shows only intentional documentation/report changes:

```powershell
git add README.md docs/operator docs/superpowers/plans .agents/skills/hsconfig tests src
git commit -m "chore: finalize source-depth strong promotion wave"
```

If there are no changes, skip this commit.

- [ ] **Step 6: Push**

```powershell
git push origin main
```

Expected: push succeeds and `main` is up to date on GitHub.

---

## Self-Review Checklist

- Spec coverage: This plan implements the recommended Option A by adding card-level gap reporting, promotion reporting, targeted MechPala/PirateRogue/BigShaman strong promotion, narrow mechanic lowering, docs, tests, and push.
- Runtime boundary: No task adds replay parsing, HDT parsing, winrate analysis, HSTuner candidate promotion, `Presume.json`, or `Concede.json` to the normal path.
- Strong honesty: Matrix promotion is explicitly blocked unless the generated `operator_summary.json` reaches `SOURCE_BACKED_STRONG`.
- Type consistency: New public functions are `build_source_claim_gap_report(...)` and `build_strong_promotion_report(...)`; all CLI and test references use those exact names.
- Testability: Every task has a focused pytest command and expected result.
- Repository hygiene: Final task requires full pytest, skill sync, git status, and push.

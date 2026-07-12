# HSConfig Source Contract Audit Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a source-contract audit report that explains, for every source claim and every card, why HSConfig did or did not lower that evidence into Mulligan, GlobalValues, CardID, or Combo runtime config.

**Architecture:** Reuse the existing `source_document_model.surface_gate_decision()` as the only runtime-lowering authority. The new audit is a read-only explanation layer: it consumes already-built claims, plans, readiness reports, and suppression reports, then writes `reports/source_contract_audit.json` and `reports/source_contract_audit.md`. It must not create a second gate and must not widen runtime writes.

**Tech Stack:** Python stdlib, existing HSConfig JSON report pipeline, pytest, existing `hsconfig.io.write_json`.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig`.
- Do not introduce a new runtime-lowering policy.
- Do not make weak guide text, `generic_low_confidence`, `explicit_low_confidence`, `contract_gap`, or `report_only` claims runtime-writable.
- Do not turn Start of Game, deckbuilding, deck-state, or hero-power-transform enablers into automatic Mulligan keeps.
- Keep `operator_summary.json` as the first report and normal operator gate.
- Keep valid deck packages non-blocking: `VALID_PACKAGE` and `load_safe_apply` remain separated from source-strength labels.
- No new dependencies.
- Preserve existing runtime package layout and existing report names.
- Do not remove or rewrite older reports; add this report as a compact cross-reference layer.

---

## File Structure

- Create: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\source_contract_audit.py`
  - Owns the new read-only audit builder and Markdown renderer.
  - Consumes existing artifacts; does not mutate package state.
- Create: `C:\Users\darbo\Documents\HSConfig\tests\test_source_contract_audit.py`
  - Unit tests for claim lanes, card closure rows, Start of Game suppression visibility, and Markdown rendering.
- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\package_builder.py`
  - Calls the audit builder after all source/planning reports exist.
  - Writes `source_contract_audit.json` and `source_contract_audit.md`.
  - Passes the compact audit summary into `build_operator_summary()`.
- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\operator_summary.py`
  - Accepts optional `source_contract_audit_report`.
  - Adds compact `source_contract_audit_summary` without affecting apply gates.
- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\report_ownership.py`
  - Adds the new report as an explanation report after `operator_summary.json`.
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_report_ownership.py`
  - Verifies report ownership and open order.
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_operator_summary.py`
  - Verifies the new summary is diagnostic only.
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_shadowpriest_e2e.py`
  - Verifies Darkbishop effect semantics stay visible while Mulligan keep stays suppressed.
- Modify: `C:\Users\darbo\Documents\HSConfig\docs\operator\README.md`
  - Adds the new report to the normal operator reading path.
- Modify: `C:\Users\darbo\Documents\HSConfig\.agents\skills\hsconfig\SKILL.md`
  - Adds the report to the skill workflow.
- Modify: `C:\Users\darbo\.codex\skills\hsconfig\SKILL.md`
  - Syncs the installed skill so future Codex sessions use the same workflow.

---

### Task 1: Build The Source Contract Audit Module

**Files:**
- Create: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\source_contract_audit.py`
- Create: `C:\Users\darbo\Documents\HSConfig\tests\test_source_contract_audit.py`

**Interfaces:**
- Consumes:
  - `surface_gate_decision(claim: Mapping[str, Any], surface: str, context: Mapping[str, Any] | None) -> SurfaceGateDecision`
  - `config_readiness_report["cards"]`
  - `guide_claim_bundle["claims"]`
  - plan reports: `mulligan_plan`, `card_behavior_plan`, `combo_plan`, `global_values_authority_matrix`
- Produces:
  - `build_source_contract_audit(...) -> dict[str, Any]`
  - `render_source_contract_audit_markdown(report: dict[str, Any]) -> str`

- [ ] **Step 1: Write failing unit tests**

Add this file:

```python
# C:\Users\darbo\Documents\HSConfig\tests\test_source_contract_audit.py
from __future__ import annotations

from hsconfig.source_contract_audit import (
    build_source_contract_audit,
    render_source_contract_audit_markdown,
)


def test_source_contract_audit_explains_surface_gate_lanes():
    report = build_source_contract_audit(
        deck_name="FixtureDeck",
        deck_identity={
            "deck_name": "FixtureDeck",
            "cards": [
                {"card_id": "CARD_KEEP", "name": "Keep Card", "count": 2},
                {"card_id": "CARD_NUM", "name": "Numeric Card", "count": 1},
            ],
        },
        guide_claim_bundle={
            "claims": [
                {
                    "claim_id": "keep_claim",
                    "claim_kind": "mulligan_keep",
                    "claim_readiness": "guide_backed",
                    "trust_ceiling": "runtime_candidate",
                    "cards": ["CARD_KEEP"],
                    "source_title": "Fixture Guide",
                    "evidence_text_short": "Keep CARD_KEEP.",
                },
                {
                    "claim_id": "numeric_claim",
                    "claim_kind": "globalvalue_numeric_tuning",
                    "claim_readiness": "guide_backed",
                    "trust_ceiling": "runtime_candidate",
                    "cards": ["CARD_NUM"],
                    "source_title": "Fixture Guide",
                    "evidence_text_short": "Tune LowHpBoardValuePenalty later.",
                },
            ]
        },
        mulligan_plan={"rules": [{"card": "CARD_KEEP", "action": "hold"}], "suppressed_rules": []},
        card_behavior_plan={"rows": [], "suppressed": []},
        combo_plan={"combos": [], "suppressed": []},
        global_values_authority_matrix={
            "allowed_step1_overlays": [],
            "blocked_until_runtime_evidence": [
                {"key": "LowHpBoardValuePenalty", "claim_id": "numeric_claim"}
            ],
        },
        config_readiness_report={
            "cards": {
                "CARD_KEEP": {
                    "name": "Keep Card",
                    "roles": ["mulligan_anchor"],
                    "runtime_surfaces": ["Mulligan.json"],
                    "readiness_lane": "mulligan_only",
                    "first_missing_link": "needs_runtime_surface",
                },
                "CARD_NUM": {
                    "name": "Numeric Card",
                    "roles": [],
                    "runtime_surfaces": [],
                    "readiness_lane": "report_only_supported",
                    "first_missing_link": "none",
                },
            }
        },
    )

    assert report["schema_version"] == 1
    assert report["summary"]["claims_total"] == 2
    assert report["summary"]["runtime_lowered_claims"] == 1
    assert report["summary"]["runtime_evidence_required_claims"] == 1
    assert report["claim_rows"]["keep_claim"]["lane"] == "runtime_lowered"
    assert report["claim_rows"]["keep_claim"]["surfaces"]["mulligan"]["allowed"] is True
    assert report["claim_rows"]["numeric_claim"]["lane"] == "runtime_evidence_required"
    assert report["claim_rows"]["numeric_claim"]["surfaces"]["globalvalues"]["reason"] == (
        "requires_runtime_evidence"
    )
    assert report["card_rows"]["CARD_KEEP"]["first_missing_link"] == "needs_runtime_surface"
    assert report["card_rows"]["CARD_KEEP"]["claim_lanes"]["runtime_lowered"] == 1


def test_source_contract_audit_preserves_start_of_game_effect_without_mulligan_keep():
    report = build_source_contract_audit(
        deck_name="ShadowPriest",
        deck_identity={
            "deck_name": "ShadowPriest",
            "cards": [{"card_id": "SW_448", "name": "Darkbishop Benedictus", "count": 1}],
        },
        guide_claim_bundle={
            "claims": [
                {
                    "claim_id": "darkbishop_effect",
                    "claim_kind": "hero_power_transform",
                    "claim_readiness": "source_backed_static_semantics",
                    "trust_ceiling": "runtime_candidate",
                    "cards": ["SW_448"],
                    "source_title": "Hearthstone card data",
                    "evidence_text_short": "Start of Game hero power transform.",
                },
                {
                    "claim_id": "bad_keep",
                    "claim_kind": "mulligan_keep",
                    "claim_readiness": "guide_backed",
                    "trust_ceiling": "runtime_candidate",
                    "cards": ["SW_448"],
                    "source_title": "Bad fixture",
                    "evidence_text_short": "Keep because the effect matters.",
                },
            ]
        },
        mulligan_plan={
            "rules": [],
            "suppressed_rules": [
                {
                    "claim_id": "bad_keep",
                    "card": "SW_448",
                    "reason": "start_of_game_effect_does_not_require_opening_hand",
                }
            ],
        },
        card_behavior_plan={
            "rows": [
                {
                    "claim_id": "darkbishop_effect",
                    "card_id": "SW_448",
                    "surface_family": "CARDID.json",
                    "meaningful_runtime_surface": True,
                    "behavior_block": {"BeforeUseHeroPowerBonus": {"values": []}},
                }
            ],
            "suppressed": [],
        },
        combo_plan={"combos": [], "suppressed": []},
        global_values_authority_matrix={"allowed_step1_overlays": [], "blocked_until_runtime_evidence": []},
        config_readiness_report={
            "cards": {
                "SW_448": {
                    "name": "Darkbishop Benedictus",
                    "roles": ["start_of_game", "hero_power_transform"],
                    "runtime_surfaces": ["SW_448.json"],
                    "readiness_lane": "runtime_emitted",
                    "first_missing_link": "none",
                }
            }
        },
    )

    assert report["claim_rows"]["darkbishop_effect"]["lane"] == "runtime_lowered"
    assert report["claim_rows"]["darkbishop_effect"]["surfaces"]["cardid"]["allowed"] is True
    assert report["claim_rows"]["bad_keep"]["lane"] == "suppressed_with_reason"
    assert report["claim_rows"]["bad_keep"]["first_reason"] == (
        "start_of_game_effect_does_not_require_opening_hand"
    )
    assert report["card_rows"]["SW_448"]["claim_lanes"]["runtime_lowered"] == 1
    assert report["card_rows"]["SW_448"]["claim_lanes"]["suppressed_with_reason"] == 1


def test_source_contract_audit_markdown_is_compact_and_operator_readable():
    report = {
        "deck_name": "FixtureDeck",
        "summary": {
            "claims_total": 2,
            "runtime_lowered_claims": 1,
            "suppressed_claims": 1,
            "runtime_evidence_required_claims": 0,
            "report_only_claims": 0,
            "cards_total": 1,
            "cards_with_missing_links": 1,
        },
        "card_rows": {
            "CARD_001": {
                "name": "Fixture Card",
                "readiness_lane": "report_only_supported",
                "first_missing_link": "needs_runtime_surface",
                "runtime_surfaces": [],
                "claim_lanes": {"suppressed_with_reason": 1},
            }
        },
    }

    markdown = render_source_contract_audit_markdown(report)

    assert "# Source Contract Audit: FixtureDeck" in markdown
    assert "| Claims total | 2 |" in markdown
    assert "| CARD_001 | Fixture Card | report_only_supported | needs_runtime_surface |" in markdown
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
$env:PYTHONPATH='src'
python -m pytest tests/test_source_contract_audit.py -q
```

Expected: fail with `ModuleNotFoundError: No module named 'hsconfig.source_contract_audit'`.

- [ ] **Step 3: Implement the audit module**

Create:

```python
# C:\Users\darbo\Documents\HSConfig\src\hsconfig\source_contract_audit.py
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Mapping

from hsconfig.source_document_model import normalized_claim_kind, surface_gate_decision


SURFACES = ("mulligan", "globalvalues", "combo", "cardid")


def build_source_contract_audit(
    *,
    deck_name: str,
    deck_identity: dict[str, Any],
    guide_claim_bundle: dict[str, Any],
    mulligan_plan: dict[str, Any],
    card_behavior_plan: dict[str, Any],
    combo_plan: dict[str, Any],
    global_values_authority_matrix: dict[str, Any],
    config_readiness_report: dict[str, Any],
) -> dict[str, Any]:
    card_roles = _card_roles(config_readiness_report)
    emitted_claim_ids = _emitted_claim_ids(
        mulligan_plan=mulligan_plan,
        card_behavior_plan=card_behavior_plan,
        combo_plan=combo_plan,
        global_values_authority_matrix=global_values_authority_matrix,
    )
    suppressed_reasons = _suppressed_reasons(
        mulligan_plan=mulligan_plan,
        card_behavior_plan=card_behavior_plan,
        combo_plan=combo_plan,
    )
    runtime_evidence_claim_ids = _runtime_evidence_claim_ids(global_values_authority_matrix)

    claim_rows: dict[str, dict[str, Any]] = {}
    card_claim_lanes: dict[str, Counter[str]] = defaultdict(Counter)
    lane_counter: Counter[str] = Counter()

    for index, claim in enumerate(guide_claim_bundle.get("claims", []), start=1):
        if not isinstance(claim, Mapping):
            continue
        claim_id = str(claim.get("claim_id") or f"claim_{index}")
        claim_kind = normalized_claim_kind(claim)
        surfaces = {
            surface: _decision_to_dict(
                surface_gate_decision(claim, surface, {"card_roles": card_roles})
            )
            for surface in SURFACES
        }
        lane, first_reason = _claim_lane(
            claim_id=claim_id,
            surfaces=surfaces,
            emitted_claim_ids=emitted_claim_ids,
            suppressed_reasons=suppressed_reasons,
            runtime_evidence_claim_ids=runtime_evidence_claim_ids,
        )
        lane_counter[lane] += 1
        cards = _claim_cards(claim)
        for card_id in cards:
            card_claim_lanes[card_id][lane] += 1
        claim_rows[claim_id] = {
            "claim_id": claim_id,
            "claim_kind": claim_kind,
            "claim_readiness": str(claim.get("claim_readiness", "")),
            "trust_ceiling": str(claim.get("trust_ceiling", "")),
            "cards": cards,
            "source_title": str(claim.get("source_title", "")),
            "evidence_text_short": str(claim.get("evidence_text_short", claim.get("claim", ""))),
            "lane": lane,
            "first_reason": first_reason,
            "surfaces": surfaces,
        }

    card_rows = _card_rows(config_readiness_report, card_claim_lanes)
    cards_with_missing_links = sum(
        1 for row in card_rows.values() if row.get("first_missing_link") not in {"", "none"}
    )

    return {
        "schema_version": 1,
        "deck_name": deck_name,
        "deck_slug": str(deck_identity.get("deck_slug", "")),
        "summary": {
            "claims_total": len(claim_rows),
            "runtime_lowered_claims": lane_counter["runtime_lowered"],
            "suppressed_claims": lane_counter["suppressed_with_reason"],
            "runtime_evidence_required_claims": lane_counter["runtime_evidence_required"],
            "report_only_claims": lane_counter["report_only"],
            "unsupported_claims": lane_counter["unsupported_or_unmapped"],
            "cards_total": len(card_rows),
            "cards_with_missing_links": cards_with_missing_links,
        },
        "claim_rows": claim_rows,
        "card_rows": card_rows,
    }


def render_source_contract_audit_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    if not isinstance(summary, dict):
        summary = {}
    lines = [
        f"# Source Contract Audit: {report.get('deck_name', 'Deck')}",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Claims total | {summary.get('claims_total', 0)} |",
        f"| Runtime lowered claims | {summary.get('runtime_lowered_claims', 0)} |",
        f"| Suppressed claims | {summary.get('suppressed_claims', 0)} |",
        f"| Runtime evidence required claims | {summary.get('runtime_evidence_required_claims', 0)} |",
        f"| Report-only claims | {summary.get('report_only_claims', 0)} |",
        f"| Cards with missing links | {summary.get('cards_with_missing_links', 0)} |",
        "",
        "## Card Closure",
        "",
        "| Card ID | Name | Lane | First Missing Link | Runtime Surfaces |",
        "| --- | --- | --- | --- | --- |",
    ]
    cards = report.get("card_rows", {})
    if isinstance(cards, dict):
        for card_id, row in sorted(cards.items()):
            if not isinstance(row, dict):
                continue
            surfaces = ", ".join(str(item) for item in row.get("runtime_surfaces", []))
            lines.append(
                f"| {card_id} | {row.get('name', card_id)} | "
                f"{row.get('readiness_lane', '')} | {row.get('first_missing_link', '')} | "
                f"{surfaces or '-'} |"
            )
    lines.append("")
    return "\n".join(lines)


def _card_roles(config_readiness_report: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    cards = config_readiness_report.get("cards", {})
    if not isinstance(cards, Mapping):
        return {}
    return {
        str(card_id): {
            "roles": list(row.get("roles", [])) if isinstance(row, Mapping) else [],
            "semantic_families": list(row.get("semantic_families", []))
            if isinstance(row, Mapping)
            else [],
        }
        for card_id, row in cards.items()
    }


def _emitted_claim_ids(
    *,
    mulligan_plan: Mapping[str, Any],
    card_behavior_plan: Mapping[str, Any],
    combo_plan: Mapping[str, Any],
    global_values_authority_matrix: Mapping[str, Any],
) -> set[str]:
    claim_ids: set[str] = set()
    for row in list(mulligan_plan.get("rules", [])) + list(card_behavior_plan.get("rows", [])) + list(combo_plan.get("combos", [])):
        if isinstance(row, Mapping) and row.get("claim_id"):
            claim_ids.add(str(row["claim_id"]))
    for row in global_values_authority_matrix.get("allowed_step1_overlays", []):
        if isinstance(row, Mapping) and row.get("claim_id"):
            claim_ids.add(str(row["claim_id"]))
    return claim_ids


def _suppressed_reasons(
    *,
    mulligan_plan: Mapping[str, Any],
    card_behavior_plan: Mapping[str, Any],
    combo_plan: Mapping[str, Any],
) -> dict[str, str]:
    reasons: dict[str, str] = {}
    for row in list(mulligan_plan.get("suppressed_rules", [])) + list(card_behavior_plan.get("suppressed", [])) + list(combo_plan.get("suppressed", [])):
        if isinstance(row, Mapping) and row.get("claim_id"):
            reasons[str(row["claim_id"])] = str(row.get("reason", "suppressed"))
    return reasons


def _runtime_evidence_claim_ids(global_values_authority_matrix: Mapping[str, Any]) -> set[str]:
    claim_ids = set()
    for row in global_values_authority_matrix.get("blocked_until_runtime_evidence", []):
        if isinstance(row, Mapping) and row.get("claim_id"):
            claim_ids.add(str(row["claim_id"]))
    return claim_ids


def _claim_lane(
    *,
    claim_id: str,
    surfaces: Mapping[str, Mapping[str, Any]],
    emitted_claim_ids: set[str],
    suppressed_reasons: Mapping[str, str],
    runtime_evidence_claim_ids: set[str],
) -> tuple[str, str]:
    if claim_id in emitted_claim_ids:
        return "runtime_lowered", "allowed"
    if claim_id in suppressed_reasons:
        return "suppressed_with_reason", suppressed_reasons[claim_id]
    if claim_id in runtime_evidence_claim_ids:
        return "runtime_evidence_required", "requires_runtime_evidence"
    reasons = {str(row.get("reason", "")) for row in surfaces.values() if isinstance(row, Mapping)}
    if "requires_runtime_evidence" in reasons:
        return "runtime_evidence_required", "requires_runtime_evidence"
    if "claim_not_runtime_lowerable" in reasons:
        return "report_only", "claim_not_runtime_lowerable"
    if all(reason.startswith("claim_kind_not_") for reason in reasons if reason):
        return "unsupported_or_unmapped", sorted(reasons)[0] if reasons else "no_surface"
    return "report_only", sorted(reasons)[0] if reasons else "no_surface"


def _claim_cards(claim: Mapping[str, Any]) -> list[str]:
    cards = claim.get("cards", [])
    if isinstance(cards, str):
        cards = [cards]
    if not isinstance(cards, list):
        return []
    return [str(card) for card in cards if str(card)]


def _decision_to_dict(decision: Any) -> dict[str, Any]:
    return {
        "allowed": bool(decision.allowed),
        "reason": str(decision.reason),
        "claim_kind": str(decision.claim_kind),
        "surface": str(decision.surface),
    }


def _card_rows(
    config_readiness_report: Mapping[str, Any],
    card_claim_lanes: Mapping[str, Counter[str]],
) -> dict[str, dict[str, Any]]:
    cards = config_readiness_report.get("cards", {})
    if not isinstance(cards, Mapping):
        return {}
    rows: dict[str, dict[str, Any]] = {}
    for card_id, row in sorted(cards.items()):
        if not isinstance(row, Mapping):
            continue
        rows[str(card_id)] = {
            "card_id": str(card_id),
            "name": str(row.get("name", card_id)),
            "roles": [str(role) for role in row.get("roles", [])],
            "runtime_surfaces": [str(surface) for surface in row.get("runtime_surfaces", [])],
            "readiness_lane": str(row.get("readiness_lane", "")),
            "first_missing_link": str(row.get("first_missing_link", "")),
            "claim_lanes": dict(card_claim_lanes.get(str(card_id), Counter())),
        }
    return rows
```

- [ ] **Step 4: Run tests to verify Task 1 passes**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
$env:PYTHONPATH='src'
python -m pytest tests/test_source_contract_audit.py -q
```

Expected: `3 passed`.

- [ ] **Step 5: Commit Task 1**

```powershell
git add src/hsconfig/source_contract_audit.py tests/test_source_contract_audit.py
git commit -m "feat: add source contract audit report builder"
```

---

### Task 2: Wire Audit Into Package Generation

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\package_builder.py`
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_prepare_cli.py`

**Interfaces:**
- Consumes:
  - `build_source_contract_audit(...)`
  - `render_source_contract_audit_markdown(report)`
- Produces:
  - `reports/source_contract_audit.json`
  - `reports/source_contract_audit.md`
  - `operator_summary.json.generated_files` includes both new files.

- [ ] **Step 1: Write failing package-generation regression**

Append this test to `C:\Users\darbo\Documents\HSConfig\tests\test_prepare_cli.py`:

```python
def test_prepare_writes_source_contract_audit_reports(tmp_path, monkeypatch):
    from tests.helpers.fixture_prepare import (
        load_archetype_matrix,
        prepare_fixture_deck,
        read_json,
    )

    monkeypatch.setattr(
        "hsconfig.package_builder.fetch_latest_cards",
        lambda timeout=10.0: [],
    )
    deck = next(row for row in load_archetype_matrix() if row["deck_name"] == "ShadowPriest")
    result = prepare_fixture_deck(tmp_path, deck)
    package = result["out"]
    reports = package / "reports"

    audit_json = read_json(reports / "source_contract_audit.json")
    audit_md = (reports / "source_contract_audit.md").read_text(encoding="utf-8")
    operator = read_json(reports / "operator_summary.json")
    generated = {path.replace("\\", "/") for path in operator["generated_files"]}

    assert result["exit_code"] == 0
    assert audit_json["schema_version"] == 1
    assert audit_json["deck_name"] == "ShadowPriest"
    assert audit_json["summary"]["cards_total"] > 0
    assert "# Source Contract Audit: ShadowPriest" in audit_md
    assert "reports/source_contract_audit.json" in generated
    assert "reports/source_contract_audit.md" in generated
    assert operator["source_contract_audit_summary"]["cards_total"] == audit_json["summary"][
        "cards_total"
    ]
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
$env:PYTHONPATH='src'
python -m pytest tests/test_prepare_cli.py::test_prepare_writes_source_contract_audit_reports -q
```

Expected: fail because `reports/source_contract_audit.json` does not exist.

- [ ] **Step 3: Modify package builder**

In `C:\Users\darbo\Documents\HSConfig\src\hsconfig\package_builder.py`, add imports near the other report imports:

```python
from hsconfig.source_contract_audit import (
    build_source_contract_audit,
    render_source_contract_audit_markdown,
)
```

After `source_claim_gap_report = build_source_claim_gap_report(...)`, add:

```python
    source_contract_audit_report = build_source_contract_audit(
        deck_name=args.deck_name,
        deck_identity=deck_identity,
        guide_claim_bundle=guide_claim_bundle,
        mulligan_plan=mulligan_plan,
        card_behavior_plan=card_behavior_plan,
        combo_plan=combo_plan,
        global_values_authority_matrix=global_values_authority_matrix,
        config_readiness_report=config_readiness_report,
    )
    write_json(reports_dir / "source_contract_audit.json", source_contract_audit_report)
    (reports_dir / "source_contract_audit.md").write_text(
        render_source_contract_audit_markdown(source_contract_audit_report),
        encoding="utf-8",
        newline="\n",
    )
```

Add the report to `operator_summary_kwargs`:

```python
        "source_contract_audit_report": source_contract_audit_report,
```

Keep `operator_summary` creation after `generated_files = _generated_package_files(...)` so the new reports are included in `generated_files`.

- [ ] **Step 4: Run package test**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
$env:PYTHONPATH='src'
python -m pytest tests/test_prepare_cli.py::test_prepare_writes_source_contract_audit_reports -q
```

Expected: `1 passed`.

- [ ] **Step 5: Run nearby CLI/report tests**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
$env:PYTHONPATH='src'
python -m pytest tests/test_prepare_cli.py tests/test_shadowpriest_e2e.py -q
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit Task 2**

```powershell
git add src/hsconfig/package_builder.py tests/test_prepare_cli.py
git commit -m "feat: write source contract audit during prepare"
```

---

### Task 3: Thread Audit Summary Through Operator Reports

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\operator_summary.py`
- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\report_ownership.py`
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_operator_summary.py`
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_report_ownership.py`

**Interfaces:**
- Consumes:
  - `source_contract_audit_report: dict[str, Any] | None`
- Produces:
  - `operator_summary["source_contract_audit_summary"]`
  - `operator_summary["report_ownership"]` includes `reports/source_contract_audit.json`

- [ ] **Step 1: Write failing operator summary test**

Append to `tests/test_operator_summary.py`:

```python
def test_operator_summary_threads_source_contract_audit_without_gating_apply():
    summary = build_operator_summary(
        deck_name="AuditDeck",
        deck_code="AAEBAQAAAA==",
        technical_validation={"status": "passed", "errors": []},
        guide_source_depth={"source_depth_status": "static_semantics_only", "claim_count": 1},
        generated_files=[
            "CustomConfig/auditdeck/GlobalValues.json",
            "CustomConfig/auditdeck/Mulligan.json",
            "reports/source_contract_audit.json",
            "reports/source_contract_audit.md",
        ],
        source_contract_audit_report={
            "summary": {
                "claims_total": 4,
                "runtime_lowered_claims": 2,
                "suppressed_claims": 1,
                "runtime_evidence_required_claims": 1,
                "report_only_claims": 0,
                "cards_total": 3,
                "cards_with_missing_links": 1,
            }
        },
    )

    assert summary["technical_status"] == "VALID_PACKAGE"
    assert summary["runtime_apply_allowed"] is True
    assert summary["source_contract_audit_summary"] == {
        "claims_total": 4,
        "runtime_lowered_claims": 2,
        "suppressed_claims": 1,
        "runtime_evidence_required_claims": 1,
        "report_only_claims": 0,
        "cards_total": 3,
        "cards_with_missing_links": 1,
        "next_report_to_open": "reports/source_contract_audit.json",
    }
```

Append to `tests/test_report_ownership.py`:

```python
def test_report_ownership_includes_source_contract_audit():
    rows = build_report_ownership()
    by_file = {row["file"]: row for row in rows}

    assert by_file["reports/source_contract_audit.json"]["authority"] == (
        "source_contract_explanation"
    )
    assert by_file["reports/source_contract_audit.json"]["answers"] == (
        "why each source claim did or did not lower to runtime config"
    )
    assert by_file["reports/operator_summary.json"]["open_order"] == "1"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
$env:PYTHONPATH='src'
python -m pytest tests/test_operator_summary.py::test_operator_summary_threads_source_contract_audit_without_gating_apply tests/test_report_ownership.py::test_report_ownership_includes_source_contract_audit -q
```

Expected: fail because `build_operator_summary()` has no `source_contract_audit_report` argument and ownership lacks the new report.

- [ ] **Step 3: Modify operator summary**

In `build_operator_summary()` signature, add:

```python
    source_contract_audit_report: dict[str, Any] | None = None,
```

Before `summary = { ... }`, add:

```python
    source_contract_audit_summary = _source_contract_audit_summary(
        source_contract_audit_report
    )
```

Inside `summary`, add:

```python
        "source_contract_audit_summary": source_contract_audit_summary,
```

At the bottom of `operator_summary.py`, add:

```python
def _source_contract_audit_summary(report: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(report, dict):
        return {
            "claims_total": 0,
            "runtime_lowered_claims": 0,
            "suppressed_claims": 0,
            "runtime_evidence_required_claims": 0,
            "report_only_claims": 0,
            "cards_total": 0,
            "cards_with_missing_links": 0,
            "next_report_to_open": None,
        }
    summary = report.get("summary", {})
    if not isinstance(summary, dict):
        summary = {}
    return {
        "claims_total": _int_value(summary.get("claims_total", 0)),
        "runtime_lowered_claims": _int_value(summary.get("runtime_lowered_claims", 0)),
        "suppressed_claims": _int_value(summary.get("suppressed_claims", 0)),
        "runtime_evidence_required_claims": _int_value(
            summary.get("runtime_evidence_required_claims", 0)
        ),
        "report_only_claims": _int_value(summary.get("report_only_claims", 0)),
        "cards_total": _int_value(summary.get("cards_total", 0)),
        "cards_with_missing_links": _int_value(summary.get("cards_with_missing_links", 0)),
        "next_report_to_open": "reports/source_contract_audit.json",
    }
```

- [ ] **Step 4: Modify report ownership**

Insert this row after `reports/operator_summary.json` in `build_report_ownership()`:

```python
        {
            "file": "reports/source_contract_audit.json",
            "authority": "source_contract_explanation",
            "answers": "why each source claim did or did not lower to runtime config",
            "open_order": "2",
        },
```

Increment later open order numbers by one so `reports/source_claim_gap_report.json` becomes `"3"`, `reports/strong_promotion_report.json` becomes `"4"`, and so on. Keep `operator_summary.json` as the only `"1"`.

- [ ] **Step 5: Run focused tests**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
$env:PYTHONPATH='src'
python -m pytest tests/test_operator_summary.py::test_operator_summary_threads_source_contract_audit_without_gating_apply tests/test_report_ownership.py -q
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit Task 3**

```powershell
git add src/hsconfig/operator_summary.py src/hsconfig/report_ownership.py tests/test_operator_summary.py tests/test_report_ownership.py
git commit -m "feat: expose source contract audit in operator summary"
```

---

### Task 4: Add ShadowPriest And No-Block E2E Coverage

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_shadowpriest_e2e.py`
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_universal_wild_no_block_matrix.py`

**Interfaces:**
- Consumes:
  - Generated package reports from existing fixture helpers.
- Produces:
  - Regression that `SW_448` effect visibility and no-mulligan behavior are both visible in the new audit.
  - Regression that all representative Wild decks still generate a source audit and remain load-safe.

- [ ] **Step 1: Add ShadowPriest audit assertions**

In the existing ShadowPriest E2E test, after reading `operator_summary.json`, read:

```python
    source_contract_audit = json.loads(
        (reports / "source_contract_audit.json").read_text(encoding="utf-8")
    )
```

Add assertions:

```python
    assert source_contract_audit["deck_name"] == "ShadowPriest"
    darkbishop = source_contract_audit["card_rows"]["SW_448"]
    assert "SW_448.json" in darkbishop["runtime_surfaces"]
    assert darkbishop["claim_lanes"].get("runtime_lowered", 0) >= 1

    darkbishop_claims = [
        row
        for row in source_contract_audit["claim_rows"].values()
        if "SW_448" in row["cards"]
    ]
    assert any(row["claim_kind"] == "hero_power_transform" for row in darkbishop_claims)
    assert not any(
        row["claim_kind"] == "mulligan_keep"
        and row["lane"] == "runtime_lowered"
        for row in darkbishop_claims
    )
```

- [ ] **Step 2: Add representative no-block audit assertions**

In `tests/test_universal_wild_no_block_matrix.py`, after the package is prepared and reports are loaded, assert:

```python
    audit_path = out / "reports" / "source_contract_audit.json"
    assert audit_path.exists()
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    assert audit["summary"]["cards_total"] > 0
    assert operator["runtime_apply_allowed"] is True
```

- [ ] **Step 3: Run E2E tests**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
$env:PYTHONPATH='src'
python -m pytest tests/test_shadowpriest_e2e.py tests/test_universal_wild_no_block_matrix.py -q
```

Expected: all selected tests pass.

- [ ] **Step 4: Commit Task 4**

```powershell
git add tests/test_shadowpriest_e2e.py tests/test_universal_wild_no_block_matrix.py
git commit -m "test: prove source contract audit on shadowpriest and wild matrix"
```

---

### Task 5: Update Operator And Skill Documentation

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\docs\operator\README.md`
- Modify: `C:\Users\darbo\Documents\HSConfig\docs\operator\guide-research-policy.md`
- Modify: `C:\Users\darbo\Documents\HSConfig\.agents\skills\hsconfig\SKILL.md`
- Modify: `C:\Users\darbo\.codex\skills\hsconfig\SKILL.md`
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_skill_files.py`
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_docs_active_path.py`

**Interfaces:**
- Consumes:
  - New `reports/source_contract_audit.json` and Markdown report.
- Produces:
  - Active docs explain the report as diagnostic and not an apply gate.
  - Skill opens `operator_summary.json` first and uses source-contract audit for explanation.

- [ ] **Step 1: Add failing docs/skill assertions**

In `tests/test_skill_files.py`, add:

```python
def test_hsconfig_skill_mentions_source_contract_audit_as_diagnostic():
    text = Path(".agents/skills/hsconfig/SKILL.md").read_text(encoding="utf-8")

    assert "reports/source_contract_audit.json" in text
    assert "why a claim did or did not lower" in text
    assert "operator_summary.json" in text
```

In `tests/test_docs_active_path.py`, add:

```python
def test_operator_docs_describe_source_contract_audit_without_replacing_gate():
    text = Path("docs/operator/README.md").read_text(encoding="utf-8")

    assert "reports/source_contract_audit.json" in text
    assert "does not replace `reports/operator_summary.json`" in text
```

- [ ] **Step 2: Run docs tests to verify they fail**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
$env:PYTHONPATH='src'
python -m pytest tests/test_skill_files.py::test_hsconfig_skill_mentions_source_contract_audit_as_diagnostic tests/test_docs_active_path.py::test_operator_docs_describe_source_contract_audit_without_replacing_gate -q
```

Expected: fail because docs do not mention the new report yet.

- [ ] **Step 3: Update operator docs**

In `docs/operator/README.md`, add this paragraph near the report ownership table:

```markdown
`reports/source_contract_audit.json` explains why each source claim did or did not lower into Mulligan, GlobalValues, CardID, or Combo runtime config. It is diagnostic only and does not replace `reports/operator_summary.json` as the normal gate. Use it when a card looks under-configured or when a Start of Game, hero-power-transform, deckbuilding, Combo, or GlobalValues claim was intentionally kept visible without becoming a runtime row.
```

Add this table row after `operator_summary.json`:

```markdown
| `reports/source_contract_audit.json` | source-contract explanation | why each source claim did or did not lower to runtime config |
```

In `docs/operator/guide-research-policy.md`, add:

```markdown
`source_contract_audit.json` is the claim-to-runtime explanation report. It keeps the workflow non-blocking: weak or unsupported claims stay visible, runtime-evidence-only GlobalValues rows stay visible, and only documented surface-matching claims lower into runtime files.
```

- [ ] **Step 4: Update repo skill and installed skill**

In both skill files, add this bullet near the report-opening guidance:

```markdown
- Use `reports/source_contract_audit.json` when you need to explain why a claim did or did not lower into Mulligan, GlobalValues, CardID, or Combo. It is diagnostic only; `reports/operator_summary.json` remains the gate.
```

Affected files:

```text
C:\Users\darbo\Documents\HSConfig\.agents\skills\hsconfig\SKILL.md
C:\Users\darbo\.codex\skills\hsconfig\SKILL.md
```

- [ ] **Step 5: Run docs/skill tests**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
$env:PYTHONPATH='src'
python -m pytest tests/test_skill_files.py tests/test_docs_active_path.py -q
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit repo docs and note local skill sync**

```powershell
git add docs/operator/README.md docs/operator/guide-research-policy.md .agents/skills/hsconfig/SKILL.md tests/test_skill_files.py tests/test_docs_active_path.py
git commit -m "docs: document source contract audit report"
```

The installed skill file at `C:\Users\darbo\.codex\skills\hsconfig\SKILL.md` is outside the Git repository. Update it during implementation, verify it with `tests/test_skill_files.py`, but do not stage it in this repository.

---

### Task 6: Final Verification And GitHub Sync

**Files:**
- No planned source edits unless verification exposes a regression.

**Interfaces:**
- Consumes:
  - All tasks above.
- Produces:
  - Verified branch with clean status.
  - Main pushed after green verification if this is executed directly on `main`.

- [ ] **Step 1: Validate research gate remains intact**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python C:\Users\darbo\.codex\skills\research\validate_json.py -f docs\research\2026-07-12-hsconfig-source-contract-logic-brainstorm\fields.yaml -d docs\research\2026-07-12-hsconfig-source-contract-logic-brainstorm\results
```

Expected:

```text
Validation passed: 3/3
Average coverage: 100.0%
```

- [ ] **Step 2: Run targeted source-contract tests**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
$env:PYTHONPATH='src'
python -m pytest tests/test_source_contract_audit.py tests/test_claim_kind_runtime_contract.py tests/test_surface_authority_split.py tests/test_shadowpriest_e2e.py -q
```

Expected: all selected tests pass.

- [ ] **Step 3: Run reporting and docs tests**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
$env:PYTHONPATH='src'
python -m pytest tests/test_operator_summary.py tests/test_report_ownership.py tests/test_prepare_cli.py tests/test_skill_files.py tests/test_docs_active_path.py -q
```

Expected: all selected tests pass.

- [ ] **Step 4: Run wider suite**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
$env:PYTHONPATH='src'
python -m pytest -q
```

Expected: full suite passes. Prior baseline was `870 passed, 2 skipped`; the exact count may increase after new tests.

- [ ] **Step 5: Scan for accidental policy drift**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
rg -n "source_contract_audit|source contract audit|operator_summary.json" docs .agents src tests
rg -n "Darkbishop|SW_448|start_of_game_effect_does_not_require_opening_hand" src tests docs .agents
```

Expected:
- New report is mentioned only as diagnostic.
- `operator_summary.json` remains the normal gate.
- Darkbishop/SW_448 tests still prove effect semantics without Mulligan keep.

- [ ] **Step 6: Inspect diff**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
git diff --stat
git diff -- src tests docs .agents
git status --short --branch
```

Expected:
- Only planned files changed.
- No generated packages, raw runtime logs, caches, or unrelated files are staged.

- [ ] **Step 7: Commit and push final state**

If earlier task commits were not made, create one final commit:

```powershell
cd C:\Users\darbo\Documents\HSConfig
git add src tests docs .agents
git commit -m "feat: add source contract audit explanation report"
git push origin main
```

If task commits already exist locally, run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
git push origin main
```

Expected:

```text
Everything up-to-date
```

or a successful push of the new commits.

---

## Self-Review

- Spec coverage: The plan implements the recommended Source-/Contract-Closure report, keeps runtime gates unchanged, preserves no-block behavior, documents the new report, and adds ShadowPriest/Darkbishop regression coverage.
- Placeholder scan: No undefined placeholder marker or deferred follow-up wording is used.
- Type consistency: `build_source_contract_audit(...)`, `render_source_contract_audit_markdown(...)`, `source_contract_audit_report`, and `source_contract_audit_summary` are named consistently across tasks.
- Scope discipline: The plan avoids a new pipeline, new dependencies, and broad schema rewrites. It adds one explanation artifact plus minimal operator and documentation threading.

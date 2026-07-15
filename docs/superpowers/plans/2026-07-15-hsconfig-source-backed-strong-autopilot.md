# HSConfig Source-Backed Strong Autopilot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a lean source-autopilot layer that turns public guide/search records into strict `source_documents.json`, feeds the existing HSConfig source-contract pipeline, and proves ShadowPriest can reach `SOURCE_BACKED_STRONG` without default-only runtime surfaces or the Darkbishop Benedictus mulligan regression.

**Architecture:** Keep the existing `configure -> source-manifest -> draft-source-documents -> research-deck -> prepare -> validate -> apply` authority chain. Add one pure Python source-autopilot module plus one CLI command that prepares evidence rows before the existing drafter, then add an optional `configure --auto-source` bridge that consumes those rows without changing runtime apply authority. Source strength remains diagnostic truth: load-safe packages are never blocked by source depth, and `SOURCE_BACKED_STRONG` is only emitted when guide-backed lowerable claims actually exist.

**Tech Stack:** Python 3.11+, stdlib `json`, `pathlib`, `datetime`, existing HSConfig modules, `unittest`/`pytest`-style tests already used in the repo, no new runtime dependencies.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig` for `Teufelsboy/HSConfig`.
- Do not move work to `C:\Users\darbo\Documents\HS`, temp checkouts, or shadow workspaces.
- Keep HSConfig pre-run only: no replay parsing, no winrate tuning, no post-game HSTuner logic.
- Runtime writes remain allowed only through existing `hsconfig apply` or `hsconfig configure --apply`.
- `reports/operator_summary.json` remains the normal apply authority.
- `source_contract_audit.json`, `source_to_runtime_explainability.json`, source-depth reports, and no-default-only diagnostics remain diagnostic.
- Do not fake `SOURCE_BACKED_STRONG`; static HearthstoneJSON/card-text semantics do not count as guide-backed strong evidence.
- Do not convert Darkbishop Benedictus / Shadow Priest start-of-game effect into a mulligan keep unless a source explicitly says to keep the card in the opening hand.
- Preserve Darkbishop Benedictus as a `hero_power_transform` runtime/effect claim when source or static semantics support the effect.
- Do not hide default-only surfaces. If generated surfaces are thin, report the first missing source-to-runtime link.
- Produce a valid load-safe config for any deck even when guide evidence is weak or unavailable.
- Use short structured source records and evidence rows in tests. Do not commit raw long guide pages, private browsing dumps, logs, or scraped bulk text.
- Keep the implementation narrow: source ranking, evidence-row extraction, source-document drafting, configure integration, reports, tests, docs.

---

## File Structure

Create:

- `src/hsconfig/source_autopilot.py`
  - Pure deterministic builder. Converts source search records into ranked public source rows, source evidence rows, strict source documents, and a compact source-autopilot report.

- `tests/test_source_autopilot.py`
  - Unit tests for ranking, extraction, dedupe, Darkbishop split, source-document compatibility, and non-blocking weak-source behavior.

- `tests/test_source_autopilot_cli.py`
  - CLI tests for the new inspected command.

- `tests/test_configure_auto_source.py`
  - End-to-end configure tests proving `--auto-source` uses source-autopilot output and keeps load-safe no-block behavior.

- `tests/fixtures/source_search_shadowpriest_2026.json`
  - Compact structured guide/search fixture with current ShadowPriest guide-backed mulligan and hero-power evidence.

- `tests/fixtures/source_search_decklist_only.json`
  - Compact source fixture with only decklist/static evidence to prove source-informed no-block fallback.

Modify:

- `src/hsconfig/commands/source_workflow.py`
  - Add `source_autopilot_payload(args)` and `run_source_autopilot_command(args)`.

- `src/hsconfig/commands/configure.py`
  - Add optional `--auto-source` stage between manifest and draft/research.

- `src/hsconfig/cli.py`
  - Register and dispatch `source-autopilot`.

- `src/hsconfig/cli_parser.py`
  - Add parser args for `source-autopilot`, `configure --auto-source`, and `configure --source-search-results-json`.

- `docs/operator/README.md`
  - Document the normal source-autopilot path without turning source strength into an apply blocker.

- `docs/operator/source-builder-workflow.md`
  - Replace the manual evidence-row-only flow with the inspected autopilot flow plus the manual fallback.

- `docs/operator/autonomous-source-builder-next.md`
  - Mark the implemented boundary: search/source records can now feed HSConfig directly; free web browsing remains Codex/operator responsibility, not a hidden runtime dependency.

- `docs/operator/guide-research-policy.md`
  - Add the claim-quality boundary for `source-autopilot`: guide-backed claims can promote strong, decklist-only and static claims cannot.

---

### Task 1: Add Source Search Fixtures And Failing Unit Tests

**Files:**
- Create: `tests/fixtures/source_search_shadowpriest_2026.json`
- Create: `tests/fixtures/source_search_decklist_only.json`
- Create: `tests/test_source_autopilot.py`

**Interfaces:**
- Consumes: existing `draft_source_documents(...)`, `build_source_document_bundle(...)`, and source-document claim schema.
- Produces: failing tests for `rank_public_sources(...)`, `extract_source_evidence_rows(...)`, and `build_source_autopilot_bundle(...)`.

- [ ] **Step 1: Create the ShadowPriest compact source-search fixture**

Write `tests/fixtures/source_search_shadowpriest_2026.json`:

```json
{
  "schema_version": 1,
  "deck_name": "ShadowPriest",
  "records": [
    {
      "source_url": "https://www.hearthpwn.com/decks/1461644-voidburn-wild-aggro-shadow-priest",
      "source_title": "Voidburn Wild Aggro Shadow Priest",
      "source_family": "guide",
      "retrieved_at": "2026-07-15T00:00:00Z",
      "deck_match": {
        "deck_name": "ShadowPriest",
        "archetype": "aggro_burn_hero_power_transform",
        "matched_card_ids": ["BAR_735", "SCH_514", "SW_444", "TOY_381", "GVG_009"]
      },
      "mulligan": {
        "keep_card_ids": ["TOY_381", "SW_444", "SCH_514", "GVG_009"],
        "discard_cost_min": 4,
        "evidence_text_short": "Guide mulligan keeps cheap pressure cards and says not to keep cards costing 4 or more."
      },
      "claims": [
        {
          "claim_kind": "gameplan_posture",
          "scope": "deck",
          "stance": "aggressive_burn_pressure",
          "evidence_text_short": "The deck is an aggressive Shadow Priest burn strategy.",
          "source_confidence": "high"
        },
        {
          "claim_kind": "hero_power_transform",
          "cards": ["BAR_735"],
          "stance": "enable_mind_spike_shadow_hero_power",
          "evidence_text_short": "Darkbishop Benedictus enables the Shadow Priest hero power plan.",
          "source_confidence": "high",
          "semantic_qualifiers": {
            "zone_scope": "Deck",
            "state_requirements": ["deckbuilding_effect"]
          }
        },
        {
          "claim_kind": "targeting_rule",
          "cards": ["SW_444"],
          "stance": "advance_face_damage_plan",
          "evidence_text_short": "Twilight Deceptor belongs to the low-cost pressure and burn plan.",
          "source_confidence": "high"
        }
      ]
    }
  ]
}
```

- [ ] **Step 2: Create the weak decklist-only fixture**

Write `tests/fixtures/source_search_decklist_only.json`:

```json
{
  "schema_version": 1,
  "deck_name": "ThinDeck",
  "records": [
    {
      "source_url": "https://example.com/thin-decklist",
      "source_title": "Thin Decklist",
      "source_family": "decklist",
      "retrieved_at": "2026-07-15T00:00:00Z",
      "deck_match": {
        "deck_name": "ThinDeck",
        "archetype": "unknown",
        "matched_card_ids": ["CARD_001"]
      },
      "claims": [
        {
          "claim_kind": "card_role",
          "cards": ["CARD_001"],
          "stance": "listed_card",
          "evidence_text_short": "The card appears in the decklist.",
          "source_confidence": "medium"
        }
      ]
    }
  ]
}
```

- [ ] **Step 3: Write failing source-autopilot unit tests**

Create `tests/test_source_autopilot.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from hsconfig.source_document_builder import build_source_document_bundle
from hsconfig.source_autopilot import (
    build_source_autopilot_bundle,
    extract_source_evidence_rows,
    rank_public_sources,
)


FIXTURES = Path(__file__).parent / "fixtures"

SHADOW_DECK_IDENTITY = {
    "deck_name": "ShadowPriest",
    "deck_code_hash": "sha256:shadow",
    "deck_slug": "shadowpriest",
    "cards": [
        {"card_id": "BAR_735", "name": "Darkbishop Benedictus", "cost": 5, "count": 1},
        {"card_id": "TOY_381", "name": "Papercraft Angel", "cost": 3, "count": 2},
        {"card_id": "SW_444", "name": "Twilight Deceptor", "cost": 2, "count": 2},
        {"card_id": "SCH_514", "name": "Raise Dead", "cost": 0, "count": 2},
        {"card_id": "GVG_009", "name": "Shadowbomber", "cost": 1, "count": 2},
    ],
}


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_rank_public_sources_prefers_current_matching_guides_over_decklists():
    guide = _fixture("source_search_shadowpriest_2026.json")["records"][0]
    decklist = _fixture("source_search_decklist_only.json")["records"][0]

    ranked = rank_public_sources(
        deck_name="ShadowPriest",
        deck_identity=SHADOW_DECK_IDENTITY,
        source_search_records=[decklist, guide],
        current_date="2026-07-15",
    )

    assert ranked[0]["source_url"] == guide["source_url"]
    assert ranked[0]["source_rank_lane"] == "guide_current_deck_match"
    assert ranked[1]["source_rank_lane"] == "decklist_only"


def test_extract_source_evidence_rows_preserves_darkbishop_effect_not_mulligan_keep():
    records = _fixture("source_search_shadowpriest_2026.json")["records"]

    rows = extract_source_evidence_rows(
        deck_name="ShadowPriest",
        deck_identity=SHADOW_DECK_IDENTITY,
        ranked_sources=rank_public_sources(
            deck_name="ShadowPriest",
            deck_identity=SHADOW_DECK_IDENTITY,
            source_search_records=records,
            current_date="2026-07-15",
        ),
        current_date="2026-07-15",
    )

    darkbishop_rows = [
        row for row in rows if row.get("cards") == ["BAR_735"] or row.get("card_mentions") == ["Darkbishop Benedictus"]
    ]
    assert any(row["claim_kind"] == "hero_power_transform" for row in darkbishop_rows)
    assert not any(row["claim_kind"] == "mulligan_keep" for row in darkbishop_rows)
    assert any(
        row["claim_kind"] == "mulligan_discard" and row.get("cards") == ["BAR_735"]
        for row in darkbishop_rows
    )


def test_build_source_autopilot_bundle_outputs_strict_source_documents():
    payload = _fixture("source_search_shadowpriest_2026.json")

    bundle = build_source_autopilot_bundle(
        deck_name="ShadowPriest",
        deck_identity=SHADOW_DECK_IDENTITY,
        source_search_records=payload["records"],
        current_date="2026-07-15",
    )

    assert bundle["source_autopilot_report"]["status"] == "OK"
    assert bundle["source_autopilot_report"]["source_rank_summary"]["guide_current_deck_match"] == 1
    assert bundle["source_autopilot_report"]["claim_kind_counts"]["mulligan_keep"] == 4
    assert bundle["source_documents_payload"]["source_documents"]

    strict_bundle = build_source_document_bundle(
        deck_identity=SHADOW_DECK_IDENTITY,
        card_metadata={"cards": SHADOW_DECK_IDENTITY["cards"]},
        source_documents=bundle["source_documents_payload"]["source_documents"],
        current_date="2026-07-15",
    )
    assert strict_bundle["unsupported_claims"] == []
    assert any(claim["claim_kind"] == "hero_power_transform" for claim in strict_bundle["claims"])


def test_build_source_autopilot_bundle_keeps_weak_sources_non_blocking_and_visible():
    payload = _fixture("source_search_decklist_only.json")
    deck_identity = {
        "deck_name": "ThinDeck",
        "deck_code_hash": "sha256:thin",
        "deck_slug": "thindeck",
        "cards": [{"card_id": "CARD_001", "name": "Fixture Card", "cost": 1, "count": 2}],
    }

    bundle = build_source_autopilot_bundle(
        deck_name="ThinDeck",
        deck_identity=deck_identity,
        source_search_records=payload["records"],
        current_date="2026-07-15",
    )

    report = bundle["source_autopilot_report"]
    assert report["status"] == "OK"
    assert report["source_rank_summary"]["decklist_only"] == 1
    assert report["strong_candidate"] is False
    assert report["first_missing_source_action"] == "add_current_deck_guide_or_mulligan_guide"
```

- [ ] **Step 4: Run the failing unit tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_source_autopilot.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'hsconfig.source_autopilot'` or missing function imports.

- [ ] **Step 5: Commit the failing contract tests**

```powershell
git add tests/fixtures/source_search_shadowpriest_2026.json tests/fixtures/source_search_decklist_only.json tests/test_source_autopilot.py
git commit -m "test: define source autopilot contract"
```

---

### Task 2: Implement Pure Source Autopilot Builder

**Files:**
- Create: `src/hsconfig/source_autopilot.py`
- Test: `tests/test_source_autopilot.py`

**Interfaces:**
- Consumes:
  - `draft_source_documents(deck_name: str, deck_identity: dict[str, Any], evidence_rows: list[dict[str, Any]], current_date: Any = None) -> dict[str, Any]`
  - `verify_source_documents(source_documents: list[dict[str, Any]]) -> dict[str, Any]`
- Produces:
  - `rank_public_sources(deck_name: str, deck_identity: Mapping[str, Any], source_search_records: Sequence[Mapping[str, Any]], current_date: str | date | None = None) -> list[dict[str, Any]]`
  - `extract_source_evidence_rows(deck_name: str, deck_identity: Mapping[str, Any], ranked_sources: Sequence[Mapping[str, Any]], current_date: str | date | None = None) -> list[dict[str, Any]]`
  - `build_source_autopilot_bundle(deck_name: str, deck_identity: Mapping[str, Any], source_search_records: Sequence[Mapping[str, Any]], current_date: str | date | None = None) -> dict[str, Any]`

- [ ] **Step 1: Add the source-autopilot module with exact interfaces**

Write `src/hsconfig/source_autopilot.py`:

```python
from __future__ import annotations

from collections import Counter
from datetime import date, datetime
from typing import Any, Mapping, Sequence

from hsconfig.source_document_drafter import draft_source_documents
from hsconfig.source_evidence_verifier import verify_source_documents

GUIDE_FAMILIES = {"guide", "mulligan_guide", "matchup_guide", "guide_fixture"}
DECKLIST_FAMILIES = {"decklist", "deck_snapshot", "deck_code"}
STATIC_FAMILIES = {"hearthstonejson_static_semantics", "static_semantics", "metadata", "card_text"}


def rank_public_sources(
    *,
    deck_name: str,
    deck_identity: Mapping[str, Any],
    source_search_records: Sequence[Mapping[str, Any]],
    current_date: str | date | None = None,
) -> list[dict[str, Any]]:
    ranked: list[dict[str, Any]] = []
    current_year = _current_year(current_date)
    deck_card_ids = _deck_card_ids(deck_identity)
    normalized_deck_name = _norm(deck_name)
    for index, record in enumerate(source_search_records):
        row = dict(record)
        family = _text(row.get("source_family", "")).lower()
        match = row.get("deck_match", {})
        if not isinstance(match, Mapping):
            match = {}
        matched_ids = {
            _text(card_id)
            for card_id in _as_list(match.get("matched_card_ids", []))
            if _text(card_id)
        }
        deck_name_match = _norm(match.get("deck_name", "")) == normalized_deck_name
        card_overlap = len(deck_card_ids & matched_ids)
        score = 0
        if family in GUIDE_FAMILIES:
            score += 60
        if family in DECKLIST_FAMILIES:
            score += 15
        if family in STATIC_FAMILIES:
            score -= 20
        if deck_name_match:
            score += 25
        score += min(card_overlap, 10) * 3
        if _record_year(row) == current_year:
            score += 10
        if not _is_public_https(row.get("source_url", "")):
            score -= 100
        row["source_rank_score"] = score
        row["source_rank_lane"] = _rank_lane(family, deck_name_match, card_overlap, current_year, row)
        row["source_rank_index"] = index
        ranked.append(row)
    ranked.sort(key=lambda row: (-int(row["source_rank_score"]), int(row["source_rank_index"])))
    return ranked


def extract_source_evidence_rows(
    *,
    deck_name: str,
    deck_identity: Mapping[str, Any],
    ranked_sources: Sequence[Mapping[str, Any]],
    current_date: str | date | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for source in ranked_sources:
        base = _source_base(deck_name, source, current_date)
        for row in _mulligan_rows(deck_identity, source, base):
            _append_unique(rows, seen, row)
        for row in _explicit_claim_rows(source, base):
            _append_unique(rows, seen, row)
    return rows


def build_source_autopilot_bundle(
    *,
    deck_name: str,
    deck_identity: Mapping[str, Any],
    source_search_records: Sequence[Mapping[str, Any]],
    current_date: str | date | None = None,
) -> dict[str, Any]:
    ranked = rank_public_sources(
        deck_name=deck_name,
        deck_identity=deck_identity,
        source_search_records=source_search_records,
        current_date=current_date,
    )
    evidence_rows = extract_source_evidence_rows(
        deck_name=deck_name,
        deck_identity=deck_identity,
        ranked_sources=ranked,
        current_date=current_date,
    )
    draft = draft_source_documents(
        deck_name=deck_name,
        deck_identity=dict(deck_identity),
        evidence_rows=evidence_rows,
        current_date=current_date,
    )
    source_documents_payload = {
        "schema_version": 1,
        "deck_name": deck_name,
        "source_documents": draft["source_documents"],
    }
    verification = verify_source_documents(draft["source_documents"])
    report = _build_report(
        deck_name=deck_name,
        ranked_sources=ranked,
        evidence_rows=evidence_rows,
        draft=draft,
        verification=verification,
    )
    return {
        "schema_version": 1,
        "deck_name": deck_name,
        "ranked_sources": ranked,
        "source_evidence_rows": evidence_rows,
        "source_documents_payload": source_documents_payload,
        "source_document_draft_report": {
            "schema_version": 1,
            "deck_name": deck_name,
            "draft_summary": draft["draft_summary"],
            "unresolved_mentions": draft["unresolved_mentions"],
            "source_evidence_report": verification,
        },
        "source_autopilot_report": report,
    }


def _mulligan_rows(
    deck_identity: Mapping[str, Any],
    source: Mapping[str, Any],
    base: Mapping[str, Any],
) -> list[dict[str, Any]]:
    mulligan = source.get("mulligan", {})
    if not isinstance(mulligan, Mapping):
        return []
    rows: list[dict[str, Any]] = []
    evidence = _text(mulligan.get("evidence_text_short", "Mulligan guidance from current public source."))
    for card_id in _as_list(mulligan.get("keep_card_ids", [])):
        if _text(card_id):
            rows.append({
                **base,
                "claim_kind": "mulligan_keep",
                "cards": [_text(card_id)],
                "scope": "card",
                "stance": "keep",
                "evidence_text_short": evidence,
                "source_confidence": "high",
                "timing": "mulligan",
            })
    for card_id in _as_list(mulligan.get("discard_card_ids", [])):
        if _text(card_id):
            rows.append({
                **base,
                "claim_kind": "mulligan_discard",
                "cards": [_text(card_id)],
                "scope": "card",
                "stance": "discard",
                "evidence_text_short": evidence,
                "source_confidence": "high",
                "timing": "mulligan",
            })
    cost_min = mulligan.get("discard_cost_min")
    if isinstance(cost_min, int):
        for card in deck_identity.get("cards", []):
            if not isinstance(card, Mapping):
                continue
            if _int_or_none(card.get("cost")) is not None and int(card["cost"]) >= cost_min:
                card_id = _text(card.get("card_id", ""))
                if card_id:
                    rows.append({
                        **base,
                        "claim_kind": "mulligan_discard",
                        "cards": [card_id],
                        "scope": "card",
                        "stance": f"discard_cost_{cost_min}_or_more",
                        "evidence_text_short": evidence,
                        "source_confidence": "high",
                        "timing": "mulligan",
                    })
    return rows


def _explicit_claim_rows(source: Mapping[str, Any], base: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for claim in _as_list(source.get("claims", [])):
        if not isinstance(claim, Mapping):
            continue
        row = {**base, **dict(claim)}
        row.setdefault("source_confidence", "high" if base.get("source_family") in GUIDE_FAMILIES else "medium")
        row.setdefault("scope", "card")
        row.setdefault("evidence_text_short", "Structured public source claim.")
        rows.append(row)
    return rows


def _build_report(
    *,
    deck_name: str,
    ranked_sources: Sequence[Mapping[str, Any]],
    evidence_rows: Sequence[Mapping[str, Any]],
    draft: Mapping[str, Any],
    verification: Mapping[str, Any],
) -> dict[str, Any]:
    lane_counts = Counter(_text(source.get("source_rank_lane", "")) for source in ranked_sources)
    claim_counts = Counter(_text(row.get("claim_kind", "")) for row in evidence_rows)
    guide_rows = [
        row for row in evidence_rows
        if _text(row.get("source_family", "")).lower() in GUIDE_FAMILIES
    ]
    lowerable_rows = [
        row for row in guide_rows
        if _text(row.get("claim_kind", "")) not in {"source_note", "generic_advice"}
    ]
    strong_candidate = bool(lowerable_rows) and not draft.get("unresolved_mentions") and not verification.get("blocking_issues")
    return {
        "schema_version": 1,
        "deck_name": deck_name,
        "status": "OK",
        "source_rank_summary": dict(sorted(lane_counts.items())),
        "claim_kind_counts": dict(sorted(claim_counts.items())),
        "strong_candidate": strong_candidate,
        "first_missing_source_action": (
            "none" if strong_candidate else "add_current_deck_guide_or_mulligan_guide"
        ),
        "draft_summary": draft["draft_summary"],
        "verification_summary": {
            "blocking_issue_count": len(verification.get("blocking_issues", [])),
            "warning_count": len(verification.get("warnings", [])),
        },
    }


def _source_base(deck_name: str, source: Mapping[str, Any], current_date: str | date | None) -> dict[str, Any]:
    match = source.get("deck_match", {})
    if not isinstance(match, Mapping):
        match = {}
    return {
        "source_url": _text(source.get("source_url", "")),
        "source_title": _text(source.get("source_title", "")),
        "source_family": _text(source.get("source_family", "guide")),
        "retrieved_at": _text(source.get("retrieved_at", "")) or _iso_datetime(current_date),
        "deck_name": deck_name,
        "archetype": _text(match.get("archetype", "")),
    }


def _append_unique(rows: list[dict[str, Any]], seen: set[tuple[Any, ...]], row: dict[str, Any]) -> None:
    key = (
        row.get("source_url"),
        row.get("claim_kind"),
        tuple(row.get("cards", [])),
        tuple(row.get("card_mentions", [])),
        row.get("stance"),
        row.get("condition"),
        row.get("runtime_block"),
    )
    if key in seen:
        return
    seen.add(key)
    rows.append(row)


def _rank_lane(
    family: str,
    deck_name_match: bool,
    card_overlap: int,
    current_year: int | None,
    source: Mapping[str, Any],
) -> str:
    if family in GUIDE_FAMILIES and deck_name_match and card_overlap > 0 and _record_year(source) == current_year:
        return "guide_current_deck_match"
    if family in GUIDE_FAMILIES and card_overlap > 0:
        return "guide_card_overlap"
    if family in DECKLIST_FAMILIES:
        return "decklist_only"
    if family in STATIC_FAMILIES:
        return "static_semantics_only"
    return "source_unclassified"


def _deck_card_ids(deck_identity: Mapping[str, Any]) -> set[str]:
    return {
        _text(card.get("card_id", ""))
        for card in deck_identity.get("cards", [])
        if isinstance(card, Mapping) and _text(card.get("card_id", ""))
    }


def _record_year(record: Mapping[str, Any]) -> int | None:
    retrieved = _text(record.get("retrieved_at", ""))
    if len(retrieved) >= 4 and retrieved[:4].isdigit():
        return int(retrieved[:4])
    return None


def _current_year(current_date: str | date | None) -> int | None:
    if isinstance(current_date, date):
        return current_date.year
    text = _text(current_date)
    if len(text) >= 4 and text[:4].isdigit():
        return int(text[:4])
    return None


def _iso_datetime(current_date: str | date | None) -> str:
    if isinstance(current_date, date):
        return f"{current_date.isoformat()}T00:00:00Z"
    text = _text(current_date)
    if text:
        return text if "T" in text else f"{text}T00:00:00Z"
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _is_public_https(value: Any) -> bool:
    text = _text(value)
    return text.startswith("https://") and "localhost" not in text and "127.0.0.1" not in text


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _text(value: Any) -> str:
    return str(value or "").strip()


def _norm(value: Any) -> str:
    return "".join(ch for ch in _text(value).lower() if ch.isalnum())
```

- [ ] **Step 2: Run source-autopilot unit tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_source_autopilot.py -q
```

Expected: PASS, with four tests passing.

- [ ] **Step 3: Run existing source-document tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_source_document_drafter.py tests/test_source_document_builder.py -q
```

Expected: PASS. This proves the new module feeds the current strict source-document model instead of bypassing it.

- [ ] **Step 4: Commit pure builder implementation**

```powershell
git add src/hsconfig/source_autopilot.py tests/test_source_autopilot.py tests/fixtures/source_search_shadowpriest_2026.json tests/fixtures/source_search_decklist_only.json
git commit -m "feat: add source autopilot builder"
```

---

### Task 3: Add Inspected `source-autopilot` CLI Command

**Files:**
- Modify: `src/hsconfig/commands/source_workflow.py`
- Modify: `src/hsconfig/cli.py`
- Modify: `src/hsconfig/cli_parser.py`
- Create: `tests/test_source_autopilot_cli.py`

**Interfaces:**
- Consumes: `build_source_autopilot_bundle(...)` from Task 2.
- Produces:
  - CLI command: `hsconfig source-autopilot --deck-name ... --deck-code ... --source-search-results-json ... --out ...`
  - Files:
    - `ranked_sources.json`
    - `source_evidence_rows.json`
    - `source_documents.json`
    - `source_document_draft_report.json`
    - `source_autopilot_report.json`

- [ ] **Step 1: Write failing CLI tests**

Create `tests/test_source_autopilot_cli.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from hsconfig.cli import main


FIXTURES = Path(__file__).parent / "fixtures"


def test_source_autopilot_command_writes_inspected_source_artifacts(tmp_path, monkeypatch):
    cards_payload = {
        "cards": [
            {"card_id": "BAR_735", "name": "Darkbishop Benedictus", "cost": 5, "count": 1},
            {"card_id": "TOY_381", "name": "Papercraft Angel", "cost": 3, "count": 2},
            {"card_id": "SW_444", "name": "Twilight Deceptor", "cost": 2, "count": 2},
            {"card_id": "SCH_514", "name": "Raise Dead", "cost": 0, "count": 2},
            {"card_id": "GVG_009", "name": "Shadowbomber", "cost": 1, "count": 2},
        ]
    }
    cards_json = tmp_path / "cards.json"
    cards_json.write_text(json.dumps(cards_payload), encoding="utf-8")
    out = tmp_path / "source"

    status = main([
        "source-autopilot",
        "--deck-name", "ShadowPriest",
        "--deck-code", "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=",
        "--cards-json", str(cards_json),
        "--source-search-results-json", str(FIXTURES / "source_search_shadowpriest_2026.json"),
        "--out", str(out),
        "--json",
    ])

    assert status == 0
    report = json.loads((out / "source_autopilot_report.json").read_text(encoding="utf-8"))
    rows = json.loads((out / "source_evidence_rows.json").read_text(encoding="utf-8"))["evidence_rows"]
    docs = json.loads((out / "source_documents.json").read_text(encoding="utf-8"))

    assert report["strong_candidate"] is True
    assert any(row["claim_kind"] == "hero_power_transform" for row in rows)
    assert docs["source_documents"][0]["claims"]
```

- [ ] **Step 2: Run failing CLI test**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_source_autopilot_cli.py -q
```

Expected: FAIL with parser error or unknown command `source-autopilot`.

- [ ] **Step 3: Implement payload and command runner**

In `src/hsconfig/commands/source_workflow.py`, add imports:

```python
from hsconfig.source_autopilot import build_source_autopilot_bundle
from hsconfig.io import read_json
```

Add functions:

```python
def run_source_autopilot_command(args: argparse.Namespace) -> int:
    return run_payload_command(args, source_autopilot_payload)


def source_autopilot_payload(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    out = Path(args.out)
    prepare_research_output_dir(out)

    cards_payload = load_cards(
        args.cards_json,
        deck_name=args.deck_name,
        deck_code=args.deck_code,
        allow_placeholder=args.allow_placeholder,
    )
    deck_identity = build_deck_identity(
        deck_name=args.deck_name,
        deck_code=args.deck_code,
        cards=cards_payload["cards"],
        hero_dbf_id=cards_payload.get("hero_dbf_id"),
        format=cards_payload.get("format"),
        sideboards=cards_payload.get("sideboards", []),
    )
    source_payload = read_json(args.source_search_results_json)
    source_records = source_payload.get("records", source_payload)
    if not isinstance(source_records, list):
        raise ValueError("--source-search-results-json must contain a list or an object with a records list")

    bundle = build_source_autopilot_bundle(
        deck_name=args.deck_name,
        deck_identity=deck_identity,
        source_search_records=source_records,
        current_date=getattr(args, "current_date", None),
    )
    write_json(out / "ranked_sources.json", {"schema_version": 1, "ranked_sources": bundle["ranked_sources"]})
    write_json(out / "source_evidence_rows.json", {"schema_version": 1, "evidence_rows": bundle["source_evidence_rows"]})
    write_json(out / "source_documents.json", bundle["source_documents_payload"])
    write_json(out / "source_document_draft_report.json", bundle["source_document_draft_report"])
    write_json(out / "source_autopilot_report.json", bundle["source_autopilot_report"])
    return (
        {
            "status": "OK",
            "deck_name": args.deck_name,
            "deck_slug": deck_identity["deck_slug"],
            "source_autopilot_report": str(out / "source_autopilot_report.json"),
            "source_documents_json": str(out / "source_documents.json"),
            "source_evidence_json": str(out / "source_evidence_rows.json"),
        },
        0,
    )
```

- [ ] **Step 4: Register parser args**

In `src/hsconfig/cli_parser.py`, add after `draft-source-documents` parser:

```python
    source_autopilot = subparsers.add_parser(
        "source-autopilot",
        help="inspected source search to strict source documents stage",
        description=(
            "Inspected source search to strict source documents stage. "
            "Consumes compact public source records, ranks them, emits source evidence rows, "
            "drafts strict source_documents.json, and reports whether the input can support "
            "source-backed strong promotion. This command does not write runtime files."
        ),
    )
    source_autopilot.add_argument("--deck-name", required=True)
    source_autopilot.add_argument("--deck-code", required=True)
    source_autopilot.add_argument("--source-search-results-json", required=True)
    source_autopilot.add_argument("--out", required=True)
    source_autopilot.add_argument("--cards-json")
    source_autopilot.add_argument("--allow-placeholder", action="store_true")
    source_autopilot.add_argument("--current-date")
    source_autopilot.add_argument("--json", action="store_true")
```

- [ ] **Step 5: Register CLI dispatch**

In `src/hsconfig/cli.py`, import:

```python
    run_source_autopilot_command,
```

from `hsconfig.commands.source_workflow`, then add before `research-deck`:

```python
    if args.command == "source-autopilot":
        return run_source_autopilot_command(args)
```

- [ ] **Step 6: Run CLI test**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_source_autopilot_cli.py -q
```

Expected: PASS.

- [ ] **Step 7: Run source workflow tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_source_autopilot.py tests/test_source_autopilot_cli.py tests/test_source_document_drafter.py tests/test_source_document_builder.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit inspected CLI command**

```powershell
git add src/hsconfig/commands/source_workflow.py src/hsconfig/cli.py src/hsconfig/cli_parser.py tests/test_source_autopilot_cli.py
git commit -m "feat: add source autopilot command"
```

---

### Task 4: Add `configure --auto-source` Bridge

**Files:**
- Modify: `src/hsconfig/commands/configure.py`
- Modify: `src/hsconfig/cli_parser.py`
- Create: `tests/test_configure_auto_source.py`

**Interfaces:**
- Consumes: `source_autopilot_payload(args)` from `hsconfig.commands.source_workflow`.
- Produces:
  - `hsconfig configure --auto-source --source-search-results-json ...`
  - `outputs/<DeckName>/02_source_autopilot/*`
  - Existing downstream files remain unchanged under `03_research` and `04_package`.

- [ ] **Step 1: Write failing configure auto-source tests**

Create `tests/test_configure_auto_source.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from hsconfig.cli import main


FIXTURES = Path(__file__).parent / "fixtures"


def test_configure_auto_source_feeds_source_documents_into_package(tmp_path, monkeypatch):
    from hsconfig.commands import source_workflow

    monkeypatch.setattr(source_workflow, "fetch_latest_cards", lambda timeout=10.0: [])
    monkeypatch.setattr(source_workflow, "fetch_latest_collectible_cards", lambda timeout=10.0: [])

    runtime = tmp_path / "runtime"
    runtime.mkdir()
    cards_json = tmp_path / "cards.json"
    cards_json.write_text(json.dumps({
        "cards": [
            {"card_id": "BAR_735", "name": "Darkbishop Benedictus", "cost": 5, "count": 1},
            {"card_id": "TOY_381", "name": "Papercraft Angel", "cost": 3, "count": 2},
            {"card_id": "SW_444", "name": "Twilight Deceptor", "cost": 2, "count": 2},
            {"card_id": "SCH_514", "name": "Raise Dead", "cost": 0, "count": 2},
            {"card_id": "GVG_009", "name": "Shadowbomber", "cost": 1, "count": 2},
        ]
    }), encoding="utf-8")
    out = tmp_path / "shadow"

    status = main([
        "configure",
        "--deck-name", "ShadowPriest",
        "--deck-code", "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=",
        "--runtime-root", str(runtime),
        "--out", str(out),
        "--cards-json", str(cards_json),
        "--auto-source",
        "--source-search-results-json", str(FIXTURES / "source_search_shadowpriest_2026.json"),
        "--json",
    ])

    assert status == 0
    summary = json.loads((out / "configure_summary.json").read_text(encoding="utf-8"))
    operator = json.loads((out / "04_package" / "reports" / "operator_summary.json").read_text(encoding="utf-8"))
    mulligan = json.loads((out / "04_package" / "CustomConfig" / "shadowpriest" / "Mulligan.json").read_text(encoding="utf-8"))

    assert summary["source_autopilot_path"].endswith("02_source_autopilot")
    assert operator["technical_status"] == "VALID_PACKAGE"
    assert operator["default_only_runtime_surfaces"] == []
    assert "BAR_735" not in json.dumps(mulligan)
    assert (out / "02_source_autopilot" / "source_documents.json").exists()


def test_configure_auto_source_requires_source_search_results_json(tmp_path):
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    out = tmp_path / "out"

    status = main([
        "configure",
        "--deck-name", "ShadowPriest",
        "--deck-code", "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=",
        "--runtime-root", str(runtime),
        "--out", str(out),
        "--auto-source",
        "--json",
    ])

    assert status == 1
    summary = json.loads((out / "configure_summary.json").read_text(encoding="utf-8"))
    assert summary["stage"] == "source-autopilot"
    assert "--source-search-results-json is required when --auto-source is used" in summary["errors"][0]
```

- [ ] **Step 2: Run failing configure tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_configure_auto_source.py -q
```

Expected: FAIL because `--auto-source` and `--source-search-results-json` are not registered.

- [ ] **Step 3: Add parser flags to configure**

In `src/hsconfig/cli_parser.py`, add to the `configure` parser after `--source-evidence-json`:

```python
    configure.add_argument("--auto-source", action="store_true")
    configure.add_argument("--source-search-results-json")
```

- [ ] **Step 4: Integrate source-autopilot stage in configure**

In `src/hsconfig/commands/configure.py`, import:

```python
    source_autopilot_payload,
```

from `hsconfig.commands.source_workflow`.

In `configure_payload`, add a stage directory:

```python
    autopilot_dir = out / "02_source_autopilot"
```

Change the stage directory loop:

```python
    for stage_dir in (manifest_dir, autopilot_dir, draft_dir, research_dir, package_dir):
        stage_dir.mkdir(parents=True, exist_ok=True)
```

Replace the source-document setup block with:

```python
    source_documents_json = None
    source_autopilot_path = None
    if bool(getattr(args, "auto_source", False)):
        if not getattr(args, "source_search_results_json", None):
            return _finish(
                out,
                "failed",
                {
                    "stage": "source-autopilot",
                    "errors": ["--source-search-results-json is required when --auto-source is used"],
                },
                1,
            )
        try:
            autopilot_payload, autopilot_status = source_autopilot_payload(
                SimpleNamespace(
                    **common,
                    source_search_results_json=args.source_search_results_json,
                    current_date=None,
                    out=str(autopilot_dir),
                )
            )
        except Exception as exc:
            return _finish_stage_exception(out, "source-autopilot", exc)
        if autopilot_status != 0:
            return _finish(
                out,
                "failed",
                {"stage": "source-autopilot", **autopilot_payload},
                autopilot_status,
            )
        source_documents_json = autopilot_dir / "source_documents.json"
        source_autopilot_path = str(autopilot_dir)
    elif getattr(args, "source_evidence_json", None):
        try:
            draft_payload, draft_status = draft_source_documents_payload(
                SimpleNamespace(
                    **common,
                    source_evidence_json=args.source_evidence_json,
                    out=str(draft_dir),
                )
            )
        except Exception as exc:
            return _finish_stage_exception(out, "draft-source-documents", exc)
        if draft_status != 0:
            return _finish(
                out,
                "failed",
                {"stage": "draft-source-documents", **draft_payload},
                draft_status,
            )
        source_documents_json = draft_dir / "source_documents.json"
```

Add `source_autopilot_path` to the final `_finish` payload:

```python
            "source_autopilot_path": source_autopilot_path,
```

- [ ] **Step 5: Run configure auto-source tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_configure_auto_source.py -q
```

Expected: PASS.

- [ ] **Step 6: Run configure and source workflow regression tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_configure_auto_source.py tests/test_universal_wild_no_block_matrix.py tests/test_source_autopilot.py tests/test_source_autopilot_cli.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit configure bridge**

```powershell
git add src/hsconfig/commands/configure.py src/hsconfig/cli_parser.py tests/test_configure_auto_source.py
git commit -m "feat: wire source autopilot into configure"
```

---

### Task 5: Prove ShadowPriest Strong Path And No-Default-Only Boundary

**Files:**
- Modify: `tests/test_configure_auto_source.py`
- Modify: `tests/fixtures/source_search_shadowpriest_2026.json`

**Interfaces:**
- Consumes: full configure output from Task 4.
- Produces: regression proof that ShadowPriest source-autopilot does not fall back to default-only and does not keep Darkbishop.

- [ ] **Step 1: Extend the ShadowPriest fixture with enough guide-backed lowerable claims**

In `tests/fixtures/source_search_shadowpriest_2026.json`, add these claims to the existing `claims` list:

```json
        {
          "claim_kind": "card_role",
          "cards": ["TOY_381"],
          "stance": "early_board_pressure",
          "evidence_text_short": "Papercraft Angel is part of the cheap pressure mulligan plan.",
          "source_confidence": "high"
        },
        {
          "claim_kind": "card_role",
          "cards": ["SCH_514"],
          "stance": "reload_after_pressure",
          "evidence_text_short": "Raise Dead supports aggressive refill after cheap minions are used.",
          "source_confidence": "high"
        },
        {
          "claim_kind": "card_role",
          "cards": ["GVG_009"],
          "stance": "face_damage_pressure",
          "evidence_text_short": "Shadowbomber belongs to the cheap face damage pressure plan.",
          "source_confidence": "high"
        }
```

- [ ] **Step 2: Add an assertion for strong source semantics when fixture is complete**

In `tests/test_configure_auto_source.py`, extend `test_configure_auto_source_feeds_source_documents_into_package`:

```python
    assert operator["semantic_status"] == "SOURCE_BACKED_STRONG"
    assert operator["source_claim_quality_summary"]["source_quality_lane_counts"]["guide_backed"] > 0
    assert operator["guide_strength_summary"]["guide_backed_cards"] > 0
```

- [ ] **Step 3: Add explicit Darkbishop runtime-effect assertion**

In the same test, after the Mulligan assertion add:

```python
    darkbishop = json.loads((out / "04_package" / "CustomConfig" / "shadowpriest" / "BAR_735.json").read_text(encoding="utf-8"))
    assert "BeforeUseHeroPowerBonus" in json.dumps(darkbishop)
```

If the generated card file is named with a different current Darkbishop card ID, inspect the package card map once, then use that exact card ID consistently in the fixture and assertion. Do not support both IDs in the test; the fixture must use the canonical current card ID for this deck.

- [ ] **Step 4: Run the ShadowPriest proof test**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_configure_auto_source.py::test_configure_auto_source_feeds_source_documents_into_package -q
```

Expected: PASS with `semantic_status == "SOURCE_BACKED_STRONG"` and no Darkbishop mulligan keep.

- [ ] **Step 5: Run source and contract sentinel tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_configure_auto_source.py tests/test_source_contract_conformance.py tests/test_surface_authority_split.py tests/test_source_claim_family_registry.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit ShadowPriest strong proof**

```powershell
git add tests/test_configure_auto_source.py tests/fixtures/source_search_shadowpriest_2026.json
git commit -m "test: prove shadowpriest source autopilot strong path"
```

---

### Task 6: Add Representative No-Block Matrix For Source Autopilot

**Files:**
- Modify: `tests/test_source_autopilot.py`
- Modify: `tests/fixtures/source_search_decklist_only.json`

**Interfaces:**
- Consumes: source-autopilot report from Task 2.
- Produces: visible no-block contract for decks with thin or partial public source records.

- [ ] **Step 1: Add a matrix test for strong, decklist-only, and no-record cases**

Append to `tests/test_source_autopilot.py`:

```python
def test_source_autopilot_never_blocks_config_creation_for_thin_or_empty_sources():
    thin_payload = _fixture("source_search_decklist_only.json")
    deck_identity = {
        "deck_name": "ThinDeck",
        "deck_code_hash": "sha256:thin",
        "deck_slug": "thindeck",
        "cards": [{"card_id": "CARD_001", "name": "Fixture Card", "cost": 1, "count": 2}],
    }

    thin_bundle = build_source_autopilot_bundle(
        deck_name="ThinDeck",
        deck_identity=deck_identity,
        source_search_records=thin_payload["records"],
        current_date="2026-07-15",
    )
    empty_bundle = build_source_autopilot_bundle(
        deck_name="ThinDeck",
        deck_identity=deck_identity,
        source_search_records=[],
        current_date="2026-07-15",
    )

    assert thin_bundle["source_autopilot_report"]["status"] == "OK"
    assert empty_bundle["source_autopilot_report"]["status"] == "OK"
    assert thin_bundle["source_autopilot_report"]["strong_candidate"] is False
    assert empty_bundle["source_autopilot_report"]["first_missing_source_action"] == "add_current_deck_guide_or_mulligan_guide"
```

- [ ] **Step 2: Run source-autopilot no-block tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_source_autopilot.py -q
```

Expected: PASS.

- [ ] **Step 3: Commit no-block source-autopilot matrix**

```powershell
git add tests/test_source_autopilot.py tests/fixtures/source_search_decklist_only.json
git commit -m "test: cover source autopilot no-block lanes"
```

---

### Task 7: Update Operator Docs And Skill Boundary

**Files:**
- Modify: `docs/operator/README.md`
- Modify: `docs/operator/source-builder-workflow.md`
- Modify: `docs/operator/autonomous-source-builder-next.md`
- Modify: `docs/operator/guide-research-policy.md`

**Interfaces:**
- Consumes: CLI behavior from Tasks 3 and 4.
- Produces: one normal operator path and one inspected path with source-autopilot documented.

- [ ] **Step 1: Update normal operator README command block**

In `docs/operator/README.md`, add this after the existing `hsconfig configure` example:

```markdown
When current public source records are available, prefer the autopilot source path:

```powershell
hsconfig configure --deck-name "<DeckName>" --deck-code "<DeckCode>" --runtime-root "<HearthRangerRoot>" --out "outputs/<DeckName>" --auto-source --source-search-results-json "source_search_results.json" --json
```

`--auto-source` creates `02_source_autopilot/source_autopilot_report.json`, `source_evidence_rows.json`, and `source_documents.json` before the existing `research-deck` and `prepare` stages. It improves source strength and no-default-only visibility, but it does not create a second apply gate. Runtime apply still depends on `reports/operator_summary.json`.
```

- [ ] **Step 2: Update inspected source-builder workflow**

In `docs/operator/source-builder-workflow.md`, replace the first command ladder with:

```markdown
Inspected source-autopilot path:

```powershell
hsconfig source-manifest --deck-name "<DeckName>" --deck-code "<DeckCode>" --out "outputs/<DeckName>/01_manifest" --json
hsconfig source-autopilot --deck-name "<DeckName>" --deck-code "<DeckCode>" --source-search-results-json "source_search_results.json" --out "outputs/<DeckName>/02_source_autopilot" --json
hsconfig research-deck --deck-name "<DeckName>" --deck-code "<DeckCode>" --source-documents-json "outputs/<DeckName>/02_source_autopilot/source_documents.json" --out "outputs/<DeckName>/03_research" --json
hsconfig prepare --deck-name "<DeckName>" --deck-code "<DeckCode>" --runtime-root "<HearthRangerRoot>" --guide-sources-json "outputs/<DeckName>/03_research/guide_sources.json" --source-documents-json "outputs/<DeckName>/02_source_autopilot/source_documents.json" --out "outputs/<DeckName>/04_package" --json
```

Manual fallback remains `draft-source-documents --source-evidence-json` when the operator already has curated evidence rows and does not want source ranking.
```

- [ ] **Step 3: Update autonomous source builder status**

In `docs/operator/autonomous-source-builder-next.md`, add:

```markdown
Implemented boundary:

- HSConfig can now consume compact public source search records through `source-autopilot`.
- The command ranks current deck-matching guides above decklists and static card text.
- The command emits strict evidence rows and source documents for the existing contract pipeline.
- It does not browse the web by itself and does not store raw guide pages.
- Weak or missing sources stay non-blocking and visible through `first_missing_source_action`.
```

- [ ] **Step 4: Update guide research policy**

In `docs/operator/guide-research-policy.md`, add:

```markdown
`source-autopilot` claim-quality rule:

- `guide`, `mulligan_guide`, `matchup_guide`, and `guide_fixture` records may create guide-backed lowerable claims when the record is public HTTPS, current enough for the deck context, and card identity resolves to the current deck.
- `decklist`, `deck_snapshot`, `deck_code`, `metadata`, `card_text`, and `hearthstonejson_static_semantics` records may create visible source-informed or static semantic evidence, but they do not by themselves promote a package to `SOURCE_BACKED_STRONG`.
- A start-of-game/deckbuilding effect such as Darkbishop Benedictus may create a `hero_power_transform` claim and a high-priority runtime effect file. It must not create a `mulligan_keep` row unless the source explicitly says to keep that card in the opening hand.
```

- [ ] **Step 5: Run docs scan**

Run:

```powershell
rg -n "source-autopilot|--auto-source|SOURCE_BACKED_STRONG|Darkbishop" docs/operator
```

Expected: matches in the four edited docs and no text saying source strength blocks runtime apply.

- [ ] **Step 6: Commit docs**

```powershell
git add docs/operator/README.md docs/operator/source-builder-workflow.md docs/operator/autonomous-source-builder-next.md docs/operator/guide-research-policy.md
git commit -m "docs: document source autopilot workflow"
```

---

### Task 8: Final Verification, Current ShadowPriest Dry Run, And Git Hygiene

**Files:**
- No new code files.
- Verify generated output under a temporary ignored path such as `outputs/_verification_shadowpriest_autosource`.

**Interfaces:**
- Consumes: completed tasks 1-7.
- Produces: final evidence that tests pass, source-autopilot artifacts are written, ShadowPriest config is load-safe and guide-strong when source input is complete.

- [ ] **Step 1: Run focused source tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_source_autopilot.py tests/test_source_autopilot_cli.py tests/test_configure_auto_source.py -q
```

Expected: PASS.

- [ ] **Step 2: Run contract and no-block tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_source_contract_conformance.py tests/test_surface_authority_split.py tests/test_source_claim_family_registry.py tests/test_universal_wild_no_block_matrix.py -q
```

Expected: PASS.

- [ ] **Step 3: Run broader suite**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest -q
```

Expected: PASS. If runtime exceeds local shell timeout, rerun with a longer command timeout and record the last completed test module plus the timeout boundary in the final implementation summary.

- [ ] **Step 4: Run a local ShadowPriest auto-source dry run**

Run with a runtime root that exists on the machine:

```powershell
$env:PYTHONPATH='src'; python -m hsconfig configure --deck-name "ShadowPriest" --deck-code "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=" --runtime-root "<HearthRangerRoot>" --out "outputs/_verification_shadowpriest_autosource" --auto-source --source-search-results-json "tests/fixtures/source_search_shadowpriest_2026.json" --json
```

Expected:

- Exit code `0`.
- `outputs/_verification_shadowpriest_autosource/02_source_autopilot/source_autopilot_report.json` exists.
- `outputs/_verification_shadowpriest_autosource/04_package/reports/operator_summary.json` has `technical_status=VALID_PACKAGE`.
- `default_only_runtime_surfaces=[]`.
- `Mulligan.json` does not contain the Darkbishop card ID.

- [ ] **Step 5: Inspect git status**

Run:

```powershell
git status --short --branch
```

Expected: only intentional commits ahead of `origin/main`, or clean if commits were pushed by the implementation worker.

- [ ] **Step 6: Push only after tests pass**

Run:

```powershell
git push origin main
```

Expected: push succeeds. If branch protection rejects direct push, create a `codex/source-backed-strong-autopilot` branch and open a PR instead.

---

## Implementation Notes

- The source-autopilot module must remain deterministic. Live web searching is outside the module so tests are stable and the CLI works offline with captured source records.
- The source-search fixture stores structured claims, not copied long guide text. Keep quotes short and prefer paraphrased `evidence_text_short`.
- `source_autopilot_report.strong_candidate` is a preflight signal, not the final strong verdict. The final `SOURCE_BACKED_STRONG` verdict still comes from the existing `prepare` reports.
- If a deck has no good sources, HSConfig must still produce a valid load-safe package through existing policy-backed/static-semantic paths. The autopilot report must expose `first_missing_source_action`.
- If ShadowPriest uses a different canonical Darkbishop card ID in current card data, normalize the fixture to that card ID and keep one canonical ID throughout the tests.

## Self-Review Checklist

- Spec coverage:
  - Source-/Contract-Logik: Tasks 1-5 feed existing strict source-document and contract reports.
  - No default-only hidden success: Tasks 4-6 assert visible non-blocking lanes and default-only absence on ShadowPriest.
  - ShadowPriest Darkbishop split: Tasks 1 and 5 assert effect preserved and mulligan keep removed.
  - Autonomous but schmal: Tasks 2-4 add one pure module, one CLI command, one configure bridge.
  - `SOURCE_BACKED_STRONG` truth: Tasks 5 and 8 verify strong only through existing operator summary.
  - Any-deck no-block behavior: Task 6 preserves weak-source load-safe behavior.
- Placeholder scan: no banned placeholder phrases or unspecified validation steps are used.
- Type consistency:
  - `rank_public_sources`, `extract_source_evidence_rows`, and `build_source_autopilot_bundle` signatures are identical in tests and implementation steps.
  - CLI files all use `source_search_results_json`, `auto_source`, and `source_autopilot_payload` consistently.
  - Output file names are stable across CLI tests, configure tests, docs, and verification commands.

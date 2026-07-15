# HSConfig Source-Backed Evidence Harvester Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a compact Source Evidence Closure layer so HSConfig always generates a valid deck config, never hides default-only behavior, and only labels a deck or surface `SOURCE_BACKED_STRONG` when the full source-to-runtime chain is genuinely proven.

**Architecture:** Keep the existing HSConfig pipeline intact: `configure` -> source acquisition/autopilot -> source documents -> research/prepare -> package reports -> operator summary. Add one focused evidence policy module and thread its decisions into source acquisition, source autopilot, source-to-runtime explainability, and operator summaries. Do not add another apply authority, do not make source strength block package generation, and do not rewrite the runtime writer.

**Tech Stack:** Python, argparse CLI, JSON report artifacts, pytest, existing HSConfig package builders, no new runtime dependencies.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig`.
- Keep generation non-blocking: every technically valid deck must still produce a load-safe package.
- `SOURCE_BACKED_STRONG` is an evidence/confidence label, not a runtime-apply gate.
- `operator_summary.json` remains the only normal operator/apply authority.
- Do not infer `mulligan_keep` from static card text, card importance, generic prose, or start-of-game effects.
- Preserve Darkbishop Benedictus / `SW_448` as `hero_power_transform` / Mind Spike effect semantics while keeping it out of opening-hand keeps unless an explicit opening-hand source exists.
- `decklist_only`, stats-only, snippet-only, `policy_fallback`, `default_runtime`, stale guide, weak static record, and generic low confidence must not promote to `SOURCE_BACKED_STRONG`.
- No hidden default-only runtime: every normal surface must be emitted, suppressed with reason, or reported with first missing link.
- No new external Python dependencies.
- Keep docs and installed skill in sync when workflow behavior changes.

---

## File Structure

- Create: `src/hsconfig/source_evidence_policy.py`
  - Single responsibility: classify evidence records into source lanes, trust ceilings, promotion blockers, and first missing source actions.
- Modify: `src/hsconfig/source_acquisition.py`
  - Use the shared evidence policy for `source_visibility`, source lane, deck match scope, and publication-year handling.
- Modify: `src/hsconfig/source_autopilot.py`
  - Replace local strong-lane promotion checks with the shared evidence policy while preserving existing report fields.
- Modify: `src/hsconfig/source_document_drafter.py`
  - Preserve evidence policy fields when drafting `source_documents.json`.
- Modify: `src/hsconfig/static_semantics.py`
  - Emit explicit static-semantics source records for card IDs, hero powers, mechanics, generated entities, and supported effect semantics.
- Modify: `src/hsconfig/source_to_runtime_explainability.py`
  - Add per-card/per-surface evidence-chain rows and first missing source links.
- Modify: `src/hsconfig/operator_summary.py`
  - Surface evidence closure summary without changing apply authority.
- Modify: `src/hsconfig/report_ownership.py`
  - Register any new diagnostic report as diagnostic-only.
- Modify: `.agents/skills/hsconfig/SKILL.md`
  - Update operator instructions after behavior changes.
- Modify: `docs/operator/guide-research-policy.md`
  - Document evidence lanes and the exact `SOURCE_BACKED_STRONG` contract.
- Modify: `docs/operator/README.md`
  - Document the operator path for source closure.
- Test: `tests/test_source_evidence_policy.py`
- Test: `tests/test_source_acquisition_strong_closure.py`
- Test: `tests/test_source_autopilot.py`
- Test: `tests/test_source_document_drafter.py`
- Test: `tests/test_static_semantics_source_records.py`
- Test: `tests/test_source_to_runtime_explainability.py`
- Test: `tests/test_operator_summary.py`
- Test: `tests/test_archetype_fixture_matrix.py`
- Test: `tests/test_universal_wild_no_block_matrix.py`
- Test: `tests/test_shadowpriest_depth_e2e.py`
- Test: `tests/test_skill_files.py`

---

### Task 1: Shared Evidence Policy Module

**Files:**
- Create: `src/hsconfig/source_evidence_policy.py`
- Test: `tests/test_source_evidence_policy.py`

**Interfaces:**
- Produces: `classify_source_evidence(record: Mapping[str, Any], *, deck_name: str, current_date: str | date | None) -> dict[str, Any]`
- Produces keys: `source_visibility`, `source_lane`, `source_rank_lane`, `deck_match_scope`, `promotion_eligible`, `strong_promotion_eligible`, `trust_ceiling`, `promotion_blockers`, `first_missing_source_action`
- Consumed by: `source_acquisition.py`, `source_autopilot.py`, `source_document_drafter.py`

- [ ] **Step 1: Write failing tests for source lanes and blockers**

Add this test file:

```python
# tests/test_source_evidence_policy.py
from datetime import date

from hsconfig.source_evidence_policy import classify_source_evidence


def test_current_full_text_deck_matched_guide_can_promote():
    row = classify_source_evidence(
        {
            "source_family": "public_guide",
            "source_title": "ShadowPriest Guide",
            "normalized_text": "ShadowPriest guide. Mulligan: keep Voidtouched Attendant and Mind Blast against slow decks. " * 4,
            "publication_year": 2026,
            "source_visibility": "full_text",
            "deck_match": {"deck_name": "ShadowPriest", "matched_card_ids": ["SW_448"]},
        },
        deck_name="ShadowPriest",
        current_date=date(2026, 7, 15),
    )

    assert row["source_visibility"] == "full_text"
    assert row["source_lane"] == "deck_matched_public_guide"
    assert row["source_rank_lane"] == "guide_current_deck_match"
    assert row["promotion_eligible"] is True
    assert row["strong_promotion_eligible"] is True
    assert row["promotion_blockers"] == []
    assert row["first_missing_source_action"] == "none"


def test_decklist_stats_snippet_policy_and_partial_records_never_promote():
    cases = [
        {"source_family": "decklist", "source_visibility": "decklist_only"},
        {"source_family": "stats", "source_visibility": "full_text"},
        {"source_family": "public_guide", "source_visibility": "snippet_only"},
        {"source_type": "policy_backed_autonomous_mulligan", "source_visibility": "full_text"},
        {
            "source_family": "public_guide",
            "source_visibility": "full_text",
            "source_record_strength": "partial",
        },
    ]

    for case in cases:
        row = classify_source_evidence(
            {
                **case,
                "source_title": "ShadowPriest",
                "normalized_text": "ShadowPriest guide text " * 20,
                "publication_year": 2026,
                "deck_match": {"deck_name": "ShadowPriest", "matched_card_ids": ["SW_448"]},
            },
            deck_name="ShadowPriest",
            current_date=date(2026, 7, 15),
        )

        assert row["promotion_eligible"] is False or row["strong_promotion_eligible"] is False
        assert row["first_missing_source_action"] != "none"


def test_retrieved_at_does_not_count_as_publication_year():
    row = classify_source_evidence(
        {
            "source_family": "public_guide",
            "source_title": "ShadowPriest Guide",
            "normalized_text": "ShadowPriest guide text " * 20,
            "retrieved_at": "2026-07-15T12:00:00Z",
            "source_visibility": "full_text",
            "deck_match": {"deck_name": "ShadowPriest", "matched_card_ids": ["SW_448"]},
        },
        deck_name="ShadowPriest",
        current_date=date(2026, 7, 15),
    )

    assert row["source_rank_lane"] != "guide_current_deck_match"
    assert "missing_publication_year" in row["promotion_blockers"]
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_source_evidence_policy.py -q
```

Expected: FAIL because `hsconfig.source_evidence_policy` does not exist.

- [ ] **Step 3: Implement the evidence policy module**

Create `src/hsconfig/source_evidence_policy.py` with this public function and constants:

```python
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Mapping


GUIDE_FAMILIES = {"guide", "public_guide", "community_guide"}
DECKLIST_FAMILIES = {"decklist", "decklist_only", "deck_aggregator"}
STATS_FAMILIES = {"stats", "statistical_enrichment", "hsreplay", "hsguru"}
STATIC_FAMILIES = {"hearthstonejson_static_semantics", "hearthstonejson", "official_card_data"}
NON_PROMOTING_SOURCE_TYPES = {
    "policy_backed_autonomous_mulligan",
    "default_runtime",
    "generated_default",
}


def classify_source_evidence(
    record: Mapping[str, Any],
    *,
    deck_name: str,
    current_date: str | date | None,
) -> dict[str, Any]:
    result = dict(record)
    family = _text(record.get("source_family") or record.get("source_type") or record.get("source_type_family")).lower()
    source_type = _text(record.get("source_type") or record.get("provenance")).lower()
    visibility = _source_visibility(record, family)
    deck_scope = _deck_match_scope(record, deck_name)
    publication_year = _publication_year(record)
    current_year = _current_year(current_date)
    source_rank_lane = _source_rank_lane(family, visibility, deck_scope, publication_year, current_year)
    source_lane = _source_lane(source_rank_lane, deck_scope)
    blockers = _promotion_blockers(
        record,
        family=family,
        source_type=source_type,
        visibility=visibility,
        deck_scope=deck_scope,
        publication_year=publication_year,
        current_year=current_year,
        source_rank_lane=source_rank_lane,
    )
    promotion_eligible = not blockers and family in GUIDE_FAMILIES

    result.update(
        {
            "source_visibility": visibility,
            "source_rank_lane": source_rank_lane,
            "source_lane": source_lane,
            "deck_match_scope": deck_scope,
            "publication_year": publication_year,
            "promotion_eligible": promotion_eligible,
            "strong_promotion_eligible": promotion_eligible and source_lane == "deck_matched_public_guide",
            "trust_ceiling": "source_backed_strong" if promotion_eligible else "source_informed_partial",
            "promotion_blockers": blockers,
            "first_missing_source_action": "none" if promotion_eligible else _first_missing_source_action(blockers),
        }
    )
    return result


def _source_visibility(record: Mapping[str, Any], family: str) -> str:
    explicit = _text(record.get("source_visibility")).lower()
    if explicit:
        return explicit
    if family in DECKLIST_FAMILIES:
        return "decklist_only"
    text = _text(record.get("normalized_text") or record.get("text"))
    if family in GUIDE_FAMILIES and len(text) >= 180:
        return "full_text"
    if family in GUIDE_FAMILIES and text:
        return "snippet_only"
    return "unknown"


def _deck_match_scope(record: Mapping[str, Any], deck_name: str) -> str:
    explicit = _text(record.get("deck_match_scope")).lower()
    if explicit:
        return explicit
    match = record.get("deck_match", {})
    if not isinstance(match, Mapping):
        return "unknown"
    declared = _norm(match.get("deck_name"))
    matched_ids = match.get("matched_card_ids", [])
    has_overlap = isinstance(matched_ids, list) and bool(matched_ids)
    source_text = _norm(f"{record.get('source_title', '')} {record.get('normalized_text', '')}")
    if declared == _norm(deck_name) and (has_overlap or _norm(deck_name) in source_text):
        return "deck_or_archetype_matched"
    return "unknown"


def _source_rank_lane(
    family: str,
    visibility: str,
    deck_scope: str,
    publication_year: int | None,
    current_year: int | None,
) -> str:
    if family in DECKLIST_FAMILIES:
        return "decklist_only"
    if family in STATS_FAMILIES:
        return "statistical_enrichment"
    if family in STATIC_FAMILIES:
        return "static_semantics_only"
    if (
        family in GUIDE_FAMILIES
        and visibility == "full_text"
        and deck_scope in {"deck_matched", "deck_or_archetype_matched"}
        and current_year is not None
        and publication_year == current_year
    ):
        return "guide_current_deck_match"
    if family in GUIDE_FAMILIES and visibility == "full_text":
        return "guide_full_text_not_current"
    if family in GUIDE_FAMILIES:
        return "guide_not_full_text"
    return "source_unclassified"


def _source_lane(source_rank_lane: str, deck_scope: str) -> str:
    if source_rank_lane == "guide_current_deck_match" and deck_scope in {
        "deck_matched",
        "deck_or_archetype_matched",
    }:
        return "deck_matched_public_guide"
    return source_rank_lane or "unknown"


def _promotion_blockers(
    record: Mapping[str, Any],
    *,
    family: str,
    source_type: str,
    visibility: str,
    deck_scope: str,
    publication_year: int | None,
    current_year: int | None,
    source_rank_lane: str,
) -> list[str]:
    blockers: list[str] = []
    if record.get("promotion_eligible") is False:
        blockers.append("promotion_explicitly_disabled")
    if source_type in NON_PROMOTING_SOURCE_TYPES:
        blockers.append(f"non_promoting_source_type_{source_type}")
    if family in DECKLIST_FAMILIES:
        blockers.append("decklist_only_not_strong_evidence")
    if family in STATS_FAMILIES:
        blockers.append("stats_only_not_strong_evidence")
    if visibility != "full_text":
        blockers.append(f"source_visibility_{visibility}_not_strong")
    if deck_scope not in {"deck_matched", "deck_or_archetype_matched"}:
        blockers.append("deck_match_scope_not_strong")
    if publication_year is None:
        blockers.append("missing_publication_year")
    elif current_year is not None and publication_year != current_year:
        blockers.append("source_not_current_year")
    strength = _text(record.get("source_record_strength")).lower()
    if strength and strength != "candidate_strong":
        blockers.append(f"non_strong_source_record_strength_{strength}")
    if source_rank_lane != "guide_current_deck_match":
        blockers.append(f"source_rank_lane_{source_rank_lane}_not_strong")
    return sorted(set(blockers))


def _first_missing_source_action(blockers: list[str]) -> str:
    if "missing_publication_year" in blockers or "source_not_current_year" in blockers:
        return "add_current_publication_metadata_or_current_guide"
    if any(blocker.startswith("source_visibility_") for blocker in blockers):
        return "add_full_text_public_guide_source"
    if "deck_match_scope_not_strong" in blockers:
        return "add_deck_or_archetype_matched_source"
    return "add_current_deck_guide_or_mulligan_guide"


def _publication_year(record: Mapping[str, Any]) -> int | None:
    explicit = record.get("publication_year")
    if isinstance(explicit, int):
        return explicit
    published = _text(record.get("published_at") or record.get("publication_date") or record.get("published_date"))
    if len(published) >= 4 and published[:4].isdigit():
        return int(published[:4])
    return None


def _current_year(value: str | date | None) -> int | None:
    if isinstance(value, date):
        return value.year
    text = _text(value)
    if len(text) >= 4 and text[:4].isdigit():
        return int(text[:4])
    return datetime.utcnow().year


def _text(value: Any) -> str:
    return str(value or "").strip()


def _norm(value: Any) -> str:
    return "".join(ch for ch in _text(value).lower() if ch.isalnum())
```

- [ ] **Step 4: Run tests and verify pass**

Run:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_source_evidence_policy.py -q
```

Expected: `3 passed`.

- [ ] **Step 5: Commit**

```powershell
git add src/hsconfig/source_evidence_policy.py tests/test_source_evidence_policy.py
git commit -m "feat: add source evidence policy classifier"
```

---

### Task 2: Thread Evidence Policy Through Acquisition, Autopilot, and Drafting

**Files:**
- Modify: `src/hsconfig/source_acquisition.py`
- Modify: `src/hsconfig/source_autopilot.py`
- Modify: `src/hsconfig/source_document_drafter.py`
- Test: `tests/test_source_acquisition_strong_closure.py`
- Test: `tests/test_source_autopilot.py`
- Test: `tests/test_source_document_drafter.py`

**Interfaces:**
- Consumes: `classify_source_evidence(...)`
- Produces: source search rows and drafted claims that preserve `promotion_eligible`, `source_record_strength`, `source_visibility`, `source_lane`, `source_rank_lane`, `deck_match_scope`, and `first_missing_source_action`

- [ ] **Step 1: Write regression tests for policy field preservation**

Add or extend tests with:

```python
def test_source_document_drafter_preserves_evidence_policy_fields(tmp_path):
    from hsconfig.source_document_drafter import draft_source_documents_payload

    evidence = tmp_path / "source_evidence.json"
    out = tmp_path / "out"
    evidence.write_text(
        """
        {
          "deck_name": "ShadowPriest",
          "evidence_rows": [
            {
              "source_family": "public_guide",
              "source_url": "https://example.test/shadow",
              "source_title": "ShadowPriest Guide",
              "claim_kind": "mulligan_keep",
              "card_mentions": ["Voidtouched Attendant"],
              "source_visibility": "full_text",
              "source_lane": "deck_matched_public_guide",
              "source_rank_lane": "guide_current_deck_match",
              "deck_match_scope": "deck_or_archetype_matched",
              "source_record_strength": "candidate_strong",
              "promotion_eligible": true,
              "evidence_text_short": "Mulligan: keep Voidtouched Attendant."
            }
          ]
        }
        """,
        encoding="utf-8",
    )

    payload, status = draft_source_documents_payload(
        deck_name="ShadowPriest",
        deck_code="AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=",
        source_evidence_json=str(evidence),
        out=str(out),
        cards_json=None,
        allow_placeholder=False,
    )

    assert status == 0
    claim = payload["source_documents"][0]["claims"][0]
    assert claim["promotion_eligible"] is True
    assert claim["source_record_strength"] == "candidate_strong"
    assert claim["source_visibility"] == "full_text"
    assert claim["source_lane"] == "deck_matched_public_guide"
    assert claim["deck_match_scope"] == "deck_or_archetype_matched"
```

Add an autopilot regression:

```python
def test_valid_strong_guide_is_not_vetoed_by_separate_partial_record(tmp_path):
    from hsconfig.source_autopilot import source_autopilot_payload

    source_search = tmp_path / "source_search.json"
    source_search.write_text(
        """
        {
          "sources": [
            {
              "source_family": "public_guide",
              "source_url": "https://example.test/strong",
              "source_title": "ShadowPriest Guide",
              "normalized_text": "ShadowPriest guide. Mulligan: keep Voidtouched Attendant. " ,
              "publication_year": 2026,
              "source_visibility": "full_text",
              "source_record_strength": "candidate_strong",
              "deck_match": {"deck_name": "ShadowPriest", "matched_card_ids": ["SW_448"]},
              "claims": [
                {
                  "claim_kind": "targeting_rule",
                  "cards": ["CORE_CS2_004"],
                  "runtime_block": {"BeforeUseCardBonus": 30},
                  "evidence_text_short": "Use burn to finish opponents."
                }
              ]
            },
            {
              "source_family": "public_guide",
              "source_url": "https://example.test/partial",
              "source_title": "ShadowPriest Note",
              "normalized_text": "ShadowPriest note. Mulligan hints exist.",
              "publication_year": 2026,
              "source_visibility": "snippet_only",
              "source_record_strength": "partial",
              "deck_match": {"deck_name": "ShadowPriest", "matched_card_ids": ["SW_448"]},
              "claims": [
                {
                  "claim_kind": "mulligan_keep",
                  "cards": ["CORE_CS2_004"],
                  "promotion_eligible": false,
                  "evidence_text_short": "Weak note."
                }
              ]
            }
          ]
        }
        """,
        encoding="utf-8",
    )

    payload, status = source_autopilot_payload(
        deck_name="ShadowPriest",
        deck_code="AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=",
        source_search_results_json=str(source_search),
        out=str(tmp_path / "out"),
        cards_json=None,
        allow_placeholder=False,
        current_date="2026-07-15",
    )

    assert status == 0
    assert payload["source_autopilot_report"]["strong_candidate"] is True
    assert payload["source_autopilot_report"]["non_promoting_claim_count"] >= 1
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_source_document_drafter.py tests/test_source_autopilot.py tests/test_source_acquisition_strong_closure.py -q
```

Expected: at least one failure until all policy fields are threaded consistently.

- [ ] **Step 3: Replace duplicated lane logic with policy module**

Modify:

```python
from hsconfig.source_evidence_policy import classify_source_evidence
```

Use it in:

- `source_acquisition.py` after parsing a source page and before writing a compact record.
- `source_autopilot.py` in `_source_base(...)` and strong-candidate evaluation.
- `source_document_drafter.py` in `_claim_from_row(...)` to preserve all policy fields.

Keep existing public JSON keys stable. Add new keys only; do not remove current report fields.

- [ ] **Step 4: Run task tests**

Run:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_source_document_drafter.py tests/test_source_autopilot.py tests/test_source_acquisition_strong_closure.py -q
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit**

```powershell
git add src/hsconfig/source_acquisition.py src/hsconfig/source_autopilot.py src/hsconfig/source_document_drafter.py tests/test_source_acquisition_strong_closure.py tests/test_source_autopilot.py tests/test_source_document_drafter.py
git commit -m "feat: thread evidence policy through source autopilot"
```

---

### Task 3: Build-Pinned Static Semantics Source Records

**Files:**
- Modify: `src/hsconfig/static_semantics.py`
- Test: `tests/test_static_semantics_source_records.py`
- Test: `tests/test_claim_kind_runtime_contract.py`
- Fixture: `tests/fixtures/hearthstonejson_shadowpriest_cards.json`

**Interfaces:**
- Produces: `build_static_semantics_source_records(deck_identity: Mapping[str, Any], cards_by_id: Mapping[str, Any], *, build_id: str | None) -> list[dict[str, Any]]`
- Consumed by: source research/build steps that need static card semantics as evidence records.

- [ ] **Step 1: Write failing tests for static source records**

Create:

```python
# tests/test_static_semantics_source_records.py
import json
from pathlib import Path

from hsconfig.static_semantics import build_static_semantics_source_records


def test_hearthstonejson_static_records_support_darkbishop_effect_not_mulligan():
    cards = json.loads(
        Path("tests/fixtures/hearthstonejson_shadowpriest_cards.json").read_text(
            encoding="utf-8"
        )
    )
    cards_by_id = {card["id"]: card for card in cards}
    deck_identity = {
        "deck_name": "ShadowPriest",
        "cards": [{"card_id": "SW_448", "name": "Darkbishop Benedictus", "count": 1}],
    }

    records = build_static_semantics_source_records(
        deck_identity,
        cards_by_id,
        build_id="latest-resolved-test-build",
    )

    darkbishop_claims = [
        claim
        for record in records
        for claim in record["claims"]
        if "SW_448" in claim.get("cards", [])
    ]
    assert any(claim["claim_kind"] == "hero_power_transform" for claim in darkbishop_claims)
    assert not any(claim["claim_kind"] == "mulligan_keep" for claim in darkbishop_claims)
    assert all(record["source_family"] == "hearthstonejson_static_semantics" for record in records)
    assert all(record["source_record_strength"] == "static_semantics" for record in records)
```

- [ ] **Step 2: Run test and verify failure**

Run:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_static_semantics_source_records.py -q
```

Expected: FAIL because `build_static_semantics_source_records` is missing or incomplete.

- [ ] **Step 3: Implement static record emission**

Add a function to `src/hsconfig/static_semantics.py`:

```python
def build_static_semantics_source_records(
    deck_identity: Mapping[str, Any],
    cards_by_id: Mapping[str, Any],
    *,
    build_id: str | None,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for deck_card in deck_identity.get("cards", []):
        card_id = str(deck_card.get("card_id", ""))
        card = cards_by_id.get(card_id)
        if not isinstance(card, Mapping):
            continue
        claims = _static_claims_for_card(card_id, card)
        if not claims:
            continue
        records.append(
            {
                "source_family": "hearthstonejson_static_semantics",
                "source_type": "official_card_data",
                "source_title": f"HearthstoneJSON {build_id or 'unresolved-build'} {card_id}",
                "source_url": f"hearthstonejson://{build_id or 'unresolved-build'}/{card_id}",
                "source_visibility": "full_text",
                "source_record_strength": "static_semantics",
                "promotion_eligible": True,
                "deck_name": deck_identity.get("deck_name", ""),
                "claims": claims,
            }
        )
    return records
```

Add `_static_claims_for_card(...)` so `SW_448` emits `hero_power_transform`, supported mechanics emit `mechanic_usage`, and no static card emits `mulligan_keep`.

- [ ] **Step 4: Run static tests**

Run:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_static_semantics_source_records.py tests/test_claim_kind_runtime_contract.py -q
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit**

```powershell
git add src/hsconfig/static_semantics.py tests/test_static_semantics_source_records.py tests/test_claim_kind_runtime_contract.py
git commit -m "feat: emit static semantics source records"
```

---

### Task 4: Per-Card Source-To-Runtime Closure Rows

**Files:**
- Modify: `src/hsconfig/source_to_runtime_explainability.py`
- Modify: `src/hsconfig/operator_summary.py`
- Test: `tests/test_source_to_runtime_explainability.py`
- Test: `tests/test_operator_summary.py`
- Test: `tests/test_universal_wild_no_block_matrix.py`

**Interfaces:**
- Produces: `evidence_chain` per card row with `source_lane`, `claim_kind`, `surface`, `runtime_file`, `resolution_reason`, `first_missing_link`, `first_missing_source_action`
- Produces: `operator_summary.source_evidence_closure_summary`

- [ ] **Step 1: Write failing closure-row tests**

Add:

```python
def test_explainability_includes_evidence_chain_for_each_card():
    from hsconfig.source_to_runtime_explainability import build_source_to_runtime_explainability_report

    report = build_source_to_runtime_explainability_report(
        {
            "card_rows": [
                {
                    "card_id": "SW_448",
                    "name": "Darkbishop Benedictus",
                    "claim_rows": [
                        {
                            "claim_kind": "hero_power_transform",
                            "source_lane": "official_static_semantics",
                            "surface": "cardid_behavior",
                            "runtime_files": ["SW_448.json"],
                            "first_missing_source_action": "none",
                        }
                    ],
                    "closure": {"lane": "static_semantics_backed", "default_only_risk": False},
                }
            ]
        }
    )

    row = report["card_rows"][0]
    assert row["card_id"] == "SW_448"
    assert row["evidence_chain"][0]["claim_kind"] == "hero_power_transform"
    assert row["evidence_chain"][0]["runtime_file"] == "SW_448.json"
    assert row["evidence_chain"][0]["resolution_reason"] == "static_semantics_backed"
```

Add operator-summary assertion:

```python
def test_operator_summary_reports_source_evidence_closure_summary():
    from hsconfig.operator_summary import _source_evidence_closure_summary

    summary = _source_evidence_closure_summary(
        {
            "card_rows": [
                {"closure": {"lane": "source_backed", "default_only_risk": False}},
                {"closure": {"lane": "policy_fallback", "default_only_risk": False}},
                {"closure": {"lane": "contract_gap", "default_only_risk": True}},
            ]
        }
    )

    assert summary["lane_counts"]["source_backed"] == 1
    assert summary["lane_counts"]["policy_fallback"] == 1
    assert summary["lane_counts"]["contract_gap"] == 1
    assert summary["default_only_risk_count"] == 1
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_source_to_runtime_explainability.py tests/test_operator_summary.py -q
```

Expected: FAIL until `evidence_chain` and summary helper exist.

- [ ] **Step 3: Implement evidence-chain projection**

In `source_to_runtime_explainability.py`, add evidence chain construction from existing claim rows. Use existing fields first; default missing values to visible strings:

```python
def _evidence_chain(row: Mapping[str, Any]) -> list[dict[str, Any]]:
    chains: list[dict[str, Any]] = []
    for claim in _as_list(row.get("claim_rows")):
        if not isinstance(claim, Mapping):
            continue
        runtime_files = _as_list(claim.get("runtime_files"))
        if not runtime_files:
            runtime_files = _as_list(row.get("runtime_files"))
        for runtime_file in runtime_files or ["missing_runtime_surface"]:
            chains.append(
                {
                    "claim_kind": str(claim.get("claim_kind", "unknown")),
                    "source_lane": str(claim.get("source_lane", "unknown")),
                    "surface": str(claim.get("surface", "unknown")),
                    "runtime_file": str(runtime_file),
                    "resolution_reason": str(row.get("closure", {}).get("lane", "unknown")),
                    "first_missing_link": row.get("closure", {}).get("first_missing_link"),
                    "first_missing_source_action": str(
                        claim.get("first_missing_source_action")
                        or row.get("first_missing_source_action")
                        or "none"
                    ),
                }
            )
    return chains
```

In `operator_summary.py`, add:

```python
def _source_evidence_closure_summary(report: dict[str, Any]) -> dict[str, Any]:
    lane_counts: dict[str, int] = {}
    default_only_risk_count = 0
    for row in report.get("card_rows", []):
        if not isinstance(row, dict):
            continue
        closure = row.get("closure", {})
        if not isinstance(closure, dict):
            continue
        lane = str(closure.get("lane", "unknown"))
        lane_counts[lane] = lane_counts.get(lane, 0) + 1
        if closure.get("default_only_risk") is True:
            default_only_risk_count += 1
    return {
        "lane_counts": dict(sorted(lane_counts.items())),
        "default_only_risk_count": default_only_risk_count,
    }
```

- [ ] **Step 4: Run closure tests**

Run:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_source_to_runtime_explainability.py tests/test_operator_summary.py tests/test_universal_wild_no_block_matrix.py -q
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit**

```powershell
git add src/hsconfig/source_to_runtime_explainability.py src/hsconfig/operator_summary.py tests/test_source_to_runtime_explainability.py tests/test_operator_summary.py tests/test_universal_wild_no_block_matrix.py
git commit -m "feat: expose per-card source evidence closure"
```

---

### Task 5: Representative Deck Closure Matrix

**Files:**
- Modify: `docs/operator/archetype-fixture-matrix.json`
- Modify: `docs/operator/source-backed-strong-closure.md`
- Test: `tests/test_archetype_fixture_matrix.py`
- Test: `tests/test_archetype_fixture_e2e.py`
- Test: `tests/test_archetype_source_fixtures.py`

**Interfaces:**
- Consumes: existing 11 representative decks.
- Produces: exact current expected status and first missing action for each deck.

- [ ] **Step 1: Write matrix expectations**

Update `tests/test_archetype_fixture_matrix.py` so the 11-deck matrix explicitly expects:

```python
EXPECTED_FIRST_MISSING_ACTION = {
    "ShadowPriest": "none",
    "BigShaman": "none",
    "PirateRogue": "none",
    "MechPala": "none",
    "ImbueMage": "none",
    "CtAPaladin": "add_explicit_mulligan_source",
    "Discolock": "add_explicit_mulligan_source",
    "TreantDruid": "add_card_specific_source_claim",
    "Kingslayer": "add_mulligan_keep_or_discard_claim",
    "Boarlock": "add_mulligan_keep_or_discard_claim",
    "PirateDH": "add_card_specific_source_claim",
}
```

Also assert each row has:

```python
assert row["runtime_apply_allowed"] is True
assert row["default_only_runtime_surfaces"] == []
assert row["first_missing_source_action"] == EXPECTED_FIRST_MISSING_ACTION[row["deck_name"]]
```

- [ ] **Step 2: Run matrix tests and verify failure**

Run:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_archetype_fixture_matrix.py tests/test_archetype_fixture_e2e.py tests/test_archetype_source_fixtures.py -q
```

Expected: FAIL until docs matrix and fixture reports align.

- [ ] **Step 3: Update matrix docs**

Update `docs/operator/archetype-fixture-matrix.json` and `docs/operator/source-backed-strong-closure.md` so each representative deck row says one of:

- `SOURCE_BACKED_STRONG`
- `SOURCE_BACKED_PARTIAL`
- `SOURCE_INFORMED_VALID`

Do not promote a deck solely because it has a current decklist, stats page, or static semantics.

- [ ] **Step 4: Run matrix tests**

Run:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_archetype_fixture_matrix.py tests/test_archetype_fixture_e2e.py tests/test_archetype_source_fixtures.py -q
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit**

```powershell
git add docs/operator/archetype-fixture-matrix.json docs/operator/source-backed-strong-closure.md tests/test_archetype_fixture_matrix.py tests/test_archetype_fixture_e2e.py tests/test_archetype_source_fixtures.py
git commit -m "docs: lock representative source closure matrix"
```

---

### Task 6: Configure/Operator Integration Without New Apply Authority

**Files:**
- Modify: `src/hsconfig/commands/configure.py`
- Modify: `src/hsconfig/report_ownership.py`
- Modify: `src/hsconfig/output_ownership_manifest.py`
- Test: `tests/test_configure_auto_source.py`
- Test: `tests/test_output_ownership_manifest.py`
- Test: `tests/test_apply_authority_boundary.py`

**Interfaces:**
- Produces report: `reports/source_evidence_closure.json`
- Keeps authority: `diagnostic_only`

- [ ] **Step 1: Write failing configure ownership tests**

Add:

```python
def test_configure_writes_source_evidence_closure_as_diagnostic_only(tmp_path):
    # Use the existing configure helper pattern in this file.
    result = _run_configure_shadowpriest_auto_source(tmp_path)
    report = result.out / "04_package" / "reports" / "source_evidence_closure.json"
    ownership = result.out / "04_package" / "reports" / "output_ownership_manifest.json"

    assert report.exists()
    manifest = json.loads(ownership.read_text(encoding="utf-8"))
    row = next(item for item in manifest["artifacts"] if item["path"] == "reports/source_evidence_closure.json")
    assert row["authority"] == "diagnostic_only"
```

Extend apply boundary test:

```python
def test_active_apply_paths_do_not_consume_source_evidence_closure():
    content = Path("src/hsconfig/runtime_apply.py").read_text(encoding="utf-8")
    assert "source_evidence_closure" not in content
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_configure_auto_source.py tests/test_output_ownership_manifest.py tests/test_apply_authority_boundary.py -q
```

Expected: FAIL until the report and ownership entry exist.

- [ ] **Step 3: Write diagnostic report during package build**

In `configure.py`, after package reports are built and before final ownership refresh, write `reports/source_evidence_closure.json` from the existing `source_to_runtime_explainability_report` and operator summary:

```python
source_evidence_closure = {
    "schema_version": 1,
    "authority": "diagnostic_only",
    "deck_name": args.deck_name,
    "semantic_status": operator_summary.get("semantic_status"),
    "default_only_runtime_surfaces": operator_summary.get("default_only_runtime_surfaces", []),
    "source_to_runtime_summary": operator_summary.get("source_to_runtime_explainability_summary", {}),
    "source_evidence_closure_summary": operator_summary.get("source_evidence_closure_summary", {}),
}
write_json(package_reports_dir / "source_evidence_closure.json", source_evidence_closure)
```

Register `reports/source_evidence_closure.json` as `diagnostic_only` in report ownership.

- [ ] **Step 4: Run integration tests**

Run:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_configure_auto_source.py tests/test_output_ownership_manifest.py tests/test_apply_authority_boundary.py -q
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit**

```powershell
git add src/hsconfig/commands/configure.py src/hsconfig/report_ownership.py src/hsconfig/output_ownership_manifest.py tests/test_configure_auto_source.py tests/test_output_ownership_manifest.py tests/test_apply_authority_boundary.py
git commit -m "feat: add diagnostic source evidence closure report"
```

---

### Task 7: ShadowPriest Canary And Skill/Docs Sync

**Files:**
- Modify: `.agents/skills/hsconfig/SKILL.md`
- Modify: `docs/operator/guide-research-policy.md`
- Modify: `docs/operator/README.md`
- Test: `tests/test_shadowpriest_depth_e2e.py`
- Test: `tests/test_skill_files.py`

**Interfaces:**
- Consumes: source evidence closure outputs.
- Produces: operator docs and skill text aligned to the new closure report.

- [ ] **Step 1: Strengthen ShadowPriest canary**

Extend `tests/test_shadowpriest_depth_e2e.py` with assertions:

```python
def test_shadowpriest_darkbishop_effect_is_static_strong_but_not_mulligan_keep(tmp_path):
    result = _prepare_shadowpriest_package(tmp_path)
    mulligan = json.loads((result.out / "Mulligan.json").read_text(encoding="utf-8"))
    cardid = json.loads((result.out / "SW_448.json").read_text(encoding="utf-8"))
    closure = json.loads(
        (result.out / "reports" / "source_to_runtime_explainability.json").read_text(
            encoding="utf-8"
        )
    )

    assert "SW_448" not in json.dumps(mulligan)
    assert "BeforeUseHeroPowerBonus" in json.dumps(cardid)
    row = next(item for item in closure["card_rows"] if item["card_id"] == "SW_448")
    assert any(chain["claim_kind"] == "hero_power_transform" for chain in row["evidence_chain"])
    assert not any(chain["claim_kind"] == "mulligan_keep" for chain in row["evidence_chain"])
```

- [ ] **Step 2: Run canary and verify failure or current pass**

Run:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_shadowpriest_depth_e2e.py -q
```

Expected: PASS if Task 4 already exposed `evidence_chain`; otherwise FAIL until docs and report integration are complete.

- [ ] **Step 3: Update docs and installed skill source**

Update `.agents/skills/hsconfig/SKILL.md`, `docs/operator/guide-research-policy.md`, and `docs/operator/README.md` with these exact policies:

- Static semantics can prove card identity, mechanics, Hero Powers, generated entities, and supported deterministic effects.
- Static semantics cannot prove mulligan keeps, combo ordering, matchup plan, or priority.
- `source_evidence_closure.json` and `source_to_runtime_explainability.json` are diagnostic-only.
- `operator_summary.json` remains the only normal apply authority.
- Every deck generates when technically valid; source weakness changes semantic status, not generation.

- [ ] **Step 4: Sync installed skill and run docs tests**

Run:

```powershell
$env:PYTHONPATH='src'
python scripts/sync_installed_skill.py
python -m pytest tests/test_skill_files.py tests/test_shadowpriest_depth_e2e.py -q
```

Expected: all selected tests pass and installed skill sync succeeds.

- [ ] **Step 5: Commit**

```powershell
git add .agents/skills/hsconfig/SKILL.md docs/operator/guide-research-policy.md docs/operator/README.md tests/test_shadowpriest_depth_e2e.py tests/test_skill_files.py
git commit -m "docs: document source evidence closure policy"
```

---

### Task 8: Final Verification And Merge Readiness

**Files:**
- Verify only unless tests reveal a defect.

**Interfaces:**
- Consumes all previous tasks.
- Produces merge-ready branch with clean status.

- [ ] **Step 1: Run focused source/contract suite**

Run:

```powershell
$env:PYTHONPATH='src'
$env:PYTHONDONTWRITEBYTECODE='1'
python -m pytest -q -p no:cacheprovider `
  tests/test_source_evidence_policy.py `
  tests/test_source_acquisition_strong_closure.py `
  tests/test_source_autopilot.py `
  tests/test_source_document_drafter.py `
  tests/test_static_semantics_source_records.py `
  tests/test_source_to_runtime_explainability.py `
  tests/test_operator_summary.py `
  tests/test_universal_wild_no_block_matrix.py `
  tests/test_shadowpriest_depth_e2e.py
```

Expected: all selected tests pass.

- [ ] **Step 2: Run representative deck suite**

Run:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_archetype_fixture_matrix.py tests/test_archetype_fixture_e2e.py tests/test_archetype_source_fixtures.py tests/test_output_competence_matrix.py -q
```

Expected: all selected tests pass.

- [ ] **Step 3: Run full suite**

Run:

```powershell
$env:PYTHONPATH='src'
python -m pytest -q
```

Expected: full suite passes with only existing skips.

- [ ] **Step 4: Verify skill sync**

Run:

```powershell
python scripts/sync_installed_skill.py --check
```

Expected: command exits `0` and reports the installed HSConfig skill is in sync.

- [ ] **Step 5: Check diff and status**

Run:

```powershell
git diff --check
git status --short --branch
```

Expected: `git diff --check` exits `0`; status shows the feature branch with no unstaged files after final commit.

- [ ] **Step 6: Commit final fixes if needed**

If any verification-only doc or test stabilization change was required:

```powershell
git add <changed-files>
git commit -m "test: verify source evidence closure"
```

Do not create an empty commit.

---

## Self-Review

**Spec coverage:** The plan covers source/contract correctness, no hidden default-only behavior, non-blocking deck generation, strict `SOURCE_BACKED_STRONG`, ShadowPriest/Darkbishop semantics, representative Wild decks, docs, skill sync, and verification.

**Placeholder scan:** The plan contains no `TBD`, no `TODO`, no unspecified edge-case instruction, and no unnamed tests.

**Type consistency:** The shared policy interface is defined in Task 1 and consumed by Tasks 2-4. The new diagnostic report is introduced in Task 6 and documented in Task 7. `operator_summary.json` remains the only apply authority in every task.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-15-hsconfig-source-backed-evidence-harvester-closure.md`.

Two execution options:

1. **Subagent-Driven (recommended)** - dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** - execute tasks in this session using executing-plans, batch execution with checkpoints.

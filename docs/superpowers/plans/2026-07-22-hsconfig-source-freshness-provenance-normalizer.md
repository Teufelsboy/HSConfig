# HSConfig Source Freshness Provenance Normalizer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a small diagnostic-only source freshness and provenance normalizer so HSConfig can honestly reach `SOURCE_BACKED_STRONG` when fetched full-text evidence is current or evergreen, while still generating load-safe configs for every valid deck.

**Architecture:** Keep the existing HSConfig pipeline and apply boundary intact. Add one pure provenance helper, wire its fields into source evidence/autopilot rows, and reuse the same normalized facts in research-result validation and contract-preflight summaries. No gameplay tuning, no log dependency, no new runtime surface, and no second apply gate.

**Tech Stack:** Python 3, pytest, existing HSConfig CLI, existing source-autopilot/source-contract modules.

## Global Constraints

- Work only in `C:\Users\darbo\Documents\HSConfig`.
- Do not use HSTuner or HearthRanger game logs for this change.
- `reports/operator_summary.json` remains the only normal apply authority.
- `SOURCE_BACKED_STRONG` remains an evidence-quality label, not a generation or apply gate.
- `source_status_apply_blocking` must remain `false` for source-quality diagnostics.
- A valid deck must still build a load-safe package when public source evidence is thin.
- No hidden default-only runtime: expected surfaces must be emitted, explicitly suppressed, or visible as diagnostic debt.
- Normal output must not emit `Presume.json`, `Concede.json`, or aggregate `CardBehavior.json`.
- Darkbishop Benedictus start-of-game/hero-power-transform effect must not become a Mulligan keep without explicit opening-hand evidence.
- Do not add new dependencies.
- Keep the installed skill in sync with the repo skill.
- Finish with a clean worktree. Commit and push the plan implementation branch if execution creates changes.

---

## File Structure

- Create `src/hsconfig/source_provenance.py`
  - One pure module that normalizes source visibility, deck identity match, freshness, current-or-evergreen reason, and diagnostic apply-blocking fields.
- Create `tests/test_source_provenance.py`
  - Unit tests for the normalizer without touching the CLI or runtime package builder.
- Modify `src/hsconfig/source_evidence_policy.py`
  - Reuse normalized provenance fields inside existing source evidence classification.
  - Preserve existing rank lanes and blockers.
- Modify `src/hsconfig/source_autopilot.py`
  - Carry normalized provenance fields from ranked sources into evidence rows and source-autopilot reports.
- Modify `src/hsconfig/research_result_validator.py`
  - Validate Strong research snapshots from the normalized top-level or nested provenance markers.
- Modify `src/hsconfig/research_result_contract.py`
  - Reuse the same current/evergreen helper so strict validation and contract classification do not drift.
- Modify `src/hsconfig/research_result_contract_sentinel.py`
  - Add diagnostic row fields and summary counts for missing freshness/provenance.
- Modify `src/hsconfig/contract_preflight.py`
  - Surface the new research-result sentinel summary counts in `research_context`.
- Modify `tests/test_source_autopilot.py`
  - Add focused tests proving provenance fields survive ranking and evidence-row extraction.
- Modify `tests/test_research_result_validator.py`
  - Add strict Strong acceptance/rejection tests for normalized nested provenance.
- Modify `tests/test_research_result_contract.py`
  - Add classification tests aligned with the strict validator.
- Modify `tests/test_research_result_contract_sentinel.py`
  - Add sentinel summary tests for freshness gaps.
- Modify `tests/test_contract_preflight.py`
  - Assert the new diagnostic counts exist and remain non-blocking.
- Modify `docs/operator/README.md`
  - Document the compact source freshness/provenance contract.
- Modify `docs/operator/universal-wild-no-block-contract.md`
  - Document that missing provenance prevents Strong only; it never blocks load-safe config generation.
- Modify `.agents/skills/hsconfig/SKILL.md`
  - Route operators to the normalized provenance fields and keep the no-block contract explicit.

---

### Task 1: Add Pure Source Provenance Normalizer

**Files:**
- Create: `src/hsconfig/source_provenance.py`
- Create: `tests/test_source_provenance.py`

**Interfaces:**
- Produces: `normalize_source_provenance(record: Mapping[str, Any], *, deck_name: str, deck_identity: Mapping[str, Any] | None = None, current_date: str | date | None = None) -> dict[str, Any]`
- Produces: `research_payload_provenance(payload: Mapping[str, Any]) -> dict[str, Any]`
- Consumed by later tasks: `source_evidence_policy.classify_source_evidence`, `research_result_validator.validate_research_result_payload`, and `research_result_contract.classify_research_result_contract`.

- [ ] **Step 1: Write the failing unit tests**

Create `tests/test_source_provenance.py` with:

```python
from __future__ import annotations

from hsconfig.source_provenance import (
    normalize_source_provenance,
    research_payload_provenance,
)


DECK_IDENTITY = {
    "deck_name": "ShadowPriest",
    "deck_code_hash": "sha256:shadow",
    "deck_slug": "shadowpriest",
    "format": "wild",
    "cards": [
        {"card_id": "SW_448", "name": "Darkbishop Benedictus", "count": 1},
        {"card_id": "SW_446", "name": "Voidtouched Attendant", "count": 2},
    ],
}


def test_current_full_text_public_guide_projects_current_provenance() -> None:
    result = normalize_source_provenance(
        {
            "source_url": "https://example.test/shadow-guide",
            "source_title": "ShadowPriest Guide 2026",
            "source_family": "guide",
            "source_visibility": "full_text",
            "publication_year": 2026,
            "deck_match": {
                "deck_name": "ShadowPriest",
                "matched_card_ids": ["SW_448", "SW_446"],
            },
        },
        deck_name="ShadowPriest",
        deck_identity=DECK_IDENTITY,
        current_date="2026-07-22",
    )

    assert result["source_visibility"] == "full_text"
    assert result["deck_identity_match"] is True
    assert result["deck_identity_match_basis"] == "deck_name_and_card_overlap"
    assert result["freshness_status"] == "current"
    assert result["current_or_evergreen"] is True
    assert result["current_or_evergreen_reason"] == "publication_year_matches_current_year"
    assert result["source_status_apply_blocking"] is False


def test_evergreen_wild_requires_wild_scope_and_card_overlap() -> None:
    result = normalize_source_provenance(
        {
            "source_url": "https://example.test/evergreen-shadow",
            "source_title": "Evergreen Wild Shadow Priest Guide",
            "source_family": "guide",
            "source_visibility": "full_text",
            "publication_year": 2023,
            "format_scope": "wild",
            "deck_match": {
                "deck_name": "ShadowPriest",
                "matched_card_ids": ["SW_448", "SW_446"],
            },
        },
        deck_name="ShadowPriest",
        deck_identity=DECK_IDENTITY,
        current_date="2026-07-22",
    )

    assert result["freshness_status"] == "evergreen"
    assert result["current_or_evergreen"] is True
    assert result["current_or_evergreen_reason"] == "wild_guide_with_card_overlap"


def test_decklist_only_is_visible_but_never_current_guide_provenance() -> None:
    result = normalize_source_provenance(
        {
            "source_url": "https://example.test/decklist",
            "source_family": "decklist_only",
            "deck_match": {
                "deck_name": "ShadowPriest",
                "matched_card_ids": ["SW_448", "SW_446"],
            },
        },
        deck_name="ShadowPriest",
        deck_identity=DECK_IDENTITY,
        current_date="2026-07-22",
    )

    assert result["source_visibility"] == "decklist_only"
    assert result["deck_identity_match"] is True
    assert result["freshness_status"] == "not_strategy_guide"
    assert result["current_or_evergreen"] is False
    assert result["current_or_evergreen_reason"] == "decklist_not_strategy_guide"
    assert result["source_status_apply_blocking"] is False


def test_research_payload_provenance_accepts_nested_current_marker() -> None:
    result = research_payload_provenance(
        {
            "source_strength": "exact_full_text_guide",
            "source_visibility": "full_text",
            "guide_sources": [
                {
                    "source_freshness_lane": "guide_current_deck_match",
                    "current_or_evergreen_reason": "publication_year_matches_current_year",
                }
            ],
        }
    )

    assert result["freshness_status"] == "current"
    assert result["current_or_evergreen"] is True
    assert result["current_or_evergreen_reason"] == "publication_year_matches_current_year"
    assert result["source_status_apply_blocking"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_source_provenance.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'hsconfig.source_provenance'`.

- [ ] **Step 3: Implement the normalizer**

Create `src/hsconfig/source_provenance.py` with:

```python
from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from typing import Any


GUIDE_FAMILIES = {
    "guide",
    "public_guide",
    "community_guide",
    "mulligan_guide",
    "matchup_guide",
    "guide_fixture",
}
DECKLIST_FAMILIES = {
    "decklist",
    "decklist_only",
    "deck_aggregator",
    "deck_snapshot",
    "deck_code",
}
STATIC_FAMILIES = {
    "official_static_semantics",
    "blizzard_card_library",
    "hearthstonejson_static_semantics",
    "hearthstonejson",
    "official_card_data",
    "static_semantics",
    "metadata",
    "card_text",
}
CURRENT_MARKERS = {
    "current",
    "current_deck",
    "current_full_text",
    "current_or_evergreen",
    "same_year",
}
EVERGREEN_MARKERS = {
    "evergreen",
    "evergreen_wild",
    "evergreen_wild_archetype",
    "guide_evergreen_wild_archetype",
}
CURRENT_OR_EVERGREEN_RANK_LANES = {
    "guide_current_deck_match",
    "guide_evergreen_wild_archetype",
}
EVERGREEN_WILD_MAX_AGE_YEARS = 10
EVERGREEN_WILD_MIN_MATCHED_CARDS = 2


def normalize_source_provenance(
    record: Mapping[str, Any],
    *,
    deck_name: str,
    deck_identity: Mapping[str, Any] | None = None,
    current_date: str | date | None = None,
) -> dict[str, Any]:
    family = _source_family(record)
    visibility = _source_visibility(record, family)
    publication_year = _publication_year(record)
    current_year = _current_year(current_date)
    deck_match = _deck_identity_match(record, deck_name)
    freshness_status, reason = _freshness_status(
        record,
        family=family,
        publication_year=publication_year,
        current_year=current_year,
        visibility=visibility,
    )
    return {
        "source_visibility": visibility,
        "deck_identity_match": deck_match["matched"],
        "deck_identity_match_basis": deck_match["basis"],
        "freshness_status": freshness_status,
        "current_or_evergreen": freshness_status in {"current", "evergreen"},
        "current_or_evergreen_reason": reason,
        "source_status_apply_blocking": False,
    }


def research_payload_provenance(payload: Mapping[str, Any]) -> dict[str, Any]:
    top_level_status = _normalized_marker(payload.get("freshness_status"))
    if top_level_status in CURRENT_MARKERS:
        return _provenance_result("current", _reason(payload, "top_level_current"))
    if top_level_status in EVERGREEN_MARKERS:
        return _provenance_result("evergreen", _reason(payload, "top_level_evergreen"))
    if _truthy(payload.get("current_or_evergreen")):
        return _provenance_result("current", _reason(payload, "top_level_current_or_evergreen"))
    if _truthy(payload.get("evergreen_wild_archetype")):
        return _provenance_result("evergreen", _reason(payload, "top_level_evergreen_wild_archetype"))

    for row in _nested_rows(payload):
        marker = _normalized_marker(row.get("freshness_status"))
        lane = _normalized_marker(row.get("source_freshness_lane") or row.get("source_rank_lane"))
        if marker in CURRENT_MARKERS or lane in CURRENT_MARKERS or lane == "guide_current_deck_match":
            return _provenance_result("current", _reason(row, "nested_current_marker"))
        if marker in EVERGREEN_MARKERS or lane in EVERGREEN_MARKERS:
            return _provenance_result("evergreen", _reason(row, "nested_evergreen_marker"))
        if _truthy(row.get("current_or_evergreen")):
            return _provenance_result("current", _reason(row, "nested_current_or_evergreen"))
        if _truthy(row.get("evergreen_wild_archetype")):
            return _provenance_result("evergreen", _reason(row, "nested_evergreen_wild_archetype"))

    return _provenance_result("unknown", "missing_current_or_evergreen_marker")


def _provenance_result(status: str, reason: str) -> dict[str, Any]:
    return {
        "freshness_status": status,
        "current_or_evergreen": status in {"current", "evergreen"},
        "current_or_evergreen_reason": reason,
        "source_status_apply_blocking": False,
    }


def _nested_rows(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    rows: list[Mapping[str, Any]] = []
    for key in ("guide_sources", "current_deck_sources", "full_text_claim_sources", "records"):
        value = payload.get(key)
        if isinstance(value, list):
            rows.extend(row for row in value if isinstance(row, Mapping))
    return rows


def _source_family(record: Mapping[str, Any]) -> str:
    family = _text(
        record.get("source_family")
        or record.get("source_type_family")
        or record.get("source_type")
    ).lower()
    return family or "unknown"


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
    if family in STATIC_FAMILIES:
        return "full_text"
    return "unknown"


def _deck_identity_match(record: Mapping[str, Any], deck_name: str) -> dict[str, Any]:
    explicit = _text(record.get("deck_match_scope")).lower()
    if explicit in {"deck_matched", "deck_or_archetype_matched"}:
        return {"matched": True, "basis": explicit}
    match = record.get("deck_match", {})
    if not isinstance(match, Mapping):
        return {"matched": False, "basis": "missing_deck_match"}
    declared = _norm(match.get("deck_name"))
    matched_ids = match.get("matched_card_ids", [])
    has_card_overlap = isinstance(matched_ids, list) and any(_text(card_id) for card_id in matched_ids)
    if declared == _norm(deck_name) and has_card_overlap:
        return {"matched": True, "basis": "deck_name_and_card_overlap"}
    if declared == _norm(deck_name):
        return {"matched": True, "basis": "deck_name"}
    if has_card_overlap:
        return {"matched": True, "basis": "card_overlap"}
    return {"matched": False, "basis": "no_identity_match"}


def _freshness_status(
    record: Mapping[str, Any],
    *,
    family: str,
    publication_year: int | None,
    current_year: int | None,
    visibility: str,
) -> tuple[str, str]:
    explicit = _normalized_marker(record.get("freshness_status"))
    if explicit in CURRENT_MARKERS:
        return "current", _reason(record, "explicit_current")
    if explicit in EVERGREEN_MARKERS:
        return "evergreen", _reason(record, "explicit_evergreen")
    if _truthy(record.get("current_or_evergreen")):
        return "current", _reason(record, "explicit_current_or_evergreen")
    if _truthy(record.get("evergreen_wild_archetype")):
        return "evergreen", _reason(record, "explicit_evergreen_wild_archetype")
    if family in DECKLIST_FAMILIES:
        return "not_strategy_guide", "decklist_not_strategy_guide"
    if family not in GUIDE_FAMILIES:
        return "not_strategy_guide", f"{family}_not_strategy_guide"
    if visibility != "full_text":
        return "unknown", f"source_visibility_{visibility}_not_full_text"
    if publication_year is None or current_year is None:
        return "unknown", "missing_publication_year"
    if publication_year == current_year:
        return "current", "publication_year_matches_current_year"
    if _is_evergreen_wild_source(record, publication_year=publication_year, current_year=current_year):
        return "evergreen", "wild_guide_with_card_overlap"
    return "stale", "publication_year_not_current_or_evergreen"


def _is_evergreen_wild_source(
    record: Mapping[str, Any],
    *,
    publication_year: int,
    current_year: int,
) -> bool:
    age = current_year - publication_year
    if age < 1 or age > EVERGREEN_WILD_MAX_AGE_YEARS:
        return False
    format_scope = _text(record.get("format_scope") or record.get("format")).lower()
    if format_scope not in {"wild", "wild_archetype", "hearthstone_wild"}:
        return False
    match = record.get("deck_match", {})
    if not isinstance(match, Mapping):
        return False
    matched = match.get("matched_card_ids", [])
    if not isinstance(matched, list):
        return False
    return len({_text(card_id) for card_id in matched if _text(card_id)}) >= EVERGREEN_WILD_MIN_MATCHED_CARDS


def _reason(row: Mapping[str, Any], fallback: str) -> str:
    return _text(row.get("current_or_evergreen_reason")) or fallback


def _publication_year(record: Mapping[str, Any]) -> int | None:
    explicit = record.get("publication_year")
    if isinstance(explicit, int):
        return explicit
    published = _text(
        record.get("published_at")
        or record.get("publication_date")
        or record.get("published_date")
    )
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


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return _text(value).lower() in {"1", "true", "yes", "y"}


def _normalized_marker(value: Any) -> str:
    return _text(value).lower()


def _norm(value: Any) -> str:
    return "".join(ch for ch in _text(value).lower() if ch.isalnum())


def _text(value: Any) -> str:
    return str(value or "").strip()
```

- [ ] **Step 4: Run the normalizer tests**

Run:

```powershell
python -m pytest tests/test_source_provenance.py -q
```

Expected: all tests in `tests/test_source_provenance.py` pass.

- [ ] **Step 5: Commit Task 1**

Run:

```powershell
git add src/hsconfig/source_provenance.py tests/test_source_provenance.py
git commit -m "feat: add source provenance normalizer"
```

Expected: commit succeeds and `git status --short` is clean.

---

### Task 2: Carry Provenance Through Source Autopilot

**Files:**
- Modify: `src/hsconfig/source_evidence_policy.py`
- Modify: `src/hsconfig/source_autopilot.py`
- Modify: `tests/test_source_autopilot.py`

**Interfaces:**
- Consumes: `normalize_source_provenance(...) -> dict[str, Any]`
- Produces: ranked source rows and source evidence rows with `freshness_status`, `current_or_evergreen`, `current_or_evergreen_reason`, `deck_identity_match`, `deck_identity_match_basis`, and `source_status_apply_blocking`.

- [ ] **Step 1: Write failing source-autopilot tests**

Append to `tests/test_source_autopilot.py`:

```python
def test_rank_public_sources_exposes_current_or_evergreen_provenance() -> None:
    ranked = rank_public_sources(
        deck_name="ShadowPriest",
        deck_identity=SHADOW_DECK_IDENTITY,
        source_search_records=[
            {
                "source_url": "https://example.test/shadow-current",
                "source_title": "ShadowPriest Guide 2026",
                "source_family": "guide",
                "source_visibility": "full_text",
                "publication_year": 2026,
                "normalized_text": "x" * 220,
                "deck_match": {
                    "deck_name": "ShadowPriest",
                    "matched_card_ids": ["SW_448", "SW_446"],
                },
                "claims": [
                    {
                        "claim_kind": "mulligan_keep",
                        "cards": ["SW_446"],
                        "evidence_text_short": "Keep Voidtouched Attendant.",
                    }
                ],
            }
        ],
        current_date="2026-07-22",
    )

    assert ranked[0]["freshness_status"] == "current"
    assert ranked[0]["current_or_evergreen"] is True
    assert ranked[0]["current_or_evergreen_reason"] == "publication_year_matches_current_year"
    assert ranked[0]["deck_identity_match"] is True
    assert ranked[0]["source_status_apply_blocking"] is False


def test_source_evidence_rows_preserve_provenance_projection() -> None:
    ranked = rank_public_sources(
        deck_name="ShadowPriest",
        deck_identity=SHADOW_DECK_IDENTITY,
        source_search_records=[
            {
                "source_url": "https://example.test/shadow-current",
                "source_title": "ShadowPriest Guide 2026",
                "source_family": "guide",
                "source_visibility": "full_text",
                "publication_year": 2026,
                "normalized_text": "x" * 220,
                "deck_match": {
                    "deck_name": "ShadowPriest",
                    "matched_card_ids": ["SW_448", "SW_446"],
                },
                "claims": [
                    {
                        "claim_kind": "mulligan_keep",
                        "cards": ["SW_446"],
                        "evidence_text_short": "Keep Voidtouched Attendant.",
                    }
                ],
            }
        ],
        current_date="2026-07-22",
    )
    rows = extract_source_evidence_rows(
        deck_name="ShadowPriest",
        deck_identity=SHADOW_DECK_IDENTITY,
        ranked_sources=ranked,
        current_date="2026-07-22",
    )

    assert rows
    assert rows[0]["freshness_status"] == "current"
    assert rows[0]["current_or_evergreen"] is True
    assert rows[0]["current_or_evergreen_reason"] == "publication_year_matches_current_year"
    assert rows[0]["source_status_apply_blocking"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_source_autopilot.py::test_rank_public_sources_exposes_current_or_evergreen_provenance tests/test_source_autopilot.py::test_source_evidence_rows_preserve_provenance_projection -q
```

Expected: FAIL because the new provenance fields are absent from ranked rows or evidence rows.

- [ ] **Step 3: Wire normalizer into source evidence policy**

Modify `src/hsconfig/source_evidence_policy.py`:

```python
from hsconfig.source_provenance import normalize_source_provenance
```

Change the signature:

```python
def classify_source_evidence(
    record: Mapping[str, Any],
    *,
    deck_name: str,
    current_date: str | date | None,
    deck_identity: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
```

Inside `classify_source_evidence`, after `source_rank_lane` is computed and before `result.update(...)`, add:

```python
    provenance = normalize_source_provenance(
        record,
        deck_name=deck_name,
        deck_identity=deck_identity,
        current_date=current_date,
    )
```

Then include these fields in the existing `result.update(...)` mapping:

```python
            "freshness_status": provenance["freshness_status"],
            "current_or_evergreen": provenance["current_or_evergreen"],
            "current_or_evergreen_reason": provenance["current_or_evergreen_reason"],
            "deck_identity_match": provenance["deck_identity_match"],
            "deck_identity_match_basis": provenance["deck_identity_match_basis"],
            "source_status_apply_blocking": False,
```

- [ ] **Step 4: Pass deck identity and carry fields through autopilot**

In `src/hsconfig/source_autopilot.py`, change both `classify_source_evidence(...)` calls to pass `deck_identity=deck_identity` where available.

In `rank_public_sources`, replace:

```python
        policy = classify_source_evidence(
            row,
            deck_name=deck_name,
            current_date=current_date,
        )
```

with:

```python
        policy = classify_source_evidence(
            row,
            deck_name=deck_name,
            deck_identity=deck_identity,
            current_date=current_date,
        )
```

In `_source_base`, keep the existing call but add the new fields to `_policy_fields(...)`:

```python
        "freshness_status",
        "current_or_evergreen",
        "current_or_evergreen_reason",
        "deck_identity_match",
        "deck_identity_match_basis",
        "source_status_apply_blocking",
```

- [ ] **Step 5: Run focused source-autopilot tests**

Run:

```powershell
python -m pytest tests/test_source_autopilot.py::test_rank_public_sources_exposes_current_or_evergreen_provenance tests/test_source_autopilot.py::test_source_evidence_rows_preserve_provenance_projection -q
```

Expected: both tests pass.

- [ ] **Step 6: Run existing source-autopilot regression tests**

Run:

```powershell
python -m pytest tests/test_source_autopilot.py -q
```

Expected: all source-autopilot tests pass; existing Strong/partial behavior remains unchanged.

- [ ] **Step 7: Commit Task 2**

Run:

```powershell
git add src/hsconfig/source_evidence_policy.py src/hsconfig/source_autopilot.py tests/test_source_autopilot.py
git commit -m "feat: expose source provenance in autopilot"
```

Expected: commit succeeds and `git status --short` is clean.

---

### Task 3: Use Normalized Provenance in Research Result Validation

**Files:**
- Modify: `src/hsconfig/research_result_validator.py`
- Modify: `src/hsconfig/research_result_contract.py`
- Modify: `tests/test_research_result_validator.py`
- Modify: `tests/test_research_result_contract.py`

**Interfaces:**
- Consumes: `research_payload_provenance(payload: Mapping[str, Any]) -> dict[str, Any]`
- Produces: strict Strong validation that accepts top-level or nested current/evergreen metadata and rejects Strong when that metadata is truly missing.

- [ ] **Step 1: Add failing validator tests**

Append to `tests/test_research_result_validator.py`:

```python
def test_research_result_validator_accepts_strong_with_nested_current_source_metadata() -> None:
    result = validate_research_result_payload(
        {
            "deck_name": "CtAPaladin",
            "archetype": "Wild Call to Arms Paladin",
            "current_deck_sources": [],
            "guide_sources": [
                {
                    "url": "https://example.test/cta-paladin-guide",
                    "source_visibility": "full_text",
                    "source_freshness_lane": "guide_current_deck_match",
                    "current_or_evergreen_reason": "publication_year_matches_current_year",
                }
            ],
            "source_strength": "exact_full_text_guide",
            "source_visibility": "full_text",
            "lowerable_claim_kinds": ["mulligan_keep"],
            "non_promoting_support": [],
            "default_only_runtime_surfaces": [],
            "first_missing_source_action": "none",
            "notes": "Nested guide source proves current freshness.",
        }
    )

    assert result["valid"] is True
    assert result["errors"] == []
    assert result["current_or_evergreen"] is True
    assert result["freshness_status"] == "current"
    assert result["source_status_apply_blocking"] is False


def test_research_result_validator_still_rejects_strong_without_any_current_marker() -> None:
    result = validate_research_result_payload(
        {
            "deck_name": "CtAPaladin",
            "archetype": "Wild Call to Arms Paladin",
            "current_deck_sources": [],
            "guide_sources": [
                {
                    "url": "https://example.test/cta-paladin-guide",
                    "source_visibility": "full_text",
                }
            ],
            "source_strength": "exact_full_text_guide",
            "source_visibility": "full_text",
            "lowerable_claim_kinds": ["mulligan_keep"],
            "non_promoting_support": [],
            "default_only_runtime_surfaces": [],
            "first_missing_source_action": "none",
            "notes": "No freshness marker exists.",
        }
    )

    assert result["valid"] is False
    assert "strong_requires_current_or_evergreen_freshness" in result["errors"]
    assert result["source_status_apply_blocking"] is False
```

- [ ] **Step 2: Add failing contract classification tests**

Append to `tests/test_research_result_contract.py`:

```python
def test_research_result_contract_accepts_nested_evergreen_marker_for_strong_promotion() -> None:
    result = classify_research_result_contract(
        {
            "deck_name": "TreantDruid",
            "deck_code": "AAEBAZICFixture",
            "source_strength": "exact_full_text_guide",
            "source_visibility": "full_text",
            "lowerable_claim_kinds": ["mulligan_keep"],
            "default_only_runtime_surfaces": [],
            "first_missing_source_action": "none",
            "guide_sources": [
                {
                    "source_freshness_lane": "guide_evergreen_wild_archetype",
                    "current_or_evergreen_reason": "wild_guide_with_card_overlap",
                }
            ],
        }
    )

    assert result["contract_valid"] is True
    assert result["snapshot_kind"] == "strong"
    assert result["canonical_promotion_allowed"] is True
    assert result["source_status_apply_blocking"] is False
```

- [ ] **Step 3: Run tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_research_result_validator.py::test_research_result_validator_accepts_strong_with_nested_current_source_metadata tests/test_research_result_validator.py::test_research_result_validator_still_rejects_strong_without_any_current_marker tests/test_research_result_contract.py::test_research_result_contract_accepts_nested_evergreen_marker_for_strong_promotion -q
```

Expected: at least the nested-marker acceptance tests fail because the validator and contract classifier still require only top-level freshness.

- [ ] **Step 4: Update strict validator**

Modify `src/hsconfig/research_result_validator.py`:

```python
from hsconfig.source_provenance import research_payload_provenance
```

Inside `validate_research_result_payload`, after `lowerable_claim_kinds` is built, add:

```python
    provenance = research_payload_provenance(payload)
```

Replace the Strong freshness check:

```python
        freshness = str(payload.get("freshness_status") or "")
        if freshness not in {"current", "evergreen"}:
            errors.append("strong_requires_current_or_evergreen_freshness")
```

with:

```python
        if not provenance["current_or_evergreen"]:
            errors.append("strong_requires_current_or_evergreen_freshness")
```

Add these keys to the returned dictionary:

```python
        "freshness_status": provenance["freshness_status"],
        "current_or_evergreen": provenance["current_or_evergreen"],
        "current_or_evergreen_reason": provenance["current_or_evergreen_reason"],
```

- [ ] **Step 5: Update research contract classifier**

Modify `src/hsconfig/research_result_contract.py`:

```python
from hsconfig.source_provenance import research_payload_provenance
```

Replace the body of `_has_current_or_evergreen_evidence(...)` with:

```python
def _has_current_or_evergreen_evidence(payload: Mapping[str, Any]) -> bool:
    return bool(research_payload_provenance(payload)["current_or_evergreen"])
```

- [ ] **Step 6: Run research result tests**

Run:

```powershell
python -m pytest tests/test_research_result_validator.py tests/test_research_result_contract.py -q
```

Expected: all tests pass. Existing tests that reject Strong without freshness remain green.

- [ ] **Step 7: Commit Task 3**

Run:

```powershell
git add src/hsconfig/research_result_validator.py src/hsconfig/research_result_contract.py tests/test_research_result_validator.py tests/test_research_result_contract.py
git commit -m "fix: validate research freshness provenance"
```

Expected: commit succeeds and `git status --short` is clean.

---

### Task 4: Surface Provenance Gaps in Sentinel and Preflight

**Files:**
- Modify: `src/hsconfig/research_result_contract_sentinel.py`
- Modify: `src/hsconfig/contract_preflight.py`
- Modify: `tests/test_research_result_contract_sentinel.py`
- Modify: `tests/test_contract_preflight.py`

**Interfaces:**
- Consumes: strict validator return fields from Task 3.
- Produces: sentinel summary keys `freshness_missing_count`, `current_or_evergreen_count`, and per-row `current_or_evergreen_reason`.
- Produces: contract-preflight `research_context.latest_research_result_contract_freshness_missing_count`.

- [ ] **Step 1: Add failing sentinel test**

Append to `tests/test_research_result_contract_sentinel.py`:

```python
def test_sentinel_counts_missing_freshness_without_apply_blocking(tmp_path: Path) -> None:
    fields_path = tmp_path / "fields.yaml"
    fields_path.write_text(yaml.safe_dump(FIELDS), encoding="utf-8")
    results_dir = tmp_path / "results"
    _write_json(
        results_dir / "CtAPaladin.json",
        {
            "deck_name": "CtAPaladin",
            "archetype": "Wild Call to Arms Paladin",
            "current_deck_sources": [],
            "guide_sources": [],
            "source_strength": "exact_full_text_guide",
            "source_visibility": "full_text",
            "lowerable_claim_kinds": ["mulligan_keep"],
            "non_promoting_support": [],
            "default_only_runtime_surfaces": [],
            "first_missing_source_action": "none",
            "notes": "Missing current or evergreen marker.",
        },
    )

    report = build_research_result_contract_sentinel(fields_path, results_dir)

    assert report["summary"]["status"] == "attention"
    assert report["summary"]["freshness_missing_count"] == 1
    assert report["summary"]["current_or_evergreen_count"] == 0
    assert report["result_rows"][0]["freshness_status"] == "unknown"
    assert report["result_rows"][0]["current_or_evergreen"] is False
    assert report["result_rows"][0]["current_or_evergreen_reason"] == "missing_current_or_evergreen_marker"
    assert report["source_status_apply_blocking"] is False
```

- [ ] **Step 2: Add failing preflight test**

Append to `tests/test_contract_preflight.py`:

```python
def test_contract_preflight_exposes_research_freshness_missing_count() -> None:
    payload = build_contract_preflight(".")
    context = payload["research_context"]

    assert "latest_research_result_contract_freshness_missing_count" in context
    assert isinstance(context["latest_research_result_contract_freshness_missing_count"], int)
    assert context["source_status_apply_blocking"] is False
    assert payload["source_status_apply_blocking"] is False
```

If `build_contract_preflight` is not imported in the file yet, add:

```python
from hsconfig.contract_preflight import build_contract_preflight
```

- [ ] **Step 3: Run tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_research_result_contract_sentinel.py::test_sentinel_counts_missing_freshness_without_apply_blocking tests/test_contract_preflight.py::test_contract_preflight_exposes_research_freshness_missing_count -q
```

Expected: FAIL because the new summary keys are absent.

- [ ] **Step 4: Add sentinel summary fields**

Modify `src/hsconfig/research_result_contract_sentinel.py`.

Inside `build_research_result_contract_sentinel`, after `strong_promoting_count`:

```python
    freshness_missing_count = sum(
        1
        for row in rows
        if "strong_requires_current_or_evergreen_freshness"
        in row["strict_research_result_errors"]
    )
    current_or_evergreen_count = sum(
        1 for row in rows if row["current_or_evergreen"] is True
    )
```

Add to `summary`:

```python
            "freshness_missing_count": freshness_missing_count,
            "current_or_evergreen_count": current_or_evergreen_count,
```

Inside `_result_row`, add these fields from `strict`:

```python
        "freshness_status": str(strict.get("freshness_status") or ""),
        "current_or_evergreen": bool(strict.get("current_or_evergreen", False)),
        "current_or_evergreen_reason": str(strict.get("current_or_evergreen_reason") or ""),
```

- [ ] **Step 5: Add preflight field**

Modify `src/hsconfig/contract_preflight.py`.

Where the latest research result contract summary is projected into `research_context`, add:

```python
        latest_research_result_contract_freshness_missing_count=int(
            latest_summary.get("freshness_missing_count") or 0
        ),
```

If the current implementation builds a dictionary rather than a dataclass, add:

```python
        "latest_research_result_contract_freshness_missing_count": int(
            latest_summary.get("freshness_missing_count") or 0
        ),
```

Also add the same key with value `0` to `_unavailable_research_context_payload(...)` in `src/hsconfig/commands/contract_preflight.py` if that fallback mirrors the research context schema.

- [ ] **Step 6: Run sentinel and preflight tests**

Run:

```powershell
python -m pytest tests/test_research_result_contract_sentinel.py tests/test_contract_preflight.py -q
```

Expected: all tests pass and no test treats freshness gaps as apply-blocking.

- [ ] **Step 7: Commit Task 4**

Run:

```powershell
git add src/hsconfig/research_result_contract_sentinel.py src/hsconfig/contract_preflight.py src/hsconfig/commands/contract_preflight.py tests/test_research_result_contract_sentinel.py tests/test_contract_preflight.py
git commit -m "feat: report research provenance gaps"
```

Expected: commit succeeds and `git status --short` is clean.

---

### Task 5: Update Operator Docs and Installed Skill

**Files:**
- Modify: `docs/operator/README.md`
- Modify: `docs/operator/universal-wild-no-block-contract.md`
- Modify: `.agents/skills/hsconfig/SKILL.md`

**Interfaces:**
- Consumes: fields produced by Tasks 1-4.
- Produces: operator-facing documentation that explains how to read provenance gaps without turning them into apply blockers.

- [ ] **Step 1: Update operator README wording**

In `docs/operator/README.md`, add this paragraph near the existing source-autopilot and research-result sentinel section:

```markdown
Source freshness/provenance fields are diagnostic-only. `freshness_status`,
`current_or_evergreen`, `current_or_evergreen_reason`, `deck_identity_match`,
and `deck_identity_match_basis` explain why a fetched source can or cannot
support `SOURCE_BACKED_STRONG`. Missing or stale provenance prevents Strong
promotion, but it does not block a technically valid load-safe package and it
does not replace `reports/operator_summary.json`.
```

- [ ] **Step 2: Update no-block contract wording**

In `docs/operator/universal-wild-no-block-contract.md`, add this bullet under the source quality section:

```markdown
- Missing freshness/provenance metadata is visible source-quality debt. It can
  keep `SOURCE_BACKED_STRONG` at partial or attention status, but
  `source_status_apply_blocking` remains `false` and a valid deck still builds
  a load-safe package.
```

- [ ] **Step 3: Update repo skill routing**

In `.agents/skills/hsconfig/SKILL.md`, add this operator note near the current source-backed Strong guidance:

```markdown
When source strength is unclear, inspect the normalized provenance fields:
`freshness_status`, `current_or_evergreen`, `current_or_evergreen_reason`,
`deck_identity_match`, and `deck_identity_match_basis`. These fields explain
Strong eligibility only. They do not grant apply authority, do not block valid
load-safe config generation, and do not override `reports/operator_summary.json`.
```

- [ ] **Step 4: Sync installed skill**

Run:

```powershell
python scripts\sync_installed_skill.py --install-root C:\Users\darbo\.codex\skills
python scripts\sync_installed_skill.py --check --install-root C:\Users\darbo\.codex\skills
```

Expected: output includes `HSConfig skill is in sync: C:\Users\darbo\.codex\skills\hsconfig`.

- [ ] **Step 5: Commit Task 5**

Run:

```powershell
git add docs/operator/README.md docs/operator/universal-wild-no-block-contract.md .agents/skills/hsconfig/SKILL.md
git commit -m "docs: document source provenance diagnostics"
```

Expected: commit succeeds and `git status --short` is clean.

---

### Task 6: Final Contract Verification

**Files:**
- Verify only. No source file edits in this task unless a prior task introduced a failing test.

**Interfaces:**
- Consumes: all implementation tasks.
- Produces: final proof that the repo is current, the skill is synced, contract guardrails pass, and the worktree is clean.

- [ ] **Step 1: Run focused test set**

Run:

```powershell
python -m pytest tests/test_source_provenance.py tests/test_source_autopilot.py tests/test_research_result_validator.py tests/test_research_result_contract.py tests/test_research_result_contract_sentinel.py tests/test_contract_preflight.py -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run contract diagnostics**

Run:

```powershell
python -m hsconfig.cli contract-preflight --json
python -m hsconfig.cli contract-spine-sentinel --json
```

Expected:
- `contract-preflight` returns `status: "PASS"`.
- `contract-spine-sentinel` returns `status: "clean"`.
- Both payloads keep `source_status_apply_blocking: false`.
- `research_context.latest_research_result_contract_freshness_missing_count` is present.

- [ ] **Step 3: Run full guardrail suite**

Run:

```powershell
python scripts\check_contract_guardrails.py
```

Expected:
- pytest completes with all tests passed.
- Output includes `OK: installed skill sync`.
- Output includes `OK: contract spine sentinel`.
- Output includes `OK: focused contract boundary tests`.

- [ ] **Step 4: Confirm currentness and clean worktree**

Run:

```powershell
python scripts\check_hsconfig_currentness.py --cwd . --json
git status --short --branch
```

Expected:
- Currentness JSON contains `dirty: false`, `behind_origin_main: 0`, and `clean_for_runtime_work: true`.
- `git status --short --branch` shows the current branch and no changed files.

- [ ] **Step 5: Push if execution created commits**

Run:

```powershell
git push
```

Expected: push succeeds and `git status --short --branch` shows no ahead/behind drift against the upstream branch.

---

## Self-Review

- Spec coverage: The plan improves source freshness/provenance only, keeps HSConfig-only workflow, avoids logs/HSTuner, preserves no-block generation, and keeps `operator_summary.json` as the only apply authority.
- Scope control: The plan does not add gameplay sequencing, card-value tuning, a Hearthstone simulator, runtime logs, or new output surfaces.
- Contract safety: Every new field is diagnostic-only and carries `source_status_apply_blocking=false`.
- No-default-only boundary: The plan preserves existing `default_only_runtime_surfaces` checks and only adds provenance visibility around Strong eligibility.
- Darkbishop boundary: The plan does not touch Mulligan inference rules or promote start-of-game effects to opening-hand keeps.
- Testability: Each task has focused failing tests before implementation and a scoped pass command after implementation.
- Cleanliness: Each task ends with a commit; final verification requires clean currentness and synced installed skill.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-22-hsconfig-source-freshness-provenance-normalizer.md`.

Two execution options:

1. Subagent-Driven (recommended) - dispatch a fresh subagent per task, review between tasks, fast iteration.
2. Inline Execution - execute tasks in this session using executing-plans, batch execution with checkpoints.

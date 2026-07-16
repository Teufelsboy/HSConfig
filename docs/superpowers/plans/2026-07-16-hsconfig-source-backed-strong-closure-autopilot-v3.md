# HSConfig Source-Backed Strong Closure Autopilot V3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make HSConfig produce the best load-safe, non-default-only config for every valid deck while awarding `SOURCE_BACKED_STRONG` only when the public source-to-runtime contract is truly closed.

**Architecture:** Keep the existing no-block runtime contract and apply authority intact. Strengthen only the source closure chain: source candidates -> fetched/classified source evidence -> atomic claim extraction -> closure profile evaluation -> no-default runtime package proof. The implementation must avoid broad orchestration growth and use small focused modules with tests around each boundary.

**Tech Stack:** Python 3, pytest, existing HSConfig CLI/modules, no new runtime dependency unless the repository already vendors or declares it.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig`.
- Do not make `SOURCE_BACKED_STRONG` a runtime-write gate.
- `reports/operator_summary.json` remains the only normal apply authority.
- Valid deck input must produce a load-safe package even when source coverage is partial.
- `default_only_runtime_surfaces` must remain empty for the 12-deck Wild proof matrix.
- Candidate URLs are source acquisition seeds only; they are never promotion authority by themselves.
- Decklist-only, stats-only, snippet-only, policy fallback, default runtime, generated defaults, and raw registry metadata must never promote a runtime surface to `SOURCE_BACKED_STRONG`.
- Static semantics may close deterministic CardID/effect surfaces, but must not prove deck-specific mulligan, combo, targeting, or gameplan posture by itself.
- Darkbishop Benedictus (`SW_448`) must preserve `hero_power_transform`, Shadowform, and Mind Spike semantics, but must not become a mulligan keep unless a same-source sentence explicitly says to keep that exact card.
- No normal-path `Presume.json` or `Concede.json`.
- No raw runtime evidence, logs, HDT replay files, HearthRanger logs, or private evidence folders in commits.
- Keep the change narrow: source acquisition, source evidence policy, source text claim extraction, source autopilot, source reports, docs, and tests only.

---

## File Structure

- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\source_candidate_registry.py`
  - Owns built-in source candidate seeds and their strength ceilings.
- Modify: `C:\Users\darbo\Documents\HSConfig\docs\operator\source-candidate-proof-decks.json`
  - Owns the 12-deck user proof set and expected first missing source action.
- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\source_evidence_policy.py`
  - Owns evidence classification and trust ceiling rules.
- Create: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\source_text_claim_extractor.py`
  - Owns deterministic text-to-claim extraction from fetched full-text guide sources.
- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\source_autopilot.py`
  - Owns ranking, source document drafting, closure report, and first missing source actions.
- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\commands\configure.py`
  - Owns the `configure --online-source --auto-source` orchestration path.
- Modify: `C:\Users\darbo\Documents\HSConfig\docs\operator\source-backed-strong-closure.md`
  - Owns operator-facing semantics and promotion rules.
- Modify: `C:\Users\darbo\Documents\HSConfig\docs\operator\guide-research-policy.md`
  - Owns guide/source policy language.
- Modify: `C:\Users\darbo\Documents\HSConfig\.agents\skills\hsconfig\SKILL.md`
  - Owns repo-local HSConfig skill behavior.
- Modify: `C:\Users\darbo\.codex\skills\hsconfig\SKILL.md`
  - Owns installed HSConfig skill behavior.
- Add or modify tests:
  - `C:\Users\darbo\Documents\HSConfig\tests\test_source_candidate_registry_matrix.py`
  - `C:\Users\darbo\Documents\HSConfig\tests\test_source_evidence_policy.py`
  - `C:\Users\darbo\Documents\HSConfig\tests\test_source_text_claim_extractor.py`
  - `C:\Users\darbo\Documents\HSConfig\tests\test_source_autopilot.py`
  - `C:\Users\darbo\Documents\HSConfig\tests\test_configure_online_source.py`
  - `C:\Users\darbo\Documents\HSConfig\tests\test_universal_wild_no_block_matrix.py`

---

### Task 1: Lock The 12-Deck Source Candidate Contract

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_source_candidate_registry_matrix.py`
- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\source_candidate_registry.py`
- Modify: `C:\Users\darbo\Documents\HSConfig\docs\operator\source-candidate-proof-decks.json`

**Interfaces:**
- Consumes: `source_candidates_for_deck(deck_name: str, deck_code: str | None = None) -> list[SourceCandidate]`
- Produces: Stable candidate proof invariants used by source acquisition and configure tests.

- [ ] **Step 1: Add the failing proof test**

Add this test to `C:\Users\darbo\Documents\HSConfig\tests\test_source_candidate_registry_matrix.py`:

```python
import json
from pathlib import Path

from hsconfig.source_candidate_registry import source_candidates_for_deck


PROOF_PATH = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "operator"
    / "source-candidate-proof-decks.json"
)


def test_source_candidate_proof_rows_match_registry_contract():
    proof = json.loads(PROOF_PATH.read_text(encoding="utf-8"))

    assert proof["strongness_policy"].startswith("Candidate URLs are source acquisition seeds")

    for row in proof["decks"]:
        deck_name = row["deck_name"]
        candidates = source_candidates_for_deck(deck_name)
        urls = {candidate.url for candidate in candidates}
        expected_urls = set(row["candidate_urls"])

        assert len(candidates) >= row["expected_candidate_count_min"], deck_name
        assert expected_urls <= urls, deck_name
        assert {
            candidate.strength_ceiling for candidate in candidates
            if candidate.url in expected_urls
        } == {row["expected_strength_ceiling"]}, deck_name

        expected_action = row["first_missing_source_action"]
        matching_actions = {
            candidate.first_missing_source_action
            for candidate in candidates
            if candidate.url in expected_urls
        }
        assert matching_actions == {expected_action}, deck_name


def test_context_only_candidates_cannot_declare_runtime_claim_kinds():
    for deck_name in ["MechPala"]:
        candidates = source_candidates_for_deck(deck_name)
        context_candidates = [
            candidate for candidate in candidates
            if candidate.strength_ceiling == "context_only"
        ]

        assert context_candidates
        assert all(candidate.expected_claim_kinds == () for candidate in context_candidates)
        assert all(
            candidate.first_missing_source_action
            == "add_current_full_text_mulligan_or_gameplan_source"
            for candidate in context_candidates
        )
```

- [ ] **Step 2: Run the test and confirm current failures**

Run:

```powershell
python -m pytest -p no:cacheprovider tests\test_source_candidate_registry_matrix.py -q
```

Expected before fixes: either pass if the contract is already fully aligned, or fail with a deck name where registry/proof JSON diverges.

- [ ] **Step 3: Fix candidate/proof divergence only**

If the test fails, edit only:

```text
C:\Users\darbo\Documents\HSConfig\src\hsconfig\source_candidate_registry.py
C:\Users\darbo\Documents\HSConfig\docs\operator\source-candidate-proof-decks.json
```

Use these exact rules:

```python
# context-only candidate
strength_ceiling = "context_only"
expected_claim_kinds = ()
first_missing_source_action = "add_current_full_text_mulligan_or_gameplan_source"

# candidate that may promote only after fetched claims close
strength_ceiling = "candidate_strong"
first_missing_source_action = "none"

# candidate that remains source-informed until an exact missing source closes
strength_ceiling = "candidate_partial"
first_missing_source_action = "add_current_card_specific_runtime_source"
```

For deck-specific missing actions, preserve the existing more precise action when it exists:

```text
add_current_cta_paladin_mulligan_keep_source
add_current_pirate_rogue_mulligan_or_role_source
add_discolock_matchup_or_card_role_source
add_treant_druid_card_specific_source_claim
add_kingslayer_quick_pick_mulligan_source
add_boarlock_fracking_mulligan_source
add_pirate_dh_card_role_or_mulligan_source
add_current_full_text_mulligan_or_gameplan_source
```

- [ ] **Step 4: Run the task tests**

Run:

```powershell
python -m pytest -p no:cacheprovider tests\test_source_candidate_registry_matrix.py -q
```

Expected: all tests in the file pass.

- [ ] **Step 5: Commit**

```powershell
git add tests\test_source_candidate_registry_matrix.py src\hsconfig\source_candidate_registry.py docs\operator\source-candidate-proof-decks.json
git commit -m "test: lock source candidate proof matrix"
```

---

### Task 2: Harden Evidence Classification Before Claim Extraction

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_source_evidence_policy.py`
- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\source_evidence_policy.py`

**Interfaces:**
- Consumes: `classify_source_evidence(record: Mapping[str, Any], *, deck_name: str, current_date: str | date | None) -> dict[str, Any]`
- Produces: Stable `source_visibility`, `source_rank_lane`, `source_lane`, `trust_ceiling`, `promotion_blockers`, and `first_missing_source_action`.

- [ ] **Step 1: Add hard classification tests**

Append these tests to `C:\Users\darbo\Documents\HSConfig\tests\test_source_evidence_policy.py`:

```python
from hsconfig.source_evidence_policy import classify_source_evidence


def test_current_full_text_deck_matched_guide_is_strong_eligible():
    record = {
        "source_url": "https://example.test/shadowpriest-guide",
        "source_title": "2026 Wild ShadowPriest Guide",
        "source_family": "guide",
        "source_visibility": "full_text",
        "publication_year": 2026,
        "deck_match": {
            "deck_name": "ShadowPriest",
            "matched_card_ids": ["SW_448", "TOY_381"],
        },
        "normalized_text": "ShadowPriest guide with mulligan, burn posture, and Mind Spike plan.",
        "source_record_strength": "candidate_strong",
    }

    result = classify_source_evidence(
        record,
        deck_name="ShadowPriest",
        current_date="2026-07-16",
    )

    assert result["source_visibility"] == "full_text"
    assert result["source_rank_lane"] == "guide_current_deck_match"
    assert result["source_lane"] == "deck_matched_public_guide"
    assert result["promotion_eligible"] is True
    assert result["strong_promotion_eligible"] is True
    assert result["trust_ceiling"] == "source_backed_strong"
    assert result["promotion_blockers"] == []
    assert result["first_missing_source_action"] == "none"


def test_decklist_only_source_never_promotes_to_strong():
    record = {
        "source_url": "https://example.test/mech-paladin",
        "source_title": "Mech Paladin Decklist",
        "source_family": "decklist",
        "source_visibility": "decklist_only",
        "publication_year": 2026,
        "deck_match": {
            "deck_name": "MechPala",
            "matched_card_ids": ["GVG_058", "BOT_906"],
        },
        "source_record_strength": "candidate_strong",
    }

    result = classify_source_evidence(record, deck_name="MechPala", current_date="2026-07-16")

    assert result["source_rank_lane"] == "decklist_only"
    assert result["source_lane"] == "decklist_only"
    assert result["promotion_eligible"] is False
    assert result["strong_promotion_eligible"] is False
    assert result["trust_ceiling"] == "decklist_informed"
    assert "decklist_only_not_strong_evidence" in result["promotion_blockers"]
    assert result["first_missing_source_action"] == "add_current_or_evergreen_wild_public_guide"


def test_static_semantics_supports_cardid_effects_but_not_strategy_surfaces():
    effect_record = {
        "source_family": "hearthstonejson_static_semantics",
        "claim_kind": "hero_power_transform",
        "source_visibility": "full_text",
        "deck_match_scope": "deck_or_archetype_matched",
        "publication_year": 2026,
    }
    strategy_record = {
        "source_family": "hearthstonejson_static_semantics",
        "claim_kind": "mulligan_keep",
        "source_visibility": "full_text",
        "deck_match_scope": "deck_or_archetype_matched",
        "publication_year": 2026,
    }

    effect = classify_source_evidence(effect_record, deck_name="ShadowPriest", current_date="2026-07-16")
    strategy = classify_source_evidence(strategy_record, deck_name="ShadowPriest", current_date="2026-07-16")

    assert effect["static_runtime_surface_eligible"] is True
    assert effect["static_runtime_surface_scope"] == "cardid_effect"
    assert effect["trust_ceiling"] == "static_semantics_only"
    assert effect["strong_promotion_eligible"] is False

    assert strategy["static_runtime_surface_eligible"] is False
    assert strategy["static_runtime_surface_scope"] == "not_runtime_surface_static"
    assert strategy["static_runtime_surface_limit"] == "static_semantics_does_not_prove_strategy_surface"
    assert strategy["strong_promotion_eligible"] is False
```

- [ ] **Step 2: Run the test and observe failures**

Run:

```powershell
python -m pytest -p no:cacheprovider tests\test_source_evidence_policy.py -q
```

Expected before fixes: any failure points to evidence classification being too permissive or too vague.

- [ ] **Step 3: Implement minimal policy fixes**

Edit `C:\Users\darbo\Documents\HSConfig\src\hsconfig\source_evidence_policy.py` so these invariants hold:

```python
DECKLIST_FAMILIES = {"decklist", "decklist_only", "deck_aggregator", "deck_snapshot", "deck_code"}
STATS_FAMILIES = {"stats", "statistical_enrichment", "hsguru", "hs_guru", "hs-guru"}
STATIC_CARDID_EFFECT_CLAIM_KINDS = {"hero_power_transform", "mechanic_usage", "card_role"}
```

Ensure `_promotion_blockers()` adds these blockers:

```python
if family in DECKLIST_FAMILIES:
    blockers.append("decklist_only_not_strong_evidence")
    blockers.append("decklist_not_guide")
if family in STATS_FAMILIES:
    blockers.append("stats_only_not_strong_evidence")
    blockers.append("stats_not_guide")
if family in STATIC_FAMILIES:
    blockers.append("static_semantics_not_public_guide")
    blockers.append("static_semantics_not_deck_strategy")
if visibility != "full_text":
    blockers.append(f"source_visibility_{visibility}_not_strong")
```

Ensure `_static_runtime_surface_scope()` returns:

```python
{
    "static_runtime_surface_eligible": True,
    "static_runtime_surface_scope": "cardid_effect",
    "static_runtime_surface_limit": "static_semantics_supports_cardid_effects_only",
}
```

only for static semantics plus deterministic CardID/effect claim kinds.

- [ ] **Step 4: Run the task tests**

Run:

```powershell
python -m pytest -p no:cacheprovider tests\test_source_evidence_policy.py -q
```

Expected: all evidence policy tests pass.

- [ ] **Step 5: Commit**

```powershell
git add tests\test_source_evidence_policy.py src\hsconfig\source_evidence_policy.py
git commit -m "fix: harden source evidence promotion policy"
```

---

### Task 3: Add Full-Text Source Claim Extraction

**Files:**
- Create: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\source_text_claim_extractor.py`
- Create: `C:\Users\darbo\Documents\HSConfig\tests\test_source_text_claim_extractor.py`

**Interfaces:**
- Produces: `extract_text_claims(*, deck_name: str, deck_identity: Mapping[str, Any], source_record: Mapping[str, Any], current_date: str | date | None = None) -> list[dict[str, Any]]`
- Consumes later: `source_autopilot.extract_source_evidence_rows()`

- [ ] **Step 1: Write failing extractor tests**

Create `C:\Users\darbo\Documents\HSConfig\tests\test_source_text_claim_extractor.py`:

```python
from hsconfig.source_text_claim_extractor import extract_text_claims


def _shadow_identity():
    return {
        "cards": [
            {
                "card_id": "SW_448",
                "name": "Darkbishop Benedictus",
                "cost": 5,
                "text": "Start of Game: If the spells in your deck are all Shadow, enter Shadowform.",
            },
            {"card_id": "TOY_381", "name": "Papercraft Angel", "cost": 3, "text": ""},
            {"card_id": "SCH_514", "name": "Raise Dead", "cost": 0, "text": ""},
        ]
    }


def test_extracts_explicit_mulligan_keep_without_darkbishop_false_keep():
    source = {
        "source_url": "https://example.test/guide",
        "source_title": "Wild ShadowPriest Guide",
        "source_family": "guide",
        "source_visibility": "full_text",
        "source_lane": "deck_matched_public_guide",
        "source_rank_lane": "guide_current_deck_match",
        "publication_year": 2026,
        "deck_match": {"deck_name": "ShadowPriest", "matched_card_ids": ["SW_448", "TOY_381"]},
        "normalized_text": (
            "Mulligan: keep Papercraft Angel. "
            "Do not keep any 4-cost or higher card. "
            "Darkbishop Benedictus changes your hero power into Mind Spike at the start of the game."
        ),
        "source_record_strength": "candidate_strong",
    }

    claims = extract_text_claims(
        deck_name="ShadowPriest",
        deck_identity=_shadow_identity(),
        source_record=source,
        current_date="2026-07-16",
    )

    keep_cards = {
        card_id
        for claim in claims
        if claim["claim_kind"] == "mulligan_keep"
        for card_id in claim["cards"]
    }
    discard_cards = {
        card_id
        for claim in claims
        if claim["claim_kind"] == "mulligan_discard"
        for card_id in claim["cards"]
    }
    transform_cards = {
        card_id
        for claim in claims
        if claim["claim_kind"] == "hero_power_transform"
        for card_id in claim["cards"]
    }

    assert keep_cards == {"TOY_381"}
    assert "SW_448" in discard_cards
    assert transform_cards == {"SW_448"}


def test_decklist_only_source_extracts_no_runtime_claims():
    source = {
        "source_url": "https://example.test/decklist",
        "source_title": "Mech Paladin Decklist",
        "source_family": "decklist",
        "source_visibility": "decklist_only",
        "normalized_text": "Deck code and card list only.",
        "publication_year": 2026,
    }

    assert extract_text_claims(
        deck_name="MechPala",
        deck_identity={"cards": [{"card_id": "CARD_1", "name": "Mech", "cost": 1}]},
        source_record=source,
        current_date="2026-07-16",
    ) == []
```

- [ ] **Step 2: Run the tests and confirm import failure**

Run:

```powershell
python -m pytest -p no:cacheprovider tests\test_source_text_claim_extractor.py -q
```

Expected: fail with `ModuleNotFoundError` or missing function.

- [ ] **Step 3: Create the extractor module**

Create `C:\Users\darbo\Documents\HSConfig\src\hsconfig\source_text_claim_extractor.py` with this implementation shape:

```python
from __future__ import annotations

from datetime import date
from typing import Any, Mapping


STRONG_SOURCE_LANES = {"deck_matched_public_guide"}
STRONG_RANK_LANES = {"guide_current_deck_match", "guide_evergreen_wild_archetype"}


def extract_text_claims(
    *,
    deck_name: str,
    deck_identity: Mapping[str, Any],
    source_record: Mapping[str, Any],
    current_date: str | date | None = None,
) -> list[dict[str, Any]]:
    del deck_name, current_date
    if not _is_full_text_guide(source_record):
        return []

    text = _text(source_record.get("normalized_text") or source_record.get("text")).lower()
    if not text:
        return []

    claims: list[dict[str, Any]] = []
    cards = [card for card in deck_identity.get("cards", []) if isinstance(card, Mapping)]
    claims.extend(_explicit_keep_claims(cards, text, source_record))
    claims.extend(_cost_based_discard_claims(cards, text, source_record))
    claims.extend(_hero_power_transform_claims(cards, text, source_record))
    return _dedupe_claims(claims)


def _is_full_text_guide(source_record: Mapping[str, Any]) -> bool:
    family = _text(source_record.get("source_family")).lower()
    visibility = _text(source_record.get("source_visibility")).lower()
    lane = _text(source_record.get("source_lane")).lower()
    rank_lane = _text(source_record.get("source_rank_lane")).lower()
    return (
        family in {"guide", "public_guide", "community_guide", "mulligan_guide", "matchup_guide", "guide_fixture"}
        and visibility == "full_text"
        and lane in STRONG_SOURCE_LANES
        and rank_lane in STRONG_RANK_LANES
    )


def _explicit_keep_claims(
    cards: list[Mapping[str, Any]],
    text: str,
    source_record: Mapping[str, Any],
) -> list[dict[str, Any]]:
    claims: list[dict[str, Any]] = []
    for card in cards:
        card_id = _text(card.get("card_id"))
        name = _text(card.get("name"))
        if not card_id or not name:
            continue
        name_l = name.lower()
        if _is_non_opening_hand_effect_card(card):
            continue
        if f"keep {name_l}" in text or f"{name_l} is a keep" in text:
            claims.append(_claim(source_record, "mulligan_keep", card_id, f"Guide explicitly keeps {name}."))
    return claims


def _cost_based_discard_claims(
    cards: list[Mapping[str, Any]],
    text: str,
    source_record: Mapping[str, Any],
) -> list[dict[str, Any]]:
    if "do not keep any 4-cost or higher" not in text and "do not keep any 4 cost or higher" not in text:
        return []
    claims: list[dict[str, Any]] = []
    for card in cards:
        cost = _int_or_none(card.get("cost"))
        card_id = _text(card.get("card_id"))
        if card_id and cost is not None and cost >= 4:
            claims.append(_claim(source_record, "mulligan_discard", card_id, "Guide discards 4-cost or higher cards."))
    return claims


def _hero_power_transform_claims(
    cards: list[Mapping[str, Any]],
    text: str,
    source_record: Mapping[str, Any],
) -> list[dict[str, Any]]:
    claims: list[dict[str, Any]] = []
    for card in cards:
        card_id = _text(card.get("card_id"))
        name = _text(card.get("name"))
        card_text = _text(card.get("text")).lower()
        if not card_id or not name:
            continue
        mentions_card = name.lower() in text
        mentions_power = "mind spike" in text or "shadowform" in text or "hero power" in text
        start_of_game = "start of game" in card_text or "start of game" in text
        if mentions_card and mentions_power and start_of_game:
            claims.append(_claim(source_record, "hero_power_transform", card_id, f"{name} transforms the hero power."))
    return claims


def _claim(source_record: Mapping[str, Any], claim_kind: str, card_id: str, evidence: str) -> dict[str, Any]:
    return {
        "source_url": _text(source_record.get("source_url")),
        "source_title": _text(source_record.get("source_title")),
        "source_family": _text(source_record.get("source_family")),
        "source_visibility": _text(source_record.get("source_visibility")),
        "source_lane": _text(source_record.get("source_lane")),
        "source_rank_lane": _text(source_record.get("source_rank_lane")),
        "source_record_strength": _text(source_record.get("source_record_strength")),
        "publication_year": source_record.get("publication_year"),
        "claim_kind": claim_kind,
        "cards": [card_id],
        "scope": "card",
        "source_confidence": "high",
        "evidence_text_short": evidence,
    }


def _dedupe_claims(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, tuple[str, ...]]] = set()
    deduped: list[dict[str, Any]] = []
    for claim in claims:
        key = (claim["source_url"], claim["claim_kind"], tuple(claim["cards"]))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(claim)
    return deduped


def _is_non_opening_hand_effect_card(card: Mapping[str, Any]) -> bool:
    name = _text(card.get("name")).lower()
    text = _text(card.get("text")).lower()
    roles = {_text(role).lower() for role in _as_list(card.get("roles"))}
    return (
        name == "darkbishop benedictus"
        or "start of game" in text
        or "hero_power_transform" in roles
        or "start_of_game" in roles
    )


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _text(value: Any) -> str:
    return str(value or "").strip()
```

- [ ] **Step 4: Run extractor tests**

Run:

```powershell
python -m pytest -p no:cacheprovider tests\test_source_text_claim_extractor.py -q
```

Expected: both tests pass.

- [ ] **Step 5: Commit**

```powershell
git add src\hsconfig\source_text_claim_extractor.py tests\test_source_text_claim_extractor.py
git commit -m "feat: extract claims from full text guide sources"
```

---

### Task 4: Wire Text Claims Into Source Autopilot

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\source_autopilot.py`
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_source_autopilot.py`
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_configure_online_source.py`

**Interfaces:**
- Consumes: `extract_text_claims(...) -> list[dict[str, Any]]`
- Produces: `source_autopilot_report.json.source_evidence_rows`, `card_rows`, `surface_rows`, and `source_backed_strong_closure`.

- [ ] **Step 1: Add a source autopilot integration test**

Append this test to `C:\Users\darbo\Documents\HSConfig\tests\test_source_autopilot.py`:

```python
from hsconfig.source_autopilot import build_source_autopilot_bundle


def test_autopilot_extracts_full_text_claims_before_closure_evaluation():
    deck_identity = {
        "cards": [
            {
                "card_id": "SW_448",
                "name": "Darkbishop Benedictus",
                "cost": 5,
                "text": "Start of Game: If the spells in your deck are all Shadow, enter Shadowform.",
            },
            {"card_id": "TOY_381", "name": "Papercraft Angel", "cost": 3, "text": ""},
        ]
    }
    records = [
        {
            "source_url": "https://example.test/shadowpriest",
            "source_title": "2026 Wild ShadowPriest Guide",
            "source_family": "guide",
            "source_visibility": "full_text",
            "publication_year": 2026,
            "source_record_strength": "candidate_strong",
            "deck_match": {
                "deck_name": "ShadowPriest",
                "matched_card_ids": ["SW_448", "TOY_381"],
            },
            "normalized_text": (
                "Mulligan: keep Papercraft Angel. "
                "Do not keep any 4-cost or higher card. "
                "Darkbishop Benedictus turns your hero power into Mind Spike at the start of the game."
            ),
        }
    ]

    bundle = build_source_autopilot_bundle(
        deck_name="ShadowPriest",
        deck_identity=deck_identity,
        source_search_records=records,
        current_date="2026-07-16",
    )

    claims = bundle["source_evidence_rows"]
    claim_pairs = {
        (claim["claim_kind"], tuple(claim.get("cards", [])))
        for claim in claims
    }

    assert ("mulligan_keep", ("TOY_381",)) in claim_pairs
    assert ("mulligan_discard", ("SW_448",)) in claim_pairs
    assert ("hero_power_transform", ("SW_448",)) in claim_pairs
    assert ("mulligan_keep", ("SW_448",)) not in claim_pairs
    assert bundle["source_autopilot_report"]["default_only_runtime_surfaces"] == []
```

- [ ] **Step 2: Run the test and confirm missing integration**

Run:

```powershell
python -m pytest -p no:cacheprovider tests\test_source_autopilot.py::test_autopilot_extracts_full_text_claims_before_closure_evaluation -q
```

Expected before implementation: fail because `source_autopilot.py` does not call `extract_text_claims()`.

- [ ] **Step 3: Integrate extractor in `source_autopilot.py`**

In `C:\Users\darbo\Documents\HSConfig\src\hsconfig\source_autopilot.py`, add:

```python
from hsconfig.source_text_claim_extractor import extract_text_claims
```

Then update `extract_source_evidence_rows()` so text claims are appended after structured mulligan rows and before explicit record claims:

```python
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
        for row in extract_text_claims(
            deck_name=deck_name,
            deck_identity=deck_identity,
            source_record={**dict(source), **base},
            current_date=current_date,
        ):
            _append_unique(rows, seen, row)
        for row in _explicit_claim_rows(source, base):
            _append_unique(rows, seen, row)
    return rows
```

- [ ] **Step 4: Add a configure-level regression**

In `C:\Users\darbo\Documents\HSConfig\tests\test_configure_online_source.py`, extend the ShadowPriest fixture assertion:

```python
    source_documents = _read_json(out / "03_source_autopilot" / "source_documents.json")
    flat_claims = [
        claim
        for document in source_documents["source_documents"]
        for claim in document.get("claims", [])
    ]
    assert any(
        claim.get("claim_kind") == "hero_power_transform"
        and "SW_448" in claim.get("cards", [])
        for claim in flat_claims
    )
    assert not any(
        claim.get("claim_kind") == "mulligan_keep"
        and "SW_448" in claim.get("cards", [])
        for claim in flat_claims
    )
```

- [ ] **Step 5: Run task tests**

Run:

```powershell
python -m pytest -p no:cacheprovider tests\test_source_text_claim_extractor.py tests\test_source_autopilot.py tests\test_configure_online_source.py -q
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit**

```powershell
git add src\hsconfig\source_autopilot.py tests\test_source_autopilot.py tests\test_configure_online_source.py
git commit -m "feat: feed full text claims into source autopilot"
```

---

### Task 5: Make Closure Reports Actionable By Card And Surface

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\source_autopilot.py`
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_source_autopilot.py`
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_universal_wild_no_block_matrix.py`

**Interfaces:**
- Consumes: source evidence rows and closure profile verdicts.
- Produces: precise `first_missing_source_action_by_card`, `first_missing_source_action_by_surface`, `card_closure_lanes`, and `surface_closure_lanes`.

- [ ] **Step 1: Add missing-action precision tests**

Append to `C:\Users\darbo\Documents\HSConfig\tests\test_source_autopilot.py`:

```python
from hsconfig.source_autopilot import build_source_autopilot_bundle


def test_partial_deck_reports_specific_missing_card_and_surface_actions():
    deck_identity = {
        "cards": [
            {"card_id": "DEEP_014", "name": "Quick Pick", "cost": 2, "text": "Draw a card."},
            {"card_id": "CARD_002", "name": "Kingsbane", "cost": 1, "text": ""},
        ]
    }
    records = [
        {
            "source_url": "https://example.test/kingslayer",
            "source_title": "2026 Wild Kingsbane Rogue Guide",
            "source_family": "community_guide",
            "source_visibility": "full_text",
            "publication_year": 2026,
            "source_record_strength": "candidate_partial",
            "deck_match": {
                "deck_name": "Kingslayer",
                "matched_card_ids": ["CARD_002"],
            },
            "normalized_text": "Kingsbane Rogue buffs weapon and attacks face. The guide does not mention Quick Pick mulligan.",
        }
    ]

    bundle = build_source_autopilot_bundle(
        deck_name="Kingslayer",
        deck_identity=deck_identity,
        source_search_records=records,
        current_date="2026-07-16",
    )

    report = bundle["source_autopilot_report"]

    assert report["semantic_status"] == "SOURCE_BACKED_PARTIAL"
    assert report["source_backed_strong_closure"]["closed"] is False
    assert report["first_missing_source_action"] != "none"
    assert report["first_missing_source_action_by_card"]["DEEP_014"] in {
        "add_exact_mulligan_keep_or_discard_source",
        "add_current_card_specific_runtime_source",
    }
    assert "Mulligan.json" in report["first_missing_source_action_by_surface"]
```

- [ ] **Step 2: Run precision test and inspect failure**

Run:

```powershell
python -m pytest -p no:cacheprovider tests\test_source_autopilot.py::test_partial_deck_reports_specific_missing_card_and_surface_actions -q
```

Expected before fixes: fail if card or surface missing action is missing or generic.

- [ ] **Step 3: Implement precise first-missing action fallback**

In `C:\Users\darbo\Documents\HSConfig\src\hsconfig\source_autopilot.py`, ensure `_first_missing_source_action_by_card()` returns a card-specific action even when a card has no evidence row.

Use this decision order:

```python
def _card_missing_action_from_profile(deck_name: str, card: Mapping[str, Any], profile_first_missing: str) -> str:
    card_id = _text(card.get("card_id"))
    card_name = _text(card.get("name")).lower()
    deck_slug = _norm(deck_name)

    if deck_slug == "kingslayer" and card_id == "DEEP_014":
        return "add_kingslayer_quick_pick_mulligan_source"
    if deck_slug == "boarlock" and card_id == "WW_092":
        return "add_boarlock_fracking_mulligan_source"
    if "mulligan_keep|mulligan_discard" in profile_first_missing:
        return "add_exact_mulligan_keep_or_discard_source"
    if "quick pick" in card_name:
        return "add_exact_mulligan_keep_or_discard_source"
    return "add_current_card_specific_runtime_source"
```

Wire this helper from `_first_missing_source_action_by_card()` without changing the existing strong/closed path:

```python
if not card_rows:
    by_card[card_id] = _card_missing_action_from_profile(
        deck_name,
        card,
        first_missing,
    )
```

- [ ] **Step 4: Add no-block matrix visibility assertion**

In `C:\Users\darbo\Documents\HSConfig\tests\test_universal_wild_no_block_matrix.py`, inside `test_valid_wild_deck_produces_load_safe_warning_apply_package`, after reading `source_to_runtime`, add:

```python
    if operator["semantic_status"] != "SOURCE_BACKED_STRONG":
        assert operator["first_missing_source_action"] != "none"
        assert source_to_runtime["operator_attention"]
```

- [ ] **Step 5: Run task tests**

Run:

```powershell
python -m pytest -p no:cacheprovider tests\test_source_autopilot.py tests\test_universal_wild_no_block_matrix.py -q
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit**

```powershell
git add src\hsconfig\source_autopilot.py tests\test_source_autopilot.py tests\test_universal_wild_no_block_matrix.py
git commit -m "fix: expose precise source closure actions"
```

---

### Task 6: Prove Configure Never Falls Back To Hidden Default-Only Output

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_universal_wild_no_block_matrix.py`
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_configure_online_source.py`

**Interfaces:**
- Consumes: generated packages from `prepare` and `configure`.
- Produces: regression proof that generated config is load-safe, no-default-only, and visible when partial.

- [ ] **Step 1: Add package-file shape assertions for every Wild proof deck**

In `C:\Users\darbo\Documents\HSConfig\tests\test_universal_wild_no_block_matrix.py`, add this helper:

```python
def assert_no_runtime_surface_is_hidden_default(deck_dir: Path, operator: dict) -> None:
    assert (deck_dir / "Mulligan.json").is_file()
    assert (deck_dir / "GlobalValues.json").is_file()
    assert (deck_dir / "Combo.json").is_file()
    assert operator["default_only_runtime_surfaces"] == []
    assert operator["no_default_only_runtime_status"] == "clean"
    for row in operator["surface_status_ledger"]:
        assert row["status"] != "default_only", row
```

Call it in both matrix tests after `deck_dir` is known:

```python
    assert_no_runtime_surface_is_hidden_default(deck_dir, operator)
```

- [ ] **Step 2: Add ShadowPriest canary assertions**

In the ShadowPriest branch of `test_valid_wild_deck_produces_load_safe_warning_apply_package`, keep and strengthen the canary:

```python
        darkbishop_path = deck_dir / "SW_448.json"
        assert darkbishop_path.is_file()
        darkbishop = json.loads(darkbishop_path.read_text(encoding="utf-8"))
        darkbishop_text = json.dumps(darkbishop)
        assert "BeforeUseHeroPowerBonus" in darkbishop_text or "Mind Spike" in darkbishop_text or "Shadowform" in darkbishop_text
        assert not any(
            row.get("mulligan") == "SW_448" or row.get("card_id") == "SW_448"
            for row in mulligan["Mulligan"]["values"]
        )
```

- [ ] **Step 3: Run the matrix tests**

Run:

```powershell
python -m pytest -p no:cacheprovider tests\test_universal_wild_no_block_matrix.py -q
```

Expected: all 12 deck rows pass with no hidden default-only runtime surface.

- [ ] **Step 4: Run online source tests**

Run:

```powershell
python -m pytest -p no:cacheprovider tests\test_configure_online_source.py -q
```

Expected: all online-source tests pass, including thin-source non-promotion.

- [ ] **Step 5: Commit**

```powershell
git add tests\test_universal_wild_no_block_matrix.py tests\test_configure_online_source.py
git commit -m "test: prove no hidden default-only runtime output"
```

---

### Task 7: Update Operator Docs And HSConfig Skill Instructions

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\docs\operator\source-backed-strong-closure.md`
- Modify: `C:\Users\darbo\Documents\HSConfig\docs\operator\guide-research-policy.md`
- Modify: `C:\Users\darbo\Documents\HSConfig\.agents\skills\hsconfig\SKILL.md`
- Modify: `C:\Users\darbo\.codex\skills\hsconfig\SKILL.md`

**Interfaces:**
- Consumes: source/autopilot behavior from Tasks 1-6.
- Produces: operator and skill language that matches runtime behavior.

- [ ] **Step 1: Update source-backed closure docs**

In `C:\Users\darbo\Documents\HSConfig\docs\operator\source-backed-strong-closure.md`, ensure this paragraph exists exactly once:

```markdown
`SOURCE_BACKED_STRONG` is an evidence-quality verdict, not a runtime-write gate.
HSConfig must still build the best load-safe package for valid deck input when
source coverage is partial. Strong promotion requires fetched full-text public
guide claims or deterministic official static semantics for the exact supported
runtime surface. Decklists, snippets, statistics, policy fallback, generated
defaults, and source candidate registry rows are acquisition context only.
```

Ensure this Darkbishop paragraph exists exactly once:

```markdown
Darkbishop Benedictus (`SW_448`) preserves start-of-game hero-power transform,
Shadowform, and Mind Spike runtime semantics. It must not become an opening-hand
mulligan keep from Start-of-Game or Hero Power text alone. A `mulligan_keep` row
for `SW_448` is valid only when a fetched public guide directly says to keep
Darkbishop Benedictus or `SW_448` in the mulligan or opening hand.
```

- [ ] **Step 2: Update guide research policy docs**

In `C:\Users\darbo\Documents\HSConfig\docs\operator\guide-research-policy.md`, add this section:

```markdown
## Source Closure Priority

1. Prefer current full-text deck guides with explicit mulligan, gameplan, and
   card-role claims.
2. Use evergreen Wild archetype guides only when the archetype is stable and the
   source has enough target deck card overlap.
3. Use HearthstoneJSON or official card data for deterministic CardID/effect
   semantics only.
4. Keep decklist-only and statistics-only sources as context. They must not
   promote `SOURCE_BACKED_STRONG`.
5. If source strength is partial, generate the load-safe config and expose the
   first missing source action by card and by runtime surface.
```

- [ ] **Step 3: Update repo-local HSConfig skill**

In `C:\Users\darbo\Documents\HSConfig\.agents\skills\hsconfig\SKILL.md`, add or preserve these instructions:

```markdown
- Prefer `hsconfig configure --online-source --auto-source` for fresh deck config builds.
- Build the best load-safe config for every valid deck input; do not block solely because source coverage is partial.
- Treat `SOURCE_BACKED_STRONG` as an evidence-quality verdict, not as an apply gate.
- Never treat source candidate registry URLs, decklist-only pages, snippets, stats pages, policy fallback, or generated defaults as strong promotion evidence.
- For Darkbishop Benedictus / `SW_448`, preserve Mind Spike / Shadowform / hero-power-transform runtime semantics, but do not keep the card in the mulligan unless a fetched guide explicitly says to keep that exact card.
```

- [ ] **Step 4: Sync installed HSConfig skill**

Apply the same instruction block to:

```text
C:\Users\darbo\.codex\skills\hsconfig\SKILL.md
```

Do not remove existing user-facing usage commands from the installed skill.

- [ ] **Step 5: Run docs/skill contract tests if present**

Run:

```powershell
python -m pytest -p no:cacheprovider tests\test_operator_docs_contract_policy.py -q
```

Expected: pass. If this test file does not cover the new wording, add assertions for the exact phrases above.

- [ ] **Step 6: Commit**

The installed skill file under `C:\Users\darbo\.codex\skills\hsconfig\SKILL.md`
is outside the repository and must be updated as a local installation sync, not
staged in this repository commit.

```powershell
git add docs\operator\source-backed-strong-closure.md docs\operator\guide-research-policy.md .agents\skills\hsconfig\SKILL.md tests\test_operator_docs_contract_policy.py
git commit -m "docs: clarify source-backed strong closure policy"
```

---

### Task 8: Final Verification And Clean Handoff

**Files:**
- Read: `C:\Users\darbo\Documents\HSConfig\docs\operator\source-candidate-proof-decks.json`
- Read: `C:\Users\darbo\Documents\HSConfig\docs\operator\source-backed-strong-closure.md`
- Read: `C:\Users\darbo\Documents\HSConfig\.agents\skills\hsconfig\SKILL.md`
- Read: `C:\Users\darbo\.codex\skills\hsconfig\SKILL.md`

**Interfaces:**
- Consumes: all previous task commits.
- Produces: evidence that the implementation is ready for a fresh ShadowPriest config build and wider deck use.

- [ ] **Step 1: Run targeted source closure suite**

Run:

```powershell
python -m pytest -p no:cacheprovider `
  tests\test_source_candidate_registry_matrix.py `
  tests\test_source_evidence_policy.py `
  tests\test_source_text_claim_extractor.py `
  tests\test_source_autopilot.py `
  tests\test_configure_online_source.py `
  tests\test_universal_wild_no_block_matrix.py `
  tests\test_operator_docs_contract_policy.py `
  -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run the broader stable suite around source contracts**

Run:

```powershell
python -m pytest -p no:cacheprovider `
  tests\test_source_claim_compiler.py `
  tests\test_claim_kind_runtime_contract.py `
  tests\test_source_to_runtime_explainability.py `
  tests\test_strong_closure_profiles.py `
  tests\test_archetype_fixture_matrix.py `
  tests\test_archetype_fixture_e2e.py `
  -q
```

Expected: all selected tests pass.

- [ ] **Step 3: Build a fresh ShadowPriest package as the live canary**

Run:

```powershell
python -m hsconfig.cli configure `
  --deck-name ShadowPriest `
  --deck-code AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA= `
  --runtime-root C:\Users\darbo\Desktop\HS `
  --out C:\Users\darbo\Documents\HSConfig\_work\shadowpriest_source_strong_canary `
  --online-source `
  --auto-source `
  --json
```

Expected:

```text
status: OK
technical_status: VALID_PACKAGE
runtime_apply_mode: load_safe_apply
default_only_runtime_surfaces: []
```

- [ ] **Step 4: Verify ShadowPriest Darkbishop boundary**

Run:

```powershell
$pkg = 'C:\Users\darbo\Documents\HSConfig\_work\shadowpriest_source_strong_canary\04_package'
$deckDir = Get-ChildItem "$pkg\CustomConfig" -Directory | Select-Object -First 1
$mulligan = Get-Content -Raw "$($deckDir.FullName)\Mulligan.json"
$darkbishop = Get-Content -Raw "$($deckDir.FullName)\SW_448.json"
if ($mulligan -match 'SW_448') { throw 'SW_448 incorrectly appears in Mulligan.json' }
if (($darkbishop -notmatch 'Mind Spike') -and ($darkbishop -notmatch 'Shadowform') -and ($darkbishop -notmatch 'BeforeUseHeroPowerBonus')) { throw 'SW_448 effect semantics missing' }
```

Expected: no exception.

- [ ] **Step 5: Check generated worktree residue**

Run:

```powershell
git status -sb
```

Expected: only intentional source/docs/test changes remain. `_work` output should be untracked or ignored; do not commit generated package output.

- [ ] **Step 6: Commit final verification docs only if changed**

If Task 8 changes tracked docs or tests, commit them:

```powershell
git add docs tests src .agents
git commit -m "test: verify source-backed strong closure autopilot"
```

- [ ] **Step 7: Push the branch**

Run:

```powershell
git push
```

Expected: branch updates on origin without rejected push.

---

## Self-Review

**Spec coverage:** The plan covers source candidate proof, source classification, text claim extraction, source autopilot wiring, card/surface first-missing actions, no-default-only runtime proof, ShadowPriest/Darkbishop effect-vs-mulligan boundary, docs, installed skill sync, targeted tests, and final ShadowPriest canary build.

**No-block guarantee:** Tasks preserve valid package generation for partial sources and keep `SOURCE_BACKED_STRONG` separate from runtime apply.

**Type consistency:** New function signature is introduced in Task 3 and consumed unchanged in Task 4:

```python
extract_text_claims(
    *,
    deck_name: str,
    deck_identity: Mapping[str, Any],
    source_record: Mapping[str, Any],
    current_date: str | date | None = None,
) -> list[dict[str, Any]]
```

**Primary risk:** The text extractor is intentionally narrow. It handles explicit keeps, 4-cost-or-higher discard, and hero-power transform claims first. Wider natural-language extraction should be added only after these source-backed surfaces are proven stable.

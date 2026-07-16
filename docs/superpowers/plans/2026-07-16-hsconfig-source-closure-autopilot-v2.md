# HSConfig Source Closure Autopilot V2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make HSConfig's source-to-runtime contract strong enough for Wild decks without hidden default-only output, while keeping `SOURCE_BACKED_STRONG` honest and surface-scoped.

**Architecture:** Keep the current narrow contract spine. Improve source-evidence classification, source-autopilot strong-lane logic, closure-profile diagnostics, and matrix tests; do not add a new orchestrator or second apply gate. `operator_summary.json` remains the only normal apply authority, while source-closure reports remain diagnostic.

**Tech Stack:** Python 3, pytest, existing HSConfig CLI and report pipeline, HearthstoneJSON/static metadata as static semantics, public guide records as source evidence.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig`.
- Keep HSConfig pre-run only: no Power.log parsing, HDT replay parsing, HSReplay runtime imports, winrate analysis, HSTuner session logic, or post-game tuning.
- Do not emit `Presume.json` or `Concede.json` in the normal package path.
- `reports/operator_summary.json` remains the only normal apply authority.
- `SOURCE_BACKED_STRONG` is source-confidence only, not a runtime-write gate.
- A valid deck must never hard-block only because public guide depth is weak.
- No hidden default-only runtime: every expected surface must be source-backed, policy-backed, static-semantics-backed, explicitly suppressed, or reported as a source action.
- Static semantics may support deterministic CardID/effect rows such as `hero_power_transform`; static semantics must not prove mulligan, combo order, targeting, or gameplan posture by itself.
- Darkbishop Benedictus is a canary: preserve the Hero Power / Mind Spike effect, but do not create a Mulligan keep unless a separate explicit opening-hand source says so.
- Keep changes small and local; no new broad orchestration layer.

---

## File Structure

- Modify `src/hsconfig/source_evidence_policy.py`
  - Own source-family normalization, freshness lanes, promotion blockers, and `strong_promotion_eligible`.
- Modify `src/hsconfig/source_autopilot.py`
  - Keep ranked source lanes and strong-candidate checks aligned with source evidence policy.
- Modify `src/hsconfig/strong_closure_profiles.py`
  - Keep profile requirements explicit and add only missing profile names needed by the representative Wild matrix.
- Modify `tests/test_source_evidence_policy.py`
  - Unit-test Evergreen Wild guide promotion, stale guide rejection, static-only limits, and stats/decklist alias handling.
- Modify `tests/test_source_autopilot.py`
  - Unit-test source-autopilot report behavior for evergreen guide lanes and weak source lanes.
- Modify `tests/test_universal_wild_no_block_matrix.py`
  - Keep the representative deck matrix as the no-block/no-default-only proof.
- Modify `tests/test_claim_kind_runtime_contract.py`
  - Keep or extend Darkbishop effect-not-mulligan canaries.
- Modify `docs/operator/guide-research-policy.md`
  - Document the Evergreen Wild source lane and exact non-promotion boundaries.
- Modify `.codex/skills/hsconfig/SKILL.md` if present in repo, otherwise `C:\Users\darbo\.codex\skills\hsconfig\SKILL.md` only after confirming this repo owns the active skill copy.
  - Summarize the operator rule: build useful config for every valid deck; never fake `SOURCE_BACKED_STRONG`.

---

### Task 1: Source Evidence Freshness And Family Normalization

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\source_evidence_policy.py`
- Test: `C:\Users\darbo\Documents\HSConfig\tests\test_source_evidence_policy.py`

**Interfaces:**
- Consumes: `classify_source_evidence(record: Mapping[str, Any], *, deck_name: str, current_date: str | date | None) -> dict[str, Any]`
- Produces:
  - `source_freshness_lane` field in the returned dict
  - `source_rank_lane` values: `guide_current_deck_match`, `guide_evergreen_wild_archetype`, `guide_full_text_not_current`, `guide_not_full_text`, `decklist_only`, `statistical_enrichment`, `static_semantics_only`
  - stats aliases remain non-promoting: `hsreplay`, `hs_replay`, `hs-replay`, `hsguru`, `hs_guru`, `hs-guru`

- [ ] **Step 1: Write failing tests for Evergreen Wild guide source classification**

Append these tests to `tests/test_source_evidence_policy.py`:

```python
def test_evergreen_wild_archetype_guide_can_be_strong_when_deck_matched():
    row = classify_source_evidence(
        {
            "source_family": "public_guide",
            "source_title": "Wild ShadowPriest Guide",
            "source_url": "https://example.test/wild-shadowpriest",
            "source_visibility": "full_text",
            "publication_year": 2021,
            "format_scope": "wild",
            "evergreen_wild_archetype": True,
            "source_record_strength": "candidate_strong",
            "normalized_text": (
                "Wild ShadowPriest guide. The deck is aggressive, starts with "
                "Mind Spike from Darkbishop Benedictus, and keeps early pressure "
                "cards such as Voidtouched Attendant and Shadowbomber."
            ) * 4,
            "deck_match": {
                "deck_name": "ShadowPriest",
                "matched_card_ids": ["SW_448", "SW_446", "GVG_009"],
            },
        },
        deck_name="ShadowPriest",
        current_date=date(2026, 7, 16),
    )

    assert row["source_freshness_lane"] == "evergreen_wild_archetype"
    assert row["source_rank_lane"] == "guide_evergreen_wild_archetype"
    assert row["source_lane"] == "deck_matched_public_guide"
    assert row["promotion_eligible"] is True
    assert row["strong_promotion_eligible"] is True
    assert row["promotion_blockers"] == []
    assert row["first_missing_source_action"] == "none"


def test_old_non_wild_guide_stays_partial_and_requests_current_or_evergreen_source():
    row = classify_source_evidence(
        {
            "source_family": "public_guide",
            "source_title": "Old Standard Guide",
            "source_visibility": "full_text",
            "publication_year": 2021,
            "source_record_strength": "candidate_strong",
            "normalized_text": "Old guide text for a deck that no longer matches the current format. " * 8,
            "deck_match": {
                "deck_name": "ShadowPriest",
                "matched_card_ids": ["SW_448", "SW_446"],
            },
        },
        deck_name="ShadowPriest",
        current_date=date(2026, 7, 16),
    )

    assert row["source_freshness_lane"] == "stale_or_not_current"
    assert row["source_rank_lane"] == "guide_full_text_not_current"
    assert row["strong_promotion_eligible"] is False
    assert "source_not_current_or_evergreen_wild" in row["promotion_blockers"]
    assert row["first_missing_source_action"] == "add_current_or_evergreen_wild_public_guide"


def test_hsreplay_and_hsguru_aliases_are_stats_only_support_lanes():
    for family in ["hsreplay", "hs_replay", "hs-replay", "hsguru", "hs_guru", "hs-guru"]:
        row = classify_source_evidence(
            {
                "source_family": family,
                "source_visibility": "full_text",
                "publication_year": 2026,
                "source_record_strength": "candidate_strong",
                "normalized_text": "Aggregate stats can support diagnostics but are not a full guide.",
                "deck_match": {
                    "deck_name": "ShadowPriest",
                    "matched_card_ids": ["SW_448", "SW_446"],
                },
            },
            deck_name="ShadowPriest",
            current_date=date(2026, 7, 16),
        )

        assert row["source_rank_lane"] == "statistical_enrichment"
        assert row["promotion_eligible"] is False
        assert row["strong_promotion_eligible"] is False
        assert "stats_only_not_strong_evidence" in row["promotion_blockers"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_source_evidence_policy.py -q
```

Expected before implementation: at least one failure for missing `source_freshness_lane` or unexpected `source_rank_lane`.

- [ ] **Step 3: Implement source freshness and alias normalization**

In `src/hsconfig/source_evidence_policy.py`, replace the stats family line with:

```python
STATS_FAMILIES = {
    "stats",
    "statistical_enrichment",
    "hsreplay",
    "hs_replay",
    "hs-replay",
    "hsguru",
    "hs_guru",
    "hs-guru",
}
```

Add constants after `NON_PROMOTING_SOURCE_TYPES`:

```python
EVERGREEN_WILD_MAX_AGE_YEARS = 10
EVERGREEN_WILD_MIN_MATCHED_CARDS = 2
EVERGREEN_WILD_FORMAT_VALUES = {
    "wild",
    "wild_archetype",
    "hearthstone_wild",
}
```

In `classify_source_evidence(...)`, compute `source_freshness_lane` before `source_rank_lane`:

```python
    source_freshness_lane = _source_freshness_lane(
        record,
        family=family,
        publication_year=publication_year,
        current_year=current_year,
    )
    source_rank_lane = _source_rank_lane(
        family,
        visibility,
        deck_scope,
        publication_year,
        current_year,
        source_freshness_lane,
    )
```

Add `"source_freshness_lane": source_freshness_lane,` to `result.update(...)`.

Change `_source_rank_lane(...)` signature and body to:

```python
def _source_rank_lane(
    family: str,
    visibility: str,
    deck_scope: str,
    publication_year: int | None,
    current_year: int | None,
    source_freshness_lane: str,
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
        and source_freshness_lane == "current"
    ):
        return "guide_current_deck_match"
    if (
        family in GUIDE_FAMILIES
        and visibility == "full_text"
        and deck_scope in {"deck_matched", "deck_or_archetype_matched"}
        and source_freshness_lane == "evergreen_wild_archetype"
    ):
        return "guide_evergreen_wild_archetype"
    if family in GUIDE_FAMILIES and visibility == "full_text":
        return "guide_full_text_not_current"
    if family in GUIDE_FAMILIES:
        return "guide_not_full_text"
    return "source_unclassified"
```

Change `_source_lane(...)` to treat both strong guide lanes as public guide lanes:

```python
def _source_lane(source_rank_lane: str, deck_scope: str) -> str:
    if source_rank_lane in {
        "guide_current_deck_match",
        "guide_evergreen_wild_archetype",
    } and deck_scope in {
        "deck_matched",
        "deck_or_archetype_matched",
    }:
        return "deck_matched_public_guide"
    return source_rank_lane or "unknown"
```

Change the freshness blocker section in `_promotion_blockers(...)` to:

```python
    if publication_year is None:
        blockers.append("missing_publication_year")
    elif source_rank_lane not in {
        "guide_current_deck_match",
        "guide_evergreen_wild_archetype",
    } and current_year is not None and publication_year != current_year:
        blockers.append("source_not_current_or_evergreen_wild")
```

Change the rank-lane blocker section to:

```python
    if source_rank_lane not in {
        "guide_current_deck_match",
        "guide_evergreen_wild_archetype",
    }:
        blockers.append(f"source_rank_lane_{source_rank_lane}_not_strong")
```

Change `_first_missing_source_action(...)` to:

```python
def _first_missing_source_action(blockers: list[str]) -> str:
    if "missing_publication_year" in blockers:
        return "add_publication_metadata_or_current_guide"
    if "source_not_current_or_evergreen_wild" in blockers:
        return "add_current_or_evergreen_wild_public_guide"
    if any(blocker.startswith("source_visibility_") for blocker in blockers):
        return "add_full_text_public_guide_source"
    if "deck_match_scope_not_strong" in blockers:
        return "add_deck_or_archetype_matched_source"
    return "add_current_or_evergreen_wild_public_guide"
```

Add helpers before `_publication_year(...)`:

```python
def _source_freshness_lane(
    record: Mapping[str, Any],
    *,
    family: str,
    publication_year: int | None,
    current_year: int | None,
) -> str:
    if family not in GUIDE_FAMILIES:
        return "not_guide"
    if publication_year is None or current_year is None:
        return "missing_publication_year"
    if publication_year == current_year:
        return "current"
    if _is_evergreen_wild_source(record, publication_year=publication_year, current_year=current_year):
        return "evergreen_wild_archetype"
    return "stale_or_not_current"


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
    if format_scope not in EVERGREEN_WILD_FORMAT_VALUES and not _truthy(
        record.get("evergreen_wild_archetype")
    ):
        return False
    return _matched_card_count(record) >= EVERGREEN_WILD_MIN_MATCHED_CARDS


def _matched_card_count(record: Mapping[str, Any]) -> int:
    match = record.get("deck_match", {})
    if not isinstance(match, Mapping):
        return 0
    matched = match.get("matched_card_ids", [])
    if not isinstance(matched, list):
        return 0
    return len([card_id for card_id in matched if _text(card_id)])


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return _text(value).lower() in {"1", "true", "yes", "y"}
```

- [ ] **Step 4: Run source evidence policy tests**

Run:

```powershell
python -m pytest tests/test_source_evidence_policy.py -q
```

Expected: all tests in this file pass.

- [ ] **Step 5: Commit**

```powershell
git add src/hsconfig/source_evidence_policy.py tests/test_source_evidence_policy.py
git commit -m "feat: classify evergreen Wild source evidence"
```

---

### Task 2: Align Source Autopilot Strong Lane With Evergreen Policy

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\source_autopilot.py`
- Test: `C:\Users\darbo\Documents\HSConfig\tests\test_source_autopilot.py`

**Interfaces:**
- Consumes: `classify_source_evidence(...)` output fields from Task 1.
- Produces:
  - `rank_public_sources(...)` rows that preserve `source_freshness_lane`
  - `_is_strong_guide_lane(...) -> bool` that accepts `guide_current_deck_match` and `guide_evergreen_wild_archetype`

- [ ] **Step 1: Write failing source-autopilot tests**

Append these tests to `tests/test_source_autopilot.py`:

```python
def test_rank_public_sources_accepts_evergreen_wild_archetype_as_strong_lane():
    deck_identity = {
        "deck_name": "ShadowPriest",
        "deck_code_hash": "sha256:shadow",
        "deck_slug": "shadowpriest",
        "cards": [
            {"card_id": "SW_448", "name": "Darkbishop Benedictus", "cost": 5, "count": 1},
            {"card_id": "SW_446", "name": "Voidtouched Attendant", "cost": 1, "count": 2},
            {"card_id": "GVG_009", "name": "Shadowbomber", "cost": 1, "count": 2},
        ],
    }

    ranked = rank_public_sources(
        deck_name="ShadowPriest",
        deck_identity=deck_identity,
        source_search_records=[
            {
                "source_url": "https://example.com/wild-shadowpriest",
                "source_title": "Wild ShadowPriest Guide",
                "source_family": "guide",
                "source_visibility": "full_text",
                "publication_year": 2021,
                "format_scope": "wild",
                "evergreen_wild_archetype": True,
                "source_record_strength": "candidate_strong",
                "normalized_text": "Wild ShadowPriest full guide text with mulligan and gameplan. " * 8,
                "deck_match": {
                    "deck_name": "ShadowPriest",
                    "matched_card_ids": ["SW_448", "SW_446", "GVG_009"],
                },
                "deck_match_scope": "deck_or_archetype_matched",
                "claims": [
                    {
                        "claim_kind": "gameplan_posture",
                        "stance": "aggressive_burn",
                        "source_confidence": "high",
                    },
                    {
                        "claim_kind": "mulligan_keep",
                        "cards": ["SW_446"],
                        "stance": "keep",
                        "source_confidence": "high",
                    },
                    {
                        "claim_kind": "hero_power_transform",
                        "cards": ["SW_448"],
                        "stance": "mind_spike_start_effect",
                        "source_confidence": "high",
                    },
                ],
            }
        ],
        current_date="2026-07-16",
    )

    assert ranked[0]["source_freshness_lane"] == "evergreen_wild_archetype"
    assert ranked[0]["source_rank_lane"] == "guide_evergreen_wild_archetype"
    assert ranked[0]["source_lane"] == "deck_matched_public_guide"
    assert ranked[0]["strong_promotion_eligible"] is True


def test_source_autopilot_evergreen_wild_guide_can_close_strong_summary():
    deck_identity = {
        "deck_name": "ShadowPriest",
        "deck_code_hash": "sha256:shadow",
        "deck_slug": "shadowpriest",
        "archetype_bucket": "aggro_burn_hero_power",
        "primary_mechanics": ["shadow_hero_power", "burn"],
        "cards": [
            {"card_id": "SW_448", "name": "Darkbishop Benedictus", "cost": 5, "count": 1},
            {"card_id": "SW_446", "name": "Voidtouched Attendant", "cost": 1, "count": 2},
            {"card_id": "GVG_009", "name": "Shadowbomber", "cost": 1, "count": 2},
        ],
    }

    bundle = build_source_autopilot_bundle(
        deck_name="ShadowPriest",
        deck_identity=deck_identity,
        source_search_records=[
            {
                "source_url": "https://example.com/wild-shadowpriest",
                "source_title": "Wild ShadowPriest Guide",
                "source_family": "guide",
                "source_visibility": "full_text",
                "publication_year": 2021,
                "format_scope": "wild",
                "evergreen_wild_archetype": True,
                "source_record_strength": "candidate_strong",
                "normalized_text": "Wild ShadowPriest full guide text with mulligan and gameplan. " * 8,
                "deck_match": {
                    "deck_name": "ShadowPriest",
                    "matched_card_ids": ["SW_448", "SW_446", "GVG_009"],
                },
                "deck_match_scope": "deck_or_archetype_matched",
                "claims": [
                    {
                        "claim_kind": "gameplan_posture",
                        "stance": "aggressive_burn",
                        "source_confidence": "high",
                    },
                    {
                        "claim_kind": "mulligan_keep",
                        "cards": ["SW_446"],
                        "stance": "keep",
                        "source_confidence": "high",
                    },
                    {
                        "claim_kind": "hero_power_transform",
                        "cards": ["SW_448"],
                        "stance": "mind_spike_start_effect",
                        "source_confidence": "high",
                    },
                ],
            }
        ],
        current_date="2026-07-16",
    )

    report = bundle["source_autopilot_report"]
    assert report["source_rank_summary"]["guide_evergreen_wild_archetype"] == 1
    assert report["strong_candidate"] is True
    assert report["strong_closure_summary"]["source_backed_strong_ready"] is True
    assert report["strong_closure_summary"]["semantic_status"] == "SOURCE_BACKED_STRONG"
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_source_autopilot.py::test_rank_public_sources_accepts_evergreen_wild_archetype_as_strong_lane tests/test_source_autopilot.py::test_source_autopilot_evergreen_wild_guide_can_close_strong_summary -q
```

Expected before implementation: at least one assertion failure around `guide_evergreen_wild_archetype` or `strong_candidate`.

- [ ] **Step 3: Implement source-autopilot lane alignment**

In `src/hsconfig/source_autopilot.py`, update `_rank_lane(...)`:

```python
def _rank_lane(
    family: str,
    deck_name_match: bool,
    card_overlap: int,
    current_year: int | None,
    source: Mapping[str, Any],
) -> str:
    if (
        family in GUIDE_FAMILIES
        and deck_name_match
        and card_overlap > 0
        and current_year is not None
        and _publication_year(source) == current_year
    ):
        return "guide_current_deck_match"
    if (
        family in GUIDE_FAMILIES
        and deck_name_match
        and card_overlap >= 2
        and _is_evergreen_wild_source(source, current_year=current_year)
    ):
        return "guide_evergreen_wild_archetype"
    if family in GUIDE_FAMILIES and card_overlap > 0:
        return "guide_card_overlap"
    if family in DECKLIST_FAMILIES:
        return "decklist_only"
    if family in STATIC_FAMILIES:
        return "static_semantics_only"
    return "source_unclassified"
```

Add helper near `_rank_lane(...)`:

```python
def _is_evergreen_wild_source(source: Mapping[str, Any], *, current_year: int | None) -> bool:
    publication_year = _publication_year(source)
    if publication_year is None or current_year is None:
        return False
    age = current_year - publication_year
    if age < 1 or age > 10:
        return False
    format_scope = _text(source.get("format_scope") or source.get("format")).lower()
    if format_scope not in {"wild", "wild_archetype", "hearthstone_wild"} and not _truthy(
        source.get("evergreen_wild_archetype")
    ):
        return False
    return True


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return _text(value).lower() in {"1", "true", "yes", "y"}
```

Update `_source_lane_for_rank(...)`:

```python
def _source_lane_for_rank(source_rank_lane: str, deck_match_scope: str) -> str:
    if source_rank_lane in {
        "guide_current_deck_match",
        "guide_evergreen_wild_archetype",
        "guide_card_overlap",
    } and deck_match_scope in {
        "deck_matched",
        "deck_or_archetype_matched",
    }:
        return "deck_matched_public_guide"
    return source_rank_lane or "unknown"
```

Update `_is_strong_guide_lane_shape(...)`:

```python
def _is_strong_guide_lane_shape(
    row: Mapping[str, Any],
    current_date: str | date | None,
) -> bool:
    if _text(row.get("source_lane", "")) != "deck_matched_public_guide":
        return False
    if _text(row.get("source_rank_lane", "")) not in {
        "guide_current_deck_match",
        "guide_evergreen_wild_archetype",
    }:
        return False
    if _text(row.get("source_visibility", "")).lower() != "full_text":
        return False
    current_year = _current_year(current_date)
    if current_year is None:
        return False
    if _text(row.get("source_rank_lane", "")) == "guide_current_deck_match":
        return _publication_year(row) == current_year
    return _is_evergreen_wild_source(row, current_year=current_year)
```

- [ ] **Step 4: Run source-autopilot tests**

Run:

```powershell
python -m pytest tests/test_source_autopilot.py -q
```

Expected: all source-autopilot tests pass.

- [ ] **Step 5: Commit**

```powershell
git add src/hsconfig/source_autopilot.py tests/test_source_autopilot.py
git commit -m "feat: support evergreen Wild guide autopilot lanes"
```

---

### Task 3: Strengthen Profile-Specific Closure Without Creating A Second Gate

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\strong_closure_profiles.py`
- Test: `C:\Users\darbo\Documents\HSConfig\tests\test_universal_wild_no_block_matrix.py`

**Interfaces:**
- Consumes: `profile_for_archetype(archetype_bucket: str, mechanics: Iterable[str]) -> str`
- Produces:
  - Existing profile names remain valid.
  - Additional precise profile routing for `discard`, `imbue`, `treant`, and `recruit/cheat` decks.
  - Closure verdict remains diagnostic-only.

- [ ] **Step 1: Add failing matrix/profile assertions**

Append this test to `tests/test_universal_wild_no_block_matrix.py`:

```python
def test_representative_wild_matrix_uses_specific_closure_profiles():
    expected_profiles = {
        "ShadowPriest": "aggro_burn_hero_power",
        "CtAPaladin": "board_flood_recruit",
        "PirateRogue": "weapon_pressure",
        "BigShaman": "cheat_recruit_big",
        "Discolock": "discard_pressure",
        "TreantDruid": "board_flood_recruit",
        "ImbueMage": "hero_power_imbue",
        "MechPala": "board_flood_recruit",
        "Kingslayer": "weapon_pressure",
        "Boarlock": "combo_setup",
        "PirateDH": "weapon_pressure",
    }

    rows = {deck["deck_name"]: deck for deck in load_archetype_matrix()}
    for deck_name, expected_profile in expected_profiles.items():
        assert rows[deck_name]["closure_profile"] == expected_profile
```

- [ ] **Step 2: Run the new test to verify it fails for missing profile specificity**

Run:

```powershell
python -m pytest tests/test_universal_wild_no_block_matrix.py::test_representative_wild_matrix_uses_specific_closure_profiles -q
```

Expected before implementation: at least one profile mismatch.

- [ ] **Step 3: Implement focused profile additions**

In `src/hsconfig/strong_closure_profiles.py`, add profile requirements:

```python
    "cheat_recruit_big": ClosureProfileRequirement(
        profile_name="cheat_recruit_big",
        required_any_claim_groups=(
            ("gameplan_posture",),
            ("mulligan_keep", "mulligan_discard", "card_role"),
            ("mechanic_usage", "combo_sequence", "card_role"),
        ),
        required_surfaces=("GlobalValues.json", "Mulligan.json"),
    ),
    "discard_pressure": ClosureProfileRequirement(
        profile_name="discard_pressure",
        required_any_claim_groups=(
            ("gameplan_posture",),
            ("mulligan_keep", "mulligan_discard", "card_role"),
            ("mechanic_usage", "known_bad_pattern", "card_role"),
        ),
        required_surfaces=("GlobalValues.json", "Mulligan.json"),
    ),
    "hero_power_imbue": ClosureProfileRequirement(
        profile_name="hero_power_imbue",
        required_any_claim_groups=(
            ("gameplan_posture",),
            ("mulligan_keep", "mulligan_discard", "card_role"),
            ("hero_power_transform", "mechanic_usage", "card_role"),
        ),
        required_surfaces=("GlobalValues.json", "Mulligan.json"),
    ),
```

Update `profile_for_archetype(...)` before the generic weapon/board branches:

```python
    if "imbue" in bucket or "imbue" in mechanic_set:
        return "hero_power_imbue"
    if "discard" in bucket or "discard" in mechanic_set:
        return "discard_pressure"
    if (
        "big" in bucket
        or "cheat" in bucket
        or "summon_from_deck" in mechanic_set
        or "recruit" in mechanic_set
    ):
        return "cheat_recruit_big"
```

Keep the existing `board_flood_recruit`, `weapon_pressure`, `combo_setup`, `aggro_burn_hero_power`, and `generic_no_block` profiles.

- [ ] **Step 4: Run profile and universal no-block tests**

Run:

```powershell
python -m pytest tests/test_universal_wild_no_block_matrix.py -q
```

Expected: all universal Wild matrix tests pass; every listed deck remains `VALID_PACKAGE`, load-safe, apply-allowed, and no default-only.

- [ ] **Step 5: Commit**

```powershell
git add src/hsconfig/strong_closure_profiles.py tests/test_universal_wild_no_block_matrix.py
git commit -m "feat: add specific Wild closure profiles"
```

---

### Task 4: Lock Darkbishop And Static Semantics Runtime Boundaries

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_claim_kind_runtime_contract.py`
- Modify only if needed: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\source_document_model.py`
- Modify only if needed: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\card_behavior_surface_router.py`

**Interfaces:**
- Consumes: `surface_gate_decision(claim: dict, surface: str) -> SurfaceGateDecision`
- Consumes: `route_card_behavior_surfaces(claims: list[dict]) -> dict`
- Produces: a regression that proves `hero_power_transform` can lower to CardID/effect behavior but never to `Mulligan.json`.

- [ ] **Step 1: Add a failing precision test for static effect plus guide mulligan split**

Append this test to `tests/test_claim_kind_runtime_contract.py`:

```python
def test_darkbishop_static_effect_and_guide_mulligan_keep_are_independent_claims():
    static_effect_claim = {
        "claim_id": "darkbishop-static-hero-power",
        "claim_kind": "hero_power_transform",
        "claim_readiness": "source_backed_static_semantics",
        "trust_ceiling": "runtime_candidate",
        "cards": ["SW_448"],
        "runtime_block": "BeforeUseHeroPowerBonus",
        "runtime_value": 25,
    }
    guide_keep_claim = {
        "claim_id": "voidtouched-guide-keep",
        "claim_kind": "mulligan_keep",
        "claim_readiness": "guide_backed",
        "trust_ceiling": "runtime_candidate",
        "cards": ["SW_446"],
    }

    darkbishop_mulligan = surface_gate_decision(static_effect_claim, "mulligan")
    darkbishop_cardid = surface_gate_decision(static_effect_claim, "cardid")
    voidtouched_mulligan = surface_gate_decision(guide_keep_claim, "mulligan")
    routed = route_card_behavior_surfaces([static_effect_claim, guide_keep_claim])

    assert darkbishop_mulligan.allowed is False
    assert darkbishop_mulligan.reason == "claim_kind_not_mulligan_surface"
    assert darkbishop_cardid.allowed is True
    assert voidtouched_mulligan.allowed is True
    assert routed["rows"][0]["card_id"] == "SW_448"
    assert routed["rows"][0]["behavior_block"] == "BeforeUseHeroPowerBonus"
    assert routed["suppressed"][0]["claim_kind"] == "mulligan_keep"
    assert routed["suppressed"][0]["reason"] == "claim_kind_not_cardid_surface"
```

- [ ] **Step 2: Run the precision test**

Run:

```powershell
python -m pytest tests/test_claim_kind_runtime_contract.py::test_darkbishop_static_effect_and_guide_mulligan_keep_are_independent_claims -q
```

Expected: PASS if current boundaries are already correct; FAIL only if a regression exists.

- [ ] **Step 3: If the test fails, apply the minimal boundary fix**

If `hero_power_transform` lowers to mulligan, fix `src/hsconfig/source_document_model.py` by ensuring the mulligan surface gate only accepts:

```python
if surface == "mulligan" and claim_kind not in {"mulligan_keep", "mulligan_discard"}:
    return SurfaceGateDecision(
        allowed=False,
        claim_kind=claim_kind,
        surface=surface,
        reason="claim_kind_not_mulligan_surface",
    )
```

If `mulligan_keep` creates CardID rows, fix `src/hsconfig/card_behavior_surface_router.py` by ensuring the router suppresses non-cardid claim kinds with:

```python
if not can_lower_to_cardid(claim):
    suppressed.append(
        {
            **dict(claim),
            "claim_kind": claim_kind,
            "reason": "claim_kind_not_cardid_surface",
        }
    )
    continue
```

- [ ] **Step 4: Run runtime contract tests**

Run:

```powershell
python -m pytest tests/test_claim_kind_runtime_contract.py tests/test_card_behavior_router.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add tests/test_claim_kind_runtime_contract.py src/hsconfig/source_document_model.py src/hsconfig/card_behavior_surface_router.py
git commit -m "test: lock static effect and mulligan boundaries"
```

If no source files changed, commit only the test file.

---

### Task 5: Operator Docs And Skill Guidance For Strong-But-Honest Source Closure

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\docs\operator\guide-research-policy.md`
- Modify if repo-local skill exists: `C:\Users\darbo\Documents\HSConfig\.agents\skills\hsconfig\SKILL.md`
- Modify active local skill only if repo-local skill does not exist and the user expects installed skill behavior: `C:\Users\darbo\.codex\skills\hsconfig\SKILL.md`

**Interfaces:**
- Consumes: source lanes from Tasks 1-2.
- Produces: operator-facing guidance that `SOURCE_BACKED_STRONG` may use current or Evergreen Wild guide evidence, but never stats/decklist/static-only evidence for strategic runtime surfaces.

- [ ] **Step 1: Add doc test for required wording**

If a docs wording test exists, extend it. If no docs wording test exists, add this to `tests/test_docs_active_path.py`:

```python
def test_guide_research_policy_documents_evergreen_wild_source_lane():
    content = Path("docs/operator/guide-research-policy.md").read_text(encoding="utf-8")

    assert "evergreen_wild_archetype" in content
    assert "SOURCE_BACKED_STRONG" in content
    assert "stats" in content.lower()
    assert "must not prove" in content
    assert "operator_summary.json remains the only normal apply authority" in content
```

If `Path` is not imported in that file, add:

```python
from pathlib import Path
```

- [ ] **Step 2: Run doc test to verify it fails if wording is missing**

Run:

```powershell
python -m pytest tests/test_docs_active_path.py -q
```

Expected before docs update: failure if `evergreen_wild_archetype` is not documented.

- [ ] **Step 3: Update `docs/operator/guide-research-policy.md`**

In the "Source Lanes" section, add:

```markdown
- `evergreen_wild_archetype`: full-text public Wild guide for the same deck or close archetype whose publication year is older than the current year but still valid because the deck/card overlap is explicit and current static card text does not contradict it.
```

In the Source Autopilot or Online Source Acquisition section, add:

```markdown
Evergreen Wild guide rule:

- `SOURCE_BACKED_STRONG` may use either a current deck-matched public guide or an `evergreen_wild_archetype` guide when the guide is full-text, public, deck/archetype-matched, and has explicit card overlap.
- Old non-Wild guides, snippets, decklists, HSReplay/HSGuru aggregate stats, and static card databases remain support or diagnostic lanes. They must not prove strategic runtime surfaces by themselves.
- HearthstoneJSON/static records may still support deterministic CardID/effect rows, such as `hero_power_transform`, but they must not create opening-hand Mulligan keeps without an explicit mulligan claim.
```

- [ ] **Step 4: Update the active HSConfig skill guidance**

Check paths:

```powershell
Test-Path .agents\skills\hsconfig\SKILL.md
Test-Path C:\Users\darbo\.codex\skills\hsconfig\SKILL.md
```

If the repo-local skill exists, update only `C:\Users\darbo\Documents\HSConfig\.agents\skills\hsconfig\SKILL.md`. If it does not, update `C:\Users\darbo\.codex\skills\hsconfig\SKILL.md`.

Add this compact rule near the source policy section:

```markdown
Source-backed strong rule: prefer current public deck guides, but for Wild decks an older full-text guide may count as `evergreen_wild_archetype` when deck/card overlap is explicit and current static card text does not contradict it. Never promote decklists, aggregate stats, snippets, policy fallback, or static card text into strategic runtime claims. Static semantics can support deterministic CardID/effect rows such as Hero Power transforms only.
```

- [ ] **Step 5: Run doc tests**

Run:

```powershell
python -m pytest tests/test_docs_active_path.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add docs/operator/guide-research-policy.md tests/test_docs_active_path.py .agents/skills/hsconfig/SKILL.md C:/Users/darbo/.codex/skills/hsconfig/SKILL.md
git commit -m "docs: document evergreen Wild source closure"
```

If one skill path does not exist or is not edited, omit it from `git add`.

---

### Task 6: Matrix Verification And No Default-Only Regression Proof

**Files:**
- Modify only if tests expose a real gap:
  - `C:\Users\darbo\Documents\HSConfig\src\hsconfig\operator_summary.py`
  - `C:\Users\darbo\Documents\HSConfig\src\hsconfig\source_to_runtime_explainability.py`
  - `C:\Users\darbo\Documents\HSConfig\src\hsconfig\package_builder.py`
- Test:
  - `C:\Users\darbo\Documents\HSConfig\tests\test_universal_wild_no_block_matrix.py`
  - `C:\Users\darbo\Documents\HSConfig\tests\test_archetype_fixture_matrix.py`
  - `C:\Users\darbo\Documents\HSConfig\tests\test_apply_gate.py`

**Interfaces:**
- Consumes: all earlier changes.
- Produces: proof that every representative Wild deck remains non-blocking and not default-only.

- [ ] **Step 1: Run focused matrix and gate tests**

Run:

```powershell
python -m pytest tests/test_universal_wild_no_block_matrix.py tests/test_archetype_fixture_matrix.py tests/test_apply_gate.py -q
```

Expected: PASS.

- [ ] **Step 2: If default-only regression appears, fix report surface status only**

If a failure says `default_only_runtime_surfaces` is not empty, inspect the failing `operator_summary` row and fix the producer so the surface is explicitly one of:

```python
allowed_surface_statuses = {
    "source_backed",
    "source_and_policy_backed",
    "policy_backed",
    "static_semantics_backed",
    "suppressed",
    "source_gap",
    "warning_only",
}
```

Do not add a hard block for source depth. Keep the package load-safe if technical files are valid.

- [ ] **Step 3: Re-run the focused tests**

Run:

```powershell
python -m pytest tests/test_universal_wild_no_block_matrix.py tests/test_archetype_fixture_matrix.py tests/test_apply_gate.py -q
```

Expected: PASS.

- [ ] **Step 4: Commit if code changed**

If Task 6 required source changes:

```powershell
git add src/hsconfig/operator_summary.py src/hsconfig/source_to_runtime_explainability.py src/hsconfig/package_builder.py tests/test_universal_wild_no_block_matrix.py tests/test_archetype_fixture_matrix.py tests/test_apply_gate.py
git commit -m "fix: keep Wild matrix no-default-only visible"
```

If no files changed, skip this commit.

---

### Task 7: Final Verification, Diff Audit, And Push

**Files:**
- No planned source edits.
- Verify repo-wide behavior.

**Interfaces:**
- Consumes: Tasks 1-6.
- Produces: pushed branch ready for user review or follow-up implementation.

- [ ] **Step 1: Run targeted contract suite**

Run:

```powershell
python -m pytest tests/test_source_evidence_policy.py tests/test_source_autopilot.py tests/test_claim_kind_runtime_contract.py tests/test_card_behavior_router.py tests/test_universal_wild_no_block_matrix.py -q
```

Expected: PASS.

- [ ] **Step 2: Run docs and authority boundary suite**

Run:

```powershell
python -m pytest tests/test_docs_active_path.py tests/test_apply_authority_boundary.py tests/test_no_second_gate_contract.py tests/test_source_contract_conformance.py tests/test_contract_spine_sentinel.py -q
```

Expected: PASS.

- [ ] **Step 3: Run full test suite**

Run:

```powershell
python -m pytest -q
```

Expected: PASS. Record total passed/skipped count in the final handoff.

- [ ] **Step 4: Inspect diff and ensure no generated/runtime evidence is tracked**

Run:

```powershell
git diff --stat
git status --short
rg -n "Power\\.log|\\.hdtreplay|\\.hsreplay|HearthRanger|winrate|post-game|postgame" src tests docs/operator .agents/skills/hsconfig C:\Users\darbo\.codex\skills\hsconfig
```

Expected:

- Diff only contains source policy, autopilot, profile/tests/docs/skill updates.
- No generated runtime package, raw logs, HDT files, `.hsreplay`, `.hdtreplay`, or Power.log is staged.
- Scope scan finds only expected boundary documentation or tests, not new runtime-analysis code.

- [ ] **Step 5: Push branch**

Run:

```powershell
git status -sb
git push
```

Expected: branch is up to date on GitHub.

---

## Self-Review Checklist

- Spec coverage:
  - Source-/Contract-Logik remains one narrow chain: Task 1, Task 2, Task 4.
  - No default-only invariant remains tested: Task 3, Task 6, Task 7.
  - `SOURCE_BACKED_STRONG` is honest and not forced: Task 1, Task 2, Task 5.
  - Wild guide age is handled without lying: Task 1, Task 2, Task 5.
  - Darkbishop effect-not-mulligan behavior is locked: Task 4.
  - Representative deck matrix stays non-blocking: Task 3, Task 6.
  - No repo bloat / no new orchestrator: File Structure and Global Constraints.
- Placeholder scan:
  - No unresolved placeholder markers or deferred behavior is required.
  - Every task has exact files, exact commands, and expected outcomes.
- Type consistency:
  - `classify_source_evidence(...)` remains the source policy interface.
  - `source_freshness_lane`, `source_rank_lane`, `source_lane`, `promotion_eligible`, and `strong_promotion_eligible` are plain dict fields.
  - Source-autopilot uses the same lane strings as source evidence policy.
  - Closure profile verdict remains diagnostic-only and does not change apply authority.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-16-hsconfig-source-closure-autopilot-v2.md`.

Two execution options:

1. Subagent-Driven (recommended) - dispatch a fresh subagent per task, review between tasks, fast iteration.
2. Inline Execution - execute tasks in this session with checkpoints.

Recommended execution: Subagent-Driven.

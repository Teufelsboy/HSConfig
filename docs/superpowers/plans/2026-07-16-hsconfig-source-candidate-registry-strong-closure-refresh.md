# HSConfig Source Candidate Registry And Strong Closure Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make HSConfig's source/contract path prove the 12 supplied Wild decks can build useful non-default-only config packages while `SOURCE_BACKED_STRONG` is awarded only when the source-to-runtime chain is genuinely closed.

**Architecture:** Keep HSConfig narrow: source candidates seed acquisition, acquisition/autopilot verifies evidence, `claim_kind` and surface gates decide runtime lowering, and `reports/operator_summary.json` remains the single apply authority. Add a 12-deck source-candidate proof set beside the existing representative fixture matrix instead of widening the representative matrix blindly.

**Tech Stack:** Python 3.11, existing HSConfig CLI modules, JSON docs/fixtures, pytest. No new runtime service, no new dependency, no HSTuner replay loop, no HSranger migration.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig`.
- Keep `SOURCE_BACKED_STRONG` as an evidence-quality label, not a generation or apply gate.
- Every syntactically valid deck input must still attempt to build a load-safe config package.
- Missing public guide evidence must not block config generation.
- `default_only_runtime_surfaces` must not be silently hidden; every runtime surface is source-backed, policy-backed, static-semantics-backed, suppressed, warning-only, or reported as a source gap.
- Candidate registry URLs are acquisition seeds only. A URL in `source_candidate_registry.py` must not by itself prove `SOURCE_BACKED_STRONG`.
- Decklists, stats pages, search snippets, policy-backed rows, generated defaults, and runtime examples must not promote to `SOURCE_BACKED_STRONG`.
- Current full-text public guide claims and qualifying evergreen Wild archetype guide claims may promote only the concrete runtime surfaces they actually support.
- Official/static data such as HearthstoneJSON may support deterministic CardID/effect rows, but must not prove opening-hand keeps, combo order, or deck-specific targeting by itself.
- Darkbishop Benedictus (`SW_448`) remains a start-of-game `hero_power_transform` effect row and must not become a Mulligan keep without explicit opening-hand source text.
- Presume and Concede remain outside the normal generated package.
- Keep the current 11-deck representative fixture matrix unless a missing runtime/source family is proven. Add a separate 12-deck source-candidate proof set for the user-supplied decks.

---

## File Structure

Modify:

- `src/hsconfig/source_candidate_registry.py`
  - Holds source candidate seeds and their declared evidence ceiling.
- `src/hsconfig/source_evidence_policy.py`
  - Keeps source-family trust ceilings and promotion blockers.
- `src/hsconfig/source_autopilot.py`
  - Exposes candidate-derived source gaps and per-deck first missing source actions.
- `docs/operator/source-backed-strong-closure.md`
  - Documents the honest current status of the 12-deck source proof set.
- `docs/operator/guide-research-policy.md`
  - Documents source-family authority and candidate registry boundaries.
- `docs/operator/README.md`
  - Updates operator wording for source candidates and 12-deck proof.

Create:

- `docs/operator/source-candidate-proof-decks.json`
  - The 12-deck source candidate proof set supplied by the user.
- `tests/test_source_candidate_registry_matrix.py`
  - Registry coverage and source-ceiling tests for all 12 decks.

Modify tests:

- `tests/test_source_candidate_registry.py`
- `tests/test_source_acquisition_strong_closure.py`
- `tests/test_configure_online_source.py`
- `tests/test_universal_wild_no_block_matrix.py`
- `tests/test_source_informed_closure_contract.py`
- `tests/test_docs_active_path.py`

Do not create a new large source subsystem. Extend the existing registry/acquisition/autopilot path only.

---

## Task 1: Add Source Candidate Metadata Without Making It Authority

**Files:**

- Modify: `src/hsconfig/source_candidate_registry.py`
- Modify: `tests/test_source_candidate_registry.py`
- Create: `tests/test_source_candidate_registry_matrix.py`

**Interfaces:**

- Consumes: `source_candidates_for_deck(deck_name: str, deck_code: str | None = None) -> list[SourceCandidate]`
- Produces:
  - `SourceCandidate.publication_year: int | None`
  - `SourceCandidate.source_visibility: str`
  - `SourceCandidate.strength_ceiling: str`
  - `SourceCandidate.expected_claim_kinds: tuple[str, ...]`
  - `SourceCandidate.first_missing_source_action: str`

- [ ] **Step 1: Write the failing metadata test**

Add to `tests/test_source_candidate_registry.py`:

```python
def test_source_candidate_metadata_is_seed_not_authority():
    candidates = source_candidates_for_deck(
        "ShadowPriest",
        "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=",
    )

    assert candidates
    first = candidates[0]
    assert first.source_visibility in {"full_text", "decklist_only", "snippet_only"}
    assert first.strength_ceiling in {
        "candidate_strong",
        "candidate_partial",
        "context_only",
    }
    assert isinstance(first.expected_claim_kinds, tuple)
    assert "mulligan_keep" in first.expected_claim_kinds
    assert first.first_missing_source_action == "none"
```

- [ ] **Step 2: Run the failing test**

Run:

```powershell
python -m pytest tests/test_source_candidate_registry.py::test_source_candidate_metadata_is_seed_not_authority -q
```

Expected before implementation: fail because the new fields do not exist.

- [ ] **Step 3: Extend `SourceCandidate` narrowly**

Patch `SourceCandidate` in `src/hsconfig/source_candidate_registry.py`:

```python
@dataclass(frozen=True)
class SourceCandidate:
    url: str
    source_family: str
    deck_name: str
    archetype: str
    reason: str
    priority: int
    expected_strength: str
    format_scope: str = "wild"
    evergreen_wild_archetype: bool = False
    publication_year: int | None = None
    source_visibility: str = "full_text"
    strength_ceiling: str = "candidate_partial"
    expected_claim_kinds: tuple[str, ...] = ()
    first_missing_source_action: str = "add_current_deck_guide_or_mulligan_guide"
```

- [ ] **Step 4: Update existing candidates with explicit metadata**

For `ShadowPriest`, set:

```python
publication_year=2026,
source_visibility="full_text",
strength_ceiling="candidate_strong",
expected_claim_kinds=("gameplan_posture", "mulligan_keep", "mulligan_discard", "targeting_rule", "hero_power_transform"),
first_missing_source_action="none",
```

For `BigShaman`, set:

```python
publication_year=2018,
source_visibility="full_text",
strength_ceiling="candidate_strong",
expected_claim_kinds=("gameplan_posture", "mulligan_keep", "mulligan_discard", "mechanic_usage", "combo_sequence", "card_role"),
first_missing_source_action="none",
```

- [ ] **Step 5: Run the registry tests**

Run:

```powershell
python -m pytest tests/test_source_candidate_registry.py -q
```

Expected after implementation: all tests pass.

- [ ] **Step 6: Commit**

Run:

```powershell
git add src/hsconfig/source_candidate_registry.py tests/test_source_candidate_registry.py
git commit -m "Add HSConfig source candidate metadata"
```

---

## Task 2: Add The 12-Deck Source Candidate Proof Set

**Files:**

- Modify: `src/hsconfig/source_candidate_registry.py`
- Create: `docs/operator/source-candidate-proof-decks.json`
- Create: `tests/test_source_candidate_registry_matrix.py`

**Interfaces:**

- Consumes: `source_candidates_for_deck()`
- Produces: deterministic candidate coverage for these deck names:
  - `ShadowPriest`
  - `CtAPaladin`
  - `PirateRogue`
  - `BigShaman`
  - `Discolock`
  - `TreantDruid`
  - `ImbueMage`
  - `MechPala`
  - `Kingslayer`
  - `Boarlock`
  - `PirateDH`
  - `CuteWarrior`

- [ ] **Step 1: Write the 12-deck coverage test**

Create `tests/test_source_candidate_registry_matrix.py`:

```python
from __future__ import annotations

from hsconfig.source_candidate_registry import source_candidates_for_deck


DECKS = {
    "ShadowPriest": "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=",
    "CtAPaladin": "AAEBAZ8FBowBwP0ChJYFzpwGprMGg8IHDIgO+NICg94DkeQDzusDyaAE4aQEwcQFhY4GmY4G9ZUGmvwHAAA=",
    "PirateRogue": "AAEBAaIHApG8AuXRAg6MAtQF+w/psAPz3QOvoASKyQSa2wTXowW/9wXWngb8pQb8qAatxQYAAA==",
    "BigShaman": "AAEBAaoIBpQD5LcDv84E9qMGgbgGmvYGDM4P0hP2vQKPlAPW9QO8tgT08gXqmAbGpgakpwb44gas/QYAAA==",
    "Discolock": "AAEBAf0GBM4Hj4ID8aEG9qEGDbW5A9XRA9DhA5iSBauSBZXKBteXB4SZB6StB8ayB9a+B9m+B8+/BwAA",
    "TreantDruid": "AAEBAZICAt/7ApOyBw7NuwLB8wL8rQP/rQOV4APs9QOvgASuwASy3QTO5AWw+gXZ/wXJ0Aat4gYAAA==",
    "ImbueMage": "AAEBAf0EBIUXm80DvO0Egb8GDcAB9KsD0+wD1uwDr8QForMG1voG3PoG9PwG94EHs4cHwIcH7o0HAAA=",
    "MechPala": "AAEBAZ8FAtS9BMekBg6f9QLW/gLX/gKHrgOStQThtQTa0wTZ0AW5/gWf4Qa08Qbi8Qa6lgea/AcAAQPzswbHpAb2swbHpAbu3gbHpAYAAA==",
    "Kingslayer": "AAEBAaIHBpG8ApKDB4aoB4eoB4ioB4jZBwyMAtQF6bAD1bYEiskE16MF7p4G/KUG/KgGs8EG6sQGrcUGAAA=",
    "Boarlock": "AAEBAf0GBuAF054G7qEGxKIG0YIHqYgHDJDHAvLQAp2pA5vNA9P5A6bqBPTGBYSeBpWzBpTKBoSZB4adBwAA",
    "PirateDH": "AAEBAea5AwaRvALUyAP51QOHiwTh+AX8wAYM+w/psAPyyQPltgSl4gSr4gSVqgX8qAbYwAb2wAatxQax6wYAAA==",
    "CuteWarrior": "AAEBAQcEkbwCkdAD69YHstgHDY0Q6bADpLYDxN4D/9sEj5UFlaoFtNEF9PIFovoF/KgGltMGtI8HAAA=",
}


def test_source_candidate_registry_covers_user_supplied_wild_decks():
    missing = [
        deck_name
        for deck_name, deck_code in DECKS.items()
        if not source_candidates_for_deck(deck_name, deck_code)
    ]

    assert missing == []


def test_candidate_strength_ceiling_is_explicit_for_every_user_deck():
    for deck_name, deck_code in DECKS.items():
        candidates = source_candidates_for_deck(deck_name, deck_code)
        assert candidates, deck_name
        assert candidates[0].strength_ceiling in {
            "candidate_strong",
            "candidate_partial",
            "context_only",
        }, deck_name
        assert candidates[0].first_missing_source_action, deck_name


def test_context_only_candidates_do_not_claim_none_missing_action():
    for deck_name, deck_code in DECKS.items():
        for candidate in source_candidates_for_deck(deck_name, deck_code):
            if candidate.strength_ceiling == "context_only":
                assert candidate.first_missing_source_action != "none", candidate.url
```

- [ ] **Step 2: Run the failing coverage test**

Run:

```powershell
python -m pytest tests/test_source_candidate_registry_matrix.py -q
```

Expected before implementation: fail because several decks return no candidates.

- [ ] **Step 3: Add candidate rows for all 12 decks**

Patch `_KNOWN_CANDIDATES` with these first candidates and ceilings:

```python
"ctapaladin": (
    SourceCandidate(
        url="https://www.reddit.com/r/wildhearthstone/comments/1rzz9b1/rank_1_legend_with_cta_and_qldh/",
        source_family="community_guide",
        deck_name="CtAPaladin",
        archetype="wild_cta_paladin",
        reason="current Wild CtA Paladin positioning and card-choice evidence without full mulligan closure",
        priority=8,
        expected_strength="guide_current_archetype_partial",
        publication_year=2026,
        strength_ceiling="candidate_partial",
        expected_claim_kinds=("gameplan_posture", "card_role", "mechanic_usage"),
        first_missing_source_action="add_current_cta_paladin_mulligan_keep_source",
    ),
),
```

Use these exact first-candidate URLs for the remaining decks:

- `PirateRogue`: `https://www.hearthpwn.com/decks/1441097-ww-pirate-rogue`
- `Discolock`: `https://www.reddit.com/r/CompetitiveHS/comments/1s7nr67/easy_wild_legend_discolock/`
- `TreantDruid`: `https://www.reddit.com/r/wildhearthstone/comments/1mjge7n/treant_druid_to_early_legend/`
- `ImbueMage`: `https://www.hearthpwn.com/decks/1462266-wild-imbue-mage`
- `MechPala`: `https://hearthstone-decks.net/wild-decks/paladin-wild-decks/wild-mech-paladin/`
- `Kingslayer`: `https://www.reddit.com/r/wildhearthstone/comments/1p8sp6f/legend_1478_kingsbane_rogue/`
- `Boarlock`: `https://www.hearthpwn.com/decks/1455610-elwynn-boar-sneak-attack-otk`
- `PirateDH`: `https://hearthstone-decks.net/pirate-demon-hunter-223-legend-mangekou-score-49-32/`
- `CuteWarrior`: `https://www.reddit.com/r/wildhearthstone/comments/13e0x4w/powersliding_with_cute_warrior_to_rank_278/`

Set initial ceilings:

```python
{
    "PirateRogue": "candidate_partial",
    "Discolock": "candidate_partial",
    "TreantDruid": "candidate_partial",
    "ImbueMage": "candidate_strong",
    "MechPala": "context_only",
    "Kingslayer": "candidate_partial",
    "Boarlock": "candidate_partial",
    "PirateDH": "candidate_partial",
    "CuteWarrior": "candidate_partial",
}
```

Reasoning:

- `candidate_strong` means the page may close the package if acquisition extracts matching full-text claims.
- `candidate_partial` means it can improve config quality but must still expose remaining source gaps.
- `context_only` means it may confirm archetype/meta presence but cannot promote strong.

- [ ] **Step 4: Create the 12-deck proof document**

Create `docs/operator/source-candidate-proof-decks.json`:

```json
{
  "schema_version": 1,
  "purpose": "User-supplied 12-deck source candidate proof set for HSConfig online-source coverage. This does not replace the representative archetype fixture matrix.",
  "strongness_policy": "Candidate URLs are source acquisition seeds only. SOURCE_BACKED_STRONG requires fetched full-text claims that pass source evidence policy, claim-kind normalization, surface gates, and closure profile checks.",
  "decks": []
}
```

Fill `decks` with one object per deck:

```json
{
  "deck_name": "ShadowPriest",
  "expected_candidate_count_min": 1,
  "expected_strength_ceiling": "candidate_strong",
  "first_missing_source_action": "none"
}
```

Use these expected strength ceilings:

```json
{
  "ShadowPriest": "candidate_strong",
  "CtAPaladin": "candidate_partial",
  "PirateRogue": "candidate_partial",
  "BigShaman": "candidate_strong",
  "Discolock": "candidate_partial",
  "TreantDruid": "candidate_partial",
  "ImbueMage": "candidate_strong",
  "MechPala": "context_only",
  "Kingslayer": "candidate_partial",
  "Boarlock": "candidate_partial",
  "PirateDH": "candidate_partial",
  "CuteWarrior": "candidate_partial"
}
```

- [ ] **Step 5: Run the registry matrix tests**

Run:

```powershell
python -m pytest tests/test_source_candidate_registry.py tests/test_source_candidate_registry_matrix.py -q
```

Expected after implementation: all tests pass.

- [ ] **Step 6: Commit**

Run:

```powershell
git add src/hsconfig/source_candidate_registry.py tests/test_source_candidate_registry.py tests/test_source_candidate_registry_matrix.py docs/operator/source-candidate-proof-decks.json
git commit -m "Add HSConfig 12 deck source candidate proof set"
```

---

## Task 3: Guard Against Registry URL Equals Strong Evidence

**Files:**

- Modify: `tests/test_source_acquisition_strong_closure.py`
- Modify: `tests/test_configure_online_source.py`
- Modify: `src/hsconfig/source_evidence_policy.py`
- Modify: `src/hsconfig/source_autopilot.py`

**Interfaces:**

- Consumes:
  - `SourceCandidate.strength_ceiling`
  - `classify_source_evidence(record, deck_name=..., current_date=...)`
  - `source_acquire_payload(...)`
- Produces:
  - source-acquisition rows that say whether a source was fetched as `full_text`, `snippet_only`, `decklist_only`, or `fetch_failed`
  - strong promotion only after source evidence policy and claim extraction pass

- [ ] **Step 1: Add a failing test for a candidate URL that fetches thin text**

Add to `tests/test_configure_online_source.py`:

```python
def test_candidate_registry_url_does_not_promote_without_full_text_claims(tmp_path, monkeypatch):
    fixture_map = tmp_path / "source_fixture_url_map.json"
    fixture_map.write_text(
        json.dumps(
            {
                "https://example.test/thin-mech-paladin": {
                    "source_url": "https://example.test/thin-mech-paladin",
                    "source_title": "Thin Mech Paladin Decklist",
                    "source_family": "decklist",
                    "publication_year": 2026,
                    "normalized_text": "Mech Paladin deck code and card list only.",
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "hsconfig.source_candidate_registry.source_candidates_for_deck",
        lambda deck_name, deck_code=None: [
            type(
                "Candidate",
                (),
                {
                    "url": "https://example.test/thin-mech-paladin",
                    "priority": 10,
                    "strength_ceiling": "candidate_strong",
                },
            )()
        ],
    )

    result, status = configure_payload(
        argparse.Namespace(
            deck_name="MechPala",
            deck_code="AAEBAZ8FAtS9BMekBg6f9QLW/gLX/gKHrgOStQThtQTa0wTZ0AW5/gWf4Qa08Qbi8Qa6lgea/AcAAQPzswbHpAb2swbHpAbu3gbHpAYAAA==",
            runtime_root=str(tmp_path / "runtime"),
            out=str(tmp_path / "out"),
            online_source=True,
            auto_source=False,
            source_url=[],
            source_fixture_url_map_json=str(fixture_map),
            source_fetch_timeout_seconds=1.0,
            current_date="2026-07-16",
            cards_json=None,
            collectible_cards_json=None,
            full_cards_json=None,
            allow_placeholder=True,
            apply=False,
            fake_apply=False,
            json=True,
        )
    )

    assert status == 0
    operator = result["package"]["reports"]["operator_summary"]
    assert operator["technical_status"] == "VALID_PACKAGE"
    assert operator["semantic_status"] != "SOURCE_BACKED_STRONG"
    assert operator["first_missing_source_action"] != "none"
```

If local helper shape differs, adapt only the call harness, not the assertion intent.

- [ ] **Step 2: Run the failing test**

Run:

```powershell
python -m pytest tests/test_configure_online_source.py::test_candidate_registry_url_does_not_promote_without_full_text_claims -q
```

Expected before implementation: fail if registry metadata can leak into strong status or if the helper shape needs adjustment.

- [ ] **Step 3: Keep registry metadata out of promotion eligibility**

Patch source acquisition/autopilot so fetched row fields drive promotion:

```python
promotion_source = {
    "source_family": fetched_record.get("source_family"),
    "source_visibility": fetched_record.get("source_visibility"),
    "normalized_text": fetched_record.get("normalized_text"),
    "publication_year": fetched_record.get("publication_year"),
    "deck_match": fetched_record.get("deck_match"),
}
```

Do not read `SourceCandidate.strength_ceiling` inside `classify_source_evidence()`. That field is a search seed ceiling, not evidence.

- [ ] **Step 4: Run the focused online-source tests**

Run:

```powershell
python -m pytest tests/test_source_acquisition_strong_closure.py tests/test_configure_online_source.py -q
```

Expected after implementation: all tests pass.

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/hsconfig/source_evidence_policy.py src/hsconfig/source_autopilot.py tests/test_source_acquisition_strong_closure.py tests/test_configure_online_source.py
git commit -m "Prevent source candidates from bypassing evidence policy"
```

---

## Task 4: Add Honest Strongness Expectations For The 12-Deck Proof Set

**Files:**

- Modify: `docs/operator/source-candidate-proof-decks.json`
- Modify: `docs/operator/source-backed-strong-closure.md`
- Modify: `tests/test_source_candidate_registry_matrix.py`
- Modify: `tests/test_docs_active_path.py`

**Interfaces:**

- Consumes: `docs/operator/source-candidate-proof-decks.json`
- Produces:
  - `expected_candidate_strength_ceiling`
  - `expected_runtime_generation_status`
  - `expected_strong_promotion_status`
  - `first_missing_source_action`

- [ ] **Step 1: Add proof-set expectation assertions**

Add to `tests/test_source_candidate_registry_matrix.py`:

```python
import json
from pathlib import Path


EXPECTED_STRENGTH = {
    "ShadowPriest": "candidate_strong",
    "CtAPaladin": "candidate_partial",
    "PirateRogue": "candidate_partial",
    "BigShaman": "candidate_strong",
    "Discolock": "candidate_partial",
    "TreantDruid": "candidate_partial",
    "ImbueMage": "candidate_strong",
    "MechPala": "context_only",
    "Kingslayer": "candidate_partial",
    "Boarlock": "candidate_partial",
    "PirateDH": "candidate_partial",
    "CuteWarrior": "candidate_partial",
}


def test_source_candidate_proof_doc_matches_registry_expectations():
    proof = json.loads(
        Path("docs/operator/source-candidate-proof-decks.json").read_text(
            encoding="utf-8"
        )
    )
    rows = {row["deck_name"]: row for row in proof["decks"]}

    assert set(rows) == set(EXPECTED_STRENGTH)
    for deck_name, expected_strength in EXPECTED_STRENGTH.items():
        assert rows[deck_name]["expected_strength_ceiling"] == expected_strength
        assert rows[deck_name]["expected_runtime_generation_status"] == "load_safe_no_default_only"
        assert rows[deck_name]["expected_strong_promotion_status"] in {
            "candidate_strong_if_fetched_claims_close",
            "partial_until_missing_source_action_closes",
            "context_only_not_strong",
        }
```

- [ ] **Step 2: Run the failing proof doc test**

Run:

```powershell
python -m pytest tests/test_source_candidate_registry_matrix.py::test_source_candidate_proof_doc_matches_registry_expectations -q
```

Expected before implementation: fail until the JSON proof doc contains the required fields.

- [ ] **Step 3: Fill `source-candidate-proof-decks.json`**

For each deck row, include:

```json
{
  "deck_name": "MechPala",
  "expected_strength_ceiling": "context_only",
  "expected_runtime_generation_status": "load_safe_no_default_only",
  "expected_strong_promotion_status": "context_only_not_strong",
  "first_missing_source_action": "add_current_full_text_mulligan_or_gameplan_source",
  "candidate_urls": [
    "https://hearthstone-decks.net/wild-decks/paladin-wild-decks/wild-mech-paladin/"
  ]
}
```

Use `candidate_strong_if_fetched_claims_close` only for `ShadowPriest`, `BigShaman`, and `ImbueMage`.

Use `partial_until_missing_source_action_closes` for `CtAPaladin`, `PirateRogue`, `Discolock`, `TreantDruid`, `Kingslayer`, `Boarlock`, `PirateDH`, and `CuteWarrior`.

Use `context_only_not_strong` for `MechPala`.

- [ ] **Step 4: Update docs without changing apply authority**

Patch `docs/operator/source-backed-strong-closure.md`:

```markdown
## 12-Deck Source Candidate Proof Set

`docs/operator/source-candidate-proof-decks.json` tracks the user-supplied 12-deck source candidate set. This file proves that HSConfig has a source acquisition seed or an explicit source gap for every supplied deck. It does not replace `docs/operator/archetype-fixture-matrix.json`, and it does not make candidate URLs promotion authority.

Candidate rows can be:

- `candidate_strong`: acquisition may reach `SOURCE_BACKED_STRONG` if fetched full-text claims close the runtime surfaces.
- `candidate_partial`: acquisition can improve source quality, but at least one first missing source action is expected.
- `context_only`: the source can confirm archetype or meta presence, but must not promote `SOURCE_BACKED_STRONG`.
```

- [ ] **Step 5: Update docs active path tests if required**

If `tests/test_docs_active_path.py` checks exact wording, add assertions for:

```python
assert "source-candidate-proof-decks.json" in readme_text
assert "candidate URLs" in source_closure_text
assert "must not promote" in source_closure_text
```

- [ ] **Step 6: Run docs/proof tests**

Run:

```powershell
python -m pytest tests/test_source_candidate_registry_matrix.py tests/test_docs_active_path.py -q
```

Expected after implementation: all tests pass.

- [ ] **Step 7: Commit**

Run:

```powershell
git add docs/operator/source-candidate-proof-decks.json docs/operator/source-backed-strong-closure.md tests/test_source_candidate_registry_matrix.py tests/test_docs_active_path.py
git commit -m "Document HSConfig source candidate proof set"
```

---

## Task 5: Preserve No-Default-Only Runtime Output Across The 12 Decks

**Files:**

- Modify: `tests/test_universal_wild_no_block_matrix.py`
- Modify: `src/hsconfig/operator_summary.py` only if a failing test reveals a missing ledger/source gap
- Modify: `src/hsconfig/config_usefulness.py` only if a failing test reveals hidden thin/default-only wording

**Interfaces:**

- Consumes: generated `reports/operator_summary.json`
- Produces:
  - `default_only_runtime_surfaces == []`
  - `mulligan_policy_status.default_only is False`
  - `surface_status_ledger` has explicit rows for `mulligan`, `globalvalues`, `cardid_behavior`, and `combo`
  - `first_missing_source_action` is always a non-empty string

- [ ] **Step 1: Strengthen existing no-default-only assertions**

In `tests/test_universal_wild_no_block_matrix.py`, extend `assert_no_default_only_runtime_surfaces()`:

```python
def assert_no_default_only_runtime_surfaces(operator: dict) -> None:
    assert operator["default_only_runtime_surfaces"] == []
    assert operator["no_default_only_runtime_status"] == "clean"
    assert operator["first_missing_source_action"]

    ledger = {
        row["surface"]: row
        for row in operator.get("surface_status_ledger", [])
    }
    assert {"mulligan", "globalvalues", "cardid_behavior"} <= set(ledger)
    assert ledger["mulligan"]["status"] in {
        "source_backed",
        "policy_backed",
        "source_and_policy_backed",
        "warning_only",
    }
    assert ledger["globalvalues"]["status"] != "default_only"
    assert ledger["cardid_behavior"]["status"] != "default_only"

    mulligan_policy = operator["mulligan_policy_status"]
    assert mulligan_policy["default_only"] is False
```

- [ ] **Step 2: Run the existing 12-deck no-block test**

Run:

```powershell
python -m pytest tests/test_universal_wild_no_block_matrix.py -q
```

Expected before implementation: may pass already. If it fails, patch only the missing summary/ledger field and do not widen apply gates.

- [ ] **Step 3: Patch only if a hidden default-only gap appears**

If the test fails because a surface is missing from the ledger, patch `operator_summary.py` so missing-but-suppressed surfaces are represented as:

```python
{
    "surface": "combo",
    "status": "suppressed_with_reason",
    "reason": "no_exact_combo_sequence_claim",
    "apply_blocking": False,
}
```

Do not mark suppressed optional `Combo.json` as default-only.

- [ ] **Step 4: Run the focused no-default suite**

Run:

```powershell
python -m pytest tests/test_universal_wild_no_block_matrix.py tests/test_source_to_runtime_explainability.py tests/test_surface_authority_split.py -q
```

Expected after implementation: all tests pass.

- [ ] **Step 5: Commit**

Run:

```powershell
git add tests/test_universal_wild_no_block_matrix.py src/hsconfig/operator_summary.py src/hsconfig/config_usefulness.py
git commit -m "Strengthen HSConfig no default only proof"
```

If neither Python file changed, commit only the test file.

---

## Task 6: Keep Darkbishop And Static Semantics Boundaries As Canary Tests

**Files:**

- Modify: `tests/test_static_semantics_source_records.py`
- Modify: `tests/test_universal_wild_no_block_matrix.py`
- Modify: `docs/operator/guide-research-policy.md`

**Interfaces:**

- Consumes:
  - static semantics records for `SW_448`
  - source claim normalization
  - runtime Mulligan output
- Produces:
  - `hero_power_transform` preserved in source/runtime behavior
  - no `mulligan_keep` for Darkbishop effect-only evidence

- [ ] **Step 1: Add explicit no-opening-hand keep assertion**

In `tests/test_static_semantics_source_records.py`, extend the Darkbishop test:

```python
assert "hero_power_transform" in claim_kinds
assert "mulligan_keep" not in claim_kinds
assert "mulligan_discard" not in claim_kinds
```

If those assertions already exist, add a package-level assertion in `tests/test_universal_wild_no_block_matrix.py`:

```python
def test_shadowpriest_darkbishop_effect_is_not_opening_hand_keep(tmp_path, monkeypatch):
    result = prepare_matrix_deck(tmp_path, monkeypatch, "ShadowPriest")
    deck_dir = result["deck_dir"]
    mulligan = json.loads((deck_dir / "Mulligan.json").read_text(encoding="utf-8"))
    darkbishop_rows = [
        row for row in mulligan.get("values", [])
        if row.get("card_id") == "SW_448"
    ]
    assert darkbishop_rows == []
    assert (deck_dir / "SW_448.json").is_file()
```

Use the existing helper names in `tests/test_universal_wild_no_block_matrix.py`; do not create a second package builder helper if one already exists.

- [ ] **Step 2: Run the canary tests**

Run:

```powershell
python -m pytest tests/test_static_semantics_source_records.py tests/test_universal_wild_no_block_matrix.py::test_singleton_hero_power_state_requirement_preserves_effect_without_mulligan_keep -q
```

Expected after implementation: all tests pass.

- [ ] **Step 3: Update guide policy wording**

Add to `docs/operator/guide-research-policy.md`:

```markdown
Effect-only source truth is not opening-hand truth. Static or guide evidence that a card changes the hero power, modifies deckbuilding, starts in deck, or applies before the mulligan can lower to supported CardID/effect surfaces, but it must not create `mulligan_keep` unless the source explicitly says the card should be kept in the opening hand.
```

- [ ] **Step 4: Run docs and canary tests**

Run:

```powershell
python -m pytest tests/test_static_semantics_source_records.py tests/test_docs_active_path.py -q
```

Expected after implementation: all tests pass.

- [ ] **Step 5: Commit**

Run:

```powershell
git add tests/test_static_semantics_source_records.py tests/test_universal_wild_no_block_matrix.py docs/operator/guide-research-policy.md
git commit -m "Preserve effect semantics without mulligan keeps"
```

---

## Task 7: Operator Docs And Skill Sync

**Files:**

- Modify: `docs/operator/README.md`
- Modify: `docs/operator/source-backed-strong-closure.md`
- Modify: `docs/operator/guide-research-policy.md`
- Modify: installed skill docs only if this repo owns a synchronized skill path in tests
- Modify: `tests/test_skill_files.py` only if it is the local guardrail for skill text

**Interfaces:**

- Consumes: source candidate proof terminology from Tasks 1-4
- Produces: a single operator story:
  - run `hsconfig configure`
  - optional `--online-source`
  - candidate registry seeds source acquisition
  - operator opens `reports/operator_summary.json`
  - strong source depth is diagnostic, not apply authority

- [ ] **Step 1: Add operator wording for source candidates**

Patch `docs/operator/README.md` near the online-source command:

```markdown
When `--online-source` is used, HSConfig also checks its source candidate registry for the deck name. These candidate URLs are acquisition seeds only. They reduce manual source entry, but they do not promote a package to `SOURCE_BACKED_STRONG` unless fetched full-text evidence passes source evidence policy, claim-kind normalization, surface gates, and closure profile checks.
```

- [ ] **Step 2: Add the 12-deck proof link**

Patch the Fixture Matrix or Supplemental Proof section:

```markdown
`docs/operator/source-candidate-proof-decks.json` is the separate 12-deck source-candidate proof set. It proves that each user-supplied Wild deck has either a registry candidate or an explicit first missing source action. It does not widen the representative fixture matrix and does not change runtime apply authority.
```

- [ ] **Step 3: Run docs tests**

Run:

```powershell
python -m pytest tests/test_docs_active_path.py tests/test_skill_files.py -q
```

Expected after implementation: all tests pass.

- [ ] **Step 4: Run the contract guardrail script**

Run:

```powershell
python scripts/check_contract_guardrails.py
```

Expected after implementation: exit code 0.

- [ ] **Step 5: Commit**

Run:

```powershell
git add docs/operator/README.md docs/operator/source-backed-strong-closure.md docs/operator/guide-research-policy.md tests/test_docs_active_path.py tests/test_skill_files.py
git commit -m "Align HSConfig operator docs with source candidate proof"
```

If `tests/test_skill_files.py` and skill files are unchanged, commit only the docs that changed.

---

## Task 8: Final Verification And Review

**Files:**

- No planned code changes.
- Review all modified files from Tasks 1-7.

**Interfaces:**

- Consumes: all task outputs
- Produces: final evidence that the implementation is current, narrow, and safe

- [ ] **Step 1: Run focused source/contract suite**

Run:

```powershell
python -m pytest tests/test_source_candidate_registry.py tests/test_source_candidate_registry_matrix.py tests/test_source_acquisition_strong_closure.py tests/test_configure_online_source.py tests/test_universal_wild_no_block_matrix.py tests/test_static_semantics_source_records.py tests/test_lean_source_backed_strong_autopilot.py tests/test_archetype_fixture_matrix.py -q
```

Expected result:

```text
passed
```

- [ ] **Step 2: Run contract guardrail**

Run:

```powershell
python scripts/check_contract_guardrails.py
```

Expected result: exit code 0.

- [ ] **Step 3: Run full test suite if focused suite is green**

Run:

```powershell
python -m pytest -q
```

Expected result:

```text
passed
```

- [ ] **Step 4: Review diff for scope creep**

Run:

```powershell
git diff --stat
git diff -- src/hsconfig/source_candidate_registry.py src/hsconfig/source_evidence_policy.py src/hsconfig/source_autopilot.py docs/operator/source-candidate-proof-decks.json docs/operator/README.md docs/operator/source-backed-strong-closure.md docs/operator/guide-research-policy.md
```

Check:

- No new runtime service.
- No new dependency.
- No Presume/Concede normal-path generation.
- No new apply authority.
- No forced `SOURCE_BACKED_STRONG` from candidate URLs.
- No Darkbishop opening-hand keep from effect-only semantics.

- [ ] **Step 5: Final commit if any final fixes were needed**

Run:

```powershell
git status --short
git add <changed-files>
git commit -m "Complete HSConfig source candidate closure refresh"
```

Skip this commit if all changes are already committed by earlier tasks.

---

## Self-Review

Spec coverage:

- Source-/Contract-Logik einwandfrei: Tasks 1, 3, 4, 6.
- Kein default only: Task 5.
- Schmal und kompetent: global constraints, File Structure, Tasks 1-7.
- Autonom und no-block: Tasks 3, 5, 7.
- `SOURCE_BACKED_STRONG` nur ehrlich: Tasks 1, 3, 4.
- Optimale Config trotz partial sources: Tasks 2, 5, 7.
- 12 user-supplied decks: Task 2 and Task 4.
- Online/research source grounding: source URLs and source-family ceilings are encoded in Task 2.

Placeholder scan:

- No undecided-content marker remains in task instructions.
- No deferred-work marker remains in task instructions.
- No unspecified "write tests for above" steps remain.
- Every code-changing task has concrete files and commands.

Type consistency:

- `SourceCandidate` fields introduced in Task 1 are consumed by Tasks 2 and 4.
- `source_candidates_for_deck()` remains the public registry interface.
- Strong promotion remains owned by source acquisition, source evidence policy, source autopilot, and operator summary, not the registry.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-16-hsconfig-source-candidate-registry-strong-closure-refresh.md`.

Two execution options:

1. **Subagent-Driven (recommended)** - dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** - execute tasks in this session using executing-plans, batch execution with checkpoints.

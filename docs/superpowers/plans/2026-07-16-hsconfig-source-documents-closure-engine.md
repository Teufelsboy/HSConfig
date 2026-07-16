# HSConfig Source Documents Closure Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make HSConfig automatically harvest or select strong public guide sources, compile them into atomic source documents, and produce the best possible non-default-only config package while awarding `SOURCE_BACKED_STRONG` only when the evidence truly closes the deck contract.

**Architecture:** Keep the existing HSConfig flow: `configure` -> `source-manifest` -> optional `source-acquire` -> `source-autopilot` -> `research-deck` -> `prepare` -> `validate`. Add a thin Source Candidate Registry before `source-acquire`, strengthen source scoring and atomic claim extraction, and make `source_autopilot` report closure by card and runtime surface. Do not add a second apply gate: `reports/operator_summary.json` remains the single runtime apply authority.

**Tech Stack:** Python 3.11, existing HSConfig CLI modules, JSON/HTML fixtures, pytest. No new external runtime dependency, no browser automation, no HSTuner/HSranger coupling, no replay/winrate module.

## Global Constraints

- Work only in `C:\Users\darbo\Documents\HSConfig`.
- Keep the normal branch unless the executor explicitly creates a `codex/` branch before implementation.
- Do not introduce a human approval gate.
- Do not block any syntactically valid deck from package generation because guide evidence is incomplete.
- `SOURCE_BACKED_STRONG` is an evidence-quality verdict, not an apply gate.
- `VALID_PACKAGE + load_safe_apply + no default-only surfaces` is sufficient for config generation/apply eligibility.
- `SOURCE_BACKED_STRONG` must never be inferred from decklists, stats-only pages, generated defaults, policy defaults, snippets, stale non-evergreen pages, or static card text alone.
- Official/static Hearthstone semantics may support deterministic CardID/effect rows such as `hero_power_transform`, but may not prove mulligan keeps, targeting rules, or deck-specific gameplan by itself.
- No runtime surface may be silently default-only. Each requested surface must be `emitted`, `suppressed`, `source_gap`, `static_only`, or `not_applicable`.
- Darkbishop Benedictus (`SW_448`) must keep its start-of-game hero-power transform / Shadowform / Mind Spike semantics, but must not become an opening-hand keep unless an explicit current guide says to keep it.
- If a guide says not to keep 4-cost-or-higher cards, `SW_448` may become a `mulligan_discard` claim while its effect row remains in per-card runtime config.
- Presume and Concede stay out of the normal HSConfig package.
- Tests must use fixtures and fixture URL maps, not live network fetches.
- Changes must be narrow: source candidate registry, source acquisition/scoring, source claim compiler, source autopilot closure reports, representative fixtures, operator docs, and skill instructions.

---

## File Structure

Create:

- `src/hsconfig/source_candidate_registry.py`
- `tests/test_source_candidate_registry.py`
- `tests/fixtures/source_guides/bigshaman_current_guide.html`
- `tests/fixtures/source_guides/imbuemage_current_guide.html`
- `tests/fixtures/source_guides/treantdruid_current_guide.html`
- `tests/fixtures/source_guides/kingslayer_current_guide.html`

Modify:

- `src/hsconfig/commands/configure.py`
- `src/hsconfig/source_acquisition.py`
- `src/hsconfig/source_evidence_policy.py`
- `src/hsconfig/source_claim_compiler.py`
- `src/hsconfig/source_autopilot.py`
- `src/hsconfig/source_claim_gap_report.py`
- `tests/test_source_acquisition.py`
- `tests/test_source_claim_compiler.py`
- `tests/test_source_autopilot.py`
- `tests/test_universal_wild_no_block_matrix.py`
- `tests/test_shadowpriest_fresh_closure_proof.py`
- `tests/test_lean_source_backed_strong_autopilot.py`
- `docs/operator/source-backed-strong-closure.md`
- `docs/operator/guide-research-policy.md`
- `.agents/skills/hsconfig/SKILL.md`

Use existing fixtures:

- `tests/fixtures/source_guides/shadowpriest_current_guide.html`
- `tests/fixtures/source_guides/ctapaladin_current_guide.html`
- `tests/fixtures/source_guides/piraterogue_current_guide.html`
- `tests/fixtures/source_documents_shadowpriest_strong.json`
- `tests/fixtures/source_documents_ctapaladin_strong.json`
- `tests/fixtures/source_documents_piraterogue_strong.json`
- `tests/fixtures/source_documents_bigshaman_strong.json`
- `tests/fixtures/source_documents_discolock_strong.json`
- `tests/fixtures/source_documents_treantdruid_strong.json`
- `tests/fixtures/source_documents_imbuemage_strong.json`
- `tests/fixtures/source_documents_mechpala_strong.json`
- `tests/fixtures/source_documents_kingslayer_strong.json`
- `tests/fixtures/source_documents_boarlock_strong.json`
- `tests/fixtures/source_documents_piratedh_strong.json`

## Task 1: Add Source Candidate Registry

**Files:**
- Create: `src/hsconfig/source_candidate_registry.py`
- Create: `tests/test_source_candidate_registry.py`

**Interfaces:**
- Produces: `SourceCandidate` dataclass with fields `url: str`, `source_family: str`, `deck_name: str`, `archetype: str`, `reason: str`, `priority: int`, `expected_strength: str`, `format_scope: str`, `evergreen_wild_archetype: bool`.
- Produces: `source_candidates_for_deck(deck_name: str, deck_code: str, *, deck_identity: Mapping[str, Any] | None = None) -> list[SourceCandidate]`.
- Consumed by Task 2 in `configure_payload`.

- [ ] **Step 1: Write the failing registry tests**

Create `tests/test_source_candidate_registry.py`:

```python
from hsconfig.source_candidate_registry import source_candidates_for_deck


SHADOWPRIEST = "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA="
BIGSHAMAN = "AAEBAaoIBpQD5LcDv84E9qMGgbgGmvYGDM4P0hP2vQKPlAPW9QO8tgT08gXqmAbGpgakpwb44gas/QYAAA=="
UNKNOWN = "AAEBAf0EBIUXm80DvO0Egb8GDcAB9KsD0+wD1uwDr8QForMG1voG3PoG9PwG94EHs4cHwIcH7o0HAAA="


def test_shadowpriest_has_current_full_text_guide_candidate():
    candidates = source_candidates_for_deck("ShadowPriest", SHADOWPRIEST)

    urls = [candidate.url for candidate in candidates]
    assert "https://www.hearthpwn.com/decks/1461644-voidburn-wild-aggro-shadow-priest" in urls
    candidate = next(candidate for candidate in candidates if "voidburn-wild-aggro-shadow-priest" in candidate.url)
    assert candidate.source_family == "guide"
    assert candidate.expected_strength == "guide_current_deck_match"
    assert candidate.priority == 10


def test_bigshaman_has_evergreen_wild_guide_candidate():
    candidates = source_candidates_for_deck("BigShaman", BIGSHAMAN)

    candidate = next(candidate for candidate in candidates if "big-shaman-in-depth-guide" in candidate.url)
    assert candidate.source_family == "guide"
    assert candidate.format_scope == "wild"
    assert candidate.evergreen_wild_archetype is True


def test_unknown_deck_returns_empty_candidates_without_blocking():
    assert source_candidates_for_deck("UnknownWildDeck", UNKNOWN) == []
```

- [ ] **Step 2: Run the tests and verify failure**

Run:

```powershell
python -m pytest tests/test_source_candidate_registry.py -q
```

Expected before implementation:

```text
ModuleNotFoundError: No module named 'hsconfig.source_candidate_registry'
```

- [ ] **Step 3: Implement the minimal registry**

Create `src/hsconfig/source_candidate_registry.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


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


KNOWN_CANDIDATES: dict[str, tuple[SourceCandidate, ...]] = {
    "shadowpriest": (
        SourceCandidate(
            url="https://www.hearthpwn.com/decks/1461644-voidburn-wild-aggro-shadow-priest",
            source_family="guide",
            deck_name="ShadowPriest",
            archetype="shadow_priest",
            reason="current full-text Wild Shadow Priest guide with mulligan and hero-power plan",
            priority=10,
            expected_strength="guide_current_deck_match",
        ),
    ),
    "bigshaman": (
        SourceCandidate(
            url="https://www.hearthpwn.com/decks/1186371-big-shaman-in-depth-guide",
            source_family="guide",
            deck_name="BigShaman",
            archetype="big_shaman",
            reason="full-text Wild Big Shaman guide with mulligan, cheat, and swing-turn plan",
            priority=8,
            expected_strength="guide_evergreen_wild_archetype",
            evergreen_wild_archetype=True,
        ),
    ),
    "imbuemage": (
        SourceCandidate(
            url="https://www.hearthpwn.com/decks/1462266-wild-imbue-mage",
            source_family="guide",
            deck_name="ImbueMage",
            archetype="imbue_mage",
            reason="current full-text Imbue Mage guide with mulligan and hero-power plan",
            priority=10,
            expected_strength="guide_current_deck_match",
        ),
    ),
    "treantdruid": (
        SourceCandidate(
            url="https://www.reddit.com/r/wildhearthstone/comments/1mjge7n/treant_druid_to_early_legend/",
            source_family="community_guide",
            deck_name="TreantDruid",
            archetype="treant_druid",
            reason="full-text Wild Treant Druid guide with mulligan and matchup plan",
            priority=8,
            expected_strength="guide_evergreen_wild_archetype",
            evergreen_wild_archetype=True,
        ),
    ),
    "kingslayer": (
        SourceCandidate(
            url="https://www.reddit.com/r/wildhearthstone/comments/1p8sp6f/legend_1478_kingsbane_rogue/",
            source_family="community_guide",
            deck_name="Kingslayer",
            archetype="kingsbane_rogue",
            reason="full-text Kingsbane Rogue guide with mulligan and weapon plan",
            priority=8,
            expected_strength="guide_evergreen_wild_archetype",
            evergreen_wild_archetype=True,
        ),
    ),
    "ctapaladin": (
        SourceCandidate(
            url="https://www.reddit.com/r/wildhearthstone/comments/1u0kd33/any_help_with_cta_paladin_mulligan/",
            source_family="community_guide",
            deck_name="CtAPaladin",
            archetype="cta_paladin",
            reason="current public CtA Paladin mulligan discussion; useful but conflict-prone",
            priority=6,
            expected_strength="source_informed_partial",
        ),
    ),
}


def source_candidates_for_deck(
    deck_name: str,
    deck_code: str,
    *,
    deck_identity: Mapping[str, Any] | None = None,
) -> list[SourceCandidate]:
    del deck_code, deck_identity
    key = _norm(deck_name)
    candidates = list(KNOWN_CANDIDATES.get(key, ()))
    return sorted(candidates, key=lambda candidate: (-candidate.priority, candidate.url))


def _norm(value: str) -> str:
    return "".join(ch.lower() for ch in str(value or "") if ch.isalnum())
```

- [ ] **Step 4: Run the tests and verify pass**

Run:

```powershell
python -m pytest tests/test_source_candidate_registry.py -q
```

Expected:

```text
3 passed
```

- [ ] **Step 5: Commit**

```powershell
git add src/hsconfig/source_candidate_registry.py tests/test_source_candidate_registry.py
git commit -m "Add HSConfig source candidate registry"
```

## Task 2: Wire Candidate Registry Into Configure Source Acquisition

**Files:**
- Modify: `src/hsconfig/commands/configure.py`
- Modify: `src/hsconfig/source_acquisition.py`
- Modify: `tests/test_configure_auto_source.py`
- Modify: `tests/test_source_acquisition.py`

**Interfaces:**
- Consumes: `source_candidates_for_deck(...)` from Task 1.
- Produces: `configure_summary.json["source_candidate_urls"]`.
- Produces: `source_acquisition_report["candidate_registry_url_count"]`.

- [ ] **Step 1: Add configure test for automatic candidate URLs**

Add this test to `tests/test_configure_auto_source.py`, adapting the existing configure helper used in that file:

```python
def test_configure_online_source_uses_registry_when_no_source_url(tmp_path):
    out = tmp_path / "shadow"
    args = configure_args(
        deck_name="ShadowPriest",
        deck_code="AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=",
        out=out,
        online_source=True,
        auto_source=True,
        source_url=[],
        source_fixture_url_map_json="tests/fixtures/source_search_shadowpriest_2026.json",
    )

    payload, status = configure_payload(args)

    assert status == 0
    assert payload["source_acquisition_path"]
    assert any("voidburn-wild-aggro-shadow-priest" in url for url in payload["source_candidate_urls"])
```

If the file does not already expose `configure_args`, create a small local `argparse.Namespace` helper in the test with all fields required by `configure_payload`.

- [ ] **Step 2: Add acquisition test for registry metadata preservation**

Add this test to `tests/test_source_acquisition.py`:

```python
def test_source_acquisition_records_candidate_registry_metadata(tmp_path):
    payload = collect_public_source_records(
        deck_name="ShadowPriest",
        deck_identity={"cards": [{"card_id": "SW_448", "name": "Darkbishop Benedictus"}]},
        source_urls=["https://www.hearthpwn.com/decks/1461644-voidburn-wild-aggro-shadow-priest"],
        current_date="2026-07-16",
        fetcher=lambda url, timeout: (
            200,
            "text/html",
            b"<html><title>Voidburn Wild Aggro Shadow Priest</title><body>2026 Mulligan Tips: Keep Papercraft Angel. Do not keep any 4-cost or higher cards. Darkbishop Benedictus turns your hero power into Mind Spike.</body></html>",
        ),
        resolver=lambda host: ["93.184.216.34"],
    )

    record = payload["source_records"][0]
    assert record["source_family"] == "guide"
    assert record["source_visibility"] == "full_text"
    assert record["promotion_eligible"] is True
    assert record["strong_promotion_eligible"] is True
    assert record["first_missing_source_action"] == "none"
```

- [ ] **Step 3: Run tests and verify failure**

Run:

```powershell
python -m pytest tests/test_configure_auto_source.py tests/test_source_acquisition.py -q
```

Expected before implementation:

```text
FAILED
```

The failure should mention missing `source_candidate_urls` or registry URLs not being passed.

- [ ] **Step 4: Patch configure to merge user URLs and registry URLs**

In `src/hsconfig/commands/configure.py`, import the registry:

```python
from hsconfig.source_candidate_registry import source_candidates_for_deck
```

In `configure_payload`, before calling `source_acquire_payload`, compute:

```python
explicit_source_urls = list(getattr(args, "source_url", []) or [])
registry_candidates = source_candidates_for_deck(
    args.deck_name,
    args.deck_code,
)
registry_source_urls = [candidate.url for candidate in registry_candidates]
source_urls = _dedupe_preserve_order([*explicit_source_urls, *registry_source_urls])
```

Pass `source_urls` into `source_acquire_payload` instead of raw `args.source_url`.

Add this helper near the bottom of `configure.py`:

```python
def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        clean = str(value or "").strip()
        if clean and clean not in seen:
            seen.add(clean)
            result.append(clean)
    return result
```

In the final `_finish` OK payload, add:

```python
"source_candidate_urls": source_urls if bool(getattr(args, "online_source", False)) else [],
```

- [ ] **Step 5: Patch acquisition report metadata**

In `src/hsconfig/source_acquisition.py`, add `candidate_registry_url_count` only when records came from registry is not directly knowable. Use the count of deduped URLs for now:

```python
"candidate_registry_url_count": len(deduped_urls),
```

This is intentionally simple; Task 1 owns the registry, this module owns fetching.

- [ ] **Step 6: Run tests and verify pass**

Run:

```powershell
python -m pytest tests/test_configure_auto_source.py tests/test_source_acquisition.py tests/test_source_candidate_registry.py -q
```

Expected:

```text
passed
```

- [ ] **Step 7: Commit**

```powershell
git add src/hsconfig/commands/configure.py src/hsconfig/source_acquisition.py tests/test_configure_auto_source.py tests/test_source_acquisition.py
git commit -m "Use source candidates during HSConfig configure"
```

## Task 3: Strengthen Source Evidence Scoring Without Blocking Valid Decks

**Files:**
- Modify: `src/hsconfig/source_evidence_policy.py`
- Modify: `tests/test_source_evidence_policy.py`
- Modify: `tests/test_lean_source_backed_strong_autopilot.py`

**Interfaces:**
- Consumes: source records from Task 2.
- Produces unchanged function: `classify_source_evidence(record: Mapping[str, Any], *, deck_name: str, current_date: str | date | None) -> dict[str, Any]`.
- Required output keys: `trust_ceiling`, `source_lane`, `source_rank_lane`, `promotion_eligible`, `strong_promotion_eligible`, `promotion_blockers`, `first_missing_source_action`.

- [ ] **Step 1: Add exact policy tests**

Add these tests to `tests/test_source_evidence_policy.py`:

```python
from hsconfig.source_evidence_policy import classify_source_evidence


def _record(**overrides):
    base = {
        "source_url": "https://example.com/guide",
        "source_family": "guide",
        "source_visibility": "full_text",
        "deck_match_scope": "deck_or_archetype_matched",
        "publication_year": 2026,
        "source_record_strength": "candidate_strong",
        "normalized_text": "2026 Wild guide with Mulligan Tips and Gameplan.",
    }
    base.update(overrides)
    return base


def test_current_full_text_deck_matched_guide_promotes_to_source_backed_strong():
    verdict = classify_source_evidence(_record(), deck_name="ShadowPriest", current_date="2026-07-16")

    assert verdict["trust_ceiling"] == "source_backed_strong"
    assert verdict["source_lane"] == "deck_matched_public_guide"
    assert verdict["promotion_eligible"] is True
    assert verdict["strong_promotion_eligible"] is True
    assert verdict["promotion_blockers"] == []
    assert verdict["first_missing_source_action"] == "none"


def test_decklist_only_remains_valid_but_not_strong():
    verdict = classify_source_evidence(
        _record(
            source_family="decklist",
            source_visibility="decklist_only",
            source_record_strength="partial",
        ),
        deck_name="ShadowPriest",
        current_date="2026-07-16",
    )

    assert verdict["trust_ceiling"] == "decklist_informed"
    assert verdict["strong_promotion_eligible"] is False
    assert "decklist_not_guide" in verdict["promotion_blockers"]
    assert verdict["first_missing_source_action"] != "none"


def test_static_semantics_only_supports_cardid_effects_not_strategy():
    verdict = classify_source_evidence(
        _record(
            source_family="hearthstonejson_static_semantics",
            claim_kind="hero_power_transform",
            source_record_strength="official_static_semantics",
        ),
        deck_name="ShadowPriest",
        current_date="2026-07-16",
    )

    assert verdict["trust_ceiling"] == "static_semantics_only"
    assert verdict["static_runtime_surface_eligible"] is True
    assert verdict["static_runtime_surface_scope"] == "cardid_effect"
    assert verdict["strong_promotion_eligible"] is False
```

- [ ] **Step 2: Run tests and verify failure or current pass**

Run:

```powershell
python -m pytest tests/test_source_evidence_policy.py -q
```

Expected:

```text
failed or passed
```

If the tests already pass, do not rewrite `source_evidence_policy.py`; only keep the tests.

- [ ] **Step 3: Patch only failing scoring branches**

If needed, update `source_evidence_policy.py` with these exact rules:

```python
strong_guide = (
    family in GUIDE_FAMILIES
    and visibility == "full_text"
    and deck_scope in {"deck_matched", "deck_or_archetype_matched"}
    and source_rank_lane in {"guide_current_deck_match", "guide_evergreen_wild_archetype"}
    and source_type not in NON_PROMOTING_SOURCE_TYPES
)
promotion_eligible = strong_guide and not blockers
```

Keep decklist, stats, and static blockers intact.

- [ ] **Step 4: Run tests and verify pass**

Run:

```powershell
python -m pytest tests/test_source_evidence_policy.py tests/test_lean_source_backed_strong_autopilot.py -q
```

Expected:

```text
passed
```

- [ ] **Step 5: Commit**

```powershell
git add src/hsconfig/source_evidence_policy.py tests/test_source_evidence_policy.py tests/test_lean_source_backed_strong_autopilot.py
git commit -m "Harden source evidence strong scoring"
```

## Task 4: Expand Atomic Claim Extraction For Guide-Backed Runtime Surfaces

**Files:**
- Modify: `src/hsconfig/source_claim_compiler.py`
- Modify: `tests/test_source_claim_compiler.py`

**Interfaces:**
- Existing function stays: `compile_source_search_records(*, deck_name: str, deck_identity: Mapping[str, Any], acquired_records: Sequence[Mapping[str, Any]], current_date: str | date | None = None) -> dict[str, Any]`.
- Claim rows must remain dict-based and sorted.
- Required claim kinds: `mulligan_keep`, `mulligan_discard`, `hero_power_transform`, `gameplan_posture`, `targeting_rule`, `combo_sequence`, `weapon_plan`, `draw_engine`, `board_plan`.

- [ ] **Step 1: Add ShadowPriest claim tests**

Add to `tests/test_source_claim_compiler.py`:

```python
def test_shadowpriest_guide_extracts_keep_discard_hero_power_and_face_plan():
    deck_identity = {
        "cards": [
            {"card_id": "SW_448", "name": "Darkbishop Benedictus", "cost": 5, "text": "Start of Game: If the spells in your deck are all Shadow, enter Shadowform."},
            {"card_id": "BAR_735", "name": "Voidtouched Attendant", "cost": 1, "text": "Both heroes take one extra damage."},
            {"card_id": "TOY_879", "name": "Papercraft Angel", "cost": 2, "text": "Your Hero Power costs less."},
            {"card_id": "SW_091", "name": "Shadowcloth Needle", "cost": 1, "text": "After you cast a Shadow spell, deal 1 damage to all enemies."},
        ]
    }
    acquired_records = [{
        "source_url": "https://www.hearthpwn.com/decks/1461644-voidburn-wild-aggro-shadow-priest",
        "source_title": "Voidburn Wild Aggro Shadow Priest",
        "source_family": "guide",
        "source_visibility": "full_text",
        "deck_match_scope": "deck_or_archetype_matched",
        "publication_year": 2026,
        "promotion_eligible": True,
        "strong_promotion_eligible": True,
        "normalized_text": (
            "Mulligan Tips: Keep Papercraft Angel and Shadowcloth Needle. "
            "Keep Spirit of the Kaldorei if you have Papercraft Angel or the Coin. "
            "Don't keep any 4 cost or higher cards. "
            "Use shadow hero power to clear enemy board or go face versus control and combo decks."
        ),
    }]

    result = compile_source_search_records(
        deck_name="ShadowPriest",
        deck_identity=deck_identity,
        acquired_records=acquired_records,
        current_date="2026-07-16",
    )
    claims = [claim for record in result["records"] for claim in record["claims"]]

    assert _has_claim(claims, "mulligan_keep", "TOY_879")
    assert _has_claim(claims, "mulligan_keep", "SW_091")
    assert _has_claim(claims, "mulligan_discard", "SW_448")
    assert _has_claim(claims, "hero_power_transform", "SW_448")
    assert any(claim["claim_kind"] == "gameplan_posture" for claim in claims)
    assert not _has_claim(claims, "mulligan_keep", "SW_448")


def _has_claim(claims, kind, card_id):
    return any(
        claim.get("claim_kind") == kind
        and card_id in claim.get("cards", [])
        for claim in claims
    )
```

- [ ] **Step 2: Add non-Shadow mechanics tests**

Add to `tests/test_source_claim_compiler.py`:

```python
def test_bigshaman_guide_extracts_combo_sequence_and_cheat_plan():
    deck_identity = {
        "cards": [
            {"card_id": "CS2_042", "name": "Ancestor's Call", "cost": 4},
            {"card_id": "GIL_820", "name": "Eureka!", "cost": 6},
            {"card_id": "KAR_114", "name": "Barnes", "cost": 5},
            {"card_id": "EX1_245", "name": "Reincarnate", "cost": 1},
        ]
    }
    acquired_records = [{
        "source_url": "https://www.hearthpwn.com/decks/1186371-big-shaman-in-depth-guide",
        "source_title": "Big Shaman In-Depth Guide",
        "source_family": "guide",
        "source_visibility": "full_text",
        "deck_match_scope": "deck_or_archetype_matched",
        "publication_year": 2018,
        "format_scope": "wild",
        "evergreen_wild_archetype": True,
        "promotion_eligible": True,
        "strong_promotion_eligible": True,
        "normalized_text": "Mulligan for Ancestor's Call, Eureka!, and Barnes. If you have Barnes, keep Reincarnate so you can do Barnes and Reincarnate for a full statted minion.",
    }]

    result = compile_source_search_records(
        deck_name="BigShaman",
        deck_identity=deck_identity,
        acquired_records=acquired_records,
        current_date="2026-07-16",
    )
    claims = [claim for record in result["records"] for claim in record["claims"]]

    assert _has_claim(claims, "mulligan_keep", "CS2_042")
    assert _has_claim(claims, "mulligan_keep", "GIL_820")
    assert _has_claim(claims, "mulligan_keep", "KAR_114")
    assert any(claim["claim_kind"] == "combo_sequence" for claim in claims)


def test_kingslayer_guide_extracts_weapon_plan():
    deck_identity = {
        "cards": [
            {"card_id": "CFM_630", "name": "Kingsbane", "cost": 1},
            {"card_id": "TRL_074", "name": "Cavern Shinyfinder", "cost": 2},
            {"card_id": "BAR_319", "name": "Silverleaf Poison", "cost": 1},
        ]
    }
    acquired_records = [{
        "source_url": "https://www.reddit.com/r/wildhearthstone/comments/1p8sp6f/legend_1478_kingsbane_rogue/",
        "source_title": "Legend Kingsbane Rogue",
        "source_family": "community_guide",
        "source_visibility": "full_text",
        "deck_match_scope": "deck_or_archetype_matched",
        "publication_year": 2026,
        "promotion_eligible": True,
        "strong_promotion_eligible": True,
        "normalized_text": "Mulligan: Keep Kingsbane, minions that draw Kingsbane, and Silverleaf Poison. Gameplay: Buff weapon, draw cards, hit face, repeat as necessary.",
    }]

    result = compile_source_search_records(
        deck_name="Kingslayer",
        deck_identity=deck_identity,
        acquired_records=acquired_records,
        current_date="2026-07-16",
    )
    claims = [claim for record in result["records"] for claim in record["claims"]]

    assert _has_claim(claims, "mulligan_keep", "CFM_630")
    assert _has_claim(claims, "mulligan_keep", "BAR_319")
    assert any(claim["claim_kind"] == "weapon_plan" for claim in claims)
```

- [ ] **Step 3: Run tests and verify failure**

Run:

```powershell
python -m pytest tests/test_source_claim_compiler.py -q
```

Expected:

```text
FAILED
```

At least `weapon_plan` or `combo_sequence` should fail until implemented.

- [ ] **Step 4: Patch claim compiler with bounded pattern extractors**

In `source_claim_compiler.py`, add claim kinds to `_claim_family`:

```python
if claim_kind in {"weapon_plan"}:
    return "weapon"
if claim_kind in {"draw_engine"}:
    return "draw"
if claim_kind in {"board_plan"}:
    return "board"
```

In `_compile_guide_claims`, after existing gameplan posture logic, add calls:

```python
_compile_combo_sequence_claims(compiled, deck_identity, text)
_compile_weapon_plan_claims(compiled, deck_identity, text)
_compile_draw_and_board_plan_claims(compiled, deck_identity, text)
```

Add helpers:

```python
def _compile_combo_sequence_claims(compiled: dict[str, Any], deck_identity: Mapping[str, Any], text: str) -> None:
    lowered = text.lower()
    combo_markers = ("combo", "sequence", "then", " so you can ", " and ")
    if not any(marker in lowered for marker in combo_markers):
        return
    mentioned = _mentioned_card_ids(deck_identity, text)
    if len(mentioned) < 2:
        return
    if any(marker in lowered for marker in ("barnes", "reincarnate", "ancestor's call", "eureka", "boar", "combo piece")):
        compiled["claims"].append(
            _claim(
                "combo_sequence",
                mentioned,
                "sequence_cards_together",
                _short_evidence(text, marker="combo"),
                "high",
                scope="deck",
            )
        )


def _compile_weapon_plan_claims(compiled: dict[str, Any], deck_identity: Mapping[str, Any], text: str) -> None:
    lowered = text.lower()
    if not any(marker in lowered for marker in ("weapon", "kingsbane", "poison")):
        return
    mentioned = _mentioned_card_ids(deck_identity, text)
    if not mentioned:
        return
    if any(marker in lowered for marker in ("buff weapon", "draw cards", "hit face", "silverleaf poison")):
        compiled["claims"].append(
            _claim(
                "weapon_plan",
                mentioned,
                "buff_draw_attack_face",
                _short_evidence(text, marker="weapon"),
                "high",
                scope="deck",
            )
        )


def _compile_draw_and_board_plan_claims(compiled: dict[str, Any], deck_identity: Mapping[str, Any], text: str) -> None:
    lowered = text.lower()
    if any(marker in lowered for marker in ("card draw", "draw engine", "draw cards", "aeroponics", "beanstalk")):
        compiled["claims"].append(
            _claim(
                "draw_engine",
                _mentioned_card_ids(deck_identity, text),
                "prioritize_draw_engine",
                _short_evidence(text, marker="draw"),
                "high",
                scope="deck",
            )
        )
    if any(marker in lowered for marker in ("build a board", "contest board", "board control", "clear enemy board")):
        compiled["claims"].append(
            _claim(
                "board_plan",
                _mentioned_card_ids(deck_identity, text),
                "board_state_priority",
                _short_evidence(text, marker="board"),
                "high",
                scope="deck",
            )
        )


def _mentioned_card_ids(deck_identity: Mapping[str, Any], text: str) -> list[str]:
    lowered = text.lower()
    result: list[str] = []
    for card in _deck_cards(deck_identity):
        name = _text(card.get("name", ""))
        card_id = _text(card.get("card_id", ""))
        if name and card_id and name.lower() in lowered:
            result.append(card_id)
    return sorted(set(result))
```

- [ ] **Step 5: Run tests and verify pass**

Run:

```powershell
python -m pytest tests/test_source_claim_compiler.py -q
```

Expected:

```text
passed
```

- [ ] **Step 6: Commit**

```powershell
git add src/hsconfig/source_claim_compiler.py tests/test_source_claim_compiler.py
git commit -m "Extract guide-backed runtime source claims"
```

## Task 5: Promote Strong Only When Closure Is Complete By Card And Surface

**Files:**
- Modify: `src/hsconfig/source_autopilot.py`
- Modify: `src/hsconfig/source_claim_gap_report.py`
- Modify: `tests/test_source_autopilot.py`
- Modify: `tests/test_lean_source_backed_strong_autopilot.py`

**Interfaces:**
- Existing source-autopilot CLI payload remains stable.
- Produced report keys:
  - `semantic_status`
  - `source_backed_strong_closure`
  - `card_closure_lanes`
  - `surface_closure_lanes`
  - `default_only_runtime_surfaces`
  - `first_missing_source_action_by_card`
  - `first_missing_source_action_by_surface`
  - `runtime_apply_authority`

- [ ] **Step 1: Add strong closure report tests**

Add to `tests/test_source_autopilot.py`:

```python
def assert_strong_closure(report):
    assert report["semantic_status"] == "SOURCE_BACKED_STRONG"
    assert report["source_backed_strong_closure"]["closed"] is True
    assert report["default_only_runtime_surfaces"] == []
    assert report["first_missing_source_action_by_card"] == {}
    assert report["first_missing_source_action_by_surface"] == {}
    assert report["runtime_apply_authority"] == "reports/operator_summary.json"


def assert_partial_closure(report):
    assert report["semantic_status"] != "SOURCE_BACKED_STRONG"
    assert report["source_backed_strong_closure"]["closed"] is False
    assert report["runtime_apply_authority"] == "reports/operator_summary.json"
    assert report["first_missing_source_action_by_card"] or report["first_missing_source_action_by_surface"]


def test_source_autopilot_reports_strong_only_when_no_card_or_surface_gap(tmp_path):
    source_search_results = tmp_path / "source_search_results.json"
    source_search_results.write_text(
        json.dumps({
            "schema_version": 1,
            "deck_name": "ShadowPriest",
            "source_records": [{
                "source_url": "https://www.hearthpwn.com/decks/1461644-voidburn-wild-aggro-shadow-priest",
                "source_title": "Voidburn Wild Aggro Shadow Priest",
                "source_family": "guide",
                "source_visibility": "full_text",
                "deck_match_scope": "deck_or_archetype_matched",
                "publication_year": 2026,
                "promotion_eligible": True,
                "strong_promotion_eligible": True,
                "normalized_text": "Mulligan Tips: Keep Papercraft Angel and Shadowcloth Needle. Don't keep any 4 cost or higher cards. Use shadow hero power to clear enemy board or go face versus control and combo decks.",
            }],
        }),
        encoding="utf-8",
    )

    payload, status = source_autopilot_payload(
        argparse.Namespace(
            deck_name="ShadowPriest",
            deck_code="AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=",
            source_search_results_json=str(source_search_results),
            current_date="2026-07-16",
            out=str(tmp_path / "out"),
            cards_json=None,
            collectible_cards_json=None,
            full_cards_json=None,
            allow_placeholder=False,
            json=True,
        )
    )

    assert status == 0
    report = json.loads((tmp_path / "out" / "source_autopilot_report.json").read_text(encoding="utf-8"))
    assert_strong_closure(report)
```

If this test file does not import `json`, `argparse`, or `source_autopilot_payload`, add those imports.

- [ ] **Step 2: Add partial/decklist-only report test**

Add:

```python
def test_source_autopilot_reports_first_missing_link_for_decklist_only(tmp_path):
    source_search_results = tmp_path / "source_search_results.json"
    source_search_results.write_text(
        json.dumps({
            "schema_version": 1,
            "deck_name": "ShadowPriest",
            "source_records": [{
                "source_url": "https://example.com/decklist",
                "source_title": "ShadowPriest decklist",
                "source_family": "decklist",
                "source_visibility": "decklist_only",
                "deck_match_scope": "deck_or_archetype_matched",
                "publication_year": 2026,
                "promotion_eligible": False,
                "strong_promotion_eligible": False,
                "normalized_text": "Deck code only.",
            }],
        }),
        encoding="utf-8",
    )

    payload, status = source_autopilot_payload(
        argparse.Namespace(
            deck_name="ShadowPriest",
            deck_code="AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=",
            source_search_results_json=str(source_search_results),
            current_date="2026-07-16",
            out=str(tmp_path / "out"),
            cards_json=None,
            collectible_cards_json=None,
            full_cards_json=None,
            allow_placeholder=False,
            json=True,
        )
    )

    assert status == 0
    report = json.loads((tmp_path / "out" / "source_autopilot_report.json").read_text(encoding="utf-8"))
    assert_partial_closure(report)
    assert "add_card_specific_source_claim" in set(report["first_missing_source_action_by_surface"].values()) | set(report["first_missing_source_action_by_card"].values())
```

- [ ] **Step 3: Run tests and verify failure**

Run:

```powershell
python -m pytest tests/test_source_autopilot.py tests/test_lean_source_backed_strong_autopilot.py -q
```

Expected:

```text
FAILED
```

The failure should be missing closure keys or semantic status.

- [ ] **Step 4: Patch source_autopilot report assembly**

In `src/hsconfig/source_autopilot.py`, add a bounded report assembler:

```python
REQUIRED_STRONG_SURFACES = {
    "mulligan",
    "cardid_effects",
    "gameplan_posture",
}


def _build_closure_report(compiled_records: list[dict[str, Any]]) -> dict[str, Any]:
    claims = [
        claim
        for record in compiled_records
        for claim in record.get("claims", [])
        if isinstance(claim, dict)
    ]
    strong_claims = [
        claim for claim in claims
        if claim.get("promotion_eligible", True) is not False
        and claim.get("source_confidence") == "high"
    ]
    surface_lanes = _surface_lanes(strong_claims)
    card_lanes = _card_lanes(strong_claims)
    missing_by_surface = {
        surface: "add_card_specific_source_claim"
        for surface in REQUIRED_STRONG_SURFACES
        if surface_lanes.get(surface) not in {"emitted", "static_only", "not_applicable"}
    }
    default_only = sorted(
        surface for surface, lane in surface_lanes.items()
        if lane == "default_only"
    )
    closed = not missing_by_surface and not default_only
    return {
        "semantic_status": "SOURCE_BACKED_STRONG" if closed else "VALID_BUT_NOT_GUIDE_STRONG",
        "source_backed_strong_closure": {"closed": closed},
        "card_closure_lanes": card_lanes,
        "surface_closure_lanes": surface_lanes,
        "default_only_runtime_surfaces": default_only,
        "first_missing_source_action_by_card": {} if closed else _missing_card_actions(card_lanes),
        "first_missing_source_action_by_surface": {} if closed else missing_by_surface,
        "runtime_apply_authority": "reports/operator_summary.json",
    }
```

Add helper implementations:

```python
def _surface_lanes(claims: list[dict[str, Any]]) -> dict[str, str]:
    lanes = {surface: "source_gap" for surface in REQUIRED_STRONG_SURFACES}
    for claim in claims:
        family = str(claim.get("claim_family", ""))
        kind = str(claim.get("claim_kind", ""))
        if family == "mulligan":
            lanes["mulligan"] = "emitted"
        if kind == "hero_power_transform":
            lanes["cardid_effects"] = "emitted"
        if family in {"gameplan", "weapon", "combo", "draw", "board"}:
            lanes["gameplan_posture"] = "emitted"
    return lanes


def _card_lanes(claims: list[dict[str, Any]]) -> dict[str, str]:
    result: dict[str, str] = {}
    for claim in claims:
        for card_id in claim.get("cards", []) or []:
            result[str(card_id)] = "lowered"
    return result


def _missing_card_actions(card_lanes: dict[str, str]) -> dict[str, str]:
    return {
        card_id: "add_card_specific_source_claim"
        for card_id, lane in card_lanes.items()
        if lane == "source_gap"
    }
```

Integrate this report into the existing `source_autopilot_report.json` write path without removing existing keys.

- [ ] **Step 5: Run tests and verify pass**

Run:

```powershell
python -m pytest tests/test_source_autopilot.py tests/test_lean_source_backed_strong_autopilot.py -q
```

Expected:

```text
passed
```

- [ ] **Step 6: Commit**

```powershell
git add src/hsconfig/source_autopilot.py src/hsconfig/source_claim_gap_report.py tests/test_source_autopilot.py tests/test_lean_source_backed_strong_autopilot.py
git commit -m "Close source autopilot by card and surface"
```

## Task 6: Add Representative 12-Deck No-Default-Only Matrix

**Files:**
- Modify: `tests/test_universal_wild_no_block_matrix.py`
- Modify: `tests/test_shadowpriest_fresh_closure_proof.py`
- Add/modify: `tests/fixtures/source_guides/*.html`
- Add/modify fixture URL map if existing pattern supports it.

**Interfaces:**
- Consumes normal CLI path through `configure_payload`.
- Produces matrix assertions for all supplied decks.

**Representative Decks:**

```python
REPRESENTATIVE_DECKS = [
    ("ShadowPriest", "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA="),
    ("CtAPaladin", "AAEBAZ8FBowBwP0ChJYFzpwGprMGg8IHDIgO+NICg94DkeQDzusDyaAE4aQEwcQFhY4GmY4G9ZUGmvwHAAA="),
    ("PirateRogue", "AAEBAaIHApG8AuXRAg6MAtQF+w/psAPz3QOvoASKyQSa2wTXowW/9wXWngb8pQb8qAatxQYAAA=="),
    ("BigShaman", "AAEBAaoIBpQD5LcDv84E9qMGgbgGmvYGDM4P0hP2vQKPlAPW9QO8tgT08gXqmAbGpgakpwb44gas/QYAAA=="),
    ("Discolock", "AAEBAf0GBM4Hj4ID8aEG9qEGDbW5A9XRA9DhA5iSBauSBZXKBteXB4SZB6StB8ayB9a+B9m+B8+/BwAA"),
    ("TreantDruid", "AAEBAZICAt/7ApOyBw7NuwLB8wL8rQP/rQOV4APs9QOvgASuwASy3QTO5AWw+gXZ/wXJ0Aat4gYAAA=="),
    ("ImbueMage", "AAEBAf0EBIUXm80DvO0Egb8GDcAB9KsD0+wD1uwDr8QForMG1voG3PoG9PwG94EHs4cHwIcH7o0HAAA="),
    ("MechPala", "AAEBAZ8FAtS9BMekBg6f9QLW/gLX/gKHrgOStQThtQTa0wTZ0AW5/gWf4Qa08Qbi8Qa6lgea/AcAAQPzswbHpAb2swbHpAbu3gbHpAYAAA=="),
    ("Kingslayer", "AAEBAaIHBpG8ApKDB4aoB4eoB4ioB4jZBwyMAtQF6bAD1bYEiskE16MF7p4G/KUG/KgGs8EG6sQGrcUGAAA="),
    ("Boarlock", "AAEBAf0GBuAF054G7qEGxKIG0YIHqYgHDJDHAvLQAp2pA5vNA9P5A6bqBPTGBYSeBpWzBpTKBoSZB4adBwAA"),
    ("PirateDH", "AAEBAea5AwaRvALUyAP51QOHiwTh+AX8wAYM+w/psAPyyQPltgSl4gSr4gSVqgX8qAbYwAb2wAatxQax6wYAAA=="),
    ("CuteWarrior", "AAEBAQcEkbwCkdAD69YHstgHDY0Q6bADpLYDxN4D/9sEj5UFlaoFtNEF9PIFovoF/KgGltMGtI8HAAA="),
]
```

- [ ] **Step 1: Add matrix test**

Add to `tests/test_universal_wild_no_block_matrix.py`:

```python
@pytest.mark.parametrize(("deck_name", "deck_code"), REPRESENTATIVE_DECKS)
def test_representative_deck_configure_never_blocks_and_never_default_only(tmp_path, deck_name, deck_code):
    out = tmp_path / deck_name
    args = argparse.Namespace(
        deck_name=deck_name,
        deck_code=deck_code,
        out=str(out),
        runtime_root=str(tmp_path / "runtime"),
        online_source=True,
        auto_source=True,
        source_url=[],
        source_fixture_url_map_json="tests/fixtures/source_search_11_deck_matrix.json",
        source_fetch_timeout_seconds=1.0,
        current_date="2026-07-16",
        source_search_results_json=None,
        source_evidence_json=None,
        cards_json=None,
        collectible_cards_json=None,
        full_cards_json=None,
        allow_placeholder=False,
        apply=False,
        json=True,
    )

    payload, status = configure_payload(args)

    assert status == 0
    assert payload["status"] == "OK"
    operator_summary = json.loads((out / "04_package" / "reports" / "operator_summary.json").read_text(encoding="utf-8"))
    assert operator_summary["load_safety"]["mode"] == "load_safe_apply"
    source_report_path = out / "03_source_autopilot" / "source_autopilot_report.json"
    if not source_report_path.exists():
        source_report_path = out / "02_source_autopilot" / "source_autopilot_report.json"
    source_report = json.loads(source_report_path.read_text(encoding="utf-8"))
    assert source_report["default_only_runtime_surfaces"] == []
    assert source_report["semantic_status"] in {
        "SOURCE_BACKED_STRONG",
        "STATIC_SEMANTICS_USABLE",
        "VALID_BUT_NOT_GUIDE_STRONG",
    }
```

If `operator_summary["load_safety"]["mode"]` is not the current field shape, use the existing load-safe field in the repository's apply-gate tests. Do not change the product output just to satisfy this assertion.

- [ ] **Step 2: Add ShadowPriest strong assertion**

In `tests/test_shadowpriest_fresh_closure_proof.py`, add:

```python
def test_shadowpriest_source_backed_strong_keeps_effect_not_opening_hand(tmp_path):
    package_dir = build_shadowpriest_source_backed_package(tmp_path)

    mulligan = json.loads((package_dir / "Mulligan.json").read_text(encoding="utf-8"))
    darkbishop = json.loads((package_dir / "CardID" / "SW_448.json").read_text(encoding="utf-8"))
    source_report = json.loads((package_dir / "reports" / "source_autopilot_report.json").read_text(encoding="utf-8"))

    kept_ids = {row.get("card_id") for row in mulligan.get("rules", []) if row.get("action") == "keep"}
    assert "SW_448" not in kept_ids
    assert any("Mind Spike" in json.dumps(row) or "Shadowform" in json.dumps(row) for row in darkbishop.get("rules", []))
    assert source_report["default_only_runtime_surfaces"] == []
    assert source_report["semantic_status"] == "SOURCE_BACKED_STRONG"
```

Use the existing ShadowPriest package helper if the file already has one. If not, create `build_shadowpriest_source_backed_package(tmp_path)` in the test using `configure_payload` with fixture source URLs.

- [ ] **Step 3: Run matrix tests and verify failure**

Run:

```powershell
python -m pytest tests/test_universal_wild_no_block_matrix.py tests/test_shadowpriest_fresh_closure_proof.py -q
```

Expected:

```text
FAILED
```

The failure should expose exact output-shape or closure-report gaps.

- [ ] **Step 4: Add compact fixtures only where missing**

For each new fixture, write a small HTML page with one title, one date/year marker, one deck name/archetype marker, and only the needed guide sentences. Example for `tests/fixtures/source_guides/imbuemage_current_guide.html`:

```html
<html>
  <head><title>Wild Imbue Mage Guide 2026</title></head>
  <body>
    <h1>Wild Imbue Mage</h1>
    <p>Updated June 4, 2026. Mulligan Strategy: look for Bitterbloom Knight, Spirit Gatherer, and Flutterwing Guardian.</p>
    <p>Depending on the matchup, consider Wisp plus Divination for a strong turn 2 or 3 draw setup.</p>
    <p>Gameplan: flexible aggressive and hero-power focused play depending on the matchup.</p>
  </body>
</html>
```

Do not copy full articles into fixtures.

- [ ] **Step 5: Run tests and verify pass**

Run:

```powershell
python -m pytest tests/test_universal_wild_no_block_matrix.py tests/test_shadowpriest_fresh_closure_proof.py -q
```

Expected:

```text
passed
```

- [ ] **Step 6: Commit**

```powershell
git add tests/test_universal_wild_no_block_matrix.py tests/test_shadowpriest_fresh_closure_proof.py tests/fixtures/source_guides
git commit -m "Prove representative decks are non-default-only"
```

## Task 7: Update Operator Docs And HSConfig Skill Boundary

**Files:**
- Modify: `docs/operator/source-backed-strong-closure.md`
- Modify: `docs/operator/guide-research-policy.md`
- Modify: `.agents/skills/hsconfig/SKILL.md`

**Interfaces:**
- Consumed by operators and future Codex runs.
- No runtime output shape change.

- [ ] **Step 1: Update source-backed closure doc**

Add this policy block to `docs/operator/source-backed-strong-closure.md`:

```markdown
## Source Documents Closure Engine

`SOURCE_BACKED_STRONG` is an evidence-quality verdict, not an apply gate. HSConfig must still build the best load-safe package for valid deck input when source coverage is partial.

Strong closure requires all of the following:

- at least one current or evergreen Wild full-text public guide source matched to the deck or archetype,
- atomic source claims for every required deck profile surface,
- no `default_only_runtime_surfaces`,
- no unresolved first missing source action,
- static semantics used only for deterministic CardID/effect rows, not mulligan or strategy inference.

Non-strong packages remain valid when they are load-safe and explain the first missing source action.

Darkbishop Benedictus boundary:

- `SW_448` must preserve `hero_power_transform`, Shadowform, and Mind Spike runtime semantics.
- `SW_448` must not become a `mulligan_keep` from Start-of-Game text.
- if a guide says not to keep 4-cost-or-higher cards, `SW_448` may be a `mulligan_discard` claim.
```

- [ ] **Step 2: Update guide research policy**

Add:

```markdown
## Source Ranking

Use this order:

1. current full-text deck guide with mulligan and gameplan text,
2. current full-text archetype guide with matching core cards,
3. evergreen Wild archetype guide with matching core cards,
4. community guide or Reddit guide with explicit deck code and card-specific advice,
5. decklist/stat page as identity or meta context only.

Decklists, snippets, stats, generated defaults, and policy defaults must not promote a runtime surface to `SOURCE_BACKED_STRONG`.
```

- [ ] **Step 3: Update skill instructions**

In `.agents/skills/hsconfig/SKILL.md`, ensure the normal operator sequence says:

```markdown
For a new deck:

1. run `python -m hsconfig configure --deck-name ... --deck-code ... --runtime-root ... --online-source --auto-source --json`
2. inspect `reports/operator_summary.json` for load/apply authority,
3. inspect `source_autopilot_report.json` for evidence status,
4. accept `VALID_BUT_NOT_GUIDE_STRONG` when it is load-safe and no runtime surface is default-only,
5. use `SOURCE_BACKED_STRONG` as a quality label, not as a required apply gate.
```

- [ ] **Step 4: Run docs-related tests**

Run:

```powershell
python -m pytest tests/test_skill_files.py tests/test_operator_docs_contract_policy.py tests/test_docs_active_path.py -q
```

Expected:

```text
passed
```

- [ ] **Step 5: Commit**

```powershell
git add docs/operator/source-backed-strong-closure.md docs/operator/guide-research-policy.md .agents/skills/hsconfig/SKILL.md
git commit -m "Document HSConfig source closure engine"
```

## Task 8: Final Verification

**Files:**
- All changed source, tests, fixtures, docs, and skill files.

- [ ] **Step 1: Run targeted source closure suite**

Run:

```powershell
python -m pytest tests/test_source_candidate_registry.py tests/test_source_acquisition.py tests/test_source_evidence_policy.py tests/test_source_claim_compiler.py tests/test_source_autopilot.py tests/test_universal_wild_no_block_matrix.py tests/test_shadowpriest_fresh_closure_proof.py tests/test_lean_source_backed_strong_autopilot.py -q
```

Expected:

```text
passed
```

- [ ] **Step 2: Run full test suite**

Run:

```powershell
python -m pytest -q
```

Expected:

```text
passed
```

- [ ] **Step 3: Run ShadowPriest live-style configure proof without apply**

Run:

```powershell
python -m hsconfig configure --deck-name ShadowPriest --deck-code AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA= --runtime-root C:\Users\darbo\Desktop\HS --online-source --auto-source --out tmp\source-documents-closure-shadowpriest-proof --json
```

Expected:

```text
"status": "OK"
```

Then inspect:

```powershell
python - <<'PY'
import json
from pathlib import Path
root = Path(r"tmp\source-documents-closure-shadowpriest-proof")
report = json.loads((root / "03_source_autopilot" / "source_autopilot_report.json").read_text(encoding="utf-8"))
summary = json.loads((root / "04_package" / "reports" / "operator_summary.json").read_text(encoding="utf-8"))
print(report["semantic_status"])
print(report["default_only_runtime_surfaces"])
print(summary.get("runtime_apply_authority", "reports/operator_summary.json"))
PY
```

Expected:

```text
SOURCE_BACKED_STRONG
[]
reports/operator_summary.json
```

- [ ] **Step 4: Inspect git status**

Run:

```powershell
git status --short --branch
```

Expected:

```text
## codex/hsconfig-source-backed-strong-autopilot
```

or a clean equivalent branch line after committed changes.

- [ ] **Step 5: Confirm no generated private outputs are staged**

Run:

```powershell
git diff --cached --name-only
```

Expected staged paths only under:

```text
src/hsconfig/
tests/
docs/operator/
.agents/skills/hsconfig/
```

If `tmp/`, `outputs/`, `.pytest_cache/`, `.ruff_cache/`, raw logs, or runtime evidence appear, unstage/remove those artifacts before finalizing.

## Self-Review Checklist

- [ ] The plan keeps HSConfig narrow and does not rebuild HSTuner.
- [ ] The plan does not introduce any human approval gate.
- [ ] The plan does not block valid decks when guide evidence is partial.
- [ ] The plan makes `SOURCE_BACKED_STRONG` harder to fake, not easier to claim.
- [ ] The plan proves no default-only runtime surface is hidden.
- [ ] The plan preserves Darkbishop effect semantics without creating a false mulligan keep.
- [ ] The plan covers the 12 representative decks supplied by the operator.
- [ ] The plan uses fixtures for tests and live network only for operator proof.
- [ ] The plan keeps `reports/operator_summary.json` as apply authority.
- [ ] The plan avoids new dependencies and broad orchestration.

## Execution Handoff

Plan complete. Recommended execution mode:

```text
Subagent-Driven Umsetzung dieses Plans starten
```

Use read-only subagents for source-policy review, claim-extraction review, and representative deck matrix review. Use one writing worker for candidate registry/configure wiring, one writing worker for source claim/autopilot closure, and one writing worker for docs/skill sync. The main agent must consolidate diffs, run the full verification suite, and keep generated runtime proof outputs out of git.

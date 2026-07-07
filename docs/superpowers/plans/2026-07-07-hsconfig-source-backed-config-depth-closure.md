# HSConfig Source-Backed Config Depth Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make HSConfig reliably produce source-backed, guide-depth HearthRanger VisionAI Step-1 config packages from a deck input, while staying lean and separate from HSTuner.

**Architecture:** Keep HSConfig as a deterministic pre-game config compiler. Codex or the skill performs online guide research and passes structured `source_documents`; HSConfig validates, normalizes, atomizes, compiles, reports, and applies only validated runtime config. The implementation closes the current gaps in deck identity, per-card claim coverage, Mulligan selector depth, CardID behavior routing, Combo timing, GlobalValues authority, and multi-deck proof.

**Tech Stack:** Python 3.11+, `hearthstone>=9.0.0`, pytest, existing `hsconfig` package, HearthRanger VisionAI JSON surfaces, HearthstoneJSON metadata.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig` for `Teufelsboy/HSConfig`.
- Keep HSConfig separate from HSTuner.
- Do not add replay parsing, HDT parsing, winrate validation, candidate promotion, runtime missplay analysis, or post-run tuning.
- Generated runtime packages belong under `outputs/` and stay ignored by git.
- Every implementation change must preserve exact deck and CardID identity.
- Every implementation change must preserve full `GlobalValues.json` key profiling.
- Every implementation change must preserve every card covered in the gameplan contract.
- Every implementation change must preserve strict JSON validation.
- Every implementation change must preserve row-level provenance for generated config rows.
- Runtime surfaces allowed in the normal path remain `GlobalValues.json`, `Mulligan.json`, deck-local `<CARDID>.json`, and `Combo.json`.
- `Presume.json` and `Concede.json` stay out of the normal path.

---

## File Structure

### Existing Files To Modify

- `src/hsconfig/deckstring_decode.py`
  - Normalize HearthSim sideboard triplets and preserve owner identity.
- `src/hsconfig/hearthstonejson.py`
  - Preserve additional static identity fields such as `heroPowerDbfId`, `questReward`, `playRequirements`, and `entourage`.
- `src/hsconfig/semantic_enrichment.py`
  - Consume preserved identity fields and keep known derived hero-power links provenance-tagged.
- `src/hsconfig/identity_graph.py`
  - Report sideboards, starting hero power, and unresolved linked entities.
- `src/hsconfig/guide_source_builder.py`
  - Strengthen source-document normalization and source-depth classification.
- `src/hsconfig/guide_claim_builder.py`
  - Atomize source documents into stricter claim rows and add conflict, freshness, and coverage support.
- `src/hsconfig/research_contract.py`
  - Carry richer claim maps into downstream contracts.
- `src/hsconfig/gameplan_contract.py`
  - Preserve source-backed posture, mulligan, usage, target, combo, and known-bad-pattern facts without flattening them.
- `src/hsconfig/mulligan_plan.py`
  - Move from card-only rules to selector-level ordered rules.
- `src/hsconfig/compile_mulligan.py`
  - Emit documented selectors and preserve plan order.
- `src/hsconfig/condition_format.py`
  - Expand only documented condition lowering required by Mulligan and CardID routing.
- `src/hsconfig/card_behavior_router.py`
  - Route claim-level intent to specific documented CardID behavior blocks.
- `src/hsconfig/compile_cardid.py`
  - Consume routed CardID rows and preserve row order.
- `src/hsconfig/combo_plan.py`
  - Require explicit order and timing before Combo emission.
- `src/hsconfig/compile_combo.py`
  - Keep runtime rows official-shape-only and move provenance to reports.
- `src/hsconfig/globalvalues_authority.py`
  - Make per-key authority explicit.
- `src/hsconfig/compile_globalvalues.py`
  - Consume authority rows and report copied, changed, and blocked keys.
- `src/hsconfig/config_readiness.py`
  - Improve readiness lanes and first missing link for guide depth.
- `src/hsconfig/operator_summary.py`
  - Strengthen operator-facing statuses and warnings.
- `src/hsconfig/cli.py`
  - Wire new reports into `research-deck`, `prepare`, and `build`.
- `src/hsconfig/validate_package.py`
  - Add stricter validation for new Mulligan, CardID, Combo, and GlobalValues contracts.
- `README.md`
  - Update normal workflow and readiness definitions.
- `.agents/skills/hsconfig/SKILL.md`
  - Update the installed repo skill workflow.
- `.agents/skills/hsconfig/references/*.md`
  - Update reference docs for source-backed depth.
- `docs/operator/guide-research-policy.md`
  - Document source-document and atomic-claim schema.

### New Files To Create

- `src/hsconfig/source_document_model.py`
  - Dataclasses and helpers for source documents, evidence rows, atomic claims, freshness, and conflicts.
- `src/hsconfig/source_document_builder.py`
  - Deterministic normalizer from researched source documents into evidence rows and atomic claims.
- `src/hsconfig/card_behavior_surface_router.py`
  - Claim-level CardID block router with suppression reports.
- `src/hsconfig/option_identity_resolver.py`
  - Resolve Discover, Choose One, hero power, sideboard owner, and linked entity identities.
- `src/hsconfig/mulligan_selector.py`
  - Parse and validate documented Mulligan selectors.
- `src/hsconfig/combo_sequence_contract.py`
  - Validate combo order, timing, operator, and runtime row readiness.
- `src/hsconfig/globalvalues_key_authority.py`
  - Per-key GlobalValues authority registry.
- `tests/fixtures/mechpala_sideboard_deck.json`
  - Minimal decoded expectations for MechPala sideboard regression.
- `tests/fixtures/source_documents_shadowpriest_depth.json`
  - Strong source-document fixture for ShadowPriest.
- `tests/fixtures/source_documents_multiarchetype.json`
  - Compact source-document rows for broad archetype proof.

---

### Task 1: Fix Sideboard Deckstring Identity

**Files:**
- Modify: `src/hsconfig/deckstring_decode.py`
- Modify: `src/hsconfig/deck_identity.py`
- Modify: `src/hsconfig/identity_graph.py`
- Test: `tests/test_deckstring_decode.py`
- Test: `tests/test_identity_graph.py`

**Interfaces:**
- Consumes: `decode_deck_code(deck_code: str) -> dict[str, Any]`
- Produces: `decoded["sideboards"]` as `list[dict[str, Any]]`, each row containing `owner_dbf_id`, optional `owner_card_id`, and `cards`.

- [ ] **Step 1: Add a failing MechPala sideboard decode test**

Add this test to `tests/test_deckstring_decode.py`:

```python
MECHPALA_CODE = (
    "AAEBAZ8FAtS9BMekBg6f9QLW/gLX/gKHrgOStQThtQTa0wTZ0AW5/gWf4Qa08Qbi8Qa6lgea/"
    "AcAAQPzswbHpAb2swbHpAbu3gbHpAYAAA=="
)


def test_decode_mechpala_sideboards_from_hearthsim_triplets():
    decoded = decode_deck_code(MECHPALA_CODE)

    assert decoded["hero_dbf_id"] == 671
    assert decoded["format"] == "FT_WILD"
    assert decoded["card_count_total"] == 30
    assert decoded["sideboard_count"] == 3
    assert decoded["deckstring_decode_receipt"]["sideboard_unique_card_count"] == 3
    assert len(decoded["sideboards"]) == 1

    sideboard = decoded["sideboards"][0]
    assert sideboard["owner_dbf_id"] == 102983
    assert sideboard["owner_card_id"]
    assert {card["dbf_id"] for card in sideboard["cards"]} == {104947, 104950, 110446}
```

- [ ] **Step 2: Run the failing test**

Run:

```powershell
python -m pytest tests/test_deckstring_decode.py::test_decode_mechpala_sideboards_from_hearthsim_triplets -q
```

Expected before implementation:

```text
FAILED ... TypeError: 'int' object is not iterable
```

- [ ] **Step 3: Normalize sideboard shapes in `deckstring_decode.py`**

Replace `_sideboard_rows` with logic that accepts both grouped sideboards and HearthSim triplets:

```python
def _sideboard_rows(cards_db: dict[int, Any], sideboards: Any) -> list[dict[str, Any]]:
    grouped: dict[int | None, list[tuple[int, int]]] = {}
    if not sideboards:
        return []

    for sideboard in sideboards:
        if isinstance(sideboard, tuple) and len(sideboard) == 3:
            card_dbf_id, count, owner_dbf_id = sideboard
            grouped.setdefault(int(owner_dbf_id), []).append((int(card_dbf_id), int(count)))
            continue
        if isinstance(sideboard, tuple) and len(sideboard) >= 2:
            owner_dbf_id = int(sideboard[0]) if sideboard[0] is not None else None
            cards_payload = sideboard[1] or []
            grouped.setdefault(owner_dbf_id, []).extend(
                (int(dbf_id), int(count)) for dbf_id, count in cards_payload
            )
            continue
        if isinstance(sideboard, dict):
            owner = sideboard.get("owner") or sideboard.get("owner_dbf_id")
            owner_dbf_id = int(owner) if owner is not None else None
            cards_payload = sideboard.get("cards", [])
            grouped.setdefault(owner_dbf_id, []).extend(
                (int(dbf_id), int(count)) for dbf_id, count in cards_payload
            )
            continue
        raise ValueError(f"Unsupported sideboard row shape: {sideboard!r}")

    rows: list[dict[str, Any]] = []
    for index, (owner_dbf_id, cards_payload) in enumerate(sorted(grouped.items(), key=lambda item: str(item[0])), start=1):
        owner_card_id = None
        if owner_dbf_id is not None:
            owner_card = cards_db.get(owner_dbf_id)
            owner_card_id = str(owner_card.card_id) if owner_card is not None else None
        rows.append(
            {
                "sideboard_index": index,
                "owner_dbf_id": owner_dbf_id,
                "owner_card_id": owner_card_id,
                "cards": [_card_row(cards_db, dbf_id, count) for dbf_id, count in sorted(cards_payload)],
            }
        )
    return rows
```

- [ ] **Step 4: Preserve sideboard owner identity in `deck_identity.py`**

Ensure `build_deck_identity(...)` copies `owner_card_id` and `owner_dbf_id` unchanged into the identity payload. Add this assertion to the existing sideboard test:

```python
assert deck_identity["sideboards"][0]["owner_dbf_id"] == 102983
assert deck_identity["sideboards"][0]["owner_card_id"]
```

- [ ] **Step 5: Run targeted tests**

Run:

```powershell
python -m pytest tests/test_deckstring_decode.py tests/test_deck_identity.py tests/test_identity_graph.py -q
```

Expected:

```text
passed
```

- [ ] **Step 6: Commit**

```powershell
git add src/hsconfig/deckstring_decode.py src/hsconfig/deck_identity.py src/hsconfig/identity_graph.py tests/test_deckstring_decode.py tests/test_deck_identity.py tests/test_identity_graph.py
git commit -m "fix: decode HearthSim sideboard triplets"
```

---

### Task 2: Preserve Static Identity Fields And Derived Links

**Files:**
- Modify: `src/hsconfig/hearthstonejson.py`
- Modify: `src/hsconfig/semantic_enrichment.py`
- Modify: `src/hsconfig/identity_graph.py`
- Create: `src/hsconfig/option_identity_resolver.py`
- Test: `tests/test_hearthstonejson.py`
- Test: `tests/test_semantic_enrichment.py`
- Test: `tests/test_identity_graph.py`

**Interfaces:**
- Produces: `normalize_card_row(row: dict[str, Any]) -> dict[str, Any]` preserving `hero_power_dbf_id`, `quest_reward`, `play_requirements`, and `entourage`.
- Produces: `resolve_linked_entities(cards: list[dict[str, Any]], card_index: dict[str, dict[str, Any]]) -> dict[str, list[dict[str, Any]]]`

- [ ] **Step 1: Add failing HearthstoneJSON field-preservation tests**

Add to `tests/test_hearthstonejson.py`:

```python
def test_normalize_card_row_preserves_identity_link_fields():
    row = normalize_card_row(
        {
            "id": "HERO_09",
            "dbfId": 637,
            "name": "Anduin",
            "type": "HERO",
            "heroPowerDbfId": 479,
            "questReward": "QUEST_REWARD_CARD",
            "playRequirements": {"REQ_TARGET_TO_PLAY": 0},
            "entourage": ["TOKEN_001"],
        }
    )

    assert row["hero_power_dbf_id"] == 479
    assert row["quest_reward"] == "QUEST_REWARD_CARD"
    assert row["play_requirements"] == {"REQ_TARGET_TO_PLAY": 0}
    assert row["entourage"] == ["TOKEN_001"]
```

- [ ] **Step 2: Run the failing test**

```powershell
python -m pytest tests/test_hearthstonejson.py::test_normalize_card_row_preserves_identity_link_fields -q
```

Expected before implementation:

```text
FAILED ... KeyError: 'hero_power_dbf_id'
```

- [ ] **Step 3: Extend `normalize_card_row`**

Add these fields to the returned dict in `src/hsconfig/hearthstonejson.py`:

```python
"hero_power_dbf_id": int(row["heroPowerDbfId"]) if row.get("heroPowerDbfId") is not None else None,
"quest_reward": row.get("questReward", row.get("quest_reward")),
"play_requirements": dict(row.get("playRequirements", row.get("play_requirements", {})) or {}),
```

- [ ] **Step 4: Create `option_identity_resolver.py`**

Create `src/hsconfig/option_identity_resolver.py`:

```python
from __future__ import annotations

from typing import Any


def resolve_linked_entities(
    cards: list[dict[str, Any]],
    card_index: dict[str, dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    links: dict[str, list[dict[str, Any]]] = {}
    for card in cards:
        card_id = str(card.get("id") or card.get("card_id") or "")
        rows: list[dict[str, Any]] = []
        hero_power_dbf_id = card.get("hero_power_dbf_id")
        if hero_power_dbf_id is not None and str(hero_power_dbf_id) in card_index:
            target = card_index[str(hero_power_dbf_id)]
            rows.append(_link("starting_hero_power", target, "hearthstonejson.heroPowerDbfId"))
        quest_reward = card.get("quest_reward")
        if quest_reward and str(quest_reward) in card_index:
            rows.append(_link("quest_reward", card_index[str(quest_reward)], "hearthstonejson.questReward"))
        for entourage_id in card.get("entourage", []) or []:
            if str(entourage_id) in card_index:
                rows.append(_link("entourage", card_index[str(entourage_id)], "hearthstonejson.entourage"))
        if card_id and rows:
            links[card_id] = rows
    return links


def _link(kind: str, target: dict[str, Any], source: str) -> dict[str, Any]:
    return {
        "link_kind": kind,
        "card_id": str(target.get("id") or target.get("card_id")),
        "dbf_id": target.get("dbf_id"),
        "name": str(target.get("name", target.get("id", ""))),
        "type": str(target.get("type", "UNKNOWN")),
        "source": source,
    }
```

- [ ] **Step 5: Add tests for linked entity resolution**

Add to `tests/test_semantic_enrichment.py` or a new `tests/test_option_identity_resolver.py`:

```python
from hsconfig.option_identity_resolver import resolve_linked_entities


def test_resolve_linked_entities_from_hero_power_dbf_id():
    cards = [{"id": "HERO_09", "hero_power_dbf_id": 479}]
    index = {
        "479": {"id": "CS1h_001", "dbf_id": 479, "name": "Lesser Heal", "type": "HERO_POWER"}
    }

    links = resolve_linked_entities(cards, index)

    assert links["HERO_09"][0]["link_kind"] == "starting_hero_power"
    assert links["HERO_09"][0]["card_id"] == "CS1h_001"
```

- [ ] **Step 6: Wire linked entities into semantic enrichment**

In `semantic_enrichment.py`, after HearthstoneJSON merge and before writing `linked_entities`, call the resolver for enriched cards and merge link rows by card id. Preserve existing Mind Spike derived fallback as `source="builtin_shadowform_fallback"` when HearthstoneJSON lacks a direct link.

- [ ] **Step 7: Run targeted tests**

```powershell
python -m pytest tests/test_hearthstonejson.py tests/test_semantic_enrichment.py tests/test_identity_graph.py -q
```

Expected:

```text
passed
```

- [ ] **Step 8: Commit**

```powershell
git add src/hsconfig/hearthstonejson.py src/hsconfig/semantic_enrichment.py src/hsconfig/identity_graph.py src/hsconfig/option_identity_resolver.py tests/test_hearthstonejson.py tests/test_semantic_enrichment.py tests/test_identity_graph.py
git commit -m "feat: preserve static identity links"
```

---

### Task 3: Add Source Document Model And Atomic Claim Builder

**Files:**
- Create: `src/hsconfig/source_document_model.py`
- Create: `src/hsconfig/source_document_builder.py`
- Modify: `src/hsconfig/guide_source_builder.py`
- Modify: `src/hsconfig/guide_claim_builder.py`
- Test: `tests/test_source_document_builder.py`
- Test: `tests/test_guide_claim_builder.py`

**Interfaces:**
- Produces: `build_source_document_bundle(deck_identity: dict[str, Any], card_metadata: dict[str, Any], source_documents: list[dict[str, Any]]) -> dict[str, Any]`
- Produces keys: `claims`, `source_evidence_index`, `claim_coverage_report`, `claim_conflict_report`, `unsupported_claims`.

- [ ] **Step 1: Write failing tests for atomic source claims**

Create `tests/test_source_document_builder.py`:

```python
from hsconfig.source_document_builder import build_source_document_bundle


def test_source_document_builder_atomizes_claims_and_tracks_coverage():
    deck_identity = {
        "deck_name": "Fixture",
        "cards": [
            {"card_id": "CARD_A", "count": 2, "name": "Card A"},
            {"card_id": "CARD_B", "count": 2, "name": "Card B"},
        ],
    }
    card_metadata = {"cards": deck_identity["cards"]}
    source_documents = [
        {
            "source_url": "https://example.invalid/guide",
            "source_title": "Fixture Guide",
            "source_family": "guide",
            "retrieved_at": "2026-07-07T00:00:00Z",
            "claims": [
                {
                    "claim_kind": "mulligan_keep",
                    "cards": ["CARD_A"],
                    "stance": "keep",
                    "evidence_text_short": "Keep Card A as opener.",
                    "source_confidence": "high",
                }
            ],
        }
    ]

    bundle = build_source_document_bundle(
        deck_identity=deck_identity,
        card_metadata=card_metadata,
        source_documents=source_documents,
    )

    assert bundle["claims"][0]["claim_kind"] == "mulligan_keep"
    assert bundle["claims"][0]["support_status"] == "source_backed"
    assert bundle["claim_coverage_report"]["cards"]["CARD_A"]["coverage_status"] == "guide_backed"
    assert bundle["claim_coverage_report"]["cards"]["CARD_B"]["coverage_status"] in {
        "static_semantics_backfilled",
        "uncovered_low_confidence",
    }
    assert bundle["source_evidence_index"][0]["source_url"] == "https://example.invalid/guide"
```

- [ ] **Step 2: Run the failing test**

```powershell
python -m pytest tests/test_source_document_builder.py -q
```

Expected before implementation:

```text
FAILED ... ModuleNotFoundError: No module named 'hsconfig.source_document_builder'
```

- [ ] **Step 3: Create `source_document_model.py`**

Create explicit supported claim constants:

```python
from __future__ import annotations

SUPPORTED_ATOMIC_CLAIM_KINDS = frozenset(
    {
        "archetype",
        "mulligan_keep",
        "mulligan_discard",
        "card_role",
        "targeting_rule",
        "combo_sequence",
        "gameplan_posture",
        "hero_power_transform",
        "mechanic_usage",
        "known_bad_pattern",
        "tech_slot",
        "replacement_option",
    }
)

REQUIRED_SOURCE_KEYS = ("source_url", "source_title", "source_family", "retrieved_at")
REQUIRED_CLAIM_KEYS = ("claim_kind", "evidence_text_short", "source_confidence")
```

- [ ] **Step 4: Create `source_document_builder.py`**

Implement `build_source_document_bundle(...)` with:

```python
def build_source_document_bundle(
    *,
    deck_identity: dict[str, Any],
    card_metadata: dict[str, Any],
    source_documents: list[dict[str, Any]],
) -> dict[str, Any]:
    ...
```

Behavior:

- validate each source has `source_url`, `source_title`, `source_family`, `retrieved_at`
- validate each claim has `claim_kind`, `evidence_text_short`, `source_confidence`
- reject unsupported claim kinds into `unsupported_claims`
- reject card-scoped claims where any card is not in deck
- generate stable `claim_id`
- mark accepted claims as `support_status="source_backed"`
- build `source_evidence_index`
- build per-card coverage where unmentioned cards are `uncovered_low_confidence`
- return empty `claim_conflict_report` with `conflict_count=0` until Task 4 adds conflicts

- [ ] **Step 5: Integrate into `guide_claim_builder.py`**

In `build_guide_claim_bundle(...)`, call `build_source_document_bundle(...)` before existing claim normalization when `source_documents` is non-empty. Preserve the existing static semantic backfill by appending static claims after source-backed claims.

- [ ] **Step 6: Run targeted tests**

```powershell
python -m pytest tests/test_source_document_builder.py tests/test_guide_claim_builder.py tests/test_research_contract.py -q
```

Expected:

```text
passed
```

- [ ] **Step 7: Commit**

```powershell
git add src/hsconfig/source_document_model.py src/hsconfig/source_document_builder.py src/hsconfig/guide_source_builder.py src/hsconfig/guide_claim_builder.py tests/test_source_document_builder.py tests/test_guide_claim_builder.py
git commit -m "feat: build atomic source-backed guide claims"
```

---

### Task 4: Add Freshness, Conflict, And Coverage Gates

**Files:**
- Modify: `src/hsconfig/source_document_builder.py`
- Modify: `src/hsconfig/guide_source_depth.py`
- Modify: `src/hsconfig/operator_summary.py`
- Modify: `src/hsconfig/cli.py`
- Test: `tests/test_source_document_builder.py`
- Test: `tests/test_operator_summary.py`
- Test: `tests/test_prepare_cli.py`

**Interfaces:**
- Consumes: `source_documents[*].retrieved_at`
- Produces: `claim_conflict_report.json`, `claim_coverage_report.json`, and stronger `operator_summary.warnings`.

- [ ] **Step 1: Add failing freshness and conflict tests**

Append to `tests/test_source_document_builder.py`:

```python
def test_source_document_builder_downgrades_stale_sources():
    deck_identity = {"deck_name": "Fixture", "cards": [{"card_id": "CARD_A", "count": 2}]}
    bundle = build_source_document_bundle(
        deck_identity=deck_identity,
        card_metadata={"cards": deck_identity["cards"]},
        source_documents=[
            {
                "source_url": "https://example.invalid/old",
                "source_title": "Old Guide",
                "source_family": "guide",
                "retrieved_at": "2024-01-01T00:00:00Z",
                "claims": [
                    {
                        "claim_kind": "mulligan_keep",
                        "cards": ["CARD_A"],
                        "stance": "keep",
                        "evidence_text_short": "Old guide keep.",
                        "source_confidence": "high",
                    }
                ],
            }
        ],
    )

    assert bundle["claims"][0]["freshness_status"] == "stale"
    assert bundle["claims"][0]["claim_confidence"] == "medium"
```

Append:

```python
def test_source_document_builder_reports_conflicting_mulligan_claims():
    deck_identity = {"deck_name": "Fixture", "cards": [{"card_id": "CARD_A", "count": 2}]}
    docs = [
        {
            "source_url": "https://example.invalid/a",
            "source_title": "Guide A",
            "source_family": "guide",
            "retrieved_at": "2026-07-07T00:00:00Z",
            "claims": [
                {
                    "claim_kind": "mulligan_keep",
                    "cards": ["CARD_A"],
                    "stance": "keep",
                    "evidence_text_short": "Keep Card A.",
                    "source_confidence": "high",
                }
            ],
        },
        {
            "source_url": "https://example.invalid/b",
            "source_title": "Guide B",
            "source_family": "guide",
            "retrieved_at": "2026-07-07T00:00:00Z",
            "claims": [
                {
                    "claim_kind": "mulligan_discard",
                    "cards": ["CARD_A"],
                    "stance": "discard",
                    "evidence_text_short": "Throw Card A.",
                    "source_confidence": "high",
                }
            ],
        },
    ]

    bundle = build_source_document_bundle(
        deck_identity=deck_identity,
        card_metadata={"cards": deck_identity["cards"]},
        source_documents=docs,
    )

    assert bundle["claim_conflict_report"]["conflict_count"] == 1
    assert bundle["claim_conflict_report"]["conflicts"][0]["card_id"] == "CARD_A"
```

- [ ] **Step 2: Run failing tests**

```powershell
python -m pytest tests/test_source_document_builder.py -q
```

Expected:

```text
FAILED
```

- [ ] **Step 3: Implement freshness classification**

In `source_document_builder.py`, add:

```python
def classify_freshness(retrieved_at: str, *, current_date: str = "2026-07-07") -> str:
    if not retrieved_at:
        return "unknown"
    retrieved = datetime.fromisoformat(retrieved_at.replace("Z", "+00:00")).date()
    current = date.fromisoformat(current_date)
    return "stale" if (current - retrieved).days > 365 else "current"
```

Set:

```python
claim["freshness_status"] = freshness_status
claim["claim_confidence"] = "medium" if freshness_status == "stale" and source_confidence == "high" else source_confidence
```

- [ ] **Step 4: Implement conflict report**

Conflict key:

```python
(card_id, "mulligan")
```

Conflict condition:

```python
{"mulligan_keep", "mulligan_discard"} <= kinds_for_card
```

Report shape:

```python
{
    "conflict_count": len(conflicts),
    "conflicts": [
        {
            "card_id": card_id,
            "conflict_family": "mulligan",
            "claim_ids": sorted(claim_ids),
            "resolution": "downgrade_to_report_visible_conflict",
        }
    ],
}
```

- [ ] **Step 5: Wire report files in `cli.py`**

When building reports, write:

```python
write_json(reports_dir / "claim_conflict_report.json", guide_claim_bundle.get("claim_conflict_report", {"conflict_count": 0, "conflicts": []}))
```

- [ ] **Step 6: Add operator warnings**

In `operator_summary.py`, add warnings:

```python
{"reason": "claim_conflicts_present", "conflict_count": conflict_count}
{"reason": "cards_still_low_confidence", "card_count": count}
```

Pass these from `cli.py` by extending `build_operator_summary(...)` with optional `claim_conflict_report` and `claim_coverage_report`.

- [ ] **Step 7: Run targeted tests**

```powershell
python -m pytest tests/test_source_document_builder.py tests/test_operator_summary.py tests/test_prepare_cli.py -q
```

Expected:

```text
passed
```

- [ ] **Step 8: Commit**

```powershell
git add src/hsconfig/source_document_builder.py src/hsconfig/guide_source_depth.py src/hsconfig/operator_summary.py src/hsconfig/cli.py tests/test_source_document_builder.py tests/test_operator_summary.py tests/test_prepare_cli.py
git commit -m "feat: report guide claim freshness and conflicts"
```

---

### Task 5: Strengthen Operator Status And Semantic Gates

**Files:**
- Modify: `src/hsconfig/operator_summary.py`
- Modify: `src/hsconfig/guide_source_depth.py`
- Modify: `src/hsconfig/config_readiness.py`
- Modify: `README.md`
- Modify: `.agents/skills/hsconfig/SKILL.md`
- Test: `tests/test_operator_summary.py`
- Test: `tests/test_guide_source_depth.py`
- Test: `tests/test_skill_files.py`

**Interfaces:**
- Produces operator statuses:
  - `SOURCE_BACKED_STRONG`
  - `STATIC_SEMANTICS_USABLE`
  - `VALID_BUT_NOT_GUIDE_STRONG`
  - `NEEDS_MORE_RESEARCH`
  - `INVALID_PACKAGE`

- [ ] **Step 1: Add failing status tests**

Add to `tests/test_operator_summary.py`:

```python
def test_operator_summary_marks_valid_package_not_guide_strong_when_many_cards_need_claims():
    summary = build_operator_summary(
        deck_name="Fixture",
        deck_code="AAE=",
        technical_validation={"status": "passed", "errors": []},
        guide_source_depth={"source_depth_status": "static_semantics_only", "claim_count": 3},
        unsupported_conditions=[],
        globalvalue_authority={"blocked_until_runtime_evidence": []},
        generated_files=["CustomConfig/fixture/GlobalValues.json"],
        claim_coverage_report={
            "total_cards": 10,
            "guide_backed_cards": 1,
            "uncovered_cards": ["A", "B", "C"],
        },
        config_readiness_summary={"generic_low_confidence": 3},
    )

    assert summary["technical_status"] == "VALID_PACKAGE"
    assert summary["semantic_status"] == "VALID_BUT_NOT_GUIDE_STRONG"
    assert summary["next_action"] == "IMPROVE_GUIDE_SOURCES_BEFORE_STRONG_APPLY"
```

- [ ] **Step 2: Run failing test**

```powershell
python -m pytest tests/test_operator_summary.py::test_operator_summary_marks_valid_package_not_guide_strong_when_many_cards_need_claims -q
```

Expected:

```text
FAILED ... unexpected semantic_status
```

- [ ] **Step 3: Extend `build_operator_summary` signature**

Update function signature:

```python
def build_operator_summary(
    *,
    deck_name: str,
    deck_code: str,
    technical_validation: dict[str, Any],
    guide_source_depth: dict[str, Any] | None,
    unsupported_conditions: list[dict[str, Any]] | None,
    globalvalue_authority: dict[str, Any] | None,
    generated_files: list[str],
    claim_coverage_report: dict[str, Any] | None = None,
    config_readiness_summary: dict[str, Any] | None = None,
    claim_conflict_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
```

- [ ] **Step 4: Implement semantic status derivation**

Rules:

```python
if technical_status == "INVALID_PACKAGE":
    semantic_status = "INVALID_PACKAGE"
elif source_depth_status == "source_backed" and claim_count > 0 and generic_low_confidence == 0 and conflict_count == 0:
    semantic_status = "SOURCE_BACKED_STRONG"
elif generic_low_confidence > 0 or uncovered_cards:
    semantic_status = "VALID_BUT_NOT_GUIDE_STRONG"
elif source_depth_status == "static_semantics_only":
    semantic_status = "STATIC_SEMANTICS_USABLE"
else:
    semantic_status = "NEEDS_MORE_RESEARCH"
```

Next action:

```python
SOURCE_BACKED_STRONG -> READY_TO_APPLY_OR_HANDOFF
STATIC_SEMANTICS_USABLE -> READY_WITH_WARNINGS
VALID_BUT_NOT_GUIDE_STRONG -> IMPROVE_GUIDE_SOURCES_BEFORE_STRONG_APPLY
NEEDS_MORE_RESEARCH -> RESEARCH_REQUIRED_BEFORE_STRONG_CONFIG
INVALID_PACKAGE -> FIX_PACKAGE_BEFORE_APPLY
```

- [ ] **Step 5: Wire new inputs from `cli.py`**

Pass:

```python
claim_coverage_report=guide_claim_bundle["coverage"]
config_readiness_summary=config_readiness_report["summary"]
claim_conflict_report=guide_claim_bundle.get("claim_conflict_report")
```

- [ ] **Step 6: Update docs**

Update `README.md` and `.agents/skills/hsconfig/SKILL.md` to state:

```text
VALID_PACKAGE means the JSON package loads structurally.
SOURCE_BACKED_STRONG means HSConfig has enough current guide-backed coverage for strong initial config.
STATIC_SEMANTICS_USABLE means the package is safe but not guide-depth.
VALID_BUT_NOT_GUIDE_STRONG means Codex should improve source documents before calling the package optimized.
```

- [ ] **Step 7: Run targeted tests**

```powershell
python -m pytest tests/test_operator_summary.py tests/test_prepare_cli.py tests/test_skill_files.py -q
```

Expected:

```text
passed
```

- [ ] **Step 8: Commit**

```powershell
git add src/hsconfig/operator_summary.py src/hsconfig/guide_source_depth.py src/hsconfig/config_readiness.py src/hsconfig/cli.py README.md .agents/skills/hsconfig/SKILL.md tests/test_operator_summary.py tests/test_guide_source_depth.py tests/test_skill_files.py
git commit -m "feat: distinguish valid packages from guide-strong configs"
```

---

### Task 6: Add Mulligan Selector Depth

**Files:**
- Create: `src/hsconfig/mulligan_selector.py`
- Modify: `src/hsconfig/mulligan_plan.py`
- Modify: `src/hsconfig/compile_mulligan.py`
- Modify: `src/hsconfig/validate_package.py`
- Test: `tests/test_mulligan_plan.py`
- Test: `tests/test_compile_mulligan.py`
- Test: `tests/test_validate_package.py`

**Interfaces:**
- Produces: `normalize_mulligan_selector(rule: dict[str, Any]) -> dict[str, Any]`
- Supports selector kinds: `card`, `card_list`, `drop_n`, `plus_combo`, `wildcard`.

- [ ] **Step 1: Add failing selector tests**

Add to `tests/test_compile_mulligan.py`:

```python
def test_compile_mulligan_emits_drop_and_plus_selectors_in_plan_order():
    config = compile_mulligan(
        {
            "deck_name": "Fixture",
            "mulligan_plan": {
                "rules": [
                    {
                        "rule_id": "keep_drop1",
                        "selector_kind": "drop_n",
                        "selector": "DROP1",
                        "action": "hold",
                        "condition": "*",
                    },
                    {
                        "rule_id": "keep_combo",
                        "selector_kind": "plus_combo",
                        "selector": "CARD_A + CARD_B",
                        "action": "hold",
                        "condition": "coin",
                    },
                    {
                        "rule_id": "throw_card_c",
                        "selector_kind": "card",
                        "selector": "CARD_C",
                        "action": "discard",
                        "condition": "*",
                    },
                ]
            },
        }
    )

    rows = config["Mulligan"]["values"]
    assert [row["mulligan"] for row in rows] == ["DROP1", "CARD_A + CARD_B", "CARD_C"]
    assert rows[1]["condition"] == "coin"
    assert rows[2]["value"] == "discard"
```

Add:

```python
def test_compile_mulligan_blocks_lone_wildcard_discard():
    config = compile_mulligan(
        {
            "deck_name": "Fixture",
            "mulligan_plan": {
                "rules": [
                    {
                        "rule_id": "discard_all",
                        "selector_kind": "wildcard",
                        "selector": "*",
                        "action": "discard",
                        "condition": "*",
                    }
                ]
            },
        }
    )

    assert config["Mulligan"]["values"] == []
```

- [ ] **Step 2: Run failing tests**

```powershell
python -m pytest tests/test_compile_mulligan.py::test_compile_mulligan_emits_drop_and_plus_selectors_in_plan_order tests/test_compile_mulligan.py::test_compile_mulligan_blocks_lone_wildcard_discard -q
```

Expected:

```text
FAILED
```

- [ ] **Step 3: Implement `mulligan_selector.py`**

Create:

```python
from __future__ import annotations

import re
from typing import Any


DROP_RE = re.compile(r"^DROP\\d+$")
CARD_RE = re.compile(r"^[A-Za-z0-9_]+$")


def normalize_mulligan_selector(rule: dict[str, Any]) -> dict[str, Any]:
    selector = str(rule.get("selector", rule.get("card", ""))).strip()
    selector_kind = str(rule.get("selector_kind", "")).strip()
    if selector == "*":
        selector_kind = selector_kind or "wildcard"
    elif DROP_RE.fullmatch(selector):
        selector_kind = selector_kind or "drop_n"
    elif "+" in selector:
        selector_kind = selector_kind or "plus_combo"
    elif "," in selector:
        selector_kind = selector_kind or "card_list"
    elif CARD_RE.fullmatch(selector):
        selector_kind = selector_kind or "card"
    else:
        return {"supported": False, "reason": "unsupported_mulligan_selector", "selector": selector}
    return {"supported": True, "selector_kind": selector_kind, "selector": selector}
```

- [ ] **Step 4: Update `mulligan_plan.py`**

When processing claims, build rows with:

```python
"selector_kind": claim.get("selector_kind", "card"),
"selector": claim.get("selector", card_id),
"action": action,
"condition": condition,
```

Rules:

- explicit source claim selectors are preserved
- card-only claims still emit `selector=card_id`
- wildcard discard is appended only if there is at least one non-wildcard hold
- unsupported selectors go to `suppressed_rules`

- [ ] **Step 5: Update `compile_mulligan.py`**

In `_anchors_from_plan`, use:

```python
selector_info = normalize_mulligan_selector(rule)
if not selector_info["supported"]:
    continue
if selector_info["selector_kind"] == "wildcard" and str(rule.get("action", rule.get("intent"))) == "discard":
    if not has_previous_non_wildcard_hold:
        continue
```

Emit:

```python
"mulligan": selector_info["selector"]
```

instead of always `card_id`.

- [ ] **Step 6: Add validation**

In `validate_package.py`, reject:

```text
Mulligan wildcard discard appears before any non-wildcard hold
```

and reject selectors not matching card, comma list, `DROPn`, plus-combo, or wildcard.

- [ ] **Step 7: Run targeted tests**

```powershell
python -m pytest tests/test_mulligan_plan.py tests/test_compile_mulligan.py tests/test_validate_package.py -q
```

Expected:

```text
passed
```

- [ ] **Step 8: Commit**

```powershell
git add src/hsconfig/mulligan_selector.py src/hsconfig/mulligan_plan.py src/hsconfig/compile_mulligan.py src/hsconfig/validate_package.py tests/test_mulligan_plan.py tests/test_compile_mulligan.py tests/test_validate_package.py
git commit -m "feat: support documented mulligan selectors"
```

---

### Task 7: Add Claim-Level CardID Behavior Routing

**Files:**
- Create: `src/hsconfig/card_behavior_surface_router.py`
- Create: `src/hsconfig/option_identity_resolver.py` if Task 2 did not create it
- Modify: `src/hsconfig/card_behavior_router.py`
- Modify: `src/hsconfig/compile_cardid.py`
- Modify: `src/hsconfig/cli.py`
- Test: `tests/test_card_behavior_router.py`
- Test: `tests/test_compile_cardid.py`
- Test: `tests/test_prepare_cli.py`

**Interfaces:**
- Produces: `route_card_behavior_surfaces(claims: list[dict[str, Any]], identity_links: dict[str, Any] | None = None) -> dict[str, Any]`
- Output keys: `rows`, `suppressed`, `option_resolution`.

- [ ] **Step 1: Add failing CardID routing tests**

Add to `tests/test_card_behavior_router.py`:

```python
def test_card_behavior_router_routes_specific_runtime_blocks():
    claims = [
        {
            "claim_id": "claim_target",
            "claim_kind": "targeting_rule",
            "cards": ["CARD_A"],
            "stance": "prefer_enemy_hero",
            "runtime_block": "BeforePlayCardBonus",
            "condition": {"runtime_condition": "my_target(count(),hero=true) > 0"},
            "runtime_value": "12",
        },
        {
            "claim_id": "claim_discover",
            "claim_kind": "mechanic_usage",
            "cards": ["CARD_B"],
            "mechanic": "discover",
            "runtime_block": "OnDiscoverCardBonus",
            "condition": {"runtime_condition": "my_discover(count(),cardid=CARD_C) > 0"},
            "runtime_value": "10",
        },
    ]

    plan = route_card_behavior_claims(claims)

    assert plan["rows"][0]["behavior_block"] == "BeforePlayCardBonus"
    assert plan["rows"][0]["condition"] == "my_target(count(),hero=true) > 0"
    assert plan["rows"][1]["behavior_block"] == "OnDiscoverCardBonus"
    assert plan["rows"][1]["condition"] == "my_discover(count(),cardid=CARD_C) > 0"
```

- [ ] **Step 2: Run failing or regression test**

```powershell
python -m pytest tests/test_card_behavior_router.py::test_card_behavior_router_routes_specific_runtime_blocks -q
```

Expected before implementation:

```text
FAILED
```

- [ ] **Step 3: Create or extend claim-level router**

Ensure routing supports:

```python
INTENT_BLOCKS = {
    "in_hand_value": "InHandBonus",
    "on_board_value": "OnBoardBonus",
    "play_timing": "BeforePlayCardBonus",
    "targeting_rule": "BeforeBattlecryTargetBonus",
    "hero_power_use": "BeforeUseHeroPowerBonus",
    "attack_posture": "BeforePhysicalAttackBonus",
    "discover_choice": "OnDiscoverCardBonus",
    "choose_one_choice": "OnChooseOneCardBonus",
}
```

Explicit `runtime_block` wins only when it is in `CARD_BEHAVIOR_BLOCKS`.

- [ ] **Step 4: Add suppression shape**

Suppressed row shape:

```python
{
    "claim_id": claim_id,
    "claim_kind": claim_kind,
    "cards": cards,
    "reason": "unsupported_card_behavior_block" | "unsupported_condition" | "unresolved_option_identity",
}
```

- [ ] **Step 5: Update `compile_cardid.py`**

Ensure `compile_cardid_behaviors(..., rows=...)` preserves row order for `behavior_rows` and does not collapse rows by sorted role order when explicit behavior rows exist.

- [ ] **Step 6: Wire `card_behavior_suppression_report.json`**

In `cli.py`, write:

```python
write_json(reports_dir / "card_behavior_suppression_report.json", card_behavior_plan.get("suppressed", []))
```

- [ ] **Step 7: Run targeted tests**

```powershell
python -m pytest tests/test_card_behavior_router.py tests/test_compile_cardid.py tests/test_prepare_cli.py -q
```

Expected:

```text
passed
```

- [ ] **Step 8: Commit**

```powershell
git add src/hsconfig/card_behavior_surface_router.py src/hsconfig/card_behavior_router.py src/hsconfig/compile_cardid.py src/hsconfig/cli.py tests/test_card_behavior_router.py tests/test_compile_cardid.py tests/test_prepare_cli.py
git commit -m "feat: route guide claims to CardID behavior blocks"
```

---

### Task 8: Add Combo Timing Contract

**Files:**
- Create: `src/hsconfig/combo_sequence_contract.py`
- Modify: `src/hsconfig/combo_plan.py`
- Modify: `src/hsconfig/compile_combo.py`
- Modify: `src/hsconfig/validate_package.py`
- Modify: `src/hsconfig/cli.py`
- Test: `tests/test_combo_plan.py`
- Test: `tests/test_compile_combo.py`
- Test: `tests/test_validate_package.py`

**Interfaces:**
- Produces: `build_combo_sequence_contract(claim: dict[str, Any], deck_cards: set[str]) -> dict[str, Any]`
- Supports operators: `>>`, `>->`.

- [ ] **Step 1: Add failing combo timing tests**

Add to `tests/test_combo_plan.py`:

```python
def test_combo_plan_suppresses_vague_combo_without_timing():
    plan = build_combo_plan(
        deck_cards={"CARD_A", "CARD_B"},
        claims=[
            {
                "claim_id": "claim_vague",
                "claim_kind": "combo_sequence",
                "cards": ["CARD_A", "CARD_B"],
                "evidence_text_short": "These cards work well together.",
            }
        ],
    )

    assert plan["combos"] == []
    assert plan["suppressed"][0]["reason"] == "missing_timing"
```

Add:

```python
def test_combo_plan_emits_cross_turn_operator_when_source_backed():
    plan = build_combo_plan(
        deck_cards={"CARD_A", "CARD_B"},
        claims=[
            {
                "claim_id": "claim_cross_turn",
                "claim_kind": "combo_sequence",
                "cards": ["CARD_A", "CARD_B"],
                "sequence": ["CARD_A", "CARD_B"],
                "timing_kind": "cross_turn",
                "operator": ">->",
                "values": ["20", "30"],
            }
        ],
    )

    assert plan["combos"][0]["operator"] == ">->"
    assert plan["combos"][0]["cards"] == ["CARD_A", "CARD_B"]
```

- [ ] **Step 2: Run failing tests**

```powershell
python -m pytest tests/test_combo_plan.py::test_combo_plan_suppresses_vague_combo_without_timing tests/test_combo_plan.py::test_combo_plan_emits_cross_turn_operator_when_source_backed -q
```

Expected:

```text
FAILED
```

- [ ] **Step 3: Create `combo_sequence_contract.py`**

Implement:

```python
SUPPORTED_TIMING_TO_OPERATOR = {"same_turn": ">>", "cross_turn": ">->"}


def build_combo_sequence_contract(claim: dict[str, Any], deck_cards: set[str]) -> dict[str, Any]:
    sequence = [str(card) for card in claim.get("sequence", claim.get("cards", []))]
    timing_kind = str(claim.get("timing_kind", "")).strip()
    if len(sequence) < 2:
        return {"emittable": False, "reason": "sequence_too_short", "cards": sequence}
    missing = [card for card in sequence if card not in deck_cards]
    if missing:
        return {"emittable": False, "reason": "card_not_in_deck", "cards": sequence, "missing_cards": missing}
    if timing_kind not in SUPPORTED_TIMING_TO_OPERATOR:
        return {"emittable": False, "reason": "missing_timing", "cards": sequence}
    operator = str(claim.get("operator", SUPPORTED_TIMING_TO_OPERATOR[timing_kind]))
    if operator != SUPPORTED_TIMING_TO_OPERATOR[timing_kind]:
        return {"emittable": False, "reason": "operator_timing_mismatch", "cards": sequence}
    values = [str(value) for value in claim.get("values", [])]
    if len(values) != len(sequence):
        return {"emittable": False, "reason": "value_segment_mismatch", "cards": sequence}
    return {
        "emittable": True,
        "rule_id": f"{claim['claim_id']}_combo",
        "cards": sequence,
        "timing_kind": timing_kind,
        "operator": operator,
        "values": values,
        "condition": claim.get("condition", "*"),
        "source_claim_ids": [claim["claim_id"]],
        "confidence": claim.get("confidence", "source_backed"),
    }
```

- [ ] **Step 4: Update `combo_plan.py`**

Only emit rows where `build_combo_sequence_contract(...).get("emittable") is True`. Otherwise append to `suppressed`.

- [ ] **Step 5: Ensure `compile_combo.py` emits official row keys only**

Runtime row keys must be exactly:

```python
{"comment", "condition", "combo", "value"}
```

No provenance keys inside runtime JSON.

- [ ] **Step 6: Wire report**

In `cli.py`, write:

```python
write_json(reports_dir / "combo_suppression_report.json", combo_plan.get("suppressed", []))
```

- [ ] **Step 7: Run targeted tests**

```powershell
python -m pytest tests/test_combo_plan.py tests/test_compile_combo.py tests/test_validate_package.py -q
```

Expected:

```text
passed
```

- [ ] **Step 8: Commit**

```powershell
git add src/hsconfig/combo_sequence_contract.py src/hsconfig/combo_plan.py src/hsconfig/compile_combo.py src/hsconfig/validate_package.py src/hsconfig/cli.py tests/test_combo_plan.py tests/test_compile_combo.py tests/test_validate_package.py
git commit -m "feat: require source-backed combo timing"
```

---

### Task 9: Add GlobalValues Per-Key Authority

**Files:**
- Create: `src/hsconfig/globalvalues_key_authority.py`
- Modify: `src/hsconfig/globalvalues_authority.py`
- Modify: `src/hsconfig/compile_globalvalues.py`
- Modify: `src/hsconfig/cli.py`
- Test: `tests/test_globalvalues_authority.py`
- Test: `tests/test_compile_globalvalues.py`
- Test: `tests/test_prepare_cli.py`

**Interfaces:**
- Produces: `authority_for_key(key: str) -> dict[str, str]`
- Categories: `copy_baseline`, `step1_posture_overlay_allowed`, `runtime_evidence_required`.

- [ ] **Step 1: Add failing per-key authority tests**

Add to `tests/test_globalvalues_authority.py`:

```python
from hsconfig.globalvalues_key_authority import authority_for_key


def test_globalvalues_key_authority_classifies_core_keys():
    assert authority_for_key("FirstTurnValueWeight")["category"] == "step1_posture_overlay_allowed"
    assert authority_for_key("SecondTurnValueWeight")["category"] == "step1_posture_overlay_allowed"
    assert authority_for_key("MyHeroPowerValue")["category"] == "step1_posture_overlay_allowed"
    assert authority_for_key("OpponentSpecificMatchupTuning")["category"] == "runtime_evidence_required"
```

- [ ] **Step 2: Run failing test**

```powershell
python -m pytest tests/test_globalvalues_authority.py::test_globalvalues_key_authority_classifies_core_keys -q
```

Expected:

```text
FAILED ... ModuleNotFoundError
```

- [ ] **Step 3: Create `globalvalues_key_authority.py`**

Create:

```python
from __future__ import annotations


STEP1_POSTURE_KEYS = {
    "FirstTurnValueWeight": "turn_weight",
    "SecondTurnValueWeight": "turn_weight",
    "MyHeroPowerValue": "hero_power",
    "GlobalMinionAttack": "board_pressure",
    "GlobalMinionIntrinsicValue": "board_pressure",
    "MyWeaponValue": "weapon_pressure",
}

RUNTIME_EVIDENCE_KEYS = {
    "LowHpBoardValuePenalty": "runtime_safety",
    "OpponentSpecificMatchupTuning": "matchup_runtime",
    "PostApplyRegressionTuning": "post_apply_validation",
}


def authority_for_key(key: str) -> dict[str, str]:
    if key in STEP1_POSTURE_KEYS:
        return {
            "key": key,
            "category": "step1_posture_overlay_allowed",
            "board_value_component": STEP1_POSTURE_KEYS[key],
        }
    if key in RUNTIME_EVIDENCE_KEYS:
        return {
            "key": key,
            "category": "runtime_evidence_required",
            "board_value_component": RUNTIME_EVIDENCE_KEYS[key],
        }
    return {"key": key, "category": "copy_baseline", "board_value_component": "baseline"}
```

- [ ] **Step 4: Use key authority in `globalvalues_authority.py`**

For every allowed overlay row, include:

```python
"key_authority": authority_for_key(key)
```

For blocked rows, include:

```python
"key_authority": authority_for_key(key)
```

- [ ] **Step 5: Improve compile profile**

In `compile_globalvalues.py`, add to profile rows:

```python
"authority_category": key_authority["category"]
"board_value_component": key_authority["board_value_component"]
```

- [ ] **Step 6: Wire `global_values_key_profile_report.json`**

In `cli.py`, write the same payload as `globalvalues_profile.json` or a refined per-key list:

```python
write_json(reports_dir / "global_values_key_profile_report.json", globalvalues["profile"])
```

- [ ] **Step 7: Run targeted tests**

```powershell
python -m pytest tests/test_globalvalues_authority.py tests/test_compile_globalvalues.py tests/test_prepare_cli.py -q
```

Expected:

```text
passed
```

- [ ] **Step 8: Commit**

```powershell
git add src/hsconfig/globalvalues_key_authority.py src/hsconfig/globalvalues_authority.py src/hsconfig/compile_globalvalues.py src/hsconfig/cli.py tests/test_globalvalues_authority.py tests/test_compile_globalvalues.py tests/test_prepare_cli.py
git commit -m "feat: classify GlobalValues key authority"
```

---

### Task 10: Prove Source-Backed ShadowPriest Depth

**Files:**
- Create: `tests/fixtures/source_documents_shadowpriest_depth.json`
- Modify: `tests/test_shadowpriest_depth_e2e.py`
- Modify: `tests/test_autonomous_guide_workflow_e2e.py`
- Test: `tests/test_shadowpriest_depth_e2e.py`

**Interfaces:**
- Consumes: `--source-documents-json tests/fixtures/source_documents_shadowpriest_depth.json`
- Produces: `operator_summary.semantic_status == "SOURCE_BACKED_STRONG"` for the fixture.

- [ ] **Step 1: Create source document fixture**

Create `tests/fixtures/source_documents_shadowpriest_depth.json` with compact source documents that include:

```json
[
  {
    "source_url": "https://example.invalid/shadowpriest-guide",
    "source_title": "ShadowPriest Fixture Guide",
    "source_family": "guide_fixture",
    "retrieved_at": "2026-07-07T00:00:00Z",
    "deck_name": "ShadowPriest",
    "archetype": "aggro_burn",
    "claims": [
      {
        "claim_kind": "gameplan_posture",
        "scope": "deck",
        "cards": [],
        "stance": "aggro_burn",
        "evidence_text_short": "ShadowPriest fixture plays proactive burn pressure.",
        "source_confidence": "high"
      },
      {
        "claim_kind": "mulligan_keep",
        "cards": ["SW_446"],
        "selector": "SW_446",
        "selector_kind": "card",
        "stance": "keep",
        "evidence_text_short": "Fixture guide keeps the pressure opener.",
        "source_confidence": "high"
      },
      {
        "claim_kind": "targeting_rule",
        "cards": ["DS1_233"],
        "stance": "prefer_enemy_hero",
        "runtime_block": "BeforePlayCardBonus",
        "condition": {"runtime_condition": "my_target(count(),hero=true) > 0"},
        "runtime_value": "12",
        "evidence_text_short": "Fixture guide points direct damage face.",
        "source_confidence": "high"
      }
    ]
  }
]
```

Add enough compact claims to cover every ShadowPriest deck card with at least `card_role` or `mechanic_usage`. Keep evidence text short and fixture-safe.

- [ ] **Step 2: Add E2E assertion**

In `tests/test_shadowpriest_depth_e2e.py`, add:

```python
def test_shadowpriest_source_documents_reach_source_backed_strong(tmp_path):
    out = tmp_path / "shadowpriest"
    source_docs = Path("tests/fixtures/source_documents_shadowpriest_depth.json")

    code = main(
        [
            "prepare",
            "--deck-name",
            "ShadowPriest",
            "--deck-code",
            SHADOWPRIEST_CODE,
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(out),
            "--source-documents-json",
            str(source_docs),
            "--json",
        ]
    )

    assert code == 0
    summary = read_json(out / "reports" / "operator_summary.json")
    assert summary["technical_status"] == "VALID_PACKAGE"
    assert summary["semantic_status"] == "SOURCE_BACKED_STRONG"
```

- [ ] **Step 3: Run failing E2E**

```powershell
python -m pytest tests/test_shadowpriest_depth_e2e.py::test_shadowpriest_source_documents_reach_source_backed_strong -q
```

Expected before previous tasks are complete:

```text
FAILED
```

- [ ] **Step 4: Adjust fixture coverage and readiness logic**

If the E2E fails because cards remain `generic_low_confidence`, add a `card_role` claim for the specific missing card. Do not weaken `operator_summary` gates to force a pass.

- [ ] **Step 5: Run targeted E2E**

```powershell
python -m pytest tests/test_shadowpriest_depth_e2e.py tests/test_autonomous_guide_workflow_e2e.py -q
```

Expected:

```text
passed
```

- [ ] **Step 6: Commit**

```powershell
git add tests/fixtures/source_documents_shadowpriest_depth.json tests/test_shadowpriest_depth_e2e.py tests/test_autonomous_guide_workflow_e2e.py
git commit -m "test: prove source-backed ShadowPriest depth"
```

---

### Task 11: Add Multi-Deck Source-Backed Proof

**Files:**
- Create: `tests/fixtures/source_documents_multiarchetype.json`
- Create: `tests/test_multideck_source_backed_e2e.py`
- Test: `tests/test_multideck_source_backed_e2e.py`

**Interfaces:**
- Consumes representative deck codes for ShadowPriest, MechPala, BigShaman, Kingslayer, TreantDruid, Discolock, and Boarlock.
- Produces at least `VALID_PACKAGE` for all representative decks and `SOURCE_BACKED_STRONG` for fixture-backed archetypes.

- [ ] **Step 1: Create compact multi-archetype fixture**

Create `tests/fixtures/source_documents_multiarchetype.json` as an object keyed by deck name:

```json
{
  "ShadowPriest": [
    {
      "source_url": "https://example.invalid/shadowpriest",
      "source_title": "ShadowPriest Fixture",
      "source_family": "guide_fixture",
      "retrieved_at": "2026-07-07T00:00:00Z",
      "deck_name": "ShadowPriest",
      "archetype": "aggro_burn",
      "claims": []
    }
  ],
  "MechPala": [
    {
      "source_url": "https://example.invalid/mechpala",
      "source_title": "MechPala Fixture",
      "source_family": "guide_fixture",
      "retrieved_at": "2026-07-07T00:00:00Z",
      "deck_name": "MechPala",
      "archetype": "token_board",
      "claims": []
    }
  ]
}
```

Fill each deck with compact `gameplan_posture`, `mulligan_keep`, and `card_role` claims sufficient for fixture proof. Keep claim texts short.

- [ ] **Step 2: Add parametrized E2E test**

Create `tests/test_multideck_source_backed_e2e.py`:

```python
import json
from pathlib import Path

import pytest

from hsconfig.cli import main
from hsconfig.io import read_json, write_json


DECKS = {
    "ShadowPriest": "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=",
    "MechPala": "AAEBAZ8FAtS9BMekBg6f9QLW/gLX/gKHrgOStQThtQTa0wTZ0AW5/gWf4Qa08Qbi8Qa6lgea/AcAAQPzswbHpAb2swbHpAbu3gbHpAYAAA==",
    "BigShaman": "AAEBAaoIBpQD5LcDv84E9qMGgbgGmvYGDM4P0hP2vQKPlAPW9QO8tgT08gXqmAbGpgakpwb44gas/QYAAA==",
}


@pytest.mark.parametrize("deck_name,deck_code", DECKS.items())
def test_multideck_source_backed_prepare(tmp_path, deck_name, deck_code):
    fixture = json.loads(Path("tests/fixtures/source_documents_multiarchetype.json").read_text(encoding="utf-8"))
    source_path = tmp_path / f"{deck_name}_sources.json"
    write_json(source_path, fixture[deck_name])
    out = tmp_path / deck_name

    code = main(
        [
            "prepare",
            "--deck-name",
            deck_name,
            "--deck-code",
            deck_code,
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(out),
            "--source-documents-json",
            str(source_path),
            "--json",
        ]
    )

    assert code == 0
    summary = read_json(out / "reports" / "operator_summary.json")
    assert summary["technical_status"] == "VALID_PACKAGE"
    assert summary["semantic_status"] in {"SOURCE_BACKED_STRONG", "VALID_BUT_NOT_GUIDE_STRONG"}
```

- [ ] **Step 3: Run failing or partial E2E**

```powershell
python -m pytest tests/test_multideck_source_backed_e2e.py -q
```

Expected before fixture completion:

```text
FAILED
```

- [ ] **Step 4: Fill fixtures until representative decks pass**

Add only compact claims required by the failing report. Use each `per_card_config_readiness_report.json` to identify cards still missing guide coverage. Do not relax readiness gates.

- [ ] **Step 5: Run targeted E2E**

```powershell
python -m pytest tests/test_multideck_source_backed_e2e.py -q
```

Expected:

```text
passed
```

- [ ] **Step 6: Commit**

```powershell
git add tests/fixtures/source_documents_multiarchetype.json tests/test_multideck_source_backed_e2e.py
git commit -m "test: prove multi-deck source-backed workflow"
```

---

### Task 12: CLI, Docs, Skill Workflow, And Full Verification

**Files:**
- Modify: `README.md`
- Modify: `docs/operator/guide-research-policy.md`
- Modify: `.agents/skills/hsconfig/SKILL.md`
- Modify: `.agents/skills/hsconfig/references/workflow.md`
- Modify: `.agents/skills/hsconfig/references/guide-research-policy.md`
- Modify: `.agents/skills/hsconfig/references/card-behavior-policy.md`
- Modify: `.agents/skills/hsconfig/references/globalvalues-policy.md`
- Modify: `src/hsconfig/cli.py`
- Test: `tests/test_skill_files.py`
- Test: `tests/test_prepare_cli.py`

**Interfaces:**
- Normal operator path remains:
  - research current guides with Codex
  - write `source_documents.json`
  - run `hsconfig research-deck --source-documents-json ...`
  - run `hsconfig prepare --guide-sources-json ...`
  - inspect `operator_summary.json`
  - run `hsconfig apply ...` only when requested.

- [ ] **Step 1: Add docs tests for stale or weak wording**

In `tests/test_skill_files.py`, add scans that fail if active docs imply static semantics are fully optimized:

```python
def test_skill_docs_do_not_call_static_semantics_optimized():
    active_files = [
        Path("README.md"),
        Path(".agents/skills/hsconfig/SKILL.md"),
        Path(".agents/skills/hsconfig/references/workflow.md"),
    ]
    forbidden = [
        "static semantics are optimized",
        "valid package means optimized",
        "no guide research needed",
    ]
    for path in active_files:
        text = path.read_text(encoding="utf-8").lower()
        for phrase in forbidden:
            assert phrase not in text
```

- [ ] **Step 2: Run failing or passing docs test**

```powershell
python -m pytest tests/test_skill_files.py::test_skill_docs_do_not_call_static_semantics_optimized -q
```

Expected:

```text
passed
```

If it fails, update the docs in Step 3.

- [ ] **Step 3: Update normal workflow docs**

Update README and skill docs with this exact readiness language:

```text
HSConfig has two useful success levels.

VALID_PACKAGE means the runtime JSON package is structurally valid and load-safe.
SOURCE_BACKED_STRONG means the package has current guide-backed per-card coverage and can be treated as a strong initial config.

STATIC_SEMANTICS_USABLE and VALID_BUT_NOT_GUIDE_STRONG are safe handoff states, not optimized-config claims.
```

- [ ] **Step 4: Update guide policy docs**

Document:

- accepted source document fields
- atomic claim kinds
- claim freshness
- conflict reporting
- every-card coverage lanes
- Mulligan selector support
- CardID behavior block support
- Combo timing support
- GlobalValues key authority

- [ ] **Step 5: Ensure installed skill parity**

After repo docs are updated, copy the updated `.agents/skills/hsconfig/SKILL.md` content into:

```powershell
C:\Users\darbo\.codex\skills\hsconfig\SKILL.md
```

Use PowerShell:

```powershell
Copy-Item .agents\skills\hsconfig\SKILL.md C:\Users\darbo\.codex\skills\hsconfig\SKILL.md -Force
```

Do not git-add the installed skill path because it is outside the repo.

- [ ] **Step 6: Run full test suite**

```powershell
python -m pytest -q
```

Expected:

```text
passed
```

- [ ] **Step 7: Run multi-deck smoke command**

Run a local ignored smoke for MechPala:

```powershell
$out = "tmp\final-smoke\mechpala"
if (Test-Path $out) { Remove-Item -Recurse -Force $out }
python -m hsconfig research-deck --deck-name "MechPala" --deck-code "AAEBAZ8FAtS9BMekBg6f9QLW/gLX/gKHrgOStQThtQTa0wTZ0AW5/gWf4Qa08Qbi8Qa6lgea/AcAAQPzswbHpAb2swbHpAbu3gbHpAYAAA==" --out "$out\research" --json
python -m hsconfig prepare --deck-name "MechPala" --deck-code "AAEBAZ8FAtS9BMekBg6f9QLW/gLX/gKHrgOStQThtQTa0wTZ0AW5/gWf4Qa08Qbi8Qa6lgea/AcAAQPzswbHpAb2swbHpAbu3gbHpAYAAA==" --runtime-root "C:\Users\darbo\Desktop\HS" --out "$out\package" --guide-sources-json "$out\research\guide_sources.json" --json
```

Expected:

```text
"status": "passed"
```

- [ ] **Step 8: Check diff hygiene**

```powershell
git diff --check
git status --short --branch
```

Expected:

```text
git diff --check exits 0
status shows only intended tracked changes before commit
```

- [ ] **Step 9: Commit docs and final wiring**

```powershell
git add README.md docs/operator/guide-research-policy.md .agents/skills/hsconfig src/hsconfig/cli.py tests/test_skill_files.py tests/test_prepare_cli.py
git commit -m "docs: describe source-backed HSConfig workflow"
```

- [ ] **Step 10: Push main after final review**

If the branch is already `main` and tests passed:

```powershell
git push origin main
```

If implementation was done on a feature branch:

```powershell
git switch main
git pull --ff-only origin main
git merge --ff-only <feature-branch>
git push origin main
```

---

## Final Acceptance Checklist

- [ ] `python -m pytest -q` passes.
- [ ] `git diff --check` exits 0.
- [ ] MechPala `research-deck -> prepare` no longer fails on sideboards.
- [ ] ShadowPriest source-backed fixture reaches `SOURCE_BACKED_STRONG`.
- [ ] Static-semantics-only packages remain valid but are not labeled optimized.
- [ ] Mulligan supports documented `DROPn`, plus-combo, wildcard, concrete card, and explicit discard selectors.
- [ ] CardID routing emits specific documented blocks where claims justify them.
- [ ] Combo rows require explicit order and timing.
- [ ] GlobalValues reports per-key authority and blocked runtime-evidence-only changes.
- [ ] Active docs and skill files preserve HSConfig/HSTuner separation.
- [ ] `git status --short --branch` is clean after push.

## Self-Review

- Spec coverage: The plan covers sideboard identity, source-backed claims, semantic status gates, Mulligan depth, CardID routing, Combo timing, GlobalValues authority, ShadowPriest proof, multi-deck proof, docs, tests, and GitHub update.
- Placeholder scan: No forbidden placeholder phrases or unspecified test instructions remain.
- Type consistency: Function names and return shapes introduced in earlier tasks are reused consistently by later tasks.
- Scope check: The plan intentionally does not add replay parsing, winrate analysis, candidate promotion, or HSTuner runtime tuning.

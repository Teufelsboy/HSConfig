# HSConfig Hero-Power Semantic Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make HSConfig reliably understand hero-power-transform decks, starting with ShadowPriest / Darkbishop Benedictus / Mind Spike, and translate that semantic chain into contract, GlobalValues, audit reports, and validated runtime config.

**Architecture:** Keep HSConfig lean: deck input still flows through deckstring decode, card metadata, semantic enrichment, gameplan contract, compilers, validation, and optional runtime apply. Add a focused semantic-enrichment layer that uses HearthstoneJSON-style data when available, but does not make live network availability required for builds. Apply hero-power-transform effects through deckwide contract and `GlobalValues.MyHeroPowerValue`, not by blindly adding `BeforeUseHeroPowerBonus` to a Start-of-Game card.

**Tech Stack:** Python 3.11 stdlib (`json`, `urllib.request`, `pathlib`), existing `hearthstone` dependency, pytest, current HSConfig CLI and report-writing patterns.

---

## Scope Boundaries

This plan must not add replay parsing, HDT parsing, winrate analysis, candidate promotion, or post-run tuning. Those are HSTuner concerns.

This plan must not make HearthstoneJSON network availability a hard runtime dependency. Live HearthstoneJSON data is preferred for enrichment, but builds must still produce a validated package with an explicit partial-enrichment report if network lookup fails.

This plan does not turn `Presume.json` or `Concede.json` into active normal-path surfaces. They may remain as legacy/gated validator support, but active HSConfig docs should not present them as part of the normal output.

## File Structure

- Create `src/hsconfig/hearthstonejson.py`  
  Fetch and normalize HearthstoneJSON card rows. Provide deterministic helpers and no global mutable state.

- Create `src/hsconfig/semantic_enrichment.py`  
  Convert hydrated card metadata plus optional HearthstoneJSON rows into card semantics, linked entities, deckwide effects, and enrichment status.

- Create `src/hsconfig/semantic_audit.py`  
  Render a compact Markdown audit for generated package reports.

- Modify `src/hsconfig/cli.py`  
  Insert semantic enrichment between `hydrate_card_metadata()` and `build_gameplan_contract()`. Write `semantic_enrichment_report.json` and `card_semantic_audit.md`.

- Modify `src/hsconfig/gameplan_contract.py`  
  Preserve semantic families, linked entities, deckwide effects, and hero-power-pressure roles in the contract. Add GlobalValues overlay reasons.

- Modify `src/hsconfig/compile_globalvalues.py`  
  Use overlay-specific reason text when present so `MyHeroPowerValue` explains Darkbishop / Shadowform / Mind Spike.

- Modify `.agents/skills/hsconfig/*` and `README.md`  
  Document the semantic-enrichment boundary and mark Presume/Concede as not normal-path outputs.

- Create `tests/fixtures/hearthstonejson_shadowpriest_cards.json`  
  Small fixture containing `SW_448`, `EX1_625t`, and `BOM_05_Xyrella_006p2`.

- Create `tests/test_hearthstonejson.py`
- Create `tests/test_semantic_enrichment.py`
- Update `tests/test_card_metadata.py`
- Update `tests/test_gameplan_contract.py`
- Update `tests/test_compile_globalvalues.py`
- Update `tests/test_shadowpriest_e2e.py`
- Update `tests/test_skill_files.py`

---

## Task 1: HearthstoneJSON Adapter And Fixture

**Files:**
- Create: `tests/fixtures/hearthstonejson_shadowpriest_cards.json`
- Create: `src/hsconfig/hearthstonejson.py`
- Create: `tests/test_hearthstonejson.py`

- [ ] **Step 1: Add the focused HearthstoneJSON fixture**

Create `tests/fixtures/hearthstonejson_shadowpriest_cards.json`:

```json
[
  {
    "id": "SW_448",
    "dbfId": 64443,
    "name": "Darkbishop Benedictus",
    "type": "MINION",
    "cardClass": "PRIEST",
    "cost": 5,
    "set": "STORMWIND",
    "collectible": true,
    "referencedTags": ["START_OF_GAME_KEYWORD"],
    "text": "<b>Start of Game:</b> If the spells in your deck are all Shadow, enter Shadowform."
  },
  {
    "id": "EX1_625t",
    "dbfId": 1622,
    "name": "Mind Spike",
    "type": "HERO_POWER",
    "cardClass": "PRIEST",
    "cost": 2,
    "set": "EXPERT1",
    "text": "Deal $2 damage."
  },
  {
    "id": "BOM_05_Xyrella_006p2",
    "dbfId": 76557,
    "name": "Mind Spike",
    "type": "HERO_POWER",
    "cardClass": "PRIEST",
    "cost": 2,
    "set": "STORMWIND",
    "text": "Deal $3 damage."
  }
]
```

- [ ] **Step 2: Write failing adapter tests**

Create `tests/test_hearthstonejson.py`:

```python
import json
from pathlib import Path

from hsconfig.hearthstonejson import (
    HEARTHSTONEJSON_LATEST_ENUS_CARDS_URL,
    index_cards_by_id,
    load_cards_json,
    normalize_card_row,
)


FIXTURE = Path("tests/fixtures/hearthstonejson_shadowpriest_cards.json")


def test_load_cards_json_reads_fixture_rows():
    cards = load_cards_json(FIXTURE)

    assert {card["id"] for card in cards} == {
        "SW_448",
        "EX1_625t",
        "BOM_05_Xyrella_006p2",
    }


def test_normalize_card_row_preserves_semantic_fields():
    row = normalize_card_row(
        {
            "id": "SW_448",
            "dbfId": 64443,
            "name": "Darkbishop Benedictus",
            "type": "MINION",
            "cardClass": "PRIEST",
            "text": "enter Shadowform",
            "referencedTags": ["START_OF_GAME_KEYWORD"],
        }
    )

    assert row == {
        "id": "SW_448",
        "dbf_id": 64443,
        "name": "Darkbishop Benedictus",
        "type": "MINION",
        "card_class": "PRIEST",
        "cost": None,
        "text": "enter Shadowform",
        "mechanics": [],
        "referenced_tags": ["START_OF_GAME_KEYWORD"],
        "entourage": [],
    }


def test_index_cards_by_id_supports_id_and_dbf_lookup():
    cards = [normalize_card_row(row) for row in json.loads(FIXTURE.read_text(encoding="utf-8"))]
    index = index_cards_by_id(cards)

    assert index["SW_448"]["name"] == "Darkbishop Benedictus"
    assert index["64443"]["id"] == "SW_448"
    assert index["EX1_625t"]["type"] == "HERO_POWER"


def test_latest_url_points_to_hearthstonejson_latest_cards():
    assert HEARTHSTONEJSON_LATEST_ENUS_CARDS_URL == (
        "https://api.hearthstonejson.com/v1/latest/enUS/cards.json"
    )
```

- [ ] **Step 3: Run tests and confirm failure**

Run:

```powershell
pytest tests\test_hearthstonejson.py -q
```

Expected: fail with `ModuleNotFoundError: No module named 'hsconfig.hearthstonejson'`.

- [ ] **Step 4: Implement adapter**

Create `src/hsconfig/hearthstonejson.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen


HEARTHSTONEJSON_LATEST_ENUS_CARDS_URL = (
    "https://api.hearthstonejson.com/v1/latest/enUS/cards.json"
)
USER_AGENT = "HSConfig/0.1 semantic-enrichment"


def load_cards_json(path: str | Path) -> list[dict[str, Any]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"HearthstoneJSON card payload must be a list: {path}")
    return [normalize_card_row(row) for row in payload]


def fetch_latest_cards(timeout: float = 10.0) -> list[dict[str, Any]]:
    request = Request(
        HEARTHSTONEJSON_LATEST_ENUS_CARDS_URL,
        headers={"User-Agent": USER_AGENT},
    )
    with urlopen(request, timeout=timeout) as response:
        payload = json.load(response)
    if not isinstance(payload, list):
        raise ValueError("HearthstoneJSON latest cards response must be a list")
    return [normalize_card_row(row) for row in payload]


def normalize_card_row(row: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(row, dict):
        raise ValueError("HearthstoneJSON card row must be an object")
    card_id = str(row.get("id") or "").strip()
    if not card_id:
        raise ValueError("HearthstoneJSON card row missing id")
    return {
        "id": card_id,
        "dbf_id": int(row["dbfId"]) if row.get("dbfId") is not None else None,
        "name": str(row.get("name") or card_id),
        "type": str(row.get("type") or "UNKNOWN"),
        "card_class": row.get("cardClass"),
        "cost": int(row["cost"]) if row.get("cost") is not None else None,
        "text": str(row.get("text") or ""),
        "mechanics": [str(item) for item in row.get("mechanics", []) or []],
        "referenced_tags": [str(item) for item in row.get("referencedTags", []) or []],
        "entourage": [str(item) for item in row.get("entourage", []) or []],
    }


def index_cards_by_id(cards: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for card in cards:
        normalized = normalize_card_row(card) if "id" not in card else dict(card)
        index[str(normalized["id"])] = normalized
        if normalized.get("dbf_id") is not None:
            index[str(normalized["dbf_id"])] = normalized
    return index
```

- [ ] **Step 5: Run adapter tests**

Run:

```powershell
pytest tests\test_hearthstonejson.py -q
```

Expected: `4 passed`.

- [ ] **Step 6: Commit**

```powershell
git add src\hsconfig\hearthstonejson.py tests\test_hearthstonejson.py tests\fixtures\hearthstonejson_shadowpriest_cards.json
git commit -m "feat: add hearthstonejson card adapter"
```

---

## Task 2: Semantic Enrichment Layer

**Files:**
- Create: `src/hsconfig/semantic_enrichment.py`
- Create: `tests/test_semantic_enrichment.py`
- Modify: `src/hsconfig/card_metadata.py`
- Modify: `tests/test_card_metadata.py`

- [ ] **Step 1: Extend card metadata to preserve HearthstoneJSON-style fields**

Add this test to `tests/test_card_metadata.py`:

```python
def test_hydrate_card_metadata_preserves_referenced_tags_and_entourage():
    snapshot = hydrate_card_metadata(
        cards=[{"card_id": "SW_448", "dbf_id": 64443, "count": 1}],
        source_records={
            "SW_448": {
                "name": "Darkbishop Benedictus",
                "type": "MINION",
                "text": "Start of Game: enter Shadowform.",
                "referenced_tags": ["START_OF_GAME_KEYWORD"],
                "entourage": ["EX1_625t"],
            }
        },
    )

    card = snapshot["cards"][0]
    assert card["referenced_tags"] == ["START_OF_GAME_KEYWORD"]
    assert card["entourage"] == ["EX1_625t"]
```

Run:

```powershell
pytest tests\test_card_metadata.py::test_hydrate_card_metadata_preserves_referenced_tags_and_entourage -q
```

Expected: fail with `KeyError: 'referenced_tags'`.

- [ ] **Step 2: Implement metadata preservation**

In `src/hsconfig/card_metadata.py`, add these fields inside `merged = {...}` in `hydrate_card_metadata()`:

```python
            "referenced_tags": list(source.get("referenced_tags", source.get("referencedTags", [])) or []),
            "entourage": list(source.get("entourage", [] ) or []),
```

Keep the rest of the function unchanged.

Run:

```powershell
pytest tests\test_card_metadata.py -q
```

Expected: all card metadata tests pass.

- [ ] **Step 3: Write semantic enrichment tests**

Create `tests/test_semantic_enrichment.py`:

```python
import json
from pathlib import Path

from hsconfig.hearthstonejson import load_cards_json
from hsconfig.semantic_enrichment import enrich_card_metadata


FIXTURE = Path("tests/fixtures/hearthstonejson_shadowpriest_cards.json")


def test_enrich_darkbishop_links_shadowform_and_mind_spike():
    card_metadata = {
        "cards": [
            {
                "card_id": "SW_448",
                "dbf_id": 64443,
                "name": "Darkbishop Benedictus",
                "type": "MINION",
                "text": "<b>Start of Game:</b> If the spells in your deck are all Shadow, enter Shadowform.",
                "mechanic_families": ["minion"],
                "metadata_status": "source_record",
            }
        ]
    }

    enriched = enrich_card_metadata(
        card_metadata,
        hearthstonejson_cards=load_cards_json(FIXTURE),
    )

    card = enriched["cards"][0]
    assert "start_of_game" in card["semantic_families"]
    assert "shadowform" in card["semantic_families"]
    assert "hero_power_transform" in card["semantic_families"]
    assert "hero_power_pressure" in card["semantic_families"]
    assert card["linked_entities"][0]["card_id"] == "EX1_625t"
    assert card["linked_entities"][0]["type"] == "HERO_POWER"
    assert enriched["deckwide_effects"][0]["effect"] == "replace_starting_hero_power"


def test_enrichment_uses_fallback_mind_spike_when_json_rows_are_missing():
    card_metadata = {
        "cards": [
            {
                "card_id": "SW_448",
                "dbf_id": 64443,
                "name": "Darkbishop Benedictus",
                "type": "MINION",
                "text": "Start of Game: enter Shadowform.",
                "mechanic_families": ["minion"],
                "metadata_status": "source_record",
            }
        ]
    }

    enriched = enrich_card_metadata(card_metadata, hearthstonejson_cards=[])

    card = enriched["cards"][0]
    assert card["linked_entities"][0]["card_id"] == "EX1_625t"
    assert enriched["semantic_enrichment_status"] == "partial"
    assert enriched["semantic_enrichment_warnings"]


def test_non_shadowform_cards_keep_existing_mechanic_families():
    card_metadata = {
        "cards": [
            {
                "card_id": "EX1_001",
                "name": "Example",
                "mechanic_families": ["battlecry"],
                "metadata_status": "source_record",
            }
        ]
    }

    enriched = enrich_card_metadata(card_metadata, hearthstonejson_cards=[])

    assert enriched["cards"][0]["semantic_families"] == ["battlecry"]
    assert enriched["deckwide_effects"] == []
```

- [ ] **Step 4: Run tests and confirm failure**

Run:

```powershell
pytest tests\test_semantic_enrichment.py -q
```

Expected: fail with `ModuleNotFoundError: No module named 'hsconfig.semantic_enrichment'`.

- [ ] **Step 5: Implement semantic enrichment**

Create `src/hsconfig/semantic_enrichment.py`:

```python
from __future__ import annotations

import re
from typing import Any

from hsconfig.hearthstonejson import index_cards_by_id


MIND_SPIKE_FALLBACK = {
    "card_id": "EX1_625t",
    "dbf_id": 1622,
    "name": "Mind Spike",
    "type": "HERO_POWER",
    "card_class": "PRIEST",
    "text": "Deal $2 damage.",
    "source": "builtin_shadowform_fallback",
}


def enrich_card_metadata(
    card_metadata: dict[str, Any],
    *,
    hearthstonejson_cards: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    hjson_index = index_cards_by_id(hearthstonejson_cards or [])
    warnings: list[dict[str, Any]] = []
    deckwide_effects: list[dict[str, Any]] = []
    enriched_cards = []

    for card in card_metadata.get("cards", []):
        enriched = dict(card)
        hjson = hjson_index.get(str(card.get("card_id"))) or hjson_index.get(str(card.get("dbf_id")))
        if hjson:
            enriched = _merge_hjson(enriched, hjson)

        semantic_families = set(str(item) for item in enriched.get("mechanic_families", []))
        semantic_families.update(_semantic_families_from_card(enriched))
        linked_entities = list(enriched.get("linked_entities", []))

        if "shadowform" in semantic_families:
            hero_power, warning = _mind_spike_entity(hjson_index)
            linked_entities.append(hero_power)
            if warning:
                warnings.append({"card_id": enriched["card_id"], "warning": warning})
            semantic_families.update({"hero_power_transform", "hero_power_pressure"})
            deckwide_effects.append(
                {
                    "source_card_id": enriched["card_id"],
                    "source_card_name": enriched.get("name", enriched["card_id"]),
                    "effect": "replace_starting_hero_power",
                    "target_card_id": hero_power["card_id"],
                    "target_name": hero_power["name"],
                    "target_type": hero_power["type"],
                    "reason": (
                        "Darkbishop Benedictus enters Shadowform at Start of Game; "
                        "Mind Spike is a damage Hero Power for the ShadowPriest pressure plan."
                    ),
                }
            )

        enriched["semantic_families"] = sorted(semantic_families)
        enriched["linked_entities"] = linked_entities
        enriched_cards.append(enriched)

    return {
        "cards": enriched_cards,
        "deckwide_effects": _dedupe_deckwide_effects(deckwide_effects),
        "semantic_enrichment_status": "partial" if warnings else "complete",
        "semantic_enrichment_warnings": warnings,
    }


def _merge_hjson(card: dict[str, Any], hjson: dict[str, Any]) -> dict[str, Any]:
    merged = dict(card)
    merged.setdefault("name", hjson.get("name"))
    merged.setdefault("type", hjson.get("type"))
    merged.setdefault("text", hjson.get("text", ""))
    merged["referenced_tags"] = list(
        dict.fromkeys([*merged.get("referenced_tags", []), *hjson.get("referenced_tags", [])])
    )
    merged["entourage"] = list(dict.fromkeys([*merged.get("entourage", []), *hjson.get("entourage", [])]))
    return merged


def _semantic_families_from_card(card: dict[str, Any]) -> set[str]:
    text = _plain_text(str(card.get("text", ""))).lower()
    tags = {str(tag).upper() for tag in card.get("referenced_tags", [])}
    families: set[str] = set()
    if "START_OF_GAME_KEYWORD" in tags or "start of game" in text:
        families.add("start_of_game")
    if "enter shadowform" in text or "shadowform" in text:
        families.add("shadowform")
    if "hero power" in text:
        families.add("hero_power")
    if str(card.get("type", "")).upper() == "HERO_POWER":
        families.add("hero_power")
    return families


def _mind_spike_entity(index: dict[str, dict[str, Any]]) -> tuple[dict[str, Any], str | None]:
    row = index.get("EX1_625t")
    if row:
        return (
            {
                "card_id": str(row["id"]),
                "dbf_id": row.get("dbf_id"),
                "name": str(row.get("name", "Mind Spike")),
                "type": str(row.get("type", "HERO_POWER")),
                "text": str(row.get("text", "")),
                "source": "hearthstonejson",
            },
            None,
        )
    return dict(MIND_SPIKE_FALLBACK), "mind_spike_resolved_from_builtin_fallback"


def _plain_text(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).replace("$", "")


def _dedupe_deckwide_effects(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str]] = set()
    deduped = []
    for row in rows:
        key = (str(row["source_card_id"]), str(row["effect"]), str(row["target_card_id"]))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return sorted(deduped, key=lambda row: (row["source_card_id"], row["effect"], row["target_card_id"]))
```

- [ ] **Step 6: Run semantic tests**

Run:

```powershell
pytest tests\test_card_metadata.py tests\test_semantic_enrichment.py -q
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```powershell
git add src\hsconfig\card_metadata.py src\hsconfig\semantic_enrichment.py tests\test_card_metadata.py tests\test_semantic_enrichment.py
git commit -m "feat: enrich hero power transform semantics"
```

---

## Task 3: Wire Enrichment Into CLI Reports

**Files:**
- Modify: `src/hsconfig/cli.py`
- Create: `src/hsconfig/semantic_audit.py`
- Create: `tests/test_semantic_audit.py`
- Update: `tests/test_shadowpriest_e2e.py`

- [ ] **Step 1: Write audit renderer tests**

Create `tests/test_semantic_audit.py`:

```python
from hsconfig.semantic_audit import render_semantic_audit_markdown


def test_render_semantic_audit_mentions_darkbishop_mind_spike_and_globalvalues():
    report = {
        "cards": [
            {
                "card_id": "SW_448",
                "name": "Darkbishop Benedictus",
                "semantic_families": [
                    "start_of_game",
                    "shadowform",
                    "hero_power_transform",
                    "hero_power_pressure",
                ],
                "linked_entities": [
                    {"card_id": "EX1_625t", "name": "Mind Spike", "type": "HERO_POWER"}
                ],
            }
        ],
        "deckwide_effects": [
            {
                "source_card_id": "SW_448",
                "effect": "replace_starting_hero_power",
                "target_card_id": "EX1_625t",
                "target_name": "Mind Spike",
                "reason": "Darkbishop Benedictus enters Shadowform at Start of Game.",
            }
        ],
        "semantic_enrichment_status": "complete",
        "semantic_enrichment_warnings": [],
    }

    text = render_semantic_audit_markdown(report)

    assert "# Card Semantic Audit" in text
    assert "SW_448 Darkbishop Benedictus" in text
    assert "hero_power_transform" in text
    assert "EX1_625t Mind Spike" in text
    assert "replace_starting_hero_power" in text
```

Run:

```powershell
pytest tests\test_semantic_audit.py -q
```

Expected: fail with `ModuleNotFoundError: No module named 'hsconfig.semantic_audit'`.

- [ ] **Step 2: Implement audit renderer**

Create `src/hsconfig/semantic_audit.py`:

```python
from __future__ import annotations

from typing import Any


def render_semantic_audit_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Card Semantic Audit",
        "",
        f"Status: `{report.get('semantic_enrichment_status', 'unknown')}`",
        "",
        "## Deckwide Effects",
        "",
    ]
    effects = report.get("deckwide_effects", [])
    if not effects:
        lines.append("- None")
    for effect in effects:
        lines.append(
            "- "
            f"{effect.get('source_card_id')} -> {effect.get('effect')} -> "
            f"{effect.get('target_card_id')} {effect.get('target_name')}: "
            f"{effect.get('reason', '')}"
        )

    lines.extend(["", "## Cards", ""])
    for card in sorted(report.get("cards", []), key=lambda row: str(row.get("card_id", ""))):
        lines.append(f"### {card.get('card_id')} {card.get('name', '')}".rstrip())
        lines.append("")
        families = ", ".join(card.get("semantic_families", [])) or "none"
        lines.append(f"- Semantic families: {families}")
        linked = card.get("linked_entities", [])
        if linked:
            for entity in linked:
                lines.append(
                    "- Linked entity: "
                    f"{entity.get('card_id')} {entity.get('name')} ({entity.get('type')})"
                )
        else:
            lines.append("- Linked entity: none")
        lines.append("")

    warnings = report.get("semantic_enrichment_warnings", [])
    lines.extend(["## Warnings", ""])
    if not warnings:
        lines.append("- None")
    for warning in warnings:
        lines.append(f"- {warning.get('card_id')}: {warning.get('warning')}")
    lines.append("")
    return "\n".join(lines)
```

- [ ] **Step 3: Run audit renderer tests**

Run:

```powershell
pytest tests\test_semantic_audit.py -q
```

Expected: pass.

- [ ] **Step 4: Update ShadowPriest E2E test for new reports**

Add these assertions to `tests/test_shadowpriest_e2e.py` after loading `deck_identity` / `manifest`:

```python
    semantic_report = json.loads(
        (reports / "semantic_enrichment_report.json").read_text(encoding="utf-8")
    )
    semantic_audit = (reports / "card_semantic_audit.md").read_text(encoding="utf-8")
    darkbishop = next(card for card in semantic_report["cards"] if card["card_id"] == "SW_448")

    assert semantic_report["semantic_enrichment_status"] in {"complete", "partial"}
    assert "hero_power_transform" in darkbishop["semantic_families"]
    assert darkbishop["linked_entities"][0]["card_id"] == "EX1_625t"
    assert "SW_448 Darkbishop Benedictus" in semantic_audit
    assert "EX1_625t Mind Spike" in semantic_audit
```

Run:

```powershell
pytest tests\test_shadowpriest_e2e.py -q
```

Expected: fail because CLI does not write semantic reports yet.

- [ ] **Step 5: Wire semantic enrichment into CLI**

Modify `src/hsconfig/cli.py`:

Add imports:

```python
from hsconfig.hearthstonejson import fetch_latest_cards
from hsconfig.semantic_audit import render_semantic_audit_markdown
from hsconfig.semantic_enrichment import enrich_card_metadata
```

Replace:

```python
    card_metadata = hydrate_card_metadata(
        cards=deck_identity["cards"],
        source_records=source_records,
    )
```

with:

```python
    card_metadata = hydrate_card_metadata(
        cards=deck_identity["cards"],
        source_records=source_records,
    )
    hearthstonejson_cards: list[dict[str, Any]] = []
    semantic_fetch_error: str | None = None
    try:
        hearthstonejson_cards = fetch_latest_cards(timeout=10.0)
    except Exception as exc:
        semantic_fetch_error = str(exc)
    semantic_report = enrich_card_metadata(
        card_metadata,
        hearthstonejson_cards=hearthstonejson_cards,
    )
    if semantic_fetch_error is not None:
        semantic_report.setdefault("semantic_enrichment_warnings", []).append(
            {"card_id": None, "warning": f"hearthstonejson_fetch_failed: {semantic_fetch_error}"}
        )
        semantic_report["semantic_enrichment_status"] = "partial"
    card_metadata = {"cards": semantic_report["cards"]}
```

After writing `deck_identity.json`, write:

```python
    write_json(reports_dir / "semantic_enrichment_report.json", semantic_report)
    (reports_dir / "card_semantic_audit.md").parent.mkdir(parents=True, exist_ok=True)
    (reports_dir / "card_semantic_audit.md").write_text(
        render_semantic_audit_markdown(semantic_report),
        encoding="utf-8",
        newline="\n",
    )
```

- [ ] **Step 6: Run CLI/E2E tests**

Run:

```powershell
pytest tests\test_semantic_audit.py tests\test_shadowpriest_e2e.py tests\test_cli.py -q
```

Expected: pass.

- [ ] **Step 7: Commit**

```powershell
git add src\hsconfig\cli.py src\hsconfig\semantic_audit.py tests\test_semantic_audit.py tests\test_shadowpriest_e2e.py
git commit -m "feat: write semantic enrichment reports"
```

---

## Task 4: Gameplan Contract Uses Hero-Power Semantics

**Files:**
- Modify: `src/hsconfig/gameplan_contract.py`
- Modify: `tests/test_gameplan_contract.py`

- [ ] **Step 1: Add contract regression test**

Add to `tests/test_gameplan_contract.py`:

```python
def test_gameplan_contract_turns_shadowform_semantics_into_hero_power_pressure():
    deck_identity = {
        "deck_name": "ShadowPriest",
        "cards": [{"card_id": "SW_448", "count": 1}],
    }
    card_metadata = {
        "cards": [
            {
                "card_id": "SW_448",
                "name": "Darkbishop Benedictus",
                "mechanic_families": ["minion"],
                "semantic_families": [
                    "minion",
                    "start_of_game",
                    "shadowform",
                    "hero_power_transform",
                    "hero_power_pressure",
                ],
                "linked_entities": [
                    {
                        "card_id": "EX1_625t",
                        "name": "Mind Spike",
                        "type": "HERO_POWER",
                        "text": "Deal $2 damage.",
                    }
                ],
                "deckwide_effects": [
                    {
                        "effect": "replace_starting_hero_power",
                        "target_card_id": "EX1_625t",
                        "target_name": "Mind Spike",
                    }
                ],
            }
        ]
    }

    contract = build_gameplan_contract(deck_identity, card_metadata)

    darkbishop = contract["cards"]["SW_448"]
    assert "hero_power_transform" in darkbishop["roles"]
    assert "hero_power_pressure" in darkbishop["roles"]
    assert darkbishop["linked_entities"][0]["card_id"] == "EX1_625t"
    assert contract["deckwide_effects"][0]["effect"] == "replace_starting_hero_power"
    assert (
        contract["card_usage_expectations"]["SW_448"]["expected_use"]
        == "start_of_game_shadowform_enables_hero_power_pressure"
    )
    assert contract["aggression_profile"]["global_value_overlays"]["MyHeroPowerValue"] == "increase"
    assert "Mind Spike" in contract["aggression_profile"]["global_value_overlay_reasons"]["MyHeroPowerValue"]
```

Run:

```powershell
pytest tests\test_gameplan_contract.py::test_gameplan_contract_turns_shadowform_semantics_into_hero_power_pressure -q
```

Expected: fail because roles and deckwide effects are not preserved.

- [ ] **Step 2: Preserve semantic families and deckwide effects**

Modify `src/hsconfig/gameplan_contract.py`.

Inside the per-card loop, replace the current `mechanic_families = ...` block with:

```python
        mechanic_families = sorted(
            {
                str(item)
                for item in metadata.get(
                    "mechanic_families", deck_card.get("mechanic_families", [])
                )
            }
        )
        semantic_families = sorted(
            {
                *mechanic_families,
                *[str(item) for item in metadata.get("semantic_families", [])],
            }
        )
```

Call:

```python
        roles = _infer_roles(semantic_families, related_claims)
```

and add to `card_record`:

```python
            "semantic_families": semantic_families,
            "linked_entities": list(metadata.get("linked_entities", [])),
```

Before return, compute:

```python
    deckwide_effects = _deckwide_effects(card_map, metadata_by_card)
    global_value_overlays, global_value_overlay_reasons = _global_value_overlay_profile(card_map, deckwide_effects)
```

Replace the `aggression_profile` field with:

```python
        "aggression_profile": {
            "speed": "aggro",
            "pressure_bias": "high",
            "global_value_overlays": global_value_overlays,
            "global_value_overlay_reasons": global_value_overlay_reasons,
        },
        "deckwide_effects": deckwide_effects,
```

- [ ] **Step 3: Add helper implementations**

In `src/hsconfig/gameplan_contract.py`, replace `_global_value_overlays()` with:

```python
def _global_value_overlay_profile(
    card_map: dict[str, dict[str, Any]],
    deckwide_effects: list[dict[str, Any]],
) -> tuple[dict[str, str], dict[str, str]]:
    overlays: dict[str, str] = {}
    reasons: dict[str, str] = {}
    all_roles = {role for card in card_map.values() for role in card.get("roles", [])}
    if {"pressure", "damage", "combo_piece"} & all_roles:
        overlays.update(
            {
                "GlobalMinionAttack": "increase",
                "GlobalMinionIntrinsicValue": "increase",
                "OppGlobalHeroHealth": "increase",
                "OppGlobalMinionAttack": "decrease",
                "OppGlobalMinionHealth": "decrease",
                "OppGlobalMinionIntrinsicValue": "decrease",
            }
        )
    if "divine_shield" in all_roles:
        overlays["GlobalDivineShield"] = "increase"
    if "charge" in all_roles:
        overlays["GlobalCharge"] = "increase"
    if "rush" in all_roles:
        overlays["GlobalRush"] = "increase"
    if "location" in all_roles:
        overlays["GlobalLocationIntrinsicValue"] = "increase"
        overlays["GlobalLocationHealth"] = "increase"
    if {"hero_power", "hero_power_pressure", "hero_power_transform"} & all_roles:
        overlays["MyHeroPowerValue"] = "increase"
        reasons["MyHeroPowerValue"] = _hero_power_overlay_reason(deckwide_effects)
    if "taunt" in all_roles:
        overlays["GlobalTaunt"] = "decrease"
    return overlays, reasons


def _hero_power_overlay_reason(deckwide_effects: list[dict[str, Any]]) -> str:
    for effect in deckwide_effects:
        if effect.get("effect") == "replace_starting_hero_power":
            return (
                f"{effect.get('source_card_name', effect.get('source_card_id'))} "
                f"enters Shadowform and enables {effect.get('target_name', 'the Hero Power')} "
                "as pressure damage."
            )
    return "Hero Power pressure is part of this deck plan."


def _deckwide_effects(
    card_map: dict[str, dict[str, Any]],
    metadata_by_card: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    rows = []
    for card_id, card in card_map.items():
        metadata = metadata_by_card.get(card_id, {})
        for linked in card.get("linked_entities", []):
            if "hero_power_transform" not in card.get("roles", []):
                continue
            rows.append(
                {
                    "source_card_id": card_id,
                    "source_card_name": card.get("name", card_id),
                    "effect": "replace_starting_hero_power",
                    "target_card_id": linked.get("card_id"),
                    "target_name": linked.get("name"),
                    "target_type": linked.get("type"),
                    "reason": (
                        f"{card.get('name', card_id)} enables "
                        f"{linked.get('name', linked.get('card_id'))} as the deck's pressure Hero Power."
                    ),
                }
            )
    return sorted(rows, key=lambda row: (row["source_card_id"], row["effect"], str(row["target_card_id"])))
```

Update `_infer_expected_use()`:

```python
    if "hero_power_transform" in roles and "hero_power_pressure" in roles:
        return "start_of_game_shadowform_enables_hero_power_pressure"
```

Place this before the `combo_piece` check.

- [ ] **Step 4: Run contract tests**

Run:

```powershell
pytest tests\test_gameplan_contract.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```powershell
git add src\hsconfig\gameplan_contract.py tests\test_gameplan_contract.py
git commit -m "feat: add hero power pressure to gameplan contract"
```

---

## Task 5: GlobalValues Uses Hero-Power Reason Text

**Files:**
- Modify: `src/hsconfig/compile_globalvalues.py`
- Modify: `tests/test_compile_globalvalues.py`

- [ ] **Step 1: Add GlobalValues regression test**

Add to `tests/test_compile_globalvalues.py`:

```python
def test_compile_globalvalues_uses_hero_power_overlay_reason():
    baseline = {
        "GameCardId": "GlobalValues",
        "ConfigComment": "Baseline",
        "MyHeroPowerValue": {"values": [{"condition": "*", "value": "1.00"}]},
    }
    contract = {
        "aggression_profile": {
            "speed": "aggro",
            "global_value_overlays": {"MyHeroPowerValue": "increase"},
            "global_value_overlay_reasons": {
                "MyHeroPowerValue": "Darkbishop Benedictus enables Mind Spike as pressure damage."
            },
        }
    }

    result = compile_globalvalues(baseline, contract)

    assert result["config"]["MyHeroPowerValue"]["values"][0]["value"] == "1.15"
    profile = result["profile"]["keys"]["MyHeroPowerValue"]
    assert profile["decision"] == "overlay_changed"
    assert profile["reason"] == "Darkbishop Benedictus enables Mind Spike as pressure damage."
```

Run:

```powershell
pytest tests\test_compile_globalvalues.py::test_compile_globalvalues_uses_hero_power_overlay_reason -q
```

Expected: fail because `_overlay_reason()` currently only receives key and overlay.

- [ ] **Step 2: Implement reason lookup**

In `src/hsconfig/compile_globalvalues.py`, after `overlays = ...`, add:

```python
    overlay_reasons = dict(aggression_profile.get("global_value_overlay_reasons", {}))
```

Replace:

```python
                    "reason": _overlay_reason(key, overlay),
```

with:

```python
                    "reason": overlay_reasons.get(key, _overlay_reason(key, overlay)),
```

- [ ] **Step 3: Run GlobalValues tests**

Run:

```powershell
pytest tests\test_compile_globalvalues.py -q
```

Expected: pass.

- [ ] **Step 4: Commit**

```powershell
git add src\hsconfig\compile_globalvalues.py tests\test_compile_globalvalues.py
git commit -m "feat: explain hero power globalvalues overlays"
```

---

## Task 6: ShadowPriest End-To-End Semantic Regression

**Files:**
- Modify: `tests/test_shadowpriest_e2e.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Extend ShadowPriest E2E assertions**

In `tests/test_shadowpriest_e2e.py`, add after loading `deck_identity` and before final runtime assertions:

```python
    contract = json.loads((reports / "gameplan_contract.json").read_text(encoding="utf-8"))
    globalvalues_profile = json.loads(
        (reports / "globalvalues_profile.json").read_text(encoding="utf-8")
    )
    darkbishop_contract = contract["cards"]["SW_448"]

    assert "hero_power_transform" in darkbishop_contract["roles"]
    assert "hero_power_pressure" in darkbishop_contract["roles"]
    assert darkbishop_contract["linked_entities"][0]["card_id"] == "EX1_625t"
    assert contract["deckwide_effects"][0]["target_name"] == "Mind Spike"
    assert (
        contract["card_usage_expectations"]["SW_448"]["expected_use"]
        == "start_of_game_shadowform_enables_hero_power_pressure"
    )

    hero_power_profile = globalvalues_profile["keys"]["MyHeroPowerValue"]
    assert hero_power_profile["decision"] == "overlay_changed"
    assert "Mind Spike" in hero_power_profile["reason"]
```

Also assert no normal-path optional surfaces:

```python
    assert not (deck_dir / "Presume.json").exists()
    assert not (deck_dir / "Concede.json").exists()
```

- [ ] **Step 2: Run E2E test and confirm failure before previous tasks**

If executing this task after Tasks 1-5, it should pass. If it is run before Tasks 1-5, it should fail with missing semantic roles. The worker should run it now:

```powershell
pytest tests\test_shadowpriest_e2e.py -q
```

Expected after Tasks 1-5: pass.

- [ ] **Step 3: Add CLI report presence assertions**

In `tests/test_cli.py`, inside `test_build_decodes_deck_code_by_default`, add:

```python
    semantic_report = json.loads(
        (reports / "semantic_enrichment_report.json").read_text(encoding="utf-8")
    )
    assert any(card["card_id"] == "SW_448" for card in semantic_report["cards"])
    assert (reports / "card_semantic_audit.md").exists()
```

Run:

```powershell
pytest tests\test_cli.py tests\test_shadowpriest_e2e.py -q
```

Expected: pass.

- [ ] **Step 4: Commit**

```powershell
git add tests\test_shadowpriest_e2e.py tests\test_cli.py
git commit -m "test: lock shadowpriest hero power semantics"
```

---

## Task 7: Presume / Concede Active-Path Cleanup

**Files:**
- Modify: `README.md`
- Modify: `.agents/skills/hsconfig/SKILL.md`
- Modify: `.agents/skills/hsconfig/references/visionai-surfaces.md`
- Modify: `tests/test_skill_files.py`
- Modify: `tests/test_surface_intent.py`

- [ ] **Step 1: Update skill file test expectations**

Add to `tests/test_skill_files.py`:

```python
def test_skill_docs_keep_presume_concede_out_of_normal_path():
    text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    workflow = (SKILL_ROOT / "references" / "workflow.md").read_text(encoding="utf-8")
    surfaces = (SKILL_ROOT / "references" / "visionai-surfaces.md").read_text(encoding="utf-8")

    assert "Presume.json` or `Concede.json`" in text
    assert "normal path" in surfaces
    assert "Presume.json" not in workflow
    assert "Concede.json" not in workflow
```

Run:

```powershell
pytest tests\test_skill_files.py::test_skill_docs_keep_presume_concede_out_of_normal_path -q
```

Expected: fail until docs are updated.

- [ ] **Step 2: Update active docs**

In `.agents/skills/hsconfig/SKILL.md`, keep the rule:

```markdown
- Do not emit `Presume.json` or `Concede.json` in the normal path; they are legacy/gated surfaces only.
```

In `.agents/skills/hsconfig/references/visionai-surfaces.md`, make the Presume/Concede line:

```markdown
- `Presume.json` and `Concede.json` are legacy/gated validator-supported surfaces, not normal HSConfig outputs.
```

Do not add Presume/Concede to `.agents/skills/hsconfig/references/workflow.md`.

- [ ] **Step 3: Update surface intent test to isolate legacy policies**

In `tests/test_surface_intent.py`, split the current `test_surface_intent_routes_all_runtime_surfaces_from_contract` into:

1. A normal-path test with no `policies`, asserting `Presume.json` and `Concede.json` are not in `optional_surfaces`.
2. A legacy/gated test with `policies`, asserting they can still appear when explicitly present.

Use this normal-path assertion:

```python
    assert "Presume.json" not in intent["optional_surfaces"]
    assert "Concede.json" not in intent["optional_surfaces"]
```

- [ ] **Step 4: Run docs/surface tests**

Run:

```powershell
pytest tests\test_skill_files.py tests\test_surface_intent.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```powershell
git add README.md .agents\skills\hsconfig\SKILL.md .agents\skills\hsconfig\references\visionai-surfaces.md tests\test_skill_files.py tests\test_surface_intent.py
git commit -m "docs: clarify normal hsconfig surfaces"
```

---

## Task 8: Final Verification And Smoke

**Files:**
- No source changes unless verification finds a defect.

- [ ] **Step 1: Run targeted semantic suite**

```powershell
pytest tests\test_hearthstonejson.py tests\test_semantic_enrichment.py tests\test_semantic_audit.py tests\test_gameplan_contract.py tests\test_compile_globalvalues.py tests\test_shadowpriest_e2e.py -q
```

Expected: all tests pass.

- [ ] **Step 2: Run full suite**

```powershell
pytest -q
```

Expected: all tests pass.

- [ ] **Step 3: Run ShadowPriest CLI smoke**

```powershell
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path .).Path
$tmpRoot = Join-Path $repo 'tmp'
New-Item -ItemType Directory -Force -Path $tmpRoot | Out-Null
$suffix = [System.Guid]::NewGuid().ToString('N').Substring(0, 8)
$package = Join-Path $tmpRoot "shadowpriest_semantic_smoke_$suffix"
$runtime = Join-Path $tmpRoot "shadowpriest_semantic_runtime_$suffix"
$env:PYTHONPATH = 'src'
$deckCode = 'AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA='
python -m hsconfig.cli build --deck-name 'ShadowPriest' --deck-code $deckCode --runtime-root $runtime --out $package --json
python -m hsconfig.cli validate --package $package --json
python -m hsconfig.cli apply --package $package --runtime-root $runtime --json
$contract = Get-Content -Raw -LiteralPath (Join-Path $package 'reports\gameplan_contract.json') | ConvertFrom-Json
$profile = Get-Content -Raw -LiteralPath (Join-Path $package 'reports\globalvalues_profile.json') | ConvertFrom-Json
$deckConfig = Get-Content -Raw -LiteralPath (Join-Path $runtime 'CustomConfig\deck_config.ini')
if ($contract.cards.SW_448.roles -notcontains 'hero_power_transform') { throw 'Missing hero_power_transform role' }
if ($contract.deckwide_effects[0].target_name -ne 'Mind Spike') { throw 'Missing Mind Spike deckwide effect' }
if ($profile.keys.MyHeroPowerValue.decision -ne 'overlay_changed') { throw 'MyHeroPowerValue was not changed' }
if ($deckConfig -notmatch 'ShadowPriest\s*=\s*shadowpriest') { throw 'Missing deck_config mapping' }
foreach ($target in @($package, $runtime)) {
  $resolved = (Resolve-Path -LiteralPath $target).Path
  $tmpResolved = (Resolve-Path -LiteralPath $tmpRoot).Path
  if (-not $resolved.StartsWith($tmpResolved, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to remove outside tmp: $resolved"
  }
  Remove-Item -LiteralPath $resolved -Recurse -Force
}
```

Expected:

- build status `passed`
- validate status `passed`
- apply status `applied`
- `SW_448` has `hero_power_transform`
- deckwide effect targets `Mind Spike`
- `MyHeroPowerValue` is `overlay_changed`
- runtime `deck_config.ini` contains `ShadowPriest = shadowpriest`

- [ ] **Step 4: Diff and status checks**

```powershell
git diff --check
git status --short --branch
```

Expected: no diff-check output; branch ahead of `origin/main` only by intended commits.

- [ ] **Step 5: Push**

```powershell
git push origin main
```

Expected: `main -> main`.

---

## Self-Review Checklist

- [ ] The plan keeps HSConfig separate from HSTuner and does not add replay/log/winrate/candidate-promotion logic.
- [ ] The plan gives ShadowPriest / Darkbishop / Mind Spike a concrete regression path.
- [ ] Hero-power transform is expressed through semantic contract and `GlobalValues.MyHeroPowerValue`, not a blind card-local `BeforeUseHeroPowerBonus`.
- [ ] HearthstoneJSON is useful but not a hard build dependency.
- [ ] Presume/Concede are not normal-path HSConfig outputs.
- [ ] Every new behavior has targeted tests and an E2E ShadowPriest check.
- [ ] Every task has a commit gate.

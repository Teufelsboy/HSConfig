# HSConfig No-Block Static Semantic Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make HSConfig always produce a load-safe HearthRanger CustomConfig package while improving static Hearthstone mechanic understanding enough that every deck card receives a useful, visible config intent or a non-blocking warning.

**Architecture:** Keep HSConfig as a lean pre-run config generator, not a post-game tuner. Tighten runtime package gates around actual HearthRanger load safety, expand the HearthstoneJSON-backed semantic layer, then route every mechanic into direct, identity-gated direct, partial, or warning-only lanes that never block `VALID_PACKAGE` apply.

**Tech Stack:** Python package under `src/hsconfig`, pytest, HearthstoneJSON full `cards.json`, existing VisionAI registry, existing `operator_summary.json` as the single operator gate.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig` for `Teufelsboy/HSConfig`.
- HSConfig is pre-run only: no replay parsing, no winrate analysis, no HSTuner behavior, no runtime-log tuning.
- Runtime package validity is technical: valid JSON, supported VisionAI surfaces, required `GlobalValues.json`, required `Mulligan.json`, one deck runtime directory, input manifest, and no normal-path `Presume.json` or `Concede.json`.
- Missing per-card `CARDID.json` coverage is a warning or richness gap, not a package blocker, when required runtime files are valid.
- `reports/operator_summary.json` remains the single operator-facing readiness and apply gate.
- `runtime_apply_allowed=true` is allowed when `technical_status=VALID_PACKAGE`, even if semantic warnings exist.
- Warning-only mechanics must stay visible in reports and must not block load-safe apply.
- Do not add a new orchestration layer or new dependency for this wave.
- Keep every generated package deck-neutral; fixture decks prove behavior but do not become product logic.

---

## File Structure

- Modify `src/hsconfig/apply_gate.py`: remove per-card CardID presence as a hard apply-gate requirement; keep required files and stale-summary checks.
- Modify `src/hsconfig/validate_package.py`: strict completeness should require `GlobalValues.json` and `Mulligan.json`, but not at least one per-card CardID file.
- Modify `src/hsconfig/hearthstonejson.py`: preserve richer normalized fields from full `cards.json`.
- Create `src/hsconfig/static_semantics.py`: central, deterministic static card semantic inference from card type, mechanics, referenced tags, text, and explicit fields.
- Modify `src/hsconfig/card_metadata.py`: use `static_semantics.infer_static_semantics()` to assign mechanic families and preserve semantic evidence.
- Modify `src/hsconfig/semantic_enrichment.py`: merge static semantic evidence after HearthstoneJSON hydration and keep linked hero power/entity behavior intact.
- Modify `src/hsconfig/mechanic_support.py`: ensure all new mechanic families have non-blocking support lanes and warning boundaries.
- Modify `src/hsconfig/operator_summary.py`: expose a compact static semantic summary and first non-blocking warning boundary without changing apply permission.
- Modify `src/hsconfig/package_builder.py`: emit `reports/semantic_enrichment_report.json` from existing prepare flow.
- Modify `docs/operator/README.md`: document the no-block load-safe contract and the new semantic report.
- Modify `C:\Users\darbo\.codex\skills\hsconfig\SKILL.md` only through `scripts/sync_installed_skill.py` after repo docs are updated.
- Add tests:
  - `tests/test_apply_gate.py`
  - `tests/test_validate_package.py`
  - `tests/test_hearthstonejson.py`
  - `tests/test_static_semantics.py`
  - `tests/test_card_metadata.py`
  - `tests/test_semantic_enrichment.py`
  - `tests/test_mechanic_support.py`
  - `tests/test_operator_summary.py`
  - `tests/test_universal_wild_no_block_matrix.py`
  - `tests/test_docs_active_path.py`
  - `tests/test_skill_sync.py`

---

### Task 1: Align Runtime Gates With Minimal Load-Safe CustomConfig

**Files:**
- Modify: `src/hsconfig/apply_gate.py`
- Modify: `src/hsconfig/validate_package.py`
- Test: `tests/test_apply_gate.py`
- Test: `tests/test_validate_package.py`

**Interfaces:**
- Consumes: `evaluate_apply_gate(package_root: str | Path, *, allow_source_informed: bool = False) -> dict[str, Any]`
- Consumes: `validate_config_package(package_root: str | Path, *, require_complete_package: bool = False, ...) -> dict[str, Any]`
- Produces: load-safe apply and strict validation that allow packages with `GlobalValues.json` and `Mulligan.json` even when no per-card CardID file exists.

- [ ] **Step 1: Add failing apply-gate test for minimal package without CardID files**

Append this test to `tests/test_apply_gate.py`:

```python
def test_apply_gate_allows_minimal_load_safe_package_without_cardid_files(tmp_path: Path):
    package = tmp_path / "package"
    write_json(
        package / "reports" / "input_manifest.json",
        {"deck_name": "deck", "deck_code": "fixture", "runtime_root": "unused"},
    )
    write_json(
        package / "CustomConfig" / "deck" / "GlobalValues.json",
        {"GameCardId": "GlobalValues", "ConfigComment": "new"},
    )
    write_json(
        package / "CustomConfig" / "deck" / "Mulligan.json",
        {"GameCardId": "Mulligan", "ConfigComment": "new", "Mulligan": {"values": []}},
    )
    _write_operator_summary(
        package,
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "STATIC_SEMANTICS_USABLE",
            "next_action": "READY_TO_APPLY_WITH_WARNINGS",
            "apply_policy": "ALLOWED_WITH_WARNINGS",
            "semantic_blockers": [{"reason": "no_cardid_runtime_rows", "count": 30}],
            "generated_files": [
                "CustomConfig/deck/GlobalValues.json",
                "CustomConfig/deck/Mulligan.json",
            ],
        },
    )

    gate = evaluate_apply_gate(package)

    assert gate["status"] == "allowed"
    assert gate["allowed"] is True
    assert gate["mode"] == "load_safe_apply"
    assert gate["reasons"][0]["reason"] == "runtime_load_safe_package"
    assert gate["reasons"][0]["semantic_blocker_count"] == 1
```

- [ ] **Step 2: Add failing strict validation test for minimal complete runtime package**

Append this test to `tests/test_validate_package.py`:

```python
def test_validate_package_strict_mode_accepts_minimal_load_safe_package_without_cardid(tmp_path: Path):
    deck_dir = tmp_path / "CustomConfig" / "deck"
    write_json(
        deck_dir / "GlobalValues.json",
        {
            "GameCardId": "GlobalValues",
            "ConfigComment": "test",
            "FirstTurnValueWeight": {"values": [{"condition": "*", "value": "1"}]},
            "SecondTurnValueWeight": {"values": [{"condition": "*", "value": "0"}]},
        },
    )
    write_json(
        deck_dir / "Mulligan.json",
        {
            "GameCardId": "Mulligan",
            "ConfigComment": "test",
            "Mulligan": {
                "values": [
                    {
                        "comment": "hold early pressure",
                        "mulligan": "EX1_001",
                        "condition": "*",
                        "value": "hold",
                    }
                ]
            },
        },
    )

    report = validate_config_package(tmp_path, require_complete_package=True)

    assert report == {"status": "passed", "errors": [], "checked_files": 2}
```

- [ ] **Step 3: Run tests to verify they fail**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_apply_gate.py::test_apply_gate_allows_minimal_load_safe_package_without_cardid_files tests/test_validate_package.py::test_validate_package_strict_mode_accepts_minimal_load_safe_package_without_cardid -q
```

Expected: both tests fail because `missing_cardid_runtime_file` and `missing at least one per-card CardID runtime file` are still hard blockers.

- [ ] **Step 4: Remove CardID hard requirement from apply gate**

In `src/hsconfig/apply_gate.py`, delete the `card_files` block inside `_required_package_structure_reasons()` that returns `missing_cardid_runtime_file`. Keep the `REQUIRED_RUNTIME_FILES` loop and summary-file checks unchanged.

- [ ] **Step 5: Remove CardID hard requirement from strict validation**

In `src/hsconfig/validate_package.py`, change `_validate_required_package_files()` so it only checks `GlobalValues.json` and `Mulligan.json`:

```python
def _validate_required_package_files(deck_dir: Path) -> list[str]:
    errors = []
    if not (deck_dir / "GlobalValues.json").is_file():
        errors.append(f"{deck_dir}: missing required runtime file GlobalValues.json")
    if not (deck_dir / "Mulligan.json").is_file():
        errors.append(f"{deck_dir}: missing required runtime file Mulligan.json")
    return errors
```

- [ ] **Step 6: Run focused tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_apply_gate.py tests/test_validate_package.py -q
```

Expected: all selected tests pass.

- [ ] **Step 7: Commit**

```powershell
git add src/hsconfig/apply_gate.py src/hsconfig/validate_package.py tests/test_apply_gate.py tests/test_validate_package.py
git commit -m "fix: allow minimal load-safe hsconfig packages"
```

---

### Task 2: Preserve Rich HearthstoneJSON Fields

**Files:**
- Modify: `src/hsconfig/hearthstonejson.py`
- Test: `tests/test_hearthstonejson.py`

**Interfaces:**
- Consumes: `normalize_card_row(row: dict[str, Any]) -> dict[str, Any]`
- Produces: normalized card rows with rich fields for later static semantic inference.

- [ ] **Step 1: Add failing normalization test**

Append this test to `tests/test_hearthstonejson.py`:

```python
def test_normalize_card_row_preserves_static_semantic_fields():
    row = normalize_card_row(
        {
            "id": "TEST_001",
            "dbfId": 1001,
            "name": "Test Weapon",
            "type": "WEAPON",
            "cardClass": "WARRIOR",
            "classes": ["WARRIOR", "ROGUE"],
            "cost": 3,
            "attack": 4,
            "health": 0,
            "durability": 2,
            "collectible": True,
            "text": "Tradeable. Overload: (1).",
            "mechanics": ["TRADEABLE"],
            "referencedTags": ["OVERLOAD"],
            "spellSchool": "FIRE",
            "race": "MECHANICAL",
            "races": ["MECHANICAL"],
            "overload": 1,
            "spellDamage": 2,
            "targetingArrowText": "Deal damage.",
            "heroPowerDbfId": 479,
            "entourage": ["TEST_001t"],
        }
    )

    assert row["collectible"] is True
    assert row["attack"] == 4
    assert row["health"] == 0
    assert row["durability"] == 2
    assert row["classes"] == ["WARRIOR", "ROGUE"]
    assert row["spell_school"] == "FIRE"
    assert row["race"] == "MECHANICAL"
    assert row["races"] == ["MECHANICAL"]
    assert row["overload"] == 1
    assert row["spell_damage"] == 2
    assert row["targeting_arrow_text"] == "Deal damage."
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_hearthstonejson.py::test_normalize_card_row_preserves_static_semantic_fields -q
```

Expected: FAIL with missing keys such as `collectible` or `attack`.

- [ ] **Step 3: Extend `normalize_card_row()`**

In `src/hsconfig/hearthstonejson.py`, add small helpers and include the fields in the returned dict:

```python
def _int_or_none(value: Any) -> int | None:
    return int(value) if value is not None else None


def _string_list(value: Any) -> list[str]:
    return [str(item) for item in value or []]
```

Use those helpers so the returned row contains:

```python
"collectible": bool(row.get("collectible", False)),
"classes": _string_list(row.get("classes", [])),
"attack": _int_or_none(row.get("attack")),
"health": _int_or_none(row.get("health")),
"durability": _int_or_none(row.get("durability")),
"spell_school": str(row.get("spellSchool", row.get("spell_school", "")) or ""),
"race": str(row.get("race", "")) if row.get("race") is not None else None,
"races": _string_list(row.get("races", [])),
"overload": _int_or_none(row.get("overload")),
"spell_damage": _int_or_none(row.get("spellDamage", row.get("spell_damage"))),
"targeting_arrow_text": str(row.get("targetingArrowText", row.get("targeting_arrow_text", "")) or ""),
```

Keep existing keys unchanged for backward compatibility.

- [ ] **Step 4: Run focused tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_hearthstonejson.py -q
```

Expected: all HearthstoneJSON tests pass.

- [ ] **Step 5: Commit**

```powershell
git add src/hsconfig/hearthstonejson.py tests/test_hearthstonejson.py
git commit -m "feat: preserve richer hearthstonejson semantics"
```

---

### Task 3: Add Central Static Semantic Inference

**Files:**
- Create: `src/hsconfig/static_semantics.py`
- Modify: `src/hsconfig/card_metadata.py`
- Test: `tests/test_static_semantics.py`
- Test: `tests/test_card_metadata.py`

**Interfaces:**
- Produces: `infer_static_semantics(card: Mapping[str, Any]) -> dict[str, Any]`
- Produces: semantic result shape with keys `families: list[str]`, `evidence: list[dict[str, str]]`, and `warning_only: list[str]`
- Consumes: normalized card metadata rows from `hydrate_card_metadata()`

- [ ] **Step 1: Add failing static semantics tests**

Create `tests/test_static_semantics.py`:

```python
from hsconfig.static_semantics import infer_static_semantics


def _families(card):
    return set(infer_static_semantics(card)["families"])


def test_infers_mechanics_from_type_mechanics_referenced_tags_and_text():
    card = {
        "id": "TEST_001",
        "type": "WEAPON",
        "mechanics": ["TRADEABLE"],
        "referenced_tags": ["OVERLOAD"],
        "text": "Battlecry: Discover a spell. Dredge. Silence an enemy minion.",
    }

    families = _families(card)

    assert {"weapon", "tradeable", "overload", "battlecry", "discover", "dredge", "silence"} <= families


def test_infers_location_secret_and_generated_entity_patterns():
    card = {
        "id": "TEST_002",
        "type": "LOCATION",
        "mechanics": ["SECRET"],
        "text": "Secret: When your opponent plays a minion, summon a random minion.",
    }

    families = _families(card)

    assert {"location", "secret", "summon", "generated_entity", "generated_entity_random_pool"} <= families


def test_infers_hero_power_transform_and_start_of_game_from_tags_and_text():
    card = {
        "id": "SW_448",
        "type": "MINION",
        "referenced_tags": ["START_OF_GAME_KEYWORD"],
        "text": "Start of Game: If the spells in your deck are all Shadow, enter Shadowform.",
    }

    families = _families(card)

    assert {"start_of_game", "shadowform", "hero_power", "hero_power_transform"} <= families


def test_warning_only_contains_unlowerable_choice_surfaces():
    result = infer_static_semantics(
        {
            "id": "TEST_003",
            "type": "SPELL",
            "text": "Dredge. Tradeable. Choose One - Summon a minion; or Draw a card.",
        }
    )

    assert "dredge" in result["families"]
    assert "tradeable" in result["families"]
    assert "choose_one" in result["families"]
    assert "dredge" in result["warning_only"]
    assert "tradeable" in result["warning_only"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_static_semantics.py -q
```

Expected: import fails because `hsconfig.static_semantics` does not exist.

- [ ] **Step 3: Implement `src/hsconfig/static_semantics.py`**

Create this file:

```python
from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any


TEXT_PATTERNS: dict[str, tuple[str, ...]] = {
    "battlecry": ("battlecry",),
    "deathrattle": ("deathrattle",),
    "discover": ("discover",),
    "dredge": ("dredge",),
    "tradeable": ("tradeable",),
    "overload": ("overload",),
    "freeze": ("freeze", "frozen"),
    "lifesteal": ("lifesteal",),
    "reborn": ("reborn",),
    "rush": ("rush",),
    "charge": ("charge",),
    "taunt": ("taunt",),
    "secret": ("secret",),
    "draw": ("draw", "draws", "drawn"),
    "heal": ("heal", "healed", "healing", "restore health"),
    "damage": ("damage", "deal damage", "deals damage"),
    "summon": ("summon", "summons", "summoned"),
    "recruit": ("recruit", "from your deck"),
    "discard": ("discard", "discards"),
    "silence": ("silence", "silences"),
    "transform": ("transform", "transforms", "becomes"),
    "destroy": ("destroy", "destroys"),
    "choose_one": ("choose one",),
    "aura": ("adjacent", "your other", "your minions have", "whenever"),
}

TYPE_TO_FAMILY = {
    "HERO_POWER": "hero_power",
    "LOCATION": "location",
    "MINION": "minion",
    "SPELL": "spell",
    "WEAPON": "weapon",
}

REFERENCED_TAG_TO_FAMILY = {
    "BATTLECRY": "battlecry",
    "DEATHRATTLE": "deathrattle",
    "DISCOVER": "discover",
    "DREDGE": "dredge",
    "TRADEABLE": "tradeable",
    "OVERLOAD": "overload",
    "FREEZE": "freeze",
    "LIFESTEAL": "lifesteal",
    "REBORN": "reborn",
    "RUSH": "rush",
    "CHARGE": "charge",
    "TAUNT": "taunt",
    "SECRET": "secret",
    "START_OF_GAME_KEYWORD": "start_of_game",
}

WARNING_ONLY_MECHANICS = {
    "board_position",
    "dredge",
    "generated_entity_random_pool",
    "location_activation",
    "secret_timing",
    "tradeable",
}


def infer_static_semantics(card: Mapping[str, Any]) -> dict[str, Any]:
    families: set[str] = set()
    evidence: list[dict[str, str]] = []

    card_type = str(card.get("type", "") or "").upper()
    if card_type in TYPE_TO_FAMILY:
        _add(families, evidence, TYPE_TO_FAMILY[card_type], "type", card_type)

    for mechanic in card.get("mechanics", []) or []:
        family = _normalize_family(str(mechanic))
        _add(families, evidence, family, "mechanics", str(mechanic))

    for tag in card.get("referenced_tags", card.get("referencedTags", [])) or []:
        tag_text = str(tag).upper()
        family = REFERENCED_TAG_TO_FAMILY.get(tag_text)
        if family:
            _add(families, evidence, family, "referenced_tags", tag_text)

    text = _plain_text(f"{card.get('name', '')} {card.get('text', '')} {card.get('targeting_arrow_text', '')}")
    lowered = text.lower()
    for family, patterns in TEXT_PATTERNS.items():
        if any(_contains(lowered, pattern) for pattern in patterns):
            _add(families, evidence, family, "text", next(pattern for pattern in patterns if _contains(lowered, pattern)))

    if card.get("overload") is not None:
        _add(families, evidence, "overload", "overload", str(card["overload"]))
    if card.get("spell_damage") is not None:
        _add(families, evidence, "spell_damage", "spell_damage", str(card["spell_damage"]))
    if card.get("hero_power_dbf_id") is not None:
        _add(families, evidence, "hero_power", "heroPowerDbfId", str(card["hero_power_dbf_id"]))

    if "start of game" in lowered:
        _add(families, evidence, "start_of_game", "text", "start of game")
    if "shadowform" in lowered:
        _add(families, evidence, "shadowform", "text", "shadowform")
        _add(families, evidence, "hero_power", "text", "shadowform")
        if "start_of_game" in families:
            _add(families, evidence, "hero_power_transform", "text", "shadowform start of game")
    if "random" in lowered and ("summon" in families or "add" in lowered or "generate" in lowered):
        _add(families, evidence, "generated_entity", "text", "random generated entity")
        _add(families, evidence, "generated_entity_random_pool", "text", "random generated entity")
    if "secret" in families:
        _add(families, evidence, "secret_timing", "mechanic", "secret")
    if "location" in families:
        _add(families, evidence, "location_activation", "type", "LOCATION")

    warning_only = sorted(families & WARNING_ONLY_MECHANICS)
    return {
        "families": sorted(families),
        "evidence": _dedupe_evidence(evidence),
        "warning_only": warning_only,
    }


def _add(families: set[str], evidence: list[dict[str, str]], family: str, source: str, value: str) -> None:
    if not family:
        return
    families.add(family)
    evidence.append({"family": family, "source": source, "value": value})


def _normalize_family(value: str) -> str:
    return value.strip().lower().replace(" ", "_")


def _plain_text(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).replace("$", "")


def _contains(haystack: str, needle: str) -> bool:
    if " " in needle:
        return needle in haystack
    return bool(re.search(rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])", haystack))


def _dedupe_evidence(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str, str]] = set()
    deduped = []
    for row in rows:
        key = (row["family"], row["source"], row["value"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return sorted(deduped, key=lambda row: (row["family"], row["source"], row["value"]))
```

- [ ] **Step 4: Integrate with `card_metadata.py`**

Replace `assign_mechanic_families()` internals so it delegates to the new module:

```python
from hsconfig.static_semantics import infer_static_semantics


def assign_mechanic_families(card: dict[str, Any]) -> list[str]:
    return infer_static_semantics(card)["families"]
```

Inside `hydrate_card_metadata()`, after `merged["mechanic_families"] = ...`, add:

```python
semantic_result = infer_static_semantics(merged)
merged["mechanic_families"] = semantic_result["families"]
merged["static_semantic_evidence"] = semantic_result["evidence"]
merged["warning_only_mechanics"] = semantic_result["warning_only"]
```

- [ ] **Step 5: Add metadata preservation test**

Append this test to `tests/test_card_metadata.py`:

```python
def test_hydrate_card_metadata_adds_static_semantic_evidence():
    snapshot = hydrate_card_metadata(
        cards=[{"card_id": "TEST_001", "dbf_id": 1, "count": 1}],
        source_records={
            "TEST_001": {
                "name": "Test Dredge",
                "type": "SPELL",
                "text": "Dredge. Tradeable.",
                "mechanics": ["TRADEABLE"],
            }
        },
    )

    card = snapshot["cards"][0]

    assert "dredge" in card["mechanic_families"]
    assert "tradeable" in card["mechanic_families"]
    assert "dredge" in card["warning_only_mechanics"]
    assert any(row["family"] == "tradeable" for row in card["static_semantic_evidence"])
```

- [ ] **Step 6: Run focused tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_static_semantics.py tests/test_card_metadata.py -q
```

Expected: all selected tests pass.

- [ ] **Step 7: Commit**

```powershell
git add src/hsconfig/static_semantics.py src/hsconfig/card_metadata.py tests/test_static_semantics.py tests/test_card_metadata.py
git commit -m "feat: add static hearthstone semantic inference"
```

---

### Task 4: Merge Static Semantics Through Enrichment and Mechanic Support

**Files:**
- Modify: `src/hsconfig/semantic_enrichment.py`
- Modify: `src/hsconfig/mechanic_support.py`
- Test: `tests/test_semantic_enrichment.py`
- Test: `tests/test_mechanic_support.py`

**Interfaces:**
- Consumes: `infer_static_semantics(card) -> dict[str, Any]`
- Produces: enriched cards whose `semantic_families`, `static_semantic_evidence`, and `warning_only_mechanics` survive HearthstoneJSON hydration.
- Produces: `support_for_roles(roles: Iterable[str]) -> list[dict[str, Any]]` that covers every new family.

- [ ] **Step 1: Add failing enrichment test for static semantics after HearthstoneJSON merge**

Append this test to `tests/test_semantic_enrichment.py`:

```python
def test_enrichment_merges_static_semantics_from_hjson_fields():
    enriched = enrich_card_metadata(
        {
            "cards": [
                {
                    "card_id": "TEST_001",
                    "dbf_id": 1001,
                    "name": "TEST_001",
                    "type": "UNKNOWN",
                    "text": "",
                    "mechanic_families": [],
                    "metadata_status": "source_record",
                }
            ]
        },
        hearthstonejson_cards=[
            {
                "id": "TEST_001",
                "dbfId": 1001,
                "name": "Test Location",
                "type": "LOCATION",
                "text": "Choose One - Summon a random minion; or Draw a card.",
                "mechanics": [],
                "referencedTags": ["CHOOSE_ONE"],
            }
        ],
    )

    card = enriched["cards"][0]

    assert "location" in card["semantic_families"]
    assert "choose_one" in card["semantic_families"]
    assert "generated_entity_random_pool" in card["semantic_families"]
    assert "location_activation" in card["warning_only_mechanics"]
```

- [ ] **Step 2: Add failing mechanic support test for new families**

Append this test to `tests/test_mechanic_support.py`:

```python
def test_mechanic_support_covers_static_semantic_families_without_blocking():
    rows = support_for_roles(
        [
            "choose_one",
            "spell_damage",
            "start_of_game",
            "location_activation",
            "secret_timing",
            "generated_entity_random_pool",
        ]
    )
    by_mechanic = {row["mechanic"]: row for row in rows}

    assert by_mechanic["choose_one"]["support_level"] == "direct"
    assert by_mechanic["spell_damage"]["support_level"] in {"partial", "warning_only"}
    assert by_mechanic["start_of_game"]["support_level"] in {"partial", "warning_only"}
    assert by_mechanic["location_activation"]["support_level"] == "warning_only"
    assert by_mechanic["secret_timing"]["support_level"] == "warning_only"
    assert by_mechanic["generated_entity_random_pool"]["support_level"] == "warning_only"
```

- [ ] **Step 3: Run tests to verify they fail**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_semantic_enrichment.py::test_enrichment_merges_static_semantics_from_hjson_fields tests/test_mechanic_support.py::test_mechanic_support_covers_static_semantic_families_without_blocking -q
```

Expected: fail because enrichment does not yet expose all static semantic fields or support registry lacks `spell_damage` / `start_of_game`.

- [ ] **Step 4: Integrate static semantics in `semantic_enrichment.py`**

Import and use the new function:

```python
from hsconfig.static_semantics import infer_static_semantics
```

After `_merge_hjson()` and before assigning `enriched["semantic_families"]`, merge the static result:

```python
static_semantics = infer_static_semantics(enriched)
semantic_families.update(static_semantics["families"])
enriched["static_semantic_evidence"] = static_semantics["evidence"]
enriched["warning_only_mechanics"] = static_semantics["warning_only"]
```

Keep the existing Shadowform-specific deckwide effect logic unchanged.

- [ ] **Step 5: Add missing mechanic support rows**

In `src/hsconfig/mechanic_support.py`, add these entries to `MECHANIC_SUPPORT`:

```python
"spell_damage": {
    "support_level": "partial",
    "normal_path_surfaces": ["CARDID.json:BeforePlayCardBonus", "GlobalValues.json:deck_posture"],
    "warning_boundary": "Spell-damage synergy can be encouraged, but exact hand and spell sequencing remains source-dependent.",
},
"start_of_game": {
    "support_level": "partial",
    "normal_path_surfaces": ["GlobalValues.json:deck_posture", "CARDID.json:resolved_identity"],
    "warning_boundary": "Start-of-game effects are represented through deck posture or exact linked entities, not by executing a runtime action.",
},
```

- [ ] **Step 6: Run focused tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_semantic_enrichment.py tests/test_mechanic_support.py -q
```

Expected: all selected tests pass.

- [ ] **Step 7: Commit**

```powershell
git add src/hsconfig/semantic_enrichment.py src/hsconfig/mechanic_support.py tests/test_semantic_enrichment.py tests/test_mechanic_support.py
git commit -m "feat: route static semantics through mechanic support"
```

---

### Task 5: Emit a Semantic Enrichment Report and Summarize It in Operator Output

**Files:**
- Modify: `src/hsconfig/package_builder.py`
- Modify: `src/hsconfig/operator_summary.py`
- Test: `tests/test_operator_summary.py`
- Test: `tests/test_prepare_cli.py`
- Test: `tests/test_universal_wild_no_block_matrix.py`

**Interfaces:**
- Produces: `reports/semantic_enrichment_report.json`
- Produces: `operator_summary["semantic_enrichment_summary"]` with non-blocking counts.
- Consumes: enriched card metadata from the prepare pipeline.

- [ ] **Step 1: Add failing operator summary unit test**

Append this test to `tests/test_operator_summary.py`:

```python
def test_operator_summary_exposes_static_semantic_warning_counts():
    summary = build_operator_summary(
        deck_name="deck",
        deck_code="fixture",
        technical_validation={"status": "passed"},
        guide_source_depth={"source_depth_status": "static_semantics_only", "claim_count": 0},
        config_readiness_report={
            "summary": {
                "mechanic_visibility": {
                    "non_blocking": True,
                    "bucket_counts": {
                        "direct": 2,
                        "identity_gated_direct": 1,
                        "partial": 3,
                        "warning_only": 4,
                    },
                    "mechanics_by_bucket": {
                        "direct": ["battlecry"],
                        "identity_gated_direct": ["hero_power_transform"],
                        "partial": ["deathrattle"],
                        "warning_only": ["dredge", "tradeable"],
                    },
                    "warning_only_card_count": 2,
                    "first_warning_boundary": {
                        "mechanic": "dredge",
                        "warning_boundary": "Dredge option selection has no documented normal-path VisionAI choice surface.",
                    },
                    "warning_boundaries": [],
                }
            }
        },
    )

    assert summary["runtime_apply_allowed"] is True
    assert summary["mechanic_visibility_summary"]["non_blocking"] is True
    assert summary["mechanic_visibility_summary"]["bucket_counts"]["warning_only"] == 4
    assert summary["operator_guidance"]["next_action"] in {
        "READY_TO_APPLY_WITH_WARNINGS",
        "READY_TO_APPLY_OR_HANDOFF",
    }
```

- [ ] **Step 2: Add failing prepare CLI report existence assertion**

In the existing prepare CLI test that builds a package, add:

```python
semantic_report = json.loads((out / "reports" / "semantic_enrichment_report.json").read_text(encoding="utf-8"))
assert semantic_report["non_blocking"] is True
assert "cards" in semantic_report
assert "summary" in semantic_report
```

Use the local variable names already present in that test. If no single package-building test is short enough, add this assertion to `tests/test_universal_wild_no_block_matrix.py` after the package output is created.

- [ ] **Step 3: Run tests to verify report assertion fails**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_operator_summary.py tests/test_prepare_cli.py tests/test_universal_wild_no_block_matrix.py -q
```

Expected: fail because `semantic_enrichment_report.json` is not emitted or the summary key is missing.

- [ ] **Step 4: Emit `semantic_enrichment_report.json` in `package_builder.py`**

Find the prepare flow after enriched metadata is available. Write a report with this shape:

```python
semantic_enrichment_report = {
    "schema_version": 1,
    "non_blocking": True,
    "summary": {
        "total_cards": len(enriched_metadata.get("cards", [])),
        "cards_with_warning_only_mechanics": sum(
            1 for card in enriched_metadata.get("cards", []) if card.get("warning_only_mechanics")
        ),
        "deckwide_effect_count": len(enriched_metadata.get("deckwide_effects", [])),
    },
    "deckwide_effects": enriched_metadata.get("deckwide_effects", []),
    "cards": [
        {
            "card_id": str(card.get("card_id", "")),
            "name": str(card.get("name", "")),
            "semantic_families": list(card.get("semantic_families", card.get("mechanic_families", [])) or []),
            "warning_only_mechanics": list(card.get("warning_only_mechanics", []) or []),
            "static_semantic_evidence": list(card.get("static_semantic_evidence", []) or []),
        }
        for card in enriched_metadata.get("cards", [])
    ],
}
```

Write it through the repo's existing JSON writer to `reports/semantic_enrichment_report.json`, and add that path to generated report metadata only if the prepare flow tracks report outputs separately from runtime files.

- [ ] **Step 5: Keep apply permission independent of semantic report**

Do not add semantic report fields to `evaluate_apply_gate()`. The apply gate must continue to read only `operator_summary.json`, package structure, actual runtime files, and summary generated runtime files.

- [ ] **Step 6: Run focused tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_operator_summary.py tests/test_prepare_cli.py tests/test_universal_wild_no_block_matrix.py -q
```

Expected: all selected tests pass.

- [ ] **Step 7: Commit**

```powershell
git add src/hsconfig/package_builder.py src/hsconfig/operator_summary.py tests/test_operator_summary.py tests/test_prepare_cli.py tests/test_universal_wild_no_block_matrix.py
git commit -m "feat: report nonblocking static semantic coverage"
```

---

### Task 6: Add Focused Wild Mechanic Micro-Fixtures

**Files:**
- Create: `tests/test_static_semantic_micro_fixtures.py`
- Modify: `tests/test_universal_wild_no_block_matrix.py`

**Interfaces:**
- Consumes: `infer_static_semantics()`
- Consumes: normal `hsconfig prepare` CLI through `main([...])`
- Produces: targeted proof that important Wild mechanics are visible without expanding the repository with many full deck fixtures.

- [ ] **Step 1: Create micro-fixture tests**

Create `tests/test_static_semantic_micro_fixtures.py`:

```python
import pytest

from hsconfig.static_semantics import infer_static_semantics


CASES = [
    (
        "secret_hidden_interrupt",
        {"type": "SPELL", "mechanics": ["SECRET"], "text": "Secret: When your opponent plays a minion, counter it."},
        {"secret", "secret_timing"},
        {"secret_timing"},
    ),
    (
        "dredge_tradeable",
        {"type": "SPELL", "mechanics": ["TRADEABLE"], "text": "Dredge. Tradeable."},
        {"dredge", "tradeable"},
        {"dredge", "tradeable"},
    ),
    (
        "deathrattle_reborn",
        {"type": "MINION", "mechanics": ["DEATHRATTLE", "REBORN"], "text": "Deathrattle: Summon a minion."},
        {"minion", "deathrattle", "reborn", "summon"},
        set(),
    ),
    (
        "recruit_from_deck",
        {"type": "SPELL", "text": "Recruit a minion from your deck."},
        {"spell", "recruit"},
        set(),
    ),
    (
        "location_activation",
        {"type": "LOCATION", "text": "Give a minion +2 Attack."},
        {"location", "location_activation"},
        {"location_activation"},
    ),
    (
        "discard_destroy_silence_transform",
        {"type": "SPELL", "text": "Discard a card. Destroy a minion. Silence it, then transform it."},
        {"spell", "discard", "destroy", "silence", "transform"},
        set(),
    ),
]


@pytest.mark.parametrize(("name", "card", "expected_families", "expected_warning_only"), CASES)
def test_static_semantic_micro_fixture(name, card, expected_families, expected_warning_only):
    result = infer_static_semantics({"id": name, **card})

    assert expected_families <= set(result["families"])
    assert expected_warning_only <= set(result["warning_only"])
```

- [ ] **Step 2: Run micro-fixture tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_static_semantic_micro_fixtures.py -q
```

Expected: pass after Task 3 and Task 4.

- [ ] **Step 3: Strengthen full deck no-block matrix**

In `tests/test_universal_wild_no_block_matrix.py`, after reading `operator`, add:

```python
assert operator["mechanic_visibility_summary"]["non_blocking"] is True
assert operator["runtime_apply_allowed"] is True
```

If Task 5 added `semantic_enrichment_report.json` to this test, also assert:

```python
assert semantic_report["non_blocking"] is True
```

- [ ] **Step 4: Run deck matrix and micro-fixtures**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_static_semantic_micro_fixtures.py tests/test_universal_wild_no_block_matrix.py -q
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit**

```powershell
git add tests/test_static_semantic_micro_fixtures.py tests/test_universal_wild_no_block_matrix.py
git commit -m "test: cover wild mechanic semantics without blocking"
```

---

### Task 7: Update Operator Docs and Installed Skill Copy

**Files:**
- Modify: `docs/operator/README.md`
- Modify through script: `C:\Users\darbo\.codex\skills\hsconfig\SKILL.md`
- Test: `tests/test_docs_active_path.py`
- Test: `tests/test_skill_sync.py`

**Interfaces:**
- Consumes: current normal workflow in `docs/operator/README.md`
- Produces: operator docs and installed skill guidance that describe load-safe warnings, semantic report, and the no-block contract.

- [ ] **Step 1: Add docs test expectation**

Extend `tests/test_docs_active_path.py` with assertions equivalent to:

```python
def test_operator_docs_describe_no_block_static_semantics():
    text = Path("docs/operator/README.md").read_text(encoding="utf-8")

    assert "semantic_enrichment_report.json" in text
    assert "warning-only mechanics do not block load-safe apply" in text
    assert "GlobalValues.json" in text
    assert "Mulligan.json" in text
```

If `Path` is not imported in that file, add `from pathlib import Path`.

- [ ] **Step 2: Run docs test to verify it fails**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_docs_active_path.py::test_operator_docs_describe_no_block_static_semantics -q
```

Expected: fail until docs are updated.

- [ ] **Step 3: Update `docs/operator/README.md`**

Add a compact section under the normal `prepare`/review path:

```markdown
### Load-Safe Warnings

HSConfig separates runtime load safety from semantic strength. A package is load-safe when the runtime JSON is valid, `GlobalValues.json` and `Mulligan.json` exist for the deck, normal-path forbidden surfaces are absent, and `reports/operator_summary.json` reports `technical_status=VALID_PACKAGE`.

Warning-only mechanics do not block load-safe apply. Open `reports/semantic_enrichment_report.json` when `operator_summary.json` points to static or warning-only mechanic coverage. Missing per-card CardID richness is a config quality gap, not a runtime package blocker.
```

- [ ] **Step 4: Sync installed skill**

Run:

```powershell
python scripts/sync_installed_skill.py
```

Expected: script completes successfully and updates the installed skill copy only if repo skill text changed.

- [ ] **Step 5: Run docs and skill sync tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_docs_active_path.py tests/test_skill_sync.py -q
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit**

```powershell
git add docs/operator/README.md tests/test_docs_active_path.py C:/Users/darbo/.codex/skills/hsconfig/SKILL.md
git commit -m "docs: document no-block static semantics workflow"
```

If the installed skill file is outside the repository and cannot be committed, commit only the repo files and mention the synced external skill in the final implementation summary.

---

### Task 8: Full Verification and GitHub Finish

**Files:**
- No planned source edits.
- Review: all modified files from previous tasks.

**Interfaces:**
- Consumes: all tasks above.
- Produces: verified branch ready for merge or direct push, depending on current branch policy.

- [ ] **Step 1: Run targeted no-block semantic suite**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_apply_gate.py tests/test_validate_package.py tests/test_hearthstonejson.py tests/test_static_semantics.py tests/test_static_semantic_micro_fixtures.py tests/test_card_metadata.py tests/test_semantic_enrichment.py tests/test_mechanic_support.py tests/test_operator_summary.py tests/test_universal_wild_no_block_matrix.py -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run broader suite**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest -q
```

Expected: all tests pass. If runtime exceeds the normal terminal window, rerun failing or interrupted subsets with a longer timeout before claiming success.

- [ ] **Step 3: Scan for stale blocking language**

Run:

```powershell
rg -n "missing_cardid_runtime_file|missing at least one per-card CardID runtime file|must have.*CardID|blocks load-safe" src tests docs
```

Expected: no active code or docs claim per-card CardID absence blocks load-safe apply. Test names may mention old behavior only if they assert it no longer occurs.

- [ ] **Step 4: Review diff**

Run:

```powershell
git diff -- src tests docs
git status --short --branch
```

Expected: only planned files changed plus any pre-existing untracked research directories left untouched.

- [ ] **Step 5: Commit any final polish**

If Step 4 shows final doc/test polish changes:

```powershell
git add src tests docs
git commit -m "chore: verify no-block semantic expansion"
```

- [ ] **Step 6: Push**

Run:

```powershell
git push origin main
```

Expected: `main` is up to date on GitHub.

---

## Self-Review

- Spec coverage: The plan covers no-block runtime gates, richer HearthstoneJSON fields, static semantic inference, mechanic support lanes, semantic reporting, Wild mechanic fixtures, docs, installed skill sync, and final verification.
- Placeholder scan: No task relies on deferred unspecified work; each test and function signature is named.
- Type consistency: `infer_static_semantics(card: Mapping[str, Any]) -> dict[str, Any]` is introduced in Task 3 and consumed consistently in later tasks.
- Boundary check: The plan keeps HSConfig pre-run only and does not add replay, winrate, or HSTuner responsibilities.

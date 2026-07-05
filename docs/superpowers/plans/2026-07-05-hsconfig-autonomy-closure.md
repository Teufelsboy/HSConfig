# HSConfig Autonomy Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make HSConfig's normal path truly autonomous: deck name + deck code + runtime root produce a real CardID-backed, validated HearthRanger CustomConfig package and apply it with a correct `deck_config.ini` mapping.

**Architecture:** Keep HSConfig lean and deterministic. Add a focused deckstring decode module that turns Hearthstone deck codes into exact CardIDs and card metadata, wire it into `hsconfig build` as the default path, keep explicit `--cards-json` / `--claims-json` as expert overrides, and harden runtime apply to write both the config folder and the activation mapping.

**Tech Stack:** Python 3.11, `hearthstone` package for HearthSim deckstring/CardXML decode, existing stdlib JSON/pathlib modules, pytest, existing HSConfig CLI and compilers.

---

## Scope

This plan closes the gap found in the audit:

- `hsconfig build --deck-name "ShadowPriest" --deck-code "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA="` must use the real deck code by default, not deterministic placeholder cards.
- Placeholder cards remain available only through an explicit CI/debug flag.
- The build reports must preserve decode evidence: hero, format, DBF card list, CardID map, and card count.
- `hsconfig apply` must update `CustomConfig/deck_config.ini` with the exact deck name to config directory mapping while preserving unrelated mappings.
- The existing ShadowPriest E2E path must work without hand-written `cards.json`.

Out of scope:

- replay parsing
- winrate analysis
- HSTuner sessions
- runtime log analysis
- automatic online guide scraping inside the CLI
- broad CardID behavior redesign

Guide/source research remains Codex/skill responsibility and continues to feed `--claims-json`. This keeps the CLI deterministic and the skill flexible.

## File Structure

- Modify: `pyproject.toml`
  - Add the `hearthstone` dependency.
- Create: `src/hsconfig/deckstring_decode.py`
  - Decode Hearthstone deck codes with HearthSim, map DBF IDs to CardIDs, and expose report payloads.
- Modify: `src/hsconfig/cli.py`
  - Add `--allow-placeholder`.
  - Use real deckstring decode when `--cards-json` is absent.
  - Write decode reports when deckstring decode is used.
- Modify: `src/hsconfig/deck_identity.py`
  - Preserve hero and format already produced by decode.
- Modify: `src/hsconfig/runtime_apply.py`
  - Write/update `CustomConfig/deck_config.ini`.
  - Preserve unrelated mappings.
- Modify: `src/hsconfig/io.py`
  - Add a small text hashing helper only if needed by runtime apply.
- Modify: `README.md`
  - Make deckcode-only build the normal path.
  - Move placeholder path to expert/debug section.
- Modify: `.agents/skills/hsconfig/SKILL.md`
  - State that deckcode decode is normal and `cards-json` is only an override.
- Modify: `.agents/skills/hsconfig/references/workflow.md`
  - Align workflow with the new default path.
- Tests:
  - Create `tests/test_deckstring_decode.py`.
  - Modify `tests/test_cli.py`.
  - Modify `tests/test_e2e_preview.py`.
  - Modify `tests/test_runtime_apply.py`.
  - Modify `tests/test_skill_files.py` if wording assertions need adjustment.

## Task 1: Add HearthSim Deckstring Decode Core

**Files:**
- Modify: `pyproject.toml`
- Create: `src/hsconfig/deckstring_decode.py`
- Test: `tests/test_deckstring_decode.py`

- [ ] **Step 1: Add dependency test expectation**

Create `tests/test_deckstring_decode.py` with these tests:

```python
from hsconfig.deckstring_decode import decode_deck_code


SHADOWPRIEST_CODE = (
    "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/"
    "KgG17oG1cEGAAA="
)


def test_decode_shadowpriest_deck_code_to_exact_cardids():
    decoded = decode_deck_code(SHADOWPRIEST_CODE)

    assert decoded["hero_dbf_id"] == 813
    assert decoded["format"] == "FT_WILD"
    assert decoded["card_count_total"] == 30
    assert decoded["unresolved_card_count"] == 0
    assert {card["card_id"] for card in decoded["cards"]} == {
        "CFM_637",
        "DRG_056",
        "DS1_233",
        "GVG_009",
        "NX2_019",
        "REV_290",
        "SCH_514",
        "SW_444",
        "SW_446",
        "SW_448",
        "TOY_381",
        "TOY_518",
        "VAC_419",
        "VAC_512",
        "WON_065",
        "YOD_032",
    }
    assert not any(card["card_id"].startswith("HSC_") for card in decoded["cards"])


def test_decode_receipt_contains_dbf_and_cardid_map():
    decoded = decode_deck_code(SHADOWPRIEST_CODE)

    receipt = decoded["deckstring_decode_receipt"]
    assert receipt["decoder"] == "hearthstone.deckstrings"
    assert receipt["hero_dbf_id"] == 813
    assert receipt["format"] == "FT_WILD"
    assert receipt["card_count_total"] == 30

    card_id_map = decoded["card_id_map"]
    assert card_id_map["545"]["card_id"] == "DS1_233"
    assert card_id_map["64429"]["card_id"] == "SW_446"
```

- [ ] **Step 2: Run the failing tests**

Run:

```powershell
pytest tests\test_deckstring_decode.py -q
```

Expected: fail with `ModuleNotFoundError: No module named 'hsconfig.deckstring_decode'`.

- [ ] **Step 3: Add dependency**

Modify `pyproject.toml`:

```toml
[project]
name = "hsconfig"
version = "0.1.0"
description = "Guide-aligned HearthRanger VisionAI CustomConfig generator"
readme = "README.md"
requires-python = ">=3.11"
dependencies = [
  "hearthstone>=9.0.0",
]
```

- [ ] **Step 4: Implement `deckstring_decode.py`**

Create `src/hsconfig/deckstring_decode.py`:

```python
from __future__ import annotations

from typing import Any

from hearthstone import cardxml
from hearthstone.deckstrings import FormatType, parse_deckstring


TYPE_NAMES = {
    3: "HERO",
    4: "MINION",
    5: "SPELL",
    7: "WEAPON",
    10: "HERO_POWER",
    39: "LOCATION",
}

MECHANIC_ATTRS = (
    "battlecry",
    "charge",
    "deathrattle",
    "discover",
    "dredge",
    "lifesteal",
    "overload",
    "reborn",
    "rush",
    "secret",
    "taunt",
    "tradeable",
)


def decode_deck_code(deck_code: str) -> dict[str, Any]:
    parsed = parse_deckstring(deck_code)
    cards_db, _ = cardxml.load_dbf()

    cards: list[dict[str, Any]] = []
    card_id_map: dict[str, dict[str, Any]] = {}
    unresolved: list[dict[str, Any]] = []

    for dbf_id, count in sorted(parsed.cards, key=lambda row: row[0]):
        row = _card_row(cards_db, dbf_id, count)
        cards.append(row)
        card_id_map[str(dbf_id)] = {
            "dbf_id": dbf_id,
            "card_id": row["card_id"],
            "name": row["name"],
            "count": count,
        }
        if row["metadata_status"] != "source_record":
            unresolved.append({"dbf_id": dbf_id, "count": count})

    hero_dbf_id = parsed.heroes[0] if parsed.heroes else None
    format_name = _format_name(parsed.format)
    card_count_total = sum(card["count"] for card in cards)
    receipt = {
        "decoder": "hearthstone.deckstrings",
        "deck_code_length": len(deck_code),
        "format": format_name,
        "hero_dbf_id": hero_dbf_id,
        "card_count_total": card_count_total,
        "unique_card_count": len(cards),
        "unresolved_card_count": len(unresolved),
        "unresolved_cards": unresolved,
    }

    return {
        "cards": cards,
        "hero_dbf_id": hero_dbf_id,
        "format": format_name,
        "card_count_total": card_count_total,
        "unresolved_card_count": len(unresolved),
        "deckstring_decode_receipt": receipt,
        "card_id_map": card_id_map,
    }


def _card_row(cards_db: dict[int, Any], dbf_id: int, count: int) -> dict[str, Any]:
    card = cards_db.get(dbf_id)
    if card is None:
        return {
            "card_id": f"UNRESOLVED_DBF_{dbf_id}",
            "dbf_id": dbf_id,
            "count": count,
            "name": f"Unresolved DBF {dbf_id}",
            "cost": None,
            "type": "UNKNOWN",
            "card_class": None,
            "text": "",
            "mechanics": [],
            "metadata_status": "missing_source_record",
        }

    mechanics = [name for name in MECHANIC_ATTRS if getattr(card, name, None)]
    return {
        "card_id": str(card.card_id),
        "dbf_id": int(dbf_id),
        "count": int(count),
        "name": str(card.english_name or card.name or card.card_id),
        "cost": int(card.cost) if card.cost is not None else None,
        "type": TYPE_NAMES.get(int(card.type), str(card.type)),
        "card_class": str(card.card_class) if card.card_class is not None else None,
        "text": str(card.english_description or "").replace("\n", " "),
        "mechanics": sorted(set(mechanics)),
        "metadata_status": "source_record",
    }


def _format_name(format_value: FormatType | int | None) -> str | None:
    if format_value is None:
        return None
    try:
        return FormatType(format_value).name
    except ValueError:
        return str(format_value)
```

- [ ] **Step 5: Run the deckstring tests**

Run:

```powershell
pytest tests\test_deckstring_decode.py -q
```

Expected: `2 passed`.

- [ ] **Step 6: Commit**

Run:

```powershell
git add pyproject.toml src/hsconfig/deckstring_decode.py tests/test_deckstring_decode.py
git commit -m "feat: decode deck codes into card ids"
```

## Task 2: Make Real Deck Decode The Default Build Path

**Files:**
- Modify: `src/hsconfig/cli.py`
- Modify: `tests/test_cli.py`
- Modify: `tests/test_e2e_preview.py`
- Modify: `tests/test_runtime_apply.py`

- [ ] **Step 1: Add CLI tests for real decode and explicit placeholder mode**

Append to `tests/test_cli.py`:

```python
import json
from pathlib import Path

from hsconfig.cli import main


SHADOWPRIEST_CODE = (
    "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/"
    "KgG17oG1cEGAAA="
)


def test_build_without_cards_json_decodes_real_deck_code(tmp_path: Path, capsys):
    out = tmp_path / "shadowpriest"

    code = main(
        [
            "build",
            "--deck-name",
            "ShadowPriest",
            "--deck-code",
            SHADOWPRIEST_CODE,
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(out),
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    identity = json.loads((out / "reports" / "deck_identity.json").read_text(encoding="utf-8"))
    receipt = json.loads(
        (out / "reports" / "deckstring_decode_receipt.json").read_text(encoding="utf-8")
    )
    card_map = json.loads((out / "reports" / "card_id_map.json").read_text(encoding="utf-8"))

    assert code == 0
    assert payload["status"] == "passed"
    assert identity["card_count_total"] == 30
    assert identity["hero_dbf_id"] == 813
    assert receipt["format"] == "FT_WILD"
    assert card_map["64429"]["card_id"] == "SW_446"
    assert not any(card["card_id"].startswith("HSC_") for card in identity["cards"])


def test_build_placeholder_requires_explicit_flag(tmp_path: Path, capsys):
    out = tmp_path / "fixture"

    code = main(
        [
            "build",
            "--deck-name",
            "Fixture Deck",
            "--deck-code",
            "fixture-code",
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(out),
            "--allow-placeholder",
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    identity = json.loads((out / "reports" / "deck_identity.json").read_text(encoding="utf-8"))

    assert code == 0
    assert payload["status"] == "passed"
    assert any(card["card_id"].startswith("HSC_") for card in identity["cards"])
```

- [ ] **Step 2: Update existing fixture-code build tests**

Find tests that call `main(["build", "--deck-code", "fixture-code", "--allow-placeholder", "--json"])` and add `"--allow-placeholder"` to those argument lists. At minimum update:

- `tests/test_e2e_preview.py`
- `tests/test_runtime_apply.py`

The changed argument block should include:

```python
"--allow-placeholder",
"--json",
```

- [ ] **Step 3: Run CLI tests and verify failure before implementation**

Run:

```powershell
pytest tests\test_cli.py tests\test_e2e_preview.py tests\test_runtime_apply.py -q
```

Expected: fail because `--allow-placeholder` is not yet recognized and real decode reports are not yet written.

- [ ] **Step 4: Wire parser flags and real decode**

Modify `src/hsconfig/cli.py`.

Add import:

```python
from hsconfig.deckstring_decode import decode_deck_code
```

Add parser argument after `--claims-json`:

```python
build.add_argument("--allow-placeholder", action="store_true")
```

Change the cards load call in `_build` from:

```python
cards = _load_cards(args.cards_json, deck_name=args.deck_name, deck_code=args.deck_code)
```

to:

```python
cards_payload = _load_cards(
    args.cards_json,
    deck_name=args.deck_name,
    deck_code=args.deck_code,
    allow_placeholder=args.allow_placeholder,
)
cards = cards_payload["cards"]
```

Change `build_deck_identity` call to include decoded hero:

```python
deck_identity = build_deck_identity(
    deck_name=args.deck_name,
    deck_code=args.deck_code,
    cards=cards,
    hero_dbf_id=cards_payload.get("hero_dbf_id"),
    format=cards_payload.get("format"),
)
```

After existing report writes for `deck_identity.json`, add:

```python
if cards_payload.get("deckstring_decode_receipt") is not None:
    write_json(
        reports_dir / "deckstring_decode_receipt.json",
        cards_payload["deckstring_decode_receipt"],
    )
if cards_payload.get("card_id_map") is not None:
    write_json(reports_dir / "card_id_map.json", cards_payload["card_id_map"])
```

Set `manifest["format"]`:

```python
manifest["format"] = cards_payload.get("format")
```

- [ ] **Step 5: Replace `_load_cards` with an explicit source payload**

In `src/hsconfig/cli.py`, replace `_load_cards` with:

```python
def _load_cards(
    cards_json: str | None,
    *,
    deck_name: str,
    deck_code: str,
    allow_placeholder: bool,
) -> dict[str, Any]:
    if cards_json is None:
        if allow_placeholder:
            return {
                "cards": _placeholder_cards(deck_name=deck_name, deck_code=deck_code),
                "hero_dbf_id": None,
                "format": None,
                "deckstring_decode_receipt": None,
                "card_id_map": None,
                "card_source": "placeholder",
            }
        decoded = decode_deck_code(deck_code)
        return {
            "cards": decoded["cards"],
            "hero_dbf_id": decoded["hero_dbf_id"],
            "format": decoded["format"],
            "deckstring_decode_receipt": decoded["deckstring_decode_receipt"],
            "card_id_map": decoded["card_id_map"],
            "card_source": "deckstring",
        }

    payload = read_json(cards_json)
    if isinstance(payload, dict):
        payload = payload.get("cards")
    if not isinstance(payload, list):
        raise ValueError("--cards-json must contain a list or an object with a cards list")
    cards = [_normalize_card_input(card) for card in payload]
    if not cards:
        raise ValueError("--cards-json did not contain any cards")
    return {
        "cards": cards,
        "hero_dbf_id": None,
        "format": None,
        "deckstring_decode_receipt": None,
        "card_id_map": None,
        "card_source": "cards_json",
    }
```

- [ ] **Step 6: Run targeted tests**

Run:

```powershell
pytest tests\test_deckstring_decode.py tests\test_cli.py tests\test_e2e_preview.py tests\test_runtime_apply.py -q
```

Expected: all selected tests pass.

- [ ] **Step 7: Commit**

Run:

```powershell
git add src/hsconfig/cli.py tests/test_cli.py tests/test_e2e_preview.py tests/test_runtime_apply.py
git commit -m "feat: use real deck decode by default"
```

## Task 3: Preserve Deck Format In Deck Identity

**Files:**
- Modify: `src/hsconfig/deck_identity.py`
- Test: `tests/test_deck_identity.py`

- [ ] **Step 1: Add deck identity format test**

Append to `tests/test_deck_identity.py`:

```python
def test_build_deck_identity_preserves_format():
    identity = build_deck_identity(
        deck_name="Example",
        deck_code="test-code",
        cards=[{"card_id": "A", "dbf_id": 1, "count": 2}],
        hero_dbf_id=7,
        format="FT_WILD",
    )

    assert identity["format"] == "FT_WILD"
    assert identity["hero_dbf_id"] == 7
```

- [ ] **Step 2: Run the failing test**

Run:

```powershell
pytest tests\test_deck_identity.py -q
```

Expected: fail because `build_deck_identity()` does not accept `format`.

- [ ] **Step 3: Implement format preservation**

Modify `src/hsconfig/deck_identity.py`.

Change the function signature to:

```python
def build_deck_identity(
    *,
    deck_name: str,
    deck_code: str,
    cards: list[dict[str, Any]],
    hero_dbf_id: int | None = None,
    format: str | None = None,
) -> dict[str, Any]:
```

Add this field to the returned dict:

```python
"format": format,
```

- [ ] **Step 4: Run deck identity tests**

Run:

```powershell
pytest tests\test_deck_identity.py -q
```

Expected: all deck identity tests pass.

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/hsconfig/deck_identity.py tests/test_deck_identity.py
git commit -m "feat: preserve decoded deck format"
```

## Task 4: Add deck_config.ini Runtime Mapping

**Files:**
- Modify: `src/hsconfig/runtime_apply.py`
- Modify: `src/hsconfig/cli.py`
- Modify: `tests/test_runtime_apply.py`

- [ ] **Step 1: Add runtime apply mapping tests**

Append to `tests/test_runtime_apply.py`:

```python
def test_apply_package_writes_deck_config_mapping(tmp_path: Path):
    package = tmp_path / "package"
    package_deck = package / "CustomConfig" / "shadowpriest"
    write_json(package_deck / "GlobalValues.json", {"GameCardId": "GlobalValues", "ConfigComment": "new"})
    write_json(
        package_deck / "Mulligan.json",
        {"GameCardId": "Mulligan", "ConfigComment": "new", "Mulligan": {"values": []}},
    )
    write_json(
        package_deck / "SW_446.json",
        {"GameCardId": "SW_446", "ConfigComment": "new", "InHandPlayPriority": {"values": []}},
    )
    write_json(
        package / "reports" / "input_manifest.json",
        {
            "deck_name": "ShadowPriest",
            "deck_code": "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=",
            "runtime_root": str(tmp_path / "runtime"),
            "target_config_mode": "preview",
        },
    )

    runtime = tmp_path / "runtime"
    custom_config = runtime / "CustomConfig"
    custom_config.mkdir(parents=True)
    (custom_config / "deck_config.ini").write_text(
        "[CONFIGS]\nOther Deck = other_deck\n",
        encoding="utf-8",
    )

    receipt = apply_package(package_root=package, runtime_root=runtime, config_dir="shadowpriest")

    deck_config_text = (custom_config / "deck_config.ini").read_text(encoding="utf-8")
    assert "Other Deck = other_deck" in deck_config_text
    assert "ShadowPriest = shadowpriest" in deck_config_text
    assert receipt["deck_config_ini_updated"] is True
    assert receipt["mapped_deck_name"] == "ShadowPriest"
    assert receipt["config_dir"] == "shadowpriest"


def test_apply_package_updates_existing_mapping_without_duplicate(tmp_path: Path):
    package = tmp_path / "package"
    package_deck = package / "CustomConfig" / "shadowpriest"
    write_json(package_deck / "GlobalValues.json", {"GameCardId": "GlobalValues", "ConfigComment": "new"})
    write_json(
        package_deck / "Mulligan.json",
        {"GameCardId": "Mulligan", "ConfigComment": "new", "Mulligan": {"values": []}},
    )
    write_json(
        package_deck / "SW_446.json",
        {"GameCardId": "SW_446", "ConfigComment": "new", "InHandPlayPriority": {"values": []}},
    )
    write_json(
        package / "reports" / "input_manifest.json",
        {
            "deck_name": "ShadowPriest",
            "deck_code": "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=",
            "runtime_root": str(tmp_path / "runtime"),
            "target_config_mode": "preview",
        },
    )

    runtime = tmp_path / "runtime"
    custom_config = runtime / "CustomConfig"
    custom_config.mkdir(parents=True)
    (custom_config / "deck_config.ini").write_text(
        "[CONFIGS]\nShadowPriest = old_shadow\n",
        encoding="utf-8",
    )

    apply_package(package_root=package, runtime_root=runtime, config_dir="shadowpriest")

    deck_config_text = (custom_config / "deck_config.ini").read_text(encoding="utf-8")
    assert deck_config_text.count("ShadowPriest = shadowpriest") == 1
    assert "ShadowPriest = old_shadow" not in deck_config_text
```

- [ ] **Step 2: Run failing apply tests**

Run:

```powershell
pytest tests\test_runtime_apply.py -q
```

Expected: fail because `deck_config.ini` is not written.

- [ ] **Step 3: Import read helper**

Modify `src/hsconfig/runtime_apply.py` import:

```python
from hsconfig.io import file_sha256, read_json, write_json
```

- [ ] **Step 4: Resolve deck name from package manifest**

Add to `src/hsconfig/runtime_apply.py`:

```python
def _deck_name_from_manifest(package: Path, fallback: str) -> str:
    manifest_path = package / "reports" / "input_manifest.json"
    if not manifest_path.is_file():
        return fallback
    manifest = read_json(manifest_path)
    if not isinstance(manifest, dict):
        return fallback
    deck_name = str(manifest.get("deck_name", "")).strip()
    return deck_name or fallback
```

- [ ] **Step 5: Implement deck_config.ini mapping writer**

Add to `src/hsconfig/runtime_apply.py`:

```python
def _write_deck_config_mapping(target_root: Path, deck_name: str, config_dir: str) -> dict[str, Any]:
    path = target_root / "deck_config.ini"
    before_sha = file_sha256(path) if path.is_file() else None
    lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []

    if not any(line.strip().lower() == "[configs]" for line in lines):
        if lines and lines[-1].strip():
            lines.append("")
        lines.append("[CONFIGS]")

    output: list[str] = []
    in_configs = False
    mapping_written = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            if in_configs and not mapping_written:
                output.append(f"{deck_name} = {config_dir}")
                mapping_written = True
            in_configs = stripped.lower() == "[configs]"
            output.append(line)
            continue
        if in_configs and "=" in line:
            left = line.split("=", 1)[0].strip()
            if left == deck_name:
                if not mapping_written:
                    output.append(f"{deck_name} = {config_dir}")
                    mapping_written = True
                continue
        output.append(line)

    if not mapping_written:
        output.append(f"{deck_name} = {config_dir}")

    path.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")
    after_sha = file_sha256(path)
    return {
        "deck_config_ini_path": str(path),
        "deck_config_ini_updated": before_sha != after_sha,
        "deck_config_ini_previous_sha256": before_sha,
        "deck_config_ini_sha256": after_sha,
    }
```

- [ ] **Step 6: Call mapping writer from apply**

In `apply_package`, after `shutil.copytree(source_dir, target_dir)`, add:

```python
deck_name = _deck_name_from_manifest(package, deck_dir_name)
mapping_receipt = _write_deck_config_mapping(target_root, deck_name, deck_dir_name)
```

Add these fields to the receipt:

```python
"mapped_deck_name": deck_name,
**mapping_receipt,
```

The receipt block should include:

```python
receipt = {
    "status": "applied",
    "runtime_write_performed": True,
    "package_root": str(package),
    "runtime_root": str(runtime),
    "config_dir": deck_dir_name,
    "mapped_deck_name": deck_name,
    "source_path": str(source_dir),
    "target_path": str(target_dir),
    "replaced_existing": replaced_existing,
    "copied_files": copied_files,
    **mapping_receipt,
}
```

- [ ] **Step 7: Run runtime apply tests**

Run:

```powershell
pytest tests\test_runtime_apply.py -q
```

Expected: all runtime apply tests pass.

- [ ] **Step 8: Commit**

Run:

```powershell
git add src/hsconfig/runtime_apply.py tests/test_runtime_apply.py
git commit -m "feat: write deck config mapping on apply"
```

## Task 5: ShadowPriest Deckinput-Only E2E Proof

**Files:**
- Create: `tests/test_shadowpriest_e2e.py`

- [ ] **Step 1: Add the E2E proof test**

Create `tests/test_shadowpriest_e2e.py`:

```python
import json
from pathlib import Path

from hsconfig.cli import main


SHADOWPRIEST_CODE = (
    "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/"
    "KgG17oG1cEGAAA="
)


def test_shadowpriest_build_validate_apply_from_deck_input_only(tmp_path: Path, capsys):
    package = tmp_path / "shadowpriest_package"
    runtime = tmp_path / "runtime"

    build_code = main(
        [
            "build",
            "--deck-name",
            "ShadowPriest",
            "--deck-code",
            SHADOWPRIEST_CODE,
            "--runtime-root",
            str(runtime),
            "--out",
            str(package),
            "--json",
        ]
    )
    build_payload = json.loads(capsys.readouterr().out)
    assert build_code == 0
    assert build_payload["status"] == "passed"

    validate_code = main(["validate", "--package", str(package), "--json"])
    validate_payload = json.loads(capsys.readouterr().out)
    assert validate_code == 0
    assert validate_payload["status"] == "passed"

    apply_code = main(
        [
            "apply",
            "--package",
            str(package),
            "--runtime-root",
            str(runtime),
            "--json",
        ]
    )
    apply_payload = json.loads(capsys.readouterr().out)
    assert apply_code == 0
    assert apply_payload["status"] == "applied"

    deck_dir = package / "CustomConfig" / "shadowpriest"
    identity = json.loads((package / "reports" / "deck_identity.json").read_text(encoding="utf-8"))
    decode_receipt = json.loads(
        (package / "reports" / "deckstring_decode_receipt.json").read_text(encoding="utf-8")
    )
    deck_config = (runtime / "CustomConfig" / "deck_config.ini").read_text(encoding="utf-8")

    assert identity["card_count_total"] == 30
    assert identity["hero_dbf_id"] == 813
    assert identity["format"] == "FT_WILD"
    assert decode_receipt["unresolved_card_count"] == 0
    assert (deck_dir / "SW_446.json").exists()
    assert (deck_dir / "DS1_233.json").exists()
    assert (deck_dir / "GlobalValues.json").exists()
    assert (deck_dir / "Mulligan.json").exists()
    assert "ShadowPriest = shadowpriest" in deck_config
```

- [ ] **Step 2: Run the E2E proof**

Run:

```powershell
pytest tests\test_shadowpriest_e2e.py -q
```

Expected: `1 passed`.

- [ ] **Step 3: Commit**

Run:

```powershell
git add tests/test_shadowpriest_e2e.py
git commit -m "test: prove shadowpriest deck input e2e"
```

## Task 6: Update README And Skill Docs To The New Normal Path

**Files:**
- Modify: `README.md`
- Modify: `.agents/skills/hsconfig/SKILL.md`
- Modify: `.agents/skills/hsconfig/references/workflow.md`
- Modify: `.agents/skills/hsconfig/references/globalvalues-policy.md`
- Test: `tests/test_skill_files.py`

- [ ] **Step 1: Update README command sections**

Replace the README command section with:

```markdown
## Commands

Build a real deck package from deck input:

```powershell
hsconfig build --deck-name "ShadowPriest" --deck-code "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=" --runtime-root "C:\Users\darbo\Desktop\HS" --out ".\outputs\shadowpriest" --json
```

Validate a package:

```powershell
hsconfig validate --package ".\outputs\shadowpriest" --json
```

Apply a validated package to HearthRanger runtime:

```powershell
hsconfig apply --package ".\outputs\shadowpriest" --runtime-root "C:\Users\darbo\Desktop\HS" --json
```

Expert overrides:

- `--cards-json` supplies explicit card rows and skips deckstring decode.
- `--claims-json` supplies source-backed guide claims for stronger Mulligan, Combo, and CardID behavior.
- `--allow-placeholder` enables deterministic placeholder cards for CI/debug smoke tests only.

Generated runtime packages are written under `outputs/` and ignored by git.
```

- [ ] **Step 2: Update skill frontmatter and workflow wording**

In `.agents/skills/hsconfig/SKILL.md`, keep the frontmatter but update the inputs and workflow:

```markdown
Inputs:

- deck name
- deck code
- optional source-backed guide claims JSON
- optional card JSON override
- runtime root only when applying

Workflow:

1. Decode the deck code into exact CardIDs and card metadata.
2. Add or create guide-backed claims when available.
3. Generate direct runtime config surfaces only: `GlobalValues.json`, `Mulligan.json`, per-card `<CARDID>.json`, and `Combo.json` when a concrete valid combo exists.
4. Validate the package before any apply.
5. Runtime apply only when the user asks.
```

- [ ] **Step 3: Update workflow reference**

Replace `.agents/skills/hsconfig/references/workflow.md` content with:

```markdown
# Workflow

Build flow: deck input -> deckstring decode -> exact CardIDs -> card metadata -> guide claims -> guide-backed gameplan -> surface intent -> compilers -> validation -> optional runtime apply.

Use `hsconfig build` for package creation. A normal build decodes the deck code directly. Use `--claims-json` when guide research has source-backed claims, use `--cards-json` only as an expert override, use `hsconfig validate` before handoff or apply, and use `hsconfig apply` only when the user explicitly asks to write to a HearthRanger runtime.
```

- [ ] **Step 4: Update GlobalValues policy with runtime syntax tolerance**

Append to `.agents/skills/hsconfig/references/globalvalues-policy.md`:

```markdown
Runtime baseline files may contain UTF-8 BOMs, trailing commas, or simple numeric expressions. HSConfig must read those runtime forms but must write strict JSON packages.
```

- [ ] **Step 5: Add skill docs assertions**

Modify `tests/test_skill_files.py` with:

```python
def test_skill_documents_deck_decode_as_normal_path():
    text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    workflow = (SKILL_ROOT / "references" / "workflow.md").read_text(encoding="utf-8")

    assert "Decode the deck code into exact CardIDs" in text
    assert "deckstring decode" in workflow
    assert "--allow-placeholder" in workflow
```

If the last assertion is too strict after wording changes, use:

```python
assert "placeholder" in workflow.lower()
```

- [ ] **Step 6: Run docs tests**

Run:

```powershell
pytest tests\test_skill_files.py -q
```

Expected: all skill file tests pass.

- [ ] **Step 7: Commit**

Run:

```powershell
git add README.md .agents/skills/hsconfig tests/test_skill_files.py
git commit -m "docs: document autonomous deck build path"
```

## Task 7: Full Verification And GitHub Sync

**Files:**
- Verify: all touched files
- Optional local install check: `C:\Users\darbo\.codex\skills\hsconfig`

- [ ] **Step 1: Run full test suite**

Run:

```powershell
pytest -q
```

Expected: all tests pass.

- [ ] **Step 2: Run real ShadowPriest CLI smoke**

Run:

```powershell
if (Test-Path ".\tmp\shadowpriest_autonomy_smoke") {
  Remove-Item -LiteralPath ".\tmp\shadowpriest_autonomy_smoke" -Recurse -Force
}
hsconfig build --deck-name "ShadowPriest" --deck-code "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=" --runtime-root "C:\Users\darbo\Desktop\HS" --out ".\tmp\shadowpriest_autonomy_smoke" --json
hsconfig validate --package ".\tmp\shadowpriest_autonomy_smoke" --json
```

Expected:

- build JSON contains `"status": "passed"`
- validate JSON contains `"status": "passed"`
- `tmp\shadowpriest_autonomy_smoke\reports\deckstring_decode_receipt.json` exists
- no `HSC_` placeholder files exist in `tmp\shadowpriest_autonomy_smoke\CustomConfig\shadowpriest`

- [ ] **Step 3: Run temp runtime apply smoke**

Run:

```powershell
if (Test-Path ".\tmp\shadowpriest_autonomy_runtime") {
  Remove-Item -LiteralPath ".\tmp\shadowpriest_autonomy_runtime" -Recurse -Force
}
hsconfig apply --package ".\tmp\shadowpriest_autonomy_smoke" --runtime-root ".\tmp\shadowpriest_autonomy_runtime" --json
Get-Content ".\tmp\shadowpriest_autonomy_runtime\CustomConfig\deck_config.ini"
```

Expected:

```text
[CONFIGS]
ShadowPriest = shadowpriest
```

Additional lines are allowed if the temp runtime was pre-seeded for a test, but unrelated mappings must remain intact.

- [ ] **Step 4: Check generated outputs are ignored**

Run:

```powershell
git status --short --branch
git check-ignore -v tmp\shadowpriest_autonomy_smoke tmp\shadowpriest_autonomy_runtime
```

Expected:

- branch shows only tracked source/doc/test changes before final commit, or clean after final commit
- `tmp/` ignore rule matches both smoke folders

- [ ] **Step 5: Optional local skill discoverability check**

Run:

```powershell
Test-Path "C:\Users\darbo\.codex\skills\hsconfig\SKILL.md"
Test-Path ".\.agents\skills\hsconfig\SKILL.md"
```

Expected:

- repo-local skill path is `True`
- global skill path may be `False`

If global path is `False`, do not block the implementation. Report that HSConfig is repo-local and can be installed globally in a separate skill-install step if desired.

- [ ] **Step 6: Final commit if needed**

If any final doc/test changes remain:

```powershell
git add README.md .agents/skills/hsconfig src tests pyproject.toml
git commit -m "feat: close autonomous deck build workflow"
```

- [ ] **Step 7: Push main**

Run:

```powershell
git status --short --branch
git push origin main
```

Expected:

- local branch is clean before push
- `origin/main` receives the new commits

## Self-Review Checklist

- Spec coverage:
  - Deckcode decode is covered by Tasks 1 and 2.
  - Exact CardIDs and metadata are covered by Task 1.
  - Placeholder fallback is explicitly gated by Task 2.
  - Runtime `deck_config.ini` is covered by Task 4.
  - ShadowPriest deckinput-only proof is covered by Task 5.
  - Docs and skill wording are covered by Task 6.
  - Full tests and push are covered by Task 7.
- Scope control:
  - No HSTuner logic is introduced.
  - No replay/log/winrate modules are introduced.
  - Online guide research remains an input/skill activity, not deterministic CLI behavior.
- Type consistency:
  - `decode_deck_code()` returns `cards`, `hero_dbf_id`, `format`, `deckstring_decode_receipt`, and `card_id_map`.
  - `_load_cards()` returns one payload dict, not just a list.
  - `build_deck_identity()` accepts `format`.
  - `apply_package()` still supports existing callers through optional `config_dir`.
- Validation:
  - Targeted tests run after each task.
  - Full `pytest -q` runs before push.
  - Real ShadowPriest CLI smoke proves the core user workflow.



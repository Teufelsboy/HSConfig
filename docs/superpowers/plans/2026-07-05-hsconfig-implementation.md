# HSConfig Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build HSConfig: a lean Codex skill and Python CLI that turns a Hearthstone deck name/code plus guide research into a complete, aggressive HearthRanger VisionAI `CustomConfig` package.

**Architecture:** HSConfig is a direct config authoring tool, not a replay tuner. The pipeline is deck identity -> card metadata -> guide research -> aggressive gameplan contract -> surface intent matrix -> VisionAI compilers -> strict package validation -> optional runtime apply. `GlobalValues.json` is a full-key surface: every default key must be profiled and explicitly changed, confirmed, or blocked.

**Tech Stack:** Python 3.11+, stdlib `json`/`dataclasses`/`pathlib`, `pytest`, optional `requests` for live source fetches, optional HearthSim `hearthstone` package for deckstring decoding, repo-local Codex skill under `.agents/skills/hsconfig`.

---

## File Structure

Create these files:

- `pyproject.toml` - package metadata, CLI entry point, pytest config.
- `README.md` - short operator entrypoint.
- `AGENTS.md` - repo-local agent rules.
- `src/hsconfig/__init__.py` - package marker and version.
- `src/hsconfig/cli.py` - `hsconfig build`, `validate`, `apply`.
- `src/hsconfig/io.py` - JSON read/write, hash helpers, slugging.
- `src/hsconfig/models.py` - dataclasses and typed dict-like contracts.
- `src/hsconfig/deck_identity.py` - deckstring decode and CardID map orchestration.
- `src/hsconfig/card_metadata.py` - card metadata hydration and mechanic taxonomy.
- `src/hsconfig/guide_research.py` - guide/data source normalization.
- `src/hsconfig/gameplan_contract.py` - aggressive gameplan construction and card coverage.
- `src/hsconfig/surface_intent.py` - route gameplan claims to VisionAI surfaces.
- `src/hsconfig/visionai_registry.py` - documented blocks, required top-level keys, allowed surfaces.
- `src/hsconfig/compile_mulligan.py` - `Mulligan.json` compiler.
- `src/hsconfig/compile_globalvalues.py` - full-key `GlobalValues.json` compiler.
- `src/hsconfig/compile_cardid.py` - per-card `<CARDID>.json` compiler.
- `src/hsconfig/compile_combo.py` - `Combo.json` compiler.
- `src/hsconfig/compile_optional_surfaces.py` - gated `Presume.json` / `Concede.json`.
- `src/hsconfig/validate_package.py` - strict package validator.
- `src/hsconfig/runtime_apply.py` - guarded runtime writer.
- `.agents/skills/hsconfig/SKILL.md` - repo-local Codex skill.
- `.agents/skills/hsconfig/references/workflow.md` - workflow reference.
- `.agents/skills/hsconfig/references/visionai-surfaces.md` - VisionAI surface rules.
- `.agents/skills/hsconfig/references/guide-research-policy.md` - guide source rules.
- `.agents/skills/hsconfig/references/globalvalues-policy.md` - full-key global policy.
- `.agents/skills/hsconfig/references/card-behavior-policy.md` - CardID behavior lowering.
- `.agents/skills/hsconfig/references/output-contract.md` - artifact contract.
- `.agents/skills/hsconfig/scripts/build_config.py` - thin CLI wrapper.
- `.agents/skills/hsconfig/scripts/validate_package.py` - thin validation wrapper.
- `tests/fixtures/default_globalvalues.json` - minimal but representative default baseline.
- `tests/fixtures/shadowpriest_input.json` - deterministic deck fixture input.
- `tests/fixtures/card_metadata_sample.json` - CardID metadata fixture.
- `tests/test_*.py` files listed below.

Do not create replay/log parsing modules. Do not add HSTuner concepts.

---

## Task 1: Repository Bootstrap And Toolchain

**Files:**
- Create: `pyproject.toml`
- Create: `README.md`
- Create: `AGENTS.md`
- Create: `src/hsconfig/__init__.py`
- Test: `tests/test_package_import.py`

- [ ] **Step 1: Write package import test**

Create `tests/test_package_import.py`:

```python
def test_package_imports():
    import hsconfig

    assert hsconfig.__version__ == "0.1.0"
```

- [ ] **Step 2: Create package marker**

Create `src/hsconfig/__init__.py`:

```python
__version__ = "0.1.0"
```

- [ ] **Step 3: Create `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "hsconfig"
version = "0.1.0"
description = "Guide-aligned HearthRanger VisionAI CustomConfig generator"
requires-python = ">=3.11"
dependencies = [
  "requests>=2.32",
  "hearthstone>=9.0.0",
]

[project.optional-dependencies]
dev = [
  "pytest>=8.0",
]

[project.scripts]
hsconfig = "hsconfig.cli:main"

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
```

- [ ] **Step 4: Create repo README**

Create `README.md`:

```markdown
# HSConfig

HSConfig builds HearthRanger VisionAI `CustomConfig` packages from a Hearthstone deck name and deck code.

It is a direct config authoring tool: deck identity, card metadata, guide research, aggressive gameplan contract, VisionAI compilers, validation, and optional runtime apply.

Normal flow:

```powershell
hsconfig build --deck-name "DeckName" --deck-code "..." --runtime-root "C:\Users\darbo\Desktop\HS" --out ".\outputs\deckname" --json
hsconfig validate --package ".\outputs\deckname" --json
hsconfig apply --package ".\outputs\deckname" --runtime-root "C:\Users\darbo\Desktop\HS" --json
```

HSConfig does not parse replays, evaluate winrate, or tune from post-game evidence. Those are HSTuner concerns.
```
```

- [ ] **Step 5: Create repo agent rules**

Create `AGENTS.md`:

```markdown
# HSConfig Agent Rules

Work in `C:\Users\darbo\Documents\HSConfig` for `Teufelsboy/HSConfig`.

HSConfig is a lean deck-to-HearthRanger-config generator. Keep it separate from HSTuner.

Do not add replay parsing, HDT parsing, winrate validation, candidate promotion, or post-run tuning to this repo.

Generated runtime packages belong under `outputs/` and are ignored by git.

Every implementation change must keep:

- exact deck and CardID identity
- full `GlobalValues.json` key profiling
- every card covered in the gameplan contract
- strict JSON validation
- row-level provenance for generated config rows
```

- [ ] **Step 6: Run import test**

Run:

```powershell
python -m pip install -e .[dev]
python -m pytest tests/test_package_import.py -v
```

Expected: `1 passed`.

- [ ] **Step 7: Commit**

```powershell
git add pyproject.toml README.md AGENTS.md src/hsconfig/__init__.py tests/test_package_import.py
git commit -m "chore: bootstrap hsconfig package"
```

---

## Task 2: Shared IO And Contract Models

**Files:**
- Create: `src/hsconfig/io.py`
- Create: `src/hsconfig/models.py`
- Test: `tests/test_io_and_models.py`

- [ ] **Step 1: Write IO/model tests**

Create `tests/test_io_and_models.py`:

```python
from pathlib import Path

from hsconfig.io import file_sha256, read_json, slugify_deck_name, write_json
from hsconfig.models import InputManifest


def test_json_round_trip_and_hash(tmp_path: Path):
    path = tmp_path / "data.json"

    write_json(path, {"b": 2, "a": 1})

    assert read_json(path) == {"a": 1, "b": 2}
    assert len(file_sha256(path)) == 64


def test_slugify_deck_name():
    assert slugify_deck_name("Shadow Priest!") == "shadow_priest"
    assert slugify_deck_name("  CtA Paladin  ") == "cta_paladin"


def test_input_manifest_serializes():
    manifest = InputManifest(
        deck_name="ShadowPriest",
        deck_code="AAEBA...",
        runtime_root="C:\\Users\\darbo\\Desktop\\HS",
        target_config_mode="preview",
    )

    assert manifest.to_dict()["deck_name"] == "ShadowPriest"
    assert manifest.to_dict()["target_config_mode"] == "preview"
```

- [ ] **Step 2: Implement `io.py`**

```python
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


def read_json(path: str | Path) -> Any:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: str | Path, data: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)
        handle.write("\n")


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def slugify_deck_name(deck_name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", deck_name.strip().lower())
    return re.sub(r"_+", "_", slug).strip("_")
```

- [ ] **Step 3: Implement `models.py`**

```python
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class InputManifest:
    deck_name: str
    deck_code: str
    runtime_root: str
    target_config_mode: str = "preview"
    format: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ConfigRow:
    file_path: str
    json_pointer: str
    source_rule_id: str
    source_refs: list[str] = field(default_factory=list)
    confidence: str = "source_backed"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
```

- [ ] **Step 4: Run tests**

```powershell
python -m pytest tests/test_io_and_models.py -v
```

Expected: `3 passed`.

- [ ] **Step 5: Commit**

```powershell
git add src/hsconfig/io.py src/hsconfig/models.py tests/test_io_and_models.py
git commit -m "feat: add shared io and contract models"
```

---

## Task 3: Deck Identity And Card Metadata Fixtures

**Files:**
- Create: `src/hsconfig/deck_identity.py`
- Create: `src/hsconfig/card_metadata.py`
- Create: `tests/fixtures/shadowpriest_input.json`
- Create: `tests/fixtures/card_metadata_sample.json`
- Test: `tests/test_deck_identity.py`
- Test: `tests/test_card_metadata.py`

- [ ] **Step 1: Create fixture input**

Create `tests/fixtures/shadowpriest_input.json`:

```json
{
  "deck_name": "ShadowPriest",
  "deck_code": "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=",
  "runtime_root": "C:\\Users\\darbo\\Desktop\\HS",
  "target_config_mode": "preview"
}
```

- [ ] **Step 2: Create card metadata sample**

Create `tests/fixtures/card_metadata_sample.json`:

```json
{
  "card_id": "CS2_235",
  "dbf_id": 1367,
  "name": "Northshire Cleric",
  "cost": 1,
  "type": "MINION",
  "mechanics": [],
  "text": "Whenever a minion is healed, draw a card."
}
```

- [ ] **Step 3: Write deck identity tests**

Create `tests/test_deck_identity.py`:

```python
from hsconfig.deck_identity import build_deck_identity, stable_deck_fingerprint


def test_stable_deck_fingerprint_is_order_independent():
    left = stable_deck_fingerprint([("A", 2), ("B", 1)])
    right = stable_deck_fingerprint([("B", 1), ("A", 2)])

    assert left == right
    assert len(left) == 64


def test_build_deck_identity_from_explicit_cards():
    identity = build_deck_identity(
        deck_name="Example",
        deck_code="test-code",
        cards=[{"card_id": "A", "dbf_id": 1, "count": 2}],
        hero_dbf_id=7,
    )

    assert identity["deck_name"] == "Example"
    assert identity["cards"][0]["card_id"] == "A"
    assert identity["cards"][0]["count"] == 2
    assert identity["unresolved_card_count"] == 0
```

- [ ] **Step 4: Implement deck identity fallback**

Implement `src/hsconfig/deck_identity.py`:

```python
from __future__ import annotations

import hashlib
import json
from typing import Any


def stable_deck_fingerprint(cards: list[tuple[str, int]]) -> str:
    canonical = sorted(cards, key=lambda row: row[0])
    payload = json.dumps(canonical, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_deck_identity(
    *,
    deck_name: str,
    deck_code: str,
    cards: list[dict[str, Any]],
    hero_dbf_id: int | None = None,
) -> dict[str, Any]:
    normalized_cards = [
        {
            "card_id": str(card["card_id"]),
            "dbf_id": int(card["dbf_id"]),
            "count": int(card.get("count", 1)),
        }
        for card in cards
    ]
    fingerprint = stable_deck_fingerprint(
        [(card["card_id"], card["count"]) for card in normalized_cards]
    )
    return {
        "deck_name": deck_name,
        "deck_code_hash": hashlib.sha256(deck_code.encode("utf-8")).hexdigest(),
        "hero_dbf_id": hero_dbf_id,
        "cards": normalized_cards,
        "deck_fingerprint": fingerprint,
        "card_count_total": sum(card["count"] for card in normalized_cards),
        "unresolved_card_count": sum(1 for card in normalized_cards if not card["card_id"]),
    }
```

- [ ] **Step 5: Write metadata tests**

Create `tests/test_card_metadata.py`:

```python
from hsconfig.card_metadata import assign_mechanic_families, hydrate_card_metadata


def test_assign_mechanic_families_from_text_and_tags():
    card = {
        "card_id": "TEST",
        "mechanics": ["BATTLECRY"],
        "text": "Battlecry: Discover a spell.",
        "type": "MINION",
    }

    families = assign_mechanic_families(card)

    assert "battlecry" in families
    assert "discover" in families


def test_hydrate_card_metadata_uses_source_records():
    snapshot = hydrate_card_metadata(
        cards=[{"card_id": "CS2_235", "dbf_id": 1367, "count": 1}],
        source_records={"CS2_235": {"name": "Northshire Cleric", "cost": 1, "type": "MINION", "text": "Draw a card."}},
    )

    assert snapshot["cards"][0]["name"] == "Northshire Cleric"
    assert snapshot["cards"][0]["card_id"] == "CS2_235"
```

- [ ] **Step 6: Implement metadata module**

Implement `src/hsconfig/card_metadata.py`:

```python
from __future__ import annotations

from typing import Any


MECHANIC_ALIASES = {
    "battlecry": ["battlecry", "BATTLECRY"],
    "deathrattle": ["deathrattle", "DEATHRATTLE"],
    "discover": ["discover", "DISCOVER"],
    "dredge": ["dredge", "DREDGE"],
    "tradeable": ["tradeable", "TRADEABLE"],
    "overload": ["overload", "OVERLOAD"],
    "lifesteal": ["lifesteal", "LIFESTEAL"],
    "reborn": ["reborn", "REBORN"],
    "rush": ["rush", "RUSH"],
    "charge": ["charge", "CHARGE"],
    "taunt": ["taunt", "TAUNT"],
    "secret": ["secret", "SECRET"],
    "weapon": ["weapon", "WEAPON"],
    "location": ["location", "LOCATION"],
    "discard": ["discard"],
    "silence": ["silence"],
    "transform": ["transform"],
    "destroy": ["destroy"],
}


def assign_mechanic_families(card: dict[str, Any]) -> list[str]:
    haystack = " ".join(
        [str(card.get("type", "")), str(card.get("text", ""))]
        + [str(item) for item in card.get("mechanics", [])]
    ).lower()
    families = []
    for family, aliases in MECHANIC_ALIASES.items():
        if any(alias.lower() in haystack for alias in aliases):
            families.append(family)
    return sorted(set(families))


def hydrate_card_metadata(
    *,
    cards: list[dict[str, Any]],
    source_records: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    hydrated = []
    for card in cards:
        card_id = card["card_id"]
        source = source_records.get(card_id, {})
        merged = {
            "card_id": card_id,
            "dbf_id": card["dbf_id"],
            "count": card.get("count", 1),
            "name": source.get("name", card_id),
            "cost": source.get("cost"),
            "type": source.get("type", "UNKNOWN"),
            "text": source.get("text", ""),
            "mechanics": source.get("mechanics", []),
        }
        merged["mechanic_families"] = assign_mechanic_families(merged)
        hydrated.append(merged)
    return {"cards": hydrated}
```

- [ ] **Step 7: Run tests**

```powershell
python -m pytest tests/test_deck_identity.py tests/test_card_metadata.py -v
```

Expected: `4 passed`.

- [ ] **Step 8: Commit**

```powershell
git add src/hsconfig/deck_identity.py src/hsconfig/card_metadata.py tests/fixtures tests/test_deck_identity.py tests/test_card_metadata.py
git commit -m "feat: add deck identity and card metadata core"
```

---

## Task 4: Guide Research And Aggressive Gameplan Contract

**Files:**
- Create: `src/hsconfig/guide_research.py`
- Create: `src/hsconfig/gameplan_contract.py`
- Test: `tests/test_guide_research.py`
- Test: `tests/test_gameplan_contract.py`

- [ ] **Step 1: Write guide research tests**

Create `tests/test_guide_research.py`:

```python
from hsconfig.guide_research import normalize_source_claims


def test_normalize_source_claims_keeps_aggressive_claims():
    claims = normalize_source_claims(
        [
            {
                "source": "guide",
                "url": "https://example.invalid/deck",
                "claim": "Always keep Shadowbomber and push face damage early.",
                "cards": ["CARD_1"],
                "claim_type": "mulligan_and_gameplan",
            }
        ]
    )

    assert claims["claims"][0]["claim"] == "Always keep Shadowbomber and push face damage early."
    assert claims["claims"][0]["confidence"] == "source_backed"
```

- [ ] **Step 2: Implement guide research normalizer**

Create `src/hsconfig/guide_research.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def normalize_source_claims(raw_claims: list[dict[str, Any]]) -> dict[str, Any]:
    normalized = []
    retrieved_at = datetime.now(timezone.utc).isoformat()
    for index, claim in enumerate(raw_claims, start=1):
        normalized.append(
            {
                "claim_id": f"claim_{index:04d}",
                "source": claim["source"],
                "url": claim["url"],
                "claim": claim["claim"],
                "cards": claim.get("cards", []),
                "claim_type": claim.get("claim_type", "general"),
                "confidence": claim.get("confidence", "source_backed"),
                "retrieved_at": retrieved_at,
            }
        )
    return {"claims": normalized}
```

- [ ] **Step 3: Write gameplan contract tests**

Create `tests/test_gameplan_contract.py`:

```python
from hsconfig.gameplan_contract import build_gameplan_contract


def test_gameplan_contract_covers_every_card():
    contract = build_gameplan_contract(
        deck_name="Example",
        cards=[
            {"card_id": "CARD_1", "name": "One", "mechanic_families": ["battlecry"]},
            {"card_id": "CARD_2", "name": "Two", "mechanic_families": []},
        ],
        claims={
            "claims": [
                {
                    "claim_id": "claim_0001",
                    "claim": "Keep One and play it early.",
                    "cards": ["CARD_1"],
                    "confidence": "source_backed",
                }
            ]
        },
    )

    assert {row["card_id"] for row in contract["card_role_map"]} == {"CARD_1", "CARD_2"}
    assert contract["card_role_map"][1]["coverage_status"] == "generic_low_confidence"
```

- [ ] **Step 4: Implement gameplan builder**

Create `src/hsconfig/gameplan_contract.py`:

```python
from __future__ import annotations

from typing import Any


def build_gameplan_contract(
    *,
    deck_name: str,
    cards: list[dict[str, Any]],
    claims: dict[str, Any],
) -> dict[str, Any]:
    claims_by_card: dict[str, list[dict[str, Any]]] = {}
    for claim in claims.get("claims", []):
        for card_id in claim.get("cards", []):
            claims_by_card.setdefault(card_id, []).append(claim)

    role_rows = []
    usage_rows = []
    for card in cards:
        card_id = card["card_id"]
        related_claims = claims_by_card.get(card_id, [])
        coverage_status = "source_backed" if related_claims else "generic_low_confidence"
        role_rows.append(
            {
                "card_id": card_id,
                "name": card.get("name", card_id),
                "mechanic_families": card.get("mechanic_families", []),
                "roles": _infer_roles(card, related_claims),
                "coverage_status": coverage_status,
                "source_claim_ids": [claim["claim_id"] for claim in related_claims],
            }
        )
        usage_rows.append(
            {
                "card_id": card_id,
                "expected_use": _infer_expected_use(related_claims),
                "target_policy": "from_surface_intent",
                "coverage_status": coverage_status,
            }
        )

    return {
        "deck_name": deck_name,
        "archetype": "guide_derived",
        "card_role_map": role_rows,
        "card_usage_expectations": usage_rows,
        "unknowns": [],
    }


def _infer_roles(card: dict[str, Any], claims: list[dict[str, Any]]) -> list[str]:
    text = " ".join(claim.get("claim", "") for claim in claims).lower()
    roles = []
    if "keep" in text:
        roles.append("mulligan_anchor")
    if "face" in text or "damage" in text:
        roles.append("pressure")
    roles.extend(card.get("mechanic_families", []))
    return sorted(set(roles)) or ["deck_card"]


def _infer_expected_use(claims: list[dict[str, Any]]) -> str:
    text = " ".join(claim.get("claim", "") for claim in claims).lower()
    if "keep" in text:
        return "keep_and_play_on_plan"
    if "hold" in text:
        return "hold_for_condition"
    return "follow_archetype_plan"
```

- [ ] **Step 5: Run tests**

```powershell
python -m pytest tests/test_guide_research.py tests/test_gameplan_contract.py -v
```

Expected: `2 passed`.

- [ ] **Step 6: Commit**

```powershell
git add src/hsconfig/guide_research.py src/hsconfig/gameplan_contract.py tests/test_guide_research.py tests/test_gameplan_contract.py
git commit -m "feat: add guide research and gameplan contracts"
```

---

## Task 5: VisionAI Registry And Package Validator

**Files:**
- Create: `src/hsconfig/visionai_registry.py`
- Create: `src/hsconfig/validate_package.py`
- Test: `tests/test_visionai_registry.py`
- Test: `tests/test_validate_package.py`

- [ ] **Step 1: Write registry tests**

Create `tests/test_visionai_registry.py`:

```python
from hsconfig.visionai_registry import CARD_BEHAVIOR_BLOCKS, supported_surface


def test_supported_surfaces():
    assert supported_surface("Mulligan.json")
    assert supported_surface("GlobalValues.json")
    assert supported_surface("Combo.json")
    assert supported_surface("EX1_001.json")


def test_card_behavior_blocks_include_targeting_and_discover():
    assert "BeforeBattlecryTargetBonus" in CARD_BEHAVIOR_BLOCKS
    assert "OnDiscoverCardBonus" in CARD_BEHAVIOR_BLOCKS
```

- [ ] **Step 2: Implement registry**

Create `src/hsconfig/visionai_registry.py`:

```python
from __future__ import annotations

CARD_BEHAVIOR_BLOCKS = {
    "InHandBonus",
    "OnBoardBonus",
    "BeforePlayCardBonus",
    "BeforeBattlecryTargetBonus",
    "BeforeUseHeroPowerBonus",
    "BeforePhysicalAttackBonus",
    "BeforeEndTurnBonus",
    "OnDiscoverCardBonus",
    "OnChooseOneCardBonus",
    "OnAdaptCardBonus",
    "BeforeUpgradeCardBonus",
    "InHandPlayPriority",
    "OnBoardPlayPriority",
}

SPECIAL_SURFACES = {
    "Mulligan.json",
    "GlobalValues.json",
    "Combo.json",
    "Presume.json",
    "Concede.json",
}


def supported_surface(filename: str) -> bool:
    if filename in SPECIAL_SURFACES:
        return True
    return filename.endswith(".json") and filename[:-5].isalnum() or "_" in filename[:-5]
```

- [ ] **Step 3: Write validator tests**

Create `tests/test_validate_package.py`:

```python
from pathlib import Path

from hsconfig.io import write_json
from hsconfig.validate_package import validate_config_package


def test_validate_package_rejects_cardid_mismatch(tmp_path: Path):
    deck_dir = tmp_path / "CustomConfig" / "deck"
    write_json(deck_dir / "ABC.json", {"GameCardId": "XYZ", "ConfigComment": "bad"})

    report = validate_config_package(tmp_path)

    assert report["status"] == "failed"
    assert "GameCardId mismatch" in report["errors"][0]


def test_validate_package_accepts_minimal_globalvalues(tmp_path: Path):
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

    report = validate_config_package(tmp_path)

    assert report["status"] == "passed"
```

- [ ] **Step 4: Implement validator**

Create `src/hsconfig/validate_package.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any

from hsconfig.io import read_json
from hsconfig.visionai_registry import CARD_BEHAVIOR_BLOCKS


def validate_config_package(package_root: str | Path) -> dict[str, Any]:
    root = Path(package_root)
    errors: list[str] = []
    for path in root.glob("CustomConfig/*/*.json"):
        try:
            data = read_json(path)
        except Exception as exc:
            errors.append(f"{path}: invalid JSON: {exc}")
            continue
        expected = _expected_game_card_id(path)
        if data.get("GameCardId") != expected:
            errors.append(f"{path}: GameCardId mismatch: expected {expected}, got {data.get('GameCardId')}")
        errors.extend(_validate_blocks(path, data))
    return {"status": "failed" if errors else "passed", "errors": errors}


def _expected_game_card_id(path: Path) -> str:
    if path.name == "GlobalValues.json":
        return "GlobalValues"
    if path.name == "Mulligan.json":
        return "Mulligan"
    if path.name == "Combo.json":
        return "Combo"
    if path.name == "Presume.json":
        return "Presume"
    if path.name == "Concede.json":
        return "Concede"
    return path.stem


def _validate_blocks(path: Path, data: dict[str, Any]) -> list[str]:
    if path.name in {"GlobalValues.json", "Mulligan.json", "Combo.json", "Presume.json", "Concede.json"}:
        return []
    errors = []
    for key, value in data.items():
        if key in {"GameCardId", "ConfigComment"}:
            continue
        if key not in CARD_BEHAVIOR_BLOCKS:
            errors.append(f"{path}: unsupported card behavior block {key}")
        elif not isinstance(value, dict) or not isinstance(value.get("values"), list):
            errors.append(f"{path}: block {key} must contain values array")
    return errors
```

- [ ] **Step 5: Run tests**

```powershell
python -m pytest tests/test_visionai_registry.py tests/test_validate_package.py -v
```

Expected: `4 passed`.

- [ ] **Step 6: Commit**

```powershell
git add src/hsconfig/visionai_registry.py src/hsconfig/validate_package.py tests/test_visionai_registry.py tests/test_validate_package.py
git commit -m "feat: add visionai registry and package validation"
```

---

## Task 6: Surface Intent Matrix

**Files:**
- Create: `src/hsconfig/surface_intent.py`
- Test: `tests/test_surface_intent.py`

- [ ] **Step 1: Write surface intent tests**

Create `tests/test_surface_intent.py`:

```python
from hsconfig.surface_intent import build_surface_intent


def test_surface_intent_routes_mulligan_and_pressure():
    gameplan = {
        "card_role_map": [
            {"card_id": "CARD_1", "roles": ["mulligan_anchor", "pressure"], "source_claim_ids": ["claim_1"]},
            {"card_id": "CARD_2", "roles": ["battlecry"], "source_claim_ids": []},
        ],
        "card_usage_expectations": [
            {"card_id": "CARD_1", "expected_use": "keep_and_play_on_plan"},
            {"card_id": "CARD_2", "expected_use": "follow_archetype_plan"},
        ],
    }

    intent = build_surface_intent(gameplan)

    surfaces = {(row["card_id"], row["surface"]) for row in intent["rows"]}
    assert ("CARD_1", "Mulligan.json") in surfaces
    assert ("CARD_1", "CARDID.json") in surfaces
```

- [ ] **Step 2: Implement surface intent**

Create `src/hsconfig/surface_intent.py`:

```python
from __future__ import annotations

from typing import Any


def build_surface_intent(gameplan: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for role in gameplan.get("card_role_map", []):
        card_id = role["card_id"]
        roles = set(role.get("roles", []))
        if "mulligan_anchor" in roles:
            rows.append(
                {
                    "rule_id": f"{card_id}_mulligan_keep",
                    "card_id": card_id,
                    "surface": "Mulligan.json",
                    "intent": "hold",
                    "source_claim_ids": role.get("source_claim_ids", []),
                }
            )
        if roles & {"pressure", "battlecry", "discover", "weapon", "secret", "location"}:
            rows.append(
                {
                    "rule_id": f"{card_id}_behavior",
                    "card_id": card_id,
                    "surface": "CARDID.json",
                    "intent": "play_according_to_role",
                    "source_claim_ids": role.get("source_claim_ids", []),
                }
            )
    return {"rows": rows}
```

- [ ] **Step 3: Run tests**

```powershell
python -m pytest tests/test_surface_intent.py -v
```

Expected: `1 passed`.

- [ ] **Step 4: Commit**

```powershell
git add src/hsconfig/surface_intent.py tests/test_surface_intent.py
git commit -m "feat: route gameplan claims to config surfaces"
```

---

## Task 7: Mulligan Compiler

**Files:**
- Create: `src/hsconfig/compile_mulligan.py`
- Test: `tests/test_compile_mulligan.py`

- [ ] **Step 1: Write compiler tests**

Create `tests/test_compile_mulligan.py`:

```python
from hsconfig.compile_mulligan import compile_mulligan


def test_compile_mulligan_emits_hold_rows_and_discard_fallback():
    result = compile_mulligan(
        deck_name="Example",
        rows=[
            {"rule_id": "CARD_1_mulligan_keep", "card_id": "CARD_1", "surface": "Mulligan.json", "intent": "hold"}
        ],
        add_discard_fallback=True,
    )

    rules = result["Mulligan"]["values"]
    assert rules[0]["mulligan"] == "CARD_1"
    assert rules[0]["value"] == "hold"
    assert rules[-1]["mulligan"] == "*"
    assert rules[-1]["value"] == "discard"
```

- [ ] **Step 2: Implement compiler**

Create `src/hsconfig/compile_mulligan.py`:

```python
from __future__ import annotations

from typing import Any


def compile_mulligan(
    *,
    deck_name: str,
    rows: list[dict[str, Any]],
    add_discard_fallback: bool = True,
) -> dict[str, Any]:
    values = []
    for row in rows:
        if row.get("surface") != "Mulligan.json":
            continue
        values.append(
            {
                "comment": f"{deck_name}: {row['rule_id']}",
                "mulligan": row["card_id"],
                "condition": row.get("condition", "*"),
                "value": row.get("intent", "hold"),
            }
        )
    if add_discard_fallback:
        values.append(
            {
                "comment": f"{deck_name}: discard cards not covered by guide-backed holds",
                "mulligan": "*",
                "condition": "*",
                "value": "discard",
            }
        )
    return {
        "GameCardId": "Mulligan",
        "ConfigComment": f"{deck_name} generated mulligan rules",
        "Mulligan": {"values": values},
    }
```

- [ ] **Step 3: Run tests**

```powershell
python -m pytest tests/test_compile_mulligan.py -v
```

Expected: `1 passed`.

- [ ] **Step 4: Commit**

```powershell
git add src/hsconfig/compile_mulligan.py tests/test_compile_mulligan.py
git commit -m "feat: compile guide-backed mulligan rules"
```

---

## Task 8: Full-Key GlobalValues Compiler

**Files:**
- Create: `src/hsconfig/compile_globalvalues.py`
- Create: `tests/fixtures/default_globalvalues.json`
- Test: `tests/test_compile_globalvalues.py`

- [ ] **Step 1: Create baseline fixture**

Create `tests/fixtures/default_globalvalues.json`:

```json
{
  "GameCardId": "GlobalValues",
  "ConfigComment": "Default GlobalValues fixture",
  "FirstTurnValueWeight": {
    "values": [{"condition": "*", "value": "0"}]
  },
  "SecondTurnValueWeight": {
    "values": [{"condition": "*", "value": "1"}]
  },
  "GlobalDivineShield": {
    "values": [{"condition": "*", "value": "2.74"}]
  },
  "GlobalTaunt": {
    "values": [{"condition": "*", "value": "1.25"}]
  }
}
```

- [ ] **Step 2: Write GlobalValues tests**

Create `tests/test_compile_globalvalues.py`:

```python
from hsconfig.compile_globalvalues import compile_globalvalues


def test_compile_globalvalues_profiles_every_key():
    baseline = {
        "GameCardId": "GlobalValues",
        "ConfigComment": "Default",
        "FirstTurnValueWeight": {"values": [{"condition": "*", "value": "0"}]},
        "SecondTurnValueWeight": {"values": [{"condition": "*", "value": "1"}]},
        "GlobalDivineShield": {"values": [{"condition": "*", "value": "2.74"}]},
    }

    result = compile_globalvalues(
        baseline=baseline,
        posture={"speed": "aggro", "mechanic_priorities": {"GlobalDivineShield": "increase"}},
    )

    config = result["config"]
    profile = result["profile"]
    assert set(config) == set(baseline)
    assert profile["key_count"] == 5
    assert profile["keys"]["FirstTurnValueWeight"]["decision"] == "overlay_changed"
    assert profile["keys"]["GlobalDivineShield"]["decision"] == "overlay_changed"
    assert profile["keys"]["SecondTurnValueWeight"]["decision"] == "overlay_changed"
```

- [ ] **Step 3: Implement full-key compiler**

Create `src/hsconfig/compile_globalvalues.py`:

```python
from __future__ import annotations

from copy import deepcopy
from typing import Any


def compile_globalvalues(
    *,
    baseline: dict[str, Any],
    posture: dict[str, Any],
) -> dict[str, Any]:
    config = deepcopy(baseline)
    profile: dict[str, Any] = {"key_count": len(baseline), "keys": {}}
    speed = posture.get("speed", "balanced")
    mechanic_priorities = posture.get("mechanic_priorities", {})

    for key, value in baseline.items():
        if key in {"GameCardId", "ConfigComment"}:
            profile["keys"][key] = {
                "category": "metadata",
                "decision": "baseline_confirmed",
                "reason": "Required metadata key.",
            }
            continue
        decision = {
            "category": _classify_key(key),
            "baseline_value": _first_value(value),
            "decision": "baseline_confirmed",
            "reason": "No deck-specific overlay required.",
        }
        if key == "FirstTurnValueWeight" and speed in {"aggro", "tempo"}:
            _set_first_value(config[key], "0.75")
            decision.update({"decision": "overlay_changed", "new_value": "0.75", "reason": "Aggressive deck values immediate board outcomes."})
        elif key == "SecondTurnValueWeight" and speed in {"aggro", "tempo"}:
            _set_first_value(config[key], "0.25")
            decision.update({"decision": "overlay_changed", "new_value": "0.25", "reason": "Aggressive deck reduces delayed outcome weighting."})
        elif mechanic_priorities.get(key) == "increase":
            old = _first_value(config[key])
            new = _increase_numeric_string(old)
            _set_first_value(config[key], new)
            decision.update({"decision": "overlay_changed", "new_value": new, "reason": "Deck gameplan prioritizes this mechanic."})
        profile["keys"][key] = decision

    return {"config": config, "profile": profile}


def _first_value(block: Any) -> str | None:
    if isinstance(block, dict) and block.get("values"):
        return str(block["values"][0].get("value"))
    return None


def _set_first_value(block: dict[str, Any], value: str) -> None:
    block["values"][0]["value"] = value


def _increase_numeric_string(value: str | None) -> str:
    if value is None:
        return "1"
    return f"{float(value) * 1.15:.2f}"


def _classify_key(key: str) -> str:
    lowered = key.lower()
    if "turnvalueweight" in lowered:
        return "turn_weight"
    if "weapon" in lowered:
        return "weapon"
    if "secret" in lowered:
        return "secret"
    if "hero" in lowered:
        return "hero"
    if "deck" in lowered:
        return "deck"
    return "mechanic_modifier"
```

- [ ] **Step 4: Run tests**

```powershell
python -m pytest tests/test_compile_globalvalues.py -v
```

Expected: `1 passed`.

- [ ] **Step 5: Commit**

```powershell
git add src/hsconfig/compile_globalvalues.py tests/fixtures/default_globalvalues.json tests/test_compile_globalvalues.py
git commit -m "feat: compile full-key global values"
```

---

## Task 9: CardID Behavior Compiler

**Files:**
- Create: `src/hsconfig/compile_cardid.py`
- Test: `tests/test_compile_cardid.py`

- [ ] **Step 1: Write CardID compiler tests**

Create `tests/test_compile_cardid.py`:

```python
from hsconfig.compile_cardid import compile_cardid_behaviors


def test_compile_cardid_behaviors_emits_priority_file():
    files = compile_cardid_behaviors(
        deck_name="Example",
        rows=[
            {
                "rule_id": "CARD_1_behavior",
                "card_id": "CARD_1",
                "surface": "CARDID.json",
                "intent": "play_according_to_role",
            }
        ],
    )

    config = files["CARD_1.json"]
    assert config["GameCardId"] == "CARD_1"
    assert "InHandPlayPriority" in config
    assert config["InHandPlayPriority"]["values"][0]["value"] == "10"
```

- [ ] **Step 2: Implement CardID compiler**

Create `src/hsconfig/compile_cardid.py`:

```python
from __future__ import annotations

from typing import Any


def compile_cardid_behaviors(
    *,
    deck_name: str,
    rows: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    files: dict[str, dict[str, Any]] = {}
    for row in rows:
        if row.get("surface") != "CARDID.json":
            continue
        card_id = row["card_id"]
        config = files.setdefault(
            f"{card_id}.json",
            {"GameCardId": card_id, "ConfigComment": f"{deck_name}: generated behavior for {card_id}"},
        )
        config.setdefault("InHandPlayPriority", {"values": []})["values"].append(
            {
                "comment": f"{deck_name}: {row['rule_id']}",
                "condition": row.get("condition", "*"),
                "value": row.get("value", "10"),
            }
        )
    return files
```

- [ ] **Step 3: Run tests**

```powershell
python -m pytest tests/test_compile_cardid.py -v
```

Expected: `1 passed`.

- [ ] **Step 4: Commit**

```powershell
git add src/hsconfig/compile_cardid.py tests/test_compile_cardid.py
git commit -m "feat: compile card behavior files"
```

---

## Task 10: Combo And Optional Surface Compilers

**Files:**
- Create: `src/hsconfig/compile_combo.py`
- Create: `src/hsconfig/compile_optional_surfaces.py`
- Test: `tests/test_compile_combo.py`
- Test: `tests/test_compile_optional_surfaces.py`

- [ ] **Step 1: Write Combo tests**

Create `tests/test_compile_combo.py`:

```python
from hsconfig.compile_combo import compile_combo


def test_compile_combo_emits_same_turn_sequence():
    combo = compile_combo(
        deck_name="Example",
        sequences=[
            {
                "rule_id": "combo_1",
                "cards": ["A", "B"],
                "operator": ">>",
                "values": ["5", "10"],
            }
        ],
    )

    row = combo["ComboList"]["values"][0]
    assert row["combo"] == "A >> B"
    assert row["value"] == "5 >> 10"
```

- [ ] **Step 2: Implement Combo compiler**

Create `src/hsconfig/compile_combo.py`:

```python
from __future__ import annotations

from typing import Any


def compile_combo(*, deck_name: str, sequences: list[dict[str, Any]]) -> dict[str, Any]:
    values = []
    for sequence in sequences:
        cards = sequence["cards"]
        value_parts = sequence["values"]
        operator = sequence.get("operator", ">>")
        if len(cards) < 2 or len(cards) != len(value_parts):
            raise ValueError(f"Invalid combo sequence {sequence['rule_id']}")
        values.append(
            {
                "comment": f"{deck_name}: {sequence['rule_id']}",
                "condition": sequence.get("condition", "*"),
                "combo": f" {operator} ".join(cards),
                "value": f" {operator} ".join(value_parts),
            }
        )
    return {"GameCardId": "Combo", "ConfigComment": f"{deck_name} generated combos", "ComboList": {"values": values}}
```

- [ ] **Step 3: Write optional surface tests**

Create `tests/test_compile_optional_surfaces.py`:

```python
from hsconfig.compile_optional_surfaces import compile_concede, compile_presume


def test_compile_presume_requires_enabled_policy():
    result = compile_presume(deck_name="Example", assumptions=[], enabled=False)

    assert result["emitted"] is False


def test_compile_concede_requires_enabled_policy():
    result = compile_concede(deck_name="Example", rules=[], enabled=False)

    assert result["emitted"] is False
```

- [ ] **Step 4: Implement optional surfaces**

Create `src/hsconfig/compile_optional_surfaces.py`:

```python
from __future__ import annotations

from typing import Any


def compile_presume(*, deck_name: str, assumptions: list[dict[str, Any]], enabled: bool) -> dict[str, Any]:
    if not enabled:
        return {"emitted": False, "reason": "Presume surface not enabled for this package."}
    return {
        "emitted": True,
        "config": {
            "GameCardId": "Presume",
            "ConfigComment": f"{deck_name} generated presume rules",
            "Presume": {"values": assumptions},
        },
    }


def compile_concede(*, deck_name: str, rules: list[dict[str, Any]], enabled: bool) -> dict[str, Any]:
    if not enabled:
        return {"emitted": False, "reason": "Concede surface not enabled for this package."}
    return {
        "emitted": True,
        "config": {
            "GameCardId": "Concede",
            "ConfigComment": f"{deck_name} generated concede rules",
            "Concede": {"values": rules},
        },
    }
```

- [ ] **Step 5: Run tests**

```powershell
python -m pytest tests/test_compile_combo.py tests/test_compile_optional_surfaces.py -v
```

Expected: `3 passed`.

- [ ] **Step 6: Commit**

```powershell
git add src/hsconfig/compile_combo.py src/hsconfig/compile_optional_surfaces.py tests/test_compile_combo.py tests/test_compile_optional_surfaces.py
git commit -m "feat: compile combo and optional surfaces"
```

---

## Task 11: Build Pipeline And CLI

**Files:**
- Create: `src/hsconfig/cli.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write CLI smoke test**

Create `tests/test_cli.py`:

```python
import json

from hsconfig.cli import main


def test_validate_missing_package_returns_nonzero(tmp_path, capsys):
    code = main(["validate", "--package", str(tmp_path / "missing"), "--json"])

    captured = capsys.readouterr()
    assert code == 1
    assert json.loads(captured.out)["status"] == "failed"
```

- [ ] **Step 2: Implement CLI skeleton**

Create `src/hsconfig/cli.py`:

```python
from __future__ import annotations

import argparse
import json
from pathlib import Path

from hsconfig.validate_package import validate_config_package


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hsconfig")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build")
    build.add_argument("--deck-name", required=True)
    build.add_argument("--deck-code", required=True)
    build.add_argument("--runtime-root", required=True)
    build.add_argument("--out", required=True)
    build.add_argument("--json", action="store_true")

    validate = subparsers.add_parser("validate")
    validate.add_argument("--package", required=True)
    validate.add_argument("--json", action="store_true")

    apply = subparsers.add_parser("apply")
    apply.add_argument("--package", required=True)
    apply.add_argument("--runtime-root", required=True)
    apply.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)
    if args.command == "validate":
        package = Path(args.package)
        if not package.exists():
            return _emit({"status": "failed", "errors": [f"Package not found: {package}"]}, args.json, 1)
        report = validate_config_package(package)
        return _emit(report, args.json, 0 if report["status"] == "passed" else 1)
    if args.command == "build":
        return _emit({"status": "failed", "errors": ["Build pipeline not wired until Task 12."]}, args.json, 1)
    if args.command == "apply":
        return _emit({"status": "failed", "errors": ["Runtime apply not wired until Task 12."]}, args.json, 1)
    return 1


def _emit(payload: dict, as_json: bool, code: int) -> int:
    if as_json:
        print(json.dumps(payload, sort_keys=True))
    else:
        print(payload)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: Run CLI test**

```powershell
python -m pytest tests/test_cli.py -v
```

Expected: `1 passed`.

- [ ] **Step 4: Commit**

```powershell
git add src/hsconfig/cli.py tests/test_cli.py
git commit -m "feat: add hsconfig cli skeleton"
```

---

## Task 12: End-To-End Preview Builder And Runtime Apply

**Files:**
- Modify: `src/hsconfig/cli.py`
- Create: `src/hsconfig/runtime_apply.py`
- Test: `tests/test_e2e_preview.py`
- Test: `tests/test_runtime_apply.py`

- [ ] **Step 1: Write E2E preview test**

Create `tests/test_e2e_preview.py`:

```python
import json
from pathlib import Path

from hsconfig.cli import main


def test_build_preview_creates_package(tmp_path: Path):
    out = tmp_path / "shadow"
    code = main(
        [
            "build",
            "--deck-name",
            "FixtureDeck",
            "--deck-code",
            "fixture-code",
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(out),
            "--json",
        ]
    )

    assert code == 0
    assert (out / "CustomConfig" / "fixturedeck" / "GlobalValues.json").exists()
    assert (out / "reports" / "validation_report.json").exists()
    report = json.loads((out / "reports" / "validation_report.json").read_text(encoding="utf-8"))
    assert report["status"] == "passed"
```

- [ ] **Step 2: Implement preview builder inside CLI**

Modify `src/hsconfig/cli.py` build branch:

```python
from hsconfig.compile_globalvalues import compile_globalvalues
from hsconfig.compile_mulligan import compile_mulligan
from hsconfig.io import slugify_deck_name, write_json
```

Replace build branch with:

```python
    if args.command == "build":
        deck_slug = slugify_deck_name(args.deck_name)
        out = Path(args.out)
        deck_dir = out / "CustomConfig" / deck_slug
        baseline = {
            "GameCardId": "GlobalValues",
            "ConfigComment": "Fallback baseline",
            "FirstTurnValueWeight": {"values": [{"condition": "*", "value": "0"}]},
            "SecondTurnValueWeight": {"values": [{"condition": "*", "value": "1"}]},
        }
        global_result = compile_globalvalues(baseline=baseline, posture={"speed": "aggro", "mechanic_priorities": {}})
        write_json(deck_dir / "GlobalValues.json", global_result["config"])
        write_json(out / "reports" / "global_values_key_profile_report.json", global_result["profile"])
        write_json(deck_dir / "Mulligan.json", compile_mulligan(deck_name=args.deck_name, rows=[], add_discard_fallback=False))
        report = validate_config_package(out)
        write_json(out / "reports" / "validation_report.json", report)
        return _emit({"status": report["status"], "package": str(out)}, args.json, 0 if report["status"] == "passed" else 1)
```

- [ ] **Step 3: Write runtime apply tests**

Create `tests/test_runtime_apply.py`:

```python
from pathlib import Path

from hsconfig.io import write_json
from hsconfig.runtime_apply import apply_package


def test_apply_package_writes_deck_config_and_files(tmp_path: Path):
    package = tmp_path / "package"
    deck_dir = package / "CustomConfig" / "deck"
    write_json(deck_dir / "GlobalValues.json", {"GameCardId": "GlobalValues"})
    runtime = tmp_path / "runtime"

    receipt = apply_package(package_root=package, runtime_root=runtime, deck_name="Deck", config_dir="deck")

    assert receipt["runtime_write_performed"] is True
    assert (runtime / "CustomConfig" / "deck_config.ini").exists()
    assert (runtime / "CustomConfig" / "deck" / "GlobalValues.json").exists()
```

- [ ] **Step 4: Implement runtime apply**

Create `src/hsconfig/runtime_apply.py`:

```python
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any


def apply_package(
    *,
    package_root: str | Path,
    runtime_root: str | Path,
    deck_name: str,
    config_dir: str,
) -> dict[str, Any]:
    package_root = Path(package_root)
    runtime_root = Path(runtime_root)
    source_dir = package_root / "CustomConfig" / config_dir
    target_root = runtime_root / "CustomConfig"
    target_dir = target_root / config_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    for source_file in source_dir.glob("*.json"):
        shutil.copy2(source_file, target_dir / source_file.name)
    deck_config = target_root / "deck_config.ini"
    deck_config.parent.mkdir(parents=True, exist_ok=True)
    deck_config.write_text(f"[CONFIGS]\n{deck_name} = {config_dir}\n", encoding="utf-8")
    return {
        "runtime_write_performed": True,
        "deck_name": deck_name,
        "config_dir": config_dir,
        "runtime_root": str(runtime_root),
    }
```

- [ ] **Step 5: Wire apply command**

Modify `src/hsconfig/cli.py` apply branch:

```python
from hsconfig.runtime_apply import apply_package
```

Replace apply branch with:

```python
    if args.command == "apply":
        package = Path(args.package)
        if not package.exists():
            return _emit({"status": "failed", "errors": [f"Package not found: {package}"]}, args.json, 1)
        custom_dirs = [path for path in (package / "CustomConfig").iterdir() if path.is_dir()]
        if len(custom_dirs) != 1:
            return _emit({"status": "failed", "errors": ["Expected exactly one CustomConfig deck directory."]}, args.json, 1)
        config_dir = custom_dirs[0].name
        receipt = apply_package(package_root=package, runtime_root=args.runtime_root, deck_name=config_dir, config_dir=config_dir)
        return _emit({"status": "applied", "receipt": receipt}, args.json, 0)
```

- [ ] **Step 6: Run E2E tests**

```powershell
python -m pytest tests/test_e2e_preview.py tests/test_runtime_apply.py tests/test_cli.py -v
```

Expected: `3 passed`.

- [ ] **Step 7: Commit**

```powershell
git add src/hsconfig/cli.py src/hsconfig/runtime_apply.py tests/test_e2e_preview.py tests/test_runtime_apply.py
git commit -m "feat: add preview build and runtime apply"
```

---

## Task 13: Repo-Local Codex Skill

**Files:**
- Create: `.agents/skills/hsconfig/SKILL.md`
- Create: `.agents/skills/hsconfig/references/workflow.md`
- Create: `.agents/skills/hsconfig/references/visionai-surfaces.md`
- Create: `.agents/skills/hsconfig/references/guide-research-policy.md`
- Create: `.agents/skills/hsconfig/references/globalvalues-policy.md`
- Create: `.agents/skills/hsconfig/references/card-behavior-policy.md`
- Create: `.agents/skills/hsconfig/references/output-contract.md`
- Create: `.agents/skills/hsconfig/scripts/build_config.py`
- Create: `.agents/skills/hsconfig/scripts/validate_package.py`
- Test: `tests/test_skill_files.py`

- [ ] **Step 1: Write skill file tests**

Create `tests/test_skill_files.py`:

```python
from pathlib import Path


SKILL_ROOT = Path(".agents/skills/hsconfig")


def test_skill_has_required_files():
    assert (SKILL_ROOT / "SKILL.md").exists()
    assert (SKILL_ROOT / "references" / "globalvalues-policy.md").exists()
    assert (SKILL_ROOT / "scripts" / "build_config.py").exists()


def test_skill_frontmatter_mentions_deck_config_generation():
    text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    assert "name: hsconfig" in text
    assert "HearthRanger" in text
    assert "GlobalValues" in text
```

- [ ] **Step 2: Create `SKILL.md`**

```markdown
---
name: hsconfig
description: Generate aggressive guide-aligned HearthRanger VisionAI CustomConfig packages from a Hearthstone deck name and deck code. Use when Codex must create Mulligan.json, GlobalValues.json, per-card CARDID.json, Combo.json, or optional Presume/Concede for a deck before games are played.
---

# HSConfig

Use this skill to turn a Hearthstone deck into a HearthRanger VisionAI `CustomConfig` package.

Required inputs:

- deck name
- deck code
- runtime root if applying to HearthRanger

Workflow:

1. Decode deck identity.
2. Resolve CardIDs and card metadata.
3. Research current guides and data sources.
4. Build aggressive gameplan contracts.
5. Compile `Mulligan.json`, full-key `GlobalValues.json`, `<CARDID>.json`, `Combo.json`, and optional `Presume.json` / `Concede.json`.
6. Validate package before runtime apply.

Read references only when needed:

- `references/workflow.md` for the full flow.
- `references/visionai-surfaces.md` for runtime file surfaces.
- `references/globalvalues-policy.md` before generating `GlobalValues.json`.
- `references/card-behavior-policy.md` before generating `<CARDID>.json`.
- `references/output-contract.md` before final validation.

Do not use this skill for replay parsing, winrate analysis, post-run tuning, or HSTuner candidate promotion.
```

- [ ] **Step 3: Create reference stubs with concrete policy**

Create `.agents/skills/hsconfig/references/globalvalues-policy.md`:

```markdown
# GlobalValues Policy

`GlobalValues.json` must be generated for every deck.

Rules:

- Copy the full default baseline.
- Profile every key.
- Classify every key.
- Apply deckplan overlays when guide posture implies them.
- Explain every unchanged key.
- Emit `global_values_key_profile_report.json`.
- Never emit a reduced partial `GlobalValues.json`.
```

Create `.agents/skills/hsconfig/references/card-behavior-policy.md`:

```markdown
# Card Behavior Policy

Every deck card must be checked against the gameplan.

Emit `<CARDID>.json` when documented VisionAI syntax can express a guide-backed behavior, target, priority, discover, choice, attack, hero-power, or timing rule.

If a guide claim cannot be lowered safely, write it to `suppressed_rules_report.json`.
```

Create the remaining references with short concrete text:

```markdown
# Workflow

Build flow: deck input -> identity -> metadata -> guide research -> gameplan -> surface intent -> compilers -> validation -> optional apply.
```

```markdown
# VisionAI Surfaces

Supported surfaces: `deck_config.ini`, `GlobalValues.json`, `Mulligan.json`, `<CARDID>.json`, `Combo.json`, optional `Presume.json`, optional `Concede.json`.
```

```markdown
# Guide Research Policy

Use current guide and data sources aggressively as strategic priors. Record URL, retrieval date, patch context, claim confidence, and affected cards for every claim.
```

```markdown
# Output Contract

A build produces `contracts/`, `CustomConfig/`, and `reports/`. Every emitted row must have provenance and every suppressed claim must be visible.
```

- [ ] **Step 4: Create skill scripts**

Create `.agents/skills/hsconfig/scripts/build_config.py`:

```python
#!/usr/bin/env python
from hsconfig.cli import main

raise SystemExit(main(["build", *(__import__("sys").argv[1:])]))
```

Create `.agents/skills/hsconfig/scripts/validate_package.py`:

```python
#!/usr/bin/env python
from hsconfig.cli import main

raise SystemExit(main(["validate", *(__import__("sys").argv[1:])]))
```

- [ ] **Step 5: Run skill tests**

```powershell
python -m pytest tests/test_skill_files.py -v
```

Expected: `2 passed`.

- [ ] **Step 6: Commit**

```powershell
git add .agents/skills/hsconfig tests/test_skill_files.py
git commit -m "feat: add hsconfig codex skill"
```

---

## Task 14: Final QA, Docs, And GitHub Push

**Files:**
- Modify: `README.md`
- Verify: all files

- [ ] **Step 1: Run full tests**

```powershell
python -m pytest -v
```

Expected: all tests pass.

- [ ] **Step 2: Run CLI smoke commands**

```powershell
hsconfig build --deck-name "FixtureDeck" --deck-code "fixture-code" --runtime-root "C:\Users\darbo\Desktop\HS" --out ".\outputs\fixturedeck" --json
hsconfig validate --package ".\outputs\fixturedeck" --json
```

Expected:

- build returns JSON with `"status": "passed"`
- validate returns JSON with `"status": "passed"`

- [ ] **Step 3: Confirm ignored generated outputs**

```powershell
git status --short
```

Expected: no `outputs/` files shown.

- [ ] **Step 4: Update README with current command examples**

If command output differs from Task 1 README, update `README.md` to match the working CLI exactly.

- [ ] **Step 5: Commit final docs if changed**

```powershell
git add README.md
git diff --cached --quiet; if ($LASTEXITCODE -ne 0) { git commit -m "docs: update hsconfig usage" }
```

- [ ] **Step 6: Push main**

```powershell
git status --short --branch
git push -u origin main
```

Expected: branch `main` is pushed to `Teufelsboy/HSConfig`.

---

## Self-Review Checklist

- Spec coverage: all design sections are represented by tasks: repo bootstrap, contracts, deck identity, metadata, guide research, gameplan, surface routing, all compilers, validation, runtime apply, skill packaging, QA.
- GlobalValues requirement: Task 8 implements full-key profiling, explicit decisions, and complete `GlobalValues.json` emission.
- Non-conservative requirement: Tasks 4, 6, 7, 8, 9, and 10 turn guide/card expectations into runtime surfaces instead of leaving them only in prose.
- Lean boundary: no tasks add replay parsing, HDT parsing, winrate, candidate promotion, or post-run tuning.
- GitHub requirement: Task 14 pushes `main` to `origin`.

